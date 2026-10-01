"""As pastas do RAG (índices e modelo) podem apontar para outro lugar, como as outras pastas de dados do config.py.

Para que serve: o servidor de teste de uma cópia isolada do repositório (worktree) usa os índices e o modelo da pasta
principal sem copiar nada e sem criar atalho de pasta. Apagar uma cópia que tivesse um atalho poderia apagar a pasta
verdadeira.

Cada caso roda num processo novo, porque os módulos leem a variável uma vez só, quando são importados.
"""
import os
import subprocess
import sys
from pathlib import Path

# A raiz do projeto, de onde o processo novo importa os módulos
RAIZ = Path(__file__).resolve().parent.parent


def pasta_lida_num_processo_novo(variaveis: dict, variaveis_a_tirar: tuple, codigo: str) -> str:
    """O que o código imprime num processo Python novo, com as variáveis de ambiente informadas.

    Recebe: as variáveis a pôr, as variáveis a tirar do ambiente e o código a rodar (que imprime a pasta).
    Devolve: o texto impresso, sem espaços nas pontas.
    """
    ambiente = dict(os.environ)
    ambiente.update(variaveis)
    for nome in variaveis_a_tirar:
        ambiente.pop(nome, None)
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=ambiente, capture_output=True,
                               text=True, check=True)
    return resultado.stdout.strip()


def test_pastas_do_rag_seguem_as_variaveis_de_ambiente(tmp_path):
    """Com PASTA_INDICES e PASTA_MODELOS, os índices e o modelo vêm do lugar informado (ex.: a pasta principal)."""
    indices = tmp_path / "indices_da_pasta_principal"
    modelos = tmp_path / "modelos_da_pasta_principal"
    assert pasta_lida_num_processo_novo({"PASTA_INDICES": str(indices)}, (),
                                        "from rag import busca; print(busca.PASTA_INDICES)") == str(indices)
    assert pasta_lida_num_processo_novo({"PASTA_MODELOS": str(modelos)}, (),
                                        "from rag import embeddings; print(embeddings.PASTA_MODELOS)") == str(modelos)


def test_sem_as_variaveis_as_pastas_ficam_no_storage_do_projeto():
    """Sem as variáveis, nada muda: os índices e o modelo ficam em storage/, dentro do projeto."""
    assert pasta_lida_num_processo_novo({}, ("PASTA_INDICES",), "from rag import busca; print(busca.PASTA_INDICES)") == \
        str(RAIZ / "storage" / "indices")
    assert pasta_lida_num_processo_novo({}, ("PASTA_MODELOS",),
                                        "from rag import embeddings; print(embeddings.PASTA_MODELOS)") == \
        str(RAIZ / "storage" / "modelos")
