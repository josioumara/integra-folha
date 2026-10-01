"""Trilha de auditoria: o registro de tudo o que acontece com cada processamento.

Guarda quem fez o quê, em que etapa e quando. Nunca guarda dado pessoal:
só identificadores, a etapa, o tipo do evento e um detalhe técnico (contagens, nomes de regras).
Exemplo de evento: etapa "Validação", tipo "VALIDADO", detalhe {"contagem": {"BLOQUEANTE": 1, ...}}.
"""
import json
from datetime import datetime, timezone


def _preparar(conexao) -> None:
    """Cria a tabela de eventos no banco, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS eventos (
               id               INTEGER PRIMARY KEY AUTOINCREMENT,
               processamento_id TEXT NOT NULL,
               empresa_id       TEXT NOT NULL,
               etapa            TEXT NOT NULL,
               tipo             TEXT NOT NULL,
               detalhe          TEXT NOT NULL,
               criado_em        TEXT NOT NULL
           )"""
    )


def registrar(conexao, processamento_id: str, empresa_id: str, etapa: str, tipo: str, detalhe: dict) -> None:
    """Grava um evento na trilha. O detalhe é um dicionário, guardado como texto JSON."""
    # Garante que a tabela existe
    _preparar(conexao)
    # Momento do evento, no horário universal (UTC), sem frações de segundo
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Transforma o detalhe em texto JSON, mantendo os acentos legíveis
    detalhe_em_texto = json.dumps(detalhe, ensure_ascii=False)
    # Grava o evento
    conexao.execute(
        "INSERT INTO eventos (processamento_id, empresa_id, etapa, tipo, detalhe, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
        (processamento_id, empresa_id, etapa, tipo, detalhe_em_texto, agora),
    )
    conexao.commit()


def eventos(conexao, processamento_id: str | None = None) -> list[dict]:
    """Os eventos, na ordem em que aconteceram. Com processamento_id, só os daquele processamento."""
    # Garante que a tabela existe
    _preparar(conexao)
    # "? IS NULL OR ...": sem processamento informado, traz todos
    consulta = conexao.execute(
        """SELECT processamento_id, empresa_id, etapa, tipo, detalhe, criado_em FROM eventos
            WHERE (? IS NULL OR processamento_id = ?) ORDER BY id""",
        (processamento_id, processamento_id),
    )
    lista_de_eventos = []
    for processamento, empresa, etapa, tipo, detalhe_em_texto, criado_em in consulta:
        # Monta o evento como dicionário, com o detalhe de volta de texto JSON para dicionário
        lista_de_eventos.append({"processamento_id": processamento, "empresa_id": empresa, "etapa": etapa,
                                 "tipo": tipo, "detalhe": json.loads(detalhe_em_texto), "criado_em": criado_em})
    return lista_de_eventos
