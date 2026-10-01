"""Motor de planejamento: registra cada funcionário homologado, sem LLM e sem gerar ofertas (ADR-25).

Roda uma vez por arquivo, logo depois da homologação (o fluxo chama em liberar_planejamento). Cada funcionário do
arquivo final entra numa tabela interna com a região da unidade de trabalho e a data de referência da carga.

Sem a base do banco: o sistema não sabe, na homologação, se a pessoa já é correntista.
Quem conta isso é o arquivo de contas que o banco devolve (services/contas_abertas.py, colunas tipo_conta e
situacao_correntista). Por isso o motor não classifica ninguém: cada Cadastrado fica "aguardando o retorno do banco"
até o arquivo de contas dizer o tipo; a classificação é feita na hora da consulta, em services/planejamento.py.

Privacidade (ADR-28, ADR-29):
- o motor só lê os campos que ele precisa, e todos têm de estar liberados para uso comercial no layout
  ativo (uso_comercial_permitido = S); se algum não estiver, o motor NÃO roda;
- a tabela por funcionário é interna (para rastrear os números) e guarda o HASH do CPF, nunca o CPF:
  basta para não contar a mesma pessoa duas vezes quando chega um arquivo de inclusão e para cruzar com o retorno
  do banco (o CPF do retorno vira hash e é comparado com o hash guardado);
- para fora saem só números agregados (services/planejamento.py).
"""
import csv
import hashlib
import io
import re
from datetime import datetime, timezone

from services import auditoria, banco, homologacao, parametros, processamentos

# Os únicos campos do arquivo homologado que o motor lê (região = endereço comercial, ADR-27)
CAMPOS_USADOS = ("cpf", "codigo_unidade", "nome_unidade", "municipio_comercial", "uf_comercial")

def preparar_tabelas(conexao) -> None:
    """Cria a tabela interna por funcionário e a tabela das simulações (e acrescenta colunas novas a bancos antigos).

    Nunca apaga nada: as colunas que vinham da base do banco saem só pelo scripts/tirar_a_base_do_planejamento.py,
    rodado uma vez na junção, porque o banco de dados é um só para todos os servidores (a versão antiga ainda as lê).
    """
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS planejamento_funcionario (
               empresa_id       TEXT NOT NULL,
               cpf_hash         TEXT NOT NULL,      -- SHA-256 do CPF: nunca o CPF
               processamento_id TEXT NOT NULL,      -- o arquivo em que a pessoa entrou
               uf               TEXT NOT NULL,      -- da unidade de trabalho (endereço comercial)
               municipio        TEXT NOT NULL,
               codigo_unidade   TEXT NOT NULL,
               nome_unidade     TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               data_referencia  TEXT NOT NULL DEFAULT '',  -- a data de referência da carga (filtro do painel)
               PRIMARY KEY (empresa_id, cpf_hash)   -- a mesma pessoa na mesma empresa entra uma vez só
           )"""
    )
    _acrescentar_data_de_referencia(conexao)
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS simulacao_ganho (
               id               INTEGER PRIMARY KEY AUTOINCREMENT,
               criado_em        TEXT NOT NULL,
               usuario          TEXT NOT NULL,
               filtros          TEXT NOT NULL,      -- empresa, UF e data de referência usadas (JSON)
               taxa_conquista   TEXT NOT NULL,      -- a taxa usada (fração, ex.: "0.2"; vazia se não informada)
               versao_premissas TEXT NOT NULL,      -- a versão oficial de onde a simulação partiu (ADR-26)
               resultado        TEXT NOT NULL,      -- contagens e ganhos (JSON), só números
               nome             TEXT NOT NULL DEFAULT '',    -- o nome que o especialista deu à simulação
               premissas        TEXT NOT NULL DEFAULT '{}'   -- os valores usados na simulação (JSON)
           )"""
    )
    _acrescentar_nome_e_premissas_da_simulacao(conexao)


def _acrescentar_data_de_referencia(conexao) -> None:
    """Migração: bancos criados antes da coluna data_referencia ganham a coluna."""
    # Se a coluna já existe, não há nada a migrar
    if "data_referencia" in banco.colunas_da_tabela(conexao, "planejamento_funcionario"):
        return
    # A visão antiga dos totais dependia das colunas da tabela: sai antes (não é mais usada)
    conexao.execute("DROP VIEW IF EXISTS resumo_planejamento")
    conexao.execute("ALTER TABLE planejamento_funcionario ADD COLUMN data_referencia TEXT NOT NULL DEFAULT ''")
    conexao.commit()


def _acrescentar_nome_e_premissas_da_simulacao(conexao) -> None:
    """Migração: simulações antigas (sem nome nem valores próprios) ganham as duas colunas, vazias."""
    colunas_existentes = banco.colunas_da_tabela(conexao, "simulacao_ganho")
    if "nome" not in colunas_existentes:
        conexao.execute("ALTER TABLE simulacao_ganho ADD COLUMN nome TEXT NOT NULL DEFAULT ''")
    if "premissas" not in colunas_existentes:
        conexao.execute("ALTER TABLE simulacao_ganho ADD COLUMN premissas TEXT NOT NULL DEFAULT '{}'")
    conexao.commit()


def hash_do_cpf(cpf: str) -> str:
    """A "impressão digital" do CPF (SHA-256), só dos 11 algarismos: serve para não contar a pessoa duas vezes e para
    cruzar com o retorno do banco, sem guardar o CPF.

    Exemplo: "529.982.247-25" e "52998224725" dão o mesmo hash (a pontuação sai antes).
    """
    # Só os algarismos: o arquivo homologado e o retorno do banco podem escrever o CPF de jeitos diferentes
    somente_algarismos = re.sub(r"\D", "", cpf)
    return hashlib.sha256(somente_algarismos.encode("utf-8")).hexdigest()


def campos_liberados(conexao) -> set[str]:
    """Os campos do layout ativo marcados como liberados para uso comercial (ADR-29)."""
    _, campos = parametros.layout_ativo(conexao)
    liberados = set()
    for campo in campos:
        if campo.uso_comercial_permitido:
            liberados.add(campo.campo)
    return liberados


def ler_registros_homologados(conexao, processamento_id: str) -> list[dict]:
    """Lê do arquivo final homologado SÓ os campos que o motor usa, depois de conferir que estão liberados."""
    liberados = campos_liberados(conexao)
    for campo in CAMPOS_USADOS:
        if campo not in liberados:
            raise ValueError(f"O campo {campo} não está liberado para uso comercial no layout ativo: "
                             "o motor de planejamento não roda.")
    homologado = homologacao.obter(conexao, processamento_id)
    if homologado is None:
        raise ValueError("O arquivo ainda não foi homologado: o motor só roda depois da homologação.")
    # O arquivo final é um CSV com ";" (services/homologacao.py)
    leitor = csv.DictReader(io.StringIO(homologado["arquivo"].decode("utf-8")), delimiter=";")
    registros = []
    for linha in leitor:
        # Copia só os campos usados: os outros (salário, cargo, sexo...) nem chegam ao motor
        registro = {}
        for campo in CAMPOS_USADOS:
            registro[campo] = (linha.get(campo) or "").strip()
        registros.append(registro)
    return registros


def processar_homologacao(conexao, processamento_id: str, empresa_id: str) -> dict:
    """Registra os funcionários do arquivo homologado (todos aguardando o retorno do banco). Devolve só contagens.

    Quem já foi registrado nesta empresa (ex.: a mesma pessoa numa inclusão) não é contado de novo.
    Devolve: {"novos": 35, "ja_contados": 0}.
    """
    preparar_tabelas(conexao)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # A data de referência que a empresa informou no envio do arquivo
    data_referencia = processamentos.obter(conexao, processamento_id).data_referencia.isoformat()
    contagem = {"novos": 0, "ja_contados": 0}
    for registro in ler_registros_homologados(conexao, processamento_id):
        # "ON CONFLICT DO NOTHING": se a pessoa já está na tabela desta empresa, nada é gravado
        cursor = conexao.execute(
            "INSERT INTO planejamento_funcionario (empresa_id, cpf_hash, processamento_id, uf, municipio, "
            "codigo_unidade, nome_unidade, criado_em, data_referencia) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            (empresa_id, hash_do_cpf(registro["cpf"]), processamento_id, registro["uf_comercial"],
             registro["municipio_comercial"], registro["codigo_unidade"], registro["nome_unidade"], agora,
             data_referencia))
        # rowcount = 1: a linha entrou (pessoa nova); 0: já estava lá
        if cursor.rowcount == 1:
            contagem["novos"] += 1
        else:
            contagem["ja_contados"] += 1
    conexao.commit()
    auditoria.registrar(conexao, processamento_id, empresa_id, "Planejamento", "PLANEJAMENTO_CALCULADO", contagem)
    return contagem
