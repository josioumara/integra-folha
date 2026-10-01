"""Prepara o banco de TESTE para ver a faixa salarial por profissão (CBO) funcionando (ADR-129).

Para que serve: o servidor de teste do pedido (porta 8040) usa um banco SQLite só dele. Este script põe nele:
1. os usuários de teste (teste.empresa, RH da Aurora, e teste.banco, o especialista), os mesmos dos roteiros de clique;
2. o campo "codigo_cbo" no parâmetro do layout (a comparação por profissão liga com ele), como o especialista faria na
   tela Parâmetros;
3. duas OUTRAS empresas (Horizonte, EMP002, e Brisa, EMP003) com 10 pedreiros (CBO 7152-10) já cadastrados cada
   uma, com salários sintéticos entre 30% e 40% do caminho da faixa pública. Assim a faixa das outras
   empresas aparece no alerta da Aurora (arquivo 08 de Imports_Arquivos_CBO).

Segurança: só roda com BANCO=sqlite. Nunca grava no PostgreSQL de todos (o banco de verdade só muda na junção).

Como rodar (com as mesmas variáveis do servidor de teste: BANCO=sqlite e CAMINHO_BANCO=<o banco de teste>):
    .venv\\Scripts\\python.exe scripts\\preparar_demo_faixas_cbo.py
"""
import os
import random
import sys
from decimal import Decimal
from pathlib import Path

# Pasta raiz do projeto, para importar os serviços
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from services import auth, faixa_salarial_cbo, processamentos  # noqa: E402
from services.documentos import gerar_cpf  # noqa: E402
from tests.e2e import apoio  # noqa: E402

# As outras empresas preparadas e a profissão delas
OUTRAS_EMPRESAS = ("EMP002", "EMP003")
CARGO_DAS_OUTRAS, CODIGO_DAS_OUTRAS = "Pedreiro", "715210"
PESSOAS_POR_EMPRESA = 10
# O sorteio sempre com a mesma semente (rodar de novo dá os mesmos salários)
SEMENTE = 1290


def usuarios_de_teste(conexao) -> None:
    """Cria teste.empresa e teste.banco, se ainda não existem."""
    existe = conexao.execute("SELECT COUNT(*) FROM usuarios WHERE login = ?", (apoio.LOGIN_DA_EMPRESA,)).fetchone()[0]
    if not existe:
        apoio.criar_usuarios_de_teste(conexao)


def salarios_das_outras(conexao, sorteio: random.Random) -> list[Decimal]:
    """Os salários sintéticos de uma empresa: entre 30% e 40% do caminho entre o mínimo e o máximo públicos."""
    faixa = faixa_salarial_cbo.faixa_em_uso(conexao, CODIGO_DAS_OUTRAS)
    largura = faixa.maximo - faixa.minimo
    salarios = []
    for _ in range(PESSOAS_POR_EMPRESA):
        parte = Decimal(str(sorteio.uniform(0.30, 0.40)))
        salarios.append((faixa.minimo + largura * parte).quantize(Decimal("0.01")))
    return salarios


def cadastrar_as_outras_empresas(conexao) -> None:
    """As pessoas já cadastradas (homologadas) das outras empresas e a profissão do cargo delas."""
    processamentos._preparar(conexao)
    sorteio = random.Random(SEMENTE)
    for empresa in OUTRAS_EMPRESAS:
        for salario in salarios_das_outras(conexao, sorteio):
            conexao.execute("INSERT INTO funcionarios_homologados (empresa_id, cpf, processamento_id, homologado_em, "
                            "matricula, cargo, tipo_renda, valor_renda) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT (empresa_id, cpf) DO NOTHING",
                            (empresa, gerar_cpf(sorteio), "demo-faixas-cbo", "2026-09-01", "", CARGO_DAS_OUTRAS, "CLT",
                             str(salario)))
        faixa_salarial_cbo._gravar_profissao(conexao, empresa, CARGO_DAS_OUTRAS, CODIGO_DAS_OUTRAS,
                                             faixa_salarial_cbo.ORIGEM_ARQUIVO, "demo-faixas-cbo", None,
                                             substituir=False)
    conexao.commit()


if __name__ == "__main__":
    # Os acentos saem certos no terminal do Windows
    sys.stdout.reconfigure(encoding="utf-8")
    if os.environ.get("BANCO") != "sqlite" or not os.environ.get("CAMINHO_BANCO"):
        sys.exit("Só roda no banco de teste: defina BANCO=sqlite e CAMINHO_BANCO=<arquivo do banco de teste>.")
    conexao = auth.conectar()
    usuarios_de_teste(conexao)
    versao = faixa_salarial_cbo.ligar_o_campo_do_cbo(conexao, apoio.LOGIN_DO_BANCO)
    faixa_salarial_cbo._preparar(conexao)
    cadastrar_as_outras_empresas(conexao)
    conexao.close()
    print(f"Pronto: usuários de teste, parâmetro v{versao} com o campo codigo_cbo e as outras empresas "
          f"({', '.join(OUTRAS_EMPRESAS)}) com {PESSOAS_POR_EMPRESA} pessoas cada.")
