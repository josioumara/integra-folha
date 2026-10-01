"""Validador. Regras decidem a severidade; renda fora do padrão é alerta; o LLM só explica."""
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from models.contratos import EstadoProcessamento, carregar_layout
from services import (auditoria, banco, cadastro, correcoes, ingestao, mapeamentos, normalizador, processamentos,
                      validador)
from services.normalizador import Normalizacao
from services.validador import ALERTA, AVISO, BLOQUEANTE
# O parâmetro de cada teste: quais campos são obrigatórios (ADR-143); os erros do gabarito que viram pendência usam a
# mesma tabela da avaliação (o nome do erro no gabarito -> a regra do Validador que deve achá-lo)
from tests.apoio_do_parametro import (OBRIGATORIOS_DA_ADR_143, OBRIGATORIOS_DO_LAYOUT, erros_que_viram_pendencia,
                                      layout_com, marcar_como_obrigatorios)
from tests.test_normalizador import plano_do_gabarito

# Os arquivos das empresas, os gabaritos e o layout
RAIZ = Path(__file__).resolve().parent.parent
ENVIOS = RAIZ / "data" / "synthetic" / "envios"
GABARITOS = {}
for caminho_do_gabarito in sorted((RAIZ / "data" / "golden").glob("*.json")):
    GABARITOS[caminho_do_gabarito.stem] = json.loads(caminho_do_gabarito.read_text(encoding="utf-8"))
CAMPOS = carregar_layout()


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


def _decisoes(nome, gabarito):
    """Na Brisa, a empresa informa que a matrícula tem 5 dígitos; nos outros arquivos, nenhuma decisão."""
    if not nome.startswith("brisa"):
        return None
    decisoes = {}
    for coluna, campo in gabarito["mapeamento"].items():
        if campo == "matricula":
            decisoes[coluna] = "zeros:5"
    return decisoes


def _homologados_da_carga_inicial(nome, verdade):
    """Numa inclusão, os colegas da carga inicial já estão homologados."""
    inicial = GABARITOS[nome.replace("inclusao", "carga_inicial")]
    homologados = []
    for funcionario_id in inicial["funcionario_ids"]:
        pessoa = {}
        for campo in ("cpf", "matricula", "cargo", "tipo_renda", "valor_renda"):
            pessoa[campo] = verdade[funcionario_id][campo]
        homologados.append(pessoa)
    return homologados


def validar_arquivo(nome, verdade):
    """Lê, normaliza e valida um arquivo da demo, como se o mapeamento do gabarito tivesse sido aprovado."""
    gabarito = GABARITOS[nome]
    leitura = ingestao.ler_arquivo((ENVIOS / gabarito["arquivo"]).read_bytes(), gabarito["arquivo"])
    normalizacao = normalizador.normalizar(leitura, plano_do_gabarito(gabarito), CAMPOS, _decisoes(nome, gabarito))
    homologados = []
    if gabarito["tipo_carga"] == "INCLUSAO":
        homologados = _homologados_da_carga_inicial(nome, verdade)
    return validador.validar(normalizacao, CAMPOS, gabarito["empresa_id"], homologados, referencia=date(2026, 9, 1))


def registro(**campos):
    """Um funcionário com todos os campos vazios, menos os informados (linha 2 se não informada)."""
    linha = campos.pop("_linha", 2)
    novo_registro = {"_linha": linha}
    for campo in CAMPOS:
        novo_registro[campo.campo] = None
    novo_registro.update(campos)
    return novo_registro


def normalizacao_de(*registros, campos_mapeados=None):
    """Uma padronização "de mentira" com os registros; por padrão, mapeados são os campos preenchidos."""
    if campos_mapeados is None:
        preenchidos = set()
        for registro_do_teste in registros:
            for campo, valor in registro_do_teste.items():
                if valor and campo != "_linha":
                    preenchidos.add(campo)
        campos_mapeados = sorted(preenchidos)
    plano = []
    for campo in campos_mapeados:
        plano.append({"coluna": campo, "campo": campo, "tipo": "", "operacoes": []})
    return Normalizacao(registros=list(registros), log=[], plano=plano,
                        conferencia={"linhas_conferem": True, "vazios_conferem": True})


def _achados_da_regra(relatorio, regra_id):
    """Os achados de uma regra."""
    achados = []
    for achado in relatorio.achados:
        if achado.regra_id == regra_id:
            achados.append(achado)
    return achados


def _regras(relatorio):
    """As regras que acharam alguma coisa."""
    regras = set()
    for achado in relatorio.achados:
        regras.add(achado.regra_id)
    return regras


# ---------- Os erros injetados, na linha certa, e nada além deles ----------

@pytest.mark.parametrize("nome", list(GABARITOS))
def test_acha_exatamente_os_erros_do_gabarito(nome, verdade):
    """Em cada arquivo, cada erro injetado num campo obrigatório é achado na linha certa, e nenhum outro.

    O erro num campo opcional não vira pendência (ADR-143): o gabarito continua o mesmo, e o filtro é o layout.
    """
    relatorio = validar_arquivo(nome, verdade)
    achado = set()
    for item in relatorio.achados:
        achado.add((item.registro, item.regra_id))
    assert achado == erros_que_viram_pendencia(GABARITOS[nome])


def test_o_erro_do_gabarito_num_campo_opcional_nao_vira_pendencia(verdade):
    """A matrícula repetida da Vale Verde está no gabarito, mas a matrícula é opcional: nada a corrigir (ADR-143)."""
    gabarito = GABARITOS["vale_verde_carga_inicial"]
    assert len(gabarito["erros"]) == 1 and erros_que_viram_pendencia(gabarito) == set()
    relatorio = validar_arquivo("vale_verde_carga_inicial", verdade)
    assert relatorio.achados == [] and relatorio.pronto_para_homologar


def test_cpf_invalido_bloqueia_a_homologacao(verdade):
    """CPF inválido é BLOQUEANTE e aparece como está no cadastro (ADR-101)."""
    relatorio = validar_arquivo("aurora_carga_inicial", verdade)
    cpf = _achados_da_regra(relatorio, "CPF_INVALIDO")[0]
    assert cpf.severidade == BLOQUEANTE and not relatorio.pronto_para_homologar
    # O valor é o CPF de verdade, com os 11 dígitos (sem máscara)
    digitos = ""
    for caractere in cpf.valor:
        if caractere.isdigit():
            digitos += caractere
    assert len(digitos) == 11 and set(digitos) != {"9"}


def test_renda_dez_vezes_a_mediana_e_alerta_nao_acusacao(verdade):
    """Renda fora do padrão é ALERTA, sem acusar ninguém, e pede justificativa."""
    relatorio = validar_arquivo("atlantico_carga_inicial", verdade)
    rendas = _achados_da_regra(relatorio, "RENDA_FORA_DO_CARGO")
    assert rendas
    for achado in rendas:
        assert achado.severidade == ALERTA
        assert "fraude" not in achado.mensagem.lower() and "justifique" in achado.mensagem
    mensagens_com_vezes = 0
    for achado in rendas:
        if "x a " in achado.mensagem:
            mensagens_com_vezes += 1
    assert mensagens_com_vezes > 0


def test_cargo_com_poucos_colegas_usa_a_tabela_de_referencia():
    """Um diretor sozinho é comparado com a tabela de referência do cargo."""
    diretor = registro(cargo="Diretor", tipo_renda="CLT", valor_renda="1100.00")
    relatorio = validador.validar(normalizacao_de(diretor), CAMPOS, "EMP003")
    renda = _achados_da_regra(relatorio, "RENDA_FORA_DO_CARGO")[0]
    assert "referência do cargo" in renda.mensagem


def test_cargo_com_colegas_usa_a_mediana_da_empresa():
    """Com 6 analistas, o que ganha 10 vezes mais é apontado, comparado com a mediana dos colegas."""
    rendas_dos_analistas = ["5000.00", "5200.00", "5400.00", "5100.00", "5300.00", "52000.00"]
    colegas = []
    for linha, renda in enumerate(rendas_dos_analistas, start=2):
        colegas.append(registro(_linha=linha, cargo="Analista", tipo_renda="CLT", valor_renda=renda))
    relatorio = validador.validar(normalizacao_de(*colegas), CAMPOS, "EMP001")
    rendas = _achados_da_regra(relatorio, "RENDA_FORA_DO_CARGO")
    linhas = []
    for achado in rendas:
        linhas.append(achado.linha)
    assert linhas == [7] and "mediana do cargo na empresa" in rendas[0].mensagem


def test_inclusao_compara_com_colegas_ja_homologados():
    """Na inclusão, a renda é comparada com os colegas já homologados; a matrícula também, quando é obrigatória."""
    homologados = []
    for numero in range(1, 7):
        homologados.append({"cpf": f"{numero:011d}", "matricula": f"{numero:05d}", "cargo": "Vendedor",
                            "tipo_renda": "CLT", "valor_renda": "2800.00"})
    novo = registro(cargo="Vendedor", tipo_renda="CLT", valor_renda="28000.00", matricula="00001", cpf="52998224725")
    # No layout, a matrícula é opcional: a matrícula de outra pessoa não vira pendência (ADR-143)
    regras = _regras(validador.validar(normalizacao_de(novo), CAMPOS, "EMP005", homologados))
    assert "RENDA_FORA_DO_CARGO" in regras and "MATRICULA_JA_HOMOLOGADA" not in regras
    # Com a matrícula obrigatória no parâmetro, a regra da matrícula continua valendo
    campos = layout_com(OBRIGATORIOS_DO_LAYOUT | {"matricula"})
    regras = _regras(validador.validar(normalizacao_de(novo), campos, "EMP005", homologados))
    assert "RENDA_FORA_DO_CARGO" in regras and "MATRICULA_JA_HOMOLOGADA" in regras


# ---------- Outras regras ----------

def test_obrigatorio_sem_coluna_gera_um_achado_so():
    """Coluna obrigatória ausente: um achado por campo, não um por linha."""
    relatorio = validador.validar(normalizacao_de(registro(cpf="52998224725"), registro(_linha=3, cpf="11144477735"),
                                                  campos_mapeados=["cpf"]), CAMPOS, "EMP001")
    sem_coluna = _achados_da_regra(relatorio, "OBRIGATORIO_SEM_COLUNA")
    obrigatorios = 0
    for campo in CAMPOS:
        if campo.obrigatorio:
            obrigatorios += 1
    # Todos menos o CPF
    assert len(sem_coluna) == obrigatorios - 1
    assert "OBRIGATORIO_VAZIO" not in _regras(relatorio)


def test_sem_coluna_diz_se_a_informacao_e_da_empresa_ou_de_cada_pessoa():
    """A coluna que o arquivo inteiro não trouxe (o CPF é sempre único, ADR-124): um dado da
    empresa (o CNPJ do empregador) pode ser informado uma vez para todos; um dado de cada pessoa (o nome) só chega
    num arquivo novo, com a coluna. Quem decide é a marcação "Pode ser igual para todos" do parâmetro."""
    relatorio = validador.validar(normalizacao_de(registro(cpf="52998224725"), campos_mapeados=["cpf"]), CAMPOS,
                                  "EMP001")
    # O achado de cada campo sem coluna
    achado_por_campo = {}
    for achado in _achados_da_regra(relatorio, "OBRIGATORIO_SEM_COLUNA"):
        achado_por_campo[achado.campo] = achado
    # O CNPJ do empregador: dado da empresa, informado uma vez
    cnpj = achado_por_campo["cnpj_empregador"]
    assert cnpj.acao == "Informar o valor uma vez, para todos (é um dado da empresa)"
    assert "único por funcionário" not in cnpj.mensagem
    # O nome: de cada pessoa, só com o arquivo de novo
    nome = achado_por_campo["nome_completo"]
    assert nome.acao == "Enviar o arquivo de novo com esta coluna (a informação é única por funcionário)"
    assert "único por funcionário" in nome.mensagem


def test_datas_incoerentes():
    """Nascimento no futuro e admissão antes do nascimento bloqueiam; efetivação antes da admissão é alerta, quando a
    efetivação é obrigatória (no layout, ela é opcional e não vira pendência, ADR-143)."""
    pessoa = registro(data_nascimento="2030-01-01", data_admissao="2020-01-01", data_efetivacao="2019-01-01")
    campos = layout_com(OBRIGATORIOS_DO_LAYOUT | {"data_efetivacao"})
    relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1))
    severidade_da_regra = {}
    for achado in relatorio.achados:
        severidade_da_regra[achado.regra_id] = achado.severidade
    assert severidade_da_regra["NASCIMENTO_NO_FUTURO"] == BLOQUEANTE
    assert severidade_da_regra["ADMISSAO_ANTES_DO_NASCIMENTO"] == BLOQUEANTE
    assert severidade_da_regra["EFETIVACAO_ANTES_DA_ADMISSAO"] == ALERTA
    # No layout, a efetivação é opcional: a mesma data não vira pendência
    relatorio = validador.validar(normalizacao_de(pessoa), CAMPOS, "EMP001", referencia=date(2026, 9, 1))
    assert "EFETIVACAO_ANTES_DA_ADMISSAO" not in _regras(relatorio)


def test_cnpj_de_outra_empresa_bloqueia():
    """CNPJ válido, mas de outra empresa: bloqueia."""
    # CNPJ válido da Horizonte, num arquivo da Aurora
    pessoa = registro(cnpj_empregador="88805929000139")
    relatorio = validador.validar(normalizacao_de(pessoa), CAMPOS, "EMP001")
    assert "CNPJ_DE_OUTRA_EMPRESA" in _regras(relatorio)


def test_aviso_nao_impede_homologacao():
    """Só avisos: pode homologar. O e-mail e o telefone estão obrigatórios neste parâmetro de teste; num campo
    opcional, eles nem viram aviso (ADR-143)."""
    pessoa = registro(email_pessoal="sem-arroba", telefone_celular="123")
    campos = layout_com({"email_pessoal", "telefone_celular"})
    relatorio = validador.validar(normalizacao_de(pessoa, campos_mapeados=["email_pessoal", "telefone_celular"]),
                                  campos, "EMP001")
    severidades = set()
    for achado in relatorio.achados:
        severidades.add(achado.severidade)
    assert severidades == {AVISO} and relatorio.pronto_para_homologar


# ---------- Campo opcional não abre pendência automática (ADR-143); o pedido do banco é a exceção ----------

# Um problema em cada tipo de campo: (o campo, o valor com problema, a regra que o acha quando o campo é obrigatório).
# O CEP "7" é o caso que achou o defeito; os outros são variações de outros tipos (a regra vale para todos)
PROBLEMAS_EM_UM_CAMPO = [
    ("cep_residencial", "7", "CEP_INVALIDO"),                             # o caso do pedido
    ("cep_comercial", "0100100099", "CEP_INVALIDO"),                      # outro CEP, com dígitos a mais
    ("telefone_celular", "123", "TELEFONE_INVALIDO"),                     # o telefone sem DDD
    ("email_corporativo", "rh.empresa.com.br", "EMAIL_INVALIDO"),         # o e-mail sem arroba
    ("cnpj_empregador", "88805929000139", "CNPJ_DE_OUTRA_EMPRESA"),       # CNPJ válido, de outra empresa
    ("cnpj_grupo", "11222333000180", "CNPJ_INVALIDO"),                    # CNPJ com o dígito errado
    ("data_efetivacao", "2019-01-01", "EFETIVACAO_ANTES_DA_ADMISSAO"),    # a data incoerente com a admissão
]


def pessoa_com_os_obrigatorios_da_adr_143() -> dict:
    """Uma pessoa com o CPF, a renda e a admissão certos (os obrigatórios da ADR-143 no layout_v1)."""
    return registro(cpf="52998224725", valor_renda="3000.00", data_admissao="2020-01-01")


@pytest.mark.parametrize("campo, valor, regra", PROBLEMAS_EM_UM_CAMPO)
def test_campo_opcional_com_problema_nao_vira_pendencia(campo, valor, regra):
    """Com o parâmetro da ADR-143, o valor com problema num campo opcional não gera achado, e o envio pode seguir."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa[campo] = valor
    relatorio = validador.validar(normalizacao_de(pessoa), layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1))
    assert relatorio.achados == [] and relatorio.pronto_para_homologar


@pytest.mark.parametrize("campo, valor, regra", PROBLEMAS_EM_UM_CAMPO)
def test_o_mesmo_campo_obrigatorio_vira_pendencia(campo, valor, regra):
    """O mesmo valor, com o campo marcado obrigatório no parâmetro, gera o achado da regra, preso ao campo."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa[campo] = valor
    campos = layout_com(OBRIGATORIOS_DA_ADR_143 | {campo})
    relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1))
    achados_da_regra = _achados_da_regra(relatorio, regra)
    assert len(achados_da_regra) == 1 and achados_da_regra[0].campo == campo


@pytest.mark.parametrize("nascimento, regras_com_o_nascimento_obrigatorio", [
    ("2030-01-01", {"NASCIMENTO_NO_FUTURO", "ADMISSAO_ANTES_DO_NASCIMENTO"}),   # no futuro (o caso conferido)
    ("2021-06-15", {"ADMISSAO_ANTES_DO_NASCIMENTO"}),                           # depois da admissão
    ("2010-03-20", {"ADMISSAO_ANTES_DOS_14"}),                                  # 9 anos na admissão
])
def test_nascimento_opcional_nao_questiona_a_admissao(nascimento, regras_com_o_nascimento_obrigatorio):
    """Com o nascimento opcional (o parâmetro da ADR-143), um nascimento errado não vira pendência, nem presa à
    admissão, que está certa. Com o nascimento obrigatório, as regras das datas continuam valendo."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa["data_nascimento"] = nascimento
    relatorio = validador.validar(normalizacao_de(pessoa), layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1))
    assert relatorio.achados == [] and relatorio.pronto_para_homologar
    campos = layout_com(OBRIGATORIOS_DA_ADR_143 | {"data_nascimento"})
    relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1))
    assert _regras(relatorio) == regras_com_o_nascimento_obrigatorio


@pytest.mark.parametrize("cpf", ["52998224700", "11111111111", "1234567890"])
def test_cpf_invalido_continua_pendencia_no_parametro_da_adr_143(cpf):
    """O CPF é obrigatório: o CPF com o dígito errado, repetido ou curto continua bloqueando."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa["cpf"] = cpf
    relatorio = validador.validar(normalizacao_de(pessoa), layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1))
    assert _regras(relatorio) == {"CPF_INVALIDO"} and not relatorio.pronto_para_homologar


def pedido_do_banco(campo: str | None, valor_apontado: str | None) -> dict:
    """Um apontamento do especialista do banco que já foi para a empresa (ADR-121), na linha 2."""
    return {"apontamento_id": "ap-7", "linha": 2, "campo": campo, "valor_apontado": valor_apontado,
            "recado": "Confira este dado, por favor."}


@pytest.mark.parametrize("campo, valor", [
    ("nome_completo", "Ana"),        # o motivo "Nome incorreto ou incompleto" (o caso do defeito)
    ("cargo", "Assistnte"),          # o motivo "Cargo incorreto"
    ("sexo", "F"),                   # um campo de lista
    ("nome_mae", "Rita de Souza"),   # um texto
    ("matricula", "00731"),          # a matrícula
])
def test_pedido_do_banco_num_campo_opcional_vira_pendencia(campo, valor):
    """O pedido do especialista do banco é a exceção da ADR-143: ele vira pendência num campo opcional, com o recado
    dele, como num obrigatório (foi uma pessoa que pediu, e não uma regra que achou)."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa[campo] = valor
    pedidos = [pedido_do_banco(campo, valor)]
    # O campo opcional e o mesmo campo obrigatório: o pedido vira a pendência da pessoa nos dois
    for campos in (layout_com(OBRIGATORIOS_DA_ADR_143), layout_com(OBRIGATORIOS_DA_ADR_143 | {campo})):
        relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1),
                                      pedidos_do_banco=pedidos)
        assert _regras(relatorio) == {"PEDIDO_DO_BANCO:ap-7"}
        assert relatorio.achados[0].campo == campo
        assert relatorio.achados[0].mensagem == "O banco pediu: Confira este dado, por favor."


@pytest.mark.parametrize("valor_em_branco", [None, ""])
def test_pedido_do_banco_num_opcional_em_branco_some_quando_a_empresa_preenche(valor_em_branco):
    """O campo opcional pode chegar em branco ao banco (ADR-143). Apontado assim, o pedido fica até a empresa preencher
    o campo; preenchido, some. O branco é o mesmo, venha como None ou como texto vazio."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa["cargo"] = valor_em_branco
    # O valor na hora do envio: em branco (o apontamentos_do_banco guarda None quando o campo não tem valor)
    pedidos = [pedido_do_banco("cargo", None if valor_em_branco is None else "")]
    campos = layout_com(OBRIGATORIOS_DA_ADR_143)
    relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1),
                                  pedidos_do_banco=pedidos)
    assert _regras(relatorio) == {"PEDIDO_DO_BANCO:ap-7"}
    # A empresa preenche o cargo: a pendência some
    pessoa["cargo"] = "Analista de RH"
    relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1),
                                  pedidos_do_banco=pedidos)
    assert relatorio.achados == []


@pytest.mark.parametrize("campo, valor", [(None, None), ("valor_renda", "3000.00")])
def test_pedido_do_banco_sobre_a_pessoa_ou_num_obrigatorio_continua(campo, valor):
    """O pedido sobre a pessoa toda (sem campo) e o pedido num campo obrigatório continuam sendo pendência."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    relatorio = validador.validar(normalizacao_de(pessoa), layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1), pedidos_do_banco=[pedido_do_banco(campo, valor)])
    assert _regras(relatorio) == {"PEDIDO_DO_BANCO:ap-7"}


def normalizacao_com_duvida_de_coluna(pessoa: dict, tipo: str, campo: str | None) -> Normalizacao:
    """A padronização da pessoa com uma dúvida de formato da coluna inteira (a data ambígua, os zeros da matrícula)."""
    normalizacao = normalizacao_de(pessoa)
    normalizacao.pendencias_de_coluna = [{"tipo": tipo, "coluna": "Coluna do teste", "campo": campo,
                                          "mensagem": "O formato desta coluna está em dúvida."}]
    return normalizacao


@pytest.mark.parametrize("tipo, campo, valor", [
    ("ZEROS_A_ESQUERDA", "matricula", "731"),                    # a matrícula sem os zeros
    ("DATA_AMBIGUA", "data_efetivacao", "2021-03-04"),           # uma data opcional ambígua
    ("DATA_AMBIGUA", "data_emissao_documento", "2015-05-06"),    # outra data opcional
])
def test_duvida_de_formato_numa_coluna_opcional_nao_vira_pendencia(tipo, campo, valor):
    """A dúvida de formato de uma coluna opcional não pede decisão; a de uma coluna obrigatória bloqueia."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa[campo] = valor
    normalizacao = normalizacao_com_duvida_de_coluna(pessoa, tipo, campo)
    # O campo opcional: nada a decidir
    relatorio = validador.validar(normalizacao, layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1))
    assert relatorio.achados == []
    # O mesmo campo, obrigatório: a dúvida bloqueia
    relatorio = validador.validar(normalizacao, layout_com(OBRIGATORIOS_DA_ADR_143 | {campo}), "EMP001",
                                  referencia=date(2026, 9, 1))
    assert _regras(relatorio) == {tipo} and not relatorio.pronto_para_homologar


def test_duvida_de_coluna_sem_o_campo_continua():
    """A padronização antiga não diz o campo da dúvida: sem saber se ele é opcional, ela
    continua pedindo a decisão."""
    normalizacao = normalizacao_com_duvida_de_coluna(pessoa_com_os_obrigatorios_da_adr_143(), "DATA_AMBIGUA", None)
    relatorio = validador.validar(normalizacao, layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1))
    assert _regras(relatorio) == {"DATA_AMBIGUA"}


def test_so_o_valor_errado_em_si_fica_em_branco():
    """Num campo opcional, o valor errado em si (o CEP "7") vai para os valores em branco; a pergunta da IA só sai do
    relatório, e o valor fica como veio; o pedido do banco fica, e nunca deixa nada em branco. Com o campo
    obrigatório, nada fica em branco."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    pessoa["cep_residencial"] = "7"
    pessoa["nome_mae"] = "Rita de Souza"
    pessoa["estado_civil"] = "Solteiro"
    pedidos = [pedido_do_banco("nome_mae", "Rita de Souza")]
    perguntas = [{"linha": 2, "campo": "estado_civil", "pergunta": "O estado civil está certo?"}]
    relatorio = validador.validar(normalizacao_de(pessoa), layout_com(OBRIGATORIOS_DA_ADR_143), "EMP001",
                                  referencia=date(2026, 9, 1), pedidos_do_banco=pedidos, perguntas_da_ia=perguntas)
    em_branco = []
    for achado in relatorio.valores_em_branco:
        em_branco.append((achado.linha, achado.campo, achado.valor))
    assert _regras(relatorio) == {"PEDIDO_DO_BANCO:ap-7"} and em_branco == [(2, "cep_residencial", "7")]
    # O CEP obrigatório: é pendência, e nada fica em branco
    campos = layout_com(OBRIGATORIOS_DA_ADR_143 | {"cep_residencial"})
    relatorio = validador.validar(normalizacao_de(pessoa), campos, "EMP001", referencia=date(2026, 9, 1))
    assert _regras(relatorio) == {"CEP_INVALIDO"} and relatorio.valores_em_branco == []


# O arquivo do envio de verdade: a Ana com o CEP "7" (opcional no parâmetro da ADR-143) e a Bia com o CPF de dígito
# errado (obrigatório). As datas têm o dia acima de 12, para não haver dúvida de formato
ARQUIVO_COM_CEP_E_CPF_ERRADOS = ("Nome;CPF;CEP;Salário;Admissão\n"
                                 "Ana Lima;52998224725;7;3000,00;15/02/2020\n"
                                 "Bia Souza;11144477700;01310100;3200,00;20/03/2021\n").encode("utf-8")
# As colunas do arquivo e o campo de cada uma (o aceite da empresa)
ESCOLHAS_DO_ARQUIVO_COM_CEP = {"Nome": "nome_completo", "CPF": "cpf", "CEP": "cep_residencial",
                               "Salário": "valor_renda", "Admissão": "data_admissao"}


def test_envio_de_verdade_deixa_o_cep_opcional_em_branco_e_o_cpf_pendente(tmp_path, monkeypatch):
    """No envio de verdade, com o parâmetro da ADR-143: o CEP "7" não vira pendência e fica em branco nos dados que
    seguem (a correção do sistema guarda o motivo; a trilha, só o campo e a quantidade); o CPF inválido continua
    pendência, com o valor como veio. As contas da empresa não mudam, e validar de novo não grava outro branco."""
    from tests.test_correcao import busca_falsa
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    conexao = banco.conectar(tmp_path / "envio.db")
    marcar_como_obrigatorios(conexao, *OBRIGATORIOS_DA_ADR_143, so_estes=True)
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.aurora", ARQUIVO_COM_CEP_E_CPF_ERRADOS, "cep.csv",
                                      busca=busca_falsa)
    envio = leitura["processamento_id"]
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.aurora", envio, ESCOLHAS_DO_ARQUIVO_COM_CEP, busca=busca_falsa)
    # Só o CPF da Bia é pendência
    relatorio = validador.obter(conexao, envio)
    assert [(achado.regra_id, achado.linha) for achado in relatorio.achados] == [("CPF_INVALIDO", 3)]
    # O CEP "7" ficou em branco; o CEP certo e o CPF inválido continuam como vieram
    ana, bia = correcoes.dados_atuais(conexao, envio).registros
    assert ana["cep_residencial"] is None and bia["cep_residencial"] == "01310100"
    assert bia["cpf"] == "11144477700"
    # O motivo fica na correção do sistema, que não é da empresa
    brancos = correcoes.listar(conexao, envio, correcoes.EM_BRANCO_PELO_SISTEMA)
    assert [(branco.linha, branco.campo, branco.antes, branco.depois) for branco in brancos] == [
        (2, "cep_residencial", "7", None)]
    assert brancos[0].motivo.startswith("Campo opcional com valor inválido: CEP com 1 ")
    assert brancos[0].proposta_por == correcoes.SISTEMA and correcoes.listar(conexao, envio, "APLICADA") == []
    # Na trilha, só o campo e a quantidade
    eventos = auditoria.eventos(conexao, envio)
    detalhes = [evento["detalhe"] for evento in eventos if evento["tipo"] == "VALOR_INVALIDO_EM_BRANCO"]
    assert detalhes == [{"campos": {"cep_residencial": 1}}]
    # Validar de novo não grava outro branco
    validador.executar(conexao, envio, "EMP001")
    assert len(correcoes.listar(conexao, envio, correcoes.EM_BRANCO_PELO_SISTEMA)) == 1
    conexao.close()


def test_o_branco_do_sistema_nao_apaga_o_valor_novo_da_empresa(tmp_path, monkeypatch):
    """Se a empresa escreve outro valor na célula que o sistema deixou em branco, o valor dela vale; se ela escreve
    de novo um valor inválido, ele também fica em branco (outro branco, depois da correção dela)."""
    from tests.test_correcao import busca_falsa
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    conexao = banco.conectar(tmp_path / "envio.db")
    marcar_como_obrigatorios(conexao, *OBRIGATORIOS_DA_ADR_143, so_estes=True)
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.aurora", ARQUIVO_COM_CEP_E_CPF_ERRADOS, "cep.csv",
                                      busca=busca_falsa)
    envio = leitura["processamento_id"]
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.aurora", envio, ESCOLHAS_DO_ARQUIVO_COM_CEP, busca=busca_falsa)
    # A empresa escreve o CEP certo da Ana: vale o dela
    correcao = correcoes.propor(conexao, envio, "EMP001", 2, "cep_residencial", "01310-100", "CEP certo", "rh.aurora")
    correcoes.decidir(conexao, envio, "EMP001", correcao.correcao_id, True, "rh.aurora")
    assert correcoes.dados_atuais(conexao, envio).registros[0]["cep_residencial"] == "01310100"
    # A empresa escreve um CEP curto de novo: ele também fica em branco
    correcao = correcoes.propor(conexao, envio, "EMP001", 2, "cep_residencial", "7", "outro CEP", "rh.aurora")
    correcoes.decidir(conexao, envio, "EMP001", correcao.correcao_id, True, "rh.aurora")
    assert correcoes.dados_atuais(conexao, envio).registros[0]["cep_residencial"] is None
    assert len(correcoes.listar(conexao, envio, correcoes.EM_BRANCO_PELO_SISTEMA)) == 2
    conexao.close()


def test_quem_ja_foi_cadastrado_fica_de_fora_mesmo_com_o_cpf_opcional():
    """O aviso de quem fica de fora do envio não é pendência: ele fica, e a linha não vai ao banco (ADR-126), mesmo
    num parâmetro de teste com o CPF opcional."""
    pessoa = pessoa_com_os_obrigatorios_da_adr_143()
    ja_cadastrada = {"cpf": "52998224725", "matricula": None, "cargo": None, "tipo_renda": None, "valor_renda": None}
    relatorio = validador.validar(normalizacao_de(pessoa), layout_com({"valor_renda", "data_admissao"}), "EMP001",
                                  [ja_cadastrada], referencia=date(2026, 9, 1))
    assert _regras(relatorio) == {"JA_HOMOLOGADO_NA_EMPRESA"}
    assert list(validador.linhas_que_ficam_de_fora(relatorio)) == [2]


# ---------- O LLM só explica ----------

def _regras_e_severidades(relatorio):
    """(regra, severidade) de cada achado, na ordem."""
    pares = []
    for achado in relatorio.achados:
        pares.append((achado.regra_id, achado.severidade))
    return pares


def test_explicacao_nao_muda_severidade_e_recebe_o_valor_de_cada_achado(verdade):
    """A explicação não mexe em nenhuma severidade; o LLM recebe o valor de cada achado (ADR-101)."""
    relatorio = validar_arquivo("prisma_carga_inicial", verdade)
    antes = _regras_e_severidades(relatorio)
    prompts_recebidos = []

    def simulador(prompt):
        """Guarda o prompt e responde com o resumo simulado."""
        prompts_recebidos.append(prompt)
        return validador._explicacao_simulada(prompt)
    from services.llm_client import LLMClient
    texto = validador.explicar(relatorio, LLMClient(modo="mock", respostas_mock={"explicar_validacao": simulador}))
    assert "bloqueantes" in texto.lower() or "pendências" in texto
    assert _regras_e_severidades(relatorio) == antes
    assert '"valor":' in prompts_recebidos[0]


# ---------- Persistência, status e rótulos ----------

def test_executar_grava_relatorio_status_e_evento_sem_dado_pessoal(tmp_path):
    """Validar grava o relatório, muda o status e registra o evento sem nenhum CPF."""
    conexao = banco.conectar(tmp_path / "t.db")
    conteudo = "Colaborador;CPF;Salário Bruto\nAna;11111111111;R$ 3.150,00\n".encode()
    processamento_id = processamentos.receber_arquivo(conexao, conteudo, "v.csv", "EMP001", date(2026, 9, 1),
                                                      "t").perfil.processamento_id
    mapeamentos.interpretar_processamento(conexao, processamento_id, "EMP001", configuracao="B2")
    mapeamentos.aprovar(conexao, processamento_id, "EMP001", {}, "rh")
    normalizador.executar(conexao, processamento_id, "EMP001")
    relatorio = validador.executar(conexao, processamento_id, "EMP001")
    assert "CPF_INVALIDO" in _regras(relatorio)
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.VALIDACAO_PENDENTE
    assert validador.obter(conexao, processamento_id).achados == relatorio.achados
    ultimo_evento = auditoria.eventos(conexao, processamento_id)[-1]
    assert ultimo_evento["tipo"] == "VALIDADO" and "11111111111" not in json.dumps(ultimo_evento)


def test_resolucao_de_alerta_vira_rotulo_com_justificativa(tmp_path):
    """Só resoluções da lista, sempre com justificativa, viram rótulo."""
    conexao = banco.conectar(tmp_path / "t.db")
    with pytest.raises(ValueError):
        validador.registrar_resolucao(conexao, "p1", "RENDA_FORA_DO_CARGO", 5, "FRAUDE", "x", "rh")
    with pytest.raises(ValueError):
        validador.registrar_resolucao(conexao, "p1", "RENDA_FORA_DO_CARGO", 5, "CONFIRMADO", "  ", "rh")
    validador.registrar_resolucao(conexao, "p1", "RENDA_FORA_DO_CARGO", 5, "CONFIRMADO", "Diretor recém-contratado", "rh")
    assert conexao.execute("SELECT resolucao FROM resolucoes_alerta").fetchone() == ("CONFIRMADO",)
