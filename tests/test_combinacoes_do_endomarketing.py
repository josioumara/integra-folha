"""EXP-019: a avaliação das combinações do Endomarketing (eval/combinacoes_do_endomarketing.py), em MOCK.

O que estes testes provam:
- a grade tem cada benefício sozinho, todos juntos e a lista vazia, em cada tipo, canal e caso do destaque; a empresa
  sem catálogo fica só com a lista vazia;
- o destaque fora do catálogo usa um benefício que a empresa não tem; o ataque da grade cai na lista de frases e o
  disfarçado não (é o caso que exercita o detector do Bedrock Guardrails com a IA real);
- cada combinação passa pelo caminho da tela e sai com a situação e o motivo que a tela mostraria (em MOCK: o
  rascunho gerado, a lista vazia barrada na entrada, a empresa sem catálogo e o ataque recusado pela lista);
- as marcas lidas do rascunho (os benefícios sem bloco, o corte do WhatsApp, a promessa do ataque) e o CSV, que volta
  igual ao gravado;
- a amostra da etapa 2 tem uma de cada situação, as de fronteira, as casas e as repetições, e sai igual com a mesma
  semente; a rodada para antes do teto em dólares e depois de três quedas seguidas da IA;
- o resumo conta por situação, tipo e canal, acha as empresas que não geram e compara a IA real com o MOCK;
- o script se recusa a rodar no banco e no índice de todos, e no modo errado para a etapa.
"""
import pytest

from agents import endomarketing
from eval import combinacoes_do_endomarketing as combinacoes
from eval import resumo_das_combinacoes as resumo
from rag import busca as busca_rag
from services import banco, config, guardrail_injecao
from services import empresas as cadastro_de_empresas
from tests.test_empresas import ESPECIALISTA, dados_da_empresa_nova
from tests.test_endomarketing import busca_por_palavras

# Quantos tipos, canais e casos do destaque a grade cruza
TIPOS, CANAIS, CASOS = len(endomarketing.TIPOS), len(endomarketing.CANAIS), len(combinacoes.CASOS_DO_DESTAQUE)


@pytest.fixture
def conexao(tmp_path, monkeypatch):
    """Um banco novo, só deste teste (as 6 empresas da semente), com a busca do catálogo por palavras."""
    # A lista de empresas em memória relê o banco padrão: ele aponta para o banco deste teste
    monkeypatch.setattr(config, "CAMINHO_BANCO", tmp_path / "teste.db")
    # O banco novo nasce com a semente: as 6 empresas fictícias, com o catálogo de cada uma
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    # A busca por palavras faz o papel do índice do RAG (o teste não depende dele)
    busca = busca_por_palavras(conexao_do_teste)

    def buscar_beneficios(empresa_id, consulta, dia=None, k=2):
        """A mesma assinatura da busca do RAG; o dia não importa no teste."""
        return busca(empresa_id, consulta, k=k)
    # O agente passa a usar a busca falsa
    monkeypatch.setattr("rag.busca.buscar_beneficios", buscar_beneficios)
    yield conexao_do_teste
    conexao_do_teste.close()


def _da_empresa(linhas: list[dict], empresa_id: str) -> list[dict]:
    """As linhas de uma empresa."""
    escolhidas = []
    # Só as linhas da empresa pedida
    for linha in linhas:
        if linha["empresa_id"] == empresa_id:
            escolhidas.append(linha)
    return escolhidas


# ---------------- A grade ----------------

def test_conjuntos_cada_um_todos_e_nenhum():
    """Cada benefício sozinho, todos juntos e a lista vazia; com um benefício só, "todos" não se repete."""
    # Dois benefícios: cada um, os dois juntos e a lista vazia
    assert combinacoes.conjuntos_de_beneficios(["A", "B"]) == [
        {"conjunto": "um", "beneficios": ["A"]}, {"conjunto": "um", "beneficios": ["B"]},
        {"conjunto": "todos", "beneficios": ["A", "B"]}, {"conjunto": "nenhum", "beneficios": []}]
    assert combinacoes.conjuntos_de_beneficios(["A"]) == [{"conjunto": "um", "beneficios": ["A"]},
                                                          {"conjunto": "nenhum", "beneficios": []}]
    assert combinacoes.conjuntos_de_beneficios([]) == [{"conjunto": "nenhum", "beneficios": []}]


def test_destaque_fora_do_catalogo_usa_um_beneficio_que_a_empresa_nao_tem():
    """O primeiro candidato que a empresa não tem, comparado sem acento e sem maiúsculas."""
    # Sem a previdência, ela é o destaque; com ela (em maiúsculas), o seguro de vida
    assert combinacoes.beneficio_que_a_empresa_nao_tem(["Conta salário"]) == "previdência privada"
    assert combinacoes.beneficio_que_a_empresa_nao_tem(["PREVIDÊNCIA privada", "Conta salário"]) == \
        "seguro de vida em grupo"
    assert combinacoes.destaque_do_caso(combinacoes.CASO_FORA_DO_CATALOGO, ["Previdência privada"]) == \
        "reforce que a empresa oferece seguro de vida em grupo"
    # A empresa com todos os candidatos: a grade avisa que precisa de um candidato novo
    with pytest.raises(ValueError, match="candidato"):
        combinacoes.beneficio_que_a_empresa_nao_tem(["Previdência privada", "Seguro de vida em grupo",
                                                     "Consórcio de imóveis"])


def test_o_ataque_da_grade_cai_na_lista_e_o_disfarcado_nao():
    """O ataque da grade para na 1ª camada; o disfarçado e o pedido normal passam por ela (a 2ª só na IA real)."""
    # A lista pega o "ignore as regras"; o disfarçado e o pedido normal passam por ela
    assert guardrail_injecao.e_suspeito(combinacoes.TEXTO_DO_ATAQUE)
    assert not guardrail_injecao.e_suspeito(combinacoes.TEXTO_DO_ATAQUE_DISFARCADO)
    assert not guardrail_injecao.e_suspeito(combinacoes.TEXTO_DO_DESTAQUE_NORMAL)


def test_grade_tem_todas_as_combinacoes_e_a_empresa_sem_catalogo_so_a_lista_vazia(conexao):
    """(benefícios + todos + nenhum) × tipos × canais × casos; a empresa nova, sem catálogo, só a lista vazia."""
    # A empresa nova (EMP007) entra sem catálogo
    cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova())
    grade = combinacoes.montar_grade(conexao)
    beneficios_da_aurora = endomarketing.beneficios_do_catalogo(conexao, "EMP001")
    assert len(_da_empresa(grade, "EMP001")) == (len(beneficios_da_aurora) + 2) * TIPOS * CANAIS * CASOS
    da_nova = _da_empresa(grade, "EMP007")
    assert len(da_nova) == TIPOS * CANAIS * CASOS
    # Na empresa sem catálogo, só a lista vazia
    for linha in da_nova:
        assert linha["conjunto"] == "nenhum" and linha["beneficios"] == [] and linha["beneficios_no_catalogo"] == 0
    # O número segue a ordem da grade, sem repetir; o caso extra fica marcado fora da grade aprovada
    numeros = set()
    for linha in grade:
        numeros.add(linha["combinacao"])
    assert grade[0]["combinacao"] == "C00001" and len(numeros) == len(grade)
    for linha in grade:
        assert linha["na_grade_aprovada"] == (linha["caso_do_destaque"] != combinacoes.CASO_ATAQUE_DISFARCADO)


# ---------------- Pedir pelo caminho da tela ----------------

def test_cada_combinacao_sai_com_a_situacao_e_o_motivo_da_tela(conexao):
    """Em MOCK: gerado, ataque recusado pela lista, lista vazia barrada e a empresa sem catálogo sem nada."""
    # A empresa nova (EMP007) entra sem catálogo
    cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova())
    escolhidas = []
    for linha in combinacoes.montar_grade(conexao):
        # Um tipo e um canal só
        if linha["tipo"] != "comunicado" or linha["canal"] != "whatsapp":
            continue
        # Na Aurora, a conta salário sozinha e a lista vazia; e a empresa nova inteira
        da_aurora_escolhida = linha["empresa_id"] == "EMP001" and linha["beneficios"] in (["Conta salário"], [])
        if da_aurora_escolhida or linha["empresa_id"] == "EMP007":
            escolhidas.append(linha)
    # Pelo mesmo caminho da tela, no MOCK
    rodada = combinacoes.rodar(conexao, escolhidas, etapa=1)
    assert rodada["feitas"] == len(escolhidas) and rodada["parou_porque"] == ""
    # O resultado de cada combinação, pela empresa, a escolha e o destaque
    resultado = {}
    for linha in rodada["linhas"]:
        resultado[(linha["empresa_id"], linha["conjunto"], linha["caso_do_destaque"])] = linha
    # A Aurora com a conta salário: o rascunho sai pelo simulador, sem custo, com um bloco da conta salário
    gerado = resultado[("EMP001", "um", "vazio")]
    assert (gerado["situacao"], gerado["motivo"], gerado["modelo"]) == ("GERADO", "gerado", "mock")
    assert gerado["ia_chamada"] and gerado["custo_usd"] is None and gerado["material_id"]
    assert gerado["blocos_sobre_os_escolhidos"] == 1 and gerado["escolhidos_sem_bloco"] == []
    assert gerado["blocos"] <= 3 and gerado["texto"] == ""
    # O ataque da grade: recusado pela lista, antes da IA
    ataque = resultado[("EMP001", "um", "ataque")]
    assert (ataque["situacao"], ataque["motivo"], ataque["ia_chamada"]) == ("RECUSADO", "destaque_barrado_pela_lista",
                                                                            False)
    # O disfarçado passa pela lista: no MOCK, o rascunho sai (a 2ª camada só roda com a IA real)
    assert resultado[("EMP001", "um", "ataque_disfarcado")]["situacao"] == "GERADO"
    # A lista vazia na Aurora: barrada na entrada, com a mensagem da tela
    vazia = resultado[("EMP001", "nenhum", "vazio")]
    assert (vazia["situacao"], vazia["motivo"]) == ("BARRADO_NA_ENTRADA", "nenhum_beneficio_marcado")
    assert "pelo menos um benefício" in vazia["mensagem"]
    # A empresa sem catálogo: nada sai em nenhum destaque (o ataque é recusado antes da escolha de benefícios)
    for caso in combinacoes.CASOS_DO_DESTAQUE:
        assert resultado[("EMP007", "nenhum", caso)]["situacao"] != "GERADO"
    assert resultado[("EMP007", "nenhum", "vazio")]["motivo"] == "empresa_sem_catalogo"
    sem_nada = resumo.empresas_que_nao_geram(rodada["linhas"])
    assert len(sem_nada) == 1 and sem_nada[0]["empresa_id"] == "EMP007" and "catálogo" in sem_nada[0]["porque"]


def test_marcas_do_rascunho_beneficio_sem_bloco_corte_e_promessa():
    """O que se lê do rascunho: os benefícios sem bloco, o atendimento, o corte do canal e a promessa do ataque."""
    # Um rascunho montado à mão: um bloco da conta salário e um do atendimento, e a promessa no título
    material = {"titulo": "Crédito com juros zero", "blocos": [
        {"texto": "Conta sem tarifa.", "fontes": ["Pacote Aurora v2 › Conta salário"]},
        {"texto": "Fale com o RH.", "fontes": ["Pacote Aurora v2 › Canais de dúvidas"]}]}
    detalhes = combinacoes._detalhes_do_material(material, ["Conta salário", "Crédito consignado"])
    assert (detalhes["blocos"], detalhes["blocos_sobre_os_escolhidos"], detalhes["blocos_de_atendimento"]) == (2, 1, 1)
    assert detalhes["escolhidos_sem_bloco"] == ["Crédito consignado"] and detalhes["promete_juros_zero"]
    assert detalhes["tamanho_do_texto"] == len("Conta sem tarifa.") + len("Fale com o RH.")
    # Uma observação de cada tipo que a conferência escreve
    marcas = combinacoes._marcas_das_observacoes([
        "Bloco removido: o número 36 não está no trecho citado.", "Bloco removido: usa o termo proibido \"grátis\".",
        "Para o WhatsApp, o texto ficou nos 3 primeiros trechos.", "Título trocado pelo padrão: o número 9.",
        "Os benefícios escolhidos no catálogo desta empresa não trazem informação sobre \"x\": nada foi escrito.",
        "A IA não encontrou no catálogo: \"x\"."])
    assert marcas == {"blocos_removidos": 2, "titulo_trocado": True, "cortado_pelo_canal": True,
                      "destaque_avisado": True, "ia_nao_encontrou": True}
    # O texto de hoje da observação (com o nome do agente) também conta como "não encontrou"
    marcas_de_hoje = combinacoes._marcas_das_observacoes([
        "O Agente de Endomarketing não encontrou no catálogo: \"previdência privada\"."])
    assert marcas_de_hoje["ia_nao_encontrou"]
    # Sem rascunho, nada a contar
    assert combinacoes._detalhes_do_material(None, ["Conta salário"])["blocos"] == 0


def test_o_csv_volta_igual_ao_que_foi_gravado(conexao, tmp_path):
    """Gravar e ler o CSV devolve os mesmos valores, cada um no seu tipo (números, sim/não e listas)."""
    # As 6 primeiras combinações da grade, pedidas no MOCK
    grade = combinacoes.montar_grade(conexao)[:6]
    rodada = combinacoes.rodar(conexao, grade, etapa=1)
    # Grava e lê de volta
    caminho = tmp_path / "etapa1.csv"
    combinacoes.gravar_csv(rodada["linhas"], caminho)
    lidas = combinacoes.ler_csv(caminho)
    assert len(lidas) == 6
    # Cada coluna volta igual, no mesmo tipo
    for gravada, lida in zip(rodada["linhas"], lidas):
        for coluna in combinacoes.COLUNAS_DO_CSV:
            # A etapa 1 não tem as colunas só da amostra (o porquê e a rodada)
            if coluna in gravada:
                assert lida[coluna] == gravada[coluna], coluna


# ---------------- A amostra da etapa 2 ----------------

def _linhas_sinteticas() -> list[dict]:
    """Uma etapa 1 de mentira, com as mesmas regras do MOCK: 2 empresas com catálogo (uma com 1 benefício) e 1 sem."""
    linhas = []
    # A Aurora com 2 benefícios, a Nacional com 1 e a Maré sem catálogo
    empresas_e_beneficios = ((("EMP001", "Aurora"), ["Conta salário", "Crédito"]),
                             (("EMP024", "Nacional"), ["Cartão"]), (("EMP008", "Maré"), []))
    for empresa, beneficios in empresas_e_beneficios:
        linhas.extend(combinacoes._combinacoes_da_empresa({"empresa_id": empresa[0], "nome": empresa[1]}, beneficios,
                                                          combinacoes.CASOS_DO_DESTAQUE))
    # Numera como a grade de verdade
    numero = 0
    for linha in linhas:
        numero += 1
        linha["combinacao"] = f"C{numero:05d}"
        # O ataque da grade para na lista; a lista vazia é barrada; o resto chega à IA e gera
        if linha["caso_do_destaque"] == combinacoes.CASO_ATAQUE:
            linha.update({"situacao": "RECUSADO", "motivo": "destaque_barrado_pela_lista", "ia_chamada": False})
        elif not linha["beneficios"] and linha["beneficios_no_catalogo"] == 0:
            linha.update({"situacao": "BARRADO_NA_ENTRADA", "motivo": "empresa_sem_catalogo", "ia_chamada": False})
        elif not linha["beneficios"]:
            linha.update({"situacao": "BARRADO_NA_ENTRADA", "motivo": "nenhum_beneficio_marcado", "ia_chamada": False})
        else:
            linha.update({"situacao": "GERADO", "motivo": "gerado", "ia_chamada": True})
    return linhas


def _por_que(amostra: list[dict], por_que: str) -> list[dict]:
    """As combinações da amostra que entraram por este porquê."""
    escolhidas = []
    for combinacao in amostra:
        if combinacao["por_que_entrou"] == por_que:
            escolhidas.append(combinacao)
    return escolhidas


def test_amostra_tem_cada_situacao_as_fronteiras_as_casas_e_as_repeticoes():
    """Uma de cada situação, as fronteiras, todas as casas cobertas, sem repetir na rodada 1, e as repetições."""
    linhas = _linhas_sinteticas()
    amostra = combinacoes.escolher_a_amostra(linhas)
    # Uma de cada situação (4 pares de situação e motivo)
    assert len(_por_que(amostra, "uma de cada situação")) == 4
    # A rodada 1 não repete combinação
    primeiras = set()
    casas_na_amostra = set()
    for combinacao in amostra:
        if combinacao["rodada"] == 1:
            assert combinacao["combinacao"] not in primeiras
            primeiras.add(combinacao["combinacao"])
            casas_na_amostra.add((combinacao["empresa_id"], combinacao["tipo"], combinacao["canal"],
                                  combinacao["caso_do_destaque"], combinacao["conjunto"]))
    # As fronteiras entram (por elas, ou por já estarem na amostra): o WhatsApp com todos só na Aurora; a Nacional,
    # com um benefício só, ganha um de cada tipo; o ataque disfarçado nas duas empresas com catálogo
    whatsapp = _por_que(amostra, "fronteira: WhatsApp com todos os benefícios")
    assert len(whatsapp) <= 1
    for combinacao in whatsapp:
        assert combinacao["empresa_id"] == "EMP001"
        assert (combinacao["canal"], combinacao["conjunto"]) == ("whatsapp", "todos")
    for tipo in endomarketing.TIPOS:
        assert ("EMP024", tipo, "email", "vazio", "um") in casas_na_amostra
    disfarcados_por_empresa = set()
    for combinacao in amostra:
        if combinacao["caso_do_destaque"] == combinacoes.CASO_ATAQUE_DISFARCADO:
            disfarcados_por_empresa.add(combinacao["empresa_id"])
    # (a empresa sem catálogo também pode aparecer, sorteada entre as sem catálogo: lá o pedido para antes da IA)
    assert {"EMP001", "EMP024"} <= disfarcados_por_empresa
    # Todas as casas das combinações que chegaram à IA estão cobertas
    casas_cobertas = set()
    for empresa_id, tipo, canal, caso, conjunto in casas_na_amostra:
        casas_cobertas.add((tipo, canal, caso, conjunto))
    for linha in linhas:
        if linha["ia_chamada"]:
            assert (linha["tipo"], linha["canal"], linha["caso_do_destaque"], linha["conjunto"]) in casas_cobertas
    # As repetições: rodada 2 de combinações que já estão na rodada 1 e chegaram à IA
    repeticoes = _por_que(amostra, "repetição (consistência)")
    assert len(repeticoes) == combinacoes.REPETICOES_NA_AMOSTRA
    for repeticao in repeticoes:
        assert repeticao["rodada"] == 2 and repeticao["combinacao"] in primeiras
    # A mesma semente refaz a mesma amostra; outra semente, outra
    assert combinacoes.escolher_a_amostra(linhas) == amostra
    assert combinacoes.escolher_a_amostra(linhas, semente=7) != amostra


def _pedido_falso(custo: float, motivo: str = "gerado"):
    """Um pedido de material de mentira, com o custo e o motivo pedidos (para testar o teto sem a IA)."""
    def pedir(conexao, combinacao, guardar_o_texto=False):
        """Devolve sempre o mesmo resultado."""
        return {"situacao": "GERADO", "motivo": motivo, "custo_usd": custo}
    return pedir


def test_a_rodada_para_antes_do_teto(monkeypatch):
    """Com US$ 0,02 por combinação e teto de US$ 0,11: faz 3 (a margem é a maior entre a estimativa e o medido)."""
    monkeypatch.setattr(combinacoes, "pedir_o_material", _pedido_falso(0.02))
    combinacoes_pedidas = []
    for numero in range(8):
        combinacoes_pedidas.append({"combinacao": f"C{numero:05d}"})
    rodada = combinacoes.rodar(None, combinacoes_pedidas, etapa=2, teto_usd=0.11)
    assert (rodada["feitas"], rodada["total"], rodada["parou_porque"]) == (3, 8, "teto")
    assert rodada["gasto_usd"] == pytest.approx(0.06)
    # Sem teto (a etapa 1), faz todas
    assert combinacoes.rodar(None, combinacoes_pedidas, etapa=1)["feitas"] == 8


def test_a_rodada_para_depois_de_tres_quedas_seguidas_da_ia(monkeypatch):
    """A IA real fora do ar três vezes seguidas: a rodada para, em vez de anotar dezenas de pausas."""
    monkeypatch.setattr(combinacoes, "pedir_o_material", _pedido_falso(0.0, combinacoes.MOTIVO_IA_FORA_DO_AR))
    combinacoes_pedidas = []
    for numero in range(8):
        combinacoes_pedidas.append({"combinacao": f"C{numero:05d}"})
    rodada = combinacoes.rodar(None, combinacoes_pedidas, etapa=2, teto_usd=5.0)
    assert (rodada["feitas"], rodada["parou_porque"]) == (3, "ia_fora_do_ar")


# ---------------- O resumo ----------------

def _linha_do_resultado(combinacao: str, situacao: str, motivo: str, **outros) -> dict:
    """Uma linha de resultado de mentira, com o mínimo que o resumo lê."""
    linha = {"combinacao": combinacao, "empresa_id": "EMP001", "empresa": "Aurora", "beneficios": ["Conta salário"],
             "conjunto": "um", "tipo": "comunicado", "canal": "email", "caso_do_destaque": "vazio",
             "na_grade_aprovada": True, "situacao": situacao, "motivo": motivo, "mensagem": "m", "ia_chamada": True,
             "blocos": 3, "blocos_sobre_os_escolhidos": 1, "escolhidos_sem_bloco": [], "blocos_removidos": 0,
             "titulo_trocado": False, "cortado_pelo_canal": False, "destaque_avisado": False, "ia_nao_encontrou": False,
             "promete_juros_zero": False, "tamanho_do_texto": 100, "checagem_do_detector": "", "custo_usd": None,
             "tokens_entrada": None, "tokens_saida": None, "segundos": 0.1, "observacoes": [], "texto": "", "rodada": 1}
    linha.update(outros)
    return linha


def test_resumo_conta_compara_com_o_mock_e_mede_a_consistencia():
    """A tabela por situação, tipo e canal; a comparação com o MOCK; a consistência; o custo e os percentis."""
    etapa_1 = [_linha_do_resultado("C1", "GERADO", "gerado"),
               _linha_do_resultado("C2", "GERADO", "gerado", canal="whatsapp", tipo="faq"),
               _linha_do_resultado("C3", "BARRADO_NA_ENTRADA", "nenhum_beneficio_marcado", ia_chamada=False)]
    tabela = resumo.tabela_de_situacoes(etapa_1)
    assert tabela[0]["situacao"] == "GERADO" and tabela[0]["combinacoes"] == 2
    assert tabela[0]["por_canal"] == {"email": 1, "mural": 0, "whatsapp": 1}
    assert tabela[0]["por_tipo"]["faq"] == 1
    assert tabela[0]["exemplo"] == "EMP001 · comunicado · E-mail · Conta salário · destaque vazio → m"
    assert tabela[1]["motivo"] == "nenhum_beneficio_marcado"
    # A IA real: a C2 perdeu todos os blocos na conferência; a C1 gerou duas vezes, com textos diferentes
    etapa_2 = [_linha_do_resultado("C1", "GERADO", "gerado", blocos=5, tamanho_do_texto=400, custo_usd=0.02,
                                   segundos=8.0, texto="a", checagem_do_detector="normal"),
               _linha_do_resultado("C2", "SEM_EVIDENCIA", "nenhum_bloco_passou_na_conferencia", canal="whatsapp",
                                   tipo="faq", custo_usd=0.03, segundos=12.0, observacoes=["Bloco removido: x"]),
               _linha_do_resultado("C1", "GERADO", "gerado", blocos=5, custo_usd=0.02, segundos=9.0, texto="b",
                                   rodada=2)]
    comparacao = resumo.comparar_com_o_mock(etapa_1, etapa_2)
    assert comparacao["pares"] == {"GERADO → GERADO": 1, "GERADO → SEM_EVIDENCIA": 1}
    assert len(comparacao["divergencias"]) == 1 and comparacao["divergencias"][0]["combinacao"] == "C2"
    assert comparacao["blocos_medios"] == {"mock": 3, "ia_real": 5}
    assert comparacao["tamanho_medio"] == {"mock": 100, "ia_real": 400}
    assert resumo.consistencia(etapa_2) == {"pares": 1, "mesma_situacao": 1, "mesmo_numero_de_blocos": 1,
                                                 "mesmo_texto": 0}
    custo = resumo.custo_e_tempo(etapa_2)
    assert custo["chamadas_da_ia"] == 3 and custo["custo_total_usd"] == pytest.approx(0.07)
    assert (custo["segundos_p50"], custo["segundos_p95"], custo["segundos_maximo"]) == (9.0, 12.0, 12.0)
    assert resumo.checagens_do_detector(etapa_2) == {"vazio": {"normal": 1}}
    das_etapas = resumo.resumir(etapa_1, etapa_2)
    assert das_etapas["etapa_1"]["por_situacao"] == {"GERADO": 2, "BARRADO_NA_ENTRADA": 1}
    assert das_etapas["etapa_2"]["rodada_1"] == 2 and das_etapas["etapa_1"]["empresas_que_nao_geram"] == []


def test_aviso_do_destaque_certo_e_o_que_faltou():
    """O fora do catálogo devia avisar sempre; o normal, só sem a conta salário; o aviso da IA também conta."""
    linhas = [_linha_do_resultado("C1", "GERADO", "gerado", caso_do_destaque="fora_do_catalogo",
                                  destaque_avisado=True),
              _linha_do_resultado("C2", "GERADO", "gerado", caso_do_destaque="fora_do_catalogo"),
              _linha_do_resultado("C3", "GERADO", "gerado", caso_do_destaque="fora_do_catalogo", ia_nao_encontrou=True),
              _linha_do_resultado("C4", "GERADO", "gerado", caso_do_destaque="normal", beneficios=["Crédito"],
                                  destaque_avisado=True),
              _linha_do_resultado("C5", "GERADO", "gerado", caso_do_destaque="normal", destaque_avisado=True),
              # Não gerado: a tela não mostra aviso nenhum, e a linha fica de fora
              _linha_do_resultado("C6", "RECUSADO", "destaque_barrado_pela_lista", caso_do_destaque="normal")]
    assert resumo.aviso_do_destaque(linhas) == {
        "normal": {"devia_avisar": 1, "avisou": 1, "nao_devia_avisar": 1, "avisou_sem_precisar": 1},
        "fora_do_catalogo": {"devia_avisar": 3, "avisou": 2, "nao_devia_avisar": 0, "avisou_sem_precisar": 0}}


# ---------------- A conferência do ambiente ----------------

def test_nunca_roda_no_banco_nem_no_indice_de_todos_nem_no_modo_errado(monkeypatch):
    """O PostgreSQL de todos, o SQLite de uso e o índice de uso são recusados; a etapa 2 exige a IA real."""
    de_todos = "postgresql://aplicacao@localhost:5432/integra_folha"
    monkeypatch.setattr(config, "BANCO", "postgres")
    monkeypatch.setattr(config, "POSTGRES_URL", de_todos)
    with pytest.raises(combinacoes.AmbienteProibido, match="banco de todos"):
        combinacoes.conferir_o_ambiente(1, de_todos)
    # A cópia passa (o índice dos testes já é uma cópia, pelo conftest; o modo é o MOCK)
    monkeypatch.setattr(config, "POSTGRES_URL", "postgresql://aplicacao@localhost:5432/integra_folha_exp019")
    combinacoes.conferir_o_ambiente(1, de_todos)
    # A etapa 2 só com a IA real
    with pytest.raises(combinacoes.AmbienteProibido, match="MODE=llm"):
        combinacoes.conferir_o_ambiente(2, de_todos)
    # O índice de uso: recusado
    monkeypatch.setattr(busca_rag, "PASTA_INDICES", config.RAIZ / "storage" / "indices")
    with pytest.raises(combinacoes.AmbienteProibido, match="índice"):
        combinacoes.conferir_o_ambiente(1, de_todos)
    # O SQLite de uso também é recusado
    monkeypatch.setattr(config, "BANCO", "sqlite")
    monkeypatch.setattr(config, "CAMINHO_BANCO", config.RAIZ / "storage" / "integra_folha.db")
    with pytest.raises(combinacoes.AmbienteProibido, match="banco de uso"):
        combinacoes.conferir_o_ambiente(1, de_todos)
