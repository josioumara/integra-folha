"""Roteiro: a linha do tempo de cada envio, na seção "Envios" (Histórico) de Acompanhar.

O defeito: a última etapa caía para a linha de baixo. A sequência tem de ser
"Arquivo carregado → Lido pela IA → Conferido por você → Enviado ao banco → Aprovação das contas enviadas →
Contas abertas", com a última dizendo quantos do envio já têm conta e o percentual ("22 de 35 contas (63%)").

O que ele confere:
- as 6 etapas aparecem, nesta ordem, no envio que acabou de chegar;
- na tela do computador, as 6 ficam na MESMA linha (a bolinha de cada uma está na mesma altura);
- a 1ª etapa está feita (verde) e a 2ª é a atual (a IA ainda não leu o arquivo);
- no envio aprovado, depois do arquivo de contas do banco, "Contas abertas" está feita e diz "3 de N contas (X%)",
  com a bolinha verde clarinho (só parte das contas: não parece concluída);
- no celular, as etapas continuam visíveis, em duas colunas.
"""
from tests.e2e.apoio import LOGIN_DA_EMPRESA, entrar

DESCRICAO = "Linha do tempo do envio: 6 etapas, na ordem, numa linha só, e as contas abertas do envio"
# As etapas que a empresa deve ver no envio que acabou de chegar, na ordem do caminho do envio
ETAPAS_ESPERADAS = ["Arquivo carregado", "Lido pelos agentes", "Conferido por você", "Enviado ao banco",
                    "Aprovação das contas enviadas", "Contas abertas"]
# Quantos funcionários da carga inicial ganham conta no arquivo do banco
CONTAS_NO_ARQUIVO = 3


def preparar() -> dict:
    """A Aurora com a carga inicial aprovada, 3 contas abertas pelo arquivo do banco e um envio novo que acabou de chegar."""
    import csv
    from datetime import date

    import rag.busca
    from models.contratos import Perfil
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, contas_abertas, processamentos
    from services.auth import Usuario
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import RAIZ, busca_falsa
    from tests.test_planejamento import homologar
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (para corrigir tudo e aprovar a carga inicial)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    homologar(conexao, "aurora_carga_inicial", verdade)
    # O arquivo semanal do banco com a conta de 3 funcionários da carga inicial, confirmado pelo especialista
    cpfs = []
    for (cpf,) in conexao.execute("SELECT cpf FROM funcionarios_homologados WHERE empresa_id = 'EMP001' ORDER BY cpf"):
        cpfs.append(cpf)
    # O layout fixo do arquivo de contas, subido por empresa (ADR-122; o formato novo, ADR-149):
    # cpf;status;agencia;conta;data_abertura, com a data em AAAA-MM-DD e o status 1 (Conta nova)
    linhas = ["cpf;status;agencia;conta;data_abertura"]
    for cpf in cpfs[:CONTAS_NO_ARQUIVO]:
        linhas.append(cpf + ";1;0001;" + cpf[-5:] + "-0;2026-09-24")
    especialista = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
    previa = contas_abertas.conferir_arquivo(conexao, especialista, "EMP001", "\n".join(linhas).encode("utf-8"),
                                             "semana.csv")
    contas_abertas.confirmar_baixa(conexao, especialista, previa["arquivo_id"])
    # Um envio novo, que acabou de chegar (arquivo pequeno, sem passar pela IA)
    conteudo = "Nome;Cargo\nPessoa de teste;Analista\n".encode("utf-8")
    processamentos.receber_arquivo(conexao, conteudo, "lista.csv", "EMP001", date(2026, 9, 1), LOGIN_DA_EMPRESA)
    conexao.close()
    # O texto esperado na última etapa da carga inicial: "3 de N contas (X%)"
    percentual = (100 * CONTAS_NO_ARQUIVO) // len(cpfs)
    return {"contas": str(CONTAS_NO_ARQUIVO) + " de " + str(len(cpfs)) + " contas (" + str(percentual) + "%)"}


def alturas_das_bolinhas(aba) -> list:
    """A distância do topo da página até a bolinha de cada etapa do 1º envio (mesma altura = mesma linha)."""
    return aba.evaluate("""() => {
        const envio = document.querySelector('[data-lista-envios] [data-envio]');
        const alturas = [];
        for (const bolinha of envio.querySelectorAll('.linha-do-tempo .passo-marca')) {
            alturas.push(Math.round(bolinha.getBoundingClientRect().top));
        }
        return alturas;
    }""")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Abre Acompanhar e confere as etapas dos dois envios, no computador e no celular."""
    aba = entrar(navegador, endereco, LOGIN_DA_EMPRESA, erros_da_pagina)
    aba.goto(endereco + "/acompanhar.html")
    # Espera os envios de verdade substituírem os exemplos do protótipo
    aba.wait_for_function("() => document.querySelector('[data-contador-envios]').innerText.includes('de 2 envios')",
                          timeout=20000)
    envios = aba.locator("[data-lista-envios] [data-envio]")
    # O envio que acabou de chegar (o 1º da lista): os nomes das etapas, na ordem
    nomes = envios.nth(0).locator(".linha-do-tempo .passo-nome").all_inner_texts()
    conferir("as 6 etapas, na ordem pedida", nomes == ETAPAS_ESPERADAS)
    # Todas as bolinhas na mesma altura: nenhuma etapa caiu para a linha de baixo
    alturas = alturas_das_bolinhas(aba)
    conferir("no computador, as 6 etapas ficam numa linha só", len(alturas) == 6 and len(set(alturas)) == 1)
    # A 1ª feita (verde) e a 2ª atual (a IA ainda não leu o arquivo)
    classes = envios.nth(0).locator(".linha-do-tempo .passo").evaluate_all(
        "passos => passos.map(passo => passo.className)")
    conferir("'Arquivo carregado' feita e 'Lido pelos agentes' atual",
             "passo-feito" in classes[0] and "passo-atual" in classes[1])
    # A carga inicial aprovada (o 2º da lista): "Contas abertas" feita, com o número do arquivo do banco
    ultima = envios.nth(1).locator(".linha-do-tempo .passo").last
    texto_da_ultima = ultima.text_content()
    conferir(f"'Contas abertas' feita, com '{dados['contas']}' (na tela: {texto_da_ultima})",
             "passo-feito" in ultima.get_attribute("class") and "Contas abertas" in texto_da_ultima
             and dados["contas"] in texto_da_ultima)
    # Só parte das contas: a bolinha é verde clarinho (não parece concluída), e a da aprovação, verde cheio
    cor_da_ultima = ultima.locator(".passo-marca").evaluate("bolinha => getComputedStyle(bolinha).backgroundColor")
    passos_da_carga = envios.nth(1).locator(".linha-do-tempo .passo")
    # A penúltima etapa ("Aprovação das contas enviadas")
    aprovacao = passos_da_carga.nth(passos_da_carga.count() - 2)
    cor_da_aprovacao = aprovacao.locator(".passo-marca").evaluate("bolinha => getComputedStyle(bolinha).backgroundColor")
    conferir(f"com só parte das contas, bolinha verde clarinho (na tela: {cor_da_ultima}; aprovação: {cor_da_aprovacao})",
             cor_da_ultima == "rgb(227, 244, 234)" and cor_da_aprovacao == "rgb(0, 132, 55)")
    # O rodapé da lista de envios com singular e plural certos
    conferir("o rodapé diz 'Mostrando 2 de 2 envios'", aba.inner_text("[data-contador-envios]") == "Mostrando 2 de 2 envios")
    singular = aba.evaluate("() => texto_do_contador_de_envios(1, 1)")
    conferir(f"com 1 envio, o rodapé fica no singular (na tela: {singular})", singular == "Mostrando 1 de 1 envio")
    # No celular: duas colunas, então as 6 etapas ocupam 3 linhas, todas visíveis
    aba.set_viewport_size({"width": 390, "height": 900})
    alturas_no_celular = alturas_das_bolinhas(aba)
    conferir("no celular, as etapas ficam em duas colunas (3 linhas)", len(set(alturas_no_celular)) == 3)
    aba.close()
