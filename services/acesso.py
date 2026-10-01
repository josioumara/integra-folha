"""A porta das operações sensíveis: as telas passam por aqui, e aqui o perfil é conferido.

O porteiro da API já barra quem não pode abrir a página, e cada rota confere o perfil (api/principal.py). Esta porta
confere DE NOVO, no serviço, com a tabela PERFIS_POR_OPERACAO (services/permissoes.py): mesmo chamando o serviço por
fora da tela, o perfil errado é barrado. Duas regras extras:
- a empresa vem SEMPRE do cadastro do usuário logado, nunca de um parâmetro da tela;
- quem fez a operação (o login) também vem do usuário, para a auditoria.

A API e os serviços dos portais não podem chamar essas operações direto: um teste confere isso
(tests/test_seguranca.py).
"""
from agents import endomarketing
from services import auth, catalogo, painel, parametros, planejamento, sessoes
from services.permissoes import autorizar


# ---------------- Endomarketing (só o banco gera e publica, ADR-115) ----------------

def gerar_material(conexao, usuario, empresa_id: str, tipo: str, beneficios: list[str], destaque: str = "",
                   processamento_id: str | None = None, canal: str = endomarketing.CANAL_PADRAO):
    """Endomarketing: o especialista gera um rascunho para a empresa escolhida, com os benefícios que ele marcou.

    Por que o banco e não a empresa (ADR-115): assim nenhuma empresa divulga um benefício sem a validação do banco.
    Quem gerou (o login) vem do usuário da sessão, para a auditoria.
    """
    autorizar(usuario, "gerar_material")
    return endomarketing.gerar_material(conexao, empresa_id, tipo, usuario.login, destaque=destaque,
                                        processamento_id=processamento_id, canal=canal, beneficios=beneficios)


def publicar_material(conexao, usuario, empresa_id: str, material_id: str, arte_png: bytes | None = None) -> None:
    """O especialista publica um rascunho para a empresa (com a arte, se houver): a empresa passa a ver e baixar."""
    autorizar(usuario, "publicar_material")
    endomarketing.publicar(conexao, empresa_id, material_id, usuario.login, arte_png)


def descartar_material(conexao, usuario, empresa_id: str, material_id: str) -> None:
    """O especialista descarta um rascunho (a empresa nunca o vê)."""
    autorizar(usuario, "publicar_material")
    endomarketing.descartar(conexao, empresa_id, material_id, usuario.login)


def retirar_material(conexao, usuario, empresa_id: str, material_id: str) -> None:
    """O especialista retira um material publicado: a empresa deixa de ver e de baixar."""
    autorizar(usuario, "publicar_material")
    endomarketing.retirar(conexao, empresa_id, material_id, usuario.login)


# ---------------- Banco ----------------

def salvar_simulacao(conexao, usuario, nome: str, simulacao: dict, base: dict, resultado: dict, filtros: dict) -> None:
    """Guarda a simulação de rentabilidade com o nome dado e quem simulou (só o banco). As oficiais não mudam.

    simulacao: o que services/planejamento.premissas_do_simulador devolve; base: {clientes, origem}; resultado: o que
    planejamento.simular_rentabilidade devolve.
    """
    autorizar(usuario, "salvar_simulacao")
    planejamento.salvar_simulacao(conexao, nome, simulacao, base, resultado, filtros, usuario.login)


def salvar_premissas(conexao, usuario, premissas: dict) -> int:
    """Nova versão das premissas financeiras (só o banco)."""
    autorizar(usuario, "editar_parametros")
    return parametros.salvar_premissas(conexao, premissas, usuario.login)


def adicionar_documento(conexao, usuario, empresa_id: str, titulo: str, vigencia_inicio: str, vigencia_fim: str,
                        conteudo_md: str) -> int:
    """Novo documento do catálogo de benefícios de uma empresa (só o banco, que define o catálogo)."""
    autorizar(usuario, "editar_parametros")
    return catalogo.adicionar_documento(conexao, empresa_id, titulo, vigencia_inicio, vigencia_fim, conteudo_md,
                                        usuario.login)


def cadastrar_usuario(conexao, usuario, login: str, senha: str, perfil, empresa_id: str | None,
                      senha_provisoria: bool = False) -> None:
    """Cadastra um usuário (só o banco). senha_provisoria: a pessoa troca no primeiro acesso (ADR-109)."""
    autorizar(usuario, "gerir_usuarios")
    auth.cadastrar_usuario(conexao, login, senha, perfil, empresa_id, senha_provisoria)


def redefinir_senha(conexao, usuario, login_alvo: str, nova_senha: str, senha_provisoria: bool = False) -> None:
    """Redefine a senha de alguém e derruba as sessões abertas dessa pessoa (só o banco).

    senha_provisoria: True quando o banco gera a senha (a pessoa troca no próximo acesso, ADR-109).
    """
    autorizar(usuario, "gerir_usuarios")
    auth.redefinir_senha(conexao, login_alvo, nova_senha, senha_provisoria)
    sessoes.encerrar_sessoes_do_usuario(conexao, login_alvo)


def definir_ativo(conexao, usuario, login_alvo: str, ativo: bool) -> None:
    """Ativa ou desativa alguém; desativado perde as sessões na hora (só o banco; ninguém desativa a si mesmo)."""
    autorizar(usuario, "gerir_usuarios")
    if login_alvo == usuario.login:
        raise ValueError("Ninguém desativa o próprio usuário.")
    auth.definir_ativo(conexao, login_alvo, ativo)
    if not ativo:
        sessoes.encerrar_sessoes_do_usuario(conexao, login_alvo)


# ---------------- Desempenho da IA (aba Telemetria do banco) ----------------

def execucoes_do_painel(conexao, usuario, agente=None, modelo=None, desde=None, ate=None) -> list[dict]:
    """As execuções dos agentes, com os filtros (o especialista do banco, na aba Telemetria)."""
    autorizar(usuario, "ver_execucoes")
    return painel.execucoes_filtradas(conexao, agente=agente, modelo=modelo, desde=desde, ate=ate)
