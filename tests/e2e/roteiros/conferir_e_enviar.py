"""Roteiro: conferir e enviar (ADR-126).

O que ele confere:
- envio parcial em Acompanhar: o arquivo com 2 pessoas que já foram ao banco e 2 novas aparece em "Pronto para enviar"
  com "2 pessoas · 2 ficam de fora (já mandadas antes)"; a janela da conferência diz quem fica de fora e por quê, a
  grade tem só as 2 novas, e o recado depois do envio conta quem ficou de fora;
- um número só: no Cadastrar, o "para revisar" do painel "Linhas do arquivo" é o mesmo dos contadores da
  conferência e do filtro de arquivos de Acompanhar, contando as informações que faltam no arquivo inteiro, com o
  aviso de onde elas se resolvem;
- a lista final: o CNPJ informado "para todos" nos cartões aparece na ficha da pessoa (nada de
  "Informação não encontrada" para o que vai ao banco);
- o arquivo em que todos já foram mandados antes é recusado com o porquê ("Nada novo para enviar ... em análise no
  banco"), e nada é enviado.
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Conferir e enviar: quem já foi ao banco fica de fora, um número só de pendências e a lista final"


def preparar() -> dict:
    """A Aurora com um envio no banco, um arquivo com 2 já enviadas e 2 novas (pronto) e um arquivo curto."""
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro, correcoes, empresas
    from tests.e2e.apoio import criar_usuarios_de_teste, pasta_do_roteiro
    from tests.test_avaliacao_do_banco import enviar_a_aurora_ao_banco
    from tests.test_conferir_e_enviar import (_arquivo_curto, _cpfs_do_envio, _enviar_e_aceitar, _linhas_ja_enviadas,
                                              _pessoa_nova, _planilha)
    from tests.test_correcao import RAIZ, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # A carga inicial da Aurora já foi ao banco e espera a análise
    no_banco = enviar_a_aurora_ao_banco(conexao, verdade)
    ja_enviadas = _linhas_ja_enviadas(_cpfs_do_envio(conexao, no_banco))
    # O arquivo novo: 2 pessoas que já foram ao banco e 2 novas (pronto para enviar)
    linhas = [ja_enviadas[0], _pessoa_nova(ja_enviadas[0], 3), ja_enviadas[1], _pessoa_nova(ja_enviadas[0], 4)]
    _enviar_e_aceitar(conexao, _planilha(linhas), "novos_e_repetidos.xlsx")
    # O arquivo curto (só Nome e CPF, 3 pessoas novas), com o CNPJ informado "para todos" num cartão
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, _arquivo_curto(3, False), "curto.csv",
                                      busca=busca_falsa)
    curto = leitura["processamento_id"]
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, curto, {"Nome": "nome_completo", "CPF": "cpf"},
                                busca=busca_falsa)
    cnpj = empresas.cnpjs_conhecidos(conexao, "EMP001")["principal"]
    correcoes.preencher_para_todos(conexao, curto, "EMP001", "cnpj_empregador", cnpj, "Informado no cartão",
                                   LOGIN_DA_EMPRESA)
    # A planilha em que todos já foram ao banco (para a recusa)
    caminho_repetidos = pasta_do_roteiro() / "todos_repetidos.xlsx"
    caminho_repetidos.write_bytes(_planilha(ja_enviadas[2:5]))
    conexao.close()
    return {"curto": curto, "cnpj": cnpj, "todos_repetidos": str(caminho_repetidos)}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques em Acompanhar e no Cadastrar."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    # 1. Envio parcial: "Pronto para enviar" com quem vai e quem fica de fora
    aba.goto(endereco + "/acompanhar.html")
    aba.locator("[data-prontos]").wait_for(state="visible", timeout=20000)
    item = aba.inner_text("[data-lista-prontos]")
    conferir(f"o envio pronto diz quantas vão e quantas ficam de fora (na tela: {item})",
             "novos_e_repetidos.xlsx" in item and "2 pessoas" in item
             and "2 ficam de fora (já mandadas antes)" in item)
    aba.click("[data-abrir-conferencia-prontos]")
    aba.locator("#janela-conferir-envio[open] .linha-de-grupos").wait_for(timeout=20000)
    bloco = aba.locator("#janela-conferir-envio .quem-fica-de-fora")
    texto_do_bloco = bloco.inner_text()
    conferir("a janela diz quem fica de fora e por quê",
             "2 pessoas ficam de fora deste envio" in texto_do_bloco
             and texto_do_bloco.count("Já foi enviada ao banco no arquivo") == 2
             and re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto_do_bloco) is not None)
    linhas_da_grade = aba.locator("#janela-conferir-envio [data-grades-dos-prontos] tbody tr").count()
    conferir(f"a grade tem só as 2 pessoas novas ({linhas_da_grade} linhas)", linhas_da_grade == 2)
    conferir("o botão conta só quem vai",
             "2 pessoa(s)" in aba.inner_text("[data-enviar-prontos]"))
    aba.locator("#janela-conferir-envio").screenshot(path="storage/painel/conferir_e_enviar_parcial.png")
    aba.check("[data-conferi-prontos]")
    aba.click("[data-enviar-prontos]")
    aba.wait_for_url("**acompanhar.html?enviado=*", timeout=30000)
    recado = aba.inner_text("[data-aviso-recebido-texto]")
    conferir(f"o recado conta quem ficou de fora (na tela: {recado})",
             "Os 2 funcionários" in recado and "2 pessoas que já tinham sido mandadas antes ficaram de fora" in recado)
    # 2. Um número só: o filtro de arquivos de Acompanhar conta as pendências do arquivo curto
    aba.locator("[data-filtro-arquivo-pendencias] option", has_text="curto.csv").wait_for(state="attached",
                                                                                            timeout=20000)
    opcao = aba.locator("[data-filtro-arquivo-pendencias] option", has_text="curto.csv").inner_text()
    encontrado = re.search(r"(\d+) pendência", opcao)
    pendencias_em_acompanhar = int(encontrado.group(1)) if encontrado else -1
    conferir(f"Acompanhar conta as pendências do arquivo curto (na tela: {opcao})", pendencias_em_acompanhar > 0)
    # No Cadastrar, o mesmo número no painel e nos contadores da conferência
    aba.goto(endereco + "/cadastrar.html?envio=" + dados["curto"])
    aba.locator("[data-real-contadores-conferencia] .contador-conferencia").first.wait_for(timeout=30000)
    no_painel = aba.inner_text("#contador-revisar")
    contadores = aba.inner_text("[data-real-contadores-conferencia]")
    conferir(f"o painel e a conferência dizem o mesmo número (painel: {no_painel}; conferência: {contadores})",
             (no_painel + " para revisar") in contadores and int(no_painel) == pendencias_em_acompanhar)
    conferir("a conferência conta as informações que faltam no arquivo",
             "informações faltam no arquivo" in contadores and "0 pessoas com pendência" in contadores)
    conferir("o painel diz 0 prontas enquanto falta informação no arquivo", aba.inner_text("#contador-prontas") == "0")
    aviso = aba.locator("[data-real-aviso-no-arquivo]")
    conferir("o aviso diz onde se resolve o que falta no arquivo",
             aviso.is_visible() and "Acompanhar cadastros" in aviso.inner_text())
    # 3. A lista final mostra o que vai para o banco: o CNPJ informado para todos aparece na ficha da pessoa
    aba.uncheck("[data-real-so-pendencias]")
    aba.locator("[data-real-corpo-conferencia] .botao-nome", has_text="Ver todos os dados").first.click()
    aba.locator(".linha-ficha-real").first.wait_for(timeout=10000)
    ficha = aba.inner_text(".linha-ficha-real")
    conferir("a ficha mostra o CNPJ informado no cartão", "cnpj empregador" in ficha and dados["cnpj"] in ficha)
    aba.locator("[data-real-bloco-conferencia]").screenshot(path="storage/painel/conferir_e_enviar_numero_unico.png")
    # 4. Todos já foram ao banco: recusado com o porquê, nada enviado
    aba.goto(endereco + "/cadastrar.html")
    aba.set_input_files("#campo-arquivo", dados["todos_repetidos"])
    # A recusa vem na conversa da IA, num balão de alerta (espera o texto terminar de ser escrito)
    aba.wait_for_function("() => Array.from(document.querySelectorAll('.mensagem-ia-alerta'))"
                          ".some(mensagem => mensagem.innerText.includes('Acompanhar cadastros'))", timeout=60000)
    texto_do_erro = aba.locator(".mensagem-ia-alerta", has_text="Nada novo para enviar").last.inner_text()
    conferir(f"recusado com o porquê (na tela: {texto_do_erro})",
             "Nada novo para enviar" in texto_do_erro and "em análise no banco" in texto_do_erro
             and "Nada foi enviado" in texto_do_erro)
    aba.close()
