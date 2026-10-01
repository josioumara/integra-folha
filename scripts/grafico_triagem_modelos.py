"""Desenha o gráfico da triagem dos modelos de IA (ADR-11; docs/avaliacao.md, seção 12).

Lê data/avaliacao/modelos_candidatos.json e grava docs/imagens/triagem_modelos.svg. SVG é um desenho feito de
texto: abre no VS Code, no GitHub, no Obsidian, no navegador e no PowerPoint, e não precisa de biblioteca nova.

O gráfico tem um painel por provedor:
- eixo horizontal: quanto custaria testar o modelo nas 30 planilhas da comparação (escala logarítmica, porque os
  preços vão de centavos a dólares: cada marca vale 10 vezes a anterior, mais ou menos);
- eixo vertical: linha atual do provedor (em cima) ou geração anterior (embaixo);
- cor: verde = testar; vermelho = cortado por custo; cinza = cortado por ser de geração anterior.
Uma linha tracejada marca o limite de custo da regra de corte (US$ 4 / 20 por 1 milhão de tokens).

Para rodar: python scripts/grafico_triagem_modelos.py
"""
import json
import math
import os
from pathlib import Path

# Pasta raiz do projeto
RAIZ = Path(__file__).resolve().parent.parent
# O arquivo com os modelos candidatos e o desenho gerado
CAMINHO_DOS_CANDIDATOS = RAIZ / "data" / "avaliacao" / "modelos_candidatos.json"
CAMINHO_DO_GRAFICO = RAIZ / "docs" / "imagens" / "triagem_modelos.svg"

# Tamanho do desenho e de cada painel, em pixels
LARGURA = 1100
ALTURA_DO_PAINEL = 300
MARGEM_ESQUERDA = 150
MARGEM_DIREITA = 40
TOPO = 70
# O menor e o maior custo que o eixo mostra (em dólares, para as 30 planilhas)
CUSTO_MINIMO_DO_EIXO = 0.02
CUSTO_MAXIMO_DO_EIXO = 8.0
# As marcas do eixo horizontal (em dólares)
MARCAS_DO_EIXO = [0.03, 0.1, 0.3, 1.0, 3.0]
# O preço da regra de corte: acima disso, a linha atual é cortada por custo
PRECO_LIMITE_DE_ENTRADA = 4.0
PRECO_LIMITE_DE_SAIDA = 20.0
# Cor de cada motivo (verde = testar, vermelho = caro, cinza = antigo)
CORES = {"testar": "#1f9d55", "muito caro": "#d64545", "geração anterior": "#9aa0a6",
         "geração anterior e muito caro": "#6b7078"}


def carregar_candidatos() -> dict:
    """O arquivo da triagem: preços, tokens por chamada e a decisão de cada modelo."""
    return json.loads(CAMINHO_DOS_CANDIDATOS.read_text(encoding="utf-8"))


def custo_estimado(entrada: float, saida: float, tokens: dict, planilhas: int) -> float:
    """Quanto custaria interpretar as planilhas com esse preço (dólares). Ex.: US$ 2 / 10 em 30 planilhas ≈ 0,76."""
    # Custo de uma chamada: tokens × preço por milhão
    custo_de_uma_chamada = (tokens["entrada"] * entrada + tokens["saida"] * saida) / 1_000_000
    return custo_de_uma_chamada * planilhas


def posicao_horizontal(custo: float) -> float:
    """Onde o custo fica no eixo horizontal (pixels), em escala logarítmica."""
    # Na escala logarítmica, a distância é proporcional ao número de "vezes 10"
    inicio = math.log10(CUSTO_MINIMO_DO_EIXO)
    fim = math.log10(CUSTO_MAXIMO_DO_EIXO)
    fracao = (math.log10(custo) - inicio) / (fim - inicio)
    largura_util = LARGURA - MARGEM_ESQUERDA - MARGEM_DIREITA
    return MARGEM_ESQUERDA + fracao * largura_util


def cor_do_modelo(modelo: dict) -> str:
    """A cor do ponto: a da decisão (testar) ou a do motivo do corte."""
    if modelo["decisao"] == "testar":
        return CORES["testar"]
    return CORES[modelo["motivo"]]


def desenhar_painel(provedor: str, modelos: list[dict], topo: float, tokens: dict, planilhas: int) -> list[str]:
    """Os elementos SVG de um painel: título, as duas faixas, o eixo, a linha do limite e os pontos."""
    elementos = []
    meio = topo + ALTURA_DO_PAINEL / 2
    base = topo + ALTURA_DO_PAINEL
    # Título do painel
    elementos.append(f'<text x="{MARGEM_ESQUERDA}" y="{topo - 12}" font-size="16" font-weight="bold">{provedor}</text>')
    # As duas faixas: linha atual (em cima) e geração anterior (embaixo)
    elementos.append(f'<rect x="{MARGEM_ESQUERDA}" y="{topo}" width="{LARGURA - MARGEM_ESQUERDA - MARGEM_DIREITA}" '
                     f'height="{ALTURA_DO_PAINEL / 2}" fill="#f3f8f4"/>')
    elementos.append(f'<rect x="{MARGEM_ESQUERDA}" y="{meio}" width="{LARGURA - MARGEM_ESQUERDA - MARGEM_DIREITA}" '
                     f'height="{ALTURA_DO_PAINEL / 2}" fill="#f5f5f5"/>')
    elementos.append(f'<text x="{MARGEM_ESQUERDA - 10}" y="{topo + 40}" font-size="13" text-anchor="end">Linha atual</text>')
    elementos.append(f'<text x="{MARGEM_ESQUERDA - 10}" y="{meio + 40}" font-size="13" text-anchor="end">'
                     'Geração anterior</text>')
    # Marcas do eixo horizontal
    for marca in MARCAS_DO_EIXO:
        posicao = posicao_horizontal(marca)
        elementos.append(f'<line x1="{posicao:.1f}" y1="{topo}" x2="{posicao:.1f}" y2="{base}" stroke="#dddddd"/>')
        elementos.append(f'<text x="{posicao:.1f}" y="{base + 18}" font-size="12" text-anchor="middle">'
                         f'US$ {marca:g}</text>')
    # A linha do limite de custo da regra de corte
    limite = posicao_horizontal(custo_estimado(PRECO_LIMITE_DE_ENTRADA, PRECO_LIMITE_DE_SAIDA, tokens, planilhas))
    elementos.append(f'<line x1="{limite:.1f}" y1="{topo}" x2="{limite:.1f}" y2="{base}" stroke="#d64545" '
                     'stroke-dasharray="6,4"/>')
    elementos.append(f'<text x="{limite + 6:.1f}" y="{topo + 14}" font-size="11" fill="#d64545">limite de custo '
                     f'(US$ {PRECO_LIMITE_DE_ENTRADA:g} / {PRECO_LIMITE_DE_SAIDA:g})</text>')
    elementos.extend(_desenhar_pontos(modelos, topo, meio, tokens, planilhas))
    return elementos


def _desenhar_pontos(modelos: list[dict], topo: float, meio: float, tokens: dict, planilhas: int) -> list[str]:
    """Um ponto por preço, com os nomes ao lado; nomes vizinhos ficam em alturas diferentes para não se cobrirem."""
    elementos = []
    for faixa, altura_da_faixa in (("atual", topo), ("anterior", meio)):
        # Os modelos da faixa, juntos quando têm o mesmo preço, do mais barato para o mais caro
        da_faixa = []
        for modelo in modelos:
            if modelo["geracao"] == faixa:
                da_faixa.append(modelo)
        grupos = _agrupar_por_preco(da_faixa)
        for posicao_na_faixa, grupo in enumerate(grupos):
            primeiro = grupo[0]
            custo = custo_estimado(primeiro["entrada"], primeiro["saida"], tokens, planilhas)
            horizontal = posicao_horizontal(custo)
            # Quatro alturas possíveis dentro da faixa, alternando entre vizinhos
            vertical = altura_da_faixa + 30 + (posicao_na_faixa % 4) * 30
            rotulo = _rotulo_do_grupo(grupo)
            detalhe = (f'{rotulo}: US$ {primeiro["entrada"]:g} / {primeiro["saida"]:g} por 1M tokens; '
                       f'~US$ {custo:.2f} nas {planilhas} planilhas; {primeiro["decisao"]} ({primeiro["motivo"]})')
            elementos.append(f'<circle cx="{horizontal:.1f}" cy="{vertical:.1f}" r="7" fill="{cor_do_modelo(primeiro)}">'
                             f'<title>{detalhe}</title></circle>')
            elementos.append(f'<text x="{horizontal + 11:.1f}" y="{vertical + 4:.1f}" font-size="12">{rotulo}</text>')
    return elementos


def _agrupar_por_preco(modelos: list[dict]) -> list[list[dict]]:
    """Junta os modelos de mesmo preço e mesma decisão num grupo só (eles cairiam no mesmo ponto do gráfico).

    Devolve os grupos do mais barato para o mais caro. Ex.: os cinco Opus de US$ 5 / 25 viram um grupo.
    """
    grupos_por_chave = {}
    for modelo in modelos:
        chave = (modelo["saida"], modelo["entrada"], modelo["decisao"], modelo["motivo"])
        # Primeiro modelo com essa chave: abre o grupo
        if chave not in grupos_por_chave:
            grupos_por_chave[chave] = []
        grupos_por_chave[chave].append(modelo)
    # Do mais barato para o mais caro (a chave começa pelo preço de saída, que pesa mais no custo)
    chaves_em_ordem = sorted(grupos_por_chave)
    grupos = []
    for chave in chaves_em_ordem:
        grupos.append(grupos_por_chave[chave])
    return grupos


def _rotulo_do_grupo(grupo: list[dict]) -> str:
    """O nome do ponto: o modelo, ou vários com o começo comum escrito uma vez só.

    Ex.: claude-opus-5 e claude-opus-4-8 viram "claude-opus-5, 4-8".
    """
    nomes = []
    for modelo in grupo:
        nomes.append(modelo["modelo"])
    if len(nomes) == 1:
        return nomes[0]
    # O começo comum a todos os nomes, cortado no último hífen (ex.: "claude-opus-")
    comeco_comum = os.path.commonprefix(nomes)
    comeco_comum = comeco_comum[:comeco_comum.rfind("-") + 1]
    # Não cortar a versão pela metade: "claude-sonnet-4-" volta para "claude-sonnet-" (finais "4-6, 4-5")
    while comeco_comum.count("-") > 2:
        comeco_comum = comeco_comum[:comeco_comum[:-1].rfind("-") + 1]
    finais = []
    for nome in nomes[1:]:
        finais.append(nome[len(comeco_comum):])
    return ", ".join([nomes[0]] + finais)


def desenhar_legenda(topo: float) -> list[str]:
    """A legenda das cores e a nota sobre a estimativa."""
    elementos = []
    itens = [("testar", "Testar"), ("muito caro", "Cortado: muito caro"),
             ("geração anterior", "Cortado: geração anterior"),
             ("geração anterior e muito caro", "Cortado: geração anterior e muito caro")]
    horizontal = MARGEM_ESQUERDA
    for chave, texto in itens:
        elementos.append(f'<circle cx="{horizontal}" cy="{topo}" r="7" fill="{CORES[chave]}"/>')
        elementos.append(f'<text x="{horizontal + 12}" y="{topo + 4}" font-size="12">{texto}</text>')
        horizontal += 200
    return elementos


def montar_svg(dados: dict) -> str:
    """O desenho inteiro, em texto SVG."""
    tokens = dados["tokens_por_chamada"]
    planilhas = dados["planilhas_na_comparacao"]
    elementos = [f'<text x="{MARGEM_ESQUERDA}" y="30" font-size="20" font-weight="bold">Triagem dos modelos de IA: '
                 f'o que testar e o que cortar</text>',
                 f'<text x="{MARGEM_ESQUERDA}" y="50" font-size="12" fill="#555555">Custo estimado para interpretar '
                 f'as {planilhas} planilhas da comparação (preços de {dados["data_dos_precos"]}; modelos que pensam '
                 f'antes de responder podem custar mais)</text>']
    topo = TOPO + 20
    for provedor in ("OpenAI", "Anthropic"):
        # Os modelos do provedor
        do_provedor = []
        for modelo in dados["modelos"]:
            if modelo["provedor"] == provedor:
                do_provedor.append(modelo)
        elementos.extend(desenhar_painel(provedor, do_provedor, topo, tokens, planilhas))
        topo += ALTURA_DO_PAINEL + 70
    elementos.extend(desenhar_legenda(topo - 20))
    altura_total = topo + 20
    corpo = "\n  ".join(elementos)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA}" height="{altura_total:.0f}" '
            f'viewBox="0 0 {LARGURA} {altura_total:.0f}" font-family="Segoe UI, Arial, sans-serif">\n'
            f'  <rect width="100%" height="100%" fill="#ffffff"/>\n  {corpo}\n</svg>\n')


def main() -> Path:
    """Gera o SVG e devolve onde ele foi gravado."""
    CAMINHO_DO_GRAFICO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_DO_GRAFICO.write_text(montar_svg(carregar_candidatos()), encoding="utf-8", newline="\n")
    return CAMINHO_DO_GRAFICO


if __name__ == "__main__":
    print(f"Gráfico gravado em {main()}")
