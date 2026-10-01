"""Usar o que o sistema já sabe da empresa nas pendências do envio (ADR-127).

Para que serve: o CNPJ e o endereço da empresa já estão no cadastro dela (a aba Empresas do Portal Interno), mas um
arquivo sem essas colunas pediria tudo de novo: "é o CNPJ da nossa empresa" receberia "deveria ter 14 dígitos", e o
endereço da unidade viraria 6 cartões, um por pedaço (rua, número, bairro, cidade, UF e CEP). Por isso:
    1. o cartão do CNPJ do empregador oferece "Usar o CNPJ da empresa (10.433.218/0001-93)", e o cartão de cada pedaço
       do endereço comercial oferece "Usar o endereço da empresa (...)";
    2. um clique (ou a frase "é o CNPJ da nossa empresa") preenche, de uma vez, todos os funcionários que estão sem
       esse dado, e o endereço inteiro sai numa resposta só, com um Desfazer para tudo;
    3. o que o cadastro da empresa não tem (ex.: o CEP e o bairro) NÃO é inventado: a fala diz o que faltou, e os
       cartões desses pedaços continuam abertos (nada do banco é assumido).
Nada de IA aqui: o texto do botão é reconhecido pela regra, sem custo.

Exemplo de uso:
    valores = valores_do_cadastro(conexao, "EMP001")          # {"cnpj_empregador": "10433218000193", ...}
    grupo = grupo_pedido("Usar o CNPJ da empresa (10.433.218/0001-93)", "cnpj_empregador")   # → "cnpj"
    fala, aplicado = usar_no_envio(conexao, "EMP001", "rh.aurora", "a1b2", grupo, "Pedido na conversa com a IA: ...")
"""
import unicodedata

from services import correcoes, divisao, empresas, parametros

# Os dois grupos de dados que o cadastro da empresa conhece, e os campos do layout de cada um
GRUPO_CNPJ = "cnpj"
GRUPO_ENDERECO = "endereco"
# As partes do endereço comercial, na ordem da fala: {parte da divisão: campo do layout}
PARTES_DO_ENDERECO_COMERCIAL = {"logradouro": "logradouro_comercial", "numero": "numero_comercial",
                                "complemento": "complemento_comercial", "bairro": "bairro_comercial",
                                "municipio": "municipio_comercial", "uf": "uf_comercial", "cep": "cep_comercial"}
CAMPOS_DO_GRUPO = {GRUPO_CNPJ: ["cnpj_empregador"],
                   GRUPO_ENDERECO: list(PARTES_DO_ENDERECO_COMERCIAL.values())}
# As frases que pedem o dado do cadastro (sem acento e em minúsculas), em cada grupo. O texto do botão tem a primeira
FRASES_DO_GRUPO = {GRUPO_CNPJ: ("cnpj da empresa", "cnpj da nossa empresa", "nosso cnpj"),
                   GRUPO_ENDERECO: ("endereco da empresa", "endereco da nossa empresa", "nosso endereco")}
# O nome de cada campo do endereço na fala (curto, como a empresa fala)
NOME_NA_FALA = {"cnpj_empregador": "CNPJ", "logradouro_comercial": "rua", "numero_comercial": "número",
                "complemento_comercial": "complemento", "bairro_comercial": "bairro",
                "municipio_comercial": "cidade", "uf_comercial": "UF", "cep_comercial": "CEP"}
# O tipo de "Desfazer" desta resposta (volta todos os preenchimentos dela de uma vez)
DESFAZER_DADOS_DA_EMPRESA = "dados_da_empresa"


def _sem_acento_e_minusculo(texto: str) -> str:
    """ "Usar o Endereço" → "usar o endereco" (para comparar frases sem ligar para acento nem maiúscula)."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    letras = []
    for caractere in decomposto:
        # As marcas de acento viram caracteres à parte na decomposição: ficam de fora
        if unicodedata.category(caractere) != "Mn":
            letras.append(caractere)
    return "".join(letras)


def _cnpj_formatado(cnpj: str) -> str:
    """ "10433218000193" → "10.433.218/0001-93" (sem 14 dígitos, volta como veio)."""
    digitos = ""
    for caractere in cnpj:
        if caractere.isdigit():
            digitos = digitos + caractere
    if len(digitos) != 14:
        return cnpj
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def valores_do_cadastro(conexao, empresa_id: str) -> dict[str, str]:
    """O que o cadastro da empresa diz de cada campo do layout: o CNPJ e os pedaços do endereço comercial.

    Recebe: conexao; a empresa (da sessão).
    Devolve: {campo do layout: valor}, só com o que o cadastro tem (nada inventado). Empresa que não existe: {}.
    Ex.: CNPJ 10433218000193, endereço "Avenida Industrial, 4338", Campinas/SP → {"cnpj_empregador": "10433218000193",
    "logradouro_comercial": "Avenida Industrial", "numero_comercial": "4338", "municipio_comercial": "Campinas",
    "uf_comercial": "SP"}.
    """
    try:
        empresa = empresas.obter(conexao, empresa_id)
    except KeyError:
        return {}
    valores = {}
    if (empresa.get("cnpj") or "").strip():
        valores["cnpj_empregador"] = empresa["cnpj"].strip()
    # O endereço do cadastro é um texto só: a mesma divisão por regra das colunas de endereço (services/divisao.py)
    dividido = divisao.dividir_endereco(empresa.get("endereco_comercial") or "")
    for parte, valor in dividido.partes.items():
        if parte in PARTES_DO_ENDERECO_COMERCIAL and valor.strip():
            valores[PARTES_DO_ENDERECO_COMERCIAL[parte]] = valor.strip()
    # A cidade e a UF têm colunas próprias no cadastro: valem mais que o que a divisão achou no texto
    if (empresa.get("municipio") or "").strip():
        valores["municipio_comercial"] = empresa["municipio"].strip()
    if (empresa.get("uf") or "").strip():
        valores["uf_comercial"] = empresa["uf"].strip()
    return valores


def grupo_do_campo(campo: str | None) -> str | None:
    """O grupo do campo: "cnpj" (CNPJ do empregador), "endereco" (um pedaço do endereço comercial) ou None."""
    for grupo, campos in CAMPOS_DO_GRUPO.items():
        if campo in campos:
            return grupo
    return None


def _endereco_para_o_botao(valores: dict[str, str]) -> str:
    """O endereço do cadastro numa linha. Ex.: "Avenida Industrial, 4338, Campinas/SP"."""
    pedacos = []
    for campo in ("logradouro_comercial", "numero_comercial", "complemento_comercial", "bairro_comercial"):
        if campo in valores:
            pedacos.append(valores[campo])
    cidade = valores.get("municipio_comercial", "")
    if cidade and "uf_comercial" in valores:
        cidade = cidade + "/" + valores["uf_comercial"]
    if cidade:
        pedacos.append(cidade)
    return ", ".join(pedacos)


def texto_do_botao(campo: str | None, valores: dict[str, str]) -> str | None:
    """A resposta rápida do cartão, quando o cadastro da empresa sabe o valor do campo; senão, None.

    Ex.: ("cnpj_empregador", {...}) → "Usar o CNPJ da empresa (10.433.218/0001-93)";
    ("bairro_comercial", {...}) → "Usar o endereço da empresa (Avenida Industrial, 4338, Campinas/SP)", mas só se o
    cadastro tem o bairro (o botão não aparece num cartão que ele não resolve).
    """
    grupo = grupo_do_campo(campo)
    if grupo is None or campo not in valores:
        return None
    if grupo == GRUPO_CNPJ:
        return f"Usar o CNPJ da empresa ({_cnpj_formatado(valores[campo])})"
    return f"Usar o endereço da empresa ({_endereco_para_o_botao(valores)})"


def grupo_pedido(texto: str, campo: str | None) -> str | None:
    """O grupo que a mensagem pede para usar do cadastro, no cartão deste campo, ou None.

    Recebe: a mensagem da empresa; o campo da pendência.
    Devolve: "cnpj" ou "endereco", só quando a frase combina com o cartão (o CNPJ no cartão do CNPJ; o endereço num
    cartão do endereço). Pergunta ("?") ou negação ("não é o CNPJ da empresa") nunca valem (ADR-127).
    Ex.: ("é o CNPJ da nossa empresa", "cnpj_empregador") → "cnpj"; ("o CNPJ da empresa serve?", ...) → None.
    """
    grupo = grupo_do_campo(campo)
    if grupo is None or "?" in texto:
        return None
    frase = " " + _sem_acento_e_minusculo(texto) + " "
    if " nao " in frase:
        return None
    for jeito_de_dizer in FRASES_DO_GRUPO[grupo]:
        if jeito_de_dizer in frase:
            return grupo
    return None


def _campos_do_layout(conexao) -> dict:
    """{campo: CampoLayout} do layout vigente."""
    campos = {}
    for campo_do_layout in parametros.layout_ativo(conexao)[1]:
        campos[campo_do_layout.campo] = campo_do_layout
    return campos


def _lista_em_texto(itens: list[str]) -> str:
    """ ["rua", "número", "UF"] → "rua, número e UF"; ["CEP"] → "CEP"."""
    if len(itens) == 1:
        return itens[0]
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _plural_de_funcionarios(quantidade: int) -> str:
    """ "1 funcionário" ou "N funcionários"."""
    if quantidade == 1:
        return "1 funcionário"
    return f"{quantidade} funcionários"


def usar_no_envio(conexao, empresa_id: str, login: str, processamento_id: str, grupo: str,
                  motivo: str) -> tuple[str, dict | None]:
    """Preenche, com o cadastro da empresa, todos os funcionários do envio que estão sem os campos do grupo.

    Recebe: o envio; o grupo ("cnpj" ou "endereco"); o motivo (a frase da empresa, guardada em cada correção).
    Devolve: (a fala, o aplicado {resumo, desfazer {tipo "dados_da_empresa", id}}), ou (a fala, None) quando nada
    mudou. O id do Desfazer junta a primeira correção de cada campo preenchido ("a1,b2,c3"): desfazer_tudo volta todos.
    Quem já tem o campo no arquivo NÃO muda (a regra do preencher_para_todos). O que o cadastro não tem fica de fora,
    e a fala diz o quê.
    Levanta KeyError (envio de outra empresa).
    """
    valores = valores_do_cadastro(conexao, empresa_id)
    campos_do_layout = _campos_do_layout(conexao)
    primeiros_ids = []
    usados = []
    quantidade = 0
    faltaram = []
    for campo in CAMPOS_DO_GRUPO[grupo]:
        # Campo que o layout vigente não tem: nada a fazer
        if campo not in campos_do_layout:
            continue
        # O cadastro não sabe: não inventa; se o campo é obrigatório, a fala avisa
        if campo not in valores:
            if campos_do_layout[campo].obrigatorio:
                faltaram.append(NOME_NA_FALA[campo])
            continue
        # try/except: todos já têm o campo, ou o valor do cadastro não passa nas regras do campo (fica como está)
        try:
            identificadores = correcoes.preencher_para_todos(conexao, processamento_id, empresa_id, campo,
                                                             valores[campo], motivo, login)
        except ValueError:
            continue
        primeiros_ids.append(identificadores[0])
        # Na fala, o CNPJ como a empresa lê (com pontos, barra e traço)
        valor_na_fala = valores[campo]
        if grupo == GRUPO_CNPJ:
            valor_na_fala = _cnpj_formatado(valor_na_fala)
        usados.append(f'{NOME_NA_FALA[campo]} "{valor_na_fala}"')
        quantidade = max(quantidade, len(identificadores))
    # Como a fala e o resumo chamam o grupo
    o_que = "o endereço da empresa"
    resumo = "Endereço da empresa"
    if grupo == GRUPO_CNPJ:
        o_que = "o CNPJ da empresa"
        resumo = "CNPJ da empresa"
    falta = ""
    if faltaram:
        falta = (f" O cadastro da empresa não tem {_lista_em_texto(faltaram)}: informe no cartão de cada um, que "
                 "continua aberto.")
    if not primeiros_ids:
        return f"Não usei {o_que}: todos os funcionários deste envio já têm essa informação.{falta}", None
    fala = f"Pronto: usei {o_que} em {_plural_de_funcionarios(quantidade)}: {_lista_em_texto(usados)}.{falta}"
    aplicado = {"resumo": f"{resumo} em {_plural_de_funcionarios(quantidade)}",
                "desfazer": {"tipo": DESFAZER_DADOS_DA_EMPRESA, "id": ",".join(primeiros_ids)}}
    return fala, aplicado


def desfazer_tudo(conexao, empresa_id: str, login: str, processamento_id: str, identificador: str) -> str:
    """Volta todos os preenchimentos de uma resposta "Usar o ... da empresa". Devolve o resumo para a conversa.

    Recebe: o id do Desfazer ("a1,b2,c3": a primeira correção de cada campo). Levanta ValueError se um desses
    dados mudou de novo depois (os campos de antes dele, na ordem do id, já terão voltado; os outros ficam).
    """
    quantos = 0
    for primeiro_id in identificador.split(","):
        quantos = max(quantos, correcoes.desfazer_lote(conexao, processamento_id, empresa_id, primeiro_id.strip(),
                                                       login, evento="DADOS_DA_EMPRESA_DESFEITOS"))
    return f"Desfiz: {_plural_de_funcionarios(quantos)} sem o dado da empresa de novo."
