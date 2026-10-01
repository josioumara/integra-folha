"""As idas e voltas de um envio com o banco, em frases simples, para as duas telas (ADR-121).

Para que serve: quando o banco devolve (o envio inteiro ou só algumas pessoas), o envio vai e volta entre a empresa e
o banco. A linha do tempo mostra só onde o envio está agora (ela anda sempre para a frente). Este arquivo conta a
história inteira, uma linha por rodada, e é o mesmo texto no Portal da empresa (Acompanhar cadastros) e no Portal
Interno (Envios):
    - 28/09 às 10h10 · 1º envio ao banco
    - 28/09 às 14h32 · O banco aprovou 33 pessoas e devolveu 2 (Ana Souza: Confirmar o salário; João Lima: CPF incorreto)
    - 29/09 às 09h05 · 2º envio ao banco (as pessoas devolvidas)
    - 29/09 às 11h40 · O banco aprovou 2 pessoas

Uma FAMÍLIA de envios é o envio que a empresa mandou mais os envios de devolução que nasceram dele (e os que nasceram
destes, se o banco devolver de novo). Todos mostram a mesma história.

Também ficam aqui duas contas que as telas usam:
    - quantas pessoas do envio de origem já foram aprovadas, somando as rodadas ("33 de 35 aprovadas · 2 devolvidas");
    - o que a empresa respondeu a cada apontamento do banco (o que o especialista lê quando o envio volta).
"""
from datetime import datetime

from models.contratos import EstadoProcessamento
from services import apontamentos_do_banco, auditoria, correcoes, homologacao, normalizador, processamentos

# Os eventos da trilha de auditoria que contam a história com o banco
EVENTOS_DAS_IDAS_E_VOLTAS = ("ENVIADO_AO_BANCO", "DEVOLVIDO_PELO_BANCO", "APROVADO_PELO_BANCO", "DEVOLUCAO_ENCERRADA")


def data_curta(texto: str) -> str:
    """A data de um evento no jeito curto, no horário desta máquina: "2026-09-28T13:10:00+00:00" → "28/09"."""
    return datetime.fromisoformat(texto).astimezone().strftime("%d/%m")


def texto_de_pessoas(quantidade: int) -> str:
    """ "1 pessoa" ou "2 pessoas": o número com a palavra no singular ou no plural."""
    if quantidade == 1:
        return "1 pessoa"
    return str(quantidade) + " pessoas"


def envio_raiz(conexao, processamento_id: str):
    """O primeiro envio da família: sobe pelos envios de origem até o envio que a empresa mandou.

    Recebe: conexao; processamento_id (qualquer envio da família). Devolve: o retrato do envio raiz.
    """
    perfil = processamentos.obter(conexao, processamento_id)
    # Sobe enquanto o envio veio de outro (o envio de devolução de um envio de devolução também sobe até o começo)
    while perfil.envio_de_origem:
        perfil = processamentos.obter(conexao, perfil.envio_de_origem)
    return perfil


def envios_de_devolucao(conexao, perfil) -> list:
    """Os envios de devolução que nasceram diretamente de um envio (os "filhos" dele), do mais antigo ao mais novo.

    Recebe: conexao; perfil (o retrato do envio). Devolve: a lista de retratos.
    """
    filhos = []
    for outro in processamentos.listar(conexao, perfil.empresa_id):
        if outro.envio_de_origem == perfil.processamento_id:
            filhos.append(outro)
    # listar vem do mais recente para o mais antigo: aqui a ordem é a das rodadas
    filhos.reverse()
    return filhos


def familia(conexao, processamento_id: str) -> list:
    """O envio raiz e todos os envios de devolução que nasceram dele, em qualquer nível.

    Recebe: conexao; processamento_id (qualquer envio da família). Devolve: a lista de retratos, a raiz primeiro.
    """
    raiz = envio_raiz(conexao, processamento_id)
    envios = [raiz]
    # Percorre a lista enquanto ela cresce: cada envio pode ter os seus filhos
    posicao = 0
    while posicao < len(envios):
        for filho in envios_de_devolucao(conexao, envios[posicao]):
            envios.append(filho)
        posicao = posicao + 1
    return envios


def _nomes_por_linha(conexao, processamento_id: str) -> dict[int, str]:
    """O nome de cada pessoa do envio pela linha dela no arquivo, como o envio foi padronizado (inclui quem saiu depois).

    Recebe: conexao; processamento_id. Devolve: {linha: nome}. Exemplo: {12: "Ana Souza"}.
    """
    nomes = {}
    padronizacao = normalizador.obter(conexao, processamento_id)
    if padronizacao is None:
        return nomes
    for registro in padronizacao.registros:
        nomes[registro["_linha"]] = registro.get("nome_completo") or ("Funcionário da linha " + str(registro["_linha"]))
    return nomes


def _quem_foi_devolvido(conexao, envio_de_devolucao) -> str:
    """As pessoas de um envio de devolução com o motivo do banco. Ex.: "Ana Souza: Confirmar o salário; João Lima: CPF".

    Recebe: conexao; envio_de_devolucao (o retrato). Devolve: o texto (vazio se não há apontamento).
    """
    nomes = _nomes_por_linha(conexao, envio_de_devolucao.processamento_id)
    partes = []
    for apontamento in apontamentos_do_banco.enviados(conexao, envio_de_devolucao.processamento_id):
        nome = nomes.get(apontamento["linha"], "Funcionário da linha " + str(apontamento["linha"]))
        partes.append(nome + ": " + apontamento["motivo_texto"])
    return "; ".join(partes)


def _aprovadas_no_evento(conexao, evento: dict) -> int:
    """Quantas pessoas o banco aprovou num evento de aprovação (eventos antigos não guardavam: lê a homologação)."""
    if "aprovadas" in evento["detalhe"]:
        return evento["detalhe"]["aprovadas"]
    homologado = homologacao.obter(conexao, evento["processamento_id"])
    if homologado is None:
        return 0
    return homologado["relatorio"]["registros_homologados"]


def _frase_do_evento(conexao, evento: dict, raiz_id: str, envios_ao_banco: int) -> dict | None:
    """Uma linha das idas e voltas a partir de um evento da trilha, ou None quando o evento não entra.

    Recebe: conexao; evento (da auditoria); raiz_id (o envio que a empresa mandou); envios_ao_banco (quantos envios ao
    banco a família já tinha, contando este, se ele for um envio). Devolve: {quando, tipo, texto} ou None.
    """
    tipo_do_evento = evento["tipo"]
    detalhe = evento["detalhe"]
    if tipo_do_evento == "ENVIADO_AO_BANCO":
        texto = str(envios_ao_banco) + "º envio ao banco"
        # O envio de devolução leva só as pessoas que tinham voltado
        if evento["processamento_id"] != raiz_id:
            texto = texto + " (as pessoas devolvidas)"
        return {"quando": evento["criado_em"], "tipo": "enviado", "texto": texto}
    if tipo_do_evento == "DEVOLVIDO_PELO_BANCO":
        # A devolução que cria o envio de devolução já está contada na aprovação em parte do envio de origem
        if detalhe.get("envio_de_origem"):
            return None
        return {"quando": evento["criado_em"], "tipo": "devolvido",
                "texto": "O banco devolveu o envio inteiro: \"" + detalhe.get("motivo", "") + "\""}
    if tipo_do_evento == "APROVADO_PELO_BANCO":
        aprovadas = _aprovadas_no_evento(conexao, evento)
        devolvidas = detalhe.get("devolvidas", 0)
        if not devolvidas:
            return {"quando": evento["criado_em"], "tipo": "aprovado",
                    "texto": "O banco aprovou " + texto_de_pessoas(aprovadas)}
        texto = "O banco aprovou " + texto_de_pessoas(aprovadas) + " e devolveu " + str(devolvidas)
        # Quem voltou e por quê: está no envio de devolução que nasceu desta aprovação
        perfil = processamentos.obter(conexao, evento["processamento_id"])
        for filho in envios_de_devolucao(conexao, perfil):
            quem = _quem_foi_devolvido(conexao, filho)
            if quem:
                texto = texto + " (" + quem + ")"
        return {"quando": evento["criado_em"], "tipo": "aprovado_em_parte", "texto": texto}
    # DEVOLUCAO_ENCERRADA: a empresa tirou todas as pessoas devolvidas (não volta ao banco)
    return {"quando": evento["criado_em"], "tipo": "encerrado",
            "texto": "A empresa tirou as pessoas devolvidas do envio: a devolução foi encerrada"}


def _teve_devolucao(eventos: list[dict]) -> bool:
    """True se o banco já devolveu algo nesta família (o envio inteiro ou algumas pessoas)."""
    for evento in eventos:
        if evento["tipo"] == "DEVOLVIDO_PELO_BANCO":
            return True
        if evento["tipo"] == "APROVADO_PELO_BANCO" and evento["detalhe"].get("devolvidas"):
            return True
    return False


def _data_do_evento(evento: dict) -> str:
    """A data do evento, para ordenar (o texto AAAA-MM-DD... ordena igual à data)."""
    return evento["criado_em"]


def idas_e_voltas(conexao, processamento_id: str) -> list[dict]:
    """A história do envio com o banco, uma linha por rodada, da mais antiga à mais nova.

    Recebe: conexao; processamento_id (qualquer envio da família). Devolve: [{quando, tipo, texto}], com tipo
    "enviado", "devolvido", "aprovado_em_parte", "aprovado" ou "encerrado". Lista vazia quando o banco nunca
    devolveu nada: um envio que foi e foi aprovado de primeira já está todo na linha do tempo.
    """
    envios = familia(conexao, processamento_id)
    raiz_id = envios[0].processamento_id
    # Os eventos que contam a história, de todos os envios da família
    eventos = []
    for perfil in envios:
        for evento in auditoria.eventos(conexao, perfil.processamento_id):
            if evento["tipo"] in EVENTOS_DAS_IDAS_E_VOLTAS:
                eventos.append(evento)
    if not _teve_devolucao(eventos):
        return []
    # Na ordem em que aconteceram (sort mantém a ordem da trilha quando dois eventos têm o mesmo segundo)
    eventos.sort(key=_data_do_evento)
    linhas = []
    envios_ao_banco = 0
    for evento in eventos:
        if evento["tipo"] == "ENVIADO_AO_BANCO":
            envios_ao_banco = envios_ao_banco + 1
        frase = _frase_do_evento(conexao, evento, raiz_id, envios_ao_banco)
        if frase is not None:
            linhas.append(frase)
    return linhas


def texto_da_origem(conexao, perfil) -> str | None:
    """A linha que diz de onde veio um envio de devolução. Ex.: "Devolução do envio de 28/09 (2 pessoas)".

    Recebe: conexao; perfil (o retrato do envio). Devolve: o texto, ou None se o envio não é de devolução.
    """
    if not perfil.envio_de_origem:
        return None
    criado_em = conexao.execute("SELECT criado_em FROM processamentos WHERE processamento_id = ?",
                                (perfil.envio_de_origem,)).fetchone()[0]
    return "Devolução do envio de " + data_curta(criado_em) + " (" + texto_de_pessoas(perfil.n_linhas) + ")"


def _pessoas_ainda_com_a_empresa(conexao, perfil) -> int:
    """Quantas pessoas de um envio de devolução ainda não foram aprovadas (0 se ele já foi aprovado ou encerrado)."""
    if perfil.status in (EstadoProcessamento.HOMOLOGADO, EstadoProcessamento.REJEITADO):
        return 0
    return len(correcoes.dados_atuais(conexao, perfil.processamento_id).registros)


def _homologadas_no_envio(conexao, perfil) -> int:
    """Quantas pessoas o banco já cadastrou por este envio (0 se ele ainda não foi aprovado)."""
    homologado = homologacao.obter(conexao, perfil.processamento_id)
    if homologado is None:
        return 0
    return homologado["relatorio"]["registros_homologados"]


def aprovacao_em_rodadas(conexao, perfil) -> dict | None:
    """A conta da etapa "Aprovação das contas enviadas" de um envio que o banco aprovou em parte.

    Recebe: conexao; perfil (o envio que a empresa mandou, já aprovado). Devolve: {detalhe, parcial}, ou None quando
    o banco não devolveu ninguém dele (a etapa fica como sempre). Exemplos:
        - logo depois da aprovação em parte: {"detalhe": "33 de 35 aprovadas · 2 devolvidas", "parcial": True};
        - depois de o banco aprovar as 2: {"detalhe": "35 de 35 aprovadas", "parcial": False};
        - se a empresa tirou 1 delas: {"detalhe": "34 de 35 aprovadas · 1 saiu do envio", "parcial": False}.
    """
    envios = familia(conexao, perfil.processamento_id)
    # Só quando nasceu algum envio de devolução deste envio
    if len(envios) == 1:
        return None
    # Aprovadas: somando o envio de origem e as rodadas seguintes
    aprovadas = 0
    ainda_com_a_empresa = 0
    for envio in envios:
        aprovadas = aprovadas + _homologadas_no_envio(conexao, envio)
        if envio.envio_de_origem:
            ainda_com_a_empresa = ainda_com_a_empresa + _pessoas_ainda_com_a_empresa(conexao, envio)
    # O total é o que o banco avaliou na primeira rodada: as aprovadas dela mais as devolvidas dela
    total = _homologadas_no_envio(conexao, envios[0])
    for filho in envios_de_devolucao(conexao, envios[0]):
        total = total + filho.n_linhas
    # Quem não foi aprovado nem está com a empresa saiu do envio ("Não cadastrar esta pessoa")
    sairam = total - aprovadas - ainda_com_a_empresa
    detalhe = str(aprovadas) + " de " + str(total) + " aprovadas"
    if ainda_com_a_empresa == 1:
        detalhe = detalhe + " · 1 devolvida"
    elif ainda_com_a_empresa > 1:
        detalhe = detalhe + " · " + str(ainda_com_a_empresa) + " devolvidas"
    if sairam == 1:
        detalhe = detalhe + " · 1 saiu do envio"
    elif sairam > 1:
        detalhe = detalhe + " · " + str(sairam) + " saíram do envio"
    return {"detalhe": detalhe, "parcial": ainda_com_a_empresa > 0}


def respostas_aos_apontamentos(conexao, processamento_id: str) -> list[dict]:
    """O que a empresa fez com cada apontamento do banco neste envio (o especialista lê na próxima avaliação).

    Recebe: conexao; processamento_id. Devolve: [{nome, motivo, recado, resposta}]. Exemplos de resposta:
    "A empresa corrigiu Valor renda: R$ 48.000,00 → R$ 4.800,00", "A empresa respondeu: \"Está certo assim\"",
    "A empresa tirou a pessoa do envio" ou "Ainda sem resposta da empresa".
    """
    # Importado aqui dentro: o acompanhamento também usa este arquivo (importar lá em cima faria um laço)
    from services import acompanhamento, validador
    nomes = _nomes_por_linha(conexao, processamento_id)
    # Os dados de hoje, pela linha (quem saiu do envio não está aqui)
    atuais_por_linha = {}
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        atuais_por_linha[registro["_linha"]] = registro
    respostas = []
    for apontamento in apontamentos_do_banco.enviados(conexao, processamento_id):
        linha = apontamento["linha"]
        campo = apontamento["campo"]
        registro = atuais_por_linha.get(linha)
        regra_id = validador.PREFIXO_DO_PEDIDO_DO_BANCO + apontamento["apontamento_id"]
        justificativa = apontamentos_do_banco.justificativa_da_empresa(conexao, processamento_id, regra_id, linha)
        if registro is None:
            resposta = "A empresa tirou a pessoa do envio"
        # A empresa trocou o valor (também o campo que estava em branco e ela preencheu)
        elif apontamentos_do_banco.empresa_mudou_o_valor(apontamento, registro):
            antes = acompanhamento.valor_lido_para_a_tela(campo, apontamento["valor_apontado"]) or "(vazio)"
            depois = acompanhamento.valor_lido_para_a_tela(campo, registro.get(campo)) or "(vazio)"
            resposta = "A empresa corrigiu " + acompanhamento.rotulo_do_campo(campo) + ": " + antes + " → " + depois
        elif justificativa:
            resposta = "A empresa respondeu: \"" + justificativa + "\""
        else:
            resposta = "Ainda sem resposta da empresa"
        respostas.append({"nome": nomes.get(linha, "Funcionário da linha " + str(linha)),
                          "motivo": apontamento["motivo_texto"], "recado": apontamento["recado"],
                          "resposta": resposta})
    return respostas
