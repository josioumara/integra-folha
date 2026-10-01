"""Dados de exemplo (MOCK) usados pelas telas enquanto as fases seguintes não geram os dados reais.

As telas pedem os dados por aqui, nunca lendo os arquivos direto. Quando os dados reais chegarem,
só este arquivo muda; as telas continuam iguais.
"""
import json
from functools import lru_cache

from services import config

# Pasta dos arquivos de exemplo
PASTA_MOCK = config.RAIZ / "data" / "mock"


@lru_cache
def _ler_arquivo_mock(nome: str):
    """Lê um arquivo JSON da pasta de exemplos. O lru_cache guarda o resultado: cada arquivo é lido uma vez só."""
    with open(PASTA_MOCK / f"{nome}.json", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def sementes_das_empresas() -> list[dict]:
    """As 6 empresas fictícias do arquivo (a semente da tabela de empresas, services/empresas.py)."""
    return _ler_arquivo_mock("empresas")


def empresas() -> list[dict]:
    """As empresas da carteira (empresa_id, nome, setor, município, UF...), lidas da tabela de empresas.

    A tabela começa com as 6 da semente e cresce com as que o banco cadastra (ADR-69, passo 18). A lista fica em
    memória por alguns segundos (services/empresas.py), para as telas não abrirem o banco a cada nome.
    """
    # Importado aqui dentro: services/empresas.py também usa este arquivo (a semente)
    from services import empresas as cadastro_de_empresas
    return cadastro_de_empresas.lista_em_memoria()


def nome_da_empresa(empresa_id: str) -> str:
    """O nome da empresa a partir do id (ex.: "EMP001" -> "Aurora Alimentos"). Id desconhecido volta como está."""
    for empresa in empresas():
        if empresa["empresa_id"] == empresa_id:
            return empresa["nome"]
    return empresa_id

