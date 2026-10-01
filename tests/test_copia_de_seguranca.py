"""A cópia de segurança do projeto (o .env fica de fora, ADR-79).

O que estes testes provam:
- o .env (segredos), os ambientes virtuais, os modelos baixados e os índices ficam de fora; o .env.example vai;
- a cópia cria uma pasta com data e hora e leva o resto da árvore;
- a simulação conta sem copiar nada.
"""
from datetime import datetime

from scripts import copia_de_seguranca


def test_o_que_fica_de_fora():
    assert copia_de_seguranca.fica_de_fora(".env", e_pasta=False)
    assert not copia_de_seguranca.fica_de_fora(".env.example", e_pasta=False)
    assert copia_de_seguranca.fica_de_fora(".venv", e_pasta=True)
    assert copia_de_seguranca.fica_de_fora("modelos", e_pasta=True)
    assert not copia_de_seguranca.fica_de_fora("front", e_pasta=True)


def test_copia_com_data_sem_os_segredos(tmp_path):
    # Uma árvore de mentira, com um .env, um .venv e o resto
    origem = tmp_path / "AI_Payroll_Hub"
    (origem / "integra-folha" / ".venv").mkdir(parents=True)
    (origem / "integra-folha" / ".venv" / "pesado.bin").write_bytes(b"x" * 10)
    (origem / "integra-folha" / ".env").write_text("ANTHROPIC_API_KEY=segredo", encoding="utf-8")
    (origem / "integra-folha" / ".env.example").write_text("ANTHROPIC_API_KEY=", encoding="utf-8")
    (origem / "Apresentacao").mkdir()
    (origem / "Apresentacao" / "deck.pptx").write_bytes(b"deck")
    # A simulação conta 2 arquivos (o .env.example e o deck), sem copiar nada
    assert copia_de_seguranca.contar(origem)[0] == 2
    pasta = copia_de_seguranca.fazer_copia(origem, tmp_path / "copias", datetime(2026, 9, 26, 7, 30))
    assert pasta.name == "20260926_0730"
    copiado = pasta / "AI_Payroll_Hub"
    assert (copiado / "Apresentacao" / "deck.pptx").exists()
    assert (copiado / "integra-folha" / ".env.example").exists()
    assert not (copiado / "integra-folha" / ".env").exists()
    assert not (copiado / "integra-folha" / ".venv").exists()
