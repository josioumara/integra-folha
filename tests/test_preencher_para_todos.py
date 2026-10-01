""""Preencher para todos": um campo que o documento não traz recebe o mesmo valor em quem está sem ele.

O que estes testes provam:
- o campo obrigatório sem coluna no arquivo (ex.: o CNPJ do empregador) vira UMA pendência, que some depois de a
  empresa digitar o valor uma vez; o valor passa pelas regras do Validador (a regra do CNPJ, por exemplo);
- quem já tem o dado não muda (o documento continua valendo, decisão 6); só quem está sem ele é preenchido;
- cada funcionário preenchido vira uma correção aplicada, com quem clicou, e a trilha registra quantos (sem o valor);
- valor que não pode ser padronizado, sem motivo, ninguém sem o campo e envio de outra empresa são recusados;
- uma informação de cada pessoa (o CPF) nunca recebe um valor para todos.
"""
from datetime import date

import pytest

from services import acompanhamento, auditoria, banco, correcoes, mapeamentos, normalizador, processamentos, validador
from tests.test_correcao import (ENVIOS, _decisoes_da_matricula, _escolhas_do_gabarito, _gabarito, busca_falsa,
                                 preparar_ate_a_validacao)

# O CNPJ principal da Aurora (EMP001)
CNPJ_DA_AURORA = "10433218000193"


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


@pytest.fixture(autouse=True)
def usar_busca_falsa(monkeypatch):
    """Nenhum uso do RAG depende do índice nem do modelo de embeddings."""
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def envio_sem_a_coluna(conexao, campo_ignorado: str) -> str:
    """O envio da Aurora com a coluna de um campo ignorada no aceite (como um Word que não fala dele).

    Recebe: conexao; o campo cuja coluna fica de fora (ex.: "cnpj_empregador"). Devolve: o processamento_id, já
    padronizado e validado.
    """
    gabarito = _gabarito("aurora_carga_inicial")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    recebido = processamentos.receber_arquivo(conexao, conteudo, gabarito["arquivo"], "EMP001", date(2026, 9, 1),
                                              "empresa.teste")
    processamento_id = recebido.perfil.processamento_id
    mapeamentos.interpretar_processamento(conexao, processamento_id, "EMP001")
    escolhas = _escolhas_do_gabarito(gabarito)
    # A coluna do campo fica de fora
    for coluna, campo in gabarito["mapeamento"].items():
        if campo == campo_ignorado:
            escolhas[coluna] = mapeamentos.IGNORAR
    mapeamentos.aprovar(conexao, processamento_id, "EMP001", escolhas, "empresa.teste")
    normalizador.executar(conexao, processamento_id, "EMP001", _decisoes_da_matricula(gabarito))
    validador.executar(conexao, processamento_id, "EMP001")
    return processamento_id


def envio_sem_a_coluna_do_cnpj(conexao) -> str:
    """O envio da Aurora sem a coluna do CNPJ do empregador (um dado da empresa). Devolve: o processamento_id."""
    return envio_sem_a_coluna(conexao, "cnpj_empregador")


def regras_do_campo(conexao, processamento_id: str, campo: str) -> set:
    """As regras com achados no campo, no último relatório do envio."""
    regras = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        if achado.campo == campo:
            regras.add(achado.regra_id)
    return regras


def test_campo_que_o_arquivo_nao_traz_e_preenchido_para_todos(conexao):
    """Uma pendência do arquivo inteiro; um valor; todos preenchidos; a pendência some."""
    processamento_id = envio_sem_a_coluna_do_cnpj(conexao)
    assert regras_do_campo(conexao, processamento_id, "cnpj_empregador") == {"OBRIGATORIO_SEM_COLUNA"}
    total = len(correcoes.dados_atuais(conexao, processamento_id).registros)
    quantidade = acompanhamento.preencher_para_todos(conexao, "EMP001", "rh.aurora", processamento_id,
                                                     "cnpj_empregador", "10.433.218/0001-93", "CNPJ da empresa")
    assert quantidade == total
    assert regras_do_campo(conexao, processamento_id, "cnpj_empregador") == set()
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        assert registro["cnpj_empregador"] == CNPJ_DA_AURORA
    # Uma correção aplicada por funcionário, com quem clicou; a trilha diz quantos, sem o valor
    aplicadas = correcoes.listar(conexao, processamento_id, "APLICADA")
    assert len(aplicadas) == total and aplicadas[0].aprovada_por == "rh.aurora"
    detalhes_do_evento = []
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "CORRECAO_PARA_TODOS":
            detalhes_do_evento.append(evento["detalhe"])
    assert detalhes_do_evento == [{"campo": "cnpj_empregador", "quantidade": total}]
    # De novo: ninguém mais está sem o campo
    with pytest.raises(ValueError, match="Nenhum funcionário"):
        acompanhamento.preencher_para_todos(conexao, "EMP001", "rh.aurora", processamento_id, "cnpj_empregador",
                                            CNPJ_DA_AURORA, "de novo")


def test_valor_de_outra_empresa_passa_pela_regra_do_cnpj(conexao):
    """O valor preenchido não escapa das regras: CNPJ de outra raiz em todos vira a pergunta "é do grupo?"."""
    processamento_id = envio_sem_a_coluna_do_cnpj(conexao)
    acompanhamento.preencher_para_todos(conexao, "EMP001", "rh.aurora", processamento_id, "cnpj_empregador",
                                        "88805929000139", "CNPJ informado")
    assert regras_do_campo(conexao, processamento_id, "cnpj_empregador") == {validador.REGRA_CNPJ_DO_GRUPO}


def test_quem_ja_tem_o_dado_nao_muda(conexao):
    """Só quem está sem o campo é preenchido; os valores do documento continuam."""
    processamento_id = preparar_ate_a_validacao(conexao, "aurora_carga_inicial")
    registros = correcoes.dados_atuais(conexao, processamento_id).registros
    valores_antes = {}
    for registro in registros:
        valores_antes[registro["_linha"]] = registro["nome_unidade"]
    # A empresa apaga a unidade de uma pessoa
    primeira_linha = registros[0]["_linha"]
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, primeira_linha,
                                      "nome_unidade", "", "teste")
    quantidade = acompanhamento.preencher_para_todos(conexao, "EMP001", "rh.aurora", processamento_id,
                                                     "nome_unidade", "Fábrica Campinas", "Unidade de todos")
    assert quantidade == 1
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] == primeira_linha:
            assert registro["nome_unidade"] == "Fábrica Campinas"
        else:
            assert registro["nome_unidade"] == valores_antes[registro["_linha"]]


def test_recusas(conexao):
    """Valor que não se padroniza, sem motivo, campo fora do layout e envio de outra empresa."""
    processamento_id = envio_sem_a_coluna_do_cnpj(conexao)
    casos = [("cnpj_empregador", "", "motivo", ValueError, "Digite"),
             ("cnpj_empregador", "123", "", ValueError, "motivo"),
             ("campo_que_nao_existe", "x", "motivo", ValueError, "não existe"),
             ("data_referencia_renda", "trinta de fevereiro", "motivo", ValueError, None)]
    for campo, valor, motivo, erro, mensagem in casos:
        with pytest.raises(erro, match=mensagem):
            acompanhamento.preencher_para_todos(conexao, "EMP001", "rh.aurora", processamento_id, campo, valor,
                                                motivo)
    with pytest.raises(KeyError):
        acompanhamento.preencher_para_todos(conexao, "EMP002", "rh.horizonte", processamento_id, "cnpj_empregador",
                                            CNPJ_DA_AURORA, "motivo")
    # Nada foi gravado
    assert correcoes.listar(conexao, processamento_id) == []


def test_informacao_de_cada_pessoa_nunca_recebe_um_valor_para_todos(conexao):
    """O CPF é sempre único (ADR-124). Sem a coluna do CPF, o valor para todos é recusado, nada
    muda e a pendência continua: só um arquivo novo, com a coluna, resolve."""
    processamento_id = envio_sem_a_coluna(conexao, "cpf")
    assert "OBRIGATORIO_SEM_COLUNA" in regras_do_campo(conexao, processamento_id, "cpf")
    with pytest.raises(ValueError, match="única por funcionário"):
        acompanhamento.preencher_para_todos(conexao, "EMP001", "rh.aurora", processamento_id, "cpf",
                                            "529.982.247-25", "O mesmo para todos")
    # Nada foi gravado, e a pendência continua
    assert correcoes.listar(conexao, processamento_id) == []
    assert "OBRIGATORIO_SEM_COLUNA" in regras_do_campo(conexao, processamento_id, "cpf")
