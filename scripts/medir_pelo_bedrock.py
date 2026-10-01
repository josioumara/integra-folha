"""Mede modelos pelo AWS Bedrock, na mesma prova congelada da comparação de modelos (ADR-96 e ADR-106).

Para que serve: comparar modelos pelo Bedrock com a MESMA régua das APIs diretas. Cada modelo interpreta as MESMAS
30 planilhas, na MESMA configuração (B3, com RAG), da comparação feita pelas APIs diretas
(data/avaliacao/resultados/comparacao_modelos.json). O código da comparação é o congelado
(eval/comparacao_de_modelos.py), usado sem mudar uma linha: este script só escolhe os modelos, mede todos AO MESMO
TEMPO (um por trilha) e grava o resultado num arquivo à parte.

Dois usos:
- sem --modelos: os dois modelos do .env (MODELO_GRANDE e MODELO_PEQUENO), no arquivo comparacao_modelos_bedrock.json;
- com --modelos: o plano B (ADR-106), ex.: os modelos que a conta libera enquanto o Sonnet 5 e o GPT-6 Luna não
  chegam, no arquivo comparacao_plano_b_bedrock.json.

Acompanhamento: cada modelo escreve no terminal as planilhas feitas e o gasto, a cada planilha, e o resultado final.

Precisa de: ROTA_DA_IA=bedrock (no .env ou no terminal) e AWS_BEARER_TOKEN_BEDROCK no .env, e os índices do RAG.
Custa dinheiro: cada modelo tem o próprio teto (--teto-por-modelo); a soma dos tetos nunca passa do teto da sessão.

Para rodar:
  python scripts/medir_pelo_bedrock.py
  python scripts/medir_pelo_bedrock.py --modelos claude-sonnet-4-6,claude-haiku-4-5,nova-pro,nova-2-lite
"""
import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agents import interpretador  # noqa: E402
from eval.comparacao_de_modelos import (FalhaDoProvedor, carregar_amostra, carregar_prova, medir_b0,  # noqa: E402
                                        medir_modelo)
from eval.congelamento import exigir_prova_congelada  # noqa: E402
from models.contratos import carregar_layout  # noqa: E402
from rag.busca import indice_disponivel, search_rules  # noqa: E402
from services import config, provedores_de_ia  # noqa: E402

# Onde fica o resultado dos modelos do .env (ao lado do resultado das APIs diretas, para comparar)
CAMINHO_DO_RESULTADO = RAIZ / "data" / "avaliacao" / "resultados" / "comparacao_modelos_bedrock.json"
# Onde fica o resultado do plano B (os modelos passados em --modelos)
CAMINHO_DO_PLANO_B = RAIZ / "data" / "avaliacao" / "resultados" / "comparacao_plano_b_bedrock.json"
# O teto padrão de cada modelo, em dólares (o Sonnet 4.6, o mais caro do plano B, fica perto de US$ 2)
TETO_PADRAO_POR_MODELO = 2.5
# Só uma trilha grava o arquivo de resultado por vez (as trilhas rodam ao mesmo tempo)
TRAVA_DO_RESULTADO = threading.Lock()
# Quantas planilhas cada modelo já fez, para o progresso no terminal: {"nova-pro": 12, ...}
PLANILHAS_FEITAS = {}
# O nome de cada modelo no Bedrock (o que a conta mostra), para a linha do progresso
NOME_NO_BEDROCK = {}
# Quantas planilhas cada modelo vai fazer (as mesmas 30 para todos)
TOTAL_DE_PLANILHAS = {"valor": 0}
# A função original do Interpretador, guardada antes de ser envolvida pelo contador de progresso
INTERPRETAR_ORIGINAL = interpretador.interpretar


def ler_opcoes() -> argparse.Namespace:
    """As opções da linha de comando: os modelos e o teto de gasto de cada um."""
    leitor = argparse.ArgumentParser(description="Modelos pelo Bedrock, na prova congelada, em paralelo.")
    leitor.add_argument("--modelos", default="", help="nomes separados por vírgula (sem isso: os dois do .env)")
    leitor.add_argument("--teto-por-modelo", type=float, default=TETO_PADRAO_POR_MODELO,
                        help="teto de gasto de cada modelo, em dólares")
    leitor.add_argument("--planilhas", type=int, default=0,
                        help="só as N primeiras planilhas da amostra (triagem); sem isso, as 30")
    leitor.add_argument("--saida", default="",
                        help="arquivo do resultado, relativo à raiz (para duas medições rodarem ao mesmo tempo)")
    leitor.add_argument("--juntar", action="store_true",
                        help="mantém os modelos já medidos no arquivo e junta os novos (para refazer só alguns)")
    return leitor.parse_args()


def resultado_inicial(caminho: Path, juntar: bool, planilhas: list, teto_por_modelo: float) -> dict:
    """O resultado onde as medidas vão entrar: novo ou, com juntar, o que já está no arquivo.

    Juntar serve para refazer só alguns modelos (ex.: os que caíram) sem perder o que os outros já mediram e pagaram.
    """
    if juntar and caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    resultado = {"rota": "bedrock", "perfil_geografico": provedores_de_ia.PERFIL_GEOGRAFICO_DO_BEDROCK,
                 "regiao": config.REGIAO_BEDROCK, "configuracao": "B3", "planilhas": len(planilhas),
                 "formato_garantido": config.INTERPRETADOR_FORMATO_GARANTIDO,
                 "teto_por_modelo_usd": teto_por_modelo, "gasto_usd": 0.0, "modelos": {}}
    # O dicionário sem IA, como régua (de graça)
    resultado["b0"] = medir_b0(planilhas)
    return resultado


def modelos_escolhidos(opcoes: argparse.Namespace) -> list[str]:
    """Os modelos a medir: os de --modelos ou, sem a opção, os dois do .env."""
    if not opcoes.modelos:
        return [config.MODELO_GRANDE, config.MODELO_PEQUENO]
    # "a, b,c" → ["a", "b", "c"], sem espaços e sem itens vazios
    modelos = []
    for nome in opcoes.modelos.split(","):
        if nome.strip():
            modelos.append(nome.strip())
    return modelos


def gravar_resultado(caminho: Path, resultado: dict) -> None:
    """Grava o resultado (depois de cada modelo, para não perder o que já foi pago se parar no meio)."""
    # Uma trilha de cada vez, para uma não gravar por cima da outra pela metade
    with TRAVA_DO_RESULTADO:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


# ---------------- Formato garantido na comparação congelada ----------------

class MedidorComFormato:
    """Deixa o medidor da comparação congelada repassar o esquema da resposta (formato garantido, ADR-107).

    Por que existe: o medidor congelado (eval/comparacao_de_modelos.py, ClienteSemDisfarce) é anterior ao formato
    garantido e não aceita o parâmetro do esquema. Este adaptador faz exatamente o que ele faz (mede o tempo e os
    tokens e recusa resposta simulada) e, além disso, repassa o esquema ao cliente de IA. Só entra com
    INTERPRETADOR_FORMATO_GARANTIDO=sim.
    """

    def __init__(self, medidor):
        """medidor: o ClienteSemDisfarce criado pela comparação (é nele que as medidas ficam guardadas)."""
        self.medidor = medidor
        # O cliente de IA de verdade (a comparação lê dele o gasto)
        self.cliente = medidor.cliente

    def gerar(self, tarefa, prompt, sistema="", modelo=None, temperatura=0.0, esquema_json=None):
        """Repassa a chamada com o esquema e soma o tempo e os tokens no medidor congelado."""
        inicio = time.perf_counter()
        resposta = self.medidor.cliente.gerar(tarefa, prompt, sistema, modelo, temperatura, esquema_json=esquema_json)
        self.medidor.segundos += time.perf_counter() - inicio
        # Resposta simulada não entra na medição (a mesma regra do medidor congelado)
        if resposta.modo != "llm":
            raise FalhaDoProvedor(resposta.motivo_fallback or "resposta não veio do provedor")
        self.medidor.tokens_entrada += resposta.tokens_entrada or 0
        self.medidor.tokens_saida += resposta.tokens_saida or 0
        return resposta


# ---------------- Progresso no terminal ----------------

def interpretar_contando(perfil, campos, versao_layout, cliente, **opcoes_do_interpretador):
    """Chama o Interpretador de verdade e, depois, escreve no terminal que mais uma planilha daquele modelo terminou.

    Por que existe: o código da comparação é congelado (não pode mudar nem para mostrar progresso). Então este
    script troca, só enquanto roda, a função que a comparação chama por esta, que faz a mesma coisa e ainda conta.
    O "cliente" aqui é o medidor da comparação: ele sabe quanto o modelo já gastou.
    """
    # Com o formato garantido ligado, o medidor congelado ganha o adaptador que repassa o esquema
    cliente_da_chamada = cliente
    if config.INTERPRETADOR_FORMATO_GARANTIDO:
        cliente_da_chamada = MedidorComFormato(cliente)
    plano = INTERPRETAR_ORIGINAL(perfil, campos, versao_layout, cliente_da_chamada, **opcoes_do_interpretador)
    modelo = opcoes_do_interpretador["modelo"]
    PLANILHAS_FEITAS[modelo] = PLANILHAS_FEITAS.get(modelo, 0) + 1
    # Uma linha por planilha: o modelo, quantas já foram e quanto ele já gastou
    print(f"{NOME_NO_BEDROCK[modelo]}: {PLANILHAS_FEITAS[modelo]}/{TOTAL_DE_PLANILHAS['valor']} planilhas "
          f"(B3, com RAG) · gasto US$ {cliente.cliente.gasto_usd:.4f}", flush=True)
    return plano


def estado_final_da_trilha(medida: dict) -> tuple[str, str]:
    """O estado e o texto da linha final do modelo. Ex.: completo → ("feito", "acurácia 84,4% ...")."""
    # Sem planilha pontuada (ex.: modelo fora da conta), não há acurácia para mostrar
    if "acuracia_por_campo" not in medida:
        return "erro", medida["situacao"]
    texto = (f"acurácia por campo {medida['acuracia_por_campo']:.1%} · {medida['segundos_por_planilha']} s por "
             f"planilha · {medida['situacao']}")
    if medida["situacao"] != "completo":
        return "erro", texto
    return "feito", texto


# ---------------- A medição ----------------

def medir_um_modelo(nome_do_modelo: str, planilhas: list, campos: list, teto: float, caminho: Path,
                    resultado: dict) -> None:
    """Mede um modelo (uma trilha) e grava a medida dele no resultado comum."""
    print(f"{NOME_NO_BEDROCK[nome_do_modelo]}: começando ({len(planilhas)} planilhas)", flush=True)
    modelo = {"provedor": "AWS Bedrock (perfil EUA)", "modelo": nome_do_modelo}
    medida = medir_modelo(modelo, planilhas, campos, teto)
    # A linha final mostra o resultado (ou o motivo de não ter medido)
    estado, texto = estado_final_da_trilha(medida)
    print(f"{NOME_NO_BEDROCK[nome_do_modelo]}: {estado} · {medida['planilhas_pontuadas']}/{len(planilhas)} planilhas "
          f"· {texto} · US$ {medida['custo_usd']:.4f}", flush=True)
    resultado["modelos"][nome_do_modelo] = medida
    resultado["gasto_usd"] = round(resultado["gasto_usd"] + medida["custo_usd"], 4)
    gravar_resultado(caminho, resultado)


def abrir_o_indice_antes_das_trilhas() -> None:
    """Faz uma busca no RAG antes de as trilhas começarem, para o índice ser aberto uma vez só.

    Por que existe: o banco dos índices (ChromaDB) se prepara na primeira abertura. Com 8 trilhas abrindo ao mesmo
    tempo pela primeira vez, algumas recebem "Could not connect to tenant" (visto na medição pelo Bedrock). Aberto
    antes, as trilhas só reaproveitam.
    """
    search_rules("CPF")


def conferir_antes_de_gastar(modelos: list[str], teto_por_modelo: float) -> None:
    """Para antes de gastar se faltar algo: rota, chave, prova congelada, índice ou teto da sessão."""
    # Esta medição é só da rota Bedrock
    if not provedores_de_ia.usa_o_bedrock():
        sys.exit("Use ROTA_DA_IA=bedrock (no .env ou no terminal).")
    if not config.CHAVE_BEDROCK:
        sys.exit("O .env precisa de AWS_BEARER_TOKEN_BEDROCK.")
    # A soma dos tetos dos modelos não pode passar do teto da sessão
    if teto_por_modelo * len(modelos) > config.TETO_DE_GASTO_USD:
        sys.exit(f"{len(modelos)} modelos × US$ {teto_por_modelo} passa do teto da sessão "
                 f"(US$ {config.TETO_DE_GASTO_USD}): diminua --teto-por-modelo.")
    # A prova, a amostra e as métricas têm de estar como foram congeladas (ADR-58)
    exigir_prova_congelada()
    # O B3 usa o RAG: sem o índice, a medição seria de outra configuração
    if not indice_disponivel():
        sys.exit("Monte os índices antes: python scripts/build_index.py")


def main() -> dict:
    """Confere tudo, mede os modelos ao mesmo tempo (um por trilha) e devolve o resultado."""
    opcoes = ler_opcoes()
    modelos = modelos_escolhidos(opcoes)
    conferir_antes_de_gastar(modelos, opcoes.teto_por_modelo)
    # O plano B grava em arquivo próprio, para não misturar com a medição dos modelos do .env
    caminho = CAMINHO_DO_RESULTADO
    if opcoes.modelos:
        caminho = CAMINHO_DO_PLANO_B
    # Um arquivo escolhido na linha de comando vale mais que os dois padrões
    if opcoes.saida:
        caminho = RAIZ / opcoes.saida
    # As mesmas 30 planilhas da comparação pelas APIs diretas, na mesma ordem
    prova = carregar_prova()
    planilhas = []
    for identificador in carregar_amostra():
        planilhas.append(prova[identificador])
    # Triagem: só as primeiras N da amostra (sempre as mesmas, na mesma ordem)
    if opcoes.planilhas:
        planilhas = planilhas[:opcoes.planilhas]
    campos = carregar_layout()
    resultado = resultado_inicial(caminho, opcoes.juntar, planilhas, opcoes.teto_por_modelo)
    # Prepara o progresso: o nome de cada modelo no Bedrock e o total de planilhas
    TOTAL_DE_PLANILHAS["valor"] = len(planilhas)
    for nome_do_modelo in modelos:
        NOME_NO_BEDROCK[nome_do_modelo] = provedores_de_ia.nome_do_modelo_na_rota(nome_do_modelo)
    abrir_o_indice_antes_das_trilhas()
    # Enquanto roda, a comparação chama o Interpretador pelo contador de progresso
    interpretador.interpretar = interpretar_contando
    # Um modelo por trilha, todos ao mesmo tempo
    with ThreadPoolExecutor(max_workers=len(modelos)) as executor:
        trilhas = []
        for nome_do_modelo in modelos:
            trilhas.append(executor.submit(medir_um_modelo, nome_do_modelo, planilhas, campos,
                                           opcoes.teto_por_modelo, caminho, resultado))
        # Espera todas; um erro inesperado numa trilha aparece aqui, em vez de sumir
        for trilha in trilhas:
            trilha.result()
    interpretador.interpretar = INTERPRETAR_ORIGINAL
    gravar_resultado(caminho, resultado)
    return resultado


if __name__ == "__main__":
    resultado_final = main()
    print(f"Gasto: US$ {resultado_final['gasto_usd']:.2f}")
    print(f"  B0 (sem IA): acurácia por campo {resultado_final['b0']['acuracia_por_campo']:.1%}")
    # Uma linha por modelo, com as mesmas medidas da comparação pelas APIs diretas
    for nome, medida_do_modelo in resultado_final["modelos"].items():
        if "acuracia_por_campo" in medida_do_modelo:
            print(f"  {nome}: acurácia por campo {medida_do_modelo['acuracia_por_campo']:.1%} | abstenção "
                  f"{medida_do_modelo['abstencao_recall']:.1%} | US$ {medida_do_modelo['custo_usd']:.2f} | "
                  f"{medida_do_modelo['segundos_por_planilha']} s por planilha | {medida_do_modelo['situacao']}")
        else:
            print(f"  {nome}: {medida_do_modelo['situacao']}")
