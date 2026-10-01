"""Cadastrar funcionários pelo novo front: enviar o arquivo e conduzir o fluxo da IA até a homologação (ADR-69).

Para que serve: a tela "Cadastrar funcionários" do Portal Empresa (front/cadastrar.html) precisa, na ordem:
    1. enviar o arquivo: a aplicação lê, registra o envio e roda o fluxo até a primeira pausa (a IA propõe o
       mapeamento das colunas);
    2. ver a leitura: as colunas, o campo que a IA propôs para cada uma e por quê, e o que falta decidir;
    3. aceitar o mapeamento (com as escolhas da pessoa): o fluxo padroniza e valida;
    4. decidir o formato de uma coluna inteira (datas dia/mês ou mês/dia; quantos dígitos tem a matrícula);
    5. conferir a lista do jeito que vai para o banco e corrigir um valor com um clique;
    6. "Ajude a IA a acertar": pedir que a IA releia uma ou mais colunas, cada uma com uma dica da empresa (o
       mapeamento volta ao aceite; tudo conta como uma releitura);
    7. enviar ao banco (quando não sobra pendência; com "Conferi a lista" registrado) ou descartar a leitura.

Este arquivo NÃO tem regra nova: só liga os serviços que já existem (processamentos.receber_arquivo e o fluxo em
LangGraph, workflows/fluxo_empresa.py) e monta, para a tela, a leitura em linguagem simples. As pendências do meio do
caminho se resolvem com services/acompanhamento.py (corrigir, confirmar, tirar linha repetida).

Toda função recebe a empresa da SESSÃO: o fluxo confere que o envio é dela antes de qualquer coisa (KeyError se não).
"""
import re
from datetime import date

from models.contratos import DivisaoProposta, EstadoProcessamento, ItemMapeamento, ParteDaDivisao, StatusMapeamento
from services import (acompanhamento, auditoria, correcoes, divisao, divisao_da_coluna, ingestao, mapeamentos,
                      normalizador, parametros, processamentos, progresso, teto_de_gasto, validador)
# O que a IA achou sem ter certeza do campo vai para o detalhe de cada pessoa da lista (ADR-143, Parte 1)
from services import informacoes_sem_rotulo
from workflows import fluxo_empresa

# O motivo gravado nas correções feitas na conferência da lista (quem corrigiu fica no registro da correção)
MOTIVO_DA_CONFERENCIA = "Corrigido pela empresa na conferência da lista"
# A justificativa registrada quando a empresa clica em "Está certo assim" sem escrever o porquê
JUSTIFICATIVA_PADRAO_DA_CONFERENCIA = "Confirmado pela empresa na conferência da lista"
# As etapas em que a lista já foi padronizada e ainda não foi para o banco (dá para conferir e corrigir)
ETAPAS_DA_CONFERENCIA = ("aguardar_correcao", "aprovar_homologacao")

# Como aparece a coluna cujo campo a empresa trocou (ela manda: vale o que ela escolheu)
SITUACAO_AJUSTADA_PELA_EMPRESA = "Ajustado por você"
# A coluna que a IA dividiu (ADR-104) e cada parte dela; a coluna que a empresa dividiu
SITUACAO_DIVIDIDA_PELA_IA = "Dividida pelo Agente Interpretador"
SITUACAO_PARTE_DA_IA = "Dividido pelo Agente Interpretador"
SITUACAO_DIVIDIDA_PELA_EMPRESA = "Dividida por você"
# Quantas linhas a prévia de uma coluna dividida mostra
LINHAS_DA_PREVIA_DA_DIVISAO = 3
# Quantas colunas a empresa pode explicar numa releitura do "Ajude a IA a acertar"
MAXIMO_DE_COLUNAS_POR_RELEITURA = 5

# Como cada situação do mapeamento aparece para a empresa
SITUACAO_DA_COLUNA = {
    StatusMapeamento.PROPOSTO: "Reconhecida",
    StatusMapeamento.AMBIGUO: "Escolha o campo",
    StatusMapeamento.NAO_MAPEADO: "Deixada de fora",
}

# A escolha que ignora uma coluna (a mesma de services/mapeamentos.py)
IGNORAR = mapeamentos.IGNORAR


def _exemplo_para_a_tela(valor: str) -> str:
    """Um valor de exemplo da coluna, para a empresa reconhecer o dado em "Como a IA leu".

    O valor aparece inteiro: é o dado que a própria empresa enviou, e é o sistema que mostra, não a IA (ADR-97).
    Ex.: "Helena Duarte Ramos" → "Helena Duarte Ramos"; "  analista " → "analista".
    """
    return valor.strip()


def _primeiro_valor_da_coluna(leitura, coluna: str) -> str:
    """O primeiro valor preenchido da coluna (vazio se a coluna não tem nenhum)."""
    posicao = leitura.cabecalhos.index(coluna)
    for linha in leitura.linhas:
        if linha[posicao].strip():
            return linha[posicao].strip()
    return ""


def _colunas_da_leitura(plano, perfil, leitura=None, campos_por_nome=None) -> list[dict]:
    """As colunas do arquivo, uma por item do plano, no formato da tela.

    Recebe: plano (MappingPlan); perfil (o retrato do envio); leitura e campos_por_nome ({campo: CampoLayout}), para o
    exemplo de cada coluna (sem leitura, o exemplo fica vazio).
    Devolve: lista de {coluna, campo, situacao, precisa_decidir, justificativa, candidatos, origem, no_documento,
    pessoas, exemplo}. "precisa_decidir" é verdadeiro nas colunas em que a IA pediu ajuda (AMBIGUO); a situação é
    "Ajustado por você" quando a empresa trocou o campo que a IA propôs. "exemplo" é o primeiro valor da coluna, com a
    máscara decidida pelo parâmetro (ver _exemplo_para_a_tela).
    No Word em texto corrido (origem "leitor"), cada coluna é um jeito de a empresa chamar o dado: "no_documento" traz
    o rótulo (ex.: ["Documento fiscal"]) e "pessoas", em quantas pessoas ele apareceu. Assim a empresa vê cada pedaço
    que a IA separou e troca o campo só dele (ADR-73).
    """
    colunas = []
    for item in plano.itens:
        origem_no_documento = perfil.origem_das_colunas.get(item.coluna, {})
        situacao = _situacao_da_coluna(item)
        exemplo = ""
        if leitura is not None and item.coluna in leitura.cabecalhos:
            valor = _primeiro_valor_da_coluna(leitura, item.coluna)
            if valor:
                exemplo = _exemplo_para_a_tela(valor)
        colunas.append({
            "coluna": item.coluna,
            "campo": item.campo,
            "situacao": situacao,
            "precisa_decidir": item.status == StatusMapeamento.AMBIGUO,
            "justificativa": item.justificativa,
            "candidatos": list(item.candidatos),
            "origem": item.origem,
            "no_documento": mapeamentos.rotulos_da_origem(origem_no_documento),
            "pessoas": origem_no_documento.get("pessoas"),
            "exemplo": exemplo,
        })
        # A coluna dividida: como ela foi dividida, a prévia e quantas vezes ainda dá para pedir para refazer
        if item.divisao is not None:
            colunas[-1]["divisao"] = _divisao_para_a_tela(item, leitura)
        # Uma parte de coluna dividida: de qual coluna ela saiu
        colunas[-1]["parte_de"] = _coluna_de_origem_da_parte(item.coluna, plano)
    return colunas


def _situacao_da_coluna(item: ItemMapeamento) -> str:
    """Como a situação da coluna aparece para a empresa ("Reconhecida", "Dividida pela IA", "Ajustado por você"...)."""
    if item.divisao is not None and item.origem == "llm":
        return SITUACAO_DIVIDIDA_PELA_IA
    if item.divisao is not None:
        return SITUACAO_DIVIDIDA_PELA_EMPRESA
    if item.origem == "humano" and item.status == StatusMapeamento.PROPOSTO:
        return SITUACAO_AJUSTADA_PELA_EMPRESA
    if item.origem == "llm" and item.status == StatusMapeamento.PROPOSTO and divisao_da_coluna.SINAL_DA_PARTE in item.coluna:
        return SITUACAO_PARTE_DA_IA
    return SITUACAO_DA_COLUNA[item.status]


def _coluna_de_origem_da_parte(coluna: str, plano) -> str | None:
    """A coluna dividida de onde esta parte saiu ("Endereço · rua" → "Endereço"), ou None se não é parte."""
    for item in plano.itens:
        if item.divisao is not None and coluna.startswith(item.coluna + divisao_da_coluna.SINAL_DA_PARTE):
            return item.coluna
    return None


def _divisao_para_a_tela(item: ItemMapeamento, leitura) -> dict:
    """A divisão de uma coluna como a tela mostra: as partes (nome e campo), a prévia e o que falta para refazer.

    Devolve: {ferramenta, partes: [{parte, nome, campo}], previa: {colunas: [...], linhas: [[...]]},
    refazer_restantes}. A prévia são as primeiras linhas com valor, parte por parte, como estão no arquivo.
    """
    proposta = item.divisao
    partes = []
    for parte in proposta.partes:
        partes.append({"parte": parte.parte, "nome": divisao.nome_da_parte(proposta.ferramenta, parte.parte),
                       "campo": parte.campo})
    previa = {"colunas": [], "linhas": []}
    if leitura is not None and item.coluna in leitura.cabecalhos:
        # As colunas das partes que existem na tabela
        prefixo = item.coluna + divisao_da_coluna.SINAL_DA_PARTE
        posicoes = []
        for posicao, cabecalho in enumerate(leitura.cabecalhos):
            if cabecalho.startswith(prefixo):
                posicoes.append(posicao)
                previa["colunas"].append(cabecalho[len(prefixo):])
        posicao_da_original = leitura.cabecalhos.index(item.coluna)
        for linha in leitura.linhas:
            if len(previa["linhas"]) == LINHAS_DA_PREVIA_DA_DIVISAO:
                break
            # Só linhas em que a coluna original tem valor
            if not linha[posicao_da_original].strip():
                continue
            valores = [linha[posicao_da_original]]
            for posicao in posicoes:
                valores.append(linha[posicao])
            previa["linhas"].append(valores)
    return {"ferramenta": proposta.ferramenta, "partes": partes, "previa": previa,
            "refazer_restantes": max(divisao_da_coluna.LIMITE_DE_REFAZER - proposta.refeita, 0)}


def _campos_por_nome(conexao) -> dict:
    """{nome do campo: CampoLayout} do layout ativo."""
    _, campos = parametros.layout_ativo(conexao)
    campos_por_nome = {}
    for campo in campos:
        campos_por_nome[campo.campo] = campo
    return campos_por_nome


def leitura_do_envio(conexao, empresa_id: str, processamento_id: str) -> dict:
    """Onde o envio está e o que a IA leu, para a tela "Cadastrar funcionários".

    Recebe: conexao; empresa_id (da sessão); processamento_id.
    Devolve: {processamento_id, tipo, linhas, etapa, nome_da_etapa, terminou, erro, reaproveitou_mapeamento,
              colunas, obrigatorios_sem_coluna, pendencias, avisos, formatos_pendentes, campos_do_layout,
              aviso_do_nome}. aviso_do_nome: a frase quando já há outro arquivo com o mesmo nome, ou None.
      - etapa: a pausa em que o fluxo espera a pessoa ("aprovar_mapeamento", "aguardar_correcao",
        "aprovar_homologacao"...) ou None se terminou;
      - reaproveitou_mapeamento: True quando as colunas são as de um envio já aprovado (a IA nem foi chamada);
      - pendencias: contagem por severidade da última validação.
    Levanta KeyError se o envio não é da empresa.
    """
    # O retrato do envio, só se for da empresa
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise KeyError(processamento_id)
    # Onde o fluxo está
    situacao = fluxo_empresa.situacao(conexao, processamento_id)
    estado = situacao["estado"]
    # O recado da pausa (ex.: "escolha o campo destas colunas") ou o último erro guardado
    erro = None
    if situacao["pergunta"]:
        erro = situacao["pergunta"].get("erro")
    # O envio pausado pelo teto de gasto: nesta tela o recado aponta o botão "Tentar de novo" (ADR-139)
    if erro == teto_de_gasto.RECADO_PARA_A_EMPRESA:
        erro = teto_de_gasto.RECADO_DO_ENVIO_PAUSADO
    # O mapeamento proposto (pode não existir se o fluxo falhou antes)
    colunas = []
    obrigatorios_sem_coluna = []
    reaproveitou = False
    existente = mapeamentos.obter(conexao, processamento_id)
    if existente is not None:
        plano = existente[0]
        # Enquanto a empresa confere as colunas (aceite e conferência), a tabela é lida para o exemplo de cada coluna
        leitura_guardada = None
        if situacao["etapa_atual"] in ("aprovar_mapeamento",) + ETAPAS_DA_CONFERENCIA:
            leitura_guardada = processamentos.carregar_tabela(conexao, processamento_id)
        colunas = _colunas_da_leitura(plano, perfil, leitura_guardada, _campos_por_nome(conexao))
        obrigatorios_sem_coluna = mapeamentos.obrigatorios_sem_coluna(conexao, plano)
        # Reaproveitou só quando as colunas vieram de um envio já aprovado (no Word em texto corrido, a IA do
        # mapeamento também não é chamada, mas porque o Leitor de Documentos já leu os campos)
        reaproveitou = not plano.chamou_llm and plano.modelo == "reuso"
    # A leitura em linguagem simples
    return {
        "processamento_id": processamento_id,
        "tipo": "Carga inicial" if perfil.tipo_carga.value == "INICIAL" else "Inclusão",
        "linhas": perfil.n_linhas,
        "etapa": situacao["etapa_atual"],
        "nome_da_etapa": fluxo_empresa.NOMES_DAS_ETAPAS.get(situacao["etapa_atual"], "Concluído"),
        "terminou": situacao["terminou"],
        "erro": erro,
        "reaproveitou_mapeamento": reaproveitou,
        "colunas": colunas,
        "obrigatorios_sem_coluna": obrigatorios_sem_coluna,
        "pendencias": estado.get("pendencias", {}),
        "avisos": list(perfil.avisos),
        "duvidas": list(perfil.duvidas),
        "perguntas_da_ia": _perguntas_da_ia_para_responder(conexao, perfil),
        "formato": perfil.formato,
        "formatos_pendentes": formatos_pendentes(conexao, processamento_id),
        "campos_do_layout": _nomes_dos_campos(conexao),
        # Para onde uma coluna pode ser dividida (ex.: o endereço inteiro numa célula, ADR-76)
        "destinos_da_divisao": destinos_da_divisao(conexao),
        # O aviso de que já há outro arquivo com o mesmo nome (e como este aparece na tela), ou None
        "aviso_do_nome": aviso_de_nome_repetido(conexao, empresa_id, perfil),
        # O número único das pendências (o painel "Linhas do arquivo" mostra o mesmo da conferência), ou None
        "resumo_das_pendencias": _resumo_da_leitura(conexao, processamento_id, situacao["etapa_atual"]),
    }


def _resumo_da_leitura(conexao, processamento_id: str, etapa: str | None) -> dict | None:
    """O resumo das pendências para o painel da leitura, depois da primeira validação.

    Recebe: conexao; processamento_id; etapa (a pausa do fluxo). Devolve: o resumo_das_pendencias, ou None enquanto
    as colunas não foram aceitas (os dados ainda não foram conferidos).
    """
    if etapa == "aprovar_mapeamento":
        return None
    relatorio = validador.obter(conexao, processamento_id)
    if relatorio is None:
        return None
    registros = correcoes.dados_atuais(conexao, processamento_id).registros
    return resumo_das_pendencias(relatorio, registros)


def aviso_de_nome_repetido(conexao, empresa_id: str, perfil) -> str | None:
    """O aviso para a empresa quando ela já enviou outro arquivo com o mesmo nome.

    Recebe: conexao; empresa_id; perfil (o retrato do envio). Devolve: a frase, ou None se o nome não se repete.
    Ex.: 'Você já enviou outro arquivo com o nome "aurora.xlsx". Para não confundir, este aparece como
    "aurora.xlsx (v2)" nas pendências e na lista para o banco.'
    """
    nome_na_tela = processamentos.nomes_na_tela(conexao, empresa_id)[perfil.processamento_id]
    if nome_na_tela == perfil.nome_arquivo:
        return None
    return (f'Você já enviou outro arquivo com o nome "{perfil.nome_arquivo}". Para não confundir, este aparece como '
            f'"{nome_na_tela}" nas pendências e na lista para o banco.')


def _nomes_dos_campos(conexao) -> list[str]:
    """Os nomes dos campos do layout ativo, na ordem (para a empresa trocar o campo de uma coluna no aceite)."""
    _, campos = parametros.layout_ativo(conexao)
    nomes = []
    for campo in campos:
        nomes.append(campo.campo)
    return nomes


def _campos_opcionais(conexao) -> set[str]:
    """Os nomes técnicos dos campos opcionais do parâmetro vigente: eles não pedem nada à empresa (ADR-143).

    Ex.: no parâmetro com só o cpf, o codigo_cbo, a valor_renda e a data_admissao obrigatórios → {"matricula", ...}.
    """
    _, campos = parametros.layout_ativo(conexao)
    opcionais = set()
    for campo in campos:
        if not campo.obrigatorio:
            opcionais.add(campo.campo)
    return opcionais


def formatos_pendentes(conexao, processamento_id: str) -> list[dict]:
    """As colunas inteiras cujo formato a empresa precisa decidir (datas ambíguas, zeros à esquerda da matrícula).

    Recebe: conexao; processamento_id. Devolve: [{coluna, tipo, mensagem}] ("DATA_AMBIGUA" ou "ZEROS_A_ESQUERDA").
    Vazio antes da padronização ou quando não há dúvida. A dúvida de uma coluna de campo opcional fica de fora, como no
    Validador: um campo opcional não pede nada à empresa (ADR-143). A dúvida sem o campo (gravada por uma
    padronização antiga) fica, porque não dá para saber se o campo é opcional.
    Ex.: a matrícula sem os zeros, com a matrícula opcional → nada a decidir.
    """
    normalizacao = normalizador.obter(conexao, processamento_id)
    if normalizacao is None:
        return []
    campos_opcionais = _campos_opcionais(conexao)
    pendentes = []
    for pendencia in normalizacao.pendencias_de_coluna:
        # A dúvida de uma coluna de campo opcional não pede decisão
        if pendencia.get("campo") in campos_opcionais:
            continue
        pendentes.append({"coluna": pendencia["coluna"], "tipo": pendencia["tipo"], "mensagem": pendencia["mensagem"]})
    return pendentes


def _perguntas_da_ia_para_responder(conexao, perfil) -> int:
    """Quantas perguntas da IA a empresa responde: as de campo obrigatório e as sobre a pessoa toda (sem campo).

    A pergunta sobre um campo opcional não vira pendência no Validador (ADR-143) e não entra na conta: o número que a
    conversa do Cadastrar diz é o mesmo da conferência.
    Ex.: 3 perguntas (cpf, nome_mae e uma sobre a pessoa toda), com o nome_mae opcional → 2.
    """
    campos_opcionais = _campos_opcionais(conexao)
    quantidade = 0
    for pergunta in perfil.perguntas_da_ia:
        # A pergunta sobre um campo opcional não pede nada
        if pergunta.get("campo") in campos_opcionais:
            continue
        quantidade = quantidade + 1
    return quantidade


def cpfs_da_leitura(leitura) -> set[str]:
    """Os CPFs (só os dígitos, 11) das colunas de CPF do arquivo lido: as que o Leitor de Documentos leu como cpf
    (Word em texto corrido), a que se chama "cpf" ou a que tem cara de CPF no retrato das colunas.
    Sem coluna de CPF, devolve vazio (nada a comparar)."""
    posicoes = []
    for perfil in ingestao.perfil_das_colunas(leitura):
        # No texto corrido, a origem diz o campo que o Leitor leu na coluna
        lida_como_cpf = False
        origem = leitura.origem_das_colunas.get(perfil["nome"])
        if origem is not None:
            lida_como_cpf = mapeamentos.campo_lido_pelo_leitor(perfil["nome"], origem) == "cpf"
        if lida_como_cpf or perfil["nome"].lower() == "cpf" or perfil["tipo_provavel"] == "CPF":
            posicoes.append(perfil["posicao"] - 1)
    cpfs = set()
    for linha in leitura.linhas:
        for posicao in posicoes:
            digitos = re.sub(r"\D", "", linha[posicao])
            if len(digitos) == 11:
                cpfs.add(digitos)
    return cpfs


# Onde está a pessoa que a empresa já mandou (a mensagem do arquivo sem ninguém novo diz, em números, por quê)
JA_CADASTRADA = "já cadastrada(s)"
EM_ANALISE_NO_BANCO = "em análise no banco"
EM_OUTRO_ARQUIVO = "em outro arquivo que ainda não foi ao banco"


def pessoas_ja_conhecidas(conexao, empresa_id: str) -> dict[str, str]:
    """Os CPFs que a empresa já mandou, cada um com onde ele está: cadastrado, em análise no banco ou em outro envio
    que ainda está com a empresa.

    Devolve: {cpf: JA_CADASTRADA, EM_ANALISE_NO_BANCO ou EM_OUTRO_ARQUIVO}. Quem foi devolvido pelo banco e saiu do
    envio de devolução não está em lugar nenhum: pode voltar num arquivo novo (ADR-121 e ADR-126).
    """
    conhecidos = {}
    for pessoa in validador.homologados_da_empresa(conexao, empresa_id):
        conhecidos[pessoa["cpf"]] = JA_CADASTRADA
    for cpf in validador.pessoas_de_outros_envios(conexao, empresa_id, None, (EstadoProcessamento.AGUARDANDO_BANCO,)):
        conhecidos.setdefault(cpf, EM_ANALISE_NO_BANCO)
    for cpf in validador.pessoas_de_outros_envios(conexao, empresa_id, None, validador.ESTADOS_COM_A_EMPRESA):
        conhecidos.setdefault(cpf, EM_OUTRO_ARQUIVO)
    return conhecidos


def mensagem_de_nada_novo(cpfs_do_arquivo: set[str], conhecidos: dict[str, str]) -> str:
    """A mensagem do arquivo em que todas as pessoas já foram mandadas antes, com quantas estão em cada lugar.

    Exemplo: 5 CPFs, 3 cadastrados e 2 em análise → 'Nada novo para enviar: as 5 pessoas deste arquivo já foram
    mandadas antes (3 já cadastrada(s), 2 em análise no banco). Nada foi enviado; confira em "Acompanhar cadastros".'
    """
    quantas_em_cada_lugar = {}
    for cpf in cpfs_do_arquivo:
        lugar = conhecidos[cpf]
        quantas_em_cada_lugar[lugar] = quantas_em_cada_lugar.get(lugar, 0) + 1
    partes = []
    # Sempre na mesma ordem: cadastradas, em análise, em outro arquivo
    for lugar in (JA_CADASTRADA, EM_ANALISE_NO_BANCO, EM_OUTRO_ARQUIVO):
        if lugar in quantas_em_cada_lugar:
            partes.append(f"{quantas_em_cada_lugar[lugar]} {lugar}")
    if len(cpfs_do_arquivo) == 1:
        comeco = "a pessoa deste arquivo já foi mandada antes"
    else:
        comeco = f"as {len(cpfs_do_arquivo)} pessoas deste arquivo já foram mandadas antes"
    return (f"Nada novo para enviar: {comeco} ({', '.join(partes)}). Nada foi enviado; confira em "
            "\"Acompanhar cadastros\".")


def enviar_arquivo(conexao, empresa_id: str, login: str, conteudo: bytes, nome_do_arquivo: str,
                   cliente=None, busca=None) -> dict:
    """Recebe o arquivo da empresa, começa o fluxo e devolve a leitura (com o mapeamento proposto pela IA).

    Recebe: conexao; empresa_id (da sessão); login de quem enviou; o conteúdo e o nome do arquivo;
            cliente e busca (o LLM e o RAG; os testes trocam por versões falsas, na vida real ficam vazios).
    Devolve: a leitura (leitura_do_envio), com "duplicado": True se o mesmo arquivo já tinha sido enviado.
    Levanta ingestao.ArquivoRecusado (um ValueError) com a mensagem para a empresa, se o arquivo não servir.
    """
    # Antes de virar um envio: se todas as pessoas do arquivo já estão cadastradas ou num envio pendente, recusa
    def recusar_se_nada_novo(leitura):
        """Recusa o arquivo quando ele não traz nenhuma pessoa nova para a empresa."""
        cpfs_do_arquivo = cpfs_da_leitura(leitura)
        conhecidos = pessoas_ja_conhecidas(conexao, empresa_id)
        if cpfs_do_arquivo and cpfs_do_arquivo <= set(conhecidos):
            raise ingestao.ArquivoRecusado(mensagem_de_nada_novo(cpfs_do_arquivo, conhecidos))

    # Lê, retrata e registra (reenvio idêntico devolve o envio que já existe). O cliente só é usado se o arquivo for
    # um Word em texto corrido (o Leitor de Documentos monta a tabela)
    progresso.anotar("Lendo o arquivo.")
    recebido = processamentos.receber_arquivo(conexao, conteudo, nome_do_arquivo, empresa_id, date.today(), login,
                                              cliente=cliente, conferir_antes_de_registrar=recusar_se_nada_novo)
    processamento_id = recebido.perfil.processamento_id
    # Roda o fluxo até a primeira pausa (se já tinha começado, não recomeça)
    progresso.anotar("Os agentes estão entendendo cada coluna e ligando ao layout do banco.")
    fluxo_empresa.iniciar(conexao, processamento_id, empresa_id, cliente=cliente, busca=busca)
    # A leitura para a tela
    leitura = leitura_do_envio(conexao, empresa_id, processamento_id)
    leitura["duplicado"] = recebido.duplicado
    return leitura


def aceitar_mapeamento(conexao, empresa_id: str, login: str, processamento_id: str, escolhas: dict,
                       cliente=None, busca=None) -> dict:
    """A pessoa confere as colunas e aceita: o fluxo padroniza e valida. Devolve a leitura depois.

    Recebe: escolhas — {coluna: campo} só das colunas que a pessoa mudou ou decidiu (as AMBIGUO precisam de
    escolha; IGNORAR deixa a coluna de fora). Se faltar decisão ou um campo aparecer duas vezes, o fluxo não avança e
    a leitura volta com o "erro" explicando (a pausa continua no aceite).
    """
    fluxo_empresa.responder(conexao, processamento_id, empresa_id, "aprovar_mapeamento",
                            {"acao": "aprovar", "escolhas": escolhas, "usuario": login}, cliente=cliente, busca=busca)
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def homologar(conexao, empresa_id: str, login: str, processamento_id: str, conferiu_a_lista: bool = False) -> dict:
    """O clique final, "Enviar ao banco": sem pendências, o envio vai para a avaliação do banco. Devolve a leitura.

    Os funcionários só ficam cadastrados quando o especialista aprovar (ADR-69, passo 15).

    Se o envio ainda tem pendência, o fluxo revalida primeiro; se a pendência continua, nada é cadastrado e levanta
    ValueError explicando a etapa em que o arquivo está (a tela mostra a mensagem). Também levanta ValueError se o
    envio está numa etapa em que homologar não faz sentido (ex.: aceite ainda não feito).
    conferiu_a_lista: a pessoa marcou "Conferi a lista" na tela; fica registrado na auditoria (o banco vê na trilha).
    """
    if conferiu_a_lista and processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is not None:
        auditoria.registrar(conexao, processamento_id, empresa_id, "Conferência", "LISTA_CONFERIDA",
                            {"conferida_por": login})
    fluxo_empresa.responder(conexao, processamento_id, empresa_id, "aprovar_homologacao",
                            {"acao": "homologar", "usuario": login})
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def tentar_de_novo(conexao, empresa_id: str, processamento_id: str, cliente=None, busca=None) -> dict:
    """Retoma um envio parado em "tentar de novo" (a IA foi pausada pelo teto de gasto, ou uma etapa falhou; ADR-131).

    Recebe: a empresa da sessão e o envio. Devolve: a leitura do envio depois de retomar.
    Confere, nesta ordem:
    1. o envio é da própria empresa (senão, KeyError → 404, sem dizer se ele existe em outra empresa);
    2. o envio está esperando uma nova tentativa (senão, ValueError → 400, com o motivo);
    3. o teto de gasto ainda está atingido: levanta TetoDeGastoAtingido (→ 503 com o recado) sem mexer no fluxo, e
       o envio continua guardado, esperando.
    Ex.: a empresa volta no dia seguinte e retoma: o fluxo refaz a etapa que parou (ex.: interpretar) e segue.
    """
    # 1. Só a empresa dona do envio (o isolamento entre empresas vem antes de qualquer outra resposta)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    # 2. O envio precisa estar parado esperando uma nova tentativa
    if fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"] != "aguardar_nova_tentativa":
        raise ValueError("Este envio não está esperando uma nova tentativa.")
    # 3. Com o teto ainda atingido, nada muda: a pessoa recebe o recado e o envio continua guardado
    periodo_atingido = teto_de_gasto.teto_atingido()
    if periodo_atingido is not None:
        raise teto_de_gasto.TetoDeGastoAtingido(periodo_atingido)
    # O fluxo refaz a etapa que parou e segue até a próxima pausa
    fluxo_empresa.responder(conexao, processamento_id, empresa_id, "aguardar_nova_tentativa",
                            {"acao": "tentar_de_novo"}, cliente=cliente, busca=busca)
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def _decisao_valida(tipo: str, decisao: str) -> bool:
    """Confere a decisão de formato: "DMY" ou "MDY" para datas; "zeros:N" (N de 1 a 20) para a matrícula."""
    if tipo == "DATA_AMBIGUA":
        return decisao in ("DMY", "MDY")
    if tipo == "ZEROS_A_ESQUERDA":
        encontrado = re.fullmatch(r"zeros:(\d{1,2})", decisao)
        return encontrado is not None and 1 <= int(encontrado.group(1)) <= 20
    return False


def decidir_formato(conexao, empresa_id: str, processamento_id: str, coluna: str, decisao: str,
                    cliente=None, busca=None) -> dict:
    """A empresa decide o formato de uma coluna inteira; o fluxo padroniza de novo com a decisão. Devolve a leitura.

    Recebe: coluna — a coluna com a dúvida; decisao — "DMY" (dia/mês), "MDY" (mês/dia) ou "zeros:N" (a matrícula fica
    com N dígitos). Levanta ValueError se a coluna não tem dúvida de formato ou a decisão não serve.
    """
    # Primeiro o dono: envio de outra empresa recebe "não encontrado", antes de ler qualquer dúvida dele (A-24).
    # Sem isso, a resposta mudaria conforme o envio alheio tivesse ou não aquela dúvida, e revelaria as colunas dele
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    tipo = None
    for pendente in formatos_pendentes(conexao, processamento_id):
        if pendente["coluna"] == coluna:
            tipo = pendente["tipo"]
    if tipo is None:
        raise ValueError(f"A coluna {coluna!r} não tem dúvida de formato para decidir.")
    if not _decisao_valida(tipo, decisao):
        raise ValueError("Escolha uma opção válida para o formato da coluna.")
    fluxo_empresa.responder(conexao, processamento_id, empresa_id, "aguardar_correcao",
                            {"acao": "decidir_colunas", "decisoes": {coluna: decisao}}, cliente=cliente, busca=busca)
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def _etapa_permite_conferencia(conexao, empresa_id: str, processamento_id: str) -> None:
    """Confere que o envio é da empresa e está entre a padronização e o envio ao banco. Levanta KeyError/ValueError."""
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    etapa = fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"]
    if etapa not in ETAPAS_DA_CONFERENCIA:
        raise ValueError("A lista só pode ser conferida depois de aceitar as colunas e antes de enviar ao banco.")


def _valor_para_a_tela(valor, campo_do_layout) -> str:
    """O valor como a conferência mostra: inteiro, com o CPF formatado.

    É a lista que a própria empresa enviou (ADR-97).
    Ex.: ("52998224725", cpf) → "529.982.247-25"; ("Maria", nome_mae) → "Maria"; (None, qualquer) → "".
    """
    if valor in (None, ""):
        return ""
    if campo_do_layout.campo == "cpf":
        return acompanhamento.formatar_cpf(str(valor))
    return str(valor)


def _campos_da_lista(plano, campos_do_layout: list, registros: list[dict]) -> list:
    """Os campos do layout que a lista mostra: os que têm coluna no arquivo e os que ganharam valor depois.

    Recebe: plano (o mapeamento aceito); campos_do_layout (o layout ativo, na ordem); registros (os dados atuais).
    Devolve: os CampoLayout, na ordem do layout.
    Por que olhar os valores (ADR-126): o CNPJ, a unidade, a admissão ou a renda que o arquivo não
    trouxe e a empresa informou nos cartões ("para todos" ou pessoa a pessoa) também vão para o banco; filtrando só
    pelas colunas do arquivo, a lista escondia esses valores e mostrava "Informação não encontrada".
    """
    campos_com_valor = set()
    for item in plano.itens:
        if item.campo:
            campos_com_valor.add(item.campo)
    # O campo sem coluna que tem valor em pelo menos uma pessoa (preenchido pelos cartões)
    for registro in registros:
        for campo_do_layout in campos_do_layout:
            if registro.get(campo_do_layout.campo) not in (None, ""):
                campos_com_valor.add(campo_do_layout.campo)
    campos = []
    for campo_do_layout in campos_do_layout:
        if campo_do_layout.campo in campos_com_valor:
            campos.append(campo_do_layout)
    return campos


def _quem_fica_de_fora(relatorio, registros: list[dict]) -> list[dict]:
    """As pessoas que não vão ao banco por este envio, e por quê (envio parcial, ADR-126).

    Recebe: relatorio (a última validação, ou None); registros (os dados atuais).
    Devolve: [{linha, nome, cpf, motivo}], na ordem do arquivo. Ex.: [{linha: 6, nome: "Ana Lima",
    cpf: "529.982.247-25", motivo: "Já foi enviada ao banco no arquivo aurora.xlsx e está em análise: não vai de novo."}]
    """
    if relatorio is None:
        return []
    de_fora = validador.linhas_que_ficam_de_fora(relatorio)
    pessoas = []
    for registro in registros:
        achado = de_fora.get(registro["_linha"])
        if achado is None:
            continue
        pessoas.append({"linha": registro["_linha"], "nome": registro.get("nome_completo") or "",
                        "cpf": acompanhamento.formatar_cpf(registro.get("cpf") or ""), "motivo": achado.mensagem})
    return pessoas


def lista_para_conferir(conexao, empresa_id: str, processamento_id: str, cliente=None) -> dict:
    """A lista do jeito que vai para o banco (os dados padronizados e já corrigidos), para a empresa conferir.

    Recebe: conexao; empresa_id (da sessão); processamento_id.
    Devolve: {campos: [{campo, descricao, sensivel, obrigatorio, regra, nao_confundir_com, exemplo}],
              linhas: [{linha, valores: {campo: valor}, pendencias: [...], informacoes_sem_rotulo: [...]}],
              contagem: {...}, ficam_de_fora: [...]}.
      - campos: os que têm coluna no arquivo ou valor informado nos cartões (ver _campos_da_lista);
      - linhas: só as pessoas que vão ao banco por este envio; pendencias: o que falta resolver na linha
        (ver _pendencias_por_linha); informacoes_sem_rotulo: o que a IA achou sem ter certeza do campo, só para o
        detalhe da pessoa, fora dos valores (services/informacoes_sem_rotulo.py; ADR-143, Parte 1);
      - contagem: o resumo único das pendências (ver resumo_das_pendencias), o mesmo do painel e de Acompanhar;
      - ficam_de_fora: quem não vai por este envio, e por quê (ver _quem_fica_de_fora).
    Os textos de cada campo vêm do parâmetro do layout e aparecem no "i" de ajuda da coluna. O exemplo de um campo
    sensível (nome, CPF, endereço...) não vai para a tela, como não vai para o índice do RAG. Os valores da empresa
    vêm inteiros, com o CPF formatado (ver _valor_para_a_tela).
    """
    _etapa_permite_conferencia(conexao, empresa_id, processamento_id)
    plano = mapeamentos.obter(conexao, processamento_id)[0]
    registros = correcoes.dados_atuais(conexao, processamento_id).registros
    _, campos_do_layout = parametros.layout_ativo(conexao)
    campos = _campos_da_lista(plano, campos_do_layout, registros)
    relatorio = validador.obter(conexao, processamento_id)
    ficam_de_fora = _quem_fica_de_fora(relatorio, registros)
    # As linhas de quem fica de fora, para não entrarem na lista que vai ao banco
    linhas_de_fora = set()
    for pessoa in ficam_de_fora:
        linhas_de_fora.add(pessoa["linha"])
    pendencias_por_linha = _pendencias_por_linha(conexao, empresa_id, processamento_id, cliente)
    linhas = []
    for registro in registros:
        if registro["_linha"] in linhas_de_fora:
            continue
        valores = {}
        for campo_do_layout in campos:
            valores[campo_do_layout.campo] = _valor_para_a_tela(registro.get(campo_do_layout.campo), campo_do_layout)
        linhas.append({"linha": registro["_linha"], "valores": valores,
                       "pendencias": pendencias_por_linha.get(registro["_linha"], [])})
        # O que a IA achou sem ter certeza do campo: ao lado dos valores, nunca dentro deles (ADR-143, Parte 1)
        linhas[-1]["informacoes_sem_rotulo"] = informacoes_sem_rotulo.do_registro_para_a_tela(registro)
    campos_para_a_tela = []
    for campo_do_layout in campos:
        campos_para_a_tela.append({"campo": campo_do_layout.campo, "descricao": campo_do_layout.descricao,
                                   "sensivel": campo_do_layout.sensivel, "obrigatorio": campo_do_layout.obrigatorio,
                                   "regra": campo_do_layout.regra, "nao_confundir_com": campo_do_layout.nao_confundir_com,
                                   "exemplo": campo_do_layout.exemplo})
    return {"campos": campos_para_a_tela, "linhas": linhas,
            "contagem": resumo_das_pendencias(relatorio, registros), "ficam_de_fora": ficam_de_fora}


# ===== A prévia das pessoas do envio (a 1ª aba do resultado, na tela "Cadastrar funcionários") =====

def _plano_da_previa(plano, campos_do_layout: list, cabecalhos: list[str]):
    """O mapeamento que a prévia usa: só as colunas que o agente reconheceu, com um campo do parâmetro vigente.

    Recebe: plano — o mapeamento guardado do envio (o que o agente propôs, ainda sem o aceite); campos_do_layout — os
    campos do parâmetro vigente; cabecalhos — as colunas da tabela do envio.
    Devolve: uma CÓPIA do plano (o guardado não muda), em que ficam de fora da prévia: a coluna em dúvida entre campos
    (ela espera a escolha da empresa), a coluna cujo campo o parâmetro não tem mais e a coluna que não está na tabela.
    A coluna deixada de fora e a coluna dividida (as partes dela entram) continuam como estão.
    Ex.: "Documento" → cpf continua; "Data", em dúvida entre a admissão e o nascimento, fica de fora.
    Por que a cópia: a padronização só aceita um plano sem dúvida (services/normalizador.py), e a prévia nunca escolhe
    pela empresa.
    """
    # Os nomes dos campos do parâmetro vigente, para conferir cada coluna reconhecida
    nomes_dos_campos = set()
    for campo_do_layout in campos_do_layout:
        nomes_dos_campos.add(campo_do_layout.campo)
    itens_da_previa = []
    for item in plano.itens:
        # A coluna reconhecida precisa de um campo que o parâmetro ainda tem e de estar na tabela do envio
        campo_existe = item.campo in nomes_dos_campos
        coluna_existe = item.coluna in cabecalhos
        reconhecida_sem_lugar = item.status == StatusMapeamento.PROPOSTO and not (campo_existe and coluna_existe)
        # A coluna em dúvida (e a reconhecida sem lugar) fica de fora; os candidatos ficam, para a trava da LGPD
        # (services/informacoes_sem_rotulo.py)
        if item.status == StatusMapeamento.AMBIGUO or reconhecida_sem_lugar:
            itens_da_previa.append(item.model_copy(update={"status": StatusMapeamento.NAO_MAPEADO, "campo": None}))
        else:
            itens_da_previa.append(item)
    return plano.model_copy(update={"itens": itens_da_previa})


def _registros_da_previa(conexao, processamento_id: str, plano, status_do_plano: str,
                         campos_do_layout: list) -> list[dict]:
    """Os registros que a prévia mostra, um por pessoa ({"_linha": 2, "cpf": "52998224725", ...}).

    Recebe: conexao; processamento_id; plano e status_do_plano (os do mapeamento guardado); campos_do_layout.
    Devolve: depois do aceite, os dados atuais do envio (a padronização guardada, com as correções da empresa); antes
    dele, a padronização do arquivo com as colunas que o agente reconheceu, calculada agora e sem gravar.
    """
    # Aceito e padronizado: a lista do jeito que vai para o banco
    if status_do_plano == "APROVADO" and normalizador.obter(conexao, processamento_id) is not None:
        return correcoes.dados_atuais(conexao, processamento_id).registros
    # Antes do aceite: a MESMA padronização do aceite (services/normalizador.py), só que sem gravar nada
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    plano_da_previa = _plano_da_previa(plano, campos_do_layout, leitura.cabecalhos)
    return normalizador.normalizar(leitura, plano_da_previa, campos_do_layout).registros


def previa_da_lista(conexao, empresa_id: str, processamento_id: str) -> dict:
    """As pessoas do envio com os valores como o agente leu, para a 1ª aba do resultado da tela (só leitura).

    Recebe: conexao; empresa_id (da sessão); processamento_id.
    Devolve: {pronta, linhas: [{linha, valores: {campo: valor}, informacoes_sem_rotulo: [...]}]}.
      - pronta: False enquanto o agente não terminou de ler as colunas (ex.: o envio parou antes, esperando uma nova
        tentativa); aí as linhas vêm vazias;
      - linhas: uma por pessoa do arquivo, só com os campos que têm valor (o campo sem valor não vem, e a tela mostra
        "Informação não encontrada"), no formato da conferência da lista (ver _valor_para_a_tela). Antes do aceite, a
        coluna em dúvida entre campos não entra: ela espera a escolha da empresa.
    Nada é gravado: nem o mapeamento, nem a padronização, nem a auditoria. É a leitura do arquivo que a própria empresa
    mandou, como na conferência da lista.
    Levanta KeyError se o envio não é da empresa (a rota responde 404, sem dizer se ele existe em outra empresa).
    Ex.: o arquivo com "CPF" e "Início" reconhecidos → {pronta: True, linhas: [{linha: 2, valores: {cpf:
    "529.982.247-25", data_admissao: "2026-03-05"}, informacoes_sem_rotulo: []}]}.
    """
    # Primeiro o dono: envio de outra empresa é "não encontrado", antes de ler qualquer coisa dele
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    mapeamento_guardado = mapeamentos.obter(conexao, processamento_id)
    # O agente ainda não terminou de ler as colunas: não há o que mostrar
    if mapeamento_guardado is None:
        return {"pronta": False, "linhas": []}
    plano, status_do_plano = mapeamento_guardado
    _, campos_do_layout = parametros.layout_ativo(conexao)
    registros = _registros_da_previa(conexao, processamento_id, plano, status_do_plano, campos_do_layout)
    linhas = []
    for registro in registros:
        # Só os campos com valor, no formato da conferência (o CPF com pontos)
        valores = {}
        for campo_do_layout in campos_do_layout:
            valor = _valor_para_a_tela(registro.get(campo_do_layout.campo), campo_do_layout)
            if valor:
                valores[campo_do_layout.campo] = valor
        # O que o agente achou sem ter certeza do campo vai ao lado, só para o detalhe da pessoa (ADR-143, Parte 1)
        linhas.append({"linha": registro["_linha"], "valores": valores,
                       "informacoes_sem_rotulo": informacoes_sem_rotulo.do_registro_para_a_tela(registro)})
    return {"pronta": True, "linhas": linhas}


def _nome_de_cada_linha(conexao, processamento_id: str) -> dict[int, str]:
    """O nome de cada pessoa do envio pela linha do arquivo, com as correções aplicadas. Ex.: {8: "Ana Lima"}."""
    nomes = {}
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        nomes[registro["_linha"]] = registro.get("nome_completo") or ""
    return nomes

def _pendencias_por_linha(conexao, empresa_id: str, processamento_id: str,
                          cliente=None) -> dict[int, list[dict]]:
    """O que falta resolver em cada linha, pela última validação:
    {linha: [{tipo, regra_id, campo, problema, acao, pergunta_da_ia, valor_lido, palpite, pergunta, sugestoes, grupo}]}
    (grupo: o mesmo de acompanhamento.marcar_os_grupos, ADR-120).

    tipo "corrigir": BLOQUEANTE (o envio não passa sem corrigir); tipo "confirmar": ALERTA ainda não confirmado,
    inclusive as perguntas da IA (ADR-73); tipo "explicacao": pergunta da IA sobre um campo que já tem algo para
    CORRIGIR na mesma linha (ex.: CPF vazio + "o CPF vem depois"): a tela mostra como explicação da correção e ela
    se resolve junto, quando o campo é corrigido. Pendência do arquivo inteiro (sem linha) fica de fora.
    valor_lido, palpite, pergunta e sugestoes são os mesmos de "Acompanhar cadastros" (pendências por
    conversa): a informação que gerou a dúvida, o palpite seguro, a fala do agente e as respostas rápidas. A fala é
    escrita pela IA, uma chamada por envio (cliente: o da IA; os testes passam um falso), com a frase de reserva quando
    a IA não responde a tempo.
    """
    relatorio = validador.obter(conexao, processamento_id)
    pendencias = {}
    if relatorio is None:
        return pendencias
    # O nome de cada pessoa, para a fala do agente ("O CPF de Ana veio ...")
    nomes = _nome_de_cada_linha(conexao, processamento_id)
    # A descrição de cada campo no parâmetro (o nome do campo na fala do agente)
    descricoes = acompanhamento.descricoes_dos_campos(conexao)
    # As pendências e o que a IA recebe de cada uma (para escrever as perguntas no fim)
    pares = []
    # Cada pendência com o seu achado (para achar os grupos de pessoas com o mesmo valor)
    pendencias_e_achados = []
    for achado in relatorio.achados:
        if achado.linha is None:
            continue
        if achado.severidade == validador.BLOQUEANTE:
            tipo = "corrigir"
        elif achado.severidade == validador.ALERTA and not achado.resolvido:
            tipo = "confirmar"
        else:
            continue
        pergunta_da_ia = achado.regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA)
        # O pedido do especialista do banco sobre esta pessoa (ADR-121): selo na tela e as palavras dele
        pedido_do_banco = achado.regra_id.startswith(validador.PREFIXO_DO_PEDIDO_DO_BANCO)
        # A informação que gerou a dúvida, como a empresa a reconhece (None se o arquivo veio sem ela)
        valor_lido = acompanhamento.valor_lido_para_a_tela(achado.campo, achado.valor)
        # O palpite seguro num valor fora da lista (None nas outras pendências)
        palpite = acompanhamento.palpite_do_achado(achado)
        pendencia = {
            "tipo": tipo, "regra_id": achado.regra_id, "campo": achado.campo, "problema": achado.mensagem,
            "acao": achado.acao, "pergunta_da_ia": pergunta_da_ia, "pedido_do_banco": pedido_do_banco,
            "valor_lido": valor_lido, "palpite": palpite,
            # A fala do agente no balão, por enquanto a de reserva (a da IA entra no fim, para o envio todo)
            "pergunta": acompanhamento.pergunta_do_achado(achado, valor_lido, nomes.get(achado.linha), palpite,
                                                          descricoes.get(achado.campo)),
            # As respostas rápidas da conversa
            "sugestoes": acompanhamento.sugestoes_da_pendencia(achado.regra_id, tipo, achado.linha, achado.campo,
                                                               palpite),
            # O grupo de pessoas com o mesmo valor fora da lista (ADR-120; None se ela está sozinha)
            "grupo": None,
            # O título do cartão: o que fazer, a informação e de quem (ADR-120)
            "titulo_do_cartao": acompanhamento.titulo_do_cartao(
                achado.regra_id, achado.campo, tipo, nomes.get(achado.linha) or f"Pessoa da linha {achado.linha}",
                descricoes.get(achado.campo)),
            # O problema, numa frase curta e só dele: um cartão nunca trata mais de um problema
            "problema_do_cartao": acompanhamento.problema_do_cartao(achado.regra_id, achado.mensagem),
            # A informação em destaque na ficha completa (None nos problemas da pessoa inteira)
            "campo_em_revisao": acompanhamento.campo_em_revisao(achado)}
        # O pedido do banco aparece com as palavras do especialista (a IA não reescreve o recado do banco)
        if pedido_do_banco:
            pendencia["pergunta"] = achado.mensagem
        pendencias.setdefault(achado.linha, []).append(pendencia)
        pendencias_e_achados.append((pendencia, achado))
        pares.append((pendencia, acompanhamento.pendencia_para_escrever(achado, tipo, valor_lido,
                                                                        nomes.get(achado.linha), palpite,
                                                                        descricoes.get(achado.campo))))
    # As pessoas com o mesmo valor fora da lista viram um grupo, com uma pergunta só (ADR-120): cada linha do grupo
    # mostra o cartão do grupo, e a resposta numa delas vale para todas
    pares.extend(acompanhamento.marcar_os_grupos(processamento_id, pendencias_e_achados, descricoes))
    # A fala do agente em cada pendência: escrita pela IA (uma chamada para o envio) ou a reserva
    acompanhamento.perguntas_escritas_pela_ia(conexao, processamento_id, empresa_id, pares, cliente)
    # A pergunta da IA sobre um campo que já tem algo para corrigir vira explicação dessa correção
    for pendencias_da_linha in pendencias.values():
        campos_a_corrigir = set()
        for pendencia in pendencias_da_linha:
            if pendencia["tipo"] == "corrigir" and pendencia["campo"]:
                campos_a_corrigir.add(pendencia["campo"])
        for pendencia in pendencias_da_linha:
            if pendencia["pergunta_da_ia"] and pendencia["campo"] in campos_a_corrigir:
                pendencia["tipo"] = "explicacao"
    return pendencias


def _pendencias_abertas(relatorio) -> list[dict]:
    """As pendências em aberto da validação, uma por cartão de "Acompanhar cadastros" (ADR-126).

    Recebe: relatorio (a última validação). Devolve: [{linha, campo, tipo, pergunta_da_ia}], com tipo "corrigir"
    (BLOQUEANTE) ou "confirmar" (ALERTA ainda não confirmado); linha None = o arquivo inteiro (ex.: uma informação
    obrigatória que o arquivo não trouxe).
    A pergunta da IA sobre um campo que já tem algo a corrigir na mesma linha não conta à parte: ela se resolve junto
    com a correção (a mesma junção de acompanhamento.juntar_perguntas_as_correcoes).
    """
    pendencias = []
    campos_a_corrigir = set()
    for achado in relatorio.achados:
        if achado.severidade == validador.BLOQUEANTE:
            tipo = "corrigir"
        elif achado.severidade == validador.ALERTA and not achado.resolvido:
            tipo = "confirmar"
        else:
            continue
        pergunta_da_ia = achado.regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA)
        pendencias.append({"linha": achado.linha, "campo": achado.campo, "tipo": tipo, "pergunta_da_ia": pergunta_da_ia})
        if tipo == "corrigir" and achado.campo:
            campos_a_corrigir.add((achado.linha, achado.campo))
    abertas = []
    for pendencia in pendencias:
        # A pergunta da IA que vira explicação da correção do mesmo campo
        if pendencia["pergunta_da_ia"] and (pendencia["linha"], pendencia["campo"]) in campos_a_corrigir:
            continue
        abertas.append(pendencia)
    return abertas


def resumo_das_pendencias(relatorio, registros: list[dict]) -> dict:
    """O número único das pendências do envio: o mesmo na conferência, no painel "Linhas do arquivo" e em Acompanhar.

    Recebe: relatorio (a última validação, ou None antes dela); registros (os dados atuais do envio).
    Devolve: {linhas, linhas_com_pendencia, corrigir, confirmar, perguntas_da_ia, no_arquivo, para_revisar, prontas,
    ficam_de_fora}:
      - linhas: as pessoas que vão ao banco por este envio (sem quem fica de fora, ADR-126);
      - corrigir e confirmar: as pendências de uma pessoa; no_arquivo: as do arquivo inteiro (ex.: "14 informações
        faltam no arquivo");
      - para_revisar: corrigir + confirmar + no_arquivo — o número que as três telas mostram;
      - prontas: as pessoas sem nenhuma pendência (zero enquanto falta informação no arquivo inteiro, que é de todas).
    Por que existe (ADR-126): a conferência dizia "0 com pendência" e o painel ao lado, "14 para revisar", porque a
    conferência deixava de fora as informações que faltam no arquivo inteiro.
    """
    de_fora = {}
    if relatorio is not None:
        de_fora = validador.linhas_que_ficam_de_fora(relatorio)
    pessoas = 0
    for registro in registros:
        if registro["_linha"] not in de_fora:
            pessoas = pessoas + 1
    resumo = {"linhas": pessoas, "linhas_com_pendencia": 0, "corrigir": 0, "confirmar": 0, "perguntas_da_ia": 0,
              "no_arquivo": 0, "para_revisar": 0, "prontas": pessoas, "ficam_de_fora": len(de_fora)}
    if relatorio is None:
        return resumo
    linhas_com_pendencia = set()
    for pendencia in _pendencias_abertas(relatorio):
        if pendencia["linha"] is None:
            resumo["no_arquivo"] = resumo["no_arquivo"] + 1
        else:
            resumo[pendencia["tipo"]] = resumo[pendencia["tipo"]] + 1
            linhas_com_pendencia.add(pendencia["linha"])
    resumo["linhas_com_pendencia"] = len(linhas_com_pendencia)
    # As perguntas que a IA fez e a empresa ainda não respondeu (também as que viraram explicação de uma correção)
    for achado in relatorio.achados:
        pergunta_da_ia = achado.regra_id.startswith(validador.PREFIXO_DA_PERGUNTA_DA_IA)
        if pergunta_da_ia and not achado.resolvido:
            resumo["perguntas_da_ia"] = resumo["perguntas_da_ia"] + 1
    resumo["para_revisar"] = resumo["corrigir"] + resumo["confirmar"] + resumo["no_arquivo"]
    # Informação que falta no arquivo inteiro falta para todos: ninguém está pronto ainda
    if resumo["no_arquivo"] > 0:
        resumo["prontas"] = 0
    else:
        resumo["prontas"] = pessoas - resumo["linhas_com_pendencia"]
    return resumo


def envios_prontos_para_o_banco(conexao, empresa_id: str) -> list[dict]:
    """Os envios da empresa que já podem ir para o banco: colunas aceitas e nenhuma pendência em aberto.

    Recebe: conexao; empresa_id (da sessão).
    Devolve: [{processamento_id, nome_arquivo, enviado_em, pessoas, ficam_de_fora}]; pessoas: quem vai ao banco;
    ficam_de_fora: quem não vai por este envio, e por quê (ADR-126, ver _quem_fica_de_fora).
    É a "lista pendente" da empresa: cada arquivo continua um envio por
    trás, e a tela manda de uma vez tudo o que estiver pronto. O envio em que ninguém vai ao banco (todos ficaram de
    fora) não está pronto: não há o que enviar.
    """
    quando_e_quem = acompanhamento.quando_e_quem_enviou(conexao, empresa_id)
    # O nome de cada arquivo como a tela mostra (arquivos diferentes com o mesmo nome ganham "(v1)", "(v2)")
    nomes_dos_arquivos = processamentos.nomes_na_tela(conexao, empresa_id)
    prontos = []
    for perfil in processamentos.listar(conexao, empresa_id):
        # Só entre o aceite das colunas e o envio ao banco
        etapa = fluxo_empresa.situacao(conexao, perfil.processamento_id)["etapa_atual"]
        if etapa not in ETAPAS_DA_CONFERENCIA:
            continue
        # Sem nenhuma pendência em aberto na última validação
        relatorio = validador.obter(conexao, perfil.processamento_id)
        if relatorio is None or not relatorio.pronto_para_homologar:
            continue
        # Quem vai ao banco e quem fica de fora deste envio
        registros = correcoes.dados_atuais(conexao, perfil.processamento_id).registros
        ficam_de_fora = _quem_fica_de_fora(relatorio, registros)
        pessoas = len(registros) - len(ficam_de_fora)
        if pessoas == 0:
            continue
        prontos.append({"processamento_id": perfil.processamento_id,
                        "nome_arquivo": nomes_dos_arquivos[perfil.processamento_id],
                        "enviado_em": quando_e_quem[perfil.processamento_id][0], "pessoas": pessoas,
                        "ficam_de_fora": ficam_de_fora})
    return prontos


def enviar_prontos_ao_banco(conexao, empresa_id: str, login: str, conferiu_a_lista: bool) -> dict:
    """"Enviar ao banco": manda, de uma vez, todos os envios prontos. Devolve {envios, pessoas, ficaram_de_fora}.

    Levanta ValueError se a pessoa não marcou "Conferi a lista" ou se não há nada pronto.
    Cada envio passa pelo mesmo caminho de antes (homologar): vai para a avaliação do banco, com o registro de que a
    lista foi conferida e por quem. As pessoas contadas são as que foram mesmo: o envio é validado de novo na hora
    de ir, e quem já tinha ido ao banco por outro envio fica de fora (ADR-126).
    """
    if not conferiu_a_lista:
        raise ValueError("Marque \"Conferi a lista\" antes de enviar ao banco.")
    prontos = envios_prontos_para_o_banco(conexao, empresa_id)
    if not prontos:
        raise ValueError("Não há envio pronto para o banco: resolva as pendências primeiro.")
    pessoas, ficaram_de_fora = 0, 0
    for pronto in prontos:
        homologar(conexao, empresa_id, login, pronto["processamento_id"], conferiu_a_lista=True)
        # A validação feita na hora do envio: quem foi e quem ficou de fora
        registros = correcoes.dados_atuais(conexao, pronto["processamento_id"]).registros
        de_fora = len(_quem_fica_de_fora(validador.obter(conexao, pronto["processamento_id"]), registros))
        pessoas += len(registros) - de_fora
        ficaram_de_fora += de_fora
    return {"envios": len(prontos), "pessoas": pessoas, "ficaram_de_fora": ficaram_de_fora}


def confirmar_na_conferencia(conexao, empresa_id: str, login: str, processamento_id: str, regra_id: str, linha: int,
                             justificativa: str) -> dict:
    """"Está certo assim": a empresa confirma um alerta (ou responde uma pergunta da IA) na conferência da lista.

    Recebe: a regra e a linha do alerta; justificativa (vazia vira JUSTIFICATIVA_PADRAO_DA_CONFERENCIA).
    Devolve: a lista atualizada. Levanta ValueError se a etapa não permite ou se o alerta não existe.
    A confirmação fica registrada com quem confirmou (a mesma de "Acompanhar cadastros") e o envio é validado de novo.
    """
    _etapa_permite_conferencia(conexao, empresa_id, processamento_id)
    texto = (justificativa or "").strip() or JUSTIFICATIVA_PADRAO_DA_CONFERENCIA
    acompanhamento.confirmar_pendencia(conexao, empresa_id, login, processamento_id, regra_id, linha, texto[:300])
    return lista_para_conferir(conexao, empresa_id, processamento_id)


def corrigir_na_conferencia(conexao, empresa_id: str, login: str, processamento_id: str, linha: int, campo: str,
                            valor: str) -> dict:
    """A empresa corrige um valor na conferência da lista: o pedido é registrado, aplicado e o envio é revalidado.

    Recebe: linha e campo do valor; valor — o valor certo (vazio apaga). Devolve: a lista atualizada.
    Levanta ValueError se o valor não serve para o campo (a mensagem diz por quê) ou a etapa não permite.
    """
    _etapa_permite_conferencia(conexao, empresa_id, processamento_id)
    try:
        correcao = correcoes.propor(conexao, processamento_id, empresa_id, linha, campo, valor, MOTIVO_DA_CONFERENCIA,
                                    login)
    except normalizador.NaoConvertido as erro:
        raise ValueError(f"O valor não serve para este campo: {erro}.") from erro
    correcoes.decidir(conexao, processamento_id, empresa_id, correcao.correcao_id, True, login)
    return lista_para_conferir(conexao, empresa_id, processamento_id)


def _dicas_dos_pedidos(pedidos: list[dict]) -> dict[str, str]:
    """{coluna: dica} dos pedidos da tela ([{coluna, dica}]), conferindo cada um.

    Levanta ValueError: nenhum pedido, mais de MAXIMO_DE_COLUNAS_POR_RELEITURA, coluna repetida ou dica vazia.
    """
    if not pedidos:
        raise ValueError("Escolha pelo menos uma coluna e conte ao Agente Interpretador o que ela contém.")
    if len(pedidos) > MAXIMO_DE_COLUNAS_POR_RELEITURA:
        raise ValueError(f"Explique no máximo {MAXIMO_DE_COLUNAS_POR_RELEITURA} colunas por releitura.")
    dicas_por_coluna = {}
    for pedido in pedidos:
        coluna = pedido.get("coluna") or ""
        dica = (pedido.get("dica") or "").strip()
        if coluna in dicas_por_coluna:
            raise ValueError(f"A coluna \"{coluna}\" apareceu duas vezes: junte as explicações numa só.")
        if not dica:
            raise ValueError(f"Conte ao Agente Interpretador o que a coluna \"{coluna}\" contém.")
        dicas_por_coluna[coluna] = dica[:300]
    return dicas_por_coluna


def reler_colunas(conexao, empresa_id: str, processamento_id: str, pedidos: list[dict], cliente=None,
                  busca=None) -> dict:
    """"Ajude a IA a acertar": a IA relê as colunas indicadas, cada uma com a dica da empresa, e o mapeamento volta
    ao aceite. Várias colunas de uma vez contam como UMA releitura.

    Recebe: pedidos — [{coluna, dica}]: a coluna que a IA deixou de fora ou leu errado e o que a empresa sabe dela
    (cada dica passa pelo guardrail de injeção). Devolve: a leitura, parada no aceite, com as colunas relidas.
    Levanta ValueError (dica vazia, com ordem para a IA, limite de releituras) ou KeyError (envio de outra empresa).
    Ex.: [{"coluna": "Obs", "dica": "é o e-mail pessoal"}, {"coluna": "Registro", "dica": "é o CPF"}].
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    dicas_por_coluna = _dicas_dos_pedidos(pedidos)
    situacao = fluxo_empresa.situacao(conexao, processamento_id)
    etapa = situacao["etapa_atual"]
    if etapa not in ("aprovar_mapeamento",) + ETAPAS_DA_CONFERENCIA:
        raise ValueError("O Agente Interpretador só relê colunas antes de o envio ir para o banco.")
    configuracao = situacao["estado"].get("configuracao") or "B3"
    mapeamentos.reinterpretar_colunas(conexao, processamento_id, empresa_id, dicas_por_coluna, "Ajude a IA a acertar",
                                      cliente=cliente, configuracao=configuracao, busca=busca)
    # Depois do aceite, o fluxo volta sozinho ao aceite (o mapeamento ficou PENDENTE)
    if etapa in ETAPAS_DA_CONFERENCIA:
        fluxo_empresa.retomar(conexao, processamento_id, empresa_id, {"acao": "revalidar"}, cliente=cliente, busca=busca)
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def conferir_coluna(conexao, empresa_id: str, processamento_id: str, coluna: str, campo: str) -> dict:
    """Na hora em que a empresa troca o campo de uma coluna, confere se os valores dela servem para o campo novo.

    A escolha da empresa vale (ela conhece o próprio arquivo), mas a tela avisa quando o tipo não bate (ex.: a coluna
    do CPF posta na data de admissão). Nada é gravado: se ela aceitar assim, os valores que não servem ficam vazios e
    viram pendência para revisar em "Acompanhar cadastros".
    Recebe: coluna — a do arquivo; campo — o escolhido. Devolve: {coluna, campo, preenchidos, nao_servem, exemplos,
    mensagem}; "mensagem" vazia quando tudo serve. Levanta KeyError (envio de outra empresa) ou ValueError.
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    campos_por_nome = _campos_por_nome(conexao)
    if campo not in campos_por_nome:
        raise ValueError(f"O campo {campo!r} não existe no layout.")
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    if coluna not in leitura.cabecalhos:
        raise ValueError(f"A coluna {coluna!r} não existe no arquivo.")
    posicao = leitura.cabecalhos.index(coluna)
    valores = []
    for linha in leitura.linhas:
        valores.append(linha[posicao])
    conferencia = normalizador.conferir_valores_para_o_campo(valores, campos_por_nome[campo])
    # Os exemplos saem com a máscara da tela (um CPF nunca aparece inteiro)
    exemplos = []
    for exemplo in conferencia["exemplos"]:
        exemplos.append({"valor": _exemplo_para_a_tela(exemplo["valor"]),
                         "motivo": exemplo["motivo"]})
    mensagem = ""
    if conferencia["nao_servem"]:
        primeiro = exemplos[0]
        mensagem = (f"{conferencia['nao_servem']} de {conferencia['preenchidos']} valor(es) desta coluna não servem "
                    f"para {campo} (ex.: \"{primeiro['valor']}\": {primeiro['motivo']}). Se aceitar assim, eles ficam "
                    "em branco e viram pendência para você revisar em \"Acompanhar cadastros\".")
    return {"coluna": coluna, "campo": campo, "preenchidos": conferencia["preenchidos"],
            "nao_servem": conferencia["nao_servem"], "exemplos": exemplos, "mensagem": mensagem}


# Quantos exemplos a prévia da divisão mostra
EXEMPLOS_DA_PREVIA = 3


def _valores_da_coluna(leitura, coluna: str) -> list[str]:
    """Os valores da coluna, um por linha (levanta ValueError se a coluna não existe)."""
    if coluna not in leitura.cabecalhos:
        raise ValueError(f"A coluna {coluna!r} não existe no arquivo.")
    posicao = leitura.cabecalhos.index(coluna)
    valores = []
    for linha in leitura.linhas:
        valores.append(linha[posicao])
    return valores


def _parte_para_a_tela(valor: str) -> str:
    """Uma parte dividida, como a prévia mostra: inteira (ver _exemplo_para_a_tela). Parte vazia vira texto vazio."""
    if not valor:
        return ""
    return _exemplo_para_a_tela(valor)


def previa_da_divisao(conexao, empresa_id: str, processamento_id: str, coluna: str, destino: str) -> dict:
    """Como a coluna ficaria dividida, sem gravar nada: os primeiros exemplos e quantas linhas a regra não conseguiu
    dividir por inteiro.

    Recebe: coluna — a do arquivo; destino — o nome escolhido (ex.: "Endereço residencial").
    Devolve: {coluna, destino, partes: [{parte, nome, campo}], exemplos: [{partes: {parte: valor}, sobrou}],
    linhas_com_sobra, destinos}. Os valores saem inteiros (são os dados da própria empresa).
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    campos_por_nome = _campos_por_nome(conexao)
    escolhido = divisao.destino_pelo_nome(list(campos_por_nome.values()), destino)
    valores = _valores_da_coluna(processamentos.carregar_tabela(conexao, processamento_id), coluna)
    exemplos = []
    linhas_com_sobra = 0
    for valor in valores:
        if not valor.strip():
            continue
        dividido = divisao.dividir(valor, escolhido)
        if dividido.sobrou:
            linhas_com_sobra += 1
        if len(exemplos) < EXEMPLOS_DA_PREVIA:
            partes = {}
            for parte, campo in escolhido["partes"].items():
                partes[parte] = _parte_para_a_tela(dividido.partes.get(parte, ""))
            sobrou = []
            for pedaco in dividido.sobrou:
                sobrou.append(pedaco)
            exemplos.append({"partes": partes, "sobrou": sobrou})
    partes_do_destino = []
    for parte, campo in escolhido["partes"].items():
        partes_do_destino.append({"parte": parte, "nome": divisao.NOMES_DAS_PARTES[parte], "campo": campo})
    return {"coluna": coluna, "destino": destino, "partes": partes_do_destino, "exemplos": exemplos,
            "linhas_com_sobra": linhas_com_sobra}


def destinos_da_divisao(conexao) -> list[str]:
    """Os nomes dos destinos de divisão que o layout vigente permite (ex.: "Endereço residencial")."""
    nomes = []
    for destino in divisao.destinos_disponiveis(list(_campos_por_nome(conexao).values())):
        nomes.append(destino["nome"])
    return nomes


def dividir_coluna(conexao, empresa_id: str, login: str, processamento_id: str, coluna: str, destino: str) -> dict:
    """Divide uma coluna em várias (ex.: o endereço inteiro em rua, número, bairro, cidade, UF e CEP), antes do aceite.

    Cada parte vira uma coluna nova ("Endereço · rua"), já ligada ao seu campo e marcada "Ajustado por você"; a coluna
    original fica de fora (a informação continua nas partes). Parte cujo campo já vem de outra coluna do arquivo fica
    de fora, com o motivo. A tabela nova é gravada ao lado do original, que continua intacto.
    Recebe: coluna; destino — o nome escolhido. Devolve: a leitura do envio. Levanta ValueError (etapa, coluna já
    dividida, destino que não existe) ou KeyError (envio de outra empresa).
    """
    _conferir_que_da_para_dividir(conexao, empresa_id, processamento_id)
    campos_por_nome = _campos_por_nome(conexao)
    escolhido = divisao.destino_pelo_nome(list(campos_por_nome.values()), destino)
    # O destino escolhido vira uma proposta de divisão, como a que a IA faz (o mesmo serviço aplica as duas)
    partes = []
    for parte, campo in escolhido["partes"].items():
        partes.append(ParteDaDivisao(parte=parte, campo=campo))
    ferramenta = "endereco" if "logradouro" in escolhido["partes"] else "cidade_uf"
    proposta = DivisaoProposta(ferramenta=ferramenta, partes=partes)
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    plano = mapeamentos.obter(conexao, processamento_id)[0]
    try:
        itens = divisao_da_coluna.aplicar(leitura, plano.itens, coluna, proposta, "humano")
    except ValueError as erro:
        raise ValueError(f"{erro} (destino: {destino})") from erro
    processamentos.guardar_tabela_do_envio(conexao, processamento_id, leitura)
    mapeamentos.regravar_plano_pendente(conexao, processamento_id, plano.model_copy(update={"itens": itens}))
    auditoria.registrar(conexao, processamento_id, empresa_id, "Aceite do mapeamento", "COLUNA_DIVIDIDA",
                        {"coluna": coluna, "destino": destino, "por": login})
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def _conferir_que_da_para_dividir(conexao, empresa_id: str, processamento_id: str) -> None:
    """A divisão só vale no envio da própria empresa e antes do aceite das colunas.

    Levanta KeyError (envio de outra empresa) ou ValueError (as colunas já foram aceitas).
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    if fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"] != "aprovar_mapeamento":
        raise ValueError("Dá para dividir uma coluna só antes de aceitar as colunas.")


def refazer_divisao(conexao, empresa_id: str, login: str, processamento_id: str, coluna: str, comentario: str,
                    cliente=None, busca=None) -> dict:
    """A empresa comentou a divisão que a IA fez numa coluna: a IA refaz SÓ essa coluna, com o comentário (ADR-104).

    Recebe: a coluna dividida; o comentário da empresa (ex.: "é o endereço do trabalho, não o de casa").
    Devolve: a leitura do envio. As partes antigas saem, a IA relê a coluna com o comentário e a divisão anterior, e a
    nova proposta é aplicada (ou a coluna fica como a IA decidir, se ela disser que não é para dividir).
    Levanta ValueError (sem comentário, comentário com cara de ordem para a IA, coluna não dividida, limite de
    tentativas) ou KeyError (envio de outra empresa).
    """
    from agents import interpretador
    from services import guardrail_injecao
    _conferir_que_da_para_dividir(conexao, empresa_id, processamento_id)
    comentario = (comentario or "").strip()
    if not comentario:
        raise ValueError("Conte o que está errado na divisão para o Agente Interpretador refazer.")
    if guardrail_injecao.verificar_mensagem(comentario):
        raise ValueError("O comentário tem uma frase com cara de instrução para o Agente Interpretador; descreva "
                         "só a coluna.")
    plano = mapeamentos.obter(conexao, processamento_id)[0]
    item_dividido = None
    for item in plano.itens:
        if item.coluna == coluna and item.divisao is not None:
            item_dividido = item
    if item_dividido is None:
        raise ValueError(f"A coluna \"{coluna}\" não está dividida.")
    if item_dividido.divisao.refeita >= divisao_da_coluna.LIMITE_DE_REFAZER:
        raise ValueError("O Agente Interpretador já refez esta divisão " + str(divisao_da_coluna.LIMITE_DE_REFAZER) +
                         " vezes. Ajuste o campo de cada parte na tabela ou deixe a coluna de fora.")
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    versao, campos = parametros.layout_ativo(conexao)
    # A IA relê só esta coluna, com o comentário e a divisão anterior (como DADO: passa pelo bloco da empresa)
    dica = ("Comentário sobre a divisão desta coluna: " + comentario + ". Divisão anterior: " +
            divisao_da_coluna.descrever(item_dividido.divisao) + ".")
    relida = interpretador.interpretar(perfil, campos, versao, cliente or interpretador.cliente_padrao(), busca=busca,
                                       colunas=[mapeamentos.coluna_do_perfil(perfil, coluna)], dica=dica)
    item_novo = relida.itens[0]
    # A tentativa conta mesmo se a IA mudar de ideia sobre dividir
    tentativas = item_dividido.divisao.refeita + 1
    if item_novo.divisao is not None:
        item_novo = item_novo.model_copy(update={"divisao": item_novo.divisao.model_copy(update={"refeita": tentativas})})
    # As partes antigas saem e o item da coluna é trocado pelo da releitura
    leitura = processamentos.carregar_tabela(conexao, processamento_id)
    itens = divisao_da_coluna.desfazer(leitura, plano.itens, coluna)
    processamentos.guardar_tabela_do_envio(conexao, processamento_id, leitura)
    itens = mapeamentos.trocar_item(itens, item_novo)
    itens = mapeamentos.aplicar_divisoes_da_ia(conexao, processamento_id, itens)
    mapeamentos.regravar_plano_pendente(conexao, processamento_id, plano.model_copy(update={"itens": itens}))
    # O que a IA decidiu desta vez: a divisão nova, ou a situação da coluna (se ela disse que não é para dividir)
    depois = item_novo.status.value
    if item_novo.divisao is not None:
        depois = divisao_da_coluna.descrever(item_novo.divisao)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Aceite do mapeamento", "DIVISAO_REFEITA",
                        {"coluna": coluna, "por": login, "tentativa": tentativas,
                         "antes": divisao_da_coluna.descrever(item_dividido.divisao), "depois": depois})
    return leitura_do_envio(conexao, empresa_id, processamento_id)


def o_que_se_perde(conexao, empresa_id: str, processamento_id: str) -> dict:
    """O que se perde ao descartar o envio, para a confirmação da tela: {funcionarios, correcoes}.

    Recebe: conexao; empresa_id (da sessão); o envio. Levanta KeyError se o envio não é da empresa.
    funcionarios: as linhas lidas do arquivo; correcoes: as correções já feitas pela empresa neste envio.
    Nada foi enviado ao banco antes do "Enviar ao banco": descartar só perde este trabalho.
    """
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise KeyError(processamento_id)
    return {"funcionarios": perfil.n_linhas,
            "correcoes": len(correcoes.listar(conexao, processamento_id, "APLICADA"))}


def descartar(conexao, empresa_id: str, processamento_id: str, login: str) -> dict:
    """"Descartar esta leitura" (arquivo errado): o envio é encerrado sem cadastrar ninguém. Devolve a leitura.

    Recebe: conexao; empresa_id (da sessão); o envio; login de quem descartou.
    Levanta ValueError se o fluxo não está esperando uma decisão (ex.: já homologado: não dá para descartar).
    A trilha ganha o evento DESCARTADO_PELA_EMPRESA: quem descartou e o que se perdeu (quantidades, sem dados).
    """
    perdido = o_que_se_perde(conexao, empresa_id, processamento_id)
    # O fluxo aceita "rejeitar" em qualquer pausa; retomar confere o dono e se há pausa à espera
    fluxo_empresa.retomar(conexao, processamento_id, empresa_id, {"acao": "rejeitar"})
    auditoria.registrar(conexao, processamento_id, empresa_id, "Fluxo", "DESCARTADO_PELA_EMPRESA",
                        {"por": login, "funcionarios": perdido["funcionarios"], "correcoes": perdido["correcoes"]})
    return leitura_do_envio(conexao, empresa_id, processamento_id)
