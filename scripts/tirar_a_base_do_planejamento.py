"""Tira do banco de dados o que o planejamento guardava da base do banco (ADR-123). Roda UMA vez, na junção.

Para que serve: até o ADR-123, o motor de planejamento classificava cada funcionário cruzando o CPF com a base
sintética do banco, e guardava três colunas que vinham dela na tabela planejamento_funcionario (a classificação, a
autorização de contato e o segmento), além da visão resumo_planejamento, que somava essas colunas. Com o ADR-123, quem
diz o tipo de cada pessoa é o arquivo de contas que o banco devolve; as três colunas e a visão deixam de ser usadas.

Por que é um script, e não uma migração automática ao abrir o banco: o banco de dados (PostgreSQL do .env) é um só
para todos os servidores. Enquanto a versão antiga da aplicação está no ar (porta 8000), ela ainda lê essas colunas e
essa visão; se o servidor de teste as apagasse ao abrir, a versão no ar quebraria. Por isso a limpeza acontece só
depois da junção, logo antes de religar a porta 8000 com a versão nova.

O que ele faz: apaga a visão resumo_planejamento e as três colunas, se ainda existirem. As pessoas continuam na tabela
(empresa, hash do CPF, região e data de referência), aguardando o retorno do banco. Rodar de novo não faz nada.

Para rodar (no banco do .env):
    python scripts/tirar_a_base_do_planejamento.py
"""
import os
import sys
from pathlib import Path

# Nada de IA neste script, mesmo com o .env no modo pago (regra do projeto para script solto)
os.environ["MODE"] = "mock"

# Permite importar os módulos do projeto ao rodar o script diretamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import auth, banco  # noqa: E402

# As colunas que vinham da base do banco: a classificação sorteada, a autorização de contato e o segmento
COLUNAS_DA_BASE_ANTIGA = ("classificacao", "autoriza_contato", "segmento")


def tirar_colunas_da_base_antiga(conexao) -> list[str]:
    """Apaga a visão antiga dos totais e as colunas que vinham da base do banco, se ainda estiverem na tabela.

    Recebe: conexao (a do banco de dados que será limpo).
    Devolve: os nomes das colunas apagadas (vazio se não havia nada a apagar).
    Exemplo: num banco de antes do ADR-123 → ["classificacao", "autoriza_contato", "segmento"]; rodando de novo → [].
    """
    colunas_existentes = banco.colunas_da_tabela(conexao, "planejamento_funcionario")
    # Monta a lista das colunas antigas que ainda estão na tabela
    colunas_para_tirar = []
    for coluna in COLUNAS_DA_BASE_ANTIGA:
        if coluna in colunas_existentes:
            colunas_para_tirar.append(coluna)
    # A visão antiga dos totais somava essas colunas: sai antes, senão o banco não deixa tirar a coluna
    conexao.execute("DROP VIEW IF EXISTS resumo_planejamento")
    # Tira cada coluna antiga, uma por vez
    for coluna in colunas_para_tirar:
        conexao.execute(f"ALTER TABLE planejamento_funcionario DROP COLUMN {coluna}")
    conexao.commit()
    return colunas_para_tirar


def main() -> None:
    """Abre o banco de dados do .env, faz a limpeza e diz o que foi apagado."""
    conexao = auth.conectar()
    try:
        apagadas = tirar_colunas_da_base_antiga(conexao)
    finally:
        conexao.close()
    # Diz o resultado em português, para quem rodou saber se havia algo a limpar
    if apagadas:
        print("Apagadas a visão resumo_planejamento e as colunas: " + ", ".join(apagadas) + ".")
    else:
        print("Nada a apagar: o banco já estava sem as colunas da base do banco.")


if __name__ == "__main__":
    main()
