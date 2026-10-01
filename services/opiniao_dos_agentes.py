"""A opinião das pessoas sobre os agentes de IA: o joinha para cima (ajudou) e para baixo (não ajudou) em cada
resposta de um agente, e os números que o banco acompanha na tela Acompanhamento dos agentes (ADR-151).

Onde o joinha aparece (os "tipos" de interação):
    - "resposta_da_conversa": cada resposta do Agente de validação na conversa de uma pendência (Portal Empresa, telas
      Cadastrar e Acompanhar). A referência é a chave da conversa e a posição do balão, "<chave>|<ordem>", do jeito que
      services/conversas_das_pendencias.py guarda. Ex.: "a1b2|VALOR_NAO_CONVERTIDO|8|estado_civil|2";
    - "pergunta_da_leitura": a pergunta que o Agente Leitor ou o Agente Conferidor fez ao ler o documento, que vira a
      pendência "PERGUNTA_DA_IA:<campo>" (services/validador.py). A referência é "<envio>|<linha>|<campo>", com
      "PESSOA" no lugar do campo quando a pergunta é sobre a pessoa toda. Ex.: "a1b2|4|cpf";
    - "material_do_endomarketing": o texto que o Agente de Endomarketing escreveu, que o especialista do banco avalia
      (Portal Interno, aba Endomarketing). A referência é o código do material.

As regras:
    - um voto por pessoa em cada interação: mudar de ideia troca o voto, sem somar dois; retirar o voto apaga a linha;
    - cada portal vota só no que é dele. A empresa vota nas respostas e nas perguntas dos envios dela (o envio de outra
      empresa é "não encontrado", sem dizer se existe); o banco vota nos materiais do Endomarketing;
    - o comentário é opcional, só no joinha para baixo ("O que faltou?"), com até 200 letras. Quem votou vê o próprio
      comentário embaixo do joinha. Ele pode trazer dado pessoal: por isso não vai para nenhuma IA e não aparece para o
      banco, que vê só quantos há;
    - quem votou fica guardado (o login e o perfil), mas o banco vê só números agregados, como no resto do Portal
      Interno (ADR-117 e ADR-144): a satisfação de cada agente, os votos do período e a tendência por semana;
    - a origem diz de onde veio o voto: "tela" (uma pessoa votou) ou "carga sintética" (os dados de demonstração do
      scripts/gerar_opinioes_dos_agentes.py, que o mesmo script tira com --remover).

Exemplo de uso:
    opiniao = votar_como_empresa(conexao, usuario, "resposta_da_conversa", "a1b2|CPF_INVALIDO|8|cpf|2", "para_cima")
    numeros = satisfacao_dos_agentes(conexao, de="2026-09-01", ate="2026-09-30")
"""
from datetime import date, datetime, timedelta, timezone

from agents import conferidor_da_leitura, endomarketing
from services import conversas_das_pendencias, processamentos

# Os três tipos de interação que recebem o joinha (ver o texto do alto)
TIPO_RESPOSTA_DA_CONVERSA = "resposta_da_conversa"
TIPO_PERGUNTA_DA_LEITURA = "pergunta_da_leitura"
TIPO_MATERIAL_DO_ENDOMARKETING = "material_do_endomarketing"
# Os dois votos: ajudou (para cima) e não ajudou (para baixo)
PARA_CIMA = "para_cima"
PARA_BAIXO = "para_baixo"
VOTOS = (PARA_CIMA, PARA_BAIXO)
# O maior comentário aceito: uma frase curta
TAMANHO_MAXIMO_DO_COMENTARIO = 200
# De onde veio o voto: de uma pessoa, na tela, ou da carga dos dados de demonstração
ORIGEM_DA_TELA = "tela"
ORIGEM_DA_CARGA_SINTETICA = "carga sintética"
# O campo da pergunta sobre a pessoa toda (é a pendência "PERGUNTA_DA_IA:PESSOA", em services/validador.py)
PERGUNTA_SOBRE_A_PESSOA = "PESSOA"
# Quem fala na conversa quando é o agente (os outros são "empresa" e "erro")
QUEM_E_O_AGENTE = "ia"
# Os agentes que recebem o joinha, na ordem em que a tela mostra: o nome que as telas usam e o que ele faz
AGENTES = {
    "agente_de_validacao": {"nome": "Agente de validação",
                            "o_que_faz": "Responde a empresa na conversa de cada pendência."},
    "leitor": {"nome": "Agente Leitor",
               "o_que_faz": "Pergunta à empresa o que não entendeu ao ler o documento."},
    "conferidor": {"nome": "Agente Conferidor",
                   "o_que_faz": "Pergunta à empresa quando desconfia de um valor lido."},
    "endomarketing": {"nome": "Agente de Endomarketing",
                      "o_que_faz": "Escreve os materiais que o banco confere e publica."},
}
# Quantas semanas a tendência mostra: a semana do fim do período e as anteriores
SEMANAS_DA_TENDENCIA = 12
# Quantas semanas de cada ponta da tendência entram na comparação ("subiu 9 pontos"): as primeiras e as últimas
SEMANAS_DA_COMPARACAO = 4
# O mínimo de votos em cada ponta para a comparação valer: com menos, a diferença seria obra do acaso (2 votos em 2
# semanas viram "100%" ou "0%")
MINIMO_DE_VOTOS_PARA_COMPARAR = 5
# O horário de Brasília (3 horas atrás do horário universal): a semana vira à meia-noite daqui
FUSO_DE_BRASILIA = timezone(timedelta(hours=-3))
# O que a tela recebe quando a referência não diz qual resposta ou qual pergunta recebeu o voto
REFERENCIA_DA_RESPOSTA_INVALIDA = "Não sei qual resposta recebeu o voto. Atualize a página e tente de novo."
REFERENCIA_DA_PERGUNTA_INVALIDA = "Não sei qual pergunta recebeu o voto. Atualize a página e tente de novo."


def _preparar(conexao) -> None:
    """Cria a tabela das opiniões, se ainda não existir: uma linha por pessoa e por interação."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS opinioes_dos_agentes (
               tipo             TEXT NOT NULL,     -- o tipo da interação (ver o texto do alto)
               referencia       TEXT NOT NULL,     -- qual resposta, pergunta ou material recebeu o voto
               login            TEXT NOT NULL,     -- quem votou
               agente           TEXT NOT NULL,     -- agente_de_validacao, leitor, conferidor ou endomarketing
               perfil           TEXT NOT NULL,     -- EMPRESA ou BANCO
               empresa_id       TEXT NOT NULL,     -- a empresa da interação (a do envio ou a do material)
               processamento_id TEXT,              -- o envio da interação (vazio no material)
               voto             TEXT NOT NULL,     -- para_cima ou para_baixo
               comentario       TEXT,              -- opcional, só no para_baixo
               origem           TEXT NOT NULL,     -- tela ou carga sintética
               criado_em        TEXT NOT NULL,     -- quando a pessoa votou a primeira vez
               atualizado_em    TEXT NOT NULL,     -- quando o voto que vale foi dado (a data que a satisfação conta)
               PRIMARY KEY (tipo, referencia, login)
           )"""
    )


def _agora() -> str:
    """Data e hora atuais (UTC), em texto. Ex.: "2026-09-30T17:40:00+00:00"."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _numero_inteiro(texto: str) -> int | None:
    """O número escrito só com algarismos de 0 a 9, ou None. Ex.: "12" → 12; "-1", "1.5" e "" → None."""
    # isascii evita os algarismos de outras escritas (ex.: "²"), que isdigit aceitaria
    if texto.isascii() and texto.isdigit():
        return int(texto)
    return None


# ---------------- Qual interação recebeu o voto ----------------

def _envio_da_chave(chave: str) -> str:
    """O envio de uma chave de conversa.

    Ex.: "a1b2|CPF_INVALIDO|8|cpf" → "a1b2"; "grupo|a1b2|estado_civil|casdo" → "a1b2" (a conversa de um grupo começa
    com "grupo|", e o envio vem logo depois).
    """
    partes = chave.split("|")
    # A conversa de um grupo: o envio é o segundo pedaço
    if chave.startswith(conversas_das_pendencias.PREFIXO_DO_GRUPO):
        return partes[1]
    # A conversa de uma pessoa: o envio é o primeiro pedaço
    return partes[0]


def _interacao_da_conversa(conexao, empresa_id: str, referencia: str) -> dict:
    """Confere a resposta do Agente de validação que recebe o voto e diz de quem ela é.

    Recebe: empresa_id — o da sessão; referencia — "<chave da conversa>|<posição do balão>".
    Devolve: {agente, empresa_id, processamento_id}.
    Levanta ValueError (a referência não traz a posição, ou o balão não é uma resposta do agente) ou KeyError (o envio
    é de outra empresa, ou a resposta não existe).
    """
    # A posição do balão vem depois da última barra (a chave da conversa também tem barras)
    if "|" not in referencia:
        raise ValueError(REFERENCIA_DA_RESPOSTA_INVALIDA)
    chave, ordem_em_texto = referencia.rsplit("|", 1)
    ordem = _numero_inteiro(ordem_em_texto)
    if ordem is None:
        raise ValueError(REFERENCIA_DA_RESPOSTA_INVALIDA)
    processamento_id = _envio_da_chave(chave)
    # O envio precisa ser da empresa de quem vota (o de outra empresa é "não encontrado", sem dizer se existe)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    balao = conversas_das_pendencias.balao_guardado(conexao, processamento_id, chave, ordem)
    # Nenhum balão guardado nessa posição
    if balao is None:
        raise KeyError(referencia)
    # Só a resposta do agente recebe o voto: nem a fala da pessoa, nem o aviso de erro, nem a pergunta que abre o cartão
    if balao["quem"] != QUEM_E_O_AGENTE or balao["pergunta"]:
        raise ValueError("Só as respostas do agente recebem o joinha.")
    return {"agente": "agente_de_validacao", "empresa_id": empresa_id, "processamento_id": processamento_id}


def agente_da_pergunta(texto: str) -> str:
    """Qual agente fez uma pergunta da leitura: o Conferidor, cuja pergunta começa sempre do mesmo jeito, ou o Leitor.

    Recebe: o texto da pergunta. Devolve: "conferidor" ou "leitor".
    Ex.: "Confira este valor: no documento está ..." → "conferidor"; "Não achei o CPF de Beatriz..." → "leitor".
    As perguntas que a conferência por regra faz junto com a leitura (ex.: um CPF com dígito errado) contam como do
    Leitor: é a leitura dele que a empresa confere.
    """
    # O começo de hoje e o da primeira versão do Conferidor (as perguntas dos envios antigos)
    for comeco in (conferidor_da_leitura.INICIO_DA_PERGUNTA, conferidor_da_leitura.INICIO_DA_PERGUNTA_DA_V1):
        if texto.startswith(comeco):
            return "conferidor"
    return "leitor"


def _interacao_da_pergunta(conexao, empresa_id: str, referencia: str) -> dict:
    """Confere a pergunta da leitura que recebe o voto e diz de quem ela é (o Leitor ou o Conferidor).

    Recebe: empresa_id — o da sessão; referencia — "<envio>|<linha>|<campo ou PESSOA>".
    Devolve: {agente, empresa_id, processamento_id}.
    Levanta ValueError (a referência fora do formato) ou KeyError (o envio é de outra empresa, ou a pergunta não
    existe).
    """
    partes = referencia.split("|")
    # Três pedaços, e a linha é um número
    if len(partes) != 3 or _numero_inteiro(partes[1]) is None:
        raise ValueError(REFERENCIA_DA_PERGUNTA_INVALIDA)
    processamento_id, linha_em_texto, campo = partes
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    # O envio precisa ser da empresa de quem vota
    if perfil is None:
        raise KeyError(processamento_id)
    # A pergunta guardada no envio com a mesma linha e o mesmo campo
    for pergunta in perfil.perguntas_da_ia:
        # A pergunta sobre a pessoa toda não tem campo: na referência, ela é "PESSOA"
        campo_da_pergunta = pergunta.get("campo") or PERGUNTA_SOBRE_A_PESSOA
        if pergunta["linha"] == int(linha_em_texto) and campo_da_pergunta == campo:
            return {"agente": agente_da_pergunta(pergunta["pergunta"]), "empresa_id": empresa_id,
                    "processamento_id": processamento_id}
    raise KeyError(referencia)


def _interacao_do_material(conexao, empresa_id: str, referencia: str) -> dict:
    """Confere o material do Endomarketing que recebe o voto: ele precisa ser da empresa aberta na tela.

    Recebe: empresa_id — a empresa do material (a do endereço); referencia — o código do material.
    Devolve: {agente, empresa_id, processamento_id (None: o material não é de um envio)}.
    Levanta KeyError (o material é de outra empresa, ou não existe).
    """
    # O material precisa existir e ser desta empresa (senão, KeyError: "não encontrado")
    endomarketing.obter(conexao, empresa_id, referencia)
    return {"agente": "endomarketing", "empresa_id": empresa_id, "processamento_id": None}


# ---------------- O voto ----------------

def _conferir_voto(voto: str | None) -> None:
    """Confere o voto: "para_cima", "para_baixo" ou None (retirar). Levanta ValueError se for outra coisa."""
    if voto is not None and voto not in VOTOS:
        raise ValueError("O voto é o joinha para cima ou para baixo.")


def _comentario_conferido(voto: str, comentario: str | None) -> str | None:
    """O comentário como fica guardado: só no joinha para baixo e sem espaços nas pontas. Vazio vira None.

    Recebe: voto; comentario — o que a pessoa escreveu (ou None). Devolve: o texto, ou None.
    Levanta ValueError se o texto passar de TAMANHO_MAXIMO_DO_COMENTARIO letras.
    Ex.: ("para_baixo", "  Não resolveu.  ") → "Não resolveu."; ("para_cima", "Ótimo") → None.
    """
    # O comentário é do joinha para baixo ("O que faltou?"): no para cima, não fica
    if voto != PARA_BAIXO or comentario is None:
        return None
    texto = comentario.strip()
    # Só espaços: nada a guardar
    if not texto:
        return None
    if len(texto) > TAMANHO_MAXIMO_DO_COMENTARIO:
        raise ValueError(f"O comentário pode ter até {TAMANHO_MAXIMO_DO_COMENTARIO} letras.")
    return texto


def gravar(conexao, opiniao: dict) -> None:
    """Grava uma opinião. Na primeira vez, é uma linha nova; depois, troca o voto, o comentário e a data do voto (sem
    somar dois).

    Recebe: opiniao — {tipo, referencia, login, agente, perfil, empresa_id, processamento_id, voto, comentario, origem,
    quando (a data e a hora do voto, em texto ISO)}.
    Devolve: nada. Não faz commit: quem chama decide (um voto da tela, ou a carga inteira dos dados de demonstração).
    """
    # "ON CONFLICT ... DO UPDATE": se a pessoa já votou nesta interação, a linha dela é atualizada (SQLite e PostgreSQL)
    conexao.execute(
        "INSERT INTO opinioes_dos_agentes (tipo, referencia, login, agente, perfil, empresa_id, processamento_id, voto, "
        "comentario, origem, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (tipo, referencia, login) DO UPDATE SET voto = excluded.voto, "
        "comentario = excluded.comentario, atualizado_em = excluded.atualizado_em",
        (opiniao["tipo"], opiniao["referencia"], opiniao["login"], opiniao["agente"], opiniao["perfil"],
         opiniao["empresa_id"], opiniao["processamento_id"], opiniao["voto"], opiniao["comentario"],
         opiniao["origem"], opiniao["quando"], opiniao["quando"]))


def _opiniao_para_a_tela(tipo: str, referencia: str, agente: str, voto: str | None, comentario: str | None) -> dict:
    """A opinião como a tela recebe: {tipo, referencia, agente, nome_do_agente, voto, comentario}."""
    return {"tipo": tipo, "referencia": referencia, "agente": agente, "nome_do_agente": AGENTES[agente]["nome"],
            "voto": voto, "comentario": comentario}


def _gravar_o_voto(conexao, usuario, tipo: str, referencia: str, interacao: dict, voto: str | None,
                   comentario: str | None) -> dict:
    """Grava (ou retira) o voto da pessoa numa interação já conferida e devolve a opinião que vale agora.

    Recebe: usuario — o da sessão; tipo e referencia — a interação; interacao — {agente, empresa_id,
    processamento_id}; voto — "para_cima", "para_baixo" ou None (retirar); comentario — opcional.
    """
    _preparar(conexao)
    # Retirar o voto: a linha sai, e a interação volta a ficar sem a opinião desta pessoa
    if voto is None:
        conexao.execute("DELETE FROM opinioes_dos_agentes WHERE tipo = ? AND referencia = ? AND login = ?",
                        (tipo, referencia, usuario.login))
        conexao.commit()
        return _opiniao_para_a_tela(tipo, referencia, interacao["agente"], None, None)
    comentario_guardado = _comentario_conferido(voto, comentario)
    gravar(conexao, {"tipo": tipo, "referencia": referencia, "login": usuario.login, "agente": interacao["agente"],
                     "perfil": usuario.perfil.value, "empresa_id": interacao["empresa_id"],
                     "processamento_id": interacao["processamento_id"], "voto": voto,
                     "comentario": comentario_guardado, "origem": ORIGEM_DA_TELA, "quando": _agora()})
    conexao.commit()
    return _opiniao_para_a_tela(tipo, referencia, interacao["agente"], voto, comentario_guardado)


def votar_como_empresa(conexao, usuario, tipo: str, referencia: str, voto: str | None,
                       comentario: str | None = None) -> dict:
    """O voto de uma pessoa da empresa numa resposta da conversa ou numa pergunta da leitura.

    Recebe: usuario — o da sessão (perfil EMPRESA, com a empresa dele); tipo — "resposta_da_conversa" ou
    "pergunta_da_leitura"; referencia — qual interação (ver o texto do alto); voto — "para_cima", "para_baixo" ou None
    (retira o voto); comentario — opcional, só no para baixo.
    Devolve: a opinião que vale agora, {tipo, referencia, agente, nome_do_agente, voto, comentario}.
    Levanta ValueError (tipo, voto, referência ou comentário fora da regra) ou KeyError (a interação é de outra empresa,
    ou não existe).
    """
    _conferir_voto(voto)
    # Cada tipo tem a sua conferência: a resposta guardada na conversa, ou a pergunta guardada no envio
    if tipo == TIPO_RESPOSTA_DA_CONVERSA:
        interacao = _interacao_da_conversa(conexao, usuario.empresa_id, referencia)
    elif tipo == TIPO_PERGUNTA_DA_LEITURA:
        interacao = _interacao_da_pergunta(conexao, usuario.empresa_id, referencia)
    else:
        raise ValueError("No Portal Empresa, o joinha vale para as respostas da conversa e as perguntas da leitura.")
    return _gravar_o_voto(conexao, usuario, tipo, referencia, interacao, voto, comentario)


def votar_como_banco(conexao, usuario, empresa_id: str, tipo: str, referencia: str, voto: str | None,
                     comentario: str | None = None) -> dict:
    """O voto do especialista do banco num material que o Agente de Endomarketing escreveu para uma empresa.

    Recebe: usuario — o da sessão (perfil BANCO); empresa_id — a empresa do material; tipo —
    "material_do_endomarketing"; referencia — o código do material; voto e comentario — como em votar_como_empresa.
    Devolve: a opinião que vale agora. Levanta ValueError (tipo, voto ou comentário fora da regra) ou KeyError (o
    material é de outra empresa, ou não existe).
    """
    _conferir_voto(voto)
    # No Portal Interno, só o material do Endomarketing recebe o joinha
    if tipo != TIPO_MATERIAL_DO_ENDOMARKETING:
        raise ValueError("No Portal Interno, o joinha vale para os materiais do Endomarketing.")
    interacao = _interacao_do_material(conexao, empresa_id, referencia)
    return _gravar_o_voto(conexao, usuario, tipo, referencia, interacao, voto, comentario)


# ---------------- As opiniões de quem está na tela (para marcar os joinhas já dados) ----------------

def _opinioes_da_consulta(consulta) -> list[dict]:
    """As linhas (tipo, referencia, agente, voto, comentario) no formato da tela."""
    opinioes = []
    for tipo, referencia, agente, voto, comentario in consulta:
        opinioes.append(_opiniao_para_a_tela(tipo, referencia, agente, voto, comentario))
    return opinioes


def opinioes_do_envio(conexao, usuario, processamento_id: str) -> list[dict]:
    """As opiniões desta pessoa nas respostas e nas perguntas de um envio da empresa dela (a tela marca os joinhas).

    Recebe: usuario — o da sessão (perfil EMPRESA); processamento_id — o envio.
    Devolve: [{tipo, referencia, agente, nome_do_agente, voto, comentario}]. Só as desta pessoa: o voto de um colega do
    RH é dele. Levanta KeyError se o envio é de outra empresa (ou não existe).
    """
    # O envio precisa ser da empresa de quem pede
    if processamentos.obter_da_empresa(conexao, processamento_id, usuario.empresa_id) is None:
        raise KeyError(processamento_id)
    _preparar(conexao)
    consulta = conexao.execute(
        "SELECT tipo, referencia, agente, voto, comentario FROM opinioes_dos_agentes WHERE login = ? "
        "AND empresa_id = ? AND processamento_id = ? ORDER BY criado_em, rowid",
        (usuario.login, usuario.empresa_id, processamento_id))
    return _opinioes_da_consulta(consulta)


def opinioes_dos_materiais(conexao, usuario, empresa_id: str) -> list[dict]:
    """As opiniões deste especialista nos materiais do Endomarketing de uma empresa (a tela marca os joinhas).

    Recebe: usuario — o da sessão (perfil BANCO); empresa_id — a empresa aberta na aba.
    Devolve: [{tipo, referencia, agente, nome_do_agente, voto, comentario}].
    """
    _preparar(conexao)
    consulta = conexao.execute(
        "SELECT tipo, referencia, agente, voto, comentario FROM opinioes_dos_agentes WHERE login = ? AND tipo = ? "
        "AND empresa_id = ? ORDER BY criado_em, rowid", (usuario.login, TIPO_MATERIAL_DO_ENDOMARKETING, empresa_id))
    return _opinioes_da_consulta(consulta)


# ---------------- Os números do Acompanhamento dos agentes (só agregados) ----------------

def _dia_em_brasilia(momento: datetime) -> date:
    """O dia de um momento no horário de Brasília. Ex.: 28/09/2026 às 01h no horário universal → 27/09/2026."""
    return momento.astimezone(FUSO_DE_BRASILIA).date()


def _segunda_feira(dia: date) -> date:
    """A segunda-feira da semana de um dia. Ex.: quarta, 30/09/2026 → segunda, 28/09/2026."""
    # weekday(): segunda = 0, terça = 1... domingo = 6
    return dia - timedelta(days=dia.weekday())


def _semanas_da_tendencia(ultimo_dia: date) -> list:
    """As segundas-feiras das SEMANAS_DA_TENDENCIA semanas que terminam na semana do último dia, da mais antiga para
    a mais nova. Ex.: último dia 30/09/2026 → 13/07/2026, 20/07/2026, ..., 28/09/2026."""
    semana_do_ultimo_dia = _segunda_feira(ultimo_dia)
    semanas = []
    # Da mais antiga (11 semanas antes) até a do último dia
    for semanas_antes in range(SEMANAS_DA_TENDENCIA - 1, -1, -1):
        semanas.append(semana_do_ultimo_dia - timedelta(weeks=semanas_antes))
    return semanas


def _data_do_periodo(texto: str, qual: str) -> date | None:
    """Uma ponta do período, como a tela manda: "AAAA-MM-DD" vira a data; vazio é "sem limite" (None).

    Recebe: texto — a data; qual — "de começo" ou "de fim", para a frase do erro.
    Levanta ValueError se a data não existe ou não está no formato. Ex.: "2026-09-30" → date(2026, 9, 30).
    """
    if texto == "":
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise ValueError(f"A data {qual} do período não é uma data certa (AAAA-MM-DD).") from None


def _satisfacao(para_cima: int, votos: int) -> float | None:
    """A % de joinha para cima, com uma casa decimal, ou None sem voto (nunca um zero inventado).

    Ex.: (41, 50) → 82.0; (2, 3) → 66.7; (0, 0) → None.
    """
    if votos == 0:
        return None
    return round(100 * para_cima / votos, 1)


def _contagem_vazia() -> dict:
    """Uma contagem zerada: {votos, para_cima, para_baixo, com_comentario}."""
    return {"votos": 0, "para_cima": 0, "para_baixo": 0, "com_comentario": 0}


def _contar(contagem: dict, voto: str, tem_comentario: bool) -> None:
    """Soma um voto na contagem (e o comentário, se houver)."""
    contagem["votos"] = contagem["votos"] + 1
    if voto == PARA_CIMA:
        contagem["para_cima"] = contagem["para_cima"] + 1
    else:
        contagem["para_baixo"] = contagem["para_baixo"] + 1
    if tem_comentario:
        contagem["com_comentario"] = contagem["com_comentario"] + 1


def _com_satisfacao(contagem: dict) -> dict:
    """A contagem com a satisfação calculada: {votos, para_cima, para_baixo, com_comentario, satisfacao}."""
    resultado = dict(contagem)
    resultado["satisfacao"] = _satisfacao(contagem["para_cima"], contagem["votos"])
    return resultado


def satisfacao_dos_agentes(conexao, de: str = "", ate: str = "", agora: datetime | None = None) -> dict:
    """Os números da opinião sobre os agentes, para a tela Acompanhamento dos agentes do banco. Só agregados: nenhum
    login, nenhum texto de comentário e nenhuma interação aparecem aqui.

    Recebe: de e ate — o período escolhido no alto da tela, em datas AAAA-MM-DD de Brasília, com as duas pontas
    dentro ("" = sem limite daquele lado, como no "Tudo"); agora — o momento da conta (os testes informam; padrão:
    agora).
    Devolve: {periodo: {de, ate}, semanas: ["2026-07-13", ...], total: {votos, para_cima, para_baixo, com_comentario,
    satisfacao}, agentes: [{agente, nome, o_que_faz, votos, para_cima, para_baixo, com_comentario, satisfacao,
    tendencia: [{semana, votos, para_cima, satisfacao}], comparacao: {no_comeco, no_fim, votos_no_comeco,
    votos_no_fim, diferenca}}]}.
    O período vale para os números de cada agente e para o total. A tendência mostra as SEMANAS_DA_TENDENCIA semanas
    que terminam na semana do fim do período (sem fim, na semana de hoje), cada uma pela segunda-feira, em Brasília. A
    satisfação é a % de joinha para cima, ou None sem voto. Levanta ValueError se uma data não é certa ou se o começo
    vem depois do fim.
    """
    dia_de_comeco = _data_do_periodo(de, "de começo")
    dia_de_fim = _data_do_periodo(ate, "de fim")
    if dia_de_comeco is not None and dia_de_fim is not None and dia_de_comeco > dia_de_fim:
        raise ValueError("A data de começo do período vem depois da data de fim.")
    _preparar(conexao)
    # A tendência termina na semana do fim do período (ou na de hoje)
    ultimo_dia = dia_de_fim or _dia_em_brasilia(agora or datetime.now(timezone.utc))
    semanas = _semanas_da_tendencia(ultimo_dia)
    # A contagem do período e a de cada semana, por agente
    contagens = {}
    por_semana = {}
    for agente in AGENTES:
        contagens[agente] = _contagem_vazia()
        por_semana[agente] = {}
        for semana in semanas:
            por_semana[agente][semana] = _contagem_vazia()
    total = _contagem_vazia()
    # Cada voto guardado: o agente, o voto, se tem comentário e a data do voto que vale
    consulta = conexao.execute("SELECT agente, voto, CASE WHEN comentario IS NULL THEN 0 ELSE 1 END, atualizado_em "
                               "FROM opinioes_dos_agentes")
    for agente, voto, tem_comentario, atualizado_em in consulta:
        # Um agente que a tela não mostra: não conta
        if agente not in AGENTES:
            continue
        dia_do_voto = _dia_em_brasilia(datetime.fromisoformat(atualizado_em))
        # Dentro do período (as duas pontas contam): conta no agente e no total
        depois_do_comeco = dia_de_comeco is None or dia_do_voto >= dia_de_comeco
        antes_do_fim = dia_de_fim is None or dia_do_voto <= dia_de_fim
        if depois_do_comeco and antes_do_fim:
            _contar(contagens[agente], voto, bool(tem_comentario))
            _contar(total, voto, bool(tem_comentario))
        # Numa das semanas da tendência: conta na semana
        semana = _segunda_feira(dia_do_voto)
        if semana in por_semana[agente]:
            _contar(por_semana[agente][semana], voto, bool(tem_comentario))
    return {"periodo": {"de": de, "ate": ate}, "semanas": _semanas_em_texto(semanas),
            "total": _com_satisfacao(total), "agentes": _agentes_para_a_tela(contagens, por_semana, semanas)}


def _semanas_em_texto(semanas: list) -> list[str]:
    """As segundas-feiras em texto ISO. Ex.: [date(2026, 9, 28)] → ["2026-09-28"]."""
    textos = []
    for semana in semanas:
        textos.append(semana.isoformat())
    return textos


def _contagem_das_semanas(semanas: list[dict]) -> tuple[int, int]:
    """Os votos de várias semanas juntas: (votos, para_cima), somados (e não a média das porcentagens).

    Ex.: uma semana com 1 de 1 e outra com 3 de 9 → (10, 4), ou seja, 40% (a média das porcentagens daria 66,7%).
    """
    para_cima = 0
    votos = 0
    for semana in semanas:
        para_cima = para_cima + semana["para_cima"]
        votos = votos + semana["votos"]
    return votos, para_cima


def _comparacao_da_tendencia(tendencia: list[dict]) -> dict:
    """A satisfação das primeiras semanas da tendência contra a das últimas.

    Recebe: a tendência de um agente (as semanas da mais antiga para a de agora).
    Devolve: {no_comeco, no_fim, votos_no_comeco, votos_no_fim, diferenca}: a satisfação e os votos das
    SEMANAS_DA_COMPARACAO primeiras semanas e das últimas (a satisfação é None sem voto naquela ponta) e a diferença em
    pontos, com uma casa decimal. A diferença é None quando uma das pontas tem menos de MINIMO_DE_VOTOS_PARA_COMPARAR
    votos: com poucos votos, a diferença seria obra do acaso.
    Ex.: 74% em 20 votos nas 4 primeiras semanas e 86% em 30 votos nas 4 últimas → diferenca 12.0.
    Por que juntar 4 semanas: uma semana com 2 votos, sozinha, pareceria uma virada.
    """
    votos_no_comeco, para_cima_no_comeco = _contagem_das_semanas(tendencia[:SEMANAS_DA_COMPARACAO])
    votos_no_fim, para_cima_no_fim = _contagem_das_semanas(tendencia[-SEMANAS_DA_COMPARACAO:])
    no_comeco = _satisfacao(para_cima_no_comeco, votos_no_comeco)
    no_fim = _satisfacao(para_cima_no_fim, votos_no_fim)
    diferenca = None
    # Só dá para comparar com votos bastantes nas duas pontas
    pontas_com_votos_bastantes = (votos_no_comeco >= MINIMO_DE_VOTOS_PARA_COMPARAR
                                  and votos_no_fim >= MINIMO_DE_VOTOS_PARA_COMPARAR)
    if pontas_com_votos_bastantes:
        diferenca = round(no_fim - no_comeco, 1)
    return {"no_comeco": no_comeco, "no_fim": no_fim, "votos_no_comeco": votos_no_comeco,
            "votos_no_fim": votos_no_fim, "diferenca": diferenca}


def _agentes_para_a_tela(contagens: dict, por_semana: dict, semanas: list) -> list[dict]:
    """Cada agente, na ordem de AGENTES, com os números do período, a tendência semana a semana e a comparação das
    pontas da tendência."""
    agentes = []
    for agente, descricao in AGENTES.items():
        tendencia = []
        for semana in semanas:
            contagem_da_semana = por_semana[agente][semana]
            tendencia.append({"semana": semana.isoformat(), "votos": contagem_da_semana["votos"],
                              "para_cima": contagem_da_semana["para_cima"],
                              "satisfacao": _satisfacao(contagem_da_semana["para_cima"],
                                                        contagem_da_semana["votos"])})
        numeros = _com_satisfacao(contagens[agente])
        numeros.update({"agente": agente, "nome": descricao["nome"], "o_que_faz": descricao["o_que_faz"],
                        "tendencia": tendencia, "comparacao": _comparacao_da_tendencia(tendencia)})
        agentes.append(numeros)
    return agentes


# ---------------- Os dados de demonstração (scripts/gerar_opinioes_dos_agentes.py) ----------------

def remover_carga_sintetica(conexao) -> int:
    """Tira só as opiniões da carga sintética (as de demonstração). Devolve quantas saíram.

    Os votos dados na tela ficam: a origem separa os dois.
    """
    _preparar(conexao)
    cursor = conexao.execute("DELETE FROM opinioes_dos_agentes WHERE origem = ?", (ORIGEM_DA_CARGA_SINTETICA,))
    conexao.commit()
    return cursor.rowcount


def quantas_da_carga_sintetica(conexao) -> int:
    """Quantas opiniões da carga sintética o banco tem (0 antes da carga)."""
    _preparar(conexao)
    return conexao.execute("SELECT COUNT(*) FROM opinioes_dos_agentes WHERE origem = ?",
                           (ORIGEM_DA_CARGA_SINTETICA,)).fetchone()[0]
