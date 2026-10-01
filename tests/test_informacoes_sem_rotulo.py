"""Informações sem rótulo (ADR-143, Parte 1): o que a IA achou num campo opcional sem ter certeza de qual campo é.

O que estes testes provam (com a IA simulada, sem custo; as planilhas são montadas aqui, com pessoas inventadas, e o
parâmetro tem só o CPF, a renda e a admissão como obrigatórios, como no ADR-143):
- a coluna em que a IA ficou em dúvida só entre campos opcionais, e que fica de fora (como a tela faz sozinha), é
  guardada sem rótulo em cada pessoa: o valor como veio e os candidatos, com o nome legível na tela; a célula vazia não
  é guardada, e o valor nunca vira o valor de um campo;
- a coluna desconhecida (a IA não indicou nenhum campo, ex.: "Religião") nunca é guardada;
- a dúvida que envolve um campo obrigatório continua como antes: sem a escolha, o aceite não passa; deixada de fora, ela
  não é guardada, e o obrigatório sem coluna vira pendência;
- a coluna que a empresa escolheu mapear vira um campo normal; a que a IA reconheceu com certeza (mesmo mandando
  candidatos, também na releitura) e ficou de fora não é guardada;
- a lista sobrevive à correção e à revalidação, vai junto no envio de devolução, segue com o funcionário no cadastro e
  volta na inclusão seguinte (a coluna reaproveitada do aceite anterior);
- as rotas do detalhe das 5 listas trazem a lista ao lado dos dados da pessoa, sem ela entrar nos downloads nem no
  arquivo final do banco; 401 sem login, 403 para o outro perfil, e uma empresa nunca vê a outra.
Cada caso tem variações (outro nome de coluna, outros campos em dúvida, outra ordem das colunas ou dos candidatos), para
a regra valer em arquivos novos e não só no exemplo do contrato.
"""
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from agents import interpretador
from api.principal import aplicacao
from models.contratos import DivisaoProposta, ItemMapeamento, MappingPlan, ParteDaDivisao, Perfil, StatusMapeamento
from services import (acompanhamento, auth, avaliacao_do_banco, banco, cadastro, correcoes, homologacao,
                      informacoes_sem_rotulo, mapeamentos, validador)
from services.auth import Usuario
from services.llm_client import LLMClient
from tests.apoio_do_parametro import layout_com, marcar_como_obrigatorios
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import cpf_valido

# A empresa dos testes, a outra empresa (para o isolamento) e os logins
EMPRESA = "EMP001"
OUTRA_EMPRESA = "EMP002"
LOGIN = "rh.aurora"
LOGIN_DA_OUTRA = "rh.horizonte"
LOGIN_DO_BANCO = "especialista.banco"
SENHA_DE_TESTE = "senha-de-teste-123"
ESPECIALISTA = Usuario(login=LOGIN_DO_BANCO, perfil=Perfil.BANCO, empresa_id=None)
# Os obrigatórios do parâmetro do teste: os do ADR-143 que existem no layout_v1 (o codigo_cbo não está nele)
OBRIGATORIOS_DO_TESTE = ("cpf", "valor_renda", "data_admissao")
# As pessoas inventadas: nome, os 9 primeiros dígitos do CPF, o salário e a admissão
PESSOAS = [("Bianca Torres", "812345670", "3.500,00", "03/02/2025"),
           ("Caio Mendes", "823456781", "4.250,50", "15/07/2024"),
           ("Dora Albuquerque", "834567892", "2.980,00", "20/09/2023")]
# Outras pessoas, para o arquivo de inclusão
OUTRAS_PESSOAS = [("Elias Moura", "845678903", "3.100,00", "11/03/2026"),
                  ("Fabiana Rocha", "856789014", "5.020,00", "25/08/2026")]
# As colunas que todo arquivo do teste tem e o campo de cada uma
COLUNAS_DE_SEMPRE = ["Nome", "CPF", "Salário", "Admissão"]
ESCOLHAS_DE_SEMPRE = {"Nome": "nome_completo", "CPF": "cpf", "Salário": "valor_renda", "Admissão": "data_admissao"}
# O exemplo do contrato: o "C.E.P" em dúvida entre os dois CEPs opcionais (a terceira pessoa não tem o valor)
CANDIDATOS_DO_CEP = ["cep_residencial", "cep_comercial"]
VALORES_DO_CEP = ["01310-100", "20040-002", ""]


# ---------------- A IA simulada do teste ----------------

def duvida(candidatos: list[str]) -> tuple:
    """A resposta da IA em dúvida entre os candidatos (AMBIGUO)."""
    return ("AMBIGUO", None, candidatos)


def certeza(campo: str, candidatos: list[str]) -> tuple:
    """A resposta da IA com certeza num campo (PROPOSTO), mandando candidatos mesmo assim."""
    return ("PROPOSTO", campo, candidatos)


def sem_campo(candidatos: list[str]) -> tuple:
    """A resposta da IA de que a coluna não é de nenhum campo (NAO_MAPEADO), mandando candidatos mesmo assim."""
    return ("NAO_MAPEADO", None, candidatos)


class IaDoTeste:
    """A IA simulada de sempre (agents/interpretador.simular_llm), com a resposta que o teste quer em algumas colunas.

    Uso: IaDoTeste({"C.E.P": duvida(["cep_residencial", "cep_comercial"])}).cliente().
    """

    def __init__(self, respostas: dict | None = None):
        """respostas: {coluna: (status, campo, candidatos)}, montadas com duvida(), certeza() ou sem_campo()."""
        self.respostas = respostas or {}

    def responder(self, pedido: str) -> str:
        """Responde como a IA simulada e troca o item das colunas escolhidas pelo teste."""
        resposta = json.loads(interpretador.simular_llm(pedido))
        for item in resposta["itens"]:
            if item["coluna"] in self.respostas:
                status, campo, candidatos = self.respostas[item["coluna"]]
                item.update({"status": status, "campo": campo, "candidatos": list(candidatos), "divisao": None,
                             "fontes": [], "justificativa": "Resposta escolhida pelo teste."})
        return json.dumps(resposta, ensure_ascii=False)

    def cliente(self) -> LLMClient:
        """O cliente de IA (no modo MOCK) que responde por esta classe."""
        return LLMClient(modo="mock", respostas_mock={interpretador.TAREFA: self.responder})


# ---------------- Planilhas e passos do cadastro ----------------

@pytest.fixture(autouse=True)
def usar_busca_falsa(monkeypatch):
    """Nenhum uso do RAG depende do índice nem do modelo de embeddings."""
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, com o parâmetro do ADR-143 (só o CPF, a renda e a admissão obrigatórios)."""
    conexao_do_teste = banco.conectar(tmp_path / "sem_rotulo.db")
    marcar_como_obrigatorios(conexao_do_teste, *OBRIGATORIOS_DO_TESTE, so_estes=True)
    yield conexao_do_teste
    conexao_do_teste.close()


def valores_de_sempre(pessoa: tuple) -> dict:
    """Os valores das colunas de sempre de uma pessoa: {coluna: valor}."""
    nome, nove_digitos, salario, admissao = pessoa
    return {"Nome": nome, "CPF": cpf_valido(nove_digitos), "Salário": salario, "Admissão": admissao}


def planilha(colunas_extras: dict, extras_primeiro: bool = False, sem: tuple = (),
             pessoas: list | None = None) -> bytes:
    """Um CSV (separador ";") com as colunas de sempre e as colunas extras do teste, uma linha por pessoa.

    Recebe: colunas_extras — {coluna: [o valor de cada pessoa, na ordem das pessoas]}; extras_primeiro — True põe as
    extras antes das de sempre (outra ordem de colunas); sem — as colunas de sempre que ficam fora do arquivo; pessoas —
    quem entra no arquivo (sem informar, PESSOAS). Devolve: os bytes do arquivo, em UTF-8.
    """
    pessoas = pessoas or PESSOAS
    # As colunas de sempre que entram, na ordem
    de_sempre = []
    for coluna in COLUNAS_DE_SEMPRE:
        if coluna not in sem:
            de_sempre.append(coluna)
    # O cabeçalho, com as extras antes ou depois das de sempre
    if extras_primeiro:
        cabecalho = list(colunas_extras) + de_sempre
    else:
        cabecalho = de_sempre + list(colunas_extras)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(cabecalho)
    for posicao, pessoa in enumerate(pessoas):
        # Os valores da pessoa, coluna por coluna
        valores_da_pessoa = valores_de_sempre(pessoa)
        for coluna, valores_da_coluna in colunas_extras.items():
            valores_da_pessoa[coluna] = valores_da_coluna[posicao]
        linha = []
        for coluna in cabecalho:
            linha.append(valores_da_pessoa[coluna])
        escritor.writerow(linha)
    return saida.getvalue().encode("utf-8")


def escolhas(escolhas_extras: dict, sem: tuple = ()) -> dict:
    """As escolhas do aceite: o campo de cada coluna de sempre (menos as que ficaram fora do arquivo) e as do teste."""
    todas = {}
    for coluna, campo in ESCOLHAS_DE_SEMPRE.items():
        if coluna not in sem:
            todas[coluna] = campo
    todas.update(escolhas_extras)
    return todas


def enviar(conexao, conteudo: bytes, ia: IaDoTeste) -> dict:
    """Envia a planilha pela porta do cadastro (como a tela faz), com a IA do teste. Devolve a leitura."""
    return cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, conteudo, "sem_rotulo.csv", cliente=ia.cliente(),
                                   busca=busca_falsa)


def confirmar_os_alertas(conexao, processamento_id: str) -> None:
    """Confirma os alertas em aberto do envio (ex.: salário longe dos colegas, num arquivo pequeno)."""
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return
    for achado in relatorio.achados:
        if achado.severidade == validador.ALERTA and not achado.resolvido:
            acompanhamento.confirmar_pendencia(conexao, EMPRESA, LOGIN, processamento_id, achado.regra_id,
                                               achado.linha, "Conferido no teste")


def aceitar(conexao, processamento_id: str, escolhas_do_aceite: dict) -> dict:
    """Aceita as colunas com as escolhas informadas e confirma os alertas, como a empresa faria. Devolve a leitura."""
    leitura = cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, processamento_id, escolhas_do_aceite,
                                          busca=busca_falsa)
    confirmar_os_alertas(conexao, processamento_id)
    return leitura


def envio_com_o_cep_em_duvida(conexao, pessoas: list | None = None, valores: list | None = None) -> str:
    """Um envio com o "C.E.P" em dúvida entre os dois CEPs, deixado de fora no aceite (como a tela faz sozinha).

    Devolve o envio, já padronizado e validado, esperando a conferência.
    """
    conteudo = planilha({"C.E.P": valores or VALORES_DO_CEP}, pessoas=pessoas)
    leitura = enviar(conexao, conteudo, IaDoTeste({"C.E.P": duvida(CANDIDATOS_DO_CEP)}))
    aceitar(conexao, leitura["processamento_id"], escolhas({"C.E.P": mapeamentos.IGNORAR}))
    return leitura["processamento_id"]


def coluna_da_leitura(leitura: dict, nome: str) -> dict:
    """A coluna da leitura (o aceite das colunas na tela) com este nome."""
    for coluna in leitura["colunas"]:
        if coluna["coluna"] == nome:
            return coluna
    raise AssertionError(f"A coluna {nome!r} não está na leitura")


def registros(conexao, processamento_id: str) -> list[dict]:
    """Os registros do envio como estão agora (a padronização com as correções aplicadas)."""
    return correcoes.dados_atuais(conexao, processamento_id).registros


def esperado_na_tela(coluna: str, valor: str, candidatos: list[str]) -> dict:
    """Uma informação sem rótulo como a tela recebe (o formato combinado com o front)."""
    candidatos_na_tela = []
    for campo in candidatos:
        candidatos_na_tela.append({"campo": campo, "rotulo": acompanhamento.rotulo_do_campo(campo)})
    return {"coluna": coluna, "valor": valor, "candidatos": candidatos_na_tela}


def esperado_por_cpf(pessoas: list, valores: list[str]) -> dict:
    """O que cada pessoa traz na tela, pelo CPF formatado: a lista com o "C.E.P", ou vazia sem o valor."""
    por_cpf = {}
    for pessoa, valor in zip(pessoas, valores):
        cpf = acompanhamento.formatar_cpf(cpf_valido(pessoa[1]))
        por_cpf[cpf] = []
        if valor:
            por_cpf[cpf] = [esperado_na_tela("C.E.P", valor, CANDIDATOS_DO_CEP)]
    return por_cpf


# ---------------- A regra: só a dúvida entre opcionais ----------------

def item(coluna: str, status: StatusMapeamento, campo: str | None = None, candidatos: list | None = None,
         divisao: DivisaoProposta | None = None) -> ItemMapeamento:
    """Um item do mapeamento aprovado, montado no teste."""
    return ItemMapeamento(coluna=coluna, status=status, campo=campo, candidatos=candidatos or [], divisao=divisao,
                          justificativa="teste")


def test_a_regra_guarda_so_a_duvida_entre_opcionais_do_parametro():
    """A trava da LGPD, item por item, no mapeamento aprovado (sem arquivo e sem IA)."""
    campos = layout_com(set(OBRIGATORIOS_DO_TESTE))
    endereco_dividido = DivisaoProposta(ferramenta="endereco", partes=[ParteDaDivisao(parte="cep",
                                                                                      campo="cep_residencial")])
    itens = [
        # Em dúvida só entre opcionais e deixada de fora: guardada
        item("C.E.P", StatusMapeamento.NAO_MAPEADO, candidatos=["cep_residencial", "cep_comercial"]),
        # Um candidato que o parâmetro não tem mais sai; o outro fica, uma vez só (a IA o repetiu)
        item("Fone", StatusMapeamento.NAO_MAPEADO, candidatos=["fax_antigo", "telefone_celular", "telefone_celular"]),
        # Desconhecida, sem candidato: nunca
        item("Religião", StatusMapeamento.NAO_MAPEADO),
        # A dúvida com um obrigatório: a empresa decide, e não fica sem rótulo
        item("Data", StatusMapeamento.NAO_MAPEADO, candidatos=["data_nascimento", "data_admissao"]),
        # A empresa escolheu mapear: vira um campo normal
        item("CEP da casa", StatusMapeamento.PROPOSTO, campo="cep_residencial", candidatos=["cep_residencial"]),
        # A coluna dividida em partes (as partes é que alimentam os campos)
        item("Endereço", StatusMapeamento.NAO_MAPEADO, candidatos=["cep_residencial"], divisao=endereco_dividido),
        # Só candidatos que saíram do parâmetro: é como se fosse desconhecida
        item("Ramal", StatusMapeamento.NAO_MAPEADO, candidatos=["fax_antigo"]),
    ]
    plano = MappingPlan(processamento_id="teste", versao_layout=1, configuracao="B3", modelo="teste",
                        versao_prompt="teste", itens=itens, chamou_llm=True)
    assert informacoes_sem_rotulo.colunas_sem_rotulo(plano, campos) == {
        "C.E.P": ["cep_residencial", "cep_comercial"], "Fone": ["telefone_celular"]}


# As colunas em dúvida só entre campos opcionais (variações do "C.E.P" do contrato): o nome, os candidatos e o valor de
# cada pessoa (a célula vazia não é guardada)
DUVIDAS_ENTRE_OPCIONAIS = [
    ("C.E.P", CANDIDATOS_DO_CEP, VALORES_DO_CEP),
    ("Fone", ["telefone_celular", "telefone_residencial"], ["(11) 91234-5678", "", "(21) 3232-1010"]),
    ("Cód. interno", ["codigo_unidade", "matricula"], ["A-17", "B-02", "C-33"]),
]


@pytest.mark.parametrize("extras_primeiro", [False, True])
@pytest.mark.parametrize("coluna, candidatos, valores", DUVIDAS_ENTRE_OPCIONAIS)
def test_a_coluna_em_duvida_entre_opcionais_fica_guardada_sem_rotulo(conexao, coluna, candidatos, valores,
                                                                    extras_primeiro):
    leitura = enviar(conexao, planilha({coluna: valores}, extras_primeiro), IaDoTeste({coluna: duvida(candidatos)}))
    processamento_id = leitura["processamento_id"]
    # A IA ficou em dúvida: é a coluna que a tela deixa de fora sozinha ("Deixar de fora")
    assert coluna_da_leitura(leitura, coluna)["precisa_decidir"] is True
    aceitar(conexao, processamento_id, escolhas({coluna: mapeamentos.IGNORAR}))
    for registro, valor in zip(registros(conexao, processamento_id), valores):
        if valor:
            assert registro["_sem_rotulo"] == [{"coluna": coluna, "valor": valor, "candidatos": candidatos}]
        else:
            # A célula vazia não é guardada
            assert "_sem_rotulo" not in registro
        # O valor nunca vira o valor de um campo: os candidatos continuam vazios
        for campo in candidatos:
            assert registro[campo] is None
    # A conferência (Cadastrar e o "Conferir e enviar") traz a lista ao lado dos valores, nunca dentro deles
    lista = cadastro.lista_para_conferir(conexao, EMPRESA, processamento_id)
    for linha, valor in zip(lista["linhas"], valores):
        if valor:
            assert linha["informacoes_sem_rotulo"] == [esperado_na_tela(coluna, valor, candidatos)]
        else:
            assert linha["informacoes_sem_rotulo"] == []
        assert coluna not in linha["valores"]


def test_o_exemplo_do_contrato_com_os_rotulos(conexao):
    """O "C.E.P" do contrato, com o nome legível de cada candidato, como a tela mostra."""
    processamento_id = envio_com_o_cep_em_duvida(conexao)
    primeira = cadastro.lista_para_conferir(conexao, EMPRESA, processamento_id)["linhas"][0]
    assert primeira["informacoes_sem_rotulo"] == [
        {"coluna": "C.E.P", "valor": "01310-100",
         "candidatos": [{"campo": "cep_residencial", "rotulo": "CEP residencial"},
                        {"campo": "cep_comercial", "rotulo": "CEP comercial"}]}]


@pytest.mark.parametrize("coluna_desconhecida, valores", [
    ("Religião", ["Católica", "Espírita", "Nenhuma"]),
    ("Time do coração", ["Palmeiras", "Bahia", "Grêmio"]),
])
def test_a_coluna_desconhecida_nunca_e_guardada(conexao, coluna_desconhecida, valores):
    extras = {coluna_desconhecida: valores, "C.E.P": ["01310-100", "20040-002", "30130-010"]}
    # A IA não reconhece a coluna desconhecida (a simulada, sozinha, liga nomes parecidos a algum campo)
    ia = IaDoTeste({"C.E.P": duvida(CANDIDATOS_DO_CEP), coluna_desconhecida: sem_campo([])})
    leitura = enviar(conexao, planilha(extras), ia)
    processamento_id = leitura["processamento_id"]
    # A IA não indicou nenhum campo para ela: é a coluna desconhecida
    desconhecida = coluna_da_leitura(leitura, coluna_desconhecida)
    assert desconhecida["campo"] is None and desconhecida["candidatos"] == []
    assert desconhecida["precisa_decidir"] is False
    aceitar(conexao, processamento_id, escolhas({"C.E.P": mapeamentos.IGNORAR}))
    for registro, valor in zip(registros(conexao, processamento_id), valores):
        # Só a dúvida entre opcionais fica guardada; a coluna desconhecida, nunca
        colunas_guardadas = []
        for informacao in registro["_sem_rotulo"]:
            colunas_guardadas.append(informacao["coluna"])
        assert colunas_guardadas == ["C.E.P"]
        assert valor not in json.dumps(registro, ensure_ascii=False)


@pytest.mark.parametrize("coluna, candidatos", [
    ("Data", ["data_admissao", "data_nascimento"]),
    ("Quando entrou", ["data_nascimento", "data_admissao"]),
])
def test_a_duvida_com_um_campo_obrigatorio_continua_como_hoje(conexao, coluna, candidatos):
    # O arquivo sem a coluna "Admissão": a data de admissão (obrigatória) só pode vir da coluna em dúvida
    datas = ["03/02/2025", "15/07/2024", "20/09/2023"]
    conteudo = planilha({coluna: datas}, sem=("Admissão",))
    leitura = enviar(conexao, conteudo, IaDoTeste({coluna: duvida(candidatos)}))
    processamento_id = leitura["processamento_id"]
    # Sem a escolha da empresa, o aceite não passa: a dúvida com um obrigatório é dela
    sem_escolha = cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, processamento_id,
                                              escolhas({}, sem=("Admissão",)), busca=busca_falsa)
    assert sem_escolha["etapa"] == "aprovar_mapeamento" and coluna in sem_escolha["erro"]
    # Deixada de fora, ela não é guardada, e a data de admissão sem coluna vira pendência
    aceitar(conexao, processamento_id, escolhas({coluna: mapeamentos.IGNORAR}, sem=("Admissão",)))
    for registro in registros(conexao, processamento_id):
        assert "_sem_rotulo" not in registro
    pendencias = set()
    for achado in validador.obter(conexao, processamento_id).achados:
        pendencias.add((achado.regra_id, achado.campo))
    assert ("OBRIGATORIO_SEM_COLUNA", "data_admissao") in pendencias


@pytest.mark.parametrize("campo_escolhido", CANDIDATOS_DO_CEP)
def test_a_coluna_que_a_empresa_mapeou_vira_um_campo_normal(conexao, campo_escolhido):
    valores = ["01310-100", "20040-002", "30130-010"]
    leitura = enviar(conexao, planilha({"C.E.P": valores}), IaDoTeste({"C.E.P": duvida(CANDIDATOS_DO_CEP)}))
    aceitar(conexao, leitura["processamento_id"], escolhas({"C.E.P": campo_escolhido}))
    for registro, valor in zip(registros(conexao, leitura["processamento_id"]), valores):
        # O CEP escolhido recebe o valor (só com os dígitos, como todo CEP), e nada fica sem rótulo
        assert registro[campo_escolhido] == valor.replace("-", "")
        assert "_sem_rotulo" not in registro


@pytest.mark.parametrize("resposta_da_ia, escolha_da_empresa", [
    # A IA reconheceu o campo com certeza, mas mandou candidatos; a empresa deixou a coluna de fora
    (certeza("cep_residencial", CANDIDATOS_DO_CEP), {"C.E.P": mapeamentos.IGNORAR}),
    # A IA disse que a coluna não é de nenhum campo, mas mandou candidatos
    (sem_campo(CANDIDATOS_DO_CEP), {}),
])
def test_sem_a_duvida_da_ia_a_coluna_de_fora_nao_e_guardada(conexao, resposta_da_ia, escolha_da_empresa):
    leitura = enviar(conexao, planilha({"C.E.P": VALORES_DO_CEP}), IaDoTeste({"C.E.P": resposta_da_ia}))
    # Só a coluna em dúvida guarda os candidatos no mapeamento
    assert coluna_da_leitura(leitura, "C.E.P")["candidatos"] == []
    aceitar(conexao, leitura["processamento_id"], escolhas(escolha_da_empresa))
    for registro in registros(conexao, leitura["processamento_id"]):
        assert "_sem_rotulo" not in registro


def test_a_releitura_tambem_so_guarda_candidatos_na_duvida(conexao):
    leitura = enviar(conexao, planilha({"C.E.P": VALORES_DO_CEP}), IaDoTeste({"C.E.P": duvida(CANDIDATOS_DO_CEP)}))
    # "Ajude a IA a acertar": na releitura, a IA acha o campo com certeza, mas manda candidatos junto
    ia_com_certeza = IaDoTeste({"C.E.P": certeza("cep_residencial", CANDIDATOS_DO_CEP)})
    relida = cadastro.reler_colunas(conexao, EMPRESA, leitura["processamento_id"],
                                    [{"coluna": "C.E.P", "dica": "é o CEP da casa da pessoa"}],
                                    cliente=ia_com_certeza.cliente(), busca=busca_falsa)
    coluna = coluna_da_leitura(relida, "C.E.P")
    assert coluna["campo"] == "cep_residencial" and coluna["candidatos"] == []


# ---------------- A lista acompanha a pessoa ----------------

def test_a_lista_sobrevive_a_correcao_e_a_revalidacao(conexao):
    processamento_id = envio_com_o_cep_em_duvida(conexao)
    primeira = cadastro.lista_para_conferir(conexao, EMPRESA, processamento_id)["linhas"][0]
    assert primeira["informacoes_sem_rotulo"] != []
    # A empresa corrige o nome na conferência: a lista é refeita (corrigida e revalidada), e a informação continua
    corrigida = cadastro.corrigir_na_conferencia(conexao, EMPRESA, LOGIN, processamento_id, primeira["linha"],
                                                 "nome_completo", "Bianca Torres Lima")
    assert corrigida["linhas"][0]["valores"]["nome_completo"] == "Bianca Torres Lima"
    assert corrigida["linhas"][0]["informacoes_sem_rotulo"] == primeira["informacoes_sem_rotulo"]
    # A validação de novo (como a do envio ao banco) também não mexe nela
    validador.executar(conexao, processamento_id, EMPRESA)
    assert registros(conexao, processamento_id)[0]["_sem_rotulo"][0]["valor"] == VALORES_DO_CEP[0]


def guardadas_no_cadastro(conexao) -> dict:
    """{cpf: o texto da coluna informacoes_sem_rotulo} dos cadastrados da empresa do teste."""
    guardadas = {}
    consulta = conexao.execute("SELECT cpf, informacoes_sem_rotulo FROM funcionarios_homologados WHERE empresa_id = ?",
                               (EMPRESA,))
    for cpf, texto in consulta:
        guardadas[cpf] = texto
    return guardadas


def test_a_lista_vai_na_devolucao_segue_no_cadastro_e_volta_na_inclusao(conexao):
    processamento_id = envio_com_o_cep_em_duvida(conexao)
    cadastro.homologar(conexao, EMPRESA, LOGIN, processamento_id, conferiu_a_lista=True)
    # O banco aponta a primeira pessoa e aprova as outras: a apontada volta num envio de devolução
    primeira_linha = registros(conexao, processamento_id)[0]["_linha"]
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, primeira_linha, "outro",
                               "Confira o endereço desta pessoa, por favor.")
    avaliado = avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id,
                                          decisao="aprovar_e_devolver_marcados")
    devolvida = registros(conexao, avaliado["envio_de_devolucao"])[0]
    assert devolvida["_sem_rotulo"] == [{"coluna": "C.E.P", "valor": VALORES_DO_CEP[0],
                                         "candidatos": CANDIDATOS_DO_CEP}]
    # As aprovadas seguem com a lista no cadastro (a coluna nova, em texto JSON); sem o valor, a coluna fica vazia
    guardadas = guardadas_no_cadastro(conexao)
    assert json.loads(guardadas[cpf_valido(PESSOAS[1][1])]) == [
        {"coluna": "C.E.P", "valor": VALORES_DO_CEP[1], "candidatos": CANDIDATOS_DO_CEP}]
    assert guardadas[cpf_valido(PESSOAS[2][1])] is None
    # A inclusão com as mesmas colunas: a "C.E.P" vem do aceite anterior (a IA não é chamada para ela) e volta a ser
    # guardada, mesmo com uma IA que, perguntada, proporia um campo
    valores_da_inclusao = ["40010-000", "50030-230"]
    leitura = enviar(conexao, planilha({"C.E.P": valores_da_inclusao}, pessoas=OUTRAS_PESSOAS), IaDoTeste())
    assert coluna_da_leitura(leitura, "C.E.P")["origem"] == "reuso"
    aceitar(conexao, leitura["processamento_id"], escolhas({}))
    for registro, valor in zip(registros(conexao, leitura["processamento_id"]), valores_da_inclusao):
        assert registro["_sem_rotulo"] == [{"coluna": "C.E.P", "valor": valor, "candidatos": CANDIDATOS_DO_CEP}]


# ---------------- As rotas da API ----------------

@pytest.fixture
def ambiente_da_api(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com os três logins e o envio com o "C.E.P" aceito."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_sem_rotulo.db"

    def conectar_no_banco_do_teste(caminho_pedido=None):
        """No lugar de auth.conectar: toda rota abre o banco deste teste."""
        return conectar_original(caminho)

    monkeypatch.setattr(auth, "conectar", conectar_no_banco_do_teste)
    conexao_do_teste = conectar_original(caminho)
    marcar_como_obrigatorios(conexao_do_teste, *OBRIGATORIOS_DO_TESTE, so_estes=True)
    processamento_id = envio_com_o_cep_em_duvida(conexao_do_teste)
    auth.cadastrar_usuario(conexao_do_teste, LOGIN, SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, LOGIN_DA_OUTRA, SENHA_DE_TESTE, Perfil.EMPRESA, OUTRA_EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)
    yield {"conexao": conexao_do_teste, "envio": processamento_id}
    conexao_do_teste.close()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado (com a senha de teste)."""
    navegador = TestClient(aplicacao)
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200, resposta.text
    return navegador


def conferir_as_pessoas(pessoas: list[dict]) -> None:
    """Cada pessoa da lista traz, ao lado dos dados dela, a lista esperada pelo CPF."""
    esperado = esperado_por_cpf(PESSOAS, VALORES_DO_CEP)
    assert len(pessoas) == len(PESSOAS)
    for pessoa in pessoas:
        assert pessoa["informacoes_sem_rotulo"] == esperado[pessoa["cpf"]]


def conferir_as_linhas(linhas: list[dict]) -> None:
    """Cada linha da conferência traz a lista esperada, ao lado da linha, dos valores e das pendências."""
    assert len(linhas) == len(PESSOAS)
    for linha, valor in zip(linhas, VALORES_DO_CEP):
        esperado = []
        if valor:
            esperado = [esperado_na_tela("C.E.P", valor, CANDIDATOS_DO_CEP)]
        assert linha["informacoes_sem_rotulo"] == esperado
        assert "informacoes_sem_rotulo" not in linha["valores"]


def mandar_e_aprovar(rh: TestClient, banco_logado: TestClient, envio: str) -> None:
    """A empresa manda o envio ao banco, e o banco aprova (os funcionários ficam cadastrados)."""
    enviado = rh.post("/api/empresa/cadastro/" + envio + "/homologar", json={"conferi_a_lista": True})
    assert enviado.status_code == 200 and enviado.json()["etapa"] == "avaliar_no_banco", enviado.text
    aprovado = banco_logado.post("/api/banco/envios/" + envio + "/avaliar", json={"decisao": "aprovar"})
    assert aprovado.status_code == 200, aprovado.text


def test_as_rotas_da_empresa_trazem_a_lista_ao_lado_dos_dados(ambiente_da_api):
    envio = ambiente_da_api["envio"]
    rh = entrar(LOGIN)
    base = "/api/empresa/cadastro/" + envio
    # Cadastrar e o "Conferir e enviar" de Acompanhar: cada linha da lista
    lista = rh.get(base + "/lista")
    assert lista.status_code == 200
    conferir_as_linhas(lista.json()["linhas"])
    # A correção na conferência devolve a lista refeita, ainda com a informação
    primeira = lista.json()["linhas"][0]
    corrigida = rh.post(base + "/lista/corrigir", json={"linha": primeira["linha"], "campo": "nome_completo",
                                                         "valor": "Bianca Torres Lima"})
    assert corrigida.status_code == 200, corrigida.text
    conferir_as_linhas(corrigida.json()["linhas"])
    # Acompanhar: as pessoas do envio ainda com a empresa
    conferir_as_pessoas(rh.get("/api/empresa/funcionarios").json())


def test_as_rotas_do_banco_e_o_cadastro_trazem_a_lista(ambiente_da_api):
    envio = ambiente_da_api["envio"]
    rh = entrar(LOGIN)
    banco_logado = entrar(LOGIN_DO_BANCO)
    enviado = rh.post("/api/empresa/cadastro/" + envio + "/homologar", json={"conferi_a_lista": True})
    assert enviado.status_code == 200, enviado.text
    # Envios (banco): cada pessoa traz a lista ao lado de "campos", nunca dentro dele
    pessoas = banco_logado.get("/api/banco/envios/" + envio + "/pessoas").json()
    conferir_as_pessoas(pessoas)
    for pessoa in pessoas:
        assert "informacoes_sem_rotulo" not in pessoa["campos"]
    # Visão geral da empresa (banco), com as pessoas em análise
    visao = "/api/banco/empresas/" + EMPRESA + "/visao_geral"
    conferir_as_pessoas(banco_logado.get(visao).json()["funcionarios"])
    # O banco aprova: a lista vem do cadastro, em Acompanhar, na ficha e na Visão geral
    aprovado = banco_logado.post("/api/banco/envios/" + envio + "/avaliar", json={"decisao": "aprovar"})
    assert aprovado.status_code == 200, aprovado.text
    cadastrados = rh.get("/api/empresa/funcionarios").json()
    conferir_as_pessoas(cadastrados)
    for pessoa in cadastrados:
        assert pessoa["situacao"] == "Cadastrado"
        ficha = rh.get("/api/empresa/funcionarios/" + pessoa["id"]).json()
        assert ficha["informacoes_sem_rotulo"] == pessoa["informacoes_sem_rotulo"]
    conferir_as_pessoas(banco_logado.get(visao).json()["funcionarios"])


def test_a_lista_nao_entra_nos_downloads_nem_no_arquivo_final(ambiente_da_api):
    envio = ambiente_da_api["envio"]
    rh = entrar(LOGIN)
    banco_logado = entrar(LOGIN_DO_BANCO)
    mandar_e_aprovar(rh, banco_logado, envio)
    # O arquivo final do banco (o da homologação), o download da empresa (Acompanhar) e o do banco (Envios)
    arquivo_final = homologacao.obter(ambiente_da_api["conexao"], envio)["arquivo"].decode("utf-8")
    identificadores = []
    for pessoa in rh.get("/api/empresa/funcionarios").json():
        identificadores.append(pessoa["id"])
    baixado_pela_empresa = rh.post("/api/empresa/funcionarios/baixar", json={"identificadores": identificadores})
    baixado_pelo_banco = banco_logado.get("/api/banco/envios/" + envio + "/baixar")
    assert baixado_pela_empresa.status_code == 200 and baixado_pelo_banco.status_code == 200
    for conteudo in (arquivo_final, baixado_pela_empresa.text, baixado_pelo_banco.text):
        # Nem o valor (como veio ou só com os dígitos), nem a coluna, nem a chave aparecem
        for valor in VALORES_DO_CEP:
            if valor:
                assert valor not in conteudo and valor.replace("-", "") not in conteudo
        assert "C.E.P" not in conteudo and "sem_rotulo" not in conteudo


def test_as_rotas_401_403_e_uma_empresa_nunca_ve_a_outra(ambiente_da_api):
    envio = ambiente_da_api["envio"]
    rotas_da_empresa = ["/api/empresa/funcionarios", "/api/empresa/cadastro/" + envio + "/lista"]
    rotas_do_banco = ["/api/banco/envios/" + envio + "/pessoas", "/api/banco/empresas/" + EMPRESA + "/visao_geral"]
    # Sem login: 401 em todas
    sem_login = TestClient(aplicacao)
    for rota in rotas_da_empresa + rotas_do_banco:
        assert sem_login.get(rota).status_code == 401, rota
    # O outro perfil: 403
    banco_logado = entrar(LOGIN_DO_BANCO)
    for rota in rotas_da_empresa:
        assert banco_logado.get(rota).status_code == 403, rota
    rh = entrar(LOGIN)
    for rota in rotas_do_banco:
        assert rh.get(rota).status_code == 403, rota
    # A outra empresa: o envio da Aurora não existe para ela, e a lista dela não traz nada da Aurora
    outra = entrar(LOGIN_DA_OUTRA)
    assert outra.get("/api/empresa/cadastro/" + envio + "/lista").status_code == 404
    lista_da_outra = outra.get("/api/empresa/funcionarios")
    assert lista_da_outra.status_code == 200
    for valor in VALORES_DO_CEP:
        if valor:
            assert valor not in lista_da_outra.text
