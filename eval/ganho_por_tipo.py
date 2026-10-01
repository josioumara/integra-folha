"""Régua da prova por tipo de arquivo: quanto a IA acrescenta ao acerto e às perguntas, em cada tipo de arquivo.

Recebe o que a medição (scripts/avaliar_ganho_por_tipo.py) guardou de cada arquivo nos dois braços, sem IA e com IA,
e compara com o gabarito do manifesto (data/avaliacao/prova_por_tipo/manifesto.json). O mesmo arquivo passa pelos
dois braços; só muda quem entende o arquivo: as regras (o dicionário B0, a leitura de tabela e de fichas) ou a IA.

As medidas de cada arquivo:
- ACERTO POR CAMPO: das células que o gabarito espera (pessoa × campo que o arquivo traz), quantas ficaram com o valor
  certo nos dados do envio. A empresa responde só o que o sistema perguntou sobre as COLUNAS (a coluna em dúvida e a
  que o aceite recusou) e o formato de uma coluna; as pendências das pessoas ficam sem resposta (elas são o trabalho
  que sobra). Os dois lados passam pela mesma padronização do sistema;
- OS 4 OBRIGATÓRIOS CERTOS (a medida principal, ADR-143): as pessoas com CPF, CBO, renda e admissão certos. No texto
  misturado, o obrigatório que a armadilha tira de propósito (o CPF que "vem depois", as duas datas de admissão) conta
  como certo quando fica em branco e vira pergunta;
- PESSOAS SEM PERGUNTA: as pessoas prontas para ir ao banco (nenhuma pendência nelas nem no arquivo inteiro) E com os
  4 obrigatórios certos. A pessoa pronta com um obrigatório errado é o ERRO SILENCIOSO: iria errada ao banco;
- PERGUNTAS: tudo o que a empresa precisa responder: as colunas, o formato de uma coluna, as pendências das pessoas e
  as do arquivo inteiro (as das pessoas e do arquivo são o mesmo número que a tela mostra);
- ALARMES FALSOS: as pendências de uma pessoa num campo cujo valor já está certo (o dado estava bom e o sistema
  perguntou assim mesmo);
- COLUNAS CERTAS (planilhas e tabelas): a coluna foi para o campo certo, foi dividida nos campos certos ou ficou de
  fora quando devia;
- TEMPO e CUSTO: os segundos do envio (da leitura ao aceite) e o custo das chamadas reais à IA.

O arquivo que o sistema recusa (o texto corrido sem a IA) não tem dados: todas as células contam como erradas, e
nenhuma pessoa é cadastrada.

O GANHO de um tipo é o com IA menos o sem IA, nos mesmos arquivos e nas mesmas células: o McNemar exato
(eval/teste_pareado.py), o intervalo de confiança sorteando os arquivos (bootstrap) e o custo por ponto ganho.
"""
from eval import teste_pareado
from eval.avaliacao_do_leitor import casar_pessoas, valores_iguais
from services import tabela_cbo

# Os 4 campos obrigatórios do parâmetro (ADR-143)
CAMPOS_OBRIGATORIOS = ("cpf", "codigo_cbo", "valor_renda", "data_admissao")
# Os tipos em que cada linha do arquivo é uma pessoa, na ordem do arquivo (planilhas, tabela e fichas)
GRUPOS_POR_LINHA = ("planilha",)
# O sinal que separa o nome da coluna dividida e o nome da parte ("Nome - CPF · parte 1")
SINAL_DA_PARTE = " · "
# O nome que a leitura dá a uma coluna sem nome ("Coluna 5")
NOME_DA_COLUNA_SEM_NOME = "Coluna {posicao}"


# ============================== Comparar um valor ==============================

def valor_certo(esperado: str, lido: str, campo) -> bool:
    """True se o valor dos dados do envio é o certo.

    Recebe: o valor certo (do manifesto), o que ficou nos dados e o CampoLayout. O código da profissão é comparado pelo
    código (sem pontos e traços: "4110-10" é o 411010); os outros, pela padronização do sistema (a mesma régua do
    Leitor de Documentos, eval/avaliacao_do_leitor.py).
    """
    # Sem valor nos dados, está errado (o esperado nunca é vazio: células vazias não entram no gabarito)
    if not lido:
        return False
    # O código da profissão: o mesmo código, escrito de qualquer jeito
    if campo.campo == "codigo_cbo":
        return tabela_cbo.codigo_normalizado(lido) == tabela_cbo.codigo_normalizado(esperado)
    return valores_iguais(esperado, str(lido), campo)


# ============================== Achar cada pessoa nos dados ==============================

def casar_registros(entrada: dict, grupo: str, registros: list[dict], valores_por_pessoa: dict) -> dict:
    """Qual registro dos dados do envio é cada pessoa do gabarito. Devolve {pessoa_id: registro ou None}.

    Nas planilhas, cada linha do arquivo é uma pessoa, na ordem do manifesto: casa pela ordem das linhas (não depende
    de o sistema ter lido certo o CPF ou o nome). Nos documentos, a leitura pode juntar ou separar pessoas: casa pelo
    CPF, pelo e-mail ou pelo nome (a mesma régua do Leitor de Documentos).
    """
    ids_das_pessoas = []
    for gabarito in entrada["gabarito"]:
        ids_das_pessoas.append(gabarito["pessoa_id"])
    # Os registros na ordem das linhas do arquivo
    ordenados = sorted(registros, key=_linha_do_registro)
    casados = {}
    # Planilha com uma linha por pessoa: pela ordem
    if grupo in GRUPOS_POR_LINHA and len(ordenados) == len(ids_das_pessoas):
        for pessoa_id, registro in zip(ids_das_pessoas, ordenados):
            casados[pessoa_id] = registro
        return casados
    # Documento (ou planilha com linhas a mais ou a menos): pelo CPF, e-mail ou nome
    esperadas = []
    for pessoa_id in ids_das_pessoas:
        valores = valores_por_pessoa[pessoa_id]
        esperadas.append({"campos": {"cpf": valores["cpf"], "email_pessoal": valores["email_pessoal"],
                                     "nome_completo": valores["nome_completo"]}})
    lidas = []
    for registro in ordenados:
        lidas.append(_registro_em_texto(registro))
    for posicao_esperada, posicao_lida in casar_pessoas(esperadas, lidas):
        registro = None
        if posicao_lida is not None:
            registro = ordenados[posicao_lida]
        casados[ids_das_pessoas[posicao_esperada]] = registro
    return casados


def _linha_do_registro(registro: dict) -> int:
    """A linha do registro no arquivo (serve para ordenar os registros)."""
    return registro.get("_linha") or 0


def _registro_em_texto(registro: dict) -> dict:
    """O registro com os valores em texto, sem as marcas internas (as chaves que começam com "_")."""
    em_texto = {}
    for campo, valor in registro.items():
        if not campo.startswith("_") and valor not in (None, ""):
            em_texto[campo] = str(valor)
    return em_texto


# ============================== As pendências ==============================

def pendencias_por_linha(pendencias: list[dict]) -> dict:
    """As pendências abertas de cada pessoa: {linha: [campo, ...]} (o campo pode ser None: a pessoa toda).

    As pendências do arquivo inteiro (linha None) ficam de fora: elas são contadas à parte.
    """
    por_linha = {}
    for pendencia in pendencias:
        if pendencia["linha"] is None:
            continue
        por_linha.setdefault(pendencia["linha"], []).append(pendencia["campo"])
    return por_linha


def contar_perguntas(bruto: dict) -> dict:
    """Tudo o que a empresa precisa responder no arquivo, por tipo de pergunta, e o total.

    Recebe: o que a medição guardou do arquivo (as perguntas das colunas e dos formatos, que ela contou ao responder,
    e o resumo das pendências da tela). Devolve: {de_coluna, de_formato, de_pessoa, no_arquivo, total}.
    """
    resumo = bruto.get("resumo_das_pendencias") or {}
    perguntas = {"de_coluna": bruto.get("perguntas_de_coluna", 0), "de_formato": bruto.get("perguntas_de_formato", 0),
                 "de_pessoa": resumo.get("corrigir", 0) + resumo.get("confirmar", 0),
                 "no_arquivo": resumo.get("no_arquivo", 0)}
    perguntas["total"] = (perguntas["de_coluna"] + perguntas["de_formato"] + perguntas["de_pessoa"]
                          + perguntas["no_arquivo"])
    return perguntas


# ============================== As colunas ==============================

def colunas_esperadas(entrada: dict) -> list[dict]:
    """O que cada coluna do arquivo devia virar: [{nome, esperado, campos}].

    Nas planilhas, vem das colunas do manifesto (a coluna sem nome é lida como "Coluna N"); na tabela e nas fichas do
    Word, do cabeçalho de cada coluna (ou do rótulo de cada ficha). No texto corrido, não há colunas: lista vazia.
    """
    esperadas = []
    for coluna in entrada.get("colunas", []):
        nome = coluna["cabecalho"].strip()
        # A coluna sem nome ganha "Coluna N" na leitura
        if not nome:
            nome = NOME_DA_COLUNA_SEM_NOME.format(posicao=coluna["posicao"])
        esperadas.append({"nome": nome, "esperado": coluna["esperado"], "campos": coluna["campos"]})
    for cabecalho, campo in entrada.get("cabecalho_para_campo", {}).items():
        esperadas.append({"nome": cabecalho, "esperado": campo, "campos": [campo]})
    return esperadas


def coluna_certa(esperada: dict, item: dict | None) -> bool:
    """True se a decisão final sobre a coluna é a certa.

    Recebe: a coluna esperada e o item final do mapeamento aprovado ({coluna, campo, partes}; None se a coluna sumiu).
    Campo esperado → o item tem esse campo. Ambígua ou a mais → a coluna ficou de fora (sem campo e sem divisão).
    Dividir → a coluna foi dividida, e as partes levam os campos esperados (ex.: o nome e o CPF).
    """
    if item is None:
        return False
    if esperada["esperado"] in ("AMBIGUO", "NAO_MAPEADO"):
        return item["campo"] is None and not item.get("partes")
    if esperada["esperado"] == "DIVIDIR":
        return set(esperada["campos"]) <= set(item.get("partes") or [])
    return item["campo"] == esperada["esperado"]


def medir_colunas(entrada: dict, colunas_finais: list[dict]) -> dict:
    """Quantas colunas do arquivo terminaram certas. Devolve {certas, total, erradas: [nome, ...]}."""
    item_pelo_nome = {}
    for item in colunas_finais:
        item_pelo_nome[_nome_limpo(item["coluna"])] = item
    medida = {"certas": 0, "total": 0, "erradas": []}
    for esperada in colunas_esperadas(entrada):
        medida["total"] += 1
        if coluna_certa(esperada, item_pelo_nome.get(_nome_limpo(esperada["nome"]))):
            medida["certas"] += 1
        else:
            medida["erradas"].append(esperada["nome"])
    return medida


def _nome_limpo(nome: str) -> str:
    """O nome da coluna sem espaços sobrando (" Nacion.  " → "Nacion."), para comparar."""
    return " ".join(str(nome).split())


# ============================== Medir um arquivo ==============================

def _obrigatorio_resolvido(campo: str, gabarito: dict, registro: dict, campos_da_pendencia: list,
                           certos: dict) -> bool:
    """True se o obrigatório da pessoa terminou do jeito certo.

    Recebe: o campo, o gabarito da pessoa, o registro dela, os campos das pendências dela e as células certas.
    Campo no gabarito → o valor certo. Campo que a armadilha tira (o CPF que vem depois, as duas datas de admissão) →
    em branco e com uma pergunta sobre ele (ou sobre a pessoa toda).
    """
    if campo in gabarito["campos"]:
        return certos.get(campo, False)
    # Tirado pela armadilha: não pode ser inventado, e alguém precisa perguntar
    em_branco = not registro.get(campo)
    perguntou = campo in campos_da_pendencia or None in campos_da_pendencia
    return em_branco and perguntou


def _campos_tirados_pela_armadilha(gabarito: dict) -> list[str]:
    """Os campos que o texto misturado tira de propósito da pessoa: os da armadilha e o CPF que "vem depois"."""
    tirados = list(gabarito.get("armadilhas", []))
    if gabarito.get("armadilha") == "cpf_depois":
        tirados.append("cpf")
    return tirados


def medir_pessoa(gabarito: dict, valores: dict, registro: dict | None, campos_da_pendencia: list,
                 campos_por_nome: dict, arquivo_tem_pendencia: bool) -> dict:
    """As medidas de uma pessoa: as células, os 4 obrigatórios, se ficou pronta, os alarmes falsos e as armadilhas."""
    registro_em_texto = _registro_em_texto(registro or {})
    celulas = []
    certos = {}
    for campo in gabarito["campos"]:
        certo = registro is not None and valor_certo(valores[campo], registro_em_texto.get(campo, ""),
                                                     campos_por_nome[campo])
        certos[campo] = certo
        celulas.append({"pessoa_id": gabarito["pessoa_id"], "campo": campo, "certo": certo,
                        "obrigatorio": campo in CAMPOS_OBRIGATORIOS})
    # Os 4 obrigatórios (os tirados pela armadilha contam quando ficam em branco e viram pergunta)
    obrigatorios_certos = registro is not None
    for campo in CAMPOS_OBRIGATORIOS:
        if not _obrigatorio_resolvido(campo, gabarito, registro_em_texto, campos_da_pendencia, certos):
            obrigatorios_certos = False
    # Pronta: foi lida, não tem pendência e o arquivo inteiro também não
    pronta = registro is not None and not campos_da_pendencia and not arquivo_tem_pendencia
    # Alarme falso: a pendência num campo que já está certo
    alarmes_falsos = 0
    for campo in campos_da_pendencia:
        if campo is not None and certos.get(campo):
            alarmes_falsos += 1
    # As armadilhas: o campo tirado de propósito não pode ter valor (nada inventado)
    tirados = _campos_tirados_pela_armadilha(gabarito)
    respeitadas = 0
    for campo in tirados:
        if not registro_em_texto.get(campo):
            respeitadas += 1
    # A pergunta esperada: só a do obrigatório tirado pela armadilha (campo opcional não pergunta, ADR-143)
    esperada = False
    feita = False
    for campo in tirados:
        if campo in CAMPOS_OBRIGATORIOS:
            esperada = True
            if campo in campos_da_pendencia or None in campos_da_pendencia:
                feita = True
    return {"pessoa_id": gabarito["pessoa_id"], "celulas": celulas, "encontrada": registro is not None,
            "obrigatorios_certos": obrigatorios_certos, "sem_pergunta": pronta and obrigatorios_certos,
            "erro_silencioso": pronta and not obrigatorios_certos, "alarmes_falsos": alarmes_falsos,
            "armadilhas": len(tirados), "armadilhas_respeitadas": respeitadas,
            "pergunta_esperada": esperada, "pergunta_feita": esperada and feita}


def medir_arquivo(entrada: dict, grupo: str, bruto: dict, valores_por_pessoa: dict, campos_por_nome: dict) -> dict:
    """As medidas de um arquivo num braço (sem IA ou com IA).

    Recebe: a entrada do manifesto; o grupo do tipo ("planilha" ou "documento"); o que a medição guardou (bruto); os
    valores certos de cada pessoa; e {nome: CampoLayout} do parâmetro usado.
    Devolve: as medidas do arquivo, com a lista de células e de pessoas (para o teste pareado).
    """
    recusado = bruto.get("recusado") or bruto.get("travado_no_aceite")
    registros = []
    if not recusado:
        registros = bruto.get("registros", [])
    casados = casar_registros(entrada, grupo, registros, valores_por_pessoa)
    por_linha = pendencias_por_linha(bruto.get("pendencias", []))
    resumo = bruto.get("resumo_das_pendencias") or {}
    arquivo_tem_pendencia = resumo.get("no_arquivo", 0) > 0
    pessoas = []
    for gabarito in entrada["gabarito"]:
        registro = casados.get(gabarito["pessoa_id"])
        campos_da_pendencia = []
        if registro is not None:
            campos_da_pendencia = por_linha.get(registro.get("_linha"), [])
        pessoas.append(medir_pessoa(gabarito, valores_por_pessoa[gabarito["pessoa_id"]], registro,
                                    campos_da_pendencia, campos_por_nome, arquivo_tem_pendencia))
    medida = {"arquivo": entrada["arquivo"], "tipo": entrada["tipo"], "numero": entrada["numero"],
              "braco": bruto.get("braco"), "recusado": recusado, "pessoas": pessoas,
              "perguntas": None if recusado else contar_perguntas(bruto),
              "colunas": None, "segundos": bruto.get("segundos", 0.0), "custo_usd": bruto.get("custo_usd", 0.0),
              "chamadas_reais": bruto.get("chamadas_reais", 0), "chamadas_simuladas": bruto.get("chamadas_simuladas", 0)}
    # As colunas (planilhas, tabela e fichas), quando o arquivo chegou ao aceite
    if colunas_esperadas(entrada) and not recusado:
        medida["colunas"] = medir_colunas(entrada, bruto.get("colunas_finais", []))
    return medida


# ============================== Resumir um tipo num braço ==============================

def _dividir(parte: float, total: float) -> float:
    """parte ÷ total, ou 0 se não há total."""
    if not total:
        return 0.0
    return parte / total


def _percentil(valores: list[float], fracao: float) -> float:
    """O percentil pelo método "mais próximo" (com 5 arquivos, o p95 é o mais lento). Ex.: fracao 0.5 = a mediana."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    posicao = max(0, min(len(ordenados) - 1, round(fracao * len(ordenados) + 0.5) - 1))
    return ordenados[posicao]


def resumir(medidas: list[dict]) -> dict:
    """O resumo de um tipo num braço (os 5 arquivos): as porcentagens, as perguntas, o tempo e o custo."""
    total = {"arquivos": len(medidas), "recusados": 0, "pessoas": 0, "celulas": 0, "celulas_certas": 0,
             "obrigatorios_certos": 0, "sem_pergunta": 0, "erro_silencioso": 0, "encontradas": 0,
             "alarmes_falsos": 0, "armadilhas": 0, "armadilhas_respeitadas": 0, "perguntas_esperadas": 0,
             "perguntas_feitas": 0, "perguntas": 0, "colunas": 0, "colunas_certas": 0, "custo_usd": 0.0,
             "chamadas_reais": 0, "chamadas_simuladas": 0}
    segundos = []
    for medida in medidas:
        if medida["recusado"]:
            total["recusados"] += 1
        segundos.append(medida["segundos"])
        total["custo_usd"] += medida["custo_usd"] or 0.0
        total["chamadas_reais"] += medida["chamadas_reais"]
        total["chamadas_simuladas"] += medida["chamadas_simuladas"]
        if medida["perguntas"] is not None:
            total["perguntas"] += medida["perguntas"]["total"]
        if medida["colunas"] is not None:
            total["colunas"] += medida["colunas"]["total"]
            total["colunas_certas"] += medida["colunas"]["certas"]
        _somar_pessoas(total, medida["pessoas"])
    return {"arquivos": total["arquivos"], "recusados": total["recusados"], "pessoas": total["pessoas"],
            "acerto_por_campo": _dividir(total["celulas_certas"], total["celulas"]),
            "celulas": total["celulas"], "celulas_certas": total["celulas_certas"],
            "obrigatorios_certos": _dividir(total["obrigatorios_certos"], total["pessoas"]),
            "sem_pergunta": _dividir(total["sem_pergunta"], total["pessoas"]),
            "erro_silencioso": total["erro_silencioso"], "pessoas_encontradas": total["encontradas"],
            "perguntas_por_arquivo": _perguntas_por_arquivo(total),
            "perguntas_por_pessoa": _dividir(total["perguntas"], total["pessoas"]),
            "alarmes_falsos": total["alarmes_falsos"],
            "armadilhas_respeitadas": f"{total['armadilhas_respeitadas']} de {total['armadilhas']}",
            "perguntas_esperadas_feitas": f"{total['perguntas_feitas']} de {total['perguntas_esperadas']}",
            "colunas_certas": _dividir(total["colunas_certas"], total["colunas"]) if total["colunas"] else None,
            "segundos_p50": _percentil(segundos, 0.5), "segundos_p95": _percentil(segundos, 0.95),
            "custo_usd": round(total["custo_usd"], 4),
            "custo_por_arquivo_usd": round(_dividir(total["custo_usd"], total["arquivos"]), 4),
            "custo_por_funcionario_usd": round(_dividir(total["custo_usd"], total["pessoas"]), 4),
            "chamadas_reais": total["chamadas_reais"], "chamadas_simuladas": total["chamadas_simuladas"]}


def _perguntas_por_arquivo(total: dict) -> float | None:
    """As perguntas por arquivo lido; None quando todos foram recusados (não houve o que perguntar: o arquivo voltou)."""
    lidos = total["arquivos"] - total["recusados"]
    if lidos == 0:
        return None
    return total["perguntas"] / lidos


def _somar_pessoas(total: dict, pessoas: list[dict]) -> None:
    """Soma as medidas das pessoas de um arquivo no total do tipo."""
    for pessoa in pessoas:
        total["pessoas"] += 1
        total["encontradas"] += int(pessoa["encontrada"])
        total["obrigatorios_certos"] += int(pessoa["obrigatorios_certos"])
        total["sem_pergunta"] += int(pessoa["sem_pergunta"])
        total["erro_silencioso"] += int(pessoa["erro_silencioso"])
        total["alarmes_falsos"] += pessoa["alarmes_falsos"]
        total["armadilhas"] += pessoa["armadilhas"]
        total["armadilhas_respeitadas"] += pessoa["armadilhas_respeitadas"]
        total["perguntas_esperadas"] += int(pessoa["pergunta_esperada"])
        total["perguntas_feitas"] += int(pessoa["pergunta_feita"])
        for celula in pessoa["celulas"]:
            total["celulas"] += 1
            total["celulas_certas"] += int(celula["certo"])


# ============================== O ganho de um tipo ==============================

def _pares_das_celulas(medidas_sem_ia: list[dict], medidas_com_ia: list[dict]) -> dict:
    """Os pares (sem IA acertou?, com IA acertou?) de cada célula, agrupados por arquivo: {arquivo: [pares]}.

    Só entram os arquivos medidos nos dois braços (a trava de custo pode ter parado o com IA antes do fim).
    """
    certo_sem_ia = {}
    for medida in medidas_sem_ia:
        for pessoa in medida["pessoas"]:
            for celula in pessoa["celulas"]:
                certo_sem_ia[(medida["arquivo"], celula["pessoa_id"], celula["campo"])] = celula["certo"]
    grupos = {}
    for medida in medidas_com_ia:
        for pessoa in medida["pessoas"]:
            for celula in pessoa["celulas"]:
                chave = (medida["arquivo"], celula["pessoa_id"], celula["campo"])
                if chave in certo_sem_ia:
                    grupos.setdefault(medida["arquivo"], []).append((certo_sem_ia[chave], celula["certo"]))
    return grupos


def _pares_das_pessoas(medidas_sem_ia: list[dict], medidas_com_ia: list[dict], medida: str) -> dict:
    """Os pares (sem IA?, com IA?) de uma medida por pessoa (ex.: "obrigatorios_certos"), agrupados por arquivo."""
    valor_sem_ia = {}
    for medida_do_arquivo in medidas_sem_ia:
        for pessoa in medida_do_arquivo["pessoas"]:
            valor_sem_ia[(medida_do_arquivo["arquivo"], pessoa["pessoa_id"])] = pessoa[medida]
    grupos = {}
    for medida_do_arquivo in medidas_com_ia:
        for pessoa in medida_do_arquivo["pessoas"]:
            chave = (medida_do_arquivo["arquivo"], pessoa["pessoa_id"])
            if chave in valor_sem_ia:
                grupos.setdefault(medida_do_arquivo["arquivo"], []).append((valor_sem_ia[chave], pessoa[medida]))
    return grupos


def teste_da_medida(grupos: dict) -> dict:
    """O teste pareado de uma medida: a diferença (com − sem IA), o intervalo (sorteando os arquivos) e o McNemar."""
    todos_os_pares = []
    for pares in grupos.values():
        todos_os_pares += pares
    contagem = teste_pareado.contar_discordantes(todos_os_pares)
    bootstrap = teste_pareado.bootstrap_pareado(list(grupos.values()))
    return {"diferenca": bootstrap["diferenca"], "ic_95": [bootstrap["ic_95_baixo"], bootstrap["ic_95_alto"]],
            "arquivos": bootstrap["grupos"], "itens": bootstrap["itens"],
            "so_sem_ia_acertou": contagem["so_o_primeiro"], "so_com_ia_acertou": contagem["so_o_segundo"],
            "valor_p": teste_pareado.mcnemar_exato(contagem["so_o_primeiro"], contagem["so_o_segundo"])}


def comparar_tipo(medidas_sem_ia: list[dict], medidas_com_ia: list[dict]) -> dict:
    """O ganho da IA num tipo: no acerto por campo, nos 4 obrigatórios e nas pessoas sem pergunta, com o custo."""
    campos = teste_da_medida(_pares_das_celulas(medidas_sem_ia, medidas_com_ia))
    obrigatorios = teste_da_medida(_pares_das_pessoas(medidas_sem_ia, medidas_com_ia, "obrigatorios_certos"))
    sem_pergunta = teste_da_medida(_pares_das_pessoas(medidas_sem_ia, medidas_com_ia, "sem_pergunta"))
    # O custo do com IA nos arquivos que entraram na comparação
    custo = 0.0
    for medida in medidas_com_ia:
        custo += medida["custo_usd"] or 0.0
    return {"acerto_por_campo": campos, "obrigatorios_certos": obrigatorios, "sem_pergunta": sem_pergunta,
            "custo_com_ia_usd": round(custo, 4),
            "custo_por_ponto_do_acerto_usd": _custo_por_ponto(custo, campos["diferenca"]),
            "custo_por_ponto_dos_obrigatorios_usd": _custo_por_ponto(custo, obrigatorios["diferenca"])}


def _custo_por_ponto(custo_usd: float, diferenca: float) -> float | None:
    """Quanto custou cada ponto percentual ganho (None se a IA não ganhou nada)."""
    pontos = diferenca * 100
    if pontos <= 0:
        return None
    return round(custo_usd / pontos, 4)


def corrigir_os_valores_p(comparacoes: dict) -> None:
    """Acrescenta a cada tipo o valor-p corrigido por Holm (7 tipos testados ao mesmo tempo), em cada medida."""
    for medida in ("acerto_por_campo", "obrigatorios_certos", "sem_pergunta"):
        valores_p = {}
        for tipo, comparacao in comparacoes.items():
            valores_p[tipo] = comparacao[medida]["valor_p"]
        corrigidos = teste_pareado.correcao_de_holm(valores_p)
        for tipo, comparacao in comparacoes.items():
            comparacao[medida]["valor_p_holm"] = corrigidos[tipo]


# ============================== A prova inteira ==============================

def valores_das_pessoas(manifesto: dict) -> dict:
    """{pessoa_id: {campo: valor certo}} de todas as pessoas do manifesto."""
    valores = {}
    for pessoa in manifesto["pessoas"]:
        valores[pessoa["pessoa_id"]] = pessoa["valores"]
    return valores


def medir_braco(manifesto: dict, brutos: dict, campos_por_nome: dict) -> dict:
    """As medidas de todos os arquivos medidos num braço: {tipo: [medida de cada arquivo]}.

    Recebe: o manifesto, {arquivo: bruto} do braço e {nome: CampoLayout}. Arquivo sem bruto (não medido) fica de fora.
    """
    valores = valores_das_pessoas(manifesto)
    por_tipo = {}
    for entrada in manifesto["arquivos"]:
        bruto = brutos.get(entrada["arquivo"])
        # Arquivo não medido, ou em que a medição quebrou (um erro do script, e não do sistema): fica de fora
        if bruto is None or bruto.get("erro_da_medicao"):
            continue
        grupo = manifesto["tipos"][entrada["tipo"]]["grupo"]
        por_tipo.setdefault(entrada["tipo"], []).append(medir_arquivo(entrada, grupo, bruto, valores, campos_por_nome))
    return por_tipo


def relatorio(manifesto: dict, brutos_sem_ia: dict, brutos_com_ia: dict, campos_por_nome: dict) -> dict:
    """O relatório inteiro: por tipo, o resumo sem IA, o resumo com IA e o ganho (com o Holm nos 7 tipos).

    Com IA ainda não medido (brutos_com_ia vazio): só o resumo sem IA.
    """
    sem_ia = medir_braco(manifesto, brutos_sem_ia, campos_por_nome)
    com_ia = medir_braco(manifesto, brutos_com_ia, campos_por_nome)
    por_tipo = {}
    comparacoes = {}
    for tipo in manifesto["tipos"]:
        linha = {"nome": manifesto["tipos"][tipo]["nome"], "sem_ia": resumir(sem_ia.get(tipo, [])), "com_ia": None,
                 "ganho": None}
        if com_ia.get(tipo):
            # O sem IA dos mesmos arquivos que o com IA mediu (a comparação é sempre pareada)
            medidos_com_ia = set()
            for medida in com_ia[tipo]:
                medidos_com_ia.add(medida["arquivo"])
            mesmos_sem_ia = []
            for medida in sem_ia.get(tipo, []):
                if medida["arquivo"] in medidos_com_ia:
                    mesmos_sem_ia.append(medida)
            linha["com_ia"] = resumir(com_ia[tipo])
            linha["ganho"] = comparar_tipo(mesmos_sem_ia, com_ia[tipo])
            comparacoes[tipo] = linha["ganho"]
        por_tipo[tipo] = linha
    if comparacoes:
        corrigir_os_valores_p(comparacoes)
    return {"por_tipo": por_tipo, "medidas_sem_ia": sem_ia, "medidas_com_ia": com_ia}

