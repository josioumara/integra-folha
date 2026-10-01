"""Rotas do joinha: a opinião das pessoas sobre as respostas dos agentes de IA (ADR-151). As regras ficam em
services/opiniao_dos_agentes.py.

As rotas:
    POST /api/empresa/opinioes                       só EMPRESA: o voto numa resposta do Agente de validação ou numa
                                                     pergunta do Agente Leitor ou do Agente Conferidor, num envio da
                                                     própria empresa
    GET  /api/empresa/opinioes?envio=<id>            só EMPRESA: os votos desta pessoa naquele envio (a tela marca os
                                                     joinhas já dados)
    POST /api/banco/empresas/{empresa_id}/opinioes   só BANCO: o voto num material do Agente de Endomarketing
    GET  /api/banco/empresas/{empresa_id}/opinioes   só BANCO: os votos deste especialista nos materiais da empresa
    GET  /api/banco/telemetria/opinioes              só BANCO: os números agregados da tela Acompanhamento dos agentes,
                                                     com o período do alto dela (?de=AAAA-MM-DD&ate=AAAA-MM-DD; sem as
                                                     datas, tudo)
Sem login, 401 (o porteiro responde antes de ler o pedido); com o outro perfil, 403. O envio ou o material de outra
empresa, e a resposta que não existe, dão 404, sem dizer se existem em outra empresa. Voto, comentário, referência ou
data fora da regra: 400, com a frase para a pessoa.
"""
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from services import opiniao_dos_agentes

# O "roteador": um grupo de rotas que o api/principal.py acrescenta à aplicação
roteador = APIRouter()


class PedidoDeOpiniao(BaseModel):
    """O voto que a tela manda: o tipo e a referência da interação, o voto (None retira o voto) e o comentário.

    Os tetos de tamanho barram um pedido gigante antes de qualquer conta. O limite do comentário que a pessoa vê (200
    letras) é conferido no serviço, com a frase certa para a tela.
    """

    tipo: str = Field(max_length=40)
    referencia: str = Field(max_length=1000)
    voto: str | None = Field(default=None, max_length=20)
    comentario: str | None = Field(default=None, max_length=1000)


def _principal():
    """O api/principal.py, com a conferência de quem pede e a tradução dos erros.

    O import fica aqui dentro porque o api/principal.py importa este arquivo: importar no topo faria os dois arquivos
    esperarem um pelo outro ao carregar.
    """
    from api import principal
    return principal


@roteador.post("/api/empresa/opinioes")
def votar_como_empresa(dados: PedidoDeOpiniao, pedido: Request) -> dict:
    """O joinha da empresa numa resposta do Agente de validação ou numa pergunta da leitura.

    Devolve a opinião que vale agora: {tipo, referencia, agente, nome_do_agente, voto, comentario}.
    """
    principal = _principal()
    # Só o RH de uma empresa; a empresa vem da sessão, nunca do pedido
    usuario = principal.usuario_da_empresa(pedido)
    return principal.executar_acao(lambda conexao: opiniao_dos_agentes.votar_como_empresa(
        conexao, usuario, dados.tipo, dados.referencia, dados.voto, dados.comentario))


@roteador.get("/api/empresa/opinioes")
def opinioes_da_empresa(pedido: Request, envio: str = Query(max_length=100)) -> dict:
    """Os votos desta pessoa num envio da empresa dela: {opinioes: [{tipo, referencia, voto, comentario, ...}]}."""
    principal = _principal()
    usuario = principal.usuario_da_empresa(pedido)
    opinioes = principal.executar_acao(lambda conexao: opiniao_dos_agentes.opinioes_do_envio(
        conexao, usuario, envio))
    return {"opinioes": opinioes}


@roteador.post("/api/banco/empresas/{empresa_id}/opinioes")
def votar_como_banco(empresa_id: str, dados: PedidoDeOpiniao, pedido: Request) -> dict:
    """O joinha do especialista num material que o Agente de Endomarketing escreveu para a empresa."""
    principal = _principal()
    # Só o especialista do banco
    usuario = principal.usuario_do_banco(pedido)
    return principal.executar_acao(lambda conexao: opiniao_dos_agentes.votar_como_banco(
        conexao, usuario, empresa_id, dados.tipo, dados.referencia, dados.voto, dados.comentario))


@roteador.get("/api/banco/empresas/{empresa_id}/opinioes")
def opinioes_do_banco(empresa_id: str, pedido: Request) -> dict:
    """Os votos deste especialista nos materiais de uma empresa: {opinioes: [...]}."""
    principal = _principal()
    usuario = principal.usuario_do_banco(pedido)
    opinioes = principal.executar_acao(lambda conexao: opiniao_dos_agentes.opinioes_dos_materiais(
        conexao, usuario, empresa_id))
    return {"opinioes": opinioes}


@roteador.get("/api/banco/telemetria/opinioes")
def satisfacao_dos_agentes(pedido: Request, de: str = Query(default="", max_length=10),
                           ate: str = Query(default="", max_length=10)) -> dict:
    """Os números da opinião sobre os agentes, com o período da tela Acompanhamento dos agentes: só agregados."""
    principal = _principal()
    # Só o especialista do banco (quem votou e o texto dos comentários nunca saem daqui)
    principal.usuario_do_banco(pedido)
    return principal.executar_acao(lambda conexao: opiniao_dos_agentes.satisfacao_dos_agentes(conexao, de, ate))
