"""Testes da data da versão no rodapé de todas as telas (ADR-133; services/versao_da_aplicacao.py e /api/versao).

O que se prova aqui:
    - a data vem, em ordem, da variável DATA_DA_VERSAO, do arquivo preenchido pelo "git archive" e do Git;
    - sem nenhuma das três (sem Git, arquivo com o marcador, variável com lixo), não há data: nunca se inventa;
    - o texto sai no horário de Brasília ("Atualizado em 29/09/2026 às 14:30"), com commits feitos em outros fusos;
    - a rota /api/versao abre sem login, para os dois perfis, e devolve só o texto;
    - todas as telas (menos a que só redireciona) têm o lugar do rótulo e o script que o preenche.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from services import versao_da_aplicacao

# A pasta das telas do front
PASTA_DO_FRONT = Path(__file__).resolve().parent.parent / "front"
# A única tela sem o rótulo: o endereço antigo que só leva ao Endomarketing (não tem rodapé)
TELAS_SEM_RODAPE = {"banco_beneficios.html"}
# O começo de todo rótulo, seguido de data e hora
FORMATO_DO_ROTULO = r"^Atualizado em \d{2}/\d{2}/\d{4} às \d{2}:\d{2}$"


@pytest.fixture(autouse=True)
def sem_data_guardada(monkeypatch):
    """Cada teste começa sem a variável DATA_DA_VERSAO e sem a data guardada, e termina sem a data guardada."""
    # Tira a variável, se o computador a tiver
    monkeypatch.delenv(versao_da_aplicacao.NOME_DA_VARIAVEL, raising=False)
    # Esquece a data lida por outro teste
    versao_da_aplicacao.esquecer_data_guardada()
    # Roda o teste
    yield
    # Esquece a data deste teste, para não sobrar para o próximo
    versao_da_aplicacao.esquecer_data_guardada()


def criar_repositorio_com_um_commit(pasta: Path, data_do_commit: str) -> None:
    """Cria um repositório Git na pasta, com um commit de TUDO o que está nela, na data informada.

    Recebe: pasta; data_do_commit — ex.: "2026-09-29T14:30:00-03:00" (vale para o autor e para o "committer").
    """
    # O ambiente do Git com a data fixa do commit (a do autor e a do "committer")
    ambiente = dict(os.environ)
    ambiente["GIT_AUTHOR_DATE"] = data_do_commit
    ambiente["GIT_COMMITTER_DATE"] = data_do_commit
    # Um nome e um e-mail só deste repositório de teste (sem mexer na configuração do computador)
    identidade = ["-c", "user.name=Teste", "-c", "user.email=teste@exemplo.invalid"]
    # Um arquivo qualquer, para o commit nunca sair vazio
    (pasta / "leia.txt").write_text("teste", encoding="utf-8")
    # Cria o repositório, junta todos os arquivos da pasta e faz o commit
    subprocess.run(["git", "init", "-q", str(pasta)], check=True)
    subprocess.run(["git", "-C", str(pasta), "add", "--all"], check=True)
    subprocess.run(["git", "-C", str(pasta), *identidade, "commit", "-q", "-m", "um commit"], check=True, env=ambiente)


# ---------------- A leitura da data ----------------

def test_texto_iso_com_fuso_vira_data_e_o_resto_nao():
    """Só uma data ISO com fuso conta; vazio, marcador do Git, data sem fuso e lixo ficam sem data."""
    # Datas de verdade, com fuso ("-03:00" e o "Z" do horário universal)
    assert versao_da_aplicacao.ler_data_iso("2026-09-29T14:30:00-03:00") is not None
    assert versao_da_aplicacao.ler_data_iso(" 2026-09-29T17:30:00Z\n") is not None
    # O que não é data confiável
    for texto in (None, "", "   ", "$Format:%cI$", "ontem", "2026-09-29T14:30:00", "29/09/2026 14:30"):
        assert versao_da_aplicacao.ler_data_iso(texto) is None, texto


def test_rotulo_no_horario_de_brasilia_com_commit_de_outro_fuso():
    """O rótulo sai sempre no horário de Brasília, com zero à esquerda, e virando o dia quando precisa."""
    # O mesmo instante escrito em três fusos: Brasília, horário universal e Lisboa no verão (+01:00)
    for texto in ("2026-09-29T14:30:00-03:00", "2026-09-29T17:30:00Z", "2026-09-29T18:30:00+01:00"):
        data = versao_da_aplicacao.ler_data_iso(texto)
        assert versao_da_aplicacao.texto_do_rotulo(data) == "Atualizado em 29/09/2026 às 14:30", texto
    # Madrugada no horário universal ainda é o dia anterior em Brasília
    data_da_madrugada = versao_da_aplicacao.ler_data_iso("2026-10-01T02:05:00Z")
    assert versao_da_aplicacao.texto_do_rotulo(data_da_madrugada) == "Atualizado em 30/09/2026 às 23:05"
    # Sem data, sem rótulo
    assert versao_da_aplicacao.texto_do_rotulo(None) is None


def test_data_do_git_com_repositorio(tmp_path):
    """Numa pasta com Git, a data é a do último commit."""
    # Um repositório com um commit feito em 05/09/2026 às 08:05 (Brasília)
    criar_repositorio_com_um_commit(tmp_path, "2026-09-05T08:05:00-03:00")
    # O Git devolve a data do commit
    data = versao_da_aplicacao.data_do_git(tmp_path)
    assert versao_da_aplicacao.texto_do_rotulo(data) == "Atualizado em 05/09/2026 às 08:05"


def test_sem_git_nao_ha_data(tmp_path):
    """Numa pasta que não é repositório (como o site publicado, sem a pasta .git), o Git não dá data."""
    # Uma pasta vazia, fora de qualquer repositório (a pasta temporária do sistema)
    assert versao_da_aplicacao.data_do_git(tmp_path) is None


def test_git_nao_instalado_nao_derruba(tmp_path, monkeypatch):
    """Sem o programa git no computador, fica sem data, sem erro."""
    # Finge que o programa git não existe
    def git_que_nao_existe(*argumentos, **opcoes):
        raise FileNotFoundError("git")
    monkeypatch.setattr(versao_da_aplicacao.subprocess, "run", git_que_nao_existe)
    # Sem data, e o servidor segue
    assert versao_da_aplicacao.data_do_git(tmp_path) is None


def test_arquivo_preenchido_pelo_git_archive_e_com_o_marcador(tmp_path):
    """O arquivo vale quando o "git archive" trocou o marcador pela data; com o marcador ou ausente, não vale."""
    # O arquivo como o "git archive" deixa (a data do commit e uma quebra de linha)
    arquivo_preenchido = tmp_path / "preenchido.txt"
    arquivo_preenchido.write_text("2026-09-29T14:30:00-03:00\n", encoding="utf-8")
    data = versao_da_aplicacao.data_do_arquivo(arquivo_preenchido)
    assert versao_da_aplicacao.texto_do_rotulo(data) == "Atualizado em 29/09/2026 às 14:30"
    # O arquivo como está no Git (o marcador ainda não trocado)
    arquivo_com_marcador = tmp_path / "marcador.txt"
    arquivo_com_marcador.write_text("$Format:%cI$\n", encoding="utf-8")
    assert versao_da_aplicacao.data_do_arquivo(arquivo_com_marcador) is None
    # Sem o arquivo
    assert versao_da_aplicacao.data_do_arquivo(tmp_path / "nao_existe.txt") is None


def test_arquivo_ilegivel_fica_sem_data_e_a_rota_nao_quebra(tmp_path, monkeypatch):
    """Um arquivo que não pode ser lido (uma pasta no lugar, bytes que não são texto) fica sem data, sem erro 500."""
    # Uma pasta com o nome do arquivo: existe, mas não se lê como texto (erro do sistema, OSError)
    pasta_no_lugar = tmp_path / "pasta_no_lugar.txt"
    pasta_no_lugar.mkdir()
    assert versao_da_aplicacao.data_do_arquivo(pasta_no_lugar) is None
    # Bytes que não são texto UTF-8 (erro de decodificação)
    arquivo_com_bytes_errados = tmp_path / "bytes_errados.txt"
    arquivo_com_bytes_errados.write_bytes(b"\xff\xfe\x00data")
    assert versao_da_aplicacao.data_do_arquivo(arquivo_com_bytes_errados) is None
    # A rota sem login, com esse arquivo e sem Git: responde 200 com texto nulo, nunca erro
    monkeypatch.setattr(versao_da_aplicacao, "ARQUIVO_DA_VERSAO", arquivo_com_bytes_errados)
    monkeypatch.setattr(versao_da_aplicacao, "RAIZ_DO_REPOSITORIO", tmp_path)
    resposta = TestClient(aplicacao, raise_server_exceptions=False).get("/api/versao")
    assert resposta.status_code == 200
    assert resposta.json() == {"texto": None}


def test_o_arquivo_do_repositorio_tem_o_marcador_e_a_regra_do_git():
    """No repositório, o arquivo guarda o marcador, e o .gitattributes manda o "git archive" preenchê-lo."""
    # O marcador que o Git troca pela data do commit
    assert versao_da_aplicacao.ARQUIVO_DA_VERSAO.read_text(encoding="utf-8").strip() == "$Format:%cI$"
    # A regra "export-subst" para esse arquivo
    regras = (versao_da_aplicacao.RAIZ_DO_REPOSITORIO / ".gitattributes").read_text(encoding="utf-8")
    assert "versao_da_aplicacao.txt export-subst" in regras


def test_git_archive_preenche_o_arquivo(tmp_path):
    """O caminho do site publicado: o "git archive" troca o marcador pela data do commit (a regra export-subst)."""
    # Um repositório com o arquivo (com o marcador), a regra e um commit numa data fixa
    (tmp_path / "versao_da_aplicacao.txt").write_text("$Format:%cI$\n", encoding="utf-8")
    (tmp_path / ".gitattributes").write_text("versao_da_aplicacao.txt export-subst\n", encoding="utf-8")
    criar_repositorio_com_um_commit(tmp_path, "2026-09-29T14:30:00-03:00")
    # O que sai do "git archive" para esse arquivo (o mesmo comando do publicar.sh, só com este arquivo)
    resultado = subprocess.run(["git", "-C", str(tmp_path), "archive", "--format=tar", "HEAD",
                                "versao_da_aplicacao.txt"], capture_output=True, check=True)
    # O marcador foi trocado pela data do commit
    assert b"2026-09-29T14:30:00-03:00" in resultado.stdout
    assert b"$Format" not in resultado.stdout


def test_ordem_das_fontes(tmp_path, monkeypatch):
    """A variável vale mais que o arquivo, que vale mais que o Git; variável com lixo é ignorada."""
    # O arquivo preenchido, numa pasta com um Git que responderia outra data (10/09)
    arquivo = tmp_path / "versao.txt"
    arquivo.write_text("2026-09-20T10:00:00-03:00", encoding="utf-8")
    criar_repositorio_com_um_commit(tmp_path, "2026-09-10T10:00:00-03:00")
    monkeypatch.setattr(versao_da_aplicacao, "ARQUIVO_DA_VERSAO", arquivo)
    monkeypatch.setattr(versao_da_aplicacao, "RAIZ_DO_REPOSITORIO", tmp_path)
    # Sem a variável: vale o arquivo
    rotulo = versao_da_aplicacao.texto_do_rotulo(versao_da_aplicacao.descobrir_data_da_versao())
    assert rotulo == "Atualizado em 20/09/2026 às 10:00"
    # Sem o arquivo preenchido: vale o Git
    arquivo.write_text("$Format:%cI$", encoding="utf-8")
    rotulo = versao_da_aplicacao.texto_do_rotulo(versao_da_aplicacao.descobrir_data_da_versao())
    assert rotulo == "Atualizado em 10/09/2026 às 10:00"
    # Com o arquivo preenchido de novo e a variável: vale a variável
    arquivo.write_text("2026-09-20T10:00:00-03:00", encoding="utf-8")
    monkeypatch.setenv("DATA_DA_VERSAO", "2026-09-29T14:30:00-03:00")
    rotulo = versao_da_aplicacao.texto_do_rotulo(versao_da_aplicacao.descobrir_data_da_versao())
    assert rotulo == "Atualizado em 29/09/2026 às 14:30"
    # Com lixo na variável: ela é ignorada, e volta a valer o arquivo
    monkeypatch.setenv("DATA_DA_VERSAO", "amanha")
    rotulo = versao_da_aplicacao.texto_do_rotulo(versao_da_aplicacao.descobrir_data_da_versao())
    assert rotulo == "Atualizado em 20/09/2026 às 10:00"


def test_sem_nenhuma_fonte_nao_ha_rotulo(tmp_path, monkeypatch):
    """Sem variável, com o arquivo ainda com o marcador e sem Git: não há data, e o rótulo não aparece."""
    # O arquivo com o marcador (como numa imagem montada sem o "git archive") e nenhum Git
    arquivo = tmp_path / "versao.txt"
    arquivo.write_text("$Format:%cI$", encoding="utf-8")
    monkeypatch.setattr(versao_da_aplicacao, "ARQUIVO_DA_VERSAO", arquivo)
    monkeypatch.setattr(versao_da_aplicacao, "RAIZ_DO_REPOSITORIO", tmp_path)
    # Nenhuma data, nenhum texto
    assert versao_da_aplicacao.rotulo_da_versao() == {"texto": None}


def test_a_data_e_lida_uma_vez_so(monkeypatch):
    """A data é a da versão que o servidor carregou: lida na primeira consulta e guardada."""
    # Conta quantas vezes a data é descoberta
    vezes = []
    def descobrir_contando():
        # Anota mais uma descoberta e devolve uma data fixa
        vezes.append(1)
        return versao_da_aplicacao.ler_data_iso("2026-09-29T14:30:00-03:00")
    # A aplicação passa a usar a descoberta que conta
    monkeypatch.setattr(versao_da_aplicacao, "descobrir_data_da_versao", descobrir_contando)
    # Três consultas, sempre com o mesmo texto
    for numero_da_consulta in range(3):
        assert versao_da_aplicacao.rotulo_da_versao() == {"texto": "Atualizado em 29/09/2026 às 14:30"}
    # E uma descoberta só
    assert len(vezes) == 1


# ---------------- A rota ----------------

def test_rota_abre_sem_login_e_devolve_so_o_texto(monkeypatch):
    """Sem login (a tela de login mostra o rótulo), a rota responde 200 com só o texto pronto."""
    # Uma data fixa pela variável
    monkeypatch.setenv("DATA_DA_VERSAO", "2026-09-29T14:30:00-03:00")
    # Um navegador sem login pede a data
    resposta = TestClient(aplicacao).get("/api/versao")
    # 200, só a chave "texto", no formato do rodapé
    assert resposta.status_code == 200
    assert resposta.json() == {"texto": "Atualizado em 29/09/2026 às 14:30"}


def test_rota_sem_data_devolve_nulo(monkeypatch):
    """Sem data confiável, a rota devolve texto nulo (e a tela esconde o rótulo)."""
    # Nenhuma fonte dá data
    def descobrir_sem_data():
        # Nenhuma das três fontes respondeu
        return None
    # A aplicação passa a usar a descoberta sem data
    monkeypatch.setattr(versao_da_aplicacao, "descobrir_data_da_versao", descobrir_sem_data)
    # Um navegador sem login pede a data
    resposta = TestClient(aplicacao).get("/api/versao")
    # 200, com o texto nulo (e a tela deixa o rótulo escondido)
    assert resposta.status_code == 200
    assert resposta.json() == {"texto": None}


def test_rota_da_versao_de_verdade_tem_o_formato_do_rodape():
    """Com as fontes de verdade (aqui, o Git da cópia do repositório), o texto tem data e hora."""
    # A resposta de verdade (sem trocar nada)
    texto = TestClient(aplicacao).get("/api/versao").json()["texto"]
    # Na máquina local há Git; se um dia os testes rodarem sem Git, o texto é nulo (e nunca inventado)
    if texto is not None:
        assert re.match(FORMATO_DO_ROTULO, texto)


# ---------------- As telas ----------------

def test_todas_as_telas_tem_o_lugar_do_rotulo_e_o_script():
    """Toda tela com rodapé tem o lugar do rótulo (escondido até a data chegar) e o script que o preenche."""
    # As telas sem o lugar ou sem o script
    telas_incompletas = []
    # Cada tela do front, em ordem alfabética
    for tela in sorted(PASTA_DO_FRONT.glob("*.html")):
        # A tela que só redireciona não tem rodapé: fica de fora
        if tela.name in TELAS_SEM_RODAPE:
            continue
        # O código da tela
        conteudo = tela.read_text(encoding="utf-8")
        # O lugar começa escondido: sem data, nada aparece (nunca uma data de exemplo)
        tem_o_lugar = "data-data-da-versao hidden" in conteudo
        # O script que pede a data e preenche o lugar
        tem_o_script = '<script src="js/data_da_versao.js"></script>' in conteudo
        # Faltou um dos dois: anota a tela
        if not tem_o_lugar or not tem_o_script:
            telas_incompletas.append(tela.name)
    # Nenhuma tela incompleta
    assert telas_incompletas == []
    # A varredura precisa ter varrido as telas dos dois portais e o login
    assert len(list(PASTA_DO_FRONT.glob("*.html"))) >= 15


def test_o_rotulo_fica_oculto_nesta_versao_em_todas_as_telas():
    """O rótulo "Atualizado em ..." não aparece nesta versão (ADR-148): o lugar de toda tela tem a marca de oculto, e o
    script só preenche os lugares sem a marca (com todos marcados, ele nem pergunta a data ao servidor)."""
    # A marca que o lugar do rótulo tem de trazer em toda tela
    lugar_oculto = 'data-data-da-versao hidden data-oculto-nesta-versao="data-da-versao"'
    # As telas com o lugar do rótulo sem a marca (o rótulo apareceria)
    telas_com_o_rotulo_a_mostra = []
    for tela in sorted(PASTA_DO_FRONT.glob("*.html")):
        conteudo = tela.read_text(encoding="utf-8")
        if "data-data-da-versao" in conteudo and lugar_oculto not in conteudo:
            telas_com_o_rotulo_a_mostra.append(tela.name)
    assert telas_com_o_rotulo_a_mostra == []
    # O script pula os lugares marcados
    script = (PASTA_DO_FRONT / "js" / "data_da_versao.js").read_text(encoding="utf-8")
    assert "[data-data-da-versao]:not([data-oculto-nesta-versao])" in script
