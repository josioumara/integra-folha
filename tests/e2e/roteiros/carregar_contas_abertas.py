"""Roteiro: "Carregar Contas Abertas" na ficha da empresa, no formato novo "cpf;status;agencia;conta;data_abertura"
(ADR-149).

O arquivo de contas abertas é de UMA empresa, a da ficha aberta: ele é carregado na aba "Contas abertas" da ficha, e
cada linha traz o CPF de um funcionário Cadastrado nela, o status (1 = Conta nova, 2 = Já era correntista), a agência,
a conta e a data de abertura (AAAA-MM-DD). O que ele confere:
- a aba mostra, em destaque, a orientação (vinda do servidor, sem CNPJ) e a legenda do status, e "Último arquivo:
  nenhum";
- o botão "Carregar Contas Abertas" da aba abre a janela para a Aurora: o título cita a empresa, a orientação aparece
  no alto, o formato fixo mostra o cabeçalho exato (5 colunas) e todas as conferências, sem as antigas (CNPJ,
  situação e folha); o modelo para baixar é o formato novo;
- um arquivo com o cabeçalho diferente é recusado, sem nenhum botão de confirmar;
- um arquivo no formato antigo (9 colunas) é recusado, e o motivo diz as colunas que sobram;
- um arquivo com o CPF de uma pessoa de OUTRA empresa é recusado inteiro, com o motivo e a orientação da Aurora;
- um arquivo com divergências (CPF repetido, CPF inválido, CPF que não está Cadastrado, conta repetida, data futura,
  data no jeito antigo e status 3) é recusado, com uma linha por problema e a contagem por tipo;
- o arquivo certo (1 conta nova e 2 correntistas) mostra a prévia com as contas novas e os correntistas e, no
  "Confirmar a baixa de 3 contas", grava as contas; ao fechar a janela, o aviso verde e o histórico da aba (com a
  coluna das contas novas e dos correntistas) mudam sem recarregar a página;
- o mesmo arquivo de novo só avisa ("a mesma conta já estava gravada") e não tem conta nova para confirmar;
- o histórico é por empresa: a ficha da Horizonte continua sem nenhum arquivo.
"""
from pathlib import Path

from tests.e2e.apoio import LOGIN_DO_BANCO, entrar, pasta_do_roteiro

DESCRICAO = "Contas abertas na ficha da empresa: formato cpf;status;agencia;conta;data_abertura, recusas, baixa e histórico"
# O cabeçalho fixo do arquivo de contas abertas (o mesmo do servidor, ADR-149)
CABECALHO_FIXO = "cpf;status;agencia;conta;data_abertura"
# O cabeçalho do formato antigo, que não é mais aceito
CABECALHO_ANTIGO = ("cnpj_empresa;cpf;codigo_banco;agencia;conta;data_abertura;tipo_conta;situacao_correntista;"
                    "folha_ja_identificada")
# A legenda do status que a aba e a janela mostram (a mesma do servidor)
LEGENDA_DO_STATUS = "1 = Conta nova · 2 = Já era correntista"
# A empresa do roteiro (Aurora) e a outra empresa, em que uma pessoa está Cadastrada (Horizonte)
EMPRESA_DO_ARQUIVO = "EMP001"
OUTRA_EMPRESA = "EMP002"


def somente_digitos(texto: str) -> str:
    """Tira pontos, barra e traço: "529.982.247-25" → "52998224725"."""
    digitos = ""
    for caractere in texto:
        if caractere.isdigit():
            digitos = digitos + caractere
    return digitos


def cpfs_fora_da_carteira(cpfs_da_carteira: set, quantidade: int) -> list[str]:
    """CPFs válidos que não são de ninguém da carteira (para "não está Cadastrado" e para a pessoa da Horizonte)."""
    import random

    from services.documentos import gerar_cpf
    # Sorteio com semente fixa: o roteiro dá sempre os mesmos CPFs
    sorteio = random.Random(2026)
    sorteados = []
    while len(sorteados) < quantidade:
        digitos = somente_digitos(gerar_cpf(sorteio))
        if digitos not in cpfs_da_carteira and digitos not in sorteados:
            sorteados.append(digitos)
    return sorteados


def gravar_arquivo(nome: str, linhas: list[str]) -> str:
    """Grava um arquivo .csv na pasta do roteiro e devolve o caminho."""
    caminho = pasta_do_roteiro() / nome
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return str(caminho)


def preparar() -> dict:
    """A Aurora com a carga inicial cadastrada, uma pessoa Cadastrada na Horizonte e os arquivos de contas do roteiro."""
    import csv

    import rag.busca
    from scripts.gerar_dados import main as gerar_dados
    from services import auth, empresas
    from tests.e2e.apoio import criar_usuarios_de_teste
    from tests.test_correcao import RAIZ, busca_falsa
    from tests.test_planejamento import homologar
    # A busca do RAG de mentira: a preparação não depende do índice
    rag.busca.search_rules = busca_falsa
    gerar_dados()
    # O gabarito de cada funcionário (para cadastrar a carga inicial da Aurora)
    verdade = {}
    with open(RAIZ / "data" / "synthetic" / "funcionarios_truth.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            verdade[linha["funcionario_id"]] = linha
    conexao = auth.conectar()
    criar_usuarios_de_teste(conexao)
    homologar(conexao, "aurora_carga_inicial", verdade)
    # Os CPFs cadastrados da Aurora (situação "Cadastrado"), só com os dígitos
    cadastrados = []
    consulta = "SELECT cpf FROM funcionarios_homologados WHERE empresa_id = ? ORDER BY cpf"
    for (cpf,) in conexao.execute(consulta, (EMPRESA_DO_ARQUIVO,)):
        cadastrados.append(somente_digitos(cpf))
    # Uma pessoa de fora da carteira e outra Cadastrada só na Horizonte (direto na tabela, como os testes do serviço)
    de_fora, da_horizonte = cpfs_fora_da_carteira(set(cadastrados), 2)
    conexao.execute("INSERT INTO funcionarios_homologados (empresa_id, cpf, processamento_id, homologado_em) "
                    "VALUES (?, ?, 'roteiro', '2026-09-28')", (OUTRA_EMPRESA, da_horizonte))
    conexao.commit()
    # O nome da Aurora no cadastro (o mesmo que a ficha e o título da janela mostram) e o CNPJ, para o formato antigo
    nome_da_aurora = empresas.obter(conexao, EMPRESA_DO_ARQUIVO)["nome"]
    cnpj_da_aurora = empresas.obter(conexao, EMPRESA_DO_ARQUIVO)["cnpj"]
    conexao.close()
    primeiro, segundo, terceiro, quarto, quinto, sexto, setimo = cadastrados[:7]
    # 1. Cabeçalho fora do layout (nomes e ordem diferentes)
    errado = gravar_arquivo("contas_cabecalho_errado.csv", ["CPF;Agência;Conta;Status", primeiro + ";1234;01234567-8;1"])
    # 2. O formato antigo, com o CNPJ, o código do banco, a situação e a folha: não é mais aceito
    antigo = gravar_arquivo("contas_formato_antigo.csv", [
        CABECALHO_ANTIGO, cnpj_da_aurora + ";" + primeiro + ";033;1234;00000001-1;22/09/2026;1;;"])
    # As três contas certas: uma conta nova (status 1) e dois correntistas (status 2)
    contas_certas = [
        primeiro + ";1;1234;00000001-1;2026-09-22",
        segundo + ";2;1234;00000002-2;2019-03-15",
        quinto + ";2;0456;00000005-5;2021-07-02",
    ]
    # 3. Uma pessoa Cadastrada em outra empresa (a Horizonte): o arquivo é recusado inteiro
    de_outra_empresa = gravar_arquivo("contas_de_outra_empresa.csv", [
        CABECALHO_FIXO, contas_certas[0], da_horizonte + ";1;1234;00000008-8;2026-09-22"])
    # 4. Uma divergência de cada tipo: CPF repetido, CPF inválido, CPF fora da carteira, conta repetida, data futura,
    # data no jeito antigo (DD/MM/AAAA) e o status 3 (não existe)
    com_divergencias = gravar_arquivo("contas_com_divergencias.csv", [
        CABECALHO_FIXO,
        primeiro + ";1;1234;00000001-1;2026-09-22",
        primeiro + ";1;1234;00000001-1;2026-09-22",
        "12345678900;1;1234;00000002-2;2026-09-22",
        de_fora + ";1;1234;00000003-3;2026-09-22",
        segundo + ";1;1234;00000009-9;2026-09-22",
        terceiro + ";1;1234;00000009-9;2026-09-22",
        quarto + ";1;1234;00000004-4;2099-01-01",
        sexto + ";1;1234;00000006-6;22/09/2026",
        setimo + ";3;1234;00000007-7;2026-09-22",
    ])
    # 5. O arquivo certo: as três contas da Aurora
    linhas_certas = [CABECALHO_FIXO] + contas_certas
    certo = gravar_arquivo("contas_da_semana.csv", linhas_certas)
    # 6. O mesmo arquivo de novo (outro nome): as três contas já estão gravadas, iguais
    repetido = gravar_arquivo("contas_da_semana_de_novo.csv", linhas_certas)
    return {"errado": errado, "antigo": antigo, "de_outra_empresa": de_outra_empresa,
            "com_divergencias": com_divergencias, "certo": certo, "repetido": repetido,
            "nome_da_aurora": nome_da_aurora}


def carregar_na_janela(aba, caminho: str, etapa_esperada: str) -> None:
    """Escolhe o arquivo na janela aberta e espera a etapa do resultado ("recusado" ou "pronto")."""
    aba.set_input_files("[data-campo-arquivo-contas-janela]", caminho)
    aba.locator(f"[data-etapa-janela-contas='{etapa_esperada}']").wait_for(state="visible", timeout=20000)


def tipos_na_tabela(aba) -> set:
    """Os tipos de divergência que aparecem na tabela da recusa (em minúsculas)."""
    tipos = set()
    for linha in aba.locator("[data-divergencias-contas] tr").all():
        tipos.add((linha.get_attribute("data-tipo") or "").lower())
    return tipos


def abrir_a_janela(aba) -> None:
    """Clica em "Carregar Contas Abertas" na aba da ficha e espera a janela com as conferências do servidor."""
    aba.click("[data-conteudo-aba='contas'] [data-abrir-carregar-contas]")
    aba.locator("[data-janela-contas-abertas][open]").wait_for(timeout=10000)
    aba.locator("[data-conferencia]").first.wait_for(timeout=10000)


def voltar_a_escolher(aba) -> None:
    """Na recusa, clica em "Carregar o arquivo corrigido" (volta à etapa de escolher o arquivo)."""
    aba.click("[data-etapa-janela-contas='recusado'] [data-voltar-a-escolher]")


def percorrer(navegador, endereco: str, dados: dict, conferir, erros_da_pagina: list) -> None:
    """Carrega os arquivos pela janela da aba "Contas abertas" da ficha da Aurora."""
    aba = entrar(navegador, endereco, LOGIN_DO_BANCO, erros_da_pagina)
    aba.goto(endereco + "/banco_empresas.html?empresa=" + EMPRESA_DO_ARQUIVO + "&aba=contas")
    # 1. A aba mostra a orientação e a legenda do status, vindas do servidor
    aba.locator("[data-legenda-status][data-dado-pronto]").wait_for(state="attached", timeout=20000)
    conferir("a aba Contas abertas abre direto pelo endereço (?aba=contas)",
             aba.locator("[data-conteudo-aba='contas']").is_visible())
    orientacao = aba.inner_text("[data-orientacao-contas]")
    conferir("a orientação diz que o arquivo é da Aurora, com os CPFs Cadastrados nela (" + orientacao + ")",
             dados["nome_da_aurora"] in orientacao and "Cadastrado" in orientacao)
    conferir("a orientação não pede mais o CNPJ", "CNPJ" not in orientacao)
    conferir("a orientação chama a conta de conta salário", "a conta salário e a data de abertura" in orientacao)
    conferir("a aba não mostra mais 'CNPJs aceitos'", "CNPJs aceitos" not in aba.inner_text("[data-conteudo-aba='contas']"))
    conferir("a aba mostra a legenda do status", LEGENDA_DO_STATUS in aba.inner_text("[data-legenda-status]"))
    aba.locator("[data-ultimo-arquivo-contas][data-dado-pronto]").wait_for(state="attached", timeout=10000)
    conferir("nenhum arquivo ainda", "nenhum" in aba.inner_text("[data-ultimo-arquivo-contas]"))
    # 2. O botão abre a janela para a Aurora, com a orientação, o formato e as conferências (vindos do servidor)
    abrir_a_janela(aba)
    conferir("o título da janela cita a empresa", dados["nome_da_aurora"] in aba.inner_text("[data-titulo-janela-contas]"))
    conferir("a janela mostra a legenda do status na orientação",
             LEGENDA_DO_STATUS in aba.inner_text("[data-orientacao-janela-contas]"))
    conferir("o formato explica o status", LEGENDA_DO_STATUS in aba.inner_text("[data-regra-status]"))
    conferir("o formato diz que a data vem como AAAA-MM-DD", "AAAA-MM-DD" in aba.inner_text("[data-formato-contas]"))
    conferir("a janela mostra o cabeçalho exato do arquivo", CABECALHO_FIXO in aba.inner_text("[data-formato-contas]"))
    conferir("a tabela do formato tem as 5 colunas",
             aba.locator("[data-formato-contas] .tabela-formato-contas tbody tr").count() == 5)
    # A coluna "conta" do arquivo aparece como "Conta salário" (o cabeçalho do arquivo continua "conta")
    conferir("a tabela do formato chama a coluna conta de 'Conta salário'",
             "Conta salário" in aba.inner_text("[data-formato-contas] .tabela-formato-contas"))
    conferir("a janela lista as conferências (16 que travam e 2 avisos)", aba.locator("[data-conferencia]").count() == 18)
    conferir("as conferências do status e da data estão na lista",
             aba.locator("[data-conferencia='status_invalido']").count() == 1
             and aba.locator("[data-conferencia='data_invalida']").count() == 1)
    conferir("as conferências antigas (CNPJ, situação e folha) saíram",
             aba.locator("[data-conferencia='cnpj_de_outra_empresa']").count() == 0
             and aba.locator("[data-conferencia='situacao_do_correntista_faltando']").count() == 0
             and aba.locator("[data-conferencia='folha_do_correntista_faltando']").count() == 0)
    # O modelo para baixar: o cabeçalho novo e as duas linhas de exemplo (uma conta nova e um correntista)
    with aba.expect_download() as baixado:
        aba.click("[data-baixar-modelo-contas]")
    # "utf-8-sig": o arquivo baixado começa com a marca BOM, para o Excel abrir os acentos certo
    modelo = Path(baixado.value.path()).read_text(encoding="utf-8-sig").splitlines()
    conferir("o modelo baixado é o formato novo (" + " | ".join(modelo) + ")",
             modelo == [CABECALHO_FIXO, "52998224725;1;0123;45678-9;2026-09-29", "11144477735;2;0456;11223-4;2019-03-10"])
    aba.screenshot(path="storage/painel/carregar_contas_abertas.png")
    # 3. Cabeçalho fora do layout: recusado, sem botão de confirmar
    carregar_na_janela(aba, dados["errado"], "recusado")
    conferir("cabeçalho diferente: arquivo recusado", "cabecalho" in tipos_na_tabela(aba))
    conferir("recusado não tem botão de confirmar", aba.locator("[data-confirmar-baixa-janela]").count() == 0)
    # 4. O formato antigo: recusado, e o motivo diz as colunas que sobram
    voltar_a_escolher(aba)
    carregar_na_janela(aba, dados["antigo"], "recusado")
    texto_da_recusa = aba.inner_text("[data-divergencias-contas]")
    conferir("formato antigo: recusado pelo cabeçalho (" + str(tipos_na_tabela(aba)) + ")",
             tipos_na_tabela(aba) == {"cabecalho"})
    conferir("formato antigo: o motivo diz que sobram as colunas do CNPJ, da situação e da folha",
             "Sobram as colunas cnpj_empresa, codigo_banco, tipo_conta, situacao_correntista, folha_ja_identificada"
             in texto_da_recusa)
    # 5. Uma pessoa Cadastrada em outra empresa: recusado inteiro, com o motivo e a orientação à vista
    voltar_a_escolher(aba)
    carregar_na_janela(aba, dados["de_outra_empresa"], "recusado")
    conferir("pessoa de outra empresa: arquivo recusado (" + str(tipos_na_tabela(aba)) + ")",
             tipos_na_tabela(aba) == {"cpf_nao_cadastrado"})
    conferir("pessoa de outra empresa: o motivo diz a empresa (Horizonte)",
             "Cadastrado em outra empresa (Horizonte" in aba.inner_text("[data-divergencias-contas]"))
    conferir("pessoa de outra empresa: nenhuma conta gravada",
             "Nenhuma conta foi gravada" in aba.inner_text("[data-aviso-recusa]"))
    conferir("pessoa de outra empresa: a orientação da Aurora aparece na recusa",
             aba.locator("[data-orientacao-na-recusa]").is_visible()
             and dados["nome_da_aurora"] in aba.inner_text("[data-orientacao-na-recusa]"))
    aba.screenshot(path="storage/painel/carregar_contas_outra_empresa.png")
    # 6. As divergências de linha e de carteira, cada uma na tabela
    voltar_a_escolher(aba)
    carregar_na_janela(aba, dados["com_divergencias"], "recusado")
    tipos = tipos_na_tabela(aba)
    for tipo in ("cpf_repetido_no_arquivo", "cpf_invalido", "cpf_nao_cadastrado", "conta_repetida_no_arquivo",
                 "data_invalida", "status_invalido"):
        conferir(f"divergência '{tipo}' aparece na tabela", tipo in tipos)
    conferir("a data no jeito antigo (DD/MM/AAAA) é recusada",
             "22/09/2026" in aba.inner_text("[data-divergencias-contas]"))
    conferir("o aviso diz que nenhuma conta foi gravada",
             "Nenhuma conta foi gravada" in aba.inner_text("[data-aviso-recusa]"))
    conferir("a contagem por tipo aparece", aba.locator(".etiquetas-divergencias-contas li").count() >= 6)
    aba.screenshot(path="storage/painel/carregar_contas_recusado.png")
    # 7. O arquivo certo: prévia e baixa, com a página marcada para provar que ela não recarrega
    aba.evaluate("() => { window.marca_do_roteiro = 'sem recarregar'; }")
    voltar_a_escolher(aba)
    carregar_na_janela(aba, dados["certo"], "pronto")
    botao = aba.locator("[data-confirmar-baixa-janela]")
    conferir("o botão diz 'Confirmar a baixa de 3 contas'", botao.inner_text() == "Confirmar a baixa de 3 contas")
    conferir("a prévia conta 1 conta nova", aba.inner_text("[data-previa-novas-contas]").startswith("1"))
    texto_dos_correntistas = aba.inner_text("[data-previa-correntistas]")
    conferir("a prévia conta 2 correntistas, sem ativos, inativos nem folha (" + texto_dos_correntistas + ")",
             texto_dos_correntistas.startswith("2") and "ativo" not in texto_dos_correntistas
             and "folha" not in texto_dos_correntistas)
    conferir("a prévia diz que a empresa vê a agência, o número e a data",
             "agência, número e data de abertura" in aba.inner_text("[data-etapa-janela-contas='pronto']"))
    aba.screenshot(path="storage/painel/carregar_contas_previa_com_tipos.png")
    botao.click()
    aba.locator("[data-aviso-baixa-feita]").wait_for(timeout=10000)
    conferir("a baixa foi feita (3 funcionários)", "3 funcionários passaram" in aba.inner_text("[data-aviso-baixa-feita]"))
    # 8. Fechada a janela, o aviso verde e o histórico da aba já mudaram, sem recarregar a página
    aba.keyboard.press("Escape")
    aba.locator("[data-aviso-contas]:not([hidden])").wait_for(timeout=10000)
    conferir("o aviso verde da aba mostra a baixa", "3 funcionários passaram" in aba.inner_text("[data-aviso-contas]"))
    aba.wait_for_function("() => document.querySelector('[data-historico-contas]').innerText.includes('+3')",
                          timeout=10000)
    conferir("o histórico da aba mostra o arquivo com +3", "+3" in aba.inner_text("[data-historico-contas]"))
    conferir("o histórico da aba divide contas novas e correntistas",
             "1 conta nova · 2 correntistas" in aba.inner_text("[data-historico-contas]"))
    conferir("o último arquivo deixou de ser 'nenhum'", "nenhum" not in aba.inner_text("[data-ultimo-arquivo-contas]"))
    conferir("a página não recarregou",
             aba.evaluate("() => window.marca_do_roteiro") == "sem recarregar")
    aba.screenshot(path="storage/painel/carregar_contas_historico.png")
    # 9. O mesmo arquivo de novo: só aviso, nenhuma conta nova para confirmar
    abrir_a_janela(aba)
    carregar_na_janela(aba, dados["repetido"], "pronto")
    conferir("mesma conta de novo: sem conta nova para confirmar",
             aba.locator("[data-confirmar-baixa-janela]").is_disabled())
    conferir("as 3 linhas aparecem como ignoradas", "3 linhas ignoradas" in aba.inner_text("[data-etapa-janela-contas='pronto']"))
    # Fechar a janela descarta a prévia
    aba.keyboard.press("Escape")
    conferir("Esc fecha a janela", aba.locator("[data-janela-contas-abertas][open]").count() == 0)
    # 10. O histórico é por empresa: a Horizonte continua sem arquivo (a Carteira está congelada na empresa do arquivo:
    #     o "Trocar empresa" traz a lista de volta)
    aba.click("[data-trocar-empresa]")
    aba.click(f"[data-abrir-empresa='{OUTRA_EMPRESA}']")
    aba.wait_for_function("() => document.querySelector('[data-historico-contas]').innerText.includes('Nenhum arquivo')",
                          timeout=10000)
    conferir("a Horizonte não tem arquivo no histórico", "Nenhum arquivo" in aba.inner_text("[data-historico-contas]"))
    conferir("o aviso verde da Aurora some ao trocar de empresa", aba.locator("[data-aviso-contas]").is_hidden())
    aba.close()
