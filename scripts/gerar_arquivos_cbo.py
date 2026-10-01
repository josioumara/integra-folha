"""Gera os arquivos de teste da faixa salarial por profissão (CBO) e o registro do resultado esperado (ADR-129).

Para que serve: testar a comparação do salário com a faixa da profissão, enviando estes arquivos na tela
(pasta D:\\AI_Payroll_Hub\\Imports_Arquivos_CBO). Cada arquivo tem um objetivo, e o REGISTRO_IMPORTS_CBO.txt diz, para
cada um, o que se deve ver.

Regras deste gerador (a cláusula de generalização do pedido):
- dados 100% sintéticos, feitos aqui do zero: nomes sorteados de listas curtas, CPF sorteado com o dígito certo
  (services/documentos.gerar_cpf), endereços inventados. Nada vem da pasta Imports_Arquivos nem das capturas do QA;
- os salários são postos EM VOLTA da faixa de verdade da profissão (data/cbo/faixas_salariais_cbo.csv): no meio, no
  limite, um centavo fora, muito fora. Assim o arquivo continua valendo se a faixa for recalculada;
- cada caso tem pelo menos 3 variações (nome da coluna, jeito de escrever o código, palavras do cargo).

Como rodar (da pasta integra-folha; depois de scripts/calcular_faixas_cbo.py):
    .venv\\Scripts\\python.exe scripts\\gerar_arquivos_cbo.py [pasta de destino]
"""
import csv
import random
import sys
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

# Pasta raiz do projeto, para importar os serviços
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from services import tabela_cbo  # noqa: E402
from services.documentos import gerar_cpf  # noqa: E402



def pasta_padrao() -> Path:
    """A pasta de destino padrão: ao lado da pasta integra-folha, junto de Imports_Arquivos (que nunca é alterada).

    Numa cópia isolada do repositório (integra-folha/.claude/worktrees/<cópia>), sobe até a integra-folha de verdade.
    """
    raiz_do_repositorio = RAIZ
    if ".claude" in RAIZ.parts:
        posicao = RAIZ.parts.index(".claude")
        raiz_do_repositorio = Path(*RAIZ.parts[:posicao])
    return raiz_do_repositorio.parent / "Imports_Arquivos_CBO"
# O arquivo das faixas calculadas
ARQUIVO_DAS_FAIXAS = RAIZ / "data" / "cbo" / "faixas_salariais_cbo.csv"
# A empresa dos arquivos: a Aurora (EMP001), a do usuário de teste teste.empresa
CNPJ_DA_EMPRESA = "10433218000193"
# O sorteio sempre com a mesma semente: gerar de novo dá os mesmos arquivos
SEMENTE = 20260929

# Os pedaços dos nomes sintéticos
PRIMEIROS_NOMES = ("Lia", "Caio", "Nara", "Otto", "Iara", "Davi", "Mel", "Enzo", "Rute", "Ciro", "Tais", "Ivo")
SOBRENOMES = ("Moraes", "Teles", "Queiroz", "Bastos", "Paiva", "Rocha", "Dantas", "Leal", "Viana", "Amaral")
# As colunas de cada arquivo (o nome que a empresa usa), na ordem; a coluna do CBO entra depois do cargo
COLUNAS = ("Matrícula", "Nome completo", "CPF", "Nascimento", "Sexo", "Estado civil", "CEP", "Rua", "Número", "Bairro",
           "Cidade", "UF", "Celular", "CNPJ", "Unidade", "Nome da unidade", "Cargo", "Admissão", "Vínculo",
           "Salário bruto", "Competência", "CEP da unidade", "Endereço da unidade", "Nº da unidade",
           "Bairro da unidade", "Cidade da unidade", "UF da unidade")

# Os casos: (arquivo, nome da coluna do CBO ou None, objetivo, pessoas)
# Cada pessoa: (cargo, código como está escrito, vínculo, onde fica o salário, o que se espera)
# Onde fica o salário: MEIO (no meio da faixa), MINIMO, MAXIMO (nos limites), ABAIXO / ACIMA (um centavo fora),
# DIGITACAO_BAIXA (o salário dividido por 1.000, como "2.500" lido "2,50"), DIGITACAO_ALTA (vezes 100),
# OUTRAS_ALTO (dentro da faixa pública, mas acima da faixa das outras empresas preparadas no servidor de teste)
CASOS = (
    ("01_com_cbo_todos_na_faixa.csv", "Código CBO",
     "Coluna do CBO com traço; todos os salários dentro da faixa, inclusive nos limites.", (
         ("Assistente administrativo", "4110-10", "CLT", "MEIO", "nada"),
         ("Técnico de enfermagem", "3222-05", "CLT", "MINIMO", "nada"),
         ("Operador de caixa", "4211-25", "CLT", "MAXIMO", "nada"),
         ("Almoxarife", "4141-05", "CLT", "MEIO", "nada"),
     )),
    ("02_com_cbo_salarios_fora.xlsx", "CBO",
     "Coluna do CBO só com dígitos; erros de digitação e salários um centavo fora da faixa.", (
         ("Assistente administrativo", "411010", "CLT", "DIGITACAO_BAIXA", "RENDA_FORA_DA_PROFISSAO"),
         ("Motorista de caminhão", "782510", "CLT", "DIGITACAO_ALTA", "RENDA_FORA_DA_PROFISSAO"),
         ("Recepcionista", "422105", "CLT", "ABAIXO", "RENDA_FORA_DA_PROFISSAO"),
         ("Almoxarife", "414105", "CLT", "ACIMA", "RENDA_FORA_DA_PROFISSAO"),
         ("Técnico de enfermagem", "322205", "CLT", "MEIO", "nada"),
     )),
    ("03_cbo_em_formatos_variados.csv", "Cód. Ocupação",
     "O mesmo código escrito de jeitos diferentes: com ponto, com espaço, só dígitos e com barra.", (
         ("Assist. administrativo", "4110.10", "CLT", "MEIO", "nada"),
         ("Assistente adm", "4110 10", "CLT", "DIGITACAO_BAIXA", "RENDA_FORA_DA_PROFISSAO"),
         ("Assistente Administrativa", "411010", "CLT", "ACIMA", "RENDA_FORA_DA_PROFISSAO"),
         ("Assistente administrativo II", "4110/10", "CLT", "MINIMO", "nada"),
     )),
    ("04_cbo_que_nao_existe.xlsx", "Ocupação CBO",
     "Códigos que não existem na CBO ou não têm o desenho dela: alerta no código, e o salário não é comparado.", (
         ("Assistente administrativo", "9999-99", "CLT", "DIGITACAO_BAIXA", "CBO_DESCONHECIDO"),
         ("Almoxarife", "4141", "CLT", "MEIO", "CBO_DESCONHECIDO"),
         ("Recepcionista", "recepção", "CLT", "MEIO", "CBO_DESCONHECIDO"),
         ("Operador de caixa", "4211-25", "CLT", "MEIO", "nada"),
     )),
    ("05_sem_cbo_cargos_da_tabela.csv", None,
     "Sem a coluna do CBO: a profissão sai do nome do cargo e a empresa confirma uma vez por cargo (plural, "
     "feminino, abreviação e nível na carreira não mudam a profissão).", (
         ("Técnica de Enfermagem", "", "CLT", "DIGITACAO_BAIXA",
          "CBO_A_CONFIRMAR (3222-05); depois do \"Está certo assim\": RENDA_FORA_DA_PROFISSAO"),
         ("TÉCNICA DE ENFERMAGEM", "", "CLT", "MEIO", "segue a resposta da linha de cima (mesmo cargo)"),
         ("Operadores de caixa", "", "CLT", "ACIMA",
          "CBO_A_CONFIRMAR (4211-25); depois do \"Está certo assim\": RENDA_FORA_DA_PROFISSAO"),
         ("Recepcionista Pleno", "", "CLT", "MEIO", "CBO_A_CONFIRMAR (4221-05)"),
         ("Almoxarife", "", "CLT", "MEIO", "CBO_A_CONFIRMAR (4141-05)"),
     )),
    ("06_sem_cbo_cargos_genericos.xlsx", None,
     "Sem a coluna do CBO e com nomes genéricos ou de mais de uma profissão: só um AVISO por cargo, nada bloqueia.", (
         ("Analista", "", "CLT", "DIGITACAO_BAIXA", "CBO_NAO_ENCONTRADO (aviso)"),
         ("Supervisor", "", "CLT", "MEIO", "CBO_NAO_ENCONTRADO (aviso)"),
         ("Designer de interiores", "", "CLT", "MEIO", "CBO_NAO_ENCONTRADO (aviso, profissão ambígua)"),
     )),
    ("07_pro_labore_e_limites.csv", "Código CBO",
     "Pró-labore nunca é comparado; salário CLT exatamente no mínimo e no máximo passa, um centavo fora não.", (
         ("Sócio administrador", "", "PRO_LABORE", "DIGITACAO_ALTA",
          "CBO_NAO_ENCONTRADO (aviso do cargo; o pró-labore não é comparado)"),
         ("Assistente administrativo", "4110-10", "PRO_LABORE", "DIGITACAO_BAIXA", "nada (pró-labore)"),
         ("Assistente administrativo", "4110-10", "CLT", "MINIMO", "nada"),
         ("Assistente administrativo", "4110-10", "CLT", "MAXIMO", "nada"),
         ("Assistente administrativo", "4110-10", "CLT", "ABAIXO", "RENDA_FORA_DA_PROFISSAO"),
     )),
    ("08_fora_das_outras_empresas.xlsx", "Código da ocupação",
     "Salário dentro da faixa pública, mas acima da faixa das outras empresas (o servidor de teste já tem 2 outras "
     "empresas com pedreiros cadastrados; só este arquivo usa a profissão Pedreiro).", (
         ("Pedreiro", "7152-10", "CLT", "OUTRAS_ALTO", "RENDA_FORA_DA_PROFISSAO (outras empresas)"),
         ("Pedreiro", "7152-10", "CLT", "OUTRAS_DENTRO", "nada"),
         ("Pedreiro", "715210", "CLT", "DIGITACAO_ALTA",
          "RENDA_FORA_DA_PROFISSAO (profissão e outras empresas, um alerta só)"),
     )),
    ("09_coluna_cbo_em_parte_vazia.csv", "CBO",
     "A coluna do CBO vem vazia em algumas linhas: essas seguem o nome do cargo (a profissão já registrada do cargo "
     "ou a pergunta).", (
         ("Assistente administrativo", "4110-10", "CLT", "MEIO", "nada (registra a profissão do cargo)"),
         ("Assistente administrativo", "", "CLT", "DIGITACAO_BAIXA", "RENDA_FORA_DA_PROFISSAO (pelo cargo)"),
         ("Motorista de caminhão", "", "CLT", "MEIO", "CBO_A_CONFIRMAR (7825-10)"),
     )),
)


def ler_as_faixas() -> dict[str, tuple[Decimal, Decimal]]:
    """{código: (mínimo, máximo)} das profissões com faixa (as "sem dados" ficam de fora)."""
    faixas = {}
    with open(ARQUIVO_DAS_FAIXAS, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha["minimo"] and linha["maximo"]:
                faixas[linha["codigo_cbo"]] = (Decimal(linha["minimo"]), Decimal(linha["maximo"]))
    return faixas


def faixa_das_outras_empresas(minimo: Decimal, maximo: Decimal) -> tuple[Decimal, Decimal]:
    """A faixa que o servidor de teste dá às outras empresas numa profissão: de 30% a 40% do caminho entre o mínimo e o
    máximo públicos (scripts/preparar_demo_faixas_cbo.py usa a mesma conta)."""
    largura = maximo - minimo
    menor = (minimo + largura * Decimal("0.30")).quantize(Decimal("0.01"))
    maior = (minimo + largura * Decimal("0.40")).quantize(Decimal("0.01"))
    return menor, maior


def salario_do_caso(onde: str, codigo: str, faixas: dict) -> Decimal:
    """O salário da pessoa, posto em volta da faixa da profissão (ou um valor fixo quando não há faixa)."""
    # Sem faixa (código que não existe ou pró-labore sem código): um valor comum
    if codigo not in faixas:
        base = Decimal("3000.00")
        if onde == "DIGITACAO_BAIXA":
            return (base / 1000).quantize(Decimal("0.01"))
        if onde == "DIGITACAO_ALTA":
            return base * 100
        return base
    minimo, maximo = faixas[codigo]
    das_outras_minimo, das_outras_maximo = faixa_das_outras_empresas(minimo, maximo)
    valores = {
        "MEIO": ((minimo + maximo) / 2).quantize(Decimal("0.01")),
        "MINIMO": minimo,
        "MAXIMO": maximo,
        "ABAIXO": minimo - Decimal("0.01"),
        "ACIMA": maximo + Decimal("0.01"),
        "DIGITACAO_BAIXA": (((minimo + maximo) / 2) / 1000).quantize(Decimal("0.01")),
        "DIGITACAO_ALTA": ((minimo + maximo) / 2 * 100).quantize(Decimal("0.01")),
        "OUTRAS_ALTO": (minimo + (maximo - minimo) * Decimal("0.90")).quantize(Decimal("0.01")),
        "OUTRAS_DENTRO": ((das_outras_minimo + das_outras_maximo) / 2).quantize(Decimal("0.01")),
    }
    return valores[onde]


def em_reais_no_arquivo(valor: Decimal) -> str:
    """O salário como a empresa escreve na planilha: vírgula nos centavos, sem ponto de milhar ("2500,00")."""
    return f"{valor:.2f}".replace(".", ",")


def linha_da_pessoa(sorteio: random.Random, numero: int, cargo: str, vinculo: str, salario: Decimal) -> dict:
    """Uma linha sintética completa (todas as colunas obrigatórias do layout preenchidas)."""
    nome = f"{sorteio.choice(PRIMEIROS_NOMES)} {sorteio.choice(SOBRENOMES)} {sorteio.choice(SOBRENOMES)}"
    return {
        "Matrícula": f"C{numero:04d}", "Nome completo": nome, "CPF": gerar_cpf(sorteio),
        "Nascimento": f"{sorteio.randint(1, 28):02d}/{sorteio.randint(1, 12):02d}/{sorteio.randint(1965, 2002)}",
        "Sexo": sorteio.choice(("F", "M")), "Estado civil": sorteio.choice(("Solteiro", "Casado", "Divorciado")),
        "CEP": f"{sorteio.randint(13000000, 13999999)}", "Rua": "Rua das Acácias", "Número": str(sorteio.randint(1, 999)),
        "Bairro": "Jardim das Flores", "Cidade": "Campinas", "UF": "SP",
        "Celular": f"(19) 9{sorteio.randint(1000, 9999)}-{sorteio.randint(1000, 9999)}",
        "CNPJ": CNPJ_DA_EMPRESA, "Unidade": "AUR-01", "Nome da unidade": "Matriz Campinas", "Cargo": cargo,
        "Admissão": f"{sorteio.randint(1, 28):02d}/{sorteio.randint(1, 12):02d}/{sorteio.randint(2010, 2025)}",
        "Vínculo": vinculo, "Salário bruto": em_reais_no_arquivo(salario), "Competência": "01/09/2026",
        "CEP da unidade": "13086902", "Endereço da unidade": "Avenida das Indústrias", "Nº da unidade": "1500",
        "Bairro da unidade": "Distrito Industrial", "Cidade da unidade": "Campinas", "UF da unidade": "SP",
    }


def gravar_arquivo(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    """Grava as linhas em CSV (com ";", como os sistemas brasileiros exportam) ou em Excel, pela extensão."""
    if caminho.suffix == ".csv":
        with open(caminho, "w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
            escritor.writeheader()
            escritor.writerows(linhas)
        return
    planilha = Workbook()
    aba = planilha.active
    aba.title = "Funcionarios"
    aba.append(colunas)
    for linha in linhas:
        valores = []
        for coluna in colunas:
            valores.append(linha[coluna])
        aba.append(valores)
    planilha.save(caminho)


def gerar(pasta: Path) -> None:
    """Gera os arquivos e o registro na pasta."""
    pasta.mkdir(parents=True, exist_ok=True)
    faixas = ler_as_faixas()
    sorteio = random.Random(SEMENTE)
    registro = ["REGISTRO DOS ARQUIVOS DE TESTE DA FAIXA SALARIAL POR PROFISSÃO (CBO) — ADR-129",
                "", "Gerado por integra-folha/scripts/gerar_arquivos_cbo.py (dados 100% sintéticos).",
                "Empresa: Aurora (EMP001), usuário teste.empresa. Antes: o parâmetro precisa ter o campo codigo_cbo "
                "(o servidor de teste já tem).",
                "Linha = a linha no Excel (a 1 é o cabeçalho). Só as regras da CBO estão listadas: o arquivo pode ter "
                "outras pendências do Validador (ex.: a renda comparada com os colegas do cargo).", ""]
    numero = 1
    for nome_do_arquivo, coluna_do_cbo, objetivo, pessoas in CASOS:
        colunas = list(COLUNAS)
        if coluna_do_cbo:
            colunas.insert(colunas.index("Cargo") + 1, coluna_do_cbo)
        linhas = []
        registro.append(f"== {nome_do_arquivo} ==")
        registro.append(f"Objetivo: {objetivo}")
        registro.append(f"Coluna do CBO: {coluna_do_cbo or '(nenhuma)'}")
        for posicao, (cargo, codigo_escrito, vinculo, onde, esperado) in enumerate(pessoas, start=2):
            codigo = tabela_cbo.codigo_normalizado(codigo_escrito)
            # Sem código no arquivo: a faixa é a da profissão que o cargo sugere
            if codigo is None and not codigo_escrito:
                codigo = tabela_cbo.sugerir(cargo).codigo
            salario = salario_do_caso(onde, codigo, faixas)
            linha = linha_da_pessoa(sorteio, numero, cargo, vinculo, salario)
            if coluna_do_cbo:
                linha[coluna_do_cbo] = codigo_escrito
            linhas.append(linha)
            faixa = faixas.get(codigo)
            texto_da_faixa = "sem faixa"
            if faixa:
                texto_da_faixa = f"faixa {em_reais_no_arquivo(faixa[0])} a {em_reais_no_arquivo(faixa[1])}"
            registro.append(f"  linha {posicao}: {cargo} | CBO '{codigo_escrito}' | {vinculo} | salário "
                            f"{em_reais_no_arquivo(salario)} ({texto_da_faixa}) → esperado: {esperado}")
            numero += 1
        gravar_arquivo(pasta / nome_do_arquivo, colunas, linhas)
        registro.append("")
    (pasta / "REGISTRO_IMPORTS_CBO.txt").write_text("\n".join(registro) + "\n", encoding="utf-8")
    print(f"{len(CASOS)} arquivos e o registro em {pasta}")


if __name__ == "__main__":
    # Os acentos saem certos no terminal do Windows
    sys.stdout.reconfigure(encoding="utf-8")
    pasta_pedida = pasta_padrao()
    if len(sys.argv) > 1:
        pasta_pedida = Path(sys.argv[1])
    gerar(pasta_pedida)
