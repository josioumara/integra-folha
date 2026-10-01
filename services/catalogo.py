"""Catálogo de produtos e benefícios de cada empresa: a base de conhecimento do Endomarketing (ADR-19).

O banco mantém um documento Markdown por empresa. Cada novo envio do mesmo documento vira uma versão
nova, e só a versão mais recente dentro da vigência é usada. Documento com frase de ordem escondida é
recusado pelo guardrail (ADR-38). A versão 1 nasce dos arquivos de data/parametros/catalogo/.
"""
import json
from datetime import date, datetime, timezone

from services import config, guardrail_injecao

# Pasta dos documentos da versão 1 e do manifesto que diz de qual empresa é cada um
PASTA_CATALOGO = config.RAIZ / "data" / "parametros" / "catalogo"

# O autor gravado nos documentos da versão 1, carregados sozinhos na primeira vez
AUTOR_DA_VERSAO_1 = "sistema (v1 dos arquivos do projeto)"

# As colunas que as consultas de documentos devolvem, na ordem
COLUNAS_DO_DOCUMENTO = ("empresa_id", "titulo", "versao", "vigencia_inicio", "vigencia_fim", "conteudo_md")


def _preparar(conexao) -> None:
    """Cria a tabela do catálogo e, na primeira vez, carrega a versão 1 dos arquivos do projeto."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS catalogo_documentos (
               empresa_id      TEXT NOT NULL,
               titulo          TEXT NOT NULL,
               versao          INTEGER NOT NULL,
               vigencia_inicio TEXT NOT NULL,
               vigencia_fim    TEXT NOT NULL,
               conteudo_md     TEXT NOT NULL,
               criado_em       TEXT NOT NULL,
               criado_por      TEXT NOT NULL,
               PRIMARY KEY (empresa_id, titulo, versao)
           )"""
    )
    # Conta quantos documentos já existem
    quantidade = conexao.execute("SELECT COUNT(*) FROM catalogo_documentos").fetchone()[0]
    # Primeira vez: carrega um documento por empresa, conforme o manifesto
    if quantidade == 0:
        manifesto = json.loads((PASTA_CATALOGO / "manifesto.json").read_text(encoding="utf-8"))
        for item in manifesto:
            conteudo = (PASTA_CATALOGO / item["arquivo"]).read_text(encoding="utf-8")
            _inserir_versao(conexao, item["empresa_id"], item["titulo"], item["vigencia_inicio"],
                            item["vigencia_fim"], conteudo, AUTOR_DA_VERSAO_1)


def _inserir_versao(conexao, empresa_id, titulo, vigencia_inicio, vigencia_fim, conteudo, autor) -> int:
    """Grava o documento como a próxima versão daquele título, naquela empresa. Devolve o número da versão."""
    # Última versão deste título nesta empresa (0 se é a primeira)
    consulta = conexao.execute(
        "SELECT COALESCE(MAX(versao), 0) FROM catalogo_documentos WHERE empresa_id = ? AND titulo = ?",
        (empresa_id, titulo),
    )
    nova_versao = consulta.fetchone()[0] + 1
    # Momento da gravação
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Grava a nova versão
    conexao.execute("INSERT INTO catalogo_documentos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (empresa_id, titulo, nova_versao, vigencia_inicio, vigencia_fim, conteudo, agora, autor))
    conexao.commit()
    return nova_versao


def adicionar_documento(conexao, empresa_id: str, titulo: str, vigencia_inicio: str, vigencia_fim: str,
                        conteudo_md: str, autor: str) -> int:
    """Grava um documento (ou uma nova versão dele). Recusa documento vazio, ordem escondida e vigência invertida."""
    # Garante que a tabela existe
    _preparar(conexao)
    # Documento sem conteúdo
    if not conteudo_md.strip():
        raise ValueError("O documento está vazio.")
    # Guardrail: documento com frase de ordem para a IA é recusado inteiro
    if guardrail_injecao.verificar_mensagem(conteudo_md):
        raise ValueError("Documento recusado pelo Guardrail: contém frase com cara de instrução para o Agente de "
                         "Endomarketing.")
    # O fim da vigência não pode vir antes do início
    if date.fromisoformat(vigencia_fim) < date.fromisoformat(vigencia_inicio):
        raise ValueError("O fim da vigência não pode ser antes do início.")
    return _inserir_versao(conexao, empresa_id, titulo.strip(), vigencia_inicio, vigencia_fim, conteudo_md, autor)


def secoes_do_documento(conteudo_md: str) -> list[dict]:
    """Divide um documento do catálogo nas suas seções (cada "## Título" e o texto até a próxima).

    Recebe: o texto Markdown. Devolve: [{titulo, texto}], na ordem. O título do documento ("# ...") fica de fora.
    Exemplo: "# Pacote\\n## Conta salário\\nSem tarifa.\\n## Crédito\\nTaxa negociada."
             → [{"titulo": "Conta salário", "texto": "Sem tarifa."}, {"titulo": "Crédito", "texto": "Taxa negociada."}]
    """
    secoes = []
    secao_atual = None
    for linha in conteudo_md.splitlines():
        # "## " abre uma seção nova (um benefício ou um canal de atendimento)
        if linha.startswith("## "):
            secao_atual = {"titulo": linha[3:].strip(), "linhas": []}
            secoes.append(secao_atual)
        # As outras linhas entram na seção aberta (antes da primeira seção, é o título do documento: fica de fora)
        elif secao_atual is not None:
            secao_atual["linhas"].append(linha)
    # Junta as linhas de cada seção num texto só, sem linhas vazias nas pontas
    resultado = []
    for secao in secoes:
        resultado.append({"titulo": secao["titulo"], "texto": "\n".join(secao["linhas"]).strip()})
    return resultado


# As seções do catálogo que não são um benefício, mas o jeito de tirar dúvidas (vão para o quadro de atendimento)
SECOES_DE_ATENDIMENTO = ("Onde consultar", "Canais de dúvidas")
# As três partes que todo benefício deve ter para a vitrine (ordem da janela de detalhes): título no Markdown → chave
PARTES_DO_BENEFICIO = {"Como funciona": "como_funciona", "Quem pode usar": "quem_pode_usar",
                       "Como contratar": "como_contratar"}
# As categorias da vitrine: o nome escrito no catálogo ("Categoria: Crédito") → a chave do filtro na tela
CATEGORIAS = {"Conta e dia a dia": "conta", "Crédito": "credito", "Proteção": "protecao",
              "Investimentos": "investimentos"}
# O começo da linha que diz a categoria de um benefício
MARCA_DA_CATEGORIA = "Categoria:"


def partes_do_beneficio(texto: str) -> dict:
    """Separa o texto de uma seção de benefício em categoria, resumo e as três partes da vitrine.

    Recebe: o texto da seção (o que vem depois do "## Título"). Devolve: {categoria, resumo, partes}:
      - categoria: a chave do filtro ("conta", "credito"...) ou None, se a linha "Categoria:" falta ou não é conhecida;
      - resumo: o texto antes da primeira parte (sem a linha da categoria);
      - partes: {como_funciona, quem_pode_usar, como_contratar} com o texto de cada "### ..." que existir.
    Exemplo: "Categoria: Crédito\\nTaxa negociada.\\n### Como funciona\\nParcelas na folha."
             → {"categoria": "credito", "resumo": "Taxa negociada.", "partes": {"como_funciona": "Parcelas na folha."}}
    Catálogo antigo, só com texto corrido: categoria None, o texto inteiro no resumo e nenhuma parte.
    """
    categoria = None
    linhas_do_resumo = []
    linhas_da_parte = {}
    parte_atual = None
    for linha in texto.splitlines():
        # A linha da categoria (fica fora do resumo)
        if linha.strip().startswith(MARCA_DA_CATEGORIA):
            nome = linha.strip()[len(MARCA_DA_CATEGORIA):].strip()
            categoria = CATEGORIAS.get(nome)
            continue
        # "### Como funciona" abre uma parte; um "###" desconhecido fecha a parte aberta e vai para o resumo
        if linha.startswith("### "):
            parte_atual = PARTES_DO_BENEFICIO.get(linha[4:].strip())
            if parte_atual is not None:
                linhas_da_parte[parte_atual] = []
                continue
        # A linha entra na parte aberta ou, antes de qualquer parte, no resumo
        if parte_atual is not None:
            linhas_da_parte[parte_atual].append(linha)
        else:
            linhas_do_resumo.append(linha)
    partes = {}
    for chave, linhas in linhas_da_parte.items():
        partes[chave] = "\n".join(linhas).strip()
    return {"categoria": categoria, "resumo": "\n".join(linhas_do_resumo).strip(), "partes": partes}


def o_que_falta_no_beneficio(texto: str) -> list[str]:
    """O que falta numa seção de benefício para a vitrine: a categoria e cada uma das três partes.

    Recebe: o texto da seção. Devolve: os nomes do que falta (lista vazia = completo).
    Exemplo: só texto corrido → ["Categoria", "Como funciona", "Quem pode usar", "Como contratar"].
    """
    separado = partes_do_beneficio(texto)
    faltam = []
    if separado["categoria"] is None:
        faltam.append("Categoria")
    for nome, chave in PARTES_DO_BENEFICIO.items():
        if not separado["partes"].get(chave):
            faltam.append(nome)
    return faltam


def _linhas_em_dicionarios(consulta) -> list[dict]:
    """Transforma cada linha da consulta num dicionário com os nomes das colunas."""
    documentos = []
    for linha in consulta:
        documentos.append(dict(zip(COLUNAS_DO_DOCUMENTO, linha)))
    return documentos


def documentos_vigentes(conexao, empresa_id: str | None = None, dia: date | None = None) -> list[dict]:
    """A versão mais recente de cada documento, só os vigentes no dia (sem informar, hoje).

    Com empresa_id, devolve SÓ os documentos daquela empresa: a Empresa A nunca vê o pacote da B.
    """
    # Garante que a tabela existe (e a versão 1)
    _preparar(conexao)
    # O dia em texto AAAA-MM-DD, que se compara direto com as datas guardadas
    dia_em_texto = (dia or date.today()).isoformat()
    # Pega, de cada título, só a versão mais alta; e só se o dia estiver dentro da vigência
    consulta = conexao.execute(
        """SELECT documento.empresa_id, documento.titulo, documento.versao, documento.vigencia_inicio,
                  documento.vigencia_fim, documento.conteudo_md
             FROM catalogo_documentos AS documento
            WHERE documento.versao = (SELECT MAX(versao) FROM catalogo_documentos
                                       WHERE empresa_id = documento.empresa_id AND titulo = documento.titulo)
              AND documento.vigencia_inicio <= ? AND documento.vigencia_fim >= ?
              AND (? IS NULL OR documento.empresa_id = ?)
            ORDER BY documento.empresa_id, documento.titulo""",
        (dia_em_texto, dia_em_texto, empresa_id, empresa_id),
    )
    return _linhas_em_dicionarios(consulta)


def documentos_mais_recentes(conexao) -> list[dict]:
    """A versão mais recente de cada documento, vigente ou não (o índice do RAG filtra a vigência na busca)."""
    # Garante que a tabela existe (e a versão 1)
    _preparar(conexao)
    consulta = conexao.execute(
        """SELECT documento.empresa_id, documento.titulo, documento.versao, documento.vigencia_inicio,
                  documento.vigencia_fim, documento.conteudo_md
             FROM catalogo_documentos AS documento
            WHERE documento.versao = (SELECT MAX(versao) FROM catalogo_documentos
                                       WHERE empresa_id = documento.empresa_id AND titulo = documento.titulo)
            ORDER BY documento.empresa_id, documento.titulo"""
    )
    return _linhas_em_dicionarios(consulta)
