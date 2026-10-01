"""Testes do Planejamento no Portal do Banco (novo front, ADR-69): serviço e rotas /api/banco/...

O que se prova aqui:
    - os números são os mesmos de services/planejamento.py (nenhuma conta nova), com e sem filtros;
    - o ganho usa a mesma fórmula e nunca uma taxa padrão;
    - simulações são só do perfil BANCO;
    - a rota do Consultor saiu com ele (ADR-144): ninguém a alcança, e ela não quebra (nada de erro 500).
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, cadastro, motor_planejamento, planejamento, portal_do_banco, sessoes
from services.auth import Usuario
from tests.test_correcao import ENVIOS, _gabarito, busca_falsa
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Usuários de mentira para chamar o serviço direto
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")


@pytest.fixture
def conexao(tmp_path, verdade):
    """Um banco com a Aurora e a Brisa homologadas e passadas pelo motor de planejamento."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    for nome, empresa_id in (("aurora_carga_inicial", "EMP001"), ("brisa_carga_inicial", "EMP003")):
        processamento_id = homologar(conexao_do_teste, nome, verdade)
        motor_planejamento.processar_homologacao(conexao_do_teste, processamento_id, empresa_id)
    yield conexao_do_teste
    conexao_do_teste.close()


def test_filtros_trazem_as_empresas_com_numeros(conexao):
    filtros = portal_do_banco.filtros_do_planejamento(conexao)
    ids = [empresa["id"] for empresa in filtros["empresas"]]
    assert ids == ["EMP001", "EMP003"]
    assert all(empresa["nome"] for empresa in filtros["empresas"])
    assert filtros["ufs"]


def test_numeros_sao_os_mesmos_do_servico_de_planejamento(conexao):
    # Sem filtro
    numeros = portal_do_banco.numeros_do_planejamento(conexao, {})
    assert numeros["resumo"] == planejamento.resumir(conexao)
    assert numeros["indicadores"]["empresas_integradas"] == 2
    # Com filtro de empresa (texto vazio nos outros = todos)
    numeros = portal_do_banco.numeros_do_planejamento(conexao, {"empresa_id": "EMP001", "uf": ""})
    assert numeros["resumo"] == planejamento.resumir(conexao, "EMP001")
    assert numeros["indicadores"]["empresas_integradas"] == 1


# As três taxas do Simulador de Rentabilidade usadas nos testes daqui (de 0 a 100)
TAXAS_DE_TESTE = {"percentual_novas_contas": "15", "percentual_nao_folha": "40", "percentual_folha": "20",
                  "percentual_ativos": "50"}


def test_ganho_usa_a_mesma_formula_e_nunca_taxa_padrao(conexao):
    # Sem as taxas: a simulação espera (nunca há valor padrão)
    sem_taxa = portal_do_banco.simular(conexao, {}, {}, 100)
    assert sem_taxa["simulacao"]["total"] is None
    assert sem_taxa["simulacao"]["falta"] == ["% novas contas", "% correntista (não folha)", "% correntista (folha)",
                                              "% ativos entre os correntistas"]
    # Com as três taxas: a MESMA conta de services/planejamento.py
    simulado = portal_do_banco.simular(conexao, {}, dict(TAXAS_DE_TESTE), 100)
    usados = planejamento.premissas_do_simulador(conexao, dict(TAXAS_DE_TESTE))
    esperado = planejamento.simular_rentabilidade(100, usados["taxas"], usados["premissas"])
    assert simulado["simulacao"] == esperado and simulado["base"] == {"clientes": 100, "origem": "empresa"}
    # Taxa fora de 0% a 100%: recusada pelo serviço
    with pytest.raises(ValueError):
        portal_do_banco.simular(conexao, {}, {"percentual_novas_contas": "150"}, 100)


def test_simulacao_so_do_banco_e_fica_salva(conexao):
    salva = portal_do_banco.salvar_simulacao(conexao, ESPECIALISTA, "Aurora a 20%", {"empresa_id": "EMP001"},
                                             dict(TAXAS_DE_TESTE), 35)
    salvas = portal_do_banco.simulacoes_salvas(conexao)
    assert salvas[0]["usuario"] == "especialista" and salvas[0]["ganho_total"] == salva["ganho_total"]
    assert salvas[0]["nome"] == "Aurora a 20%" and salvas[0]["filtros"]["empresa_id"] == "EMP001"
    # O RH da empresa não salva simulação do banco
    with pytest.raises(PermissionError):
        portal_do_banco.salvar_simulacao(conexao, RH_DA_AURORA, "Da empresa", {}, {"taxa_conquista": "20"})


# ---------------- Início e aba Telemetria ----------------


def enviar_pelo_fluxo(conexao, nome):
    """Envia um arquivo da demo pelo cadastro (o fluxo em LangGraph grava as execuções dos agentes)."""
    gabarito = _gabarito(nome)
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    return cadastro.enviar_arquivo(conexao, gabarito["empresa_id"], "rh.teste", conteudo, gabarito["arquivo"],
                                   busca=busca_falsa)


def test_inicio_mostra_a_carteira_com_a_situacao_de_cada_empresa(conexao):
    # A Horizonte manda um arquivo que para no aceite (envio em andamento)
    enviar_pelo_fluxo(conexao, "horizonte_carga_inicial")
    inicio = portal_do_banco.inicio_do_banco(conexao)
    por_id = {linha["id"]: linha for linha in inicio["carteira"]}
    assert len(inicio["carteira"]) == 6
    assert por_id["EMP001"]["cadastrados"] > 0 and por_id["EMP001"]["situacao"]["texto"] == "Em dia"
    assert por_id["EMP002"]["situacao"]["texto"] == "Em andamento"
    assert por_id["EMP004"]["situacao"]["texto"] == "Sem carga"
    # Os números somam a carteira
    assert inicio["numeros"]["cadastrados"] == por_id["EMP001"]["cadastrados"] + por_id["EMP003"]["cadastrados"]
    assert inicio["numeros"]["empresas_sem_carga"] == 3
    # A fila começa pelas empresas sem carga (urgentes)
    assert inicio["fila"][0]["urgente"] is True and "nenhuma carga" in inicio["fila"][0]["detalhe"]


def test_desempenho_da_ia_com_as_execucoes_para_o_banco(conexao):
    enviar_pelo_fluxo(conexao, "horizonte_carga_inicial")
    tecnico = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)
    assert tecnico["visao"]["execucoes"] > 0 and tecnico["recentes"]
    # Só os campos técnicos (nenhum dado de pessoa)
    assert set(tecnico["recentes"][0]) == set(portal_do_banco.CAMPOS_DA_EXECUCAO) | {"empresa"}
    # Tokens e custo em MOCK: "não medido", nunca zero inventado
    assert tecnico["visao"]["custo_usd"] == "não medido"
    # A empresa não vê (a aba Telemetria é do banco)
    with pytest.raises(PermissionError):
        portal_do_banco.telemetria_da_ia(conexao, RH_DA_AURORA)


def test_uso_das_empresas_com_acessos_funil_e_linha_do_tempo(conexao):
    # A Horizonte manda um arquivo que para no aceite; o RH da Aurora entra duas vezes
    enviar_pelo_fluxo(conexao, "horizonte_carga_inicial")
    auth.preparar_tabela(conexao)
    sessoes.preparar_tabela(conexao)
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    sessoes.criar_sessao(conexao, "rh.aurora")
    sessoes.criar_sessao(conexao, "rh.aurora")
    uso = portal_do_banco.uso_das_empresas(conexao)
    por_id = {empresa["id"]: empresa for empresa in uso["empresas"]}
    assert len(uso["empresas"]) == 6 and len(uso["etapas"]) == 4
    # Acessos contados pelas sessões de login
    assert por_id["EMP001"]["acessos"] == 2 and por_id["EMP001"]["ultimo_acesso"]
    assert por_id["EMP004"]["acessos"] == 0 and por_id["EMP004"]["ultimo_acesso"] is None
    # A Aurora chegou ao fim do funil; a Horizonte parou antes de conferir as colunas
    assert por_id["EMP001"]["funil"] == [1, 1, 1, 1]
    assert por_id["EMP002"]["funil"][0] == 1 and por_id["EMP002"]["funil"][3] == 0
    assert por_id["EMP002"]["onde_parou"] == "Em andamento"
    # A linha do tempo diz o que aconteceu, sem nenhum dado de funcionário
    assert por_id["EMP002"]["linha_do_tempo"][0]["o_que"] == "mandou um arquivo"
    assert set(por_id["EMP002"]["linha_do_tempo"][0]) == {"quando", "o_que"}
    # O funil da carteira é a soma das empresas
    assert uso["carteira"]["funil"][0] == sum(empresa["funil"][0] for empresa in uso["empresas"])


def test_ficha_das_empresas_com_usuarios_e_catalogo(conexao):
    # Duas pessoas da Aurora (uma entrou no portal) e o especialista, que não é usuário de empresa
    auth.preparar_tabela(conexao)
    sessoes.preparar_tabela(conexao)
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "rh2.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    sessoes.criar_sessao(conexao, "rh.aurora")
    fichas = portal_do_banco.empresas_da_carteira(conexao)
    por_id = {ficha["id"]: ficha for ficha in fichas}
    assert len(fichas) == 6 and por_id["EMP001"]["setor"]
    # Usuários: só as pessoas da empresa, com o último acesso (quem nunca entrou fica sem data); nunca a senha
    usuarios_da_aurora = {usuario["login"]: usuario for usuario in por_id["EMP001"]["usuarios"]}
    assert set(usuarios_da_aurora) == {"rh.aurora", "rh2.aurora"}
    assert usuarios_da_aurora["rh.aurora"]["ultimo_acesso"] and usuarios_da_aurora["rh2.aurora"]["ultimo_acesso"] is None
    assert set(usuarios_da_aurora["rh.aurora"]) == {"login", "ativo", "ultimo_acesso", "suspensao", "senha_provisoria",
                                                    "senha_provisoria_vencida"}
    # Catálogo: o documento vigente da empresa, com as seções (e só o da própria empresa)
    documento = por_id["EMP001"]["catalogo"][0]
    assert documento["versao"] == 1 and "Crédito consignado" in documento["secoes"]
    assert "Aurora" in documento["titulo"] and "Horizonte" not in documento["titulo"]
    assert por_id["EMP001"]["cadastrados"] > 0 and por_id["EMP004"]["situacao"]["texto"] == "Sem carga"


def test_banco_desativa_e_reativa_so_pessoa_de_empresa(conexao):
    auth.preparar_tabela(conexao)
    sessoes.preparar_tabela(conexao)
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao, "outro.especialista", SENHA_DE_TESTE, Perfil.BANCO)
    ingresso = sessoes.criar_sessao(conexao, "rh.aurora")
    # Desativada: não entra e perde a sessão aberta na hora
    portal_do_banco.ativar_ou_desativar_usuario_da_empresa(conexao, ESPECIALISTA, "rh.aurora", False)
    assert auth.autenticar(conexao, "rh.aurora", SENHA_DE_TESTE) is None
    assert sessoes.validar_sessao(conexao, ingresso) is None
    # Reativada: entra de novo
    portal_do_banco.ativar_ou_desativar_usuario_da_empresa(conexao, ESPECIALISTA, "rh.aurora", True)
    assert auth.autenticar(conexao, "rh.aurora", SENHA_DE_TESTE) is not None
    # Esta tela não mexe em usuário do banco, nem em login que não existe
    with pytest.raises(ValueError):
        portal_do_banco.ativar_ou_desativar_usuario_da_empresa(conexao, ESPECIALISTA, "outro.especialista", False)
    with pytest.raises(ValueError):
        portal_do_banco.ativar_ou_desativar_usuario_da_empresa(conexao, ESPECIALISTA, "ninguem", False)
    # A empresa não desativa ninguém (a porta de acesso confere o perfil)
    with pytest.raises(PermissionError):
        portal_do_banco.ativar_ou_desativar_usuario_da_empresa(conexao, RH_DA_AURORA, "rh.aurora", False)


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_do_banco(tmp_path, monkeypatch, verdade):
    """A API apontada para um banco só deste teste, com a Aurora no planejamento, um especialista e um RH."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_banco.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    processamento_id = homologar(conexao_do_teste, "aurora_carga_inicial", verdade)
    motor_planejamento.processar_homologacao(conexao_do_teste, processamento_id, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_planejamento_ganho_e_simulacao_do_banco(api_do_banco):
    especialista = entrar("especialista")
    assert especialista.get("/api/banco/planejamento/filtros").json()["empresas"][0]["id"] == "EMP001"
    numeros = especialista.get("/api/banco/planejamento?empresa_id=EMP001").json()
    assert numeros["indicadores"]["empresas_integradas"] == 1
    # Sem as taxas: a simulação espera; com as três: o total em texto
    sem_taxa = especialista.post("/api/banco/planejamento/ganho", json={"filtros": {}, "clientes_da_empresa": 35}).json()
    assert sem_taxa["simulacao"]["total"] is None
    premissas = dict(TAXAS_DE_TESTE)
    ganho = especialista.post("/api/banco/planejamento/ganho", json={"filtros": {}, "premissas": premissas,
                                                                     "clientes_da_empresa": 35}).json()
    assert ganho["simulacao"]["total"]
    # Simulação salva (com nome) e listada
    pedido = {"nome": "Carteira a 15%", "filtros": {}, "premissas": premissas, "clientes_da_empresa": 35}
    assert especialista.post("/api/banco/planejamento/simulacoes", json=pedido).status_code == 200
    assert len(especialista.get("/api/banco/planejamento/simulacoes").json()) == 1


def test_api_simulacao_guarda_quem_simulou_e_a_versao_das_premissas(api_do_banco):
    """A simulação salva pela API registra o login de quem simulou, as taxas informadas e a versão das premissas."""
    especialista = entrar("especialista")
    # Salva uma simulação com a % novas contas de 20% informada pelo especialista
    pedido = {"nome": "Taxa de 20%", "filtros": {}, "premissas": {"percentual_novas_contas": "20"},
              "clientes_da_empresa": 35}
    assert especialista.post("/api/banco/planejamento/simulacoes", json=pedido).status_code == 200
    # A mais recente é a primeira da lista
    ultima = especialista.get("/api/banco/planejamento/simulacoes").json()[0]
    # Quem simulou vem da sessão, nunca do pedido
    assert ultima["usuario"] == "especialista"
    # A taxa é a informada (20%) e as premissas partiram da versão 1
    assert ultima["valores"]["percentual_novas_contas"] == "20.00"
    assert ultima["versao_premissas"] == "v1" and ultima["nome"] == "Taxa de 20%"


def test_api_a_rota_do_consultor_saiu_para_todos_os_perfis(api_do_banco):
    """O Consultor saiu do sistema (ADR-144): a rota antiga não responde a ninguém, e nunca com erro 500."""
    # O especialista (que era quem perguntava), o RH de uma empresa e alguém sem login
    navegadores = {"banco": entrar("especialista"), "empresa": entrar("rh.aurora"), "sem login": TestClient(aplicacao)}
    for quem, navegador in navegadores.items():
        # A pergunta que antes ia ao Consultor
        resposta = navegador.post("/api/banco/consultor", json={"pergunta": "Quantas contas preciso abrir?"})
        # 405: o endereço não é mais uma rota da API (sobra só a pasta das páginas, que não aceita POST). Sem login,
        # o porteiro responde 401 antes de procurar a rota, como em todo endereço da API (achado A-19)
        codigo_esperado = 401 if quem == "sem login" else 405
        assert resposta.status_code == codigo_esperado, quem
        # Nada de resposta de agente: nenhum texto nem situação volta
        assert "situacao" not in resposta.text, quem


def test_api_inicio_do_banco_e_telemetria_por_perfil(api_do_banco):
    especialista = entrar("especialista")
    inicio = especialista.get("/api/banco/inicio")
    assert inicio.status_code == 200 and len(inicio.json()["carteira"]) == 6
    # A aba Telemetria (uso das empresas e desempenho da IA) é do especialista
    for rota in ["/api/banco/telemetria/ia", "/api/banco/telemetria/uso"]:
        assert especialista.get(rota).status_code == 200
        assert TestClient(aplicacao).get(rota).status_code == 401
    uso = especialista.get("/api/banco/telemetria/uso")
    assert uso.status_code == 200 and len(uso.json()["empresas"]) == 6
    # As fichas das empresas e a desativação de uma pessoa do RH (que perde a sessão na hora)
    rh = entrar("rh.aurora")
    fichas = especialista.get("/api/banco/empresas")
    assert fichas.status_code == 200 and fichas.json()[0]["usuarios"][0]["login"] == "rh.aurora"
    rota = "/api/banco/empresas/usuarios/rh.aurora/situacao"
    assert especialista.post(rota, json={"ativo": False}).status_code == 200
    assert rh.get("/api/empresa/resumo").status_code == 401
    assert especialista.post(rota, json={"ativo": True}).status_code == 200
    assert especialista.post("/api/banco/empresas/usuarios/especialista/situacao", json={"ativo": False}).status_code == 400


def test_api_do_banco_recusa_a_empresa_e_quem_nao_entrou(api_do_banco):
    rh = entrar("rh.aurora")
    anonimo = TestClient(aplicacao)
    for rota in ["/api/banco/planejamento", "/api/banco/planejamento/filtros", "/api/banco/planejamento/simulacoes",
                 "/api/banco/inicio", "/api/banco/telemetria/uso", "/api/banco/telemetria/ia", "/api/banco/empresas"]:
        assert rh.get(rota).status_code == 403
        assert anonimo.get(rota).status_code == 401
    assert rh.post("/api/banco/empresas/usuarios/rh.aurora/situacao", json={"ativo": False}).status_code == 403
