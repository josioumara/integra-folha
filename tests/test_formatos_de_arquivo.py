"""Os formatos novos de arquivo, lidos por regra: Excel antigo (.xls), LibreOffice (.ods), texto (.txt), Word do
LibreOffice (.odt) e texto formatado (.rtf) (ADR-88 e ADR-89).

O que estes testes provam:
- .xls e .ods viram a mesma leitura de uma planilha .xlsx: cabeçalho achado, datas em AAAA-MM-DD com o aviso,
  números marcados como número (para o aviso dos zeros à esquerda) e o aviso quando há mais de uma aba;
- .txt com colunas é lido como CSV; .txt sem colunas (um e-mail do RH) passa pelo caminho do Word em texto corrido;
- a assinatura dos bytes confere com a extensão (um PDF com o nome .xls, ou um .ods que não é zip, é recusado);
- a regra "o texto parece uma tabela?" separa tabela de texto corrido;
- .odt vira um Word em memória (parágrafos e tabelas na mesma ordem) e .rtf vira texto, pelos caminhos que já existem.
"""
import io
from datetime import datetime
from pathlib import Path

import pandas
import pytest

from services import ingestao

# O Excel antigo de teste (gerado uma vez com a biblioteca xlwt; 2 pessoas fictícias e uma segunda aba vazia)
ARQUIVO_XLS = Path(__file__).resolve().parent / "dados" / "lista_excel_antigo.xls"


def planilha_ods() -> bytes:
    """Uma planilha do LibreOffice (.ods) feita na hora: cabeçalho e 1 pessoa, com data e salário."""
    tabela = pandas.DataFrame([["Nome", "CPF", "Admissão", "Salário"],
                               ["Maria Souza", "52998224725", datetime(2024, 3, 1), 3150.5]])
    memoria = io.BytesIO()
    tabela.to_excel(memoria, engine="odf", header=False, index=False)
    return memoria.getvalue()


def test_excel_antigo_xls_vira_a_mesma_leitura_da_planilha():
    leitura = ingestao.ler_arquivo(ARQUIVO_XLS.read_bytes(), "lista.xls")
    assert leitura.formato == "xls"
    assert leitura.cabecalhos == ["Nome", "CPF", "Matrícula", "Admissão", "Salário"]
    assert leitura.linhas[0] == ["Maria Souza", "52998224725", "123", "2024-03-01", "3150.5"]
    assert "A planilha tem 2 abas; só a aba Funcionarios foi lida." in leitura.avisos
    assert "Células de data da planilha foram lidas no formato AAAA-MM-DD." in leitura.avisos


def test_libreoffice_ods_vira_a_mesma_leitura_da_planilha():
    leitura = ingestao.ler_arquivo(planilha_ods(), "lista.ods")
    assert leitura.formato == "ods"
    assert leitura.cabecalhos == ["Nome", "CPF", "Admissão", "Salário"]
    assert leitura.linhas == [["Maria Souza", "52998224725", "2024-03-01", "3150.5"]]


def test_txt_com_colunas_e_lido_como_csv():
    conteudo = "Nome;CPF\nAna;52998224725\nBia;11144477735\n".encode("utf-8")
    leitura = ingestao.ler_arquivo(conteudo, "lista.txt")
    assert leitura.formato == "txt"
    assert leitura.cabecalhos == ["Nome", "CPF"]
    assert leitura.linhas == [["Ana", "52998224725"], ["Bia", "11144477735"]]


def test_txt_sem_colunas_passa_pelo_caminho_do_texto_corrido():
    """Um e-mail do RH em .txt: a lista é montada pelo mesmo caminho do Word (IA simulada nos testes)."""
    texto = ("Oi, pessoal do banco!\nA Helena Duarte Ramos, CPF 529.982.247-25, entrou em 02/09/2026 como analista, "
             "com salário de R$ 5.200,00.\nO Rafael Monteiro Siqueira, CPF 111.444.777-35, começou em 08/09/2026 "
             "como assistente, salário de R$ 2.750,00.\nAbraços, RH.")
    leitura = ingestao.ler_arquivo(texto.encode("utf-8"), "anotacoes.txt")
    assert leitura.formato == "txt"
    assert len(leitura.linhas) == 2
    assert leitura.avisos[0].startswith("Texto corrido: o Agente Leitor montou a lista com 2 funcionário(s)")


def test_assinatura_dos_bytes_confere_com_a_extensao():
    with pytest.raises(ingestao.ArquivoRecusado, match="Excel antigo"):
        ingestao.ler_arquivo(b"%PDF-1.7 um pdf qualquer", "lista.xls")
    with pytest.raises(ingestao.ArquivoRecusado, match="LibreOffice"):
        ingestao.ler_arquivo(b"texto qualquer", "lista.ods")
    with pytest.raises(ingestao.ArquivoRecusado, match="não é um CSV"):
        ingestao.ler_arquivo(b"PK\x03\x04zip com nome de txt", "lista.txt")
    # Formato fora da lista: a mensagem diz tudo o que serve
    with pytest.raises(ingestao.ArquivoRecusado, match=r"\.xls ou \.ods"):
        ingestao.ler_arquivo(b"qualquer", "programa.exe")


@pytest.mark.parametrize("texto,e_tabela", [
    ("Nome;CPF\nAna;1\nBia;2", True),
    ("Nome\tCPF\nAna\t1\nBia\t2", True),
    ("Nome,CPF,Cargo\nAna,1,Analista\nBia,2,Vendedora", True),
    ("Oi, tudo bem?\nA Ana entrou ontem, como analista.\nAbraços, RH.", False),
    ("Uma linha só; nada mais", False),
    ("Lista de funcionários\nNome;CPF\nAna;1\nBia;2", True),
    ("Oi!\nSeguem os dados; qualquer dúvida, me chame.\nAbraços.", False),
])
def test_texto_parece_tabela(texto, e_tabela):
    assert ingestao.texto_parece_tabela(texto) is e_tabela


def documento_odt(com_tabela: bool) -> bytes:
    """Um documento do LibreOffice (.odt) feito na hora: um parágrafo e, se pedido, uma tabela Nome/CPF/Cargo.

    Sem a tabela, o documento traz as pessoas em texto corrido (vai para o Leitor, com a IA simulada nos testes).
    """
    from odf import table as tabela_odf
    from odf import text as texto_odf
    from odf.opendocument import OpenDocumentText
    documento = OpenDocumentText()
    documento.text.addElement(texto_odf.P(text="Seguem os funcionários que entraram este mês."))
    if com_tabela:
        tabela = tabela_odf.Table(name="Lista")
        tabela.addElement(tabela_odf.TableColumn(numbercolumnsrepeated=3))
        for linha in (["Nome", "CPF", "Cargo"], ["Ana Souza", "52998224725", "Analista"],
                      ["Bia Lima", "11144477735", "Vendedora"]):
            linha_odf = tabela_odf.TableRow()
            for valor in linha:
                celula = tabela_odf.TableCell()
                celula.addElement(texto_odf.P(text=valor))
                linha_odf.addElement(celula)
            tabela.addElement(linha_odf)
        documento.text.addElement(tabela)
    else:
        documento.text.addElement(texto_odf.P(
            text="A Helena Duarte Ramos, CPF 529.982.247-25, entrou em 02/09/2026 como analista, com salário de "
                 "R$ 5.200,00."))
        documento.text.addElement(texto_odf.P(
            text="O Rafael Monteiro Siqueira, CPF 111.444.777-35, começou em 08/09/2026 como assistente, salário de "
                 "R$ 2.750,00."))
    memoria = io.BytesIO()
    documento.write(memoria)
    return memoria.getvalue()


def test_odt_com_tabela_e_lido_por_regra():
    leitura = ingestao.ler_arquivo(documento_odt(com_tabela=True), "lista.odt")
    assert leitura.formato == "odt"
    assert leitura.cabecalhos == ["Nome", "CPF", "Cargo"]
    assert leitura.linhas == [["Ana Souza", "52998224725", "Analista"], ["Bia Lima", "11144477735", "Vendedora"]]


def test_odt_em_texto_corrido_vai_para_o_leitor():
    leitura = ingestao.ler_arquivo(documento_odt(com_tabela=False), "anotacoes.odt")
    assert leitura.formato == "odt"
    assert len(leitura.linhas) == 2


def test_rtf_com_tabela_e_com_acento():
    """A tabela do RTF vira linhas com "|"; o acento escrito como código (\'e3 = ã) volta a ser letra."""
    conteudo = (r"{\rtf1\ansi\ansicpg1252 Lista de funcion\'e1rios\par"
                r"\trowd\cellx2000\cellx4000\cellx6000 Nome\cell CPF\cell Cargo\cell\row"
                r"\trowd\cellx2000\cellx4000\cellx6000 Jo\'e3o Lima\cell 11144477735\cell Assistente\cell\row"
                r"\trowd\cellx2000\cellx4000\cellx6000 Ana Souza\cell 52998224725\cell Analista\cell\row}")
    leitura = ingestao.ler_arquivo(conteudo.encode("ascii"), "lista.rtf")
    assert leitura.formato == "rtf"
    assert leitura.cabecalhos == ["Nome", "CPF", "Cargo"]
    assert leitura.linhas[0] == ["João Lima", "11144477735", "Assistente"]


def test_odt_e_rtf_com_a_extensao_trocada_sao_recusados():
    with pytest.raises(ingestao.ArquivoRecusado, match="LibreOffice"):
        ingestao.ler_arquivo(b"texto qualquer", "lista.odt")
    with pytest.raises(ingestao.ArquivoRecusado, match="rtf"):
        ingestao.ler_arquivo(b"texto qualquer", "lista.rtf")
    # Um .ods com o nome .odt: é zip, mas não abre como documento de texto
    with pytest.raises(ingestao.ArquivoRecusado):
        ingestao.ler_arquivo(planilha_ods(), "lista.odt")

