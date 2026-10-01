"""Congelamento da avaliação: a "foto" da prova e das métricas antes de medir (ADR-37, ADR-58).

Por que congelar: se a prova ou a forma de contar o acerto mudarem DEPOIS de ver um resultado, o
número deixa de ser confiável (é como trocar as questões depois de corrigir a prova). Então, antes de
medir, tiramos a impressão digital (SHA-256) de cada arquivo da prova e do código das métricas e
gravamos em data/avaliacao/congelamento.json. Os scripts de medição conferem a foto antes de rodar:
se algo mudou, eles se recusam a medir até alguém recongelar, dizendo o motivo.

O que fica congelado:
- a prova do Interpretador (300 cabeçalhos) e o vocabulário de teste;
- os gabaritos (golden) dos arquivos de envio;
- as consultas do RAG e os casos do guardrail;
- a calibração do B0 e o código das métricas e das avaliações (eval/metricas.py,
  eval/avaliacao_do_fluxo.py e eval/avaliacao_do_endomarketing.py);
- os casos do Endomarketing (data/avaliacao/endomarketing_casos.json);
- a amostra e o código da comparação de modelos (amostra_comparacao_modelos.json, eval/comparacao_de_modelos.py);
- as armadilhas do Conferidor da Leitura (data/avaliacao/conferidor_armadilhas.json; ADR-131);
- o conjunto de texto corrido difícil e a régua do Leitor (data/avaliacao/documentos_texto_dificil/,
  eval/avaliacao_do_leitor.py e scripts/avaliar_leitor.py; EXP-017);
- o manifesto da reserva do texto corrido difícil (data/avaliacao/reserva_d39_manifesto.json; os documentos ficam
  fora do Git);
- o manifesto do conjunto fora da distribuição do texto corrido difícil
  (data/avaliacao/fora_da_distribuicao_d39_manifesto.json);
- a prova por tipo de arquivo: o manifesto e a foto do parâmetro (data/avaliacao/prova_por_tipo/) e a régua
  (eval/ganho_por_tipo.py, eval/teste_pareado.py e scripts/avaliar_ganho_por_tipo.py).

Para recongelar: python scripts/congelar_avaliacao.py "motivo da mudança"
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# Pasta raiz do projeto: os caminhos da foto são relativos a ela (valem em qualquer máquina)
RAIZ = Path(__file__).resolve().parent.parent
# Onde a foto fica gravada
CAMINHO_DO_CONGELAMENTO = RAIZ / "data" / "avaliacao" / "congelamento.json"

# Os arquivos congelados, um por um
ARQUIVOS_CONGELADOS = [
    "data/avaliacao/cabecalhos_teste.jsonl",
    "data/vocabulario/teste.csv",
    "data/avaliacao/calibracao_b0.json",
    "data/avaliacao/consultas_rag.json",
    "data/avaliacao/guardrail_casos.json",
    "eval/metricas.py",
    "eval/avaliacao_do_fluxo.py",
    "eval/avaliacao_do_endomarketing.py",
    "data/avaliacao/endomarketing_casos.json",
    "data/avaliacao/amostra_comparacao_modelos.json",
    "eval/comparacao_de_modelos.py",
    # As armadilhas do Conferidor da Leitura (ADR-131): congeladas antes da primeira medição
    "data/avaliacao/conferidor_armadilhas.json",
    # A régua do Leitor de Documentos (EXP-017): a forma de contar não muda entre o antes e o depois da correção
    "eval/avaliacao_do_leitor.py",
    "scripts/avaliar_leitor.py",
    # O manifesto da reserva do texto corrido difícil (as impressões digitais do 2º conjunto, guardado FORA do
    # Git, em
    # D:\AI_Payroll_Hub\Bases_de_Teste\reserva_d39\; conferido com gerar_texto_corrido_dificil.diferencas_do_manifesto)
    "data/avaliacao/reserva_d39_manifesto.json",
    # O manifesto do conjunto fora da distribuição do texto corrido difícil (estruturas que o gerador público não tem; o gerador e os
    # documentos ficam fora do Git, em D:\AI_Payroll_Hub\Bases_de_Teste\reserva_d39\fora_da_distribuicao\)
    "data/avaliacao/fora_da_distribuicao_d39_manifesto.json",
    # A prova por tipo de arquivo (o ganho da IA por tipo): o manifesto (com a impressão digital de cada um dos 35
    # arquivos, que a medição confere), a foto do parâmetro usado e a régua (as contas, o teste pareado e a pessoa
    # simulada que responde o que o sistema pergunta)
    "data/avaliacao/prova_por_tipo/manifesto.json",
    "data/avaliacao/prova_por_tipo/parametro_do_layout.json",
    "eval/ganho_por_tipo.py",
    "eval/teste_pareado.py",
    "scripts/avaliar_ganho_por_tipo.py",
]
# Pasta cujos arquivos .json também ficam congelados (um gabarito por arquivo de envio)
PASTA_DOS_GABARITOS = "data/golden"
# O conjunto de texto corrido difícil (EXP-017): todos os arquivos da pasta (os .docx e o gabarito), congelados
# antes da correção da leitura; quem corrige não abre este conjunto
PASTA_DO_TEXTO_DIFICIL = "data/avaliacao/documentos_texto_dificil"


class AvaliacaoAlterada(Exception):
    """A prova ou as métricas mudaram depois do congelamento: medir agora não seria confiável."""


def impressao_digital(caminho: Path) -> str:
    """O SHA-256 do arquivo, igual no Windows e no Linux.

    O Windows costuma gravar o fim de linha como CRLF e o Linux como LF. Sem cuidado, o mesmo texto
    teria duas impressões digitais. Por isso, trocamos CRLF por LF antes de calcular.
    Exemplo: impressao_digital(Path("eval/metricas.py")) -> "3f5a...c9" (64 letras e números)
    """
    # Lê os bytes do arquivo
    conteudo = caminho.read_bytes()
    # Deixa o fim de linha igual em qualquer sistema
    conteudo = conteudo.replace(b"\r\n", b"\n")
    # Calcula a impressão digital
    return hashlib.sha256(conteudo).hexdigest()


def arquivos_da_prova() -> list[str]:
    """Todos os caminhos congelados (relativos à raiz), em ordem alfabética."""
    # Começa pelos arquivos da lista fixa
    caminhos = list(ARQUIVOS_CONGELADOS)
    # Soma cada gabarito de arquivo de envio
    for gabarito in (RAIZ / PASTA_DOS_GABARITOS).glob("*.json"):
        caminhos.append(f"{PASTA_DOS_GABARITOS}/{gabarito.name}")
    # Soma cada arquivo do conjunto de texto corrido difícil (os documentos e o gabarito)
    for arquivo in (RAIZ / PASTA_DO_TEXTO_DIFICIL).glob("*"):
        if arquivo.is_file():
            caminhos.append(f"{PASTA_DO_TEXTO_DIFICIL}/{arquivo.name}")
    # Ordem fixa: a foto sai igual toda vez
    caminhos.sort()
    return caminhos


def fotografar() -> dict:
    """A impressão digital de cada arquivo congelado. Exemplo: {"eval/metricas.py": "3f5a...c9", ...}"""
    foto = {}
    for caminho_relativo in arquivos_da_prova():
        foto[caminho_relativo] = impressao_digital(RAIZ / caminho_relativo)
    return foto


def congelar(motivo: str) -> dict:
    """Grava a foto atual em data/avaliacao/congelamento.json, com a data e o motivo."""
    # Sem motivo, ninguém sabe depois por que a prova mudou
    if not motivo.strip():
        raise ValueError("Informe o motivo do congelamento (ex.: 'prova inicial').")
    registro = {
        "data": datetime.now(timezone.utc).date().isoformat(),
        "motivo": motivo.strip(),
        "arquivos": fotografar(),
    }
    # Grava com fim de linha LF, para a foto do Git ficar igual em qualquer máquina
    texto = json.dumps(registro, ensure_ascii=False, indent=2) + "\n"
    CAMINHO_DO_CONGELAMENTO.write_text(texto, encoding="utf-8", newline="\n")
    return registro


def diferencas(foto_gravada: dict, foto_atual: dict) -> list[str]:
    """O que mudou entre a foto gravada e a atual, em frases. Lista vazia = nada mudou.

    Exemplo: ["alterado: eval/metricas.py", "novo, não congelado: data/golden/nova.json"]
    """
    mudancas = []
    # Arquivo congelado que mudou ou sumiu
    for caminho, impressao_gravada in foto_gravada.items():
        if caminho not in foto_atual:
            mudancas.append(f"removido: {caminho}")
        elif foto_atual[caminho] != impressao_gravada:
            mudancas.append(f"alterado: {caminho}")
    # Arquivo que apareceu depois do congelamento (ex.: um gabarito novo)
    for caminho in foto_atual:
        if caminho not in foto_gravada:
            mudancas.append(f"novo, não congelado: {caminho}")
    return mudancas


def conferir() -> list[str]:
    """Compara a foto gravada com os arquivos de hoje. Lista vazia = a prova está intacta."""
    # Sem foto gravada, nada foi congelado ainda: isso também impede medir
    if not CAMINHO_DO_CONGELAMENTO.exists():
        return ["a avaliação ainda não foi congelada (rode scripts/congelar_avaliacao.py)"]
    registro = json.loads(CAMINHO_DO_CONGELAMENTO.read_text(encoding="utf-8"))
    return diferencas(registro["arquivos"], fotografar())


def exigir_prova_congelada() -> None:
    """Para a medição se a prova ou as métricas mudaram depois do congelamento.

    Os scripts de medição chamam esta função antes de rodar.
    """
    mudancas = conferir()
    if mudancas:
        raise AvaliacaoAlterada("A prova ou as métricas mudaram depois do congelamento: "
                                + "; ".join(mudancas)
                                + ". Se a mudança é intencional, recongele informando o motivo.")
