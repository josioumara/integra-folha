"""Motor de planejamento e painel, SEM a base do banco.

O que estes testes provam:
- o motor não lê base nenhuma do banco: cada funcionário homologado entra "aguardando o retorno do banco";
- o resumo cruza as pessoas com o retorno do banco (o arquivo de contas), pelo hash do CPF: contas abertas (status
  1) e correntistas (status 2, um grupo só desde o ADR-149: a situação e a folha antigas não são mais lidas); uma
  conta gravada antes da coluna do tipo conta como aguardando (o banco sempre informa o status: sem ele, ainda não
  foi dito);
- sem recontar, sem dado individual, sem campo proibido; números rastreáveis até o arquivo homologado;
- o ganho realizado e o potencial, conferidos com a conta feita à mão; sem a % que já é correntista ou sem a taxa,
  o potencial espera (nada é suposto);
- o simulador usa as premissas oficiais e troca só as que o especialista mudou, sem mudar as oficiais; a simulação
  salva tem nome (obrigatório) e os próprios valores;
- as rotas do simulador são só do BANCO (401 sem login, 403 para a empresa).

O retorno do banco é trocado aqui por um falso (retorno_do_banco), com a mesma assinatura de
services/contas_abertas.retorno_por_cpf: assim cada teste diz exatamente o tipo de cada CPF.
"""
import csv
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil, carregar_layout
from services import (auth, banco, config, contas_abertas, homologacao, motor_planejamento, parametros,
                      planejamento, portal_do_banco)
from scripts import tirar_a_base_do_planejamento
from tests.test_correcao import busca_falsa, corrigir_tudo, preparar_ate_a_validacao

# A base sintética e os gabaritos
RAIZ = Path(__file__).resolve().parent.parent
SINTETICO = RAIZ / "data" / "synthetic"
GOLDEN = RAIZ / "data" / "golden"
# Campos que nunca podem chegar ao motor (ADR-29), mais salário e cargo
CAMPOS_QUE_O_MOTOR_NAO_PODE_LER = {"sexo", "estado_civil", "nacionalidade", "data_nascimento", "valor_renda",
                                   "cargo", "nome_completo", "nome_mae"}
# Senha dos usuários de teste das rotas (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"
# A função de verdade do retorno do banco, guardada antes de a troca pelo falso (retorno_do_banco) acontecer
RETORNO_POR_CPF_DE_VERDADE = contas_abertas.retorno_por_cpf


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


@pytest.fixture(autouse=True)
def usar_busca_falsa(monkeypatch):
    """O Interpretador usa a busca falsa (sem depender do índice do RAG)."""
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)


@pytest.fixture(autouse=True)
def retorno_do_banco(monkeypatch):
    """O retorno do banco (o arquivo de contas) de mentira: {empresa_id: {cpf: {"tipo_conta"}}}.

    Começa vazio (todo mundo aguardando); cada teste põe o que precisa. A função falsa respeita as empresas pedidas,
    como a de verdade (services/contas_abertas.retorno_por_cpf).
    """
    retornos = {}

    def retorno_por_cpf_falso(conexao, empresa_ids):
        """O retorno só das empresas pedidas."""
        resultado = {}
        for empresa_id in empresa_ids:
            resultado.update(retornos.get(empresa_id, {}))
        return resultado
    # raising=False: a troca vale mesmo antes de a função de verdade existir
    monkeypatch.setattr(contas_abertas, "retorno_por_cpf", retorno_por_cpf_falso, raising=False)
    return retornos


@pytest.fixture(scope="module")
def verdade():
    """O gabarito de cada funcionário: funcionario_id -> campos corretos."""
    funcionarios = {}
    with open(SINTETICO / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            funcionarios[linha["funcionario_id"]] = linha
    return funcionarios


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def _funcionarios_do_gabarito(nome: str) -> list[str]:
    """Os funcionario_id de um arquivo, pelo gabarito."""
    return json.loads((GOLDEN / f"{nome}.json").read_text(encoding="utf-8"))["funcionario_ids"]


def _cpfs_do_arquivo(nome: str, verdade) -> list[str]:
    """Os CPFs (11 algarismos) das pessoas de um arquivo, pelo gabarito."""
    cpfs = []
    for funcionario_id in _funcionarios_do_gabarito(nome):
        cpfs.append(verdade[funcionario_id]["cpf"])
    return cpfs


def homologar(conexao, nome: str, verdade) -> str:
    """Recebe, aceita, corrige tudo e homologa um arquivo da demo. Devolve o processamento_id."""
    processamento_id = preparar_ate_a_validacao(conexao, nome)
    corrigir_tudo(conexao, nome, processamento_id, verdade)
    empresa_id = json.loads((GOLDEN / f"{nome}.json").read_text(encoding="utf-8"))["empresa_id"]
    homologacao.homologar(conexao, processamento_id, empresa_id, "rh")
    return processamento_id


def _aurora_no_planejamento(conexao, verdade) -> str:
    """A carga inicial da Aurora homologada e registrada pelo motor. Devolve o processamento_id."""
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    motor_planejamento.processar_homologacao(conexao, processamento_id, "EMP001")
    return processamento_id


def _contagens(**valores) -> dict:
    """Um resumo com todas as contagens em zero, menos as informadas. Ex.: _contagens(contas_abertas=2)."""
    resumo = {}
    for campo in planejamento.CAMPOS_CONTAGEM:
        resumo[campo] = valores.get(campo, 0)
    return resumo


# ---------- O motor, sem a base do banco ----------

def test_a_base_do_banco_saiu_e_o_motor_nao_a_le():
    """O arquivo da base sintética do banco não existe mais, e o motor não fala dela."""
    assert importlib.util.find_spec("services.base_banco") is None
    assert not (SINTETICO / "base_banco.csv").exists()
    codigo_do_motor = (RAIZ / "services" / "motor_planejamento.py").read_text(encoding="utf-8")
    assert "import base_banco" not in codigo_do_motor and "base_banco." not in codigo_do_motor


def test_cada_homologado_fica_aguardando_o_retorno_do_banco(conexao, verdade):
    """Sem nenhum arquivo de contas, os 35 da Aurora estão Cadastrados e aguardando o retorno do banco."""
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    contagem = motor_planejamento.processar_homologacao(conexao, processamento_id, "EMP001")
    assert contagem == {"novos": 35, "ja_contados": 0}
    assert planejamento.resumir(conexao, "EMP001") == _contagens(cadastrados=35, aguardando_retorno=35)


def test_motor_so_roda_depois_da_homologacao(conexao):
    """Arquivo ainda não homologado: o motor recusa."""
    processamento_id = preparar_ate_a_validacao(conexao, "aurora_carga_inicial")
    with pytest.raises(ValueError, match="homologado"):
        motor_planejamento.processar_homologacao(conexao, processamento_id, "EMP001")


def test_inclusao_nao_reconta_ninguem(conexao, verdade):
    """Brisa: a inclusão só conta as pessoas novas; rodar o motor de novo no mesmo arquivo não soma nada."""
    inicial = homologar(conexao, "brisa_carga_inicial", verdade)
    motor_planejamento.processar_homologacao(conexao, inicial, "EMP003")
    cadastrados_depois_da_carga_inicial = planejamento.resumir(conexao, "EMP003")["cadastrados"]
    inclusao = homologar(conexao, "brisa_inclusao", verdade)
    contagem = motor_planejamento.processar_homologacao(conexao, inclusao, "EMP003")
    # A inclusão trazia 2 pessoas novas e 1 já homologada (que nem entra no arquivo final)
    assert contagem["novos"] == 2
    de_novo = motor_planejamento.processar_homologacao(conexao, inclusao, "EMP003")
    assert de_novo["novos"] == 0 and de_novo["ja_contados"] == 2
    assert planejamento.resumir(conexao, "EMP003")["cadastrados"] == cadastrados_depois_da_carga_inicial + 2


def test_hash_do_cpf_ignora_a_pontuacao():
    """O CPF com ou sem pontuação dá o mesmo hash: o retorno do banco cruza com o motor de qualquer jeito."""
    assert motor_planejamento.hash_do_cpf("529.982.247-25") == motor_planejamento.hash_do_cpf("52998224725")


# ---------- O retorno do banco (arquivo de contas) ----------

def test_resumo_cruza_com_o_retorno_por_tipo(conexao, verdade, retorno_do_banco):
    """2 contas abertas, 2 correntistas (um grupo só, ADR-149) e o resto aguardando, com a conta sem o tipo."""
    _aurora_no_planejamento(conexao, verdade)
    cpfs = _cpfs_do_arquivo("aurora_carga_inicial", verdade)
    retorno_do_banco["EMP001"] = {
        cpfs[0]: {"tipo_conta": "NOVA_CONTA"},
        cpfs[1]: {"tipo_conta": "NOVA_CONTA"},
        cpfs[2]: {"tipo_conta": "CORRENTISTA"},
        cpfs[3]: {"tipo_conta": "CORRENTISTA"},
        # Conta gravada antes da coluna do tipo: o banco ainda não disse o status, então aguarda (nada é assumido)
        cpfs[4]: {"tipo_conta": None},
    }
    assert planejamento.resumir(conexao) == _contagens(
        cadastrados=35, aguardando_retorno=31, contas_abertas=2, correntistas_marcados=2)
    # O resumo só tem as quatro contagens: sem ativos, inativos nem a folha (ADR-149)
    assert planejamento.CAMPOS_CONTAGEM == ("cadastrados", "aguardando_retorno", "contas_abertas",
                                            "correntistas_marcados")


def test_resumo_com_o_arquivo_de_contas_de_verdade(conexao, verdade, monkeypatch):
    """O mesmo cruzamento com a tabela de contas de verdade (services/contas_abertas.py), com o CPF só em algarismos."""
    monkeypatch.setattr(contas_abertas, "retorno_por_cpf", RETORNO_POR_CPF_DE_VERDADE)
    _aurora_no_planejamento(conexao, verdade)
    cpfs = _cpfs_do_arquivo("aurora_carga_inicial", verdade)
    # Lista vazia: só cria as tabelas das contas
    assert contas_abertas.retorno_por_cpf(conexao, []) == {}
    # Três baixas do banco: uma conta nova, um correntista gravado antes do ADR-149 (com a situação INATIVO, que não
    # é mais lida) e uma conta antiga, sem o tipo
    for cpf, tipo_conta, situacao in ((cpfs[0], "NOVA_CONTA", None), (cpfs[1], "CORRENTISTA", "INATIVO"),
                                      (cpfs[2], None, None)):
        conexao.execute("INSERT INTO contas_abertas (empresa_id, cpf, data_abertura, agencia, conta, codigo_banco, "
                        "arquivo_id, baixa_em, tipo_conta, situacao_correntista) VALUES "
                        "('EMP001', ?, '2026-09-20', '0001', '12345', '033', 'arq-1', '2026-09-21T10:00:00+00:00', "
                        "?, ?)", (cpf, tipo_conta, situacao))
    conexao.commit()
    assert planejamento.resumir(conexao) == _contagens(
        cadastrados=35, aguardando_retorno=33, contas_abertas=1, correntistas_marcados=1)


def test_retorno_de_quem_nao_e_cadastrado_ou_e_de_outra_empresa_nao_conta(conexao, verdade, retorno_do_banco):
    """Um CPF que não está no planejamento, ou a conta do mesmo CPF em outra empresa, não mexe nos números."""
    _aurora_no_planejamento(conexao, verdade)
    cpfs_da_aurora = _cpfs_do_arquivo("aurora_carga_inicial", verdade)
    cpfs_da_vale_verde = _cpfs_do_arquivo("vale_verde_carga_inicial", verdade)
    # Na Aurora, a conta de alguém da Vale Verde (não é Cadastrado aqui)
    retorno_do_banco["EMP001"] = {cpfs_da_vale_verde[0]: {"tipo_conta": "NOVA_CONTA"}}
    # Na Vale Verde, a conta de alguém da Aurora (o retorno de outra empresa não vale para a Aurora)
    retorno_do_banco["EMP004"] = {cpfs_da_aurora[0]: {"tipo_conta": "NOVA_CONTA"}}
    assert planejamento.resumir(conexao) == _contagens(cadastrados=35, aguardando_retorno=35)


def test_por_empresa_e_por_regiao_somam_o_resumo(conexao, verdade, retorno_do_banco):
    """Com duas empresas e retornos, as linhas por empresa e por região somam o total; o filtro de UF recorta."""
    for nome, empresa_id in (("aurora_carga_inicial", "EMP001"), ("vale_verde_carga_inicial", "EMP004")):
        processamento_id = homologar(conexao, nome, verdade)
        motor_planejamento.processar_homologacao(conexao, processamento_id, empresa_id)
    cpfs_da_vale_verde = _cpfs_do_arquivo("vale_verde_carga_inicial", verdade)
    retorno_do_banco["EMP004"] = {cpfs_da_vale_verde[0]: {"tipo_conta": "NOVA_CONTA"},
                                  cpfs_da_vale_verde[1]: {"tipo_conta": "CORRENTISTA"}}
    total = planejamento.resumir(conexao)
    assert total["cadastrados"] == 35 + 70 and total["contas_abertas"] == 1 and total["correntistas_marcados"] == 1
    for campo in planejamento.CAMPOS_CONTAGEM:
        soma_das_empresas = 0
        for linha in planejamento.por_empresa(conexao):
            soma_das_empresas += linha[campo]
        soma_das_regioes = 0
        for linha in planejamento.por_regiao(conexao):
            soma_das_regioes += linha[campo]
        assert soma_das_empresas == total[campo] and soma_das_regioes == total[campo]
    assert planejamento.valores_para_filtro(conexao, "uf") == ["PR", "SP"]
    assert planejamento.resumir(conexao, uf="PR") == planejamento.resumir(conexao, empresa_id="EMP004")


def test_o_filtro_de_segmento_saiu(conexao):
    """O segmento vinha da base do banco: não há mais de onde tirá-lo, e o filtro não existe."""
    assert "segmento" not in planejamento.COLUNAS_DE_FILTRO
    with pytest.raises(ValueError, match="Coluna sem filtro"):
        planejamento.valores_para_filtro(conexao, "segmento")
    assert "segmento" not in portal_do_banco.filtros_do_planejamento(conexao)


# ---------- Privacidade ----------

def test_nenhuma_saida_expoe_dado_individual(conexao, verdade, retorno_do_banco):
    """Resumo, tabela por região e por empresa: só contagens e a região; nenhum CPF sai do planejamento."""
    _aurora_no_planejamento(conexao, verdade)
    cpfs = _cpfs_do_arquivo("aurora_carga_inicial", verdade)
    retorno_do_banco["EMP001"] = {cpfs[0]: {"tipo_conta": "CORRENTISTA"}}
    resumo = planejamento.resumir(conexao)
    assert set(resumo) == set(planejamento.CAMPOS_CONTAGEM)
    for valor in resumo.values():
        assert isinstance(valor, int)
    for linha in planejamento.por_regiao(conexao):
        assert set(linha) == {"uf", "municipio", "nome_unidade"} | set(planejamento.CAMPOS_CONTAGEM)
    saidas = json.dumps([resumo, planejamento.por_regiao(conexao), planejamento.por_empresa(conexao)])
    for cpf in cpfs:
        assert cpf not in saidas
        assert motor_planejamento.hash_do_cpf(cpf) not in saidas


def test_tabela_interna_guarda_o_hash_e_nunca_o_cpf(conexao, verdade):
    """A tabela por funcionário (interna) tem o SHA-256 do CPF, nunca o CPF; e nada que vinha da base do banco."""
    _aurora_no_planejamento(conexao, verdade)
    linhas = conexao.execute("SELECT * FROM planejamento_funcionario").fetchall()
    conteudo = json.dumps(linhas)
    for cpf in _cpfs_do_arquivo("aurora_carga_inicial", verdade):
        assert cpf not in conteudo
    for linha in conexao.execute("SELECT cpf_hash FROM planejamento_funcionario"):
        assert len(linha[0]) == 64
    colunas = banco.colunas_da_tabela(conexao, "planejamento_funcionario")
    assert not set(tirar_a_base_do_planejamento.COLUNAS_DA_BASE_ANTIGA) & set(colunas)


def test_motor_so_le_campos_liberados_para_uso_comercial(conexao, verdade):
    """O motor lê só os seus 5 campos, todos liberados; campos proibidos nunca chegam a ele."""
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    liberados = motor_planejamento.campos_liberados(conexao)
    assert set(motor_planejamento.CAMPOS_USADOS) <= liberados
    assert not set(motor_planejamento.CAMPOS_USADOS) & CAMPOS_QUE_O_MOTOR_NAO_PODE_LER
    for registro in motor_planejamento.ler_registros_homologados(conexao, processamento_id):
        assert set(registro) == set(motor_planejamento.CAMPOS_USADOS)


def test_campo_do_motor_bloqueado_no_layout_impede_o_motor(conexao, verdade):
    """Se o banco marcar a UF comercial como proibida para uso comercial, o motor não roda."""
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    linhas = []
    for campo in carregar_layout():
        linha = campo.model_dump(mode="json")
        if campo.campo == "uf_comercial":
            linha["uso_comercial_permitido"] = False
        linhas.append(linha)
    parametros.salvar_layout(conexao, linhas, "especialista.banco")
    with pytest.raises(ValueError, match="uf_comercial"):
        motor_planejamento.processar_homologacao(conexao, processamento_id, "EMP001")


# ---------- Premissas e ganho realizado ----------

def test_premissas_v1_sao_as_do_business_case_e_so_tem_mob_e_horizonte(conexao):
    """A v1 tem os números do business case; as taxas não são premissas oficiais (só do simulador)."""
    premissas = parametros.premissas_ativas(conexao)
    assert premissas.mob_cliente_folha == Decimal("2090.62")
    assert premissas.mob_cliente_nao_folha == Decimal("1724.00")
    assert premissas.mob_cliente_folha - premissas.mob_cliente_nao_folha == Decimal("366.62")
    assert sorted(parametros.premissas_como_dict(premissas)) == ["horizonte_meses", "mob_cliente_folha",
                                                                 "mob_cliente_nao_folha",
                                                                 "mob_cliente_novo_conquistado"]


def test_ganho_realizado_conferido_a_mao(conexao):
    """Realizado = 3 correntistas × 366,62 + 2 contas novas × 2.090,62 (ADR-149: o correntista é um grupo só, o
    cliente que já estava no banco e passa a ter a folha reconhecida)."""
    resumo = _contagens(cadastrados=15, aguardando_retorno=10, contas_abertas=2, correntistas_marcados=3)
    ganho = planejamento.projetar_ganho(resumo, parametros.premissas_ativas(conexao))
    assert ganho == {"realizado": {"correntistas": Decimal("1099.86"), "contas_abertas": Decimal("4181.24"),
                                   "total": Decimal("5281.10")}, "versao_premissas": "v1", "horizonte_meses": 12}


def test_conta_sem_o_tipo_conta_como_aguardando_e_nao_entra_no_realizado(conexao):
    """O banco sempre informa o tipo: uma conta gravada sem ele só pode ser de antes da
    coluna, e o status dela ainda não foi dito. Ela aguarda o retorno e não entra no realizado."""
    assert planejamento.classificar({"tipo_conta": None}) == planejamento.AGUARDANDO_RETORNO
    assert planejamento.classificar(None) == planejamento.AGUARDANDO_RETORNO
    assert "retorno_sem_tipo" not in planejamento.CAMPOS_CONTAGEM


def test_premissa_nova_muda_o_cenario_e_a_antiga_continua_reproduzivel(conexao):
    """Com a v2 (MOB folha maior), o ganho muda; a v1 escolhida de novo dá o mesmo ganho de antes."""
    resumo = _contagens(cadastrados=10, correntistas_marcados=10)
    antes = planejamento.projetar_ganho(resumo, planejamento.premissas_da_versao(conexao, 1))
    dados = parametros.premissas_como_dict(parametros.premissas_ativas(conexao))
    dados["mob_cliente_folha"] = "2200.00"
    parametros.salvar_premissas(conexao, dados, "especialista.banco")
    assert len(parametros.historico(conexao, "premissas")) == 2
    com_a_v2 = planejamento.projetar_ganho(resumo, planejamento.premissas_da_versao(conexao, 2))
    com_a_v1_de_novo = planejamento.projetar_ganho(resumo, planejamento.premissas_da_versao(conexao, 1))
    assert com_a_v2["realizado"]["total"] != antes["realizado"]["total"] and com_a_v2["versao_premissas"] == "v2"
    assert com_a_v1_de_novo == antes
    with pytest.raises(ValueError, match="versão 9"):
        planejamento.premissas_da_versao(conexao, 9)


def test_taxa_digitada_vira_fracao_no_servico():
    """20 (de 20%) vira 0,20 em Decimal: a tela não faz essa conta."""
    assert planejamento.taxa_da_porcentagem(20) == Decimal("0.2")
    assert planejamento.taxa_da_porcentagem(12.5) == Decimal("0.125")


# ---------- O Simulador de Rentabilidade ----------

# As quatro taxas do exemplo conferido à mão: 30% novas contas, 40% correntista não folha, 20%
# correntista folha e 75% dos correntistas ativos
TAXAS_DO_EXEMPLO = {"percentual_novas_contas": "30", "percentual_nao_folha": "40", "percentual_folha": "20",
                    "percentual_ativos": "75"}


def test_simulacao_conferida_a_mao(conexao):
    """312 clientes, 30% / 40% / 20% e 75% ativos: a nova conta traz o MOB novo; o não folha ativo, a diferença de
    MOB; o folha (já traz o MOB maior), o inativo e o resto da base não trazem nada."""
    simulacao = planejamento.premissas_do_simulador(conexao, TAXAS_DO_EXEMPLO)
    resultado = planejamento.simular_rentabilidade(312, simulacao["taxas"], simulacao["premissas"])
    linhas = {}
    for linha in resultado["linhas"]:
        linhas[linha["grupo"]] = (linha["pessoas"], linha["ganho"], linha["rende"])
    # 312 × 30% = 93,6 × 2.090,62 = 195.682,032 → 195.682,03
    # 312 × 40% = 124,8 não folha; 75% ativos = 93,6 × 366,62 = 34.315,632 → 34.315,63; inativos 31,2
    # 312 × 20% = 62,4 folha: 46,8 ativos e 15,6 inativos; o resto: 312 − 93,6 − 124,8 − 62,4 = 31,2
    assert linhas == {
        "Novas contas": ("93.6", "195682.03", True),
        "Correntistas não folha · ativos (folha identificada)": ("93.6", "34315.63", True),
        "Correntistas não folha · inativos": ("31.2", "0.00", False),
        "Correntistas folha · ativos": ("46.8", "0.00", False),
        "Correntistas folha · inativos": ("15.6", "0.00", False),
        "Resto da base (não abrem conta)": ("31.2", "0.00", False),
    }
    assert resultado["total"] == "229997.66" and resultado["falta"] == [] and resultado["clientes"] == 312


def test_sem_uma_taxa_a_simulacao_espera(conexao):
    """Nada é suposto: sem uma das quatro taxas não há linhas nem total, e "falta" diz qual falta."""
    simulacao = planejamento.premissas_do_simulador(conexao, {"percentual_novas_contas": "30"})
    resultado = planejamento.simular_rentabilidade(312, simulacao["taxas"], simulacao["premissas"])
    assert resultado["linhas"] == [] and resultado["total"] is None
    assert resultado["falta"] == ["% correntista (não folha)", "% correntista (folha)",
                                  "% ativos entre os correntistas"]


def test_simulador_parte_das_oficiais_e_troca_so_o_que_mudou(conexao):
    """Sem nada mudado, valem as oficiais, e as taxas e a estimativa ficam sem valor; mudando, só o que veio troca."""
    oficial = planejamento.premissas_do_simulador(conexao, {})
    assert oficial["valores"] == {"horizonte_meses": 12, "mob_cliente_folha": "2090.62",
                                  "mob_cliente_nao_folha": "1724.00", "mob_cliente_novo_conquistado": "2090.62",
                                  "percentual_novas_contas": None, "percentual_nao_folha": None,
                                  "percentual_folha": None, "percentual_ativos": None, "clientes_estimados": None}
    assert oficial["alteradas"] == [] and oficial["clientes_estimados"] is None and oficial["premissas"].versao == "v1"
    mudada = planejamento.premissas_do_simulador(conexao, {"mob_cliente_folha": "2200", "clientes_estimados": "1200",
                                                           "percentual_novas_contas": "30"})
    # Só as premissas globais contam como "mudadas" (as taxas e a estimativa nunca são oficiais)
    assert mudada["alteradas"] == ["mob_cliente_folha"]
    assert mudada["premissas"].mob_cliente_folha == Decimal("2200.00")
    assert mudada["taxas"]["percentual_novas_contas"] == Decimal("0.3") and mudada["clientes_estimados"] == 1200


@pytest.mark.parametrize("valores, recado", [
    ({"mob_cliente_folha": "0"}, "maior que zero"),
    ({"mob_cliente_folha": ""}, "Informe o valor"),
    ({"horizonte_meses": "0"}, "de 1 a 60"),
    ({"percentual_novas_contas": "150"}, "entre 0% e 100%"),
    ({"percentual_nao_folha": "NaN"}, "entre 0% e 100%"),
    ({"percentual_ativos": "-1"}, "entre 0% e 100%"),
    ({"percentual_folha": "101"}, "entre 0% e 100%"),
    ({"percentual_novas_contas": "12.345"}, "no máximo 2 casas"),
    ({"percentual_novas_contas": "60", "percentual_nao_folha": "50"}, "passam de 100%"),
    ({"percentual_novas_contas": "40", "percentual_nao_folha": "40", "percentual_folha": "30"}, "passam de 100%"),
    ({"clientes_estimados": "12,5"}, "inteiro"),
    ({"clientes_estimados": "-3"}, "inteiro"),
    ({"clientes_estimados": "10000001"}, "10 milhões"),
])
def test_simulador_recusa_valor_invalido(conexao, valores, recado):
    """Cada valor do simulador é conferido: as premissas como nas oficiais, as taxas de 0 a 100 (novas contas + não
    folha até 100%) e a estimativa de clientes inteira, até 10 milhões."""
    with pytest.raises(ValueError, match=recado):
        planejamento.premissas_do_simulador(conexao, valores)


def test_simulacao_salva_com_nome_base_e_valores_sem_mudar_as_oficiais(conexao):
    """A simulação guarda o nome, quem, a empresa, os próprios valores, a base e o resultado; as oficiais não mudam."""
    valores = dict(TAXAS_DO_EXEMPLO)
    valores["mob_cliente_folha"] = "2200"
    simulacao = planejamento.premissas_do_simulador(conexao, valores)
    base = {"clientes": 100, "origem": "estimativa"}
    resultado = planejamento.simular_rentabilidade(100, simulacao["taxas"], simulacao["premissas"])
    planejamento.salvar_simulacao(conexao, "  Cenário otimista  ", simulacao, base, resultado,
                                  {"empresa_id": "EMP001"}, "especialista.banco")
    salva = planejamento.simulacoes(conexao)[0]
    assert salva["nome"] == "Cenário otimista" and salva["usuario"] == "especialista.banco"
    assert salva["filtros"] == {"empresa_id": "EMP001"} and salva["versao_premissas"] == "v1"
    assert salva["valores"]["mob_cliente_folha"] == "2200.00" and salva["valores"]["percentual_novas_contas"] == "30.00"
    assert salva["base"] == base
    # O detalhe por grupo volta junto, para a janela "Visualizar"
    assert salva["simulacao"] == resultado and len(salva["simulacao"]["linhas"]) == 6
    # 100 × 30% × 2.090,62 = 62.718,60 e 100 × 40% × 75% ativos × (2.200 − 1.724) = 30 × 476 = 14.280,00
    assert salva["ganho_total"] == "76998.60"
    # As oficiais não mudaram: continua só a v1, com os valores do business case
    assert len(parametros.historico(conexao, "premissas")) == 1
    assert parametros.premissas_ativas(conexao).mob_cliente_folha == Decimal("2090.62")


@pytest.mark.parametrize("nome", ["", "   ", None, "x" * 81])
def test_simulacao_sem_nome_ou_com_nome_grande_e_recusada(conexao, nome):
    """O nome é obrigatório (e tem até 80 caracteres): nada é gravado sem ele."""
    simulacao = planejamento.premissas_do_simulador(conexao, {})
    resultado = planejamento.simular_rentabilidade(0, simulacao["taxas"], simulacao["premissas"])
    with pytest.raises(ValueError, match="nome"):
        planejamento.salvar_simulacao(conexao, nome, simulacao, {"clientes": 0, "origem": "empresa"}, resultado, {},
                                      "especialista.banco")
    assert planejamento.simulacoes(conexao) == []


def test_simulacao_antiga_ganha_os_valores_da_versao_que_usou(conexao):
    """Simulação salva antes do Simulador de Rentabilidade: reabre com as premissas da versão dela, sem as taxas."""
    motor_planejamento.preparar_tabelas(conexao)
    conexao.execute("INSERT INTO simulacao_ganho (criado_em, usuario, filtros, taxa_conquista, versao_premissas, "
                    "resultado) VALUES ('2026-09-25T10:00:00+00:00', 'rafael.lima', '{}', '0.2', 'v1', "
                    "'{\"ganho_total\": \"5647.72\"}')")
    antiga = planejamento.simulacoes(conexao)[0]
    assert antiga["nome"] == "" and antiga["ganho_total"] == "5647.72" and antiga["base"] is None and antiga["simulacao"] is None
    assert antiga["valores"]["mob_cliente_folha"] == "2090.62"
    assert antiga["valores"]["percentual_novas_contas"] is None and antiga["valores"]["clientes_estimados"] is None


def test_retorno_confirmado_mostra_as_taxas_observadas(conexao):
    """A referência do simulador: de quem já teve retorno, quantos abriram conta nova e quantos eram correntistas (um
    grupo só, ADR-149)."""
    resumo = _contagens(cadastrados=14, aguardando_retorno=4, contas_abertas=3, correntistas_marcados=6)
    confirmado = planejamento.retorno_confirmado(resumo, parametros.premissas_ativas(conexao))
    assert confirmado["com_retorno"] == 10 and confirmado["correntistas"] == 6
    assert confirmado["taxas_observadas"] == {"novas_contas": "30.0", "correntistas": "60.0"}
    # Os 6 correntistas e as 3 contas novas: 6 × 366,62 + 3 × 2.090,62
    assert confirmado["realizado"]["total"] == "8471.58"
    # Sem retorno nenhum, não há taxa observada (nunca uma divisão por zero)
    sem_retorno = planejamento.retorno_confirmado(_contagens(cadastrados=5, aguardando_retorno=5),
                                                  parametros.premissas_ativas(conexao))
    assert sem_retorno["taxas_observadas"] == {"novas_contas": None, "correntistas": None}


# ---------- O painel ----------

def test_cards_batem_com_a_consulta_de_origem(conexao, verdade):
    """Os números de cima do painel são exatamente os da tabela do motor, contados direto no banco."""
    for nome in ("aurora_carga_inicial", "vale_verde_carga_inicial"):
        processamento_id = homologar(conexao, nome, verdade)
        empresa_id = json.loads((GOLDEN / f"{nome}.json").read_text(encoding="utf-8"))["empresa_id"]
        motor_planejamento.processar_homologacao(conexao, processamento_id, empresa_id)
    indicadores = planejamento.indicadores(conexao)
    empresas, funcionarios = conexao.execute(
        "SELECT COUNT(DISTINCT empresa_id), COUNT(*) FROM planejamento_funcionario").fetchone()
    assert indicadores == {"empresas_integradas": empresas, "funcionarios_processados": funcionarios}
    assert indicadores == {"empresas_integradas": 2, "funcionarios_processados": 35 + 70}
    assert planejamento.resumir(conexao)["cadastrados"] == funcionarios
    # O filtro respeita o escopo: só a Vale Verde
    assert planejamento.indicadores(conexao, empresa_id="EMP004")["funcionarios_processados"] == 70


def test_filtro_pela_data_de_referencia_da_carga(conexao, verdade):
    """A data de referência informada no envio vira filtro; outra data não traz ninguém."""
    _aurora_no_planejamento(conexao, verdade)
    assert planejamento.valores_para_filtro(conexao, "data_referencia") == ["2026-09-01"]
    assert planejamento.resumir(conexao, data_referencia="2026-09-01") == planejamento.resumir(conexao)
    assert planejamento.resumir(conexao, data_referencia="2025-01-01") == _contagens()


def test_numeros_rastreaveis_ate_o_arquivo_homologado(conexao, verdade):
    """A tabela "de onde vêm os números" aponta o arquivo homologado e quantas pessoas ele trouxe, sem CPF."""
    processamento_id = _aurora_no_planejamento(conexao, verdade)
    fontes = planejamento.por_arquivo(conexao)
    assert len(fontes) == 1
    assert fontes[0]["arquivo"] == "aurora_carga_inicial.xlsx" and fontes[0]["funcionarios"] == 35
    assert fontes[0]["processamento_id"] == processamento_id and fontes[0]["data_referencia"] == "2026-09-01"
    conteudo = json.dumps(fontes)
    for cpf in _cpfs_do_arquivo("aurora_carga_inicial", verdade):
        assert cpf not in conteudo


def test_banco_antigo_continua_intacto_ate_o_script_e_depois_perde_as_colunas_da_base(conexao):
    """Tabela de antes (com classificação, contato e segmento, sem a data e com a visão antiga): abrir o planejamento
    não apaga nada (a versão antiga, no ar, ainda lê as colunas); o script da junção tira as colunas e a visão, e a
    pessoa continua Cadastrada, aguardando o retorno."""
    conexao.execute("""CREATE TABLE planejamento_funcionario (empresa_id TEXT NOT NULL, cpf_hash TEXT NOT NULL,
                       processamento_id TEXT NOT NULL, classificacao TEXT NOT NULL, autoriza_contato INTEGER NOT NULL,
                       segmento TEXT NOT NULL, uf TEXT NOT NULL, municipio TEXT NOT NULL,
                       codigo_unidade TEXT NOT NULL, nome_unidade TEXT NOT NULL, criado_em TEXT NOT NULL,
                       data_referencia TEXT NOT NULL DEFAULT '', PRIMARY KEY (empresa_id, cpf_hash))""")
    conexao.execute("INSERT INTO planejamento_funcionario VALUES ('EMP001', 'h', 'p', 'NAO_CORRENTISTA', 0, "
                    "'Plus', 'SP', 'Campinas', 'AUR-01', 'Fábrica', '2026-09-24', '')")
    conexao.execute("CREATE VIEW resumo_planejamento AS SELECT empresa_id, classificacao FROM planejamento_funcionario")
    # Abrir e consultar o planejamento conta a pessoa, sem apagar nada do banco
    assert planejamento.resumir(conexao) == _contagens(cadastrados=1, aguardando_retorno=1)
    colunas = banco.colunas_da_tabela(conexao, "planejamento_funcionario")
    assert "classificacao" in colunas and "segmento" in colunas
    visao = conexao.execute("SELECT name FROM sqlite_master WHERE type = 'view' AND name = 'resumo_planejamento'")
    assert visao.fetchone() is not None
    # O script da junção tira as três colunas e a visão; a pessoa continua contada
    assert tirar_a_base_do_planejamento.tirar_colunas_da_base_antiga(conexao) == ["classificacao", "autoriza_contato",
                                                                                 "segmento"]
    colunas = banco.colunas_da_tabela(conexao, "planejamento_funcionario")
    assert "classificacao" not in colunas and "segmento" not in colunas and "data_referencia" in colunas
    assert planejamento.resumir(conexao) == _contagens(cadastrados=1, aguardando_retorno=1)
    # Rodar de novo não faz nada
    assert tirar_a_base_do_planejamento.tirar_colunas_da_base_antiga(conexao) == []


# ---------- As rotas do simulador ----------

@pytest.fixture()
def banco_proprio(tmp_path, monkeypatch):
    """Um banco só deste teste, com um usuário do banco e um da empresa (nada vaza para os outros testes)."""
    monkeypatch.setattr(config, "CAMINHO_BANCO", tmp_path / "simulador_api.db")
    conexao_do_teste = auth.conectar()
    auth.cadastrar_usuario(conexao_do_teste, "simulador.banco", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "simulador.empresa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()


def navegador_logado(login: str) -> TestClient:
    """Um navegador de mentira já logado com o usuário informado."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200
    return navegador


# As rotas novas do simulador, com um corpo válido para cada uma
ROTAS_DO_SIMULADOR = [
    ("post", "/api/banco/planejamento/ganho", {"filtros": {}, "premissas": {"percentual_novas_contas": "20"},
                                               "clientes_da_empresa": 10}),
    ("get", "/api/banco/planejamento/base", None),
    ("post", "/api/banco/planejamento/simulacoes", {"nome": "Teste", "filtros": {}, "premissas": {}}),
    ("get", "/api/banco/planejamento/simulacoes", None),
    ("get", "/api/banco/planejamento", None),
]


def test_rotas_do_simulador_sao_so_do_banco(banco_proprio):
    """Sem login: 401. Empresa: 403. E a empresa não conseguiu salvar nada."""
    anonimo = TestClient(aplicacao, follow_redirects=False)
    empresa = navegador_logado("simulador.empresa")
    for metodo, rota, corpo in ROTAS_DO_SIMULADOR:
        if metodo == "post":
            assert anonimo.post(rota, json=corpo).status_code == 401
            assert empresa.post(rota, json=corpo).status_code == 403
        else:
            assert anonimo.get(rota).status_code == 401
            assert empresa.get(rota).status_code == 403
    assert navegador_logado("simulador.banco").get("/api/banco/planejamento/simulacoes").json() == []


def test_rota_simula_sem_gravar_e_salva_com_nome(banco_proprio):
    """O simulador calcula com os valores enviados sem gravar; a estimativa substitui os enviados; salvar pede nome."""
    especialista = navegador_logado("simulador.banco")
    # Os clientes que a empresa enviou (a Aurora, sem nada no banco do teste): zero
    base = especialista.get("/api/banco/planejamento/base?empresa_id=EMP001").json()
    assert base == {"empresa_id": "EMP001", "cadastrados": 0, "em_analise": 0, "enviados": 0}
    assert especialista.get("/api/banco/planejamento/base?empresa_id=EMP999").status_code == 400
    # Com os enviados (a tela manda o número que recebeu) e as três taxas
    corpo = {"filtros": {"empresa_id": "EMP001"}, "premissas": dict(TAXAS_DO_EXEMPLO), "clientes_da_empresa": 312}
    simulado = especialista.post("/api/banco/planejamento/ganho", json=corpo).json()
    assert simulado["base"] == {"clientes": 312, "origem": "empresa"}
    assert simulado["simulacao"]["total"] == "229997.66" and simulado["alteradas"] == []
    assert simulado["confirmado"]["com_retorno"] == 0
    # A estimativa da especialista substitui os enviados
    corpo["premissas"]["clientes_estimados"] = "1000"
    estimado = especialista.post("/api/banco/planejamento/ganho", json=corpo).json()
    assert estimado["base"] == {"clientes": 1000, "origem": "estimativa"}
    # Simular não grava nada: nem simulação, nem versão oficial
    assert especialista.get("/api/banco/planejamento/simulacoes").json() == []
    assert especialista.get("/api/banco/premissas").json()["versao"] == 1
    # Valor inválido: 400 com a mensagem para a pessoa
    recusado = especialista.post("/api/banco/planejamento/ganho", json={
        "premissas": {"percentual_novas_contas": "150"}, "clientes_da_empresa": 10})
    assert recusado.status_code == 400 and "entre 0% e 100%" in recusado.json()["detail"]
    # Salvar sem nome: 400; com nome: aparece na lista com quem, os valores, a base e o ganho
    sem_nome = especialista.post("/api/banco/planejamento/simulacoes", json={"premissas": {}})
    assert sem_nome.status_code == 400 and "nome" in sem_nome.json()["detail"]
    corpo["nome"] = "Quadro inteiro"
    salva = especialista.post("/api/banco/planejamento/simulacoes", json=corpo).json()
    assert salva["nome"] == "Quadro inteiro" and salva["usuario"] == "simulador.banco"
    assert salva["base"] == {"clientes": 1000, "origem": "estimativa"}
    assert salva["valores"]["clientes_estimados"] == 1000 and salva["filtros"]["empresa_id"] == "EMP001"
    lista = especialista.get("/api/banco/planejamento/simulacoes").json()
    assert len(lista) == 1 and lista[0]["nome"] == "Quadro inteiro"
    # As oficiais continuam a v1
    assert especialista.get("/api/banco/premissas").json()["vigente"]["mob_cliente_folha"] == "2090.62"


def test_base_da_empresa_soma_cadastrados_e_em_analise(conexao, verdade, monkeypatch):
    """Os clientes que a empresa enviou são os cadastrados mais os em análise pelo banco; sem empresa, a carteira."""
    from services import acompanhamento
    _aurora_no_planejamento(conexao, verdade)
    monkeypatch.setattr(acompanhamento, "pessoas_em_analise_pelo_banco", lambda conexao, empresa_id: 3)
    base = portal_do_banco.base_da_empresa(conexao, "EMP001")
    assert base == {"empresa_id": "EMP001", "cadastrados": 35, "em_analise": 3, "enviados": 38}
    # A carteira toda: a Aurora é a única com cadastrados; cada empresa tem 3 em análise (o falso de cima)
    carteira = portal_do_banco.base_da_empresa(conexao, None)
    assert carteira["cadastrados"] == 35 and carteira["enviados"] == 35 + carteira["em_analise"]
    with pytest.raises(ValueError, match="Empresa não encontrada"):
        portal_do_banco.base_da_empresa(conexao, "EMP999")


def test_simulador_traz_o_confirmado_da_empresa_e_a_tabela_por_empresa_segue_a_empresa(conexao, verdade):
    """O simulador manda o que o banco já confirmou da empresa; com uma empresa no filtro, a tabela é só dela."""
    _aurora_no_planejamento(conexao, verdade)
    simulacao = portal_do_banco.simular(conexao, {"empresa_id": "EMP001"}, {}, 35)
    assert simulacao["confirmado"]["cadastrados"] == 35 and simulacao["simulacao"]["total"] is None
    # Sem empresa: a Aurora é a única com números; com a Horizonte (sem Cadastrados): tabela vazia
    todas = portal_do_banco.numeros_do_planejamento(conexao, {})["por_empresa"]
    empresas_da_tabela = []
    for linha in todas:
        empresas_da_tabela.append(linha["empresa_id"])
    assert empresas_da_tabela == ["EMP001"]
    so_a_horizonte = portal_do_banco.numeros_do_planejamento(conexao, {"empresa_id": "EMP002"})["por_empresa"]
    assert so_a_horizonte == []


# ---------- Uma conta só: o mesmo número em todas as telas ----------

def test_o_mesmo_numero_em_todas_as_telas(conexao, verdade, monkeypatch):
    """O retorno do banco da Aurora (2 contas novas, 2 correntistas gravados antes do ADR-149, com a situação que não é
    mais lida, e 1 conta antiga sem o tipo) dá os MESMOS números no painel de Indicadores, no cartão e no Início da
    empresa, na lista de funcionários, no Endomarketing e na carteira do banco. A conta antiga, sem o tipo, aguarda
    (o banco ainda não disse o status)."""
    from agents import endomarketing
    from services import acompanhamento
    monkeypatch.setattr(contas_abertas, "retorno_por_cpf", RETORNO_POR_CPF_DE_VERDADE)
    _aurora_no_planejamento(conexao, verdade)
    cpfs = _cpfs_do_arquivo("aurora_carga_inicial", verdade)
    # As baixas do banco, direto na tabela (a mesma que o arquivo grava)
    contas_abertas.retorno_por_cpf(conexao, [])
    baixas = ((cpfs[0], "NOVA_CONTA", None), (cpfs[1], "NOVA_CONTA", None), (cpfs[2], "CORRENTISTA", "ATIVO"),
              (cpfs[3], "CORRENTISTA", "INATIVO"), (cpfs[4], None, None))
    for cpf, tipo_conta, situacao in baixas:
        conexao.execute("INSERT INTO contas_abertas (empresa_id, cpf, data_abertura, agencia, conta, codigo_banco, "
                        "arquivo_id, baixa_em, tipo_conta, situacao_correntista) VALUES "
                        "('EMP001', ?, '2026-09-20', '0001', '12345-6', '033', 'arq-1', '2026-09-21T10:00:00+00:00', "
                        "?, ?)", (cpf, tipo_conta, situacao))
    conexao.execute("INSERT INTO arquivos_de_contas (arquivo_id, nome_arquivo, enviado_por, enviado_em, situacao, "
                    "resultado, empresa_id) VALUES ('arq-1', 'contas.csv', 'teste.banco', '2026-09-21T10:00:00+00:00', "
                    "?, '{}', 'EMP001')", (contas_abertas.CONFIRMADO,))
    conexao.commit()
    # 1. O painel de Indicadores (a classificação de cada pessoa)
    painel = planejamento.resumir(conexao, empresa_id="EMP001")
    assert (painel["contas_abertas"], painel["correntistas_marcados"], painel["aguardando_retorno"]) == (2, 2, 31)
    # 2. A conta única das telas das contas: os mesmos números
    unica = contas_abertas.retorno_da_empresa(conexao, "EMP001")
    assert unica["cadastrados"] == painel["cadastrados"]
    assert unica["contas_abertas"] == painel["contas_abertas"]
    assert unica["ja_correntistas"] == painel["correntistas_marcados"]
    assert unica["aguardando_retorno"] == painel["aguardando_retorno"]
    # 3. O cartão da empresa (Acompanhar) e a carteira/Visão geral do banco: 4 com conta
    cartao = contas_abertas.contas_para_a_empresa(conexao, "EMP001")
    assert cartao["com_conta"] == 4 and cartao["contas_abertas"] == 2 and cartao["ja_correntistas"] == 2
    assert "2 abriram a conta agora e 2 já eram correntistas" in cartao["texto"]
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["com_conta"] == 4
    # 4. O Início da empresa e a sugestão do Endomarketing: quem aguarda
    assert endomarketing.consultar_resumo_equipe(conexao, "EMP001")["quantidade"] == painel["aguardando_retorno"]
    # 5. A lista de funcionários da empresa: 2 "Conta aberta", 2 "Já é correntista"; nunca ATIVO/INATIVO
    situacoes = {}
    for funcionario in acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001"):
        situacoes[funcionario["situacao"]] = situacoes.get(funcionario["situacao"], 0) + 1
        assert "ATIVO" not in str(funcionario.values())
    assert situacoes.get("Conta aberta") == 2 and situacoes.get("Já é correntista") == 2
    assert situacoes.get("Cadastrado") == painel["aguardando_retorno"]


def test_o_correntista_e_um_grupo_so_e_a_situacao_e_a_folha_antigas_nao_contam(conexao, verdade, retorno_do_banco):
    """ADR-149: o arquivo só diz se a pessoa já era correntista. Um retorno gravado antes (com a situação e a folha)
    conta como correntista, do mesmo jeito, qualquer que fosse a situação ou a folha."""
    _aurora_no_planejamento(conexao, verdade)
    cpfs = _cpfs_do_arquivo("aurora_carga_inicial", verdade)
    retorno_do_banco["EMP001"] = {
        cpfs[0]: {"tipo_conta": "CORRENTISTA", "situacao_correntista": "ATIVO", "folha_ja_identificada": "N"},
        cpfs[1]: {"tipo_conta": "CORRENTISTA", "situacao_correntista": "INATIVO", "folha_ja_identificada": "N"},
        cpfs[2]: {"tipo_conta": "CORRENTISTA", "situacao_correntista": "ATIVO", "folha_ja_identificada": "S"},
        cpfs[3]: {"tipo_conta": "CORRENTISTA"},
        cpfs[4]: {"tipo_conta": "NOVA_CONTA"},
    }
    assert planejamento.resumir(conexao) == _contagens(
        cadastrados=35, aguardando_retorno=30, contas_abertas=1, correntistas_marcados=4)
    # No ganho, os 4 correntistas e a conta nova somam: 4 × 366,62 + 1 × 2.090,62
    ganho = planejamento.projetar_ganho(planejamento.resumir(conexao), parametros.premissas_ativas(conexao))
    assert ganho["realizado"]["total"] == Decimal("3557.10")
