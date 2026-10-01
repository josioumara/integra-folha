"""Testes da comparação de modelos (ADR-65), sem rede e sem gastar nada.

O provedor é trocado por um "provedor de mentira" que responde com o simulador do Interpretador e informa
5.000 tokens de entrada e 1.500 de saída por chamada. Provam que:
- a amostra é sempre a mesma (semente fixa) e bate com a gravada;
- a planilha da prova vira só nomes de coluna, sem dados;
- os 5 modelos selecionados rodam nas 30 planilhas, com custo pela tabela de preços, e o B0 entra como régua;
- o teto de gasto corta a comparação (modelo parcial e modelos não medidos);
- provedor que falha seguidamente deixa o modelo "indisponível", sem pontuar resposta simulada;
- sem chave, nada é chamado; rodar de novo não cobra de novo os modelos completos.
"""
import json

import pytest

from agents import interpretador
from eval import comparacao_de_modelos as comparacao
from services import config, provedores_de_ia
from services.llm_client import LLMClient
from tests.test_fluxo_empresa import busca_falsa


class ProvedorDeMentira:
    """Faz o papel dos provedores: responde com o simulador e conta as chamadas; pode falhar para um modelo."""

    def __init__(self, modelo_que_falha: str | None = None):
        """modelo_que_falha: se informado, toda chamada a esse modelo quebra (como um modelo fora da conta)."""
        self.modelo_que_falha = modelo_que_falha
        self.chamadas_por_modelo = {}

    def chamar(self, modelo, sistema, pedido, temperatura, esforco=None, esquema_json=None):
        """Uma chamada: conta, falha se for o modelo marcado ou responde com o simulador."""
        self.chamadas_por_modelo[modelo] = self.chamadas_por_modelo.get(modelo, 0) + 1
        if modelo == self.modelo_que_falha:
            raise RuntimeError("model not found")
        return provedores_de_ia.RespostaDoProvedor(texto=interpretador.simular_llm(pedido), tokens_entrada=5000,
                                                   tokens_saida=1500)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Chaves de mentira (os testes nunca têm as reais) e o resultado gravado numa pasta temporária."""
    monkeypatch.setattr(config, "CHAVE_OPENAI", "chave-de-teste")
    monkeypatch.setattr(config, "CHAVE_ANTHROPIC", "chave-de-teste")
    monkeypatch.setattr(comparacao, "CAMINHO_DO_RESULTADO", tmp_path / "comparacao_modelos.json")
    # A medição roda com o MOCK de reserva (ADR-145), como na máquina local: a falha do provedor vira a resposta
    # simulada, que o medidor congelado recusa e conta como falha (sem ela, a primeira falha pararia a comparação)
    monkeypatch.setattr(config, "MOCK_DE_RESERVA", True)
    return tmp_path


def _trocar_provedor(monkeypatch, provedor: ProvedorDeMentira) -> None:
    """Põe o provedor de mentira no lugar dos provedores de verdade."""
    monkeypatch.setattr(provedores_de_ia, "chamar", provedor.chamar)


def test_amostra_e_sempre_a_mesma_e_bate_com_a_gravada():
    """O sorteio com semente fixa dá as mesmas 30 planilhas que estão gravadas (e congeladas)."""
    prova = comparacao.carregar_prova()
    assert comparacao.sortear_amostra(prova) == comparacao.carregar_amostra()
    assert len(comparacao.carregar_amostra()) == comparacao.TAMANHO_DA_AMOSTRA


def test_planilha_da_prova_vira_so_nomes_de_coluna():
    """O perfil tem os cabeçalhos da planilha e nenhuma amostra de dados (a mesma informação do B0)."""
    planilha = comparacao.carregar_prova()[comparacao.carregar_amostra()[0]]
    perfil = comparacao.perfil_da_planilha(planilha)
    nomes = []
    for coluna in perfil.colunas:
        nomes.append(coluna.nome)
        assert coluna.amostras == []
    assert nomes == planilha["cabecalhos"]


def test_os_cinco_modelos_rodam_com_custo_da_tabela(ambiente, monkeypatch):
    """Todos completos nas 30 planilhas; o custo é tokens × preço; o B0 entra; o resultado é gravado."""
    provedor = ProvedorDeMentira()
    _trocar_provedor(monkeypatch, provedor)
    resultado = comparacao.comparar(25.0, busca=busca_falsa)
    assert len(resultado["modelos"]) == 5
    for nome_do_modelo, medida in resultado["modelos"].items():
        assert medida["situacao"] == "completo"
        assert medida["planilhas_pontuadas"] == 30
        # Uma chamada por planilha: 30 × (5.000 × entrada + 1.500 × saída) / 1 milhão
        entrada, saida = provedores_de_ia.carregar_precos()[nome_do_modelo]
        assert medida["custo_usd"] == pytest.approx(30 * (5000 * entrada + 1500 * saida) / 1_000_000, abs=1e-3)
        assert 0.0 <= medida["acuracia_por_campo"] <= 1.0
    assert resultado["b0"]["planilhas_pontuadas"] == 30
    assert json.loads(ambiente.joinpath("comparacao_modelos.json").read_text(encoding="utf-8"))["modelos"]


def test_teto_de_gasto_corta_a_comparacao(ambiente, monkeypatch):
    """Com teto de US$ 0,50: os baratos completam, um fica parcial e os caros nem começam."""
    _trocar_provedor(monkeypatch, ProvedorDeMentira())
    resultado = comparacao.comparar(0.50, busca=busca_falsa)
    situacoes = []
    for medida in resultado["modelos"].values():
        situacoes.append(medida["situacao"])
    assert "completo" in situacoes
    assert "parcial: teto de gasto atingido" in situacoes
    assert "não medido: teto de gasto atingido" in situacoes
    # O gasto passa do teto no máximo pelo custo de uma planilha do modelo mais caro testado (Opus: US$ 0,05)
    assert resultado["gasto_acumulado_usd"] <= 0.50 + 0.05


def test_provedor_que_falha_deixa_o_modelo_indisponivel_sem_pontuar_mock(ambiente, monkeypatch):
    """Toda chamada ao Sonnet quebra: ele fica "indisponível" sem nenhuma planilha pontuada; os outros completam."""
    provedor = ProvedorDeMentira(modelo_que_falha="claude-sonnet-5")
    _trocar_provedor(monkeypatch, provedor)
    resultado = comparacao.comparar(25.0, busca=busca_falsa)
    sonnet = resultado["modelos"]["claude-sonnet-5"]
    assert sonnet["situacao"] == "indisponível: o provedor falhou seguidamente"
    assert sonnet["planilhas_pontuadas"] == 0 and "acuracia_por_campo" not in sonnet
    assert len(sonnet["falhas_do_provedor"]) == comparacao.LIMITE_DE_FALHAS_SEGUIDAS
    assert resultado["modelos"]["gpt-6-sol"]["situacao"] == "completo"


def test_sem_chave_nada_e_chamado(ambiente, monkeypatch):
    """Faltando a chave da Anthropic, a comparação para antes da primeira chamada."""
    provedor = ProvedorDeMentira()
    _trocar_provedor(monkeypatch, provedor)
    monkeypatch.setattr(config, "CHAVE_ANTHROPIC", "")
    with pytest.raises(provedores_de_ia.ConfiguracaoDoProvedor, match="ANTHROPIC_API_KEY"):
        comparacao.comparar(25.0, busca=busca_falsa)
    assert provedor.chamadas_por_modelo == {}


def test_rodar_de_novo_nao_cobra_de_novo_os_completos(ambiente, monkeypatch):
    """Na segunda rodada, nenhum modelo completo é chamado de novo e o gasto acumulado não muda."""
    primeiro = ProvedorDeMentira()
    _trocar_provedor(monkeypatch, primeiro)
    gasto_da_primeira = comparacao.comparar(25.0, busca=busca_falsa)["gasto_acumulado_usd"]
    segundo = ProvedorDeMentira()
    _trocar_provedor(monkeypatch, segundo)
    resultado = comparacao.comparar(25.0, busca=busca_falsa)
    assert segundo.chamadas_por_modelo == {}
    assert resultado["gasto_acumulado_usd"] == gasto_da_primeira


def test_cliente_sem_disfarce_recusa_resposta_do_mock():
    """Se o cliente de IA devolver o MOCK (ex.: provedor fora do ar), a medição recusa em vez de pontuar."""
    medidor = comparacao.ClienteSemDisfarce(LLMClient(modo="mock"))
    with pytest.raises(comparacao.FalhaDoProvedor):
        medidor.gerar("interpretar_colunas", "pedido")
