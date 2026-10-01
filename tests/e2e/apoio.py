"""O que todos os roteiros de clique usam: os usuários de teste, o jeito de entrar e os arquivos de exemplo.

Os usuários existem só no banco temporário de cada roteiro (tests/e2e/rodar.py), com uma senha de teste. Os arquivos
de exemplo (um Word em texto corrido e uma planilha com o endereço inteiro) são gravados na pasta temporária do
roteiro. Dados 100% inventados.
"""
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

# A pasta integra-folha/ (onde fica o .env), duas acima desta
PASTA_DO_PROJETO = Path(__file__).resolve().parents[2]


def ler_a_senha_de_teste() -> str:
    """A senha dos usuários de teste: a variável SENHA_DOS_TESTES, do ambiente ou do .env. A variável é OPCIONAL.

    Devolve: a senha (texto).
    Sem a variável, sorteia uma senha que vale para este processo e para os que ele abrir: ela fica no ambiente, e o
    preparar() do rodar.py (outro processo) cria os usuários com a mesma senha que o roteiro usa para entrar. O pytest
    cria e entra no mesmo processo. Assim, a bateria e os roteiros funcionam sem nada no .env.
    A variável só é necessária para entrar à mão num servidor de teste, com os usuários criados por outro comando.
    Por que a senha não fica no código: o repositório é aberto, e uma senha escrita aqui valeria em qualquer cópia dele.
    """
    # 1º: o ambiente (inclusive a senha sorteada por um processo pai)
    senha_do_ambiente = os.environ.get("SENHA_DOS_TESTES", "").strip()
    if senha_do_ambiente:
        return senha_do_ambiente
    # 2º: o .env da pasta do projeto (lido sem mudar o ambiente; sem o arquivo, vem vazio)
    senha_do_arquivo = (dotenv_values(PASTA_DO_PROJETO / ".env").get("SENHA_DOS_TESTES") or "").strip()
    if senha_do_arquivo:
        return senha_do_arquivo
    # 3º: uma senha sorteada (22 caracteres entre letras, números, "-" e "_"; a aplicação pede de 8 a 72), guardada
    # no ambiente para os processos filhos usarem a mesma
    senha_sorteada = secrets.token_urlsafe(16)
    os.environ["SENHA_DOS_TESTES"] = senha_sorteada
    return senha_sorteada


# A senha dos usuários de teste (vale só no banco temporário de cada roteiro)
SENHA_DE_TESTE = ler_a_senha_de_teste()
# O RH da Aurora (EMP001) e o especialista do banco
LOGIN_DA_EMPRESA = "teste.empresa"
LOGIN_DO_BANCO = "teste.banco"


def criar_usuarios_de_teste(conexao) -> None:
    """Cadastra o RH da Aurora e o especialista do banco no banco temporário (roda dentro de preparar())."""
    from models.contratos import Perfil
    from services import auth
    auth.cadastrar_usuario(conexao, LOGIN_DA_EMPRESA, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)


def entrar(navegador, endereco: str, login: str, erros_da_pagina: list):
    """Abre uma aba, entra com o usuário e espera a página inicial do perfil. Devolve a aba.

    Recebe: o navegador do Playwright; o endereço do servidor; o login; a lista onde anotar os erros de JavaScript.
    A página inicial muda com o perfil: home.html para a empresa, banco_inicio.html para o banco.
    """
    aba = navegador.new_page(viewport={"width": 1440, "height": 1000})
    # Todo erro de JavaScript da página fica anotado (e reprova o roteiro)
    aba.on("pageerror", lambda erro: erros_da_pagina.append(str(erro)))
    aba.goto(endereco + "/login.html")
    aba.fill("[name='usuario']", login)
    aba.fill("[name='senha']", SENHA_DE_TESTE)
    aba.click("button[type='submit']")
    # Espera sair da tela de login
    aba.wait_for_url(lambda url: "login.html" not in url, timeout=20000)
    return aba


def abrir_janela_de_cadastro(aba):
    """Clica em "Cadastrar funcionários", espera a janela abrir e a tela de dentro TERMINAR de carregar.

    Recebe: a aba. Devolve: o quadro da janela (para os cliques lá dentro).
    Por que esperar o carregamento inteiro: o campo do arquivo aparece antes de o JavaScript da tela ligar a escuta;
    um arquivo mandado nesse meio-tempo se perdia (uma corrida que só o robô provoca: uma pessoa nunca é tão rápida).
    """
    aba.click(".botao-cadastrar-funcionarios")
    aba.locator(".janela-novo-envio[open]").wait_for(timeout=10000)
    aba.wait_for_function("""() => {
        const quadro = document.querySelector('.janela-novo-envio-quadro');
        return quadro !== null && quadro.contentWindow.location.href.includes('cadastrar.html')
            && quadro.contentDocument.readyState === 'complete';
    }""", timeout=20000)
    return aba.frame_locator(".janela-novo-envio-quadro")


def pasta_do_roteiro() -> Path:
    """A pasta temporária do roteiro (a mesma do banco), onde o preparar() grava os arquivos de exemplo."""
    return Path(os.environ["E2E_PASTA"])


# O e-mail do RH em texto corrido: 4 pessoas; a Luíza vem sem CPF (vira pergunta da IA e pendência)
PARAGRAFOS_DO_WORD = [
    "Olá, pessoal do banco!",
    "Seguem os funcionários que entraram este mês na Brisa, para o cadastro da conta-salário.",
    "A Helena Duarte Ramos, CPF 529.982.247-25, entrou em 02/09/2026 como analista financeira, com salário de "
    "R$ 5.200,00. Ela mora na Rua das Acácias, 88, Campinas - SP, CEP 13015-100.",
    "O Rafael Monteiro Siqueira, CPF 111.444.777-35, começou em 08/09/2026 como assistente de logística, salário "
    "de R$ 2.750,00.",
    "Também temos o Caio Brandão (CPF 123.456.789-09), contratado em 15/09/2026 como vendedor, salário R$ 2.300,00.",
    "A Luíza começa no dia 22/09/2026 como recepcionista, com salário de R$ 2.100,00; o CPF dela eu mando depois.",
    "Qualquer dúvida, estou à disposição.",
    "Atenciosamente, Patrícia, RH da Brisa.",
]


def criar_word_de_exemplo() -> str:
    """Grava o Word em texto corrido na pasta do roteiro. Devolve o caminho do arquivo (texto)."""
    from docx import Document
    # Um documento em branco, com um parágrafo por linha do e-mail
    documento = Document()
    for paragrafo in PARAGRAFOS_DO_WORD:
        documento.add_paragraph(paragrafo)
    # Grava na pasta temporária do roteiro (apagada no fim)
    caminho = pasta_do_roteiro() / "novos_funcionarios.docx"
    documento.save(caminho)
    return str(caminho)


def criar_planilha_com_endereco() -> str:
    """Grava uma planilha (CSV) com o endereço inteiro numa coluna só. Devolve o caminho do arquivo (texto)."""
    planilha = (
        "Nome;CPF;Endereço;Cargo\n"
        "Maria Souza;529.982.247-25;Rua das Flores, 123, apto 4 - Centro, São Paulo - SP, 01234-567;Analista\n"
        "João Lima;111.444.777-35;Av. Brasil 45 - Jardim América - Goiânia/GO;Assistente\n"
    )
    caminho = pasta_do_roteiro() / "lista_com_endereco.csv"
    caminho.write_text(planilha, encoding="utf-8")
    return str(caminho)
