"""Rotas da API das KBs de endomarketing: a tela "Benefícios" do Portal Interno e a sub-aba da Telemetria (ADR-125).

Todas as rotas são SÓ do perfil BANCO (o especialista): a empresa nunca vê nem edita as KBs; ela vê só o que foi
publicado, na vitrine "Benefícios do seu time" (/api/empresa/beneficios, que já existe).

As rotas, em ordem (as de caminho fixo vêm antes de /{kb_id}, senão "modelos" seria lido como um id de KB):
    GET  /api/banco/kbs-endomarketing                          a lista das KBs (uma linha por KB), com filtro por dono
    GET  /api/banco/kbs-endomarketing/modelos                  os tipos, as seções, as categorias e os donos
    GET  /api/banco/kbs-endomarketing/achados                  o que a trava apontou (sub-aba da Telemetria)
    GET  /api/banco/kbs-endomarketing/aplicacoes               cada vez que as KBs foram aplicadas numa empresa
    GET  /api/banco/kbs-endomarketing/contexto/{empresa_id}    o pacote de KBs publicadas pronto para o agente
    POST /api/banco/kbs-endomarketing/verificar                roda a trava sem gravar
    POST /api/banco/kbs-endomarketing                          cria uma KB nova (rascunho)
    POST /api/banco/kbs-endomarketing/empresas/{empresa_id}/aplicar   aplica na empresa: catálogo, kit e logo
    GET  /api/banco/kbs-endomarketing/{kb_id}                  uma KB, com as seções e o histórico de versões
    POST /api/banco/kbs-endomarketing/{kb_id}/versoes          grava uma versão nova (rascunho)
    POST /api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/publicar   publica a versão
    POST /api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo       anexa o logo a um rascunho da KB do kit
    GET  /api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo       a imagem do logo da versão (sem logo: 404)
    DELETE /api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo     tira o logo de um rascunho da KB do kit
    POST /api/banco/kbs-endomarketing/{kb_id}/retirar          retira a versão publicada
    POST /api/banco/kbs-endomarketing/{kb_id}/revisar          renova a vigência (KB vencida ou vencendo)
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from api.mensagem_de_erro import mensagem_para_a_pessoa
from services import auth, kbs_endomarketing, kbs_publicacao, kit_de_marca

# O "roteador": um grupo de rotas que o api/principal.py acrescenta à aplicação
roteador = APIRouter()
# O maior corpo de KB aceito (50 mil letras: uma KB bem escrita tem poucas mil)
LIMITE_DO_CORPO = 50_000
# O maior valor de um campo da ficha (um título ou uma lista de cores cabem com folga) e o máximo de campos
LIMITE_DO_CAMPO_DA_FICHA, MAXIMO_DE_CAMPOS_DA_FICHA = 300, 20
# Um campo da ficha: texto de até 300 letras (texto gigante é recusado com 422 antes de chegar ao serviço)
CampoDaFicha = Annotated[str, Field(max_length=LIMITE_DO_CAMPO_DA_FICHA)]


class PedidoDeKb(BaseModel):
    """O formulário de uma KB: os campos da ficha e o Markdown das seções."""

    ficha: dict[str, CampoDaFicha] = Field(default_factory=dict, max_length=MAXIMO_DE_CAMPOS_DA_FICHA)
    corpo: str = Field(default="", max_length=LIMITE_DO_CORPO)


class PedidoDeRevisao(BaseModel):
    """A revisão de uma KB: a nova data de fim da vigência (AAAA-MM-DD)."""

    vigencia_fim: str = Field(max_length=10)


def _usuario_do_banco(pedido: Request):
    """Confere que quem pede está logado e é do perfil BANCO (a mesma conferência das outras rotas do banco).

    O import fica aqui dentro porque o api/principal.py importa este arquivo: importar no topo faria os dois
    arquivos esperarem um pelo outro ao carregar.
    """
    from api import principal
    return principal.usuario_do_banco(pedido)


def _executar(acao):
    """Roda a ação com uma conexão aberta e traduz os erros em respostas claras.

    A trava que bloqueou vira 400 com a mensagem E a lista de achados (a tela mostra cada um); KB ou empresa que não
    existe vira 404; operação fora do perfil vira 403; outro erro de regra vira 400.
    """
    conexao = auth.conectar()
    try:
        resultado = acao(conexao)
    except kbs_endomarketing.TravaBloqueou as erro:
        raise HTTPException(status_code=400, detail={"mensagem": str(erro), "achados": erro.achados})
    except PermissionError:
        raise HTTPException(status_code=403, detail="Operação não permitida para o seu perfil.")
    except KeyError:
        raise HTTPException(status_code=404, detail="KB ou empresa não encontrada.")
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=mensagem_para_a_pessoa(erro))
    finally:
        conexao.close()
    return resultado


# ---------------- Consultas ----------------

@roteador.get("/api/banco/kbs-endomarketing")
def listar_kbs(pedido: Request, dono: str | None = None):
    """A lista das KBs (uma linha por KB), de um dono ou de todos."""
    _usuario_do_banco(pedido)
    return _executar(lambda conexao: {"kbs": kbs_endomarketing.listar(conexao, dono)})


@roteador.get("/api/banco/kbs-endomarketing/modelos")
def modelos_das_kbs(pedido: Request):
    """Os tipos de KB (com as seções obrigatórias), as categorias da vitrine e os donos para escolher."""
    _usuario_do_banco(pedido)

    def montar(conexao):
        """Junta os modelos do repositório com os donos da carteira."""
        resultado = kbs_endomarketing.modelos()
        resultado["donos"] = kbs_publicacao.donos_disponiveis(conexao)
        return resultado
    return _executar(montar)


@roteador.get("/api/banco/kbs-endomarketing/achados")
def achados_da_trava(pedido: Request, dono: str | None = None):
    """Os achados gravados da trava, do mais recente para o mais antigo (até 200), e os totais de todos eles
    (bloqueios, avisos e KBs com achados), para os números da seção nunca ficarem menores do que são."""
    _usuario_do_banco(pedido)

    def montar(conexao):
        """Junta a lista dos mais recentes e os totais, do mesmo dono (ou de todos)."""
        return {"achados": kbs_endomarketing.listar_achados(conexao, dono),
                "totais": kbs_endomarketing.resumo_dos_achados(conexao, dono)}
    return _executar(montar)


@roteador.get("/api/banco/kbs-endomarketing/aplicacoes")
def aplicacoes_nas_empresas(pedido: Request, empresa_id: str | None = None):
    """Cada vez que as KBs foram aplicadas numa empresa (catálogo, kit e logo)."""
    _usuario_do_banco(pedido)
    return _executar(lambda conexao: {"aplicacoes": kbs_publicacao.aplicacoes(conexao, empresa_id)})


@roteador.get("/api/banco/kbs-endomarketing/contexto/{empresa_id}")
def contexto_do_agente(empresa_id: str, pedido: Request):
    """O pacote de KBs publicadas e vigentes que o agente recebe para escrever o material da empresa."""
    _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.contexto_do_agente(conexao, empresa_id))


# ---------------- Gravar, conferir e aplicar ----------------

@roteador.post("/api/banco/kbs-endomarketing/verificar")
def verificar_kb(dados: PedidoDeKb, pedido: Request, kb_id: str | None = None):
    """Roda a trava no formulário sem gravar. Devolve os achados (lista vazia = tudo certo)."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: {"achados": kbs_publicacao.verificar_kb(conexao, usuario, dados.ficha,
                                                                             dados.corpo, kb_id)})


@roteador.post("/api/banco/kbs-endomarketing")
def criar_kb(dados: PedidoDeKb, pedido: Request):
    """Cria uma KB nova, como rascunho (o id é criado a partir do dono, do tipo e do título)."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.salvar_kb(conexao, usuario, dados.ficha, dados.corpo))


@roteador.post("/api/banco/kbs-endomarketing/empresas/{empresa_id}/aplicar")
def aplicar_na_empresa(empresa_id: str, pedido: Request):
    """Aplica as KBs publicadas da empresa: a versão nova do catálogo do agente, o kit escolhido e o logo."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.aplicar_na_empresa(conexao, usuario, empresa_id))


# ---------------- Uma KB ----------------

@roteador.get("/api/banco/kbs-endomarketing/{kb_id}")
def obter_kb(kb_id: str, pedido: Request, versao: int | None = None):
    """Uma KB: a versão pedida (sem informar, a publicada ou a última), com as seções e o histórico."""
    _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_endomarketing.obter(conexao, kb_id, versao))


@roteador.post("/api/banco/kbs-endomarketing/{kb_id}/versoes")
def nova_versao_da_kb(kb_id: str, dados: PedidoDeKb, pedido: Request):
    """Grava uma versão nova da KB, como rascunho. A publicada continua valendo até esta ser publicada."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.salvar_kb(conexao, usuario, dados.ficha, dados.corpo, kb_id))


@roteador.post("/api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/publicar")
def publicar_kb(kb_id: str, versao: int, pedido: Request):
    """Publica a versão (a trava roda de novo). Se a KB muda a vitrine ou o kit da empresa, aplica na empresa."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.publicar_kb(conexao, usuario, kb_id, versao))


# ---------------- O logo da KB do kit (anexado a cada versão) ----------------

@roteador.post("/api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo")
async def enviar_logo_da_kb(kb_id: str, versao: int, pedido: Request, arquivo: UploadFile):
    """Anexa (ou troca) o logo de um rascunho da KB do kit: PNG ou JPEG de verdade, até 500 KB (multipart, "arquivo").

    Devolve {kb_id, versao, tem_logo: true}. Versão que não é rascunho, KB que não é do kit ou imagem inválida: 400.
    """
    usuario = _usuario_do_banco(pedido)
    # Lê só até o limite do logo (mais 1 byte, para saber se passou); a conferência fica no serviço
    conteudo = await arquivo.read(kit_de_marca.LIMITE_DO_LOGO + 1)
    return _executar(lambda conexao: kbs_publicacao.enviar_logo_da_kb(conexao, usuario, kb_id, versao, conteudo))


@roteador.get("/api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo")
def logo_da_kb(kb_id: str, versao: int, pedido: Request):
    """A imagem do logo de uma versão da KB do kit, em qualquer situação, para o editor mostrar (sem logo: 404)."""
    usuario = _usuario_do_banco(pedido)
    imagem, tipo = _executar(lambda conexao: kbs_publicacao.logo_da_kb(conexao, usuario, kb_id, versao))
    return Response(imagem, media_type=tipo)


@roteador.delete("/api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo")
def tirar_logo_da_kb(kb_id: str, versao: int, pedido: Request):
    """Tira o logo de um rascunho da KB do kit. Devolve {kb_id, versao, tem_logo: false}."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.tirar_logo_da_kb(conexao, usuario, kb_id, versao))


@roteador.post("/api/banco/kbs-endomarketing/{kb_id}/retirar")
def retirar_kb(kb_id: str, pedido: Request):
    """Retira a versão publicada: a KB deixa de valer para a vitrine e para o agente."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.retirar_kb(conexao, usuario, kb_id))


@roteador.post("/api/banco/kbs-endomarketing/{kb_id}/revisar")
def revisar_kb(kb_id: str, dados: PedidoDeRevisao, pedido: Request):
    """Renova a vigência da KB (vencida ou vencendo) com uma versão nova."""
    usuario = _usuario_do_banco(pedido)
    return _executar(lambda conexao: kbs_publicacao.revisar_kb(conexao, usuario, kb_id, dados.vigencia_fim))
