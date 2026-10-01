"""Teste de segurança, frente A: login, sessão, autorização por rota, isolamento entre empresas e permissões.

Para que serve: confere, do jeito que um atacante tentaria, se os controles de acesso descritos em
docs/seguranca.md (seções 2 e 3) funcionam de verdade. Cada teste descreve o comportamento CORRETO:
    - quando o controle funciona, o teste passa;
    - quando o teste achou uma falha, ele leva a marca xfail(strict=True) com o código do achado (ex.: "A-02").
      "xfail" quer dizer "falha esperada": a bateria continua verde enquanto a falha existir e fica VERMELHA no
      dia em que alguém corrigir o problema (aí é só tirar a marca). É um lembrete automático.
O relatório com a tabela de achados (A-01, A-02...) fica em docs/testes_de_seguranca.md.

Regras de ambiente (obrigatórias):
    - só o TestClient (um "navegador de mentira" que fala direto com a aplicação, sem ligar servidor);
    - banco SQLite descartável deste arquivo e MODE=mock (tests/conftest.py): nada de IA real, nada de custo;
    - nunca o servidor da porta 8000, o PostgreSQL, a pasta storage/ de verdade nem o .env.

Quem é quem nos testes:
    - "seg.aurora" (EMP001, a Aurora) é a VÍTIMA: tem funcionários cadastrados, um envio aberto e um rascunho de
      Endomarketing;
    - "seg.horizonte" (EMP002, a Horizonte) é a empresa ATACANTE: tenta ler e mexer nas coisas da Aurora;
    - "seg.banco" e "seg.banco2" são especialistas do banco; "seg.provisoria" está com a senha provisória.

Conceitos para leigo:
    - IDOR (referência direta insegura): trocar um número na URL ("/envios/123" → "/envios/124") para ver o que é de
      outra pessoa. A defesa é o servidor conferir o dono de cada coisa, e não confiar no número que chegou;
    - mass assignment: mandar no pedido um campo a mais (ex.: "perfil": "BANCO") esperando que o servidor grave;
    - CSRF: um site de fora faz o navegador da vítima mandar um pedido ao nosso site, com o cookie dela;
    - fixação de sessão: o atacante planta um ingresso no navegador da vítima antes do login e o reaproveita depois.
"""
import csv
import inspect
import re
import tempfile
import time
import types
import typing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import params
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from agents import endomarketing
from api.principal import MENSAGEM_LOGIN_RECUSADO, aplicacao
from models.contratos import Perfil
from services import acesso, auth, dados_mock, progresso, sessoes
from services import empresas as cadastro_de_empresas
from services.auth import Usuario
from services.permissoes import PERFIS_POR_OPERACAO, AcessoNegado, autorizar
from tests.test_correcao import ENVIOS, _gabarito, busca_falsa
from tests.test_endomarketing import busca_por_palavras
from tests.test_planejamento import SINTETICO, homologar

# Senha dos usuários de teste (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"
# A empresa vítima (Aurora) e a empresa atacante (Horizonte)
EMPRESA_VITIMA = "EMP001"
EMPRESA_ATACANTE = "EMP002"
# Um endereço de outro site, para os testes de CSRF e de CORS
ORIGEM_MALICIOSA = "https://site-malicioso.example"
# As rotas da API que não são de um perfil só: entrar, sair, quem sou eu, o cabeçalho, a troca de senha e a data da
# versão do rodapé (ADR-133)
ROTAS_COMUNS = {"/api/entrar", "/api/sair", "/api/eu", "/api/cabecalho", "/api/minha-senha", "/api/versao"}
# O que a pessoa com senha provisória ainda pode usar (ADR-109): quem sou eu, o cabeçalho, trocar a senha e sair; e a
# data da versão do rodapé, que nem exige login (ADR-133)
ROTAS_LIBERADAS_COM_SENHA_PROVISORIA = {"/api/entrar", "/api/sair", "/api/eu", "/api/cabecalho", "/api/minha-senha",
                                        "/api/versao"}
# As rotas que abrem sem login: entrar, sair e a data da versão do rodapé (só o texto "Atualizado em ...", ADR-133)
ROTAS_SEM_LOGIN = ("/api/entrar", "/api/sair", "/api/versao")


# ---------------- Preparação: um banco só deste arquivo, com a vítima e a atacante ----------------

def gerar_arquivos_da_demo_se_faltarem() -> None:
    """Gera os arquivos sintéticos da demo (envios e gabarito) só se ainda não existem.

    Por quê: os arquivos de envio não vão para o Git. Gerar só quando faltam evita reescrever os arquivos enquanto
    outras baterias de teste, rodando ao mesmo tempo, estão lendo.
    """
    # O arquivo da carga inicial da Aurora e o gabarito dos funcionários
    arquivo_da_carga = ENVIOS / _gabarito("aurora_carga_inicial")["arquivo"]
    arquivo_do_gabarito = SINTETICO / "funcionarios_truth.csv"
    # Os dois já existem: nada a fazer
    if arquivo_da_carga.exists() and arquivo_do_gabarito.exists():
        return
    # Falta algum: gera os dados sintéticos (mesma semente, mesmo conteúdo)
    from scripts.gerar_dados import main
    main()


def ler_gabarito_dos_funcionarios() -> dict:
    """O gabarito de cada funcionário (funcionario_id → campos corretos), usado para homologar a carga da vítima."""
    # Um dicionário: o identificador do funcionário aponta para a linha com os dados corretos dele
    gabarito = {}
    # Lê o CSV do gabarito linha por linha
    with open(SINTETICO / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            gabarito[linha["funcionario_id"]] = linha
    return gabarito


def cadastrar_usuarios_do_teste(conexao) -> None:
    """Cadastra a vítima, a atacante, dois especialistas do banco e a pessoa com senha provisória."""
    # A empresa vítima (Aurora) e a empresa atacante (Horizonte)
    auth.cadastrar_usuario(conexao, "seg.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    auth.cadastrar_usuario(conexao, "seg.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_ATACANTE)
    # Dois especialistas do banco (um tenta mexer no outro)
    auth.cadastrar_usuario(conexao, "seg.banco", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao, "seg.banco2", SENHA_DE_TESTE, Perfil.BANCO)
    # Uma pessoa da Aurora que ainda não trocou a senha provisória do convite
    auth.cadastrar_usuario(conexao, "seg.provisoria", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA,
                           senha_provisoria=True)


def entrar(login: str, senha: str = SENHA_DE_TESTE, endereco_base: str = "http://testserver") -> TestClient:
    """Um navegador de mentira já logado com o usuário informado.

    Recebe: login; senha; endereco_base — "https://testserver" simula a conexão segura.
    Devolve: o TestClient com o cookie da sessão guardado (ele devolve o cookie a cada pedido, como um navegador).
    """
    # Navegador novo, sem cookies; sem seguir desvios, para os testes enxergarem o 303 do "Sair"
    navegador = TestClient(aplicacao, base_url=endereco_base, follow_redirects=False)
    # Entra com usuário e senha
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": senha})
    # O login precisa ter dado certo para o teste seguir
    assert resposta.status_code == 200, resposta.text
    return navegador


def navegador_com_ingresso(ingresso: str) -> TestClient:
    """Um navegador de mentira que manda o ingresso informado no cookie (como quem copiou ou inventou um)."""
    # Navegador novo, sem login
    navegador = TestClient(aplicacao, follow_redirects=False)
    # Planta o ingresso no cookie da sessão
    navegador.cookies.set(sessoes.NOME_COOKIE, ingresso)
    return navegador


@pytest.fixture(scope="module", autouse=True)
def ambiente():
    """Monta, uma vez para este arquivo, o banco descartável com a vítima, a atacante e os recursos da vítima.

    Devolve: {processamento_da_vitima, funcionarios_da_vitima (ids), cpfs_da_vitima, material_da_vitima}.
    Como: a API passa a abrir sempre o banco deste arquivo (troca de auth.conectar, como em tests/test_cadastro.py),
    e a busca do RAG vira a busca falsa (sem índice e sem modelo de embeddings).
    """
    # "Remendos" temporários, desfeitos no fim (o monkeypatch do pytest, na versão que serve a um arquivo inteiro)
    remendos = pytest.MonkeyPatch()
    # Um arquivo de banco numa pasta temporária, só deste arquivo de teste
    caminho_do_banco = Path(tempfile.mkdtemp()) / "seg_acesso.db"
    # Guarda a abertura original do banco, para chamá-la com o caminho deste arquivo
    conectar_original = auth.conectar

    def conectar_no_banco_do_teste(caminho_pedido=None):
        """Abre sempre o banco deste arquivo, qualquer que seja o caminho pedido."""
        return conectar_original(caminho_do_banco)

    # Toda a API (login, sessões e rotas) passa a usar o banco deste arquivo
    remendos.setattr(auth, "conectar", conectar_no_banco_do_teste)
    # O Interpretador usa a busca falsa (nada de índice do RAG)
    remendos.setattr("rag.busca.search_rules", busca_falsa)
    # Os arquivos da demo precisam existir
    gerar_arquivos_da_demo_se_faltarem()
    # Abre o banco do teste e cadastra as pessoas
    conexao = conectar_original(caminho_do_banco)
    cadastrar_usuarios_do_teste(conexao)
    # A vítima com funcionários cadastrados: a carga inicial da Aurora, homologada
    homologar(conexao, "aurora_carga_inicial", ler_gabarito_dos_funcionarios())
    # A vítima com um material de Endomarketing (MOCK, sobre o catálogo dela) que o banco gerou e publicou com a
    # arte: desde o ADR-115 quem gera é o banco, e a empresa só vê o que foi publicado
    material_gerado = endomarketing.gerar_material(conexao, EMPRESA_VITIMA, "comunicado", "seg.banco",
                                                   busca=busca_por_palavras(conexao))
    endomarketing.publicar(conexao, EMPRESA_VITIMA, material_gerado.material_id, "seg.banco",
                           b"\x89PNG\r\n\x1a\n" + b"arte da vitima")
    conexao.close()
    # A vítima envia a inclusão pela tela: o envio fica aberto, esperando o aceite do mapeamento
    vitima = entrar("seg.aurora")
    gabarito_da_inclusao = _gabarito("aurora_inclusao")
    conteudo_da_inclusao = (ENVIOS / gabarito_da_inclusao["arquivo"]).read_bytes()
    resposta_do_envio = vitima.post("/api/empresa/cadastro/enviar",
                                    files={"arquivo": (gabarito_da_inclusao["arquivo"], conteudo_da_inclusao)})
    assert resposta_do_envio.status_code == 200, resposta_do_envio.text
    # Os funcionários cadastrados da vítima: o id (ficha e download) e o CPF
    identificadores_da_vitima = []
    cpfs_da_vitima = []
    for pessoa in vitima.get("/api/empresa/funcionarios").json():
        # Só os cadastrados têm id
        if pessoa.get("id"):
            identificadores_da_vitima.append(pessoa["id"])
        # O CPF de todos (cadastrados e do envio aberto)
        if pessoa.get("cpf"):
            cpfs_da_vitima.append(pessoa["cpf"])
    # O material de Endomarketing publicado para a vítima
    materiais_da_vitima = vitima.get("/api/empresa/endomarketing").json()
    # Entrega o que os testes precisam
    yield {
        "processamento_da_vitima": resposta_do_envio.json()["processamento_id"],
        "funcionarios_da_vitima": identificadores_da_vitima,
        "cpfs_da_vitima": cpfs_da_vitima,
        "material_da_vitima": materiais_da_vitima[0]["material_id"],
    }
    # Desfaz os remendos: os outros arquivos de teste voltam ao normal
    remendos.undo()


# ---------------- Ajudantes da varredura de rotas ----------------

def rotas_da_api() -> list[APIRoute]:
    """Todas as rotas da API (as que começam com /api/), lidas da própria aplicação.

    Por que ler da aplicação, e não de uma lista escrita à mão: uma rota nova entra na varredura sozinha.
    """
    # As rotas encontradas
    rotas = []
    for rota in aplicacao.routes:
        # Só as rotas de função (a pasta do front, montada no fim, não é uma delas)
        if not isinstance(rota, APIRoute):
            continue
        # Só a API (o /robots.txt fica de fora)
        if not rota.path.startswith("/api/"):
            continue
        rotas.append(rota)
    return rotas


def endereco_de_exemplo(caminho: str) -> str:
    """Troca cada pedaço variável do endereço por "exemplo". Ex.: "/api/empresa/cadastro/{processamento_id}" →
    "/api/empresa/cadastro/exemplo"."""
    # {qualquer_coisa} vira "exemplo"
    return re.sub(r"\{[^}]+\}", "exemplo", caminho)


def valor_de_exemplo(tipo_do_campo):
    """Um valor que cabe no tipo do campo, para montar um pedido válido. Ex.: str → "x"; int → 1."""
    # O "tipo de fora" de tipos compostos (list[str] → list; str | None → UnionType)
    tipo_de_fora = typing.get_origin(tipo_do_campo)
    # Lista: vazia
    if tipo_de_fora is list:
        return []
    # Dicionário: vazio
    if tipo_de_fora is dict:
        return {}
    # "Um ou outro" (ex.: int | None): None, se o campo aceita vazio; senão, o exemplo do primeiro tipo
    if tipo_de_fora is typing.Union or tipo_de_fora is types.UnionType:
        tipos_aceitos = typing.get_args(tipo_do_campo)
        if type(None) in tipos_aceitos:
            return None
        return valor_de_exemplo(tipos_aceitos[0])
    # Verdadeiro ou falso
    if tipo_do_campo is bool:
        return False
    # Número inteiro
    if tipo_do_campo is int:
        return 1
    # Número com vírgula
    if tipo_do_campo is float:
        return 1.0
    # Qualquer outro: texto de uma letra só (cabe em qualquer limite de tamanho, como a UF com 2 letras)
    return "x"


def corpo_de_exemplo(modelo) -> dict:
    """Um corpo JSON válido para o modelo do pedido, só com os campos obrigatórios. Ex.: {"texto": "exemplo"}."""
    # O corpo, campo por campo
    corpo = {}
    for nome_do_campo, campo in modelo.model_fields.items():
        # Campo com valor padrão pode ficar de fora
        if not campo.is_required():
            continue
        corpo[nome_do_campo] = valor_de_exemplo(campo.annotation)
    return corpo


def pedido_de_exemplo(rota: APIRoute) -> dict:
    """Os argumentos de um pedido VÁLIDO para a rota (json, ou arquivo e campos de formulário).

    Por quê: o FastAPI confere o formato do corpo ANTES de a rota conferir o login. Com um corpo válido, a
    resposta mostra o que a rota decide sobre quem pede (401 ou 403), e não um erro de formato (422).
    Devolve: um dicionário para TestClient.request (ex.: {"json": {...}} ou {"files": {...}, "data": {...}}).
    """
    # Os argumentos do pedido, o arquivo e os campos de formulário
    argumentos = {}
    arquivos = {}
    campos_de_formulario = {}
    for parametro in rota.dependant.body_params:
        # Arquivo enviado (UploadFile): um CSV pequeno
        if isinstance(parametro.field_info, params.File):
            arquivos[parametro.alias] = ("exemplo.csv", b"nome;cpf\nAna;123\n")
            continue
        # Campo de formulário: texto
        if isinstance(parametro.field_info, params.Form):
            campos_de_formulario[parametro.alias] = "exemplo"
            continue
        # Corpo JSON opcional (ex.: o "Conferi a lista" do homologar): fica de fora
        if not parametro.field_info.is_required():
            continue
        # Corpo JSON obrigatório: monta um exemplo a partir do modelo do pedido
        modelo = parametro.field_info.annotation
        if inspect.isclass(modelo) and issubclass(modelo, BaseModel):
            argumentos["json"] = corpo_de_exemplo(modelo)
    # Só manda arquivo e formulário quando a rota pede
    if arquivos:
        argumentos["files"] = arquivos
    if campos_de_formulario:
        argumentos["data"] = campos_de_formulario
    return argumentos


def varrer_rotas(navegador: TestClient, rotas: list[APIRoute], codigo_esperado: int) -> list[str]:
    """Pede cada rota com um corpo válido e devolve as que NÃO responderam o código esperado.

    Recebe: navegador (logado ou não); rotas; codigo_esperado (ex.: 401 ou 403).
    Devolve: lista de textos "MÉTODO /caminho → código" das rotas que fugiram da regra (vazia = tudo certo).
    """
    # As rotas que fugiram da regra
    fora_da_regra = []
    for rota in rotas:
        for metodo in sorted(rota.methods):
            # Faz o pedido com o endereço e o corpo de exemplo
            resposta = navegador.request(metodo, endereco_de_exemplo(rota.path), **pedido_de_exemplo(rota))
            # Anota se o código não foi o esperado
            if resposta.status_code != codigo_esperado:
                fora_da_regra.append(f"{metodo} {rota.path} → {resposta.status_code}")
    return fora_da_regra


def rotas_com_prefixo(prefixo: str) -> list[APIRoute]:
    """As rotas da API cujo endereço começa com o prefixo. Ex.: "/api/banco/" → as rotas do Portal do Banco."""
    # As rotas que começam com o prefixo
    escolhidas = []
    for rota in rotas_da_api():
        if rota.path.startswith(prefixo):
            escolhidas.append(rota)
    return escolhidas


# ---------------- 1. Login ----------------

def test_senha_errada_inexistente_e_desativado_recebem_a_mesma_resposta():
    """A-01: senha errada, usuário que não existe e usuário desativado recebem a mesma resposta (código e texto)."""
    # Um usuário desativado, só deste teste
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.mensagem.desativado", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    auth.definir_ativo(conexao, "seg.mensagem.desativado", False)
    conexao.close()
    # As três tentativas, cada uma num navegador novo
    senha_errada = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.aurora", "senha": "errada-123"})
    inexistente = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.nao.existe", "senha": "x-123456"})
    desativado = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.mensagem.desativado",
                                                                 "senha": SENHA_DE_TESTE})
    # O mesmo código e a mesma mensagem para as três
    for resposta in (senha_errada, inexistente, desativado):
        assert resposta.status_code == 401
        assert resposta.json() == {"detail": MENSAGEM_LOGIN_RECUSADO}


def medir_o_menor_tempo_de_login(logins: list[str], senha: str) -> float:
    """O menor tempo (em segundos) entre várias tentativas de login. O menor tira o "ruído" da máquina."""
    # O tempo de cada tentativa
    tempos = []
    for login in logins:
        # Marca o relógio, tenta entrar e marca de novo
        inicio = time.perf_counter()
        TestClient(aplicacao).post("/api/entrar", json={"usuario": login, "senha": senha})
        tempos.append(time.perf_counter() - inicio)
    return min(tempos)


def test_tempo_de_resposta_nao_revela_se_o_usuario_existe():
    """A-02: o login que não existe (ou está desativado) leva o mesmo tempo que uma senha errada de quem existe.

    Por quê: a mensagem é a mesma (A-01), mas services/auth.autenticar só roda o bcrypt (lento de propósito, ~0,2 s)
    quando o login existe e está ativo. Medindo o tempo, quem tenta descobre quais logins existem ("enumeração").
    """
    # Um usuário que existe, só deste teste (3 senhas erradas: abaixo do limite de 5)
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.tempo", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    # Senha errada de quem existe (o bcrypt roda)
    tempo_de_quem_existe = medir_o_menor_tempo_de_login(["seg.tempo", "seg.tempo", "seg.tempo"], "senha-errada-1")
    # Login que não existe (um diferente a cada vez)
    tempo_de_quem_nao_existe = medir_o_menor_tempo_de_login(["seg.fantasma.1", "seg.fantasma.2", "seg.fantasma.3"],
                                                            "senha-errada-1")
    # Correto: os dois tempos parecidos (ao menos metade). Hoje, o login inexistente responde muito mais rápido
    assert tempo_de_quem_nao_existe >= 0.5 * tempo_de_quem_existe, (
        f"inexistente {tempo_de_quem_nao_existe:.3f}s × existente {tempo_de_quem_existe:.3f}s")


def test_quinta_senha_errada_bloqueia_o_login_e_nem_a_certa_entra():
    """A-03: 5 senhas erradas seguidas bloqueiam o login (429), e durante o bloqueio nem a senha certa entra."""
    # Um usuário só deste teste
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.bloqueio", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    # As quatro primeiras senhas erradas: a mensagem de sempre
    for tentativa in range(4):
        resposta = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.bloqueio", "senha": "errada-123"})
        assert resposta.status_code == 401
    # A quinta: bloqueio, com o aviso e o "tente de novo em" (Retry-After)
    quinta = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.bloqueio", "senha": "errada-123"})
    assert quinta.status_code == 429
    assert quinta.headers["retry-after"] == str(15 * 60)
    # A senha certa também é barrada durante o bloqueio
    certa = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.bloqueio", "senha": SENHA_DE_TESTE})
    assert certa.status_code == 429


def test_bloqueio_nao_e_contornado_com_espacos_ou_maiusculas():
    """A-04: com o login bloqueado, escrever o login com espaços ou em maiúsculas não dá uma nova chance."""
    # Um usuário só deste teste, bloqueado com 5 senhas erradas
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.variacao", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    for tentativa in range(5):
        TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.variacao", "senha": "errada-123"})
    # Com espaços nas pontas: o login é limpo antes da conferência, e o bloqueio vale
    com_espacos = TestClient(aplicacao).post("/api/entrar", json={"usuario": "  seg.variacao  ",
                                                                  "senha": SENHA_DE_TESTE})
    assert com_espacos.status_code == 429
    # Em maiúsculas: não é o mesmo login (a conferência diferencia maiúsculas), então a senha certa não entra
    em_maiusculas = TestClient(aplicacao).post("/api/entrar", json={"usuario": "SEG.VARIACAO",
                                                                    "senha": SENHA_DE_TESTE})
    assert em_maiusculas.status_code in (401, 429)


@pytest.mark.xfail(strict=True, reason="A-05: o limite é só por login; tentar 1 senha em muitos logins não é barrado "
                                       "(docs/seguranca.md, seção 8, item 2)")
def test_muitas_tentativas_do_mesmo_endereco_em_logins_diferentes_sao_barradas():
    """A-05: 10 logins diferentes, cada um com 1 senha errada, vindos do mesmo endereço: alguma deve ser barrada.

    Por quê: o ataque de "espalhar senhas" (password spraying) tenta uma senha comum em muitos logins; o limite por
    login (5 erros) nunca é atingido. O correto é também limitar por endereço de rede (ou exigir SSO em produção).
    """
    # O mesmo navegador (mesmo endereço) tenta 10 logins diferentes
    navegador = TestClient(aplicacao)
    codigos = []
    for numero in range(10):
        resposta = navegador.post("/api/entrar", json={"usuario": f"seg.spray.{numero}", "senha": "Senha@2026"})
        codigos.append(resposta.status_code)
    # Correto: alguma tentativa barrada com 429. Hoje, as 10 recebem 401
    assert 429 in codigos, codigos


def test_troca_de_senha_limita_as_tentativas_da_senha_atual():
    """A-06: /api/minha-senha também bloqueia depois de 5 senhas atuais erradas (como o login).

    Por quê: quem roubou um cookie de sessão (válido por até 7 dias) pode adivinhar a senha atual da vítima pela
    troca de senha, sem o limite do login, e, ao acertar, troca a senha e toma a conta de vez.
    Como o login (A-03): o 5º erro já responde 429, e durante o bloqueio toda tentativa recebe 429, certa ou errada.
    Se a errada recebesse 400 e a certa 429, a própria resposta contaria quando o chute acertou.
    """
    # Um usuário só deste teste, logado
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.forca.troca", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    navegador = entrar("seg.forca.troca")
    # As 4 primeiras senhas atuais erradas: recusadas com a mensagem de sempre
    for numero in range(4):
        errada = navegador.post("/api/minha-senha", json={"senha_atual": f"chute-{numero}-123",
                                                          "nova_senha": "nova-senha-456", "confirmacao": "nova-senha-456"})
        assert errada.status_code == 400
    # A 5ª errada começa o bloqueio, e a 6ª já chega bloqueada
    for numero in range(4, 6):
        bloqueada = navegador.post("/api/minha-senha", json={"senha_atual": f"chute-{numero}-123",
                                                             "nova_senha": "nova-senha-456",
                                                             "confirmacao": "nova-senha-456"})
        assert bloqueada.status_code == 429
    # A senha atual certa, logo em seguida
    certa = navegador.post("/api/minha-senha", json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "nova-senha-456",
                                                     "confirmacao": "nova-senha-456"})
    # Correto: ainda bloqueado (429), com a mesma resposta da errada
    assert certa.status_code == 429, certa.status_code


def test_senha_provisoria_so_libera_quem_sou_eu_cabecalho_troca_de_senha_e_sair():
    """A-07: com a senha provisória, TODA rota da API recusa (403), menos quem sou eu, cabeçalho, troca e sair."""
    # A pessoa com a senha provisória, logada
    navegador = entrar("seg.provisoria")
    # A rota "quem sou eu" avisa que a senha é provisória
    assert navegador.get("/api/eu").json()["senha_provisoria"] is True
    # As rotas que não são liberadas para a senha provisória
    rotas_travadas = []
    for rota in rotas_da_api():
        if rota.path not in ROTAS_LIBERADAS_COM_SENHA_PROVISORIA:
            rotas_travadas.append(rota)
    # Todas devem responder 403
    assert varrer_rotas(navegador, rotas_travadas, 403) == []


@pytest.mark.xfail(strict=True, reason="A-08: senha fraca aceita (só 8 caracteres, sem lista de senhas comuns) "
                                       "(docs/seguranca.md, seção 8, item 3)")
def test_senha_fraca_e_recusada_na_troca():
    """A-08: "12345678" e "aaaaaaaa" (8 caracteres, mas óbvias) são recusadas como nova senha."""
    # Um usuário só deste teste, logado
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.senha.fraca", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    navegador = entrar("seg.senha.fraca")
    # Tenta trocar para uma senha óbvia
    resposta = navegador.post("/api/minha-senha", json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "12345678",
                                                        "confirmacao": "12345678"})
    # Correto: recusada (400). Hoje, aceita (200)
    assert resposta.status_code == 400, resposta.status_code


def test_senha_guardada_so_como_bcrypt_com_custo_12_e_sal_diferente():
    """A-09: a senha vira hash bcrypt ($2b$, custo 12) e a mesma senha gera hashes diferentes (o "sal")."""
    # Dois usuários com a MESMA senha
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.hash.1", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    auth.cadastrar_usuario(conexao, "seg.hash.2", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    # O que está guardado para cada um
    hash_do_primeiro = conexao.execute("SELECT senha_hash FROM usuarios WHERE login = ?", ("seg.hash.1",)).fetchone()[0]
    hash_do_segundo = conexao.execute("SELECT senha_hash FROM usuarios WHERE login = ?", ("seg.hash.2",)).fetchone()[0]
    conexao.close()
    # bcrypt, versão 2b, custo 12 (2^12 rodadas): o começo do hash diz isso
    assert hash_do_primeiro.startswith("$2b$12$")
    # A senha em si não aparece
    assert SENHA_DE_TESTE not in hash_do_primeiro
    # Mesmo com a mesma senha, os hashes são diferentes: o sal sorteado
    assert hash_do_primeiro != hash_do_segundo


# ---------------- 2. Sessão e cookie ----------------

def test_cookie_de_sessao_sai_com_httponly_samesite_strict_e_secure_em_https():
    """A-10: o cookie sai com HttpOnly e SameSite=Strict sempre, e com Secure quando a conexão é https."""
    # Login em http (a máquina local)
    em_http = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.aurora", "senha": SENHA_DE_TESTE})
    cookie_em_http = em_http.headers["set-cookie"].lower()
    # HttpOnly (o JavaScript não lê) e SameSite=Strict (não vai em pedido de outro site)
    assert "httponly" in cookie_em_http
    assert "samesite=strict" in cookie_em_http
    # Login em https (a publicação)
    em_https = TestClient(aplicacao, base_url="https://testserver").post(
        "/api/entrar", json={"usuario": "seg.aurora", "senha": SENHA_DE_TESTE})
    cookie_em_https = em_https.headers["set-cookie"].lower()
    # Em https, também Secure (o cookie nunca viaja sem criptografia)
    assert "secure" in cookie_em_https
    assert "httponly" in cookie_em_https and "samesite=strict" in cookie_em_https


def test_sessao_vencida_nao_vale():
    """A-11: ingresso vencido (a sessão vale 8 horas; não há mais o "Lembrar de mim") é recusado com 401."""
    # Agora, em horário universal
    agora = datetime.now(timezone.utc)
    conexao = auth.conectar()
    # Uma sessão criada há 9 horas (venceu há 1 hora)
    ingresso_vencido = sessoes.criar_sessao(conexao, "seg.aurora", agora=agora - timedelta(hours=9))
    conexao.close()
    # Recusada
    assert navegador_com_ingresso(ingresso_vencido).get("/api/eu").status_code == 401


def test_sair_invalida_o_ingresso_no_servidor():
    """A-12: depois do "Sair", o mesmo ingresso (copiado por alguém) não vale mais em lugar nenhum."""
    # A vítima entra e alguém copia o ingresso dela
    navegador = entrar("seg.aurora")
    ingresso_copiado = navegador.cookies.get(sessoes.NOME_COOKIE)
    # O ingresso copiado funciona antes do "Sair"
    assert navegador_com_ingresso(ingresso_copiado).get("/api/eu").status_code == 200
    # A vítima sai
    assert navegador.get("/api/sair").status_code == 303
    # O ingresso copiado deixou de valer no servidor (não só no navegador)
    assert navegador_com_ingresso(ingresso_copiado).get("/api/eu").status_code == 401


def test_login_sempre_gera_ingresso_novo_contra_fixacao_de_sessao():
    """A-13: o ingresso plantado antes do login não é aproveitado; cada login sorteia um ingresso novo."""
    # O atacante planta um ingresso no navegador da vítima
    ingresso_plantado = "ingresso-plantado-pelo-atacante"
    navegador = navegador_com_ingresso(ingresso_plantado)
    # A vítima entra nesse navegador
    resposta = navegador.post("/api/entrar", json={"usuario": "seg.aurora", "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200
    # O servidor mandou um ingresso novo, diferente do plantado
    ingresso_novo = resposta.cookies.get(sessoes.NOME_COOKIE)
    assert ingresso_novo and ingresso_novo != ingresso_plantado
    # O ingresso plantado continua sem valor (o atacante não entra com ele)
    assert navegador_com_ingresso(ingresso_plantado).get("/api/eu").status_code == 401
    # Dois logins seguidos: dois ingressos diferentes
    outro_login = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.aurora", "senha": SENHA_DE_TESTE})
    assert outro_login.cookies.get(sessoes.NOME_COOKIE) != ingresso_novo


def test_cookie_adulterado_ou_inventado_e_recusado():
    """A-14: ingresso com uma letra trocada, inventado, com cara de SQL ou gigante: 401, nunca erro 500."""
    # Um ingresso verdadeiro, para adulterar
    ingresso_verdadeiro = entrar("seg.aurora").cookies.get(sessoes.NOME_COOKIE)
    # A última letra trocada
    ultima_letra_trocada = "A"
    if ingresso_verdadeiro.endswith("A"):
        ultima_letra_trocada = "B"
    adulterado = ingresso_verdadeiro[:-1] + ultima_letra_trocada
    # As falsificações
    falsificacoes = [adulterado, "ingresso-inventado", "' OR '1'='1", "x" * 4000]
    for falsificacao in falsificacoes:
        # Cada uma é recusada como "sem login"
        assert navegador_com_ingresso(falsificacao).get("/api/eu").status_code == 401


def test_usuario_desativado_perde_a_sessao_na_hora_e_reativar_nao_a_devolve():
    """A-15: o banco desativa a pessoa → a sessão aberta dela cai na hora; reativar não ressuscita a sessão velha."""
    # Uma pessoa da Aurora, só deste teste, logada
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.desativar", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    pessoa = entrar("seg.desativar")
    # O banco desativa
    banco = entrar("seg.banco")
    desativar = banco.post("/api/banco/empresas/usuarios/seg.desativar/situacao", json={"ativo": False})
    assert desativar.status_code == 200
    # A sessão aberta caiu
    assert pessoa.get("/api/eu").status_code == 401
    # O banco reativa: a sessão velha continua cancelada (precisa entrar de novo)
    reativar = banco.post("/api/banco/empresas/usuarios/seg.desativar/situacao", json={"ativo": True})
    assert reativar.status_code == 200
    assert pessoa.get("/api/eu").status_code == 401


def test_senha_redefinida_pelo_banco_derruba_as_sessoes_e_a_senha_velha():
    """A-16: o banco gera uma senha provisória → as sessões abertas caem e a senha antiga para de funcionar."""
    # Uma pessoa da Aurora, só deste teste, logada
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.redefinir", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    pessoa = entrar("seg.redefinir")
    # O banco gera a nova senha provisória
    resposta = entrar("seg.banco").post("/api/banco/empresas/usuarios/seg.redefinir/nova-senha")
    assert resposta.status_code == 200
    # A sessão aberta caiu
    assert pessoa.get("/api/eu").status_code == 401
    # A senha antiga não entra mais
    antiga = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.redefinir", "senha": SENHA_DE_TESTE})
    assert antiga.status_code == 401


def test_troca_da_propria_senha_derruba_as_outras_sessoes():
    """A-17: quem troca a própria senha (ex.: por desconfiar de roubo) derruba as outras sessões abertas.

    Por quê: services/auth.trocar_propria_senha só grava a senha nova; não chama encerrar_sessoes_do_usuario (o banco
    faz isso ao redefinir, A-16). O ingresso roubado continua valendo por até 7 dias depois da troca.
    """
    # Um usuário só deste teste, com duas sessões: a da pessoa e a de quem roubou o ingresso
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.duas.sessoes", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_VITIMA)
    conexao.close()
    pessoa = entrar("seg.duas.sessoes")
    ladrao = entrar("seg.duas.sessoes")
    # A pessoa troca a senha
    troca = pessoa.post("/api/minha-senha", json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "senha-nova-789",
                                                  "confirmacao": "senha-nova-789"})
    assert troca.status_code == 200
    # Correto: a sessão do ladrão caiu (401). Hoje, continua valendo (200)
    assert ladrao.get("/api/eu").status_code == 401


# ---------------- 3. Autorização por rota ----------------

def test_toda_rota_da_api_sem_login_responde_401():
    """A-18: sem login, TODA rota da API (lida da própria aplicação) responde 401, com um pedido de formato válido."""
    # Entrar, sair e a data da versão não exigem login (e entrar com "exemplo" contaria uma tentativa errada)
    rotas_que_exigem_login = []
    for rota in rotas_da_api():
        if rota.path not in ROTAS_SEM_LOGIN:
            rotas_que_exigem_login.append(rota)
    # A varredura precisa ter o que varrer (a aplicação tem dezenas de rotas)
    assert len(rotas_que_exigem_login) > 60
    # Um navegador sem login: todas devem responder 401
    assert varrer_rotas(TestClient(aplicacao), rotas_que_exigem_login, 401) == []


def test_pedido_anonimo_sem_corpo_nao_recebe_o_formato_dos_campos():
    """A-19: sem login, um pedido com o corpo vazio recebe 401, e não 422 com a lista dos campos que a rota espera.

    Por quê: o FastAPI confere o formato do corpo antes de a rota conferir o login. O 422 descreve os campos
    ("senha_atual", "nova_senha"...) para quem nem entrou, desfazendo em parte o "sem o mapa da API" (ADR-100).
    """
    # As rotas que recebem corpo (JSON, arquivo ou formulário)
    rotas_com_corpo = []
    for rota in rotas_da_api():
        if rota.dependant.body_params and rota.path != "/api/entrar":
            rotas_com_corpo.append(rota)
    # Pedido com o corpo vazio ({}), sem login
    anonimo = TestClient(aplicacao)
    respostas_com_formato = []
    for rota in rotas_com_corpo:
        for metodo in sorted(rota.methods):
            resposta = anonimo.request(metodo, endereco_de_exemplo(rota.path), json={})
            # 422: o servidor descreveu o formato do pedido
            if resposta.status_code == 422:
                respostas_com_formato.append(f"{metodo} {rota.path}")
    # Correto: nenhuma. Hoje, todas as rotas com corpo obrigatório descrevem os campos
    assert respostas_com_formato == []


def test_empresa_recebe_403_em_toda_rota_do_banco():
    """A-20: o perfil EMPRESA recebe 403 em TODA rota /api/banco/ (gestão de usuários, empresas, envios, contas...)."""
    # A empresa atacante, logada
    empresa = entrar("seg.horizonte")
    # As rotas do Portal do Banco
    rotas_do_banco = rotas_com_prefixo("/api/banco/")
    assert len(rotas_do_banco) > 20
    # Todas recusadas
    assert varrer_rotas(empresa, rotas_do_banco, 403) == []


def test_banco_recebe_403_em_toda_rota_da_empresa():
    """A-21: o perfil BANCO recebe 403 em TODA rota /api/empresa/ (o banco não age em nome da empresa)."""
    # O especialista do banco, logado
    banco = entrar("seg.banco")
    # As rotas do Portal Empresa
    rotas_da_empresa = rotas_com_prefixo("/api/empresa/")
    assert len(rotas_da_empresa) > 30
    # Todas recusadas
    assert varrer_rotas(banco, rotas_da_empresa, 403) == []


def test_so_as_rotas_comuns_ficam_fora_dos_prefixos_de_perfil():
    """A-22: toda rota da API é /api/empresa/ ou /api/banco/, menos as 5 comuns (entrar, sair, eu, cabeçalho, senha).

    Por quê: as duas varreduras acima (A-20 e A-21) só cobrem os dois prefixos. Uma rota nova fora deles escaparia.
    """
    # As rotas fora dos dois prefixos
    rotas_sem_perfil = set()
    for rota in rotas_da_api():
        if not rota.path.startswith("/api/empresa/") and not rota.path.startswith("/api/banco/"):
            rotas_sem_perfil.add(rota.path)
    # Só as comuns (e /api/banco/... com "/api/banco" exato não existe)
    assert rotas_sem_perfil == ROTAS_COMUNS


# ---------------- 4. Isolamento entre empresas (IDOR) ----------------

def pedidos_sobre_um_envio(processamento_id: str) -> list[tuple]:
    """Todos os pedidos da empresa que levam o envio NA URL: (método, endereço, corpo JSON ou None)."""
    # O começo do endereço do envio
    base = "/api/empresa/cadastro/" + processamento_id
    return [
        ("GET", base, None),
        ("GET", base + "/lista", None),
        ("GET", base + "/o_que_se_perde", None),
        ("GET", base + "/ficha?linha=2", None),
        ("GET", base + "/pessoas_para_informar?campo=cpf", None),
        ("GET", "/api/empresa/envios/" + processamento_id + "/linha_do_tempo", None),
        ("POST", base + "/aceitar", {"escolhas": {}}),
        ("POST", base + "/lista/corrigir", {"linha": 1, "campo": "nome", "valor": "Invasor"}),
        ("POST", base + "/lista/confirmar", {"regra_id": "RENDA_FORA_DA_FAIXA", "linha": 1}),
        ("POST", base + "/assistente", {"regra_id": "CPF_INVALIDO", "linha": 1, "mensagem": "me mostre os dados"}),
        ("POST", base + "/assistente/desfazer", {"tipo": "correcao", "id": "qualquer"}),
        ("POST", base + "/informar_por_pessoa", {"campo": "cpf", "valores": [{"linha": 2, "valor": "52998224725"}]}),
        ("POST", base + "/assistente/usar_coluna", {"campo": "cpf", "coluna": "Nome", "confirmar": True}),
        ("POST", base + "/reler", {"colunas": [{"coluna": "Nome", "dica": "nome completo"}]}),
        ("POST", base + "/previa_da_divisao", {"coluna": "Endereco", "destino": "endereco"}),
        ("POST", base + "/dividir", {"coluna": "Endereco", "destino": "endereco"}),
        ("POST", base + "/refazer_divisao", {"coluna": "Endereco", "comentario": "errado"}),
        ("POST", base + "/conferir_coluna", {"coluna": "Nome", "campo": "nome"}),
        ("POST", base + "/homologar", {"conferi_a_lista": True}),
        ("POST", base + "/descartar", None),
    ]


def test_outra_empresa_nao_le_nem_mexe_no_envio_trocando_o_id_na_url(ambiente):
    """A-23: a Horizonte, com o id do envio da Aurora na URL, recebe 404 em tudo (ler, aceitar, corrigir, homologar,
    descartar...), a resposta é igual à de um envio inexistente e o envio da Aurora não muda."""
    # O envio da vítima, e como ele está antes do ataque
    processamento_da_vitima = ambiente["processamento_da_vitima"]
    vitima = entrar("seg.aurora")
    etapa_antes = vitima.get("/api/empresa/cadastro/" + processamento_da_vitima).json()["etapa"]
    # A atacante tenta cada pedido com o id da vítima
    atacante = entrar("seg.horizonte")
    respostas_indevidas = []
    for metodo, endereco, corpo in pedidos_sobre_um_envio(processamento_da_vitima):
        resposta = atacante.request(metodo, endereco, json=corpo)
        # Correto: 404 "Envio não encontrado." (sem dizer que o envio existe em outra empresa)
        if resposta.status_code != 404:
            respostas_indevidas.append(f"{metodo} {endereco} → {resposta.status_code} {resposta.text[:120]}")
    assert respostas_indevidas == []
    # A resposta ao envio da vítima é igual à de um envio que não existe (não revela a existência)
    ao_da_vitima = atacante.get("/api/empresa/cadastro/" + processamento_da_vitima)
    ao_inexistente = atacante.get("/api/empresa/cadastro/envio-que-nao-existe")
    assert (ao_da_vitima.status_code, ao_da_vitima.json()) == (ao_inexistente.status_code, ao_inexistente.json())
    # O envio da vítima continua na mesma etapa (nada foi aceito, homologado nem descartado)
    assert vitima.get("/api/empresa/cadastro/" + processamento_da_vitima).json()["etapa"] == etapa_antes
    # As pendências resolvidas e as conversas guardadas (ADR-120): nada do envio da vítima na lista da atacante
    assert processamento_da_vitima not in atacante.get("/api/empresa/pendencias/resolvidas").text


def test_decidir_formato_confere_o_dono_antes_de_ler_o_envio(ambiente):
    """A-24: a Horizonte, decidindo o formato de uma coluna do envio da Aurora, recebe 404 como nas outras rotas.

    Por quê: services/cadastro.decidir_formato lê formatos_pendentes(processamento_id) SEM a empresa e responde 400
    ("A coluna ... não tem dúvida de formato" ou "Escolha uma opção válida"); o dono só é conferido depois, no fluxo.
    Nada é gravado (o fluxo barra), mas a resposta muda conforme o envio alheio tem ou não aquela dúvida: dá para
    descobrir que o envio existe e quais colunas dele têm data ambígua ou matrícula com zeros.
    """
    # A atacante decide o formato de uma coluna do envio da vítima
    atacante = entrar("seg.horizonte")
    endereco = "/api/empresa/cadastro/" + ambiente["processamento_da_vitima"] + "/formato"
    resposta = atacante.post(endereco, json={"coluna": "Admissao", "decisao": "DMY"})
    # Correto: 404 "Envio não encontrado." Hoje: 400 com a mensagem sobre a coluna do envio alheio
    assert resposta.status_code == 404, resposta.text


def test_outra_empresa_nao_mexe_no_envio_mandando_o_id_no_corpo(ambiente):
    """A-25: corrigir, confirmar ou preencher para todos com o id do envio da Aurora NO CORPO: 404 para a Horizonte."""
    # O envio da vítima
    processamento_da_vitima = ambiente["processamento_da_vitima"]
    atacante = entrar("seg.horizonte")
    # Os três pedidos que levam o envio no corpo
    pedidos = [
        ("/api/empresa/pendencias/corrigir", {"processamento_id": processamento_da_vitima, "linha": 1, "campo": "nome",
                                              "novo_valor": "Invasor", "motivo": "teste"}),
        ("/api/empresa/pendencias/confirmar", {"processamento_id": processamento_da_vitima,
                                               "regra_id": "RENDA_FORA_DA_FAIXA", "linha": 1,
                                               "justificativa": "teste"}),
        ("/api/empresa/pendencias/preencher_para_todos", {"processamento_id": processamento_da_vitima,
                                                          "campo": "cnpj_empregador", "novo_valor": "00000000000000",
                                                          "motivo": "teste"}),
    ]
    for endereco, corpo in pedidos:
        # Cada um recusado como "envio não encontrado"
        assert atacante.post(endereco, json=corpo).status_code == 404, endereco


def test_outra_empresa_nao_abre_ficha_nao_baixa_e_nao_lista_funcionarios_alheios(ambiente):
    """A-26: a Horizonte não abre a ficha, não baixa o CSV e não vê na lista nenhum funcionário da Aurora (nem o CPF)."""
    # Os funcionários da vítima (ids e CPFs)
    identificadores_da_vitima = ambiente["funcionarios_da_vitima"]
    cpfs_da_vitima = ambiente["cpfs_da_vitima"]
    # A vítima tem funcionários cadastrados (senão o teste não provaria nada)
    assert identificadores_da_vitima and cpfs_da_vitima
    atacante = entrar("seg.horizonte")
    # A ficha de uma pessoa da vítima: 404, igual a um id que não existe
    ficha_alheia = atacante.get("/api/empresa/funcionarios/" + identificadores_da_vitima[0])
    ficha_inexistente = atacante.get("/api/empresa/funcionarios/nao-existe.1")
    assert ficha_alheia.status_code == 404
    assert ficha_alheia.json() == ficha_inexistente.json()
    # O download com os ids da vítima: recusado, sem nenhum CPF na resposta
    download = atacante.post("/api/empresa/funcionarios/baixar", json={"identificadores": identificadores_da_vitima})
    assert download.status_code == 400
    for cpf in cpfs_da_vitima:
        assert cpf not in download.text
    # A lista da atacante: nenhum id nem CPF da vítima
    lista_da_atacante = atacante.get("/api/empresa/funcionarios").text
    for identificador in identificadores_da_vitima:
        assert identificador not in lista_da_atacante
    for cpf in cpfs_da_vitima:
        assert cpf not in lista_da_atacante


def test_outra_empresa_nao_decide_material_nem_liga_kit_a_envio_alheio(ambiente):
    """A-27 (refeito pelo ADR-115): a Horizonte não baixa a arte da Aurora (404), não usa as rotas do banco para
    publicar, retirar ou gerar um kit ligado ao envio da Aurora (403), e as rotas antigas de gerar e aprovar
    da empresa não existem mais."""
    # O material publicado para a vítima
    material_da_vitima = ambiente["material_da_vitima"]
    atacante = entrar("seg.horizonte")
    # Baixar a arte da vítima trocando o id na URL: 404
    assert atacante.get(f"/api/empresa/endomarketing/{material_da_vitima}/arte").status_code == 404
    # As rotas do banco (retirar o material da vítima, gerar um kit ligado ao envio dela): 403
    rota_da_vitima = f"/api/banco/empresas/{EMPRESA_VITIMA}/endomarketing"
    assert atacante.post(f"{rota_da_vitima}/{material_da_vitima}/retirar").status_code == 403
    kit = atacante.post(f"{rota_da_vitima}/gerar", json={"tipo": "kit_boas_vindas", "beneficios": ["Conta salário"],
                                                         "processamento_id": ambiente["processamento_da_vitima"]})
    assert kit.status_code == 403
    # As rotas antigas da empresa (aprovar e gerar) não existem mais
    decisao = atacante.post(f"/api/empresa/endomarketing/{material_da_vitima}/decidir", json={"aprovar": False})
    assert decisao.status_code in (404, 405)
    assert atacante.post("/api/empresa/endomarketing/gerar", json={"tipo": "faq"}).status_code in (404, 405)
    # O material da vítima continua publicado para ela
    materiais_da_vitima = []
    for material in entrar("seg.aurora").get("/api/empresa/endomarketing").json():
        materiais_da_vitima.append(material["material_id"])
    assert material_da_vitima in materiais_da_vitima
    # Os materiais da atacante não trazem o da vítima
    assert material_da_vitima not in atacante.get("/api/empresa/endomarketing").text


def test_outra_empresa_nao_le_o_progresso_do_envio_alheio():
    """A-28: o código de progresso de um envio só responde para quem enviou (a Horizonte recebe 404)."""
    # A vítima começa um envio com um código de progresso (simulado direto no serviço)
    codigo_da_vitima = "abcdef0123456789abcdef0123456789"
    bilhete = progresso.comecar(codigo_da_vitima, "seg.aurora")
    progresso.terminar(bilhete)
    # A vítima lê a frase do progresso
    assert entrar("seg.aurora").get("/api/empresa/cadastro/progresso/" + codigo_da_vitima).status_code == 200
    # A atacante, com o mesmo código, não lê
    assert entrar("seg.horizonte").get("/api/empresa/cadastro/progresso/" + codigo_da_vitima).status_code == 404


def test_mensagem_da_empresa_vai_sempre_para_a_propria_conversa():
    """A-29: a Horizonte manda "empresa_id": "EMP001" no corpo da mensagem; ela cai na conversa da Horizonte."""
    # A atacante tenta escrever na conversa da vítima (campo a mais no corpo)
    atacante = entrar("seg.horizonte")
    texto_do_ataque = "mensagem plantada pela Horizonte na conversa da Aurora"
    resposta = atacante.post("/api/empresa/conversa", json={"texto": texto_do_ataque, "empresa_id": EMPRESA_VITIMA})
    assert resposta.status_code == 200
    # A conversa da vítima não tem a mensagem
    assert texto_do_ataque not in entrar("seg.aurora").get("/api/empresa/conversa").text
    # A conversa da atacante tem
    assert texto_do_ataque in atacante.get("/api/empresa/conversa").text


def test_catalogo_kit_e_numeros_sao_sempre_da_empresa_da_sessao():
    """A-30: benefícios, materiais publicados, início e resumo da Horizonte nunca trazem o nome da Aurora, mesmo
    pedindo "?empresa_id=EMP001" no endereço. (O kit visual saiu da empresa com o ADR-115: a arte é feita no banco.)"""
    # O nome da vítima, que não pode aparecer
    nome_da_vitima = dados_mock.nome_da_empresa(EMPRESA_VITIMA)
    atacante = entrar("seg.horizonte")
    # As consultas da empresa, com a tentativa de trocar a empresa pelo endereço
    for endereco in ("/api/empresa/beneficios", "/api/empresa/endomarketing", "/api/empresa/inicio",
                     "/api/empresa/resumo"):
        resposta = atacante.get(endereco, params={"empresa_id": EMPRESA_VITIMA})
        assert resposta.status_code == 200, endereco
        assert nome_da_vitima not in resposta.text, endereco


# ---------------- 5. Permissões e gestão de usuários ----------------

def test_login_ignora_perfil_e_empresa_mandados_no_corpo():
    """A-31: mandar "perfil": "BANCO" e outra "empresa_id" no login não muda nada: o perfil vem do cadastro."""
    # Login com campos a mais
    resposta = TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.horizonte", "senha": SENHA_DE_TESTE,
                                                               "perfil": "BANCO", "empresa_id": EMPRESA_VITIMA})
    assert resposta.status_code == 200
    # O perfil e a empresa são os do cadastro
    assert resposta.json()["perfil"] == "EMPRESA"
    assert resposta.json()["empresa_id"] == EMPRESA_ATACANTE


def test_troca_de_senha_ignora_perfil_empresa_e_login_mandados_no_corpo():
    """A-32: a troca de senha com "perfil", "empresa_id" e "login" a mais só troca a senha de quem está logado."""
    # Um usuário só deste teste, logado
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "seg.mass.assignment", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA_ATACANTE)
    conexao.close()
    navegador = entrar("seg.mass.assignment")
    # A troca com campos a mais (tentando virar BANCO, mudar de empresa e trocar a senha de outra pessoa)
    resposta = navegador.post("/api/minha-senha", json={"senha_atual": SENHA_DE_TESTE, "nova_senha": "nova-senha-321",
                                                        "confirmacao": "nova-senha-321", "perfil": "BANCO",
                                                        "empresa_id": EMPRESA_VITIMA, "login": "seg.banco"})
    assert resposta.status_code == 200
    # Continua EMPRESA, da mesma empresa
    quem_sou = navegador.get("/api/eu").json()
    assert quem_sou["perfil"] == "EMPRESA"
    assert quem_sou["empresa_id"] == EMPRESA_ATACANTE
    # A senha do banco não mudou
    assert TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.banco",
                                                           "senha": SENHA_DE_TESTE}).status_code == 200


def test_empresa_nao_convida_nao_redefine_senha_nem_desativa_ninguem():
    """A-33: a empresa não cria usuário, não gera senha provisória, não desativa colega nem cadastra empresa (403)."""
    atacante = entrar("seg.horizonte")
    # Convidar uma pessoa (criar usuário)
    convite = atacante.post(f"/api/banco/empresas/{EMPRESA_ATACANTE}/convite", json={"email": "intruso@exemplo.com"})
    assert convite.status_code == 403
    # Gerar a senha provisória da vítima (tomaria a conta dela)
    nova_senha = atacante.post("/api/banco/empresas/usuarios/seg.aurora/nova-senha")
    assert nova_senha.status_code == 403
    # Desativar a vítima
    desativar = atacante.post("/api/banco/empresas/usuarios/seg.aurora/situacao", json={"ativo": False})
    assert desativar.status_code == 403
    # Nada mudou: nenhum usuário novo e a vítima ainda entra com a senha dela
    conexao = auth.conectar()
    logins = []
    for usuario in auth.listar_usuarios(conexao):
        logins.append(usuario.login)
    conexao.close()
    assert "intruso@exemplo.com" not in logins
    assert TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.aurora",
                                                           "senha": SENHA_DE_TESTE}).status_code == 200


def test_banco_nao_desativa_nem_redefine_usuario_do_banco_pela_tela_de_empresas():
    """A-34: pela tela de empresas, o banco só mexe em pessoa de EMPRESA: outro especialista ou ele mesmo → 400."""
    banco = entrar("seg.banco")
    # Desativar outro especialista, redefinir a senha dele e desativar a si mesmo: recusados
    assert banco.post("/api/banco/empresas/usuarios/seg.banco2/situacao", json={"ativo": False}).status_code == 400
    assert banco.post("/api/banco/empresas/usuarios/seg.banco2/nova-senha").status_code == 400
    assert banco.post("/api/banco/empresas/usuarios/seg.banco/situacao", json={"ativo": False}).status_code == 400
    # O outro especialista continua entrando com a senha dele
    assert TestClient(aplicacao).post("/api/entrar", json={"usuario": "seg.banco2",
                                                           "senha": SENHA_DE_TESTE}).status_code == 200


def test_convite_cria_so_empresa_com_senha_provisoria_e_recusa_login_repetido_ou_de_fora():
    """A-35: o convite cria pessoa de EMPRESA, da empresa certa, com senha provisória; login repetido e e-mail de
    outro domínio são recusados."""
    # O domínio de e-mail da vítima
    conexao = auth.conectar()
    dominio = cadastro_de_empresas.obter(conexao, EMPRESA_VITIMA)["dominio_email"]
    conexao.close()
    banco = entrar("seg.banco")
    # Convite válido
    email_novo = "seg.convidado@" + dominio
    convite = banco.post(f"/api/banco/empresas/{EMPRESA_VITIMA}/convite", json={"email": email_novo})
    assert convite.status_code == 200
    # A pessoa convidada é EMPRESA, da Aurora, e precisa trocar a senha
    convidado = entrar(email_novo, convite.json()["senha_provisoria"])
    quem_sou = convidado.get("/api/eu").json()
    assert quem_sou["perfil"] == "EMPRESA"
    assert quem_sou["empresa_id"] == EMPRESA_VITIMA
    assert quem_sou["senha_provisoria"] is True
    # Convidar de novo o mesmo e-mail (sobrescreveria a senha): recusado
    repetido = banco.post(f"/api/banco/empresas/{EMPRESA_VITIMA}/convite", json={"email": email_novo})
    assert repetido.status_code == 400
    # E-mail de outro domínio: recusado
    de_fora = banco.post(f"/api/banco/empresas/{EMPRESA_VITIMA}/convite", json={"email": "pessoa@gmail.com"})
    assert de_fora.status_code == 400


def test_permissoes_e_porta_de_acesso_chamadas_direto():
    """A-36: chamando services/permissoes.py e services/acesso.py direto (sem a API): sem login, operação
    desconhecida, perfil errado e empresa vazia são negados; ninguém desativa a si mesmo."""
    # As pessoas de mentira (só objetos na memória, como a sessão devolveria)
    empresa = Usuario(login="seg.aurora", perfil=Perfil.EMPRESA, empresa_id=EMPRESA_VITIMA)
    empresa_sem_empresa = Usuario(login="seg.sem.empresa", perfil=Perfil.EMPRESA, empresa_id=None)
    banco = Usuario(login="seg.banco", perfil=Perfil.BANCO, empresa_id=None)
    # Sem login: negado
    with pytest.raises(AcessoNegado):
        autorizar(None, "gerar_material")
    # Operação que não existe na tabela: negada até para o banco
    with pytest.raises(AcessoNegado):
        autorizar(banco, "operacao_que_nao_existe")
    # Empresa sem empresa no cadastro: negada
    with pytest.raises(AcessoNegado):
        autorizar(empresa_sem_empresa, "gerar_material")
    # Cada operação, para cada perfil que NÃO está autorizado: negada
    for operacao, perfis_autorizados in PERFIS_POR_OPERACAO.items():
        for usuario in (empresa, banco):
            if usuario.perfil in perfis_autorizados:
                continue
            with pytest.raises(AcessoNegado):
                autorizar(usuario, operacao)
    # A porta de acesso: a empresa tentando criar um usuário do banco
    conexao = auth.conectar()
    with pytest.raises(AcessoNegado):
        acesso.cadastrar_usuario(conexao, empresa, "seg.intruso.banco", "senha-longa-123", Perfil.BANCO, None)
    # O usuário não foi criado
    logins = []
    for usuario in auth.listar_usuarios(conexao):
        logins.append(usuario.login)
    assert "seg.intruso.banco" not in logins
    # Ninguém desativa o próprio usuário
    with pytest.raises(ValueError):
        acesso.definir_ativo(conexao, banco, "seg.banco", False)
    conexao.close()


# ---------------- 6. CSRF (pedido vindo de outro site) ----------------

def test_rota_json_recusa_corpo_de_formulario_simples_de_outro_site():
    """A-37: a mesma mensagem mandada como "text/plain" (o que um formulário de outro site consegue mandar sem pedir
    licença ao navegador) é recusada (422) e não é gravada."""
    # A vítima logada
    vitima = entrar("seg.aurora")
    texto_do_ataque = "mensagem plantada por formulario de outro site"
    # O corpo com cara de JSON, mas com o tipo que um formulário comum consegue mandar
    resposta = vitima.post("/api/empresa/conversa", content='{"texto": "' + texto_do_ataque + '"}',
                           headers={"content-type": "text/plain", "origin": ORIGEM_MALICIOSA})
    assert resposta.status_code == 422
    # Nada gravado
    assert texto_do_ataque not in vitima.get("/api/empresa/conversa").text


def test_api_nao_libera_leitura_das_respostas_para_outro_site():
    """A-38: a API não responde com Access-Control-Allow-Origin para outro site (CORS fechado): uma página de fora
    não consegue LER os dados da vítima, mesmo que o navegador mande o pedido."""
    # A vítima logada
    vitima = entrar("seg.aurora")
    # Pedido comum vindo de outro site
    leitura = vitima.get("/api/empresa/funcionarios", headers={"origin": ORIGEM_MALICIOSA})
    assert "access-control-allow-origin" not in leitura.headers
    # A "pergunta prévia" (preflight) que o navegador faz antes de um pedido com JSON
    pergunta_previa = vitima.options("/api/empresa/conversa", headers={"origin": ORIGEM_MALICIOSA,
                                                                       "access-control-request-method": "POST"})
    assert "access-control-allow-origin" not in pergunta_previa.headers


@pytest.mark.xfail(strict=True, reason="A-39: o servidor não confere a origem (Origin/Referer) dos pedidos que mudam "
                                       "dados; a defesa contra CSRF é só o SameSite=Strict do cookie")
def test_pedido_que_muda_dados_vindo_de_outra_origem_e_recusado():
    """A-39: um pedido que muda dados com "Origin" de outro site é recusado pelo servidor (403), com ou sem cookie.

    Por quê: hoje, a única barreira é o navegador não mandar o cookie SameSite=Strict (A-10). Rotas que aceitam
    formulário (envio de arquivo, catálogo, contas), rotas POST sem corpo (descartar, confirmar baixa, nova senha) e o
    "Sair" por GET ficam sem uma segunda camada no servidor (navegador antigo, subdomínio do mesmo site etc.).
    """
    # A vítima logada; o pedido chega com a origem de outro site (como se o cookie tivesse ido junto)
    vitima = entrar("seg.aurora")
    resposta = vitima.post("/api/empresa/conversa", json={"texto": "pedido vindo de outro site"},
                           headers={"origin": ORIGEM_MALICIOSA, "referer": ORIGEM_MALICIOSA + "/pagina"})
    # Correto: recusado (403). Hoje, aceito (200)
    assert resposta.status_code == 403, resposta.status_code
