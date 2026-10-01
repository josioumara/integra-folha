"""A prova de generalização (EXP-017): as contas da análise e o conjunto novo de texto corrido difícil.

O que se prova aqui:
    - o intervalo de Wilson e o teste exato de Fisher dão os valores conhecidos (conferidos à mão);
    - o estrato de cada arquivo sai pela extensão e pelo nível, e "exato" é uma linha por pessoa, todas certas;
    - um grupo sem arquivos (os antigos não tinham texto corrido alto) vira "nenhum arquivo", e não um erro;
    - o conjunto texto_dificil tem 24 documentos (6 estruturas × 4), de 3 a 5 pessoas, cada pessoa aparece com o nome
      inteiro no documento, e só a estrutura de dependentes tem terceiros;
    - o conjunto e a régua do Leitor estão na foto congelada, e a foto confere.
Nenhum teste chama a IA.
"""
import json

import pytest
from docx import Document

from eval import congelamento
from scripts import avaliar_generalizacao, gerar_texto_corrido_dificil
from scripts.gerar_documentos_de_teste import RAIZ, pasta_do_conjunto

# A pasta do conjunto novo
PASTA = pasta_do_conjunto("texto_dificil")


def test_wilson_e_fisher_dao_os_valores_conhecidos():
    # Wilson 95%: 10/10 → 72% a 100%; 0/7 → 0% a 35%; 18/26 → 50% a 83%
    for acertos, total, esperado in ((10, 10, (0.722, 1.0)), (0, 7, (0.0, 0.354)), (18, 26, (0.500, 0.834))):
        baixo, alto = avaliar_generalizacao.intervalo_de_wilson(acertos, total)
        assert baixo == pytest.approx(esperado[0], abs=0.002) and alto == pytest.approx(esperado[1], abs=0.002)
    # Sem casos, sem taxa
    assert avaliar_generalizacao.intervalo_de_wilson(0, 0) == (0.0, 0.0)
    # Fisher bilateral: 10/10 × 18/26 → 0,076; grupos iguais → 1; 10/10 × 0/10 → quase 0
    assert avaliar_generalizacao.teste_exato_de_fisher(10, 10, 18, 26) == pytest.approx(0.0757, abs=0.001)
    assert avaliar_generalizacao.teste_exato_de_fisher(5, 10, 5, 10) == pytest.approx(1.0)
    assert avaliar_generalizacao.teste_exato_de_fisher(10, 10, 0, 10) < 0.001


def test_estrato_e_exato():
    casos = {"por_nivel/alto/007.csv": "tabela", "lote_guardado/por_nivel/baixo/002.xlsx": "tabela",
             "lote_guardado/por_nivel/altissimo/016.txt": "texto_alto", "por_nivel/alto/069.docx": "texto_alto",
             "por_nivel/medio/036.docx": "texto_baixo_medio", "suite_300/05/130.txt": "texto_baixo_medio"}
    for arquivo, estrato in casos.items():
        assert avaliar_generalizacao.estrato_do_arquivo(arquivo) == estrato, arquivo
    # Exato: uma linha por pessoa e todas certas; linha a mais ou pessoa errada não é exato
    assert avaliar_generalizacao.arquivo_exato({"linhas_na_lista": 3, "pessoas_esperadas": 3, "pessoas_certas": 3})
    assert not avaliar_generalizacao.arquivo_exato({"linhas_na_lista": 4, "pessoas_esperadas": 3, "pessoas_certas": 3})
    assert not avaliar_generalizacao.arquivo_exato({"linhas_na_lista": 3, "pessoas_esperadas": 3, "pessoas_certas": 2})


def test_grupo_sem_arquivos_vira_nenhum_arquivo():
    vazio = avaliar_generalizacao.resumir([])
    assert avaliar_generalizacao.texto_da_taxa(vazio) == "nenhum arquivo"
    cheio = avaliar_generalizacao.resumir([{"exato": True, "pessoas_certas": 3, "pessoas_esperadas": 3,
                                            "linhas_a_mais": 0, "custo_usd": 0.1}])
    assert avaliar_generalizacao.texto_da_taxa(cheio).startswith("1/1 (100%")
    # Custo não medido fica None ("não medido"), e não vira zero (ADR-36); medido e não medido somam só o medido
    sem_custo = {"exato": False, "pessoas_certas": 1, "pessoas_esperadas": 2, "linhas_a_mais": 1, "custo_usd": None}
    assert avaliar_generalizacao.resumir([sem_custo])["custo_usd"] is None
    assert avaliar_generalizacao.resumir([sem_custo, {**sem_custo, "custo_usd": 0.05}])["custo_usd"] == 0.05


def test_o_conjunto_bate_com_o_gabarito():
    gabarito = json.loads((PASTA / "gabarito.json").read_text(encoding="utf-8"))
    documentos = gabarito["documentos"]
    assert len(documentos) == 24
    estruturas = {}
    for documento in documentos:
        estruturas[documento["estrutura"]] = estruturas.get(documento["estrutura"], 0) + 1
        assert 3 <= len(documento["pessoas"]) <= 5
        # Cada pessoa do gabarito aparece com o nome inteiro no documento (na identificação)
        paragrafos = []
        for paragrafo in Document(PASTA / documento["arquivo"]).paragraphs:
            paragrafos.append(paragrafo.text)
        texto = "\n".join(paragrafos)
        for pessoa in documento["pessoas"]:
            assert pessoa["campos"]["nome_completo"] in texto or pessoa["campos"]["nome_completo"].upper() in texto
            # Os terceiros (dependentes) só existem na estrutura de dependentes
            if documento["estrutura"] == "dependentes":
                assert pessoa["terceiros"] and pessoa["terceiros"][0]["nome"] in texto
            else:
                assert pessoa["terceiros"] == []
    assert estruturas == {"nome_curto": 4, "apelido": 4, "ordem_trocada": 4, "referencia_por_cpf": 4,
                          "cpf_repetido": 4, "dependentes": 4}


def test_o_gerador_padrao_reproduz_o_conjunto_congelado(tmp_path):
    # Sem opções, o gerador faz o mesmo gabarito que está congelado (a refatoração não mudou o sorteio)
    gerado = gerar_texto_corrido_dificil.gerar(tmp_path)
    congelado = json.loads((PASTA / "gabarito.json").read_text(encoding="utf-8"))
    assert gerado == congelado


def test_o_manifesto_acusa_arquivo_mudado_faltando_ou_sobrando(tmp_path):
    # Uma pasta pequena, com outra semente (qualquer uma serve para testar o manifesto)
    gerar_texto_corrido_dificil.gerar(tmp_path, semente=7, conjunto="teste")
    manifesto = gerar_texto_corrido_dificil.manifesto_da_pasta(tmp_path, "teste")
    # O manifesto nunca guarda a semente (com ela, o conjunto guardado poderia ser regerado)
    assert "semente" not in manifesto and len(manifesto["arquivos"]) == 25
    assert gerar_texto_corrido_dificil.diferencas_do_manifesto(tmp_path, manifesto) == []
    # Três variações: um arquivo alterado, um apagado e um a mais
    (tmp_path / "gabarito.json").write_text("{}", encoding="utf-8")
    (tmp_path / "N6_apelido_1.docx").unlink()
    (tmp_path / "rascunho.txt").write_text("x", encoding="utf-8")
    diferencas = gerar_texto_corrido_dificil.diferencas_do_manifesto(tmp_path, manifesto)
    assert set(diferencas) == {"alterado: gabarito.json", "faltando: N6_apelido_1.docx", "sobrando: rascunho.txt"}


def test_a_reserva_nunca_grava_no_repositorio(tmp_path):
    padrao = gerar_texto_corrido_dificil.SEMENTE
    # A semente de sempre, sem pasta: a pasta do conjunto congelado
    assert gerar_texto_corrido_dificil.conferir_destino(padrao, "") == PASTA
    # Outra semente sem pasta: recusada (gravaria por cima do conjunto congelado)
    with pytest.raises(ValueError):
        gerar_texto_corrido_dificil.conferir_destino(padrao + 1, "")
    # Outra semente dentro do repositório (três variações de lugar): recusada
    for dentro in (str(RAIZ), str(RAIZ / "data" / "avaliacao" / "reserva"), str(RAIZ / "tests" / "x")):
        with pytest.raises(ValueError):
            gerar_texto_corrido_dificil.conferir_destino(padrao + 1, dentro)
    # Dentro de OUTRO repositório (ex.: o principal, rodando de uma cópia isolada): também recusada
    outro_repositorio = tmp_path / "outro_repositorio"
    (outro_repositorio / ".git").mkdir(parents=True)
    with pytest.raises(ValueError):
        gerar_texto_corrido_dificil.conferir_destino(padrao + 1, str(outro_repositorio / "data" / "reserva"))
    # Outra semente fora do repositório: aceita
    assert gerar_texto_corrido_dificil.conferir_destino(padrao + 1, str(tmp_path)) == tmp_path.resolve()


def test_os_manifestos_da_reserva_e_do_fora_da_distribuicao_estao_na_foto_sem_a_semente():
    # A reserva (24 documentos + gabarito) e o conjunto fora da distribuição (12 + gabarito), ambos fora do Git
    for arquivo, conjunto, quantos in (("reserva_d39_manifesto.json", "texto_dificil_reserva", 25),
                                       ("fora_da_distribuicao_d39_manifesto.json", "texto_fora_da_distribuicao", 13)):
        manifesto = json.loads((RAIZ / "data" / "avaliacao" / arquivo).read_text(encoding="utf-8"))
        assert manifesto["conjunto"] == conjunto and "semente" not in manifesto, arquivo
        assert len(manifesto["arquivos"]) == quantos, arquivo
        assert f"data/avaliacao/{arquivo}" in congelamento.arquivos_da_prova(), arquivo


def test_o_conjunto_e_a_regua_estao_congelados():
    arquivos = congelamento.arquivos_da_prova()
    assert "data/avaliacao/documentos_texto_dificil/gabarito.json" in arquivos
    assert "eval/avaliacao_do_leitor.py" in arquivos and "scripts/avaliar_leitor.py" in arquivos
    # 24 documentos + o gabarito
    do_conjunto = 0
    for caminho in arquivos:
        if "documentos_texto_dificil" in caminho:
            do_conjunto += 1
    assert do_conjunto == 25
    # E a foto confere com os arquivos de agora
    assert congelamento.conferir() == []
