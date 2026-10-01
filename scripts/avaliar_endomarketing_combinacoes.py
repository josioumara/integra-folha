"""Roda o EXP-019 (as combinações do Endomarketing) numa CÓPIA do banco e grava o resultado.

A lógica está em eval/combinacoes_do_endomarketing.py (a grade, os pedidos e a amostra) e em
eval/resumo_das_combinacoes.py (as tabelas); aqui ficam as etapas, os arquivos e a conferência do ambiente:
- etapa 1 (MOCK, sem custo): a grade inteira → data/avaliacao/resultados/endomarketing_combinacoes_etapa1.csv;
- etapa 2 (IA real, com teto em dólares): a amostra tirada da etapa 1 → endomarketing_combinacoes_etapa2.csv;
- resumir: as duas etapas → data/avaliacao/resultados/endomarketing_combinacoes.json (as tabelas do EXP-019).
Sempre numa CÓPIA (regra do projeto: nada de rascunhos, execuções ou gastos no banco de todos):
- BANCO=postgres com o POSTGRES_URL de um banco de teste restaurado de um pg_dump, ou BANCO=sqlite com o CAMINHO_BANCO
  de uma cópia;
- PASTA_INDICES numa cópia do índice do RAG.
O script se recusa a rodar no banco e no índice de todos. A etapa 2 exige MODE=llm e o teto (a aprovação vem antes).

Para rodar (PowerShell, na pasta do repositório, com o banco e o índice já apontados para as cópias):
  $env:MODE='mock'; python scripts/avaliar_endomarketing_combinacoes.py --etapa 1
  $env:MODE='llm';  python scripts/avaliar_endomarketing_combinacoes.py --etapa 2 --teto-usd 5
  python scripts/avaliar_endomarketing_combinacoes.py --resumir
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
# O Python passa a achar os módulos do projeto (eval, services...) a partir da raiz
sys.path.insert(0, str(RAIZ))

from eval import combinacoes_do_endomarketing as combinacoes  # noqa: E402
from eval import resumo_das_combinacoes  # noqa: E402
from services import auth  # noqa: E402

# Onde os resultados ficam (os brutos de cada medição, regravados a cada execução)
PASTA_DOS_RESULTADOS = RAIZ / "data" / "avaliacao" / "resultados"
CSV_DA_ETAPA_1 = PASTA_DOS_RESULTADOS / "endomarketing_combinacoes_etapa1.csv"     # a grade inteira, no MOCK
CSV_DA_ETAPA_2 = PASTA_DOS_RESULTADOS / "endomarketing_combinacoes_etapa2.csv"     # a amostra, com a IA real
ARQUIVO_DO_RESUMO = PASTA_DOS_RESULTADOS / "endomarketing_combinacoes.json"        # as tabelas do EXP-019


def ler_opcoes() -> argparse.Namespace:
    """A etapa (1 ou 2) ou o resumo, e o teto em dólares da etapa 2."""
    leitor = argparse.ArgumentParser(description="EXP-019: as combinações do Endomarketing, numa cópia do banco.")
    # Uma coisa de cada vez: a etapa 1, a etapa 2 ou o resumo
    grupo = leitor.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--etapa", type=int, choices=(1, 2), help="1 = a grade em MOCK; 2 = a amostra com a IA real")
    grupo.add_argument("--resumir", action="store_true", help="junta as duas etapas no resumo do EXP")
    # O teto da IA real e o ensaio com poucas combinações
    leitor.add_argument("--teto-usd", type=float, dest="teto_usd", help="o teto em dólares da etapa 2 (obrigatório)")
    leitor.add_argument("--limite", type=int, help="só as N primeiras combinações (um ensaio antes da medição)")
    return leitor.parse_args()


def rodar_a_etapa_1(limite: int | None) -> dict:
    """A grade inteira em MOCK, gravada no CSV da etapa 1."""
    # O banco do ambiente (a cópia: conferir_o_ambiente já recusou o de todos)
    conexao = auth.conectar()
    try:
        # Todas as combinações de todas as empresas cadastradas
        grade = combinacoes.montar_grade(conexao)
        # O ensaio roda só o começo da grade
        if limite:
            grade = grade[:limite]
        print(f"Etapa 1 (MOCK): {len(grade)} combinações", flush=True)
        rodada = combinacoes.rodar(conexao, grade, etapa=1)
    finally:
        # A conexão fecha mesmo se a execução quebrar
        conexao.close()
    # Uma linha por combinação, com o que a tela mostraria
    combinacoes.gravar_csv(rodada["linhas"], CSV_DA_ETAPA_1)
    return rodada


def rodar_a_etapa_2(teto_usd: float, limite: int | None) -> dict:
    """A amostra com a IA real, tirada da etapa 1, gravada no CSV da etapa 2 (para antes do teto)."""
    # A amostra sai da etapa 1, com a semente fixa: a mesma a cada vez
    amostra = combinacoes.escolher_a_amostra(combinacoes.ler_csv(CSV_DA_ETAPA_1))
    # O ensaio roda só o começo da amostra
    if limite:
        amostra = amostra[:limite]
    print(f"Etapa 2 (IA real): {len(amostra)} combinações, teto US$ {teto_usd:.2f}", flush=True)
    # O banco do ambiente (a cópia)
    conexao = auth.conectar()
    try:
        # Com a IA real, o texto de cada material fica guardado para comparar com o MOCK
        rodada = combinacoes.rodar(conexao, amostra, etapa=2, teto_usd=teto_usd, guardar_o_texto=True)
    finally:
        # A conexão fecha mesmo se a execução quebrar
        conexao.close()
    combinacoes.gravar_csv(rodada["linhas"], CSV_DA_ETAPA_2)
    return rodada


def resumir() -> dict:
    """O resumo das duas etapas, com onde a etapa 2 parou (a amostra inteira sai de novo da etapa 1, pela semente)."""
    # As duas etapas, lidas dos CSVs
    linhas_da_etapa_1 = combinacoes.ler_csv(CSV_DA_ETAPA_1)
    linhas_da_etapa_2 = combinacoes.ler_csv(CSV_DA_ETAPA_2)
    resumo = resumo_das_combinacoes.resumir(linhas_da_etapa_1, linhas_da_etapa_2)
    # Quantas da amostra rodaram: menos que o total quer dizer que o teto (ou a IA fora do ar) parou antes
    resumo["etapa_2"]["amostra_planejada"] = len(combinacoes.escolher_a_amostra(linhas_da_etapa_1))
    # O JSON do resumo, lido no registro do EXP
    ARQUIVO_DO_RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                 newline="\n")
    return resumo


def main() -> None:
    """Confere o ambiente, roda a etapa pedida (ou o resumo) e mostra o essencial."""
    opcoes = ler_opcoes()
    # O resumo não chama a IA nem o banco: só lê os CSVs
    if opcoes.resumir:
        resumo = resumir()
        print(f"Resumo gravado em {ARQUIVO_DO_RESUMO}: etapa 1 {resumo['etapa_1']['por_situacao']}; "
              f"etapa 2 {resumo['etapa_2']['por_situacao']}")
        return
    # O endereço do PostgreSQL de todos, lido do .env: rodar nele é recusado
    endereco_de_todos = dotenv_values(RAIZ / ".env").get("POSTGRES_URL")
    combinacoes.conferir_o_ambiente(opcoes.etapa, endereco_de_todos)
    # A etapa 1, sem custo
    if opcoes.etapa == 1:
        rodada = rodar_a_etapa_1(opcoes.limite)
    else:
        # A IA real só com o teto combinado
        if opcoes.teto_usd is None:
            sys.exit("A etapa 2 exige o teto em dólares: --teto-usd.")
        rodada = rodar_a_etapa_2(opcoes.teto_usd, opcoes.limite)
    # Quantas rodaram, quanto custou e por que parou (se parou)
    print(f"Feitas {rodada['feitas']} de {rodada['total']}; gasto US$ {rodada['gasto_usd']:.4f}; "
          f"parou: {rodada['parou_porque'] or 'não (fez todas)'}")


# Só roda quando chamado como script (e não ao ser importado pelos testes)
if __name__ == "__main__":
    main()
