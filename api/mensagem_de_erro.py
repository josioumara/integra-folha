"""A mensagem de erro que pode ir para a tela: a escrita pelo projeto, ou uma frase geral (achados B-15 e C-24).

Para que serve: as regras do projeto recusam um pedido levantando um ValueError com uma frase escrita para a pessoa
("A senha atual não confere."). As rotas da API transformam esse erro numa resposta 400 com a frase. O problema: o
próprio Python também levanta ValueError, em inglês e com detalhe técnico ("invalid literal for int()", "month must
be in 1..12"), e essa frase ia parar na tela, revelando como o sistema é feito por dentro.

Este arquivo separa os dois casos. Ele é usado pelas três partes da API que traduzem erros (api/principal.py,
api/rotas_kbs_endomarketing.py e api/rotas_faixas_cbo.py), por isso fica num arquivo só dele.
"""
import logging
import os
import traceback
from pathlib import Path

# O registro de avisos (aparece no terminal do servidor): o detalhe técnico fica aqui, nunca na tela
registro_de_avisos = logging.getLogger(__name__)
# A frase de quando um dado chega fora do formato e o erro vem de dentro do Python (e não de uma regra nossa)
MENSAGEM_DE_DADO_FORA_DO_FORMATO = "Um dos dados enviados não está no formato esperado. Confira e tente de novo."
# A pasta do projeto, no jeito de escrever do sistema. O Windows não diferencia maiúsculas: "D:\AI_Payroll_Hub" e
# "D:\AI_PAYROLL_HUB" são a mesma pasta, e o normcase deixa as duas iguais para a comparação
PASTA_DO_PROJETO = os.path.normcase(str(Path(__file__).resolve().parent.parent))
# A pasta das bibliotecas instaladas fica dentro do projeto, mas o que nasce lá não foi escrito por nós
PASTA_DAS_BIBLIOTECAS = os.path.normcase(".venv")


def mensagem_para_a_pessoa(erro: ValueError) -> str:
    """A frase do erro, se ela foi escrita pelo projeto; senão, a frase geral em português.

    Recebe: o erro (um ValueError ou uma "filha" dele, como o ArquivoRecusado). Devolve: o texto para a tela.
    Como separa: o erro escrito por nós nasce numa linha "raise ..." de um arquivo do projeto. O erro do Python nasce
    dentro de uma biblioteca, ou numa linha nossa que só chamou a função (ex.: "numero = int(texto)").
    Exemplos: raise ValueError("A nova senha precisa ser diferente da atual.") → a própria frase;
    int("²") → "Um dos dados enviados não está no formato esperado. Confira e tente de novo."
    Dois pontos cegos conhecidos (por ora, nenhum aparece no código):
    - "if condicao: raise ValueError(...)" numa linha só não começa com "raise": a nossa frase vira a geral. Escreva o
      raise na linha de baixo;
    - reembrulhar o erro do Python com a mensagem dele (raise ValueError(f"... {erro}")) deixa o texto técnico passar,
      porque a linha é um raise nosso. Escreva a frase sem o texto do erro original.
    """
    # O último passo do caminho do erro: o arquivo e a linha onde ele nasceu
    onde_nasceu = traceback.extract_tb(erro.__traceback__)[-1]
    # O arquivo onde nasceu, no mesmo jeito de escrever da pasta do projeto
    arquivo_onde_nasceu = os.path.normcase(onde_nasceu.filename)
    # Nasceu num arquivo do projeto, fora das bibliotecas instaladas?
    dentro_do_projeto = arquivo_onde_nasceu.startswith(PASTA_DO_PROJETO)
    nasceu_no_projeto = dentro_do_projeto and PASTA_DAS_BIBLIOTECAS not in arquivo_onde_nasceu
    # A linha onde nasceu é um "raise" (o erro foi levantado de propósito, com a nossa frase)?
    linha_e_um_raise = (onde_nasceu.line or "").strip().startswith("raise")
    # Os dois: a frase é nossa e pode ir para a tela
    if nasceu_no_projeto and linha_e_um_raise:
        return str(erro)
    # Nasceu dentro do Python ou de uma biblioteca: o detalhe fica no registro do servidor; a pessoa lê a frase geral
    registro_de_avisos.warning("Erro de formato vindo do Python: %s", erro)
    return MENSAGEM_DE_DADO_FORA_DO_FORMATO
