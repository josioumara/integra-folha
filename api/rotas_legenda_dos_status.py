"""Rotas da legenda dos status: o que quer dizer cada situação das grades.

O "i" em cima de cada grade com a coluna "Situação" (front/js/legenda_dos_status.js) pede os textos aqui, uma vez por
página, na primeira vez em que alguém o abre. As explicações ficam só em services/legenda_dos_status.py.

As rotas:
    GET /api/banco/legenda_dos_status     só do perfil BANCO: as grades do Portal Interno
    GET /api/empresa/legenda_dos_status   só do perfil EMPRESA: as grades do Portal Empresa, nada das do banco
Sem login, 401; com o outro perfil, 403 (a mesma conferência das outras rotas de cada portal). O texto é fixo, sem
dado de empresa: por isso as duas rotas não abrem o banco de dados, além da conferência de quem pede.
"""
from fastapi import APIRouter, Request

from services import legenda_dos_status

# O "roteador": um grupo de rotas que o api/principal.py acrescenta à aplicação
roteador = APIRouter()


def _conferir_usuario_do_banco(pedido: Request) -> None:
    """Confere que quem pede está logado e é do perfil BANCO (levanta 401 ou 403, como as outras rotas do banco).

    O import fica aqui dentro porque o api/principal.py importa este arquivo: importar no topo faria os dois
    arquivos esperarem um pelo outro ao carregar.
    """
    from api import principal
    principal.usuario_do_banco(pedido)


def _conferir_usuario_da_empresa(pedido: Request) -> None:
    """Confere que quem pede está logado e é do perfil EMPRESA (levanta 401 ou 403, como as outras rotas da empresa).

    O import fica aqui dentro pelo mesmo motivo de _conferir_usuario_do_banco.
    """
    from api import principal
    principal.usuario_da_empresa(pedido)


@roteador.get("/api/banco/legenda_dos_status")
def legenda_dos_status_do_banco(pedido: Request) -> dict:
    """O que quer dizer cada situação das grades do Portal Interno: {grade: [{texto, classe, explicacao}]}.

    As grades: "empresas" (a carteira do Início e de Empresas), "funcionarios" (a Visão geral), "usuarios" e
    "pessoas_do_envio" (a avaliação na aba Envios). Só BANCO.
    """
    # Só o especialista do banco
    _conferir_usuario_do_banco(pedido)
    # As explicações, da fonte única
    return legenda_dos_status.legendas_do_banco()


@roteador.get("/api/empresa/legenda_dos_status")
def legenda_dos_status_da_empresa(pedido: Request) -> dict:
    """O que quer dizer cada situação das grades do Portal Empresa: {grade: [{texto, classe, explicacao}]}.

    As grades: "funcionarios" (Acompanhar), "colunas" e "conferencia" (Cadastrar). Só EMPRESA.
    """
    # Só o RH de uma empresa
    _conferir_usuario_da_empresa(pedido)
    # As explicações, da fonte única (só as grades que a empresa vê)
    return legenda_dos_status.legendas_da_empresa()
