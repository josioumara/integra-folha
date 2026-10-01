"""A data da versão que está rodando, para o rótulo "Atualizado em ..." no fim de todas as telas (ADR-133).

Para que serve: mostrar, no rodapé do site, quando a aplicação foi atualizada pela última vez. A data é a
da VERSÃO (o último commit da versão principal que o servidor carregou), e não a hora de agora nem a da publicação.

De onde vem a data, nesta ordem (vale a primeira que existir e for uma data de verdade):
1. a variável de ambiente DATA_DA_VERSAO (ex.: "2026-09-29T14:30:00-03:00"), para quem quiser informar à mão;
2. o arquivo versao_da_aplicacao.txt, na raiz do repositório. No Git, ele guarda o marcador "$Format:%cI$". Quando a
   imagem do site é montada com o "git archive" (publicacao/publicar.sh), o próprio Git troca o marcador pela data
   do commit (a regra "export-subst" do .gitattributes). Assim, o site na AWS, que não tem a pasta .git, sabe a data;
3. o próprio Git (git log -1), na máquina local, onde a pasta .git existe;
4. nenhuma das três: não há data, e o rótulo não aparece. Nunca se inventa uma data.

A data é lida UMA vez, na primeira consulta, e guardada: é a da versão que o servidor carregou ao subir.

Conceitos para leigo:
    - Commit: cada "foto" do código guardada no Git, com a data em que foi tirada.
    - export-subst: uma regra do Git que troca um marcador dentro de um arquivo pela informação do commit (a data,
      por exemplo) na hora de exportar o código com o "git archive".
    - ISO 8601: o jeito padrão de escrever data e hora em texto, com o fuso no fim (ex.: "2026-09-29T14:30:00-03:00").
"""
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A raiz do repositório (a pasta acima de services/), onde ficam o .git e o versao_da_aplicacao.txt
RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parent.parent
# O arquivo que o "git archive" preenche com a data do commit
ARQUIVO_DA_VERSAO = RAIZ_DO_REPOSITORIO / "versao_da_aplicacao.txt"
# O nome da variável de ambiente que, se existir, vale mais que tudo
NOME_DA_VARIAVEL = "DATA_DA_VERSAO"
# O horário de Brasília: 3 horas a menos que o horário universal (o Brasil não tem horário de verão desde 2019)
HORARIO_DE_BRASILIA = timezone(timedelta(hours=-3))
# Quanto tempo o Git pode levar para responder, em segundos (se travar, fica sem data, e o servidor sobe do mesmo jeito)
TEMPO_MAXIMO_DO_GIT = 5

# A data já lida (guardada depois da primeira consulta). "ainda_nao_lida" distingue "não li" de "li e não havia data"
_data_guardada = "ainda_nao_lida"


def ler_data_iso(texto: str | None) -> datetime | None:
    """Converte um texto ISO 8601 numa data com fuso. Texto vazio, marcador não preenchido ou lixo: None.

    Recebe: texto — ex.: "2026-09-29T14:30:00-03:00", "2026-09-29T17:30:00Z" ou "$Format:%cI$".
    Devolve: a data (datetime com fuso) ou None.
    Exemplos: "2026-09-29T14:30:00-03:00" → 29/09/2026 14:30 (−03:00); "$Format:%cI$" → None; "ontem" → None.
    """
    # Nada escrito: sem data
    if texto is None:
        return None
    # Tira os espaços e a quebra de linha das pontas (o arquivo e o Git terminam com uma quebra de linha)
    texto_limpo = texto.strip()
    # Vazio depois de limpar: sem data
    if texto_limpo == "":
        return None
    # Tenta ler como data ISO (o Python 3.12 entende o fuso "-03:00" e o "Z" do horário universal)
    try:
        data = datetime.fromisoformat(texto_limpo)
    except ValueError:
        # Não é uma data (ex.: o marcador "$Format:%cI$", que o Git só troca no "git archive")
        return None
    # Uma data sem fuso seria ambígua (de que horário?): não arrisca
    if data.tzinfo is None:
        return None
    # Uma data de verdade, com fuso
    return data


def data_da_variavel_de_ambiente() -> datetime | None:
    """A data da variável DATA_DA_VERSAO, se ela existe e é uma data ISO com fuso; senão, None."""
    # Lê a variável (None se não existe)
    return ler_data_iso(os.environ.get(NOME_DA_VARIAVEL))


def data_do_arquivo(arquivo: Path | None = None) -> datetime | None:
    """A data do versao_da_aplicacao.txt, se o "git archive" já o preencheu; senão, None.

    Recebe: arquivo — o caminho do arquivo; sem ele, o versao_da_aplicacao.txt da raiz (os testes passam outro).
    Devolve: a data, ou None se o arquivo não existe, não pode ser lido ou ainda tem o marcador "$Format:%cI$".
    """
    # Sem caminho informado: o arquivo da raiz do repositório
    if arquivo is None:
        arquivo = ARQUIVO_DA_VERSAO
    # Sem o arquivo: sem data por aqui
    if not arquivo.exists():
        return None
    # Lê o texto do arquivo; se não der (sem permissão, é uma pasta, bytes que não são texto), fica sem data, e a rota
    # sem login nunca responde erro por causa disso
    try:
        texto_do_arquivo = arquivo.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    # Tenta entender o texto como data
    return ler_data_iso(texto_do_arquivo)


def data_do_git(raiz: Path | None = None) -> datetime | None:
    """A data do último commit da versão que está na pasta, perguntada ao Git; sem Git, None.

    Recebe: raiz — a pasta do repositório; sem ela, a raiz desta aplicação (os testes passam outra).
    Devolve: a data do commit (a do "committer", a de quando ele entrou na versão), ou None se a pasta não é um
    repositório, se o Git não está instalado ou se ele não respondeu a tempo.
    """
    # Sem pasta informada: a raiz desta aplicação
    if raiz is None:
        raiz = RAIZ_DO_REPOSITORIO
    # "%cI" é a data do commit no formato ISO 8601, com o fuso de quem fez o commit
    comando = ["git", "-C", str(raiz), "log", "-1", "--format=%cI"]
    # Pergunta ao Git, sem mostrar nada na tela
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=TEMPO_MAXIMO_DO_GIT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        # O Git não está instalado (OSError) ou travou: sem data
        return None
    # O Git respondeu com erro (ex.: a pasta não é um repositório): sem data
    if resultado.returncode != 0:
        return None
    # Converte a resposta em data
    return ler_data_iso(resultado.stdout)


def descobrir_data_da_versao() -> datetime | None:
    """Procura a data da versão nas três fontes, em ordem (variável, arquivo, Git). Sem nenhuma, None."""
    # 1. A variável de ambiente vale mais que tudo
    data = data_da_variavel_de_ambiente()
    if data is not None:
        return data
    # 2. O arquivo preenchido pelo "git archive" (o site publicado)
    data = data_do_arquivo()
    if data is not None:
        return data
    # 3. O Git da máquina local (pode ser None: aí não há data)
    return data_do_git()


def data_da_versao() -> datetime | None:
    """A data da versão que o servidor carregou: descobre na primeira consulta e guarda para as seguintes."""
    # A variável guardada é a do arquivo (o "global" permite trocar o valor dela aqui dentro)
    global _data_guardada
    # Primeira consulta: descobre e guarda
    if _data_guardada == "ainda_nao_lida":
        _data_guardada = descobrir_data_da_versao()
    # Devolve a data guardada (ou None)
    return _data_guardada


def esquecer_data_guardada() -> None:
    """Apaga a data guardada, para a próxima consulta descobrir de novo (usado pelos testes)."""
    # Volta ao estado de "ainda não li"
    global _data_guardada
    _data_guardada = "ainda_nao_lida"


def texto_do_rotulo(data: datetime | None) -> str | None:
    """O texto do rótulo do rodapé, no horário de Brasília. Sem data, None (e o rótulo não aparece).

    Recebe: data — a data da versão, com fuso (ou None).
    Devolve: ex.: "Atualizado em 29/09/2026 às 14:30"; ou None.
    Exemplo: 2026-09-29T17:30:00Z (horário universal) → "Atualizado em 29/09/2026 às 14:30".
    """
    # Sem data: sem rótulo
    if data is None:
        return None
    # Passa a data para o horário de Brasília (um commit feito em outro fuso aparece na hora de Brasília)
    data_em_brasilia = data.astimezone(HORARIO_DE_BRASILIA)
    # Dia/mês/ano e hora:minuto, com zero à esquerda (ex.: 05/09/2026 às 08:05)
    return "Atualizado em " + data_em_brasilia.strftime("%d/%m/%Y") + " às " + data_em_brasilia.strftime("%H:%M")


def rotulo_da_versao() -> dict:
    """O que a rota /api/versao devolve: só o texto do rótulo (ou None). Nenhum outro dado da versão sai daqui.

    Devolve: {"texto": "Atualizado em 29/09/2026 às 14:30"} ou {"texto": None}.
    """
    # O texto a partir da data guardada
    return {"texto": texto_do_rotulo(data_da_versao())}
