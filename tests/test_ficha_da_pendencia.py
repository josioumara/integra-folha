"""Testes do título do cartão e da ficha completa aberta pelo cartão da pendência (ADR-120).

O que estes testes provam (sem IA):
- o título diz o que fazer, a informação e de quem: pessoa, arquivo inteiro, formato da coluna, grupo, alerta
  ("Conferir") e valor fora da lista (sempre "Ajuste");
- cada pendência de Acompanhar e da conferência do Cadastrar traz o título, e o grupo também;
- a ficha traz os campos considerados (os que têm coluna no arquivo), agrupados pelo parâmetro, com o valor já
  corrigido, e marca o campo com pendência e o que veio no arquivo; a abertura fica registrada;
- linha que não está no envio: recusada; envio de outra empresa: KeyError (404 na rota);
- a rota: 401 sem login, 403 para o banco, 404 para outra empresa.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, auth, cadastro, ficha_da_pendencia
from tests.apoio_do_parametro import marcar_como_obrigatorios
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import (EMPRESA, ESCOLHAS_DO_ARQUIVO, LOGIN, arquivo_com_casdo,  # noqa: F401
                                            conexao, envio, usar_busca_falsa)

# Senha dos usuários de teste da rota
SENHA_DE_TESTE = "senha-de-teste-123"


# ---------------- O título do cartão ----------------

def test_o_titulo_diz_o_que_fazer_a_informacao_e_de_quem():
    titulo = acompanhamento.titulo_do_cartao
    assert titulo("CPF_INVALIDO", "cpf", "corrigir", "Ana Lima", "CPF do funcionário") == \
        'Ajuste na informação "CPF" de Ana Lima'
    assert titulo("RENDA_FORA_DO_CARGO", "valor_renda", "confirmar", "Ana Lima", "Valor da renda") == \
        'Conferir a informação "Valor da renda" de Ana Lima'
    # O valor fora da lista não se confirma: é sempre "Ajuste", mesmo num alerta
    assert titulo("VALOR_NAO_CONVERTIDO", "estado_civil", "confirmar", "Ana Lima", "Estado civil do funcionário") == \
        'Ajuste na informação "Estado civil" de Ana Lima'
    assert titulo("OBRIGATORIO_SEM_COLUNA", "codigo_unidade", "corrigir", "Arquivo inteiro",
                  "Código da unidade (filial) onde o funcionário trabalha") == \
        'Ajuste na informação "Código da unidade onde o funcionário trabalha" no arquivo inteiro'
    assert titulo("DATA_AMBIGUA", "data_admissao", "corrigir", "Arquivo inteiro", None, "Admissão") == \
        'Ajuste no formato da coluna "Admissão" no arquivo inteiro'
    assert titulo("VALOR_NAO_CONVERTIDO", "estado_civil", "corrigir", None, "Estado civil", quantidade=4) == \
        'Ajuste na informação "Estado civil" de 4 pessoas'
    assert titulo("PESSOA_DUPLICADA", None, "corrigir", "Ana Lima", None) == "Ajuste no cadastro de Ana Lima"
    assert titulo("CONFERENCIA_DE_TOTAIS", None, "corrigir", "Arquivo inteiro", None) == "Ajuste no arquivo inteiro"


def test_as_pendencias_e_o_grupo_trazem_o_titulo(conexao, envio):
    titulos = set()
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        assert pendencia["titulo_do_cartao"]
        titulos.add(pendencia["titulo_do_cartao"])
        if pendencia["grupo"]:
            assert pendencia["grupo"]["titulo_do_cartao"] == 'Ajuste na informação "Estado civil" de 3 pessoas'
    assert 'Ajuste na informação "Estado civil" de Davi Melo' in titulos
    # Na conferência do Cadastrar, o mesmo título
    lista = cadastro.lista_para_conferir(conexao, EMPRESA, envio)
    titulos_da_conferencia = set()
    for linha in lista["linhas"]:
        for pendencia in linha["pendencias"]:
            titulos_da_conferencia.add(pendencia["titulo_do_cartao"])
    assert 'Ajuste na informação "Estado civil" de Davi Melo' in titulos_da_conferencia


# ---------------- A ficha ----------------

def linha_de(conexao, nome: str) -> int:
    """A linha do arquivo da pessoa, pela lista de pendências."""
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["nome"] == nome:
            return pendencia["linha"]
    raise AssertionError(f"{nome} devia ter pendência")


def campos_da_ficha(ficha: dict) -> dict:
    """Os campos da ficha pelo nome técnico."""
    campos = {}
    for grupo in ficha["grupos"]:
        for campo in grupo["campos"]:
            campos[campo["campo"]] = campo
    return campos


def test_a_ficha_traz_os_campos_considerados_e_marca_o_da_pendencia(conexao, envio):
    linha = linha_de(conexao, "Davi Melo")
    ficha = ficha_da_pendencia.ficha_da_linha(conexao, EMPRESA, LOGIN, envio, linha)
    assert ficha["linha"] == linha and ficha["nome"] == "Davi Melo"
    campos = campos_da_ficha(ficha)
    # Os campos que têm coluna no arquivo, e só eles
    assert set(campos) == {"nome_completo", "cpf", "estado_civil"}
    assert campos["cpf"]["valor"] == "987.654.321-00" and campos["cpf"]["com_pendencia"] is False
    # O campo em revisão: com pendência, sem valor ainda e com o que veio no arquivo
    assert campos["estado_civil"]["com_pendencia"] is True and campos["estado_civil"]["valor"] == ""
    assert campos["estado_civil"]["valor_lido"] == "Noiva" and campos["estado_civil"]["nome"] == "Estado civil"
    # A abertura fica registrada
    acessos = acompanhamento.acessos_da_empresa(conexao, EMPRESA)
    assert acessos and acessos[0]["tipo"] == acompanhamento.ACESSO_FICHA


def test_a_ficha_mostra_o_valor_ja_corrigido(conexao, envio):
    from services import assistente_na_tela
    linha = linha_de(conexao, "Davi Melo")
    assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, "VALOR_NAO_CONVERTIDO", linha, "Solteiro")
    campos = campos_da_ficha(ficha_da_pendencia.ficha_da_linha(conexao, EMPRESA, LOGIN, envio, linha))
    assert campos["estado_civil"]["valor"] == "Solteiro" and campos["estado_civil"]["com_pendencia"] is False
    assert campos["estado_civil"]["valor_lido"] is None


def test_a_ficha_recusa_linha_fora_do_envio_e_envio_de_outra_empresa(conexao, envio):
    with pytest.raises(ValueError, match="não está neste envio"):
        ficha_da_pendencia.ficha_da_linha(conexao, EMPRESA, LOGIN, envio, 999)
    with pytest.raises(KeyError):
        ficha_da_pendencia.ficha_da_linha(conexao, "EMP003", "rh.brisa", envio, 2)


# ---------------- A rota ----------------

@pytest.fixture
def api_da_ficha(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com o envio da Aurora. Devolve (envio, linha do Davi)."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    # O estado civil é opcional no layout: o parâmetro deste teste o marca como obrigatório (ADR-143)
    marcar_como_obrigatorios(conexao_do_teste, "estado_civil")
    leitura = cadastro.enviar_arquivo(conexao_do_teste, EMPRESA, LOGIN, arquivo_com_casdo(), "estado_civil.csv",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao_do_teste, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS_DO_ARQUIVO,
                                busca=busca_falsa)
    linha = linha_de(conexao_do_teste, "Davi Melo")
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao_do_teste.close()
    return leitura["processamento_id"], linha


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_a_rota_da_ficha_e_so_da_empresa_dona_do_envio(api_da_ficha):
    processamento_id, linha = api_da_ficha
    endereco = f"/api/empresa/cadastro/{processamento_id}/ficha?linha={linha}"
    resposta = entrar("rh.aurora").get(endereco)
    assert resposta.status_code == 200 and resposta.json()["nome"] == "Davi Melo"
    assert TestClient(aplicacao).get(endereco).status_code == 401
    assert entrar("especialista").get(endereco).status_code == 403
    assert entrar("rh.brisa").get(endereco).status_code == 404
    assert entrar("rh.aurora").get(f"/api/empresa/cadastro/{processamento_id}/ficha?linha=999").status_code == 400


# ---------------- Um cartão, um problema (ADR-120) ----------------

def test_cpf_invalido_e_pessoa_em_outro_arquivo_sao_cartoes_bem_diferentes():
    """A mesma pessoa com o CPF errado e também em outro arquivo: os dois problemas ficam presos ao CPF no Validador,
    mas são dois cartões com títulos e problemas diferentes (antes, os dois se chamavam
    'Ajuste na informação "CPF"')."""
    titulo = acompanhamento.titulo_do_cartao
    do_cpf = titulo("CPF_INVALIDO", "cpf", "corrigir", "Ana Lima", "CPF do funcionário")
    do_outro_arquivo = titulo("PESSOA_EM_OUTRO_ENVIO", "cpf", "corrigir", "Ana Lima", "CPF do funcionário")
    repetida = titulo("PESSOA_DUPLICADA", "cpf", "corrigir", "Ana Lima", "CPF do funcionário")
    assert do_cpf == 'Ajuste na informação "CPF" de Ana Lima'
    assert do_outro_arquivo == "Ajuste no cadastro de Ana Lima" and repetida == "Ajuste no cadastro de Ana Lima"
    # O problema de cada um: curto, só dele
    problema = acompanhamento.problema_do_cartao
    assert problema("CPF_INVALIDO", "CPF com dígito verificador inválido.") == "CPF com o dígito verificador errado"
    assert problema("PESSOA_EM_OUTRO_ENVIO", "Esta pessoa também está em outro envio que ainda não foi cadastrado "
                    "(arquivo folha_set.xlsx).") == \
        'a pessoa também está em outro arquivo que ainda não foi ao banco ("folha_set.xlsx")'
    assert problema("PESSOA_DUPLICADA", "O mesmo CPF já aparece na linha 7.") == \
        "a mesma pessoa aparece duas vezes neste arquivo (a outra é a linha 7)"
    assert problema("PERGUNTA_DA_IA:cpf", "O CPF está ilegível?") == "Dúvida dos agentes ao ler o documento"
    assert problema("REGRA_NOVA", "Algo diferente.") == "Algo diferente"


def test_a_ia_nao_recebe_o_cpf_na_pendencia_da_pessoa_em_outro_arquivo():
    """Para a pergunta não misturar "o CPF veio errado" com "está em outro arquivo", a IA recebe só o problema."""
    from types import SimpleNamespace
    achado = SimpleNamespace(regra_id="PESSOA_EM_OUTRO_ENVIO", campo="cpf", linha=5, valor="52998224725",
                             severidade="BLOQUEANTE",
                             mensagem="Esta pessoa também está em outro envio que ainda não foi cadastrado "
                                      "(arquivo folha_set.xlsx).")
    dados = acompanhamento.pendencia_para_escrever(achado, "corrigir", "529.982.247-25", "Ana Lima", None,
                                                   "CPF do funcionário")
    assert dados.valor_lido == "" and dados.informacao == "" and "529" not in str(dados)
    # No CPF inválido, a IA recebe o CPF lido (é dele que o cartão trata)
    achado.regra_id = "CPF_INVALIDO"
    dados_do_cpf = acompanhamento.pendencia_para_escrever(achado, "corrigir", "529.982.247-25", "Ana Lima", None,
                                                          "CPF do funcionário")
    assert dados_do_cpf.valor_lido == "529.982.247-25" and dados_do_cpf.informacao == "CPF"


def test_cada_pendencia_da_lista_traz_o_seu_problema(conexao, envio):
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        assert pendencia["problema_do_cartao"]
        if pendencia["grupo"]:
            assert pendencia["grupo"]["problema_do_cartao"] == "valor que o sistema não reconheceu"
    lista = cadastro.lista_para_conferir(conexao, EMPRESA, envio)
    for linha in lista["linhas"]:
        for pendencia in linha["pendencias"]:
            assert pendencia["problema_do_cartao"]
