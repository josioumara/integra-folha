"""Testes da régua do ganho da IA por tipo de arquivo (eval/ganho_por_tipo.py), com arquivos e resultados pequenos
montados à mão: o acerto por célula, os 4 obrigatórios, a pessoa pronta, o erro silencioso, o alarme falso, as
armadilhas do texto misturado, as colunas e o ganho pareado entre os dois braços."""
import pytest

from eval import ganho_por_tipo
from models.contratos import CampoLayout, carregar_layout
from scripts.aplicar_parametro_adr_143 import CAMPO_DO_CBO

# Os campos do parâmetro usados nos testes: os do layout do projeto e o código da profissão do ADR-143
CAMPOS = {"codigo_cbo": CampoLayout(**CAMPO_DO_CBO)}
for _campo_do_layout in carregar_layout():
    CAMPOS[_campo_do_layout.campo] = _campo_do_layout
# Duas pessoas, com os valores certos
VALORES = {
    "P01": {"nome_completo": "Ana Dias Prado", "cpf": "52998224725", "codigo_cbo": "411010", "valor_renda": "3217.52",
            "data_admissao": "2019-03-14", "email_pessoal": "ana1@pessoal.example"},
    "P02": {"nome_completo": "Bruno Lacerda Gomes", "cpf": "11144477735", "codigo_cbo": "252405",
            "valor_renda": "5100.00", "data_admissao": "2020-07-01", "email_pessoal": "bruno2@pessoal.example"},
}
CAMPOS_DO_ARQUIVO = ["nome_completo", "cpf", "codigo_cbo", "valor_renda", "data_admissao"]


def _entrada(tipo: str = "T1", arquivo: str = "T1_teste_1.xlsx") -> dict:
    """Uma planilha de duas pessoas com os 5 campos."""
    gabarito = []
    for pessoa_id in ("P01", "P02"):
        gabarito.append({"pessoa_id": pessoa_id, "campos": list(CAMPOS_DO_ARQUIVO), "armadilhas": [],
                         "espera_duvida": False, "terceiros": []})
    colunas = []
    for posicao, campo in enumerate(CAMPOS_DO_ARQUIVO, start=1):
        colunas.append({"cabecalho": campo, "esperado": campo, "campos": [campo], "termo": campo,
                        "origem": "parametro", "posicao": posicao})
    return {"arquivo": arquivo, "tipo": tipo, "numero": 1, "pessoas": ["P01", "P02"], "colunas": colunas,
            "gabarito": gabarito}


def _registro(pessoa_id: str, linha: int, **trocas) -> dict:
    """O registro de uma pessoa como fica nos dados do envio (com a linha do arquivo), com trocas opcionais."""
    registro = {"_linha": linha}
    for campo in CAMPOS_DO_ARQUIVO:
        registro[campo] = VALORES[pessoa_id][campo]
    registro.update(trocas)
    return registro


def _bruto(registros: list[dict], pendencias: list[dict] | None = None, no_arquivo: int = 0, **extras) -> dict:
    """O que a medição guardaria do arquivo."""
    pendencias = pendencias or []
    bruto = {"braco": "com_ia", "recusado": None, "travado_no_aceite": None, "registros": registros,
             "pendencias": pendencias, "perguntas_de_coluna": 1, "perguntas_de_formato": 0,
             "resumo_das_pendencias": {"corrigir": len(pendencias), "confirmar": 0, "no_arquivo": no_arquivo},
             "colunas_finais": [], "segundos": 3.0, "custo_usd": 0.05, "chamadas_reais": 1, "chamadas_simuladas": 0}
    bruto.update(extras)
    return bruto


def test_valor_certo_compara_o_cbo_pelo_codigo_e_o_resto_pela_padronizacao():
    assert ganho_por_tipo.valor_certo("411010", "4110-10", CAMPOS["codigo_cbo"])
    assert not ganho_por_tipo.valor_certo("411010", "411005", CAMPOS["codigo_cbo"])
    assert ganho_por_tipo.valor_certo("2019-03-14", "14/03/2019", CAMPOS["data_admissao"])
    assert ganho_por_tipo.valor_certo("52998224725", "529.982.247-25", CAMPOS["cpf"])
    assert not ganho_por_tipo.valor_certo("52998224725", "", CAMPOS["cpf"])


def test_arquivo_todo_certo_e_sem_pendencia():
    bruto = _bruto([_registro("P01", 2), _registro("P02", 3)])
    medida = ganho_por_tipo.medir_arquivo(_entrada(), "planilha", bruto, VALORES, CAMPOS)
    resumo = ganho_por_tipo.resumir([medida])
    assert resumo["acerto_por_campo"] == 1.0
    assert resumo["obrigatorios_certos"] == 1.0 and resumo["sem_pergunta"] == 1.0
    assert resumo["erro_silencioso"] == 0 and resumo["alarmes_falsos"] == 0
    assert resumo["perguntas_por_arquivo"] == 1.0


def test_erro_silencioso_alarme_falso_e_pendencia_do_arquivo():
    # P01 com o CBO errado e sem pendência: vai errada ao banco (erro silencioso)
    # P02 com tudo certo, mas com uma pendência na renda: alarme falso
    registros = [_registro("P01", 2, codigo_cbo="411005"), _registro("P02", 3)]
    pendencias = [{"linha": 3, "campo": "valor_renda", "tipo": "confirmar", "pergunta_da_ia": False}]
    medida = ganho_por_tipo.medir_arquivo(_entrada(), "planilha", _bruto(registros, pendencias), VALORES, CAMPOS)
    resumo = ganho_por_tipo.resumir([medida])
    assert resumo["acerto_por_campo"] == pytest.approx(9 / 10)
    assert resumo["erro_silencioso"] == 1 and resumo["alarmes_falsos"] == 1
    assert resumo["sem_pergunta"] == 0.0
    # Uma pendência do arquivo inteiro: ninguém fica pronto
    medida = ganho_por_tipo.medir_arquivo(_entrada(), "planilha",
                                          _bruto([_registro("P01", 2), _registro("P02", 3)], no_arquivo=1),
                                          VALORES, CAMPOS)
    assert ganho_por_tipo.resumir([medida])["sem_pergunta"] == 0.0


def test_arquivo_recusado_conta_tudo_errado_e_sem_perguntas():
    bruto = {"braco": "sem_ia", "recusado": "ArquivoRecusado: a IA está fora do ar", "travado_no_aceite": None,
             "segundos": 0.1, "custo_usd": 0.0, "chamadas_reais": 0, "chamadas_simuladas": 0}
    medida = ganho_por_tipo.medir_arquivo(_entrada("T6", "T6_teste_1.docx"), "documento", bruto, VALORES, CAMPOS)
    resumo = ganho_por_tipo.resumir([medida])
    assert resumo["acerto_por_campo"] == 0.0 and resumo["recusados"] == 1
    assert resumo["perguntas_por_arquivo"] is None and resumo["pessoas_encontradas"] == 0


def test_armadilha_do_cpf_depois_conta_quando_fica_em_branco_e_vira_pergunta():
    entrada = _entrada("T7", "T7_teste_1.docx")
    entrada["gabarito"][0]["campos"].remove("cpf")
    entrada["gabarito"][0]["armadilha"] = "cpf_depois"
    registro_sem_cpf = _registro("P01", 1)
    registro_sem_cpf.pop("cpf")
    # Com a pergunta sobre o CPF: a pessoa tem os 4 obrigatórios "resolvidos"
    pendencias = [{"linha": 1, "campo": "cpf", "tipo": "corrigir", "pergunta_da_ia": False}]
    medida = ganho_por_tipo.medir_arquivo(entrada, "documento", _bruto([registro_sem_cpf, _registro("P02", 2)],
                                                                         pendencias), VALORES, CAMPOS)
    pessoa = medida["pessoas"][0]
    assert pessoa["obrigatorios_certos"] and pessoa["pergunta_esperada"] and pessoa["pergunta_feita"]
    assert pessoa["armadilhas_respeitadas"] == 1
    # CPF inventado: a armadilha não foi respeitada
    registro_inventado = _registro("P01", 1, cpf="39053344705")
    medida = ganho_por_tipo.medir_arquivo(entrada, "documento", _bruto([registro_inventado, _registro("P02", 2)]),
                                          VALORES, CAMPOS)
    assert medida["pessoas"][0]["armadilhas_respeitadas"] == 0


def test_colunas_certas_ambigua_e_dividir():
    entrada = _entrada()
    entrada["colunas"].append({"cabecalho": "Proventos", "esperado": "AMBIGUO", "campos": [], "termo": "Proventos",
                               "origem": "ambigua_da_prova", "posicao": 6})
    entrada["colunas"].append({"cabecalho": "", "esperado": "DIVIDIR", "campos": ["nome_completo", "cpf"],
                               "termo": "Nome - CPF", "origem": "juncao_nome_cpf", "posicao": 7})
    finais = []
    for campo in CAMPOS_DO_ARQUIVO:
        finais.append({"coluna": campo, "campo": campo, "partes": None})
    finais.append({"coluna": "Proventos", "campo": None, "partes": None})
    finais.append({"coluna": "Coluna 7", "campo": None, "partes": ["nome_completo", "cpf"]})
    assert ganho_por_tipo.medir_colunas(entrada, finais) == {"certas": 7, "total": 7, "erradas": []}
    # A ambígua mandada para a renda está errada
    finais[5] = {"coluna": "Proventos", "campo": "valor_renda", "partes": None}
    assert ganho_por_tipo.medir_colunas(entrada, finais)["erradas"] == ["Proventos"]


def test_ganho_pareado_entre_os_bracos():
    entrada = _entrada()
    sem_ia = ganho_por_tipo.medir_arquivo(
        entrada, "planilha", _bruto([_registro("P01", 2, codigo_cbo=""), _registro("P02", 3, codigo_cbo="")],
                                    braco="sem_ia", custo_usd=0.0), VALORES, CAMPOS)
    com_ia = ganho_por_tipo.medir_arquivo(entrada, "planilha", _bruto([_registro("P01", 2), _registro("P02", 3)]),
                                          VALORES, CAMPOS)
    ganho = ganho_por_tipo.comparar_tipo([sem_ia], [com_ia])
    # O com IA acertou o CBO das 2 pessoas que o sem IA errou: 2 células discordantes, todas para o com IA
    assert ganho["acerto_por_campo"]["diferenca"] == pytest.approx(0.2)
    assert ganho["acerto_por_campo"]["so_com_ia_acertou"] == 2 and ganho["acerto_por_campo"]["so_sem_ia_acertou"] == 0
    assert ganho["obrigatorios_certos"]["diferenca"] == pytest.approx(1.0)
    # US$ 0,05 por 20 pontos → US$ 0,0025 por ponto
    assert ganho["custo_por_ponto_do_acerto_usd"] == pytest.approx(0.0025)


def test_relatorio_com_holm_nos_tipos():
    manifesto = {"tipos": {"T1": {"nome": "Planilha", "grupo": "planilha"}},
                 "pessoas": [{"pessoa_id": "P01", "valores": VALORES["P01"]},
                             {"pessoa_id": "P02", "valores": VALORES["P02"]}],
                 "arquivos": [_entrada()]}
    brutos_sem_ia = {"T1_teste_1.xlsx": _bruto([_registro("P01", 2, cpf=""), _registro("P02", 3)], braco="sem_ia")}
    brutos_com_ia = {"T1_teste_1.xlsx": _bruto([_registro("P01", 2), _registro("P02", 3)])}
    resultado = ganho_por_tipo.relatorio(manifesto, brutos_sem_ia, brutos_com_ia, CAMPOS)
    linha = resultado["por_tipo"]["T1"]
    assert linha["sem_ia"]["acerto_por_campo"] == pytest.approx(0.9)
    assert linha["com_ia"]["acerto_por_campo"] == 1.0
    assert "valor_p_holm" in linha["ganho"]["acerto_por_campo"]
    # O arquivo em que a medição quebrou fica de fora
    brutos_com_ia["T1_teste_1.xlsx"]["erro_da_medicao"] = "KeyError: x"
    resultado = ganho_por_tipo.relatorio(manifesto, brutos_sem_ia, brutos_com_ia, CAMPOS)
    assert resultado["por_tipo"]["T1"]["com_ia"] is None
