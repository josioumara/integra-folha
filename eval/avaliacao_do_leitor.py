"""Régua do experimento EXP-010: o quanto o Leitor de Documentos acerta, por nível de documento e por modo (ADR-73).

Compara o que a leitura devolveu com o gabarito de data/avaliacao/documentos/gabarito.json. As medidas:
- ACERTO POR CAMPO: dos campos que o gabarito espera, quantos vieram com o valor certo (os dois lados passam pela mesma
  padronização do sistema: "14 de setembro de 1991" e "14/09/1991" são a mesma data);
- PESSOAS: quantas pessoas do gabarito foram encontradas e quantas "pessoas" a mais apareceram;
- ARMADILHAS RESPEITADAS: campos que o documento não permite decidir (ex.: duas datas de admissão) e que precisam
  ficar em branco;
- PERGUNTAS: das pessoas em que o gabarito espera uma pergunta, quantas ganharam uma;
- TERCEIROS VAZADOS: quantas vezes um dado de outra pessoa (dependente, contato de emergência) entrou num campo;
- CUSTO E TEMPO por documento.

O intervalo de confiança (95%) do acerto sai de um "bootstrap": sorteia as pessoas com reposição muitas vezes e vê
quanto o acerto varia. Diz o quanto o número poderia mudar com outra amostra do mesmo tipo.
"""
import random
import re
import unicodedata

from rapidfuzz import fuzz

from models.contratos import CampoLayout, TipoCampo
from services.normalizador import NaoConvertido, converter_valor

# Tipos que passam pela padronização do sistema antes de comparar
TIPOS_PADRONIZADOS = {TipoCampo.CPF, TipoCampo.CNPJ, TipoCampo.CEP, TipoCampo.UF, TipoCampo.TELEFONE, TipoCampo.EMAIL,
                      TipoCampo.DECIMAL_MONETARIO, TipoCampo.DATA, TipoCampo.DOMINIO}
# Campos de documento comparados só pelos dígitos (e pelo X do RG): "44.827.196-3 SSP-SP" = "44.827.196-3"
CAMPOS_COMPARADOS_PELOS_DIGITOS = {"numero_documento", "nis_pis"}
# A partir de quanta semelhança um nome lido é a mesma pessoa do gabarito (quando não há CPF para casar)
SEMELHANCA_MINIMA_DO_NOME = 85
# Quantos sorteios o bootstrap faz
SORTEIOS_DO_BOOTSTRAP = 2000


# ============================== Comparar valores ==============================

def _texto_simples(texto: str) -> str:
    """Minúsculas, sem acento, sem pontuação nas pontas e com um espaço só entre as palavras."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split()).strip(" .,;:-")


def _padronizar(valor: str, campo: CampoLayout) -> str | None:
    """O valor como o sistema guardaria; None se o sistema não consegue padronizar (vira erro na comparação)."""
    if campo.campo in CAMPOS_COMPARADOS_PELOS_DIGITOS:
        return re.sub(r"[^0-9Xx]", "", valor).upper()
    if campo.tipo in TIPOS_PADRONIZADOS:
        try:
            return converter_valor(valor, campo)
        except NaoConvertido:
            return None
    return _texto_simples(valor)


def valores_iguais(esperado: str, lido: str, campo: CampoLayout) -> bool:
    """True se o valor lido é o esperado, depois da mesma padronização dos dois lados."""
    padrao_esperado = _padronizar(esperado, campo)
    padrao_lido = _padronizar(lido, campo)
    return padrao_lido is not None and padrao_lido == padrao_esperado


# ============================== Casar pessoas ==============================

def _digitos(texto: str) -> str:
    """Só os dígitos do texto."""
    return re.sub(r"\D", "", texto or "")


def casar_pessoas(esperadas: list[dict], lidas: list[dict]) -> list[tuple[int, int | None]]:
    """Para cada pessoa do gabarito, a posição da pessoa lida que é ela (ou None). Pelo CPF, pelo e-mail ou pelo nome.

    esperadas: as pessoas do gabarito ({"campos": {...}}); lidas: {campo: valor} de cada pessoa lida.
    """
    usadas = set()
    pares = []
    for posicao_esperada, esperada in enumerate(esperadas):
        cpf_esperado = _digitos(esperada["campos"].get("cpf", ""))
        nome_esperado = _texto_simples(esperada["campos"].get("nome_completo", ""))
        escolhida = None
        # 1. Pelo CPF (quando os dois têm)
        for posicao_lida, lida in enumerate(lidas):
            if posicao_lida not in usadas and cpf_esperado and _digitos(lida.get("cpf", "")) == cpf_esperado:
                escolhida = posicao_lida
                break
        # 2. Pelo e-mail (também é único por pessoa; serve quando a IA deixou nome e CPF em branco)
        email_esperado = _texto_simples(esperada["campos"].get("email_pessoal", ""))
        if escolhida is None and email_esperado:
            for posicao_lida, lida in enumerate(lidas):
                if posicao_lida not in usadas and _texto_simples(lida.get("email_pessoal", "")) == email_esperado:
                    escolhida = posicao_lida
                    break
        # 3. Pelo nome mais parecido, se passar da semelhança mínima
        if escolhida is None and nome_esperado:
            melhor_nota = 0
            for posicao_lida, lida in enumerate(lidas):
                if posicao_lida in usadas:
                    continue
                nota = fuzz.token_sort_ratio(nome_esperado, _texto_simples(lida.get("nome_completo", "")))
                if nota >= SEMELHANCA_MINIMA_DO_NOME and nota > melhor_nota:
                    melhor_nota = nota
                    escolhida = posicao_lida
        if escolhida is not None:
            usadas.add(escolhida)
        pares.append((posicao_esperada, escolhida))
    return pares


# ============================== Medir um documento ==============================

def pessoas_lidas(linhas: list[list[str]], cabecalho_para_campo: dict) -> list[dict]:
    """As linhas da leitura (a primeira é o cabeçalho) como {campo: valor} de cada pessoa.

    cabecalho_para_campo: nos documentos lidos por regra (tabela e fichas), qual campo cada cabeçalho é. No texto
    corrido, os cabeçalhos já são os campos do layout (o dicionário vem vazio).
    """
    cabecalhos = linhas[0]
    pessoas = []
    for linha in linhas[1:]:
        pessoa = {}
        for posicao, cabecalho in enumerate(cabecalhos):
            campo = cabecalho_para_campo.get(cabecalho, cabecalho)
            valor = linha[posicao].strip() if posicao < len(linha) else ""
            if valor:
                pessoa[campo] = valor
        pessoas.append(pessoa)
    return pessoas


def _vazou_terceiro(lidas: list[dict], terceiros: list[dict]) -> int:
    """Quantos valores lidos são dado de outra pessoa (nome, data ou telefone de dependente ou contato)."""
    valores_dos_terceiros = set()
    for terceiro in terceiros:
        for valor in terceiro.values():
            valores_dos_terceiros.add(_texto_simples(valor))
            valores_dos_terceiros.add(_digitos(valor))
    valores_dos_terceiros.discard("")
    vazamentos = 0
    for lida in lidas:
        for valor in lida.values():
            if _texto_simples(valor) in valores_dos_terceiros or (
                    len(_digitos(valor)) >= 8 and _digitos(valor) in valores_dos_terceiros):
                vazamentos += 1
    return vazamentos


def _tem_pergunta_da_pessoa(duvidas: list[str], esperada: dict, posicao_lida: int | None) -> bool:
    """True se alguma pergunta da leitura é sobre esta pessoa: pelo nome dela ou por "Pessoa N".

    "Pessoa N" é como a leitura chama quem ficou sem nome (N = a posição dela entre as pessoas lidas, contando de 1).
    """
    nome = _texto_simples(esperada["campos"].get("nome_completo", ""))
    rotulo_sem_nome = f"pessoa {posicao_lida + 1} " if posicao_lida is not None else None
    for duvida in duvidas:
        texto_da_duvida = _texto_simples(duvida) + " "
        if nome and nome in texto_da_duvida:
            return True
        if rotulo_sem_nome and texto_da_duvida.startswith(rotulo_sem_nome):
            return True
    return False


def medir_documento(documento: dict, linhas: list[list[str]], duvidas: list[str], campos: list[CampoLayout]) -> dict:
    """As medidas de um documento lido. Devolve contagens e, por pessoa, os campos certos e esperados (bootstrap)."""
    campo_pelo_nome = {}
    for campo in campos:
        campo_pelo_nome[campo.campo] = campo
    lidas = pessoas_lidas(linhas, documento.get("cabecalho_para_campo", {}))
    esperadas = documento["pessoas"]
    medida = {"pessoas_esperadas": len(esperadas), "pessoas_encontradas": 0, "pessoas_a_mais": 0,
              "campos_esperados": 0, "campos_certos": 0, "campos_errados": 0, "campos_faltando": 0,
              "armadilhas": 0, "armadilhas_respeitadas": 0, "perguntas_esperadas": 0, "perguntas_feitas": 0,
              "terceiros_vazados": 0, "por_pessoa": [], "erros": []}
    pares = casar_pessoas(esperadas, lidas)
    casadas = set()
    for posicao_esperada, posicao_lida in pares:
        esperada = esperadas[posicao_esperada]
        lida = lidas[posicao_lida] if posicao_lida is not None else {}
        if posicao_lida is not None:
            medida["pessoas_encontradas"] += 1
            casadas.add(posicao_lida)
        certos_da_pessoa = 0
        for nome_do_campo, valor_esperado in esperada["campos"].items():
            medida["campos_esperados"] += 1
            valor_lido = lida.get(nome_do_campo, "")
            if not valor_lido:
                medida["campos_faltando"] += 1
                medida["erros"].append({"pessoa": posicao_esperada + 1, "campo": nome_do_campo, "tipo": "faltando"})
            elif valores_iguais(valor_esperado, valor_lido, campo_pelo_nome[nome_do_campo]):
                medida["campos_certos"] += 1
                certos_da_pessoa += 1
            else:
                medida["campos_errados"] += 1
                medida["erros"].append({"pessoa": posicao_esperada + 1, "campo": nome_do_campo, "tipo": "errado"})
        # Armadilha só conta quando a pessoa foi encontrada (pessoa que sumiu não "respeitou" nada)
        for campo_armadilha in esperada.get("armadilhas", []):
            if posicao_lida is None:
                continue
            medida["armadilhas"] += 1
            if not lida.get(campo_armadilha):
                medida["armadilhas_respeitadas"] += 1
        if esperada.get("espera_duvida"):
            medida["perguntas_esperadas"] += 1
            if _tem_pergunta_da_pessoa(duvidas, esperada, posicao_lida):
                medida["perguntas_feitas"] += 1
        medida["por_pessoa"].append({"certos": certos_da_pessoa, "esperados": len(esperada["campos"])})
        medida["terceiros_vazados"] += _vazou_terceiro([lida], esperada.get("terceiros", []))
    medida["pessoas_a_mais"] = len(lidas) - len(casadas)
    return medida


# ============================== Juntar e resumir ==============================

def intervalo_do_acerto(por_pessoa: list[dict], semente: int = 7) -> tuple[float, float]:
    """O intervalo de confiança de 95% do acerto por campo, sorteando pessoas com reposição (bootstrap)."""
    if not por_pessoa:
        return 0.0, 0.0
    sorteio = random.Random(semente)
    acertos = []
    for _ in range(SORTEIOS_DO_BOOTSTRAP):
        certos = 0
        esperados = 0
        for _ in range(len(por_pessoa)):
            pessoa = sorteio.choice(por_pessoa)
            certos += pessoa["certos"]
            esperados += pessoa["esperados"]
        acertos.append(certos / esperados if esperados else 0.0)
    acertos.sort()
    return acertos[int(0.025 * len(acertos))], acertos[int(0.975 * len(acertos)) - 1]


def resumir(medidas: list[dict]) -> dict:
    """Soma as medidas de vários documentos (um nível ou um modo) e calcula as porcentagens."""
    total = {}
    por_pessoa = []
    for medida in medidas:
        for chave, valor in medida.items():
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                total[chave] = total.get(chave, 0) + valor
        por_pessoa.extend(medida.get("por_pessoa", []))
    acerto = total.get("campos_certos", 0) / total["campos_esperados"] if total.get("campos_esperados") else 0.0
    minimo, maximo = intervalo_do_acerto(por_pessoa)
    total["acerto_por_campo"] = round(acerto, 4)
    total["intervalo_95"] = [round(minimo, 4), round(maximo, 4)]
    if total.get("armadilhas"):
        total["armadilhas_respeitadas_pct"] = round(total["armadilhas_respeitadas"] / total["armadilhas"], 4)
    if total.get("perguntas_esperadas"):
        total["perguntas_feitas_pct"] = round(total["perguntas_feitas"] / total["perguntas_esperadas"], 4)
    if total.get("pessoas_esperadas"):
        total["pessoas_encontradas_pct"] = round(total["pessoas_encontradas"] / total["pessoas_esperadas"], 4)
        total["custo_por_funcionario_usd"] = round(total.get("custo_usd", 0) / total["pessoas_esperadas"], 5)
    return total
