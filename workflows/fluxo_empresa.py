"""Fluxo da empresa em LangGraph: do arquivo recebido à homologação, com pausas para a pessoa decidir.

O fluxo só LIGA os serviços que já existem (nenhuma regra é reescrita aqui) e decide a próxima etapa:

    perfilar → recuperar_conhecimento → interpretar → aprovar_mapeamento (pausa)
    → padronizar → validar ─┬─ sem pendências → aprovar_homologacao (pausa: a empresa envia ao banco)
                            │     → avaliar_no_banco (pausa: o banco aprova ou devolve)
                            │           ├─ aprovado → liberar_planejamento → fim
                            │           └─ devolvido com motivo → aguardar_correcao
                            └─ com pendências → aguardar_correcao (pausa) → validar (de novo)

Os nomes do plano (em inglês) correspondem a: profile = perfilar, retrieve = recuperar_conhecimento,
interpret = interpretar, approve_mapping = aprovar_mapeamento, transform = padronizar, validate = validar,
wait_correction = aguardar_correcao, approve_homologation = aprovar_homologacao.

Garantias:
- Pausa e retomada (ADR-15, ADR-39): o estado de cada arquivo fica gravado num ponto de salvamento
  (checkpointer SQLite) com thread_id = processamento_id. Recarregar a página não refaz nada.
- O estado só guarda identificadores, situação, contagens e decisões de coluna: nenhum dado pessoal.
- Handoff: se o Assistente devolveu o mapeamento ao aceite (ADR-17), o fluxo volta para aprovar_mapeamento.
- Falha não vira falso sucesso: uma etapa que quebra leva a aguardar_nova_tentativa, e o arquivo não
  avança. Há limite de ciclos de correção e de tentativas depois de falha.
- Pausa pelo teto de gasto (ADR-131): se a IA foi pausada pelo teto do dia ou do mês, a etapa também espera em
  aguardar_nova_tentativa, com o recado para a empresa, mas SEM contar como falha: o envio nunca é rejeitado por isso.
- Pausa pela falha da IA real (ADR-145): se o provedor falhou (ou a operação passou do limite de chamadas), a etapa
  espera do mesmo jeito, com o mesmo recado e o botão "Tentar de novo". Nada é simulado no lugar da resposta real.
- Cada etapa grava uma execução (AgentRunEvent) para a telemetria (services/execucoes.py).
- A homologação libera o planejamento do banco uma única vez.
- Avaliação do banco (ADR-69, passo 15): o clique final da empresa ENVIA o arquivo ao banco; os funcionários só
  ficam cadastrados quando o especialista aprova. Devolvido, o arquivo volta para a correção, com o motivo.
"""
import sqlite3
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from models.contratos import EstadoProcessamento
from rag.busca import indice_disponivel
from services import (auditoria, banco, config, execucoes, homologacao, mapeamentos, motor_planejamento, normalizador,
                      processamentos, teto_de_gasto, uso_da_ia, validador)
# A IA real que não respondeu (ADR-145): a etapa pausa como no teto de gasto, sem resposta simulada no lugar
from services.llm_client import IAIndisponivel

# Quantas vezes a empresa pode pedir revalidação no mesmo arquivo antes de o fluxo encerrar
LIMITE_CICLOS_DE_CORRECAO = 20
# Quantas vezes uma etapa que falhou pode ser tentada de novo antes de o fluxo encerrar
LIMITE_DE_TENTATIVAS = 3


class EstadoDoFluxo(TypedDict):
    """O que o fluxo guarda (e grava no ponto de salvamento). Nenhum dado pessoal entra aqui."""

    processamento_id: str
    empresa_id: str
    status: str                        # a situação do arquivo (EstadoProcessamento)
    configuracao: str | None           # B3 (com RAG) ou B2 (sem índice), escolhida em recuperar_conhecimento
    versao_layout: int | None          # a versão do layout usada no mapeamento
    pendencias: dict                   # contagem por severidade na última validação
    decisoes_de_coluna: dict           # coluna -> "DMY", "MDY" ou "zeros:N" (decisões da empresa)
    ciclos_de_correcao: int            # quantas revalidações a empresa já pediu
    handoffs: int                      # quantas vezes o Assistente devolveu o mapeamento ao aceite
    falhas: int                        # quantas etapas falharam
    etapa_com_falha: str | None        # a etapa a tentar de novo depois de uma falha
    motivo_da_rejeicao: str | None     # por que o arquivo foi rejeitado (um código, nunca texto livre)
    ultimo_erro: str | None            # o último recado para a tela (ex.: coluna AMBIGUO sem decisão)
    proximo_passo: str                 # a próxima etapa, decidida pela etapa atual


def _agora() -> datetime:
    """O momento atual, no horário universal."""
    return datetime.now(timezone.utc)


def _seguir(estado: EstadoDoFluxo) -> str:
    """As setas do fluxo: cada etapa escreve em "proximo_passo" para onde o arquivo vai."""
    return estado["proximo_passo"]


class FluxoDaEmpresa:
    """As etapas do fluxo. Guarda a conexão com o banco (que não pode ir para o ponto de salvamento)."""

    def __init__(self, conexao, cliente=None, busca=None):
        """conexao: o banco da aplicação; cliente e busca: o LLM e o RAG (os testes trocam por versões falsas)."""
        self.conexao = conexao
        self.cliente = cliente
        self.busca = busca

    # ---------------- Ferramentas das etapas ----------------

    def _executar_etapa(self, estado: EstadoDoFluxo, etapa: str, agente: str, trabalho) -> dict:
        """Roda o trabalho da etapa, mede o tempo e grava a execução (AgentRunEvent).

        trabalho() devolve (mudancas_no_estado, detalhes), em que detalhes pode ter "modelo",
        "versao_prompt" e "guardrail_disparado". Se o trabalho quebrar, a execução é gravada como ERRO e o
        fluxo vai para aguardar_nova_tentativa: a falha nunca vira falso sucesso.
        """
        inicio = _agora()
        # O taxímetro da etapa: as chamadas à IA feitas dentro do trabalho somam aqui (tokens e custo; ADR-131)
        with uso_da_ia.medir() as uso:
            try:
                mudancas, detalhes = trabalho()
            except GraphBubbleUp:
                # É a pausa do LangGraph (não é erro): deixa passar
                raise
            except teto_de_gasto.TetoDeGastoAtingido:
                # A IA foi pausada pelo teto de gasto (dia ou mês; ADR-131): o envio espera, sem se perder. Não conta
                # como falha (senão, 3 pausas rejeitariam o envio); o banco vê o ERRO na Telemetria
                execucoes.registrar_pausa_pelo_teto(self.conexao, estado["processamento_id"], estado["empresa_id"],
                                                    etapa, agente, inicio, uso)
                return {"etapa_com_falha": etapa, "ultimo_erro": teto_de_gasto.RECADO_PARA_A_EMPRESA,
                        "proximo_passo": "aguardar_nova_tentativa"}
            except IAIndisponivel:
                # A IA real não respondeu (o provedor falhou, ou o limite da operação; ADR-145): a mesma pausa do teto.
                # O envio espera em "tentar de novo", com o mesmo recado, e nada é simulado no lugar. Também não conta
                # como falha (um provedor fora do ar não pode rejeitar o envio); o banco vê o ERRO na Telemetria
                execucoes.registrar_queda_da_ia(self.conexao, estado["processamento_id"], estado["empresa_id"],
                                                etapa, agente, inicio, uso)
                return {"etapa_com_falha": etapa, "ultimo_erro": teto_de_gasto.RECADO_PARA_A_EMPRESA,
                        "proximo_passo": "aguardar_nova_tentativa"}
            except Exception as erro:
                # Grava só o TIPO do erro (sem mensagem, que poderia trazer dado)
                execucoes.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"], etapa, agente,
                                    inicio, _agora(), execucoes.ERRO, tipo_erro=type(erro).__name__, uso=uso)
                return {"falhas": estado["falhas"] + 1, "etapa_com_falha": etapa,
                        "ultimo_erro": f"A etapa {etapa} falhou ({type(erro).__name__}: {erro}).",
                        "proximo_passo": "aguardar_nova_tentativa"}
        execucoes.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"], etapa, agente, inicio,
                            _agora(), execucoes.OK, modelo=detalhes.get("modelo"),
                            versao_prompt=detalhes.get("versao_prompt"),
                            guardrail_disparado=detalhes.get("guardrail_disparado", False), uso=uso)
        return mudancas

    def _mapeamento_voltou_para_o_aceite(self, estado: EstadoDoFluxo) -> bool:
        """True se o mapeamento está PENDENTE de novo (o Assistente pediu remapeamento: handoff)."""
        return mapeamento_voltou_para_o_aceite(self.conexao, estado["processamento_id"])

    def _voltar_para_o_aceite(self, estado: EstadoDoFluxo) -> dict:
        """As mudanças no estado quando um handoff devolveu o mapeamento à empresa."""
        return {"handoffs": estado["handoffs"] + 1, "status": EstadoProcessamento.MAPEAMENTO_PENDENTE.value,
                "ultimo_erro": None, "proximo_passo": "aprovar_mapeamento"}

    # ---------------- Etapas automáticas ----------------

    def perfilar(self, estado: EstadoDoFluxo) -> dict:
        """profile: confere que o arquivo foi recebido e retratado (a leitura acontece no envio)."""
        def trabalho():
            perfil = processamentos.obter_da_empresa(self.conexao, estado["processamento_id"], estado["empresa_id"])
            if perfil is None:
                raise KeyError("processamento não encontrado")
            processamentos.atualizar_status(self.conexao, estado["processamento_id"], EstadoProcessamento.PERFILADO)
            return {"status": EstadoProcessamento.PERFILADO.value, "proximo_passo": "recuperar_conhecimento"}, {}
        return self._executar_etapa(estado, "perfilar", "Regra", trabalho)

    def recuperar_conhecimento(self, estado: EstadoDoFluxo) -> dict:
        """retrieve: escolhe como o Interpretador consulta o conhecimento: pela busca (B3) ou inteiro (B2)."""
        def trabalho():
            # Com o índice do RAG montado (ou uma busca de teste), B3; sem índice, o histórico vai inteiro (B2)
            if self.busca is not None or indice_disponivel():
                configuracao = "B3"
            else:
                configuracao = "B2"
            return {"configuracao": configuracao, "proximo_passo": "interpretar"}, {}
        return self._executar_etapa(estado, "recuperar_conhecimento", "RAG", trabalho)

    def interpretar(self, estado: EstadoDoFluxo) -> dict:
        """interpret: o Interpretador propõe o mapeamento (reaproveitando o que a empresa já aprovou)."""
        def trabalho():
            existente = mapeamentos.obter(self.conexao, estado["processamento_id"])
            # Mapeamento já aprovado antes (ex.: arquivo tratado antes deste fluxo existir): segue adiante
            if existente is not None and existente[1] == "APROVADO":
                return {"versao_layout": existente[0].versao_layout, "proximo_passo": "padronizar"}, {}
            plano = mapeamentos.interpretar_processamento(self.conexao, estado["processamento_id"],
                                                          estado["empresa_id"], cliente=self.cliente,
                                                          configuracao=estado["configuracao"], busca=self.busca)
            # O guardrail de saída (ou uma nova tentativa) deixa observações no plano
            detalhes = {"modelo": plano.modelo, "versao_prompt": plano.versao_prompt,
                        "guardrail_disparado": bool(plano.observacoes)}
            return {"status": EstadoProcessamento.MAPEAMENTO_PENDENTE.value, "versao_layout": plano.versao_layout,
                    "proximo_passo": "aprovar_mapeamento"}, detalhes
        return self._executar_etapa(estado, "interpretar", "Interpretador", trabalho)

    def padronizar(self, estado: EstadoDoFluxo) -> dict:
        """transform: o Normalizador padroniza, com as decisões de coluna já tomadas pela empresa."""
        def trabalho():
            decisoes = dict(normalizador.decisoes_salvas(self.conexao, estado["processamento_id"]))
            decisoes.update(estado["decisoes_de_coluna"])
            normalizador.executar(self.conexao, estado["processamento_id"], estado["empresa_id"], decisoes)
            return {"proximo_passo": "validar"}, {}
        return self._executar_etapa(estado, "padronizar", "Normalizador", trabalho)

    def validar(self, estado: EstadoDoFluxo) -> dict:
        """validate: o Validador aponta as pendências; sem nenhuma, o arquivo segue para a homologação."""
        def trabalho():
            if self._mapeamento_voltou_para_o_aceite(estado):
                return self._voltar_para_o_aceite(estado), {}
            relatorio = validador.executar(self.conexao, estado["processamento_id"], estado["empresa_id"])
            if relatorio.pronto_para_homologar:
                status, proximo = EstadoProcessamento.NORMALIZADO, "aprovar_homologacao"
            else:
                status, proximo = EstadoProcessamento.VALIDACAO_PENDENTE, "aguardar_correcao"
            return {"status": status.value, "pendencias": relatorio.contagem(), "proximo_passo": proximo}, {}
        return self._executar_etapa(estado, "validar", "Validador", trabalho)

    def liberar_planejamento(self, estado: EstadoDoFluxo) -> dict:
        """O arquivo foi homologado: o motor de planejamento classifica os funcionários (uma vez só)."""
        def trabalho():
            contagem = motor_planejamento.processar_homologacao(self.conexao, estado["processamento_id"],
                                                                estado["empresa_id"])
            auditoria.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"], "Planejamento",
                                "PLANEJAMENTO_LIBERADO", {"funcionarios_novos": contagem["novos"]})
            return {"proximo_passo": "fim"}, {}
        return self._executar_etapa(estado, "liberar_planejamento", "Motor de planejamento", trabalho)

    def rejeitar(self, estado: EstadoDoFluxo) -> dict:
        """O arquivo não segue: situação REJEITADO, com o motivo registrado (um código, sem texto livre)."""
        def trabalho():
            processamentos.atualizar_status(self.conexao, estado["processamento_id"], EstadoProcessamento.REJEITADO)
            auditoria.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"], "Fluxo", "REJEITADO",
                                {"motivo": estado["motivo_da_rejeicao"]})
            return {"status": EstadoProcessamento.REJEITADO.value, "proximo_passo": "fim"}, {}
        return self._executar_etapa(estado, "rejeitar", "Regra", trabalho)

    # ---------------- Pausas: a pessoa decide ----------------
    # Atenção: o LangGraph roda a etapa de novo, desde o começo, quando a pessoa responde. Por isso nada que
    # mude dados pode vir ANTES do interrupt() (a mesma regra do spike).

    def aprovar_mapeamento(self, estado: EstadoDoFluxo) -> dict:
        """approve_mapping: espera o aceite. Respostas: {"acao": "aprovar", "escolhas": {...}, "usuario": ...}
        ou {"acao": "rejeitar"}."""
        resposta = interrupt({"etapa": "aprovar_mapeamento", "erro": estado["ultimo_erro"],
                              "pergunta": "Confira o mapeamento das colunas e aceite (ou escolha o campo das AMBIGUO)."})

        def trabalho():
            acao = resposta.get("acao")
            if acao == "rejeitar":
                return {"motivo_da_rejeicao": "pedido da empresa", "proximo_passo": "rejeitar"}, {}
            if acao != "aprovar":
                return {"ultimo_erro": f"Ação desconhecida: {acao}.", "proximo_passo": "aprovar_mapeamento"}, {}
            try:
                mapeamentos.aprovar(self.conexao, estado["processamento_id"], estado["empresa_id"],
                                    resposta.get("escolhas", {}), resposta.get("usuario", "empresa"))
            except ValueError as erro:
                # Recusa de negócio (ex.: coluna AMBIGUO sem decisão): pergunta de novo, com o motivo
                return {"ultimo_erro": str(erro), "proximo_passo": "aprovar_mapeamento"}, {}
            return {"status": EstadoProcessamento.MAPEAMENTO_APROVADO.value, "ultimo_erro": None,
                    "proximo_passo": "padronizar"}, {}
        return self._executar_etapa(estado, "aprovar_mapeamento", "Humano", trabalho)

    def aguardar_correcao(self, estado: EstadoDoFluxo) -> dict:
        """wait_correction: a empresa corrige ou justifica (cada correção já revalida) e depois pede para seguir.

        Respostas: {"acao": "revalidar"}, {"acao": "decidir_colunas", "decisoes": {...}} ou {"acao": "rejeitar"}.
        """
        resposta = interrupt({"etapa": "aguardar_correcao", "pendencias": estado["pendencias"],
                              "erro": estado["ultimo_erro"],
                              "pergunta": "Corrija ou justifique as pendências e peça a revalidação."})

        def trabalho():
            # O Assistente devolveu o mapeamento ao aceite (handoff): qualquer resposta leva ao aceite
            if self._mapeamento_voltou_para_o_aceite(estado):
                return self._voltar_para_o_aceite(estado), {}
            acao = resposta.get("acao")
            if acao == "rejeitar":
                return {"motivo_da_rejeicao": "pedido da empresa", "proximo_passo": "rejeitar"}, {}
            if acao not in ("revalidar", "decidir_colunas"):
                return {"ultimo_erro": f"Ação desconhecida: {acao}.", "proximo_passo": "aguardar_correcao"}, {}
            # Cada pedido para seguir é um ciclo de correção; passou do limite, o fluxo encerra
            ciclos = estado["ciclos_de_correcao"] + 1
            if ciclos > LIMITE_CICLOS_DE_CORRECAO:
                return {"ciclos_de_correcao": ciclos, "motivo_da_rejeicao": "limite de ciclos de correção",
                        "proximo_passo": "rejeitar"}, {}
            if acao == "decidir_colunas":
                # A empresa decidiu o formato de uma coluna (data ou zeros): padroniza de novo
                decisoes = dict(estado["decisoes_de_coluna"])
                decisoes.update(resposta.get("decisoes", {}))
                return {"ciclos_de_correcao": ciclos, "decisoes_de_coluna": decisoes, "ultimo_erro": None,
                        "proximo_passo": "padronizar"}, {}
            return {"ciclos_de_correcao": ciclos, "ultimo_erro": None, "proximo_passo": "validar"}, {}
        return self._executar_etapa(estado, "aguardar_correcao", "Humano", trabalho)

    def aprovar_homologacao(self, estado: EstadoDoFluxo) -> dict:
        """approve_homologation: sem pendências, espera o clique final. Respostas: {"acao": "homologar",
        "usuario": ...}, {"acao": "voltar_a_correcao"} ou {"acao": "rejeitar"}."""
        resposta = interrupt({"etapa": "aprovar_homologacao", "erro": estado["ultimo_erro"],
                              "pergunta": "Sem pendências. Homologar o arquivo?"})

        def trabalho():
            if self._mapeamento_voltou_para_o_aceite(estado):
                return self._voltar_para_o_aceite(estado), {}
            acao = resposta.get("acao")
            if acao == "rejeitar":
                return {"motivo_da_rejeicao": "pedido da empresa", "proximo_passo": "rejeitar"}, {}
            if acao == "voltar_a_correcao":
                return {"ultimo_erro": None, "proximo_passo": "aguardar_correcao"}, {}
            if acao != "homologar":
                return {"ultimo_erro": f"Ação desconhecida: {acao}.", "proximo_passo": "aprovar_homologacao"}, {}
            try:
                # Confere de novo, na hora, que não sobrou pendência (nada de cadastro é gravado aqui)
                homologacao.conferir_antes_do_envio(self.conexao, estado["processamento_id"], estado["empresa_id"])
            except ValueError as erro:
                # A revalidação feita na hora achou pendência: volta para a validação
                return {"ultimo_erro": str(erro), "proximo_passo": "validar"}, {}
            # O arquivo vai para a avaliação do banco: os funcionários só ficam cadastrados quando o banco aprovar
            processamentos.atualizar_status(self.conexao, estado["processamento_id"],
                                            EstadoProcessamento.AGUARDANDO_BANCO)
            auditoria.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"], "Homologação",
                                "ENVIADO_AO_BANCO", {"enviado_por": resposta.get("usuario", "empresa")})
            return {"status": EstadoProcessamento.AGUARDANDO_BANCO.value, "ultimo_erro": None,
                    "proximo_passo": "avaliar_no_banco"}, {}
        return self._executar_etapa(estado, "aprovar_homologacao", "Humano", trabalho)

    def avaliar_no_banco(self, estado: EstadoDoFluxo) -> dict:
        """O especialista do banco avalia o envio. Respostas: {"acao": "aprovar", "usuario": ...},
        {"acao": "aprovar_parte", "linhas_devolvidas": [12, 30], "usuario": ...} ou
        {"acao": "devolver", "motivo": "...", "usuario": ...}.

        Aprovado: o arquivo é homologado (funcionários cadastrados) e o planejamento é liberado.
        Aprovado em parte (ADR-121): o mesmo, sem as pessoas que o banco apontou; elas voltam à empresa num envio de
        devolução, criado depois por services/devolucao_por_pessoa.py.
        Devolvido: o arquivo volta para a correção, com o motivo como recado para a empresa.
        """
        resposta = interrupt({"etapa": "avaliar_no_banco", "erro": estado["ultimo_erro"],
                              "pergunta": "O especialista do banco avalia o envio: aprovar ou devolver com motivo."})

        def trabalho():
            acao = resposta.get("acao")
            avaliado_por = resposta.get("usuario", "banco")
            if acao == "devolver":
                motivo = (resposta.get("motivo") or "").strip()
                # Devolver sem dizer por quê não ajuda a empresa: pergunta de novo
                if not motivo:
                    return {"ultimo_erro": "Escreva o motivo da devolução.", "proximo_passo": "avaliar_no_banco"}, {}
                processamentos.atualizar_status(self.conexao, estado["processamento_id"], EstadoProcessamento.DEVOLVIDO)
                auditoria.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"],
                                    "Avaliação do banco", "DEVOLVIDO_PELO_BANCO",
                                    {"motivo": motivo[:500], "avaliado_por": avaliado_por})
                return {"status": EstadoProcessamento.DEVOLVIDO.value, "ultimo_erro": "Devolvido pelo banco: " + motivo[:500],
                        "proximo_passo": "aguardar_correcao"}, {}
            if acao not in ("aprovar", "aprovar_parte"):
                return {"ultimo_erro": f"Ação desconhecida: {acao}.", "proximo_passo": "avaliar_no_banco"}, {}
            # As pessoas que o banco devolve à empresa (só no "aprovar_parte"; no "aprovar", ninguém)
            linhas_devolvidas = set()
            if acao == "aprovar_parte":
                for linha in resposta.get("linhas_devolvidas", []):
                    linhas_devolvidas.add(int(linha))
            try:
                qualidade = homologacao.homologar(self.conexao, estado["processamento_id"], estado["empresa_id"],
                                                  avaliado_por, linhas_devolvidas)
            except ValueError as erro:
                # Algo mudou desde o envio (ex.: pendência nova): o banco vê o motivo e decide de novo
                return {"ultimo_erro": str(erro), "proximo_passo": "avaliar_no_banco"}, {}
            # Na trilha, só contagens: quantas pessoas o banco aprovou e quantas devolveu
            auditoria.registrar(self.conexao, estado["processamento_id"], estado["empresa_id"], "Avaliação do banco",
                                "APROVADO_PELO_BANCO", {"avaliado_por": avaliado_por,
                                                        "aprovadas": qualidade["registros_homologados"],
                                                        "devolvidas": len(linhas_devolvidas)})
            return {"status": EstadoProcessamento.HOMOLOGADO.value, "ultimo_erro": None,
                    "proximo_passo": "liberar_planejamento"}, {}
        return self._executar_etapa(estado, "avaliar_no_banco", "Humano", trabalho)

    def aguardar_nova_tentativa(self, estado: EstadoDoFluxo) -> dict:
        """Uma etapa falhou: o arquivo para aqui. Respostas: {"acao": "tentar_de_novo"} ou {"acao": "rejeitar"}.

        Passou do limite de tentativas, o fluxo encerra sozinho (sem perguntar).
        """
        if estado["falhas"] > LIMITE_DE_TENTATIVAS:
            return {"motivo_da_rejeicao": "falha repetida", "proximo_passo": "rejeitar"}
        # A pergunta da tela: pausa pelo teto de gasto (a IA volta depois) ou falha da etapa
        if estado["ultimo_erro"] == teto_de_gasto.RECADO_PARA_A_EMPRESA:
            pergunta = teto_de_gasto.RECADO_PARA_A_EMPRESA
        else:
            pergunta = f"A etapa {estado['etapa_com_falha']} falhou. Tentar de novo?"
        resposta = interrupt({"etapa": "aguardar_nova_tentativa", "erro": estado["ultimo_erro"],
                              "pergunta": pergunta})
        acao = resposta.get("acao")
        if acao == "rejeitar":
            return {"motivo_da_rejeicao": "pedido da empresa depois de falha", "proximo_passo": "rejeitar"}
        if acao == "tentar_de_novo":
            return {"ultimo_erro": None, "proximo_passo": estado["etapa_com_falha"]}
        return {"ultimo_erro": f"Ação desconhecida: {acao}.", "proximo_passo": "aguardar_nova_tentativa"}


# ---------------- Montagem do grafo ----------------

# Para cada etapa, as etapas para onde ela pode seguir (as setas do desenho do fluxo)
TODAS_AS_ETAPAS_QUE_PODEM_FALHAR = ["perfilar", "recuperar_conhecimento", "interpretar", "aprovar_mapeamento",
                                    "padronizar", "validar", "aguardar_correcao", "aprovar_homologacao",
                                    "avaliar_no_banco", "liberar_planejamento", "rejeitar"]
DESTINOS = {
    "perfilar": ["recuperar_conhecimento", "aguardar_nova_tentativa"],
    "recuperar_conhecimento": ["interpretar", "aguardar_nova_tentativa"],
    "interpretar": ["aprovar_mapeamento", "padronizar", "aguardar_nova_tentativa"],
    "aprovar_mapeamento": ["padronizar", "aprovar_mapeamento", "rejeitar", "aguardar_nova_tentativa"],
    "padronizar": ["validar", "aguardar_nova_tentativa"],
    "validar": ["aprovar_homologacao", "aguardar_correcao", "aprovar_mapeamento", "aguardar_nova_tentativa"],
    "aguardar_correcao": ["validar", "padronizar", "aprovar_mapeamento", "aguardar_correcao", "rejeitar",
                          "aguardar_nova_tentativa"],
    "aprovar_homologacao": ["avaliar_no_banco", "aguardar_correcao", "aprovar_mapeamento", "validar",
                            "aprovar_homologacao", "rejeitar", "aguardar_nova_tentativa"],
    "avaliar_no_banco": ["liberar_planejamento", "aguardar_correcao", "avaliar_no_banco", "aguardar_nova_tentativa"],
    "aguardar_nova_tentativa": TODAS_AS_ETAPAS_QUE_PODEM_FALHAR + ["aguardar_nova_tentativa"],
    "liberar_planejamento": ["fim", "aguardar_nova_tentativa"],
    "rejeitar": ["fim", "aguardar_nova_tentativa"],
}


# Um ponto de salvamento no PostgreSQL por lugar (endereço + esquema), aberto uma vez só e reaproveitado:
# abrir uma conexão nova a cada clique esgotaria as conexões que o servidor aceita
CHECKPOINTERS_DO_POSTGRES = {}
# As situações em que o fluxo do arquivo acabou. O ponto de salvamento é guardado para sempre (ADR-71
# revisto); se ele se perder (ex.: banco restaurado sem ele), o envio continua aparecendo como
# encerrado e nunca recomeça
ESTADOS_FINAIS = (EstadoProcessamento.HOMOLOGADO, EstadoProcessamento.REJEITADO)


def abrir_checkpointer(conexao):
    """Onde fica o ponto de salvamento de cada processamento: no mesmo banco da aplicação (ADR-49 e ADR-67).

    Com o PostgreSQL, nas tabelas checkpoint* do mesmo banco (e do mesmo esquema) da conexão; com o SQLite, no
    arquivo config.CAMINHO_CHECKPOINTS.
    """
    if banco.e_postgres(conexao):
        return _checkpointer_do_postgres(conexao.url, conexao.esquema)
    caminho = config.CAMINHO_CHECKPOINTS
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: a API atende cada pedido numa "thread" (linha de execução) diferente
    return SqliteSaver(sqlite3.connect(caminho, check_same_thread=False))


def _checkpointer_do_postgres(url: str, esquema: str | None):
    """O ponto de salvamento no PostgreSQL (criado na primeira vez; depois, o mesmo)."""
    lugar = (url, esquema)
    if lugar not in CHECKPOINTERS_DO_POSTGRES:
        # Importados só aqui: quem usa SQLite não precisa dessas bibliotecas
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        # As opções que a biblioteca do LangGraph exige: cada gravação confirmada na hora (autocommit), sem comandos
        # preparados no servidor e linhas lidas como dicionário
        conexao_do_checkpointer = psycopg.connect(url, options=banco.opcoes_do_esquema(esquema), autocommit=True,
                                                  prepare_threshold=0, row_factory=dict_row)
        checkpointer = PostgresSaver(conexao_do_checkpointer)
        # Cria as tabelas do ponto de salvamento, se ainda não existirem
        checkpointer.setup()
        CHECKPOINTERS_DO_POSTGRES[lugar] = checkpointer
    return CHECKPOINTERS_DO_POSTGRES[lugar]


def construir(conexao, cliente=None, busca=None):
    """Monta o fluxo: as etapas, as setas entre elas e o ponto de salvamento."""
    etapas = FluxoDaEmpresa(conexao, cliente=cliente, busca=busca)
    grafo = StateGraph(EstadoDoFluxo)
    for nome_da_etapa in DESTINOS:
        grafo.add_node(nome_da_etapa, getattr(etapas, nome_da_etapa))
    grafo.add_edge(START, "perfilar")
    for nome_da_etapa, destinos in DESTINOS.items():
        # "fim" é o END do LangGraph; os outros destinos são as próprias etapas
        caminhos = {}
        for destino in destinos:
            caminhos[destino] = END if destino == "fim" else destino
        grafo.add_conditional_edges(nome_da_etapa, _seguir, caminhos)
    return grafo.compile(checkpointer=abrir_checkpointer(conexao))


def _configuracao(processamento_id: str) -> dict:
    """Cada processamento tem a sua própria linha do tempo no ponto de salvamento (thread_id)."""
    return {"configurable": {"thread_id": processamento_id}}


def _conferir_dono(conexao, processamento_id: str, empresa_id: str) -> None:
    """Só a empresa dona do arquivo mexe no fluxo dele."""
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)


def _motivo_da_rejeicao_na_auditoria(conexao, processamento_id: str) -> str | None:
    """O motivo do encerramento, lido na auditoria (o evento REJEITADO guarda o código do motivo)."""
    motivo = None
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "REJEITADO":
            motivo = evento["detalhe"].get("motivo")
    return motivo


def _situacao_de_envio_encerrado(conexao, processamento_id: str) -> dict | None:
    """A situação de um envio encerrado cujo ponto de salvamento já foi apagado (ADR-71). None se não for o caso.

    Sem o ponto de salvamento, o LangGraph diria "ainda não começou". Mas o envio acabou: a situação é montada a partir
    do próprio envio (situação HOMOLOGADO ou REJEITADO) e da auditoria, para as telas mostrarem "concluído".
    """
    perfil = processamentos.obter(conexao, processamento_id)
    # Envio que não existe ou que ainda não acabou: não é o caso
    if perfil is None or perfil.status not in ESTADOS_FINAIS:
        return None
    estado = {"processamento_id": processamento_id, "empresa_id": perfil.empresa_id, "status": perfil.status.value,
              "motivo_da_rejeicao": _motivo_da_rejeicao_na_auditoria(conexao, processamento_id),
              "ponto_de_salvamento_apagado": True}
    return {"iniciado": True, "terminou": True, "etapa_atual": None, "pergunta": None, "estado": estado}


def situacao(conexao, processamento_id: str) -> dict:
    """Onde o fluxo do arquivo está: a etapa em que parou, a pergunta para a pessoa e o estado guardado."""
    grafo = construir(conexao)
    retrato = grafo.get_state(_configuracao(processamento_id))
    iniciado = bool(retrato.values)
    # Sem ponto de salvamento: pode ser um envio encerrado cujo ponto já foi apagado depois do prazo
    if not iniciado:
        encerrado = _situacao_de_envio_encerrado(conexao, processamento_id)
        if encerrado is not None:
            return encerrado
    etapa_atual, pergunta = None, None
    if retrato.next:
        etapa_atual = retrato.next[0]
    # A pergunta da pausa, se o fluxo estiver parado esperando uma pessoa
    for tarefa in retrato.tasks:
        if tarefa.interrupts:
            pergunta = tarefa.interrupts[0].value
    return {"iniciado": iniciado, "terminou": iniciado and not retrato.next, "etapa_atual": etapa_atual,
            "pergunta": pergunta, "estado": dict(retrato.values)}


def iniciar(conexao, processamento_id: str, empresa_id: str, cliente=None, busca=None) -> dict:
    """Começa o fluxo do arquivo (se ainda não começou) e roda até a primeira pausa. Devolve a situação."""
    _conferir_dono(conexao, processamento_id, empresa_id)
    grafo = construir(conexao, cliente=cliente, busca=busca)
    # Já começou antes (ex.: página recarregada): não começa de novo
    if grafo.get_state(_configuracao(processamento_id)).values:
        return situacao(conexao, processamento_id)
    # Envio encerrado cujo ponto de salvamento foi apagado (ADR-71): nunca recomeça do zero
    if processamentos.obter(conexao, processamento_id).status in ESTADOS_FINAIS:
        return situacao(conexao, processamento_id)
    estado_inicial = {"processamento_id": processamento_id, "empresa_id": empresa_id,
                      "status": EstadoProcessamento.RECEBIDO.value, "configuracao": None, "versao_layout": None,
                      "pendencias": {}, "decisoes_de_coluna": {}, "ciclos_de_correcao": 0, "handoffs": 0,
                      "falhas": 0, "etapa_com_falha": None, "motivo_da_rejeicao": None, "ultimo_erro": None,
                      "proximo_passo": "perfilar"}
    grafo.invoke(estado_inicial, _configuracao(processamento_id))
    return situacao(conexao, processamento_id)


def retomar(conexao, processamento_id: str, empresa_id: str, resposta: dict, cliente=None, busca=None) -> dict:
    """Entrega a decisão da pessoa ao fluxo parado e roda até a próxima pausa (ou o fim). Devolve a situação."""
    _conferir_dono(conexao, processamento_id, empresa_id)
    atual = situacao(conexao, processamento_id)
    # Sem pausa à espera, não há o que retomar (ex.: fluxo já terminado: nada é refeito)
    if atual["pergunta"] is None:
        raise ValueError("O fluxo deste arquivo não está esperando uma decisão.")
    grafo = construir(conexao, cliente=cliente, busca=busca)
    grafo.invoke(Command(resume=resposta), _configuracao(processamento_id))
    return situacao(conexao, processamento_id)


# ---------------- Para a tela: nomes das etapas e o desenho do fluxo ----------------

# Como cada etapa aparece para a empresa
NOMES_DAS_ETAPAS = {
    "perfilar": "Leitura do arquivo",
    "recuperar_conhecimento": "Busca no conhecimento (RAG)",
    "interpretar": "Interpretação das colunas (Agente Interpretador)",
    "aprovar_mapeamento": "Aceite do mapeamento (você)",
    "padronizar": "Padronização",
    "validar": "Validação",
    "aguardar_correcao": "Correção das pendências (você)",
    "aprovar_homologacao": "Envio ao banco (você)",
    "avaliar_no_banco": "Avaliação do banco",
    "aguardar_nova_tentativa": "Falha: tentar de novo? (você)",
    "liberar_planejamento": "Planejamento liberado para o banco",
    "rejeitar": "Arquivo encerrado",
}


def desenho(etapa_atual: str | None = None) -> str:
    """O fluxo no formato DOT (Graphviz), com a etapa atual destacada. A tela mostra com st.graphviz_chart."""
    linhas = ["digraph fluxo {", "  rankdir=LR;", '  node [shape=box, style="rounded,filled", fillcolor="#f2f2f2"];']
    for etapa, nome in NOMES_DAS_ETAPAS.items():
        # A etapa atual fica amarela; as pausas para a pessoa, azuis
        if etapa == etapa_atual:
            cor = "#ffd966"
        elif "(você)" in nome:
            cor = "#dbe9f7"
        else:
            cor = "#f2f2f2"
        linhas.append(f'  {etapa} [label="{nome}", fillcolor="{cor}"];')
    linhas.append('  fim [label="Fim", shape=circle];')
    for etapa, destinos in DESTINOS.items():
        for destino in destinos:
            # As voltas para "tentar de novo" poluem o desenho: ficam de fora
            if destino == "aguardar_nova_tentativa" or etapa == "aguardar_nova_tentativa" or destino == etapa:
                continue
            linhas.append(f"  {etapa} -> {destino};")
    linhas.append("}")
    return "\n".join(linhas)


def comecar_na_correcao(conexao, processamento_id: str, empresa_id: str, estado_de_origem: dict,
                        recado: str) -> dict:
    """Começa o fluxo de um envio de devolução já parado na correção, como um envio que o banco acabou de devolver.

    Para que serve (ADR-121): quando o banco aprova as outras pessoas e devolve só as apontadas, as devolvidas vão para
    um envio novo, que não passa de novo pela leitura, pela IA nem pelo aceite das colunas (isso já foi feito no envio
    de origem). O fluxo dele começa direto na pausa "aguardar_correcao": a empresa responde às pendências do banco e
    manda de novo, pelo mesmo caminho de sempre (validar → envio ao banco → avaliação do banco).
    Recebe: conexao; processamento_id (o envio de devolução) e empresa_id; estado_de_origem (o estado guardado do
    fluxo do envio de origem, de onde vêm a configuração, a versão do layout e as decisões de coluna); recado (o que
    aparece como último recado para a tela). Devolve: a situação do fluxo (parado em "aguardar_correcao").
    """
    grafo = construir(conexao)
    estado = {"processamento_id": processamento_id, "empresa_id": empresa_id,
              "status": EstadoProcessamento.DEVOLVIDO.value,
              "configuracao": estado_de_origem.get("configuracao"),
              "versao_layout": estado_de_origem.get("versao_layout"),
              "pendencias": {}, "decisoes_de_coluna": dict(estado_de_origem.get("decisoes_de_coluna") or {}),
              "ciclos_de_correcao": 0, "handoffs": 0, "falhas": 0, "etapa_com_falha": None,
              "motivo_da_rejeicao": None, "ultimo_erro": recado, "proximo_passo": "aguardar_correcao"}
    # Grava o estado como se a etapa "avaliar_no_banco" tivesse acabado de devolver o envio...
    grafo.update_state(_configuracao(processamento_id), estado, as_node="avaliar_no_banco")
    # ...e roda até a próxima pausa, que é a correção pela empresa
    grafo.invoke(None, _configuracao(processamento_id))
    return situacao(conexao, processamento_id)


def mapeamento_voltou_para_o_aceite(conexao, processamento_id: str) -> bool:
    """True se o mapeamento está PENDENTE (ex.: o Assistente pediu remapeamento depois do aceite)."""
    existente = mapeamentos.obter(conexao, processamento_id)
    return existente is not None and existente[1] == "PENDENTE"


def responder(conexao, processamento_id: str, empresa_id: str, etapa_esperada: str, resposta: dict,
              cliente=None, busca=None) -> dict:
    """Entrega a resposta de um botão da tela à pausa certa do fluxo. Devolve a situação depois.

    Começa o fluxo, se preciso (arquivos tratados antes de o fluxo existir). Se o fluxo está parado mais
    adiante e a tela pede uma etapa anterior (ou vice-versa), leva o fluxo até ela sem pular regra:
    - aceite pedido, mas o fluxo está na correção ou na homologação e o mapeamento voltou para PENDENTE
      (handoff): o fluxo volta ao aceite;
    - homologação pedida, mas o fluxo está na correção: revalida primeiro (é um ciclo de correção).
    Se ainda assim a etapa não for a esperada, nada é entregue: levanta ValueError com o motivo.
    """
    situacao_atual = iniciar(conexao, processamento_id, empresa_id, cliente=cliente, busca=busca)
    etapa_atual = situacao_atual["etapa_atual"]
    parado_depois_do_aceite = etapa_atual in ("aguardar_correcao", "aprovar_homologacao")
    if etapa_esperada == "aprovar_mapeamento" and parado_depois_do_aceite \
            and mapeamento_voltou_para_o_aceite(conexao, processamento_id):
        situacao_atual = retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"}, cliente, busca)
    elif etapa_esperada == "aprovar_homologacao" and etapa_atual == "aguardar_correcao":
        situacao_atual = retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"}, cliente, busca)
    if situacao_atual["etapa_atual"] != etapa_esperada:
        etapa_do_arquivo = NOMES_DAS_ETAPAS.get(situacao_atual["etapa_atual"], "fluxo encerrado")
        raise ValueError(f'O arquivo está na etapa "{etapa_do_arquivo}"; esta ação é da etapa '
                         f'"{NOMES_DAS_ETAPAS[etapa_esperada]}".')
    return retomar(conexao, processamento_id, empresa_id, resposta, cliente, busca)
