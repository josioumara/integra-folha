"""Testes das premissas financeiras oficiais, na engrenagem "Configuração" do Portal Interno: o especialista salva as
novas premissas oficiais, com registro de quem mudou.

O que fica provado:
- a versão 1 são os números do business case (MOB cliente folha R$ 2.090,62, não folha R$ 1.724,00, 12 meses);
- a tela grava uma versão oficial nova (v2, v3...), e a v1 continua guardada (as simulações antigas a reproduzem);
- o registro de cada versão diz quem gravou, quando e o que mudou (de → para);
- a conferência recusa zero, negativo, horizonte fora de 1 a 60 ou quebrado, mais de 2 casas e "nada mudou";
- as premissas oficiais são só o horizonte e os 3 MOB: as taxas (% novas contas, % correntistas não folha, %
  correção de folha) são estimativas do Simulador de Rentabilidade e nunca entram numa versão oficial;
- as rotas GET e POST /api/banco/premissas são só do BANCO (401 sem login, 403 para a empresa).

Cada teste usa um banco próprio (tmp_path): uma versão nova gravada aqui nunca muda as premissas dos outros testes.
"""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, config, parametros

# Senha dos usuários de teste deste arquivo (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"

# Os valores da versão 1 (business case), como a tela manda: texto com ponto nos centavos
VALORES_DA_V1 = {"horizonte_meses": "12", "mob_cliente_folha": "2090.62", "mob_cliente_nao_folha": "1724.00",
                 "mob_cliente_novo_conquistado": "2090.62"}


def valores_com(**trocas) -> dict:
    """Os valores da v1 com algumas premissas trocadas. Ex.: valores_com(mob_cliente_folha="2150.00")."""
    valores = dict(VALORES_DA_V1)
    valores.update(trocas)
    return valores


# ---------------- O serviço (services/parametros.py) ----------------

def test_a_versao_1_sao_os_numeros_do_business_case(tmp_path):
    conexao = auth.conectar(tmp_path / "premissas.db")
    tela = parametros.premissas_para_a_tela(conexao)
    assert tela["versao"] == 1
    assert tela["vigente"] == {"horizonte_meses": 12, "mob_cliente_folha": "2090.62",
                               "mob_cliente_nao_folha": "1724.00", "mob_cliente_novo_conquistado": "2090.62"}
    assert tela["horizonte_maximo_meses"] == 60
    # O registro começa com a v1, gravada pelo sistema, dizendo de onde ela veio
    assert len(tela["registro"]) == 1
    primeira = tela["registro"][0]
    assert primeira["versao"] == 1
    assert primeira["criado_por"].startswith("sistema")
    assert primeira["mudancas"][0].startswith("Primeira versão: Business case")


def test_mudancas_dizem_de_onde_para_onde_em_reais_e_em_meses():
    antes = {"horizonte_meses": 12, "mob_cliente_folha": "2090.62", "mob_cliente_nao_folha": "1724.00",
             "mob_cliente_novo_conquistado": "2090.62"}
    depois = {"horizonte_meses": 24, "mob_cliente_folha": "2150.00", "mob_cliente_nao_folha": "1724.0",
              "mob_cliente_novo_conquistado": "2090.62"}
    # "1724.00" e "1724.0" são o mesmo dinheiro: não entra no registro
    assert parametros.mudancas_das_premissas(antes, depois) == [
        "Horizonte da projeção: 12 meses → 24 meses",
        "MOB cliente folha: R$ 2.090,62 → R$ 2.150,00",
    ]


def test_conferencia_devolve_o_conteudo_com_duas_casas_e_as_mudancas(tmp_path):
    conexao = auth.conectar(tmp_path / "premissas.db")
    conferido = parametros.conferir_premissas_da_tela(conexao, valores_com(mob_cliente_nao_folha="1800"))
    assert conferido["conteudo"] == {"horizonte_meses": 12, "mob_cliente_folha": "2090.62",
                                     "mob_cliente_nao_folha": "1800.00", "mob_cliente_novo_conquistado": "2090.62"}
    assert conferido["mudancas"] == ["MOB cliente não folha: R$ 1.724,00 → R$ 1.800,00"]


def test_as_taxas_nao_entram_nas_premissas_oficiais(tmp_path):
    """Uma taxa mandada junto (ex.: de uma tela antiga) não entra na versão oficial: só no simulador."""
    conexao = auth.conectar(tmp_path / "premissas.db")
    conferido = parametros.conferir_premissas_da_tela(conexao, valores_com(mob_cliente_folha="2150",
                                                                           percentual_novas_contas="35"))
    assert sorted(conferido["conteudo"]) == ["horizonte_meses", "mob_cliente_folha", "mob_cliente_nao_folha",
                                             "mob_cliente_novo_conquistado"]
    with pytest.raises(ValueError, match="Nada mudou"):
        parametros.conferir_premissas_da_tela(conexao, valores_com(percentual_ja_correntista="35"))


@pytest.mark.parametrize("trocas, recado", [
    ({"mob_cliente_folha": "0"}, "maior que zero"),
    ({"mob_cliente_nao_folha": "-10"}, "maior que zero"),
    ({"mob_cliente_folha": "2090.625"}, "no máximo 2 casas"),
    ({"mob_cliente_folha": "dois mil"}, "informe um valor em reais"),
    ({"mob_cliente_folha": "NaN"}, "informe um valor em reais"),
    ({"mob_cliente_novo_conquistado": ""}, "Informe o valor"),
    ({"horizonte_meses": "0"}, "de 1 a 60"),
    ({"horizonte_meses": "61"}, "de 1 a 60"),
    ({"horizonte_meses": "12.5"}, "de 1 a 60"),
    ({"horizonte_meses": "-3"}, "de 1 a 60"),
    ({}, "Nada mudou"),
])
def test_conferencia_recusa_valor_invalido_e_nada_mudou(tmp_path, trocas, recado):
    conexao = auth.conectar(tmp_path / "premissas.db")
    with pytest.raises(ValueError, match=recado):
        parametros.conferir_premissas_da_tela(conexao, valores_com(**trocas))


def test_nova_versao_vale_para_os_calculos_e_a_v1_continua_guardada(tmp_path):
    conexao = auth.conectar(tmp_path / "premissas.db")
    conferido = parametros.conferir_premissas_da_tela(conexao, valores_com(mob_cliente_folha="2150.00"))
    parametros.salvar_premissas(conexao, conferido["conteudo"], "especialista.banco")
    # A v2 passa a ser a vigente (a que os cálculos novos usam)
    vigente = parametros.premissas_ativas(conexao)
    assert vigente.versao == "v2"
    assert vigente.mob_cliente_folha == Decimal("2150.00")
    # A v1 continua guardada, para as simulações feitas com ela
    assert parametros.premissas_da_versao(conexao, 1).mob_cliente_folha == Decimal("2090.62")
    # O registro: a v2 no alto, com quem gravou e o que mudou
    registro = parametros.registro_das_premissas(conexao)
    numeros_das_versoes = []
    for versao in registro:
        numeros_das_versoes.append(versao["versao"])
    assert numeros_das_versoes == [2, 1]
    assert registro[0]["criado_por"] == "especialista.banco"
    assert registro[0]["criado_em"]
    assert registro[0]["mudancas"] == ["MOB cliente folha: R$ 2.090,62 → R$ 2.150,00"]


# ---------------- As rotas (api/principal.py) ----------------

@pytest.fixture()
def banco_proprio(tmp_path, monkeypatch):
    """Um banco só deste teste, com um usuário do banco e um da empresa (a versão nova não vaza para os outros)."""
    monkeypatch.setattr(config, "CAMINHO_BANCO", tmp_path / "premissas_api.db")
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, "premissas.banco", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao, "premissas.empresa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao.close()


def navegador_logado(login: str) -> TestClient:
    """Um navegador de mentira já logado com o usuário informado."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200
    return navegador


def test_rotas_das_premissas_sao_so_do_banco(banco_proprio):
    anonimo = TestClient(aplicacao, follow_redirects=False)
    assert anonimo.get("/api/banco/premissas").status_code == 401
    assert anonimo.post("/api/banco/premissas", json=VALORES_DA_V1).status_code == 401
    empresa = navegador_logado("premissas.empresa")
    assert empresa.get("/api/banco/premissas").status_code == 403
    assert empresa.post("/api/banco/premissas", json=valores_com(mob_cliente_folha="1.00")).status_code == 403
    # A empresa não conseguiu gravar nada: continua a v1
    assert navegador_logado("premissas.banco").get("/api/banco/premissas").json()["versao"] == 1


def test_banco_grava_a_versao_oficial_nova_e_ve_o_registro(banco_proprio):
    banco = navegador_logado("premissas.banco")
    assert banco.get("/api/banco/premissas").json()["vigente"]["mob_cliente_folha"] == "2090.62"
    resposta = banco.post("/api/banco/premissas", json=valores_com(mob_cliente_folha="2150", horizonte_meses=24))
    assert resposta.status_code == 200
    tela = resposta.json()
    assert tela["versao"] == 2
    assert tela["vigente"]["mob_cliente_folha"] == "2150.00"
    assert tela["vigente"]["horizonte_meses"] == 24
    assert tela["mudancas"] == ["Horizonte da projeção: 12 meses → 24 meses",
                                "MOB cliente folha: R$ 2.090,62 → R$ 2.150,00"]
    assert tela["registro"][0]["criado_por"] == "premissas.banco"
    assert tela["registro"][1]["versao"] == 1
    # O GET mostra o mesmo
    assert banco.get("/api/banco/premissas").json()["versao"] == 2


def test_rota_recusa_com_400_e_a_mensagem_para_a_pessoa(banco_proprio):
    banco = navegador_logado("premissas.banco")
    recusado = banco.post("/api/banco/premissas", json=valores_com(mob_cliente_folha="-1"))
    assert recusado.status_code == 400
    assert "maior que zero" in recusado.json()["detail"]
    sem_mudanca = banco.post("/api/banco/premissas", json=VALORES_DA_V1)
    assert sem_mudanca.status_code == 400
    assert "Nada mudou" in sem_mudanca.json()["detail"]
    # Uma taxa (que é só do simulador) não muda a versão oficial: "Nada mudou"
    so_a_taxa = banco.post("/api/banco/premissas", json=valores_com(percentual_ja_correntista="40"))
    assert so_a_taxa.status_code == 400 and "Nada mudou" in so_a_taxa.json()["detail"]
    # Nada foi gravado
    assert banco.get("/api/banco/premissas").json()["versao"] == 1
