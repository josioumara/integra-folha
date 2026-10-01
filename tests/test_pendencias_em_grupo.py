"""Testes das pendências em grupo (ADR-120).

O que estes testes provam (com a IA simulada, sem custo):
- várias pessoas do mesmo arquivo com o MESMO valor fora da lista viram um grupo: a lista continua com uma pendência
  por pessoa (os números das telas não mudam), e todas apontam para o mesmo grupo, com UMA pergunta ("3 pessoas...")
  e as respostas rápidas para todas ('Sim, use "Casado" para as 3');
- maiúsculas e espaços nas pontas não separam o grupo; uma pessoa sozinha, ou um campo livre (salário), não agrupa;
- a resposta no cartão do grupo vale para todas: uma troca por pessoa, ligadas como um lote, na trilha sem valor
  pessoal; o Desfazer volta o grupo inteiro e as pendências voltam;
- no cartão do grupo, "não cadastrar" não muda nada (é pessoa a pessoa, pelo "Responder uma a uma");
- fora do cartão do grupo, a mesma resposta vale só para a pessoa;
- a conferência do Cadastrar marca o mesmo grupo;
- a pergunta do grupo escrita pela IA só passa na conferência com o número de pessoas.
"""
from types import SimpleNamespace

import pytest

from agents import redator_de_perguntas
from services import (acompanhamento, assistente_na_tela, auditoria, banco, cadastro, correcoes,
                      pendencias_em_grupo, validador)
from tests.apoio_do_parametro import marcar_como_obrigatorios  # o estado civil é opcional no layout (ADR-143)
from tests.test_correcao import busca_falsa

# A empresa e quem escreve na conversa
EMPRESA = "EMP001"
LOGIN = "rh.aurora"
# As colunas do arquivo e o campo de cada uma (o aceite da empresa)
ESCOLHAS_DO_ARQUIVO = {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"}


def cpf_valido(nove_digitos: str) -> str:
    """Completa 9 dígitos com os dois dígitos verificadores do CPF. Ex.: "529982247" → "52998224725"."""
    digitos = nove_digitos
    for tamanho in (9, 10):
        # Cada dígito vezes o peso (10, 9, 8... no primeiro; 11, 10, 9... no segundo)
        soma = 0
        for posicao in range(tamanho):
            soma = soma + int(digitos[posicao]) * (tamanho + 1 - posicao)
        resto = (soma * 10) % 11
        digitos = digitos + str(resto % 10)
    return digitos


def arquivo_com_casdo() -> bytes:
    """Quatro pessoas: três com "Casdo" (duas escritas de jeitos diferentes) e uma com "Noiva" (sozinha)."""
    linhas = ["Nome;CPF;Estado civil",
              f"Ana Lima;{cpf_valido('529982247')};Casdo",
              f"Bia Souza;{cpf_valido('111444777')};casdo ",
              f"Caio Reis;{cpf_valido('123456789')};Casdo",
              f"Davi Melo;{cpf_valido('987654321')};Noiva"]
    return ("\n".join(linhas) + "\n").encode("utf-8")


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture(autouse=True)
def usar_busca_falsa(monkeypatch):
    """Nenhum uso do RAG depende do índice nem do modelo de embeddings."""
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)


@pytest.fixture
def envio(conexao) -> str:
    """O arquivo enviado e aceito pela Aurora (a padronização e a validação rodam no aceite). Devolve o envio.

    O estado civil é opcional no layout, e um campo opcional não abre pendência (ADR-143): o parâmetro deste banco de
    teste o marca como obrigatório, para as pendências em grupo continuarem testadas.
    """
    marcar_como_obrigatorios(conexao, "estado_civil")
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, arquivo_com_casdo(), "estado_civil.csv",
                                      busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS_DO_ARQUIVO,
                                busca=busca_falsa)
    return leitura["processamento_id"]


def pendencias_do_estado_civil(conexao) -> list[dict]:
    """As pendências de valor fora da lista do estado civil, como Acompanhar recebe."""
    pendencias = []
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == "VALOR_NAO_CONVERTIDO" and pendencia["campo"] == "estado_civil":
            pendencias.append(pendencia)
    return pendencias


def valores_em_aberto(conexao, processamento_id: str) -> list[str]:
    """Os valores do estado civil que o Validador ainda aponta (sem maiúsculas e sem espaços nas pontas)."""
    valores = []
    for achado in validador.obter(conexao, processamento_id).achados:
        if achado.regra_id == "VALOR_NAO_CONVERTIDO" and achado.campo == "estado_civil":
            valores.append(achado.valor.strip().casefold())
    return sorted(valores)


def representante(conexao) -> dict:
    """A pendência que representa o grupo (a primeira pessoa dele)."""
    for pendencia in pendencias_do_estado_civil(conexao):
        grupo = pendencia["grupo"]
        if grupo and pendencia["linha"] == grupo["linha_do_representante"]:
            return pendencia
    raise AssertionError("o envio devia ter um grupo")


def eventos(conexao, processamento_id: str, tipo: str) -> list[dict]:
    """Os detalhes dos eventos de um tipo na trilha do envio."""
    detalhes = []
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == tipo:
            detalhes.append(evento["detalhe"])
    return detalhes


# ---------------- O grupo na lista ----------------

def test_o_mesmo_valor_fora_da_lista_vira_um_grupo(conexao, envio):
    pendencias = pendencias_do_estado_civil(conexao)
    # A lista continua com uma pendência por pessoa (os números das telas não mudam)
    assert len(pendencias) == 4
    com_grupo = [pendencia for pendencia in pendencias if pendencia["grupo"]]
    sozinha = [pendencia for pendencia in pendencias if not pendencia["grupo"]]
    # "Casdo" e "casdo " são o mesmo valor: as três pessoas no mesmo grupo; "Noiva" fica sozinha
    assert len(com_grupo) == 3 and len(sozinha) == 1 and sozinha[0]["valor_lido"] == "Noiva"
    chaves = {pendencia["grupo"]["chave"] for pendencia in com_grupo}
    assert len(chaves) == 1
    grupo = com_grupo[0]["grupo"]
    assert grupo["quantidade"] == 3 and grupo["palpite"] == "Casado"
    # Uma pergunta só, com o número, o valor lido e o palpite, e sem nome de pessoa
    assert grupo["pergunta"].startswith("3 pessoas deste arquivo")
    assert '"Casdo"' in grupo["pergunta"] and '"Casado" para todas' in grupo["pergunta"]
    assert "Ana" not in grupo["pergunta"]
    # A primeira resposta rápida aceita o palpite para todas; as outras são os valores da lista
    assert grupo["sugestoes"][0] == {"texto": 'Sim, use "Casado" para as 3', "envia": True}
    textos = [sugestao["texto"] for sugestao in grupo["sugestoes"]]
    assert "Solteiro" in textos and "Casado" not in textos


def test_campo_livre_e_pessoa_sozinha_nao_agrupam():
    dominios = {"estado_civil": {"valores": ["Casado"]}}
    lista = SimpleNamespace(regra_id="VALOR_NAO_CONVERTIDO", linha=2, campo="estado_civil", valor="Casdo")
    salario = SimpleNamespace(regra_id="VALOR_NAO_CONVERTIDO", linha=2, campo="valor_renda", valor="a combinar")
    arquivo_inteiro = SimpleNamespace(regra_id="VALOR_NAO_CONVERTIDO", linha=None, campo="estado_civil", valor="X")
    outra_regra = SimpleNamespace(regra_id="CPF_INVALIDO", linha=2, campo="estado_civil", valor="Casdo")
    assert pendencias_em_grupo.pode_agrupar(lista, dominios)
    assert not pendencias_em_grupo.pode_agrupar(salario, dominios)
    assert not pendencias_em_grupo.pode_agrupar(arquivo_inteiro, dominios)
    assert not pendencias_em_grupo.pode_agrupar(outra_regra, dominios)
    assert pendencias_em_grupo.MINIMO_PARA_AGRUPAR == 2


# ---------------- A resposta no cartão do grupo ----------------

def test_a_resposta_no_grupo_vale_para_todas_e_o_desfazer_volta_o_grupo(conexao, envio):
    pendencia = representante(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, pendencia["regra_id"],
                                            pendencia["linha"], 'Sim, use "Casado" para as 3', em_grupo=True)
    # As três trocadas de uma vez, com o resumo e o Desfazer do grupo
    assert resposta["resolvida"] and resposta["confirmacao"] is None
    assert resposta["mensagem"] == ('Pronto: troquei a informação "Estado civil" de "Casdo" para "Casado" em 3 '
                                    "pessoas: Ana, Bia e Caio.")
    assert resposta["aplicado"]["resumo"] == "Estado civil: Casdo → Casado em 3 pessoas"
    assert resposta["aplicado"]["desfazer"]["tipo"] == "grupo"
    assert valores_em_aberto(conexao, envio) == ["noiva"]
    # Uma correção por pessoa, todas APLICADAS, com quem pediu e a frase dela como motivo
    aplicadas = correcoes.listar(conexao, envio, "APLICADA")
    assert len(aplicadas) == 3
    for correcao in aplicadas:
        assert correcao.depois == "Casado" and correcao.aprovada_por == LOGIN
        assert "para as 3" in correcao.motivo
    # Na trilha: o campo e a quantidade, sem nenhum valor pessoal
    assert eventos(conexao, envio, "CORRECAO_EM_GRUPO") == [{"campo": "estado_civil", "quantidade": 3}]
    # O Desfazer volta as três, e as pendências voltam
    desfeito = assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, "grupo",
                                           resposta["aplicado"]["desfazer"]["id"])
    assert desfeito["resumo"] == "Desfiz a troca: 3 pessoas com o valor do arquivo de novo."
    assert valores_em_aberto(conexao, envio) == ["casdo", "casdo", "casdo", "noiva"]
    assert eventos(conexao, envio, "CORRECAO_EM_GRUPO_DESFEITA") == [{"campo": "estado_civil", "quantidade": 3}]
    # Desfazer de novo é recusado
    with pytest.raises(ValueError):
        assistente_na_tela.desfazer(conexao, EMPRESA, LOGIN, envio, "grupo", resposta["aplicado"]["desfazer"]["id"])


def test_um_valor_da_lista_no_grupo_tambem_vale_para_todas(conexao, envio):
    pendencia = representante(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, pendencia["regra_id"],
                                            pendencia["linha"], "Solteiro", em_grupo=True)
    assert resposta["aplicado"]["resumo"].endswith("em 3 pessoas")
    assert valores_em_aberto(conexao, envio) == ["noiva"]


def test_nao_cadastrar_no_cartao_do_grupo_nao_muda_nada(conexao, envio):
    pendencia = representante(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, pendencia["regra_id"],
                                            pendencia["linha"], "não cadastrar esta pessoa", em_grupo=True)
    assert resposta["aplicado"] is None and resposta["confirmacao"] is None and not resposta["resolvida"]
    assert "Responder uma a uma" in resposta["mensagem"]
    # Nada mudou nem ficou esperando confirmação
    assert correcoes.listar(conexao, envio) == []
    assert valores_em_aberto(conexao, envio) == ["casdo", "casdo", "casdo", "noiva"]


def test_fora_do_cartao_do_grupo_a_resposta_vale_so_para_a_pessoa(conexao, envio):
    pendencia = representante(conexao)
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, pendencia["regra_id"],
                                            pendencia["linha"], 'Sim, use "Casado"')
    assert resposta["aplicado"]["desfazer"]["tipo"] == "correcao"
    assert len(correcoes.listar(conexao, envio, "APLICADA")) == 1
    # As outras duas continuam num grupo, agora de 2
    grupos = {pendencia["grupo"]["chave"]: pendencia["grupo"]["quantidade"]
              for pendencia in pendencias_do_estado_civil(conexao) if pendencia["grupo"]}
    assert list(grupos.values()) == [2]


def test_o_grupo_que_se_desfez_responde_so_pela_pessoa(conexao, envio):
    # Duas das três resolvidas uma a uma: a terceira fica sozinha, e o "em grupo" vale só para ela
    pendencias = [pendencia for pendencia in pendencias_do_estado_civil(conexao) if pendencia["grupo"]]
    for pendencia in pendencias[1:]:
        assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, pendencia["regra_id"], pendencia["linha"],
                                     "Casado")
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, pendencias[0]["regra_id"],
                                            pendencias[0]["linha"], "Casado", em_grupo=True)
    assert resposta["aplicado"]["desfazer"]["tipo"] == "correcao"
    assert valores_em_aberto(conexao, envio) == ["noiva"]


# ---------------- A conferência do Cadastrar e a pergunta escrita pela IA ----------------

def test_a_conferencia_do_cadastrar_marca_o_mesmo_grupo(conexao, envio):
    lista = cadastro.lista_para_conferir(conexao, EMPRESA, envio)
    quantidades = []
    for linha in lista["linhas"]:
        for pendencia in linha["pendencias"]:
            if pendencia["grupo"]:
                quantidades.append(pendencia["grupo"]["quantidade"])
    assert quantidades == [3, 3, 3]


def test_a_pergunta_do_grupo_escrita_pela_ia_precisa_do_numero():
    pendencia = redator_de_perguntas.PendenciaParaEscrever(
        id="x", regra="VALOR_NAO_CONVERTIDO", gravidade="BLOQUEANTE", pessoa="", informacao="Estado civil",
        valor_lido="Casdo", o_que_aconteceu="Valor fora da lista.", tipo="corrigir", palpite="Casado",
        quantidade_de_pessoas=23)
    sem_o_numero = 'Várias pessoas vieram com "Casdo" no estado civil. Posso usar "Casado" para todas?'
    com_o_numero = '23 pessoas vieram com "Casdo" no estado civil. Posso usar "Casado" para todas?'
    assert not redator_de_perguntas.conferir_pergunta(sem_o_numero, pendencia)
    assert redator_de_perguntas.conferir_pergunta(com_o_numero, pendencia)
    # A IA simulada (modo MOCK) escreve a frase de reserva do grupo, que passa na conferência
    resposta = redator_de_perguntas.simular_perguntas(redator_de_perguntas.montar_pedido([pendencia]))
    assert "23 pessoas" in resposta


# ---------------- Travas contra misturar pendências ----------------

def test_dois_lotes_iguais_no_mesmo_segundo_se_desfazem_separados(conexao, envio):
    """Duas trocas em grupo no mesmo campo, com a mesma resposta, uma logo depois da outra: o Desfazer de uma não
    desfaz a outra (a hora do lote tem microssegundos)."""
    linhas_do_casdo = []
    linha_da_noiva = None
    for pendencia in pendencias_do_estado_civil(conexao):
        if pendencia["grupo"]:
            linhas_do_casdo.append(pendencia["linha"])
        else:
            linha_da_noiva = pendencia["linha"]
    motivo = "Pedido na conversa com a IA: Casado"
    primeiro_lote = correcoes.trocar_em_varias_linhas(conexao, envio, EMPRESA, linhas_do_casdo, "estado_civil",
                                                      "Casado", motivo, LOGIN)
    correcoes.trocar_em_varias_linhas(conexao, envio, EMPRESA, [linha_da_noiva], "estado_civil", "Casado", motivo,
                                      LOGIN)
    # Desfazer o primeiro lote volta só as três pessoas dele
    assert correcoes.desfazer_lote(conexao, envio, EMPRESA, primeiro_lote[0], LOGIN) == 3
    assert valores_em_aberto(conexao, envio) == ["casdo", "casdo", "casdo"]


def test_valor_nao_entendido_nao_se_confirma(conexao, envio):
    """Um valor que o sistema não entendeu não se confirma "como está". Desde a ADR-143, ele é sempre BLOQUEANTE: o de
    um campo opcional nem vira pendência, e aqui o estado civil está obrigatório no parâmetro do teste. A conversa pede
    o valor certo, nada muda, e o serviço de confirmar recusa."""
    noiva = None
    for pendencia in pendencias_do_estado_civil(conexao):
        if not pendencia["grupo"]:
            noiva = pendencia
    assert noiva["severidade"] == validador.BLOQUEANTE
    # Pela conversa: o agente pede o valor certo, e nada muda
    resposta = assistente_na_tela.conversar(conexao, EMPRESA, LOGIN, envio, noiva["regra_id"], noiva["linha"],
                                            "Está certo assim", campo=noiva["campo"])
    assert resposta["aplicado"] is None and not resposta["resolvida"]
    assert "valor certo" in resposta["mensagem"]
    # Pelo serviço (as rotas antigas de confirmar): recusado
    with pytest.raises(ValueError):
        validador.justificar_alerta(conexao, envio, EMPRESA, noiva["regra_id"], noiva["linha"], "CONFIRMADO",
                                    "Está certo", LOGIN)
    assert "noiva" in valores_em_aberto(conexao, envio)
