"""Cópia de segurança do projeto: a pasta D:\\AI_Payroll_Hub e o banco PostgreSQL.

Para que serve: uma vez por dia, guardar tudo o que não dá para recriar numa pasta com data e hora
(ex.: G:\\Meu Drive\\ProjetoIA\\20260926_0730), que o Google Drive sobe para a nuvem.

O que vai e o que fica de fora:
- vai: o código (com o histórico do Git), a apresentação, os arquivos de teste, o layout, os bancos SQLite e uma
  cópia do banco PostgreSQL (pg_dump), quando a aplicação usa o PostgreSQL;
- fica de fora: o .env (segredos: ficam no gerenciador de senhas; o .env.example,
  que é o modelo, vai), os ambientes virtuais (.venv), os modelos baixados (storage/modelos), os índices do RAG
  (storage/indices, refeitos pelo scripts/build_index.py) e as pastas de cache.

Para rodar:
  .\\.venv\\Scripts\\python.exe scripts\\copia_de_seguranca.py              (copia para G:\\Meu Drive\\ProjetoIA)
  .\\.venv\\Scripts\\python.exe scripts\\copia_de_seguranca.py --simular    (só conta o que iria, sem copiar)
  .\\.venv\\Scripts\\python.exe scripts\\copia_de_seguranca.py --destino E:\\Copias
Para rodar sozinha todo dia: o Agendador de Tarefas do Windows (passo a passo no README, "Cópia de segurança").
"""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from services import config  # noqa: E402

# O que é copiado: a pasta de cima do repositório (D:\AI_Payroll_Hub)
ORIGEM = RAIZ.parent
# Para onde vai, sem informar outro destino
DESTINO_PADRAO = Path(r"G:\Meu Drive\ProjetoIA")
# Pastas que nunca vão (pelo nome, em qualquer lugar da árvore)
PASTAS_DE_FORA = {".venv", "venv_slides", "__pycache__", ".pytest_cache", "node_modules", "modelos", "indices"}
# Arquivos que nunca vão (pelo nome): os segredos
ARQUIVOS_DE_FORA = {".env"}
# Onde fica o pg_dump quando ele não está no caminho do sistema (a instalação do PostgreSQL 18 no Windows)
PG_DUMP_PADRAO = Path(r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe")


def fica_de_fora(nome: str, e_pasta: bool) -> bool:
    """True se o arquivo ou a pasta não entra na cópia.

    Ex.: (".env", False) → True; (".env.example", False) → False; (".venv", True) → True; ("front", True) → False.
    """
    if e_pasta:
        return nome in PASTAS_DE_FORA
    return nome in ARQUIVOS_DE_FORA or nome.endswith(".pyc")


def _ignorar(pasta: str, nomes: list[str]) -> list[str]:
    """Para o shutil.copytree: os nomes desta pasta que ficam de fora."""
    de_fora = []
    for nome in nomes:
        if fica_de_fora(nome, (Path(pasta) / nome).is_dir()):
            de_fora.append(nome)
    return de_fora


def contar(origem: Path) -> tuple[int, int]:
    """Quantos arquivos e quantos bytes iriam para a cópia (sem copiar nada)."""
    arquivos = 0
    tamanho = 0
    pendentes = [origem]
    while pendentes:
        pasta = pendentes.pop()
        for item in pasta.iterdir():
            if fica_de_fora(item.name, item.is_dir()):
                continue
            if item.is_dir():
                pendentes.append(item)
            else:
                arquivos += 1
                tamanho += item.stat().st_size
    return arquivos, tamanho


def copiar_banco_postgres(destino: Path) -> Path | None:
    """Uma cópia do banco PostgreSQL da aplicação (pg_dump, formato compacto). None se a aplicação usa o SQLite.

    A senha vai dentro do endereço de conexão lido do .env (nunca escrita em arquivo nenhum da cópia).
    """
    if config.BANCO != "postgres":
        return None
    programa = shutil.which("pg_dump") or str(PG_DUMP_PADRAO)
    arquivo_da_copia = destino / "banco_integra_folha.dump"
    subprocess.run([programa, "--format=custom", f"--dbname={config.POSTGRES_URL}", f"--file={arquivo_da_copia}"],
                   check=True)
    return arquivo_da_copia


def fazer_copia(origem: Path, destino_base: Path, agora: datetime | None = None) -> Path:
    """Copia a origem para destino_base\\AAAAMMDD_HHMM (sem o que fica de fora). Devolve a pasta criada."""
    momento = agora or datetime.now()
    pasta_da_copia = destino_base / momento.strftime("%Y%m%d_%H%M")
    shutil.copytree(origem, pasta_da_copia / origem.name, ignore=_ignorar)
    return pasta_da_copia


def main() -> None:
    """Lê as opções, copia (ou só conta) e diz o que foi feito."""
    leitor = argparse.ArgumentParser(description="Cópia de segurança do Integra Folha (sem o .env).")
    leitor.add_argument("--destino", default=str(DESTINO_PADRAO), help="pasta base da cópia")
    leitor.add_argument("--simular", action="store_true", help="só conta o que iria, sem copiar")
    opcoes = leitor.parse_args()
    arquivos, tamanho = contar(ORIGEM)
    print(f"copia_de_seguranca: {arquivos} arquivos, {tamanho / 1024 / 1024:.1f} MB (sem .env, .venv, modelos e "
          "índices)")
    if opcoes.simular:
        return
    pasta_da_copia = fazer_copia(ORIGEM, Path(opcoes.destino))
    print(f"copia_de_seguranca: pasta copiada para {pasta_da_copia}")
    copia_do_banco = copiar_banco_postgres(pasta_da_copia)
    if copia_do_banco is not None:
        print(f"copia_de_seguranca: banco PostgreSQL copiado em {copia_do_banco}")


if __name__ == "__main__":
    main()
