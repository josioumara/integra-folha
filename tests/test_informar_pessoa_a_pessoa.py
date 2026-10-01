"""Testes do "Não é a mesma para todos" e da lista "Informar pessoa a pessoa" (ADR-124, alternativas A e B).

O caso: a empresa diz que a informação não é a mesma para todos. Os dois caminhos de correção: enviar o arquivo de
novo com a coluna, ou informar o valor de cada pessoa numa lista do cartão.

O que estes testes provam (com a IA simulada, sem custo):
- o cartão da coluna que o arquivo inteiro não trouxe oferece "Informar pessoa a pessoa" e "Descartar a leitura e
  enviar outro arquivo"; no dado da empresa, antes deles, "Não é a mesma para todos";
- "Não é a mesma para todos" não muda nada: o agente mostra os dois caminhos (antes, perguntava de novo "Qual é o
  valor para todos?");
- a lista traz cada pessoa pela LINHA do arquivo, com o nome: funciona mesmo sem o CPF no arquivo;
- salvar a lista grava um valor por pessoa, num lote com um Desfazer só, com a trilha sem valor pessoal e a conversa
  guardada; a pendência do arquivo inteiro some, e quem ficou sem valor ganha um cartão de revisão;
- o CPF informado pessoa a pessoa passa pelas regras do CPF (o mesmo CPF em duas pessoas vira pendência);
- um valor que não serve não grava nada, e a mensagem diz a linha e o nome; as outras recusas: nenhum valor, linha
  repetida, informação que já tem coluna, lista sem o campo e envio de outra empresa;
- as rotas: 200 para a empresa dona, 401 sem login, 403 para o banco, 404 para outra empresa e 400 sem o campo.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import (acompanhamento, assistente_na_tela, auditoria, auth, cadastro, conversas_das_pendencias,
                      correcoes, validador)
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import EMPRESA, LOGIN, conexao, cpf_valido, usar_busca_falsa  # noqa: F401

# As colunas do arquivo sem CPF e o campo de cada uma (o aceite da empresa)
ESCOLHAS_SEM_CPF = {"Nome": "nome_completo", "Estado civil": "estado_civil"}
# A regra da coluna que o arquivo inteiro não trouxe
SEM_COLUNA = "OBRIGATORIO_SEM_COLUNA"
# Senha dos usuários de teste da rota
SENHA_DE_TESTE = "senha-de-teste-123"


def arquivo_sem_cpf() -> bytes:
    """Três pessoas, só com o nome e o estado civil: o arquivo não traz o CPF, a unidade nem o nascimento."""
    linhas = ["Nome;Estado civil", "Ana Lima;Casado", "Bia Souza;Solteiro", "Caio Reis;Casado"]
    return ("\n".join(linhas) + "\n").encode("utf-8")


def enviar_sem_cpf(conexao) -> str:
    """O arquivo sem CPF, enviado e aceito pela Aurora (a padronização e a validação rodam no aceite).

    Devolve: o envio.
    """
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, arquivo_sem_cpf(), "sem_cpf.csv", busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS_SEM_CPF,
                                busca=busca_falsa)
    return leitura["processamento_id"]


@pytest.fixture
def envio(conexao) -> str:
    """O envio sem CPF deste teste."""
    return enviar_sem_cpf(conexao)


def linhas_por_nome(conexao, envio: str, campo: str) -> dict[str, int]:
    """A linha de cada pessoa, pela lista "Informar pessoa a pessoa" do campo. Ex.: {"Ana Lima": 2, ...}."""
    linhas = {}
    for pessoa in assistente_na_tela.pessoas_para_informar(conexao, EMPRESA, envio, campo)["pessoas"]:
        linhas[pessoa["nome"]] = pessoa["linha"]
    return linhas


def regras_da_linha(conexao, envio: str, linha: int) -> set[str]:
    """As regras com achados numa linha, no último relatório do envio."""
    regras = set()
    for achado in validador.obter(conexao, envio).achados:
        if achado.linha == linha:
            regras.add(achado.regra_id)
    return regras


def sem_coluna_em_aberto(conexao, envio: str, campo: str) -> bool:
    """True se a pendência "o arquivo inteiro não trouxe esta coluna" do campo está no relatório."""
    for achado in validador.obter(conexao, envio).achados:
        if achado.regra_id == SEM_COLUNA and achado.campo == campo:
            return True
    return False


# ---------------- A: o cartão e o "Não é a mesma para todos" ----------------

def test_o_cartao_da_coluna_que_falta_oferece_os_dois_caminhos(conexao, envio):
    textos_por_campo = {}
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == SEM_COLUNA:
            textos = []
            for sugestao in pendencia["sugestoes"]:
                textos.append(sugestao["texto"])
            textos_por_campo[pendencia["campo"]] = textos
    # O CPF é de cada pessoa: os dois caminhos
    assert textos_por_campo["cpf"] == ["Informar pessoa a pessoa", "Descartar a leitura e enviar outro arquivo"]
    # O código da unidade é da empresa: antes, "Não é a mesma para todos"
    assert textos_por_campo["codigo_unidade"] == ["Não é a mesma para todos", "Informar pessoa a pessoa",
                                                  "Descartar a leitura e enviar outro arquivo"]


def test_nao_e_a_mesma_para_todos_mostra_os_dois_caminhos_sem_mudar_nada(conexao, envio):
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, SEM_COLUNA, None,
                                            "Não é a mesma para todos", campo="codigo_unidade")
    assert resposta["acao"] == "responder" and resposta["aplicado"] is None
    assert "Informar pessoa a pessoa" in resposta["mensagem"]
    assert "Descartar a leitura e enviar outro arquivo" in resposta["mensagem"]
    # O defeito de antes: o agente perguntava de novo o valor para todos
    assert "Qual é o valor para todos" not in resposta["mensagem"]
    assert correcoes.listar(conexao, envio) == [] and sem_coluna_em_aberto(conexao, envio, "codigo_unidade")


# ---------------- B: a lista "Informar pessoa a pessoa" ----------------

def test_a_lista_traz_cada_pessoa_pela_linha_mesmo_sem_cpf(conexao, envio):
    lista = assistente_na_tela.pessoas_para_informar(conexao, EMPRESA, envio, "cpf")
    assert lista["campo"] == "cpf" and lista["informacao"] == "CPF" and lista["igual_para_todos"] is False
    nomes = []
    for pessoa in lista["pessoas"]:
        nomes.append(pessoa["nome"])
        assert isinstance(pessoa["linha"], int)
    assert nomes == ["Ana Lima", "Bia Souza", "Caio Reis"]
    # No dado da empresa, a lista diz que ele pode ser igual para todos (a tela oferece "usar nos marcados")
    assert assistente_na_tela.pessoas_para_informar(conexao, EMPRESA, envio, "codigo_unidade")["igual_para_todos"]


def test_o_cpf_pessoa_a_pessoa_resolve_e_o_desfazer_volta_tudo(conexao, envio):
    linhas = linhas_por_nome(conexao, envio, "cpf")
    cpfs = {"Ana Lima": cpf_valido("529982247"), "Bia Souza": cpf_valido("111444777"),
            "Caio Reis": cpf_valido("123456789")}
    valores = []
    for nome, cpf in cpfs.items():
        valores.append({"linha": linhas[nome], "valor": cpf})
    resposta = assistente_na_tela.informar_por_pessoa(conexao, EMPRESA, LOGIN, envio, "cpf", valores)
    # O chat diz exatamente o que mudou e em quem, com o Desfazer do lote
    assert resposta["mensagem"] == 'Pronto: informei "CPF" de 3 pessoas: Ana, Bia e Caio.'
    assert resposta["resolvida"] is True and resposta["aplicado"]["desfazer"]["tipo"] == "por_pessoa"
    assert not sem_coluna_em_aberto(conexao, envio, "cpf")
    for registro in correcoes.dados_atuais(conexao, envio).registros:
        assert registro["cpf"] == cpfs[registro["nome_completo"]]
    # Na trilha, o campo e quantos, sem o valor
    detalhes = []
    for evento in auditoria.eventos(conexao, envio):
        if evento["tipo"] == "CORRECAO_POR_PESSOA":
            detalhes.append(evento["detalhe"])
    assert detalhes == [{"campo": "cpf", "quantidade": 3}]
    # A conversa do cartão fica guardada e vai para "Resolvidas"
    chaves = set()
    for resolvida in conversas_das_pendencias.resolvidas_da_empresa(conexao, EMPRESA):
        chaves.add(resolvida["chave"])
    assert resposta["chave"] in chaves
    # O Desfazer volta as três, e o cartão do arquivo inteiro reaparece
    desfazer = resposta["aplicado"]["desfazer"]
    desfeito = assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, desfazer["tipo"], desfazer["id"])
    assert desfeito["resumo"] == "Desfiz o que foi informado: 3 pessoas sem este dado de novo."
    assert sem_coluna_em_aberto(conexao, envio, "cpf")


def test_quem_fica_sem_valor_ganha_o_seu_cartao(conexao, envio):
    linhas = linhas_por_nome(conexao, envio, "codigo_unidade")
    valores = [{"linha": linhas["Ana Lima"], "valor": "001"}, {"linha": linhas["Bia Souza"], "valor": "002"},
               {"linha": linhas["Caio Reis"], "valor": ""}]
    resposta = assistente_na_tela.informar_por_pessoa(conexao, EMPRESA, LOGIN, envio, "codigo_unidade", valores)
    assert resposta["mensagem"].endswith("1 pessoa ficou sem esta informação e ganhou um cartão de revisão.")
    # A coluna passa a contar como presente: o cartão do arquivo inteiro sai, e o Caio ganha o dele
    assert not sem_coluna_em_aberto(conexao, envio, "codigo_unidade")
    assert "OBRIGATORIO_VAZIO" in regras_da_linha(conexao, envio, linhas["Caio Reis"])
    assert "OBRIGATORIO_VAZIO" not in regras_da_linha(conexao, envio, linhas["Ana Lima"])


def test_o_mesmo_cpf_em_duas_pessoas_vira_pendencia(conexao, envio):
    linhas = linhas_por_nome(conexao, envio, "cpf")
    repetido = cpf_valido("529982247")
    valores = [{"linha": linhas["Ana Lima"], "valor": repetido}, {"linha": linhas["Bia Souza"], "valor": repetido},
               {"linha": linhas["Caio Reis"], "valor": cpf_valido("123456789")}]
    assistente_na_tela.informar_por_pessoa(conexao, EMPRESA, LOGIN, envio, "cpf", valores)
    # O CPF informado passa pelas mesmas regras de um CPF que veio no arquivo
    assert "PESSOA_DUPLICADA" in regras_da_linha(conexao, envio, linhas["Bia Souza"])
    assert "PESSOA_DUPLICADA" not in regras_da_linha(conexao, envio, linhas["Caio Reis"])


def test_um_valor_que_nao_serve_nao_grava_nada(conexao, envio):
    linhas = linhas_por_nome(conexao, envio, "data_nascimento")
    valores = [{"linha": linhas["Ana Lima"], "valor": "10/05/1990"},
               {"linha": linhas["Bia Souza"], "valor": "trinta de fevereiro"}]
    with pytest.raises(ValueError, match=f"Linha {linhas['Bia Souza']} \\(Bia Souza\\)"):
        assistente_na_tela.informar_por_pessoa(conexao, EMPRESA, LOGIN, envio, "data_nascimento", valores)
    # Nada pela metade: nem a data da Ana foi gravada
    assert correcoes.listar(conexao, envio) == [] and sem_coluna_em_aberto(conexao, envio, "data_nascimento")


def test_recusas(conexao, envio):
    linhas = linhas_por_nome(conexao, envio, "cpf")
    informar = assistente_na_tela.informar_por_pessoa
    with pytest.raises(ValueError, match="pelo menos uma pessoa"):
        informar(conexao, EMPRESA, LOGIN, envio, "cpf", [{"linha": linhas["Ana Lima"], "valor": "  "}])
    with pytest.raises(ValueError, match="duas vezes"):
        informar(conexao, EMPRESA, LOGIN, envio, "cpf", [{"linha": linhas["Ana Lima"], "valor": "1"},
                                                          {"linha": linhas["Ana Lima"], "valor": "2"}])
    # O nome veio no arquivo: não há pendência de coluna que falta para ele
    with pytest.raises(ValueError, match="não está mais em aberto"):
        informar(conexao, EMPRESA, LOGIN, envio, "nome_completo", [{"linha": linhas["Ana Lima"], "valor": "Ana"}])
    with pytest.raises(ValueError, match="Diga de qual informação"):
        assistente_na_tela.pessoas_para_informar(conexao, EMPRESA, envio, "")
    with pytest.raises(KeyError):
        informar(conexao, "EMP003", "rh.brisa", envio, "cpf", [{"linha": linhas["Ana Lima"], "valor": "1"}])
    assert correcoes.listar(conexao, envio) == []


# ---------------- As rotas ----------------

@pytest.fixture
def api_pessoa_a_pessoa(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com o envio sem CPF da Aurora. Devolve o envio."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    processamento_id = enviar_sem_cpf(conexao_do_teste)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao_do_teste.close()
    return processamento_id


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_as_rotas_sao_so_da_empresa_dona_do_envio(api_pessoa_a_pessoa):
    base = f"/api/empresa/cadastro/{api_pessoa_a_pessoa}"
    endereco_da_lista = base + "/pessoas_para_informar?campo=cpf"
    aurora = entrar("rh.aurora")
    lista = aurora.get(endereco_da_lista)
    assert lista.status_code == 200 and len(lista.json()["pessoas"]) == 3
    assert TestClient(aplicacao).get(endereco_da_lista).status_code == 401
    assert entrar("especialista").get(endereco_da_lista).status_code == 403
    assert entrar("rh.brisa").get(endereco_da_lista).status_code == 404
    assert aurora.get(base + "/pessoas_para_informar").status_code == 400
    # Salvar: a primeira pessoa com um CPF; a resposta é uma rodada da conversa do cartão
    primeira = lista.json()["pessoas"][0]["linha"]
    corpo = {"campo": "cpf", "valores": [{"linha": primeira, "valor": cpf_valido("529982247")}]}
    assert TestClient(aplicacao).post(base + "/informar_por_pessoa", json=corpo).status_code == 401
    assert entrar("rh.brisa").post(base + "/informar_por_pessoa", json=corpo).status_code == 404
    salvo = aurora.post(base + "/informar_por_pessoa", json=corpo)
    assert salvo.status_code == 200 and salvo.json()["aplicado"]["desfazer"]["tipo"] == "por_pessoa"
