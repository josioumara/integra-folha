"""A base viva: o catálogo, o gerador (semente fixa) e a carga no banco, sem IA.

O que estes testes provam:
- o catálogo é coerente: cada cargo tem um código CBO que existe e tem faixa pública, cada estilo de arquivo traz os
  4 obrigatórios, as conversas são de empresas que existem e os nomes de arquivo não têm acento nem espaço;
- o gerador é determinístico: a mesma semente refaz o mesmo conjunto, e cada empresa tem o seu sorteio (gerar só
  algumas dá as mesmas pessoas);
- os salários ficam nos degraus, dentro da faixa pública da profissão (e da referência do cargo no Validador);
- a carga, num banco temporário, leva cada envio à etapa do roteiro, sem chamar a IA e sem gravar execução de agente
  nem par no histórico de mapeamentos, e a lista de conferência bate inteira;
- a carga não duplica (roda de novo e pula), a remoção tira só a base viva, a senha vem do segredo e nunca aparece
  na saída, e a carga recusa o parâmetro que não é a v7.
Nenhum teste lê a pasta data/base_viva: cada um gera o seu conjunto numa pasta temporária (a base viva não entra na
bateria nem na avaliação).
"""
import json
from datetime import date
from decimal import Decimal

import pytest

from models.contratos import Perfil
from scripts import aplicar_parametro_adr_143, carregar_base_viva, conferir_base_viva, gerar_base_viva
from scripts import catalogos_da_base_viva as catalogos
from services import auth, banco, config, homologacao, kbs_endomarketing, llm_client, tabela_cbo, validador
from services import empresas as cadastro_de_empresas
from services.documentos import cnpj_valido
from workflows import fluxo_empresa

# A senha de teste da base viva (a de verdade só existe no .env e nunca aparece aqui)
SENHA_DE_TESTE = "senha-da-base-viva-de-teste"
# Empresas que cobrem todas as etapas: cadastrado, pendente, devolvido, parado no aceite, pronto e em análise, nos
# estilos CSV, Excel e eSocial (texto do Windows)
EMPRESAS_DO_TESTE = ["mare_mansa", "duna_clara", "pequizeiro", "carnauba_fina", "jucara_norte"]
# Poucas pessoas por envio: o teste fica rápido
LIMITE_DE_PESSOAS = 8


# ================================ O catálogo ================================

def test_cada_cargo_tem_um_cbo_que_existe_e_tem_faixa_publica():
    publicas = gerar_base_viva.faixas_publicas()
    for cargo, profissao in catalogos.PROFISSOES.items():
        # O código está na tabela oficial e tem a faixa calculada da RAIS
        assert tabela_cbo.existe(profissao["cbo"]), cargo
        assert profissao["cbo"] in publicas, cargo
    # Todo cargo dos setores está nas profissões
    for setor, cargos in catalogos.CARGOS_POR_SETOR.items():
        for cargo, _peso in cargos:
            assert cargo in catalogos.PROFISSOES, (setor, cargo)


def test_as_empresas_do_catalogo_sao_coerentes():
    chaves, nomes = set(), set()
    for empresa in catalogos.EMPRESAS:
        chaves.add(empresa["chave"])
        nomes.add(empresa["nome"])
        # O setor dos cargos e o estilo do arquivo existem; a UF tem 2 letras
        assert empresa["cargos"] in catalogos.CARGOS_POR_SETOR
        assert empresa["estilo"] in catalogos.ESTILOS_DE_ARQUIVO
        assert len(empresa["uf"]) == 2
        # O primeiro envio é a carga inicial; os outros, inclusões, do mais antigo ao mais recente
        tipos = []
        for envio in empresa["envios"]:
            tipos.append(envio["tipo"])
        assert tipos[0] == "INICIAL" and "INICIAL" not in tipos[1:]
        dias = []
        for envio in empresa["envios"]:
            dias.append(envio["dias_uteis"])
        assert dias == sorted(dias, reverse=True) and min(dias) >= 1
    # 17 empresas, sem repetir a chave nem o nome
    assert len(catalogos.EMPRESAS) == 17 and len(chaves) == 17 and len(nomes) == 17
    # As conversas são de empresas que existem
    for conversa in catalogos.CONVERSAS:
        assert conversa["empresa"] in chaves


def test_todo_estilo_traz_os_4_obrigatorios_e_nomes_de_arquivo_sem_acento():
    for estilo, definicao in catalogos.ESTILOS_DE_ARQUIVO.items():
        campos = set()
        for _cabecalho, campo in definicao["colunas"]:
            campos.add(campo)
        assert carregar_base_viva.OBRIGATORIOS_DA_V7 <= campos, estilo
    for inicial, inclusao in gerar_base_viva.NOMES_DOS_ARQUIVOS.values():
        for nome in (inicial, inclusao.format(numero=2)):
            assert nome.isascii() and " " not in nome, nome


# ================================ O gerador ================================

def test_degraus_de_salario_ficam_dentro_das_faixas():
    publicas = gerar_base_viva.faixas_publicas()
    de_referencia = validador.faixas_de_referencia()
    for cargo, profissao in catalogos.PROFISSOES.items():
        degraus = gerar_base_viva.degraus_de_salario(cargo, publicas, de_referencia)
        # Do menor para o maior, nunca abaixo do piso
        assert degraus == sorted(degraus) and degraus[0] >= gerar_base_viva.PISO_SALARIAL, cargo
        if profissao["tipo_renda"] == "PRO_LABORE":
            continue
        minimo, maximo = publicas[profissao["cbo"]]
        assert minimo <= degraus[0] and degraus[-1] <= maximo, cargo
        # Com a referência do cargo no Validador, também dentro dela
        referencia = de_referencia.get((cargo, "CLT"))
        if referencia is not None:
            assert referencia["faixa_minima"] <= degraus[0] and degraus[-1] <= referencia["faixa_maxima"], cargo


def test_documentos_e_datas_do_gerador():
    # A filial tem a raiz da sede e o verificador certo
    filial = gerar_base_viva.cnpj_com_a_mesma_raiz("10433218000193", 2)
    assert filial[:8] == "10433218" and filial[8:12] == "0002" and cnpj_valido(filial)
    # O erro de digitação do CBO é um código que não existe
    assert not tabela_cbo.existe(gerar_base_viva._cbo_que_nao_existe("411010"))
    # Os dias úteis pulam o fim de semana: quarta 30/09/2026 → sexta 25/09 com 3 dias úteis
    assert gerar_base_viva.dia_util_antes(date(2026, 9, 30), 3) == date(2026, 9, 25)
    # Passar do fim do expediente leva ao começo do dia útil seguinte, e nunca depois de ontem (dia 1)
    assert gerar_base_viva._depois(5, 17 * 60, 120) == (4, gerar_base_viva.INICIO_DO_EXPEDIENTE + 30)
    assert gerar_base_viva._depois(1, 18 * 60, 120) == (1, gerar_base_viva.FIM_DO_EXPEDIENTE)
    # O dinheiro e o CBO em cada jeito dos sistemas de RH
    assert gerar_base_viva._dinheiro_no_estilo(Decimal("3450.00"), "brasileiro_com_milhar") == "3.450,00"
    assert gerar_base_viva._cbo_no_estilo("411010", "com_ponto") == "4110.10"


def test_a_semente_refaz_o_mesmo_conjunto_e_cada_empresa_tem_o_seu_sorteio(tmp_path):
    primeiro = gerar_base_viva.gerar(tmp_path / "a", chaves=["jacamim", "garoa"], limite=5)
    segundo = gerar_base_viva.gerar(tmp_path / "b", chaves=["jacamim", "garoa"], limite=5)
    assert primeiro == segundo
    # Os arquivos CSV saem byte a byte iguais
    for envio in primeiro["empresas"][0]["envios"]:
        assert (tmp_path / "a" / envio["arquivo"]).read_bytes() == (tmp_path / "b" / envio["arquivo"]).read_bytes()
    # Gerar só a garoa dá a mesma garoa
    so_a_garoa = gerar_base_viva.gerar(tmp_path / "c", chaves=["garoa"], limite=5)
    assert so_a_garoa["empresas"][0] == primeiro["empresas"][1]


def test_o_roteiro_completo_segue_o_catalogo(tmp_path):
    roteiro = gerar_base_viva.gerar(tmp_path)
    resumo = gerar_base_viva.resumo(roteiro)
    assert resumo["empresas"] == 17
    assert resumo["envios_por_destino"] == {"CADASTRADO": 31, "EM_ANALISE": 5, "PENDENTE": 4, "PRONTO": 1,
                                            "DEVOLVIDO": 1, "NO_ACEITE": 1}
    # De 3 a 5 mil pessoas, e cada empresa com um domínio reservado e um CNPJ válido
    assert 3000 <= resumo["pessoas_novas"] <= 5000
    for empresa in roteiro["empresas"]:
        assert empresa["dominio_email"].endswith(".example") and cnpj_valido(empresa["cnpj"])
        assert empresa["login"].startswith("rh.")
        for envio in empresa["envios"]:
            # Os momentos de cada envio andam para a frente (menos dias úteis antes da carga = mais recente)
            momentos = []
            for etapa in ("recebido", "aceite", "correcoes", "enviado", "decisao"):
                if etapa in envio["linha_do_tempo"]:
                    momento = envio["linha_do_tempo"][etapa]
                    momentos.append((-momento["dias_uteis"], momento["hora"]))
            assert momentos == sorted(momentos), envio["arquivo"]


# ================================ A carga ================================

@pytest.fixture
def banco_da_base_viva(tmp_path, monkeypatch):
    """Um banco SQLite novo, só deste teste, que também é o banco "padrão" (a lista de empresas em memória o relê).

    Com o parâmetro da v7 (4 obrigatórios), um login do banco e o da Aurora, e as pastas dos arquivos e do fluxo
    também temporárias.
    """
    monkeypatch.setattr(config, "CAMINHO_BANCO", tmp_path / "base_viva.db")
    monkeypatch.setattr(config, "CAMINHO_CHECKPOINTS", tmp_path / "checkpoints.db")
    monkeypatch.setattr(config, "PASTA_UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(homologacao, "PASTA_HOMOLOGADOS", tmp_path / "homologados")
    cadastro_de_empresas.esquecer_lista_em_memoria()
    conexao = banco.conectar()
    auth.preparar_tabela(conexao)
    auth.cadastrar_usuario(conexao, "especialista.banco", "senha-do-banco-de-teste", Perfil.BANCO)
    auth.cadastrar_usuario(conexao, "empresa.aurora", "senha-da-aurora-de-teste", Perfil.EMPRESA, "EMP001")
    aplicar_parametro_adr_143.aplicar(conexao)
    yield conexao
    conexao.close()
    cadastro_de_empresas.esquecer_lista_em_memoria()


@pytest.fixture
def roteiro_do_teste(tmp_path):
    """O roteiro de 5 empresas, com poucas pessoas por envio, numa pasta temporária."""
    pasta = tmp_path / "base_viva"
    return pasta, gerar_base_viva.gerar(pasta, chaves=EMPRESAS_DO_TESTE, limite=LIMITE_DE_PESSOAS)


def _ia_proibida(*_argumentos, **_nomeados):
    """No lugar da IA durante a carga: se alguém chamar, o teste quebra."""
    raise AssertionError("A carga da base viva chamou a IA.")


def test_carga_sem_ia_leva_cada_envio_a_sua_etapa_e_a_conferencia_bate(banco_da_base_viva, roteiro_do_teste,
                                                                      monkeypatch):
    pasta, roteiro = roteiro_do_teste
    monkeypatch.setattr(llm_client.LLMClient, "gerar", _ia_proibida)
    linhas_escritas = []
    resumo = carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE, escrever=linhas_escritas.append)
    assert len(resumo["carregadas"]) == len(EMPRESAS_DO_TESTE) and resumo["puladas"] == []
    # A lista de conferência inteira bate (com poucas pessoas, a faixa das outras empresas pode não ligar)
    itens = conferir_base_viva.conferir(banco_da_base_viva, roteiro, minimo_de_profissoes_ligadas=0)
    falhas = []
    for item in itens:
        if not item["bateu"]:
            falhas.append(item)
    assert falhas == []
    # O kit próprio virou a KB do kit, publicada (a fonte única), e o cadastro tem as cores dela; o padrão não tem KB
    for empresa in roteiro["empresas"]:
        empresa_id = banco_da_base_viva.execute("SELECT empresa_id FROM empresas WHERE cnpj = ?",
                                                (empresa["cnpj"],)).fetchone()[0]
        kits = [kb for kb in kbs_endomarketing.listar(banco_da_base_viva, empresa_id) if kb["tipo"] == "kit_da_marca"]
        if empresa["kit"]["escolhido"] == "proprio":
            assert len(kits) == 1 and kits[0]["versao_publicada"] == 1, empresa["nome"]
            assert cadastro_de_empresas.obter(banco_da_base_viva, empresa_id)["kit_cores"] == empresa["kit"]["cores"]
        else:
            assert kits == [], empresa["nome"]
    # A senha nunca aparece na saída
    assert SENHA_DE_TESTE not in json.dumps(linhas_escritas + [resumo], ensure_ascii=False)
    # O RH entra com a senha única, que é definitiva (não pede troca)
    usuario = auth.autenticar(banco_da_base_viva, "rh.maremansa", SENHA_DE_TESTE)
    assert usuario is not None and usuario.perfil == Perfil.EMPRESA and not usuario.senha_provisoria


def test_carga_roda_de_novo_sem_duplicar_e_a_remocao_tira_so_a_base_viva(banco_da_base_viva, roteiro_do_teste):
    pasta, _roteiro = roteiro_do_teste
    carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE)
    envios_depois_da_primeira = banco_da_base_viva.execute("SELECT COUNT(*) FROM processamentos").fetchone()[0]
    # A segunda carga pula todas as empresas e não grava nada de novo
    segunda = carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE)
    assert segunda["carregadas"] == [] and len(segunda["puladas"]) == len(EMPRESAS_DO_TESTE)
    assert banco_da_base_viva.execute("SELECT COUNT(*) FROM processamentos").fetchone()[0] == envios_depois_da_primeira
    # Um envio qualquer, para conferir depois que o fluxo e os arquivos dele sumiram
    processamento_id = banco_da_base_viva.execute("SELECT processamento_id FROM homologacoes").fetchone()[0]
    ids_da_base_viva = []
    for empresa in carregar_base_viva.empresas_da_base_viva(banco_da_base_viva):
        ids_da_base_viva.append(empresa["empresa_id"])
    apagadas = carregar_base_viva.remover(banco_da_base_viva)
    assert apagadas["empresas"] == len(EMPRESAS_DO_TESTE) and apagadas["usuarios"] == len(EMPRESAS_DO_TESTE)
    # As KBs do kit da base viva saíram junto (as duas de kit próprio do teste), com os logos das versões
    assert apagadas["kbs_endomarketing"] == 2 and apagadas["logos_das_kbs"] == 0
    for empresa_id in ids_da_base_viva:
        assert kbs_endomarketing.listar(banco_da_base_viva, empresa_id) == [], empresa_id
    # Nada da base viva ficou: nem empresa, nem envio, nem sessão, nem fluxo, nem arquivo
    assert carregar_base_viva.empresas_da_base_viva(banco_da_base_viva) == []
    assert banco_da_base_viva.execute("SELECT COUNT(*) FROM processamentos").fetchone()[0] == 0
    assert banco_da_base_viva.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0] == 0
    assert not fluxo_empresa.situacao(banco_da_base_viva, processamento_id)["iniciado"]
    assert list(config.PASTA_UPLOADS.glob(processamento_id + ".*")) == []
    # As 6 empresas fictícias e os logins da demo continuam lá
    assert len(cadastro_de_empresas.listar(banco_da_base_viva)) == 6
    assert auth.autenticar(banco_da_base_viva, "especialista.banco", "senha-do-banco-de-teste") is not None
    # E dá para carregar de novo depois de remover
    assert len(carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE)["carregadas"]) == len(
        EMPRESAS_DO_TESTE)


def test_a_mesma_senha_nos_logins_da_demo_so_com_a_opcao(banco_da_base_viva, tmp_path):
    pasta = tmp_path / "uma_empresa"
    gerar_base_viva.gerar(pasta, chaves=["cantaria"], limite=3)
    carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE)
    # Sem a opção, os logins da demo continuam com a senha deles
    assert auth.autenticar(banco_da_base_viva, "empresa.aurora", SENHA_DE_TESTE) is None
    resumo = carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE, tambem_logins_da_demo=True)
    assert sorted(resumo["logins_da_demo"]) == ["empresa.aurora", "especialista.banco"]
    usuario = auth.autenticar(banco_da_base_viva, "especialista.banco", SENHA_DE_TESTE)
    assert usuario is not None and not usuario.senha_provisoria


def test_carga_recusa_sem_senha_parametro_antigo_e_empresa_pela_metade(banco_da_base_viva, tmp_path):
    pasta = tmp_path / "uma_empresa"
    gerar_base_viva.gerar(pasta, chaves=["cantaria"], limite=3)
    # Sem a senha: recusa antes de gravar qualquer coisa
    with pytest.raises(carregar_base_viva.CargaRecusada, match="SENHA_DA_BASE_VIVA"):
        carregar_base_viva.carregar(banco_da_base_viva, pasta, "")
    assert carregar_base_viva.empresas_da_base_viva(banco_da_base_viva) == []
    # Uma empresa que ficou pela metade (um envio a menos): pede para remover e carregar de novo
    carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE)
    banco_da_base_viva.execute("DELETE FROM processamentos")
    banco_da_base_viva.commit()
    with pytest.raises(carregar_base_viva.CargaRecusada, match="--remover"):
        carregar_base_viva.carregar(banco_da_base_viva, pasta, SENHA_DE_TESTE)


def test_carga_recusa_o_parametro_que_nao_e_a_v7(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CAMINHO_BANCO", tmp_path / "v1.db")
    cadastro_de_empresas.esquecer_lista_em_memoria()
    conexao = banco.conectar()
    # O parâmetro padrão das bases novas é o layout v1, com 24 obrigatórios
    with pytest.raises(carregar_base_viva.CargaRecusada, match="4 obrigatórios"):
        carregar_base_viva.conferir_o_parametro(conexao)
    conexao.close()
    cadastro_de_empresas.esquecer_lista_em_memoria()


def test_momento_real_usa_os_dias_uteis_e_o_horario_de_brasilia():
    momento = carregar_base_viva.momento_real({"dias_uteis": 2, "hora": "10:15"}, date(2026, 9, 30))
    # Segunda 28/09/2026, 10:15 em Brasília = 13:15 no horário universal
    assert momento.isoformat() == "2026-09-28T13:15:00+00:00"
