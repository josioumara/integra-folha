"""Roteiro: as decisões do ADR-128 no parâmetro do layout, nas duas pontas.

O que ele confere (com a IA simulada, sem custo):
- no Portal Interno, tela Parâmetros:
  - a matrícula continua na lista, opcional, e o sexo é obrigatório;
  - a coluna "Faixa" mostra "a partir de R$ 500,00" no salário e "—" no CPF;
  - "Editar" o salário mostra o "Mínimo" (500,00) e o "Máximo" vazio, e gravar um máximo registra "sem limite →
    R$ 90.000,00" e muda a coluna;
  - o mínimo maior que o máximo é recusado com a explicação;
  - num campo de texto (CPF), o mínimo e o máximo nem aparecem;
- no Portal da empresa, em Acompanhar, os cartões de um arquivo com três pessoas (valores inventados aqui):
  - o sexo vazio e o sexo "Não informado" viram cartões com as respostas rápidas F e M;
  - o tipo de renda "Mensal" vira um cartão sem palpite de CLT, com as opções CLT, PRO_LABORE e OUTROS; o clique em
    OUTROS resolve;
  - o tipo "Outro" é aceito (vira OUTROS, sem cartão);
  - o salário de R$ 320,00 vira um alerta, "abaixo do mínimo do parâmetro (R$ 500,00)", com "Está certo assim".
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar
from tests.e2e.painel_da_conversa import abrir_a_conversa

DESCRICAO = ("Parâmetro do layout (ADR-128): matrícula opcional, sexo obrigatório, faixa do salário na tela e os cartões "
             "do sexo, do tipo de renda com OUTROS e do alerta de faixa")
# As pessoas do arquivo (CPFs válidos e inventados): sem sexo; "Não informado" e "Mensal"; "Outro" e salário baixo
PESSOA_SEM_SEXO = ("Lia Prado", "52998224725", "", "CLT", "2.500,00")
PESSOA_MENSAL = ("Rui Costa", "11144477735", "Não informado", "Mensal", "3.100,00")
PESSOA_ABAIXO_DO_PISO = ("Gil Nunes", "12345678909", "M", "Outro", "320,00")
# Os nomes das informações nos títulos dos cartões (a descrição do parâmetro, sem o que está entre parênteses)
INFORMACAO_DO_SEXO = "Sexo informado no cadastro"
INFORMACAO_DO_TIPO = "Natureza da renda"
INFORMACAO_DO_SALARIO = "Salário bruto mensal ou pró-labore"
# As posições das colunas da lista de Parâmetros (Campo, Tipo, Obrigatório, Dado pessoal, Uso comercial, Igual, Faixa)
COLUNA_OBRIGATORIO = 2
COLUNA_FAIXA = 6


def preparar() -> dict:
    """Um envio da Aurora com as três pessoas, com as colunas aceitas. Devolve {processamento_id}."""
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
    # O arquivo: uma linha por pessoa, separado por ponto e vírgula
    linhas = ["Nome;CPF;Sexo;Tipo de renda;Salário"]
    for pessoa in (PESSOA_SEM_SEXO, PESSOA_MENSAL, PESSOA_ABAIXO_DO_PISO):
        linhas.append(";".join(pessoa))
    conteudo = ("\n".join(linhas) + "\n").encode("utf-8")
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", LOGIN_DA_EMPRESA, conteudo, "parametros_do_layout.csv",
                                      busca=busca_falsa)
    escolhas = {"Nome": "nome_completo", "CPF": "cpf", "Sexo": "sexo", "Tipo de renda": "tipo_renda",
                "Salário": "valor_renda"}
    cadastro.aceitar_mapeamento(conexao, "EMP001", LOGIN_DA_EMPRESA, leitura["processamento_id"], escolhas,
                                busca=busca_falsa)
    conexao.close()
    return {"processamento_id": leitura["processamento_id"]}


# ============================== Portal Interno: a tela Parâmetros ==============================

def celula(aba, campo: str, coluna: int) -> str:
    """O texto de uma coluna da lista de Parâmetros, na linha do campo."""
    return aba.locator(f"tr[data-campo='{campo}'] td").nth(coluna).inner_text().strip()


def primeira_linha_do_registro(aba) -> str:
    """O texto da linha mais recente do registro das alterações."""
    return aba.locator("[data-corpo-registro] tr").first.inner_text()


def abrir_o_campo(aba, campo: str) -> None:
    """Clica em "Editar" no campo e espera a janela abrir."""
    aba.click(f"[data-editar-campo='{campo}']")
    aba.locator("[data-janela-campo][open]").wait_for(timeout=5000)


def conferir_a_tela_de_parametros(navegador, endereco: str, conferir, erros_da_pagina: list) -> None:
    """A lista (matrícula opcional, sexo obrigatório, coluna Faixa) e a janela do campo (mínimo e máximo)."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_parametros.html")
    aba.locator("[data-corpo-parametros] tr[data-campo='valor_renda']").wait_for(timeout=15000)
    obrigatoria = celula(aba, "matricula", COLUNA_OBRIGATORIO)
    conferir(f"a matrícula continua no parâmetro, opcional (na tela: {obrigatoria})", obrigatoria == "—")
    conferir(f"o sexo é obrigatório (na tela: {celula(aba, 'sexo', COLUNA_OBRIGATORIO)})",
             celula(aba, "sexo", COLUNA_OBRIGATORIO) == "Sim")
    faixa_do_salario = celula(aba, "valor_renda", COLUNA_FAIXA)
    conferir(f"a coluna Faixa: o salário a partir de R$ 500,00, o CPF sem faixa (na tela: {faixa_do_salario})",
             faixa_do_salario == "a partir de R$ 500,00" and celula(aba, "cpf", COLUNA_FAIXA) == "—")
    # Num campo de texto, a faixa nem aparece
    abrir_o_campo(aba, "cpf")
    conferir("no CPF (texto), a janela não mostra mínimo nem máximo", aba.locator("[data-faixa-do-campo]").is_hidden())
    aba.click("[data-cancelar-campo]")
    # No salário: o mínimo preenchido e o máximo vazio
    abrir_o_campo(aba, "valor_renda")
    minimo = aba.input_value("[data-campo-limite='minimo']")
    conferir(f"no salário, a janela mostra o mínimo 500,00 e o máximo vazio (na tela: {minimo})",
             aba.locator("[data-faixa-do-campo]").is_visible() and minimo == "500,00"
             and aba.input_value("[data-campo-limite='maximo']") == "")
    # O mínimo maior que o máximo: a janela explica e não grava
    aba.fill("[data-campo-limite='maximo']", "400")
    aba.click("[data-salvar-campo]")
    aba.locator("[data-erro-janela-campo]:not([hidden])").wait_for(timeout=10000)
    conferir(f"mínimo maior que o máximo é recusado (na tela: {aba.inner_text('[data-erro-janela-campo]')})",
             "mínimo não pode ser maior" in aba.inner_text("[data-erro-janela-campo]")
             and "Value error" not in aba.inner_text("[data-erro-janela-campo]"))
    # Um máximo válido: grava a versão nova, e o registro diz em reais
    aba.fill("[data-campo-limite='maximo']", "90.000,00")
    aba.click("[data-salvar-campo]")
    aba.wait_for_function("() => document.querySelector('[data-corpo-registro] tr').innerText.includes('máximo')",
                          timeout=15000)
    registro = primeira_linha_do_registro(aba)
    conferir(f"o registro diz o máximo em reais (na tela: {registro[:160]})",
             "valor_renda · máximo: sem limite → R$ 90.000,00" in registro)
    faixa_nova = celula(aba, "valor_renda", COLUNA_FAIXA)
    conferir(f"a coluna Faixa mostra os dois lados (na tela: {faixa_nova})",
             faixa_nova == "R$ 500,00 a R$ 90.000,00")
    aba.locator(".tabela-parametros").screenshot(path="storage/painel/parametros_do_layout.png")
    aba.close()


# ============================== Portal da empresa: os cartões ==============================

def cartao(aba, informacao: str, nome: str):
    """O cartão da informação de uma pessoa em Acompanhar (pelo título, que diz a informação e de quem é)."""
    titulo = aba.locator(".ajuste-titulo", has_text=f'"{informacao}" de {nome}')
    return aba.locator("[data-pendencia]").filter(has=titulo).first


def respostas_rapidas(cartao_da_pessoa) -> list[str]:
    """Os textos das respostas rápidas (pílulas) do cartão."""
    return cartao_da_pessoa.locator("[data-sugestao-da-conversa]").all_inner_texts()


def conferir_os_cartoes_do_sexo(aba, conferir) -> None:
    """O sexo vazio e o "Não informado" viram cartões com F e M."""
    sem_sexo = cartao(aba, INFORMACAO_DO_SEXO, PESSOA_SEM_SEXO[0])
    sem_sexo.wait_for(timeout=30000)
    # A conversa de cada cartão abre no painel do lado (ADR-138)
    sem_sexo = abrir_a_conversa(aba, sem_sexo)
    pergunta = sem_sexo.locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"o sexo vazio vira um cartão que pergunta (na tela: {pergunta})",
             "veio sem a informação" in pergunta and pergunta.strip().endswith("?"))
    conferir(f"as respostas rápidas do sexo são F e M (na tela: {respostas_rapidas(sem_sexo)})",
             respostas_rapidas(sem_sexo)[:2] == ["F", "M"])
    nao_informado = abrir_a_conversa(aba, cartao(aba, INFORMACAO_DO_SEXO, PESSOA_MENSAL[0]))
    pergunta = nao_informado.locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"'Não informado' não é aceito e vira cartão (na tela: {pergunta})",
             '"Não informado"' in pergunta and "F" in respostas_rapidas(nao_informado))


def conferir_o_cartao_do_tipo_de_renda(aba, conferir) -> None:
    """ "Mensal" não vira CLT: o cartão oferece CLT, PRO_LABORE e OUTROS; OUTROS resolve. "Outro" nem vira cartão."""
    do_tipo = cartao(aba, INFORMACAO_DO_TIPO, PESSOA_MENSAL[0])
    do_tipo.wait_for(timeout=30000)
    do_tipo = abrir_a_conversa(aba, do_tipo)
    pergunta = do_tipo.locator("[data-pergunta-da-pendencia]").inner_text()
    respostas = respostas_rapidas(do_tipo)
    conferir(f"'Mensal' vira um cartão sem palpite de CLT (na tela: {pergunta})",
             '"Mensal"' in pergunta and "Acredito" not in pergunta and "Sim, use" not in " ".join(respostas))
    conferir(f"as opções do cartão são CLT, PRO_LABORE e OUTROS (na tela: {respostas})",
             respostas[:3] == ["CLT", "PRO_LABORE", "OUTROS"])
    conferir("o tipo 'Outro' foi aceito: nenhum cartão do tipo de renda para Gil",
             aba.locator(".ajuste-titulo", has_text=f'"{INFORMACAO_DO_TIPO}" de {PESSOA_ABAIXO_DO_PISO[0]}').count() == 0)
    do_tipo.locator("[data-sugestao-da-conversa]", has_text="OUTROS").click()
    pronto = aba.locator(".mudanca-da-ia", has_text="OUTROS").first
    pronto.wait_for(timeout=30000)
    conferir(f"o clique em OUTROS resolve o cartão (na tela: {pronto.inner_text()[:160]})",
             "Pronto:" in pronto.inner_text())


def conferir_o_alerta_de_faixa(aba, conferir) -> None:
    """O salário abaixo do piso vira alerta, com o limite e o "Está certo assim"."""
    do_salario = cartao(aba, INFORMACAO_DO_SALARIO, PESSOA_ABAIXO_DO_PISO[0])
    do_salario.wait_for(timeout=30000)
    do_salario = abrir_a_conversa(aba, do_salario)
    problema = do_salario.locator("[data-problema-do-cartao]").inner_text()
    pergunta = do_salario.locator("[data-pergunta-da-pendencia]").inner_text()
    conferir(f"a linha do problema diz a faixa (na tela: {problema})",
             problema == "Problema: valor fora da faixa esperada pelo banco")
    conferir(f"a pergunta diz o limite e pede confirmação (na tela: {pergunta})",
             "abaixo do mínimo do parâmetro (R$ 500,00)" in pergunta and pergunta.strip().endswith("Está certo?"))
    conferir(f"a resposta rápida é 'Está certo assim' (na tela: {respostas_rapidas(do_salario)})",
             "Está certo assim" in respostas_rapidas(do_salario))
    aba.locator("#pendencias").screenshot(path="storage/painel/cartoes_do_adr_128.png")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Os cliques: os cartões da empresa em Acompanhar e, depois, a tela Parâmetros do banco."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    conferir_os_cartoes_do_sexo(aba, conferir)
    conferir_o_alerta_de_faixa(aba, conferir)
    conferir_o_cartao_do_tipo_de_renda(aba, conferir)
    aba.close()
    conferir_a_tela_de_parametros(navegador, endereco, conferir, erros_da_pagina)
