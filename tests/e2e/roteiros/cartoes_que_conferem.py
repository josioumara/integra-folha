"""Roteiro: o cartão de pendência só diz "Pronto" quando o valor confere (ADR-127).

O que ele confere em Acompanhar (com a IA simulada, sem custo):
- um envio parado na conferência das colunas aparece num aviso ("Esperando você conferir as colunas"), com o botão
  "Continuar a conferência das colunas"; com ele, a tela nunca mostra "Tudo em dia!";
- no cartão do CPF com o dígito errado, "o certo é 123.456.789-00" recebe "Esse CPF não confere", sem "Pronto",
  e o cartão continua aberto;
- o cartão do CNPJ do empregador oferece "Usar o CNPJ da empresa (10.433.218/0001-93)"; um clique responde
  "Pronto: usei o CNPJ da empresa em 2 funcionários", com o Desfazer.
Desde o ADR-138, a conversa de cada cartão abre no painel do lado: o roteiro abre o cartão e usa o painel.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = "Cartões que conferem: o CPF errado recusado, o CNPJ da empresa num clique e o aviso do envio parado"
# O CPF certo da Bia e o da Ana com o último dígito trocado (inventados)
CPF_CERTO = "11144477735"
CPF_ERRADO = "52998224700"
# O CPF do envio parado (outra pessoa: o mesmo CPF num envio aberto seria recusado)
CPF_DO_PARADO = "12345678909"
# O texto do botão do CNPJ da Aurora (o cadastro da empresa, data/mock/empresas.json)
BOTAO_DO_CNPJ = "Usar o CNPJ da empresa (10.433.218/0001-93)"


def preparar() -> dict:
    """Dois envios da Aurora: um com pendências (sem o CNPJ e o endereço da empresa, e o CPF da Ana errado) e outro
    enviado e ainda sem as colunas conferidas (parado)."""
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
    conteudo = (f"Nome;CPF;Estado civil\nAna Lima;{CPF_ERRADO};Casado\nBia Souza;{CPF_CERTO};Casado\n"
                ).encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, "sem_cnpj.csv",
                                      busca=busca_falsa)
    escolhas = {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"}
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], escolhas,
                                busca=busca_falsa)
    # O envio parado: enviado, e as colunas ainda não conferidas
    parado = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, f"Nome;CPF\nCaio Reis;{CPF_DO_PARADO}\n".encode(),
                                     "parado.csv", busca=busca_falsa)
    conexao.close()
    return {"processamento_id": leitura["processamento_id"], "parado": parado["processamento_id"]}


def conferir_o_aviso_do_envio_parado(aba, dados: dict, conferir) -> None:
    """O aviso do envio parado, com o botão para continuar; nada de "Tudo em dia!"."""
    aviso = aba.locator(f"[data-envio-parado='{dados['parado']}']")
    aviso.wait_for(timeout=30000)
    conferir(f"o aviso do envio parado (na tela: {aviso.inner_text()})",
             "Esperando você conferir as colunas" in aviso.inner_text() and '"parado.csv"' in aviso.inner_text())
    botao = aviso.get_by_text("Continuar a conferência das colunas")
    conferir("o botão abre a conferência das colunas do envio parado",
             botao.count() == 1 and dados["parado"] in (botao.get_attribute("href") or ""))
    conferir("com o envio parado, nada de 'Tudo em dia!'", aba.locator("[data-sem-pendencias]").is_hidden())


def cartao_com(aba, texto: str):
    """O primeiro cartão de pendência que tem o texto (o título, a pergunta ou uma resposta rápida)."""
    return aba.locator("[data-pendencia]").filter(has_text=texto).first


def conferir_o_cpf_que_nao_confere(aba, conferir) -> None:
    """ "o certo é 123.456.789-00" no cartão do CPF da Ana: recusado, sem "Pronto"."""
    cartao_da_lista = cartao_com(aba, "Ana Lima")
    cartao_da_lista.wait_for(timeout=30000)
    # A conversa do cartão, no painel do lado (ADR-138)
    cartao = abrir_a_conversa(aba, cartao_da_lista)
    caixa = cartao.locator("[data-caixa-da-conversa]")
    caixa.fill("o certo é 123.456.789-00")
    caixa.press("Enter")
    recusa = cartao.get_by_text("Esse CPF não confere").first
    recusa.wait_for(timeout=30000)
    conferir(f"o CPF com o dígito errado é recusado na hora (na tela: {recusa.inner_text()})",
             "Nada mudou." in recusa.inner_text() and cartao.get_by_text("Pronto:").count() == 0)


def conferir_o_cnpj_da_empresa(aba, conferir) -> None:
    """O botão "Usar o CNPJ da empresa (...)" no cartão do CNPJ resolve num clique, com o Desfazer."""
    # O cartão da lista pelo título; o botão fica na conversa, no painel do lado (ADR-138)
    titulo_do_cnpj = aba.locator(".ajuste-titulo", has_text="CNPJ")
    cartao_da_lista = aba.locator("[data-lista-pendencias] [data-pendencia]").filter(has=titulo_do_cnpj).first
    cartao_da_lista.wait_for(timeout=30000)
    cartao = abrir_a_conversa(aba, cartao_da_lista)
    botao = cartao.locator("[data-sugestao-da-conversa]", has_text=BOTAO_DO_CNPJ)
    conferir("o cartão do CNPJ oferece o CNPJ do cadastro da empresa", botao.count() == 1)
    botao.click()
    pronto = aba.get_by_text("Pronto: usei o CNPJ da empresa em 2 funcionários").first
    pronto.wait_for(timeout=30000)
    conferir(f"um clique preenche os dois funcionários (na tela: {pronto.inner_text()})",
             '"10.433.218/0001-93"' in pronto.inner_text())
    conferir("o Desfazer fica à mão", aba.locator("[data-desfazer-mudanca]").count() >= 1)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques em Acompanhar: o aviso do envio parado, o CPF recusado e o CNPJ da empresa."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_o_aviso_do_envio_parado(aba, dados, conferir)
    conferir_o_cpf_que_nao_confere(aba, conferir)
    conferir_o_cnpj_da_empresa(aba, conferir)
    aba.close()
