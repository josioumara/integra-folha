"""O fluxo da empresa em LangGraph. Transições, pausas, retomada, falhas e limites.

O que estes testes provam (critério da fase):
- o arquivo com erro volta para a etapa certa;
- recarregar (abrir o fluxo de novo) retoma do mesmo ponto, sem refazer etapas;
- falha não vira falso sucesso; arquivo incompleto não chega a HOMOLOGADO nem libera o planejamento;
- a homologação libera o planejamento uma única vez;
- o estado guardado não tem dado pessoal.
"""
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from agents import interpretador
from models.contratos import EstadoProcessamento
from services import auditoria, banco, correcoes, execucoes, homologacao, mapeamentos, processamentos, validador
from services.llm_client import LLMClient
from tests.apoio_do_parametro import marcar_como_obrigatorios  # a matrícula é opcional no layout (ADR-143)
from workflows import fluxo_empresa as fluxo

# Os arquivos das empresas e os gabaritos
RAIZ = Path(__file__).resolve().parent.parent
ENVIOS = RAIZ / "data" / "synthetic" / "envios"
GOLDEN = RAIZ / "data" / "golden"


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


def busca_falsa(texto, k=3, **outros_argumentos):
    """RAG de mentira, sem depender do índice nem do modelo de embeddings."""
    return [{"fonte": f"Mapeamentos homologados › {texto}", "campo": None,
             "texto": f"Mapeamentos homologados › {texto}\nex."}]


@pytest.fixture(scope="module")
def verdade():
    """O gabarito de cada funcionário: funcionario_id -> campos corretos."""
    funcionarios = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            funcionarios[linha["funcionario_id"]] = linha
    return funcionarios


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def _gabarito(nome: str) -> dict:
    """O gabarito de um arquivo, pelo nome sem extensão."""
    return json.loads((GOLDEN / f"{nome}.json").read_text(encoding="utf-8"))


def receber(conexao, nome: str) -> tuple[str, str]:
    """Recebe um arquivo da demo. Devolve (processamento_id, empresa_id)."""
    gabarito = _gabarito(nome)
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    recebido = processamentos.receber_arquivo(conexao, conteudo, gabarito["arquivo"], gabarito["empresa_id"],
                                              date(2026, 9, 1), "empresa.teste")
    return recebido.perfil.processamento_id, gabarito["empresa_id"]


def receber_csv_incompleto(conexao) -> str:
    """Um arquivo da Aurora sem as colunas obrigatórias do layout: nunca pode ser homologado."""
    conteudo = "Colaborador;CPF;Salário Bruto\nAna;52998224725;R$ 3.150,00\n".encode()
    return processamentos.receber_arquivo(conexao, conteudo, "incompleto.csv", "EMP001", date(2026, 9, 1),
                                          "t").perfil.processamento_id


def escolhas_do_gabarito(nome: str) -> dict:
    """As decisões do aceite: a coluna ambígua vai para o campo certo; a extra é ignorada."""
    gabarito = _gabarito(nome)
    escolhas = {}
    for coluna, campo in gabarito["mapeamento"].items():
        if campo is None:
            campo = gabarito["colunas_ambiguas"][coluna]["campo_apos_confirmacao"]
        escolhas[coluna] = campo
    for coluna in gabarito["colunas_extras"]:
        escolhas[coluna] = mapeamentos.IGNORAR
    return escolhas


def iniciar(conexao, processamento_id, empresa_id, cliente=None):
    """Começa o fluxo com a busca falsa."""
    return fluxo.iniciar(conexao, processamento_id, empresa_id, cliente=cliente, busca=busca_falsa)


def retomar(conexao, processamento_id, empresa_id, resposta, cliente=None):
    """Entrega a decisão da pessoa, com a busca falsa."""
    return fluxo.retomar(conexao, processamento_id, empresa_id, resposta, cliente=cliente, busca=busca_falsa)


def aprovar(conexao, processamento_id, empresa_id, nome):
    """Retoma o aceite do mapeamento com as escolhas do gabarito."""
    resposta = {"acao": "aprovar", "escolhas": escolhas_do_gabarito(nome), "usuario": "rh"}
    return retomar(conexao, processamento_id, empresa_id, resposta)


def etapas_executadas(conexao, processamento_id) -> list[str]:
    """As etapas gravadas como execução (AgentRunEvent), na ordem."""
    etapas = []
    for execucao in execucoes.listar(conexao, processamento_id):
        etapas.append(execucao["etapa"])
    return etapas


def tipos_de_evento(conexao, processamento_id) -> list[str]:
    """Os tipos dos eventos da auditoria, na ordem."""
    tipos = []
    for evento in auditoria.eventos(conexao, processamento_id):
        tipos.append(evento["tipo"])
    return tipos


def corrigir_cpf_da_aurora(conexao, processamento_id, verdade):
    """O único bloqueante da Aurora: o CPF da linha 8. Pede e aplica a correção (como a empresa faria)."""
    for achado in validador.obter(conexao, processamento_id).achados:
        if achado.regra_id == "CPF_INVALIDO":
            funcionario_id = _gabarito("aurora_carga_inicial")["funcionario_ids"][achado.registro - 1]
            pedido = correcoes.propor(conexao, processamento_id, "EMP001", achado.linha, "cpf",
                                      verdade[funcionario_id]["cpf"], "CPF digitado errado", "rh")
            correcoes.decidir(conexao, processamento_id, "EMP001", pedido.correcao_id, True, "rh")


def cliente_que_falha():
    """Um LLM que sempre quebra (simula o provedor fora do ar sem queda para o MOCK)."""
    def falhar(prompt):
        """Toda chamada quebra."""
        raise RuntimeError("provedor fora do ar")
    return LLMClient(modo="mock", respostas_mock={interpretador.TAREFA: falhar})


# ---------- O caminho completo ----------

def test_caminho_completo_ate_a_homologacao(conexao, verdade):
    """Aurora: pausa no aceite, volta para a correção por causa do CPF, homologa e libera o planejamento."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    situacao = iniciar(conexao, processamento_id, empresa_id)
    assert situacao["etapa_atual"] == "aprovar_mapeamento"
    assert situacao["estado"]["status"] == EstadoProcessamento.MAPEAMENTO_PENDENTE.value

    situacao = aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    # O arquivo com erro para na etapa certa: a correção
    assert situacao["etapa_atual"] == "aguardar_correcao"
    assert situacao["estado"]["pendencias"]["BLOQUEANTE"] == 1

    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"})
    assert situacao["etapa_atual"] == "aprovar_homologacao"
    assert situacao["estado"]["ciclos_de_correcao"] == 1

    # A empresa envia ao banco: o arquivo espera a avaliação, e ninguém está cadastrado ainda
    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "homologar", "usuario": "rh"})
    assert situacao["etapa_atual"] == "avaliar_no_banco"
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.AGUARDANDO_BANCO
    assert homologacao.obter(conexao, processamento_id) is None
    # O banco aprova: homologado e planejamento liberado
    situacao = aprovar_no_banco(conexao, processamento_id, empresa_id)
    assert situacao["terminou"] and situacao["estado"]["status"] == EstadoProcessamento.HOMOLOGADO.value
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.HOMOLOGADO
    assert etapas_executadas(conexao, processamento_id) == [
        "perfilar", "recuperar_conhecimento", "interpretar", "aprovar_mapeamento", "padronizar", "validar",
        "aguardar_correcao", "validar", "aprovar_homologacao", "avaliar_no_banco", "liberar_planejamento"]


def aprovar_no_banco(conexao, processamento_id, empresa_id):
    """O especialista do banco aprova o envio que a empresa mandou (a pausa avaliar_no_banco)."""
    return retomar(conexao, processamento_id, empresa_id, {"acao": "aprovar", "usuario": "especialista"})


def test_homologacao_libera_o_planejamento_uma_unica_vez(conexao, verdade):
    """Depois do fim, retomar é recusado e iniciar não recomeça: o planejamento é liberado uma vez só."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"})
    retomar(conexao, processamento_id, empresa_id, {"acao": "homologar", "usuario": "rh"})
    aprovar_no_banco(conexao, processamento_id, empresa_id)

    with pytest.raises(ValueError, match="não está esperando"):
        retomar(conexao, processamento_id, empresa_id, {"acao": "homologar", "usuario": "rh"})
    situacao = iniciar(conexao, processamento_id, empresa_id)
    assert situacao["terminou"]
    assert tipos_de_evento(conexao, processamento_id).count("PLANEJAMENTO_LIBERADO") == 1
    assert tipos_de_evento(conexao, processamento_id).count("HOMOLOGADO") == 1


def test_retomada_nao_refaz_etapas(conexao):
    """Abrir o fluxo de novo (como a página recarregada) mostra a mesma pausa, sem rodar o Interpretador outra vez."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    # "Recarregar a página": iniciar de novo e consultar a situação com um grafo novo
    situacao = iniciar(conexao, processamento_id, empresa_id)
    assert situacao["etapa_atual"] == "aprovar_mapeamento"
    assert fluxo.situacao(conexao, processamento_id)["pergunta"]["etapa"] == "aprovar_mapeamento"
    assert etapas_executadas(conexao, processamento_id).count("interpretar") == 1


# ---------- Decisões humanas e voltas para a etapa certa ----------

def test_aceite_sem_decidir_a_coluna_ambigua_pergunta_de_novo(conexao):
    """Atlântico: sem escolher o campo de "Vencimentos", o fluxo continua no aceite, com o motivo."""
    processamento_id, empresa_id = receber(conexao, "atlantico_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "aprovar", "escolhas": {}, "usuario": "rh"})
    assert situacao["etapa_atual"] == "aprovar_mapeamento"
    assert "Vencimentos" in situacao["pergunta"]["erro"]
    situacao = aprovar(conexao, processamento_id, empresa_id, "atlantico_carga_inicial")
    # Com a decisão, segue; as rendas fora do padrão param na correção
    assert situacao["etapa_atual"] == "aguardar_correcao"


def test_handoff_devolve_o_fluxo_para_o_aceite(conexao):
    """O Assistente pediu remapeamento: ao seguir, o fluxo volta para o aceite do mapeamento."""
    processamento_id, empresa_id = receber(conexao, "atlantico_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "atlantico_carga_inicial")
    # O que o Assistente de Correção faz quando a empresa diz que a coluna é o salário líquido
    mapeamentos.solicitar_remapeamento(conexao, processamento_id, empresa_id, "Vencimentos",
                                       "a coluna Vencimentos é o salário líquido", busca=busca_falsa)
    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"})
    assert situacao["etapa_atual"] == "aprovar_mapeamento"
    assert situacao["estado"]["handoffs"] == 1
    assert situacao["estado"]["status"] == EstadoProcessamento.MAPEAMENTO_PENDENTE.value


def test_decisao_de_coluna_padroniza_de_novo(conexao):
    """Brisa: a matrícula perdeu os zeros; a empresa informa 5 dígitos e o fluxo padroniza de novo.

    A matrícula é opcional no layout, e um campo opcional não abre pendência (ADR-143): o parâmetro deste banco de
    teste a marca como obrigatória, para a decisão de coluna continuar testada.
    """
    marcar_como_obrigatorios(conexao, "matricula")
    processamento_id, empresa_id = receber(conexao, "brisa_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    situacao = aprovar(conexao, processamento_id, empresa_id, "brisa_carga_inicial")
    assert situacao["etapa_atual"] == "aguardar_correcao"
    regras_antes = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        regras_antes.add(achado.regra_id)
    assert "ZEROS_A_ESQUERDA" in regras_antes

    coluna_da_matricula = None
    for coluna, campo in _gabarito("brisa_carga_inicial")["mapeamento"].items():
        if campo == "matricula":
            coluna_da_matricula = coluna
    situacao = retomar(conexao, processamento_id, empresa_id,
                       {"acao": "decidir_colunas", "decisoes": {coluna_da_matricula: "zeros:5"}})
    regras_depois = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        regras_depois.add(achado.regra_id)
    assert "ZEROS_A_ESQUERDA" not in regras_depois
    assert situacao["estado"]["decisoes_de_coluna"] == {coluna_da_matricula: "zeros:5"}


def test_duvida_de_formato_da_matricula_opcional_nao_vira_pendencia(conexao):
    """Brisa, com o parâmetro como o layout (a matrícula é opcional): a dúvida dos zeros não vira pendência (ADR-143)."""
    processamento_id, empresa_id = receber(conexao, "brisa_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "brisa_carga_inicial")
    regras = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        regras.add(achado.regra_id)
    assert "ZEROS_A_ESQUERDA" not in regras


def test_empresa_pode_rejeitar_o_arquivo(conexao):
    """No aceite, a empresa desiste: REJEITADO, com o motivo registrado como código."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "rejeitar"})
    assert situacao["terminou"] and situacao["estado"]["status"] == EstadoProcessamento.REJEITADO.value
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.REJEITADO
    assert auditoria.eventos(conexao, processamento_id)[-1]["detalhe"] == {"motivo": "pedido da empresa"}


# ---------- Arquivo incompleto, falhas e limites ----------

def test_arquivo_incompleto_nao_homologa_nem_libera_o_planejamento(conexao):
    """Sem as colunas obrigatórias, o arquivo fica na correção; pedir "homologar" ali não faz nada."""
    processamento_id = receber_csv_incompleto(conexao)
    iniciar(conexao, processamento_id, "EMP001")
    situacao = retomar(conexao, processamento_id, "EMP001", {"acao": "aprovar", "escolhas": {}, "usuario": "rh"})
    assert situacao["etapa_atual"] == "aguardar_correcao"
    situacao = retomar(conexao, processamento_id, "EMP001", {"acao": "homologar", "usuario": "rh"})
    assert situacao["etapa_atual"] == "aguardar_correcao"
    assert "Ação desconhecida" in situacao["pergunta"]["erro"]
    assert processamentos.obter(conexao, processamento_id).status != EstadoProcessamento.HOMOLOGADO
    assert "PLANEJAMENTO_LIBERADO" not in tipos_de_evento(conexao, processamento_id)


def test_falha_do_llm_para_o_arquivo_e_permite_tentar_de_novo(conexao):
    """O Interpretador quebra: o arquivo para em aguardar_nova_tentativa, sem avançar; a nova tentativa segue."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    situacao = fluxo.iniciar(conexao, processamento_id, empresa_id, cliente=cliente_que_falha(), busca=busca_falsa)
    assert situacao["etapa_atual"] == "aguardar_nova_tentativa"
    assert situacao["estado"]["etapa_com_falha"] == "interpretar"
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.PERFILADO
    ultima_execucao = execucoes.listar(conexao, processamento_id)[-1]
    # Só o TIPO do erro vai para o Painel Técnico
    assert (ultima_execucao["etapa"], ultima_execucao["status"], ultima_execucao["tipo_erro"]) == (
        "interpretar", execucoes.ERRO, "RuntimeError")

    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "tentar_de_novo"})
    assert situacao["etapa_atual"] == "aprovar_mapeamento"


def test_falhas_repetidas_encerram_o_fluxo(conexao):
    """Passou do limite de tentativas depois de falha: REJEITADO, sem perguntar de novo."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    fluxo.iniciar(conexao, processamento_id, empresa_id, cliente=cliente_que_falha(), busca=busca_falsa)
    situacao = None
    for _ in range(fluxo.LIMITE_DE_TENTATIVAS):
        situacao = fluxo.retomar(conexao, processamento_id, empresa_id, {"acao": "tentar_de_novo"},
                                 cliente=cliente_que_falha(), busca=busca_falsa)
    assert situacao["terminou"] and situacao["estado"]["status"] == EstadoProcessamento.REJEITADO.value
    assert situacao["estado"]["motivo_da_rejeicao"] == "falha repetida"


def test_limite_de_ciclos_de_correcao(conexao, monkeypatch):
    """Mais pedidos de revalidação que o limite: o fluxo encerra (a empresa reenvia o arquivo corrigido)."""
    monkeypatch.setattr(fluxo, "LIMITE_CICLOS_DE_CORRECAO", 2)
    processamento_id = receber_csv_incompleto(conexao)
    iniciar(conexao, processamento_id, "EMP001")
    retomar(conexao, processamento_id, "EMP001", {"acao": "aprovar", "escolhas": {}, "usuario": "rh"})
    situacao = None
    for _ in range(3):
        situacao = retomar(conexao, processamento_id, "EMP001", {"acao": "revalidar"})
    assert situacao["estado"]["status"] == EstadoProcessamento.REJEITADO.value
    assert situacao["estado"]["motivo_da_rejeicao"] == "limite de ciclos de correção"


# ---------- Isolamento e privacidade ----------

def test_outra_empresa_nao_mexe_no_fluxo(conexao):
    """A Horizonte não inicia nem retoma o fluxo do arquivo da Aurora."""
    processamento_id, _ = receber(conexao, "aurora_carga_inicial")
    with pytest.raises(KeyError):
        iniciar(conexao, processamento_id, "EMP002")
    iniciar(conexao, processamento_id, "EMP001")
    with pytest.raises(KeyError):
        retomar(conexao, processamento_id, "EMP002", {"acao": "rejeitar"})


def test_estado_guardado_nao_tem_dado_pessoal(conexao, verdade):
    """O estado no ponto de salvamento só tem identificadores, contagens e decisões: nenhum CPF ou nome."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    estado_em_texto = json.dumps(fluxo.situacao(conexao, processamento_id), ensure_ascii=False, default=str)
    for funcionario_id in _gabarito("aurora_carga_inicial")["funcionario_ids"]:
        assert verdade[funcionario_id]["cpf"] not in estado_em_texto
        assert verdade[funcionario_id]["nome_completo"] not in estado_em_texto


def test_toda_etapa_do_grafo_tem_destinos_validos():
    """As setas do fluxo só apontam para etapas que existem (ou para o fim)."""
    for destinos in fluxo.DESTINOS.values():
        for destino in destinos:
            assert destino == "fim" or destino in fluxo.DESTINOS


# ---------- A ponte com a tela (fluxo.responder) ----------

def test_responder_leva_o_fluxo_ao_aceite_depois_do_handoff(conexao):
    """Fluxo parado na correção + mapeamento devolvido pelo Assistente: o clique em "Aceitar" chega ao aceite."""
    processamento_id, empresa_id = receber(conexao, "atlantico_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "atlantico_carga_inicial")
    mapeamentos.solicitar_remapeamento(conexao, processamento_id, empresa_id, "Vencimentos",
                                       "a coluna Vencimentos é o salário líquido", busca=busca_falsa)
    situacao = fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_mapeamento",
                               {"acao": "aprovar", "escolhas": {}, "usuario": "rh"}, busca=busca_falsa)
    # O novo aceite passou (a coluna ficou ignorada) e a revalidação aponta a falta da renda
    assert situacao["etapa_atual"] == "aguardar_correcao"
    assert situacao["estado"]["handoffs"] == 1
    regras = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        regras.add(achado.regra_id)
    assert "OBRIGATORIO_SEM_COLUNA" in regras


def test_responder_homologa_a_partir_da_correcao(conexao, verdade):
    """Com as pendências resolvidas, "Homologar" revalida e homologa, mesmo com o fluxo parado na correção."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    situacao = fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao",
                               {"acao": "homologar", "usuario": "rh"}, busca=busca_falsa)
    assert situacao["etapa_atual"] == "avaliar_no_banco"
    situacao = fluxo.responder(conexao, processamento_id, empresa_id, "avaliar_no_banco",
                               {"acao": "aprovar", "usuario": "especialista"}, busca=busca_falsa)
    assert situacao["terminou"] and situacao["estado"]["status"] == EstadoProcessamento.HOMOLOGADO.value


def test_banco_devolve_com_motivo_e_a_empresa_envia_de_novo(conexao, verdade):
    """Devolvido: o arquivo volta para a correção com o motivo; enviado de novo e aprovado, fica homologado."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao", {"acao": "homologar", "usuario": "rh"},
                    busca=busca_falsa)
    # Devolver sem motivo não vale: o banco é perguntado de novo
    situacao = retomar(conexao, processamento_id, empresa_id, {"acao": "devolver", "motivo": "  ", "usuario": "especialista"})
    assert situacao["etapa_atual"] == "avaliar_no_banco" and "motivo" in situacao["estado"]["ultimo_erro"]
    # Devolvido com motivo: volta para a correção, com o recado para a empresa
    situacao = retomar(conexao, processamento_id, empresa_id,
                       {"acao": "devolver", "motivo": "Confirme a data de admissão da linha 3.", "usuario": "especialista"})
    assert situacao["etapa_atual"] == "aguardar_correcao"
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.DEVOLVIDO
    assert "data de admissão" in situacao["estado"]["ultimo_erro"]
    assert homologacao.obter(conexao, processamento_id) is None
    assert "DEVOLVIDO_PELO_BANCO" in tipos_de_evento(conexao, processamento_id)
    # A empresa envia de novo (revalida sozinho) e o banco aprova
    situacao = fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao",
                               {"acao": "homologar", "usuario": "rh"}, busca=busca_falsa)
    assert situacao["etapa_atual"] == "avaliar_no_banco"
    situacao = aprovar_no_banco(conexao, processamento_id, empresa_id)
    assert situacao["terminou"] and homologacao.obter(conexao, processamento_id) is not None
    assert tipos_de_evento(conexao, processamento_id).count("APROVADO_PELO_BANCO") == 1


def test_responder_recusa_acao_de_outra_etapa(conexao):
    """Homologar com pendência em aberto: o fluxo não chega à homologação e recusa, dizendo a etapa."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    with pytest.raises(ValueError, match="Correção das pendências"):
        fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao",
                        {"acao": "homologar", "usuario": "rh"}, busca=busca_falsa)
    assert processamentos.obter(conexao, processamento_id).status != EstadoProcessamento.HOMOLOGADO


def test_desenho_do_fluxo_mostra_todas_as_etapas_e_destaca_a_atual():
    """O desenho (DOT) tem todas as etapas e pinta a atual."""
    desenho = fluxo.desenho("validar")
    for etapa in fluxo.NOMES_DAS_ETAPAS:
        assert f"  {etapa} [label=" in desenho
    assert 'validar [label="Validação", fillcolor="#ffd966"]' in desenho
