"""Testes da regra da fila "O que precisa de você" de que o filtro do Início depende.

O filtro do Início (front/js/banco_inicio.js) separa os itens da fila pelo prazo sem pedir nada novo ao servidor:
    - o envio que espera a avaliação do banco e PASSOU do prazo de 1 dia útil vem com "urgente" e com o "envio_id";
    - o envio DENTRO do prazo vem com o "envio_id" e sem "urgente";
    - os itens sem envio para avaliar (empresa sem carga, com pendência ou em andamento) vêm sem "envio_id": não têm
      prazo, e o filtro os mostra só em "Todos".
Estes testes travam essa regra do servidor (services/portal_do_banco.py, _fila_do_dia, com o prazo de
services/avaliacao_do_banco.py), para o filtro nunca pôr um envio no prazo errado se alguém mudar a fila.
Os dados são inventados aqui (nenhum vem de arquivo de teste).
"""
from datetime import datetime, timedelta, timezone

from services import avaliacao_do_banco, portal_do_banco


def envio_esperando_o_banco(empresa_id: str, envio_id: str, horas_desde_o_envio: float) -> dict:
    """Um envio no formato da fila da aba Envios, mandado ao banco há tantas horas (o prazo vem da regra de verdade).

    Recebe: o código da empresa; o código do envio; quantas horas se passaram desde o envio ao banco.
    Devolve: {id, empresa_id, empresa, tipo, prazo}. Ex.: 30 horas → o prazo "Passou do prazo de 1 dia útil".
    """
    enviado_em = (datetime.now(timezone.utc) - timedelta(hours=horas_desde_o_envio)).isoformat()
    return {"id": envio_id, "empresa_id": empresa_id, "empresa": "Empresa " + empresa_id, "tipo": "Inclusão",
            "prazo": avaliacao_do_banco._prazo(enviado_em)}


def linha_da_carteira(empresa_id: str, envios: int, com_pendencia: int, em_andamento: int) -> dict:
    """Uma linha da carteira só com o que a fila usa: o código, o nome e as contagens de envios."""
    return {"id": empresa_id, "nome": "Empresa " + empresa_id, "envios": envios, "com_pendencia": com_pendencia,
            "em_andamento": em_andamento}


def itens_por_envio(fila: list[dict]) -> dict:
    """Os itens da fila que têm envio para avaliar, pelo código do envio: {envio_id: item}."""
    por_envio = {}
    for item in fila:
        if item.get("envio_id"):
            por_envio[item["envio_id"]] = item
    return por_envio


def test_envio_que_passou_do_prazo_vem_urgente_e_o_que_esta_no_prazo_nao():
    """O filtro "Passou do prazo" usa o "urgente" do envio; "Dentro do prazo", o envio sem "urgente"."""
    atrasado = envio_esperando_o_banco("EMP901", "ENVIO-ATRASADO", horas_desde_o_envio=30)
    no_prazo = envio_esperando_o_banco("EMP902", "ENVIO-NO-PRAZO", horas_desde_o_envio=2)
    por_envio = itens_por_envio(portal_do_banco._fila_do_dia([], [atrasado, no_prazo]))
    # O atrasado: urgente, e o detalhe diz o nome que a tela mostra
    assert por_envio["ENVIO-ATRASADO"]["urgente"] is True
    assert "Passou do prazo de 1 dia útil" in por_envio["ENVIO-ATRASADO"]["detalhe"]
    # O que está no prazo: sem urgente, e o detalhe diz "Dentro do prazo"
    assert por_envio["ENVIO-NO-PRAZO"]["urgente"] is False
    assert "Dentro do prazo de 1 dia útil" in por_envio["ENVIO-NO-PRAZO"]["detalhe"]
    # Cada envio traz o código da empresa (o filtro por empresa usa esse código)
    assert por_envio["ENVIO-ATRASADO"]["empresa_id"] == "EMP901"
    assert por_envio["ENVIO-NO-PRAZO"]["empresa_id"] == "EMP902"


def test_a_virada_do_prazo_fica_nas_24_horas():
    """Perto da virada: meia hora antes das 24 horas ainda está no prazo; meia hora depois, passou."""
    quase_la = envio_esperando_o_banco("EMP903", "ENVIO-23H30", horas_desde_o_envio=23.5)
    passou = envio_esperando_o_banco("EMP903", "ENVIO-24H30", horas_desde_o_envio=24.5)
    por_envio = itens_por_envio(portal_do_banco._fila_do_dia([], [quase_la, passou]))
    assert por_envio["ENVIO-23H30"]["urgente"] is False
    assert por_envio["ENVIO-24H30"]["urgente"] is True


def test_itens_sem_envio_para_avaliar_nao_tem_prazo():
    """Empresa sem carga, com pendência ou em andamento: nenhum envio para avaliar, e por isso nenhum "envio_id" (o
    filtro mostra esses itens só em "Todos"). A empresa sem carga continua urgente (a faixa laranja da fila)."""
    linhas = [linha_da_carteira("EMP911", envios=0, com_pendencia=0, em_andamento=0),
              linha_da_carteira("EMP912", envios=2, com_pendencia=1, em_andamento=0),
              linha_da_carteira("EMP913", envios=3, com_pendencia=0, em_andamento=1)]
    fila = portal_do_banco._fila_do_dia(linhas, [])
    assert len(fila) == 3
    # Nenhum deles tem envio para avaliar, e cada um traz a empresa dele
    empresas_da_fila = []
    for item in fila:
        assert not item.get("envio_id")
        empresas_da_fila.append(item["empresa_id"])
    assert empresas_da_fila == ["EMP911", "EMP912", "EMP913"]
    # Só a empresa sem carga é urgente
    assert fila[0]["urgente"] is True and fila[1]["urgente"] is False and fila[2]["urgente"] is False


def test_os_envios_vem_antes_das_empresas_na_fila():
    """A ordem que o filtro mantém: primeiro os envios que esperam o banco, depois as empresas."""
    linhas = [linha_da_carteira("EMP921", envios=0, com_pendencia=0, em_andamento=0)]
    envio = envio_esperando_o_banco("EMP922", "ENVIO-PRIMEIRO", horas_desde_o_envio=1)
    fila = portal_do_banco._fila_do_dia(linhas, [envio])
    assert fila[0]["envio_id"] == "ENVIO-PRIMEIRO"
    assert fila[1]["empresa_id"] == "EMP921" and not fila[1].get("envio_id")
