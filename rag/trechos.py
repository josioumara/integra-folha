"""Corta as fontes de conhecimento em trechos que fazem sentido sozinhos (ADR-09).

- Layout do banco: um trecho por CAMPO.
- Regras de validação: um trecho por REGRA.
- Histórico: um trecho por MAPEAMENTO homologado (coluna da planilha -> campo do layout).
- Catálogo de benefícios: um trecho por seção "##"; seção longa é dividida por parágrafo.

Todo trecho começa pelo caminho de origem (ex.: "Pacote de benefícios Aurora v1 › Conta salário"),
porque uma seção lida sozinha nem sempre diz de que empresa ou produto fala.

Cada trecho tem dois textos: `texto` é o que o agente LÊ (com o caminho de origem, para citar a fonte);
`texto_busca` é o que a busca COMPARA. No layout, o texto de busca é só o assunto: frases repetidas em
todos os trechos ("Parâmetro do layout v1", "foi homologada como") pesavam mais que o conteúdo e
atrapalhavam a busca (ADR-42). No catálogo, o caminho entra na busca, porque empresa e seção são conteúdo.

Privacidade: desde o ADR-101, o exemplo do parâmetro entra no índice também nos campos de dado pessoal (CPF, nome,
endereço...): ele ajuda a IA a reconhecer o dado, e a IA roda numa nuvem contratada que não guarda os pedidos.
"""
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from models.contratos import CampoLayout

# Seção do catálogo maior que isso (em caracteres) é dividida por parágrafo
LIMITE_CARACTERES = 700


@dataclass
class Trecho:
    """Um pedaço de conhecimento pronto para ir ao índice de busca."""

    id: str                                         # identificador único do trecho
    texto: str                                      # o que o agente lê (com a fonte no começo)
    metadados: dict = field(default_factory=dict)   # etiquetas para filtrar e citar (fonte, empresa, vigência...)
    texto_busca: str = ""                           # o que a busca compara; vazio = o próprio texto

    def __post_init__(self):
        """Roda logo depois de criar o trecho: sem texto de busca, a busca compara o próprio texto."""
        if not self.texto_busca:
            self.texto_busca = self.texto


def _frase_de_igual_para_todos(campo: CampoLayout) -> str:
    """A frase do trecho que diz se o campo pode ser o mesmo para todos os funcionários do arquivo.

    Ex.: cnpj_empregador → "Pode ser o mesmo para todos os funcionários do arquivo (dado da empresa)."; cpf → "É de
    cada pessoa: nunca é o mesmo para todos os funcionários do arquivo."
    """
    # Importado aqui: services importa o RAG, e o RAG só precisa desta regra do parâmetro
    from services.parametros import pode_ser_igual_para_todos
    if pode_ser_igual_para_todos(campo):
        return "Pode ser o mesmo para todos os funcionários do arquivo (dado da empresa)."
    return "É de cada pessoa: nunca é o mesmo para todos os funcionários do arquivo."


def _frase_da_faixa(campo: CampoLayout) -> str | None:
    """A frase do trecho com o mínimo e o máximo do parâmetro (ADR-128), ou None se o campo não tem faixa.

    Ex.: valor_renda com mínimo 500 → "Faixa esperada: a partir de R$ 500,00; fora dela, vira alerta (a empresa
    confirma ou corrige)."; com os dois → "Faixa esperada: de R$ 500,00 a R$ 50.000,00; ...".
    """
    # Importado aqui: services importa o RAG (como em _frase_de_igual_para_todos)
    from services.formatacao import em_reais
    # Sem limite nenhum: o trecho não fala de faixa
    if campo.minimo is None and campo.maximo is None:
        return None
    # Os dois lados, só o mínimo ou só o máximo
    if campo.minimo is not None and campo.maximo is not None:
        faixa = f"de {em_reais(campo.minimo)} a {em_reais(campo.maximo)}"
    elif campo.minimo is not None:
        faixa = f"a partir de {em_reais(campo.minimo)}"
    else:
        faixa = f"até {em_reais(campo.maximo)}"
    return f"Faixa esperada: {faixa}; fora dela, vira alerta (a empresa confirma ou corrige)."


def trechos_layout(versao: int, campos: list[CampoLayout]) -> list[Trecho]:
    """Um trecho por campo do layout, com descrição, regra, "não confundir com" e exemplo."""
    trechos = []
    for campo in campos:
        # O caminho de origem, que o agente cita como fonte
        fonte = f"Parâmetro do layout v{versao} › {campo.campo}"
        # As partes do texto, uma por linha; parte sem conteúdo é pulada
        obrigatoriedade = "obrigatório" if campo.obrigatorio else "opcional"
        partes = [fonte, f"Campo {campo.campo} ({campo.grupo}), tipo {campo.tipo.value}, {obrigatoriedade}."]
        if campo.descricao:
            partes.append(f"O que é: {campo.descricao}.")
        if campo.regra:
            partes.append(f"Regra: {campo.regra}.")
        if campo.nao_confundir_com:
            partes.append(f"Não confundir com: {campo.nao_confundir_com}.")
        # Se pode ser o mesmo para todos do arquivo (dado da empresa) ou é de cada pessoa (ADR-124):
        # o agente lê e cita isto ao explicar por que não aceita "o mesmo CPF para todos"
        partes.append(_frase_de_igual_para_todos(campo))
        # O mínimo e o máximo do parâmetro, quando o campo tem (ADR-128): o agente explica o alerta de faixa com eles
        frase_da_faixa = _frase_da_faixa(campo)
        if frase_da_faixa:
            partes.append(frase_da_faixa)
        # O exemplo do parâmetro do banco ajuda a IA a reconhecer o dado (ADR-101)
        if campo.exemplo:
            partes.append(f"Exemplo: {campo.exemplo}.")
        # O texto de busca é só o assunto: descrição, nome do campo com espaços e grupo
        texto_busca = f"{campo.descricao}. {campo.campo.replace('_', ' ')}. {campo.grupo}"
        metadados = {"tipo_trecho": "campo", "campo": campo.campo, "fonte": fonte, "versao": versao}
        trechos.append(Trecho(f"campo:{campo.campo}", "\n".join(partes), metadados, texto_busca=texto_busca))
    return trechos


def trechos_regras(caminho: Path) -> list[Trecho]:
    """Um trecho por regra de validação (do arquivo data/contratos/regras_v1.json)."""
    trechos = []
    for regra in json.loads(caminho.read_text(encoding="utf-8")):
        # O caminho de origem da regra
        fonte = f"Regras de validação v1 › {regra['titulo']}"
        metadados = {"tipo_trecho": "regra", "campo": "", "fonte": fonte, "versao": 1}
        # A busca compara o título e o texto da regra
        texto_busca = f"{regra['titulo']}. {regra['texto']}"
        trechos.append(Trecho(f"regra:{regra['id']}", f"{fonte}\n{regra['texto']}", metadados,
                              texto_busca=texto_busca))
    return trechos


def trechos_historico(caminho: Path, descricoes: dict[str, str] | None = None) -> list[Trecho]:
    """Um trecho por mapeamento já homologado (coluna da planilha -> campo).

    descricoes (campo -> descrição) enriquece a busca: "Vlr Salário" vira "Vlr Salário: salário bruto...". Quando vem,
    são os campos do layout vigente, e o mapeamento para um campo que não está nele (que o banco tirou do parâmetro, na
    tela Parâmetros; ADR-128) não entra: a IA não aprende a propor um campo que o banco tirou. É a mesma regra do índice
    dos mapeamentos aprovados (rag/aprendizado.py).
    """
    # Sem descrições informadas, a busca usa o nome do campo, e todos os mapeamentos entram
    filtrar_pelo_layout = descricoes is not None
    descricoes = descricoes or {}
    trechos = []
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        for numero, linha in enumerate(csv.DictReader(arquivo)):
            coluna, campo = linha["coluna_origem"], linha["campo"]
            # Campo que saiu do layout vigente: o mapeamento não é mais conhecimento para a IA
            if filtrar_pelo_layout and campo not in descricoes:
                continue
            # O caminho de origem do mapeamento
            fonte = f"Mapeamentos homologados › {coluna}"
            # O texto que o agente lê
            texto = (f"{fonte}\nA coluna \"{coluna}\" de uma planilha de RH foi homologada "
                     f"como o campo {campo} (layout v{linha['versao_layout']}).")
            metadados = {"tipo_trecho": "mapeamento", "campo": campo, "fonte": fonte,
                         "versao": int(linha["versao_layout"])}
            # A busca compara o nome da coluna com a descrição do campo
            texto_busca = f"{coluna}: {descricoes.get(campo, campo)}"
            trechos.append(Trecho(f"mapeamento:{numero}", texto, metadados, texto_busca=texto_busca))
    return trechos


def _data_como_numero(data_em_texto: str) -> int:
    """'2026-03-01' vira 20260301: o filtro do ChromaDB só compara números com maior e menor."""
    return int(data_em_texto.replace("-", ""))


def _secoes_do_markdown(markdown: str) -> list[tuple[str, str]]:
    """Separa o documento em (título da seção "##", texto da seção). O título "#" do documento é ignorado."""
    secoes = []
    titulo_atual = None
    linhas_da_secao = []
    for linha in markdown.splitlines():
        # Começo de uma seção nova
        if linha.startswith("## "):
            # Guarda a seção anterior, se havia uma
            if titulo_atual:
                secoes.append((titulo_atual, "\n".join(linhas_da_secao).strip()))
            titulo_atual = linha[3:].strip()
            linhas_da_secao = []
        # Linha dentro de uma seção
        elif titulo_atual:
            linhas_da_secao.append(linha)
    # Guarda a última seção
    if titulo_atual:
        secoes.append((titulo_atual, "\n".join(linhas_da_secao).strip()))
    return secoes


def _dividir_por_paragrafo(texto_da_secao: str) -> list[str]:
    """Junta parágrafos até o limite de caracteres; cada pedaço vira um trecho (que repete o título)."""
    # Os parágrafos não vazios (separados por uma linha em branco)
    paragrafos = []
    for paragrafo in texto_da_secao.split("\n\n"):
        if paragrafo.strip():
            paragrafos.append(paragrafo.strip())
    pedacos = []
    pedaco_atual = ""
    for paragrafo in paragrafos:
        # Se o parágrafo não cabe mais no pedaço atual, fecha o pedaço e começa outro
        if pedaco_atual and len(pedaco_atual) + len(paragrafo) > LIMITE_CARACTERES:
            pedacos.append(pedaco_atual)
            pedaco_atual = paragrafo
        # Senão, acrescenta o parágrafo ao pedaço atual
        elif pedaco_atual:
            pedaco_atual = f"{pedaco_atual}\n\n{paragrafo}"
        else:
            pedaco_atual = paragrafo
    # Guarda o último pedaço
    if pedaco_atual:
        pedacos.append(pedaco_atual)
    return pedacos


def trechos_catalogo(documentos: list[dict]) -> list[Trecho]:
    """Um trecho por seção de cada documento do catálogo, com empresa e vigência nas etiquetas."""
    trechos = []
    for documento in documentos:
        for secao, texto_da_secao in _secoes_do_markdown(documento["conteudo_md"]):
            # O caminho de origem: título do documento, versão e seção
            fonte = f"{documento['titulo']} v{documento['versao']} › {secao}"
            # Seção longa vira vários pedaços; curta fica inteira
            if len(texto_da_secao) > LIMITE_CARACTERES:
                pedacos = _dividir_por_paragrafo(texto_da_secao)
            else:
                pedacos = [texto_da_secao]
            for numero_do_pedaco, pedaco in enumerate(pedacos, start=1):
                # Identificador único: empresa, título, versão, seção e número do pedaço
                identificador = (f"{documento['empresa_id']}:{documento['titulo']}:v{documento['versao']}:"
                                 f"{secao}:{numero_do_pedaco}")
                # As etiquetas: a empresa (para o filtro obrigatório) e a vigência em número
                metadados = {"tipo_trecho": "beneficio", "empresa_id": documento["empresa_id"],
                             "titulo": documento["titulo"], "versao": documento["versao"], "secao": secao,
                             "fonte": fonte, "vigencia_inicio": _data_como_numero(documento["vigencia_inicio"]),
                             "vigencia_fim": _data_como_numero(documento["vigencia_fim"])}
                trechos.append(Trecho(identificador, f"{fonte}\n{pedaco}", metadados))
    return trechos
