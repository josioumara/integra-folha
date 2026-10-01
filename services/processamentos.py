"""Recebimento do arquivo: registro, tipo de carga, reenvio repetido e retrato guardado.

Cada envio vira um PROCESSAMENTO, com um identificador próprio. O mesmo identificador vai na barra de
endereço do navegador (ADR-39), para o F5 não perder o arquivo, e no "ponto de salvamento" do fluxo.
O arquivo original é guardado intacto, com a sua impressão digital SHA-256, para auditoria (ADR-31).
Do Word, também fica guardada a tabela que saiu da leitura (ADR-72): quando foi a IA que leu o texto corrido,
as etapas seguintes usam essa tabela e a IA não é chamada (nem paga) de novo.
"""
import json
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from agents import leitor_de_documentos
from models.contratos import ColunaPerfil, EstadoProcessamento, FileProfile, definir_tipo_carga
from services import auditoria, banco, config, execucoes, ingestao, leitura_de_word, parametros
from services import leitura_de_fichas
from services.permissoes import AcessoNegado
from services.uso_da_ia import Uso

# Colunas acrescentadas à tabela de homologados depois da versão inicial (bancos antigos não as têm). A última guarda, em texto
# JSON, as informações sem rótulo da pessoa (ADR-143, Parte 1; services/informacoes_sem_rotulo.py)
COLUNAS_NOVAS_DOS_HOMOLOGADOS = ("matricula", "cargo", "tipo_renda", "valor_renda", "informacoes_sem_rotulo")
# O maior nome de arquivo guardado (o limite comum dos sistemas de arquivos): o resto é cortado (C-09)
TAMANHO_MAXIMO_DO_NOME_DO_ARQUIVO = 255


@dataclass
class Recebimento:
    """O resultado de um envio: o retrato do arquivo e se ele já tinha sido enviado antes."""

    perfil: FileProfile  # o retrato do arquivo (colunas, linhas, tipo de carga, situação)
    duplicado: bool      # True: o mesmo arquivo já tinha sido enviado, e nada novo foi criado


def _preparar(conexao) -> None:
    """Cria as tabelas deste arquivo no banco, se ainda não existirem (outros serviços também a chamam)."""
    # Tabela dos processamentos: um registro por arquivo recebido
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS processamentos (
               processamento_id TEXT PRIMARY KEY,
               empresa_id       TEXT NOT NULL,
               nome_arquivo     TEXT NOT NULL,
               hash_sha256      TEXT NOT NULL,
               caminho_original TEXT NOT NULL,
               tipo_carga       TEXT NOT NULL,
               data_referencia  TEXT NOT NULL,
               status           TEXT NOT NULL,
               perfil           TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               criado_por       TEXT NOT NULL
           )"""
    )
    # Tabela dos funcionários já homologados, preenchida na homologação.
    # Ela decide o tipo de carga e serve de referência nas inclusões (repetição e renda dos colegas).
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS funcionarios_homologados (
               empresa_id       TEXT NOT NULL,
               cpf              TEXT NOT NULL,
               processamento_id TEXT NOT NULL,
               homologado_em    TEXT NOT NULL,
               matricula        TEXT,
               cargo            TEXT,
               tipo_renda       TEXT,
               valor_renda      TEXT,
               informacoes_sem_rotulo TEXT,
               PRIMARY KEY (empresa_id, cpf)
           )"""
    )
    # Descobre quais colunas a tabela de homologados já tem (bancos antigos têm menos)
    colunas_existentes = banco.colunas_da_tabela(conexao, "funcionarios_homologados")
    # Acrescenta as colunas que faltam, sem apagar nada do que já existe
    for coluna in COLUNAS_NOVAS_DOS_HOMOLOGADOS:
        if coluna not in colunas_existentes:
            conexao.execute(f"ALTER TABLE funcionarios_homologados ADD COLUMN {coluna} TEXT")


def empresa_tem_homologados(conexao, empresa_id: str) -> bool:
    """True se a empresa já tem pelo menos um funcionário homologado (então o próximo envio é inclusão)."""
    # Garante que as tabelas existem
    _preparar(conexao)
    # Conta os homologados da empresa
    consulta = conexao.execute("SELECT COUNT(*) FROM funcionarios_homologados WHERE empresa_id = ?", (empresa_id,))
    quantidade = consulta.fetchone()[0]
    # Basta um para a empresa "já ter homologados"
    return quantidade > 0


def _envio_anterior_igual(conexao, empresa_id: str, hash_sha256: str) -> FileProfile | None:
    """Se a empresa já enviou exatamente este arquivo (mesma impressão digital), devolve o retrato dele.

    Envio DESCARTADO (REJEITADO) não conta: a empresa descartou a leitura e pode mandar o mesmo arquivo de novo.
    """
    # Procura o primeiro envio da empresa com a mesma impressão digital que não foi descartado
    consulta = conexao.execute(
        "SELECT perfil FROM processamentos WHERE empresa_id = ? AND hash_sha256 = ? AND status <> ? "
        "ORDER BY criado_em LIMIT 1",
        (empresa_id, hash_sha256, EstadoProcessamento.REJEITADO.value),
    )
    linha = consulta.fetchone()
    # Não achou: é um arquivo novo
    if linha is None:
        return None
    # Achou: transforma o retrato guardado (texto JSON) de volta em FileProfile
    return FileProfile.model_validate_json(linha[0])


# ---------------- Execuções do Leitor e do Conferidor (Acompanhamento dos agentes) ----------------
# A leitura de um Word em texto corrido acontece ANTES de o envio existir: o Leitor de documentos (e o Conferidor da
# leitura, se ligado) só mede o próprio trabalho e devolve a medição. Quem grava em execucoes_agentes é este arquivo,
# que é quem cria o número do envio. Se o arquivo for recusado depois de a IA trabalhar, o trabalho fica registrado
# com um identificador da leitura ("leitura-..."), porque não há envio para prendê-lo.

# O começo do identificador de uma leitura que não virou envio (ex.: "leitura-3f9c2a1b7d4e")
PREFIXO_DA_LEITURA_SEM_ENVIO = "leitura-"


def _identificador_da_leitura_sem_envio() -> str:
    """Um identificador novo para a leitura que não virou envio: "leitura-" e 12 caracteres sorteados."""
    return PREFIXO_DA_LEITURA_SEM_ENVIO + uuid.uuid4().hex[:12]


def _tirar_execucoes_da_leitura(leitura: ingestao.Leitura) -> list[dict]:
    """Tira do uso da IA as execuções medidas na leitura e as devolve (lista vazia se a IA não leu nada).

    Saem dali para a auditoria "TEXTO_CORRIDO_LIDO" e a leitura guardada continuarem só com o uso, como antes.
    """
    if not leitura.uso_da_ia:
        return []
    return leitura.uso_da_ia.pop(leitor_de_documentos.CHAVE_DAS_EXECUCOES, [])


def _execucoes_do_arquivo_recusado(erro: ingestao.ArquivoRecusado) -> list[dict]:
    """As execuções medidas antes de o arquivo ser recusado (ex.: a IA do Leitor caiu no meio da leitura).

    A recusa nasce na leitura do Word (services/leitura_de_word.DocumentoRecusado, que leva as execuções) e a ingestão
    a troca por ArquivoRecusado, guardando a original como "causa" (erro.__cause__). Recusa sem IA (ex.: CSV quebrado)
    não tem causa com execuções: devolve lista vazia.
    """
    causa = erro.__cause__
    # Só a recusa da leitura do Word traz execuções
    if isinstance(causa, leitura_de_word.DocumentoRecusado):
        return causa.execucoes_dos_agentes
    return []


def _gravar_execucoes_da_leitura(conexao, identificador: str, empresa_id: str, execucoes_medidas: list[dict]) -> None:
    """Grava em execucoes_agentes cada execução medida na leitura (Leitor e Conferidor).

    Recebe: identificador — o número do envio (ou o da leitura sem envio); a empresa; as execuções, no formato de
    agents/leitor_de_documentos.execucao_do_leitor (horários em texto ISO). A origem (REAL ou MOCK) sai do modelo, como
    nos outros agentes (services/execucoes.registrar). Tokens e custo vêm do "uso" de cada execução (ADR-131).
    Nada pessoal: agente, etapa, horários, situação, modelo, tokens e custo.
    """
    for execucao_medida in execucoes_medidas:
        execucoes.registrar(conexao, identificador, empresa_id, execucao_medida["etapa"], execucao_medida["agente"],
                            datetime.fromisoformat(execucao_medida["inicio"]),
                            datetime.fromisoformat(execucao_medida["fim"]), execucao_medida["status"],
                            modelo=execucao_medida["modelo"], versao_prompt=execucao_medida["versao_prompt"],
                            tipo_erro=execucao_medida["tipo_erro"],
                            guardrail_disparado=execucao_medida["guardrail_disparado"],
                            uso=Uso.do_dicionario(execucao_medida.get("uso")))


def nome_do_arquivo_saneado(nome_arquivo: str) -> str:
    """O nome do arquivo sem pastas, sem caracteres invisíveis ou de controle e com no máximo 255 letras (C-09).

    Por quê: o nome vem do computador da empresa e vai para o banco de dados e para as telas. Um NUL derruba a
    gravação no PostgreSQL; uma inversão de direção (\\u202e) faz "folha.csv" parecer outro nome; e nada impedia
    um nome de 4.000 letras. O caminho no disco já era seguro (o arquivo é gravado com o código do envio).
    Exemplo: "../fo\\x00lha\\u202e.csv" → "folha.csv". O corte mantém a extensão: 300 letras + ".csv" → 251 + ".csv".
    """
    # Sem pastas: só o último pedaço do caminho (a barra do Windows também separa pastas)
    so_o_nome = PurePosixPath(nome_arquivo.replace("\\", "/")).name
    # Sem os caracteres invisíveis (categoria "Cf") e de controle ("Cc")
    letras_visiveis = []
    for letra in so_o_nome:
        if unicodedata.category(letra) not in ("Cf", "Cc"):
            letras_visiveis.append(letra)
    nome_limpo = "".join(letras_visiveis).strip()
    # Até 255 letras, cortando o começo do nome e mantendo a extensão (".csv", ".xlsx"...)
    if len(nome_limpo) > TAMANHO_MAXIMO_DO_NOME_DO_ARQUIVO:
        extensao = PurePosixPath(nome_limpo).suffix[:10]
        nome_limpo = nome_limpo[:TAMANHO_MAXIMO_DO_NOME_DO_ARQUIVO - len(extensao)] + extensao
    return nome_limpo


def receber_arquivo(conexao, conteudo: bytes, nome_arquivo: str, empresa_id: str, data_referencia: date,
                    usuario: str, cliente=None, conferir_antes_de_registrar=None) -> Recebimento:
    """Lê, retrata e registra o arquivo enviado pela empresa.

    cliente: o LLM, usado só quando o arquivo é um Word em texto corrido (os testes passam um falso).
    conferir_antes_de_registrar: uma função que recebe a leitura e pode recusar o arquivo (ArquivoRecusado) antes de
    ele virar um envio (ex.: "todas as pessoas já estão cadastradas ou em outro envio"). Sem ela, nada é conferido.
    Se o arquivo não puder ser lido, levanta ingestao.ArquivoRecusado com a mensagem para a empresa.
    Se for um reenvio idêntico, devolve o processamento que já existe (duplicado=True).
    """
    # Garante que as tabelas existem
    _preparar(conexao)
    # O nome que a empresa deu ao arquivo, limpo antes de ir para o banco de dados e para as telas (C-09)
    nome_arquivo = nome_do_arquivo_saneado(nome_arquivo)
    # Calcula a impressão digital do arquivo
    hash_sha256 = ingestao.hash_do_arquivo(conteudo)

    # Reenvio idêntico: não cria outro processamento, só registra que aconteceu.
    # A conferência vem antes da leitura: assim o mesmo Word em texto corrido não paga a IA duas vezes
    envio_anterior = _envio_anterior_igual(conexao, empresa_id, hash_sha256)
    if envio_anterior is not None:
        auditoria.registrar(conexao, envio_anterior.processamento_id, empresa_id, "Recebimento", "REENVIO_IDENTICO",
                            {"nome_arquivo": nome_arquivo})
        return Recebimento(envio_anterior, duplicado=True)

    # Lê o arquivo (recusa se o formato, o tamanho ou o conteúdo não servirem)
    limite_em_bytes = config.LIMITE_UPLOAD_MB * 1024 * 1024
    # No Word em texto corrido, a IA preenche os campos do layout vigente (o que o banco cadastrou na tela)
    _, campos_do_layout = parametros.layout_ativo(conexao)
    try:
        leitura = ingestao.ler_arquivo(conteudo, nome_arquivo, limite_em_bytes, cliente=cliente,
                                       campos_do_layout=campos_do_layout)
    except ingestao.ArquivoRecusado as erro:
        # Recusado depois de a IA trabalhar (ex.: ela caiu no meio da leitura): o trabalho dela fica registrado
        _gravar_execucoes_da_leitura(conexao, _identificador_da_leitura_sem_envio(), empresa_id,
                                     _execucoes_do_arquivo_recusado(erro))
        raise
    # As execuções do Leitor e do Conferidor medidas na leitura (saem do uso da IA: a auditoria fica como era)
    execucoes_da_leitura = _tirar_execucoes_da_leitura(leitura)
    # A conferência de quem chamou (pode recusar o arquivo antes de ele virar um envio)
    if conferir_antes_de_registrar is not None:
        try:
            conferir_antes_de_registrar(leitura)
        except ingestao.ArquivoRecusado:
            # A IA leu, mas o arquivo não virou envio: o trabalho dela fica registrado mesmo assim
            _gravar_execucoes_da_leitura(conexao, _identificador_da_leitura_sem_envio(), empresa_id,
                                         execucoes_da_leitura)
            raise

    # Cria um identificador novo (12 caracteres sorteados) para este processamento
    processamento_id = uuid.uuid4().hex[:12]
    # Guarda o arquivo original intacto, para auditoria
    config.PASTA_UPLOADS.mkdir(parents=True, exist_ok=True)
    extensao = nome_arquivo.rsplit(".", 1)[-1].lower()
    caminho_do_original = config.PASTA_UPLOADS / f"{processamento_id}.{extensao}"
    caminho_do_original.write_bytes(conteudo)
    # Documentos e texto: guarda também a tabela que saiu da leitura, para as próximas etapas não lerem (nem pagarem a IA,
    # no texto corrido) de novo
    if leitura.formato in ("docx", "odt", "txt", "rtf"):
        _guardar_leitura(caminho_do_original, leitura)
    # As fichas em texto também passam pela IA: a tabela lida fica guardada do mesmo jeito (ADR-130)
    if leitura_de_fichas.leitura_veio_das_fichas(leitura):
        _guardar_leitura(caminho_do_original, leitura)

    # O tipo de carga é uma regra: com homologados, é inclusão; sem, é carga inicial (ADR-23)
    tipo_carga = definir_tipo_carga(empresa_tem_homologados(conexao, empresa_id))
    # Monta o retrato do arquivo
    perfil = FileProfile(
        processamento_id=processamento_id, empresa_id=empresa_id, nome_arquivo=nome_arquivo,
        formato=leitura.formato, codificacao=leitura.codificacao, separador=leitura.separador,
        linha_do_cabecalho=leitura.linha_do_cabecalho, n_linhas=len(leitura.linhas),
        n_colunas=len(leitura.cabecalhos), colunas=ingestao.perfil_das_colunas(leitura),
        hash_sha256=hash_sha256, tamanho_bytes=len(conteudo), tipo_carga=tipo_carga,
        data_referencia=data_referencia, status=EstadoProcessamento.RECEBIDO,
        avisos=leitura.avisos, alertas_guardrail=leitura.alertas_guardrail, duvidas=leitura.duvidas,
        perguntas_da_ia=leitura.perguntas_da_ia, origem_das_colunas=leitura.origem_das_colunas,
    )
    # Grava o processamento no banco, com o retrato em formato JSON
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conexao.execute(
        "INSERT INTO processamentos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (processamento_id, empresa_id, nome_arquivo, hash_sha256, str(caminho_do_original), tipo_carga.value,
         data_referencia.isoformat(), perfil.status.value, perfil.model_dump_json(), agora, usuario),
    )
    conexao.commit()
    # Registra o recebimento na trilha de auditoria (só contagens: nada pessoal)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Recebimento", "RECEBIDO",
                        {"linhas": perfil.n_linhas, "colunas": perfil.n_colunas, "tipo_carga": tipo_carga.value,
                         "formato": perfil.formato})
    # Se a IA leu o texto corrido do Word, registra modo, modelo, custo e contagens (nada pessoal)
    if leitura.uso_da_ia:
        auditoria.registrar(conexao, processamento_id, empresa_id, "Leitor de Documentos", "TEXTO_CORRIDO_LIDO",
                            leitura.uso_da_ia)
    # E as execuções do Leitor e do Conferidor, com o número do envio (Acompanhamento dos agentes)
    _gravar_execucoes_da_leitura(conexao, processamento_id, empresa_id, execucoes_da_leitura)
    # Se o guardrail trocou algum texto, registra onde (linha e coluna), na trilha de auditoria
    if leitura.alertas_guardrail:
        posicoes = []
        for alerta in leitura.alertas_guardrail:
            posicoes.append((alerta["linha"], alerta["coluna"]))
        auditoria.registrar(conexao, processamento_id, empresa_id, "Guardrail de entrada", "INJECAO_REMOVIDA",
                            {"quantidade": len(leitura.alertas_guardrail), "posicoes": posicoes})
    return Recebimento(perfil, duplicado=False)


def obter(conexao, processamento_id: str, empresa_id: str | None = None) -> FileProfile | None:
    """O retrato de um processamento. Com empresa_id, só devolve se o processamento for daquela empresa.

    É isso que impede uma empresa de ver o arquivo de outra, mesmo copiando o link.
    """
    # Garante que as tabelas existem
    _preparar(conexao)
    # "? IS NULL OR empresa_id = ?": sem empresa informada, não filtra; com empresa, só a dela
    consulta = conexao.execute(
        "SELECT perfil FROM processamentos WHERE processamento_id = ? AND (? IS NULL OR empresa_id = ?)",
        (processamento_id, empresa_id, empresa_id),
    )
    linha = consulta.fetchone()
    # Não achou (ou é de outra empresa)
    if linha is None:
        return None
    # Transforma o texto JSON de volta em FileProfile
    return FileProfile.model_validate_json(linha[0])


def obter_da_empresa(conexao, processamento_id: str, empresa_id: str) -> FileProfile | None:
    """O processamento, SÓ se for da empresa informada. Empresa vazia é recusada (AcessoNegado).

    É a porta das operações de empresa (correção, homologação, fluxo, Assistente): sem ela, um empresa_id
    vazio significaria "sem filtro" e abriria o arquivo de qualquer empresa.
    """
    if not empresa_id:
        raise AcessoNegado("Operação de empresa sem empresa: acesso negado.")
    return obter(conexao, processamento_id, empresa_id=empresa_id)


def listar(conexao, empresa_id: str) -> list[FileProfile]:
    """Todos os envios da empresa, do mais recente para o mais antigo."""
    # Garante que as tabelas existem
    _preparar(conexao)
    # Desempate pela ordem de gravação (rowid): dois envios no mesmo segundo ficam na ordem em que chegaram.
    # No PostgreSQL, a porta do banco acrescenta a coluna rowid (ADR-67), então a ordem é a mesma nos dois
    consulta = conexao.execute(
        "SELECT perfil FROM processamentos WHERE empresa_id = ? ORDER BY criado_em DESC, rowid DESC", (empresa_id,))
    # Transforma cada retrato guardado em FileProfile
    envios = []
    for linha in consulta:
        envios.append(FileProfile.model_validate_json(linha[0]))
    return envios


def nomes_na_tela(conexao, empresa_id: str) -> dict[str, str]:
    """O nome de cada envio da empresa como a tela mostra: arquivos diferentes com o mesmo nome ganham a versão.

    Para que serve: quando a empresa envia dois arquivos diferentes chamados "aurora_carga_inicial.xlsx", a pendência
    diria "também está no arquivo aurora_carga_inicial.xlsx" dentro do próprio aurora_carga_inicial.xlsx. Por isso,
    cada um vira "aurora_carga_inicial.xlsx (v1)" e "(v2)", pela ordem de
    chegada, no filtro de arquivos, na linha de baixo do cartão, nos prontos para o banco e na mensagem da pendência.
    Recebe: conexao; empresa_id. Devolve: {processamento_id: nome}. O nome que não se repete fica como está; a
    comparação ignora maiúsculas. Todos os envios contam, até os descartados e os que já foram ao banco: assim a
    versão de um arquivo nunca muda depois.
    Ex.: dois "aurora.xlsx" e um "brisa.xlsx" →
    {"a1": "aurora.xlsx (v1)", "a2": "aurora.xlsx (v2)", "b1": "brisa.xlsx"}.
    """
    # Do mais antigo para o mais recente (listar devolve do mais recente para o mais antigo)
    envios_em_ordem_de_chegada = list(reversed(listar(conexao, empresa_id)))
    # Quantas vezes cada nome aparece
    vezes_do_nome = {}
    for envio in envios_em_ordem_de_chegada:
        chave_do_nome = envio.nome_arquivo.casefold()
        vezes_do_nome[chave_do_nome] = vezes_do_nome.get(chave_do_nome, 0) + 1
    # O nome de cada envio: com a versão só quando o nome se repete
    nomes = {}
    versao_do_nome = {}
    for envio in envios_em_ordem_de_chegada:
        chave_do_nome = envio.nome_arquivo.casefold()
        if vezes_do_nome[chave_do_nome] == 1:
            nomes[envio.processamento_id] = envio.nome_arquivo
            continue
        versao_do_nome[chave_do_nome] = versao_do_nome.get(chave_do_nome, 0) + 1
        nomes[envio.processamento_id] = f"{envio.nome_arquivo} (v{versao_do_nome[chave_do_nome]})"
    return nomes


def listar_pagina(conexao, empresa_id: str, inicio: int, quantidade: int) -> list[FileProfile]:
    """Uma página dos envios da empresa, na mesma ordem de listar (do mais recente para o mais antigo).

    Recebe: empresa_id; inicio (quantos pular, a partir de 0); quantidade (quantos trazer).
    Devolve: no máximo `quantidade` envios. Exemplo: inicio=5, quantidade=5 → do 6º ao 10º envio.
    Por que no banco (LIMIT e OFFSET) e não na tela: uma empresa pode ter centenas de envios; só a página pedida é
    lida e montada.
    """
    _preparar(conexao)
    # LIMIT: quantos trazer; OFFSET: quantos pular (a mesma forma no SQLite e no PostgreSQL)
    consulta = conexao.execute(
        "SELECT perfil FROM processamentos WHERE empresa_id = ? ORDER BY criado_em DESC, rowid DESC LIMIT ? OFFSET ?",
        (empresa_id, quantidade, inicio))
    envios = []
    for linha in consulta:
        envios.append(FileProfile.model_validate_json(linha[0]))
    return envios


def contar(conexao, empresa_id: str) -> int:
    """Quantos envios a empresa tem (para a tela dizer "Mostrando 5 de 120 envios")."""
    _preparar(conexao)
    return conexao.execute("SELECT COUNT(*) FROM processamentos WHERE empresa_id = ?", (empresa_id,)).fetchone()[0]


def _caminho_que_existe(caminho_guardado) -> Path:
    """Onde o arquivo original está hoje, mesmo que a pasta do projeto tenha mudado de nome depois do envio.

    Recebe: o caminho gravado no banco no dia do envio. Devolve: esse caminho, se o arquivo ainda está lá; senão, o
    mesmo nome de arquivo na pasta de uploads atual, se ele estiver lá; senão, o caminho gravado (quem lê o arquivo
    dá o erro de "arquivo não encontrado").
    Por quê: o projeto se chamava "ai-payroll-hub" e passou a "integra-folha"; os envios antigos
    guardaram o caminho com o nome antigo da pasta, que não existe mais.
    Exemplo: "D:\\AI_Payroll_Hub\\ai-payroll-hub\\storage\\uploads\\fa647ab8753a.csv" → a mesma pasta de uploads de hoje
    + "fa647ab8753a.csv".
    """
    # O caminho gravado ainda vale: usa ele
    caminho = Path(caminho_guardado)
    if caminho.exists():
        return caminho
    # Só o nome do arquivo (sem as pastas), procurado na pasta de uploads atual; o nome é o do próprio envio
    caminho_na_pasta_atual = config.PASTA_UPLOADS / caminho.name
    if caminho_na_pasta_atual.exists():
        return caminho_na_pasta_atual
    # Não está em nenhum dos dois lugares: devolve o gravado, e a leitura avisa que o arquivo não existe
    return caminho


def _caminho_da_leitura_guardada(caminho_do_original) -> Path:
    """Onde fica a tabela lida do Word: ao lado do original, terminando em ".leitura.json" (ex.: abc123.leitura.json)."""
    return Path(caminho_do_original).with_suffix(".leitura.json")


def _guardar_leitura(caminho_do_original, leitura: ingestao.Leitura) -> None:
    """Grava a leitura inteira (cabeçalhos, linhas, avisos) num arquivo JSON ao lado do original."""
    # asdict transforma a Leitura num dicionário simples, que o JSON sabe gravar
    dados = asdict(leitura)
    _caminho_da_leitura_guardada(caminho_do_original).write_text(json.dumps(dados, ensure_ascii=False),
                                                                encoding="utf-8")


def _ler_leitura_guardada(caminho_da_leitura: Path) -> ingestao.Leitura:
    """Lê de volta a leitura gravada por _guardar_leitura."""
    dados = json.loads(caminho_da_leitura.read_text(encoding="utf-8"))
    # O JSON só guarda chaves de texto: as posições das colunas voltam a ser números
    celulas_numericas = {}
    for posicao, quantidade in dados["celulas_numericas"].items():
        celulas_numericas[int(posicao)] = quantidade
    dados["celulas_numericas"] = celulas_numericas
    return ingestao.Leitura(**dados)


def carregar_tabela(conexao, processamento_id: str) -> ingestao.Leitura:
    """Relê o arquivo original guardado, com as mesmas regras (e o mesmo guardrail), para as fases seguintes.

    Word: usa a tabela guardada no recebimento (a IA do texto corrido não é chamada de novo).
    """
    # Garante que as tabelas existem
    _preparar(conexao)
    # Onde está o original e qual era o nome dele
    consulta = conexao.execute("SELECT caminho_original, nome_arquivo FROM processamentos WHERE processamento_id = ?",
                               (processamento_id,))
    linha = consulta.fetchone()
    # Processamento inexistente
    if linha is None:
        raise KeyError(processamento_id)
    caminho_gravado, nome_arquivo = linha
    # Onde o original está hoje (a pasta do projeto pode ter mudado de nome depois do envio)
    caminho_do_original = _caminho_que_existe(caminho_gravado)
    # Documentos e texto: a tabela lida no recebimento já está guardada, ao lado do original
    caminho_da_leitura = _caminho_da_leitura_guardada(caminho_do_original)
    if caminho_da_leitura.exists():
        return _ler_leitura_guardada(caminho_da_leitura)
    # Lê de novo o arquivo guardado
    limite_em_bytes = config.LIMITE_UPLOAD_MB * 1024 * 1024
    return ingestao.ler_arquivo(Path(caminho_do_original).read_bytes(), nome_arquivo, limite_em_bytes)


def guardar_tabela_do_envio(conexao, processamento_id: str, leitura: ingestao.Leitura) -> FileProfile:
    """Grava a tabela do envio depois de a empresa mudar as colunas (ex.: dividir o endereço em partes) e refaz o
    retrato das colunas. Devolve o retrato novo.

    A tabela fica ao lado do original (".leitura.json", como a do Word): as etapas seguintes leem dela, e o arquivo
    original continua intacto para a auditoria.
    """
    consulta = conexao.execute("SELECT caminho_original FROM processamentos WHERE processamento_id = ?",
                               (processamento_id,))
    linha = consulta.fetchone()
    if linha is None:
        raise KeyError(processamento_id)
    # Grava ao lado do original, onde ele está hoje (a pasta do projeto pode ter mudado de nome depois do envio)
    _guardar_leitura(_caminho_que_existe(linha[0]), leitura)
    # O retrato passa a ter as colunas novas
    perfil = obter(conexao, processamento_id)
    colunas = []
    for coluna in ingestao.perfil_das_colunas(leitura):
        colunas.append(ColunaPerfil(**coluna))
    perfil.colunas = colunas
    perfil.n_colunas = len(leitura.cabecalhos)
    conexao.execute("UPDATE processamentos SET perfil = ? WHERE processamento_id = ?",
                    (perfil.model_dump_json(), processamento_id))
    conexao.commit()
    return perfil


def atualizar_status(conexao, processamento_id: str, status: EstadoProcessamento) -> None:
    """Muda a situação do processamento (ex.: de RECEBIDO para MAPEAMENTO_PENDENTE).

    A situação fica em dois lugares (na coluna "status" e dentro do retrato), e os dois mudam juntos.
    """
    # Pega o retrato atual
    perfil = obter(conexao, processamento_id)
    # Muda a situação dentro do retrato
    perfil.status = status
    # Grava a situação nova na coluna e no retrato
    conexao.execute("UPDATE processamentos SET status = ?, perfil = ? WHERE processamento_id = ?",
                    (status.value, perfil.model_dump_json(), processamento_id))
    conexao.commit()
