"""A primeira fala do Agente de validação escrita pela IA (pendências por conversa, ADR-118): uma resposta mais
natural, com uma diretriz de tom de voz séria.

O que estes testes provam, com um cliente de IA falso (nada é pago):
- uma resposta boa passa na conferência, aparece na lista e fica GUARDADA: a lista abre de novo sem chamar a IA;
- uma resposta ruim (sem "?", com nome técnico, sem o valor lido, com exclamação) cai na frase de reserva, e nada
  é guardado;
- a IA fora do ar, lenta demais ou com a resposta fora do formato: a lista aparece com as reservas, e a falha fica na
  Telemetria;
- o valor lido mudou (a empresa corrigiu e ainda há problema): a pergunta é escrita de novo;
- as duas diretrizes (pergunta e conversa) usam o mesmo arquivo de tom de voz;
- no modo MOCK, a IA simulada escreve as próprias frases de reserva.
"""
import json
import time

import pytest

from agents import assistente_correcao, redator_de_perguntas, tom_de_voz
from services import acompanhamento, cadastro, execucoes, perguntas_das_pendencias, validador
from services.llm_client import LLMClient
from tests.test_assistente_na_tela import aurora_com_o_cpf_errado
from tests.test_fluxo_empresa import conexao, gerar_envios, verdade  # noqa: F401


class IaFalsa:
    """Uma IA de mentira para a tarefa das perguntas: conta as chamadas e responde com a função dada."""

    def __init__(self, responder):
        """responder: função que recebe as pendências do pedido ([dict]) e devolve o texto da resposta."""
        self.chamadas = 0
        self.responder = responder

    def cliente(self) -> LLMClient:
        """O cliente que os serviços usam (modo MOCK, com esta IA no lugar da simulação)."""
        return LLMClient(modo="mock", respostas_mock={redator_de_perguntas.TAREFA: self._responder})

    def _responder(self, pedido: str) -> str:
        """Lê as pendências do pedido (uma por linha, em JSON) e chama a função dada."""
        self.chamadas = self.chamadas + 1
        pendencias = []
        for linha in pedido.splitlines():
            if linha.strip().startswith("{"):
                pendencias.append(json.loads(linha))
        return self.responder(pendencias)


def responde_para_cada(frase_de):
    """Uma função de resposta que escreve, para cada pendência, a frase que frase_de(pendência) devolver."""
    def responder(pendencias):
        """Monta o JSON do contrato com uma pergunta por pendência."""
        perguntas = []
        for pendencia in pendencias:
            perguntas.append({"id": pendencia["id"], "pergunta": frase_de(pendencia)})
        return json.dumps({"perguntas": perguntas}, ensure_ascii=False)
    return responder


def boa(pendencia) -> str:
    """Uma frase boa: curta, com o valor lido e uma pergunta só."""
    return f'Recebemos "{pendencia["valor_lido"]}" de {pendencia["pessoa"] or "uma pessoa"}. Qual é o valor correto?'


def pendencia_do_cpf(conexao) -> dict:
    """A pendência do CPF inválido da Aurora, como a lista de Acompanhar mostra."""
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, "EMP001"):
        if pendencia["regra_id"] == "CPF_INVALIDO":
            return pendencia
    raise AssertionError("a Aurora devia ter o CPF inválido")


def pergunta_do_cpf(conexao, cliente) -> str:
    """A pergunta do CPF inválido na lista de Acompanhar, pedida com o cliente dado."""
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, "EMP001", cliente=cliente):
        if pendencia["regra_id"] == "CPF_INVALIDO":
            return pendencia["pergunta"]
    raise AssertionError("a Aurora devia ter o CPF inválido")


def execucoes_das_perguntas(conexao, processamento_id: str) -> list[dict]:
    """As execuções da escrita das perguntas na Telemetria."""
    lista = []
    for execucao in execucoes.listar(conexao, processamento_id):
        if execucao["etapa"] == perguntas_das_pendencias.ETAPA:
            lista.append(execucao)
    return lista


def test_resposta_boa_aparece_e_fica_guardada(conexao):
    processamento_id, _ = aurora_com_o_cpf_errado(conexao)
    ia = IaFalsa(responde_para_cada(boa))
    primeira = pergunta_do_cpf(conexao, ia.cliente())
    assert primeira.startswith("Recebemos ") and primeira.endswith("Qual é o valor correto?")
    # Guardada: abrir de novo não chama a IA, e a pergunta é a mesma
    chamadas = ia.chamadas
    assert pergunta_do_cpf(conexao, ia.cliente()) == primeira and ia.chamadas == chamadas
    # A mesma pergunta na conferência do Cadastrar (o mesmo envio, sem nova chamada)
    em_cadastrar = None
    for linha in cadastro.lista_para_conferir(conexao, "EMP001", processamento_id, cliente=ia.cliente())["linhas"]:
        for item in linha["pendencias"]:
            if item["regra_id"] == "CPF_INVALIDO":
                em_cadastrar = item["pergunta"]
    assert em_cadastrar == primeira and ia.chamadas == chamadas
    # A chamada ficou na Telemetria, com a versão do prompt
    execucao = execucoes_das_perguntas(conexao, processamento_id)[0]
    assert execucao["status"] == execucoes.OK and execucao["versao_prompt"] == redator_de_perguntas.VERSAO_PROMPT


@pytest.mark.parametrize("frase_ruim", [
    lambda pendencia: "Precisamos do CPF certo.",                                     # sem pergunta
    lambda pendencia: f'O cpf_funcionario veio "{pendencia["valor_lido"]}". Qual é?',  # nome técnico
    lambda pendencia: "O CPF veio errado. Qual é o certo?",                           # sem o valor lido
    lambda pendencia: f'Atenção! Veio "{pendencia["valor_lido"]}". Qual é?',          # exclamação
    lambda pendencia: f'Veio "{pendencia["valor_lido"]}". Qual é? Tem certeza?',       # duas perguntas
])
def test_resposta_ruim_cai_na_reserva_e_nao_e_guardada(conexao, frase_ruim):
    processamento_id, _ = aurora_com_o_cpf_errado(conexao)
    reserva = pendencia_do_cpf(conexao)["pergunta"]
    ia = IaFalsa(responde_para_cada(frase_ruim))
    assert pergunta_do_cpf(conexao, ia.cliente()) == reserva
    chave_do_cpf = None
    for chave in perguntas_das_pendencias.guardadas(conexao, processamento_id):
        if chave.startswith("CPF_INVALIDO|"):
            chave_do_cpf = chave
    # A do MOCK (a primeira carga) pode estar guardada; a ruim, nunca
    guardadas = perguntas_das_pendencias.guardadas(conexao, processamento_id)
    assert chave_do_cpf is None or guardadas[chave_do_cpf] == reserva


def test_ia_fora_do_ar_ou_fora_do_formato_cai_na_reserva(conexao, monkeypatch):
    processamento_id, _ = aurora_com_o_cpf_errado(conexao)
    # Nada guardado ainda: cada carga chama a IA
    monkeypatch.setattr(perguntas_das_pendencias, "guardadas", lambda conexao_da_lista, envio: {})
    reserva = pendencia_do_cpf(conexao)["pergunta"]

    def falha(pendencias):
        """A IA fora do ar."""
        raise RuntimeError("provedor fora do ar")
    assert pergunta_do_cpf(conexao, IaFalsa(falha).cliente()) == reserva
    assert pergunta_do_cpf(conexao, IaFalsa(lambda pendencias: "não sei").cliente()) == reserva
    # As duas falhas estão na Telemetria
    tipos_de_erro = []
    for execucao in execucoes_das_perguntas(conexao, processamento_id):
        if execucao["status"] == execucoes.ERRO:
            tipos_de_erro.append(execucao["tipo_erro"])
    assert "RuntimeError" in tipos_de_erro and "RespostaForaDoContrato" in tipos_de_erro


def test_ia_lenta_nao_segura_a_lista(conexao, monkeypatch):
    processamento_id, _ = aurora_com_o_cpf_errado(conexao)
    monkeypatch.setattr(perguntas_das_pendencias, "guardadas", lambda conexao_da_lista, envio: {})
    monkeypatch.setattr(redator_de_perguntas, "LIMITE_DE_SEGUNDOS", 0.2)
    reserva = pendencia_do_cpf(conexao)["pergunta"]

    def lenta(pendencias):
        """A IA que demora mais que o limite."""
        time.sleep(1)
        return responde_para_cada(boa)(pendencias)
    inicio = time.monotonic()
    assert pergunta_do_cpf(conexao, IaFalsa(lenta).cliente()) == reserva
    assert time.monotonic() - inicio < 5
    tipos_de_erro = []
    for execucao in execucoes_das_perguntas(conexao, processamento_id):
        tipos_de_erro.append(execucao["tipo_erro"])
    assert "TempoEsgotado" in tipos_de_erro


def test_valor_lido_mudado_escreve_de_novo(conexao):
    processamento_id, pendencia = aurora_com_o_cpf_errado(conexao)
    ia = IaFalsa(responde_para_cada(boa))
    antes = pergunta_do_cpf(conexao, ia.cliente())
    chamadas = ia.chamadas
    # A empresa troca o CPF por outro que ainda não passa: o valor lido mudou
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, pendencia["linha"], "cpf",
                                      "123.456.789-00", "conferido no documento")
    depois = pergunta_do_cpf(conexao, ia.cliente())
    assert ia.chamadas == chamadas + 1 and '"123.456.789-00"' in depois and depois != antes


def test_no_mock_a_ia_simulada_escreve_a_reserva(conexao):
    aurora_com_o_cpf_errado(conexao)
    pendencia = pendencia_do_cpf(conexao)
    assert pendencia["pergunta"] == (f'O CPF de {pendencia["nome"].split()[0]} veio "{pendencia["valor_lido"]}", e o '
                                     "dígito verificador não bate. Qual é o CPF certo?")


def test_os_dois_prompts_usam_a_mesma_diretriz_de_tom_de_voz():
    diretriz = tom_de_voz.diretriz()
    assert "Sério, cordial, direto e profissional" in diretriz and "sem ponto de exclamação" in diretriz
    sistema_das_perguntas, _ = redator_de_perguntas.carregar_prompt()
    assert diretriz in sistema_das_perguntas and "{tom_de_voz}" not in sistema_das_perguntas
    sistema_da_conversa = assistente_correcao._sistema()
    assert diretriz in sistema_da_conversa and "{tom_de_voz}" not in sistema_da_conversa


def test_a_conferencia_da_frase():
    pendencia = redator_de_perguntas.PendenciaParaEscrever(
        id="x", regra="VALOR_NAO_CONVERTIDO", gravidade="ALERTA", pessoa="Diego", informacao="Estado civil",
        valor_lido="Solteiro(a)", o_que_aconteceu="fora da lista", tipo="confirmar", palpite="Solteiro")
    assert redator_de_perguntas.conferir_pergunta(
        'No estado civil de Diego veio "Solteiro(a)". Posso usar "Solteiro"?', pendencia)
    # Sem o palpite, longa demais, ou sem texto: fora
    assert not redator_de_perguntas.conferir_pergunta('Veio "Solteiro(a)". Qual é o certo?', pendencia)
    assert not redator_de_perguntas.conferir_pergunta('Veio "Solteiro(a)", "Solteiro"' + " x" * 200 + "?", pendencia)
    assert not redator_de_perguntas.conferir_pergunta(None, pendencia)


def test_a_conferencia_da_frase_de_uma_informacao_de_cada_pessoa():
    """A coluna que falta de uma informação única por funcionário (o CPF): a frase da IA precisa dizer "única por
    funcionário" (prompt pergunta_da_pendencia_v4, ADR-153); a que pede um valor para todos, ou que ainda diz "de cada
    pessoa", cai na reserva."""
    pendencia = redator_de_perguntas.PendenciaParaEscrever(
        id="x", regra="OBRIGATORIO_SEM_COLUNA", gravidade="BLOQUEANTE", pessoa="", informacao="CPF", valor_lido="",
        o_que_aconteceu="O arquivo não traz este dado para nenhum funcionário, e ele é de cada pessoa.",
        tipo="corrigir", igual_para_todos=False)
    assert not redator_de_perguntas.conferir_pergunta(
        "Nenhum funcionário veio com o CPF. Se for o mesmo para todos, qual é?", pendencia)
    # O jeito antigo de dizer não passa mais
    assert not redator_de_perguntas.conferir_pergunta(
        "O arquivo veio sem o CPF, que é de cada pessoa. Quer enviar o arquivo de novo com essa coluna?", pendencia)
    assert redator_de_perguntas.conferir_pergunta(
        "O arquivo veio sem a informação CPF, que é única por funcionário. Quer enviar o arquivo de novo com essa "
        "coluna?", pendencia)
    # "Único por funcionário" (no masculino) também passa
    assert redator_de_perguntas.conferir_pergunta(
        "O CPF é único por funcionário e não veio no arquivo. Quer informar pessoa a pessoa?", pendencia)


def test_a_pergunta_guardada_antes_da_regra_de_cada_pessoa_nao_volta():
    """A pergunta da coluna do CPF guardada quando ela ainda pedia um valor para todos tem outra chave: não volta."""
    achado = validador.Achado("OBRIGATORIO_SEM_COLUNA", validador.BLOQUEANTE, "Sem a coluna.", "Enviar de novo",
                              campo="cpf")
    chave_de_antes = acompanhamento.chave_da_pergunta(achado, None)
    chave_de_agora = acompanhamento.chave_da_pergunta(achado, None, igual_para_todos=False)
    assert chave_de_antes != chave_de_agora
