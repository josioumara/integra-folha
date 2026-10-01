"""Padroniza de novo e valida de novo os envios que ainda esperam a empresa (não foram ao banco).

Para que serve (pendências por conversa): quando uma regra do Normalizador
melhora (ex.: "Solteiro(a)" e "Casada" passaram a ser entendidos como "Solteiro" e "Casado"), os envios que já estavam
esperando continuam com a pendência antiga, porque foram padronizados antes. Este script passa por eles e refaz os dois
passos, com as mesmas decisões de coluna que a empresa já tomou:
    1. o Normalizador padroniza de novo a partir do arquivo guardado;
    2. o Validador valida de novo (as correções e confirmações da empresa continuam valendo por cima).

O que ele NÃO faz: não chama a IA (MODE=mock forçado), não mexe em envio que já foi ao banco, que foi descartado ou
cujo mapeamento ainda espera o aceite, e não muda a etapa do fluxo (quem pede para seguir continua sendo a empresa).

Para rodar (no banco do .env; em teste, use um banco temporário):
    python scripts/padronizar_de_novo_os_envios_pendentes.py
"""
import os
import sys
from pathlib import Path

# Nada de IA neste script, mesmo com o .env no modo pago (regra do projeto para script solto)
os.environ["MODE"] = "mock"

# Permite importar os módulos do projeto ao rodar o script diretamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import auth, cadastro, mapeamentos, normalizador, processamentos, validador  # noqa: E402
from workflows import fluxo_empresa  # noqa: E402


def empresas_com_envios(conexao) -> list[str]:
    """As empresas que têm algum envio registrado, em ordem. Ex.: ["EMP001", "EMP003"]."""
    processamentos._preparar(conexao)
    consulta = conexao.execute("SELECT DISTINCT empresa_id FROM processamentos ORDER BY empresa_id")
    empresas = []
    for linha in consulta:
        empresas.append(linha[0])
    return empresas


def envio_ainda_espera_a_empresa(conexao, perfil) -> bool:
    """True se o envio está entre a padronização e o envio ao banco, com o mapeamento já aceito.

    Envio no banco, cadastrado, descartado ou esperando o aceite das colunas fica de fora.
    """
    # A situação do envio: padronizado ou com pendência
    if perfil.status not in validador.ESTADOS_QUE_A_EMPRESA_AINDA_MEXE:
        return False
    # O mapeamento precisa estar aceito (o Normalizador só roda assim)
    mapeamento = mapeamentos.obter(conexao, perfil.processamento_id)
    if mapeamento is None or mapeamento[1] != "APROVADO":
        return False
    # O fluxo parado na correção ou na conferência (antes de ir ao banco)
    etapa = fluxo_empresa.situacao(conexao, perfil.processamento_id)["etapa_atual"]
    return etapa in cadastro.ETAPAS_DA_CONFERENCIA


def pendencias_em_aberto(conexao, processamento_id: str) -> int:
    """Quantas pendências pedem ação da empresa agora (bloqueantes e alertas não confirmados)."""
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return 0
    contagem = relatorio.contagem()
    return contagem[validador.BLOQUEANTE] + contagem[validador.ALERTA]


def padronizar_de_novo_os_envios_pendentes(conexao) -> list[dict]:
    """Passa por todos os envios que ainda esperam a empresa e refaz a padronização e a validação.

    Devolve: [{processamento_id, empresa_id, nome_arquivo, pendencias_antes, pendencias_depois, pulado}], um por envio
    que ainda esperava a empresa; pulado é None, ou o motivo de o envio ter ficado como estava (ex.: o arquivo original
    não foi encontrado).
    Primeiro padroniza todos; depois valida todos: a regra "pessoa em outro envio" compara os envios entre si, então
    cada um é validado quando todos já estão padronizados.
    """
    refeitos = []
    # 1. Padroniza de novo, com as decisões de coluna que a empresa já tomou
    for empresa_id in empresas_com_envios(conexao):
        for perfil in processamentos.listar(conexao, empresa_id):
            if not envio_ainda_espera_a_empresa(conexao, perfil):
                continue
            antes = pendencias_em_aberto(conexao, perfil.processamento_id)
            decisoes = normalizador.decisoes_salvas(conexao, perfil.processamento_id)
            # try/except: um envio cujo arquivo original sumiu não pode parar os outros (fica anotado e é pulado)
            try:
                normalizador.executar(conexao, perfil.processamento_id, empresa_id, decisoes)
            except FileNotFoundError:
                refeitos.append({"processamento_id": perfil.processamento_id, "empresa_id": empresa_id,
                                 "nome_arquivo": perfil.nome_arquivo, "pendencias_antes": antes,
                                 "pulado": "o arquivo original não foi encontrado"})
                continue
            refeitos.append({"processamento_id": perfil.processamento_id, "empresa_id": empresa_id,
                             "nome_arquivo": perfil.nome_arquivo, "pendencias_antes": antes, "pulado": None})
    # 2. Valida de novo (as correções e confirmações da empresa continuam valendo por cima)
    for refeito in refeitos:
        # O envio pulado fica como estava: nem padronizado nem validado de novo
        if refeito["pulado"]:
            refeito["pendencias_depois"] = refeito["pendencias_antes"]
            continue
        validador.executar(conexao, refeito["processamento_id"], refeito["empresa_id"], revalidar_os_outros=False)
        refeito["pendencias_depois"] = pendencias_em_aberto(conexao, refeito["processamento_id"])
    return refeitos

def main() -> None:
    """Roda no banco do .env e mostra, por envio, quantas pendências havia e quantas ficaram."""
    conexao = auth.conectar()
    try:
        refeitos = padronizar_de_novo_os_envios_pendentes(conexao)
    finally:
        conexao.close()
    print(f"Envios padronizados de novo: {len(refeitos)}")
    for refeito in refeitos:
        # O envio pulado diz o porquê; os outros, quantas pendências havia e quantas ficaram
        if refeito["pulado"]:
            print(f"  {refeito['empresa_id']} · {refeito['nome_arquivo']}: pulado ({refeito['pulado']})")
            continue
        print(f"  {refeito['empresa_id']} · {refeito['nome_arquivo']}: "
              f"{refeito['pendencias_antes']} → {refeito['pendencias_depois']} pendência(s)")


if __name__ == "__main__":
    main()
