"""Os apontamentos do especialista do banco: um problema numa pessoa do envio, com o recado para a empresa (ADR-121).

Para que serve: na aba Envios do Portal Interno, o especialista confere as pessoas de um envio que espera o banco. Além
de aprovar tudo ou devolver o envio inteiro (ADR-69), ele pode "apontar um problema" em qualquer
pessoa (com ou sem alerta), escolhendo o motivo de uma lista fechada e escrevendo o recado que a empresa vai ler.

A vida de um apontamento, em duas situações:
    - RASCUNHO: o especialista marcou a pessoa, mas ainda não decidiu o envio. Ele pode trocar o recado ou desfazer;
    - ENVIADO: o especialista decidiu ("Aprovar os outros e devolver os marcados" ou "Devolver o envio inteiro"). O
      apontamento vai para a empresa e vira uma pendência daquela pessoa (services/validador.py, regra
      PEDIDO_DO_BANCO). Nessa hora ele guarda o valor que o campo tinha ("valor_apontado"): se a empresa trocar o
      valor, a pendência some sozinha, e o banco vê o antes e o depois.

Exemplo: o salário de Ana veio R$ 48.000,00 para o cargo de assistente. O especialista aponta "Confirmar o salário",
com o recado "O salário parece alto demais para o cargo. Pode conferir?". A empresa corrige para R$ 4.800,00 (a
pendência some) ou responde "Está certo assim" (o banco lê a resposta na próxima avaliação).

Nada de dado pessoal vai para a trilha de auditoria por aqui: o recado fica só nesta tabela, que é da empresa dona do
envio e do banco.
"""
import uuid
from datetime import datetime, timezone

from services import auditoria

# Os motivos que o especialista pode escolher (lista fechada: ajuda a medir depois os problemas mais comuns).
# Cada motivo diz o texto da tela e o campo do layout que ele aponta (None: a pessoa inteira, sem um campo só)
MOTIVOS = {
    "salario": {"texto": "Confirmar o salário", "campo": "valor_renda"},
    "cpf": {"texto": "CPF incorreto", "campo": "cpf"},
    "nome": {"texto": "Nome incorreto ou incompleto", "campo": "nome_completo"},
    "cargo": {"texto": "Cargo incorreto", "campo": "cargo"},
    "admissao": {"texto": "Data de admissão incorreta", "campo": "data_admissao"},
    "outro_dado": {"texto": "Outro dado incorreto ou incompleto", "campo": None},
    "nao_pertence": {"texto": "Pessoa não parece ser desta empresa", "campo": None},
    "outro": {"texto": "Outro motivo", "campo": None},
}
# O recado precisa dizer algo à empresa: pelo menos 15 letras, e no máximo 400 (o tamanho da caixa de texto da tela)
MINIMO_DE_LETRAS_DO_RECADO = 15
MAXIMO_DE_LETRAS_DO_RECADO = 400
# As duas situações de um apontamento
RASCUNHO = "RASCUNHO"
ENVIADO = "ENVIADO"


def _agora() -> str:
    """Data e hora atuais (UTC), em texto. Exemplo: "2026-09-28T14:05:00+00:00"."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _preparar(conexao) -> None:
    """Cria a tabela dos apontamentos, se ainda não existir.

    processamento_id é o envio em que o apontamento está AGORA: o envio avaliado (no rascunho e na devolução do envio
    inteiro) ou o envio de devolução (quando o banco aprova os outros e devolve só as pessoas marcadas).
    """
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS apontamentos_do_banco (
               apontamento_id   TEXT PRIMARY KEY,
               processamento_id TEXT NOT NULL,
               empresa_id       TEXT NOT NULL,
               linha            INTEGER NOT NULL,   -- a linha da pessoa no arquivo da empresa
               motivo           TEXT NOT NULL,      -- uma chave de MOTIVOS
               campo            TEXT,               -- o campo do layout apontado (vazio: a pessoa inteira)
               recado           TEXT NOT NULL,      -- o que a empresa lê
               valor_apontado   TEXT,               -- o valor do campo quando o apontamento foi para a empresa
               situacao         TEXT NOT NULL,      -- RASCUNHO ou ENVIADO
               criado_por       TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               enviado_em       TEXT
           )"""
    )


def motivos() -> list[dict]:
    """Os motivos da lista fechada, na ordem da tela.

    Recebe: nada. Devolve: [{valor, texto}]. Exemplo: [{"valor": "salario", "texto": "Confirmar o salário"}, ...].
    """
    lista = []
    for valor, motivo in MOTIVOS.items():
        lista.append({"valor": valor, "texto": motivo["texto"]})
    return lista


def _para_a_tela(linha_do_banco: tuple) -> dict:
    """Um apontamento lido da tabela, no formato que as telas usam.

    Recebe: a linha da consulta (apontamento_id, processamento_id, linha, motivo, campo, recado, valor_apontado,
    situacao, criado_por, criado_em). Devolve: o dicionário com as mesmas chaves e mais "motivo_texto".
    """
    (apontamento_id, processamento_id, linha, motivo, campo, recado, valor_apontado, situacao, criado_por,
     criado_em) = linha_do_banco
    # O texto do motivo (um motivo que saiu da lista continua legível pela própria chave)
    motivo_texto = MOTIVOS.get(motivo, {"texto": motivo})["texto"]
    return {"apontamento_id": apontamento_id, "processamento_id": processamento_id, "linha": linha,
            "motivo": motivo, "motivo_texto": motivo_texto, "campo": campo, "recado": recado,
            "valor_apontado": valor_apontado, "situacao": situacao, "criado_por": criado_por,
            "criado_em": criado_em}


def _listar(conexao, processamento_id: str, situacao: str) -> list[dict]:
    """Os apontamentos de um envio numa situação, na ordem em que foram feitos.

    Recebe: conexao; processamento_id; situacao (RASCUNHO ou ENVIADO). Devolve: a lista de apontamentos.
    """
    _preparar(conexao)
    consulta = conexao.execute(
        "SELECT apontamento_id, processamento_id, linha, motivo, campo, recado, valor_apontado, situacao, criado_por, "
        "criado_em FROM apontamentos_do_banco WHERE processamento_id = ? AND situacao = ? ORDER BY criado_em, linha",
        (processamento_id, situacao))
    apontamentos = []
    for linha_do_banco in consulta:
        apontamentos.append(_para_a_tela(linha_do_banco))
    return apontamentos


def rascunhos(conexao, processamento_id: str) -> dict[int, dict]:
    """Os apontamentos ainda não decididos de um envio, pela linha da pessoa.

    Recebe: conexao; processamento_id. Devolve: {linha: apontamento}. Exemplo: {12: {"motivo": "salario", ...}}.
    """
    por_linha = {}
    for apontamento in _listar(conexao, processamento_id, RASCUNHO):
        por_linha[apontamento["linha"]] = apontamento
    return por_linha


def enviados(conexao, processamento_id: str) -> list[dict]:
    """Os apontamentos que já foram para a empresa neste envio (viram pendências da empresa; ver o validador).

    Recebe: conexao; processamento_id. Devolve: a lista de apontamentos, do mais antigo ao mais novo.
    """
    return _listar(conexao, processamento_id, ENVIADO)


def conferir_recado(motivo: str, recado: str) -> str:
    """Confere o motivo e o recado de um apontamento e devolve o recado sem espaços nas pontas.

    Recebe: motivo (uma chave de MOTIVOS); recado. Devolve: o recado limpo.
    Levanta ValueError com a frase para a tela, se o motivo não é da lista ou o recado é curto ou longo demais.
    """
    if motivo not in MOTIVOS:
        raise ValueError("Escolha um motivo da lista.")
    recado_limpo = (recado or "").strip()
    if len(recado_limpo) < MINIMO_DE_LETRAS_DO_RECADO:
        raise ValueError("Escreva um recado com pelo menos 15 letras: é o que a empresa vai ler.")
    if len(recado_limpo) > MAXIMO_DE_LETRAS_DO_RECADO:
        raise ValueError("O recado pode ter no máximo 400 letras.")
    return recado_limpo


def gravar_rascunho(conexao, processamento_id: str, empresa_id: str, linha: int, motivo: str, recado: str,
                    login: str) -> dict:
    """Grava (ou troca) o apontamento em rascunho de uma pessoa do envio.

    Recebe: conexao; o envio e a empresa dele; linha (a pessoa); motivo e recado já conferidos (conferir_recado);
    login (quem apontou). Devolve: o apontamento gravado.
    Quem confere se o envio espera o banco e se a linha é do envio é services/avaliacao_do_banco.apontar.
    """
    _preparar(conexao)
    # Uma pessoa tem no máximo um apontamento em rascunho: o novo substitui o anterior
    conexao.execute("DELETE FROM apontamentos_do_banco WHERE processamento_id = ? AND linha = ? AND situacao = ?",
                    (processamento_id, linha, RASCUNHO))
    # Um identificador curto e sorteado, que entra no código da pendência da empresa (PEDIDO_DO_BANCO:<id>)
    apontamento_id = uuid.uuid4().hex[:12]
    conexao.execute(
        "INSERT INTO apontamentos_do_banco (apontamento_id, processamento_id, empresa_id, linha, motivo, campo, recado, "
        "valor_apontado, situacao, criado_por, criado_em, enviado_em) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)",
        (apontamento_id, processamento_id, empresa_id, linha, motivo, MOTIVOS[motivo]["campo"], recado, RASCUNHO,
         login, _agora()))
    conexao.commit()
    # Na trilha, só a linha e o motivo (o recado pode citar dado pessoal)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Avaliação do banco", "PESSOA_APONTADA_PELO_BANCO",
                        {"linha": linha, "motivo": motivo, "por": login})
    return rascunhos(conexao, processamento_id)[linha]


def apagar_rascunho(conexao, processamento_id: str, empresa_id: str, linha: int, login: str) -> bool:
    """Desfaz o apontamento em rascunho de uma pessoa (o especialista mudou de ideia).

    Recebe: conexao; o envio e a empresa dele; linha; login. Devolve: True se havia um apontamento; False se não havia.
    """
    _preparar(conexao)
    # Só o rascunho sai: um apontamento que já foi para a empresa fica guardado (é o histórico da avaliação)
    cursor = conexao.execute("DELETE FROM apontamentos_do_banco WHERE processamento_id = ? AND linha = ? AND "
                             "situacao = ?", (processamento_id, linha, RASCUNHO))
    conexao.commit()
    havia = cursor.rowcount > 0
    if havia:
        auditoria.registrar(conexao, processamento_id, empresa_id, "Avaliação do banco",
                            "APONTAMENTO_DESFEITO_PELO_BANCO", {"linha": linha, "por": login})
    return havia


def enviar_para_a_empresa(conexao, processamento_id_avaliado: str, processamento_id_destino: str,
                          registros_por_linha: dict[int, dict]) -> list[dict]:
    """Manda os rascunhos de um envio para a empresa: eles viram ENVIADO, no envio em que a empresa vai responder.

    Recebe: conexao; processamento_id_avaliado (onde os rascunhos estão); processamento_id_destino (o próprio envio,
    na devolução do envio inteiro, ou o envio de devolução, quando só as pessoas marcadas voltam);
    registros_por_linha ({linha: registro com os dados atuais}), para guardar o valor de cada campo apontado.
    Devolve: os apontamentos enviados.
    """
    agora = _agora()
    for linha, apontamento in rascunhos(conexao, processamento_id_avaliado).items():
        # O valor do campo apontado nesta hora (sem campo, nada a guardar)
        valor_apontado = None
        registro = registros_por_linha.get(linha, {})
        if apontamento["campo"] and registro.get(apontamento["campo"]) is not None:
            valor_apontado = str(registro.get(apontamento["campo"]))
        conexao.execute("UPDATE apontamentos_do_banco SET processamento_id = ?, valor_apontado = ?, situacao = ?, "
                        "enviado_em = ? WHERE apontamento_id = ?",
                        (processamento_id_destino, valor_apontado, ENVIADO, agora, apontamento["apontamento_id"]))
    conexao.commit()
    return enviados(conexao, processamento_id_destino)


def _valor_em_texto(valor) -> str:
    """Um valor do cadastro como texto, para comparar: o campo em branco (None ou "") é sempre o texto vazio.

    Ex.: None → ""; "" → ""; Decimal("4800.00") → "4800.00".
    """
    if valor is None:
        return ""
    return str(valor)


def empresa_mudou_o_valor(apontamento: dict, registro: dict) -> bool:
    """Diz se a empresa trocou o valor do campo apontado depois que o apontamento foi para ela (ela corrigiu).

    Recebe: o apontamento (com "campo" e "valor_apontado", o valor na hora do envio) e o registro da pessoa com os dados
    de hoje. Devolve: True se o valor mudou; False se não mudou ou se o apontamento é da pessoa inteira (sem campo).
    O campo em branco conta como texto vazio: um campo opcional pode chegar em branco ao banco (ADR-143), e preenchê-lo
    é a resposta da empresa. É a mesma conta para a pendência da empresa (services/validador.py) e para a resposta que o
    banco lê (services/idas_e_voltas.py).
    Ex.: "48000.00" → hoje "4800.00": True; em branco (None) → hoje "Analista": True; "Ana" → hoje "Ana": False.
    """
    # O apontamento da pessoa inteira não tem um valor para comparar
    if not apontamento["campo"]:
        return False
    # O valor na hora do envio e o de hoje, os dois como texto
    valor_na_hora_do_envio = _valor_em_texto(apontamento["valor_apontado"])
    valor_de_hoje = _valor_em_texto(registro.get(apontamento["campo"]))
    return valor_de_hoje != valor_na_hora_do_envio


def justificativa_da_empresa(conexao, processamento_id: str, regra_id: str, linha: int) -> str | None:
    """A resposta que a empresa escreveu ao confirmar uma pendência do banco ("Está certo assim, é diretor").

    Recebe: conexao; o envio; o código da pendência (PEDIDO_DO_BANCO:<id>); a linha. Devolve: o texto mais recente,
    ou None se a empresa não confirmou (ou reabriu).
    """
    # A tabela das resoluções é do validador; importado aqui dentro para os dois arquivos não se importarem em laço
    from services import validador
    validador._preparar(conexao)
    consulta = conexao.execute("SELECT resolucao, justificativa FROM resolucoes_alerta WHERE processamento_id = ? AND "
                               "regra_id = ? AND linha = ? ORDER BY criado_em, rowid", (processamento_id, regra_id,
                                                                                        linha))
    resposta = None
    # Em ordem: a mais recente vale (uma reabertura apaga a resposta anterior)
    for resolucao, justificativa in consulta:
        resposta = None
        if resolucao in validador.RESOLUCOES_DE_JUSTIFICATIVA:
            resposta = justificativa
    return resposta
