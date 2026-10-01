"""O Assistente de Correção nas telas do Integra Folha (Cadastrar e Acompanhar), pela API.

Para que serve (pendências por conversa): a empresa resolve cada pendência
CONVERSANDO com a IA, sem campo para digitar. Ela explica ("o CPF certo é 529.982.247-25", "não cadastrar esta
pessoa", "está certo assim") e a aplicação já ajusta, com "Desfazer" à mão. As portas que o front usa:
    1. conversar: a empresa escreve sobre a pendência; o agente (agents/assistente_correcao.py) escolhe a ação e,
       quando ela muda um dado, este arquivo APLICA na hora e devolve o que mudou e como desfazer;
    2. confirmar_retirada: "não cadastrar" e "deixar em branco" não valem na hora; a pessoa confirma (ou cancela), e a
       resposta entra na trilha de auditoria;
    3. desfazer: volta a troca (ou a confirmação, ou o "preencher para todos") e valida o envio de novo;
    4. pessoas_para_informar e informar_por_pessoa (ADR-124): quando a coluna que o arquivo inteiro não trouxe não é
       a mesma para todos, ou é de cada pessoa, a empresa informa o valor de cada funcionário numa lista do cartão.
    Pendências em grupo (ADR-120): quando várias pessoas vieram com o mesmo valor fora da lista, a tela mostra um cartão
    só; a mensagem dele chega com em_grupo=True, e o valor vale para todas (com um Desfazer para o grupo inteiro).

As regras que protegem a empresa e o dado:
    - a pendência é montada AQUI, a partir do relatório do Validador: o navegador só diz qual é (regra e linha), e não
      consegue mandar um texto qualquer como se fosse a pendência;
    - a conversa é presa à informação da pendência: o agente recusa outro campo, outra linha ou outra coluna
      ("fora do assunto") e nada muda;
    - a mensagem da empresa é a decisão dela (substitui o clique em "Aplicar" do ADR-16 nesta tela): fica registrado
      quem pediu (o login), o antes, o depois e a frase dela como motivo; tudo pode ser desfeito;
    - o valor da pendência vai como está para a IA (ADR-101: a IA roda pelo AWS Bedrock); a mensagem da empresa
      passa pelo guardrail de injeção dentro do agente;
    - só vale enquanto o envio está na correção ou na conferência (antes de ir ao banco);
    - o valor que a empresa escreve passa por TODAS as regras do campo antes de a pendência sair da lista (ADR-153):
      a padronização e o dígito antes da troca e, depois dela, o relatório refeito pelo Validador de verdade (a CBO
      oficial, a pessoa repetida, o outro envio...). Se o valor não passar, a troca volta na hora, o agente explica o
      que está errado, com um exemplo, e a pendência continua aberta: nenhum cartão novo nasce desse valor;
    - toda pergunta do agente sobre uma pessoa mostra a informação e o que veio no arquivo (ou que veio vazio); depois
      de LIMITE_DE_RESPOSTAS_SEM_VALOR respostas sem valor ("não sei", "não tenho"), o agente para de insistir e
      encerra a conversa com educação, e a pendência continua aberta (ADR-153).

Exemplo de uso:
    resposta = conversar(conexao, "EMP001", "rh.aurora", "a1b2c3", "CPF_INVALIDO", 8, "o certo é 529.982.247-25")
    if resposta["aplicado"] and resposta["aplicado"]["desfazer"]:
        desfazer(conexao, "EMP001", "rh.aurora", "a1b2c3", resposta["aplicado"]["desfazer"]["tipo"],
                 resposta["aplicado"]["desfazer"]["id"])
"""
from agents import assistente_correcao
from models.contratos import TipoCampo
from services import (acompanhamento, auditoria, cadastro, coluna_do_campo_que_falta, conferencia_do_valor,
                      conversas_das_pendencias, correcoes, dados_da_empresa_no_envio, devolucao_por_pessoa,
                      parametros, pendencias_em_grupo, pergunta_da_pendencia, processamentos, validador)
from workflows import fluxo_empresa

# O maior texto que a empresa pode mandar numa mensagem (uma pergunta, não um documento)
TAMANHO_MAXIMO_DA_MENSAGEM = 1000
# O maior motivo guardado numa correção ou confirmação (o mesmo limite das outras telas)
TAMANHO_MAXIMO_DO_MOTIVO = 300
# Os tipos de "Desfazer" que a tela pode pedir
DESFAZER_CORRECAO = "correcao"
DESFAZER_PARA_TODOS = "para_todos"
DESFAZER_CONFIRMACAO = "confirmacao"
DESFAZER_GRUPO = "grupo"
DESFAZER_POR_PESSOA = "por_pessoa"
DESFAZER_COLUNA = "coluna"
DESFAZER_DADOS_DA_EMPRESA = dados_da_empresa_no_envio.DESFAZER_DADOS_DA_EMPRESA
# Como a escolha de formato aparece no resumo
FORMATO_PARA_A_EMPRESA = {"DMY": "datas em dia/mês (DD/MM/AAAA)", "MDY": "datas em mês/dia (MM/DD/AAAA)"}
# Quantas respostas sem valor ("não sei", "não tenho", "prefiro não informar") a conversa de uma pendência aceita: na
# última, o agente para de insistir, agradece e encerra; a pendência continua aberta (ADR-153)
LIMITE_DE_RESPOSTAS_SEM_VALOR = 3


def _conferir_envio_e_etapa(conexao, empresa_id: str, processamento_id: str) -> None:
    """Confere que o envio é da empresa e que ele está na correção ou na conferência (antes de ir ao banco).

    Levanta KeyError (envio de outra empresa ou inexistente) ou ValueError (etapa que não permite a conversa).
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    etapa = fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"]
    if etapa not in cadastro.ETAPAS_DA_CONFERENCIA:
        raise ValueError("O assistente ajuda nas pendências enquanto o envio não foi para o banco.")


def _achado_em_aberto(conexao, processamento_id: str, regra_id: str, linha: int | None, campo: str | None = None):
    """O achado do Validador com esta regra, esta linha e este campo ainda sem resolução, ou None.

    Por que o campo: a mesma regra pode aparecer várias vezes na mesma
    linha, uma por campo. Ex.: o arquivo sem 11 colunas obrigatórias gera 11 "OBRIGATORIO_SEM_COLUNA" no arquivo
    inteiro; só a regra e a linha misturavam os 11 cartões (a mesma conversa, a mesma pergunta, e o valor podia ir
    para outro campo). Sem campo (pedido de uma tela antiga), vale o primeiro achado da regra e da linha.
    """
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return None
    for achado in relatorio.achados:
        # A mesma regra, na mesma linha, no mesmo campo, e ainda sem resolução
        mesmo_campo = campo is None or achado.campo == campo
        if achado.regra_id == regra_id and achado.linha == linha and mesmo_campo and not achado.resolvido:
            return achado
    return None


def pendencia_do_validador(conexao, processamento_id: str, regra_id: str, linha: int | None,
                           campo: str | None = None) -> dict:
    """A pendência em aberto, montada a partir do relatório do Validador (nunca a partir do que o navegador mandou).

    Recebe: a regra, a linha (None = pendência do arquivo inteiro) e o campo da pendência.
    Devolve: {regra_id, severidade, campo, linha, mensagem, valor}, o formato que o agente recebe.
    Levanta ValueError se não há pendência aberta com essa regra, essa linha e esse campo.
    """
    achado = _achado_em_aberto(conexao, processamento_id, regra_id, linha, campo)
    if achado is None:
        raise ValueError("Esta pendência não está mais em aberto. Atualize a página.")
    # Se a informação pode ser a mesma para todos (dado da empresa) ou é de cada pessoa: o agente lê, e a trava do
    # "preencher para todos" usa (a marcação do parâmetro). None sem campo
    igual_para_todos = None
    if achado.campo:
        igual_para_todos = achado.campo in parametros.campos_iguais_para_todos(conexao)
    return {"regra_id": achado.regra_id, "severidade": achado.severidade, "campo": achado.campo,
            "linha": achado.linha, "mensagem": achado.mensagem, "valor": achado.valor,
            "igual_para_todos": igual_para_todos}


def _nome_da_pessoa(conexao, processamento_id: str, linha: int | None) -> str:
    """O nome da pessoa da linha, com as correções aplicadas. Ex.: 8 → "Ana Souza"; None → "o arquivo inteiro"."""
    if linha is None:
        return "o arquivo inteiro"
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] == linha and registro.get("nome_completo"):
            return registro["nome_completo"]
    return "a pessoa da linha " + str(linha)


def _informacao(conexao, campo: str | None) -> str:
    """O nome do campo nas falas do agente, pela descrição do parâmetro (a mesma das perguntas).

    Ex.: "estado_civil" → "Estado civil"; "codigo_unidade" → "Código da unidade onde o funcionário trabalha";
    None → "Este dado".
    """
    if not campo:
        return "Este dado"
    descricao = acompanhamento.descricoes_dos_campos(conexao).get(campo)
    return pergunta_da_pendencia.nome_da_informacao(descricao, acompanhamento.rotulo_do_campo(campo))

def _campo_e_obrigatorio(conexao, campo: str | None) -> bool:
    """True se o campo é obrigatório no layout ativo (não pode ficar em branco)."""
    _, campos = parametros.layout_ativo(conexao)
    for campo_do_layout in campos:
        if campo_do_layout.campo == campo:
            return campo_do_layout.obrigatorio
    return False


def _para_a_tela(campo: str | None, valor) -> str:
    """Um valor como a empresa lê (CPF com pontos, data dd/mm/aaaa, renda em reais), ou "(vazio)" sem valor."""
    texto = None
    if valor is not None:
        texto = acompanhamento.valor_lido_para_a_tela(campo, str(valor))
    return texto or "(vazio)"


def _motivo(mensagem_da_empresa: str) -> str:
    """O motivo guardado na correção: a frase da empresa (ela é a decisão), no limite de tamanho."""
    return ("Pedido na conversa com o Agente de validação: " + mensagem_da_empresa)[:TAMANHO_MAXIMO_DO_MOTIVO]


def _plural_de_funcionarios(quantidade: int) -> str:
    """ "1 funcionário" ou "N funcionários"."""
    if quantidade == 1:
        return "1 funcionário"
    return f"{quantidade} funcionários"


# ---------------- As ações que mudam dado (aplicadas na hora, com "Desfazer") ----------------

def _aplicar_correcao(conexao, empresa_id, login, processamento_id, pendencia, valor, mensagem_da_empresa) -> tuple:
    """Troca o valor do campo da pendência por um valor novo (não vazio). Devolve (a fala, o aplicado)."""
    campo = pendencia["campo"]
    # O pedido (em nome de quem escreveu) e a aplicação, com a revalidação do envio
    correcao = correcoes.propor(conexao, processamento_id, empresa_id, pendencia["linha"], campo, valor,
                                _motivo(mensagem_da_empresa), f"assistente (para {login})")
    correcoes.decidir(conexao, processamento_id, empresa_id, correcao.correcao_id, True, login)
    # O antes: o valor da pessoa; se o arquivo trouxe algo que não deu para entender, o que veio no arquivo
    antes_no_arquivo = correcao.antes
    if antes_no_arquivo is None:
        antes_no_arquivo = pendencia.get("valor")
    antes = _para_a_tela(campo, antes_no_arquivo)
    depois = _para_a_tela(campo, correcao.depois)
    # A fala diz exatamente o que mudou: de quem, o campo, o antes e o depois
    fala = _fala_da_troca(_a_informacao_de_quem(conexao, processamento_id, campo, pendencia["linha"]), antes, depois)
    aplicado = {"resumo": f"{_informacao(conexao, campo)}: {antes} → {depois}",
                "desfazer": {"tipo": DESFAZER_CORRECAO, "id": correcao.correcao_id}}
    return fala, aplicado


def _fala_da_troca(a_informacao_de_quem: str, antes: str, depois: str) -> str:
    """A fala do agente depois de uma troca, dizendo exatamente o que mudou.

    Ex.: ('a informação "Estado civil" de Ana', "Solteirx", "Solteiro") →
    'Pronto: troquei a informação "Estado civil" de Ana de "Solteirx" para "Solteiro".'; sem o antes ("(vazio)"):
    'Pronto: preenchi a informação "Cargo" de Ana com "Analista".'
    """
    if antes == "(vazio)":
        return f'Pronto: preenchi {a_informacao_de_quem} com "{depois}".'
    return f'Pronto: troquei {a_informacao_de_quem} de "{antes}" para "{depois}".'


# ---------------- Não subir uma informação: pede confirmação antes ----------------

def e_retirada(acao: str, valor: str | None) -> bool:
    """True se a decisão tira algo do envio: a pessoa inteira ("nao_cadastrar") ou o dado ("corrigir" com vazio)."""
    return acao == "nao_cadastrar" or (acao == "corrigir" and not (valor or "").strip())


def _correcao_e_retirada(correcao) -> bool:
    """True se a correção tira a pessoa inteira ou deixa o campo em branco."""
    return correcao.campo == correcoes.EXCLUIR or correcao.depois is None


def _a_informacao_de_quem(conexao, processamento_id: str, campo: str, linha: int | None) -> str:
    """ 'a informação "Estado civil" de Diego': o campo entre aspas (nunca erra o gênero) e o primeiro nome.

    Sem linha (pendência do arquivo inteiro): só 'a informação "Estado civil"'.
    """
    if linha is None:
        return f'a informação "{_informacao(conexao, campo)}"'
    nome = pergunta_da_pendencia.primeiro_nome(_nome_da_pessoa(conexao, processamento_id, linha))
    de_quem = "de " + nome if nome else "desta pessoa"
    return f'a informação "{_informacao(conexao, campo)}" {de_quem}'

def _pedir_confirmacao(conexao, empresa_id, login, processamento_id, pendencia, acao, mensagem_da_empresa) -> tuple:
    """Registra a retirada como PROPOSTA (nada muda ainda) e monta a pergunta de confirmação.

    Devolve: (a fala, a confirmacao {correcao_id, sim, nao}), ou (a fala, None) quando não dá para retirar (campo
    obrigatório não fica em branco). Quem decide é a pessoa, pela rota /assistente/confirmar.
    """
    linha = pendencia["linha"]
    # Deixar em branco: campo obrigatório não pode, e a conversa continua
    if acao == "corrigir" and _campo_e_obrigatorio(conexao, pendencia["campo"]):
        informacao = _informacao(conexao, pendencia["campo"])
        return (f'A informação "{informacao}" é obrigatória e não pode ficar em branco. Qual é o valor certo?', None)
    # A retirada fica PROPOSTA, em nome de quem escreveu (o dado ainda não muda)
    campo = correcoes.EXCLUIR if acao == "nao_cadastrar" else pendencia["campo"]
    correcao = correcoes.propor(conexao, processamento_id, empresa_id, linha, campo, None,
                                _motivo(mensagem_da_empresa), f"assistente (para {login})")
    if acao == "nao_cadastrar":
        nome = pergunta_da_pendencia.primeiro_nome(_nome_da_pessoa(conexao, processamento_id, linha)) or "esta pessoa"
        fala = f"Confirma que não vamos cadastrar {nome} neste envio? Fica registrado com o seu nome."
        sim = "Sim, não cadastrar"
    else:
        fala = (f"Confirma que {_a_informacao_de_quem(conexao, processamento_id, campo, linha)} não vai para o banco? "
                "Fica registrado com o seu nome.")
        sim = "Sim, deixar em branco"
    return fala, {"correcao_id": correcao.correcao_id, "sim": sim, "nao": "Cancelar"}


def _detalhe_da_retirada(login: str, correcao) -> dict:
    """O que a trilha de auditoria guarda de uma retirada: quem, a linha, o campo (ou a pessoa inteira) e a frase da
    pessoa como motivo. Nenhum valor pessoal: nem o valor que saiu, nem o nome."""
    campo = "pessoa inteira" if correcao.campo == correcoes.EXCLUIR else correcao.campo
    return {"login": login, "linha": correcao.linha, "campo": campo, "motivo": correcao.motivo}


def _sobrou_pendencia_na_celula(conexao, processamento_id: str, correcao) -> bool:
    """True se a linha (pessoa inteira) ou a célula (linha e campo) da correção ainda tem pendência em aberto."""
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return False
    for achado in relatorio.achados:
        pede_acao = achado.severidade == validador.BLOQUEANTE or (achado.severidade == validador.ALERTA
                                                                  and not achado.resolvido)
        mesma_celula = correcao.campo == correcoes.EXCLUIR or achado.campo == correcao.campo
        if pede_acao and achado.linha == correcao.linha and mesma_celula:
            return True
    return False


def confirmar_retirada(conexao, empresa_id: str, login: str, processamento_id: str, correcao_id: str,
                       confirmar: bool) -> dict:
    """A resposta da pessoa à pergunta de confirmação: "Sim, não cadastrar" / "Sim, deixar em branco" ou "Cancelar".

    Recebe: o envio; a correção PROPOSTA que a conversa criou; confirmar — True aplica, False cancela.
    Devolve: {mensagem, aplicado ({resumo, desfazer} ou None), resolvida}. Confirmar aplica, valida de novo e deixa
    "Desfazer" à mão; cancelar deixa tudo como estava ("Tudo bem, nada mudou.").
    As duas respostas entram na trilha de auditoria do envio (RETIRADA_CONFIRMADA_PELA_EMPRESA ou
    RETIRADA_CANCELADA_PELA_EMPRESA), com quem, a linha, o campo e a frase da pessoa, sem valor pessoal.
    Levanta KeyError (outra empresa) ou ValueError (etapa errada, nada esperando confirmação com esse id).
    """
    _conferir_envio_e_etapa(conexao, empresa_id, processamento_id)
    correcao = None
    for proposta in correcoes.listar(conexao, processamento_id, "PROPOSTA"):
        if proposta.correcao_id == correcao_id and _correcao_e_retirada(proposta):
            correcao = proposta
    if correcao is None:
        raise ValueError("Não há nada esperando a sua confirmação. Atualize a página.")
    # Cancelar: nada muda, e a resposta fica registrada
    if not confirmar:
        correcoes.decidir(conexao, processamento_id, empresa_id, correcao_id, False, login)
        auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "RETIRADA_CANCELADA_PELA_EMPRESA",
                            _detalhe_da_retirada(login, correcao))
        resposta = {"mensagem": "Tudo bem, nada mudou.", "aplicado": None, "resolvida": False}
        conversas_das_pendencias.registrar_a_confirmacao(conexao, processamento_id, correcao_id,
                                                         _texto_da_escolha(correcao, False), resposta, login)
        return resposta
    # O que veio no arquivo e o nome da pessoa, lidos ANTES de aplicar (depois, a pendência some do relatório e a
    # pessoa que não vai ser cadastrada some dos dados)
    veio_no_arquivo = _valor_no_arquivo(conexao, processamento_id, correcao)
    nome = _titulo_da_pessoa(conexao, processamento_id, correcao.linha)
    # Confirmar: aplica, valida de novo e registra
    correcoes.decidir(conexao, processamento_id, empresa_id, correcao_id, True, login)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "RETIRADA_CONFIRMADA_PELA_EMPRESA",
                        _detalhe_da_retirada(login, correcao))
    desfazer = {"tipo": DESFAZER_CORRECAO, "id": correcao_id}
    # A fala diz exatamente o que mudou
    if correcao.campo == correcoes.EXCLUIR:
        aplicado = {"resumo": f"Não cadastrar {nome} (linha {correcao.linha})", "desfazer": desfazer}
        mensagem = f"Pronto: tirei {nome} (linha {correcao.linha}) deste envio; esta pessoa não será cadastrada."
        # No envio de devolução, se não sobrou ninguém, a devolução se encerra sozinha e não volta ao banco (ADR-121);
        # o envio encerrado não se desfaz mais (a resposta segue para a conversa guardada, como as outras)
        if devolucao_por_pessoa.encerrar_se_ficou_vazio(conexao, processamento_id, empresa_id, login):
            aplicado["desfazer"] = None
            mensagem = mensagem + " Como não sobrou ninguém neste envio de devolução, ele foi encerrado."
    else:
        rotulo = _informacao(conexao, correcao.campo)
        antes = _para_a_tela(correcao.campo, veio_no_arquivo)
        aplicado = {"resumo": f"{rotulo}: {antes} → (vazio)", "desfazer": desfazer}
        quem = _a_informacao_de_quem(conexao, processamento_id, correcao.campo, correcao.linha)
        mensagem = f"Pronto: deixei {quem} em branco."
        if veio_no_arquivo:
            mensagem = f'Pronto: deixei {quem} em branco (no arquivo veio "{antes}").'
    resposta = {"mensagem": mensagem, "aplicado": aplicado,
                "resolvida": not _sobrou_pendencia_na_celula(conexao, processamento_id, correcao)}
    # A escolha e a resposta entram na conversa guardada (reabre em "Resolvidas")
    conversas_das_pendencias.registrar_a_confirmacao(conexao, processamento_id, correcao_id,
                                                     _texto_da_escolha(correcao, True), resposta, login)
    return resposta


def _valor_no_arquivo(conexao, processamento_id: str, correcao) -> str | None:
    """O valor da célula antes da retirada: o que está nos dados ou, se o arquivo trouxe algo que não deu para
    entender, o valor lido da pendência daquela célula. None se não havia nada."""
    if correcao.antes is not None or correcao.campo == correcoes.EXCLUIR:
        return correcao.antes
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return None
    for achado in relatorio.achados:
        if achado.linha == correcao.linha and achado.campo == correcao.campo and achado.valor:
            return achado.valor
    return None


def _texto_da_escolha(correcao, confirmar: bool) -> str:
    """O texto do botão que a pessoa clicou na confirmação (o mesmo de _pedir_confirmacao)."""
    if not confirmar:
        return "Cancelar"
    if correcao.campo == correcoes.EXCLUIR:
        return "Sim, não cadastrar"
    return "Sim, deixar em branco"

def _aplicar_confirmacao(conexao, empresa_id, login, processamento_id, pendencia, justificativa) -> tuple:
    """Registra que o alerta está certo, com as palavras da empresa. Devolve (a fala, o aplicado)."""
    acompanhamento.confirmar_pendencia(conexao, empresa_id, login, processamento_id, pendencia["regra_id"],
                                       pendencia["linha"], justificativa[:TAMANHO_MAXIMO_DO_MOTIVO])
    # "Sim, é do nosso grupo" põe o CNPJ no cadastro da empresa (vale para todos): isso não se desfaz daqui
    desfazer = None
    if pendencia["regra_id"] != validador.REGRA_CNPJ_DO_GRUPO:
        linha_em_texto = "" if pendencia["linha"] is None else str(pendencia["linha"])
        desfazer = {"tipo": DESFAZER_CONFIRMACAO, "id": pendencia["regra_id"] + "|" + linha_em_texto}
    # A fala diz exatamente o que foi confirmado: de quem, o campo e o valor
    quem = _a_informacao_de_quem(conexao, processamento_id, pendencia["campo"], pendencia["linha"])
    valor = _para_a_tela(pendencia["campo"], pendencia["valor"])
    if pendencia["campo"] and valor != "(vazio)":
        fala = (f'Pronto: registrei que {quem}, "{valor}", está certa, com as suas palavras. '
                "O banco vê essa confirmação.")
    else:
        fala = "Pronto: registrei que está certo, com as suas palavras. O banco vê essa confirmação."
    informacao = _informacao(conexao, pendencia["campo"])
    aplicado = {"resumo": f"{informacao}: confirmado que está certo", "desfazer": desfazer}
    return fala, aplicado


def _aplicar_para_todos(conexao, empresa_id, login, processamento_id, pendencia, valor, mensagem_da_empresa) -> tuple:
    """Usa o mesmo valor em todos do envio que estão sem este dado. Devolve (a fala, o aplicado)."""
    campo = pendencia["campo"]
    identificadores = correcoes.preencher_para_todos(conexao, processamento_id, empresa_id, campo, valor,
                                                     _motivo(mensagem_da_empresa), login)
    quantos = _plural_de_funcionarios(len(identificadores))
    fala = f"Pronto: usei \"{valor}\" em {quantos} que estavam sem a informação \"{_informacao(conexao, campo)}\"."
    aplicado = {"resumo": f"{_informacao(conexao, campo)} = {valor} em {quantos}",
                "desfazer": {"tipo": DESFAZER_PARA_TODOS, "id": identificadores[0]}}
    return fala, aplicado


# ---------------- Pendências em grupo (ADR-120) ----------------

def _plural_de_pessoas(quantidade: int) -> str:
    """ "1 pessoa" ou "N pessoas"."""
    if quantidade == 1:
        return "1 pessoa"
    return f"{quantidade} pessoas"


def _achados_do_grupo(conexao, processamento_id: str, regra_id: str, linha: int | None,
                      campo: str | None = None) -> list:
    """Os achados das pessoas do grupo da pendência (ela incluída), refeitos a partir do relatório do Validador.

    Devolve: a lista, ou [] se a pendência não está mais num grupo (ex.: as outras já foram resolvidas).
    O navegador nunca manda a lista de pessoas: só diz qual pendência representa o grupo.
    """
    achado = _achado_em_aberto(conexao, processamento_id, regra_id, linha, campo)
    relatorio = validador.obter(conexao, processamento_id)
    if achado is None or relatorio is None:
        return []
    return pendencias_em_grupo.grupo_do_achado(relatorio.achados, achado)


# Quantos nomes a fala do grupo cita, no máximo (os outros viram "e mais N")
NOMES_NA_FALA_DO_GRUPO = 5


def _nomes_para_a_fala(conexao, processamento_id: str, linhas: list[int]) -> str:
    """Os primeiros nomes das pessoas do grupo, para a fala. Ex.: [2, 3, 4] → "Ana, Bia e Caio"; com 23 pessoas →
    "Ana, Bia, Caio, Davi, Eva e mais 18"."""
    # O nome de cada linha, numa passada só pelos dados do envio
    nome_da_linha = {}
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        nome_da_linha[registro["_linha"]] = registro.get("nome_completo")
    nomes = []
    for linha in linhas:
        nome = pergunta_da_pendencia.primeiro_nome(nome_da_linha.get(linha))
        nomes.append(nome or f"linha {linha}")
    if len(nomes) > NOMES_NA_FALA_DO_GRUPO:
        return ", ".join(nomes[:NOMES_NA_FALA_DO_GRUPO]) + f" e mais {len(nomes) - NOMES_NA_FALA_DO_GRUPO}"
    if len(nomes) == 1:
        return nomes[0]
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _aplicar_no_grupo(conexao, empresa_id, login, processamento_id, pendencia, linhas, valor,
                      mensagem_da_empresa) -> tuple:
    """Usa o valor em todas as pessoas do grupo, de uma vez. Devolve (a fala, o aplicado, com o Desfazer do lote).

    Ex.: 23 pessoas com "Divorciado(a)" e a resposta 'Sim, use "Divorciado" para as 23' → "Pronto: Estado civil =
    Divorciado em 23 pessoas."
    """
    campo = pendencia["campo"]
    identificadores = correcoes.trocar_em_varias_linhas(conexao, processamento_id, empresa_id, linhas, campo, valor,
                                                        _motivo(mensagem_da_empresa), login)
    # O valor como ficou (padronizado) e o que tinha vindo no arquivo
    primeira = correcoes.correcao_pelo_id(conexao, processamento_id, identificadores[0])
    depois = _para_a_tela(campo, primeira.depois)
    veio = _para_a_tela(campo, pendencia["valor"])
    quantas = _plural_de_pessoas(len(identificadores))
    informacao = _informacao(conexao, campo)
    # A fala diz exatamente o que mudou e em quem
    fala = (f'Pronto: troquei a informação "{informacao}" de "{veio}" para "{depois}" em {quantas}: '
            f"{_nomes_para_a_fala(conexao, processamento_id, linhas)}.")
    aplicado = {"resumo": f"{informacao}: {veio} → {depois} em {quantas}",
                "desfazer": {"tipo": DESFAZER_GRUPO, "id": identificadores[0]}}
    return fala, aplicado


# ---------------- Informar pessoa a pessoa (ADR-124, alternativa B) ----------------

# A regra da coluna que o arquivo inteiro não trouxe: a única pendência que abre a lista pessoa a pessoa
REGRA_SEM_COLUNA = acompanhamento.REGRA_OBRIGATORIO_SEM_COLUNA
# O motivo guardado em cada correção da lista (salvar a lista é a decisão da empresa)
MOTIVO_PESSOA_A_PESSOA = "Informado pessoa a pessoa pela empresa, na lista do cartão"


def pessoas_para_informar(conexao, empresa_id: str, processamento_id: str, campo: str) -> dict:
    """A lista "Informar pessoa a pessoa" de um cartão: as pessoas do envio, para a empresa dizer o valor de cada uma.

    Para que serve: quando a informação que o arquivo inteiro não trouxe não é a mesma para todos (ex.: duas
    unidades) ou é de cada pessoa (ex.: o CPF), a empresa informa o valor de cada funcionário sem mandar o arquivo de
    novo.
    Recebe: o envio e o campo da pendência "coluna que o arquivo inteiro não trouxe".
    Devolve: {campo, informacao, igual_para_todos, pessoas: [{linha, nome, matricula}]}, na ordem do arquivo. A chave
    de cada pessoa é a LINHA do arquivo, não o CPF (que pode estar faltando ou errado); o nome e a matrícula servem
    para a empresa reconhecer quem é. Levanta KeyError (outra empresa) ou ValueError (etapa errada, sem campo ou
    pendência que não está mais em aberto).
    """
    _conferir_envio_e_etapa(conexao, empresa_id, processamento_id)
    if not campo:
        raise ValueError("Diga de qual informação é a lista.")
    pendencia = pendencia_do_validador(conexao, processamento_id, REGRA_SEM_COLUNA, None, campo)
    # Cada pessoa do envio (sem as que saíram), com o que ajuda a reconhecê-la
    pessoas = []
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        pessoas.append({"linha": registro["_linha"], "nome": registro.get("nome_completo") or "",
                        "matricula": registro.get("matricula") or ""})
    return {"campo": campo, "informacao": _informacao(conexao, campo),
            "igual_para_todos": pendencia["igual_para_todos"], "pessoas": pessoas}


def _valores_preenchidos(valores: list[dict]) -> dict[int, str]:
    """Os valores que a tela mandou, só os preenchidos: {linha: valor}. Quem ficou em branco fica de fora.

    Recebe: [{linha, valor}]. Levanta ValueError se uma linha vier duas vezes (a tela manda uma por pessoa).
    Ex.: [{"linha": 2, "valor": "001"}, {"linha": 3, "valor": ""}] → {2: "001"}.
    """
    preenchidos = {}
    linhas_vistas = set()
    for item in valores:
        linha = item["linha"]
        if linha in linhas_vistas:
            raise ValueError(f"A linha {linha} veio duas vezes na lista.")
        linhas_vistas.add(linha)
        valor = (item.get("valor") or "").strip()
        if valor:
            preenchidos[linha] = valor
    return preenchidos


def _fala_de_quem_ficou_sem(quantidade: int) -> str:
    """O pedaço da fala sobre quem ficou sem valor na lista ("" se ninguém). Ex.: 2 → " 2 pessoas ficaram sem esta
    informação; cada uma ganhou um cartão de revisão." """
    if quantidade == 0:
        return ""
    if quantidade == 1:
        return " 1 pessoa ficou sem esta informação e ganhou um cartão de revisão."
    return f" {quantidade} pessoas ficaram sem esta informação; cada uma ganhou um cartão de revisão."


def _resumo_pessoa_a_pessoa(informacao: str, quantidade: int) -> str:
    """O resumo do que mudou (no balão e em "Resolvidas"). Ex.: ("Código da unidade", 4) → "Código da unidade de 4
    pessoas, uma a uma"; com 1 pessoa, sem o "uma a uma"."""
    if quantidade == 1:
        return f"{informacao} de 1 pessoa"
    return f"{informacao} de {quantidade} pessoas, uma a uma"


def informar_por_pessoa(conexao, empresa_id: str, login: str, processamento_id: str, campo: str,
                        valores: list[dict]) -> dict:
    """Salva a lista "Informar pessoa a pessoa": o valor de cada pessoa, num lote com um Desfazer só.

    Recebe: o envio, o campo da pendência "coluna que o arquivo inteiro não trouxe" e [{linha, valor}] (vazio = a
    pessoa fica sem o dado e ganha um cartão de revisão depois).
    Devolve: o mesmo formato de uma rodada da conversa (ver conversar): a tela mostra o "Pronto: ..." no chat do
    cartão, com o Desfazer, e a conversa fica guardada (vai para "Resolvidas"). O balão da pessoa diz "Informei pessoa
    a pessoa (N pessoas)."
    Levanta KeyError (outra empresa) ou ValueError (etapa errada, pendência resolvida, nenhum valor ou valor que não
    serve; a mensagem diz cada linha).
    """
    _conferir_envio_e_etapa(conexao, empresa_id, processamento_id)
    pendencia_do_validador(conexao, processamento_id, REGRA_SEM_COLUNA, None, campo)
    preenchidos = _valores_preenchidos(valores)
    # A chave da conversa do cartão e a abertura (a pergunta que a pessoa viu), montadas ANTES de mudar o dado
    chave, abertura = _chave_e_abertura(conexao, processamento_id, REGRA_SEM_COLUNA, None, campo, [])
    total_de_pessoas = len(correcoes.dados_atuais(conexao, processamento_id).registros)
    identificadores = correcoes.informar_por_pessoa(conexao, processamento_id, empresa_id, campo, preenchidos,
                                                    MOTIVO_PESSOA_A_PESSOA, login)
    quantas = _plural_de_pessoas(len(identificadores))
    informacao = _informacao(conexao, campo)
    # A fala diz exatamente o que mudou e em quem, e quem ficou sem
    nomes = _nomes_para_a_fala(conexao, processamento_id, sorted(preenchidos))
    fala = (f'Pronto: informei "{informacao}" de {quantas}: {nomes}.'
            f"{_fala_de_quem_ficou_sem(total_de_pessoas - len(identificadores))}")
    aplicado = {"resumo": _resumo_pessoa_a_pessoa(informacao, len(identificadores)),
                "desfazer": {"tipo": DESFAZER_POR_PESSOA, "id": identificadores[0]}}
    # A pendência do arquivo inteiro saiu da lista? (o campo passa a contar como presente)
    resolvida = _achado_em_aberto(conexao, processamento_id, REGRA_SEM_COLUNA, None, campo) is None
    rodada = {"mensagem": fala, "acao": "informar_por_pessoa", "fontes": [], "aplicado": aplicado,
              "confirmacao": None, "remapeado": False, "recusado": False, "resolvida": resolvida, "encerrada": False}
    return _guardar_a_rodada(conexao, processamento_id, chave, abertura, f"Informei pessoa a pessoa ({quantas}).",
                             rodada, login)


# ---------------- A informação que faltou está em outra coluna (ADR-124) -------------------

def _id_da_confirmacao_da_coluna(coluna: str, campo: str) -> str:
    """O identificador da pergunta "Confirma que a coluna X é o CPF?" na conversa guardada.

    Ex.: ("Registro", "cpf") → "coluna|cpf|Registro".
    """
    return f"coluna|{campo}|{coluna}"


def _nome_curto(campo: str | None) -> str:
    """O nome curto de um campo, como a empresa fala dele. Ex.: "matricula" → "Matrícula"; None → "fora do cadastro"."""
    if not campo:
        return "fora do cadastro"
    return acompanhamento.rotulo_do_campo(campo)


def _o_que_foi_conferido(conferencia: dict, informacao: str) -> str:
    """A primeira frase da conferência. Ex.: 'Conferi a coluna "Registro" (hoje lida como "Matrícula") com as regras
    de "CPF", com o dígito verificador: 35 de 35 valores passaram.'"""
    hoje = ""
    if conferencia["campo_de_hoje"]:
        hoje = f' (hoje lida como "{_nome_curto(conferencia["campo_de_hoje"])}")'
    digito = ", com o dígito verificador" if conferencia["com_digito"] else ""
    return (f'Conferi a coluna "{conferencia["coluna"]}"{hoje} com as regras de "{informacao}"{digito}: '
            f'{conferencia["validos"]} de {conferencia["preenchidos"]} valores passaram.')


def _exemplo_que_nao_passou(conferencia: dict) -> str:
    """O primeiro valor que não passou, com o motivo, para a fala. Ex.: ' (ex.: "00123": não tem 11 dígitos)'."""
    if not conferencia["exemplos"]:
        return ""
    exemplo = conferencia["exemplos"][0]
    return f' (ex.: "{exemplo["valor"]}": {exemplo["motivo"]})'


def _quem_ganha_cartao(quantidade: int) -> str:
    """O pedaço da fala sobre os valores que não passaram.

    Ex.: 5 → "5 não passaram e viram um cartão de revisão para cada pessoa".
    """
    if quantidade == 1:
        return "1 não passou e vira um cartão de revisão da pessoa"
    return f"{quantidade} não passaram e viram um cartão de revisão para cada pessoa"


def _propor_a_coluna(conexao, processamento_id: str, pendencia: dict, coluna: str) -> tuple:
    """Confere a coluna indicada pela empresa e, se a maioria dos valores passa, pergunta se pode usar (nada muda).

    Recebe: o envio; a pendência (a coluna que o arquivo inteiro não trouxe); a coluna indicada.
    Devolve: (a fala, a confirmação {correcao_id, tipo "coluna", coluna, campo, sim, nao}) ou (a fala, None) quando a
    coluna não serve (a maioria dos valores não passa, ou ela está vazia). Levanta ValueError se a coluna não existe.
    """
    campo = pendencia["campo"]
    informacao = _informacao(conexao, campo)
    conferencia = coluna_do_campo_que_falta.conferir(conexao, processamento_id, coluna, campo)
    # A coluna não serve: nada muda, e a conversa lembra os outros caminhos
    if not conferencia["maioria"]:
        if conferencia["preenchidos"] == 0:
            fala = f'A coluna "{coluna}" está vazia no arquivo: ela não pode ser a informação "{informacao}".'
        else:
            fala = (f'{_o_que_foi_conferido(conferencia, informacao)[:-1]}{_exemplo_que_nao_passou(conferencia)}. '
                    f'Ela não parece ser a informação "{informacao}", então nada mudou.')
        return fala + " " + assistente_correcao.FALA_DOS_DOIS_CAMINHOS, None
    # A maioria passou: o que muda, e a pergunta
    partes = [_o_que_foi_conferido(conferencia, informacao)]
    nao_passaram = conferencia["preenchidos"] - conferencia["validos"]
    if nao_passaram:
        partes.append(f"Se você confirmar, {_quem_ganha_cartao(nao_passaram)}{_exemplo_que_nao_passou(conferencia)}.")
    if conferencia["campo_de_hoje"]:
        nome_de_hoje = _nome_curto(conferencia["campo_de_hoje"])
        # Um campo obrigatório sem coluna vira pendência: a pessoa fica sabendo antes de confirmar
        e_ganha_cartao = ""
        if _campo_e_obrigatorio(conexao, conferencia["campo_de_hoje"]):
            e_ganha_cartao = " e ganha um cartão de revisão"
        partes.append(f'Com a troca, "{nome_de_hoje}" fica sem coluna{e_ganha_cartao}.')
    partes.append(f'Confirma que a coluna "{coluna}" é a informação "{informacao}"?')
    confirmacao = {"correcao_id": _id_da_confirmacao_da_coluna(coluna, campo), "tipo": "coluna", "coluna": coluna,
                   "campo": campo, "sim": f"Sim, usar como {informacao}", "nao": "Cancelar"}
    return " ".join(partes), confirmacao


def _fala_da_coluna_trocada(conexao, conferencia: dict, informacao: str, campo_de_antes: str | None) -> str:
    """O "Pronto: ..." da troca. Ex.: 'Pronto: a coluna "Registro" agora é a informação "CPF" (35 de 35 valores
    passaram). "Matrícula" ficou sem coluna e ganhou um cartão de revisão.'"""
    fala = (f'Pronto: a coluna "{conferencia["coluna"]}" agora é a informação "{informacao}" '
            f'({conferencia["validos"]} de {conferencia["preenchidos"]} valores passaram).')
    if campo_de_antes:
        e_ganhou_cartao = " e ganhou um cartão de revisão" if _campo_e_obrigatorio(conexao, campo_de_antes) else ""
        fala += f' "{_nome_curto(campo_de_antes)}" ficou sem coluna{e_ganhou_cartao}.'
    nao_passaram = conferencia["preenchidos"] - conferencia["validos"]
    if nao_passaram == 1:
        fala += " O valor que não passou virou um cartão de revisão da pessoa."
    elif nao_passaram > 1:
        fala += f" Os {nao_passaram} valores que não passaram viraram um cartão de revisão para cada pessoa."
    return fala


def confirmar_coluna(conexao, empresa_id: str, login: str, processamento_id: str, campo: str, coluna: str,
                     confirmar: bool, cliente=None, busca=None) -> dict:
    """A resposta da empresa à pergunta "Confirma que a coluna X é a informação Y?" (ADR-124).

    Recebe: o envio; o campo da pendência; a coluna; confirmar — True troca, False deixa tudo como estava; cliente e
    busca (os do fluxo). Devolve: {mensagem, aplicado ({resumo, desfazer} ou None), resolvida}.
    Confirmar confere de novo (a pendência continua aberta e a maioria dos valores ainda passa), troca a coluna, refaz
    a leitura e deixa o Desfazer à mão; as duas respostas vão para a trilha e para a conversa guardada.
    Levanta KeyError (outra empresa) ou ValueError (etapa errada, pendência resolvida, coluna que não serve mais).
    """
    _conferir_envio_e_etapa(conexao, empresa_id, processamento_id)
    identificador = _id_da_confirmacao_da_coluna(coluna, campo)
    informacao = _informacao(conexao, campo)
    # Cancelar: nada muda, e a resposta fica registrada
    if not confirmar:
        resposta = {"mensagem": "Tudo bem, nada mudou.", "aplicado": None, "resolvida": False}
        auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "COLUNA_RECUSADA_PELA_EMPRESA",
                            {"login": login, "coluna": coluna, "campo": campo})
        conversas_das_pendencias.registrar_a_confirmacao(conexao, processamento_id, identificador, "Cancelar",
                                                         resposta, login)
        return resposta
    # Confere tudo de novo: o arquivo e o mapeamento podem ter mudado desde a pergunta
    pendencia_do_validador(conexao, processamento_id, REGRA_SEM_COLUNA, None, campo)
    conferencia = coluna_do_campo_que_falta.conferir(conexao, processamento_id, coluna, campo)
    if not conferencia["maioria"]:
        raise ValueError(f'A maioria dos valores da coluna "{coluna}" não passa nas regras de "{informacao}".')
    campo_de_antes = coluna_do_campo_que_falta.usar_coluna(conexao, empresa_id, login, processamento_id, coluna, campo,
                                                           cliente=cliente, busca=busca)
    aplicado = {"resumo": f'Coluna "{coluna}": {_nome_curto(campo_de_antes)} → {informacao}',
                "desfazer": {"tipo": DESFAZER_COLUNA, "id": f"{coluna}|{campo_de_antes or ''}"}}
    resposta = {"mensagem": _fala_da_coluna_trocada(conexao, conferencia, informacao, campo_de_antes),
                "aplicado": aplicado,
                "resolvida": _achado_em_aberto(conexao, processamento_id, REGRA_SEM_COLUNA, None, campo) is None}
    # A escolha e a resposta entram na conversa guardada (reabre em "Resolvidas")
    conversas_das_pendencias.registrar_a_confirmacao(conexao, processamento_id, identificador,
                                                     f"Sim, usar como {informacao}", resposta, login)
    return resposta


def _fala_do_grupo_so_com_valor(quantidade: int) -> str:
    """A fala quando, no cartão do grupo, a pessoa pede algo que não é um valor para todas (ex.: não cadastrar alguém).

    Nada muda: tirar alguém ou deixar em branco é decisão pessoa a pessoa, pelo "Responder uma a uma".
    """
    return (f"Aqui a resposta vale para as {quantidade} pessoas. Para não cadastrar alguém, deixar a informação em "
            'branco ou responder cada caso, use "Responder uma a uma". Qual opção uso para todas?')


def _conversar_no_grupo(conexao, empresa_id, login, processamento_id, pendencia, linhas, resposta, texto) -> tuple:
    """Aplica a decisão do agente no cartão do grupo. Devolve (a fala, o aplicado ou None).

    Só a troca de valor ("corrigir" com um valor) vale para o grupo; as outras ações que mudam dado não mudam nada
    e a fala explica o caminho.
    """
    # Um valor: vale para todas as pessoas do grupo, se ele conferir (ADR-127: nada de "Pronto" com valor errado)
    if resposta.acao == "corrigir" and (resposta.valor or "").strip():
        recusa = _recusa_do_valor(conexao, processamento_id, pendencia, resposta, em_grupo=True)
        if recusa:
            return recusa, None
        # As pendências do grupo (uma por pessoa), para a conferência depois da troca (ADR-153)
        chaves_do_grupo = set()
        for linha_do_grupo in linhas:
            chaves_do_grupo.add((pendencia["regra_id"], linha_do_grupo, pendencia["campo"]))
        try:
            # O relatório de antes da troca: a conferência compara com o de depois
            antes = _achados_para_conferir(conexao, processamento_id)
            fala, aplicado = _aplicar_no_grupo(conexao, empresa_id, login, processamento_id, pendencia, linhas,
                                               resposta.valor, texto)
            # O valor passa por todas as regras do Validador; se não passar, a troca volta na hora (ADR-153)
            return _conferir_o_que_mudou(conexao, empresa_id, login, processamento_id, pendencia, chaves_do_grupo,
                                         antes, fala, aplicado, set(linhas), em_grupo=True)
        except (ValueError, KeyError) as erro:
            return _fala_de_valor_recusado(erro), None
    # Tirar alguém, deixar em branco, confirmar...: pessoa a pessoa
    if resposta.acao in assistente_correcao.ACOES_QUE_MUDAM_DADO:
        return _fala_do_grupo_so_com_valor(len(linhas)), None
    # Responder, explicar, fora do assunto: a fala do agente, sem mudança
    return resposta.mensagem, None


def _aplicar_formato(conexao, empresa_id, processamento_id, pendencia, decisao, cliente, busca) -> tuple:
    """Decide o formato da coluna inteira (datas ou dígitos da matrícula). Devolve (a fala, o aplicado)."""
    coluna = acompanhamento.coluna_da_duvida_de_formato(conexao, processamento_id, pendencia["regra_id"],
                                                        pendencia["mensagem"])
    if coluna is None:
        raise ValueError("Não achei a coluna desta dúvida de formato. Atualize a página.")
    # O mesmo serviço do botão de formato: o fluxo padroniza a coluna de novo
    cadastro.decidir_formato(conexao, empresa_id, processamento_id, coluna, decisao, cliente=cliente, busca=busca)
    escolha = FORMATO_PARA_A_EMPRESA.get(decisao)
    if escolha is None:
        escolha = "matrícula com " + decisao.split(":")[1] + " dígitos"
    fala = f"Pronto: a coluna {coluna} ficou com {escolha}, e o arquivo foi padronizado de novo."
    # Sem "Desfazer": o formato decide a padronização da coluna inteira
    return fala, {"resumo": f"Coluna {coluna}: {escolha}", "desfazer": None}


def _aplicar(conexao, empresa_id, login, processamento_id, pendencia, resposta, mensagem_da_empresa, cliente,
             busca) -> tuple:
    """Aplica a ação que o agente escolheu. Devolve (a fala, o aplicado). Levanta ValueError se a regra recusar."""
    if resposta.acao == "corrigir":
        return _aplicar_correcao(conexao, empresa_id, login, processamento_id, pendencia, resposta.valor,
                                 mensagem_da_empresa)

    if resposta.acao == "confirmar_alerta":
        return _aplicar_confirmacao(conexao, empresa_id, login, processamento_id, pendencia,
                                    resposta.justificativa or mensagem_da_empresa)
    if resposta.acao == "preencher_para_todos":
        return _aplicar_para_todos(conexao, empresa_id, login, processamento_id, pendencia, resposta.valor,
                                   mensagem_da_empresa)
    # escolher_formato (a única que sobra na lista das que mudam dado)
    return _aplicar_formato(conexao, empresa_id, processamento_id, pendencia, resposta.valor, cliente, busca)


def _fala_fora_do_assunto(conexao, processamento_id: str, pendencia: dict) -> str:
    """A recusa de uma mensagem sobre outra informação, dizendo o que esta conversa ajusta.

    Ex.: 'Aqui eu só ajusto a informação "CPF" de Ana. Para outra informação, use a pendência correspondente na lista.'
    """
    quem = _a_informacao_de_quem(conexao, processamento_id, pendencia["campo"], pendencia["linha"])
    return f"Aqui eu só ajusto {quem}. Para outra informação, use a pendência correspondente na lista."


def _fala_de_valor_recusado(erro: Exception) -> str:
    """A fala quando o valor não pôde ser usado (a regra recusou), no tom do agente.

    Ex.: ValueError("valor não numérico") → "Não consegui usar esse valor (valor não numérico). Pode informar de outro
    jeito?"
    """
    explicacao = str(erro).strip().strip("'\"").rstrip(".")
    return f"Não consegui usar esse valor ({explicacao}). Pode informar de outro jeito?"


# ---------------- Conferir antes do "Pronto" (ADR-127) ----------------

# O que a conversa acrescenta quando o agente devolveu o envio à leitura das colunas (ADR-127)
FALA_DO_ENVIO_DE_VOLTA_AS_COLUNAS = ("O envio voltou para a leitura das colunas: as pendências voltam depois que você "
                                     'conferir as colunas, pelo botão "Continuar a conferência das colunas".')
# As ações que levam um valor novo (as que a conferência olha antes de aplicar)
ACOES_COM_VALOR_NOVO = ("corrigir", "preencher_para_todos")
# Os documentos com dígito verificador, pelo nome curto na fala ("Esse CPF não confere")
DOCUMENTOS_COM_DIGITO = {TipoCampo.CPF: "CPF", TipoCampo.CNPJ: "CNPJ"}


def _documento_do_campo(conexao, campo: str | None) -> str | None:
    """O nome curto do documento com dígito verificador (ex.: "CPF"), ou None nos outros campos."""
    if not campo:
        return None
    campo_do_layout = conferencia_do_valor.campo_do_layout_pelo_nome(conexao, campo)
    if campo_do_layout is None:
        return None
    return DOCUMENTOS_COM_DIGITO.get(campo_do_layout.tipo)


def _fala_do_valor_que_nao_confere(conexao, processamento_id: str, pendencia: dict, valor: str, motivo: str,
                                   em_grupo: bool) -> str:
    """A fala quando o valor que a empresa escreveu não confere na padronização (antes de qualquer troca): o que está
    errado, o jeito certo pelo parâmetro, que nada mudou, o que a informação tem hoje e a pergunta, com um exemplo.

    Ex.: CPF "123.456.789-00" → 'Esse CPF não confere: o dígito verificador está errado. O certo: 11 dígitos com
    dígito verificador válido. Nada mudou. A informação "CPF" de Ana continua "529.982.247-20". Qual é o CPF certo
    (ex.: "123.456.789-09")?'; data "31/02/2026" → 'O valor "31/02/2026" não serve para a informação "Data de
    admissão" (data inexistente). O certo: data válida, não futura. Nada mudou. ...'
    """
    campo = pendencia["campo"]
    documento = _documento_do_campo(conexao, campo)
    # O que está errado: no documento, a frase curta de sempre; nos outros, o valor e a informação
    if documento:
        explicacao = f"Esse {documento} não confere: {motivo}."
    else:
        explicacao = f'O valor "{valor}" não serve para a informação "{_informacao(conexao, campo)}" ({motivo}).'
    return _recusa_completa(conexao, processamento_id, pendencia, explicacao, _jeito_certo(conexao, campo), em_grupo)


def _recusa_do_valor(conexao, processamento_id: str, pendencia: dict, resposta, em_grupo: bool = False) -> str | None:
    """A fala de recusa quando o valor novo não confere com a padronização do campo; None quando confere (ou não há
    valor).

    Recebe: o envio; a pendência; a resposta do agente (a ação e o valor); em_grupo — True no cartão do grupo (a fala
    não fala de uma pessoa só). Só olha as ações com um valor novo: deixar em branco tem a sua própria confirmação, e o
    formato da coluna não é um valor. As outras regras (a CBO oficial, a pessoa repetida...) são conferidas depois da
    troca, pelo Validador (_conferir_o_que_mudou).
    """
    if resposta.acao not in ACOES_COM_VALOR_NOVO or not (resposta.valor or "").strip():
        return None
    motivo = conferencia_do_valor.motivo_para_recusar(conexao, pendencia["campo"], resposta.valor)
    if motivo is None:
        return None
    return _fala_do_valor_que_nao_confere(conexao, processamento_id, pendencia, resposta.valor.strip(), motivo,
                                          em_grupo)


# ---------------- Conferir na hora, com todas as regras do Validador (ADR-153) ----------------
#
# Por que depois da troca: as regras do campo não moram num lugar só. A padronização e o dígito do CPF são conferidos
# antes (acima); a CBO oficial, a pessoa repetida no arquivo, a pessoa em outro envio e as outras moram no Validador,
# que olha o envio inteiro. Em vez de copiar essas regras, a conversa usa o próprio Validador: grava a troca, compara
# o relatório de antes com o de depois e, se o valor trouxe um achado que diz que ele está errado, volta a troca na
# hora (o mesmo Desfazer da tela). A pendência continua aberta, e nenhum cartão novo nasce desse valor.

# O começo da frase que avisa o que o valor novo trouxe (ex.: o salário fora da faixa da profissão nova)
COMECO_DO_AVISO = "Atenção:"
# Os jeitos de uma fala dizer que a informação veio vazia no arquivo (a fala que já diz isso não ganha outra frase)
JEITOS_DE_DIZER_QUE_VEIO_VAZIO = ("vazi", "em branco", "não veio", "nao veio", "não trouxe", "nao trouxe")


def _chave_do_achado(achado) -> tuple:
    """O que identifica um achado no relatório: (a regra, a linha, o campo). Ex.: ("CPF_INVALIDO", 8, "cpf")."""
    return (achado.regra_id, achado.linha, achado.campo)


def _chave_da_pendencia(pendencia: dict) -> tuple:
    """A mesma identificação para a pendência da conversa. Ex.: ("OBRIGATORIO_VAZIO", 5, "codigo_cbo")."""
    return (pendencia["regra_id"], pendencia["linha"], pendencia["campo"])


def _achados_para_conferir(conexao, processamento_id: str) -> dict:
    """Os achados do relatório de agora que a conferência compara: os que pedem algo à empresa e os avisos de quem fica
    de fora do envio. Devolve {chave do achado: achado}.

    Ex.: {("CPF_INVALIDO", 8, "cpf"): Achado(...), ("JA_HOMOLOGADO_NA_EMPRESA", 4, "cpf"): Achado(...)}.
    """
    achados = {}
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return achados
    for achado in relatorio.achados:
        # O aviso de quem fica de fora não pede nada à empresa, mas tira a pessoa do envio: a fala avisa
        fica_de_fora = achado.regra_id in validador.REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA
        if pendencias_em_grupo.achado_em_aberto(achado) or fica_de_fora:
            achados[_chave_do_achado(achado)] = achado
    return achados


def _diz_que_o_valor_esta_errado(achado) -> bool:
    """True se o achado diz que um valor está errado em si, e não só faz uma pergunta: um BLOQUEANTE ou uma das regras
    de valor inválido do Validador (ex.: o código que não é uma profissão da CBO oficial).

    O alerta que só pergunta (ex.: o salário fora da faixa) e o aviso de quem fica de fora do envio dão False.
    """
    return achado.severidade == validador.BLOQUEANTE or achado.regra_id in validador.REGRAS_DE_VALOR_INVALIDO


def _conferir_o_que_mudou(conexao, empresa_id: str, login: str, processamento_id: str, pendencia: dict,
                          chaves_da_pendencia: set, antes: dict, fala: str, aplicado: dict,
                          linhas_da_troca: set | None, em_grupo: bool) -> tuple[str, dict | None]:
    """Depois de usar um valor novo: confere, no relatório refeito pelo Validador de verdade, o que o valor trouxe.

    Recebe: a pendência e as chaves dela (a da pessoa, ou as das pessoas do grupo); antes — os achados de antes da
    troca (_achados_para_conferir); a fala e o aplicado da troca (o aplicado de uma troca de valor sempre traz o
    Desfazer); linhas_da_troca — as linhas que mudaram (None: várias, no "preencher para todos"); em_grupo — True no
    cartão do grupo.
    Devolve (a fala, o aplicado):
      - o valor não passou numa regra (o achado nasceu agora, ou é a própria pendência que continua aberta, e diz que o
        valor está errado): a troca volta na hora, e a fala explica o que está errado → (a recusa, None);
      - o valor passou, mas trouxe um alerta que só pergunta (ex.: o salário ficou fora da faixa da profissão nova) ou
        tirou a pessoa do envio: a troca fica, e a fala avisa → (a fala com o aviso, o aplicado).
    Ex.: o código CBO "C900" no lugar do vazio → a troca volta, e a fala diz que "C900" não é uma profissão da CBO.
    """
    depois = _achados_para_conferir(conexao, processamento_id)
    errados = []
    novos_avisos = []
    for chave, achado in depois.items():
        nasceu_agora = chave not in antes
        # A própria pendência ainda aberta: o valor novo também não passou na regra dela
        pendencia_continua = chave in chaves_da_pendencia
        if not nasceu_agora and not pendencia_continua:
            continue
        if _diz_que_o_valor_esta_errado(achado):
            errados.append(achado)
        elif nasceu_agora:
            novos_avisos.append(achado)
    # O valor não passou: a troca volta, e a pendência continua como estava
    if errados:
        _voltar_o_valor_recusado(conexao, empresa_id, login, processamento_id, pendencia, aplicado, errados)
        recusa = _fala_do_valor_que_nao_passou(conexao, processamento_id, pendencia, errados[0], linhas_da_troca,
                                               em_grupo)
        return recusa, None
    # O valor passou: a fala avisa o que ele trouxe (o alerta vira um cartão para conferir)
    for achado in novos_avisos:
        fala = fala + " " + _aviso_do_que_o_valor_trouxe(conexao, achado)
    return fala, aplicado


def _voltar_o_valor_recusado(conexao, empresa_id: str, login: str, processamento_id: str, pendencia: dict,
                             aplicado: dict, errados: list) -> None:
    """Volta a troca cujo valor não passou numa regra (o mesmo Desfazer da tela, que valida o envio de novo) e registra
    na trilha por quê: quem, a linha, o campo e as regras que recusaram, sem nenhum valor pessoal."""
    desfazer = aplicado["desfazer"]
    _desfazer_a_mudanca(conexao, empresa_id, login, processamento_id, desfazer["tipo"], desfazer["id"])
    # As regras que recusaram, cada uma uma vez
    regras = []
    for achado in errados:
        if achado.regra_id not in regras:
            regras.append(achado.regra_id)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "VALOR_RECUSADO_NA_CONVERSA",
                        {"login": login, "linha": pendencia["linha"], "campo": pendencia["campo"], "regras": regras})


def _explicacao_do_achado(conexao, achado) -> str:
    """A mensagem do Validador sobre um achado, com o nome técnico do campo trocado pelo nome que a empresa lê.

    Ex.: "Valor de valor_renda acima do máximo do parâmetro (R$ 30.000,00)." → 'Valor de "Renda" acima do máximo do
    parâmetro (R$ 30.000,00).'
    """
    return pergunta_da_pendencia.mensagem_sem_nome_tecnico(achado.mensagem, achado.campo,
                                                          _informacao(conexao, achado.campo))


def _minuscula_no_comeco(texto: str) -> str:
    """A primeira letra em minúscula, para a frase continuar depois de ":" (a sigla fica como está).

    Ex.: "Data válida, não futura" → "data válida, não futura"; "O mesmo CPF" → "o mesmo CPF"; "CPF com dígito
    errado" → igual; "" → "".
    """
    if not texto:
        return texto
    primeira_palavra = texto.split(" ")[0]
    # Uma sigla (mais de uma letra, todas maiúsculas) fica como está
    if len(primeira_palavra) > 1 and primeira_palavra.isupper():
        return texto
    return texto[0].lower() + texto[1:]


def _fala_do_valor_que_nao_passou(conexao, processamento_id: str, pendencia: dict, achado,
                                  linhas_da_troca: set | None, em_grupo: bool) -> str:
    """A recusa quando o valor novo não passou numa regra do Validador: a explicação da regra (sem nome técnico), que
    nada mudou, o que a informação tem hoje e a pergunta do valor certo.

    Se o problema ficou em outra pessoa (ex.: o CPF escrito já é de outra linha do arquivo), a fala diz de quem.
    Ex.: 'O código "C900" não é uma profissão da tabela oficial de profissões (CBO). Confira o código (são 6 dígitos,
    como 4110-10). Nada mudou. A informação "Código CBO" de Ana continua vazia. Qual é o valor certo?'
    """
    explicacao = _explicacao_do_achado(conexao, achado)
    # O problema ficou numa linha que não mudou: a fala diz de quem é (o nome e a linha)
    outra_pessoa = achado.linha is not None and linhas_da_troca is not None and achado.linha not in linhas_da_troca
    if outra_pessoa:
        nome = _nome_da_pessoa(conexao, processamento_id, achado.linha)
        explicacao = (f"Com esse valor, {nome} (linha {achado.linha}) ficaria com outro problema: "
                      f"{_minuscula_no_comeco(explicacao)}")
    return _recusa_completa(conexao, processamento_id, pendencia, explicacao, "", em_grupo)


def _jeito_certo(conexao, campo: str | None) -> str:
    """Como o valor deve vir, pela regra que o banco escreveu no parâmetro (só a primeira parte, até o ";": o resto
    costuma ser para quem guarda o dado, ex.: "guardar como texto"). "" sem regra.

    Ex.: "cpf" → "O certo: 11 dígitos com dígito verificador válido."; "data_admissao" → "O certo: data válida, não
    futura."
    """
    if not campo:
        return ""
    campo_do_layout = conferencia_do_valor.campo_do_layout_pelo_nome(conexao, campo)
    if campo_do_layout is None or not campo_do_layout.regra.strip():
        return ""
    # A primeira parte da regra, sem o ponto final
    primeira_parte = campo_do_layout.regra.split(";")[0]
    primeira_parte = primeira_parte.strip().rstrip(".")
    return "O certo: " + _minuscula_no_comeco(primeira_parte) + "."


def _exemplo_do_parametro(conexao, campo: str | None) -> str | None:
    """O exemplo que o banco escreveu no parâmetro, como a empresa lê. Ex.: "cpf" → "123.456.789-09"; sem exemplo,
    None."""
    if not campo:
        return None
    campo_do_layout = conferencia_do_valor.campo_do_layout_pelo_nome(conexao, campo)
    if campo_do_layout is None:
        return None
    return acompanhamento.valor_lido_para_a_tela(campo, campo_do_layout.exemplo.strip())


def _pergunta_do_valor_certo(conexao, campo: str | None, fala_ate_aqui: str) -> str:
    """A pergunta que fecha a recusa, com o exemplo do parâmetro quando ele ainda não apareceu na fala.

    Ex.: "cpf" → 'Qual é o CPF certo (ex.: "123.456.789-09")?'; sem exemplo → "Qual é o valor certo?".
    """
    documento = _documento_do_campo(conexao, campo)
    o_que = "o valor"
    if documento:
        o_que = "o " + documento
    exemplo = _exemplo_do_parametro(conexao, campo)
    if exemplo and exemplo not in fala_ate_aqui:
        return f'Qual é {o_que} certo (ex.: "{exemplo}")?'
    return f"Qual é {o_que} certo?"


def _como_a_informacao_esta(conexao, processamento_id: str, pendencia: dict) -> str:
    """O que a informação da pessoa tem agora, numa frase. Ex.: 'A informação "CPF" de Ana continua
    "529.982.247-20".'; sem valor: 'A informação "Código CBO" de Ana continua vazia.'"""
    quem = _a_informacao_de_quem(conexao, processamento_id, pendencia["campo"], pendencia["linha"])
    # A frase começa com maiúscula
    quem = quem[0].upper() + quem[1:]
    valor = _para_a_tela(pendencia["campo"], pendencia["valor"])
    if valor == "(vazio)":
        return f"{quem} continua vazia."
    return f'{quem} continua "{valor}".'


def _recusa_completa(conexao, processamento_id: str, pendencia: dict, explicacao: str, jeito_certo: str,
                     em_grupo: bool) -> str:
    """Monta a recusa de um valor: a explicação, o jeito certo (quando há), "Nada mudou.", o que a informação tem hoje
    (na pendência de uma pessoa) e a pergunta do valor certo, com o exemplo do parâmetro.

    Recebe: a pendência; a explicação do que está errado; jeito_certo ("" = sem essa frase); em_grupo — True no cartão
    do grupo (a informação é de várias pessoas: sem a frase de uma pessoa só).
    """
    partes = [explicacao]
    if jeito_certo:
        partes.append(jeito_certo)
    partes.append("Nada mudou.")
    # Numa pessoa: o que a informação dela tem agora (o valor que veio no arquivo, ou vazia)
    if pendencia["linha"] is not None and pendencia["campo"] and not em_grupo:
        partes.append(_como_a_informacao_esta(conexao, processamento_id, pendencia))
    fala = " ".join(partes)
    return fala + " " + _pergunta_do_valor_certo(conexao, pendencia["campo"], fala)


def _aviso_do_que_o_valor_trouxe(conexao, achado) -> str:
    """O aviso de um achado que o valor novo trouxe e que não o recusa, para a fala do "Pronto".

    Ex.: o salário fora da faixa da profissão nova → 'Atenção: Salário de R$ 9.000,00 fora da faixa da profissão ...
    Ficou um cartão para você conferir.'; a pessoa que fica de fora do envio → 'Atenção: Funcionário já homologado
    nesta empresa: não entra de novo.' (esse não vira cartão).
    """
    aviso = f"{COMECO_DO_AVISO} {_explicacao_do_achado(conexao, achado)}"
    if achado.regra_id in validador.REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA:
        return aviso
    return aviso + " Ficou um cartão para você conferir."


# ---------------- O dado que veio no arquivo, em toda pergunta (ADR-153) ----------------

def _fala_mostra_o_dado(pendencia: dict, fala: str) -> bool:
    """True se a fala já mostra o que veio no arquivo: o valor (como veio ou como a tela escreve) ou que veio vazio."""
    valor = pendencia["valor"]
    # Sem valor: a fala precisa dizer que veio vazio
    if valor in (None, ""):
        minusculas = fala.lower()
        for jeito in JEITOS_DE_DIZER_QUE_VEIO_VAZIO:
            if jeito in minusculas:
                return True
        return False
    # Com valor: ele aparece como veio, ou como a tela escreve (ex.: o CPF com pontos)
    valor_na_tela = _para_a_tela(pendencia["campo"], valor)
    return str(valor) in fala or valor_na_tela in fala


def _o_que_veio_no_arquivo(conexao, processamento_id: str, pendencia: dict) -> str:
    """A frase com a informação da pendência e o que veio no arquivo, como a empresa lê.

    Ex.: 'No arquivo, a informação "CPF" de Ana veio como "123.456.789-00".'; sem valor: 'No arquivo, a informação
    "Código CBO" de Ana veio vazia.'
    """
    quem = _a_informacao_de_quem(conexao, processamento_id, pendencia["campo"], pendencia["linha"])
    valor = _para_a_tela(pendencia["campo"], pendencia["valor"])
    if valor == "(vazio)":
        return f"No arquivo, {quem} veio vazia."
    return f'No arquivo, {quem} veio como "{valor}".'


def _com_o_dado_do_arquivo(conexao, processamento_id: str, pendencia: dict, fala: str) -> str:
    """A fala com a informação e o que veio no arquivo na frente, quando ela pergunta algo e ainda não mostra o dado.

    Vale na pendência de uma pessoa (com linha e campo); uma fala sem pergunta (ex.: "Pronto: ...") fica como está.
    Ex.: "Qual é o valor certo?" no CPF da Ana → 'No arquivo, a informação "CPF" de Ana veio como "123.456.789-00".
    Qual é o valor certo?'
    """
    de_uma_pessoa = pendencia["linha"] is not None and pendencia["campo"]
    if not de_uma_pessoa or "?" not in fala or _fala_mostra_o_dado(pendencia, fala):
        return fala
    return _o_que_veio_no_arquivo(conexao, processamento_id, pendencia) + " " + fala


# ---------------- As respostas sem valor e o encerramento educado (ADR-153) ----------------

def _fala_do_encerramento(conexao, processamento_id: str, pendencia: dict, pessoas_do_grupo: int) -> str:
    """O encerramento educado depois de LIMITE_DE_RESPOSTAS_SEM_VALOR respostas sem valor: agradece, diz que a
    pendência continua aberta e pede para revisar a informação no arquivo (ou com o funcionário) e enviar de novo.

    Recebe: a pendência; pessoas_do_grupo — quantas pessoas no cartão do grupo (0 fora do grupo).
    Ex.: 'Obrigado pela ajuda até aqui. Vou encerrar esta conversa por enquanto, e a pendência continua aberta: a
    informação "CPF" de Ana, que veio "123.456.789-00" no arquivo, ainda precisa ser conferida. Revise essa informação
    no arquivo, ou com o funcionário, e envie o arquivo de novo. Se você descobrir o valor antes, é só escrever aqui.'
    """
    informacao = _informacao(conexao, pendencia["campo"])
    valor = _para_a_tela(pendencia["campo"], pendencia["valor"])
    # De quem é a informação e com quem conferir
    if pessoas_do_grupo:
        quem = f'a informação "{informacao}" dessas {pessoas_do_grupo} pessoas'
        com_quem = ", ou com os funcionários,"
    elif pendencia["linha"] is not None:
        quem = _a_informacao_de_quem(conexao, processamento_id, pendencia["campo"], pendencia["linha"])
        com_quem = ", ou com o funcionário,"
    else:
        quem = f'a informação "{informacao}"'
        com_quem = ""
    # O que veio no arquivo (no arquivo inteiro, a informação não é de uma pessoa: fica sem essa parte)
    veio = ""
    if pendencia["linha"] is not None and valor == "(vazio)":
        veio = ", que veio vazia no arquivo,"
    elif pendencia["linha"] is not None:
        veio = f', que veio "{valor}" no arquivo,'
    return ("Obrigado pela ajuda até aqui. Vou encerrar esta conversa por enquanto, e a pendência continua aberta: "
            f"{quem}{veio} ainda precisa ser conferida. Revise essa informação no arquivo{com_quem} e envie o arquivo "
            "de novo. Se você descobrir o valor antes, é só escrever aqui.")


def _fala_sem_valor(conexao, processamento_id: str, chave: str, pendencia: dict, fala_do_agente: str,
                    pessoas_do_grupo: int) -> tuple[str, bool]:
    """A fala de uma resposta sem valor ("não sei", "não tenho") e se a conversa foi encerrada.

    Até a penúltima resposta do limite, vale a fala do agente (ele ajuda a achar o dado e pergunta de novo, mostrando o
    que veio no arquivo); na última, o encerramento educado (_fala_do_encerramento).
    Ex.: com LIMITE_DE_RESPOSTAS_SEM_VALOR = 3, a 1ª e a 2ª → (a fala do agente, False); a 3ª → (o encerramento, True).
    """
    anteriores = conversas_das_pendencias.respostas_sem_valor_desde_o_encerramento(conexao, processamento_id, chave)
    # Esta é a última resposta sem valor que a conversa aceita: o agente para de insistir
    if anteriores + 1 >= LIMITE_DE_RESPOSTAS_SEM_VALOR:
        return _fala_do_encerramento(conexao, processamento_id, pendencia, pessoas_do_grupo), True
    return fala_do_agente, False


def _pergunta_de_reserva(conexao, processamento_id: str, regra_id: str, linha: int | None,
                         campo: str | None = None) -> str:
    """A frase de reserva da pendência que continua em aberto (depois de uma troca que ainda não resolveu).

    Ex.: 'O CPF de Maria veio "123.456.789-00", e o dígito verificador não bate. Qual é o CPF certo?'
    """
    achado = _achado_em_aberto(conexao, processamento_id, regra_id, linha, campo)
    valor_lido = acompanhamento.valor_lido_para_a_tela(achado.campo, achado.valor)
    descricao = acompanhamento.descricoes_dos_campos(conexao).get(achado.campo)
    # A informação é de cada pessoa ou pode ser a mesma para todos (a marcação do parâmetro)
    igual = acompanhamento.igual_para_todos_do_achado(achado, parametros.campos_iguais_para_todos(conexao))
    return acompanhamento.pergunta_do_achado(achado, valor_lido, _nome_da_pessoa(conexao, processamento_id, linha),
                                             acompanhamento.palpite_do_achado(achado), descricao,
                                             igual_para_todos=igual)


def conversar(conexao, empresa_id: str, login: str, processamento_id: str, regra_id: str, linha: int | None,
              mensagem: str, cliente=None, busca=None, em_grupo: bool = False, campo: str | None = None) -> dict:
    """Uma rodada da conversa sobre uma pendência: a IA responde e, quando a empresa explica o que quer, já aplica.

    Recebe: conexao; empresa_id e login (da sessão); o envio; a regra e a linha da pendência; a mensagem da empresa;
            cliente e busca (o LLM e o RAG; os testes trocam por versões falsas, na vida real ficam vazios);
            em_grupo — True quando a mensagem veio do cartão do grupo (ADR-120): o valor vale para todas as pessoas
            com o mesmo valor fora da lista (o grupo é refeito aqui; se ele não existe mais, vale só para esta);
            campo — o campo da pendência (a mesma regra aparece uma vez por campo na mesma linha; sem ele, vale o
            primeiro achado da regra e da linha).
    Devolve: {mensagem, acao, fontes, aplicado ({resumo, desfazer: {tipo, id} ou None} ou None), confirmacao (numa
              retirada, {correcao_id, sim, nao}, ou None), remapeado, recusado, resolvida (a pendência saiu da lista),
              encerrada (o agente encerrou a conversa depois das respostas sem valor; a pendência continua aberta),
              chave (a da conversa guardada, a mesma da tela)}.
    "Não cadastrar" e "deixar em branco" não aplicam na hora: a retirada fica PROPOSTA e a pessoa confirma pela rota
    /assistente/confirmar (confirmar_retirada). No cartão do grupo, elas não valem (pessoa a pessoa).
    Um valor novo passa por todas as regras do campo antes de a pendência sair da lista; o que não passa volta na hora,
    com a explicação na fala (ADR-153).
    Levanta KeyError (envio de outra empresa) ou ValueError (mensagem vazia ou longa demais, etapa errada,
    pendência que não está mais em aberto).
    """
    texto = (mensagem or "").strip()
    if not texto:
        raise ValueError("Escreva a sua pergunta ou o que você sabe sobre a pendência.")
    if len(texto) > TAMANHO_MAXIMO_DA_MENSAGEM:
        raise ValueError(f"A mensagem pode ter até {TAMANHO_MAXIMO_DA_MENSAGEM} caracteres.")
    _conferir_envio_e_etapa(conexao, empresa_id, processamento_id)
    pendencia = pendencia_do_validador(conexao, processamento_id, regra_id, linha, campo)
    # Daqui em diante, o campo é o da pendência achada (o mesmo que a tela mandou, ou o único da regra e da linha)
    campo = pendencia["campo"]
    # O grupo de pessoas com o mesmo valor (só quando a mensagem veio do cartão do grupo e ele ainda existe)
    achados_do_grupo = []
    if em_grupo:
        achados_do_grupo = _achados_do_grupo(conexao, processamento_id, regra_id, linha, campo)
    linhas_do_grupo = []
    for achado_do_grupo in achados_do_grupo:
        linhas_do_grupo.append(achado_do_grupo.linha)
    # A conversa guardada (a chave e, na primeira mensagem, de quem é e a pergunta que a pessoa viu)
    chave, abertura = _chave_e_abertura(conexao, processamento_id, regra_id, linha, campo, achados_do_grupo)
    # "Usar o CNPJ da empresa" / "Usar o endereço da empresa" (ADR-127): o cadastro da empresa, sem IA
    grupo_da_empresa = dados_da_empresa_no_envio.grupo_pedido(texto, campo)
    if grupo_da_empresa and not linhas_do_grupo:
        fala, aplicado = dados_da_empresa_no_envio.usar_no_envio(conexao, empresa_id, login, processamento_id,
                                                                 grupo_da_empresa, _motivo(texto))
        resposta_da_regra = assistente_correcao.RespostaAssistente(fala, "preencher_para_todos")
        rodada = _resposta_da_rodada(conexao, processamento_id, regra_id, linha, campo, resposta_da_regra, fala,
                                     aplicado, None)
        return _guardar_a_rodada(conexao, processamento_id, chave, abertura, texto, rodada, login)
    # O agente sabe que a resposta vale para todas (prompt do agente, regra 8)
    pendencia_para_o_agente = dict(pendencia)
    if linhas_do_grupo:
        pendencia_para_o_agente["pessoas_com_o_mesmo_valor"] = len(linhas_do_grupo)
    # O valor como a empresa lê (ex.: o CPF com pontos), para a pergunta do agente mostrar o dado (ADR-153)
    pendencia_para_o_agente["valor_na_tela"] = acompanhamento.valor_lido_para_a_tela(campo, pendencia["valor"])
    # Quantas respostas sem valor a conversa já teve: o agente não repete a mesma fala (ADR-153)
    pendencia_para_o_agente["respostas_sem_valor_antes"] = (
        conversas_das_pendencias.respostas_sem_valor_desde_o_encerramento(conexao, processamento_id, chave))
    # A conversa em si: o agente decide (e grava a execução na Telemetria e a ação na trilha)
    resposta = assistente_correcao.conversar(conexao, processamento_id, empresa_id, pendencia_para_o_agente, texto,
                                             cliente=cliente, busca=busca, usuario=login)
    # A IA pediu para reler uma coluna: o mapeamento ficou pendente, e o fluxo volta para o aceite das colunas
    if resposta.remapeado:
        fluxo_empresa.retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"}, cliente=cliente,
                              busca=busca)
    # A pessoa respondeu sem um valor ("não sei", "não tenho"): nada muda; na última resposta do limite, o agente
    # encerra a conversa com educação, e a pendência continua aberta (ADR-153)
    if resposta.acao == assistente_correcao.ACAO_SEM_VALOR:
        fala, encerrada = _fala_sem_valor(conexao, processamento_id, chave, pendencia, resposta.mensagem,
                                          len(linhas_do_grupo))
        # Fora do grupo, a pergunta do agente mostra a informação e o que veio no arquivo
        if not linhas_do_grupo:
            fala = _com_o_dado_do_arquivo(conexao, processamento_id, pendencia, fala)
        rodada = _resposta_da_rodada(conexao, processamento_id, regra_id, linha, campo, resposta, fala, None, None,
                                     encerrada=encerrada)
        return _guardar_a_rodada(conexao, processamento_id, chave, abertura, texto, rodada, login)
    # No cartão do grupo: só um valor para todas muda dado
    if linhas_do_grupo:
        fala, aplicado = _conversar_no_grupo(conexao, empresa_id, login, processamento_id, pendencia,
                                             linhas_do_grupo, resposta, texto)
        rodada = _resposta_da_rodada(conexao, processamento_id, regra_id, linha, campo, resposta, fala, aplicado,
                                     None)
        return _guardar_a_rodada(conexao, processamento_id, chave, abertura, texto, rodada, login)
    fala = resposta.mensagem
    aplicado = None
    # O envio voltou para a leitura das colunas (ADR-127): a fala diz onde continuar, e o Acompanhar mostra o aviso
    if resposta.remapeado:
        fala = fala + " " + FALA_DO_ENVIO_DE_VOLTA_AS_COLUNAS
    # Fora do assunto: a recusa diz o que esta conversa ajusta
    if resposta.acao == "fora_do_assunto":
        fala = _fala_fora_do_assunto(conexao, processamento_id, pendencia)
    confirmacao = None
    # Tirar a pessoa ou deixar o dado em branco: antes, a pessoa confirma
    if e_retirada(resposta.acao, resposta.valor):
        try:
            fala, confirmacao = _pedir_confirmacao(conexao, empresa_id, login, processamento_id, pendencia,
                                                   resposta.acao, texto)
        except (ValueError, KeyError) as erro:
            fala = _fala_de_valor_recusado(erro)
    # A informação que o arquivo inteiro não trouxe está em outra coluna (ADR-124): a conferência dos valores e,
    # se a maioria passa, a pergunta de confirmação (nada muda antes do "Sim")
    elif resposta.acao == "usar_coluna":
        try:
            fala, confirmacao = _propor_a_coluna(conexao, processamento_id, pendencia, resposta.coluna)
        except ValueError as erro:
            fala = str(erro)
    # A empresa disse o que quer: aplica na hora (a regra de negócio ainda pode recusar o valor)
    # (antes, o valor é conferido: com o valor errado, nada muda e o cartão pergunta de novo; ADR-127)
    elif resposta.acao in assistente_correcao.ACOES_QUE_MUDAM_DADO:
        recusa = _recusa_do_valor(conexao, processamento_id, pendencia, resposta)
        if recusa:
            fala = recusa
        else:
            try:
                # O relatório de antes da troca: a conferência compara com o de depois (ADR-153)
                antes = _achados_para_conferir(conexao, processamento_id)
                fala, aplicado = _aplicar(conexao, empresa_id, login, processamento_id, pendencia, resposta, texto,
                                          cliente, busca)
                # Um valor novo passa por todas as regras do Validador; se não passar, a troca volta na hora
                if resposta.acao in ACOES_COM_VALOR_NOVO:
                    fala, aplicado = _conferir_o_que_mudou(conexao, empresa_id, login, processamento_id, pendencia,
                                                           {_chave_da_pendencia(pendencia)}, antes, fala, aplicado,
                                                           _linhas_da_troca(pendencia, resposta), em_grupo=False)
            except (ValueError, KeyError) as erro:
                fala = _fala_de_valor_recusado(erro)
    # Nada mudou e o agente pergunta algo: a pergunta mostra a informação e o que veio no arquivo (ADR-153)
    if aplicado is None and confirmacao is None:
        fala = _com_o_dado_do_arquivo(conexao, processamento_id, pendencia, fala)
    rodada = _resposta_da_rodada(conexao, processamento_id, regra_id, linha, campo, resposta, fala, aplicado,
                                 confirmacao)
    return _guardar_a_rodada(conexao, processamento_id, chave, abertura, texto, rodada, login)


def _linhas_da_troca(pendencia: dict, resposta) -> set | None:
    """As linhas que a troca muda: a da pessoa, na correção; None no "preencher para todos" (várias linhas, todas as
    que estavam sem o dado). Ex.: corrigir na linha 8 → {8}."""
    if resposta.acao == "preencher_para_todos" or pendencia["linha"] is None:
        return None
    return {pendencia["linha"]}


# ---------------- A conversa guardada no servidor (pendências resolvidas, ADR-120) ----------------

def _titulo_da_pessoa(conexao, processamento_id: str, linha: int | None) -> str:
    """De quem é a conversa, como o cartão mostra. Ex.: "Ana Lima"; sem nome, "Funcionário da linha 8"; sem linha,
    "Arquivo inteiro"."""
    if linha is None:
        return pergunta_da_pendencia.SEM_PESSOA
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] == linha and registro.get("nome_completo"):
            return registro["nome_completo"]
    return f"{pergunta_da_pendencia.SEM_NOME} {linha}"


def _chave_e_abertura(conexao, processamento_id: str, regra_id: str, linha: int | None, campo: str | None,
                      achados_do_grupo: list) -> tuple[str, dict | None]:
    """A chave da conversa e, se ela ainda não existe, a abertura: {titulo, nome_do_campo, quantidade, pergunta}.

    A pergunta é a que a pessoa viu no cartão (a da IA, se guardada, ou a de reserva), montada ANTES de qualquer
    mudança (depois, a pendência pode sumir do relatório).
    """
    # A chave: a do grupo, no cartão do grupo; senão, a da pessoa (a mesma da tela)
    if achados_do_grupo:
        chave_do_grupo = pendencias_em_grupo.chave_do_grupo(achados_do_grupo[0])
        chave = conversas_das_pendencias.chave_da_conversa_do_grupo(processamento_id, chave_do_grupo)
    else:
        chave = conversas_das_pendencias.chave_da_conversa(processamento_id, regra_id, linha, campo)
    # A conversa já começou: nada de abertura
    if conversas_das_pendencias.conversa_existe(conexao, processamento_id, chave):
        return chave, None
    achado = _achado_em_aberto(conexao, processamento_id, regra_id, linha, campo)
    # O título do cartão (o mesmo que a pessoa viu): o que fazer, a informação e de quem
    tipo = "corrigir" if achado.severidade == validador.BLOQUEANTE else "confirmar"
    descricao = acompanhamento.descricoes_dos_campos(conexao).get(achado.campo)
    if achados_do_grupo:
        quantidade = len(achados_do_grupo)
        titulo = acompanhamento.titulo_do_cartao(regra_id, achado.campo, tipo, None, descricao,
                                                 quantidade=quantidade)
        pergunta = acompanhamento.pergunta_mostrada_do_grupo(conexao, processamento_id, achados_do_grupo)
    else:
        quantidade = 1
        nome = _titulo_da_pessoa(conexao, processamento_id, linha)
        coluna_do_formato = acompanhamento.coluna_da_duvida_de_formato(conexao, processamento_id, regra_id,
                                                                       achado.mensagem)
        titulo = acompanhamento.titulo_do_cartao(regra_id, achado.campo, tipo, nome, descricao, coluna_do_formato)
        pergunta = acompanhamento.pergunta_mostrada(conexao, processamento_id, achado, nome)
    return chave, {"titulo": titulo, "nome_do_campo": acompanhamento.nome_simples_do_campo(conexao, achado.campo),
                   "quantidade": quantidade, "pergunta": pergunta}


def _guardar_a_rodada(conexao, processamento_id: str, chave: str, abertura: dict | None, texto: str, rodada: dict,
                      login: str) -> dict:
    """Grava na conversa o que a pessoa escreveu e a resposta do agente, e devolve a rodada com a chave da conversa e a
    posição da resposta nela ("ordem").

    A resposta sem valor e o encerramento ficam marcados no balão do agente: é por eles que a conversa conta as
    respostas sem valor (ADR-153).
    """
    baloes = [conversas_das_pendencias.fala("empresa", texto),
              conversas_das_pendencias.fala("ia", rodada["mensagem"], aplicado=rodada["aplicado"],
                                            confirmacao=rodada["confirmacao"], recusado=rodada["recusado"],
                                            fontes=rodada["fontes"],
                                            sem_valor=rodada["acao"] == assistente_correcao.ACAO_SEM_VALOR,
                                            encerrada=rodada["encerrada"])]
    conversas_das_pendencias.registrar(conexao, processamento_id, chave, abertura, baloes, login)
    rodada["chave"] = chave
    # A posição da resposta do agente na conversa (o último balão gravado): é por ela que o joinha da tela vota
    rodada["ordem"] = conversas_das_pendencias.ordem_da_ultima_fala(conexao, processamento_id, chave)
    return rodada


def _resposta_da_rodada(conexao, processamento_id: str, regra_id: str, linha: int | None, campo: str | None,
                        resposta, fala: str, aplicado: dict | None, confirmacao: dict | None,
                        encerrada: bool = False) -> dict:
    """O que a tela recebe de uma rodada da conversa (ver conversar), com "resolvida" conferido no relatório novo.

    encerrada: True quando o agente encerrou a conversa depois das respostas sem valor (ADR-153).
    """
    # A pendência saiu da lista? (um alerta que só pergunta pode continuar aberto com o valor novo)
    resolvida = _achado_em_aberto(conexao, processamento_id, regra_id, linha, campo) is None
    if aplicado and not resolvida:
        ainda_falta = _pergunta_de_reserva(conexao, processamento_id, regra_id, linha, campo)
        fala = fala + " Ainda há um problema: " + ainda_falta
    return {"mensagem": fala, "acao": resposta.acao, "fontes": resposta.fontes or [], "aplicado": aplicado,
            "confirmacao": confirmacao, "remapeado": resposta.remapeado, "recusado": resposta.recusado,
            "resolvida": resolvida, "encerrada": encerrada}


def _separar_regra_e_linha(identificador: str) -> tuple[str, int | None]:
    """ "RENDA_FORA_DO_CARGO|7" → ("RENDA_FORA_DO_CARGO", 7); "REGRA|" → ("REGRA", None). Levanta ValueError."""
    if "|" not in identificador:
        raise ValueError("Não sei desfazer isso.")
    regra_id, linha_em_texto = identificador.rsplit("|", 1)
    if linha_em_texto == "":
        return regra_id, None
    if not linha_em_texto.isdigit():
        raise ValueError("Não sei desfazer isso.")
    return regra_id, int(linha_em_texto)


def desfazer(conexao, empresa_id: str, login: str, processamento_id: str, tipo: str, identificador: str) -> dict:
    """ "Desfazer" na conversa: volta o que a IA aplicou e valida o envio de novo (a pendência volta, se for o caso).

    Recebe: o envio; tipo — "correcao" (troca de valor ou "não cadastrar"), "para_todos", "grupo" (a troca feita no
            cartão do grupo, ADR-120) ou "confirmacao";
            identificador — o id que veio em aplicado.desfazer.
    Devolve: {"desfeito": True, "resumo": "Voltei CPF para 123.456.789-00."}.
    Levanta KeyError (outra empresa) ou ValueError (etapa errada, já desfeito, dado mudado de novo depois).
    O balão que trouxe a mudança vira "Desfeito" na conversa guardada, e o que voltou entra como uma fala do agente.
    """
    _conferir_envio_e_etapa(conexao, empresa_id, processamento_id)
    resultado = _desfazer_a_mudanca(conexao, empresa_id, login, processamento_id, tipo, identificador)
    conversas_das_pendencias.registrar_o_desfazer(conexao, processamento_id, tipo, identificador, resultado["resumo"],
                                                  login)
    return resultado


def _desfazer_a_mudanca(conexao, empresa_id: str, login: str, processamento_id: str, tipo: str,
                        identificador: str) -> dict:
    """Volta a mudança pelo tipo dela (ver desfazer). Devolve {"desfeito": True, "resumo": ...}."""
    if tipo == DESFAZER_CORRECAO:
        correcao = correcoes.desfazer(conexao, processamento_id, empresa_id, identificador, login)
        # "Não cadastrar" desfeito: a pessoa volta para o envio
        if correcao.campo == correcoes.EXCLUIR:
            nome = _nome_da_pessoa(conexao, processamento_id, correcao.linha)
            return {"desfeito": True, "resumo": f"Voltei {nome} para o envio."}
        return {"desfeito": True,
                "resumo": f"Voltei {_informacao(conexao, correcao.campo)} para "
                          f"{_para_a_tela(correcao.campo, correcao.antes)}."}
    if tipo == DESFAZER_PARA_TODOS:
        quantos = correcoes.desfazer_lote(conexao, processamento_id, empresa_id, identificador, login)
        return {"desfeito": True,
                "resumo": f"Desfiz o preenchimento: {_plural_de_funcionarios(quantos)} sem este dado de novo."}
    if tipo == DESFAZER_GRUPO:
        # A troca em grupo inteira volta (ADR-120): cada pessoa volta ao valor do arquivo, e a pendência reaparece
        quantos = correcoes.desfazer_lote(conexao, processamento_id, empresa_id, identificador, login,
                                          evento="CORRECAO_EM_GRUPO_DESFEITA")
        return {"desfeito": True,
                "resumo": f"Desfiz a troca: {_plural_de_pessoas(quantos)} com o valor do arquivo de novo."}
    if tipo == DESFAZER_POR_PESSOA:
        # A lista "Informar pessoa a pessoa" inteira volta (ADR-124): todos sem o dado de novo, e o cartão reaparece
        quantos = correcoes.desfazer_lote(conexao, processamento_id, empresa_id, identificador, login,
                                          evento="CORRECAO_POR_PESSOA_DESFEITA")
        return {"desfeito": True,
                "resumo": f"Desfiz o que foi informado: {_plural_de_pessoas(quantos)} sem este dado de novo."}
    if tipo == DESFAZER_COLUNA:
        # A coluna volta para o campo de antes (ADR-124): a leitura é refeita, e o cartão da informação que faltou
        # reaparece. O id é "coluna|campo de antes" (vazio: a coluna estava de fora)
        if "|" not in identificador:
            raise ValueError("Não sei desfazer isso.")
        coluna, campo_de_antes = identificador.rsplit("|", 1)
        coluna_do_campo_que_falta.usar_coluna(conexao, empresa_id, login, processamento_id, coluna,
                                              campo_de_antes or None)
        return {"desfeito": True, "resumo": f'Voltei a coluna "{coluna}" para "{_nome_curto(campo_de_antes)}".'}
    if tipo == DESFAZER_DADOS_DA_EMPRESA:
        # "Usar o CNPJ (ou o endereço) da empresa" inteiro volta (ADR-127): todos os campos preenchidos de uma vez
        resumo = dados_da_empresa_no_envio.desfazer_tudo(conexao, empresa_id, login, processamento_id, identificador)
        return {"desfeito": True, "resumo": resumo}
    if tipo == DESFAZER_CONFIRMACAO:
        regra_id, linha = _separar_regra_e_linha(identificador)
        validador.reabrir_alerta(conexao, processamento_id, empresa_id, regra_id, linha, login)
        return {"desfeito": True, "resumo": "Desfiz a confirmação: o alerta voltou para você conferir."}
    raise ValueError("Não sei desfazer isso.")
