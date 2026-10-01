"""Roteiro: a conversa da pendência confere o valor na hora e encerra com educação depois das respostas sem valor
(ADR-153).

O que ele confere em Acompanhar (com a IA simulada, sem custo), no parâmetro dos 4 obrigatórios (ADR-143):
- no cartão do código da profissão que veio vazio, o código "C900" (que não é da CBO oficial) é recusado na mesma
  resposta: o balão diz o que está errado, com o exemplo, que nada mudou e que a informação continua vazia; não aparece
  "Pronto", o cartão continua na lista e nenhum cartão novo nasce para a pessoa;
- no cartão do CPF com o dígito errado, "não sei" e "não tenho" recebem balões diferentes, cada um com o CPF que veio
  no arquivo; o terceiro ("prefiro não informar") recebe o encerramento educado e a marca "Conversa encerrada. A
  pendência continua aberta."; a caixa continua valendo.
A conversa de cada cartão abre na janela por cima da tela (ADR-138).
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = "Conferir na hora: o código da profissão recusado no mesmo cartão e o encerramento depois de 3 'não sei'"
# Os CPFs das pessoas (inventados): o da Ana e o da Bia certos, o do Caio com o último dígito trocado
CPF_DA_ANA = "52998224725"
CPF_DA_BIA = "11144477735"
CPF_DO_CAIO = "12345678900"
# O CPF do Caio como a tela escreve
CPF_DO_CAIO_NA_TELA = "123.456.789-00"
# O que o arquivo traz: a Ana sem o código da profissão e o Caio com o CPF errado (as datas com o dia acima de 12)
ARQUIVO = ("Nome;CPF;Cargo;Código CBO;Tipo de renda;Salário;Admissão\n"
           f"Ana Lima;{CPF_DA_ANA};Assistente administrativo;;CLT;3000,00;15/02/2020\n"
           f"Bia Souza;{CPF_DA_BIA};Assistente administrativo;4110-10;CLT;3000,00;16/02/2020\n"
           f"Caio Reis;{CPF_DO_CAIO};Assistente administrativo;4110-10;CLT;3000,00;17/02/2020\n")
# As colunas do arquivo e o campo de cada uma (o aceite da empresa)
ESCOLHAS = {"Nome": "nome_completo", "CPF": "cpf", "Cargo": "cargo", "Código CBO": "codigo_cbo",
            "Tipo de renda": "tipo_renda", "Salário": "valor_renda", "Admissão": "data_admissao"}
# As três respostas sem valor do cartão do CPF
RESPOSTAS_SEM_VALOR = ("não sei", "não tenho", "prefiro não informar")


def preparar() -> dict:
    """O parâmetro dos 4 obrigatórios (com o código da profissão) e um envio da Aurora com as duas pendências."""
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, cadastro, faixa_salarial_cbo
    from tests.apoio_do_parametro import marcar_como_obrigatorios
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # O parâmetro do ADR-143: o código da profissão no layout, e só os 4 obrigatórios
    faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao, "especialista")
    marcar_como_obrigatorios(conexao, "cpf", "codigo_cbo", "valor_renda", "data_admissao", so_estes=True)
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, ARQUIVO.encode("utf-8"),
                                      "profissoes.csv", busca=busca_falsa)
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], ESCOLHAS,
                                busca=busca_falsa)
    conexao.close()
    return {"processamento_id": leitura["processamento_id"]}


def cartoes_de(aba, nome: str):
    """Os cartões da lista das pendências abertas de uma pessoa."""
    return aba.locator("[data-lista-pendencias] [data-pendencia]").filter(has_text=nome)


def mandar(painel, texto: str) -> None:
    """Escreve na caixa da conversa e manda (Enter)."""
    caixa = painel.locator("[data-caixa-da-conversa]")
    caixa.fill(texto)
    caixa.press("Enter")


def conferir_o_codigo_recusado_na_hora(aba, conferir) -> None:
    """ "C900" no código da profissão da Ana: recusado no mesmo cartão, sem "Pronto" e sem cartão novo."""
    cartao_da_ana = cartoes_de(aba, "Ana Lima").first
    cartao_da_ana.wait_for(timeout=30000)
    conferir("a Ana tem um cartão só (o código da profissão que veio vazio)", cartoes_de(aba, "Ana Lima").count() == 1)
    painel = abrir_a_conversa(aba, cartao_da_ana)
    mandar(painel, "C900")
    recusa = painel.get_by_text("não é uma profissão").first
    recusa.wait_for(timeout=30000)
    texto = recusa.inner_text()
    conferir(f"o código que não existe é recusado na hora, com o exemplo (na tela: {texto})",
             '"C900"' in texto and "4110-10" in texto and "Nada mudou." in texto and "continua vazia" in texto)
    conferir("nenhum 'Pronto' na conversa", painel.get_by_text("Pronto:").count() == 0)
    # A pendência continua aberta, e nenhum cartão novo nasceu do valor recusado
    aba.wait_for_timeout(500)
    conferir("a Ana continua com um cartão só, o mesmo", cartoes_de(aba, "Ana Lima").count() == 1)


def conferir_o_encerramento_educado(aba, conferir) -> None:
    """Três respostas sem valor no cartão do CPF do Caio: as duas primeiras mostram o CPF que veio no arquivo; a terceira
    encerra com educação, com a marca "Conversa encerrada"."""
    cartao_do_caio = cartoes_de(aba, "Caio Reis").first
    cartao_do_caio.wait_for(timeout=30000)
    painel = abrir_a_conversa(aba, cartao_do_caio)
    # 1ª e 2ª: o CPF que veio no arquivo, em falas diferentes
    mandar(painel, RESPOSTAS_SEM_VALOR[0])
    primeira = painel.get_by_text("ficha de registro").first
    primeira.wait_for(timeout=30000)
    conferir(f"a 1ª resposta mostra o CPF que veio no arquivo (na tela: {primeira.inner_text()})",
             CPF_DO_CAIO_NA_TELA in primeira.inner_text())
    mandar(painel, RESPOSTAS_SEM_VALOR[1])
    segunda = painel.get_by_text("encerro a conversa por aqui").first
    segunda.wait_for(timeout=30000)
    conferir(f"a 2ª resposta é outra fala, com o CPF (na tela: {segunda.inner_text()})",
             CPF_DO_CAIO_NA_TELA in segunda.inner_text())
    conferir("antes da 3ª, nenhuma marca de conversa encerrada", painel.locator("[data-conversa-encerrada]").count() == 0)
    # 3ª: o encerramento educado e a marca
    mandar(painel, RESPOSTAS_SEM_VALOR[2])
    marca = painel.locator("[data-conversa-encerrada]")
    marca.wait_for(timeout=30000)
    conferir(f"a marca da conversa encerrada (na tela: {marca.inner_text()})",
             marca.inner_text() == "Conversa encerrada. A pendência continua aberta.")
    encerramento = painel.get_by_text("Obrigado pela ajuda até aqui").first
    conferir(f"o encerramento educado pede para revisar o arquivo (na tela: {encerramento.inner_text()})",
             "a pendência continua aberta" in encerramento.inner_text()
             and "envie o arquivo de novo" in encerramento.inner_text())
    conferir("a caixa continua valendo (quem descobrir o valor pode escrever)",
             painel.locator("[data-caixa-da-conversa]").is_enabled())
    conferir("o cartão do Caio continua na lista", cartoes_de(aba, "Caio Reis").count() == 1)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques em Acompanhar: o código da profissão recusado e o encerramento depois das respostas sem valor."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_o_codigo_recusado_na_hora(aba, conferir)
    conferir_o_encerramento_educado(aba, conferir)
    aba.close()
