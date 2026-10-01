"""A receita da imagem (Dockerfile): a aplicação roda com um usuário sem poderes de administrador (ADR-110).

O Docker não está ligado em toda máquina, então a prova confere a receita lida como texto: existe a linha USER com um
usuário comum, ela vem antes da subida, e esse usuário é dono das pastas em que a aplicação escreve.
"""
from pathlib import Path

import yaml

# Pasta raiz do projeto
RAIZ = Path(__file__).resolve().parent.parent
# O usuário sem poderes criado na imagem
USUARIO_DA_APLICACAO = "integra"


def linhas_do_dockerfile() -> list[str]:
    """As instruções do Dockerfile, sem comentários e sem linhas vazias."""
    linhas = []
    for linha in (RAIZ / "Dockerfile").read_text(encoding="utf-8").splitlines():
        # Comentário e linha vazia não são instrução
        if linha.strip() and not linha.lstrip().startswith("#"):
            linhas.append(linha.strip())
    return linhas


def test_a_aplicacao_roda_com_um_usuario_sem_poderes_de_administrador():
    """A última linha USER é o usuário comum (nunca root) e vem antes do comando de subida (CMD)."""
    linhas = linhas_do_dockerfile()
    posicoes_do_usuario = []
    posicao_da_subida = None
    for posicao, linha in enumerate(linhas):
        if linha.startswith("USER "):
            posicoes_do_usuario.append(posicao)
        if linha.startswith("CMD "):
            posicao_da_subida = posicao
    assert posicoes_do_usuario, "o Dockerfile não tem a linha USER"
    ultima_linha_user = linhas[posicoes_do_usuario[-1]]
    assert ultima_linha_user == "USER " + USUARIO_DA_APLICACAO
    assert posicoes_do_usuario[-1] < posicao_da_subida


def test_o_usuario_escreve_no_volume_e_nos_dados_de_exemplo_mas_nao_no_codigo():
    """O usuário é criado com pasta pessoal e é dono só de /app/storage e /app/data/synthetic."""
    receita = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "useradd --create-home" in receita
    assert f"chown -R {USUARIO_DA_APLICACAO}:{USUARIO_DA_APLICACAO} /app/storage /app/data/synthetic" in receita
    # O código não muda de dono: nenhum "chown" na pasta inteira
    assert "chown -R integra:integra /app\n" not in receita
    assert "chown -R integra:integra /app " not in receita


def test_o_volume_do_compose_e_a_pasta_do_usuario():
    """O volume da aplicação no docker-compose é montado em /app/storage, a pasta que o usuário pode escrever."""
    receita = yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "arquivos_da_aplicacao:/app/storage" in receita["services"]["aplicacao"]["volumes"]
