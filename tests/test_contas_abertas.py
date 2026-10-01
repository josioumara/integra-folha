"""Contas abertas: o arquivo do banco dá baixa em cada funcionário cadastrado (ADR-69, passo 16; layout fixo e
travas, ADR-119; um arquivo por empresa, ADR-122; o formato novo, ADR-149).

O que estes testes provam:
- o arquivo segue um layout FIXO (.csv com ";" e o cabeçalho exato "cpf;status;agencia;conta;data_abertura", com a
  data em AAAA-MM-DD; ADR-149); a rota do layout de cada empresa entrega à tela as mesmas constantes que o
  código confere (fonte única), a empresa e a orientação, só para o perfil BANCO;
- só o formato novo é aceito: o antigo (com o CNPJ, o código do banco, a situação e a folha) é recusado, e o motivo diz
  o que falta e o que sobra;
- o arquivo é subido POR EMPRESA (a da ficha): o CPF precisa estar Cadastrado NESTA empresa (se está em outra, o motivo
  diz qual); o histórico é de cada empresa; empresa que não existe dá 404;
- cada tipo de divergência trava o arquivo inteiro: a prévia volta com pode_importar = false, sem arquivo_id, e o
  registro fica RECUSADO sem nenhum CPF; confirmar um arquivo recusado dá 400;
- o CPF que não está Cadastrado diz por quê: em análise no banco, ainda com a empresa ou nunca enviado;
- o arquivo limpo gera a prévia PENDENTE e só a confirmação dá baixa; quem já tinha a MESMA conta (agência e número) é
  só aviso; outra conta para o mesmo CPF, ou a conta de outro CPF, trava; a conta antiga, com o código do banco, é a
  mesma conta;
- o CPF cadastrado em duas empresas ganha a baixa pelo arquivo de cada uma;
- a empresa vê o total da empresa e, na lista, na ficha e no download, a conta de cada funcionário dela (agência,
  número e data, ADR-102); uma empresa nunca vê a conta de funcionário de outra; o código do banco vem vazio;
- cada linha diz o status (1 = Conta nova, 2 = Já era correntista): vazio ou diferente de 1 e 2, e a mesma conta já
  gravada com o outro status recusam o arquivo inteiro; a conta antiga, gravada sem o status, ganha o do arquivo; a
  prévia e o histórico contam contas novas e correntistas; retorno_por_cpf entrega o tipo ao planejamento;
- a empresa nunca vê o tipo gravado (nem os nomes das colunas do banco): nenhuma rota /api/empresa/... o devolve.
"""
import json
import random
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import EstadoProcessamento, Perfil
from services import auth, banco, contas_abertas, correcoes, processamentos
from services.auth import Usuario
from services.documentos import gerar_cpf
from tests.test_correcao import preparar_ate_a_validacao
from tests.test_planejamento import gerar_envios, homologar, usar_busca_falsa, verdade  # noqa: F401 (fixtures)

# Senha dos usuários de teste
SENHA_DE_TESTE = "senha-de-teste-123"
# Usuários de mentira para chamar o serviço direto
ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
RH_DA_AURORA = Usuario(login="rh.aurora", perfil=Perfil.EMPRESA, empresa_id="EMP001")
# O cabeçalho exato do layout (ADR-149: o CPF, o status, a agência, a conta e a data de abertura)
CABECALHO = "cpf;status;agencia;conta;data_abertura"
# O cabeçalho do layout antigo (ADR-122), que não é mais aceito
CABECALHO_ANTIGO = ("cnpj_empresa;cpf;codigo_banco;agencia;conta;data_abertura;tipo_conta;situacao_correntista;"
                    "folha_ja_identificada")
# A data de abertura usada nas linhas de teste, como vem no arquivo (AAAA-MM-DD) e como fica gravada (DD/MM/AAAA)
DATA_DE_ABERTURA = "2026-09-24"
DATA_GRAVADA = "24/09/2026"


@pytest.fixture
def conexao(tmp_path, verdade):
    """Um banco com a carga inicial da Aurora cadastrada."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    homologar(conexao_do_teste, "aurora_carga_inicial", verdade)
    yield conexao_do_teste
    conexao_do_teste.close()


def cpfs_da_aurora(conexao, quantidade: int) -> list[str]:
    """Os CPFs de alguns funcionários cadastrados da Aurora (como estão na tabela)."""
    consulta = conexao.execute("SELECT cpf FROM funcionarios_homologados WHERE empresa_id = 'EMP001' ORDER BY cpf")
    cpfs = []
    for (cpf,) in consulta:
        cpfs.append(cpf)
    return cpfs[:quantidade]


def conta_de_teste(cpf: str) -> str:
    """O número de conta inventado de cada pessoa: os 5 últimos dígitos do CPF e "-0" (ex.: "24725-0")."""
    return cpf[-5:] + "-0"


def linha_de_conta(cpf: str, status: str = "1", agencia: str = "0001", conta: str | None = None,
                   data_abertura: str = DATA_DE_ABERTURA) -> str:
    """Uma linha do arquivo no layout fixo; sem conta informada, usa a conta de teste; sem status, uma Conta nova."""
    if conta is None:
        conta = conta_de_teste(cpf)
    return ";".join([cpf, status, agencia, conta, data_abertura])


def arquivo_de_linhas(linhas: list[str], cabecalho: str = CABECALHO) -> bytes:
    """O arquivo em bytes: o cabeçalho e as linhas, em UTF-8."""
    return "\n".join([cabecalho] + linhas).encode("utf-8")


def arquivo_de_contas(cpfs: list[str]) -> bytes:
    """Um arquivo limpo, como o que os sistemas do banco geram: uma linha por CPF, com a conta de teste."""
    linhas = []
    for cpf in cpfs:
        linhas.append(linha_de_conta(cpf))
    return arquivo_de_linhas(linhas)


def somente_digitos(texto: str) -> str:
    """Só os dígitos: "529.982.247-25" → "52998224725"."""
    digitos = ""
    for caractere in texto:
        if caractere.isdigit():
            digitos = digitos + caractere
    return digitos


def tipos_da_previa(previa: dict) -> set[str]:
    """Os tipos de divergência que apareceram na prévia."""
    tipos = set()
    for divergencia in previa["divergencias"]:
        tipos.add(divergencia["tipo"])
    return tipos


def conferir_recusa_sem_cpf(conexao, previa: dict, cpfs: list[str]) -> None:
    """Confere a trava: nada a confirmar, nada gravado e o registro RECUSADO sem nenhum CPF."""
    assert previa["pode_importar"] is False and previa["arquivo_id"] is None
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["com_conta"] == 0
    for (resultado,) in conexao.execute("SELECT resultado FROM arquivos_de_contas WHERE situacao = 'RECUSADO'"):
        for cpf in cpfs:
            assert cpf not in resultado


# ---------------- O layout fixo ----------------

def test_layout_do_arquivo_sai_das_constantes_do_servico(conexao):
    layout = contas_abertas.layout_do_arquivo(conexao, "EMP001")
    assert (layout["extensao"], layout["separador"], layout["cabecalho"]) == (".csv", ";", CABECALHO)
    nomes = []
    for coluna in layout["colunas"]:
        nomes.append(coluna["nome"])
        assert coluna["titulo"] and coluna["formato"] and coluna["exemplo"]
    assert ";".join(nomes) == CABECALHO
    # O exemplo (o modelo para baixar) tem uma conta nova e um correntista, com a data em AAAA-MM-DD
    assert layout["exemplo_de_linhas"] == ["52998224725;1;0123;45678-9;2026-09-29",
                                           "11144477735;2;0456;11223-4;2019-03-10"]
    # A empresa é a da ficha (o arquivo não traz mais o CNPJ), e a orientação diz o que vale em cada linha
    assert layout["empresa"] == {"empresa_id": "EMP001", "nome": "Aurora Alimentos Ltda."}
    orientacao = layout["orientacao_da_empresa"]
    assert "Aurora Alimentos Ltda." in orientacao and "Cadastrado" in orientacao and "recusa o arquivo" in orientacao
    assert "1 = Conta nova" in orientacao and "2 = Já era correntista" in orientacao
    assert "CNPJ" not in orientacao and "ATIVO" not in orientacao and "folha" not in orientacao
    assert layout["legenda_do_status"] == "1 = Conta nova · 2 = Já era correntista"
    codigos = []
    for valor_do_status in layout["valores_do_status"]:
        codigos.append(valor_do_status["codigo"])
    assert codigos == ["1", "2"]
    # Todas as conferências do contrato, e só os avisos não travam
    tipos_que_travam = set()
    tipos_que_nao_travam = set()
    for validacao in layout["validacoes"]:
        assert validacao["grupo"] in ("arquivo", "linha", "carteira") and validacao["titulo"] and validacao["descricao"]
        if validacao["trava"]:
            tipos_que_travam.add(validacao["tipo"])
        else:
            tipos_que_nao_travam.add(validacao["tipo"])
    assert tipos_que_travam == {"formato_do_arquivo", "arquivo_vazio", "cabecalho", "quantidade_de_colunas",
                                "campo_vazio", "cpf_invalido", "status_invalido", "agencia_invalida", "conta_invalida",
                                "data_invalida", "cpf_repetido_no_arquivo", "conta_repetida_no_arquivo",
                                "cpf_nao_cadastrado", "conta_diferente_da_gravada", "conta_de_outro_cpf",
                                "status_diferente_do_gravado"}
    assert tipos_que_nao_travam == {"ja_tinha_conta", "status_completado"}
    # Cada conferência diz como corrigir (a tela mostra)
    for validacao in layout["validacoes"]:
        assert validacao["como_corrigir"]


def test_a_conta_que_o_banco_informa_se_chama_conta_salario(conexao):
    """A conta que o banco informa à empresa é a conta salário: o título da coluna na tela, a orientação da ficha e os
    avisos que falam da conta de uma pessoa dizem "conta salário". O nome técnico (conta) e o cabeçalho não mudam."""
    layout = contas_abertas.layout_do_arquivo(conexao, "EMP001")
    # O título de cada coluna na tela, pelo nome técnico dela
    titulo_por_nome = {}
    for coluna in layout["colunas"]:
        titulo_por_nome[coluna["nome"]] = coluna["titulo"]
    # A coluna "conta" aparece como "Conta salário"; o cabeçalho do arquivo continua o mesmo
    assert titulo_por_nome["conta"] == "Conta salário" and layout["cabecalho"] == CABECALHO
    # A orientação da ficha diz o que cada linha traz, com a conta salário
    assert "a agência, a conta salário e a data de abertura" in layout["orientacao_da_empresa"]
    # Os avisos sobre a conta de uma pessoa dizem "conta salário", no título e na descrição
    for tipo in ("conta_invalida", "conta_repetida_no_arquivo", "conta_diferente_da_gravada", "conta_de_outro_cpf",
                 "status_diferente_do_gravado", "status_completado", "ja_tinha_conta"):
        validacao = contas_abertas.VALIDACAO_POR_TIPO[tipo]
        assert "conta salário" in validacao["titulo"].lower() and "conta salário" in validacao["descricao"]


def test_as_linhas_de_exemplo_do_layout_passam_na_conferencia(conexao):
    """O exemplo que a tela mostra (e o modelo para baixar) é um arquivo certo: com os CPFs cadastrados, passa."""
    dois = cpfs_da_aurora(conexao, 2)
    linhas_de_exemplo = contas_abertas.layout_do_arquivo(conexao, "EMP001")["exemplo_de_linhas"]
    # Troca os CPFs de exemplo pelos de duas pessoas Cadastradas na Aurora (o resto da linha fica igual)
    linhas = [linhas_de_exemplo[0].replace("52998224725", dois[0]), linhas_de_exemplo[1].replace("11144477735", dois[1])]
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(linhas), "modelo.csv")
    assert previa["pode_importar"] is True and previa["divergencias"] == []
    assert previa["tipos_das_novas"] == {"nova_conta": 1, "correntista": 1}


def test_o_layout_antigo_e_recusado_e_o_motivo_diz_o_que_falta_e_o_que_sobra(conexao):
    """Só o formato novo é aceito (ADR-149): o arquivo antigo, com 9 colunas, é recusado."""
    um = cpfs_da_aurora(conexao, 1)[0]
    linha_antiga = ";".join(["10433218000193", um, "033", "0001", conta_de_teste(um), "24/09/2026", "2", "ATIVO", "N"])
    conteudo = arquivo_de_linhas([linha_antiga], cabecalho=CABECALHO_ANTIGO)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "antigo.csv")
    assert tipos_da_previa(previa) == {"cabecalho"} and previa["pode_importar"] is False
    motivo = previa["divergencias"][0]["motivo"]
    assert "Falta a coluna status" in motivo
    assert ("Sobram as colunas cnpj_empresa, codigo_banco, tipo_conta, situacao_correntista, folha_ja_identificada"
            in motivo)
    # Com o cabeçalho novo, mas a linha no formato antigo (9 colunas): a linha não tem as 5 colunas
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas([linha_antiga]),
                                             "misturado.csv")
    assert tipos_da_previa(previa) == {"quantidade_de_colunas"}
    conferir_recusa_sem_cpf(conexao, previa, [um])


# ---------------- Cada divergência trava o arquivo inteiro ----------------

def _amanha() -> str:
    """A data de amanhã em AAAA-MM-DD (uma abertura futura)."""
    return (date.today() + timedelta(days=1)).isoformat()


def _caso_da_divergencia(tipo: str, dois: list[str]) -> tuple:
    """O arquivo (conteúdo e nome) que provoca cada tipo de divergência, com dois CPFs cadastrados da Aurora.

    A primeira linha é sempre limpa: prova que uma linha errada recusa o arquivo inteiro.
    """
    limpa = linha_de_conta(dois[0])
    outro = dois[1]
    casos = {
        "formato_do_arquivo": (arquivo_de_contas(dois), "contas.xlsx"),
        "arquivo_vazio": (CABECALHO.encode("utf-8") + b"\n", "contas.csv"),
        "cabecalho": (arquivo_de_linhas([limpa], cabecalho="CPF;Status;Agencia;Conta;Data"), "contas.csv"),
        "quantidade_de_colunas": (arquivo_de_linhas([limpa, outro + ";1;0001;12345-0"]), "contas.csv"),
        "campo_vazio": (arquivo_de_linhas([limpa, linha_de_conta(outro, agencia="")]), "contas.csv"),
        "cpf_invalido": (arquivo_de_linhas([limpa, linha_de_conta("12345678900")]), "contas.csv"),
        # O status 3 não existe
        "status_invalido": (arquivo_de_linhas([limpa, linha_de_conta(outro, status="3")]), "contas.csv"),
        "agencia_invalida": (arquivo_de_linhas([limpa, linha_de_conta(outro, agencia="001")]), "contas.csv"),
        "conta_invalida": (arquivo_de_linhas([limpa, linha_de_conta(outro, conta="12345")]), "contas.csv"),
        "data_invalida": (arquivo_de_linhas([limpa, linha_de_conta(outro, data_abertura=_amanha())]), "contas.csv"),
        "cpf_repetido_no_arquivo": (arquivo_de_linhas([limpa, linha_de_conta(dois[0], conta="99999-9")]),
                                    "contas.csv"),
        "conta_repetida_no_arquivo": (arquivo_de_linhas([limpa, linha_de_conta(outro, conta=conta_de_teste(dois[0]))]),
                                      "contas.csv"),
        "cpf_nao_cadastrado": (arquivo_de_linhas([limpa, linha_de_conta(gerar_cpf(random.Random(7)))]), "contas.csv"),
    }
    return casos[tipo]


@pytest.mark.parametrize("tipo", ["formato_do_arquivo", "arquivo_vazio", "cabecalho", "quantidade_de_colunas",
                                  "campo_vazio", "cpf_invalido", "status_invalido", "agencia_invalida",
                                  "conta_invalida", "data_invalida", "cpf_repetido_no_arquivo",
                                  "conta_repetida_no_arquivo", "cpf_nao_cadastrado"])
def test_cada_divergencia_trava_o_arquivo_inteiro(conexao, tipo):
    dois = cpfs_da_aurora(conexao, 2)
    conteudo, nome = _caso_da_divergencia(tipo, dois)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, nome)
    assert tipo in tipos_da_previa(previa)
    # A contagem por tipo traz o título da conferência
    titulos = {}
    for contagem in previa["divergencias_por_tipo"]:
        titulos[contagem["tipo"]] = contagem["titulo"]
    assert titulos[tipo] == contas_abertas.VALIDACAO_POR_TIPO[tipo]["titulo"]
    # Cada divergência diz o que fazer
    for divergencia in previa["divergencias"]:
        assert divergencia["motivo"] and divergencia["como_corrigir"]
    conferir_recusa_sem_cpf(conexao, previa, dois)


def test_erros_do_arquivo_inteiro_vem_numa_divergencia_so(conexao):
    """Não é texto, está vazio ou tem o cabeçalho errado: UMA divergência, na linha 0 (ou 1, no cabeçalho)."""
    dois = cpfs_da_aurora(conexao, 2)
    excel_renomeado = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", b"PK\x03\x04resto", "contas.csv")
    assert [(item["tipo"], item["linha"]) for item in excel_renomeado["divergencias"]] == [("formato_do_arquivo", 0)]
    vazio = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", b"", "contas.csv")
    assert [(item["tipo"], item["linha"]) for item in vazio["divergencias"]] == [("arquivo_vazio", 0)]
    # As mesmas colunas, fora de ordem: o motivo não diz que falta nem que sobra nenhuma
    cabecalho_fora_de_ordem = "cpf;status;conta;agencia;data_abertura"
    cabecalho_errado = arquivo_de_linhas([linha_de_conta(dois[0])], cabecalho=cabecalho_fora_de_ordem)
    errado = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", cabecalho_errado, "contas.csv")
    assert [(item["tipo"], item["linha"]) for item in errado["divergencias"]] == [("cabecalho", 1)]
    assert "Falta" not in errado["divergencias"][0]["motivo"] and "Sobra" not in errado["divergencias"][0]["motivo"]
    # A linha do cabeçalho não conta; a de dados, sim
    assert errado["linhas"] == 1


def test_linha_conta_o_cabecalho_como_1_e_repeticao_marca_todas(conexao):
    dois = cpfs_da_aurora(conexao, 2)
    conteudo = arquivo_de_linhas([linha_de_conta(dois[0]), linha_de_conta(dois[1]), linha_de_conta(dois[0])])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "contas.csv")
    repetidos = []
    for divergencia in previa["divergencias"]:
        if divergencia["tipo"] == "cpf_repetido_no_arquivo":
            repetidos.append(divergencia["linha"])
    # O CPF está nas linhas 2 e 4 do arquivo (a 1 é o cabeçalho)
    assert repetidos == [2, 4]
    # Nada a importar, e as contas que dariam baixa não incluem as linhas com divergência
    assert previa["pode_importar"] is False and previa["novas"] == 1


def test_data_que_nao_existe_ou_fora_do_molde_trava(conexao):
    """A data vem como AAAA-MM-DD: o jeito antigo (DD/MM/AAAA), sem os zeros ou que não existe é recusado."""
    dois = cpfs_da_aurora(conexao, 2)
    for data_errada in ("2026-02-31", "24/09/2026", "2026-9-1", "2026/09/24"):
        conteudo = arquivo_de_linhas([linha_de_conta(dois[0], data_abertura=data_errada)])
        previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "contas.csv")
        assert tipos_da_previa(previa) == {"data_invalida"}


def test_status_vazio_tem_a_conferencia_propria_e_diz_os_dois_codigos(conexao):
    um = cpfs_da_aurora(conexao, 1)[0]
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001",
                                             arquivo_de_linhas([linha_de_conta(um, status="")]), "c.csv")
    # Não é "Coluna vazia": é a conferência do status, que diz o que vale
    assert tipos_da_previa(previa) == {"status_invalido"} and previa["pode_importar"] is False
    assert "1 (Conta nova) ou 2 (Já era correntista)" in previa["divergencias"][0]["motivo"]


def test_colunas_vazias_viram_uma_divergencia_so_com_os_nomes(conexao):
    um = cpfs_da_aurora(conexao, 1)[0]
    conteudo = arquivo_de_linhas([";".join([um, "1", "", "", ""])])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "c.csv")
    assert tipos_da_previa(previa) == {"campo_vazio"} and len(previa["divergencias"]) == 1
    assert previa["divergencias"][0]["motivo"] == "vazia: Agência, Conta salário, Data de abertura"


def test_arquivo_com_bom_fim_de_linha_do_windows_e_espacos_passa(conexao):
    """UTF-8 com a marca BOM, linhas terminadas em \\r\\n, espaços em volta e linha em branco no fim: tudo aceito."""
    um = cpfs_da_aurora(conexao, 1)[0]
    linha_com_espacos = " " + um + " ; 2 ;0001; " + conta_de_teste(um) + " ;" + DATA_DE_ABERTURA + " "
    texto = CABECALHO + "\r\n" + linha_com_espacos + "\r\n\r\n"
    # A marca BOM do UTF-8: 3 bytes invisíveis no começo do arquivo
    conteudo = b"\xef\xbb\xbf" + texto.encode("utf-8")
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "CONTAS.CSV")
    assert previa["pode_importar"] is True and previa["novas"] == 1 and previa["linhas"] == 1
    assert previa["tipos_das_novas"] == {"nova_conta": 0, "correntista": 1}


def test_a_lista_de_divergencias_tem_limite_mas_a_contagem_nao(conexao):
    linhas = []
    for _numero in range(600):
        linhas.append(linha_de_conta("12345678900"))
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(linhas), "contas.csv")
    assert len(previa["divergencias"]) == 500
    quantidade_por_tipo = {}
    for contagem in previa["divergencias_por_tipo"]:
        quantidade_por_tipo[contagem["tipo"]] = contagem["quantidade"]
    assert quantidade_por_tipo["cpf_invalido"] == 600


# ---------------- CPF que não está Cadastrado: o motivo ----------------

def test_cpf_nao_cadastrado_diz_onde_a_pessoa_esta(conexao):
    """Nunca enviado, ainda com a empresa (Aguardando envio) e, depois de mandado ao banco, em análise."""
    inclusao = preparar_ate_a_validacao(conexao, "aurora_inclusao")
    registros = correcoes.dados_atuais(conexao, inclusao).registros
    cpf_da_inclusao = somente_digitos(str(registros[0]["cpf"]))
    nunca_enviado = gerar_cpf(random.Random(7))
    conteudo = arquivo_de_linhas([linha_de_conta(cpf_da_inclusao), linha_de_conta(nunca_enviado)])

    def motivos_por_cpf() -> dict:
        """Confere o arquivo e devolve {cpf só com dígitos: motivo} das linhas de CPF não cadastrado."""
        previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "contas.csv")
        motivos = {}
        for divergencia in previa["divergencias"]:
            if divergencia["tipo"] == "cpf_nao_cadastrado":
                motivos[somente_digitos(divergencia["cpf"])] = divergencia["motivo"]
        return motivos

    antes = motivos_por_cpf()
    assert antes[nunca_enviado] == contas_abertas.MOTIVO_NUNCA_ENVIADO
    assert antes[cpf_da_inclusao].startswith("ainda com a empresa, na situação Aguardando envio")
    # Mandado ao banco: a mesma pessoa passa a "em análise"
    processamentos.atualizar_status(conexao, inclusao, EstadoProcessamento.AGUARDANDO_BANCO)
    depois = motivos_por_cpf()
    assert depois[cpf_da_inclusao].startswith("ainda em análise no banco (")


# ---------------- Arquivo limpo: prévia, confirmação e contas já gravadas ----------------

def test_arquivo_limpo_gera_previa_e_so_a_confirmacao_da_baixa(conexao):
    tres = cpfs_da_aurora(conexao, 3)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(tres), "semana1.csv")
    assert previa["pode_importar"] is True and previa["arquivo_id"] is not None
    assert (previa["linhas"], previa["novas"], previa["divergencias"], previa["avisos"]) == (3, 3, [], [])
    # O que muda por empresa (Aurora e a linha da carteira)
    assert previa["por_empresa"][0]["novas"] == 3 and previa["por_empresa"][-1]["empresa"] == "Carteira"
    # Nada gravado nas contas ainda
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["com_conta"] == 0
    resultado = contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    assert resultado["novas"] == 3
    numeros = contas_abertas.numeros_de_contas(conexao, "EMP001")
    assert numeros["com_conta"] == 3 and numeros["arquivo_recebido"] is True
    # A conta fica gravada com a data como DD/MM/AAAA (o jeito das contas antigas) e sem o código do banco
    gravada = conexao.execute("SELECT data_abertura, agencia, conta, codigo_banco, tipo_conta, situacao_correntista, "
                              "folha_ja_identificada FROM contas_abertas WHERE cpf = ?", (tres[0],)).fetchone()
    assert tuple(gravada) == (DATA_GRAVADA, "0001", conta_de_teste(tres[0]), "", "NOVA_CONTA", None, None)
    # Confirmar de novo não vale
    with pytest.raises(ValueError):
        contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    # O histórico mostra só o arquivo confirmado
    historico = contas_abertas.historico(conexao, ESPECIALISTA, "EMP001")
    assert [(arquivo["nome_arquivo"], arquivo["novas"]) for arquivo in historico] == [("semana1.csv", 3)]


def test_mesma_conta_de_antes_e_so_aviso_e_nao_trava(conexao):
    quatro = cpfs_da_aurora(conexao, 4)
    primeira = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(quatro[:3]),
                                               "semana1.csv")
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, primeira["arquivo_id"])
    # Na semana seguinte, as 3 de antes (mesma conta) e 1 nova
    segunda = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(quatro), "semana2.csv")
    assert segunda["pode_importar"] is True and segunda["novas"] == 1 and segunda["divergencias"] == []
    tipos_dos_avisos = []
    for aviso in segunda["avisos"]:
        tipos_dos_avisos.append(aviso["tipo"])
    assert tipos_dos_avisos == ["ja_tinha_conta", "ja_tinha_conta", "ja_tinha_conta"]
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, segunda["arquivo_id"])
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["com_conta"] == 4
    # Descartar não grava nada
    terceira = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(quatro[:1]),
                                               "semana3.csv")
    contas_abertas.descartar(conexao, ESPECIALISTA, terceira["arquivo_id"])
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["com_conta"] == 4


def test_outra_conta_para_o_cpf_ou_conta_de_outro_cpf_trava(conexao):
    tres = cpfs_da_aurora(conexao, 3)
    primeira = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(tres[:1]),
                                               "semana1.csv")
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, primeira["arquivo_id"])
    # O mesmo CPF com outra conta
    outra_conta = arquivo_de_linhas([linha_de_conta(tres[0], conta="99999-9"), linha_de_conta(tres[1])])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", outra_conta, "semana2.csv")
    assert tipos_da_previa(previa) == {"conta_diferente_da_gravada"}
    assert "agência 0001, conta salário 99999-9" in previa["divergencias"][0]["motivo"]
    # A linha limpa conta como nova na prévia (o que entraria depois da correção), mas nada pode ser confirmado
    assert previa["novas"] == 1
    conferir_recusa_depois_da_primeira_baixa(conexao, previa)
    # Outro CPF com a conta já gravada do primeiro
    conta_do_primeiro = arquivo_de_linhas([linha_de_conta(tres[2], conta=conta_de_teste(tres[0]))])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conta_do_primeiro, "semana3.csv")
    assert tipos_da_previa(previa) == {"conta_de_outro_cpf"} and previa["novas"] == 0
    conferir_recusa_depois_da_primeira_baixa(conexao, previa)
    # A mesma conta numa agência diferente é outra conta: passa
    outra_agencia = arquivo_de_linhas([linha_de_conta(tres[2], agencia="0002", conta=conta_de_teste(tres[0]))])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", outra_agencia, "semana4.csv")
    assert previa["pode_importar"] is True and previa["novas"] == 1


def conferir_recusa_depois_da_primeira_baixa(conexao, previa: dict) -> None:
    """A trava depois de uma baixa já feita: nada a confirmar e a Aurora continua com 1 conta."""
    assert previa["pode_importar"] is False and previa["arquivo_id"] is None
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["com_conta"] == 1


def test_conta_antiga_com_o_codigo_do_banco_e_a_mesma_conta(conexao):
    """A conta gravada antes do ADR-149 (com o código do banco) é comparada pela agência e pelo número: o arquivo
    novo com a mesma conta é só aviso; outro CPF com ela trava."""
    dois = cpfs_da_aurora(conexao, 2)
    contas_abertas._preparar(conexao)
    conexao.execute("INSERT INTO contas_abertas (empresa_id, cpf, data_abertura, agencia, conta, codigo_banco, "
                    "arquivo_id, baixa_em, tipo_conta) VALUES ('EMP001', ?, '01/09/2026', '0001', ?, '033', "
                    "'antigo', '2026-09-01', 'NOVA_CONTA')", (dois[0], conta_de_teste(dois[0])))
    conexao.commit()
    igual = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(dois[:1]), "c.csv")
    assert igual["pode_importar"] is True and [aviso["tipo"] for aviso in igual["avisos"]] == ["ja_tinha_conta"]
    de_outro = arquivo_de_linhas([linha_de_conta(dois[1], conta=conta_de_teste(dois[0]))])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", de_outro, "d.csv")
    assert tipos_da_previa(previa) == {"conta_de_outro_cpf"}


def test_confirmar_arquivo_recusado_da_erro(conexao):
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", b"", "contas.csv")
    assert previa["arquivo_id"] is None
    arquivo_id = conexao.execute("SELECT arquivo_id FROM arquivos_de_contas WHERE situacao = 'RECUSADO'").fetchone()[0]
    with pytest.raises(ValueError, match="recusado"):
        contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, arquivo_id)
    with pytest.raises(ValueError, match="recusado"):
        contas_abertas.descartar(conexao, ESPECIALISTA, arquivo_id)


def test_previa_guardada_antes_do_adr_149_ainda_confirma(conexao):
    """Uma prévia PENDENTE guardada no formato de antes (com o código do banco) continua valendo na confirmação."""
    um = cpfs_da_aurora(conexao, 1)[0]
    contas_abertas._preparar(conexao)
    baixa_antiga = {"empresa_id": "EMP001", "cpf": um, "data_abertura": "01/09/2026", "agencia": "0001",
                    "conta": conta_de_teste(um), "codigo_banco": "033", "tipo_conta": "CORRENTISTA",
                    "situacao_correntista": "ATIVO", "folha_ja_identificada": "N"}
    resultado = json.dumps({"novas": [baixa_antiga], "completar": [], "linhas": 1, "avisos": 0})
    conexao.execute("INSERT INTO arquivos_de_contas (arquivo_id, nome_arquivo, enviado_por, enviado_em, situacao, "
                    "resultado, empresa_id) VALUES ('pendente', 'p.csv', 'especialista', '2026-09-29', 'PENDENTE', ?, "
                    "'EMP001')", (resultado,))
    conexao.commit()
    assert contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, "pendente")["novas"] == 1
    gravada = conexao.execute("SELECT codigo_banco, tipo_conta FROM contas_abertas WHERE cpf = ?", (um,)).fetchone()
    assert tuple(gravada) == ("033", "CORRENTISTA")


def cadastrar_na_horizonte(conexao, cpf: str) -> None:
    """Põe o CPF na situação Cadastrado na Horizonte (EMP002), direto na tabela."""
    conexao.execute("INSERT INTO funcionarios_homologados (empresa_id, cpf, processamento_id, homologado_em) "
                    "VALUES ('EMP002', ?, 'teste', '2026-09-28')", (cpf,))
    conexao.commit()


def test_cpf_em_duas_empresas_ganha_a_baixa_pelo_arquivo_de_cada_uma(conexao):
    """ADR-122: o arquivo é de uma empresa só, então a baixa é só nela; a outra ganha pelo arquivo dela."""
    um = cpfs_da_aurora(conexao, 1)[0]
    # A mesma pessoa também cadastrada na Horizonte (EMP002)
    cadastrar_na_horizonte(conexao, um)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas([um]), "contas.csv")
    assert previa["pode_importar"] is True and previa["novas"] == 1
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    esperado = {"data_abertura": DATA_GRAVADA, "agencia": "0001", "conta": conta_de_teste(um), "codigo_banco": "",
                "situacao_na_empresa": "Conta aberta"}
    assert contas_abertas.contas_da_empresa(conexao, "EMP001")[um] == esperado
    assert contas_abertas.contas_da_empresa(conexao, "EMP002") == {}
    # O arquivo da Horizonte dá a baixa lá (a mesma conta do mesmo CPF não é "conta de outro CPF")
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP002", arquivo_de_contas([um]), "horizonte.csv")
    assert previa["pode_importar"] is True and previa["novas"] == 1
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    assert contas_abertas.contas_da_empresa(conexao, "EMP002")[um] == esperado


# ---------------- O arquivo é de UMA empresa: a da ficha (ADR-122 e ADR-149) ----------------

def test_arquivo_de_outra_empresa_e_recusado_pelos_cpfs_e_diz_de_quem_e(conexao):
    """Sem o CNPJ no arquivo, o que prova a empresa são os CPFs: o arquivo da Aurora na ficha da Horizonte é recusado
    inteiro, e o motivo diz que as pessoas estão Cadastradas na Aurora."""
    dois = cpfs_da_aurora(conexao, 2)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP002", arquivo_de_contas(dois), "h.csv")
    assert previa["pode_importar"] is False and tipos_da_previa(previa) == {"cpf_nao_cadastrado"}
    for divergencia in previa["divergencias"]:
        assert divergencia["motivo"].startswith("está Cadastrado em outra empresa (Aurora")
    assert previa["empresa"] == {"empresa_id": "EMP002", "nome": "Horizonte Logística Ltda."}


def test_cpf_cadastrado_em_outra_empresa_recusa_e_diz_qual(conexao):
    um = cpfs_da_aurora(conexao, 1)[0]
    # Uma pessoa Cadastrada só na Horizonte
    so_da_horizonte = gerar_cpf(random.Random(11))
    cadastrar_na_horizonte(conexao, so_da_horizonte)
    conteudo = arquivo_de_linhas([linha_de_conta(um), linha_de_conta(so_da_horizonte)])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "c.csv")
    assert tipos_da_previa(previa) == {"cpf_nao_cadastrado"} and previa["pode_importar"] is False
    motivo = previa["divergencias"][0]["motivo"]
    assert motivo.startswith("está Cadastrado em outra empresa (Horizonte") and "não nesta" in motivo
    conferir_recusa_sem_cpf(conexao, previa, [um, so_da_horizonte])


def test_historico_e_numeros_sao_de_cada_empresa(conexao):
    tres = cpfs_da_aurora(conexao, 3)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(tres), "aurora.csv")
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    # Um arquivo antigo, de antes do ADR-122 (sem empresa): continua no banco e não aparece em nenhum histórico
    conexao.execute("INSERT INTO arquivos_de_contas (arquivo_id, nome_arquivo, enviado_por, enviado_em, situacao, "
                    "resultado, decidido_em) VALUES ('antigo', 'antigo.csv', 'especialista', '2026-09-01', "
                    "'CONFIRMADO', '{\"novas\": 0}', '2026-09-01')")
    conexao.commit()
    historico_da_aurora = contas_abertas.historico(conexao, ESPECIALISTA, "EMP001")
    assert [(arquivo["nome_arquivo"], arquivo["novas"]) for arquivo in historico_da_aurora] == [("aurora.csv", 3)]
    # As contas "depois" são as da Aurora, não as da carteira
    cadastrados_da_aurora = contas_abertas.numeros_de_contas(conexao, "EMP001")["cadastrados"]
    assert historico_da_aurora[0]["carteira_depois"]["com_conta"] == 3
    assert historico_da_aurora[0]["carteira_depois"]["cadastrados"] == cadastrados_da_aurora
    assert contas_abertas.historico(conexao, ESPECIALISTA, "EMP002") == []
    # Só a Aurora já recebeu o arquivo dela: a Horizonte continua "ainda não chegou" (sem o arquivo antigo)
    conexao.execute("DELETE FROM arquivos_de_contas WHERE arquivo_id = 'antigo'")
    conexao.commit()
    assert contas_abertas.numeros_de_contas(conexao, "EMP001")["arquivo_recebido"] is True
    assert contas_abertas.numeros_de_contas(conexao, "EMP002")["arquivo_recebido"] is False
    # O registro do arquivo guarda a empresa
    empresa_gravada = conexao.execute("SELECT empresa_id FROM arquivos_de_contas "
                                      "WHERE nome_arquivo = 'aurora.csv'").fetchone()[0]
    assert empresa_gravada == "EMP001"
    # Empresa que não existe: KeyError (a rota responde 404)
    with pytest.raises(KeyError):
        contas_abertas.historico(conexao, ESPECIALISTA, "EMP999")
    with pytest.raises(KeyError):
        contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP999", arquivo_de_contas(tres), "c.csv")
    with pytest.raises(KeyError):
        contas_abertas.layout_do_arquivo(conexao, "EMP999")


def test_arquivos_de_contas_antigo_ganha_a_coluna_da_empresa(tmp_path):
    """Um banco criado antes do ADR-122 (sem a coluna empresa_id) ganha a coluna sem perder os arquivos."""
    conexao_antiga = banco.conectar(tmp_path / "antigo.db")
    conexao_antiga.execute("CREATE TABLE arquivos_de_contas (arquivo_id TEXT PRIMARY KEY, nome_arquivo TEXT NOT NULL, "
                           "enviado_por TEXT NOT NULL, enviado_em TEXT NOT NULL, situacao TEXT NOT NULL, "
                           "resultado TEXT NOT NULL, decidido_em TEXT)")
    conexao_antiga.execute("INSERT INTO arquivos_de_contas VALUES ('a1', 'velho.csv', 'especialista', '2026-09-01', "
                           "'CONFIRMADO', '{\"novas\": 2}', '2026-09-01')")
    conexao_antiga.commit()
    contas_abertas._preparar(conexao_antiga)
    assert "empresa_id" in banco.colunas_da_tabela(conexao_antiga, "arquivos_de_contas")
    arquivos_guardados = conexao_antiga.execute("SELECT nome_arquivo, empresa_id FROM arquivos_de_contas").fetchall()
    assert arquivos_guardados == [("velho.csv", None)]
    # O arquivo antigo valia para a carteira toda: a empresa conta como "recebido"
    assert contas_abertas.numeros_de_contas(conexao_antiga, "EMP001")["arquivo_recebido"] is True
    conexao_antiga.close()


def test_empresa_ve_o_total_e_so_o_banco_sobe_o_arquivo(conexao):
    # Antes do primeiro arquivo: "ainda não mandou"
    antes = contas_abertas.contas_para_a_empresa(conexao, "EMP001")
    assert antes["arquivo_recebido"] is False and antes["percentual"] is None
    tres = cpfs_da_aurora(conexao, 3)
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_contas(tres), "semana1.csv")
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    depois = contas_abertas.contas_para_a_empresa(conexao, "EMP001")
    assert depois["com_conta"] == 3 and depois["cadastrados"] >= 10 and depois["percentual"] is not None
    # A empresa vê quantos abriram a conta agora e quantos já eram correntistas (ADR-123)
    assert "já têm conta no banco" in depois["texto"] and "3 abriram a conta agora" in depois["texto"]
    assert depois["contas_abertas"] == 3 and depois["ja_correntistas"] == 0
    # O arquivo é por empresa (ADR-122): a Vale Verde (EMP004) ainda não recebeu o dela
    sem_arquivo = contas_abertas.contas_para_a_empresa(conexao, "EMP004")
    assert sem_arquivo["arquivo_recebido"] is False and sem_arquivo["percentual"] is None
    # Com um arquivo confirmado da Vale Verde, mas ninguém cadastrado: nenhum percentual, e o texto diz por quê
    conexao.execute("INSERT INTO arquivos_de_contas (arquivo_id, nome_arquivo, enviado_por, enviado_em, situacao, "
                    "resultado, decidido_em, empresa_id) VALUES ('vale', 'vale.csv', 'especialista', '2026-09-28', "
                    "'CONFIRMADO', '{\"novas\": 0}', '2026-09-28', 'EMP004')")
    conexao.commit()
    sem_ninguem = contas_abertas.contas_para_a_empresa(conexao, "EMP004")
    assert sem_ninguem["percentual"] is None and sem_ninguem["texto"] == "Nenhum funcionário cadastrado ainda."
    # A conta de cada um fica só com a empresa dele (sem o código do banco, que saiu do arquivo)
    contas_da_aurora = contas_abertas.contas_da_empresa(conexao, "EMP001")
    assert contas_da_aurora[tres[0]] == {"data_abertura": DATA_GRAVADA, "agencia": "0001",
                                         "conta": conta_de_teste(tres[0]), "codigo_banco": "",
                                         "situacao_na_empresa": "Conta aberta"}
    assert contas_abertas.contas_da_empresa(conexao, "EMP002") == {}
    # Só o banco sobe e confirma
    with pytest.raises(PermissionError):
        contas_abertas.conferir_arquivo(conexao, RH_DA_AURORA, "EMP001", arquivo_de_contas(tres), "x.csv")


# ---------------- O status: conta nova ou já era correntista (ADR-149) ----------------

def test_previa_e_historico_contam_contas_novas_e_correntistas(conexao):
    quatro = cpfs_da_aurora(conexao, 4)
    linhas = [linha_de_conta(quatro[0]), linha_de_conta(quatro[1], status="2"),
              linha_de_conta(quatro[2], status="2"), linha_de_conta(quatro[3], status="2")]
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(linhas), "t.csv")
    # 1 conta nova e 3 correntistas: o correntista é um grupo só
    esperado = {"nova_conta": 1, "correntista": 3}
    assert previa["pode_importar"] is True and previa["tipos_das_novas"] == esperado
    resultado = contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    assert resultado["tipos_das_novas"] == esperado
    historico = contas_abertas.historico(conexao, ESPECIALISTA, "EMP001")
    assert historico[0]["tipos_das_novas"] == esperado and historico[0]["completadas"] == 0
    # O status fica gravado com o nome que se lê sozinho; a situação e a folha ficam sem valor
    gravados = conexao.execute("SELECT cpf, tipo_conta, situacao_correntista, folha_ja_identificada "
                               "FROM contas_abertas ORDER BY cpf").fetchall()
    assert (quatro[0], "NOVA_CONTA", None, None) in gravados and (quatro[3], "CORRENTISTA", None, None) in gravados
    # O retorno para o planejamento: o tipo de cada CPF, só das empresas pedidas
    retorno = contas_abertas.retorno_por_cpf(conexao, ["EMP001"])
    assert retorno[quatro[0]] == {"tipo_conta": "NOVA_CONTA"}
    assert retorno[quatro[1]] == {"tipo_conta": "CORRENTISTA"}
    assert contas_abertas.retorno_por_cpf(conexao, ["EMP002"]) == {}
    assert contas_abertas.retorno_por_cpf(conexao, []) == {}


def test_mesma_conta_com_o_outro_status_trava(conexao):
    dois = cpfs_da_aurora(conexao, 2)
    # Primeiro arquivo: uma conta nova e um correntista
    linhas = [linha_de_conta(dois[0]), linha_de_conta(dois[1], status="2")]
    primeira = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(linhas), "1.csv")
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, primeira["arquivo_id"])
    # A mesma conta de novo, igualzinha: só aviso
    igual = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(linhas), "2.csv")
    assert igual["pode_importar"] is True and igual["divergencias"] == []
    # A conta nova vira correntista, e o correntista vira conta nova: as duas linhas travam
    trocadas = [linha_de_conta(dois[0], status="2"), linha_de_conta(dois[1], status="1")]
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(trocadas), "3.csv")
    assert tipos_da_previa(previa) == {"status_diferente_do_gravado"} and previa["pode_importar"] is False
    assert len(previa["divergencias"]) == 2
    assert "gravada como Conta nova" in previa["divergencias"][0]["motivo"]
    assert "gravada como Já era correntista" in previa["divergencias"][1]["motivo"]
    # Nada mudou no que estava gravado
    assert contas_abertas.retorno_por_cpf(conexao, ["EMP001"])[dois[1]] == {"tipo_conta": "CORRENTISTA"}


def test_conta_antiga_sem_o_status_ganha_o_status_do_arquivo(conexao):
    um = cpfs_da_aurora(conexao, 1)[0]
    # Uma baixa de um arquivo antigo, de antes do tipo de conta (tipo vazio), com o código do banco
    contas_abertas._preparar(conexao)
    conexao.execute("INSERT INTO contas_abertas (empresa_id, cpf, data_abertura, agencia, conta, codigo_banco, "
                    "arquivo_id, baixa_em) VALUES ('EMP001', ?, '01/09/2026', '0001', ?, '033', 'antigo', "
                    "'2026-09-01')", (um, conta_de_teste(um)))
    conexao.commit()
    assert contas_abertas.retorno_por_cpf(conexao, ["EMP001"])[um] == {"tipo_conta": None}
    # O arquivo novo traz a mesma conta, agora com o status: é aviso, e o arquivo segue
    conteudo = arquivo_de_linhas([linha_de_conta(um, status="2")])
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", conteudo, "c.csv")
    assert previa["pode_importar"] is True and previa["novas"] == 0 and previa["completadas"] == 1
    assert [aviso["tipo"] for aviso in previa["avisos"]] == ["status_completado"]
    resultado = contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    assert resultado["completadas"] == 1
    assert contas_abertas.retorno_por_cpf(conexao, ["EMP001"])[um] == {"tipo_conta": "CORRENTISTA"}
    assert contas_abertas.historico(conexao, ESPECIALISTA, "EMP001")[0]["completadas"] == 1


def test_contas_abertas_antiga_ganha_as_colunas_do_tipo(tmp_path):
    """Um banco criado antes do tipo de conta ganha as colunas sem perder as baixas (que ficam sem o tipo e, até o
    banco mandar o status num arquivo novo, contam como aguardando: o status ainda não foi dito; ADR-123)."""
    conexao_antiga = banco.conectar(tmp_path / "antigo.db")
    conexao_antiga.execute("CREATE TABLE contas_abertas (empresa_id TEXT NOT NULL, cpf TEXT NOT NULL, "
                           "data_abertura TEXT NOT NULL, agencia TEXT NOT NULL, conta TEXT NOT NULL DEFAULT '', "
                           "codigo_banco TEXT NOT NULL DEFAULT '', arquivo_id TEXT NOT NULL, baixa_em TEXT NOT NULL, "
                           "PRIMARY KEY (empresa_id, cpf))")
    conexao_antiga.execute("INSERT INTO contas_abertas VALUES ('EMP001', '52998224725', '01/09/2026', '0001', "
                           "'24725-0', '033', 'a1', '2026-09-01')")
    conexao_antiga.commit()
    contas_abertas._preparar(conexao_antiga)
    colunas = banco.colunas_da_tabela(conexao_antiga, "contas_abertas")
    # As colunas continuam as mesmas do esquema de antes (a situação e a folha, sem uso desde o ADR-149)
    assert "tipo_conta" in colunas and "situacao_correntista" in colunas and "folha_ja_identificada" in colunas
    assert contas_abertas.retorno_por_cpf(conexao_antiga, ["EMP001"]) == {"52998224725": {"tipo_conta": None}}
    # A baixa de antes continua gravada, mas sem o tipo ainda não aparece para a empresa (a mesma regra do painel)
    assert contas_abertas.contas_da_empresa(conexao_antiga, "EMP001") == {}
    conexao_antiga.close()


def test_as_funcoes_da_empresa_nao_trazem_o_tipo_gravado(conexao):
    dois = cpfs_da_aurora(conexao, 2)
    linhas = [linha_de_conta(dois[0], status="2"), linha_de_conta(dois[1], status="2")]
    previa = contas_abertas.conferir_arquivo(conexao, ESPECIALISTA, "EMP001", arquivo_de_linhas(linhas), "c.csv")
    contas_abertas.confirmar_baixa(conexao, ESPECIALISTA, previa["arquivo_id"])
    # A conta de cada funcionário (lista, ficha e download da empresa): banco, agência, conta, data e a situação em
    # palavras ("Já é correntista", ADR-123), nunca o nome gravado do tipo
    for conta in contas_abertas.contas_da_empresa(conexao, "EMP001").values():
        assert set(conta) == {"data_abertura", "agencia", "conta", "codigo_banco", "situacao_na_empresa"}
        assert conta["situacao_na_empresa"] == "Já é correntista"
    # O cartão do total: nenhum nome gravado do tipo
    texto_do_cartao = json.dumps(contas_abertas.contas_para_a_empresa(conexao, "EMP001"), ensure_ascii=False)
    assert "CORRENTISTA" not in texto_do_cartao and "NOVA_CONTA" not in texto_do_cartao


# ---------------- As rotas da API ----------------

@pytest.fixture
def api_das_contas(tmp_path, monkeypatch, verdade):
    """A API apontada para um banco só deste teste, com a Aurora cadastrada. Devolve 3 CPFs e o caminho do banco."""
    conectar_original = auth.conectar
    caminho = tmp_path / "api_contas.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao_do_teste = conectar_original(caminho)
    homologar(conexao_do_teste, "aurora_carga_inicial", verdade)
    auth.cadastrar_usuario(conexao_do_teste, "especialista", SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao_do_teste, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    cpfs = cpfs_da_aurora(conexao_do_teste, 3)
    conexao_do_teste.close()
    return {"cpfs": cpfs, "caminho": caminho}


def entrar(login):
    """Um navegador de mentira logado com o usuário informado."""
    navegador = TestClient(aplicacao)
    assert navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE}).status_code == 200
    return navegador


# Os endereços das rotas de contas da Aurora (ADR-122: o arquivo é subido por empresa)
ROTA_DO_LAYOUT_DA_AURORA = "/api/banco/empresas/EMP001/contas/layout"
ROTA_DE_CONFERIR_DA_AURORA = "/api/banco/empresas/EMP001/contas/conferir"
ROTA_DO_HISTORICO_DA_AURORA = "/api/banco/empresas/EMP001/contas/historico"


def test_rota_do_layout_so_para_o_banco(api_das_contas):
    assert TestClient(aplicacao).get(ROTA_DO_LAYOUT_DA_AURORA).status_code == 401
    assert entrar("rh.aurora").get(ROTA_DO_LAYOUT_DA_AURORA).status_code == 403
    especialista = entrar("especialista")
    resposta = especialista.get(ROTA_DO_LAYOUT_DA_AURORA)
    conexao = banco.conectar(api_das_contas["caminho"])
    esperado = contas_abertas.layout_do_arquivo(conexao, "EMP001")
    conexao.close()
    assert resposta.status_code == 200 and resposta.json() == esperado
    assert resposta.json()["cabecalho"] == CABECALHO and resposta.json()["orientacao_da_empresa"]


def test_rotas_das_contas_de_empresa_que_nao_existe_dao_404_e_as_antigas_sairam(api_das_contas):
    especialista = entrar("especialista")
    arquivo = {"arquivo": ("contas.csv", arquivo_de_contas(api_das_contas["cpfs"]), "text/csv")}
    assert especialista.get("/api/banco/empresas/EMP999/contas/layout").status_code == 404
    assert especialista.post("/api/banco/empresas/EMP999/contas/conferir", files=arquivo).status_code == 404
    assert especialista.get("/api/banco/empresas/EMP999/contas/historico").status_code == 404
    # Sem login: 401 em todas; a EMPRESA: 403 em todas
    anonimo = TestClient(aplicacao)
    rh = entrar("rh.aurora")
    for navegador, codigo_esperado in ((anonimo, 401), (rh, 403)):
        assert navegador.get(ROTA_DO_LAYOUT_DA_AURORA).status_code == codigo_esperado
        assert navegador.post(ROTA_DE_CONFERIR_DA_AURORA, files=arquivo).status_code == codigo_esperado
        assert navegador.get(ROTA_DO_HISTORICO_DA_AURORA).status_code == codigo_esperado
    # As rotas antigas, sem a empresa, não existem mais
    assert especialista.get("/api/banco/contas/layout").status_code in (404, 405)
    assert especialista.post("/api/banco/contas/conferir", files=arquivo).status_code in (404, 405)
    assert especialista.get("/api/banco/contas/historico").status_code in (404, 405)


def test_api_das_contas_por_perfil(api_das_contas):
    especialista = entrar("especialista")
    rh = entrar("rh.aurora")
    arquivo = {"arquivo": ("contas.csv", arquivo_de_contas(api_das_contas["cpfs"]), "text/csv")}
    # A empresa não sobe o arquivo
    assert rh.post(ROTA_DE_CONFERIR_DA_AURORA, files=arquivo).status_code == 403
    previa = especialista.post(ROTA_DE_CONFERIR_DA_AURORA, files=arquivo)
    assert previa.status_code == 200 and previa.json()["novas"] == 3
    assert previa.json()["empresa"]["empresa_id"] == "EMP001"
    assert especialista.post("/api/banco/contas/" + previa.json()["arquivo_id"] + "/confirmar").status_code == 200
    assert especialista.get(ROTA_DO_HISTORICO_DA_AURORA).json()[0]["novas"] == 3
    # O histórico da Horizonte não mostra o arquivo da Aurora
    assert especialista.get("/api/banco/empresas/EMP002/contas/historico").json() == []
    # O mesmo arquivo (CPFs da Aurora) subido na Horizonte é recusado inteiro
    na_horizonte = especialista.post("/api/banco/empresas/EMP002/contas/conferir", files=arquivo).json()
    assert na_horizonte["pode_importar"] is False and tipos_da_previa(na_horizonte) == {"cpf_nao_cadastrado"}
    # A empresa vê o total no resumo
    assert rh.get("/api/empresa/resumo").json()["contas"]["com_conta"] == 3
    assert especialista.post("/api/banco/contas/nao-existe/confirmar").status_code == 404


def test_api_recusa_com_200_e_confirmar_recusado_da_400(api_das_contas):
    especialista = entrar("especialista")
    # Arquivo recusado: a prévia volta com 200, sem nada a confirmar
    arquivo = {"arquivo": ("contas.xlsx", b"PK\x03\x04resto", "application/octet-stream")}
    previa = especialista.post(ROTA_DE_CONFERIR_DA_AURORA, files=arquivo)
    assert previa.status_code == 200
    assert previa.json()["pode_importar"] is False and previa.json()["arquivo_id"] is None
    # Sem arquivo: 400
    assert especialista.post(ROTA_DE_CONFERIR_DA_AURORA).status_code == 400
    # O registro recusado não pode ser confirmado
    conexao = banco.conectar(api_das_contas["caminho"])
    arquivo_id = conexao.execute("SELECT arquivo_id FROM arquivos_de_contas WHERE situacao = 'RECUSADO'").fetchone()[0]
    resultado_guardado = json.loads(conexao.execute("SELECT resultado FROM arquivos_de_contas WHERE arquivo_id = ?",
                                                    (arquivo_id,)).fetchone()[0])
    conexao.close()
    assert resultado_guardado["novas"] == 0
    assert especialista.post("/api/banco/contas/" + arquivo_id + "/confirmar").status_code == 400


def test_t9_t17_a_empresa_ve_a_conta_de_cada_funcionario_dela(api_das_contas):
    """ADR-102: depois da baixa, a lista, a ficha e o download da empresa trazem a conta de quem abriu (onde ela paga
    o salário); quem não abriu vem com a conta vazia. O código do banco vem vazio (saiu do arquivo, ADR-149)."""
    especialista = entrar("especialista")
    rh = entrar("rh.aurora")
    # O banco dá baixa em 3 pessoas
    arquivo = {"arquivo": ("contas.csv", arquivo_de_contas(api_das_contas["cpfs"]), "text/csv")}
    previa = especialista.post(ROTA_DE_CONFERIR_DA_AURORA, files=arquivo).json()
    especialista.post("/api/banco/contas/" + previa["arquivo_id"] + "/confirmar")
    # A lista: as 3 pessoas com agência, conta e data; as outras, vazias
    cpfs_com_conta = set()
    for cpf in api_das_contas["cpfs"]:
        cpfs_com_conta.add(somente_digitos(cpf))
    funcionarios = rh.get("/api/empresa/funcionarios").json()
    com_conta = 0
    for funcionario in funcionarios:
        cpf = somente_digitos(funcionario["cpf"])
        if cpf in cpfs_com_conta:
            com_conta = com_conta + 1
            assert (funcionario["agencia"], funcionario["conta"]) == ("0001", conta_de_teste(cpf))
            assert funcionario["conta_aberta_em"] == DATA_GRAVADA
            assert funcionario["codigo_banco"] == ""
            assert funcionario["situacao"] == "Conta aberta"
        else:
            assert (funcionario["agencia"], funcionario["conta"], funcionario["conta_aberta_em"]) == ("", "", "")
            assert funcionario["situacao"] == "Cadastrado"
    assert com_conta == 3
    # A ficha de quem abriu também traz a conta
    primeira_com_conta = None
    for funcionario in funcionarios:
        if funcionario["conta"]:
            primeira_com_conta = funcionario
    ficha = rh.get("/api/empresa/funcionarios/" + primeira_com_conta["id"]).json()
    assert ficha["conta"] == primeira_com_conta["conta"]
    # O download: as colunas da conta, para o pagamento do salário
    identificadores = []
    for funcionario in funcionarios:
        identificadores.append(funcionario["id"])
    arquivo_baixado = rh.post("/api/empresa/funcionarios/baixar", json={"identificadores": identificadores})
    linhas_baixadas = arquivo_baixado.content.decode("utf-8-sig").splitlines()
    assert linhas_baixadas[0].endswith("Situação;Conta salário aberta em;Código do banco;Agência;Conta salário")
    assert ";Conta aberta;" in arquivo_baixado.content.decode("utf-8-sig")
    assert conta_de_teste(somente_digitos(primeira_com_conta["cpf"])) in arquivo_baixado.content.decode("utf-8-sig")
    # O total continua no resumo
    assert rh.get("/api/empresa/resumo").json()["contas"]["com_conta"] == 3


# O que nunca pode aparecer numa resposta para a empresa: os nomes das colunas do banco e os nomes gravados do tipo.
# "\b" é a borda de uma palavra: "ATIVO" sozinho casa, mas não dentro de "NEGATIVO" nem de "INATIVO" (que tem a dele)
PALAVRAS_SO_DO_BANCO = re.compile(r"situacao_correntista|tipo_conta|\bATIVO\b|\bINATIVO\b|\bCORRENTISTA\b|"
                                  r"\bNOVA_CONTA\b|folha_ja_identificada|falso_nao_folha|falso não folha")


def enderecos_das_rotas_da_empresa(valores_dos_parametros: dict) -> list[str]:
    """Os endereços de TODAS as rotas GET /api/empresa/... da aplicação, com os parâmetros trocados por valores reais.

    Recebe: {nome do parâmetro: valor} (ex.: {"identificador": "abc"}). Devolve: os endereços prontos para pedir.
    Pegar as rotas da própria aplicação garante que uma rota nova da empresa entra neste teste sozinha.
    """
    enderecos = []
    for rota in aplicacao.routes:
        caminho = getattr(rota, "path", "")
        metodos = getattr(rota, "methods", set()) or set()
        # Só as rotas da empresa que devolvem dados (GET)
        if not caminho.startswith("/api/empresa") or "GET" not in metodos:
            continue
        # Cada "{parametro}" do caminho vira o valor real (ou "x", que dá 404 e também não pode vazar nada)
        for nome_do_parametro in re.findall(r"\{([^}]+)\}", caminho):
            caminho = caminho.replace("{" + nome_do_parametro + "}", valores_dos_parametros.get(nome_do_parametro, "x"))
        enderecos.append(caminho)
    return enderecos


def test_nenhuma_rota_da_empresa_devolve_o_tipo_gravado(api_das_contas):
    """O nome gravado do tipo e os nomes das colunas do banco são só do banco: a empresa vê o status só em palavras
    ("Conta aberta" ou "Já é correntista")."""
    especialista = entrar("especialista")
    rh = entrar("rh.aurora")
    # O banco dá baixa em 3 pessoas: dois correntistas e uma conta nova
    cpfs = api_das_contas["cpfs"]
    linhas = [linha_de_conta(cpfs[0], status="2"), linha_de_conta(cpfs[1], status="2"), linha_de_conta(cpfs[2])]
    arquivo = {"arquivo": ("contas.csv", arquivo_de_linhas(linhas), "text/csv")}
    previa = especialista.post(ROTA_DE_CONFERIR_DA_AURORA, files=arquivo).json()
    assert previa["tipos_das_novas"] == {"nova_conta": 1, "correntista": 2}
    assert especialista.post("/api/banco/contas/" + previa["arquivo_id"] + "/confirmar").status_code == 200
    # Os valores reais dos parâmetros: um funcionário com conta e o envio da Aurora
    funcionarios = rh.get("/api/empresa/funcionarios").json()
    identificadores = []
    identificador_com_conta = ""
    for funcionario in funcionarios:
        identificadores.append(funcionario["id"])
        if funcionario["conta"]:
            identificador_com_conta = funcionario["id"]
    conexao = banco.conectar(api_das_contas["caminho"])
    envio_da_aurora = processamentos.listar(conexao, "EMP001")[0].processamento_id
    conexao.close()
    valores = {"identificador": identificador_com_conta, "processamento_id": envio_da_aurora}
    enderecos = enderecos_das_rotas_da_empresa(valores)
    # As rotas principais da empresa estão na varredura (a lista, a ficha e o resumo)
    assert "/api/empresa/funcionarios" in enderecos and "/api/empresa/resumo" in enderecos
    assert "/api/empresa/funcionarios/" + identificador_com_conta in enderecos
    for endereco in enderecos:
        resposta = rh.get(endereco)
        achado = PALAVRAS_SO_DO_BANCO.search(resposta.content.decode("utf-8", errors="replace"))
        assert achado is None, endereco + " devolveu " + achado.group(0)
    # O download da lista de funcionários também não traz
    baixado = rh.post("/api/empresa/funcionarios/baixar", json={"identificadores": identificadores})
    assert baixado.status_code == 200
    assert PALAVRAS_SO_DO_BANCO.search(baixado.content.decode("utf-8-sig")) is None
    # E o banco, sim, vê a divisão no histórico
    historico = especialista.get(ROTA_DO_HISTORICO_DA_AURORA).json()
    assert historico[0]["tipos_das_novas"] == {"nova_conta": 1, "correntista": 2}
