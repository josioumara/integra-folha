"""Gera a base viva: os arquivos e o roteiro de 17 empresas usando a plataforma (desenho §3.8; ADR-143).

Para que serve: dados sintéticos que fazem a plataforma parecer viva, nos painéis do banco e na
jornada da empresa. Este gerador sorteia, com uma semente FIXA, tudo o que as 17 empresas "fizeram":
    - o cadastro de cada empresa (CNPJ válido, filiais, domínio, kit de marca) e o login do RH;
    - as pessoas de cada empresa, com os 4 obrigatórios (CPF, código CBO da profissão, renda bruta e admissão) e parte
      dos campos opcionais, do jeito que o sistema de RH de cada uma escreve (catalogos_da_base_viva.py);
    - um arquivo por envio (CSV ou Excel), com os erros de digitação que a empresa corrigiu (ou ainda vai corrigir);
    - o roteiro (roteiro.json): em que etapa cada envio está, quando cada coisa aconteceu (em dias úteis antes da
      carga), as correções, as contas que o banco abriu, os acessos ao portal e as conversas com o banco.
Quem põe tudo no banco de dados é o scripts/carregar_base_viva.py, SEM chamar a IA.

Regras (as do projeto para dados sintéticos):
    - 100% sintético: nomes sorteados de listas comuns, CPF e CNPJ sorteados com o dígito verificador certo (a
      plataforma exige), e-mails em domínios ".example" (reservados, nunca de ninguém);
    - a semente é fixa (SEMENTE) e a data de referência também (catalogos.REFERENCIA_DO_GERADOR): rodar de novo refaz
      exatamente o mesmo conjunto. Cada empresa tem o seu próprio sorteio, então gerar só algumas empresas (nos
      testes) dá as mesmas pessoas que o conjunto inteiro;
    - os salários saem de "degraus" por profissão, dentro da faixa pública da CBO (data/cbo): todas as empresas usam
      os mesmos degraus, e a faixa das outras empresas (ADR-129) liga sem abrir alerta à toa;
    - nada daqui vai para a IA (prompt, regra ou RAG) nem para a avaliação: a pasta data/base_viva/ é só da carga.

Para rodar: python scripts/gerar_base_viva.py
Resultado: data/base_viva/roteiro.json e data/base_viva/arquivos/<empresa>/<arquivo>.
"""
import csv
import io
import json
import random
import shutil
import sys
import unicodedata
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from openpyxl import Workbook  # noqa: E402

from scripts import catalogos_da_base_viva as catalogos  # noqa: E402
from services import tabela_cbo, validador  # noqa: E402
from services.documentos import cnpj_valido, cpf_valido, gerar_cnpj, gerar_cpf  # noqa: E402

# A semente fixa do sorteio: com ela, o mesmo conjunto é refeito igual (anotada também no roteiro)
SEMENTE = 20260930
# A versão do formato do roteiro (sobe se o formato mudar, para a carga recusar um roteiro que ela não entende)
VERSAO_DO_ROTEIRO = 1
# Onde a base viva fica (fora da avaliação, data/golden e data/avaliacao, e fora das bases do QA)
PASTA_DA_BASE_VIVA = RAIZ / "data" / "base_viva"
# O nome do roteiro e da pasta dos arquivos dentro dela
NOME_DO_ROTEIRO = "roteiro.json"
NOME_DA_PASTA_DOS_ARQUIVOS = "arquivos"
# A faixa pública de cada profissão (RAIS 2025), a mesma que o banco usa (services/faixa_salarial_cbo.py)
ARQUIVO_DAS_FAIXAS = RAIZ / "data" / "cbo" / "faixas_salariais_cbo.csv"

# Os degraus de salário de cada profissão: 4 pontos da faixa (18%, 26%, 34% e 42% do caminho entre o mínimo e o
# máximo), com mais gente nos degraus de baixo. Como todas as empresas usam os mesmos degraus, o mínimo e o máximo da
# faixa "das outras empresas" (os percentis 5 e 95) caem no primeiro e no último degrau
POSICOES_DOS_DEGRAUS = (Decimal("0.18"), Decimal("0.26"), Decimal("0.34"), Decimal("0.42"))
PESOS_DOS_DEGRAUS = (35, 30, 20, 15)
# Ninguém ganha menos que isto (um piso um pouco acima do salário mínimo)
PISO_SALARIAL = Decimal("1630.00")
# O pró-labore dos sócios (dentro da referência do cargo "Sócio-administrador", de R$ 12 mil a R$ 32 mil) e o
# pró-labore alto, que abre o alerta que a empresa confirma
DEGRAUS_DO_PRO_LABORE = (Decimal("15000.00"), Decimal("20000.00"), Decimal("25000.00"))
PRO_LABORE_ALTO = Decimal("45000.00")

# O expediente em que as pessoas trabalham no portal (em minutos desde a meia-noite, horário de Brasília)
INICIO_DO_EXPEDIENTE = 8 * 60 + 30
FIM_DO_EXPEDIENTE = 18 * 60 + 30
# A parte das pessoas de cada tipo no arquivo de contas do banco: nova conta ou correntista (e, no correntista, se
# ele está ativo e se a folha dele já era identificada; o "N" é o falso não folha do business case)
PARTE_DE_NOVAS_CONTAS = 0.42
PARTE_DE_CORRENTISTAS_ATIVOS = 0.78
PARTE_COM_A_FOLHA_JA_IDENTIFICADA = 0.40
# O motivo de cada correção que a empresa fez, pelo tipo do erro de digitação (o texto que fica na correção)
MOTIVOS_DAS_CORRECOES = {
    "cpf_digitado_errado": "CPF digitado errado; conferido no documento da pessoa.",
    "admissao_vazia": "Data de admissão que faltou; conferida no contrato de trabalho.",
    "cbo_desconhecido": "Código CBO digitado errado; conferido no eSocial.",
    "cbo_vazio": "Código CBO que faltou; conferido no eSocial.",
    "salario_vazio": "Salário que faltou; conferido na folha do mês.",
    "salario_dez_vezes": "Salário com um zero a mais; conferido na folha do mês.",
}
# As palavras dos cargos de nível superior e de nível técnico (para sortear a escolaridade de cada pessoa)
PALAVRAS_DE_NIVEL_SUPERIOR = ("Analista", "Engenheiro", "Médico", "Enfermeiro", "Farmacêutico", "Fisioterapeuta",
                              "Biomédico", "Professor", "Professora", "Coordenadora", "Gerente", "Designer", "Sócio")
PALAVRAS_DE_NIVEL_TECNICO = ("Técnico", "Supervisor", "Assistente", "Inspetor", "Mestre", "Governanta")


# ================================ Datas e momentos ================================

def dia_util_antes(dia: date, dias_uteis: int) -> date:
    """O dia que fica `dias_uteis` dias úteis antes de `dia` (sábado e domingo não contam; feriados ainda contam).

    Ex.: quarta-feira 30/09/2026 e 2 dias úteis → segunda-feira 28/09/2026; e 3 → sexta-feira 25/09/2026.
    """
    # Começa no próprio dia e volta até descontar todos os dias úteis
    resultado = dia
    restantes = dias_uteis
    while restantes > 0:
        # Volta um dia no calendário
        resultado = resultado - timedelta(days=1)
        # weekday(): 0 é segunda e 4 é sexta; só os dias úteis descontam
        if resultado.weekday() < 5:
            restantes = restantes - 1
    return resultado


def _momento(dias_uteis: int, minutos: int) -> dict:
    """Um momento do roteiro: quantos dias úteis antes da carga e a hora (HH:MM, horário de Brasília).

    Ex.: (3, 615) → {"dias_uteis": 3, "hora": "10:15"}.
    """
    # Os minutos desde a meia-noite viram "HH:MM" (615 minutos → 10 horas e 15 minutos)
    return {"dias_uteis": dias_uteis, "hora": f"{minutos // 60:02d}:{minutos % 60:02d}"}


def _depois(dias_uteis: int, minutos: int, minutos_a_mais: int) -> tuple[int, int]:
    """O momento `minutos_a_mais` depois de (dias_uteis, minutos), passando para o dia útil seguinte fora do expediente.

    Recebe e devolve (dias úteis antes da carga, minutos desde a meia-noite). O dia útil seguinte é o de número menor
    (mais perto da carga). Nunca passa do dia 1 (ontem): o que não cabe fica no fim do expediente dele.
    Ex.: (5, 17*60) + 120 min → (4, 9*60) (19h passou do expediente: vai para as 9h do dia seguinte).
    """
    # O mesmo dia, com os minutos somados
    novo_dia, novos_minutos = dias_uteis, minutos + minutos_a_mais
    # Enquanto passar do fim do expediente, o que sobra vai para o começo do dia útil seguinte
    while novos_minutos > FIM_DO_EXPEDIENTE:
        # O dia 1 é o último antes da carga: o momento fica no fim do expediente dele
        if novo_dia <= 1:
            return 1, FIM_DO_EXPEDIENTE
        # O dia útil seguinte (um a menos antes da carga), começando pelo que sobrou
        novo_dia = novo_dia - 1
        novos_minutos = INICIO_DO_EXPEDIENTE + (novos_minutos - FIM_DO_EXPEDIENTE)
    return novo_dia, novos_minutos


def _data_no_arquivo(dias_uteis: int) -> date:
    """A data de um envio como os arquivos a enxergam: `dias_uteis` dias úteis antes da referência do gerador."""
    return dia_util_antes(catalogos.REFERENCIA_DO_GERADOR, dias_uteis)


def _data_sorteada(sorteio: random.Random, inicio: date, fim: date) -> date:
    """Um dia sorteado entre `inicio` e `fim` (os dois contam). Com o fim antes do início, devolve o início."""
    # Quantos dias cabem entre os dois
    dias_no_intervalo = (fim - inicio).days
    # Intervalo vazio (ou invertido): fica o início
    if dias_no_intervalo <= 0:
        return inicio
    # Um dia qualquer do intervalo
    return inicio + timedelta(days=sorteio.randint(0, dias_no_intervalo))


# ================================ Salários ================================

def faixas_publicas() -> dict[str, tuple[Decimal, Decimal]]:
    """{código CBO: (mínimo, máximo)} da faixa pública de cada profissão que tem dados (data/cbo)."""
    faixas = {}
    # O arquivo das faixas calculadas da RAIS (o mesmo que o banco carrega)
    with open(ARQUIVO_DAS_FAIXAS, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            # Profissão sem dados na RAIS (SEM_DADOS) fica de fora: não tem faixa
            if linha["minimo"] and linha["maximo"]:
                faixas[linha["codigo_cbo"]] = (Decimal(linha["minimo"]), Decimal(linha["maximo"]))
    return faixas


def degraus_de_salario(cargo: str, publicas: dict, de_referencia: dict) -> list[Decimal]:
    """Os degraus de salário de um cargo: 4 valores dentro da faixa pública da CBO dele.

    Recebe: o cargo (catalogos.PROFISSOES); as faixas públicas (faixas_publicas); as faixas de referência por cargo do
    Validador (validador.faixas_de_referencia), que valem quando a empresa tem poucos colegas no cargo.
    Devolve: os degraus, do menor para o maior, arredondados para a dezena de reais.
    Ex.: "Assistente administrativo" (faixa de R$ 2.040 a R$ 5.440 depois de cruzar as duas) → [2650, 2920, 3200, 3470].
    """
    profissao = catalogos.PROFISSOES[cargo]
    # O sócio recebe pró-labore: degraus próprios, dentro da referência do cargo
    if profissao["tipo_renda"] == "PRO_LABORE":
        return list(DEGRAUS_DO_PRO_LABORE)
    # A faixa pública da profissão (o código CBO do cargo)
    minimo, maximo = publicas[profissao["cbo"]]
    # Cargo com faixa de referência no Validador: os degraus ficam dentro das duas faixas
    referencia = de_referencia.get((cargo, "CLT"))
    if referencia is not None:
        minimo = max(minimo, referencia["faixa_minima"])
        maximo = min(maximo, referencia["faixa_maxima"])
    # A largura da faixa, para achar os pontos de 18%, 26%, 34% e 42% dela
    largura = maximo - minimo
    degraus = []
    for posicao in POSICOES_DOS_DEGRAUS:
        # O ponto da faixa, arredondado para a dezena de reais (ex.: 2.923,47 → 2.920,00)
        valor = ((minimo + largura * posicao) / 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 10
        # Nunca abaixo do piso
        degraus.append(max(valor, PISO_SALARIAL).quantize(Decimal("0.01")))
    return degraus


# ================================ Documentos e contatos ================================

def cnpj_com_a_mesma_raiz(cnpj_da_sede: str, numero_do_estabelecimento: int) -> str:
    """O CNPJ de uma filial: a mesma raiz (os 8 primeiros dígitos) da sede e outro número de estabelecimento.

    Os 2 dígitos verificadores são achados tentando os 100 possíveis e ficando com o que a conta aceita.
    Ex.: ("10433218000193", 2) → "1043321800020x" (com o verificador certo).
    """
    # A raiz da sede e o número do estabelecimento (ex.: 0002)
    doze_primeiros = cnpj_da_sede[:8] + f"{numero_do_estabelecimento:04d}"
    # Tenta os verificadores de 00 a 99: só um passa na conta
    for verificadores in range(100):
        candidato = doze_primeiros + f"{verificadores:02d}"
        if cnpj_valido(candidato):
            return candidato
    raise ValueError("Não achei o verificador do CNPJ da filial.")


def _cpf_novo(sorteio: random.Random, cpfs_usados: set) -> str:
    """Um CPF sintético válido que ainda não foi usado na base viva (11 dígitos, sem pontuação)."""
    while True:
        # Um CPF sorteado com o dígito verificador certo (services/documentos.py)
        cpf = gerar_cpf(sorteio)
        # CPF repetido entre pessoas diferentes: sorteia outro
        if cpf not in cpfs_usados:
            cpfs_usados.add(cpf)
            return cpf


def _sem_acento(texto: str) -> str:
    """O texto sem acentos, em minúsculas e sem espaços: para montar e-mails. Ex.: "Júlio César" → "juliocesar"."""
    # Separa as letras dos acentos e joga os acentos fora
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    # Sem espaços nem hífens (o e-mail não tem)
    return sem_acento.replace(" ", "").replace("-", "")


def _telefone(sorteio: random.Random, ddd: str, celular: bool) -> str:
    """Um telefone sintético: celular "(92) 99123-4567" ou fixo "(92) 3234-5678"."""
    # O celular começa com 9 e tem 9 dígitos
    if celular:
        return f"({ddd}) 9{sorteio.randint(8100, 9999)}-{sorteio.randint(0, 9999):04d}"
    # O fixo começa com 3 e tem 8 dígitos
    return f"({ddd}) 3{sorteio.randint(100, 999)}-{sorteio.randint(0, 9999):04d}"


def _cep(sorteio: random.Random, prefixo: str) -> str:
    """Um CEP de 8 dígitos que começa com o prefixo do município (ex.: "690" → "69012345")."""
    return prefixo + f"{sorteio.randint(0, 99999):05d}"


# ================================ A empresa ================================

def _cadastro_da_empresa(empresa: dict, sorteio: random.Random) -> dict:
    """O cadastro da empresa (o que o especialista do banco preenche) e o que o gerador precisa dela.

    Recebe: a empresa do catálogo e o sorteio dela. Devolve: {cnpj, cnpjs_extras, login, dominio_email, agencias,
    unidades: [{codigo, nome, cnpj, endereco}]}. As filiais usam a raiz da sede; a empresa do grupo, outra raiz.
    """
    # O CNPJ da sede, sorteado com o verificador certo
    cnpj_da_sede = gerar_cnpj(sorteio)
    cnpjs_extras = []
    # As filiais: a mesma raiz, estabelecimentos 0002, 0003...
    for numero in range(2, 2 + empresa["filiais"]):
        cnpjs_extras.append({"cnpj": cnpj_com_a_mesma_raiz(cnpj_da_sede, numero), "tipo": "FILIAL"})
    # A empresa do grupo (só quando o catálogo diz): outra raiz
    if empresa.get("empresa_do_grupo"):
        cnpjs_extras.append({"cnpj": gerar_cnpj(sorteio), "tipo": "GRUPO"})
    # Cada unidade de trabalho tem o seu CNPJ (a sede, as filiais e, na última, o grupo) e o seu endereço
    cnpjs_das_unidades = [cnpj_da_sede]
    for extra in cnpjs_extras:
        cnpjs_das_unidades.append(extra["cnpj"])
    unidades = []
    for posicao, (codigo, nome) in enumerate(empresa["unidades"]):
        # A unidade usa o CNPJ da mesma posição; quando há mais unidades que CNPJs, fica com a sede
        cnpj_da_unidade = cnpj_da_sede
        if posicao < len(cnpjs_das_unidades):
            cnpj_da_unidade = cnpjs_das_unidades[posicao]
        # O endereço da unidade, no município da empresa (a região é a do cadastro)
        endereco = {"cep": _cep(sorteio, empresa["prefixo_do_cep"]), "logradouro": sorteio.choice(catalogos.RUAS),
                    "numero": str(sorteio.randint(10, 3500)), "bairro": sorteio.choice(empresa["bairros"])}
        unidades.append({"codigo": codigo, "nome": nome, "cnpj": cnpj_da_unidade, "endereco": endereco})
    # As agências do banco perto da empresa (4 dígitos cada)
    agencias = [f"{sorteio.randint(1000, 9999)}", f"{sorteio.randint(1000, 9999)}"]
    # O login do RH ("rh." e a chave sem "_") e o domínio reservado (a chave com "-" e ".example")
    return {"cnpj": cnpj_da_sede, "cnpjs_extras": cnpjs_extras, "login": "rh." + empresa["chave"].replace("_", ""),
            "dominio_email": empresa["chave"].replace("_", "-") + ".example", "agencias": agencias,
            "unidades": unidades}


# ================================ As pessoas ================================

def _nome_sem_repetir(sorteio: random.Random, sexo: str, nomes_usados: set) -> str:
    """Um nome completo sorteado (nome e 1 ou 2 sobrenomes) que ainda não existe na empresa."""
    # A lista dos nomes do sexo da pessoa
    lista = catalogos.NOMES_FEMININOS if sexo == "F" else catalogos.NOMES_MASCULINOS
    while True:
        # O nome e um sobrenome
        partes = [sorteio.choice(lista), sorteio.choice(catalogos.SOBRENOMES)]
        # Metade das pessoas tem dois sobrenomes
        if sorteio.random() < 0.5:
            partes.append(sorteio.choice(catalogos.SOBRENOMES))
        nome = " ".join(partes)
        # Nome que já existe na empresa: sorteia de novo
        if nome not in nomes_usados:
            nomes_usados.add(nome)
            return nome


def _estado_civil(sorteio: random.Random, idade: int, sexo: str) -> str:
    """O estado civil sorteado conforme a idade (quem é jovem é mais solteiro), escrito no feminino para as mulheres.

    Ex.: 23 anos e "F" → quase sempre "Solteira"; 45 anos e "M" → mais "Casado" e "Divorciado". A padronização aceita
    a forma feminina (services/normalizador.converter_dominio: "Casada" vira "Casado").
    """
    # Os pesos de cada estado civil, pela faixa de idade
    if idade < 25:
        pesos = {"Solteiro": 80, "União estável": 15, "Casado": 5}
    elif idade < 40:
        pesos = {"Solteiro": 35, "Casado": 40, "União estável": 20, "Divorciado": 5}
    else:
        pesos = {"Casado": 50, "Solteiro": 15, "Divorciado": 20, "União estável": 10, "Viúvo": 5}
    # Um estado civil sorteado pelos pesos
    estado = sorteio.choices(list(pesos.keys()), weights=list(pesos.values()))[0]
    # No feminino: "Solteiro" → "Solteira", "Casado" → "Casada"... ("União estável" fica igual)
    if sexo == "F" and estado.endswith("o"):
        return estado[:-1] + "a"
    return estado


def _escolaridade(sorteio: random.Random, cargo: str) -> str:
    """A escolaridade sorteada conforme o nível do cargo (superior, técnico ou operacional)."""
    # Cargo de nível superior (ex.: "Analista", "Enfermeiro"): superior completo ou pós-graduação
    for palavra in PALAVRAS_DE_NIVEL_SUPERIOR:
        if palavra in cargo:
            return sorteio.choice(["Superior completo", "Superior completo", "Pós-graduação"])
    # Cargo técnico (ex.: "Técnico", "Supervisor"): médio completo para cima
    for palavra in PALAVRAS_DE_NIVEL_TECNICO:
        if palavra in cargo:
            return sorteio.choice(["Médio completo", "Médio completo", "Superior incompleto", "Superior completo"])
    # Os outros cargos: do fundamental ao médio completo
    return sorteio.choice(["Fundamental completo", "Médio incompleto", "Médio completo", "Médio completo"])


def _cargo_sorteado(sorteio: random.Random, setor: str) -> str:
    """Um cargo do setor, sorteado pelos pesos do catálogo (ex.: mais costureiras que gerentes na confecção)."""
    # Os cargos do setor e os pesos deles, em duas listas (o sorteio pede assim)
    cargos, pesos = [], []
    for cargo, peso in catalogos.CARGOS_POR_SETOR[setor]:
        cargos.append(cargo)
        pesos.append(peso)
    return sorteio.choices(cargos, weights=pesos)[0]


def _pessoa(sorteio: random.Random, contexto: dict, cargo: str, admissao: date, data_do_envio: date) -> dict:
    """Uma pessoa, com todos os campos do layout no formato padrão (datas AAAA-MM-DD, dinheiro 3450.00).

    Recebe: o sorteio; o contexto da empresa (catálogo, cadastro, CPFs e nomes já usados, degraus e a matrícula);
    o cargo; a data de admissão; a data do envio (como os arquivos a enxergam).
    Devolve: {campo do layout: valor}. Quem escreve no jeito do sistema de RH é _valor_no_arquivo.
    """
    empresa, cadastro = contexto["empresa"], contexto["cadastro"]
    # O sexo, sorteado meio a meio
    sexo = sorteio.choice(["F", "M"])
    # A idade na admissão: de 18 a 50 anos (mais gente jovem)
    idade_na_admissao = 18 + int(sorteio.triangular(0, 32, 6))
    # O nascimento: a idade na admissão antes dela, num dia qualquer do ano
    nascimento = admissao - timedelta(days=idade_na_admissao * 365 + sorteio.randint(0, 364))
    # A unidade de trabalho (a principal tem mais gente)
    unidade = sorteio.choices(cadastro["unidades"], weights=_pesos_das_unidades(cadastro["unidades"]))[0]
    profissao = catalogos.PROFISSOES[cargo]
    # O salário: um dos degraus da profissão (mais gente nos de baixo)
    salario = sorteio.choices(contexto["degraus"][cargo], weights=_pesos_dos_degraus(contexto["degraus"][cargo]))[0]
    nome = _nome_sem_repetir(sorteio, sexo, contexto["nomes_usados"])
    # O e-mail usa o primeiro nome e o último sobrenome, sem acento
    partes_do_nome = nome.split(" ")
    usuario_do_email = _sem_acento(partes_do_nome[0]) + "." + _sem_acento(partes_do_nome[-1])
    # A matrícula: a próxima da empresa
    contexto["matricula"] = contexto["matricula"] + 1
    # Os campos do layout, um a um (os opcionais que o estilo do arquivo não traz ficam de fora na hora de escrever)
    pessoa = {
        "matricula": f"{contexto['matricula']:06d}",
        "nome_completo": nome,
        "cpf": _cpf_novo(sorteio, contexto["cpfs_usados"]),
        "data_nascimento": nascimento.isoformat(),
        "sexo": sexo,
        # A idade no dia do envio decide o estado civil
        "estado_civil": _estado_civil(sorteio, (data_do_envio - nascimento).days // 365, sexo),
        # A mãe tem o último sobrenome da pessoa
        "nome_mae": sorteio.choice(catalogos.NOMES_FEMININOS) + " " + sorteio.choice(catalogos.SOBRENOMES) + " "
                    + nome.split(" ")[-1],
        "nacionalidade": "Brasileira",
        "municipio_naturalidade": empresa["municipio"],
        "uf_naturalidade": empresa["uf"],
        # O NIS (PIS) começa com 1 e tem 11 dígitos
        "nis_pis": "1" + f"{sorteio.randint(0, 9999999999):010d}",
        "escolaridade": _escolaridade(sorteio, cargo),
        "numero_documento": str(sorteio.randint(1000000, 99999999)),
        "orgao_emissor": "SSP",
        "uf_emissor": empresa["uf"],
        # O endereço de casa, no município da empresa
        "cep_residencial": _cep(sorteio, empresa["prefixo_do_cep"]),
        "logradouro_residencial": sorteio.choice(catalogos.RUAS),
        "numero_residencial": str(sorteio.randint(1, 2800)),
        # Três em cada dez endereços têm complemento
        "complemento_residencial": sorteio.choice(catalogos.COMPLEMENTOS) if sorteio.random() < 0.3 else "",
        "bairro_residencial": sorteio.choice(empresa["bairros"]),
        "municipio_residencial": empresa["municipio"],
        "uf_residencial": empresa["uf"],
        # Duas em cada dez pessoas têm telefone fixo; todas têm celular
        "telefone_residencial": _telefone(sorteio, empresa["ddd"], False) if sorteio.random() < 0.2 else "",
        "telefone_celular": _telefone(sorteio, empresa["ddd"], True),
        # O e-mail pessoal num provedor ".example" e o corporativo no domínio da empresa
        "email_pessoal": usuario_do_email + str(sorteio.randint(1, 99)) + "@" + sorteio.choice(
            catalogos.PROVEDORES_DE_EMAIL),
        "email_corporativo": usuario_do_email + "@" + cadastro["dominio_email"],
        # O vínculo com a empresa: o CNPJ e a unidade de trabalho
        "cnpj_empregador": unidade["cnpj"],
        "cnpj_grupo": "",
        "codigo_unidade": unidade["codigo"],
        "nome_unidade": unidade["nome"],
        # O cargo e o código da profissão (CBO), sempre o mesmo para o mesmo cargo
        "cargo": cargo,
        "codigo_cbo": profissao["cbo"],
        "data_admissao": admissao.isoformat(),
        "data_efetivacao": _efetivacao(admissao, data_do_envio),
        # A renda: o tipo (CLT ou pró-labore), o valor e o mês de referência (o do envio)
        "tipo_renda": profissao["tipo_renda"],
        "valor_renda": str(salario),
        "data_referencia_renda": data_do_envio.replace(day=1).isoformat(),
        # O endereço do trabalho: o da unidade
        "cep_comercial": unidade["endereco"]["cep"],
        "logradouro_comercial": unidade["endereco"]["logradouro"],
        "numero_comercial": unidade["endereco"]["numero"],
        "complemento_comercial": "",
        "bairro_comercial": unidade["endereco"]["bairro"],
        "municipio_comercial": empresa["municipio"],
        "uf_comercial": empresa["uf"],
    }
    return pessoa


def _pesos_das_unidades(unidades: list[dict]) -> list[int]:
    """O peso de cada unidade no sorteio: a primeira (a principal) tem mais gente. Ex.: 3 unidades → [6, 2, 2]."""
    pesos = []
    for posicao in range(len(unidades)):
        # A primeira pesa 6; as outras, 2
        pesos.append(6 if posicao == 0 else 2)
    return pesos


def _pesos_dos_degraus(degraus: list) -> list[int]:
    """O peso de cada degrau de salário: PESOS_DOS_DEGRAUS, ou pesos iguais nos 3 degraus do pró-labore."""
    # Os 4 degraus do empregado: mais gente nos de baixo
    if len(degraus) == len(PESOS_DOS_DEGRAUS):
        return list(PESOS_DOS_DEGRAUS)
    # Os degraus do pró-labore: todos com o mesmo peso
    return [1] * len(degraus)


def _efetivacao(admissao: date, data_do_envio: date) -> str:
    """A efetivação 90 dias depois da admissão (o fim do contrato de experiência), ou vazia se ainda não chegou."""
    efetivacao = admissao + timedelta(days=90)
    # Ainda no contrato de experiência no dia do envio: sem efetivação
    if efetivacao > data_do_envio:
        return ""
    return efetivacao.isoformat()


def _admissao_na_carga_inicial(sorteio: random.Random, data_do_envio: date) -> date:
    """A admissão de quem já trabalhava na empresa: de alguns meses a 20 anos antes (mais gente recente)."""
    # Quantos anos antes do envio (a maioria entrou nos últimos 4 anos; ninguém antes de 20)
    anos_antes = min(20.0, sorteio.expovariate(1 / 4))
    return data_do_envio - timedelta(days=30 + int(anos_antes * 365))


def _socios(sorteio: random.Random, contexto: dict, data_do_envio: date, pro_labore_alto: bool) -> list[dict]:
    """Os sócios da empresa (1 ou 2), que recebem pró-labore. Com pro_labore_alto, o primeiro recebe acima da
    referência do cargo (é o alerta RENDA_FORA_DO_CARGO que a empresa confirmou)."""
    socios = []
    # Um ou dois sócios, sorteado
    for _vez in range(sorteio.choice([1, 2])):
        # O sócio está na empresa há 3 a 15 anos
        admissao = data_do_envio - timedelta(days=sorteio.randint(3 * 365, 15 * 365))
        socio = _pessoa(sorteio, contexto, "Sócio-administrador", admissao, data_do_envio)
        # O sócio não passa pelo contrato de experiência: não tem data de efetivação
        socio["data_efetivacao"] = ""
        socios.append(socio)
    # O pró-labore acima da referência do cargo (a empresa confirma o alerta antes de enviar)
    if pro_labore_alto:
        socios[0]["valor_renda"] = str(PRO_LABORE_ALTO)
    return socios


# ================================ Os erros de digitação ================================

def _cbo_que_nao_existe(codigo_certo: str) -> str:
    """Um código de 6 dígitos parecido com o certo que NÃO está na tabela da CBO (o erro de digitação do CBO)."""
    # A mesma família (os 4 primeiros dígitos), com os 2 últimos trocados, do 99 para baixo
    for final in range(99, 9, -1):
        candidato = codigo_certo[:4] + f"{final:02d}"
        if not tabela_cbo.existe(candidato):
            return candidato
    raise ValueError("Não achei um código CBO inexistente parecido com " + codigo_certo)


def _cpf_com_digito_errado(cpf_certo: str) -> str:
    """O CPF com o último dígito trocado, que a conta do verificador recusa (o erro de digitação do CPF)."""
    # Soma 1, 2, 3... ao último dígito até a conta do verificador recusar
    for troca in range(1, 10):
        candidato = cpf_certo[:10] + str((int(cpf_certo[10]) + troca) % 10)
        if not cpf_valido(candidato):
            return candidato
    raise ValueError("Não achei um CPF inválido parecido.")


def _plantar_erro(tipo: str, pessoa: dict) -> dict:
    """Troca o valor certo de um obrigatório pelo erro de digitação e devolve a correção que a empresa faria.

    Recebe: o tipo do erro (MOTIVOS_DAS_CORRECOES) e a pessoa (mudada aqui). Devolve: {campo, valor certo} no jeito
    que a empresa digita no portal (datas DD/MM/AAAA, dinheiro com vírgula). Ex.: "admissao_vazia" → a admissão fica
    vazia e a correção é {"campo": "data_admissao", "valor": "03/02/2020"}.
    """
    # O CPF com o último dígito errado; a correção é o CPF certo
    if tipo == "cpf_digitado_errado":
        certo = pessoa["cpf"]
        pessoa["cpf"] = _cpf_com_digito_errado(certo)
        return {"campo": "cpf", "valor": certo}
    # A admissão que faltou; a correção é a data certa, como se digita no portal
    if tipo == "admissao_vazia":
        certo = date.fromisoformat(pessoa["data_admissao"]).strftime("%d/%m/%Y")
        pessoa["data_admissao"] = ""
        return {"campo": "data_admissao", "valor": certo}
    # O CBO que não existe (ou que faltou); a correção é o código certo, com o traço
    if tipo in ("cbo_desconhecido", "cbo_vazio"):
        certo = pessoa["codigo_cbo"]
        pessoa["codigo_cbo"] = _cbo_que_nao_existe(certo) if tipo == "cbo_desconhecido" else ""
        return {"campo": "codigo_cbo", "valor": certo[:4] + "-" + certo[4:]}
    # O salário que faltou (ou com um zero a mais); a correção é o valor certo, com vírgula
    if tipo in ("salario_vazio", "salario_dez_vezes"):
        certo = Decimal(pessoa["valor_renda"])
        pessoa["valor_renda"] = "" if tipo == "salario_vazio" else str(certo * 10)
        return {"campo": "valor_renda", "valor": str(certo).replace(".", ",")}
    raise ValueError("Tipo de erro desconhecido: " + tipo)


# ================================ O arquivo de cada envio ================================

def _valor_no_arquivo(campo: str, valor: str, estilo: dict) -> str:
    """O valor do jeito que o sistema de RH escreve: data, dinheiro, CBO, sexo, vínculo, CPF e CNPJ.

    Ex.: ("data_admissao", "2020-02-03", estilo dd/mm/aaaa) → "03/02/2020"; ("codigo_cbo", "411010", com traço) →
    "4110-10"; ("valor_renda", "3450.00", brasileiro com milhar) → "3.450,00". Valor vazio continua vazio.
    """
    # Vazio continua vazio (o erro de digitação "faltou")
    if valor == "":
        return ""
    # Cada tipo de valor no jeito do estilo
    if campo.startswith("data_"):
        return _data_no_estilo(valor, estilo["data"])
    if campo == "valor_renda":
        return _dinheiro_no_estilo(Decimal(valor), estilo["dinheiro"])
    if campo == "codigo_cbo":
        return _cbo_no_estilo(valor, estilo["cbo"])
    if campo == "sexo" and estilo["sexo"] == "por_extenso":
        return "Feminino" if valor == "F" else "Masculino"
    if campo == "tipo_renda":
        return _vinculo_no_estilo(valor, estilo["vinculo"])
    if campo in ("cpf", "cnpj_empregador", "cnpj_grupo"):
        return _documento_no_estilo(campo, valor, estilo)
    # Os outros campos vão como estão
    return valor


def _data_no_estilo(valor: str, jeito: str) -> str:
    """A data AAAA-MM-DD no jeito do estilo (DD/MM/AAAA ou AAAA-MM-DD)."""
    # O jeito brasileiro: dia, mês e ano com barras
    if jeito == "dd/mm/aaaa":
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    return valor


def _dinheiro_no_estilo(valor: Decimal, jeito: str) -> str:
    """O dinheiro no jeito do estilo. Ex.: 3450.00 → "3.450,00", "3450,00" ou "3450.00"."""
    # Sempre com duas casas, com ponto (ex.: "3450.00")
    texto_com_ponto = f"{valor:.2f}"
    if jeito == "ponto_decimal":
        return texto_com_ponto
    # A parte inteira e os centavos, separados
    inteiro, centavos = texto_com_ponto.split(".")
    if jeito == "virgula_decimal":
        return inteiro + "," + centavos
    # Com o ponto de milhar: "1234567" → "1.234.567"
    com_milhar = f"{int(inteiro):,}".replace(",", ".")
    return com_milhar + "," + centavos


def _cbo_no_estilo(codigo: str, jeito: str) -> str:
    """O código CBO de 6 dígitos num dos 4 jeitos. Ex.: "411010" → "4110-10", "411010", "4110.10" ou "4110 10"."""
    # Um código já errado (o erro plantado) é escrito do mesmo jeito que os certos
    if jeito == "com_traco":
        return codigo[:4] + "-" + codigo[4:]
    if jeito == "com_ponto":
        return codigo[:4] + "." + codigo[4:]
    if jeito == "com_espaco":
        return codigo[:4] + " " + codigo[4:]
    # Só os dígitos
    return codigo


def _vinculo_no_estilo(valor: str, jeito: str) -> str:
    """O tipo de renda como o sistema escreve: "CLT"/"PRO_LABORE" ou "Celetista"/"Pró-labore"."""
    # Por extenso: "Celetista" ou "Pró-labore" (a padronização converte os dois)
    if jeito == "por_extenso":
        return "Celetista" if valor == "CLT" else "Pró-labore"
    return valor


def _documento_no_estilo(campo: str, valor: str, estilo: dict) -> str:
    """CPF e CNPJ com pontuação nos estilos de CSV com ponto e vírgula e no Excel; só os dígitos nos outros.

    Ex.: "52998224725" → "529.982.247-25"; "10433218000193" → "10.433.218/0001-93".
    """
    # Os estilos de exportação com vírgula ou do eSocial mandam só os dígitos
    if estilo["separador"] == "," or estilo["codificacao"] == "cp1252":
        return valor
    # O CPF com pontos e traço
    if campo == "cpf":
        return f"{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}"
    # O CNPJ com pontos, barra e traço
    return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"


def _linha_no_arquivo(pessoa: dict, estilo: dict) -> list[str]:
    """Os valores de uma pessoa na ordem das colunas do estilo (nome em maiúsculas nos sistemas antigos)."""
    valores = []
    for _cabecalho, campo in estilo["colunas"]:
        # O valor do campo no jeito do estilo (campo que a pessoa não tem sai vazio)
        valor = _valor_no_arquivo(campo, pessoa.get(campo, ""), estilo)
        # Os sistemas de siglas e do eSocial escrevem o nome em maiúsculas
        if campo == "nome_completo" and (estilo["separador"] == "," or estilo["codificacao"] == "cp1252"):
            valor = valor.upper()
        valores.append(valor)
    return valores


def conteudo_do_arquivo(linhas: list[dict], estilo: dict) -> bytes:
    """Os bytes do arquivo de um envio: o cabeçalho do estilo e uma linha por pessoa (CSV ou Excel).

    No Excel, toda célula é texto (como a planilha que o RH digita): o CPF e a matrícula não perdem os zeros.
    """
    # O cabeçalho: o nome de cada coluna no estilo
    cabecalhos = []
    for cabecalho, _campo in estilo["colunas"]:
        cabecalhos.append(cabecalho)
    # A planilha do Excel tem o seu próprio jeito de gravar
    if estilo["formato"] == "xlsx":
        return _conteudo_do_excel(cabecalhos, linhas, estilo)
    # O CSV: o separador do estilo e a quebra de linha do Windows
    texto = io.StringIO()
    escritor = csv.writer(texto, delimiter=estilo["separador"], lineterminator="\r\n")
    escritor.writerow(cabecalhos)
    for pessoa in linhas:
        escritor.writerow(_linha_no_arquivo(pessoa, estilo))
    # O texto na codificação do estilo (ex.: a do Windows, no eSocial)
    return texto.getvalue().encode(estilo["codificacao"])


def _conteudo_do_excel(cabecalhos: list[str], linhas: list[dict], estilo: dict) -> bytes:
    """Os bytes de uma planilha do Excel (.xlsx) com o cabeçalho e as pessoas, tudo como texto."""
    # Uma planilha nova, com uma aba só
    planilha = Workbook()
    aba = planilha.active
    aba.title = "Funcionarios"
    # O cabeçalho e uma linha por pessoa (os valores são textos: nenhum vira número)
    aba.append(cabecalhos)
    for pessoa in linhas:
        aba.append(_linha_no_arquivo(pessoa, estilo))
    # Grava na memória e devolve os bytes
    saida = io.BytesIO()
    planilha.save(saida)
    return saida.getvalue()


# O nome de cada arquivo, pelo estilo: o da carga inicial e o das inclusões (com o número do envio)
NOMES_DOS_ARQUIVOS = {
    "classico": ("cadastro_funcionarios.csv", "admitidos_lote_{numero}.csv"),
    "siglas": ("EXPORT_FUNC_COMPLETO.csv", "EXPORT_FUNC_ADMITIDOS_{numero:02d}.csv"),
    "planilha": ("funcionarios_carga_inicial.xlsx", "novos_colaboradores_{numero}.xlsx"),
    "esocial": ("esocial_trabalhadores.csv", "esocial_admissoes_{numero}.csv"),
    "enxuta": ("lista_funcionarios.csv", "lista_novos_{numero}.csv"),
    "descritiva": ("arquivo_para_o_banco_completo.csv", "arquivo_para_o_banco_inclusao_{numero}.csv"),
}


def _nome_do_arquivo(estilo: str, tipo: str, numero: int) -> str:
    """O nome do arquivo do envio, sem acentos nem espaços. Ex.: ("classico", "INCLUSAO", 2) → admitidos_lote_2.csv."""
    inicial, inclusao = NOMES_DOS_ARQUIVOS[estilo]
    # A carga inicial tem nome fixo; a inclusão leva o número
    if tipo == "INICIAL":
        return inicial
    return inclusao.format(numero=numero)


def _decisoes_de_coluna(estilo: dict) -> dict:
    """As decisões de formato que a empresa deu às colunas de data DD/MM/AAAA ("DMY": o dia vem antes do mês)."""
    decisoes = {}
    # Datas AAAA-MM-DD não deixam dúvida: nada a decidir
    if estilo["data"] != "dd/mm/aaaa":
        return decisoes
    # Cada coluna de data: o dia vem antes do mês
    for cabecalho, campo in estilo["colunas"]:
        if campo.startswith("data_"):
            decisoes[cabecalho] = "DMY"
    return decisoes


def _colunas_do_roteiro(estilo: dict) -> list[list[str]]:
    """As colunas do estilo no formato do roteiro: [[cabeçalho, campo], ...] (o JSON guarda listas)."""
    colunas = []
    for cabecalho, campo in estilo["colunas"]:
        colunas.append([cabecalho, campo])
    return colunas


# ================================ A linha do tempo de cada envio ================================

def _linha_do_tempo(sorteio: random.Random, envio: dict, tem_correcoes: bool) -> dict:
    """Os momentos de um envio (dias úteis antes da carga e hora), do recebimento à decisão do banco.

    Recebe: o sorteio; o envio do catálogo (dias_uteis e destino); se a empresa corrigiu ou confirmou algo.
    Devolve: {recebido, aceite, correcoes?, enviado?, decisao?}: só as etapas que o destino já alcançou.
    O banco decide no mesmo dia ou em até 2 dias úteis; a devolução, no mesmo dia do envio.
    """
    dia = envio["dias_uteis"]
    # O arquivo chega de manhã (entre 8h10 e 11h50)
    recebido = (dia, sorteio.randint(8 * 60 + 10, 11 * 60 + 50))
    # A empresa confere as colunas de 8 a 40 minutos depois
    aceite = _depois(recebido[0], recebido[1], sorteio.randint(8, 40))
    momentos = {"recebido": _momento(*recebido), "aceite": _momento(*aceite)}
    ultimo = aceite
    # A empresa corrigiu ou confirmou algo antes de seguir (o pendente parou antes disso)
    if tem_correcoes and envio["destino"] != "PENDENTE":
        ultimo = _depois(ultimo[0], ultimo[1], sorteio.randint(30, 150))
        momentos["correcoes"] = _momento(*ultimo)
    # Só os que foram ao banco têm o envio e a decisão
    if envio["destino"] not in ("CADASTRADO", "EM_ANALISE", "DEVOLVIDO"):
        return momentos
    # O envio ao banco, de 20 a 90 minutos depois da última etapa
    enviado = _depois(ultimo[0], ultimo[1], sorteio.randint(20, 90))
    momentos["enviado"] = _momento(*enviado)
    # A devolução: no mesmo dia, 3 a 5 horas depois
    if envio["destino"] == "DEVOLVIDO":
        momentos["decisao"] = _momento(*_depois(enviado[0], enviado[1], sorteio.randint(180, 300)))
    # A aprovação: no mesmo dia ou em até 2 dias úteis
    if envio["destino"] == "CADASTRADO":
        momentos["decisao"] = _momento(*_decisao_do_banco(sorteio, enviado))
    return momentos


def _decisao_do_banco(sorteio: random.Random, enviado: tuple[int, int]) -> tuple[int, int]:
    """Quando o banco aprovou: no mesmo dia (horas depois) ou 1 a 2 dias úteis depois, em horário de expediente."""
    # Quantos dias úteis depois do envio (a maioria em até 1)
    dias_depois = sorteio.choices([0, 1, 2], weights=[35, 50, 15])[0]
    # No mesmo dia: de 1h30 a 5 horas depois
    if dias_depois == 0:
        return _depois(enviado[0], enviado[1], sorteio.randint(90, 300))
    # Nunca depois de ontem (dia 1)
    dia_da_decisao = max(1, enviado[0] - dias_depois)
    return dia_da_decisao, sorteio.randint(9 * 60, 17 * 60)


# ================================ As contas do banco ================================

def _contas_do_envio(sorteio: random.Random, contexto: dict, pessoas: list[dict], envio: dict,
                     decisao: dict) -> dict | None:
    """O arquivo de contas que o banco devolveu para as pessoas de um envio cadastrado (ou None, se ainda não veio).

    Recebe: o sorteio; o contexto da empresa; as pessoas cadastradas pelo envio; o envio do catálogo e o momento da
    decisão do banco. Devolve: {momento, nome_do_arquivo, pessoas: [{cpf, cnpj_empresa, agencia, conta, tipo,
    situacao, folha, data_abertura}]}. Na nova conta, a data de abertura fica vazia: a carga põe uma data entre a
    aprovação e a chegada do arquivo (a data real da carga só é conhecida lá).
    """
    contas = envio.get("contas")
    # O catálogo diz que o banco ainda não devolveu as contas deste envio
    if contas is None:
        return None
    # O dia em que o arquivo chegou: alguns dias úteis depois da aprovação
    dia_das_contas = decisao["dias_uteis"] - contas["dias_uteis_depois"]
    # O arquivo ainda não chegou (cairia hoje ou depois da carga): fica sem contas
    if dia_das_contas < 1:
        return None
    # A parte das pessoas que já tem conta, sorteada
    quantas = round(len(pessoas) * contas["parte"])
    escolhidas = sorteio.sample(pessoas, quantas)
    linhas = []
    for pessoa in escolhidas:
        linhas.append(_conta_de_uma_pessoa(sorteio, contexto, pessoa))
    # O nome do arquivo: a empresa e o número do arquivo dela
    contexto["arquivos_de_contas"] = contexto["arquivos_de_contas"] + 1
    nome = f"contas_abertas_{contexto['empresa']['chave']}_{contexto['arquivos_de_contas']}.csv"
    return {"momento": _momento(dia_das_contas, sorteio.randint(10 * 60, 16 * 60)), "nome_do_arquivo": nome,
            "pessoas": linhas}


def _conta_de_uma_pessoa(sorteio: random.Random, contexto: dict, pessoa: dict) -> dict:
    """A linha de uma pessoa no arquivo de contas: nova conta (tipo 1) ou correntista (tipo 2, ativo ou inativo)."""
    # O número da conta: 8 dígitos e um dígito verificador, sem repetir na base viva
    while True:
        conta = f"{sorteio.randint(10000000, 99999999)}-{sorteio.randint(0, 9)}"
        if conta not in contexto["contas_usadas"]:
            contexto["contas_usadas"].add(conta)
            break
    # O CNPJ é o do empregador da pessoa (a sede, a filial ou o grupo): todos são da empresa no cadastro
    linha = {"cpf": pessoa["cpf"], "cnpj_empresa": pessoa["cnpj_empregador"],
             "agencia": sorteio.choice(contexto["cadastro"]["agencias"]), "conta": conta}
    # Nova conta: sem situação, sem folha e com a data de abertura posta pela carga
    if sorteio.random() < PARTE_DE_NOVAS_CONTAS:
        linha.update({"tipo": "1", "situacao": "", "folha": "", "data_abertura": None})
        return linha
    # O correntista já tinha a conta: a data de abertura é a da conta antiga (de 1 a 15 anos antes)
    abertura = catalogos.REFERENCIA_DO_GERADOR - timedelta(days=sorteio.randint(365, 15 * 365))
    # Ativo ou inativo no banco, e se a folha dele já era identificada ("N" é o falso não folha)
    situacao = "ATIVO" if sorteio.random() < PARTE_DE_CORRENTISTAS_ATIVOS else "INATIVO"
    folha = "S" if sorteio.random() < PARTE_COM_A_FOLHA_JA_IDENTIFICADA else "N"
    linha.update({"tipo": "2", "situacao": situacao, "folha": folha, "data_abertura": abertura.strftime("%d/%m/%Y")})
    return linha


# ================================ Os acessos e as conversas ================================

def _acessos(sorteio: random.Random, empresa: dict, envios: list[dict], conversa: dict | None) -> list[dict]:
    """Os acessos do RH ao portal: um em cada etapa em que a empresa mexeu, um em cada mensagem e alguns avulsos.

    Devolve: [{dias_uteis, hora}], do mais antigo ao mais recente, sem repetir o mesmo momento.
    """
    # Um conjunto: o mesmo momento não entra duas vezes
    momentos = set()
    # Um acesso pouco antes de cada etapa em que a empresa mexeu (mandou, corrigiu, enviou ao banco)
    for envio in envios:
        for etapa in ("recebido", "correcoes", "enviado"):
            if etapa in envio["linha_do_tempo"]:
                momentos.add(_alguns_minutos_antes(envio["linha_do_tempo"][etapa], sorteio))
    # Um acesso pouco antes de cada mensagem que a empresa escreveu ao banco
    if conversa is not None:
        for mensagem in conversa["mensagens"]:
            if mensagem["de"] == "EMPRESA":
                momentos.add(_alguns_minutos_antes(mensagem, sorteio))
    # Os acessos avulsos: a empresa entra para acompanhar, entre o contrato e ontem
    for _vez in range(empresa["acessos_extras"]):
        dia = sorteio.randint(1, empresa["contrato_dias_uteis"])
        momentos.add((dia, sorteio.randint(8 * 60 + 30, 17 * 60 + 30)))
    # Do mais antigo ao mais recente
    ordenados = sorted(momentos, key=_ordem_do_momento)
    acessos = []
    for dia, minutos in ordenados:
        acessos.append(_momento(dia, minutos))
    return acessos


def _alguns_minutos_antes(momento: dict, sorteio: random.Random) -> tuple[int, int]:
    """(dias úteis, minutos) de 2 a 6 minutos antes de um momento do roteiro (a pessoa entrou e depois agiu)."""
    horas, minutos = momento["hora"].split(":")
    # Os minutos do momento, menos de 2 a 6 (nunca antes da meia-noite)
    return momento["dias_uteis"], max(0, int(horas) * 60 + int(minutos) - sorteio.randint(2, 6))


def _ordem_do_momento(momento: tuple[int, int]) -> tuple[int, int]:
    """A ordem cronológica de (dias úteis antes da carga, minutos): mais dias úteis antes vem primeiro."""
    return -momento[0], momento[1]


def _conversa_da_empresa(chave: str) -> dict | None:
    """A conversa da empresa com o banco (catalogos.CONVERSAS) no formato do roteiro, ou None se ela não escreveu."""
    for conversa in catalogos.CONVERSAS:
        # Só a conversa desta empresa
        if conversa["empresa"] != chave:
            continue
        # Cada mensagem vira um dicionário com nomes (o JSON do roteiro fica legível)
        mensagens = []
        for dias_uteis, hora, de, contexto, texto in conversa["mensagens"]:
            mensagens.append({"dias_uteis": dias_uteis, "hora": hora, "de": de, "contexto": contexto, "texto": texto})
        return {"resolvida": conversa["resolvida"], "mensagens": mensagens}
    return None


# ================================ Os envios de uma empresa ================================

def _pessoas_novas(sorteio: random.Random, contexto: dict, envio: dict, data_do_envio: date,
                   data_do_envio_anterior: date | None) -> list[dict]:
    """As pessoas que o envio traz pela primeira vez: todo mundo na carga inicial; os admitidos, nas inclusões."""
    pessoas = []
    quantidade = envio["pessoas"]
    # Na carga inicial entram os sócios (fora da conta das pessoas, que é dos empregados)
    if envio["tipo"] == "INICIAL":
        pessoas.extend(_socios(sorteio, contexto, data_do_envio, envio.get("pro_labore_alto", False)))
    for _vez in range(quantidade):
        # O cargo, pelos pesos do setor da empresa
        cargo = _cargo_sorteado(sorteio, contexto["empresa"]["cargos"])
        # Na carga inicial, quem já trabalhava na empresa (admissão de meses a anos antes)
        if envio["tipo"] == "INICIAL":
            admissao = _admissao_na_carga_inicial(sorteio, data_do_envio)
        else:
            # O admitido entrou entre o envio anterior e 2 dias antes deste
            admissao = _data_sorteada(sorteio, data_do_envio_anterior + timedelta(days=1),
                                      data_do_envio - timedelta(days=2))
        pessoas.append(_pessoa(sorteio, contexto, cargo, admissao, data_do_envio))
    return pessoas


def _montar_as_linhas(sorteio: random.Random, contexto: dict, envio: dict, novas: list[dict]) -> dict:
    """As linhas do arquivo: as pessoas novas, as já cadastradas que vieram de novo e os erros de digitação.

    Devolve: {linhas, cadastradas_pelo_envio, correcoes, exclusoes}. A linha 1 do arquivo é o cabeçalho: a pessoa da
    posição 0 está na linha 2 (a numeração que a empresa vê no Excel).
    """
    # Uma cópia de cada pessoa nova (o erro de digitação muda a cópia, e a pessoa certa fica guardada)
    linhas = []
    for pessoa in novas:
        linhas.append(dict(pessoa))
    # As já cadastradas que vieram de novo (ficam de fora do envio, com um aviso), em lugares sorteados
    repetidas = sorteio.sample(contexto["cadastradas"], min(envio.get("ja_cadastrados", 0), len(contexto["cadastradas"])))
    for pessoa in repetidas:
        linhas.insert(sorteio.randint(0, len(linhas)), dict(pessoa))
    # Os erros de digitação caem só em empregados novos (nunca no sócio nem em quem veio de novo)
    candidatas = []
    cpfs_repetidos = set()
    for pessoa in repetidas:
        cpfs_repetidos.add(pessoa["cpf"])
    for posicao, pessoa in enumerate(linhas):
        if pessoa["cpf"] not in cpfs_repetidos and pessoa["tipo_renda"] == "CLT":
            candidatas.append(posicao)
    correcoes, exclusoes = [], []
    erros = list(envio.get("erros", []))
    # A pessoa repetida no arquivo: uma cópia logo depois da original (a segunda linha é a que sai)
    if "pessoa_repetida" in erros:
        erros.remove("pessoa_repetida")
        posicao_da_original = sorteio.choice(candidatas)
        linhas.insert(posicao_da_original + 1, dict(linhas[posicao_da_original]))
        # A cópia está uma posição abaixo da original; a linha do arquivo é a posição mais 2 (o cabeçalho é a 1)
        exclusoes.append({"linha": posicao_da_original + 3, "motivo": "Pessoa repetida no arquivo; ficou a primeira linha."})
        candidatas = _posicoes_depois_da_insercao(candidatas, posicao_da_original)
    # Cada erro numa pessoa diferente, sorteada entre as candidatas
    for tipo, posicao in zip(erros, sorteio.sample(candidatas, len(erros))):
        correcao = _plantar_erro(tipo, linhas[posicao])
        # A linha do arquivo (a posição mais 2) e o motivo que a empresa escreve na correção
        correcao.update({"linha": posicao + 2, "motivo": MOTIVOS_DAS_CORRECOES[tipo]})
        correcoes.append(correcao)
    # As pessoas que este envio cadastra (se chegar ao cadastro): as novas, sem as que vieram de novo e sem a cópia
    cadastradas = list(novas)
    return {"linhas": linhas, "cadastradas_pelo_envio": cadastradas, "correcoes": correcoes, "exclusoes": exclusoes}


def _posicoes_depois_da_insercao(posicoes: list[int], posicao_da_original: int) -> list[int]:
    """As posições candidatas depois de uma linha entrar logo após `posicao_da_original` (as de baixo andam uma)."""
    novas = []
    for posicao in posicoes:
        # A original e a cópia não recebem outro erro
        if posicao == posicao_da_original:
            continue
        # As de baixo da original descem uma posição (a cópia entrou no meio)
        novas.append(posicao + 1 if posicao > posicao_da_original else posicao)
    return novas


def _envios_da_empresa(sorteio: random.Random, contexto: dict, pasta_da_empresa: Path, limite: int | None) -> list:
    """Gera os arquivos e o roteiro de cada envio da empresa, na ordem em que aconteceram.

    Recebe: o sorteio e o contexto da empresa; a pasta onde gravar os arquivos; limite — no máximo esse número de
    pessoas novas por envio (só nos testes; None = as do catálogo).
    Devolve: a lista dos envios no formato do roteiro.
    """
    empresa = contexto["empresa"]
    # O estilo do sistema de RH da empresa (o mesmo em todos os envios dela)
    estilo = catalogos.ESTILOS_DE_ARQUIVO[empresa["estilo"]]
    envios, data_anterior, numero_da_inclusao = [], None, 1
    for envio_do_catalogo in empresa["envios"]:
        # Uma cópia do envio do catálogo (o limite dos testes não muda o catálogo)
        envio = dict(envio_do_catalogo)
        if limite is not None:
            envio["pessoas"] = min(envio["pessoas"], limite)
        # A data do envio como os arquivos a enxergam, as pessoas e as linhas do arquivo
        data_do_envio = _data_no_arquivo(envio["dias_uteis"])
        novas = _pessoas_novas(sorteio, contexto, envio, data_do_envio, data_anterior)
        montagem = _montar_as_linhas(sorteio, contexto, envio, novas)
        # As inclusões são numeradas a partir de 2 (a carga inicial é o envio 1)
        if envio["tipo"] == "INCLUSAO":
            numero_da_inclusao = numero_da_inclusao + 1
        # Grava o arquivo do envio na pasta da empresa
        nome_do_arquivo = _nome_do_arquivo(empresa["estilo"], envio["tipo"], numero_da_inclusao)
        (pasta_da_empresa / nome_do_arquivo).write_bytes(conteudo_do_arquivo(montagem["linhas"], estilo))
        # A empresa corrigiu ou confirmou algo antes de enviar (erros, repetida ou pró-labore alto)
        tem_correcoes = bool(montagem["correcoes"] or montagem["exclusoes"] or envio.get("pro_labore_alto"))
        linha_do_tempo = _linha_do_tempo(sorteio, envio, tem_correcoes)
        # O envio no roteiro: o arquivo, a etapa, as colunas, as datas, as correções e o motivo da devolução
        roteiro_do_envio = {
            "arquivo": f"{NOME_DA_PASTA_DOS_ARQUIVOS}/{empresa['chave']}/{nome_do_arquivo}",
            "nome_do_arquivo": nome_do_arquivo, "tipo": envio["tipo"], "destino": envio["destino"],
            "linhas": len(montagem["linhas"]), "pessoas_novas": len(novas),
            "colunas": _colunas_do_roteiro(estilo), "decisoes_de_coluna": _decisoes_de_coluna(estilo),
            "linha_do_tempo": linha_do_tempo, "correcoes": montagem["correcoes"], "exclusoes": montagem["exclusoes"],
            "motivo_da_devolucao": catalogos.MOTIVO_DA_DEVOLUCAO if envio["destino"] == "DEVOLVIDO" else None,
            "contas": None,
        }
        if envio["destino"] == "CADASTRADO":
            # As pessoas cadastradas entram na lista da empresa (as próximas inclusões podem repetir alguém)
            contexto["cadastradas"].extend(montagem["cadastradas_pelo_envio"])
            # O arquivo de contas que o banco devolveu para elas (se já chegou)
            roteiro_do_envio["contas"] = _contas_do_envio(sorteio, contexto, montagem["cadastradas_pelo_envio"],
                                                          envio, linha_do_tempo["decisao"])
        envios.append(roteiro_do_envio)
        data_anterior = data_do_envio
    return envios


# ================================ O roteiro inteiro ================================

def _empresa_no_roteiro(empresa: dict, cpfs_usados: set, contas_usadas: set, degraus: dict, pasta: Path,
                        limite: int | None) -> dict:
    """Uma empresa completa no roteiro: o cadastro, o login, os envios, os acessos e a conversa com o banco."""
    # Cada empresa tem o seu sorteio (a semente e a chave): gerar só algumas dá as mesmas pessoas
    sorteio = random.Random(f"{SEMENTE}-{empresa['chave']}")
    cadastro = _cadastro_da_empresa(empresa, sorteio)
    # O que as funções das pessoas e dos envios precisam saber da empresa (a matrícula começa num número sorteado)
    contexto = {"empresa": empresa, "cadastro": cadastro, "cpfs_usados": cpfs_usados, "contas_usadas": contas_usadas,
                "nomes_usados": set(), "degraus": degraus, "matricula": sorteio.randint(100, 900) * 10,
                "cadastradas": [], "arquivos_de_contas": 0}
    # A pasta dos arquivos da empresa
    pasta_da_empresa = pasta / NOME_DA_PASTA_DOS_ARQUIVOS / empresa["chave"]
    pasta_da_empresa.mkdir(parents=True, exist_ok=True)
    envios = _envios_da_empresa(sorteio, contexto, pasta_da_empresa, limite)
    conversa = _conversa_da_empresa(empresa["chave"])
    # A empresa no roteiro: o cadastro, o login, os acessos, a conversa e os envios
    return {
        "chave": empresa["chave"], "nome": empresa["nome"], "setor": empresa["setor"],
        "municipio": empresa["municipio"], "uf": empresa["uf"], "cnpj": cadastro["cnpj"],
        "endereco_comercial": empresa["endereco_comercial"], "dominio_email": cadastro["dominio_email"],
        "contrato_dias_uteis": empresa["contrato_dias_uteis"], "kit": empresa["kit"],
        "cnpjs_extras": cadastro["cnpjs_extras"], "login": cadastro["login"],
        "acessos": _acessos(sorteio, empresa, envios, conversa),
        "acessos_aos_dados": _acessos_aos_dados(sorteio, envios), "conversa": conversa, "envios": envios,
    }


def _acessos_aos_dados(sorteio: random.Random, envios: list[dict]) -> list[dict]:
    """As aberturas da lista de funcionários pelo RH: uma depois de cada cadastro aprovado (e um download às vezes).

    Devolve: [{dias_uteis, hora, tipo, quantidade}], em que quantidade é quantas pessoas a lista mostrava.
    """
    acessos, cadastradas = [], 0
    for envio in envios:
        # Só depois de um cadastro aprovado há gente nova na lista
        if envio["destino"] != "CADASTRADO":
            continue
        # Quantas pessoas a lista mostrava (as cadastradas até este envio)
        cadastradas = cadastradas + envio["pessoas_novas"]
        decisao = envio["linha_do_tempo"]["decisao"]
        # No dia da aprovação (no fim da tarde) ou no dia seguinte (de manhã)
        dia = max(1, decisao["dias_uteis"] - sorteio.choice([0, 1]))
        acessos.append({"dias_uteis": dia, "hora": "16:45" if dia == decisao["dias_uteis"] else "10:20",
                        "tipo": "LISTA", "quantidade": cadastradas})
        # Às vezes a empresa baixa a lista (para o financeiro pagar o salário nas contas)
        if sorteio.random() < 0.4:
            acessos.append({"dias_uteis": dia, "hora": "17:05" if dia == decisao["dias_uteis"] else "10:35",
                            "tipo": "DOWNLOAD", "quantidade": cadastradas})
    return acessos


def gerar(pasta: Path = PASTA_DA_BASE_VIVA, chaves: list[str] | None = None, limite: int | None = None) -> dict:
    """Gera a base viva na pasta: um arquivo por envio e o roteiro.json. Devolve o roteiro.

    Recebe: pasta (padrão: data/base_viva); chaves — só estas empresas (None = as 17); limite — no máximo esse número
    de pessoas novas por envio (os testes usam poucas; None = as do catálogo).
    Apaga antes o que a geração anterior deixou (a pasta dos arquivos e o roteiro), para não sobrar arquivo velho.
    """
    pasta = Path(pasta)
    # Os arquivos da geração anterior saem (o roteiro é regravado no fim)
    shutil.rmtree(pasta / NOME_DA_PASTA_DOS_ARQUIVOS, ignore_errors=True)
    pasta.mkdir(parents=True, exist_ok=True)
    # As faixas de salário: a pública de cada profissão e a de referência de cada cargo no Validador
    publicas = faixas_publicas()
    de_referencia = validador.faixas_de_referencia()
    # Os degraus de salário de cada cargo (os mesmos para todas as empresas)
    degraus = {}
    for cargo in catalogos.PROFISSOES:
        degraus[cargo] = degraus_de_salario(cargo, publicas, de_referencia)
    # Os CPFs e as contas usados (nunca se repetem entre empresas) e as empresas do roteiro
    cpfs_usados, contas_usadas, empresas = set(), set(), []
    for empresa in catalogos.EMPRESAS:
        # Só as empresas pedidas (nos testes); sem pedido, as 17
        if chaves is not None and empresa["chave"] not in chaves:
            continue
        empresas.append(_empresa_no_roteiro(empresa, cpfs_usados, contas_usadas, degraus, pasta, limite))
    # O roteiro: a versão, a semente, a referência das datas dos arquivos e as empresas
    roteiro = {"versao": VERSAO_DO_ROTEIRO, "semente": SEMENTE,
               "referencia_do_gerador": catalogos.REFERENCIA_DO_GERADOR.isoformat(),
               "codigo_do_banco": catalogos.CODIGO_DO_BANCO, "empresas": empresas}
    (pasta / NOME_DO_ROTEIRO).write_text(json.dumps(roteiro, ensure_ascii=False, indent=1), encoding="utf-8")
    return roteiro


def resumo(roteiro: dict) -> dict:
    """As contagens do roteiro: empresas, envios por destino, linhas e pessoas novas. Só números."""
    por_destino, linhas, pessoas = {}, 0, 0
    for empresa in roteiro["empresas"]:
        for envio in empresa["envios"]:
            # Quantos envios em cada etapa e quantas linhas e pessoas novas no total
            por_destino[envio["destino"]] = por_destino.get(envio["destino"], 0) + 1
            linhas = linhas + envio["linhas"]
            pessoas = pessoas + envio["pessoas_novas"]
    return {"empresas": len(roteiro["empresas"]), "envios_por_destino": por_destino, "linhas": linhas,
            "pessoas_novas": pessoas}


if __name__ == "__main__":
    # Gera a base viva inteira em data/base_viva e mostra as contagens
    roteiro_gerado = gerar()
    print(json.dumps(resumo(roteiro_gerado), ensure_ascii=False, indent=1))
    print("Gravado em", PASTA_DA_BASE_VIVA)
