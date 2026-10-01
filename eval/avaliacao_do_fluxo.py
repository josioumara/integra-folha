"""Avaliação do fluxo da empresa de ponta a ponta, em modo MOCK (Fase 14, ADR-59).

Passa os 9 arquivos de envio pelo fluxo inteiro (o mesmo do Portal): leitura, interpretação, aceite,
padronização, validação, correção e homologação. As decisões da empresa são tomadas por uma "pessoa
simulada", que decide sempre pelo gabarito (golden), como faria um RH que conhece os próprios dados.

O que é medido, por arquivo e no total:
- conclusão: quantos arquivos chegaram a HOMOLOGADO;
- erros injetados achados: dos erros que o gerador colocou de propósito, quantos o fluxo achou na linha certa;
- intervenções humanas: aceite, decisões de coluna, valores corrigidos, linhas excluídas, alertas
  justificados, pedidos de revalidação e homologação;
- métricas proxy de negócio: arquivo homologado sem edição manual de valor e tempo de máquina até a homologação;
- retomada: toda decisão é entregue a um fluxo reaberto do ponto de salvamento, e nenhuma etapa é refeita;
- erros por etapa: execuções com erro ou bloqueio, e um cenário de falha (provedor fora do ar).

Limites honestos: a IA está em MOCK, então a interpretação e o tempo NÃO são os de um modelo real, e o
tempo da pessoa não entra (só no uso real). O que esta avaliação prova é o FLUXO: as regras, as pausas, a
retomada e o controle humano. As chamadas ao banco usam a conexão recebida (nunca o banco local).
"""
import csv
import json
import sqlite3
import time
from datetime import date
from pathlib import Path

from agents import interpretador
from services import auditoria, correcoes, execucoes, mapeamentos, processamentos, validador
from services.llm_client import LLMClient
from workflows import fluxo_empresa

# Pasta raiz do projeto e onde ficam os arquivos, os gabaritos e a verdade de cada funcionário
RAIZ = Path(__file__).resolve().parent.parent
PASTA_DOS_ENVIOS = RAIZ / "data" / "synthetic" / "envios"
PASTA_DOS_GABARITOS = RAIZ / "data" / "golden"
CAMINHO_DA_VERDADE = RAIZ / "data" / "synthetic" / "funcionarios_truth.csv"

# O nome do erro no gabarito -> a regra do Validador que deve achá-lo
REGRA_DO_GABARITO = {"CPF_INVALIDO": "CPF_INVALIDO", "CAMPO_OBRIGATORIO_VAZIO": "OBRIGATORIO_VAZIO",
                     "RENDA_FORA_DO_CARGO": "RENDA_FORA_DO_CARGO", "MATRICULA_DUPLICADA": "MATRICULA_DUPLICADA",
                     "VALOR_COMO_TEXTO": "VALOR_NAO_CONVERTIDO", "PESSOA_DUPLICADA_NO_ARQUIVO": "PESSOA_DUPLICADA",
                     "JA_HOMOLOGADO_NA_EMPRESA": "JA_HOMOLOGADO_NA_EMPRESA"}
# Pendências que são da COLUNA inteira (a empresa decide o formato), e não de uma linha
PENDENCIAS_DE_COLUNA = ("DATA_AMBIGUA", "ZEROS_A_ESQUERDA")
# Quantas decisões a pessoa simulada pode tomar num arquivo antes de a avaliação desistir (evita laço)
LIMITE_DE_DECISOES = 40
# Quem aparece como autor das decisões simuladas na auditoria
USUARIO_SIMULADO = "avaliacao.simulada"
# A data de referência das cargas (a mesma dos testes)
DATA_DE_REFERENCIA = date(2026, 9, 1)


def carregar_gabaritos() -> dict:
    """O gabarito de cada arquivo, pelo nome sem extensão. Ex.: {"aurora_carga_inicial": {...}, ...}"""
    gabaritos = {}
    for caminho in sorted(PASTA_DOS_GABARITOS.glob("*.json")):
        gabaritos[caminho.stem] = json.loads(caminho.read_text(encoding="utf-8"))
    return gabaritos


def carregar_verdade() -> dict:
    """Os dados corretos de cada funcionário: funcionario_id -> campos (é o que o RH "sabe")."""
    funcionarios = {}
    with open(CAMINHO_DA_VERDADE, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            funcionarios[linha["funcionario_id"]] = linha
    return funcionarios


def ordem_de_processamento(gabaritos: dict) -> list[str]:
    """As cargas iniciais primeiro, depois as inclusões: uma inclusão só existe depois da carga da empresa."""
    iniciais = []
    inclusoes = []
    for nome, gabarito in gabaritos.items():
        if gabarito["tipo_carga"] == "INCLUSAO":
            inclusoes.append(nome)
        else:
            iniciais.append(nome)
    return iniciais + inclusoes


def escolhas_do_aceite(gabarito: dict) -> dict:
    """As escolhas da pessoa no aceite: cada coluna no campo certo; a ambígua, no campo confirmado; a extra, ignorada."""
    escolhas = {}
    for coluna, campo in gabarito["mapeamento"].items():
        # Coluna ambígua: o gabarito diz para qual campo ela vai depois da confirmação
        if campo is None:
            campo = gabarito["colunas_ambiguas"][coluna]["campo_apos_confirmacao"]
        escolhas[coluna] = campo
    # Colunas que não interessam ao layout são ignoradas
    for coluna in gabarito["colunas_extras"]:
        escolhas[coluna] = mapeamentos.IGNORAR
    return escolhas


def _nova_contagem_de_intervencoes() -> dict:
    """Os contadores de decisões humanas de um arquivo, todos começando em zero."""
    return {"aceite": 0, "decisoes_de_coluna": 0, "valores_corrigidos": 0, "linhas_excluidas": 0,
            "alertas_justificados": 0, "revalidacoes": 0, "homologacao": 0, "avaliacao_do_banco": 0}


def _decisoes_de_coluna(conexao, processamento_id: str, gabarito: dict, verdade: dict) -> dict:
    """Para cada coluna com formato em aberto, a decisão da pessoa. Ex.: {"Matrícula": "zeros:5"}."""
    decisoes = {}
    for pendencia in correcoes.dados_atuais(conexao, processamento_id).pendencias_de_coluna:
        if pendencia["tipo"] == "ZEROS_A_ESQUERDA":
            # O RH sabe quantos dígitos tem a matrícula: o tamanho da matrícula de um funcionário real
            primeiro_funcionario = verdade[gabarito["funcionario_ids"][0]]
            decisoes[pendencia["coluna"]] = f"zeros:{len(primeiro_funcionario['matricula'])}"
        elif pendencia["tipo"] == "DATA_AMBIGUA":
            # Empresa brasileira escreve dia/mês/ano
            decisoes[pendencia["coluna"]] = "DMY"
    return decisoes


def _primeira_pendencia_de_linha(relatorio) -> validador.Achado | None:
    """A primeira pendência que impede a homologação (BLOQUEANTE, ou ALERTA ainda sem justificativa)."""
    for achado in relatorio.achados:
        # Pendência de coluna é resolvida por decisão de formato, não linha a linha
        if achado.regra_id in PENDENCIAS_DE_COLUNA:
            continue
        if achado.severidade == validador.BLOQUEANTE:
            return achado
        if achado.severidade == validador.ALERTA and not achado.resolvido:
            return achado
    return None


def _resolver_pendencia(conexao, processamento_id: str, empresa_id: str, achado, gabarito: dict,
                        verdade: dict, intervencoes: dict) -> None:
    """Resolve UMA pendência como o RH faria: exclui a linha repetida, justifica o alerta ou corrige o valor.

    Toda ação passa pelos mesmos serviços do Portal (pedido + clique de aprovação) e já revalida.
    """
    if achado.regra_id == "PESSOA_DUPLICADA":
        # A mesma pessoa duas vezes: a linha repetida sai do arquivo
        pedido = correcoes.propor(conexao, processamento_id, empresa_id, achado.linha, correcoes.EXCLUIR, None,
                                  "Linha repetida", USUARIO_SIMULADO)
        correcoes.decidir(conexao, processamento_id, empresa_id, pedido.correcao_id, True, USUARIO_SIMULADO)
        intervencoes["linhas_excluidas"] += 1
    elif achado.severidade == validador.ALERTA:
        # Alerta não é erro: a pessoa confere e confirma, com justificativa
        validador.justificar_alerta(conexao, processamento_id, empresa_id, achado.regra_id, achado.linha,
                                    "CONFIRMADO", "Conferido no cadastro do RH", USUARIO_SIMULADO)
        intervencoes["alertas_justificados"] += 1
    else:
        # Erro: a pessoa informa o valor certo, que ela conhece (a verdade do funcionário)
        funcionario_id = gabarito["funcionario_ids"][achado.registro - 1]
        valor_certo = verdade[funcionario_id][achado.campo]
        pedido = correcoes.propor(conexao, processamento_id, empresa_id, achado.linha, achado.campo, valor_certo,
                                  "Valor conferido no cadastro do RH", USUARIO_SIMULADO)
        correcoes.decidir(conexao, processamento_id, empresa_id, pedido.correcao_id, True, USUARIO_SIMULADO)
        intervencoes["valores_corrigidos"] += 1


def _achados_de_linha(relatorio) -> set:
    """Os achados do relatório como pares (registro, regra), sem as pendências de coluna."""
    pares = set()
    for achado in relatorio.achados:
        if achado.regra_id not in PENDENCIAS_DE_COLUNA:
            pares.add((achado.registro, achado.regra_id))
    return pares


def _erros_esperados(gabarito: dict) -> set:
    """Os erros injetados no arquivo como pares (registro, regra do Validador)."""
    pares = set()
    for erro in gabarito["erros"]:
        pares.add((erro["linha"], REGRA_DO_GABARITO[erro["tipo"]]))
    return pares


def _tem_pendencia_de_coluna(relatorio) -> bool:
    """True se ainda falta a empresa decidir o formato de alguma coluna."""
    for achado in relatorio.achados:
        if achado.regra_id in PENDENCIAS_DE_COLUNA:
            return True
    return False


def processar_arquivo(conexao, nome: str, gabarito: dict, verdade: dict, busca=None) -> dict:
    """Passa um arquivo pelo fluxo inteiro, com a pessoa simulada decidindo. Devolve as medidas do arquivo.

    busca: a busca do RAG (None = a busca real, se o índice existir; os testes passam uma busca falsa).
    """
    conteudo = (PASTA_DOS_ENVIOS / gabarito["arquivo"]).read_bytes()
    empresa_id = gabarito["empresa_id"]
    # Começa a contar o tempo de máquina no recebimento
    inicio = time.perf_counter()
    recebido = processamentos.receber_arquivo(conexao, conteudo, gabarito["arquivo"], empresa_id,
                                              DATA_DE_REFERENCIA, USUARIO_SIMULADO)
    processamento_id = recebido.perfil.processamento_id
    situacao = fluxo_empresa.iniciar(conexao, processamento_id, empresa_id, busca=busca)

    intervencoes = _nova_contagem_de_intervencoes()
    retomadas = 0
    achados_iniciais = None
    # Cada volta entrega UMA decisão ao fluxo parado; o fluxo é reaberto do ponto de salvamento a cada vez
    for _decisao in range(LIMITE_DE_DECISOES):
        etapa = situacao["etapa_atual"]
        # Fluxo terminado (homologado ou encerrado): acabou
        if etapa is None:
            break
        if etapa == "aprovar_mapeamento":
            resposta = {"acao": "aprovar", "escolhas": escolhas_do_aceite(gabarito), "usuario": USUARIO_SIMULADO}
            intervencoes["aceite"] += 1
        elif etapa == "aguardar_correcao":
            relatorio = validador.obter(conexao, processamento_id)
            if _tem_pendencia_de_coluna(relatorio):
                # Primeiro o formato das colunas: sem ele, os valores da coluna ainda não estão certos
                resposta = {"acao": "decidir_colunas",
                            "decisoes": _decisoes_de_coluna(conexao, processamento_id, gabarito, verdade)}
                intervencoes["decisoes_de_coluna"] += len(resposta["decisoes"])
            else:
                # A primeira foto sem pendência de coluna é a que se compara com o gabarito
                if achados_iniciais is None:
                    achados_iniciais = _achados_de_linha(relatorio)
                # Resolve as pendências uma a uma (cada ação já revalida) e pede para seguir
                pendencia = _primeira_pendencia_de_linha(relatorio)
                while pendencia is not None:
                    _resolver_pendencia(conexao, processamento_id, empresa_id, pendencia, gabarito, verdade,
                                        intervencoes)
                    pendencia = _primeira_pendencia_de_linha(validador.obter(conexao, processamento_id))
                resposta = {"acao": "revalidar"}
                intervencoes["revalidacoes"] += 1
        elif etapa == "aprovar_homologacao":
            # Arquivo que chegou limpo à homologação: a foto dos achados é tirada aqui
            if achados_iniciais is None:
                achados_iniciais = _achados_de_linha(validador.obter(conexao, processamento_id))
            resposta = {"acao": "homologar", "usuario": USUARIO_SIMULADO}
            intervencoes["homologacao"] += 1
        elif etapa == "avaliar_no_banco":
            # O especialista do banco (simulado) aprova o envio: a etapa de avaliação do ADR-69, passo 15
            resposta = {"acao": "aprovar", "usuario": USUARIO_SIMULADO}
            intervencoes["avaliacao_do_banco"] += 1
        else:
            # Etapa inesperada (ex.: falha): a pessoa desiste, e o arquivo não conta como concluído
            resposta = {"acao": "rejeitar"}
        situacao = fluxo_empresa.retomar(conexao, processamento_id, empresa_id, resposta, busca=busca)
        retomadas += 1
    segundos = time.perf_counter() - inicio
    return _medidas_do_arquivo(conexao, nome, gabarito, processamento_id, situacao, intervencoes, retomadas,
                               achados_iniciais or set(), segundos)


def _medidas_do_arquivo(conexao, nome: str, gabarito: dict, processamento_id: str, situacao: dict,
                        intervencoes: dict, retomadas: int, achados_iniciais: set, segundos: float) -> dict:
    """Junta as medidas de um arquivo processado."""
    esperados = _erros_esperados(gabarito)
    # Execuções gravadas: etapas feitas, erros por etapa e quantas vezes o Interpretador rodou
    etapas_executadas = 0
    interpretacoes = 0
    erros_por_etapa = {}
    for execucao in execucoes.listar(conexao, processamento_id):
        etapas_executadas += 1
        if execucao["etapa"] == "interpretar":
            interpretacoes += 1
        if execucao["status"] != "OK":
            erros_por_etapa[execucao["etapa"]] = erros_por_etapa.get(execucao["etapa"], 0) + 1
    # O que a auditoria registrou no aceite (colunas mudadas pela empresa) e na proposta (colunas reaproveitadas)
    colunas_alteradas_no_aceite = 0
    colunas_reusadas = 0
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "MAPEAMENTO_APROVADO":
            colunas_alteradas_no_aceite = evento["detalhe"]["alteradas_pela_empresa"]
        elif evento["tipo"] == "MAPEAMENTO_PROPOSTO":
            colunas_reusadas = evento["detalhe"]["colunas_reusadas"]
    # Somatório das intervenções humanas
    total_de_intervencoes = 0
    for quantidade in intervencoes.values():
        total_de_intervencoes += quantidade
    # Achados que não estavam no gabarito (para revisar: podem ser erro do fluxo ou do gabarito)
    fora_do_gabarito = []
    for registro, regra in sorted(achados_iniciais - esperados, key=str):
        fora_do_gabarito.append({"registro": registro, "regra": regra})
    status_final = situacao["estado"]["status"]
    return {
        "arquivo": nome,
        "empresa_id": gabarito["empresa_id"],
        "tipo_carga": gabarito["tipo_carga"],
        "status_final": status_final,
        "concluiu": status_final == "HOMOLOGADO",
        "erros_injetados": len(esperados),
        "erros_achados": len(esperados & achados_iniciais),
        "achados_fora_do_gabarito": fora_do_gabarito,
        "colunas_reusadas": colunas_reusadas,
        "colunas_alteradas_no_aceite": colunas_alteradas_no_aceite,
        "intervencoes": intervencoes,
        "total_de_intervencoes": total_de_intervencoes,
        # Proxy de negócio: homologado sem a empresa editar nenhum valor nem excluir linha
        "sem_edicao_manual": intervencoes["valores_corrigidos"] == 0 and intervencoes["linhas_excluidas"] == 0,
        "ciclos_de_correcao": situacao["estado"]["ciclos_de_correcao"],
        "handoffs": situacao["estado"]["handoffs"],
        "retomadas": retomadas,
        "etapas_executadas": etapas_executadas,
        # Retomada sem refazer: o Interpretador roda uma vez por arquivo (mais uma por handoff)
        "etapas_refeitas": interpretacoes - 1 - situacao["estado"]["handoffs"],
        "erros_por_etapa": erros_por_etapa,
        "segundos_de_maquina": round(segundos, 3),
    }


def cenario_de_falha(conexao, gabarito: dict, busca=None) -> dict:
    """O provedor de IA fora do ar na interpretação: o arquivo tem de PARAR, nunca virar falso sucesso."""
    def falhar(pedido):
        """Toda chamada à IA quebra, como um provedor fora do ar."""
        raise RuntimeError("provedor fora do ar")

    cliente_que_falha = LLMClient(modo="mock", respostas_mock={interpretador.TAREFA: falhar})
    conteudo = (PASTA_DOS_ENVIOS / gabarito["arquivo"]).read_bytes()
    recebido = processamentos.receber_arquivo(conexao, conteudo, gabarito["arquivo"], gabarito["empresa_id"],
                                              DATA_DE_REFERENCIA, USUARIO_SIMULADO)
    processamento_id = recebido.perfil.processamento_id
    situacao = fluxo_empresa.iniciar(conexao, processamento_id, gabarito["empresa_id"], cliente=cliente_que_falha,
                                     busca=busca)
    # Onde parou e com que situação
    etapas_com_erro = []
    for execucao in execucoes.listar(conexao, processamento_id):
        if execucao["status"] != "OK":
            etapas_com_erro.append(execucao["etapa"])
    return {"arquivo": gabarito["arquivo"], "parou_em": situacao["etapa_atual"],
            "etapa_com_falha": situacao["estado"]["etapa_com_falha"], "etapas_com_erro": etapas_com_erro,
            "status": situacao["estado"]["status"],
            "virou_sucesso": situacao["estado"]["status"] == "HOMOLOGADO"}


def _dividir(parte: float, total: float) -> float:
    """parte / total, ou 0 quando o total é zero (evita a divisão por zero)."""
    if total == 0:
        return 0.0
    return parte / total


def resumir(arquivos: list[dict]) -> dict:
    """Os números do conjunto: conclusão, erros achados, proxies de negócio, retomada e erros por etapa."""
    concluidos = 0
    erros_injetados = 0
    erros_achados = 0
    fora_do_gabarito = 0
    sem_edicao = 0
    intervencoes = 0
    ciclos = 0
    retomadas = 0
    etapas_refeitas = 0
    segundos_dos_concluidos = 0.0
    erros_por_etapa = {}
    for arquivo in arquivos:
        erros_injetados += arquivo["erros_injetados"]
        erros_achados += arquivo["erros_achados"]
        fora_do_gabarito += len(arquivo["achados_fora_do_gabarito"])
        intervencoes += arquivo["total_de_intervencoes"]
        ciclos += arquivo["ciclos_de_correcao"]
        retomadas += arquivo["retomadas"]
        etapas_refeitas += arquivo["etapas_refeitas"]
        # Os proxies de tempo e de edição só valem para quem chegou ao fim
        if arquivo["concluiu"]:
            concluidos += 1
            segundos_dos_concluidos += arquivo["segundos_de_maquina"]
            if arquivo["sem_edicao_manual"]:
                sem_edicao += 1
        for etapa, quantidade in arquivo["erros_por_etapa"].items():
            erros_por_etapa[etapa] = erros_por_etapa.get(etapa, 0) + quantidade
    quantidade_de_arquivos = len(arquivos)
    return {
        "arquivos": quantidade_de_arquivos,
        "concluidos": concluidos,
        "taxa_de_conclusao": round(_dividir(concluidos, quantidade_de_arquivos), 3),
        "erros_injetados": erros_injetados,
        "erros_achados": erros_achados,
        "recall_dos_erros_injetados": round(_dividir(erros_achados, erros_injetados), 3),
        "achados_fora_do_gabarito": fora_do_gabarito,
        "homologados_sem_edicao_manual": sem_edicao,
        "taxa_sem_edicao_manual": round(_dividir(sem_edicao, concluidos), 3),
        "intervencoes_por_arquivo": round(_dividir(intervencoes, quantidade_de_arquivos), 2),
        "ciclos_de_correcao_por_arquivo": round(_dividir(ciclos, quantidade_de_arquivos), 2),
        "segundos_de_maquina_ate_homologar": round(_dividir(segundos_dos_concluidos, concluidos), 3),
        "retomadas": retomadas,
        "etapas_refeitas_na_retomada": etapas_refeitas,
        "erros_por_etapa": erros_por_etapa,
    }


def avaliar(conexao, busca=None) -> dict:
    """Roda os 9 arquivos (cargas iniciais antes das inclusões) e o cenário de falha. Devolve tudo medido."""
    gabaritos = carregar_gabaritos()
    verdade = carregar_verdade()
    arquivos = []
    for nome in ordem_de_processamento(gabaritos):
        arquivos.append(processar_arquivo(conexao, nome, gabaritos[nome], verdade, busca=busca))
    # A falha roda num banco à parte, só na memória: no banco principal, o mesmo arquivo seria um reenvio
    # idêntico (e voltaria o processamento já homologado)
    conexao_da_falha = sqlite3.connect(":memory:", check_same_thread=False)
    falha = cenario_de_falha(conexao_da_falha, gabaritos["aurora_carga_inicial"], busca=busca)
    conexao_da_falha.close()
    return {"modo": "MOCK", "resumo": resumir(arquivos), "cenario_de_falha": falha, "arquivos": arquivos}
