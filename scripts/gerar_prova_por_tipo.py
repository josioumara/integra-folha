"""Gera a prova por tipo de arquivo: as MESMAS pessoas escritas em 7 tipos de arquivo, com o gabarito.

Para que serve: medir, em cada tipo de arquivo que as empresas mandam, quanto a IA acrescenta ao acerto e às perguntas
que sobram para a empresa, e quanto isso custa (a medição fica em eval/ganho_por_tipo.py). O mesmo arquivo passa duas
vezes pelo caminho da tela: só com as regras (sem IA) e com a IA. Como as pessoas são as mesmas em todos os tipos, a
diferença entre um tipo e outro vem só do formato do arquivo, e não de pessoas mais fáceis ou mais difíceis.

Os 7 tipos, em 4 grupos:
    Planilhas (Excel nos arquivos 1 a 3 e CSV com ";" nos arquivos 4 e 5 de cada tipo)
    T1 · no padrão do banco: os nomes técnicos do parâmetro, na ordem dele, e todos os campos (o controle)
    T2 · as colunas fora de ordem, colunas a mais (que não existem no layout) e sem parte dos campos opcionais
    T3 · os nomes próximos: os nomes do vocabulário da PROVA (data/vocabulario/teste.csv), às vezes em maiúsculas ou
         com erro de digitação, e as colunas ambíguas e a mais da prova (nunca o vocabulário de treino, que já foi
         usado para ajustar o sistema)
    T4 · o cabeçalho difícil: um título e uma linha de grupos acima dos nomes das colunas, uma coluna sem nome e o nome
         e o CPF numa coluna só ("Nome - CPF"), que precisa ser dividida
    Documentos Word (escritos pelas funções de scripts/gerar_documentos_de_teste.py)
    T5 · tabela (arquivos 1 a 3) ou fichas "Rótulo: valor" (arquivos 4 e 5), lidas por regra, sem IA
    T6 · texto corrido simples (arquivos 1 e 2) ou variado (arquivos 3 a 5)
    T7 · texto misturado, com dados de outras pessoas e armadilhas (campos que o documento não deixa decidir)
Fora da prova: o PDF e a foto, que a aplicação ainda não lê (entram no relatório como o limite de hoje).

As pessoas: 75 (5 arquivos de 15 por tipo). O arquivo 1 de cada tipo tem as pessoas P01 a P15; o arquivo 2, as P16 a
P30, e assim por diante. Cada pessoa tem os 44 campos do layout (scripts/gerar_dados.py, gerar_funcionario) e o código
da profissão (CBO), um dos 4 obrigatórios do parâmetro (ADR-143). A renda fica dentro da faixa pública da profissão:
fora dela o sistema pergunta à empresa, e a pergunta não seria culpa do formato do arquivo.

Tudo é inventado (dados 100% sintéticos): CPFs com dígito verificador certo, e-mails no domínio reservado .example.
Nada daqui entra em prompt, regra ou base do RAG.

Sai (data/avaliacao/prova_por_tipo/):
    - os 35 arquivos (7 tipos × 5 arquivos);
    - manifesto.json: a semente; as pessoas com os valores certos; e, para cada arquivo, o tipo, as pessoas, as colunas
      e o que cada uma deve virar (nas planilhas), os campos esperados de cada pessoa e a impressão digital (SHA-256).
      A medição confere cada arquivo pela impressão digital antes de medir, e o manifesto fica congelado
      (eval/congelamento.py).

Uso: python scripts/gerar_prova_por_tipo.py   (a semente fixa gera sempre as mesmas pessoas e os mesmos arquivos)
"""
import csv
import io
import json
import random
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from docx import Document
from openpyxl import Workbook

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.congelamento import impressao_digital  # noqa: E402
from models.contratos import carregar_layout  # noqa: E402
from scripts import gerar_cabecalhos, gerar_dados  # noqa: E402
from scripts import gerar_documentos_de_teste as documentos  # noqa: E402
from scripts.aplicar_parametro_adr_143 import CAMPOS_OBRIGATORIOS  # noqa: E402

# A semente do sorteio: a mesma semente gera sempre as mesmas pessoas e os mesmos arquivos
SEMENTE = 20260930
# Quantas pessoas vão em cada arquivo e quantos arquivos cada tipo tem
PESSOAS_POR_ARQUIVO = 15
ARQUIVOS_POR_TIPO = 5
# Os arquivos de planilha de 1 a 3 saem em Excel; os outros, em CSV com ";"
ULTIMO_ARQUIVO_EM_EXCEL = 3
# Onde a prova é gravada
PASTA_DA_PROVA = RAIZ / "data" / "avaliacao" / "prova_por_tipo"
# A empresa que "manda" os arquivos: a Aurora (EMP001) da base sintética. A medição usa a mesma empresa, para o CNPJ
# do arquivo ser o dela
EMPRESA_DA_PROVA = "EMP001"
# O número da primeira pessoa no gerador da base sintética (vira a matrícula "09001"): longe das matrículas que a Aurora
# já tem (00001 em diante), para o sistema não apontar "matrícula já cadastrada para outra pessoa"
NUMERO_DA_PRIMEIRA_PESSOA = 9001

# O código da profissão (CBO oficial, 6 dígitos) de cada cargo do gerador da base sintética. Cada código existe na
# tabela oficial (data/cbo) e a faixa pública dele cobre a renda que o gerador sorteia para o cargo (o teste confere)
CBO_DO_CARGO = {
    "Auxiliar administrativo": "411005",    # Auxiliar de escritório
    "Assistente administrativo": "411010",  # Assistente administrativo
    "Analista": "252405",                   # Analista de recursos humanos
    "Analista sênior": "252405",            # Analista de recursos humanos
    "Coordenador": "142105",                # Gerente administrativo
    "Gerente": "142105",                    # Gerente administrativo
    "Diretor": "123105",                    # Diretor administrativo
    "Operador de logística": "414140",      # Auxiliar de logística
    "Motorista": "782305",                  # Motorista de furgão ou veículo similar
    "Desenvolvedor": "317110",              # Programador de sistemas de informação
    "Vendedor": "521110",                   # Vendedor de comércio varejista
    "Técnico de enfermagem": "322205",      # Técnico de enfermagem
    "Enfermeiro": "223505",                 # Enfermeiro
    "Sócio-administrador": "121010",        # Diretor geral de empresa
}

# Os nomes da coluna do CBO no T3 e no T4. O vocabulário da prova foi dividido antes de o campo existir (ADR-143) e
# não tem nome para ele; estes nomes são novos, só desta prova, e nunca vão para a IA
NOMES_DO_CBO_NA_PROVA = ["CBO", "Cód. Ocupação (CBO)", "Ocupação CBO"]
# Os nomes da coluna que junta o nome e o CPF (T4) e o jeito de escrever o valor em cada uma
JUNCOES_DO_NOME_E_CPF = [("Nome - CPF", "{nome} - {cpf}"), ("Funcionário / CPF", "{nome} / {cpf}"),
                         ("Nome e CPF", "{nome}, CPF {cpf}")]
# Os campos que podem ficar sem nome no T4, um por arquivo (dois deles são obrigatórios)
CAMPOS_SEM_NOME_NO_T4 = ["data_admissao", "telefone_celular", "valor_renda", "email_pessoal", "data_nascimento"]
# Os grupos do T4, na ordem das colunas, com os campos que cada um pode ter. O nome do grupo fica na linha acima dos
# nomes das colunas, só na primeira coluna do grupo. A identificação começa pela coluna que junta o nome e o CPF
GRUPOS_DO_T4 = [("IDENTIFICAÇÃO", ["data_nascimento", "sexo", "estado_civil", "nome_mae"]),
                ("CONTRATO", ["cargo", "codigo_cbo", "data_admissao", "valor_renda", "tipo_renda", "matricula"]),
                ("ENDEREÇO", ["logradouro_residencial", "numero_residencial", "bairro_residencial",
                              "municipio_residencial", "uf_residencial", "cep_residencial"]),
                ("CONTATO", ["telefone_celular", "email_pessoal"])]
# Os valores das colunas a mais (que não existem no layout) e das ambíguas (não dá para saber o campo)
VALORES_DAS_COLUNAS_A_MAIS = {"Observação Interna": ["", "Aguardando exame", "Transferido da filial", "Sem pendência"],
                              "Escala": ["5x2", "6x1", "12x36"], "Sindicato": ["SINDCOM", "SINTRAL", "Sem sindicato"],
                              "Tamanho Uniforme": ["P", "M", "G", "GG"], "Vaga Garagem": ["Sim", "Não"]}

# A descrição de cada tipo, que vai para o manifesto e para o relatório
TIPOS = {
    "T1": {"nome": "Planilha no padrão do banco", "grupo": "planilha",
           "descricao": "Os nomes técnicos do parâmetro, na ordem dele, com todos os campos (o controle).",
           "valores": "no formato do banco (data AAAA-MM-DD, renda 3217.52, CPF só com os dígitos)"},
    "T2": {"nome": "Planilha com colunas fora de ordem, a mais e faltando", "grupo": "planilha",
           "descricao": "Os nomes técnicos, embaralhados, com colunas que não existem no layout e sem parte dos opcionais.",
           "valores": "no formato do banco"},
    "T3": {"nome": "Planilha com nomes próximos", "grupo": "planilha",
           "descricao": "Os nomes do vocabulário da prova (às vezes em maiúsculas ou com erro de digitação), com colunas "
                        "ambíguas e a mais da prova.",
           "valores": "no formato das empresas (data DD/MM/AAAA, renda 3.217,52, CPF com pontos, CBO com traço)"},
    "T4": {"nome": "Planilha com cabeçalho difícil", "grupo": "planilha",
           "descricao": "Um título e uma linha de grupos acima dos nomes, uma coluna sem nome e o nome e o CPF numa "
                        "coluna só (a IA propõe dividir).",
           "valores": "no formato das empresas"},
    "T5": {"nome": "Word com tabela ou fichas", "grupo": "documento",
           "descricao": "Tabela (arquivos 1 a 3) ou fichas \"Rótulo: valor\" (4 e 5), lidas por regra, sem IA.",
           "valores": "como o gerador dos documentos escreve (N1 e N2)"},
    "T6": {"nome": "Word com texto corrido simples ou variado", "grupo": "documento",
           "descricao": "Uma frase igual para cada pessoa (arquivos 1 e 2) ou frases e formatos variados (3 a 5).",
           "valores": "como o gerador dos documentos escreve (N3 e N4)"},
    "T7": {"nome": "Word com texto misturado e armadilhas", "grupo": "documento",
           "descricao": "Blocos com títulos variados, dados de outras pessoas e uma armadilha por pessoa.",
           "valores": "como o gerador dos documentos escreve (N5)"},
}
# O que a prova deixa de fora, e por quê
FORA_DA_PROVA = {"PDF": "a aplicação ainda não lê PDF", "foto": "a aplicação ainda não lê foto nem imagem"}


# ============================== As pessoas ==============================

def cnpj_da_empresa(empresa_id: str) -> str:
    """O CNPJ da empresa na base sintética (data/synthetic/empresas.csv). Ex.: "EMP001" → "10433218000193"."""
    with open(RAIZ / "data" / "synthetic" / "empresas.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha["empresa_id"] == empresa_id:
                return linha["cnpj"]
    raise ValueError(f"A empresa {empresa_id} não está na base sintética")


def empresa_da_prova() -> dict:
    """A empresa das pessoas da prova: a Aurora (EMP001) do gerador da base sintética, com todos os cargos dele."""
    # Uma cópia, para não mexer na lista do gerador
    empresa = dict(gerar_dados.EMPRESAS[0])
    # Todos os cargos que o gerador conhece (cada um com o seu código CBO em CBO_DO_CARGO)
    empresa["cargos"] = list(gerar_dados.CARGOS)
    return empresa


def campos_do_parametro() -> list[str]:
    """Os nomes técnicos dos campos do parâmetro vigente (ADR-143): os 44 do layout, com o codigo_cbo depois do cargo."""
    nomes = []
    for campo in carregar_layout():
        nomes.append(campo.campo)
        # O código da profissão entra logo depois do cargo, como no parâmetro
        if campo.campo == "cargo":
            nomes.append("codigo_cbo")
    return nomes


def gerar_pessoas(sorteio: random.Random) -> list[dict]:
    """As 75 pessoas da prova, com os 44 campos do layout e o código da profissão.

    Devolve: uma lista de {"pessoa_id": "P01", "valores": {campo: valor}}; os valores são os certos (o gabarito).
    """
    empresa = empresa_da_prova()
    cnpj = cnpj_da_empresa(EMPRESA_DA_PROVA)
    campos = campos_do_parametro()
    quantidade = PESSOAS_POR_ARQUIVO * ARQUIVOS_POR_TIPO
    pessoas = []
    for numero in range(1, quantidade + 1):
        # Os 44 campos, com o gerador da base sintética (a matrícula sai do número: 9001 → "09001")
        numero_no_gerador = NUMERO_DA_PRIMEIRA_PESSOA + numero - 1
        valores = gerar_dados.gerar_funcionario(sorteio, empresa, cnpj, numero_no_gerador, "INICIAL")
        # O código da profissão do cargo sorteado
        valores["codigo_cbo"] = CBO_DO_CARGO[valores["cargo"]]
        # Só os campos do parâmetro ficam (saem o id interno, a empresa e o tipo de carga do gerador)
        valores_do_parametro = {}
        for campo in campos:
            valores_do_parametro[campo] = valores[campo]
        pessoas.append({"pessoa_id": f"P{numero:02d}", "valores": valores_do_parametro})
    return pessoas


def pessoas_do_arquivo(pessoas: list[dict], numero_do_arquivo: int) -> list[dict]:
    """As 15 pessoas do arquivo (o arquivo 1 tem as P01 a P15; o 2, as P16 a P30...), iguais em todos os tipos."""
    inicio = (numero_do_arquivo - 1) * PESSOAS_POR_ARQUIVO
    return pessoas[inicio:inicio + PESSOAS_POR_ARQUIVO]


# ============================== Os valores no formato das empresas ==============================

def cpf_com_pontos(cpf: str) -> str:
    """"52998224725" → "529.982.247-25"."""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def cbo_escrito(sorteio: random.Random, codigo: str) -> str:
    """O código da profissão escrito de um jeito sorteado: "411010", "4110-10" ou "4110.10"."""
    jeitos = [codigo, f"{codigo[:4]}-{codigo[4:]}", f"{codigo[:4]}.{codigo[4:]}"]
    return sorteio.choice(jeitos)


def valor_da_empresa(campo: str, valor: str, sorteio: random.Random) -> str:
    """O valor como uma empresa costuma exportar do sistema dela (datas DD/MM/AAAA, dinheiro com vírgula...).

    Recebe: o campo, o valor certo (no formato do banco) e o sorteio (para o jeito de escrever o CBO).
    Ex.: ("data_admissao", "2019-03-14") → "14/03/2019"; ("valor_renda", "3217.52") → "3.217,52".
    """
    # Campo vazio continua vazio
    if not valor:
        return valor
    # Datas: dia, mês e ano com barras
    if campo.startswith("data_"):
        return documentos.data_curta(date.fromisoformat(valor))
    # A renda: o padrão brasileiro, com ponto no milhar e vírgula nos centavos
    if campo == "valor_renda":
        return documentos.dinheiro(Decimal(valor))
    # O CPF com pontos e traço
    if campo == "cpf":
        return cpf_com_pontos(valor)
    # O CEP com traço
    if campo.startswith("cep_"):
        return f"{valor[:5]}-{valor[5:]}"
    # O código da profissão, com ou sem traço ou ponto
    if campo == "codigo_cbo":
        return cbo_escrito(sorteio, valor)
    # Os outros campos saem como estão
    return valor


# ============================== As colunas das planilhas ==============================

def coluna(cabecalho: str, esperado: str, campos: list[str], termo: str, origem: str) -> dict:
    """Uma coluna da planilha e o que ela deve virar.

    Recebe: o cabeçalho como fica no arquivo; o esperado (o nome de um campo, "AMBIGUO", "NAO_MAPEADO" ou "DIVIDIR");
    os campos que a coluna traz (vazio nas ambíguas e nas a mais); o termo de origem (o nome antes da variação) e de
    onde o nome veio ("parametro", "vocabulario_da_prova", "cbo_da_prova", "ambigua_da_prova", "a_mais_da_prova",
    "juncao_nome_cpf" ou "sem_nome").
    """
    return {"cabecalho": cabecalho, "esperado": esperado, "campos": campos, "termo": termo, "origem": origem}


def colunas_do_t1() -> list[dict]:
    """T1: todos os campos do parâmetro, com os nomes técnicos e na ordem dele."""
    colunas = []
    for campo in campos_do_parametro():
        colunas.append(coluna(campo, campo, [campo], campo, "parametro"))
    return colunas


def opcionais_que_ficam(sorteio: random.Random, candidatos: list[str], fracao: float) -> list[str]:
    """Uma parte dos campos opcionais, sorteada (o nome completo fica sempre: é o que identifica a pessoa na tela).

    Recebe: o sorteio, os campos opcionais candidatos e a fração que fica (ex.: 0.7 = 70%).
    """
    # O nome completo nunca sai
    outros = []
    for campo in candidatos:
        if campo != "nome_completo":
            outros.append(campo)
    quantos_ficam = round(len(outros) * fracao)
    escolhidos = sorteio.sample(outros, k=quantos_ficam)
    # O nome completo volta, na frente
    return ["nome_completo"] + escolhidos


def colunas_a_mais(sorteio: random.Random, minimo: int, maximo: int) -> list[dict]:
    """De `minimo` a `maximo` colunas que não existem no layout, da lista da PROVA (esperado: NAO_MAPEADO)."""
    nomes = sorteio.sample(gerar_cabecalhos.EXTRAS["teste"], k=sorteio.randint(minimo, maximo))
    colunas = []
    for nome in nomes:
        colunas.append(coluna(nome, "NAO_MAPEADO", [], nome, "a_mais_da_prova"))
    return colunas


def colunas_do_t2(sorteio: random.Random) -> list[dict]:
    """T2: os nomes técnicos, sem 30% dos opcionais, com 2 ou 3 colunas a mais, tudo embaralhado."""
    # Os opcionais do parâmetro (os que não estão entre os 4 obrigatórios; o CNPJ do grupo vem sempre vazio)
    opcionais = []
    for campo in campos_do_parametro():
        if campo not in CAMPOS_OBRIGATORIOS and campo != "cnpj_grupo":
            opcionais.append(campo)
    campos = list(CAMPOS_OBRIGATORIOS) + opcionais_que_ficam(sorteio, opcionais, 0.7)
    colunas = []
    for campo in campos:
        colunas.append(coluna(campo, campo, [campo], campo, "parametro"))
    colunas += colunas_a_mais(sorteio, 2, 3)
    # Fora de ordem, como numa planilha montada à mão
    sorteio.shuffle(colunas)
    return colunas


def nome_da_prova(sorteio: random.Random, vocabulario: dict, campo: str, com_variacao: bool) -> tuple[str, str]:
    """Um nome da PROVA para o campo (o vocabulário de teste; o CBO usa NOMES_DO_CBO_NA_PROVA), às vezes variado.

    com_variacao: True deixa o nome às vezes em maiúsculas, com espaços sobrando ou com erro de digitação (a mesma
    variação da prova do Interpretador, gerar_cabecalhos.variar).
    Devolve: (o nome como fica no arquivo, o termo de origem antes da variação).
    Ex.: ("cpf", com variação) → ("CPF DO COLABORADOR", "CPF do Colaborador").
    """
    # O CBO não tem nome no vocabulário da prova: usa os nomes novos, só desta prova
    if campo == "codigo_cbo":
        termo = sorteio.choice(NOMES_DO_CBO_NA_PROVA)
    else:
        termo = sorteio.choice(vocabulario[campo])
    if com_variacao:
        return gerar_cabecalhos.variar(termo, sorteio), termo
    return termo, termo


def colunas_pelos_nomes_da_prova(sorteio: random.Random, vocabulario: dict, campos: list[str],
                                 com_variacao: bool) -> list[dict]:
    """Uma coluna por campo, com um nome da prova. Dois nomes iguais nunca ficam: o campo sorteia de novo.

    Recebe: o sorteio, o vocabulário da prova, os campos e se os nomes levam variação.
    """
    colunas = []
    nomes_usados = set()
    for campo in campos:
        # Até 10 tentativas de achar um nome ainda não usado (cada campo tem pelo menos 2 nomes)
        for _tentativa in range(10):
            cabecalho, termo = nome_da_prova(sorteio, vocabulario, campo, com_variacao)
            chave = chave_do_nome(cabecalho)
            if chave not in nomes_usados:
                break
        nomes_usados.add(chave)
        origem = "cbo_da_prova" if campo == "codigo_cbo" else "vocabulario_da_prova"
        colunas.append(coluna(cabecalho, campo, [campo], termo, origem))
    return colunas


def chave_do_nome(cabecalho: str) -> str:
    """O nome da coluna sem espaços sobrando e em minúsculas, para saber se dois nomes são o mesmo."""
    return cabecalho.strip().lower()


def colunas_ambiguas(sorteio: random.Random, minimo: int, maximo: int) -> list[dict]:
    """De `minimo` a `maximo` colunas ambíguas da lista da PROVA (esperado: AMBIGUO, a empresa decide)."""
    nomes = sorteio.sample(gerar_cabecalhos.AMBIGUAS["teste"], k=sorteio.randint(minimo, maximo))
    colunas = []
    for nome in nomes:
        colunas.append(coluna(nome, "AMBIGUO", [], nome, "ambigua_da_prova"))
    return colunas


def colunas_do_t3(sorteio: random.Random, vocabulario: dict) -> list[dict]:
    """T3: os 4 obrigatórios, o nome e de 10 a 16 opcionais, com nomes da prova variados, mais ambíguas e a mais."""
    # Os opcionais que a prova sorteia (os do vocabulário da prova, menos o nome, que entra sempre)
    opcionais = []
    for campo in gerar_cabecalhos.campos_da_prova(vocabulario):
        if campo not in CAMPOS_OBRIGATORIOS and campo != "nome_completo":
            opcionais.append(campo)
    escolhidos = sorteio.sample(opcionais, k=sorteio.randint(10, 16))
    campos = list(CAMPOS_OBRIGATORIOS) + ["nome_completo"] + escolhidos
    colunas = colunas_pelos_nomes_da_prova(sorteio, vocabulario, campos, com_variacao=True)
    colunas += colunas_ambiguas(sorteio, 0, 2)
    colunas += colunas_a_mais(sorteio, 0, 3)
    # Fora de ordem, como nas planilhas das empresas
    sorteio.shuffle(colunas)
    return colunas


def colunas_do_t4(sorteio: random.Random, vocabulario: dict, numero_do_arquivo: int) -> list[dict]:
    """T4: o nome e o CPF numa coluna só, os outros 3 obrigatórios e 8 opcionais, com uma coluna sem nome.

    A coluna sem nome muda a cada arquivo (CAMPOS_SEM_NOME_NO_T4). A ordem segue os grupos (identificação, contrato,
    endereço, contato), porque a linha de grupos fica acima dos nomes.
    """
    # A coluna que junta o nome e o CPF (a IA deve propor dividir); ela abre o grupo da identificação
    cabecalho_da_juncao, _ = JUNCOES_DO_NOME_E_CPF[(numero_do_arquivo - 1) % len(JUNCOES_DO_NOME_E_CPF)]
    juncao = coluna(cabecalho_da_juncao, "DIVIDIR", ["nome_completo", "cpf"], cabecalho_da_juncao, "juncao_nome_cpf")
    juncao["grupo_acima"] = GRUPOS_DO_T4[0][0]
    # O campo que fica sem nome neste arquivo
    campo_sem_nome = CAMPOS_SEM_NOME_NO_T4[(numero_do_arquivo - 1) % len(CAMPOS_SEM_NOME_NO_T4)]
    colunas = [juncao]
    for nome_do_grupo, campos_do_grupo in GRUPOS_DO_T4:
        escolhidos = []
        for campo in campos_do_grupo:
            # Os obrigatórios e o campo sem nome ficam sempre; os outros, com 60% de chance
            if campo in CAMPOS_OBRIGATORIOS or campo == campo_sem_nome or sorteio.random() < 0.6:
                escolhidos.append(campo)
        colunas_do_grupo = colunas_pelos_nomes_da_prova(sorteio, vocabulario, escolhidos, com_variacao=False)
        # O nome do grupo vai acima da primeira coluna dele (a identificação já começou na junção)
        if colunas_do_grupo and nome_do_grupo != GRUPOS_DO_T4[0][0]:
            colunas_do_grupo[0]["grupo_acima"] = nome_do_grupo
        colunas += colunas_do_grupo
    # A coluna do campo sorteado perde o nome (o cabeçalho fica vazio no arquivo)
    for coluna_do_arquivo in colunas:
        if coluna_do_arquivo["campos"] == [campo_sem_nome]:
            coluna_do_arquivo["cabecalho"] = ""
            coluna_do_arquivo["origem"] = "sem_nome"
    return colunas


# ============================== As linhas das planilhas ==============================

def valor_da_coluna(coluna_do_arquivo: dict, pessoa: dict, formato: str, sorteio: random.Random,
                    numero_do_arquivo: int) -> str:
    """O texto da célula da pessoa nesta coluna.

    Recebe: a coluna, a pessoa ({"pessoa_id", "valores"}), o formato ("banco" ou "empresa"), o sorteio e o número do
    arquivo (para o jeito de escrever a junção do nome e do CPF).
    """
    valores = pessoa["valores"]
    esperado = coluna_do_arquivo["esperado"]
    # A junção do nome e do CPF, no jeito do cabeçalho
    if esperado == "DIVIDIR":
        _, molde = JUNCOES_DO_NOME_E_CPF[(numero_do_arquivo - 1) % len(JUNCOES_DO_NOME_E_CPF)]
        return molde.format(nome=valores["nome_completo"], cpf=cpf_com_pontos(valores["cpf"]))
    # Coluna a mais: um valor qualquer da lista dela
    if esperado == "NAO_MAPEADO":
        return sorteio.choice(VALORES_DAS_COLUNAS_A_MAIS[coluna_do_arquivo["termo"]])
    # Coluna ambígua: um valor que não é nenhum campo do layout (a empresa diz que é para ignorar)
    if esperado == "AMBIGUO":
        return valor_da_coluna_ambigua(coluna_do_arquivo["termo"], valores, sorteio)
    # Coluna de um campo: o valor certo, no formato do tipo
    campo = coluna_do_arquivo["campos"][0]
    if formato == "empresa":
        return valor_da_empresa(campo, valores[campo], sorteio)
    return valores[campo]


def valor_da_coluna_ambigua(termo: str, valores: dict, sorteio: random.Random) -> str:
    """Um valor plausível para a coluna ambígua, que não é nenhum campo do layout.

    "Proventos" e "Soma" levam a renda com extras (não é a renda do contrato); "Montante", um valor de benefício;
    "Dt.", uma data que não é nascimento nem admissão (o último exame); "Cód.", um código interno.
    """
    if termo in ("Proventos", "Soma"):
        # A renda com horas extras e adicionais: maior que a renda do contrato
        extras = Decimal(valores["valor_renda"]) * Decimal(str(round(sorteio.uniform(1.08, 1.35), 2)))
        return documentos.dinheiro(extras.quantize(Decimal("0.01")))
    if termo == "Montante":
        # Um valor de benefício, bem menor que a renda
        return documentos.dinheiro(Decimal(sorteio.randint(150, 900)))
    if termo == "Dt.":
        # A data do último exame periódico (nenhum campo do layout)
        return documentos.data_curta(documentos.sortear_data(sorteio, date(2025, 1, 1), date(2026, 8, 31)))
    # "Cód.": um código interno, com letra e número
    return f"{sorteio.choice('ABCDEFGH')}-{sorteio.randint(10, 99)}"


def linhas_da_planilha(colunas: list[dict], pessoas: list[dict], formato: str, sorteio: random.Random,
                       numero_do_arquivo: int) -> list[list[str]]:
    """As linhas de dados (uma por pessoa), com os valores na ordem das colunas."""
    linhas = []
    for pessoa in pessoas:
        linha = []
        for coluna_do_arquivo in colunas:
            linha.append(valor_da_coluna(coluna_do_arquivo, pessoa, formato, sorteio, numero_do_arquivo))
        linhas.append(linha)
    return linhas


def linhas_de_cima_do_t4(colunas: list[dict]) -> list[list[str]]:
    """O título e a linha de grupos que o T4 tem acima dos nomes das colunas.

    O título ocupa uma célula; o nome de cada grupo fica só na primeira coluna do grupo (como um CSV exportado de uma
    planilha com células mescladas).
    """
    titulo = ["Relação de funcionários admitidos - Aurora Alimentos - setembro/2026"] + [""] * (len(colunas) - 1)
    grupos = []
    for coluna_do_arquivo in colunas:
        # Só a primeira coluna de cada grupo leva o nome dele; as outras ficam vazias
        grupos.append(coluna_do_arquivo.get("grupo_acima", ""))
    return [titulo, grupos]


def planilha_excel(linhas: list[list[str]]) -> bytes:
    """A planilha em Excel (.xlsx), com toda célula como texto (os zeros à esquerda ficam)."""
    livro = Workbook()
    aba = livro.active
    aba.title = "Funcionarios"
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def planilha_csv(linhas: list[list[str]]) -> bytes:
    """A planilha em CSV com ";" e UTF-8, como os sistemas de RH costumam exportar."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerows(linhas)
    return saida.getvalue().encode("utf-8")


# ============================== Os documentos ==============================

def pessoa_para_os_documentos(pessoa: dict, numero: int, sorteio: random.Random) -> dict:
    """A pessoa no formato que as funções de scripts/gerar_documentos_de_teste.py escrevem.

    Recebe: a pessoa da prova, o número dela (para o título "FICHA 007" do texto misturado) e o sorteio (para o jeito
    de escrever o CBO). Ex.: "telefone_celular" "(47) 91234-5678" vira ddd "47" e celular "912345678".
    """
    valores = pessoa["valores"]
    # Só os dígitos do celular: os dois primeiros são o DDD
    digitos_do_celular = ""
    for caractere in valores["telefone_celular"]:
        if caractere.isdigit():
            digitos_do_celular += caractere
    pis = valores["nis_pis"]
    cep = valores["cep_residencial"]
    return {
        "numero": numero, "feminino": valores["sexo"] == "F", "nome": valores["nome_completo"], "cpf": valores["cpf"],
        "nascimento": date.fromisoformat(valores["data_nascimento"]),
        "admissao": date.fromisoformat(valores["data_admissao"]),
        # No texto, o cargo vai em minúsculas ("foi admitida como assistente administrativo")
        "cargo": valores["cargo"].lower(), "salario": Decimal(valores["valor_renda"]), "mae": valores["nome_mae"],
        "rua": valores["logradouro_residencial"], "numero_da_casa": valores["numero_residencial"],
        "bairro": valores["bairro_residencial"], "cidade": valores["municipio_residencial"],
        "uf": valores["uf_residencial"], "cep": f"{cep[:5]}-{cep[5:]}",
        "ddd": digitos_do_celular[:2], "celular": digitos_do_celular[2:], "email": valores["email_pessoal"],
        "estado_civil": valores["estado_civil"].lower(), "rg": valores["numero_documento"],
        # O PIS no jeito dos documentos: 123.45678.90-1
        "pis": f"{pis[:3]}.{pis[3:8]}.{pis[8:10]}-{pis[10]}",
        "cbo": cbo_escrito(sorteio, valores["codigo_cbo"]),
    }


def nivel_do_documento(tipo: str, numero_do_arquivo: int) -> str:
    """O nível do gerador de documentos que escreve o arquivo: T5 → N1 ou N2; T6 → N3 ou N4; T7 → N5."""
    if tipo == "T5":
        return "N1" if numero_do_arquivo <= 3 else "N2"
    if tipo == "T6":
        return "N3" if numero_do_arquivo <= 2 else "N4"
    return "N5"


def documento_word(nivel: str, pessoas_do_documento: list[dict], sorteio: random.Random):
    """Escreve o documento com a função do nível.

    Devolve (documento, gabaritos, cabecalho_para_campo) do gerador dos documentos. cabecalho_para_campo diz qual campo
    é cada cabeçalho da tabela ou rótulo das fichas (ex.: {"CBO": "codigo_cbo"}); no texto corrido, vem vazio.
    """
    # N1 a N3 são fixos; N4 e N5 sorteiam os formatos
    if nivel == "N1":
        return documentos.documento_n1(pessoas_do_documento)
    if nivel == "N2":
        return documentos.documento_n2(pessoas_do_documento)
    if nivel == "N3":
        return documentos.documento_n3(pessoas_do_documento)
    if nivel == "N4":
        return documentos.documento_n4(sorteio, pessoas_do_documento)
    return documentos.documento_n5(sorteio, pessoas_do_documento)


def bytes_do_word(documento) -> bytes:
    """O documento Word em bytes."""
    saida = io.BytesIO()
    documento.save(saida)
    return saida.getvalue()


# ============================== O gabarito de cada arquivo ==============================

def gabarito_da_planilha(colunas: list[dict], pessoas: list[dict]) -> list[dict]:
    """Os campos que cada pessoa deve ter depois do envio: os que as colunas trazem e que a pessoa tem preenchidos.

    Um campo vazio na pessoa (ex.: sem data de efetivação) não conta: não há o que acertar nele.
    """
    campos_do_arquivo = []
    for coluna_do_arquivo in colunas:
        campos_do_arquivo += coluna_do_arquivo["campos"]
    gabarito = []
    for pessoa in pessoas:
        campos = []
        for campo in campos_do_arquivo:
            if pessoa["valores"][campo]:
                campos.append(campo)
        gabarito.append({"pessoa_id": pessoa["pessoa_id"], "campos": campos, "armadilhas": [],
                         "espera_duvida": False, "terceiros": []})
    return gabarito


def gabarito_do_documento(gabaritos: list[dict], pessoas: list[dict]) -> list[dict]:
    """O gabarito do documento pelo gerador dos documentos: os campos esperados, as armadilhas e os terceiros.

    Os valores esperados ficam só nas pessoas (manifesto["pessoas"]); aqui vão os nomes dos campos. Um campo vazio
    na pessoa não conta.
    """
    gabarito = []
    for pessoa, gabarito_do_gerador in zip(pessoas, gabaritos):
        campos = []
        for campo in gabarito_do_gerador["campos"]:
            if pessoa["valores"][campo]:
                campos.append(campo)
        gabarito.append({"pessoa_id": pessoa["pessoa_id"], "campos": campos,
                         "armadilhas": gabarito_do_gerador["armadilhas"],
                         "espera_duvida": gabarito_do_gerador["espera_duvida"],
                         "terceiros": gabarito_do_gerador["terceiros"],
                         "armadilha": gabarito_do_gerador.get("armadilha")})
    return gabarito


# ============================== A prova inteira ==============================

def sorteio_do_arquivo(tipo: str, numero_do_arquivo: int) -> random.Random:
    """Um sorteio só deste arquivo (a semente, o tipo e o número): mudar um arquivo não muda os outros."""
    return random.Random(f"{SEMENTE}-{tipo}-{numero_do_arquivo}")


def nome_do_arquivo(tipo: str, numero_do_arquivo: int) -> str:
    """Ex.: ("T3", 2) → "T3_nomes_proximos_2.xlsx"; ("T6", 4) → "T6_texto_corrido_4.docx"."""
    apelidos = {"T1": "padrao_do_banco", "T2": "colunas_fora_de_ordem", "T3": "nomes_proximos",
                "T4": "cabecalho_dificil", "T5": "tabela_ou_fichas", "T6": "texto_corrido", "T7": "texto_misturado"}
    if TIPOS[tipo]["grupo"] == "documento":
        extensao = "docx"
    elif numero_do_arquivo <= ULTIMO_ARQUIVO_EM_EXCEL:
        extensao = "xlsx"
    else:
        extensao = "csv"
    return f"{tipo}_{apelidos[tipo]}_{numero_do_arquivo}.{extensao}"


def montar_planilha(tipo: str, numero_do_arquivo: int, pessoas: list[dict], vocabulario: dict) -> tuple[bytes, dict]:
    """Monta um arquivo de planilha (T1 a T4). Devolve (os bytes, a entrada do manifesto sem a impressão digital)."""
    sorteio = sorteio_do_arquivo(tipo, numero_do_arquivo)
    linhas_de_cima = []
    if tipo == "T1":
        colunas = colunas_do_t1()
    elif tipo == "T2":
        colunas = colunas_do_t2(sorteio)
    elif tipo == "T3":
        colunas = colunas_do_t3(sorteio, vocabulario)
    else:
        colunas = colunas_do_t4(sorteio, vocabulario, numero_do_arquivo)
        linhas_de_cima = linhas_de_cima_do_t4(colunas)
    # T1 e T2 seguem o formato do banco; T3 e T4, o das empresas
    formato = "banco" if tipo in ("T1", "T2") else "empresa"
    cabecalhos = []
    for coluna_do_arquivo in colunas:
        cabecalhos.append(coluna_do_arquivo["cabecalho"])
    linhas = linhas_de_cima + [cabecalhos] + linhas_da_planilha(colunas, pessoas, formato, sorteio, numero_do_arquivo)
    nome = nome_do_arquivo(tipo, numero_do_arquivo)
    conteudo = planilha_excel(linhas) if nome.endswith(".xlsx") else planilha_csv(linhas)
    # A posição de cada coluna (1 = a primeira): a coluna sem nome vira "Coluna N" na leitura
    for posicao, coluna_do_arquivo in enumerate(colunas, start=1):
        coluna_do_arquivo["posicao"] = posicao
    entrada = {"arquivo": nome, "tipo": tipo, "numero": numero_do_arquivo, "formato_dos_valores": formato,
               "linhas_antes_do_cabecalho": len(linhas_de_cima), "colunas": colunas,
               "gabarito": gabarito_da_planilha(colunas, pessoas)}
    return conteudo, entrada


def montar_documento(tipo: str, numero_do_arquivo: int, pessoas: list[dict]) -> tuple[bytes, dict]:
    """Monta um documento Word (T5 a T7). Devolve (os bytes, a entrada do manifesto sem a impressão digital)."""
    sorteio = sorteio_do_arquivo(tipo, numero_do_arquivo)
    pessoas_do_documento = []
    for pessoa in pessoas:
        # O número global da pessoa (P07 → 7), para o título das fichas do texto misturado
        numero = int(pessoa["pessoa_id"][1:])
        pessoas_do_documento.append(pessoa_para_os_documentos(pessoa, numero, sorteio))
    nivel = nivel_do_documento(tipo, numero_do_arquivo)
    documento, gabaritos, cabecalho_para_campo = documento_word(nivel, pessoas_do_documento, sorteio)
    # cabecalho_para_campo: na tabela e nas fichas, o campo de cada cabeçalho ou rótulo (a medição confere as colunas)
    entrada = {"arquivo": nome_do_arquivo(tipo, numero_do_arquivo), "tipo": tipo, "numero": numero_do_arquivo,
               "nivel": nivel, "cabecalho_para_campo": cabecalho_para_campo,
               "gabarito": gabarito_do_documento(gabaritos, pessoas)}
    return bytes_do_word(documento), entrada


def gerar_prova(pasta: Path) -> dict:
    """Gera os 35 arquivos e o manifesto na pasta. Devolve o manifesto."""
    pasta.mkdir(parents=True, exist_ok=True)
    pessoas = gerar_pessoas(random.Random(SEMENTE))
    # O vocabulário da PROVA (nunca o de treino)
    vocabulario = gerar_cabecalhos.ler_vocabulario("teste")
    arquivos = []
    for tipo in TIPOS:
        for numero_do_arquivo in range(1, ARQUIVOS_POR_TIPO + 1):
            pessoas_deste = pessoas_do_arquivo(pessoas, numero_do_arquivo)
            if TIPOS[tipo]["grupo"] == "planilha":
                conteudo, entrada = montar_planilha(tipo, numero_do_arquivo, pessoas_deste, vocabulario)
            else:
                conteudo, entrada = montar_documento(tipo, numero_do_arquivo, pessoas_deste)
            caminho = pasta / entrada["arquivo"]
            caminho.write_bytes(conteudo)
            # As pessoas do arquivo e a impressão digital (a medição confere antes de medir)
            ids_das_pessoas = []
            for pessoa in pessoas_deste:
                ids_das_pessoas.append(pessoa["pessoa_id"])
            entrada["pessoas"] = ids_das_pessoas
            entrada["sha256"] = impressao_digital(caminho)
            arquivos.append(entrada)
    manifesto = {"conjunto": "prova_por_tipo", "semente": SEMENTE, "gerado_por": "scripts/gerar_prova_por_tipo.py",
                 "empresa_id": EMPRESA_DA_PROVA, "cnpj_da_empresa": cnpj_da_empresa(EMPRESA_DA_PROVA),
                 "pessoas_por_arquivo": PESSOAS_POR_ARQUIVO, "arquivos_por_tipo": ARQUIVOS_POR_TIPO,
                 "campos_obrigatorios": list(CAMPOS_OBRIGATORIOS), "tipos": TIPOS, "fora_da_prova": FORA_DA_PROVA,
                 "pessoas": pessoas, "arquivos": arquivos}
    (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifesto


def main() -> None:
    """Gera a prova na pasta dela e mostra um resumo."""
    manifesto = gerar_prova(PASTA_DA_PROVA)
    print(f"{len(manifesto['pessoas'])} pessoas | {len(manifesto['arquivos'])} arquivos | semente {SEMENTE} | "
          f"{PASTA_DA_PROVA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
