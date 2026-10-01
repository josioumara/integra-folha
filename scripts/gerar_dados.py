"""Gera o "mundo de mentira" do Integra Folha, sempre igual para a mesma seed (ADR-21).

O que sai:
- data/synthetic/empresas.csv            as 6 empresas fictícias, com CNPJ sintético
- data/synthetic/funcionarios_truth.csv  o GABARITO: cada funcionário com os 44 campos corretos
- data/synthetic/faixas_referencia_cargo.csv  faixa de renda de referência por cargo
- data/synthetic/envios/                 os arquivos que as empresas enviam, cada um num formato e
                                         com erros escondidos de propósito
- data/golden/                           para cada arquivo, o gabarito: como mapear as colunas e
                                         quais erros existem, em qual linha

Sem a base do banco: quem é correntista o sistema só sabe pelo arquivo de contas que o banco devolve
(services/contas_abertas.py), então o gerador não sorteia mais correntistas, autorização de contato nem segmento.

Para rodar: python scripts/gerar_dados.py
"""
import csv
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from models.contratos import carregar_layout  # noqa: E402
from services.documentos import gerar_cnpj, gerar_cpf  # noqa: E402

# Semente do sorteio: a mesma semente gera sempre o mesmo mundo
SEED = 42
# Data de referência da carga
DATA_REFERENCIA = date(2026, 9, 1)
# Onde os arquivos gerados são gravados
PASTA_SINTETICO = RAIZ / "data" / "synthetic"

# Cargo -> (tipo de renda, mediana mensal). Base das faixas de referência (ADR-14).
CARGOS = {
    "Auxiliar administrativo": ("CLT", Decimal("2600")),
    "Assistente administrativo": ("CLT", Decimal("3400")),
    "Analista": ("CLT", Decimal("5200")),
    "Analista sênior": ("CLT", Decimal("8200")),
    "Coordenador": ("CLT", Decimal("11500")),
    "Gerente": ("CLT", Decimal("16000")),
    "Diretor": ("CLT", Decimal("28000")),
    "Operador de logística": ("CLT", Decimal("2900")),
    "Motorista": ("CLT", Decimal("3300")),
    "Desenvolvedor": ("CLT", Decimal("7800")),
    "Vendedor": ("CLT", Decimal("2800")),
    "Técnico de enfermagem": ("CLT", Decimal("3600")),
    "Enfermeiro": ("CLT", Decimal("6200")),
    "Sócio-administrador": ("PRO_LABORE", Decimal("20000")),
}

# As 6 empresas do plano (§14), com o desafio de cada arquivo.
# "n" = funcionários da carga inicial; "unidades" = (código, nome, município, UF) de cada unidade.
EMPRESAS = [
    {"id": "EMP001", "nome": "Aurora Alimentos Ltda.", "setor": "Indústria", "n": 35, "arquivo": "aurora_carga_inicial.xlsx",
     "desafio": "cabeçalho e valores simples",
     "unidades": [("AUR-01", "Fábrica Campinas", "Campinas", "SP")],
     "cargos": ["Auxiliar administrativo", "Analista", "Coordenador", "Gerente", "Operador de logística", "Sócio-administrador"]},
    {"id": "EMP002", "nome": "Horizonte Logística Ltda.", "setor": "Logística", "n": 50, "arquivo": "horizonte_carga_inicial.csv",
     "desafio": "CSV com ponto e vírgula, acentos em Windows-1252, datas DD/MM/AAAA e vírgula decimal",
     "unidades": [("HOR-01", "CD Contagem", "Contagem", "MG"), ("HOR-02", "CD Campinas", "Campinas", "SP")],
     "cargos": ["Operador de logística", "Motorista", "Assistente administrativo", "Analista", "Gerente"]},
    {"id": "EMP003", "nome": "Brisa Tecnologia Ltda.", "setor": "Tecnologia", "n": 28, "arquivo": "brisa_carga_inicial.xlsx",
     "desafio": "nomes de colunas alternativos; CPF e matrícula gravados como número (zeros à esquerda perdidos)",
     "unidades": [("BRI-01", "Sede Florianópolis", "Florianópolis", "SC")],
     "cargos": ["Desenvolvedor", "Analista", "Analista sênior", "Coordenador", "Diretor"]},
    {"id": "EMP004", "nome": "Vale Verde Serviços Ltda.", "setor": "Serviços", "n": 70, "arquivo": "vale_verde_carga_inicial.xlsx",
     "desafio": "cabeçalho na linha 4 e colunas extras",
     "unidades": [("VAL-01", "Matriz Curitiba", "Curitiba", "PR")],
     "cargos": ["Auxiliar administrativo", "Assistente administrativo", "Analista", "Coordenador", "Vendedor"]},
    {"id": "EMP005", "nome": "Prisma Comércio Ltda.", "setor": "Varejo", "n": 42, "arquivo": "prisma_carga_inicial.csv",
     "desafio": "valores como texto (\"R$ 3.150,00\") e duplicidades",
     "unidades": [("PRI-01", "Loja Recife Centro", "Recife", "PE")],
     "cargos": ["Vendedor", "Auxiliar administrativo", "Gerente", "Analista"]},
    {"id": "EMP006", "nome": "Atlântico Saúde Ltda.", "setor": "Saúde", "n": 20, "arquivo": "atlantico_carga_inicial.xlsx",
     "desafio": "coluna ambígua (\"Vencimentos\") e rendas fora do padrão do cargo",
     "unidades": [("ATL-01", "Hospital Salvador", "Salvador", "BA")],
     "cargos": ["Técnico de enfermagem", "Enfermeiro", "Auxiliar administrativo", "Analista"]},
]

# Quantos funcionários novos cada empresa manda no arquivo de inclusão (ADR-23)
NOVOS_NA_INCLUSAO = {"EMP001": 5, "EMP002": 4, "EMP003": 2}

# Listas usadas para sortear nomes e endereços fictícios
NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor", "Isabela", "João", "Karina",
         "Lucas", "Mariana", "Nicolas", "Olívia", "Paulo", "Queila", "Rafael", "Sofia", "Tiago", "Úrsula",
         "Vinícius", "Wesley", "Yasmin", "Zeca"]
SOBRENOMES = ["Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferraz", "Gomes", "Holanda", "Ignácio",
              "Jardim", "Lacerda", "Machado", "Nogueira", "Oliveira", "Prado", "Queiroz", "Rezende", "Siqueira",
              "Teixeira", "Uchoa", "Vasconcelos", "Xavier"]
BAIRROS = ["Centro", "Jardim América", "Vila Nova", "Boa Vista", "São José", "Santa Luzia", "Industrial"]
RUAS = ["Rua das Palmeiras", "Avenida Brasil", "Rua do Comércio", "Rua Sete de Setembro", "Avenida das Flores"]


def _data_sorteada(sorteio: random.Random, inicio: date, fim: date) -> date:
    """Um dia qualquer entre o início e o fim."""
    dias_no_periodo = (fim - inicio).days
    return inicio + timedelta(days=sorteio.randint(0, dias_no_periodo))


def _cep_sorteado(sorteio: random.Random) -> str:
    """Um CEP fictício de 8 dígitos."""
    return f"{sorteio.randint(10000000, 99999999)}"


def _renda_sorteada(sorteio: random.Random, cargo: str) -> Decimal:
    """Renda perto da mediana do cargo (±25%), em centavos exatos."""
    mediana = CARGOS[cargo][1]
    # Um fator entre 0,75 e 1,25, com duas casas
    fator = Decimal(str(round(sorteio.uniform(0.75, 1.25), 2)))
    return (mediana * fator).quantize(Decimal("0.01"))


def _nascimento(sorteado: date, admissao: date) -> date:
    """Ninguém é admitido com menos de 18 anos (o Validador confere).

    Se o sorteio der alguém novo demais, recua 20 anos, SEM sortear de novo: assim o resto dos dados
    gerados com a mesma seed continua idêntico.
    """
    # A data de nascimento mais recente possível: 18 anos antes da admissão
    limite = admissao.replace(year=admissao.year - 18, day=1)
    if sorteado <= limite:
        return sorteado
    # Novo demais: 20 anos antes (dia no máximo 28, para não cair em 29 de fevereiro inexistente)
    return sorteado.replace(year=sorteado.year - 20, day=min(sorteado.day, 28))


def _data_de_efetivacao(sorteio: random.Random, admissao: date) -> str:
    """80% dos funcionários são efetivados 90 dias depois da admissão; os outros ficam sem a data."""
    if sorteio.random() < 0.8:
        return (admissao + timedelta(days=90)).isoformat()
    return ""


def gerar_funcionario(sorteio: random.Random, empresa: dict, cnpj: str, numero: int, carga: str) -> dict:
    """Um funcionário com os 44 campos do layout v1, todos corretos (é o gabarito).

    Atenção: os campos são sorteados na ordem em que aparecem no dicionário abaixo. Mudar a ordem muda
    todos os dados gerados.
    """
    codigo_unidade, nome_unidade, municipio, uf = sorteio.choice(empresa["unidades"])
    cargo = sorteio.choice(empresa["cargos"])
    admissao = _data_sorteada(sorteio, date(2012, 1, 1), date(2026, 6, 30))
    nome = f"{sorteio.choice(NOMES)} {sorteio.choice(SOBRENOMES)} {sorteio.choice(SOBRENOMES)}"
    # O começo dos e-mails: primeiro nome + número do funcionário (ex.: "ana7")
    usuario_do_email = nome.lower().split()[0] + str(numero)
    return {
        "funcionario_id": f"{empresa['id']}-{numero:04d}",
        "empresa_id": empresa["id"],
        "carga": carga,
        # Titular
        "matricula": f"{numero:05d}",  # zeros à esquerda fazem parte da matrícula
        "nome_completo": nome,
        "cpf": gerar_cpf(sorteio),
        "data_nascimento": _nascimento(_data_sorteada(sorteio, date(1965, 1, 1), date(2005, 12, 31)), admissao).isoformat(),
        "sexo": sorteio.choice(["F", "M"]),
        "estado_civil": sorteio.choice(["Solteiro", "Casado", "Divorciado", "União estável"]),
        "nome_mae": f"{sorteio.choice(NOMES)} {sorteio.choice(SOBRENOMES)}",
        # 95% brasileiros, 3% portugueses, 2% argentinos
        "nacionalidade": sorteio.choices(["Brasileira", "Portuguesa", "Argentina"], weights=[95, 3, 2])[0],
        "municipio_naturalidade": municipio,
        "uf_naturalidade": uf,
        "nis_pis": f"{sorteio.randint(10000000000, 99999999999)}",
        "escolaridade": sorteio.choice(["Médio completo", "Superior completo", "Pós-graduação"]),
        # Documento
        "tipo_documento": sorteio.choice(["RG", "CNH"]),
        "numero_documento": f"{sorteio.randint(1000000, 99999999)}",
        "orgao_emissor": sorteio.choice(["SSP", "DETRAN"]),
        "uf_emissor": uf,
        "data_emissao_documento": _data_sorteada(sorteio, date(2000, 1, 1), date(2025, 12, 31)).isoformat(),
        # Endereço residencial (na mesma cidade da unidade)
        "cep_residencial": _cep_sorteado(sorteio),
        "logradouro_residencial": sorteio.choice(RUAS),
        "numero_residencial": str(sorteio.randint(10, 2500)),
        # Duas chances em cinco de não ter complemento
        "complemento_residencial": sorteio.choice(["", "", "Apto 12", "Casa 2", "Bloco B"]),
        "bairro_residencial": sorteio.choice(BAIRROS),
        "municipio_residencial": municipio,
        "uf_residencial": uf,
        # Telefones e e-mails (domínio reservado .example: nunca é um endereço real)
        "telefone_residencial": f"({sorteio.randint(11, 99)}) 3{sorteio.randint(100, 999)}-{sorteio.randint(1000, 9999)}",
        "telefone_celular": f"({sorteio.randint(11, 99)}) 9{sorteio.randint(1000, 9999)}-{sorteio.randint(1000, 9999)}",
        "email_pessoal": f"{usuario_do_email}@pessoal.example",
        "email_corporativo": f"{usuario_do_email}@{empresa['id'].lower()}.example",
        # Cadastro empresarial
        "cnpj_empregador": cnpj,
        # Sem empresas de grupo nos dados fictícios: o CNPJ do grupo fica vazio (campo opcional, ADR-77)
        "cnpj_grupo": "",
        "codigo_unidade": codigo_unidade,
        "nome_unidade": nome_unidade,
        "cargo": cargo,
        "data_admissao": admissao.isoformat(),
        "data_efetivacao": _data_de_efetivacao(sorteio, admissao),
        # Renda
        "tipo_renda": CARGOS[cargo][0],
        "valor_renda": str(_renda_sorteada(sorteio, cargo)),
        "data_referencia_renda": DATA_REFERENCIA.isoformat(),
        # Endereço comercial (o da unidade de trabalho). Tem sorteio próprio, com a semente no código da
        # unidade, para sair igual para todos os funcionários da mesma unidade
        "cep_comercial": _cep_sorteado(random.Random(codigo_unidade)),
        "logradouro_comercial": "Avenida Industrial" if empresa["setor"] == "Indústria" else "Avenida Central",
        "numero_comercial": str(random.Random(codigo_unidade + "n").randint(100, 5000)),
        "complemento_comercial": "",
        "bairro_comercial": "Distrito Empresarial",
        "municipio_comercial": municipio,
        "uf_comercial": uf,
    }


def faixas_referencia() -> list[dict]:
    """Faixa de renda de referência por cargo (60% a 160% da mediana), usada quando a empresa tem
    poucos colegas no cargo."""
    faixas = []
    for cargo, (tipo_renda, mediana) in CARGOS.items():
        faixa_minima = (mediana * Decimal("0.6")).quantize(Decimal("0.01"))
        faixa_maxima = (mediana * Decimal("1.6")).quantize(Decimal("0.01"))
        faixas.append({"cargo": cargo, "tipo_renda": tipo_renda, "mediana": str(mediana),
                       "faixa_minima": str(faixa_minima), "faixa_maxima": str(faixa_maxima)})
    return faixas


def gravar_csv(caminho: Path, linhas: list[dict], separador: str = ",", codificacao: str = "utf-8") -> None:
    """Grava uma lista de dicionários como CSV, com as chaves do primeiro como cabeçalho."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding=codificacao, newline="") as arquivo:
        # Quebra de linha no formato Linux: o arquivo sai igual ao versionado no Git, em qualquer máquina
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]), delimiter=separador, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(linhas)


def main() -> None:
    """Gera todos os arquivos do mundo sintético."""
    # Os arquivos das empresas ficam num módulo próprio
    from scripts.montar_envios import montar_envios

    sorteio = random.Random(SEED)
    # Os nomes dos 44 campos do layout, na ordem do layout
    campos_do_layout = []
    for campo in carregar_layout():
        campos_do_layout.append(campo.campo)

    empresas, funcionarios = [], []
    for empresa in EMPRESAS:
        cnpj = gerar_cnpj(sorteio)
        # A cidade da empresa é a da primeira unidade
        _, _, municipio, uf = empresa["unidades"][0]
        empresas.append({"empresa_id": empresa["id"], "nome": empresa["nome"], "setor": empresa["setor"],
                         "cnpj": cnpj, "municipio": municipio, "uf": uf, "status_convenio": "ATIVO",
                         "data_inicio": "2026-08-01"})
        # Carga inicial + alguns funcionários novos para os arquivos de inclusão (ADR-23)
        novos = NOVOS_NA_INCLUSAO.get(empresa["id"], 0)
        for numero in range(1, empresa["n"] + novos + 1):
            # Os primeiros "n" vão na carga inicial; os seguintes, na inclusão
            if numero <= empresa["n"]:
                carga = "INICIAL"
            else:
                carga = "INCLUSAO"
            funcionarios.append(gerar_funcionario(sorteio, empresa, cnpj, numero, carga))

    # Conferência: o gabarito tem exatamente os 44 campos do layout, na ordem do layout
    for funcionario in funcionarios:
        campos_do_funcionario = []
        for campo in funcionario:
            if campo in campos_do_layout:
                campos_do_funcionario.append(campo)
        assert campos_do_funcionario == campos_do_layout, "gabarito fora do layout"

    gravar_csv(PASTA_SINTETICO / "empresas.csv", empresas)
    gravar_csv(PASTA_SINTETICO / "funcionarios_truth.csv", funcionarios)
    gravar_csv(PASTA_SINTETICO / "faixas_referencia_cargo.csv", faixas_referencia())

    # Os arquivos das empresas têm sorteio próprio (semente + 1)
    arquivos = montar_envios(random.Random(SEED + 1), EMPRESAS, funcionarios)

    # Resumo para conferir no terminal
    print(f"{len(empresas)} empresas | {len(funcionarios)} funcionários | {len(arquivos)} arquivos de envio")


if __name__ == "__main__":
    main()
