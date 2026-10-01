"""Baixa a tabela oficial de profissões (CBO) e calcula a faixa de salário de cada profissão com a RAIS (ADR-129).

Para que serve: o Validador compara o salário de cada funcionário com a faixa da profissão dele (o código CBO). Esta
faixa sai de dados PÚBLICOS e AGREGADOS do Ministério do Trabalho e Emprego (MTE). Nenhum dado de pessoa entra no
projeto: os microdados da RAIS ficam em storage/ (fora do Git) e daqui sai só uma tabela com um mínimo e um máximo
por profissão.

O que é cada coisa:
- CBO (Classificação Brasileira de Ocupações): a lista oficial de profissões do MTE. Cada profissão tem um código de
  6 dígitos (ex.: 411010 = "Assistente administrativo"); os 4 primeiros dígitos são a "família" (4110 = "Assistentes
  administrativos"). Os sinônimos são outros nomes da mesma profissão (ex.: "Auxiliar de escritório").
- RAIS (Relação Anual de Informações Sociais): a declaração que toda empresa entrega ao governo uma vez por ano, com
  cada emprego formal. O MTE publica os microdados sem identificação (sem nome, sem CPF, sem empresa).
- Percentil 5 e percentil 95: pondo os salários de uma profissão em fila, do menor ao maior, o percentil 5 é o salário
  de quem está na posição 5% e o percentil 95, na posição 95%. Os 5% de cada ponta (erros e casos raros) ficam fora.

O que este arquivo faz, em ordem:
1. Baixa os arquivos da CBO do site do MTE (ocupações, sinônimos e famílias) e grava uma cópia em UTF-8 em data/cbo/.
2. Baixa os microdados da RAIS 2025 (7 arquivos .7z, 3,8 GB) do FTP público do MTE para storage/fontes_publicas/.
3. Descompacta um arquivo por vez, lê só as 6 colunas que interessam e guarda o salário de dezembro de cada vínculo
   que entra na conta (CLT, ativo em 31/12, 30 horas semanais ou mais, sem ser intermitente). Apaga o texto
   descompactado logo depois (fica só o .7z).
4. Calcula, para cada profissão, o percentil 5 (o mínimo) e o percentil 95 (o máximo). Profissão com menos de 30
   vínculos usa a faixa da família; família com menos de 30 também fica "sem dados" (não gera alerta).
5. Grava data/cbo/faixas_salariais_cbo.csv e data/cbo/fontes.json (de onde veio cada arquivo, quando e a soma de
   conferência de cada um).

Como rodar (da pasta integra-folha; leva uns 40 minutos, quase todo o tempo lendo a RAIS):
    .venv\\Scripts\\python.exe scripts\\calcular_faixas_cbo.py            # tudo
    .venv\\Scripts\\python.exe scripts\\calcular_faixas_cbo.py --so-cbo   # só a tabela de profissões (segundos)
"""
import argparse
import csv
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy
import pandas
import py7zr

# Pasta raiz do projeto (integra-folha)
RAIZ = Path(__file__).resolve().parent.parent
# Onde fica a tabela derivada (vai para o Git: é pequena e só tem dados públicos agregados)
PASTA_DOS_DADOS = RAIZ / "data" / "cbo"
# Onde ficam os arquivos brutos baixados (fora do Git: a RAIS tem 3,8 GB)
PASTA_DAS_FONTES = RAIZ / "storage" / "fontes_publicas"

# O endereço dos arquivos da CBO no site do MTE, e o nome que cada um ganha em data/cbo/
ENDERECO_DA_CBO = "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/cbo/servicos/downloads/"
ARQUIVOS_DA_CBO = {
    "cbo2002-ocupacao.csv": "cbo2002_ocupacoes.csv",
    "cbo2002-sinonimo.csv": "cbo2002_sinonimos.csv",
    "cbo2002-familia.csv": "cbo2002_familias.csv",
}

# O ano da RAIS usada e o endereço dela no FTP público do MTE (Programa de Disseminação das Estatísticas do Trabalho)
ANO_DA_RAIS = 2025
ENDERECO_DA_RAIS = f"ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/{ANO_DA_RAIS}/"
# Os 7 arquivos de vínculos da RAIS 2025, um por região (NI = região não identificada)
ARQUIVOS_DA_RAIS = ("RAIS_VINC_PUB_CENTRO_OESTE.7z", "RAIS_VINC_PUB_MG_ES_RJ.7z", "RAIS_VINC_PUB_NI.7z",
                    "RAIS_VINC_PUB_NORDESTE.7z", "RAIS_VINC_PUB_NORTE.7z", "RAIS_VINC_PUB_SP.7z",
                    "RAIS_VINC_PUB_SUL.7z")

# As colunas da RAIS que interessam, com o nome curto que ganham aqui
COLUNAS_DA_RAIS = {
    "CBO 2002 Ocupação - Código": "codigo_cbo",
    "Ind Vínculo Ativo 31/12 - Código": "ativo_em_31_12",
    "Qtd Hora Contr": "horas_por_semana",
    "Vl Rem Dezembro Nom": "salario_de_dezembro",
    "Tipo Vínculo - Código": "tipo_de_vinculo",
    "Ind Trabalho Intermitente - Código": "intermitente",
}
# Os tipos de vínculo CLT, pelo dicionário da RAIS: 10, 15, 20 e 25 (prazo indeterminado, urbano e rural) e 60, 65,
# 70 e 75 (prazo determinado). Ficam fora o estatutário, o aprendiz, o temporário e o diretor sem vínculo
TIPOS_DE_VINCULO_CLT = (10, 15, 20, 25, 60, 65, 70, 75)
# A jornada mínima (horas por semana) para entrar na conta: a faixa é a de quem trabalha o tempo cheio
HORAS_MINIMAS_POR_SEMANA = 30
# Quantas linhas a RAIS é lida de cada vez (um "pedaço"; o arquivo inteiro não cabe na memória)
LINHAS_POR_PEDACO = 2_000_000

# A medida da faixa: percentil 5 (o mínimo) e percentil 95 (o máximo)
PERCENTIL_DO_MINIMO = 5
PERCENTIL_DO_MAXIMO = 95
# O corte: com menos vínculos que isto, a profissão usa a faixa da família (e a família, "sem dados")
MINIMO_DE_VINCULOS = 30
# Os três níveis de onde a faixa pode ter saído
NIVEL_OCUPACAO, NIVEL_FAMILIA, NIVEL_SEM_DADOS = "OCUPACAO", "FAMILIA", "SEM_DADOS"
# O texto da fonte gravado em cada linha da tabela
FONTE_DAS_FAIXAS = f"RAIS {ANO_DA_RAIS} - MTE"


def soma_de_conferencia(caminho: Path) -> str:
    """A "impressão digital" (SHA-256) do arquivo: se um byte mudar, ela muda.

    Recebe: o caminho. Devolve: 64 letras e números. Serve para provar, depois, qual arquivo foi usado.
    """
    # O calculador da impressão digital
    calculador = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        # Lê 8 MB de cada vez, para não pôr um arquivo de 1 GB inteiro na memória
        while True:
            bloco = arquivo.read(8 * 1024 * 1024)
            if not bloco:
                break
            calculador.update(bloco)
    return calculador.hexdigest()


def baixar(endereco: str, destino: Path) -> None:
    """Baixa o endereço para o destino, se o arquivo ainda não estiver lá.

    Recebe: o endereço (https:// ou ftp://) e o caminho de destino. Não devolve nada.
    """
    # Já baixado antes: não baixa de novo (a RAIS leva uns 10 minutos)
    if destino.exists() and destino.stat().st_size > 0:
        print(f"  já existe: {destino.name}")
        return
    # Garante a pasta de destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"  baixando {endereco}")
    # Baixa para um nome provisório e só renomeia no fim: um download interrompido nunca parece completo
    provisorio = destino.with_suffix(destino.suffix + ".parcial")
    urllib.request.urlretrieve(endereco, provisorio)
    provisorio.replace(destino)


def baixar_a_cbo(fontes: dict) -> None:
    """Passo 1: baixa os 3 arquivos da CBO e grava em data/cbo/ em UTF-8, com vírgula como separador.

    Recebe: o dicionário das fontes (é preenchido aqui). O original do MTE vem em Latin-1 e com ";".
    """
    PASTA_DOS_DADOS.mkdir(parents=True, exist_ok=True)
    for nome_no_site, nome_aqui in ARQUIVOS_DA_CBO.items():
        # O original fica em storage/, como veio do site
        original = PASTA_DAS_FONTES / "cbo_2002" / nome_no_site
        baixar(ENDERECO_DA_CBO + nome_no_site, original)
        # Lê o original (Latin-1, separado por ";", colunas CODIGO e TITULO)
        linhas_convertidas = []
        with open(original, encoding="latin-1", newline="") as arquivo:
            for linha in csv.DictReader(arquivo, delimiter=";"):
                # Tira os espaços das pontas; o código fica como texto (a família "0101" começa com zero)
                linhas_convertidas.append({"codigo": linha["CODIGO"].strip(), "titulo": linha["TITULO"].strip()})
        # Grava a cópia em UTF-8, com vírgula
        with open(PASTA_DOS_DADOS / nome_aqui, "w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=["codigo", "titulo"])
            escritor.writeheader()
            escritor.writerows(linhas_convertidas)
        # Anota de onde veio, quando foi baixado e a impressão digital do original
        baixado_em = datetime.fromtimestamp(original.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        fontes["cbo"][nome_aqui] = {"endereco": ENDERECO_DA_CBO + nome_no_site, "baixado_em": baixado_em,
                                    "sha256_do_original": soma_de_conferencia(original),
                                    "linhas": len(linhas_convertidas)}
        print(f"  {nome_aqui}: {len(linhas_convertidas)} linhas")


def salarios_de_um_arquivo(arquivo_7z: Path) -> pandas.DataFrame:
    """Passo 3: descompacta um arquivo da RAIS e devolve (codigo_cbo, salario) dos vínculos que entram na conta.

    Recebe: o .7z. Devolve: uma tabela com duas colunas (código CBO como número e salário de dezembro).
    O texto descompactado (de 0,1 a 7 GB) é apagado no fim; o .7z fica.
    """
    # A pasta provisória da descompactação
    pasta_extraida = PASTA_DAS_FONTES / f"rais_{ANO_DA_RAIS}" / "extraido"
    pasta_extraida.mkdir(parents=True, exist_ok=True)
    # A pasta onde a descompactação acontece: só depois de completa o arquivo vai para a pasta_extraida
    pasta_provisoria = pasta_extraida / "descompactando"
    with py7zr.SevenZipFile(arquivo_7z) as compactado:
        # Cada .7z tem um único arquivo de texto dentro
        nome_de_dentro = compactado.getnames()[0]
        texto = pasta_extraida / nome_de_dentro
        # Descompacta só se ainda não estiver descompactado (uma execução interrompida pode ter deixado o texto pronto)
        if not texto.exists():
            # Uma descompactação interrompida deixa um pedaço na pasta provisória: ele é apagado antes
            if pasta_provisoria.exists():
                for sobra in pasta_provisoria.iterdir():
                    sobra.unlink()
            compactado.extractall(pasta_provisoria)
            # Completa: move para o lugar definitivo
            (pasta_provisoria / nome_de_dentro).replace(texto)
    # Os pedaços já filtrados, juntados no fim
    pedacos_filtrados = []
    leitor = pandas.read_csv(texto, sep=",", encoding="latin-1", usecols=list(COLUNAS_DA_RAIS),
                             chunksize=LINHAS_POR_PEDACO, dtype=str)
    for pedaco in leitor:
        # Nomes curtos nas colunas
        pedaco = pedaco.rename(columns=COLUNAS_DA_RAIS)
        # Os números vêm como texto; "errors=coerce" transforma o que não é número em vazio (NaN)
        codigo = pandas.to_numeric(pedaco["codigo_cbo"], errors="coerce")
        ativo = pandas.to_numeric(pedaco["ativo_em_31_12"], errors="coerce")
        horas = pandas.to_numeric(pedaco["horas_por_semana"], errors="coerce")
        salario = pandas.to_numeric(pedaco["salario_de_dezembro"], errors="coerce")
        tipo = pandas.to_numeric(pedaco["tipo_de_vinculo"], errors="coerce")
        intermitente = pandas.to_numeric(pedaco["intermitente"], errors="coerce")
        # Quem entra na conta: CLT, ativo em 31/12, tempo cheio, não intermitente, salário de dezembro maior que zero
        entra_na_conta = ((ativo == 1) & tipo.isin(TIPOS_DE_VINCULO_CLT) & (horas >= HORAS_MINIMAS_POR_SEMANA)
                          & (intermitente != 1) & (salario > 0) & codigo.notna())
        # Guarda só o código e o salário de quem entra (números pequenos, para caber na memória)
        pedacos_filtrados.append(pandas.DataFrame({"codigo_cbo": codigo[entra_na_conta].astype("int32"),
                                                   "salario": salario[entra_na_conta].astype("float32")}))
    # Apaga o texto descompactado: o .7z continua guardado
    texto.unlink()
    return pandas.concat(pedacos_filtrados, ignore_index=True)


def faixa_de_um_grupo(salarios: numpy.ndarray) -> tuple[float, float]:
    """Passo 4: o mínimo (percentil 5) e o máximo (percentil 95) de uma lista de salários, arredondados ao centavo.

    Ex.: 100 salários de R$ 1.000 a R$ 10.900, de 100 em 100 → (R$ 1.495,00, R$ 10.405,00).
    """
    minimo = float(numpy.percentile(salarios, PERCENTIL_DO_MINIMO))
    maximo = float(numpy.percentile(salarios, PERCENTIL_DO_MAXIMO))
    return round(minimo, 2), round(maximo, 2)


def faixas_por_grupo(salarios: pandas.DataFrame, coluna_do_grupo: str) -> dict[str, dict]:
    """Calcula a faixa de cada grupo (profissão ou família) com vínculos suficientes.

    Recebe: a tabela (codigo_cbo, salario, familia) e a coluna que define o grupo.
    Devolve: {código do grupo: {"minimo", "maximo", "vinculos"}}; grupo abaixo do corte fica de fora.
    """
    faixas = {}
    for codigo_do_grupo, salarios_do_grupo in salarios.groupby(coluna_do_grupo)["salario"]:
        # Poucos vínculos: a faixa não seria confiável
        if len(salarios_do_grupo) < MINIMO_DE_VINCULOS:
            continue
        minimo, maximo = faixa_de_um_grupo(salarios_do_grupo.to_numpy())
        faixas[str(codigo_do_grupo)] = {"minimo": minimo, "maximo": maximo, "vinculos": len(salarios_do_grupo)}
    return faixas


def calcular_as_faixas(fontes: dict) -> None:
    """Passos 2 a 5: baixa a RAIS, lê os salários, calcula as faixas e grava a tabela."""
    pasta_da_rais = PASTA_DAS_FONTES / f"rais_{ANO_DA_RAIS}"
    todos_os_salarios = []
    for nome in ARQUIVOS_DA_RAIS:
        arquivo_7z = pasta_da_rais / nome
        baixar(ENDERECO_DA_RAIS + nome, arquivo_7z)
        print(f"  lendo {nome}")
        salarios = salarios_de_um_arquivo(arquivo_7z)
        print(f"    {len(salarios)} vínculos entram na conta")
        todos_os_salarios.append(salarios)
        # Anota o arquivo usado e a impressão digital dele
        fontes["rais"][nome] = {"endereco": ENDERECO_DA_RAIS + nome, "sha256": soma_de_conferencia(arquivo_7z),
                                "vinculos_na_conta": len(salarios)}
    salarios = pandas.concat(todos_os_salarios, ignore_index=True)
    # O código com 6 dígitos (o 0 da frente some quando vira número: 10105 → "010105") e a família (4 primeiros)
    salarios["codigo_cbo"] = salarios["codigo_cbo"].astype(str).str.zfill(6)
    salarios["familia"] = salarios["codigo_cbo"].str[:4]
    faixas_das_ocupacoes = faixas_por_grupo(salarios, "codigo_cbo")
    faixas_das_familias = faixas_por_grupo(salarios, "familia")
    gravar_a_tabela(faixas_das_ocupacoes, faixas_das_familias, len(salarios))
    fontes["rais"]["total_de_vinculos_na_conta"] = len(salarios)


def gravar_a_tabela(faixas_das_ocupacoes: dict, faixas_das_familias: dict, total_de_vinculos: int) -> None:
    """Passo 5: uma linha para CADA profissão da CBO, com a faixa da profissão, a da família ou "sem dados"."""
    calculado_em = datetime.now(timezone.utc).date().isoformat()
    linhas = []
    with open(PASTA_DOS_DADOS / "cbo2002_ocupacoes.csv", encoding="utf-8", newline="") as arquivo:
        for ocupacao in csv.DictReader(arquivo):
            codigo = ocupacao["codigo"]
            if codigo in faixas_das_ocupacoes:
                # A profissão tem vínculos suficientes: usa a faixa dela
                faixa, nivel = faixas_das_ocupacoes[codigo], NIVEL_OCUPACAO
            elif codigo[:4] in faixas_das_familias:
                # Poucos vínculos na profissão, mas a família tem: usa a da família
                faixa, nivel = faixas_das_familias[codigo[:4]], NIVEL_FAMILIA
            else:
                # Nem a família tem: sem faixa (o Validador não gera alerta de profissão para ela)
                faixa, nivel = {"minimo": "", "maximo": "", "vinculos": 0}, NIVEL_SEM_DADOS
            # Os valores com duas casas ("1518.00"), como o valor_renda dos funcionários
            minimo, maximo = faixa["minimo"], faixa["maximo"]
            if minimo != "":
                minimo, maximo = f"{minimo:.2f}", f"{maximo:.2f}"
            linhas.append({"codigo_cbo": codigo, "minimo": minimo, "maximo": maximo, "nivel": nivel,
                           "vinculos_na_base": faixa["vinculos"], "fonte": FONTE_DAS_FAIXAS,
                           "ano_base": ANO_DA_RAIS, "calculado_em": calculado_em})
    with open(PASTA_DOS_DADOS / "faixas_salariais_cbo.csv", "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)
    # O resumo de quantas profissões ficaram em cada nível
    contagem = {NIVEL_OCUPACAO: 0, NIVEL_FAMILIA: 0, NIVEL_SEM_DADOS: 0}
    for linha in linhas:
        contagem[linha["nivel"]] += 1
    print(f"  {len(linhas)} profissões ({total_de_vinculos} vínculos): {contagem}")


def principal() -> None:
    """Lê as opções da linha de comando e roda os passos."""
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--so-cbo", action="store_true", help="só baixa e converte a tabela de profissões")
    opcoes = argumentos.parse_args()
    # O registro das fontes: começa do que já existe (a execução só da CBO não apaga o registro da RAIS)
    caminho_das_fontes = PASTA_DOS_DADOS / "fontes.json"
    fontes = {"cbo": {}, "rais": {}}
    if caminho_das_fontes.exists():
        fontes = json.loads(caminho_das_fontes.read_text(encoding="utf-8"))
    # A medida usada, para a tela e a documentação lerem daqui
    fontes["medida"] = {"base": f"RAIS {ANO_DA_RAIS}, microdados de vínculos (MTE/PDET)",
                        "quem_entra": "vínculos CLT ativos em 31/12, jornada de 30 horas semanais ou mais, "
                                      "não intermitentes, remuneração de dezembro maior que zero",
                        "valor": "remuneração nominal de dezembro",
                        "minimo": f"percentil {PERCENTIL_DO_MINIMO}", "maximo": f"percentil {PERCENTIL_DO_MAXIMO}",
                        "corte": f"menos de {MINIMO_DE_VINCULOS} vínculos: faixa da família (4 dígitos); "
                                 "família também abaixo: sem dados"}
    print("1. Tabela de profissões (CBO)")
    baixar_a_cbo(fontes)
    if not opcoes.so_cbo:
        print("2 a 5. RAIS e faixas")
        calcular_as_faixas(fontes)
    caminho_das_fontes.write_text(json.dumps(fontes, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Pronto.")


if __name__ == "__main__":
    # Os acentos saem certos no terminal do Windows
    sys.stdout.reconfigure(encoding="utf-8")
    principal()
