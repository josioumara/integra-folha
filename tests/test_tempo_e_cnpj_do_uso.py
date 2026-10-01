"""O tempo até a avaliação do banco e os CNPJs da busca no funil, no uso das empresas (Painel de acompanhamento).

O cartão "tempo até a avaliação do banco" deixa de ser "—" e passa a ter o número real; o funil do envio ganha a
busca da empresa pelo CNPJ.

O que estes testes provam:
- a regra do tempo: dias ÚTEIS (segunda a sexta, no horário de Brasília), com fração, entre o envio da empresa ao
  banco (evento ENVIADO_AO_BANCO da auditoria) e a decisão do banco (APROVADO_PELO_BANCO ou DEVOLVIDO_PELO_BANCO);
- só os envios já decididos entram; o que ainda espera o banco fica de fora; um envio devolvido e mandado de novo
  conta uma vez para cada decisão;
- o período do cartão é o mesmo dos outros números do uso ("desde o começo");
- sem nenhuma decisão do banco: sem número (None), nunca um zero inventado;
- cada empresa da carteira traz todos os CNPJs dela (principal, filial e grupo), só com os números, para a busca
  da tela achar a empresa com ou sem pontuação;
- a rota /api/banco/telemetria/uso devolve o JSON novo ao especialista (e continua fechada para a empresa e para
  quem não entrou).
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auditoria, auth, banco, portal_do_banco
from services import empresas as cadastro_de_empresas
from services.auth import Usuario
from tests.test_cnpjs_das_empresas import CNPJ_DA_AURORA, cnpj_de_outra_raiz, filial_da_aurora

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# O especialista do banco (o único que cadastra CNPJs de filiais e do grupo)
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)

# Momentos usados nos testes, no horário universal (a auditoria grava assim). Em Brasília são 3 horas a menos:
# "2026-09-21T13:00:00+00:00" é segunda-feira, 21/09/2026, às 10h em Brasília.
SEGUNDA_10H = "2026-09-21T13:00:00+00:00"
TERCA_10H = "2026-09-22T13:00:00+00:00"
QUARTA_10H = "2026-09-23T13:00:00+00:00"
SEXTA_10H = "2026-09-25T13:00:00+00:00"
PROXIMA_SEGUNDA_10H = "2026-09-28T13:00:00+00:00"


def evento(processamento_id: str, tipo: str, quando: str, empresa_id: str = "EMP001") -> dict:
    """Um evento da auditoria no formato de auditoria.eventos (só o que a regra do tempo usa)."""
    return {"processamento_id": processamento_id, "empresa_id": empresa_id, "etapa": "Teste", "tipo": tipo,
            "detalhe": {}, "criado_em": quando}


# ---------------- A regra dos dias úteis ----------------


def test_um_dia_de_semana_inteiro_e_um_dia_util():
    assert portal_do_banco.dias_uteis_entre(SEGUNDA_10H, TERCA_10H) == 1.0


def test_o_fim_de_semana_nao_conta():
    # Sexta às 10h até segunda às 10h: 14 horas da sexta + 10 horas da segunda = 1 dia útil
    assert portal_do_banco.dias_uteis_entre(SEXTA_10H, PROXIMA_SEGUNDA_10H) == 1.0


def test_poucas_horas_no_mesmo_dia_viram_fracao_de_dia():
    # Das 10h às 16h de uma segunda: 6 horas = 0,25 dia útil
    assert portal_do_banco.dias_uteis_entre(SEGUNDA_10H, "2026-09-21T19:00:00+00:00") == 0.25


def test_sabado_e_domingo_sao_os_do_horario_de_brasilia():
    # Sexta às 23h em Brasília (sábado 02h no horário universal) até segunda 0h em Brasília (03h universal):
    # só conta a última hora da sexta. Contado no horário universal, daria 3 horas (as da segunda).
    horas = portal_do_banco.dias_uteis_entre("2026-09-26T02:00:00+00:00", "2026-09-28T03:00:00+00:00") * 24
    assert round(horas, 6) == 1.0


# ---------------- Só os envios decididos, e a média ----------------


def test_media_so_dos_envios_decididos_com_uma_casa_decimal():
    eventos = [
        # Aprovado em 1 dia útil (outros eventos do envio não mudam a conta)
        evento("P1", "RECEBIDO", SEGUNDA_10H),
        evento("P1", "ENVIADO_AO_BANCO", SEGUNDA_10H),
        evento("P1", "HOMOLOGADO", TERCA_10H),
        evento("P1", "APROVADO_PELO_BANCO", TERCA_10H),
        # Devolvido em 1 dia útil (de sexta a segunda)
        evento("P2", "ENVIADO_AO_BANCO", SEXTA_10H, "EMP002"),
        evento("P2", "DEVOLVIDO_PELO_BANCO", PROXIMA_SEGUNDA_10H, "EMP002"),
        # Aprovado em 2 dias úteis
        evento("P3", "ENVIADO_AO_BANCO", SEGUNDA_10H, "EMP003"),
        evento("P3", "APROVADO_PELO_BANCO", QUARTA_10H, "EMP003"),
        # Ainda esperando o banco: fica de fora
        evento("P4", "ENVIADO_AO_BANCO", SEGUNDA_10H, "EMP004"),
    ]
    tempo = portal_do_banco.tempo_ate_a_avaliacao(eventos)
    # (1 + 1 + 2) / 3 = 1,333... → 1,3
    assert tempo == {"media_em_dias_uteis": 1.3, "avaliacoes": 3, "soma_em_dias_uteis": 4.0, "periodo": "desde o começo"}


def test_envio_devolvido_e_mandado_de_novo_conta_uma_vez_por_decisao():
    eventos = [
        # 1ª ida ao banco: devolvido em 1 dia útil
        evento("P1", "ENVIADO_AO_BANCO", SEGUNDA_10H),
        evento("P1", "DEVOLVIDO_PELO_BANCO", TERCA_10H),
        # 2ª ida (a empresa corrigiu e mandou de novo): aprovado em 1 dia útil, contado a partir do novo envio
        evento("P1", "ENVIADO_AO_BANCO", QUARTA_10H),
        evento("P1", "APROVADO_PELO_BANCO", "2026-09-24T13:00:00+00:00"),
    ]
    avaliacoes = portal_do_banco.avaliacoes_do_banco(eventos)
    assert [(avaliacao["enviado_em"], avaliacao["decidido_em"]) for avaliacao in avaliacoes] == [
        (SEGUNDA_10H, TERCA_10H), (QUARTA_10H, "2026-09-24T13:00:00+00:00")]
    assert portal_do_banco.tempo_ate_a_avaliacao(eventos)["media_em_dias_uteis"] == 1.0


def test_o_periodo_e_desde_o_comeco_como_os_outros_numeros_do_uso():
    # Uma decisão de agosto e uma de setembro: as duas entram (o cartão vale desde o começo, não só o mês)
    eventos = [
        evento("P1", "ENVIADO_AO_BANCO", "2026-08-03T13:00:00+00:00"),
        evento("P1", "APROVADO_PELO_BANCO", "2026-08-04T13:00:00+00:00"),
        evento("P2", "ENVIADO_AO_BANCO", SEGUNDA_10H),
        evento("P2", "APROVADO_PELO_BANCO", QUARTA_10H),
    ]
    tempo = portal_do_banco.tempo_ate_a_avaliacao(eventos)
    assert tempo["avaliacoes"] == 2 and tempo["media_em_dias_uteis"] == 1.5
    assert tempo["periodo"] == portal_do_banco.PERIODO_DO_USO == "desde o começo"


def test_sem_envio_decidido_nao_ha_numero():
    # Nenhum evento, ou só envios esperando o banco: sem média (a tela mostra "—"), nunca zero
    esperado = {"media_em_dias_uteis": None, "avaliacoes": 0, "soma_em_dias_uteis": 0.0, "periodo": "desde o começo"}
    assert portal_do_banco.tempo_ate_a_avaliacao([]) == esperado
    assert portal_do_banco.tempo_ate_a_avaliacao([evento("P1", "ENVIADO_AO_BANCO", SEGUNDA_10H)]) == esperado


# ---------------- O JSON do uso, com os dados gravados ----------------


@pytest.fixture(autouse=True)
def lista_de_empresas_limpa():
    """Cada teste começa (e termina) sem a lista de empresas guardada em memória."""
    cadastro_de_empresas.esquecer_lista_em_memoria()
    yield
    cadastro_de_empresas.esquecer_lista_em_memoria()


def gravar_evento(conexao, processamento_id: str, tipo: str, quando: str, empresa_id: str = "EMP001") -> None:
    """Grava um evento na auditoria com a data escolhida (o registrar de verdade sempre usa a hora de agora)."""
    # Garante que a tabela de eventos existe
    auditoria.eventos(conexao)
    conexao.execute("INSERT INTO eventos (processamento_id, empresa_id, etapa, tipo, detalhe, criado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (processamento_id, empresa_id, "Teste", tipo, "{}", quando))
    conexao.commit()


def gravar_duas_decisoes_do_banco(conexao) -> None:
    """A Aurora com um envio aprovado em 1 dia útil e outro devolvido em 2; a Horizonte com um esperando o banco."""
    gravar_evento(conexao, "P1", "ENVIADO_AO_BANCO", SEGUNDA_10H)
    gravar_evento(conexao, "P1", "APROVADO_PELO_BANCO", TERCA_10H)
    gravar_evento(conexao, "P2", "ENVIADO_AO_BANCO", SEGUNDA_10H)
    gravar_evento(conexao, "P2", "DEVOLVIDO_PELO_BANCO", QUARTA_10H)
    gravar_evento(conexao, "P3", "ENVIADO_AO_BANCO", SEGUNDA_10H, "EMP002")


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, só deste teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def test_uso_traz_o_tempo_ate_a_avaliacao_gravado_na_auditoria(conexao):
    # Sem nenhuma decisão do banco: sem número
    assert portal_do_banco.uso_das_empresas(conexao)["tempo_ate_a_avaliacao"]["media_em_dias_uteis"] is None
    # Com as duas decisões da Aurora: (1 + 2) / 2 = 1,5 dia útil
    gravar_duas_decisoes_do_banco(conexao)
    tempo = portal_do_banco.uso_das_empresas(conexao)["tempo_ate_a_avaliacao"]
    assert tempo == {"media_em_dias_uteis": 1.5, "avaliacoes": 2, "soma_em_dias_uteis": 3.0, "periodo": "desde o começo"}


def test_cada_empresa_traz_todos_os_cnpjs_so_com_os_numeros(conexao):
    # A Aurora com uma filial e uma empresa do grupo registradas pelo banco
    filial = filial_da_aurora()
    grupo = cnpj_de_outra_raiz(7)
    cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", filial, "FILIAL")
    cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", grupo, "GRUPO")
    uso = portal_do_banco.uso_das_empresas(conexao)
    por_id = {empresa["id"]: empresa for empresa in uso["empresas"]}
    # O principal primeiro, depois a filial e o grupo
    assert por_id["EMP001"]["cnpjs"] == [CNPJ_DA_AURORA, filial, grupo]
    # Toda empresa da carteira tem ao menos o principal; todos com 14 números, sem pontuação
    for empresa in uso["empresas"]:
        assert empresa["cnpjs"]
        for cnpj in empresa["cnpjs"]:
            assert len(cnpj) == 14 and cnpj.isdigit()
    # A outra empresa não leva os CNPJs da Aurora
    assert filial not in por_id["EMP002"]["cnpjs"] and grupo not in por_id["EMP002"]["cnpjs"]


def so_os_numeros(texto: str) -> str:
    """Tira pontos, barras, traços e espaços, como a busca da tela faz ("10.433.218/0001-93" → "10433218000193")."""
    numeros = ""
    for caractere in texto:
        if caractere.isdigit():
            numeros = numeros + caractere
    return numeros


def com_pontuacao(cnpj: str) -> str:
    """O CNPJ escrito como as pessoas escrevem: "10433218000193" → "10.433.218/0001-93"."""
    return cnpj[:2] + "." + cnpj[2:5] + "." + cnpj[5:8] + "/" + cnpj[8:12] + "-" + cnpj[12:]


def empresas_achadas(uso: dict, texto_digitado: str) -> list[str]:
    """As empresas que a busca da tela acharia: a comparação é só pelos números do CNPJ."""
    procurado = so_os_numeros(texto_digitado)
    achadas = []
    for empresa in uso["empresas"]:
        if procurado in empresa["cnpjs"]:
            achadas.append(empresa["id"])
    return achadas


def test_busca_por_cnpj_acha_a_empresa_pelo_principal_filial_ou_grupo_com_ou_sem_pontuacao(conexao):
    filial = filial_da_aurora()
    grupo = cnpj_de_outra_raiz(7)
    cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", filial, "FILIAL")
    cadastro_de_empresas.adicionar_cnpj(conexao, ESPECIALISTA, "EMP001", grupo, "GRUPO")
    uso = portal_do_banco.uso_das_empresas(conexao)
    # Principal, filial e grupo: acham a Aurora (e só ela), com e sem pontuação
    for cnpj in (CNPJ_DA_AURORA, filial, grupo):
        assert empresas_achadas(uso, cnpj) == ["EMP001"]
        assert empresas_achadas(uso, com_pontuacao(cnpj)) == ["EMP001"]
    # Um CNPJ que não é de nenhuma empresa da carteira: nada (a tela avisa)
    assert empresas_achadas(uso, cnpj_de_outra_raiz(99)) == []


# ---------------- A rota ----------------


@pytest.fixture
def api_do_uso(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com as duas decisões da Aurora, um especialista e um RH."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_uso.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    gravar_duas_decisoes_do_banco(conexao_do_teste)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_rota_do_uso_devolve_o_tempo_e_os_cnpjs_so_ao_banco(api_do_uso):
    resposta = entrar("especialista").get("/api/banco/telemetria/uso")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["tempo_ate_a_avaliacao"] == {"media_em_dias_uteis": 1.5, "avaliacoes": 2, "soma_em_dias_uteis": 3.0,
                                              "periodo": "desde o começo"}
    por_id = {empresa["id"]: empresa for empresa in dados["empresas"]}
    assert por_id["EMP001"]["cnpjs"][0] == CNPJ_DA_AURORA
    # A empresa não vê o uso da carteira; quem não entrou também não
    assert entrar("rh.aurora").get("/api/banco/telemetria/uso").status_code == 403
    assert TestClient(aplicacao).get("/api/banco/telemetria/uso").status_code == 401


def test_cada_empresa_traz_a_uf_da_sede_e_o_proprio_tempo_ate_a_avaliacao(conexao):
    """O filtro do alto do painel refaz os números no navegador: cada empresa traz a UF da sede e o tempo
    dela, com a soma dos dias para a média ponderada de várias empresas."""
    gravar_duas_decisoes_do_banco(conexao)
    uso = portal_do_banco.uso_das_empresas(conexao)
    por_empresa = {}
    for empresa in uso["empresas"]:
        por_empresa[empresa["id"]] = empresa
    # A UF da sede vem do cadastro da empresa
    for empresa in cadastro_de_empresas.lista_em_memoria():
        assert por_empresa[empresa["empresa_id"]]["uf"] == empresa["uf"]
    # A Aurora: 1 e 2 dias úteis → média 1,5, soma 3; a Horizonte ainda espera o banco: sem número
    assert por_empresa["EMP001"]["tempo_ate_a_avaliacao"] == {"media_em_dias_uteis": 1.5, "avaliacoes": 2,
                                                              "soma_em_dias_uteis": 3.0, "periodo": "desde o começo"}
    assert por_empresa["EMP002"]["tempo_ate_a_avaliacao"]["media_em_dias_uteis"] is None
    assert por_empresa["EMP002"]["tempo_ate_a_avaliacao"]["soma_em_dias_uteis"] == 0.0
