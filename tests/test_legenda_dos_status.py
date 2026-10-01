"""A legenda dos status: o "i" em cima das grades explica cada situação, com os textos numa fonte única no servidor.

O que estes testes provam:
- cada grade tem as situações com o texto do selo, a cor e a explicação; nenhuma explicação atribui ação à "IA";
- toda situação que o servidor produz (funcionários, colunas, empresas da carteira) tem a explicação dela;
- as situações que nascem na tela (usuários, pessoas do envio, duas das colunas e a conferência) têm o mesmo texto e a
  mesma cor na legenda e no JavaScript: se alguém mudar um lado só, o teste avisa;
- nenhuma explicação fica escrita no JavaScript (a fonte é só o servidor);
- as rotas: 401 sem login; 403 para o outro perfil; a empresa recebe só as grades dela, e duas empresas recebem o mesmo
  texto (não há dado de empresa nenhuma na legenda).
A tela (o "i", o balão, o mouse, o clique e o teclado) tem o roteiro de clique legenda_dos_status.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, auth, cadastro, contas_abertas, legenda_dos_status, portal_do_banco
from services import empresas as cadastro_de_empresas

# A pasta do front, para ler o JavaScript e o CSS que as telas usam
PASTA_DO_FRONT = Path(__file__).resolve().parent.parent / "front"
# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# As grades de cada portal
GRADES_DO_BANCO = {"empresas", "funcionarios", "usuarios", "pessoas_do_envio"}
GRADES_DA_EMPRESA = {"funcionarios", "colunas", "conferencia"}
# Os selos que só o protótipo mostra (a página aberta como arquivo, com os exemplos): com os dados de verdade, o
# usuário criado pelo banco já nasce com a senha provisória ("Senha resetada"), e nenhuma pessoa do envio fica
# "aguardando" (ver js/banco_empresas_real.js e js/banco_envios_real.js). Por isso eles ficam fora da legenda.
SELOS_SO_DO_PROTOTIPO = {"convite", "aguardando"}
# A palavra "IA" sozinha (\b é a borda da palavra: não casa dentro de "média" nem de "IAS")
PALAVRA_IA = re.compile(r"\bIA\b")


def ler_do_front(caminho_relativo: str) -> str:
    """O conteúdo de um arquivo do front, como texto. Ex.: ler_do_front("js/banco_envios.js")."""
    return (PASTA_DO_FRONT / caminho_relativo).read_text(encoding="utf-8")


def trecho_entre(texto: str, comeco: str, fim: str) -> str:
    """O pedaço do texto que começa em "comeco" e vai até o primeiro "fim" depois dele.

    Ex.: trecho_entre(js, "const SELOS_DOS_USUARIOS = {", "};") → o bloco inteiro do dicionário.
    """
    posicao_do_comeco = texto.index(comeco)
    posicao_do_fim = texto.index(fim, posicao_do_comeco)
    return texto[posicao_do_comeco:posicao_do_fim]


def pares_da_legenda(situacoes: list[dict]) -> set:
    """Os pares (texto, cor) de uma lista de situações. Ex.: {("Ativo", "selo-sucesso"), ...}."""
    pares = set()
    for situacao in situacoes:
        pares.add((situacao["texto"], situacao["classe"]))
    return pares


def selos_do_dicionario_do_js(bloco: str) -> dict:
    """Os selos de um dicionário do JavaScript no formato "codigo": { texto: "...", classe: "..." }.

    Recebe: bloco — o trecho do dicionário. Devolve: {codigo: (texto, classe)}.
    Ex.: '"ativo": { texto: "Ativo", classe: "selo-sucesso" }' → {"ativo": ("Ativo", "selo-sucesso")}.
    """
    selos = {}
    for codigo, texto, classe in re.findall(r'"([a-z_]+)": \{ texto: "([^"]+)", classe: "([^"]+)" \}', bloco):
        selos[codigo] = (texto, classe)
    return selos


def todas_as_legendas() -> list[dict]:
    """Todas as situações das duas rotas, numa lista só (a grade "funcionarios" aparece nas duas)."""
    situacoes = []
    for legendas in (legenda_dos_status.legendas_do_banco(), legenda_dos_status.legendas_da_empresa()):
        for lista_da_grade in legendas.values():
            situacoes.extend(lista_da_grade)
    return situacoes


# ---------------- A fonte única ----------------

def test_cada_portal_tem_as_suas_grades():
    assert set(legenda_dos_status.legendas_do_banco()) == GRADES_DO_BANCO
    # A empresa não recebe nada das grades do banco (a carteira, os usuários, a avaliação dos envios)
    assert set(legenda_dos_status.legendas_da_empresa()) == GRADES_DA_EMPRESA


def test_cada_situacao_tem_texto_cor_existente_e_explicacao_em_frase():
    estilos = ler_do_front("css/estilos.css")
    for situacao in todas_as_legendas():
        assert situacao["texto"].strip()
        # A cor é uma classe que existe no CSS de todas as telas
        assert "." + situacao["classe"] + " {" in estilos, situacao["classe"]
        # A explicação é uma frase: começa com maiúscula e termina com ponto
        explicacao = situacao["explicacao"]
        assert explicacao[0].isupper() and explicacao.endswith("."), explicacao


def test_nenhuma_explicacao_atribui_acao_a_ia():
    # Quem age é o agente, pelo nome (o Agente Interpretador, o Agente de validação...)
    for situacao in todas_as_legendas():
        assert PALAVRA_IA.search(situacao["explicacao"]) is None, situacao["explicacao"]


def test_uma_grade_nao_repete_situacao():
    for legendas in (legenda_dos_status.legendas_do_banco(), legenda_dos_status.legendas_da_empresa()):
        for grade, situacoes in legendas.items():
            textos = []
            for situacao in situacoes:
                textos.append(situacao["texto"])
            assert len(textos) == len(set(textos)), grade


def test_toda_situacao_de_funcionario_do_servidor_tem_explicacao():
    # As situações que services/acompanhamento.py dá a uma pessoa, mais as duas do tipo de conta (ADR-123)
    produzidas = {acompanhamento.SITUACAO_AGUARDANDO_ENVIO, acompanhamento.SITUACAO_PENDENTE,
                  acompanhamento.SITUACAO_EM_ANALISE, acompanhamento.SITUACAO_CADASTRADO}
    for texto_do_tipo in contas_abertas.SITUACAO_NA_EMPRESA_DO_TIPO.values():
        produzidas.add(texto_do_tipo)
    textos_da_legenda = set()
    for situacao in legenda_dos_status.situacoes_dos_funcionarios():
        textos_da_legenda.add(situacao["texto"])
    assert textos_da_legenda == produzidas


def test_toda_situacao_de_coluna_do_servidor_tem_explicacao():
    # As situações que services/cadastro.py dá a uma coluna lida
    produzidas = {cadastro.SITUACAO_AJUSTADA_PELA_EMPRESA, cadastro.SITUACAO_DIVIDIDA_PELA_IA,
                  cadastro.SITUACAO_PARTE_DA_IA, cadastro.SITUACAO_DIVIDIDA_PELA_EMPRESA}
    for texto_do_status in cadastro.SITUACAO_DA_COLUNA.values():
        # Cada status do mapeamento que a tela mostra (o DIVIDIR vira as situações das colunas divididas)
        produzidas.add(texto_do_status)
    textos_da_legenda = set()
    for situacao in legenda_dos_status.situacoes_das_colunas():
        textos_da_legenda.add(situacao["texto"])
    assert produzidas <= textos_da_legenda


def test_a_situacao_da_empresa_na_carteira_bate_com_a_legenda():
    # Um resumo de cada caso de services/portal_do_banco.py (_situacao_da_empresa): sem envio, com pendência, com
    # envio a caminho e em dia
    resumos = [
        {"envios": 0, "com_pendencia": 0, "em_andamento": 0},
        {"envios": 2, "com_pendencia": 1, "em_andamento": 1},
        {"envios": 2, "com_pendencia": 0, "em_andamento": 1},
        {"envios": 2, "com_pendencia": 0, "em_andamento": 0},
    ]
    produzidas = set()
    for resumo in resumos:
        situacao = portal_do_banco._situacao_da_empresa(resumo)
        produzidas.add((situacao["texto"], situacao["classe"]))
    # As 4 situações da carteira, com a mesma cor do selo da tela
    assert pares_da_legenda(legenda_dos_status.situacoes_das_empresas()) == produzidas


def test_os_prazos_dos_usuarios_vem_das_constantes_do_acesso():
    explicacoes = ""
    for situacao in legenda_dos_status.situacoes_dos_usuarios():
        explicacoes = explicacoes + situacao["explicacao"]
    # Os mesmos prazos que suspendem o acesso da empresa (ADR-146) e que vencem a senha provisória (ADR-154)
    assert str(auth.DIAS_SEM_USO_PARA_SUSPENDER) + " dias" in explicacoes
    assert str(auth.DIAS_DE_VALIDADE_DO_ACESSO) + " dias" in explicacoes
    assert str(auth.VALIDADE_DA_SENHA_PROVISORIA_HORAS) + " horas" in explicacoes


# ---------------- A legenda bate com o que a tela mostra ----------------

def test_os_status_dos_funcionarios_da_tela_batem_com_a_legenda():
    bloco = trecho_entre(ler_do_front("js/grade_do_parametro.js"), "const STATUS_DOS_FUNCIONARIOS = [", "];")
    pares_da_tela = set(re.findall(r'situacao: "([^"]+)", classe: "([^"]+)"', bloco))
    assert pares_da_tela == pares_da_legenda(legenda_dos_status.situacoes_dos_funcionarios())


def test_os_selos_dos_usuarios_da_tela_batem_com_a_legenda():
    bloco = trecho_entre(ler_do_front("js/banco_empresas.js"), "const SELOS_DOS_USUARIOS = {", "};")
    pares_da_tela = set()
    for codigo, par in selos_do_dicionario_do_js(bloco).items():
        if codigo not in SELOS_SO_DO_PROTOTIPO:
            pares_da_tela.add(par)
    assert pares_da_tela == pares_da_legenda(legenda_dos_status.situacoes_dos_usuarios())


def test_os_selos_das_pessoas_do_envio_da_tela_batem_com_a_legenda():
    bloco = trecho_entre(ler_do_front("js/banco_envios.js"), "const SELOS_DAS_SITUACOES = {", "};")
    pares_da_tela = set()
    for codigo, par in selos_do_dicionario_do_js(bloco).items():
        if codigo not in SELOS_SO_DO_PROTOTIPO:
            pares_da_tela.add(par)
    assert pares_da_tela == pares_da_legenda(legenda_dos_status.situacoes_das_pessoas_do_envio())


def test_as_situacoes_das_colunas_que_nascem_na_tela_batem_com_a_legenda():
    tela = ler_do_front("js/cadastrar_real.js")
    # "Fica de fora (não é obrigatória)", pintada de cinza
    assert 'SITUACAO_FICA_DE_FORA = "' + legenda_dos_status.COLUNA_FORA_POR_NAO_SER_OBRIGATORIA + '"' in tela
    assert 'pintar_selo(selo, SITUACAO_FICA_DE_FORA, "selo-neutro")' in tela
    # "Ajustado · confira o tipo", pintada de laranja
    assert ('pintar_selo(selo, "' + legenda_dos_status.COLUNA_AJUSTADA_COM_TIPO_A_CONFERIR + '", "selo-atencao")'
            in tela)
    # As duas estão na legenda com essas cores
    pares = pares_da_legenda(legenda_dos_status.situacoes_das_colunas())
    assert (legenda_dos_status.COLUNA_FORA_POR_NAO_SER_OBRIGATORIA, "selo-neutro") in pares
    assert (legenda_dos_status.COLUNA_AJUSTADA_COM_TIPO_A_CONFERIR, "selo-atencao") in pares


def test_a_situacao_da_conferencia_da_tela_bate_com_a_legenda():
    tela = ler_do_front("js/cadastrar_conferencia_real.js")
    # A pessoa sem pendência: "Tudo certo"; com pendência, "1 pendência" ou "N pendências"
    assert 'let situacao = "' + legenda_dos_status.PESSOA_SEM_PENDENCIA + '";' in tela
    assert 'situacao = "1 pendência";' in tela


def test_nenhuma_explicacao_fica_escrita_no_javascript():
    # Todo o JavaScript das telas, junto, em minúsculas (uma cópia com outra maiúscula também conta)
    javascript = ""
    for arquivo in sorted((PASTA_DO_FRONT / "js").glob("*.js")):
        javascript = javascript + arquivo.read_text(encoding="utf-8").lower()
    for situacao in todas_as_legendas():
        # O começo de cada explicação (as primeiras palavras bastam para achar uma cópia)
        comeco_da_explicacao = situacao["explicacao"][:40].lower()
        assert comeco_da_explicacao not in javascript, comeco_da_explicacao


# ---------------- As rotas ----------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com o especialista e o RH de duas empresas."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    # A lista de empresas em memória é de outro banco (de outro teste): esquece
    cadastro_de_empresas.esquecer_lista_em_memoria()
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    conexao_do_teste.close()
    yield
    cadastro_de_empresas.esquecer_lista_em_memoria()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_as_rotas_pedem_login(api):
    navegador_sem_login = TestClient(aplicacao)
    assert navegador_sem_login.get("/api/banco/legenda_dos_status").status_code == 401
    assert navegador_sem_login.get("/api/empresa/legenda_dos_status").status_code == 401


def test_cada_rota_e_so_do_seu_perfil(api):
    # A empresa não abre a legenda do banco, e o banco não abre a da empresa
    assert entrar("rh.aurora").get("/api/banco/legenda_dos_status").status_code == 403
    assert entrar("especialista").get("/api/empresa/legenda_dos_status").status_code == 403


def test_o_banco_recebe_as_grades_dele(api):
    resposta = entrar("especialista").get("/api/banco/legenda_dos_status")
    assert resposta.status_code == 200
    assert resposta.json() == legenda_dos_status.legendas_do_banco()


def test_a_empresa_recebe_so_as_grades_dela_e_o_mesmo_texto_que_outra_empresa(api):
    da_aurora = entrar("rh.aurora").get("/api/empresa/legenda_dos_status")
    da_horizonte = entrar("rh.horizonte").get("/api/empresa/legenda_dos_status")
    assert da_aurora.status_code == 200 and da_horizonte.status_code == 200
    # Só as grades da empresa, nada das do banco
    assert set(da_aurora.json()) == GRADES_DA_EMPRESA
    # Texto fixo: nenhuma empresa recebe algo da outra (nem dela mesma)
    assert da_aurora.json() == da_horizonte.json()
