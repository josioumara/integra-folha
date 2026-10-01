"""O índice do conhecimento do layout: refeito sozinho quando o banco grava uma versão nova dos parâmetros (ADR-76).

Para que serve: a IA que lê as colunas (Interpretador) busca no índice os textos de cada campo do layout (descrição,
regra, "não confundir com"), as regras de validação e os mapeamentos homologados. Quando o banco muda o layout na tela
"Parâmetros", o índice precisa mudar junto: a gravação dispara a reconstrução na hora, em segundo plano, sem
precisar rodar scripts/build_index.py na mão. A tela responde logo e, poucos segundos depois, a IA já
busca nos textos novos.

Se a reconstrução falhar (ex.: o modelo de embeddings não está na máquina), o índice antigo continua valendo (ele só
é trocado depois de os vetores novos ficarem prontos, ADR-63) e o aviso vai para o registro do servidor.
"""
import logging
import threading

from rag import busca
from rag.trechos import trechos_historico, trechos_layout, trechos_regras
from services import config

# As fontes que vêm de arquivo
CAMINHO_REGRAS = config.RAIZ / "data" / "contratos" / "regras_v1.json"
CAMINHO_HISTORICO = config.RAIZ / "data" / "synthetic" / "historico_mapeamentos.csv"

# Onde os avisos da reconstrução aparecem (o registro do servidor)
registro_de_avisos = logging.getLogger(__name__)


def trechos_do_layout(versao: int, campos: list) -> list:
    """Os trechos do índice do layout: um por campo, as regras de validação e os mapeamentos homologados."""
    # A descrição de cada campo enriquece a busca dos mapeamentos homologados
    descricoes = {}
    for campo in campos:
        descricoes[campo.campo] = campo.descricao
    return trechos_layout(versao, campos) + trechos_regras(CAMINHO_REGRAS) + trechos_historico(CAMINHO_HISTORICO,
                                                                                               descricoes)


def refazer(versao: int, campos: list, pasta=None) -> int:
    """Refaz o índice do layout do zero com a versão informada. Devolve quantos trechos entraram."""
    return busca.gravar_colecao(busca.COLECAO_LAYOUT, trechos_do_layout(versao, campos), pasta)


def _refazer_sem_quebrar(versao: int, campos: list) -> None:
    """Refaz o índice; qualquer falha vira aviso no registro do servidor (o índice antigo continua valendo)."""
    try:
        quantidade = refazer(versao, campos)
        registro_de_avisos.info("Índice do layout refeito com a versão %s (%s trechos).", versao, quantidade)
    except Exception as erro:  # qualquer falha do índice: a versão do layout vale do mesmo jeito
        registro_de_avisos.warning("Índice do layout não foi refeito: %s", erro)


def refazer_em_segundo_plano(versao: int, campos: list) -> bool:
    """Começa a refazer o índice agora, sem a tela esperar. Devolve True se começou.

    Só com os índices vivos ligados (o mesmo interruptor da memória que aprende, busca.ligar_mapeamentos_aprovados):
    a API liga; testes e avaliações não, e o índice de verdade não é tocado por eles.
    "Thread" é uma linha de trabalho que corre ao lado da principal: a resposta da tela não espera por ela.
    """
    if not busca.mapeamentos_aprovados_ligados():
        return False
    trabalho = threading.Thread(target=_refazer_sem_quebrar, args=(versao, campos), daemon=True)
    trabalho.start()
    return True
