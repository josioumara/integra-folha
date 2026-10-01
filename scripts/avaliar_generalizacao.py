"""Prova de generalização (EXP-017): a leitura com IA real acerta tanto nos arquivos novos quanto nos antigos?

Para que serve: as correções dos ADR-126 a 131 foram feitas olhando os 10 arquivos em que o QA da jornada achou
os problemas.
Se alguma delas tivesse "decorado" esses casos, o acerto cairia nos 60 arquivos do lote guardado, que ninguém tinha
visto. Este script lê o que o QA da jornada coletou na medição de generalização (sem chamar a IA de novo: custo
zero) e
compara os dois grupos, no total e por tipo de arquivo (estrato).

Analogia: é conferir se o aluno aprendeu a matéria ou decorou a prova. Se ele erra só num tipo de questão que nunca
caiu nos exercícios, não é decoreba: é matéria que faltou estudar.

Como mede:
- "exato" = a lista saiu com uma linha por pessoa e todas as pessoas certas (a régua do relatório do QA);
- o intervalo de confiança de cada taxa é o de Wilson 95% (bom para amostras pequenas e taxas perto de 0% ou 100%);
- a diferença entre os grupos usa o teste exato de Fisher, bilateral (conta as tabelas possíveis, sem aproximação).

Os dados de entrada ficam fora do repositório (D:\\AI_Payroll_Hub\\QA_Jornada), e o resultado bruto guarda só
contagens por arquivo (nenhum nome, CPF ou valor de pessoa).

Uso (medir e registrar são dois passos, ADR-66):
  python scripts/avaliar_generalizacao.py medir
  python scripts/avaliar_generalizacao.py registrar
"""
import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.historico_de_experimentos import registrar  # noqa: E402
from scripts import gerar_historico_de_experimentos  # noqa: E402

# Onde o QA da jornada gravou a medição com IA real (um arquivo por linha: o que a leitura entregou)
RESULTADOS_DO_QA = Path(r"D:\AI_Payroll_Hub\QA_Jornada\Rodada_Generalizacao\llm_r1\resultados.jsonl")
# Onde fica o resultado bruto desta análise
CAMINHO_DO_RESULTADO = RAIZ / "data" / "avaliacao" / "resultados" / "generalizacao_d39.json"
# As extensões de arquivo em forma de tabela (o resto é texto corrido: .txt e .docx)
EXTENSOES_DE_TABELA = ("csv", "xlsx", "xls", "ods")
# Os estratos, na ordem em que aparecem no relatório
ESTRATOS = ("tabela", "texto_baixo_medio", "texto_alto")
# Os estratos que os arquivos antigos cobriam (a comparação justa é só neles)
ESTRATOS_COBERTOS_PELOS_ANTIGOS = ("tabela", "texto_baixo_medio")
# O valor da normal padrão para 95% de confiança
Z_95 = 1.96


def intervalo_de_wilson(acertos: int, total: int) -> tuple[float, float]:
    """O intervalo de confiança de Wilson 95% da taxa acertos/total.

    Recebe: os acertos e o total. Devolve: (limite de baixo, limite de cima), entre 0 e 1.
    Ex.: (10, 10) → (0,72; 1,00); (0, 7) → (0,00; 0,35).
    """
    # Sem nenhum caso, não há taxa
    if total == 0:
        return (0.0, 0.0)
    # A taxa observada
    taxa = acertos / total
    # O ajuste de Wilson: puxa o centro para 50% quando a amostra é pequena
    denominador = 1 + Z_95 * Z_95 / total
    centro = (taxa + Z_95 * Z_95 / (2 * total)) / denominador
    meia_largura = Z_95 * math.sqrt(taxa * (1 - taxa) / total + Z_95 * Z_95 / (4 * total * total)) / denominador
    # O intervalo, sem passar de 0 nem de 1
    return (max(0.0, centro - meia_largura), min(1.0, centro + meia_largura))


def teste_exato_de_fisher(exatos_1: int, total_1: int, exatos_2: int, total_2: int) -> float:
    """O valor p bilateral do teste exato de Fisher para duas taxas (exatos_1/total_1 × exatos_2/total_2).

    Recebe: os exatos e o total de cada grupo. Devolve: o valor p (a chance de uma diferença tão grande ou maior só
    por acaso, se os dois grupos fossem iguais). Ex.: (10, 10, 18, 26) → 0,076.
    """
    # As margens da tabela 2x2: quantos no grupo 1, quantos exatos no total e o total geral
    total_geral = total_1 + total_2
    exatos_no_total = exatos_1 + exatos_2
    # O denominador da probabilidade hipergeométrica (todas as formas de escolher o grupo 1)
    formas_de_escolher = math.comb(total_geral, total_1)
    # A probabilidade de o grupo 1 ter "exatos" acertos, com as margens fixas
    probabilidade_observada = (math.comb(exatos_no_total, exatos_1)
                               * math.comb(total_geral - exatos_no_total, total_1 - exatos_1) / formas_de_escolher)
    # Os valores possíveis de exatos no grupo 1
    menor_possivel = max(0, total_1 - (total_geral - exatos_no_total))
    maior_possivel = min(total_1, exatos_no_total)
    valor_p = 0.0
    for exatos_possiveis in range(menor_possivel, maior_possivel + 1):
        # A probabilidade desta tabela
        probabilidade = (math.comb(exatos_no_total, exatos_possiveis)
                         * math.comb(total_geral - exatos_no_total, total_1 - exatos_possiveis) / formas_de_escolher)
        # Soma as tabelas tão ou menos prováveis que a observada (a folga evita erro de arredondamento)
        if probabilidade <= probabilidade_observada * (1 + 1e-9):
            valor_p += probabilidade
    # Nunca passa de 1
    return min(1.0, valor_p)


def estrato_do_arquivo(arquivo: str) -> str:
    """O tipo do arquivo: "tabela", "texto_baixo_medio" ou "texto_alto".

    Ex.: "por_nivel/alto/007.csv" → "tabela"; "lote_guardado/por_nivel/altissimo/016.txt" → "texto_alto".
    """
    # A extensão, sem o ponto
    extensao = arquivo.rsplit(".", 1)[-1].lower()
    # Tabela, em qualquer nível
    if extensao in EXTENSOES_DE_TABELA:
        return "tabela"
    # Texto corrido de nível alto ou altíssimo
    if "/alto/" in arquivo or "/altissimo/" in arquivo:
        return "texto_alto"
    # Texto corrido de nível baixo ou médio (e os da suíte)
    return "texto_baixo_medio"


def arquivo_exato(resultado: dict) -> bool:
    """True se a lista saiu com uma linha por pessoa e todas as pessoas certas."""
    # Tantas linhas quantas pessoas esperadas
    uma_linha_por_pessoa = resultado["linhas_na_lista"] == resultado["pessoas_esperadas"]
    # E todas as pessoas certas
    todas_certas = resultado["pessoas_certas"] == resultado["pessoas_esperadas"]
    return uma_linha_por_pessoa and todas_certas


def ler_resultados_do_qa() -> list[dict]:
    """Os resultados por arquivo da medição com IA real, só com as contagens (sem dado de pessoa).

    Devolve: [{"conjunto", "arquivo", "estrato", "linhas_na_lista", "pessoas_esperadas", "pessoas_certas",
    "linhas_a_mais", "exato", "custo_usd"}].
    """
    arquivos = []
    for linha in RESULTADOS_DO_QA.read_text(encoding="utf-8").splitlines():
        # Linhas vazias no fim do arquivo não contam
        if not linha.strip():
            continue
        resultado = json.loads(linha)
        # As linhas a mais: o que sobrou na lista além das pessoas certas
        linhas_a_mais = max(0, resultado["linhas_na_lista"] - resultado["pessoas_certas"])
        arquivos.append({"conjunto": resultado["conjunto"], "arquivo": resultado["arquivo"],
                         "estrato": estrato_do_arquivo(resultado["arquivo"]),
                         "linhas_na_lista": resultado["linhas_na_lista"],
                         "pessoas_esperadas": resultado["pessoas_esperadas"],
                         "pessoas_certas": resultado["pessoas_certas"], "linhas_a_mais": linhas_a_mais,
                         # Custo que o QA não mediu fica None ("não medido"), nunca um zero inventado (ADR-36)
                         "exato": arquivo_exato(resultado), "custo_usd": resultado.get("gasto_usd")})
    return arquivos


def taxa_ou_nada(parte: int, total: int) -> float | None:
    """A taxa parte/total com 4 casas; None se não há total. Ex.: (18, 26) → 0.6923; (0, 0) → None."""
    if total == 0:
        return None
    return round(parte / total, 4)


def intervalo_arredondado(acertos: int, total: int) -> list[float]:
    """O intervalo de Wilson com 4 casas, como lista (para o JSON). Ex.: (10, 10) → [0.7225, 1.0]."""
    baixo, alto = intervalo_de_wilson(acertos, total)
    return [round(baixo, 4), round(alto, 4)]


def somar_medido(soma: float | None, valor: float | None) -> float | None:
    """Soma dois custos em que None quer dizer "não medido". Ex.: (None, 0.05) → 0.05; (0.1, None) → 0.1."""
    if valor is None:
        return soma
    if soma is None:
        return valor
    return soma + valor


def resumir(arquivos: list[dict]) -> dict:
    """As somas de um grupo de arquivos, com as taxas e os intervalos de Wilson.

    Devolve: {"arquivos", "exatos", "taxa_de_exatos", "ic95_exatos", "pessoas_certas", "pessoas_esperadas",
    "taxa_de_pessoas", "ic95_pessoas", "linhas_a_mais", "custo_usd"}.
    """
    # As somas do grupo
    exatos = 0
    pessoas_certas = 0
    pessoas_esperadas = 0
    linhas_a_mais = 0
    # O custo começa "não medido" e só vira número quando algum arquivo tem custo medido
    custo = None
    for arquivo in arquivos:
        # Conta o arquivo exato
        if arquivo["exato"]:
            exatos += 1
        pessoas_certas += arquivo["pessoas_certas"]
        pessoas_esperadas += arquivo["pessoas_esperadas"]
        linhas_a_mais += arquivo["linhas_a_mais"]
        custo = somar_medido(custo, arquivo["custo_usd"])
    # O custo com 4 casas, quando medido
    if custo is not None:
        custo = round(custo, 4)
    # As taxas, com os intervalos
    total = len(arquivos)
    return {"arquivos": total, "exatos": exatos, "taxa_de_exatos": taxa_ou_nada(exatos, total),
            "ic95_exatos": intervalo_arredondado(exatos, total),
            "pessoas_certas": pessoas_certas, "pessoas_esperadas": pessoas_esperadas,
            "taxa_de_pessoas": taxa_ou_nada(pessoas_certas, pessoas_esperadas),
            "ic95_pessoas": intervalo_arredondado(pessoas_certas, pessoas_esperadas),
            "linhas_a_mais": linhas_a_mais, "custo_usd": custo}


def filtrar(arquivos: list[dict], conjunto: str, estratos: tuple[str, ...] | None = None) -> list[dict]:
    """Os arquivos de um conjunto ("antigos" ou "lote"), só dos estratos pedidos (None = todos)."""
    escolhidos = []
    for arquivo in arquivos:
        # Só o conjunto pedido
        if arquivo["conjunto"] != conjunto:
            continue
        # Só os estratos pedidos
        if estratos is not None and arquivo["estrato"] not in estratos:
            continue
        escolhidos.append(arquivo)
    return escolhidos


def comparar(arquivos: list[dict], estratos: tuple[str, ...] | None) -> dict:
    """Antigos × lote nos estratos pedidos: o resumo de cada um e o valor p de Fisher nos exatos."""
    # Os dois grupos, nos mesmos estratos
    antigos = resumir(filtrar(arquivos, "antigos", estratos))
    lote = resumir(filtrar(arquivos, "lote", estratos))
    # A diferença nos arquivos exatos
    valor_p = teste_exato_de_fisher(antigos["exatos"], antigos["arquivos"], lote["exatos"], lote["arquivos"])
    return {"antigos": antigos, "lote": lote, "fisher_p_exatos": round(valor_p, 4)}


def medir() -> None:
    """Lê os resultados do QA, compara os grupos (total, estratos cobertos e cada estrato) e grava o resultado bruto."""
    arquivos = ler_resultados_do_qa()
    # As três comparações: tudo, só o que os antigos cobriam, e cada estrato
    resultado = {"data": date.today().isoformat(), "fonte": str(RESULTADOS_DO_QA),
                 "total": comparar(arquivos, None),
                 "estratos_cobertos_pelos_antigos": comparar(arquivos, ESTRATOS_COBERTOS_PELOS_ANTIGOS),
                 "por_estrato": {}, "arquivos": arquivos}
    for estrato in ESTRATOS:
        resultado["por_estrato"][estrato] = comparar(arquivos, (estrato,))
    CAMINHO_DO_RESULTADO.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    # O resumo na tela
    for rotulo in ("total", "estratos_cobertos_pelos_antigos"):
        comparacao = resultado[rotulo]
        print(f"{rotulo}: antigos {comparacao['antigos']['exatos']}/{comparacao['antigos']['arquivos']} × lote "
              f"{comparacao['lote']['exatos']}/{comparacao['lote']['arquivos']} (Fisher p = "
              f"{comparacao['fisher_p_exatos']:.3f})")
    for estrato, comparacao in resultado["por_estrato"].items():
        lote = comparacao["lote"]
        print(f"  {estrato}: lote {lote['exatos']}/{lote['arquivos']} exatos (IC95 {lote['ic95_exatos'][0]:.0%}–"
              f"{lote['ic95_exatos'][1]:.0%}), pessoas {lote['pessoas_certas']}/{lote['pessoas_esperadas']}, "
              f"linhas a mais {lote['linhas_a_mais']}")
    print(f"Gravado em {CAMINHO_DO_RESULTADO.relative_to(RAIZ)}")


def texto_da_taxa(resumo: dict) -> str:
    """A taxa em texto para o registro. Ex.: "18/26 (69%; IC95 50–83%)"; grupo vazio → "nenhum arquivo"."""
    # Um estrato sem arquivos neste grupo (ex.: os antigos não tinham texto corrido alto) não tem taxa
    if resumo["arquivos"] == 0:
        return "nenhum arquivo"
    baixo, alto = resumo["ic95_exatos"]
    return (f"{resumo['exatos']}/{resumo['arquivos']} ({resumo['taxa_de_exatos']:.0%}; IC95 {baixo:.0%}–"
            f"{alto:.0%})")


def registrar_experimento() -> None:
    """Registra a análise como o próximo EXP do histórico (depois de ler os números) e regera docs/experimentos.md."""
    resultado = json.loads(CAMINHO_DO_RESULTADO.read_text(encoding="utf-8"))
    # Um resultado por comparação, no formato do histórico
    resultados = []
    comparacoes = [("Total", resultado["total"]),
                   ("Estratos que os antigos cobriam (tabela e texto baixo/médio)",
                    resultado["estratos_cobertos_pelos_antigos"])]
    for estrato, comparacao in resultado["por_estrato"].items():
        comparacoes.append((f"Estrato {estrato}", comparacao))
    for nome, comparacao in comparacoes:
        resultados.append({"nome": nome, "modelo": "claude-sonnet-4-6 (Leitor) + nova-2-lite",
                           "metricas": {"antigos": texto_da_taxa(comparacao["antigos"]),
                                        "lote": texto_da_taxa(comparacao["lote"]),
                                        "fisher_p_exatos": comparacao["fisher_p_exatos"],
                                        "pessoas_lote": f"{comparacao['lote']['pessoas_certas']}/"
                                                        f"{comparacao['lote']['pessoas_esperadas']}",
                                        "linhas_a_mais_lote": comparacao["lote"]["linhas_a_mais"]}})
    total = resultado["total"]
    cobertos = resultado["estratos_cobertos_pelos_antigos"]
    texto_alto = resultado["por_estrato"]["texto_alto"]["lote"]
    experimento = {
        "titulo": "Prova de generalização: a leitura nos arquivos antigos × no lote guardado",
        "tipo": "generalizacao",
        "pergunta": ("As correções dos ADR-126 a 131, feitas olhando os 10 arquivos em que o QA achou os problemas, "
                     "valem para arquivos que ninguém viu, ou alguma delas decorou os casos?"),
        "o_que_testamos": ("A leitura com IA real (Sonnet 4.6 e Nova 2 Lite, plano B), medida pelo QA da jornada "
                           "na medição de generalização: os 10 arquivos antigos e 26 dos 60 do lote guardado "
                           "(um a cada "
                           "dois), com o mesmo roteiro. 'Exato' = uma linha por pessoa, todas certas. Comparação por "
                           "estrato (tabela; texto corrido baixo/médio; texto corrido alto/altíssimo), com o "
                           "intervalo de Wilson e o teste exato de Fisher. Busca de rastro: nomes, CPFs e nomes de "
                           "arquivo dos antigos nos prompts, no código e nas bases do RAG."),
        "amostra": f"36 arquivos ({total['antigos']['arquivos']} antigos + {total['lote']['arquivos']} do lote)",
        "modo": "IA real (dados já coletados pelo QA; esta análise não chamou a IA)",
        "resultados": resultados,
        "leitura": (f"No total, antigos {texto_da_taxa(total['antigos'])} × lote {texto_da_taxa(total['lote'])} "
                    f"(Fisher p = {total['fisher_p_exatos']:.3f}). Nos tipos que os antigos cobriam, não há queda: "
                    f"{texto_da_taxa(cobertos['antigos'])} × {texto_da_taxa(cobertos['lote'])} "
                    f"(p = {cobertos['fisher_p_exatos']:.2f}). A queda está toda no texto corrido alto e altíssimo, "
                    f"que os antigos não tinham: {texto_da_taxa(texto_alto)}, com as pessoas achadas "
                    f"({texto_alto['pessoas_certas']}/{texto_alto['pessoas_esperadas']}) mas "
                    f"{texto_alto['linhas_a_mais']} linhas a mais. Não é decoreba: o Leitor de texto corrido parte de "
                    "'um bloco = uma pessoa' e não junta pedaços; em texto difícil, cada pessoa vem em seções "
                    "(identidade, contrato, endereço), e cada seção vira uma linha (o mesmo CPF duas vezes, o nome "
                    "curto ao lado do inteiro, contrato ou endereço sem nome nem CPF). Rastro: só 1 CPF do QA, num "
                    "comentário de services/conferencia_do_valor.py (sem efeito no comportamento; a trocar)."),
        "decisao": ("A correção da leitura: um passo de junção depois da leitura dos blocos (mesmo CPF; nome curto "
                    "no completo sem conflito; trecho sem nome nem CPF nunca vira pessoa), medido num conjunto "
                    "sintético NOVO do estrato, congelado antes da correção (o lote já foi visto e deixa de servir "
                    "de prova)."),
        "custo_usd": 0.0,
        "fonte": str(CAMINHO_DO_RESULTADO.relative_to(RAIZ)).replace("\\", "/"),
    }
    caminho = registrar(experimento)
    print(f"Registrado em {caminho.relative_to(RAIZ)}")
    # O documento do histórico é gerado a partir dos registros
    gerar_historico_de_experimentos.main()


def main() -> None:
    """Escolhe o passo: medir (grava o resultado bruto) ou registrar (grava o EXP depois de ler os números)."""
    leitor = argparse.ArgumentParser(description="Prova de generalização (EXP-017): antigos × lote guardado.")
    leitor.add_argument("passo", choices=("medir", "registrar"))
    opcoes = leitor.parse_args()
    if opcoes.passo == "medir":
        medir()
    else:
        registrar_experimento()


if __name__ == "__main__":
    main()
