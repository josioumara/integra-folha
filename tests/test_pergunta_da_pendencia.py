"""A fala do agente em cada pendência e as respostas rápidas (pendências por conversa, ADR-118).

O que estes testes provam:
- cada regra vira UMA frase natural, com o campo, a pessoa e o valor lido, terminando em "?", sem nome técnico;
- num campo de lista, o agente só dá palpite quando é seguro, e "Sim, use ..." aceita o palpite;
- as respostas rápidas são os valores da lista, a confirmação do alerta e o formato (nunca "não cadastrar");
- o Normalizador entende as variações de gênero dos campos de lista ("Solteiro(a)", "solteiro/a", "Solteira",
  "Casada" → o item da lista), mas nunca inventa um valor que não está na lista do parâmetro;
- o script que padroniza de novo os envios que ainda esperam a empresa tira a pendência que a regra nova resolve e
  não mexe em envio que já foi ao banco;
- o arquivo de um envio antigo é achado mesmo com o caminho gravado na pasta do nome antigo do projeto, e o script pula
  (sem parar) o envio cujo arquivo sumiu.
"""
from pathlib import Path

import pytest

from scripts.padronizar_de_novo_os_envios_pendentes import padronizar_de_novo_os_envios_pendentes
from services import (acompanhamento, banco, cadastro, normalizador, parametros, pergunta_da_pendencia,
                      processamentos, validador)
from tests.apoio_do_parametro import marcar_como_obrigatorios  # o estado civil é opcional no layout (ADR-143)
from tests.test_correcao import busca_falsa

# Um arquivo pequeno com o estado civil escrito com o sufixo de gênero (os CPFs são válidos e fictícios; "Casada" não
# serve: ela já estava entre os sinônimos da lista antes desta regra)
ARQUIVO_COM_ESTADO_CIVIL = ("Nome;CPF;Estado civil\n"
                            "Ana Lima;52998224725;Solteiro(a)\n"
                            "Bia Souza;11144477735;Divorciado/a\n").encode("utf-8")
# As colunas do arquivo e o campo de cada uma (o aceite da empresa)
ESCOLHAS_DO_ARQUIVO = {"Nome": "nome_completo", "CPF": "cpf", "Estado civil": "estado_civil"}


@pytest.fixture
def conexao(tmp_path):
    """Um banco novo para cada teste."""
    conexao_do_teste = banco.conectar(tmp_path / "teste.db")
    yield conexao_do_teste
    conexao_do_teste.close()


@pytest.fixture(autouse=True)
def usar_busca_falsa(monkeypatch):
    """Nenhum uso do RAG depende do índice nem do modelo de embeddings."""
    monkeypatch.setattr("rag.busca.search_rules", busca_falsa)


# ---------------- A pergunta de cada regra ----------------

def perguntar(regra_id: str, valor: str | None, mensagem: str, campo: str | None = None,
              severidade: str = "BLOQUEANTE", pessoa: str | None = None, palpite: str | None = None,
              igual_para_todos: bool = True) -> str:
    """A pergunta, com o rótulo e a descrição do campo do parâmetro de verdade, como a tela usa."""
    rotulo = acompanhamento.rotulo_do_campo(campo) if campo else ""
    descricao = acompanhamento.descricoes_dos_campos(banco.conectar(":memory:")).get(campo)
    return pergunta_da_pendencia.perguntar(regra_id, severidade, campo, rotulo, valor, mensagem, pessoa, palpite,
                                           descricao, igual_para_todos=igual_para_todos)


def test_as_frases_de_reserva_de_cada_regra():
    assert perguntar("CPF_INVALIDO", "123.456.789-00", "CPF com dígito verificador inválido.", "cpf",
                     pessoa="Maria Lima") == \
        'O CPF de Maria veio "123.456.789-00", e o dígito verificador não bate. Qual é o CPF certo?'
    assert perguntar("OBRIGATORIO_VAZIO", None, "Campo obrigatório cargo vazio.", "cargo", pessoa="Diego Azevedo") == \
        'No arquivo, Diego veio sem a informação "Cargo ou função". Qual é?'
    lista = "Valor de estado_civil não reconhecido (fora da lista aceita (Solteiro, Casado))."
    assert perguntar("VALOR_NAO_CONVERTIDO", "Solteiro(a)", lista, "estado_civil", "ALERTA", "Diego Azevedo",
                     "Solteiro") == ('Para Diego, a informação "Estado civil" veio como "Solteiro(a)", que não '
                                     'está entre as opções aceitas. Acredito que o certo é "Solteiro". Posso usar?')
    assert perguntar("VALOR_NAO_CONVERTIDO", "Salário", lista, "tipo_renda", "BLOQUEANTE", "Heloísa Reis") == \
        ('Para Heloísa, a informação "Natureza da renda" veio como "Salário", que não está entre as opções aceitas. '
         "Qual destas opções é a certa?")
    assert perguntar("RENDA_FORA_DO_CARGO", "R$ 48.000,00", "Renda 9,6x a mediana do cargo na empresa (R$ 5.000,00, "
                     "6 pessoas). Pode ser erro de digitação; se estiver certa, justifique.", "valor_renda",
                     "ALERTA", "João Silva") == \
        'A renda de João veio "R$ 48.000,00", bem acima do comum para o cargo. Está certa?'
    assert perguntar("PESSOA_DUPLICADA", "529.982.247-25", "O mesmo CPF já aparece na linha 7.", "cpf",
                     pessoa="Diego Azevedo") == \
        "Diego aparece duas vezes no arquivo (a outra é a linha 7). Posso tirar esta linha?"
    assert perguntar("DATA_AMBIGUA", "03/04/1990, 05/06/1985", "Coluna Nasc: Nenhuma data...") == \
        'As datas desta coluna vieram assim: "03/04/1990, 05/06/1985". Estão em dia/mês ou mês/dia?'
    # Sem nome (arquivo inteiro ou pessoa sem nome no arquivo): a frase segue sem ele
    assert perguntar("CPF_INVALIDO", "1", "CPF...", "cpf", pessoa="Funcionário da linha 8") == \
        'O CPF veio "1", e o dígito verificador não bate. Qual é o CPF certo?'
    # A pergunta que a própria IA fez ao ler o documento continua como ela escreveu
    assert perguntar("PERGUNTA_DA_IA:data_admissao", "01/03/2026", "A admissão é mesmo em 2026?",
                     "data_admissao", "ALERTA") == "A admissão é mesmo em 2026?"


def test_a_frase_do_arquivo_inteiro_fica_certa_com_qualquer_descricao():
    """O defeito: "...onde o funcionário trabalha de ninguém". O nome vai entre aspas, e a frase fecha."""
    assert perguntar("OBRIGATORIO_SEM_COLUNA", None, "O arquivo não traz este dado para nenhum funcionário.",
                     "codigo_unidade") == ('Nenhum funcionário deste arquivo veio com a informação "Código da unidade '
                                           'onde o funcionário trabalha". Se for a mesma para todos, qual é?')


def test_a_informacao_de_cada_pessoa_nunca_pede_um_valor_para_todos():
    """O CPF é sempre único (ADR-124). Sem a coluna do CPF, a fala diz que ele é de cada pessoa e
    pergunta se a empresa quer enviar o arquivo de novo; nunca "Se for a mesma para todos, qual é?"."""
    frase = perguntar("OBRIGATORIO_SEM_COLUNA", None,
                      "O arquivo não traz este dado para nenhum funcionário, e ele é único por funcionário.", "cpf",
                      igual_para_todos=False)
    assert frase == ('O arquivo não trouxe a informação "CPF", que é única por funcionário e não pode ser a mesma '
                     'para todos. Quer informar pessoa a pessoa ou enviar o arquivo de novo com essa coluna?')


def test_o_nome_da_informacao_vem_da_descricao_do_parametro():
    assert pergunta_da_pendencia.nome_da_informacao("Natureza da renda", "Tipo renda") == "Natureza da renda"
    assert pergunta_da_pendencia.nome_da_informacao("Data de nascimento do funcionário", "Data nascimento") == \
        "Data de nascimento"
    assert pergunta_da_pendencia.nome_da_informacao("CPF do funcionário", "CPF") == "CPF"
    assert pergunta_da_pendencia.nome_da_informacao("Código da unidade (filial) onde o funcionário trabalha",
                                                    "Código unidade") == "Código da unidade onde o funcionário trabalha"
    # Sem descrição, o rótulo curto
    assert pergunta_da_pendencia.nome_da_informacao(None, "Tipo renda") == "Tipo renda"


def test_regra_sem_pergunta_propria_usa_a_mensagem_sem_nome_tecnico():
    # O nome técnico do campo (estado_civil) vira o nome da informação entre aspas, e a pergunta vai no fim
    assert perguntar("REGRA_NOVA", None, "Campo estado_civil estranho.", "estado_civil") == \
        'Campo "Estado civil" estranho. Qual é o valor certo?'
    assert perguntar("REGRA_NOVA", None, "Algo fora do comum.", None, "ALERTA") == "Algo fora do comum. Está certo?"


def test_nenhuma_frase_de_reserva_leva_nome_tecnico_de_campo():
    """Toda regra com função própria, com qualquer campo do layout: nenhum nome técnico aparece na frase."""
    _, campos = parametros.layout_ativo(banco.conectar(":memory:"))
    for regra_id in pergunta_da_pendencia.PERGUNTA_POR_REGRA:
        for campo in campos:
            frase = perguntar(regra_id, "x", f"Mensagem sobre {campo.campo} (linha 3).", campo.campo)
            assert frase.endswith("?") and frase.count("?") == 1
            assert "_" not in frase, (regra_id, campo.campo, frase)


# ---------------- O Normalizador e as variações de gênero ----------------

def test_variacoes_de_genero_viram_o_item_da_lista():
    dominios = normalizador.carregar_dominios()
    for escrito, esperado in (("Solteiro(a)", "Solteiro"), ("solteiro/a", "Solteiro"), ("SOLTEIRO (A)", "Solteiro"),
                              ("Solteira", "Solteiro"), ("Casada", "Casado"), ("Viúva", "Viúvo"),
                              ("viuvo(a)", "Viúvo"), ("Divorciado/a", "Divorciado")):
        assert normalizador.converter_dominio(escrito, "estado_civil", dominios) == esperado


def test_variacao_de_genero_nunca_inventa_um_valor():
    dominios = normalizador.carregar_dominios()
    # Nada parecido na lista: continua recusado
    for escrito in ("Solteirx", "Noiva", "Casad(a)"):
        with pytest.raises(normalizador.NaoConvertido):
            normalizador.converter_dominio(escrito, "estado_civil", dominios)
    # A regra só troca o "a" final por "o" dentro da lista: "F" e "M" do sexo não mudam
    with pytest.raises(normalizador.NaoConvertido):
        normalizador.converter_dominio("Mulhera", "sexo", dominios)


# ---------------- Padronizar de novo os envios que esperam ----------------

def regra_antiga_de_genero(monkeypatch) -> None:
    """Faz o Normalizador voltar à regra de antes (sem as variações de gênero), como nos envios antigos."""
    monkeypatch.setattr(normalizador, "_sem_sufixo_de_genero", lambda chave: chave)
    monkeypatch.setattr(normalizador, "_forma_masculina", lambda chave: None)


def envio_com_estado_civil(conexao, conteudo: bytes = ARQUIVO_COM_ESTADO_CIVIL,
                           estado_civil_obrigatorio: bool = True) -> str:
    """O arquivo pequeno enviado e aceito pela Aurora (a padronização e a validação rodam no aceite).

    conteudo: outro arquivo com as mesmas colunas, quando o teste precisa de dois envios (o mesmo conteúdo duas vezes
    seria reconhecido como o mesmo arquivo).
    estado_civil_obrigatorio: o estado civil é opcional no layout, e um campo opcional não abre pendência (ADR-143);
    por padrão, o parâmetro deste banco de teste o marca como obrigatório, para a pergunta da pendência continuar
    testada. False deixa o parâmetro como o layout.
    """
    if estado_civil_obrigatorio:
        marcar_como_obrigatorios(conexao, "estado_civil")
    leitura = cadastro.enviar_arquivo(conexao, "EMP001", "rh.aurora", conteudo, "estado_civil.csv",
                                      busca=busca_falsa)
    processamento_id = leitura["processamento_id"]
    cadastro.aceitar_mapeamento(conexao, "EMP001", "rh.aurora", processamento_id, ESCOLHAS_DO_ARQUIVO,
                                busca=busca_falsa)
    return processamento_id


def estados_civis_em_aberto(conexao, processamento_id: str) -> list:
    """Os valores do estado civil que o Validador ainda aponta como não reconhecidos."""
    valores = []
    for achado in validador.obter(conexao, processamento_id).achados:
        if achado.regra_id == "VALOR_NAO_CONVERTIDO" and achado.campo == "estado_civil" and not achado.resolvido:
            valores.append(achado.valor)
    return valores


def test_o_script_tira_a_pendencia_que_a_regra_nova_resolve(conexao, monkeypatch):
    # Um envio padronizado com a regra antiga: os dois estados civis ficaram pendentes
    with monkeypatch.context() as trocas:
        regra_antiga_de_genero(trocas)
        processamento_id = envio_com_estado_civil(conexao)
    assert sorted(estados_civis_em_aberto(conexao, processamento_id)) == ["Divorciado/a", "Solteiro(a)"]
    # A pendência, como a tela mostra: a fala do agente, com o valor lido e o palpite seguro
    perguntas = []
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, "EMP001"):
        if pendencia["regra_id"] == "VALOR_NAO_CONVERTIDO":
            perguntas.append(pendencia["pergunta"])
    assert ('Para Ana, a informação "Estado civil" veio como "Solteiro(a)", que não está entre as opções '
            'aceitas. Acredito que o certo é "Solteiro". Posso usar?') in perguntas
    # O script, já com a regra nova: a pendência sai, e o valor padronizado é o da lista
    refeitos = padronizar_de_novo_os_envios_pendentes(conexao)
    assert len(refeitos) == 1 and refeitos[0]["pendencias_antes"] > refeitos[0]["pendencias_depois"]
    assert estados_civis_em_aberto(conexao, processamento_id) == []
    estados_civis = []
    for registro in normalizador.obter(conexao, processamento_id).registros:
        estados_civis.append(registro["estado_civil"])
    assert estados_civis == ["Solteiro", "Divorciado"]


def test_o_script_nao_mexe_em_envio_descartado(conexao, monkeypatch):
    with monkeypatch.context() as trocas:
        regra_antiga_de_genero(trocas)
        processamento_id = envio_com_estado_civil(conexao)
    # A empresa descartou o envio: ele fica como estava
    cadastro.descartar(conexao, "EMP001", processamento_id, "rh.aurora")
    assert padronizar_de_novo_os_envios_pendentes(conexao) == []


def gravar_caminho_da_pasta_antiga(conexao, processamento_id: str) -> Path:
    """Troca o caminho gravado pelo de uma pasta que não existe mais (como a do nome antigo do projeto).

    Devolve o caminho do arquivo de verdade (na pasta de uploads atual), que continua lá.
    """
    caminho_de_verdade = Path(conexao.execute("SELECT caminho_original FROM processamentos WHERE processamento_id = ?",
                                              (processamento_id,)).fetchone()[0])
    caminho_antigo = Path("D:/pasta_que_nao_existe/ai-payroll-hub/storage/uploads") / caminho_de_verdade.name
    conexao.execute("UPDATE processamentos SET caminho_original = ? WHERE processamento_id = ?",
                    (str(caminho_antigo), processamento_id))
    conexao.commit()
    return caminho_de_verdade


def test_o_arquivo_e_achado_mesmo_com_o_caminho_da_pasta_antiga(conexao):
    """O defeito achado ao rodar o script: os envios de antes da troca do nome do projeto guardaram o
    caminho com "ai-payroll-hub", que não existe mais; o arquivo continua na pasta de uploads atual, com o mesmo nome."""
    processamento_id = envio_com_estado_civil(conexao)
    gravar_caminho_da_pasta_antiga(conexao, processamento_id)
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    assert leitura.cabecalhos == ["Nome", "CPF", "Estado civil"] and len(leitura.linhas) == 2


def test_o_script_pula_o_envio_sem_arquivo_e_segue_com_os_outros(conexao, monkeypatch):
    with monkeypatch.context() as trocas:
        regra_antiga_de_genero(trocas)
        sem_arquivo = envio_com_estado_civil(conexao)
        # Um segundo arquivo, com outras pessoas (CPFs válidos e fictícios) e o mesmo jeito de escrever o estado civil
        com_arquivo = envio_com_estado_civil(conexao, ("Nome;CPF;Estado civil\n"
                                                       "Caio Reis;39053344705;Solteiro(a)\n"
                                                       "Duda Melo;16899535009;Divorciado/a\n").encode("utf-8"))
    # O original de um dos envios sumiu de todo lugar (nem no caminho gravado, nem na pasta atual)
    gravar_caminho_da_pasta_antiga(conexao, sem_arquivo).unlink()
    refeitos = {}
    for refeito in padronizar_de_novo_os_envios_pendentes(conexao):
        refeitos[refeito["processamento_id"]] = refeito
    # O envio sem arquivo fica como estava, com o motivo; o outro é refeito e perde as pendências de gênero
    assert refeitos[sem_arquivo]["pulado"] == "o arquivo original não foi encontrado"
    assert refeitos[sem_arquivo]["pendencias_depois"] == refeitos[sem_arquivo]["pendencias_antes"]
    assert refeitos[com_arquivo]["pulado"] is None
    assert estados_civis_em_aberto(conexao, com_arquivo) == []

# ---------------- O palpite seguro e as respostas rápidas ----------------

def textos(sugestoes: list[dict]) -> list[str]:
    """Só os textos das respostas rápidas."""
    lista = []
    for sugestao in sugestoes:
        lista.append(sugestao["texto"])
    return lista


def test_palpite_so_quando_e_seguro():
    dominios = normalizador.carregar_dominios()
    # Um item só casa: pelas regras da padronização ou por semelhança alta com folga
    assert normalizador.palpite_na_lista("Solteiro(a)", "estado_civil", dominios) == "Solteiro"
    assert normalizador.palpite_na_lista("Casdo", "estado_civil", dominios) == "Casado"
    # Na dúvida, sem palpite: nada parecido, dois parecidos ou campo sem lista
    assert normalizador.palpite_na_lista("Salário", "tipo_renda", dominios) is None
    assert normalizador.palpite_na_lista("Superior complet", "escolaridade", dominios) is None
    assert normalizador.palpite_na_lista("Noiva", "estado_civil", dominios) is None
    assert normalizador.palpite_na_lista("Analista", "cargo", dominios) is None


def test_com_palpite_a_primeira_resposta_aceita_e_depois_vem_a_lista():
    sugestoes = acompanhamento.sugestoes_da_pendencia("VALOR_NAO_CONVERTIDO", "confirmar", 8, "estado_civil",
                                                      "Solteiro")
    # Sem "Está certo assim", sem "Não cadastrar" e sem "Deixar em branco" (a pessoa escreve e confirma)
    assert textos(sugestoes) == ['Sim, use "Solteiro"', "Casado", "Divorciado", "Viúvo", "União estável"]
    assert all(sugestao["envia"] for sugestao in sugestoes)


def test_no_maximo_oito_respostas_rapidas():
    # A escolaridade tem 7 valores; com o palpite na frente, cabem 8
    sugestoes = acompanhamento.sugestoes_da_pendencia("VALOR_NAO_CONVERTIDO", "corrigir", 8, "escolaridade",
                                                      "Médio completo")
    assert len(sugestoes) <= acompanhamento.MAXIMO_DE_SUGESTOES
    assert textos(sugestoes)[0] == 'Sim, use "Médio completo"' and textos(sugestoes).count("Médio completo") == 0


def test_sim_use_o_palpite_corrige(conexao, monkeypatch):
    from services import assistente_na_tela
    with monkeypatch.context() as trocas:
        regra_antiga_de_genero(trocas)
        processamento_id = envio_com_estado_civil(conexao)
    pendencia = None
    for item in acompanhamento.pendencias_da_empresa(conexao, "EMP001"):
        if item["regra_id"] == "VALOR_NAO_CONVERTIDO" and item["valor_lido"] == "Divorciado/a":
            pendencia = item
    # O palpite vem na pendência e a primeira resposta rápida aceita
    assert pendencia["palpite"] == "Divorciado" and pendencia["sugestoes"][0]["texto"] == 'Sim, use "Divorciado"'
    resposta = assistente_na_tela.conversar(conexao, "EMP001", "rh.aurora", processamento_id, pendencia["regra_id"],
                                            pendencia["linha"], pendencia["sugestoes"][0]["texto"])
    assert resposta["mensagem"] == ('Pronto: troquei a informação "Estado civil" de Bia de "Divorciado/a" '
                                    'para "Divorciado".')
    assert resposta["resolvida"] is True

def test_clicar_num_valor_da_lista_corrige_e_responde_pronto(conexao, monkeypatch):
    from services import assistente_na_tela
    with monkeypatch.context() as trocas:
        regra_antiga_de_genero(trocas)
        processamento_id = envio_com_estado_civil(conexao)
    # A pendência do "Solteiro(a)" (um alerta: o estado civil não é obrigatório)
    pendencia = None
    for achado in validador.obter(conexao, processamento_id).achados:
        if achado.regra_id == "VALOR_NAO_CONVERTIDO" and achado.valor == "Solteiro(a)":
            pendencia = achado
    resposta = assistente_na_tela.conversar(conexao, "EMP001", "rh.aurora", processamento_id, pendencia.regra_id,
                                            pendencia.linha, "Solteiro")
    assert resposta["acao"] == "corrigir"
    assert resposta["mensagem"] == ('Pronto: troquei a informação "Estado civil" de Ana de "Solteiro(a)" '
                                    'para "Solteiro".')
    assert resposta["resolvida"] is True
