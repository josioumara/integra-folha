"""Leitor de fichas: os arquivos que a leitura de tabela não monta sozinha (ADR-130).

Para que serve: a leitura de sempre (services/ingestao.py) entende uma TABELA, uma linha por funcionário e um dado por
coluna. Alguns arquivos chegam de outro jeito, e aí cada linha virava uma "pessoa" errada. Este leitor cuida de dois
jeitos, e SÓ deles: qualquer outro arquivo segue exatamente pela leitura de sempre.

A) Abas ligadas por um identificador (sem IA). A planilha tem uma aba com os dados pessoais e outra com o contrato,
   e as duas têm o CPF (ou outra coluna de identificador, como a matrícula). Juntamos as abas numa tabela só, uma linha
   por pessoa, casando o identificador. Ex.: aba "Pessoas" (nome, CPF) + aba "Contratos" (CPF, cargo, salário).

B) Fichas escritas em texto (com a IA). Os dados de cada pessoa estão DENTRO de uma célula de texto longo ("Ana Lima;
   CPF 529.982.247-25; nasceu em 12/03/1990..."), às vezes em pedaços espalhados por linhas e abas, com uma coluna de
   referência que diz de quem é cada pedaço (ex.: "K7"). Juntamos os pedaços de cada referência num texto só e pedimos
   ao Agente Leitor de Documentos (o mesmo do Word em texto corrido, sem mudar nada nele) os campos daquela pessoa.
   Uma pessoa por vez: assim a IA nunca mistura o pedaço de uma pessoa com o de outra.
   Depois da IA, uma conferência por regra: um nome não tem números nem "@"; todo CPF tem o dígito verificador
   conferido; um CPF não é de duas pessoas.

Como o arquivo é reconhecido: SÓ pela forma dos dados (quantas abas, que colunas têm identificador, que células têm
vários dados juntos), nunca pelo nome de uma coluna ou de um arquivo. Assim a regra vale para arquivos que ninguém viu.

Onde se encaixa: services/ingestao.ler_arquivo chama ler_se_reconhecer() antes de tudo; se a resposta for None, a
leitura de sempre continua. services/processamentos.py guarda a leitura das fichas (a IA não lê de novo nas etapas
seguintes), como já faz com o Word.
"""
import io
import re
from collections import Counter
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas
from openpyxl import load_workbook

from agents import leitor_de_documentos
from models.contratos import carregar_layout
from services import detector_de_dados, guardrail_injecao, ingestao, leitura_de_word, teto_de_gasto
from services.documentos import cpf_valido

# ============================== Constantes ==============================

# Como a leitura foi feita, gravado no uso da IA (é assim que services/processamentos.py sabe que deve guardar a leitura)
COMO_FOI_LIDO_POR_REFERENCIA = "fichas por referência"
COMO_FOI_LIDO_UMA_POR_LINHA = "fichas numa célula"

# Uma célula é "ficha" quando junta pelo menos 2 tipos de dado diferentes (ex.: um CPF e uma data)
MINIMO_DE_TIPOS_DE_DADO_NA_FICHA = 2
# A coluna de fichas: pelo menos metade das células é ficha
FRACAO_MINIMA_DE_FICHAS_NA_COLUNA = 0.5
# ... e o texto é longo: em média, pelo menos 40 caracteres (um nome ou um cargo são curtos)
MEDIA_MINIMA_DE_CARACTERES_DA_FICHA = 40
# Uma coluna "tem CPF" quando pelo menos metade das células é um CPF sozinho (então é uma tabela comum, não fichas)
FRACAO_DE_CPF_DE_UMA_COLUNA_DE_CPF = 0.5
# A referência é um código curto (ex.: "K7", "000123", "RH-45"): até 20 caracteres
MAXIMO_DE_CARACTERES_DA_REFERENCIA = 20
# ... preenchido em quase todas as linhas
FRACAO_MINIMA_DE_REFERENCIAS_PREENCHIDAS = 0.9
# Sem referência, cada linha é uma pessoa; se mais da metade das linhas não tem CPF, são pedaços de ninguém: recusa
FRACAO_MAXIMA_DE_LINHAS_SEM_CPF = 0.5
# Leitura com IA: no máximo 150 pessoas por envio (o mesmo limite do texto corrido do Word)
MAXIMO_DE_PESSOAS_POR_ENVIO = 150

# A coluna de identificador (leitor A): preenchida em pelo menos 80% das linhas
FRACAO_MINIMA_DE_IDENTIFICADORES_PREENCHIDOS = 0.8
# Duas abas se ligam quando pelo menos metade dos identificadores da aba de fora aparece na aba principal
FRACAO_MINIMA_DE_IDENTIFICADORES_EM_COMUM = 0.5

# Os campos do layout que a conferência olha
CAMPO_DO_NOME = "nome_completo"
CAMPO_DO_CPF = "cpf"
# Um nome de pessoa tem no máximo 8 palavras ("Maria das Graças de Souza e Silva Lima" tem 8)
MAXIMO_DE_PALAVRAS_DO_NOME = 8

# Um CPF escrito no texto, com ou sem pontos (o dígito verificador é conferido depois)
PADRAO_DO_CPF_NO_TEXTO = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")


# ============================== Estruturas ==============================

@dataclass
class TabelaDaAba:
    """Uma aba (ou o CSV inteiro) já com o cabeçalho achado: os nomes das colunas e as linhas de dados."""

    nome: str                                   # o nome da aba ("" no CSV)
    cabecalhos: list[str]                       # o nome de cada coluna
    linhas: list[list[str]]                     # as linhas de dados, todas com o mesmo número de colunas
    numeros_linha: list[int]                    # em que linha do arquivo (ou da aba) está cada linha, contando de 1
    colunas_numericas: list[set[int]]           # para cada linha, as colunas que vieram como número no Excel
    linha_do_cabecalho: int                     # em que linha estava o cabeçalho, contando de 1
    encontrou_data: bool = False                # se alguma célula era data do Excel


@dataclass
class Fragmento:
    """Um pedaço de ficha: o texto de uma célula, de onde ele veio e o que as outras colunas dizem dele."""

    texto: str                                  # o texto da célula de ficha
    numero_linha: int                           # a linha do arquivo (ou da aba)
    nome_da_aba: str                            # a aba ("" no CSV)
    complemento: str                            # as outras colunas curtas da linha (ex.: "proposta")
    referencia: str = ""                        # a referência da pessoa ("" quando não há coluna de referência)


@dataclass
class PessoaDasFichas:
    """Os pedaços de uma pessoa, na ordem do arquivo, e a linha em que ela começa."""

    referencia: str                             # a referência (ou "linha N", quando cada linha é uma pessoa)
    fragmentos: list[Fragmento] = field(default_factory=list)


# ============================== A entrada ==============================

def ler_se_reconhecer(conteudo: bytes, nome_do_arquivo: str, limite_em_bytes: int, cliente=None,
                      campos_do_layout=None):
    """Lê o arquivo se ele for de abas ligadas ou de fichas; senão devolve None (e a leitura de sempre continua).

    Recebe: os bytes, o nome do arquivo, o limite de tamanho, o cliente de IA e os campos do layout (os dois últimos só
    nas fichas; sem informar, o cliente do modo configurado e a versão 1 do layout).
    Devolve: a ingestao.Leitura, pronta como a da leitura de sempre, ou None.
    Pode recusar (ingestao.ArquivoRecusado) quando reconheceu as fichas mas não dá para montar as pessoas.
    Exemplo: ler_se_reconhecer(planilha_com_abas_pessoas_e_contratos, "rh.xlsx", limite) → Leitura com 1 linha por CPF.
    """
    # 1. Abre o arquivo do jeito dele; o que não abrir fica para a leitura de sempre (ela explica o problema)
    abas, informacoes_do_formato = _abas_do_arquivo(conteudo, nome_do_arquivo, limite_em_bytes)
    if not abas:
        return None
    # 2. Cada aba preenchida vira uma tabela com cabeçalho (a aba sem cabeçalho fica para a leitura de sempre)
    tabelas = _tabelas_com_cabecalho(abas)
    if not tabelas:
        return None
    # 3. Fichas em texto (vem primeiro: abas de fichas também têm uma referência em comum, e juntar as abas lado a
    # lado deixaria o texto sem ler)
    if _todas_sao_de_fichas(tabelas):
        return _ler_fichas(tabelas, informacoes_do_formato, cliente, campos_do_layout)
    # 4. Abas ligadas por um identificador (só planilha com mais de uma aba)
    if len(tabelas) > 1:
        return _ler_abas_ligadas(abas, tabelas, conteudo, informacoes_do_formato)
    return None


def leitura_veio_das_fichas(leitura) -> bool:
    """True se a leitura foi feita pelo leitor de fichas com IA (então ela é guardada, para a IA não ler de novo)."""
    if not leitura.uso_da_ia:
        return False
    return leitura.uso_da_ia.get("como_foi_lido") in (COMO_FOI_LIDO_POR_REFERENCIA, COMO_FOI_LIDO_UMA_POR_LINHA)


def avisos_das_abas_de_fora(abas_lidas: list, posicao_da_aba: int) -> list[str]:
    """O aviso da leitura de sempre quando outras abas preenchidas ficaram de fora (não deu para ligá-las).

    Recebe: as abas lidas (ingestao.AbaLida) e a posição da aba usada. Devolve a lista de avisos (vazia ou com um).
    Exemplo: abas "Pessoas" (usada) e "Salários" (sem CPF) → ["A aba Salários não foi usada: ... ponha o CPF em cada aba."]
    """
    aba_usada = abas_lidas[posicao_da_aba]
    # A aba usada, com o cabeçalho achado (sem cabeçalho, não há como procurar uma coluna em comum)
    principal = None
    if ingestao._tem_celula_preenchida(aba_usada.linhas):
        principal = _tabela_da_aba(aba_usada)
    avisos = []
    for posicao, aba_lida in enumerate(abas_lidas):
        # Só as outras abas que têm alguma coisa escrita
        if posicao == posicao_da_aba or not ingestao._tem_celula_preenchida(aba_lida.linhas):
            continue
        # O motivo de ela não ter sido ligada (a mesma regra da junção das abas)
        motivo = "sem coluna em comum"
        tabela = _tabela_da_aba(aba_lida)
        if principal is not None and tabela is not None:
            _, motivo = _ligacao_da_aba(principal, tabela)
        avisos.append(_aviso_da_aba_de_fora(aba_lida.nome, aba_usada.nome, motivo))
    return avisos


def _aviso_da_aba_de_fora(nome_da_aba: str, nome_da_principal: str, motivo: str) -> str:
    """O aviso de uma aba que não foi usada, com o motivo e o que a empresa pode fazer.

    motivo: "repetido" (o identificador se repete) ou "sem coluna em comum".
    """
    if motivo == "repetido":
        return (f"Não usei a aba {nome_da_aba}: a coluna que a liga à aba {nome_da_principal} tem o mesmo valor em mais "
                "de uma linha, e não dá para saber qual linha é de quem. Deixe uma linha por pessoa em cada aba.")
    return (f"Não usei a aba {nome_da_aba}: não achei nela uma coluna em comum com a aba {nome_da_principal}, como o "
            "CPF. Se ela tem dados dos funcionários, junte tudo numa aba só, ou ponha o CPF em cada aba, e envie de "
            "novo.")


# ============================== 1. Abrir o arquivo ==============================

def _abas_do_arquivo(conteudo: bytes, nome_do_arquivo: str, limite_em_bytes: int) -> tuple[list, dict]:
    """As abas do arquivo como texto (o CSV é uma aba só). Devolve (abas, informações do formato).

    Devolve ([], {}) quando o formato não é de tabela (Word, por exemplo) ou quando o arquivo não abre: nos dois
    casos, a leitura de sempre segue e, se for o caso, recusa com a explicação dela.
    """
    try:
        # A mesma conferência de formato e tamanho da leitura de sempre
        extensao = ingestao.conferir_arquivo(conteudo, nome_do_arquivo, limite_em_bytes)
        if extensao == ".csv":
            return _abas_do_csv(conteudo)
        # O .txt só é tabela quando tem colunas (o texto corrido é do Word)
        if extensao == ".txt":
            texto, _ = ingestao._decodificar_texto(conteudo)
            if ingestao.texto_parece_tabela(texto):
                return _abas_do_csv(conteudo)
            return [], {}
        if extensao == ".xlsx":
            return _abas_do_xlsx(conteudo)
        # O .xls que é página HTML (exportação de sistema) fica com a leitura de sempre
        if extensao == ".ods" or (extensao == ".xls" and conteudo.startswith(ingestao.ASSINATURA_DO_OLE)):
            return _abas_do_xls_ou_ods(conteudo, extensao)
    except ingestao.ArquivoRecusado:
        # Recusa da própria ingestão (formato, tamanho, linhas demais, aspas sem fechar): a mensagem já é a certa, e
        # a leitura de sempre chegaria à mesma recusa lendo o arquivo inteiro de novo (C-04)
        raise
    except Exception:
        # Arquivo que não abre: a leitura de sempre dá a mensagem certa para a empresa
        return [], {}
    return [], {}


def _abas_do_csv(conteudo: bytes) -> tuple[list, dict]:
    """O CSV como uma aba só, com a codificação e o separador descobertos pela leitura de sempre."""
    linhas, informacoes = ingestao._ler_csv(conteudo)
    return [ingestao.AbaLida(nome="", linhas=linhas)], informacoes


def _abas_do_xlsx(conteudo: bytes) -> tuple[list, dict]:
    """Todas as abas de uma planilha .xlsx como texto. Com célula mesclada, fica para a leitura de sempre."""
    planilha = load_workbook(io.BytesIO(conteudo), data_only=True)
    try:
        abas = []
        for aba in planilha.worksheets:
            # Célula mesclada: a leitura de sempre sabe repetir o valor; aqui não (fica com ela)
            if aba.merged_cells.ranges:
                return [], {}
            abas.append(ingestao._ler_aba_do_excel(aba))
    finally:
        # Fecha a planilha para liberar o arquivo
        planilha.close()
    informacoes = {"formato": "xlsx", "codificacao": None, "separador": None}
    return abas, informacoes


def _abas_do_xls_ou_ods(conteudo: bytes, extensao: str) -> tuple[list, dict]:
    """Todas as abas de uma planilha .xls (Excel antigo) ou .ods (LibreOffice) como texto."""
    # sheet_name=None lê todas as abas; header=None: o cabeçalho é achado depois, pela regra da leitura de sempre
    tabelas_do_pandas = pandas.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None, dtype=object,
                                          engine=ingestao.MOTOR_DA_PLANILHA[extensao])
    abas = []
    for nome_da_aba, tabela in tabelas_do_pandas.items():
        abas.append(ingestao._ler_aba_do_pandas(nome_da_aba, tabela))
    informacoes = {"formato": extensao.lstrip("."), "codificacao": None, "separador": None}
    return abas, informacoes


# ============================== 2. Cada aba com o seu cabeçalho ==============================

def _tabelas_com_cabecalho(abas: list) -> list[TabelaDaAba]:
    """As abas preenchidas, cada uma com o cabeçalho achado. Se alguma preenchida não tem cabeçalho, devolve [].

    Por que tudo ou nada: sem o nome das colunas, não há como saber que colunas ligam as abas.
    """
    tabelas = []
    for aba in abas:
        # Aba vazia (uma capa em branco) não conta
        if not ingestao._tem_celula_preenchida(aba.linhas):
            continue
        tabela = _tabela_da_aba(aba)
        if tabela is None:
            return []
        tabelas.append(tabela)
    return tabelas


def _tabela_da_aba(aba) -> TabelaDaAba | None:
    """A aba com o cabeçalho achado e as linhas de dados (sem linha vazia, de total ou cabeçalho repetido).

    Devolve None se a aba não tem cabeçalho (a primeira linha já é uma pessoa) ou não tem nenhuma linha de dados.
    Exemplo: [["Nome", "CPF"], ["Ana", "529.982.247-25"], ["Nome", "CPF"], ["Rui", "111.444.777-35"]] → cabeçalhos
    ["Nome", "CPF"] e 2 linhas (o cabeçalho repetido no meio não é pessoa).
    """
    # A mesma regra da leitura de sempre para achar o cabeçalho
    posicao_do_cabecalho = ingestao.achar_cabecalho(aba.linhas)
    if ingestao.linha_parece_dado(aba.linhas[posicao_do_cabecalho]):
        return None
    # Só as colunas com nome ou com algum valor (sem colunas fantasmas)
    colunas_que_ficam = ingestao._colunas_com_nome_ou_valor(aba.linhas, posicao_do_cabecalho,
                                                            posicao_do_cabecalho + 1, False)
    linhas = ingestao._so_as_colunas(aba.linhas, colunas_que_ficam)
    colunas_numericas_por_linha = ingestao._renumerar_colunas_numericas(aba.celulas_numericas_por_linha,
                                                                         colunas_que_ficam)
    cabecalhos = ingestao._montar_cabecalhos(linhas[posicao_do_cabecalho], len(colunas_que_ficam))
    tabela = TabelaDaAba(nome=aba.nome, cabecalhos=cabecalhos, linhas=[], numeros_linha=[], colunas_numericas=[],
                         linha_do_cabecalho=posicao_do_cabecalho + 1, encontrou_data=aba.encontrou_data)
    # O cabeçalho em minúsculas e sem acento, para reconhecer quando ele se repete no meio dos dados
    cabecalho_comparavel = _linha_comparavel(linhas[posicao_do_cabecalho])
    for numero_da_linha in range(posicao_do_cabecalho + 1, len(linhas)):
        linha = linhas[numero_da_linha]
        # Linha vazia, linha de total ou o cabeçalho repetido não são pessoas
        if not any(linha) or ingestao.linha_parece_de_total(linha):
            continue
        if _linha_comparavel(linha) == cabecalho_comparavel:
            continue
        tabela.linhas.append(linha)
        tabela.numeros_linha.append(numero_da_linha + 1)
        tabela.colunas_numericas.append(colunas_numericas_por_linha.get(numero_da_linha, set()))
    if not tabela.linhas:
        return None
    return tabela


def _linha_comparavel(linha: list[str]) -> list[str]:
    """A linha em minúsculas e sem acento, célula por célula, para comparar ("Transcrição" = "transcricao")."""
    comparavel = []
    for celula in linha:
        comparavel.append(ingestao._sem_acento_minusculo(celula))
    return comparavel


# ============================== 3. As fichas: reconhecer ==============================

def _tipos_de_dado(texto: str) -> set[str]:
    """Os tipos de dado de pessoa que aparecem no texto (CPF, data, valor, CEP, telefone, e-mail, documento).

    Usa o detector do projeto (services/detector_de_dados.py). Ex.: "CPF 529.982.247-25, nasceu 12/03/1990" →
    {"CPF", "DATA"}.
    """
    tipos = set()
    # O detector marca uma cópia do texto ("[CPF_1]", "[DATA_1]"...); as etiquetas dizem o tipo de cada dado
    texto_marcado = detector_de_dados.marcar(texto).texto
    for etiqueta in detector_de_dados.etiquetas_do_texto(texto_marcado):
        # A etiqueta é "[CPF_1]": o tipo é o que vem antes do último "_"
        tipo = etiqueta.strip("[]").rsplit("_", 1)[0]
        if tipo in leitor_de_documentos.TIPOS_QUE_INDICAM_PESSOA:
            tipos.add(tipo)
    return tipos


def _coluna_das_fichas(tabela: TabelaDaAba) -> int | None:
    """A coluna em que estão as fichas (texto longo com vários dados juntos), ou None.

    Regra: pelo menos metade das células junta 2 tipos de dado ou mais, o texto é longo em média, e nenhuma coluna da
    tabela é "de CPF" (quando o CPF tem coluna própria, é uma tabela comum com uma coluna de observação).
    """
    if _tem_coluna_de_cpf(tabela):
        return None
    melhor_coluna = None
    maior_fracao = 0.0
    for numero_da_coluna in range(len(tabela.cabecalhos)):
        valores = _valores_da_coluna(tabela, numero_da_coluna)
        if not valores:
            continue
        # O tamanho médio do texto das células preenchidas
        total_de_caracteres = 0
        for valor in valores:
            total_de_caracteres += len(valor)
        media_de_caracteres = total_de_caracteres / len(valores)
        if media_de_caracteres < MEDIA_MINIMA_DE_CARACTERES_DA_FICHA:
            continue
        # Quantas células são fichas (juntam pelo menos 2 tipos de dado)
        quantidade_de_fichas = 0
        for valor in valores:
            if len(_tipos_de_dado(valor)) >= MINIMO_DE_TIPOS_DE_DADO_NA_FICHA:
                quantidade_de_fichas += 1
        # A fração é sobre todas as linhas (uma coluna quase vazia não é a das fichas)
        fracao = quantidade_de_fichas / len(tabela.linhas)
        if fracao >= FRACAO_MINIMA_DE_FICHAS_NA_COLUNA and fracao > maior_fracao:
            melhor_coluna = numero_da_coluna
            maior_fracao = fracao
    return melhor_coluna


def _tem_coluna_de_cpf(tabela: TabelaDaAba) -> bool:
    """True se alguma coluna tem um CPF sozinho em pelo menos metade das linhas (ex.: a coluna "CPF" de uma lista)."""
    for numero_da_coluna in range(len(tabela.cabecalhos)):
        quantidade_de_cpfs = 0
        for linha in tabela.linhas:
            if PADRAO_DO_CPF_NO_TEXTO.fullmatch(linha[numero_da_coluna].strip()):
                quantidade_de_cpfs += 1
        if quantidade_de_cpfs / len(tabela.linhas) >= FRACAO_DE_CPF_DE_UMA_COLUNA_DE_CPF:
            return True
    return False


def _valores_da_coluna(tabela: TabelaDaAba, numero_da_coluna: int) -> list[str]:
    """Os valores preenchidos de uma coluna, na ordem das linhas (as células vazias ficam de fora)."""
    valores = []
    for linha in tabela.linhas:
        if linha[numero_da_coluna]:
            valores.append(linha[numero_da_coluna])
    return valores


def _so_os_preenchidos(valores: list[str]) -> list[str]:
    """Só os valores preenchidos, na ordem (os vazios ficam de fora). Ex.: ["A1", "", "B2"] → ["A1", "B2"]."""
    preenchidos = []
    for valor in valores:
        if valor:
            preenchidos.append(valor)
    return preenchidos


def _todas_sao_de_fichas(tabelas: list[TabelaDaAba]) -> bool:
    """True se toda aba preenchida tem uma coluna de fichas (então o arquivo inteiro é de fichas)."""
    for tabela in tabelas:
        if _coluna_das_fichas(tabela) is None:
            return False
    return True


# ============================== 4. As fichas: montar as pessoas ==============================

def _fragmentos_das_tabelas(tabelas: list[TabelaDaAba]) -> tuple[list[Fragmento], list[dict]]:
    """Todos os pedaços de ficha das abas, na ordem do arquivo, e as colunas curtas de cada linha.

    Devolve (fragmentos, colunas curtas) — as colunas curtas de cada fragmento, {nome da coluna comparável: valor},
    servem para achar a referência.
    """
    fragmentos = []
    colunas_curtas_de_cada_fragmento = []
    for tabela in tabelas:
        coluna_das_fichas = _coluna_das_fichas(tabela)
        for linha, numero_linha in zip(tabela.linhas, tabela.numeros_linha):
            # A ficha vazia não é pedaço de ninguém
            if not linha[coluna_das_fichas]:
                continue
            # As outras colunas curtas desta linha, pelo nome comparável da coluna
            colunas_curtas = {}
            for numero_da_coluna, valor in enumerate(linha):
                if numero_da_coluna != coluna_das_fichas and valor and len(valor) <= MAXIMO_DE_CARACTERES_DA_REFERENCIA:
                    colunas_curtas[ingestao._sem_acento_minusculo(tabela.cabecalhos[numero_da_coluna])] = valor
            colunas_curtas_de_cada_fragmento.append(colunas_curtas)
            fragmentos.append(Fragmento(texto=linha[coluna_das_fichas], numero_linha=numero_linha,
                                        nome_da_aba=tabela.nome, complemento=""))
    return fragmentos, colunas_curtas_de_cada_fragmento


def _cpfs_do_texto(texto: str) -> set[str]:
    """Os CPFs escritos no texto, só com os dígitos (com qualquer dígito verificador: aqui só se agrupa)."""
    cpfs = set()
    for encontrado in PADRAO_DO_CPF_NO_TEXTO.findall(texto):
        cpfs.add(re.sub(r"\D", "", encontrado))
    return cpfs


def _nota_da_coluna_de_referencia(fragmentos: list[Fragmento], colunas_curtas: list[dict], coluna: str) -> int | None:
    """Quão bem uma coluna serve de referência: quantos grupos dela têm exatamente 1 CPF.

    Devolve None se a coluna não serve: falta em muitas linhas, não se repete, nenhum grupo tem CPF, ou algum grupo
    tem 2 CPFs ou mais (juntaria duas pessoas).
    Ideia: a referência de verdade separa as pessoas, então cada grupo dela tem um CPF. Uma coluna como "origem"
    ("ficha", "contato"...) junta os CPFs de todo mundo num grupo só e perde.
    """
    # O valor da coluna em cada fragmento
    valores = []
    for colunas_do_fragmento in colunas_curtas:
        valores.append(colunas_do_fragmento.get(coluna, ""))
    preenchidos = _so_os_preenchidos(valores)
    if len(preenchidos) / len(valores) < FRACAO_MINIMA_DE_REFERENCIAS_PREENCHIDAS:
        return None
    # Uma referência se repete (vários pedaços da mesma pessoa); sem repetição, cada linha já é uma pessoa
    if len(set(preenchidos)) == len(preenchidos):
        return None
    # Os CPFs de cada grupo
    cpfs_por_grupo = {}
    for valor, fragmento in zip(valores, fragmentos):
        if valor:
            cpfs_por_grupo.setdefault(valor, set()).update(_cpfs_do_texto(fragmento.texto))
    grupos_com_um_cpf = 0
    grupos_com_varios_cpfs = 0
    for cpfs in cpfs_por_grupo.values():
        if len(cpfs) == 1:
            grupos_com_um_cpf += 1
        elif len(cpfs) > 1:
            grupos_com_varios_cpfs += 1
    # Um grupo com dois CPFs misturaria duas pessoas: a coluna não serve (melhor parar do que misturar)
    if grupos_com_um_cpf == 0 or grupos_com_varios_cpfs > 0:
        return None
    return grupos_com_um_cpf


def _coluna_de_referencia(fragmentos: list[Fragmento], colunas_curtas: list[dict]) -> str | None:
    """O nome (comparável) da coluna que diz de quem é cada pedaço, ou None se não houver.

    Só valem colunas que existem em todas as abas com o mesmo nome. No empate, a que tem mais grupos.
    """
    # As colunas curtas que aparecem nos fragmentos
    candidatas = []
    for colunas_do_fragmento in colunas_curtas:
        for coluna in colunas_do_fragmento:
            if coluna not in candidatas:
                candidatas.append(coluna)
    melhor_coluna = None
    melhor_nota = None
    for coluna in candidatas:
        nota = _nota_da_coluna_de_referencia(fragmentos, colunas_curtas, coluna)
        if nota is None:
            continue
        if melhor_nota is None or nota > melhor_nota:
            melhor_coluna = coluna
            melhor_nota = nota
    return melhor_coluna


def _pessoas_dos_fragmentos(fragmentos: list[Fragmento], colunas_curtas: list[dict],
                            coluna_de_referencia: str | None) -> tuple[list[PessoaDasFichas], list[str]]:
    """Agrupa os pedaços por pessoa. Devolve (pessoas, avisos).

    Com referência: um grupo por referência, na ordem em que cada uma aparece. Sem referência: uma pessoa por linha.
    O complemento de cada pedaço são as outras colunas curtas (ex.: "proposta"), que ajudam a IA a entender o texto.
    """
    avisos = []
    pessoas_por_referencia = {}
    for fragmento, colunas_do_fragmento in zip(fragmentos, colunas_curtas):
        # O complemento: as colunas curtas que não são a referência
        partes_do_complemento = []
        for coluna, valor in colunas_do_fragmento.items():
            if coluna != coluna_de_referencia:
                partes_do_complemento.append(valor)
        fragmento.complemento = ", ".join(partes_do_complemento)
        # Sem coluna de referência, cada linha é uma pessoa
        if coluna_de_referencia is None:
            referencia = f"linha {fragmento.numero_linha}"
            if fragmento.nome_da_aba:
                referencia = f"aba {fragmento.nome_da_aba}, {referencia}"
        else:
            referencia = colunas_do_fragmento.get(coluna_de_referencia, "")
        # Pedaço sem referência: não dá para saber de quem é, e a empresa fica sabendo
        if not referencia:
            avisos.append(f"A linha {fragmento.numero_linha} não tem referência: o texto dela ficou de fora.")
            continue
        fragmento.referencia = referencia
        pessoas_por_referencia.setdefault(referencia, PessoaDasFichas(referencia=referencia)).fragmentos.append(
            fragmento)
    # Em cada pessoa, o pedaço que a identifica (o que tem o CPF) vem primeiro; os outros seguem na ordem do arquivo
    for pessoa in pessoas_por_referencia.values():
        pessoa.fragmentos = _com_o_cpf_primeiro(pessoa.fragmentos)
    return list(pessoas_por_referencia.values()), avisos


def _com_o_cpf_primeiro(fragmentos: list[Fragmento]) -> list[Fragmento]:
    """Os pedaços com o CPF primeiro e os outros depois, cada grupo na ordem do arquivo.

    Por quê: o texto começa por quem é a pessoa (o nome costuma estar junto do CPF), e a linha da pessoa na conferência
    passa a ser a da ficha dela. Ex.: [contato, ficha com CPF, contrato] → [ficha com CPF, contato, contrato].
    """
    com_cpf = []
    sem_cpf = []
    for fragmento in fragmentos:
        if _cpfs_do_texto(fragmento.texto):
            com_cpf.append(fragmento)
        else:
            sem_cpf.append(fragmento)
    return com_cpf + sem_cpf


def _texto_da_pessoa(pessoa: PessoaDasFichas, com_nome_da_aba: bool) -> tuple[str, list[dict]]:
    """O texto que a IA lê para uma pessoa: os pedaços numa linha só, separados por " | ". Devolve (texto, alertas).

    Numa linha só porque o Leitor de Documentos divide o texto em blocos por linha: assim, uma pessoa é um bloco.
    Cada pedaço vem com o complemento entre colchetes (e a aba, se o arquivo tem várias). O pedaço com cara de ordem
    para a IA é trocado pelo aviso do guardrail ANTES de a IA ler (ADR-38), e fica anotado.
    Ex.: "[contrato] Vendedora; início 05/08/2026 | [contato] Rua Um, 10; CEP 01001-000".
    """
    pedacos = []
    alertas = []
    for fragmento in pessoa.fragmentos:
        texto = fragmento.texto.replace("\n", " ")
        if guardrail_injecao.e_suspeito(texto):
            alertas.append({"linha": fragmento.numero_linha, "coluna": 0, "onde": "célula",
                            "padroes": guardrail_injecao.padroes_encontrados(texto)})
            texto = guardrail_injecao.SUBSTITUTO
        # O que se sabe do pedaço: a aba (se houver várias) e as outras colunas curtas
        partes_da_etiqueta = []
        if com_nome_da_aba and fragmento.nome_da_aba:
            partes_da_etiqueta.append(fragmento.nome_da_aba)
        if fragmento.complemento:
            partes_da_etiqueta.append(fragmento.complemento)
        if partes_da_etiqueta:
            texto = f"[{' · '.join(partes_da_etiqueta)}] {texto}"
        pedacos.append(texto)
    return " | ".join(pedacos), alertas


# ============================== 5. As fichas: ler com a IA ==============================

def _ler_fichas(tabelas: list[TabelaDaAba], informacoes_do_formato: dict, cliente, campos_do_layout):
    """Monta as pessoas das fichas, pede os campos de cada uma à IA e confere. Devolve a ingestao.Leitura.

    Recusa (ingestao.ArquivoRecusado) quando não dá para montar as pessoas com segurança.
    """
    fragmentos, colunas_curtas = _fragmentos_das_tabelas(tabelas)
    coluna_de_referencia = _coluna_de_referencia(fragmentos, colunas_curtas)
    # Sem referência, cada linha deveria ser uma pessoa inteira; se a maioria não tem CPF, são pedaços soltos
    if coluna_de_referencia is None:
        _recusar_pedacos_sem_referencia(fragmentos)
    pessoas, avisos = _pessoas_dos_fragmentos(fragmentos, colunas_curtas, coluna_de_referencia)
    if len(pessoas) > MAXIMO_DE_PESSOAS_POR_ENVIO:
        raise ingestao.ArquivoRecusado(f"O arquivo tem mais de {MAXIMO_DE_PESSOAS_POR_ENVIO} fichas para o Agente "
                                       "Leitor ler de uma vez. Divida em arquivos menores.")
    if campos_do_layout is None:
        campos_do_layout = carregar_layout()
    if cliente is None:
        cliente = leitor_de_documentos.cliente_padrao()
    # O texto de cada pessoa (com o guardrail já aplicado)
    com_nome_da_aba = len(tabelas) > 1
    textos = []
    alertas = []
    for pessoa in pessoas:
        texto, alertas_da_pessoa = _texto_da_pessoa(pessoa, com_nome_da_aba)
        textos.append(texto)
        alertas.extend(alertas_da_pessoa)
    # A IA lê cada pessoa (várias ao mesmo tempo) e as leituras viram uma tabela só
    tabela_das_pessoas, numeros_linha = _ler_cada_pessoa(pessoas, textos, campos_do_layout, cliente)
    # A conferência por regra: nome, CPF e CPF repetido
    _conferir_as_pessoas(tabela_das_pessoas)
    if not tabela_das_pessoas.funcionarios:
        explicacao = "Não encontrei funcionários nas fichas deste arquivo."
        if tabela_das_pessoas.duvidas:
            explicacao += " " + " ".join(tabela_das_pessoas.duvidas)
        _recusar_depois_da_ia(explicacao, tabela_das_pessoas)
    return _leitura_das_fichas(tabela_das_pessoas, numeros_linha, tabelas, informacoes_do_formato, coluna_de_referencia,
                               avisos, alertas)


def _recusar_pedacos_sem_referencia(fragmentos: list[Fragmento]) -> None:
    """Recusa as fichas sem coluna de referência quando mais da metade das linhas não tem CPF (são pedaços soltos)."""
    linhas_sem_cpf = 0
    for fragmento in fragmentos:
        if not _cpfs_do_texto(fragmento.texto):
            linhas_sem_cpf += 1
    if linhas_sem_cpf / len(fragmentos) > FRACAO_MAXIMA_DE_LINHAS_SEM_CPF:
        raise ingestao.ArquivoRecusado(
            "As fichas estão em pedaços, e não achei uma coluna que diga de quem é cada pedaço. Ponha em cada linha "
            "uma referência da pessoa (a matrícula, por exemplo), ou mande uma ficha inteira por linha, com o CPF.")


def _ler_cada_pessoa(pessoas: list[PessoaDasFichas], textos: list[str], campos_do_layout,
                     cliente) -> tuple[leitor_de_documentos.TabelaDoDocumento, list[int]]:
    """Pede ao Leitor de Documentos os campos de cada pessoa e junta tudo numa tabela. Devolve (tabela, linhas).

    linhas: para cada funcionário da tabela, a linha do arquivo em que começa a ficha dele.
    Várias pessoas ao mesmo tempo, como o Leitor faz com os blocos do Word. copy_context() leva junto o "bilhete" do
    progresso da tela (services/progresso.py), que fica preso à tarefa que começou a leitura.
    """
    leituras = []
    with ThreadPoolExecutor(max_workers=leitor_de_documentos.LEITURAS_AO_MESMO_TEMPO) as executor:
        tarefas = []
        for texto in textos:
            contexto = copy_context()
            tarefas.append(executor.submit(contexto.run, leitor_de_documentos.ler, texto, campos_do_layout, cliente))
        for tarefa in tarefas:
            try:
                leituras.append(tarefa.result())
            except leitor_de_documentos.IAIndisponivel as erro:
                # A IA caiu: o arquivo é recusado com o recado simples; as execuções medidas seguem no erro
                execucoes_medidas = list(getattr(erro, "execucoes_dos_agentes", []))
                causa = leitura_de_word.DocumentoRecusado(
                    "A leitura das fichas pelo Agente Leitor está indisponível agora. Tente de novo em alguns "
                    "minutos; se continuar, mande os dados numa tabela, um dado por coluna.", execucoes_medidas)
                raise ingestao.ArquivoRecusado(str(causa)) from causa
            except teto_de_gasto.TetoDeGastoAtingido as erro:
                # A IA foi pausada pelo teto de gasto (ADR-131): o arquivo não entra (a empresa continua com ele)
                execucoes_medidas = list(getattr(erro, "execucoes_dos_agentes", []))
                causa = leitura_de_word.DocumentoRecusado(teto_de_gasto.RECADO_DO_ARQUIVO_RECUSADO, execucoes_medidas)
                raise ingestao.ArquivoRecusado(str(causa)) from causa
    return _juntar_as_leituras(pessoas, leituras, campos_do_layout)


def _juntar_as_leituras(pessoas: list[PessoaDasFichas], leituras: list, campos_do_layout
                        ) -> tuple[leitor_de_documentos.TabelaDoDocumento, list[int]]:
    """Junta as tabelas lidas (uma por pessoa) numa tabela só, como se o Leitor tivesse lido tudo de uma vez.

    Uma referência é uma pessoa: se a IA achar mais de uma, fica a que tem mais dados, e a empresa é avisada.
    """
    juntas = leitor_de_documentos.TabelaDoDocumento(colunas=[], funcionarios=[])
    juntas.uso = {"chamadas": 0, leitor_de_documentos.CHAVE_DAS_EXECUCOES: []}
    valores_das_pessoas = []
    numeros_linha = []
    for pessoa, leitura in zip(pessoas, leituras):
        _somar_o_uso(juntas.uso, leitura.uso)
        # As perguntas da IA sem pessoa (ex.: um trecho que ela não conseguiu ler)
        juntas.duvidas_gerais.extend(leitura.duvidas_gerais)
        if not leitura.funcionarios:
            texto = f"Referência {pessoa.referencia}: não encontrei um funcionário nestes pedaços."
            juntas.duvidas.append(texto)
            juntas.duvidas_gerais.append(texto)
            continue
        posicao_escolhida = _pessoa_com_mais_dados(leitura.funcionarios)
        if len(leitura.funcionarios) > 1:
            texto = (f"Referência {pessoa.referencia}: achei {len(leitura.funcionarios)} pessoas nos pedaços; "
                     "fiquei com a que tem mais dados. Confira.")
            juntas.duvidas.append(texto)
            juntas.duvidas_gerais.append(texto)
        # Os valores da pessoa escolhida, por campo
        valores = {}
        for coluna, valor in zip(leitura.colunas, leitura.funcionarios[posicao_escolhida]):
            if valor:
                valores[coluna] = valor
        valores_das_pessoas.append(valores)
        juntas.rotulos_das_pessoas.append(leitura.rotulos_das_pessoas[posicao_escolhida])
        numeros_linha.append(pessoa.fragmentos[0].numero_linha)
        # As perguntas da pessoa escolhida, presas à posição dela na tabela junta
        registro_na_tabela_junta = len(valores_das_pessoas)
        for pergunta in leitura.perguntas:
            if pergunta["registro"] == posicao_escolhida + 1:
                juntas.perguntas.append({"registro": registro_na_tabela_junta, "campo": pergunta["campo"],
                                         "pergunta": pergunta["pergunta"]})
        juntas.duvidas.extend(leitura.duvidas)
    _montar_colunas_e_linhas(juntas, valores_das_pessoas, campos_do_layout)
    return juntas, numeros_linha


def _pessoa_com_mais_dados(funcionarios: list[list[str]]) -> int:
    """A posição do funcionário com mais campos preenchidos (no empate, o primeiro)."""
    posicao_escolhida = 0
    maior_quantidade = -1
    for posicao, valores in enumerate(funcionarios):
        quantidade = len(_so_os_preenchidos(valores))
        if quantidade > maior_quantidade:
            posicao_escolhida = posicao
            maior_quantidade = quantidade
    return posicao_escolhida


def _somar_o_uso(uso_total: dict, uso_da_pessoa: dict) -> None:
    """Soma o uso da IA de uma pessoa no uso total: chamadas, tokens, custo, modelos e execuções medidas."""
    for chave in ("chamadas", "tokens_entrada", "tokens_saida", "custo_usd", "respostas_cortadas"):
        if chave in uso_da_pessoa:
            uso_total[chave] = uso_total.get(chave, 0) + uso_da_pessoa[chave]
    for chave in ("modo", "esforco"):
        if chave in uso_da_pessoa:
            uso_total[chave] = uso_da_pessoa[chave]
    modelos = uso_total.setdefault("modelos", [])
    for modelo in uso_da_pessoa.get("modelos", []):
        if modelo not in modelos:
            modelos.append(modelo)
    uso_total[leitor_de_documentos.CHAVE_DAS_EXECUCOES].extend(
        uso_da_pessoa.get(leitor_de_documentos.CHAVE_DAS_EXECUCOES, []))


def _montar_colunas_e_linhas(tabela, valores_das_pessoas: list[dict], campos_do_layout) -> None:
    """As colunas (os campos achados em alguém, na ordem do layout), as linhas e a origem de cada coluna."""
    for campo in campos_do_layout:
        for valores in valores_das_pessoas:
            if campo.campo in valores:
                tabela.colunas.append(campo.campo)
                break
    for valores in valores_das_pessoas:
        linha = []
        for coluna in tabela.colunas:
            linha.append(valores.get(coluna, ""))
        tabela.funcionarios.append(linha)
    _refazer_a_origem_das_colunas(tabela)


def _refazer_a_origem_das_colunas(tabela) -> None:
    """Como a empresa chamou cada campo e em quantas pessoas ele aparece (a mesma conta do Leitor de Documentos)."""
    rotulos_por_campo = {}
    pessoas_por_campo = Counter()
    for rotulos_da_pessoa, valores in zip(tabela.rotulos_das_pessoas, tabela.funcionarios):
        for campo, valor in zip(tabela.colunas, valores):
            # Só conta o campo que a pessoa tem (a conferência pode ter apagado um nome impossível)
            if not valor:
                continue
            pessoas_por_campo[campo] += 1
            rotulo = rotulos_da_pessoa.get(campo, "")
            if rotulo:
                rotulos_por_campo.setdefault(campo, Counter())[rotulo] += 1
    tabela.origem_das_colunas = leitor_de_documentos.origem_das_colunas(rotulos_por_campo, pessoas_por_campo)


# ============================== 6. As fichas: conferir por regra ==============================

def nome_e_impossivel(nome: str) -> bool:
    """True se o texto não pode ser um nome de pessoa: tem número, "@" ou palavras demais.

    Ex.: "Ana Lima" → False; "CEP 01001-000. falar (11) 9..." → True; "ana@exemplo.com" → True.
    """
    if re.search(r"\d", nome) or "@" in nome:
        return True
    return len(nome.split()) > MAXIMO_DE_PALAVRAS_DO_NOME


def _conferir_as_pessoas(tabela) -> None:
    """A conferência por regra depois da IA: o nome impossível sai, o CPF inválido e o CPF repetido viram pergunta.

    As perguntas ficam presas à pessoa e ao campo: viram pendência na conferência, como as do Leitor (ADR-73).
    """
    posicao_do_nome = _posicao_da_coluna(tabela, CAMPO_DO_NOME)
    posicao_do_cpf = _posicao_da_coluna(tabela, CAMPO_DO_CPF)
    # Em que pessoas aparece cada CPF (só os dígitos)
    pessoas_por_cpf = {}
    for registro, valores in enumerate(tabela.funcionarios, start=1):
        nome = _valor_na_posicao(valores, posicao_do_nome)
        if nome and nome_e_impossivel(nome):
            # O texto sai do nome (não é um nome) e a empresa diz qual é
            valores[posicao_do_nome] = ""
            _perguntar(tabela, registro, CAMPO_DO_NOME, f"O texto lido como nome (\"{nome[:60]}\") não parece um "
                                                        "nome de pessoa. Qual é o nome completo?")
        cpf = _valor_na_posicao(valores, posicao_do_cpf)
        if not cpf:
            continue
        if not cpf_valido(cpf):
            _perguntar(tabela, registro, CAMPO_DO_CPF, f"O CPF {cpf} não é válido: os dígitos verificadores não "
                                                      "conferem. Confira o número.")
        pessoas_por_cpf.setdefault(re.sub(r"\D", "", cpf), []).append(registro)
    # O mesmo CPF em duas pessoas: pergunta nas duas
    for cpf, registros in pessoas_por_cpf.items():
        if len(registros) > 1:
            for registro in registros:
                _perguntar(tabela, registro, CAMPO_DO_CPF, f"O mesmo CPF está em {len(registros)} pessoas deste "
                                                          "arquivo. Confira de quem é.")
    # A origem das colunas conta de novo, sem os nomes apagados
    _refazer_a_origem_das_colunas(tabela)


def _posicao_da_coluna(tabela, campo: str) -> int | None:
    """A posição do campo nas colunas da tabela, ou None se ninguém tem esse campo."""
    if campo in tabela.colunas:
        return tabela.colunas.index(campo)
    return None


def _valor_na_posicao(valores: list[str], posicao: int | None) -> str:
    """O valor na posição (vazio quando a coluna não existe)."""
    if posicao is None:
        return ""
    return valores[posicao]


def _perguntar(tabela, registro: int, campo: str, pergunta: str) -> None:
    """Guarda uma pergunta presa à pessoa (registro = posição na tabela, a partir de 1) e ao campo."""
    tabela.perguntas.append({"registro": registro, "campo": campo, "pergunta": pergunta})
    tabela.duvidas.append(f"Pessoa {registro} · {campo}: {pergunta}")


def _recusar_depois_da_ia(explicacao: str, tabela) -> None:
    """Recusa o arquivo depois de a IA trabalhar: as execuções medidas seguem no erro (e são gravadas)."""
    causa = leitura_de_word.DocumentoRecusado(explicacao,
                                               list(tabela.uso.get(leitor_de_documentos.CHAVE_DAS_EXECUCOES, [])))
    raise ingestao.ArquivoRecusado(str(causa)) from causa


def _leitura_das_fichas(tabela, numeros_linha: list[int], tabelas: list[TabelaDaAba], informacoes_do_formato: dict,
                        coluna_de_referencia: str | None, avisos: list[str], alertas: list[dict]):
    """Monta a ingestao.Leitura das fichas: uma coluna por jeito de a empresa chamar o dado, como no Word."""
    linhas, origem = leitura_de_word.tabela_pelos_rotulos(tabela)
    como_foi_lido = COMO_FOI_LIDO_UMA_POR_LINHA
    explicacao = "cada linha é uma ficha"
    if coluna_de_referencia is not None:
        como_foi_lido = COMO_FOI_LIDO_POR_REFERENCIA
        explicacao = "juntando os pedaços de cada referência"
    leitura = ingestao.Leitura(cabecalhos=linhas[0], linhas=linhas[1:], formato=informacoes_do_formato["formato"],
                               codificacao=informacoes_do_formato.get("codificacao"),
                               separador=informacoes_do_formato.get("separador"),
                               linha_do_cabecalho=tabelas[0].linha_do_cabecalho, numeros_linha=numeros_linha,
                               duvidas=list(tabela.duvidas_gerais), origem_das_colunas=origem)
    leitura.avisos.append(f"Fichas em texto: o Agente Leitor montou {len(tabela.funcionarios)} funcionário(s), "
                          f"{explicacao}. Você confere tudo antes de enviar ao banco.")
    leitura.avisos.extend(avisos)
    if alertas:
        leitura.avisos.append(f"{len(alertas)} trecho(s) com cara de ordem para o Agente Leitor foram tirados pelo "
                              "Guardrail antes da leitura.")
    leitura.alertas_guardrail.extend(alertas)
    # As perguntas presas à linha do arquivo de cada pessoa
    for pergunta in tabela.perguntas:
        leitura.perguntas_da_ia.append({"linha": numeros_linha[pergunta["registro"] - 1], "campo": pergunta["campo"],
                                        "pergunta": pergunta["pergunta"]})
    # O uso da IA vai para a auditoria (nada pessoal); as execuções seguem nele, e services/processamentos.py as tira
    leitura.uso_da_ia = dict(tabela.uso)
    leitura.uso_da_ia["funcionarios"] = len(tabela.funcionarios)
    leitura.uso_da_ia["duvidas"] = len(tabela.duvidas)
    leitura.uso_da_ia["como_foi_lido"] = como_foi_lido
    # O guardrail de sempre sobre o que a IA devolveu
    ingestao._aplicar_guardrail(leitura)
    return leitura


# ============================== 7. Abas ligadas por um identificador ==============================

def _valor_do_identificador(texto: str) -> str:
    """O identificador pronto para comparar entre abas. Só número: sem pontos e sem zeros à esquerda.

    Por que tirar os zeros: o Excel grava o CPF como número e perde o zero da frente ("012.345..." vira 12345...).
    Ex.: "052.998.224-25" → "52998224725"; "52998224725" → "52998224725"; "RH-07" → "rh-07".
    """
    texto = texto.strip()
    if re.fullmatch(r"[\d.\-/\s]+", texto):
        so_digitos = re.sub(r"\D", "", texto)
        return so_digitos.lstrip("0") or "0"
    return texto.casefold()


def _identificadores_da_coluna(tabela: TabelaDaAba, numero_da_coluna: int) -> list[str] | None:
    """Os identificadores da coluna, um por linha ("" na linha vazia), ou None se a coluna não é de identificador.

    Coluna de identificador: preenchida em quase todas as linhas e todo valor tem algum número (um nome não
    identifica: pode haver duas "Ana Lima").
    """
    identificadores = []
    preenchidos = 0
    for linha in tabela.linhas:
        valor = linha[numero_da_coluna]
        if valor and not re.search(r"\d", valor):
            return None
        if valor:
            preenchidos += 1
            identificadores.append(_valor_do_identificador(valor))
        else:
            identificadores.append("")
    if preenchidos / len(tabela.linhas) < FRACAO_MINIMA_DE_IDENTIFICADORES_PREENCHIDOS:
        return None
    return identificadores


def _coluna_e_de_cpf(tabela: TabelaDaAba, numero_da_coluna: int) -> bool:
    """True se a maioria dos valores da coluna é um CPF válido (com os zeros da frente de volta)."""
    quantidade_de_cpfs = 0
    for linha in tabela.linhas:
        so_digitos = re.sub(r"\D", "", linha[numero_da_coluna])
        if so_digitos and cpf_valido(so_digitos.zfill(11)):
            quantidade_de_cpfs += 1
    return quantidade_de_cpfs / len(tabela.linhas) >= FRACAO_DE_CPF_DE_UMA_COLUNA_DE_CPF


@dataclass
class Ligacao:
    """Como uma aba de fora se liga à aba principal: a coluna de cada lado e o que se sabe dela."""

    tabela: TabelaDaAba                         # a aba de fora
    coluna_na_principal: int                    # a coluna do identificador na aba principal
    coluna_na_aba: int                          # a coluna do identificador na aba de fora
    e_cpf: bool                                 # se o identificador é o CPF
    identificadores: list[str] = field(default_factory=list)  # o identificador de cada linha da aba de fora


def _ligacao_da_aba(principal: TabelaDaAba, tabela: TabelaDaAba) -> tuple[Ligacao | None, str]:
    """A melhor ligação entre a aba principal e uma aba de fora. Devolve (ligação ou None, motivo quando None).

    Regra: um par de colunas de identificador em que pelo menos metade dos valores da aba de fora aparece na
    principal. O CPF vem antes de qualquer outro identificador; depois, o par com mais valores em comum.
    O identificador que se repete numa das abas não liga (não daria para saber qual linha é de quem).
    """
    melhor_ligacao = None
    melhor_ordem = None
    repetido = False
    for coluna_na_principal in range(len(principal.cabecalhos)):
        identificadores_da_principal = _identificadores_da_coluna(principal, coluna_na_principal)
        if identificadores_da_principal is None:
            continue
        conjunto_da_principal = set(identificadores_da_principal) - {""}
        for coluna_na_aba in range(len(tabela.cabecalhos)):
            identificadores_da_aba = _identificadores_da_coluna(tabela, coluna_na_aba)
            if identificadores_da_aba is None:
                continue
            preenchidos_da_aba = _so_os_preenchidos(identificadores_da_aba)
            em_comum = set(preenchidos_da_aba) & conjunto_da_principal
            if len(em_comum) / len(set(preenchidos_da_aba)) < FRACAO_MINIMA_DE_IDENTIFICADORES_EM_COMUM:
                continue
            # Em comum, mas repetido numa das abas: não liga (e a empresa fica sabendo)
            if (len(set(preenchidos_da_aba)) < len(preenchidos_da_aba)
                    or len(conjunto_da_principal) < len(_so_os_preenchidos(identificadores_da_principal))):
                repetido = True
                continue
            e_cpf = _coluna_e_de_cpf(principal, coluna_na_principal) and _coluna_e_de_cpf(tabela, coluna_na_aba)
            # A ordem de preferência: o CPF primeiro, depois mais valores em comum
            ordem = (e_cpf, len(em_comum))
            if melhor_ordem is None or ordem > melhor_ordem:
                melhor_ordem = ordem
                melhor_ligacao = Ligacao(tabela=tabela, coluna_na_principal=coluna_na_principal,
                                         coluna_na_aba=coluna_na_aba, e_cpf=e_cpf,
                                         identificadores=identificadores_da_aba)
    if melhor_ligacao is None and repetido:
        return None, "repetido"
    if melhor_ligacao is None:
        return None, "sem coluna em comum"
    return melhor_ligacao, ""


def _ler_abas_ligadas(abas: list, tabelas: list[TabelaDaAba], conteudo: bytes, informacoes_do_formato: dict):
    """Junta as abas ligadas à aba principal numa tabela só. Devolve a ingestao.Leitura, ou None se nenhuma se liga.

    A aba principal é a que a leitura de sempre escolheria (a que tem mais linhas com CPF).
    """
    posicao_da_principal = ingestao._posicao_da_aba_da_lista(abas)
    principal = _tabela_pelo_nome(tabelas, abas[posicao_da_principal].nome)
    if principal is None:
        return None
    ligacoes = []
    avisos_das_que_ficaram_de_fora = []
    for tabela in tabelas:
        if tabela is principal:
            continue
        ligacao, motivo = _ligacao_da_aba(principal, tabela)
        if ligacao is not None:
            ligacoes.append(ligacao)
        else:
            avisos_das_que_ficaram_de_fora.append(_aviso_da_aba_de_fora(tabela.nome, principal.nome, motivo))
    # Nenhuma aba se liga: fica a leitura de sempre (de uma aba só, com o aviso dela)
    if not ligacoes:
        return None
    # Planilha com fórmula é recusada, como na leitura de sempre, agora em todas as abas usadas
    if informacoes_do_formato["formato"] == "xlsx":
        for tabela in [principal] + [ligacao.tabela for ligacao in ligacoes]:
            ingestao._recusar_formulas(conteudo, _posicao_da_aba_pelo_nome(abas, tabela.nome))
    return _leitura_das_abas_ligadas(principal, ligacoes, tabelas, informacoes_do_formato,
                                     avisos_das_que_ficaram_de_fora)


def _tabela_pelo_nome(tabelas: list[TabelaDaAba], nome: str) -> TabelaDaAba | None:
    """A tabela da aba com esse nome (None se ela não tem cabeçalho ou está vazia)."""
    for tabela in tabelas:
        if tabela.nome == nome:
            return tabela
    return None


def _posicao_da_aba_pelo_nome(abas: list, nome: str) -> int:
    """A posição da aba com esse nome na planilha (0 = a primeira)."""
    for posicao, aba in enumerate(abas):
        if aba.nome == nome:
            return posicao
    return 0


def _leitura_das_abas_ligadas(principal: TabelaDaAba, ligacoes: list[Ligacao], tabelas: list[TabelaDaAba],
                              informacoes_do_formato: dict, avisos_das_que_ficaram_de_fora: list[str]):
    """Monta a tabela junta (uma linha por pessoa) e a ingestao.Leitura dela."""
    cabecalhos = list(principal.cabecalhos)
    # As linhas começam com as da principal; as colunas de cada aba ligada entram à direita
    linhas = []
    for linha in principal.linhas:
        linhas.append(list(linha))
    numeros_linha = list(principal.numeros_linha)
    colunas_numericas = []
    for colunas_da_linha in principal.colunas_numericas:
        colunas_numericas.append(set(colunas_da_linha))
    avisos = []
    for ligacao in ligacoes:
        avisos.extend(_juntar_uma_aba(ligacao, principal, cabecalhos, linhas, numeros_linha, colunas_numericas))
    # Os nomes das abas e da coluna que ligou, para o aviso
    nomes_das_ligadas = []
    for ligacao in ligacoes:
        nomes_das_ligadas.append(ligacao.tabela.nome)
    nome_do_identificador = principal.cabecalhos[ligacoes[0].coluna_na_principal]
    leitura = ingestao.Leitura(cabecalhos=cabecalhos, linhas=[], formato=informacoes_do_formato["formato"],
                               linha_do_cabecalho=principal.linha_do_cabecalho)
    leitura.avisos.append(f"Juntei as abas {principal.nome} e {', '.join(nomes_das_ligadas)} pela coluna "
                          f"{nome_do_identificador}: {len(linhas)} funcionário(s), um por linha.")
    leitura.avisos.extend(avisos)
    leitura.avisos.extend(avisos_das_que_ficaram_de_fora)
    # Nada muda em silêncio: a empresa é avisada do formato em que as datas foram lidas
    for tabela in tabelas:
        if tabela.encontrou_data:
            leitura.avisos.append("Células de data da planilha foram lidas no formato AAAA-MM-DD.")
            break
    _completar_a_leitura(leitura, linhas, numeros_linha, colunas_numericas)
    return leitura


def _juntar_uma_aba(ligacao: Ligacao, principal: TabelaDaAba, cabecalhos: list[str], linhas: list[list[str]],
                    numeros_linha: list[int], colunas_numericas: list[set[int]]) -> list[str]:
    """Põe as colunas de uma aba ligada à direita da tabela junta. Devolve os avisos desta aba.

    Mexe nas listas recebidas: cabecalhos, linhas, numeros_linha e colunas_numericas crescem juntos.
    A pessoa que só está na aba ligada entra com o que tem, com aviso.
    """
    tabela = ligacao.tabela
    # As colunas da aba ligada que entram (o identificador já está na principal)
    colunas_que_entram = []
    for numero_da_coluna in range(len(tabela.cabecalhos)):
        if numero_da_coluna != ligacao.coluna_na_aba:
            colunas_que_entram.append(numero_da_coluna)
    primeira_coluna_nova = len(cabecalhos)
    for numero_da_coluna in colunas_que_entram:
        nome = tabela.cabecalhos[numero_da_coluna]
        # Coluna com o mesmo nome de uma que já existe: ganha o nome da aba (ex.: "Observação (Contratos)")
        if nome in cabecalhos:
            nome = f"{nome} ({tabela.nome})"
        cabecalhos.append(nome)
    # Completa as linhas que já existem com células vazias nas colunas novas
    for linha in linhas:
        linha.extend([""] * (len(cabecalhos) - len(linha)))
    # Onde está cada identificador na tabela junta
    identificadores_da_principal = _identificadores_da_coluna(principal, ligacao.coluna_na_principal)
    posicao_por_identificador = {}
    for posicao, identificador in enumerate(identificadores_da_principal):
        if identificador:
            posicao_por_identificador[identificador] = posicao
    linhas_so_nesta_aba = []
    achados = set()
    for linha_da_aba, numero_linha, numericas, identificador in zip(tabela.linhas, tabela.numeros_linha,
                                                                    tabela.colunas_numericas,
                                                                    ligacao.identificadores):
        if not identificador:
            continue
        posicao = posicao_por_identificador.get(identificador)
        if posicao is None:
            # Só está nesta aba: vira uma linha nova, com o identificador na coluna da principal
            nova_linha = [""] * len(cabecalhos)
            nova_linha[ligacao.coluna_na_principal] = linha_da_aba[ligacao.coluna_na_aba]
            linhas.append(nova_linha)
            numeros_linha.append(numero_linha)
            colunas_numericas.append(set())
            posicao = len(linhas) - 1
            linhas_so_nesta_aba.append(numero_linha)
        achados.add(posicao)
        # As células desta aba nas colunas novas da linha
        for deslocamento, numero_da_coluna in enumerate(colunas_que_entram):
            linhas[posicao][primeira_coluna_nova + deslocamento] = linha_da_aba[numero_da_coluna]
            if numero_da_coluna in numericas:
                colunas_numericas[posicao].add(primeira_coluna_nova + deslocamento)
        if ligacao.coluna_na_aba in numericas:
            colunas_numericas[posicao].add(ligacao.coluna_na_principal)
    # Quantas pessoas da aba principal não têm linha nesta aba
    pessoas_sem_esta_aba = 0
    for posicao in range(len(principal.linhas)):
        if posicao not in achados:
            pessoas_sem_esta_aba += 1
    return _avisos_da_juncao(ligacao, principal, linhas_so_nesta_aba, pessoas_sem_esta_aba)


def _avisos_da_juncao(ligacao: Ligacao, principal: TabelaDaAba, linhas_so_nesta_aba: list[int],
                      pessoas_sem_esta_aba: int) -> list[str]:
    """Os avisos de uma aba ligada: quem só estava nela e quem da principal ficou sem os dados dela."""
    avisos = []
    nome_do_identificador = principal.cabecalhos[ligacao.coluna_na_principal]
    if linhas_so_nesta_aba:
        numeros = []
        for numero in linhas_so_nesta_aba:
            numeros.append(str(numero))
        avisos.append(f"{len(linhas_so_nesta_aba)} pessoa(s) da aba {ligacao.tabela.nome} (linha(s) {', '.join(numeros)}) não "
                      f"estão na aba {principal.nome}: entraram só com os dados da aba {ligacao.tabela.nome}. "
                      f"Confira o {nome_do_identificador}.")
    if pessoas_sem_esta_aba:
        avisos.append(f"{pessoas_sem_esta_aba} pessoa(s) da aba {principal.nome} não estão na aba "
                      f"{ligacao.tabela.nome}: ficaram sem os dados dela.")
    return avisos


def _completar_a_leitura(leitura, linhas: list[list[str]], numeros_linha: list[int],
                         colunas_numericas: list[set[int]]) -> None:
    """Põe as linhas na leitura, com as contas e as recusas da leitura de sempre, e passa o guardrail."""
    if len(leitura.cabecalhos) > ingestao.MAXIMO_DE_COLUNAS:
        raise ingestao.ArquivoRecusado(f"O arquivo tem mais de {ingestao.MAXIMO_DE_COLUNAS} colunas: confira se é a "
                                       "lista de funcionários.")
    if len(linhas) > ingestao.MAXIMO_DE_LINHAS:
        raise ingestao.ArquivoRecusado(f"O arquivo tem mais de {ingestao.MAXIMO_DE_LINHAS} linhas: divida em arquivos "
                                       "menores.")
    leitura.linhas = linhas
    leitura.numeros_linha = numeros_linha
    # Soma, por coluna, as células que vieram como número no Excel (para o aviso dos zeros à esquerda)
    for colunas_da_linha in colunas_numericas:
        for numero_da_coluna in colunas_da_linha:
            leitura.celulas_numericas[numero_da_coluna] = leitura.celulas_numericas.get(numero_da_coluna, 0) + 1
    # O guardrail de injeção antes que qualquer IA veja o arquivo
    ingestao._aplicar_guardrail(leitura)
