"""Roda o experimento EXP-010: os documentos de teste pelo Leitor de Documentos, com a IA vendo os dados.

Roda um dos dois conjuntos de documentos (desenvolvimento ou prova; ver scripts/gerar_documentos_de_teste.py).
Mede, por nível de documento (N1 a N5) e por modo, o acerto por campo, as armadilhas respeitadas, as perguntas, os
dados de terceiros vazados, o custo e o tempo (régua em eval/avaliacao_do_leitor.py). Grava o resultado bruto em
data/avaliacao/resultados/leitor_de_documentos_<conjunto>.json. Registrar o experimento no histórico é um passo à parte, depois
de ler os números (ADR-66).

Custa dinheiro quando o .env está em MODE=llm (a leitura do texto corrido chama a IA). Os documentos são 100%
fictícios.

Desde o ADR-101, a IA sempre lê os dados reais, e o modo "etiquetas" (a IA lia os dados trocados por etiquetas) saiu
da plataforma. O resultado dele continua no registro do EXP-010; o código que o rodava está no commit 3910943.

Uso:
  python scripts/avaliar_leitor.py --conjunto prova               (todos os documentos)
  python scripts/avaliar_leitor.py --documentos N5_texto_misturado_a     (um piloto)
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agents import leitor_de_documentos  # noqa: E402
from scripts.gerar_documentos_de_teste import pasta_do_conjunto  # noqa: E402
from eval import avaliacao_do_leitor  # noqa: E402
from eval.congelamento import exigir_prova_congelada  # noqa: E402
from models.contratos import carregar_layout  # noqa: E402
from services import config, leitura_de_word  # noqa: E402

PASTA_DOS_RESULTADOS = RAIZ / "data" / "avaliacao" / "resultados"
# O modo medido: "dados" (a IA vê os dados reais, ADR-101). O nome fica para comparar com o registro do EXP-010
MODOS = ("dados",)
# Níveis lidos por regra (sem IA): aparecem com o modo "regra"
NIVEIS_SEM_IA = ("N1", "N2")


def ler_opcoes() -> argparse.Namespace:
    """Os documentos e os modos a rodar (sem informar, todos)."""
    leitor = argparse.ArgumentParser(description="Experimento EXP-010: Leitor de Documentos por nível e por modo.")
    leitor.add_argument("--conjunto", default="desenvolvimento", help="desenvolvimento ou prova")
    leitor.add_argument("--documentos", default="", help="nomes dos documentos, separados por vírgula (sem .docx)")
    leitor.add_argument("--modos", default=",".join(MODOS), help="dados (o único modo desde o ADR-101)")
    leitor.add_argument("--esforco", default=config.LEITOR_ESFORCO, help="low, medium ou high")
    leitor.add_argument("--saida", default="", help="onde gravar (padrão: resultados/leitor_de_documentos_<conjunto>.json)")
    return leitor.parse_args()


def commit_atual() -> str:
    """O commit do código medido (para o registro do experimento)."""
    resultado = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True)
    return resultado.stdout.strip()


def ler_um_documento(conteudo: bytes, campos, esforco: str) -> tuple[dict, float]:
    """Lê o documento. Devolve (o que saiu da leitura, segundos gastos)."""
    config.LEITOR_ESFORCO = esforco
    cliente = leitor_de_documentos.cliente_padrao()
    inicio = time.time()
    try:
        leitura = leitura_de_word.ler_word(conteudo, cliente, campos)
        # A régua compara por campo do layout: as colunas por rótulo do texto corrido voltam a ser uma por campo
        saida = {"linhas": leitura_de_word.linhas_pelos_campos(leitura), "duvidas": leitura.duvidas,
                 "avisos": leitura.avisos,
                 "como_foi_lido": leitura.como_foi_lido, "uso": leitura.uso_da_ia or {}, "recusado": None}
    except leitura_de_word.DocumentoRecusado as erro:
        saida = {"linhas": [[]], "duvidas": [], "avisos": [], "como_foi_lido": "recusado", "uso": {},
                 "recusado": str(erro)}
    return saida, time.time() - inicio


def main() -> None:
    """Roda os documentos escolhidos nos modos escolhidos e grava o resultado bruto com o resumo."""
    opcoes = ler_opcoes()
    # A prova, os conjuntos congelados e esta régua não podem ter mudado desde o congelamento (ADR-58; D39)
    exigir_prova_congelada()
    pasta_dos_documentos = pasta_do_conjunto(opcoes.conjunto)
    gabarito = json.loads((pasta_dos_documentos / "gabarito.json").read_text(encoding="utf-8"))
    saida_do_arquivo = opcoes.saida or str(PASTA_DOS_RESULTADOS / f"leitor_de_documentos_{opcoes.conjunto}.json")
    campos = carregar_layout()
    escolhidos = [nome for nome in opcoes.documentos.split(",") if nome]
    modos = [modo for modo in opcoes.modos.split(",") if modo in MODOS]
    print(f"Modo da IA: {config.MODO} · esforço: {opcoes.esforco} · modos: {modos}")
    resultados = []
    for documento in gabarito["documentos"]:
        nome = documento["arquivo"].removesuffix(".docx")
        if escolhidos and nome not in escolhidos:
            continue
        conteudo = (pasta_dos_documentos / documento["arquivo"]).read_bytes()
        modos_deste = ["regra"] if documento["nivel"] in NIVEIS_SEM_IA else modos
        for modo in modos_deste:
            saida, segundos = ler_um_documento(conteudo, campos, opcoes.esforco)
            medida = avaliacao_do_leitor.medir_documento(documento, saida["linhas"], saida["duvidas"], campos)
            medida["custo_usd"] = saida["uso"].get("custo_usd", 0) or 0
            medida["segundos"] = round(segundos, 1)
            medida["chamadas"] = saida["uso"].get("chamadas", 0)
            resultados.append({"documento": nome, "nivel": documento["nivel"], "modo": modo, "medida": medida,
                               "saida": saida})
            print(f"{nome} · {modo}: acerto {medida['campos_certos']}/{medida['campos_esperados']} · pessoas "
                  f"{medida['pessoas_encontradas']}/{medida['pessoas_esperadas']} (+{medida['pessoas_a_mais']}) · "
                  f"armadilhas {medida['armadilhas_respeitadas']}/{medida['armadilhas']} · perguntas "
                  f"{medida['perguntas_feitas']}/{medida['perguntas_esperadas']} · terceiros "
                  f"{medida['terceiros_vazados']} · US$ {medida['custo_usd']:.4f} · {segundos:.0f} s"
                  + (f" · RECUSADO: {saida['recusado'][:80]}" if saida["recusado"] else ""))
    # Resumo por modo e nível, e por modo no texto corrido (N3 a N5, os níveis em que a IA lê)
    resumo = {}
    for resultado in resultados:
        chave = f"{resultado['modo']}|{resultado['nivel']}"
        resumo.setdefault(chave, []).append(resultado["medida"])
    resumo_por_chave = {}
    for chave, medidas in resumo.items():
        resumo_por_chave[chave] = avaliacao_do_leitor.resumir(medidas)
    resumo_do_texto_corrido = {}
    for modo in modos:
        medidas = []
        for resultado in resultados:
            if resultado["modo"] == modo:
                medidas.append(resultado["medida"])
        if medidas:
            resumo_do_texto_corrido[modo] = avaliacao_do_leitor.resumir(medidas)
    saida_final = {"data": datetime.now().isoformat(timespec="seconds"), "commit": commit_atual(),
                   "conjunto": opcoes.conjunto, "prompt": leitor_de_documentos.VERSAO_PROMPT,
                   "modo_da_ia": config.MODO, "esforco": opcoes.esforco, "modelo_grande": config.MODELO_GRANDE,
                   "modelo_pequeno": config.MODELO_PEQUENO, "resumo_por_modo_e_nivel": resumo_por_chave,
                   "resumo_do_texto_corrido": resumo_do_texto_corrido, "documentos": resultados}
    Path(saida_do_arquivo).parent.mkdir(parents=True, exist_ok=True)
    Path(saida_do_arquivo).write_text(json.dumps(saida_final, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\nResumo por modo e nível:")
    for chave, total in sorted(resumo_por_chave.items()):
        print(f"  {chave}: acerto {total['acerto_por_campo']:.1%} (IC95% {total['intervalo_95'][0]:.1%}–"
              f"{total['intervalo_95'][1]:.1%}) · US$ {total.get('custo_usd', 0):.3f}")
    print(f"Gravado em {saida_do_arquivo}")


if __name__ == "__main__":
    main()
