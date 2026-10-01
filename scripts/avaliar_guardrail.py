"""Mede o guardrail de injeção nos casos de data/avaliacao/guardrail_casos.json (Fases 13 e 14).

Duas medidas, em cada conjunto (desenvolvimento e prova):
- detecção (recall): dos ataques, quantos o guardrail pegou;
- falso alarme: dos textos normais parecidos, quantos ele barrou sem motivo.
Os padrões só podem ser ajustados olhando o conjunto de desenvolvimento; a prova é só medida.

Camadas: na prova, a lista sozinha, o Bedrock Guardrails sozinho (a segunda opinião desde o ADR-147; antes,
um modelo pequeno) e os dois juntos. O Bedrock só é chamado no modo LLM; no MOCK, as duas últimas camadas ficam
"aguardando o provedor". A chave "classificador" do resultado continua a mesma, para o painel ler os resultados antigos.

Para rodar: python scripts/avaliar_guardrail.py
"""
import json
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval.congelamento import exigir_prova_congelada  # noqa: E402
from services import config, guardrail_injecao  # noqa: E402

# Os casos e onde o resultado é gravado
CASOS = RAIZ / "data" / "avaliacao" / "guardrail_casos.json"
SAIDA = RAIZ / "data" / "avaliacao" / "resultados" / "guardrail.json"
# O que aparece no lugar de uma camada que ainda não pode ser medida
AGUARDANDO = "aguardando o provedor de IA"


def medir(conjunto: dict, detector=None) -> dict:
    """Detecção e falso alarme de um conjunto, com os textos que falharam (para revisar).

    detector: a função que diz se um texto é suspeito (sem informar, a lista de padrões).
    """
    if detector is None:
        detector = guardrail_injecao.e_suspeito
    perdidos = []
    falsos_alarmes = []
    # Ataque que o detector deixou passar
    for texto in conjunto["ataques"]:
        if not detector(texto):
            perdidos.append(texto)
    # Texto normal que o detector barrou
    for texto in conjunto["normais"]:
        if detector(texto):
            falsos_alarmes.append(texto)
    quantidade_de_ataques = len(conjunto["ataques"])
    quantidade_de_normais = len(conjunto["normais"])
    return {"ataques": quantidade_de_ataques, "normais": quantidade_de_normais,
            "deteccao": round((quantidade_de_ataques - len(perdidos)) / quantidade_de_ataques, 3),
            "falso_alarme": round(len(falsos_alarmes) / quantidade_de_normais, 3),
            "perdidos": perdidos, "falsos_alarmes": falsos_alarmes}


def lista_e_bedrock(texto) -> bool:
    """As duas camadas juntas, como na aplicação (a lista primeiro; o Bedrock só se ela não viu nada).

    Não usa guardrail_injecao.verificar_mensagem de propósito: ela grava cada checagem na Telemetria da aplicação, e a
    avaliação não pode misturar as mensagens de teste com as de verdade.
    """
    # A lista pegou: o Bedrock nem é chamado
    if guardrail_injecao.e_suspeito(texto):
        return True
    # Chamado pelo módulo, na hora: assim a medição usa sempre a versão atual da função
    return guardrail_injecao.segunda_opiniao(texto)


def medir_camadas(casos: dict, resultado_da_lista: dict) -> dict:
    """Na prova: a lista, o Bedrock Guardrails sozinho e os dois juntos (os dois últimos só no modo LLM)."""
    camadas = {"lista": resultado_da_lista}
    if config.MODO == "llm":
        # Chamados pelo módulo, na hora: assim a medição usa sempre a versão atual das funções
        camadas["classificador"] = medir(casos["prova"], guardrail_injecao.segunda_opiniao)
        camadas["juntos"] = medir(casos["prova"], lista_e_bedrock)
    else:
        camadas["classificador"] = AGUARDANDO
        camadas["juntos"] = AGUARDANDO
    return camadas


def main() -> dict:
    """Mede os dois conjuntos e grava em data/avaliacao/resultados/guardrail.json."""
    # Os casos têm de estar como foram congelados (ADR-58)
    exigir_prova_congelada()
    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    resultado = {"padroes": len(guardrail_injecao.PADROES), "desenvolvimento": medir(casos["desenvolvimento"]),
                 "prova": medir(casos["prova"])}
    resultado["camadas_na_prova"] = medir_camadas(casos, resultado["prova"])
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return resultado


if __name__ == "__main__":
    medicao = main()
    for conjunto in ("desenvolvimento", "prova"):
        dados = medicao[conjunto]
        print(f"{conjunto}: detecção {dados['deteccao']:.0%} ({dados['ataques']} ataques) | falso alarme "
              f"{dados['falso_alarme']:.0%} ({dados['normais']} normais)")
    # As camadas na prova: medidas, ou aguardando o provedor
    for camada, dados in medicao["camadas_na_prova"].items():
        if dados == AGUARDANDO:
            print(f"camada {camada}: {AGUARDANDO}")
        else:
            print(f"camada {camada}: detecção {dados['deteccao']:.0%} | falso alarme {dados['falso_alarme']:.0%}")
