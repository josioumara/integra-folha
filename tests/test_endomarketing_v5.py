"""O Agente de Endomarketing com o prompt v5 (ADR-150): os quatro defeitos do EXP-019, provados em MOCK (sem IA real).

O que estes testes provam:
- o formato garantido: todo pedido leva o esquema da resposta, que segue as regras do Bedrock, e o esquema chega ao
  Bedrock no pedido ao modelo grande em uso; um catálogo com nomes entre aspas gera o material; a resposta com aspas
  sem o escape (o erro da IA real) ganha uma segunda tentativa, com o motivo; duas respostas fora do formato viram
  FALHA; um bloco sem fonte sai sozinho, sem derrubar o material;
- o link com a pontuação colada: o link do catálogo seguido de vírgula, ponto, parêntese e afins continua valendo; o
  link inventado continua derrubando o bloco; a troca por "[link removido]" (a proteção de entrada) não muda;
- o aviso do destaque fora do catálogo: o nome de uma seção que entrou cobre o destaque; senão, decide a seção mais
  parecida (uma só), dentro do corte do destaque, que é um parâmetro;
- o WhatsApp e os benefícios escolhidos: todo benefício escolhido aparece, em até 3 blocos; o que a IA deixou de fora
  (ou a conferência tirou) ganha a frase do catálogo; os blocos a mais se juntam no último, sem perder nada.

O catálogo, os links e os textos daqui foram escritos para estes testes (o domínio .test é reservado para testes).
"""
import json
import re

import httpx
import pytest

from agents import endomarketing
from rag import busca as busca_rag
from services import auth, catalogo, config, guardrail_injecao, kbs_endomarketing
from services.llm_client import LLMClient, RespostaLLM

# Quem grava os documentos de catálogo destes testes
AUTOR_DOS_TESTES = "especialista.teste"
# A empresa que recebe o catálogo de teste (uma das empresas da semente)
EMPRESA = "EMP001"
# A vigência larga do catálogo de teste: vale em qualquer dia em que o teste rodar
VIGENCIA_INICIO, VIGENCIA_FIM = "2020-01-01", "2099-12-31"
# O título do catálogo de teste e o link da página dele
TITULO_DO_GUIA = "Guia de teste da equipe"
LINK_DO_GUIA = "https://beneficios.exemplo.test/equipe"
# O catálogo de teste: três benefícios (um com nomes de tela entre aspas retas, um com número) e os dois de atendimento
CATALOGO_DE_TESTE = f"""# {TITULO_DO_GUIA}

## Vale-cultura da equipe
Categoria: Conta e dia a dia
Na opção "Meus benefícios" do aplicativo, cada pessoa consulta o saldo do vale. O saldo aparece em "Extrato do vale".

## Adiantamento no aplicativo
Categoria: Conta e dia a dia
O adiantamento é de até 40% do salário líquido, pedido no aplicativo. O valor sai no próximo pagamento.

## Reserva automática
Categoria: Investimentos
A sobra do mês vai para uma reserva com resgate a qualquer momento. A adesão é opcional.

## Onde consultar
Página do guia: {LINK_DO_GUIA}

## Canais de dúvidas
- Central da equipe: 0800 000 0099
"""
# Os benefícios do catálogo de teste, na ordem do documento
BENEFICIOS_DO_GUIA = ["Vale-cultura da equipe", "Adiantamento no aplicativo", "Reserva automática"]
# As empresas da semente, cada uma com o seu catálogo
EMPRESAS_DA_SEMENTE = ["EMP001", "EMP002", "EMP003", "EMP004", "EMP005", "EMP006"]


# ---------- Preparação ----------

@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, com a semente e, na empresa de teste, o catálogo de teste."""
    conexao_do_teste = auth.conectar(tmp_path / "teste.db")
    catalogo.adicionar_documento(conexao_do_teste, EMPRESA, TITULO_DO_GUIA, VIGENCIA_INICIO, VIGENCIA_FIM,
                                 CATALOGO_DE_TESTE, AUTOR_DOS_TESTES)
    yield conexao_do_teste
    conexao_do_teste.close()


class IaDeTeste:
    """Uma IA de teste: responde, em ordem, com as funções dadas e guarda o pedido e o esquema de cada chamada.

    Recebe: as respostas (uma função por chamada, que recebe o pedido e devolve o texto; a última vale para as
    chamadas que passarem da lista). Guarda: pedidos e esquemas, na ordem das chamadas.
    """

    def __init__(self, *respostas):
        """Começa sem nenhuma chamada guardada."""
        self.respostas = list(respostas)
        self.pedidos = []
        self.esquemas = []

    def gerar(self, tarefa: str, prompt: str, sistema: str = "", temperatura: float = 0.0,
              esquema_json: dict | None = None) -> RespostaLLM:
        """Guarda a chamada e devolve a resposta dela, no mesmo formato do cliente de verdade."""
        self.pedidos.append(prompt)
        self.esquemas.append(esquema_json)
        # A resposta desta chamada (a última da lista vale para as seguintes)
        posicao = min(len(self.pedidos), len(self.respostas)) - 1
        return RespostaLLM(texto=self.respostas[posicao](prompt), modo="mock", modelo="mock")


def resposta_fixa(texto: str):
    """Uma resposta de teste que devolve sempre o mesmo texto, qualquer que seja o pedido."""
    def responder(pedido: str) -> str:
        """O texto fixo do teste."""
        return texto
    return responder


def resposta_com(blocos: list[dict], titulo: str = "Novidades para a equipe"):
    """Uma resposta de teste com o JSON do material: o título e os blocos dados, sem nada "não encontrado"."""
    return resposta_fixa(json.dumps({"titulo": titulo, "blocos": blocos, "nao_encontrado": []}, ensure_ascii=False))


def fonte_do_guia(secao: str) -> str:
    """A fonte de uma seção do catálogo de teste (a versão 1 do documento). Ex.: "Guia ... v1 › Reserva automática"."""
    return f"{TITULO_DO_GUIA} v1 › {secao}"


def gerar(conexao, ia, beneficios: list[str], canal: str = "email", destaque: str = "", busca=None):
    """Pede um comunicado da empresa de teste com os benefícios marcados, como o especialista pede na tela."""
    return endomarketing.gerar_material(conexao, EMPRESA, "comunicado", "especialista.banco", destaque=destaque,
                                        cliente=ia, busca=busca, canal=canal, beneficios=beneficios)


def textos_dos_blocos(resultado) -> list[str]:
    """Os textos dos blocos que ficaram no rascunho, na ordem."""
    textos = []
    for bloco in resultado.material["blocos"]:
        textos.append(bloco["texto"])
    return textos


def beneficio_citado(material: dict, beneficio: str) -> bool:
    """True se algum bloco cita a fonte do benefício (a fonte termina em "› <nome do benefício>")."""
    for bloco in material["blocos"]:
        for fonte in bloco["fontes"]:
            if fonte.endswith("› " + beneficio):
                return True
    return False


def aviso_do_destaque(destaque: str) -> str:
    """A observação que a tela mostra quando os benefícios escolhidos não trazem o assunto do destaque."""
    return (f"Os benefícios escolhidos no catálogo desta empresa não trazem informação sobre \"{destaque}\": nada foi "
            "escrito sobre isso.")


# ---------- O formato garantido (o JSON quebrado pelas aspas) ----------

def test_cada_pedido_leva_o_esquema_da_resposta(conexao):
    """O formato garantido vai junto com o pedido, e é o esquema do material."""
    ia = IaDeTeste(endomarketing._simular_material)
    resultado = gerar(conexao, ia, ["Reserva automática"])
    assert resultado.situacao == endomarketing.GERADO
    assert ia.esquemas == [endomarketing.esquema_da_resposta()]


def _objetos_do_esquema(esquema: dict) -> list[dict]:
    """Todos os objetos ("type": "object") de dentro do esquema, em qualquer nível."""
    encontrados = []
    pendentes = [esquema]
    while pendentes:
        atual = pendentes.pop()
        if atual.get("type") == "object":
            encontrados.append(atual)
            pendentes.extend(atual["properties"].values())
        if "items" in atual:
            pendentes.append(atual["items"])
    return encontrados


def test_esquema_segue_as_regras_do_formato_garantido():
    """Todo objeto fecha a porta a campos extras e exige todos os campos; nenhum limite de tamanho de lista."""
    esquema = endomarketing.esquema_da_resposta()
    objetos = _objetos_do_esquema(esquema)
    # O material e o bloco
    assert len(objetos) == 2
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert sorted(objeto["required"]) == sorted(objeto["properties"])
    # O formato garantido não aceita limite no tamanho de uma lista: a regra "pelo menos uma fonte" é da conferência
    assert "minItems" not in json.dumps(esquema)


def test_catalogo_com_nomes_entre_aspas_gera_o_material(conexao):
    """O catálogo com nomes de tela entre aspas retas: o rascunho sai (MOCK), com as aspas no texto e a fonte certa."""
    resultado = endomarketing.gerar_material(conexao, EMPRESA, "faq", "especialista.banco",
                                             beneficios=["Vale-cultura da equipe"])
    assert resultado.situacao == endomarketing.GERADO
    assert '"Meus benefícios"' in " ".join(textos_dos_blocos(resultado))
    assert beneficio_citado(resultado.material, "Vale-cultura da equipe")


def test_resposta_com_aspas_sem_escape_ganha_a_segunda_tentativa(conexao):
    """O erro da IA real: as aspas retas copiadas sem o escape fecham o texto do JSON no meio. A segunda tentativa leva
    o motivo, e o material sai."""
    fonte = fonte_do_guia("Vale-cultura da equipe")
    # O JSON quebrado: as aspas do nome da tela fecham o texto antes da hora
    quebrado = ('{"titulo": "Seu vale", "blocos": [{"texto": "Na opção "Meus benefícios" veja o saldo.", "fontes": ["'
                + fonte + '"]}], "nao_encontrado": []}')
    certo = resposta_com([{"texto": 'Na opção "Meus benefícios" veja o saldo.', "fontes": [fonte]}])
    ia = IaDeTeste(resposta_fixa(quebrado), certo)
    resultado = gerar(conexao, ia, ["Vale-cultura da equipe"])
    assert resultado.situacao == endomarketing.GERADO
    assert textos_dos_blocos(resultado) == ['Na opção "Meus benefícios" veja o saldo.']
    # Duas chamadas, e a segunda leva o motivo da recusa da primeira
    assert len(ia.pedidos) == 2
    assert "A resposta da tentativa 1 não veio no formato combinado (Invalid JSON" in ia.pedidos[1]


def test_duas_respostas_fora_do_formato_viram_falha(conexao):
    """Duas respostas fora do formato: FALHA, com a mensagem da tela, e nenhum rascunho guardado."""
    ia = IaDeTeste(resposta_fixa("Não consegui escrever."), resposta_fixa('{"titulo": "sem fechar"'))
    resultado = gerar(conexao, ia, ["Reserva automática"])
    assert resultado.situacao == endomarketing.FALHA
    assert resultado.mensagem == "Não consegui montar o rascunho agora. Tente de novo."
    assert len(ia.pedidos) == 2
    assert endomarketing.listar(conexao, EMPRESA) == []


def test_ler_resposta_diz_o_motivo_numa_linha():
    """O motivo da recusa é curto e diz onde está o problema; cercas de código em volta do JSON não atrapalham."""
    with pytest.raises(ValueError, match="Invalid JSON"):
        endomarketing.ler_resposta('{"titulo": "Na área "Menu"", "blocos": [], "nao_encontrado": []}')
    with pytest.raises(ValueError, match=r"Field required \(em blocos\.0\.texto\)"):
        endomarketing.ler_resposta('{"titulo": "Oi", "blocos": [{"fontes": ["F"]}], "nao_encontrado": []}')
    with pytest.raises(ValueError, match="não trouxe um objeto JSON"):
        endomarketing.ler_resposta("sem JSON nenhum")
    material = endomarketing.ler_resposta('```json\n{"titulo": "Oi", "blocos": [], "nao_encontrado": []}\n```')
    assert material.titulo == "Oi"


def test_bloco_sem_fonte_sai_sem_derrubar_o_material(conexao):
    """Um bloco sem fonte sai com a observação; o bloco com fonte fica, e o rascunho é gerado."""
    fonte = fonte_do_guia("Reserva automática")
    ia = IaDeTeste(resposta_com([{"texto": "Um bloco sem fonte.", "fontes": []},
                                 {"texto": "A sobra do mês vai para a reserva.", "fontes": [fonte]}]))
    resultado = gerar(conexao, ia, ["Reserva automática"])
    assert resultado.situacao == endomarketing.GERADO
    assert textos_dos_blocos(resultado) == ["A sobra do mês vai para a reserva."]
    assert "Bloco removido: não cita nenhuma fonte do catálogo." in resultado.observacoes


def material_com_aspas(pedido: str) -> str:
    """O JSON que o formato garantido devolve: um bloco com um nome entre aspas (com o escape), citando a primeira fonte
    dos trechos do pedido."""
    primeira_fonte = re.search(r"<trechos>\n\[([^\]]+)\]", pedido).group(1)
    material = {"titulo": "Seu vale", "nao_encontrado": [],
                "blocos": [{"texto": 'Na opção "Meus benefícios" veja o saldo.', "fontes": [primeira_fonte]}]}
    return json.dumps(material, ensure_ascii=False)


class BedrockDeTeste:
    """Faz o papel do Bedrock na API Converse: guarda o corpo de cada pedido e responde com o material.

    Nada sai da máquina: o httpx.post é trocado por este objeto no teste.
    """

    def __init__(self):
        """Começa sem nenhum pedido guardado."""
        self.corpos = []

    def post(self, endereco, headers, json, timeout):
        """Guarda o corpo do pedido e devolve a resposta no formato da API Converse (o nome "json" é o do httpx)."""
        self.corpos.append(json)
        # O pedido que o agente montou, para a resposta citar uma fonte que veio dele
        pedido = json["messages"][0]["content"][0]["text"]
        corpo = {"output": {"message": {"content": [{"text": material_com_aspas(pedido)}]}},
                 "stopReason": "end_turn", "usage": {"inputTokens": 100, "outputTokens": 50}}
        return httpx.Response(200, json=corpo, request=httpx.Request("POST", endereco))


def test_o_esquema_chega_ao_bedrock_no_pedido_ao_modelo_grande(conexao, monkeypatch):
    """Com a IA real (um Bedrock de teste), o pedido ao Sonnet 4.6 leva o esquema do material no formato garantido, e a
    resposta com aspas vira o rascunho."""
    # A rota Bedrock, com uma chave de teste e o modelo grande do plano B
    monkeypatch.setattr(config, "ROTA_DA_IA", "bedrock")
    monkeypatch.setattr(config, "CHAVE_BEDROCK", "chave-de-teste")
    monkeypatch.setattr(config, "REGIAO_BEDROCK", "us-east-1")
    monkeypatch.setattr(config, "MODELO_GRANDE", "claude-sonnet-4-6")
    bedrock = BedrockDeTeste()
    monkeypatch.setattr(httpx, "post", bedrock.post)
    resultado = gerar(conexao, LLMClient(modo="llm", mock_de_reserva=False), ["Vale-cultura da equipe"])
    assert resultado.situacao == endomarketing.GERADO and resultado.modelo == "claude-sonnet-4-6"
    # O esquema do material foi no pedido, do jeito que o Bedrock pede (o esquema em texto)
    formato = bedrock.corpos[0]["outputConfig"]["textFormat"]
    assert formato["type"] == "json_schema"
    assert json.loads(formato["structure"]["jsonSchema"]["schema"]) == endomarketing.esquema_da_resposta()
    assert textos_dos_blocos(resultado) == ['Na opção "Meus benefícios" veja o saldo.']


# ---------- O link com a pontuação da frase colada ----------

@pytest.mark.parametrize("pontuacao", [",", ".", ")", ").", ";", ":", "!", "?", "”", "\"."])
def test_link_com_a_pontuacao_da_frase_e_o_mesmo_link(pontuacao):
    """A pontuação que a frase deixa colada no fim não é parte do endereço."""
    texto = f"Veja em ({LINK_DO_GUIA}{pontuacao} e tire as dúvidas"
    assert guardrail_injecao.links_no_texto(texto) == [LINK_DO_GUIA]


def test_a_troca_por_link_removido_continua_pegando_o_endereco_inteiro():
    """A proteção de entrada não muda: o link sai inteiro, com o que vier colado até o espaço."""
    assert guardrail_injecao.tirar_links("Confira em https://coleta.exemplo.test/?cpf=1.") == "Confira em [link removido]"
    assert guardrail_injecao.tirar_links(f"Veja {LINK_DO_GUIA}, hoje") == "Veja [link removido] hoje"


def _trechos_com_o_link() -> list[dict]:
    """Um trecho de catálogo com o link da página do guia (o formato da busca do RAG: a fonte na primeira linha)."""
    fonte = fonte_do_guia("Onde consultar")
    return [{"fonte": fonte, "texto": f"{fonte}\nPágina do guia: {LINK_DO_GUIA}"}]


@pytest.mark.parametrize("pontuacao", [",", ".", ")", ";", ":", "!", "?"])
def test_bloco_com_o_link_do_catalogo_e_a_pontuacao_fica(pontuacao):
    """O link da página, igual ao do trecho citado e seguido da pontuação da frase: o bloco passa na conferência."""
    texto = f"Tudo sobre os benefícios fica em {LINK_DO_GUIA}{pontuacao} Consulte sempre."
    bloco = endomarketing.Bloco(texto=texto, fontes=[fonte_do_guia("Onde consultar")])
    aprovados, observacoes = endomarketing.conferir_material(endomarketing.MaterialGerado(titulo="Guia", blocos=[bloco]),
                                                             _trechos_com_o_link())
    assert observacoes == []
    assert len(aprovados) == 1


@pytest.mark.parametrize("link_inventado", ["https://golpe.exemplo.test.", LINK_DO_GUIA + ".golpe.test",
                                            LINK_DO_GUIA + "?pessoa=ana,", "www.golpe.exemplo.test)"])
def test_link_que_nao_esta_no_trecho_continua_derrubando_o_bloco(link_inventado):
    """Tirar a pontuação do fim não abre brecha: o endereço que sobra precisa ser idêntico ao do trecho citado."""
    bloco = endomarketing.Bloco(texto=f"Veja em {link_inventado} os detalhes.", fontes=[fonte_do_guia("Onde consultar")])
    aprovados, observacoes = endomarketing.conferir_material(endomarketing.MaterialGerado(titulo="Guia", blocos=[bloco]),
                                                             _trechos_com_o_link())
    assert aprovados == []
    assert observacoes[0].startswith("Bloco removido: o link ")


def test_titulo_com_o_link_do_catalogo_e_pontuacao_fica():
    """O título passa pela mesma conferência dos links: o link do catálogo seguido de pontuação fica."""
    titulo, observacoes = endomarketing.conferir_titulo(f"Tudo em {LINK_DO_GUIA}!", "comunicado", _trechos_com_o_link())
    assert (titulo, observacoes) == (f"Tudo em {LINK_DO_GUIA}!", [])


def test_material_com_o_link_do_guia_e_virgula_nao_perde_o_bloco(conexao):
    """O caso do EXP-019, com o catálogo de teste: a IA escreve o link da página seguido de vírgula, e o bloco fica."""
    ia = IaDeTeste(resposta_com([
        {"texto": "A sobra do mês vai para a reserva.", "fontes": [fonte_do_guia("Reserva automática")]},
        {"texto": f"Os detalhes ficam em {LINK_DO_GUIA}, na página do guia.", "fontes": [fonte_do_guia("Onde consultar")]}]))
    resultado = gerar(conexao, ia, ["Reserva automática"])
    assert len(textos_dos_blocos(resultado)) == 2
    for observacao in resultado.observacoes:
        assert not observacao.startswith("Bloco removido")


# ---------- O aviso do destaque fora do catálogo ----------

class BuscaComDistancias:
    """Uma busca de teste que devolve, do mais parecido para o menos, as seções dadas, com a distância de cada uma.

    Recebe: as seções e as distâncias ([(fonte, distância)], em ordem). Guarda: o k pedido em cada chamada.
    """

    def __init__(self, secoes_e_distancias: list[tuple[str, float]]):
        """Começa sem nenhuma chamada guardada."""
        self.secoes_e_distancias = secoes_e_distancias
        self.pedidos_de_k = []

    def __call__(self, empresa_id: str, consulta: str, k: int = 2) -> list[dict]:
        """Os k primeiros, no formato da busca do RAG (com a distância)."""
        self.pedidos_de_k.append(k)
        encontrados = []
        for fonte, distancia in self.secoes_e_distancias[:k]:
            encontrados.append({"fonte": fonte, "texto": fonte + "\nTrecho de teste.", "empresa_id": empresa_id,
                                "distancia": distancia})
        return encontrados


def test_destaque_decide_pela_secao_mais_parecida(conexao):
    """A seção mais parecida é outra, que não entrou: o aviso sai, mesmo com a escolhida em segundo. Só uma é comparada."""
    busca = BuscaComDistancias([(fonte_do_guia("Adiantamento no aplicativo"), 0.40),
                                (fonte_do_guia("Reserva automática"), 0.45)])
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque="fale do dinheiro antes do dia", busca=busca)
    assert aviso_do_destaque("fale do dinheiro antes do dia") in resultado.observacoes
    assert busca.pedidos_de_k == [1]


def test_secao_mais_parecida_que_entrou_cobre_o_destaque(conexao):
    """A seção mais parecida é a escolhida: nenhum aviso."""
    busca = BuscaComDistancias([(fonte_do_guia("Reserva automática"), 0.40)])
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque="lembre da sobra do mês", busca=busca)
    assert aviso_do_destaque("lembre da sobra do mês") not in resultado.observacoes


def test_destaque_que_cita_o_nome_do_beneficio_escolhido_esta_coberto(conexao):
    """O nome escrito vale mais que a semelhança: a seção mais parecida é outra, mas o destaque cita a escolhida (sem
    ligar para acento nem para maiúsculas)."""
    busca = BuscaComDistancias([(fonte_do_guia("Adiantamento no aplicativo"), 0.30)])
    com_o_nome = "reforce que a RESERVA AUTOMATICA é opcional"
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque=com_o_nome, busca=busca)
    assert aviso_do_destaque(com_o_nome) not in resultado.observacoes
    # O controle: sem o nome, a mesma busca leva ao aviso
    sem_o_nome = "reforce que a adesão é opcional"
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque=sem_o_nome, busca=busca)
    assert aviso_do_destaque(sem_o_nome) in resultado.observacoes


def test_destaque_sobre_o_atendimento_esta_coberto(conexao):
    """O atendimento entra em todo material: o destaque cuja seção mais parecida é a de dúvidas não é avisado."""
    busca = BuscaComDistancias([(fonte_do_guia("Canais de dúvidas"), 0.55)])
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque="lembre a central da equipe", busca=busca)
    assert aviso_do_destaque("lembre a central da equipe") not in resultado.observacoes


def test_nada_perto_o_bastante_e_avisado(conexao):
    """A busca não acha nada dentro do corte: o catálogo não tem o assunto, e o aviso sai."""
    busca = BuscaComDistancias([])
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque="plano de saúde para a família", busca=busca)
    assert aviso_do_destaque("plano de saúde para a família") in resultado.observacoes


def test_o_corte_do_destaque_e_um_parametro(conexao, monkeypatch):
    """O corte do destaque começa no geral do catálogo; mais apertado, a seção escolhida longe dele deixa de cobrir."""
    assert endomarketing.DISTANCIA_MAXIMA_DO_DESTAQUE == busca_rag.DISTANCIA_MAXIMA_CATALOGO
    monkeypatch.setattr(endomarketing, "DISTANCIA_MAXIMA_DO_DESTAQUE", 0.5)
    destaque = "lembre da sobra do mês"
    longe = BuscaComDistancias([(fonte_do_guia("Reserva automática"), 0.6)])
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque=destaque, busca=longe)
    assert aviso_do_destaque(destaque) in resultado.observacoes
    perto = BuscaComDistancias([(fonte_do_guia("Reserva automática"), 0.4)])
    resultado = gerar(conexao, IaDeTeste(endomarketing._simular_material), ["Reserva automática"],
                      destaque=destaque, busca=perto)
    assert aviso_do_destaque(destaque) not in resultado.observacoes


# ---------- O WhatsApp e os benefícios escolhidos ----------

@pytest.mark.parametrize("tipo", list(endomarketing.TIPOS))
@pytest.mark.parametrize("empresa_id", EMPRESAS_DA_SEMENTE)
def test_whatsapp_com_todos_os_beneficios_cita_cada_um(conexao, empresa_id, tipo):
    """MOCK, no WhatsApp, com todos os benefícios da empresa marcados: até 3 blocos, e todo benefício escolhido tem a
    fonte citada (na empresa de teste, também os três do catálogo de teste)."""
    todos = endomarketing.beneficios_do_catalogo(conexao, empresa_id)
    resultado = endomarketing.gerar_material(conexao, empresa_id, tipo, "especialista.banco", canal="whatsapp",
                                             beneficios=todos)
    assert resultado.situacao == endomarketing.GERADO
    assert 0 < len(resultado.material["blocos"]) <= 3
    for beneficio in todos:
        assert beneficio_citado(resultado.material, beneficio), beneficio


def test_beneficio_que_a_ia_deixou_de_fora_ganha_a_frase_do_catalogo(conexao):
    """A IA escreve só sobre um dos três benefícios (e o atendimento): os outros dois entram com a primeira frase do
    catálogo, com a fonte, antes do atendimento, e a observação diz quais."""
    ia = IaDeTeste(resposta_com([
        {"texto": "A sobra do mês vai para a reserva.", "fontes": [fonte_do_guia("Reserva automática")]},
        {"texto": "Dúvidas? Fale com a central.", "fontes": [fonte_do_guia("Canais de dúvidas")]}]))
    resultado = gerar(conexao, ia, BENEFICIOS_DO_GUIA)
    assert textos_dos_blocos(resultado) == [
        "A sobra do mês vai para a reserva.",
        'Vale-cultura da equipe: Na opção "Meus benefícios" do aplicativo, cada pessoa consulta o saldo do vale.',
        "Adiantamento no aplicativo: O adiantamento é de até 40% do salário líquido, pedido no aplicativo.",
        "Dúvidas? Fale com a central."]
    for beneficio in BENEFICIOS_DO_GUIA:
        assert beneficio_citado(resultado.material, beneficio)
    assert ("O benefício \"Vale-cultura da equipe\" não veio no texto do Agente de Endomarketing: entrou a frase do "
            "catálogo, com a fonte.") in resultado.observacoes


def test_bloco_tirado_pela_conferencia_nao_leva_o_beneficio_embora(conexao):
    """A IA inventa um número no bloco do adiantamento: o bloco sai, e o benefício volta com a frase do catálogo, com o
    número certo."""
    ia = IaDeTeste(resposta_com([
        {"texto": "Peça até 70% do salário no aplicativo.", "fontes": [fonte_do_guia("Adiantamento no aplicativo")]},
        {"texto": "A sobra do mês vai para a reserva.", "fontes": [fonte_do_guia("Reserva automática")]}]))
    resultado = gerar(conexao, ia, ["Adiantamento no aplicativo", "Reserva automática"])
    assert textos_dos_blocos(resultado) == [
        "A sobra do mês vai para a reserva.",
        "Adiantamento no aplicativo: O adiantamento é de até 40% do salário líquido, pedido no aplicativo."]
    assert "Bloco removido: o número 70 não está no trecho citado." in resultado.observacoes


def test_ia_que_escreve_blocos_demais_no_whatsapp_junta_os_do_fim(conexao):
    """Cinco blocos no WhatsApp: ficam 3, e o terceiro junta o texto e as fontes do 3º, do 4º e do 5º, sem perder nada."""
    ia = IaDeTeste(resposta_com([
        {"texto": "A reserva é opcional.", "fontes": [fonte_do_guia("Reserva automática")]},
        {"texto": "O vale tem saldo no aplicativo.", "fontes": [fonte_do_guia("Vale-cultura da equipe")]},
        {"texto": "O adiantamento sai no próximo pagamento.", "fontes": [fonte_do_guia("Adiantamento no aplicativo")]},
        {"texto": "A página do guia tem tudo.", "fontes": [fonte_do_guia("Onde consultar")]},
        {"texto": "Fale com a central.", "fontes": [fonte_do_guia("Canais de dúvidas")]}]))
    resultado = gerar(conexao, ia, BENEFICIOS_DO_GUIA, canal="whatsapp")
    blocos = resultado.material["blocos"]
    assert len(blocos) == 3
    assert blocos[2]["texto"] == "O adiantamento sai no próximo pagamento. A página do guia tem tudo. Fale com a central."
    assert blocos[2]["fontes"] == [fonte_do_guia("Adiantamento no aplicativo"), fonte_do_guia("Onde consultar"),
                                   fonte_do_guia("Canais de dúvidas")]
    assert ("No WhatsApp, cabem 3 trechos: os que passavam disso foram juntados ao último, sem tirar nada do texto."
            in resultado.observacoes)


def test_frase_do_catalogo_com_termo_proibido_nao_entra(conexao):
    """Se a própria frase do catálogo usa um termo proibido, ela não entra, e a observação pede para gerar de novo."""
    termo = kbs_endomarketing.termos_proibidos(conexao)[0]
    extra = f"# Guia extra de teste\n\n## Brinde da equipe\nUm brinde {termo} para quem chega. Pergunte ao RH.\n"
    catalogo.adicionar_documento(conexao, EMPRESA, "Guia extra de teste", VIGENCIA_INICIO, VIGENCIA_FIM, extra,
                                 AUTOR_DOS_TESTES)
    ia = IaDeTeste(resposta_com([{"texto": "A sobra do mês vai para a reserva.",
                                  "fontes": [fonte_do_guia("Reserva automática")]}]))
    resultado = gerar(conexao, ia, ["Reserva automática", "Brinde da equipe"])
    assert textos_dos_blocos(resultado) == ["A sobra do mês vai para a reserva."]
    assert (f"O benefício \"Brinde da equipe\" ficou fora do texto: a frase dele no catálogo usa o termo proibido "
            f"\"{termo}\". Gere o material de novo.") in resultado.observacoes


def test_pedido_leva_a_lista_dos_beneficios_escolhidos(conexao):
    """O pedido do prompt padrão leva os benefícios escolhidos, um por linha, antes dos trechos."""
    ia = IaDeTeste(endomarketing._simular_material)
    gerar(conexao, ia, ["Reserva automática", "Vale-cultura da equipe"])
    pedido = ia.pedidos[0]
    lista = re.search(r"<beneficios_escolhidos>\n(.*?)\n</beneficios_escolhidos>", pedido, re.S).group(1)
    assert lista.splitlines() == ["Reserva automática", "Vale-cultura da equipe"]
    assert pedido.index("<beneficios_escolhidos>") < pedido.index("<trechos>")


def test_o_prompt_v3_nao_leva_a_lista_mas_leva_o_esquema(conexao, monkeypatch):
    """Com a chave desligada (a v3, o histórico), o pedido é o de antes, sem a lista; o formato garantido vale nas duas
    versões, porque é o contrato da resposta, o mesmo desde a v1."""
    monkeypatch.setattr(config, "ENDOMARKETING_COM_AS_KBS", False)
    ia = IaDeTeste(endomarketing._simular_material)
    gerar(conexao, ia, ["Reserva automática"])
    assert "<beneficios_escolhidos>" not in ia.pedidos[0]
    assert ia.esquemas == [endomarketing.esquema_da_resposta()]


def test_o_prompt_v5_pede_todo_beneficio_em_qualquer_canal():
    """A regra está no texto do prompt: todo benefício escolhido aparece, e o WhatsApp junta os benefícios nos blocos."""
    sistema = endomarketing._sistema("endomarketing_v5")
    assert "Todo benefício de `<beneficios_escolhidos>` aparece no material, em qualquer canal" in sistema
    assert "junte-os nos blocos" in sistema


def test_primeira_frase_para_no_ponto_seguido_de_espaco():
    """O ponto de um número ou de um endereço não fecha a frase; sem ponto seguido de espaço, vale o texto inteiro."""
    assert endomarketing._primeira_frase("Até 1.500 reais por mês. Depois, a tarifa.") == "Até 1.500 reais por mês."
    assert endomarketing._primeira_frase(f"Página do guia: {LINK_DO_GUIA}") == f"Página do guia: {LINK_DO_GUIA}"
