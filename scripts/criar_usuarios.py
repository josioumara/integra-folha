"""Cria os dois usuários da demo, um por perfil (ADR-32; o perfil CIENTISTA saiu: só EMPRESA e BANCO nesta versão).

Na sua máquina, o script PERGUNTA a senha de cada usuário, sem mostrar o que é digitado, e guarda só o
hash no banco: a senha não fica escrita em arquivo nenhum.

No servidor (onde não há ninguém para digitar), as senhas vêm das variáveis SENHA_USUARIO_EMPRESA e
SENHA_USUARIO_BANCO, definidas nos segredos da hospedagem.

Para rodar: python scripts/criar_usuarios.py
"""
import getpass
import os
import sys
from pathlib import Path

# Permite importar os módulos do projeto ao rodar o script diretamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.contratos import Perfil  # noqa: E402
from services import auth  # noqa: E402

# Os usuários da demo: login, variável da senha (só no servidor), perfil e empresa
USUARIOS_DEMO = [
    ("empresa.aurora", "SENHA_USUARIO_EMPRESA", Perfil.EMPRESA, "EMP001"),
    ("especialista.banco", "SENHA_USUARIO_BANCO", Perfil.BANCO, None),
]


def pedir_senha(login: str) -> str:
    """Pede a senha duas vezes na tela, sem mostrar o que é digitado, até as duas baterem."""
    while True:
        # getpass esconde o que é digitado
        senha = getpass.getpass(f"Senha para {login}: ")
        # Curta demais: pede de novo
        if len(senha) < auth.TAMANHO_MINIMO_SENHA:
            print(f"  A senha precisa ter pelo menos {auth.TAMANHO_MINIMO_SENHA} caracteres.")
            continue
        # A segunda digitação precisa ser igual à primeira
        senha_repetida = getpass.getpass(f"Repita a senha para {login}: ")
        if senha != senha_repetida:
            print("  As senhas não conferem. Tente de novo.")
            continue
        return senha


def main() -> None:
    """Cria (ou recria) os três usuários."""
    conexao = auth.conectar()
    for login, variavel_da_senha, perfil, empresa in USUARIOS_DEMO:
        # No servidor, a senha vem dos segredos; na máquina local, é perguntada na tela
        senha = os.getenv(variavel_da_senha) or pedir_senha(login)
        auth.cadastrar_usuario(conexao, login, senha, perfil, empresa)
        complemento = f", {empresa}" if empresa else ""
        print(f"usuário criado: {login} ({perfil.value}{complemento})")


if __name__ == "__main__":
    main()
