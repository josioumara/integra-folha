"""Contas abertas: o arquivo do banco dá baixa em cada funcionário cadastrado que já tem conta (ADR-69, passo 16).

Para que serve: os sistemas do banco geram um arquivo com uma linha por funcionário que tem conta. O especialista sobe
um arquivo POR EMPRESA, na ficha da empresa do Portal Interno (aba "Contas abertas", botão "Carregar Contas Abertas";
ADR-122), e o sistema:
    1. confere o arquivo contra um LAYOUT FIXO (ADR-149): um .csv separado por ";",
       com o cabeçalho exato "cpf;status;agencia;conta;data_abertura" e o formato certo em cada coluna. O status diz
       o que o banco fez com o funcionário: 1 = Conta nova (o banco abriu a conta agora) ou 2 = Já era correntista
       (ele já tinha conta no banco: a agência, a conta e a data são as da conta que ele já tinha). Só este formato é
       aceito: o antigo, com o CNPJ, o código do banco e a situação do correntista, é recusado;
    2. a empresa do arquivo é a da tela (a ficha aberta): cada linha é conferida contra a carteira DESSA empresa. O
       CPF precisa ser de um funcionário na situação Cadastrado nela (se ele está Cadastrado em outra empresa, o motivo
       diz qual), e a conta e o status não podem brigar com o que já está gravado;
    3. monta a PRÉVIA. Com QUALQUER divergência, o arquivo inteiro é recusado (nada pode ser confirmado): o
       especialista corrige o arquivo e sobe de novo. Sem divergência, a prévia fica PENDENTE;
    4. só no "Confirmar a baixa" as contas novas entram na tabela contas_abertas (quem subiu, quando e o arquivo).
Com isso, o percentual de contas abertas da empresa deixa de ser "ainda não chegou". A prévia e o histórico contam as
novas contas e os correntistas, só para o banco. O histórico também é por empresa: cada arquivo guarda a empresa para a
qual foi subido (arquivos antigos, de antes do ADR-122, não têm empresa e não aparecem no histórico de nenhuma).

Fonte única do layout: os formatos, os títulos e as explicações de cada conferência ficam nas constantes abaixo, e a
função layout_do_arquivo() as entrega à tela. Assim a tela explica exatamente o que este código confere.

Quem vê o quê: o especialista vê o CPF inteiro das linhas com divergência (o arquivo é do próprio banco).
A EMPRESA vê a conta de cada funcionário dela (agência, número e data de abertura), porque é
nessa conta que ela vai pagar o salário (ADR-102), e se a conta foi aberta agora ("Conta aberta") ou se ele já era
cliente ("Já é correntista"). Nunca a conta de funcionário de outra empresa. O código do banco não vem mais no arquivo
(ADR-149): nas baixas novas ele fica vazio (nada é suposto). As colunas da situação do correntista e da folha já
identificada continuam na tabela, sem uso (a mudança não mexeu no esquema do banco).
Tabelas: contas_abertas (uma linha por funcionário com conta) e arquivos_de_contas (cada arquivo subido, com a
empresa para a qual foi subido).
"""
import csv
import io
import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from services import acompanhamento, banco, dados_mock, ingestao, processamentos
from services import empresas as cadastro_de_empresas
from services.documentos import cpf_valido
from services.permissoes import autorizar

# ============================== 1. O layout fixo do arquivo ==============================

# O arquivo é sempre um .csv (texto), com as colunas separadas por ponto e vírgula. Excel não é aceito
EXTENSAO_DO_ARQUIVO = ".csv"
SEPARADOR_DE_COLUNAS = ";"

# As colunas do arquivo, NESTA ordem, todas obrigatórias (ADR-149:
# "cpf;status;agencia;conta;data_abertura"): o nome exato no cabeçalho, o título para a tela, o formato em palavras e
# um exemplo. É daqui que saem o cabeçalho esperado, as linhas de exemplo e as explicações da tela
COLUNAS_DO_ARQUIVO = (
    {"nome": "cpf", "titulo": "CPF", "formato": "11 dígitos, só números, com os dígitos verificadores válidos",
     "exemplo": "52998224725"},
    # O que o banco fez com o funcionário (1 = conta nova e 2 = já era correntista)
    {"nome": "status", "titulo": "Status",
     "formato": "1 = Conta nova (o banco abriu a conta agora); 2 = Já era correntista (ele já tinha conta no banco: "
                "a agência, a conta salário e a data são as da conta que ele já tinha)",
     "exemplo": "1"},
    {"nome": "agencia", "titulo": "Agência", "formato": "4 dígitos", "exemplo": "0123"},
    {"nome": "conta", "titulo": "Conta salário", "formato": "1 a 12 dígitos, traço e 1 dígito verificador",
     "exemplo": "45678-9"},
    {"nome": "data_abertura", "titulo": "Data de abertura", "formato": "AAAA-MM-DD, uma data que existe e não é futura",
     "exemplo": "2026-09-29"},
)

# O cabeçalho que o arquivo TEM de trazer na primeira linha, montado a partir das colunas acima
NOMES_DAS_COLUNAS = []
for coluna_do_layout in COLUNAS_DO_ARQUIVO:
    NOMES_DAS_COLUNAS.append(coluna_do_layout["nome"])
CABECALHO_ESPERADO = SEPARADOR_DE_COLUNAS.join(NOMES_DAS_COLUNAS)

# Quantas colunas cada linha tem de ter (5), para as mensagens das conferências
QUANTIDADE_DE_COLUNAS = len(COLUNAS_DO_ARQUIVO)
# Em que posição da linha está o CPF (contando do zero: 0 é a primeira coluna)
POSICAO_DO_CPF = NOMES_DAS_COLUNAS.index("cpf")


# Os códigos da coluna status, como vêm no arquivo
CODIGO_NOVA_CONTA = "1"
CODIGO_CORRENTISTA = "2"
# Como cada status fica gravado na tabela contas_abertas, na coluna tipo_conta (o código do arquivo vira um nome que
# se lê sozinho)
TIPO_NOVA_CONTA = "NOVA_CONTA"
TIPO_CORRENTISTA = "CORRENTISTA"
TIPO_GRAVADO_POR_CODIGO = {CODIGO_NOVA_CONTA: TIPO_NOVA_CONTA, CODIGO_CORRENTISTA: TIPO_CORRENTISTA}
# Os dois status, com o nome e a explicação que a tela mostra (fonte única da orientação)
VALORES_DO_STATUS = (
    {"codigo": CODIGO_NOVA_CONTA, "nome": "Conta nova", "explicacao": "o banco abriu a conta agora"},
    {"codigo": CODIGO_CORRENTISTA, "nome": "Já era correntista",
     "explicacao": "o funcionário já tinha conta no banco; a agência, a conta salário e a data são as da conta que "
                   "ele já tinha"},
)
# A legenda curta dos dois códigos, que a tela mostra em destaque: "1 = Conta nova · 2 = Já era correntista"
LEGENDA_DO_STATUS = CODIGO_NOVA_CONTA + " = Conta nova · " + CODIGO_CORRENTISTA + " = Já era correntista"

# O "molde" de cada coluna, em expressão regular (um padrão de texto que o Python sabe comparar):
# [0-9]{4} quer dizer "exatamente 4 dígitos"; [0-9]{1,12} quer dizer "de 1 a 12 dígitos"
MOLDE_DA_COLUNA = {
    "cpf": re.compile(r"[0-9]{11}"),
    # "[12]" quer dizer "o dígito 1 ou o dígito 2", e nada mais
    "status": re.compile(r"[12]"),
    "agencia": re.compile(r"[0-9]{4}"),
    "conta": re.compile(r"[0-9]{1,12}-[0-9]"),
    "data_abertura": re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
}
# Como a data de abertura vem no arquivo (ano-mês-dia), para o Python conferir se ela existe
FORMATO_DA_DATA_NO_ARQUIVO = "%Y-%m-%d"
# Como a data fica gravada na tabela (dia/mês/ano, o mesmo das contas antigas, que as telas já mostram assim)
FORMATO_DA_DATA_GRAVADA = "%d/%m/%Y"
# As colunas que formam a conta: a mesma agência e o mesmo número são a mesma conta (o código do banco saiu do
# arquivo; é sempre o banco que manda o arquivo)
COLUNAS_DA_CONTA = ("agencia", "conta")

# ============================== 2. As conferências (tipos de divergência) ==============================

# Os três grupos de conferência: o arquivo inteiro, cada linha sozinha e cada linha contra a carteira
GRUPO_ARQUIVO, GRUPO_LINHA, GRUPO_CARTEIRA = "arquivo", "linha", "carteira"

# Todas as conferências, na ordem em que a tela as mostra. "trava" diz se ela recusa o arquivo (só o aviso de quem já
# tinha a mesma conta não trava). "como_corrigir" é o que o especialista faz no arquivo antes de subir de novo
VALIDACOES = (
    {"tipo": "formato_do_arquivo", "grupo": GRUPO_ARQUIVO, "trava": True,
     "titulo": "Arquivo que não é um .csv de texto",
     "descricao": "O arquivo precisa ser um .csv (texto separado por \";\"). Excel, PDF e outros formatos são recusados.",
     "como_corrigir": "Gere o arquivo de novo como .csv separado por \";\" e suba outra vez."},
    {"tipo": "arquivo_vazio", "grupo": GRUPO_ARQUIVO, "trava": True,
     "titulo": "Arquivo sem linhas de contas",
     "descricao": "O arquivo precisa ter pelo menos uma linha de conta depois do cabeçalho.",
     "como_corrigir": "Confira se é o arquivo certo: ele precisa ter uma linha por conta aberta."},
    {"tipo": "cabecalho", "grupo": GRUPO_ARQUIVO, "trava": True,
     "titulo": "Cabeçalho diferente do layout",
     "descricao": "A primeira linha precisa ser exatamente \"" + CABECALHO_ESPERADO + "\", nessa ordem. O layout "
                  "antigo, com o CNPJ da empresa, o código do banco e a situação do correntista, não é mais aceito.",
     "como_corrigir": "Gere o arquivo no formato novo, com a primeira linha \"" + CABECALHO_ESPERADO + "\"."},
    {"tipo": "quantidade_de_colunas", "grupo": GRUPO_ARQUIVO, "trava": True,
     "titulo": "Linha sem as " + str(QUANTIDADE_DE_COLUNAS) + " colunas",
     "descricao": "Cada linha precisa ter exatamente " + str(QUANTIDADE_DE_COLUNAS) + " colunas separadas por \";\".",
     "como_corrigir": "Acerte a linha para ter as " + str(QUANTIDADE_DE_COLUNAS) + " colunas, na ordem do cabeçalho."},
    {"tipo": "campo_vazio", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "Coluna vazia",
     "descricao": "Todas as colunas são obrigatórias: nenhuma pode vir vazia.",
     "como_corrigir": "Preencha a coluna vazia com a informação do sistema do banco."},
    {"tipo": "cpf_invalido", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "CPF inválido",
     "descricao": "O CPF precisa ter 11 dígitos, só números, e os dígitos verificadores precisam conferir.",
     "como_corrigir": "Corrija o CPF (sem pontos nem traço, com os zeros do começo)."},
    {"tipo": "status_invalido", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "Status vazio ou diferente de 1 e 2",
     "descricao": "O status é obrigatório e só aceita 1 (Conta nova) ou 2 (Já era correntista: o funcionário já "
                  "tinha conta no banco).",
     "como_corrigir": "Informe 1 se o banco abriu a conta agora, ou 2 se o funcionário já era correntista."},
    {"tipo": "agencia_invalida", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "Agência inválida",
     "descricao": "A agência precisa ter 4 dígitos (ex.: 0123).",
     "como_corrigir": "Corrija a agência, com os zeros do começo."},
    {"tipo": "conta_invalida", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "Conta salário inválida",
     "descricao": "A conta salário precisa ter de 1 a 12 dígitos, um traço e 1 dígito verificador (ex.: 45678-9).",
     "como_corrigir": "Corrija a conta salário, com o traço antes do dígito verificador."},
    {"tipo": "data_invalida", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "Data de abertura inválida",
     "descricao": "A data precisa estar como AAAA-MM-DD (ex.: 2026-09-29), existir no calendário e não ser futura.",
     "como_corrigir": "Corrija a data de abertura da conta salário, no formato ano-mês-dia."},
    {"tipo": "cpf_repetido_no_arquivo", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "CPF repetido no arquivo",
     "descricao": "Cada CPF pode aparecer uma vez só no arquivo.",
     "como_corrigir": "Deixe uma linha só para este CPF."},
    {"tipo": "conta_repetida_no_arquivo", "grupo": GRUPO_LINHA, "trava": True,
     "titulo": "Mesma conta salário em CPFs diferentes",
     "descricao": "A mesma conta salário (agência e número) não pode aparecer para CPFs diferentes.",
     "como_corrigir": "Confira no sistema do banco de quem é a conta salário e corrija a linha errada."},
    {"tipo": "cpf_nao_cadastrado", "grupo": GRUPO_CARTEIRA, "trava": True,
     "titulo": "CPF que não está Cadastrado nesta empresa",
     "descricao": "Só entra o CPF de funcionário na situação Cadastrado nesta empresa (a da ficha aberta). Se ele "
                  "está Cadastrado em outra empresa, o motivo diz qual: o arquivo pode ser dela.",
     "como_corrigir": "Confira se o arquivo é desta empresa. Se for, tire a linha: ela entra num arquivo seguinte, "
                      "depois que a pessoa for cadastrada nesta empresa (ou no arquivo da empresa em que ela está "
                      "Cadastrada)."},
    {"tipo": "conta_diferente_da_gravada", "grupo": GRUPO_CARTEIRA, "trava": True,
     "titulo": "CPF que já tem outra conta salário gravada",
     "descricao": "O CPF já tem uma conta salário gravada, diferente da que veio no arquivo.",
     "como_corrigir": "Confira no sistema do banco qual é a conta salário certa; se for a gravada, tire a linha do "
                      "arquivo."},
    {"tipo": "conta_de_outro_cpf", "grupo": GRUPO_CARTEIRA, "trava": True,
     "titulo": "Conta salário já gravada para outro CPF",
     "descricao": "A conta salário (agência e número) já está gravada para outro CPF.",
     "como_corrigir": "Confira no sistema do banco de quem é a conta salário e corrija a linha."},
    {"tipo": "status_diferente_do_gravado", "grupo": GRUPO_CARTEIRA, "trava": True,
     "titulo": "Mesma conta salário já gravada com o outro status",
     "descricao": "O CPF já tem esta mesma conta salário gravada, mas com o outro status (Conta nova ou Já era "
                  "correntista).",
     "como_corrigir": "Confira no sistema do banco o status certo; se for o gravado, tire a linha do arquivo."},
    {"tipo": "status_completado", "grupo": GRUPO_CARTEIRA, "trava": False,
     "titulo": "Conta salário gravada sem o status (arquivo antigo)",
     "descricao": "O CPF já tinha esta mesma conta salário gravada por um arquivo antigo, sem o status: o que veio "
                  "neste arquivo passa a valer para ela, e o arquivo segue.",
     "como_corrigir": "Nada a fazer: é só um aviso."},
    {"tipo": "ja_tinha_conta", "grupo": GRUPO_CARTEIRA, "trava": False,
     "titulo": "CPF que já tinha esta mesma conta salário",
     "descricao": "O CPF já tinha exatamente esta conta salário gravada, com o mesmo status: a linha é ignorada e o "
                  "arquivo segue.",
     "como_corrigir": "Nada a fazer: é só um aviso."},
)

# A conferência de cada tipo, pelo nome do tipo (para achar o título e o "como corrigir" de uma divergência)
VALIDACAO_POR_TIPO = {}
for validacao_do_layout in VALIDACOES:
    VALIDACAO_POR_TIPO[validacao_do_layout["tipo"]] = validacao_do_layout

# O tipo de divergência de cada coluna com o formato errado
TIPO_DO_FORMATO_ERRADO = {
    "cpf": "cpf_invalido",
    "status": "status_invalido",
    "agencia": "agencia_invalida",
    "conta": "conta_invalida",
    "data_abertura": "data_invalida",
}

# A tela mostra no máximo estas divergências (e estes avisos); a contagem por tipo continua certa
LIMITE_DE_ITENS_NA_PREVIA = 500

# Os motivos de um CPF que não está Cadastrado, conforme o ponto da jornada em que a pessoa está
MOTIVO_NUNCA_ENVIADO = "não foi enviado ao banco por esta empresa"

# Situações de um arquivo subido: PENDENTE (prévia sem divergência, esperando a decisão), CONFIRMADO, DESCARTADO e
# RECUSADO (com divergência: fica só o registro de que foi subido, sem nenhum CPF)
PENDENTE, CONFIRMADO, DESCARTADO, RECUSADO = "PENDENTE", "CONFIRMADO", "DESCARTADO", "RECUSADO"


def empresa_do_arquivo(conexao, empresa_id: str) -> dict:
    """A empresa para a qual o arquivo é subido: a da ficha aberta na tela (ADR-149: o arquivo não traz mais o CNPJ).

    Recebe: conexao; empresa_id. Levanta KeyError se a empresa não existe (a rota responde 404).
    Devolve: {empresa_id, nome}. Exemplo: {"empresa_id": "EMP001", "nome": "Aurora Alimentos Ltda."}.
    """
    # O cadastro da empresa (KeyError se não existe)
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    return {"empresa_id": empresa["empresa_id"], "nome": empresa["nome"]}


def _orientacao_da_empresa(empresa: dict) -> str:
    """O texto que a tela mostra em destaque: o arquivo é desta empresa, e cada linha traz o CPF de um funcionário
    Cadastrado nela, o status e a conta.

    Recebe: a empresa de empresa_do_arquivo(). Devolve: o texto.
    Exemplo: "O arquivo é da Aurora Alimentos Ltda., a empresa desta ficha: cada linha traz o CPF de um funcionário
    Cadastrado nela, o status (1 = Conta nova ...; 2 = Já era correntista ...) e a agência, a conta salário e a data
    de abertura dessa conta. Um CPF que não está Cadastrado nesta empresa (por exemplo, de outra empresa) recusa o
    arquivo inteiro."
    """
    # Os dois códigos do status, na ordem da constante (ex.: "1 = Conta nova (o banco abriu ...)")
    textos_do_status = []
    for valor_do_status in VALORES_DO_STATUS:
        textos_do_status.append(valor_do_status["codigo"] + " = " + valor_do_status["nome"] + " (" +
                                valor_do_status["explicacao"] + ")")
    return ("O arquivo é da " + empresa["nome"] + ", a empresa desta ficha: cada linha traz o CPF de um funcionário "
            "Cadastrado nela, o status (" + "; ".join(textos_do_status) + ") e a agência, a conta salário e a data "
            "de abertura dessa conta. Um CPF que não está Cadastrado nesta empresa (por exemplo, de outra empresa) "
            "recusa o arquivo inteiro.")


def layout_do_arquivo(conexao, empresa_id: str) -> dict:
    """O layout do arquivo de contas abertas de UMA empresa, para a tela explicar exatamente o que o sistema confere.

    Recebe: conexao; empresa_id (a empresa aberta na ficha). Levanta KeyError se a empresa não existe.
    Devolve: {extensao, separador, cabecalho, colunas: [{nome, titulo, formato, exemplo}], exemplo_de_linhas,
    validacoes: [{tipo, grupo, titulo, descricao, como_corrigir, trava}], empresa: {empresa_id, nome},
    orientacao_da_empresa, valores_do_status: [{codigo, nome, explicacao}], legenda_do_status: "1 = Conta nova · 2 =
    Já era correntista"}. Tudo sai das constantes deste arquivo: mudou aqui, a tela muda junto. O exemplo tem uma linha
    de cada status (uma conta nova e um correntista).
    """
    empresa = empresa_do_arquivo(conexao, empresa_id)
    # Cópias das colunas, das conferências e dos status, para quem recebe não mexer nas constantes por engano
    colunas = []
    for coluna in COLUNAS_DO_ARQUIVO:
        colunas.append(dict(coluna))
    validacoes = []
    for validacao in VALIDACOES:
        validacoes.append(dict(validacao))
    valores_do_status = []
    for valor_do_status in VALORES_DO_STATUS:
        valores_do_status.append(dict(valor_do_status))
    return {"extensao": EXTENSAO_DO_ARQUIVO, "separador": SEPARADOR_DE_COLUNAS, "cabecalho": CABECALHO_ESPERADO,
            "colunas": colunas, "exemplo_de_linhas": _linhas_de_exemplo(), "validacoes": validacoes,
            "empresa": empresa, "orientacao_da_empresa": _orientacao_da_empresa(empresa),
            "valores_do_status": valores_do_status, "legenda_do_status": LEGENDA_DO_STATUS}


def _linhas_de_exemplo() -> list[str]:
    """As duas linhas do arquivo de exemplo (o modelo que a tela oferece para baixar): uma conta nova e um correntista.

    Recebe: nada. Devolve: as duas linhas, já com o ";" (um exemplo de cada status, com CPFs que passam na conta dos
    dígitos verificadores). Exemplo: ["52998224725;1;0123;45678-9;2026-09-29",
    "11144477735;2;0456;11223-4;2019-03-10"].
    """
    # 1ª linha: o banco abriu a conta agora (status 1)
    conta_nova = ["52998224725", CODIGO_NOVA_CONTA, "0123", "45678-9", "2026-09-29"]
    # 2ª linha: o funcionário já era correntista (status 2), com a conta que ele já tinha
    correntista = ["11144477735", CODIGO_CORRENTISTA, "0456", "11223-4", "2019-03-10"]
    return [SEPARADOR_DE_COLUNAS.join(conta_nova), SEPARADOR_DE_COLUNAS.join(correntista)]


# ============================== 3. Tabelas e apoio ==============================

def _preparar(conexao) -> None:
    """Cria as tabelas das contas abertas e dos arquivos subidos, se ainda não existirem."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS contas_abertas (
               empresa_id     TEXT NOT NULL,
               cpf            TEXT NOT NULL,
               data_abertura  TEXT NOT NULL,
               agencia        TEXT NOT NULL,
               conta          TEXT NOT NULL DEFAULT '',
               codigo_banco   TEXT NOT NULL DEFAULT '',
               arquivo_id     TEXT NOT NULL,
               baixa_em       TEXT NOT NULL,
               tipo_conta     TEXT,
               situacao_correntista TEXT,
               folha_ja_identificada TEXT,
               PRIMARY KEY (empresa_id, cpf)
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS arquivos_de_contas (
               arquivo_id    TEXT PRIMARY KEY,
               nome_arquivo  TEXT NOT NULL,
               enviado_por   TEXT NOT NULL,
               enviado_em    TEXT NOT NULL,
               situacao      TEXT NOT NULL,
               resultado     TEXT NOT NULL,
               decidido_em   TEXT,
               empresa_id    TEXT
           )"""
    )
    # Bancos criados antes do ADR-122 não tinham a empresa do arquivo: acrescenta a coluna vazia. Os arquivos antigos
    # continuam no banco, sem empresa (não aparecem no histórico de nenhuma empresa)
    if "empresa_id" not in banco.colunas_da_tabela(conexao, "arquivos_de_contas"):
        conexao.execute("ALTER TABLE arquivos_de_contas ADD COLUMN empresa_id TEXT")
    # Bancos criados antes do ADR-102 não tinham o número da conta: acrescenta sem perder as baixas já feitas
    colunas_existentes = banco.colunas_da_tabela(conexao, "contas_abertas")
    if "conta" not in colunas_existentes:
        conexao.execute("ALTER TABLE contas_abertas ADD COLUMN conta TEXT NOT NULL DEFAULT ''")
    # Bancos criados antes do ADR-113 não tinham o código do banco: as baixas antigas ficam vazias (nada é suposto)
    if "codigo_banco" not in colunas_existentes:
        conexao.execute("ALTER TABLE contas_abertas ADD COLUMN codigo_banco TEXT NOT NULL DEFAULT ''")
    # Bancos criados antes do tipo de conta: as baixas antigas ficam sem o tipo e
    # sem a situação (NULL = "retorno sem o tipo", nada é suposto)
    if "tipo_conta" not in colunas_existentes:
        conexao.execute("ALTER TABLE contas_abertas ADD COLUMN tipo_conta TEXT")
    if "situacao_correntista" not in colunas_existentes:
        conexao.execute("ALTER TABLE contas_abertas ADD COLUMN situacao_correntista TEXT")
    # Bancos criados antes da folha já identificada: os correntistas antigos ficam sem ela (NULL), até um arquivo novo
    # trazer a informação (nada é suposto)
    if "folha_ja_identificada" not in colunas_existentes:
        conexao.execute("ALTER TABLE contas_abertas ADD COLUMN folha_ja_identificada TEXT")


def _agora() -> str:
    """A data e hora de agora, no horário universal (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _somente_digitos(texto: str) -> str:
    """Tira pontos, traço e espaços: "529.982.247-25" → "52998224725"."""
    digitos = ""
    for caractere in texto or "":
        if caractere.isdigit():
            digitos = digitos + caractere
    return digitos


def _divergencia(linha: int, cpf: str, tipo: str, motivo: str) -> dict:
    """Uma divergência (ou aviso) no formato da prévia.

    Recebe: linha (a linha do arquivo, contando o cabeçalho como 1; 0 se nem deu para ler); cpf (como veio, ou "");
    tipo (um dos tipos de VALIDACOES); motivo (o que está errado, em linguagem simples).
    Devolve: {linha, cpf (formatado quando tem 11 dígitos), tipo, motivo, como_corrigir}.
    Exemplo: _divergencia(3, "52998224725", "cpf_repetido_no_arquivo", "...") →
    {"linha": 3, "cpf": "529.982.247-25", ...}.
    """
    cpf_para_a_tela = ""
    # O CPF sai formatado quando tem os 11 dígitos; senão, como veio (para o especialista achar a linha)
    if cpf:
        cpf_para_a_tela = acompanhamento.formatar_cpf(cpf)
    return {"linha": linha, "cpf": cpf_para_a_tela, "tipo": tipo, "motivo": motivo,
            "como_corrigir": VALIDACAO_POR_TIPO[tipo]["como_corrigir"]}


def _texto_da_conta(chave_da_conta: tuple) -> str:
    """A conta em texto, para os motivos.

    Exemplo: ("0123", "45678-9") → "agência 0123, conta salário 45678-9".
    """
    agencia, conta = chave_da_conta
    return "agência " + agencia + ", conta salário " + conta


# ============================== 4. Leitura do arquivo ==============================

def _texto_do_arquivo(conteudo: bytes) -> str | None:
    """O texto do arquivo, em UTF-8 (com ou sem a marca BOM) ou, se não der, em Latin-1.

    Recebe: os bytes do arquivo. Devolve: o texto, ou None se o conteúdo não é texto (um Excel ou PDF renomeado para
    .csv, ou um texto com byte nulo, como o "Texto Unicode" do Excel).
    """
    # Começo de zip (Excel .xlsx), PDF ou programa: não é texto
    for assinatura in ingestao.ASSINATURAS_QUE_NAO_SAO_TEXTO:
        if conteudo.startswith(assinatura):
            return None
    # O Excel antigo (.xls) também não é texto
    if conteudo.startswith(ingestao.ASSINATURA_DO_OLE):
        return None
    # Texto de verdade não tem byte nulo (o UTF-16 tem um a cada letra)
    if b"\x00" in conteudo:
        return None
    # "utf-8-sig" lê o UTF-8 e tira a marca BOM do começo, se houver
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Não é UTF-8: o Latin-1 (o padrão antigo do Windows no Brasil) lê qualquer sequência de bytes
        return conteudo.decode("latin-1")


def _linha_esta_em_branco(celulas: list[str]) -> bool:
    """True se a linha não tem nada: nenhuma célula, ou só células vazias (ex.: ";;;;" no fim de um Excel)."""
    for celula in celulas:
        if celula.strip():
            return False
    return True


def _diferencas_do_cabecalho(nomes_recebidos: list[str]) -> str:
    """O pedaço do motivo que diz quais colunas do layout não vieram no cabeçalho e quais vieram a mais (vazio se o
    problema é só a ordem).

    Recebe: os nomes do cabeçalho recebido, sem espaços. Devolve: o texto, começando com ". ".
    Exemplos: sem a data → ". Falta a coluna data_abertura"; o layout antigo ("cnpj_empresa;cpf;codigo_banco;...") →
    ". Falta a coluna status. Sobram as colunas cnpj_empresa, codigo_banco, ...: elas não fazem parte do arquivo".
    """
    # As colunas do layout que não vieram
    faltando = []
    for nome in NOMES_DAS_COLUNAS:
        if nome not in nomes_recebidos:
            faltando.append(nome)
    # As colunas que vieram e não são do layout (ex.: as do layout antigo), sem as vazias
    sobrando = []
    for nome in nomes_recebidos:
        if nome and nome not in NOMES_DAS_COLUNAS:
            sobrando.append(nome)
    texto = ""
    # Uma coluna só: no singular
    if len(faltando) == 1:
        texto = texto + ". Falta a coluna " + faltando[0]
    elif faltando:
        texto = texto + ". Faltam as colunas " + ", ".join(faltando)
    if len(sobrando) == 1:
        texto = texto + ". Sobra a coluna " + sobrando[0] + ": ela não faz parte do arquivo"
    elif sobrando:
        texto = texto + ". Sobram as colunas " + ", ".join(sobrando) + ": elas não fazem parte do arquivo"
    return texto


def _ler_linhas(conteudo: bytes, nome_do_arquivo: str) -> dict:
    """Lê o arquivo e confere o que vale para ele inteiro: formato, cabeçalho e se tem linhas.

    Recebe: os bytes e o nome do arquivo.
    Devolve: {"divergencia": a divergência do arquivo inteiro, ou None; "linhas": [(número da linha, [células])]}.
    As linhas em branco são puladas (sem contar como conta). Com a divergência do arquivo, nenhuma linha é conferida.
    Exemplo: um .xlsx → {"divergencia": {"tipo": "formato_do_arquivo", "linha": 0, ...}, "linhas": []}.
    """
    # A extensão do nome, em minúsculas (".CSV" vira ".csv")
    extensao = Path(nome_do_arquivo).suffix.lower()
    if extensao != EXTENSAO_DO_ARQUIVO:
        nome_do_formato = extensao if extensao else "sem extensão"
        motivo = "o arquivo veio como " + nome_do_formato + "; só é aceito .csv separado por \";\""
        return {"divergencia": _divergencia(0, "", "formato_do_arquivo", motivo), "linhas": []}
    # Nenhum byte: não há nem o cabeçalho
    if not conteudo:
        return {"divergencia": _divergencia(0, "", "arquivo_vazio", "o arquivo está vazio"), "linhas": []}
    texto = _texto_do_arquivo(conteudo)
    if texto is None:
        motivo = "o conteúdo não é texto: pode ser um Excel ou PDF com o nome trocado para .csv"
        return {"divergencia": _divergencia(0, "", "formato_do_arquivo", motivo), "linhas": []}
    # O leitor de CSV do Python separa as colunas pelo ";" e respeita as aspas
    leitor = csv.reader(io.StringIO(texto), delimiter=SEPARADOR_DE_COLUNAS)
    linhas_lidas = []
    try:
        for celulas in leitor:
            # line_num é a linha do arquivo em que o leitor está (a 1ª é o cabeçalho, como no Excel)
            linhas_lidas.append((leitor.line_num, celulas))
    except csv.Error:
        # Uma aspa aberta e nunca fechada: o resto do arquivo virou uma célula só
        motivo = "o texto do arquivo tem uma aspa (\") aberta que não foi fechada"
        return {"divergencia": _divergencia(0, "", "formato_do_arquivo", motivo), "linhas": []}
    # As linhas que têm alguma coisa (as em branco não contam)
    linhas_com_conteudo = []
    for numero_da_linha, celulas in linhas_lidas:
        if not _linha_esta_em_branco(celulas):
            linhas_com_conteudo.append((numero_da_linha, celulas))
    if not linhas_com_conteudo:
        return {"divergencia": _divergencia(0, "", "arquivo_vazio", "o arquivo não tem nenhuma linha"), "linhas": []}
    # A primeira linha com conteúdo é o cabeçalho; espaços em volta de cada nome são tirados
    numero_do_cabecalho, celulas_do_cabecalho = linhas_com_conteudo[0]
    nomes_limpos = []
    for nome in celulas_do_cabecalho:
        nomes_limpos.append(nome.strip())
    cabecalho_recebido = SEPARADOR_DE_COLUNAS.join(nomes_limpos)
    linhas_de_dados = linhas_com_conteudo[1:]
    if cabecalho_recebido != CABECALHO_ESPERADO:
        motivo = "veio \"" + cabecalho_recebido[:200] + "\"; o esperado é \"" + CABECALHO_ESPERADO + "\""
        # Um arquivo do layout antigo (com o CNPJ, a conta e a situação) ou sem uma coluna: diz o que falta e sobra
        motivo = motivo + _diferencas_do_cabecalho(nomes_limpos)
        return {"divergencia": _divergencia(numero_do_cabecalho, "", "cabecalho", motivo), "linhas": linhas_de_dados}
    if not linhas_de_dados:
        motivo = "o arquivo só tem o cabeçalho, sem nenhuma linha de conta"
        return {"divergencia": _divergencia(numero_do_cabecalho, "", "arquivo_vazio", motivo), "linhas": []}
    return {"divergencia": None, "linhas": linhas_de_dados}


# ============================== 5. Conferência de cada linha sozinha ==============================

def _data_certa(texto: str) -> str | None:
    """Confere a data de abertura (já no molde AAAA-MM-DD). Devolve None se está certa, ou o motivo do erro.

    Exemplo: "2026-02-31" → "a data 2026-02-31 não existe no calendário"; uma data de amanhã → "... é futura".
    """
    try:
        data = datetime.strptime(texto, FORMATO_DA_DATA_NO_ARQUIVO).date()
    except ValueError:
        return "a data " + texto + " não existe no calendário"
    if data > date.today():
        return "a data " + texto + " é futura: a conta salário ainda não pode ter sido aberta"
    return None


def _data_para_gravar(texto: str) -> str:
    """A data de abertura do arquivo (AAAA-MM-DD) no jeito em que a tabela guarda as datas das contas (DD/MM/AAAA).

    Recebe: a data já conferida. Devolve: a data no outro formato. Exemplo: "2026-09-29" → "29/09/2026".
    Por quê: as contas gravadas antes do ADR-149 estão como DD/MM/AAAA, e as telas e os downloads já as mostram assim.
    """
    return datetime.strptime(texto, FORMATO_DA_DATA_NO_ARQUIVO).strftime(FORMATO_DA_DATA_GRAVADA)


def _conferir_colunas_da_linha(registro: dict) -> list[dict]:
    """Confere as 5 colunas de uma linha: nenhuma vazia e cada uma no formato.

    Recebe: registro ({linha, cpf, status, agencia, conta, data_abertura, colunas_certas}); as colunas que passam
    entram em registro["colunas_certas"] (as outras conferências só usam as colunas certas).
    Devolve: as divergências da linha (uma por problema; as colunas vazias numa divergência só).
    Exemplo: {"cpf": "52998224725", "status": "3", ...} → [divergência "status_invalido"].
    """
    divergencias = []
    colunas_vazias = []
    for coluna in COLUNAS_DO_ARQUIVO:
        nome = coluna["nome"]
        valor = registro[nome]
        # O status vazio tem a conferência dele, que diz os dois códigos que valem
        if not valor and nome == "status":
            motivo = "Status: veio vazio; informe 1 (Conta nova) ou 2 (Já era correntista)"
            divergencias.append(_divergencia(registro["linha"], registro["cpf"], "status_invalido", motivo))
            continue
        # Coluna vazia: anota para uma divergência só, com todas as vazias da linha
        if not valor:
            colunas_vazias.append(coluna["titulo"])
            continue
        # Fora do molde (ex.: agência com 3 dígitos, ou a data como DD/MM/AAAA)
        if not MOLDE_DA_COLUNA[nome].fullmatch(valor):
            motivo = coluna["titulo"] + ": veio \"" + valor[:40] + "\"; o formato é " + coluna["formato"]
            divergencias.append(_divergencia(registro["linha"], registro["cpf"], TIPO_DO_FORMATO_ERRADO[nome], motivo))
            continue
        # O CPF no molde ainda precisa passar na conta dos dígitos verificadores
        if nome == "cpf" and not cpf_valido(valor):
            motivo = ("o CPF " + acompanhamento.formatar_cpf(valor) +
                      " não passa na conferência dos dígitos verificadores")
            divergencias.append(_divergencia(registro["linha"], valor, "cpf_invalido", motivo))
            continue
        # A data no molde ainda precisa existir e não ser futura
        if nome == "data_abertura":
            motivo_da_data = _data_certa(valor)
            if motivo_da_data:
                divergencias.append(_divergencia(registro["linha"], registro["cpf"], "data_invalida", motivo_da_data))
                continue
        registro["colunas_certas"].add(nome)
    if colunas_vazias:
        motivo = "vazia: " + ", ".join(colunas_vazias)
        divergencias.append(_divergencia(registro["linha"], registro["cpf"], "campo_vazio", motivo))
    return divergencias


def _registros_das_linhas(linhas_de_dados: list) -> dict:
    """Separa as colunas de cada linha e confere a quantidade de colunas e o formato de cada uma.

    Recebe: [(número da linha, [células])]. Devolve: {"registros": [um dicionário por linha com as 5 colunas],
    "divergencias": [...]}. Linha sem as 5 colunas não vira registro (não dá para saber o que é cada valor).
    """
    registros = []
    divergencias = []
    for numero_da_linha, celulas in linhas_de_dados:
        if len(celulas) != QUANTIDADE_DE_COLUNAS:
            motivo = "a linha tem " + str(len(celulas)) + " colunas; o layout tem " + str(QUANTIDADE_DE_COLUNAS)
            # O CPF é o 1º valor da linha: só ajuda a achar a linha
            valor_do_cpf = ""
            if len(celulas) > POSICAO_DO_CPF:
                valor_do_cpf = celulas[POSICAO_DO_CPF].strip()
            divergencias.append(_divergencia(numero_da_linha, valor_do_cpf[:20], "quantidade_de_colunas", motivo))
            continue
        # Cada valor pelo nome da coluna, sem os espaços em volta
        registro = {"linha": numero_da_linha, "colunas_certas": set()}
        for posicao, coluna in enumerate(COLUNAS_DO_ARQUIVO):
            registro[coluna["nome"]] = celulas[posicao].strip()
        divergencias.extend(_conferir_colunas_da_linha(registro))
        registros.append(registro)
    return {"registros": registros, "divergencias": divergencias}


def _conta_esta_certa(registro: dict) -> bool:
    """True se a agência e a conta da linha passaram no formato (só assim dá para comparar a conta)."""
    for nome in COLUNAS_DA_CONTA:
        if nome not in registro["colunas_certas"]:
            return False
    return True


def _chave_da_conta(registro: dict) -> tuple:
    """A conta da linha como uma chave só: (agência, conta). Ex.: ("0123", "45678-9")."""
    return (registro["agencia"], registro["conta"])


def _cpfs_repetidos(registros: list[dict]) -> list[dict]:
    """O mesmo CPF em mais de uma linha: todas as ocorrências viram divergência.

    Só entram as linhas com o CPF certo (um CPF inválido já tem a sua divergência).
    """
    # As linhas de cada CPF: {cpf: [3, 8]}
    linhas_por_cpf = {}
    for registro in registros:
        if "cpf" not in registro["colunas_certas"]:
            continue
        if registro["cpf"] not in linhas_por_cpf:
            linhas_por_cpf[registro["cpf"]] = []
        linhas_por_cpf[registro["cpf"]].append(registro["linha"])
    divergencias = []
    for cpf, linhas in linhas_por_cpf.items():
        if len(linhas) < 2:
            continue
        # Os números das linhas em que o CPF aparece, para o motivo ("linhas 3, 8")
        linhas_em_texto = []
        for linha in linhas:
            linhas_em_texto.append(str(linha))
        for linha in linhas:
            motivo = "o CPF aparece nas linhas " + ", ".join(linhas_em_texto)
            divergencias.append(_divergencia(linha, cpf, "cpf_repetido_no_arquivo", motivo))
    return divergencias


def _contas_repetidas(registros: list[dict]) -> list[dict]:
    """A mesma conta (agência e número) em CPFs diferentes: todas essas linhas viram divergência.

    O mesmo CPF repetido com a mesma conta já é "CPF repetido"; aqui só conta quando os CPFs são diferentes.
    """
    # As linhas de cada conta: {(agência, conta): [registro, ...]}
    registros_por_conta = {}
    for registro in registros:
        if not _conta_esta_certa(registro):
            continue
        chave_da_conta = _chave_da_conta(registro)
        if chave_da_conta not in registros_por_conta:
            registros_por_conta[chave_da_conta] = []
        registros_por_conta[chave_da_conta].append(registro)
    divergencias = []
    for chave_da_conta, registros_da_conta in registros_por_conta.items():
        # Os CPFs diferentes que trazem esta conta
        cpfs_da_conta = set()
        for registro in registros_da_conta:
            cpfs_da_conta.add(registro["cpf"])
        if len(cpfs_da_conta) < 2:
            continue
        for registro in registros_da_conta:
            motivo = "a " + _texto_da_conta(chave_da_conta) + " aparece para " + str(len(cpfs_da_conta)) + " CPFs"
            divergencias.append(_divergencia(registro["linha"], registro["cpf"], "conta_repetida_no_arquivo", motivo))
    return divergencias


# ============================== 6. Conferência contra a carteira da empresa ==============================

def _empresas_de_cada_cpf(conexao) -> dict:
    """As empresas em que cada CPF está na situação Cadastrado (tabela funcionarios_homologados).

    Recebe: conexao. Devolve: {cpf só com dígitos: [empresa_id, ...]}. Um CPF pode estar em duas empresas.
    """
    # Garante que a tabela existe (numa aplicação nova, ninguém foi cadastrado ainda)
    processamentos._preparar(conexao)
    empresas_por_cpf = {}
    for cpf, empresa_id in conexao.execute("SELECT cpf, empresa_id FROM funcionarios_homologados"):
        cpf_so_digitos = _somente_digitos(cpf)
        # Primeira empresa deste CPF: começa a lista
        if cpf_so_digitos not in empresas_por_cpf:
            empresas_por_cpf[cpf_so_digitos] = []
        empresas_por_cpf[cpf_so_digitos].append(empresa_id)
    return empresas_por_cpf


def _cpf_cadastrado_na_empresa(cpf: str, empresa_id: str, empresas_por_cpf: dict) -> bool:
    """True se o CPF está na situação Cadastrado nesta empresa. Ex.: ("529...", "EMP001", {"529...": ["EMP001"]})."""
    return empresa_id in empresas_por_cpf.get(cpf, [])


def _contas_gravadas(conexao) -> dict:
    """As contas que já têm baixa, vistas dos dois lados.

    Devolve: {"por_empresa_e_cpf": {(empresa_id, cpf): (agência, conta)},
              "tipo_por_empresa_e_cpf": {(empresa_id, cpf): tipo_conta},
              "cpfs_por_conta": {(agência, conta): {cpf, ...}}}.
    O tipo é None nas baixas de arquivos antigos, de antes dessa coluna. A conta é comparada pela agência e pelo
    número: o código do banco saiu do arquivo (ADR-149), e as contas antigas, que o tinham, continuam as mesmas.
    """
    por_empresa_e_cpf = {}
    tipo_por_empresa_e_cpf = {}
    cpfs_por_conta = {}
    for empresa_id, cpf, agencia, conta, tipo_conta in conexao.execute(
            "SELECT empresa_id, cpf, agencia, conta, tipo_conta FROM contas_abertas"):
        chave_da_conta = (agencia, conta)
        # A conta gravada deste CPF nesta empresa, e o tipo gravado com ela
        por_empresa_e_cpf[(empresa_id, cpf)] = chave_da_conta
        tipo_por_empresa_e_cpf[(empresa_id, cpf)] = tipo_conta
        # E, do outro lado, os CPFs que têm esta conta (normalmente um só)
        if chave_da_conta not in cpfs_por_conta:
            cpfs_por_conta[chave_da_conta] = set()
        cpfs_por_conta[chave_da_conta].add(cpf)
    return {"por_empresa_e_cpf": por_empresa_e_cpf, "tipo_por_empresa_e_cpf": tipo_por_empresa_e_cpf,
            "cpfs_por_conta": cpfs_por_conta}


def _nomes_das_outras_empresas(cpf: str, empresa_id: str, empresas_por_cpf: dict) -> list[str]:
    """Os nomes das OUTRAS empresas em que o CPF está Cadastrado (vazio se nenhuma). Ex.: ["Horizonte Logística"]."""
    nomes = []
    for outra_empresa_id in empresas_por_cpf.get(cpf, []):
        if outra_empresa_id != empresa_id:
            nomes.append(dados_mock.nome_da_empresa(outra_empresa_id))
    return nomes


def _onde_esta_cada_cpf_fora_do_cadastro(conexao, cpfs_procurados: set, empresa_id: str,
                                         empresas_por_cpf: dict) -> dict:
    """Por que cada CPF ainda não está Cadastrado nesta empresa: em análise no banco, ainda com a empresa, Cadastrado
    em outra empresa ou nunca enviado por ela.

    Recebe: conexao; os CPFs (só dígitos) que não estão Cadastrados nesta empresa; empresa_id; {cpf: [empresa_id]}.
    Devolve: {cpf: motivo}. Exemplo: {"52998224725": "está Cadastrado em outra empresa (Horizonte Logística), não
    nesta: a linha vai no arquivo dessa empresa"}.
    A busca olha só os envios desta empresa (a mesma consulta da lista de funcionários), e só roda quando há algum CPF
    procurado. Vale o mais adiantado nesta empresa (em análise, depois com a empresa); depois, outra empresa.
    """
    motivos = {}
    if not cpfs_procurados:
        return motivos
    nome_da_empresa = dados_mock.nome_da_empresa(empresa_id)
    em_analise = {}
    com_a_empresa = {}
    for pessoa in acompanhamento.todos_os_funcionarios_da_empresa(conexao, empresa_id):
        cpf = _somente_digitos(pessoa["cpf"])
        if cpf not in cpfs_procurados:
            continue
        # Envio mandado ao banco, esperando a avaliação
        if pessoa["situacao"] == acompanhamento.SITUACAO_EM_ANALISE and cpf not in em_analise:
            em_analise[cpf] = "ainda em análise no banco (" + nome_da_empresa + ")"
        # Envio ainda com a empresa: com pendência (Pendente) ou esperando ser mandado (Aguardando envio)
        situacoes_com_a_empresa = (acompanhamento.SITUACAO_PENDENTE, acompanhamento.SITUACAO_AGUARDANDO_ENVIO)
        if pessoa["situacao"] in situacoes_com_a_empresa and cpf not in com_a_empresa:
            com_a_empresa[cpf] = ("ainda com a empresa, na situação " + pessoa["situacao"] + " (" +
                                  nome_da_empresa + ")")
    for cpf in cpfs_procurados:
        outras_empresas = _nomes_das_outras_empresas(cpf, empresa_id, empresas_por_cpf)
        # O mais adiantado nesta empresa primeiro: em análise; depois com a empresa
        if cpf in em_analise:
            motivos[cpf] = em_analise[cpf]
        elif cpf in com_a_empresa:
            motivos[cpf] = com_a_empresa[cpf]
        # Cadastrado, mas em outra empresa: a linha é do arquivo dessa outra empresa
        elif outras_empresas:
            motivos[cpf] = ("está Cadastrado em outra empresa (" + ", ".join(outras_empresas) + "), não nesta: a "
                            "linha vai no arquivo dessa empresa")
        else:
            motivos[cpf] = MOTIVO_NUNCA_ENVIADO
    return motivos


def _cpfs_nao_cadastrados(conexao, registros: list[dict], empresas_por_cpf: dict, empresa_id: str) -> list[dict]:
    """As linhas cujo CPF (certo) não está Cadastrado nesta empresa, com o motivo de cada uma."""
    fora_do_cadastro = []
    cpfs_procurados = set()
    for registro in registros:
        if "cpf" not in registro["colunas_certas"]:
            continue
        if not _cpf_cadastrado_na_empresa(registro["cpf"], empresa_id, empresas_por_cpf):
            fora_do_cadastro.append(registro)
            cpfs_procurados.add(registro["cpf"])
    # Só procura nos envios em andamento se houver algum CPF fora do cadastro (a busca é a parte cara)
    motivos = _onde_esta_cada_cpf_fora_do_cadastro(conexao, cpfs_procurados, empresa_id, empresas_por_cpf)
    divergencias = []
    for registro in fora_do_cadastro:
        divergencias.append(_divergencia(registro["linha"], registro["cpf"], "cpf_nao_cadastrado",
                                         motivos[registro["cpf"]]))
    return divergencias


def _comparar_com_as_contas_gravadas(registros: list[dict], empresas_por_cpf: dict, contas_gravadas: dict,
                                     empresa_id: str) -> dict:
    """Compara a conta de cada linha com as contas já gravadas e separa as baixas que a linha daria nesta empresa.

    Recebe: os registros; {cpf: [empresa_id]}; as contas gravadas (_contas_gravadas); empresa_id (a do arquivo).
    Devolve: {"divergencias": [...], "avisos": [...], "baixas": [(linha, {empresa_id, cpf, data_abertura, agencia,
    conta, tipo_conta})], "completar": [(linha, {empresa_id, cpf, tipo_conta})]}. A baixa é só nesta empresa: um CPF
    Cadastrado em duas empresas ganha a baixa na outra pelo arquivo da outra. "completar" são as contas antigas,
    gravadas sem o status, que ganham o status deste arquivo.
    """
    divergencias = []
    avisos = []
    baixas = []
    completar = []
    nome_da_empresa = dados_mock.nome_da_empresa(empresa_id)
    for registro in registros:
        cpf = registro["cpf"]
        # Só compara a linha com o CPF certo, Cadastrado nesta empresa, e a conta no formato
        if "cpf" not in registro["colunas_certas"] or not _conta_esta_certa(registro):
            continue
        if not _cpf_cadastrado_na_empresa(cpf, empresa_id, empresas_por_cpf):
            continue
        chave_da_conta = _chave_da_conta(registro)
        # A conta já está gravada para outro CPF (em qualquer empresa): trava
        outros_cpfs = contas_gravadas["cpfs_por_conta"].get(chave_da_conta, set()) - {cpf}
        if outros_cpfs:
            outro_cpf = acompanhamento.formatar_cpf(sorted(outros_cpfs)[0])
            motivo = "a " + _texto_da_conta(chave_da_conta) + " já está gravada para o CPF " + outro_cpf
            divergencias.append(_divergencia(registro["linha"], cpf, "conta_de_outro_cpf", motivo))
            continue
        conta_gravada = contas_gravadas["por_empresa_e_cpf"].get((empresa_id, cpf))
        # Outra conta gravada: trava
        if conta_gravada is not None and conta_gravada != chave_da_conta:
            motivo = ("já tem outra conta salário gravada (" + _texto_da_conta(conta_gravada) + ", " + nome_da_empresa +
                      "); no arquivo veio " + _texto_da_conta(chave_da_conta))
            divergencias.append(_divergencia(registro["linha"], cpf, "conta_diferente_da_gravada", motivo))
            continue
        # Daqui em diante, o status e a data contam: sem os dois certos, a linha já tem a divergência dela
        if "status" not in registro["colunas_certas"] or "data_abertura" not in registro["colunas_certas"]:
            continue
        tipo_da_linha = TIPO_GRAVADO_POR_CODIGO[registro["status"]]
        # Ainda sem conta nesta empresa: a linha daria a baixa, com o status e a data no jeito da tabela
        if conta_gravada is None:
            data_para_gravar = _data_para_gravar(registro["data_abertura"])
            baixa = {"empresa_id": empresa_id, "cpf": cpf, "data_abertura": data_para_gravar,
                     "agencia": registro["agencia"], "conta": registro["conta"], "tipo_conta": tipo_da_linha}
            baixas.append((registro["linha"], baixa))
            continue
        # A mesma conta de antes: compara o status gravado com o da linha
        tipo_gravado = contas_gravadas["tipo_por_empresa_e_cpf"][(empresa_id, cpf)]
        resultado = _comparar_o_status_com_o_gravado(registro, tipo_da_linha, tipo_gravado, nome_da_empresa)
        if resultado["tipo"] == "status_diferente_do_gravado":
            divergencias.append(resultado)
        else:
            avisos.append(resultado)
        # Conta antiga, sem o status: o desta linha vai ser gravado nela na confirmação
        if resultado["tipo"] == "status_completado":
            completar.append((registro["linha"], {"empresa_id": empresa_id, "cpf": cpf, "tipo_conta": tipo_da_linha}))
    return {"divergencias": divergencias, "avisos": avisos, "baixas": baixas, "completar": completar}


def _texto_do_status(tipo_conta: str) -> str:
    """O status em palavras, para os motivos. Ex.: "CORRENTISTA" → "Já era correntista"; "NOVA_CONTA" → "Conta nova"."""
    if tipo_conta == TIPO_NOVA_CONTA:
        return "Conta nova"
    return "Já era correntista"


def _comparar_o_status_com_o_gravado(registro: dict, tipo_da_linha: str, tipo_gravado: str | None,
                                     nome_da_empresa: str) -> dict:
    """A linha traz a mesma conta já gravada para o CPF: compara o status da linha com o gravado.

    Recebe: registro; o status da linha como fica na tabela ("NOVA_CONTA" ou "CORRENTISTA"); o gravado (None nas
    contas antigas, de antes da coluna do tipo); o nome da empresa (para o motivo).
    Devolve: uma divergência "status_diferente_do_gravado" (o outro status: trava), ou um aviso: "status_completado"
    (a conta antiga não tinha o status) ou "ja_tinha_conta" (o mesmo status: a linha é ignorada).
    Exemplo: gravada como "NOVA_CONTA" e a linha com o status 2 → divergência "status_diferente_do_gravado".
    """
    linha = registro["linha"]
    cpf = registro["cpf"]
    texto_da_linha = _texto_do_status(tipo_da_linha)
    # Conta de um arquivo antigo, sem o status: o que veio nesta linha passa a valer (nada foi suposto antes)
    if tipo_gravado is None:
        motivo = ("já tinha esta mesma conta salário, gravada sem o status por um arquivo antigo (" + nome_da_empresa +
                  "); passa a valer: " + texto_da_linha)
        return _divergencia(linha, cpf, "status_completado", motivo)
    # O mesmo status: só um aviso, a linha é ignorada
    if tipo_gravado == tipo_da_linha:
        motivo = "já tinha esta mesma conta salário (" + nome_da_empresa + "); a linha é ignorada"
        return _divergencia(linha, cpf, "ja_tinha_conta", motivo)
    # O outro status: trava
    motivo = ("a conta salário já está gravada como " + _texto_do_status(tipo_gravado) + " (" + nome_da_empresa +
              "); no arquivo veio " + texto_da_linha)
    return _divergencia(linha, cpf, "status_diferente_do_gravado", motivo)


def _numero_da_linha(divergencia: dict) -> int:
    """A linha de uma divergência (para ordenar a lista na ordem do arquivo)."""
    return divergencia["linha"]


def _conferir_conteudo(conexao, conteudo: bytes, nome_do_arquivo: str, empresa: dict) -> dict:
    """Faz todas as conferências do arquivo, na ordem: arquivo inteiro, cada linha e a carteira da empresa.

    Recebe: conexao; os bytes e o nome do arquivo; a empresa escolhida (empresa_do_arquivo: {empresa_id, nome}).
    Devolve: {linhas (de dados), divergencias (em ordem de linha), avisos, baixas: [{empresa_id, cpf, data_abertura,
    agencia, conta, tipo_conta}], completar: [{empresa_id, cpf, tipo_conta}] — baixas e completar só das linhas sem
    nenhuma divergência}.
    """
    leitura = _ler_linhas(conteudo, nome_do_arquivo)
    # Erro do arquivo inteiro: nenhuma linha é conferida
    if leitura["divergencia"] is not None:
        return {"linhas": len(leitura["linhas"]), "divergencias": [leitura["divergencia"]], "avisos": [], "baixas": [],
                "completar": []}
    # Cada linha sozinha: quantidade de colunas, vazias e formato
    conferencia_das_linhas = _registros_das_linhas(leitura["linhas"])
    registros = conferencia_das_linhas["registros"]
    divergencias = list(conferencia_das_linhas["divergencias"])
    # As repetições dentro do próprio arquivo
    divergencias.extend(_cpfs_repetidos(registros))
    divergencias.extend(_contas_repetidas(registros))
    # A carteira desta empresa (a da tela): quem está Cadastrado nela e as contas já gravadas
    empresas_por_cpf = _empresas_de_cada_cpf(conexao)
    divergencias.extend(_cpfs_nao_cadastrados(conexao, registros, empresas_por_cpf, empresa["empresa_id"]))
    comparacao = _comparar_com_as_contas_gravadas(registros, empresas_por_cpf, _contas_gravadas(conexao),
                                                  empresa["empresa_id"])
    divergencias.extend(comparacao["divergencias"])
    # As linhas com alguma divergência não dão baixa
    linhas_com_divergencia = set()
    for divergencia in divergencias:
        linhas_com_divergencia.add(divergencia["linha"])
    baixas = []
    for linha, baixa in comparacao["baixas"]:
        if linha not in linhas_com_divergencia:
            baixas.append(baixa)
    # As contas antigas que ganham o tipo, também só das linhas sem divergência
    completar = []
    for linha, conta_para_completar in comparacao["completar"]:
        if linha not in linhas_com_divergencia:
            completar.append(conta_para_completar)
    # Na ordem do arquivo ("sorted" mantém a ordem das conferências dentro da mesma linha)
    divergencias = sorted(divergencias, key=_numero_da_linha)
    avisos = sorted(comparacao["avisos"], key=_numero_da_linha)
    return {"linhas": len(leitura["linhas"]), "divergencias": divergencias, "avisos": avisos, "baixas": baixas,
            "completar": completar}


def _divergencias_por_tipo(divergencias: list[dict]) -> list[dict]:
    """Quantas divergências de cada tipo, na ordem de VALIDACOES (só os tipos que apareceram).

    Exemplo: [{"tipo": "cpf_nao_cadastrado", "titulo": "CPF que não está Cadastrado", "quantidade": 2}].
    """
    quantidade_por_tipo = {}
    for divergencia in divergencias:
        quantidade_por_tipo[divergencia["tipo"]] = quantidade_por_tipo.get(divergencia["tipo"], 0) + 1
    contagem = []
    for validacao in VALIDACOES:
        if validacao["tipo"] in quantidade_por_tipo:
            contagem.append({"tipo": validacao["tipo"], "titulo": validacao["titulo"],
                             "quantidade": quantidade_por_tipo[validacao["tipo"]]})
    return contagem


# ============================== 7. Números das contas (usados pelas telas) ==============================

# O que a EMPRESA vê na situação de cada funcionário, pelo tipo que o banco informou: a conta
# nova e o correntista aparecem diferentes.
SITUACAO_NA_EMPRESA_DO_TIPO = {TIPO_NOVA_CONTA: "Conta aberta", TIPO_CORRENTISTA: "Já é correntista"}


def _cpfs_cadastrados(conexao, empresa_id: str) -> set:
    """Os CPFs (só com os dígitos) dos funcionários Cadastrados da empresa, sem repetir.

    Recebe: conexao; empresa_id. Devolve: {"52998224725", ...}. Lê a tabela dos homologados, sem montar a lista inteira
    de funcionários (conta barata: a carteira do banco chama isto para cada empresa).
    """
    processamentos._preparar(conexao)
    cpfs = set()
    for (cpf,) in conexao.execute("SELECT cpf FROM funcionarios_homologados WHERE empresa_id = ?", (empresa_id,)):
        cpfs.add(_somente_digitos(cpf))
    return cpfs


def retorno_da_empresa(conexao, empresa_id: str) -> dict:
    """A CONTA ÚNICA do retorno do banco de uma empresa: todas as telas que mostram contas usam estes números.

    Recebe: conexao; empresa_id. Devolve: {cadastrados, aguardando_retorno, contas_abertas (tipo 1), ja_correntistas
    (tipo 2), com_conta (as duas), percentual (com_conta de cadastrados, 0 a 100, sem casas), arquivo_recebido}.
    A classificação de cada Cadastrado é a MESMA do painel de Indicadores (services/planejamento.py, classificar): o
    banco sempre informa o tipo; quem não veio no arquivo (ou veio numa conta gravada antes da coluna do tipo) aguarda.
    Usam esta conta: o Início e o Acompanhar da empresa, a linha do tempo do envio, o Início, a carteira e a Visão
    geral do banco, a prévia do arquivo e a sugestão do Endomarketing. Um teste garante que ela bate com o painel.
    Exemplo: 35 cadastrados, 20 contas novas e 5 correntistas → {"com_conta": 25, "aguardando_retorno": 10,
    "percentual": 71, ...}. arquivo_recebido: algum arquivo de contas DESTA empresa já foi confirmado (um arquivo
    antigo, de antes do ADR-122, não tem empresa e valia para a carteira toda: conta para todas).
    """
    # Importado aqui dentro: services/planejamento.py também usa este arquivo (importar lá em cima faria um laço)
    from services import planejamento
    _preparar(conexao)
    cadastrados = _cpfs_cadastrados(conexao, empresa_id)
    retornos = retorno_por_cpf(conexao, [empresa_id])
    numeros = {"cadastrados": len(cadastrados), "aguardando_retorno": 0, "contas_abertas": 0, "ja_correntistas": 0}
    # Cada Cadastrado, com a mesma classificação do painel de Indicadores
    for cpf in cadastrados:
        classificacao = planejamento.classificar(retornos.get(cpf))
        if classificacao == planejamento.CONTA_ABERTA:
            numeros["contas_abertas"] = numeros["contas_abertas"] + 1
        elif classificacao == planejamento.CORRENTISTA_MARCADO:
            numeros["ja_correntistas"] = numeros["ja_correntistas"] + 1
        else:
            numeros["aguardando_retorno"] = numeros["aguardando_retorno"] + 1
    numeros["com_conta"] = numeros["contas_abertas"] + numeros["ja_correntistas"]
    numeros["percentual"] = 0
    if numeros["cadastrados"]:
        numeros["percentual"] = round(100 * numeros["com_conta"] / numeros["cadastrados"])
    # Os arquivos confirmados desta empresa (ou os antigos, sem empresa, que valiam para todas)
    recebido = conexao.execute("SELECT COUNT(*) FROM arquivos_de_contas WHERE situacao = ? "
                               "AND (empresa_id = ? OR empresa_id IS NULL)", (CONFIRMADO, empresa_id)).fetchone()[0]
    numeros["arquivo_recebido"] = recebido > 0
    return numeros


def numeros_de_contas(conexao, empresa_id: str) -> dict:
    """Quantos cadastrados da empresa já têm conta no banco (conta nova ou correntista), pela conta única.

    Recebe: conexao; empresa_id. Devolve: {cadastrados, com_conta, contas_abertas, ja_correntistas, percentual (0 a
    100, sem casas), arquivo_recebido}, os mesmos números de retorno_da_empresa.
    """
    numeros = retorno_da_empresa(conexao, empresa_id)
    return {"cadastrados": numeros["cadastrados"], "com_conta": numeros["com_conta"],
            "contas_abertas": numeros["contas_abertas"], "ja_correntistas": numeros["ja_correntistas"],
            "percentual": numeros["percentual"], "arquivo_recebido": numeros["arquivo_recebido"]}


def contagem_dos_tipos(contas: list[dict]) -> dict:
    """Quantas contas são de cada tipo: novas contas e correntistas (o correntista é um grupo só, ADR-149).

    Recebe: as contas ({tipo_conta, ...}, como as baixas da prévia). Devolve: {nova_conta, correntista}.
    Exemplo: [NOVA_CONTA, CORRENTISTA, CORRENTISTA] → {"nova_conta": 1, "correntista": 2}.
    """
    contagem = {"nova_conta": 0, "correntista": 0}
    for conta in contas:
        # .get: uma prévia guardada antes do tipo de conta não tem esta chave (não conta em nenhum tipo)
        tipo_conta = conta.get("tipo_conta")
        if tipo_conta == TIPO_NOVA_CONTA:
            contagem["nova_conta"] = contagem["nova_conta"] + 1
        if tipo_conta == TIPO_CORRENTISTA:
            contagem["correntista"] = contagem["correntista"] + 1
    return contagem


def retorno_por_cpf(conexao, empresa_ids: list[str]) -> dict:
    """O retorno do banco de cada funcionário com conta gravada: o tipo de conta.

    SÓ PARA O BANCO (o motor de planejamento e o Portal Interno).
    Recebe: conexao; empresa_ids (as empresas que interessam; lista vazia → {}).
    Devolve: {cpf só com dígitos: {"tipo_conta": "NOVA_CONTA" | "CORRENTISTA" | None}}. None no tipo = conta gravada
    antes da coluna do tipo: o status ainda não foi dito, e a pessoa conta como aguardando (o banco sempre informa o
    tipo nos arquivos novos). O CPF que não aparece não tem retorno do banco ainda (aguardando).
    Um CPF com conta em mais de uma das empresas: vale a baixa mais recente.
    Exemplo: retorno_por_cpf(conexao, ["EMP001"]) → {"52998224725": {"tipo_conta": "CORRENTISTA"}}.
    """
    _preparar(conexao)
    retorno = {}
    for empresa_id in empresa_ids:
        # Da baixa mais antiga para a mais recente: se o CPF aparece de novo, a mais recente fica
        consulta = conexao.execute("SELECT cpf, tipo_conta, baixa_em FROM contas_abertas WHERE empresa_id = ? "
                                   "ORDER BY baixa_em", (empresa_id,))
        for cpf, tipo_conta, baixa_em in consulta:
            retorno_anterior = retorno.get(cpf)
            # Já veio de outra empresa, com uma baixa mais recente: fica a outra
            if retorno_anterior is not None and retorno_anterior["baixa_em"] > baixa_em:
                continue
            retorno[cpf] = {"tipo_conta": tipo_conta, "baixa_em": baixa_em}
    # A data da baixa só servia para escolher a mais recente: sai da resposta
    for dados_do_retorno in retorno.values():
        del dados_do_retorno["baixa_em"]
    return retorno


def contas_para_a_empresa(conexao, empresa_id: str) -> dict:
    """O total de contas abertas da empresa, para o cartão do alto da tela (a conta de cada pessoa vem na lista).

    Recebe: conexao; empresa_id (da sessão). Devolve: {arquivo_recebido, texto, percentual, com_conta, cadastrados,
    contas_abertas, ja_correntistas} (os números são None enquanto o banco não mandou nenhum arquivo). Mostra quantos
    abriram a conta agora e quantos já eram correntistas. Os números são os da conta
    única (retorno_da_empresa).
    Exemplo: 35 cadastrados, 15 contas novas e 5 correntistas → {"texto": "20 de 35 já têm conta no banco (57%): 15
    abriram a conta agora e 5 já eram correntistas", "percentual": 57}.
    """
    numeros = numeros_de_contas(conexao, empresa_id)
    if not numeros["arquivo_recebido"]:
        return {"arquivo_recebido": False, "texto": "O banco ainda não mandou o arquivo de contas abertas.",
                "percentual": None, "com_conta": None, "cadastrados": None, "contas_abertas": None,
                "ja_correntistas": None}
    # Ninguém cadastrado ainda: "0 de 0" não diz nada
    if numeros["cadastrados"] == 0:
        return {"arquivo_recebido": True, "texto": "Nenhum funcionário cadastrado ainda.",
                "percentual": None, "com_conta": None, "cadastrados": None, "contas_abertas": None,
                "ja_correntistas": None}
    texto = (str(numeros["com_conta"]) + " de " + str(numeros["cadastrados"]) + " já têm conta no banco (" +
             str(numeros["percentual"]) + "%): " + _texto_dos_tipos_para_a_empresa(numeros))
    return {"arquivo_recebido": True, "percentual": numeros["percentual"], "com_conta": numeros["com_conta"],
            "cadastrados": numeros["cadastrados"], "contas_abertas": numeros["contas_abertas"],
            "ja_correntistas": numeros["ja_correntistas"], "texto": texto}


def _texto_dos_tipos_para_a_empresa(numeros: dict) -> str:
    """Quantos abriram a conta agora e quantos já eram correntistas, com singular e plural.

    Recebe: numeros — {contas_abertas, ja_correntistas}. Devolve: ex.: "15 abriram a conta agora e 1 já era
    correntista".
    """
    # A conta nova: "1 abriu" ou "15 abriram"
    abriram = str(numeros["contas_abertas"]) + " abriram a conta agora"
    if numeros["contas_abertas"] == 1:
        abriram = "1 abriu a conta agora"
    # O correntista: "1 já era" ou "5 já eram"
    correntistas = str(numeros["ja_correntistas"]) + " já eram correntistas"
    if numeros["ja_correntistas"] == 1:
        correntistas = "1 já era correntista"
    return abriram + " e " + correntistas


def contas_da_empresa(conexao, empresa_id: str) -> dict:
    """A conta de cada funcionário que o banco informou: {cpf só com dígitos: {data_abertura, codigo_banco, agencia,
    conta, situacao_na_empresa}}.

    Recebe: conexao; empresa_id (da sessão: a empresa nunca vê a conta de funcionário de outra). É o que a empresa
    precisa para pagar o salário (ADR-102), e "situacao_na_empresa" diz, em palavras, se a conta foi aberta agora
    ("Conta aberta") ou se a pessoa já era cliente ("Já é correntista"). Só entram as contas com o tipo: uma conta
    gravada antes da coluna do tipo ainda aguarda o retorno do banco (a mesma regra do painel de Indicadores e de
    retorno_da_empresa). O código do banco saiu do arquivo (ADR-149): nas baixas novas ele vem vazio.
    Exemplo: {"52998224725": {"data_abertura": "29/09/2026", "codigo_banco": "", "agencia": "0123",
    "conta": "45678-9", "situacao_na_empresa": "Conta aberta"}}.
    """
    _preparar(conexao)
    contas = {}
    for cpf, data_abertura, agencia, conta, codigo_banco, tipo_conta in conexao.execute(
            "SELECT cpf, data_abertura, agencia, conta, codigo_banco, tipo_conta FROM contas_abertas "
            "WHERE empresa_id = ? AND tipo_conta IS NOT NULL", (empresa_id,)):
        # Baixa antiga, sem o código do banco gravado: fica vazio (nada é suposto; a tela mostra "—")
        contas[cpf] = {"data_abertura": data_abertura, "agencia": agencia, "conta": conta,
                       "codigo_banco": codigo_banco, "situacao_na_empresa": SITUACAO_NA_EMPRESA_DO_TIPO[tipo_conta]}
    return contas


def _mudanca_por_empresa(conexao, novas: list[dict]) -> list[dict]:
    """O que muda em cada empresa com as contas novas: antes, novas e depois.

    Recebe: conexao; as contas novas da prévia. Devolve: [{empresa, cadastrados, antes, novas, depois}], só das
    empresas com alguma conta nova, e a linha "Carteira" no fim.
    """
    novas_por_empresa = {}
    for conta in novas:
        novas_por_empresa[conta["empresa_id"]] = novas_por_empresa.get(conta["empresa_id"], 0) + 1
    linhas = []
    total = {"empresa": "Carteira", "cadastrados": 0, "antes": 0, "novas": 0, "depois": 0}
    for empresa in dados_mock.empresas():
        empresa_id = empresa["empresa_id"]
        if empresa_id not in novas_por_empresa:
            continue
        numeros = numeros_de_contas(conexao, empresa_id)
        linha = {"empresa": empresa["nome"], "cadastrados": numeros["cadastrados"], "antes": numeros["com_conta"],
                 "novas": novas_por_empresa[empresa_id], "depois": numeros["com_conta"] + novas_por_empresa[empresa_id]}
        linhas.append(linha)
        for chave in ("cadastrados", "antes", "novas", "depois"):
            total[chave] = total[chave] + linha[chave]
    if linhas:
        linhas.append(total)
    return linhas


# ============================== 8. Prévia, confirmação, descarte e histórico ==============================

def conferir_arquivo(conexao, usuario, empresa_id: str, conteudo: bytes, nome_do_arquivo: str) -> dict:
    """Confere o arquivo de contas abertas de UMA empresa e devolve a PRÉVIA da baixa (nada é gravado nas contas ainda).

    Recebe: conexao; usuario (só o BANCO); empresa_id (a empresa aberta na ficha: o arquivo tem de ser dela);
    conteudo e nome do arquivo (.csv no layout fixo). Levanta KeyError se a empresa não existe.
    Devolve: {arquivo_id (None se recusado), nome_arquivo, empresa: {empresa_id, nome}, linhas, pode_importar,
    divergencias, divergencias_por_tipo, novas, tipos_das_novas: {nova_conta, correntista}, completadas (contas
    antigas que ganham o tipo), avisos, por_empresa}. Nunca levanta erro por causa do conteúdo: todo problema vira
    divergência. Sem divergência, a prévia fica PENDENTE (com as baixas, para a confirmação); com divergência, o
    arquivo fica registrado como RECUSADO, sem nenhum CPF, e não há nada a confirmar.
    """
    autorizar(usuario, "dar_baixa_em_contas")
    _preparar(conexao)
    # A empresa escolhida, com os CNPJs que valem no arquivo (KeyError se ela não existe)
    empresa = empresa_do_arquivo(conexao, empresa_id)
    conferencia = _conferir_conteudo(conexao, conteudo, nome_do_arquivo, empresa)
    divergencias_por_tipo = _divergencias_por_tipo(conferencia["divergencias"])
    pode_importar = len(conferencia["divergencias"]) == 0
    arquivo_id = uuid.uuid4().hex[:10]
    if pode_importar:
        # A prévia guarda as baixas e as contas antigas que ganham o tipo (com os CPFs) para a confirmação
        situacao = PENDENTE
        resultado = {"novas": conferencia["baixas"], "completar": conferencia["completar"],
                     "linhas": conferencia["linhas"], "avisos": len(conferencia["avisos"])}
    else:
        # Recusado: só as contagens, sem nenhum CPF (o arquivo precisa ser corrigido e subido de novo)
        situacao = RECUSADO
        resultado = {"novas": 0, "linhas": conferencia["linhas"], "divergencias_por_tipo": divergencias_por_tipo}
    # O registro do arquivo guarda a empresa para a qual ele foi subido (o histórico é por empresa)
    conexao.execute("INSERT INTO arquivos_de_contas (arquivo_id, nome_arquivo, enviado_por, enviado_em, situacao, "
                    "resultado, empresa_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (arquivo_id, nome_do_arquivo[:200], usuario.login, _agora(), situacao,
                     json.dumps(resultado, ensure_ascii=False), empresa["empresa_id"]))
    conexao.commit()
    # Recusado: a tela não recebe o identificador (não há o que confirmar)
    arquivo_id_da_previa = arquivo_id if pode_importar else None
    return {"arquivo_id": arquivo_id_da_previa, "nome_arquivo": nome_do_arquivo, "empresa": empresa,
            "linhas": conferencia["linhas"], "pode_importar": pode_importar,
            "divergencias": conferencia["divergencias"][:LIMITE_DE_ITENS_NA_PREVIA],
            "divergencias_por_tipo": divergencias_por_tipo, "novas": len(conferencia["baixas"]),
            "tipos_das_novas": contagem_dos_tipos(conferencia["baixas"]),
            "completadas": len(conferencia["completar"]),
            "avisos": conferencia["avisos"][:LIMITE_DE_ITENS_NA_PREVIA],
            "por_empresa": _mudanca_por_empresa(conexao, conferencia["baixas"])}


def _arquivo_pendente(conexao, arquivo_id: str) -> dict:
    """O arquivo ainda PENDENTE: o resultado guardado e a empresa dele.

    Devolve: {"resultado": o resultado guardado (com as baixas), "empresa_id": a empresa do arquivo (None nos antigos)}.
    Levanta KeyError (não existe) ou ValueError (recusado na conferência, ou já confirmado ou descartado).
    """
    linha = conexao.execute("SELECT situacao, resultado, empresa_id FROM arquivos_de_contas WHERE arquivo_id = ?",
                            (arquivo_id,)).fetchone()
    if linha is None:
        raise KeyError(arquivo_id)
    if linha[0] == RECUSADO:
        raise ValueError("Este arquivo foi recusado na conferência: corrija o arquivo e suba de novo.")
    if linha[0] != PENDENTE:
        raise ValueError("Este arquivo já foi confirmado ou descartado.")
    return {"resultado": json.loads(linha[1]), "empresa_id": linha[2]}


def _contas_da_empresa_em_numeros(conexao, empresa_id: str | None) -> dict | None:
    """As contas abertas da empresa depois da baixa, para o histórico: {com_conta, cadastrados, percentual}.

    Recebe: conexao; empresa_id (None num arquivo antigo, sem empresa: aí não há o que mostrar e volta None).
    """
    if empresa_id is None:
        return None
    numeros = numeros_de_contas(conexao, empresa_id)
    return {"com_conta": numeros["com_conta"], "cadastrados": numeros["cadastrados"],
            "percentual": numeros["percentual"]}


def confirmar_baixa(conexao, usuario, arquivo_id: str) -> dict:
    """Dá baixa nas contas novas da prévia: cada uma entra em contas_abertas, com o arquivo e a data da baixa.

    Recebe: conexao; usuario (só o BANCO); arquivo_id (da prévia: ela já sabe a empresa).
    Devolve: {novas, tipos_das_novas, completadas, por_empresa}.
    Conta que ganhou baixa entre a prévia e a confirmação (outro arquivo) não é gravada de novo. As contas antigas,
    gravadas sem o status, ganham o que veio no arquivo (só se ainda estiverem sem).
    O código do banco saiu do arquivo (ADR-149): na baixa nova ele fica vazio; a situação do correntista e a folha já
    identificada ficam sem valor (colunas sem uso desde então).
    """
    autorizar(usuario, "dar_baixa_em_contas")
    _preparar(conexao)
    pendente = _arquivo_pendente(conexao, arquivo_id)
    classificacao = pendente["resultado"]
    por_empresa = _mudanca_por_empresa(conexao, classificacao["novas"])
    agora = _agora()
    for conta in classificacao["novas"]:
        # "ON CONFLICT DO NOTHING": se a conta já ganhou baixa por outro arquivo, fica a primeira.
        # .get: uma prévia guardada antes do tipo de conta não tem o tipo (fica sem, como um arquivo antigo); uma
        # prévia guardada antes do ADR-149 ainda traz o código do banco
        conexao.execute("INSERT INTO contas_abertas (empresa_id, cpf, data_abertura, agencia, conta, codigo_banco, "
                        "arquivo_id, baixa_em, tipo_conta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        (conta["empresa_id"], conta["cpf"], conta["data_abertura"], conta["agencia"], conta["conta"],
                         conta.get("codigo_banco", ""), arquivo_id, agora, conta.get("tipo_conta")))
    # As contas antigas, sem o status, ganham o que veio neste arquivo
    completar = classificacao.get("completar", [])
    for conta in completar:
        # Só a conta ainda sem o tipo: se outro arquivo já completou nesse meio-tempo, fica o que ele gravou
        conexao.execute("UPDATE contas_abertas SET tipo_conta = ? WHERE empresa_id = ? AND cpf = ? "
                        "AND tipo_conta IS NULL", (conta["tipo_conta"], conta["empresa_id"], conta["cpf"]))
    tipos_das_novas = contagem_dos_tipos(classificacao["novas"])
    # Guarda só as contagens no histórico (os CPFs das contas já estão na tabela de contas), com as contas da empresa
    # depois da baixa (a chave continua "carteira_depois": é a carteira de contas DESTA empresa)
    resumo = {"novas": len(classificacao["novas"]), "tipos_das_novas": tipos_das_novas,
              "completadas": len(completar), "avisos": classificacao.get("avisos", 0),
              "linhas": classificacao.get("linhas", 0),
              "carteira_depois": _contas_da_empresa_em_numeros(conexao, pendente["empresa_id"])}
    conexao.execute("UPDATE arquivos_de_contas SET situacao = ?, resultado = ?, decidido_em = ? WHERE arquivo_id = ?",
                    (CONFIRMADO, json.dumps(resumo, ensure_ascii=False), agora, arquivo_id))
    conexao.commit()
    return {"novas": len(classificacao["novas"]), "tipos_das_novas": tipos_das_novas, "completadas": len(completar),
            "por_empresa": por_empresa}


def descartar(conexao, usuario, arquivo_id: str) -> None:
    """Descarta a prévia: nada é gravado nas contas, e os CPFs da prévia são apagados do registro do arquivo."""
    autorizar(usuario, "dar_baixa_em_contas")
    _preparar(conexao)
    _arquivo_pendente(conexao, arquivo_id)
    conexao.execute("UPDATE arquivos_de_contas SET situacao = ?, resultado = ?, decidido_em = ? WHERE arquivo_id = ?",
                    (DESCARTADO, json.dumps({"novas": 0}), _agora(), arquivo_id))
    conexao.commit()


def historico(conexao, usuario, empresa_id: str) -> list[dict]:
    """Os arquivos já confirmados DESTA empresa, do mais recente ao mais antigo: quem subiu, quando e quantas baixas.

    Recebe: conexao; usuario (só o BANCO); empresa_id. Levanta KeyError se a empresa não existe.
    Devolve: [{nome_arquivo, enviado_por, enviado_em, linhas, novas, tipos_das_novas: {nova_conta, correntista} (None
    nos arquivos de antes do tipo de conta; os de antes do ADR-149 guardam também a divisão antiga, que a tela não
    usa), completadas, carteira_depois: {com_conta, cadastrados, percentual} da empresa}]. Os arquivos antigos, sem
    empresa (antes do ADR-122), não aparecem em nenhuma.
    """
    autorizar(usuario, "dar_baixa_em_contas")
    _preparar(conexao)
    # A empresa precisa existir na carteira (KeyError vira "não encontrado")
    cadastro_de_empresas.obter(conexao, empresa_id)
    arquivos = []
    consulta = conexao.execute("SELECT nome_arquivo, enviado_por, decidido_em, resultado FROM arquivos_de_contas "
                               "WHERE situacao = ? AND empresa_id = ? ORDER BY decidido_em DESC",
                               (CONFIRMADO, empresa_id))
    for nome_arquivo, enviado_por, decidido_em, resultado in consulta:
        resumo = json.loads(resultado)
        arquivos.append({"nome_arquivo": nome_arquivo, "enviado_por": enviado_por, "enviado_em": decidido_em,
                         "linhas": resumo.get("linhas", 0), "novas": resumo["novas"],
                         "tipos_das_novas": resumo.get("tipos_das_novas"),
                         "completadas": resumo.get("completadas", 0),
                         "carteira_depois": resumo.get("carteira_depois")})
    return arquivos
