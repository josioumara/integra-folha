"""Roteiro: arquivos diferentes com o mesmo nome aparecem como "(v1)" e "(v2)" (ADR-120).

O caso: a empresa enviou dois arquivos diferentes chamados "folha_setembro.csv", com uma pessoa em comum (Ana Lima).
Antes, a pendência dizia "também está no arquivo folha_setembro.csv" dentro do próprio folha_setembro.csv, e a lista de
envios nem mostrava o nome dos arquivos, então a v1 não aparecia em lugar nenhum.

O que ele confere (com a IA simulada, sem custo):
- a lista de envios mostra o nome de cada arquivo no título, com a versão: "folha_setembro.csv (v2)" em cima (o mais
  recente) e "folha_setembro.csv (v1)" embaixo;
- o filtro de arquivos das pendências tem as duas versões, com quantas pendências cada uma tem, no singular ou no
  plural certo;
- o cartão "a pessoa também está em outro arquivo" da v2 cita a v1, e o da v1 cita a v2 (nunca o próprio arquivo).
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = ("Arquivos com o mesmo nome: (v1) e (v2) na lista de envios, no filtro e no cartão da pessoa em outro "
             "arquivo")
# O nome repetido dos dois arquivos
NOME_DO_ARQUIVO = "folha_setembro.csv"
# As pessoas (CPFs válidos e inventados): Ana está nos dois arquivos
PRIMEIRO_ARQUIVO = [("Ana Lima", "52998224725", "Casado"), ("Bia Souza", "11144477735", "Solteiro")]
SEGUNDO_ARQUIVO = [("Ana Lima", "52998224725", "Casado"), ("Caio Reis", "12345678909", "Solteiro")]


def conteudo_do_arquivo(pessoas: list[tuple]) -> bytes:
    """O CSV de um arquivo: nome, CPF e estado civil de cada pessoa."""
    linhas = ["Nome;CPF;Estado civil"]
    for nome, cpf, estado_civil in pessoas:
        linhas.append(f"{nome};{cpf};{estado_civil}")
    return ("\n".join(linhas) + "\n").encode("utf-8")


def preparar() -> dict:
    """Os dois envios da Aurora com o mesmo nome, com as colunas aceitas. Devolve {v1, v2} (os envios)."""
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    escolhas = {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"}
    envios = []
    for pessoas in (PRIMEIRO_ARQUIVO, SEGUNDO_ARQUIVO):
        leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo_do_arquivo(pessoas),
                                          NOME_DO_ARQUIVO, busca=busca_falsa)
        cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], escolhas,
                                    busca=busca_falsa)
        envios.append(leitura["processamento_id"])
    conexao.close()
    return {"v1": envios[0], "v2": envios[1]}


def conferir_a_lista_de_envios(aba, conferir) -> None:
    """A lista de envios: o nome de cada arquivo no título, com a versão, do mais recente para o mais antigo."""
    titulos = aba.locator("[data-lista-envios] [data-envio] [data-nome-do-arquivo]")
    titulos.nth(1).wait_for(timeout=30000)
    nomes = [titulos.nth(posicao).inner_text() for posicao in range(titulos.count())]
    conferir(f"a lista de envios mostra o nome com a versão, v2 em cima (na tela: {nomes})",
             nomes[:2] == [f"{NOME_DO_ARQUIVO} (v2)", f"{NOME_DO_ARQUIVO} (v1)"])
    linha_de_baixo = aba.locator("[data-lista-envios] [data-envio] .envio-arquivos").first.inner_text()
    conferir(f"embaixo do nome, o tipo, a data, quantos e quem (na tela: {linha_de_baixo})",
             re.match(r"(Carga inicial|Inclusão) · \d{2}/\d{2}/\d{4} · .+ · enviado por ", linha_de_baixo) is not None)
    aba.locator("[data-lista-envios]").screenshot(path="storage/painel/envios_com_o_nome_do_arquivo.png")


def conferir_o_filtro_e_os_cartoes(aba, dados: dict, conferir) -> None:
    """O filtro de arquivos com as duas versões e o cartão da pessoa em outro arquivo citando a outra versão."""
    filtro = aba.locator("[data-filtro-arquivo-pendencias]")
    aba.wait_for_function("() => document.querySelector('[data-filtro-arquivo-pendencias]').options.length >= 3",
                          timeout=30000)
    opcoes = filtro.locator("option").all_inner_texts()
    tem_as_duas = (any(opcao.startswith(f"{NOME_DO_ARQUIVO} (v1) · ") for opcao in opcoes)
                   and any(opcao.startswith(f"{NOME_DO_ARQUIVO} (v2) · ") for opcao in opcoes))
    plural_certo = all(re.search(r" · (1 pendência|\d+ pendências)$", opcao) for opcao in opcoes[1:])
    conferir(f"o filtro de arquivos tem as duas versões, com o plural certo (na tela: {opcoes})",
             tem_as_duas and plural_certo)
    # A v2: o cartão da Ana (em outro arquivo) cita a v1
    filtro.select_option(dados["v2"])
    cartao_da_v2 = aba.locator(f"[data-pendencia][data-arquivo-pendencia='{dados['v2']}']",
                               has_text="Ajuste no cadastro de Ana Lima")
    cartao_da_v2.first.wait_for(timeout=15000)
    problema_da_v2 = cartao_da_v2.first.locator("[data-problema-do-cartao]").inner_text()
    conferir(f"na v2, a pessoa em outro arquivo cita a v1 (na tela: {problema_da_v2})",
             f'"{NOME_DO_ARQUIVO} (v1)"' in problema_da_v2)
    # A v1: o cartão da Ana cita a v2
    filtro.select_option(dados["v1"])
    cartao_da_v1 = aba.locator(f"[data-pendencia][data-arquivo-pendencia='{dados['v1']}']",
                               has_text="Ajuste no cadastro de Ana Lima")
    cartao_da_v1.first.wait_for(timeout=15000)
    problema_da_v1 = cartao_da_v1.first.locator("[data-problema-do-cartao]").inner_text()
    conferir(f"na v1, a pessoa em outro arquivo cita a v2 (na tela: {problema_da_v1})",
             f'"{NOME_DO_ARQUIVO} (v2)"' in problema_da_v1)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: Acompanhar (a lista de envios, o filtro de arquivos e os cartões das duas versões)."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_a_lista_de_envios(aba, conferir)
    conferir_o_filtro_e_os_cartoes(aba, dados, conferir)
    aba.close()
