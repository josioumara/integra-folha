"""A fidelidade e a relevância dos materiais do Agente de Endomarketing, medidas com o RAGAS.

Para que serve: o EXP-019 contou ONDE o Endomarketing gera um rascunho; esta medição olha O QUE ele escreveu. Pega os
86 materiais que a IA real gerou na etapa 2 do EXP-019 e mede, com um juiz de outra família que o gerador (o gerador
é o Claude Sonnet 4.6; o juiz, o Mistral Large 3):
- a fidelidade (faithfulness): cada afirmação do material está no trecho do catálogo que o bloco cita? O juiz quebra o
  bloco em afirmações curtas e confere cada uma contra o trecho citado (sim ou não). A fidelidade do bloco é a parte
  das afirmações sustentadas; a do material soma as afirmações de todos os blocos e do título;
- a relevância (answer relevancy): o material responde ao pedido (o tipo, o canal, os benefícios e o destaque)? O juiz
  escreve 3 perguntas que o material responderia, e a relevância é o quanto elas se parecem com o pedido (a semelhança
  dos embeddings, os mesmos do RAG do projeto).
A afirmação que o trecho citado não sustenta é conferida de novo contra TODOS os trechos do material: se outro trecho
sustenta, a fonte foi citada errado; se nenhum sustenta, a afirmação foi inventada.

As 3 etapas (scripts/avaliar_endomarketing_ragas.py chama cada uma):
1. preparar (.venv do projeto, numa CÓPIA do banco, sem IA): lê os 86 GERADOS, separa os blocos, reconstrói os trechos
   que a IA recebeu (o catálogo vigente, conferido pelas fontes e pela conferência do próprio agente) e grava as
   amostras e a planilha dos 50 blocos para rotular (os rótulos de outro avaliador, comparados com os do juiz);
2. julgar (.venv-avaliacao, com o RAGAS e a IA real pelo Bedrock, com teto em dólares): a fidelidade de cada bloco e a
   relevância de cada material;
3. resumir (sem IA): as tabelas do EXP e o kappa entre o juiz e os outros avaliadores (eval/resumo_do_ragas.py).

Por que dois ambientes: o RAGAS traz versões de bibliotecas que brigam com as do projeto (o LangGraph e o
langchain-core), então ele mora num ambiente Python separado (.venv-avaliacao, com requirements-avaliacao.txt). Por
isso este arquivo só importa, no topo, o que vem com o Python: o banco e o agente (só na etapa 1), o openpyxl (só na
planilha) e o RAGAS (só na etapa 2) são importados dentro da função que usa cada um.

Analogia: é o revisor de uma redação com consulta. Ele sublinha cada frase, procura a frase na página do livro que o
aluno disse ter usado e marca "está" ou "não está". Se não está, procura no resto do livro: achou em outra página, o
aluno citou a página errada; não achou em lugar nenhum, o aluno inventou.
"""
import asyncio
import csv
import json
import math
import random
import threading
from pathlib import Path

# A raiz do repositório (este arquivo fica em eval/)
RAIZ = Path(__file__).resolve().parent.parent

# ---------------- Os arquivos ----------------

# Os resultados brutos de cada medição (regravados a cada medição)
PASTA_DOS_RESULTADOS = RAIZ / "data" / "avaliacao" / "resultados"
# Os materiais GERADOS vêm da etapa 2 do EXP-019 (a IA real)
CSV_DO_EXP_019 = PASTA_DOS_RESULTADOS / "endomarketing_combinacoes_etapa2.csv"
# O que a etapa 1 prepara: os materiais, os blocos e os trechos que a IA recebeu
ARQUIVO_DAS_AMOSTRAS = PASTA_DOS_RESULTADOS / "endomarketing_ragas_amostras.json"
# O que a etapa 2 mede: uma linha por bloco e uma por material
CSV_DOS_BLOCOS = PASTA_DOS_RESULTADOS / "endomarketing_ragas_blocos.csv"
CSV_DOS_MATERIAIS = PASTA_DOS_RESULTADOS / "endomarketing_ragas_materiais.csv"
# As tabelas do EXP (etapa 3)
ARQUIVO_DO_RESUMO = PASTA_DOS_RESULTADOS / "endomarketing_ragas.json"
# A conferência de 10 casos do juiz pelo agente que mede, caso a caso (uma IA: não é rótulo humano)
ARQUIVO_DA_CONFERENCIA_DO_AGENTE = PASTA_DOS_RESULTADOS / "endomarketing_ragas_conferencia_do_agente.json"
# A planilha dos 50 blocos sorteados para rotular
PLANILHA_DOS_50 = RAIZ / "data" / "avaliacao" / "rotulos_fidelidade_endomarketing_50.xlsx"
# Os prompts do RAGAS traduzidos para o português (uma vez, conferidos um a um; as medições seguintes só leem)
ARQUIVO_DOS_PROMPTS_EM_PORTUGUES = RAIZ / "data" / "avaliacao" / "ragas_prompts_portugues.json"

# ---------------- O que se mede ----------------

# As linhas do EXP-019 que entram: a coluna "rodada" igual a 1 (o 2 só repetia algumas combinações) e GERADO
RODADA_MEDIDA = 1
SITUACAO_GERADO = "GERADO"
# O destaque só entra na pergunta quando é um pedido comum; fora do catálogo ou ataque, o certo é o material ignorá-lo
CASO_NORMAL = "normal"
# A pergunta que cada tipo de material responde (a relevância compara as perguntas do juiz com ela). Sai da definição
# de cada tipo no prompt v4 do Endomarketing; o canal não entra, porque o prompt diz que ele muda o tamanho, nunca o
# conteúdo. {empresa}: "a empresa <assinatura>", ou só "a empresa" no kit padrão
PERGUNTA_DO_TIPO = {
    "comunicado": "O que {empresa} comunica ao time sobre os benefícios: {beneficios}?",
    "faq": "Quais são as dúvidas do time e as respostas sobre os benefícios que {empresa} oferece: {beneficios}?",
    "kit_boas_vindas": ("Quais são os primeiros passos e os benefícios para quem acabou de chegar, que {empresa} "
                        "oferece: {beneficios}?"),
    "lembrete_conta": ("Por que {empresa} convida todo o time a abrir a conta, e quais benefícios o time ganha com ela: "
                       "{beneficios}?"),
}
# A pergunta da fidelidade é neutra, sem fato nenhum. O RAGAS passa a pergunta ao juiz que quebra o texto em
# afirmações; com o pedido inteiro (o tipo, o canal e a lista de benefícios), o juiz tirava afirmações do PEDIDO, e não
# do texto (visto no ensaio com 3 materiais: "a Brisa deve abrir uma conta no canal WhatsApp")
PERGUNTA_DA_FIDELIDADE = "O que este trecho do material diz?"

# ---------------- O juiz ----------------

# O juiz é de outra família que o gerador (o Claude Sonnet 4.6), para não "concordar consigo mesmo"
JUIZ_PRINCIPAL = "mistral-large-3"
# O juiz reserva, se o principal falhar no formato da resposta (o Nova, da Amazon, também de outra família)
JUIZ_RESERVA = "nova-pro"
# A temperatura que o RAGAS usa nos juízes dele (InstructorModelArgs): quase zero, para o veredito não variar
TEMPERATURA_DO_RAGAS = 0.01
# O limite de tokens da resposta do juiz (o RAGAS usa 1.024; um bloco com muitas afirmações passaria disso)
LIMITE_DE_SAIDA_DO_JUIZ = 4096
# A instrução de sistema do juiz: só o formato (a tarefa inteira vem no prompt do RAGAS)
SISTEMA_DO_JUIZ = "Responda só com o JSON pedido."
# O custo máximo de uma chamada ao juiz, reservado antes de chamar: 4 chamadas ao mesmo tempo nunca passam do teto
CUSTO_RESERVADO_POR_CHAMADA = 0.02
# Quantas medições rodam ao mesmo tempo (acima disso, o Bedrock pede para esperar, e o projeto tenta de novo)
MEDICOES_AO_MESMO_TEMPO = 4
# Quantas perguntas o juiz escreve para a relevância (o "strictness" do RAGAS; 3 é o padrão dele)
PERGUNTAS_DA_RELEVANCIA = 3
# O idioma para o qual o RAGAS traduz os prompts dele (BasePrompt.adapt)
IDIOMA_DOS_PROMPTS = "portuguese"
# Os 3 prompts do RAGAS usados aqui: quebrar em afirmações, dar o veredito de cada uma e escrever as perguntas
NOMES_DOS_PROMPTS = ("afirmacoes", "veredito", "perguntas")

# ---------------- Os rótulos (a régua da planilha e do juiz) ----------------

ROTULO_FIEL = "fiel"            # tudo o que o bloco afirma está no trecho citado
ROTULO_EM_PARTE = "em parte"    # uma parte está, outra não
ROTULO_NAO_FIEL = "não fiel"    # nada do que o bloco afirma está no trecho citado
# Do pior para o melhor: a ordem que o kappa ponderado usa (errar "fiel" por "não fiel" pesa mais que por "em parte")
ROTULOS = (ROTULO_NAO_FIEL, ROTULO_EM_PARTE, ROTULO_FIEL)
# A semente do sorteio dos blocos para rotular (a mesma da amostra do EXP-019), e quantos são
SEMENTE_DOS_ROTULOS = 20260930
BLOCOS_PARA_ROTULAR = 50

# ---------------- A situação de cada bloco medido ----------------

BLOCO_MEDIDO = "medido"                     # o juiz deu o veredito de cada afirmação
BLOCO_SEM_AFIRMACAO = "sem_afirmacao"       # o juiz não achou afirmação nenhuma (ex.: "Até breve!")
BLOCO_ERRO_DO_JUIZ = "erro_do_juiz"         # o Bedrock falhou ou a resposta veio fora do formato
BLOCO_PARADO_PELO_TETO = "parado_pelo_teto"  # o gasto chegou ao teto antes deste bloco
# A situação do material: todos os blocos e a relevância medidos, ou faltou algo
MATERIAL_MEDIDO = "medido"
MATERIAL_INCOMPLETO = "incompleto"


# ============================== Etapa 1: preparar (sem IA, numa cópia do banco) ==============================

def separar_blocos(texto: str) -> tuple[str, list[dict]]:
    """O título e os blocos de um material, a partir do texto que o EXP-019 gravou.

    Recebe: o texto da coluna "texto" do CSV do EXP-019: o título na primeira linha e um bloco por linha, com as fontes
    no fim, entre colchetes e separadas por "; " (eval/combinacoes_do_endomarketing.py, _texto_do_material).
    Devolve: (o título, [{texto, fontes}]). Uma linha sem fontes no fim é a continuação do bloco de baixo (o texto de
    um bloco pode ter uma quebra de linha). Levanta ValueError se o texto termina sem as fontes do último bloco.
    Exemplo: "Título\nA conta é grátis. [Pacote v1 › Conta salário]" →
             ("Título", [{"texto": "A conta é grátis.", "fontes": ["Pacote v1 › Conta salário"]}])
    """
    linhas = texto.split("\n")
    # A primeira linha é o título
    titulo = linhas[0].strip()
    blocos = []
    # O começo de um bloco que ainda não chegou às fontes (quando o texto do bloco tem quebra de linha)
    pedaco_aberto = ""
    for linha in linhas[1:]:
        # As fontes ficam no fim da linha, entre o último " [" e o "]" final
        inicio_das_fontes = linha.rfind(" [")
        if linha.endswith("]") and inicio_das_fontes >= 0:
            # O texto do bloco: o que veio antes (se veio) e esta linha até as fontes
            texto_do_bloco = (pedaco_aberto + linha[:inicio_das_fontes]).strip()
            # As fontes: o que está entre os colchetes, separado por "; "
            fontes = linha[inicio_das_fontes + 2:-1].split("; ")
            blocos.append({"texto": texto_do_bloco, "fontes": fontes})
            pedaco_aberto = ""
        else:
            # Sem fontes no fim: o bloco continua na linha de baixo
            pedaco_aberto = pedaco_aberto + linha + "\n"
    # Sobrou texto sem fontes: o material não está no formato do EXP-019
    if pedaco_aberto.strip():
        raise ValueError("o texto termina com um bloco sem fontes")
    return titulo, blocos


def fatos_do_pedido(assinatura: str) -> str:
    """O que o pedido à IA dizia além dos trechos, como mais uma linha do contexto do juiz.

    O prompt v4 do Endomarketing diz que o banco é o parceiro da folha de pagamento da empresa, e a <assinatura> traz o
    nome da empresa que fala com o próprio time (vazia no kit padrão). Sem esta linha, o juiz marcaria como inventada
    uma frase como "a Brisa Tecnologia Ltda. tem a folha com o banco parceiro", que o pedido sustenta.
    Exemplo: "Brisa Tecnologia Ltda." → "[Pedido] A empresa Brisa Tecnologia Ltda. assina o material, para o próprio
    time. O banco é o parceiro da folha de pagamento da empresa."
    """
    # O banco parceiro da folha vem do prompt de sistema: vale para todo material
    fato_do_banco = "O banco é o parceiro da folha de pagamento da empresa."
    # Kit padrão: o material não leva o nome de nenhuma empresa
    if not assinatura:
        return "[Pedido] " + fato_do_banco
    return f"[Pedido] A empresa {assinatura} assina o material, para o próprio time. " + fato_do_banco


def pergunta_do_material(tipo: str, beneficios: list[str], assinatura: str, caso_do_destaque: str,
                         destaque: str) -> str:
    """A pergunta que o material deveria responder: o "user_input" da relevância do RAGAS.

    Sai do tipo (PERGUNTA_DO_TIPO), dos benefícios escolhidos e de quem assina; o destaque entra SÓ no caso normal. No
    destaque fora do catálogo e no ataque disfarçado, o certo é o material NÃO falar do destaque (o agente avisa o
    especialista): se o destaque entrasse na pergunta, o material certo pareceria menos relevante.
    Exemplo: ("lembrete_conta", ["Conta salário"], "Brisa Tecnologia Ltda.", "vazio", "") → "Por que a empresa Brisa
    Tecnologia Ltda. convida todo o time a abrir a conta, e quais benefícios o time ganha com ela: Conta salário?"
    """
    # A empresa pelo nome da assinatura, ou só "a empresa" no kit padrão
    empresa = "a empresa"
    if assinatura:
        empresa = f"a empresa {assinatura}"
    pergunta = PERGUNTA_DO_TIPO[tipo].format(empresa=empresa, beneficios=", ".join(beneficios))
    # O destaque só no pedido comum
    if caso_do_destaque == CASO_NORMAL and destaque:
        pergunta = pergunta + f" Com destaque para: {destaque}."
    return pergunta


def texto_sem_fontes(titulo: str, blocos: list[dict]) -> str:
    """O material como a empresa o lê: o título e os blocos, um por linha, sem as fontes entre colchetes."""
    linhas = [titulo]
    # Cada bloco numa linha, só o texto
    for bloco in blocos:
        linhas.append(bloco["texto"])
    return "\n".join(linhas)


def _linhas_dos_trechos(trechos: list[dict]) -> dict:
    """A linha de cada trecho, do jeito que a IA a recebeu no pedido ("[fonte] conteúdo"), por fonte.

    Exemplo: [{"fonte": "Pacote v1 › Conta salário", "texto": "Pacote v1 › Conta salário\nSem tarifa."}] →
             {"Pacote v1 › Conta salário": "[Pacote v1 › Conta salário] Sem tarifa."}
    """
    # Importado aqui: só a etapa 1 (no .venv do projeto) usa o agente
    from agents import endomarketing
    linhas = {}
    for trecho in trechos:
        # O mesmo jeito de _montar_pedido: a fonte entre colchetes e o conteúdo numa linha só
        linhas[trecho["fonte"]] = f"[{trecho['fonte']}] {endomarketing._conteudo(trecho)}"
    return linhas


def por_que_o_catalogo_nao_confere(blocos: list[dict], trechos: list[dict]) -> str:
    """Vazio se o catálogo de hoje é o mesmo que a IA recebeu; senão, o porquê.

    Duas conferências: (1) toda fonte citada existe no catálogo reconstruído (a fonte traz a versão, ex.: "Pacote de
    benefícios Brisa v2"; um catálogo novo muda o nome); (2) a conferência do próprio agente (a fonte, os números e os
    links de cada bloco) passou quando o material foi gerado e tem de passar de novo. Se não passa, o conteúdo mudou.
    Exemplo: um bloco que cita "Pacote v1 › Seguro" com o catálogo de hoje na v2 → "a fonte Pacote v1 › Seguro não
    está no catálogo de hoje".
    """
    # Importado aqui: só a etapa 1 (no .venv do projeto) usa o agente
    from agents import endomarketing
    # As fontes do catálogo reconstruído
    fontes_de_hoje = set()
    for trecho in trechos:
        fontes_de_hoje.add(trecho["fonte"])
    # (1) Cada fonte citada precisa existir hoje
    for bloco in blocos:
        for fonte in bloco["fontes"]:
            if endomarketing.fonte_sem_colchetes(fonte) not in fontes_de_hoje:
                return f"a fonte {fonte} não está no catálogo de hoje"
    # (2) A conferência do agente, com os trechos de hoje, precisa aprovar todos os blocos de novo
    blocos_do_agente = []
    for bloco in blocos:
        blocos_do_agente.append(endomarketing.Bloco(texto=bloco["texto"], fontes=bloco["fontes"]))
    material = endomarketing.MaterialGerado(titulo="", blocos=blocos_do_agente)
    aprovados, observacoes = endomarketing.conferir_material(material, trechos)
    if len(aprovados) != len(blocos):
        return "a conferência do agente não passa mais: " + observacoes[0]
    return ""


def _blocos_da_amostra(combinacao: str, titulo: str, blocos: list[dict], linhas_dos_trechos: dict,
                       fatos: str) -> list[dict]:
    """Os blocos da amostra, com o contexto que o juiz usa em cada um; o título é o bloco 0.

    O contexto de um bloco são os trechos que ele cita e os fatos do pedido. O título não cita fonte: o contexto dele
    são todos os trechos do material (e os fatos do pedido).
    """
    # Importado aqui: só a etapa 1 (no .venv do projeto) usa o agente
    from agents import endomarketing
    # Todos os trechos do material, na ordem em que a IA os recebeu, e os fatos do pedido
    contexto_do_material = list(linhas_dos_trechos.values()) + [fatos]
    amostras = [{"bloco_id": f"{combinacao}-0", "posicao": 0, "e_titulo": True, "texto": titulo, "fontes": [],
                 "contexto_citado": contexto_do_material}]
    # Os blocos de conteúdo: 1, 2, 3...
    for posicao, bloco in enumerate(blocos, start=1):
        contexto_citado = []
        # Só os trechos que o bloco cita (a fonte pode vir com colchetes: a conferência do agente já aceitou)
        for fonte in bloco["fontes"]:
            contexto_citado.append(linhas_dos_trechos[endomarketing.fonte_sem_colchetes(fonte)])
        contexto_citado.append(fatos)
        amostras.append({"bloco_id": f"{combinacao}-{posicao}", "posicao": posicao, "e_titulo": False,
                         "texto": bloco["texto"], "fontes": bloco["fontes"], "contexto_citado": contexto_citado})
    return amostras


def preparar_material(conexao, linha: dict) -> dict:
    """A amostra de um material GERADO: os blocos, o contexto de cada um e a pergunta que ele deveria responder.

    Recebe: conexao (a cópia do banco); linha (uma linha do CSV do EXP-019, lida por ler_csv).
    Devolve: {combinacao, empresa_id, empresa, tipo, canal, caso_do_destaque, conjunto, beneficios, destaque, pergunta,
    texto_sem_fontes, contexto_do_material, catalogo_confere, por_que_nao_confere, blocos}. Se o catálogo de hoje não é
    o que a IA recebeu, catalogo_confere fica False e o juiz pula o material.
    """
    # Importado aqui: só a etapa 1 (no .venv do projeto) usa o agente
    from agents import endomarketing
    titulo, blocos = separar_blocos(linha["texto"])
    # Os trechos que a IA recebeu: os benefícios escolhidos e os de atendimento, do catálogo vigente da empresa
    trechos = endomarketing._trechos_dos_beneficios_escolhidos(conexao, linha["empresa_id"], linha["beneficios"])
    # O nome que assina o material (o kit em uso da empresa; vazio no kit padrão)
    assinatura = endomarketing.assinatura_do_kit_em_uso(conexao, linha["empresa_id"])
    fatos = fatos_do_pedido(assinatura)
    linhas_dos_trechos = _linhas_dos_trechos(trechos)
    por_que_nao_confere = por_que_o_catalogo_nao_confere(blocos, trechos)
    # Os blocos só são montados se o catálogo confere (senão, uma fonte citada pode nem existir hoje)
    blocos_da_amostra = []
    if not por_que_nao_confere:
        blocos_da_amostra = _blocos_da_amostra(linha["combinacao"], titulo, blocos, linhas_dos_trechos, fatos)
    pergunta = pergunta_do_material(linha["tipo"], linha["beneficios"], assinatura, linha["caso_do_destaque"],
                                    linha["destaque"])
    return {"combinacao": linha["combinacao"], "empresa_id": linha["empresa_id"], "empresa": linha["empresa"],
            "tipo": linha["tipo"], "canal": linha["canal"], "caso_do_destaque": linha["caso_do_destaque"],
            "conjunto": linha["conjunto"], "beneficios": linha["beneficios"], "destaque": linha["destaque"],
            "pergunta": pergunta, "texto_sem_fontes": texto_sem_fontes(titulo, blocos),
            "contexto_do_material": list(linhas_dos_trechos.values()) + [fatos],
            "catalogo_confere": not por_que_nao_confere, "por_que_nao_confere": por_que_nao_confere,
            "blocos": blocos_da_amostra}


def linhas_geradas(caminho: Path = CSV_DO_EXP_019) -> list[dict]:
    """As linhas do CSV do EXP-019 que entram na medição: a coluna "rodada" igual a 1, só as que geraram um rascunho."""
    # Importado aqui: o leitor do CSV mora no módulo do EXP-019, que usa o banco (só no .venv do projeto)
    from eval import combinacoes_do_endomarketing as combinacoes
    geradas = []
    for linha in combinacoes.ler_csv(caminho):
        if linha["rodada"] == RODADA_MEDIDA and linha["situacao"] == SITUACAO_GERADO:
            geradas.append(linha)
    return geradas


def preparar(conexao, caminho: Path = CSV_DO_EXP_019) -> list[dict]:
    """As amostras de todos os materiais GERADOS do EXP-019 (a etapa 1). Recebe: conexao (a cópia do banco)."""
    amostras = []
    for linha in linhas_geradas(caminho):
        amostras.append(preparar_material(conexao, linha))
    return amostras


def sortear_blocos_para_rotular(materiais: list[dict], quantos: int = BLOCOS_PARA_ROTULAR,
                                semente: int = SEMENTE_DOS_ROTULOS) -> list[dict]:
    """Os 50 blocos da planilha para rotular, sorteados com a semente fixa (sempre os mesmos).

    Entram os blocos de conteúdo (sem os títulos, que não citam fonte) dos materiais cujo catálogo confere. O sorteio
    vem ANTES de o juiz rodar: a escolha não depende do que o juiz diz.
    Devolve: [{numero, bloco_id, tipo, canal, texto, fontes, trecho_citado}], na ordem do sorteio.
    """
    candidatos = []
    for material in materiais:
        # Catálogo que mudou: o trecho de hoje não é o que a IA recebeu
        if not material["catalogo_confere"]:
            continue
        for bloco in material["blocos"]:
            # O título não cita fonte: não há "trecho citado" para comparar
            if bloco["e_titulo"]:
                continue
            candidatos.append((material, bloco))
    # O sorteio sem repetição, sempre igual com a mesma semente
    sorteio = random.Random(semente)
    escolhidos = sorteio.sample(candidatos, min(quantos, len(candidatos)))
    linhas = []
    for numero, (material, bloco) in enumerate(escolhidos, start=1):
        linhas.append({"numero": numero, "bloco_id": bloco["bloco_id"], "tipo": material["tipo"],
                       "canal": material["canal"], "texto": bloco["texto"], "fontes": "; ".join(bloco["fontes"]),
                       "trecho_citado": "\n".join(bloco["contexto_citado"])})
    return linhas


# Quantos blocos o agente que mede confere caso a caso (metade em que o juiz viu problema, metade que ele achou fiel)
BLOCOS_PARA_A_CONFERENCIA_DO_AGENTE = 10


def sortear_para_a_conferencia_do_agente(blocos: list[dict], ja_na_planilha: set,
                                         quantos: int = BLOCOS_PARA_A_CONFERENCIA_DO_AGENTE,
                                         semente: int = SEMENTE_DOS_ROTULOS) -> list[dict]:
    """Os blocos que o agente que mede confere caso a caso, depois do juiz: sempre os mesmos com a mesma semente.

    É uma IA conferindo outra: ajuda a achar o porquê dos erros do juiz, mas não é uma calibração humana.

    Metade entre os blocos em que o juiz viu afirmação sem sustentação ("em parte" ou "não fiel") e metade entre os que
    ele achou fiéis: assim a conferência pega os dois erros possíveis do juiz (acusar à toa e deixar passar). Ficam de
    fora os títulos e os blocos da planilha de rótulos (a conferência do agente cobre outros blocos).
    Recebe: blocos (as linhas do CSV dos blocos); ja_na_planilha (os bloco_id da planilha). Devolve: as linhas sorteadas.
    """
    com_problema = []
    fieis = []
    for bloco in blocos:
        # Só os blocos de conteúdo medidos, fora da planilha
        if bloco["e_titulo"] or bloco["situacao"] != BLOCO_MEDIDO or bloco["bloco_id"] in ja_na_planilha:
            continue
        if bloco["rotulo_do_juiz"] == ROTULO_FIEL:
            fieis.append(bloco)
        else:
            com_problema.append(bloco)
    sorteio = random.Random(semente)
    metade = quantos // 2
    escolhidos = sorteio.sample(com_problema, min(metade, len(com_problema)))
    escolhidos.extend(sorteio.sample(fieis, min(quantos - metade, len(fieis))))
    return escolhidos


# O cabeçalho da planilha dos rótulos (a coluna "rótulo" é a 8ª, com a lista das 3 opções)
CABECALHO_DA_PLANILHA = ("nº", "bloco_id", "tipo", "canal", "texto do bloco", "fontes citadas",
                         "o que o trecho citado diz", "rótulo", "comentário")
COLUNA_DO_ROTULO = 8
COLUNA_DO_COMENTARIO = 9
# A largura de cada coluna da planilha, em caracteres
LARGURAS_DA_PLANILHA = (5, 12, 16, 10, 60, 35, 70, 12, 30)
# A aba "Como rotular": o que cada rótulo quer dizer
INSTRUCOES_DA_PLANILHA = (
    "Como rotular (uma linha por bloco; escolha o rótulo na lista da coluna H)",
    "",
    "Compare o TEXTO DO BLOCO com O QUE O TRECHO CITADO DIZ (e com a linha [Pedido], que diz quem assina e que o banco "
    "é o parceiro da folha).",
    "Olhe só as afirmações de fato: o quê, quanto, quando, como, quem pode, onde. Convite e tom (\"aproveite!\", "
    "\"conte com a gente\") não contam.",
    "",
    "fiel: tudo o que o bloco afirma está no trecho citado (pode estar com outras palavras).",
    "em parte: uma parte está no trecho e outra não (ex.: um prazo, um valor ou uma condição que o trecho não traz).",
    "não fiel: o principal do bloco não está no trecho citado.",
    "",
    "O comentário é opcional: use quando ficar em dúvida ou quando quiser dizer o que faltou.",
)


def gravar_planilha_dos_rotulos(linhas: list[dict], caminho: Path = PLANILHA_DOS_50) -> None:
    """Grava a planilha dos rótulos (Excel): uma linha por bloco, a lista das 3 opções e a aba de instruções."""
    # Importado aqui: só quem grava ou lê a planilha precisa do openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    livro = Workbook()
    aba = livro.active
    aba.title = "Rotulos"
    aba.append(list(CABECALHO_DA_PLANILHA))
    # Uma linha por bloco sorteado; o rótulo e o comentário ficam em branco para quem rotula
    for linha in linhas:
        aba.append([linha["numero"], linha["bloco_id"], linha["tipo"], linha["canal"], linha["texto"], linha["fontes"],
                    linha["trecho_citado"], "", ""])
    # O cabeçalho em negrito e parado no alto ao rolar
    for celula in aba[1]:
        celula.font = Font(bold=True)
    aba.freeze_panes = "A2"
    # A largura de cada coluna e o texto quebrando a linha dentro da célula
    for numero_da_coluna, largura in enumerate(LARGURAS_DA_PLANILHA, start=1):
        aba.column_dimensions[get_column_letter(numero_da_coluna)].width = largura
    for linha_da_aba in aba.iter_rows(min_row=2):
        for celula in linha_da_aba:
            celula.alignment = Alignment(wrap_text=True, vertical="top")
    # A coluna do rótulo aceita só as 3 opções (a lista que o Excel mostra ao clicar)
    lista_dos_rotulos = DataValidation(type="list", formula1='"' + ",".join(ROTULOS) + '"', allow_blank=True)
    letra_do_rotulo = get_column_letter(COLUNA_DO_ROTULO)
    lista_dos_rotulos.add(f"{letra_do_rotulo}2:{letra_do_rotulo}{len(linhas) + 1}")
    aba.add_data_validation(lista_dos_rotulos)
    # A aba das instruções
    instrucoes = livro.create_sheet("Como rotular")
    for texto in INSTRUCOES_DA_PLANILHA:
        instrucoes.append([texto])
    instrucoes.column_dimensions["A"].width = 120
    caminho.parent.mkdir(parents=True, exist_ok=True)
    livro.save(caminho)


def rotulo_escrito(texto) -> str:
    """O rótulo escrito na planilha, no formato da régua; vazio se não é um dos 3.

    Aceita maiúsculas, espaços e "nao" sem til. Exemplo: " Não Fiel " → "não fiel"; "nao fiel" → "não fiel"; "x" → "".
    """
    # Célula vazia: ainda sem rótulo
    if texto is None:
        return ""
    limpo = str(texto).strip().lower().replace("nao ", "não ")
    if limpo in ROTULOS:
        return limpo
    return ""


def ler_rotulos(caminho: Path = PLANILHA_DOS_50) -> dict:
    """Os rótulos da planilha, por bloco: {bloco_id: {"rotulo", "comentario"}} (só as linhas rotuladas)."""
    # Importado aqui: só quem grava ou lê a planilha precisa do openpyxl
    from openpyxl import load_workbook
    livro = load_workbook(caminho, read_only=True)
    rotulos = {}
    try:
        # Da 2ª linha em diante (a 1ª é o cabeçalho); cada linha como uma tupla de valores
        for valores in livro["Rotulos"].iter_rows(min_row=2, values_only=True):
            rotulo = rotulo_escrito(valores[COLUNA_DO_ROTULO - 1])
            if rotulo:
                comentario = valores[COLUNA_DO_COMENTARIO - 1] or ""
                rotulos[valores[1]] = {"rotulo": rotulo, "comentario": str(comentario)}
    finally:
        # No modo de leitura, o arquivo fica aberto até fechar (no Windows, o Excel não conseguiria salvar)
        livro.close()
    return rotulos


# ============================== Etapa 2: julgar (IA real pelo Bedrock, com o RAGAS) ==============================

class TetoAtingido(RuntimeError):
    """A próxima chamada ao juiz passaria do teto em dólares: a medição para aqui."""


class RespostaForaDoFormato(ValueError):
    """O juiz respondeu algo que não é o JSON que o RAGAS pediu."""


class CaixaDoGasto:
    """O gasto do juiz, somado por todas as chamadas (inclusive as que rodam ao mesmo tempo), com o teto.

    Antes de cada chamada, reserva o custo máximo de uma chamada; depois, troca a reserva pelo custo real. Assim, 4
    chamadas ao mesmo tempo nunca passam do teto juntas. A trava (Lock) impede que duas chamadas mexam na soma no
    mesmo instante.
    Exemplo: caixa = CaixaDoGasto(2.0); caixa.reservar(); caixa.pagar(0.004) → caixa.gasto_usd == 0.004.
    """

    def __init__(self, teto_usd: float):
        """Recebe o teto em dólares desta medição do juiz."""
        self.teto_usd = teto_usd
        # O que já foi gasto, o que está reservado para as chamadas em andamento e quantas chamadas terminaram
        self.gasto_usd = 0.0
        self.reservado_usd = 0.0
        self.chamadas = 0
        self._trava = threading.Lock()

    def reservar(self) -> None:
        """Reserva o custo máximo de uma chamada; levanta TetoAtingido se a reserva passaria do teto."""
        with self._trava:
            if self.gasto_usd + self.reservado_usd + CUSTO_RESERVADO_POR_CHAMADA > self.teto_usd:
                raise TetoAtingido(f"o gasto do juiz chegaria a mais de US$ {self.teto_usd:.2f}")
            self.reservado_usd += CUSTO_RESERVADO_POR_CHAMADA

    def pagar(self, custo_usd: float) -> None:
        """Troca a reserva de uma chamada pelo custo real dela (zero se a chamada nem saiu)."""
        with self._trava:
            self.reservado_usd -= CUSTO_RESERVADO_POR_CHAMADA
            self.gasto_usd += custo_usd
            self.chamadas += 1


def _chamar_o_bedrock(modelo: str, prompt: str, esquema_json: dict):
    """Uma chamada ao juiz pelo Bedrock, pela MESMA rota do projeto (services/provedores_de_ia.py).

    A mesma rota quer dizer as mesmas regras de privacidade (ADR-101): o perfil geográfico EUA, a recusa dos modelos
    que guardam os pedidos e as novas tentativas quando o Bedrock pede para esperar. O esquema garante o formato da
    resposta (o JSON que o RAGAS pede), como no Interpretador.
    Devolve: a RespostaDoProvedor (o texto e os tokens).
    """
    # Importado aqui: o módulo de provedores só depende do config (que lê o .env) e roda nos dois ambientes
    from services import provedores_de_ia
    # O juiz só roda pelo Bedrock (a chave do .env): pela rota direta, o nome do modelo seria outro
    if not provedores_de_ia.usa_o_bedrock():
        raise RuntimeError("O juiz do RAGAS só roda pelo Bedrock: ROTA_DA_IA=bedrock no .env.")
    provedores_de_ia.recusar_modelo_que_guarda_pedidos(modelo)
    nome_na_rota = provedores_de_ia.nome_do_modelo_na_rota(modelo)
    # O Nova recusa o esquema: nele, o formato é garantido pela "ferramenta" obrigatória (ADR-107)
    por_ferramenta = modelo in provedores_de_ia.MODELOS_COM_FERRAMENTA_FORCADA
    return provedores_de_ia.chamar_pelo_converse(nome_na_rota, SISTEMA_DO_JUIZ, prompt, TEMPERATURA_DO_RAGAS,
                                                 LIMITE_DE_SAIDA_DO_JUIZ, esquema_json=esquema_json,
                                                 formato_por_ferramenta=por_ferramenta)


def _custo_da_chamada(modelo: str, tokens_entrada: int, tokens_saida: int) -> float:
    """O custo de uma chamada ao juiz, com a tabela de preços do projeto (e os 10% do perfil EUA)."""
    # Importado aqui: o módulo de provedores só depende do config (que lê o .env) e roda nos dois ambientes
    from services import provedores_de_ia
    custo = provedores_de_ia.custo_em_dolares(modelo, tokens_entrada, tokens_saida)
    # Sem preço na tabela, o teto não teria como funcionar: melhor parar
    if custo is None:
        raise RuntimeError(f"O modelo {modelo} não tem preço na tabela do projeto.")
    return custo


class JuizDoBedrock:
    """O juiz do RAGAS: recebe o prompt do RAGAS e o formato da resposta e devolve a resposta nesse formato.

    O RAGAS 0.4 chama o juiz por generate/agenerate(prompt, response_model), onde response_model é a classe (Pydantic)
    da resposta que ele espera. Este juiz manda o prompt ao Bedrock com o formato garantido, confere a resposta com a
    classe e guarda cada resposta em "respostas" (as afirmações e os vereditos, que a métrica do RAGAS não devolve).
    Um juiz por medição: as respostas de um bloco nunca se misturam com as de outro, e o gasto soma na caixa comum.
    Recebe: modelo (ex.: "mistral-large-3"); caixa (a CaixaDoGasto da medição); chamar (a função que chama a IA; os
    testes passam uma falsa, que não gasta).
    """

    def __init__(self, modelo: str, caixa: CaixaDoGasto, chamar=None):
        """Guarda o modelo, a caixa e a função que chama a IA (a do Bedrock, se nenhuma for passada)."""
        self.modelo = modelo
        self.caixa = caixa
        self._chamar = chamar or _chamar_o_bedrock
        # O que esta medição devolveu e gastou
        self.respostas = []
        self.custo_usd = 0.0
        self.tokens_entrada = 0
        self.tokens_saida = 0

    def generate(self, prompt: str, response_model):
        """Uma chamada ao juiz: devolve a resposta no formato de response_model (a classe que o RAGAS passa)."""
        self.caixa.reservar()
        custo = 0.0
        try:
            resposta = self._chamar(self.modelo, prompt, response_model.model_json_schema())
            custo = _custo_da_chamada(self.modelo, resposta.tokens_entrada, resposta.tokens_saida)
            self.tokens_entrada += resposta.tokens_entrada
            self.tokens_saida += resposta.tokens_saida
        finally:
            # A reserva sai sempre; o custo real entra quando a chamada voltou (mesmo se a resposta vier torta)
            self.caixa.pagar(custo)
            self.custo_usd += custo
        try:
            objeto = response_model.model_validate_json(resposta.texto)
        except ValueError as erro:
            raise RespostaForaDoFormato(f"a resposta do juiz não é o JSON pedido ({type(erro).__name__})") from erro
        self.respostas.append(objeto)
        return objeto

    async def agenerate(self, prompt: str, response_model):
        """A mesma chamada, no jeito assíncrono que o RAGAS usa: roda numa thread, sem travar as outras medições."""
        return await asyncio.to_thread(self.generate, prompt, response_model)


class EmbeddingsDoProjeto:
    """Os embeddings do RAG do projeto (rag/embeddings.py), no formato que o RAGAS pede, para a relevância.

    O mesmo modelo que busca os trechos do catálogo mede a semelhança entre o pedido e as perguntas do juiz: roda nesta
    máquina, sem custo e sem mandar o texto para fora.
    """

    def embed_text(self, texto: str, **opcoes) -> list[float]:
        """O vetor de um texto (as opções que o RAGAS passa não mudam nada aqui)."""
        # Importado aqui: carregar o modelo leva alguns segundos
        from rag import embeddings
        return embeddings.vetorizar([texto])[0]

    def embed_texts(self, textos: list[str], **opcoes) -> list[list[float]]:
        """O vetor de cada texto."""
        # Importado aqui: carregar o modelo leva alguns segundos
        from rag import embeddings
        return embeddings.vetorizar(list(textos))

    async def aembed_text(self, texto: str, **opcoes) -> list[float]:
        """O vetor de um texto, no jeito assíncrono que o RAGAS usa."""
        return self.embed_text(texto)

    async def aembed_texts(self, textos: list[str], **opcoes) -> list[list[float]]:
        """O vetor de cada texto, no jeito assíncrono que o RAGAS usa."""
        return self.embed_texts(textos)


def ligar_ao_ragas() -> None:
    """Diz ao RAGAS que o nosso juiz e os nossos embeddings são "da família" das classes dele.

    As métricas do RAGAS 0.4 só aceitam um LLM que seja um InstructorBaseRagasLLM e embeddings que sejam um
    BaseRagasEmbedding (elas conferem com isinstance). O register do Python cria uma "subclasse virtual": o isinstance
    passa a dizer sim, sem que este arquivo importe o RAGAS no topo (e ele segue importável no .venv do projeto).
    """
    # Importados aqui: o RAGAS só existe no .venv-avaliacao
    from ragas.embeddings.base import BaseRagasEmbedding
    from ragas.llms.base import InstructorBaseRagasLLM
    InstructorBaseRagasLLM.register(JuizDoBedrock)
    BaseRagasEmbedding.register(EmbeddingsDoProjeto)


def _prompts_originais() -> dict:
    """Os 3 prompts do RAGAS, em inglês, como vêm na biblioteca (um objeto novo a cada chamada)."""
    # Importados aqui: o RAGAS só existe no .venv-avaliacao
    from ragas.metrics.collections.answer_relevancy.util import AnswerRelevancePrompt
    from ragas.metrics.collections.faithfulness.util import NLIStatementPrompt, StatementGeneratorPrompt
    return {"afirmacoes": StatementGeneratorPrompt(), "veredito": NLIStatementPrompt(),
            "perguntas": AnswerRelevancePrompt()}


def _prompt_em_dicionario(prompt) -> dict:
    """Um prompt do RAGAS como dicionário (o idioma, a instrução e os exemplos), para gravar em JSON."""
    exemplos = []
    # Cada exemplo é um par (entrada, saída), duas classes Pydantic
    for entrada, saida in prompt.examples:
        exemplos.append({"entrada": entrada.model_dump(), "saida": saida.model_dump()})
    return {"idioma": prompt.language, "instrucao": prompt.instruction, "exemplos": exemplos}


def _prompt_do_dicionario(prompt, dados: dict):
    """O prompt do RAGAS com o idioma, a instrução e os exemplos do dicionário (o contrário de _prompt_em_dicionario)."""
    prompt.language = dados["idioma"]
    prompt.instruction = dados["instrucao"]
    exemplos = []
    # Cada exemplo volta a ser o par de classes que o RAGAS usa para montar o texto do prompt
    for exemplo in dados["exemplos"]:
        exemplos.append((prompt.input_model(**exemplo["entrada"]), prompt.output_model(**exemplo["saida"])))
    prompt.examples = exemplos
    return prompt


async def _traduzir_prompts(juiz: JuizDoBedrock) -> dict:
    """Os 3 prompts traduzidos pelo próprio RAGAS (BasePrompt.adapt), com a instrução e os exemplos."""
    traduzidos = {}
    for nome, prompt in _prompts_originais().items():
        traduzidos[nome] = await prompt.adapt(IDIOMA_DOS_PROMPTS, juiz, adapt_instruction=True)
    return traduzidos


def prompts_em_portugues(juiz: JuizDoBedrock, caminho: Path = ARQUIVO_DOS_PROMPTS_EM_PORTUGUES) -> dict:
    """Os 3 prompts do RAGAS em português: {"afirmacoes", "veredito", "perguntas"}.

    Na primeira vez, o próprio RAGAS traduz (com o juiz) e grava em data/avaliacao/ragas_prompts_portugues.json, para
    quem mede conferir; nas outras, só lê o arquivo (a mesma tradução em toda medição, sem gastar de novo).
    """
    if not caminho.exists():
        traduzidos = asyncio.run(_traduzir_prompts(juiz))
        dados = {}
        for nome, prompt in traduzidos.items():
            dados[nome] = _prompt_em_dicionario(prompt)
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    prompts = {}
    # Cada prompt parte do original (a classe e o formato da resposta) e recebe o texto traduzido
    for nome, prompt in _prompts_originais().items():
        prompts[nome] = _prompt_do_dicionario(prompt, dados[nome])
    return prompts


def _valor_ou_nada(valor: float):
    """O valor da métrica, ou None quando o RAGAS devolve NaN ("não deu para medir")."""
    if valor is None or math.isnan(valor):
        return None
    return float(valor)


class MetricasDoRagas:
    """As métricas do RAGAS 0.4 (Faithfulness e AnswerRelevancy) com o nosso juiz: um juiz novo a cada medição.

    Recebe: modelo do juiz; caixa (o gasto e o teto); prompts (os 3 em português); embeddings (os do projeto);
    chamar (a função que chama a IA; os testes passam uma falsa).
    Cada método devolve o valor da métrica e os detalhes que o RAGAS não devolve (as afirmações com o veredito, as
    perguntas), lidos das respostas do juiz.
    """

    def __init__(self, modelo: str, caixa: CaixaDoGasto, prompts: dict, embeddings=None, chamar=None):
        """Guarda o que cada medição usa e liga o juiz e os embeddings ao RAGAS."""
        ligar_ao_ragas()
        self.modelo = modelo
        self.caixa = caixa
        self.prompts = prompts
        self.embeddings = embeddings or EmbeddingsDoProjeto()
        self._chamar = chamar

    def _novo_juiz(self) -> JuizDoBedrock:
        """Um juiz só para uma medição (as respostas dele não se misturam com as de outra)."""
        return JuizDoBedrock(self.modelo, self.caixa, self._chamar)

    async def fidelidade(self, pergunta: str, texto: str, contextos: list[str]) -> dict:
        """A fidelidade do RAGAS de um texto aos contextos: {valor, afirmacoes: [{afirmacao, veredito, motivo}],
        custo_usd, tokens_entrada, tokens_saida}. valor None: o juiz não achou afirmação nenhuma."""
        # Importado aqui: o RAGAS só existe no .venv-avaliacao
        from ragas.metrics.collections import Faithfulness
        juiz = self._novo_juiz()
        metrica = Faithfulness(llm=juiz)
        # Os prompts em português entram no lugar dos originais
        metrica.statement_generator_prompt = self.prompts["afirmacoes"]
        metrica.nli_statement_prompt = self.prompts["veredito"]
        resultado = await metrica.ascore(user_input=pergunta, response=texto, retrieved_contexts=contextos)
        afirmacoes = []
        # A 2ª resposta do juiz é a dos vereditos (a 1ª foi a lista de afirmações); sem afirmação, não há a 2ª
        if len(juiz.respostas) == 2:
            for veredito in juiz.respostas[1].statements:
                afirmacoes.append({"afirmacao": veredito.statement, "veredito": veredito.verdict,
                                   "motivo": veredito.reason})
        return {"valor": _valor_ou_nada(resultado.value), "afirmacoes": afirmacoes, "custo_usd": juiz.custo_usd,
                "tokens_entrada": juiz.tokens_entrada, "tokens_saida": juiz.tokens_saida}

    async def vereditos(self, afirmacoes: list[str], contextos: list[str]) -> dict:
        """O veredito do RAGAS para afirmações já prontas contra outros contextos (o mesmo prompt da fidelidade):
        {afirmacoes: [{afirmacao, veredito, motivo}], custo_usd, tokens_entrada, tokens_saida}."""
        # Importado aqui: o RAGAS só existe no .venv-avaliacao
        from ragas.metrics.collections.faithfulness.util import NLIStatementInput, NLIStatementOutput
        juiz = self._novo_juiz()
        # Os contextos juntos por quebra de linha, como a Faithfulness do RAGAS faz
        entrada = NLIStatementInput(context="\n".join(contextos), statements=afirmacoes)
        saida = await juiz.agenerate(self.prompts["veredito"].to_string(entrada), NLIStatementOutput)
        lista = []
        for veredito in saida.statements:
            lista.append({"afirmacao": veredito.statement, "veredito": veredito.verdict, "motivo": veredito.reason})
        return {"afirmacoes": lista, "custo_usd": juiz.custo_usd, "tokens_entrada": juiz.tokens_entrada,
                "tokens_saida": juiz.tokens_saida}

    async def relevancia(self, pergunta: str, texto: str) -> dict:
        """A relevância do RAGAS de um texto ao pedido: {valor, perguntas, evasivo, custo_usd, tokens_entrada,
        tokens_saida}. evasivo: o juiz achou o texto vago em todas as perguntas (aí o RAGAS zera a relevância)."""
        # Importado aqui: o RAGAS só existe no .venv-avaliacao
        from ragas.metrics.collections import AnswerRelevancy
        juiz = self._novo_juiz()
        metrica = AnswerRelevancy(llm=juiz, embeddings=self.embeddings, strictness=PERGUNTAS_DA_RELEVANCIA)
        # O prompt em português entra no lugar do original
        metrica.prompt = self.prompts["perguntas"]
        resultado = await metrica.ascore(user_input=pergunta, response=texto)
        perguntas = []
        evasivas = 0
        # Cada resposta do juiz é uma pergunta, com a marca de texto vago
        for resposta in juiz.respostas:
            perguntas.append(resposta.question)
            evasivas += resposta.noncommittal
        return {"valor": _valor_ou_nada(resultado.value), "perguntas": perguntas,
                "evasivo": bool(perguntas) and evasivas == len(perguntas), "custo_usd": juiz.custo_usd,
                "tokens_entrada": juiz.tokens_entrada, "tokens_saida": juiz.tokens_saida}


def rotulo_da_fidelidade(fidelidade) -> str:
    """O rótulo de 3 casas a partir da fidelidade do bloco (a mesma régua da planilha de rótulos).

    Exemplos: 1.0 → "fiel"; 0.0 → "não fiel"; 0.5 → "em parte"; None (sem afirmação medida) → "".
    """
    if fidelidade is None:
        return ""
    if fidelidade >= 1.0:
        return ROTULO_FIEL
    if fidelidade <= 0.0:
        return ROTULO_NAO_FIEL
    return ROTULO_EM_PARTE


def _linha_do_bloco(bloco: dict, material: dict) -> dict:
    """A linha do CSV de um bloco, ainda sem a medição (os dados do material e do bloco)."""
    return {"bloco_id": bloco["bloco_id"], "combinacao": material["combinacao"], "empresa_id": material["empresa_id"],
            "tipo": material["tipo"], "canal": material["canal"], "caso_do_destaque": material["caso_do_destaque"],
            "conjunto": material["conjunto"], "posicao": bloco["posicao"], "e_titulo": bloco["e_titulo"],
            "fontes": bloco["fontes"], "situacao": "", "afirmacoes": 0, "sustentadas_pela_fonte": 0,
            "sustentadas_em_outro_trecho": 0, "inventadas": 0, "sem_segundo_veredito": 0, "fidelidade": None,
            "fidelidade_ao_catalogo": None, "rotulo_do_juiz": "", "custo_usd": 0.0, "tokens_entrada": 0,
            "tokens_saida": 0, "erro": "", "texto": bloco["texto"], "detalhes": []}


def _somar_uso(linha: dict, medida: dict) -> None:
    """Soma na linha do bloco o custo e os tokens de uma medição do juiz."""
    linha["custo_usd"] += medida["custo_usd"]
    linha["tokens_entrada"] += medida["tokens_entrada"]
    linha["tokens_saida"] += medida["tokens_saida"]


def _segundo_veredito(afirmacao: str, posicao: int, segunda_medida: dict | None):
    """O veredito da afirmação contra todos os trechos do material, ou None se ela não foi conferida de novo.

    O juiz devolve as afirmações na ordem em que recebeu; se ele devolver outra quantidade, vale o texto igual.
    """
    if segunda_medida is None:
        return None
    lista = segunda_medida["afirmacoes"]
    # Mesma quantidade: a ordem casa as afirmações
    if posicao < len(lista) and lista[posicao]["afirmacao"] == afirmacao:
        return lista[posicao]
    # Outra quantidade: procura pelo texto igual
    for veredito in lista:
        if veredito["afirmacao"] == afirmacao:
            return veredito
    return None


def _contar_afirmacoes(linha: dict, afirmacoes: list[dict], segunda_medida: dict | None) -> None:
    """Conta as afirmações do bloco (sustentadas pela fonte, por outro trecho, inventadas) e guarda os detalhes.

    No título, o contexto já são todos os trechos do material: a afirmação que ele não sustenta é inventada.
    """
    posicao_na_segunda = 0
    for afirmacao in afirmacoes:
        detalhe = {"afirmacao": afirmacao["afirmacao"], "veredito": afirmacao["veredito"],
                   "motivo": afirmacao["motivo"]}
        linha["afirmacoes"] += 1
        if afirmacao["veredito"] == 1:
            linha["sustentadas_pela_fonte"] += 1
        elif linha["e_titulo"]:
            # O título foi conferido contra todos os trechos: sem sustentação, nenhum trecho a sustenta
            linha["inventadas"] += 1
            detalhe["veredito_no_catalogo"] = 0
            detalhe["motivo_no_catalogo"] = afirmacao["motivo"]
        else:
            # A afirmação sem sustentação na fonte citada foi conferida contra todos os trechos do material
            segundo = _segundo_veredito(afirmacao["afirmacao"], posicao_na_segunda, segunda_medida)
            posicao_na_segunda += 1
            if segundo is None:
                linha["sem_segundo_veredito"] += 1
            elif segundo["veredito"] == 1:
                linha["sustentadas_em_outro_trecho"] += 1
                detalhe["veredito_no_catalogo"] = 1
                detalhe["motivo_no_catalogo"] = segundo["motivo"]
            else:
                linha["inventadas"] += 1
                detalhe["veredito_no_catalogo"] = 0
                detalhe["motivo_no_catalogo"] = segundo["motivo"]
        linha["detalhes"].append(detalhe)


async def medir_bloco(bloco: dict, material: dict, metricas, parada: dict) -> dict:
    """A fidelidade de um bloco (ou do título) e o que cada afirmação dele tem de sustentação.

    Recebe: bloco e material (da amostra); metricas (as do RAGAS, ou as falsas dos testes); parada ({"teto": bool},
    comum a todas as medições: depois do teto, nenhum bloco chama o juiz).
    Devolve: a linha do CSV dos blocos. O título já é medido contra todos os trechos: não há 2ª conferência.
    """
    linha = _linha_do_bloco(bloco, material)
    # O teto já foi atingido por outra medição: este bloco fica sem medir
    if parada["teto"]:
        linha["situacao"] = BLOCO_PARADO_PELO_TETO
        return linha
    try:
        # A pergunta neutra: sem ela, o juiz tiraria afirmações da pergunta, e não do texto (PERGUNTA_DA_FIDELIDADE)
        medida = await metricas.fidelidade(PERGUNTA_DA_FIDELIDADE, bloco["texto"], bloco["contexto_citado"])
        _somar_uso(linha, medida)
        # As afirmações que a fonte citada não sustenta são conferidas contra todos os trechos do material
        sem_sustentacao = []
        for afirmacao in medida["afirmacoes"]:
            if afirmacao["veredito"] != 1:
                sem_sustentacao.append(afirmacao["afirmacao"])
        segunda_medida = None
        if sem_sustentacao and not bloco["e_titulo"]:
            segunda_medida = await metricas.vereditos(sem_sustentacao, material["contexto_do_material"])
            _somar_uso(linha, segunda_medida)
    except TetoAtingido:
        # Chegou ao teto: este e os próximos blocos ficam sem medir
        parada["teto"] = True
        linha["situacao"] = BLOCO_PARADO_PELO_TETO
        return linha
    except Exception as erro:  # noqa: BLE001 - um erro do juiz num bloco não pode perder a medição inteira
        linha["situacao"] = BLOCO_ERRO_DO_JUIZ
        linha["erro"] = f"{type(erro).__name__}: {str(erro)[:200]}"
        return linha
    # Sem afirmação nenhuma, não há fidelidade a medir (o RAGAS devolve NaN)
    if not medida["afirmacoes"]:
        linha["situacao"] = BLOCO_SEM_AFIRMACAO
        return linha
    _contar_afirmacoes(linha, medida["afirmacoes"], segunda_medida)
    linha["situacao"] = BLOCO_MEDIDO
    # A fidelidade do RAGAS (a parte sustentada pela fonte citada) e a fidelidade ao catálogo inteiro do material
    linha["fidelidade"] = medida["valor"]
    sustentadas_no_catalogo = linha["sustentadas_pela_fonte"] + linha["sustentadas_em_outro_trecho"]
    linha["fidelidade_ao_catalogo"] = sustentadas_no_catalogo / linha["afirmacoes"]
    linha["rotulo_do_juiz"] = rotulo_da_fidelidade(linha["fidelidade"])
    return linha


async def medir_relevancia(material: dict, metricas, parada: dict) -> dict:
    """A relevância do material ao pedido: {valor, perguntas, evasivo, custo_usd, ..., erro}."""
    vazio = {"valor": None, "perguntas": [], "evasivo": False, "custo_usd": 0.0, "tokens_entrada": 0,
             "tokens_saida": 0, "erro": ""}
    # O teto já foi atingido: a relevância fica sem medir
    if parada["teto"]:
        vazio["erro"] = BLOCO_PARADO_PELO_TETO
        return vazio
    try:
        medida = await metricas.relevancia(material["pergunta"], material["texto_sem_fontes"])
    except TetoAtingido:
        parada["teto"] = True
        vazio["erro"] = BLOCO_PARADO_PELO_TETO
        return vazio
    except Exception as erro:  # noqa: BLE001 - um erro do juiz num material não pode perder a medição inteira
        vazio["erro"] = f"{type(erro).__name__}: {str(erro)[:200]}"
        return vazio
    medida["erro"] = ""
    return medida


def resumo_do_material(material: dict, linhas_dos_blocos: list[dict], relevancia: dict) -> dict:
    """A linha do CSV de um material: as afirmações somadas dos blocos de conteúdo, o título à parte e a relevância.

    A fidelidade do material é a das afirmações somadas (e não a média dos blocos): um bloco com 6 afirmações pesa mais
    que um com 1. O título conta à parte: ele não cita fonte (é conferido contra todos os trechos) e, numa frase de
    efeito ("Bem-vindo(a) à Aurora!"), o RAGAS tira afirmações sobre o próprio texto ("o texto dá boas-vindas"), que
    não são fato do catálogo (visto no ensaio com 3 materiais). É a mesma régua da planilha, que não tem títulos.
    """
    linha = {"combinacao": material["combinacao"], "empresa_id": material["empresa_id"],
             "empresa": material["empresa"], "tipo": material["tipo"], "canal": material["canal"],
             "caso_do_destaque": material["caso_do_destaque"], "conjunto": material["conjunto"],
             "beneficios": material["beneficios"], "blocos": len(linhas_dos_blocos) - 1, "situacao": MATERIAL_MEDIDO,
             "afirmacoes": 0, "sustentadas_pela_fonte": 0, "sustentadas_em_outro_trecho": 0, "inventadas": 0,
             "fidelidade_do_material": None, "fidelidade_ao_catalogo": None, "blocos_fieis": 0, "blocos_em_parte": 0,
             "blocos_nao_fieis": 0, "titulo_afirmacoes": 0, "titulo_inventadas": 0, "relevancia": relevancia["valor"],
             "evasivo": relevancia["evasivo"], "perguntas": relevancia["perguntas"],
             "custo_usd": relevancia["custo_usd"], "erro": relevancia["erro"]}
    # A relevância que não saiu deixa o material incompleto
    if relevancia["erro"]:
        linha["situacao"] = MATERIAL_INCOMPLETO
    for bloco in linhas_dos_blocos:
        linha["custo_usd"] += bloco["custo_usd"]
        # Um bloco sem medida (erro ou teto) deixa o material incompleto
        if bloco["situacao"] not in (BLOCO_MEDIDO, BLOCO_SEM_AFIRMACAO):
            linha["situacao"] = MATERIAL_INCOMPLETO
            continue
        # O título conta à parte
        if bloco["e_titulo"]:
            linha["titulo_afirmacoes"] = bloco["afirmacoes"]
            linha["titulo_inventadas"] = bloco["inventadas"]
            continue
        linha["afirmacoes"] += bloco["afirmacoes"]
        linha["sustentadas_pela_fonte"] += bloco["sustentadas_pela_fonte"]
        linha["sustentadas_em_outro_trecho"] += bloco["sustentadas_em_outro_trecho"]
        linha["inventadas"] += bloco["inventadas"]
        # O rótulo do bloco (vazio quando não há afirmação)
        if not bloco["rotulo_do_juiz"]:
            continue
        if bloco["rotulo_do_juiz"] == ROTULO_FIEL:
            linha["blocos_fieis"] += 1
        elif bloco["rotulo_do_juiz"] == ROTULO_EM_PARTE:
            linha["blocos_em_parte"] += 1
        else:
            linha["blocos_nao_fieis"] += 1
    # As fidelidades do material, com as afirmações somadas
    if linha["afirmacoes"]:
        linha["fidelidade_do_material"] = linha["sustentadas_pela_fonte"] / linha["afirmacoes"]
        sustentadas_no_catalogo = linha["sustentadas_pela_fonte"] + linha["sustentadas_em_outro_trecho"]
        linha["fidelidade_ao_catalogo"] = sustentadas_no_catalogo / linha["afirmacoes"]
    return linha


async def _medir_material(material: dict, metricas, limite: asyncio.Semaphore, parada: dict,
                          avisar=None) -> tuple[list[dict], dict]:
    """Os blocos (um de cada vez) e a relevância de um material; o limite segura quantas medições correm juntas."""
    linhas_dos_blocos = []
    for bloco in material["blocos"]:
        async with limite:
            linhas_dos_blocos.append(await medir_bloco(bloco, material, metricas, parada))
    async with limite:
        relevancia = await medir_relevancia(material, metricas, parada)
    resumo = resumo_do_material(material, linhas_dos_blocos, relevancia)
    # O aviso de progresso (o script mostra na tela)
    if avisar is not None:
        avisar(resumo)
    return linhas_dos_blocos, resumo


async def _julgar_todos(materiais: list[dict], metricas, medicoes_ao_mesmo_tempo: int,
                        avisar=None) -> tuple[list[dict], list[dict]]:
    """Mede todos os materiais, com até medicoes_ao_mesmo_tempo medições correndo juntas."""
    limite = asyncio.Semaphore(medicoes_ao_mesmo_tempo)
    # O sinal comum de parada: o primeiro que bater no teto avisa os outros
    parada = {"teto": False}
    tarefas = []
    for material in materiais:
        tarefas.append(_medir_material(material, metricas, limite, parada, avisar))
    resultados = await asyncio.gather(*tarefas)
    blocos = []
    resumos = []
    # Junta os blocos e os materiais, na ordem das amostras
    for linhas_dos_blocos, resumo in resultados:
        blocos.extend(linhas_dos_blocos)
        resumos.append(resumo)
    return blocos, resumos


def julgar(materiais: list[dict], metricas, medicoes_ao_mesmo_tempo: int = MEDICOES_AO_MESMO_TEMPO,
           avisar=None) -> tuple[list[dict], list[dict]]:
    """A etapa 2: a fidelidade de cada bloco e a relevância de cada material cujo catálogo confere.

    Recebe: materiais (as amostras da etapa 1); metricas (MetricasDoRagas, ou as falsas dos testes); avisar (uma
    função chamada a cada material pronto, para mostrar o progresso).
    Devolve: (as linhas dos blocos, as linhas dos materiais).
    """
    medidos = []
    # O material cujo catálogo mudou fica de fora (o trecho de hoje não é o que a IA recebeu)
    for material in materiais:
        if material["catalogo_confere"]:
            medidos.append(material)
    return asyncio.run(_julgar_todos(medidos, metricas, medicoes_ao_mesmo_tempo, avisar))


# ============================== Os CSVs dos resultados ==============================

# As colunas de cada CSV, na ordem em que são gravadas
COLUNAS_DOS_BLOCOS = ("bloco_id", "combinacao", "empresa_id", "tipo", "canal", "caso_do_destaque", "conjunto",
                      "posicao", "e_titulo", "fontes", "situacao", "afirmacoes", "sustentadas_pela_fonte",
                      "sustentadas_em_outro_trecho", "inventadas", "sem_segundo_veredito", "fidelidade",
                      "fidelidade_ao_catalogo", "rotulo_do_juiz", "custo_usd", "tokens_entrada", "tokens_saida",
                      "erro", "texto", "detalhes")
COLUNAS_DOS_MATERIAIS = ("combinacao", "empresa_id", "empresa", "tipo", "canal", "caso_do_destaque", "conjunto",
                         "beneficios", "blocos", "situacao", "afirmacoes", "sustentadas_pela_fonte",
                         "sustentadas_em_outro_trecho", "inventadas", "fidelidade_do_material",
                         "fidelidade_ao_catalogo", "blocos_fieis", "blocos_em_parte", "blocos_nao_fieis",
                         "titulo_afirmacoes", "titulo_inventadas", "relevancia", "evasivo", "perguntas", "custo_usd",
                         "erro")
# O tipo de cada coluna, para ler o CSV de volta
COLUNAS_INTEIRAS = ("posicao", "afirmacoes", "sustentadas_pela_fonte", "sustentadas_em_outro_trecho", "inventadas",
                    "sem_segundo_veredito", "tokens_entrada", "tokens_saida", "blocos", "blocos_fieis",
                    "blocos_em_parte", "blocos_nao_fieis", "titulo_afirmacoes", "titulo_inventadas")
COLUNAS_DECIMAIS = ("fidelidade", "fidelidade_ao_catalogo", "fidelidade_do_material", "relevancia", "custo_usd")
COLUNAS_SIM_OU_NAO = ("e_titulo", "evasivo")
COLUNAS_EM_JSON = ("fontes", "beneficios", "perguntas", "detalhes")


def _celula(coluna: str, valor) -> str:
    """O valor de uma célula como texto: lista em JSON, sim/não, vazio para None, número como está."""
    if coluna in COLUNAS_EM_JSON:
        return json.dumps(valor, ensure_ascii=False)
    if coluna in COLUNAS_SIM_OU_NAO:
        if valor:
            return "sim"
        return "nao"
    if valor is None:
        return ""
    # O custo e as fidelidades com 6 casas (o bastante para somar sem perder centavos)
    if isinstance(valor, float):
        return f"{valor:.6f}"
    return str(valor)


def gravar_csv(linhas: list[dict], colunas: tuple, caminho: Path) -> None:
    """Grava as linhas no CSV (separador ";", como o Excel em português abre)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";", lineterminator="\n")
        escritor.writerow(colunas)
        for linha in linhas:
            celulas = []
            for coluna in colunas:
                celulas.append(_celula(coluna, linha[coluna]))
            escritor.writerow(celulas)


def _valor_da_celula(coluna: str, texto: str):
    """O valor de uma célula do CSV no tipo certo (o contrário de _celula)."""
    if coluna in COLUNAS_EM_JSON:
        return json.loads(texto)
    if coluna in COLUNAS_SIM_OU_NAO:
        return texto == "sim"
    # Os números: vazio é "não medido" (None)
    if coluna in COLUNAS_INTEIRAS:
        if texto == "":
            return None
        return int(texto)
    if coluna in COLUNAS_DECIMAIS:
        if texto == "":
            return None
        return float(texto)
    return texto


def ler_csv(caminho: Path) -> list[dict]:
    """As linhas de um CSV gravado por gravar_csv, com cada valor no tipo certo."""
    linhas = []
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        for linha_lida in csv.DictReader(arquivo, delimiter=";"):
            linha = {}
            for coluna, texto in linha_lida.items():
                linha[coluna] = _valor_da_celula(coluna, texto)
            linhas.append(linha)
    return linhas
