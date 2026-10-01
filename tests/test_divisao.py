"""Divisão de uma coluna em vários campos: o endereço inteiro numa célula só (ADR-76) e a divisão pela IA (ADR-104).

O que estes testes garantem:
- a regra separa rua, número, complemento, bairro, cidade, UF e CEP nos jeitos comuns de escrever um endereço;
- sem UF e com um pedaço só sobrando, a regra não chuta se é bairro ou cidade (o pedaço "sobra" e a tela mostra);
- "Salvador/BA" vira cidade e UF (naturalidade); "001 / 1234 / 56789-0" vira banco, agência e conta (separador);
- a proposta da IA só vale dentro do layout; nas linhas difíceis, só vale o pedaço que está na célula;
- no envio: a coluna com o endereço inteiro JÁ CHEGA dividida pela IA, cada parte ligada ao campo; o comentário da
  empresa refaz só aquela coluna, até o limite; depois do aceite, as partes chegam aos campos;
- a empresa também divide à mão (prévia sem gravar nada) e só antes do aceite.
"""
import json

import pytest

from models.contratos import DivisaoProposta, ParteDaDivisao, carregar_layout
from services import banco, cadastro, correcoes, divisao, divisao_da_coluna, mapeamentos
from services.llm_client import LLMClient
from tests.test_correcao import busca_falsa

# Uma planilha com o endereço inteiro numa coluna (CPFs válidos, dados fictícios)
PLANILHA_COM_ENDERECO = (
    "Nome;CPF;Endereço;Cargo\n"
    "Maria Souza;529.982.247-25;Rua das Flores, 123, apto 4 - Centro, São Paulo - SP, 01234-567;Analista\n"
    "João Lima;111.444.777-35;Av. Brasil 45 - Jardim América - Goiânia/GO;Assistente\n"
).encode("utf-8")


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste, fechado no fim."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def test_a_regra_separa_as_partes_do_endereco():
    dividido = divisao.dividir_endereco("Rua das Flores, 123, apto 4 - Centro, São Paulo - SP, 01234-567")
    assert dividido.partes == {"logradouro": "Rua das Flores", "numero": "123", "complemento": "apto 4",
                               "bairro": "Centro", "municipio": "São Paulo", "uf": "SP", "cep": "01234-567"}
    # O número colado na rua, CEP com ponto e "nº"
    assert divisao.dividir_endereco("Av. Brasil 45 - Jardim América - Goiânia/GO").partes["numero"] == "45"
    assert divisao.dividir_endereco("Travessa B, nº 7, Recife, PE, CEP 50.050-100").partes["cep"] == "50050-100"
    assert divisao.dividir_endereco("Rua A, s/n, Centro, Campinas/SP").partes["numero"] == "S/N"


def test_sem_uf_um_pedaco_sozinho_nao_vira_bairro_nem_cidade():
    dividido = divisao.dividir_endereco("Rua A, 10, Centro")
    assert "bairro" not in dividido.partes and "municipio" not in dividido.partes
    assert dividido.sobrou == ["Centro"]


def test_cidade_e_uf_da_naturalidade():
    assert divisao.dividir_cidade_e_uf("Salvador/BA").partes == {"municipio": "Salvador", "uf": "BA"}


def _colunas_por_nome(leitura: dict) -> dict:
    """{nome da coluna: a coluna como a tela recebe}."""
    colunas = {}
    for coluna in leitura["colunas"]:
        colunas[coluna["coluna"]] = coluna
    return colunas


def test_a_ia_ja_divide_o_endereco_inteiro_e_refaz_com_o_comentario(conexao):
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", PLANILHA_COM_ENDERECO, "lista.csv",
                                      busca=busca_falsa)
    processamento_id = leitura["processamento_id"]
    # A coluna chega dividida pela IA: a original fica de fora, com a prévia; cada parte, ligada ao seu campo
    colunas = _colunas_por_nome(leitura)
    assert colunas["Endereço"]["situacao"] == "Dividida pelo Agente Interpretador" and colunas["Endereço"]["campo"] is None
    assert colunas["Endereço · rua"]["campo"] == "logradouro_residencial"
    assert colunas["Endereço · rua"]["situacao"] == "Dividido pelo Agente Interpretador"
    assert colunas["Endereço · rua"]["parte_de"] == "Endereço"
    previa = colunas["Endereço"]["divisao"]["previa"]
    assert previa["linhas"][0][0].startswith("Rua das Flores") and "SP" in previa["linhas"][0]
    assert colunas["Endereço"]["divisao"]["refazer_restantes"] == 2
    # Sem comentário, não refaz
    with pytest.raises(ValueError, match="Conte o que está errado"):
        cadastro.refazer_divisao(conexao, "EMP001", "rh.teste", processamento_id, "Endereço", "  ")
    # O comentário refaz SÓ esta coluna: é o endereço do trabalho
    depois = cadastro.refazer_divisao(conexao, "EMP001", "rh.teste", processamento_id, "Endereço",
                                      "é o endereço do trabalho, não o de casa")
    colunas = _colunas_por_nome(depois)
    assert colunas["Endereço · rua"]["campo"] == "logradouro_comercial"
    assert colunas["Nome"]["campo"] == "nome_completo"
    assert colunas["Endereço"]["divisao"]["refazer_restantes"] == 1
    # Mais uma vez, e o limite chega
    cadastro.refazer_divisao(conexao, "EMP001", "rh.teste", processamento_id, "Endereço", "é o de casa")
    with pytest.raises(ValueError, match="já refez"):
        cadastro.refazer_divisao(conexao, "EMP001", "rh.teste", processamento_id, "Endereço", "de novo")
    # Depois do aceite, as partes chegam aos campos (a última divisão: o endereço de casa)
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", processamento_id, {}, busca=busca_falsa)
    joao = correcoes.dados_atuais(conexao, processamento_id).registros[1]
    assert joao["uf_residencial"] == "GO" and joao["numero_residencial"] == "45"
    assert joao["bairro_residencial"] == "Jardim América" and joao["municipio_residencial"] == "Goiânia"
    # Depois do aceite, não dá mais para dividir nem refazer
    with pytest.raises(ValueError, match="antes de aceitar"):
        cadastro.refazer_divisao(conexao, "EMP001", "rh.teste", processamento_id, "Endereço", "outra vez")
    plano = mapeamentos.obter(conexao, processamento_id)[0]
    campos_do_plano = set()
    for item in plano.itens:
        campos_do_plano.add(item.campo)
    assert {"logradouro_residencial", "bairro_residencial", "cep_residencial"} <= campos_do_plano


# Uma planilha com cidade e UF juntas numa coluna (a IA do MOCK não divide esta: a empresa divide à mão)
PLANILHA_COM_NATURALIDADE = (
    "Nome;CPF;Naturalidade;Cargo\n"
    "Maria Souza;529.982.247-25;Salvador/BA;Analista\n"
    "João Lima;111.444.777-35;Recife - PE;Assistente\n"
).encode("utf-8")


def test_a_empresa_divide_a_mao_com_previa_e_so_antes_do_aceite(conexao):
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.teste", PLANILHA_COM_NATURALIDADE, "lista.csv",
                                      busca=busca_falsa)
    processamento_id = leitura["processamento_id"]
    assert "Cidade e UF de nascimento" in leitura["destinos_da_divisao"]
    # A prévia mostra as partes e não grava nada
    previa = cadastro.previa_da_divisao(conexao, "EMP001", processamento_id, "Naturalidade", "Cidade e UF de nascimento")
    assert previa["exemplos"][0]["partes"] == {"municipio": "Salvador", "uf": "BA"}
    assert len(cadastro.leitura_do_envio(conexao, "EMP001", processamento_id)["colunas"]) == 4
    # Dividir: uma coluna por parte, "Ajustado por você"; a original, "Dividida por você"
    depois = cadastro.dividir_coluna(conexao, "EMP001", "rh.teste", processamento_id, "Naturalidade",
                                     "Cidade e UF de nascimento")
    colunas = _colunas_por_nome(depois)
    assert colunas["Naturalidade"]["situacao"] == "Dividida por você"
    assert colunas["Naturalidade · cidade"]["campo"] == "municipio_naturalidade"
    assert colunas["Naturalidade · UF"]["situacao"] == "Ajustado por você"
    # Dividir de novo a mesma coluna: recusado
    with pytest.raises(ValueError, match="já foi dividida"):
        cadastro.dividir_coluna(conexao, "EMP001", "rh.teste", processamento_id, "Naturalidade",
                                "Cidade e UF de nascimento")
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.teste", processamento_id, {}, busca=busca_falsa)
    joao = correcoes.dados_atuais(conexao, processamento_id).registros[1]
    assert joao["municipio_naturalidade"] == "Recife" and joao["uf_naturalidade"] == "PE"
    with pytest.raises(ValueError, match="antes de aceitar"):
        cadastro.dividir_coluna(conexao, "EMP001", "rh.teste", processamento_id, "Cargo", "Endereço comercial")


def _nomes_do_layout() -> set:
    """Os nomes dos campos do layout v1."""
    nomes = set()
    for campo in carregar_layout():
        nomes.add(campo.campo)
    return nomes


def test_divisao_por_separador_e_o_que_sobra_nao_vira_campo():
    dividido = divisao.dividir_por_separador("001 / 1234 / 56789-0", "/", ["banco", "agência", "conta"])
    assert dividido.partes == {"banco": "001", "agência": "1234", "conta": "56789-0"} and dividido.sobrou == []
    # Mais pedaços do que partes: os de sobra não vão para campo nenhum
    assert divisao.dividir_por_separador("a;b;c", ";", ["x", "y"]).sobrou == ["c"]


def test_a_proposta_da_ia_so_vale_dentro_do_layout():
    nomes = _nomes_do_layout()
    # Campo que não existe e campo repetido: a parte fica sem campo
    proposta = DivisaoProposta(ferramenta="cidade_uf", partes=[
        ParteDaDivisao(parte="municipio", campo="municipio_naturalidade"),
        ParteDaDivisao(parte="uf", campo="campo_que_nao_existe")])
    conferida = divisao_da_coluna.conferir_proposta(proposta, nomes)
    assert [parte.campo for parte in conferida.partes] == ["municipio_naturalidade", None]
    # Ferramenta que não existe, parte que a ferramenta não conhece e nenhum campo: recusadas
    with pytest.raises(ValueError, match="não existe"):
        divisao_da_coluna.conferir_proposta(DivisaoProposta(ferramenta="magica", partes=[]), nomes)
    with pytest.raises(ValueError, match="não existe na divisão"):
        divisao_da_coluna.conferir_proposta(DivisaoProposta(ferramenta="endereco", partes=[
            ParteDaDivisao(parte="planeta", campo="cep_residencial")]), nomes)
    with pytest.raises(ValueError, match="Nenhuma parte"):
        divisao_da_coluna.conferir_proposta(DivisaoProposta(ferramenta="separador", separador="/", partes=[
            ParteDaDivisao(parte="banco", campo=None)]), nomes)


def test_nas_linhas_dificeis_so_vale_o_pedaco_que_esta_na_celula():
    """A IA aponta, o código copia: o pedaço que a IA escreveu e não está na célula é descartado."""
    valores = ["Rua A, 10, Centro"]
    proposta = DivisaoProposta(ferramenta="endereco", partes=[
        ParteDaDivisao(parte="logradouro", campo="logradouro_residencial"),
        ParteDaDivisao(parte="numero", campo="numero_residencial"),
        ParteDaDivisao(parte="bairro", campo="bairro_residencial"),
        ParteDaDivisao(parte="municipio", campo="municipio_residencial")])
    valores_por_parte, linhas_com_sobra = divisao_da_coluna.dividir_valores(valores, proposta)
    # "Centro" sobrou (sem UF, a regra não sabe se é bairro ou cidade)
    assert linhas_com_sobra == [0] and valores_por_parte["bairro"] == [""]

    def ia_das_linhas(pedido):
        """Diz que "Centro" é o bairro e inventa a cidade."""
        return json.dumps({"linhas": [{"linha": 0, "partes": {"logradouro": "Rua A", "numero": "10",
                                                             "bairro": "Centro", "municipio": "São Paulo"}}]})
    cliente = LLMClient(modo="mock", respostas_mock={divisao_da_coluna.TAREFA_LINHAS: ia_das_linhas})
    completadas = divisao_da_coluna.completar_com_a_ia(valores, linhas_com_sobra, proposta, valores_por_parte, cliente)
    assert completadas == 1
    assert valores_por_parte["bairro"] == ["Centro"] and valores_por_parte["municipio"] == [""]


def test_a_ordem_dentro_da_celula_quase_nao_importa():
    """A rua é achada pelo tipo de via e o bairro pela palavra "Bairro", em qualquer posição."""
    dividido = divisao.dividir_endereco("Centro, Rua A, 10, Recife - PE")
    assert dividido.partes["logradouro"] == "Rua A" and dividido.partes["numero"] == "10"
    assert dividido.partes["bairro"] == "Centro" and dividido.partes["municipio"] == "Recife"
    dividido = divisao.dividir_endereco("apto 3, 45, Av. Brasil, Bairro Centro, Salvador")
    assert dividido.partes == {"logradouro": "Av. Brasil", "numero": "45", "complemento": "apto 3",
                               "bairro": "Centro", "municipio": "Salvador"}
