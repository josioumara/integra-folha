"""Roteiro: a "Nova senha provisória" do especialista aparece NA LINHA da pessoa, na aba Usuários.

A história: a senha era gerada e trocada no servidor, mas aparecia só no aviso verde do ALTO da página, fora da vista
(a aba Usuários fica embaixo da Carteira). Depois, ela foi para uma caixa acima da tabela, mas o "Confirmar?" (um
texto em negrito) não parecia um botão. Agora a pergunta tem botões de verdade, e a senha
aparece na linha da pessoa, com o botão de copiar e a orientação do primeiro acesso.

O que ele confere, no Chrome de verdade:
- na ficha da Aurora, aba Usuários, o 1º clique em "Nova senha provisória" pergunta na própria linha, com "Confirmar"
  e "Cancelar" com cara de botão; "Cancelar" volta a linha ao normal, sem gerar nada;
- "Confirmar" gera a senha: ela aparece logo abaixo da linha da pessoa, à vista (sem rolar a página), com o botão de
  copiar (com o ícone) e a orientação do primeiro acesso; a linha da pessoa passa a "Senha resetada (aguardando nova)";
- "Copiar" dá um recado (copiada, ou como copiar à mão), e "Fechar" tira a senha da página;
- o convite de uma pessoa nova mostra a senha do convite na linha dela, à vista;
- a pessoa entra no Portal Empresa com a senha provisória, é obrigada a criar a própria senha e, depois da troca,
  usa o portal (a página de benefícios abre com os dados, sem a janela de troca).
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = "A nova senha provisória aparece na linha da pessoa, com copiar e orientação, e a pessoa entra com ela"
# A pessoa do RH da Aurora que esqueceu a senha (só existe no banco temporário do roteiro)
LOGIN_QUE_ESQUECEU = "rh.segundo@aurora.com.br"
# A pessoa convidada no roteiro (o e-mail precisa ser do domínio da Aurora)
LOGIN_CONVIDADO = "rh.convidado@aurora.com.br"
# A senha que a pessoa cria depois de entrar com a provisória
SENHA_NOVA_DA_PESSOA = "minha-senha-nova-2026"
# A pessoa com a senha provisória gerada há 49 horas (só existe no banco temporário do roteiro)
LOGIN_COM_A_SENHA_VENCIDA = "rh.vencida@aurora.com.br"


def preparar() -> dict:
    """Os usuários de teste, uma pessoa do RH da Aurora que esqueceu a senha e outra com a senha provisória vencida."""
    from datetime import datetime, timedelta, timezone

    from models.contratos import Perfil
    from services import auth
    from tests.e2e.apoio import SENHA_DE_TESTE, criar_usuarios_de_teste
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    auth.cadastrar_usuario(conexao, LOGIN_QUE_ESQUECEU, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    # A senha provisória gerada há 49 horas (ADR-154: vale por 48): a hora é gravada direto no banco temporário
    auth.cadastrar_usuario(conexao, LOGIN_COM_A_SENHA_VENCIDA, "provisoria-vencida-49h", Perfil.EMPRESA, "EMP001",
                           senha_provisoria=True)
    hora = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(timespec="seconds")
    conexao.execute("UPDATE usuarios SET senha_provisoria_gerada_em = ? WHERE login = ?",
                    (hora, LOGIN_COM_A_SENHA_VENCIDA))
    conexao.commit()
    conexao.close()
    return {}


def esta_na_vista(aba, seletor: str) -> bool:
    """True se o elemento está inteiro dentro da janela do navegador (a pessoa o vê sem rolar)."""
    return aba.evaluate("(seletor) => { const caixa = document.querySelector(seletor).getBoundingClientRect();"
                        " return caixa.height > 0 && caixa.top >= 0 && caixa.bottom <= window.innerHeight; }", seletor)


def tem_cara_de_botao(aba, seletor: str) -> bool:
    """True se o elemento parece um botão: tem fundo ou borda desenhados (e não é só um texto)."""
    return aba.evaluate("(seletor) => { const estilo = getComputedStyle(document.querySelector(seletor));"
                        " const tem_fundo = estilo.backgroundColor !== 'rgba(0, 0, 0, 0)';"
                        " const tem_borda = estilo.borderTopStyle !== 'none' && estilo.borderTopWidth !== '0px';"
                        " return tem_fundo || tem_borda; }", seletor)


def linha_da_senha_logo_abaixo_da_pessoa(aba, login: str) -> bool:
    """True se a linha da senha vem logo depois da linha da pessoa, na tabela."""
    return aba.evaluate("(login) => { for (const linha of document.querySelectorAll('[data-corpo-usuarios] tr')) {"
                        " if (linha.dataset.linhaDoUsuario === login) { const seguinte = linha.nextElementSibling;"
                        " return seguinte !== null && seguinte.classList.contains('linha-da-senha-provisoria')"
                        " && seguinte.querySelector('[data-senha-na-linha]').dataset.senhaNaLinha === login; } }"
                        " return false; }", login)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """O especialista gera a senha na aba Usuários; depois, a pessoa entra com ela e cria a própria."""
    banco = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    # A tela de um notebook comum: a aba Usuários fica abaixo da Carteira
    banco.set_viewport_size({"width": 1366, "height": 768})
    banco.goto(endereco + "/banco_empresas.html?empresa=EMP001&aba=usuarios")
    botao = banco.locator(f"[data-nova-senha='{LOGIN_QUE_ESQUECEU}']")
    botao.wait_for(timeout=20000)
    # 0. A pessoa com a senha provisória de mais de 48 horas aparece com o selo de vencida (ADR-154)
    linha_da_vencida = banco.locator(f"[data-corpo-usuarios] tr[data-linha-do-usuario='{LOGIN_COM_A_SENHA_VENCIDA}']")
    conferir(f"a senha provisória de mais de 48 horas aparece como vencida (na tela: {linha_da_vencida.inner_text()})",
             "Senha provisória vencida" in linha_da_vencida.inner_text())
    # 1. O primeiro clique pergunta na própria linha, com botões de verdade
    botao.click()
    confirmar = f"[data-confirmar-nova-senha='{LOGIN_QUE_ESQUECEU}']"
    banco.locator(confirmar).wait_for(timeout=5000)
    linha_da_pessoa = banco.locator(f"[data-corpo-usuarios] tr[data-linha-do-usuario='{LOGIN_QUE_ESQUECEU}']")
    conferir("o 1º clique pergunta na linha da pessoa ('Gerar uma senha nova? A pessoa sai do portal agora.')",
             "Gerar uma senha nova? A pessoa sai do portal agora." in linha_da_pessoa.inner_text())
    conferir("o 'Confirmar' tem cara de botão", tem_cara_de_botao(banco, confirmar))
    conferir("o 'Cancelar' tem cara de botão", tem_cara_de_botao(banco, "[data-cancelar-nova-senha]"))
    conferir("o 'Confirmar' recebe o foco (quem usa o teclado confirma com Enter)",
             banco.evaluate("() => document.activeElement.dataset.confirmarNovaSenha") == LOGIN_QUE_ESQUECEU)
    conferir("nenhuma senha aparece antes de confirmar", banco.locator("[data-senha-na-linha]").count() == 0)
    banco.screenshot(path="storage/painel/senha_confirmar_na_linha.png")
    # 2. "Cancelar" volta a linha ao normal, sem gerar nada
    banco.click("[data-cancelar-nova-senha]")
    conferir("'Cancelar' volta a linha aos botões de sempre",
             banco.locator(confirmar).count() == 0 and botao.is_visible())
    conferir("'Cancelar' não gera senha", banco.locator("[data-senha-na-linha]").count() == 0
             and "Senha resetada" not in linha_da_pessoa.inner_text())
    # 3. De novo, e agora "Confirmar": a senha aparece na linha da pessoa, à vista
    botao.click()
    banco.click(confirmar)
    bloco = f"[data-senha-na-linha='{LOGIN_QUE_ESQUECEU}']"
    banco.locator(bloco).wait_for(timeout=10000)
    senha = banco.inner_text(bloco + " [data-senha-na-linha-valor]").strip()
    conferir(f"a senha aparece na linha da pessoa (com {len(senha)} caracteres)", len(senha) >= 8)
    conferir("a senha fica logo abaixo da linha da pessoa",
             linha_da_senha_logo_abaixo_da_pessoa(banco, LOGIN_QUE_ESQUECEU))
    conferir("a senha está à vista, sem rolar a página", esta_na_vista(banco, bloco))
    conferir("a linha tem o botão de copiar, com o ícone",
             banco.locator(bloco + " [data-copiar-senha-da-linha] svg use[href='#icone-copiar']").count() == 1)
    conferir("a linha orienta o primeiro acesso ('entre com esta senha; o sistema pede para criar a sua')",
             "entre com esta senha; o sistema pede para criar a sua" in banco.inner_text(bloco))
    conferir("a linha da pessoa passa a 'Senha resetada (aguardando nova)'",
             "Senha resetada (aguardando nova)" in linha_da_pessoa.inner_text())
    conferir("a senha recebe o foco (o leitor de tela a lê)",
             banco.evaluate("() => document.activeElement.dataset.senhaNaLinha") == LOGIN_QUE_ESQUECEU)
    banco.screenshot(path="storage/painel/senha_provisoria_na_linha.png")
    # 4. Copiar dá um recado (copiada, ou como copiar à mão, se o navegador não deixar)
    banco.click(bloco + " [data-copiar-senha-da-linha]")
    banco.locator(bloco + " [data-senha-copiada]:not([hidden])").wait_for(timeout=5000)
    recado = banco.inner_text(bloco + " [data-senha-copiada]")
    conferir(f"'Copiar' dá o recado ({recado})", "copiada" in recado or "copie" in recado)
    # 5. Fechar tira a senha da página
    banco.click(bloco + " [data-fechar-senha-da-linha]")
    conferir("'Fechar' tira a linha da senha", banco.locator("[data-senha-na-linha]").count() == 0)
    conferir("'Fechar' apaga a senha da página", senha not in banco.content())
    # 6. O convite: a senha do convite aparece na linha da pessoa nova, à vista
    banco.click("[data-abrir-convite]")
    banco.locator("#janela-convite[open]").wait_for(timeout=10000)
    banco.fill("[data-convite-email]", LOGIN_CONVIDADO)
    banco.click("[data-formulario-convite] button[type='submit']")
    bloco_do_convite = f"[data-senha-na-linha='{LOGIN_CONVIDADO}']"
    banco.locator(bloco_do_convite).wait_for(timeout=10000)
    conferir("o convite mostra a senha na linha da pessoa nova",
             len(banco.inner_text(bloco_do_convite + " [data-senha-na-linha-valor]").strip()) >= 8
             and linha_da_senha_logo_abaixo_da_pessoa(banco, LOGIN_CONVIDADO))
    conferir("a senha do convite está à vista", esta_na_vista(banco, bloco_do_convite))
    banco.close()
    # 7. A pessoa entra com a senha provisória, cria a própria e usa o portal
    empresa = navegador.new_page(viewport={"width": 1366, "height": 768})
    empresa.on("pageerror", lambda erro: erros_da_pagina.append(str(erro)))
    empresa.goto(endereco + "/login.html")
    empresa.fill("[name='usuario']", LOGIN_QUE_ESQUECEU)
    empresa.fill("[name='senha']", senha)
    empresa.click("button[type='submit']")
    empresa.wait_for_url(lambda url: "login.html" not in url, timeout=20000)
    conferir("a pessoa entra com a senha provisória", "login.html" not in empresa.url)
    empresa.locator("#janela-minha-senha[open]").wait_for(timeout=10000)
    conferir("a janela obriga a criar a própria senha",
             empresa.get_attribute("#janela-minha-senha", "data-obrigatoria") == "sim")
    empresa.fill("[data-senha-atual]", senha)
    empresa.fill("[data-senha-nova]", SENHA_NOVA_DA_PESSOA)
    empresa.fill("[data-senha-confirmacao]", SENHA_NOVA_DA_PESSOA)
    # Espera a resposta da troca antes de sair da página (a troca não pode ficar pela metade)
    with empresa.expect_response(lambda resposta: "/api/minha-senha" in resposta.url) as troca:
        empresa.click("[data-formulario-senha] button[type='submit']")
    conferir("a troca da senha foi aceita pelo servidor", troca.value.ok)
    # Depois da troca, a janela não volta: os benefícios abrem com os dados
    empresa.goto(endereco + "/beneficios.html")
    empresa.locator(".usuario-logado[data-dado-pronto]").wait_for(timeout=20000)
    conferir("depois da troca, os benefícios abrem sem a janela de troca",
             empresa.locator("#janela-minha-senha[open]").count() == 0 and "beneficios.html" in empresa.url)
    empresa.close()
