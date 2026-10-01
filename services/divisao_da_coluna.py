"""Divisão de uma coluna em partes, proposta pela IA ou escolhida pela empresa (ADR-76, ADR-104).

Para que serve: uma coluna pode ter mais de um dado em cada célula ("Rua das Flores, 123 - Centro, São Paulo - SP",
"001 / 1234 / 56789-0"). O layout do banco quer cada dado num campo. Aqui:
    1. a proposta é conferida (conferir_proposta): a ferramenta existe, cada campo existe no layout, nenhum campo repete;
    2. a proposta é aplicada em TODAS as linhas pela regra de services/divisao.py (aplicar): cada parte vira uma coluna
       nova ("Endereço · rua"), já ligada ao seu campo, e a coluna original fica de fora (a informação está nas partes);
    3. as linhas que a regra não conseguiu dividir por inteiro vão para a IA pequena, só elas (completar_com_a_ia). A IA
       aponta o pedaço de cada parte e o código confere que o pedaço está mesmo na célula ("a IA aponta, o código
       copia"): nada é inventado;
    4. a divisão pode ser desfeita (desfazer) e refeita com o comentário da empresa (em services/cadastro.py).

Quem decide a divisão: a IA, na mesma leitura das colunas (o Interpretador responde DIVIDIR com a proposta), ou a
empresa, pela opção "Dividir em vários campos…" da tela. As duas passam por aqui.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from models.contratos import FERRAMENTAS_DE_DIVISAO, DivisaoProposta, ItemMapeamento, ParteDaDivisao, StatusMapeamento
from services import divisao
from services.llm_client import LLMClient

# Pasta raiz do projeto (para achar o prompt)
RAIZ = Path(__file__).resolve().parent.parent
# Como o nome de uma parte é montado: a coluna, este sinal e o nome da parte ("Endereço · rua")
SINAL_DA_PARTE = " · "
# Quantas vezes a empresa pode pedir para refazer a divisão de uma coluna com um comentário
LIMITE_DE_REFAZER = 2
# Quantas linhas difíceis de uma coluna vão para a IA (as outras ficam como a regra dividiu)
LINHAS_PARA_A_IA = 50
# O prompt e a tarefa da IA que divide as linhas difíceis
VERSAO_PROMPT_LINHAS = "divisor_de_linhas_v1"
TAREFA_LINHAS = "dividir_linhas"


# ============================== 1. Conferir a proposta ==============================

def conferir_proposta(proposta: DivisaoProposta, nomes_dos_campos: set) -> DivisaoProposta:
    """A proposta só vale dentro do que existe (guardrail de saída, ADR-38).

    Recebe: a proposta (da IA ou da empresa); os nomes dos campos do layout.
    Devolve: a proposta conferida: campo que não existe no layout ou que repete vira "sem campo" (a parte fica de fora).
    Levanta ValueError se a ferramenta não existe, se falta o separador, se uma parte não existe na ferramenta ou se
    nenhuma parte ficou com campo.
    """
    if proposta.ferramenta not in FERRAMENTAS_DE_DIVISAO:
        raise ValueError(f"A ferramenta de divisão {proposta.ferramenta!r} não existe.")
    if proposta.ferramenta == "separador" and not proposta.separador:
        raise ValueError("A divisão por separador precisa do separador.")
    partes_conferidas = []
    campos_ja_usados = set()
    for parte in proposta.partes:
        nome = parte.parte.strip()
        # Endereço e cidade/UF: só as partes que a regra sabe achar
        if proposta.ferramenta != "separador" and nome not in divisao.NOMES_DAS_PARTES:
            raise ValueError(f"A parte {nome!r} não existe na divisão de {proposta.ferramenta}.")
        if not nome:
            raise ValueError("Toda parte precisa de um nome.")
        campo = parte.campo
        # Campo fora do layout, ou já usado por outra parte: a parte fica de fora
        if campo not in nomes_dos_campos or campo in campos_ja_usados:
            campo = None
        if campo is not None:
            campos_ja_usados.add(campo)
        partes_conferidas.append(ParteDaDivisao(parte=nome, campo=campo))
    if not campos_ja_usados:
        raise ValueError("Nenhuma parte da divisão ficou ligada a um campo do layout.")
    return proposta.model_copy(update={"partes": partes_conferidas})


# ============================== 2. Dividir os valores ==============================

def _nomes_das_partes(proposta: DivisaoProposta) -> list[str]:
    """Os nomes das partes, na ordem da proposta (ex.: ["logradouro", "numero", "cep"])."""
    nomes = []
    for parte in proposta.partes:
        nomes.append(parte.parte)
    return nomes


def dividir_valores(valores: list[str], proposta: DivisaoProposta) -> tuple[dict[str, list[str]], list[int]]:
    """Divide cada valor da coluna pela regra da ferramenta.

    Devolve: ({parte: [o valor da parte em cada linha]}, [posições das linhas que sobraram pedaços]).
    Célula vazia não tem parte nenhuma.
    Ex.: (["Salvador/BA", ""], cidade_uf) → ({"municipio": ["Salvador", ""], "uf": ["BA", ""]}, []).
    """
    nomes = _nomes_das_partes(proposta)
    valores_por_parte = {}
    for nome in nomes:
        valores_por_parte[nome] = []
    linhas_com_sobra = []
    for posicao, valor in enumerate(valores):
        dividido = divisao.EnderecoDividido()
        if valor.strip():
            dividido = divisao.dividir_com_a_ferramenta(valor, proposta.ferramenta, proposta.separador, nomes)
        if dividido.sobrou:
            linhas_com_sobra.append(posicao)
        for nome in nomes:
            valores_por_parte[nome].append(dividido.partes.get(nome, ""))
    return valores_por_parte, linhas_com_sobra


# ============================== 3. As linhas difíceis vão para a IA ==============================

@lru_cache(maxsize=1)
def _prompt_das_linhas() -> tuple[str, str]:
    """(sistema, pedido) do prompt versionado da IA que divide as linhas difíceis."""
    texto = (RAIZ / "prompts" / f"{VERSAO_PROMPT_LINHAS}.md").read_text(encoding="utf-8")
    _, sistema, pedido = re.split(r"^## (?:SISTEMA|PEDIDO)\s*$", texto, flags=re.M)
    return sistema.strip(), pedido.strip()


def _descrever_partes(proposta: DivisaoProposta) -> str:
    """As partes para a IA, uma por linha, com o nome que a empresa vê (ex.: "- logradouro (rua)")."""
    linhas = []
    for parte in proposta.partes:
        linhas.append(f"- {parte.parte} ({divisao.nome_da_parte(proposta.ferramenta, parte.parte)})")
    return "\n".join(linhas)


def _json_da_resposta(texto: str) -> str:
    """Só o JSON da resposta: do primeiro "{" ao último "}" (a IA às vezes escreve algo em volta)."""
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("a resposta não contém um objeto JSON")
    return texto[inicio:fim + 1]


def _simular_linhas(prompt: str) -> str:
    """MOCK da IA das linhas difíceis: não divide nada (as linhas ficam como a regra deixou)."""
    return json.dumps({"linhas": []})


def cliente_das_linhas() -> LLMClient:
    """Cliente do modo configurado; no MOCK, a IA das linhas difíceis é simulada."""
    return LLMClient(respostas_mock={TAREFA_LINHAS: _simular_linhas})


def completar_com_a_ia(valores: list[str], linhas_com_sobra: list[int], proposta: DivisaoProposta,
                       valores_por_parte: dict[str, list[str]], cliente: LLMClient | None = None) -> int:
    """Pede à IA pequena para dividir só as linhas que a regra não dividiu por inteiro, e confere cada pedaço.

    Recebe: os valores da coluna; as posições das linhas difíceis; a proposta; os valores por parte (alterados aqui).
    Devolve: quantas linhas a IA completou. Pedaço que não está na célula é descartado (a IA aponta, o código copia).
    Sem linhas difíceis, ou se a IA falhar, nada muda.
    """
    if not linhas_com_sobra:
        return 0
    escolhidas = linhas_com_sobra[:LINHAS_PARA_A_IA]
    sistema, pedido = _prompt_das_linhas()
    linhas_do_pedido = []
    for posicao in escolhidas:
        linhas_do_pedido.append(json.dumps({"linha": posicao, "valor": valores[posicao]}, ensure_ascii=False))
    pedido = pedido.replace("{partes}", _descrever_partes(proposta)).replace("{linhas}", "\n".join(linhas_do_pedido))
    resposta = (cliente or cliente_das_linhas()).gerar(TAREFA_LINHAS, pedido, sistema, modelo="pequeno", temperatura=0.0)
    try:
        # Só o JSON da resposta (sem texto em volta), e dele a lista das linhas
        linhas_da_ia = json.loads(_json_da_resposta(resposta.texto))["linhas"]
    except (ValueError, KeyError, TypeError):
        # Resposta fora do formato: as linhas ficam como a regra deixou (e continuam como pendência)
        return 0
    completadas = 0
    for linha in linhas_da_ia:
        posicao = linha.get("linha") if isinstance(linha, dict) else None
        if posicao not in escolhidas or not isinstance(linha.get("partes"), dict):
            continue
        valor = valores[posicao]
        partes_conferidas = {}
        for nome, pedaco in linha["partes"].items():
            # Só vale parte que existe na proposta e pedaço que está mesmo na célula
            if nome in valores_por_parte and isinstance(pedaco, str) and pedaco.strip() and pedaco.strip() in valor:
                partes_conferidas[nome] = pedaco.strip()
        if not partes_conferidas:
            continue
        # A linha passa a ter as partes que a IA apontou (as outras ficam vazias: nada por suposição)
        for nome in valores_por_parte:
            valores_por_parte[nome][posicao] = partes_conferidas.get(nome, "")
        completadas += 1
    return completadas


# ============================== 4. Aplicar e desfazer ==============================

def _valores_da_coluna(leitura, coluna: str) -> list[str]:
    """Os valores da coluna, um por linha (levanta ValueError se a coluna não existe)."""
    if coluna not in leitura.cabecalhos:
        raise ValueError(f"A coluna {coluna!r} não existe no arquivo.")
    posicao = leitura.cabecalhos.index(coluna)
    valores = []
    for linha in leitura.linhas:
        valores.append(linha[posicao])
    return valores


def coluna_ja_dividida(leitura, coluna: str) -> bool:
    """True se a tabela já tem as partes desta coluna ("Endereço · rua"...)."""
    for cabecalho in leitura.cabecalhos:
        if cabecalho.startswith(coluna + SINAL_DA_PARTE):
            return True
    return False


def _campos_de_outras_colunas(itens: list[ItemMapeamento], coluna: str) -> dict[str, str]:
    """{campo: coluna} dos campos que outras colunas já alimentam (as partes desta coluna não contam)."""
    usados = {}
    for item in itens:
        e_desta_coluna = item.coluna == coluna or item.coluna.startswith(coluna + SINAL_DA_PARTE)
        if item.campo and not e_desta_coluna and item.status == StatusMapeamento.PROPOSTO:
            usados[item.campo] = item.coluna
    return usados


def aplicar(leitura, itens: list[ItemMapeamento], coluna: str, proposta: DivisaoProposta, origem: str,
            cliente: LLMClient | None = None) -> list[ItemMapeamento]:
    """Divide a coluna em todas as linhas: cada parte vira uma coluna nova, ligada ao seu campo.

    Recebe: leitura (a tabela do envio: ganha as colunas novas); itens (o plano); a coluna; a proposta JÁ conferida;
    origem — "llm" (a IA propôs) ou "humano" (a empresa escolheu); cliente — da IA das linhas difíceis (só na origem
    "llm"; a divisão da empresa mostra a prévia e não chama a IA).
    Devolve: os itens novos: a coluna original fica de fora (com a proposta guardada) e as partes entram logo depois.
    Parte cujo campo já vem de outra coluna fica de fora, com o motivo. Levanta ValueError se a coluna já foi
    dividida ou se nenhuma linha tem algo para dividir.
    """
    if coluna_ja_dividida(leitura, coluna):
        raise ValueError(f"A coluna \"{coluna}\" já foi dividida.")
    valores = _valores_da_coluna(leitura, coluna)
    valores_por_parte, linhas_com_sobra = dividir_valores(valores, proposta)
    if origem == "llm":
        completar_com_a_ia(valores, linhas_com_sobra, proposta, valores_por_parte, cliente)
    quem = "pelo Agente Interpretador" if origem == "llm" else "por você"
    usados = _campos_de_outras_colunas(itens, coluna)
    itens_das_partes = []
    for parte in proposta.partes:
        preenchidas = 0
        for valor_da_parte in valores_por_parte[parte.parte]:
            if valor_da_parte:
                preenchidas += 1
        # Parte que não apareceu em nenhuma linha não vira coluna
        if preenchidas == 0:
            continue
        nome_da_parte = divisao.nome_da_parte(proposta.ferramenta, parte.parte)
        nome_da_coluna = coluna + SINAL_DA_PARTE + nome_da_parte
        leitura.cabecalhos.append(nome_da_coluna)
        for linha, valor_da_parte in zip(leitura.linhas, valores_por_parte[parte.parte]):
            linha.append(valor_da_parte)
        if parte.campo is None:
            itens_das_partes.append(ItemMapeamento(
                coluna=nome_da_coluna, status=StatusMapeamento.NAO_MAPEADO, origem=origem,
                justificativa=f"Parte \"{nome_da_parte}\" de \"{coluna}\": sem campo no layout; escolha, se quiser."))
        elif parte.campo in usados:
            itens_das_partes.append(ItemMapeamento(
                coluna=nome_da_coluna, status=StatusMapeamento.NAO_MAPEADO, origem=origem,
                justificativa=f"O campo {parte.campo} já vem da coluna \"{usados[parte.campo]}\"."))
        else:
            itens_das_partes.append(ItemMapeamento(
                coluna=nome_da_coluna, campo=parte.campo, status=StatusMapeamento.PROPOSTO, origem=origem,
                justificativa=f"Parte \"{nome_da_parte}\" de \"{coluna}\", separada {quem} "
                              f"({preenchidas} de {len(valores)} linhas)."))
    if not itens_das_partes:
        raise ValueError(f"Nenhuma linha de \"{coluna}\" tem algo que dê para dividir.")
    novos_itens = []
    for item in itens:
        if item.coluna == coluna:
            novos_itens.append(item.model_copy(update={
                "campo": None, "status": StatusMapeamento.NAO_MAPEADO, "origem": origem, "divisao": proposta,
                "candidatos": [],
                "justificativa": f"Dividida {quem} em {len(itens_das_partes)} partes, nas linhas abaixo."}))
            novos_itens.extend(itens_das_partes)
        else:
            novos_itens.append(item)
    return novos_itens


def tirar_partes_da_tabela(leitura, coluna: str) -> None:
    """Tira da tabela as colunas das partes desta coluna ("Endereço · rua"...), se houver."""
    prefixo = coluna + SINAL_DA_PARTE
    # As posições das colunas das partes, da última para a primeira (assim tirar uma não muda a posição das outras)
    posicoes = []
    for posicao, cabecalho in enumerate(leitura.cabecalhos):
        if cabecalho.startswith(prefixo):
            posicoes.append(posicao)
    posicoes.reverse()
    for posicao in posicoes:
        del leitura.cabecalhos[posicao]
        for linha in leitura.linhas:
            del linha[posicao]


def desfazer(leitura, itens: list[ItemMapeamento], coluna: str) -> list[ItemMapeamento]:
    """Tira as partes da coluna da tabela e do plano; a coluna original volta a ficar de fora, sem divisão.

    Recebe: leitura (perde as colunas das partes); itens; a coluna. Devolve: os itens sem as partes.
    """
    prefixo = coluna + SINAL_DA_PARTE
    tirar_partes_da_tabela(leitura, coluna)
    novos_itens = []
    for item in itens:
        if item.coluna.startswith(prefixo):
            continue
        if item.coluna == coluna:
            item = item.model_copy(update={"divisao": None, "campo": None, "status": StatusMapeamento.NAO_MAPEADO,
                                           "justificativa": "A divisão desta coluna foi desfeita."})
        novos_itens.append(item)
    return novos_itens


def descrever(proposta: DivisaoProposta) -> str:
    """A proposta em uma linha, para a IA e para a auditoria.

    Ex.: 'endereco: logradouro → logradouro_residencial; cep → cep_residencial'.
    """
    partes = []
    for parte in proposta.partes:
        partes.append(f"{parte.parte} → {parte.campo or 'sem campo'}")
    separador = f" (separador {proposta.separador!r})" if proposta.ferramenta == "separador" else ""
    return f"{proposta.ferramenta}{separador}: " + "; ".join(partes)
