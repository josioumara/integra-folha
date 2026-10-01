"""Assistente de Correção: conversa com a empresa sobre UMA pendência e decide como resolvê-la (pendências resolvidas
por conversa, ADR-118).

É um agente: o LLM escolhe a AÇÃO, mas só dentro de uma lista fechada (ADR-20), e a resposta passa por um contrato
(ADR-07). A mensagem da empresa É a decisão dela (ADR-118): quando ela explica o valor certo, a tela aplica na
hora e mostra "Desfazer" (services/assistente_na_tela.py). Este arquivo só DECIDE; quem aplica é o serviço da tela.

A trava que protege o resto do cadastro fica AQUI, no código, e não só no prompt: a conversa é sobre UMA informação
(o campo e a linha da pendência). Se o modelo responder com outro campo, outra linha, ou a releitura de uma coluna que
não é a desse campo, a resposta vira "fora do assunto" e nada muda.

A única ação que o agente executa sozinho é o repasse para o Interpretador (reler a coluna do campo da pendência), que
não muda dado e devolve o mapeamento para o aceite humano (ADR-17), com limite de vezes.

A mensagem da empresa passa pelo Guardrail de injeção antes de chegar ao LLM (ADR-38).

Quando a pessoa responde sem um valor ("não sei", "não tenho", "prefiro não informar"), o agente escolhe a ação
"sem_valor" (ADR-153): nada muda, ele ajuda a achar o dado e pergunta de novo. Quem conta essas respostas e encerra a
conversa no limite é o serviço da tela, no código, e não o modelo.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from agents import tom_de_voz
from services import (auditoria, execucoes, guardrail_injecao, mapeamentos, parametros, processamentos,
                      teto_de_gasto, uso_da_ia)
from services.llm_client import LLMClient
# A resposta da IA, guardada na ação preparada enquanto o detector confere a mensagem (ADR-147)
from services.llm_client import RespostaLLM
# A IA real que não respondeu (ADR-145): a conversa pausa, sem resposta simulada no lugar
from services.llm_client import IAIndisponivel

# Pasta raiz do projeto (para achar o prompt)
RAIZ = Path(__file__).resolve().parent.parent
# Versão do prompt (arquivo prompts/assistente_correcao_v4.md, ADR-153) e nome da tarefa no cliente de LLM
VERSAO_PROMPT = "assistente_correcao_v4"
TAREFA = "assistente_correcao"

# As ações que mudam dado (o serviço da tela aplica na hora, com "Desfazer")
ACOES_QUE_MUDAM_DADO = ("corrigir", "nao_cadastrar", "confirmar_alerta", "preencher_para_todos", "escolher_formato")
# A resposta sem um valor: a pessoa disse que não sabe, não tem ou não quer informar (ADR-153). Nada muda; o serviço da
# tela conta estas respostas e, no limite, encerra a conversa com educação
ACAO_SEM_VALOR = "sem_valor"
# Frases (sem acento, minúsculas) de quem responde sem um valor: não sabe, não tem ou não quer informar (ADR-153)
PALAVRAS_DE_SEM_VALOR = ("nao sei", "nao tenho", "nao temos", "nao lembro", "nao lembramos", "nao sabemos", "sei la",
                         "desconheco", "nao faco ideia", "nao faco a menor ideia", "prefiro nao informar",
                         "nao quero informar", "nao vou informar", "nao posso informar", "nao consigo informar",
                         "nao encontrei", "nao achei")
# As regras de dúvida de formato de uma coluna inteira (datas dia/mês ou mês/dia; dígitos da matrícula)
REGRAS_DE_FORMATO = ("DATA_AMBIGUA", "ZEROS_A_ESQUERDA")
# A regra do campo obrigatório vazio numa pessoa (o valor pode servir para todos os que estão sem ele)
REGRA_OBRIGATORIO_VAZIO = "OBRIGATORIO_VAZIO"
# A regra da coluna obrigatória que o arquivo inteiro não trouxe (a única em que a empresa pode indicar outra coluna)
REGRA_OBRIGATORIO_SEM_COLUNA = "OBRIGATORIO_SEM_COLUNA"
# A regra do valor que o sistema não conseguiu entender (ex.: fora da lista de opções, data que não existe): não se
# confirma; informa-se o valor certo ou a informação fica em branco
REGRA_VALOR_FORA_DA_LISTA = "VALOR_NAO_CONVERTIDO"
# O que o agente diz quando a mensagem é sobre outra informação (o serviço da tela troca pelo nome do campo e da pessoa)
MENSAGEM_FORA_DO_ASSUNTO = "Aqui eu só ajusto a informação desta pendência. Para outro dado, use a pendência dele."
# Os dois caminhos quando a coluna que o arquivo inteiro não trouxe não serve para todos (ADR-124): os botões do cartão
FALA_DOS_DOIS_CAMINHOS = ('Use "Informar pessoa a pessoa" para dizer o valor de cada funcionário, ou "Descartar a '
                          'leitura e enviar outro arquivo" para mandar o arquivo de novo com essa coluna.')


class AcaoAssistente(BaseModel):
    """O contrato da resposta do LLM: uma ação da lista fechada e os argumentos dela."""

    acao: Literal["responder", "explicar_regra", "corrigir", "nao_cadastrar", "confirmar_alerta",
                  "preencher_para_todos", "escolher_formato", "solicitar_remapeamento", "usar_coluna",
                  "fora_do_assunto", "sem_valor"]
    mensagem: str                     # o que o assistente diz para a empresa
    linha: int | None = None          # a linha do arquivo em discussão (tem de ser a da pendência)
    campo: str | None = None          # o campo em discussão (tem de ser o da pendência)
    valor: str | None = None          # o valor novo (corrigir, preencher_para_todos) ou o formato (escolher_formato)
    coluna: str | None = None         # a coluna a reler (solicitar_remapeamento) ou onde está o dado (usar_coluna)
    justificativa: str | None = None  # o motivo, com as palavras da empresa


@dataclass
class RespostaAssistente:
    """O que o agente decidiu numa rodada da conversa (o serviço da tela aplica o que mudar dado)."""

    mensagem: str
    acao: str
    valor: str | None = None          # o valor novo ou o formato escolhido
    coluna: str | None = None         # a coluna relida (solicitar_remapeamento) ou a indicada (usar_coluna)
    justificativa: str | None = None  # o motivo, com as palavras da empresa
    remapeado: bool = False           # o repasse ao Interpretador foi feito
    recusado: bool = False            # a mensagem era sobre outra informação (ou tinha uma ordem para a IA)
    fontes: list[str] | None = None   # as fontes do RAG que apoiaram a resposta
    modelo: str = "mock"


def _sistema() -> str:
    """A parte SISTEMA do arquivo do prompt, com a diretriz de tom de voz do agente (agents/tom_de_voz.py)."""
    texto = (RAIZ / "prompts" / f"{VERSAO_PROMPT}.md").read_text(encoding="utf-8")
    return tom_de_voz.com_a_diretriz(re.split(r"^## SISTEMA\s*$", texto, flags=re.M)[1].strip())


def rotulos_dos_campos(conexao) -> dict[str, str]:
    """O nome curto de cada campo do layout, como a empresa entende. Ex.: {"cpf": "CPF", "valor_renda": "Valor renda"}.

    Vai para o pedido para a IA saber quais dados NÃO são da pendência (e recusar a conversa sobre eles).
    """
    # Importado aqui: services/acompanhamento importa o fluxo, que importa este agente
    from services.acompanhamento import rotulo_do_campo
    _, campos = parametros.layout_ativo(conexao)
    rotulos = {}
    for campo_do_layout in campos:
        rotulos[campo_do_layout.campo] = rotulo_do_campo(campo_do_layout.campo)
    return rotulos


def montar_pedido(pendencia, colunas_do_campo: list[str], colunas_do_arquivo: list[str], mensagem: str,
                  busca=None, outros_campos: dict[str, str] | None = None, informacao_da_pendencia: str = "",
                  mapeamento_atual: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Contexto da conversa: a pendência (com o valor real, ADR-101), os outros campos do cadastro (fora do assunto),
    as fontes do RAG e a mensagem como DADO.

    Recebe: pendencia (dict ou None); as colunas ligadas ao campo e todas as colunas do arquivo; a mensagem; a busca
    do RAG; outros_campos — {campo: rótulo} dos campos que NÃO são desta pendência; informacao_da_pendencia — o nome
    da informação da pendência (ex.: "CPF"); mapeamento_atual — {coluna do arquivo: campo} (com ele, a IA acha a
    coluna quando a empresa diz "a matrícula é o CPF", ADR-124).
    Devolve: (o texto do pedido, as fontes usadas).
    """
    trechos = []
    if pendencia is not None:
        if busca is None:
            from rag.busca import search_rules as busca
        # Importado aqui, como a busca: o Assistente só depende do RAG quando há uma pendência
        from rag.busca import IndiceAusente
        try:
            trechos = busca(pendencia["mensagem"], k=2)
        except IndiceAusente:
            # Sem o índice do layout (ex.: servidor novo, antes do build_index), segue sem trechos de apoio
            trechos = []
    # Cada trecho com a fonte entre colchetes e sem a primeira linha (o título)
    linhas_de_conhecimento = []
    fontes = []
    for trecho in trechos:
        texto_sem_titulo = trecho["texto"].split("\n", 1)[-1]
        linhas_de_conhecimento.append(f"[{trecho['fonte']}] {texto_sem_titulo}")
        fontes.append(trecho["fonte"])
    conhecimento = "\n".join(linhas_de_conhecimento) or "(nenhum)"
    pedido = (f"Pendência:\n{json.dumps(pendencia, ensure_ascii=False)}\n\n"
              f"Informação desta pendência: {informacao_da_pendencia}\n"
              f"Coluna(s) do arquivo ligadas a este campo: {json.dumps(colunas_do_campo, ensure_ascii=False)}\n"
              f"Colunas do arquivo: {json.dumps(colunas_do_arquivo, ensure_ascii=False)}\n"
              "Mapeamento atual (coluna do arquivo → campo): "
              f"{json.dumps(mapeamento_atual or {}, ensure_ascii=False)}\n"
              "Outros campos do cadastro (fora desta pendência): "
              f"{json.dumps(outros_campos or {}, ensure_ascii=False)}\n\n"
              f"Conhecimento de apoio:\n{conhecimento}\n\n"
              f"<mensagem_da_empresa>\n{mensagem}\n</mensagem_da_empresa>")
    return pedido, fontes


def _trecho_json(texto: str) -> str:
    """Do primeiro "{" ao último "}" da resposta (tira texto e cercas de código em volta)."""
    inicio = texto.find("{")
    fim = texto.rfind("}")
    return texto[inicio:fim + 1]


def conversar(conexao, processamento_id: str, empresa_id: str, pendencia: dict | None, mensagem: str,
              cliente: LLMClient | None = None, busca=None, usuario: str = "empresa") -> RespostaAssistente:
    """Uma rodada da conversa, com a execução gravada para a Telemetria.

    Recebe: o envio e a empresa; pendencia — o achado da validação em discussão (dict, ou None); a mensagem da empresa;
            cliente e busca (o LLM e o RAG; os testes trocam por versões falsas); usuario — quem escreveu.
    Devolve: a RespostaAssistente (o que o agente decidiu; nada de dado muda aqui, fora o repasse ao Interpretador).
    """
    inicio = datetime.now(timezone.utc)
    # O taxímetro da rodada: as chamadas à IA feitas para responder somam aqui (tokens e custo; ADR-131)
    with uso_da_ia.medir() as uso:
        try:
            resposta = _responder(conexao, processamento_id, empresa_id, pendencia, mensagem, cliente, busca, usuario)
        except teto_de_gasto.TetoDeGastoAtingido:
            # A IA foi pausada pelo teto de gasto (ADR-131): o banco vê o ERRO na Telemetria, e a API avisa a empresa
            execucoes.registrar_pausa_pelo_teto(conexao, processamento_id, empresa_id, "conversa:pausada",
                                                "Assistente de Correção", inicio, uso)
            raise
        except IAIndisponivel:
            # A IA real não respondeu (ADR-145): nenhuma resposta simulada; o banco vê o ERRO na Telemetria, e a API
            # avisa a empresa, que tenta de novo depois (nada mudou no dado)
            execucoes.registrar_queda_da_ia(conexao, processamento_id, empresa_id, "conversa:pausada",
                                            "Assistente de Correção", inicio, uso)
            raise
    # O status da execução: barrado pelo guardrail, fora do contrato ou normal
    if resposta.acao == "recusado":
        status, tipo_erro = execucoes.BLOQUEADO, None
    elif resposta.acao == "falha":
        status, tipo_erro = execucoes.ERRO, "RespostaForaDoContrato"
    else:
        status, tipo_erro = execucoes.OK, None
    # Só a ação escolhida vai para o painel: nada da mensagem da empresa
    execucoes.registrar(conexao, processamento_id, empresa_id, f"conversa:{resposta.acao}", "Assistente de Correção",
                        inicio, datetime.now(timezone.utc), status, modelo=resposta.modelo,
                        versao_prompt=VERSAO_PROMPT, tipo_erro=tipo_erro,
                        guardrail_disparado=resposta.acao == "recusado", uso=uso)
    return resposta


def _colunas_do_campo(conexao, processamento_id: str, pendencia: dict | None) -> list[str]:
    """As colunas do arquivo ligadas ao campo da pendência (vazio sem pendência ou sem campo)."""
    colunas = []
    mapeamento = mapeamentos.obter(conexao, processamento_id)
    if mapeamento and pendencia and pendencia.get("campo"):
        for item in mapeamento[0].itens:
            if item.campo == pendencia["campo"]:
                colunas.append(item.coluna)
    return colunas


def _mapeamento_atual(conexao, processamento_id: str) -> dict[str, str]:
    """{coluna do arquivo: campo} das colunas que alimentam algum campo hoje (as de fora não entram).

    Ex.: {"Nome": "nome_completo", "Registro": "matricula"}.
    """
    mapeamento_atual = {}
    mapeamento = mapeamentos.obter(conexao, processamento_id)
    if mapeamento:
        for item in mapeamento[0].itens:
            if item.campo:
                mapeamento_atual[item.coluna] = item.campo
    return mapeamento_atual


def _outros_campos(conexao, pendencia: dict | None) -> dict[str, str]:
    """{campo: rótulo} de todos os campos do layout, menos o da pendência."""
    outros = {}
    campo_da_pendencia = (pendencia or {}).get("campo")
    for campo, rotulo in rotulos_dos_campos(conexao).items():
        if campo != campo_da_pendencia:
            outros[campo] = rotulo
    return outros


def _responder(conexao, processamento_id: str, empresa_id: str, pendencia: dict | None, mensagem: str,
               cliente: LLMClient | None, busca, usuario: str) -> RespostaAssistente:
    """A rodada da conversa em si (sem gravar a execução: quem grava é conversar).

    O guardrail de injeção tem duas camadas aqui (ADR-147):
    1. a lista de frases, antes de tudo: a mensagem suspeita nem chega à IA;
    2. com a IA real, o detector do Bedrock Guardrails, que roda AO MESMO TEMPO que a preparação da resposta, para a
       checagem não somar o tempo dela à espera da empresa. A resposta preparada só é usada depois do "normal"; no
       "suspeito", ela é descartada e vale a mesma recusa. A preparação só lê e pergunta à IA: nada muda no cadastro
       antes do resultado da checagem.
    """
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise KeyError(processamento_id)
    # Guardrail, 1ª camada: mensagem com cara de instrução para a IA nem chega ao LLM
    if guardrail_injecao.e_suspeito(mensagem):
        return _recusar_mensagem_suspeita(conexao, processamento_id, empresa_id, mensagem)
    # Guardrail, 2ª camada (só com a IA real): o detector começa a checar enquanto a resposta é preparada
    checagem = guardrail_injecao.comecar_checagem(mensagem)
    try:
        preparada = _preparar_a_acao(conexao, processamento_id, perfil, pendencia, mensagem, cliente, busca)
    finally:
        # Espera a checagem (no máximo o tempo dela) e grava na Telemetria, mesmo que a preparação tenha falhado
        mensagem_suspeita = guardrail_injecao.terminar_checagem(checagem, conexao, processamento_id, empresa_id)
    # O detector achou a mensagem suspeita: a resposta preparada é descartada, e vale a mesma recusa
    if mensagem_suspeita:
        return _recusar_mensagem_suspeita(conexao, processamento_id, empresa_id, mensagem)
    if preparada.acao is None:
        return RespostaAssistente("Não consegui entender agora. Pode descrever de outro jeito?", "falha")
    resultado = _decidir(conexao, processamento_id, empresa_id, pendencia or {}, preparada.acao,
                         preparada.colunas_do_campo, preparada.fontes)
    # A trava da resposta sem valor (ADR-153), no código: se o modelo só perguntou de novo a quem disse que não sabe,
    # a rodada conta como resposta sem valor (o serviço da tela conta essas respostas e encerra no limite)
    if resultado.acao == "responder" and e_resposta_sem_valor(mensagem):
        resultado.acao = ACAO_SEM_VALOR
    resultado.modelo = preparada.resposta.modelo if preparada.resposta.modo == "llm" else "mock"
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "ASSISTENTE",
                        {"acao": resultado.acao, "modelo": resultado.modelo, "versao_prompt": VERSAO_PROMPT})
    return resultado


def _recusar_mensagem_suspeita(conexao, processamento_id: str, empresa_id: str, mensagem: str) -> RespostaAssistente:
    """A recusa da mensagem com cara de ordem para a IA, com o evento na auditoria (só a contagem, nunca o texto).

    Vale para as duas camadas do guardrail: a lista de frases e o detector do Bedrock Guardrails.
    """
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "INJECAO_NO_CHAT",
                        {"padroes": len(guardrail_injecao.padroes_encontrados(mensagem))})
    return RespostaAssistente("Não posso seguir instruções que mudem as regras ou aprovem pendências. "
                              "Posso ajudar a entender e corrigir a pendência.", "recusado", recusado=True)


@dataclass
class AcaoPreparada:
    """A resposta preparada enquanto o detector checa a mensagem: nada disso muda o cadastro ainda.

    acao é None quando a IA não respondeu no formato combinado nas duas tentativas.
    """

    acao: AcaoAssistente | None      # a ação que a IA escolheu (ou None)
    colunas_do_campo: list[str]      # as colunas do arquivo ligadas ao campo da pendência
    fontes: list[str]                # as fontes do RAG que foram no pedido
    resposta: RespostaLLM            # a última resposta da IA (para saber o modelo que respondeu)


def _preparar_a_acao(conexao, processamento_id: str, perfil, pendencia: dict | None, mensagem: str,
                     cliente: LLMClient | None, busca) -> AcaoPreparada:
    """A parte da rodada que roda junto com a checagem do detector: lê o contexto e pergunta à IA, sem gravar nada.

    Recebe: o envio e o perfil do arquivo, a pendência, a mensagem da empresa, o cliente de IA e a busca do RAG.
    Devolve: a AcaoPreparada. Quem decide e muda o cadastro é _decidir, só depois do resultado da checagem.
    """
    # O contexto: as colunas ligadas ao campo, todas as colunas e os outros campos do cadastro
    colunas_do_campo = _colunas_do_campo(conexao, processamento_id, pendencia)
    colunas_do_arquivo = []
    for coluna in perfil.colunas:
        colunas_do_arquivo.append(coluna.nome)
    # O nome da informação da pendência (ex.: "CPF"): o mesmo que a empresa lê no cartão
    campo_da_pendencia = (pendencia or {}).get("campo")
    informacao_da_pendencia = rotulos_dos_campos(conexao).get(campo_da_pendencia, "") if campo_da_pendencia else ""
    pedido, fontes = montar_pedido(pendencia, colunas_do_campo, colunas_do_arquivo, mensagem, busca,
                                   _outros_campos(conexao, pendencia), informacao_da_pendencia,
                                   _mapeamento_atual(conexao, processamento_id))
    cliente = cliente or LLMClient(respostas_mock={TAREFA: simular_llm})
    # Até duas tentativas; na segunda, o LLM recebe o motivo da recusa
    acao = None
    for tentativa in (1, 2):
        resposta = cliente.gerar(TAREFA, pedido, _sistema(), temperatura=0.0)
        try:
            acao = AcaoAssistente.model_validate_json(_trecho_json(resposta.texto))
            break
        except ValueError as erro:
            # O erro de validação do Pydantic também é um ValueError
            pedido += f"\n\nSua resposta anterior foi rejeitada ({str(erro).splitlines()[0]}). Responda só o JSON."
    # Uma pergunta nunca confirma nem muda um dado (ADR-127): o modelo recebe a regra e responde de novo
    if acao is not None and e_pergunta(mensagem) and _acao_muda_dado_ou_volta_as_colunas(acao):
        acao = _responder_a_pergunta(cliente, pedido, acao)
    return AcaoPreparada(acao=acao, colunas_do_campo=colunas_do_campo, fontes=fontes, resposta=resposta)


# ---------------- Uma pergunta nunca muda dado (ADR-127) ----------------

# O que o modelo recebe quando escolheu mudar um dado numa mensagem que é uma pergunta
NOTA_DA_PERGUNTA = ('\n\nA mensagem da empresa é uma PERGUNTA (tem "?"). Uma pergunta nunca confirma nem muda um dado: '
                    'explique o que ela perguntou, em poucas palavras, e pergunte de novo o que ela quer fazer. Use a '
                    'ação "responder" e não mude nada.')
# O que o agente diz se o modelo insistir em mudar o dado (nada muda)
FALA_DA_PERGUNTA = ("Entendi que é uma pergunta, então não mudei nada. Quando você decidir, me diga o que fazer: o valor "
                    "certo, ou que a informação está certa assim.")


def e_pergunta(mensagem: str) -> bool:
    """True se a mensagem da empresa tem uma pergunta (um "?" em qualquer lugar).

    Ex.: "o que é empresa do grupo? esse CNPJ é o da matriz" → True; "o CPF certo é 529.982.247-25" → False.
    Por que o "?" e não o sentido da frase: é uma regra que a pessoa entende e que nunca falha para o lado de mudar o
    dado; na dúvida, o cartão pergunta de novo.
    """
    return "?" in mensagem


def _tem_algum_digito(texto: str) -> bool:
    """True se o texto tem algum algarismo. Ex.: "C900" → True; "não sei" → False."""
    for caractere in texto:
        if caractere.isdigit():
            return True
    return False


def e_resposta_sem_valor(mensagem: str) -> bool:
    """True se a mensagem da empresa diz que ela não sabe, não tem ou não quer informar o valor, sem trazer um valor
    nem uma pergunta (ADR-153).

    Ex.: "não sei" → True; "Prefiro não informar." → True; "não sei, acho que é 4110-10" → False (tem um valor);
    "não sei o que é CBO?" → False (é uma pergunta).
    """
    # Importado aqui, como nas outras funções que normalizam o texto
    from baselines.baseline_mapper import normalizar
    if e_pergunta(mensagem) or _tem_algum_digito(mensagem):
        return False
    return _contem_alguma(normalizar(mensagem), PALAVRAS_DE_SEM_VALOR)


def _acao_muda_dado_ou_volta_as_colunas(acao: AcaoAssistente) -> bool:
    """True se a ação muda um dado na hora, ou devolve o envio à leitura das colunas.

    "Não cadastrar", "deixar em branco" (corrigir sem valor) e "usar outra coluna" ficam de fora: eles só propõem, e a
    pessoa confirma num botão antes de qualquer mudança.
    """
    if acao.acao == "corrigir":
        return bool((acao.valor or "").strip())
    return acao.acao in ("confirmar_alerta", "preencher_para_todos", "escolher_formato", "solicitar_remapeamento")


def _responder_a_pergunta(cliente: LLMClient, pedido: str, acao_de_antes: AcaoAssistente) -> AcaoAssistente:
    """Pede ao modelo, uma vez, que responda à pergunta sem mudar nada. Devolve a nova ação (sempre uma que não muda
    dado): a do modelo, se ele obedecer; senão, a fala fixa FALA_DA_PERGUNTA.
    """
    resposta = cliente.gerar(TAREFA, pedido + NOTA_DA_PERGUNTA, _sistema(), temperatura=0.0)
    # try/except: resposta fora do contrato vale como "não obedeceu"
    try:
        nova_acao = AcaoAssistente.model_validate_json(_trecho_json(resposta.texto))
    except ValueError:
        nova_acao = None
    if nova_acao is not None and not _acao_muda_dado_ou_volta_as_colunas(nova_acao):
        return nova_acao
    return AcaoAssistente(acao="responder", mensagem=FALA_DA_PERGUNTA, linha=acao_de_antes.linha,
                          campo=acao_de_antes.campo)


def _fora_da_pendencia(pendencia: dict, acao: AcaoAssistente, colunas_do_campo: list[str]) -> bool:
    """A TRAVA: True se o modelo quer mexer em outra informação que não a da pendência.

    Outro campo, outra linha, ou a releitura de uma coluna que não é a do campo da pendência. Ex.: pendência do CPF da
    linha 8 e o modelo responde "corrigir valor_renda na linha 9" → True (nada muda).
    """
    # Outro campo (o modelo pode repetir o campo da pendência ou deixar vazio)
    if acao.campo not in (None, "", pendencia.get("campo")):
        return True
    # Outra linha
    if acao.linha is not None and acao.linha != pendencia.get("linha"):
        return True
    # Releitura de uma coluna que não é a do campo da pendência
    if acao.acao == "solicitar_remapeamento" and acao.coluna not in colunas_do_campo:
        return True
    # Indicar outra coluna para o campo só vale na informação que o arquivo inteiro não trouxe (ADR-124): nos outros
    # cartões, o campo já tem a sua coluna
    if acao.acao == "usar_coluna" and pendencia.get("regra_id") != REGRA_OBRIGATORIO_SEM_COLUNA:
        return True
    return False


def _nao_serve_para_a_pendencia(pendencia: dict, acao: str) -> str | None:
    """Uma ação da lista que não combina com esta pendência: a explicação para a empresa, ou None se combina.

    Ex.: "confirmar_alerta" num CPF inválido → "Só alertas podem ser confirmados; este dado precisa ser corrigido."
    """
    regra = pendencia.get("regra_id")
    # Corrigir precisa de um campo numa pessoa (e não serve para a dúvida de formato da coluna inteira)
    if acao == "corrigir" and (not pendencia.get("campo") or regra in REGRAS_DE_FORMATO):
        return "Esta pendência não é de um valor de uma pessoa. Me diga o que você sabe sobre ela."
    # Não cadastrar precisa de uma pessoa
    if acao == "nao_cadastrar" and pendencia.get("linha") is None:
        return "Esta pendência é do arquivo inteiro, não de uma pessoa."
    # Só alerta se confirma; erro se corrige
    if acao == "confirmar_alerta" and pendencia.get("severidade") != "ALERTA":
        return "Só alertas podem ser confirmados; este dado precisa ser corrigido. Qual é o valor certo?"
    # Um valor que não está entre as opções não se confirma (ADR-118): a confirmação é
    # guardada por regra e linha, e fecharia junto outro valor fora da lista da mesma pessoa, em outro campo
    if acao == "confirmar_alerta" and regra == REGRA_VALOR_FORA_DA_LISTA:
        return ("O sistema não conseguiu entender esse valor, então ele não pode ser confirmado como está "
                "(se preferir, a informação pode ficar em branco). Qual é o valor certo?")
    # Preencher para todos: um campo que o arquivo não traz, ou o obrigatório vazio. Nunca numa dúvida de formato: ela
    # tem o campo da coluna, mas o que se decide ali é a ordem das datas ou os dígitos, não um valor
    if acao == "preencher_para_todos" and regra in REGRAS_DE_FORMATO:
        return "Esta pendência é sobre o formato da coluna inteira. Me diga o formato, e eu ajusto a coluna."
    # Nunca numa informação única por funcionário (a marcação "Pode ser igual para todos" do parâmetro: o CPF e as
    # informações do titular são de cada funcionário)
    if acao == "preencher_para_todos" and pendencia.get("igual_para_todos") is False:
        return "Essa informação é única por funcionário e não pode ser a mesma para todos. " + FALA_DOS_DOIS_CAMINHOS
    para_todos_permitido = pendencia.get("linha") is None or regra == REGRA_OBRIGATORIO_VAZIO
    if acao == "preencher_para_todos" and (not pendencia.get("campo") or not para_todos_permitido):
        return "Aqui o valor vale só para esta pessoa. Qual é o valor certo dela?"
    # O formato só se escolhe nas dúvidas de formato da coluna
    if acao == "escolher_formato" and regra not in REGRAS_DE_FORMATO:
        return "Esta pendência não é sobre o formato de uma coluna."
    return None


def _decidir(conexao, processamento_id, empresa_id, pendencia: dict, acao: AcaoAssistente, colunas_do_campo, fontes):
    """Confere a ação escolhida contra a trava e a pendência e devolve a decisão (sem mudar dado, fora o repasse)."""
    # A trava: outra informação que não a da pendência → fora do assunto, nada muda
    if acao.acao == "fora_do_assunto" or _fora_da_pendencia(pendencia, acao, colunas_do_campo):
        return RespostaAssistente(MENSAGEM_FORA_DO_ASSUNTO, "fora_do_assunto", recusado=True, fontes=fontes)
    nome_da_acao = acao.acao
    # Corrigir num campo que o arquivo inteiro não traz é o mesmo que preencher para todos (mas não numa dúvida de
    # formato, que também é do arquivo inteiro e tem o campo da coluna: ali, corrigir não serve)
    sem_linha_com_campo = pendencia.get("linha") is None and pendencia.get("campo")
    if nome_da_acao == "corrigir" and sem_linha_com_campo and pendencia.get("regra_id") not in REGRAS_DE_FORMATO:
        nome_da_acao = "preencher_para_todos"
    # A ação não combina com esta pendência: explica, sem mudar nada
    explicacao = _nao_serve_para_a_pendencia(pendencia, nome_da_acao)
    if explicacao:
        return RespostaAssistente(explicacao, "responder", fontes=fontes)
    # Mudar um dado sem o valor (corrigir vazio é "deixar em branco": vale; os outros precisam do valor)
    if nome_da_acao in ("preencher_para_todos", "escolher_formato") and not (acao.valor or "").strip():
        return RespostaAssistente("Qual é o valor? Me diga e eu ajusto.", "responder", fontes=fontes)
    # O repasse ao Interpretador: a única ação executada aqui (não muda dado e volta para o aceite)
    if nome_da_acao == "solicitar_remapeamento":
        try:
            mapeamentos.solicitar_remapeamento(conexao, processamento_id, empresa_id, acao.coluna,
                                               acao.justificativa or acao.mensagem)
        except (ValueError, KeyError) as erro:
            # A regra de negócio recusou (limite de releituras, dica com ordem): a conversa segue, sem mudar nada
            return RespostaAssistente(f"Não deu para pedir a releitura: {erro}", "responder", fontes=fontes)
        return RespostaAssistente(acao.mensagem, nome_da_acao, coluna=acao.coluna, remapeado=True, fontes=fontes)
    # O dado que o arquivo inteiro não trouxe está em outra coluna (ADR-124): o serviço da tela confere os valores e
    # pede a confirmação da empresa antes de trocar (nada muda aqui)
    if nome_da_acao == "usar_coluna":
        if not (acao.coluna or "").strip():
            return RespostaAssistente("Em qual coluna do arquivo está essa informação?", "responder", fontes=fontes)
        return RespostaAssistente(acao.mensagem, nome_da_acao, coluna=acao.coluna.strip(),
                                  justificativa=acao.justificativa, fontes=fontes)
    # A resposta sem valor ("não sei"): nada muda, nem com um valor que o modelo tenha posto por engano (ADR-153)
    if nome_da_acao == ACAO_SEM_VALOR:
        return RespostaAssistente(acao.mensagem, nome_da_acao, fontes=fontes)
    # As outras: a decisão vai para o serviço da tela (que aplica as que mudam dado)
    return RespostaAssistente(acao.mensagem, nome_da_acao, valor=acao.valor, justificativa=acao.justificativa,
                              fontes=fontes)


# ---------------- MOCK: um "LLM" simulado que lê o pedido de verdade ----------------

# Frases (sem acento, minúsculas) que pedem para tirar a pessoa do envio
PALAVRAS_DE_NAO_CADASTRAR = ("nao cadastrar", "repetid", "duplicad", "excluir", "remover", "tirar esta linha")
# Frases que confirmam um alerta ("Está certo assim", "Sim, é do nosso grupo")
PALAVRAS_DE_CONFIRMACAO = ("correto", "certo assim", "esta certo", "confirmo", "nosso grupo")
# Frases que pedem para deixar o campo vazio
PALAVRAS_DE_EM_BRANCO = ("em branco", "deixar vazio", "deixa vazio")
# Frases de quem diz que a informação que o arquivo inteiro não trouxe não é a mesma para todos (ADR-124; antes, o
# agente simulado entendia "para todos" e perguntava de novo "Qual é o valor para todos?")
PALAVRAS_DE_NAO_E_A_MESMA = ("nao e a mesma", "nao e o mesmo", "nao e igual", "nao sao iguais", "nao sao os mesmos",
                             "nao sao as mesmas", "cada um tem", "cada uma tem", "muda de pessoa", "varia",
                             "diferente")
# O maior texto que conta como "só o valor" na resposta sobre uma coluna que o arquivo inteiro não trouxe (ex.: "SP")
TAMANHO_DA_RESPOSTA_CURTA = 60
# Palavras comuns que apontam para um campo pelo jeito de falar (o rótulo nem sempre é dito assim)
SINONIMOS_DOS_CAMPOS = {"salario": "valor_renda", "renda": "valor_renda", "nascimento": "data_nascimento",
                        "admissao": "data_admissao", "admitid": "data_admissao", "endereco": "logradouro_residencial",
                        "celular": "telefone_celular", "e-mail": "email_pessoal"}


def _montar_resposta(acao: str, mensagem: str, pendencia: dict, **argumentos) -> str:
    """A resposta simulada no contrato: a ação, a mensagem e os argumentos (os não informados ficam vazios)."""
    resposta = {"acao": acao, "mensagem": mensagem, "linha": pendencia.get("linha"), "campo": pendencia.get("campo"),
                "valor": None, "coluna": None, "justificativa": None}
    resposta.update(argumentos)
    return json.dumps(resposta, ensure_ascii=False)


def _contem_alguma(texto: str, palavras: tuple[str, ...]) -> bool:
    """True se alguma das palavras aparece no texto."""
    for palavra in palavras:
        if palavra in texto:
            return True
    return False


def _coluna_citada(colunas: list[str], texto: str) -> str | None:
    """A coluna que a mensagem cita como "coluna <nome>", se houver."""
    from baselines.baseline_mapper import normalizar
    for coluna in colunas:
        if re.search(rf"\bcoluna {re.escape(normalizar(coluna))}\b", texto):
            return coluna
    return None


def _campo_citado(texto: str, outros_campos: dict[str, str]) -> str | None:
    """O outro campo do cadastro que a mensagem cita (pelo rótulo, como palavra inteira, ou por um sinônimo comum),
    ou None. outros_campos já não tem o campo da pendência.

    Ex.: pendência do CPF e a mensagem "o cargo é Analista" → "cargo"; "o CPF certo é 529..." → None.
    """
    from baselines.baseline_mapper import normalizar
    # Pelo rótulo do campo, como palavra inteira (ex.: "cargo", "valor renda")
    for campo, rotulo in outros_campos.items():
        if re.search(rf"\b{re.escape(normalizar(rotulo))}\b", texto):
            return campo
    # Por um sinônimo (ex.: "salário" é o valor da renda)
    for palavra, campo in SINONIMOS_DOS_CAMPOS.items():
        if palavra in texto and campo in outros_campos:
            return campo
    return None


def _cita_a_informacao(texto: str, informacao: str, campo: str) -> bool:
    """True se a mensagem cita a informação da pendência, pelo nome ou pelo nome técnico. Ex.: "... é o CPF" → True."""
    from baselines.baseline_mapper import normalizar
    for nome in (informacao, campo.replace("_", " ")):
        if nome and re.search(rf"\b{re.escape(normalizar(nome))}\b", texto):
            return True
    return False


def _coluna_do_campo(mapeamento_atual: dict[str, str], campo: str) -> str | None:
    """A coluna do arquivo que alimenta o campo hoje, ou None. Ex.: ({"Registro": "matricula"}, "matricula") →
    "Registro"."""
    for coluna, campo_da_coluna in mapeamento_atual.items():
        if campo_da_coluna == campo:
            return coluna
    return None


def _linha_do_pedido(pedido: str, comeco: str) -> str:
    """O resto da linha do pedido que começa com o texto (vazio se o pedido não tem essa linha)."""
    for linha in pedido.splitlines():
        if linha.startswith(comeco):
            return linha[len(comeco):]
    return ""


def _palpite_aceito(mensagem: str) -> str | None:
    """O valor da resposta rápida que aceita o palpite do agente, ou None.

    Ex.: 'Sim, use "Solteiro"' → "Solteiro"; "sim, use Casado" → "Casado"; "sim" → None. No cartão do grupo (ADR-120),
    a frase termina com "para as N": 'Sim, use "Divorciado" para as 23' → "Divorciado".
    """
    encontrado = re.fullmatch(r"\s*sim,?\s+use\s+[\"“']?(.+?)[\"”']?(?:\s+para\s+(?:as|os|todas|todos)(?:\s+\d+)?)?\s*",
                              mensagem, flags=re.IGNORECASE)
    if encontrado:
        return encontrado.group(1).strip()
    return None


def _valor_da_lista(texto: str, campo: str) -> str | None:
    """O valor da lista fechada do campo que a mensagem é, inteira (sem acento e sem maiúsculas), ou None.

    Ex.: ("solteiro", "estado_civil") → "Solteiro"; ("uniao estavel", "estado_civil") → "União estável";
    ("o certo é solteiro", "estado_civil") → None (aí quem entende é a regra do "é").
    """
    from baselines.baseline_mapper import normalizar
    from services import normalizador
    regra = normalizador.carregar_dominios().get(campo)
    if regra is None:
        return None
    for aceito in regra["valores"]:
        if normalizar(aceito) == texto:
            return aceito
    return None


# Como a mensagem (já normalizada: sem acento, minúscula, pontuação virando espaço) diz a ordem das datas. Ex.: "As
# datas estão em dia/mês (DD/MM/AAAA)" vira "as datas estao em dia mes dd mm aaaa". Por isso os jeitos vêm sem a
# barra: procurar "dia/mes" nunca acharia nada (a normalização troca a barra por espaço), a resposta rápida não seria
# entendida e o agente perguntaria de novo
JEITOS_DE_DIZER_DIA_E_MES = ("dia mes", "dd mm")
JEITOS_DE_DIZER_MES_E_DIA = ("mes dia", "mm dd")


def _primeira_posicao(texto: str, jeitos: tuple[str, ...]) -> int | None:
    """A posição em que um dos jeitos aparece primeiro no texto, ou None se nenhum aparece."""
    posicoes = []
    for jeito in jeitos:
        posicao = texto.find(jeito)
        if posicao >= 0:
            posicoes.append(posicao)
    if not posicoes:
        return None
    return min(posicoes)


def _formato_da_mensagem(texto: str, regra: str) -> str | None:
    """O formato que a mensagem escolhe: "DMY", "MDY" ou "zeros:N". Ex.: "a matrícula tem 5 dígitos" → "zeros:5".

    texto é a mensagem normalizada (ver JEITOS_DE_DIZER_DIA_E_MES). Se a mensagem citar as duas ordens (ex.: "é dia/mês,
    não mês/dia"), vale a que aparece primeiro.
    """
    if regra == "DATA_AMBIGUA":
        dia_e_mes = _primeira_posicao(texto, JEITOS_DE_DIZER_DIA_E_MES)
        mes_e_dia = _primeira_posicao(texto, JEITOS_DE_DIZER_MES_E_DIA)
        if dia_e_mes is None and mes_e_dia is None:
            return None
        if mes_e_dia is None or (dia_e_mes is not None and dia_e_mes < mes_e_dia):
            return "DMY"
        return "MDY"
    # Matrícula: o número de dígitos
    digitos = re.search(r"(\d{1,2})\s*digito", texto)
    if digitos:
        return "zeros:" + digitos.group(1)
    return None


def _valor_depois_dos_dois_pontos(mensagem: str) -> str | None:
    """O que vem depois do último ":" (as sugestões "O valor para todos é: X"). Vazio → None."""
    if ":" not in mensagem:
        return None
    valor = mensagem.rsplit(":", 1)[1].strip()
    return valor or None


def simular_llm(pedido: str) -> str:
    """Escolhe a ação por palavras da mensagem, como o prompt pede. Só para demo e testes (MOCK)."""
    from baselines.baseline_mapper import normalizar
    # Lê as partes do pedido
    pendencia = json.loads(re.search(r"Pendência:\n(.*?)\n\n", pedido, re.S).group(1)) or {}
    colunas_do_campo = json.loads(re.search(r"Coluna\(s\) do arquivo ligadas a este campo: (.*)\n", pedido).group(1))
    colunas = json.loads(re.search(r"Colunas do arquivo: (.*)\n", pedido).group(1))
    outros_campos = json.loads(re.search(r"Outros campos do cadastro \(fora desta pendência\): (.*)\n", pedido).group(1))
    mensagem = re.search(r"<mensagem_da_empresa>\n(.*?)\n</mensagem_da_empresa>", pedido, re.S).group(1)
    primeira_fonte = re.search(r"^\[([^\]]+)\]", pedido, re.M)
    informacao = _linha_do_pedido(pedido, "Informação desta pendência: ") or (pendencia.get("campo") or "")
    mapeamento_atual = json.loads(_linha_do_pedido(pedido, "Mapeamento atual (coluna do arquivo → campo): ") or "{}")
    texto = normalizar(mensagem)
    regra = pendencia.get("regra_id") or ""
    campo = pendencia.get("campo") or ""
    # Na informação que o arquivo inteiro não trouxe, a empresa pode dizer em que coluna ela está (ADR-124)
    na_coluna_que_falta = regra == REGRA_OBRIGATORIO_SEM_COLUNA

    # 1. "a coluna X é ...": a coluna foi mal entendida -> repasse ao Interpretador (a trava confere se é a do campo);
    #    na informação que o arquivo inteiro não trouxe, a coluna citada é onde ela está (o serviço confere e confirma)
    coluna = _coluna_citada(colunas, texto)
    if coluna:
        if na_coluna_que_falta:
            return _montar_resposta("usar_coluna", f'Vou conferir a coluna "{coluna}" como {informacao}.', pendencia,
                                    coluna=coluna, justificativa=mensagem)
        if coluna not in colunas_do_campo:
            return _montar_resposta("fora_do_assunto", "Essa coluna não é a desta pendência.", pendencia)
        return _montar_resposta("solicitar_remapeamento", f"Entendi: vou pedir ao Interpretador para rever a coluna "
                                f"{coluna}. O mapeamento volta para o seu aceite.", pendencia,
                                coluna=coluna, justificativa=mensagem)
    # 2. Dúvida de formato da coluna inteira: a escolha do formato
    if regra in REGRAS_DE_FORMATO:
        formato = _formato_da_mensagem(texto, regra)
        if formato:
            return _montar_resposta("escolher_formato", "Vou usar esse formato na coluna inteira.", pendencia,
                                    valor=formato, justificativa=mensagem)
        return _montar_resposta("responder", "Me diga o formato: dia/mês ou mês/dia (ou quantos dígitos tem a "
                                "matrícula).", pendencia)
    # 3. A pessoa aceitou o palpite do agente (a resposta rápida 'Sim, use "Solteiro"'): corrige com ele
    palpite_aceito = _palpite_aceito(mensagem)
    if palpite_aceito:
        return _montar_resposta("corrigir", f"Vou usar {palpite_aceito}.", pendencia, valor=palpite_aceito,
                                justificativa=f"Palpite do agente aceito pela empresa: {palpite_aceito}")
    # 4. A resposta é exatamente um valor da lista do campo (a resposta rápida "Solteiro"): corrige com ele
    valor_da_lista = _valor_da_lista(texto, campo)
    if valor_da_lista:
        return _montar_resposta("corrigir", f"Vou usar {valor_da_lista}.", pendencia, valor=valor_da_lista,
                                justificativa=f"Informado pela empresa: {mensagem}")
    # 4.1 Na informação que o arquivo inteiro não trouxe: "a matrícula é o CPF" (o dado está na coluna de outro campo)
    outro_campo = _campo_citado(texto, outros_campos)
    if na_coluna_que_falta and outro_campo and _cita_a_informacao(texto, informacao, campo):
        coluna_do_outro = _coluna_do_campo(mapeamento_atual, outro_campo)
        if coluna_do_outro:
            return _montar_resposta("usar_coluna", f'Vou conferir a coluna "{coluna_do_outro}" como {informacao}.',
                                    pendencia, coluna=coluna_do_outro, justificativa=mensagem)
        return _montar_resposta("responder", f'A informação "{outros_campos[outro_campo]}" não veio em nenhuma coluna '
                                f'do arquivo. Em qual coluna está a informação "{informacao}"?', pendencia)
    # 5. Fala de outra informação do cadastro: fora do assunto
    if outro_campo:
        return _montar_resposta("fora_do_assunto", "Aqui eu só ajusto a informação desta pendência.", pendencia)
    # 6. Pedido para tirar a pessoa do envio
    if _contem_alguma(texto, PALAVRAS_DE_NAO_CADASTRAR):
        return _montar_resposta("nao_cadastrar", "Vou tirar esta pessoa do envio.", pendencia, justificativa=mensagem)
    # 7. Deixar o campo em branco
    if _contem_alguma(texto, PALAVRAS_DE_EM_BRANCO):
        return _montar_resposta("corrigir", "Vou deixar este campo em branco.", pendencia, valor="",
                                justificativa=mensagem)
    # 7.1 Uma coluna que o arquivo inteiro não trouxe, e o valor não é o mesmo para todos: os dois caminhos (ADR-124)
    if pendencia.get("linha") is None and campo and _contem_alguma(texto, PALAVRAS_DE_NAO_E_A_MESMA):
        return _montar_resposta("responder", "Sem problema: então esse valor não vale para todos. "
                                + FALA_DOS_DOIS_CAMINHOS, pendencia)
    # 8. O mesmo valor para todos os que estão sem o dado
    if "para todos" in texto:
        valor = _valor_depois_dos_dois_pontos(mensagem)
        if valor:
            return _montar_resposta("preencher_para_todos", f"Vou usar {valor} para todos que estão sem este dado.",
                                    pendencia, valor=valor, justificativa=mensagem)
        return _montar_resposta("responder", "Qual é o valor para todos?", pendencia)
    # 8.1 Uma coluna que o arquivo inteiro não trouxe: a resposta curta, sem pergunta, é o valor para todos (ex.: "SP";
    #     muita gente responde só com o valor, sem dizer "para todos")
    resposta_curta = "?" not in mensagem and len(mensagem.strip()) <= TAMANHO_DA_RESPOSTA_CURTA
    if pendencia.get("linha") is None and campo and resposta_curta:
        return _montar_resposta("preencher_para_todos", f"Vou usar {mensagem.strip()} para todos que estão sem este "
                                "dado.", pendencia, valor=mensagem.strip(), justificativa=mensagem)
    # 8.2 A pessoa não sabe, não tem ou não quer informar o valor, sem pergunta e sem número na frase: nada muda, e o
    #     agente ajuda a achar o dado (ADR-153; com um número, a frase traz um valor, e vale a regra 9)
    if e_resposta_sem_valor(mensagem):
        return _montar_resposta(ACAO_SEM_VALOR, _fala_sem_valor_simulada(pendencia), pendencia)
    # 9. A empresa escreveu o valor certo
    valor = _valor_da_mensagem(mensagem, campo)
    if valor:
        return _montar_resposta("corrigir", f"Vou trocar para {valor}.", pendencia, valor=valor,
                                justificativa=f"Informado pela empresa: {mensagem}")
    # 9.1 A resposta curta de uma pessoa, sem pergunta e com algum número, é o próprio valor (ex.: só o código
    #     "4110-10"); antes, o agente simulado só entendia o valor escrito depois de um "é"
    if campo and pendencia.get("linha") is not None and resposta_curta and _tem_algum_digito(mensagem):
        return _montar_resposta("corrigir", f"Vou usar {mensagem.strip()}.", pendencia, valor=mensagem.strip(),
                                justificativa=f"Informado pela empresa: {mensagem}")
    # 10. A empresa confirma um alerta
    if pendencia.get("severidade") == "ALERTA" and _contem_alguma(texto, PALAVRAS_DE_CONFIRMACAO):
        return _montar_resposta("confirmar_alerta", "Vou registrar que está certo.", pendencia, justificativa=mensagem)
    # 11. Uma pergunta: explica a regra, citando a fonte
    if "?" in mensagem or texto.startswith(("por que", "porque", "o que")):
        citacao = f" Fonte: {primeira_fonte.group(1)}." if primeira_fonte else ""
        return _montar_resposta("explicar_regra", f"{pendencia.get('mensagem', '')} Isso vem das regras do "
                                f"banco para o cadastro.{citacao}", pendencia)
    # 12. Nada disso: pede o que falta (o serviço da tela põe na frente a informação e o que veio no arquivo; só um
    #     alerta pode ser confirmado)
    if pendencia.get("severidade") == "ALERTA":
        return _montar_resposta("responder", "Esse valor está certo, ou qual é o valor certo?", pendencia)
    return _montar_resposta("responder", "Qual é o valor certo?", pendencia)


def _fala_sem_valor_simulada(pendencia: dict) -> str:
    """A fala simulada para quem respondeu sem um valor: na primeira vez, onde o dado costuma estar; na seguinte, que a
    conversa pode ser encerrada com a pendência aberta (o prompt pede o mesmo à IA real: não repetir a fala).

    O serviço da tela põe na frente a informação e o que veio no arquivo, e encerra a conversa no limite.
    """
    if not pendencia.get("respostas_sem_valor_antes"):
        return ("Sem problema. Essa informação costuma estar na ficha de registro do funcionário ou com a contabilidade "
                "da empresa. Consegue conferir e me dizer o valor certo?")
    return ("Tudo bem. Se não tiver esse dado agora, eu encerro a conversa por aqui, e a pendência continua aberta. "
            "Consegue confirmar o valor com o funcionário?")


def _valor_da_mensagem(mensagem: str, campo: str) -> str | None:
    """O valor que a empresa escreveu: dinheiro, data, documento ou o texto depois de "é"."""
    # O jeito de achar o valor depende do campo
    padroes = {"valor_renda": r"R?\$?\s?\d[\d.]*,\d{2}|\d+(?:\.\d{1,2})?(?=\s|$|\.)",
               "cpf": r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", "cnpj_empregador": r"[\d./-]{14,18}",
               "data": r"\d{1,2}/\d{1,2}/\d{4}"}
    chave = "data" if campo.startswith("data_") else campo
    if chave in padroes:
        achado = re.search(padroes[chave], mensagem)
        if achado:
            return achado.group(0).strip()
        return None
    # Outros campos: o texto depois de "é", "era", "seria"... (ex.: "a unidade é Centro")
    depois_do_e = re.search(r"\b(?:é|e|era|seria|correto é|certo é)\s+[\"“']?([^\"”'.]+)", mensagem)
    if depois_do_e and campo:
        return depois_do_e.group(1).strip()
    return None
