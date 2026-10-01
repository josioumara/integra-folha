"""Teste de segurança, frente C: validação das entradas, APIs e integrações (arquivos, formulários, IA e Docker).

Para que serve: cada teste descreve o comportamento CORRETO de um controle de segurança. Quando o controle funciona,
o teste passa. Quando o teste de segurança achou uma falha, o teste continua descrevendo o comportamento correto, mas
leva a marca "xfail" (falha esperada) com o código do achado (ex.: "C-03"). Com strict=True, no dia em que a falha for
corrigida o pytest avisa ("XPASS"), e basta tirar a marca. A tabela dos achados fica em
docs/testes_de_seguranca.md (seção 5).

O que se testa, em ordem:
1. Arquivos enviados: extensão × conteúdo, tamanho, bomba de descompressão, linhas acima do limite, XML com entidade
   externa (XXE), macro, fórmula, nome do arquivo (../, caracteres de controle, nome gigante), arquivo vazio e
   codificações estranhas.
2. Exportação: proteção contra "CSV injection" no arquivo que a empresa baixa e no arquivo homologado.
3. Campos das rotas: JSON malformado, tipos errados, textos gigantes, NaN, números gigantes, datas e CNPJ/CPF
   inválidos, Unicode perigoso e mensagens de erro técnicas.
4. Integração com a IA: prazo (timeout), erro e resposta estragada do provedor, limite de chamadas, teto de gasto e
   limite de frequência nas rotas caras. Nenhuma chamada real: o provedor é sempre simulado.
5. Docker e Compose: segredos, teste de saúde e confiança nos cabeçalhos de proxy.

Regras de ambiente (conftest do projeto): banco SQLite temporário, MODE=mock, pastas de envio temporárias. Os
arquivos de ataque são montados na memória; nada é gravado no repositório.

Conceitos para leigo:
    - Bomba de descompressão ("zip bomb"): um arquivo pequeno que, ao ser aberto, vira um arquivo gigante. O .xlsx e o
      .docx são "zips" por dentro: 200 KB podem virar 200 MB, como uma esponja seca que incha na água.
    - XXE (entidade externa do XML): um truque no XML que pede ao leitor para "colar" ali o conteúdo de outro arquivo
      do servidor (ex.: um arquivo de senhas).
    - CSV injection: uma célula que começa com "=" vira fórmula quando o Excel abre o arquivo.
    - Timeout (prazo): quanto tempo o sistema espera a resposta de outro serviço antes de desistir.
"""
import csv
import io
import json
import tempfile
import unicodedata
import zipfile
from pathlib import Path

import pytest
import yaml
from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, auth, config, homologacao, ingestao, provedores_de_ia
from services.documentos import cpf_valido
from services.llm_client import LLMClient, RespostaLLM
# A IA real que não responde pausa, sem resposta simulada (ADR-145)
from services.llm_client import IAIndisponivel
from tests.test_leitura_de_word import ClienteQueNaoPodeSerChamado

# Pasta raiz do projeto (onde ficam o Dockerfile e o docker-compose.yml)
RAIZ = Path(__file__).resolve().parent.parent.parent
# Senha dos usuários deste arquivo (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-segc"
# Login do RH de teste (perfil EMPRESA, empresa EMP001) e do especialista de teste (perfil BANCO)
LOGIN_DA_EMPRESA = "segc.empresa"
LOGIN_DO_BANCO = "segc.banco"
# Um megabyte, em bytes
UM_MEGABYTE = 1024 * 1024
# Quanto a leitura de um arquivo pode descomprimir, no máximo: 5 vezes o limite de envio (5 MB → 25 MB).
# Uma planilha de verdade com 20.000 linhas fica bem abaixo disso
LIMITE_DE_DESCOMPRESSAO_EM_BYTES = 5 * config.LIMITE_UPLOAD_MB * UM_MEGABYTE
# Tamanho do texto "inflado" dentro da bomba de descompressão (60 MB viram menos de 100 KB comprimidos)
TAMANHO_DA_BOMBA_EM_BYTES = 60 * UM_MEGABYTE
# Espaço de nomes do XML da planilha Excel (sem ele, o leitor não reconhece a aba)
ESPACO_DA_PLANILHA = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
# Começos de célula que o Excel trata como fórmula (lista da OWASP para "CSV injection")
COMECOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")
# Caracteres Unicode que enganam a leitura: inversão da direção do texto (bidi) e caracteres invisíveis
CARACTERES_UNICODE_PERIGOSOS = ("\u202e", "\u202d", "\u2066", "\u2067", "\u200b", "\u200d", "\ufeff")


# ============================== Preparação: usuários, RAG falso e trava contra IA real ==============================

@pytest.fixture(scope="module", autouse=True)
def usuarios_de_teste():
    """Cadastra, uma vez para este arquivo, o RH da EMP001 e um especialista do banco num banco SÓ deste arquivo.

    Por que um banco próprio: estes testes criam empresas com nome e data inválidos (C-21, C-23). No banco comum da
    rodada, elas mudariam as contas de outros testes (ex.: um teste que conta as 6 empresas da demo).
    """
    # "Remendos" temporários, desfeitos no fim (o monkeypatch do pytest, na versão que serve a um arquivo inteiro)
    remendos = pytest.MonkeyPatch()
    # Um arquivo de banco numa pasta temporária, só deste arquivo de teste
    caminho_do_banco = Path(tempfile.mkdtemp()) / "seg_entradas.db"
    # Guarda a abertura original do banco, para chamá-la com o caminho deste arquivo
    conectar_original = auth.conectar

    def conectar_no_banco_do_teste(caminho_pedido=None):
        """Abre sempre o banco deste arquivo, qualquer que seja o caminho pedido."""
        return conectar_original(caminho_do_banco)

    # Toda a API (login, sessões e rotas) passa a usar o banco deste arquivo
    remendos.setattr(auth, "conectar", conectar_no_banco_do_teste)
    # Abre o banco deste arquivo
    conexao = auth.conectar()
    # O RH da empresa EMP001
    auth.cadastrar_usuario(conexao, LOGIN_DA_EMPRESA, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    # O especialista do banco
    auth.cadastrar_usuario(conexao, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)
    # Fecha a conexão
    conexao.close()
    # Os testes deste arquivo rodam aqui
    yield
    # No fim do arquivo, a API volta a abrir o banco comum da rodada
    remendos.undo()


def busca_falsa(texto, k=3, **outros_argumentos):
    """RAG de mentira: um trecho de regra com fonte, sem depender do índice nem do modelo de embeddings."""
    return [{"fonte": "Regras de validação › cpf", "campo": "cpf",
             "texto": "Regras de validação › cpf\nO CPF precisa ter 11 dígitos e dígito verificador válido."}]


def chamada_real_proibida(*argumentos, **argumentos_nomeados):
    """Trava de segurança: se algum teste chegasse ao provedor de verdade, falha na hora (e nada é gasto)."""
    raise AssertionError("chamada real ao provedor de IA: proibida nos testes de segurança")


@pytest.fixture(autouse=True)
def ambiente_sem_ia_real(monkeypatch, tmp_path):
    """Em todo teste: o RAG usa a busca falsa e uma pasta de índices temporária, e qualquer chamada real ao provedor
    falha na hora."""
    # O Interpretador e o Assistente consultam o RAG: aqui, a busca falsa
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    # Qualquer índice que um teste grave (ex.: o do catálogo, refeito a cada versão nova) vai para a pasta do teste,
    # nunca para storage/indices da aplicação
    monkeypatch.setattr("rag.busca.PASTA_INDICES", tmp_path / "indices")
    # A porta de saída para os provedores (OpenAI, Anthropic e Bedrock) fica trancada
    monkeypatch.setattr(provedores_de_ia, "chamar", chamada_real_proibida)


def navegador_logado(login: str) -> TestClient:
    """Um navegador de mentira já logado. Erros internos viram resposta 500 (não exceção), como no site de verdade.

    Recebe: login — LOGIN_DA_EMPRESA ou LOGIN_DO_BANCO. Devolve: o TestClient com o cookie da sessão.
    """
    # raise_server_exceptions=False: o teste enxerga o "500 Internal Server Error" que a pessoa veria
    navegador = TestClient(aplicacao, raise_server_exceptions=False)
    # Entra com o usuário de teste
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    # O login precisa ter dado certo para o teste seguir
    assert resposta.status_code == 200, resposta.text
    return navegador


@pytest.fixture
def empresa() -> TestClient:
    """O navegador do RH da EMP001, já logado."""
    return navegador_logado(LOGIN_DA_EMPRESA)


@pytest.fixture
def banco() -> TestClient:
    """O navegador do especialista do banco, já logado."""
    return navegador_logado(LOGIN_DO_BANCO)


# ============================== Ajudantes: montar os arquivos de ataque na memória ==============================

# Contador global dos CPFs fictícios já usados (cada envio precisa de gente nova, senão é recusado como repetido)
CONTADOR_DE_CPFS = {"proximo": 100_000_000}


def digito_verificador_do_cpf(digitos: str) -> str:
    """O próximo dígito verificador do CPF para os dígitos dados (a conta oficial do módulo 11).

    Recebe: 9 ou 10 dígitos. Devolve: o dígito seguinte, em texto. Ex.: "529982247" → "2".
    """
    # O peso começa em (quantidade de dígitos + 1) e diminui de 1 em 1
    peso = len(digitos) + 1
    soma = 0
    for digito in digitos:
        # Cada dígito vezes o seu peso
        soma = soma + int(digito) * peso
        peso = peso - 1
    # O resto da divisão por 11 decide o dígito
    resto = soma % 11
    # Resto menor que 2 vira 0; senão, 11 menos o resto
    if resto < 2:
        return "0"
    return str(11 - resto)


def novo_cpf_ficticio() -> str:
    """Um CPF fictício novo, válido só na conta do dígito verificador. Ex.: "10000000019"."""
    # Os 9 primeiros dígitos: um número que nunca se repete neste arquivo
    base = str(CONTADOR_DE_CPFS["proximo"])
    CONTADOR_DE_CPFS["proximo"] = CONTADOR_DE_CPFS["proximo"] + 1
    # Os dois dígitos verificadores, um depois do outro
    primeiro_digito = digito_verificador_do_cpf(base)
    segundo_digito = digito_verificador_do_cpf(base + primeiro_digito)
    return base + primeiro_digito + segundo_digito


# Contador global dos CNPJs fictícios já usados (cada empresa nova precisa de um CNPJ que ninguém usou)
CONTADOR_DE_CNPJS = {"proximo": 87_650_000}
# Os pesos da conta oficial dos dois dígitos verificadores do CNPJ
PESOS_DO_PRIMEIRO_DIGITO_DO_CNPJ = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
PESOS_DO_SEGUNDO_DIGITO_DO_CNPJ = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def digito_verificador_do_cnpj(digitos: str, pesos: tuple) -> str:
    """Um dígito verificador do CNPJ (a conta do módulo 11 com os pesos oficiais). Devolve o dígito, em texto."""
    soma = 0
    # Cada dígito vezes o peso da mesma posição
    for posicao, digito in enumerate(digitos):
        soma = soma + int(digito) * pesos[posicao]
    # Resto menor que 2 vira 0; senão, 11 menos o resto
    resto = soma % 11
    if resto < 2:
        return "0"
    return str(11 - resto)


def novo_cnpj_ficticio() -> str:
    """Um CNPJ fictício novo (matriz "0001"), válido só na conta dos dígitos. Ex.: "87650000000191"."""
    # A raiz (8 dígitos) nunca se repete neste arquivo; a matriz é sempre "0001"
    base = str(CONTADOR_DE_CNPJS["proximo"]) + "0001"
    CONTADOR_DE_CNPJS["proximo"] = CONTADOR_DE_CNPJS["proximo"] + 1
    # Os dois dígitos verificadores, um depois do outro
    primeiro_digito = digito_verificador_do_cnpj(base, PESOS_DO_PRIMEIRO_DIGITO_DO_CNPJ)
    segundo_digito = digito_verificador_do_cnpj(base + primeiro_digito, PESOS_DO_SEGUNDO_DIGITO_DO_CNPJ)
    return base + primeiro_digito + segundo_digito


def csv_com_uma_pessoa_nova() -> bytes:
    """Um CSV pequeno e válido com uma pessoa que ainda não existe. Ex.: b"Nome;CPF\\nPessoa Teste;100000000..."."""
    # Nome e CPF: o suficiente para o envio ser aceito
    return f"Nome;CPF\nPessoa Teste;{novo_cpf_ficticio()}\n".encode("utf-8")


def bytes_do_zip_trocando_uma_parte(conteudo_do_zip: bytes, nome_da_parte: str, conteudo_novo: bytes) -> bytes:
    """Copia um arquivo zip (.xlsx, .docx, .ods) trocando o conteúdo de uma das partes de dentro dele.

    Recebe: os bytes do zip, o nome da parte (ex.: "xl/worksheets/sheet1.xml") e o conteúdo novo dela.
    Devolve: os bytes do zip novo, comprimido no nível máximo.
    """
    # O zip original, aberto na memória
    zip_original = zipfile.ZipFile(io.BytesIO(conteudo_do_zip))
    # O zip novo, também na memória
    saida = io.BytesIO()
    zip_novo = zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED, compresslevel=9)
    # Copia cada parte; a parte escolhida recebe o conteúdo novo
    for parte in zip_original.infolist():
        conteudo_da_parte = zip_original.read(parte.filename)
        if parte.filename == nome_da_parte:
            conteudo_da_parte = conteudo_novo
        zip_novo.writestr(parte.filename, conteudo_da_parte)
    # Fecha o zip novo (grava o índice do zip no fim)
    zip_novo.close()
    return saida.getvalue()


def planilha_simples() -> bytes:
    """Uma planilha Excel pequena e válida: cabeçalho Nome e CPF e uma pessoa."""
    # Um livro novo com uma aba
    livro = Workbook()
    aba = livro.active
    # O cabeçalho e uma pessoa
    aba["A1"] = "Nome"
    aba["B1"] = "CPF"
    aba["A2"] = "Ana Almeida"
    aba["B2"] = "52998224725"
    # Grava na memória e devolve os bytes
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def planilha_com_celulas(celulas: dict) -> bytes:
    """Uma planilha Excel com as células informadas (ex.: {"A1": "Nome", "B2": "=HYPERLINK(...)"})."""
    # Um livro novo com uma aba
    livro = Workbook()
    aba = livro.active
    # Cada célula recebe o seu valor (texto que começa com "=" vira fórmula no openpyxl)
    for posicao, valor in celulas.items():
        aba[posicao] = valor
    # Grava na memória e devolve os bytes
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def documento_word_com_tabela(texto_da_celula: str) -> bytes:
    """Um Word (.docx) com uma tabela de funcionários: cabeçalho Nome e CPF e uma pessoa."""
    # Documento novo com uma tabela de 2 linhas e 2 colunas
    documento = Document()
    tabela = documento.add_table(rows=2, cols=2)
    # O cabeçalho
    tabela.cell(0, 0).text = "Nome"
    tabela.cell(0, 1).text = "CPF"
    # A pessoa (o nome é o texto pedido, para o teste achar a célula depois)
    tabela.cell(1, 0).text = texto_da_celula
    tabela.cell(1, 1).text = "52998224725"
    # Grava na memória e devolve os bytes
    saida = io.BytesIO()
    documento.save(saida)
    return saida.getvalue()


def planilha_libreoffice_simples() -> bytes:
    """Uma planilha do LibreOffice (.ods) pequena: cabeçalho Nome e CPF e uma pessoa (marcada como "MARCA")."""
    # O pandas grava .ods com a biblioteca odf
    import pandas
    tabela = pandas.DataFrame({"Nome": ["MARCA"], "CPF": ["52998224725"]})
    saida = io.BytesIO()
    tabela.to_excel(saida, engine="odf", index=False)
    return saida.getvalue()


def bomba_de_descompressao(formato: str) -> bytes:
    """Um arquivo pequeno (menos de 100 KB) que, aberto, vira 60 MB de texto numa célula ou num parágrafo.

    Recebe: formato — "xlsx", "docx" ou "ods". Devolve: os bytes do arquivo com a extensão certa por dentro.
    Por que 60 MB: é o dobro do que a leitura pode descomprimir (LIMITE_DE_DESCOMPRESSAO_EM_BYTES) e ainda é rápido de
    montar. Um atacante faria o mesmo com 5 GB dentro de um arquivo de 5 MB.
    """
    # O texto que "incha": a mesma letra repetida comprime quase a nada
    texto_inflado = b"A" * TAMANHO_DA_BOMBA_EM_BYTES
    # Planilha Excel: a aba com uma célula só, de 60 MB
    if formato == "xlsx":
        aba = (b'<?xml version="1.0"?><worksheet xmlns="' + ESPACO_DA_PLANILHA.encode() + b'"><sheetData>'
               b'<row r="1"><c r="A1" t="inlineStr"><is><t>' + texto_inflado + b'</t></is></c></row>'
               b'</sheetData></worksheet>')
        return bytes_do_zip_trocando_uma_parte(planilha_simples(), "xl/worksheets/sheet1.xml", aba)
    # Word: o corpo do documento com um parágrafo só, de 60 MB
    if formato == "docx":
        corpo = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                 b'<w:p><w:r><w:t>' + texto_inflado + b'</w:t></w:r></w:p></w:body></w:document>')
        return bytes_do_zip_trocando_uma_parte(documento_word_com_tabela("Ana"), "word/document.xml", corpo)
    # LibreOffice: a célula "MARCA" do conteúdo vira os 60 MB
    original = planilha_libreoffice_simples()
    conteudo = zipfile.ZipFile(io.BytesIO(original)).read("content.xml")
    return bytes_do_zip_trocando_uma_parte(original, "content.xml", conteudo.replace(b"MARCA", texto_inflado))


class DescompressaoAlemDoLimite(Exception):
    """A leitura já tinha descomprimido mais que o limite: o teste interrompe para não gastar memória à toa."""


def contar_a_descompressao(monkeypatch) -> dict:
    """Passa a contar quantos bytes a leitura descomprime de qualquer zip; passou do limite, interrompe.

    Recebe: monkeypatch (a troca temporária do pytest, desfeita no fim do teste).
    Devolve: {"bytes": quanto já foi descomprimido}. Como: embrulha a leitura das partes do zip (ZipExtFile.read e
    read1), que é por onde o openpyxl, o python-docx e o odfpy leem o conteúdo das planilhas e documentos.
    """
    # O contador, que o teste consulta depois
    contador = {"bytes": 0}
    # As leituras originais, guardadas antes da troca
    leitura_original = zipfile.ZipExtFile.read
    leitura_parcial_original = zipfile.ZipExtFile.read1

    def somar_e_conferir(dados: bytes) -> bytes:
        """Soma o que acabou de ser descomprimido; passou do limite, interrompe a leitura."""
        contador["bytes"] = contador["bytes"] + len(dados)
        if contador["bytes"] > LIMITE_DE_DESCOMPRESSAO_EM_BYTES:
            raise DescompressaoAlemDoLimite()
        return dados

    def leitura_contada(self, quantidade=-1):
        """A leitura de sempre, com a soma dos bytes descomprimidos."""
        return somar_e_conferir(leitura_original(self, quantidade))

    def leitura_parcial_contada(self, quantidade=-1):
        """A leitura parcial de sempre, com a soma dos bytes descomprimidos."""
        return somar_e_conferir(leitura_parcial_original(self, quantidade))

    # A troca vale só até o fim do teste
    monkeypatch.setattr(zipfile.ZipExtFile, "read", leitura_contada)
    monkeypatch.setattr(zipfile.ZipExtFile, "read1", leitura_parcial_contada)
    return contador


def ler_sem_ia(conteudo: bytes, nome_do_arquivo: str):
    """Lê o arquivo como o envio faz, com um cliente de IA que falha se for chamado. Devolve a Leitura."""
    return ingestao.ler_arquivo(conteudo, nome_do_arquivo, cliente=ClienteQueNaoPodeSerChamado(modo="mock"))


def arquivo_secreto_do_servidor() -> tuple[str, str]:
    """Um arquivo "secreto" numa pasta temporária, para ver se um XXE consegue colar o conteúdo dele na leitura.

    Devolve: (endereço file:/// do arquivo, o texto secreto que não pode aparecer em lugar nenhum).
    """
    # O texto que, se aparecer na leitura, prova o vazamento
    texto_secreto = "SEGREDO_DO_SERVIDOR_XXE"
    # Grava o arquivo numa pasta temporária (fora do repositório)
    caminho = Path(tempfile.mkdtemp()) / "segredo.txt"
    caminho.write_text(texto_secreto, encoding="utf-8")
    # O endereço no formato que o XML usa ("file:///C:/...")
    endereco = "file:///" + str(caminho).replace("\\", "/")
    return endereco, texto_secreto


def arquivos_com_entidade_externa() -> list[tuple[str, bytes, str]]:
    """Os 4 formatos com XML por dentro, cada um pedindo para colar o arquivo secreto no lugar de um nome.

    Devolve: lista de (nome do arquivo, bytes, texto secreto).
    """
    endereco, texto_secreto = arquivo_secreto_do_servidor()
    # A declaração da entidade externa: "&x;" deve virar o conteúdo do arquivo secreto (é o ataque)
    declaracao = f'<!DOCTYPE raiz [<!ENTITY x SYSTEM "{endereco}">]>'.encode()
    arquivos = []
    # Planilha Excel: a aba com a entidade numa célula
    aba = (b'<?xml version="1.0"?>' + declaracao + b'<worksheet xmlns="' + ESPACO_DA_PLANILHA.encode() + b'">'
           b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Nome</t></is></c></row>'
           b'<row r="2"><c r="A2" t="inlineStr"><is><t>&x;</t></is></c></row></sheetData></worksheet>')
    arquivos.append(("xxe.xlsx", bytes_do_zip_trocando_uma_parte(planilha_simples(), "xl/worksheets/sheet1.xml", aba),
                     texto_secreto))
    # Word: a entidade no lugar do nome da pessoa na tabela
    word = documento_word_com_tabela("MARCA")
    corpo = zipfile.ZipFile(io.BytesIO(word)).read("word/document.xml")
    corpo = corpo.replace(b"?>", b"?>" + declaracao, 1).replace(b"MARCA", b"&x;")
    arquivos.append(("xxe.docx", bytes_do_zip_trocando_uma_parte(word, "word/document.xml", corpo), texto_secreto))
    # LibreOffice: a entidade no lugar do nome da pessoa
    ods = planilha_libreoffice_simples()
    conteudo = zipfile.ZipFile(io.BytesIO(ods)).read("content.xml")
    conteudo = conteudo.replace(b"?>", b"?>" + declaracao, 1).replace(b"MARCA", b"&x;")
    arquivos.append(("xxe.ods", bytes_do_zip_trocando_uma_parte(ods, "content.xml", conteudo), texto_secreto))
    # O ".xls" que é uma página HTML (muitos sistemas exportam assim)
    pagina = (declaracao + b"<html><body><table><tr><td>Nome</td><td>CPF</td></tr>"
              b"<tr><td>&x;</td><td>52998224725</td></tr></table></body></html>")
    arquivos.append(("xxe.xls", pagina, texto_secreto))
    return arquivos


def processamento_do_banco(processamento_id: str) -> tuple[str, str]:
    """O nome do arquivo e o caminho do original gravados para um envio. Devolve (nome_arquivo, caminho)."""
    # Abre o banco temporário e procura o envio
    conexao = auth.conectar()
    linha = conexao.execute("SELECT nome_arquivo, caminho_original FROM processamentos WHERE processamento_id = ?",
                            (processamento_id,)).fetchone()
    conexao.close()
    return linha[0], linha[1]


# ============================== 1. Arquivos enviados ==============================

@pytest.mark.parametrize("nome_do_arquivo, conteudo", [
    ("folha.xlsx", b"MZ\x90\x00\x03" + b"\x00" * 100),          # programa do Windows (.exe) com nome de planilha
    ("folha.csv", b"MZ\x90\x00\x03" + b"\x00" * 100),           # programa do Windows com nome de CSV
    ("folha.xlsx", b"%PDF-1.7\n1 0 obj\n"),                      # PDF com nome de planilha
    ("folha.csv", b"%PDF-1.7\n1 0 obj\n"),                       # PDF com nome de CSV
    ("folha.docx", b"%PDF-1.7\n1 0 obj\n"),                      # PDF com nome de Word
])
def test_c01_conteudo_que_nao_confere_com_a_extensao_e_recusado_na_api(empresa, nome_do_arquivo, conteudo):
    """C-01: um .exe ou PDF renomeado para .xlsx/.csv/.docx é recusado pelos primeiros bytes, com 400 e mensagem clara."""
    # Envia pela mesma rota da tela "Cadastrar funcionários"
    resposta = empresa.post("/api/empresa/cadastro/enviar", files={"arquivo": (nome_do_arquivo, conteudo)})
    # Recusa limpa (400), com a explicação de que o conteúdo não confere
    assert resposta.status_code == 400
    assert "extensão trocada" in resposta.json()["detail"]


def test_c02_arquivo_acima_do_limite_e_recusado_na_porta_e_ao_ler(empresa, monkeypatch):
    """C-02: com limite de 1 MB, 2 MB são barrados na porta (413) e 1 MB + 10 bytes são barrados ao ler (400)."""
    # Limite de 1 MB só neste teste (a conta do limite é feita a cada pedido)
    monkeypatch.setattr(config, "LIMITE_UPLOAD_MB", 1)
    # 2 MB: acima do limite mais a folga do formulário, recusado antes de receber o conteúdo
    resposta_grande = empresa.post("/api/empresa/cadastro/enviar",
                                   files={"arquivo": ("grande.csv", b"a;b\n" + b"x" * (2 * UM_MEGABYTE))})
    assert resposta_grande.status_code == 413
    assert resposta_grande.json()["detail"] == "Arquivo maior que o limite de 1 MB."
    # 1 MB + 10 bytes: cabe na folga do formulário, mas a rota lê só até o limite e recusa
    resposta_quase = empresa.post("/api/empresa/cadastro/enviar",
                                  files={"arquivo": ("quase.csv", b"x" * (UM_MEGABYTE + 10))})
    assert resposta_quase.status_code == 400
    assert resposta_quase.json()["detail"] == "Arquivo maior que o limite de 1 MB."


@pytest.mark.parametrize("formato", ["xlsx", "docx", "ods"])
def test_c03_bomba_de_descompressao_e_recusada_sem_inflar_na_memoria(monkeypatch, formato):
    """C-03: um arquivo pequeno que infla para 60 MB é recusado sem a leitura descomprimir mais que 25 MB.

    Comportamento correto: conferir o tamanho descomprimido das partes do zip (ou ler aos poucos, com teto) antes de
    abrir a planilha ou o documento. Achado: a leitura descomprime tudo (C-03 em docs/testes_de_seguranca.md:
    199 KB → 47 s e 601 MB).
    """
    # Monta a bomba ANTES de ligar o contador (a montagem também descomprime)
    bomba = bomba_de_descompressao(formato)
    # O arquivo enviado é pequeno: passa no limite de 5 MB
    assert len(bomba) < UM_MEGABYTE
    # Daqui em diante, cada byte descomprimido é contado
    contador = contar_a_descompressao(monkeypatch)
    # A leitura tem de recusar o arquivo; se a leitura passou do limite, o contador interrompe
    recusado = False
    try:
        ler_sem_ia(bomba, "bomba." + formato)
    except ingestao.ArquivoRecusado:
        recusado = True
    except DescompressaoAlemDoLimite:
        recusado = False
    # Correto: recusado sem descomprimir mais que o limite
    assert contador["bytes"] <= LIMITE_DE_DESCOMPRESSAO_EM_BYTES
    assert recusado


class LeituraAlemDoLimite(Exception):
    """A leitura do CSV já tinha passado muito do limite de linhas: o teste interrompe."""


def test_c04_arquivo_com_linhas_demais_e_recusado_sem_ler_o_arquivo_inteiro(monkeypatch):
    """C-04: um CSV com 30.000 linhas (limite de 20.000) é recusado sem a leitura passar muito do limite.

    Comportamento correto: parar de ler ao passar do limite de linhas (e de colunas), e não montar o arquivo inteiro
    na memória para só depois contar. O teste conta as linhas que o leitor de CSV entrega.
    """
    # Até onde a leitura pode ir: o limite, as linhas de procura do cabeçalho e uma folga de 1.000
    linhas_permitidas = ingestao.MAXIMO_DE_LINHAS + ingestao.LINHAS_PARA_ACHAR_CABECALHO + 1000
    # Um CSV com 30.000 pessoas (cerca de 300 KB)
    conteudo = b"Nome;CPF\n" + b"Pessoa;1\n" * 30_000
    # O contador das linhas entregues pelo leitor de CSV
    contador = {"linhas": 0}
    # O leitor de CSV original, guardado antes da troca
    leitor_original = csv.reader

    class LeitorQueConta:
        """O leitor de CSV de sempre, contando as linhas entregues (e interrompendo depois do permitido)."""

        def __init__(self, leitor):
            """Guarda o leitor de verdade."""
            self.leitor = leitor

        def __iter__(self):
            """O próprio objeto percorre as linhas."""
            return self

        def __next__(self):
            """A próxima linha do arquivo; passou do permitido, interrompe."""
            registro = next(self.leitor)
            contador["linhas"] = contador["linhas"] + 1
            if contador["linhas"] > linhas_permitidas:
                raise LeituraAlemDoLimite()
            return registro

        @property
        def line_num(self):
            """Em que linha do arquivo o leitor está (a ingestão usa para apontar aspas sem fechar)."""
            return self.leitor.line_num

    def fabrica_de_leitores(*argumentos, **argumentos_nomeados):
        """Cria o leitor de sempre, embrulhado no leitor que conta."""
        return LeitorQueConta(leitor_original(*argumentos, **argumentos_nomeados))

    # A troca vale só neste teste
    monkeypatch.setattr(csv, "reader", fabrica_de_leitores)
    # A leitura tem de recusar o arquivo
    recusado = False
    try:
        ler_sem_ia(conteudo, "muitas_linhas.csv")
    except ingestao.ArquivoRecusado:
        recusado = True
    except LeituraAlemDoLimite:
        recusado = False
    # Correto: recusado sem ler muito além do limite
    assert contador["linhas"] <= linhas_permitidas
    assert recusado


@pytest.mark.parametrize("posicao", [0, 1, 2, 3])
def test_c05_xml_com_entidade_externa_nunca_cola_arquivo_do_servidor(posicao):
    """C-05: XXE em .xlsx, .docx, .ods e .xls (HTML): o conteúdo do arquivo secreto nunca aparece na leitura.

    Pode ser recusado (planilha "corrompida") ou lido sem a entidade; nunca com o segredo, e nunca com erro 500.
    """
    # O arquivo de ataque desta posição (um por formato)
    nome_do_arquivo, conteudo, texto_secreto = arquivos_com_entidade_externa()[posicao]
    # O que a leitura devolveu (ou a recusa)
    resultado = ""
    try:
        leitura = ler_sem_ia(conteudo, nome_do_arquivo)
        resultado = json.dumps({"cabecalhos": leitura.cabecalhos, "linhas": leitura.linhas}, ensure_ascii=False)
    except ingestao.ArquivoRecusado as recusa:
        resultado = str(recusa)
    # O segredo não pode ter sido colado em lugar nenhum
    assert texto_secreto not in resultado


def test_c06_macro_e_recusada_e_planilha_com_macro_escondida_nao_roda_nada():
    """C-06: .xlsm é recusado pela extensão; um .xlsx com vbaProject.bin dentro é lido só como valores."""
    # .xlsm (planilha com macro): formato fora da lista
    with pytest.raises(ingestao.ArquivoRecusado, match="não aceito"):
        ler_sem_ia(b"PK\x03\x04conteudo", "folha.xlsm")
    # Um .xlsx com o arquivo de macro escondido dentro do zip
    planilha = planilha_simples()
    saida = io.BytesIO()
    zip_novo = zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED)
    zip_original = zipfile.ZipFile(io.BytesIO(planilha))
    for parte in zip_original.infolist():
        zip_novo.writestr(parte.filename, zip_original.read(parte.filename))
    # A "macro" (conteúdo qualquer: o que importa é que nada a execute)
    zip_novo.writestr("xl/vbaProject.bin", b"\xd0\xcf\x11\xe0 macro de mentira")
    zip_novo.close()
    # A leitura devolve só os valores das células
    leitura = ler_sem_ia(saida.getvalue(), "com_macro.xlsx")
    assert leitura.linhas == [["Ana Almeida", "52998224725"]]


@pytest.mark.parametrize("formula", ["=cmd|' /C calc'!A0", "=HYPERLINK(\"http://exemplo.invalido\",\"clique\")",
                                     "=1+1"])
def test_c07_planilha_com_formula_e_recusada_dizendo_a_celula(formula):
    """C-07: fórmula (inclusive o DDE "=cmd|...") numa planilha é recusada, apontando a célula."""
    # A fórmula na célula B2
    planilha = planilha_com_celulas({"A1": "Nome", "B1": "Salário", "A2": "Ana", "B2": formula})
    # Recusa, dizendo onde está a fórmula
    with pytest.raises(ingestao.ArquivoRecusado, match="fórmulas.*B2"):
        ler_sem_ia(planilha, "formula.xlsx")


@pytest.mark.parametrize("nome_do_arquivo", ["../../../fora_da_pasta.csv", "..\\..\\fora_da_pasta.csv",
                                             "C:\\Windows\\fora_da_pasta.csv", "/etc/fora_da_pasta.csv"])
def test_c08_nome_do_arquivo_nunca_escolhe_onde_o_original_e_gravado(empresa, nome_do_arquivo):
    """C-08: com "../" ou caminho absoluto no nome, o original vai para a pasta de envios como <id>.<extensão>."""
    # Envia um CSV válido com o nome de ataque
    resposta = empresa.post("/api/empresa/cadastro/enviar",
                            files={"arquivo": (nome_do_arquivo, csv_com_uma_pessoa_nova())})
    assert resposta.status_code == 200, resposta.text
    # Onde o original foi gravado
    processamento_id = resposta.json()["processamento_id"]
    _, caminho_gravado = processamento_do_banco(processamento_id)
    caminho = Path(caminho_gravado)
    # Dentro da pasta de envios, com o identificador do envio no nome (nunca o nome enviado)
    assert caminho.parent.resolve() == config.PASTA_UPLOADS.resolve()
    assert caminho.name == processamento_id + ".csv"
    # E nada com o nome de ataque foi criado acima da pasta de envios
    assert not (config.PASTA_UPLOADS.parent / "fora_da_pasta.csv").exists()
    assert not (config.PASTA_UPLOADS.parent.parent / "fora_da_pasta.csv").exists()


def texto_tem_caractere_de_controle(texto: str) -> bool:
    """True se o texto tem caractere de controle (NUL, campainha...) ou de formatação invisível (bidi, largura zero).

    Ex.: "folha.csv" → False; "fo\\x00lha.csv" → True; "folha\\u202e.csv" → True.
    """
    for caractere in texto:
        # "Cc" = controle (ex.: \\x00, \\x07); "Cf" = formatação invisível (ex.: \\u202e, \\u200b)
        if unicodedata.category(caractere) in ("Cc", "Cf"):
            return True
    return False


def test_c09_nome_do_arquivo_e_saneado_antes_de_ser_gravado(empresa):
    """C-09: o nome guardado do envio não tem caracteres de controle nem invisíveis e tem no máximo 255 caracteres.

    Comportamento correto: tirar NUL, controles e caracteres bidi/invisíveis, e cortar (ou recusar) nomes gigantes.
    O NUL, em especial, é recusado pelo PostgreSQL (o banco da aplicação), o que viraria erro no envio.
    """
    # Um nome com NUL, campainha (\x07), inversão de direção (\u202e) e 3.000 letras
    nome_de_ataque = "fo\x00l\x07ha\u202e" + "a" * 3000 + ".csv"
    resposta = empresa.post("/api/empresa/cadastro/enviar",
                            files={"arquivo": (nome_de_ataque, csv_com_uma_pessoa_nova())})
    # O envio em si pode ser aceito (o conteúdo é válido) ou recusado com 400 por causa do nome; nunca 500
    assert resposta.status_code in (200, 400)
    # Aceito: o nome guardado precisa estar limpo e curto
    if resposta.status_code == 200:
        nome_guardado, _ = processamento_do_banco(resposta.json()["processamento_id"])
        assert not texto_tem_caractere_de_controle(nome_guardado)
        assert len(nome_guardado) <= 255


def test_c10_arquivo_vazio_e_sem_nome_sao_recusados_sem_erro_interno(empresa):
    """C-10: arquivo vazio recebe 400 ("O arquivo está vazio."); envio sem arquivo recebe 422, nunca 500."""
    # Arquivo de 0 byte
    resposta_vazio = empresa.post("/api/empresa/cadastro/enviar", files={"arquivo": ("vazio.csv", b"")})
    assert resposta_vazio.status_code == 400
    assert resposta_vazio.json()["detail"] == "O arquivo está vazio."
    # Formulário sem o arquivo
    resposta_sem_arquivo = empresa.post("/api/empresa/cadastro/enviar", data={"pedido_de_progresso": ""})
    assert resposta_sem_arquivo.status_code == 422


@pytest.mark.parametrize("conteudo", [
    "Nome;CPF\nAna;52998224725\n".encode("utf-16-le"),         # UTF-16 sem a marca BOM (cheio de bytes nulos)
    "Nome;CPF\nAna;52998224725\n".encode("utf-32"),            # UTF-32 (começa como a marca do UTF-16)
    "Nome;CPF\nAnã;52998224725\n".encode("utf-7"),             # UTF-7 (codificação antiga e rara)
    bytes(range(1, 256)) * 10,                                 # bytes sem sentido
    b"\xff\xfe" + b"N\x00o\x00m",                              # UTF-16 cortado no meio de uma letra
    "Nome;CPF\n\ufeffAna\u202e;52998224725\n".encode("utf-8"),  # UTF-8 com marca BOM no meio e bidi
])
def test_c11_codificacoes_estranhas_viram_leitura_ou_recusa_limpa_nunca_500(empresa, conteudo):
    """C-11: codificações raras ou quebradas: a API responde 200 (lido) ou 400 (recusado), nunca erro interno."""
    # Envia pela rota da tela
    resposta = empresa.post("/api/empresa/cadastro/enviar", files={"arquivo": ("codificacao.csv", conteudo)})
    # Lido ou recusado com explicação; 500 seria a API quebrando
    assert resposta.status_code in (200, 400), resposta.text


def test_c12_limites_de_colunas_e_linhas_continuam_valendo():
    """C-12: mais de 200 colunas ou mais de 20.000 linhas: recusa com a explicação (o limite existe e funciona)."""
    # 201 colunas
    cabecalho = []
    valores = []
    for numero in range(ingestao.MAXIMO_DE_COLUNAS + 1):
        cabecalho.append(f"Coluna{numero}")
        valores.append("x")
    conteudo_largo = (";".join(cabecalho) + "\n" + ";".join(valores) + "\n").encode()
    with pytest.raises(ingestao.ArquivoRecusado, match="colunas"):
        ler_sem_ia(conteudo_largo, "largo.csv")
    # 20.016 pessoas (acima do limite, contando as linhas de procura do cabeçalho)
    conteudo_comprido = b"Nome;CPF\n" + b"Pessoa;1\n" * (ingestao.MAXIMO_DE_LINHAS + 1)
    with pytest.raises(ingestao.ArquivoRecusado, match="divida"):
        ler_sem_ia(conteudo_comprido, "comprido.csv")


# ============================== 2. Exportação: "CSV injection" ==============================

# Valores de ataque, um para cada começo perigoso, e o que o Excel faria com eles
VALORES_DE_FORMULA = ["=HYPERLINK(\"http://exemplo.invalido\",\"clique\")", "+cmd|' /C calc'!A0",
                      "-2+3+cmd|' /C calc'!A0", "@SUM(1+1)*cmd|' /C calc'!A0", "\t=1+1", "\r=1+1"]


def test_c13_download_da_empresa_e_arquivo_homologado_saem_sem_formula_executavel(empresa, monkeypatch):
    """C-13: no CSV que a empresa baixa e no arquivo homologado, toda célula com começo de fórmula ganha apóstrofo.

    Os começos da lista da OWASP: = + - @ tabulação e retorno de carro. Números negativos continuam números.
    """
    # Uma pessoa cadastrada "de mentira" com um valor de ataque em cada campo de texto do download
    pessoa = {"nome_completo": VALORES_DE_FORMULA[0], "cpf": "529.982.247-25", "matricula": VALORES_DE_FORMULA[1],
              "cargo": VALORES_DE_FORMULA[2], "nome_unidade": VALORES_DE_FORMULA[3], "data_admissao": "2026-01-10",
              "valor_renda": "-10.00", "incluido_em": "2026-09-01T10:00:00", "incluido_por": VALORES_DE_FORMULA[4],
              "conta_aberta_em": VALORES_DE_FORMULA[5], "codigo_banco": "033", "agencia": "0001", "conta": ""}

    def registros_de_mentira(conexao, empresa_id):
        """No lugar das pessoas cadastradas da empresa: só a pessoa de ataque, com o identificador "E1.1"."""
        return {"E1.1": pessoa}

    # O download usa as pessoas de mentira (a rota, o CSV e a neutralização são os de verdade)
    monkeypatch.setattr(acompanhamento, "_registros_completos_da_empresa", registros_de_mentira)
    resposta = empresa.post("/api/empresa/funcionarios/baixar", json={"identificadores": ["E1.1"]})
    assert resposta.status_code == 200
    # Lê o CSV como o Excel lê (separador ";", sem a marca BOM do começo)
    linhas = list(csv.reader(io.StringIO(resposta.content.decode("utf-8").lstrip("\ufeff")), delimiter=";"))
    celulas_da_pessoa = linhas[1]
    # Nenhuma célula pode começar com um começo de fórmula (a não ser o número negativo "-10.00")
    for celula in celulas_da_pessoa:
        if celula == "-10.00":
            continue
        assert not celula.startswith(COMECOS_DE_FORMULA), celula
    # O arquivo homologado (layout do banco) segue a mesma regra
    registro = {"nome_completo": VALORES_DE_FORMULA[0], "cargo": VALORES_DE_FORMULA[2], "valor_renda": "-10.00"}
    arquivo_final = homologacao.arquivo_final([registro], ["nome_completo", "cargo", "valor_renda"]).decode("utf-8")
    linhas_do_final = list(csv.reader(io.StringIO(arquivo_final), delimiter=";"))
    assert linhas_do_final[1][0].startswith("'=")
    assert linhas_do_final[1][1].startswith("'-")
    assert linhas_do_final[1][2] == "-10.00"


# ============================== 3. Campos e JSON das rotas ==============================

# A rota cara do banco que chama a IA (o Endomarketing; a do Consultor saiu, ADR-144) e um pedido de material válido
ROTA_DO_MATERIAL = "/api/banco/empresas/EMP001/endomarketing/gerar"
PEDIDO_DE_MATERIAL = {"tipo": "faq", "beneficios": ["Conta salário"]}


def test_c14_json_malformado_tipos_errados_e_formato_errado_recebem_4xx(banco):
    """C-14: JSON quebrado, tipo errado, lista no lugar do objeto, formulário no lugar do JSON e JSON muito
    profundo: sempre 4xx (422 ou 400), nunca erro interno."""
    # O cabeçalho de JSON, para mandar o texto cru
    cabecalho_json = {"content-type": "application/json"}
    # A rota do Simulador de Rentabilidade, que recebe um objeto JSON (a do Consultor saiu, ADR-144)
    rota_do_ganho = "/api/banco/planejamento/ganho"
    # JSON cortado no meio
    assert banco.post(rota_do_ganho, content=b'{"filtros": {', headers=cabecalho_json).status_code == 422
    # Tipo errado: texto onde a rota espera verdadeiro/falso
    assert banco.post("/api/banco/envios/x/avaliar", json={"aprovar": "talvez"}).status_code == 422
    # Tipo errado: texto onde a rota espera o objeto das premissas
    assert banco.post(rota_do_ganho, json={"premissas": "abc"}).status_code == 422
    # Lista no lugar do objeto
    assert banco.post(rota_do_ganho, json=[1, 2]).status_code == 422
    # Formulário no lugar do JSON
    resposta_formulario = banco.post(rota_do_ganho, content=b"clientes_da_empresa=35",
                                     headers={"content-type": "application/x-www-form-urlencoded"})
    assert resposta_formulario.status_code == 422
    # JSON com 100 mil colchetes aninhados (derrubaria um leitor recursivo)
    profundo = b'{"filtros": {}, "x": ' + b"[" * 100_000 + b"]" * 100_000 + b"}"
    assert banco.post(rota_do_ganho, content=profundo, headers=cabecalho_json).status_code in (400, 422)


def test_c15_campos_com_teto_recusam_texto_acima_do_limite(empresa, banco):
    """C-15: chat (4.000), destaque do material do Endomarketing (500) e login (200) recusam o texto maior com 422;
    senha de 1 MB é só uma senha errada (401), nunca erro interno."""
    # Mensagem do "Posso ajudar?" com 4.001 letras
    assert empresa.post("/api/empresa/conversa", json={"texto": "a" * 4001}).status_code == 422
    # Destaque do material do Endomarketing (a rota do banco que chama a IA) com 501 letras
    pedido_com_destaque_gigante = dict(PEDIDO_DE_MATERIAL)
    pedido_com_destaque_gigante["destaque"] = "a" * 501
    assert banco.post(ROTA_DO_MATERIAL, json=pedido_com_destaque_gigante).status_code == 422
    # Login com 201 letras
    navegador = TestClient(aplicacao, raise_server_exceptions=False)
    assert navegador.post("/api/entrar", json={"usuario": "a" * 201, "senha": "x"}).status_code == 422
    # Senha de 1 MB (o bcrypt só aceita 72 bytes): recusa comum, sem erro interno
    resposta_senha = navegador.post("/api/entrar", json={"usuario": "segc.senha.gigante", "senha": "a" * UM_MEGABYTE})
    assert resposta_senha.status_code == 401


def test_c16_todo_campo_de_texto_tem_teto_de_tamanho(empresa, banco):
    """C-16: 1 MB num campo de texto é recusado na entrada (422), antes de chegar ao serviço ou ao banco de dados.

    Comportamento correto: um max_length em cada campo de texto das rotas (como já existe no chat e na pergunta).
    """
    # Um texto de ~1 MB (1 milhão de letras: abaixo do teto de 1 MiB que o Starlette põe em cada campo de formulário,
    # para o catálogo mostrar o que a rota faz, e não o que o leitor de formulário faz)
    texto_gigante = "a" * 1_000_000
    # (O título gigante no catálogo do banco saiu com a rota: as KBs do Endomarketing a substituíram, com teto)
    # Correção de pendência: motivo gigante
    corrigir = empresa.post("/api/empresa/pendencias/corrigir",
                            json={"processamento_id": "x", "linha": 1, "campo": "cpf", "novo_valor": "1",
                                  "motivo": texto_gigante})
    assert corrigir.status_code == 422
    # Confirmação de alerta: justificativa gigante
    confirmar = empresa.post("/api/empresa/pendencias/confirmar",
                             json={"processamento_id": "x", "regra_id": "R", "linha": 1,
                                   "justificativa": texto_gigante})
    assert confirmar.status_code == 422
    # Endomarketing (gerado pelo banco desde o ADR-115): tipo gigante e benefício gigante
    material = banco.post("/api/banco/empresas/EMP001/endomarketing/gerar",
                          json={"tipo": texto_gigante, "beneficios": ["Conta salário"]})
    assert material.status_code == 422
    beneficio_gigante = banco.post("/api/banco/empresas/EMP001/endomarketing/gerar",
                                   json={"tipo": "faq", "beneficios": [texto_gigante]})
    assert beneficio_gigante.status_code in (400, 422)


def test_c17_taxa_nan_e_recusada_com_mensagem_clara(banco):
    """C-17: "NaN" (não é número) na taxa recebe 400/422 com mensagem, e não erro interno.

    O leitor de JSON do Python aceita NaN, e o Pydantic aceita NaN num float; na conta em Decimal, a comparação
    com NaN levantava InvalidOperation (não é ValueError), que virava 500. Corrigido com o simulador do planejamento:
    cada premissa passa por services/parametros.percentual_conferido, que recusa NaN e infinito (400).
    """
    # O JSON com NaN precisa ir como texto (o json.dumps padrão até aceitaria, mas assim fica explícito)
    cabecalho_json = {"content-type": "application/json"}
    # A taxa é a % novas contas do Simulador de Rentabilidade (a antiga taxa de conquista saiu)
    projecao = banco.post("/api/banco/planejamento/ganho",
                          content=b'{"premissas": {"percentual_novas_contas": NaN}, "clientes_da_empresa": 10}',
                          headers=cabecalho_json)
    simulacao = banco.post("/api/banco/planejamento/simulacoes",
                           content=b'{"nome": "NaN", "premissas": {"percentual_novas_contas": NaN}, '
                                   b'"clientes_da_empresa": 10}', headers=cabecalho_json)
    # Correto: recusa limpa nas duas rotas
    assert projecao.status_code in (400, 422)
    assert simulacao.status_code in (400, 422)


def test_c18_taxa_negativa_infinita_ou_acima_de_100_e_recusada(banco):
    """C-18: taxa -5%, 150%, Infinity e 1e400 recebem 400 com a faixa certa (0% a 100%)."""
    # Taxas fora da faixa, em JSON cru (Infinity e 1e400 viram infinito no Python)
    for taxa_em_texto in (b"-5", b"150", b"Infinity", b"1e400"):
        resposta = banco.post("/api/banco/planejamento/ganho",
                              content=b'{"clientes_da_empresa": 10, "premissas": {"percentual_novas_contas": '
                                      + taxa_em_texto + b"}}",
                              headers={"content-type": "application/json"})
        assert resposta.status_code == 400
        assert "entre 0% e 100%" in resposta.json()["detail"]


def test_c19_numero_inteiro_gigante_e_recusado_com_4xx(banco, empresa):
    """C-19: 10^20 na versão das premissas e 2^63 no início da página recebem 4xx, e não erro interno.

    O FastAPI aceita inteiros de qualquer tamanho; o SQLite só guarda até 2^63 - 1 e levanta OverflowError.
    Comportamento correto: faixa definida no modelo (ex.: Field(ge=0, le=1_000_000)).
    """
    # Versão das premissas gigante
    projecao = banco.post("/api/banco/planejamento/ganho", json={"premissas": {"horizonte_meses": 10 ** 20}})
    assert projecao.status_code in (400, 404, 422)
    # Início da página de envios logo acima do maior inteiro do SQLite
    pagina = empresa.get("/api/empresa/envios/pagina?inicio=9223372036854775808")
    assert pagina.status_code in (400, 422)


def test_c20_texto_com_unicode_invalido_e_recusado_com_4xx(empresa):
    """C-20: "\\ud800" (metade de um caractere, inválido em UTF-8) na mensagem recebe 400/422, e não erro interno."""
    # O JSON permite escrever "\ud800"; o Python aceita, mas o banco de dados não consegue gravar
    resposta = empresa.post("/api/empresa/conversa", content=b'{"texto": "ola \\ud800 mundo"}',
                            headers={"content-type": "application/json"})
    assert resposta.status_code in (400, 422)


def test_c21_cadastro_da_empresa_recusa_data_e_uf_que_nao_existem(banco):
    """C-21: "2026-02-30" no início do contrato e "ZZ" na UF são recusados com 400 (o CNPJ já é conferido)."""
    # Os dados de uma empresa, com um CNPJ válido novo em cada tentativa
    dados_com_data_invalida = {"nome": "Empresa Data Invalida", "setor": "Varejo", "municipio": "Campinas", "uf": "SP",
                               "cnpj": novo_cnpj_ficticio(), "endereco_comercial": "Rua A, 1",
                               "dominio_email": "exemplo.com.br", "contrato_desde": "2026-02-30"}
    dados_com_uf_invalida = {"nome": "Empresa UF Invalida", "setor": "Varejo", "municipio": "Campinas", "uf": "ZZ",
                             "cnpj": novo_cnpj_ficticio(), "endereco_comercial": "Rua A, 1",
                             "dominio_email": "exemplo.com.br", "contrato_desde": "2026-01-10"}
    # As duas precisam ser recusadas
    assert banco.post("/api/banco/empresas", json=dados_com_data_invalida).status_code == 400
    assert banco.post("/api/banco/empresas", json=dados_com_uf_invalida).status_code == 400


def test_c22_cnpj_e_cpf_invalidos_sao_recusados(banco):
    """C-22: CNPJ com dígito errado ou todo repetido é recusado no cadastro; CPF repetido, curto ou com letra não vale."""
    # CNPJ com o dígito verificador errado
    dados = {"nome": "Empresa CNPJ Errado", "setor": "Varejo", "municipio": "Campinas", "uf": "SP",
             "cnpj": "12.345.678/0001-00", "endereco_comercial": "Rua A, 1", "dominio_email": "exemplo.com.br",
             "contrato_desde": "2026-01-10"}
    resposta = banco.post("/api/banco/empresas", json=dados)
    assert resposta.status_code == 400
    assert "CNPJ não confere" in resposta.json()["detail"]
    # CNPJ todo repetido
    dados["cnpj"] = "11.111.111/1111-11"
    assert banco.post("/api/banco/empresas", json=dados).status_code == 400
    # CPFs inválidos: todos iguais, curto, longo e com letra
    for cpf in ("00000000000", "11111111111", "5299822472", "529982247250", "5299822472a"):
        assert not cpf_valido(cpf), cpf
    # E o válido continua valendo
    assert cpf_valido("52998224725")


def texto_tem_unicode_perigoso(texto: str) -> bool:
    """True se o texto tem um caractere de inversão de direção (bidi) ou invisível. Ex.: "Ana\\u202e" → True."""
    for caractere in CARACTERES_UNICODE_PERIGOSOS:
        if caractere in texto:
            return True
    return False


def test_c23_nome_da_empresa_nao_guarda_unicode_perigoso(banco):
    """C-23: um nome com inversão de direção ou caractere invisível é recusado (400) ou gravado sem eles.

    Por quê: "Empresa\\u202eAVON" aparece na tela como outro texto (a direção inverte): serve para enganar quem lê.
    """
    # Nome com inversão de direção e um caractere de largura zero
    dados = {"nome": "Empresa\u202eAVON\u200b", "setor": "Varejo", "municipio": "Campinas", "uf": "SP",
             "cnpj": novo_cnpj_ficticio(), "endereco_comercial": "Rua A, 1", "dominio_email": "exemplo.com.br",
             "contrato_desde": "2026-01-10"}
    resposta = banco.post("/api/banco/empresas", json=dados)
    # Recusado: tudo certo
    if resposta.status_code == 400:
        return
    # Aceito: o nome gravado não pode ter os caracteres perigosos
    assert resposta.status_code == 200
    assert not texto_tem_unicode_perigoso(resposta.json()["nome"])


def test_c24_recusa_de_entrada_nunca_mostra_a_mensagem_tecnica_do_python(banco):
    """C-24: dígito "²" no CNPJ e data "ontem" na vigência do catálogo recebem mensagem em português, sem detalhe
    técnico da linguagem (o executar_acao transforma QUALQUER ValueError em 400 com o texto do erro)."""
    # CNPJ com "²" (o Python acha que é dígito, mas int("²") falha)
    dados = {"nome": "Empresa Digito Estranho", "setor": "Varejo", "municipio": "Campinas", "uf": "SP",
             "cnpj": "\u00b2\u00b2.444.777/0001-61", "endereco_comercial": "Rua A, 1",
             "dominio_email": "exemplo.com.br", "contrato_desde": "2026-01-10"}
    resposta_cnpj = banco.post("/api/banco/empresas", json=dados)
    # A outra metade do achado (a vigência "ontem" na rota do catálogo) saiu com a rota: as KBs do Endomarketing a
    # substituíram, e a revisão da KB já recusa a data com a frase dela. O mecanismo geral é provado no B-15
    # É recusado (isso já acontecia)
    assert resposta_cnpj.status_code == 400
    # Mas a mensagem não pode ser a do Python
    assert "invalid literal" not in resposta_cnpj.json()["detail"]


# ============================== 4. Integração com a IA (sempre simulada) ==============================

def test_c25_limite_de_chamadas_e_teto_de_gasto_pausam_a_ia_dentro_do_cliente(monkeypatch):
    """C-25: no mesmo cliente de IA, passado o limite de chamadas ou o teto de gasto, a chamada PAUSA (IAIndisponivel)
    e nada é simulado (ADR-145). A queda para o MOCK só existe com a reserva, ligada na máquina local."""

    def provedor_que_custa(*argumentos):
        """Provedor simulado: responde e informa custo de 0,60 dólar."""
        return RespostaLLM(texto="ok", modo="llm", modelo="modelo-simulado", custo_usd=0.6)

    # Um cliente em modo real, com limite de 2 chamadas e teto de 1 dólar, sem a reserva (como no servidor)
    cliente = LLMClient(modo="llm", limite_chamadas=2, teto_de_gasto_usd=1.0, mock_de_reserva=False)
    # O provedor simulado no lugar do real
    monkeypatch.setattr(cliente, "_chamar_provedor", provedor_que_custa)
    # Duas chamadas reais; a terceira pausa (o teto de 1 dólar foi passado na segunda)
    modos = []
    for _ in range(2):
        modos.append(cliente.gerar("tarefa", "pedido").modo)
    with pytest.raises(IAIndisponivel):
        cliente.gerar("tarefa", "pedido")
    assert modos == ["llm", "llm"]
    # Com a reserva (só na máquina local), a terceira cai para o MOCK, como era antes
    cliente_com_reserva = LLMClient(modo="llm", limite_chamadas=2, teto_de_gasto_usd=1.0, mock_de_reserva=True)
    monkeypatch.setattr(cliente_com_reserva, "_chamar_provedor", provedor_que_custa)
    modos_com_reserva = []
    for _ in range(3):
        modos_com_reserva.append(cliente_com_reserva.gerar("tarefa", "pedido").modo)
    assert modos_com_reserva == ["llm", "llm", "mock"]


def test_c26_erro_do_provedor_nao_vaza_detalhe_nem_derruba_a_rota(empresa, monkeypatch):
    """C-26: o provedor falha com uma mensagem que tem endereço e "chave"; a rota responde sem esse detalhe e sem erro
    interno (500). Desde o ADR-145, a IA pausa: o envio da empresa fica guardado em "tentar de novo", sem mapeamento
    simulado. (A parte do Consultor saiu com ele, ADR-144.)"""
    # O texto que nunca pode chegar à tela
    detalhe_secreto = "DETALHE_INTERNO_DO_PROVEDOR https://bedrock-runtime.us-east-1.amazonaws.com chave=AKIAFALSA"

    def provedor_que_falha(self, *argumentos, **argumentos_nomeados):
        """Provedor simulado que sempre falha, com o detalhe interno na mensagem do erro."""
        raise RuntimeError(detalhe_secreto)

    # Modo real, sem o MOCK de reserva (como no servidor), com o provedor simulado que falha
    monkeypatch.setattr(config, "MODO", "llm")
    monkeypatch.setattr(config, "MOCK_DE_RESERVA", False)
    monkeypatch.setattr(LLMClient, "_chamar_provedor", provedor_que_falha)
    # O envio de arquivo da empresa (Interpretador)
    resposta_envio = empresa.post("/api/empresa/cadastro/enviar",
                                  files={"arquivo": ("falha.csv", csv_com_uma_pessoa_nova())})
    # O envio responde, pausado
    assert resposta_envio.status_code == 200, resposta_envio.text
    assert resposta_envio.json()["etapa"] == "aguardar_nova_tentativa"
    # E não mostra o detalhe interno
    assert "DETALHE_INTERNO_DO_PROVEDOR" not in resposta_envio.text
    assert "AKIAFALSA" not in resposta_envio.text


def test_c27_resposta_estragada_do_provedor_nao_derruba_o_fluxo(empresa, monkeypatch):
    """C-27: o provedor devolve texto que não é JSON; o envio segue, sem 500."""

    def provedor_que_responde_lixo(self, *argumentos, **argumentos_nomeados):
        """Provedor simulado que responde um texto sem formato nenhum."""
        return RespostaLLM(texto="}{ isto não é JSON <<<", modo="llm", modelo="modelo-simulado", custo_usd=0.0)

    # Modo real, com o provedor simulado que responde lixo
    monkeypatch.setattr(config, "MODO", "llm")
    monkeypatch.setattr(LLMClient, "_chamar_provedor", provedor_que_responde_lixo)
    # O envio da empresa continua (a pessoa escolhe os campos no aceite)
    resposta_envio = empresa.post("/api/empresa/cadastro/enviar",
                                  files={"arquivo": ("lixo.csv", csv_com_uma_pessoa_nova())})
    assert resposta_envio.status_code == 200


@pytest.mark.xfail(strict=True, reason="C-28: prazo das chamadas à IA longo demais: 300 s por tentativa no Bedrock "
                                       "(até ~21 min com 4 tentativas) e os SDKs sem prazo explícito (600 s)")
def test_c28_toda_chamada_ao_provedor_tem_prazo_explicito_e_curto(monkeypatch):
    """C-28: o prazo total de uma chamada (somando tentativas e esperas) é de no máximo 10 minutos, e os clientes da
    Anthropic e da OpenAI são criados com prazo explícito.

    Sem rede: o httpx.post, a Anthropic e a OpenAI são trocados por versões que só anotam como foram chamados.
    """
    # O que cada chamada simulada recebeu
    anotacoes = {}

    class RespostaHttpSimulada:
        """Uma resposta do Bedrock simulada, no formato da API Converse."""
        status_code = 200
        text = ""

        def raise_for_status(self):
            """Resposta de sucesso: nada a fazer."""

        def json(self):
            """O corpo da resposta, com texto e tokens."""
            return {"output": {"message": {"content": [{"text": "ok"}]}},
                    "usage": {"inputTokens": 1, "outputTokens": 1}, "stopReason": "end_turn"}

    def post_simulado(endereco, **argumentos_nomeados):
        """No lugar do httpx.post: anota o prazo pedido e responde sucesso."""
        anotacoes["prazo_do_bedrock"] = argumentos_nomeados.get("timeout")
        return RespostaHttpSimulada()

    class ClienteDeSdkSimulado:
        """No lugar de anthropic.Anthropic e openai.OpenAI: anota os argumentos de criação."""

        def __init__(self, **argumentos_nomeados):
            """Guarda os nomes dos argumentos recebidos."""
            anotacoes.setdefault("argumentos_dos_sdks", []).append(sorted(argumentos_nomeados))

    import anthropic
    import httpx
    import openai
    # As trocas valem só neste teste
    monkeypatch.setattr(httpx, "post", post_simulado)
    monkeypatch.setattr(anthropic, "Anthropic", ClienteDeSdkSimulado)
    monkeypatch.setattr(openai, "OpenAI", ClienteDeSdkSimulado)
    monkeypatch.setattr(config, "CHAVE_BEDROCK", "chave-simulada")
    monkeypatch.setattr(config, "CHAVE_ANTHROPIC", "chave-simulada")
    monkeypatch.setattr(config, "CHAVE_OPENAI", "chave-simulada")
    # Uma chamada pela API Converse do Bedrock (simulada) e a criação dos dois clientes da rota direta
    provedores_de_ia.chamar_pelo_converse("us.amazon.nova-2-lite-v1:0", "sistema", "pedido", 0.0, 100)
    provedores_de_ia._cliente_anthropic()
    provedores_de_ia._cliente_openai()
    # O Bedrock já tem um prazo por tentativa (isso existe)
    prazo_por_tentativa = anotacoes["prazo_do_bedrock"]
    assert prazo_por_tentativa is not None
    # O prazo total: todas as tentativas mais as esperas entre elas
    prazo_total = prazo_por_tentativa * provedores_de_ia.TENTATIVAS_NO_CONVERSE
    for espera in provedores_de_ia.ESPERAS_ENTRE_TENTATIVAS:
        prazo_total = prazo_total + espera
    # Correto: no máximo 10 minutos no total, e os SDKs com prazo explícito
    assert prazo_total <= 600
    for nomes_dos_argumentos in anotacoes["argumentos_dos_sdks"]:
        assert "timeout" in nomes_dos_argumentos


@pytest.mark.xfail(strict=True, reason="C-29: o limite de chamadas vale por operação, não por sessão: com limite "
                                       "2, três materiais do Endomarketing passam de 2 chamadas (seguranca.md 6.2 e 8, "
                                       "item 6)")
def test_c29_limite_de_chamadas_a_ia_vale_para_a_sessao_do_usuario(banco, monkeypatch):
    """C-29: com LIMITE_CHAMADAS_LLM_POR_SESSAO = 2, a mesma sessão não faz mais que 2 chamadas reais à IA.

    O nome da variável diz "por sessão", mas cada operação cria um cliente de IA novo, com o contador zerado.
    """
    # Quantas chamadas chegaram ao provedor (simulado)
    contador = {"chamadas": 0}

    def provedor_que_conta(self, *argumentos, **argumentos_nomeados):
        """Provedor simulado que só conta e responde um texto qualquer."""
        contador["chamadas"] = contador["chamadas"] + 1
        return RespostaLLM(texto="ok", modo="llm", modelo="modelo-simulado", custo_usd=0.0)

    # Modo real, limite de 2 chamadas, provedor simulado
    monkeypatch.setattr(config, "MODO", "llm")
    monkeypatch.setattr(config, "LIMITE_CHAMADAS_LLM_POR_SESSAO", 2)
    monkeypatch.setattr(LLMClient, "_chamar_provedor", provedor_que_conta)
    # Três materiais pedidos pela mesma sessão
    for _ in range(3):
        assert banco.post(ROTA_DO_MATERIAL, json=PEDIDO_DE_MATERIAL).status_code == 200
    # Correto: no máximo 2 chamadas reais na sessão
    assert contador["chamadas"] <= 2


@pytest.mark.xfail(strict=True, reason="C-30: sem limite de frequência nas rotas caras (Endomarketing, envio, "
                                       "assistente): 30 pedidos seguidos passam (seguranca.md 8, item 6)")
def test_c30_rotas_caras_tem_limite_de_frequencia(banco):
    """C-30: 30 pedidos seguidos de material ao Endomarketing, da mesma pessoa: a partir de algum ponto, 429 ("muitos
    pedidos").

    Em MOCK o material não custa nada; com a IA real, cada um custaria. O teste mede só se existe o freio.
    """
    # Os códigos de resposta dos 30 pedidos seguidos
    codigos = []
    for _ in range(30):
        codigos.append(banco.post(ROTA_DO_MATERIAL, json=PEDIDO_DE_MATERIAL).status_code)
    # Correto: algum pedido recebe 429
    assert 429 in codigos


# ============================== 5. Docker e Compose ==============================

@pytest.fixture(scope="module")
def receita_do_compose() -> dict:
    """O docker-compose.yml lido como dicionário (só leitura)."""
    return yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))


def test_c31_compose_e_imagem_nao_carregam_segredo_escrito(receita_do_compose):
    """C-31: nenhuma senha ou chave escrita no compose (só ${...} do .env) e o .env e o storage fora da imagem."""
    # As variáveis que são segredo
    nomes_de_segredo = ("PASSWORD", "SENHA", "KEY", "TOKEN")
    for servico in receita_do_compose["services"].values():
        for nome, valor in servico.get("environment", {}).items():
            # Todo segredo vem de uma variável ${...}, nunca escrito no arquivo
            for pedaco in nomes_de_segredo:
                if pedaco in nome:
                    assert str(valor).startswith("${"), nome
    # O .dockerignore deixa o .env e a pasta de dados fora da imagem
    linhas_do_dockerignore = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in linhas_do_dockerignore
    assert "storage/" in linhas_do_dockerignore


@pytest.mark.xfail(strict=True, reason="C-32: o contêiner da aplicação não tem teste de saúde (healthcheck); só o "
                                       "banco tem")
def test_c32_aplicacao_tem_teste_de_saude(receita_do_compose):
    """C-32: o serviço "aplicacao" tem healthcheck (no compose ou HEALTHCHECK no Dockerfile)."""
    # O serviço da aplicação e o Dockerfile
    servico = receita_do_compose["services"]["aplicacao"]
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    # Correto: um dos dois define o teste de saúde
    assert "healthcheck" in servico or "HEALTHCHECK" in dockerfile


@pytest.mark.xfail(strict=True, reason="C-33: o uvicorn confia nos cabeçalhos X-Forwarded-* de qualquer origem "
                                       "(--forwarded-allow-ips='*') e a porta 8000 abre em todas as interfaces")
def test_c33_so_o_balanceador_de_carga_pode_dizer_que_a_conexao_e_https(receita_do_compose):
    """C-33: ou a confiança nos cabeçalhos de proxy é só do balanceador, ou a porta 8000 não fica aberta a todos.

    Com "*" e a porta 8000 aberta, qualquer pessoa que chegue direto à porta pode mandar "X-Forwarded-Proto: https"
    e "X-Forwarded-For" à vontade.
    """
    # O comando de subida do contêiner e as portas publicadas
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    portas = receita_do_compose["services"]["aplicacao"].get("ports", [])
    # A confiança é em qualquer origem?
    confia_em_todos = "--forwarded-allow-ips='*'" in dockerfile
    # A porta abre para todas as interfaces (sem "127.0.0.1:" na frente)?
    porta_aberta_a_todos = False
    for porta in portas:
        if not str(porta).startswith("127.0.0.1:"):
            porta_aberta_a_todos = True
    # Correto: não as duas coisas ao mesmo tempo
    assert not (confia_em_todos and porta_aberta_a_todos)


@pytest.mark.xfail(strict=True, reason="C-34: segredos entram no contêiner como variáveis de ambiente (visíveis no "
                                       "docker inspect); o gerenciador de segredos está planejado (seguranca.md 7)")
def test_c34_segredos_chegam_ao_conteiner_por_arquivo_de_segredo(receita_do_compose):
    """C-34: as chaves e senhas chegam por "secrets" do Compose (arquivo montado), não por variável de ambiente."""
    # As variáveis de ambiente da aplicação
    ambiente = receita_do_compose["services"]["aplicacao"].get("environment", {})
    # As que são segredo
    segredos_no_ambiente = []
    for nome in ambiente:
        if "KEY" in nome or "TOKEN" in nome or "SENHA" in nome or nome == "POSTGRES_URL":
            segredos_no_ambiente.append(nome)
    # Correto: nenhum segredo como variável de ambiente, e a seção "secrets" em uso
    assert segredos_no_ambiente == []
    assert "secrets" in receita_do_compose
