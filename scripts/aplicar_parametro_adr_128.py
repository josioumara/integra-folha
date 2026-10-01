"""Grava, no banco que já está em uso, a versão nova do parâmetro do layout com as decisões do ADR-128.

Para que serve: o parâmetro do layout tem versões guardadas no banco da aplicação (services/parametros.py). A versão 1
nasce do arquivo data/contratos/layout_v1.csv só num banco NOVO (os testes e uma instalação nova já nascem com as
regras do ADR-128). Num banco que já tem versões (o PostgreSQL da máquina local), a versão vigente continua a antiga:
este script grava a próxima versão, mudando só o que o ADR-128 decidiu e mantendo o resto que o banco já editou na
tela Parâmetros. As decisões (ADR-128):
    - a matrícula passa a ser opcional (a empresa que não usa matrícula não precisa enviar; o funcionário é
      identificado pelo CPF);
    - o sexo passa a ser obrigatório (a empresa sempre informa);
    - o tipo de renda tem a opção OUTROS, e Mensal, Horária ou Comissionada não viram CLT sozinhas;
    - o salário (valor_renda) tem o mínimo de R$ 500,00 (fora da faixa, alerta).

Pode rodar mais de uma vez: se a versão vigente já está assim, nada é gravado.
Depois dele, refaça o índice do RAG (python scripts/build_index.py), com o servidor da porta 8000 parado.

Para rodar: python scripts/aplicar_parametro_adr_128.py
"""
import sys
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from services import banco, parametros  # noqa: E402

# Quem aparece no registro das alterações da tela Parâmetros
AUTOR = "sistema (ADR-128)"

# Os textos novos dos campos que o ADR-128 mudou (os mesmos do data/contratos/layout_v1.csv)
REGRA_DA_MATRICULA = ("Texto; preservar zeros à esquerda; único na empresa; opcional (a empresa que não usa matrícula "
                      "não precisa enviar; o funcionário é identificado pelo CPF)")
REGRA_DO_SEXO = "F ou M; a empresa sempre informa"
REGRA_DO_TIPO_DE_RENDA = ("CLT, PRO_LABORE ou OUTROS; a empresa informa (Mensal, Horária ou Comissionada não viram CLT "
                          "sozinhas)")
REGRA_DO_VALOR_DA_RENDA = ("Maior ou igual a zero; duas casas decimais; abaixo do mínimo ou acima do máximo do "
                           "parâmetro vira alerta")
MINIMO_DO_VALOR_DA_RENDA = "500.00"


def campo_com_o_adr_128(campo: dict) -> dict:
    """O campo como fica com o ADR-128.

    Recebe: um campo da versão vigente (dicionário, como está gravado). Devolve: uma cópia ajustada.
    Ex.: {"campo": "sexo", "obrigatorio": False, ...} → {"campo": "sexo", "obrigatorio": True, ...}.
    """
    # Uma cópia, para não mexer no dicionário de quem chamou
    ajustado = dict(campo)
    # A matrícula passa a ser opcional
    if ajustado["campo"] == "matricula":
        ajustado["obrigatorio"] = False
        ajustado["regra"] = REGRA_DA_MATRICULA
    # O sexo passa a ser obrigatório
    if ajustado["campo"] == "sexo":
        ajustado["obrigatorio"] = True
        ajustado["regra"] = REGRA_DO_SEXO
    # O tipo de renda ganha OUTROS (a lista fica em data/contratos/dominios_v1.json; aqui, o texto que a IA lê)
    if ajustado["campo"] == "tipo_renda":
        ajustado["regra"] = REGRA_DO_TIPO_DE_RENDA
    # O salário começa com o piso de R$ 500,00
    if ajustado["campo"] == "valor_renda":
        ajustado["minimo"] = MINIMO_DO_VALOR_DA_RENDA
        ajustado["regra"] = REGRA_DO_VALOR_DA_RENDA
    return ajustado


def campos_com_o_adr_128(campos: list[dict]) -> list[dict]:
    """A lista inteira de campos da versão vigente, ajustada pelo ADR-128."""
    campos_novos = []
    for campo in campos:
        campos_novos.append(campo_com_o_adr_128(campo))
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
        return parametros.salvar_layout_pela_tela(conexao, campos_com_o_adr_128(campos_em_dicionario), AUTOR)
    except ValueError as erro:
        # "Nada mudou": a versão vigente já tem o ADR-128
        if "Nada mudou" in str(erro):
            return None
        raise


if __name__ == "__main__":
    # Abre o banco da aplicação pela porta única (SQLite ou PostgreSQL, conforme o .env; ADR-67)
    conexao_do_banco = banco.conectar()
    resultado = aplicar(conexao_do_banco)
    conexao_do_banco.close()
    if resultado is None:
        print("O parâmetro vigente já tem o ADR-128: nada foi gravado.")
    else:
        print(f"Versão v{resultado['versao']} gravada:")
        for mudanca in resultado["mudancas"]:
            print(f"  - {mudanca}")
