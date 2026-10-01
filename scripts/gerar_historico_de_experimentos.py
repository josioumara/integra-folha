"""Gera docs/experimentos.md a partir dos registros de data/avaliacao/experimentos/ (ADR-66).

O documento conta a história das avaliações: a linha do tempo, a tabela que acompanha acurácia, recall e
precisão do Interpretador de experimento em experimento, e o detalhe de cada um (a pergunta, o que foi testado,
os números, a leitura e a decisão). Nada é escrito à mão: rodar de novo reconstrói o documento inteiro.

Para rodar: python scripts/gerar_historico_de_experimentos.py
"""
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.historico_de_experimentos import NUMEROS_RESERVADOS, listar  # noqa: E402

# Onde o documento é gravado
CAMINHO_DO_DOCUMENTO = RAIZ / "docs" / "experimentos.md"
# Como cada métrica aparece no documento
NOMES_DAS_METRICAS = {
    "acuracia_por_campo": "Acurácia por campo", "ic95_acuracia_por_campo": "IC 95%",
    "abstencao_recall": "Abstenção: recall", "abstencao_precisao": "Abstenção: precisão", "acerto_geral": "Acerto geral",
    "custo_usd": "Custo", "custo_por_planilha_usd": "Custo por planilha", "segundos_por_planilha": "Tempo por planilha",
    "respostas_fora_do_contrato": "Fora do contrato", "planilhas_pontuadas": "Planilhas",
    "hit_no_k_escolhido": "hit@k", "k_escolhido": "k", "trechos_de_outra_empresa": "Trechos de outra empresa",
    "deteccao": "Detecção", "falso_alarme": "Falso alarme", "recall_dos_erros_injetados": "Erros injetados achados",
}
# As métricas que são frações e aparecem como porcentagem
PORCENTAGENS = ("acuracia_por_campo", "abstencao_recall", "abstencao_precisao", "acerto_geral", "hit_no_k_escolhido",
                "deteccao", "falso_alarme", "recall_dos_erros_injetados")


def porcentagem(valor: float) -> str:
    """Fração como porcentagem brasileira. Ex.: 0.8444 → "84,4%"."""
    return f"{valor * 100:.1f}%".replace(".", ",")


def formatar(chave: str, valor) -> str:
    """O valor de uma métrica como aparece no documento."""
    if valor is None:
        return "não medido"
    if chave in PORCENTAGENS:
        return porcentagem(valor)
    if chave == "ic95_acuracia_por_campo":
        return f"{porcentagem(valor[0])} a {porcentagem(valor[1])}"
    if chave == "custo_por_planilha_usd":
        return f"US$ {valor:.4f}".replace(".", ",")
    if chave == "custo_usd":
        return f"US$ {valor:.2f}".replace(".", ",")
    if chave == "segundos_por_planilha":
        return f"{valor:g} s".replace(".", ",")
    return str(valor)


def nome_da_metrica(chave: str) -> str:
    """O nome da métrica em português (ou a própria chave, trocando "_" por espaço)."""
    return NOMES_DAS_METRICAS.get(chave, chave.replace("_", " "))


def _numero_do_registro(registro: dict) -> int:
    """O número do experimento. Ex.: {"id": "EXP-019"} → 19."""
    return int(registro["id"].split("-")[1])


def reservados_sem_registro(registros: list[dict]) -> list[tuple[int, str]]:
    """Os números reservados (NUMEROS_RESERVADOS) que ainda não têm registro, em ordem: [(número, o que é)]."""
    registrados = set()
    for registro in registros:
        registrados.add(_numero_do_registro(registro))
    reservados = []
    for numero, descricao in sorted(NUMEROS_RESERVADOS.items()):
        if numero not in registrados:
            reservados.append((numero, descricao))
    return reservados


def linha_do_tempo(registros: list[dict]) -> list[str]:
    """A tabela com um experimento por linha; o número reservado, que ainda não juntou, aparece como reservado."""
    linhas = ["| ID | Data | Experimento | Modo | Decisão |", "|---|---|---|---|---|"]
    reservados = reservados_sem_registro(registros)
    for registro in registros:
        # Os reservados que vêm antes deste registro entram antes dele, na ordem dos números
        while reservados and reservados[0][0] < _numero_do_registro(registro):
            numero, descricao = reservados.pop(0)
            linhas.append(f"| EXP-{numero:03d} | — | Reservado: {descricao} | — | — |")
        linhas.append(f"| {registro['id']} | {registro['data']} | {registro['titulo']} | {registro['modo']} | "
                      f"{registro.get('decisao', '—')} |")
    # Um reservado depois do último registro
    for numero, descricao in reservados:
        linhas.append(f"| EXP-{numero:03d} | — | Reservado: {descricao} | — | — |")
    return linhas


def evolucao_do_interpretador(registros: list[dict]) -> list[str]:
    """Acurácia, recall e precisão do Interpretador em cada experimento e modelo: a história das melhorias."""
    linhas = ["| Experimento | Configuração | Modelo | Acurácia por campo | Abstenção: recall | Abstenção: precisão | "
              "Custo por planilha | Amostra |", "|---|---|---|---|---|---|---|---|"]
    for registro in registros:
        if registro["tipo"] != "interpretador":
            continue
        for resultado in registro["resultados"]:
            metricas = resultado["metricas"]
            linhas.append(f"| {registro['id']} | {resultado['nome']} | `{resultado['modelo']}` | "
                          f"{formatar('acuracia_por_campo', metricas.get('acuracia_por_campo'))} | "
                          f"{formatar('abstencao_recall', metricas.get('abstencao_recall'))} | "
                          f"{formatar('abstencao_precisao', metricas.get('abstencao_precisao'))} | "
                          f"{formatar('custo_por_planilha_usd', metricas.get('custo_por_planilha_usd', 0.0))} | "
                          f"{registro['amostra']} |")
    return linhas


def tabela_de_resultados(resultados: list[dict]) -> list[str]:
    """Os resultados de um experimento: uma linha por configuração, uma coluna por métrica medida."""
    # As métricas que aparecem em pelo menos um resultado, na ordem em que surgem
    chaves = []
    for resultado in resultados:
        for chave in resultado["metricas"]:
            if chave not in chaves:
                chaves.append(chave)
    cabecalho = "| Configuração | Modelo |"
    separador = "|---|---|"
    for chave in chaves:
        cabecalho += f" {nome_da_metrica(chave)} |"
        separador += "---|"
    linhas = [cabecalho, separador]
    for resultado in resultados:
        linha = f"| {resultado['nome']} | `{resultado['modelo']}` |"
        for chave in chaves:
            if chave in resultado["metricas"]:
                linha += f" {formatar(chave, resultado['metricas'][chave])} |"
            else:
                linha += " — |"
        linhas.append(linha)
    return linhas


def detalhe(registro: dict) -> list[str]:
    """A seção de um experimento."""
    linhas = [f"### {registro['id']} · {registro['titulo']}", "",
              f"**Data:** {registro['data']} · **Modo:** {registro['modo']} · **Amostra:** {registro['amostra']}", "",
              f"**Pergunta:** {registro['pergunta']}", "",
              f"**O que testamos:** {registro['o_que_testamos']}", ""]
    linhas.extend(tabela_de_resultados(registro["resultados"]))
    linhas.extend(["", f"**Leitura:** {registro['leitura']}", ""])
    if registro.get("decisao"):
        linhas.extend([f"**Decisão:** {registro['decisao']}", ""])
    # Custo, fonte e commit, quando registrados
    rodape = []
    if "custo_usd" in registro:
        rodape.append(f"custo {formatar('custo_usd', registro['custo_usd'])}")
    if registro.get("fonte"):
        rodape.append(f"fonte `{registro['fonte']}`")
    if registro.get("commit"):
        rodape.append(f"commit `{registro['commit']}`")
    if rodape:
        linhas.extend([f"*{' · '.join(rodape)}*", ""])
    return linhas


def montar_documento() -> str:
    """O documento inteiro, em Markdown."""
    registros = listar()
    linhas = ["# Histórico de experimentos", "",
              "> Gerado por `scripts/gerar_historico_de_experimentos.py` a partir de `data/avaliacao/experimentos/`",
              "> (um registro por experimento, gravado uma vez e nunca sobrescrito, ADR-66). Não edite à mão.", "",
              "Cada experimento responde uma pergunta, com modelo, amostra e números registrados no dia. É a história",
              "das avaliações e melhorias do projeto; o estado atual consolidado está em [avaliacao.md](avaliacao.md).", "",
              "## Linha do tempo", ""]
    linhas.extend(linha_do_tempo(registros))
    linhas.extend(["", "## Interpretador: acurácia, recall e precisão ao longo dos experimentos", "",
                   "Recall da abstenção: das colunas que **precisavam** de pergunta, quantas o modelo perguntou. "
                   "Precisão: das perguntas que ele **fez**, quantas eram necessárias.", ""])
    linhas.extend(evolucao_do_interpretador(registros))
    linhas.extend(["", "## Detalhe de cada experimento", ""])
    for registro in registros:
        linhas.extend(detalhe(registro))
    return "\n".join(linhas).rstrip() + "\n"


def main() -> Path:
    """Grava o documento e devolve o caminho."""
    CAMINHO_DO_DOCUMENTO.write_text(montar_documento(), encoding="utf-8", newline="\n")
    return CAMINHO_DO_DOCUMENTO


if __name__ == "__main__":
    print(f"Documento gravado em {main()}")
