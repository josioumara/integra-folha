"""Mede o tamanho de cada pedido à IA, para projetar o custo de cada provedor (ADR-11, docs/avaliacao.md).

O custo de um provedor é: tokens de entrada × preço de entrada + tokens de saída × preço de saída. O preço
está na página do provedor; os TOKENS dependem do nosso sistema. Este script mede isso de verdade: roda o
fluxo dos 9 arquivos e os pedidos do Endomarketing em modo MOCK e anota, para cada tipo de chamada, quantas
chamadas houve e quantos caracteres entraram e saíram.

Por que o MOCK serve: o pedido (entrada) é o mesmo que iria para a IA real, e o simulador responde no mesmo
contrato (saída), então o tamanho da resposta é uma boa estimativa. Tokens ≈ caracteres ÷ 4 é uma
aproximação: cada provedor conta tokens do seu jeito.

Roda num banco TEMPORÁRIO: o banco local não é tocado. Grava em data/avaliacao/resultados/tamanho_dos_pedidos.json.

Para rodar: python scripts/medir_tamanho_dos_pedidos.py   (antes: gerar_dados.py e build_index.py)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Antes de qualquer import do projeto: tudo temporário e sempre MOCK (a configuração é lida no import)
PASTA_TEMPORARIA = Path(tempfile.mkdtemp(prefix="tamanho_dos_pedidos_"))
os.environ["CAMINHO_BANCO"] = str(PASTA_TEMPORARIA / "avaliacao.db")
# Sempre num SQLite temporário, mesmo que o .env diga BANCO=postgres: a avaliação nunca toca no banco de uso
os.environ["BANCO"] = "sqlite"
os.environ["PASTA_UPLOADS"] = str(PASTA_TEMPORARIA / "uploads")
os.environ["PASTA_HOMOLOGADOS"] = str(PASTA_TEMPORARIA / "homologados")
os.environ["CAMINHO_CHECKPOINTS"] = str(PASTA_TEMPORARIA / "checkpoints.db")
os.environ["MODE"] = "mock"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval import avaliacao_do_endomarketing, avaliacao_do_fluxo  # noqa: E402
from services import auth, llm_client  # noqa: E402

# Onde o resultado é gravado
SAIDA = RAIZ / "data" / "avaliacao" / "resultados" / "tamanho_dos_pedidos.json"
# Aproximação usada para converter caracteres em tokens
CARACTERES_POR_TOKEN = 4

# O que foi medido, por tipo de chamada (tarefa): {"interpretar_colunas": {"chamadas": 9, ...}, ...}
medidas_por_tarefa = {}
# O método original do cliente de IA, guardado para ser chamado de dentro do medidor
gerar_sem_medir = llm_client.LLMClient.gerar


def gerar_medindo(cliente, tarefa, prompt, sistema="", modelo=None, temperatura=0.0):
    """Faz a chamada normal ao cliente de IA e anota o tamanho do pedido e da resposta."""
    resposta = gerar_sem_medir(cliente, tarefa, prompt, sistema, modelo, temperatura)
    # Primeira chamada desta tarefa: começa os contadores em zero
    if tarefa not in medidas_por_tarefa:
        medidas_por_tarefa[tarefa] = {"chamadas": 0, "caracteres_de_entrada": 0, "caracteres_de_saida": 0}
    medida = medidas_por_tarefa[tarefa]
    medida["chamadas"] += 1
    # Entrada = o papel do agente (sistema) + o pedido; saída = o texto que voltou
    medida["caracteres_de_entrada"] += len(sistema) + len(prompt)
    medida["caracteres_de_saida"] += len(resposta.texto)
    return resposta


def resumir() -> dict:
    """Por tarefa: chamadas, caracteres médios e tokens estimados por chamada."""
    resumo = {}
    for tarefa, medida in medidas_por_tarefa.items():
        chamadas = medida["chamadas"]
        entrada_media = medida["caracteres_de_entrada"] // chamadas
        saida_media = medida["caracteres_de_saida"] // chamadas
        resumo[tarefa] = {"chamadas": chamadas,
                          "caracteres_de_entrada_por_chamada": entrada_media,
                          "caracteres_de_saida_por_chamada": saida_media,
                          "tokens_de_entrada_estimados": entrada_media // CARACTERES_POR_TOKEN,
                          "tokens_de_saida_estimados": saida_media // CARACTERES_POR_TOKEN}
    return resumo


def main() -> dict:
    """Roda o fluxo e o Endomarketing medindo cada chamada à IA; grava e devolve o resumo."""
    # Troca o método do cliente de IA pelo medidor (só dentro deste script)
    llm_client.LLMClient.gerar = gerar_medindo
    # O fluxo dos 9 arquivos (o Interpretador só é chamado para colunas que não vêm de reuso)
    conexao_do_fluxo = sqlite3.connect(PASTA_TEMPORARIA / "fluxo.db", check_same_thread=False)
    avaliacao_do_fluxo.avaliar(conexao_do_fluxo)
    conexao_do_fluxo.close()
    # Os pedidos de material do Endomarketing (o banco precisa do catálogo inicial)
    conexao_do_endomarketing = auth.conectar(PASTA_TEMPORARIA / "endomarketing.db")
    avaliacao_do_endomarketing.avaliar(conexao_do_endomarketing)
    conexao_do_endomarketing.close()
    resultado = {"caracteres_por_token": CARACTERES_POR_TOKEN, "por_tarefa": resumir()}
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return resultado


if __name__ == "__main__":
    for nome_da_tarefa, dados in main()["por_tarefa"].items():
        print(f"{nome_da_tarefa}: {dados['chamadas']} chamadas | ~{dados['tokens_de_entrada_estimados']} tokens de "
              f"entrada e ~{dados['tokens_de_saida_estimados']} de saída por chamada")
