"""O pedido do especialista do banco num campo opcional, do apontamento à volta ao banco (ADR-121, exceção da ADR-143).

Desde a ADR-143, um campo opcional (o nome, o cargo...) não abre pendência automática. O pedido explícito do
especialista é a exceção: ele vira a pendência da pessoa devolvida, com o recado dele, também num campo opcional.

O que estes testes provam, com o parâmetro em que o nome e o cargo são opcionais:
- o banco aponta uma pessoa pelo nome e outra pelo salário e escolhe "aprovar os outros e devolver os marcados": as 2
  pendências aparecem para a empresa, com o selo e as palavras do especialista;
- a empresa corrige o nome: a pendência some, o envio volta ao banco, e o banco lê "A empresa corrigiu" com o antes e
  o depois; o nome corrigido segue no cadastro;
- o cargo apontado: a empresa responde "Está certo assim", e o banco lê a resposta;
- o cargo que chegou em branco ao banco: a empresa preenche, a pendência some, e o banco lê o que ela preencheu.
"""
from models.contratos import EstadoProcessamento
from services import acompanhamento, avaliacao_do_banco, correcoes, processamentos
from tests.apoio_do_parametro import OBRIGATORIOS_DA_ADR_143, marcar_como_obrigatorios
from tests.test_avaliacao_do_banco import ESPECIALISTA
from tests.test_correcao import busca_falsa
from tests.test_fluxo_empresa import (aprovar, conexao, corrigir_cpf_da_aurora, gerar_envios, iniciar,  # noqa: F401
                                      receber, verdade)
from workflows import fluxo_empresa as fluxo

# Os recados que o especialista escreve nos testes
RECADO_DO_NOME = "O nome parece incompleto, falta o sobrenome. Pode conferir?"
RECADO_DO_SALARIO = "O salário parece alto demais para o cargo. Pode conferir?"
RECADO_DO_CARGO = "O cargo não confere com a profissão informada. Pode conferir?"


def _a_aurora_no_banco_com_o_nome_e_o_cargo_opcionais(conexao, verdade, cargo_em_branco: bool = False) -> str:
    """A Aurora vai ao banco com o parâmetro em que só o CPF, a renda e a admissão são obrigatórios.

    Recebe: cargo_em_branco — True: a empresa deixa em branco o cargo da primeira pessoa antes de enviar (o cargo é
    opcional, e o envio segue). Devolve: o processamento_id do envio que espera o banco.
    """
    # O parâmetro da ADR-143 (os obrigatórios que existem no layout_v1): o nome e o cargo ficam opcionais
    marcar_como_obrigatorios(conexao, *OBRIGATORIOS_DA_ADR_143, so_estes=True)
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    # O cargo em branco: a empresa tira o dado opcional da primeira pessoa (o caminho da conversa, confirmado)
    if cargo_em_branco:
        primeira_linha = correcoes.dados_atuais(conexao, processamento_id).registros[0]["_linha"]
        retirada = correcoes.propor(conexao, processamento_id, empresa_id, primeira_linha, "cargo", None,
                                    "Não sabemos o cargo desta pessoa", "rh")
        correcoes.decidir(conexao, processamento_id, empresa_id, retirada.correcao_id, True, "rh")
    fluxo.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao", {"acao": "homologar", "usuario": "rh"},
                    busca=busca_falsa)
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.AGUARDANDO_BANCO
    return processamento_id


def _primeiras_linhas(conexao, processamento_id: str, quantas: int) -> list[int]:
    """As linhas das primeiras pessoas do envio, como o especialista vê."""
    linhas = []
    for pessoa in avaliacao_do_banco.pessoas_do_envio(conexao, ESPECIALISTA, processamento_id)[:quantas]:
        linhas.append(pessoa["linha"])
    return linhas


def _apontar_e_devolver(conexao, processamento_id: str, apontamentos: list[tuple[int, str, str]]) -> str:
    """O especialista aponta cada (linha, motivo, recado) e aprova os outros. Devolve o envio de devolução."""
    for linha, motivo, recado in apontamentos:
        avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, linha, motivo, recado)
    envio = avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, decisao="aprovar_e_devolver_marcados")
    return envio["envio_de_devolucao"]


def _pendencias_do_banco(conexao) -> dict[int, dict]:
    """As pendências da empresa em Acompanhar, pela linha da pessoa; todas têm de ser pedidos do banco."""
    por_linha = {}
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, "EMP001"):
        assert pendencia["pedido_do_banco"] is True
        por_linha[pendencia["linha"]] = pendencia
    return por_linha


def _mandar_de_novo_e_ler_as_respostas(conexao, processamento_id: str) -> list[dict]:
    """A empresa manda o envio de devolução de novo; devolve as respostas aos apontamentos, como o banco lê."""
    fluxo.responder(conexao, processamento_id, "EMP001", "aprovar_homologacao", {"acao": "homologar", "usuario": "rh"},
                    busca=busca_falsa)
    for envio in avaliacao_do_banco.fila_de_envios(conexao, ESPECIALISTA):
        if envio["id"] == processamento_id:
            assert envio["situacao"] == "aguardando"
            return envio["respostas_aos_apontamentos"]
    raise AssertionError("O envio não voltou ao banco: " + processamento_id)


def test_o_nome_e_o_salario_apontados_viram_duas_pendencias_e_o_nome_corrigido_volta_ao_banco(conexao, verdade):
    origem = _a_aurora_no_banco_com_o_nome_e_o_cargo_opcionais(conexao, verdade)
    linha_do_nome, linha_do_salario = _primeiras_linhas(conexao, origem, 2)
    devolucao = _apontar_e_devolver(conexao, origem, [(linha_do_nome, "nome", RECADO_DO_NOME),
                                                      (linha_do_salario, "salario", RECADO_DO_SALARIO)])
    # As 2 pessoas voltam à empresa, e as 2 pendências aparecem (antes, o nome opcional sumia), com o recado do banco
    pendencias = _pendencias_do_banco(conexao)
    assert set(pendencias) == {linha_do_nome, linha_do_salario}
    assert pendencias[linha_do_nome]["campo"] == "nome_completo"
    assert pendencias[linha_do_nome]["pergunta"] == "O banco pediu: " + RECADO_DO_NOME
    assert pendencias[linha_do_salario]["campo"] == "valor_renda"
    assert pendencias[linha_do_salario]["pergunta"] == "O banco pediu: " + RECADO_DO_SALARIO
    # A empresa corrige o nome: só a pendência do salário fica
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh", devolucao, linha_do_nome, "nome_completo",
                                      "Maria Aparecida dos Santos", "Nome completo conferido no RH")
    assert set(_pendencias_do_banco(conexao)) == {linha_do_salario}
    # E responde ao banco que o salário está certo: nada mais a responder
    pendencia_do_salario = _pendencias_do_banco(conexao)[linha_do_salario]
    acompanhamento.confirmar_pendencia(conexao, "EMP001", "rh", devolucao, pendencia_do_salario["regra_id"],
                                       linha_do_salario, "Está certo: é o salário de gerente.")
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP001") == []
    # O envio volta ao banco, que lê a correção do nome (o antes e o depois) e a resposta do salário
    respostas = _mandar_de_novo_e_ler_as_respostas(conexao, devolucao)
    textos = []
    for resposta in respostas:
        textos.append(resposta["resposta"])
    assert len(textos) == 2
    assert "A empresa respondeu: \"Está certo: é o salário de gerente.\"" in textos
    # A outra resposta é a correção do nome, com o nome novo
    textos.remove("A empresa respondeu: \"Está certo: é o salário de gerente.\"")
    assert textos[0].startswith("A empresa corrigiu") and textos[0].endswith("→ Maria Aparecida dos Santos")
    # O nome corrigido é o que segue no cadastro: o banco aprova, e a pessoa fica cadastrada com ele
    avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, devolucao, decisao="aprovar")
    assert processamentos.obter(conexao, devolucao).status == EstadoProcessamento.HOMOLOGADO
    nomes_cadastrados = set()
    for funcionario in acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001"):
        if funcionario["situacao"] == "Cadastrado":
            nomes_cadastrados.add(funcionario["nome_completo"])
    assert "Maria Aparecida dos Santos" in nomes_cadastrados


def test_o_cargo_apontado_vira_pendencia_e_a_empresa_responde_que_esta_certo(conexao, verdade):
    origem = _a_aurora_no_banco_com_o_nome_e_o_cargo_opcionais(conexao, verdade)
    linha_do_cargo = _primeiras_linhas(conexao, origem, 1)[0]
    devolucao = _apontar_e_devolver(conexao, origem, [(linha_do_cargo, "cargo", RECADO_DO_CARGO)])
    # A pendência do cargo opcional aparece, com o recado do banco
    pendencia = _pendencias_do_banco(conexao)[linha_do_cargo]
    assert pendencia["campo"] == "cargo" and pendencia["pergunta"] == "O banco pediu: " + RECADO_DO_CARGO
    # A empresa responde que está certo: o banco lê a resposta
    acompanhamento.confirmar_pendencia(conexao, "EMP001", "rh", devolucao, pendencia["regra_id"], linha_do_cargo,
                                       "Está certo: o cargo é este mesmo.")
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP001") == []
    respostas = _mandar_de_novo_e_ler_as_respostas(conexao, devolucao)
    assert [resposta["resposta"] for resposta in respostas] == ["A empresa respondeu: \"Está certo: o cargo é este mesmo.\""]


def test_o_cargo_em_branco_apontado_some_quando_a_empresa_preenche(conexao, verdade):
    # A primeira pessoa chega ao banco com o cargo em branco (opcional: ele não segura o envio)
    origem = _a_aurora_no_banco_com_o_nome_e_o_cargo_opcionais(conexao, verdade, cargo_em_branco=True)
    primeira_linha = correcoes.dados_atuais(conexao, origem).registros[0]["_linha"]
    assert correcoes.dados_atuais(conexao, origem).registros[0].get("cargo") in (None, "")
    devolucao = _apontar_e_devolver(conexao, origem, [(primeira_linha, "cargo", RECADO_DO_CARGO)])
    # A pendência aparece com o cargo em branco
    pendencia = _pendencias_do_banco(conexao)[primeira_linha]
    assert pendencia["campo"] == "cargo" and pendencia["valor_lido"] is None
    # A empresa preenche o cargo: a pendência some (antes, ela ficava, porque o valor apontado era o branco)
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh", devolucao, primeira_linha, "cargo", "Analista de RH",
                                      "Cargo conferido no RH")
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP001") == []
    # O banco lê o que a empresa preencheu, e não "Ainda sem resposta da empresa"
    respostas = _mandar_de_novo_e_ler_as_respostas(conexao, devolucao)
    assert [resposta["resposta"] for resposta in respostas] == ["A empresa corrigiu Cargo: (vazio) → Analista de RH"]
