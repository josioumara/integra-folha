"""Conferir na hora, mostrar o dado e o limite das respostas sem valor, na conversa da pendência (ADR-153).

O que estes testes provam (com a IA simulada, sem custo; cada caso vem com variações que ninguém usou, pela cláusula de
generalização), no parâmetro dos 4 obrigatórios (ADR-143: o CPF, o código da profissão, a renda e a admissão):
- o código da profissão que não é da CBO oficial (letras, dígitos a menos, 6 dígitos que não existem, a letra "O" no
  lugar do zero) é recusado na mesma resposta: nada muda, a pendência continua aberta e nenhum cartão novo nasce; a fala
  diz o que está errado, com o exemplo, e o que a informação tem hoje; a trilha registra a recusa sem valor pessoal;
  vale também com uma IA que "acreditou" no valor (a trava é do código);
- o código certo, escrito de jeitos diferentes, vale na hora; se ele deixa o salário fora da faixa da profissão, a
  mesma fala avisa e o cartão do salário é o que nasce (é uma pergunta, e não um erro);
- o código que veio errado no arquivo e foi escrito errado de novo continua como veio;
- o CPF que já é de outra pessoa do arquivo é recusado, e a fala diz de quem é quando o problema fica na outra linha;
- a recusa da padronização (o dígito do CPF) traz o jeito certo e um exemplo do parâmetro;
- toda pergunta do agente sobre uma pessoa mostra a informação e o que veio no arquivo (ou que veio vazio), sem repetir
  quando a fala já mostra;
- "não sei", "não tenho", "prefiro não informar" (e outras formas) não mudam nada; a 1ª e a 2ª resposta ajudam a achar
  o dado sem repetir a mesma fala; a 3ª encerra com educação, e a pendência continua aberta, mesmo com uma IA que só
  sabe perguntar de novo; depois do encerramento, a conta recomeça; a recusa de um valor não conta como resposta sem
  valor;
- a rota da conversa devolve "encerrada".
"""
import json

import pytest

from agents import assistente_correcao
from services import (assistente_na_tela, auditoria, banco, cadastro, conversas_das_pendencias, correcoes,
                      faixa_salarial_cbo, validador)
from services.llm_client import LLMClient
from tests.apoio_do_parametro import marcar_como_obrigatorios
from tests.test_assistente_na_tela import api_do_assistente, entrar  # noqa: F401
from tests.test_correcao import busca_falsa
from tests.test_faixa_salarial_cbo import faixas_de_teste  # noqa: F401
from tests.test_pendencias_em_grupo import EMPRESA, LOGIN, cpf_valido, usar_busca_falsa  # noqa: F401

# As colunas do arquivo e o campo de cada uma (o aceite da empresa)
ESCOLHAS = {"Nome": "nome_completo", "CPF": "cpf", "Cargo": "cargo", "Código CBO": "codigo_cbo",
            "Tipo de renda": "tipo_renda", "Salário": "valor_renda", "Admissão": "data_admissao"}
# Os CPFs válidos das pessoas do arquivo (inventados)
CPF_DA_ANA = cpf_valido("529982247")
CPF_DA_BIA = cpf_valido("111444777")
CPF_DO_CAIO_CERTO = cpf_valido("123456789")
CPF_DA_DUDA = cpf_valido("987654321")
CPF_DA_FABI = cpf_valido("246813579")
# O CPF do Caio como veio no arquivo: o último dígito trocado
CPF_DO_CAIO_ERRADO = CPF_DO_CAIO_CERTO[:-1] + str((int(CPF_DO_CAIO_CERTO[-1]) + 1) % 10)
# Seis pessoas (as datas têm o dia acima de 12, para não virar dúvida de formato):
#   Ana: sem o código da profissão (o salário cabe na faixa do Assistente administrativo, 2.000 a 5.000)
#   Bia: com um código que não é da CBO
#   Caio: com o CPF de dígito errado
#   Duda: sem pendência
#   Fabi: sem o código da profissão, com o salário acima da faixa do Assistente administrativo
LINHAS_DO_ARQUIVO = [
    "Nome;CPF;Cargo;Código CBO;Tipo de renda;Salário;Admissão",
    f"Ana Lima;{CPF_DA_ANA};Assistente administrativo;;CLT;3000,00;15/02/2020",
    f"Bia Souza;{CPF_DA_BIA};Assistente administrativo;C900;CLT;3000,00;16/02/2020",
    f"Caio Reis;{CPF_DO_CAIO_ERRADO};Assistente administrativo;4110-10;CLT;3000,00;17/02/2020",
    f"Duda Melo;{CPF_DA_DUDA};Assistente administrativo;4110-10;CLT;3000,00;18/02/2020",
    f"Fabi Nunes;{CPF_DA_FABI};Analista;;CLT;9000,00;19/02/2020",
]
# A linha de cada pessoa no arquivo (a 1ª linha é o cabeçalho)
LINHA_DA_ANA, LINHA_DA_BIA, LINHA_DO_CAIO, LINHA_DA_DUDA, LINHA_DA_FABI = 2, 3, 4, 5, 6


# ---------------- Ajudantes ----------------

@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, com o parâmetro dos 4 obrigatórios (ADR-143): o CPF, o código da profissão, a renda e a admissão."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao_do_teste, "especialista")
    marcar_como_obrigatorios(conexao_do_teste, "cpf", "codigo_cbo", "valor_renda", "data_admissao", so_estes=True)
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture
def envio(conexao) -> str:
    """O arquivo das seis pessoas, enviado e aceito pela Aurora (a validação roda no aceite). Devolve o envio."""
    conteudo = ("\n".join(LINHAS_DO_ARQUIVO) + "\n").encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, conteudo, "profissoes.csv", busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS, busca=busca_falsa)
    return leitura["processamento_id"]


def ia_que_responde(**resposta) -> LLMClient:
    """Uma IA simulada que dá sempre a mesma resposta do contrato (a pior IA, para provar a trava do código)."""
    def responder(pedido):
        """Devolve a resposta fixa, em JSON."""
        return json.dumps(resposta)
    return LLMClient(modo="mock", respostas_mock={assistente_correcao.TAREFA: responder})


def conversar(conexao, envio: str, regra_id: str, linha: int, campo: str, mensagem: str, cliente=None) -> dict:
    """Uma mensagem da Aurora na conversa da pendência (a IA simulada do agente, salvo outra)."""
    return assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, regra_id, linha, mensagem, cliente=cliente,
                                        campo=campo)


def achados_da_linha(conexao, envio: str, linha: int) -> list[tuple[str, str]]:
    """(regra, campo) dos achados de uma linha no relatório de agora."""
    pares = []
    for achado in validador.obter(conexao, envio).achados:
        if achado.linha == linha:
            pares.append((achado.regra_id, achado.campo))
    return pares


def valor_de_agora(conexao, envio: str, linha: int, campo: str):
    """O valor de um campo de uma pessoa, com as correções aplicadas."""
    for registro in correcoes.dados_atuais(conexao, envio).registros:
        if registro["_linha"] == linha:
            return registro.get(campo)
    raise AssertionError(f"a linha {linha} devia existir")


def eventos(conexao, envio: str, tipo: str) -> list[dict]:
    """Os detalhes dos eventos de um tipo na trilha de auditoria do envio."""
    detalhes = []
    for evento in auditoria.eventos(conexao, envio):
        if evento["tipo"] == tipo:
            detalhes.append(evento["detalhe"])
    return detalhes


# ---------------- O caso do código da profissão: recusado na hora, sem cartão novo ----------------

@pytest.mark.parametrize("escrito", [
    "C900",       # o caso do teste: uma letra e três números
    "12345",      # dígitos a menos
    "999999",     # 6 dígitos que não são uma profissão
    "4110-1O",    # a letra "O" no lugar do zero
])
def test_o_codigo_da_profissao_que_nao_existe_e_recusado_na_hora(conexao, envio, escrito):
    assert ("OBRIGATORIO_VAZIO", "codigo_cbo") in achados_da_linha(conexao, envio, LINHA_DA_ANA)
    resposta = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_ANA, "codigo_cbo", escrito)
    # Recusado na mesma resposta: nada aplicado, a pendência continua aberta
    assert resposta["aplicado"] is None and resposta["resolvida"] is False and resposta["encerrada"] is False
    fala = resposta["mensagem"]
    assert "Pronto" not in fala and "Nada mudou." in fala
    # A explicação: o valor escrito, o que está errado e o exemplo; e a informação continua vazia
    assert f'"{escrito}"' in fala and "não é uma profissão" in fala and "4110-10" in fala
    assert "continua vazia" in fala and fala.endswith("?")
    # Nenhum cartão novo: a pendência de antes, sem o código que não existe
    assert achados_da_linha(conexao, envio, LINHA_DA_ANA) == [("OBRIGATORIO_VAZIO", "codigo_cbo")]
    assert valor_de_agora(conexao, envio, LINHA_DA_ANA, "codigo_cbo") is None
    # A troca voltou (fica guardada como desfeita) e a trilha diz por quê, sem o valor
    assert correcoes.listar(conexao, envio, "APLICADA") == []
    assert len(correcoes.listar(conexao, envio, correcoes.DESFEITA)) == 1
    recusas = eventos(conexao, envio, "VALOR_RECUSADO_NA_CONVERSA")
    assert recusas == [{"login": LOGIN, "linha": LINHA_DA_ANA, "campo": "codigo_cbo", "regras": ["CBO_DESCONHECIDO"]}]
    assert escrito not in json.dumps(recusas)


def test_a_ia_que_acreditou_no_codigo_tambem_nao_passa(conexao, envio):
    # A pior IA: ela mandou corrigir com o código que não existe (a trava é do código, não da frase)
    ia = ia_que_responde(acao="corrigir", mensagem="Pronto, troquei.", valor="C900")
    resposta = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_ANA, "codigo_cbo",
                         "o código da profissão dela é C900", cliente=ia)
    assert resposta["aplicado"] is None and resposta["resolvida"] is False
    assert "não é uma profissão" in resposta["mensagem"] and "Pronto" not in resposta["mensagem"]
    assert achados_da_linha(conexao, envio, LINHA_DA_ANA) == [("OBRIGATORIO_VAZIO", "codigo_cbo")]


@pytest.mark.parametrize("escrito", ["4110-10", "411010", "4110.10", "o código é 4110-10", "4110 10"])
def test_o_codigo_da_profissao_certo_vale_na_hora(conexao, envio, escrito):
    resposta = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_ANA, "codigo_cbo", escrito)
    assert resposta["mensagem"].startswith("Pronto:") and resposta["resolvida"] is True
    # O salário dela cabe na faixa da profissão: nada a avisar, e nenhum cartão novo
    assert assistente_na_tela.COMECO_DO_AVISO not in resposta["mensagem"]
    assert achados_da_linha(conexao, envio, LINHA_DA_ANA) == []


def test_o_codigo_que_deixa_o_salario_fora_da_faixa_avisa_na_mesma_fala(conexao, envio):
    # A Fabi ganha a profissão, e o salário dela (9.000) fica acima da faixa (2.000 a 5.000): o código vale, e a mesma
    # fala avisa que o salário ficou para conferir (é uma pergunta, e não um erro do código)
    antes = set(achados_da_linha(conexao, envio, LINHA_DA_FABI))
    resposta = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_FABI, "codigo_cbo", "4110-10")
    assert resposta["mensagem"].startswith("Pronto:") and resposta["resolvida"] is True
    assert "Atenção: Salário de R$ 9.000,00 fora da faixa da profissão" in resposta["mensagem"]
    assert resposta["mensagem"].endswith("Ficou um cartão para você conferir.")
    # O único cartão que nasceu é o do salário fora da faixa da profissão (o do código saiu)
    depois = set(achados_da_linha(conexao, envio, LINHA_DA_FABI))
    assert depois - antes == {("RENDA_FORA_DA_PROFISSAO", "valor_renda")}
    assert antes - depois == {("OBRIGATORIO_VAZIO", "codigo_cbo")}


@pytest.mark.parametrize("escrito", ["C901", "000000", "4110"])
def test_o_codigo_que_veio_errado_e_foi_escrito_errado_de_novo_fica_como_veio(conexao, envio, escrito):
    assert ("CBO_DESCONHECIDO", "codigo_cbo") in achados_da_linha(conexao, envio, LINHA_DA_BIA)
    resposta = conversar(conexao, envio, "CBO_DESCONHECIDO", LINHA_DA_BIA, "codigo_cbo", escrito)
    assert resposta["aplicado"] is None and resposta["resolvida"] is False
    assert f'"{escrito}"' in resposta["mensagem"] and 'continua "C900"' in resposta["mensagem"]
    # O valor que veio no arquivo, e a mesma pendência de antes
    assert valor_de_agora(conexao, envio, LINHA_DA_BIA, "codigo_cbo") == "C900"
    assert achados_da_linha(conexao, envio, LINHA_DA_BIA) == [("CBO_DESCONHECIDO", "codigo_cbo")]


# ---------------- As outras regras do campo: o CPF de outra pessoa e o dígito ----------------

def test_o_cpf_que_ja_e_de_uma_pessoa_de_baixo_e_recusado_e_a_fala_diz_de_quem(conexao, envio):
    # O CPF da Duda (linha de baixo) no Caio: a pessoa repetida seria apontada na linha da Duda
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "o certo é " + CPF_DA_DUDA)
    assert resposta["aplicado"] is None and resposta["resolvida"] is False
    assert resposta["mensagem"].startswith(f"Com esse valor, Duda Melo (linha {LINHA_DA_DUDA}) ficaria com outro "
                                           f"problema: o mesmo CPF já aparece na linha {LINHA_DO_CAIO}.")
    assert 'A informação "CPF" de Caio continua' in resposta["mensagem"]
    assert valor_de_agora(conexao, envio, LINHA_DO_CAIO, "cpf") == CPF_DO_CAIO_ERRADO
    assert achados_da_linha(conexao, envio, LINHA_DA_DUDA) == []


def test_o_cpf_que_ja_e_de_uma_pessoa_de_cima_e_recusado(conexao, envio):
    # O CPF da Ana (linha de cima) no Caio: a pessoa repetida seria apontada no próprio Caio
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "CPF correto: " + CPF_DA_ANA)
    assert resposta["aplicado"] is None and resposta["resolvida"] is False
    assert resposta["mensagem"].startswith(f"O mesmo CPF já aparece na linha {LINHA_DA_ANA}. Nada mudou.")
    assert achados_da_linha(conexao, envio, LINHA_DO_CAIO) == [("CPF_INVALIDO", "cpf")]


def test_o_cpf_certo_de_uma_pessoa_nova_vale_na_hora(conexao, envio):
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "o certo é " + CPF_DO_CAIO_CERTO)
    assert resposta["mensagem"].startswith("Pronto:") and resposta["resolvida"] is True
    assert achados_da_linha(conexao, envio, LINHA_DO_CAIO) == []


@pytest.mark.parametrize("escrito", ["123.456.789-00", "52998224700", "1234567890"])
def test_a_recusa_do_digito_traz_o_jeito_certo_e_um_exemplo(conexao, envio, escrito):
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "o certo é " + escrito)
    fala = resposta["mensagem"]
    assert fala.startswith("Esse CPF não confere: ") and "Nada mudou." in fala
    # O jeito certo (a regra do parâmetro), o que o CPF tem hoje e a pergunta com o exemplo do parâmetro
    assert "O certo: 11 dígitos com dígito verificador válido." in fala
    assert 'A informação "CPF" de Caio continua "' in fala
    assert fala.endswith('Qual é o CPF certo (ex.: "123.456.789-09")?')


# ---------------- Mostrar o dado: toda pergunta diz a informação e o que veio no arquivo ----------------

def test_a_pergunta_sem_o_dado_ganha_o_dado_do_arquivo(conexao, envio):
    # Uma IA que pergunta sem dizer qual é o dado
    ia = ia_que_responde(acao="responder", mensagem="Pode me dizer o valor certo?")
    no_cpf = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "hum", cliente=ia)
    cpf_na_tela = f"{CPF_DO_CAIO_ERRADO[:3]}.{CPF_DO_CAIO_ERRADO[3:6]}.{CPF_DO_CAIO_ERRADO[6:9]}-{CPF_DO_CAIO_ERRADO[9:]}"
    assert no_cpf["mensagem"] == (f'No arquivo, a informação "CPF" de Caio veio como "{cpf_na_tela}". '
                                  "Pode me dizer o valor certo?")
    # O dado que veio vazio: a frase diz que veio vazio
    no_codigo = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_ANA, "codigo_cbo", "hum", cliente=ia)
    assert no_codigo["mensagem"].startswith("No arquivo, a informação ") and "de Ana veio vazia." in no_codigo["mensagem"]


def test_a_pergunta_que_ja_mostra_o_dado_nao_repete(conexao, envio):
    # A IA já disse o valor (do jeito que veio, ou do jeito da tela) e que veio vazio: nada a acrescentar
    ia_com_o_valor = ia_que_responde(acao="responder", mensagem=f'O CPF veio "{CPF_DO_CAIO_ERRADO}". Qual é o certo?')
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "hum", cliente=ia_com_o_valor)
    assert resposta["mensagem"] == f'O CPF veio "{CPF_DO_CAIO_ERRADO}". Qual é o certo?'
    ia_com_o_vazio = ia_que_responde(acao="responder", mensagem="O código veio vazio no arquivo. Qual é o certo?")
    resposta = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_ANA, "codigo_cbo", "hum",
                         cliente=ia_com_o_vazio)
    assert resposta["mensagem"] == "O código veio vazio no arquivo. Qual é o certo?"


def test_a_fala_sem_pergunta_fica_como_esta(conexao, envio):
    # Uma explicação sem pergunta não ganha a frase do dado
    ia = ia_que_responde(acao="explicar_regra", mensagem="O CPF tem um dígito que confere os outros.")
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "por que isso", cliente=ia)
    assert resposta["mensagem"] == "O CPF tem um dígito que confere os outros."


# ---------------- O limite das respostas sem valor ----------------

@pytest.mark.parametrize("tres_respostas", [
    ("não sei", "não tenho", "prefiro não informar"),                  # o caso do teste
    ("Sei lá.", "Não lembro", "desconheço"),                          # outras palavras, com pontuação
    ("NÃO SABEMOS", "não temos essa informação", "não quero informar"),  # maiúsculas, plural
])
def test_tres_respostas_sem_valor_encerram_com_educacao(conexao, envio, tres_respostas):
    primeira = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", tres_respostas[0])
    segunda = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", tres_respostas[1])
    terceira = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", tres_respostas[2])
    # As duas primeiras: nada muda, a pergunta mostra o dado e ajuda a achar o valor, sem repetir a mesma fala
    for resposta in (primeira, segunda):
        assert resposta["acao"] == "sem_valor" and resposta["aplicado"] is None and resposta["encerrada"] is False
        assert resposta["mensagem"].startswith('No arquivo, a informação "CPF" de Caio veio como "')
    assert primeira["mensagem"] != segunda["mensagem"]
    assert "ficha de registro" in primeira["mensagem"] and "encerro a conversa" in segunda["mensagem"]
    # A terceira: o encerramento educado; a pendência continua aberta
    assert terceira["acao"] == "sem_valor" and terceira["encerrada"] is True and terceira["resolvida"] is False
    fala = terceira["mensagem"]
    assert fala.startswith("Obrigado pela ajuda até aqui.") and "a pendência continua aberta" in fala
    assert 'a informação "CPF" de Caio, que veio "' in fala
    assert "Revise essa informação no arquivo, ou com o funcionário, e envie o arquivo de novo." in fala
    assert "!" not in fala
    # Nada mudou no cadastro
    assert correcoes.listar(conexao, envio) == []
    assert achados_da_linha(conexao, envio, LINHA_DO_CAIO) == [("CPF_INVALIDO", "cpf")]


def test_o_encerramento_fica_marcado_na_conversa_e_a_conta_recomeca(conexao, envio):
    for resposta_sem_valor in ("não sei", "não sei", "não sei"):
        ultima = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", resposta_sem_valor)
    assert ultima["encerrada"] is True
    chave = ultima["chave"]
    # Os balões do agente guardam as marcas: três respostas sem valor, a última encerrou
    marcas = []
    for balao in conversas_das_pendencias.conversas_do_envio(conexao, envio)[chave]["baloes"]:
        if balao["quem"] == "ia" and not balao["pergunta"]:
            marcas.append((balao["sem_valor"], balao["encerrada"]))
    assert marcas == [(True, False), (True, False), (True, True)]
    # Depois do encerramento, a conta recomeça: a próxima resposta sem valor ajuda de novo, sem encerrar
    assert conversas_das_pendencias.respostas_sem_valor_desde_o_encerramento(conexao, envio, chave) == 0
    de_novo = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "não sei")
    assert de_novo["encerrada"] is False and "ficha de registro" in de_novo["mensagem"]


def test_a_recusa_de_um_valor_nao_conta_como_resposta_sem_valor(conexao, envio):
    respostas = []
    for mensagem in ("não sei", "C900", "não tenho", "sei lá"):
        respostas.append(conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", mensagem))
    # O "C900" foi recusado pela padronização (e não conta); a 3ª resposta sem valor é a que encerra
    assert respostas[1]["mensagem"].startswith("Esse CPF não confere")
    encerradas = []
    for resposta in respostas:
        encerradas.append(resposta["encerrada"])
    assert encerradas == [False, False, False, True]


def test_um_valor_certo_depois_do_nao_sei_resolve(conexao, envio):
    conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "não sei")
    conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "não tenho")
    resposta = conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", "achei: " + CPF_DO_CAIO_CERTO)
    assert resposta["mensagem"].startswith("Pronto:") and resposta["resolvida"] is True


def test_a_ia_que_so_pergunta_de_novo_tambem_chega_ao_limite(conexao, envio):
    # Uma IA real que não seguiu o prompt: para "não sei", ela só pergunta de novo, sem o dado
    ia = ia_que_responde(acao="responder", mensagem="Qual é o valor certo?")
    respostas = []
    for mensagem in ("não sei", "Não sei.", "não sei mesmo"):
        respostas.append(conversar(conexao, envio, "CPF_INVALIDO", LINHA_DO_CAIO, "cpf", mensagem, cliente=ia))
    # A trava do código: as três contam como respostas sem valor, e a terceira encerra
    assert respostas[0]["acao"] == "sem_valor" and respostas[0]["mensagem"].startswith("No arquivo, ")
    assert respostas[2]["encerrada"] is True and respostas[2]["mensagem"].startswith("Obrigado pela ajuda")


def test_o_encerramento_no_dado_que_veio_vazio(conexao, envio):
    for mensagem in ("não sei", "não sei", "não sei"):
        ultima = conversar(conexao, envio, "OBRIGATORIO_VAZIO", LINHA_DA_ANA, "codigo_cbo", mensagem)
    assert ultima["encerrada"] is True and "de Ana, que veio vazia no arquivo, ainda precisa ser conferida" in \
        ultima["mensagem"]


# ---------------- O agente: a ação nova e a IA simulada ----------------

@pytest.mark.parametrize("mensagem, esperado", [
    ("não sei", True), ("Prefiro não informar.", True), ("sei lá", True), ("não temos essa informação", True),
    ("não sei, acho que é 4110-10", False),   # traz um valor
    ("não sei o que é CBO?", False),           # é uma pergunta
    ("o certo é 529.982.247-25", False),       # é um valor
])
def test_a_resposta_sem_valor_e_reconhecida(mensagem, esperado):
    assert assistente_correcao.e_resposta_sem_valor(mensagem) is esperado


def test_a_resposta_sem_valor_nunca_leva_um_valor():
    # O modelo pôs um valor por engano numa resposta sem valor: a decisão sai sem ele
    acao = assistente_correcao.AcaoAssistente(acao="sem_valor", mensagem="Tudo bem.", valor="C900")
    decisao = assistente_correcao._decidir(None, "envio", EMPRESA, {"regra_id": "OBRIGATORIO_VAZIO", "linha": 2,
                                                                    "campo": "codigo_cbo"}, acao, [], [])
    assert decisao.acao == "sem_valor" and decisao.valor is None


def test_o_prompt_novo_e_o_padrao():
    assert assistente_correcao.VERSAO_PROMPT == "assistente_correcao_v4"
    sistema = assistente_correcao._sistema()
    assert '"sem_valor"' in sistema and "valor_na_tela" in sistema and "única por funcionário" in sistema


# ---------------- A rota ----------------

def test_a_rota_da_conversa_devolve_encerrada(api_do_assistente):  # noqa: F811
    processamento_id, pendencia = api_do_assistente
    endereco = "/api/empresa/cadastro/" + processamento_id + "/assistente"
    navegador = entrar("rh.aurora")
    respostas = []
    for mensagem in ("não sei", "não tenho", "prefiro não informar"):
        pedido = {"regra_id": "CPF_INVALIDO", "linha": pendencia["linha"], "mensagem": mensagem}
        respostas.append(navegador.post(endereco, json=pedido))
    for resposta in respostas:
        assert resposta.status_code == 200
    assert respostas[0].json()["encerrada"] is False and respostas[2].json()["encerrada"] is True
