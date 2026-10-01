"""O custo da IA de cada execução e o teto do dia (ADR-131).

O que se prova aqui:
    - a medição (services/uso_da_ia.py) soma as chamadas feitas dentro dela, e só elas: fora de uma medição nada soma,
      e uma medição aberta dentro de outra não soma na de fora (nada é contado duas vezes);
    - a medição atravessa para outra linha de execução quando o contexto vai junto (o Redator de perguntas);
    - a linha da execução (execucoes_agentes) grava os tokens e o custo; sem medição, fica "não medido" (vazio);
    - uma execução em que a IA real caiu para o MOCK não passa por "OK": vira ERRO, com o tipo certo;
    - os tetos do dia e do mês moram no banco (começam em US$ 20; gravar_teto recusa valor impossível), somam todas
      as chamadas reais e, atingido qualquer um, PAUSAM a próxima chamada de QUALQUER cliente (sem resposta simulada);
    - a pausa em cada lugar: o envio espera sem contar como falha, o arquivo de Word é recusado com o recado, o
      Endomarketing grava o ERRO, e a API devolve 503 com o recado de quem está na tela;
    - a leitura separa o uso do Leitor do uso do Conferidor (cada um paga o seu);
    - uma etapa do fluxo da empresa grava o uso da IA do seu trabalho.
Todos os testes rodam sem chamar a IA de verdade: o "provedor" é trocado por um falso, que informa tokens e custo.
"""
import threading
from datetime import date, datetime, timezone

import pytest

from agents import conferidor_da_leitura, leitor_de_documentos
from models.contratos import carregar_layout
from services import aceitacao_dos_agentes, banco, config, execucoes, teto_de_gasto, uso_da_ia
from services.llm_client import LLMClient, RespostaLLM
from workflows.fluxo_empresa import FluxoDaEmpresa


@pytest.fixture
def conexao(tmp_path, monkeypatch):
    """Um banco vazio, só deste teste; o teto do dia também passa a somar nele."""
    caminho = tmp_path / "uso.db"
    monkeypatch.setattr(config, "CAMINHO_BANCO", caminho)
    conexao_do_teste = banco.conectar(caminho)
    yield conexao_do_teste
    conexao_do_teste.close()


def resposta_medida(tokens_entrada: int = 1000, tokens_saida: int = 100, custo_usd: float = 0.01) -> RespostaLLM:
    """Uma resposta "real" falsa, com tokens e custo medidos."""
    return RespostaLLM(texto="{}", modo="llm", modelo="modelo-falso", tokens_entrada=tokens_entrada,
                       tokens_saida=tokens_saida, custo_usd=custo_usd)


def cliente_real_falso(monkeypatch, custo_usd: float = 0.01) -> LLMClient:
    """Um cliente no modo real cujo provedor é falso: não sai da máquina e custa o valor dado por chamada."""
    def provedor_falso(self, tarefa, prompt, sistema, modelo, temperatura, esforco=None, esquema_json=None):
        """Responde na hora, com tokens e custo medidos."""
        return resposta_medida(custo_usd=custo_usd)
    monkeypatch.setattr(LLMClient, "_chamar_provedor", provedor_falso)
    return LLMClient(modo="llm", teto_de_gasto_usd=100.0)


# ---------------- A medição (o taxímetro) ----------------

def test_a_medicao_soma_so_as_chamadas_feitas_dentro_dela(conexao, monkeypatch):
    cliente = cliente_real_falso(monkeypatch)
    # Fora de uma medição: a chamada acontece, mas não soma em lugar nenhum
    cliente.gerar("tarefa", "pedido")
    with uso_da_ia.medir() as uso:
        cliente.gerar("tarefa", "pedido")
        cliente.gerar("tarefa", "pedido")
    assert uso.chamadas == 2 and uso.tokens_entrada == 2000 and uso.tokens_saida == 200
    assert uso.custo_usd == pytest.approx(0.02)


def test_medicao_de_dentro_nao_soma_na_de_fora(conexao, monkeypatch):
    cliente = cliente_real_falso(monkeypatch)
    with uso_da_ia.medir() as de_fora:
        cliente.gerar("tarefa", "pedido")
        with uso_da_ia.medir() as de_dentro:
            cliente.gerar("tarefa", "pedido")
            cliente.gerar("tarefa", "pedido")
        cliente.gerar("tarefa", "pedido")
    # Cada execução paga só as suas chamadas: nada é contado duas vezes
    assert de_dentro.chamadas == 2 and de_fora.chamadas == 2


def test_no_mock_a_chamada_conta_mas_tokens_e_custo_ficam_nao_medidos():
    with uso_da_ia.medir() as uso:
        LLMClient(modo="mock").gerar("tarefa", "pedido")
    assert uso.chamadas == 1 and uso.custo_usd is None and uso.tokens_entrada is None and uso.motivo_da_queda is None


def test_a_medicao_atravessa_para_outra_linha_de_execucao_com_o_contexto(conexao, monkeypatch):
    import contextvars
    cliente = cliente_real_falso(monkeypatch)
    with uso_da_ia.medir() as uso:
        # Como o Redator de perguntas faz: a outra linha de execução roda com uma cópia do contexto
        contexto = contextvars.copy_context()
        linha = threading.Thread(target=contexto.run, args=(cliente.gerar, "tarefa", "pedido"))
        linha.start()
        linha.join()
    assert uso.chamadas == 1 and uso.custo_usd == pytest.approx(0.01)


def test_o_uso_sem_a_parte_de_outro_nunca_fica_negativo():
    total = uso_da_ia.Uso(chamadas=3, tokens_entrada=3000, tokens_saida=300, custo_usd=0.03)
    parte = uso_da_ia.Uso(chamadas=1, tokens_entrada=1000, tokens_saida=None, custo_usd=0.05)
    resto = total.menos(parte)
    assert resto.chamadas == 2 and resto.tokens_entrada == 2000 and resto.tokens_saida == 300 and resto.custo_usd == 0


# ---------------- A linha da execução ----------------

def registrar_e_ler(conexao, status: str, uso: uso_da_ia.Uso | None, tipo_erro: str | None = None) -> dict:
    """Grava uma execução de teste e devolve a linha gravada."""
    agora = datetime.now(timezone.utc)
    execucoes.registrar(conexao, "PROC-1", "EMP001", "etapa", "Agente", agora, agora, status, modelo="modelo-falso",
                        tipo_erro=tipo_erro, uso=uso)
    return execucoes.listar(conexao, "PROC-1")[-1]


def test_a_execucao_grava_tokens_e_custo(conexao):
    uso = uso_da_ia.Uso(chamadas=2, tokens_entrada=1500, tokens_saida=250, custo_usd=0.0123)
    linha = registrar_e_ler(conexao, execucoes.OK, uso)
    assert (linha["tokens_entrada"], linha["tokens_saida"], linha["custo_usd"]) == (1500, 250, 0.0123)
    assert linha["status"] == execucoes.OK


def test_sem_medicao_tokens_e_custo_ficam_vazios(conexao):
    linha = registrar_e_ler(conexao, execucoes.OK, None)
    assert linha["tokens_entrada"] is None and linha["custo_usd"] is None


def test_queda_para_o_mock_nao_passa_por_ok(conexao):
    # O provedor caiu (ou outro limite do cliente): a execução vira ERRO, com o tipo IAIndisponivel
    for motivo in ("falha no provedor: tempo esgotado", "limite de chamadas da sessão atingido",
                   "teto de gasto da sessão atingido"):
        linha = registrar_e_ler(conexao, execucoes.OK, uso_da_ia.Uso(chamadas=1, motivo_da_queda=motivo))
        assert (linha["status"], linha["tipo_erro"]) == (execucoes.ERRO, "IAIndisponivel"), motivo
    # O tipo que o agente já informou continua valendo
    linha = registrar_e_ler(conexao, execucoes.ERRO, uso_da_ia.Uso(chamadas=1, motivo_da_queda="x"),
                            tipo_erro="RespostaForaDoContrato")
    assert linha["tipo_erro"] == "RespostaForaDoContrato"


# ---------------- O teto de gasto (dia e mês, lidos do banco; revisão do ADR-131) ----------------

def test_os_tetos_comecam_em_20_dolares_e_moram_no_banco(conexao):
    # Num banco novo, os dois tetos começam em US$ 20
    assert teto_de_gasto.ler_tetos(conexao) == {"dia": 20.0, "mes": 20.0}
    # Ler não grava nada (a conferência roda antes de cada chamada real e não pode escrever no banco a cada vez)
    assert conexao.execute("SELECT COUNT(*) FROM limites_de_gasto_da_ia").fetchone()[0] == 0
    assert teto_de_gasto.situacao_dos_tetos(conexao)["atingido"] is None
    assert conexao.execute("SELECT COUNT(*) FROM limites_de_gasto_da_ia").fetchone()[0] == 0
    # Gravar um teto muda só aquele período, e o valor fica no banco (uma conexão nova lê o mesmo)
    assert teto_de_gasto.gravar_teto(conexao, "mes", 35, "especialista.banco") == {"dia": 20.0, "mes": 35.0}
    assert teto_de_gasto.gravar_teto(conexao, "dia", 2.5, "especialista.banco") == {"dia": 2.5, "mes": 35.0}
    outra_conexao = banco.conectar(config.CAMINHO_BANCO)
    assert teto_de_gasto.ler_tetos(outra_conexao) == {"dia": 2.5, "mes": 35.0}
    # Quem mudou e quando ficam registrados (a mudança é auditável)
    linha = outra_conexao.execute("SELECT alterado_por FROM limites_de_gasto_da_ia WHERE periodo = 'mes'").fetchone()
    assert linha[0] == "especialista.banco"
    outra_conexao.close()
    # Ler de novo não volta aos valores iniciais (eles só entram quando o período ainda não tem teto)
    assert teto_de_gasto.ler_tetos(conexao)["mes"] == 35.0


def test_gravar_teto_recusa_valor_impossivel(conexao):
    # Variações de valor e de período que não podem virar teto (nenhuma muda o que está gravado)
    recusados = [("semana", 10, "banco"), ("DIA", 10, "banco"), ("dia", 0, "banco"), ("dia", -5, "banco"),
                 ("mes", "20", "banco"), ("mes", True, "banco"), ("mes", 1000.01, "banco"), ("dia", 10, "  ")]
    for periodo, valor, quem in recusados:
        with pytest.raises(ValueError):
            teto_de_gasto.gravar_teto(conexao, periodo, valor, quem)
    assert teto_de_gasto.ler_tetos(conexao) == {"dia": 20.0, "mes": 20.0}
    # O maior valor aceito é o próprio máximo
    assert teto_de_gasto.gravar_teto(conexao, "mes", 1000, "banco")["mes"] == 1000.0


def test_o_gasto_do_dia_soma_todas_as_chamadas_de_todos_os_clientes(conexao, monkeypatch):
    cliente_real_falso(monkeypatch, custo_usd=0.25)
    # Três pedidos diferentes, cada um com o seu cliente (como na aplicação)
    for _ in range(3):
        LLMClient(modo="llm", teto_de_gasto_usd=100.0).gerar("tarefa", "pedido")
    assert teto_de_gasto.gasto_do_dia(conexao) == pytest.approx(0.75)
    situacao = teto_de_gasto.situacao_dos_tetos(conexao)
    assert situacao["gasto_dia_usd"] == pytest.approx(0.75) and situacao["gasto_mes_usd"] == pytest.approx(0.75)
    assert situacao["atingido"] is None


def test_o_gasto_do_mes_soma_so_os_dias_daquele_mes(conexao):
    # Dias do mês, do mês anterior e do seguinte: só os do mês entram (e a virada de dezembro para janeiro)
    for dia, custo in ((date(2026, 8, 31), 5.0), (date(2026, 9, 1), 1.0), (date(2026, 9, 15), 2.0),
                       (date(2026, 9, 30), 4.0), (date(2026, 10, 1), 8.0), (date(2026, 12, 31), 3.0),
                       (date(2027, 1, 1), 6.0)):
        teto_de_gasto.somar_no_dia(conexao, custo, dia)
    assert teto_de_gasto.gasto_do_mes(conexao, date(2026, 9, 10)) == pytest.approx(7.0)
    assert teto_de_gasto.gasto_do_mes(conexao, date(2026, 12, 1)) == pytest.approx(3.0)
    assert teto_de_gasto.gasto_do_mes(conexao, date(2027, 1, 20)) == pytest.approx(6.0)
    # Mês sem nenhuma chamada: zero
    assert teto_de_gasto.gasto_do_mes(conexao, date(2026, 11, 5)) == 0.0


def test_atingido_o_teto_do_dia_a_ia_pausa_sem_resposta_simulada(conexao, monkeypatch):
    teto_de_gasto.gravar_teto(conexao, "dia", 1.00, "teste")
    cliente_real_falso(monkeypatch, custo_usd=0.40)
    # Cada chamada vem de um cliente novo (o teto do cliente nunca seria atingido)
    for _ in range(3):
        assert LLMClient(modo="llm", teto_de_gasto_usd=100.0).gerar("tarefa", "pedido").modo == "llm"
    # 0,40 + 0,40 + 0,40 = 1,20 ≥ 1,00: a 4ª chamada PAUSA (nada de resposta simulada no lugar da real)
    with pytest.raises(teto_de_gasto.TetoDeGastoAtingido) as pausa:
        LLMClient(modo="llm", teto_de_gasto_usd=100.0).gerar("tarefa", "pedido")
    assert pausa.value.periodo == "dia" and str(pausa.value) == teto_de_gasto.RECADO_PARA_A_EMPRESA
    assert teto_de_gasto.situacao_dos_tetos(conexao)["atingido"] == "dia"
    # Subir o teto libera a IA na hora (sem esperar a meia-noite)
    teto_de_gasto.gravar_teto(conexao, "dia", 5.00, "teste")
    assert LLMClient(modo="llm", teto_de_gasto_usd=100.0).gerar("tarefa", "pedido").modo == "llm"


def test_atingido_o_teto_do_mes_a_ia_pausa_mesmo_com_o_dia_livre(conexao, monkeypatch):
    # O gasto do mês (lançado no dia 1º) já chegou ao teto do mês; o do dia (US$ 20) continua longe
    teto_de_gasto.gravar_teto(conexao, "mes", 3.00, "teste")
    hoje = teto_de_gasto.hoje_em_brasilia()
    teto_de_gasto.somar_no_dia(conexao, 3.00, date(hoje.year, hoje.month, 1))
    cliente_real_falso(monkeypatch)
    with pytest.raises(teto_de_gasto.TetoDeGastoAtingido) as pausa:
        LLMClient(modo="llm", teto_de_gasto_usd=100.0).gerar("tarefa", "pedido")
    assert pausa.value.periodo == "mes"


def test_no_modo_mock_o_teto_nunca_pausa(conexao):
    # O MOCK não gasta: mesmo com o teto estourado, a simulação responde (testes e demo sem custo seguem)
    teto_de_gasto.gravar_teto(conexao, "dia", 0.01, "teste")
    teto_de_gasto.somar_no_dia(conexao, 1.00)
    assert LLMClient(modo="mock").gerar("tarefa", "pedido").modo == "mock"


def test_modelo_sem_preco_avisa_no_log(conexao, caplog):
    # Chamada real sem custo medido (modelo fora da tabela de preços): não soma, mas o log avisa qual modelo
    with caplog.at_level("WARNING"):
        teto_de_gasto.anotar_custo(None, "modelo-sem-preco")
    assert "modelo-sem-preco" in caplog.text
    assert teto_de_gasto.gasto_do_dia(conexao) == 0.0


def test_o_dia_do_teto_e_o_de_brasilia():
    # 01h de 29/09 em UTC ainda é 28/09 em Brasília
    momento = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)
    assert momento.astimezone(teto_de_gasto.FUSO_DE_BRASILIA).date().isoformat() == "2026-09-28"


def test_se_o_banco_falhar_a_chamada_segue(monkeypatch):
    def banco_fora(*argumentos, **argumentos_nomeados):
        """Um banco que não responde."""
        raise OSError("banco fora do ar")
    monkeypatch.setattr(teto_de_gasto.banco, "conectar", banco_fora)
    # A conta do teto falhou: vale o teto do cliente, e o trabalho da empresa não cai
    assert teto_de_gasto.teto_atingido() is None
    teto_de_gasto.anotar_custo(0.5, "modelo-falso")


# ---------------- A pausa em cada lugar que usa a IA ----------------

def pausa_no_teto(*argumentos, **argumentos_nomeados):
    """Um trabalho de IA que encontra o teto atingido."""
    raise teto_de_gasto.TetoDeGastoAtingido("dia")


def test_no_fluxo_do_envio_a_pausa_espera_sem_contar_como_falha(conexao):
    fluxo = FluxoDaEmpresa(conexao)
    estado = {"processamento_id": "PROC-PAUSA", "empresa_id": "EMP001", "falhas": 0}
    # Várias pausas seguidas (mais que o limite de falhas): o envio nunca é rejeitado por isso
    for _ in range(5):
        mudancas = fluxo._executar_etapa(estado, "interpretar", "Interpretador", pausa_no_teto)
        assert mudancas["proximo_passo"] == "aguardar_nova_tentativa"
        assert mudancas["ultimo_erro"] == teto_de_gasto.RECADO_PARA_A_EMPRESA
        assert "falhas" not in mudancas
    # O banco vê cada pausa como ERRO na Telemetria, com o tipo da pausa
    linhas = execucoes.listar(conexao, "PROC-PAUSA")
    assert len(linhas) == 5
    for linha in linhas:
        assert (linha["status"], linha["tipo_erro"]) == (execucoes.ERRO, "TetoDeGastoAtingido")
    # Uma falha de verdade continua contando
    def falha_de_verdade():
        """Um trabalho que quebra por outro motivo."""
        raise KeyError("x")
    assert fluxo._executar_etapa(estado, "interpretar", "Interpretador", falha_de_verdade)["falhas"] == 1


def test_a_leitura_de_word_pausada_recusa_o_arquivo_com_o_recado(conexao, monkeypatch):
    from services import leitura_de_word
    teto_de_gasto.gravar_teto(conexao, "dia", 0.50, "teste")
    teto_de_gasto.somar_no_dia(conexao, 0.50)
    cliente = cliente_real_falso(monkeypatch)
    paragrafos = ["A Maria Souza, CPF 529.982.247-25, entrou em 05/03/2026 como analista, salário de R$ 4.350,00."]
    with pytest.raises(leitura_de_word.DocumentoRecusado) as recusa:
        leitura_de_word._ler_texto_corrido(paragrafos, cliente, carregar_layout())
    assert str(recusa.value) == teto_de_gasto.RECADO_DO_ARQUIVO_RECUSADO
    # A execução do Leitor vai junto, com o ERRO da pausa (o banco vê na Telemetria)
    tipos = []
    for execucao in recusa.value.execucoes_dos_agentes:
        tipos.append(execucao["tipo_erro"])
    assert "TetoDeGastoAtingido" in tipos


def test_o_endomarketing_pausado_grava_o_erro_e_deixa_o_aviso_subir(conexao, monkeypatch):
    from agents import endomarketing
    teto_de_gasto.gravar_teto(conexao, "mes", 0.10, "teste")
    teto_de_gasto.somar_no_dia(conexao, 0.10)
    cliente = cliente_real_falso(monkeypatch)
    # Um benefício do catálogo vigente da Aurora: o material só vai à IA com um benefício escolhido
    beneficio = endomarketing.beneficios_do_catalogo(conexao, "EMP001")[0]
    with pytest.raises(teto_de_gasto.TetoDeGastoAtingido):
        endomarketing.gerar_material(conexao, "EMP001", "comunicado", "especialista.banco", cliente=cliente,
                                     beneficios=[beneficio])
    linha = execucoes.listar(conexao)[-1]
    assert (linha["etapa"], linha["status"], linha["tipo_erro"]) == ("gerar_material:pausado", execucoes.ERRO,
                                                                      "TetoDeGastoAtingido")


def test_a_api_devolve_503_com_o_recado_de_quem_esta_na_tela():
    import asyncio
    import json as modulo_json

    from starlette.requests import Request

    from api import principal
    # Rotas da empresa e do banco (variações de caminho): cada uma recebe o seu recado
    casos = [("/api/banco/empresas/EMP001/endomarketing/gerar", teto_de_gasto.RECADO_PARA_O_BANCO),
             ("/api/banco/endomarketing/gerar", teto_de_gasto.RECADO_PARA_O_BANCO),
             ("/api/empresa/pendencias/assistente", teto_de_gasto.RECADO_PARA_A_EMPRESA),
             ("/api/envios", teto_de_gasto.RECADO_PARA_A_EMPRESA)]
    for caminho, recado in casos:
        pedido = Request({"type": "http", "method": "POST", "path": caminho, "headers": [], "query_string": b""})
        resposta = asyncio.run(principal.avisar_a_pausa_pelo_teto(pedido, teto_de_gasto.TetoDeGastoAtingido("dia")))
        assert resposta.status_code == 503, caminho
        assert modulo_json.loads(resposta.body)["detail"] == recado, caminho


# ---------------- Os agentes ----------------

def test_a_leitura_separa_o_uso_do_leitor_do_uso_do_conferidor(conexao, monkeypatch):
    # Um cliente no modo real com as respostas simuladas do Leitor e do Conferidor, e tokens e custo medidos
    simulacoes = {leitor_de_documentos.TAREFA: leitor_de_documentos.simular_leitura,
                  leitor_de_documentos.TAREFA_SEGMENTACAO: leitor_de_documentos.simular_divisao,
                  conferidor_da_leitura.TAREFA: conferidor_da_leitura.simular_conferencia}

    def provedor_falso(self, tarefa, prompt, sistema, modelo, temperatura, esforco=None, esquema_json=None):
        """Responde com a simulação da tarefa, custando US$ 0,01 (Leitor) ou US$ 0,001 (Conferidor)."""
        custo = 0.001 if tarefa == conferidor_da_leitura.TAREFA else 0.01
        return RespostaLLM(texto=simulacoes[tarefa](prompt), modo="llm", modelo="modelo-falso",
                           tokens_entrada=100, tokens_saida=10, custo_usd=custo)
    monkeypatch.setattr(LLMClient, "_chamar_provedor", provedor_falso)
    cliente = LLMClient(modo="llm", teto_de_gasto_usd=100.0, respostas_mock=simulacoes)
    trecho = ("A Maria Souza, CPF 529.982.247-25, entrou em 05/03/2026 como analista, salário de R$ 4.350,00.\n"
              "O João Lima, CPF 111.444.777-35, começou em 10/03/2026 como assistente, salário de R$ 2.900,00.")
    tabela = leitor_de_documentos.ler(trecho, carregar_layout(), cliente, conferir_com_outra_ia=True)
    do_leitor, do_conferidor = tabela.uso[leitor_de_documentos.CHAVE_DAS_EXECUCOES]
    uso_do_conferidor = do_conferidor["uso"]
    uso_do_leitor = do_leitor["uso"]
    # O Conferidor pagou só as suas chamadas; o Leitor, o resto; juntos, o total da leitura
    assert uso_do_conferidor["custo_usd"] == pytest.approx(0.001 * uso_do_conferidor["chamadas"])
    assert uso_do_leitor["custo_usd"] == pytest.approx(0.01 * uso_do_leitor["chamadas"])
    assert uso_do_leitor["chamadas"] + uso_do_conferidor["chamadas"] == tabela.uso["chamadas"]


def test_a_etapa_do_fluxo_grava_o_uso_da_ia_do_seu_trabalho(conexao, monkeypatch):
    cliente = cliente_real_falso(monkeypatch, custo_usd=0.02)
    fluxo = FluxoDaEmpresa(conexao)
    estado = {"processamento_id": "PROC-FLUXO", "empresa_id": "EMP001", "falhas": 0}

    def trabalho():
        """Uma etapa que chama a IA duas vezes."""
        cliente.gerar("tarefa", "pedido")
        cliente.gerar("tarefa", "pedido")
        return {}, {"modelo": "modelo-falso"}
    fluxo._executar_etapa(estado, "interpretar", "Interpretador", trabalho)
    linha = execucoes.listar(conexao, "PROC-FLUXO")[-1]
    assert linha["custo_usd"] == pytest.approx(0.04) and linha["tokens_entrada"] == 2000


def test_a_aceitacao_reconhece_a_pergunta_nova_e_a_da_v1():
    suspeita = conferidor_da_leitura.Suspeita(pessoa=1, campo="cpf", motivo="x", valor_lido="1", valor_no_documento="2")
    pergunta_nova = conferidor_da_leitura.pergunta_da_suspeita(suspeita)
    pergunta_da_v1 = conferidor_da_leitura.INICIO_DA_PERGUNTA_DA_V1 + "o CPF parece de outra pessoa."
    for pergunta in (pergunta_nova, pergunta_da_v1):
        assert pergunta.startswith(aceitacao_dos_agentes.COMECOS_DA_PERGUNTA_DO_CONFERIDOR)



# ---------------- A tela: custo por etapa ----------------

def test_custo_por_etapa_junta_por_agente_e_etapa_e_nao_inventa_zero():
    from services import painel
    lista = [
        {"agente": "Leitor de documentos", "etapa": "ler_texto_corrido", "modelo": "m", "custo_usd": 0.03,
         "tokens_entrada": 3000, "tokens_saida": 300},
        {"agente": "Leitor de documentos", "etapa": "ler_texto_corrido", "modelo": "m", "custo_usd": 0.01,
         "tokens_entrada": 1000, "tokens_saida": 100},
        # A situação depois do ":" não separa a etapa
        {"agente": "Assistente de Correção", "etapa": "conversa:corrigir", "modelo": "m", "custo_usd": 0.002,
         "tokens_entrada": 500, "tokens_saida": 50},
        {"agente": "Assistente de Correção", "etapa": "conversa:explicar", "modelo": "mock", "custo_usd": None,
         "tokens_entrada": None, "tokens_saida": None},
        # Sem medição nenhuma: fica "não medido" (None), no fim
        {"agente": "Consultor (agente único)", "etapa": "pergunta:respondido", "modelo": "mock", "custo_usd": None,
         "tokens_entrada": None, "tokens_saida": None},
        # Regra (sem modelo): não é IA, não entra
        {"agente": "Regra", "etapa": "perfilar", "modelo": None, "custo_usd": None, "tokens_entrada": None,
         "tokens_saida": None},
    ]
    tabela = painel.custo_por_etapa(lista)
    agentes = []
    for linha in tabela:
        agentes.append(linha["agente"])
    assert agentes == ["Leitor de documentos", "Assistente de Correção", "Consultor (agente único)"]
    leitor, assistente, consultor = tabela
    assert leitor["custo_usd"] == pytest.approx(0.04) and leitor["custo_medio_usd"] == pytest.approx(0.02)
    assert leitor["tokens_entrada"] == 4000
    assert (assistente["etapa"], assistente["execucoes"], assistente["medidas"]) == ("conversa", 2, 1)
    assert assistente["custo_medio_usd"] == pytest.approx(0.002)
    assert consultor["custo_usd"] is None and consultor["custo_medio_usd"] is None
