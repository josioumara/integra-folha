"""O vocabulário de teste nunca aparece no treino (ADR-37).

Se aparecesse, a avaliação mediria memória, não inteligência. A comparação ignora maiúsculas,
acentos e pontuação: "Salário" e "SALARIO" contam como a mesma palavra.
"""
import csv
import unicodedata
from pathlib import Path

from models.contratos import carregar_layout
from scripts.dividir_vocabulario import dividir

# Onde ficam os arquivos do vocabulário
PASTA = Path(__file__).resolve().parent.parent / "data" / "vocabulario"


def normalizar(termo: str) -> str:
    """Sem acento, minúsculas, pontuação vira espaço: "Salário" e "SALARIO" ficam iguais."""
    sem_acento = unicodedata.normalize("NFKD", termo).encode("ascii", "ignore").decode()
    letras = []
    for caractere in sem_acento.lower():
        letras.append(caractere if caractere.isalnum() else " ")
    return " ".join("".join(letras).split())


def ler(nome: str) -> list[tuple[str, str]]:
    """Os pares (campo, termo) de um arquivo do vocabulário."""
    pares = []
    with open(PASTA / nome, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            pares.append((linha["campo"], linha["termo"]))
    return pares


def _termos_normalizados(nome: str) -> set[str]:
    """Todos os termos de um arquivo, normalizados."""
    termos = set()
    for _, termo in ler(nome):
        termos.add(normalizar(termo))
    return termos


def _campos(nome: str) -> set[str]:
    """Os campos que aparecem num arquivo do vocabulário."""
    campos = set()
    for campo, _ in ler(nome):
        campos.add(campo)
    return campos


def test_nenhum_termo_de_teste_aparece_no_treino():
    """Nenhum termo da prova está no treino."""
    treino = _termos_normalizados("treino.csv")
    teste = _termos_normalizados("teste.csv")
    assert treino & teste == set()


def test_todo_campo_do_layout_tem_termos_de_treino_e_de_teste():
    """Os 44 campos têm termos nos dois lados."""
    campos_do_layout = set()
    for campo in carregar_layout():
        campos_do_layout.add(campo.campo)
    assert _campos("treino.csv") == campos_do_layout
    assert _campos("teste.csv") == campos_do_layout


def test_um_termo_nunca_pertence_a_dois_campos():
    """O mesmo nome de coluna não pode significar dois campos diferentes."""
    dono_do_termo = {}
    for campo, termo in ler("sinonimos.csv"):
        chave = normalizar(termo)
        # O primeiro campo que usou o termo é o dono; outro campo com o mesmo termo falha
        assert dono_do_termo.setdefault(chave, campo) == campo, f"{termo!r} em {dono_do_termo[chave]} e {campo}"


def test_divisao_e_reproduzivel_com_a_mesma_seed():
    """Dividir duas vezes dá o mesmo resultado."""
    termos = {"cargo": ["Cargo", "Função", "Ocupação", "Posição"]}
    assert dividir(termos) == dividir(termos)


def test_arquivos_gravados_batem_com_a_divisao_atual():
    """treino.csv e teste.csv foram gerados pelo script, sem edição manual."""
    termos_por_campo = {}
    for campo, termo in ler("sinonimos.csv"):
        termos_por_campo.setdefault(campo, []).append(termo)
    treino, teste = dividir(termos_por_campo)
    assert treino == ler("treino.csv")
    assert teste == ler("teste.csv")
