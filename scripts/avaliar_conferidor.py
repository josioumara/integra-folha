"""Roda o experimento EXP-015: o Conferidor da Leitura acha os erros de entendimento plantados? (ADR-105)

Como: nos documentos Word em texto corrido do EXP-010 (níveis N3 a N5), a "leitura" de cada pessoa é o gabarito
(o valor certo), e o script PLANTA erros de entendimento em algumas pessoas, sempre com valores que existem no
documento (a regra "o valor está no documento" não pegaria nenhum deles):
    - datas trocadas: a admissão no lugar do nascimento, e o contrário;
    - CPF de outra pessoa do mesmo documento;
    - salário de outra pessoa do mesmo documento.
O conferidor recebe o texto do documento e a leitura com os erros, e o script mede:
    - quantos erros plantados ele achou (acerto, "recall");
    - quantas suspeitas caíram em valores certos (alarme falso);
    - custo e tempo.
A decisão de ligar o conferidor (CONFERIDOR_DA_LEITURA=sim) sai desses números. Registrar o experimento no histórico
é um passo à parte, depois de ler os números (ADR-66).

Custa dinheiro quando o .env está em MODE=llm (uma chamada ao modelo pequeno por documento). Em MOCK, é só um ensaio
do caminho (o conferidor simulado não desconfia de nada). Os documentos são 100% fictícios.

Uso:
  python scripts/avaliar_conferidor.py --conjunto prova
  python scripts/avaliar_conferidor.py --conjunto desenvolvimento --documentos N5_texto_misturado_a
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agents import conferidor_da_leitura  # noqa: E402
from models.contratos import carregar_layout  # noqa: E402
from scripts.gerar_documentos_de_teste import pasta_do_conjunto  # noqa: E402
from eval.congelamento import exigir_prova_congelada  # noqa: E402
from services import config, leitura_de_word  # noqa: E402

PASTA_DOS_RESULTADOS = RAIZ / "data" / "avaliacao" / "resultados"
# As armadilhas (ADR-131): documentos com distrações em que a leitura está certa, e alguns com o erro de verdade
CAMINHO_DAS_ARMADILHAS = RAIZ / "data" / "avaliacao" / "conferidor_armadilhas.json"
# Os níveis em texto corrido (os que a IA lê)
NIVEIS_DE_TEXTO_CORRIDO = ("N3", "N4", "N5")
# Em quantas pessoas de cada documento um erro é plantado
PESSOAS_COM_ERRO_POR_DOCUMENTO = 3
# A semente do sorteio: os mesmos erros a cada execução (a comparação entre execuções é justa)
SEMENTE = 12
# Os tipos de erro plantado
TIPOS_DE_ERRO = ("datas_trocadas", "cpf_de_outra_pessoa", "salario_de_outra_pessoa")


def ler_opcoes() -> argparse.Namespace:
    """O conjunto, os documentos e as repetições a rodar (sem informar, todos os de texto corrido, uma vez)."""
    leitor = argparse.ArgumentParser(description="Experimento do Conferidor da Leitura: acha os erros sem alarme falso?")
    leitor.add_argument("--conjunto", default="desenvolvimento", help="desenvolvimento, prova ou armadilhas")
    leitor.add_argument("--documentos", default="", help="nomes dos documentos, separados por vírgula (sem .docx)")
    leitor.add_argument("--repeticoes", type=int, default=1, help="quantas vezes rodar tudo (consistência)")
    leitor.add_argument("--saida", default="", help="onde gravar (padrão: resultados/conferidor_<conjunto>.json)")
    return leitor.parse_args()


def texto_do_documento(conteudo: bytes) -> str:
    """O texto do Word, um parágrafo por linha (o mesmo que o Leitor recebe)."""
    documento = leitura_de_word._abrir(conteudo)
    return "\n".join(leitura_de_word._paragrafos(documento))


def plantar_erro(pessoas: list[dict], posicao: int, tipo: str) -> list[str]:
    """Planta um erro na pessoa da posição (alterando a lista). Devolve os campos que ficaram errados ([] se não deu).

    Todo valor plantado existe no documento: vem da própria pessoa (datas trocadas) ou de outra pessoa.
    """
    pessoa = pessoas[posicao]
    if tipo == "datas_trocadas":
        if pessoa.get("data_admissao") and pessoa.get("data_nascimento"):
            pessoa["data_admissao"], pessoa["data_nascimento"] = pessoa["data_nascimento"], pessoa["data_admissao"]
            return ["data_admissao", "data_nascimento"]
        return []
    campo = "cpf" if tipo == "cpf_de_outra_pessoa" else "valor_renda"
    for outra in pessoas:
        # O valor de outra pessoa, diferente do desta
        if outra is not pessoa and outra.get(campo) and outra.get(campo) != pessoa.get(campo) and pessoa.get(campo):
            pessoa[campo] = outra[campo]
            return [campo]
    return []


def qualidade_da_pergunta(pergunta: str) -> dict:
    """Confere, por regra, se a pergunta que a empresa vê é simples (ADR-131).

    Recebe o texto final da pergunta (o que vai para o cartão). Devolve cada conferência e "simples" (todas passaram):
    - sem_jargao: não fala em "segunda IA" nem em "desconfia" (a empresa não precisa saber quem conferiu);
    - termina_com_interrogacao: é uma pergunta, e não uma ordem;
    - uma_pergunta_so: só um ponto de interrogação;
    - curta: até 200 caracteres.
    Ex.: "O salário de Ana é R$ 3.000,00 ou R$ 650,00?" → simples.
    """
    texto_minusculo = pergunta.lower()
    conferencias = {"sem_jargao": "segunda ia" not in texto_minusculo and "desconfia" not in texto_minusculo,
                    "termina_com_interrogacao": pergunta.strip().endswith("?"),
                    "uma_pergunta_so": pergunta.count("?") == 1,
                    "curta": len(pergunta) <= 200}
    conferencias["simples"] = all(conferencias.values())
    return conferencias


def descrever_suspeitas(suspeitas: list) -> tuple[set, list[dict], int]:
    """As suspeitas em três formas: {(pessoa, campo)}, a lista com a pergunta final e quantas perguntas são simples."""
    apontados = set()
    perguntas = []
    simples = 0
    for suspeita in suspeitas:
        apontados.add((suspeita.pessoa, suspeita.campo))
        # A pergunta como a empresa vê no cartão
        pergunta = conferidor_da_leitura.pergunta_da_suspeita(suspeita)
        qualidade = qualidade_da_pergunta(pergunta)
        if qualidade["simples"]:
            simples += 1
        perguntas.append({"pessoa": suspeita.pessoa, "campo": suspeita.campo, "pergunta": pergunta,
                          "qualidade": qualidade})
    return apontados, perguntas, simples


def medir_documento(documento: dict, texto: str, campos, cliente, sorteio: random.Random) -> dict:
    """Planta os erros num documento, chama o conferidor e mede. Devolve a medida do documento."""
    pessoas = []
    for pessoa in documento["pessoas"]:
        pessoas.append(dict(pessoa["campos"]))
    # Os erros plantados: {(posição da pessoa, 1 = primeira, campo)}
    plantados = set()
    posicoes = sorteio.sample(range(len(pessoas)), min(PESSOAS_COM_ERRO_POR_DOCUMENTO, len(pessoas)))
    for numero, posicao in enumerate(posicoes):
        tipo = TIPOS_DE_ERRO[numero % len(TIPOS_DE_ERRO)]
        for campo in plantar_erro(pessoas, posicao, tipo):
            plantados.add((posicao + 1, campo))
    return chamar_e_comparar(texto, pessoas, plantados, campos, cliente)


def medir_armadilha(documento: dict, campos, cliente) -> dict:
    """Um documento do conjunto de armadilhas: a leitura vem pronta, com os erros de verdade anotados."""
    errados = set()
    for erro in documento["erros"]:
        errados.add((erro["pessoa"], erro["campo"]))
    medida = chamar_e_comparar(documento["texto"], documento["pessoas"], errados, campos, cliente)
    medida["distracao"] = documento["distracao"]
    return medida


def chamar_e_comparar(texto: str, pessoas: list[dict], errados: set, campos, cliente) -> dict:
    """Chama o conferidor e compara as suspeitas com os valores errados de verdade.

    Devolve: plantados (os errados), achados, alarmes falsos (suspeita num valor certo), o custo, o tempo, as perguntas
    e se o documento saiu "certo" (achou todos os errados e nenhum alarme falso).
    """
    inicio = time.time()
    suspeitas, resposta = conferidor_da_leitura.conferir(texto, pessoas, campos, cliente)
    segundos = time.time() - inicio
    apontados, perguntas, simples = descrever_suspeitas(suspeitas)
    custo = 0
    if resposta is not None and resposta.custo_usd:
        custo = resposta.custo_usd
    achados = len(errados & apontados)
    alarmes_falsos = len(apontados - errados)
    certo = achados == len(errados) and alarmes_falsos == 0
    return {"plantados": len(errados), "achados": achados, "alarmes_falsos": alarmes_falsos,
            "suspeitas": len(apontados), "perguntas_simples": simples, "certo": certo, "custo_usd": custo,
            "segundos": round(segundos, 1), "perguntas": perguntas}


def documentos_de_texto_corrido(opcoes: argparse.Namespace) -> list[dict]:
    """Os documentos Word do conjunto (desenvolvimento ou prova), com o texto já lido: [{"nome", "nivel", ...}]."""
    pasta = pasta_do_conjunto(opcoes.conjunto)
    gabarito = json.loads((pasta / "gabarito.json").read_text(encoding="utf-8"))
    escolhidos = []
    for nome in opcoes.documentos.split(","):
        if nome:
            escolhidos.append(nome)
    documentos = []
    for documento in gabarito["documentos"]:
        nome = documento["arquivo"].removesuffix(".docx")
        if documento["nivel"] not in NIVEIS_DE_TEXTO_CORRIDO or (escolhidos and nome not in escolhidos):
            continue
        texto = texto_do_documento((pasta / documento["arquivo"]).read_bytes())
        documentos.append({"nome": nome, "nivel": documento["nivel"], "texto": texto, "gabarito": documento})
    return documentos


def documentos_das_armadilhas() -> list[dict]:
    """Os documentos do conjunto de armadilhas (congelado antes de medir; ADR-58)."""
    exigir_prova_congelada()
    dados = json.loads(CAMINHO_DAS_ARMADILHAS.read_text(encoding="utf-8"))
    return dados["documentos"]


def rodar_uma_vez(opcoes: argparse.Namespace, documentos: list[dict], campos, cliente) -> list[dict]:
    """Uma repetição: mede cada documento e devolve [{"documento", "medida"}]."""
    # O sorteio recomeça a cada repetição: os mesmos erros plantados em todas (comparação pareada)
    sorteio = random.Random(SEMENTE)
    resultados = []
    for documento in documentos:
        if opcoes.conjunto == "armadilhas":
            medida = medir_armadilha(documento, campos, cliente)
        else:
            medida = medir_documento(documento["gabarito"], documento["texto"], campos, cliente, sorteio)
        resultados.append({"documento": documento["nome"], "medida": medida})
        print(f"  {documento['nome']}: achou {medida['achados']}/{medida['plantados']} · alarmes falsos "
              f"{medida['alarmes_falsos']} · perguntas simples {medida['perguntas_simples']}/{medida['suspeitas']} · "
              f"US$ {medida['custo_usd']:.4f}")
    return resultados


def resumir(resultados: list[dict]) -> dict:
    """As somas de uma repetição, com o acerto (achados ÷ errados)."""
    resumo = {"plantados": 0, "achados": 0, "alarmes_falsos": 0, "suspeitas": 0, "perguntas_simples": 0,
              "documentos_certos": 0, "custo_usd": 0.0}
    for resultado in resultados:
        medida = resultado["medida"]
        for chave in ("plantados", "achados", "alarmes_falsos", "suspeitas", "perguntas_simples", "custo_usd"):
            resumo[chave] += medida[chave]
        if medida["certo"]:
            resumo["documentos_certos"] += 1
    resumo["documentos"] = len(resultados)
    resumo["acerto"] = round(resumo["achados"] / resumo["plantados"], 3) if resumo["plantados"] else None
    return resumo


def certos_em_todas(repeticoes: list[list[dict]]) -> int:
    """Consistência (pass^k): quantos documentos saíram certos em TODAS as repetições."""
    quantos = 0
    for posicao in range(len(repeticoes[0])):
        sempre_certo = True
        for resultados in repeticoes:
            if not resultados[posicao]["medida"]["certo"]:
                sempre_certo = False
        if sempre_certo:
            quantos += 1
    return quantos


def main() -> None:
    """Roda os documentos escolhidos, quantas vezes pedido, e grava o resultado bruto com o resumo."""
    opcoes = ler_opcoes()
    campos = carregar_layout()
    cliente = conferidor_da_leitura.cliente_padrao()
    if opcoes.conjunto == "armadilhas":
        documentos = documentos_das_armadilhas()
    else:
        documentos = documentos_de_texto_corrido(opcoes)
    print(f"Modo da IA: {config.MODO} · modelo pequeno: {config.MODELO_PEQUENO} · "
          f"prompt {conferidor_da_leitura.VERSAO_PROMPT}")
    repeticoes = []
    resumos = []
    for numero in range(1, opcoes.repeticoes + 1):
        print(f"Repetição {numero}:")
        resultados = rodar_uma_vez(opcoes, documentos, campos, cliente)
        repeticoes.append(resultados)
        resumos.append(resumir(resultados))
    saida = {"experimento": "conferidor", "quando": datetime.now().isoformat(timespec="seconds"),
             "conjunto": opcoes.conjunto, "modo_da_ia": config.MODO, "modelo": config.MODELO_PEQUENO,
             "versao_prompt": conferidor_da_leitura.VERSAO_PROMPT, "semente": SEMENTE,
             "repeticoes": opcoes.repeticoes, "resumo": resumos[0], "resumo_por_repeticao": resumos,
             "certos_em_todas_as_repeticoes": certos_em_todas(repeticoes), "documentos": repeticoes[0],
             "documentos_por_repeticao": repeticoes}
    caminho = Path(opcoes.saida or PASTA_DOS_RESULTADOS / f"conferidor_{opcoes.conjunto}.json")
    caminho.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    custo_total = 0.0
    for resumo in resumos:
        custo_total += resumo["custo_usd"]
    print(f"\nPor repetição: {resumos}")
    print(f"Certos em todas as {opcoes.repeticoes}: {saida['certos_em_todas_as_repeticoes']}/{len(documentos)} · "
          f"custo total US$ {custo_total:.4f}. Gravado em {caminho}")


if __name__ == "__main__":
    main()
