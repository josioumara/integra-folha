"""A faixa salarial por profissão (CBO) e os alertas de salário (ADR-129).

O que estes testes provam (cada regra com pelo menos 3 variações: outras palavras, outro formato, outro valor):
- o código CBO é o mesmo escrito de jeitos diferentes ("4110-10", "411010", " 4110.10 ", 411010.0 do Excel) e o código
  que não existe na CBO vira o alerta CBO_DESCONHECIDO;
- o nome do cargo acha a profissão por regras gerais (maiúsculas, acentos, ordem, plural, feminino, abreviação, nível
  na carreira, "em geral"); nome genérico demais não ganha sugestão, e nome de várias profissões é "ambíguo";
- o salário CLT fora da faixa pública gera UM alerta por pessoa; nos limites, não; pró-labore e salário vazio ficam de
  fora; profissão "sem dados" não gera alerta; a faixa editada pelo banco vale no lugar da calculada;
- a profissão deduzida do cargo nunca vale sozinha: é a pergunta CBO_A_CONFIRMAR; só com o "Está certo" a comparação
  acontece, e desfazer ou recusar tira a profissão;
- a faixa das outras empresas só aparece com 2 empresas e 10 pessoas, e a mensagem só traz os dois números;
- a edição da faixa: mínimo nunca maior que o máximo, valores conferidos, quem e quando, e voltar ao calculado;
- as rotas são só do banco; e o encaixe no Validador funciona no envio de verdade (receber → validar → confirmar).
"""
import json
from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, faixa_salarial_cbo, parametros, processamentos, tabela_cbo, validador

SENHA_DE_TESTE = "senha-de-teste-123"
# A empresa e o envio de mentira dos testes do serviço
EMPRESA, ENVIO = "EMP001", "envio-de-teste"
# As faixas de teste (independem dos números da RAIS de verdade)
FAIXAS_DE_TESTE = [
    # código, mínimo, máximo, nível, vínculos
    ("411010", "2000.00", "5000.00", "OCUPACAO", "1000"),    # Assistente administrativo
    ("322205", "1800.00", "4200.00", "OCUPACAO", "800"),     # Técnico de enfermagem
    ("421125", "1500.00", "3000.00", "FAMILIA", "12"),       # Operador de caixa
    ("010105", "", "", "SEM_DADOS", "0"),                   # Oficial general da aeronáutica
]


@dataclass
class NormalizacaoDeTeste:
    """Só o que o serviço lê da padronização: as pessoas."""

    registros: list[dict]


@pytest.fixture(autouse=True)
def faixas_de_teste(tmp_path, monkeypatch):
    """Aponta o serviço para um arquivo de faixas pequeno, feito para os testes."""
    caminho = tmp_path / "faixas_de_teste.csv"
    linhas = ["codigo_cbo,minimo,maximo,nivel,vinculos_na_base,fonte,ano_base,calculado_em"]
    for codigo, minimo, maximo, nivel, vinculos in FAIXAS_DE_TESTE:
        linhas.append(f"{codigo},{minimo},{maximo},{nivel},{vinculos},RAIS 2025 - MTE,2025,2026-09-29")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    monkeypatch.setattr(faixa_salarial_cbo, "ARQUIVO_DAS_FAIXAS", caminho)
    fontes = tmp_path / "fontes.json"
    fontes.write_text(json.dumps({"medida": {"base": "RAIS 2025", "minimo": "percentil 5"}}), encoding="utf-8")
    monkeypatch.setattr(faixa_salarial_cbo, "ARQUIVO_DAS_FONTES", fontes)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, com o campo "codigo_cbo" no parâmetro (a comparação ligada)."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao_do_teste, "especialista")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture
def conexao_sem_o_campo(tmp_path):
    """Um banco novo com o parâmetro como ele é hoje (sem o campo "codigo_cbo")."""
    conexao_do_teste = banco.conectar(tmp_path / "sem_campo.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def pessoa(linha: int, cargo: str = "", salario: str = "3000.00", codigo=None, tipo: str = "CLT") -> dict:
    """Um funcionário padronizado (só o que o serviço lê)."""
    registro = {"_linha": linha, "cargo": cargo, "tipo_renda": tipo, "valor_renda": salario}
    if codigo is not None:
        registro["codigo_cbo"] = codigo
    return registro


def alertas(conexao, registros: list[dict], empresa: str = EMPRESA, envio: str = ENVIO) -> list:
    """Roda o serviço como o Validador roda e devolve os achados que ele acrescentou."""
    relatorio = validador.RelatorioValidacao()
    faixa_salarial_cbo.acrescentar_alertas(conexao, relatorio, NormalizacaoDeTeste(registros), empresa, envio)
    return relatorio.achados


def regras(achados) -> list[str]:
    """As regras dos achados, na ordem."""
    lista = []
    for achado in achados:
        lista.append(achado.regra_id)
    return lista


# ---------------- 0. Só liga com o campo "codigo_cbo" no parâmetro ----------------

def tirar_o_campo_do_cbo(conexao) -> None:
    """Grava uma versão nova do parâmetro sem o campo "codigo_cbo" (o banco tirou o campo)."""
    _, campos = parametros.layout_ativo(conexao)
    campos_sem_o_cbo = []
    for campo in campos:
        if campo.campo != "codigo_cbo":
            campos_sem_o_cbo.append(campo.model_dump(mode="json"))
    parametros.salvar_layout(conexao, campos_sem_o_cbo, "especialista")


@pytest.mark.parametrize("registros", [
    [pessoa(2, "Técnico de enfermagem", "1.00")],
    [pessoa(2, "Assistente", "1.00", codigo="411010")],
    [pessoa(2, "X", "1.00", codigo="9999-99")],
])
def test_sem_o_campo_no_parametro_nada_muda(conexao_sem_o_campo, registros):
    assert not faixa_salarial_cbo.cbo_ligado(conexao_sem_o_campo)
    assert alertas(conexao_sem_o_campo, registros) == []


def test_ligar_e_tirar_o_campo(conexao_sem_o_campo):
    versao = faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao_sem_o_campo, "especialista")
    # Ligar de novo não grava outra versão
    assert faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao_sem_o_campo, "especialista") == versao
    assert regras(alertas(conexao_sem_o_campo, [pessoa(2, "X", "1.00", codigo="411010")])) == [
        "RENDA_FORA_DA_PROFISSAO"]
    tirar_o_campo_do_cbo(conexao_sem_o_campo)
    assert alertas(conexao_sem_o_campo, [pessoa(2, "X", "1.00", codigo="411010")]) == []


# ---------------- 1. O código CBO ----------------

@pytest.mark.parametrize("escrito", ["4110-10", "411010", " 4110.10 ", "4110 10", 411010.0, "411010.0", "4110/10"])
def test_o_mesmo_codigo_escrito_de_jeitos_diferentes(escrito):
    assert tabela_cbo.codigo_normalizado(escrito) == "411010"


@pytest.mark.parametrize("escrito, esperado", [("10105", "010105"), ("0101-05", "010105"), (10105, "010105")])
def test_codigo_que_perdeu_o_zero_da_frente(escrito, esperado):
    assert tabela_cbo.codigo_normalizado(escrito) == esperado


@pytest.mark.parametrize("escrito", ["4110", "abc", "", None, "41101000", "4110-1"])
def test_texto_sem_cara_de_codigo(escrito):
    assert tabela_cbo.codigo_normalizado(escrito) is None


def test_codigo_existe_e_tem_titulo():
    assert tabela_cbo.existe("411010") and tabela_cbo.titulo("411010") == "Assistente administrativo"
    assert not tabela_cbo.existe("999999") and not tabela_cbo.existe(None)
    assert tabela_cbo.codigo_formatado("411010") == "4110-10"


# ---------------- 2. O nome do cargo ----------------

@pytest.mark.parametrize("cargo", ["Técnico de enfermagem", "TÉCNICAS DE ENFERMAGEM", "enfermagem técnico",
                                   "Téc. de Enfermagem II", "Técnica de Enfermagem Sênior"])
def test_nome_do_cargo_em_varias_formas_acha_a_mesma_profissao(cargo):
    sugestao = tabela_cbo.sugerir(cargo)
    assert sugestao.situacao == tabela_cbo.SUGESTAO_UNICA and sugestao.codigo == "322205"


@pytest.mark.parametrize("cargo", ["Operadora de caixa", "operadores de caixa", "Op. Caixa", "Caixa operador jr"])
def test_feminino_plural_e_abreviacao_do_operador_de_caixa(cargo):
    assert tabela_cbo.sugerir(cargo).codigo == "421125"


@pytest.mark.parametrize("cargo", ["Recepcionista", "recepcionistas", "RECEPCIONISTA PLENO"])
def test_nome_sem_o_em_geral_acha_a_profissao_generica(cargo):
    sugestao = tabela_cbo.sugerir(cargo)
    assert sugestao.codigo == "422105" and "em geral" in sugestao.titulo


@pytest.mark.parametrize("cargo", ["Analista", "xyz", "", "Júnior", "Supervisor"])
def test_nome_generico_demais_nao_ganha_sugestao(cargo):
    assert tabela_cbo.sugerir(cargo).situacao == tabela_cbo.SUGESTAO_NENHUMA


@pytest.mark.parametrize("cargo", ["Engenheiro de logística", "Designer de interiores", "Cortador de vidro"])
def test_nome_de_mais_de_uma_profissao_e_ambiguo(cargo):
    sugestao = tabela_cbo.sugerir(cargo)
    assert sugestao.situacao == tabela_cbo.SUGESTAO_AMBIGUA and len(sugestao.opcoes) >= 2
    assert sugestao.codigo is None


def test_busca_por_codigo_por_palavras_e_por_sinonimo():
    por_codigo = tabela_cbo.buscar("4110")
    assert por_codigo and all(item["codigo"].startswith("4110") for item in por_codigo)
    assert [item["codigo"] for item in tabela_cbo.buscar("4110-10")] == ["411010"]
    assert "782510" in [item["codigo"] for item in tabela_cbo.buscar("motor cam")]
    # "Auxiliar de escritório" é sinônimo do 411005: a busca mostra o sinônimo que bateu
    por_sinonimo = tabela_cbo.buscar("auxiliar de escrit")
    assert any(item["sinonimo"] for item in por_sinonimo)
    # Vazia: todas as profissões da CBO (a tela mostra de 50 em 50)
    assert len(tabela_cbo.buscar("")) == len(tabela_cbo.ocupacoes()) == 2694


# ---------------- 3. O salário fora da faixa pública ----------------

@pytest.mark.parametrize("salario", ["2.50", "250000.00", "1999.99", "5000.01", "20.00"])
def test_salario_fora_da_faixa_gera_um_alerta(conexao, salario):
    achados = alertas(conexao, [pessoa(2, "Assistente", salario, codigo="4110-10")])
    assert regras(achados) == ["RENDA_FORA_DA_PROFISSAO"]
    achado = achados[0]
    assert achado.severidade == "ALERTA" and achado.campo == "valor_renda" and achado.valor == salario
    assert achado.linha == 2 and achado.registro == 1
    assert "R$ 2.000,00 a R$ 5.000,00" in achado.mensagem and "4110-10" in achado.mensagem
    assert "RAIS 2025 - MTE" in achado.mensagem


@pytest.mark.parametrize("salario", ["2000.00", "5000.00", "3200.50"])
def test_salario_nos_limites_ou_dentro_nao_gera_alerta(conexao, salario):
    assert alertas(conexao, [pessoa(2, "Assistente", salario, codigo="411010")]) == []


@pytest.mark.parametrize("escrito", ["4110-10", "411010", " 4110.10 "])
def test_o_codigo_em_qualquer_formato_compara_com_a_mesma_faixa(conexao, escrito):
    assert regras(alertas(conexao, [pessoa(2, "X", "9000.00", codigo=escrito)])) == ["RENDA_FORA_DA_PROFISSAO"]


@pytest.mark.parametrize("salario, tipo", [("99.00", "PRO_LABORE"), ("", "CLT"), ("0.00", "CLT"), ("-5.00", "CLT")])
def test_pro_labore_e_salario_vazio_ou_zerado_ficam_de_fora(conexao, salario, tipo):
    assert alertas(conexao, [pessoa(2, "X", salario, codigo="411010", tipo=tipo)]) == []


def test_profissao_sem_dados_nao_gera_alerta(conexao):
    assert alertas(conexao, [pessoa(2, "X", "1.00", codigo="0101-05")]) == []


def test_a_faixa_da_familia_tambem_vale(conexao):
    assert regras(alertas(conexao, [pessoa(2, "X", "3500.00", codigo="421125")])) == ["RENDA_FORA_DA_PROFISSAO"]


def test_uma_pessoa_por_alerta_e_cada_uma_com_a_sua_linha(conexao):
    achados = alertas(conexao, [pessoa(2, "A", "1.00", codigo="411010"), pessoa(3, "A", "3000.00", codigo="411010"),
                                pessoa(7, "A", "99999.00", codigo="411010")])
    assert [achado.linha for achado in achados] == [2, 7] and [achado.registro for achado in achados] == [1, 3]


@pytest.mark.parametrize("codigo", ["9999-99", "12", "abc"])
def test_codigo_que_nao_existe_e_alerta_e_nao_compara_o_salario(conexao, codigo):
    achados = alertas(conexao, [pessoa(2, "X", "1.00", codigo=codigo)])
    assert regras(achados) == ["CBO_DESCONHECIDO"]
    assert achados[0].campo == "codigo_cbo" and achados[0].valor == codigo


def test_a_faixa_editada_pelo_banco_vale_no_lugar_da_calculada(conexao):
    faixa_salarial_cbo.editar_faixa(conexao, "especialista", "411010", "6000", "9000")
    achados = alertas(conexao, [pessoa(2, "X", "5000.00", codigo="411010")])
    assert regras(achados) == ["RENDA_FORA_DA_PROFISSAO"] and "faixa definida pelo banco" in achados[0].mensagem
    assert alertas(conexao, [pessoa(2, "X", "7000.00", codigo="411010")]) == []


# ---------------- 4. A profissão pelo nome do cargo, com a confirmação da empresa ----------------

def responder(conexao, linha: int, resposta: str, envio: str = ENVIO) -> None:
    """A empresa responde à pergunta da profissão (como o "Está certo" da conversa grava)."""
    validador.registrar_resolucao(conexao, envio, "CBO_A_CONFIRMAR", linha, resposta, "resposta do teste", "rh.teste")


def test_profissao_deduzida_e_uma_pergunta_e_nao_compara_antes_da_resposta(conexao):
    achados = alertas(conexao, [pessoa(2, "Técnica de Enfermagem", "1.00"), pessoa(3, "TÉCNICA DE ENFERMAGEM", "1.00")])
    # Uma pergunta só (na primeira pessoa do cargo), e nenhum alerta de salário ainda
    assert regras(achados) == ["CBO_A_CONFIRMAR"]
    assert achados[0].linha == 2 and achados[0].campo == "cargo" and "3222-05" in achados[0].mensagem
    assert faixa_salarial_cbo.profissoes_da_empresa(conexao, EMPRESA) == {}


@pytest.mark.parametrize("cargos", [("Técnico de enfermagem", "técnico de enfermagem"),
                                    ("Operadora de caixa", "OPERADORA DE CAIXA"),
                                    ("Assistente administrativo", "assistente  administrativo")])
def test_depois_do_esta_certo_a_profissao_vale_para_todo_o_cargo(conexao, cargos):
    registros = [pessoa(2, cargos[0], "1.00"), pessoa(3, cargos[1], "999999.00")]
    alertas(conexao, registros)
    responder(conexao, 2, "CONFIRMADO")
    achados = alertas(conexao, registros)
    # A pergunta continua (a tela mostra como respondida) e as duas pessoas são comparadas
    assert regras(achados) == ["CBO_A_CONFIRMAR", "RENDA_FORA_DA_PROFISSAO", "RENDA_FORA_DA_PROFISSAO"]
    profissao = faixa_salarial_cbo.profissoes_da_empresa(conexao, EMPRESA)[tabela_cbo.texto_normalizado(cargos[0])]
    assert profissao.origem == "CONFIRMADO_PELA_EMPRESA" and profissao.processamento_id == ENVIO


@pytest.mark.parametrize("resposta_depois", ["REABERTO", "SUSPEITO"])
def test_desfazer_ou_recusar_tira_a_profissao(conexao, resposta_depois):
    registros = [pessoa(2, "Técnico de enfermagem", "1.00")]
    alertas(conexao, registros)
    responder(conexao, 2, "CONFIRMADO")
    alertas(conexao, registros)
    responder(conexao, 2, resposta_depois)
    assert regras(alertas(conexao, registros)) == ["CBO_A_CONFIRMAR"]
    assert faixa_salarial_cbo.profissoes_da_empresa(conexao, EMPRESA) == {}


def test_profissao_confirmada_em_outro_envio_nao_pergunta_de_novo(conexao):
    alertas(conexao, [pessoa(2, "Técnico de enfermagem", "3000.00")], envio="envio-1")
    responder(conexao, 2, "CONFIRMADO", envio="envio-1")
    alertas(conexao, [pessoa(2, "Técnico de enfermagem", "3000.00")], envio="envio-1")
    achados = alertas(conexao, [pessoa(5, "Técnico de Enfermagem", "10.00")], envio="envio-2")
    assert regras(achados) == ["RENDA_FORA_DA_PROFISSAO"]


def test_a_profissao_da_coluna_do_arquivo_vale_para_o_cargo_sem_apagar_a_confirmada(conexao):
    # A coluna do arquivo grava a profissão do cargo; outra pessoa do mesmo cargo, sem a coluna, segue ela
    achados = alertas(conexao, [pessoa(2, "Aux. escritório", "3000.00", codigo="411010"),
                                pessoa(3, "Aux. escritório", "10.00")])
    assert regras(achados) == ["RENDA_FORA_DA_PROFISSAO"] and achados[0].linha == 3
    # Um código diferente no arquivo não troca a profissão já registrada do cargo
    alertas(conexao, [pessoa(2, "Aux. escritório", "3000.00", codigo="322205")], envio="outro")
    assert faixa_salarial_cbo.profissoes_da_empresa(conexao, EMPRESA)["aux escritorio"].codigo == "411010"


@pytest.mark.parametrize("cargo", ["Analista", "Designer de interiores", "Supervisor"])
def test_cargo_sem_profissao_na_cbo_e_so_um_aviso(conexao, cargo):
    achados = alertas(conexao, [pessoa(2, cargo, "1.00"), pessoa(3, cargo, "1.00")])
    assert regras(achados) == ["CBO_NAO_ENCONTRADO"] and achados[0].severidade == "AVISO"
    assert 'coluna "Código CBO"' in achados[0].mensagem


def test_as_profissoes_sao_de_cada_empresa(conexao):
    alertas(conexao, [pessoa(2, "Técnico de enfermagem", "3000.00")], empresa="EMP001")
    responder(conexao, 2, "CONFIRMADO")
    alertas(conexao, [pessoa(2, "Técnico de enfermagem", "3000.00")], empresa="EMP001")
    # A outra empresa, com o mesmo cargo, recebe a própria pergunta
    assert regras(alertas(conexao, [pessoa(2, "Técnico de enfermagem", "1.00")], empresa="EMP002",
                          envio="envio-emp002")) == ["CBO_A_CONFIRMAR"]


# ---------------- 5. A faixa das outras empresas ----------------

def cadastrar_pessoas(conexao, empresa: str, cargo: str, salarios: list[str], codigo: str | None = "322205") -> None:
    """Funcionários já cadastrados (homologados) de uma empresa, com a profissão do cargo registrada."""
    processamentos._preparar(conexao)
    faixa_salarial_cbo._preparar(conexao)
    for posicao, salario in enumerate(salarios):
        conexao.execute("INSERT INTO funcionarios_homologados (empresa_id, cpf, processamento_id, homologado_em, "
                        "matricula, cargo, tipo_renda, valor_renda) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (empresa, f"{empresa}{posicao:05d}", "envio-antigo", "2026-09-01", str(posicao), cargo, "CLT",
                         salario))
    if codigo:
        faixa_salarial_cbo._gravar_profissao(conexao, empresa, cargo, codigo, "ARQUIVO", "envio-antigo", None,
                                             substituir=False)
    conexao.commit()


def test_fora_da_faixa_das_outras_empresas_gera_o_alerta_so_com_os_numeros(conexao):
    cadastrar_pessoas(conexao, "EMP002", "Téc. Enfermagem", ["3000.00"] * 6)
    cadastrar_pessoas(conexao, "EMP003", "Enfermagem técnico", ["3200.00"] * 6)
    # Dentro da faixa pública (1.800 a 4.200), mas fora da das outras (3.000 a 3.200)
    achados = alertas(conexao, [pessoa(2, "Técnico", "4000.00", codigo="322205")])
    assert regras(achados) == ["RENDA_FORA_DA_PROFISSAO"]
    mensagem = achados[0].mensagem
    assert "outras 2 empresas" in mensagem and "R$ 3.000,00 a R$ 3.200,00" in mensagem
    # Nada das outras empresas além dos dois números
    for proibido in ("EMP002", "EMP003", "Téc. Enfermagem", "Enfermagem técnico"):
        assert proibido not in mensagem


def test_fora_das_duas_faixas_e_um_alerta_so(conexao):
    cadastrar_pessoas(conexao, "EMP002", "Técnico", ["3000.00"] * 5)
    cadastrar_pessoas(conexao, "EMP003", "Técnico", ["3100.00"] * 5)
    achados = alertas(conexao, [pessoa(2, "Técnico", "90000.00", codigo="322205")])
    assert regras(achados) == ["RENDA_FORA_DA_PROFISSAO"]
    assert "faixa da profissão" in achados[0].mensagem and "outras 2 empresas" in achados[0].mensagem


@pytest.mark.parametrize("empresas_e_pessoas", [
    {"EMP002": 12},                     # uma empresa só
    {"EMP002": 5, "EMP003": 4},         # 9 pessoas
    {"EMP002": 11, "EMP003": 0},        # a segunda empresa não tem ninguém nessa profissão
])
def test_sem_2_empresas_e_10_pessoas_nao_ha_faixa_das_outras(conexao, empresas_e_pessoas):
    for empresa, quantas in empresas_e_pessoas.items():
        cadastrar_pessoas(conexao, empresa, "Técnico", ["3000.00"] * quantas)
    assert faixa_salarial_cbo.faixa_das_outras_empresas(conexao, EMPRESA, "322205") is None
    assert alertas(conexao, [pessoa(2, "Técnico", "4000.00", codigo="322205")]) == []


def test_a_propria_empresa_e_o_pro_labore_nao_entram_na_faixa_das_outras(conexao):
    cadastrar_pessoas(conexao, EMPRESA, "Técnico", ["100000.00"] * 20)
    cadastrar_pessoas(conexao, "EMP002", "Técnico", ["3000.00"] * 6)
    cadastrar_pessoas(conexao, "EMP003", "Técnico", ["3100.00"] * 5)
    conexao.execute("UPDATE funcionarios_homologados SET tipo_renda = 'PRO_LABORE', valor_renda = '999999.00' "
                    "WHERE empresa_id = 'EMP003' AND cpf = 'EMP00300000'")
    faixa, quantas_empresas, quantas_pessoas = faixa_salarial_cbo.faixa_das_outras_empresas(conexao, EMPRESA, "322205")
    assert quantas_empresas == 2 and quantas_pessoas == 10
    assert faixa.maximo <= Decimal("3100.00")


# ---------------- 6. Editar a faixa ----------------

def test_editar_guarda_quem_quando_e_a_calculada_ao_lado(conexao):
    faixa = faixa_salarial_cbo.editar_faixa(conexao, "especialista", "411010", "2.500,00", 4800)
    assert (faixa["minimo"], faixa["maximo"]) == ("2500.00", "4800.00")
    assert (faixa["minimo_calculado"], faixa["maximo_calculado"]) == ("2000.00", "5000.00")
    assert faixa["editado_por"] == "especialista" and faixa["editado_em"]
    registro = faixa_salarial_cbo.alteracoes(conexao, "411010")
    assert registro[0]["acao"] == "EDITADA" and registro[0]["minimo_antes"] == "2000.00"


@pytest.mark.parametrize("minimo, maximo, parte_da_mensagem", [
    ("5000", "4000", "maior que o máximo"),
    ("0", "4000", "maior que zero"),
    ("-10", "4000", "maior que zero"),
    ("abc", "4000", "valor em reais"),
    ("NaN", "4000", "valor em reais"),
    ("100", "2000000", "passa de"),
])
def test_editar_recusa_valores_invalidos(conexao, minimo, maximo, parte_da_mensagem):
    with pytest.raises(ValueError, match=parte_da_mensagem):
        faixa_salarial_cbo.editar_faixa(conexao, "especialista", "411010", minimo, maximo)
    assert faixa_salarial_cbo.faixa_do_codigo(conexao, "411010")["minimo"] == "2000.00"


def test_minimo_igual_ao_maximo_pode(conexao):
    assert faixa_salarial_cbo.editar_faixa(conexao, "especialista", "411010", "3000", "3000")["maximo"] == "3000.00"


def test_voltar_ao_calculado_desfaz_a_edicao(conexao):
    faixa_salarial_cbo.editar_faixa(conexao, "especialista", "411010", "100", "200")
    faixa = faixa_salarial_cbo.voltar_ao_calculado(conexao, "outro.especialista", "411010")
    assert (faixa["minimo"], faixa["maximo"], faixa["editado_por"]) == ("2000.00", "5000.00", None)
    acoes = [alteracao["acao"] for alteracao in faixa_salarial_cbo.alteracoes(conexao, "411010")]
    assert acoes == ["VOLTOU_AO_CALCULADO", "EDITADA"]


def test_profissao_sem_dados_pode_ganhar_faixa_do_banco(conexao):
    faixa_salarial_cbo.editar_faixa(conexao, "especialista", "010105", "20000", "40000")
    assert regras(alertas(conexao, [pessoa(2, "X", "1000.00", codigo="010105")])) == ["RENDA_FORA_DA_PROFISSAO"]


def test_codigo_fora_da_tabela_nao_edita(conexao):
    with pytest.raises(KeyError):
        faixa_salarial_cbo.editar_faixa(conexao, "especialista", "999999", "1", "2")


def test_carregar_de_novo_nao_duplica_nem_apaga_a_edicao(conexao):
    faixa_salarial_cbo.editar_faixa(conexao, "especialista", "411010", "100", "200")
    # Um arquivo com uma profissão a mais (uma faixa recalculada) só acrescenta a nova
    with open(faixa_salarial_cbo.ARQUIVO_DAS_FAIXAS, "a", encoding="utf-8") as arquivo:
        arquivo.write("782510,1800.00,6000.00,OCUPACAO,500,RAIS 2025 - MTE,2025,2026-09-29\n")
    faixa_salarial_cbo._preparar(conexao)
    faixa_salarial_cbo._preparar(conexao)
    total = conexao.execute("SELECT COUNT(*) FROM faixas_salariais_cbo").fetchone()[0]
    assert total == len(FAIXAS_DE_TESTE) + 1
    assert faixa_salarial_cbo.faixa_do_codigo(conexao, "411010")["minimo"] == "100.00"


@pytest.mark.parametrize("busca, inicio, codigos_da_pagina", [
    ("", 0, ["010105"]),                     # as 3 primeiras da CBO; só a 010105 tem faixa no teste
    ("assistente administrativo", 0, ["411010"]),   # a busca por palavras
    ("4110", 1, ["411010"]),                 # a segunda página da família 4110 (411005 fica na primeira)
    ("", 3000, []),                          # depois da última: página vazia
])
def test_busca_das_faixas_de_pagina_em_pagina_com_o_total(conexao, monkeypatch, busca, inicio, codigos_da_pagina):
    # Páginas de 3 posições (na tela são 50); a página mostra as profissões da posição que têm faixa gravada
    monkeypatch.setattr(faixa_salarial_cbo, "PROFISSOES_POR_PAGINA", 3)
    resultado = faixa_salarial_cbo.buscar_faixas(conexao, busca, inicio)
    assert resultado["inicio"] == inicio
    assert [faixa["codigo_cbo"] for faixa in resultado["faixas"]] == codigos_da_pagina
    # O total conta todas as profissões da CBO que batem (e não só as da página)
    assert resultado["total"] == len(tabela_cbo.buscar(busca))


def test_busca_das_faixas_recusa_posicao_negativa(conexao):
    with pytest.raises(ValueError):
        faixa_salarial_cbo.buscar_faixas(conexao, "", -1)


def test_busca_das_faixas_traz_a_faixa_e_a_medida(conexao):
    resultado = faixa_salarial_cbo.buscar_faixas(conexao, "assistente administrativo")
    codigos = [faixa["codigo_cbo"] for faixa in resultado["faixas"]]
    assert codigos == ["411010"] and resultado["faixas"][0]["codigo_formatado"] == "4110-10"
    assert resultado["medida"]["base"] == "RAIS 2025"


# ---------------- 7. As rotas ----------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um especialista e um RH da Aurora."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_cbo.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_rotas_sao_so_do_banco(api):
    rh = entrar("rh.aurora")
    assert rh.get("/api/banco/cbo?busca=4110").status_code == 403
    assert rh.put("/api/banco/cbo/411010/faixa", json={"minimo": 1, "maximo": 2}).status_code == 403
    assert rh.post("/api/banco/cbo/411010/faixa/voltar").status_code == 403
    assert rh.get("/api/banco/cbo/411010/alteracoes").status_code == 403
    assert TestClient(aplicacao).get("/api/banco/cbo").status_code == 401


def test_rotas_do_banco_buscam_editam_e_voltam(api):
    especialista = entrar("especialista")
    busca = especialista.get("/api/banco/cbo?busca=4110-10").json()
    assert busca["faixas"][0]["codigo_cbo"] == "411010" and busca["total"] == 1
    assert especialista.get("/api/banco/cbo?inicio=-1").status_code == 400
    assert especialista.get("/api/banco/cbo?inicio=abc").status_code == 422
    editada = especialista.put("/api/banco/cbo/411010/faixa", json={"minimo": "2.100,00", "maximo": 4900})
    assert editada.status_code == 200 and editada.json()["editado_por"] == "especialista"
    assert especialista.get("/api/banco/cbo/411010/alteracoes").json()["alteracoes"][0]["acao"] == "EDITADA"
    voltou = especialista.post("/api/banco/cbo/411010/faixa/voltar").json()
    assert voltou["minimo"] == "2000.00" and voltou["editado_por"] is None


@pytest.mark.parametrize("corpo, situacao", [
    ({"minimo": 5000, "maximo": 4000}, 400),
    ({"minimo": "x" * 40, "maximo": 4000}, 400),
    ({"minimo": 0, "maximo": 4000}, 400),
    ({"maximo": 4000}, 422),
])
def test_rota_de_editar_recusa_valores_invalidos(api, corpo, situacao):
    resposta = entrar("especialista").put("/api/banco/cbo/411010/faixa", json=corpo)
    assert resposta.status_code == situacao


def test_rota_com_codigo_que_nao_existe_da_404(api):
    especialista = entrar("especialista")
    assert especialista.put("/api/banco/cbo/999999/faixa", json={"minimo": 1, "maximo": 2}).status_code == 404
    assert especialista.get("/api/banco/cbo/999999/alteracoes").status_code == 404
    assert especialista.get("/api/banco/cbo?busca=" + "a" * 101).status_code == 400


# ---------------- 8. O encaixe no Validador, com um envio de verdade ----------------

def test_envio_de_verdade_pergunta_a_profissao_e_o_esta_certo_grava_o_cargo(conexao, monkeypatch):
    from scripts.gerar_dados import main as gerar_os_envios
    from tests.test_correcao import busca_falsa, preparar_ate_a_validacao
    gerar_os_envios()
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    processamento_id = preparar_ate_a_validacao(conexao, "aurora_carga_inicial")
    relatorio = validador.obter(conexao, processamento_id)
    perguntas = [achado for achado in relatorio.achados if achado.regra_id == "CBO_A_CONFIRMAR"]
    # O arquivo da Aurora não tem a coluna do CBO: os cargos com profissão na CBO viram perguntas (uma por cargo)
    assert perguntas and len({achado.valor for achado in perguntas}) == len(perguntas)
    pergunta = perguntas[0]
    # A empresa responde "Está certo": o cargo ganha a profissão, e a pergunta fica marcada como respondida
    relatorio = validador.justificar_alerta(conexao, processamento_id, "EMP001", "CBO_A_CONFIRMAR", pergunta.linha,
                                            "CONFIRMADO", "É essa a profissão.", "rh.aurora")
    respondida = [achado for achado in relatorio.achados
                  if achado.regra_id == "CBO_A_CONFIRMAR" and achado.linha == pergunta.linha]
    assert respondida and respondida[0].resolvido == "CONFIRMADO"
    profissao = faixa_salarial_cbo.profissoes_da_empresa(conexao, "EMP001")[tabela_cbo.texto_normalizado(pergunta.valor)]
    assert profissao.origem == "CONFIRMADO_PELA_EMPRESA"
    quem = conexao.execute("SELECT registrado_por FROM cbo_dos_cargos WHERE empresa_id = 'EMP001' AND "
                           "cargo_normalizado = ?", (tabela_cbo.texto_normalizado(pergunta.valor),)).fetchone()[0]
    assert quem == "rh.aurora"


# ---------------- 9. Campo opcional não abre pendência, nem nos alertas da profissão (ADR-143) ----------------

# Quatro pessoas: a Ana e a Bia sem o código (a pergunta do cargo e o cargo sem profissão), o Caio com um código que
# não existe e a Duda com o salário acima da faixa da profissão (2.000 a 5.000). As datas têm o dia acima de 12
ARQUIVO_DA_PROFISSAO = ("Nome;CPF;Cargo;Código CBO;Tipo de renda;Salário;Admissão\n"
                        "Ana Lima;52998224725;Técnico de enfermagem;;CLT;3000,00;15/02/2020\n"
                        "Bia Souza;11144477735;Analista;;CLT;3000,00;16/02/2020\n"
                        "Caio Reis;12345678909;Assistente administrativo;9999-99;CLT;3000,00;17/02/2020\n"
                        "Duda Melo;98765432100;Assistente administrativo;4110-10;CLT;9000,00;18/02/2020\n"
                        ).encode("utf-8")
# As colunas do arquivo e o campo de cada uma (o aceite da empresa)
ESCOLHAS_DA_PROFISSAO = {"Nome": "nome_completo", "CPF": "cpf", "Cargo": "cargo", "Código CBO": "codigo_cbo",
                         "Tipo de renda": "tipo_renda", "Salário": "valor_renda", "Admissão": "data_admissao"}


def enviar_o_arquivo_da_profissao(conexao, monkeypatch) -> str:
    """O arquivo das quatro pessoas enviado e aceito pela Aurora (a validação roda no aceite). Devolve o envio."""
    from services import cadastro
    from tests.test_correcao import busca_falsa
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, "rh.aurora", ARQUIVO_DA_PROFISSAO, "profissao.csv",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, "rh.aurora", leitura["processamento_id"], ESCOLHAS_DA_PROFISSAO,
                                busca=busca_falsa)
    return leitura["processamento_id"]


def regras_e_campos(relatorio) -> set[tuple[str, str | None]]:
    """As regras do relatório, cada uma com o campo em que está presa."""
    pares = set()
    for achado in relatorio.achados:
        pares.add((achado.regra_id, achado.campo))
    return pares


def test_no_parametro_da_adr_143_o_cargo_opcional_nao_pergunta_a_profissao(conexao, monkeypatch):
    """Com o parâmetro da ADR-143 (o cargo opcional): as perguntas do cargo (CBO_A_CONFIRMAR e CBO_NAO_ENCONTRADO) não
    aparecem, e o cargo fica como veio; o código que não existe e o salário fora da profissão, presos a campos
    obrigatórios, continuam. Com o cargo obrigatório, as perguntas do cargo voltam."""
    from services import correcoes
    from tests.apoio_do_parametro import marcar_como_obrigatorios
    marcar_como_obrigatorios(conexao, "cpf", "codigo_cbo", "valor_renda", "data_admissao", so_estes=True)
    envio = enviar_o_arquivo_da_profissao(conexao, monkeypatch)
    pares = regras_e_campos(validador.obter(conexao, envio))
    assert ("CBO_DESCONHECIDO", "codigo_cbo") in pares and ("RENDA_FORA_DA_PROFISSAO", "valor_renda") in pares
    for regra, campo in pares:
        assert campo != "cargo", regra
    # O cargo e o código que não existe continuam como vieram (a pergunta não diz que o cargo está errado)
    ana, _, caio, _ = correcoes.dados_atuais(conexao, envio).registros
    assert ana["cargo"] == "Técnico de enfermagem" and caio["codigo_cbo"] == "9999-99"
    # Com o cargo obrigatório, as perguntas do cargo voltam
    marcar_como_obrigatorios(conexao, "cargo")
    pares = regras_e_campos(validador.executar(conexao, envio, EMPRESA))
    assert ("CBO_A_CONFIRMAR", "cargo") in pares and ("CBO_NAO_ENCONTRADO", "cargo") in pares


def test_codigo_cbo_opcional_que_nao_existe_fica_em_branco(conexao, monkeypatch):
    """Com o código CBO opcional, o código que não existe não vira pendência e fica em branco nos dados que seguem."""
    from services import correcoes
    from tests.apoio_do_parametro import marcar_como_obrigatorios
    marcar_como_obrigatorios(conexao, "cpf", "valor_renda", "data_admissao", so_estes=True)
    envio = enviar_o_arquivo_da_profissao(conexao, monkeypatch)
    for regra, _ in regras_e_campos(validador.obter(conexao, envio)):
        assert regra != "CBO_DESCONHECIDO"
    caio = correcoes.dados_atuais(conexao, envio).registros[2]
    assert caio["codigo_cbo"] is None
    brancos = correcoes.listar(conexao, envio, correcoes.EM_BRANCO_PELO_SISTEMA)
    assert [(branco.linha, branco.campo, branco.antes) for branco in brancos] == [(4, "codigo_cbo", "9999-99")]
