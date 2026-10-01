"""Prepara o servidor na subida, sem perguntar nada a ninguém (ADR-64).

Na hospedagem, o disco pode começar vazio a cada subida. Este script roda antes da API e gera só o
que falta:
1. os dados sintéticos (arquivos de envio), se ainda não existem;
2. os índices do RAG, se não estão disponíveis (na primeira vez, baixa o modelo de embeddings);
3. os usuários da demo, SÓ se as três senhas estiverem nos segredos da hospedagem (SENHA_USUARIO_*).
   Sem elas, avisa e segue: no servidor não há ninguém para digitar senha.

Rodar de novo não refaz dados nem índices que já existem.

Para rodar: python scripts/preparar_servidor.py   (o Dockerfile chama antes de subir a API)
"""
import os
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from rag.busca import COLECAO_CATALOGO, COLECAO_LAYOUT, indice_disponivel  # noqa: E402
from scripts import build_index, criar_usuarios, gerar_dados  # noqa: E402
from services import auth  # noqa: E402

# Onde ficam os arquivos de envio gerados
PASTA_DOS_ENVIOS = RAIZ / "data" / "synthetic" / "envios"


def precisa_gerar_dados(pasta: Path = PASTA_DOS_ENVIOS) -> bool:
    """True se a pasta dos arquivos de envio não existe ou está vazia."""
    if not pasta.exists():
        return True
    # Vazia: nenhum arquivo dentro
    arquivos = list(pasta.iterdir())
    return len(arquivos) == 0


def precisa_montar_indices() -> bool:
    """True se algum dos dois índices do RAG (layout e catálogo) não está disponível."""
    return not indice_disponivel(COLECAO_LAYOUT) or not indice_disponivel(COLECAO_CATALOGO)


def senhas_dos_segredos() -> dict | None:
    """As senhas dos dois usuários da demo, lidas dos segredos; None se faltar alguma.

    Exemplo: {"empresa.aurora": "...", "especialista.banco": "..."}
    """
    senhas = {}
    for login, variavel_da_senha, _perfil, _empresa in criar_usuarios.USUARIOS_DEMO:
        senha = os.getenv(variavel_da_senha)
        # Faltou uma: não cria nenhum (a demo precisa dos dois perfis)
        if not senha:
            return None
        senhas[login] = senha
    return senhas


def criar_usuarios_dos_segredos(senhas: dict) -> None:
    """Cria (ou recria) os dois usuários da demo com as senhas dos segredos."""
    conexao = auth.conectar()
    for login, _variavel_da_senha, perfil, empresa in criar_usuarios.USUARIOS_DEMO:
        auth.cadastrar_usuario(conexao, login, senhas[login], perfil, empresa)
    conexao.close()


def main() -> list[str]:
    """Gera o que falta e devolve, em frases, o que foi feito (também impressas na tela)."""
    feito = []
    # 1. Dados sintéticos
    if precisa_gerar_dados():
        gerar_dados.main()
        feito.append("dados sintéticos gerados")
    else:
        feito.append("dados sintéticos já existiam")
    # 2. Índices do RAG
    if precisa_montar_indices():
        build_index.main()
        feito.append("índices do RAG montados")
    else:
        feito.append("índices do RAG já existiam")
    # 3. Usuários de perfis que não existem mais (o perfil CIENTISTA saiu: só EMPRESA e BANCO nesta versão): apagados, com as sessões
    conexao = auth.conectar()
    apagados = auth.remover_usuarios_de_perfis_extintos(conexao)
    conexao.close()
    if apagados:
        feito.append("usuários de perfis que não existem mais apagados: " + ", ".join(apagados))
    # 4. Usuários da demo, só com as senhas dos segredos
    senhas = senhas_dos_segredos()
    if senhas is None:
        feito.append("usuários NÃO criados: defina SENHA_USUARIO_EMPRESA e SENHA_USUARIO_BANCO nos segredos "
                     "da hospedagem")
    else:
        criar_usuarios_dos_segredos(senhas)
        feito.append("usuários da demo criados com as senhas dos segredos")
    for frase in feito:
        print(f"preparar_servidor: {frase}")
    return feito


if __name__ == "__main__":
    main()
