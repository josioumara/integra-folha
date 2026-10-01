"""As conversas das pendências com o Agente de validação, guardadas no servidor, e a lista das pendências resolvidas
(ADR-120).

Para que serve: em "Acompanhar cadastros", a pendência resolvida vai para o filtro "Resolvidas", e a empresa pode
abrir de novo a conversa que teve com a IA, mesmo depois de recarregar a página ou em outro dia. Por isso cada balão
da conversa (a pergunta do agente, o que a empresa escreveu, a resposta do agente com o que mudou e o Desfazer) fica
gravado numa tabela, pela chave da conversa.

A chave da conversa é a mesma que a tela usa (front/js/assistente_de_correcao.js, chave_da_conversa):
    - uma pessoa:  "<envio>|<regra>|<linha>|<campo>" (sem linha: "null"). Ex.: "a1b2|CPF_INVALIDO|8|cpf";
    - um grupo:    "grupo|<envio>|<campo>|<valor>" (o valor sem maiúsculas e sem espaços nas pontas).

As regras:
    - quem grava é o servidor (services/assistente_na_tela.py), nunca o navegador: a tela só lê;
    - a conversa tem dado pessoal (é o dado da própria empresa, como a pendência): só a empresa dona do envio a vê;
      a trilha de auditoria continua sem valor pessoal;
    - "Resolvidas" mostra as conversas em que a última mudança ainda vale (não foi desfeita) e cuja pendência não está
      mais em aberto, só dos envios que ainda estão com a empresa (depois de ir ao banco, o histórico fica na trilha).

Exemplo de uso:
    registrar(conexao, "a1b2", "a1b2|CPF_INVALIDO|8", abertura, [fala_da_empresa, fala_do_agente], "rh.aurora")
    resolvidas = resolvidas_da_empresa(conexao, "EMP001")
"""
import json
from datetime import datetime, timezone

from models.contratos import EstadoProcessamento
from services import pendencias_em_grupo, processamentos, validador

# O começo da chave de uma conversa de grupo
PREFIXO_DO_GRUPO = "grupo|"


def _preparar(conexao) -> None:
    """Cria a tabela das conversas, se ainda não existir (um balão por linha)."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS conversas_das_pendencias (
               processamento_id TEXT NOT NULL,
               chave            TEXT NOT NULL,     -- a chave da conversa (ver o texto do alto)
               ordem            INTEGER NOT NULL,  -- a posição do balão na conversa (0 = a pergunta do agente)
               quem             TEXT NOT NULL,     -- "ia", "empresa" ou "erro"
               texto            TEXT NOT NULL,
               detalhe          TEXT NOT NULL,     -- JSON: pergunta, aplicado, confirmacao, recusado, fontes
               titulo           TEXT NOT NULL,     -- de quem é: o nome, ou "4 pessoas com o mesmo valor"
               nome_do_campo    TEXT NOT NULL,     -- a informação, em linguagem simples
               quantidade       INTEGER NOT NULL,  -- quantas pessoas (mais de 1 no grupo)
               login            TEXT,              -- quem escreveu (ou em nome de quem o agente respondeu)
               criado_em        TEXT NOT NULL,
               PRIMARY KEY (processamento_id, chave, ordem)
           )"""
    )


def _agora() -> str:
    """Data e hora atuais (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def chave_da_conversa(processamento_id: str, regra_id: str, linha: int | None, campo: str | None) -> str:
    """A chave da conversa de uma pessoa (ou do arquivo inteiro): o envio, a regra, a linha e o campo.

    Ex.: ("a1b2", "CPF_INVALIDO", 8, "cpf") → "a1b2|CPF_INVALIDO|8|cpf"; sem linha:
    "a1b2|OBRIGATORIO_SEM_COLUNA|null|matricula" (como o JavaScript escreve). O campo entra porque a mesma regra
    aparece uma vez por campo na mesma linha (ex.: 11 colunas obrigatórias faltando no arquivo inteiro).
    """
    linha_em_texto = "null" if linha is None else str(linha)
    return f"{processamento_id}|{regra_id}|{linha_em_texto}|{campo or ''}"


def chave_da_conversa_do_grupo(processamento_id: str, chave_do_grupo: str) -> str:
    """A chave da conversa de um grupo. Ex.: ("a1b2", "estado_civil|casdo") → "grupo|a1b2|estado_civil|casdo"."""
    return f"{PREFIXO_DO_GRUPO}{processamento_id}|{chave_do_grupo}"


def fala(quem: str, texto: str, pergunta: bool = False, aplicado: dict | None = None,
         confirmacao: dict | None = None, recusado: bool = False, fontes: list | None = None,
         sem_valor: bool = False, encerrada: bool = False) -> dict:
    """Um balão, no formato que a tela desenha.

    Ex.: fala("empresa", "Casado") ou fala("ia", "Pronto: ...", aplicado=...).

    aplicado: {resumo, desfazer: {tipo, id} ou None}; ganha "desfeito" (False) aqui.
    sem_valor: a resposta do agente a quem respondeu sem um valor ("não sei"); encerrada: a resposta em que o agente
    encerrou a conversa (ADR-153). São as marcas que contam as respostas sem valor da conversa.
    """
    aplicado_do_balao = None
    if aplicado:
        aplicado_do_balao = {"resumo": aplicado["resumo"], "desfazer": aplicado.get("desfazer"), "desfeito": False}
    return {"quem": quem, "texto": texto, "pergunta": pergunta, "aplicado": aplicado_do_balao,
            "confirmacao": confirmacao, "recusado": recusado, "fontes": fontes or [], "sem_valor": sem_valor,
            "encerrada": encerrada}


def _linhas_da_tabela(conexao, processamento_id: str) -> list[tuple]:
    """Todos os balões guardados do envio, em ordem de conversa e de posição."""
    _preparar(conexao)
    return list(conexao.execute(
        "SELECT chave, ordem, quem, texto, detalhe, titulo, nome_do_campo, quantidade, login, criado_em "
        "FROM conversas_das_pendencias WHERE processamento_id = ? ORDER BY chave, ordem", (processamento_id,)))


def _balao_da_linha(linha_da_tabela: tuple) -> dict:
    """Um balão a partir de uma linha da tabela: {quem, texto, pergunta, aplicado, confirmacao, recusado, fontes,
    login, criado_em, ordem}."""
    chave, ordem, quem, texto, detalhe, _, _, _, login, criado_em = linha_da_tabela
    balao = {"quem": quem, "texto": texto, "ordem": ordem, "login": login, "criado_em": criado_em}
    balao.update(json.loads(detalhe))
    return balao


def conversas_do_envio(conexao, processamento_id: str) -> dict[str, dict]:
    """As conversas guardadas do envio: {chave: {titulo, nome_do_campo, quantidade, baloes: [...]}}."""
    conversas = {}
    for linha_da_tabela in _linhas_da_tabela(conexao, processamento_id):
        chave, _, _, _, _, titulo, nome_do_campo, quantidade, _, _ = linha_da_tabela
        if chave not in conversas:
            conversas[chave] = {"titulo": titulo, "nome_do_campo": nome_do_campo, "quantidade": quantidade,
                                "baloes": []}
        conversas[chave]["baloes"].append(_balao_da_linha(linha_da_tabela))
    return conversas


def conversa_existe(conexao, processamento_id: str, chave: str) -> bool:
    """True se a conversa já tem algum balão guardado."""
    _preparar(conexao)
    for _ in conexao.execute("SELECT 1 FROM conversas_das_pendencias WHERE processamento_id = ? AND chave = ? "
                             "LIMIT 1", (processamento_id, chave)):
        return True
    return False


def respostas_sem_valor_desde_o_encerramento(conexao, processamento_id: str, chave: str) -> int:
    """Quantas respostas sem valor ("não sei", "não tenho") a conversa teve desde o último encerramento (ou desde o
    começo, se ela nunca foi encerrada), pelas marcas dos balões do agente (ADR-153).

    Ex.: a pergunta, "não sei" (sem_valor), "C900" (recusado), "não tenho" (sem_valor) → 2; depois de um balão
    encerrada, a conta recomeça do zero. Conversa que ainda não existe → 0.
    """
    _preparar(conexao)
    quantas = 0
    for (detalhe,) in conexao.execute("SELECT detalhe FROM conversas_das_pendencias WHERE processamento_id = ? AND "
                                      "chave = ? AND quem = 'ia' ORDER BY ordem", (processamento_id, chave)):
        marcas = json.loads(detalhe)
        # O encerramento zera a conta: a conversa recomeça se a pessoa escrever de novo
        if marcas.get("encerrada"):
            quantas = 0
        elif marcas.get("sem_valor"):
            quantas = quantas + 1
    return quantas


def _proxima_ordem(conexao, processamento_id: str, chave: str) -> int:
    """A posição do próximo balão da conversa (0 se ela ainda não existe)."""
    for (maior,) in conexao.execute("SELECT MAX(ordem) FROM conversas_das_pendencias WHERE processamento_id = ? "
                                    "AND chave = ?", (processamento_id, chave)):
        if maior is not None:
            return maior + 1
    return 0


def ordem_da_ultima_fala(conexao, processamento_id: str, chave: str) -> int | None:
    """A posição do último balão guardado da conversa (a resposta do agente que acabou de ser gravada), ou None se a
    conversa ainda não existe.

    A tela recebe essa posição junto com a resposta: é por ela que o joinha diz qual resposta recebeu o voto
    (services/opiniao_dos_agentes.py). Ex.: a pergunta (0), a fala da pessoa (1) e a resposta (2) → 2.
    """
    _preparar(conexao)
    proxima = _proxima_ordem(conexao, processamento_id, chave)
    # Nenhum balão guardado: a conversa não existe
    if proxima == 0:
        return None
    return proxima - 1


def balao_guardado(conexao, processamento_id: str, chave: str, ordem: int) -> dict | None:
    """Quem falou num balão guardado e se ele é a pergunta que abre o cartão: {quem, pergunta}, ou None se não existe.

    Serve ao joinha, que só aceita o voto numa resposta do agente (services/opiniao_dos_agentes.py).
    Ex.: a resposta "Pronto: ..." na posição 2 → {"quem": "ia", "pergunta": False}.
    """
    _preparar(conexao)
    for quem, detalhe in conexao.execute("SELECT quem, detalhe FROM conversas_das_pendencias WHERE processamento_id = ? "
                                         "AND chave = ? AND ordem = ?", (processamento_id, chave, ordem)):
        # A pergunta que abre o cartão tem a marca "pergunta" no detalhe (JSON)
        return {"quem": quem, "pergunta": bool(json.loads(detalhe).get("pergunta"))}
    return None


def _cabecalho(conexao, processamento_id: str, chave: str) -> tuple[str, str, int] | None:
    """(titulo, nome_do_campo, quantidade) da conversa, ou None se ela ainda não existe."""
    for titulo, nome_do_campo, quantidade in conexao.execute(
            "SELECT titulo, nome_do_campo, quantidade FROM conversas_das_pendencias WHERE processamento_id = ? "
            "AND chave = ? ORDER BY ordem LIMIT 1", (processamento_id, chave)):
        return titulo, nome_do_campo, quantidade
    return None


def registrar(conexao, processamento_id: str, chave: str, abertura: dict | None, baloes: list[dict],
              login: str) -> None:
    """Grava os balões novos no fim da conversa.

    Recebe: o envio; a chave da conversa; abertura — {titulo, nome_do_campo, quantidade, pergunta}, usada só quando a
    conversa ainda não existe (a pergunta do agente vira o 1º balão); os balões novos (ver fala); quem escreveu.
    Devolve: nada. Sem abertura e sem conversa, não grava (não há de quem nem de que campo).
    """
    _preparar(conexao)
    cabecalho = _cabecalho(conexao, processamento_id, chave)
    baloes_a_gravar = list(baloes)
    if cabecalho is None:
        if abertura is None:
            return
        cabecalho = (abertura["titulo"], abertura["nome_do_campo"], abertura["quantidade"])
        # A pergunta do agente, como a pessoa viu, é o primeiro balão
        baloes_a_gravar.insert(0, fala("ia", abertura["pergunta"], pergunta=True))
    titulo, nome_do_campo, quantidade = cabecalho
    ordem = _proxima_ordem(conexao, processamento_id, chave)
    agora = _agora()
    for balao in baloes_a_gravar:
        # O que não é o texto nem quem falou vai no detalhe (JSON)
        conexao.execute("INSERT INTO conversas_das_pendencias (processamento_id, chave, ordem, quem, texto, detalhe, "
                        "titulo, nome_do_campo, quantidade, login, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (processamento_id, chave, ordem, balao["quem"], balao["texto"],
                         json.dumps(_detalhe(balao), ensure_ascii=False), titulo, nome_do_campo, quantidade, login,
                         agora))
        ordem = ordem + 1
    conexao.commit()


def _trocar_detalhe(conexao, processamento_id: str, chave: str, ordem: int, detalhe: dict) -> None:
    """Regrava o detalhe de um balão (ex.: o Desfazer virou "Desfeito"). Não faz commit."""
    conexao.execute("UPDATE conversas_das_pendencias SET detalhe = ? WHERE processamento_id = ? AND chave = ? "
                    "AND ordem = ?", (json.dumps(detalhe, ensure_ascii=False), processamento_id, chave, ordem))


def _detalhe(balao: dict) -> dict:
    """O detalhe de um balão, como vai para a tabela. As marcas das respostas sem valor (ADR-153) não existem nos
    balões gravados antes delas: sem a marca, vale False."""
    return {"pergunta": balao["pergunta"], "aplicado": balao["aplicado"], "confirmacao": balao["confirmacao"],
            "recusado": balao["recusado"], "fontes": balao["fontes"], "sem_valor": balao.get("sem_valor", False),
            "encerrada": balao.get("encerrada", False)}


def registrar_o_desfazer(conexao, processamento_id: str, tipo: str, identificador: str, resumo: str,
                         login: str) -> None:
    """Marca como "Desfeito" o balão que trouxe esta mudança e conta na conversa o que voltou.

    Recebe: o envio; o tipo e o id do Desfazer (os mesmos de aplicado.desfazer); o resumo do que voltou; quem pediu.
    Devolve: nada (se a mudança não veio de uma conversa guardada, não há o que marcar).
    """
    for chave, conversa in conversas_do_envio(conexao, processamento_id).items():
        for balao in conversa["baloes"]:
            aplicado = balao.get("aplicado")
            if aplicado and aplicado.get("desfazer") == {"tipo": tipo, "id": identificador}:
                aplicado["desfeito"] = True
                _trocar_detalhe(conexao, processamento_id, chave, balao["ordem"], _detalhe(balao))
                conexao.commit()
                registrar(conexao, processamento_id, chave, None, [fala("ia", resumo)], login)
                return


def registrar_a_confirmacao(conexao, processamento_id: str, correcao_id: str, escolha: str, resposta: dict,
                            login: str) -> None:
    """Grava a escolha da pessoa numa pergunta de confirmação ("Sim, não cadastrar" ou "Cancelar") e a resposta do
    agente, e marca a pergunta como decidida (os botões não voltam ao reabrir a conversa).

    Recebe: o envio; a retirada proposta; o texto da escolha; resposta — {mensagem, aplicado}; quem escolheu.
    """
    for chave, conversa in conversas_do_envio(conexao, processamento_id).items():
        for balao in conversa["baloes"]:
            confirmacao = balao.get("confirmacao")
            if confirmacao and confirmacao.get("correcao_id") == correcao_id:
                confirmacao["decidida"] = True
                _trocar_detalhe(conexao, processamento_id, chave, balao["ordem"], _detalhe(balao))
                conexao.commit()
                registrar(conexao, processamento_id, chave, None,
                          [fala("empresa", escolha), fala("ia", resposta["mensagem"], aplicado=resposta["aplicado"])],
                          login)
                # A posição da resposta na conversa vai para a tela, com a resposta (é por ela que o joinha vota)
                resposta["ordem"] = ordem_da_ultima_fala(conexao, processamento_id, chave)
                return


# ---------------- As pendências resolvidas ----------------

def _pendencia_da_chave_em_aberto(chave: str, achados: list) -> bool:
    """True se a pendência da conversa ainda está em aberto no relatório do Validador.

    Uma pessoa: um achado em aberto com a mesma regra, a mesma linha e o mesmo campo (na chave antiga, sem o campo,
    qualquer campo). Um grupo: algum achado em aberto com o mesmo campo e o mesmo valor (ainda há alguém do grupo
    com o valor fora da lista).
    """
    if chave.startswith(PREFIXO_DO_GRUPO):
        # "grupo|<envio>|<campo>|<valor>": o que vem depois do envio é a chave do grupo
        chave_do_grupo = chave.split("|", 2)[2]
        for achado in achados:
            # Só o valor fora da lista, ainda em aberto, com campo e valor
            do_tipo_do_grupo = achado.regra_id == pendencias_em_grupo.REGRA_DO_GRUPO and achado.campo and achado.valor
            if not do_tipo_do_grupo or not pendencias_em_grupo.achado_em_aberto(achado):
                continue
            if pendencias_em_grupo.chave_do_grupo(achado) == chave_do_grupo:
                return True
        return False
    # "<envio>|<regra>|<linha>|<campo>"
    partes = chave.split("|", 3)
    regra_id = partes[1]
    linha_em_texto = partes[2]
    # A chave antiga (gravada antes de o campo entrar nela) tem só envio, regra e linha: vale qualquer campo
    campo = None
    if len(partes) == 4:
        campo = partes[3]
    for achado in achados:
        mesma_linha = str(achado.linha) == linha_em_texto or (achado.linha is None and linha_em_texto == "null")
        mesmo_campo = campo is None or (achado.campo or "") == campo
        if achado.regra_id == regra_id and mesma_linha and mesmo_campo and pendencias_em_grupo.achado_em_aberto(achado):
            return True
    return False


def _ultima_mudanca(baloes: list[dict]) -> dict | None:
    """O último balão do agente que mudou algo, ou None se a conversa nunca mudou nada."""
    ultima = None
    for balao in baloes:
        if balao.get("aplicado"):
            ultima = balao
    return ultima


def _resolvida_para_a_tela(chave: str, conversa: dict, mudanca: dict, perfil, enviado_em, nome_arquivo: str) -> dict:
    """Uma resolvida como a tela recebe (ver resolvidas_da_empresa)."""
    baloes = []
    for balao in conversa["baloes"]:
        # A posição ("ordem") vai junto: é por ela que o joinha de cada resposta vota (services/opiniao_dos_agentes.py)
        baloes.append({"quem": balao["quem"], "texto": balao["texto"], "pergunta": balao.get("pergunta", False),
                       "aplicado": balao.get("aplicado"), "confirmacao": balao.get("confirmacao"),
                       "recusado": balao.get("recusado", False), "fontes": balao.get("fontes") or [],
                       "ordem": balao["ordem"]})
    return {"chave": chave, "processamento_id": perfil.processamento_id, "nome_arquivo": nome_arquivo,
            "enviado_em": enviado_em, "titulo": conversa["titulo"], "nome_do_campo": conversa["nome_do_campo"],
            "quantidade": conversa["quantidade"], "resumo": mudanca["aplicado"]["resumo"],
            "resolvida_em": mudanca["criado_em"], "resolvida_por": mudanca["login"], "conversa": baloes}


def resolvidas_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """As pendências que a empresa resolveu conversando com o agente, nos envios que ainda estão com ela.

    Recebe: conexao; empresa_id (da sessão). Devolve: a lista, da mais recente para a mais antiga, de
    {chave, processamento_id, nome_arquivo, enviado_em, titulo, nome_do_campo, quantidade, resumo, resolvida_em,
    resolvida_por, conversa: [{quem, texto, pergunta, aplicado, confirmacao, recusado, fontes, ordem}]}.
    Entra a conversa cuja última mudança ainda vale (não foi desfeita) e cuja pendência não está mais em aberto.
    """
    # Importado aqui: acompanhamento importa serviços que importam este arquivo
    from services.acompanhamento import quando_e_quem_enviou
    quando_e_quem = quando_e_quem_enviou(conexao, empresa_id)
    # O nome de cada arquivo como a tela mostra (arquivos diferentes com o mesmo nome ganham "(v1)", "(v2)")
    nomes_dos_arquivos = processamentos.nomes_na_tela(conexao, empresa_id)
    resolvidas = []
    for perfil in processamentos.listar(conexao, empresa_id):
        # Depois de ir ao banco (ou descartado), o histórico fica na trilha do envio
        if perfil.status in (EstadoProcessamento.HOMOLOGADO, EstadoProcessamento.REJEITADO):
            continue
        relatorio = validador.obter(conexao, perfil.processamento_id)
        achados = relatorio.achados if relatorio else []
        enviado_em = quando_e_quem.get(perfil.processamento_id, (None,))[0]
        for chave, conversa in conversas_do_envio(conexao, perfil.processamento_id).items():
            mudanca = _ultima_mudanca(conversa["baloes"])
            # Nunca mudou nada, ou a última mudança foi desfeita: não é uma resolvida
            if mudanca is None or mudanca["aplicado"].get("desfeito"):
                continue
            # A pendência ainda está em aberto (ex.: o valor novo ainda tem problema): continua em "em aberto"
            if _pendencia_da_chave_em_aberto(chave, achados):
                continue
            resolvidas.append(_resolvida_para_a_tela(chave, conversa, mudanca, perfil, enviado_em,
                                                     nomes_dos_arquivos[perfil.processamento_id]))
    # Da mais recente para a mais antiga
    resolvidas.sort(key=_hora_da_resolvida, reverse=True)
    return resolvidas


def _hora_da_resolvida(resolvida: dict) -> str:
    """A hora da resolução (para ordenar a lista)."""
    return resolvida["resolvida_em"]
