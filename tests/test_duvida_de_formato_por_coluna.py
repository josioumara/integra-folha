"""Testes da dúvida de formato de uma coluna ("dia/mês ou mês/dia?") quando o arquivo tem mais de uma (o defeito: a
empresa respondia a ordem das datas, e o agente voltava a fazer a mesma pergunta na mesma conversa; ADR-120).

O caso: um arquivo com duas colunas de data em dúvida (nascimento e admissão). As duas dúvidas vinham do Validador sem
campo e sem linha, com a mesma regra: os dois cartões dividiam a conversa, a resposta decidia a PRIMEIRA coluna (não a
do cartão) e o agente emendava "Ainda há um problema:" com a mesma pergunta.

O que estes testes provam (com a IA simulada, sem custo):
- cada dúvida de formato traz o campo da coluna: os dois cartões têm identidades e conversas diferentes;
- a resposta no cartão da admissão decide a admissão (e só ela), resolve o cartão e não repete a pergunta;
- o nascimento continua em dúvida, com a pergunta dele.
"""
import pytest

from services import acompanhamento, assistente_na_tela, banco, cadastro, validador
from tests.test_correcao import busca_falsa

# A empresa e quem escreve
EMPRESA = "EMP001"
LOGIN = "rh.aurora"
# Duas colunas de data em que nada desempata dia/mês de mês/dia (as datas com barras têm dia e mês até 12)
ARQUIVO = ("Nome;CPF;Nascimento;Admissão\n"
           "Ana Lima;52998224725;01/03/1983;02/03/2015\n"
           "Bia Souza;11144477735;1999-01-02;05/06/2018\n"
           "Caio Reis;12345678909;11/08/1991;07/08/2020\n").encode("utf-8")
# O aceite das colunas
ESCOLHAS = {"Nome": "nome_completo", "CPF": "cpf", "Nascimento": "data_nascimento", "Admissão": "data_admissao"}


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture(autouse=True)
def usar_busca_falsa(monkeypatch):
    """Nenhum uso do RAG depende do índice nem do modelo de embeddings."""
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)


@pytest.fixture
def envio(conexao) -> str:
    """O arquivo enviado e aceito pela Aurora. Devolve o envio."""
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, ARQUIVO, "datas.csv", busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS, busca=busca_falsa)
    return leitura["processamento_id"]


def duvidas_de_data(conexao) -> dict[str, dict]:
    """As pendências de dúvida de datas, pelo nome da coluna (como Acompanhar recebe)."""
    duvidas = {}
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == "DATA_AMBIGUA":
            duvidas[pendencia["coluna_do_formato"]] = pendencia
    return duvidas


def test_cada_duvida_de_formato_tem_o_seu_campo(conexao, envio):
    duvidas = duvidas_de_data(conexao)
    assert set(duvidas) == {"Nascimento", "Admissão"}
    assert duvidas["Nascimento"]["campo"] == "data_nascimento"
    assert duvidas["Admissão"]["campo"] == "data_admissao"
    # O título diz a coluna, e cada cartão tem a sua pergunta, com os exemplos da sua coluna
    assert duvidas["Admissão"]["titulo_do_cartao"] == 'Ajuste no formato da coluna "Admissão" no arquivo inteiro'
    assert "02/03/2015" in duvidas["Admissão"]["pergunta"] and "01/03/1983" in duvidas["Nascimento"]["pergunta"]


def test_a_resposta_no_cartao_da_admissao_decide_so_a_admissao_e_nao_repete_a_pergunta(conexao, envio):
    admissao = duvidas_de_data(conexao)["Admissão"]
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, admissao["regra_id"], admissao["linha"],
                                            "As datas estão em dia/mês (DD/MM/AAAA)", campo=admissao["campo"])
    # Resolvido, sem "Ainda há um problema" nem a mesma pergunta de novo
    assert resposta["acao"] == "escolher_formato" and resposta["resolvida"] is True
    assert "Ainda há um problema" not in resposta["mensagem"]
    assert "Admissão" in resposta["mensagem"]
    # Só a admissão foi decidida: o nascimento continua em dúvida, no cartão dele
    colunas_pendentes = [formato["coluna"] for formato in cadastro.formatos_pendentes(conexao, envio)]
    assert colunas_pendentes == ["Nascimento"]
    assert set(duvidas_de_data(conexao)) == {"Nascimento"}
    # As conversas das duas colunas são diferentes
    nascimento = duvidas_de_data(conexao)["Nascimento"]
    assert resposta["chave"] != f"{envio}|DATA_AMBIGUA|null|{nascimento['campo']}"


def test_a_duvida_de_formato_nao_aceita_um_valor_para_todos(conexao, envio):
    """Com o campo na dúvida de formato, "o valor para todos é X" não pode virar um preenchimento da coluna."""
    admissao = duvidas_de_data(conexao)["Admissão"]
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, admissao["regra_id"], admissao["linha"],
                                            "O valor para todos é: 01/01/2020", campo=admissao["campo"])
    assert resposta["aplicado"] is None and resposta["resolvida"] is False
    relatorio = validador.obter(conexao, envio)
    for achado in relatorio.achados:
        assert achado.regra_id != "OBRIGATORIO_VAZIO" or achado.campo != "data_admissao"


def test_o_agente_entende_as_respostas_rapidas_das_datas():
    """As duas respostas rápidas do cartão (e o jeito de escrever à mão) viram a ordem certa das datas; antes, o texto
    normalizado ("dia mes") nunca casava com a procura por "dia/mes", e o agente perguntava de novo."""
    from agents.assistente_correcao import _formato_da_mensagem
    from baselines.baseline_mapper import normalizar
    assert _formato_da_mensagem(normalizar("As datas estão em dia/mês (DD/MM/AAAA)"), "DATA_AMBIGUA") == "DMY"
    assert _formato_da_mensagem(normalizar("As datas estão em mês/dia (MM/DD/AAAA)"), "DATA_AMBIGUA") == "MDY"
    assert _formato_da_mensagem(normalizar("é dia/mês, não mês/dia"), "DATA_AMBIGUA") == "DMY"
    assert _formato_da_mensagem(normalizar("não sei"), "DATA_AMBIGUA") is None
    assert _formato_da_mensagem(normalizar("A matrícula tem 5 dígitos"), "ZEROS_A_ESQUERDA") == "zeros:5"
