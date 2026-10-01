"""Mapeamento de cada processamento: proposta da IA, reuso do que já foi aprovado e aceite humano.

- Inclusão com colunas já conhecidas reaproveita o mapeamento aprovado da empresa: sem chamar a IA e
  sem pedir aprovação de novo do que já foi aprovado (ADR-24). Só colunas novas vão para o LLM.
- A empresa aceita (ou corrige) o mapeamento com um clique; coluna AMBIGUO precisa de uma decisão (ADR-16).
- Na correção, o Assistente pode pedir ao Interpretador para rever UMA coluna (handoff, ADR-17).
- Coluna que a IA mandou DIVIDIR já chega dividida: cada parte vira uma coluna, ligada ao seu campo (ADR-104).
"""
from datetime import datetime, timezone

from agents import interpretador
from models.contratos import EstadoProcessamento, ItemMapeamento, MappingPlan, StatusMapeamento
from services import auditoria, divisao_da_coluna, parametros, processamentos

# Escolha da empresa para uma coluna que não deve entrar no layout
IGNORAR = "(ignorar coluna)"
# Quantas vezes o Assistente pode pedir remapeamento no mesmo arquivo (ADR-17: interação entre agentes tem limite)
LIMITE_HANDOFFS = 2


def _preparar(conexao) -> None:
    """Cria a tabela dos mapeamentos, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS mapeamentos (
               processamento_id TEXT PRIMARY KEY,
               empresa_id       TEXT NOT NULL,
               status           TEXT NOT NULL,      -- PENDENTE ou APROVADO
               plano            TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               aprovado_por     TEXT,
               aprovado_em      TEXT
           )"""
    )


def _agora() -> str:
    """Data e hora atuais (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def obter(conexao, processamento_id: str) -> tuple[MappingPlan, str] | None:
    """(plano, status) do processamento, ou None se ainda não foi interpretado."""
    _preparar(conexao)
    linha = conexao.execute("SELECT plano, status FROM mapeamentos WHERE processamento_id = ?",
                            (processamento_id,)).fetchone()
    if linha is None:
        return None
    plano_em_json, status = linha
    return MappingPlan.model_validate_json(plano_em_json), status


def ultimo_aprovado(conexao, empresa_id: str) -> MappingPlan | None:
    """O mapeamento mais recente da empresa num envio que o BANCO aprovou (base do reuso nas inclusões, ADR-24).

    Só conta envio HOMOLOGADO: o aceite da empresa sozinho não basta, porque o banco ainda pode devolver o envio.
    Assim, o aviso "as colunas são as de um envio que o banco já aprovou" é sempre verdadeiro.
    """
    _preparar(conexao)
    # Junta cada mapeamento aceito com o envio dele e fica só com os envios homologados (aprovados pelo banco)
    linha = conexao.execute(
        "SELECT mapeamentos.plano FROM mapeamentos JOIN processamentos "
        "ON processamentos.processamento_id = mapeamentos.processamento_id "
        "WHERE mapeamentos.empresa_id = ? AND mapeamentos.status = 'APROVADO' AND processamentos.status = ? "
        "ORDER BY mapeamentos.aprovado_em DESC LIMIT 1",
        (empresa_id, EstadoProcessamento.HOMOLOGADO.value)).fetchone()
    if linha is None:
        return None
    return MappingPlan.model_validate_json(linha[0])


def _colunas_conhecidas(conexao, empresa_id: str, nomes_dos_campos: set) -> dict:
    """Coluna -> item do último mapeamento aprovado da empresa, se o campo dele ainda existe no layout."""
    aprovado = ultimo_aprovado(conexao, empresa_id)
    conhecidas = {}
    if aprovado is None:
        return conhecidas
    for item in aprovado.itens:
        # Coluna ignorada (sem campo) também é reaproveitada
        if item.campo is None or item.campo in nomes_dos_campos:
            conhecidas[item.coluna] = item
    return conhecidas


def campo_lido_pelo_leitor(nome_da_coluna: str, origem: dict) -> str:
    """O campo do layout que o Leitor de Documentos leu numa coluna do texto corrido.

    Cada coluna é um rótulo do documento, e a origem diz o campo ({"campo": "cpf", "rotulo": ...}).
    Nos envios mais antigos, a coluna era o próprio campo (a origem não tinha "campo").
    Ex.: ("Documento fiscal", {"campo": "cpf", ...}) → "cpf"; ("cpf", {"rotulos": [...]}) → "cpf".
    """
    return origem.get("campo", nome_da_coluna)


def rotulos_da_origem(origem: dict) -> list[str]:
    """Os rótulos que a empresa usou, no formato novo (um rótulo por coluna) ou no antigo (vários por campo)."""
    if "campo" in origem:
        if origem.get("rotulo"):
            return [origem["rotulo"]]
        return []
    return list(origem.get("rotulos", []))


def _item_lido_do_documento(coluna: str, origem: dict, total_de_pessoas: int) -> ItemMapeamento:
    """O item do mapeamento de uma coluna que o Leitor de Documentos leu do texto corrido (ADR-73).

    A justificativa conta em quantas pessoas a empresa usou aquele jeito de chamar o dado. Sem rótulo, a IA achou o
    dado pelo lugar no texto (ex.: o nome logo abaixo do título).
    Ex.: coluna "Documento fiscal" do campo cpf → 'A IA leu este dado no seu documento (8 de 12 pessoas).'
    """
    pessoas = f"{origem.get('pessoas', 0)} de {total_de_pessoas} pessoas"
    if rotulos_da_origem(origem):
        justificativa = f"O Agente Leitor leu este dado no seu documento ({pessoas})."
    else:
        justificativa = f"O Agente Leitor achou este dado pelo lugar no texto, sem um rótulo ({pessoas})."
    campo = campo_lido_pelo_leitor(coluna, origem)
    return ItemMapeamento(coluna=coluna, campo=campo, status=StatusMapeamento.PROPOSTO, justificativa=justificativa,
                          origem="leitor")


def _candidatos_so_na_duvida(item: ItemMapeamento) -> ItemMapeamento:
    """O item da IA com os candidatos só quando a coluna ficou em dúvida (AMBIGUO); nos outros, a lista fica vazia.

    Por quê (ADR-143, Parte 1): depois do aceite, a coluna em dúvida só entre campos opcionais que ficou de fora é
    reconhecida pelos candidatos e é guardada sem rótulo (services/informacoes_sem_rotulo.py). A IA pode mandar
    candidatos também numa coluna que ela reconheceu com certeza: sem esta limpeza, essa coluna, se a empresa a deixasse
    de fora, seria guardada sem motivo (a trava da LGPD manda guardar só a dúvida da IA).
    Ex.: {status: PROPOSTO, campo: "cep_residencial", candidatos: ["cep_comercial"]} → os mesmos dados, candidatos [].
    """
    # A coluna em dúvida guarda os candidatos (a empresa escolhe entre eles); a que não traz nenhum fica como está
    if item.status == StatusMapeamento.AMBIGUO or not item.candidatos:
        return item
    return item.model_copy(update={"candidatos": []})


def interpretar_processamento(conexao, processamento_id: str, empresa_id: str, cliente=None,
                              configuracao: str = "B3", busca=None) -> MappingPlan:
    """Gera (ou refaz, enquanto pendente) a proposta de mapeamento do processamento."""
    _preparar(conexao)
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise KeyError(processamento_id)
    existente = obter(conexao, processamento_id)
    if existente and existente[1] == "APROVADO":
        raise ValueError("Este mapeamento já foi aprovado.")
    versao, campos = parametros.layout_ativo(conexao)
    nomes_dos_campos = set()
    for campo in campos:
        nomes_dos_campos.add(campo.campo)

    # Reuso: colunas com o mesmo nome no último mapeamento aprovado da empresa
    conhecidas = _colunas_conhecidas(conexao, empresa_id, nomes_dos_campos)
    # Texto corrido do Word: o Leitor de Documentos já leu o campo de cada coluna (cada coluna é um jeito de a empresa
    # chamar o dado, ADR-73). Não precisa chamar a IA do mapeamento de novo
    for coluna in perfil.colunas:
        origem = perfil.origem_das_colunas.get(coluna.nome)
        if origem is not None and campo_lido_pelo_leitor(coluna.nome, origem) in nomes_dos_campos:
            conhecidas[coluna.nome] = _item_lido_do_documento(coluna.nome, origem, perfil.n_linhas)
    novas = []
    for coluna in perfil.colunas:
        if coluna.nome not in conhecidas:
            novas.append(coluna)

    # Só as colunas novas vão para a IA
    item_da_ia, plano_da_ia = {}, None
    if novas:
        plano_da_ia = interpretador.interpretar(perfil, campos, versao, cliente or interpretador.cliente_padrao(),
                                                configuracao=configuracao, busca=busca, colunas=novas)
        for item in plano_da_ia.itens:
            # Só a coluna em dúvida guarda os candidatos que a IA indicou (ADR-143, Parte 1)
            item_da_ia[item.coluna] = _candidatos_so_na_duvida(item)
    # Junta tudo na ordem das colunas do arquivo
    itens = []
    for coluna in perfil.colunas:
        if coluna.nome in conhecidas and conhecidas[coluna.nome].origem == "leitor":
            item = conhecidas[coluna.nome]
        elif coluna.nome in conhecidas:
            item = conhecidas[coluna.nome].model_copy(update={
                "origem": "reuso", "justificativa": "Mesma coluna de um mapeamento já aprovado por vocês."})
        else:
            item = item_da_ia[coluna.nome]
        itens.append(item)

    # As colunas que a IA mandou dividir já chegam divididas (a empresa confere e pode pedir para refazer)
    itens = aplicar_divisoes_da_ia(conexao, processamento_id, itens)
    if plano_da_ia:
        modelo, observacoes = plano_da_ia.modelo, plano_da_ia.observacoes
    elif perfil.origem_das_colunas:
        modelo, observacoes = "leitor de documentos", []
    else:
        modelo, observacoes = "reuso", []
    plano = MappingPlan(processamento_id=processamento_id, versao_layout=versao, configuracao=configuracao,
                        modelo=modelo, versao_prompt=interpretador.VERSAO_PROMPT, itens=itens,
                        chamou_llm=bool(novas), observacoes=observacoes)
    # Grava ou substitui o plano, de novo pendente de aprovação ("ON CONFLICT": a mesma forma nos dois bancos)
    conexao.execute("INSERT INTO mapeamentos (processamento_id, empresa_id, status, plano, criado_em, aprovado_por, "
                    "aprovado_em) VALUES (?, ?, 'PENDENTE', ?, ?, NULL, NULL) "
                    "ON CONFLICT (processamento_id) DO UPDATE SET empresa_id = excluded.empresa_id, "
                    "status = excluded.status, plano = excluded.plano, criado_em = excluded.criado_em, "
                    "aprovado_por = NULL, aprovado_em = NULL",
                    (processamento_id, empresa_id, plano.model_dump_json(), _agora()))
    conexao.commit()
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.MAPEAMENTO_PENDENTE)
    # Quantas colunas ficaram em cada status (PROPOSTO, AMBIGUO, NAO_MAPEADO)
    quantidade_por_status = {}
    for status in StatusMapeamento:
        quantidade_por_status[status.value] = 0
    for item in itens:
        quantidade_por_status[item.status.value] += 1
    auditoria.registrar(conexao, processamento_id, empresa_id, "Interpretação", "MAPEAMENTO_PROPOSTO", {
        "configuracao": configuracao, "modelo": plano.modelo, "versao_prompt": plano.versao_prompt,
        "chamou_llm": plano.chamou_llm, "colunas_reusadas": len(perfil.colunas) - len(novas),
        "status": quantidade_por_status, "observacoes": len(plano.observacoes)})
    return plano


def aplicar_divisoes_da_ia(conexao, processamento_id: str, itens: list[ItemMapeamento]) -> list[ItemMapeamento]:
    """As colunas que a IA mandou DIVIDIR viram partes na tabela do envio e no plano (ADR-104).

    Recebe: o envio; os itens do plano. Devolve: os itens com as partes. A divisão roda pela regra em todas as linhas
    (services/divisao_da_coluna.py); se nenhuma linha der para dividir, a coluna fica de fora, com o motivo.
    """
    # As colunas a dividir
    colunas_a_dividir = []
    for item in itens:
        if item.status == StatusMapeamento.DIVIDIR:
            colunas_a_dividir.append(item)
    if not colunas_a_dividir:
        return itens
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    for item in colunas_a_dividir:
        # Uma leitura anterior do mesmo envio já tinha dividido esta coluna: as partes antigas saem antes
        divisao_da_coluna.tirar_partes_da_tabela(leitura, item.coluna)
        try:
            itens = divisao_da_coluna.aplicar(leitura, itens, item.coluna, item.divisao, "llm")
        except ValueError as erro:
            # Nada deu para dividir: a coluna fica de fora, e a empresa pode dividir pela tela
            itens = trocar_item(itens, item.model_copy(update={
                "status": StatusMapeamento.NAO_MAPEADO, "divisao": None,
                "justificativa": f"O Agente Interpretador propôs dividir esta coluna, mas não deu: {erro}"}))
    processamentos.guardar_tabela_do_envio(conexao, processamento_id, leitura)
    return itens


def trocar_item(itens: list[ItemMapeamento], item_novo: ItemMapeamento) -> list[ItemMapeamento]:
    """Os itens com o da mesma coluna trocado pelo novo."""
    novos_itens = []
    for item in itens:
        if item.coluna == item_novo.coluna:
            novos_itens.append(item_novo)
        else:
            novos_itens.append(item)
    return novos_itens


def obrigatorios_sem_coluna(conexao, plano: MappingPlan) -> list[str]:
    """Campos obrigatórios do layout que nenhuma coluna alimenta."""
    _, campos = parametros.layout_ativo(conexao)
    campos_usados = set()
    for item in plano.itens:
        if item.status == StatusMapeamento.PROPOSTO:
            campos_usados.add(item.campo)
    faltando = []
    for campo in campos:
        if campo.obrigatorio and campo.campo not in campos_usados:
            faltando.append(campo.campo)
    return faltando


def regravar_plano_pendente(conexao, processamento_id: str, plano: MappingPlan) -> None:
    """Regrava o plano ainda à espera do aceite (ex.: a empresa dividiu uma coluna em partes). Aprovado não muda."""
    atual = obter(conexao, processamento_id)
    if atual is None or atual[1] != "PENDENTE":
        raise ValueError("As colunas só mudam antes do aceite.")
    conexao.execute("UPDATE mapeamentos SET plano = ? WHERE processamento_id = ?",
                    (plano.model_dump_json(), processamento_id))
    conexao.commit()


def _colunas_por_campo(itens: list[ItemMapeamento]) -> dict[str, list[str]]:
    """{campo: [colunas]} só dos campos que recebem mais de uma coluna."""
    colunas_por_campo = {}
    for item in itens:
        if item.campo:
            colunas_por_campo.setdefault(item.campo, []).append(item.coluna)
    repetidos = {}
    for campo, colunas in colunas_por_campo.items():
        if len(colunas) > 1:
            repetidos[campo] = colunas
    return repetidos


def _colunas_que_se_cruzam(leitura, colunas: list[str]) -> bool:
    """True se alguma linha tem valor em mais de uma destas colunas (aí não dá para saber qual vale)."""
    posicoes = []
    for coluna in colunas:
        posicoes.append(leitura.cabecalhos.index(coluna))
    for linha in leitura.linhas:
        preenchidas = 0
        for posicao in posicoes:
            if linha[posicao].strip():
                preenchidas += 1
        if preenchidas > 1:
            return True
    return False


def _conferir_colunas_repetidas(conexao, processamento_id: str, perfil, itens: list[ItemMapeamento]) -> None:
    """Recusa (ValueError) mais de uma coluna no mesmo campo, com uma exceção: o Word em texto corrido.

    No texto corrido, cada coluna é um jeito de a empresa chamar o dado ("Admissão", "Data de entrada"), e cada pessoa
    usou um só: as colunas se completam. Só é recusado quando uma MESMA pessoa tem valor nas duas (qual vale?).
    """
    repetidos = _colunas_por_campo(itens)
    if not repetidos:
        return
    # Planilha: um campo, uma coluna
    if not perfil.origem_das_colunas:
        raise ValueError("Mais de uma coluna para o mesmo campo: " + ", ".join(sorted(repetidos)))
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    for campo, colunas in sorted(repetidos.items()):
        if _colunas_que_se_cruzam(leitura, colunas):
            nomes = []
            for coluna in colunas:
                nomes.append(f"\"{coluna}\"")
            raise ValueError(f"{' e '.join(nomes)} têm valor na mesma pessoa e iriam para o mesmo campo ({campo}). "
                             "Escolha outro campo para uma delas.")


def aprovar(conexao, processamento_id: str, empresa_id: str, escolhas: dict[str, str | None],
            usuario: str) -> MappingPlan:
    """Aplica as decisões da empresa e aprova. escolhas: coluna -> campo, IGNORAR ou None (não decidido).

    Coluna sem escolha fica como a IA propôs; AMBIGUO sem escolha impede a aprovação.
    """
    atual = obter(conexao, processamento_id)
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if atual is None or perfil is None:
        raise KeyError(processamento_id)
    plano, status = atual
    if status == "APROVADO":
        raise ValueError("Este mapeamento já foi aprovado.")
    _, campos = parametros.layout_ativo(conexao)
    nomes_dos_campos = set()
    for campo in campos:
        nomes_dos_campos.add(campo.campo)

    itens, sem_decisao = [], []
    for item in plano.itens:
        # Sem escolha da empresa: vale o campo proposto pela IA (se houver)
        if item.status == StatusMapeamento.PROPOSTO:
            escolha_padrao = item.campo
        else:
            escolha_padrao = None
        escolha = escolhas.get(item.coluna, escolha_padrao)
        if escolha == IGNORAR or (escolha is None and item.status == StatusMapeamento.NAO_MAPEADO):
            # Coluna ignorada: pela empresa, ou porque a IA já disse que não serve
            origem = "humano" if escolha == IGNORAR else item.origem
            novo_item = item.model_copy(update={"campo": None, "status": StatusMapeamento.NAO_MAPEADO,
                                                "origem": origem})
        elif escolha is None:
            # AMBIGUO sem decisão
            sem_decisao.append(item.coluna)
            continue
        elif escolha not in nomes_dos_campos:
            raise ValueError(f"O campo {escolha!r} não existe no layout.")
        else:
            # A origem vira "humano" quando a empresa mudou o que a IA propôs
            mudou = escolha != item.campo or item.status != StatusMapeamento.PROPOSTO
            origem = "humano" if mudou else item.origem
            novo_item = item.model_copy(update={"campo": escolha, "status": StatusMapeamento.PROPOSTO,
                                                "origem": origem})
        itens.append(novo_item)
    if sem_decisao:
        raise ValueError("Escolha o campo (ou ignore) destas colunas: " + ", ".join(sem_decisao))
    # Um campo só pode receber uma coluna (no texto corrido, mais de uma, desde que nunca na mesma pessoa)
    _conferir_colunas_repetidas(conexao, processamento_id, perfil, itens)

    plano = plano.model_copy(update={"itens": itens})
    conexao.execute("UPDATE mapeamentos SET status = 'APROVADO', plano = ?, aprovado_por = ?, aprovado_em = ? "
                    "WHERE processamento_id = ?", (plano.model_dump_json(), usuario, _agora(), processamento_id))
    conexao.commit()
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.MAPEAMENTO_APROVADO)
    alteradas_pela_empresa = 0
    for item in itens:
        if item.origem == "humano":
            alteradas_pela_empresa += 1
    auditoria.registrar(conexao, processamento_id, empresa_id, "Aceite do mapeamento", "MAPEAMENTO_APROVADO",
                        {"alteradas_pela_empresa": alteradas_pela_empresa})
    return plano


def _handoffs_feitos(conexao, processamento_id: str) -> int:
    """Quantos remapeamentos o Assistente já pediu neste arquivo (contados na auditoria)."""
    feitos = 0
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "HANDOFF_REMAPEAMENTO":
            feitos += 1
    return feitos


def solicitar_remapeamento(conexao, processamento_id: str, empresa_id: str, coluna: str, dica: str, cliente=None,
                           configuracao: str = "B3", busca=None) -> MappingPlan:
    """Handoff do Assistente de Correção para o Interpretador (ADR-17): UMA coluna, com o que a empresa contou.

    A conversa revelou que uma coluna foi mal entendida: o Interpretador reinterpreta SÓ essa coluna e o mapeamento
    volta para o aceite humano (ver reinterpretar_colunas).
    """
    return reinterpretar_colunas(conexao, processamento_id, empresa_id, {coluna: dica}, "Assistente de Correção",
                                 cliente=cliente, configuracao=configuracao, busca=busca)


def trocar_o_campo_da_coluna(conexao, processamento_id: str, empresa_id: str, coluna: str, campo_novo: str | None,
                             quem_pediu: str) -> str | None:
    """Troca, sem a IA, o campo de UMA coluna do mapeamento, que volta a PENDENTE para o aceite vir em seguida.

    Para que serve (ADR-124): no cartão da coluna que o arquivo inteiro não trouxe, a empresa disse em que
    coluna o dado está (ex.: "a matrícula é o CPF"), a conferência dos valores passou e ela confirmou. Diferente do
    handoff (solicitar_remapeamento), a IA não relê a coluna: o campo foi dito pela empresa.
    Recebe: a coluna do arquivo; o campo novo (None = a coluna fica de fora); quem pediu (vai para a trilha).
    Devolve: o campo que a coluna alimentava antes (None se ela estava de fora).
    Levanta KeyError (envio de outra empresa) ou ValueError (coluna que não está no mapeamento, ou dividida em partes).
    A padronização e a validação antigas deixam de valer (são refeitas no aceite).
    """
    from services import normalizador, validador
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    atual = obter(conexao, processamento_id)
    if perfil is None or atual is None:
        raise KeyError(processamento_id)
    plano, _ = atual
    itens = []
    campo_de_antes = None
    achou = False
    for item in plano.itens:
        if item.coluna != coluna:
            itens.append(item)
            continue
        achou = True
        # A coluna dividida em partes (ex.: o endereço) alimenta vários campos: a troca é pela tela de colunas
        if item.divisao is not None:
            raise ValueError(f'A coluna "{coluna}" foi dividida em partes: ajuste-a em "Conferir as colunas".')
        if item.status != StatusMapeamento.NAO_MAPEADO:
            campo_de_antes = item.campo
        # A coluna passa para o campo novo, como decisão da empresa (ou fica de fora)
        if campo_novo:
            itens.append(item.model_copy(update={"campo": campo_novo, "status": StatusMapeamento.PROPOSTO,
                                                 "origem": "humano"}))
        else:
            itens.append(item.model_copy(update={"campo": None, "status": StatusMapeamento.NAO_MAPEADO,
                                                 "origem": "humano"}))
    if not achou:
        raise ValueError(f'Não achei a coluna "{coluna}" no arquivo.')
    plano = plano.model_copy(update={"itens": itens})
    # O mapeamento volta a PENDENTE; padronização e validação antigas são apagadas
    conexao.execute("UPDATE mapeamentos SET status = 'PENDENTE', plano = ?, aprovado_por = NULL, aprovado_em = NULL "
                    "WHERE processamento_id = ?", (plano.model_dump_json(), processamento_id))
    normalizador.descartar(conexao, processamento_id)
    validador.descartar(conexao, processamento_id)
    conexao.commit()
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.MAPEAMENTO_PENDENTE)
    # Na trilha, a coluna e os campos (nomes técnicos), sem nenhum valor
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "COLUNA_TROCADA_NA_CONVERSA",
                        {"de": quem_pediu, "coluna": coluna, "antes": campo_de_antes, "depois": campo_novo})
    return campo_de_antes


def coluna_do_perfil(perfil, coluna: str):
    """O retrato da coluna no envio. Levanta ValueError se a coluna não existe no arquivo."""
    for coluna_do_arquivo in perfil.colunas:
        if coluna_do_arquivo.nome == coluna:
            return coluna_do_arquivo
    raise ValueError(f"A coluna {coluna!r} não existe no arquivo.")


def reinterpretar_colunas(conexao, processamento_id: str, empresa_id: str, dicas_por_coluna: dict[str, str],
                          quem_pediu: str, cliente=None, configuracao: str = "B3", busca=None) -> MappingPlan:
    """O Interpretador relê as colunas indicadas, cada uma com a dica da empresa, e o mapeamento volta ao aceite.

    Recebe: dicas_por_coluna — {coluna: o que a empresa sabe dela}; quem_pediu — "Assistente de Correção" (handoff
    da conversa) ou "Ajude a IA a acertar" (a tela de cadastro).
    Devolve: o plano novo, PENDENTE. Tudo conta como UMA releitura no limite (LIMITE_HANDOFFS): a empresa pode
    explicar várias colunas de uma vez. A padronização e a validação antigas deixam de valer (são refeitas depois
    do novo aceite). Cada dica passa antes pelo guardrail de injeção.
    Ex.: {"Obs": "é o e-mail pessoal", "Registro": "é o CPF"} → as duas colunas relidas, uma chamada de IA por coluna.
    """
    from services import guardrail_injecao, normalizador, validador
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    atual = obter(conexao, processamento_id)
    if perfil is None or atual is None:
        raise KeyError(processamento_id)
    if _handoffs_feitos(conexao, processamento_id) >= LIMITE_HANDOFFS:
        raise ValueError("Limite de remapeamentos pelo assistente atingido: ajuste o campo direto na tabela.")
    # Confere tudo antes de chamar a IA: as colunas existem e nenhuma dica tem cara de ordem para a IA
    for coluna, dica in dicas_por_coluna.items():
        coluna_do_perfil(perfil, coluna)
        if guardrail_injecao.verificar_mensagem(dica):
            raise ValueError("A mensagem tem uma frase com cara de instrução para o Agente Interpretador; descreva "
                             "só a coluna.")

    plano, _ = atual
    versao, campos = parametros.layout_ativo(conexao)
    # Uma leitura por coluna, cada uma com a sua dica: {coluna: o item novo, marcado como vindo do handoff}
    itens_novos = {}
    observacoes = list(plano.observacoes)
    for coluna, dica in dicas_por_coluna.items():
        reinterpretado = interpretador.interpretar(perfil, campos, versao, cliente or interpretador.cliente_padrao(),
                                                   configuracao=configuracao, busca=busca,
                                                   colunas=[coluna_do_perfil(perfil, coluna)], dica=dica)
        itens_novos[coluna] = reinterpretado.itens[0].model_copy(update={"origem": "handoff"})
        # Só a coluna em dúvida guarda os candidatos que a IA indicou (ADR-143, Parte 1)
        itens_novos[coluna] = _candidatos_so_na_duvida(itens_novos[coluna])
        observacoes = observacoes + reinterpretado.observacoes
        observacoes.append(f"Coluna {coluna!r} reinterpretada a pedido de: {quem_pediu}.")
    # Coluna que já estava dividida: as partes saem antes (a releitura decide de novo o que fazer com ela)
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    itens_do_plano = plano.itens
    for item in plano.itens:
        if item.coluna in dicas_por_coluna and item.divisao is not None:
            itens_do_plano = divisao_da_coluna.desfazer(leitura, itens_do_plano, item.coluna)
    processamentos.guardar_tabela_do_envio(conexao, processamento_id, leitura)
    plano = plano.model_copy(update={"itens": itens_do_plano})
    # Troca só os itens dessas colunas, guardando o antes e o depois de cada uma (para a auditoria)
    itens = []
    antes = {}
    depois = {}
    for item in plano.itens:
        if item.coluna in itens_novos:
            item_depois = itens_novos[item.coluna]
            antes[item.coluna] = item.campo or item.status.value
            depois[item.coluna] = item_depois.campo or item_depois.status.value
            itens.append(item_depois)
        else:
            itens.append(item)
    # A releitura também pode mandar dividir a coluna
    itens = aplicar_divisoes_da_ia(conexao, processamento_id, itens)
    plano = plano.model_copy(update={"itens": itens, "observacoes": observacoes})
    # O mapeamento volta a PENDENTE; padronização e validação antigas são apagadas
    conexao.execute("UPDATE mapeamentos SET status = 'PENDENTE', plano = ?, aprovado_por = NULL, aprovado_em = NULL "
                    "WHERE processamento_id = ?", (plano.model_dump_json(), processamento_id))
    normalizador.descartar(conexao, processamento_id)
    validador.descartar(conexao, processamento_id)
    conexao.commit()
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.MAPEAMENTO_PENDENTE)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "HANDOFF_REMAPEAMENTO", {
        "de": quem_pediu, "para": "Interpretador", "colunas": list(dicas_por_coluna),
        "antes": antes, "depois": depois})
    return plano
