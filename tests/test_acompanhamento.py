"""Testes de "Acompanhar cadastros" no novo front (ADR-69): serviço e rotas /api/empresa/...

O que se prova aqui:
    - os envios e os funcionários vêm do que a aplicação já guarda (processamentos e arquivos finais);
    - a Empresa A nunca vê a Empresa B, nem pelo serviço nem pela API (a empresa vem da sessão);
    - o CPF sai inteiro e formatado, e só saem os campos que a tela usa (nada de
      nome da mãe, PIS ou documento);
    - só o perfil EMPRESA consulta.
Os arquivos da demo são recebidos, corrigidos e homologados de verdade (os mesmos ajudantes do planejamento).
"""
import csv
import io
import re

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, auth, banco, contas_abertas, correcoes, homologacao, parametros, validador
from services.auth import Usuario
from tests.test_correcao import preparar_ate_a_validacao
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# O formato do CPF na tela: inteiro e formatado, "123.456.789-01"
FORMATO_DO_CPF_NA_TELA = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def test_formatar_cpf_mostra_o_cpf_inteiro_com_pontuacao():
    """A tela mostra o CPF inteiro: com e sem pontuação, o mesmo resultado."""
    assert acompanhamento.formatar_cpf("24681357954") == "246.813.579-54"
    assert acompanhamento.formatar_cpf("246.813.579-54") == "246.813.579-54"
    # Tamanho errado: volta como veio (a tela mostra o que a empresa mandou, para ela corrigir)
    assert acompanhamento.formatar_cpf("123") == "123"


def test_envio_homologado_aparece_como_cadastrado_com_quem_enviou(conexao, verdade):
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    envios = acompanhamento.envios_da_empresa(conexao, "EMP001")
    # Um envio, cadastrado, com a contagem do relatório da homologação
    assert len(envios) == 1
    assert envios[0]["situacao"] == "Cadastrado"
    assert envios[0]["cadastrados"] == homologacao.obter(conexao, processamento_id)["relatorio"]["registros_homologados"]
    assert envios[0]["enviado_por"] == "empresa.teste"
    assert envios[0]["tipo_carga"] == "INICIAL" and envios[0]["tipo"] == "Carga inicial"
    # O nome do arquivo aparece (ADR-120): um envio só, sem versão
    assert envios[0]["nome_arquivo"] == "aurora_carga_inicial.xlsx"


def test_funcionarios_saem_do_arquivo_final_com_cpf_formatado_e_so_os_campos_da_tela(conexao, verdade):
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    funcionarios = acompanhamento.funcionarios_da_empresa(conexao, "EMP001")
    # Tantos quantos a homologação registrou
    assert len(funcionarios) == homologacao.obter(conexao, processamento_id)["relatorio"]["registros_homologados"]
    for pessoa in funcionarios:
        # CPF inteiro e formatado
        assert FORMATO_DO_CPF_NA_TELA.match(pessoa["cpf"])
        # Todos os campos do parâmetro vigente (ADR-111: a empresa confere tudo o que enviou), mais os da consulta e as
        # informações sem rótulo, só para o detalhe (ADR-143, Parte 1)
        campos_do_parametro = set(acompanhamento.campos_para_a_empresa(conexao))
        assert set(pessoa) == campos_do_parametro | {"incluido_em", "incluido_por", "tipo_de_envio", "id", "envio",
                                                     "conta_aberta_em", "codigo_banco", "agencia", "conta",
                                                     "situacao_da_conta", "informacoes_sem_rotulo"}
        assert "nome_mae" in pessoa and "nis_pis" in pessoa and "numero_documento" in pessoa
        # Sempre com nome e com quem incluiu
        assert pessoa["nome_completo"] and pessoa["incluido_por"] == "empresa.teste"
    # Ordenados por nome
    nomes = [pessoa["nome_completo"].lower() for pessoa in funcionarios]
    assert nomes == sorted(nomes)


def test_empresa_a_nunca_ve_funcionario_da_empresa_b(conexao, verdade):
    homologar(conexao, "aurora_carga_inicial", verdade)
    homologar(conexao, "brisa_carga_inicial", verdade)
    # Nomes de cada empresa
    nomes_da_aurora = {pessoa["nome_completo"] for pessoa in acompanhamento.funcionarios_da_empresa(conexao, "EMP001")}
    nomes_da_brisa = {pessoa["nome_completo"] for pessoa in acompanhamento.funcionarios_da_empresa(conexao, "EMP003")}
    # As duas listas existem e não se cruzam
    assert nomes_da_aurora and nomes_da_brisa
    assert not nomes_da_aurora & nomes_da_brisa
    # Os envios também são separados
    assert len(acompanhamento.envios_da_empresa(conexao, "EMP001")) == 1
    assert acompanhamento.envios_da_empresa(conexao, "EMP002") == []


def test_inclusao_nao_repete_quem_ja_estava_cadastrado(conexao, verdade):
    homologar(conexao, "brisa_carga_inicial", verdade)
    antes = len(acompanhamento.funcionarios_da_empresa(conexao, "EMP003"))
    inclusao = homologar(conexao, "brisa_inclusao", verdade)
    depois = acompanhamento.funcionarios_da_empresa(conexao, "EMP003")
    # A lista cresce exatamente o que a inclusão cadastrou
    cadastrados_na_inclusao = homologacao.obter(conexao, inclusao)["relatorio"]["registros_homologados"]
    assert len(depois) == antes + cadastrados_na_inclusao
    # Ninguém aparece duas vezes
    assert len({pessoa["nome_completo"] + pessoa["cpf"] for pessoa in depois}) == len(depois)


def test_resumo_conta_cadastrados_e_envio_em_andamento(conexao, verdade):
    homologar(conexao, "brisa_carga_inicial", verdade)
    # Um segundo envio que para antes da homologação
    preparar_ate_a_validacao(conexao, "brisa_inclusao")
    resumo = acompanhamento.resumo_da_empresa(conexao, "EMP003")
    assert resumo["envios"] == 2
    assert resumo["em_andamento"] == 1
    assert resumo["cadastrados"] == len(acompanhamento.funcionarios_da_empresa(conexao, "EMP003"))


def test_linha_do_tempo_de_envio_aprovado_espera_o_arquivo_de_contas(conexao, verdade):
    homologar(conexao, "aurora_carga_inicial", verdade)
    etapas = acompanhamento.envios_da_empresa(conexao, "EMP001")[0]["linha_do_tempo"]
    # Aprovado sem passar pelo banco (envio antigo): sem "Enviado ao banco"; as 4 primeiras feitas, com data
    assert [etapa["nome"] for etapa in etapas] == ["Arquivo carregado", "Lido pelos agentes", "Conferido por você",
                                                   "Aprovação das contas enviadas", "Contas abertas"]
    for etapa in etapas[:-1]:
        assert etapa["feito"] and etapa["quando"] and not etapa["atual"]
    # Sem o arquivo de contas do banco, a última é a atual e não tem número nenhum (nada é suposto)
    assert etapas[-1] == {"nome": "Contas abertas", "feito": False, "atual": True, "quando": None, "detalhe": None,
                          "parcial": False, "devolvido": False}


def test_contas_abertas_na_linha_do_tempo_vem_do_arquivo_do_banco(conexao, verdade):
    homologar(conexao, "aurora_carga_inicial", verdade)
    # O banco sobe o arquivo semanal com a conta de 3 funcionários do envio e confirma a baixa
    cpfs = []
    for (cpf,) in conexao.execute("SELECT cpf FROM funcionarios_homologados WHERE empresa_id = 'EMP001' ORDER BY cpf"):
        cpfs.append(cpf)
    # O layout fixo do arquivo de contas (ADR-149): cpf;status;agencia;conta;data_abertura, com a data em AAAA-MM-DD.
    # Aqui, contas novas (status 1)
    linhas = ["cpf;status;agencia;conta;data_abertura"]
    for cpf in cpfs[:3]:
        linhas.append(cpf + ";1;0001;" + cpf[-5:] + "-0;2026-09-24")
    especialista = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
    previa = contas_abertas.conferir_arquivo(conexao, especialista, "EMP001", "\n".join(linhas).encode("utf-8"),
                                             "semana.csv")
    contas_abertas.confirmar_baixa(conexao, especialista, previa["arquivo_id"])
    # A última etapa fica feita, mas parcial (verde clarinho), com a data da baixa e "3 de N contas (X%)"
    envio = acompanhamento.envios_da_empresa(conexao, "EMP001")[0]
    ultima = envio["linha_do_tempo"][-1]
    percentual = (100 * 3) // len(cpfs)
    assert ultima["nome"] == "Contas abertas" and ultima["feito"] and ultima["quando"] and not ultima["atual"]
    assert ultima["parcial"] is True
    assert ultima["detalhe"] == "3 de " + str(len(cpfs)) + " contas (" + str(percentual) + "%)"
    # Na semana seguinte chegam as contas de todos os outros: 100%, e a etapa deixa de ser parcial (verde cheio)
    # Os outros já eram correntistas (status 2): a conta que eles já tinham também conta na etapa
    linhas = ["cpf;status;agencia;conta;data_abertura"]
    for cpf in cpfs[3:]:
        linhas.append(cpf + ";2;0001;" + cpf[-5:] + "-0;2026-09-25")
    previa = contas_abertas.conferir_arquivo(conexao, especialista, "EMP001", "\n".join(linhas).encode("utf-8"),
                                             "semana2.csv")
    contas_abertas.confirmar_baixa(conexao, especialista, previa["arquivo_id"])
    ultima = acompanhamento.envios_da_empresa(conexao, "EMP001")[0]["linha_do_tempo"][-1]
    assert ultima["parcial"] is False
    assert ultima["detalhe"] == str(len(cpfs)) + " de " + str(len(cpfs)) + " contas (100%)"


def test_linha_do_tempo_mostra_onde_o_envio_parou(conexao):
    # Envio lido pela IA, mas com as colunas ainda não conferidas pela empresa
    preparar_ate_a_validacao(conexao, "horizonte_carga_inicial", aprovar=False)
    etapas = acompanhamento.envios_da_empresa(conexao, "EMP002")[0]["linha_do_tempo"]
    feitas = [etapa["nome"] for etapa in etapas if etapa["feito"]]
    atuais = [etapa["nome"] for etapa in etapas if etapa["atual"]]
    assert feitas == ["Arquivo carregado", "Lido pelos agentes"]
    assert atuais == ["Conferido por você"]


def test_pendencias_do_envio_em_aberto_com_nome_e_sem_cpf_inteiro(conexao, verdade):
    preparar_ate_a_validacao(conexao, "brisa_carga_inicial")
    pendencias = acompanhamento.pendencias_da_empresa(conexao, "EMP003")
    # O arquivo da demo tem pendências de propósito
    assert pendencias
    for pendencia in pendencias:
        assert pendencia["tipo"] in ("corrigir", "confirmar")
        assert pendencia["nome"] and pendencia["problema"] and pendencia["acao"]
    # Nenhum CPF inteiro da Brisa (do gabarito) aparece nas pendências
    texto_das_pendencias = str(pendencias)
    for pessoa in verdade.values():
        if pessoa["empresa_id"] == "EMP003":
            assert pessoa["cpf"] not in texto_das_pendencias
    # Outra empresa não vê estas pendências
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP001") == []


def test_envios_do_mesmo_segundo_saem_do_mais_recente_para_o_mais_antigo(conexao, verdade):
    # Os dois envios são criados em sequência rápida (podem cair no mesmo segundo)
    homologar(conexao, "brisa_carga_inicial", verdade)
    preparar_ate_a_validacao(conexao, "brisa_inclusao")
    tipos = [envio["tipo"] for envio in acompanhamento.envios_da_empresa(conexao, "EMP003")]
    assert tipos == ["Inclusão", "Carga inicial"]


def test_envio_cadastrado_nao_tem_pendencia(conexao, verdade):
    homologar(conexao, "brisa_carga_inicial", verdade)
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP003") == []


# ---------------- Resolver pendências pela tela ----------------

def pendencia_da_regra(conexao, empresa_id, regra_id):
    """A primeira pendência em aberto de uma regra (ou None)."""
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, empresa_id):
        if pendencia["regra_id"] == regra_id:
            return pendencia
    return None


def test_corrigir_pendencia_aplica_registra_quem_e_tira_a_pendencia(conexao):
    processamento_id = preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    pendencia = pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO")
    acompanhamento.corrigir_pendencia(conexao, "EMP002", "rh.horizonte", processamento_id, pendencia["linha"],
                                      pendencia["campo"], "15/03/2022", "Data conferida no contrato")
    # A pendência saiu (o envio foi validado de novo)
    assert pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO") is None
    # A correção ficou registrada: aplicada, com quem propôs e quem aprovou
    aplicadas = correcoes.listar(conexao, processamento_id, "APLICADA")
    assert len(aplicadas) == 1
    assert aplicadas[0].proposta_por == "rh.horizonte" and aplicadas[0].aprovada_por == "rh.horizonte"
    assert aplicadas[0].depois == "2022-03-15"


def test_corrigir_com_valor_que_nao_serve_recusa_e_mantem_a_pendencia(conexao):
    processamento_id = preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    pendencia = pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO")
    # Valor que não é data e correção sem motivo: os dois são recusados
    with pytest.raises(ValueError):
        acompanhamento.corrigir_pendencia(conexao, "EMP002", "rh", processamento_id, pendencia["linha"],
                                          pendencia["campo"], "ontem", "Data do contrato")
    with pytest.raises(ValueError):
        acompanhamento.corrigir_pendencia(conexao, "EMP002", "rh", processamento_id, pendencia["linha"],
                                          pendencia["campo"], "15/03/2022", "  ")
    # Nada mudou
    assert pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO") is not None
    assert correcoes.listar(conexao, processamento_id, "APLICADA") == []


def test_empresa_nao_corrige_nem_confirma_envio_de_outra(conexao):
    processamento_id = preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    pendencia = pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO")
    with pytest.raises(KeyError):
        acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, pendencia["linha"],
                                          pendencia["campo"], "15/03/2022", "Tentativa de outra empresa")
    with pytest.raises(KeyError):
        acompanhamento.confirmar_pendencia(conexao, "EMP001", "rh.aurora", processamento_id, "OBRIGATORIO_VAZIO",
                                           pendencia["linha"], "Tentativa de outra empresa")


def test_confirmar_alerta_com_justificativa_tira_a_pendencia(conexao):
    processamento_id = preparar_ate_a_validacao(conexao, "brisa_carga_inicial")
    pendencia = pendencia_da_regra(conexao, "EMP003", "RENDA_FORA_DO_CARGO")
    # Sem justificativa: recusado
    with pytest.raises(ValueError):
        acompanhamento.confirmar_pendencia(conexao, "EMP003", "rh.brisa", processamento_id, pendencia["regra_id"],
                                           pendencia["linha"], "")
    # Com justificativa: confirmado e fora da lista
    acompanhamento.confirmar_pendencia(conexao, "EMP003", "rh.brisa", processamento_id, pendencia["regra_id"],
                                       pendencia["linha"], "Diretora contratada em setembro")
    assert pendencia_da_regra(conexao, "EMP003", "RENDA_FORA_DO_CARGO") is None


def test_tirar_linha_repetida_resolve_a_pessoa_duplicada(conexao):
    processamento_id = preparar_ate_a_validacao(conexao, "prisma_carga_inicial")
    pendencia = pendencia_da_regra(conexao, "EMP005", "PESSOA_DUPLICADA")
    # Tirar a linha repetida é uma correção especial (EXCLUIR), com motivo
    acompanhamento.corrigir_pendencia(conexao, "EMP005", "rh.prisma", processamento_id, pendencia["linha"],
                                      correcoes.EXCLUIR, "", "A mesma pessoa veio duas vezes")
    assert pendencia_da_regra(conexao, "EMP005", "PESSOA_DUPLICADA") is None


# ---------------- CPF inteiro: ficha e download registrados ----------------

def cpfs_do_gabarito(verdade, empresa_id):
    """Os CPFs inteiros (só dígitos) de uma empresa, pelo gabarito."""
    cpfs = set()
    for pessoa in verdade.values():
        if pessoa["empresa_id"] == empresa_id:
            cpfs.add(pessoa["cpf"])
    return cpfs


def test_ficha_traz_o_cpf_inteiro_e_registra_quem_abriu(conexao, verdade):
    homologar(conexao, "aurora_carga_inicial", verdade)
    primeira = acompanhamento.funcionarios_da_empresa(conexao, "EMP001")[0]
    ficha = acompanhamento.ficha_do_funcionario(conexao, "EMP001", "rh.aurora", primeira["id"])
    # O CPF inteiro, pontuado, é um CPF de verdade da Aurora
    assert re.match(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", ficha["cpf"])
    assert ficha["cpf"].replace(".", "").replace("-", "") in cpfs_do_gabarito(verdade, "EMP001")
    assert ficha["nome_completo"] == primeira["nome_completo"]
    # O acesso ficou registrado, sem o CPF
    acessos = acompanhamento.acessos_da_empresa(conexao, "EMP001")
    assert acessos == [{"login": "rh.aurora", "tipo": "FICHA", "quantidade": 1, "criado_em": acessos[0]["criado_em"]}]


def test_ficha_de_pessoa_de_outra_empresa_nao_abre(conexao, verdade):
    homologar(conexao, "aurora_carga_inicial", verdade)
    homologar(conexao, "brisa_carga_inicial", verdade)
    da_brisa = acompanhamento.funcionarios_da_empresa(conexao, "EMP003")[0]["id"]
    with pytest.raises(KeyError):
        acompanhamento.ficha_do_funcionario(conexao, "EMP001", "rh.aurora", da_brisa)
    # Tentativa barrada não conta como acesso
    assert acompanhamento.acessos_da_empresa(conexao, "EMP001") == []


def test_download_traz_so_as_pessoas_pedidas_da_empresa_com_cpf_inteiro(conexao, verdade):
    homologar(conexao, "aurora_carga_inicial", verdade)
    homologar(conexao, "brisa_carga_inicial", verdade)
    da_aurora = [pessoa["id"] for pessoa in acompanhamento.funcionarios_da_empresa(conexao, "EMP001")[:5]]
    da_brisa = acompanhamento.funcionarios_da_empresa(conexao, "EMP003")[0]["id"]
    # Pede 5 da Aurora e 1 da Brisa (esta é ignorada)
    conteudo = acompanhamento.lista_para_baixar(conexao, "EMP001", "rh.aurora", da_aurora + [da_brisa])
    texto = conteudo.decode("utf-8")
    linhas = texto.lstrip("﻿").strip().split("\n")
    # Cabeçalho + 5 pessoas, cada uma com um CPF inteiro da Aurora
    assert linhas[0].startswith("Nome;CPF;")
    assert len(linhas) == 6
    for linha in linhas[1:]:
        cpf = linha.split(";")[1]
        assert cpf.replace(".", "").replace("-", "") in cpfs_do_gabarito(verdade, "EMP001")
    # O download ficou registrado com 5 pessoas
    assert acompanhamento.acessos_da_empresa(conexao, "EMP001")[-1]["quantidade"] == 5
    # Sem nenhuma pessoa da empresa: recusado, e nada é registrado
    with pytest.raises(ValueError):
        acompanhamento.lista_para_baixar(conexao, "EMP001", "rh.aurora", [da_brisa])
    assert len(acompanhamento.acessos_da_empresa(conexao, "EMP001")) == 1


def test_download_neutraliza_celula_com_cara_de_formula(conexao, verdade, monkeypatch):
    homologar(conexao, "aurora_carga_inicial", verdade)
    lista = acompanhamento.funcionarios_da_empresa(conexao, "EMP001")
    # Um nome malicioso que o Excel executaria como fórmula
    lista[0]["nome_completo"] = "=HYPERLINK(\"http://exemplo.invalido\")"
    monkeypatch.setattr(acompanhamento, "funcionarios_da_empresa", lambda conexao_usada, empresa: lista)
    texto = acompanhamento.lista_para_baixar(conexao, "EMP001", "rh.aurora", [lista[0]["id"]]).decode("utf-8")
    # Lido como o Excel lê (o CSV pode pôr a célula entre aspas): o nome começa com o apóstrofo, então vira texto
    linhas = list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))
    assert linhas[1][0].startswith("'=HYPERLINK")


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_com_banco_do_teste(tmp_path, monkeypatch, verdade):
    """A API apontada para um banco só deste teste, com Aurora e Brisa homologadas e um usuário de cada perfil."""
    # O "conectar" original, guardado antes de trocar
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    # Toda conexão aberta pela API (e pelos serviços que usam auth.conectar) vai para o banco do teste
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    # Dados: Aurora e Brisa homologadas
    conexao = conectar_original(caminho)
    homologar(conexao, "aurora_carga_inicial", verdade)
    homologar(conexao, "brisa_carga_inicial", verdade)
    # Usuários
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    auth.cadastrar_usuario(conexao, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    conexao.close()
    return aplicacao


def entrar(aplicacao_do_teste, login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao_do_teste)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_api_devolve_so_os_dados_da_empresa_da_sessao(api_com_banco_do_teste):
    aurora = entrar(api_com_banco_do_teste, "rh.aurora")
    brisa = entrar(api_com_banco_do_teste, "rh.brisa")
    nomes_da_aurora = {pessoa["nome_completo"] for pessoa in aurora.get("/api/empresa/funcionarios").json()}
    nomes_da_brisa = {pessoa["nome_completo"] for pessoa in brisa.get("/api/empresa/funcionarios").json()}
    # Cada uma vê só os seus
    assert nomes_da_aurora and nomes_da_brisa and not nomes_da_aurora & nomes_da_brisa
    # Mandar outra empresa no endereço não muda nada: a empresa vem da sessão
    tentativa = aurora.get("/api/empresa/funcionarios?empresa_id=EMP003").json()
    assert {pessoa["nome_completo"] for pessoa in tentativa} == nomes_da_aurora


def test_api_lista_com_cpf_inteiro_registra_quem_abriu(api_com_banco_do_teste):
    """Abrir a lista (com o CPF inteiro, ADR-97) fica registrado: quem, o tipo e quantas pessoas."""
    aurora = entrar(api_com_banco_do_teste, "rh.aurora")
    resposta = aurora.get("/api/empresa/funcionarios")
    lista = resposta.json()
    # O navegador não guarda cópia de uma resposta com CPF inteiro
    assert resposta.headers["cache-control"] == "no-store"
    # O CPF sai inteiro e formatado
    assert re.match(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", lista[0]["cpf"])
    # O acesso ficou registrado, com a quantidade de pessoas e sem o CPF
    conexao = auth.conectar()
    acessos = acompanhamento.acessos_da_empresa(conexao, "EMP001")
    conexao.close()
    assert [(acesso["login"], acesso["tipo"], acesso["quantidade"]) for acesso in acessos] == \
        [("rh.aurora", "LISTA", len(lista))]


def test_api_resumo_e_envios_da_empresa(api_com_banco_do_teste, verdade):
    aurora = entrar(api_com_banco_do_teste, "rh.aurora")
    resumo = aurora.get("/api/empresa/resumo").json()
    pagina = aurora.get("/api/empresa/envios/pagina").json()
    assert resumo["envios"] == 1 and resumo["em_andamento"] == 0 and pagina["total"] == 1
    # O 2º cartão: as pessoas em análise pelo banco; a carga já foi cadastrada, então nenhuma
    assert resumo["pessoas_em_analise"] == 0
    assert resumo["cadastrados"] == pagina["envios"][0]["cadastrados"]
    # Nenhum CPF inteiro da Aurora (do gabarito) aparece na resposta
    corpo = aurora.get("/api/empresa/funcionarios").text
    for pessoa in verdade.values():
        if pessoa["empresa_id"] == "EMP001":
            assert pessoa["cpf"] not in corpo
    # Todos os campos do parâmetro saem, inclusive o nome da mãe (ADR-111: a empresa confere o que ela mesma enviou)
    assert "nome_mae" in corpo


@pytest.fixture
def api_com_pendencias(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com a carga da Horizonte parada em pendências."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_pendencias.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao = conectar_original(caminho)
    processamento_id = preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    auth.cadastrar_usuario(conexao, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao.close()
    return processamento_id


def test_api_corrige_pendencia_e_explica_valor_que_nao_serve(api_com_pendencias):
    horizonte = entrar(aplicacao, "rh.horizonte")
    pendencia = None
    for item in horizonte.get("/api/empresa/pendencias").json():
        if item["regra_id"] == "OBRIGATORIO_VAZIO":
            pendencia = item
    pedido = {"processamento_id": pendencia["processamento_id"], "linha": pendencia["linha"],
              "campo": pendencia["campo"], "novo_valor": "ontem", "motivo": "Data do contrato"}
    # Valor que não serve: 400 com a explicação
    resposta = horizonte.post("/api/empresa/pendencias/corrigir", json=pedido)
    assert resposta.status_code == 400 and resposta.json()["detail"]
    # Valor certo: 200 e a pendência some
    pedido["novo_valor"] = "15/03/2022"
    assert horizonte.post("/api/empresa/pendencias/corrigir", json=pedido).status_code == 200
    regras = [item["regra_id"] for item in horizonte.get("/api/empresa/pendencias").json()]
    assert "OBRIGATORIO_VAZIO" not in regras


def test_api_outra_empresa_nao_corrige_o_envio(api_com_pendencias):
    aurora = entrar(aplicacao, "rh.aurora")
    pedido = {"processamento_id": api_com_pendencias, "linha": 13, "campo": "data_admissao",
              "novo_valor": "15/03/2022", "motivo": "Tentativa de outra empresa"}
    # 404: nem revela que o envio existe em outra empresa
    assert aurora.post("/api/empresa/pendencias/corrigir", json=pedido).status_code == 404
    confirmacao = {"processamento_id": api_com_pendencias, "regra_id": "OBRIGATORIO_VAZIO", "linha": 13,
                   "justificativa": "Tentativa de outra empresa"}
    assert aurora.post("/api/empresa/pendencias/confirmar", json=confirmacao).status_code == 404
    # Sem login: 401
    assert TestClient(aplicacao).post("/api/empresa/pendencias/corrigir", json=pedido).status_code == 401


def test_api_ficha_e_download_com_cpf_inteiro_so_da_propria_empresa(api_com_banco_do_teste):
    aurora = entrar(api_com_banco_do_teste, "rh.aurora")
    brisa = entrar(api_com_banco_do_teste, "rh.brisa")
    id_da_aurora = aurora.get("/api/empresa/funcionarios").json()[0]["id"]
    # A ficha: CPF inteiro e sem cópia no navegador
    resposta = aurora.get("/api/empresa/funcionarios/" + id_da_aurora)
    assert resposta.status_code == 200
    assert re.match(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", resposta.json()["cpf"])
    assert resposta.headers["cache-control"] == "no-store"
    # A Brisa pedindo a ficha de alguém da Aurora: 404
    assert brisa.get("/api/empresa/funcionarios/" + id_da_aurora).status_code == 404
    # O download: CSV para baixar, sem cópia no navegador
    download = aurora.post("/api/empresa/funcionarios/baixar", json={"identificadores": [id_da_aurora]})
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["cache-control"] == "no-store"
    # Lista vazia (ou só de outra empresa): 400
    assert brisa.post("/api/empresa/funcionarios/baixar", json={"identificadores": [id_da_aurora]}).status_code == 400
    # O banco não baixa lista de funcionários da empresa
    especialista = entrar(api_com_banco_do_teste, "especialista")
    assert especialista.post("/api/empresa/funcionarios/baixar", json={"identificadores": [id_da_aurora]}).status_code == 403


def test_api_da_empresa_recusa_sem_login_e_outro_perfil(api_com_banco_do_teste):
    # Sem login: 401
    anonimo = TestClient(api_com_banco_do_teste)
    rotas = ["/api/empresa/resumo", "/api/empresa/envios/pagina", "/api/empresa/funcionarios",
             "/api/empresa/pendencias"]
    for rota in rotas:
        assert anonimo.get(rota).status_code == 401
    # Especialista do banco: 403 em todas (estas consultas são do Portal Empresa)
    especialista = entrar(api_com_banco_do_teste, "especialista")
    for rota in rotas:
        assert especialista.get(rota).status_code == 403


def dado_da_empresa_vazio_em_alguem(processamento_id: str) -> str:
    """Um campo que pode ser igual para todos (dado da empresa) e está vazio em alguém do envio."""
    from services import correcoes, parametros
    conexao = auth.conectar()
    try:
        registros = correcoes.dados_atuais(conexao, processamento_id).registros
        for campo in sorted(parametros.campos_iguais_para_todos(conexao)):
            for registro in registros:
                if registro.get(campo) in (None, ""):
                    return campo
    finally:
        conexao.close()
    raise AssertionError("o envio devia ter um dado da empresa vazio em alguém")


def test_api_preenche_para_todos_so_na_propria_empresa(api_com_pendencias):
    """A rota do "Preencher para todos": outra empresa recebe 404; valor que não serve, 400; informação de cada pessoa
    (a data de admissão), 400; um dado da empresa, 200."""
    horizonte = entrar(aplicacao, "rh.horizonte")
    aurora = entrar(aplicacao, "rh.aurora")
    pedido = {"processamento_id": api_com_pendencias, "campo": "data_admissao", "novo_valor": "15/03/2022",
              "motivo": "Mesma data para todos"}
    assert aurora.post("/api/empresa/pendencias/preencher_para_todos", json=pedido).status_code == 404
    # A data de admissão é de cada pessoa: nunca a mesma para todos
    recusado = horizonte.post("/api/empresa/pendencias/preencher_para_todos", json=pedido)
    assert recusado.status_code == 400 and "única por funcionário" in recusado.json()["detail"]
    # Um dado da empresa vazio em alguém: primeiro um valor que não serve, depois o certo
    campo_da_empresa = dado_da_empresa_vazio_em_alguem(api_com_pendencias)
    pedido["campo"] = campo_da_empresa
    valores_certos = {"complemento_comercial": "Sala 1", "cnpj_grupo": "11222333000181", "numero_comercial": "100",
                      "codigo_unidade": "U01", "nome_unidade": "Matriz", "bairro_comercial": "Centro",
                      "data_referencia_renda": "01/09/2026"}
    pedido["novo_valor"] = valores_certos.get(campo_da_empresa, "Centro")
    resposta = horizonte.post("/api/empresa/pendencias/preencher_para_todos", json=pedido)
    assert resposta.status_code == 200 and resposta.json()["preenchidos"] >= 1, (campo_da_empresa, resposta.text)


def test_pagina_de_envios_monta_so_a_pagina_pedida(conexao, verdade):
    """ADR-86: a página traz os envios pedidos, na ordem da lista inteira, e o total; pedido fora dos limites é recusado."""
    from datetime import date

    from services import processamentos
    homologar(conexao, "aurora_carga_inicial", verdade)
    # Mais 6 envios da Aurora, cada um com um arquivo diferente (o mesmo arquivo de novo seria o mesmo envio): 7 no total
    for numero in range(6):
        conteudo = ("Nome;Cargo\nPessoa " + str(numero) + ";Analista\n").encode("utf-8")
        processamentos.receber_arquivo(conexao, conteudo, "lista_" + str(numero) + ".csv", "EMP001", date(2026, 9, 1),
                                       "rh.aurora")
    todos = acompanhamento.envios_da_empresa(conexao, "EMP001")
    primeira = acompanhamento.pagina_de_envios(conexao, "EMP001", 0, 5)
    segunda = acompanhamento.pagina_de_envios(conexao, "EMP001", 5, 5)
    assert primeira["total"] == segunda["total"] == 7 == len(todos)
    ids_das_paginas = [envio["processamento_id"] for envio in primeira["envios"] + segunda["envios"]]
    assert ids_das_paginas == [envio["processamento_id"] for envio in todos]
    assert len(segunda["envios"]) == 2 and processamentos.contar(conexao, "EMP002") == 0
    for inicio, quantidade in ((-1, 5), (0, 0), (0, 51)):
        with pytest.raises(ValueError):
            acompanhamento.pagina_de_envios(conexao, "EMP001", inicio, quantidade)


def test_todos_os_funcionarios_com_a_situacao_de_cada_um(conexao, verdade):
    """Item 106: cadastrados, em análise e pendentes na mesma consulta, sem repetir a pessoa e sem o CPF inteiro."""
    from services import processamentos
    from models.contratos import EstadoProcessamento
    homologar(conexao, "aurora_carga_inicial", verdade)
    inclusao = preparar_ate_a_validacao(conexao, "aurora_inclusao")
    todos = acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001")
    cadastrados = [pessoa for pessoa in todos if pessoa["situacao"] == "Cadastrado"]
    pendentes = [pessoa for pessoa in todos if pessoa["situacao"] == "Pendente"]
    aguardando = [pessoa for pessoa in todos if pessoa["situacao"] == "Aguardando envio"]
    assert len(cadastrados) == len(acompanhamento.funcionarios_da_empresa(conexao, "EMP001"))
    # As 5 pessoas do envio com a empresa: as com pendência ficariam "Pendente"; esta inclusão não tem nenhuma, então
    # as 5 estão "Aguardando envio" (ADR-114): os dados estão certos, só falta a empresa mandar o envio ao banco
    assert len(pendentes) == 0 and len(aguardando) == 5
    # Pendente: sem id (sem ficha; o download usa o id_para_baixar, ADR-155), com a pendência dela
    assert all(pessoa["id"] is None and pessoa["pendencia"] for pessoa in pendentes)
    # Aguardando envio: sem id (sem ficha) e sem pendência (só espera o envio ir ao banco)
    assert all(pessoa["id"] is None and pessoa["pendencia"] is None for pessoa in aguardando)
    # O CPF sai formatado, e a chave interna (só os dígitos) não vaza
    for pessoa in todos:
        assert "_cpf_completo" not in pessoa
        assert pessoa["cpf"] == "" or FORMATO_DO_CPF_NA_TELA.match(pessoa["cpf"])
    # Mandado ao banco: os mesmos 5 passam a "Em análise", sem pendência
    processamentos.atualizar_status(conexao, inclusao, EstadoProcessamento.AGUARDANDO_BANCO)
    em_analise = [pessoa for pessoa in acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001")
                  if pessoa["situacao"] == "Em análise"]
    assert len(em_analise) == 5 and all(pessoa["pendencia"] is None for pessoa in em_analise)


def test_resumo_conta_as_pessoas_em_analise_pelo_banco(conexao, verdade):
    """O 2º cartão de "Acompanhar cadastros": quantas PESSOAS estão com o banco (envio em AGUARDANDO_BANCO).

    O número bate com o filtro "Em análise" da lista de funcionários; volta a 0 quando o banco cadastra; e o envio
    que ainda tem pendência (está com a empresa) não conta.
    """
    from services import processamentos
    from models.contratos import EstadoProcessamento
    homologar(conexao, "aurora_carga_inicial", verdade)
    inclusao = preparar_ate_a_validacao(conexao, "aurora_inclusao")
    # Antes de mandar ao banco: as 5 pessoas da inclusão estão "Aguardando envio", ninguém em análise
    assert acompanhamento.pessoas_em_analise_pelo_banco(conexao, "EMP001") == 0
    # Mandado ao banco: as 5 pessoas passam a contar como em análise
    processamentos.atualizar_status(conexao, inclusao, EstadoProcessamento.AGUARDANDO_BANCO)
    em_analise = acompanhamento.pessoas_em_analise_pelo_banco(conexao, "EMP001")
    assert em_analise == 5
    cadastrados_antes = acompanhamento.resumo_da_empresa(conexao, "EMP001")["cadastrados"]
    # O cartão bate com o filtro "Em análise" da lista de funcionários
    filtradas_em_analise = []
    for pessoa in acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001"):
        if pessoa["situacao"] == "Em análise":
            filtradas_em_analise.append(pessoa)
    assert em_analise == len(filtradas_em_analise)
    # O banco cadastra (homologa): ninguém mais em análise, e os cadastrados sobem
    homologacao.homologar(conexao, inclusao, "EMP001", "rh")
    assert acompanhamento.pessoas_em_analise_pelo_banco(conexao, "EMP001") == 0
    assert acompanhamento.resumo_da_empresa(conexao, "EMP001")["cadastrados"] == cadastrados_antes + 5
    # Envio parado em pendências (com a empresa, não com o banco): não conta como em análise
    preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    assert acompanhamento.resumo_da_empresa(conexao, "EMP002")["com_pendencia"] == 1
    assert acompanhamento.pessoas_em_analise_pelo_banco(conexao, "EMP002") == 0


def test_api_linha_do_tempo_do_envio_da_ficha(api_com_banco_do_teste):
    """O histórico da ficha: cada pessoa traz o envio; a linha do tempo dele só sai para a própria empresa."""
    aurora = entrar(api_com_banco_do_teste, "rh.aurora")
    brisa = entrar(api_com_banco_do_teste, "rh.brisa")
    pessoa = aurora.get("/api/empresa/funcionarios").json()[0]
    envio = pessoa["envio"]
    etapas = aurora.get("/api/empresa/envios/" + envio + "/linha_do_tempo").json()
    assert etapas[0]["nome"] == "Arquivo carregado" and etapas[0]["feito"]
    assert etapas[-1]["nome"] == "Contas abertas"
    # A Brisa não vê o envio da Aurora (404, sem dizer se existe)
    assert brisa.get("/api/empresa/envios/" + envio + "/linha_do_tempo").status_code == 404


def test_colunas_da_consulta_sao_todos_os_campos_do_parametro_com_a_marca_de_obrigatorio(conexao):
    """A grade tem uma coluna por campo do parâmetro vigente, na ordem do layout, com rótulo legível e a marca de
    obrigatório igual à do parâmetro (ADR-111)."""
    _, campos_do_layout = parametros.layout_ativo(conexao)
    colunas = acompanhamento.colunas_da_consulta(conexao)
    nomes_das_colunas = []
    for coluna in colunas:
        nomes_das_colunas.append(coluna["campo"])
    nomes_do_layout = []
    obrigatorios_do_layout = set()
    for campo in campos_do_layout:
        nomes_do_layout.append(campo.campo)
        if campo.obrigatorio:
            obrigatorios_do_layout.add(campo.campo)
    assert nomes_das_colunas == nomes_do_layout
    obrigatorios_nas_colunas = set()
    for coluna in colunas:
        if coluna["obrigatorio"]:
            obrigatorios_nas_colunas.add(coluna["campo"])
    assert obrigatorios_nas_colunas == obrigatorios_do_layout


def test_rotulo_legivel_do_campo():
    """O nome técnico vira um rótulo que a pessoa lê, com acento e siglas."""
    assert acompanhamento.rotulo_do_campo("data_admissao") == "Data admissão"
    assert acompanhamento.rotulo_do_campo("cnpj_empregador") == "CNPJ empregador"
    assert acompanhamento.rotulo_do_campo("nome_mae") == "Nome mãe"
    assert acompanhamento.rotulo_do_campo("campo_novo_do_banco") == "Campo novo do banco"
    # A sigla da profissão (ADR-143): "Código CBO", e não "Código cbo"
    assert acompanhamento.rotulo_do_campo("codigo_cbo") == "Código CBO"


def test_no_envio_com_a_empresa_quem_tem_pendencia_e_pendente_e_quem_nao_tem_aguarda_o_envio(conexao):
    """ADR-114: a carga inicial da Aurora tem uma pessoa com pendência (o CPF). Ela fica "Pendente", com a pendência;
    as outras, sem nenhuma pendência, ficam "Aguardando envio" (o envio espera a correção dela para ir ao banco)."""
    preparar_ate_a_validacao(conexao, "aurora_carga_inicial")
    todos = acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001")
    pendentes = [pessoa for pessoa in todos if pessoa["situacao"] == "Pendente"]
    aguardando = [pessoa for pessoa in todos if pessoa["situacao"] == "Aguardando envio"]
    assert len(pendentes) >= 1 and len(aguardando) >= 1
    assert len(pendentes) + len(aguardando) == len(todos)
    assert all(pessoa["pendencia"] for pessoa in pendentes)
    assert all(pessoa["pendencia"] is None for pessoa in aguardando)


def test_obrigatorio_vazio_nao_se_resolve_com_valor_em_branco_nem_com_confirmacao(conexao):
    """Campo obrigatório vazio é BLOQUEANTE: corrigir com o valor em branco não tira a pendência, e "confirmar" (a
    justificativa que vale só para alerta) é recusado. O envio continua sem poder ir ao banco."""
    processamento_id = preparar_ate_a_validacao(conexao, "horizonte_carga_inicial")
    pendencia = pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO")
    # 1. Corrigir com o valor em branco: o pedido é registrado, mas a validação refeita aponta o vazio de novo
    acompanhamento.corrigir_pendencia(conexao, "EMP002", "rh.horizonte", processamento_id, pendencia["linha"],
                                      pendencia["campo"], "", "Deixar em branco")
    ainda_pendente = pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO")
    assert ainda_pendente is not None and ainda_pendente["linha"] == pendencia["linha"]
    # 2. Confirmar (justificar) um obrigatório vazio é recusado: só alerta aceita justificativa
    with pytest.raises(ValueError, match="Não há um alerta"):
        acompanhamento.confirmar_pendencia(conexao, "EMP002", "rh.horizonte", processamento_id, "OBRIGATORIO_VAZIO",
                                           pendencia["linha"], "Está certo assim")
    assert pendencia_da_regra(conexao, "EMP002", "OBRIGATORIO_VAZIO") is not None
    # 3. Com o obrigatório vazio, o envio não está pronto para o banco
    assert not validador.obter(conexao, processamento_id).pronto_para_homologar
