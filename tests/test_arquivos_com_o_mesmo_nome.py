"""Testes dos arquivos diferentes com o mesmo nome (ADR-120).

O caso: a empresa enviou dois arquivos diferentes chamados "estado_civil.csv", com pessoas em comum. A pendência do
segundo dizia "também está no arquivo estado_civil.csv", o próprio nome, e parecia falar do mesmo arquivo.

O que estes testes provam (sem IA):
- nomes repetidos ganham a versão pela ordem de chegada ("(v1)", "(v2)"), sem diferença de maiúsculas; um nome que não
  se repete fica como está;
- as pendências e os filtros recebem o nome com a versão, e a mensagem "também está em outro arquivo" cita a outra
  versão.
"""
from services import acompanhamento, cadastro, processamentos
from tests.test_correcao import busca_falsa
from tests.test_pendencias_em_grupo import (EMPRESA, ESCOLHAS_DO_ARQUIVO, LOGIN, arquivo_com_casdo,  # noqa: F401
                                            conexao, cpf_valido, usar_busca_falsa)


def enviar(conexao, conteudo: bytes, nome: str) -> str:
    """Envia e aceita um arquivo da Aurora. Devolve o envio."""
    leitura = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, conteudo, nome, busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, EMPRESA, LOGIN, leitura["processamento_id"], ESCOLHAS_DO_ARQUIVO,
                                busca=busca_falsa)
    return leitura["processamento_id"]


def segundo_arquivo() -> bytes:
    """Outro arquivo (conteúdo diferente) com uma pessoa do primeiro (Ana Lima) e uma pessoa nova."""
    linhas = ["Nome;CPF;Estado civil",
              f"Ana Lima;{cpf_valido('529982247')};Casado",
              f"Eva Nunes;{cpf_valido('246813579')};Solteiro"]
    return ("\n".join(linhas) + "\n").encode("utf-8")


def terceiro_arquivo() -> bytes:
    """Um arquivo com outro nome e só uma pessoa nova."""
    return ("Nome;CPF;Estado civil\n" f"Gil Rocha;{cpf_valido('135792468')};Casado\n").encode("utf-8")


def test_nomes_repetidos_ganham_a_versao_pela_ordem_de_chegada(conexao):
    primeiro = enviar(conexao, arquivo_com_casdo(), "estado_civil.csv")
    segundo = enviar(conexao, segundo_arquivo(), "ESTADO_CIVIL.csv")
    outro = enviar(conexao, terceiro_arquivo(), "inclusao.csv")
    nomes = processamentos.nomes_na_tela(conexao, EMPRESA)
    assert nomes[primeiro] == "estado_civil.csv (v1)"
    assert nomes[segundo] == "ESTADO_CIVIL.csv (v2)"
    assert nomes[outro] == "inclusao.csv"


def test_as_pendencias_e_a_mensagem_do_outro_arquivo_citam_a_versao(conexao):
    primeiro = enviar(conexao, arquivo_com_casdo(), "estado_civil.csv")
    segundo = enviar(conexao, segundo_arquivo(), "estado_civil.csv")
    nomes_por_envio = {}
    em_outro_arquivo = []
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        nomes_por_envio[pendencia["processamento_id"]] = pendencia["nome_arquivo"]
        if pendencia["regra_id"] == "PESSOA_EM_OUTRO_ENVIO":
            em_outro_arquivo.append(pendencia)
    assert nomes_por_envio[primeiro] == "estado_civil.csv (v1)"
    assert nomes_por_envio[segundo] == "estado_civil.csv (v2)"
    # A Ana está nos dois: o cartão de cada envio cita a OUTRA versão, nunca a própria
    citacoes = {}
    for pendencia in em_outro_arquivo:
        citacoes[pendencia["processamento_id"]] = pendencia["problema_do_cartao"]
    assert citacoes[segundo].endswith('("estado_civil.csv (v1)")')
    assert citacoes[primeiro].endswith('("estado_civil.csv (v2)")')


def test_o_envio_avisa_que_o_nome_ja_foi_usado(conexao):
    leitura_do_primeiro = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, arquivo_com_casdo(), "estado_civil.csv",
                                                  busca=busca_falsa)
    # O primeiro, sozinho: nada a avisar
    assert leitura_do_primeiro["aviso_do_nome"] is None
    leitura_do_segundo = cadastro.enviar_arquivo(conexao, EMPRESA, LOGIN, segundo_arquivo(), "estado_civil.csv",
                                                 busca=busca_falsa)
    assert leitura_do_segundo["aviso_do_nome"] == (
        'Você já enviou outro arquivo com o nome "estado_civil.csv". Para não confundir, este aparece como '
        '"estado_civil.csv (v2)" nas pendências e na lista para o banco.')
    # Reaberto no Cadastrar, o primeiro também avisa, com a versão dele
    primeiro_de_novo = cadastro.leitura_do_envio(conexao, EMPRESA, leitura_do_primeiro["processamento_id"])
    assert primeiro_de_novo["aviso_do_nome"].endswith('"estado_civil.csv (v1)" nas pendências e na lista para o banco.')


def test_a_pessoa_em_outro_arquivo_nao_marca_o_cpf(conexao):
    """Um cartão, um problema: "a pessoa também está em outro arquivo" é da pessoa inteira. A ficha não destaca o CPF
    nem o marca como "também com pendência", e o cartão não pede destaque de nenhum campo."""
    from services import ficha_da_pendencia
    enviar(conexao, arquivo_com_casdo(), "estado_civil.csv")
    segundo = enviar(conexao, segundo_arquivo(), "estado_civil.csv")
    da_ana = None
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, EMPRESA):
        if pendencia["regra_id"] == "PESSOA_EM_OUTRO_ENVIO" and pendencia["processamento_id"] == segundo:
            da_ana = pendencia
    assert da_ana is not None and da_ana["campo"] == "cpf"
    # O cartão não pede destaque (o problema não é o CPF)
    assert da_ana["campo_em_revisao"] is None
    assert da_ana["titulo_do_cartao"] == "Ajuste no cadastro de Ana Lima"
    # Na ficha, o CPF aparece sem pendência
    ficha = ficha_da_pendencia.ficha_da_linha(conexao, EMPRESA, LOGIN, segundo, da_ana["linha"])
    for grupo in ficha["grupos"]:
        for campo in grupo["campos"]:
            if campo["campo"] == "cpf":
                assert campo["com_pendencia"] is False


def test_a_lista_de_envios_mostra_o_nome_com_a_versao_mesmo_do_descartado(conexao):
    """O defeito: a lista de envios não mostrava o nome dos arquivos, e a v1 de um arquivo com o mesmo nome da v2 não
    aparecia em lugar nenhum. A lista de envios traz o nome com a versão, e a v1 descartada continua nela."""
    primeiro = enviar(conexao, arquivo_com_casdo(), "estado_civil.csv")
    cadastro.descartar(conexao, EMPRESA, primeiro, LOGIN)
    segundo = enviar(conexao, segundo_arquivo(), "estado_civil.csv")
    pagina = acompanhamento.pagina_de_envios(conexao, EMPRESA, 0, 5)
    nome_e_situacao = {}
    for envio in pagina["envios"]:
        nome_e_situacao[envio["processamento_id"]] = (envio["nome_arquivo"], envio["situacao"])
    assert nome_e_situacao[segundo][0] == "estado_civil.csv (v2)"
    assert nome_e_situacao[primeiro] == ("estado_civil.csv (v1)", "Descartado")
    # A lista inteira (usada na Início) traz o mesmo nome
    nomes = [envio["nome_arquivo"] for envio in acompanhamento.envios_da_empresa(conexao, EMPRESA)]
    assert nomes == ["estado_civil.csv (v2)", "estado_civil.csv (v1)"]
