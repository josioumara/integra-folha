"""Grava, no banco que já está em uso, a versão nova do parâmetro do layout com só 4 campos obrigatórios (ADR-143).

Para que serve: o parâmetro do layout tem versões guardadas no banco da aplicação (services/parametros.py). Este script
grava a próxima versão com a decisão do ADR-143 (o plano simplificado):
    - só 4 informações são obrigatórias: o CPF, o código da profissão (CBO), a renda bruta mensal e a data de admissão;
    - todos os outros campos passam a ser opcionais (o cargo também);
    - entra o campo novo codigo_cbo, logo depois do cargo: texto com os 6 dígitos da CBO oficial.
O arquivo data/contratos/layout_v1.csv NÃO muda (é o padrão das bases novas e dos testes): a mudança vale só no banco
em que o script roda. Ele usa o mesmo caminho da tela Parâmetros, então a mudança aparece no registro das alterações.

Pode rodar mais de uma vez: se a versão vigente já está assim, nada é gravado.
Depois dele, refaça o índice do RAG (python scripts/build_index.py), com o servidor da porta 8000 parado.

Para rodar: python scripts/aplicar_parametro_adr_143.py
"""
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from services import banco, parametros  # noqa: E402

# Quem aparece no registro das alterações da tela Parâmetros
AUTOR = "sistema (ADR-143)"

# Os únicos campos obrigatórios depois do ADR-143
CAMPOS_OBRIGATORIOS = ["cpf", "codigo_cbo", "valor_renda", "data_admissao"]

# O campo novo do código da profissão, no mesmo grupo do cargo (entra logo depois dele)
CAMPO_DO_CBO = {
    "campo": "codigo_cbo",
    "grupo": "Cadastro empresarial",
    "tipo": "TEXTO",
    "obrigatorio": True,
    "sensivel": False,
    "uso_comercial_permitido": False,
    "descricao": "Código da profissão pela CBO oficial (Classificação Brasileira de Ocupações)",
    "regra": "6 dígitos da CBO oficial; pode vir com traço ou ponto (ex.: 4110-10)",
    "nao_confundir_com": "Cargo; código da unidade; centro de custo",
    "exemplo": "411010",
    "igual_para_todos": False,
}


def campo_com_o_adr_143(campo: dict) -> dict:
    """O campo como fica com o ADR-143: obrigatório só se estiver na lista dos 4.

    Recebe: um campo da versão vigente (dicionário, como está gravado). Devolve: uma cópia ajustada.
    Ex.: {"campo": "sexo", "obrigatorio": True, ...} → {"campo": "sexo", "obrigatorio": False, ...}.
    """
    # Uma cópia, para não mexer no dicionário de quem chamou
    ajustado = dict(campo)
    # Obrigatório só se o nome técnico estiver entre os 4 campos da decisão
    ajustado["obrigatorio"] = ajustado["campo"] in CAMPOS_OBRIGATORIOS
    return ajustado


def campos_com_o_adr_143(campos: list[dict]) -> list[dict]:
    """A lista inteira de campos ajustada pelo ADR-143, com o codigo_cbo logo depois do cargo.

    Recebe: os campos da versão vigente. Devolve: a lista nova, na mesma ordem, com o campo do CBO a mais (se ele ainda
    não existir; se existir, só a marca de obrigatório muda).
    """
    # Confere se o campo do CBO já existe na versão vigente
    ja_tem_o_cbo = False
    for campo in campos:
        if campo["campo"] == "codigo_cbo":
            ja_tem_o_cbo = True
    campos_novos = []
    for campo in campos:
        # O campo da versão vigente, com a marca de obrigatório da decisão
        campos_novos.append(campo_com_o_adr_143(campo))
        # O campo do CBO entra logo depois do cargo, se ainda não existir
        if campo["campo"] == "cargo" and not ja_tem_o_cbo:
            campos_novos.append(dict(CAMPO_DO_CBO))
    return campos_novos


def aplicar(conexao) -> dict | None:
    """Grava a versão nova do parâmetro, se precisar. Devolve {versao, mudancas}, ou None se já estava assim."""
    # A versão vigente, como a tela Parâmetros a manda (dicionários)
    _, campos_vigentes = parametros.layout_ativo(conexao)
    campos_em_dicionario = []
    for campo in campos_vigentes:
        campos_em_dicionario.append(campo.model_dump(mode="json"))
    try:
        # O mesmo caminho da tela: confere, compara, grava a versão nova e deixa o registro das alterações
        return parametros.salvar_layout_pela_tela(conexao, campos_com_o_adr_143(campos_em_dicionario), AUTOR)
    except ValueError as erro:
        # "Nada mudou": a versão vigente já tem o ADR-143
        if "Nada mudou" in str(erro):
            return None
        raise


if __name__ == "__main__":
    # Abre o banco da aplicação pela porta única (SQLite ou PostgreSQL, conforme o .env; ADR-67)
    conexao_do_banco = banco.conectar()
    resultado = aplicar(conexao_do_banco)
    conexao_do_banco.close()
    if resultado is None:
        print("O parâmetro vigente já tem o ADR-143: nada foi gravado.")
    else:
        print(f"Versão v{resultado['versao']} gravada:")
        for mudanca in resultado["mudancas"]:
            print(f"  - {mudanca}")
