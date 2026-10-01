"""Carrega a base viva no banco de dados da aplicação, SEM chamar a IA (desenho §3.8).

Para que serve: põe no banco as 17 empresas do roteiro (scripts/gerar_base_viva.py) como se elas usassem a plataforma
há uns 3 meses: o cadastro, o login do RH, os envios em todas as etapas da jornada, os funcionários cadastrados (com o
código CBO), o planejamento, as contas abertas, os acessos ao portal e as conversas com o banco.

Como entra:
    - pelas funções dos serviços, onde elas existem: a empresa pela conferência do cadastro (services/empresas.py), o
      kit próprio pela KB do kit publicada, a fonte única do kit (services/kbs_publicacao.py), a senha pelo bcrypt
      (services/auth.py), o arquivo pelo recebimento (services/processamentos.py), a
      padronização, a validação, as correções, o cadastro (homologação), o planejamento e as contas abertas pelos
      serviços de sempre.
      Assim cada tela lê exatamente o que leria depois do uso de verdade;
    - SEM a IA: a leitura das colunas não passa pelo Interpretador. O mapeamento é gravado já pronto, com a origem
      "regra" (a coluna ligada pela carga) ou "reuso" (a mesma coluna de um envio já aprovado), que não contam como
      proposta de nenhum agente de IA. O script roda no modo MOCK, e nenhuma execução de agente é gravada: a Telemetria
      e o teto de gasto mostram só o que a IA de verdade fez;
    - o conhecimento da IA não é tocado: o histórico de mapeamentos que a homologação grava é apagado na hora, e o
      aprendizado do RAG fica desligado (o índice não muda; a KB do kit entra no índice só na próxima indexação
      completa, scripts/indexar_kbs_endomarketing.py);
    - as datas: cada etapa acontece "agora" e em seguida ganha a data do roteiro (dias úteis antes da carga, no horário
      de Brasília). A base continua recente em qualquer dia em que a carga rodar;
    - o fluxo de cada envio em andamento fica parado na etapa certa (o ponto de salvamento do LangGraph), como se a
      pessoa tivesse parado ali: a empresa e o banco continuam dali pela tela;
    - a senha é uma só, a do segredo SENHA_DA_BASE_VIVA do .env, e é definitiva. O valor nunca é escrito aqui, em log
      ou na saída.

Pode rodar de novo: a empresa que já está completa é pulada. A opção --remover tira só a base viva (as empresas criadas
por esta carga e tudo o que é delas), e a opção --tambem-logins-da-demo põe a mesma senha nos logins da demo (o do
banco e o da Aurora).

Para rodar (na pasta integra-folha, com o .env do banco que vai receber a base):
    python scripts/carregar_base_viva.py
    python scripts/carregar_base_viva.py --tambem-logins-da-demo
    python scripts/carregar_base_viva.py --remover
A lista de conferência (tabela a tabela) é o scripts/conferir_base_viva.py.
"""
import argparse
import csv
import io
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# A carga nunca paga a IA: o modo MOCK vale antes de qualquer serviço ler o .env (o .env da máquina está no modo pago)
os.environ["MODE"] = "mock"
# O aprendizado do RAG fica desligado: nenhuma homologação da carga mexe no índice de verdade
os.environ["APRENDIZADO_DO_RAG"] = "desligado"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from models.contratos import EstadoProcessamento, ItemMapeamento, MappingPlan, Perfil, StatusMapeamento  # noqa: E402
from rag import busca  # noqa: E402
from scripts import gerar_base_viva  # noqa: E402
from scripts.criar_usuarios import USUARIOS_DEMO  # noqa: E402
from services import (acompanhamento, auditoria, auth, banco, contas_abertas, correcoes, empresas,  # noqa: E402
                      homologacao, kbs_publicacao, mapeamentos, mensagens, motor_planejamento, normalizador,
                      parametros, processamentos, sessoes, validador)
from services.aceitacao_dos_agentes import JUSTIFICATIVA_DO_REUSO  # noqa: E402
from services.auth import Usuario  # noqa: E402
from workflows import fluxo_empresa  # noqa: E402

# O nome gravado em "criado_por" nas empresas desta carga: é como a remoção reconhece a base viva. Tem espaços, então
# nunca é o login de alguém
MARCA_DA_BASE_VIVA = "carga da base viva"
# O nome do segredo com a senha única da base viva, no .env
NOME_DO_SEGREDO_DA_SENHA = "SENHA_DA_BASE_VIVA"
# De onde veio o kit de marca que a carga grava na KB do kit (vai na ficha da KB)
ORIGEM_DO_KIT = "Carga da base viva (dados sintéticos, sem IA)"
# Os 4 campos obrigatórios do parâmetro que a base viva segue (a v7, ADR-143)
OBRIGATORIOS_DA_V7 = {"cpf", "codigo_cbo", "valor_renda", "data_admissao"}
# O horário de Brasília (3 horas atrás do horário universal; sem horário de verão desde 2019)
FUSO_DE_BRASILIA = timezone(timedelta(hours=-3))
# O que o plano de mapeamento da carga diz de si mesmo: nenhuma IA leu as colunas
MODELO_DA_CARGA = "base viva (sem IA)"
SEM_IA = "sem IA"
JUSTIFICATIVA_DA_CARGA = "Coluna ligada ao campo pela carga da base viva (dados sintéticos, sem IA)."
# A confirmação que a empresa deu a cada alerta que sobrou antes de enviar ao banco (pela regra do alerta)
JUSTIFICATIVAS_DOS_ALERTAS = {
    "RENDA_FORA_DO_CARGO": "Valor conferido: pró-labore aprovado pelos sócios.",
    "RENDA_FORA_DA_PROFISSAO": "Salário conferido com o contrato de trabalho.",
    "VALOR_FORA_DA_FAIXA": "Valor conferido com a folha do mês.",
}
JUSTIFICATIVA_PADRAO = "Conferido pela empresa com a folha do mês."
# As etapas em que o fluxo de um envio fica parado, com a etapa que "acabou de rodar" antes dela
ETAPA_ANTERIOR_DA_PAUSA = {
    "aprovar_mapeamento": "interpretar",
    "aguardar_correcao": "validar",
    "aprovar_homologacao": "validar",
    "avaliar_no_banco": "aprovar_homologacao",
}
# Onde cada destino do roteiro deixa o fluxo parado (o CADASTRADO terminou: não tem pausa)
PAUSA_DE_CADA_DESTINO = {
    "NO_ACEITE": "aprovar_mapeamento",
    "PENDENTE": "aguardar_correcao",
    "PRONTO": "aprovar_homologacao",
    "EM_ANALISE": "avaliar_no_banco",
    "DEVOLVIDO": "aguardar_correcao",
}
# As tabelas com datas que a carga ajusta depois de cada etapa: (tabela, como achar as linhas da empresa, colunas)
# "empresa": a coluna empresa_id; "envio": o processamento_id, entre os envios da empresa
TABELAS_COM_DATA = (
    ("empresas", "empresa", ("criado_em",)),
    ("cnpjs_das_empresas", "empresa", ("registrado_em",)),
    ("processamentos", "empresa", ("criado_em",)),
    ("eventos", "empresa", ("criado_em",)),
    ("mapeamentos", "empresa", ("criado_em", "aprovado_em")),
    ("normalizacoes", "envio", ("criado_em",)),
    ("validacoes", "envio", ("criado_em",)),
    ("correcoes", "envio", ("criado_em", "decidido_em")),
    ("resolucoes_alerta", "envio", ("criado_em",)),
    ("cbo_dos_cargos", "empresa", ("registrado_em",)),
    ("homologacoes", "empresa", ("homologado_em",)),
    ("funcionarios_homologados", "empresa", ("homologado_em",)),
    ("planejamento_funcionario", "empresa", ("criado_em",)),
    ("contas_abertas", "empresa", ("baixa_em",)),
    ("arquivos_de_contas", "empresa", ("enviado_em", "decidido_em")),
    ("acessos_a_dados", "empresa", ("criado_em",)),
    ("mensagens_de_ajuda", "empresa", ("criado_em",)),
    ("conversas_resolvidas", "empresa", ("resolvida_em",)),
)
# Quantos segundos separam duas linhas gravadas na mesma etapa (mantém a ordem em que aconteceram)
PASSO_ENTRE_LINHAS = 4


class CargaRecusada(Exception):
    """A carga não pode seguir (ex.: falta a senha, o parâmetro não é a v7, uma empresa ficou pela metade)."""


# ================================ Datas ================================

def _agora_em_texto() -> str:
    """O momento real de agora (horário universal, em segundos), no mesmo formato em que os serviços gravam."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def momento_real(momento: dict, dia_da_carga: date) -> datetime:
    """A data e a hora de verdade de um momento do roteiro (dias úteis antes do dia da carga e a hora de Brasília).

    Ex.: {"dias_uteis": 2, "hora": "10:15"} com a carga na quarta 30/09/2026 → segunda 28/09/2026, 10:15 em Brasília
    (13:15 no horário universal, que é como o banco de dados guarda).
    """
    # O dia: tantos dias úteis antes do dia da carga (sábado e domingo não contam)
    dia = gerar_base_viva.dia_util_antes(dia_da_carga, momento["dias_uteis"])
    # A hora de Brasília, separada em horas e minutos ("10:15" → 10 e 15)
    horas, minutos = momento["hora"].split(":")
    # O dia e a hora juntos, no horário de Brasília
    local = datetime.combine(dia, time(int(horas), int(minutos)), tzinfo=FUSO_DE_BRASILIA)
    # O mesmo instante no horário universal (é assim que o banco de dados guarda)
    return local.astimezone(timezone.utc)


def _mais(momento: datetime, segundos: int) -> datetime:
    """O momento alguns segundos depois (ou antes, com segundos negativos)."""
    return momento + timedelta(seconds=segundos)


def _texto(momento: datetime) -> str:
    """O momento no formato do banco: horário universal, até os segundos (ex.: "2026-09-28T13:15:00+00:00")."""
    return momento.astimezone(timezone.utc).isoformat(timespec="seconds")


def _envios_da_empresa(conexao, empresa_id: str) -> list[str]:
    """Os identificadores dos envios da empresa."""
    # Garante que a tabela dos envios existe (num banco novo, ela ainda não foi criada)
    processamentos._preparar(conexao)
    identificadores = []
    # Um identificador por envio da empresa
    for (processamento_id,) in conexao.execute("SELECT processamento_id FROM processamentos WHERE empresa_id = ?",
                                               (empresa_id,)):
        identificadores.append(processamento_id)
    return identificadores


def _marcadores(quantidade: int) -> str:
    """Os "?" de uma lista no SQL (ex.: 3 → "?, ?, ?")."""
    return ", ".join(["?"] * quantidade)


def datar_a_etapa(conexao, empresa_id: str, inicio_real: str, momento: datetime) -> None:
    """Põe a data do roteiro em tudo o que a etapa acabou de gravar para a empresa.

    Recebe: conexao; a empresa; inicio_real — a hora REAL em que a etapa começou (as linhas com data a partir dela são
    desta etapa: as das etapas anteriores já foram para o passado); momento — a data do roteiro.
    Faz: em cada tabela de TABELAS_COM_DATA, as linhas da empresa gravadas agora ganham o momento, na ordem em que
    foram gravadas, com PASSO_ENTRE_LINHAS segundos entre uma e outra. A comparação das datas é feita aqui no Python
    (o texto ISO em horário universal ordena igual ao tempo), e não no SQL, que no PostgreSQL depende do idioma do banco.
    """
    # Os envios da empresa (as tabelas que só têm o processamento_id são achadas por eles)
    envios = _envios_da_empresa(conexao, empresa_id)
    for tabela, chave, colunas in TABELAS_COM_DATA:
        # A tabela ainda não existe neste banco (nenhum serviço a criou): nada a datar
        if not banco.colunas_da_tabela(conexao, tabela):
            continue
        # O filtro das linhas da empresa: pela coluna empresa_id ou pelos envios dela
        if chave == "empresa":
            filtro, valores = "empresa_id = ?", (empresa_id,)
        elif envios:
            filtro, valores = f"processamento_id IN ({_marcadores(len(envios))})", tuple(envios)
        else:
            # A empresa ainda não tem envio: nenhuma linha dessa tabela é dela
            continue
        # Cada coluna de data da tabela
        for coluna in colunas:
            _datar_uma_coluna(conexao, tabela, coluna, filtro, valores, inicio_real, momento)
    # Grava as datas de uma vez
    conexao.commit()


def _datar_uma_coluna(conexao, tabela: str, coluna: str, filtro: str, valores: tuple, inicio_real: str,
                      momento: datetime) -> None:
    """Numa coluna de data, as linhas gravadas a partir de inicio_real ganham o momento (um passo a mais em cada)."""
    # As linhas da empresa, na ordem em que foram gravadas (rowid: a ordem de gravação, no SQLite e no PostgreSQL)
    consulta = conexao.execute(f"SELECT rowid, {coluna} FROM {tabela} WHERE {filtro} ORDER BY rowid", valores)
    gravadas_agora = []
    for identificador, valor in consulta.fetchall():
        # Data a partir do começo da etapa: a linha foi gravada nesta etapa (a de antes já está no passado)
        if valor is not None and str(valor) >= inicio_real:
            gravadas_agora.append(identificador)
    # A primeira ganha o momento; cada uma das seguintes, alguns segundos depois (a ordem fica a mesma)
    for posicao, identificador in enumerate(gravadas_agora):
        conexao.execute(f"UPDATE {tabela} SET {coluna} = ? WHERE rowid = ?",
                        (_texto(_mais(momento, posicao * PASSO_ENTRE_LINHAS)), identificador))


# ================================ A empresa e o login ================================

def empresas_da_base_viva(conexao) -> list[dict]:
    """As empresas que esta carga criou (as que têm a MARCA_DA_BASE_VIVA em criado_por), com o id e o CNPJ."""
    # Garante que a tabela das empresas existe (e a semente das 6 fictícias)
    empresas._preparar(conexao)
    encontradas = []
    # Só as empresas com a marca da carga, na ordem do código (EMP007, EMP008...)
    for empresa_id, cnpj in conexao.execute("SELECT empresa_id, cnpj FROM empresas WHERE criado_por = ? "
                                            "ORDER BY empresa_id", (MARCA_DA_BASE_VIVA,)):
        encontradas.append({"empresa_id": empresa_id, "cnpj": cnpj})
    return encontradas


def _situacao_da_empresa(conexao, empresa: dict) -> str | None:
    """Se a empresa do roteiro já está no banco: None (não está), "completa" ou "incompleta".

    Levanta CargaRecusada se o CNPJ dela já é de uma empresa que não foi criada por esta carga.
    """
    for existente in empresas.listar(conexao):
        # A empresa do roteiro é achada pelo CNPJ (o id depende de quantas empresas já existiam)
        if existente["cnpj"] != empresa["cnpj"]:
            continue
        # Quem criou a empresa com esse CNPJ
        criado_por = conexao.execute("SELECT criado_por FROM empresas WHERE empresa_id = ?",
                                     (existente["empresa_id"],)).fetchone()[0]
        # O CNPJ é de uma empresa de verdade da carteira: a carga não mexe nela
        if criado_por != MARCA_DA_BASE_VIVA:
            raise CargaRecusada(f"O CNPJ da empresa {empresa['nome']} já é de outra empresa da carteira "
                                f"({existente['empresa_id']}).")
        # Completa: todos os envios do roteiro já estão no banco
        if len(_envios_da_empresa(conexao, existente["empresa_id"])) == len(empresa["envios"]):
            return "completa"
        # A carga anterior parou no meio desta empresa
        return "incompleta"
    # O CNPJ não está na carteira: a empresa ainda não foi carregada
    return None


def _cadastrar_a_empresa(conexao, empresa: dict, usuario_do_banco: Usuario, dia_da_carga: date) -> str:
    """Cadastra a empresa como o especialista faria (a conferência do cadastro, o kit e os outros CNPJs). Devolve o id.

    O criado_por é a MARCA_DA_BASE_VIVA (é como a remoção a reconhece); o contrato começa `contrato_dias_uteis` dias
    úteis antes da carga, e o cadastro, 2 dias úteis antes do contrato.
    """
    # A hora real em que esta etapa começou (as linhas gravadas a partir dela ganham a data do roteiro)
    inicio_real = _agora_em_texto()
    # O dia em que o contrato começou
    contrato = gerar_base_viva.dia_util_antes(dia_da_carga, empresa["contrato_dias_uteis"])
    # Os dados que o especialista preenche na aba Empresas
    dados = {"nome": empresa["nome"], "setor": empresa["setor"], "municipio": empresa["municipio"],
             "uf": empresa["uf"], "cnpj": empresa["cnpj"], "endereco_comercial": empresa["endereco_comercial"],
             "dominio_email": empresa["dominio_email"], "contrato_desde": contrato.isoformat()}
    # Quem cadastra: a marca da carga, com o perfil do banco (a conferência do cadastro exige o perfil BANCO)
    usuario_da_carga = Usuario(login=MARCA_DA_BASE_VIVA, perfil=Perfil.BANCO, empresa_id=None)
    # O cadastro de sempre: confere o CNPJ, a UF e o domínio, e dá o próximo código (EMP007, EMP008...)
    empresa_id = empresas.cadastrar(conexao, usuario_da_carga, dados)["empresa_id"]
    # O kit de marca: o próprio da empresa vira a KB do kit dela, publicada (a KB é a fonte única do kit; publicar
    # leva o kit para o cadastro). O padrão não precisa de KB: a empresa já nasce no padrão. O índice do RAG não muda
    kit = empresa["kit"]
    if kit["escolhido"] == empresas.KIT_PROPRIO:
        kbs_publicacao.publicar_kit_novo(conexao, usuario_da_carga, empresa_id, kit["escolhido"], kit["texto"],
                                         kit["cores"], None, ORIGEM_DO_KIT, atualizar_indice=False)
    # Os outros CNPJs que o banco conhece: filiais e a empresa do grupo
    for extra in empresa["cnpjs_extras"]:
        empresas.adicionar_cnpj(conexao, usuario_do_banco, empresa_id, extra["cnpj"], extra["tipo"])
    # O cadastro aconteceu 2 dias úteis antes do contrato, às 10h de Brasília
    cadastro = datetime.combine(gerar_base_viva.dia_util_antes(contrato, 2), time(10, 0), tzinfo=FUSO_DE_BRASILIA)
    datar_a_etapa(conexao, empresa_id, inicio_real, cadastro.astimezone(timezone.utc))
    return empresa_id


# ================================ O mapeamento gravado pela carga ================================

def _plano_da_carga(processamento_id: str, versao: int, colunas: list, reaproveitado: bool) -> MappingPlan:
    """O mapeamento de um envio da base viva, sem IA: cada coluna ligada ao campo que o gerador usou.

    Recebe: o envio; a versão do parâmetro; as colunas [[cabeçalho, campo], ...]; reaproveitado — True quando as
    colunas são as mesmas de um envio da empresa já aprovado pelo banco (a origem é "reuso", como a aplicação faz).
    Devolve: o plano. A origem "regra" ou "reuso" não conta como proposta da IA na aceitação por agente
    (services/aceitacao_dos_agentes.py), e o modelo diz que não houve IA.
    """
    itens = []
    for cabecalho, campo in colunas:
        # A inclusão com as colunas de um envio já aprovado: o reuso, com a mesma justificativa da aplicação
        if reaproveitado:
            itens.append(ItemMapeamento(coluna=cabecalho, campo=campo, status=StatusMapeamento.PROPOSTO,
                                        justificativa=JUSTIFICATIVA_DO_REUSO, origem="reuso"))
        else:
            # A coluna ligada pela carga (a origem "regra": ninguém da IA propôs)
            itens.append(ItemMapeamento(coluna=cabecalho, campo=campo, status=StatusMapeamento.PROPOSTO,
                                        justificativa=JUSTIFICATIVA_DA_CARGA, origem="regra"))
    # O modelo do plano: "reuso" (como a aplicação escreve quando reaproveita) ou o da carga, sem IA
    modelo = "reuso" if reaproveitado else MODELO_DA_CARGA
    return MappingPlan(processamento_id=processamento_id, versao_layout=versao, configuracao=SEM_IA, modelo=modelo,
                       versao_prompt=SEM_IA, itens=itens, chamou_llm=False, observacoes=[])


def _gravar_o_plano(conexao, processamento_id: str, empresa_id: str, plano: MappingPlan) -> None:
    """Grava o mapeamento esperando o aceite da empresa, como a leitura das colunas grava (mapeamentos.py).

    Deixa o envio "Esperando você conferir as colunas" e registra na trilha o evento MAPEAMENTO_PROPOSTO, que marca a
    etapa "Lido pela IA" da linha do tempo; o detalhe diz o modelo "base viva (sem IA)" e que a IA não foi chamada.
    """
    # Garante que a tabela dos mapeamentos existe
    mapeamentos._preparar(conexao)
    # O plano, ainda PENDENTE (esperando o aceite), como o services/mapeamentos.py grava
    conexao.execute("INSERT INTO mapeamentos (processamento_id, empresa_id, status, plano, criado_em, aprovado_por, "
                    "aprovado_em) VALUES (?, ?, 'PENDENTE', ?, ?, NULL, NULL)",
                    (processamento_id, empresa_id, plano.model_dump_json(), _agora_em_texto()))
    conexao.commit()
    # O envio fica esperando a empresa conferir as colunas
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.MAPEAMENTO_PENDENTE)
    # A trilha: as colunas foram lidas (sem a IA), com as mesmas chaves do detalhe da aplicação
    auditoria.registrar(conexao, processamento_id, empresa_id, "Interpretação", "MAPEAMENTO_PROPOSTO", {
        "configuracao": plano.configuracao, "modelo": plano.modelo, "versao_prompt": plano.versao_prompt,
        "chamou_llm": False, "colunas_reusadas": len(plano.itens) if plano.modelo == "reuso" else 0,
        "status": {"PROPOSTO": len(plano.itens), "AMBIGUO": 0, "NAO_MAPEADO": 0, "DIVIDIR": 0}, "observacoes": 0})


# ================================ O fluxo parado na etapa certa ================================

def parar_o_fluxo(conexao, processamento_id: str, empresa_id: str, etapa: str, versao: int, pendencias: dict,
                  decisoes: dict, recado: str | None = None) -> None:
    """Deixa o fluxo do envio (o ponto de salvamento do LangGraph) parado na etapa, sem rodar nenhuma etapa antes.

    Recebe: o envio e a empresa; etapa — a pausa (ETAPA_ANTERIOR_DA_PAUSA); a versão do parâmetro; a contagem das
    pendências; as decisões de coluna; recado — o último recado para a tela (ex.: o motivo da devolução).
    Faz: grava o estado como se a etapa anterior tivesse acabado de rodar e pede ao fluxo para seguir: a primeira
    coisa que a etapa de pausa faz é parar e esperar a pessoa (interrupt), antes de gravar qualquer execução. É o mesmo
    jeito de workflows/fluxo_empresa.comecar_na_correcao. Levanta CargaRecusada se o fluxo não parou onde devia.
    """
    # A etapa que "acabou de rodar" antes da pausa (a seta dela leva à pausa)
    anterior = ETAPA_ANTERIOR_DA_PAUSA[etapa]
    # A situação do envio agora (o estado do fluxo guarda a mesma)
    status = processamentos.obter(conexao, processamento_id).status.value
    # O estado do fluxo, com todas as chaves do EstadoDoFluxo; "proximo_passo" aponta a pausa
    estado = {"processamento_id": processamento_id, "empresa_id": empresa_id, "status": status, "configuracao": "B3",
              "versao_layout": versao, "pendencias": pendencias, "decisoes_de_coluna": dict(decisoes),
              "ciclos_de_correcao": 0, "handoffs": 0, "falhas": 0, "etapa_com_falha": None,
              "motivo_da_rejeicao": None, "ultimo_erro": recado, "proximo_passo": etapa}
    # O fluxo, com o ponto de salvamento do mesmo banco (no PostgreSQL, as tabelas checkpoint*)
    grafo = fluxo_empresa.construir(conexao)
    # A linha do tempo do fluxo deste envio
    configuracao = {"configurable": {"thread_id": processamento_id}}
    # Grava o estado como se a etapa anterior tivesse acabado agora...
    grafo.update_state(configuracao, estado, as_node=anterior)
    # ...e segue até a pausa, que para na hora e espera a pessoa
    grafo.invoke(None, configuracao)
    # Confere que parou onde devia
    parado_em = fluxo_empresa.situacao(conexao, processamento_id)["etapa_atual"]
    if parado_em != etapa:
        raise CargaRecusada(f"O fluxo do envio {processamento_id} parou em {parado_em}, e não em {etapa}.")


# ================================ Um envio, etapa por etapa ================================

def _receber(conexao, contexto: dict, envio: dict) -> str:
    """Recebe o arquivo (a leitura de sempre, sem IA: CSV e Excel não usam o Leitor) e grava o mapeamento.

    Devolve: o id do envio. A data de referência é o dia do recebimento, como a tela usa.
    """
    inicio_real = _agora_em_texto()
    # Quando o arquivo chegou, pelo roteiro
    recebido = momento_real(envio["linha_do_tempo"]["recebido"], contexto["dia_da_carga"])
    # O arquivo gerado, como a empresa mandou
    conteudo = (contexto["pasta"] / envio["arquivo"]).read_bytes()
    # O recebimento de sempre: lê, retrata, guarda o original e registra o envio (a data de referência é a do dia)
    recebimento = processamentos.receber_arquivo(conexao, conteudo, envio["nome_do_arquivo"], contexto["empresa_id"],
                                                 recebido.astimezone(FUSO_DE_BRASILIA).date(), contexto["login"])
    # O mesmo arquivo já enviado: a base viva nunca manda um arquivo duas vezes
    if recebimento.duplicado:
        raise CargaRecusada(f"O arquivo {envio['nome_do_arquivo']} já tinha sido enviado por esta empresa.")
    processamento_id = recebimento.perfil.processamento_id
    # As inclusões reaproveitam as colunas do envio já aprovado (a mesma exportação do mesmo sistema de RH)
    reaproveitado = envio["tipo"] == "INCLUSAO" and contexto["tem_envio_aprovado"]
    # O mapeamento pronto, sem IA, esperando o aceite
    plano = _plano_da_carga(processamento_id, contexto["versao"], envio["colunas"], reaproveitado)
    _gravar_o_plano(conexao, processamento_id, contexto["empresa_id"], plano)
    datar_a_etapa(conexao, contexto["empresa_id"], inicio_real, recebido)
    return processamento_id


def _aceitar_e_validar(conexao, contexto: dict, envio: dict, processamento_id: str) -> None:
    """A empresa confere as colunas e aceita; a padronização e a validação rodam (as regras de sempre, sem IA)."""
    inicio_real = _agora_em_texto()
    # O aceite das colunas, sem mudar nenhuma (as escolhas vazias: fica o que o plano diz)
    mapeamentos.aprovar(conexao, processamento_id, contexto["empresa_id"], {}, contexto["login"])
    # A padronização, com as decisões de formato das colunas de data (o dia vem antes do mês)
    normalizador.executar(conexao, processamento_id, contexto["empresa_id"], envio["decisoes_de_coluna"])
    # A validação: as regras do Validador e as da profissão (CBO)
    validador.executar(conexao, processamento_id, contexto["empresa_id"])
    datar_a_etapa(conexao, contexto["empresa_id"], inicio_real,
                  momento_real(envio["linha_do_tempo"]["aceite"], contexto["dia_da_carga"]))


def _corrigir(conexao, contexto: dict, envio: dict, processamento_id: str) -> None:
    """A empresa corrige os erros de digitação, tira a linha repetida e confirma os alertas que sobraram.

    Cada correção acontece 2 minutos depois da anterior, a partir do momento "correcoes" do roteiro (ou, sem ele, 15
    minutos depois do aceite). Levanta CargaRecusada se sobrar uma pendência que bloqueia (o gerador errou).
    """
    empresa_id, login = contexto["empresa_id"], contexto["login"]
    linha_do_tempo = envio["linha_do_tempo"]
    # Quando a empresa começou a corrigir: o momento do roteiro, ou 15 minutos depois do aceite
    if "correcoes" in linha_do_tempo:
        momento = momento_real(linha_do_tempo["correcoes"], contexto["dia_da_carga"])
    else:
        momento = _mais(momento_real(linha_do_tempo["aceite"], contexto["dia_da_carga"]), 15 * 60)
    for correcao in envio["correcoes"]:
        inicio_real = _agora_em_texto()
        # A correção de sempre: o pedido (o valor passa pelas regras da padronização) e o clique que aplica
        pedido = correcoes.propor(conexao, processamento_id, empresa_id, correcao["linha"], correcao["campo"],
                                  correcao["valor"], correcao["motivo"], login)
        correcoes.decidir(conexao, processamento_id, empresa_id, pedido.correcao_id, True, login)
        datar_a_etapa(conexao, empresa_id, inicio_real, momento)
        # A próxima correção, 2 minutos depois
        momento = _mais(momento, 120)
    for exclusao in envio["exclusoes"]:
        inicio_real = _agora_em_texto()
        # A pessoa repetida no arquivo: a empresa tira a segunda linha (a exclusão também é uma correção)
        pedido = correcoes.propor(conexao, processamento_id, empresa_id, exclusao["linha"], correcoes.EXCLUIR, None,
                                  exclusao["motivo"], login)
        correcoes.decidir(conexao, processamento_id, empresa_id, pedido.correcao_id, True, login)
        datar_a_etapa(conexao, empresa_id, inicio_real, momento)
        momento = _mais(momento, 120)
    _confirmar_os_alertas(conexao, contexto, processamento_id, momento)


def _confirmar_os_alertas(conexao, contexto: dict, processamento_id: str, momento: datetime) -> None:
    """A empresa confirma cada alerta que sobrou (com a justificativa da regra) e o envio fica sem pendência."""
    relatorio = validador.obter(conexao, processamento_id)
    for achado in relatorio.achados:
        # Só os alertas ainda em aberto (o bloqueante não se confirma: se corrige)
        if achado.severidade != validador.ALERTA or achado.resolvido:
            continue
        inicio_real = _agora_em_texto()
        # A justificativa da regra (ex.: "Salário conferido com o contrato de trabalho.")
        justificativa = JUSTIFICATIVAS_DOS_ALERTAS.get(achado.regra_id, JUSTIFICATIVA_PADRAO)
        # A confirmação de sempre, que valida de novo
        validador.justificar_alerta(conexao, processamento_id, contexto["empresa_id"], achado.regra_id, achado.linha,
                                    "CONFIRMADO", justificativa, contexto["login"])
        datar_a_etapa(conexao, contexto["empresa_id"], inicio_real, momento)
        momento = _mais(momento, 60)
    # Depois das correções e confirmações, o envio precisa estar sem pendência
    relatorio = validador.obter(conexao, processamento_id)
    if not relatorio.pronto_para_homologar:
        pendentes = []
        for achado in relatorio.achados:
            if achado.severidade == validador.BLOQUEANTE:
                pendentes.append(f"{achado.regra_id} na linha {achado.linha}")
        raise CargaRecusada(f"O envio {processamento_id} ficou com pendência que bloqueia: {', '.join(pendentes)}.")


def _enviar_ao_banco(conexao, contexto: dict, envio: dict, processamento_id: str) -> None:
    """A empresa marca "Conferi a lista" e envia ao banco (o mesmo que a etapa aprovar_homologacao do fluxo faz)."""
    inicio_real = _agora_em_texto()
    empresa_id, login = contexto["empresa_id"], contexto["login"]
    # A pessoa marcou "Conferi a lista" na tela (o banco vê na trilha)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Conferência", "LISTA_CONFERIDA",
                        {"conferida_por": login})
    # Confere de novo, sobre os dados atuais, que não sobrou pendência
    homologacao.conferir_antes_do_envio(conexao, processamento_id, empresa_id)
    # O envio vai para a avaliação do banco
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.AGUARDANDO_BANCO)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Homologação", "ENVIADO_AO_BANCO",
                        {"enviado_por": login})
    # Tudo isso meio minuto antes do momento do envio no roteiro
    enviado = momento_real(envio["linha_do_tempo"]["enviado"], contexto["dia_da_carga"])
    datar_a_etapa(conexao, empresa_id, inicio_real, _mais(enviado, -30))


def _devolver(conexao, contexto: dict, envio: dict, processamento_id: str) -> None:
    """O especialista devolve o envio inteiro com o motivo (o que a etapa avaliar_no_banco do fluxo grava)."""
    inicio_real = _agora_em_texto()
    # O envio volta para a empresa
    processamentos.atualizar_status(conexao, processamento_id, EstadoProcessamento.DEVOLVIDO)
    # A trilha guarda o motivo (o recado que a empresa lê) e quem devolveu
    auditoria.registrar(conexao, processamento_id, contexto["empresa_id"], "Avaliação do banco",
                        "DEVOLVIDO_PELO_BANCO", {"motivo": envio["motivo_da_devolucao"][:500],
                                                 "avaliado_por": contexto["usuario_do_banco"].login})
    datar_a_etapa(conexao, contexto["empresa_id"], inicio_real,
                  momento_real(envio["linha_do_tempo"]["decisao"], contexto["dia_da_carga"]))


def _aprovar(conexao, contexto: dict, envio: dict, processamento_id: str) -> None:
    """O especialista aprova: o cadastro (homologação), o planejamento e a trilha, como o fluxo faria, sem a IA.

    A homologação de sempre grava o arquivo final, os funcionários (com as informações sem rótulo, se houver) e os
    pares no histórico de mapeamentos. Os pares são apagados na hora: o histórico é o conhecimento da IA e a base viva
    não o toca (o aprendizado do RAG está desligado nesta carga, então o índice não muda).
    """
    inicio_real = _agora_em_texto()
    empresa_id, avaliado_por = contexto["empresa_id"], contexto["usuario_do_banco"].login
    # O cadastro: o arquivo final, os funcionários e o relatório de qualidade
    qualidade = homologacao.homologar(conexao, processamento_id, empresa_id, avaliado_por, set())
    # O histórico de mapeamentos que a homologação acabou de gravar sai: a base viva não ensina nada à IA
    conexao.execute("DELETE FROM historico_mapeamentos WHERE processamento_id = ?", (processamento_id,))
    conexao.commit()
    # A trilha da decisão do banco: quantas pessoas ele aprovou (e nenhuma devolvida)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Avaliação do banco", "APROVADO_PELO_BANCO",
                        {"avaliado_por": avaliado_por, "aprovadas": qualidade["registros_homologados"],
                         "devolvidas": 0})
    # O planejamento do banco passa a contar os cadastrados (só números, sem IA)
    contagem = motor_planejamento.processar_homologacao(conexao, processamento_id, empresa_id)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Planejamento", "PLANEJAMENTO_LIBERADO",
                        {"funcionarios_novos": contagem["novos"]})
    datar_a_etapa(conexao, empresa_id, inicio_real,
                  momento_real(envio["linha_do_tempo"]["decisao"], contexto["dia_da_carga"]))


def _carregar_um_envio(conexao, contexto: dict, envio: dict) -> str:
    """Leva um envio do recebimento até a etapa do roteiro ("destino") e deixa o fluxo parado ali. Devolve o id."""
    processamento_id = _receber(conexao, contexto, envio)
    destino = envio["destino"]
    # Parado no aceite das colunas: a empresa ainda não conferiu
    if destino == "NO_ACEITE":
        parar_o_fluxo(conexao, processamento_id, contexto["empresa_id"], "aprovar_mapeamento", contexto["versao"],
                      {}, {})
        return processamento_id
    _aceitar_e_validar(conexao, contexto, envio, processamento_id)
    relatorio = validador.obter(conexao, processamento_id)
    # Com pendências: os erros de digitação continuam lá, esperando a empresa
    if destino == "PENDENTE":
        parar_o_fluxo(conexao, processamento_id, contexto["empresa_id"], "aguardar_correcao", contexto["versao"],
                      relatorio.contagem(), envio["decisoes_de_coluna"])
        return processamento_id
    _corrigir(conexao, contexto, envio, processamento_id)
    # Pronto para enviar: sem pendência, espera o clique "Enviar ao banco"
    if destino == "PRONTO":
        parar_o_fluxo(conexao, processamento_id, contexto["empresa_id"], "aprovar_homologacao", contexto["versao"],
                      validador.obter(conexao, processamento_id).contagem(), envio["decisoes_de_coluna"])
        return processamento_id
    _enviar_ao_banco(conexao, contexto, envio, processamento_id)
    contagem = validador.obter(conexao, processamento_id).contagem()
    # Em análise: espera o especialista do banco
    if destino == "EM_ANALISE":
        parar_o_fluxo(conexao, processamento_id, contexto["empresa_id"], "avaliar_no_banco", contexto["versao"],
                      contagem, envio["decisoes_de_coluna"])
        return processamento_id
    # Devolvido: volta para a correção, com o motivo como recado
    if destino == "DEVOLVIDO":
        _devolver(conexao, contexto, envio, processamento_id)
        parar_o_fluxo(conexao, processamento_id, contexto["empresa_id"], "aguardar_correcao", contexto["versao"],
                      contagem, envio["decisoes_de_coluna"], "Devolvido pelo banco: " + envio["motivo_da_devolucao"])
        return processamento_id
    # Cadastrado: o banco aprovou (o fluxo terminou; sem ponto de salvamento, a situação vem do próprio envio)
    _aprovar(conexao, contexto, envio, processamento_id)
    contexto["tem_envio_aprovado"] = True
    # O arquivo de contas do banco, se já chegou
    if envio["contas"] is not None:
        _dar_baixa_nas_contas(conexao, contexto, envio)
    return processamento_id


# ================================ As contas abertas ================================

def _conteudo_das_contas(envio: dict, contexto: dict) -> bytes:
    """O arquivo de contas que o banco devolveu, no layout fixo (services/contas_abertas.py).

    Desde o ADR-149, o arquivo é "cpf;status;agencia;conta;data_abertura", com a data em AAAA-MM-DD. A
    linha é montada pelo nome de cada coluna do layout: se o layout mudar, o arquivo acompanha.
    A data de abertura da nova conta fica entre o dia da aprovação e o dia em que o arquivo chegou (a do correntista
    é a da conta antiga, que o gerador sorteou). Exemplo de linha: "52998224725;1;1234;56789-0;2026-09-22".
    """
    # O dia da aprovação e o dia em que o arquivo chegou, no horário de Brasília
    aprovacao = momento_real(envio["linha_do_tempo"]["decisao"], contexto["dia_da_carga"]).astimezone(FUSO_DE_BRASILIA)
    chegada = momento_real(envio["contas"]["momento"], contexto["dia_da_carga"]).astimezone(FUSO_DE_BRASILIA)
    texto = io.StringIO()
    # O layout fixo: ponto e vírgula e o cabeçalho exato que a conferência exige
    escritor = csv.writer(texto, delimiter=contas_abertas.SEPARADOR_DE_COLUNAS, lineterminator="\n")
    escritor.writerow(contas_abertas.NOMES_DAS_COLUNAS)
    for posicao, conta in enumerate(envio["contas"]["pessoas"]):
        if conta["data_abertura"] is None:
            # A nova conta: um dia entre a aprovação e a chegada do arquivo (sempre no passado)
            dias_no_intervalo = max(0, (chegada.date() - aprovacao.date()).days)
            abertura = aprovacao.date() + timedelta(days=posicao % (dias_no_intervalo + 1))
        else:
            # O correntista: a data da conta antiga, que o gerador escreveu como DD/MM/AAAA
            abertura = datetime.strptime(conta["data_abertura"], "%d/%m/%Y").date()
        # O valor de cada coluna do layout, pelo nome dela (a data no formato do arquivo: AAAA-MM-DD)
        valores = {"cpf": conta["cpf"], "status": conta["tipo"], "agencia": conta["agencia"], "conta": conta["conta"],
                   "data_abertura": abertura.isoformat()}
        # Uma linha por pessoa, na ordem das colunas do layout
        linha = []
        for nome_da_coluna in contas_abertas.NOMES_DAS_COLUNAS:
            linha.append(valores[nome_da_coluna])
        escritor.writerow(linha)
    return texto.getvalue().encode("utf-8")


def _dar_baixa_nas_contas(conexao, contexto: dict, envio: dict) -> None:
    """O especialista sobe o arquivo de contas da empresa e confirma a baixa (a conferência de sempre).

    Levanta CargaRecusada se a conferência achar divergência (o arquivo inteiro seria recusado).
    """
    inicio_real = _agora_em_texto()
    usuario_do_banco = contexto["usuario_do_banco"]
    # A conferência de sempre: o layout, os CPFs cadastrados nesta empresa e as contas já gravadas
    previa = contas_abertas.conferir_arquivo(conexao, usuario_do_banco, contexto["empresa_id"],
                                             _conteudo_das_contas(envio, contexto), envio["contas"]["nome_do_arquivo"])
    # Com qualquer divergência, o arquivo seria recusado: a carga para (o gerador errou)
    if not previa["pode_importar"]:
        raise CargaRecusada(f"O arquivo de contas {envio['contas']['nome_do_arquivo']} teve divergências: "
                            f"{json.dumps(previa['divergencias_por_tipo'], ensure_ascii=False)}.")
    # "Confirmar a baixa": as contas entram na tabela
    contas_abertas.confirmar_baixa(conexao, usuario_do_banco, previa["arquivo_id"])
    datar_a_etapa(conexao, contexto["empresa_id"], inicio_real,
                  momento_real(envio["contas"]["momento"], contexto["dia_da_carga"]))


# ================================ Os acessos e as conversas ================================

def _acessos_ao_portal(conexao, contexto: dict, empresa: dict) -> None:
    """As entradas do RH no portal: uma sessão por acesso, já vencida e encerrada (ninguém consegue usá-la).

    A sessão é criada pela função de sempre, com a hora do roteiro (services/sessoes.criar_sessao aceita "agora"): ela
    vence 8 horas depois, no passado. O ingresso sorteado nunca é guardado: só o hash dele vai para o banco.
    """
    for acesso in empresa["acessos"]:
        # A sessão, na hora do acesso (vence 8 horas depois, no passado)
        ingresso = sessoes.criar_sessao(conexao, contexto["login"], momento_real(acesso, contexto["dia_da_carga"]))
        # E já encerrada, como quem clicou em "Sair"
        sessoes.encerrar_sessao(conexao, ingresso)


def _acessos_aos_dados(conexao, contexto: dict, empresa: dict) -> None:
    """As aberturas da lista de funcionários e os downloads do RH (o registro de acesso a dados pessoais)."""
    for acesso in empresa["acessos_aos_dados"]:
        inicio_real = _agora_em_texto()
        # A lista aberta na tela ou baixada, com quantas pessoas ela mostrava
        tipo = acompanhamento.ACESSO_LISTA if acesso["tipo"] == "LISTA" else acompanhamento.ACESSO_DOWNLOAD
        acompanhamento.registrar_acesso(conexao, contexto["empresa_id"], contexto["login"], tipo, acesso["quantidade"])
        datar_a_etapa(conexao, contexto["empresa_id"], inicio_real, momento_real(acesso, contexto["dia_da_carga"]))


def _conversa_com_o_banco(conexao, contexto: dict, empresa: dict) -> None:
    """As mensagens do "Posso ajudar?" entre o RH e o especialista, na ordem, e a marca de resolvida."""
    conversa = empresa["conversa"]
    # A empresa não escreveu para o banco
    if conversa is None:
        return
    # O RH da empresa, para as mensagens do lado dela
    usuario_da_empresa = Usuario(login=contexto["login"], perfil=Perfil.EMPRESA, empresa_id=contexto["empresa_id"])
    momento = None
    for mensagem in conversa["mensagens"]:
        inicio_real = _agora_em_texto()
        # Quem escreveu: o RH ou o especialista
        autor = usuario_da_empresa if mensagem["de"] == "EMPRESA" else contexto["usuario_do_banco"]
        mensagens.mandar_mensagem(conexao, autor, mensagem["texto"], mensagem["contexto"], contexto["empresa_id"])
        momento = momento_real(mensagem, contexto["dia_da_carga"])
        datar_a_etapa(conexao, contexto["empresa_id"], inicio_real, momento)
    # O banco marcou a conversa como resolvida, 20 minutos depois da última mensagem
    if conversa["resolvida"]:
        inicio_real = _agora_em_texto()
        mensagens.marcar_resolvida(conexao, contexto["usuario_do_banco"], contexto["empresa_id"])
        datar_a_etapa(conexao, contexto["empresa_id"], inicio_real, _mais(momento, 20 * 60))


# ================================ A carga inteira ================================

def conferir_o_parametro(conexao) -> int:
    """Confere que o parâmetro vigente é o da base viva (os 4 obrigatórios da v7, com o codigo_cbo). Devolve a versão.

    Levanta CargaRecusada com o motivo, se não for.
    """
    versao, campos = parametros.layout_ativo(conexao)
    # Os campos obrigatórios do parâmetro vigente
    obrigatorios = set()
    for campo in campos:
        if campo.obrigatorio:
            obrigatorios.add(campo.campo)
    # Outros obrigatórios mudariam as pendências de todos os envios: a base viva não carrega
    if obrigatorios != OBRIGATORIOS_DA_V7:
        raise CargaRecusada(f"A base viva segue o parâmetro com os 4 obrigatórios (ADR-143); o vigente (v{versao}) "
                            f"tem: {', '.join(sorted(obrigatorios))}.")
    return versao


def usuario_do_banco(conexao) -> Usuario:
    """O especialista do banco que aparece nas decisões e nas contas (o primeiro login ativo do perfil BANCO)."""
    for usuario in auth.listar_usuarios(conexao):
        if usuario.perfil == Perfil.BANCO and usuario.ativo:
            return usuario
    # Sem ninguém do banco, ninguém poderia avaliar os envios
    raise CargaRecusada("O banco de dados não tem nenhum login ativo do perfil BANCO (rode scripts/criar_usuarios.py).")


def carregar_empresa(conexao, empresa: dict, pasta: Path, senha: str, dia_da_carga: date, versao: int,
                     codigo_do_banco: str) -> dict:
    """Carrega uma empresa inteira do roteiro. Devolve {empresa_id, envios, login}."""
    usuario_banco = usuario_do_banco(conexao)
    empresa_id = _cadastrar_a_empresa(conexao, empresa, usuario_banco, dia_da_carga)
    # O login do RH: a senha única da base viva, definitiva (não pede troca no primeiro acesso)
    auth.cadastrar_usuario(conexao, empresa["login"], senha, Perfil.EMPRESA, empresa_id, senha_provisoria=False)
    # O que as etapas dos envios precisam saber da empresa
    contexto = {"empresa_id": empresa_id, "login": empresa["login"], "pasta": pasta, "dia_da_carga": dia_da_carga,
                "versao": versao, "usuario_do_banco": usuario_banco, "tem_envio_aprovado": False,
                "codigo_do_banco": codigo_do_banco}
    # Os envios, do mais antigo ao mais recente
    envios = []
    for envio in empresa["envios"]:
        envios.append(_carregar_um_envio(conexao, contexto, envio))
    # O uso do portal: as entradas, as aberturas da lista e a conversa com o banco
    _acessos_ao_portal(conexao, contexto, empresa)
    _acessos_aos_dados(conexao, contexto, empresa)
    _conversa_com_o_banco(conexao, contexto, empresa)
    return {"empresa_id": empresa_id, "envios": envios, "login": empresa["login"]}


def _execucoes_de_agentes(conexao) -> int:
    """Quantas execuções de agentes o banco tem (a carga não pode mudar este número)."""
    # A tabela ainda não existe (ninguém usou a IA neste banco): nenhuma execução
    if not banco.colunas_da_tabela(conexao, "execucoes_agentes"):
        return 0
    return conexao.execute("SELECT COUNT(*) FROM execucoes_agentes").fetchone()[0]


def carregar(conexao, pasta: Path, senha: str, dia_da_carga: date | None = None, tambem_logins_da_demo: bool = False,
             escrever=print) -> dict:
    """Carrega a base viva do roteiro da pasta. Devolve o resumo: empresas carregadas, puladas e logins da demo.

    Recebe: conexao; pasta (com o roteiro.json e os arquivos); senha (a do segredo; nunca é escrita); dia_da_carga (o
    dia de hoje em Brasília; os testes informam); tambem_logins_da_demo — True põe a mesma senha nos logins da demo;
    escrever — para onde vão as linhas de andamento (nenhuma leva a senha).
    Levanta CargaRecusada com o motivo, antes de gravar qualquer coisa, se algo impede a carga.
    """
    roteiro = json.loads((Path(pasta) / gerar_base_viva.NOME_DO_ROTEIRO).read_text(encoding="utf-8"))
    # O roteiro de outra versão do gerador pode ter outro formato
    if roteiro["versao"] != gerar_base_viva.VERSAO_DO_ROTEIRO:
        raise CargaRecusada("O roteiro é de outra versão do gerador: gere de novo (scripts/gerar_base_viva.py).")
    # Sem a senha, nenhum login do RH funcionaria
    if not senha:
        raise CargaRecusada(f"Falta o segredo {NOME_DO_SEGREDO_DA_SENHA} no .env (quem administra o ambiente põe; "
                            "a senha nunca é escrita no código).")
    # O aprendizado ligado (dentro da API) mexeria no índice do RAG a cada aprovação
    if busca.mapeamentos_aprovados_ligados():
        raise CargaRecusada("O aprendizado do RAG está ligado: a carga não pode mexer no índice (rode fora da API).")
    # O dia da carga: hoje, no horário de Brasília
    dia_da_carga = dia_da_carga or datetime.now(FUSO_DE_BRASILIA).date()
    versao = conferir_o_parametro(conexao)
    usuario_do_banco(conexao)
    # As execuções de agentes antes da carga (depois, o número tem de ser o mesmo)
    execucoes_antes = _execucoes_de_agentes(conexao)
    # Primeiro confere todas as empresas (nenhuma pela metade, nenhum CNPJ de outra empresa), depois carrega
    situacoes = {}
    for empresa in roteiro["empresas"]:
        situacoes[empresa["chave"]] = _situacao_da_empresa(conexao, empresa)
        if situacoes[empresa["chave"]] == "incompleta":
            raise CargaRecusada(f"A empresa {empresa['nome']} ficou pela metade numa carga anterior: rode com "
                                "--remover e carregue de novo.")
    carregadas, puladas = [], []
    for empresa in roteiro["empresas"]:
        # A empresa que já está completa no banco é pulada (a carga roda de novo sem duplicar)
        if situacoes[empresa["chave"]] == "completa":
            puladas.append(empresa["nome"])
            continue
        escrever(f"Carregando {empresa['nome']} ({len(empresa['envios'])} envios)...")
        carregadas.append(carregar_empresa(conexao, empresa, Path(pasta), senha, dia_da_carga, versao,
                                           roteiro["codigo_do_banco"]))
    # A mesma senha nos logins da demo, só com a opção
    logins_da_demo = []
    if tambem_logins_da_demo:
        logins_da_demo = senha_nos_logins_da_demo(conexao, senha)
    # A prova de que a carga não usou a IA: nenhuma execução de agente a mais
    if _execucoes_de_agentes(conexao) != execucoes_antes:
        raise CargaRecusada("A carga gravou execuções de agentes: isso não pode acontecer (confira o código).")
    # As telas leem a lista de empresas nova na próxima consulta
    empresas.esquecer_lista_em_memoria()
    return {"carregadas": carregadas, "puladas": puladas, "logins_da_demo": logins_da_demo}


def senha_nos_logins_da_demo(conexao, senha: str) -> list[str]:
    """Põe a senha única da base viva nos logins da demo que existem (o do banco e o da Aurora). Devolve os logins.

    A senha fica definitiva, e as sessões abertas desses logins são encerradas (quem estava dentro entra de novo).
    """
    # Os logins que existem neste banco
    existentes = set()
    for usuario in auth.listar_usuarios(conexao):
        existentes.add(usuario.login)
    mudados = []
    for login, _variavel, _perfil, _empresa in USUARIOS_DEMO:
        # O login da demo que não existe neste banco fica de fora (não é criado aqui)
        if login not in existentes:
            continue
        # A senha nova, definitiva, e as sessões abertas encerradas
        auth.redefinir_senha(conexao, login, senha, senha_provisoria=False)
        sessoes.encerrar_sessoes_do_usuario(conexao, login)
        mudados.append(login)
    return mudados


# ================================ A remoção ================================

def _tabelas_do_banco(conexao) -> list[str]:
    """As tabelas do banco da aplicação (no SQLite e no PostgreSQL), sem as visões."""
    nomes = []
    # Cada banco lista as tabelas de um jeito
    if banco.e_postgres(conexao):
        consulta = conexao.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = "
                                   "current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name")
    else:
        consulta = conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                                   "ORDER BY name")
    for (nome,) in consulta:
        nomes.append(nome)
    return nomes


def remover(conexao) -> dict:
    """Tira só a base viva: as empresas criadas por esta carga e tudo o que é delas. Devolve {tabela: linhas apagadas}.

    Em cada tabela do banco com a coluna empresa_id, apaga as linhas dessas empresas; nas que só têm o
    processamento_id, as linhas dos envios delas; nas KBs e nos achados da trava (o dono é o código da empresa), as
    delas, e os logos das versões dessas KBs; nas sessões e nas tentativas de login, as dos logins delas. Apaga
    também o fluxo de cada envio (o ponto de salvamento) e os arquivos guardados (o original e o final). As outras
    empresas, os outros usuários e o conhecimento da IA não são tocados.
    """
    # As empresas da base viva (as da marca da carga)
    ids = []
    for empresa in empresas_da_base_viva(conexao):
        ids.append(empresa["empresa_id"])
    # Nada carregado: nada a remover
    if not ids:
        return {}
    # Os envios e os logins dessas empresas
    envios, logins = [], []
    for empresa_id in ids:
        envios.extend(_envios_da_empresa(conexao, empresa_id))
    for usuario in auth.listar_usuarios(conexao):
        if usuario.empresa_id in ids:
            logins.append(usuario.login)
    # As KBs dessas empresas (o kit da marca que a carga publica), lidas antes: os logos das versões são achados por elas
    kbs = _kbs_das_empresas(conexao, ids)
    apagadas = {}
    for tabela in _tabelas_do_banco(conexao):
        colunas = banco.colunas_da_tabela(conexao, tabela)
        # A tabela com a empresa: as linhas das empresas da base viva
        if "empresa_id" in colunas:
            apagadas[tabela] = _apagar(conexao, tabela, "empresa_id", ids)
        # A tabela só com o envio: as linhas dos envios delas
        elif "processamento_id" in colunas and envios:
            apagadas[tabela] = _apagar(conexao, tabela, "processamento_id", envios)
        # As KBs e os achados da trava: o dono é o código da empresa
        elif "dono" in colunas:
            apagadas[tabela] = _apagar(conexao, tabela, "dono", ids)
        # Os logos das versões das KBs dessas empresas
        elif "kb_id" in colunas and kbs:
            apagadas[tabela] = _apagar(conexao, tabela, "kb_id", kbs)
        # As sessões e as tentativas de login: as dos logins delas
        elif tabela in ("sessoes", "tentativas_de_login") and logins and "login" in colunas:
            apagadas[tabela] = _apagar(conexao, tabela, "login", logins)
    conexao.commit()
    _apagar_os_fluxos_e_os_arquivos(conexao, envios)
    # As telas deixam de ver as empresas removidas na próxima consulta
    empresas.esquecer_lista_em_memoria()
    return apagadas


def _kbs_das_empresas(conexao, ids: list[str]) -> list[str]:
    """Os ids das KBs cujo dono é uma das empresas (vazio se a tabela das KBs ainda não existe neste banco)."""
    # A tabela das KBs ainda não foi criada: nenhuma KB
    if not banco.colunas_da_tabela(conexao, "kbs_endomarketing"):
        return []
    kbs = []
    # Um id por KB (cada KB tem várias versões)
    for (kb_id,) in conexao.execute(f"SELECT DISTINCT kb_id FROM kbs_endomarketing WHERE dono IN "
                                    f"({_marcadores(len(ids))})", tuple(ids)):
        kbs.append(kb_id)
    return kbs


def _apagar(conexao, tabela: str, coluna: str, valores: list[str]) -> int:
    """Apaga as linhas da tabela em que a coluna tem um dos valores. Devolve quantas apagou."""
    cursor = conexao.execute(f"DELETE FROM {tabela} WHERE {coluna} IN ({_marcadores(len(valores))})", tuple(valores))
    return cursor.rowcount


def _apagar_os_fluxos_e_os_arquivos(conexao, envios: list[str]) -> None:
    """Apaga o ponto de salvamento do fluxo de cada envio e os arquivos guardados dele (o original e o final)."""
    # O ponto de salvamento do mesmo banco (no PostgreSQL, as tabelas checkpoint*; no SQLite, o arquivo próprio)
    ponto_de_salvamento = fluxo_empresa.abrir_checkpointer(conexao)
    for processamento_id in envios:
        # A linha do tempo do fluxo deste envio
        ponto_de_salvamento.delete_thread(processamento_id)
        # O original e a leitura guardada ao lado dele (ex.: abc123.csv e abc123.leitura.json)
        for arquivo in processamentos.config.PASTA_UPLOADS.glob(processamento_id + ".*"):
            arquivo.unlink()
        # O arquivo final do cadastro, se houver
        arquivo_final = homologacao.PASTA_HOMOLOGADOS / f"{processamento_id}.csv"
        if arquivo_final.exists():
            arquivo_final.unlink()


# ================================ Linha de comando ================================

def main() -> None:
    """Lê as opções, abre o banco do .env e carrega (ou remove) a base viva. Nunca escreve a senha."""
    leitor = argparse.ArgumentParser(description="Carrega a base viva (17 empresas) no banco da aplicação, sem IA.")
    leitor.add_argument("--remover", action="store_true", help="tira só a base viva do banco")
    leitor.add_argument("--tambem-logins-da-demo", action="store_true",
                        help="põe a mesma senha nos logins da demo (o do banco e o da Aurora)")
    leitor.add_argument("--pasta", default=str(gerar_base_viva.PASTA_DA_BASE_VIVA), help="a pasta da base viva")
    opcoes = leitor.parse_args()
    # O banco do .env (SQLite ou PostgreSQL)
    conexao = banco.conectar()
    print("Banco:", "PostgreSQL" if banco.e_postgres(conexao) else "SQLite", "| modo da IA:",
          processamentos.config.MODO)
    try:
        if opcoes.remover:
            apagadas = remover(conexao)
            print("Base viva removida:", json.dumps(apagadas, ensure_ascii=False))
            return
        # A senha só é lida do segredo, e nunca é escrita
        senha = os.environ.get(NOME_DO_SEGREDO_DA_SENHA, "")
        resumo = carregar(conexao, Path(opcoes.pasta), senha, tambem_logins_da_demo=opcoes.tambem_logins_da_demo)
        print(f"Carregadas: {len(resumo['carregadas'])} empresas; puladas (já estavam): {len(resumo['puladas'])}.")
        if resumo["logins_da_demo"]:
            print("Logins da demo com a senha da base viva:", ", ".join(resumo["logins_da_demo"]))
    except CargaRecusada as motivo:
        # O motivo, sem a senha; a saída 1 avisa quem chamou que a carga não terminou
        print("A carga parou:", motivo)
        sys.exit(1)
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
