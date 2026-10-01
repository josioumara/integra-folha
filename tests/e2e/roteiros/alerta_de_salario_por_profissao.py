"""Roteiro: a empresa confirma a profissão de um cargo e vê o alerta de salário fora da faixa da profissão (ADR-129).

O que ele confere:
- com o campo "codigo_cbo" no parâmetro e um arquivo sem essa coluna, o cargo com profissão na CBO vira um cartão
  que pergunta "parece ser a profissão ... Está certo?";
- antes da resposta, nenhum cartão fala da faixa da profissão (a profissão deduzida nunca vale sozinha);
- "Está certo assim" confirma, e o salário digitado errado (R$ 2,50) desse cargo vira o cartão "fora da faixa da
  profissão", com a faixa pública em reais.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = "Faixa por profissão (CBO): a empresa confirma a profissão do cargo e vê o salário fora da faixa"


def preparar() -> dict:
    """Aurora com o campo codigo_cbo no parâmetro, a carga inicial enviada e aceita, e um salário de R$ 2,50.

    Devolve: {"cargo": o cargo da pessoa com o salário errado}.
    """
    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import acompanhamento, auth, cadastro, correcoes, faixa_salarial_cbo, tabela_cbo
    from tests.e2e.apoio import LOGIN_DO_BANCO, criar_usuarios_de_teste
    from tests.test_correcao import ENVIOS, _escolhas_do_gabarito, _gabarito, busca_falsa
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    # O banco liga a comparação por profissão (o campo "codigo_cbo" no parâmetro)
    faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao, LOGIN_DO_BANCO)
    gabarito = _gabarito("aurora_carga_inicial")
    conteudo = (ENVIOS / gabarito["arquivo"]).read_bytes()
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, gabarito["arquivo"],
                                      busca=busca_falsa)
    leitura = cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                          _escolhas_do_gabarito(gabarito), busca=busca_falsa)
    # A primeira pessoa com um cargo que a CBO reconhece recebe um salário digitado errado
    cargo_escolhido = None
    for registro in correcoes.dados_atuais(conexao, leitura["processamento_id"]).registros:
        if registro.get("tipo_renda") == "CLT" and tabela_cbo.sugerir(registro.get("cargo") or "").codigo:
            cargo_escolhido = registro["cargo"]
            acompanhamento.corrigir_pendencia(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"],
                                              registro["_linha"], "valor_renda", "2,50", "Salário da folha")
            break
    conexao.close()
    return {"cargo": cargo_escolhido}


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques da empresa em Acompanhar."""
    cargo = dados["cargo"]
    conferir(f"a preparação achou um cargo que a CBO reconhece ({cargo})", bool(cargo))
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    # O cartão da pergunta deste cargo (o arquivo pode ter outros cargos, cada um com a sua pergunta)
    pergunta = aba.locator("[data-pendencia]").filter(has_text="parece ser a profissão").filter(has_text=cargo).first
    pergunta.wait_for(timeout=30000)
    conferir("o cargo vira o cartão 'parece ser a profissão ... Está certo?'", "Está certo?" in pergunta.inner_text())
    conferir("antes da resposta, nenhum cartão fala da faixa da profissão",
             aba.locator("[data-pendencia]:has-text('fora da faixa da profissão')").count() == 0)
    # "Está certo assim": a empresa confirma a profissão do cargo
    # A resposta fica na conversa, que abre no painel do lado (ADR-138)
    abrir_a_conversa(aba, pergunta).locator("button:has-text('Está certo assim')").first.click()
    alerta = aba.locator("[data-pendencia]:has-text('fora da faixa da profissão')").first
    alerta.wait_for(timeout=30000)
    texto = alerta.inner_text()
    conferir("depois do 'Está certo assim', o salário de R$ 2,50 vira o cartão 'fora da faixa da profissão', com a "
             "faixa em reais", "R$ 2,50" in texto and texto.count("R$") >= 3)
    aba.close()
