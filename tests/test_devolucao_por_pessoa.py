"""Apontar problema numa pessoa e aprovar os outros, devolvendo só os apontados (ADR-121).

O que estes testes provam:
- o especialista aponta qualquer pessoa do envio que espera o banco (motivo da lista + recado de 15 letras ou mais),
  troca e desfaz o apontamento; a empresa e quem não entrou são barrados, também pelas rotas;
- os três botões só valem na situação certa: "Aprovar" sem apontamento, "Aprovar e devolver" com apontamento (e não
  com todos apontados) e "Devolver o envio inteiro" com motivo;
- "Aprovar e devolver": as outras pessoas são cadastradas na hora; as apontadas voltam num envio de devolução, com a
  pendência "Pedido do banco" (as palavras do especialista); a linha do tempo mostra a aprovação em parte e a
  devolução em laranja, e as "Idas e voltas com o banco" contam as rodadas;
- a empresa responde (corrige, confirma ou tira a pessoa) e manda de novo; o banco lê a resposta e aprova;
- tirar a última pessoa do envio de devolução encerra a devolução sem voltar ao banco;
- "Devolver o envio inteiro" com apontamentos: eles viram pendências do próprio envio, e a etapa de aprovação
  mostra "Devolvido: o envio inteiro" até a empresa mandar de novo.
"""
import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import EstadoProcessamento
from services import (acompanhamento, apontamentos_do_banco, assistente_na_tela, auth, avaliacao_do_banco, correcoes,
                      homologacao, processamentos)
from tests.test_avaliacao_do_banco import (ESPECIALISTA, RH_DA_AURORA, SENHA_DE_TESTE, entrar,  # noqa: F401
                                           enviar_a_aurora_ao_banco)
from tests.test_correcao import busca_falsa
from tests.test_fluxo_empresa import conexao, gerar_envios, verdade  # noqa: F401
from workflows import fluxo_empresa as fluxo

# O recado que o especialista escreve nos testes
RECADO = "O salário parece alto demais para o cargo. Pode conferir?"


def _pessoas(conexao, processamento_id: str) -> list[dict]:
    """As pessoas do envio como o especialista vê."""
    return avaliacao_do_banco.pessoas_do_envio(conexao, ESPECIALISTA, processamento_id)


def _aprovar_e_devolver_a_primeira(conexao, verdade) -> tuple[str, str, dict, int]:
    """A Aurora vai ao banco; o especialista aponta a primeira pessoa e aprova as outras.

    Devolve: (envio de origem, envio de devolução, a pessoa apontada, quantas pessoas o banco avaliou).
    """
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    pessoas = _pessoas(conexao, processamento_id)
    apontada = pessoas[0]
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, apontada["linha"], "salario", RECADO)
    envio = avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id,
                                       decisao="aprovar_e_devolver_marcados")
    return processamento_id, envio["envio_de_devolucao"], apontada, len(pessoas)


def _etapa(etapas: list[dict], nome: str) -> dict:
    """Uma etapa da linha do tempo pelo nome."""
    for etapa in etapas:
        if etapa["nome"] == nome:
            return etapa
    raise AssertionError("Etapa não encontrada: " + nome)


def _envio_da_empresa(conexao, processamento_id: str) -> dict:
    """Um envio como a empresa vê em Acompanhar cadastros."""
    for envio in acompanhamento.envios_da_empresa(conexao, "EMP001"):
        if envio["processamento_id"] == processamento_id:
            return envio
    raise AssertionError("Envio não encontrado: " + processamento_id)


def _mandar_de_novo(conexao, processamento_id: str) -> None:
    """A empresa manda o envio de novo ao banco, pelo caminho de sempre."""
    fluxo.responder(conexao, processamento_id, "EMP001", "aprovar_homologacao", {"acao": "homologar", "usuario": "rh"},
                    busca=busca_falsa)


# ---------------- Apontar ----------------

def test_apontar_trocar_e_desfazer(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    pessoa = _pessoas(conexao, processamento_id)[1]
    # Motivo fora da lista, recado curto e pessoa que não é do envio: recusados, com a frase para a tela
    with pytest.raises(ValueError, match="motivo da lista"):
        avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoa["linha"], "inventado", RECADO)
    with pytest.raises(ValueError, match="15 letras"):
        avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoa["linha"], "salario", "Confira.")
    with pytest.raises(ValueError, match="não está neste envio"):
        avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, 9999, "salario", RECADO)
    # Apontar: a pessoa aparece apontada na lista do especialista e o envio conta 1 apontamento
    apontamento = avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoa["linha"], "salario", RECADO)
    assert apontamento == {"motivo": "salario", "motivo_texto": "Confirmar o salário", "recado": RECADO}
    assert _pessoas(conexao, processamento_id)[1]["apontamento"] == apontamento
    assert avaliacao_do_banco.fila_de_envios(conexao, ESPECIALISTA)[0]["apontamentos"] == 1
    # Apontar de novo troca o recado (continua um só)
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoa["linha"], "cpf", "O CPF não confere.  ")
    assert _pessoas(conexao, processamento_id)[1]["apontamento"]["motivo_texto"] == "CPF incorreto"
    assert len(apontamentos_do_banco.rascunhos(conexao, processamento_id)) == 1
    # Desfazer: some; desfazer de novo não há o que desfazer
    avaliacao_do_banco.desfazer_apontamento(conexao, ESPECIALISTA, processamento_id, pessoa["linha"])
    assert _pessoas(conexao, processamento_id)[1]["apontamento"] is None
    with pytest.raises(ValueError):
        avaliacao_do_banco.desfazer_apontamento(conexao, ESPECIALISTA, processamento_id, pessoa["linha"])
    # Só o banco aponta
    with pytest.raises(PermissionError):
        avaliacao_do_banco.apontar(conexao, RH_DA_AURORA, processamento_id, pessoa["linha"], "salario", RECADO)


def test_cada_botao_so_vale_na_situacao_certa(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    pessoas = _pessoas(conexao, processamento_id)
    # Sem apontamento, "Aprovar e devolver" não faz sentido
    with pytest.raises(ValueError, match="Nenhuma pessoa está apontada"):
        avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, decisao="aprovar_e_devolver_marcados")
    # Com apontamento, "Aprovar" (tudo) não vale: o especialista usa "Aprovar e devolver" ou desfaz
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoas[0]["linha"], "salario", RECADO)
    with pytest.raises(ValueError, match="1 pessoa com problema apontado"):
        avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, decisao="aprovar")
    # Todas apontadas: é "Devolver o envio inteiro"
    for pessoa in pessoas:
        avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoa["linha"], "outro", RECADO)
    with pytest.raises(ValueError, match="Todas as pessoas"):
        avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, decisao="aprovar_e_devolver_marcados")
    # Nada mudou no envio: ele continua esperando o banco
    assert processamentos.obter(conexao, processamento_id).status == EstadoProcessamento.AGUARDANDO_BANCO


# ---------------- Aprovar os outros e devolver os apontados ----------------

def test_aprovar_os_outros_e_devolver_o_apontado(conexao, verdade):
    origem, devolucao, apontada, total = _aprovar_e_devolver_a_primeira(conexao, verdade)
    # O envio de origem está cadastrado, sem a pessoa apontada
    assert processamentos.obter(conexao, origem).status == EstadoProcessamento.HOMOLOGADO
    assert homologacao.obter(conexao, origem)["relatorio"]["registros_homologados"] == total - 1
    assert homologacao.obter(conexao, origem)["relatorio"]["devolvidos_pelo_banco"] == 1
    # O envio de devolução está com a empresa, só com a pessoa apontada
    perfil = processamentos.obter(conexao, devolucao)
    assert perfil.status == EstadoProcessamento.DEVOLVIDO and perfil.envio_de_origem == origem and perfil.n_linhas == 1
    assert [registro["_linha"] for registro in correcoes.dados_atuais(conexao, devolucao).registros] == \
        [apontada["linha"]]
    # A lista de funcionários da empresa: as outras cadastradas, a apontada pendente com o pedido do banco
    funcionarios = acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001")
    pendentes = []
    for funcionario in funcionarios:
        if funcionario["situacao"] == "Pendente":
            pendentes.append(funcionario)
    assert len(funcionarios) == total and len(pendentes) == 1
    assert pendentes[0]["nome_completo"] == apontada["nome"] and pendentes[0]["pendencia"] == "O banco pediu: " + RECADO
    # A pendência em conversa: selo do banco e as palavras do especialista (a IA não reescreve)
    pendencias = acompanhamento.pendencias_da_empresa(conexao, "EMP001")
    assert len(pendencias) == 1 and pendencias[0]["pedido_do_banco"] is True
    assert pendencias[0]["pergunta"] == "O banco pediu: " + RECADO and pendencias[0]["campo"] == "valor_renda"
    # A linha do tempo do envio de origem: aprovação em parte, em verde clarinho
    aprovacao = _etapa(_envio_da_empresa(conexao, origem)["linha_do_tempo"], "Aprovação das contas enviadas")
    assert aprovacao["feito"] and aprovacao["parcial"]
    assert aprovacao["detalhe"] == str(total - 1) + " de " + str(total) + " aprovadas · 1 devolvida"
    # O envio de devolução: de onde veio, a aprovação devolvida (laranja) e as etapas de antes vindas da origem
    envio_de_devolucao = _envio_da_empresa(conexao, devolucao)
    assert envio_de_devolucao["origem"]["processamento_id"] == origem
    assert envio_de_devolucao["origem"]["texto"].startswith("Devolução do envio de ")
    assert envio_de_devolucao["origem"]["texto"].endswith("(1 pessoa)")
    assert envio_de_devolucao["motivo_da_devolucao"] is None
    etapas = envio_de_devolucao["linha_do_tempo"]
    assert _etapa(etapas, "Enviado ao banco")["feito"] and _etapa(etapas, "Arquivo carregado")["feito"]
    devolvida = _etapa(etapas, "Aprovação das contas enviadas")
    assert devolvida["devolvido"] and devolvida["atual"] and not devolvida["feito"]
    assert devolvida["detalhe"] == "Devolvido: 1 pessoa"
    # As idas e voltas: iguais nos dois envios da família
    idas = envio_de_devolucao["idas_e_voltas"]
    assert [ida["tipo"] for ida in idas] == ["enviado", "aprovado_em_parte"]
    assert idas[0]["texto"] == "1º envio ao banco"
    assert apontada["nome"] + ": Confirmar o salário" in idas[1]["texto"] and "devolveu 1" in idas[1]["texto"]
    assert _envio_da_empresa(conexao, origem)["idas_e_voltas"] == idas
    # O banco: o envio de origem aprovado (com as devolvidas no resultado) e o de devolução, que ainda não voltou
    fila = avaliacao_do_banco.fila_de_envios(conexao, ESPECIALISTA)
    por_id = {}
    for envio in fila:
        por_id[envio["id"]] = envio
    assert "1 pessoa devolvida(s) à empresa" in por_id[origem]["resultado"]
    assert por_id[devolucao]["situacao"] == "devolvido" and por_id[devolucao]["origem"].endswith("(1 pessoa)")
    assert avaliacao_do_banco.envios_esperando_o_banco(conexao) == 0


def test_a_empresa_corrige_manda_de_novo_e_o_banco_aprova(conexao, verdade):
    origem, devolucao, apontada, total = _aprovar_e_devolver_a_primeira(conexao, verdade)
    # A empresa corrige o salário: a pendência do banco some
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh", devolucao, apontada["linha"], "valor_renda",
                                      "3.500,00", "Salário conferido na folha")
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP001") == []
    # A etapa continua devolvida (laranja) até a empresa mandar de novo
    etapas = _envio_da_empresa(conexao, devolucao)["linha_do_tempo"]
    assert _etapa(etapas, "Aprovação das contas enviadas")["devolvido"]
    # Manda de novo: o banco vê o envio de devolução esperando, com a resposta da empresa ao apontamento
    _mandar_de_novo(conexao, devolucao)
    envio = avaliacao_do_banco.fila_de_envios(conexao, ESPECIALISTA)[0]
    assert envio["id"] == devolucao and envio["situacao"] == "aguardando"
    resposta = envio["respostas_aos_apontamentos"][0]
    assert resposta["nome"] == apontada["nome"] and resposta["recado"] == RECADO
    assert resposta["resposta"].startswith("A empresa corrigiu") and "R$ 3.500,00" in resposta["resposta"]
    # A etapa volta a esperar o banco, sem laranja
    aprovacao = _etapa(_envio_da_empresa(conexao, devolucao)["linha_do_tempo"], "Aprovação das contas enviadas")
    assert aprovacao["atual"] and not aprovacao["devolvido"]
    # O banco aprova: todas cadastradas; a aprovação do envio de origem fica completa
    avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, devolucao, decisao="aprovar")
    assert processamentos.obter(conexao, devolucao).status == EstadoProcessamento.HOMOLOGADO
    situacoes = set()
    for funcionario in acompanhamento.todos_os_funcionarios_da_empresa(conexao, "EMP001"):
        situacoes.add(funcionario["situacao"])
    assert situacoes == {"Cadastrado"}
    aprovacao = _etapa(_envio_da_empresa(conexao, origem)["linha_do_tempo"], "Aprovação das contas enviadas")
    assert aprovacao["detalhe"] == str(total) + " de " + str(total) + " aprovadas" and not aprovacao["parcial"]
    # As idas e voltas: 1º envio, aprovação em parte, 2º envio (as devolvidas) e aprovação
    idas = _envio_da_empresa(conexao, origem)["idas_e_voltas"]
    assert [ida["tipo"] for ida in idas] == ["enviado", "aprovado_em_parte", "enviado", "aprovado"]
    assert idas[2]["texto"] == "2º envio ao banco (as pessoas devolvidas)" and idas[3]["texto"] == "O banco aprovou 1 pessoa"


def test_a_empresa_responde_que_esta_certo(conexao, verdade):
    _, devolucao, apontada, _ = _aprovar_e_devolver_a_primeira(conexao, verdade)
    pendencia = acompanhamento.pendencias_da_empresa(conexao, "EMP001")[0]
    acompanhamento.confirmar_pendencia(conexao, "EMP001", "rh", devolucao, pendencia["regra_id"], pendencia["linha"],
                                       "Está certo: é o salário de diretor.")
    assert acompanhamento.pendencias_da_empresa(conexao, "EMP001") == []
    _mandar_de_novo(conexao, devolucao)
    envio = avaliacao_do_banco.fila_de_envios(conexao, ESPECIALISTA)[0]
    assert envio["respostas_aos_apontamentos"][0]["resposta"] == "A empresa respondeu: \"Está certo: é o salário de diretor.\""
    # A resposta ao pedido do banco não se repete nos alertas confirmados
    for alerta in envio["alertas"]:
        assert "O banco pediu" not in alerta["texto"]
    # O especialista pode apontar de novo a mesma pessoa, com um recado novo (vira uma pendência nova)
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, devolucao, apontada["linha"], "outro_dado",
                               "Mande o holerite do último mês, por favor.")
    avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, devolucao, decisao="devolver", motivo="Falta o holerite.")
    pendencias = acompanhamento.pendencias_da_empresa(conexao, "EMP001")
    assert len(pendencias) == 1 and pendencias[0]["pergunta"] == "O banco pediu: Mande o holerite do último mês, por favor."


def test_tirar_a_ultima_pessoa_encerra_a_devolucao(conexao, verdade):
    origem, devolucao, apontada, total = _aprovar_e_devolver_a_primeira(conexao, verdade)
    # "Não cadastrar esta pessoa", confirmado pela empresa (o caminho da conversa, ADR-118)
    retirada = correcoes.propor(conexao, devolucao, "EMP001", apontada["linha"], correcoes.EXCLUIR, None,
                                "Ela saiu da empresa", "rh")
    resposta = assistente_na_tela.confirmar_retirada(conexao, "EMP001", "rh", devolucao, retirada.correcao_id, True)
    assert "foi encerrado" in resposta["mensagem"] and resposta["aplicado"]["desfazer"] is None
    # A devolução se encerra sozinha, sem voltar ao banco
    assert processamentos.obter(conexao, devolucao).status == EstadoProcessamento.REJEITADO
    assert avaliacao_do_banco.envios_esperando_o_banco(conexao) == 0
    aprovacao = _etapa(_envio_da_empresa(conexao, origem)["linha_do_tempo"], "Aprovação das contas enviadas")
    assert aprovacao["detalhe"] == str(total - 1) + " de " + str(total) + " aprovadas · 1 saiu do envio"
    assert not aprovacao["parcial"]
    assert _envio_da_empresa(conexao, origem)["idas_e_voltas"][-1]["tipo"] == "encerrado"


# ---------------- Devolver o envio inteiro ----------------

def test_devolver_inteiro_com_apontamento(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    pessoa = _pessoas(conexao, processamento_id)[2]
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoa["linha"], "salario", RECADO)
    envio = avaliacao_do_banco.avaliar(conexao, ESPECIALISTA, processamento_id, decisao="devolver",
                                       motivo="Confira o arquivo todo.")
    assert envio["situacao"] == "devolvido" and envio["envio_de_devolucao"] is None
    # O apontamento vira pendência do próprio envio; o motivo geral aparece no alto
    pendencias = acompanhamento.pendencias_da_empresa(conexao, "EMP001")
    assert [pendencia["pedido_do_banco"] for pendencia in pendencias] == [True]
    envio_da_empresa = _envio_da_empresa(conexao, processamento_id)
    assert envio_da_empresa["situacao"] == "Devolvido pelo banco"
    assert envio_da_empresa["motivo_da_devolucao"] == "Confira o arquivo todo."
    aprovacao = _etapa(envio_da_empresa["linha_do_tempo"], "Aprovação das contas enviadas")
    assert aprovacao["devolvido"] and aprovacao["detalhe"] == "Devolvido: o envio inteiro"
    assert [ida["tipo"] for ida in envio_da_empresa["idas_e_voltas"]] == ["enviado", "devolvido"]
    # A empresa corrige: o recado do banco continua à vista até ela mandar de novo
    acompanhamento.corrigir_pendencia(conexao, "EMP001", "rh", processamento_id, pessoa["linha"], "valor_renda",
                                      "3.500,00", "Conferido")
    assert _envio_da_empresa(conexao, processamento_id)["motivo_da_devolucao"] == "Confira o arquivo todo."
    _mandar_de_novo(conexao, processamento_id)
    envio_da_empresa = _envio_da_empresa(conexao, processamento_id)
    assert envio_da_empresa["motivo_da_devolucao"] is None
    assert not _etapa(envio_da_empresa["linha_do_tempo"], "Aprovação das contas enviadas")["devolvido"]


# ---------------- As rotas ----------------

@pytest.fixture
def api_com_a_aurora_no_banco(tmp_path, monkeypatch, verdade):
    """A API apontada para um banco só deste teste, com a Aurora já enviada ao banco."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_devolucao.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    processamento_id = enviar_a_aurora_ao_banco(conexao_do_teste, verdade)
    linha = _pessoas(conexao_do_teste, processamento_id)[0]["linha"]
    from models.contratos import Perfil
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao_do_teste.close()
    return processamento_id, linha


def test_rotas_de_apontamento_e_decisao(api_com_a_aurora_no_banco):
    processamento_id, linha = api_com_a_aurora_no_banco
    especialista = entrar("especialista")
    rh = entrar("rh.aurora")
    anonimo = TestClient(aplicacao)
    rota = "/api/banco/envios/" + processamento_id + "/apontamentos"
    pedido = {"linha": linha, "motivo": "salario", "recado": RECADO}
    # Os motivos e o apontamento: só o banco
    assert anonimo.get("/api/banco/motivos_de_apontamento").status_code == 401
    assert rh.get("/api/banco/motivos_de_apontamento").status_code == 403
    assert especialista.get("/api/banco/motivos_de_apontamento").json()[0] == {"valor": "salario",
                                                                                "texto": "Confirmar o salário"}
    assert anonimo.post(rota, json=pedido).status_code == 401
    assert rh.post(rota, json=pedido).status_code == 403
    assert especialista.post(rota, json={"linha": linha, "motivo": "salario", "recado": "curto"}).status_code == 400
    assert especialista.post("/api/banco/envios/nao-existe/apontamentos", json=pedido).status_code == 404
    resposta = especialista.post(rota, json=pedido)
    assert resposta.status_code == 200 and resposta.json()["apontamento"]["recado"] == RECADO
    # Desfazer e apontar de novo
    assert rh.delete(rota + "/" + str(linha)).status_code == 403
    assert especialista.delete(rota + "/" + str(linha)).json() == {"ok": True}
    assert especialista.delete(rota + "/" + str(linha)).status_code == 400
    especialista.post(rota, json=pedido)
    # A decisão nova: aprovar tudo não vale com apontamento; aprovar e devolver cria o envio de devolução
    avaliar = "/api/banco/envios/" + processamento_id + "/avaliar"
    assert especialista.post(avaliar, json={"decisao": "aprovar"}).status_code == 400
    assert especialista.post(avaliar, json={"decisao": "inventada"}).status_code == 400
    resposta = especialista.post(avaliar, json={"decisao": "aprovar_e_devolver_marcados"})
    assert resposta.status_code == 200 and resposta.json()["situacao"] == "aprovado"
    assert resposta.json()["envio_de_devolucao"]


# ---------------- Baixar a lista do envio ----------------

def test_baixar_a_lista_do_envio(conexao, verdade):
    processamento_id = enviar_a_aurora_ao_banco(conexao, verdade)
    pessoas = _pessoas(conexao, processamento_id)
    avaliacao_do_banco.apontar(conexao, ESPECIALISTA, processamento_id, pessoas[0]["linha"], "salario", RECADO)
    conteudo, nome_do_arquivo = avaliacao_do_banco.arquivo_do_envio(conexao, ESPECIALISTA, processamento_id)
    assert nome_do_arquivo == "envio_EMP001_" + processamento_id + ".csv"
    # UTF-8 com a marca que o Excel reconhece; separador ";"
    texto = conteudo.decode("utf-8")
    assert texto.startswith("\ufeffLinha no arquivo;")
    linhas = texto.lstrip("\ufeff").strip().split("\n")
    # O cabeçalho: a linha, um rótulo por campo do parâmetro e as duas colunas da avaliação
    cabecalho = linhas[0].split(";")
    assert len(cabecalho) == 1 + len(acompanhamento.colunas_da_consulta(conexao)) + 2
    assert cabecalho[-2:] == ["Situação na avaliação", "Problema apontado"]
    # Uma linha por pessoa da grade; a apontada traz a situação e o recado
    assert len(linhas) == len(pessoas) + 1
    primeira = linhas[1].split(";")
    assert primeira[0] == str(pessoas[0]["linha"]) and primeira[-2] == "Apontado por você"
    assert primeira[-1] == "Confirmar o salário: " + RECADO
    # O CPF vai inteiro, como o layout do banco guarda (só números)
    assert pessoas[0]["cpf"].replace(".", "").replace("-", "") in linhas[1]
    # O download fica registrado nos acessos da empresa, com quantas pessoas
    acesso = acompanhamento.acessos_da_empresa(conexao, "EMP001")[-1]
    assert (acesso["login"], acesso["tipo"], acesso["quantidade"]) == ("especialista", "DOWNLOAD", len(pessoas))
    # Só o banco baixa; envio que não existe: KeyError (404 na rota)
    with pytest.raises(PermissionError):
        avaliacao_do_banco.arquivo_do_envio(conexao, RH_DA_AURORA, processamento_id)
    with pytest.raises(KeyError):
        avaliacao_do_banco.arquivo_do_envio(conexao, ESPECIALISTA, "nao-existe")


def test_rota_de_baixar_a_lista_do_envio(api_com_a_aurora_no_banco):
    processamento_id, _ = api_com_a_aurora_no_banco
    rota = "/api/banco/envios/" + processamento_id + "/baixar"
    assert TestClient(aplicacao).get(rota).status_code == 401
    assert entrar("rh.aurora").get(rota).status_code == 403
    assert entrar("especialista").get("/api/banco/envios/nao-existe/baixar").status_code == 404
    resposta = entrar("especialista").get(rota)
    assert resposta.status_code == 200 and resposta.headers["content-type"].startswith("text/csv")
    assert resposta.headers["content-disposition"] == 'attachment; filename="envio_EMP001_' + processamento_id + '.csv"'
    assert resposta.headers["cache-control"] == "no-store"
