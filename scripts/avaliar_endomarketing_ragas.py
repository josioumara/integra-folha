"""Mede a fidelidade e a relevância dos materiais do Endomarketing com o RAGAS (as 3 etapas).

A lógica está em eval/ragas_do_endomarketing.py (preparar e julgar) e em eval/resumo_do_ragas.py (as tabelas e o
kappa); aqui ficam as etapas, os arquivos e a conferência do ambiente:
- preparar (.venv do projeto, numa CÓPIA do banco, MODE=mock): os materiais GERADOS do EXP-019 → as amostras
  (data/avaliacao/resultados/endomarketing_ragas_amostras.json) e a planilha dos 50 blocos para rotular
  (data/avaliacao/rotulos_fidelidade_endomarketing_50.xlsx; nunca regravada depois de ter rótulos);
- julgar (.venv-avaliacao, onde mora o RAGAS; IA real pelo Bedrock, MODE=llm e o teto em dólares): o CSV por bloco e
  o CSV por material;
- resumir (.venv do projeto, sem IA): data/avaliacao/resultados/endomarketing_ragas.json, com o kappa entre o juiz e
  os rótulos da planilha dos 50 quando ela já tiver os rótulos.
A cópia do banco é um banco de teste restaurado de um pg_dump (BANCO=postgres com o POSTGRES_URL dela): o script se
recusa a preparar no banco e no índice de todos. O juiz não abre o banco nem o índice.
Para rodar (PowerShell, na pasta do repositório; PASTA_MODELOS apontando para o modelo de embeddings já baixado):
  $env:MODE='mock'; python scripts/avaliar_endomarketing_ragas.py --etapa preparar
  $env:MODE='llm';  .venv-avaliacao\\Scripts\\python.exe scripts/avaliar_endomarketing_ragas.py --etapa julgar --teto-usd 1.8
  python scripts/avaliar_endomarketing_ragas.py --etapa resumir
"""
import argparse
import json
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
# O Python passa a achar os módulos do projeto (eval, services...) a partir da raiz
sys.path.insert(0, str(RAIZ))

from eval import ragas_do_endomarketing as ragas  # noqa: E402  (só importa o que vem com o Python: roda nos 2 ambientes)
from services import config  # noqa: E402  (só lê o .env: roda nos 2 ambientes)

# Os dois juízes que o script aceita (o principal e o reserva, os dois de outra família que o gerador)
JUIZES = (ragas.JUIZ_PRINCIPAL, ragas.JUIZ_RESERVA)
# De quantos em quantos materiais o progresso aparece na tela
AVISO_A_CADA = 5


def ler_opcoes() -> argparse.Namespace:
    """As opções da linha de comando."""
    leitor = argparse.ArgumentParser(description="A fidelidade e a relevância do Endomarketing, pelo RAGAS.")
    leitor.add_argument("--etapa", required=True, choices=("preparar", "julgar", "resumir"))
    leitor.add_argument("--teto-usd", type=float, dest="teto_usd", help="o teto em dólares do juiz (obrigatório)")
    leitor.add_argument("--juiz", choices=JUIZES, default=ragas.JUIZ_PRINCIPAL, help="o modelo do juiz")
    leitor.add_argument("--limite", type=int, help="só os N primeiros materiais (um ensaio antes da medição inteira)")
    return leitor.parse_args()


def _endereco_do_postgres_de_todos():
    """O POSTGRES_URL do .env (o banco de todos), lido direto do arquivo: o ambiente pode ter trocado o de uso."""
    # Importado aqui: só a etapa de preparar confere o banco
    from dotenv import dotenv_values
    return dotenv_values(RAIZ / ".env").get("POSTGRES_URL")


def preparar() -> None:
    """A etapa 1: as amostras e a planilha dos rótulos, numa cópia do banco e sem IA."""
    # Importados aqui: o módulo do EXP-019 e o login usam o banco (só no .venv do projeto)
    from eval import combinacoes_do_endomarketing as combinacoes
    from services import auth
    # A mesma conferência do EXP-019: nunca o banco nem o índice de todos, e sem IA (etapa 1 = MOCK)
    combinacoes.conferir_o_ambiente(1, _endereco_do_postgres_de_todos())
    conexao = auth.conectar()
    amostras = ragas.preparar(conexao)
    ragas.ARQUIVO_DAS_AMOSTRAS.write_text(json.dumps(amostras, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    blocos = 0
    conferem = 0
    for amostra in amostras:
        blocos += len(amostra["blocos"])
        if amostra["catalogo_confere"]:
            conferem += 1
    print(f"Amostras: {len(amostras)} materiais; {conferem} com o catálogo de hoje igual ao que a IA recebeu; "
          f"{blocos} blocos (com os títulos) → {ragas.ARQUIVO_DAS_AMOSTRAS.name}")
    # A planilha nunca é regravada depois que alguém rotulou (os rótulos se perderiam)
    if ragas.PLANILHA_DOS_50.exists() and ragas.ler_rotulos():
        print("A planilha dos rótulos já tem rótulos: ficou como estava.")
        return
    linhas = ragas.sortear_blocos_para_rotular(amostras)
    ragas.gravar_planilha_dos_rotulos(linhas)
    print(f"Planilha: {len(linhas)} blocos para rotular → {ragas.PLANILHA_DOS_50}")


class Progresso:
    """O progresso do juiz na tela: quantos materiais já foram medidos e quanto já custou.

    O juiz chama avisar() a cada material pronto. Exemplo de linha: "  5/86 materiais · gasto US$ 0.0450 · ...".
    """

    def __init__(self, caixa: ragas.CaixaDoGasto, total: int):
        """Recebe a caixa do gasto (para mostrar o gasto) e o total de materiais."""
        self.caixa = caixa
        self.total = total
        self.prontos = 0

    def avisar(self, resumo: dict) -> None:
        """Conta o material pronto e mostra o progresso de tempos em tempos (e no último)."""
        self.prontos += 1
        if self.prontos % AVISO_A_CADA == 0 or self.prontos == self.total:
            print(f"  {self.prontos}/{self.total} materiais · gasto US$ {self.caixa.gasto_usd:.4f} · "
                  f"{self.caixa.chamadas} chamadas · último: {resumo['combinacao']} ({resumo['situacao']})",
                  flush=True)


def julgar(teto_usd: float | None, modelo: str, limite: int | None) -> None:
    """A etapa 2: o juiz do RAGAS em cada bloco e em cada material, com a IA real e o teto."""
    # A IA real só com o modo pago escolhido de propósito e com o teto
    if config.MODO != "llm":
        sys.exit("O juiz usa a IA real: rode com MODE=llm (e o teto em dólares).")
    if not teto_usd or teto_usd <= 0:
        sys.exit("Informe o teto em dólares: --teto-usd.")
    amostras = json.loads(ragas.ARQUIVO_DAS_AMOSTRAS.read_text(encoding="utf-8"))
    # O ensaio: só os primeiros materiais
    if limite:
        amostras = amostras[:limite]
    caixa = ragas.CaixaDoGasto(teto_usd)
    # Os prompts em português (a tradução do próprio RAGAS roda uma vez só, com o mesmo juiz, e o gasto entra no teto)
    prompts = ragas.prompts_em_portugues(ragas.JuizDoBedrock(modelo, caixa))
    gasto_da_traducao = caixa.gasto_usd
    metricas = ragas.MetricasDoRagas(modelo, caixa, prompts)
    print(f"Juiz {modelo}, teto US$ {teto_usd:.2f}, {len(amostras)} materiais", flush=True)
    progresso = Progresso(caixa, len(amostras))
    blocos, materiais = ragas.julgar(amostras, metricas, avisar=progresso.avisar)
    ragas.gravar_csv(blocos, ragas.COLUNAS_DOS_BLOCOS, ragas.CSV_DOS_BLOCOS)
    ragas.gravar_csv(materiais, ragas.COLUNAS_DOS_MATERIAIS, ragas.CSV_DOS_MATERIAIS)
    # A situação de cada bloco, para ver de relance se houve erro ou teto
    situacoes = {}
    for bloco in blocos:
        situacoes[bloco["situacao"]] = situacoes.get(bloco["situacao"], 0) + 1
    print(f"Blocos: {situacoes}")
    print(f"Gasto do juiz: US$ {caixa.gasto_usd:.4f} ({caixa.chamadas} chamadas; a tradução dos prompts: "
          f"US$ {gasto_da_traducao:.4f})")


def resumir() -> None:
    """A etapa 3: as tabelas do EXP, com o kappa da planilha dos 50 (se já tem rótulos) e a conferência do agente."""
    # Importado aqui: só o resumo precisa das tabelas e do kappa
    from eval import resumo_do_ragas
    amostras = json.loads(ragas.ARQUIVO_DAS_AMOSTRAS.read_text(encoding="utf-8"))
    blocos = ragas.ler_csv(ragas.CSV_DOS_BLOCOS)
    materiais = ragas.ler_csv(ragas.CSV_DOS_MATERIAIS)
    # Os rótulos dos 50 blocos (de outro avaliador), quando a planilha existe
    rotulos_dos_50 = None
    if ragas.PLANILHA_DOS_50.exists():
        rotulos_dos_50 = ragas.ler_rotulos(ragas.PLANILHA_DOS_50)
    conferencia = None
    if ragas.ARQUIVO_DA_CONFERENCIA_DO_AGENTE.exists():
        conferencia = json.loads(ragas.ARQUIVO_DA_CONFERENCIA_DO_AGENTE.read_text(encoding="utf-8"))["casos"]
    resumo = resumo_do_ragas.resumir(amostras, blocos, materiais, rotulos_dos_50, conferencia)
    ragas.ARQUIVO_DO_RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    geral = resumo["geral"]
    print(f"Materiais medidos: {resumo['materiais_medidos']} de {resumo['materiais_do_exp_019']}")
    print(f"Fidelidade média {geral['fidelidade_media']} (IC 95% {resumo['fidelidade_media_ic95']}); "
          f"somada {geral['fidelidade_somada']}; ao catálogo {geral['fidelidade_ao_catalogo_media']}")
    print(f"Relevância média {geral['relevancia_media']} (IC 95% {resumo['relevancia_media_ic95']})")
    print(f"Afirmações {geral['afirmacoes']}: citadas errado {geral['citadas_errado']}, inventadas "
          f"{geral['inventadas']}")
    # O kappa entre o juiz e os 50 rótulos, quando a planilha já tem rótulos
    concordancia = resumo["concordancia_com_os_rotulos_dos_50"]
    if isinstance(concordancia, dict):
        print(f"Kappa os 50 rótulos × juiz: {concordancia['kappa']} ({concordancia['leitura']}), IC 95% "
              f"{concordancia['kappa_ic95']}, n = {concordancia['pares']}")
    print(f"→ {ragas.ARQUIVO_DO_RESUMO}")


def principal() -> None:
    """Roda a etapa pedida."""
    opcoes = ler_opcoes()
    if opcoes.etapa == "preparar":
        preparar()
    elif opcoes.etapa == "julgar":
        julgar(opcoes.teto_usd, opcoes.juiz, opcoes.limite)
    else:
        resumir()


if __name__ == "__main__":
    principal()
