"""Monta os arquivos que as empresas enviam e o gabarito (golden) de cada um.

Cada empresa exporta do seu sistema de RH de um jeito: nomes de coluna diferentes, formatos de data e
de número diferentes, cabeçalho fora do lugar. E alguns erros são colocados de propósito, com o
gabarito dizendo exatamente qual erro está em qual linha, para as fases seguintes serem testadas.

Chamado por scripts/gerar_dados.py.
"""
import csv
import json
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

# Pastas do projeto: a raiz, os arquivos das empresas e os gabaritos
RAIZ = Path(__file__).resolve().parent.parent
PASTA_ENVIOS = RAIZ / "data" / "synthetic" / "envios"
PASTA_GOLDEN = RAIZ / "data" / "golden"

# As informações que as empresas fictícias têm no sistema de RH delas, na ordem em que exportam. É a lista do layout v1
# de quando o mundo sintético foi medido (EXP-001 a EXP-015), CONGELADA aqui de propósito (ADR-128): quando o banco
# muda o parâmetro (ex.: tira um campo na tela Parâmetros), as empresas continuam mandando as mesmas colunas, e o
# sorteio dos cabeçalhos continua o mesmo. Assim os arquivos, os gabaritos e as medições não mudam por causa de um
# parâmetro.
CAMPOS_DO_MUNDO_SINTETICO = (
    "matricula", "nome_completo", "cpf", "data_nascimento", "sexo", "estado_civil", "nome_mae", "nacionalidade",
    "municipio_naturalidade", "uf_naturalidade", "nis_pis", "escolaridade", "tipo_documento", "numero_documento",
    "orgao_emissor", "uf_emissor", "data_emissao_documento", "cep_residencial", "logradouro_residencial",
    "numero_residencial", "complemento_residencial", "bairro_residencial", "municipio_residencial", "uf_residencial",
    "telefone_residencial", "telefone_celular", "email_pessoal", "email_corporativo", "cnpj_empregador", "cnpj_grupo",
    "codigo_unidade", "nome_unidade", "cargo", "data_admissao", "data_efetivacao", "tipo_renda", "valor_renda",
    "data_referencia_renda", "cep_comercial", "logradouro_comercial", "numero_comercial", "complemento_comercial",
    "bairro_comercial", "municipio_comercial", "uf_comercial",
)

# Os campos que passaram a ser obrigatórios depois que o mundo sintético foi medido, com o nome simples da coluna
# (ADR-128: o sexo). A empresa que ainda não mandava acrescenta a coluna no FIM da exportação, com esse nome e sem
# sorteio: assim as outras colunas, os cabeçalhos e os sorteios continuam os mesmos.
OBRIGATORIOS_ACRESCENTADOS_NO_FIM = {"sexo": "Sexo"}

# Campos obrigatórios do layout: toda empresa envia
OBRIGATORIOS = [
    "matricula", "nome_completo", "cpf", "data_nascimento", "cep_residencial", "logradouro_residencial",
    "numero_residencial", "bairro_residencial", "municipio_residencial", "uf_residencial", "cnpj_empregador",
    "codigo_unidade", "nome_unidade", "cargo", "data_admissao", "tipo_renda", "valor_renda",
    "data_referencia_renda", "cep_comercial", "logradouro_comercial", "numero_comercial", "bairro_comercial",
    "municipio_comercial", "uf_comercial",
]

# Como cada empresa exporta:
# - tipo: xlsx ou csv; separador e codificacao valem para o csv
# - data: formato das datas no texto (sem ele, no Excel vai data de verdade)
# - valor: "virgula" (3150,00) ou "reais_texto" (R$ 3.150,00)
# - numeros_como_numero: CPF e matrícula gravados como número (perdem os zeros à esquerda)
# - embaralhar: colunas fora da ordem do layout
# - linhas_antes_do_cabecalho: títulos em cima da tabela
# - extras: colunas que não existem no layout (nome -> valor)
# - cabecalho_fixo: campo -> nome de coluna escolhido de propósito (ex.: a coluna ambígua)
# - opcionais: campos a mais que ela envia, além dos obrigatórios ("todos" = o layout inteiro)
FORMATOS = {
    "EMP001": {"tipo": "xlsx", "opcionais": ["email_corporativo", "telefone_celular", "data_efetivacao"]},
    "EMP002": {"tipo": "csv", "separador": ";", "codificacao": "cp1252", "data": "%d/%m/%Y", "valor": "virgula",
               "opcionais": ["telefone_celular", "sexo", "estado_civil"]},
    "EMP003": {"tipo": "xlsx", "numeros_como_numero": True, "embaralhar": True,
               "opcionais": ["email_pessoal", "email_corporativo", "data_efetivacao", "escolaridade"]},
    "EMP004": {"tipo": "xlsx", "linhas_antes_do_cabecalho": ["Relatório de funcionários - Vale Verde Serviços",
                                                              "Gerado em 01/09/2026", ""],
               "extras": {"Obs. RH": "ok", "Cód. Interno": "VV"}, "opcionais": "todos"},
    "EMP005": {"tipo": "csv", "separador": ",", "codificacao": "utf-8", "data": "%d/%m/%Y", "valor": "reais_texto",
               "embaralhar": True, "opcionais": ["telefone_residencial", "complemento_residencial"]},
    "EMP006": {"tipo": "xlsx", "cabecalho_fixo": {"valor_renda": "Vencimentos"},
               "opcionais": ["nome_mae", "nis_pis", "data_efetivacao"]},
}


def _vocabulario_treino() -> dict[str, list[str]]:
    """Nomes de coluna do vocabulário de TREINO (o de teste fica guardado para a avaliação)."""
    termos = {}
    with open(RAIZ / "data" / "vocabulario" / "treino.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            termos.setdefault(linha["campo"], []).append(linha["termo"])
    return termos


def _campos_enviados(formato: dict, campos_do_layout: list[str], sorteio: random.Random) -> list[str]:
    """Os campos que a empresa envia: os obrigatórios mais os opcionais dela, na ordem do layout
    (ou embaralhados, se a empresa exporta fora de ordem)."""
    if formato["opcionais"] == "todos":
        opcionais = campos_do_layout
    else:
        opcionais = formato["opcionais"]
    campos = []
    for campo in campos_do_layout:
        if campo in OBRIGATORIOS or campo in opcionais:
            campos.append(campo)
    if formato.get("embaralhar"):
        sorteio.shuffle(campos)
    return campos


def _cabecalhos(campos: list[str], formato: dict, sorteio: random.Random) -> dict[str, str]:
    """Campo -> nome da coluna no arquivo da empresa."""
    vocabulario = _vocabulario_treino()
    nomes_fixos = formato.get("cabecalho_fixo", {})
    cabecalhos = {}
    for campo in campos:
        if campo in nomes_fixos:
            # Nome escolhido de propósito: não sorteia (e não gasta sorteio)
            cabecalhos[campo] = nomes_fixos[campo]
        else:
            # Sorteia um dos nomes que esse campo costuma ter
            cabecalhos[campo] = sorteio.choice(vocabulario[campo])
    return cabecalhos


def _formatar(valor: str, campo: str, formato: dict):
    """Converte o valor correto (do gabarito) para o jeito que a empresa exporta."""
    # Vazio continua vazio
    if valor == "":
        return ""
    if campo.startswith("data_"):
        dia = date.fromisoformat(valor)
        # Com formato de data, vira texto (ex.: 01/09/2026); sem, vai como data de verdade para o Excel
        if "data" in formato:
            return dia.strftime(formato["data"])
        return dia
    if campo == "valor_renda":
        numero = Decimal(valor)
        # "3150,00": vírgula no lugar do ponto
        if formato.get("valor") == "virgula":
            return f"{numero:.2f}".replace(".", ",")
        # "R$ 3.150,00": o Python escreve 3,150.00; trocamos vírgula e ponto de lugar (o # é só temporário)
        if formato.get("valor") == "reais_texto":
            no_formato_americano = f"{numero:,.2f}"
            no_formato_brasileiro = no_formato_americano.replace(",", "#").replace(".", ",").replace("#", ".")
            return "R$ " + no_formato_brasileiro
        # Sem formato especial: número no Excel, texto no CSV
        if formato["tipo"] == "xlsx":
            return float(numero)
        return str(numero)
    if campo in ("cpf", "matricula") and formato.get("numeros_como_numero"):
        # O Excel guarda como número e perde os zeros à esquerda
        return int(valor)
    return valor


def _gravar(caminho: Path, cabecalho: list[str], linhas: list[list], formato: dict) -> None:
    """Grava o arquivo da empresa em CSV ou Excel."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if formato["tipo"] == "csv":
        with open(caminho, "w", encoding=formato["codificacao"], newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=formato["separador"])
            escritor.writerow(cabecalho)
            escritor.writerows(linhas)
        return
    # Excel: uma aba "Funcionarios", com os títulos (se houver) em cima do cabeçalho
    planilha = Workbook()
    aba = planilha.active
    aba.title = "Funcionarios"
    for texto in formato.get("linhas_antes_do_cabecalho", []):
        aba.append([texto])
    aba.append(cabecalho)
    for linha in linhas:
        aba.append(linha)
    planilha.save(caminho)


def _montar_arquivo(nome: str, empresa: dict, funcionarios: list[dict], formato: dict, cabecalhos: dict,
                    tipo_carga: str, erros_a_injetar: list[tuple], repetir: list[tuple] = ()) -> dict:
    """Monta um arquivo e devolve o gabarito dele.

    erros_a_injetar: (linha, campo, tipo, valor_errado); linha começa em 1 (primeira linha de dados).
    repetir: (linha_origem, linha_destino) para colocar uma pessoa duas vezes no arquivo.
    """
    campos = list(cabecalhos)
    extras = formato.get("extras", {})
    # Uma cópia de cada funcionário, para os erros não estragarem o gabarito original
    registros = []
    for funcionario in funcionarios:
        registros.append(dict(funcionario))
    # Pessoas repetidas de propósito
    for origem, destino in repetir:
        registros.insert(destino - 1, dict(registros[origem - 1]))

    # Coloca os erros e anota cada um no gabarito
    erros = []
    for linha, campo, tipo, valor_errado in erros_a_injetar:
        registros[linha - 1][campo] = valor_errado
        erros.append({"linha": linha, "campo": campo, "tipo": tipo, "valor_no_arquivo": valor_errado})
    for origem, destino in repetir:
        erros.append({"linha": destino, "campo": "matricula", "tipo": "PESSOA_DUPLICADA_NO_ARQUIVO",
                      "valor_no_arquivo": registros[destino - 1]["matricula"], "repete_a_linha": origem})

    # Valor escrito por extenso ("três mil...") não é número: vai para o arquivo exatamente como está
    celulas_sem_formatacao = set()
    for erro in erros:
        if erro["tipo"] == "VALOR_COMO_TEXTO":
            celulas_sem_formatacao.add((erro["linha"], erro["campo"]))
    # A linha de cabeçalho: os nomes das colunas do layout e depois as colunas extras
    cabecalho = []
    for campo in campos:
        cabecalho.append(cabecalhos[campo])
    cabecalho.extend(extras)
    # As linhas de dados, já no formato da empresa
    linhas = []
    for numero_da_linha, registro in enumerate(registros, start=1):
        linha = []
        for campo in campos:
            if (numero_da_linha, campo) in celulas_sem_formatacao:
                linha.append(registro[campo])
            else:
                linha.append(_formatar(registro[campo], campo, formato))
        linha.extend(extras.values())
        linhas.append(linha)
    _gravar(PASTA_ENVIOS / nome, cabecalho, linhas, formato)

    # Colunas com nome escolhido de propósito são as ambíguas: exigem confirmação humana
    colunas_ambiguas = {}
    for campo in formato.get("cabecalho_fixo", {}):
        colunas_ambiguas[cabecalhos[campo]] = {"campo_apos_confirmacao": campo,
                                               "por_que": "pode ser salário bruto, líquido ou valor do crédito"}
    # Mapeamento esperado: coluna -> campo (a ambígua fica sem campo até a confirmação)
    mapeamento = {}
    for campo in campos:
        coluna = cabecalhos[campo]
        if coluna in colunas_ambiguas:
            mapeamento[coluna] = None
        else:
            mapeamento[coluna] = campo
    # Quem está em cada linha do arquivo
    funcionario_ids = []
    for registro in registros:
        funcionario_ids.append(registro["funcionario_id"])
    return {
        "arquivo": nome,
        "empresa_id": empresa["id"],
        "tipo_carga": tipo_carga,
        "desafio": empresa["desafio"],
        "formato": {"tipo": formato["tipo"], "separador": formato.get("separador"),
                    "codificacao": formato.get("codificacao"),
                    "linha_do_cabecalho": len(formato.get("linhas_antes_do_cabecalho", [])) + 1},
        "mapeamento": mapeamento,
        "colunas_ambiguas": colunas_ambiguas,
        "colunas_extras": list(extras),
        "funcionario_ids": funcionario_ids,
        "erros": erros,
    }


def _linha_do_cargo(funcionarios: list[dict], cargo: str, padrao: int) -> int:
    """Primeira linha (1..n) com o cargo pedido; se não houver, a linha padrão."""
    for numero_da_linha, funcionario in enumerate(funcionarios, start=1):
        if funcionario["cargo"] == cargo:
            return numero_da_linha
    return padrao


def _funcionarios_da_empresa(funcionarios: list[dict], empresa_id: str, carga: str) -> list[dict]:
    """Os funcionários de uma empresa numa carga (INICIAL ou INCLUSAO), na ordem do gabarito."""
    selecionados = []
    for funcionario in funcionarios:
        if funcionario["empresa_id"] == empresa_id and funcionario["carga"] == carga:
            selecionados.append(funcionario)
    return selecionados


def _erros_da_carga_inicial(empresa_id: str, iniciais: list[dict]) -> tuple[list, list]:
    """Os erros colocados de propósito na carga inicial de cada empresa, e as pessoas repetidas."""
    erros, repetir = [], []
    if empresa_id == "EMP001":
        # CPF com o último dígito trocado: o dígito verificador deixa de bater
        cpf = iniciais[6]["cpf"]
        ultimo_digito_errado = str((int(cpf[-1]) + 1) % 10)
        erros.append((7, "cpf", "CPF_INVALIDO", cpf[:-1] + ultimo_digito_errado))
    elif empresa_id == "EMP002":
        erros.append((12, "data_admissao", "CAMPO_OBRIGATORIO_VAZIO", ""))
    elif empresa_id == "EMP003":
        # Um diretor ganhando R$ 1.100
        erros.append((_linha_do_cargo(iniciais, "Diretor", 5), "valor_renda", "RENDA_FORA_DO_CARGO", "1100.00"))
    elif empresa_id == "EMP004":
        # A linha 20 com a mesma matrícula da linha 19
        erros.append((20, "matricula", "MATRICULA_DUPLICADA", iniciais[18]["matricula"]))
    elif empresa_id == "EMP005":
        erros.append((9, "valor_renda", "VALOR_COMO_TEXTO", "três mil e cem reais"))
        # A pessoa da linha 29 aparece de novo na linha 30
        repetir.append((29, 30))
    elif empresa_id == "EMP006":
        # Um analista com a renda multiplicada por 10 (zero a mais)
        linha = _linha_do_cargo(iniciais, "Analista", 3)
        dez_vezes = str(Decimal(iniciais[linha - 1]["valor_renda"]) * 10)
        erros.append((linha, "valor_renda", "RENDA_FORA_DO_CARGO", dez_vezes))
        # Um auxiliar administrativo ganhando R$ 38.000
        erros.append((_linha_do_cargo(iniciais, "Auxiliar administrativo", 4), "valor_renda",
                      "RENDA_FORA_DO_CARGO", "38000.00"))
    return erros, repetir


def montar_envios(sorteio: random.Random, empresas: list[dict], funcionarios: list[dict]) -> list[str]:
    """Gera as cargas iniciais, as inclusões e os gabaritos. Devolve os nomes dos arquivos."""
    # As colunas que as empresas fictícias exportam: a lista congelada do mundo sintético (e não o layout vigente)
    campos_do_layout = list(CAMPOS_DO_MUNDO_SINTETICO)
    PASTA_GOLDEN.mkdir(parents=True, exist_ok=True)
    gabaritos, cabecalhos_por_empresa = [], {}

    # Cargas iniciais
    for empresa in empresas:
        formato = FORMATOS[empresa["id"]]
        iniciais = _funcionarios_da_empresa(funcionarios, empresa["id"], "INICIAL")
        campos = _campos_enviados(formato, campos_do_layout, sorteio)
        cabecalhos = _cabecalhos(campos, formato, sorteio)
        # O obrigatório novo que a empresa ainda não mandava entra no fim, com o nome simples (sem sorteio)
        for campo, nome_da_coluna in OBRIGATORIOS_ACRESCENTADOS_NO_FIM.items():
            if campo not in cabecalhos:
                cabecalhos[campo] = nome_da_coluna
        cabecalhos_por_empresa[empresa["id"]] = cabecalhos
        erros, repetir = _erros_da_carga_inicial(empresa["id"], iniciais)
        gabaritos.append(_montar_arquivo(empresa["arquivo"], empresa, iniciais, formato, cabecalhos,
                                         "INICIAL", erros, repetir))

    # Arquivos de inclusão (ADR-23, ADR-24)
    empresa_por_id = {}
    for empresa in empresas:
        empresa_por_id[empresa["id"]] = empresa
    novos = {}
    for empresa_id in ("EMP001", "EMP002", "EMP003"):
        novos[empresa_id] = _funcionarios_da_empresa(funcionarios, empresa_id, "INCLUSAO")
    # Aurora: mesmas colunas da carga inicial -> o mapeamento homologado deve ser reaproveitado
    gabaritos.append(_montar_arquivo("aurora_inclusao.xlsx", empresa_por_id["EMP001"], novos["EMP001"],
                                     FORMATOS["EMP001"], cabecalhos_por_empresa["EMP001"], "INCLUSAO", []))
    # Horizonte: colunas com outros nomes (sorteio próprio, semente 7) -> a IA precisa interpretar de novo
    outros_nomes = _cabecalhos(list(cabecalhos_por_empresa["EMP002"]), FORMATOS["EMP002"], random.Random(7))
    gabaritos.append(_montar_arquivo("horizonte_inclusao.csv", empresa_por_id["EMP002"], novos["EMP002"],
                                     FORMATOS["EMP002"], outros_nomes, "INCLUSAO", []))
    # Brisa: um "novo" funcionário que já estava na carga inicial -> pendência de duplicidade
    ja_existente = _funcionarios_da_empresa(funcionarios, "EMP003", "INICIAL")[0]
    gabarito_brisa = _montar_arquivo("brisa_inclusao.xlsx", empresa_por_id["EMP003"], novos["EMP003"] + [ja_existente],
                                     FORMATOS["EMP003"], cabecalhos_por_empresa["EMP003"], "INCLUSAO", [])
    gabarito_brisa["erros"].append({"linha": len(novos["EMP003"]) + 1, "campo": "cpf",
                                    "tipo": "JA_HOMOLOGADO_NA_EMPRESA", "valor_no_arquivo": ja_existente["cpf"]})
    gabaritos.append(gabarito_brisa)

    # Grava um gabarito JSON por arquivo, com o mesmo nome do arquivo
    nomes_dos_arquivos = []
    for gabarito in gabaritos:
        destino = PASTA_GOLDEN / (Path(gabarito["arquivo"]).stem + ".json")
        destino.write_text(json.dumps(gabarito, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        nomes_dos_arquivos.append(gabarito["arquivo"])
    return nomes_dos_arquivos
