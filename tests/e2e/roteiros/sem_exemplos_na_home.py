"""Roteiro: o Início da empresa nunca mostra os números de exemplo do protótipo.

O defeito: home.html nasceu do protótipo e traz números e listas de exemplo escritos no HTML (312 aprovados, a jornada
da Aurora, 69 sem conta...). Servida pela aplicação, a cada "Atualizar" (F5) esses exemplos apareciam por um instante,
até a API responder, e davam a impressão de números aleatórios. Se a API falhava, o exemplo ficava.

O que ele confere:
- com a resposta do Início segurada por uns 2 segundos: a página tem a marca "aguardando-dados", todo número de
  exemplo está atrás da barra cinza (texto transparente) e a jornada de exemplo está escondida;
- quando a resposta chega: nenhum elemento marcado fica esperando para sempre, o anel mostra um número real e nenhum
  texto de exemplo aparece;
- com a API do Início respondendo erro (500): os números viram "—", a jornada diz que não foi possível carregar e
  nenhum exemplo aparece.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Início da empresa: nenhum número de exemplo aparece, nem esperando a API nem quando ela falha"

# O endereço da API do Início, como o Playwright procura nos pedidos da página
ROTA_DO_INICIO = "**/api/empresa/inicio"

# Textos de exemplo do home.html que nunca podem ficar à mostra com a tela ligada ao servidor
TEXTOS_DE_EXEMPLO = [
    "Parceira Santander desde agosto de 2026",
    "290 funcionários cadastrados",
    "243 dos 312 já abriram a conta",
    "+22 em setembro",
    "Retorno em até 1 dia útil",
    "funcionários com cadastro aprovado",
]

# Os elementos marcados que esperam só a API do Início (a frase e a grade dos benefícios esperam outra API)
SELETOR_DOS_MARCADOS_DO_INICIO = "[data-aguarda-dado]:not([data-inicio-descricao-beneficios])"

# Quem ainda está esperando: marcado no HTML e sem a marca de "pronto"
SELETOR_DOS_QUE_AINDA_ESPERAM = "[data-aguarda-dado]:not([data-dado-pronto]), [data-aguarda-bloco]:not([data-dado-pronto])"


def preparar() -> dict:
    """Só os usuários de teste: a Aurora e o catálogo dela entram sozinhos no banco novo."""
    from services import auth
    from tests.e2e.apoio import criar_usuarios_de_teste
    # Abre o banco temporário e cadastra o RH da Aurora e o especialista do banco
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    conexao.close()
    return {}


def situacao_durante_a_espera(aba) -> dict:
    """Como está a tela enquanto a API do Início não respondeu.

    Devolve: {marca_na_pagina, marcados, prontos, visiveis, etapas_visiveis}: se o <html> tem "aguardando-dados";
    quantos números de exemplo estão marcados; quantos já estão prontos; quantos têm o texto à mostra (cor não
    transparente); e quantos itens da jornada de exemplo estão à mostra.
    """
    return aba.evaluate("""(seletor) => {
        const marca_na_pagina = document.documentElement.classList.contains('aguardando-dados');
        let prontos = 0;
        let visiveis = 0;
        const marcados = document.querySelectorAll(seletor);
        for (const elemento of marcados) {
            if (elemento.hasAttribute('data-dado-pronto')) {
                prontos = prontos + 1;
            }
            if (getComputedStyle(elemento).color !== 'rgba(0, 0, 0, 0)') {
                visiveis = visiveis + 1;
            }
        }
        let etapas_visiveis = 0;
        for (const etapa of document.querySelectorAll('[data-inicio-etapas] > *')) {
            if (getComputedStyle(etapa).display !== 'none') {
                etapas_visiveis = etapas_visiveis + 1;
            }
        }
        return {marca_na_pagina: marca_na_pagina, marcados: marcados.length, prontos: prontos,
                visiveis: visiveis, etapas_visiveis: etapas_visiveis};
    }""", SELETOR_DOS_MARCADOS_DO_INICIO)


def exemplos_a_mostra(aba) -> list:
    """Os textos de exemplo que aparecem na página (o texto que a pessoa lê). Devolve a lista (vazia = nenhum)."""
    texto_da_pagina = aba.inner_text("body")
    encontrados = []
    # Confere um por um os textos de exemplo do home.html
    for texto_de_exemplo in TEXTOS_DE_EXEMPLO:
        if texto_de_exemplo in texto_da_pagina:
            encontrados.append(texto_de_exemplo)
    return encontrados


def quantos_ainda_esperam(aba) -> int:
    """Quantos elementos marcados ainda estão com a barra cinza (deve ser zero depois do carregamento)."""
    return aba.locator(SELETOR_DOS_QUE_AINDA_ESPERAM).count()


def esperar_o_inicio_terminar(aba) -> None:
    """Espera o Início e os benefícios saírem da espera (o anel e a grade dos benefícios ganham a marca "pronto")."""
    aba.wait_for_function("""() => {
        const anel = document.querySelector('[data-inicio-anel-numero]');
        const grade = document.querySelector('[data-grade-beneficios]');
        return anel.hasAttribute('data-dado-pronto') && grade.hasAttribute('data-dado-pronto');
    }""", timeout=20000)


def conferir_a_espera(aba, endereco: str, conferir) -> None:
    """Parte 1 e 2: segura a resposta do Início, confere que nada de exemplo aparece, solta e confere o fim."""
    # Os pedidos do Início que chegarem ficam guardados aqui, sem resposta, até o roteiro soltar
    pedidos_segurados = []

    def segurar_o_pedido(rota):
        """Guarda o pedido do Início sem responder (a página fica esperando a API)."""
        pedidos_segurados.append(rota)

    aba.route(ROTA_DO_INICIO, segurar_o_pedido)
    aba.goto(endereco + "/home.html")
    # Espera o pedido do Início chegar (no máximo 10 segundos, olhando a cada 100 ms)
    tentativas = 0
    while len(pedidos_segurados) == 0 and tentativas < 100:
        aba.wait_for_timeout(100)
        tentativas = tentativas + 1
    conferir("a página pediu o Início à API (pedido segurado)", len(pedidos_segurados) > 0)
    # Um tempo com a resposta segurada: é quando os exemplos apareciam antes da correção
    aba.wait_for_timeout(1000)
    situacao = situacao_durante_a_espera(aba)
    conferir("esperando a API, a página tem a marca 'aguardando-dados'", situacao["marca_na_pagina"])
    conferir(f"esperando a API, os {situacao['marcados']} números de exemplo estão marcados e nenhum está pronto "
             f"(prontos: {situacao['prontos']})", situacao["marcados"] >= 10 and situacao["prontos"] == 0)
    conferir(f"esperando a API, nenhum número de exemplo está à mostra (à mostra: {situacao['visiveis']})",
             situacao["visiveis"] == 0)
    conferir(f"esperando a API, a jornada de exemplo está escondida (etapas à mostra: {situacao['etapas_visiveis']})",
             situacao["etapas_visiveis"] == 0)
    # Solta a resposta do Início (mais uns instantes somam os ~2 segundos de espera)
    aba.wait_for_timeout(1000)
    for rota in pedidos_segurados:
        rota.continue_()
    esperar_o_inicio_terminar(aba)
    # 2. Depois da resposta: ninguém fica esperando e nenhum exemplo aparece
    conferir(f"depois da resposta, nenhum elemento ficou com a barra cinza (sobraram: {quantos_ainda_esperam(aba)})",
             quantos_ainda_esperam(aba) == 0)
    numero_do_anel = aba.inner_text("[data-inicio-anel-numero]").strip()
    conferir(f"o anel mostra o número real de cadastrados (na tela: {numero_do_anel})", numero_do_anel.isdigit())
    encontrados = exemplos_a_mostra(aba)
    conferir(f"nenhum texto de exemplo na tela (achados: {encontrados})", len(encontrados) == 0)
    aba.unroute(ROTA_DO_INICIO)


def conferir_a_falha(aba, endereco: str, conferir) -> None:
    """Parte 3: a API do Início responde erro (500); a tela mostra "—" e nenhum exemplo."""

    def responder_com_erro(rota):
        """Responde o pedido do Início com erro 500, como um servidor com defeito."""
        rota.fulfill(status=500, body="{}")

    aba.route(ROTA_DO_INICIO, responder_com_erro)
    aba.goto(endereco + "/home.html")
    esperar_o_inicio_terminar(aba)
    conferir(f"com a API em erro, nenhum elemento ficou com a barra cinza (sobraram: {quantos_ainda_esperam(aba)})",
             quantos_ainda_esperam(aba) == 0)
    # Os números viram "—": o anel, os quatro cartões e o total sem conta
    numero_do_anel = aba.inner_text("[data-inicio-anel-numero]").strip()
    conferir(f"com a API em erro, o anel mostra '—' (na tela: {numero_do_anel})", numero_do_anel == "—")
    valores_dos_cartoes = aba.locator("[data-inicio-numeros] .cartao-numero-valor").all_inner_texts()
    conferir(f"com a API em erro, os 4 cartões mostram '—' (na tela: {valores_dos_cartoes})",
             valores_dos_cartoes == ["—", "—", "—", "—"])
    sem_conta = aba.inner_text("[data-inicio-sem-conta-numero]").strip()
    conferir(f"com a API em erro, o total sem conta mostra '—' (na tela: {sem_conta})", sem_conta == "—")
    # A jornada diz que não foi possível carregar, e o título não traz o nome da empresa do exemplo
    jornada = aba.inner_text("[data-inicio-etapas]")
    conferir("com a API em erro, a jornada diz 'Não foi possível carregar agora.'",
             "Não foi possível carregar agora." in jornada)
    titulo = aba.inner_text("[data-inicio-titulo]")
    conferir(f"com a API em erro, o título não usa o nome do exemplo (na tela: {titulo})", "Aurora" not in titulo)
    encontrados = exemplos_a_mostra(aba)
    conferir(f"com a API em erro, nenhum texto de exemplo na tela (achados: {encontrados})", len(encontrados) == 0)
    aba.unroute(ROTA_DO_INICIO)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os passos: a espera (resposta segurada), o fim do carregamento e a API com erro."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    conferir_a_espera(aba, endereco, conferir)
    conferir_a_falha(aba, endereco, conferir)
    aba.close()
