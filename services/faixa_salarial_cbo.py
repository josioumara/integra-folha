"""A faixa de salário de cada profissão (CBO) e os alertas de salário fora da faixa (ADR-129).

Para que serve: além de comparar o salário com os colegas de cargo da própria empresa (o alerta RENDA_FORA_DO_CARGO,
que já existe no Validador), o sistema compara com duas referências de fora da empresa:
- a faixa PÚBLICA da profissão: o mínimo e o máximo calculados com a RAIS 2025, do Ministério do Trabalho
  (scripts/calcular_faixas_cbo.py), que o especialista do banco pode editar na página Parâmetros;
- a faixa das OUTRAS EMPRESAS do Integra Folha na mesma profissão: só o mínimo e o máximo (percentis 5 e 95), e só com
  pelo menos 2 outras empresas e 10 pessoas. A empresa nunca vê nada de outra empresa além desses dois números.
Sair de uma faixa gera UM alerta por pessoa (RENDA_FORA_DA_PROFISSAO), que cita as faixas de que o salário saiu. O
alerta não recusa nada: a empresa corrige o valor ou confirma que está certo.

Quando liga: só quando o parâmetro do layout vigente tem o campo "codigo_cbo" (o banco cria na tela Parâmetros, com a
DEFINICAO_DO_CAMPO abaixo). Sem o campo, nada muda nos envios: nenhuma pergunta e nenhum alerta deste arquivo.

Como a pessoa chega a um código CBO (a profissão):
1. a coluna "Código CBO" do arquivo (o campo "codigo_cbo" do parâmetro do layout, que o banco cria na tela
   Parâmetros): vale o que a empresa mandou; código que não existe na CBO é o alerta CBO_DESCONHECIDO;
2. sem a coluna, o nome do cargo: a profissão que a empresa já confirmou para esse cargo (tabela cbo_dos_cargos) ou,
   na primeira vez, a sugestão da tabela oficial (services/tabela_cbo.py), que vira o alerta CBO_A_CONFIRMAR ("O
   cargo X parece ser a profissão Y. Está certo?"). Nada é assumido: enquanto a empresa não confirma, o salário
   desse cargo não é comparado com a faixa da profissão. Sem sugestão, só um AVISO (CBO_NAO_ENCONTRADO).

As tabelas deste arquivo (todas novas; nenhuma tabela existente muda):
- faixas_salariais_cbo: a faixa EM USO de cada profissão e, ao lado, a CALCULADA dos dados públicos (para voltar a
  ela), com a fonte, o ano e quem editou. É carregada de data/cbo/faixas_salariais_cbo.csv na primeira consulta;
- faixas_salariais_cbo_alteracoes: cada edição (antes, depois, quem e quando);
- cbo_dos_cargos: a profissão de cada cargo de cada empresa (veio no arquivo ou foi confirmada pela empresa).
"""
import csv
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from services import formatacao, parametros, processamentos, tabela_cbo

# Pasta raiz do projeto e os arquivos da faixa calculada
RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_DAS_FAIXAS = RAIZ / "data" / "cbo" / "faixas_salariais_cbo.csv"
ARQUIVO_DAS_FONTES = RAIZ / "data" / "cbo" / "fontes.json"

# O nome técnico do campo do parâmetro do layout que traz o código CBO de cada pessoa
CAMPO_DO_CBO = "codigo_cbo"
# As regras deste arquivo (o identificador que aparece no relatório de validação)
REGRA_RENDA_FORA_DA_PROFISSAO = "RENDA_FORA_DA_PROFISSAO"
REGRA_CBO_DESCONHECIDO = "CBO_DESCONHECIDO"
REGRA_CBO_A_CONFIRMAR = "CBO_A_CONFIRMAR"
REGRA_CBO_NAO_ENCONTRADO = "CBO_NAO_ENCONTRADO"
# De onde veio a profissão de um cargo
ORIGEM_ARQUIVO, ORIGEM_CONFIRMADA = "ARQUIVO", "CONFIRMADO_PELA_EMPRESA"
# Só o salário CLT é comparado (a faixa pública é de vínculos CLT; o pró-labore do sócio fica de fora)
TIPO_DE_RENDA_COMPARADO = "CLT"
# A faixa das outras empresas só aparece com pelo menos 2 empresas e 10 pessoas (o mesmo mínimo de 2 empresas do
# aprendizado, ADR-116): com menos, os dois números poderiam revelar o salário de alguém
MINIMO_DE_OUTRAS_EMPRESAS = 2
MINIMO_DE_PESSOAS_DAS_OUTRAS = 10
# Os limites de uma faixa editada: maior que zero e até R$ 1 milhão por mês (acima disso é erro de digitação)
MAIOR_VALOR_DA_FAIXA = Decimal("1000000")
# Quantas profissões a busca da tela devolve de cada vez (o "Ver mais" pede as próximas)
PROFISSOES_POR_PAGINA = 50
# O que a tabela de alterações grava em "acao"
ACAO_EDITADA, ACAO_VOLTOU = "EDITADA", "VOLTOU_AO_CALCULADO"


# O campo que o banco cria no parâmetro do layout para ligar a comparação (os textos que a IA lê para achar a coluna)
DEFINICAO_DO_CAMPO = {
    "campo": CAMPO_DO_CBO, "grupo": "Cadastro empresarial", "tipo": "TEXTO", "obrigatorio": False, "sensivel": False,
    "uso_comercial_permitido": False, "igual_para_todos": False,
    "descricao": "Código da profissão do funcionário na CBO (Classificação Brasileira de Ocupações), o mesmo do eSocial",
    "regra": "6 dígitos da tabela oficial do Ministério do Trabalho, com ou sem o traço (ex.: 4110-10)",
    "nao_confundir_com": "Cargo (o nome da função); código da unidade; matrícula",
    "exemplo": "4110-10",
}


def cbo_ligado(conexao) -> bool:
    """True se o parâmetro do layout vigente tem o campo "codigo_cbo" (a comparação por profissão está ligada)."""
    _, campos = parametros.layout_ativo(conexao)
    for campo in campos:
        if campo.campo == CAMPO_DO_CBO:
            return True
    return False


def ligar_o_campo_do_cbo(conexao, autor: str) -> int:
    """Grava uma versão nova do parâmetro com o campo "codigo_cbo" no fim (se ainda não tem). Devolve a versão.

    É o mesmo que o especialista faz na tela Parâmetros ("+ Novo campo"); serve aos testes e ao servidor de teste.
    """
    numero, campos = parametros.layout_ativo(conexao)
    if cbo_ligado(conexao):
        return numero
    campos_em_dicionario = []
    for campo in campos:
        campos_em_dicionario.append(campo.model_dump(mode="json"))
    campos_em_dicionario.append(dict(DEFINICAO_DO_CAMPO))
    return parametros.salvar_layout(conexao, campos_em_dicionario, autor)


# ---------------- As tabelas ----------------

def _preparar(conexao) -> None:
    """Cria as três tabelas deste arquivo, se ainda não existirem, e carrega as faixas calculadas.

    O SQL é o mesmo no SQLite e no PostgreSQL (services/banco.py traduz o que muda). Os valores em reais ficam como
    texto ("2500.00"), como o valor_renda dos funcionários: sem arredondamento de número com vírgula.
    """
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS faixas_salariais_cbo (
               codigo_cbo        TEXT PRIMARY KEY,
               minimo            TEXT,
               maximo            TEXT,
               minimo_calculado  TEXT,
               maximo_calculado  TEXT,
               nivel             TEXT NOT NULL,     -- OCUPACAO, FAMILIA ou SEM_DADOS (de onde saiu a calculada)
               vinculos_na_base  INTEGER NOT NULL,
               fonte             TEXT NOT NULL,
               ano_base          INTEGER NOT NULL,
               calculado_em      TEXT NOT NULL,
               editado_por       TEXT,
               editado_em        TEXT
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS faixas_salariais_cbo_alteracoes (
               codigo_cbo     TEXT NOT NULL,
               acao           TEXT NOT NULL,        -- EDITADA ou VOLTOU_AO_CALCULADO
               minimo_antes   TEXT,
               maximo_antes   TEXT,
               minimo_depois  TEXT,
               maximo_depois  TEXT,
               alterado_por   TEXT NOT NULL,
               alterado_em    TEXT NOT NULL
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS cbo_dos_cargos (
               empresa_id        TEXT NOT NULL,
               cargo_normalizado TEXT NOT NULL,     -- o cargo sem acento, em minúsculas (a chave)
               cargo             TEXT NOT NULL,     -- o cargo como a empresa escreveu
               codigo_cbo        TEXT NOT NULL,
               origem            TEXT NOT NULL,     -- ARQUIVO ou CONFIRMADO_PELA_EMPRESA
               processamento_id  TEXT,              -- o envio em que veio ou foi confirmado
               registrado_por    TEXT,
               registrado_em     TEXT NOT NULL,
               PRIMARY KEY (empresa_id, cargo_normalizado)
           )"""
    )
    _carregar_as_faixas_calculadas(conexao)


def _agora() -> str:
    """O momento atual, no horário universal (UTC), sem frações de segundo."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _linhas_do_arquivo_das_faixas() -> list[dict]:
    """As linhas de data/cbo/faixas_salariais_cbo.csv (lista vazia se o arquivo ainda não foi calculado)."""
    if not ARQUIVO_DAS_FAIXAS.exists():
        return []
    with open(ARQUIVO_DAS_FAIXAS, encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _carregar_as_faixas_calculadas(conexao) -> None:
    """Grava na tabela as profissões do arquivo que ainda não estão lá (a faixa calculada vira também a em uso).

    "ON CONFLICT DO NOTHING": a profissão que já está na tabela (talvez editada pelo banco) nunca é regravada, e duas
    telas abrindo ao mesmo tempo logo depois do login não brigam pela mesma linha.
    """
    linhas = _linhas_do_arquivo_das_faixas()
    ja_gravadas = conexao.execute("SELECT COUNT(*) FROM faixas_salariais_cbo").fetchone()[0]
    # Tudo já carregado: nada a fazer (é o caso de quase toda chamada)
    if ja_gravadas >= len(linhas):
        return
    for linha in linhas:
        # Sem dados: mínimo e máximo vazios (NULL)
        minimo = linha["minimo"] or None
        maximo = linha["maximo"] or None
        conexao.execute(
            "INSERT INTO faixas_salariais_cbo (codigo_cbo, minimo, maximo, minimo_calculado, maximo_calculado, nivel, "
            "vinculos_na_base, fonte, ano_base, calculado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (codigo_cbo) DO NOTHING",
            (linha["codigo_cbo"], minimo, maximo, minimo, maximo, linha["nivel"], int(linha["vinculos_na_base"]),
             linha["fonte"], int(linha["ano_base"]), linha["calculado_em"]))
    conexao.commit()


# ---------------- A faixa de uma profissão ----------------

@dataclass
class Faixa:
    """A faixa em uso de uma profissão (mínimo e máximo em reais) e de onde ela veio."""

    minimo: Decimal
    maximo: Decimal
    fonte: str             # ex.: "RAIS 2025 - MTE" ou "faixa definida pelo banco"


# As colunas da tabela, na ordem do SELECT de _faixa_em_dicionario
COLUNAS_DA_FAIXA = ("codigo_cbo", "minimo", "maximo", "minimo_calculado", "maximo_calculado", "nivel",
                    "vinculos_na_base", "fonte", "ano_base", "calculado_em", "editado_por", "editado_em")


def _faixa_em_dicionario(linha) -> dict:
    """Uma linha da tabela como dicionário, com o título oficial e o código escrito como a CBO escreve."""
    faixa = {}
    for posicao, coluna in enumerate(COLUNAS_DA_FAIXA):
        faixa[coluna] = linha[posicao]
    faixa["titulo"] = tabela_cbo.titulo(faixa["codigo_cbo"])
    faixa["codigo_formatado"] = tabela_cbo.codigo_formatado(faixa["codigo_cbo"])
    return faixa


def faixa_do_codigo(conexao, codigo: str) -> dict:
    """A faixa de uma profissão, como dicionário. Levanta KeyError se o código não está na tabela."""
    _preparar(conexao)
    linha = conexao.execute(f"SELECT {', '.join(COLUNAS_DA_FAIXA)} FROM faixas_salariais_cbo WHERE codigo_cbo = ?",
                            (codigo,)).fetchone()
    if linha is None:
        raise KeyError(codigo)
    return _faixa_em_dicionario(linha)


def faixa_em_uso(conexao, codigo: str) -> Faixa | None:
    """A faixa que o Validador usa para a profissão, ou None (profissão sem dados ou fora da tabela)."""
    try:
        faixa = faixa_do_codigo(conexao, codigo)
    except KeyError:
        return None
    if not faixa["minimo"] or not faixa["maximo"]:
        return None
    # Editada pelo banco: a fonte passa a ser o banco; senão, a fonte pública e o ano
    fonte = faixa["fonte"]
    if faixa["editado_por"]:
        fonte = "faixa definida pelo banco"
    return Faixa(Decimal(faixa["minimo"]), Decimal(faixa["maximo"]), fonte)


def medida_das_faixas() -> dict:
    """Como a faixa calculada foi feita (base, quem entra, percentis, corte), do data/cbo/fontes.json."""
    if not ARQUIVO_DAS_FONTES.exists():
        return {}
    return json.loads(ARQUIVO_DAS_FONTES.read_text(encoding="utf-8")).get("medida", {})


def buscar_faixas(conexao, busca: str | None, inicio: int = 0) -> dict:
    """A busca da tela do banco: as profissões que batem (por código ou título), com a faixa de cada uma.

    Recebe: o texto digitado e de qual posição começar (0 = a primeira; o "Ver mais" manda 50, depois 100...).
    Devolve: {"faixas": [até 50], "total": quantas profissões batem, "inicio": a posição, "medida": {...}}.
    Ex.: busca vazia → as 50 primeiras e total 2694 (todas as profissões da CBO).
    """
    if inicio < 0:
        raise ValueError("A posição da busca não pode ser negativa.")
    _preparar(conexao)
    encontradas = tabela_cbo.buscar(busca or "")
    faixas = []
    for encontrada in encontradas[inicio:inicio + PROFISSOES_POR_PAGINA]:
        try:
            faixa = faixa_do_codigo(conexao, encontrada["codigo"])
        except KeyError:
            # Profissão da CBO que ainda não tem linha na tabela (as faixas ainda não foram calculadas)
            continue
        faixa["sinonimo"] = encontrada["sinonimo"]
        faixas.append(faixa)
    return {"faixas": faixas, "total": len(encontradas), "inicio": inicio, "medida": medida_das_faixas()}


# ---------------- Editar a faixa (só o banco) ----------------

def _valor_da_faixa(valor, nome: str) -> Decimal:
    """O valor digitado como dinheiro (Decimal com 2 casas), conferido. Levanta ValueError com a explicação.

    Aceita número (2500 ou 2500.5) ou texto no jeito brasileiro ("2.500,50") ou americano ("2500.50").
    """
    texto = str(valor).strip() if valor is not None else ""
    # Jeito brasileiro: tira o ponto dos milhares e troca a vírgula pelo ponto
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError(f"O {nome} precisa ser um valor em reais.")
    # "NaN" e "Infinity" também viram Decimal: não são valores em reais
    if not numero.is_finite():
        raise ValueError(f"O {nome} precisa ser um valor em reais.")
    if numero <= 0:
        raise ValueError(f"O {nome} precisa ser maior que zero.")
    if numero > MAIOR_VALOR_DA_FAIXA:
        raise ValueError(f"O {nome} passa de {formatacao.em_reais(MAIOR_VALOR_DA_FAIXA)} por mês.")
    return numero.quantize(Decimal("0.01"))


def _registrar_alteracao(conexao, codigo: str, acao: str, antes: dict, minimo_depois, maximo_depois,
                         login: str, momento: str) -> None:
    """Grava uma linha no registro das alterações (não faz commit)."""
    conexao.execute("INSERT INTO faixas_salariais_cbo_alteracoes (codigo_cbo, acao, minimo_antes, maximo_antes, "
                    "minimo_depois, maximo_depois, alterado_por, alterado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (codigo, acao, antes["minimo"], antes["maximo"], minimo_depois, maximo_depois, login, momento))


def editar_faixa(conexao, login: str, codigo: str, minimo, maximo) -> dict:
    """O banco muda o mínimo e o máximo de uma profissão. A faixa calculada continua guardada ao lado.

    Recebe: quem mudou (login), o código e os dois valores. Devolve: a faixa nova.
    Levanta KeyError (código fora da tabela) ou ValueError (valor inválido, ou mínimo maior que o máximo).
    """
    antes = faixa_do_codigo(conexao, codigo)
    minimo_conferido = _valor_da_faixa(minimo, "mínimo")
    maximo_conferido = _valor_da_faixa(maximo, "máximo")
    # A regra: o mínimo nunca pode ficar maior que o máximo (iguais pode: um piso fixo)
    if minimo_conferido > maximo_conferido:
        raise ValueError("O mínimo não pode ser maior que o máximo.")
    momento = _agora()
    conexao.execute("UPDATE faixas_salariais_cbo SET minimo = ?, maximo = ?, editado_por = ?, editado_em = ? "
                    "WHERE codigo_cbo = ?", (str(minimo_conferido), str(maximo_conferido), login, momento, codigo))
    _registrar_alteracao(conexao, codigo, ACAO_EDITADA, antes, str(minimo_conferido), str(maximo_conferido), login,
                         momento)
    conexao.commit()
    return faixa_do_codigo(conexao, codigo)


def voltar_ao_calculado(conexao, login: str, codigo: str) -> dict:
    """Desfaz a edição: a faixa em uso volta a ser a calculada dos dados públicos (e "editado por" fica vazio)."""
    antes = faixa_do_codigo(conexao, codigo)
    momento = _agora()
    conexao.execute("UPDATE faixas_salariais_cbo SET minimo = minimo_calculado, maximo = maximo_calculado, "
                    "editado_por = NULL, editado_em = NULL WHERE codigo_cbo = ?", (codigo,))
    _registrar_alteracao(conexao, codigo, ACAO_VOLTOU, antes, antes["minimo_calculado"], antes["maximo_calculado"],
                         login, momento)
    conexao.commit()
    return faixa_do_codigo(conexao, codigo)


def alteracoes(conexao, codigo: str) -> list[dict]:
    """As alterações de uma profissão, da mais recente para a mais antiga. KeyError se o código não existe."""
    faixa_do_codigo(conexao, codigo)
    linhas = conexao.execute("SELECT acao, minimo_antes, maximo_antes, minimo_depois, maximo_depois, alterado_por, "
                             "alterado_em FROM faixas_salariais_cbo_alteracoes WHERE codigo_cbo = ? "
                             "ORDER BY alterado_em DESC, rowid DESC", (codigo,))
    lista = []
    for acao, minimo_antes, maximo_antes, minimo_depois, maximo_depois, alterado_por, alterado_em in linhas:
        lista.append({"acao": acao, "minimo_antes": minimo_antes, "maximo_antes": maximo_antes,
                      "minimo_depois": minimo_depois, "maximo_depois": maximo_depois,
                      "alterado_por": alterado_por, "alterado_em": alterado_em})
    return lista


# ---------------- A profissão de cada cargo ----------------

@dataclass
class ProfissaoDoCargo:
    """A profissão registrada para um cargo de uma empresa."""

    codigo: str
    origem: str                    # ARQUIVO ou CONFIRMADO_PELA_EMPRESA
    processamento_id: str | None   # o envio em que veio ou foi confirmada


def profissoes_da_empresa(conexao, empresa_id: str) -> dict[str, ProfissaoDoCargo]:
    """{cargo normalizado: profissão} dos cargos da empresa que já têm profissão."""
    linhas = conexao.execute("SELECT cargo_normalizado, codigo_cbo, origem, processamento_id FROM cbo_dos_cargos "
                             "WHERE empresa_id = ?", (empresa_id,))
    profissoes = {}
    for cargo_normalizado, codigo, origem, processamento_id in linhas:
        profissoes[cargo_normalizado] = ProfissaoDoCargo(codigo, origem, processamento_id)
    return profissoes


def _gravar_profissao(conexao, empresa_id: str, cargo: str, codigo: str, origem: str, processamento_id: str,
                      registrado_por: str | None, substituir: bool) -> None:
    """Grava a profissão do cargo (não faz commit).

    substituir=False: só grava se o cargo ainda não tem profissão (a que veio no arquivo nunca apaga uma confirmada).
    substituir=True: grava por cima (a empresa acabou de confirmar esta).
    """
    comando = ("INSERT INTO cbo_dos_cargos (empresa_id, cargo_normalizado, cargo, codigo_cbo, origem, processamento_id, "
               "registrado_por, registrado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (empresa_id, "
               "cargo_normalizado) ")
    if substituir:
        comando += ("DO UPDATE SET cargo = excluded.cargo, codigo_cbo = excluded.codigo_cbo, origem = excluded.origem, "
                    "processamento_id = excluded.processamento_id, registrado_por = excluded.registrado_por, "
                    "registrado_em = excluded.registrado_em")
    else:
        comando += "DO NOTHING"
    conexao.execute(comando, (empresa_id, tabela_cbo.texto_normalizado(cargo), cargo.strip(), codigo, origem,
                              processamento_id, registrado_por, _agora()))


def _apagar_profissao_confirmada(conexao, empresa_id: str, cargo_normalizado: str, processamento_id: str) -> None:
    """Apaga a profissão que a empresa confirmou NESTE envio e depois desfez ou recusou (não faz commit)."""
    conexao.execute("DELETE FROM cbo_dos_cargos WHERE empresa_id = ? AND cargo_normalizado = ? AND origem = ? "
                    "AND processamento_id = ?", (empresa_id, cargo_normalizado, ORIGEM_CONFIRMADA, processamento_id))


def _quem_confirmou(conexao, processamento_id: str, linha: int) -> str | None:
    """O login de quem deu a última resposta ao alerta CBO_A_CONFIRMAR desta linha (a tabela é a do Validador)."""
    resposta = conexao.execute("SELECT usuario FROM resolucoes_alerta WHERE processamento_id = ? AND regra_id = ? "
                               "AND linha = ? ORDER BY criado_em DESC, rowid DESC",
                               (processamento_id, REGRA_CBO_A_CONFIRMAR, linha)).fetchone()
    if resposta is None:
        return None
    return resposta[0]


# ---------------- A faixa das outras empresas ----------------

def faixa_das_outras_empresas(conexao, empresa_id: str, codigo: str) -> tuple[Faixa, int, int] | None:
    """O mínimo e o máximo (percentis 5 e 95) do salário CLT dos funcionários já cadastrados de OUTRAS empresas na
    mesma profissão, com quantas empresas e pessoas entraram; ou None, com menos de 2 empresas ou 10 pessoas.

    A profissão de cada pessoa vem do cargo dela (tabela cbo_dos_cargos). Só os dois números saem daqui: nunca o
    salário, o cargo ou o nome de alguém de outra empresa.
    """
    # Os cargos das outras empresas registrados com esta profissão
    cargos_por_empresa = {}
    linhas = conexao.execute("SELECT empresa_id, cargo_normalizado FROM cbo_dos_cargos WHERE codigo_cbo = ? "
                             "AND empresa_id <> ?", (codigo, empresa_id))
    for outra_empresa, cargo_normalizado in linhas:
        cargos_por_empresa.setdefault(outra_empresa, set()).add(cargo_normalizado)
    if len(cargos_por_empresa) < MINIMO_DE_OUTRAS_EMPRESAS:
        return None
    # Garante que a tabela dos cadastrados existe (é do processamentos.py)
    processamentos._preparar(conexao)
    salarios = []
    empresas_com_pessoas = set()
    for outra_empresa, cargos in cargos_por_empresa.items():
        pessoas = conexao.execute("SELECT cargo, tipo_renda, valor_renda FROM funcionarios_homologados "
                                  "WHERE empresa_id = ?", (outra_empresa,))
        for cargo, tipo_renda, valor_renda in pessoas:
            if tipo_renda != TIPO_DE_RENDA_COMPARADO or not cargo or not valor_renda:
                continue
            if tabela_cbo.texto_normalizado(cargo) not in cargos:
                continue
            salario = _dinheiro_ou_nada(valor_renda)
            if salario is None or salario <= 0:
                continue
            salarios.append(salario)
            empresas_com_pessoas.add(outra_empresa)
    if len(empresas_com_pessoas) < MINIMO_DE_OUTRAS_EMPRESAS or len(salarios) < MINIMO_DE_PESSOAS_DAS_OUTRAS:
        return None
    # Os 19 pontos que dividem os salários em 20 partes iguais: o primeiro é o percentil 5 e o último, o 95
    pontos = statistics.quantiles(salarios, n=20, method="inclusive")
    faixa = Faixa(pontos[0].quantize(Decimal("0.01")), pontos[-1].quantize(Decimal("0.01")), "outras empresas")
    return faixa, len(empresas_com_pessoas), len(salarios)


def _dinheiro_ou_nada(texto) -> Decimal | None:
    """O valor como Decimal, ou None se não é um número (ex.: vazio)."""
    try:
        valor = Decimal(str(texto))
    except (InvalidOperation, ValueError):
        return None
    if not valor.is_finite():
        return None
    return valor


# ---------------- Os alertas (chamados pelo Validador) ----------------

class _Anotador:
    """Junta os achados deste arquivo no relatório do Validador, com a linha e a posição da pessoa."""

    def __init__(self, relatorio, registros: list[dict]):
        from services import validador
        self.relatorio = relatorio
        self.classe_do_achado = validador.Achado
        # Linha do arquivo → posição do funcionário (1 = primeiro), como o Validador faz
        self.posicao_da_linha = {}
        for posicao, registro in enumerate(registros, start=1):
            self.posicao_da_linha[registro["_linha"]] = posicao

    def anotar(self, regra: str, severidade: str, mensagem: str, acao: str, registro: dict, campo: str, valor) -> None:
        """Acrescenta um achado ao relatório."""
        valor_em_texto = None
        if valor not in (None, ""):
            valor_em_texto = str(valor)
        self.relatorio.achados.append(self.classe_do_achado(
            regra, severidade, mensagem, acao, linha=registro["_linha"],
            registro=self.posicao_da_linha.get(registro["_linha"]), campo=campo, valor=valor_em_texto))


def acrescentar_alertas(conexao, relatorio, normalizacao, empresa_id: str, processamento_id: str) -> None:
    """Acrescenta ao relatório do Validador os alertas de profissão e de salário fora da faixa (ADR-129).

    Recebe: a conexão, o relatório já feito pelo validar(), os dados atuais do envio, a empresa e o envio.
    Grava a profissão dos cargos (a que veio no arquivo e a que a empresa confirmou) e faz commit.
    """
    from services import validador
    # Sem o campo "codigo_cbo" no parâmetro, a comparação por profissão está desligada: o envio fica como era
    if not cbo_ligado(conexao):
        return
    _preparar(conexao)
    anotador = _Anotador(relatorio, normalizacao.registros)
    respostas = validador.resolucoes(conexao, processamento_id)
    profissoes = profissoes_da_empresa(conexao, empresa_id)
    cargos_ja_vistos = set()
    # As faixas já buscadas neste envio (uma consulta por profissão, e não por pessoa)
    faixas_ja_buscadas = {}
    for registro in normalizacao.registros:
        codigo = _profissao_do_registro(conexao, registro, empresa_id, processamento_id, profissoes, respostas,
                                        cargos_ja_vistos, anotador)
        if codigo is not None:
            _conferir_o_salario(conexao, registro, empresa_id, codigo, faixas_ja_buscadas, anotador)
    # Grava as profissões dos cargos (as respostas da empresa são marcadas depois, por validador.executar)
    conexao.commit()


def _profissao_do_registro(conexao, registro: dict, empresa_id: str, processamento_id: str, profissoes: dict,
                           respostas: dict, cargos_ja_vistos: set, anotador: _Anotador) -> str | None:
    """O código CBO da pessoa (da coluna do arquivo ou do cargo), anotando os alertas de profissão. None: sem código."""
    cargo = (registro.get("cargo") or "").strip()
    codigo_escrito = registro.get(CAMPO_DO_CBO)
    # 1. A coluna "Código CBO" veio preenchida: vale o que a empresa mandou
    if codigo_escrito not in (None, ""):
        codigo = tabela_cbo.codigo_normalizado(codigo_escrito)
        if not tabela_cbo.existe(codigo):
            anotador.anotar(REGRA_CBO_DESCONHECIDO, "ALERTA",
                            f'O código "{codigo_escrito}" não é uma profissão da tabela oficial de profissões (CBO). '
                            "Confira o código (são 6 dígitos, como 4110-10).",
                            "Corrigir o código", registro, CAMPO_DO_CBO, codigo_escrito)
            return None
        # O cargo passa a ter esta profissão (se ainda não tinha), para a comparação entre empresas
        if cargo:
            _gravar_profissao(conexao, empresa_id, cargo, codigo, ORIGEM_ARQUIVO, processamento_id, None,
                              substituir=False)
            profissoes.setdefault(tabela_cbo.texto_normalizado(cargo),
                                  ProfissaoDoCargo(codigo, ORIGEM_ARQUIVO, processamento_id))
        return codigo
    # 2. Sem código e sem cargo: nada a comparar
    if not cargo:
        return None
    cargo_normalizado = tabela_cbo.texto_normalizado(cargo)
    # A primeira pessoa do cargo neste envio decide (e recebe a pergunta); as outras seguem a resposta
    if cargo_normalizado not in cargos_ja_vistos:
        cargos_ja_vistos.add(cargo_normalizado)
        _perguntar_a_profissao_do_cargo(conexao, registro, cargo, empresa_id, processamento_id, profissoes, respostas,
                                        anotador)
    profissao = profissoes.get(cargo_normalizado)
    if profissao is None:
        return None
    return profissao.codigo


def _perguntar_a_profissao_do_cargo(conexao, registro: dict, cargo: str, empresa_id: str, processamento_id: str,
                                    profissoes: dict, respostas: dict, anotador: _Anotador) -> None:
    """Na primeira pessoa de um cargo sem profissão: a sugestão da CBO vira a pergunta CBO_A_CONFIRMAR.

    - A empresa já respondeu "Está certo" (CONFIRMADO) neste envio: a profissão é gravada e vale para o cargo;
    - desfez ou recusou: a profissão confirmada neste envio é apagada, e o cargo fica sem comparação;
    - o cargo já tem profissão de outro envio (ou do arquivo): nada a perguntar.
    O alerta continua no relatório depois da resposta (marcado como resolvido), para a empresa ver o que respondeu.
    """
    cargo_normalizado = tabela_cbo.texto_normalizado(cargo)
    profissao = profissoes.get(cargo_normalizado)
    # A profissão veio de outro envio ou do arquivo: não pergunta de novo
    if profissao is not None and not (profissao.origem == ORIGEM_CONFIRMADA
                                      and profissao.processamento_id == processamento_id):
        return
    sugestao = tabela_cbo.sugerir(cargo)
    if sugestao.situacao != tabela_cbo.SUGESTAO_UNICA:
        _avisar_sem_profissao(registro, cargo, sugestao, anotador)
        return
    anotador.anotar(REGRA_CBO_A_CONFIRMAR, "ALERTA",
                    f'O cargo "{cargo}" parece ser a profissão {tabela_cbo.codigo_formatado(sugestao.codigo)} '
                    f"({sugestao.titulo}) da tabela oficial de profissões (CBO).",
                    "Confirmar a profissão do cargo", registro, "cargo", cargo)
    resposta = respostas.get((REGRA_CBO_A_CONFIRMAR, registro["_linha"]))
    if resposta == "CONFIRMADO":
        _gravar_profissao(conexao, empresa_id, cargo, sugestao.codigo, ORIGEM_CONFIRMADA, processamento_id,
                          _quem_confirmou(conexao, processamento_id, registro["_linha"]), substituir=True)
        profissoes[cargo_normalizado] = ProfissaoDoCargo(sugestao.codigo, ORIGEM_CONFIRMADA, processamento_id)
    elif profissao is not None:
        # A empresa desfez ou recusou: a profissão confirmada neste envio sai
        _apagar_profissao_confirmada(conexao, empresa_id, cargo_normalizado, processamento_id)
        profissoes.pop(cargo_normalizado, None)


def _avisar_sem_profissao(registro: dict, cargo: str, sugestao, anotador: _Anotador) -> None:
    """O AVISO do cargo sem profissão na CBO (não bloqueia: só diz que o salário deste cargo não é comparado)."""
    if sugestao.situacao == tabela_cbo.SUGESTAO_AMBIGUA:
        opcoes = []
        for codigo, titulo in sugestao.opcoes[:tabela_cbo.OPCOES_NA_MENSAGEM]:
            opcoes.append(f"{tabela_cbo.codigo_formatado(codigo)} ({titulo})")
        explicacao = f'O cargo "{cargo}" pode ser mais de uma profissão da tabela oficial (CBO): {"; ".join(opcoes)}.'
    else:
        explicacao = f'Não achamos a profissão do cargo "{cargo}" na tabela oficial de profissões (CBO).'
    anotador.anotar(REGRA_CBO_NAO_ENCONTRADO, "AVISO",
                    explicacao + ' O salário deste cargo não é comparado com a faixa da profissão; para comparar, '
                                 'envie a coluna "Código CBO".',
                    "Enviar a coluna Código CBO", registro, "cargo", cargo)


def _conferir_o_salario(conexao, registro: dict, empresa_id: str, codigo: str, faixas_ja_buscadas: dict,
                        anotador: _Anotador) -> None:
    """Compara o salário CLT da pessoa com a faixa pública da profissão e a das outras empresas; um alerta por pessoa.

    Salário vazio, zerado ou negativo fica de fora (o Validador já aponta), e o pró-labore também.
    """
    if registro.get("tipo_renda") != TIPO_DE_RENDA_COMPARADO:
        return
    salario = _dinheiro_ou_nada(registro.get("valor_renda"))
    if salario is None or salario <= 0:
        return
    # As duas faixas da profissão, buscadas uma vez por envio
    if codigo not in faixas_ja_buscadas:
        faixas_ja_buscadas[codigo] = (faixa_em_uso(conexao, codigo),
                                      faixa_das_outras_empresas(conexao, empresa_id, codigo))
    faixa_publica, das_outras = faixas_ja_buscadas[codigo]
    # As faixas de que o salário saiu, já escritas para a mensagem
    fora_de = []
    if faixa_publica is not None and not faixa_publica.minimo <= salario <= faixa_publica.maximo:
        fora_de.append(f"da faixa da profissão, de {formatacao.em_reais(faixa_publica.minimo)} a "
                       f"{formatacao.em_reais(faixa_publica.maximo)} (fonte: {faixa_publica.fonte})")
    if das_outras is not None:
        faixa, quantas_empresas, _ = das_outras
        if not faixa.minimo <= salario <= faixa.maximo:
            fora_de.append(f"da faixa de outras {quantas_empresas} empresas nesta profissão, de "
                           f"{formatacao.em_reais(faixa.minimo)} a {formatacao.em_reais(faixa.maximo)}")
    if not fora_de:
        return
    profissao = f"{tabela_cbo.codigo_formatado(codigo)} ({tabela_cbo.titulo(codigo)})"
    anotador.anotar(REGRA_RENDA_FORA_DA_PROFISSAO, "ALERTA",
                    f"Salário de {formatacao.em_reais(salario)} fora {' e fora '.join(fora_de)}, na profissão "
                    f"{profissao}. Pode ser erro de digitação.",
                    "Corrigir ou confirmar", registro, "valor_renda", registro.get("valor_renda"))
