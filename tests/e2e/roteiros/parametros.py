"""Roteiro: a tela Sistema do banco (o antigo "Configuração", ADR-148), com os Parâmetros do layout (lista só de
leitura + janela; salvar grava na hora, com registro).

O que ele confere:
- a engrenagem "Sistema" do alto do Início abre um menu, e o item "Parâmetros do layout" abre a tela; nela, o título é
  "Sistema", nenhuma aba do menu fica marcada, a engrenagem fica marcada e o item da tela leva aria-current="page";
- a lista não tem caixas de marcar nem "Gravar nova versão"; o CPF aparece como dado pessoal;
- a coluna "Igual para todos": o CNPJ do empregador pode, o CPF não (é de cada pessoa); e a primeira gravação não lista
  essa marcação como mudança nos outros campos;
- "+ Novo campo" abre a janela; salvar grava o campo e a linha "Campo novo" no registro;
- "Editar" abre a mesma janela preenchida, com o nome técnico travado; marcar "dado pessoal" registra "não → sim";
- salvar sem mudar nada avisa e não grava; "Tirar este campo" pede confirmação e registra "Campo removido".
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Sistema (Parâmetros): menu da engrenagem, novo campo, editar, salvar sem mudança e tirar, com o "
             "registro")


def preparar() -> dict:
    """Só os usuários de teste: o layout padrão entra sozinho no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def primeira_linha_do_registro(aba) -> str:
    """O texto da linha mais recente do registro das alterações."""
    return aba.locator("[data-corpo-registro] tr").first.inner_text()


# A posição da coluna "Igual para todos" na lista (Campo, Tipo, Obrigatório, Dado pessoal, Uso comercial, Igual...)
COLUNA_IGUAL_PARA_TODOS = 5


def celula_igual_para_todos(aba, campo: str) -> str:
    """O texto da coluna "Igual para todos" de um campo da lista ("Sim" ou "—")."""
    return aba.locator(f"tr[data-campo='{campo}'] td").nth(COLUNA_IGUAL_PARA_TODOS).inner_text()


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques na tela Sistema (Parâmetros do layout) do Portal Interno."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    # 0. A engrenagem "Sistema", no alto do Início, abre o menu; o item "Parâmetros do layout" leva à tela
    aba.goto(endereco + "/banco_inicio.html")
    aba.click(".acoes-usuario [data-botao-configuracao]")
    aba.click("[data-itens-configuracao] a:has-text('Parâmetros do layout')")
    aba.wait_for_url("**/banco_parametros.html", timeout=10000)
    aba.locator("[data-corpo-parametros] tr[data-campo='cpf']").wait_for(timeout=15000)
    conferir("o item 'Parâmetros do layout' do menu da engrenagem abre a tela do Sistema, com esse título",
             aba.inner_text("h1.titulo-pagina").strip().startswith("Sistema"))
    # O botão da engrenagem e o item da tela atual (aria-current='page') ficam marcados
    classes_do_botao = aba.get_attribute("[data-botao-configuracao]", "class").split()
    conferir("no Sistema, nenhuma aba do menu fica marcada; a engrenagem fica, e o item 'Parâmetros do layout' "
             "leva aria-current='page'",
             aba.locator(".abas-banco .aba-ativa").count() == 0
             and "botao-configuracao-marcado" in classes_do_botao
             and aba.get_attribute("[data-itens-configuracao] a[aria-current='page']", "href")
             == "banco_parametros.html")
    conferir("lista só de leitura: sem caixas de marcar nem 'Gravar nova versão'",
             aba.locator("[data-corpo-parametros] input").count() == 0
             and aba.locator("text=Gravar nova versão").count() == 0)
    conferir("CPF aparece como dado pessoal (Sim)", "Sim" in aba.locator("tr[data-campo='cpf']").inner_text())
    # A ajuda da marcação: os campos que não são da empresa são únicos por funcionário
    conferir("a ajuda de 'Igual para todos' diz que os outros campos são únicos por funcionário",
             "Os outros campos são únicos por funcionário" in aba.inner_text("main"))
    # "Igual para todos": o CNPJ do empregador pode; o CPF é de cada pessoa
    igual_do_cnpj = celula_igual_para_todos(aba, "cnpj_empregador")
    igual_do_cpf = celula_igual_para_todos(aba, "cpf")
    conferir(f"coluna 'Igual para todos': CNPJ do empregador Sim, CPF — (na tela: {igual_do_cnpj} e {igual_do_cpf})",
             igual_do_cnpj == "Sim" and igual_do_cpf == "—")
    # 1. Novo campo: a janela; salvar grava na hora
    aba.click("[data-novo-campo]")
    aba.locator("[data-janela-campo][open]").wait_for(timeout=5000)
    aba.fill("[data-campo-nome]", "nome_social")
    aba.fill("[data-campo-grupo]", "Titular")
    aba.select_option("[data-campo-tipo]", "TEXTO")
    aba.fill("[data-campo-texto='descricao']", "Nome social do funcionário")
    aba.click("[data-salvar-campo]")
    aba.locator("tr[data-campo='nome_social']").wait_for(timeout=15000)
    conferir("campo novo na lista e no registro", "Campo novo: nome_social" in primeira_linha_do_registro(aba))
    conferir("a marcação 'igual para todos' dos outros campos não aparece como mudança",
             "igual para todos" not in primeira_linha_do_registro(aba))
    # 2. Editar: a mesma janela, preenchida; nome técnico travado
    aba.click("[data-editar-campo='nome_social']")
    aba.locator("[data-janela-campo][open]").wait_for(timeout=5000)
    conferir("editar abre preenchido, com o nome travado",
             aba.input_value("[data-campo-grupo]") == "Titular" and aba.locator("[data-campo-nome]").is_disabled())
    aba.check("[data-campo-marcacao='sensivel']")
    aba.click("[data-salvar-campo]")
    aba.wait_for_function("() => document.querySelector('[data-corpo-registro] tr').innerText.includes('não → sim')",
                          timeout=15000)
    conferir("edição registrada (não → sim)", True)
    # 3. Salvar sem mudar nada: a janela avisa e não grava
    aba.click("[data-editar-campo='nome_social']")
    aba.click("[data-salvar-campo]")
    aba.locator("[data-erro-janela-campo]:not([hidden])").wait_for(timeout=10000)
    conferir("salvar sem mudança avisa", "Nada mudou" in aba.inner_text("[data-erro-janela-campo]"))
    # 4. Tirar: dois cliques, grava na hora
    aba.click("[data-tirar-campo]")
    conferir("primeiro clique pede confirmação", "Clique de novo" in aba.inner_text("[data-tirar-campo]"))
    aba.click("[data-tirar-campo]")
    aba.wait_for_function("() => document.querySelector('[data-corpo-registro] tr').innerText.includes('Campo removido')",
                          timeout=15000)
    conferir("campo tirado da lista e registrado", aba.locator("tr[data-campo='nome_social']").count() == 0)
    aba.close()
