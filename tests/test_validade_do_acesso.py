"""Testes da validade do acesso da empresa (ADR-146): o acesso esquecido deixa de valer sozinho.

As regras, em services/auth.py: a pessoa de empresa que não entra há mais de 90 dias, ou cujo acesso de 12 meses
venceu, recebe 403 com o motivo na tela de login. O especialista do banco nunca é suspenso por elas, e o botão
"Ativar" do banco renova o acesso.

Como o teste "passa o tempo": ele grava direto no banco de dados de teste as datas de um acesso antigo (o último
login há 91 dias, ou a validade de ontem), em vez de esperar os dias passarem.
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth

# A senha de todos os usuários deste arquivo
SENHA_DE_TESTE = "senha-de-teste-123"
# A empresa das pessoas deste arquivo
EMPRESA_DO_TESTE = "EMP001"


def cadastrar(login: str, perfil: Perfil = Perfil.EMPRESA) -> None:
    """Cadastra uma pessoa só deste teste (empresa por padrão; o banco não tem empresa)."""
    # A empresa só vale para o perfil EMPRESA
    empresa_id = EMPRESA_DO_TESTE if perfil == Perfil.EMPRESA else None
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, login, SENHA_DE_TESTE, perfil, empresa_id)
    conexao.close()


def gravar_datas(login: str, ultimo_acesso: date | None, acesso_valido_ate: date | None) -> None:
    """Grava as duas datas do acesso de alguém, como se o tempo tivesse passado."""
    # A data em texto AAAA-MM-DD, ou vazia
    texto_do_ultimo_acesso = ultimo_acesso.isoformat() if ultimo_acesso else None
    texto_da_validade = acesso_valido_ate.isoformat() if acesso_valido_ate else None
    conexao = auth.conectar()
    conexao.execute("UPDATE usuarios SET ultimo_acesso = ?, acesso_valido_ate = ? WHERE login = ?",
                    (texto_do_ultimo_acesso, texto_da_validade, login))
    conexao.commit()
    conexao.close()


def ler_datas(login: str) -> tuple[str | None, str | None]:
    """As duas datas do acesso de alguém, como estão gravadas: (último acesso, válido até)."""
    conexao = auth.conectar()
    linha = conexao.execute("SELECT ultimo_acesso, acesso_valido_ate FROM usuarios WHERE login = ?",
                            (login,)).fetchone()
    conexao.close()
    return linha[0], linha[1]


def tentar_entrar(login: str, senha: str = SENHA_DE_TESTE):
    """Tenta entrar pela tela de login (a rota /api/entrar) e devolve a resposta."""
    return TestClient(aplicacao).post("/api/entrar", json={"usuario": login, "senha": senha})


def test_empresa_sem_entrar_ha_mais_de_90_dias_e_suspensa_com_a_mensagem():
    """Caso 1: o último login foi há 91 dias → 403, e a tela mostra o motivo e o caminho (pedir ao banco)."""
    cadastrar("validade.parada")
    gravar_datas("validade.parada", date.today() - timedelta(days=91), date.today() + timedelta(days=200))
    resposta = tentar_entrar("validade.parada")
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == auth.MENSAGEM_ACESSO_PARADO


def test_empresa_com_o_acesso_vencido_nao_entra():
    """Caso 2: a validade de 12 meses acabou ontem → 403 com a mensagem do acesso vencido."""
    cadastrar("validade.vencida")
    gravar_datas("validade.vencida", date.today() - timedelta(days=10), date.today() - timedelta(days=1))
    resposta = tentar_entrar("validade.vencida")
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == auth.MENSAGEM_ACESSO_VENCIDO


def test_senha_errada_de_quem_esta_suspenso_recebe_a_mensagem_de_sempre():
    """Caso 3: com a senha errada, a resposta é a de sempre (401): quem não sabe a senha não descobre a suspensão."""
    cadastrar("validade.sigilo")
    gravar_datas("validade.sigilo", date.today() - timedelta(days=91), None)
    resposta = tentar_entrar("validade.sigilo", senha="senha-errada-999")
    assert resposta.status_code == 401
    assert resposta.json()["detail"] != auth.MENSAGEM_ACESSO_PARADO


def test_especialista_do_banco_nunca_e_suspenso_por_estas_regras():
    """Caso 4: o especialista do banco parado há 91 dias e com a data vencida entra normalmente."""
    cadastrar("validade.banco", Perfil.BANCO)
    gravar_datas("validade.banco", date.today() - timedelta(days=91), date.today() - timedelta(days=1))
    resposta = tentar_entrar("validade.banco")
    assert resposta.status_code == 200


def usuario_na_lista_do_banco(especialista: TestClient, login: str) -> dict:
    """A pessoa como a tela de empresas do banco a recebe (a rota que a aba Empresas usa)."""
    for empresa in especialista.get("/api/banco/empresas").json():
        for usuario in empresa["usuarios"]:
            if usuario["login"] == login:
                return usuario
    raise AssertionError(f"{login} não está na lista do banco")


def test_o_banco_ve_a_suspensao_e_o_reativar_renova_o_acesso():
    """Caso 5: a tela do banco mostra a pessoa suspensa; o botão "Reativar" (a mesma rota da tela) renova o acesso,
    e ela volta a entrar com mais 12 meses de validade."""
    cadastrar("validade.reativada")
    gravar_datas("validade.reativada", date.today() - timedelta(days=120), date.today() - timedelta(days=5))
    # Suspensa antes de reativar
    assert tentar_entrar("validade.reativada").status_code == 403
    # O especialista entra e vê a suspensão na lista (a marca "ativo" continua, por isso a tela precisa do tipo)
    cadastrar("validade.especialista", Perfil.BANCO)
    especialista = TestClient(aplicacao)
    assert especialista.post("/api/entrar", json={"usuario": "validade.especialista",
                                                  "senha": SENHA_DE_TESTE}).status_code == 200
    pessoa = usuario_na_lista_do_banco(especialista, "validade.reativada")
    assert pessoa["ativo"] is True and pessoa["suspensao"] == auth.SUSPENSAO_POR_VALIDADE
    # Clica em "Reativar": a tela manda ativo = verdadeiro para a pessoa suspensa
    reativar = especialista.post("/api/banco/empresas/usuarios/validade.reativada/situacao", json={"ativo": True})
    assert reativar.status_code == 200
    # A lista não mostra mais a suspensão
    assert usuario_na_lista_do_banco(especialista, "validade.reativada")["suspensao"] is None
    # Agora entra, e as datas mostram o acesso de hoje e a validade renovada
    assert tentar_entrar("validade.reativada").status_code == 200
    ultimo_acesso, acesso_valido_ate = ler_datas("validade.reativada")
    assert ultimo_acesso == date.today().isoformat()
    assert acesso_valido_ate == (date.today() + timedelta(days=auth.DIAS_DE_VALIDADE_DO_ACESSO)).isoformat()


def test_a_tela_do_banco_mostra_a_senha_resetada_ate_a_pessoa_cadastrar_outra():
    """Caso 6: o banco gera a senha provisória → a lista marca "senha resetada"; a pessoa entra com ela e cadastra a
    própria → a marca some (antes, nada mudava na tela depois do reset)."""
    cadastrar("validade.resetada")
    cadastrar("validade.especialista.reset", Perfil.BANCO)
    especialista = TestClient(aplicacao)
    assert especialista.post("/api/entrar", json={"usuario": "validade.especialista.reset",
                                                  "senha": SENHA_DE_TESTE}).status_code == 200
    # Antes do reset: sem a marca
    assert usuario_na_lista_do_banco(especialista, "validade.resetada")["senha_provisoria"] is False
    # O banco gera a senha provisória (a tela mostra a senha uma vez)
    reset = especialista.post("/api/banco/empresas/usuarios/validade.resetada/nova-senha", json={})
    assert reset.status_code == 200
    senha_provisoria = reset.json()["senha_provisoria"]
    # A lista marca a pessoa
    assert usuario_na_lista_do_banco(especialista, "validade.resetada")["senha_provisoria"] is True
    # A pessoa entra com a provisória e cadastra a própria senha
    pessoa = TestClient(aplicacao)
    entrada = pessoa.post("/api/entrar", json={"usuario": "validade.resetada", "senha": senha_provisoria})
    assert entrada.status_code == 200
    troca = pessoa.post("/api/minha-senha", json={"senha_atual": senha_provisoria,
                                                  "nova_senha": "senha-nova-da-pessoa-1",
                                                  "confirmacao": "senha-nova-da-pessoa-1"})
    assert troca.status_code == 200
    # A marca sumiu da lista do banco
    assert usuario_na_lista_do_banco(especialista, "validade.resetada")["senha_provisoria"] is False
