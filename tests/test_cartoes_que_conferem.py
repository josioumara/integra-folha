"""O cartão de pendência só diz "Pronto" quando o valor confere (ADR-127).

Origem: o teste de ponta a ponta com a IA real achou os cinco furos descritos abaixo. Cada teste prova a REGRA
GERAL: o caso que achou o furo fica, mas vem junto com pelo menos 3 variações que
ninguém usou (outras palavras, outro formato, outra ordem, outro valor). A IA é simulada: uma IA "teimosa" responde
sempre a ação do pior caso, para provar que a trava está no código e não na sorte da frase.

O que estes testes provam:
- um CPF ou CNPJ com o dígito errado (ou sem os dígitos certos) nunca vira "Pronto": a conversa diz "Esse CPF não
  confere", nada muda e a pendência continua; o CPF certo continua valendo na hora;
- um nome de pessoa não tem números nem palavras demais; a coluna com a ficha inteira não é oferecida como o Nome
  completo; uma coluna de nomes de verdade continua sendo;
- uma mensagem com "?" nunca confirma nem muda um dado: o agente responde à pergunta; se o modelo insistir, a fala
  fixa diz que nada mudou; sem "?", a confirmação continua valendo;
- o cartão do CNPJ do empregador e o do endereço comercial oferecem o que o cadastro da empresa já sabe; um clique
  preenche todos os funcionários sem o dado (o endereço inteiro de uma vez, com um Desfazer só), e o que o cadastro não
  tem não é inventado;
- o envio que voltou para a leitura das colunas aparece na lista de envios parados ("Voltou para a leitura das
  colunas"), e a rota é só da empresa dona (401 sem login, 403 para o banco, a outra empresa não vê).
"""
import json

import pytest
from fastapi.testclient import TestClient

from agents import assistente_correcao
from api.principal import aplicacao
from models.contratos import CampoLayout, EstadoProcessamento, Perfil, TipoCampo
from services import (acompanhamento, assistente_na_tela, auth, cadastro, coluna_do_campo_que_falta,
                      conferencia_do_valor, correcoes, dados_da_empresa_no_envio, processamentos, validador)
from services.llm_client import LLMClient
from tests.apoio_do_parametro import marcar_como_obrigatorios  # o campo do exemplo é opcional no layout (ADR-143)
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import EMPRESA, LOGIN, conexao, cpf_valido, usar_busca_falsa  # noqa: F401

# A regra da coluna que o arquivo inteiro não trouxe e a do valor fora da lista
SEM_COLUNA = "OBRIGATORIO_SEM_COLUNA"
FORA_DA_LISTA = "VALOR_NAO_CONVERTIDO"
# Senha dos usuários de teste das rotas
SENHA_DE_TESTE = "senha-de-teste-123"
# Três CPFs válidos (inventados)
CPFS = [cpf_valido("529982247"), cpf_valido("111444777"), cpf_valido("123456789")]


# ---------------- Ajudantes ----------------

def ia_em_sequencia(*respostas: dict) -> LLMClient:
    """Uma IA simulada que dá as respostas na ordem (a última se repete). Serve para ver o que o agente faz na 2ª vez."""
    fila = list(respostas)

    def responder(pedido):
        """Devolve a próxima resposta da fila, em JSON."""
        if len(fila) > 1:
            return json.dumps(fila.pop(0))
        return json.dumps(fila[0])
    return LLMClient(modo="mock", respostas_mock={assistente_correcao.TAREFA: responder})


def ia_que_corrige_com(valor: str) -> LLMClient:
    """Uma IA que sempre escolhe "corrigir" com o valor dado (o pior caso: ela acreditou no valor)."""
    return ia_em_sequencia({"acao": "corrigir", "mensagem": "Vou corrigir.", "valor": valor})


def enviar(conexao, cabecalho: str, linhas: list[str], escolhas: dict[str, str]) -> str:
    """Um arquivo CSV da Aurora, enviado e aceito com as escolhas de colunas (a validação roda no aceite)."""
    conteudo = ("\n".join([cabecalho] + linhas) + "\n").encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, conteudo, "teste.csv", busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], escolhas, busca=busca_falsa)
    return leitura["processamento_id"]


def envio_com_estado_civil_errado(conexao) -> str:
    """Três pessoas; a Ana veio com "Solteirx" (fora da lista): uma pendência de valor na linha dela.

    O estado civil é opcional no layout, e um campo opcional não abre pendência (ADR-143): o parâmetro deste banco de
    teste o marca como obrigatório, para o cartão continuar testado.
    """
    marcar_como_obrigatorios(conexao, "estado_civil")
    return enviar(conexao, "Nome;CPF;Estado civil",
                  [f"Ana Lima;{CPFS[0]};Solteirx", f"Bia Souza;{CPFS[1]};Casado", f"Caio Reis;{CPFS[2]};Casado"],
                  {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"})


def envio_sem_a_coluna_do_cpf(conexao) -> str:
    """Três pessoas sem a coluna do CPF: o cartão "o arquivo não trouxe o CPF"."""
    return enviar(conexao, "Nome;Estado civil", ["Ana Lima;Casado", "Bia Souza;Casado", "Caio Reis;Casado"],
                  {"Nome": "nome_completo", "Estado civil": "estado_civil"})


def achado_em_aberto(conexao, envio: str, regra_id: str, campo: str):
    """O achado em aberto da regra e do campo, ou None."""
    for achado in validador.obter(conexao, envio).achados:
        if achado.regra_id == regra_id and achado.campo == campo and not achado.resolvido:
            return achado
    return None


# ---------------- O CPF (e o CNPJ) com o dígito conferido antes do "Pronto" ----------------

def envio_com_o_cpf_da_ana_errado(conexao) -> tuple[str, int]:
    """Duas pessoas; o CPF da Ana veio com o último dígito trocado: o cartão do dígito. Devolve (envio, linha)."""
    envio = enviar(conexao, "Nome;CPF;Estado civil",
                   [f"Ana Lima;{CPFS[0][:-1]}0;Casado", f"Bia Souza;{CPFS[1]};Casado"],
                   {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"})
    return envio, achado_em_aberto(conexao, envio, "CPF_INVALIDO", "cpf").linha


@pytest.mark.parametrize("mensagem, valor", [
    ("o certo é 123.456.789-00", "123.456.789-00"),        # o caso real que achou o furo
    ("CPF correto: 111.444.777-00", "111.444.777-00"),     # outras palavras, outro número
    ("troca para 52998224700 por favor", "52998224700"),   # sem formatação, o pedido no fim
    ("é 1234567890", "1234567890"),                        # só 10 dígitos
])
def test_esse_cpf_nao_confere_e_nada_muda(conexao, mensagem, valor):
    envio, linha = envio_com_o_cpf_da_ana_errado(conexao)
    # A pior IA: ela "acreditou" no CPF e mandou corrigir
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, "CPF_INVALIDO", linha, mensagem,
                                            cliente=ia_que_corrige_com(valor), campo="cpf")
    assert resposta["mensagem"].startswith("Esse CPF não confere: ") and "Nada mudou." in resposta["mensagem"]
    assert "Pronto" not in resposta["mensagem"]
    assert resposta["aplicado"] is None and resposta["resolvida"] is False
    assert correcoes.listar(conexao, envio) == []


def test_o_cpf_certo_continua_valendo_na_hora(conexao):
    envio, linha = envio_com_o_cpf_da_ana_errado(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, "CPF_INVALIDO", linha,
                                            "o certo é " + CPFS[2], cliente=ia_que_corrige_com(CPFS[2]), campo="cpf")
    assert resposta["mensagem"].startswith("Pronto:") and resposta["resolvida"] is True


@pytest.mark.parametrize("valor", ["31/02/2026", "Solteirx", "abc"])
def test_qualquer_valor_que_nao_serve_para_o_campo_nao_vira_pronto(conexao, valor):
    # A regra não é só do CPF: o estado civil fora da lista também não vira "Pronto"
    envio = envio_com_estado_civil_errado(conexao)
    linha_da_ana = achado_em_aberto(conexao, envio, FORA_DA_LISTA, "estado_civil").linha
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, FORA_DA_LISTA, linha_da_ana,
                                            "o certo é " + valor, cliente=ia_que_corrige_com(valor),
                                            campo="estado_civil")
    assert resposta["aplicado"] is None and "Nada mudou." in resposta["mensagem"]
    assert correcoes.listar(conexao, envio) == []


@pytest.mark.parametrize("cnpj, confere", [
    ("10.433.218/0001-93", True),     # o da Aurora, certo
    ("10.433.218/0001-00", False),    # o dígito trocado
    ("11222333000180", False),        # sem formatação, dígito errado
    ("11.222.333/0001-81", True),     # outro CNPJ certo
])
def test_o_cnpj_tambem_tem_o_digito_conferido(conexao, cnpj, confere):
    motivo = conferencia_do_valor.motivo_para_recusar(conexao, "cnpj_empregador", cnpj)
    assert (motivo is None) is confere


# ---------------- Um nome de pessoa não tem números nem palavras demais ----------------

@pytest.mark.parametrize("valor", [
    "Elisa Moura / apelido Lisa; registro do cliente 715.937.364-28; identidade 12.345.678-9",   # a ficha (o caso real)
    "Marcos Paulo Teixeira - nasc. 12/03/1990",                                                 # uma data
    "Joana Prado RG 44556677",                                                                  # um documento
    "Funcionária transferida da unidade de Campinas para a matriz de São Paulo no mês passado",  # um texto
])
def test_o_que_nao_e_nome_de_pessoa_e_recusado(conexao, valor):
    assert conferencia_do_valor.motivo_do_nome(valor) is not None
    assert conferencia_do_valor.motivo_para_recusar(conexao, "nome_completo", valor) is not None


@pytest.mark.parametrize("nome", ["Ana Lima", "Maria da Conceição dos Santos Oliveira de Souza Lima",
                                  "João D'Ávila", "Anne-Marie Souza"])
def test_nomes_de_verdade_continuam_valendo(conexao, nome):
    assert conferencia_do_valor.motivo_para_recusar(conexao, "nome_completo", nome) is None


def test_a_coluna_com_a_ficha_inteira_nao_vira_o_nome_completo(conexao):
    # O nome ficou de fora do aceite; a coluna "Observações" traz a ficha inteira de cada pessoa
    envio = enviar(conexao, "Observações;CPF;Estado civil",
                   [f"Ana Lima, CPF {CPFS[0]}, nascida em 02/02/1990;{CPFS[0]};Casado",
                    f"Bia Souza - identidade 1234567 - mãe Rita;{CPFS[1]};Casado",
                    f"Caio Reis (admissão 01/08/2026);{CPFS[2]};Casado"],
                   {"CPF": "cpf", "Estado civil": "estado_civil"})
    conferencia = coluna_do_campo_que_falta.conferir(conexao, envio, "Observações", "nome_completo")
    assert (conferencia["preenchidos"], conferencia["validos"], conferencia["maioria"]) == (3, 0, False)
    assert conferencia["exemplos"][0]["motivo"] == "um nome não tem números"


def test_a_coluna_de_nomes_de_verdade_continua_sendo_oferecida(conexao):
    envio = enviar(conexao, "Funcionário;CPF;Estado civil",
                   [f"Ana Lima;{CPFS[0]};Casado", f"Bia Souza;{CPFS[1]};Casado", f"Caio Reis;{CPFS[2]};Casado"],
                   {"CPF": "cpf", "Estado civil": "estado_civil"})
    conferencia = coluna_do_campo_que_falta.conferir(conexao, envio, "Funcionário", "nome_completo")
    assert conferencia["maioria"] is True and conferencia["validos"] == 3


def test_a_regra_do_nome_so_vale_para_nome_de_pessoa():
    # O "Nome da unidade" pode ter número ("Loja 12"): a regra do nome de pessoa não vale para ele
    unidade = CampoLayout(campo="nome_unidade", grupo="Cadastro empresarial", tipo=TipoCampo.TEXTO,
                          obrigatorio=False, sensivel=False, uso_comercial_permitido=True)
    conferencia = conferencia_do_valor.conferir_valores(["Loja 12", "Filial 3 - Centro"], unidade)
    assert conferencia["nao_servem"] == 0


# ---------------- Uma pergunta nunca confirma nem muda um dado ----------------

CONFIRMAR = {"acao": "confirmar_alerta", "mensagem": "Registrado.", "justificativa": "a empresa confirmou"}
EXPLICAR = {"acao": "responder", "mensagem": "Empresa do grupo é outra empresa com o mesmo dono. É o caso?"}


def envio_com_alerta(conexao):
    """Um envio com um alerta (a efetivação da Ana antes da admissão) e o achado dele.

    A efetivação é opcional no layout, e um campo opcional não abre pendência (ADR-143): o parâmetro deste banco de
    teste a marca como obrigatória, para a confirmação continuar testada.
    """
    marcar_como_obrigatorios(conexao, "data_efetivacao")
    envio = enviar(conexao, "Nome;CPF;Estado civil;Admissão;Efetivação",
                   [f"Ana Lima;{CPFS[0]};Casado;20/08/2026;15/07/2026",
                    f"Bia Souza;{CPFS[1]};Casado;20/08/2026;20/09/2026"],
                   {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil", "Admissão": "data_admissao",
                    "Efetivação": "data_efetivacao"})
    for achado in validador.obter(conexao, envio).achados:
        if achado.regra_id == "EFETIVACAO_ANTES_DA_ADMISSAO" and not achado.resolvido:
            return envio, achado
    raise AssertionError("o arquivo de teste devia ter o alerta da efetivação antes da admissão")


@pytest.mark.parametrize("pergunta", [
    "o que é empresa do grupo? esse CNPJ é o da nossa matriz",   # o caso real
    "Isso quer dizer o quê? Se for normal, pode confirmar",      # outra ordem
    "está certo assim?",                                          # a própria confirmação, como pergunta
    "Pode confirmar pra mim? É o salário do diretor",           # pergunta no começo
])
def test_mensagem_com_pergunta_nunca_confirma(conexao, pergunta):
    envio, alerta = envio_com_alerta(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, alerta.regra_id, alerta.linha, pergunta,
                                            cliente=ia_em_sequencia(CONFIRMAR, EXPLICAR), campo=alerta.campo)
    # O modelo recebeu a regra e respondeu à pergunta; o alerta continua em aberto
    assert resposta["aplicado"] is None and resposta["acao"] == "responder"
    # A resposta do modelo, com a informação e o que veio no arquivo na frente (a pergunta mostra o dado, ADR-153)
    assert resposta["mensagem"].endswith(EXPLICAR["mensagem"])
    assert resposta["mensagem"].startswith('No arquivo, a informação "') and '"15/07/2026"' in resposta["mensagem"]
    assert achado_em_aberto(conexao, envio, alerta.regra_id, alerta.campo) is not None


def test_se_o_modelo_insistir_a_fala_fixa_diz_que_nada_mudou(conexao):
    envio, alerta = envio_com_alerta(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, alerta.regra_id, alerta.linha,
                                            "posso confirmar?", cliente=ia_em_sequencia(CONFIRMAR),
                                            campo=alerta.campo)
    assert resposta["mensagem"] == assistente_correcao.FALA_DA_PERGUNTA and resposta["aplicado"] is None


def test_pergunta_com_um_valor_tambem_nao_muda_o_dado(conexao):
    envio = envio_com_estado_civil_errado(conexao)
    linha_da_ana = achado_em_aberto(conexao, envio, FORA_DA_LISTA, "estado_civil").linha
    corrigir = {"acao": "corrigir", "mensagem": "Vou corrigir.", "valor": "Solteiro"}
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, FORA_DA_LISTA, linha_da_ana,
                                            "seria Solteiro?", cliente=ia_em_sequencia(corrigir),
                                            campo="estado_civil")
    assert resposta["aplicado"] is None and correcoes.listar(conexao, envio) == []


def test_sem_pergunta_a_confirmacao_continua_valendo(conexao):
    envio, alerta = envio_com_alerta(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, alerta.regra_id, alerta.linha,
                                            "Está certo assim, é o salário do diretor",
                                            cliente=ia_em_sequencia(CONFIRMAR), campo=alerta.campo)
    assert resposta["aplicado"] is not None and resposta["mensagem"].startswith("Pronto:")


@pytest.mark.parametrize("mensagem, e_pergunta", [
    ("o que é isso?", True), ("é o CNPJ da matriz? acho que sim", True), ("¿qué es?", True),
    ("o CPF certo é 529.982.247-25", False), ("Sim, é do nosso grupo", False),
])
def test_o_que_conta_como_pergunta(mensagem, e_pergunta):
    assert assistente_correcao.e_pergunta(mensagem) is e_pergunta


# ---------------- Usar o que o sistema já sabe da empresa ----------------

def envio_sem_os_dados_da_empresa(conexao) -> str:
    """Três pessoas, sem o CNPJ do empregador e sem o endereço comercial (colunas que o arquivo não trouxe)."""
    return enviar(conexao, "Nome;CPF;Estado civil",
                  [f"Ana Lima;{CPFS[0]};Casado", f"Bia Souza;{CPFS[1]};Casado", f"Caio Reis;{CPFS[2]};Casado"],
                  {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"})


def test_o_cadastro_da_empresa_da_o_cnpj_e_o_endereco_sem_inventar(conexao):
    valores = dados_da_empresa_no_envio.valores_do_cadastro(conexao, EMPRESA)
    # A Aurora: o CNPJ, a rua e o número (do texto do endereço), a cidade e a UF (das colunas próprias)
    assert valores["cnpj_empregador"] == "10433218000193"
    assert valores["logradouro_comercial"] == "Avenida Industrial" and valores["numero_comercial"] == "4338"
    assert (valores["municipio_comercial"], valores["uf_comercial"]) == ("Campinas", "SP")
    # O cadastro não tem o CEP nem o bairro: nada inventado
    assert "cep_comercial" not in valores and "bairro_comercial" not in valores
    # Outra empresa, outro cadastro (a regra não é da Aurora)
    assert dados_da_empresa_no_envio.valores_do_cadastro(conexao, "EMP002")["uf_comercial"] == "MG"
    assert dados_da_empresa_no_envio.valores_do_cadastro(conexao, "EMP999") == {}


@pytest.mark.parametrize("mensagem, campo, grupo", [
    ("Usar o CNPJ da empresa (10.433.218/0001-93)", "cnpj_empregador", "cnpj"),   # o botão
    ("é o CNPJ da nossa empresa", "cnpj_empregador", "cnpj"),                      # o caso real
    ("pode usar o nosso CNPJ para todos", "cnpj_empregador", "cnpj"),              # outras palavras
    ("O ENDEREÇO DA EMPRESA serve para todo mundo", "bairro_comercial", "endereco"),
    ("usa o endereco da nossa empresa", "logradouro_comercial", "endereco"),       # sem acento
    ("é o CNPJ da empresa?", "cnpj_empregador", None),                              # pergunta
    ("não é o CNPJ da empresa, é de uma filial", "cnpj_empregador", None),         # negação
    ("é o endereço da empresa", "cnpj_empregador", None),                           # outro cartão
    ("é o CNPJ da empresa", "cpf", None),                                            # campo de cada pessoa
])
def test_a_frase_que_pede_o_dado_da_empresa(mensagem, campo, grupo):
    assert dados_da_empresa_no_envio.grupo_pedido(mensagem, campo) == grupo


def test_os_cartoes_oferecem_o_dado_que_o_cadastro_sabe(conexao):
    envio_sem_os_dados_da_empresa(conexao)
    sugestoes_por_campo = {}
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == SEM_COLUNA:
            sugestoes_por_campo[pendencia["campo"]] = [sugestao["texto"] for sugestao in pendencia["sugestoes"]]
    assert "Usar o CNPJ da empresa (10.433.218/0001-93)" in sugestoes_por_campo.get("cnpj_empregador", [])
    # Um cartão do endereço que o cadastro sabe oferece o endereço inteiro
    for campo in ("logradouro_comercial", "municipio_comercial"):
        if campo in sugestoes_por_campo:
            assert sugestoes_por_campo[campo][0] == "Usar o endereço da empresa (Avenida Industrial, 4338, Campinas/SP)"
    # O cartão de um pedaço que o cadastro não tem não ganha o botão (ele não resolveria)
    for sugestao in sugestoes_por_campo.get("cep_comercial", []):
        assert not sugestao.startswith("Usar o endereço")


def test_um_clique_preenche_o_cnpj_de_todos(conexao):
    envio = envio_sem_os_dados_da_empresa(conexao)
    if achado_em_aberto(conexao, envio, SEM_COLUNA, "cnpj_empregador") is None:
        pytest.skip("o CNPJ do empregador não é obrigatório no layout vigente")
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, SEM_COLUNA, None,
                                            "Usar o CNPJ da empresa (10.433.218/0001-93)", campo="cnpj_empregador")
    assert resposta["mensagem"] == 'Pronto: usei o CNPJ da empresa em 3 funcionários: CNPJ "10.433.218/0001-93".'
    assert resposta["resolvida"] is True and resposta["aplicado"]["desfazer"]["tipo"] == "dados_da_empresa"
    # O Desfazer volta todos
    desfeito = assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, "dados_da_empresa",
                                           resposta["aplicado"]["desfazer"]["id"])
    assert desfeito["resumo"] == "Desfiz: 3 funcionários sem o dado da empresa de novo."
    assert achado_em_aberto(conexao, envio, SEM_COLUNA, "cnpj_empregador") is not None


def test_o_endereco_sai_inteiro_numa_resposta_so(conexao):
    envio = envio_sem_os_dados_da_empresa(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, SEM_COLUNA, None,
                                            "é o endereço da nossa empresa", campo="municipio_comercial")
    assert resposta["mensagem"].startswith("Pronto: usei o endereço da empresa em 3 funcionários: ")
    assert 'rua "Avenida Industrial"' in resposta["mensagem"] and 'UF "SP"' in resposta["mensagem"]
    # Os pedaços que o cadastro sabe saíram todos juntos
    for campo in ("logradouro_comercial", "numero_comercial", "municipio_comercial", "uf_comercial"):
        assert achado_em_aberto(conexao, envio, SEM_COLUNA, campo) is None
    # Um Desfazer volta o endereço inteiro
    assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, "dados_da_empresa",
                                resposta["aplicado"]["desfazer"]["id"])
    registros = correcoes.dados_atuais(conexao, envio).registros
    assert registros[0].get("logradouro_comercial") in (None, "")
    assert registros[0].get("uf_comercial") in (None, "")


# ---------------- Nunca "Tudo em dia" com o envio parado nas colunas ----------------

def test_o_envio_que_voltou_para_as_colunas_aparece_como_parado(conexao):
    envio = envio_com_estado_civil_errado(conexao)
    linha_da_ana = achado_em_aberto(conexao, envio, FORA_DA_LISTA, "estado_civil").linha
    assert acompanhamento.envios_parados_nas_colunas(conexao, EMPRESA) == []
    # A IA pede para reler a coluna do estado civil: o envio volta para a conferência das colunas
    reler = {"acao": "solicitar_remapeamento", "mensagem": "Vou pedir para reler a coluna.",
             "coluna": "Estado civil", "justificativa": "os valores parecem de outra coluna"}
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, FORA_DA_LISTA, linha_da_ana,
                                            "essa coluna está trocada", cliente=ia_em_sequencia(reler),
                                            campo="estado_civil")
    assert resposta["remapeado"] is True
    assert resposta["mensagem"].endswith(assistente_na_tela.FALA_DO_ENVIO_DE_VOLTA_AS_COLUNAS)
    assert processamentos.obter(conexao, envio).status == EstadoProcessamento.MAPEAMENTO_PENDENTE
    parados = acompanhamento.envios_parados_nas_colunas(conexao, EMPRESA)
    assert len(parados) == 1 and parados[0]["processamento_id"] == envio
    assert parados[0]["titulo"] == "Voltou para a leitura das colunas" and parados[0]["voltou_da_conversa"] is True


def test_o_envio_novo_que_espera_as_colunas_tambem_conta(conexao):
    # Enviado e ainda não aceito: não voltou de nenhuma conversa, mas espera a empresa
    conteudo = f"Nome;CPF\nAna Lima;{CPFS[0]}\n".encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, conteudo, "novo.csv", busca=busca_falsa)
    parados = acompanhamento.envios_parados_nas_colunas(conexao, EMPRESA)
    assert [parado["processamento_id"] for parado in parados] == [leitura["processamento_id"]]
    assert parados[0]["titulo"] == "Esperando você conferir as colunas"
    # A outra empresa não vê
    assert acompanhamento.envios_parados_nas_colunas(conexao, "EMP003") == []


@pytest.fixture
def api_com_envio_parado(tmp_path, monkeypatch):
    """A API apontada para um banco só deste teste, com um envio da Aurora esperando as colunas."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    conteudo = f"Nome;CPF\nAna Lima;{CPFS[0]}\n".encode("utf-8")
    cadastro.enviar_arquivo(conexao_do_teste, EMPRESA, LOGIN, conteudo, "novo.csv", busca=busca_falsa)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, EMPRESA)
    auth.cadastrar_usuario(conexao_do_teste, "rh.brisa", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP003")
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO, None)
    conexao_do_teste.close()


def entrar(login: str) -> TestClient:
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


def test_a_rota_dos_envios_parados_e_so_da_empresa_dona(api_com_envio_parado):
    endereco = "/api/empresa/envios-parados-nas-colunas"
    assert TestClient(aplicacao).get(endereco).status_code == 401
    assert entrar("especialista").get(endereco).status_code == 403
    assert entrar("rh.brisa").get(endereco).json() == []
    resposta = entrar("rh.aurora").get(endereco)
    assert resposta.status_code == 200 and len(resposta.json()) == 1
