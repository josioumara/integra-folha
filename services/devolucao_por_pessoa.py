"""O envio de devolução: as pessoas que o banco devolveu à empresa ao aprovar as outras do mesmo envio (ADR-121).

Para que serve: o especialista do banco confere um envio de 35 pessoas e acha problema em 2. Em vez de devolver o
envio inteiro (as 33 certas esperariam as 2 erradas), ele clica "Aprovar 33 e devolver 2":
    1. as 33 são cadastradas na hora, no envio de origem (services/homologacao.py, sem as linhas devolvidas);
    2. as 2 vão para um ENVIO DE DEVOLUÇÃO novo (este arquivo), com a situação "Devolvido pelo banco" e uma pendência
       "Pedido do banco" em cada pessoa;
    3. a empresa responde às pendências e manda o envio de devolução ao banco, pelo caminho de sempre.

Por que um envio novo, e não o mesmo envio "meio aprovado": em todo o sistema, o envio é a unidade de cadastro. As
telas contam "Cadastrado", "Em análise" e "Pendente" pelo envio, e o arquivo final do banco é um por envio. Com um envio
novo, nada disso muda: o de origem está cadastrado, o de devolução está com a empresa. A ligação entre os dois fica
no retrato do envio de devolução (envio_de_origem), e a linha do tempo e as "Idas e voltas com o banco" mostram os dois
juntos (services/acompanhamento.py).

O envio de devolução não passa de novo pela leitura, pela IA nem pelo aceite das colunas: ele recebe os dados atuais
das pessoas devolvidas (já com as correções que a empresa fez no envio de origem), o mapeamento aprovado e as
respostas que a empresa já tinha dado aos alertas dessas pessoas.
"""
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from models.contratos import EstadoProcessamento
from services import (apontamentos_do_banco, auditoria, correcoes, mapeamentos, normalizador, processamentos,
                      validador)
from services.normalizador import Normalizacao


def _agora() -> str:
    """Data e hora atuais (UTC), em texto. Exemplo: "2026-09-28T14:05:00+00:00"."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def texto_de_pessoas(quantidade: int) -> str:
    """ "1 pessoa" ou "2 pessoas": o número com a palavra no singular ou no plural."""
    if quantidade == 1:
        return "1 pessoa"
    return str(quantidade) + " pessoas"


def recado_da_devolucao(quantidade: int) -> str:
    """O recado que a empresa lê no envio de devolução (o motivo da devolução, no alto do cartão do envio).

    Exemplo: 2 → "O banco aprovou as outras pessoas do envio e devolveu 2 pessoas para ajuste: veja o pedido do banco
    em cada uma."
    """
    if quantidade == 1:
        return ("O banco aprovou as outras pessoas do envio e devolveu 1 pessoa para ajuste: veja o pedido do banco "
                "nela.")
    return ("O banco aprovou as outras pessoas do envio e devolveu " + texto_de_pessoas(quantidade) +
            " para ajuste: veja o pedido do banco em cada uma.")


def _gravar_envio(conexao, perfil_de_origem, novo_id: str, quantidade: int) -> None:
    """Grava o envio de devolução na tabela dos envios, com o mesmo arquivo original e o mesmo tipo de carga.

    Recebe: conexao; perfil_de_origem (o retrato do envio de origem); novo_id; quantidade (pessoas devolvidas).
    Devolve: nada.
    """
    # O caminho do arquivo original e quem fez o envio de origem (a rastreabilidade de quem incluiu as pessoas)
    caminho_original, criado_por = conexao.execute(
        "SELECT caminho_original, criado_por FROM processamentos WHERE processamento_id = ?",
        (perfil_de_origem.processamento_id,)).fetchone()
    # O retrato é o do envio de origem, com o que muda: o identificador, as pessoas, a situação e a origem.
    # As perguntas da IA e os avisos da leitura já foram respondidos no envio de origem: não voltam
    perfil = perfil_de_origem.model_copy(update={
        "processamento_id": novo_id, "n_linhas": quantidade, "status": EstadoProcessamento.DEVOLVIDO,
        "perguntas_da_ia": [], "avisos": [], "duvidas": [], "alertas_guardrail": [],
        "envio_de_origem": perfil_de_origem.processamento_id,
        # A impressão digital ganha um final próprio: um novo envio do mesmo arquivo não é confundido com este
        "hash_sha256": perfil_de_origem.hash_sha256 + "#devolucao-" + novo_id})
    conexao.execute("INSERT INTO processamentos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (novo_id, perfil.empresa_id, perfil.nome_arquivo, perfil.hash_sha256, caminho_original,
                     perfil.tipo_carga.value, perfil.data_referencia.isoformat(), perfil.status.value,
                     perfil.model_dump_json(), _agora(), criado_por))


def _copiar_dados(conexao, processamento_id_de_origem: str, novo_id: str, registros_devolvidos: list[dict],
                  plano: list[dict], conferencia: dict) -> None:
    """Grava no envio de devolução os dados das pessoas devolvidas, o mapeamento aprovado e as decisões de coluna.

    Recebe: conexao; o envio de origem e o novo; registros_devolvidos (os dados atuais das pessoas, já com as
    correções do envio de origem); plano (o passo a passo da padronização do envio de origem); conferencia (a
    conferência de totais do arquivo, feita no envio de origem: o arquivo é o mesmo). Devolve: nada.
    """
    normalizador._preparar(conexao)
    # A padronização do envio de devolução: só as pessoas devolvidas, como estão hoje
    padronizacao = Normalizacao(registros=registros_devolvidos, plano=plano, log=[], conferencia=conferencia)
    decisoes = normalizador.decisoes_salvas(conexao, processamento_id_de_origem)
    conexao.execute("INSERT INTO normalizacoes (processamento_id, resultado, decisoes, criado_em) VALUES (?, ?, ?, ?)",
                    (novo_id, json.dumps(asdict(padronizacao), ensure_ascii=False),
                     json.dumps(decisoes, ensure_ascii=False), _agora()))
    # O mapeamento aprovado, igual ao do envio de origem (as colunas já foram conferidas pela empresa)
    mapeamentos._preparar(conexao)
    empresa_id, status, plano_em_json, criado_em, aprovado_por, aprovado_em = conexao.execute(
        "SELECT empresa_id, status, plano, criado_em, aprovado_por, aprovado_em FROM mapeamentos "
        "WHERE processamento_id = ?", (processamento_id_de_origem,)).fetchone()
    conexao.execute("INSERT INTO mapeamentos (processamento_id, empresa_id, status, plano, criado_em, aprovado_por, "
                    "aprovado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (novo_id, empresa_id, status, plano_em_json, criado_em, aprovado_por, aprovado_em))


def _copiar_respostas_aos_alertas(conexao, processamento_id_de_origem: str, novo_id: str,
                                  linhas_devolvidas: set[int]) -> None:
    """As respostas que a empresa já deu aos alertas das pessoas devolvidas continuam valendo no envio de devolução.

    Exemplo: a empresa tinha confirmado "o salário de Ana está certo" no envio de origem; no envio de devolução, esse
    alerta continua confirmado (só o pedido do banco fica em aberto). Recebe: conexao; os dois envios; as linhas.
    Devolve: nada.
    """
    validador._preparar(conexao)
    consulta = conexao.execute("SELECT regra_id, linha, resolucao, justificativa, usuario, criado_em FROM "
                               "resolucoes_alerta WHERE processamento_id = ? ORDER BY criado_em, rowid",
                               (processamento_id_de_origem,))
    respostas = []
    for regra_id, linha, resolucao, justificativa, usuario, criado_em in consulta:
        # Só as respostas das pessoas devolvidas
        if linha in linhas_devolvidas:
            respostas.append((novo_id, regra_id, linha, resolucao, justificativa, usuario, criado_em))
    for resposta in respostas:
        conexao.execute("INSERT INTO resolucoes_alerta (processamento_id, regra_id, linha, resolucao, justificativa, "
                        "usuario, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)", resposta)


def criar_envio_de_devolucao(conexao, processamento_id_de_origem: str, linhas_devolvidas: set[int],
                             avaliado_por: str) -> str:
    """Cria o envio de devolução com as pessoas que o banco apontou, já parado na correção pela empresa.

    Recebe: conexao; processamento_id_de_origem (o envio que o banco acabou de aprovar em parte); linhas_devolvidas
    (as pessoas apontadas, pela linha no arquivo); avaliado_por (o login do especialista).
    Devolve: o identificador do envio de devolução.
    Chamada logo depois da aprovação em parte (services/avaliacao_do_banco.avaliar), quando as outras pessoas já
    foram cadastradas no envio de origem.
    """
    # Importado aqui dentro: o fluxo usa vários serviços, e importar lá em cima faria um laço entre os arquivos
    from workflows import fluxo_empresa
    perfil_de_origem = processamentos.obter(conexao, processamento_id_de_origem)
    empresa_id = perfil_de_origem.empresa_id
    # Os dados atuais das pessoas devolvidas (com as correções que a empresa fez antes de enviar)
    dados = correcoes.dados_atuais(conexao, processamento_id_de_origem)
    registros_devolvidos = []
    registros_por_linha = {}
    for registro in dados.registros:
        if registro["_linha"] in linhas_devolvidas:
            registros_devolvidos.append(registro)
            registros_por_linha[registro["_linha"]] = registro
    # Um identificador novo, do mesmo jeito que o recebimento de um arquivo cria
    novo_id = uuid.uuid4().hex[:12]
    quantidade = len(registros_devolvidos)
    _gravar_envio(conexao, perfil_de_origem, novo_id, quantidade)
    _copiar_dados(conexao, processamento_id_de_origem, novo_id, registros_devolvidos, dados.plano, dados.conferencia)
    _copiar_respostas_aos_alertas(conexao, processamento_id_de_origem, novo_id, linhas_devolvidas)
    conexao.commit()
    # Os apontamentos saem do rascunho do envio de origem e vão para o envio de devolução (viram pendências)
    apontamentos_do_banco.enviar_para_a_empresa(conexao, processamento_id_de_origem, novo_id, registros_por_linha)
    # Na trilha do envio de devolução: de onde ele veio, quem devolveu e quantas pessoas (nada pessoal)
    recado = recado_da_devolucao(quantidade)
    auditoria.registrar(conexao, novo_id, empresa_id, "Avaliação do banco", "DEVOLVIDO_PELO_BANCO",
                        {"motivo": recado, "avaliado_por": avaliado_por,
                         "envio_de_origem": processamento_id_de_origem, "pessoas": quantidade})
    # As pendências da empresa: a validação de sempre, agora com os pedidos do banco
    validador.executar(conexao, novo_id, empresa_id)
    # O fluxo do envio de devolução começa parado na correção, com as escolhas do envio de origem
    estado_de_origem = fluxo_empresa.situacao(conexao, processamento_id_de_origem)["estado"]
    fluxo_empresa.comecar_na_correcao(conexao, novo_id, empresa_id, estado_de_origem, "Devolvido pelo banco: " + recado)
    # A validação acima deixou a situação em "com pendências": o envio acabou de ser devolvido pelo banco
    processamentos.atualizar_status(conexao, novo_id, EstadoProcessamento.DEVOLVIDO)
    return novo_id


def encerrar_se_ficou_vazio(conexao, processamento_id: str, empresa_id: str, login: str) -> bool:
    """Encerra o envio de devolução quando a empresa tirou todas as pessoas dele ("Não cadastrar esta pessoa").

    Tirar a pessoa não volta ao banco para confirmar; se não sobra ninguém, a
    devolução fecha sozinha e fica registrada. Recebe: conexao; o envio; a empresa; o login de quem tirou a última
    pessoa. Devolve: True se encerrou; False se não era um envio de devolução ou se ainda há pessoas nele.
    """
    # Importado aqui dentro: o fluxo usa vários serviços, e importar lá em cima faria um laço entre os arquivos
    from workflows import fluxo_empresa
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    # Só o envio de devolução se encerra sozinho (um envio comum sem ninguém segue as regras de sempre)
    if perfil is None or not perfil.envio_de_origem:
        return False
    if correcoes.dados_atuais(conexao, processamento_id).registros:
        return False
    # O fluxo está parado com a empresa (na correção ou no envio ao banco): a resposta "rejeitar" encerra o envio
    etapa_atual = fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"]
    if etapa_atual not in ("aguardar_correcao", "aprovar_homologacao"):
        return False
    fluxo_empresa.responder(conexao, processamento_id, empresa_id, etapa_atual, {"acao": "rejeitar"})
    auditoria.registrar(conexao, processamento_id, empresa_id, "Avaliação do banco", "DEVOLUCAO_ENCERRADA",
                        {"motivo": "todas as pessoas devolvidas saíram do envio", "por": login})
    return True
