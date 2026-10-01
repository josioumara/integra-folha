"""Parâmetros com versões: o layout que o banco quer receber e as premissas financeiras (ADR-03, ADR-26).

O banco configura o sistema sem mexer no código. Cada gravação cria uma VERSÃO nova, e as anteriores
nunca são apagadas: assim cada processamento e cada projeção sabem com qual versão foram feitos.
A versão 1 nasce dos arquivos do projeto (data/contratos e data/parametros).
"""
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from models.contratos import CAMINHO_LAYOUT_V1, CampoLayout
from services import config
from services.formatacao import em_reais

# Arquivo com as premissas da versão 1 (os números do business case)
CAMINHO_PREMISSAS_V1 = config.RAIZ / "data" / "parametros" / "premissas_v1.json"

# Premissas em dinheiro: não podem ser negativas
PREMISSAS_EM_DINHEIRO = ("mob_cliente_folha", "mob_cliente_nao_folha", "mob_cliente_novo_conquistado")

# As premissas oficiais são só os MOB e o horizonte: as taxas (% novas contas, % correntistas não folha, % correção de
# folha) são estimativas da especialista no Simulador de Rentabilidade, sem valor oficial


@dataclass
class Premissas:
    """As premissas financeiras de uma versão. Dinheiro sempre em Decimal, nunca em float."""

    versao: str                              # ex.: "v1"
    horizonte_meses: int                     # período da projeção (ex.: 12 meses)
    mob_cliente_folha: Decimal               # margem de um cliente com a folha no banco, no período
    mob_cliente_nao_folha: Decimal           # margem de um cliente sem a folha reconhecida
    mob_cliente_novo_conquistado: Decimal    # margem de um cliente novo conquistado


def _preparar(conexao) -> None:
    """Cria a tabela de parâmetros no banco, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS parametros (
               tipo       TEXT NOT NULL,     -- "layout" ou "premissas"
               versao     INTEGER NOT NULL,
               conteudo   TEXT NOT NULL,     -- o conteúdo da versão, em JSON
               criado_em  TEXT NOT NULL,
               criado_por TEXT NOT NULL,
               PRIMARY KEY (tipo, versao)
           )"""
    )


def _gravar_nova_versao(conexao, tipo: str, conteudo, autor: str) -> int:
    """Grava o conteúdo como a próxima versão do tipo ("layout" ou "premissas") e devolve o número dela."""
    # Garante que a tabela existe
    _preparar(conexao)
    # Descobre a última versão gravada (0 se ainda não há nenhuma)
    consulta = conexao.execute("SELECT COALESCE(MAX(versao), 0) FROM parametros WHERE tipo = ?", (tipo,))
    ultima_versao = consulta.fetchone()[0]
    nova_versao = ultima_versao + 1
    # Momento da gravação
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Grava a nova versão, com o conteúdo em JSON
    conexao.execute(
        "INSERT INTO parametros (tipo, versao, conteudo, criado_em, criado_por) VALUES (?, ?, ?, ?, ?)",
        (tipo, nova_versao, json.dumps(conteudo, ensure_ascii=False), agora, autor),
    )
    conexao.commit()
    return nova_versao


def _conteudo_da_versao_1(tipo: str):
    """O conteúdo da versão 1, lido dos arquivos do projeto."""
    # Layout: uma linha do CSV por campo, conferida pelo contrato CampoLayout
    if tipo == "layout":
        campos = []
        with open(CAMINHO_LAYOUT_V1, encoding="utf-8", newline="") as arquivo:
            for linha in csv.DictReader(arquivo):
                campos.append(CampoLayout(**linha).model_dump(mode="json"))
        return campos
    # Premissas: o JSON do business case
    with open(CAMINHO_PREMISSAS_V1, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def _versao_ativa(conexao, tipo: str) -> tuple[int, object]:
    """A versão mais recente do tipo: (número, conteúdo). Se ainda não houver nenhuma, grava a v1 dos arquivos."""
    # Garante que a tabela existe
    _preparar(conexao)
    # Pega a versão de número mais alto
    consulta = conexao.execute("SELECT versao, conteudo FROM parametros WHERE tipo = ? ORDER BY versao DESC LIMIT 1",
                               (tipo,))
    linha = consulta.fetchone()
    # Primeira vez: grava a versão 1 e busca de novo
    if linha is None:
        _gravar_nova_versao(conexao, tipo, _conteudo_da_versao_1(tipo), "sistema (v1 dos arquivos do projeto)")
        return _versao_ativa(conexao, tipo)
    numero_da_versao, conteudo_em_texto = linha
    # Devolve o conteúdo de volta de texto JSON para lista ou dicionário
    return numero_da_versao, json.loads(conteudo_em_texto)


def historico(conexao, tipo: str) -> list[dict]:
    """Todas as versões gravadas do tipo, da mais nova para a mais antiga (número, quando e quem)."""
    # Garante que a versão 1 existe
    _versao_ativa(conexao, tipo)
    consulta = conexao.execute(
        "SELECT versao, criado_em, criado_por FROM parametros WHERE tipo = ? ORDER BY versao DESC", (tipo,))
    versoes = []
    for versao, criado_em, criado_por in consulta:
        versoes.append({"versao": versao, "criado_em": criado_em, "criado_por": criado_por})
    return versoes


# ============================== Layout ==============================

def layout_ativo(conexao) -> tuple[int, list[CampoLayout]]:
    """O layout vigente: (número da versão, lista de campos)."""
    numero_da_versao, campos_em_dicionario = _versao_ativa(conexao, "layout")
    # Transforma cada campo guardado em um CampoLayout
    campos = []
    for campo in campos_em_dicionario:
        campos.append(CampoLayout(**campo))
    return numero_da_versao, campos


def salvar_layout(conexao, campos: list[dict], autor: str) -> int:
    """Confere e grava uma nova versão do layout. Devolve o número da versão.

    Recusa tipo fora do catálogo fechado, nome técnico inválido e campo repetido (ADR-04).
    """
    # O contrato CampoLayout recusa tipo fora do catálogo e nome técnico inválido
    campos_conferidos = []
    for campo in campos:
        campos_conferidos.append(CampoLayout(**campo))
    # Procura nomes de campo repetidos
    nomes = []
    for campo in campos_conferidos:
        nomes.append(campo.campo)
    repetidos = set()
    for nome in nomes:
        if nomes.count(nome) > 1:
            repetidos.add(nome)
    if repetidos:
        raise ValueError(f"Campo repetido no layout: {', '.join(sorted(repetidos))}")
    # Grava em formato JSON (o tipo vira texto, ex.: "CPF")
    conteudo = []
    for campo in campos_conferidos:
        conteudo.append(campo.model_dump(mode="json"))
    return _gravar_nova_versao(conexao, "layout", conteudo, autor)


# Como cada atributo do campo aparece no registro das alterações (a tela do banco mostra essas frases)
NOMES_DOS_ATRIBUTOS = {
    "grupo": "grupo", "tipo": "tipo", "obrigatorio": "obrigatório", "sensivel": "dado pessoal (LGPD)",
    "uso_comercial_permitido": "uso comercial", "descricao": "descrição", "regra": "regra",
    "nao_confundir_com": "não confundir com", "exemplo": "exemplo",
    "igual_para_todos": "pode ser igual para todos",
    "minimo": "mínimo", "maximo": "máximo",
}

# Os atributos que são um limite em dinheiro (ADR-128): no registro, aparecem em reais ("R$ 500,00") ou "sem limite"
LIMITES_DO_CAMPO = ("minimo", "maximo")

# ---------------- Pode ser igual para todos? ----------------

# Os campos que podem ser informados uma vez para todos os funcionários do arquivo, quando a versão do parâmetro não diz
# (versões gravadas antes desta marcação existir): os dados da empresa e a competência da renda. É a mesma lista da
# coluna "igual_para_todos" do layout v1 (data/contratos/layout_v1.csv)
IGUAIS_PARA_TODOS_POR_PADRAO = frozenset({
    "cnpj_empregador", "cnpj_grupo", "codigo_unidade", "nome_unidade", "cep_comercial", "logradouro_comercial",
    "numero_comercial", "complemento_comercial", "bairro_comercial", "municipio_comercial", "uf_comercial",
    "data_referencia_renda"})


def pode_ser_igual_para_todos(campo_do_layout: CampoLayout) -> bool:
    """True se o campo pode ter o mesmo valor para todos os funcionários do arquivo (ex.: o CNPJ do empregador).

    Para que serve (ADR-124: o CPF é sempre único, a informação do titular é de cada pessoa, e só o cadastro da
    empresa e o endereço comercial podem ser iguais para todos): o
    "preencher para todos" e a pergunta "Se for a mesma para todos, qual é?" só existem para esses campos. Quem decide
    é o parâmetro (a marcação "Pode ser igual para todos", na tela Parâmetros do banco); numa versão antiga, sem a
    marcação, vale a lista IGUAIS_PARA_TODOS_POR_PADRAO.
    Ex.: cnpj_empregador → True; cpf → False; cargo → False.
    """
    if campo_do_layout.igual_para_todos is not None:
        return campo_do_layout.igual_para_todos
    return campo_do_layout.campo in IGUAIS_PARA_TODOS_POR_PADRAO


def campos_iguais_para_todos(conexao) -> set[str]:
    """Os nomes técnicos dos campos do parâmetro vigente que podem ser iguais para todos."""
    iguais = set()
    for campo_do_layout in layout_ativo(conexao)[1]:
        if pode_ser_igual_para_todos(campo_do_layout):
            iguais.add(campo_do_layout.campo)
    return iguais


def _limite_para_o_registro(valor) -> str:
    """O mínimo ou o máximo como aparece no registro. Ex.: "500.00" → "R$ 500,00"; None → "sem limite"."""
    # Sem valor: não há limite daquele lado
    if valor is None:
        return "sem limite"
    # O valor gravado é texto ("500.00"): vira número para sair em reais
    return em_reais(Decimal(str(valor)))


def _valor_para_o_registro(valor) -> str:
    """O valor de um atributo como aparece no registro: sim/não para marcações, o texto para o resto."""
    if valor is True:
        return "sim"
    if valor is False:
        return "não"
    return f"\"{valor}\""


def _valor_do_atributo(campo_em_dicionario: dict, atributo: str):
    """O valor de um atributo de um campo gravado, para comparar duas versões.

    A marcação "pode ser igual para todos" não existia nas versões antigas: lá, vale a lista padrão. Assim, gravar a
    tela pela primeira vez depois da marcação existir não aparece como mudança em todos os campos.
    Ex.: ({"campo": "cpf"}, "igual_para_todos") → False; ({"campo": "cnpj_empregador"}, "igual_para_todos") → True.
    """
    valor = campo_em_dicionario.get(atributo)
    # A marcação que a versão não tinha: o valor da lista padrão
    if atributo == "igual_para_todos" and valor is None:
        return campo_em_dicionario["campo"] in IGUAIS_PARA_TODOS_POR_PADRAO
    return valor


def mudancas_do_layout(campos_antes: list[dict], campos_depois: list[dict]) -> list[str]:
    """O que mudou de uma versão do layout para a seguinte, em frases curtas.

    Recebe: os campos das duas versões (dicionários, como estão gravados). Devolve: a lista de frases.
    Ex.: ["Campo novo: nome_social", "Campo removido: fax", "cpf · obrigatório: não → sim",
    "valor_renda · descrição alterada"]. Textos longos (descrição, regra...) só dizem que mudaram.
    """
    antes_por_nome = {}
    for campo in campos_antes:
        antes_por_nome[campo["campo"]] = campo
    depois_por_nome = {}
    for campo in campos_depois:
        depois_por_nome[campo["campo"]] = campo
    mudancas = []
    # Campos novos e alterados, na ordem da versão nova
    for nome, campo_depois in depois_por_nome.items():
        if nome not in antes_por_nome:
            mudancas.append(f"Campo novo: {nome}")
            continue
        campo_antes = antes_por_nome[nome]
        for atributo, nome_do_atributo in NOMES_DOS_ATRIBUTOS.items():
            valor_antes = _valor_do_atributo(campo_antes, atributo)
            valor_depois = _valor_do_atributo(campo_depois, atributo)
            if valor_antes == valor_depois:
                continue
            # Textos longos: só diz que mudou; marcações, tipo e grupo: o antes e o depois
            if atributo in ("descricao", "regra", "nao_confundir_com", "exemplo"):
                mudancas.append(f"{nome} · {nome_do_atributo} alterada")
            elif atributo in LIMITES_DO_CAMPO:
                # O mínimo e o máximo: o antes e o depois em reais (ex.: "valor_renda · mínimo: sem limite → R$ 500,00")
                mudancas.append(f"{nome} · {nome_do_atributo}: {_limite_para_o_registro(valor_antes)} → "
                                f"{_limite_para_o_registro(valor_depois)}")
            else:
                mudancas.append(f"{nome} · {nome_do_atributo}: {_valor_para_o_registro(valor_antes)} → "
                                f"{_valor_para_o_registro(valor_depois)}")
    # Campos que saíram
    for nome in antes_por_nome:
        if nome not in depois_por_nome:
            mudancas.append(f"Campo removido: {nome}")
    return mudancas


def salvar_layout_pela_tela(conexao, campos: list[dict], autor: str) -> dict:
    """Grava a versão nova do layout feita na tela do banco e devolve {versao, mudancas}.

    Recusa (ValueError, com a mensagem para a pessoa) quando nada mudou ou quando um campo não passa na conferência
    do contrato (tipo fora do catálogo, nome técnico inválido, campo repetido).
    """
    _, campos_atuais = layout_ativo(conexao)
    campos_antes = []
    for campo in campos_atuais:
        campos_antes.append(campo.model_dump(mode="json"))
    # Confere cada campo e diz qual deles não serve (a mensagem técnica do contrato fica mais simples)
    campos_depois = []
    for campo in campos:
        try:
            campos_depois.append(CampoLayout(**campo).model_dump(mode="json"))
        except ValidationError as erro:
            # A mensagem do contrato, sem o "Value error, " que a biblioteca põe na frente das regras escritas por nós
            motivo = erro.errors()[0]["msg"].removeprefix("Value error, ")
            raise ValueError(f"Confira o campo \"{campo.get('campo', '')}\": {motivo}.") from erro
    mudancas = mudancas_do_layout(campos_antes, campos_depois)
    if not mudancas:
        raise ValueError("Nada mudou no layout: nenhuma versão nova foi gravada.")
    versao = salvar_layout(conexao, campos_depois, autor)
    return {"versao": versao, "mudancas": mudancas}


def registro_do_layout(conexao) -> list[dict]:
    """O registro das alterações do layout: cada versão, com quem gravou, quando e o que mudou.

    Devolve: [{versao, criado_em, criado_por, mudancas}], da mais nova para a mais antiga. A versão 1 diz de onde
    veio ("Primeira versão, a dos arquivos do projeto").
    """
    # Garante que a versão 1 existe
    _versao_ativa(conexao, "layout")
    consulta = conexao.execute(
        "SELECT versao, conteudo, criado_em, criado_por FROM parametros WHERE tipo = 'layout' ORDER BY versao")
    registro = []
    campos_da_versao_anterior = None
    for versao, conteudo_em_texto, criado_em, criado_por in consulta:
        campos = json.loads(conteudo_em_texto)
        if campos_da_versao_anterior is None:
            mudancas = [f"Primeira versão, com {len(campos)} campos."]
        else:
            mudancas = mudancas_do_layout(campos_da_versao_anterior, campos)
        registro.append({"versao": versao, "criado_em": criado_em, "criado_por": criado_por, "mudancas": mudancas})
        campos_da_versao_anterior = campos
    # Da mais nova para a mais antiga
    registro.reverse()
    return registro


# ============================== Premissas financeiras ==============================

def premissas_ativas(conexao) -> Premissas:
    """As premissas vigentes, com dinheiro em Decimal."""
    numero_da_versao, dados = _versao_ativa(conexao, "premissas")
    return _premissas_do_conteudo(numero_da_versao, dados)


def premissas_da_versao(conexao, numero_da_versao: int) -> Premissas:
    """As premissas de uma versão escolhida (ex.: a v1, para reproduzir uma simulação antiga)."""
    # Garante que a v1 existe
    _versao_ativa(conexao, "premissas")
    linha = conexao.execute("SELECT conteudo FROM parametros WHERE tipo = 'premissas' AND versao = ?",
                            (numero_da_versao,)).fetchone()
    if linha is None:
        raise ValueError(f"Não existe a versão {numero_da_versao} das premissas.")
    return _premissas_do_conteudo(numero_da_versao, json.loads(linha[0]))


def _premissas_do_conteudo(numero_da_versao: int, dados: dict) -> Premissas:
    """Monta as Premissas a partir do conteúdo guardado, com dinheiro em Decimal."""
    # Uma versão gravada antes pode ter também % (que saíram das premissas oficiais): ficam de fora
    return Premissas(
        versao=f"v{numero_da_versao}",
        horizonte_meses=int(dados["horizonte_meses"]),
        # Decimal a partir do texto, para não herdar imprecisão de float
        mob_cliente_folha=Decimal(str(dados["mob_cliente_folha"])),
        mob_cliente_nao_folha=Decimal(str(dados["mob_cliente_nao_folha"])),
        mob_cliente_novo_conquistado=Decimal(str(dados["mob_cliente_novo_conquistado"])),
    )


def salvar_premissas(conexao, premissas: dict, autor: str) -> int:
    """Confere e grava uma nova versão das premissas. Não existe taxa de conquista padrão (ADR-26)."""
    # A taxa de conquista é sempre informada pelo especialista na hora da simulação
    if "taxa_conquista" in premissas:
        raise ValueError("A taxa de conquista não é premissa fixa: o especialista informa em cada simulação.")
    # Nenhum valor em dinheiro pode ser negativo
    for campo in PREMISSAS_EM_DINHEIRO:
        if Decimal(str(premissas[campo])) < 0:
            raise ValueError(f"{campo} não pode ser negativo.")
    # O horizonte precisa ser de pelo menos 1 mês
    if int(premissas["horizonte_meses"]) < 1:
        raise ValueError("O horizonte precisa ser de pelo menos 1 mês.")
    # Decimal vira texto para caber no JSON sem perder casas
    conteudo = {}
    for nome, valor in premissas.items():
        if isinstance(valor, Decimal):
            conteudo[nome] = str(valor)
        else:
            conteudo[nome] = valor
    return _gravar_nova_versao(conexao, "premissas", conteudo, autor)


def premissas_como_dict(premissas: Premissas) -> dict:
    """As premissas como dicionário (sem o número da versão), para editar e gravar de novo."""
    dados = asdict(premissas)
    # A versão não é editada: ela é criada ao gravar
    del dados["versao"]
    return dados


# ============================== Premissas na tela da Configuração ==============================
# A tela "Premissas financeiras" (engrenagem Configuração do Portal Interno) mostra a versão vigente, grava uma versão
# oficial nova e mostra o registro de todas as versões: quem gravou, quando e o que mudou (de → para).
# O registro sai da própria tabela "parametros": cada versão já guarda quem gravou (criado_por) e quando (criado_em),
# e "o que mudou" é a comparação de cada versão com a anterior (o mesmo jeito do registro do layout).

# As premissas que a tela mostra e edita, na ordem da tela, com o nome que aparece para a pessoa
TITULOS_DAS_PREMISSAS = {
    "horizonte_meses": "Horizonte da projeção",
    "mob_cliente_folha": "MOB cliente folha",
    "mob_cliente_nao_folha": "MOB cliente não folha",
    "mob_cliente_novo_conquistado": "MOB cliente novo conquistado",
}

# O maior horizonte aceito: 60 meses (5 anos). Mais que isso deixa a estimativa sem sentido para o planejamento
HORIZONTE_MAXIMO_EM_MESES = 60

# O maior tamanho de um valor digitado (ex.: "2090.62"): evita textos enormes no pedido
TAMANHO_MAXIMO_DO_VALOR = 20

# Um centavo: o dinheiro é gravado sempre com duas casas depois da vírgula
UM_CENTAVO = Decimal("0.01")


def _texto_da_premissa(nome: str, valor) -> str:
    """O valor de uma premissa como aparece no registro.

    Recebe: nome — ex.: "mob_cliente_folha"; valor — como está gravado (ex.: "2090.62" ou 12).
    Devolve: ex.: "R$ 2.090,62" ou "12 meses" (e "1 mês", no singular).
    """
    # O horizonte é contado em meses, com singular e plural
    if nome == "horizonte_meses":
        meses = int(valor)
        if meses == 1:
            return "1 mês"
        return f"{meses} meses"
    # O resto é dinheiro, no padrão brasileiro
    return em_reais(Decimal(str(valor)))


def _valor_para_comparar(nome: str, valor):
    """O valor de uma premissa pronto para comparar: número inteiro (horizonte) ou Decimal (dinheiro).

    Por quê: "2090.62" e "2090.620" são o mesmo dinheiro; comparar o texto diria que mudou.
    """
    if nome == "horizonte_meses":
        return int(valor)
    return Decimal(str(valor))


def mudancas_das_premissas(antes: dict, depois: dict) -> list[str]:
    """O que mudou de uma versão das premissas para a seguinte, em frases curtas (de → para).

    Recebe: o conteúdo das duas versões (dicionários, como estão gravados). Devolve: a lista de frases.
    Ex.: ["MOB cliente folha: R$ 2.090,62 → R$ 2.150,00", "Horizonte da projeção: 12 meses → 24 meses"].
    """
    mudancas = []
    # Compara premissa por premissa, na ordem da tela
    for nome, titulo in TITULOS_DAS_PREMISSAS.items():
        valor_antes = _valor_para_comparar(nome, antes[nome])
        valor_depois = _valor_para_comparar(nome, depois[nome])
        # Igual nas duas versões: não entra no registro
        if valor_antes == valor_depois:
            continue
        texto_antes = _texto_da_premissa(nome, antes[nome])
        texto_depois = _texto_da_premissa(nome, depois[nome])
        mudancas.append(f"{titulo}: {texto_antes} → {texto_depois}")
    return mudancas


def _primeira_frase_do_registro(conteudo: dict) -> str:
    """A frase da versão 1 no registro: de onde ela veio (o business case, nos arquivos do projeto)."""
    # A v1 guarda a origem (ex.: "Business case validado pela área de negócio (2026-09-23)")
    origem = conteudo.get("origem")
    if origem:
        return f"Primeira versão: {origem}."
    return "Primeira versão."


def registro_das_premissas(conexao) -> list[dict]:
    """O registro das versões das premissas: cada versão, com quem gravou, quando e o que mudou (de → para).

    Devolve: [{versao, criado_em, criado_por, mudancas}], da mais nova para a mais antiga.
    Ex.: [{"versao": 2, "criado_em": "2026-09-28T14:00:00+00:00", "criado_por": "especialista.banco",
           "mudancas": ["MOB cliente folha: R$ 2.090,62 → R$ 2.150,00"]}, {"versao": 1, ...}].
    """
    # Garante que a versão 1 existe
    _versao_ativa(conexao, "premissas")
    consulta = conexao.execute(
        "SELECT versao, conteudo, criado_em, criado_por FROM parametros WHERE tipo = 'premissas' ORDER BY versao")
    registro = []
    conteudo_da_versao_anterior = None
    # Da mais antiga para a mais nova: cada versão é comparada com a anterior
    for versao, conteudo_em_texto, criado_em, criado_por in consulta:
        conteudo = json.loads(conteudo_em_texto)
        if conteudo_da_versao_anterior is None:
            mudancas = [_primeira_frase_do_registro(conteudo)]
        else:
            mudancas = mudancas_das_premissas(conteudo_da_versao_anterior, conteudo)
        registro.append({"versao": versao, "criado_em": criado_em, "criado_por": criado_por, "mudancas": mudancas})
        conteudo_da_versao_anterior = conteudo
    # Da mais nova para a mais antiga
    registro.reverse()
    return registro


def premissas_para_a_tela(conexao) -> dict:
    """O que a tela "Premissas financeiras" mostra: a versão vigente, os valores dela e o registro das versões.

    Devolve: {"versao": 1, "vigente": {"horizonte_meses": 12, "mob_cliente_folha": "2090.62", ...},
              "horizonte_maximo_meses": 60, "registro": [...]}. O dinheiro vai como texto com duas casas ("2090.62"),
    nunca como número quebrado (float), para a tela mostrar exatamente o que está gravado.
    """
    premissas = premissas_ativas(conexao)
    # O número da versão sem o "v" (ex.: "v2" vira 2)
    numero_da_versao = int(premissas.versao.lstrip("v"))
    vigente = {
        "horizonte_meses": premissas.horizonte_meses,
        "mob_cliente_folha": str(premissas.mob_cliente_folha.quantize(UM_CENTAVO)),
        "mob_cliente_nao_folha": str(premissas.mob_cliente_nao_folha.quantize(UM_CENTAVO)),
        "mob_cliente_novo_conquistado": str(premissas.mob_cliente_novo_conquistado.quantize(UM_CENTAVO)),
    }
    return {"versao": numero_da_versao, "vigente": vigente, "horizonte_maximo_meses": HORIZONTE_MAXIMO_EM_MESES,
            "registro": registro_das_premissas(conexao)}


def _texto_do_valor(nome: str, valores: dict) -> str:
    """O valor digitado de uma premissa, como texto sem espaços. Faltando: ValueError com o nome da premissa."""
    valor = valores.get(nome)
    # Vazio ou faltando: a pessoa precisa informar
    if valor is None or str(valor).strip() == "":
        raise ValueError(f"Informe o valor de \"{TITULOS_DAS_PREMISSAS[nome]}\".")
    texto = str(valor).strip()
    # Um texto enorme não é um valor de premissa
    if len(texto) > TAMANHO_MAXIMO_DO_VALOR:
        raise ValueError(f"\"{TITULOS_DAS_PREMISSAS[nome]}\": valor grande demais.")
    return texto


def horizonte_conferido(valores: dict) -> int:
    """O horizonte digitado, conferido: um número inteiro de meses, de 1 a 60. Senão, ValueError.

    Serve às premissas oficiais e ao simulador do planejamento (services/planejamento.py).
    """
    texto = _texto_do_valor("horizonte_meses", valores)
    recado = f"O horizonte da projeção precisa ser um número inteiro de meses, de 1 a {HORIZONTE_MAXIMO_EM_MESES}."
    # Só algarismos: recusa "12.5", "-3" e "doze"
    if not texto.isdigit():
        raise ValueError(recado)
    meses = int(texto)
    if meses < 1 or meses > HORIZONTE_MAXIMO_EM_MESES:
        raise ValueError(recado)
    return meses


def dinheiro_conferido(nome: str, valores: dict) -> str:
    """Um valor em reais digitado, conferido: maior que zero e com no máximo 2 casas (centavos). Senão, ValueError.

    Serve às premissas oficiais e ao simulador do planejamento (services/planejamento.py).

    Devolve: o valor como texto com duas casas, pronto para gravar. Ex.: "2150" vira "2150.00".
    """
    texto = _texto_do_valor(nome, valores)
    titulo = TITULOS_DAS_PREMISSAS[nome]
    # O texto precisa ser um número (com ponto nos centavos, como a tela manda: "2090.62")
    try:
        valor = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(f"\"{titulo}\": informe um valor em reais (ex.: 2090.62).") from erro
    # "NaN" e "Infinity" também viram Decimal, mas não são dinheiro
    if not valor.is_finite():
        raise ValueError(f"\"{titulo}\": informe um valor em reais (ex.: 2090.62).")
    # Zero ou negativo não é premissa de ganho
    if valor <= 0:
        raise ValueError(f"\"{titulo}\" precisa ser maior que zero.")
    # Mais de duas casas depois da vírgula não é centavo (o expoente -3 quer dizer 3 casas)
    if valor.as_tuple().exponent < -2:
        raise ValueError(f"\"{titulo}\": use no máximo 2 casas depois da vírgula (os centavos).")
    return str(valor.quantize(UM_CENTAVO))


def percentual_conferido(nome: str, titulo: str, valores: dict) -> str | None:
    """Uma porcentagem digitada, conferida: de 0 a 100, com no máximo 2 casas. Vazia: None (sem valor).

    Recebe: nome — a chave em valores (ex.: "percentual_novas_contas"); titulo — o nome que aparece para a pessoa;
    valores — o que a tela mandou. Devolve: o valor como texto com duas casas (ex.: "35" vira "35.00"), ou None.
    Serve às três taxas do Simulador de Rentabilidade (services/planejamento.py).
    """
    valor = valores.get(nome)
    # Vazio ou faltando: sem valor (o sistema não supõe nenhum)
    if valor is None or str(valor).strip() == "":
        return None
    texto = str(valor).strip()
    recado = f"\"{titulo}\": informe uma porcentagem entre 0% e 100%, com no máximo 2 casas depois da vírgula."
    # Um texto enorme não é uma porcentagem
    if len(texto) > TAMANHO_MAXIMO_DO_VALOR:
        raise ValueError(recado)
    try:
        percentual = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(recado) from erro
    # "NaN" e "Infinity" viram Decimal, mas não são porcentagem; fora de 0 a 100 também não
    if not percentual.is_finite() or percentual < 0 or percentual > 100:
        raise ValueError(recado)
    # Mais de duas casas depois da vírgula (o expoente -3 quer dizer 3 casas)
    if percentual.as_tuple().exponent < -2:
        raise ValueError(recado)
    return str(percentual.quantize(UM_CENTAVO))


def conferir_premissas_da_tela(conexao, valores: dict) -> dict:
    """Confere os valores digitados na tela e diz o que muda em relação à versão vigente.

    Recebe: valores — {"horizonte_meses": "12", "mob_cliente_folha": "2150.00", ...} (texto ou número).
    Devolve: {"conteudo": o que será gravado como versão nova, "mudancas": [frases de → para]}.
    Recusa (ValueError, com a mensagem para a pessoa): valor faltando, zero ou negativo, horizonte fora de 1 a 60 ou
    quebrado, dinheiro com mais de 2 casas, e quando nada mudou. Quem grava é services/acesso.salvar_premissas, que
    confere antes se a pessoa é do banco.
    """
    conteudo = {"horizonte_meses": horizonte_conferido(valores)}
    # As três premissas em dinheiro, na ordem da tela
    for nome in PREMISSAS_EM_DINHEIRO:
        conteudo[nome] = dinheiro_conferido(nome, valores)
    # Compara com a versão vigente
    _, conteudo_vigente = _versao_ativa(conexao, "premissas")
    mudancas = mudancas_das_premissas(conteudo_vigente, conteudo)
    if not mudancas:
        raise ValueError("Nada mudou nas premissas: nenhuma versão nova foi gravada.")
    return {"conteudo": conteudo, "mudancas": mudancas}
