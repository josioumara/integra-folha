"""As KBs no prompt do Agente de Endomarketing (desde a v4): as KBs gerais, a assinatura do kit e os termos proibidos.

O que estes testes provam, em modo MOCK (sem IA real):
- com a chave ENDOMARKETING_COM_AS_KBS ligada (o padrão), vale o prompt padrão (hoje a v5, ADR-150), e o pedido leva
  o texto da KB geral de tom de voz e o da KB geral de termos proibidos PUBLICADAS e a assinatura do kit em uso; a
  versão vai para o rascunho e para a Telemetria;
- com a chave desligada, vale o prompt v3 (o histórico) e o pedido de antes: é o jeito de voltar sem mexer no código;
- uma versão nova publicada de uma KB geral vale no pedido seguinte; uma KB retirada sai do pedido;
- a assinatura é o nome da empresa (o do cadastro) no kit próprio, e nada no kit padrão ou sem KB de kit publicada;
  a assinatura de uma empresa nunca vai para o pedido de outra;
- a conferência depois da geração barra o termo proibido: o bloco sai, com a observação; o título vira o nome do
  tipo; sem bloco que sobre, não há rascunho. Vale nas duas versões do prompt;
- a comparação é a da trava das KBs (a palavra inteira, sem ligar para acento nem para maiúsculas), e um termo novo
  publicado na KB passa a ser barrado sem mexer no código.

Nenhum teste supõe o kit de uma empresa: quem precisa de um kit (próprio ou padrão) publica a versão da KB que quer,
como o especialista faz no editor.
"""
import json
import re

import pytest

from agents import endomarketing
from services import auth, config, execucoes, kbs_endomarketing
from services import empresas as cadastro_de_empresas
from services.llm_client import RespostaLLM

# Quem aparece como autor das versões de KB gravadas pelos testes
AUTOR_DOS_TESTES = "especialista.teste"
# O texto de um bloco sem termo proibido e sem número (passa em todas as conferências)
BLOCO_LIMPO = "Conheça o benefício escolhido para o time."


class IaQueGuarda:
    """Uma IA de teste: guarda o pedido e o sistema de cada chamada e responde com a função dada.

    Recebe: responder (função que recebe o pedido e devolve o texto da resposta); sem informar, o simulador do
    próprio agente, que copia os trechos do catálogo. Guarda: chamadas = [(pedido, sistema)], na ordem, e
    esquemas = o formato garantido pedido em cada chamada.
    """

    def __init__(self, responder=None):
        """Começa sem nenhuma chamada guardada."""
        # Cada chamada: (o pedido, o sistema)
        self.chamadas = []
        # O esquema da resposta (o formato garantido) que cada chamada pediu
        self.esquemas = []
        # Sem resposta própria, responde como o simulador do agente (o mesmo do modo MOCK)
        self.responder = responder or endomarketing._simular_material

    def gerar(self, tarefa: str, prompt: str, sistema: str = "", temperatura: float = 0.0,
              esquema_json: dict | None = None) -> RespostaLLM:
        """Guarda o que chegou à IA e devolve a resposta no mesmo formato do cliente de verdade."""
        # Guarda o pedido e o sistema, para o teste conferir o que entrou no prompt
        self.chamadas.append((prompt, sistema))
        self.esquemas.append(esquema_json)
        # A resposta simulada, sem custo
        return RespostaLLM(texto=self.responder(prompt), modo="mock", modelo="mock")


def resposta_com_os_textos(titulo: str, textos: list[str]):
    """Uma resposta de teste: o título e um bloco para cada texto, todos citando a primeira fonte do pedido.

    Por que a primeira fonte do pedido: o bloco passa na conferência das fontes, e o teste mede só os termos
    proibidos. Os textos não têm número (a conferência dos números fica fora destes testes).
    """
    def responder(pedido: str) -> str:
        """Monta o JSON da resposta a partir do pedido que chegou."""
        # A primeira fonte entre os trechos do pedido (cada linha começa com a fonte entre colchetes)
        primeira_fonte = re.search(r"<trechos>\n\[([^\]]+)\]", pedido).group(1)
        blocos = []
        for texto in textos:
            blocos.append({"texto": texto, "fontes": [primeira_fonte]})
        return json.dumps({"titulo": titulo, "blocos": blocos, "nao_encontrado": []}, ensure_ascii=False)
    return responder


# ---------- Preparação ----------

@pytest.fixture
def conexao(tmp_path):
    """Um banco novo, com o catálogo e as KBs iniciais das empresas de exemplo."""
    conexao_do_teste = auth.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture
def com_o_prompt_padrao(monkeypatch):
    """Deixa a chave ligada neste teste (o padrão, o prompt com as KBs), qualquer que seja o .env de quem roda."""
    monkeypatch.setattr(config, "ENDOMARKETING_COM_AS_KBS", True)


@pytest.fixture
def com_o_prompt_v3(monkeypatch):
    """Desliga a chave só neste teste: volta para a v3, o histórico."""
    monkeypatch.setattr(config, "ENDOMARKETING_COM_AS_KBS", False)


def gerar(conexao, empresa_id: str, ia: IaQueGuarda):
    """Pede um comunicado da empresa com o primeiro benefício do catálogo dela, como o especialista pede na tela."""
    primeiro_beneficio = endomarketing.beneficios_do_catalogo(conexao, empresa_id)[0]
    return endomarketing.gerar_material(conexao, empresa_id, "comunicado", "especialista.banco",
                                        beneficios=[primeiro_beneficio], cliente=ia)


def texto_entre(pedido: str, marcacao: str) -> str | None:
    """O texto entre <marcacao> e </marcacao> no pedido, sem as quebras de linha das pontas. Sem a marcação: None."""
    encontrado = re.search(rf"<{marcacao}>\n(.*?)\n</{marcacao}>", pedido, re.S)
    if encontrado is None:
        return None
    return encontrado.group(1)


def sistema_do_prompt(versao: str) -> str:
    """A seção SISTEMA do arquivo do prompt: o que a IA tem de receber como sistema."""
    texto = (endomarketing.RAIZ / "prompts" / f"{versao}.md").read_text(encoding="utf-8")
    return texto.split("## SISTEMA", 1)[1].strip()


def kb_publicada(conexao, dono: str, tipo: str) -> dict:
    """A KB publicada e vigente do dono e do tipo (ex.: o tom de voz GERAL ou o kit de uma empresa)."""
    return kbs_endomarketing.kbs_publicadas(conexao, dono=dono, tipo=tipo)[0]


def publicar_versao_nova(conexao, kb_id: str, trecho_antigo: str, trecho_novo: str) -> None:
    """Grava e publica uma versão nova da KB com um trecho do texto trocado, como o especialista faz no editor."""
    publicada = kbs_endomarketing.obter(conexao, kb_id)
    conteudo_novo = publicada["conteudo_md"].replace(trecho_antigo, trecho_novo)
    # O trecho precisa existir na KB: senão o teste não estaria mudando nada
    assert conteudo_novo != publicada["conteudo_md"]
    gravada = kbs_endomarketing.salvar(conexao, AUTOR_DOS_TESTES, conteudo_novo)
    kbs_endomarketing.publicar(conexao, AUTOR_DOS_TESTES, kb_id, gravada["versao"])


def deixar_o_kit(conexao, empresa_id: str, escolha: str) -> None:
    """Deixa a KB do kit da empresa na escolha pedida ("proprio" ou "padrao"), com uma versão nova se preciso."""
    kit = kb_publicada(conexao, empresa_id, endomarketing.TIPO_DO_KIT)
    escolha_de_agora = kit["ficha"]["kit_escolhido"]
    # Só grava uma versão nova quando a escolha muda
    if escolha_de_agora != escolha:
        publicar_versao_nova(conexao, kit["kb_id"], f"kit_escolhido: {escolha_de_agora}", f"kit_escolhido: {escolha}")


def versao_do_rascunho(conexao, material_id: str) -> str:
    """A versão do prompt gravada junto com o rascunho."""
    return conexao.execute("SELECT versao_prompt FROM materiais_endomarketing WHERE material_id = ?",
                           (material_id,)).fetchone()[0]


def ultima_execucao(conexao) -> dict:
    """A última execução gravada para a Telemetria."""
    return execucoes.listar(conexao)[-1]


def textos_dos_blocos(resultado) -> list[str]:
    """Os textos dos blocos que ficaram no rascunho, na ordem."""
    textos = []
    for bloco in resultado.material["blocos"]:
        textos.append(bloco["texto"])
    return textos


# ---------- A versão do prompt e a chave ----------

def test_com_a_chave_desligada_volta_o_prompt_v3_e_o_pedido_de_antes(conexao, com_o_prompt_v3):
    """Chave desligada: o sistema é o da v3 (o histórico), e o pedido não leva as KBs nem a assinatura."""
    ia = IaQueGuarda()
    resultado = gerar(conexao, "EMP001", ia)
    assert resultado.situacao == endomarketing.GERADO
    pedido, sistema = ia.chamadas[0]
    assert sistema == sistema_do_prompt("endomarketing_v3")
    # Nenhuma das marcações novas entra no pedido
    for marcacao in ("tom_de_voz", "termos_proibidos", "assinatura"):
        assert f"<{marcacao}>" not in pedido
    # A versão usada vai para o rascunho e para a Telemetria
    assert versao_do_rascunho(conexao, resultado.material_id) == "endomarketing_v3"
    assert ultima_execucao(conexao)["versao_prompt"] == "endomarketing_v3"


def test_com_a_chave_ligada_vale_o_prompt_padrao_com_as_kbs_publicadas_e_a_assinatura(conexao, com_o_prompt_padrao):
    """Chave ligada (o padrão): o sistema é o do prompt padrão, e o pedido leva o tom de voz, os termos proibidos e a
    assinatura."""
    deixar_o_kit(conexao, "EMP001", kbs_endomarketing.KIT_PROPRIO)
    ia = IaQueGuarda()
    resultado = gerar(conexao, "EMP001", ia)
    assert resultado.situacao == endomarketing.GERADO
    pedido, sistema = ia.chamadas[0]
    assert sistema == sistema_do_prompt(endomarketing.VERSAO_PROMPT)
    # O texto das duas KBs gerais publicadas, cada um na sua marcação
    assert texto_entre(pedido, "tom_de_voz") == kb_publicada(conexao, "GERAL", "tom_de_voz")["corpo"]
    assert texto_entre(pedido, "termos_proibidos") == kb_publicada(conexao, "GERAL", "termos_proibidos")["corpo"]
    # A assinatura do kit próprio: o nome da empresa, como está no cadastro
    assert texto_entre(pedido, "assinatura") == cadastro_de_empresas.obter(conexao, "EMP001")["nome"]
    # O contexto vem antes dos trechos, e os trechos continuam no pedido
    assert pedido.index("<assinatura>") < pedido.index("<trechos>")
    # A versão padrão vai para o rascunho e para a Telemetria
    assert versao_do_rascunho(conexao, resultado.material_id) == endomarketing.VERSAO_PROMPT
    assert ultima_execucao(conexao)["versao_prompt"] == endomarketing.VERSAO_PROMPT


def test_o_simulador_do_mock_monta_o_rascunho_com_o_pedido_padrao(conexao, com_o_prompt_padrao):
    """Sem IA de teste (o cliente padrão do MOCK), o rascunho sai do pedido padrão, com as fontes do catálogo."""
    primeiro_beneficio = endomarketing.beneficios_do_catalogo(conexao, "EMP005")[0]
    resultado = endomarketing.gerar_material(conexao, "EMP005", "faq", "especialista.banco",
                                             beneficios=[primeiro_beneficio])
    assert resultado.situacao == endomarketing.GERADO
    assert resultado.material["blocos"]
    for bloco in resultado.material["blocos"]:
        assert bloco["fontes"]


@pytest.mark.parametrize("versao", ["endomarketing_v4", "endomarketing_v5"])
def test_o_prompt_com_as_kbs_nao_cita_nenhuma_empresa(conexao, versao):
    """Generalização: a regra é geral, e nenhum nome de empresa do cadastro está no texto do prompt."""
    texto_do_prompt = (endomarketing.RAIZ / "prompts" / f"{versao}.md").read_text(encoding="utf-8")
    for empresa in cadastro_de_empresas.listar(conexao):
        # O nome inteiro e a primeira palavra dele (o nome curto que um exemplo usaria)
        assert empresa["nome"] not in texto_do_prompt
        assert empresa["nome"].split()[0] not in texto_do_prompt


# ---------- As KBs gerais publicadas ----------

def test_versao_nova_publicada_do_tom_de_voz_vale_no_pedido_seguinte(conexao, com_o_prompt_padrao):
    """O especialista publica uma versão nova do tom de voz: o pedido seguinte leva a nova, e não a antiga."""
    regra_nova = "Prefira frases que caibam na tela de um celular."
    tom_de_antes = kb_publicada(conexao, "GERAL", "tom_de_voz")
    # A regra nova entra no fim da seção "Como escrever", logo antes da seção dos exemplos
    publicar_versao_nova(conexao, tom_de_antes["kb_id"], "## Exemplos certo e errado",
                         regra_nova + "\n\n## Exemplos certo e errado")
    ia = IaQueGuarda()
    gerar(conexao, "EMP002", ia)
    tom_no_pedido = texto_entre(ia.chamadas[0][0], "tom_de_voz")
    assert regra_nova in tom_no_pedido
    assert tom_no_pedido != tom_de_antes["corpo"]


def test_kb_geral_retirada_sai_do_pedido(conexao, com_o_prompt_padrao):
    """Sem versão publicada do tom de voz (retirada), a marcação vai vazia, e o material sai com as regras do prompt."""
    kbs_endomarketing.retirar(conexao, AUTOR_DOS_TESTES, kb_publicada(conexao, "GERAL", "tom_de_voz")["kb_id"])
    ia = IaQueGuarda()
    resultado = gerar(conexao, "EMP001", ia)
    assert resultado.situacao == endomarketing.GERADO
    assert texto_entre(ia.chamadas[0][0], "tom_de_voz") == ""
    # A outra KB geral continua no pedido
    assert texto_entre(ia.chamadas[0][0], "termos_proibidos")


# ---------- A assinatura do kit em uso ----------

def test_kit_proprio_assina_com_o_nome_da_propria_empresa_e_nunca_com_o_de_outra(conexao, com_o_prompt_padrao):
    """Duas empresas de kit próprio: cada pedido leva o nome da própria empresa, e nunca o da outra."""
    nomes = {}
    assinaturas = {}
    for empresa_id in ("EMP001", "EMP002"):
        deixar_o_kit(conexao, empresa_id, kbs_endomarketing.KIT_PROPRIO)
        nomes[empresa_id] = cadastro_de_empresas.obter(conexao, empresa_id)["nome"]
        ia = IaQueGuarda()
        gerar(conexao, empresa_id, ia)
        assinaturas[empresa_id] = texto_entre(ia.chamadas[0][0], "assinatura")
    assert assinaturas == nomes
    assert nomes["EMP001"] != nomes["EMP002"]


def test_nenhum_nome_de_empresa_vai_no_pedido_pelas_kbs_gerais_nem_o_de_outra_empresa(conexao, com_o_prompt_padrao):
    """As KBs gerais vão no pedido de TODA empresa: nenhum nome de empresa pode estar nelas, nem o nome curto.

    Um exemplo com o nome de uma empresa levaria esse nome ao material das outras. No pedido inteiro, o nome de outra
    empresa nunca aparece (o da própria vem na assinatura e no catálogo dela).
    """
    empresas = cadastro_de_empresas.listar(conexao)
    for empresa in empresas:
        # Só a empresa com catálogo gera material
        if not endomarketing.beneficios_do_catalogo(conexao, empresa["empresa_id"]):
            continue
        ia = IaQueGuarda()
        gerar(conexao, empresa["empresa_id"], ia)
        pedido = ia.chamadas[0][0]
        # O texto das duas KBs gerais, como foi no pedido
        kbs_gerais = texto_entre(pedido, "tom_de_voz") + "\n" + texto_entre(pedido, "termos_proibidos")
        for outra in empresas:
            # O nome curto: a primeira palavra, como um exemplo o escreveria (palavra inteira, com a maiúscula)
            nome_curto = outra["nome"].split()[0]
            assert not re.search(rf"\b{re.escape(nome_curto)}\b", kbs_gerais), (empresa["empresa_id"], nome_curto)
            # No pedido inteiro, nunca o nome de outra empresa
            if outra["empresa_id"] != empresa["empresa_id"]:
                assert outra["nome"] not in pedido


def test_kit_padrao_nao_leva_assinatura(conexao, com_o_prompt_padrao):
    """A empresa passa para o kit padrão (uma versão nova da KB): a assinatura vai vazia."""
    deixar_o_kit(conexao, "EMP003", kbs_endomarketing.KIT_PADRAO)
    assert endomarketing.assinatura_do_kit_em_uso(conexao, "EMP003") == ""
    ia = IaQueGuarda()
    gerar(conexao, "EMP003", ia)
    assert texto_entre(ia.chamadas[0][0], "assinatura") == ""


def test_sem_kb_de_kit_publicada_vale_o_padrao_sem_assinatura(conexao, com_o_prompt_padrao):
    """A KB do kit retirada: o kit em uso é o padrão, sem assinatura. Quem decide é a KB, a fonte única do kit."""
    deixar_o_kit(conexao, "EMP004", kbs_endomarketing.KIT_PROPRIO)
    nome_da_empresa = cadastro_de_empresas.obter(conexao, "EMP004")["nome"]
    assert endomarketing.assinatura_do_kit_em_uso(conexao, "EMP004") == nome_da_empresa
    # O especialista retira a KB do kit
    kbs_endomarketing.retirar(conexao, AUTOR_DOS_TESTES, kb_publicada(conexao, "EMP004", "kit_da_marca")["kb_id"])
    assert endomarketing.assinatura_do_kit_em_uso(conexao, "EMP004") == ""
    ia = IaQueGuarda()
    gerar(conexao, "EMP004", ia)
    assert texto_entre(ia.chamadas[0][0], "assinatura") == ""


# ---------- A conferência dos termos proibidos ----------

def test_bloco_com_termo_proibido_sai_com_a_observacao(conexao, com_o_prompt_padrao):
    """A IA escreve um bloco com um termo da KB: ele sai, com a observação; o bloco limpo fica; a Telemetria conta."""
    termo = kbs_endomarketing.termos_proibidos(conexao)[0]
    ia = IaQueGuarda(resposta_com_os_textos("Novidades para o time", [BLOCO_LIMPO, f"Uma frase com {termo} no meio."]))
    resultado = gerar(conexao, "EMP001", ia)
    assert resultado.situacao == endomarketing.GERADO
    assert textos_dos_blocos(resultado) == [BLOCO_LIMPO]
    assert f"Bloco removido: usa o termo proibido \"{termo}\"." in resultado.observacoes
    # O rascunho guardado também não tem o termo, e a Telemetria marca o guardrail
    guardado = endomarketing.obter(conexao, "EMP001", resultado.material_id)
    assert termo not in json.dumps(guardado["conteudo"]["blocos"], ensure_ascii=False)
    assert ultima_execucao(conexao)["guardrail_disparado"] is True


def test_titulo_com_termo_proibido_vira_o_nome_do_material(conexao, com_o_prompt_padrao):
    """O título com um termo proibido é trocado pelo nome do tipo de material, com a observação; o bloco fica."""
    termo = kbs_endomarketing.termos_proibidos(conexao)[-1]
    ia = IaQueGuarda(resposta_com_os_textos(f"Novidade: {termo}", [BLOCO_LIMPO]))
    resultado = gerar(conexao, "EMP001", ia)
    assert resultado.material["titulo"] == endomarketing.TIPOS["comunicado"]["nome"]
    assert textos_dos_blocos(resultado) == [BLOCO_LIMPO]
    assert any(observacao.startswith("Título trocado") and termo in observacao
               for observacao in resultado.observacoes)
    assert ultima_execucao(conexao)["guardrail_disparado"] is True


def test_sem_bloco_que_sobre_nao_ha_rascunho(conexao, com_o_prompt_padrao):
    """Todos os blocos com termo proibido: nenhum sobra, a situação é "sem evidência", e nada é guardado."""
    termos = kbs_endomarketing.termos_proibidos(conexao)
    ia = IaQueGuarda(resposta_com_os_textos("Novidades", [f"Frase com {termos[0]}.", f"Outra com {termos[1]}."]))
    resultado = gerar(conexao, "EMP001", ia)
    assert resultado.situacao == endomarketing.SEM_EVIDENCIA
    assert endomarketing.listar(conexao, "EMP001") == []
    assert len(resultado.observacoes) == 2


def test_a_conferencia_vale_tambem_no_prompt_v3(conexao, com_o_prompt_v3):
    """A conferência é do código, e não do prompt: com a chave desligada, o termo proibido também é barrado."""
    termo = kbs_endomarketing.termos_proibidos(conexao)[1]
    ia = IaQueGuarda(resposta_com_os_textos("Novidades", [BLOCO_LIMPO, f"Com {termo}."]))
    resultado = gerar(conexao, "EMP001", ia)
    assert textos_dos_blocos(resultado) == [BLOCO_LIMPO]
    assert f"Bloco removido: usa o termo proibido \"{termo}\"." in resultado.observacoes


def test_termo_novo_publicado_na_kb_vai_para_o_pedido_e_passa_a_ser_barrado(conexao, com_o_prompt_padrao):
    """Um termo que não estava na lista entra numa versão nova da KB: o pedido o leva, e a conferência o barra."""
    termo_novo = "aprovação relâmpago"
    assert termo_novo not in kbs_endomarketing.termos_proibidos(conexao)
    # Uma linha nova na tabela dos termos, logo depois do cabeçalho
    publicar_versao_nova(conexao, kb_publicada(conexao, "GERAL", "termos_proibidos")["kb_id"], "|---|---|---|",
                         f"|---|---|---|\n| {termo_novo} | análise rápida pelo aplicativo | Promete um prazo |")
    assert termo_novo in kbs_endomarketing.termos_proibidos(conexao)
    # A IA escreve o termo novo sem acento e em maiúsculas
    ia = IaQueGuarda(resposta_com_os_textos("Novidades", [BLOCO_LIMPO, "Crédito com APROVACAO RELAMPAGO."]))
    resultado = gerar(conexao, "EMP001", ia)
    # O prompt leva a versão nova da KB, e a conferência barra o termo novo
    assert termo_novo in texto_entre(ia.chamadas[0][0], "termos_proibidos")
    assert textos_dos_blocos(resultado) == [BLOCO_LIMPO]
    assert f"Bloco removido: usa o termo proibido \"{termo_novo}\"." in resultado.observacoes


def test_a_comparacao_e_a_da_trava_palavra_inteira_sem_acento_e_sem_maiusculas():
    """Variações escritas para o teste: acento, maiúsculas, espaços e quebra de linha não escapam; outra palavra passa."""
    termos = ["retorno certeiro", "aprovação relâmpago", "sem letras miúdas"]
    assert endomarketing.termos_proibidos_no_texto("Um RETORNO CERTEIRO todo mês", termos) == ["retorno certeiro"]
    assert endomarketing.termos_proibidos_no_texto("com aprovacao   relampago,", termos) == ["aprovação relâmpago"]
    assert endomarketing.termos_proibidos_no_texto("Sem letras\nmiúdas.", termos) == ["sem letras miúdas"]
    # A palavra inteira: "retornos certeiros" é outra palavra, e não o termo
    assert endomarketing.termos_proibidos_no_texto("retornos certeiros", termos) == []
    # Dois termos no mesmo texto: os dois, na ordem da lista
    assert endomarketing.termos_proibidos_no_texto("sem letras miúdas e retorno certeiro", termos) == [
        "retorno certeiro", "sem letras miúdas"]
