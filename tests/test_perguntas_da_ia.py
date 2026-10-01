"""As perguntas da IA viram pendências presas à pessoa e ao campo, resolvidas na conferência (ADR-73, tela).

O que se prova aqui:
    - cada pergunta do Leitor de Documentos vira um ALERTA na linha e no campo da pessoa;
    - a lista para conferir traz as pendências de cada linha e os contadores (para milhares de linhas);
    - corrigir o campo responde a pergunta (ela some);
    - "Está certo assim" confirma a pergunta, com quem confirmou, e ela deixa de contar;
    - corrigir um campo só responde a pergunta daquele campo (as outras da mesma pessoa continuam).
"""
from types import SimpleNamespace

import pytest

from services import acompanhamento, banco, cadastro, ingestao, validador
from tests.apoio_do_parametro import marcar_como_obrigatorios  # o parâmetro de um teste (ADR-143)
from tests.test_correcao import busca_falsa
from tests.test_leitura_de_word import TEXTO_CORRIDO, documento_word

# A linha da Beatriz na tabela montada (cabeçalho na linha 1; Maria 2, João 3, Beatriz 4)
LINHA_DA_BEATRIZ = 4
# Um CPF válido e fictício para a correção
CPF_NOVO = "123.456.789-09"


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def enviar_e_aceitar(conexao) -> str:
    """Envia o Word de texto corrido e aceita as colunas: o envio chega à conferência. Devolve o processamento_id."""
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", documento_word(TEXTO_CORRIDO), "novos.docx",
                                      busca=busca_falsa)
    processamento_id = leitura["processamento_id"]
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", processamento_id, {}, busca=busca_falsa)
    return processamento_id


def pendencias_da_linha(lista: dict, linha: int) -> list[dict]:
    """As pendências de uma linha da lista para conferir."""
    for item in lista["linhas"]:
        if item["linha"] == linha:
            return item["pendencias"]
    raise KeyError(linha)


def pergunta_da_ia(pendencias: list[dict]) -> dict | None:
    """A primeira pendência que é pergunta da IA (ou None)."""
    for pendencia in pendencias:
        if pendencia["pergunta_da_ia"]:
            return pendencia
    return None


def test_a_conversa_conta_so_as_perguntas_que_a_empresa_responde(conexao):
    """A conversa do Cadastrar diz quantas perguntas da IA a empresa responde: a pergunta sobre um campo opcional não
    vira pendência (ADR-143) e não entra na conta, e o número bate com o da conferência."""
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", documento_word(TEXTO_CORRIDO), "novos.docx",
                                      busca=busca_falsa)
    # A pergunta sobre o CPF da Beatriz: o CPF é obrigatório, e ela conta
    assert leitura["perguntas_da_ia"] == 1
    # Num parâmetro de teste com o CPF opcional, a mesma pergunta não conta
    marcar_como_obrigatorios(conexao, "valor_renda", "data_admissao", so_estes=True)
    assert cadastro.leitura_do_envio(conexao, "EMP001", leitura["processamento_id"])["perguntas_da_ia"] == 0


def test_a_pergunta_sobre_a_pessoa_toda_sempre_conta(conexao):
    """A pergunta sem campo (sobre a pessoa toda) não é de um campo opcional: conta. A do nome da mãe (opcional no
    layout) não conta; a do CPF (obrigatório) conta."""
    perfil = SimpleNamespace(perguntas_da_ia=[{"linha": 2, "campo": "cpf", "pergunta": "É este o CPF?"},
                                              {"linha": 2, "campo": "nome_mae", "pergunta": "É a mãe?"},
                                              {"linha": 3, "campo": None, "pergunta": "É uma pessoa só?"}])
    assert cadastro._perguntas_da_ia_para_responder(conexao, perfil) == 2


def test_pergunta_da_ia_vira_alerta_na_linha_e_no_campo(conexao):
    processamento_id = enviar_e_aceitar(conexao)
    relatorio = validador.obter(conexao, processamento_id)
    perguntas = []
    for achado in relatorio.achados:
        if achado.regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA):
            perguntas.append(achado)
    assert len(perguntas) == 1
    assert perguntas[0].regra_id == "PERGUNTA_DA_IA:cpf" and perguntas[0].severidade == validador.ALERTA
    assert perguntas[0].linha == LINHA_DA_BEATRIZ and perguntas[0].campo == "cpf"


def test_lista_para_conferir_traz_pendencias_por_linha_e_contadores(conexao):
    processamento_id = enviar_e_aceitar(conexao)
    lista = cadastro.lista_para_conferir(conexao, "EMP001", processamento_id)
    pendencias = pendencias_da_linha(lista, LINHA_DA_BEATRIZ)
    pergunta = pergunta_da_ia(pendencias)
    # O CPF da Beatriz está vazio e é obrigatório: há o que corrigir, e a pergunta da IA vira a explicação disso
    assert any(pendencia["tipo"] == "corrigir" and pendencia["campo"] == "cpf" for pendencia in pendencias)
    assert pergunta is not None and pergunta["tipo"] == "explicacao" and pergunta["campo"] == "cpf"
    contagem = lista["contagem"]
    assert contagem["linhas"] == 3 and contagem["perguntas_da_ia"] == 1 and contagem["confirmar"] == 0
    assert contagem["linhas_com_pendencia"] >= 1 and contagem["corrigir"] >= 1


def test_corrigir_o_campo_responde_a_pergunta(conexao):
    processamento_id = enviar_e_aceitar(conexao)
    lista = cadastro.corrigir_na_conferencia(conexao, "EMP001", "rh.teste", processamento_id, LINHA_DA_BEATRIZ, "cpf",
                                             CPF_NOVO)
    assert pergunta_da_ia(pendencias_da_linha(lista, LINHA_DA_BEATRIZ)) is None
    assert lista["contagem"]["perguntas_da_ia"] == 0


def test_esta_certo_assim_confirma_a_pergunta(conexao):
    processamento_id = enviar_e_aceitar(conexao)
    lista = cadastro.confirmar_na_conferencia(conexao, "EMP001", "rh.teste", processamento_id, "PERGUNTA_DA_IA:cpf",
                                              LINHA_DA_BEATRIZ, "")
    assert pergunta_da_ia(pendencias_da_linha(lista, LINHA_DA_BEATRIZ)) is None
    # A confirmação fica no relatório, marcada como resolvida
    resolvidas = []
    for achado in validador.obter(conexao, processamento_id).achados:
        if achado.regra_id == "PERGUNTA_DA_IA:cpf":
            resolvidas.append(achado.resolvido)
    assert resolvidas == ["CONFIRMADO"]


def test_corrigir_um_campo_so_responde_a_pergunta_daquele_campo():
    """Duas perguntas na mesma linha: corrigir o CPF responde só a do CPF."""
    perguntas = [{"linha": 2, "campo": "cpf", "pergunta": "Qual é o CPF?"},
                 {"linha": 2, "campo": "data_admissao", "pergunta": "Qual das duas datas?"}]
    corrigidos = {(2, "cpf")}
    abertas = validador.perguntas_em_aberto(perguntas, corrigidos)
    assert abertas == [perguntas[1]]


def test_depois_de_descartar_o_mesmo_arquivo_vira_um_envio_novo(conexao):
    """A empresa descartou a leitura: mandar o mesmo arquivo de novo cria outro envio (não reabre o descartado)."""
    # Os mesmos bytes nas duas vezes (a mesma impressão digital)
    conteudo = documento_word(TEXTO_CORRIDO)
    primeiro = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", conteudo, "novos.docx", busca=busca_falsa)
    # Antes de descartar, o mesmo arquivo reabre o mesmo envio
    repetido = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", conteudo, "novos.docx", busca=busca_falsa)
    assert repetido["duplicado"] is True
    cadastro.descartar(conexao, "EMP001", primeiro["processamento_id"], "rh.aurora")
    segundo = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", conteudo, "novos.docx", busca=busca_falsa)
    assert segundo["duplicado"] is False and segundo["processamento_id"] != primeiro["processamento_id"]


def test_acompanhar_junta_a_pergunta_da_ia_ao_cartao_de_correcao(conexao):
    """Em "Acompanhar cadastros", o CPF vazio da Beatriz e a pergunta da IA viram um cartão só, de corrigir."""
    enviar_e_aceitar(conexao)
    pendencias = acompanhamento.pendencias_da_empresa(conexao, "EMP001")
    do_cpf_da_beatriz = []
    for pendencia in pendencias:
        if pendencia["linha"] == LINHA_DA_BEATRIZ and pendencia["campo"] == "cpf":
            do_cpf_da_beatriz.append(pendencia)
    assert len(do_cpf_da_beatriz) == 1
    cartao = do_cpf_da_beatriz[0]
    assert cartao["tipo"] == "corrigir" and cartao["obrigatorio"] is True
    assert cartao["explicacao_da_ia"] and "CPF" in cartao["explicacao_da_ia"]


# ---------- A lista pendente da empresa: o cruzamento entre envios (ADR-74) ----------

# Um segundo e-mail de RH: a Maria de novo (mesmo CPF) e uma pessoa nova
SEGUNDO_TEXTO = [
    "Oi! Mais duas admissões.",
    "A Maria Conceição Souza, CPF 529.982.247-25, entrou em 05/03/2026 como analista de sistemas.",
    "O Carlos Alberto Nunes, CPF 123.456.789-09, começou em 20/03/2026 como vendedor, salário de R$ 2.500,00.",
]


def enviar_e_aceitar_texto(conexao, paragrafos) -> str:
    """Envia um Word com os parágrafos e aceita as colunas. Devolve o processamento_id."""
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", documento_word(paragrafos), "outro.docx",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", leitura["processamento_id"], {}, busca=busca_falsa)
    return leitura["processamento_id"]


def regras_do_envio(conexao, processamento_id: str) -> set[str]:
    """Os códigos das regras que acharam algo no envio."""
    regras = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        regras.add(achado.regra_id)
    return regras


def test_mesma_pessoa_em_dois_envios_vira_pendencia_nos_dois_e_some_quando_sai_de_um(conexao):
    primeiro = enviar_e_aceitar(conexao)
    segundo = enviar_e_aceitar_texto(conexao, SEGUNDO_TEXTO)
    # A Maria está nos dois: pendência nos dois envios (o primeiro foi validado de novo quando o segundo chegou)
    assert "PESSOA_EM_OUTRO_ENVIO" in regras_do_envio(conexao, primeiro)
    assert "PESSOA_EM_OUTRO_ENVIO" in regras_do_envio(conexao, segundo)
    # A empresa tira a Maria do segundo envio ("Não cadastrar esta pessoa"): a pendência some dos dois
    # (na tabela montada do segundo arquivo, a Maria é a primeira pessoa: linha 2, depois do cabeçalho)
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh.teste", segundo, 2, "__excluir__", "",
                                      "A Maria já está no outro envio")
    assert "PESSOA_EM_OUTRO_ENVIO" not in regras_do_envio(conexao, primeiro)
    assert "PESSOA_EM_OUTRO_ENVIO" not in regras_do_envio(conexao, segundo)


def test_arquivo_sem_ninguem_novo_e_recusado(conexao):
    enviar_e_aceitar(conexao)
    # Outro texto, com a Maria e o João de novo (já estão no envio pendente): nada novo
    repetido = ["Reenviando os dados:", TEXTO_CORRIDO[1], TEXTO_CORRIDO[2]]
    with pytest.raises(ingestao.ArquivoRecusado, match="Nada novo para enviar"):
        cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", documento_word(repetido), "de_novo.docx",
                                busca=busca_falsa)
