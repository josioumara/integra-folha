"""Roteiro: a seção "Faixas salariais por profissão (CBO)" da página Parâmetros do Portal Interno (ADR-129).

O que ele confere:
- a seção aparece na Configuração, com a explicação de como a faixa é calculada (percentis da RAIS);
- sem busca, mostra 50 de 2.694 profissões e o "Ver mais 50" traz as próximas;
- a busca por código ("4110-10") mostra só a profissão 4110-10, com o mínimo e o máximo em reais e a fonte;
- a busca por palavras ("motor cam") acha "Motorista de caminhão"; uma busca sem resultado diz isso;
- "Editar" abre a janela; o mínimo maior que o máximo mostra o erro e não grava;
- salvar uma faixa válida mostra "Editada por teste.banco" na linha e os valores novos;
- ao abrir de novo, o registro das alterações mostra a edição, e "Voltar ao calculado" devolve a faixa da RAIS.
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "Faixas salariais por profissão (CBO): buscar por código e por palavras, editar, erro e voltar ao calculado"
# A linha da profissão Assistente administrativo
LINHA_DO_ASSISTENTE = "[data-corpo-faixas-cbo] tr[data-codigo-cbo='411010']"


def preparar() -> dict:
    """Só os usuários de teste: as faixas entram sozinhas no banco novo, na primeira busca."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def buscar(aba, texto: str) -> None:
    """Digita a busca e espera a resposta do servidor."""
    with aba.expect_response(lambda resposta: "/api/banco/cbo?busca=" in resposta.url):
        aba.fill("[data-busca-cbo]", texto)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na seção das faixas, como o especialista do banco."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_parametros.html")
    aba.locator("[data-corpo-faixas-cbo] tr").first.wait_for(timeout=20000)
    conferir("a seção 'Faixas salariais por profissão (CBO)' aparece na Configuração",
             aba.locator("#titulo-faixas-cbo").inner_text().startswith("Faixas salariais por profissão"))
    conferir("a explicação de como a faixa é calculada aparece (percentis da RAIS)",
             "percentil 5" in aba.inner_text("[data-medida-cbo]") and "RAIS" in aba.inner_text("[data-medida-cbo]"))
    # 0. Sem busca: as 50 primeiras, dizendo quantas são ao todo; "Ver mais 50" traz as próximas
    conferir("sem busca, a seção diz 'Mostrando 1–50 de 2.694 profissões' (na tela: "
             + aba.inner_text("[data-quantas-cbo]") + ")",
             aba.inner_text("[data-quantas-cbo]").startswith("Mostrando 1–50 de 2.694 profissões")
             and aba.locator("[data-corpo-faixas-cbo] tr").count() == 50)
    with aba.expect_response(lambda resposta: "/api/banco/cbo?busca=&inicio=50" in resposta.url):
        aba.click("[data-ver-mais-cbo]")
    aba.wait_for_function("() => document.querySelectorAll('[data-corpo-faixas-cbo] tr').length === 100",
                          timeout=10000)
    conferir("'Ver mais 50' acrescenta as próximas 50 (100 na tabela, 'Mostrando 1–100 de 2.694')",
             aba.inner_text("[data-quantas-cbo]").startswith("Mostrando 1–100 de 2.694"))
    # 1. Busca por código
    buscar(aba, "4110-10")
    aba.locator(LINHA_DO_ASSISTENTE).wait_for(timeout=10000)
    linha = aba.locator(LINHA_DO_ASSISTENTE).inner_text()
    conferir("a busca '4110-10' mostra só a profissão 4110-10, com o mínimo, o máximo e a fonte",
             aba.locator("[data-corpo-faixas-cbo] tr").count() == 1 and "Assistente administrativo" in linha
             and linha.count("R$") == 2 and "RAIS 2025" in linha)
    # 2. Busca por palavras e busca sem resultado
    buscar(aba, "motor cam")
    aba.locator("[data-corpo-faixas-cbo] tr[data-codigo-cbo='782510']").wait_for(timeout=10000)
    conferir("a busca 'motor cam' acha 'Motorista de caminhão'", True)
    buscar(aba, "zzzzqqq")
    aba.locator("[data-sem-faixas-cbo]:not([hidden])").wait_for(timeout=10000)
    conferir("uma busca sem resultado diz que nenhuma profissão tem esse código ou nome", True)
    # 3. Editar: o mínimo maior que o máximo não grava
    buscar(aba, "411010")
    aba.locator(LINHA_DO_ASSISTENTE).wait_for(timeout=10000)
    aba.locator(LINHA_DO_ASSISTENTE + " button:has-text('Editar')").click()
    aba.locator("[data-janela-cbo][open]").wait_for(timeout=5000)
    aba.fill("[data-minimo-cbo]", "5000")
    aba.fill("[data-maximo-cbo]", "4000")
    aba.click("[data-salvar-cbo]")
    aba.locator("[data-erro-janela-cbo]:not([hidden])").wait_for(timeout=10000)
    conferir("o mínimo maior que o máximo mostra o erro e a janela continua aberta",
             "maior que o máximo" in aba.inner_text("[data-erro-janela-cbo]")
             and aba.locator("[data-janela-cbo][open]").count() == 1)
    # 4. Uma faixa válida grava, e a linha mostra quem editou
    aba.fill("[data-minimo-cbo]", "2.100,00")
    aba.fill("[data-maximo-cbo]", "4900")
    aba.click("[data-salvar-cbo]")
    aba.locator("[data-janela-cbo]:not([open])").wait_for(state="attached", timeout=10000)
    aba.wait_for_function("() => document.querySelector(\"" + LINHA_DO_ASSISTENTE.replace('"', '\\"')
                          + "\").innerText.includes('Editada por')", timeout=10000)
    linha = aba.locator(LINHA_DO_ASSISTENTE).inner_text()
    conferir("depois de salvar, a linha mostra 'Editada por teste.banco' e a faixa R$ 2.100,00 a R$ 4.900,00",
             "Editada por teste.banco" in linha and "R$ 2.100,00" in linha and "R$ 4.900,00" in linha)
    # 5. O registro das alterações e o "Voltar ao calculado"
    aba.locator(LINHA_DO_ASSISTENTE + " button:has-text('Editar')").click()
    aba.locator("[data-janela-cbo][open]").wait_for(timeout=5000)
    aba.locator("[data-alteracoes-cbo] li:has-text('teste.banco')").wait_for(timeout=10000)
    conferir("a janela mostra a edição no registro e o botão 'Voltar ao calculado'",
             aba.locator("[data-voltar-cbo]").is_visible())
    aba.click("[data-voltar-cbo]")
    aba.wait_for_function("() => document.querySelector(\"" + LINHA_DO_ASSISTENTE.replace('"', '\\"')
                          + "\").innerText.includes('RAIS 2025')", timeout=10000)
    conferir("'Voltar ao calculado' devolve a faixa da RAIS e tira o 'Editada por'",
             "Editada por" not in aba.locator(LINHA_DO_ASSISTENTE).inner_text())
    aba.close()
