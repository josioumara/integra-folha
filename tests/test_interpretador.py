"""Agente Interpretador (em MOCK), contrato, guardrail de saída, reuso e aceite humano."""
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from agents import interpretador
from baselines.baseline_mapper import normalizar
from models.contratos import EstadoProcessamento, StatusMapeamento, carregar_layout
from services import auditoria, banco, config, mapeamentos, parametros, processamentos, provedores_de_ia
from services.llm_client import LLMClient, RespostaLLM

# Os arquivos das empresas
RAIZ = Path(__file__).resolve().parent.parent
ENVIOS = RAIZ / "data" / "synthetic" / "envios"


def gabarito(nome_do_arquivo):
    """O gabarito de um arquivo (mesmo nome, com .json)."""
    nome_do_gabarito = nome_do_arquivo.replace(".xlsx", ".json").replace(".csv", ".json")
    return json.loads((RAIZ / "data" / "golden" / nome_do_gabarito).read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def gerar_envios():
    """Os arquivos de envio não vão para o Git: gera antes dos testes."""
    from scripts.gerar_dados import main
    main()


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def busca_falsa(nome, k=3):
    """RAG de mentira: devolve um trecho com fonte, sem depender do índice nem do modelo de embeddings."""
    return [{"fonte": f"Mapeamentos homologados › {nome}", "texto": f"Mapeamentos homologados › {nome}\nex."}]


def receber(conexao, arquivo, empresa="EMP001"):
    """Recebe um arquivo das empresas e devolve o perfil dele."""
    return processamentos.receber_arquivo(conexao, (ENVIOS / arquivo).read_bytes(), arquivo, empresa,
                                          date(2026, 9, 1), "teste").perfil


def cliente_que_responde(*respostas):
    """Cliente MOCK que devolve as respostas na ordem (para simular erro e acerto do LLM)."""
    fila = list(respostas)

    def proxima_resposta(prompt):
        """Tira a próxima resposta da fila."""
        return fila.pop(0)
    return LLMClient(modo="mock", respostas_mock={interpretador.TAREFA: proxima_resposta})


def cliente_proibido():
    """Cliente que falha o teste se for chamado (prova que o LLM não foi usado)."""
    def falhar(prompt):
        """Qualquer chamada é um erro."""
        raise AssertionError("o LLM não deveria ter sido chamado")
    return LLMClient(modo="mock", respostas_mock={interpretador.TAREFA: falhar})


def plano(conexao, perfil, cliente=None, configuracao="B3"):
    """Interpreta o processamento com a busca falsa."""
    return mapeamentos.interpretar_processamento(conexao, perfil.processamento_id, perfil.empresa_id,
                                                 cliente=cliente, configuracao=configuracao, busca=busca_falsa)


def _item_da_coluna(plano_de_mapeamento, coluna):
    """O item do plano para uma coluna."""
    for item in plano_de_mapeamento.itens:
        if item.coluna == coluna:
            return item
    raise KeyError(coluna)


def _alguma_observacao_com(plano_de_mapeamento, trecho) -> bool:
    """True se alguma observação do plano contém o trecho."""
    for observacao in plano_de_mapeamento.observacoes:
        if trecho in observacao:
            return True
    return False


def _termos_normalizados(nome_do_arquivo):
    """Os termos de um arquivo do vocabulário, normalizados."""
    termos = set()
    with open(RAIZ / "data" / "vocabulario" / nome_do_arquivo, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            termos.add(normalizar(linha["termo"]))
    return termos


# ---------- Mapeamento dos arquivos da demo ----------

def test_aurora_e_mapeada_como_no_gabarito(conexao):
    """A Aurora sai exatamente como no gabarito, tudo PROPOSTO, e o processamento espera o aceite."""
    perfil = receber(conexao, "aurora_carga_inicial.xlsx")
    proposta = plano(conexao, perfil)
    esperado = gabarito("aurora_carga_inicial.xlsx")["mapeamento"]
    campo_da_coluna = {}
    for item in proposta.itens:
        campo_da_coluna[item.coluna] = item.campo
    assert campo_da_coluna == esperado
    for item in proposta.itens:
        assert item.status == StatusMapeamento.PROPOSTO
    assert proposta.modelo == "mock" and proposta.chamou_llm
    assert processamentos.obter(conexao, perfil.processamento_id).status == EstadoProcessamento.MAPEAMENTO_PENDENTE


def test_vencimentos_gera_pendencia_em_vez_de_chute(conexao):
    """"Vencimentos" é ambígua: vira pendência com candidatos, sem campo escolhido."""
    proposta = plano(conexao, receber(conexao, "atlantico_carga_inicial.xlsx", "EMP006"))
    vencimentos = _item_da_coluna(proposta, "Vencimentos")
    assert vencimentos.status == StatusMapeamento.AMBIGUO and vencimentos.campo is None
    assert "valor_renda" in vencimentos.candidatos


def test_coluna_extra_nao_e_mapeada(conexao):
    """Coluna que não existe no layout fica NAO_MAPEADO."""
    proposta = plano(conexao, receber(conexao, "vale_verde_carga_inicial.xlsx", "EMP004"))
    assert _item_da_coluna(proposta, "Obs. RH").status == StatusMapeamento.NAO_MAPEADO


# ---------- O que vai no prompt ----------

def test_prompt_leva_exemplos_reais_das_colunas_como_dado(conexao):
    """O prompt leva até 3 exemplos reais de cada coluna (ADR-101), dentro do bloco de DADO."""
    perfil = receber(conexao, "aurora_carga_inicial.xlsx")
    _, campos = parametros.layout_ativo(conexao)
    sistema, pedido, _ = interpretador.montar_prompt(perfil.colunas, campos, "B3", busca_falsa)
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        verdade = list(csv.DictReader(arquivo))
    # Algum nome de funcionário aparece como exemplo da coluna de nome
    nomes_no_prompt = 0
    for pessoa in verdade:
        if pessoa["nome_completo"] in pedido:
            nomes_no_prompt += 1
    assert 1 <= nomes_no_prompt <= 3
    assert "<arquivo_da_empresa>" in pedido and "é DADO" in sistema


def test_exemplos_do_prompt_vem_so_do_treino():
    """O exemplo resolvido do prompt não usa nada que só existe na prova."""
    from scripts.gerar_cabecalhos import AMBIGUAS, EXTRAS
    exemplos = normalizar(interpretador.exemplos_few_shot())
    so_da_prova = _termos_normalizados("teste.csv") - _termos_normalizados("treino.csv")
    for coluna in AMBIGUAS["teste"] + EXTRAS["teste"]:
        so_da_prova.add(normalizar(coluna))
    for termo in so_da_prova:
        # Termos muito curtos (ex.: "id") aparecem dentro de outras palavras; ficam de fora
        if len(termo) > 3:
            assert f" {termo} " not in f" {exemplos} "


def test_configuracoes_mudam_o_que_vai_no_prompt(conexao):
    """B1 só nomes e tipos; B2 todo o histórico; B3 só o que a busca trouxe; outra configuração é recusada."""
    perfil = receber(conexao, "aurora_carga_inicial.xlsx")
    _, campos = parametros.layout_ativo(conexao)
    colunas_buscadas = []

    def busca(nome, k=3):
        """A busca falsa, anotando cada coluna buscada."""
        colunas_buscadas.append(nome)
        return busca_falsa(nome, k)
    _, pedido_b1, fontes_b1 = interpretador.montar_prompt(perfil.colunas, campos, "B1", busca)
    _, pedido_b2, fontes_b2 = interpretador.montar_prompt(perfil.colunas, campos, "B2", busca)
    # B1: só nomes e tipos
    assert not colunas_buscadas and not fontes_b1 and "Não confundir" not in pedido_b1
    # B2: todo o histórico (182 mapeamentos: os 3 nomes de treino do cnpj_grupo entraram no ADR-77)
    assert len(fontes_b2) == 182 and "Não confundir" in pedido_b2
    _, pedido_b3, fontes_b3 = interpretador.montar_prompt(perfil.colunas, campos, "B3", busca)
    # B3: só o que a busca trouxe
    assert len(colunas_buscadas) == len(perfil.colunas) and len(fontes_b3) < len(fontes_b2)
    with pytest.raises(ValueError):
        interpretador.montar_prompt(perfil.colunas, campos, "B9", busca)


# ---------- Contrato e guardrail de saída ----------

def _resposta(*itens):
    """Uma resposta do LLM no contrato, com os campos que faltarem preenchidos."""
    itens_completos = []
    for item in itens:
        completo = {"candidatos": [], "fontes": [], "justificativa": "x"}
        completo.update(item)
        itens_completos.append(completo)
    return json.dumps({"itens": itens_completos})


@pytest.fixture
def csv_simples(conexao):
    """Um arquivo pequeno com três colunas: Nome, CPF e Salário."""
    conteudo = "Nome;CPF;Salário\nAna;52998224725;3000\nBia;11144477735;4000\n".encode()
    return processamentos.receber_arquivo(conexao, conteudo, "s.csv", "EMP002", date(2026, 9, 1), "t").perfil


def test_saida_invalida_e_rejeitada_e_o_llm_tenta_de_novo(conexao, csv_simples):
    """Resposta fora do contrato na 1ª tentativa; a 2ª, certa, vale."""
    valida = _resposta({"coluna": "Nome", "campo": "nome_completo", "status": "PROPOSTO"},
                       {"coluna": "CPF", "campo": "cpf", "status": "PROPOSTO"},
                       {"coluna": "Salário", "campo": "valor_renda", "status": "PROPOSTO"})
    proposta = plano(conexao, csv_simples, cliente_que_responde("Claro! Aqui está o mapeamento...", valida))
    campos = []
    for item in proposta.itens:
        campos.append(item.campo)
    assert campos == ["nome_completo", "cpf", "valor_renda"]
    assert _alguma_observacao_com(proposta, "Tentativa 1")


def test_status_fora_do_contrato_e_rejeitado(conexao, csv_simples):
    """Duas respostas fora do contrato: plano de emergência, tudo para confirmação humana."""
    invalida = _resposta({"coluna": "Nome", "campo": "nome_completo", "status": "TALVEZ"})
    proposta = plano(conexao, csv_simples, cliente_que_responde(invalida, invalida))
    # Plano de emergência
    for item in proposta.itens:
        assert item.status == StatusMapeamento.AMBIGUO and item.origem == "regra"
    assert _alguma_observacao_com(proposta, "falhou duas vezes")


def test_guardrail_de_saida(conexao, csv_simples):
    """Campo inexistente, disputa, coluna inventada e fonte inventada: nada disso passa."""
    resposta = _resposta(
        {"coluna": "Nome", "campo": "nome_completo", "status": "PROPOSTO", "fontes": ["Manual secreto"]},
        {"coluna": "CPF", "campo": "numero_da_sorte", "status": "PROPOSTO"},        # campo inexistente
        {"coluna": "Salário", "campo": "nome_completo", "status": "PROPOSTO"},      # disputa com "Nome"
        {"coluna": "Senha do banco", "campo": "cpf", "status": "PROPOSTO"})        # coluna inventada
    proposta = plano(conexao, csv_simples, cliente_que_responde(resposta))
    item_da_coluna = {}
    for item in proposta.itens:
        item_da_coluna[item.coluna] = item
    assert set(item_da_coluna) == {"Nome", "CPF", "Salário"}
    assert item_da_coluna["CPF"].status == StatusMapeamento.AMBIGUO and item_da_coluna["CPF"].campo is None
    assert item_da_coluna["Nome"].status == item_da_coluna["Salário"].status == StatusMapeamento.AMBIGUO
    # Fonte inventada removida
    assert item_da_coluna["Nome"].fontes == []
    texto = " ".join(proposta.observacoes)
    assert "não existe no layout" in texto and "não existe no arquivo" in texto and "Fonte" in texto


def test_modo_llm_sem_provedor_avisa_em_vez_de_esconder(conexao, csv_simples):
    """Modo llm sem modelo escolhido no .env: erro claro, em vez de fingir que chamou a IA."""
    with pytest.raises(provedores_de_ia.ConfiguracaoDoProvedor, match="MODELO_GRANDE"):
        plano(conexao, csv_simples, LLMClient(modo="llm"))


# ---------- Reuso nas inclusões (ADR-24) e aceite humano (ADR-16) ----------

def _aprovar_aurora(conexao, banco_aprovou: bool = True):
    """Recebe, interpreta e aceita a carga inicial da Aurora; por padrão, o banco também aprova o envio."""
    perfil = receber(conexao, "aurora_carga_inicial.xlsx")
    plano(conexao, perfil)
    aceito = mapeamentos.aprovar(conexao, perfil.processamento_id, "EMP001", {}, "empresa.aurora")
    # O reuso só vale depois da aprovação do banco (o envio fica HOMOLOGADO)
    if banco_aprovou:
        processamentos.atualizar_status(conexao, perfil.processamento_id, EstadoProcessamento.HOMOLOGADO)
    return aceito


def test_sem_a_aprovacao_do_banco_nao_ha_reuso(conexao):
    """Só o aceite da empresa não basta: o banco ainda pode devolver, então a inclusão vai para a IA."""
    _aprovar_aurora(conexao, banco_aprovou=False)
    inclusao = receber(conexao, "aurora_inclusao.xlsx")
    proposta = plano(conexao, inclusao)
    assert proposta.chamou_llm
    for item in proposta.itens:
        assert item.origem != "reuso"


def test_inclusao_com_as_mesmas_colunas_nao_chama_o_llm(conexao):
    """Inclusão com as colunas já aprovadas: reuso total, sem chamar o LLM."""
    _aprovar_aurora(conexao)
    inclusao = receber(conexao, "aurora_inclusao.xlsx")
    proposta = plano(conexao, inclusao, cliente_proibido())
    assert not proposta.chamou_llm
    for item in proposta.itens:
        assert item.origem == "reuso"


def test_so_a_coluna_nova_vai_para_o_llm(conexao):
    """Três colunas conhecidas e uma nova: só a nova vai no prompt."""
    aprovado = _aprovar_aurora(conexao)
    colunas = []
    for item in aprovado.itens[:3]:
        colunas.append(item.coluna)
    colunas.append("Crachá Novo")
    conteudo = (";".join(colunas) + "\n" + ";".join(["a", "b", "c", "d"]) + "\n").encode()
    perfil = processamentos.receber_arquivo(conexao, conteudo, "inc.csv", "EMP001", date(2026, 9, 1), "t").perfil
    prompts = []

    def registrar(prompt):
        """Guarda o prompt e responde com o simulador."""
        prompts.append(prompt)
        return interpretador.simular_llm(prompt)
    proposta = plano(conexao, perfil, LLMClient(modo="mock", respostas_mock={interpretador.TAREFA: registrar}))
    bloco_do_arquivo = prompts[0].split("<arquivo_da_empresa>")[1]
    assert "Crachá Novo" in bloco_do_arquivo and colunas[0] not in bloco_do_arquivo
    origens = []
    for item in proposta.itens:
        origens.append(item.origem)
    assert origens == ["reuso", "reuso", "reuso", "llm"]


def test_aceite_exige_decisao_nas_colunas_ambiguas(conexao):
    """Sem decidir "Vencimentos", não aprova; decidida, aprova uma vez só."""
    perfil = receber(conexao, "atlantico_carga_inicial.xlsx", "EMP006")
    plano(conexao, perfil)
    with pytest.raises(ValueError, match="Vencimentos"):
        mapeamentos.aprovar(conexao, perfil.processamento_id, "EMP006", {}, "rh")
    aprovado = mapeamentos.aprovar(conexao, perfil.processamento_id, "EMP006", {"Vencimentos": "valor_renda"}, "rh")
    vencimentos = _item_da_coluna(aprovado, "Vencimentos")
    assert vencimentos.campo == "valor_renda" and vencimentos.origem == "humano"
    assert processamentos.obter(conexao, perfil.processamento_id).status == EstadoProcessamento.MAPEAMENTO_APROVADO
    tipos_de_evento = []
    for evento in auditoria.eventos(conexao, perfil.processamento_id):
        tipos_de_evento.append(evento["tipo"])
    assert "MAPEAMENTO_APROVADO" in tipos_de_evento
    with pytest.raises(ValueError, match="já foi aprovado"):
        mapeamentos.aprovar(conexao, perfil.processamento_id, "EMP006", {}, "rh")


def test_aceite_recusa_campo_inexistente_e_campo_repetido(conexao, csv_simples):
    """Campo que não existe e duas colunas no mesmo campo são recusados."""
    plano(conexao, csv_simples)
    processamento_id = csv_simples.processamento_id
    with pytest.raises(ValueError, match="não existe"):
        mapeamentos.aprovar(conexao, processamento_id, "EMP002", {"Nome": "apelido"}, "rh")
    with pytest.raises(ValueError, match="mesmo campo"):
        mapeamentos.aprovar(conexao, processamento_id, "EMP002",
                            {"Nome": "cpf", "CPF": "cpf", "Salário": mapeamentos.IGNORAR}, "rh")


def test_empresa_nao_interpreta_processamento_de_outra(conexao, csv_simples):
    """A Aurora não consegue interpretar o arquivo da Horizonte."""
    with pytest.raises(KeyError):
        mapeamentos.interpretar_processamento(conexao, csv_simples.processamento_id, "EMP001", busca=busca_falsa)


# ---------------- Formato garantido (ADR-107) ----------------

class ClienteQueAnota:
    """Cliente de IA de mentira que anota os parâmetros extras de cada chamada (ex.: o esquema da resposta)."""

    def __init__(self, texto: str):
        """texto: a resposta que o cliente devolve sempre."""
        self.texto = texto
        self.extras_de_cada_chamada = []

    def gerar(self, tarefa, prompt, sistema="", modelo=None, temperatura=0.0, **extras):
        """Anota os extras e devolve a resposta, como se viesse do provedor."""
        self.extras_de_cada_chamada.append(extras)
        return RespostaLLM(texto=self.texto, modo="llm", modelo="modelo-de-teste")


def _interpretar_com(cliente, perfil):
    """Chama o Interpretador direto (B3, busca falsa), com o cliente informado."""
    return interpretador.interpretar(perfil, carregar_layout(), 1, cliente, configuracao="B3", busca=busca_falsa)


def test_formato_garantido_desligado_chama_como_antes(monkeypatch, conexao, csv_simples):
    """Desligado (padrão): a chamada é a de antes, sem o parâmetro do esquema (o medidor congelado não o conhece)."""
    monkeypatch.setattr(config, "INTERPRETADOR_FORMATO_GARANTIDO", False)
    cliente = ClienteQueAnota(_resposta({"coluna": "Nome", "campo": "nome_completo", "status": "PROPOSTO"}))
    _interpretar_com(cliente, csv_simples)
    assert cliente.extras_de_cada_chamada == [{}]


def test_formato_garantido_ligado_manda_o_esquema(monkeypatch, conexao, csv_simples):
    """Ligado: o esquema da resposta vai junto com o pedido."""
    monkeypatch.setattr(config, "INTERPRETADOR_FORMATO_GARANTIDO", True)
    cliente = ClienteQueAnota(_resposta({"coluna": "Nome", "campo": "nome_completo", "status": "PROPOSTO"}))
    _interpretar_com(cliente, csv_simples)
    assert cliente.extras_de_cada_chamada[0]["esquema_json"] == interpretador.esquema_da_resposta()


def _objetos_do_esquema(esquema: dict) -> list[dict]:
    """Todos os objetos ("type": "object") de dentro do esquema, em qualquer nível."""
    encontrados = []
    pendentes = [esquema]
    while pendentes:
        atual = pendentes.pop()
        if atual.get("type") == "object":
            encontrados.append(atual)
            pendentes.extend(atual["properties"].values())
        if "items" in atual:
            pendentes.append(atual["items"])
        for opcao in atual.get("anyOf", []):
            pendentes.append(opcao)
    return encontrados


def test_esquema_segue_as_regras_do_bedrock():
    """Todo objeto fecha a porta a campos extras e exige todos os seus campos (regras do formato garantido)."""
    objetos = _objetos_do_esquema(interpretador.esquema_da_resposta())
    # O envelope, o item, a divisão e a parte da divisão
    assert len(objetos) == 4
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert sorted(objeto["required"]) == sorted(objeto["properties"])


def test_esquema_aceita_todos_os_status_do_contrato():
    """Os status do esquema são os mesmos do contrato (inclusive DIVIDIR)."""
    item = interpretador.esquema_da_resposta()["properties"]["itens"]["items"]
    assert item["properties"]["status"]["enum"] == ["PROPOSTO", "AMBIGUO", "NAO_MAPEADO", "DIVIDIR"]
