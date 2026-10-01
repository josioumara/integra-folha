"""Testes do "a matrícula é o CPF": a informação que o arquivo inteiro não trouxe está em outra coluna (ADR-124).

O defeito: no cartão "o arquivo não trouxe o CPF", a resposta "Na verdade o campo matrícula é o CPF" recebia "Aqui eu só
ajusto a informação CPF" (a conversa só podia tratar a coluna do próprio campo, e o CPF não tinha coluna).

O que estes testes provam (com a IA simulada, sem custo):
- a conferência da coluna usa as regras do campo, com o dígito verificador no CPF, e diz em que campo ela está hoje;
- "a matrícula é o CPF" (pelo campo) e "a coluna Registro é o CPF" (pelo nome) viram a proposta de usar a coluna,
  com os números da conferência e o aviso de que a matrícula fica sem coluna; nada muda antes do "Sim";
- a coluna que não parece CPF (a maioria não passa) não é oferecida, e a conversa lembra os outros caminhos;
- "Sim, usar como CPF" troca a coluna e refaz a leitura: o cartão do CPF sai, a matrícula ganha um cartão de revisão, a
  trilha registra a troca (sem valores) e o Desfazer volta tudo; "Cancelar" não muda nada;
- a trava: indicar outra coluna só vale no cartão da informação que o arquivo inteiro não trouxe;
- a rota: 401 sem login, 404 para outra empresa, 200 para a empresa dona.
"""
import pytest
from fastapi.testclient import TestClient

from agents import assistente_correcao
from api.principal import aplicacao
from models.contratos import Perfil
from services import (assistente_na_tela, auditoria, auth, cadastro, coluna_do_campo_que_falta, correcoes, mapeamentos,
                      validador)
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import EMPRESA, LOGIN, conexao, cpf_valido, usar_busca_falsa  # noqa: F401

# As colunas do arquivo e o campo de cada uma no aceite: a empresa pôs a coluna "Registro" (os CPFs) na matrícula
ESCOLHAS = {"Nome": "nome_completo", "Registro": "matricula", "Estado civil": "estado_civil"}
# A regra da coluna que o arquivo inteiro não trouxe
SEM_COLUNA = "OBRIGATORIO_SEM_COLUNA"
# Os CPFs da coluna "Registro" (válidos e inventados)
CPFS = [cpf_valido("529982247"), cpf_valido("111444777"), cpf_valido("123456789")]
# Senha dos usuários de teste da rota
SENHA_DE_TESTE = "senha-de-teste-123"


def arquivo_com_registro(registros: list[str]) -> bytes:
    """Três pessoas com o nome, o "Registro" (o valor de cada uma) e o estado civil; nenhuma coluna de CPF."""
    linhas = ["Nome;Registro;Estado civil"]
    for nome, registro in zip(["Ana Lima", "Bia Souza", "Caio Reis"], registros):
        linhas.append(f"{nome};{registro};Casado")
    return ("\n".join(linhas) + "\n").encode("utf-8")


def enviar(conexao, registros: list[str]) -> str:
    """O arquivo enviado e aceito pela Aurora (a padronização e a validação rodam no aceite). Devolve o envio."""
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, arquivo_com_registro(registros), "registro.csv",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS, busca=busca_falsa)
    return leitura["processamento_id"]


@pytest.fixture
def envio(conexao) -> str:
    """O envio em que a coluna "Registro" traz os CPFs, mas foi aceita como a matrícula."""
    return enviar(conexao, CPFS)


def sem_coluna_em_aberto(conexao, envio: str, campo: str) -> bool:
    """True se a pendência "o arquivo inteiro não trouxe esta coluna" do campo está no relatório."""
    for achado in validador.obter(conexao, envio).achados:
        if achado.regra_id == SEM_COLUNA and achado.campo == campo:
            return True
    return False


def conversar_no_cartao_do_cpf(conexao, envio: str, mensagem: str) -> dict:
    """Uma mensagem no cartão "o arquivo não trouxe o CPF"."""
    return assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, SEM_COLUNA, None, mensagem, campo="cpf")


# ---------------- A conferência da coluna ----------------

def test_a_conferencia_da_coluna_olha_o_digito_do_cpf(conexao):
    # Um dos três com o dígito errado: a maioria ainda passa
    envio = enviar(conexao, [CPFS[0], CPFS[1], "12345678900"])
    conferencia = coluna_do_campo_que_falta.conferir(conexao, envio, "Registro", "cpf")
    assert conferencia["campo_de_hoje"] == "matricula" and conferencia["com_digito"] is True
    assert (conferencia["preenchidos"], conferencia["validos"], conferencia["maioria"]) == (3, 2, True)
    assert conferencia["exemplos"][0] == {"valor": "12345678900", "motivo": "o dígito verificador não confere"}
    with pytest.raises(ValueError, match="Não achei a coluna"):
        coluna_do_campo_que_falta.conferir(conexao, envio, "Coluna que não existe", "cpf")


# ---------------- A proposta, pela conversa ----------------

def test_a_matricula_e_o_cpf_vira_a_proposta_sem_mudar_nada(conexao, envio):
    resposta = conversar_no_cartao_do_cpf(conexao, envio, "Na verdade o campo matrícula é o CPF")
    # Antes, "fora do assunto"; agora, a conferência e a pergunta
    assert resposta["acao"] == "usar_coluna" and resposta["recusado"] is False
    assert 'Conferi a coluna "Registro" (hoje lida como "Matrícula")' in resposta["mensagem"]
    assert "com o dígito verificador: 3 de 3 valores passaram" in resposta["mensagem"]
    # A matrícula é opcional (ADR-128): fica sem coluna, sem cartão de revisão
    assert 'Com a troca, "Matrícula" fica sem coluna. Confirma' in resposta["mensagem"]
    confirmacao = resposta["confirmacao"]
    assert (confirmacao["tipo"], confirmacao["coluna"], confirmacao["campo"]) == ("coluna", "Registro", "cpf")
    assert confirmacao["sim"] == "Sim, usar como CPF"
    # Nada muda antes do "Sim"
    assert coluna_do_campo_que_falta.campo_de_hoje_da_coluna(conexao, envio, "Registro") == "matricula"
    assert sem_coluna_em_aberto(conexao, envio, "cpf")


def test_a_coluna_pelo_nome_tambem_vira_a_proposta(conexao, envio):
    resposta = conversar_no_cartao_do_cpf(conexao, envio, "A coluna Registro é o CPF")
    assert resposta["acao"] == "usar_coluna" and resposta["confirmacao"]["coluna"] == "Registro"


def test_a_coluna_que_nao_parece_cpf_nao_e_oferecida(conexao):
    envio = enviar(conexao, ["00101", "00102", "00103"])
    resposta = conversar_no_cartao_do_cpf(conexao, envio, "Na verdade o campo matrícula é o CPF")
    assert resposta["confirmacao"] is None and resposta["aplicado"] is None
    assert "0 de 3 valores passaram" in resposta["mensagem"]
    assert 'Ela não parece ser a informação "CPF", então nada mudou.' in resposta["mensagem"]
    assert "Informar pessoa a pessoa" in resposta["mensagem"]
    assert coluna_do_campo_que_falta.campo_de_hoje_da_coluna(conexao, envio, "Registro") == "matricula"


# ---------------- A confirmação e o Desfazer ----------------

def test_sim_troca_a_coluna_refaz_a_leitura_e_o_desfazer_volta(conexao, envio):
    conversar_no_cartao_do_cpf(conexao, envio, "Na verdade o campo matrícula é o CPF")
    resposta = assistente_na_tela.confirmar_coluna(conexao, EMPRESA, LOGIN, envio, "cpf", "Registro", True)
    # A matrícula é opcional (ADR-128): fica sem coluna, sem cartão de revisão
    assert resposta["mensagem"] == ('Pronto: a coluna "Registro" agora é a informação "CPF" (3 de 3 valores '
                                    'passaram). "Matrícula" ficou sem coluna.')
    assert resposta["resolvida"] is True
    # A leitura refeita: o CPF de cada pessoa veio da coluna; a matrícula ficou sem coluna (é opcional: sem cartão)
    for registro in correcoes.dados_atuais(conexao, envio).registros:
        assert registro["cpf"] in CPFS and registro["matricula"] is None
    assert not sem_coluna_em_aberto(conexao, envio, "cpf") and not sem_coluna_em_aberto(conexao, envio, "matricula")
    assert mapeamentos.obter(conexao, envio)[1] == "APROVADO"
    # Na trilha, a troca, sem valores
    trocas = []
    for evento in auditoria.eventos(conexao, envio):
        if evento["tipo"] == "COLUNA_TROCADA_NA_CONVERSA":
            trocas.append((evento["detalhe"]["coluna"], evento["detalhe"]["antes"], evento["detalhe"]["depois"]))
    assert trocas == [("Registro", "matricula", "cpf")]
    # O Desfazer volta a coluna para a matrícula, e o cartão do CPF reaparece
    desfazer = resposta["aplicado"]["desfazer"]
    assert desfazer == {"tipo": "coluna", "id": "Registro|matricula"}
    desfeito = assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, desfazer["tipo"], desfazer["id"])
    assert desfeito["resumo"] == 'Voltei a coluna "Registro" para "Matrícula".'
    assert coluna_do_campo_que_falta.campo_de_hoje_da_coluna(conexao, envio, "Registro") == "matricula"
    assert sem_coluna_em_aberto(conexao, envio, "cpf") and not sem_coluna_em_aberto(conexao, envio, "matricula")


def test_cancelar_nao_muda_nada(conexao, envio):
    conversar_no_cartao_do_cpf(conexao, envio, "Na verdade o campo matrícula é o CPF")
    resposta = assistente_na_tela.confirmar_coluna(conexao, EMPRESA, LOGIN, envio, "cpf", "Registro", False)
    # A posição da resposta na conversa (a do joinha, ADR-151): a pergunta, a fala, a confirmação, a escolha e ela
    assert resposta == {"mensagem": "Tudo bem, nada mudou.", "aplicado": None, "resolvida": False, "ordem": 4}
    assert coluna_do_campo_que_falta.campo_de_hoje_da_coluna(conexao, envio, "Registro") == "matricula"
    assert sem_coluna_em_aberto(conexao, envio, "cpf")


def test_a_trava_so_deixa_indicar_coluna_na_informacao_que_faltou():
    acao = assistente_correcao.AcaoAssistente(acao="usar_coluna", mensagem="...", coluna="Registro")
    no_cpf_invalido = {"regra_id": "CPF_INVALIDO", "campo": "cpf", "linha": 2}
    na_coluna_que_faltou = {"regra_id": SEM_COLUNA, "campo": "cpf", "linha": None}
    assert assistente_correcao._fora_da_pendencia(no_cpf_invalido, acao, []) is True
    assert assistente_correcao._fora_da_pendencia(na_coluna_que_faltou, acao, []) is False


# ---------------- A rota ----------------

@pytest.fixture
def api_da_coluna(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com o envio da coluna "Registro". Devolve o envio."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    processamento_id = enviar(conexao_do_teste, CPFS)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    conexao_do_teste.close()
    return processamento_id


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_a_rota_da_coluna_e_so_da_empresa_dona_do_envio(api_da_coluna):
    endereco = f"/api/empresa/cadastro/{api_da_coluna}/assistente/usar_coluna"
    corpo = {"campo": "cpf", "coluna": "Registro", "confirmar": True}
    assert TestClient(aplicacao).post(endereco, json=corpo).status_code == 401
    assert entrar("rh.brisa").post(endereco, json=corpo).status_code == 404
    resposta = entrar("rh.aurora").post(endereco, json=corpo)
    assert resposta.status_code == 200 and resposta.json()["resolvida"] is True
