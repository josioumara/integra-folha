"""A avaliação dos envios pelo especialista do banco: aprovar, devolver com motivo ou aprovar os outros e devolver
só as pessoas apontadas (ADR-69, passo 15; ADR-121).

Para que serve: quando a empresa clica em "Enviar ao banco", o envio para na pausa "avaliar_no_banco" do fluxo
(workflows/fluxo_empresa.py). A aba Envios do Portal do Banco mostra aqui:
    - a fila: os envios esperando avaliação e os já avaliados (aprovados ou devolvidos), de toda a carteira;
    - a trilha de cada envio: como ele chegou até o banco (o que a IA leu, o que a empresa corrigiu e confirmou);
    - os alertas que a empresa confirmou (ex.: salário fora do padrão do cargo), para o banco conferir;
    - as pessoas do envio, com o CPF inteiro: o especialista tem autorização contratual da empresa e precisa dele
      para ligar o funcionário ao banco; abrir a lista fica registrado.
A decisão é do banco (a IA nunca aprova): aprovado, os funcionários ficam cadastrados e o planejamento é liberado;
devolvido, o envio volta para a empresa com o motivo. Cada decisão fica na auditoria (quem, quando e o motivo).

Apontar problema numa pessoa (ADR-121): o especialista marca qualquer pessoa do envio
com um motivo e um recado (services/apontamentos_do_banco.py). Com pessoas apontadas, a decisão vira:
    - "Aprovar os outros e devolver os marcados": as outras são cadastradas na hora e as apontadas voltam à empresa
      num envio de devolução (services/devolucao_por_pessoa.py), cada uma com a pendência "Pedido do banco";
    - "Devolver o envio inteiro": o envio todo volta, e os apontamentos viram pendências dele.
"""
import csv
import io
from datetime import datetime, timezone

from models.contratos import EstadoProcessamento
from services import (acompanhamento, apontamentos_do_banco, auditoria, correcoes, dados_mock, devolucao_por_pessoa,
                      homologacao, idas_e_voltas, mapeamentos, processamentos, validador)
# O que a IA achou sem ter certeza do campo vai para o detalhe de cada pessoa do envio (ADR-143, Parte 1)
from services import informacoes_sem_rotulo
from services.permissoes import autorizar
from workflows import fluxo_empresa

# O prazo combinado para o banco avaliar um envio, em horas (1 dia útil, simplificado em 24 horas)
PRAZO_EM_HORAS = 24
# As três decisões do especialista sobre um envio que espera o banco (ADR-121)
DECISAO_APROVAR = "aprovar"
DECISAO_APROVAR_E_DEVOLVER = "aprovar_e_devolver_marcados"
DECISAO_DEVOLVER = "devolver"
DECISOES = (DECISAO_APROVAR, DECISAO_APROVAR_E_DEVOLVER, DECISAO_DEVOLVER)
# Como cada alerta confirmado pela empresa aparece para o banco
CONFIRMACAO_DA_EMPRESA = {
    "CONFIRMADO": "A empresa confirmou que o valor está certo.",
    "SUSPEITO": "A empresa marcou o valor como suspeito, mas manteve.",
}


def _datas_dos_eventos(conexao, processamento_id: str) -> dict:
    """A última vez que cada tipo de evento aconteceu no envio, com o detalhe.

    Recebe: conexao; processamento_id. Devolve: {tipo: {"quando": ..., "detalhe": {...}}}.
    """
    ultimos = {}
    for evento in auditoria.eventos(conexao, processamento_id):
        ultimos[evento["tipo"]] = {"quando": evento["criado_em"], "detalhe": evento["detalhe"]}
    return ultimos


def _prazo(enviado_em: str) -> dict:
    """O selo do prazo: dentro das 24 horas ou atrasado.

    Recebe: enviado_em — a data e hora do envio ao banco. Devolve: {texto, classe}.
    """
    horas_passadas = (datetime.now(timezone.utc) - datetime.fromisoformat(enviado_em)).total_seconds() / 3600
    if horas_passadas > PRAZO_EM_HORAS:
        return {"texto": "Passou do prazo de 1 dia útil", "classe": "selo-atencao"}
    return {"texto": "Dentro do prazo de 1 dia útil", "classe": "selo-marca"}


def _quantas_retiradas_confirmadas(conexao, processamento_id: str) -> int:
    """Quantas vezes a empresa confirmou, na conversa com o agente, tirar uma pessoa do envio ou deixar um dado em
    branco (o evento RETIRADA_CONFIRMADA_PELA_EMPRESA da trilha de auditoria)."""
    quantas = 0
    for evento in auditoria.eventos(conexao, processamento_id):
        if evento["tipo"] == "RETIRADA_CONFIRMADA_PELA_EMPRESA":
            quantas = quantas + 1
    return quantas


def _trilha(conexao, perfil, eventos: dict, relatorio) -> list[str]:
    """Como o envio chegou até o banco, em frases simples (sem nenhum dado de pessoa).

    Recebe: conexao; perfil (o envio); eventos (_datas_dos_eventos); relatorio (a última validação).
    Devolve: a lista de frases, na ordem.
    """
    frases = []
    enviado_por = eventos.get("ENVIADO_AO_BANCO", {}).get("detalhe", {}).get("enviado_por", "a empresa")
    tipo = acompanhamento.TIPO_PARA_A_EMPRESA[perfil.tipo_carga]
    frases.append(tipo + " com " + str(perfil.n_linhas) + " linhas, enviada por " + enviado_por + ".")
    # O que a IA leu (o mapeamento aceito pela empresa)
    mapeamento = mapeamentos.obter(conexao, perfil.processamento_id)
    if mapeamento is not None:
        campos_reconhecidos = 0
        for item in mapeamento[0].itens:
            if item.campo:
                campos_reconhecidos = campos_reconhecidos + 1
        frases.append("Os agentes leram as colunas e a empresa conferiu: " + str(campos_reconhecidos) +
                      " campos do layout preenchidos.")
    # O que a empresa corrigiu e confirmou antes de enviar
    corrigidos = len(correcoes.listar(conexao, perfil.processamento_id, "APLICADA"))
    confirmados = 0
    repetidos = 0
    # Quem ficou de fora por já estar com o banco noutro envio (ADR-126)
    outros_de_fora = 0
    for achado in relatorio.achados:
        if achado.severidade == validador.ALERTA and achado.resolvido:
            confirmados = confirmados + 1
        if achado.regra_id == validador.JA_HOMOLOGADO_NA_EMPRESA:
            repetidos = repetidos + 1
        elif achado.regra_id in validador.REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA:
            outros_de_fora = outros_de_fora + 1
    frases.append("A empresa corrigiu " + str(corrigidos) + " valor(es) e confirmou " + str(confirmados) + " alerta(s) antes de enviar.")
    # O que a empresa tirou do envio na conversa com o agente, confirmando
    retiradas = _quantas_retiradas_confirmadas(conexao, perfil.processamento_id)
    if retiradas:
        frases.append("A empresa confirmou " + str(retiradas) + " retirada(s) na conversa com o agente (pessoa fora "
                      "do envio ou dado em branco).")
    # A pessoa marcou "Conferi a lista" antes de enviar (a validação humana final da empresa)
    if "LISTA_CONFERIDA" in eventos:
        conferida_por = eventos["LISTA_CONFERIDA"]["detalhe"].get("conferida_por", "a empresa")
        frases.append(conferida_por + " marcou \"Conferi a lista\" antes de enviar.")
    if repetidos:
        frases.append(str(repetidos) + " pessoa(s) já cadastrada(s) na empresa ficam de fora (não são cadastradas de novo).")
    if outros_de_fora:
        frases.append(str(outros_de_fora) + " pessoa(s) já enviada(s) ao banco noutro envio, ainda em análise, "
                      "ficam de fora (não entram duas vezes).")
    return frases


def _alertas_confirmados(conexao, processamento_id: str, relatorio) -> list[dict]:
    """Os alertas que a empresa confirmou, para o banco conferir (nome da pessoa, o problema e a confirmação).

    Recebe: conexao; processamento_id; relatorio. Devolve: [{linha, nome, texto, confirmacao}].
    """
    nomes = acompanhamento.nome_de_cada_registro(conexao, processamento_id)
    alertas = []
    for achado in relatorio.achados:
        if achado.severidade != validador.ALERTA or not achado.resolvido:
            continue
        # A resposta a um pedido do banco aparece em "Respostas aos seus apontamentos" (ADR-121), não aqui
        if achado.regra_id.startswith(validador.PREFIXO_DO_PEDIDO_DO_BANCO):
            continue
        nome = "Arquivo inteiro"
        if achado.registro is not None:
            nome = nomes.get(achado.registro) or ("Funcionário da linha " + str(achado.linha))
        alertas.append({"linha": achado.linha, "nome": nome, "texto": achado.mensagem,
                        "confirmacao": CONFIRMACAO_DA_EMPRESA.get(achado.resolvido, achado.resolvido)})
    return alertas


def _envio_na_fila(conexao, perfil) -> dict:
    """Um envio no formato da fila do banco: empresa, tipo, situação, prazo ou resultado, trilha e alertas.

    Recebe: conexao; perfil (um envio aguardando, devolvido ou homologado depois de passar pelo banco).
    Devolve: o dicionário do envio (sem nenhum CPF).
    """
    eventos = _datas_dos_eventos(conexao, perfil.processamento_id)
    relatorio = validador.obter(conexao, perfil.processamento_id) or validador.RelatorioValidacao()
    enviado_em = eventos.get("ENVIADO_AO_BANCO", {}).get("quando")
    envio = {
        "id": perfil.processamento_id,
        "empresa_id": perfil.empresa_id,
        "empresa": dados_mock.nome_da_empresa(perfil.empresa_id),
        "tipo": acompanhamento.TIPO_PARA_A_EMPRESA[perfil.tipo_carga],
        "linhas": perfil.n_linhas,
        "enviado_em": enviado_em,
        "trilha": _trilha(conexao, perfil, eventos, relatorio),
        "alertas": _alertas_confirmados(conexao, perfil.processamento_id, relatorio),
        # ADR-121: de onde veio (no envio de devolução), a história com o banco, o que a empresa respondeu aos
        # apontamentos e quantas pessoas estão apontadas agora (sem decisão ainda)
        "origem": idas_e_voltas.texto_da_origem(conexao, perfil),
        "idas_e_voltas": idas_e_voltas.idas_e_voltas(conexao, perfil.processamento_id),
        "respostas_aos_apontamentos": idas_e_voltas.respostas_aos_apontamentos(conexao, perfil.processamento_id),
        "apontamentos": len(apontamentos_do_banco.rascunhos(conexao, perfil.processamento_id)),
    }
    if perfil.status == EstadoProcessamento.AGUARDANDO_BANCO:
        envio["situacao"] = "aguardando"
        envio["prazo"] = _prazo(enviado_em)
        envio["resultado"] = None
    elif perfil.status == EstadoProcessamento.DEVOLVIDO:
        devolucao = eventos["DEVOLVIDO_PELO_BANCO"]
        envio["situacao"] = "devolvido"
        envio["prazo"] = {"texto": "Devolvido", "classe": "selo-atencao"}
        envio["resultado"] = ("Devolvido por " + devolucao["detalhe"].get("avaliado_por", "banco") + ": \"" +
                              devolucao["detalhe"].get("motivo", "") + "\"")
    else:
        aprovacao = eventos["APROVADO_PELO_BANCO"]
        cadastrados = homologacao.obter(conexao, perfil.processamento_id)["relatorio"]["registros_homologados"]
        envio["situacao"] = "aprovado"
        envio["prazo"] = {"texto": "Aprovado", "classe": "selo-sucesso"}
        envio["resultado"] = ("Aprovado por " + aprovacao["detalhe"].get("avaliado_por", "banco") + ". " +
                              str(cadastrados) + " funcionário(s) cadastrado(s).")
        # Aprovado em parte: as pessoas apontadas voltaram à empresa num envio de devolução (ADR-121)
        devolvidas = aprovacao["detalhe"].get("devolvidas", 0)
        if devolvidas:
            envio["resultado"] = (envio["resultado"] + " " + idas_e_voltas.texto_de_pessoas(devolvidas) +
                                  " devolvida(s) à empresa para ajuste.")
    return envio


def _passou_pelo_banco(conexao, perfil) -> bool:
    """Diz se o envio está (ou esteve) na avaliação do banco: aguardando, devolvido ou aprovado pelo banco."""
    if perfil.status in (EstadoProcessamento.AGUARDANDO_BANCO, EstadoProcessamento.DEVOLVIDO):
        return True
    if perfil.status != EstadoProcessamento.HOMOLOGADO:
        return False
    # Homologado antes da avaliação do banco existir não entra na fila (não há decisão do banco para mostrar)
    return "APROVADO_PELO_BANCO" in _datas_dos_eventos(conexao, perfil.processamento_id)


def fila_de_envios(conexao, usuario) -> list[dict]:
    """A fila da aba Envios: os envios que esperam o banco e os já avaliados, de toda a carteira.

    Recebe: conexao; usuario (da sessão; só o BANCO). Devolve: a lista, os que esperam primeiro (do mais antigo ao
    mais novo: quem espera há mais tempo vem antes) e depois os avaliados.
    """
    autorizar(usuario, "avaliar_envios")
    return fila_sem_conferir_perfil(conexao)


def fila_sem_conferir_perfil(conexao) -> list[dict]:
    """A mesma fila, para quem já conferiu o perfil antes (ex.: o Início do banco, que só o BANCO abre).

    Recebe: conexao. Devolve: a fila (os que esperam primeiro, do mais antigo ao mais novo; depois os avaliados).
    """
    aguardando = []
    avaliados = []
    for empresa in dados_mock.empresas():
        for perfil in processamentos.listar(conexao, empresa["empresa_id"]):
            if not _passou_pelo_banco(conexao, perfil):
                continue
            envio = _envio_na_fila(conexao, perfil)
            if envio["situacao"] == "aguardando":
                aguardando.append(envio)
            else:
                avaliados.append(envio)
    aguardando.sort(key=_data_de_envio)
    return aguardando + avaliados


def _data_de_envio(envio: dict) -> str:
    """A data do envio ao banco, para ordenar a fila (texto AAAA-MM-DD... ordena igual à data)."""
    return envio["enviado_em"] or ""


def pessoas_do_envio(conexao, usuario, processamento_id: str) -> list[dict]:
    """As pessoas de um envio que está (ou esteve) na avaliação do banco, com o CPF inteiro e formatado.

    Recebe: conexao; usuario (só o BANCO); processamento_id. Devolve: [{linha, nome, cpf, cargo, admissao, salario,
    alerta, campos, apontamento, informacoes_sem_rotulo}] — "campos" traz todos os campos do parâmetro vigente, para a
    grade (ADR-111); "informacoes_sem_rotulo", o que a IA achou sem ter certeza do campo, só para o detalhe da pessoa e
    fora de "campos" (ADR-143, Parte 1).
    Quem já estava cadastrado na empresa fica de fora (não é cadastrado de novo). A abertura da lista fica
    registrada nos acessos a dados pessoais da empresa (quem, quando e quantas pessoas; nunca o CPF).
    Levanta KeyError se o envio não existe ou não passou pelo banco.
    """
    autorizar(usuario, "avaliar_envios")
    perfil = processamentos.obter(conexao, processamento_id)
    if perfil is None or not _passou_pelo_banco(conexao, perfil):
        raise KeyError(processamento_id)
    relatorio = validador.obter(conexao, processamento_id) or validador.RelatorioValidacao()
    linhas_repetidas = set()
    linhas_com_alerta = set()
    for achado in relatorio.achados:
        # Quem fica de fora do envio (já cadastrado ou já com o banco noutro envio; ADR-126)
        if achado.regra_id in validador.REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA:
            linhas_repetidas.add(achado.linha)
        elif achado.severidade == validador.ALERTA:
            linhas_com_alerta.add(achado.linha)
    # Todos os campos do parâmetro vigente (a grade do especialista mostra um por coluna, ADR-111)
    nomes_dos_campos = acompanhamento.campos_para_a_empresa(conexao)
    # As pessoas que o especialista já apontou nesta avaliação (ADR-121)
    apontadas = apontamentos_do_banco.rascunhos(conexao, processamento_id)
    pessoas = []
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] in linhas_repetidas:
            continue
        # Os campos do parâmetro em texto (campo que não veio fica vazio: a tela mostra "Informação não encontrada")
        campos = {}
        for campo in nomes_dos_campos:
            valor = registro.get(campo)
            campos[campo] = ""
            if valor is not None:
                campos[campo] = str(valor)
        # O CPF sai formatado, como na coluna de sempre
        campos["cpf"] = acompanhamento.formatar_cpf(campos.get("cpf", ""))
        pessoas.append({
            "linha": registro["_linha"],
            "nome": registro.get("nome_completo") or "",
            "cpf": acompanhamento.formatar_cpf(registro.get("cpf") or ""),
            "cargo": registro.get("cargo") or "",
            "admissao": registro.get("data_admissao") or "",
            "salario": registro.get("valor_renda") or "",
            "alerta": registro["_linha"] in linhas_com_alerta,
            "campos": campos,
            # O problema apontado pelo especialista (ainda sem decisão), ou None
            "apontamento": _apontamento_para_a_tela(apontadas.get(registro["_linha"])),
        })
        # O que a IA achou sem ter certeza do campo: ao lado de "campos", nunca dentro dele (ADR-143, Parte 1)
        pessoas[-1]["informacoes_sem_rotulo"] = informacoes_sem_rotulo.do_registro_para_a_tela(registro)
    # Quem do banco viu os dados das pessoas desta empresa, e quantas (a prestação de contas da LGPD)
    acompanhamento.registrar_acesso(conexao, perfil.empresa_id, usuario.login, acompanhamento.ACESSO_LISTA,
                                    len(pessoas))
    return pessoas


# As colunas do arquivo do envio que vêm depois dos campos do parâmetro (o que a grade mostra em "Avaliação")
COLUNAS_DA_AVALIACAO_NO_ARQUIVO = ("Situação na avaliação", "Problema apontado")


def _situacao_no_arquivo(linha: int, linhas_com_alerta: set, apontadas: dict) -> str:
    """A situação da pessoa no arquivo do envio, com as palavras da tela.

    Recebe: linha; linhas_com_alerta (quem teve alerta confirmado pela empresa); apontadas ({linha: apontamento}).
    Devolve: "Apontado por você", "Confirmado pela empresa" ou "Pronto".
    """
    if linha in apontadas:
        return "Apontado por você"
    if linha in linhas_com_alerta:
        return "Confirmado pela empresa"
    return "Pronto"


def arquivo_do_envio(conexao, usuario, processamento_id: str) -> tuple[bytes, str]:
    """O arquivo (CSV para o Excel) com as pessoas do envio, como a grade da tela Envios mostra:
    a linha no arquivo, todos os campos do parâmetro vigente, a situação e o problema apontado.

    Recebe: conexao; usuario (só o BANCO); processamento_id (um envio que está ou esteve na avaliação do banco).
    Devolve: (os bytes do arquivo, o nome dele). Exemplo de nome: "envio_EMP001_94a3322a4416.csv".
    Os valores vão como o layout do banco guarda (CPF só com números, data AAAA-MM-DD, valor com ponto), prontos para
    outro sistema ler; célula com cara de fórmula é neutralizada ("CSV injection"). O download fica registrado nos
    acessos a dados pessoais da empresa (quem, quando e quantas pessoas; nunca o CPF).
    Levanta KeyError se o envio não existe ou não passou pelo banco.
    """
    autorizar(usuario, "avaliar_envios")
    perfil = processamentos.obter(conexao, processamento_id)
    if perfil is None or not _passou_pelo_banco(conexao, perfil):
        raise KeyError(processamento_id)
    # Quem teve alerta confirmado pela empresa (a mesma conta de pessoas_do_envio)
    relatorio = validador.obter(conexao, processamento_id) or validador.RelatorioValidacao()
    linhas_com_alerta = set()
    for achado in relatorio.achados:
        if achado.severidade == validador.ALERTA and achado.regra_id != "JA_HOMOLOGADO_NA_EMPRESA":
            linhas_com_alerta.add(achado.linha)
    apontadas = apontamentos_do_banco.rascunhos(conexao, processamento_id)
    # O cabeçalho: a linha, o rótulo de cada campo do parâmetro (como na grade) e as colunas da avaliação
    colunas = acompanhamento.colunas_da_consulta(conexao)
    cabecalho = ["Linha no arquivo"]
    for coluna in colunas:
        cabecalho.append(coluna["rotulo"])
    for titulo in COLUNAS_DA_AVALIACAO_NO_ARQUIVO:
        cabecalho.append(titulo)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(cabecalho)
    # Uma linha por pessoa avaliada (quem já estava cadastrado na empresa fica de fora, como na grade)
    registros = _registros_avaliados(conexao, processamento_id)
    for linha, registro in registros.items():
        valores = [str(linha)]
        for coluna in colunas:
            valor = registro.get(coluna["campo"])
            valores.append("" if valor is None else str(valor))
        valores.append(_situacao_no_arquivo(linha, linhas_com_alerta, apontadas))
        # O problema apontado: "Motivo: recado" (vazio sem apontamento)
        problema = ""
        if linha in apontadas:
            problema = apontadas[linha]["motivo_texto"] + ": " + apontadas[linha]["recado"]
        valores.append(problema)
        # Cada valor protegido contra fórmula do Excel
        linha_do_arquivo = []
        for valor in valores:
            linha_do_arquivo.append(homologacao.neutralizar_formula(valor))
        escritor.writerow(linha_do_arquivo)
    # Quem do banco baixou os dados das pessoas desta empresa, e quantas (a prestação de contas da LGPD)
    acompanhamento.registrar_acesso(conexao, perfil.empresa_id, usuario.login, acompanhamento.ACESSO_DOWNLOAD,
                                    len(registros))
    nome_do_arquivo = "envio_" + perfil.empresa_id + "_" + processamento_id + ".csv"
    # "\ufeff" no começo avisa o Excel que o arquivo é UTF-8 (senão os acentos saem errados)
    return ("\ufeff" + saida.getvalue()).encode("utf-8"), nome_do_arquivo


def _apontamento_para_a_tela(apontamento: dict | None) -> dict | None:
    """O apontamento de uma pessoa como a tela do banco usa: {motivo, motivo_texto, recado}, ou None."""
    if apontamento is None:
        return None
    return {"motivo": apontamento["motivo"], "motivo_texto": apontamento["motivo_texto"],
            "recado": apontamento["recado"]}


def _envio_esperando_o_banco(conexao, processamento_id: str):
    """O retrato de um envio que espera a avaliação do banco.

    Recebe: conexao; processamento_id. Devolve: o retrato. Levanta KeyError (envio que não existe) ou ValueError
    (envio que não espera o banco).
    """
    perfil = processamentos.obter(conexao, processamento_id)
    if perfil is None:
        raise KeyError(processamento_id)
    if perfil.status != EstadoProcessamento.AGUARDANDO_BANCO:
        raise ValueError("Este envio não está esperando a avaliação do banco.")
    return perfil


def _registros_avaliados(conexao, processamento_id: str) -> dict[int, dict]:
    """As pessoas que o banco avalia no envio, pela linha: os dados atuais, sem quem já estava cadastrado na empresa.

    Recebe: conexao; processamento_id. Devolve: {linha: registro}.
    """
    relatorio = validador.obter(conexao, processamento_id) or validador.RelatorioValidacao()
    # Quem fica de fora do envio (já cadastrado ou já com o banco noutro envio; ADR-126)
    linhas_repetidas = validador.linhas_que_ficam_de_fora(relatorio)
    registros_por_linha = {}
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] not in linhas_repetidas:
            registros_por_linha[registro["_linha"]] = registro
    return registros_por_linha


def apontar(conexao, usuario, processamento_id: str, linha: int, motivo: str, recado: str) -> dict:
    """O especialista aponta um problema numa pessoa do envio que espera o banco (ADR-121).

    Recebe: conexao; usuario (só o BANCO); o envio; linha (a pessoa, como vem em pessoas_do_envio); motivo (uma chave
    de apontamentos_do_banco.MOTIVOS); recado (o que a empresa vai ler). Devolve: {motivo, motivo_texto, recado}.
    Pode apontar qualquer pessoa, com ou sem alerta. Apontar de novo troca o recado.
    Levanta KeyError (envio que não existe) ou ValueError (não espera o banco, linha fora do envio, motivo ou recado).
    """
    autorizar(usuario, "avaliar_envios")
    perfil = _envio_esperando_o_banco(conexao, processamento_id)
    if linha not in _registros_avaliados(conexao, processamento_id):
        raise ValueError("Esta pessoa não está neste envio.")
    recado_limpo = apontamentos_do_banco.conferir_recado(motivo, recado)
    apontamento = apontamentos_do_banco.gravar_rascunho(conexao, processamento_id, perfil.empresa_id, linha, motivo,
                                                        recado_limpo, usuario.login)
    return _apontamento_para_a_tela(apontamento)


def desfazer_apontamento(conexao, usuario, processamento_id: str, linha: int) -> None:
    """O especialista desfaz o apontamento de uma pessoa (mudou de ideia antes de decidir o envio).

    Recebe: conexao; usuario (só o BANCO); o envio; linha. Devolve: nada.
    Levanta KeyError (envio que não existe) ou ValueError (não espera o banco, ou a pessoa não estava apontada).
    """
    autorizar(usuario, "avaliar_envios")
    perfil = _envio_esperando_o_banco(conexao, processamento_id)
    if not apontamentos_do_banco.apagar_rascunho(conexao, processamento_id, perfil.empresa_id, linha, usuario.login):
        raise ValueError("Esta pessoa não estava apontada.")


def _qual_decisao(aprovar: bool | None, decisao: str | None) -> str:
    """A decisão pedida, aceitando o jeito antigo ({aprovar: true/false}) e o novo ({decisao: "..."}).

    Exemplos: (True, None) → "aprovar"; (False, None) → "devolver"; (None, "aprovar_e_devolver_marcados") → ele mesmo.
    Levanta ValueError se a decisão não é uma das três.
    """
    if decisao is None:
        if aprovar:
            return DECISAO_APROVAR
        return DECISAO_DEVOLVER
    if decisao not in DECISOES:
        raise ValueError("Decisão desconhecida.")
    return decisao


def _conferir_a_decisao(decisao: str, apontadas: dict, registros: dict, motivo: str) -> None:
    """Confere se a decisão combina com as pessoas apontadas (o botão certo para a situação).

    Recebe: decisao; apontadas ({linha: apontamento em rascunho}); registros (as pessoas avaliadas); motivo.
    Devolve: nada. Levanta ValueError com a frase para a tela.
    """
    if decisao == DECISAO_APROVAR and apontadas:
        raise ValueError("Há " + idas_e_voltas.texto_de_pessoas(len(apontadas)) + " com problema apontado: use "
                         "\"Aprovar e devolver\" ou desfaça os apontamentos.")
    if decisao == DECISAO_APROVAR_E_DEVOLVER and not apontadas:
        raise ValueError("Nenhuma pessoa está apontada: use \"Aprovar o envio\".")
    if decisao == DECISAO_APROVAR_E_DEVOLVER and len(apontadas) >= len(registros):
        raise ValueError("Todas as pessoas estão apontadas: use \"Devolver o envio inteiro\".")
    if decisao == DECISAO_DEVOLVER and not (motivo or "").strip():
        raise ValueError("Escreva o motivo da devolução: é o recado que a empresa vai ler.")


def avaliar(conexao, usuario, processamento_id: str, aprovar: bool | None = None, motivo: str = "",
            decisao: str | None = None) -> dict:
    """O especialista decide um envio que espera o banco: aprovar, aprovar os outros e devolver os apontados, ou
    devolver o envio inteiro (ADR-121).

    Recebe: conexao; usuario (só o BANCO; o login fica na auditoria); processamento_id; aprovar (o jeito antigo:
    True aprova, False devolve) ou decisao ("aprovar", "aprovar_e_devolver_marcados" ou "devolver"); motivo
    (obrigatório para devolver o envio inteiro). Devolve: o envio já avaliado, no formato da fila, com
    "envio_de_devolucao" (o identificador do envio de devolução criado, ou None).
    Levanta KeyError (envio que não existe) ou ValueError (não espera o banco, decisão que não combina com os
    apontamentos, devolução sem motivo ou o fluxo recusou).
    """
    autorizar(usuario, "avaliar_envios")
    perfil = _envio_esperando_o_banco(conexao, processamento_id)
    decisao = _qual_decisao(aprovar, decisao)
    apontadas = apontamentos_do_banco.rascunhos(conexao, processamento_id)
    registros = _registros_avaliados(conexao, processamento_id)
    _conferir_a_decisao(decisao, apontadas, registros, motivo)
    envio_de_devolucao = None
    if decisao == DECISAO_APROVAR:
        resposta = {"acao": "aprovar", "usuario": usuario.login}
        fluxo_empresa.responder(conexao, processamento_id, perfil.empresa_id, "avaliar_no_banco", resposta)
    elif decisao == DECISAO_APROVAR_E_DEVOLVER:
        envio_de_devolucao = _aprovar_e_devolver(conexao, usuario, perfil, set(apontadas))
    else:
        _devolver_inteiro(conexao, usuario, perfil, motivo.strip(), registros)
    envio = _envio_na_fila(conexao, processamentos.obter(conexao, processamento_id))
    envio["envio_de_devolucao"] = envio_de_devolucao
    return envio


def _aprovar_e_devolver(conexao, usuario, perfil, linhas_devolvidas: set[int]) -> str:
    """Cadastra as pessoas sem apontamento e manda as apontadas de volta num envio de devolução.

    Recebe: conexao; usuario; perfil (o envio avaliado); linhas_devolvidas. Devolve: o id do envio de devolução.
    Levanta ValueError se o fluxo não aprovou (ex.: apareceu uma pendência nova desde o envio).
    """
    resposta = {"acao": "aprovar_parte", "linhas_devolvidas": sorted(linhas_devolvidas), "usuario": usuario.login}
    situacao = fluxo_empresa.responder(conexao, perfil.processamento_id, perfil.empresa_id, "avaliar_no_banco",
                                       resposta)
    # O fluxo devolve o recado quando não conseguiu cadastrar (a decisão não foi tomada)
    if processamentos.obter(conexao, perfil.processamento_id).status != EstadoProcessamento.HOMOLOGADO:
        raise ValueError(situacao["estado"].get("ultimo_erro") or "Não foi possível aprovar este envio agora.")
    # As outras já estão cadastradas: as apontadas vão para o envio de devolução
    return devolucao_por_pessoa.criar_envio_de_devolucao(conexao, perfil.processamento_id, linhas_devolvidas,
                                                         usuario.login)


def _devolver_inteiro(conexao, usuario, perfil, motivo: str, registros: dict) -> None:
    """Devolve o envio inteiro com o motivo; os apontamentos feitos viram pendências do próprio envio.

    Recebe: conexao; usuario; perfil (o envio avaliado); motivo; registros (as pessoas avaliadas, pela linha).
    Devolve: nada.
    """
    resposta = {"acao": "devolver", "motivo": motivo, "usuario": usuario.login}
    fluxo_empresa.responder(conexao, perfil.processamento_id, perfil.empresa_id, "avaliar_no_banco", resposta)
    # Sem apontamento, é a devolução de sempre
    if not apontamentos_do_banco.rascunhos(conexao, perfil.processamento_id):
        return
    # Com apontamentos: eles vão para a empresa neste mesmo envio e viram pendências das pessoas
    apontamentos_do_banco.enviar_para_a_empresa(conexao, perfil.processamento_id, perfil.processamento_id, registros)
    validador.executar(conexao, perfil.processamento_id, perfil.empresa_id)
    # A validação acima deixou a situação em "com pendências": o envio acabou de ser devolvido pelo banco
    processamentos.atualizar_status(conexao, perfil.processamento_id, EstadoProcessamento.DEVOLVIDO)


def envios_esperando_o_banco(conexao) -> int:
    """Quantos envios da carteira esperam a avaliação do banco (o número da aba Envios e do Início)."""
    quantidade = 0
    for empresa in dados_mock.empresas():
        for perfil in processamentos.listar(conexao, empresa["empresa_id"]):
            if perfil.status == EstadoProcessamento.AGUARDANDO_BANCO:
                quantidade = quantidade + 1
    return quantidade
