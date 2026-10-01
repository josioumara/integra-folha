"""Normalizador determinístico. Nada corrigido por suposição; tudo bate com o gabarito."""
import csv
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from models.contratos import (EstadoProcessamento, ItemMapeamento, MappingPlan, StatusMapeamento, TipoCampo,
                              carregar_layout)
from services import auditoria, banco, ingestao, mapeamentos, normalizador, processamentos
from services.normalizador import NaoConvertido

# Os arquivos das empresas, os gabaritos e o layout
RAIZ = Path(__file__).resolve().parent.parent
ENVIOS = RAIZ / "data" / "synthetic" / "envios"
GABARITOS = []
for caminho_do_gabarito in sorted((RAIZ / "data" / "golden").glob("*.json")):
    GABARITOS.append(json.loads(caminho_do_gabarito.read_text(encoding="utf-8")))
CAMPOS = carregar_layout()
TIPO_DO_CAMPO = {}
for campo_do_layout in CAMPOS:
    TIPO_DO_CAMPO[campo_do_layout.campo] = campo_do_layout.tipo


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


@pytest.fixture(scope="module")
def verdade():
    """O gabarito de cada funcionário: funcionario_id -> campos corretos."""
    funcionarios = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            funcionarios[linha["funcionario_id"]] = linha
    return funcionarios


def _campo_da_coluna(gabarito, coluna) -> str:
    """O campo de uma coluna no gabarito; a ambígua vale pelo campo após a confirmação."""
    campo = gabarito["mapeamento"][coluna]
    if campo is None:
        campo = gabarito["colunas_ambiguas"][coluna]["campo_apos_confirmacao"]
    return campo


def plano_do_gabarito(gabarito) -> MappingPlan:
    """O mapeamento que a empresa aprovaria: o do gabarito, com as ambíguas já decididas."""
    itens = []
    for coluna in gabarito["mapeamento"]:
        itens.append(ItemMapeamento(coluna=coluna, status=StatusMapeamento.PROPOSTO, justificativa="gabarito",
                                    campo=_campo_da_coluna(gabarito, coluna)))
    for coluna in gabarito["colunas_extras"]:
        itens.append(ItemMapeamento(coluna=coluna, status=StatusMapeamento.NAO_MAPEADO, justificativa="extra"))
    return MappingPlan(processamento_id="t", versao_layout=1, configuracao="B0", modelo="gabarito",
                       versao_prompt="-", itens=itens, chamou_llm=False)


def canonico(campo, valor):
    """O valor do gabarito no formato canônico do layout (telefone e CEP só com dígitos)."""
    if TIPO_DO_CAMPO[campo] in (TipoCampo.TELEFONE, TipoCampo.CEP):
        return re.sub(r"\D", "", valor) or None
    return valor or None


def normalizar(gabarito, decisoes=None):
    """Lê o arquivo da empresa e normaliza com o mapeamento do gabarito."""
    leitura = ingestao.ler_arquivo((ENVIOS / gabarito["arquivo"]).read_bytes(), gabarito["arquivo"])
    return normalizador.normalizar(leitura, plano_do_gabarito(gabarito), CAMPOS, decisoes)


def _gabarito(nome_do_arquivo: str) -> dict:
    """O gabarito de um arquivo, pelo nome."""
    for gabarito in GABARITOS:
        if gabarito["arquivo"] == nome_do_arquivo:
            return gabarito
    raise KeyError(nome_do_arquivo)


def _nome_do_arquivo(gabarito: dict) -> str:
    """O nome do caso de teste: o arquivo do gabarito."""
    return gabarito["arquivo"]


def _decisoes_da_brisa(gabarito) -> dict | None:
    """Na Brisa, a empresa informa que a matrícula tem 5 dígitos; nos outros arquivos, nenhuma decisão."""
    if not gabarito["arquivo"].startswith("brisa"):
        return None
    decisoes = {}
    for coluna, campo in gabarito["mapeamento"].items():
        if campo == "matricula":
            decisoes[coluna] = "zeros:5"
    return decisoes


def _primeiro_cpf_valido_comecando_com_zero() -> str:
    """Um CPF válido que começa com 0 (o Excel perderia esse zero)."""
    for numero in range(1000000000, 1000100000):
        cpf = "0" + str(numero)
        if normalizador.cpf_valido(cpf):
            return cpf
    raise AssertionError("nenhum CPF válido na faixa")


# ---------- Conversões ----------

def test_os_dois_jeitos_de_escrever_o_salario_viram_o_mesmo_valor():
    """ "R$ 5.200,50" e "5200.5" viram o mesmo 5200.50."""
    assert normalizador.converter_decimal("R$ 5.200,50", "virgula") == Decimal("5200.50")
    assert normalizador.converter_decimal("5200.5", "ponto") == Decimal("5200.50")
    assert normalizador.converter_decimal("R$ 5.200,50", None) == normalizador.converter_decimal("5200.5", None)


@pytest.mark.parametrize("valor, convencao, esperado", [
    ("1.234,5", "virgula", Decimal("1234.50")), ("3150", None, Decimal("3150.00")),
    ("1.234.567", None, Decimal("1234567.00")), ("-10,00", "virgula", Decimal("-10.00"))])
def test_conversao_decimal(valor, convencao, esperado):
    """Casos de dinheiro: milhar, sem centavos, milhões e negativo."""
    assert normalizador.converter_decimal(valor, convencao) == esperado


@pytest.mark.parametrize("valor", ["três mil e cem reais", "abc", "10,555", "12,5.3"])
def test_valor_que_nao_da_para_converter_nao_e_adivinhado(valor):
    """Por extenso, texto, três casas ou mal formado: não converte, não adivinha."""
    convencao = "virgula" if "," in valor else None
    with pytest.raises(NaoConvertido):
        normalizador.converter_decimal(valor, convencao)


def test_data_ambigua_vira_pendencia_e_a_decisao_da_empresa_resolve():
    """Sem desempate, a data é ambígua; com a decisão (ou dia > 12), converte; data inexistente é recusada."""
    assert normalizador.ordem_das_datas(["01/02/2026", "03/04/2026"]) is None
    assert normalizador.ordem_das_datas(["01/02/2026", "25/12/2025"]) == "DMY"
    with pytest.raises(NaoConvertido, match="ambígua"):
        normalizador.converter_data("01/02/2026", None)
    assert normalizador.converter_data("01/02/2026", "DMY") == date(2026, 2, 1)
    # Número de série do Excel
    assert normalizador.converter_data("45536", None) == date(2024, 9, 1)
    with pytest.raises(NaoConvertido, match="inexistente"):
        normalizador.converter_data("31/02/2026", "DMY")


def test_cpf_so_recupera_zeros_quando_o_digito_verificador_confirma():
    """O zero perdido só volta se o CPF veio do Excel como número E o dígito verificador confirma."""
    assert normalizador.converter_documento("529.982.247-25", 11, normalizador.cpf_valido, False) == ("52998224725", False)
    # "05...": o Excel guardou como número e perdeu o zero; o DV confirma a recomposição
    cpf = _primeiro_cpf_valido_comecando_com_zero()
    assert normalizador.converter_documento(cpf.lstrip("0"), 11, normalizador.cpf_valido, True) == (cpf, True)
    # Se não veio do Excel como número, não completa
    with pytest.raises(NaoConvertido):
        normalizador.converter_documento(cpf.lstrip("0"), 11, normalizador.cpf_valido, False)


def test_dominios_aceitam_sinonimos_e_recusam_o_resto():
    """Listas fechadas aceitam sinônimos conhecidos; o resto é recusado."""
    dominios = normalizador.carregar_dominios()
    assert normalizador.converter_dominio("Pró-labore", "tipo_renda", dominios) == "PRO_LABORE"
    assert normalizador.converter_dominio("masculino", "sexo", dominios) == "M"
    assert normalizador.converter_dominio("união estável", "estado_civil", dominios) == "União estável"
    with pytest.raises(NaoConvertido):
        normalizador.converter_dominio("Estagiário", "tipo_renda", dominios)


# ---------- Plano de transformação (allowlist) ----------

def test_plano_so_opera_colunas_aprovadas_e_operacoes_permitidas():
    """Operação fora da allowlist, coluna fora do mapeamento e coluna AMBIGUO são recusadas."""
    plano = plano_do_gabarito(GABARITOS[0])
    passos = normalizador.plano_de_transformacao(plano, CAMPOS)
    for passo in passos:
        assert set(passo["operacoes"]) <= normalizador.ALLOWLIST
    with pytest.raises(ValueError, match="fora da lista"):
        normalizador.validar_plano([dict(passos[0], operacoes=["corrigir_salario"])], plano, CAMPOS)
    with pytest.raises(ValueError, match="fora do mapeamento"):
        normalizador.validar_plano([dict(passos[0], coluna="Coluna inventada")], plano, CAMPOS)
    item_ambiguo = plano.itens[0].model_copy(update={"status": StatusMapeamento.AMBIGUO})
    plano_com_ambiguo = plano.model_copy(update={"itens": [item_ambiguo]})
    with pytest.raises(ValueError, match="AMBIGUO"):
        normalizador.plano_de_transformacao(plano_com_ambiguo, CAMPOS)


# ---------- Os arquivos da demo contra o gabarito ----------

@pytest.mark.parametrize("gabarito", GABARITOS, ids=_nome_do_arquivo)
def test_arquivo_bate_com_o_gabarito_em_valor_e_identidade(gabarito, verdade):
    """Critério da fase. Exceções esperadas: células com erro injetado e pendências de coluna."""
    resultado = normalizar(gabarito, _decisoes_da_brisa(gabarito))
    # As células com erro injetado de propósito não entram na comparação
    celulas_com_erro = set()
    for erro in gabarito["erros"]:
        celulas_com_erro.add((erro["linha"], erro["campo"]))
    campos = []
    for coluna in gabarito["mapeamento"]:
        campos.append(_campo_da_coluna(gabarito, coluna))
    for numero_da_linha, (registro, funcionario_id) in enumerate(zip(resultado.registros, gabarito["funcionario_ids"]),
                                                                 start=1):
        for campo in campos:
            if (numero_da_linha, campo) not in celulas_com_erro:
                assert registro[campo] == canonico(campo, verdade[funcionario_id][campo]), (numero_da_linha, campo)
    assert resultado.conferencia["linhas_conferem"] and resultado.conferencia["vazios_conferem"]
    assert not resultado.pendencias_de_coluna


def test_matricula_sem_zeros_fica_pendente_sem_decisao():
    """Sem a decisão da empresa, a matrícula da Brisa fica pendente."""
    resultado = normalizar(_gabarito("brisa_carga_inicial.xlsx"))
    tipos_de_pendencia = []
    for pendencia in resultado.pendencias_de_coluna:
        tipos_de_pendencia.append(pendencia["tipo"])
    assert tipos_de_pendencia == ["ZEROS_A_ESQUERDA"]


def test_salario_por_extenso_nao_e_convertido_e_fica_registrado():
    """ "três mil e cem reais" não vira número: fica registrado, na linha certa do arquivo."""
    gabarito = _gabarito("prisma_carga_inicial.csv")
    resultado = normalizar(gabarito)
    campos_e_motivos = []
    for nao_convertido in resultado.nao_convertidos:
        campos_e_motivos.append((nao_convertido["campo"], nao_convertido["motivo"]))
    assert campos_e_motivos == [("valor_renda", "valor não numérico")]
    linha_do_erro = None
    for erro in gabarito["erros"]:
        if erro["tipo"] == "VALOR_COMO_TEXTO":
            linha_do_erro = erro["linha"]
    # Linha no arquivo: o cabeçalho é a linha 1
    assert resultado.nao_convertidos[0]["linha"] == linha_do_erro + 1


def test_soma_dos_salarios_confere_com_o_gabarito(verdade):
    """A soma das rendas convertidas é a soma do gabarito."""
    gabarito = _gabarito("aurora_carga_inicial.xlsx")
    soma_esperada = Decimal("0")
    for funcionario_id in gabarito["funcionario_ids"]:
        soma_esperada += Decimal(verdade[funcionario_id]["valor_renda"])
    assert Decimal(normalizar(gabarito).conferencia["soma_valor_renda"]) == soma_esperada


def test_data_de_coluna_so_com_dias_baixos_usa_a_convencao_do_arquivo():
    """Coluna sem desempate usa a ordem das outras datas do arquivo, e o log diz isso."""
    resultado = normalizar(_gabarito("horizonte_carga_inicial.csv"))
    entrada_do_log = None
    for entrada in resultado.log:
        if entrada["campo"] == "data_referencia_renda":
            entrada_do_log = entrada
    assert "outras datas do arquivo" in entrada_do_log["decisao"]


# ---------- Persistência e status ----------

def test_executar_exige_mapeamento_aprovado_e_registra_so_contagens(tmp_path):
    """Sem aceite não padroniza; com aceite, padroniza, guarda e registra só contagens na auditoria."""
    conexao = banco.conectar(tmp_path / "t.db")
    conteudo = "Colaborador;CPF;Salário Bruto;Dt. Admissão\nAna;529.982.247-25;R$ 3.150,00;25/01/2024\n".encode()
    perfil = processamentos.receber_arquivo(conexao, conteudo, "n.csv", "EMP001", date(2026, 9, 1), "t").perfil
    with pytest.raises(ValueError, match="aprovado"):
        normalizador.executar(conexao, perfil.processamento_id, "EMP001")
    mapeamentos.interpretar_processamento(conexao, perfil.processamento_id, "EMP001", configuracao="B2")
    mapeamentos.aprovar(conexao, perfil.processamento_id, "EMP001", {}, "rh")
    resultado = normalizador.executar(conexao, perfil.processamento_id, "EMP001")
    registro = resultado.registros[0]
    assert (registro["cpf"], registro["valor_renda"], registro["data_admissao"]) == ("52998224725", "3150.00", "2024-01-25")
    assert processamentos.obter(conexao, perfil.processamento_id).status == EstadoProcessamento.NORMALIZADO
    assert normalizador.obter(conexao, perfil.processamento_id).registros == resultado.registros
    ultimo_evento = auditoria.eventos(conexao, perfil.processamento_id)[-1]
    # Nenhum dado pessoal no evento
    assert ultimo_evento["tipo"] == "NORMALIZADO" and "52998224725" not in json.dumps(ultimo_evento)


def test_datas_por_extenso_e_com_ano_curto_sao_convertidas():
    """ADR-73: o texto corrido traz datas escritas ("14 de setembro de 1991", "03 jun 2024") e ano com 2 dígitos."""
    converter_data = normalizador.converter_data
    assert converter_data("14 de setembro de 1991", None).isoformat() == "1991-09-14"
    assert converter_data("03 jun 2024", None).isoformat() == "2024-06-03"
    assert converter_data("8 de jul. de 2024", None).isoformat() == "2024-07-08"
    assert converter_data("08 de março de 2024", None).isoformat() == "2024-03-08"
    # Ano curto: até o ano atual é deste século; acima, do século passado
    assert converter_data("06/05/24", "DMY").isoformat() == "2024-05-06"
    assert converter_data("07-03-79", "DMY").isoformat() == "1979-03-07"


def test_telefone_com_codigo_do_brasil_perde_o_55():
    """ADR-73: "+55 71 99205-7734" fica DDD + número; o DDD 55 (RS) com 11 dígitos não é mexido."""
    campo = None
    for campo_do_layout in CAMPOS:
        if campo_do_layout.campo == "telefone_celular":
            campo = campo_do_layout
    assert normalizador.converter_valor("+55 71 99205-7734", campo) == "71992057734"
    assert normalizador.converter_valor("55 99123-4567", campo) == "55991234567"


def test_conferir_valores_para_o_campo_escolhido_pela_empresa():
    """A tela avisa na hora quando a empresa põe uma coluna num campo de outro tipo (nada é gravado)."""
    campos = {}
    for campo in carregar_layout():
        campos[campo.campo] = campo
    # CPFs numa data: nenhum serve
    conferencia = normalizador.conferir_valores_para_o_campo(["529.982.247-25", "", "111.444.777-35"],
                                                            campos["data_admissao"])
    assert conferencia["preenchidos"] == 2 and conferencia["nao_servem"] == 2
    # Datas numa data: servem (mesmo sem saber se é dia/mês ou mês/dia)
    assert normalizador.conferir_valores_para_o_campo(["01/02/2026", "03/04/2026"],
                                                      campos["data_admissao"])["nao_servem"] == 0
    # Texto aceita texto; número sem letra nenhuma num campo de texto é estranhado
    assert normalizador.conferir_valores_para_o_campo(["Analista"], campos["cargo"])["nao_servem"] == 0
    assert normalizador.conferir_valores_para_o_campo(["05/03/2026"], campos["cargo"])["nao_servem"] == 1


@pytest.mark.parametrize("valor, ordem, esperado", [
    ("14/09/1991", None, "1991-09-14"),          # dia passa de 12: dia/mês
    ("09/14/1991", None, "1991-09-14"),          # jeito americano, o dia passa de 12: mês/dia
    ("01/09/2026", "MDY", "2026-01-09"),         # sem desempate: vale a ordem decidida pela empresa
    ("06/05/24", "DMY", "2024-05-06"),           # ano com 2 dígitos
    ("2026/9/1", None, "2026-09-01"),            # ano primeiro, com barra
    ("2026-09-01T08:30:00", None, "2026-09-01"), # com hora (o Excel e os sistemas exportam assim)
    ("9/14/2026 8:30 PM", None, "2026-09-14"),   # americano com hora
    ("20260901", None, "2026-09-01"),            # compacta, ano primeiro
    ("01092026", "DMY", "2026-09-01"),           # compacta, dia primeiro
    ("1º de maio de 2020", None, "2020-05-01"),  # por extenso, com ordinal
    ("14-Sep-2024", None, "2024-09-14"),         # mês em inglês
    ("14/set/24", None, "2024-09-14"),           # mês abreviado em português, ano curto
    ("Sep 14, 1991", None, "1991-09-14"),        # mês primeiro (americano), por extenso
    ("May 3rd, 2020", None, "2020-05-03"),
])
def test_formatos_de_data_em_portugues_ingles_e_outros(valor, ordem, esperado):
    assert normalizador.converter_data(valor, ordem).isoformat() == esperado


def test_data_ambigua_com_ano_curto_ou_compacta_espera_a_decisao_da_empresa():
    """Sem nenhuma data que desempate, "06/05/24" e "01092026" não são convertidas por suposição."""
    with pytest.raises(NaoConvertido, match="ambígua"):
        normalizador.converter_data("06/05/24", None)
    assert normalizador.ordem_das_datas(["06/05/24", "25/05/24"]) == "DMY"
    assert normalizador.ordem_das_datas(["01092026", "09252026"]) == "MDY"
