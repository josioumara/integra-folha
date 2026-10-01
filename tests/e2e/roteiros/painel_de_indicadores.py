"""Roteiro: a aba Indicadores, só com o Painel de acompanhamento (com o filtro do alto). O Simulador de Rentabilidade
e o cartão do falso não folha recuperado ficam ocultos nesta versão (ADR-148). A conversa com o Consultor saiu do
sistema (ADR-144).

Os cliques do Simulador (as seções, a conta refeita a cada ajuste, salvar, visualizar e reabrir) saíram deste roteiro
junto com a tela: estão no histórico do Git (a tag antes-do-menu-e-indicadores) e voltam com ela.

O que ele confere, no Chrome de verdade:
- sem ?aba no endereço, abre o Painel de acompanhamento, com as partes do planejamento e do uso das empresas à vista,
  na ordem da história (números, onde as empresas travam, potencial, empresa por empresa), e nada fica esperando;
- a sub-aba "Desempenho da IA" saiu desta tela;
- (ADR-148) não há guias no alto: o endereço do simulador (?aba=simulador) abre o painel, e o simulador, o link para ele
  e o cartão do falso não folha não aparecem (o cartão continua na página, escondido, com os números de verdade); a
  guia do Consultor não existe mais (nem o botão, nem a conversa, nem o texto "Converse com o Consultor");
- os endereços guardados da conversa que saiu (?aba=consultor e #consultor) abrem o painel, sem erro;
- os endereços antigos não quebram: ?aba=uso&empresa=EMP001 cai no painel com a linha do tempo da Aurora;
  ?aba=planejamento#consultor abre o painel; ?aba=ia abre o painel;
- o cartão "tempo até a avaliação do banco" mostra o número em dias úteis quando há envio decidido pelo
  banco (a Aurora: enviada numa segunda às 10h, aprovada na terça às 10h → "1,0");
- o FILTRO DO ALTO: pelo CNPJ de uma filial com pontuação, o painel inteiro fica com a Aurora (números do
  planejamento, funil, linha do tempo e a tabela do uso com uma linha; o endereço guarda ?empresa=); um pedaço do nome
  também acha; um CNPJ de fora da carteira avisa; o estado da sede deixa na tabela só as empresas daquele estado;
  clicar no nome de uma empresa na tabela escolhe ela no filtro; "Limpar o filtro" volta à carteira toda. O funil não
  tem mais a escolha da empresa nem a busca por CNPJ;
- (o planejamento sem a base do banco) os números do alto: 35 Cadastrados da Aurora, 32 aguardando o
  retorno do banco, 1 conta aberta e 2 correntistas, pelo arquivo de contas (ADR-149: o correntista é um grupo só, e a
  situação e a folha gravadas antes não contam); à vista, só esses 4 cartões (o do falso não folha está oculto e,
  sem esse número no resumo, mostra um traço; o banco sempre informa o tipo: não há cartão de "retorno sem o tipo");
  não existe mais "autorizam contato" nem o filtro de segmento;
- as premissas oficiais continuam a v1 e o painel continua lendo-as (a API /api/banco/premissas responde).
"""
from tests.e2e.apoio import LOGIN_DO_BANCO, entrar

DESCRICAO = ("Indicadores: só o Painel de acompanhamento, com o filtro do alto (o Simulador e o falso não folha "
             "ocultos; sem o Consultor)")

# O que ficou oculto nesta versão (ADR-148): os botões das guias, o simulador, o link para ele e os endereços dele
RESTOS_DO_SIMULADOR = ("[data-aba-indicadores], #guia-simulador, [data-conteudo-indicadores='simulador'], "
                       "[data-simulador], [data-ir-para-simulador], a[href*='aba=simulador']")

# As partes do painel, na ordem da história que ele conta
PARTES_DO_PAINEL_NA_ORDEM = ["numeros", "travas", "potencial", "uso-por-empresa"]

# O script que conta os elementos que ainda esperam o dado (zero quando a tela terminou de carregar)
CONTAR_OS_QUE_ESPERAM = ("() => document.querySelectorAll('[data-aguarda-dado]:not([data-dado-pronto]), "
                         "[data-aguarda-bloco]:not([data-dado-pronto])').length")

# O script que devolve os elementos que ainda esperam dado, pelo primeiro atributo data- de cada um (para o aviso)
LISTAR_OS_QUE_ESPERAM = """() => {
  const nomes = [];
  for (const elemento of document.querySelectorAll('[data-aguarda-dado]:not([data-dado-pronto]), '
                                                   + '[data-aguarda-bloco]:not([data-dado-pronto])')) {
    const atributos = [];
    for (const atributo of elemento.attributes) {
      if (atributo.name.startsWith('data-') && !atributo.name.startsWith('data-aguarda')) {
        atributos.push(atributo.name + (atributo.value ? '=' + atributo.value : ''));
      }
    }
    nomes.push(atributos.join(' ') || elemento.tagName);
  }
  return nomes;
}"""

# O script que lê as partes do painel na ordem em que aparecem na página
PARTES_NA_PAGINA = """() => {
  const partes = [];
  for (const parte of document.querySelectorAll("[data-parte-painel]")) {
    partes.push(parte.dataset.partePainel);
  }
  return partes;
}"""

# O que ainda restaria da conversa com o Consultor, se ela não tivesse saído: o botão da guia, a guia e a caixa
RESTOS_DA_CONVERSA_DO_CONSULTOR = ("[data-aba-indicadores='consultor'], #guia-consultor, [data-pergunta-consultor], "
                                   "[data-formulario-consultor]")


def preparar() -> dict:
    """A Aurora com a carga inicial cadastrada: o planejamento tem números e o uso tem a linha do tempo dela."""
    import csv

    import rag.busca
    from models.contratos import Perfil
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, empresas, motor_planejamento
    from services.auth import Usuario
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_cnpjs_das_empresas import cnpj_de_outra_raiz, filial_da_aurora
    from tests.test_correcao import RAIZ, busca_falsa
    from tests.test_planejamento import homologar
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (para corrigir tudo e cadastrar a carga inicial)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    processamento_id = homologar(conexao, "aurora_carga_inicial", verdade)
    # O motor de planejamento conta a carga cadastrada (como a aplicação faz depois da homologação)
    motor_planejamento.processar_homologacao(conexao, processamento_id, "EMP001")
    # O retorno do banco de 3 pessoas da Aurora: 1 conta nova, 1 correntista ativo e 1 correntista inativo
    gravar_retorno_do_banco(conexao, verdade)
    # A decisão do banco sobre esse envio, com datas escolhidas (o registro de verdade usa a hora de agora):
    # enviado ao banco na segunda, 21/09/2026, às 10h de Brasília, e aprovado na terça às 10h → 1,0 dia útil
    gravar_evento_com_data(conexao, processamento_id, "ENVIADO_AO_BANCO", "2026-09-21T13:00:00+00:00")
    gravar_evento_com_data(conexao, processamento_id, "APROVADO_PELO_BANCO", "2026-09-22T13:00:00+00:00")
    # Uma filial da Aurora registrada pelo banco (a busca por CNPJ também acha a empresa por ela)
    especialista = Usuario(login=LOGIN_DO_BANCO, perfil=Perfil.BANCO, empresa_id=None)
    cnpj_da_filial = filial_da_aurora()
    empresas.adicionar_cnpj(conexao, especialista, "EMP001", cnpj_da_filial, "FILIAL")
    # O nome e a UF da sede da Aurora como estão no cadastro
    aurora = empresas.obter(conexao, "EMP001")
    # Quantas empresas da carteira têm a sede no estado da Aurora (o filtro de estado deixa só elas na tabela do uso)
    empresas_no_estado_da_aurora = 0
    for empresa in empresas.lista_em_memoria():
        if empresa["uf"] == aurora["uf"]:
            empresas_no_estado_da_aurora = empresas_no_estado_da_aurora + 1
    conexao.close()
    return {"empresa_id": "EMP001", "nome_da_empresa": aurora["nome"], "cnpj_da_filial": cnpj_da_filial,
            "cnpj_de_fora_da_carteira": cnpj_de_outra_raiz(99), "uf_da_aurora": aurora["uf"],
            "empresas_no_estado_da_aurora": empresas_no_estado_da_aurora}


def gravar_retorno_do_banco(conexao, verdade: dict) -> None:
    """Grava o retorno do banco (a tabela do arquivo de contas) de 3 pessoas da Aurora, com o tipo de cada uma."""
    import json

    from services import contas_abertas
    from tests.test_correcao import RAIZ
    # As 3 primeiras pessoas da carga inicial da Aurora, pelo gabarito
    gabarito = json.loads((RAIZ / "data" / "golden" / "aurora_carga_inicial.json").read_text(encoding="utf-8"))
    cpfs = []
    for funcionario_id in gabarito["funcionario_ids"][:3]:
        cpfs.append(verdade[funcionario_id]["cpf"])
    # Lista vazia: só cria as tabelas das contas
    contas_abertas.retorno_por_cpf(conexao, [])
    # Uma conta nova e dois correntistas gravados antes do ADR-149, com a situação e a folha (que não contam mais: o
    # correntista é um grupo só)
    retornos = [(cpfs[0], "NOVA_CONTA", None, None), (cpfs[1], "CORRENTISTA", "ATIVO", "N"),
                (cpfs[2], "CORRENTISTA", "INATIVO", "S")]
    for cpf, tipo_conta, situacao, folha in retornos:
        conexao.execute("INSERT INTO contas_abertas (empresa_id, cpf, data_abertura, agencia, conta, codigo_banco, "
                        "arquivo_id, baixa_em, tipo_conta, situacao_correntista, folha_ja_identificada) VALUES "
                        "('EMP001', ?, '2026-09-20', '0001', '12345', '033', 'roteiro', '2026-09-21T10:00:00+00:00', "
                        "?, ?, ?)", (cpf, tipo_conta, situacao, folha))
    conexao.commit()


def gravar_evento_com_data(conexao, processamento_id: str, tipo: str, quando: str) -> None:
    """Grava um evento da Aurora na auditoria com a data escolhida (auditoria.registrar sempre usa a hora de agora)."""
    from services import auditoria
    # Garante que a tabela de eventos existe
    auditoria.eventos(conexao)
    conexao.execute("INSERT INTO eventos (processamento_id, empresa_id, etapa, tipo, detalhe, criado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (processamento_id, "EMP001", "Avaliação do banco", tipo, "{}", quando))
    conexao.commit()


def com_pontuacao(cnpj: str) -> str:
    """O CNPJ escrito como as pessoas escrevem: "10433218000193" → "10.433.218/0001-93"."""
    return cnpj[:2] + "." + cnpj[2:5] + "." + cnpj[5:8] + "/" + cnpj[8:12] + "-" + cnpj[12:]


def guias_a_mostra(aba) -> list[str]:
    """As guias de Indicadores que estão à vista agora (o esperado é uma só). Ex.: ["painel"]."""
    a_mostra = []
    # Confere uma por uma se o conteúdo da guia está visível
    for guia in ["painel", "simulador"]:
        if aba.locator(f"[data-conteudo-indicadores='{guia}']").is_visible():
            a_mostra.append(guia)
    return a_mostra


def abrir_e_esperar(aba, endereco_da_tela: str) -> None:
    """Abre o endereço e espera todos os dados chegarem (nenhum elemento com a barra de "carregando")."""
    aba.goto(endereco_da_tela)
    try:
        aba.wait_for_function(CONTAR_OS_QUE_ESPERAM + " === 0", timeout=20000)
    except Exception as erro:
        # Passou do tempo: diz quais elementos continuam com a barra de "carregando", para achar o bloco esquecido
        ainda_esperando = aba.evaluate(LISTAR_OS_QUE_ESPERAM)
        raise AssertionError("ainda carregando depois de 20 s: " + ", ".join(ainda_esperando)) from erro


def conferir_o_painel(aba, endereco: str, conferir) -> None:
    """Parte 1: sem ?aba, o painel com o planejamento e o uso à vista, na ordem, e sem o Desempenho da IA."""
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html")
    conferir("sem ?aba: abre o Painel de acompanhamento (só ele à vista)", guias_a_mostra(aba) == ["painel"])
    conferir("não há guias no alto: a tela é só o Painel de acompanhamento (ADR-148)",
             aba.locator("[data-aba-indicadores]").count() == 0)
    # As partes do painel, na ordem da história
    partes = aba.evaluate(PARTES_NA_PAGINA)
    conferir(f"as partes do painel na ordem {PARTES_DO_PAINEL_NA_ORDEM} (na tela: {partes})",
             partes == PARTES_DO_PAINEL_NA_ORDEM)
    # A parte do planejamento: os números de verdade (a Aurora foi cadastrada) e as tabelas do potencial
    cadastrados = numero_do_planejamento(aba, "cadastrados")
    conferir(f"planejamento à vista: Cadastrados que passaram pelo motor (na tela: {cadastrados})",
             aba.locator("[data-numero='cadastrados']").is_visible() and cadastrados not in ("", "—", "0"))
    conferir("o filtro do alto (empresa e estado) está à vista; o simulador não está no painel",
             aba.locator("[data-filtro-empresa-indicadores]").is_visible()
             and aba.locator("[data-filtro-uf-indicadores]").is_visible()
             and aba.locator("#guia-painel [data-premissa-simulador]").count() == 0)
    conferir("o funil não tem mais a escolha da empresa nem a busca por CNPJ",
             aba.locator("[data-escolha-empresa-uso], [data-cnpj-uso], [data-filtro-empresa]").count() == 0)
    linhas_do_potencial = aba.locator("[data-corpo-por-empresa] tr").count()
    conferir(f"planejamento à vista: 'Potencial por empresa' com linhas ({linhas_do_potencial})",
             aba.locator("[data-tabela-por-empresa]").is_visible() and linhas_do_potencial >= 1)
    # A parte do uso: os números do uso, o funil e a tabela das 6 empresas da carteira
    envios = aba.inner_text("[data-uso-envios-valor]").strip()
    conferir(f"uso à vista: envios das empresas (na tela: {envios})",
             aba.locator("[data-uso-envios-valor]").is_visible() and envios not in ("", "—"))
    # O tempo até a avaliação do banco: a Aurora foi aprovada 1 dia útil depois do envio
    tempo = aba.inner_text("[data-uso-tempo-valor]").strip()
    legenda_do_tempo = aba.inner_text("[data-uso-tempo-legenda]").strip()
    conferir(f"uso à vista: tempo até a avaliação do banco com número (na tela: {tempo} · {legenda_do_tempo})",
             tempo == "1,0" and legenda_do_tempo.startswith("dia útil, em média")
             and "1 avaliação" in legenda_do_tempo and "feriados" in legenda_do_tempo)
    conferir("uso à vista: o funil do envio com as etapas",
             aba.locator("[data-funil]").is_visible() and aba.locator("[data-funil] li").count() >= 1)
    linhas_do_uso = aba.locator("[data-corpo-uso] tr").count()
    conferir(f"uso à vista: 'Uso do portal por empresa' com as 6 empresas da carteira ({linhas_do_uso})",
             aba.locator("[data-tabela-uso]").is_visible() and linhas_do_uso == 6)
    # O Desempenho da IA saiu desta tela (foi para a engrenagem, "Acompanhamento dos agentes")
    conferir("a sub-aba 'Desempenho da IA' saiu de Indicadores",
             aba.locator("[data-aba-indicadores='ia'], [data-conteudo-indicadores='ia']").count() == 0
             and "Execuções recentes dos agentes" not in aba.inner_text("main"))


def numero_do_planejamento(aba, nome: str) -> str:
    """O texto de um número do planejamento. Ex.: numero_do_planejamento(aba, "cadastrados") → "35"."""
    return aba.inner_text(f"[data-bloco-de='planejamento'] [data-numero='{nome}']").strip()


def conferir_os_numeros_do_planejamento(aba, endereco: str, conferir) -> None:
    """Parte 6: os números do alto, pelo retorno do banco; sem 'autorizam contato' nem segmento. O cartão
    do falso não folha fica oculto (ADR-148) e, sem esse número no resumo (ADR-149), com um traço."""
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html")
    numeros = {}
    for nome in ("cadastrados", "empresas", "aguardando_retorno", "contas_abertas", "correntistas_marcados"):
        numeros[nome] = numero_do_planejamento(aba, nome)
    conferir(f"os números do alto: 35 Cadastrados (1 empresa), 32 aguardando, 1 conta nova e 2 correntistas "
             f"(na tela: {numeros})",
             numeros == {"cadastrados": "35", "empresas": "1", "aguardando_retorno": "32", "contas_abertas": "1",
                         "correntistas_marcados": "2"})
    # O cartão do falso não folha: oculto nesta versão; o número saiu do resumo (ADR-149), e ele recebe um traço (nunca
    # o número de exemplo nem "NaN")
    cartao_do_falso_nao_folha = aba.locator("[data-oculto-nesta-versao='falso-nao-folha']")
    falso_nao_folha = numero_do_planejamento(aba, "falso_nao_folha")
    conferir(f"o cartão do falso não folha está oculto (ADR-148) e com um traço (na página: {falso_nao_folha})",
             cartao_do_falso_nao_folha.count() == 1 and cartao_do_falso_nao_folha.is_hidden()
             and falso_nao_folha == "—" and "falso não folha recuperados" not in aba.inner_text("#guia-painel"))
    # As tabelas do potencial têm a coluna dos correntistas (e não mais a do falso não folha)
    titulos_da_tabela = aba.locator("[data-tabela-por-empresa] th").all_inner_texts()
    conferir(f"a tabela 'Potencial por empresa' tem a coluna Correntistas (na tela: {titulos_da_tabela})",
             titulos_da_tabela[-1] == "Correntistas" and "Falso não folha" not in titulos_da_tabela)
    cartoes_a_mostra = aba.locator("[data-bloco-de='planejamento'] .grade-numeros .cartao-numero:visible").count()
    conferir(f"no planejamento, 4 cartões à vista (na tela: {cartoes_a_mostra})", cartoes_a_mostra == 4)
    conferir("não existe cartão de 'retorno sem o tipo' (o banco sempre informa o tipo)",
             aba.locator("[data-numero='retorno_sem_tipo']").count() == 0
             and "sem o tipo" not in aba.inner_text("#guia-painel"))
    texto_do_painel = aba.inner_text("#guia-painel")
    conferir("saíram 'autorizam contato' e o filtro de segmento",
             "autoriz" not in texto_do_painel.lower() and aba.locator("[data-filtro-segmento]").count() == 0)
    # As premissas oficiais continuam valendo para o painel (a tela delas está oculta; a API, não)
    versao_oficial = aba.evaluate("async () => (await (await fetch('/api/banco/premissas')).json()).versao")
    conferir(f"as premissas oficiais continuam a v1 e a API responde (versão: {versao_oficial})", versao_oficial == 1)


def conferir_o_simulador_oculto(aba, endereco: str, conferir) -> None:
    """Parte 2 (ADR-148): sem guias; nada do simulador aparece; o endereço dele abre o painel; a guia do Consultor
    também não existe."""
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html")
    restos = aba.locator(RESTOS_DO_SIMULADOR).count()
    conferir(f"nenhum resto do simulador na página: nem guias, nem o simulador, nem o link para ele (achados: {restos})",
             restos == 0)
    conferir("a parte 3 ('O potencial da carteira') não convida mais para o simulador",
             "Simulador de Rentabilidade" not in aba.inner_text("[data-parte-painel='potencial']"))
    conferir("a guia 'Converse com o Consultor' não existe mais (nem o botão, nem a conversa, nem a caixa)",
             aba.locator(RESTOS_DA_CONVERSA_DO_CONSULTOR).count() == 0)
    # Quem guardou o endereço do simulador cai no painel, sem erro
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html?aba=simulador")
    conferir("?aba=simulador (a guia oculta): abre o Painel de acompanhamento, sem o simulador",
             guias_a_mostra(aba) == ["painel"] and aba.locator(RESTOS_DO_SIMULADOR).count() == 0)


def conferir_que_o_consultor_saiu(aba, endereco: str, conferir) -> None:
    """Parte 3: os endereços guardados da conversa que saiu (?aba=consultor e #consultor) abrem o painel, sem erro, e
    o texto da guia que saiu não aparece mais na tela."""
    # O endereço do botão do Início de antes (?aba=consultor)
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html?aba=consultor")
    conferir("?aba=consultor (a conversa que saiu): abre o painel", guias_a_mostra(aba) == ["painel"])
    # Pelo texto exato da guia que saiu (uma empresa chamada "... Consultoria" pode aparecer nas tabelas)
    conferir("nenhum 'Converse com o Consultor' na tela", aba.get_by_text("Converse com o Consultor").count() == 0)
    # A âncora sozinha, de um link mais antigo ainda (#consultor)
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html#consultor")
    conferir("#consultor (a conversa que saiu): abre o painel", guias_a_mostra(aba) == ["painel"])


def conferir_os_enderecos_antigos(aba, endereco: str, dados: dict, conferir) -> None:
    """Parte 4: os endereços de antes caem no lugar certo, sem quebrar."""
    # O "Ver o uso" de antes: ?aba=uso com a empresa
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html?aba=uso&empresa=" + dados["empresa_id"])
    conferir("?aba=uso (antigo): cai no painel", guias_a_mostra(aba) == ["painel"])
    titulo = aba.inner_text("[data-titulo-linha-do-tempo]").strip()
    conferir(f"?aba=uso&empresa={dados['empresa_id']}: a linha do tempo é da {dados['nome_da_empresa']} "
             f"(na tela: {titulo})", titulo == dados["nome_da_empresa"])
    conferir("o funil e o filtro do alto também estão na empresa pedida",
             aba.inner_text("[data-sobre-o-funil]").startswith(dados["nome_da_empresa"])
             and aba.input_value("[data-filtro-empresa-indicadores]").startswith(dados["nome_da_empresa"]))
    acontecimentos = aba.locator("[data-linha-do-tempo] li").all_inner_texts()
    conferir(f"a linha do tempo tem os acontecimentos da empresa ({len(acontecimentos)})",
             len(acontecimentos) >= 1 and "Nenhum arquivo enviado até agora." not in acontecimentos)
    conferir("a tela desce até 'Onde as empresas travam'", aba.evaluate("() => window.scrollY > 0"))
    # O botão do Consultor de antes (a conversa saiu, ADR-144): ?aba=planejamento#consultor
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html?aba=planejamento#consultor")
    conferir("?aba=planejamento#consultor (antigo): abre o painel", guias_a_mostra(aba) == ["painel"])
    # A sub-aba que saiu: ?aba=ia abre o painel
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html?aba=ia")
    conferir("?aba=ia (a sub-aba que saiu): abre o painel", guias_a_mostra(aba) == ["painel"])


def filtrar_pela_empresa(aba, texto: str) -> None:
    """Digita no campo da empresa do filtro do alto e aperta Enter (o painel se refaz)."""
    aba.fill("[data-filtro-empresa-indicadores]", texto)
    aba.press("[data-filtro-empresa-indicadores]", "Enter")


def esperar_linhas_do_uso(aba, quantas: int) -> None:
    """Espera a tabela "Uso do portal por empresa" ficar com esse número de linhas."""
    aba.wait_for_function("(quantas) => document.querySelectorAll('[data-corpo-uso] tr').length === quantas",
                          arg=quantas, timeout=15000)


def conferir_o_filtro_do_alto(aba, endereco: str, dados: dict, conferir) -> None:
    """Parte 5: o filtro do alto (empresa por nome ou CNPJ, e estado) vale para o painel inteiro."""
    abrir_e_esperar(aba, endereco + "/banco_indicadores.html")
    # O CNPJ de uma filial, com pontuação: o painel inteiro fica com a Aurora
    filtrar_pela_empresa(aba, com_pontuacao(dados["cnpj_da_filial"]))
    esperar_linhas_do_uso(aba, 1)
    aba.wait_for_function("() => document.querySelector('[data-titulo-linha-do-tempo]').textContent.trim() !== "
                          "'Escolha uma empresa'", timeout=15000)
    titulo = aba.inner_text("[data-titulo-linha-do-tempo]").strip()
    conferir(f"CNPJ da filial com pontuação: a linha do tempo e o funil são da {dados['nome_da_empresa']} "
             f"(na tela: {titulo})",
             titulo == dados["nome_da_empresa"] and aba.inner_text("[data-sobre-o-funil]").startswith(dados["nome_da_empresa"]))
    conferir("a tabela do uso fica só com a Aurora, e o campo mostra o nome e o CNPJ dela",
             aba.locator("[data-corpo-uso] tr").count() == 1
             and dados["nome_da_empresa"] in aba.inner_text("[data-corpo-uso]")
             and aba.input_value("[data-filtro-empresa-indicadores]").startswith(dados["nome_da_empresa"] + " · "))
    conferir(f"os números do planejamento são os da Aurora (35 Cadastrados; na tela: {numero_do_planejamento(aba, 'cadastrados')})",
             numero_do_planejamento(aba, "cadastrados") == "35")
    conferir(f"o endereço guarda a empresa (?empresa=EMP001): {aba.url}", "empresa=" + dados["empresa_id"] in aba.url)
    # Um CNPJ válido que não é de nenhuma empresa da carteira: avisa, e o filtro continua na Aurora
    filtrar_pela_empresa(aba, com_pontuacao(dados["cnpj_de_fora_da_carteira"]))
    aviso = aba.inner_text("[data-aviso-filtro-indicadores]").strip()
    conferir(f"CNPJ de fora da carteira: avisa e o filtro não muda (na tela: {aviso})",
             aba.locator("[data-aviso-filtro-indicadores]").is_visible()
             and aviso.startswith("Nenhuma empresa da carteira com este nome ou CNPJ")
             and aba.locator("[data-corpo-uso] tr").count() == 1)
    # "Limpar o filtro": a carteira toda de novo
    aba.click("[data-limpar-filtro-indicadores]")
    esperar_linhas_do_uso(aba, 6)
    conferir("'Limpar o filtro' volta à carteira toda (6 empresas, sem aviso, sem empresa no endereço)",
             aba.locator("[data-aviso-filtro-indicadores]").is_hidden() and "empresa=" not in aba.url
             and aba.input_value("[data-filtro-empresa-indicadores]") == "")
    # Um pedaço do nome também acha a empresa
    filtrar_pela_empresa(aba, dados["nome_da_empresa"][:5].lower())
    esperar_linhas_do_uso(aba, 1)
    conferir(f"um pedaço do nome ('{dados['nome_da_empresa'][:5].lower()}') acha a Aurora",
             dados["nome_da_empresa"] in aba.inner_text("[data-corpo-uso]"))
    aba.click("[data-limpar-filtro-indicadores]")
    esperar_linhas_do_uso(aba, 6)
    # O estado: na tabela do uso, só as empresas com a sede nele
    aba.select_option("[data-filtro-uf-indicadores]", dados["uf_da_aurora"])
    esperar_linhas_do_uso(aba, dados["empresas_no_estado_da_aurora"])
    conferir(f"estado {dados['uf_da_aurora']}: a tabela do uso fica com as "
             f"{dados['empresas_no_estado_da_aurora']} empresas com a sede nele, e o endereço guarda o estado",
             aba.locator("[data-corpo-uso] tr").count() == dados["empresas_no_estado_da_aurora"]
             and "uf=" + dados["uf_da_aurora"] in aba.url)
    aba.click("[data-limpar-filtro-indicadores]")
    esperar_linhas_do_uso(aba, 6)
    # Clicar no nome da empresa na tabela escolhe ela no filtro
    aba.click(f"[data-corpo-uso] [data-escolher-empresa='{dados['empresa_id']}']")
    esperar_linhas_do_uso(aba, 1)
    conferir("clicar no nome da Aurora na tabela escolhe ela no filtro do alto",
             aba.input_value("[data-filtro-empresa-indicadores]").startswith(dados["nome_da_empresa"]))
    aba.click("[data-limpar-filtro-indicadores]")
    esperar_linhas_do_uso(aba, 6)


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Entra como especialista do banco e confere o painel, o simulador oculto, a saída do Consultor, os endereços
    antigos, o filtro do alto e os números do planejamento."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    conferir_o_painel(aba, endereco, conferir)
    conferir_o_simulador_oculto(aba, endereco, conferir)
    conferir_que_o_consultor_saiu(aba, endereco, conferir)
    conferir_os_enderecos_antigos(aba, endereco, dados, conferir)
    conferir_o_filtro_do_alto(aba, endereco, dados, conferir)
    conferir_os_numeros_do_planejamento(aba, endereco, conferir)
    aba.close()
