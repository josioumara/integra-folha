"""Repositório das KBs de endomarketing: ler, conferir (a "trava"), guardar em versões e publicar (ADR-125).

KB (do inglês "knowledge base", base de conhecimento) é um documento curto e padronizado que o Agente de
Endomarketing consulta para escrever os materiais. Há três grupos:
- as GERAIS, que valem para todas as empresas (tom de voz, termos proibidos, guardrails, diretrizes, canais,
  glossário e a jornada padrão);
- as do SANTANDER, o banco parceiro (o kit da marca padrão e a prateleira de benefícios);
- as de cada EMPRESA (benefícios, jornada de contratação, landing page, kit da marca e canais de atendimento).

O modelo de toda KB está em data/kbs_endomarketing/MODELO.md: uma "ficha" no começo (id, título, tipo, dono,
vigência, origem...) e as seções obrigatórias de cada tipo.

O que este arquivo faz, em ordem:
1. Separa a ficha e as seções de uma KB.
2. Confere a KB (a TRAVA): ficha, seções, termos proibidos, valores sem "simulação", dado pessoal e frase de ordem
   para a IA. Cada achado é gravado, para a Telemetria mostrar depois ("Guardrails das KBs").
3. Guarda cada gravação como uma VERSÃO nova. Cada versão tem uma situação: rascunho, publicada, substituída ou
   retirada. Só a versão publicada vale para a vitrine da empresa e para o agente.
4. Na primeira vez, carrega os arquivos de data/kbs_endomarketing/ como a versão 1, já publicada.
5. O logo da KB do kit (a KB do kit é a FONTE ÚNICA das cores, do logo e da escolha entre o
   padrão e o próprio). O logo é uma imagem anexada a cada VERSÃO da KB (tabela logos_das_kbs, em
   services/kit_de_marca.py), e não um campo da ficha. Só um rascunho recebe ou perde o logo; uma versão nova nasce com
   o logo da versão em que se baseia; e o kit próprio sem logo ganha um AVISO da trava (não bloqueia).

A vitrine, o catálogo do agente e o kit da empresa ficam em services/kbs_publicacao.py.
"""
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from services import catalogo, config, guardrail_injecao, kit_de_marca

# ---------------- Onde ficam os arquivos e quem gravou a versão 1 ----------------

# A pasta das KBs da versão 1 (os arquivos do projeto)
PASTA_DAS_KBS = config.RAIZ / "data" / "kbs_endomarketing"
# O arquivo que explica o modelo: fica na pasta, mas não é uma KB
ARQUIVO_DO_MODELO = "MODELO.md"
# O autor gravado nas KBs carregadas sozinhas na primeira vez
AUTOR_DA_VERSAO_1 = "sistema (v1 dos arquivos do projeto)"

# ---------------- Os donos, os tipos e as seções de cada tipo ----------------

# Os donos fixos; os outros donos são o código de uma empresa (ex.: "EMP001")
DONO_GERAL, DONO_SANTANDER = "GERAL", "SANTANDER"
# O formato do código de uma empresa
PADRAO_DO_CODIGO_DA_EMPRESA = re.compile(r"^EMP\d{3}$")
# Marca usada nas regras abaixo para dizer "qualquer empresa"
QUALQUER_EMPRESA = "EMPRESA"
# O começo do id de cada dono fixo (a KB de empresa começa pelo código da empresa)
PREFIXO_DO_DONO = {DONO_GERAL: "GER", DONO_SANTANDER: "SAN"}

# As seções obrigatórias de cada tipo de KB, na ordem do modelo
SECOES_DO_TIPO = {
    "tom_de_voz": ("Quem fala", "Personalidade", "Como escrever", "Exemplos certo e errado"),
    "termos_proibidos": ("Por que existe", "Termos proibidos", "Expressões sob condição"),
    "guardrails": ("O que o agente nunca faz", "O que o agente sempre faz", "Quando recusar"),
    "diretrizes": ("Regras de comunicação", "Avisos obrigatórios", "Dados e privacidade"),
    "canais": ("E-mail", "Mural ou intranet", "WhatsApp"),
    "glossario": ("Termos",),
    "jornada": ("Visão geral", "Passo a passo", "Documentos necessários", "Prazos", "Dúvidas comuns"),
    "kit_da_marca": ("Identidade", "Cores", "Tipografia", "Logo", "Tom da marca", "Assinatura", "O que não fazer"),
    "beneficio": ("Resumo", "Como funciona", "Quem pode usar", "Como contratar", "Condições", "Mensagem principal",
                  "O que não dizer"),
    "landing_page": ("Objetivo", "Chamada principal", "Seções da página", "Botões", "Perguntas frequentes",
                     "Avisos legais"),
    "atendimento": ("Onde consultar", "Canais de dúvidas"),
}
# O nome de cada tipo na tela
NOME_DO_TIPO = {
    "tom_de_voz": "Tom de voz", "termos_proibidos": "Termos proibidos", "guardrails": "Guardrails",
    "diretrizes": "Diretrizes", "canais": "Canais", "glossario": "Glossário", "jornada": "Jornada de contratação",
    "kit_da_marca": "Kit da marca", "beneficio": "Benefício", "landing_page": "Landing page",
    "atendimento": "Canais de atendimento",
}
# Quem pode ser dono de cada tipo
DONOS_DO_TIPO = {
    "tom_de_voz": (DONO_GERAL,), "termos_proibidos": (DONO_GERAL,), "guardrails": (DONO_GERAL,),
    "diretrizes": (DONO_GERAL,), "canais": (DONO_GERAL,), "glossario": (DONO_GERAL,),
    "jornada": (DONO_GERAL, QUALQUER_EMPRESA), "kit_da_marca": (DONO_SANTANDER, QUALQUER_EMPRESA),
    "beneficio": (DONO_SANTANDER, QUALQUER_EMPRESA), "landing_page": (QUALQUER_EMPRESA,),
    "atendimento": (QUALQUER_EMPRESA,),
}
# As chaves que toda ficha precisa ter
CHAVES_OBRIGATORIAS = ("id", "titulo", "tipo", "dono", "vigencia_inicio", "vigencia_fim", "origem")
# Todas as chaves que a ficha pode ter, na ordem em que são gravadas (as obrigatórias e as de benefício e de kit).
# O logo não é chave da ficha: ele é uma imagem anexada à versão da KB (ver a parte 6)
ORDEM_DAS_CHAVES_DA_FICHA = CHAVES_OBRIGATORIAS + ("categoria", "prateleira", "kit_escolhido", "cores")
# As opções do kit da marca
KIT_PROPRIO, KIT_PADRAO = "proprio", "padrao"
# O máximo de cores de um kit (o mesmo limite do cadastro da empresa)
MAXIMO_DE_CORES = 5
# O maior texto do kit que o cadastro da empresa aceita (services/empresas.py corta em 500)
LIMITE_DO_TEXTO_DO_KIT = 500
# O tipo da KB que tem logo
TIPO_DO_KIT = "kit_da_marca"
# O logo da versão 1: o arquivo com este nome na mesma pasta da KB do kit (ex.: data/kbs_endomarketing/EMP001/logo.png)
ARQUIVO_DO_LOGO_NA_PASTA = "logo.png"
# O endereço da imagem do logo de uma versão, na API (o editor da KB mostra a prévia por ele)
ENDERECO_DO_LOGO_DA_VERSAO = "/api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo"

# ---------------- As situações de uma versão ----------------

RASCUNHO, PUBLICADA, SUBSTITUIDA, RETIRADA = "RASCUNHO", "PUBLICADA", "SUBSTITUIDA", "RETIRADA"
# O nome de cada situação na tela
NOME_DA_SITUACAO = {RASCUNHO: "Rascunho", PUBLICADA: "Publicada", SUBSTITUIDA: "Substituída por outra versão",
                    RETIRADA: "Retirada"}
# Quantos dias antes do fim da vigência a KB já aparece em "Para revisar"
DIAS_PARA_AVISAR_O_VENCIMENTO = 30
# A situação da vigência, do jeito que a tela mostra
VIGENTE, VENCE_EM_BREVE, VENCIDA, FUTURA = "vigente", "vence_em_breve", "vencida", "futura"

# ---------------- A trava ----------------

# A gravidade de um achado: BLOQUEIA impede gravar ou publicar; AVISO só informa
BLOQUEIA, AVISO = "BLOQUEIA", "AVISO"
# O momento em que a trava rodou (fica gravado com o achado)
CARGA_INICIAL, SALVAR, PUBLICAR, REVISAR, VERIFICAR = "CARGA_INICIAL", "SALVAR", "PUBLICAR", "REVISAR", "VERIFICAR"
# O id da KB que diz os termos proibidos (a lista da trava sai dela)
ID_DOS_TERMOS_PROIBIDOS = "GER-TERMOS-PROIBIDOS"
# As seções que citam o proibido de propósito: a regra dos termos proibidos não olha para elas
SECOES_QUE_CITAM_O_PROIBIDO = ("O que não dizer", "O que não fazer", "Exemplos certo e errado", "Termos proibidos",
                               "Expressões sob condição", "O que o agente nunca faz")
# A palavra que todo valor em R$ ou % precisa ter na mesma linha (sem acento, porque o texto é comparado sem acento)
MARCA_DA_SIMULACAO = "simulacao"
# Um CPF: com pontos e traço (123.456.789-09) ou 11 dígitos seguidos
PADRAO_DO_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
# Uma cor em "#rrggbb"
PADRAO_DA_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
# O aviso do kit próprio sem logo: a regra e o texto que a tela mostra
REGRA_DO_LOGO = "Logo"
AVISO_DO_KIT_SEM_LOGO = "Kit próprio sem logo: a arte sai só com as cores e o nome da empresa."
# Um id: blocos de letras maiúsculas e números, separados por hífen (ex.: "EMP001-BEN-CONTA-SALARIO")
PADRAO_DO_ID = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)+$")

# As colunas das consultas de KBs, na ordem
COLUNAS_DA_KB = ("kb_id", "versao", "dono", "tipo", "titulo", "vigencia_inicio", "vigencia_fim", "conteudo_md",
                 "situacao", "criado_em", "criado_por", "publicado_em", "publicado_por")
# As colunas das consultas de achados, na ordem
COLUNAS_DO_ACHADO = ("achado_id", "kb_id", "versao", "dono", "momento", "regra", "gravidade", "detalhe", "trecho",
                     "feito_em", "feito_por")


class TravaBloqueou(ValueError):
    """A trava achou um problema que impede gravar ou publicar. Leva junto a lista de achados, para a tela mostrar.

    É um ValueError: quem não conhece a trava trata como qualquer erro de regra (a resposta vira 400).
    """

    def __init__(self, achados: list[dict]):
        """Guarda os achados e monta a mensagem com os motivos que bloquearam."""
        self.achados = achados
        motivos = []
        for achado in achados:
            if achado["gravidade"] == BLOQUEIA:
                motivos.append(achado["detalhe"])
        super().__init__("A trava das KBs bloqueou: " + " · ".join(motivos))


# ---------------- 1. Ficha e seções ----------------

def separar_ficha(conteudo_md: str) -> tuple[dict, str]:
    """Separa a ficha (as linhas "chave: valor" entre duas linhas "---") do resto da KB.

    Recebe: o texto da KB. Devolve: (ficha, corpo). Sem ficha: ({}, o texto inteiro).
    Exemplo: "---\\nid: GER-X\\n---\\n# Título" → ({"id": "GER-X"}, "# Título").
    """
    linhas = conteudo_md.strip().splitlines()
    # Sem a linha "---" no começo, não há ficha
    if not linhas or linhas[0].strip() != "---":
        return {}, conteudo_md
    ficha = {}
    for posicao in range(1, len(linhas)):
        linha = linhas[posicao]
        # A segunda linha "---" fecha a ficha: o resto é o corpo
        if linha.strip() == "---":
            return ficha, "\n".join(linhas[posicao + 1:]).strip()
        # Cada linha da ficha é "chave: valor" (só o primeiro ":" separa, porque o valor pode ter ":")
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            ficha[chave.strip()] = valor.strip()
    # A ficha nunca foi fechada: trata como KB sem ficha
    return {}, conteudo_md


def montar_conteudo(ficha: dict, corpo: str) -> str:
    """Junta a ficha e o corpo de volta num texto de KB (o contrário de separar_ficha).

    Recebe: ficha (dicionário "chave → valor", na ordem em que deve aparecer); corpo (o Markdown das seções).
    Devolve: o texto completo. Chave com valor vazio fica de fora.
    """
    linhas = ["---"]
    for chave, valor in ficha.items():
        # Valor vazio não entra (ex.: "categoria" numa KB que não é benefício)
        if str(valor).strip():
            linhas.append(f"{chave}: {str(valor).strip()}")
    linhas.append("---")
    return "\n".join(linhas) + "\n" + corpo.strip() + "\n"


def secoes_da_kb(corpo: str) -> list[dict]:
    """As seções "## ..." do corpo, na ordem: [{titulo, texto}]. Usa a mesma divisão do catálogo."""
    return catalogo.secoes_do_documento(corpo)


def texto_da_secao(corpo: str, titulo_da_secao: str) -> str:
    """O texto de uma seção pelo título. Seção que não existe: texto vazio."""
    for secao in secoes_da_kb(corpo):
        if secao["titulo"] == titulo_da_secao:
            return secao["texto"]
    return ""


def cores_do_kit(ficha: dict) -> list[str]:
    """As cores da ficha de um kit ("#aaaaaa, #bbbbbb") como lista, sem espaços. Sem cores: lista vazia."""
    cores = []
    for pedaco in ficha.get("cores", "").split(","):
        # Tira os espaços em volta de cada cor e ignora os pedaços vazios
        if pedaco.strip():
            cores.append(pedaco.strip())
    return cores


def kit_da_versao(ficha: dict, corpo: str) -> dict:
    """O kit que uma versão da KB do kit define, do jeito que o cadastro da empresa guarda (a cópia derivada).

    Recebe: a ficha e o corpo da versão. Devolve: {escolhido, texto, cores}: a escolha ("padrao" se a ficha não diz),
    o texto da seção "Identidade" (até 500 letras, o limite do cadastro) e a lista de cores.
    Exemplo: a KB da Aurora → {"escolhido": "proprio", "texto": "Aurora Alimentos, indústria...", "cores": [...]}.
    """
    return {"escolhido": ficha.get("kit_escolhido") or KIT_PADRAO,
            "texto": texto_da_secao(corpo, "Identidade")[:LIMITE_DO_TEXTO_DO_KIT],
            "cores": cores_do_kit(ficha)}


def e_codigo_de_empresa(dono: str) -> bool:
    """Diz se o dono é uma empresa (um código como "EMP001")."""
    return bool(PADRAO_DO_CODIGO_DA_EMPRESA.match(dono or ""))


def _normalizar(texto: str) -> str:
    """Tira os acentos, deixa em minúsculas e junta os espaços, para comparar palavras sem se importar com a grafia.

    Exemplo: "Aprovação  IMEDIATA" → "aprovacao imediata".
    """
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


# ---------------- 2. A trava ----------------

def _achado(regra: str, gravidade: str, detalhe: str, trecho: str = "") -> dict:
    """Monta um achado da trava. O trecho é cortado em 200 letras (basta para achar o ponto na KB)."""
    return {"regra": regra, "gravidade": gravidade, "detalhe": detalhe, "trecho": trecho[:200]}


def _conferir_ficha(ficha: dict, tem_logo: bool) -> list[dict]:
    """Confere a ficha: chaves obrigatórias, tipo, dono, id, vigência, categoria e as chaves do kit.

    tem_logo: se a versão tem (ou vai ter) o logo anexado; só importa no kit da marca (ver _conferir_kit).
    """
    achados = []
    # Sem ficha nenhuma, o resto nem dá para conferir
    if not ficha:
        return [_achado("Ficha", BLOQUEIA, "A KB não tem a ficha no começo (as linhas entre dois \"---\").")]
    # Cada chave obrigatória precisa ter valor
    for chave in CHAVES_OBRIGATORIAS:
        if not ficha.get(chave):
            achados.append(_achado("Ficha", BLOQUEIA, f"Falta \"{chave}\" na ficha."))
    tipo = ficha.get("tipo", "")
    dono = ficha.get("dono", "")
    # O tipo precisa ser um dos tipos do modelo
    if tipo and tipo not in SECOES_DO_TIPO:
        achados.append(_achado("Ficha", BLOQUEIA, f"O tipo \"{tipo}\" não existe no modelo."))
    # O dono precisa ser GERAL, SANTANDER ou o código de uma empresa, e combinar com o tipo
    if dono and tipo in DONOS_DO_TIPO:
        achados.extend(_conferir_dono(tipo, dono))
    # O id segue o formato e começa pelo dono
    if ficha.get("id"):
        achados.extend(_conferir_id(ficha["id"], dono))
    # A vigência: datas válidas e o fim depois do início
    achados.extend(_conferir_datas(ficha))
    # Benefício precisa de categoria; categoria que a vitrine não conhece só avisa
    if tipo == "beneficio":
        achados.extend(_conferir_categoria(ficha.get("categoria", "")))
    # Kit da marca: a escolha, as cores e o logo
    if tipo == TIPO_DO_KIT:
        achados.extend(_conferir_kit(ficha, tem_logo))
    return achados


def _conferir_dono(tipo: str, dono: str) -> list[dict]:
    """Confere se o dono existe e pode ter uma KB daquele tipo."""
    donos_permitidos = DONOS_DO_TIPO[tipo]
    # Uma empresa conta como "QUALQUER_EMPRESA" na lista de donos permitidos
    dono_na_regra = dono
    if e_codigo_de_empresa(dono):
        dono_na_regra = QUALQUER_EMPRESA
    elif dono not in (DONO_GERAL, DONO_SANTANDER):
        return [_achado("Ficha", BLOQUEIA, f"O dono \"{dono}\" não existe: use GERAL, SANTANDER ou o código da "
                                           "empresa (ex.: EMP001).")]
    if dono_na_regra not in donos_permitidos:
        return [_achado("Ficha", BLOQUEIA, f"Uma KB do tipo \"{tipo}\" não pode ter o dono \"{dono}\".")]
    return []


def _conferir_id(kb_id: str, dono: str) -> list[dict]:
    """Confere o formato do id e se ele começa pelo dono (GER-, SAN- ou o código da empresa)."""
    if not PADRAO_DO_ID.match(kb_id):
        return [_achado("Ficha", BLOQUEIA, "O id usa só letras maiúsculas, números e hífen (ex.: EMP001-BEN-PIX).",
                        kb_id)]
    # O prefixo esperado: GER, SAN ou o próprio código da empresa
    prefixo_esperado = PREFIXO_DO_DONO.get(dono, dono)
    if dono and not kb_id.startswith(prefixo_esperado + "-"):
        return [_achado("Ficha", BLOQUEIA, f"O id precisa começar por \"{prefixo_esperado}-\".", kb_id)]
    return []


def _conferir_datas(ficha: dict) -> list[dict]:
    """Confere as datas da vigência: formato AAAA-MM-DD e o fim no mesmo dia ou depois do início."""
    datas = {}
    for chave in ("vigencia_inicio", "vigencia_fim"):
        # Data ausente já foi avisada na conferência das chaves obrigatórias
        if not ficha.get(chave):
            continue
        try:
            datas[chave] = date.fromisoformat(ficha[chave])
        except ValueError:
            return [_achado("Ficha", BLOQUEIA, f"A data \"{chave}\" precisa estar em AAAA-MM-DD.", ficha[chave])]
    if len(datas) == 2 and datas["vigencia_fim"] < datas["vigencia_inicio"]:
        return [_achado("Ficha", BLOQUEIA, "O fim da vigência não pode ser antes do início.")]
    return []


def _conferir_categoria(categoria: str) -> list[dict]:
    """Benefício sem categoria bloqueia; categoria fora das 4 da vitrine só avisa (o filtro não vai achá-lo)."""
    if not categoria:
        return [_achado("Ficha", BLOQUEIA, "Benefício precisa de \"categoria\" na ficha.")]
    if categoria not in catalogo.CATEGORIAS:
        nomes = ", ".join(catalogo.CATEGORIAS)
        return [_achado("Categoria", AVISO, f"A categoria \"{categoria}\" não é uma das da vitrine ({nomes}).")]
    return []


def _conferir_kit(ficha: dict, tem_logo: bool) -> list[dict]:
    """Kit da marca: a escolha (proprio ou padrao) e as cores em #rrggbb, até 5; o kit próprio precisa de cor.

    O logo não bloqueia: o kit próprio sem logo só ganha um AVISO (a arte sai com as cores e o nome da empresa).
    """
    achados = []
    # A escolha é uma das duas opções do kit
    if ficha.get("kit_escolhido") not in (KIT_PROPRIO, KIT_PADRAO):
        achados.append(_achado("Ficha", BLOQUEIA, "No kit, \"kit_escolhido\" é \"proprio\" ou \"padrao\"."))
    cores = cores_do_kit(ficha)
    # Cada cor no formato "#rrggbb"
    for cor in cores:
        if not PADRAO_DA_COR.match(cor):
            achados.append(_achado("Ficha", BLOQUEIA, "Cada cor do kit é \"#rrggbb\".", cor))
    # No máximo 5 cores (o mesmo limite do cadastro da empresa)
    if len(cores) > MAXIMO_DE_CORES:
        achados.append(_achado("Ficha", BLOQUEIA, f"O kit tem no máximo {MAXIMO_DE_CORES} cores."))
    # O kit próprio precisa de pelo menos uma cor (a da faixa da arte)
    if ficha.get("kit_escolhido") == KIT_PROPRIO and not cores:
        achados.append(_achado("Ficha", BLOQUEIA, "O kit próprio precisa de pelo menos uma cor."))
    # O kit próprio sem logo só avisa: a pessoa pode anexar o logo ao rascunho antes de publicar
    if ficha.get("kit_escolhido") == KIT_PROPRIO and not tem_logo:
        achados.append(_achado(REGRA_DO_LOGO, AVISO, AVISO_DO_KIT_SEM_LOGO))
    return achados


def _conferir_secoes(tipo: str, corpo: str) -> list[dict]:
    """Confere se cada seção obrigatória do tipo existe e tem texto."""
    achados = []
    textos = {}
    for secao in secoes_da_kb(corpo):
        textos[secao["titulo"]] = secao["texto"]
    for titulo_da_secao in SECOES_DO_TIPO.get(tipo, ()):
        if not textos.get(titulo_da_secao, "").strip():
            achados.append(_achado("Seções obrigatórias", BLOQUEIA, f"Falta a seção \"## {titulo_da_secao}\" com texto."))
    return achados


def termos_da_kb_de_termos(conteudo_md: str) -> list[str]:
    """Os termos proibidos da tabela da KB de termos: a primeira coluna de cada linha, sem o cabeçalho.

    Recebe: o texto da KB de termos proibidos. Devolve: a lista de termos, sem repetir.
    Exemplo: a linha "| garantido | sujeito a análise | ... |" → "garantido".
    """
    _, corpo = separar_ficha(conteudo_md)
    termos = []
    for linha in texto_da_secao(corpo, "Termos proibidos").splitlines():
        # Só as linhas da tabela, que começam por "|"
        if not linha.strip().startswith("|"):
            continue
        primeira_coluna = linha.strip().strip("|").split("|")[0].strip()
        # Pula o cabeçalho e a linha de traços que separa o cabeçalho
        if not primeira_coluna or set(primeira_coluna) <= set("-: ") or primeira_coluna == "Termo proibido":
            continue
        if primeira_coluna not in termos:
            termos.append(primeira_coluna)
    return termos


def termos_proibidos(conexao) -> list[str]:
    """A lista da trava: os termos da versão PUBLICADA da KB de termos proibidos (sem ela, a do arquivo do projeto).

    Assim, quem publica uma versão nova da KB de termos muda a regra da trava sem mexer no código.
    """
    # A tabela pode ainda não existir (ex.: conferir uma KB antes de qualquer consulta)
    _criar_tabelas(conexao)
    linha = conexao.execute(
        "SELECT conteudo_md FROM kbs_endomarketing WHERE kb_id = ? AND situacao = ?",
        (ID_DOS_TERMOS_PROIBIDOS, PUBLICADA),
    ).fetchone()
    # Publicada no banco de dados: vale a do banco
    if linha is not None:
        return termos_da_kb_de_termos(linha[0])
    # Ainda não publicada (ex.: na carga inicial): vale o arquivo do projeto
    arquivo = PASTA_DAS_KBS / "gerais" / "termos_proibidos.md"
    if arquivo.exists():
        return termos_da_kb_de_termos(arquivo.read_text(encoding="utf-8"))
    return []


def _conferir_termos(termos: list[str], ficha: dict, corpo: str) -> list[dict]:
    """Procura cada termo proibido no título e nas seções que não citam o proibido de propósito."""
    # A KB que define os termos cita todos eles: não é conferida por esta regra
    if ficha.get("tipo") == "termos_proibidos":
        return []
    # Os textos conferidos: o título e cada seção que não está na lista das que citam o proibido
    textos_conferidos = [ficha.get("titulo", "")]
    for secao in secoes_da_kb(corpo):
        if secao["titulo"] not in SECOES_QUE_CITAM_O_PROIBIDO:
            textos_conferidos.append(secao["texto"])
    achados = []
    for termo in termos:
        # O termo precisa aparecer como palavra inteira ("garantido" não pega "garantidos")
        padrao = re.compile(r"(?<![a-z0-9])" + re.escape(_normalizar(termo)) + r"(?![a-z0-9])")
        for texto in textos_conferidos:
            for linha in texto.splitlines():
                if padrao.search(_normalizar(linha)):
                    achados.append(_achado("Termo proibido", BLOQUEIA, f"Usa o termo proibido \"{termo}\".", linha))
    return achados


def _conferir_valores(corpo: str) -> list[dict]:
    """Toda linha com "R$" ou "%" precisa dizer "simulação" (os valores do case são fictícios)."""
    achados = []
    for linha in corpo.splitlines():
        if ("R$" in linha or "%" in linha) and MARCA_DA_SIMULACAO not in _normalizar(linha):
            achados.append(_achado("Valor sem simulação", BLOQUEIA,
                                   "Valor em R$ ou % sem a palavra \"simulação\" na mesma linha.", linha))
    return achados


def _conferir_dado_pessoal(conteudo_md: str) -> list[dict]:
    """Nada com cara de CPF: a KB fala com o time, nunca de uma pessoa (LGPD)."""
    encontrado = PADRAO_DO_CPF.search(conteudo_md)
    if encontrado:
        return [_achado("Dado pessoal", BLOQUEIA, "A KB tem um número com cara de CPF.", encontrado.group(0))]
    return []


def _conferir_injecao(conteudo_md: str) -> list[dict]:
    """Frase com cara de ordem para a IA bloqueia a KB inteira (guardrail de injeção do projeto, ADR-38).

    Só a lista de frases confere a KB, sem a IA (ADR-147): a KB é escrita só pelo banco, é por natureza uma lista de
    regras para o agente (um detector de "ordens para a IA" tenderia a marcá-la) e só vale depois que uma pessoa
    publica. Assim, salvar, conferir e publicar nunca esperam a IA nem gastam com ela.
    """
    if guardrail_injecao.e_suspeito(conteudo_md):
        return [_achado("Ordem para o agente", BLOQUEIA,
                        "A KB tem uma frase com cara de ordem para o Agente de Endomarketing.")]
    return []


def situacao_da_vigencia(vigencia_inicio: str, vigencia_fim: str, dia: date | None = None) -> str:
    """Diz se a vigência está valendo, vence em breve (até 30 dias), já venceu ou ainda vai começar.

    Exemplo: fim 2026-10-10 visto em 2026-09-28 → "vence_em_breve".
    """
    hoje = dia or date.today()
    inicio = date.fromisoformat(vigencia_inicio)
    fim = date.fromisoformat(vigencia_fim)
    if fim < hoje:
        return VENCIDA
    if inicio > hoje:
        return FUTURA
    if fim <= hoje + timedelta(days=DIAS_PARA_AVISAR_O_VENCIMENTO):
        return VENCE_EM_BREVE
    return VIGENTE


def _conferir_vencimento(ficha: dict, dia: date | None) -> list[dict]:
    """KB vencida só avisa: ela continua guardada, mas a vitrine e o agente deixam de usá-la."""
    try:
        situacao = situacao_da_vigencia(ficha["vigencia_inicio"], ficha["vigencia_fim"], dia)
    except (KeyError, ValueError):
        # Data ausente ou inválida já virou achado na conferência da ficha
        return []
    if situacao == VENCIDA:
        return [_achado("Vencida", AVISO, "A vigência já terminou: revise a KB para ela voltar a valer.")]
    return []


def conferir(conexao, conteudo_md: str, dia: date | None = None, tem_logo: bool = False) -> list[dict]:
    """A trava inteira: devolve todos os achados da KB (lista vazia = tudo certo). Nenhuma conferência chama a IA.

    Recebe: conexao (para ler a lista de termos proibidos publicada); conteudo_md (a KB inteira, com a ficha);
    dia (para a vigência; sem informar, hoje); tem_logo (se a versão tem, ou vai ter, o logo anexado; o logo não fica
    no texto da KB, por isso quem chama informa).
    Devolve: [{regra, gravidade, detalhe, trecho}]. Um achado BLOQUEIA impede gravar e publicar.
    """
    ficha, corpo = separar_ficha(conteudo_md)
    achados = _conferir_ficha(ficha, tem_logo)
    # As seções só são conferidas quando o tipo é conhecido
    if ficha.get("tipo") in SECOES_DO_TIPO:
        achados.extend(_conferir_secoes(ficha["tipo"], corpo))
    achados.extend(_conferir_termos(termos_proibidos(conexao), ficha, corpo))
    achados.extend(_conferir_valores(corpo))
    achados.extend(_conferir_dado_pessoal(conteudo_md))
    achados.extend(_conferir_injecao(conteudo_md))
    achados.extend(_conferir_vencimento(ficha, dia))
    return achados


def tem_bloqueio(achados: list[dict]) -> bool:
    """Diz se algum achado bloqueia."""
    for achado in achados:
        if achado["gravidade"] == BLOQUEIA:
            return True
    return False


# ---------------- 3. As tabelas, as versões e os achados gravados ----------------

def _agora() -> str:
    """O momento atual, em texto ISO (UTC), para gravar nas tabelas."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _preparar(conexao) -> None:
    """Cria as tabelas (se preciso) e, na primeira vez, carrega a versão 1 dos arquivos do projeto."""
    _criar_tabelas(conexao)
    # Primeira vez: carrega os arquivos do projeto
    quantidade = conexao.execute("SELECT COUNT(*) FROM kbs_endomarketing").fetchone()[0]
    if quantidade == 0:
        _carregar_versao_1(conexao)


def _criar_tabelas(conexao) -> None:
    """Cria as tabelas das KBs e dos achados, se ainda não existirem (sem carregar nada)."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS kbs_endomarketing (
               kb_id           TEXT NOT NULL,
               versao          INTEGER NOT NULL,
               dono            TEXT NOT NULL,     -- GERAL, SANTANDER ou o código da empresa
               tipo            TEXT NOT NULL,
               titulo          TEXT NOT NULL,
               vigencia_inicio TEXT NOT NULL,
               vigencia_fim    TEXT NOT NULL,
               conteudo_md     TEXT NOT NULL,     -- a KB inteira: a ficha e as seções
               situacao        TEXT NOT NULL,     -- RASCUNHO, PUBLICADA, SUBSTITUIDA ou RETIRADA
               criado_em       TEXT NOT NULL,
               criado_por      TEXT NOT NULL,
               publicado_em    TEXT,
               publicado_por   TEXT,
               PRIMARY KEY (kb_id, versao)
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS kbs_achados_da_trava (
               achado_id  TEXT PRIMARY KEY,
               kb_id      TEXT NOT NULL,
               versao     INTEGER,               -- vazio quando a trava bloqueou e a versão nem foi gravada
               dono       TEXT NOT NULL,
               momento    TEXT NOT NULL,         -- CARGA_INICIAL, SALVAR, PUBLICAR, REVISAR ou VERIFICAR
               regra      TEXT NOT NULL,
               gravidade  TEXT NOT NULL,         -- BLOQUEIA ou AVISO
               detalhe    TEXT NOT NULL,
               trecho     TEXT NOT NULL,
               feito_em   TEXT NOT NULL,
               feito_por  TEXT NOT NULL
           )"""
    )
    conexao.commit()


def _arquivos_da_versao_1() -> list:
    """Os arquivos .md das KBs do projeto (todas as pastas), sem o MODELO.md, em ordem de caminho."""
    arquivos = []
    for caminho in sorted(PASTA_DAS_KBS.rglob("*.md")):
        if caminho.name != ARQUIVO_DO_MODELO:
            arquivos.append(caminho)
    return arquivos


def logo_da_pasta(caminho_da_kb, ficha: dict) -> bytes | None:
    """O logo da versão 1 de uma KB do kit: o arquivo logo.png da mesma pasta, se ele existe e é uma imagem válida.

    Recebe: o caminho do arquivo da KB; a ficha dela. Devolve: os bytes da imagem, ou None (a KB não é do kit, a pasta
    não tem logo.png ou o arquivo não é um PNG ou JPEG de até 500 KB). O nome é fixo: nenhum caminho vem da ficha.
    Exemplo: data/kbs_endomarketing/EMP001/kit_da_marca.md → os bytes de data/kbs_endomarketing/EMP001/logo.png.
    """
    # Só a KB do kit tem logo
    if ficha.get("tipo") != TIPO_DO_KIT:
        return None
    arquivo_do_logo = caminho_da_kb.parent / ARQUIVO_DO_LOGO_NA_PASTA
    # A pasta sem logo.png: a versão 1 fica sem logo
    if not arquivo_do_logo.is_file():
        return None
    conteudo = arquivo_do_logo.read_bytes()
    # Uma imagem que o sistema não aceita também não entra (a trava avisa do kit próprio sem logo)
    try:
        kit_de_marca.conferir_logo(conteudo)
    except ValueError:
        return None
    return conteudo


def kit_dos_arquivos(empresa_id: str) -> dict | None:
    """O kit que a KB do kit da empresa define nos arquivos do projeto (a versão 1), com o logo.png da pasta.

    É o kit com que a semente das empresas nasce (services/empresas.py): assim, num banco novo, a cópia derivada que
    a arte lê já começa igual à KB publicada. Os arquivos do projeto passam na trava (tests/test_kbs_endomarketing.py).
    Recebe: o código da empresa (ex.: "EMP001"). Devolve: {escolhido, texto, cores, logo (os bytes ou None)}; sem KB do
    kit na pasta da empresa, None.
    """
    for caminho in sorted((PASTA_DAS_KBS / empresa_id).glob("*.md")):
        ficha, corpo = separar_ficha(caminho.read_text(encoding="utf-8"))
        # Só a KB do kit desta empresa
        if ficha.get("tipo") != TIPO_DO_KIT or ficha.get("dono") != empresa_id:
            continue
        kit = kit_da_versao(ficha, corpo)
        kit["logo"] = logo_da_pasta(caminho, ficha)
        return kit
    return None


def _carregar_versao_1(conexao) -> None:
    """Grava cada arquivo do projeto como a versão 1, PUBLICADA se passar na trava (senão, fica como rascunho).

    A KB do kit ganha, na versão 1, o logo.png da mesma pasta (logo_da_pasta).
    """
    for caminho in _arquivos_da_versao_1():
        conteudo = caminho.read_text(encoding="utf-8")
        ficha, _ = separar_ficha(conteudo)
        # O logo da pasta (só na KB do kit): ele entra na versão 1 junto com o texto
        logo = logo_da_pasta(caminho, ficha)
        # A trava, como na tela: só conferências fixas, sem a IA (ligar o servidor não gasta nada)
        achados = conferir(conexao, conteudo, tem_logo=logo is not None)
        # Arquivo sem as chaves que a tabela exige não é gravado: só o achado fica registrado
        chaves_que_faltam = []
        for chave in CHAVES_OBRIGATORIAS:
            if not ficha.get(chave):
                chaves_que_faltam.append(chave)
        if chaves_que_faltam:
            _gravar_achados(conexao, ficha.get("id") or caminho.stem, None, ficha.get("dono") or "?", CARGA_INICIAL,
                            achados, AUTOR_DA_VERSAO_1)
            continue
        situacao = PUBLICADA
        if tem_bloqueio(achados):
            situacao = RASCUNHO
        # Outra tela pode estar carregando ao mesmo tempo: só grava os achados de quem gravou a KB de fato
        if _inserir_versao_1(conexao, ficha, conteudo, situacao):
            # Os achados da carga ficam gravados também (um arquivo com problema aparece na Telemetria)
            _gravar_achados(conexao, ficha["id"], 1, ficha["dono"], CARGA_INICIAL, achados, AUTOR_DA_VERSAO_1)
            # O logo da pasta fica anexado à versão 1 (só quem gravou a versão grava o logo)
            if logo is not None:
                kit_de_marca.gravar_logo_da_versao(conexao, ficha["id"], 1, logo, AUTOR_DA_VERSAO_1)


def _inserir_versao_1(conexao, ficha: dict, conteudo_md: str, situacao: str) -> bool:
    """Grava a versão 1 de um arquivo do projeto, se ela ainda não existe. Devolve se gravou.

    Por que "ON CONFLICT DO NOTHING": logo depois do login, a página inicial e a vitrine pedem os benefícios quase
    juntas; com o banco vazio, as duas carregam os arquivos ao mesmo tempo. A versão 1 tem o número fixo, então a
    segunda gravação da mesma KB esbarra na chave (kb_id, versao) e é ignorada, em vez de virar uma "versão 2" repetida.
    O comando é o mesmo no SQLite e no PostgreSQL.
    """
    agora = _agora()
    publicado_em = None
    publicado_por = None
    if situacao == PUBLICADA:
        publicado_em = agora
        publicado_por = AUTOR_DA_VERSAO_1
    cursor = conexao.execute(
        "INSERT INTO kbs_endomarketing (kb_id, versao, dono, tipo, titulo, vigencia_inicio, vigencia_fim, conteudo_md, "
        "situacao, criado_em, criado_por, publicado_em, publicado_por) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (kb_id, versao) DO NOTHING",
        (ficha["id"], ficha["dono"], ficha["tipo"], ficha["titulo"], ficha["vigencia_inicio"], ficha["vigencia_fim"],
         conteudo_md, situacao, agora, AUTOR_DA_VERSAO_1, publicado_em, publicado_por),
    )
    gravou = cursor.rowcount == 1
    conexao.commit()
    return gravou


def _inserir_versao(conexao, ficha: dict, conteudo_md: str, situacao: str, autor: str) -> int:
    """Grava a KB como a próxima versão daquele id. Devolve o número da versão."""
    consulta = conexao.execute("SELECT COALESCE(MAX(versao), 0) FROM kbs_endomarketing WHERE kb_id = ?",
                               (ficha["id"],))
    nova_versao = consulta.fetchone()[0] + 1
    agora = _agora()
    # Publicada já na gravação (carga inicial): o autor também é quem publicou
    publicado_em = None
    publicado_por = None
    if situacao == PUBLICADA:
        publicado_em = agora
        publicado_por = autor
    conexao.execute(
        "INSERT INTO kbs_endomarketing (kb_id, versao, dono, tipo, titulo, vigencia_inicio, vigencia_fim, conteudo_md, "
        "situacao, criado_em, criado_por, publicado_em, publicado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ficha["id"], nova_versao, ficha["dono"], ficha["tipo"], ficha["titulo"], ficha["vigencia_inicio"],
         ficha["vigencia_fim"], conteudo_md, situacao, agora, autor, publicado_em, publicado_por),
    )
    conexao.commit()
    return nova_versao


def _gravar_achados(conexao, kb_id: str, versao: int | None, dono: str, momento: str, achados: list[dict],
                    autor: str) -> None:
    """Grava cada achado da trava, para a Telemetria mostrar o que ela apontou, quando e para quem."""
    agora = _agora()
    for achado in achados:
        conexao.execute(
            "INSERT INTO kbs_achados_da_trava (achado_id, kb_id, versao, dono, momento, regra, gravidade, detalhe, "
            "trecho, feito_em, feito_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, kb_id, versao, dono, momento, achado["regra"], achado["gravidade"], achado["detalhe"],
             achado["trecho"], agora, autor),
        )
    conexao.commit()


def _linhas_em_kbs(consulta) -> list[dict]:
    """Transforma cada linha da consulta num dicionário com os nomes das colunas."""
    kbs = []
    for linha in consulta:
        kbs.append(dict(zip(COLUNAS_DA_KB, linha)))
    return kbs


def _versoes(conexao, kb_id: str) -> list[dict]:
    """Todas as versões de uma KB, da mais nova para a mais antiga."""
    consulta = conexao.execute(
        "SELECT " + ", ".join(COLUNAS_DA_KB) + " FROM kbs_endomarketing WHERE kb_id = ? ORDER BY versao DESC",
        (kb_id,),
    )
    return _linhas_em_kbs(consulta)


def _versao(conexao, kb_id: str, versao: int) -> dict:
    """Uma versão da KB. KeyError se não existe."""
    for linha in _versoes(conexao, kb_id):
        if linha["versao"] == versao:
            return linha
    raise KeyError(kb_id)


def versao_publicada(conexao, kb_id: str) -> dict | None:
    """A versão publicada da KB (há no máximo uma). Sem versão publicada: None."""
    for linha in _versoes(conexao, kb_id):
        if linha["situacao"] == PUBLICADA:
            return linha
    return None


# ---------------- 4. Consultas para a tela e para quem usa as KBs ----------------

def _resumo_da_kb(versoes: list[dict], dia: date | None) -> dict:
    """O resumo de uma KB para a lista da tela: a última versão, a publicada e a situação da vigência.

    A vigência mostrada é a da versão publicada (a que vale); sem versão publicada, a da última versão.
    """
    ultima = versoes[0]
    publicada = None
    for linha in versoes:
        if linha["situacao"] == PUBLICADA:
            publicada = linha
    referencia = publicada or ultima
    ficha, _ = separar_ficha(referencia["conteudo_md"])
    versao_publicada_numero = None
    if publicada:
        versao_publicada_numero = publicada["versao"]
    return {"kb_id": ultima["kb_id"], "titulo": referencia["titulo"], "tipo": ultima["tipo"],
            "nome_do_tipo": NOME_DO_TIPO.get(ultima["tipo"], ultima["tipo"]), "dono": ultima["dono"],
            "categoria": ficha.get("categoria", ""), "ultima_versao": ultima["versao"],
            "situacao_da_ultima": ultima["situacao"],
            "nome_da_situacao": NOME_DA_SITUACAO.get(ultima["situacao"], ultima["situacao"]),
            "versao_publicada": versao_publicada_numero, "vigencia_inicio": referencia["vigencia_inicio"],
            "vigencia_fim": referencia["vigencia_fim"],
            "vigencia": situacao_da_vigencia(referencia["vigencia_inicio"], referencia["vigencia_fim"], dia),
            "atualizado_em": ultima["criado_em"], "atualizado_por": ultima["criado_por"]}


def listar(conexao, dono: str | None = None, dia: date | None = None) -> list[dict]:
    """Uma linha por KB (não por versão), do dono pedido ou de todos, em ordem de dono, tipo e título.

    Recebe: conexao; dono (GERAL, SANTANDER, o código da empresa ou None para todos); dia (para a vigência).
    Devolve: o resumo de cada KB (ver _resumo_da_kb), com "para_revisar" = vencida ou vencendo em até 30 dias.
    """
    _preparar(conexao)
    consulta = conexao.execute(
        "SELECT " + ", ".join(COLUNAS_DA_KB) + " FROM kbs_endomarketing WHERE (? IS NULL OR dono = ?) "
        "ORDER BY kb_id, versao DESC",
        (dono, dono),
    )
    # Agrupa as versões por KB (a consulta já vem com a mais nova primeiro)
    versoes_por_kb = {}
    for linha in _linhas_em_kbs(consulta):
        versoes_por_kb.setdefault(linha["kb_id"], []).append(linha)
    resumos = []
    for versoes in versoes_por_kb.values():
        resumo = _resumo_da_kb(versoes, dia)
        resumo["para_revisar"] = resumo["vigencia"] in (VENCIDA, VENCE_EM_BREVE)
        resumos.append(resumo)
    resumos.sort(key=_ordem_na_lista)
    return resumos


def _ordem_na_lista(resumo: dict) -> tuple:
    """A ordem da lista: pelo dono, pela ordem dos tipos no modelo e pelo título."""
    tipos_em_ordem = list(SECOES_DO_TIPO)
    return resumo["dono"], tipos_em_ordem.index(resumo["tipo"]), resumo["titulo"]


def obter(conexao, kb_id: str, versao: int | None = None) -> dict:
    """Uma KB para a tela de detalhe: a versão pedida (sem informar, a publicada ou a última), com ficha e seções.

    Devolve: {kb_id, versao, dono, tipo, titulo, vigência, situacao, ficha, corpo, secoes, versoes, tem_logo,
    endereco_do_logo}. KeyError se não existe. "versoes" é o histórico: [{versao, situacao, criado_em, criado_por,
    publicado_em, publicado_por}]. tem_logo diz se a versão mostrada tem o logo anexado (só a KB do kit tem), e
    endereco_do_logo é o endereço da imagem na API (None sem logo).
    """
    _preparar(conexao)
    versoes = _versoes(conexao, kb_id)
    if not versoes:
        raise KeyError(kb_id)
    # A versão mostrada: a pedida; senão a publicada; senão a última
    escolhida = versao_publicada(conexao, kb_id) or versoes[0]
    if versao is not None:
        escolhida = _versao(conexao, kb_id, versao)
    ficha, corpo = separar_ficha(escolhida["conteudo_md"])
    # O logo anexado à versão mostrada, e o endereço da imagem para a prévia do editor
    tem_logo = kit_de_marca.logo_da_versao(conexao, kb_id, escolhida["versao"]) is not None
    endereco_do_logo = None
    if tem_logo:
        endereco_do_logo = ENDERECO_DO_LOGO_DA_VERSAO.format(kb_id=kb_id, versao=escolhida["versao"])
    historico = []
    for linha in versoes:
        historico.append({"versao": linha["versao"], "situacao": linha["situacao"],
                          "nome_da_situacao": NOME_DA_SITUACAO.get(linha["situacao"], linha["situacao"]),
                          "criado_em": linha["criado_em"], "criado_por": linha["criado_por"],
                          "publicado_em": linha["publicado_em"], "publicado_por": linha["publicado_por"]})
    resultado = dict(escolhida)
    resultado.update({"nome_do_tipo": NOME_DO_TIPO.get(escolhida["tipo"], escolhida["tipo"]),
                      "nome_da_situacao": NOME_DA_SITUACAO.get(escolhida["situacao"], escolhida["situacao"]),
                      "ficha": ficha, "corpo": corpo, "secoes": secoes_da_kb(corpo), "versoes": historico,
                      "vigencia": situacao_da_vigencia(escolhida["vigencia_inicio"], escolhida["vigencia_fim"]),
                      "tem_logo": tem_logo, "endereco_do_logo": endereco_do_logo})
    return resultado


def kbs_publicadas(conexao, dono: str | None = None, tipo: str | None = None, dia: date | None = None) -> list[dict]:
    """As versões PUBLICADAS e VIGENTES no dia (sem informar, hoje), do dono e do tipo pedidos.

    É o que vale para a vitrine da empresa e para o agente. Com dono, a Empresa A nunca recebe a KB da B.
    Cada item traz também a ficha e o corpo separados.
    """
    _preparar(conexao)
    dia_em_texto = (dia or date.today()).isoformat()
    consulta = conexao.execute(
        "SELECT " + ", ".join(COLUNAS_DA_KB) + " FROM kbs_endomarketing WHERE situacao = ? "
        "AND vigencia_inicio <= ? AND vigencia_fim >= ? AND (? IS NULL OR dono = ?) AND (? IS NULL OR tipo = ?) "
        "ORDER BY dono, tipo, titulo",
        (PUBLICADA, dia_em_texto, dia_em_texto, dono, dono, tipo, tipo),
    )
    kbs = []
    for linha in _linhas_em_kbs(consulta):
        ficha, corpo = separar_ficha(linha["conteudo_md"])
        linha.update({"ficha": ficha, "corpo": corpo})
        kbs.append(linha)
    return kbs


def listar_achados(conexao, dono: str | None = None, limite: int = 200) -> list[dict]:
    """Os achados gravados da trava, do mais recente para o mais antigo (para a Telemetria)."""
    _preparar(conexao)
    consulta = conexao.execute(
        "SELECT " + ", ".join(COLUNAS_DO_ACHADO) + " FROM kbs_achados_da_trava WHERE (? IS NULL OR dono = ?) "
        "ORDER BY feito_em DESC, kb_id LIMIT ?",
        (dono, dono, limite),
    )
    achados = []
    for linha in consulta:
        achados.append(dict(zip(COLUNAS_DO_ACHADO, linha)))
    return achados


def resumo_dos_achados(conexao, dono: str | None = None) -> dict:
    """Os três números da seção "Guardrails das KBs", contados em TODOS os achados gravados (do dono, ou de todos).

    Por quê: a lista da tela traz só os mais recentes (listar_achados, até 200); os números contam tudo, para nunca
    ficarem menores do que são.
    Recebe: conexao; dono (GERAL, SANTANDER, o código de uma empresa, ou None para todos).
    Devolve: {"bloqueios": ..., "avisos": ..., "kbs_com_achados": ...}. Ex.: {"bloqueios": 9, "avisos": 26,
    "kbs_com_achados": 15}.
    """
    _preparar(conexao)
    consulta = conexao.execute("SELECT kb_id, gravidade FROM kbs_achados_da_trava WHERE (? IS NULL OR dono = ?)",
                               (dono, dono))
    bloqueios = 0
    avisos = 0
    kbs_com_achados = set()
    for kb_id, gravidade in consulta:
        # O achado que impediu gravar ou publicar conta como bloqueio; o resto só avisou
        if gravidade == BLOQUEIA:
            bloqueios = bloqueios + 1
        else:
            avisos = avisos + 1
        # A KB entra uma vez só, tenha quantos achados tiver
        kbs_com_achados.add(kb_id)
    return {"bloqueios": bloqueios, "avisos": avisos, "kbs_com_achados": len(kbs_com_achados)}


def modelos() -> dict:
    """O que a tela precisa para criar uma KB: os tipos (com as seções e os donos permitidos) e as categorias."""
    tipos = []
    for tipo, secoes in SECOES_DO_TIPO.items():
        tipos.append({"tipo": tipo, "nome": NOME_DO_TIPO[tipo], "secoes": list(secoes),
                      "donos": list(DONOS_DO_TIPO[tipo])})
    return {"tipos": tipos, "categorias": list(catalogo.CATEGORIAS), "kits": [KIT_PROPRIO, KIT_PADRAO]}


# ---------------- 5. Gravar, publicar, retirar e revisar ----------------

def _slug(texto: str) -> str:
    """O texto em letras maiúsculas sem acento, com hífen no lugar dos espaços (para montar um id).

    Exemplo: "Cartão com cashback!" → "CARTAO-COM-CASHBACK".
    """
    palavras = re.findall(r"[a-z0-9]+", _normalizar(texto))
    return "-".join(palavras).upper()[:40].strip("-")


def novo_id(conexao, dono: str, tipo: str, titulo: str) -> str:
    """Um id que ainda não existe para uma KB nova: prefixo do dono, tipo e título (com número, se repetir).

    Exemplo: ("EMP001", "beneficio", "Pix sem tarifa") → "EMP001-BENEFICIO-PIX-SEM-TARIFA".
    """
    _preparar(conexao)
    prefixo = PREFIXO_DO_DONO.get(dono, dono)
    base = f"{prefixo}-{_slug(tipo)}-{_slug(titulo) or 'KB'}"
    candidato = base
    numero = 2
    # Se o id já existe, acrescenta -2, -3...
    while conexao.execute("SELECT 1 FROM kbs_endomarketing WHERE kb_id = ?", (candidato,)).fetchone():
        candidato = f"{base}-{numero}"
        numero += 1
    return candidato


def conteudo_do_formulario(conexao, ficha_recebida: dict, corpo: str, kb_id: str | None = None) -> str:
    """Monta o texto da KB com o que a tela enviou: a ficha (só as chaves do modelo, na ordem dele) e o corpo.

    Recebe: ficha_recebida (os campos do formulário); corpo (o Markdown das seções); kb_id (numa versão nova, o id da
    KB que está sendo editada; numa KB nova, None, e o id é criado aqui a partir do dono, do tipo e do título).
    Devolve: o texto completo, pronto para salvar ou conferir. Chave fora do modelo é ignorada.
    """
    ficha = {}
    for chave in ORDEM_DAS_CHAVES_DA_FICHA:
        ficha[chave] = str(ficha_recebida.get(chave) or "").strip()
    # O id: o da KB editada, ou um novo para uma KB nova
    if kb_id:
        ficha["id"] = kb_id
    elif not ficha["id"]:
        ficha["id"] = novo_id(conexao, ficha["dono"], ficha["tipo"], ficha["titulo"])
    return montar_conteudo(ficha, corpo)


def conteudo_do_kit_novo(conexao, empresa_id: str, nome_da_empresa: str, escolhido: str, texto: str,
                         cores: list[str], origem: str, dia: date | None = None) -> str:
    """O texto de uma KB do kit nova, para uma empresa que ainda não tem KB do kit, com o kit que ela já tem.

    Serve aos scripts que passam para a KB um kit que estava só no cadastro (scripts/migrar_kit_para_kb.py) ou que
    chega pronto (a carga da base viva). Recebe: o código e o nome da empresa; a escolha, o texto da identidade e as
    cores do kit; origem (de onde veio, para a ficha); dia (o começo da vigência; sem informar, hoje).
    Devolve: a KB inteira (ficha e seções), no modelo: a vigência vai até o fim do ano seguinte, e as seções que o
    cadastro não tem ganham um texto simples, que o especialista completa depois na tela.
    Exemplo de id: "EMP007-KIT-DA-MARCA" (se ele já existe, um id novo, como na tela).
    """
    _preparar(conexao)
    hoje = dia or date.today()
    titulo = f"Kit da marca {nome_da_empresa}"
    # O id de sempre do kit de uma empresa; já ocupado, um id novo
    kb_id = f"{empresa_id}-KIT-DA-MARCA"
    if conexao.execute("SELECT 1 FROM kbs_endomarketing WHERE kb_id = ?", (kb_id,)).fetchone():
        kb_id = novo_id(conexao, empresa_id, TIPO_DO_KIT, titulo)
    ficha = {"id": kb_id, "titulo": titulo, "tipo": TIPO_DO_KIT, "dono": empresa_id,
             "vigencia_inicio": hoje.isoformat(), "vigencia_fim": date(hoje.year + 1, 12, 31).isoformat(),
             "origem": origem, "kit_escolhido": escolhido, "cores": ", ".join(cores)}
    return montar_conteudo(ficha, _corpo_do_kit_novo(nome_da_empresa, texto, cores))


# O uso de cada cor do kit na arte, na ordem da ficha (a 1ª é a faixa de cima; a 2ª, o rodapé)
USOS_DAS_CORES = ("Principal (faixa e botões)", "Escura (rodapé e títulos)", "Fundo", "Texto", "Apoio (avisos)")


def _corpo_do_kit_novo(nome_da_empresa: str, texto: str, cores: list[str]) -> str:
    """As seções obrigatórias do kit, montadas com o que se sabe: a identidade (o texto) e as cores.

    As outras seções dizem que ainda não foram definidas, e o que vale enquanto isso.
    """
    linhas = [f"# Kit da marca {nome_da_empresa}", "", "## Identidade", texto or f"Kit da marca de {nome_da_empresa}.",
              "", "## Cores"]
    # As cores numa tabela (uso e cor), como nas KBs do projeto; sem cores, vale o padrão do banco
    if cores:
        linhas.append("| Uso | Cor |")
        linhas.append("|---|---|")
        for uso, cor in zip(USOS_DAS_CORES, cores):
            linhas.append(f"| {uso} | {cor} |")
    else:
        linhas.append("Usa as cores do kit padrão do banco.")
    linhas.extend(["", "## Tipografia", "Ainda não definida: a arte usa as fontes do molde.",
                   "", "## Logo", "O logo é a imagem anexada à versão desta KB. Sem ela, a arte mostra o nome da "
                                  "empresa em texto.",
                   "", "## Tom da marca", "Ainda não definido: vale a KB geral de tom de voz.",
                   "", "## Assinatura", f"\"{nome_da_empresa}\" e, no rodapé, \"Banco parceiro: Santander\".",
                   "", "## O que não fazer", "Ainda não definido: valem as diretrizes gerais."])
    return "\n".join(linhas)


def _conferir_id_existente(conexao, ficha: dict) -> list[dict]:
    """Uma versão nova não muda o dono nem o tipo da KB (o id é sempre da mesma KB)."""
    versoes = _versoes(conexao, ficha.get("id", ""))
    if not versoes:
        return []
    anterior = versoes[0]
    if anterior["dono"] != ficha.get("dono") or anterior["tipo"] != ficha.get("tipo"):
        return [_achado("Ficha", BLOQUEIA, "Uma versão nova não pode mudar o dono nem o tipo da KB.")]
    return []


def _versao_de_origem(conexao, kb_id: str, versao_de_origem: int | None) -> int | None:
    """A versão em que uma versão nova se baseia: a informada; senão a última da KB; numa KB nova, None.

    Exemplo: a KB tem as versões 1 (substituída) e 2 (publicada) → sem informar, a origem é a 2.
    """
    # Quem chama já sabe a origem (ex.: a revisão parte da versão publicada)
    if versao_de_origem is not None:
        return versao_de_origem
    versoes = _versoes(conexao, kb_id)
    # KB nova: não há de onde partir
    if not versoes:
        return None
    # A última versão (a lista vem da mais nova para a mais antiga)
    return versoes[0]["versao"]


def _tem_logo(conexao, kb_id: str, versao: int | None) -> bool:
    """Diz se a versão tem o logo anexado (versão None, de uma KB que ainda não existe: sem logo)."""
    if versao is None:
        return False
    return kit_de_marca.logo_da_versao(conexao, kb_id, versao) is not None


def salvar(conexao, autor: str, conteudo_md: str, versao_de_origem: int | None = None) -> dict:
    """Grava a KB como uma versão nova, em RASCUNHO, depois de passar pela trava.

    Recebe: conexao; autor (o login do especialista); conteudo_md (a KB inteira, com a ficha); versao_de_origem (a
    versão em que esta se baseia; sem informar, a última da KB). Na KB do kit, a versão nova nasce com o logo da
    versão de origem (a tela troca ou tira o logo depois, no rascunho).
    Devolve: {kb_id, versao, situacao, achados}. Achado que bloqueia: grava os achados e levanta TravaBloqueou.
    A versão publicada (se houver) continua valendo até esta ser publicada.
    """
    _preparar(conexao)
    ficha, _ = separar_ficha(conteudo_md)
    kb_id = ficha.get("id") or "(sem id)"
    dono = ficha.get("dono") or "?"
    # A versão de onde vem o logo: a trava conta o logo que a versão nova vai herdar
    origem = _versao_de_origem(conexao, kb_id, versao_de_origem)
    achados = conferir(conexao, conteudo_md, tem_logo=_tem_logo(conexao, kb_id, origem))
    achados = achados + _conferir_id_existente(conexao, ficha)
    if tem_bloqueio(achados):
        _gravar_achados(conexao, kb_id, None, dono, SALVAR, achados, autor)
        raise TravaBloqueou(achados)
    versao = _inserir_versao(conexao, ficha, conteudo_md, RASCUNHO, autor)
    # A KB do kit leva junto o logo da versão de origem (sem origem ou sem logo nela, a versão nova fica sem)
    if ficha.get("tipo") == TIPO_DO_KIT and origem is not None:
        kit_de_marca.copiar_logo_da_versao(conexao, kb_id, origem, versao)
    _gravar_achados(conexao, kb_id, versao, dono, SALVAR, achados, autor)
    return {"kb_id": kb_id, "versao": versao, "situacao": RASCUNHO, "achados": achados}


def verificar(conexao, autor: str, conteudo_md: str) -> list[dict]:
    """Roda a trava sem gravar a KB (o botão "Conferir" da tela). Os achados ficam gravados mesmo assim.

    O logo conta como na gravação: a versão nova herdaria o logo da última versão da KB (numa KB nova, nenhum).
    """
    _preparar(conexao)
    ficha, _ = separar_ficha(conteudo_md)
    kb_id = ficha.get("id") or "(sem id)"
    # A versão que a gravação tomaria como origem (a última), e se ela tem logo
    tem_logo = _tem_logo(conexao, kb_id, _versao_de_origem(conexao, kb_id, None))
    achados = conferir(conexao, conteudo_md, tem_logo=tem_logo)
    _gravar_achados(conexao, kb_id, None, ficha.get("dono") or "?", VERIFICAR, achados, autor)
    return achados


def publicar(conexao, autor: str, kb_id: str, versao: int, momento: str = PUBLICAR) -> dict:
    """Publica uma versão (rascunho ou retirada): ela passa a valer, e a publicada de antes vira SUBSTITUIDA.

    A trava roda de novo (a lista de termos pode ter mudado desde o rascunho). Devolve a KB publicada (ver obter).
    KeyError se a versão não existe; ValueError se ela já está publicada ou foi substituída.
    """
    _preparar(conexao)
    escolhida = _versao(conexao, kb_id, versao)
    if escolhida["situacao"] not in (RASCUNHO, RETIRADA):
        raise ValueError("Só um rascunho ou uma versão retirada pode ser publicada.")
    # O logo que conta é o anexado a esta versão
    achados = conferir(conexao, escolhida["conteudo_md"], tem_logo=_tem_logo(conexao, kb_id, versao))
    _gravar_achados(conexao, kb_id, versao, escolhida["dono"], momento, achados, autor)
    if tem_bloqueio(achados):
        raise TravaBloqueou(achados)
    # A publicada de antes deixa de valer
    conexao.execute("UPDATE kbs_endomarketing SET situacao = ? WHERE kb_id = ? AND situacao = ?",
                    (SUBSTITUIDA, kb_id, PUBLICADA))
    conexao.execute("UPDATE kbs_endomarketing SET situacao = ?, publicado_em = ?, publicado_por = ? "
                    "WHERE kb_id = ? AND versao = ?", (PUBLICADA, _agora(), autor, kb_id, versao))
    conexao.commit()
    return obter(conexao, kb_id, versao)


def retirar(conexao, autor: str, kb_id: str) -> dict:
    """Retira a versão publicada: a KB deixa de valer para a vitrine e para o agente (as versões ficam guardadas).

    Devolve a KB (ver obter). KeyError se a KB não existe; ValueError se ela não tem versão publicada.
    """
    _preparar(conexao)
    publicada = versao_publicada(conexao, kb_id)
    if publicada is None:
        # Distingue "não existe" (404) de "não está publicada" (400)
        if not _versoes(conexao, kb_id):
            raise KeyError(kb_id)
        raise ValueError("Esta KB não tem versão publicada para retirar.")
    conexao.execute("UPDATE kbs_endomarketing SET situacao = ? WHERE kb_id = ? AND versao = ?",
                    (RETIRADA, kb_id, publicada["versao"]))
    conexao.commit()
    return obter(conexao, kb_id, publicada["versao"])


def revisar(conexao, autor: str, kb_id: str, nova_vigencia_fim: str, dia: date | None = None) -> dict:
    """Revisa uma KB vencida ou vencendo: grava uma versão nova com a vigência renovada.

    Recebe: autor; kb_id; nova_vigencia_fim (AAAA-MM-DD, depois de hoje). A versão nova parte da publicada (ou da
    última). Se partiu da publicada, já é publicada (a revisão confere o conteúdo); senão, fica como rascunho.
    Devolve a KB revisada (ver obter).
    """
    _preparar(conexao)
    hoje = dia or date.today()
    try:
        fim = date.fromisoformat(nova_vigencia_fim)
    except ValueError:
        raise ValueError("Informe a nova data de fim da vigência (AAAA-MM-DD).")
    if fim <= hoje:
        raise ValueError("A nova vigência precisa terminar depois de hoje.")
    versoes = _versoes(conexao, kb_id)
    if not versoes:
        raise KeyError(kb_id)
    origem = versao_publicada(conexao, kb_id) or versoes[0]
    ficha, corpo = separar_ficha(origem["conteudo_md"])
    # Só o fim da vigência muda; o início fica como estava
    ficha["vigencia_fim"] = nova_vigencia_fim
    conteudo_revisado = montar_conteudo(ficha, corpo)
    # A versão revisada parte da de origem (e leva o logo dela, na KB do kit)
    resultado = salvar(conexao, autor, conteudo_revisado, versao_de_origem=origem["versao"])
    if origem["situacao"] == PUBLICADA:
        return publicar(conexao, autor, kb_id, resultado["versao"], REVISAR)
    return obter(conexao, kb_id, resultado["versao"])


# ---------------- 6. O logo da KB do kit (uma imagem anexada à versão) ----------------

def _versao_do_kit(conexao, kb_id: str, versao: int) -> dict:
    """A versão pedida de uma KB do kit. KeyError se ela não existe; ValueError se a KB não é do kit da marca."""
    _preparar(conexao)
    escolhida = _versao(conexao, kb_id, versao)
    # Só a KB do kit tem logo (um benefício, por exemplo, não tem)
    if escolhida["tipo"] != TIPO_DO_KIT:
        raise ValueError("Só a KB do kit da marca tem logo.")
    return escolhida


def _rascunho_do_kit(conexao, kb_id: str, versao: int) -> dict:
    """A versão da KB do kit, conferindo que ela é um RASCUNHO (só o rascunho recebe ou perde o logo).

    Por quê: a versão publicada é a que vale para a arte; trocar o logo dela mudaria a arte sem passar pela
    publicação. Para mudar o logo, grava-se uma versão nova (que nasce com o logo da anterior) e troca-se nela.
    """
    escolhida = _versao_do_kit(conexao, kb_id, versao)
    if escolhida["situacao"] != RASCUNHO:
        raise ValueError("Só um rascunho recebe ou perde o logo. Grave uma versão nova e troque o logo nela.")
    return escolhida


def anexar_logo_ao_rascunho(conexao, autor: str, kb_id: str, versao: int, conteudo: bytes) -> dict:
    """Anexa (ou troca) o logo de um rascunho da KB do kit. Devolve {kb_id, versao, tem_logo: True}.

    Recebe: autor (o login do especialista); kb_id e versao; conteudo (os bytes da imagem enviada).
    KeyError se a versão não existe; ValueError se a KB não é do kit, se a versão não é rascunho ou se a imagem não
    passa na conferência (PNG ou JPEG de verdade, pela assinatura, com até 500 KB).
    """
    _rascunho_do_kit(conexao, kb_id, versao)
    kit_de_marca.gravar_logo_da_versao(conexao, kb_id, versao, conteudo, autor)
    return {"kb_id": kb_id, "versao": versao, "tem_logo": True}


def tirar_logo_do_rascunho(conexao, kb_id: str, versao: int) -> dict:
    """Tira o logo de um rascunho da KB do kit. Devolve {kb_id, versao, tem_logo: False}.

    KeyError se a versão não existe; ValueError se a KB não é do kit ou se a versão não é rascunho.
    """
    _rascunho_do_kit(conexao, kb_id, versao)
    kit_de_marca.tirar_logo_da_versao(conexao, kb_id, versao)
    return {"kb_id": kb_id, "versao": versao, "tem_logo": False}


def imagem_do_logo(conexao, kb_id: str, versao: int) -> tuple[bytes, str]:
    """O logo de uma versão da KB do kit, em qualquer situação: (bytes da imagem, tipo).

    KeyError se a versão não existe ou não tem logo (vira 404); ValueError se a KB não é do kit.
    """
    _versao_do_kit(conexao, kb_id, versao)
    encontrado = kit_de_marca.logo_da_versao(conexao, kb_id, versao)
    # A versão existe, mas está sem logo
    if encontrado is None:
        raise KeyError(kb_id)
    return encontrado
