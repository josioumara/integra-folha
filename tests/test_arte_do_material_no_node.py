"""Roda no Node os testes do desenho da arte do endomarketing, para eles entrarem na bateria do pytest.

Para que serve: a arte do endomarketing é desenhada no navegador, em JavaScript (front/js/arte_do_material.js). Os
testes dela (tests/front/arte_do_material.test.mjs) rodam no Node, com o executor de testes que já vem com ele
(node --test), sem instalar nada. Este arquivo só chama o Node e confere que todos passaram: o molde de cada canal
no tamanho certo, a arte sem o nome do canal entre parênteses e todo texto dentro da imagem.
Se a máquina não tiver o Node, o teste é pulado e diz por quê.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

# O arquivo dos testes da arte, que roda no Node
TESTES_DA_ARTE_NO_NODE = Path(__file__).parent / "front" / "arte_do_material.test.mjs"
# Quanto esperar o Node terminar (em segundos): os testes levam menos de 1 segundo
TEMPO_MAXIMO = 120


def test_desenho_da_arte_passa_nos_testes_do_node():
    """O molde de cada canal, o texto sem o canal e todo texto dentro da arte: os testes do Node passam."""
    # Procura o Node no caminho da máquina
    executavel_do_node = shutil.which("node")
    if executavel_do_node is None:
        pytest.skip("O Node não está instalado nesta máquina: os testes da arte no Node não rodaram.")
    # Roda os testes; o Node devolve o código 0 quando todos passam
    resultado = subprocess.run([executavel_do_node, "--test", str(TESTES_DA_ARTE_NO_NODE)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=TEMPO_MAXIMO)
    # Se algum falhou, a saída do Node vai junto, para mostrar qual
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
