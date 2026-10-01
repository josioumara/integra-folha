"""Rotas da API da faixa salarial por profissão (CBO): a seção nova da página Parâmetros do Portal Interno (ADR-129).

Todas as rotas são SÓ do perfil BANCO (o especialista). A empresa não consulta a tabela: ela só recebe o alerta quando
o salário de alguém sai da faixa (services/faixa_salarial_cbo.py, chamado pelo Validador).

As rotas:
    GET  /api/banco/cbo?busca=&inicio=           as profissões que batem com a busca (código ou título), com a faixa,
                                                 de 50 em 50 (inicio = a posição da primeira), e o total
    GET  /api/banco/cbo/{codigo}/alteracoes      quem mudou a faixa da profissão, quando e de quanto para quanto
    PUT  /api/banco/cbo/{codigo}/faixa           muda o mínimo e o máximo (a calculada continua guardada ao lado)
    POST /api/banco/cbo/{codigo}/faixa/voltar    volta à faixa calculada dos dados públicos
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.mensagem_de_erro import mensagem_para_a_pessoa
from services import auth, faixa_salarial_cbo

# O "roteador": um grupo de rotas que o api/principal.py acrescenta à aplicação
roteador = APIRouter()
# O maior texto aceito na busca e em cada valor (um código ou um título cabem com folga)
LIMITE_DA_BUSCA = 100
LIMITE_DO_VALOR = 30


class PedidoDeFaixa(BaseModel):
    """A faixa nova: o mínimo e o máximo em reais (número, ou texto como "2.500,00")."""

    minimo: float | str
    maximo: float | str


def _usuario_do_banco(pedido: Request):
    """Confere que quem pede está logado e é do perfil BANCO (a mesma conferência das outras rotas do banco).

    O import fica aqui dentro porque o api/principal.py importa este arquivo: importar no topo faria os dois
    arquivos esperarem um pelo outro ao carregar.
    """
    from api import principal
    return principal.usuario_do_banco(pedido)


def _executar(acao):
    """Roda a ação com uma conexão aberta e traduz os erros: código que não existe vira 404; valor inválido, 400."""
    conexao = auth.conectar()
    try:
        resultado = acao(conexao)
    except KeyError:
        raise HTTPException(status_code=404, detail="Profissão não encontrada na tabela CBO.")
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=mensagem_para_a_pessoa(erro))
    finally:
        conexao.close()
    return resultado


def _valor_curto(valor) -> float | str:
    """Recusa com 400 um texto comprido demais para ser um valor em reais (antes de chegar ao serviço)."""
    if isinstance(valor, str) and len(valor) > LIMITE_DO_VALOR:
        raise HTTPException(status_code=400, detail="Valor comprido demais para um valor em reais.")
    return valor


@roteador.get("/api/banco/cbo")
def buscar_faixas(pedido: Request, busca: str = "", inicio: int = 0):
    """As profissões que batem com a busca (50 por vez, a partir de "inicio"), com a faixa em uso, a calculada, a fonte
    e quem editou, e o total de profissões que batem."""
    _usuario_do_banco(pedido)
    if len(busca) > LIMITE_DA_BUSCA:
        raise HTTPException(status_code=400, detail="Busca comprida demais.")
    return _executar(lambda conexao: faixa_salarial_cbo.buscar_faixas(conexao, busca, inicio))


@roteador.get("/api/banco/cbo/{codigo}/alteracoes")
def alteracoes_da_faixa(codigo: str, pedido: Request):
    """As alterações da faixa da profissão, da mais recente para a mais antiga."""
    _usuario_do_banco(pedido)
    return _executar(lambda conexao: {"alteracoes": faixa_salarial_cbo.alteracoes(conexao, codigo)})


@roteador.put("/api/banco/cbo/{codigo}/faixa")
def editar_faixa(codigo: str, dados: PedidoDeFaixa, pedido: Request):
    """Muda o mínimo e o máximo da profissão (o mínimo nunca maior que o máximo). Guarda quem mudou e quando."""
    usuario = _usuario_do_banco(pedido)
    minimo, maximo = _valor_curto(dados.minimo), _valor_curto(dados.maximo)
    return _executar(lambda conexao: faixa_salarial_cbo.editar_faixa(conexao, usuario.login, codigo, minimo, maximo))


@roteador.post("/api/banco/cbo/{codigo}/faixa/voltar")
def voltar_ao_calculado(codigo: str, pedido: Request):
    """Volta a faixa da profissão à calculada dos dados públicos."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: faixa_salarial_cbo.voltar_ao_calculado(conexao, usuario.login, codigo))
