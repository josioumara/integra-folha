"""Roteiro: a tela "Acompanhamento dos agentes" (Sistema do Portal Interno), com um cartão por agente de IA, o filtro
por período e a aceitação de cada agente, só com o que aconteceu com o modelo real.

O que ele confere, no Chrome de verdade, com o que grava no banco de teste:
    - 3 execuções do Interpretador com o modelo real, há minutos (uma deu certo, com o custo medido; uma com erro; uma
      barrada pelo guardrail), e 1 dele há 60 dias (fora dos 30 dias, dentro dos 90);
    - 2 execuções SIMULADAS (a IA em MOCK) do Endomarketing, há minutos: não podem aparecer em lugar nenhum;
    - 1 decisão de pessoa (sem modelo), há minutos, e 1 execução antiga do Consultor, há 45 dias (ele saiu do sistema,
      ADR-144, mas o gasto dele não se apaga);
    - 1 mapeamento aceito pela empresa hoje, proposto pelo modelo real, com 4 colunas do Interpretador: 3 mantidas e 1
      trocada de campo (aceitação de 75%);
e então:
- a tela abre pelo menu Sistema ("Acompanhamento dos agentes") e tem esse título; o padrão é "Últimos 30 dias";
- os cartões aparecem na ordem do fluxo, a mesma que o servidor manda; o Consultor não tem cartão;
- o Interpretador, nos 30 dias, mostra "3 execuções", "1 deu certo", "1 com erro", "1 barrada pelo guardrail", a última
  execução com data e hora e o custo medido ("US$ 0,0142"); nenhum cartão tem mais o selo do modo (simulado × real);
- a aceitação: o texto que explica a acurácia na operação (só com as propostas do modelo real); no Interpretador,
  "75%", "3 aprovadas sem mudança", "1 corrigida" e "0 recusadas"; no Agente de validação, "não medido", com o porquê;
- o Endomarketing (só simulado) e o Leitor (sem nada) dizem "Sem execuções com o modelo real no período.", sem números;
- as execuções recentes: as 3 do Interpretador e a decisão de pessoa ("sem modelo" no custo), nenhuma do Endomarketing;
- o custo por etapa: só o Interpretador, "3 (1 medida)", com os tokens e o custo medido;
- ocultos: a qualidade do Interpretador (EXP-008) e os números de custo do alto; a frase do registro dos experimentos
  saiu;
- uma ação nova aparece: a empresa manda uma planilha e, ao voltar para a aba do Acompanhamento, as etapas de verdade
  (a Regra e a busca no RAG, sem modelo) entram nas execuções recentes; a leitura simulada do Interpretador, não;
- o filtro troca os números: "Últimos 90 dias" e "Tudo" mostram 4 execuções do Interpretador (e, em Tudo, o Leitor diz
  "Ainda sem execuções com o modelo real."); "De/até" em volta do dia de 60 dias atrás mostra 1; o período escolhido
  fica no endereço e continua valendo depois de recarregar a página;
- nenhum erro de JavaScript (o rodar.py reprova qualquer erro da página).
"""
import re

from tests.e2e.apoio import LOGIN_DA_EMPRESA, LOGIN_DO_BANCO, entrar

DESCRICAO = ("Acompanhamento dos agentes: só o modelo real (o simulado não aparece), cartões na ordem do fluxo, "
             "aceitação (75% no Interpretador), custo medido, 'Sem execuções com o modelo real no período', EXP-008 e "
             "custos do alto ocultos, uma execução nova depois de uma ação e o filtro por período")

# A ordem dos agentes na tela (a ordem do fluxo, do arquivo da empresa até o Endomarketing do banco), pelo
# identificador; o Consultor saiu do sistema (ADR-144)
ORDEM_DOS_AGENTES = ["leitor_de_documentos", "conferidor_da_leitura", "interpretador", "assistente_de_correcao",
                     "validacao_perguntas", "endomarketing", "guardrail_bedrock"]

# O modelo real das execuções de teste (a origem fica REAL) e o do modo simulado (a origem fica MOCK)
MODELO_REAL = "claude-sonnet-4-6"
MODELO_SIMULADO = "mock"

# Há quantos dias foi a execução antiga do Consultor (fora dos 30 dias; longe do De/até da execução antiga do
# Interpretador)
DIAS_DA_EXECUCAO_DO_CONSULTOR = 45

# As situações das 3 execuções recentes do Interpretador que o roteiro grava: (situação, o guardrail agiu?)
EXECUCOES_DO_INTERPRETADOR = [("OK", False), ("ERRO", False), ("BLOQUEADO", True)]

# O custo medido pelo provedor na execução do Interpretador que deu certo (e os tokens dela)
CUSTO_MEDIDO = 0.0142
TOKENS_DE_ENTRADA, TOKENS_DE_SAIDA = 1200, 300

# Há quantos dias foi a execução antiga do Interpretador (fora dos 30 dias, dentro dos 90)
DIAS_DA_EXECUCAO_ANTIGA = 60

# As 4 colunas do mapeamento aceito: (coluna, campo que ficou, origem). "humano" = a empresa trocou o campo
COLUNAS_DO_MAPEAMENTO = [("CPF", "cpf", "llm"), ("Nome", "nome", "llm"), ("Cargo", "cargo", "llm"),
                         ("Salário", "valor_renda", "humano")]

# Data e hora no jeito brasileiro, como a tela escreve a última execução (ex.: "28/09/2026, 10:12")
FORMATO_DA_DATA_E_HORA = re.compile(r"\d{2}/\d{2}/\d{4}, \d{2}:\d{2}")

# Os seletores da tela
GRADE_DOS_CARTOES = "[data-cartoes-agentes]"
CORPO_DAS_EXECUCOES = "[data-corpo-execucoes]"
CORPO_DO_CUSTO_POR_ETAPA = "[data-corpo-custo-por-etapa]"
PILULA_DO_PERIODO = "[data-escolha-do-periodo] [data-periodo='{tipo}']"

# O que o cartão diz quando o agente não rodou com o modelo real no período (e em Tudo)
SEM_EXECUCAO_REAL_NO_PERIODO = "Sem execuções com o modelo real no período."
SEM_EXECUCAO_REAL_AINDA = "Ainda sem execuções com o modelo real."

# O script que lê os identificadores dos cartões, na ordem da tela
IDENTIFICADORES_DOS_CARTOES = """() => {
  const identificadores = [];
  for (const cartao of document.querySelectorAll("[data-cartoes-agentes] [data-cartao-agente]")) {
    identificadores.push(cartao.getAttribute("data-cartao-agente"));
  }
  return identificadores;
}"""

# O script que diz se a tela terminou de carregar os cartões e a tabela (nada mais esperando a API)
TELA_CARREGADA = """() => document.querySelector("[data-cartoes-agentes]").hasAttribute("data-dado-pronto")
  && document.querySelector("[data-tabela-execucoes]").hasAttribute("data-dado-pronto")"""

# O script que espera o cartão do Interpretador mostrar um total de execuções (o argumento é o texto esperado)
INTERPRETADOR_MOSTRA = """(esperado) => {
  const cartao = document.querySelector("[data-cartoes-agentes] [data-cartao-agente='interpretador']");
  return cartao !== null && cartao.innerText.includes(esperado);
}"""

# O script que espera uma linha das execuções recentes com o texto pedido (o argumento é o texto)
EXECUCOES_TEM_A_LINHA = """(texto) => {
  for (const linha of document.querySelectorAll("[data-corpo-execucoes] tr")) {
    if (linha.innerText.includes(texto)) {
      return true;
    }
  }
  return false;
}"""


def preparar() -> dict:
    """Os usuários de teste, as execuções (reais e simuladas), um mapeamento aceito hoje e a planilha da empresa."""
    from datetime import datetime, timedelta, timezone

    from models.contratos import ItemMapeamento, MappingPlan, StatusMapeamento
    from services import auth, execucoes, mapeamentos
    from services.uso_da_ia import Uso
    from tests.e2e.apoio import criar_planilha_com_endereco, criar_usuarios_de_teste
    # Abre o banco temporário e cadastra o RH da Aurora e o especialista do banco
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    agora = datetime.now(timezone.utc)
    # As 3 execuções recentes do Interpretador, com o modelo real; a que deu certo tem o custo medido pelo provedor
    for posicao, situacao_e_guardrail in enumerate(EXECUCOES_DO_INTERPRETADOR):
        situacao = situacao_e_guardrail[0]
        guardrail_agiu = situacao_e_guardrail[1]
        inicio = agora - timedelta(minutes=10 - posicao)
        fim = inicio + timedelta(seconds=3.2)
        uso = None
        if situacao == "OK":
            uso = Uso(chamadas=1, tokens_entrada=TOKENS_DE_ENTRADA, tokens_saida=TOKENS_DE_SAIDA, custo_usd=CUSTO_MEDIDO)
        execucoes.registrar(conexao, f"roteiro-agentes-{posicao}", "EMP001", "interpretar", "Interpretador", inicio,
                            fim, situacao, modelo=MODELO_REAL, guardrail_disparado=guardrail_agiu, uso=uso)
    # 2 execuções simuladas do Endomarketing (a IA em MOCK): nenhuma pode aparecer na tela
    for posicao in range(2):
        inicio = agora - timedelta(minutes=5 - posicao)
        execucoes.registrar(conexao, f"endomarketing-roteiro-{posicao}", "EMP001", "gerar_material:GERADO",
                            "Endomarketing", inicio, inicio + timedelta(seconds=0.4), "OK", modelo=MODELO_SIMULADO)
    # Uma decisão de pessoa (sem modelo): aconteceu de verdade, então entra nas execuções recentes
    inicio_da_decisao = agora - timedelta(minutes=2)
    execucoes.registrar(conexao, "roteiro-agentes-0", "EMP001", "aprovar_mapeamento", "Humano", inicio_da_decisao,
                        inicio_da_decisao + timedelta(seconds=0.1), "OK")
    # A execução antiga do Interpretador (fora dos 30 dias, dentro dos 90), com o modelo real
    inicio_antigo = agora - timedelta(days=DIAS_DA_EXECUCAO_ANTIGA)
    execucoes.registrar(conexao, "roteiro-agentes-antigo", "EMP001", "interpretar", "Interpretador", inicio_antigo,
                        inicio_antigo + timedelta(seconds=3.0), "OK", modelo=MODELO_REAL)
    # A execução antiga do Consultor, gravada antes de ele sair do sistema (ADR-144): fica no banco, sem cartão
    inicio_do_consultor = agora - timedelta(days=DIAS_DA_EXECUCAO_DO_CONSULTOR)
    execucoes.registrar(conexao, "roteiro-agentes-consultor", "EMP001", "pergunta:RESPONDIDO", "Consultor (agente único)",
                        inicio_do_consultor, inicio_do_consultor + timedelta(seconds=0.4), "OK", modelo=MODELO_REAL)
    # O mapeamento aceito hoje pela empresa, proposto pelo modelo real: 3 colunas como ele propôs e 1 trocada de campo
    itens = []
    for nome_da_coluna, campo, origem in COLUNAS_DO_MAPEAMENTO:
        itens.append(ItemMapeamento(coluna=nome_da_coluna, campo=campo, status=StatusMapeamento.PROPOSTO,
                                    justificativa="Nome equivalente.", origem=origem))
    plano = MappingPlan(processamento_id="roteiro-agentes-0", versao_layout=1, configuracao="B3", modelo=MODELO_REAL,
                        versao_prompt="roteiro", itens=itens, chamou_llm=True)
    mapeamentos._preparar(conexao)
    conexao.execute("INSERT INTO mapeamentos (processamento_id, empresa_id, status, plano, criado_em, aprovado_por, "
                    "aprovado_em) VALUES (?, 'EMP001', 'APROVADO', ?, ?, 'rh', ?)",
                    ("roteiro-agentes-0", plano.model_dump_json(), agora.isoformat(timespec="seconds"),
                     agora.isoformat(timespec="seconds")))
    conexao.commit()
    conexao.close()
    # O De/até em volta da execução antiga: um dia antes e um depois (a folga cobre a diferença entre o dia do
    # computador e o dia do servidor, em UTC), bem longe das execuções recentes
    dia_antigo = inicio_antigo.astimezone().date()
    return {"de": (dia_antigo - timedelta(days=1)).isoformat(), "ate": (dia_antigo + timedelta(days=1)).isoformat(),
            "planilha": criar_planilha_com_endereco()}


def texto_do_cartao(aba, agente: str) -> str:
    """O texto inteiro do cartão de um agente (ex.: agente "interpretador")."""
    return aba.inner_text(f"{GRADE_DOS_CARTOES} [data-cartao-agente='{agente}']")


def texto_da_aceitacao(aba, agente: str) -> str:
    """O texto do bloco da aceitação no cartão de um agente."""
    return aba.inner_text(f"{GRADE_DOS_CARTOES} [data-cartao-agente='{agente}'] [data-aceitacao]")


def quantos_numeros_no_cartao(aba, agente: str) -> int:
    """Quantos blocos de números de execução o cartão tem (o total e as contagens do trabalho); 0 quando nenhum."""
    cartao = f"{GRADE_DOS_CARTOES} [data-cartao-agente='{agente}']"
    return aba.locator(f"{cartao} .cartao-agente-total, {cartao} > .cartao-agente-contagens").count()


def linhas_das_execucoes(aba) -> list[str]:
    """O texto de cada linha da tabela das execuções recentes."""
    return aba.locator(CORPO_DAS_EXECUCOES + " tr").all_inner_texts()


def esperar_o_interpretador(aba, esperado: str) -> None:
    """Espera o cartão do Interpretador mostrar o texto esperado (ex.: "4 execuções") depois de trocar o período."""
    aba.wait_for_function(INTERPRETADOR_MOSTRA, arg=esperado, timeout=20000)


def conferir_a_chegada_pelo_menu(aba, endereco: str, conferir) -> None:
    """Parte 1: o item "Acompanhamento dos agentes" do menu Sistema abre a tela, com esse título e 30 dias."""
    aba.goto(endereco + "/banco_inicio.html")
    aba.click(".acoes-usuario [data-botao-configuracao]")
    aba.click("[data-itens-configuracao] a:has-text('Acompanhamento dos agentes')")
    aba.wait_for_url("**/banco_agentes.html", timeout=10000)
    aba.wait_for_function(TELA_CARREGADA, timeout=20000)
    conferir("o menu Sistema abre o Acompanhamento dos agentes, com esse título",
             aba.inner_text("h1.titulo-pagina").strip().startswith("Acompanhamento dos agentes"))
    pilula_dos_30 = aba.get_attribute(PILULA_DO_PERIODO.format(tipo="30"), "aria-pressed")
    conferir(f"o período padrão é 'Últimos 30 dias' (aria-pressed: {pilula_dos_30})", pilula_dos_30 == "true")


def conferir_a_ordem(aba, endereco: str, conferir) -> None:
    """Parte 2: os cartões na ordem do fluxo, a mesma que o servidor manda."""
    na_tela = aba.evaluate(IDENTIFICADORES_DOS_CARTOES)
    # A ordem que o servidor mandou (a tela não pode reordenar); aba.request usa a mesma sessão do navegador
    resposta = aba.request.get(endereco + "/api/banco/telemetria/ia")
    do_servidor = []
    for cartao in resposta.json()["cartoes_por_agente"]:
        do_servidor.append(cartao["agente"])
    conferir(f"os cartões estão na ordem do fluxo (na tela: {na_tela})", na_tela == ORDEM_DOS_AGENTES)
    conferir("a ordem da tela é a mesma do servidor", na_tela == do_servidor)
    conferir("o Consultor saiu: nenhum cartão dele",
             aba.locator(f"{GRADE_DOS_CARTOES} [data-cartao-agente='consultor']").count() == 0)


def conferir_quem_rodou(aba, conferir) -> None:
    """Parte 3: o Interpretador (3 execuções com o modelo real nos 30 dias) mostra as contagens e o custo medido."""
    texto = texto_do_cartao(aba, "interpretador")
    conferir(f"Interpretador: 3 execuções nos 30 dias (no cartão: {texto!r})", "3 execuções" in texto)
    conferir("Interpretador: 1 deu certo, 1 com erro e 1 barrada pelo guardrail",
             "1 deu certo" in texto and "1 com erro" in texto and "1 barrada pelo guardrail" in texto)
    conferir("Interpretador: a última execução tem data e hora no jeito brasileiro",
             FORMATO_DA_DATA_E_HORA.search(texto) is not None)
    conferir("Interpretador: o custo medido pelo provedor ('US$ 0,0142')", "US$ 0,0142" in texto)
    # Tudo é do modelo real: nenhum cartão tem mais o selo do modo nem as linhas do simulado
    selos_do_modo = aba.locator(f"{GRADE_DOS_CARTOES} .cartao-agente-topo .selo").count()
    conferir(f"nenhum cartão tem o selo do modo (selos: {selos_do_modo})", selos_do_modo == 0)
    conferir("nenhum cartão fala em 'Simuladas (MOCK)'", "MOCK" not in aba.inner_text(GRADE_DOS_CARTOES))


def conferir_a_aceitacao(aba, conferir) -> None:
    """Parte 4: o texto da acurácia na operação, a aceitação do Interpretador (75%) e o "não medido" do Agente de
    validação."""
    explicacao = aba.inner_text("[data-texto-aceitacao]")
    conferir(f"o texto explica a acurácia na operação × contra gabarito, só com o modelo real (texto: {explicacao!r})",
             "acurácia na operação" in explicacao and "gabarito" in explicacao and "modelo real" in explicacao)
    do_interpretador = texto_da_aceitacao(aba, "interpretador")
    conferir(f"Interpretador: aceitação de 75% (no bloco: {do_interpretador!r})", "75%" in do_interpretador)
    conferir("Interpretador: 3 aprovadas sem mudança, 1 corrigida e 0 recusadas",
             "3 aprovadas sem mudança" in do_interpretador and "1 corrigida" in do_interpretador
             and "0 recusadas" in do_interpretador)
    da_validacao = texto_da_aceitacao(aba, "validacao_perguntas")
    conferir(f"Agente de validação: aceitação 'não medido', com o porquê (no bloco: {da_validacao!r})",
             "não medido" in da_validacao and "não sugere a resposta" in da_validacao and "%" not in da_validacao)


def conferir_quem_nao_rodou_com_o_modelo_real(aba, conferir) -> None:
    """Parte 5: o Endomarketing (só simulado) e o Leitor (nada) dizem que não houve execução com o modelo real."""
    for agente in ("endomarketing", "leitor_de_documentos"):
        texto = texto_do_cartao(aba, agente)
        conferir(f"{agente}: '{SEM_EXECUCAO_REAL_NO_PERIODO}', sem contagens (no cartão: {texto!r})",
                 SEM_EXECUCAO_REAL_NO_PERIODO in texto and quantos_numeros_no_cartao(aba, agente) == 0)
        conferir(f"{agente}: nada de 'Não trabalhou'", "Não trabalhou" not in texto)


def conferir_as_execucoes_recentes(aba, conferir) -> None:
    """Parte 6: as execuções recentes trazem as 3 do Interpretador e a decisão de pessoa; nada do simulado."""
    linhas = linhas_das_execucoes(aba)
    do_interpretador = []
    for linha in linhas:
        if "Interpretador" in linha:
            do_interpretador.append(linha)
    conferir(f"execuções recentes: as 3 do Interpretador nos 30 dias (linhas: {len(linhas)})",
             len(do_interpretador) == 3)
    conferir("execuções recentes: nenhuma do Endomarketing simulado", "Endomarketing" not in " ".join(linhas))
    # A decisão de pessoa: sem modelo, então sem custo de IA
    da_pessoa = []
    for linha in linhas:
        if "Humano" in linha:
            da_pessoa.append(linha)
    conferir("execuções recentes: a decisão de pessoa, com 'sem modelo' no custo",
             len(da_pessoa) == 1 and "sem modelo" in da_pessoa[0])
    conferir("execuções recentes: a do Interpretador que deu certo, com o custo medido",
             "US$ 0,0142" in " ".join(do_interpretador))
    # O sobretítulo aparece em maiúsculas (o estilo da página): compara em minúsculas
    sobretitulo = aba.inner_text("[data-sobretitulo-execucoes]").lower()
    conferir(f"execuções recentes: o resumo conta as 4 execuções reais (resumo: {sobretitulo!r})",
             "4 execuções" in sobretitulo and "sem as simuladas" in sobretitulo)


def conferir_o_custo_por_etapa(aba, conferir) -> None:
    """Parte 7: o custo por etapa tem só o Interpretador, com 1 medida de 3 execuções, os tokens e o custo."""
    linhas = aba.locator(CORPO_DO_CUSTO_POR_ETAPA + " tr").all_inner_texts()
    conferir(f"custo por etapa: uma linha só, a do Interpretador (linhas: {linhas!r})",
             len(linhas) == 1 and "Interpretador" in linhas[0])
    if linhas:
        conferir("custo por etapa: '3 (1 medida)', os tokens '1.200 / 300' e 'US$ 0,0142'",
                 "3 (1 medida)" in linhas[0] and "1.200 / 300" in linhas[0] and "US$ 0,0142" in linhas[0])


def conferir_o_que_ficou_oculto(aba, conferir) -> None:
    """Parte 8: a qualidade do Interpretador (EXP-008) e os números de custo do alto estão ocultos; a frase saiu."""
    conferir("a qualidade do Interpretador (EXP-008) não aparece",
             aba.locator("#titulo-qualidade").count() == 0 and "Qualidade do Interpretador" not in aba.inner_text("main"))
    conferir("os números de custo do alto não aparecem (o gasto × os tetos e o custo do período)",
             aba.locator("[data-teto-de-gasto]").is_hidden() and aba.locator("[data-custo-do-periodo]").is_hidden())
    conferir("nada fica esperando para sempre (nem os números ocultos)",
             aba.locator("[data-teto-de-gasto]").get_attribute("data-dado-pronto") is not None)
    conferir("a frase 'Um registro por experimento, nunca sobrescrito' saiu",
             "nunca sobrescrito" not in aba.inner_text("main"))
    conferir("a linha do tempo dos experimentos continua", aba.locator("#titulo-experimentos").is_visible())


def conferir_uma_execucao_nova(navegador, aba, endereco: str, dados: dict, conferir, erros_da_pagina) -> None:
    """Parte 9: a empresa manda uma planilha; ao voltar para a aba do Acompanhamento, as etapas de verdade aparecem."""
    antes = len(linhas_das_execucoes(aba))
    aba_da_empresa = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba_da_empresa.goto(endereco + "/cadastrar.html")
    aba_da_empresa.set_input_files("#campo-arquivo", dados["planilha"])
    aba_da_empresa.locator("#resultado-real:not([hidden])").wait_for(timeout=60000)
    aba_da_empresa.close()
    # A pessoa volta para a aba do Acompanhamento: a tela busca os números de novo (o evento de "voltar à aba")
    aba.bring_to_front()
    aba.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    aba.wait_for_function(EXECUCOES_TEM_A_LINHA, arg="perfilar", timeout=20000)
    depois = linhas_das_execucoes(aba)
    conferir(f"depois da ação, as execuções recentes cresceram ({antes} → {len(depois)} linhas)", len(depois) > antes)
    da_regra = []
    for linha in depois:
        if "perfilar" in linha:
            da_regra.append(linha)
    conferir("a etapa nova (a Regra, 'perfilar') aparece, com 'sem modelo'",
             len(da_regra) == 1 and "sem modelo" in da_regra[0])
    # A leitura das colunas foi simulada (o roteiro roda em MOCK): não entra
    do_interpretador = []
    for linha in depois:
        if "Interpretador" in linha:
            do_interpretador.append(linha)
    conferir("a leitura simulada do Interpretador não entra (continuam 3 linhas dele)", len(do_interpretador) == 3)
    esperar_o_interpretador(aba, "3 execuções")
    conferir("o cartão do Interpretador continua com 3 execuções", "3 execuções" in texto_do_cartao(aba, "interpretador"))


def conferir_o_filtro_por_periodo(aba, dados: dict, conferir) -> None:
    """Parte 10: as pílulas e o De/até trocam os números, e o período escolhido fica no endereço."""
    # 90 dias: a execução antiga entra (4 no total)
    aba.click(PILULA_DO_PERIODO.format(tipo="90"))
    esperar_o_interpretador(aba, "4 execuções")
    conferir(f"'Últimos 90 dias': 4 execuções do Interpretador e o endereço com periodo=90 ({aba.url})",
             "periodo=90" in aba.url)
    # Tudo: as 4, e o Leitor, que nunca rodou com o modelo real, diz isso
    aba.click(PILULA_DO_PERIODO.format(tipo="tudo"))
    aba.wait_for_function("() => window.location.search.includes('periodo=tudo')", timeout=10000)
    esperar_o_interpretador(aba, "4 execuções")
    aba.wait_for_function("(texto) => document.querySelector(\"[data-cartao-agente='leitor_de_documentos']\")"
                          ".innerText.includes(texto)", arg=SEM_EXECUCAO_REAL_AINDA, timeout=20000)
    conferir(f"'Tudo': 4 execuções do Interpretador e o Leitor '{SEM_EXECUCAO_REAL_AINDA}'", True)
    # A execução antiga do Consultor está no período, mas ele saiu do sistema: continua sem cartão
    conferir("'Tudo': a execução antiga do Consultor não vira cartão",
             aba.locator(f"{GRADE_DOS_CARTOES} [data-cartao-agente='consultor']").count() == 0
             and aba.evaluate(IDENTIFICADORES_DOS_CARTOES) == ORDEM_DOS_AGENTES)
    # De/até em volta da execução antiga: só ela (1 execução)
    aba.click(PILULA_DO_PERIODO.format(tipo="de_ate"))
    aba.fill("[data-campo-de]", dados["de"])
    aba.fill("[data-campo-ate]", dados["ate"])
    aba.click("[data-formulario-de-ate] button[type='submit']")
    esperar_o_interpretador(aba, "1 execução")
    conferir(f"'De/até' de {dados['de']} a {dados['ate']}: 1 execução do Interpretador e as datas no endereço "
             f"({aba.url})", f"de={dados['de']}" in aba.url and f"ate={dados['ate']}" in aba.url)
    # Recarregar a página mantém o período do endereço
    aba.reload()
    aba.wait_for_function(TELA_CARREGADA, timeout=20000)
    esperar_o_interpretador(aba, "1 execução")
    pilula_de_ate = aba.get_attribute(PILULA_DO_PERIODO.format(tipo="de_ate"), "aria-pressed")
    conferir(f"depois de recarregar, o De/até continua escolhido (aria-pressed: {pilula_de_ate})",
             pilula_de_ate == "true")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Entra como especialista do banco, chega à tela pelo menu Sistema e confere cartões, aceitação, o que ficou
    oculto, uma execução nova depois de uma ação e o período."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_a_chegada_pelo_menu(aba, endereco, conferir)
    conferir_a_ordem(aba, endereco, conferir)
    conferir_quem_rodou(aba, conferir)
    conferir_a_aceitacao(aba, conferir)
    conferir_quem_nao_rodou_com_o_modelo_real(aba, conferir)
    conferir_as_execucoes_recentes(aba, conferir)
    conferir_o_custo_por_etapa(aba, conferir)
    conferir_o_que_ficou_oculto(aba, conferir)
    conferir_uma_execucao_nova(navegador, aba, endereco, dados, conferir, erros_da_pagina)
    conferir_o_filtro_por_periodo(aba, dados, conferir)
    aba.close()
