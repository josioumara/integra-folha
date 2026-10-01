"""Roteiro: a tela de login, sem o antigo "Lembrar de mim", que não funcionava e saiu. Antes, este roteiro se
chamava lembrar_de_mim.

O que ele confere:
- a tela de login não tem mais a caixa "Lembrar de mim";
- "Esqueci minha senha" abre uma janela que explica o caminho (pedir uma senha provisória nova ao especialista do
  banco), sem pôr "#" no endereço; "Entendi" e o Esc fecham, e o foco volta ao link;
- o usuário que o antigo "Lembrar de mim" guardou no navegador é apagado ao abrir a tela (o campo vem vazio);
- o cookie da sessão some ao fechar o navegador (cookie de sessão, sem data de validade);
- a tela de login não cita o Santander, e depois do login aparece o selo "Banco parceiro: Santander";
- a nota de que o site é um projeto aparece no rodapé;
- o primeiro acesso e a senha esquecida levam ao especialista do banco que cuida da empresa;
- a senha provisória vencida (mais de 48 horas, ADR-154) é recusada com o aviso, e a pessoa fica no login.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, SENHA_DE_TESTE

DESCRICAO = ("Login sem o 'Lembrar de mim' e cookie de sessão; janela do 'Esqueci minha senha'; login sem Santander; "
             "selo e nota do projeto; o texto do primeiro acesso; a senha provisória vencida")

# Onde o antigo "Lembrar de mim" guardava o usuário no navegador (o mesmo nome de front/js/login.js)
CHAVE_DO_ANTIGO_USUARIO_LEMBRADO = "integra_folha_usuario_lembrado"
# Uma pessoa da Aurora com a senha provisória gerada há 49 horas (só existe no banco temporário do roteiro)
LOGIN_COM_A_SENHA_VENCIDA = "rh.vencida@aurora.com.br"
SENHA_PROVISORIA_VENCIDA = "provisoria-vencida-49h"


def preparar() -> dict:
    """Os usuários de teste e uma pessoa com a senha provisória vencida."""
    from datetime import datetime, timedelta, timezone

    from models.contratos import Perfil
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # A senha provisória gerada há 49 horas: a hora é gravada direto no banco temporário
    auth.cadastrar_usuario(conexao, LOGIN_COM_A_SENHA_VENCIDA, SENHA_PROVISORIA_VENCIDA, Perfil.EMPRESA, "EMP001",
                           senha_provisoria=True)
    hora = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(timespec="seconds")
    conexao.execute("UPDATE usuarios SET senha_provisoria_gerada_em = ? WHERE login = ?",
                    (hora, LOGIN_COM_A_SENHA_VENCIDA))
    conexao.commit()
    conexao.close()
    return {}


def cookie_da_sessao(aba) -> dict:
    """O cookie da sessão guardado no navegador."""
    for cookie in aba.context.cookies():
        if cookie["name"] == "integra_folha_sessao":
            return cookie
    raise AssertionError("sem o cookie da sessão")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: abrir o login (com um usuário guardado pelo antigo "Lembrar"), entrar e conferir cookie, selo e nota."""
    aba = navegador.new_page(viewport={"width": 1440, "height": 1000})
    aba.on("pageerror", lambda erro: erros_da_pagina.append(str(erro)))
    # 1. Um navegador que marcou o antigo "Lembrar de mim": o usuário ficou guardado nele
    aba.goto(endereco + "/login.html")
    aba.evaluate("chave => window.localStorage.setItem(chave, 'usuario.antigo')", CHAVE_DO_ANTIGO_USUARIO_LEMBRADO)
    # 2. Abrir o login de novo: sem a caixa, sem Santander, e o usuário guardado some
    aba.goto(endereco + "/login.html")
    conferir("a tela de login não tem a caixa 'Lembrar de mim'",
             aba.locator("[name='lembrar']").count() == 0 and "lembrar de mim" not in aba.inner_text("body").lower())
    conferir("a tela de login não cita o Santander", "santander" not in aba.content().lower())
    guardado = aba.evaluate("chave => window.localStorage.getItem(chave)", CHAVE_DO_ANTIGO_USUARIO_LEMBRADO)
    conferir("o usuário guardado pelo antigo 'Lembrar de mim' é apagado e o campo vem vazio",
             guardado is None and aba.input_value("[name='usuario']") == "")
    conferir("o 'Esqueci minha senha' continua na tela", aba.locator("#link-esqueci-a-senha").is_visible())
    # 3. "Esqueci minha senha": abre a janela que explica o caminho, sem mudar o endereço
    endereco_antes = aba.url
    aba.click("#link-esqueci-a-senha")
    janela = aba.locator("#janela-esqueci-a-senha")
    conferir("clicar em 'Esqueci minha senha' abre a janela com o caminho",
             janela.is_visible() and "senha provisória nova ao especialista do banco" in janela.inner_text())
    conferir("o link não põe '#' no endereço", aba.url == endereco_antes)
    conferir("a janela não cita o Santander", "santander" not in janela.inner_text().lower())
    # "Entendi" fecha, e o foco volta ao link
    aba.click("#botao-entendi-a-senha")
    foco_no_link = aba.evaluate("document.activeElement && document.activeElement.id === 'link-esqueci-a-senha'")
    conferir("'Entendi' fecha a janela e o foco volta ao link", not janela.is_visible() and foco_no_link)
    # O Esc também fecha
    aba.click("#link-esqueci-a-senha")
    aba.keyboard.press("Escape")
    conferir("o Esc também fecha a janela", not janela.is_visible())
    # O primeiro acesso e a senha esquecida levam ao especialista do banco que cuida da empresa
    primeiro_acesso = " ".join(aba.inner_text(".login-primeiro-acesso").split())
    conferir(f"o texto do primeiro acesso (na tela: {primeiro_acesso})",
             primeiro_acesso == "Primeiro acesso ou esqueceu a senha? Fale com o especialista do banco que cuida do "
                                "relacionamento com a sua empresa.")
    # A senha provisória vencida: o aviso aparece, e a pessoa continua no login
    aba.fill("[name='usuario']", LOGIN_COM_A_SENHA_VENCIDA)
    aba.fill("[name='senha']", SENHA_PROVISORIA_VENCIDA)
    aba.click("button[type='submit']")
    aba.locator("#aviso-login:not([hidden])").wait_for(timeout=10000)
    aviso = aba.inner_text("#aviso-login")
    conferir(f"a senha provisória vencida é recusada com o aviso (na tela: {aviso})",
             "A sua senha provisória venceu. Peça uma nova ao especialista do banco que cuida do relacionamento com "
             "a sua empresa." in aviso and "login.html" in aba.url)
    # 4. Entrar: cookie de sessão (sem validade: some ao fechar o navegador)
    aba.fill("[name='usuario']", LOGIN_DA_EMPRESA)
    aba.fill("[name='senha']", SENHA_DE_TESTE)
    aba.click("button[type='submit']")
    aba.wait_for_url(lambda url: "login.html" not in url, timeout=20000)
    conferir("o cookie da sessão some ao fechar o navegador", cookie_da_sessao(aba)["expires"] == -1)
    # 5. Depois do login: o selo do banco parceiro e a nota do projeto
    conferir("depois do login, o selo 'Banco parceiro: Santander'",
             "Banco parceiro: Santander" in aba.inner_text(".selo-banco-parceiro"))
    conferir("a nota do projeto no rodapé", "projeto acadêmico" in aba.inner_text(".nota-do-projeto"))
    aba.close()
