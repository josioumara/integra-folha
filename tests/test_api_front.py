"""Testes da API do novo front (ADR-69): entrar, sair, "quem sou eu" e o porteiro das páginas.

Usa o TestClient do FastAPI: um "navegador de mentira" que faz os pedidos direto na aplicação, sem ligar
servidor, e guarda os cookies entre um pedido e outro, como um navegador de verdade.
O banco é o temporário dos testes (tests/conftest.py): os usuários da demo nunca são tocados.
"""
import time

import pytest
from fastapi.testclient import TestClient

from api.principal import (ENDERECOS_PUBLICOS, MENSAGEM_LOGIN_RECUSADO, PAGINA_INICIAL_DO_PERFIL,
                           PAGINAS_OCULTAS_NESTA_VERSAO, PASTA_DO_FRONT, aplicacao, pagina_permitida,
                           tela_no_lugar_da_pagina_oculta)
from models.contratos import Perfil
from services import auth, sessoes

# Senha usada pelos usuários de teste (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"


@pytest.fixture(scope="module", autouse=True)
def usuarios_de_teste():
    """Cadastra um usuário de cada perfil (e um desativado) no banco temporário, uma vez para este arquivo."""
    # Abre o banco temporário dos testes
    conexao = auth.conectar()
    # Um usuário de cada perfil
    auth.cadastrar_usuario(conexao, "api.empresa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "api.banco", SENHA_DE_TESTE, Perfil.BANCO)
    # Um usuário desativado, que não pode entrar
    auth.cadastrar_usuario(conexao, "api.desativado", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.definir_ativo(conexao, "api.desativado", False)
    conexao.close()


def navegador_logado(login):
    """Um navegador de mentira já logado com o usuário informado."""
    # Navegador novo, sem cookies; follow_redirects=False para os testes enxergarem os desvios do porteiro
    navegador = TestClient(aplicacao, follow_redirects=False)
    # Entra
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    # O login precisa ter dado certo para o teste seguir
    assert resposta.status_code == 200
    return navegador


def test_login_certo_devolve_perfil_e_pagina_inicial_de_cada_perfil():
    # Cada perfil vai para a sua página inicial
    esperado = {"api.empresa": "home.html", "api.banco": "banco_inicio.html"}
    for login, pagina in esperado.items():
        navegador = TestClient(aplicacao)
        # O espaço nas pontas do usuário é ignorado (quem copia o login costuma trazer um espaço junto)
        resposta = navegador.post("/api/entrar", json={"usuario": " " + login + " ", "senha": SENHA_DE_TESTE})
        assert resposta.status_code == 200
        assert resposta.json()["pagina_inicial"] == pagina


def test_login_certo_grava_cookie_httponly_e_samesite_strict():
    navegador = TestClient(aplicacao)
    resposta = navegador.post("/api/entrar", json={"usuario": "api.banco", "senha": SENHA_DE_TESTE})
    # O cabeçalho que grava o cookie
    cabecalho = resposta.headers["set-cookie"].lower()
    assert cabecalho.startswith(sessoes.NOME_COOKIE + "=")
    assert "httponly" in cabecalho
    assert "samesite=strict" in cabecalho


def test_o_cookie_e_sempre_de_sessao_mesmo_com_o_lembrar_de_uma_tela_antiga():
    """Sem o "Lembrar de mim", o cookie nunca tem max-age: some ao fechar o navegador.

    Uma tela antiga guardada no navegador ainda pode mandar "lembrar": True; o login funciona e o campo é ignorado.
    """
    # Login comum, como a tela de hoje manda
    comum = TestClient(aplicacao).post("/api/entrar", json={"usuario": "api.banco", "senha": SENHA_DE_TESTE})
    assert comum.status_code == 200
    assert "max-age" not in comum.headers["set-cookie"].lower()
    # Login com o campo antigo: entra, e o cookie continua sendo de sessão
    antigo = TestClient(aplicacao).post("/api/entrar", json={"usuario": "api.banco", "senha": SENHA_DE_TESTE,
                                                             "lembrar": True})
    assert antigo.status_code == 200
    assert "max-age" not in antigo.headers["set-cookie"].lower()


def test_a_sessao_vale_8_horas():
    """A sessão ainda vale 7 horas depois do login e já não vale com 9 horas (não existe mais a de 7 dias)."""
    from datetime import datetime, timedelta, timezone
    conexao = auth.conectar()
    # O momento do login
    agora = datetime.now(timezone.utc)
    ingresso = sessoes.criar_sessao(conexao, "api.banco", agora=agora)
    # Dentro das 8 horas vale; depois, não
    assert sessoes.validar_sessao(conexao, ingresso, agora=agora + timedelta(hours=7)) is not None
    assert sessoes.validar_sessao(conexao, ingresso, agora=agora + timedelta(hours=9)) is None
    assert sessoes.VALIDADE_HORAS == 8
    conexao.close()


def test_resposta_do_login_nunca_traz_senha_nem_ingresso():
    navegador = TestClient(aplicacao)
    resposta = navegador.post("/api/entrar", json={"usuario": "api.empresa", "senha": SENHA_DE_TESTE})
    # Só login, perfil, empresa, página inicial e a marca de senha provisória (verdadeiro ou falso, nunca a senha)
    assert set(resposta.json()) == {"login", "perfil", "empresa_id", "pagina_inicial", "senha_provisoria"}
    assert resposta.json()["senha_provisoria"] is False
    # O ingresso do cookie não aparece no corpo da resposta
    assert navegador.cookies.get(sessoes.NOME_COOKIE) not in resposta.text


def test_senha_errada_usuario_inexistente_e_desativado_recebem_a_mesma_mensagem():
    navegador = TestClient(aplicacao)
    tentativas = [("api.empresa", "senha-errada-123"), ("nao.existe", SENHA_DE_TESTE), ("api.desativado", SENHA_DE_TESTE)]
    for login, senha in tentativas:
        resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": senha})
        # Sempre 401 com a mesma mensagem: não revela se o usuário existe
        assert resposta.status_code == 401
        assert resposta.json()["detail"] == MENSAGEM_LOGIN_RECUSADO
        # E nenhum cookie é gravado
        assert "set-cookie" not in resposta.headers


def test_pedido_de_login_sem_senha_e_recusado_pelo_formato():
    navegador = TestClient(aplicacao)
    # O FastAPI confere o formato: faltando a senha, nem chega a consultar o banco
    resposta = navegador.post("/api/entrar", json={"usuario": "api.empresa"})
    assert resposta.status_code == 422


def test_quem_sou_eu_sem_login_e_401_e_com_login_devolve_o_usuario():
    # Sem login
    assert TestClient(aplicacao).get("/api/eu").status_code == 401
    # Com login
    resposta = navegador_logado("api.empresa").get("/api/eu")
    assert resposta.status_code == 200
    assert resposta.json()["login"] == "api.empresa"
    assert resposta.json()["empresa_id"] == "EMP001"


def test_sair_cancela_a_sessao_mesmo_para_quem_copiou_o_ingresso():
    navegador = navegador_logado("api.banco")
    # Alguém copia o ingresso antes de a pessoa sair
    ingresso_copiado = navegador.cookies.get(sessoes.NOME_COOKIE)
    # A pessoa sai: volta ao login
    resposta = navegador.get("/api/sair")
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login.html"
    # O ingresso copiado não vale mais
    outro_navegador = TestClient(aplicacao)
    outro_navegador.cookies.set(sessoes.NOME_COOKIE, ingresso_copiado)
    assert outro_navegador.get("/api/eu").status_code == 401


def test_login_e_aparencia_abrem_sem_login():
    navegador = TestClient(aplicacao, follow_redirects=False)
    # A tela de login, o css e o js abrem para quem ainda não entrou
    for endereco in ["/login.html", "/css/estilos.css", "/js/login.js"]:
        assert navegador.get(endereco).status_code == 200
    # A raiz do site leva ao login
    assert navegador.get("/").headers["location"] == "/login.html"


def test_pagina_sem_login_volta_ao_login():
    navegador = TestClient(aplicacao, follow_redirects=False)
    for pagina in ["/home.html", "/banco_inicio.html", "/banco_indicadores.html", "/banco_agentes.html"]:
        resposta = navegador.get(pagina)
        assert resposta.status_code == 303
        assert resposta.headers["location"] == "/login.html"


def test_variacoes_do_endereco_nao_passam_pelo_porteiro():
    """Maiúsculas, ponto ou barra no fim e caminhos desconhecidos também exigem login."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    for endereco in ["/HOME.HTML", "/Home.html", "/home.html.", "/banco_inicio.html/", "/qualquer_coisa",
                     "/CSS/../home.html", "/favicon.ico"]:
        resposta = navegador.get(endereco)
        assert resposta.status_code == 303, endereco
        assert resposta.headers["location"] == "/login.html"


def test_buscadores_nao_indexam_nada_e_a_api_nao_se_descreve():
    """robots.txt proíbe tudo; toda resposta (página, desvio, API, css) leva o X-Robots-Tag; sem /openapi.json."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    robots = navegador.get("/robots.txt")
    assert robots.status_code == 200 and "Disallow: /" in robots.text
    for endereco in ["/login.html", "/home.html", "/api/eu", "/css/estilos.css", "/"]:
        assert navegador.get(endereco).headers["x-robots-tag"] == "noindex, nofollow, noarchive", endereco
    # A descrição automática das rotas da API não fica pública
    assert navegador.get("/openapi.json").status_code in (303, 404)
    # Cada página também traz a marca para os buscadores
    for pagina in PASTA_DO_FRONT.glob("*.html"):
        assert 'name="robots" content="noindex, nofollow, noarchive"' in pagina.read_text(encoding="utf-8"), pagina.name


def test_empresa_nao_abre_pagina_do_banco_e_volta_para_a_propria():
    navegador = navegador_logado("api.empresa")
    # A página da empresa abre
    assert navegador.get("/acompanhar.html").status_code == 200
    # A do banco não: volta para a home da empresa
    for pagina in ["/banco_inicio.html", "/banco_envios.html", "/banco_indicadores.html", "/banco_agentes.html"]:
        resposta = navegador.get(pagina)
        assert resposta.status_code == 303
        assert resposta.headers["location"] == "/home.html"


def test_banco_abre_as_paginas_do_banco():
    navegador = navegador_logado("api.banco")
    # As 7 páginas do banco à vista abrem: as 5 do menu (Indicadores junta as antigas Planejamento e Telemetria) e as 2
    # do Sistema, no menu da engrenagem do alto (os Parâmetros do layout e o Acompanhamento dos agentes). As Premissas
    # financeiras estão ocultas nesta versão (ADR-148): o teste delas está logo abaixo
    for pagina in ["banco_inicio", "banco_empresas", "banco_envios", "banco_endomarketing", "banco_indicadores",
                   "banco_parametros", "banco_agentes"]:
        assert navegador.get("/" + pagina + ".html").status_code == 200
    # As da empresa não
    assert navegador.get("/home.html").headers["location"] == "/banco_inicio.html"


def test_so_existem_os_perfis_da_empresa_e_do_banco():
    """Nesta versão, o banco tem a gestão completa; o perfil CIENTISTA saiu (ADR-78)."""
    perfis = []
    for perfil in Perfil:
        perfis.append(perfil.value)
    assert perfis == ["EMPRESA", "BANCO"]
    # O banco abre os Indicadores e o Acompanhamento dos agentes (o antigo Desempenho da IA); a empresa, não
    assert navegador_logado("api.banco").get("/banco_indicadores.html").status_code == 200
    assert navegador_logado("api.empresa").get("/banco_indicadores.html").status_code != 200
    assert navegador_logado("api.banco").get("/banco_agentes.html").status_code == 200
    assert navegador_logado("api.empresa").get("/banco_agentes.html").status_code != 200


def test_premissas_financeiras_ocultas_levam_o_banco_aos_indicadores():
    """As Premissas financeiras ficam ocultas nesta versão (ADR-148): o banco, dono da tela, vai para os Indicadores; a
    empresa continua voltando para a home dela; quem não entrou continua voltando ao login."""
    do_banco = navegador_logado("api.banco").get("/banco_premissas.html")
    assert do_banco.status_code == 303
    assert do_banco.headers["location"] == "/banco_indicadores.html"
    da_empresa = navegador_logado("api.empresa").get("/banco_premissas.html")
    assert da_empresa.status_code == 303
    assert da_empresa.headers["location"] == "/home.html"
    sem_login = TestClient(aplicacao, follow_redirects=False).get("/banco_premissas.html")
    assert sem_login.status_code == 303
    assert sem_login.headers["location"] == "/login.html"


@pytest.mark.parametrize("endereco", ["/banco_premissas.html/", "/banco_premissas.html.", "/banco_premissas.html ",
                                      "/banco_Premissas.html", "/banco_premissas.HTML", "/banco_premissas.html/."])
def test_variacoes_do_endereco_da_pagina_oculta_tambem_levam_aos_indicadores(endereco):
    """As variações que o Windows abre como o mesmo arquivo (barra, ponto ou espaço no fim; maiúsculas no meio) não
    mostram a página oculta: o banco vai para os Indicadores. Nenhuma delas deixa de exigir login."""
    do_banco = navegador_logado("api.banco").get(endereco)
    assert do_banco.status_code == 303, endereco
    assert do_banco.headers["location"] == "/banco_indicadores.html", endereco
    sem_login = TestClient(aplicacao, follow_redirects=False).get(endereco)
    assert sem_login.headers["location"] == "/login.html", endereco


def test_tela_no_lugar_da_pagina_oculta_pagina_por_pagina():
    """A regra das páginas ocultas (ADR-148), direto na função: só a lista de ocultas desvia; o resto segue."""
    assert tela_no_lugar_da_pagina_oculta("/banco_premissas.html") == "banco_indicadores.html"
    assert tela_no_lugar_da_pagina_oculta("/BANCO_PREMISSAS.HTML/") == "banco_indicadores.html"
    # As outras telas do banco e da empresa não estão ocultas
    for endereco in ["/banco_parametros.html", "/banco_indicadores.html", "/banco_agentes.html", "/home.html",
                     "/banco_premissas.html.bak", "/banco_premissas", "/"]:
        assert tela_no_lugar_da_pagina_oculta(endereco) is None, endereco
    # A tela de volta de cada página oculta existe e é do mesmo perfil (ninguém cai numa página que não abre)
    for pagina_oculta, tela_de_volta in PAGINAS_OCULTAS_NESTA_VERSAO.items():
        assert (PASTA_DO_FRONT / pagina_oculta).exists() and (PASTA_DO_FRONT / tela_de_volta).exists()
        for perfil in Perfil:
            assert pagina_permitida(perfil, pagina_oculta) == pagina_permitida(perfil, tela_de_volta)


def test_pagina_guardada_pelo_porteiro_nao_pode_ficar_no_cache_do_navegador():
    # Sem isto, depois do "Sair" o navegador mostrava a cópia guardada sem perguntar ao servidor
    navegador = navegador_logado("api.banco")
    resposta = navegador.get("/banco_inicio.html")
    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "no-store"


def test_arquivo_fora_da_pasta_do_front_nunca_e_entregue():
    navegador = navegador_logado("api.banco")
    # Tentativas de sair da pasta front/ para pegar o .env ou o código
    for endereco in ["/../.env", "/..%2F.env", "/%2e%2e/api/principal.py"]:
        resposta = navegador.get(endereco)
        # Recusado pelo servidor de arquivos (400/404) ou desviado antes pelo porteiro (303, lista de liberação)
        assert resposta.status_code in (303, 400, 404)
        assert "OPENAI_API_KEY" not in resposta.text


def test_regra_do_porteiro_pagina_por_pagina():
    # A tabela da regra, direto na função (sem servidor)
    assert pagina_permitida(Perfil.EMPRESA, "cadastrar.html")
    assert not pagina_permitida(Perfil.EMPRESA, "banco_empresas.html")
    assert pagina_permitida(Perfil.BANCO, "banco_empresas.html")
    assert pagina_permitida(Perfil.BANCO, "banco_indicadores.html")
    assert not pagina_permitida(Perfil.EMPRESA, "banco_indicadores.html")
    assert pagina_permitida(Perfil.BANCO, "banco_agentes.html")
    assert not pagina_permitida(Perfil.EMPRESA, "banco_agentes.html")
    assert pagina_permitida(Perfil.BANCO, "banco_premissas.html")
    assert not pagina_permitida(Perfil.EMPRESA, "banco_premissas.html")
    # Página que não existe na lista: ninguém abre, nem o banco nem a empresa
    assert not pagina_permitida(Perfil.BANCO, "qualquer.html")
    assert not pagina_permitida(Perfil.EMPRESA, "qualquer.html")


def paginas_do_front() -> list[str]:
    """Os nomes de todas as páginas do front que exigem login (todas as .html da pasta front/, menos as públicas: a de
    login e as de privacidade e de termos de uso, que estão em ENDERECOS_PUBLICOS).

    Exemplo: ["acompanhar.html", "banco_empresas.html", ..., "home.html"].
    """
    # A lista de páginas, em ordem alfabética, para o resultado do teste sair sempre igual
    nomes_das_paginas = []
    for pagina in sorted(PASTA_DO_FRONT.glob("*.html")):
        # As páginas públicas abrem para todos: ficam fora da lista
        if "/" + pagina.name not in ENDERECOS_PUBLICOS:
            nomes_das_paginas.append(pagina.name)
    return nomes_das_paginas


def test_toda_pagina_do_front_tem_exatamente_um_perfil_dono():
    """Toda página nova precisa entrar na regra do porteiro; página sem dono ninguém abriria (e ninguém perceberia).

    Substitui o antigo "toda tela tem arquivo e permissão" do Streamlit (saiu com o Streamlit, ADR-108).
    """
    for nome_da_pagina in paginas_do_front():
        # Os perfis que podem abrir esta página
        perfis_que_abrem = []
        for perfil in Perfil:
            if pagina_permitida(perfil, nome_da_pagina):
                perfis_que_abrem.append(perfil)
        # Cada página é de um perfil só: da empresa ou do banco
        assert len(perfis_que_abrem) == 1, nome_da_pagina


@pytest.mark.parametrize("nome_da_pagina", paginas_do_front())
def test_cada_pagina_abre_so_para_o_dono_e_nunca_sem_login(nome_da_pagina):
    """Página por página: o perfil dono abre; o outro perfil volta para a própria página inicial; sem login, ao login.
    Uma página oculta nesta versão (ADR-148) leva o dono para a tela que fica no lugar dela.

    Substitui o "cada tela × perfil" e o "sem login nenhuma tela abre" que rodavam nas telas do Streamlit.
    """
    endereco = "/" + nome_da_pagina
    # Sem login: sempre de volta ao login
    sem_login = TestClient(aplicacao, follow_redirects=False).get(endereco)
    assert sem_login.status_code == 303
    assert sem_login.headers["location"] == "/login.html"
    # Um navegador logado de cada perfil
    logins_por_perfil = {Perfil.EMPRESA: "api.empresa", Perfil.BANCO: "api.banco"}
    for perfil, login in logins_por_perfil.items():
        resposta = navegador_logado(login).get(endereco)
        if pagina_permitida(perfil, nome_da_pagina) and nome_da_pagina in PAGINAS_OCULTAS_NESTA_VERSAO:
            # O dono de uma página oculta vai para a tela que fica no lugar dela
            assert resposta.status_code == 303, login
            assert resposta.headers["location"] == "/" + PAGINAS_OCULTAS_NESTA_VERSAO[nome_da_pagina], login
        elif pagina_permitida(perfil, nome_da_pagina):
            # O dono da página abre
            assert resposta.status_code == 200, login
        else:
            # O outro perfil é desviado para a própria página inicial
            assert resposta.status_code == 303, login
            assert resposta.headers["location"] == "/" + PAGINA_INICIAL_DO_PERFIL[perfil]


def test_tela_de_parametros_so_do_banco_grava_versao_e_registra_quem_mudou_o_que():
    """A tela Parâmetros: só o BANCO abre; gravar cria uma versão nova com o registro de quem, quando e o quê."""
    # A empresa não mexe no layout
    assert navegador_logado("api.empresa").get("/api/banco/parametros/layout").status_code == 403
    banco = navegador_logado("api.banco")
    tela = banco.get("/api/banco/parametros/layout").json()
    assert "CPF" in tela["tipos"] and tela["registro"][0]["versao"] == tela["versao"]
    campos_originais = tela["campos"]
    # Sem mudança: nada é gravado
    assert banco.post("/api/banco/parametros/layout", json={"campos": campos_originais}).status_code == 400
    # Marca o CNPJ do empregador como dado pessoal protegido
    campos_novos = []
    for campo in campos_originais:
        campo_novo = dict(campo)
        if campo["campo"] == "cnpj_empregador":
            campo_novo["sensivel"] = True
        campos_novos.append(campo_novo)
    gravado = banco.post("/api/banco/parametros/layout", json={"campos": campos_novos})
    assert gravado.status_code == 200, gravado.text
    ultima = gravado.json()["registro"][0]
    assert gravado.json()["versao"] == tela["versao"] + 1
    assert ultima["criado_por"] == "api.banco"
    assert ultima["mudancas"] == ["cnpj_empregador · dado pessoal (LGPD): não → sim"]
    # Tipo fora do catálogo: recusado com o nome do campo
    campos_errados = []
    for campo in campos_originais:
        campo_errado = dict(campo)
        if campo["campo"] == "cargo":
            campo_errado["tipo"] = "INVENTADO"
        campos_errados.append(campo_errado)
    recusado = banco.post("/api/banco/parametros/layout", json={"campos": campos_errados})
    assert recusado.status_code == 400 and "cargo" in recusado.json()["detail"]
    # Volta ao layout original (outra versão, também registrada)
    assert banco.post("/api/banco/parametros/layout", json={"campos": campos_originais}).status_code == 200


def test_gravar_o_layout_refaz_o_indice_da_ia_so_com_os_indices_vivos_ligados(monkeypatch):
    """Nos testes (índices vivos desligados), gravar não mexe no índice de verdade; ligados, a reconstrução começa."""
    from rag import busca, indice_do_layout
    # Desligados: não começa
    assert indice_do_layout.refazer_em_segundo_plano(1, []) is False
    # Ligados: começa em segundo plano (aqui, com a reconstrução trocada por uma que só anota)
    chamadas = []
    monkeypatch.setattr(busca, "_consultar_mapeamentos_aprovados", True)
    monkeypatch.setattr(indice_do_layout, "_refazer_sem_quebrar", lambda versao, campos: chamadas.append(versao))
    assert indice_do_layout.refazer_em_segundo_plano(7, []) is True
    for _ in range(50):
        if chamadas:
            break
        time.sleep(0.05)
    assert chamadas == [7]


def test_quadro_de_contas_explica_onde_ver_a_conta_de_cada_funcionario():
    """ADR-102: a conta de cada funcionário aparece na lista, com a autorização do funcionário pela Lei Complementar."""
    pagina = navegador_logado("api.empresa").get("/acompanhar.html").text
    assert "Lei Complementar nº 105/2001" in pagina and "grupos de 10 pessoas ou mais" not in pagina
    assert "<th scope=\"col\">Conta salário</th>" in pagina
    # A nota fica sempre à mostra: nenhum script a esconde
    script = (PASTA_DO_FRONT / "js" / "acompanhar.js").read_text(encoding="utf-8")
    assert "[data-nota-sigilo]\").hidden = true" not in script
    # A etapa 4 da Home aponta onde ver a conta de cada um
    texto_da_home = (PASTA_DO_FRONT / "js" / "home_real.js").read_text(encoding="utf-8")
    assert "a conta salário de cada funcionário está em Acompanhar" in texto_da_home


def test_a_ajuda_de_parametros_diz_unico_por_funcionario():
    """A ajuda da marcação "Igual para todos" diz que os outros campos (o CPF, o nome...) são únicos por funcionário."""
    pagina = navegador_logado("api.banco").get("/banco_parametros.html").text
    # O texto novo aparece, e o antigo não
    assert "Os outros campos são únicos por funcionário" in pagina
    assert "Os outros campos são de cada pessoa" not in pagina


# ---------------- Senha provisória: troca obrigatória e nova senha pelo banco (ADR-109) ----------------

def _entrar_com(login: str, senha: str):
    """Um navegador de mentira que tenta entrar com o login e a senha informados. Devolve (navegador, resposta)."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": senha})
    return navegador, resposta


def test_senha_provisoria_so_libera_cabecalho_e_troca_de_senha():
    """Com a senha provisória, os dados ficam fechados até a própria pessoa trocá-la; depois, tudo abre."""
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "api.provisoria", "provisoria-123", Perfil.EMPRESA, "EMP001", senha_provisoria=True)
    conexao.close()
    navegador, resposta = _entrar_com("api.provisoria", "provisoria-123")
    # O login avisa que a senha é provisória
    assert resposta.json()["senha_provisoria"] is True
    # Nenhum dado da empresa sai para esta sessão
    assert navegador.get("/api/empresa/resumo").status_code == 403
    # O cabeçalho responde e diz para abrir a troca obrigatória
    assert navegador.get("/api/cabecalho").json()["senha_provisoria"] is True
    # Trocar pela mesma senha provisória não vale
    mesma = {"senha_atual": "provisoria-123", "nova_senha": "provisoria-123", "confirmacao": "provisoria-123"}
    assert navegador.post("/api/minha-senha", json=mesma).status_code == 400
    # Trocar por uma senha só dela libera a mesma sessão
    nova = {"senha_atual": "provisoria-123", "nova_senha": "so-minha-4567", "confirmacao": "so-minha-4567"}
    assert navegador.post("/api/minha-senha", json=nova).status_code == 200
    assert navegador.get("/api/cabecalho").json()["senha_provisoria"] is False
    assert navegador.get("/api/empresa/resumo").status_code == 200


def test_banco_gera_nova_senha_provisoria_e_a_pessoa_sai_na_hora():
    """O banco gera uma senha nova para quem esqueceu: a sessão antiga cai, a senha antiga para de valer, e a nova
    entra como provisória."""
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "api.esqueceu", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao.close()
    pessoa = navegador_logado("api.esqueceu")
    resposta = navegador_logado("api.banco").post("/api/banco/empresas/usuarios/api.esqueceu/nova-senha")
    assert resposta.status_code == 200
    senha_nova = resposta.json()["senha_provisoria"]
    # A sessão que estava aberta caiu
    assert pessoa.get("/api/empresa/resumo").status_code == 401
    # A senha antiga não entra mais; a nova entra, marcada como provisória
    assert _entrar_com("api.esqueceu", SENHA_DE_TESTE)[1].status_code == 401
    assert _entrar_com("api.esqueceu", senha_nova)[1].json()["senha_provisoria"] is True


def test_so_o_banco_gera_nova_senha_e_so_para_pessoa_de_empresa():
    """A empresa não gera senha para ninguém, e o banco não usa esta porta para mexer em outro usuário do banco."""
    assert navegador_logado("api.empresa").post("/api/banco/empresas/usuarios/api.empresa/nova-senha").status_code == 403
    assert navegador_logado("api.banco").post("/api/banco/empresas/usuarios/api.banco/nova-senha").status_code == 400


def test_colunas_da_grade_para_a_empresa_e_para_o_banco():
    """As duas telas da grade (ADR-111) recebem as mesmas colunas; cada perfil só pela rota dele."""
    empresa = navegador_logado("api.empresa")
    banco = navegador_logado("api.banco")
    colunas_da_empresa = empresa.get("/api/empresa/colunas_da_consulta").json()
    assert colunas_da_empresa == banco.get("/api/banco/colunas_da_consulta").json()
    assert empresa.get("/api/banco/colunas_da_consulta").status_code == 403
    assert banco.get("/api/empresa/colunas_da_consulta").status_code == 403


def test_js_e_css_sao_sempre_conferidos_com_o_servidor():
    """O navegador pergunta "mudou?" antes de usar a cópia guardada do js e do css (senão a tela nova não aparece)."""
    navegador = TestClient(aplicacao)
    assert navegador.get("/js/grade_do_parametro.js").headers["Cache-Control"] == "no-cache"
    assert navegador.get("/css/estilos.css").headers["Cache-Control"] == "no-cache"


def test_visao_geral_da_empresa_so_para_o_banco_e_com_o_acesso_registrado():
    """Aba Empresas do banco (ADR-112): os números e a lista de funcionários; a empresa não usa esta porta; empresa
    inexistente dá 404; cada abertura fica registrada nos acessos da empresa."""
    from services import acompanhamento
    banco = navegador_logado("api.banco")
    resposta = banco.get("/api/banco/empresas/EMP001/visao_geral")
    assert resposta.status_code == 200 and resposta.headers["Cache-Control"] == "no-store"
    visao = resposta.json()
    assert set(visao) == {"resumo", "contas", "funcionarios"} and "cadastrados" in visao["resumo"]
    # As pessoas em análise pelo banco batem com a lista da própria visão
    em_analise_na_lista = 0
    for pessoa in visao["funcionarios"]:
        if pessoa["situacao"] == "Em análise":
            em_analise_na_lista = em_analise_na_lista + 1
    assert visao["resumo"]["pessoas_em_analise"] == em_analise_na_lista
    conexao = auth.conectar()
    ultimo_acesso = acompanhamento.acessos_da_empresa(conexao, "EMP001")[-1]
    conexao.close()
    assert (ultimo_acesso["login"], ultimo_acesso["tipo"]) == ("api.banco", "LISTA")
    assert navegador_logado("api.empresa").get("/api/banco/empresas/EMP001/visao_geral").status_code == 403
    assert banco.get("/api/banco/empresas/NAO_EXISTE/visao_geral").status_code == 404
