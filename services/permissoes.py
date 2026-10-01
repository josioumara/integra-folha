"""Quem pode executar cada operação sensível.

A regra fica num lugar só: os serviços conferem o perfil pela OPERAÇÃO, não pela tela. Assim, mesmo que alguém chame
o serviço sem passar pela tela, o perfil errado é barrado. Quem pode abrir cada PÁGINA do front é outra regra, a do
porteiro da API (pagina_permitida, em api/principal.py).
"""
from models.contratos import Perfil

# Operação -> os perfis que podem executá-la
PERFIS_POR_OPERACAO = {
    "gerar_material": {Perfil.BANCO},                # Endomarketing: o banco gera o rascunho para a empresa (ADR-115)
    "publicar_material": {Perfil.BANCO},             # Endomarketing: publicar, descartar e retirar (ADR-115)
    "salvar_simulacao": {Perfil.BANCO},              # Simulação de ganho no Planejamento
    "editar_parametros": {Perfil.BANCO},             # Layout, premissas e catálogo
    "gerir_usuarios": {Perfil.BANCO},                # Cadastrar, redefinir senha, ativar e desativar
    "ver_execucoes": {Perfil.BANCO},                 # Execuções dos agentes (aba Telemetria, Desempenho da IA)
    "avaliar_envios": {Perfil.BANCO},                # Aprovar ou devolver os envios das empresas (ADR-69, passo 15)
    "dar_baixa_em_contas": {Perfil.BANCO},           # Subir o arquivo de contas abertas e dar baixa (ADR-69, passo 16)
    "editar_empresas": {Perfil.BANCO},               # Cadastrar e editar as empresas da carteira e o kit (ADR-69, passo 18)
    "consultar_funcionarios": {Perfil.BANCO},        # Visão geral da empresa com a lista de funcionários (ADR-112)
}


class AcessoNegado(PermissionError):
    """O usuário não pode executar esta operação (perfil errado, sem login ou sem empresa)."""


def autorizar(usuario, operacao: str) -> None:
    """Levanta AcessoNegado se o usuário não pode executar a operação. Operação desconhecida é sempre negada.

    Recebe: usuario — o da sessão (ou None, se ninguém entrou); operacao — ex.: "salvar_simulacao".
    Devolve: nada; só levanta o erro quando não pode. Ex.: (usuário da empresa, "salvar_simulacao") → AcessoNegado.
    """
    # Sem login, nenhuma operação
    if usuario is None:
        raise AcessoNegado("É preciso estar logado.")
    # Operação que não está na tabela não tem nenhum perfil autorizado
    perfis_autorizados = PERFIS_POR_OPERACAO.get(operacao, set())
    # O perfil de quem pede precisa estar entre os autorizados
    if usuario.perfil not in perfis_autorizados:
        raise AcessoNegado(f"O perfil {usuario.perfil.value} não pode executar: {operacao}.")
    # Operação de empresa exige a empresa do cadastro do usuário
    if Perfil.EMPRESA in perfis_autorizados and not usuario.empresa_id:
        raise AcessoNegado("Usuário de empresa sem empresa no cadastro.")
