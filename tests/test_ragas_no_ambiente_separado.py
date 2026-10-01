"""O encaixe do nosso juiz e dos nossos embeddings nas métricas do próprio RAGAS 0.4 (Faithfulness e AnswerRelevancy).

Só roda no .venv-avaliacao, onde o RAGAS mora; no .venv do projeto (a bateria), o teste é pulado:
  .venv-avaliacao\\Scripts\\python.exe -m pytest tests/test_ragas_no_ambiente_separado.py
Sem gastar: a chamada ao Bedrock é falsa (responde pelo formato que o RAGAS pede), e os embeddings são vetores fixos.
"""
import asyncio
import json
import math

import pytest

# Sem o RAGAS (o .venv do projeto), o arquivo inteiro é pulado
pytest.importorskip("ragas")

from eval import ragas_do_endomarketing as ragas  # noqa: E402
from services.provedores_de_ia import RespostaDoProvedor  # noqa: E402

# A resposta do juiz falso para cada formato que o RAGAS pede (o "title" do esquema é o nome da classe)
RESPOSTAS_POR_FORMATO = {
    "StatementGeneratorOutput": {"statements": ["A conta salário não tem tarifa.", "O crédito tem juros zero."]},
    "NLIStatementOutput": {"statements": [
        {"statement": "A conta salário não tem tarifa.", "reason": "o trecho diz isso", "verdict": 1},
        {"statement": "O crédito tem juros zero.", "reason": "o trecho não fala de juros", "verdict": 0}]},
    "AnswerRelevanceOutput": {"question": "A conta salário tem tarifa?", "noncommittal": 0},
}


def chamar_falso(modelo: str, prompt: str, esquema_json: dict) -> RespostaDoProvedor:
    """A chamada falsa ao Bedrock: a resposta combinada para o formato pedido.

    Na tradução dos prompts (o _TranslatedStrings do RAGAS), devolve cada texto com "PT: " na frente, na mesma ordem.
    """
    if esquema_json["title"] == "_TranslatedStrings":
        textos = json.loads(prompt.split("Statements to translate:\n", 1)[1])
        traduzidos = []
        for texto in textos:
            traduzidos.append("PT: " + texto)
        resposta = {"statements": traduzidos}
    else:
        resposta = RESPOSTAS_POR_FORMATO[esquema_json["title"]]
    return RespostaDoProvedor(texto=json.dumps(resposta, ensure_ascii=False), tokens_entrada=500, tokens_saida=100)


class EmbeddingsFalsos(ragas.EmbeddingsDoProjeto):
    """Vetores fixos: o pedido é [1, 0]; cada pergunta do juiz, [0,6; 0,8] (a semelhança entre eles é 0,6)."""

    async def aembed_text(self, texto: str, **opcoes) -> list[float]:
        """O vetor do pedido."""
        return [1.0, 0.0]

    async def aembed_texts(self, textos: list[str], **opcoes) -> list[list[float]]:
        """O vetor de cada pergunta."""
        vetores = []
        for _ in textos:
            vetores.append([0.6, 0.8])
        return vetores


def _metricas(caixa: ragas.CaixaDoGasto) -> ragas.MetricasDoRagas:
    """As métricas do RAGAS com o juiz falso, os embeddings fixos e os prompts originais (em inglês)."""
    return ragas.MetricasDoRagas("mistral-large-3", caixa, ragas._prompts_originais(), EmbeddingsFalsos(),
                                 chamar=chamar_falso)


def test_fidelidade_pela_faithfulness_do_ragas():
    """A Faithfulness do RAGAS aceita o nosso juiz: 1 de 2 afirmações sustentadas → 0,5, com as afirmações."""
    caixa = ragas.CaixaDoGasto(1.0)
    medida = asyncio.run(_metricas(caixa).fidelidade("o pedido", "o texto", ["[P › A] Sem tarifa."]))
    assert medida["valor"] == 0.5 and len(medida["afirmacoes"]) == 2
    assert medida["afirmacoes"][1] == {"afirmacao": "O crédito tem juros zero.", "veredito": 0,
                                       "motivo": "o trecho não fala de juros"}
    # Duas chamadas: as afirmações e os vereditos
    assert caixa.chamadas == 2 and math.isclose(medida["custo_usd"], caixa.gasto_usd)


def test_vereditos_de_afirmacoes_prontas():
    """A 2ª conferência usa o prompt dos vereditos do RAGAS com as afirmações já prontas."""
    medida = asyncio.run(_metricas(ragas.CaixaDoGasto(1.0)).vereditos(["A", "B"], ["[P › A] x", "[P › B] y"]))
    assert [afirmacao["veredito"] for afirmacao in medida["afirmacoes"]] == [1, 0]


def test_relevancia_pela_answer_relevancy_do_ragas():
    """A AnswerRelevancy do RAGAS aceita o nosso juiz e os nossos embeddings: 3 perguntas, semelhança 0,6."""
    caixa = ragas.CaixaDoGasto(1.0)
    medida = asyncio.run(_metricas(caixa).relevancia("o pedido", "o texto"))
    assert math.isclose(medida["valor"], 0.6) and len(medida["perguntas"]) == 3 and not medida["evasivo"]
    assert caixa.chamadas == ragas.PERGUNTAS_DA_RELEVANCIA


def test_traducao_dos_prompts_pelo_ragas_e_leitura_do_arquivo(tmp_path):
    """Sem o arquivo, o RAGAS traduz (com o juiz) e grava; com o arquivo, só lê, sem chamar o juiz de novo."""
    caminho = tmp_path / "prompts.json"
    caixa = ragas.CaixaDoGasto(1.0)
    prompts = ragas.prompts_em_portugues(ragas.JuizDoBedrock("mistral-large-3", caixa, chamar_falso), caminho)
    chamadas_da_traducao = caixa.chamadas
    # Os exemplos e a instrução de cada um dos 3 prompts foram traduzidos
    assert chamadas_da_traducao == 6
    assert prompts["afirmacoes"].instruction.startswith("PT: ") and prompts["veredito"].language == "portuguese"
    assert prompts["perguntas"].examples[0][1].question.startswith("PT: ")
    # O prompt traduzido monta o texto que vai ao juiz
    assert "PT: " in prompts["veredito"].to_string(prompts["veredito"].input_model(context="c", statements=["s"]))
    # A 2ª vez só lê o arquivo
    de_novo = ragas.prompts_em_portugues(ragas.JuizDoBedrock("mistral-large-3", caixa, chamar_falso), caminho)
    assert caixa.chamadas == chamadas_da_traducao and de_novo["afirmacoes"].instruction == \
        prompts["afirmacoes"].instruction
