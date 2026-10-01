"""A prévia das pessoas do envio: a 1ª aba ("Funcionários") do resultado de "Cadastrar funcionários".

O que estes testes provam:
- antes do aceite das colunas, a prévia mostra cada pessoa do arquivo com os valores das colunas que o agente
  reconheceu, padronizados do MESMO jeito que o aceite padroniza (o CPF com pontos, a data e o dinheiro no formato do
  sistema);
- a coluna em dúvida entre campos não entra nos valores (a empresa ainda vai escolher); a dúvida só entre campos
  opcionais vai para as "Informações sem rótulo" da pessoa, e a dúvida com um campo obrigatório não vai (a trava da
  LGPD, ADR-143, Parte 1);
- a prévia não grava nada: o mapeamento continua à espera do aceite, sem padronização guardada e sem evento novo na
  auditoria;
- depois do aceite, a prévia mostra os dados atuais do envio (com as correções), os mesmos da conferência da lista;
- vale para um arquivo que o sistema nunca viu, com outros nomes de coluna e outra ordem (a regra é geral);
- a rota é só da empresa dona do envio: sem login, 401; o banco, 403; outra empresa, 404.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil, StatusMapeamento
from services import auditoria, auth, cadastro, mapeamentos, normalizador, processamentos
from tests.apoio_do_parametro import marcar_como_obrigatorios
from tests.test_fluxo_empresa import (aprovar, busca_falsa, conexao, corrigir_cpf_da_aurora,  # noqa: F401
                                      gerar_envios, iniciar, receber, verdade)
from tests.test_interpretador import _resposta, cliente_que_responde

# A senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Os campos obrigatórios que nunca ficam em branco pelo sistema (um obrigatório inválido vira pendência, com o valor)
OBRIGATORIOS_COMPARADOS = ["cpf", "data_admissao", "valor_renda"]

# Um arquivo que o sistema nunca viu: outros nomes de coluna, outra ordem, a data com dia/mês e o dinheiro com ponto e
# vírgula. "Fone" fica em dúvida entre os dois telefones (opcionais); "Data", entre o nascimento e a admissão (esta é
# obrigatória).
ARQUIVO_COM_OUTROS_NOMES = (
    "Admitido em;Fone;CPF do colaborador;Salário mensal;Data\n"
    "25/03/2026;(19) 98765-4321;52998224725;3.150,00;17/05/1990\n"
    "30/01/2025;;11144477735;4.200,50;02/11/1988\n"
).encode()


def valores_por_linha(lista: dict) -> dict:
    """Os valores de cada pessoa de uma lista (a prévia ou a conferência), pela linha do arquivo. Ex.: {2: {...}}."""
    valores = {}
    for linha in lista["linhas"]:
        valores[linha["linha"]] = linha["valores"]
    return valores


def campos_reconhecidos(plano) -> set:
    """Os campos que as colunas reconhecidas pelo agente alimentam (as colunas em dúvida não contam)."""
    campos = set()
    for item in plano.itens:
        if item.status == StatusMapeamento.PROPOSTO:
            campos.add(item.campo)
    return campos


def test_antes_do_aceite_a_previa_mostra_a_leitura_do_agente_sem_gravar(conexao):
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    plano, status = mapeamentos.obter(conexao, processamento_id)
    eventos_antes = len(auditoria.eventos(conexao, processamento_id))
    previa = cadastro.previa_da_lista(conexao, empresa_id, processamento_id)
    # Uma linha por pessoa do arquivo
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    assert previa["pronta"] is True and len(previa["linhas"]) == len(leitura.linhas)
    for linha in previa["linhas"]:
        # Só os campos das colunas que o agente reconheceu, e o CPF com pontos, como na conferência
        assert set(linha["valores"]) <= campos_reconhecidos(plano)
        assert "informacoes_sem_rotulo" in linha
        if "cpf" in linha["valores"]:
            assert len(linha["valores"]["cpf"]) == 14 and linha["valores"]["cpf"][3] == "."
    # Nada gravado: o mapeamento espera o aceite, não há padronização guardada, e a auditoria não ganhou evento
    assert status == "PENDENTE" and mapeamentos.obter(conexao, processamento_id)[1] == "PENDENTE"
    assert normalizador.obter(conexao, processamento_id) is None
    assert len(auditoria.eventos(conexao, processamento_id)) == eventos_antes


def test_a_previa_padroniza_do_mesmo_jeito_que_o_aceite(conexao):
    """Os obrigatórios que a prévia mostra antes do aceite são os mesmos da conferência da lista depois dele."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    antes = valores_por_linha(cadastro.previa_da_lista(conexao, empresa_id, processamento_id))
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    depois = valores_por_linha(cadastro.lista_para_conferir(conexao, empresa_id, processamento_id))
    comparados = 0
    for numero_da_linha, valores_da_conferencia in depois.items():
        for campo in OBRIGATORIOS_COMPARADOS:
            # Só o que a prévia já mostrava (a coluna em dúvida só entra depois da escolha)
            if campo in antes[numero_da_linha]:
                assert antes[numero_da_linha][campo] == valores_da_conferencia.get(campo, ""), (numero_da_linha, campo)
                comparados = comparados + 1
    assert comparados > 0


def test_depois_do_aceite_a_previa_mostra_os_dados_atuais_do_envio(conexao, verdade):
    """Com as colunas aceitas e o CPF corrigido, a prévia é a lista que vai para o banco (a mesma da conferência)."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    iniciar(conexao, processamento_id, empresa_id)
    aprovar(conexao, processamento_id, empresa_id, "aurora_carga_inicial")
    corrigir_cpf_da_aurora(conexao, processamento_id, verdade)
    previa = valores_por_linha(cadastro.previa_da_lista(conexao, empresa_id, processamento_id))
    conferencia = valores_por_linha(cadastro.lista_para_conferir(conexao, empresa_id, processamento_id))
    assert conferencia
    for numero_da_linha, valores_da_conferencia in conferencia.items():
        # Cada valor da conferência (os vazios não vêm na prévia) é o mesmo na prévia
        for campo, valor in valores_da_conferencia.items():
            assert previa[numero_da_linha].get(campo, "") == valor, (numero_da_linha, campo)


def test_sem_a_leitura_das_colunas_a_previa_ainda_nao_esta_pronta(conexao):
    """O envio que parou antes da leitura das colunas: nada para mostrar, sem erro."""
    processamento_id, empresa_id = receber(conexao, "aurora_carga_inicial")
    assert cadastro.previa_da_lista(conexao, empresa_id, processamento_id) == {"pronta": False, "linhas": []}


def test_envio_de_outra_empresa_nao_e_encontrado(conexao):
    """A empresa nunca vê a prévia do envio de outra (KeyError vira 404 na rota)."""
    processamento_id, _ = receber(conexao, "aurora_carga_inicial")
    with pytest.raises(KeyError):
        cadastro.previa_da_lista(conexao, "EMP002", processamento_id)


def test_arquivo_com_outros_nomes_e_outra_ordem(conexao):
    """A regra vale para o arquivo que o sistema nunca viu: cada coluna reconhecida vai para o seu campo, padronizada;
    a dúvida entre os telefones (opcionais) fica sem rótulo; a dúvida com a admissão (obrigatória) fica de fora."""
    marcar_como_obrigatorios(conexao, "cpf", "valor_renda", "data_admissao", so_estes=True)
    recebido = processamentos.receber_arquivo(conexao, ARQUIVO_COM_OUTROS_NOMES, "equipe_nova.csv", "EMP001",
                                              date(2026, 9, 1), "empresa.teste")
    processamento_id = recebido.perfil.processamento_id
    resposta_do_agente = _resposta(
        {"coluna": "Admitido em", "campo": "data_admissao", "status": "PROPOSTO"},
        {"coluna": "Fone", "campo": None, "status": "AMBIGUO",
         "candidatos": ["telefone_celular", "telefone_residencial"]},
        {"coluna": "CPF do colaborador", "campo": "cpf", "status": "PROPOSTO"},
        {"coluna": "Salário mensal", "campo": "valor_renda", "status": "PROPOSTO"},
        {"coluna": "Data", "campo": None, "status": "AMBIGUO", "candidatos": ["data_nascimento", "data_admissao"]})
    mapeamentos.interpretar_processamento(conexao, processamento_id, "EMP001",
                                          cliente=cliente_que_responde(resposta_do_agente), configuracao="B3",
                                          busca=busca_falsa)
    previa = cadastro.previa_da_lista(conexao, "EMP001", processamento_id)
    primeira, segunda = previa["linhas"]
    # As colunas reconhecidas, padronizadas como no aceite; a "Data" em dúvida não vira nascimento nem admissão
    assert primeira["valores"] == {"cpf": "529.982.247-25", "data_admissao": "2026-03-25", "valor_renda": "3150.00"}
    assert segunda["valores"] == {"cpf": "111.444.777-35", "data_admissao": "2025-01-30", "valor_renda": "4200.50"}
    # O telefone em dúvida entre dois opcionais fica guardado sem rótulo, como veio; a pessoa sem telefone não tem nada
    assert [informacao["coluna"] for informacao in primeira["informacoes_sem_rotulo"]] == ["Fone"]
    assert primeira["informacoes_sem_rotulo"][0]["valor"] == "(19) 98765-4321"
    assert segunda["informacoes_sem_rotulo"] == []


# ---------------- A rota da API ----------------

@pytest.fixture
def api_da_previa(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com o envio da Aurora esperando o aceite das colunas."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_previa.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)
    conexao_do_teste = conectar_original(caminho)
    processamento_id, empresa_id = receber(conexao_do_teste, "aurora_carga_inicial")
    iniciar(conexao_do_teste, processamento_id, empresa_id)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao_do_teste, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    auth.cadastrar_usuario(conexao_do_teste, "especialista.previa", SENHA_DE_TESTE, Perfil.BANCO)
    conexao_do_teste.close()
    return processamento_id


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_a_rota_da_previa_e_so_da_empresa_dona_do_envio(api_da_previa):
    endereco = "/api/empresa/cadastro/" + api_da_previa + "/previa"
    # Sem login: 401; o especialista do banco: 403; outra empresa: 404, sem dizer se o envio existe
    assert TestClient(aplicacao).get(endereco).status_code == 401
    assert entrar("especialista.previa").get(endereco).status_code == 403
    assert entrar("rh.horizonte").get(endereco).status_code == 404
    # A dona do envio: as pessoas do arquivo, com os valores
    resposta = entrar("rh.aurora").get(endereco)
    assert resposta.status_code == 200
    assert resposta.json()["pronta"] is True and resposta.json()["linhas"]
