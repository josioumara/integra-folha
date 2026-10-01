"""Homologação: o clique final da empresa, que libera o planejamento do banco.

Só homologa sem BLOQUEANTE e com todo ALERTA corrigido ou justificado. O arquivo final contém só os
registros autorizados (sem linhas excluídas e sem quem já estava homologado), no layout do banco, com
checksum SHA-256. Depois:
- os funcionários entram em `funcionarios_homologados` (vínculo, referência de renda nas inclusões);
- o MAPEAMENTO aprovado por pessoa entra no histórico como par estruturado (coluna → campo, empresa,
  versão). Nada do chat nem de célula vira conhecimento (ADR-38);
- com o aprendizado ligado (a aplicação liga ao abrir), o histórico atualiza o índice de mapeamentos aprovados do
  RAG, e a próxima planilha de qualquer empresa já encontra esses pares na busca (rag/aprendizado.py, ADR-70).
"""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from models.contratos import EstadoProcessamento, StatusMapeamento
from rag import aprendizado
from services import auditoria, config, correcoes, mapeamentos, parametros, processamentos, validador
# As informações sem rótulo seguem com o funcionário no cadastro (ADR-143, Parte 1)
from services import informacoes_sem_rotulo

# Onde os arquivos finais ficam (fora do Git)
PASTA_HOMOLOGADOS = config.PASTA_HOMOLOGADOS


def _preparar(conexao) -> None:
    """Cria as tabelas das homologações e do histórico de mapeamentos, se ainda não existirem."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS homologacoes (
               processamento_id TEXT PRIMARY KEY,
               empresa_id       TEXT NOT NULL,
               arquivo_final    TEXT NOT NULL,
               checksum_sha256  TEXT NOT NULL,
               relatorio        TEXT NOT NULL,
               homologado_por   TEXT NOT NULL,
               homologado_em    TEXT NOT NULL
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS historico_mapeamentos (
               coluna_origem    TEXT NOT NULL,
               campo            TEXT NOT NULL,
               empresa_id       TEXT NOT NULL,
               versao_layout    INTEGER NOT NULL,
               processamento_id TEXT NOT NULL,
               PRIMARY KEY (coluna_origem, campo, empresa_id, versao_layout)
           )"""
    )


# Começos de célula que o Excel trata como fórmula ao abrir um CSV ("CSV injection")
INICIOS_DE_FORMULA = ("=", "+", "@", "\t", "\r")


def neutralizar_formula(valor: str) -> str:
    """Um texto que o Excel executaria como fórmula ganha um apóstrofo na frente e vira só texto.

    Ex.: "=HYPERLINK(...)" vira "'=HYPERLINK(...)". Um "-" só é perigoso quando não é número ("-10.00"
    fica como está; "-cmd" ganha o apóstrofo).
    """
    if valor.startswith(INICIOS_DE_FORMULA):
        return "'" + valor
    if valor.startswith("-") and not valor[1:].replace(".", "", 1).isdigit():
        return "'" + valor
    return valor


def arquivo_final(registros: list[dict], campos: list[str]) -> bytes:
    """CSV no layout do banco: campos na ordem do layout, separador ";" e UTF-8.

    Proteção contra "CSV injection": célula com cara de fórmula é neutralizada (neutralizar_formula).
    """
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(campos)
    for registro in registros:
        # Campo vazio (None) sai como texto vazio
        linha = []
        for campo in campos:
            valor = registro.get(campo)
            linha.append("" if valor is None else neutralizar_formula(str(valor)))
        escritor.writerow(linha)
    return saida.getvalue().encode("utf-8")


def conferir_antes_do_envio(conexao, processamento_id: str, empresa_id: str) -> None:
    """Confere, sobre os dados atuais, que o arquivo pode ir para a avaliação do banco (sem gravar nada de cadastro).

    Recebe: conexao; processamento_id; empresa_id (da sessão). Devolve: nada.
    Levanta KeyError (envio de outra empresa) ou ValueError (já homologado, ou ainda com pendências).
    """
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise KeyError(processamento_id)
    if perfil.status == EstadoProcessamento.HOMOLOGADO:
        raise ValueError("Este arquivo já foi homologado.")
    # Valida de novo, sempre sobre os dados atuais
    relatorio = validador.executar(conexao, processamento_id, empresa_id)
    if not relatorio.pronto_para_homologar:
        raise ValueError("Ainda há pendências: corrija os bloqueantes e corrija ou justifique os alertas.")


def homologar(conexao, processamento_id: str, empresa_id: str, usuario: str,
              linhas_devolvidas: set[int] | None = None) -> dict:
    """Homologa o arquivo: gera o arquivo final, registra os funcionários e o mapeamento. Devolve o
    relatório de qualidade.

    linhas_devolvidas: as pessoas que o banco devolveu à empresa ao aprovar as outras (ADR-121). Elas ficam fora do
    arquivo final e do cadastro; seguem num envio de devolução (services/devolucao_por_pessoa.py). Sem elas, entra
    todo mundo, como sempre.
    """
    _preparar(conexao)
    linhas_devolvidas = linhas_devolvidas or set()
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise KeyError(processamento_id)
    if perfil.status == EstadoProcessamento.HOMOLOGADO:
        raise ValueError("Este arquivo já foi homologado.")
    # Valida de novo, sempre sobre os dados atuais
    relatorio = validador.executar(conexao, processamento_id, empresa_id)
    if not relatorio.pronto_para_homologar:
        raise ValueError("Ainda há pendências: corrija os bloqueantes e corrija ou justifique os alertas.")

    # O arquivo final: dados atuais, sem quem já estava homologado na empresa
    versao, campos = parametros.layout_ativo(conexao)
    nomes_dos_campos = []
    for campo in campos:
        nomes_dos_campos.append(campo.campo)
    dados = correcoes.dados_atuais(conexao, processamento_id)
    # As linhas que ficam de fora (já cadastradas ou já com o banco noutro envio; ADR-126)
    linhas_de_fora = validador.linhas_que_ficam_de_fora(relatorio)
    linhas_ja_homologadas = set()
    for linha, achado in linhas_de_fora.items():
        if achado.regra_id == validador.JA_HOMOLOGADO_NA_EMPRESA:
            linhas_ja_homologadas.add(linha)
    registros_finais = []
    for registro in dados.registros:
        # Fica de fora quem não vai por este envio e quem o banco devolveu à empresa
        if registro["_linha"] not in linhas_de_fora and registro["_linha"] not in linhas_devolvidas:
            registros_finais.append(registro)
    conteudo = arquivo_final(registros_finais, nomes_dos_campos)
    checksum = hashlib.sha256(conteudo).hexdigest()
    PASTA_HOMOLOGADOS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_HOMOLOGADOS / f"{processamento_id}.csv"
    caminho.write_bytes(conteudo)

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Os funcionários homologados (vínculo e referência de renda para as próximas inclusões)
    for registro in registros_finais:
        # As informações sem rótulo seguem com o funcionário, em texto JSON (vazio quando não há; ADR-143, Parte 1)
        sem_rotulo = informacoes_sem_rotulo.em_texto(informacoes_sem_rotulo.guardadas(registro))
        # Grava ou atualiza a pessoa nesta empresa ("ON CONFLICT": a mesma forma no SQLite e no PostgreSQL)
        conexao.execute("INSERT INTO funcionarios_homologados (empresa_id, cpf, processamento_id, homologado_em, "
                        "matricula, cargo, tipo_renda, valor_renda, informacoes_sem_rotulo) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT (empresa_id, cpf) DO UPDATE SET processamento_id = excluded.processamento_id, "
                        "homologado_em = excluded.homologado_em, matricula = excluded.matricula, "
                        "cargo = excluded.cargo, tipo_renda = excluded.tipo_renda, valor_renda = excluded.valor_renda, "
                        "informacoes_sem_rotulo = excluded.informacoes_sem_rotulo",
                        (empresa_id, registro["cpf"], processamento_id, agora, registro.get("matricula"),
                         registro.get("cargo"), registro.get("tipo_renda"), registro.get("valor_renda"), sem_rotulo))
    # O histórico: só pares aprovados por pessoa; nada do chat, nada de célula
    plano, _ = mapeamentos.obter(conexao, processamento_id)
    for item in plano.itens:
        if item.status == StatusMapeamento.PROPOSTO:
            # "ON CONFLICT DO NOTHING": o par que já está no histórico não é gravado de novo
            conexao.execute("INSERT INTO historico_mapeamentos (coluna_origem, campo, empresa_id, versao_layout, "
                            "processamento_id) VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                            (item.coluna, item.campo, empresa_id, versao, processamento_id))
    # O relatório de qualidade
    registros_excluidos, valores_corrigidos = 0, 0
    for correcao in correcoes.listar(conexao, processamento_id, "APLICADA"):
        if correcao.campo == correcoes.EXCLUIR:
            registros_excluidos += 1
        else:
            valores_corrigidos += 1
    alertas_justificados = 0
    for achado in relatorio.achados:
        if achado.resolvido:
            alertas_justificados += 1
    qualidade = {
        "registros_recebidos": perfil.n_linhas, "registros_homologados": len(registros_finais),
        "registros_excluidos": registros_excluidos,
        "ja_homologados_ignorados": len(linhas_ja_homologadas),
        # Todas as linhas que ficaram de fora do envio, pelos dois motivos (ADR-126)
        "linhas_que_ficaram_de_fora": len(linhas_de_fora),
        "devolvidos_pelo_banco": len(linhas_devolvidas),
        "valores_corrigidos": valores_corrigidos,
        "alertas_justificados": alertas_justificados,
        "avisos": relatorio.contagem()["AVISO"], "versao_layout": versao,
        "checksum_sha256": checksum}
    conexao.execute("INSERT INTO homologacoes VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (processamento_id, empresa_id, str(caminho), checksum, json.dumps(qualidade, ensure_ascii=False),
                     usuario, agora))
    conexao.commit()
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.HOMOLOGADO)
    # A memória que aprende: os pares já gravados atualizam o índice de mapeamentos aprovados (se ligado)
    aprendizado.aprender_depois_da_aprovacao(historico(conexao), campos)
    # Na auditoria vai o relatório sem o checksum
    detalhes = dict(qualidade)
    del detalhes["checksum_sha256"]
    auditoria.registrar(conexao, processamento_id, empresa_id, "Homologação", "HOMOLOGADO", detalhes)
    return qualidade


def obter(conexao, processamento_id: str) -> dict | None:
    """Relatório de qualidade e o arquivo final (bytes), se já homologado."""
    _preparar(conexao)
    linha = conexao.execute("SELECT arquivo_final, relatorio, homologado_por, homologado_em FROM homologacoes "
                            "WHERE processamento_id = ?", (processamento_id,)).fetchone()
    if linha is None:
        return None
    caminho, relatorio, homologado_por, homologado_em = linha
    return {"arquivo": Path(caminho).read_bytes(), "relatorio": json.loads(relatorio),
            "homologado_por": homologado_por, "homologado_em": homologado_em}


def historico(conexao) -> list[dict]:
    """Todos os mapeamentos homologados (coluna → campo, empresa, versão do layout)."""
    _preparar(conexao)
    linhas = conexao.execute("SELECT coluna_origem, campo, empresa_id, versao_layout FROM historico_mapeamentos")
    pares = []
    for coluna_origem, campo, empresa_id, versao_layout in linhas:
        pares.append({"coluna_origem": coluna_origem, "campo": campo, "empresa_id": empresa_id,
                      "versao_layout": versao_layout})
    return pares
