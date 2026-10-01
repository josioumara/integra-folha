"""Teste de segurança, frente B: exposição de dados e de segredos, tratamento de erros e falhas comuns da web.

Para que serve: confere, com ataques de verdade (feitos pelo "navegador de mentira" do FastAPI, o TestClient), se os
controles que o capítulo docs/seguranca.md diz existir funcionam. Cada teste tem o nome do que ele prova.

Como ler o resultado:
    - teste que PASSA: o controle funciona;
    - teste marcado com xfail ("falha esperada"): a vulnerabilidade foi demonstrada. O teste descreve o
      comportamento CORRETO e hoje falha de propósito; com strict=True, no dia em que alguém corrigir, ele passa a
      "passar sem querer" (XPASS) e o pytest avisa, para tirar a marca. O código B-NN liga o teste à tabela de
      achados da frente B.

O que este arquivo nunca faz: ler ou mostrar o conteúdo do .env, tocar no servidor da porta 8000, no PostgreSQL, na
pasta storage/ real ou gastar IA. Tudo roda em MOCK, num banco SQLite temporário só deste arquivo, com a busca do RAG
trocada por uma falsa (sem abrir o índice real).

Conceitos para leigo:
    - XSS: fazer a página rodar um código escondido num dado (ex.: um nome de funcionário "<img onerror=...>");
    - SQL injection: esconder um pedaço de consulta ao banco de dados num campo (ex.: "' OR '1'='1");
    - path traversal: usar "../" no endereço para sair da pasta permitida e pegar outro arquivo;
    - stack trace: o "relatório de pane" do Python, com nomes de arquivos e linhas do código. Nunca pode ir para a tela.
"""
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api.principal import PASTA_DO_FRONT, aplicacao
from models.contratos import Perfil
from services import acompanhamento, auth, planejamento, portal_do_banco, sessoes

# Pasta raiz do projeto (integra-folha), dois níveis acima de tests/seguranca/
RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent.parent
# Senha dos usuários deste arquivo (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"
# Os usuários deste arquivo: prefixo "segb." para nunca colidir com os usuários das outras frentes
LOGIN_DA_HORIZONTE = "segb.horizonte"
LOGIN_DA_AURORA = "segb.aurora"
LOGIN_DO_BANCO = "segb.banco"
# Um nome de funcionário que é, na verdade, um código para a página rodar (ataque de XSS)
NOME_COM_CODIGO = "<img src=x onerror=alert(1)>"
# Três CPFs sintéticos válidos (dígitos verificadores certos), inventados para este teste
CPFS_DO_ARQUIVO = ("52998224725", "11144477735", "39053344705")
# Os nomes das três pessoas do arquivo (o primeiro é o ataque)
NOMES_DO_ARQUIVO = (NOME_COM_CODIGO, "Beatriz Quintanilha Zorzetto", "Orlando Vasconcelos Pimpao")
# Salários fáceis de reconhecer numa varredura (no arquivo, do jeito brasileiro)
SALARIOS_DO_ARQUIVO = ("7654,30", "7654,31", "7654,32")
# O cabeçalho do arquivo, no mesmo formato da demo da Horizonte (data/synthetic/envios/horizonte_carga_inicial.csv)
CABECALHO_DO_ARQUIVO = ("ID Funcionário;Empregado;CPF;DN;Sexo;Situação Conjugal;Código Postal;Logradouro;Nº;"
                        "Bairro Res.;Cidade Residência;UF Residência;Celular;Cadastro Empresa;Cód. Unidade;"
                        "Nome da Filial;Cargo;Data de Entrada;Vínculo;Salário Bruto;Competência;CEP Unidade;"
                        "End. Unidade;Nº Comercial;Bairro Empresa;Cidade Comercial;UF Trabalho")
# O resto de cada linha depois do salário (competência, endereço comercial), igual para as três pessoas
FIM_DA_LINHA = "01/09/2026;31360673;Avenida Central;4889;Distrito Empresarial;Campinas;SP"
# Os cabeçalhos de proteção que TODA resposta tem de trazer (docs/seguranca.md, 2.4 e 2.6)
CABECALHOS_OBRIGATORIOS = ("content-security-policy", "x-frame-options", "x-content-type-options",
                           "referrer-policy", "x-robots-tag")
# Pedaços de texto que denunciam um "relatório de pane" ou detalhe interno numa resposta de erro
SINAIS_DE_DETALHE_INTERNO = ("Traceback", "File \"", ".py", "sqlite", "psycopg", "SELECT ", "INSERT ", "uvicorn",
                             "starlette", "Python", "D:\\", "C:\\", "/app/")


# ---------------- Preparação: um banco só deste arquivo, com um envio de verdade (em MOCK) ----------------

def busca_falsa(texto, k=3, **outros_argumentos):
    """RAG de mentira: devolve um trecho fixo, sem abrir o índice real nem o modelo de embeddings.

    Recebe: texto e k (como a busca de verdade). Devolve: uma lista com um trecho de regra e a fonte.
    """
    # Um trecho fixo, com fonte, no formato que o Interpretador espera
    return [{"fonte": "Regras de validação › cpf", "campo": "cpf",
             "texto": "Regras de validação › cpf\nO CPF precisa ter 11 dígitos e dígito verificador válido."}]


def reindexar_sem_gravar(conexao):
    """No lugar do refazer do índice do catálogo: não faz nada, para nenhum teste gravar em storage/ real."""
    # Nada a fazer: o índice real nunca é tocado por este arquivo
    return None


def conteudo_do_arquivo_de_teste() -> bytes:
    """Monta o CSV sintético de três pessoas (a primeira com o nome que é um ataque de XSS).

    Devolve: os bytes do arquivo em UTF-8. Exemplo de linha: "00001;<img ...>;52998224725;...;7654,30;01/09/2026;...".
    """
    # Começa pelo cabeçalho
    linhas = [CABECALHO_DO_ARQUIVO]
    # Uma linha por pessoa, com o número da matrícula, o nome, o CPF e o salário dela
    for posicao in range(len(CPFS_DO_ARQUIVO)):
        # A matrícula com zeros à esquerda (00001, 00002, 00003)
        matricula = str(posicao + 1).zfill(5)
        # O meio da linha: nascimento, endereço residencial, celular, CNPJ, unidade, cargo, admissão e vínculo
        meio_da_linha = ("01/07/1975;F;Divorciado;80794454;Rua Sete de Setembro;673;Industrial;Campinas;SP;"
                         "(17) 98873-7081;88805929000139;HOR-02;CD Campinas;Motorista;22/08/2015;CLT")
        # Junta as partes da linha com ";" (o separador do arquivo)
        partes = [matricula, NOMES_DO_ARQUIVO[posicao], CPFS_DO_ARQUIVO[posicao], meio_da_linha,
                  SALARIOS_DO_ARQUIVO[posicao], FIM_DA_LINHA]
        linhas.append(";".join(partes))
    # O arquivo inteiro, com uma quebra de linha no fim
    return ("\n".join(linhas) + "\n").encode("utf-8")


def navegador_logado(login: str) -> TestClient:
    """Um navegador de mentira já logado. Não segue desvios e devolve o erro 500 como resposta (não como exceção).

    Recebe: login. Devolve: o TestClient com o cookie da sessão.
    """
    # follow_redirects=False: o teste enxerga o desvio (303); raise_server_exceptions=False: o 500 volta como resposta
    navegador = TestClient(aplicacao, follow_redirects=False, raise_server_exceptions=False)
    # Entra com a senha de teste
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    # O login precisa dar certo para o teste seguir
    assert resposta.status_code == 200
    return navegador


def navegador_sem_login() -> TestClient:
    """Um navegador de mentira sem sessão, que não segue desvios e devolve o erro 500 como resposta."""
    # Sem cookie nenhum
    return TestClient(aplicacao, follow_redirects=False, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    """Prepara, uma vez para o arquivo: banco próprio, usuários, e um envio da Horizonte já com pendência.

    Devolve: {"horizonte", "aurora", "banco"} (navegadores logados), "processamento_id" (o envio) e "conectar" (abre
    o banco deste arquivo). No fim, desfaz as trocas (o resto da bateria volta ao banco dos testes).
    """
    # Um arquivo de banco só deste arquivo de testes, numa pasta temporária
    caminho_do_banco = tmp_path_factory.mktemp("frente_b") / "seguranca_exposicao.db"
    # A abertura original do banco, guardada antes da troca
    conectar_original = auth.conectar

    def conectar_no_banco_deste_arquivo(caminho_pedido=None):
        """Abre sempre o banco deste arquivo, qualquer que seja o caminho pedido."""
        return conectar_original(caminho_do_banco)

    # Troca temporária: o MonkeyPatch guarda o original e devolve no fim
    trocas = pytest.MonkeyPatch()
    # A API passa a usar o banco deste arquivo
    trocas.setattr(auth, "conectar", conectar_no_banco_deste_arquivo)
    # O RAG vira a busca falsa (sem índice real)
    trocas.setattr("rag.busca.search_rules", busca_falsa)
    # O catálogo nunca refaz o índice real
    trocas.setattr(portal_do_banco, "_reindexar_catalogo", reindexar_sem_gravar)
    # Cadastra os três usuários: RH da Horizonte (EMP002), RH da Aurora (EMP001) e o especialista do banco
    conexao = conectar_no_banco_deste_arquivo()
    auth.cadastrar_usuario(conexao, LOGIN_DA_HORIZONTE, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao, LOGIN_DA_AURORA, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()
    # Os três navegadores logados
    horizonte = navegador_logado(LOGIN_DA_HORIZONTE)
    aurora = navegador_logado(LOGIN_DA_AURORA)
    banco = navegador_logado(LOGIN_DO_BANCO)
    # Uma senha errada de propósito: grava uma linha na tabela de tentativas (varrida no teste dos registros)
    navegador_sem_login().post("/api/entrar", json={"usuario": LOGIN_DA_HORIZONTE, "senha": "senha-errada-999"})
    # A Horizonte envia o arquivo, como a tela faz (formulário multipart)
    resposta_do_envio = horizonte.post("/api/empresa/cadastro/enviar",
                                       files={"arquivo": ("folha.csv", conteudo_do_arquivo_de_teste())})
    assert resposta_do_envio.status_code == 200
    # O identificador do envio
    processamento_id = resposta_do_envio.json()["processamento_id"]
    # Aceita o mapeamento proposto (em MOCK, todas as colunas foram reconhecidas): o envio vai para a correção
    resposta_do_aceite = horizonte.post(f"/api/empresa/cadastro/{processamento_id}/aceitar", json={"escolhas": {}})
    assert resposta_do_aceite.status_code == 200
    # Abre a lista de funcionários: grava uma linha no registro de acessos (varrido no teste dos registros)
    assert horizonte.get("/api/empresa/funcionarios").status_code == 200
    # Entrega o ambiente aos testes
    yield {"horizonte": horizonte, "aurora": aurora, "banco": banco, "processamento_id": processamento_id,
           "conectar": conectar_no_banco_deste_arquivo}
    # No fim do arquivo, desfaz todas as trocas
    trocas.undo()


def cabecalhos_que_faltam(resposta) -> list[str]:
    """Os cabeçalhos de proteção que não vieram numa resposta. Ex.: [] quando está tudo certo."""
    # Junta os que faltam
    faltando = []
    for nome in CABECALHOS_OBRIGATORIOS:
        if nome not in resposta.headers:
            faltando.append(nome)
    return faltando


def sinais_de_detalhe_interno(texto: str) -> list[str]:
    """Os pedaços que denunciam detalhe interno (pane, caminho, SQL, servidor) num texto. Ex.: ["Traceback"]."""
    # Junta os sinais encontrados
    encontrados = []
    for sinal in SINAIS_DE_DETALHE_INTERNO:
        if sinal in texto:
            encontrados.append(sinal)
    return encontrados


# ---------------- 1. Segredos: fora do Git e fora da imagem ----------------

def rodar_git(argumentos: list[str]) -> subprocess.CompletedProcess:
    """Roda um comando do Git na pasta do projeto e devolve o resultado (sem mostrar nada na tela).

    Recebe: argumentos — ex.: ["log", "--all", "--format=%h"]. Pula o teste se o Git não existir ou não for um
    repositório (ex.: numa cópia sem a pasta .git).
    """
    # Sem o programa git na máquina, não há o que conferir
    if shutil.which("git") is None:
        pytest.skip("Git não instalado nesta máquina.")
    # Roda o comando, guardando a saída em bytes (o histórico tem acentos)
    resultado = subprocess.run(["git", *argumentos], cwd=RAIZ_DO_PROJETO, capture_output=True)
    # Pasta que não é repositório: pula
    if b"not a git repository" in resultado.stderr:
        pytest.skip("A pasta do projeto não é um repositório Git.")
    return resultado


def test_b01_env_fica_fora_do_git_e_da_imagem():
    """B-01: o .env (com as chaves) está no .gitignore e no .dockerignore, e o Git confirma que o ignora."""
    # O nome exato ".env" aparece nos dois arquivos de "ignorar" (numa linha própria)
    for nome_do_arquivo in (".gitignore", ".dockerignore"):
        # As linhas do arquivo, sem espaços nas pontas
        linhas = []
        for linha in (RAIZ_DO_PROJETO / nome_do_arquivo).read_text(encoding="utf-8").splitlines():
            linhas.append(linha.strip())
        assert ".env" in linhas, nome_do_arquivo
    # E o próprio Git diz que ignora o .env (check-ignore devolve 0 quando o arquivo é ignorado)
    assert rodar_git(["check-ignore", "-q", ".env"]).returncode == 0


def test_b02_env_nunca_entrou_no_historico_do_git():
    """B-02: nenhum commit, em nenhum ramo, tem o arquivo .env (só o modelo .env.example)."""
    # Os commits que mexeram num arquivo chamado exatamente .env
    resultado = rodar_git(["log", "--all", "--format=%h", "--", ".env"])
    # Nenhum
    assert resultado.stdout.strip() == b""


# Os padrões de segredo procurados no histórico (o tipo; o valor nunca é mostrado)
PADROES_DE_SEGREDO = {
    "chave de acesso da AWS": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "segredo da AWS": re.compile(r"aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+]{30,}"),
    "chave da Anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "chave da OpenAI": re.compile(r"\bsk-(proj-)?[A-Za-z0-9_\-]{32,}"),
    "chave do Bedrock": re.compile(r"ABSK[A-Za-z0-9+/=]{30,}"),
    "token do Bedrock preenchido": re.compile(r"AWS_BEARER_TOKEN_BEDROCK\s*=\s*[^\s$'\"{]{10,}"),
    "chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "token do GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
}
# Endereço de banco de dados com senha (postgresql://usuario:SENHA@...): a senha é o grupo "senha"
PADRAO_DE_ENDERECO_COM_SENHA = re.compile(r"postgres(ql)?://[^:/\s@]+:(?P<senha>[^@\s]+)@")
# As "senhas" que são só marcadores: exemplo na documentação (postgresql://usuario:senha@localhost), variável do
# Compose ou do shell (${SENHA...}, $SENHA) e variável de f-string do Python ({senha_da_aplicacao}, preenchida na hora)
MARCADORES_DE_EXEMPLO = ("senha", "SENHA", "${", "$SENHA", "{", "<", "***", "sua_senha")


def endereco_tem_senha_de_verdade(linha: str) -> bool:
    """True se a linha tem um endereço postgresql:// com uma senha que não é um marcador de exemplo.

    Exemplos: "postgresql://usuario:senha@localhost" → False; "postgresql://app:${SENHA}@banco" → False.
    """
    # Cada endereço com senha da linha
    for achado in PADRAO_DE_ENDERECO_COM_SENHA.finditer(linha):
        # A senha escrita no endereço
        senha_escrita = achado.group("senha")
        # É um marcador de exemplo?
        eh_marcador = False
        for marcador in MARCADORES_DE_EXEMPLO:
            if senha_escrita.startswith(marcador):
                eh_marcador = True
        # Uma senha que não é marcador: segredo de verdade
        if not eh_marcador:
            return True
    return False


def test_b03_nenhum_segredo_no_historico_inteiro_do_git():
    """B-03: o histórico inteiro (todos os ramos, todas as linhas acrescentadas) não tem chave, token ou senha real.

    A mensagem de erro diz só o TIPO, o arquivo e o commit; o valor achado nunca é mostrado.
    """
    # O histórico inteiro com as mudanças de cada commit; "COMMIT <hash>" marca o começo de cada um
    resultado = rodar_git(["log", "-p", "--all", "--no-color", "--format=COMMIT %h"])
    # Em texto (um byte estranho vira "?", sem quebrar a leitura)
    historico = resultado.stdout.decode("utf-8", errors="replace")
    # O commit e o arquivo da linha que está sendo lida
    commit_atual = ""
    arquivo_atual = ""
    # Os achados: "tipo em arquivo (commit)"
    achados = []
    for linha in historico.splitlines():
        # Começo de um commit
        if linha.startswith("COMMIT "):
            commit_atual = linha.split()[1]
            continue
        # Nome do arquivo mudado
        if linha.startswith("+++ b/"):
            arquivo_atual = linha[len("+++ b/"):]
            continue
        # Só as linhas acrescentadas contam (começam com "+", mas não são o "+++" do nome do arquivo)
        if not linha.startswith("+") or linha.startswith("+++"):
            continue
        # Cada padrão de segredo
        for tipo, padrao in PADROES_DE_SEGREDO.items():
            if padrao.search(linha):
                achados.append(f"{tipo} em {arquivo_atual} ({commit_atual})")
        # Endereço de banco com senha de verdade
        if endereco_tem_senha_de_verdade(linha):
            achados.append(f"endereço de banco com senha em {arquivo_atual} ({commit_atual})")
    assert achados == []


@pytest.mark.xfail(strict=True, reason="B-04: .gitignore e .dockerignore cobrem só o nome exato .env; variantes "
                                       "(.env.local, .env.producao) e arquivos novos em storage/ entrariam no Git")
def test_b04_variantes_do_env_e_a_pasta_storage_ficam_fora_do_git():
    """B-04: uma cópia do .env com outro nome, ou um arquivo novo em storage/ (ex.: um dump do banco), é ignorada."""
    # Nomes que costumam guardar segredos ou dados reais
    caminhos_sensiveis = (".env.local", ".env.producao", "storage/copia_do_banco.sql")
    # Os que o Git NÃO ignoraria (check-ignore devolve 1 quando o arquivo não é ignorado)
    nao_ignorados = []
    for caminho in caminhos_sensiveis:
        if rodar_git(["check-ignore", "-q", caminho]).returncode != 0:
            nao_ignorados.append(caminho)
    assert nao_ignorados == []


def test_b05_imagem_e_compose_sem_segredo_escrito_sem_administrador_e_banco_fechado():
    """B-05: o Dockerfile não copia o .env nem roda como administrador; o Compose não tem senha escrita e o
    PostgreSQL só abre em 127.0.0.1."""
    # As instruções do Dockerfile, sem comentários
    instrucoes = []
    for linha in (RAIZ_DO_PROJETO / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if linha.strip() and not linha.strip().startswith("#"):
            instrucoes.append(linha.strip())
    # Nenhuma instrução copia um .env para dentro da imagem
    for instrucao in instrucoes:
        if instrucao.startswith(("COPY ", "ADD ")):
            assert ".env" not in instrucao, instrucao
    # A última linha USER existe e não é o administrador (root)
    linhas_de_usuario = []
    for instrucao in instrucoes:
        if instrucao.startswith("USER "):
            linhas_de_usuario.append(instrucao)
    assert linhas_de_usuario and linhas_de_usuario[-1] not in ("USER root", "USER 0")
    # O docker-compose.yml lido como dados
    receita = yaml.safe_load((RAIZ_DO_PROJETO / "docker-compose.yml").read_text(encoding="utf-8"))
    # Cada variável de ambiente com "SENHA" ou "PASSWORD" no nome vem do .env (${...}), nunca escrita
    for nome_do_servico, servico in receita["services"].items():
        for nome_da_variavel, valor in (servico.get("environment") or {}).items():
            if "SENHA" in nome_da_variavel or "PASSWORD" in nome_da_variavel:
                assert str(valor).startswith("${"), (nome_do_servico, nome_da_variavel)
    # A porta do PostgreSQL só abre para a própria máquina
    for porta in receita["services"]["banco"]["ports"]:
        assert str(porta).startswith("127.0.0.1:"), porta


# ---------------- 2. O que as respostas da API mostram ----------------

def test_b06_mapa_da_api_nao_fica_exposto_com_ou_sem_login(ambiente):
    """B-06: /docs, /redoc e /openapi.json não existem: sem login, desvio para o login; logado, nunca a descrição."""
    # Os três endereços que o FastAPI cria sozinho quando não são desligados
    enderecos_do_mapa = ("/docs", "/redoc", "/openapi.json")
    # Sem login e com cada perfil
    for navegador in (navegador_sem_login(), ambiente["horizonte"], ambiente["banco"]):
        for endereco in enderecos_do_mapa:
            resposta = navegador.get(endereco)
            # Nunca 200 (a página ou o JSON do mapa)
            assert resposta.status_code in (303, 404), endereco
            # E nada que pareça a descrição das rotas
            assert "\"paths\"" not in resposta.text and "swagger" not in resposta.text.lower()


def chaves_e_valores_sensiveis(dados, caminho: str, achados: list[str]) -> None:
    """Percorre uma resposta JSON e anota o que não pode sair da API: hash de senha, ingresso, chave, caminho do disco.

    Recebe: dados — a resposta já lida (dicionário, lista ou valor); caminho — onde estamos (ex.: "/usuarios[]");
    achados — a lista onde anotar. Devolve: nada (anota em achados).
    Permitido: "senha_provisoria" (só diz True/False para a tela pedir a troca) e "tokens_entrada" (contagem de
    tokens da IA na Telemetria, não é segredo).
    """
    # Dicionário: confere cada chave e desce em cada valor
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            # Nome de campo que denuncia segredo (senha_hash, ingresso, api_key, secret...)
            if re.search(r"hash|ingresso|password|api_key|secret|segredo|token_", chave, re.IGNORECASE):
                achados.append(f"chave {caminho}/{chave}")
            # Um campo de senha com texto dentro (o booleano senha_provisoria é permitido)
            if "senha" in chave.lower() and isinstance(valor, str):
                achados.append(f"senha em texto {caminho}/{chave}")
            chaves_e_valores_sensiveis(valor, caminho + "/" + chave, achados)
        return
    # Lista: desce em cada item
    if isinstance(dados, list):
        for item in dados:
            chaves_e_valores_sensiveis(item, caminho + "[]", achados)
        return
    # Texto: não pode ser um hash bcrypt ("$2b$...") nem um caminho de pasta do servidor
    if isinstance(dados, str):
        if re.match(r"^\$2[aby]\$", dados):
            achados.append(f"hash bcrypt em {caminho}")
        if re.search(r"[A-Za-z]:\\|/app/|/tmp/|storage[/\\]", dados):
            achados.append(f"caminho do disco em {caminho}")


def test_b07_nenhuma_resposta_traz_hash_de_senha_ingresso_ou_caminho_do_disco(ambiente):
    """B-07: todas as consultas (GET) dos dois portais, lidas por inteiro, sem hash, ingresso, chave ou caminho."""
    processamento_id = ambiente["processamento_id"]
    # As consultas do Portal Empresa (RH da Horizonte)
    rotas_da_empresa = ("/api/eu", "/api/cabecalho", "/api/empresa/resumo", "/api/empresa/inicio",
                        "/api/empresa/funcionarios", "/api/empresa/pendencias", "/api/empresa/pendencias/resolvidas",
                        "/api/empresa/envios/pagina",
                        "/api/empresa/conversa", "/api/empresa/endomarketing", "/api/empresa/beneficios",
                        "/api/empresa/prontos_para_o_banco", f"/api/empresa/cadastro/{processamento_id}",
                        f"/api/empresa/cadastro/{processamento_id}/lista")
    # As consultas do Portal Interno (especialista do banco)
    rotas_do_banco = ("/api/eu", "/api/cabecalho", "/api/banco/inicio", "/api/banco/empresas", "/api/banco/envios",
                      "/api/banco/endomarketing", "/api/banco/empresas/EMP001/endomarketing",
                      "/api/banco/telemetria/uso", "/api/banco/telemetria/ia", "/api/banco/conversas",
                      "/api/banco/empresas/EMP001/contas/historico", "/api/banco/empresas/EMP001/contas/layout",
                      "/api/banco/parametros/layout",
                      "/api/banco/empresas/EMP002/visao_geral", "/api/banco/planejamento")
    # Os achados de todas as rotas
    achados = []
    for navegador, rotas in ((ambiente["horizonte"], rotas_da_empresa), (ambiente["banco"], rotas_do_banco)):
        for rota in rotas:
            resposta = navegador.get(rota)
            # Toda consulta tem de responder (senão a varredura não vale)
            assert resposta.status_code == 200, rota
            chaves_e_valores_sensiveis(resposta.json(), rota, achados)
    assert achados == []


def textos_das_tabelas(conectar, tabelas: tuple[str, ...]) -> dict[str, str]:
    """Todo o conteúdo de cada tabela, como um texto só, para procurar dado pessoal.

    Recebe: conectar — abre o banco deste arquivo; tabelas — os nomes. Devolve: {tabela: texto}.
    """
    # Abre o banco deste arquivo
    conexao = conectar()
    # O texto de cada tabela
    textos = {}
    for tabela in tabelas:
        # O nome vem da lista fixa acima (nunca do usuário): pode entrar na consulta
        linhas = conexao.execute(f"SELECT * FROM {tabela}").fetchall()
        # Cada linha vira texto; todas juntas
        partes = []
        for linha in linhas:
            # Cada valor da linha como texto (números e datas também)
            valores_em_texto = []
            for valor in linha:
                valores_em_texto.append(str(valor))
            partes.append(" | ".join(valores_em_texto))
        textos[tabela] = "\n".join(partes)
    conexao.close()
    return textos


def test_b08_registros_de_auditoria_telemetria_e_acesso_sem_dado_pessoal(ambiente):
    """B-08: depois de um envio completo, os registros (eventos, execuções da IA, acessos, tentativas de login e
    sessões) não têm CPF, nome, salário, senha nem o ingresso da sessão."""
    # As tabelas de registro (as tabelas de DADOS do envio, como validacoes, guardam CPF por necessidade)
    tabelas_de_registro = ("eventos", "execucoes_agentes", "acessos_a_dados", "tentativas_de_login", "sessoes")
    textos = textos_das_tabelas(ambiente["conectar"], tabelas_de_registro)
    # O que nunca pode aparecer: cada CPF, os nomes, os salários (com vírgula ou ponto) e as senhas digitadas
    proibidos = list(CPFS_DO_ARQUIVO) + list(NOMES_DO_ARQUIVO) + [SENHA_DE_TESTE, "senha-errada-999"]
    for salario in SALARIOS_DO_ARQUIVO:
        proibidos.append(salario)
        proibidos.append(salario.replace(",", "."))
    # O ingresso de cada sessão (o valor do cookie): no banco, só o hash dele pode ficar
    for nome_do_navegador in ("horizonte", "aurora", "banco"):
        proibidos.append(ambiente[nome_do_navegador].cookies.get(sessoes.NOME_COOKIE))
    # Os achados: "o quê na tabela"
    achados = []
    for tabela, texto in textos.items():
        for proibido in proibidos:
            if proibido in texto:
                achados.append(f"{proibido!r} em {tabela}")
    assert achados == []
    # A varredura só vale se os registros existem: o envio gerou eventos e o login errado gerou uma tentativa
    assert textos["eventos"] and textos["tentativas_de_login"] and textos["acessos_a_dados"]


def test_b09_toda_resposta_com_cpf_proibe_copia_no_navegador(ambiente):
    """B-09: resposta que traz o CPF inteiro sai com "Cache-Control: no-store" (o navegador não guarda cópia)."""
    processamento_id = ambiente["processamento_id"]
    # O primeiro CPF, do jeito que a tela mostra (com pontos e traço)
    cpf = CPFS_DO_ARQUIVO[0]
    cpf_com_pontos = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    # As consultas da empresa que podem trazer CPF
    rotas = ("/api/empresa/funcionarios", f"/api/empresa/cadastro/{processamento_id}",
             f"/api/empresa/cadastro/{processamento_id}/lista")
    # As que trazem CPF sem proibir a cópia
    sem_protecao = []
    for rota in rotas:
        resposta = ambiente["horizonte"].get(rota)
        # Traz o CPF (cru ou com pontos)?
        traz_cpf = cpf in resposta.text or cpf_com_pontos in resposta.text
        # Sem o "no-store"?
        if traz_cpf and resposta.headers.get("cache-control") != "no-store":
            sem_protecao.append(rota)
    assert sem_protecao == []


# ---------------- 3. Tratamento de erros ----------------

def test_b10_recurso_inexistente_responde_404_curto_sem_detalhe_interno(ambiente):
    """B-10: identificadores que não existem recebem 404 com uma frase curta, sem pane, caminho, SQL ou versão."""
    # Rotas da empresa com um identificador inventado
    rotas_da_empresa = ("/api/empresa/cadastro/NAOEXISTE", "/api/empresa/funcionarios/NAOEXISTE",
                        "/api/empresa/envios/NAOEXISTE/linha_do_tempo", "/api/empresa/cadastro/NAOEXISTE/lista",
                        "/api/empresa/cadastro/progresso/NAOEXISTE", "/api/nao_existe")
    for rota in rotas_da_empresa:
        resposta = ambiente["horizonte"].get(rota)
        assert resposta.status_code == 404, rota
        assert sinais_de_detalhe_interno(resposta.text) == [], rota
    # Rotas do banco com um identificador inventado
    for rota in ("/api/banco/envios/NAOEXISTE/pessoas", "/api/banco/empresas/NAOEXISTE/visao_geral"):
        resposta = ambiente["banco"].get(rota)
        assert resposta.status_code == 404, rota
        assert sinais_de_detalhe_interno(resposta.text) == [], rota


def test_b11_envio_de_outra_empresa_recebe_a_mesma_resposta_que_um_inexistente(ambiente):
    """B-11: a Aurora pede o envio da Horizonte: a resposta é idêntica à de um envio que não existe (404, mesma frase).

    Assim, ninguém descobre se um identificador existe em outra empresa (403 × 404 revelaria).
    """
    processamento_id = ambiente["processamento_id"]
    # Os finais de endereço testados (leitura, lista, linha do tempo e o que se perde)
    rotas = ("/api/empresa/cadastro/{}", "/api/empresa/cadastro/{}/lista", "/api/empresa/envios/{}/linha_do_tempo",
             "/api/empresa/cadastro/{}/o_que_se_perde")
    for modelo_da_rota in rotas:
        # O envio que existe, mas é da Horizonte
        de_outra_empresa = ambiente["aurora"].get(modelo_da_rota.format(processamento_id))
        # Um envio que não existe
        inexistente = ambiente["aurora"].get(modelo_da_rota.format("000000000000"))
        assert de_outra_empresa.status_code == inexistente.status_code == 404, modelo_da_rota
        assert de_outra_empresa.json() == inexistente.json(), modelo_da_rota
    # O mesmo para uma ação (descartar): a Aurora não mexe, e a resposta não revela nada
    acao_de_outra_empresa = ambiente["aurora"].post(f"/api/empresa/cadastro/{processamento_id}/descartar")
    acao_inexistente = ambiente["aurora"].post("/api/empresa/cadastro/000000000000/descartar")
    assert acao_de_outra_empresa.status_code == acao_inexistente.status_code == 404
    assert acao_de_outra_empresa.json() == acao_inexistente.json()


def provocar_erros_internos(ambiente) -> list:
    """Provoca os dois erros internos (500) achados: número gigante na paginação e "NaN" na taxa de conquista.

    Devolve: as duas respostas. "NaN" ("não é um número") é um valor que o JSON do Python aceita e a conta com
    Decimal não sabe comparar; o número gigante não cabe no inteiro do SQLite.
    """
    # Empresa: pedir a página de envios a partir de um início com 23 dígitos
    numero_gigante = ambiente["horizonte"].get("/api/empresa/envios/pagina?inicio=99999999999999999999999"
                                               "&quantidade=5")
    # Banco: projetar o ganho com a taxa NaN (o corpo vai escrito à mão, porque o cliente não gera NaN)
    taxa_nan = ambiente["banco"].post("/api/banco/planejamento/ganho",
                                      content=b'{"filtros": {}, "premissas": {"percentual_novas_contas": NaN}, '
                                              b'"clientes_da_empresa": 10}',
                                      headers={"content-type": "application/json"})
    return [numero_gigante, taxa_nan]


def test_b12_erro_interno_nao_mostra_pane_caminho_sql_nem_versao(ambiente):
    """B-12: quando algo quebra por dentro (500), a resposta é só "Internal Server Error": sem stack trace, sem
    caminho de arquivo, sem SQL e sem versão; e a aplicação não está em modo de depuração."""
    # O modo de depuração do FastAPI mostraria a pane inteira na tela
    assert aplicacao.debug is False
    for resposta in provocar_erros_internos(ambiente):
        # São erros internos de verdade (se um dia virarem 400, o teste B-14 passa e este continua valendo)
        if resposta.status_code != 500:
            continue
        # Só a frase padrão, sem nenhum detalhe
        assert resposta.text == "Internal Server Error"
        assert sinais_de_detalhe_interno(resposta.text) == []


def test_b13_erro_interno_tambem_leva_os_cabecalhos_de_protecao(ambiente):
    """B-13: docs/seguranca.md 2.6 diz que TODA resposta leva os cabeçalhos de proteção, inclusive as recusas."""
    # As respostas dos dois erros internos
    respostas = provocar_erros_internos(ambiente)
    # Os cabeçalhos que faltam em cada uma
    faltando = []
    for resposta in respostas:
        faltando.extend(cabecalhos_que_faltam(resposta))
    assert faltando == []


def test_b14_entrada_fora_da_faixa_vira_recusa_clara_e_nao_erro_interno(ambiente):
    """B-14: valor fora da faixa é recusado com uma explicação (400 ou 422), nunca com um erro interno (500)."""
    # Os códigos de cada resposta
    codigos = []
    for resposta in provocar_erros_internos(ambiente):
        codigos.append(resposta.status_code)
    assert codigos[0] in (400, 422) and codigos[1] in (400, 422)


def test_b15_mensagem_de_erro_para_a_pessoa_nunca_e_texto_interno_do_python(ambiente, monkeypatch):
    """B-15: um erro que nasce dentro do Python (ex.: "month must be in 1..12") chega à tela como uma frase em
    português; a frase escrita por uma regra do projeto continua chegando como está.

    Como: a rota antiga do catálogo, onde o achado apareceu, saiu (as KBs do Endomarketing a substituíram). O teste
    prova o mecanismo: troca, só neste teste, o serviço da página de envios por um que quebra como o Python quebra.
    """

    def servico_que_quebra_por_dentro(*argumentos):
        """Monta uma data com o mês 13: o Python levanta ValueError("month must be in 1..12")."""
        return date(2027, 13, 1)

    # A troca vale só neste teste
    monkeypatch.setattr(acompanhamento, "pagina_de_envios", servico_que_quebra_por_dentro)
    resposta = ambiente["horizonte"].get("/api/empresa/envios/pagina?inicio=0&quantidade=5")
    # A recusa é esperada (400); o que não pode é a frase interna do Python
    assert resposta.status_code == 400
    assert "must be" not in resposta.json()["detail"]
    # (A frase de uma regra do projeto continuar indo como está é provada no C-22: "CNPJ não confere")


def test_b16_recusas_e_erros_de_formato_tambem_levam_os_cabecalhos_de_protecao(ambiente):
    """B-16: 404, 405 e 422 (e o desvio 303 do porteiro) trazem todos os cabeçalhos de proteção."""
    # Endereço que não existe (404)
    nao_existe = ambiente["horizonte"].get("/api/nao_existe")
    # Método errado (405)
    metodo_errado = ambiente["horizonte"].put("/api/eu")
    # Formato errado (422): texto no lugar do número
    formato_errado = ambiente["horizonte"].get("/api/empresa/envios/pagina?inicio=abc")
    # Página guardada sem login (303 para o login)
    desvio = navegador_sem_login().get("/home.html")
    for resposta in (nao_existe, metodo_errado, formato_errado, desvio):
        assert cabecalhos_que_faltam(resposta) == [], resposta.status_code


# ---------------- 4. Falhas comuns da web ----------------

# Os usos de innerHTML que recebem uma expressão (e não um texto fixo), conferidos um a um na leitura do código:
# - "item.urgente?:" (banco_inicio.js): escolhe entre dois ícones fixos; o dado só decide QUAL texto fixo entra;
# - "icone_do_cartao.innerHTML" e "detalhes_do_cartao.innerHTML" (janela_beneficio.js): copiam um pedaço da própria
#   página, que já foi montado com textContent (o navegador devolve o texto com os "<" escapados).
EXPRESSOES_CONFERIDAS = {"item.urgente?:", "icone_do_cartao.innerHTML", "detalhes_do_cartao.innerHTML"}
# Um texto fixo em JavaScript: entre aspas duplas, simples ou crases (a crase sem "${" também é fixa)
PADRAO_DE_TEXTO_FIXO = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\$]|\\.|\$(?!\{))*`")


def instrucao_a_partir_da_linha(linhas: list[str], posicao: int) -> str:
    """A instrução JavaScript que começa numa linha e termina na primeira linha acabada em ";".

    Recebe: linhas do arquivo; posicao — a linha do começo. Devolve: a instrução inteira, numa linha só.
    """
    # Junta as linhas até achar o fim da instrução
    pedacos = []
    for linha in linhas[posicao:]:
        pedacos.append(linha.strip())
        if linha.rstrip().endswith(";"):
            break
    return " ".join(pedacos)


def lado_direito_sem_textos_fixos(instrucao: str) -> str:
    """O que é atribuído ao innerHTML, sem os textos fixos, sem espaços, "+" e ";".

    Exemplos: 'x.innerHTML = "";' → ""; 'x.innerHTML = "<svg>" + nome;' → "nome".
    """
    # Tira os textos fixos (o que sobra é código: variáveis, chamadas, operadores)
    sem_textos = PADRAO_DE_TEXTO_FIXO.sub("", instrucao)
    # O que vem depois do primeiro "=" (a atribuição)
    lado_direito = sem_textos.split("=", 1)[1]
    # Sem espaços, "+" e ";"
    for caractere in (" ", "+", ";"):
        lado_direito = lado_direito.replace(caractere, "")
    return lado_direito


def test_b17_nenhuma_tela_escreve_dado_como_html():
    """B-17 (XSS, leitura do código): no front, innerHTML só recebe texto fixo (ícones, esqueletos, limpar lista);
    e ninguém usa outerHTML, insertAdjacentHTML, document.write ou eval."""
    # Os usos perigosos achados: "arquivo:linha → o que entra"
    achados = []
    for arquivo in sorted((PASTA_DO_FRONT / "js").glob("*.js")):
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        for posicao, linha in enumerate(linhas):
            # Formas de escrever HTML que o front não usa: qualquer uso é um achado
            if re.search(r"\.outerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(", linha):
                achados.append(f"{arquivo.name}:{posicao + 1} → {linha.strip()}")
                continue
            # Atribuição ao innerHTML ("=", mas não "==")
            if not re.search(r"\.innerHTML\s*=(?!=)", linha):
                continue
            # O que entra, sem os textos fixos
            expressao = lado_direito_sem_textos_fixos(instrucao_a_partir_da_linha(linhas, posicao))
            # Vazio (só texto fixo) ou uma das expressões conferidas: seguro
            if expressao == "" or expressao in EXPRESSOES_CONFERIDAS:
                continue
            achados.append(f"{arquivo.name}:{posicao + 1} → {expressao}")
    assert achados == []


def test_b18_nome_com_codigo_volta_so_como_dado_json_com_as_travas_do_navegador(ambiente):
    """B-18 (XSS, pela API): o nome "<img src=x onerror=alert(1)>" volta igual, mas só dentro de JSON, marcado como
    JSON, com nosniff (o navegador não o trata como página) e com a CSP (script injetado não roda)."""
    for rota in ("/api/empresa/funcionarios", "/api/empresa/pendencias"):
        resposta = ambiente["horizonte"].get(rota)
        # Marcado como JSON, nunca como página HTML
        assert resposta.headers["content-type"].startswith("application/json"), rota
        # O navegador não "adivinha" outro tipo
        assert resposta.headers["x-content-type-options"] == "nosniff", rota
        # A política de conteúdo só deixa rodar script de arquivo do site
        assert "script-src 'self'" in resposta.headers["content-security-policy"], rota
        # O nome volta como dado (a tela o escreve com textContent, B-17)
        assert NOME_COM_CODIGO in json.dumps(resposta.json(), ensure_ascii=False), rota


def test_b19_sql_injection_nos_filtros_identificadores_e_login_nao_muda_a_consulta(ambiente):
    """B-19: aspas e "OR 1=1" em filtros, identificadores e login são tratados como texto (consultas com "?")."""
    # Planejamento com um filtro de UF que tenta abrir a consulta: responde normal, com tudo zerado
    resposta = ambiente["banco"].get("/api/banco/planejamento", params={"uf": "SP' OR '1'='1"})
    assert resposta.status_code == 200
    assert resposta.json()["indicadores"]["funcionarios_processados"] == 0
    # O mesmo com um comentário de SQL no fim do filtro de empresa
    assert ambiente["banco"].get("/api/banco/planejamento", params={"empresa_id": "EMP002'--"}).status_code == 200
    # A coluna do filtro vem de uma lista fechada: um nome montado é recusado antes de virar consulta
    conexao = ambiente["conectar"]()
    with pytest.raises(ValueError):
        planejamento.valores_para_filtro(conexao, "uf FROM usuarios --")
    conexao.close()
    # Ficha de funcionário com um identificador que tenta trazer todos: não acha ninguém
    assert ambiente["horizonte"].get("/api/empresa/funcionarios/' OR '1'='1").status_code == 404
    # Download com o mesmo truque: nenhuma pessoa sai
    download = ambiente["horizonte"].post("/api/empresa/funcionarios/baixar",
                                          json={"identificadores": ["' OR 1=1 --"]})
    assert download.status_code == 400
    # Login com o truque clássico: recusado como qualquer senha errada
    login = navegador_sem_login().post("/api/entrar", json={"usuario": "' OR '1'='1' --", "senha": "' OR '1'='1"})
    assert login.status_code == 401


def test_b20_nenhum_arquivo_fora_da_pasta_do_front_e_entregue(ambiente):
    """B-20 (path traversal para fora): "../" cru ou codificado nunca entrega o .env nem o código do servidor."""
    # Tentativas de sair da pasta front/ (codificadas: %2e = ".", %2f = "/", %5c = "\")
    tentativas = ("/js/%2e%2e/%2e%2e/.env", "/%2e%2e/.env", "/js/..%2f..%2f.env", "/css/%2e%2e%5c%2e%2e%5c.env",
                  "/js/%2e%2e/%2e%2e/api/principal.py", "/api/%2e%2e/%2e%2e/requirements.txt")
    for navegador in (navegador_sem_login(), ambiente["horizonte"]):
        for endereco in tentativas:
            resposta = navegador.get(endereco)
            # Recusado (400/404) ou desviado para o login (303); nunca entregue
            assert resposta.status_code in (303, 400, 404), endereco
            # E nada do conteúdo desses arquivos (sem ler o .env: só procura nomes que estariam nele ou no código)
            assert "MODE=" not in resposta.text and "import " not in resposta.text and "fastapi" not in resposta.text


def test_b21_ponto_ponto_codificado_nao_pula_o_porteiro():
    """B-21: sem login, "/js/%2e%2e/home.html" (e variações) desvia para o login como "/home.html", nunca entrega a
    página. Hoje o porteiro vê "/js/..." (pasta pública) e o servidor de arquivos resolve para front/home.html."""
    # Páginas guardadas dos dois portais, alcançadas pelas três pastas públicas
    tentativas = ("/js/%2e%2e/home.html", "/css/%2e%2e/banco_inicio.html", "/api/%2e%2e/acompanhar.html",
                  "/js/..%2fbanco_envios.html", "/js/..%5chome.html")
    # As que foram entregues (200) sem login
    entregues = []
    for endereco in tentativas:
        if navegador_sem_login().get(endereco).status_code == 200:
            entregues.append(endereco)
    assert entregues == []


def test_b22_nenhuma_origem_de_fora_recebe_permissao_de_cors(ambiente):
    """B-22 (CORS): um site de fora não recebe "Access-Control-Allow-Origin" (nem na consulta nem na pré-consulta).

    CORS é a permissão que um site dá para OUTRO site ler as respostas dele pelo navegador da pessoa.
    """
    # Consulta comum vinda de um site de fora
    consulta = ambiente["horizonte"].get("/api/eu", headers={"Origin": "https://site-de-fora.example"})
    assert "access-control-allow-origin" not in consulta.headers
    # Pré-consulta (OPTIONS) que o navegador faz antes de um pedido de outro site
    pre_consulta = ambiente["horizonte"].options("/api/eu", headers={"Origin": "https://site-de-fora.example",
                                                                     "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre_consulta.headers
    assert "access-control-allow-credentials" not in pre_consulta.headers


def test_b23_metodos_inesperados_sao_recusados_sem_expor_nada(ambiente):
    """B-23: PUT, DELETE, PATCH e TRACE onde não existem recebem 405 com a frase padrão (nada de eco do pedido)."""
    # Métodos que a rota /api/eu não aceita (só GET)
    for metodo in ("PUT", "DELETE", "PATCH", "TRACE"):
        resposta = ambiente["horizonte"].request(metodo, "/api/eu")
        assert resposta.status_code == 405, metodo
        assert resposta.json() == {"detail": "Method Not Allowed"}, metodo
    # Apagar uma página do front: também 405
    assert ambiente["horizonte"].delete("/login.html").status_code == 405
