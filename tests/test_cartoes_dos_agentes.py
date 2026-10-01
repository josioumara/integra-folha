"""Testes dos cartões dos agentes: a tela Acompanhamento dos agentes (GET /api/banco/telemetria/ia, cartoes_por_agente).

O que se prova aqui:
    - um cartão por agente de IA, sempre na ordem do fluxo, mesmo para quem nunca trabalhou;
    - os nomes gravados do mesmo agente se juntam ("Leitor de Documentos" + "Leitor de documentos" = Leitor);
    - as execuções antigas do Consultor, que saiu do sistema (ADR-144), não viram cartão, mas continuam na visão geral
      e na tabela de custo (gasto não se apaga);
    - "Regra" e "Humano" não viram cartão;
    - como cada execução terminou (certo, erro, barrada pelo guardrail);
    - só o modelo real entra na tela: as execuções simuladas (MOCK) ficam de fora dos cartões e dos números, e a
      aceitação conta só as propostas feitas com o modelo real;
    - duração, última execução e custo ficam vazios (None) quando não há o que medir: nunca um zero inventado;
    - a rota é só do banco: sem login 401, empresa 403;
    - o filtro por período: ?de=&ate= vale para os cartões, os números e as execuções
      recentes; data inválida ou começo depois do fim: 400;
    - a aceitação de cada agente (aprovadas sem mudança, corrigidas, recusadas e o percentual), a partir do que a
      aplicação já grava; sem dado, None ("não medido"), nunca zero.

As execuções e as propostas são gravadas direto nas tabelas, num banco só deste teste: assim cada número esperado é
conhecido de antemão. Sem dizer o modelo, a execução de teste é do modelo real (MODELO_REAL_DE_TESTE).
"""
import inspect
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agents import conferidor_da_leitura, endomarketing, interpretador
from api.principal import aplicacao
from models.contratos import ItemMapeamento, MappingPlan, Perfil, StatusMapeamento
from services import (aceitacao_dos_agentes, auth, banco, correcoes, divisao_da_coluna, execucoes, mapeamentos, painel,
                      portal_do_banco, processamentos, validador)
from services.auth import Usuario

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Usuário de mentira do banco, para chamar o serviço direto
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
# Um horário fixo de partida, para as execuções terem horários conhecidos
PARTIDA = datetime(2026, 9, 28, 10, 0, 0, tzinfo=timezone.utc)
# As chaves que todo cartão traz (o contrato com a tela)
CHAVES_DO_CARTAO = {"agente", "nome_na_tela", "o_que_faz", "execucoes", "deram_certo", "com_erro",
                    "barradas_pelo_guardrail", "com_ia_real", "simuladas", "duracao_media_s", "ultima_execucao",
                    "custo_usd", "registra_o_trabalho", "aceitacao", "aceitacao_sem_medida_porque"}
# As chaves da aceitação, quando ela foi medida
CHAVES_DA_ACEITACAO = {"aprovadas", "corrigidas", "recusadas", "percentual_aprovadas", "fonte"}
# Um horário dentro do período dos testes de aceitação (setembro de 2026) e um fora dele (agosto)
DENTRO_DO_PERIODO = "2026-09-20T10:00:00+00:00"
FORA_DO_PERIODO = "2026-08-10T10:00:00+00:00"
# O período dos testes de aceitação: setembro de 2026 inteiro
SETEMBRO = (date(2026, 9, 1), date(2026, 9, 30))
# O nome de um modelo real (a execução com este modelo tem a origem REAL) e o do modo simulado (a origem fica MOCK)
MODELO_REAL_DE_TESTE = "claude-sonnet-4-6"
MODELO_SIMULADO = "mock"
# Quantos minutos antes da PARTIDA (28/09, 10h) fica o dia DENTRO_DO_PERIODO (20/09, 10h): 8 dias
MINUTOS_ATE_O_DIA_DAS_PROPOSTAS = -8 * 24 * 60


@pytest.fixture
def conexao(tmp_path):
    """Um banco vazio, só deste teste."""
    conexao_do_teste = banco.conectar(tmp_path / "cartoes.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def gravar(conexao, agente: str, etapa: str = "etapa", status: str = execucoes.OK,
           modelo: str | None = MODELO_REAL_DE_TESTE, minutos_depois: int = 0, segundos: float = 1.0,
           processamento_id: str = "proc-teste") -> None:
    """Grava uma execução de teste do envio informado: começa `minutos_depois` da PARTIDA e dura `segundos`."""
    inicio = PARTIDA + timedelta(minutes=minutos_depois)
    fim = inicio + timedelta(seconds=segundos)
    execucoes.registrar(conexao, processamento_id, "EMP001", etapa, agente, inicio, fim, status, modelo=modelo)


def cartao_do(conexao, agente: str) -> dict:
    """O cartão de um agente (pelo identificador), como a rota devolve."""
    cartoes = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)["cartoes_por_agente"]
    for cartao in cartoes:
        if cartao["agente"] == agente:
            return cartao
    raise AssertionError(f"Sem cartão para {agente}")


def test_um_cartao_por_agente_na_ordem_do_fluxo_mesmo_sem_execucao(conexao):
    cartoes = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)["cartoes_por_agente"]
    # A ordem do fluxo: do arquivo da empresa até o Endomarketing do banco (o Consultor saiu, ADR-144); por último, o
    # Bedrock Guardrails, que confere as mensagens de todas as etapas (ADR-147)
    identificadores = []
    for cartao in cartoes:
        identificadores.append(cartao["agente"])
    assert identificadores == ["leitor_de_documentos", "conferidor_da_leitura", "interpretador",
                               "assistente_de_correcao", "validacao_perguntas", "endomarketing", "guardrail_bedrock"]
    for cartao in cartoes:
        # Todo cartão tem as chaves do contrato e uma frase sobre o que o agente faz
        assert set(cartao) == CHAVES_DO_CARTAO
        assert cartao["nome_na_tela"] and cartao["o_que_faz"].endswith(".")
        # Nunca trabalhou: contagens em zero, e nada inventado para duração, última execução e custo
        assert cartao["execucoes"] == cartao["deram_certo"] == cartao["com_erro"] == 0
        assert cartao["barradas_pelo_guardrail"] == cartao["com_ia_real"] == cartao["simuladas"] == 0
        assert cartao["duracao_media_s"] is None and cartao["ultima_execucao"] is None and cartao["custo_usd"] is None


def test_todos_os_agentes_registram_o_trabalho(conexao):
    cartoes = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)["cartoes_por_agente"]
    # O Leitor e o Conferidor também gravam em execucoes_agentes:
    # todos os cartões podem dizer "Ainda não trabalhou" sem mentir (a tela continua sabendo mostrar o caso False)
    for cartao in cartoes:
        assert cartao["registra_o_trabalho"] is True


def test_regra_e_humano_nao_viram_cartao(conexao):
    gravar(conexao, "Regra", "perfilar")
    gravar(conexao, "Humano", "aprovar_mapeamento", modelo=None)
    gravar(conexao, "Validador", "validar", modelo=None)
    cartoes = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)["cartoes_por_agente"]
    # Nenhum cartão contou essas execuções (não são IA)
    for cartao in cartoes:
        assert cartao["execucoes"] == 0
    # As intervenções humanas continuam na visão geral
    assert portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)["visao"]["intervencoes_humanas"] == 1


def test_os_dois_nomes_gravados_do_leitor_se_juntam(conexao):
    # O mesmo agente gravado com e sem a maiúscula: um cartão só, com as duas leituras
    gravar(conexao, "Leitor de Documentos", "ler_texto_corrido", minutos_depois=1)
    gravar(conexao, "Leitor de documentos", "ler_texto_corrido", minutos_depois=2)
    leitor = cartao_do(conexao, "leitor_de_documentos")
    assert leitor["execucoes"] == 2 and leitor["deram_certo"] == 2
    # A última execução é a leitura mais recente
    assert leitor["ultima_execucao"].startswith("2026-09-28T10:02:00")


def test_execucoes_antigas_do_consultor_ficam_no_total_sem_cartao(conexao):
    # O Consultor saiu do sistema (ADR-144), mas as execuções dele continuam gravadas: gasto não se apaga
    gravar(conexao, "Consultor (agente único)", "pergunta:RESPONDIDO", minutos_depois=1)
    gravar(conexao, "Consultor (agente único)", "contar_por_uf", minutos_depois=1)
    gravar(conexao, "Consultor (supervisor)", "pergunta:RESPONDIDO", minutos_depois=2)
    gravar(conexao, "Subagente Planejamento", "contar_por_uf", minutos_depois=2)
    telemetria = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)
    # Nenhum cartão é do Consultor, e nenhum cartão contou as execuções dele
    for cartao in telemetria["cartoes_por_agente"]:
        assert cartao["agente"] != "consultor"
        assert cartao["execucoes"] == 0
    # A visão geral continua somando as quatro execuções antigas
    assert telemetria["visao"]["execucoes"] == 4
    # E a tabela de custo continua mostrando o agente antigo (com o custo "não medido": o provedor não mediu)
    agentes_da_tabela_de_custo = []
    for linha in telemetria["custo_por_etapa"]:
        agentes_da_tabela_de_custo.append(linha["agente"])
    assert "Consultor (agente único)" in agentes_da_tabela_de_custo


def test_erro_bloqueado_e_guardrail(conexao):
    gravar(conexao, "Assistente de Correção", "conversa:explicar", execucoes.OK)
    gravar(conexao, "Assistente de Correção", "conversa:falha", execucoes.ERRO)
    gravar(conexao, "Assistente de Correção", "conversa:recusado", execucoes.BLOQUEADO)
    gravar(conexao, "Assistente de Correção", "conversa:recusado", execucoes.BLOQUEADO)
    assistente = cartao_do(conexao, "assistente_de_correcao")
    assert assistente["execucoes"] == 4
    assert assistente["deram_certo"] == 1 and assistente["com_erro"] == 1
    assert assistente["barradas_pelo_guardrail"] == 2


def test_so_as_execucoes_com_o_modelo_real_entram_na_tela(conexao):
    gravar(conexao, "Interpretador", "interpretar", modelo=MODELO_SIMULADO, segundos=1.0)
    gravar(conexao, "Interpretador", "interpretar", modelo=MODELO_REAL_DE_TESTE, segundos=3.0)
    gravar(conexao, "Interpretador", "interpretar", modelo=MODELO_REAL_DE_TESTE, segundos=2.0)
    # Um agente que só rodou na simulação fica sem execução nenhuma na tela
    gravar(conexao, "Endomarketing", "gerar_material:GERADO", modelo=MODELO_SIMULADO)
    telemetria = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)
    cartoes = {}
    for cartao in telemetria["cartoes_por_agente"]:
        cartoes[cartao["agente"]] = cartao
    # O cartão conta só as duas reais: a simulada não entra em nenhum número
    assert cartoes["interpretador"]["execucoes"] == 2
    assert cartoes["interpretador"]["com_ia_real"] == 2 and cartoes["interpretador"]["simuladas"] == 0
    # A duração média das reais: (3 + 2) / 2 = 2,5 segundos
    assert cartoes["interpretador"]["duracao_media_s"] == 2.5
    assert cartoes["endomarketing"]["execucoes"] == 0 and cartoes["endomarketing"]["ultima_execucao"] is None
    # A visão geral, a tabela de custo e as execuções recentes também ficam só com as reais
    assert telemetria["visao"]["execucoes"] == 2 and len(telemetria["recentes"]) == 2
    for linha in telemetria["recentes"]:
        assert linha["origem"] == "REAL"
    for linha in telemetria["custo_por_etapa"]:
        assert linha["agente"] == "Interpretador" and linha["execucoes"] == 2
    # A função que monta os cartões continua sabendo contar as duas origens (quem escolhe o que entra é a tela)
    todas = painel.cartoes_por_agente(execucoes.listar(conexao))
    assert todas[2]["com_ia_real"] == 2 and todas[2]["simuladas"] == 1


def test_so_execucoes_reais_guarda_as_etapas_sem_modelo():
    # A Regra e o Humano (sem modelo) aconteceram de verdade: ficam; só a simulada sai
    lista = [{"agente": "Regra", "origem": "REAL"}, {"agente": "Interpretador", "origem": "MOCK"},
             {"agente": "Humano", "origem": "REAL"}, {"agente": "Interpretador", "origem": "REAL"}]
    reais = painel.so_execucoes_reais(lista)
    assert reais == [lista[0], lista[2], lista[3]]
    assert painel.so_execucoes_reais([]) == []


def test_custo_so_quando_medido(conexao):
    gravar(conexao, "Endomarketing", "gerar_material:GERADO")
    gravar(conexao, "Endomarketing", "gerar_material:GERADO")
    # Nada medido ainda: custo vazio, nunca zero
    assert cartao_do(conexao, "endomarketing")["custo_usd"] is None
    # O provedor mediu uma das duas: soma só a medida
    conexao.execute("UPDATE execucoes_agentes SET custo_usd = 0.0125 WHERE id = (SELECT MIN(id) FROM execucoes_agentes)")
    conexao.commit()
    assert cartao_do(conexao, "endomarketing")["custo_usd"] == 0.0125


def test_agente_de_validacao_e_cartoes_sem_dado_de_pessoa(conexao):
    gravar(conexao, "Agente de validação (perguntas)", "escrever_perguntas", execucoes.ERRO)
    validacao = cartao_do(conexao, "validacao_perguntas")
    assert validacao["execucoes"] == 1 and validacao["com_erro"] == 1
    # O cartão traz só contagens, tempos e custo: nada de empresa, CPF ou nome de pessoa
    assert "empresa_id" not in validacao and "processamento_id" not in validacao
    for cartao in painel.cartoes_por_agente([]):
        assert set(cartao) == CHAVES_DO_CARTAO


@pytest.fixture
def api_do_banco(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um especialista, um RH e uma execução do Interpretador."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_cartoes.db"
    # Toda conexão da API vai para o banco deste teste
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    gravar(conexao_do_teste, "Interpretador", "interpretar")
    conexao_do_teste.close()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_rota_devolve_os_cartoes_so_para_o_banco(api_do_banco):
    rota = "/api/banco/telemetria/ia"
    resposta = entrar("especialista").get(rota)
    assert resposta.status_code == 200
    corpo = resposta.json()
    # As chaves de antes continuam, e os cartões chegam junto
    assert {"visao", "por_agente", "recentes", "cartoes_por_agente"} <= set(corpo)
    assert len(corpo["cartoes_por_agente"]) == len(painel.AGENTES_DE_IA)
    assert corpo["cartoes_por_agente"][2]["agente"] == "interpretador"
    assert corpo["cartoes_por_agente"][2]["execucoes"] == 1 and corpo["cartoes_por_agente"][2]["com_ia_real"] == 1
    # Sem login: 401; a empresa: 403
    assert TestClient(aplicacao).get(rota).status_code == 401
    assert entrar("rh.aurora").get(rota).status_code == 403


# ---------------- Filtro por período ----------------

def test_periodo_filtra_cartoes_numeros_e_execucoes_recentes(conexao):
    # Uma execução no dia 28/09 (a PARTIDA) e duas no dia 26/09 (2 dias antes)
    gravar(conexao, "Interpretador", "interpretar", minutos_depois=0)
    gravar(conexao, "Interpretador", "interpretar", minutos_depois=-2 * 24 * 60)
    gravar(conexao, "Endomarketing", "gerar_material:GERADO", minutos_depois=-2 * 24 * 60)
    # Só o dia 28: uma execução, só do Interpretador
    so_o_dia_28 = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA, "2026-09-28", "2026-09-28")
    assert so_o_dia_28["periodo"] == {"de": "2026-09-28", "ate": "2026-09-28"}
    assert so_o_dia_28["visao"]["execucoes"] == 1 and len(so_o_dia_28["recentes"]) == 1
    cartoes = {}
    for cartao in so_o_dia_28["cartoes_por_agente"]:
        cartoes[cartao["agente"]] = cartao
    assert cartoes["interpretador"]["execucoes"] == 1 and cartoes["endomarketing"]["execucoes"] == 0
    # Sem as datas: tudo (as três execuções)
    tudo = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA)
    assert tudo["periodo"] == {"de": None, "ate": None}
    assert tudo["visao"]["execucoes"] == 3 and len(tudo["recentes"]) == 3
    # Só o começo: do dia 27 em diante (uma execução)
    assert portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA, "2026-09-27", "")["visao"]["execucoes"] == 1


def test_periodo_invalido_e_recusado(conexao):
    # Data fora do formato AAAA-MM-DD
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA, "28/09/2026", "")
    # O começo depois do fim
    with pytest.raises(ValueError, match="depois do fim"):
        painel.periodo_do_endereco("2026-09-30", "2026-09-01")


# ---------------- Aceitação por agente: como gravar as propostas de teste ----------------

def gravar_mapeamento_aceito(conexao, processamento_id: str, itens: list, criado_em: str = DENTRO_DO_PERIODO,
                             status: str = "APROVADO", modelo: str = MODELO_REAL_DE_TESTE) -> None:
    """Grava direto na tabela um mapeamento com as colunas informadas (APROVADO = a empresa já aceitou), proposto pelo
    modelo informado ("mock" = a simulação)."""
    mapeamentos._preparar(conexao)
    plano = MappingPlan(processamento_id=processamento_id, versao_layout=1, configuracao="B3", modelo=modelo,
                        versao_prompt="teste", itens=itens, chamou_llm=True)
    conexao.execute("INSERT INTO mapeamentos (processamento_id, empresa_id, status, plano, criado_em, aprovado_por, "
                    "aprovado_em) VALUES (?, 'EMP001', ?, ?, ?, NULL, NULL)",
                    (processamento_id, status, plano.model_dump_json(), criado_em))
    conexao.commit()


def coluna(nome: str, campo: str | None, origem: str, justificativa: str = "Nome equivalente.") -> ItemMapeamento:
    """Uma coluna de mapeamento aceito: com campo = ligada a ele; sem campo = ignorada."""
    status = StatusMapeamento.PROPOSTO if campo else StatusMapeamento.NAO_MAPEADO
    return ItemMapeamento(coluna=nome, campo=campo, status=status, justificativa=justificativa, origem=origem)


def gravar_correcao(conexao, processamento_id: str, linha: int, campo: str, status: str, proposta_por: str,
                    criado_em: str = DENTRO_DO_PERIODO) -> None:
    """Grava direto na tabela uma correção (sem valores de pessoa: antes e depois vazios)."""
    correcoes._preparar(conexao)
    identificador = f"{processamento_id}-{linha}-{campo}-{criado_em}-{status}"
    conexao.execute("INSERT INTO correcoes VALUES (?, ?, ?, ?, NULL, NULL, 'teste', ?, ?, ?, NULL, NULL)",
                    (identificador, processamento_id, linha, campo, status, proposta_por, criado_em))
    conexao.commit()


def gravar_envio_com_perguntas(conexao, processamento_id: str, perguntas: list[dict],
                               criado_em: str = DENTRO_DO_PERIODO) -> None:
    """Grava direto na tabela um envio cujo perfil só tem as perguntas da IA (o resto não importa aqui)."""
    processamentos._preparar(conexao)
    perfil = json.dumps({"perguntas_da_ia": perguntas}, ensure_ascii=False)
    conexao.execute("INSERT INTO processamentos VALUES (?, 'EMP001', 'lista.docx', 'hash', 'caminho', 'CARGA_INICIAL', "
                    "'2026-09-01', 'VALIDACAO_PENDENTE', ?, ?, 'rh')", (processamento_id, perfil, criado_em))
    conexao.commit()


def gravar_material(conexao, material_id: str, status: str, criado_em: str = DENTRO_DO_PERIODO,
                    modelo: str = MODELO_REAL_DE_TESTE) -> None:
    """Grava direto na tabela um material do Endomarketing na situação informada, escrito pelo modelo informado."""
    endomarketing._preparar(conexao)
    conexao.execute("INSERT INTO materiais_endomarketing (material_id, empresa_id, tipo, conteudo, status, modelo, "
                    "versao_prompt, criado_em, criado_por) VALUES (?, 'EMP001', 'comunicado', '{}', ?, ?, 'v', ?, "
                    "'especialista')", (material_id, status, modelo, criado_em))
    conexao.commit()


def aceitacao_do(conexao, agente: str) -> dict | None:
    """A aceitação de um agente no cartão (setembro de 2026), como a rota devolve."""
    de, ate = SETEMBRO
    cartoes = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA, de.isoformat(), ate.isoformat())
    for cartao in cartoes["cartoes_por_agente"]:
        if cartao["agente"] == agente:
            return cartao["aceitacao"]
    raise AssertionError(f"Sem cartão para {agente}")


def pergunta_do_conferidor(linha: int, campo: str) -> dict:
    """Uma pergunta como o Conferidor deixa no perfil do envio (o texto sai da função dele)."""
    suspeita = conferidor_da_leitura.Suspeita(pessoa=1, campo=campo, motivo="O valor parece de outra pessoa.")
    return {"linha": linha, "campo": campo, "pergunta": conferidor_da_leitura.pergunta_da_suspeita(suspeita)}


# ---------------- Aceitação por agente: com dado ----------------

def test_aceitacao_do_interpretador_e_do_leitor_pelas_colunas_aceitas(conexao):
    # A coluna do Leitor, gerada pela própria função de services/mapeamentos.py (o texto da justificativa é o dela)
    do_leitor = mapeamentos._item_lido_do_documento("Documento", {"campo": "cpf", "rotulo": "Documento",
                                                                  "pessoas": 3}, 3)
    parte_dividida_pela_pessoa = 'Parte "Rua" de "Endereço", separada por você (3 de 3 linhas).'
    itens = [
        # Interpretador: mantida, relida a pedido (handoff) e mantida, trocada de campo, ignorada
        coluna("CPF", "cpf", "llm"),
        coluna("Salário", "valor_renda", "handoff"),
        coluna("Nome", "nome", "humano"),
        coluna("Obs", None, "humano"),
        # Reaproveitadas de um mapeamento aprovado (mantida ou mudada): sem proposta de IA, ficam de fora
        coluna("Cargo", "cargo", "reuso", aceitacao_dos_agentes.JUSTIFICATIVA_DO_REUSO),
        coluna("Setor", "setor", "humano", aceitacao_dos_agentes.JUSTIFICATIVA_DO_REUSO),
        # Leitor: mantido e trocado de campo
        do_leitor,
        coluna("Admissão", "data_admissao", "humano", do_leitor.justificativa),
        # Uma parte de coluna que a própria pessoa dividiu: fica de fora
        coluna("Endereço" + divisao_da_coluna.SINAL_DA_PARTE + "Rua", "logradouro", "humano",
               parte_dividida_pela_pessoa),
    ]
    gravar_mapeamento_aceito(conexao, "proc-1", itens)
    # O Leitor leu o Word deste envio com o modelo real (sem essa execução, as colunas dele seriam da simulação)
    gravar(conexao, "Leitor de documentos", "ler_texto_corrido", processamento_id="proc-1")
    # Fora da conta: um mapeamento ainda pendente e um aceito fora do período
    gravar_mapeamento_aceito(conexao, "proc-2", [coluna("X", "cpf", "llm")], status="PENDENTE")
    gravar_mapeamento_aceito(conexao, "proc-3", [coluna("Y", "cpf", "llm")], criado_em=FORA_DO_PERIODO)
    do_interpretador = aceitacao_do(conexao, "interpretador")
    assert set(do_interpretador) == CHAVES_DA_ACEITACAO
    assert (do_interpretador["aprovadas"], do_interpretador["corrigidas"], do_interpretador["recusadas"]) == (2, 1, 1)
    # 2 das 4 decididas ficaram como a IA propôs
    assert do_interpretador["percentual_aprovadas"] == 50.0
    assert do_interpretador["fonte"].startswith("Colunas dos mapeamentos aceitos")
    do_leitor_na_tela = aceitacao_do(conexao, "leitor_de_documentos")
    assert (do_leitor_na_tela["aprovadas"], do_leitor_na_tela["corrigidas"], do_leitor_na_tela["recusadas"]) == (1, 1, 0)
    # Sem o período (tudo), o mapeamento de agosto também conta
    assert aceitacao_dos_agentes.aceitacao_por_agente(conexao)["interpretador"]["aceitacao"]["aprovadas"] == 3


def test_textos_que_reconhecem_a_proposta_continuam_iguais_aos_das_outras_partes():
    # Se um destes textos mudar lá, a aceitação passaria a contar a coluna para o agente errado
    assert aceitacao_dos_agentes.JUSTIFICATIVA_DO_REUSO in inspect.getsource(mapeamentos)
    assert '"por você"' in inspect.getsource(divisao_da_coluna)
    assert aceitacao_dos_agentes.COMECO_DA_JUSTIFICATIVA_DE_EMERGENCIA in inspect.getsource(interpretador)
    assert pergunta_do_conferidor(5, "cpf")["pergunta"].startswith(aceitacao_dos_agentes.COMECO_DA_PERGUNTA_DO_CONFERIDOR)


def test_mapeamentos_gravados_antes_da_troca_de_ia_pelo_nome_do_agente_continuam_contando(conexao):
    # A justificativa de hoje, gerada pela própria função de services/mapeamentos.py, já fala do Agente Leitor
    do_leitor_hoje = mapeamentos._item_lido_do_documento("Documento", {"campo": "cpf", "rotulo": "Documento",
                                                                       "pessoas": 3}, 3)
    assert do_leitor_hoje.justificativa.startswith("O Agente Leitor leu este dado no seu documento")
    # Todas trocadas pela pessoa (origem "humano"): é a justificativa que diz de quem era a proposta
    itens = [
        # Leitor: a de hoje e a de antes de 30/09 ("A IA leu..."), trocadas de campo; a de antes sem rótulo, ignorada
        coluna("Documento", "rg", "humano", do_leitor_hoje.justificativa),
        coluna("Registro", "rg", "humano", "A IA leu este dado no seu documento (3 de 3 pessoas)."),
        coluna("Obs", None, "humano", "A IA achou este dado pelo lugar no texto, sem um rótulo (3 de 3 pessoas)."),
        # O plano de emergência, o de hoje e o de antes: não é proposta de agente, fica fora da conta
        coluna("Cargo", "cargo", "humano", "Agente Interpretador indisponível: sugestão do dicionário, confirme."),
        coluna("Setor", "setor", "humano", "IA indisponível: sugestão do dicionário, confirme."),
        # Uma proposta comum do Interpretador, trocada de campo
        coluna("Nome", "nome_completo", "humano"),
    ]
    gravar_mapeamento_aceito(conexao, "proc-1", itens)
    # O Leitor leu o Word deste envio com o modelo real
    gravar(conexao, "Leitor de documentos", "ler_texto_corrido", processamento_id="proc-1")
    do_leitor = aceitacao_do(conexao, "leitor_de_documentos")
    assert (do_leitor["aprovadas"], do_leitor["corrigidas"], do_leitor["recusadas"]) == (0, 2, 1)
    do_interpretador = aceitacao_do(conexao, "interpretador")
    assert (do_interpretador["aprovadas"], do_interpretador["corrigidas"], do_interpretador["recusadas"]) == (0, 1, 0)


def test_aceitacao_do_assistente_pelas_correcoes_que_ele_fez(conexao):
    assistente = "assistente (para rh.aurora)"
    # A rodada da conversa com o modelo real, um minuto antes da primeira correção (20/09, 09h59)
    gravar(conexao, "Assistente de Correção", "conversa:corrigir", processamento_id="proc-1",
           minutos_depois=MINUTOS_ATE_O_DIA_DAS_PROPOSTAS - 1)
    # Aplicada e ninguém mexeu depois: aprovada
    gravar_correcao(conexao, "proc-1", 5, "cpf", "APLICADA", assistente, "2026-09-20T10:00:00+00:00")
    # Aplicada, e a empresa trocou a mesma célula depois: corrigida
    gravar_correcao(conexao, "proc-1", 6, "cargo", "APLICADA", assistente, "2026-09-20T10:01:00+00:00")
    gravar_correcao(conexao, "proc-1", 6, "cargo", "APLICADA", "rh.aurora", "2026-09-20T10:05:00+00:00")
    # Desfeita e cancelada: recusadas
    gravar_correcao(conexao, "proc-1", 7, "nome", correcoes.DESFEITA, assistente, "2026-09-20T10:02:00+00:00")
    gravar_correcao(conexao, "proc-1", 8, correcoes.EXCLUIR, "CANCELADA", assistente, "2026-09-20T10:03:00+00:00")
    # Fora da conta: esperando a confirmação, feita pela própria empresa, e fora do período
    gravar_correcao(conexao, "proc-1", 9, correcoes.EXCLUIR, "PROPOSTA", assistente, "2026-09-20T10:04:00+00:00")
    gravar_correcao(conexao, "proc-1", 10, "cpf", "APLICADA", "rh.aurora", "2026-09-20T10:06:00+00:00")
    gravar_correcao(conexao, "proc-1", 11, "cpf", "APLICADA", assistente, FORA_DO_PERIODO)
    do_assistente = aceitacao_do(conexao, "assistente_de_correcao")
    assert (do_assistente["aprovadas"], do_assistente["corrigidas"], do_assistente["recusadas"]) == (1, 1, 2)
    assert do_assistente["percentual_aprovadas"] == 25.0


def test_aceitacao_do_conferidor_pelas_respostas_da_empresa(conexao):
    perguntas = [pergunta_do_conferidor(5, "cpf"), pergunta_do_conferidor(6, "data_admissao"),
                 pergunta_do_conferidor(7, "valor_renda"),
                 # Uma pergunta do próprio Leitor (não é do Conferidor): não conta
                 {"linha": 8, "campo": "cpf", "pergunta": "Qual é o CPF desta pessoa?"}]
    gravar_envio_com_perguntas(conexao, "proc-word", perguntas)
    # O Conferidor conferiu este envio com o modelo real
    gravar(conexao, "Conferidor da leitura", "conferir_leitura", processamento_id="proc-word")
    # A empresa corrigiu o CPF da linha 5 (a suspeita valeu) e o da linha 8 (a pergunta do Leitor)
    gravar_correcao(conexao, "proc-word", 5, "cpf", "APLICADA", "rh.aurora")
    gravar_correcao(conexao, "proc-word", 8, "cpf", "APLICADA", "rh.aurora")
    # E confirmou que a data da linha 6 estava certa (alarme falso); a renda da linha 7 ainda não foi respondida
    validador.registrar_resolucao(conexao, "proc-word", validador.PREFIXO_DA_PERGUNTA_DA_IA + "data_admissao", 6,
                                  "CONFIRMADO", "Está certo assim.", "rh.aurora")
    do_conferidor = aceitacao_do(conexao, "conferidor_da_leitura")
    # "corrigidas" não se aplica ao Conferidor (a suspeita não traz um valor): None, nunca zero
    assert (do_conferidor["aprovadas"], do_conferidor["corrigidas"], do_conferidor["recusadas"]) == (1, None, 1)
    assert do_conferidor["percentual_aprovadas"] == 50.0


def test_aceitacao_do_endomarketing_pelos_materiais(conexao):
    gravar_material(conexao, "m1", endomarketing.PUBLICADO)
    gravar_material(conexao, "m2", endomarketing.PUBLICADO)
    gravar_material(conexao, "m3", endomarketing.APROVADO)
    gravar_material(conexao, "m4", endomarketing.DESCARTADO)
    gravar_material(conexao, "m5", endomarketing.RETIRADO)
    # Fora da conta: rascunho (sem decisão) e um publicado fora do período
    gravar_material(conexao, "m6", endomarketing.RASCUNHO)
    gravar_material(conexao, "m7", endomarketing.PUBLICADO, FORA_DO_PERIODO)
    do_endomarketing = aceitacao_do(conexao, "endomarketing")
    assert (do_endomarketing["aprovadas"], do_endomarketing["corrigidas"], do_endomarketing["recusadas"]) == (3, None, 2)
    assert do_endomarketing["percentual_aprovadas"] == 60.0


def test_aceitacao_conta_so_as_propostas_do_modelo_real(conexao):
    assistente = "assistente (para rh.aurora)"
    # Interpretador: o plano da simulação não conta; o do modelo real conta
    gravar_mapeamento_aceito(conexao, "proc-simulado", [coluna("CPF", "cpf", "llm"), coluna("Nome", "nome", "humano")],
                             modelo=MODELO_SIMULADO)
    gravar_mapeamento_aceito(conexao, "proc-real", [coluna("CPF", "cpf", "llm")])
    # Leitor: a coluna lida num envio em que só a simulação leu o Word não conta
    do_leitor = mapeamentos._item_lido_do_documento("Documento", {"campo": "cpf", "rotulo": "Documento",
                                                                  "pessoas": 3}, 3)
    gravar_mapeamento_aceito(conexao, "proc-word-simulado", [do_leitor])
    gravar(conexao, "Leitor de documentos", "ler_texto_corrido", modelo=MODELO_SIMULADO,
           processamento_id="proc-word-simulado")
    # Conferidor: a suspeita de um envio conferido pela simulação não conta, mesmo com a empresa corrigindo o valor
    gravar_envio_com_perguntas(conexao, "proc-conferido-simulado", [pergunta_do_conferidor(5, "cpf")])
    gravar_correcao(conexao, "proc-conferido-simulado", 5, "cpf", "APLICADA", "rh.aurora")
    gravar(conexao, "Conferidor da leitura", "conferir_leitura", modelo=MODELO_SIMULADO,
           processamento_id="proc-conferido-simulado")
    # Assistente: a correção da rodada simulada (20/09, 10h) não conta; a da rodada real (10h30, no mesmo envio) conta
    gravar(conexao, "Assistente de Correção", "conversa:corrigir", modelo=MODELO_SIMULADO,
           processamento_id="proc-conversa", minutos_depois=MINUTOS_ATE_O_DIA_DAS_PROPOSTAS)
    gravar_correcao(conexao, "proc-conversa", 5, "cpf", "APLICADA", assistente, "2026-09-20T10:00:05+00:00")
    gravar(conexao, "Assistente de Correção", "conversa:corrigir", processamento_id="proc-conversa",
           minutos_depois=MINUTOS_ATE_O_DIA_DAS_PROPOSTAS + 30)
    gravar_correcao(conexao, "proc-conversa", 6, "cargo", "APLICADA", assistente, "2026-09-20T10:30:07+00:00")
    # A correção sem nenhuma rodada gravada antes (não dá para dizer que foi o modelo real): não conta
    gravar_correcao(conexao, "proc-sem-rodada", 7, "nome", "APLICADA", assistente, "2026-09-20T11:00:00+00:00")
    # Endomarketing: o material escrito pela simulação não conta
    gravar_material(conexao, "m-simulado", endomarketing.PUBLICADO, modelo=MODELO_SIMULADO)
    gravar_material(conexao, "m-real", endomarketing.DESCARTADO)
    do_interpretador = aceitacao_do(conexao, "interpretador")
    assert (do_interpretador["aprovadas"], do_interpretador["corrigidas"], do_interpretador["recusadas"]) == (1, 0, 0)
    assert aceitacao_do(conexao, "leitor_de_documentos") is None
    assert aceitacao_do(conexao, "conferidor_da_leitura") is None
    do_assistente = aceitacao_do(conexao, "assistente_de_correcao")
    assert (do_assistente["aprovadas"], do_assistente["corrigidas"], do_assistente["recusadas"]) == (1, 0, 0)
    do_endomarketing = aceitacao_do(conexao, "endomarketing")
    assert (do_endomarketing["aprovadas"], do_endomarketing["recusadas"]) == (0, 1)


def test_mapeamento_carregado_sem_agente_nao_conta(conexao):
    # Uma carga de dados sintéticos liga as colunas sem IA (origem "regra" ou "reuso"): não é proposta de agente
    itens = [coluna("CPF", "cpf", "regra", "Coluna ligada ao campo pela carga (dados sintéticos, sem IA)."),
             coluna("Nome", "nome", "reuso", aceitacao_dos_agentes.JUSTIFICATIVA_DO_REUSO)]
    gravar_mapeamento_aceito(conexao, "proc-da-carga", itens, modelo="carga (sem IA)")
    assert aceitacao_do(conexao, "interpretador") is None


# ---------------- Aceitação por agente: sem dado ----------------

def test_aceitacao_sem_dado_e_nao_medido_nunca_zero(conexao):
    de, ate = SETEMBRO
    cartoes = portal_do_banco.telemetria_da_ia(conexao, ESPECIALISTA, de.isoformat(), ate.isoformat())
    motivos = {}
    for cartao in cartoes["cartoes_por_agente"]:
        # Banco vazio: nenhum agente tem aceitação, e cada um diz por quê
        assert cartao["aceitacao"] is None
        motivos[cartao["agente"]] = cartao["aceitacao_sem_medida_porque"]
    # O Agente de validação não tem fonte: o porquê é dele
    assert motivos["validacao_perguntas"] == aceitacao_dos_agentes.SEM_MEDIDA_NA_VALIDACAO
    # O Bedrock Guardrails também não: ele só dá uma nota a cada mensagem (ADR-147)
    assert motivos["guardrail_bedrock"] == aceitacao_dos_agentes.SEM_MEDIDA_NO_GUARDRAIL
    # Os outros têm fonte, mas nada foi decidido no período
    for agente in ("leitor_de_documentos", "conferidor_da_leitura", "interpretador", "assistente_de_correcao",
                   "endomarketing"):
        assert motivos[agente] == aceitacao_dos_agentes.SEM_DECISAO_NO_PERIODO


def test_rota_com_periodo_e_data_invalida(api_do_banco):
    navegador = entrar("especialista")
    # A execução de teste é de 28/09/2026: entra no dia e fica fora de um período antigo
    no_dia = navegador.get("/api/banco/telemetria/ia?de=2026-09-28&ate=2026-09-28").json()
    assert no_dia["periodo"] == {"de": "2026-09-28", "ate": "2026-09-28"}
    assert no_dia["cartoes_por_agente"][2]["execucoes"] == 1
    assert "aceitacao" in no_dia["cartoes_por_agente"][2]
    antigo = navegador.get("/api/banco/telemetria/ia?de=2026-01-01&ate=2026-01-31").json()
    assert antigo["cartoes_por_agente"][2]["execucoes"] == 0 and antigo["recentes"] == []
    # Data que não é data: 400, com a mensagem
    resposta = navegador.get("/api/banco/telemetria/ia?de=ontem")
    assert resposta.status_code == 400 and "AAAA-MM-DD" in resposta.json()["detail"]


def test_o_periodo_usa_o_calendario_de_brasilia():
    """Os horários são gravados em horário universal: às 21h50 de 28/09 em Brasília já é 29/09 em UTC. O filtro "até
    28/09" precisa incluir esse trabalho (o dia é o do calendário da especialista, em Brasília)."""
    from datetime import date

    from services import painel
    assert painel.dia_em_brasilia("2026-09-29T00:50:00+00:00") == date(2026, 9, 28)
    assert painel.dia_em_brasilia("2026-09-29T03:10:00+00:00") == date(2026, 9, 29)
    assert painel.dentro_do_periodo("2026-09-29T00:50:00+00:00", date(2026, 9, 1), date(2026, 9, 28)) is True
    assert painel.dentro_do_periodo("2026-09-29T03:10:00+00:00", date(2026, 9, 1), date(2026, 9, 28)) is False
    assert painel.dentro_do_periodo(None, None, None) is False
