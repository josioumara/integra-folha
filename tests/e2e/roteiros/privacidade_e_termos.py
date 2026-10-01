"""Roteiro: as páginas "Privacidade e LGPD" e "Termos de uso" e o rodapé das telas da empresa que leva a elas.

O que ele confere:
- sem entrar, as duas páginas abrem, com o título e o aviso de projeto, e o "Voltar" de quem abriu o endereço direto
  leva ao login;
- no painel do login, os links das duas páginas; o da privacidade abre a página, e o "Voltar" traz de volta ao login;
- depois do login da empresa, o rodapé da Home e o de Acompanhar mostram só "Privacidade e LGPD" e "Termos de uso"
  ("Central de ajuda" e "Fale com seu especialista" ficam ocultos, ADR-148);
- o clique em "Privacidade e LGPD" na Home abre a página, e o "Voltar" traz de volta à Home;
- o clique em "Termos de uso" em Acompanhar abre a página dos termos;
- no Início do banco, o rodapé mostra só "Política de sigilo e LGPD" ("Manual do especialista" e "Suporte interno"
  ocultos), que abre a privacidade, e o "Voltar" traz de volta ao Início;
- logado como banco, as duas páginas também abrem (não são de um portal só);
- nenhum erro de JavaScript em nenhuma delas (o rodar.py reprova o roteiro se houver).
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = ("Páginas de Privacidade e LGPD e de Termos de uso: abrem sem login, com o 'Voltar'; os links no login, no "
             "rodapé da empresa e no do Início do banco levam às páginas")

# As duas páginas e o título que cada uma mostra
PAGINAS_DE_TEXTO = (("privacidade.html", "Privacidade e LGPD"), ("termos_de_uso.html", "Termos de uso"))
# Os links que o rodapé da empresa mostra, na ordem
LINKS_DO_RODAPE_DA_EMPRESA = ["Privacidade e LGPD", "Termos de uso"]


def preparar() -> dict:
    """Os usuários de teste da empresa e do banco."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    # Abre o banco temporário do roteiro e cadastra os dois usuários
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def textos_dos_links_do_rodape(aba) -> list[str]:
    """Os textos dos links que aparecem no rodapé da tela (o que está guardado num <template> não aparece)."""
    return [texto.strip() for texto in aba.locator("footer .rodape-links a").all_inner_texts()]


def titulo_da_pagina(aba) -> str:
    """O título (h1) da página aberta, sem os espaços das pontas."""
    return aba.inner_text("h1").strip()


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: as páginas sem entrar, o rodapé da empresa (Home e Acompanhar) e as páginas abertas pelo banco."""
    # 1. Sem entrar: uma aba nova, com os erros de JavaScript anotados
    aba = navegador.new_page(viewport={"width": 1440, "height": 1000})
    aba.on("pageerror", lambda erro: erros_da_pagina.append(str(erro)))
    for pagina, titulo in PAGINAS_DE_TEXTO:
        aba.goto(endereco + "/" + pagina)
        conferir(f"sem entrar, {pagina} abre (o porteiro não manda para o login)", pagina in aba.url)
        conferir(f"{pagina} mostra o título '{titulo}'", titulo_da_pagina(aba) == titulo)
        conferir(f"{pagina} mostra o aviso de projeto", "projeto acadêmico" in aba.inner_text(".documento-aviso"))
    # Quem abriu o endereço direto não tem tela anterior do site: o "Voltar" leva ao login
    aba.click("[data-voltar]")
    aba.wait_for_url(lambda url: "login.html" in url, timeout=10000)
    conferir("aberto direto, o 'Voltar' leva ao login", "login.html" in aba.url)
    # No login, o link do painel abre a privacidade, e o "Voltar" traz de volta ao login
    aba.click(".login-links-do-painel a:has-text('Privacidade e LGPD')")
    aba.wait_for_url(lambda url: "privacidade.html" in url, timeout=10000)
    conferir("o link do painel do login abre a privacidade", titulo_da_pagina(aba) == "Privacidade e LGPD")
    aba.click("[data-voltar]")
    aba.wait_for_url(lambda url: "login.html" in url, timeout=10000)
    conferir("da privacidade, o 'Voltar' traz de volta ao login", "login.html" in aba.url)
    # O link dos termos também está no painel do login
    conferir("o painel do login também tem o link dos termos",
             aba.locator(".login-links-do-painel a:has-text('Termos de uso')").count() == 1)
    aba.close()

    # 2. A empresa: o rodapé da Home só com os dois links
    empresa = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    empresa.goto(endereco + "/home.html")
    links = textos_dos_links_do_rodape(empresa)
    conferir(f"o rodapé da Home mostra só Privacidade e Termos (na tela: {links})", links == LINKS_DO_RODAPE_DA_EMPRESA)
    # O clique em "Privacidade e LGPD" abre a página
    empresa.click("footer .rodape-links a:has-text('Privacidade e LGPD')")
    empresa.wait_for_url(lambda url: "privacidade.html" in url, timeout=10000)
    conferir("o link do rodapé da Home abre a página de privacidade", titulo_da_pagina(empresa) == "Privacidade e LGPD")
    # O "Voltar" traz de volta à tela de onde a pessoa veio
    empresa.click("[data-voltar]")
    empresa.wait_for_url(lambda url: "home.html" in url, timeout=10000)
    conferir("o 'Voltar' traz de volta à Home", "home.html" in empresa.url)

    # 3. Em Acompanhar: o mesmo rodapé, e o link dos termos
    empresa.goto(endereco + "/acompanhar.html")
    links = textos_dos_links_do_rodape(empresa)
    conferir(f"o rodapé de Acompanhar mostra só Privacidade e Termos (na tela: {links})",
             links == LINKS_DO_RODAPE_DA_EMPRESA)
    empresa.click("footer .rodape-links a:has-text('Termos de uso')")
    empresa.wait_for_url(lambda url: "termos_de_uso.html" in url, timeout=10000)
    conferir("o link do rodapé de Acompanhar abre os termos", titulo_da_pagina(empresa) == "Termos de uso")
    empresa.close()

    # 4. O banco: o rodapé do Início só com a "Política de sigilo e LGPD", que abre a privacidade
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    banco.goto(endereco + "/banco_inicio.html")
    links = textos_dos_links_do_rodape(banco)
    conferir(f"o rodapé do Início do banco mostra só a Política de sigilo e LGPD (na tela: {links})",
             links == ["Política de sigilo e LGPD"])
    banco.click("footer .rodape-links a:has-text('Política de sigilo e LGPD')")
    banco.wait_for_url(lambda url: "privacidade.html" in url, timeout=10000)
    conferir("o link do rodapé do banco abre a privacidade", titulo_da_pagina(banco) == "Privacidade e LGPD")
    banco.click("[data-voltar]")
    banco.wait_for_url(lambda url: "banco_inicio.html" in url, timeout=10000)
    conferir("o 'Voltar' traz de volta ao Início do banco", "banco_inicio.html" in banco.url)
    # As duas páginas também abrem para o banco
    for pagina, titulo in PAGINAS_DE_TEXTO:
        banco.goto(endereco + "/" + pagina)
        conferir(f"logado como banco, {pagina} abre", pagina in banco.url and titulo_da_pagina(banco) == titulo)
    banco.close()
