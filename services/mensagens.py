"""As conversas de ajuda entre as empresas e o especialista do banco (o "Posso ajudar?"), gravadas no banco de dados.

Para que serve: a empresa escreve pelo balão "Posso ajudar?" do Portal Empresa, e o especialista responde na aba
Conversa da ficha da empresa, no Portal Interno. É uma conversa ENTRE PESSOAS: nenhuma IA responde por ninguém.
Cada empresa tem uma conversa só; cada mensagem guarda quem escreveu (o login), de que lado
(empresa ou banco), de que tela veio (o "contexto") e quando.

Regras:
    - a empresa só lê e escreve na PRÓPRIA conversa (a empresa vem da sessão, nunca da tela);
    - só o banco vê todas as conversas, responde, começa uma conversa e a marca como resolvida (na tela, "Marcar
      como respondida");
    - mensagem nova reabre a conversa resolvida;
    - mensagem vazia ou longa demais é recusada.

Conversa aberta (o sinal com o número, a "bolinha", no menu do banco, na aba Conversa e na Carteira): a conversa que
tem mensagem e ainda não foi marcada como respondida. Ou ela espera a resposta do
especialista (a última mensagem é da empresa), ou ele já respondeu e ainda não marcou.

Tabelas: mensagens_de_ajuda (uma linha por mensagem) e conversas_resolvidas (as empresas com a conversa resolvida).

Prazo de resposta (ADR-94): o banco responde em até 1 dia útil. Cada vez que a empresa escreve e fica esperando, o
prazo é o mesmo horário do próximo dia útil (sábado e domingo não contam; feriados ainda não). A aba Mensagens mostra
quantas perguntas foram respondidas no prazo e marca a conversa atrasada.
"""
from datetime import datetime, timedelta, timezone

from models.contratos import Perfil
from services import dados_mock

# O tamanho máximo de uma mensagem (uma conversa de ajuda, não um documento)
TAMANHO_MAXIMO = 2000


def _preparar(conexao) -> None:
    """Cria as tabelas das conversas, se ainda não existirem."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS mensagens_de_ajuda (
               id          INTEGER PRIMARY KEY AUTOINCREMENT,
               empresa_id  TEXT NOT NULL,
               de          TEXT NOT NULL,
               autor       TEXT NOT NULL,
               contexto    TEXT NOT NULL,
               texto       TEXT NOT NULL,
               criado_em   TEXT NOT NULL
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS conversas_resolvidas (
               empresa_id    TEXT PRIMARY KEY,
               resolvida_por TEXT NOT NULL,
               resolvida_em  TEXT NOT NULL
           )"""
    )


def _agora() -> str:
    """A data e hora de agora, no horário universal (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texto_conferido(texto: str) -> str:
    """Tira os espaços das pontas e confere o tamanho da mensagem.

    Recebe: o texto digitado. Devolve: o texto limpo. Levanta ValueError se ficar vazio ou passar do tamanho máximo.
    """
    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        raise ValueError("Escreva a mensagem antes de enviar.")
    if len(texto_limpo) > TAMANHO_MAXIMO:
        raise ValueError("A mensagem passou de " + str(TAMANHO_MAXIMO) + " caracteres. Resuma e envie de novo.")
    return texto_limpo


def _mensagens(conexao, empresa_id: str | None = None) -> dict:
    """As mensagens gravadas, agrupadas por empresa e em ordem.

    Recebe: conexao; empresa_id (só dessa empresa) ou None (todas). Devolve: {empresa_id: [mensagem, ...]}.
    """
    consulta = conexao.execute(
        "SELECT empresa_id, de, autor, contexto, texto, criado_em FROM mensagens_de_ajuda "
        "WHERE (? IS NULL OR empresa_id = ?) ORDER BY id", (empresa_id, empresa_id))
    por_empresa = {}
    for empresa, de, autor, contexto, texto, criado_em in consulta:
        por_empresa.setdefault(empresa, []).append(
            {"de": de, "autor": autor, "contexto": contexto, "texto": texto, "quando": criado_em})
    return por_empresa


def _empresas_resolvidas(conexao) -> set:
    """As empresas com a conversa marcada como resolvida."""
    resolvidas = set()
    for (empresa_id,) in conexao.execute("SELECT empresa_id FROM conversas_resolvidas"):
        resolvidas.add(empresa_id)
    return resolvidas


def _montar_conversa(empresa_id: str, mensagens: list[dict], resolvidas: set) -> dict:
    """Uma conversa no formato das telas: {id, empresa, resolvida, mensagens}."""
    return {"id": empresa_id, "empresa": dados_mock.nome_da_empresa(empresa_id),
            "resolvida": empresa_id in resolvidas, "mensagens": mensagens}


def conversa_da_empresa(conexao, empresa_id: str) -> dict:
    """A conversa de uma empresa (vazia se ela ainda não escreveu).

    Recebe: conexao; empresa_id (da sessão). Devolve: {id, empresa, resolvida, mensagens}.
    """
    _preparar(conexao)
    mensagens = _mensagens(conexao, empresa_id).get(empresa_id, [])
    return _montar_conversa(empresa_id, mensagens, _empresas_resolvidas(conexao))


def conversas_da_carteira(conexao) -> list[dict]:
    """Todas as conversas que têm pelo menos uma mensagem (a aba Mensagens do banco), na ordem da carteira.

    Recebe: conexao. Devolve: [{id, empresa, resolvida, mensagens}].
    """
    _preparar(conexao)
    por_empresa = _mensagens(conexao)
    resolvidas = _empresas_resolvidas(conexao)
    conversas = []
    for empresa in dados_mock.empresas():
        empresa_id = empresa["empresa_id"]
        if empresa_id in por_empresa:
            conversas.append(_montar_conversa(empresa_id, por_empresa[empresa_id], resolvidas))
    return conversas


def mandar_mensagem(conexao, usuario, texto: str, contexto: str = "", empresa_id: str | None = None) -> None:
    """Grava uma mensagem na conversa de uma empresa e reabre a conversa, se estava resolvida.

    Recebe: conexao; usuario (da sessão); texto; contexto (a tela de onde a empresa escreveu);
    empresa_id — só para o banco (a conversa que ele responde); a empresa escreve sempre na PRÓPRIA conversa.
    Devolve: nada. Levanta ValueError (texto vazio, longo ou empresa errada).
    """
    _preparar(conexao)
    texto_limpo = _texto_conferido(texto)
    # De que lado vem a mensagem e em que conversa ela entra
    if usuario.perfil == Perfil.EMPRESA:
        lado = "empresa"
        conversa = usuario.empresa_id
    else:
        # O banco (o outro perfil) responde à conversa da empresa escolhida
        lado = "banco"
        conversa = empresa_id
        # O banco só responde a uma empresa da carteira
        if conversa not in _ids_das_empresas():
            raise ValueError("Empresa não encontrada na carteira.")
    conexao.execute(
        "INSERT INTO mensagens_de_ajuda (empresa_id, de, autor, contexto, texto, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
        (conversa, lado, usuario.login, (contexto or "")[:100], texto_limpo, _agora()))
    # Mensagem nova reabre a conversa
    conexao.execute("DELETE FROM conversas_resolvidas WHERE empresa_id = ?", (conversa,))
    conexao.commit()


def marcar_resolvida(conexao, usuario, empresa_id: str) -> None:
    """O banco marca a conversa de uma empresa como resolvida.

    Recebe: conexao; usuario (da sessão; só o BANCO); empresa_id. Devolve: nada.
    Levanta PermissionError (outro perfil) ou ValueError (conversa sem mensagens).
    """
    _preparar(conexao)
    if usuario.perfil != Perfil.BANCO:
        raise PermissionError("Só o banco marca uma conversa como resolvida.")
    if not _mensagens(conexao, empresa_id):
        raise ValueError("Esta empresa ainda não escreveu.")
    # Troca a marca antiga (se houver) pela nova
    conexao.execute("DELETE FROM conversas_resolvidas WHERE empresa_id = ?", (empresa_id,))
    conexao.execute("INSERT INTO conversas_resolvidas (empresa_id, resolvida_por, resolvida_em) VALUES (?, ?, ?)",
                    (empresa_id, usuario.login, _agora()))
    conexao.commit()


def _ultima_mensagem_de_cada_conversa(conexao) -> list[tuple]:
    """A última mensagem de cada conversa: de que empresa, de que lado (empresa ou banco) e quando.

    Recebe: conexao. Devolve: [(empresa_id, de, criado_em)], da mensagem mais recente para a mais antiga.
    A última mensagem de uma conversa é a de maior número (id), porque as mensagens são numeradas na ordem em que
    chegam. Só lê essas três colunas: o texto das mensagens não sai daqui.
    """
    consulta = conexao.execute(
        "SELECT empresa_id, de, criado_em FROM mensagens_de_ajuda "
        "WHERE id IN (SELECT MAX(id) FROM mensagens_de_ajuda GROUP BY empresa_id) ORDER BY criado_em DESC")
    # Uma tupla por conversa
    ultimas = []
    for empresa_id, de, criado_em in consulta:
        ultimas.append((empresa_id, de, criado_em))
    return ultimas


def empresas_com_conversa_aberta(conexao) -> list[dict]:
    """As empresas da carteira com a conversa aberta: é o que o sinal (a "bolinha") conta.

    Aberta é a conversa que tem mensagem e ainda não foi marcada como respondida. Marcar como respondida fecha a
    conversa, mesmo quando a última palavra foi da empresa (ex.: um "obrigado", que não pede resposta).

    Recebe: conexao. Devolve: [{empresa_id, sem_resposta, ultima_mensagem_em}], da conversa com a mensagem mais
    recente para a mais antiga. sem_resposta é True quando a última mensagem é da empresa (ela espera o especialista)
    e False quando o especialista já respondeu (falta marcar); ultima_mensagem_em é a data e a hora dessa mensagem.
    Exemplo: [{"empresa_id": "EMP001", "sem_resposta": True, "ultima_mensagem_em": "2026-09-30T10:05:00+00:00"}].
    """
    _preparar(conexao)
    # As conversas já marcadas como respondidas e as empresas da carteira
    resolvidas = _empresas_resolvidas(conexao)
    ids_da_carteira = _ids_das_empresas()
    abertas = []
    for empresa_id, de, criado_em in _ultima_mensagem_de_cada_conversa(conexao):
        # Empresa fora da carteira: não entra (a mesma regra da lista das conversas)
        if empresa_id not in ids_da_carteira:
            continue
        # Marcada como respondida: fechada
        if empresa_id in resolvidas:
            continue
        # Aberta: esperando o especialista (a última é da empresa) ou esperando ele marcar como respondida
        abertas.append({"empresa_id": empresa_id, "sem_resposta": de == "empresa", "ultima_mensagem_em": criado_em})
    return abertas


# Sábado e domingo (segunda = 0 ... domingo = 6): não são dias úteis
DIAS_DO_FIM_DE_SEMANA = (5, 6)


def prazo_de_um_dia_util(momento: datetime) -> datetime:
    """O fim do prazo de 1 dia útil a partir de uma mensagem da empresa.

    Recebe: a hora da mensagem. Devolve: a mesma hora do próximo dia útil. Mensagem no fim de semana conta a partir
    de segunda, 0h. Exemplos: quinta 15h → sexta 15h; sexta 15h → segunda 15h; sábado 10h → terça 0h.
    """
    inicio = momento
    # No fim de semana, o prazo começa a contar na segunda, 0h
    while inicio.weekday() in DIAS_DO_FIM_DE_SEMANA:
        inicio = (inicio + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Um dia útil depois: pula sábado e domingo
    fim = inicio + timedelta(days=1)
    while fim.weekday() in DIAS_DO_FIM_DE_SEMANA:
        fim = fim + timedelta(days=1)
    return fim


def _vezes_da_empresa(mensagens: list[dict]) -> list[dict]:
    """Cada vez que a empresa escreveu e ficou esperando o banco: quando escreveu e quando o banco respondeu.

    Recebe: as mensagens da conversa, em ordem. Devolve: [{perguntou_em, respondida_em (ou None)}]. Várias mensagens
    seguidas da empresa contam como uma vez só (o prazo corre da primeira). Exemplo: empresa, empresa, banco, empresa
    → 2 vezes: a primeira respondida, a segunda esperando.
    """
    vezes = []
    esperando = None
    for mensagem in mensagens:
        if mensagem["de"] == "empresa" and esperando is None:
            esperando = {"perguntou_em": datetime.fromisoformat(mensagem["quando"]), "respondida_em": None}
        elif mensagem["de"] == "banco" and esperando is not None:
            esperando["respondida_em"] = datetime.fromisoformat(mensagem["quando"])
            vezes.append(esperando)
            esperando = None
    if esperando is not None:
        vezes.append(esperando)
    return vezes


def prazo_das_respostas(conexao, agora: datetime | None = None) -> dict:
    """O prazo de resposta de 1 dia útil, medido nas conversas da carteira (ADR-94).

    Recebe: conexao; agora (para os testes; sem informar, a hora atual). Devolve: {respondidas, no_prazo,
    percentual_no_prazo (None sem respondidas), esperando, atrasadas, atrasadas_por_empresa: [empresa_id]}.
    Conversa resolvida pelo banco sem resposta escrita não conta como esperando.
    """
    agora = agora or datetime.now(timezone.utc)
    respondidas, no_prazo, esperando, atrasadas = 0, 0, 0, 0
    atrasadas_por_empresa = []
    for conversa in conversas_da_carteira(conexao):
        for vez in _vezes_da_empresa(conversa["mensagens"]):
            prazo = prazo_de_um_dia_util(vez["perguntou_em"])
            if vez["respondida_em"] is not None:
                respondidas = respondidas + 1
                if vez["respondida_em"] <= prazo:
                    no_prazo = no_prazo + 1
            elif not conversa["resolvida"]:
                esperando = esperando + 1
                if agora > prazo:
                    atrasadas = atrasadas + 1
                    atrasadas_por_empresa.append(conversa["id"])
    percentual = None
    if respondidas:
        percentual = round(100 * no_prazo / respondidas)
    return {"respondidas": respondidas, "no_prazo": no_prazo, "percentual_no_prazo": percentual,
            "esperando": esperando, "atrasadas": atrasadas, "atrasadas_por_empresa": atrasadas_por_empresa}


def _ids_das_empresas() -> set:
    """Os ids das empresas da carteira."""
    ids = set()
    for empresa in dados_mock.empresas():
        ids.add(empresa["empresa_id"])
    return ids
