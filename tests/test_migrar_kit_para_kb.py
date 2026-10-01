"""A migração do kit para a KB (scripts/migrar_kit_para_kb.py): nada se perde e rodar de novo não duplica.

O banco do teste é posto como ele era antes de 30/09 (a KB do kit com o antigo campo "logo" na ficha e sem logo
anexado; o kit gravado direto no cadastro), com um caso de cada tipo:
- EMP001: o kit que o "aplicar" antigo copiou da KB (o cadastro igual à KB, com o logo do arquivo);
- EMP002: o cadastro que nunca foi mexido (o padrão, vazio), com a KB dizendo o kit próprio;
- EMP003: o kit gravado pela tela que saiu (outras cores, outro texto e outro logo);
- EMP005: a KB do kit retirada, com o kit que ficou no cadastro;
- EMP006: já no formato novo (nada a fazer);
- uma empresa nova com o kit só no cadastro (sem KB) e outra só com o padrão.
O que estes testes provam: sem --gravar nada muda; com ele, cada empresa fica com a KB certa, a arte continua com o
kit que o banco gravou (ou passa a ter o que a KB já dizia, quando o cadastro nunca foi mexido), nenhuma cor e nenhum
logo se perdem; a segunda rodada não grava nada; um caminho de pasta no antigo campo "logo" nunca é lido.
"""
import pytest

from models.contratos import Perfil
from scripts import migrar_kit_para_kb as migracao
from services import banco, endomarketing_do_banco, kbs_endomarketing, kbs_publicacao, kit_de_marca
from services import empresas as cadastro_de_empresas
from services.auth import Usuario
from tests.test_empresas import dados_da_empresa_nova

ESPECIALISTA = Usuario(login="especialista", perfil=Perfil.BANCO, empresa_id=None)
# Imagens de teste: só a assinatura do formato e alguns bytes
PNG_DA_TELA_ANTIGA = kit_de_marca.ASSINATURA_PNG + b"logo que o banco subiu pela tela que saiu"
PNG_DA_EMPRESA_NOVA = kit_de_marca.ASSINATURA_PNG + b"logo da empresa nova"


@pytest.fixture
def conexao(tmp_path, monkeypatch):
    """Um banco novo, só deste teste, sem o índice do RAG (a publicação não precisa do modelo de embeddings)."""
    monkeypatch.setattr(kbs_publicacao, "_atualizar_kb_no_indice", lambda conexao_recebida, kb_id: True)
    conexao_do_teste = banco.conectar(tmp_path / "migracao.db")
    yield conexao_do_teste
    conexao_do_teste.close()


def logo_da_pasta(empresa_id: str) -> bytes:
    """O logo.png da pasta da empresa nos arquivos do projeto."""
    return (kbs_endomarketing.PASTA_DAS_KBS / empresa_id / "logo.png").read_bytes()


def kit_como_antes(conexao, empresa_id: str) -> None:
    """A KB do kit da empresa como era antes: o campo "logo: logo.png" na ficha da versão 1, e nenhum logo anexado."""
    kb_id = f"{empresa_id}-KIT-DA-MARCA"
    conteudo = kbs_endomarketing.obter(conexao, kb_id, 1)["conteudo_md"]
    # O campo antigo entra logo antes do "---" que fecha a ficha
    antigo = conteudo.replace("\n---\n# ", "\nlogo: logo.png\n---\n# ", 1)
    conexao.execute("UPDATE kbs_endomarketing SET conteudo_md = ? WHERE kb_id = ? AND versao = 1", (antigo, kb_id))
    conexao.commit()
    kit_de_marca.tirar_logo_da_versao(conexao, kb_id, 1)


def cadastro_como_nasceu(conexao, empresa_id: str) -> None:
    """O kit do cadastro como a empresa nascia antes de 30/09: o padrão, sem texto, sem cores e sem logo."""
    cadastro_de_empresas.definir_kit(conexao, ESPECIALISTA, empresa_id, "padrao", "", [])
    kit_de_marca.tirar_logo(conexao, empresa_id)


@pytest.fixture
def banco_de_antes(conexao):
    """O banco como era antes de 30/09, com um caso de cada tipo (ver o texto do topo). Devolve os ids novos."""
    # As KBs da versão 1 e a semente das empresas entram primeiro
    kbs_endomarketing.listar(conexao)
    cadastro_de_empresas.listar(conexao)
    for empresa_id in ("EMP001", "EMP002", "EMP003", "EMP005"):
        kit_como_antes(conexao, empresa_id)
    # EMP001: o "aplicar" antigo já tinha copiado o kit da KB e o logo do arquivo (a semente deixa o cadastro assim)
    # EMP002: o cadastro nunca foi mexido
    cadastro_como_nasceu(conexao, "EMP002")
    # EMP003: a tela que saiu gravou outras cores, outro texto e outro logo
    cadastro_de_empresas.definir_kit(conexao, ESPECIALISTA, "EMP003", "proprio", "Texto da tela antiga",
                                     ["#abcdef", "#123456"])
    kit_de_marca.gravar_logo(conexao, "EMP003", PNG_DA_TELA_ANTIGA, "especialista")
    # EMP005: a KB do kit foi retirada, e o kit ficou no cadastro (o código antigo não voltava ao padrão)
    kbs_endomarketing.retirar(conexao, "especialista", "EMP005-KIT-DA-MARCA")
    cadastro_de_empresas.definir_kit(conexao, ESPECIALISTA, "EMP005", "proprio", "Prisma", ["#c2185b"])
    kit_de_marca.gravar_logo(conexao, "EMP005", logo_da_pasta("EMP005"), "especialista")
    # Uma empresa nova com o kit só no cadastro (sem KB) e outra só com o padrão
    com_kit = cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova())["empresa_id"]
    cadastro_de_empresas.definir_kit(conexao, ESPECIALISTA, com_kit, "proprio", "Logo azul da Cedro", ["#0a1b2c"])
    kit_de_marca.gravar_logo(conexao, com_kit, PNG_DA_EMPRESA_NOVA, "especialista")
    so_padrao = cadastro_de_empresas.cadastrar(conexao, ESPECIALISTA, dados_da_empresa_nova(12))["empresa_id"]
    return {"com_kit": com_kit, "so_padrao": so_padrao}


def quantas_versoes(conexao) -> int:
    """Quantas versões de KB o banco tem (todas as KBs)."""
    return conexao.execute("SELECT COUNT(*) FROM kbs_endomarketing").fetchone()[0]


def acoes(planos: list[dict]) -> dict:
    """A ação de cada empresa: {empresa_id: acao}."""
    por_empresa = {}
    for plano in planos:
        por_empresa[plano["empresa_id"]] = plano["acao"]
    return por_empresa


def test_sem_gravar_so_mostra_o_plano(conexao, banco_de_antes):
    versoes_antes = quantas_versoes(conexao)
    planos = migracao.migrar(conexao, gravar=False)
    assert acoes(planos) == {"EMP001": migracao.VERSAO_NOVA, "EMP002": migracao.VERSAO_NOVA,
                             "EMP003": migracao.VERSAO_NOVA, "EMP004": migracao.JA_ESTAVA,
                             "EMP005": migracao.RASCUNHO, "EMP006": migracao.JA_ESTAVA,
                             banco_de_antes["com_kit"]: migracao.KB_NOVA, banco_de_antes["so_padrao"]: migracao.NADA}
    # Nada foi gravado
    assert quantas_versoes(conexao) == versoes_antes
    assert cadastro_de_empresas.obter(conexao, "EMP002")["kit_escolhido"] == "padrao"
    # O relatório diz o que faria, de onde vêm o kit e o logo, sem nenhum byte de imagem
    linhas = []
    for plano in planos:
        linhas.append(migracao.linha_do_relatorio(plano))
    assert "EMP001-KIT-DA-MARCA, a partir da v1; kit: o do cadastro; logo: o do cadastro" in linhas[0]
    assert "kit: o da KB; logo: o arquivo do antigo campo \"logo\"" in linhas[1]


def test_nada_se_perde_e_a_arte_fica_com_o_kit_certo(conexao, banco_de_antes):
    migracao.migrar(conexao, gravar=True)
    # EMP001: a versão 2 publicada, sem o campo antigo, com o mesmo kit e o logo anexado; a arte não muda
    aurora = kbs_endomarketing.obter(conexao, "EMP001-KIT-DA-MARCA")
    assert (aurora["versao"], aurora["situacao"]) == (2, kbs_endomarketing.PUBLICADA) and "logo" not in aurora["ficha"]
    assert kbs_endomarketing.cores_do_kit(aurora["ficha"])[0] == "#e8772e"
    assert kbs_endomarketing.imagem_do_logo(conexao, "EMP001-KIT-DA-MARCA", 2)[0] == logo_da_pasta("EMP001")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP001")[0] == logo_da_pasta("EMP001")
    # EMP002: o cadastro nunca foi mexido: vale o que a KB dizia (o kit próprio), com o logo do campo antigo
    horizonte = kbs_endomarketing.obter(conexao, "EMP002-KIT-DA-MARCA")
    assert horizonte["versao"] == 2 and horizonte["ficha"]["kit_escolhido"] == "proprio"
    arte = endomarketing_do_banco.kit_da_empresa(conexao, "EMP002")
    assert (arte["escolhido"], arte["cor_principal"]) == ("proprio", "#0f5c8c")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP002")[0] == logo_da_pasta("EMP002")
    # EMP003: o que a tela que saiu gravou vai para a KB (as cores, o texto e o logo), e a arte continua igual
    boa_onda = kbs_endomarketing.obter(conexao, "EMP003-KIT-DA-MARCA")
    assert kbs_endomarketing.cores_do_kit(boa_onda["ficha"]) == ["#abcdef", "#123456"]
    assert kbs_endomarketing.texto_da_secao(boa_onda["corpo"], "Identidade") == "Texto da tela antiga"
    assert kbs_endomarketing.imagem_do_logo(conexao, "EMP003-KIT-DA-MARCA", 2)[0] == PNG_DA_TELA_ANTIGA
    arte = endomarketing_do_banco.kit_da_empresa(conexao, "EMP003")
    assert (arte["cor_principal"], arte["cor_escura"]) == ("#abcdef", "#123456")
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, "EMP003")[0] == PNG_DA_TELA_ANTIGA
    # As outras seções da KB da EMP003 continuam as de antes
    assert kbs_endomarketing.texto_da_secao(boa_onda["corpo"], "Tom da marca") == kbs_endomarketing.texto_da_secao(
        kbs_endomarketing.obter(conexao, "EMP003-KIT-DA-MARCA", 1)["corpo"], "Tom da marca")


def test_kb_retirada_ganha_rascunho_e_a_empresa_sem_kb_ganha_uma(conexao, banco_de_antes):
    migracao.migrar(conexao, gravar=True)
    # EMP005: a KB estava retirada: um rascunho com o kit e o logo do cadastro, e a empresa no padrão até publicar
    rascunho = kbs_endomarketing.obter(conexao, "EMP005-KIT-DA-MARCA", 2)
    assert rascunho["situacao"] == kbs_endomarketing.RASCUNHO
    assert kbs_endomarketing.cores_do_kit(rascunho["ficha"]) == ["#c2185b"] and rascunho["tem_logo"]
    assert endomarketing_do_banco.kit_da_empresa(conexao, "EMP005")["escolhido"] == "padrao"
    # A empresa nova com o kit só no cadastro ganha a KB do kit, publicada, com o logo; a arte continua igual
    com_kit = banco_de_antes["com_kit"]
    nova = kbs_endomarketing.obter(conexao, f"{com_kit}-KIT-DA-MARCA")
    assert nova["situacao"] == kbs_endomarketing.PUBLICADA and nova["ficha"]["origem"] == migracao.ORIGEM_DA_MIGRACAO
    assert kbs_endomarketing.texto_da_secao(nova["corpo"], "Identidade") == "Logo azul da Cedro"
    assert endomarketing_do_banco.kit_da_empresa(conexao, com_kit)["cor_principal"] == "#0a1b2c"
    assert endomarketing_do_banco.logo_da_empresa(conexao, ESPECIALISTA, com_kit)[0] == PNG_DA_EMPRESA_NOVA
    # A empresa só com o padrão não ganha KB
    assert kbs_endomarketing.listar(conexao, banco_de_antes["so_padrao"]) == []
    # Quem gravou e publicou fica na versão
    assert nova["versoes"][0]["publicado_por"] == migracao.AUTOR_DA_MIGRACAO


def test_rodar_de_novo_nao_grava_nada(conexao, banco_de_antes):
    migracao.migrar(conexao, gravar=True)
    versoes_depois_da_primeira = quantas_versoes(conexao)
    segunda = migracao.migrar(conexao, gravar=True)
    # Cada empresa: já estava na KB, ou nada a levar
    for plano in segunda:
        assert plano["acao"] in (migracao.JA_ESTAVA, migracao.NADA), plano["empresa_id"]
    assert quantas_versoes(conexao) == versoes_depois_da_primeira


def test_o_campo_antigo_nunca_le_um_caminho_de_pasta(tmp_path):
    """Só um nome de arquivo da pasta da empresa é lido; um caminho que sai dela, nunca."""
    assert migracao.logo_do_campo_antigo("EMP001", {"logo": "logo.png"}) == logo_da_pasta("EMP001")
    for caminho in ("../../.env", "../EMP002/logo.png", "C:\\segredo.png", "logo.gif", ""):
        assert migracao.logo_do_campo_antigo("EMP001", {"logo": caminho}) is None, caminho
    # O arquivo que não existe também não quebra
    assert migracao.logo_do_campo_antigo("EMP001", {"logo": "nao_existe.png"}) is None


def test_trocar_o_texto_de_uma_secao_so_muda_ela():
    corpo = "# Kit\n\n## Identidade\nAntigo.\nSegunda linha.\n\n## Cores\n| Uso | Cor |\n\n## Logo\nTexto."
    trocado = migracao.trocar_texto_da_secao(corpo, "Identidade", "Novo.")
    assert trocado == "# Kit\n\n## Identidade\nNovo.\n\n## Cores\n| Uso | Cor |\n\n## Logo\nTexto."
    # Sem a seção, nada muda
    assert migracao.trocar_texto_da_secao(corpo, "Não existe", "Novo.") == corpo
