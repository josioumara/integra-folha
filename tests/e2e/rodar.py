"""Roda os roteiros de clique (ponta a ponta) num navegador de verdade, cada um num banco temporário e sem custo.

Para que serve: os testes do pytest conferem os serviços e as rotas; estes roteiros conferem a TELA, clicando como
uma pessoa: abrem o Chrome, entram com um usuário de teste, preenchem campos e conferem o que aparece. Cada roteiro:
    1. cria uma pasta temporária com um banco SQLite novo (o banco local e o PostgreSQL não são tocados);
    2. prepara os dados dele (usuários de teste, um envio parado em pendências...) num processo separado;
    3. sobe o servidor (FastAPI) numa porta livre, em modo MOCK e sem chave de API (nada de custo);
    4. percorre as telas e confere cada passo ("OK" ou "FALHOU"), junto com os erros de JavaScript da página;
    5. desliga o servidor e apaga a pasta temporária.

Como rodar (na pasta integra-folha, com o .venv e as dependências de tests/e2e/requirements.txt):
    python tests/e2e/rodar.py                                   todos os roteiros
    python tests/e2e/rodar.py cnpj_do_grupo parametros          só os roteiros escolhidos
Precisa do Google Chrome instalado: o Playwright usa o Chrome do computador (channel="chrome").

Por que não é pytest: cada roteiro sobe um servidor e abre um navegador (dezenas de segundos); fica fora da bateria
rápida, que roda a cada mudança. Os nomes dos arquivos não começam com "test_", então o pytest não os recolhe.
"""
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# A pasta integra-folha/ (onde ficam api/, services/ e o .venv)
RAIZ = Path(__file__).resolve().parents[2]
# Os roteiros (um arquivo por roteiro, na pasta tests/e2e/roteiros/)
PASTA_DOS_ROTEIROS = Path(__file__).resolve().parent / "roteiros"
# Quanto tempo esperar o servidor responder (em segundos)
ESPERA_DO_SERVIDOR = 60

# Deixa "tests.e2e.roteiros.<nome>" importável a partir daqui
sys.path.insert(0, str(RAIZ))


def roteiros_disponiveis() -> list[str]:
    """Os nomes dos roteiros (os arquivos .py da pasta roteiros/, sem o __init__), em ordem alfabética.

    Exemplo: ["cnpj_do_grupo", "parametros", "preencher_para_todos"].
    """
    nomes = []
    for arquivo in sorted(PASTA_DOS_ROTEIROS.glob("*.py")):
        # O __init__.py só marca a pasta como pacote
        if arquivo.stem != "__init__":
            nomes.append(arquivo.stem)
    return nomes


def variaveis_do_ambiente(pasta: Path) -> dict:
    """As variáveis de ambiente do roteiro: tudo aponta para a pasta temporária, em MOCK e sem chaves.

    Recebe: a pasta temporária. Devolve: uma cópia do ambiente atual com as trocas.
    Por que as chaves vazias: o .env é lido sem sobrescrever o que já está no ambiente, então uma chave vazia aqui
    garante que nenhuma chamada paga aconteça, mesmo com a chave no .env.
    """
    ambiente = dict(os.environ)
    ambiente.update({
        "BANCO": "sqlite",                                       # banco em arquivo, só deste roteiro
        "POSTGRES_URL": "",
        "CAMINHO_BANCO": str(pasta / "banco.db"),
        "CAMINHO_CHECKPOINTS": str(pasta / "checkpoints.db"),   # os pontos de salvamento do fluxo
        "PASTA_UPLOADS": str(pasta / "uploads"),
        "PASTA_HOMOLOGADOS": str(pasta / "homologados"),
        "MODE": "mock",                                          # IA simulada: sem custo
        "APRENDIZADO_DO_RAG": "desligado",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "MODELO_GRANDE": "",
        "MODELO_PEQUENO": "",
        "PYTHONIOENCODING": "utf-8",
        "E2E_PASTA": str(pasta),                                 # onde o preparar() grava arquivos de exemplo
    })
    return ambiente


def porta_livre() -> int:
    """Uma porta de rede livre no computador (o sistema escolhe ao pedir a porta 0)."""
    with socket.socket() as conexao_de_rede:
        conexao_de_rede.bind(("127.0.0.1", 0))
        return conexao_de_rede.getsockname()[1]


def preparar_os_dados(nome: str, pasta: Path, ambiente: dict) -> dict:
    """Roda o preparar() do roteiro num processo separado (com o ambiente temporário) e devolve os dados dele.

    Por que outro processo: a configuração da aplicação (services/config.py) lê o ambiente uma vez, ao ser importada.
    Rodando à parte, cada roteiro começa com o banco dele, e este processo nunca abre o banco de verdade.
    """
    arquivo_dos_dados = pasta / "dados.json"
    comando = [sys.executable, str(Path(__file__).resolve()), "--preparar", nome, str(arquivo_dos_dados)]
    resultado = subprocess.run(comando, cwd=RAIZ, env=ambiente, capture_output=True, text=True, encoding="utf-8")
    # Deu erro na preparação: mostra a saída para quem rodou entender
    if resultado.returncode != 0:
        raise RuntimeError("A preparação do roteiro " + nome + " falhou:\n" + resultado.stdout + resultado.stderr)
    return json.loads(arquivo_dos_dados.read_text(encoding="utf-8"))


def subir_o_servidor(porta: int, ambiente: dict) -> subprocess.Popen:
    """Sobe a API (uvicorn) na porta informada e espera ela responder. Devolve o processo, para desligar depois."""
    comando = [sys.executable, "-m", "uvicorn", "api.principal:aplicacao", "--port", str(porta)]
    processo = subprocess.Popen(comando, cwd=RAIZ, env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    endereco = "http://127.0.0.1:" + str(porta) + "/login.html"
    limite = time.monotonic() + ESPERA_DO_SERVIDOR
    # Tenta até o servidor responder (ou o tempo acabar)
    while time.monotonic() < limite:
        try:
            urllib.request.urlopen(endereco, timeout=2)
            return processo
        except OSError:
            time.sleep(0.5)
    processo.terminate()
    raise RuntimeError("O servidor não respondeu em " + str(ESPERA_DO_SERVIDOR) + " segundos.")


def rodar_um_roteiro(nome: str) -> tuple[list[str], list[str]]:
    """Roda um roteiro do começo ao fim. Devolve (as linhas de resultado, os erros de JavaScript da página)."""
    from playwright.sync_api import sync_playwright
    roteiro = importlib.import_module("tests.e2e.roteiros." + nome)
    pasta = Path(tempfile.mkdtemp(prefix="e2e_" + nome + "_"))
    ambiente = variaveis_do_ambiente(pasta)
    resultados, erros_da_pagina = [], []

    def conferir(descricao: str, condicao: bool) -> None:
        """Anota um passo conferido: "OK" se a condição vale, "FALHOU" se não."""
        if condicao:
            resultados.append("OK      " + descricao)
        else:
            resultados.append("FALHOU  " + descricao)

    servidor = None
    # try/finally: o servidor desliga e a pasta some mesmo se o roteiro der erro
    try:
        dados = preparar_os_dados(nome, pasta, ambiente)
        porta = porta_livre()
        servidor = subir_o_servidor(porta, ambiente)
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(channel="chrome")
            # Um passo que quebra (ex.: um elemento que não apareceu) vira "FALHOU", e os outros roteiros seguem
            try:
                roteiro.percorrer(navegador, "http://127.0.0.1:" + str(porta), dados, conferir, erros_da_pagina)
            except Exception as erro:  # noqa: BLE001 (qualquer erro do roteiro é um resultado, não uma parada)
                conferir("o roteiro parou no meio: " + str(erro).splitlines()[0][:150], False)
            navegador.close()
    finally:
        if servidor is not None:
            servidor.terminate()
            servidor.wait(timeout=20)
        shutil.rmtree(pasta, ignore_errors=True)
    return resultados, erros_da_pagina


def principal(nomes_pedidos: list[str]) -> int:
    """Roda os roteiros pedidos (ou todos) e mostra o resultado. Devolve 0 se tudo passou e 1 se algo falhou."""
    nomes = nomes_pedidos or roteiros_disponiveis()
    for nome in nomes:
        if nome not in roteiros_disponiveis():
            print("Roteiro desconhecido:", nome, "| disponíveis:", ", ".join(roteiros_disponiveis()))
            return 1
    algo_falhou = False
    for nome in nomes:
        print("\n=== " + nome + " ===")
        resultados, erros_da_pagina = rodar_um_roteiro(nome)
        for linha in resultados:
            print(linha)
        print("erros de JavaScript na página:", erros_da_pagina or "nenhum")
        # Um passo que falhou ou um erro de JavaScript reprova o roteiro
        falhas = 0
        for linha in resultados:
            if linha.startswith("FALHOU"):
                falhas = falhas + 1
        if falhas or erros_da_pagina or not resultados:
            algo_falhou = True
    print("\nResultado:", "ALGO FALHOU" if algo_falhou else "tudo certo")
    return 1 if algo_falhou else 0


def preparar_neste_processo(nome: str, arquivo_dos_dados: str) -> None:
    """O lado "filho" de preparar_os_dados: roda o preparar() do roteiro e grava o que ele devolveu em JSON."""
    roteiro = importlib.import_module("tests.e2e.roteiros." + nome)
    dados = roteiro.preparar()
    Path(arquivo_dos_dados).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    # O mesmo arquivo faz os dois papéis: rodar os roteiros ou (chamado por ele mesmo) preparar um deles
    if len(sys.argv) >= 4 and sys.argv[1] == "--preparar":
        preparar_neste_processo(sys.argv[2], sys.argv[3])
    else:
        sys.exit(principal(sys.argv[1:]))
