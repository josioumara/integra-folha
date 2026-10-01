"""Mede os dois índices do RAG com as 10 consultas de teste de cada um (ADR-09, ADR-10).

- hit@k: das perguntas com resposta, em quantas o trecho certo aparece entre os k primeiros.
  O k de cada índice é o menor que alcança o melhor hit@k.
- Distâncias: a do trecho certo nas perguntas com resposta e a do mais parecido nas perguntas SEM
  resposta. O limite de "sem evidência" precisa ficar entre as duas.
- Isolamento: na consulta que pede dado de outra empresa, nenhum trecho dela pode voltar.

Para rodar: python scripts/avaliar_rag.py   (antes: python scripts/build_index.py)
"""
import json
import sys
from datetime import date
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.congelamento import exigir_prova_congelada  # noqa: E402
from rag.busca import buscar_beneficios, search_rules  # noqa: E402

# As consultas de teste e onde o resultado é gravado
CONSULTAS = RAIZ / "data" / "avaliacao" / "consultas_rag.json"
SAIDA = RAIZ / "data" / "avaliacao" / "resultados" / "rag.json"
# Até quantos trechos a medição olha
K_MAXIMO = 5


def acertou(consulta: dict, trecho: dict) -> bool:
    """True se o trecho é a resposta certa da consulta (o campo esperado ou a fonte esperada)."""
    if "campo" in consulta:
        return trecho["campo"] == consulta["campo"]
    return consulta["fonte_contem"] in trecho["fonte"]


def medir(consultas: list[dict], buscar) -> dict:
    """Mede um índice. `buscar(consulta, k)` é a função de busca daquele índice."""
    posicoes = []                  # em que posição veio o trecho certo, em cada pergunta com resposta
    distancias_certas = []         # a distância do trecho certo
    distancias_sem_resposta = []   # a distância do trecho mais parecido, nas perguntas sem resposta
    vazamentos = 0                 # trechos de outra empresa que voltaram (tem de ser zero)
    for consulta in consultas:
        # Sem limite de distância: mede tudo
        trechos = buscar(consulta, K_MAXIMO)
        if consulta["tipo"] == "conhecida":
            # A posição do primeiro trecho certo (1 = primeiro); None se não veio
            posicao_do_certo = None
            for posicao, trecho in enumerate(trechos, start=1):
                if acertou(consulta, trecho):
                    posicao_do_certo = posicao
                    break
            posicoes.append(posicao_do_certo)
            if posicao_do_certo:
                distancias_certas.append(trechos[posicao_do_certo - 1]["distancia"])
        elif consulta["tipo"] == "sem_resposta":
            distancias_sem_resposta.append(trechos[0]["distancia"])
        elif consulta["tipo"] == "outra_empresa":
            for trecho in trechos:
                if trecho["empresa_id"] == consulta["empresa_alheia"]:
                    vazamentos += 1
    # hit@k para k de 1 a 5: a fração de perguntas com o trecho certo entre os k primeiros
    quantidade = len(posicoes)
    acerto_por_k = {}
    for k in range(1, K_MAXIMO + 1):
        acertos = 0
        for posicao in posicoes:
            if posicao and posicao <= k:
                acertos += 1
        acerto_por_k[k] = acertos / quantidade
    # O k escolhido é o menor que alcança o melhor acerto
    melhor_acerto = max(acerto_por_k.values())
    k_escolhido = None
    for k, acerto in acerto_por_k.items():
        if acerto == melhor_acerto:
            k_escolhido = k
            break
    return {"consultas_com_resposta": quantidade, "hit_at_k": acerto_por_k, "k_escolhido": k_escolhido,
            "maior_distancia_certa": max(distancias_certas),
            "menor_distancia_sem_resposta": min(distancias_sem_resposta),
            "trechos_de_outra_empresa": vazamentos}


def main() -> dict:
    """Mede os dois índices e grava o resultado em data/avaliacao/resultados/rag.json."""
    # As consultas têm de estar como foram congeladas (ADR-58)
    exigir_prova_congelada()
    dados = json.loads(CONSULTAS.read_text(encoding="utf-8"))
    # A data usada para a vigência do catálogo (fixa, para o teste dar sempre o mesmo resultado)
    dia = date.fromisoformat(dados["dia"])

    def buscar_no_layout(consulta, k):
        """Busca no índice do layout, sem limite de distância."""
        return search_rules(consulta["pergunta"], k=k, distancia_maxima=2)

    def buscar_no_catalogo(consulta, k):
        """Busca no catálogo da empresa da consulta, sem limite de distância."""
        return buscar_beneficios(consulta["empresa_id"], consulta["pergunta"], dia=dia, k=k, distancia_maxima=2)

    resultado = {"layout": medir(dados["layout"], buscar_no_layout),
                 "catalogo": medir(dados["catalogo"], buscar_no_catalogo)}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return resultado


if __name__ == "__main__":
    for indice, medicao in main().items():
        # Ex.: "@1=62% @2=88% ..."
        partes = []
        for k, acerto in medicao["hit_at_k"].items():
            partes.append(f"@{k}={acerto:.0%}")
        print(f"{indice}: hit {' '.join(partes)} | k escolhido {medicao['k_escolhido']} | distância: certa até "
              f"{medicao['maior_distancia_certa']}, sem resposta a partir de {medicao['menor_distancia_sem_resposta']} | "
              f"trechos de outra empresa: {medicao['trechos_de_outra_empresa']}")
