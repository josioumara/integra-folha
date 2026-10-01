"""O cabeçalho das telas do novo front: quem entrou e os números que pedem atenção (ADR-69, passo 19).

Para que serve: o cabeçalho do layout tinha um nome fixo ("Marina Costa", "Rafael Lima") e números inventados na aba
Envios. (O sino de avisos não fica no cabeçalho: não levaria a nada útil.) Com a página ligada à aplicação, o cabeçalho mostra:
    - quem entrou (o login, que é o que a aplicação guarda) e o papel: "RH · <empresa>" ou "Especialista do banco",
      com as iniciais;
    - o número da aba Envios do banco (os envios esperando a avaliação).
O número da aba Empresas (as conversas abertas) não vem daqui: o js/sinal_de_conversas.js o busca e o atualiza de
tempos em tempos (GET /api/banco/conversas/abertas).
Nenhum dado de funcionário: só contagens.
"""
from models.contratos import Perfil
from services import avaliacao_do_banco, dados_mock

# O papel do especialista do banco, como aparece embaixo do nome (o da empresa leva o nome dela)
PAPEL_DO_BANCO = "Especialista do banco"


def iniciais(login: str) -> str:
    """As duas letras do círculo do cabeçalho, tiradas do login.

    Recebe: login — ex.: "marina.costa@aurora.com.br" ou "teste.banco". Devolve: "MC" ou "TB".
    Usa as duas primeiras partes do nome (separadas por ponto, traço ou sublinhado, antes do @).
    """
    nome = login.split("@")[0]
    partes = []
    for pedaco in nome.replace("-", ".").replace("_", ".").split("."):
        if pedaco:
            partes.append(pedaco)
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[1][0]).upper()


def cabecalho(conexao, usuario) -> dict:
    """O que o cabeçalho mostra para quem entrou.

    Recebe: conexao; usuario (da sessão). Devolve: {login, perfil, papel, nome_da_empresa, iniciais,
    envios_para_avaliar, empresas_na_carteira} — nome_da_empresa só existe para a empresa (None nos outros perfis);
    os dois últimos só fazem sentido para o banco (0 nos outros perfis).
    """
    envios_para_avaliar = 0
    # Quantas empresas a carteira do banco tem (a faixa escura do Portal Interno mostra esse número)
    empresas_na_carteira = 0
    nome_da_empresa = None
    if usuario.perfil == Perfil.EMPRESA:
        nome_da_empresa = dados_mock.nome_da_empresa(usuario.empresa_id)
        papel = "RH · " + nome_da_empresa
    else:
        papel = PAPEL_DO_BANCO
        envios_para_avaliar = avaliacao_do_banco.envios_esperando_o_banco(conexao)
        empresas_na_carteira = len(dados_mock.empresas())
    return {"login": usuario.login, "perfil": usuario.perfil.value, "papel": papel, "nome_da_empresa": nome_da_empresa,
            "iniciais": iniciais(usuario.login),
            "envios_para_avaliar": envios_para_avaliar,
            "empresas_na_carteira": empresas_na_carteira,
            # Senha provisória (convite ou redefinição): a tela abre "Minha senha" e não deixa seguir (ADR-109)
            "senha_provisoria": usuario.senha_provisoria}
