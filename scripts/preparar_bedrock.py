"""Prepara a conta da AWS para o projeto usar o Bedrock com retenção zero (ADR-96). Roda uma vez, depois da chave.

O que faz, em ordem:
1. liga a RETENÇÃO ZERO na conta, na região do .env ("none": a AWS não grava pedido nem resposta, e o fornecedor do
   modelo não recebe nada). É a segunda trava contra os modelos que guardam os pedidos: com ela ligada, o próprio
   Bedrock recusa qualquer modelo que exija guardar (a primeira trava fica no código, provedores_de_ia.py);
2. lê a configuração de volta, para confirmar que ficou gravada;
3. faz uma pergunta mínima a cada modelo do .env (MODELO_GRANDE e MODELO_PEQUENO), para provar que os dois funcionam
   com a retenção zero, e mostra o tempo, os tokens e o custo de cada um.

Precisa de: ROTA_DA_IA=bedrock, AWS_BEARER_TOKEN_BEDROCK e REGIAO_BEDROCK no .env. Custa centavos (duas perguntas).

Para rodar:
  python scripts/preparar_bedrock.py
"""
import sys
import time
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import httpx  # noqa: E402

from services import config, provedores_de_ia  # noqa: E402

# O modo de retenção que o projeto exige: "none" = nada gravado pela AWS, nada entregue ao fornecedor do modelo
RETENCAO_EXIGIDA = "none"


def endereco_da_retencao() -> str:
    """O endereço da configuração de retenção da conta, na região do .env (a API de controle do Bedrock)."""
    return "https://bedrock." + config.REGIAO_BEDROCK + ".amazonaws.com/data-retention"


def cabecalhos_da_chave() -> dict:
    """O cabeçalho que leva a chave do Bedrock (o mesmo jeito que a documentação da AWS mostra)."""
    return {"Authorization": "Bearer " + config.CHAVE_BEDROCK, "Content-Type": "application/json"}


def ligar_retencao_zero() -> dict:
    """Grava a retenção zero na conta e devolve o que a AWS respondeu. Levanta erro se a AWS recusar."""
    resposta = httpx.put(endereco_da_retencao(), headers=cabecalhos_da_chave(), json={"mode": RETENCAO_EXIGIDA},
                         timeout=30)
    # Erro da AWS (chave errada, sem permissão) sobe como está, com a mensagem dela
    resposta.raise_for_status()
    return resposta.json()


def ler_retencao() -> dict:
    """Lê a retenção gravada na conta (para confirmar que a gravação pegou)."""
    resposta = httpx.get(endereco_da_retencao(), headers=cabecalhos_da_chave(), timeout=30)
    resposta.raise_for_status()
    return resposta.json()


def perguntar_ao_modelo(modelo: str) -> None:
    """Uma pergunta mínima ao modelo, pelo Bedrock; mostra a resposta, o tempo, os tokens e o custo."""
    inicio = time.perf_counter()
    resposta = provedores_de_ia.chamar(modelo, "Responda em uma palavra.", "Qual é a capital do Brasil?", 0.0)
    segundos = round(time.perf_counter() - inicio, 1)
    custo = provedores_de_ia.custo_em_dolares(modelo, resposta.tokens_entrada, resposta.tokens_saida)
    print(f"  {provedores_de_ia.nome_do_modelo_na_rota(modelo)}: {resposta.texto.strip()!r} | {segundos} s | "
          f"tokens {resposta.tokens_entrada} + {resposta.tokens_saida} | US$ {custo:.5f}")


def main() -> None:
    """Confere o .env, liga a retenção zero, confirma e testa os dois modelos."""
    # Sem a rota e a chave, não há o que preparar
    if not provedores_de_ia.usa_o_bedrock():
        sys.exit("O .env precisa de ROTA_DA_IA=bedrock.")
    if not config.CHAVE_BEDROCK:
        sys.exit("O .env precisa de AWS_BEARER_TOKEN_BEDROCK (a chave criada no console da AWS).")
    print(f"Região: {config.REGIAO_BEDROCK} | perfil geográfico: {provedores_de_ia.PERFIL_GEOGRAFICO_DO_BEDROCK}")
    # 1 e 2: grava a retenção zero e lê de volta
    print("Retenção da conta, gravada:", ligar_retencao_zero())
    retencao = ler_retencao()
    print("Retenção da conta, lida de volta:", retencao)
    if retencao.get("mode") != RETENCAO_EXIGIDA:
        sys.exit(f"A retenção não ficou em {RETENCAO_EXIGIDA!r}: pare aqui e confira a conta.")
    # 3: os dois modelos do .env, com a retenção zero ligada
    print("Pergunta de teste a cada modelo:")
    for modelo in (config.MODELO_GRANDE, config.MODELO_PEQUENO):
        perguntar_ao_modelo(modelo)


if __name__ == "__main__":
    main()
