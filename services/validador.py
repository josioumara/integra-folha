"""Validador: separa erro objetivo de alerta que precisa de contexto (ADR-13, ADR-14).

Quem decide é sempre uma REGRA, com identificador (`regra_id`) e severidade:
- BLOQUEANTE: impede a homologação até ser corrigido (ex.: CPF inválido, obrigatório vazio);
- ALERTA: precisa de correção ou justificativa (ex.: renda muito fora do padrão do cargo);
- AVISO: informativo (ex.: a pessoa já cadastrada, que fica de fora do envio).

Só os campos obrigatórios do parâmetro vigente pedem correção: o achado de um campo opcional sai do relatório
(ADR-143). Ex.: um e-mail com formato estranho, num campo opcional, não vira pendência. A exceção é o pedido explícito
do especialista do banco (PEDIDO_DO_BANCO): ele vale em qualquer campo, porque foi uma pessoa que pediu.
Renda fora do padrão é ALERTA, nunca acusação: pode ser erro de digitação, pode ser um diretor novo.
O LLM só EXPLICA o relatório em linguagem simples; não muda nenhuma severidade.
"""
import csv
import json
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from models.contratos import CampoLayout, EstadoProcessamento, TipoCampo
from services import apontamentos_do_banco, auditoria, empresas, formatacao, parametros, processamentos
from services.documentos import cnpj_valido, cpf_valido
from services import faixa_salarial_cbo
from services.normalizador import Normalizacao

# Pasta raiz do projeto (para achar os dados de referência e os prompts)
RAIZ = Path(__file__).resolve().parent.parent
# As três severidades
BLOQUEANTE, ALERTA, AVISO = "BLOQUEANTE", "ALERTA", "AVISO"
# Abaixo deste número de colegas no cargo, a renda é comparada com a tabela de referência do cargo
MINIMO_DE_COLEGAS = 5
# Distância máxima da mediana, em "desvios robustos" (MAD × 1,4826); acima disso, é alerta
LIMITE_Z_ROBUSTO = Decimal("3.5")
# Fator que torna o MAD comparável ao desvio-padrão
FATOR_DO_MAD = Decimal("1.4826")
# As resoluções que a empresa pode dar a um alerta
RESOLUCOES_DE_JUSTIFICATIVA = ("CONFIRMADO", "SUSPEITO")
# O valor que o sistema não conseguiu entender (fora da lista, data que não existe...): não se confirma
REGRA_VALOR_NAO_CONVERTIDO = "VALOR_NAO_CONVERTIDO"
# A empresa desfez a confirmação de um alerta (pendências por conversa): o alerta volta a ficar em aberto
REABERTO = "REABERTO"
RESOLUCOES_VALIDAS = ("ERRO_CORRIGIDO", "CONFIRMADO", "SUSPEITO", REABERTO)

# A regra do CNPJ repetido que não está no cadastro (ADR-77): a empresa confirma que é do grupo, e ele entra no cadastro
REGRA_CNPJ_DO_GRUPO = "CNPJ_DO_GRUPO_A_CONFIRMAR"
# O valor fora do mínimo ou do máximo que o parâmetro do layout define para o campo (ADR-128): é ALERTA
REGRA_VALOR_FORA_DA_FAIXA = "VALOR_FORA_DA_FAIXA"

@dataclass
class Achado:
    """Uma pendência encontrada por uma regra."""

    regra_id: str                   # qual regra achou (ex.: CPF_INVALIDO)
    severidade: str                 # BLOQUEANTE, ALERTA ou AVISO
    mensagem: str                   # o problema, em linguagem simples
    acao: str                       # o que a empresa deve fazer
    linha: int | None = None        # linha no arquivo, como a empresa vê no Excel
    registro: int | None = None     # posição do funcionário (1 = primeiro)
    campo: str | None = None
    valor: str | None = None        # o valor que a regra achou, como está no cadastro (ADR-101)
    resolvido: str | None = None    # alerta justificado pela empresa: CONFIRMADO ou SUSPEITO


@dataclass
class RelatorioValidacao:
    """Todos os achados de um arquivo."""

    achados: list[Achado] = field(default_factory=list)
    # Os valores inválidos de campo opcional, que ficam em branco (ADR-143): não são pendência e não ficam guardados no
    # relatório; executar grava cada um como o branco do sistema (services/correcoes.py)
    valores_em_branco: list[Achado] = field(default_factory=list)

    def contagem(self) -> dict:
        """Pendências em aberto por severidade (alerta justificado não conta mais)."""
        contagem = {BLOQUEANTE: 0, ALERTA: 0, AVISO: 0}
        for achado in self.achados:
            if not achado.resolvido:
                contagem[achado.severidade] += 1
        return contagem

    @property
    def pronto_para_homologar(self) -> bool:
        """Sem nenhum BLOQUEANTE e com todo ALERTA justificado."""
        for achado in self.achados:
            if achado.severidade == BLOQUEANTE:
                return False
            if achado.severidade == ALERTA and not achado.resolvido:
                return False
        return True


# ---------------- Referências ----------------

def faixas_de_referencia() -> dict[tuple[str, str], dict]:
    """(cargo, tipo de renda) -> mediana, faixa mínima e faixa máxima da tabela de referência."""
    faixas = {}
    with open(RAIZ / "data" / "synthetic" / "faixas_referencia_cargo.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            faixas[(linha["cargo"], linha["tipo_renda"])] = {"mediana": Decimal(linha["mediana"]),
                                                             "faixa_minima": Decimal(linha["faixa_minima"]),
                                                             "faixa_maxima": Decimal(linha["faixa_maxima"])}
    return faixas


def cnpj_principal_do_arquivo(empresa_id: str) -> str | None:
    """O CNPJ principal da empresa no arquivo das empresas fictícias (quando a validação não recebe o cadastro).

    Recebe: empresa_id. Devolve: o CNPJ (14 dígitos) ou None, se a empresa não está no arquivo.
    Na aplicação, o Validador usa o cadastro do banco de dados (empresas.cnpjs_conhecidos, em executar); este arquivo
    é o substituto para quem chama validar sozinho (testes e avaliação).
    """
    with open(RAIZ / "data" / "synthetic" / "empresas.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha["empresa_id"] == empresa_id:
                return linha["cnpj"]
    return None


# ---------------- Regras ----------------

def validar(normalizacao: Normalizacao, campos: list[CampoLayout], empresa_id: str,
            homologados: list[dict] | None = None, referencia: date | None = None,
            perguntas_da_ia: list[dict] | None = None, outros_envios: dict[str, str] | None = None,
            cnpjs_da_empresa: dict | None = None, pedidos_do_banco: list[dict] | None = None,
            ja_enviados: dict[str, str] | None = None) -> RelatorioValidacao:
    """Aplica todas as regras. homologados: funcionários já homologados na empresa (inclusões).

    ja_enviados: {cpf: nome do arquivo} das pessoas em outros envios da empresa que já foram ao banco e esperam a
    análise dele; a linha delas fica de fora deste envio (envio parcial, ADR-126).

    pedidos_do_banco: os apontamentos do especialista que já foram para a empresa (services/apontamentos_do_banco.py,
    ADR-121); cada um vira uma pendência da pessoa, até ela corrigir o campo ou responder ao banco.

    perguntas_da_ia: as perguntas do Leitor de Documentos ainda em aberto ({linha, campo, pergunta}, ADR-73).
    outros_envios: {cpf: nome do arquivo} das pessoas que estão em OUTROS envios da empresa ainda não cadastrados
    (a lista pendente da empresa).
    cnpjs_da_empresa: {"principal", "registrados"} do cadastro da empresa (ADR-77); sem ele, vale o CNPJ principal do
    arquivo das empresas fictícias.
    """
    relatorio = RelatorioValidacao()
    # Sem o cadastro, só o CNPJ principal do arquivo (sem filiais nem grupo registrados)
    if cnpjs_da_empresa is None:
        cnpjs_da_empresa = {"principal": cnpj_principal_do_arquivo(empresa_id), "registrados": []}
    homologados = homologados or []
    # Os campos que têm coluna no arquivo
    campos_mapeados = set()
    for passo in normalizacao.plano:
        campos_mapeados.add(passo["campo"])
    # Campo sem coluna, mas preenchido por correção (ex.: "Preencher para todos"): conta como presente, e o valor
    # passa pelas mesmas regras (obrigatório, formato, CNPJ da empresa)
    for registro in normalizacao.registros:
        for campo in campos:
            if registro.get(campo.campo) not in (None, ""):
                campos_mapeados.add(campo.campo)
    # Linha do arquivo -> posição do funcionário (1 = primeiro)
    posicao_da_linha = {}
    for posicao, registro in enumerate(normalizacao.registros, start=1):
        posicao_da_linha[registro["_linha"]] = posicao

    def anotar(regra, severidade, mensagem, acao, registro=None, campo=None, valor=None):
        """Registra um achado, com o valor que a regra achou (a empresa e o Assistente veem o dado real)."""
        linha, posicao = None, None
        if registro:
            linha = registro["_linha"]
            posicao = posicao_da_linha.get(registro["_linha"])
        # O valor como texto (sem valor, fica vazio)
        valor_em_texto = None
        if valor not in (None, ""):
            valor_em_texto = str(valor)
        relatorio.achados.append(Achado(regra, severidade, mensagem, acao, linha=linha, registro=posicao,
                                        campo=campo, valor=valor_em_texto))

    # As regras, sempre nesta ordem (a ordem dos achados no relatório segue esta)
    _regras_da_conferencia(normalizacao, anotar)
    _regras_de_obrigatorios(normalizacao, campos, campos_mapeados, anotar)
    _regras_de_formato(normalizacao.registros, campos, campos_mapeados, cnpjs_da_empresa, anotar)
    _regras_de_datas(normalizacao.registros, campos, referencia or date.today(), anotar)
    _duplicidades(normalizacao.registros, homologados, ja_enviados or {}, anotar)
    _renda_nao_positiva(normalizacao.registros, anotar)
    _valores_fora_da_faixa(normalizacao.registros, campos, anotar)
    _enquadramento_de_renda(normalizacao.registros, homologados, anotar)
    _perguntas_da_ia(normalizacao.registros, perguntas_da_ia or [], anotar)
    _pessoas_em_outros_envios(normalizacao.registros, outros_envios or {}, anotar)
    _pedidos_do_banco(normalizacao.registros, pedidos_do_banco or [], anotar)
    # Campo opcional com problema não pede nada à empresa (ADR-143)
    _tirar_as_pendencias_de_campo_opcional(relatorio, campos)
    # Quem fica de fora do envio não pede mais nada à empresa (ADR-126)
    _tirar_as_pendencias_de_quem_fica_de_fora(relatorio)
    return relatorio


def _regras_da_conferencia(normalizacao: Normalizacao, anotar) -> None:
    """1. A conferência do Normalizador, as decisões de coluna em aberto e os valores não convertidos.

    O valor não convertido bloqueia; o de um campo opcional sai depois, com os outros achados de campo opcional
    (_tirar_as_pendencias_de_campo_opcional, ADR-143).
    """
    conferencia = normalizacao.conferencia
    if not (conferencia.get("linhas_conferem") and conferencia.get("vazios_conferem")):
        anotar("CONFERENCIA_DE_TOTAIS", BLOQUEANTE, "A conferência de linhas ou de campos vazios não bateu.",
               "Reenviar o arquivo")
    for pendencia in normalizacao.pendencias_de_coluna:
        # O campo da coluna identifica a dúvida (duas colunas em dúvida são duas pendências); padronizações antigas
        # não o têm
        anotar(pendencia["tipo"], BLOQUEANTE, f"Coluna {pendencia['coluna']}: {pendencia['mensagem']}",
               "Decidir o formato da coluna", campo=pendencia.get("campo"))
    for nao_convertido in normalizacao.nao_convertidos:
        registro = _registro_da_linha(normalizacao.registros, nao_convertido["linha"])
        anotar("VALOR_NAO_CONVERTIDO", BLOQUEANTE,
               f"Valor de {nao_convertido['campo']} não reconhecido ({nao_convertido['motivo']}).", "Corrigir o valor",
               registro, nao_convertido["campo"], nao_convertido["valor"])


def _registro_da_linha(registros: list[dict], linha: int) -> dict:
    """O registro de uma linha do arquivo."""
    for registro in registros:
        if registro["_linha"] == linha:
            return registro
    raise KeyError(linha)


def _regras_de_obrigatorios(normalizacao: Normalizacao, campos: list[CampoLayout], campos_mapeados: set,
                            anotar) -> None:
    """2. Obrigatórios: coluna ausente no arquivo (uma vez) ou célula vazia (por linha)."""
    # Célula que não foi convertida já foi apontada na conferência: não aponta de novo como vazia
    ja_apontados = set()
    for nao_convertido in normalizacao.nao_convertidos:
        ja_apontados.add((nao_convertido["linha"], nao_convertido["campo"]))
    for campo in campos:
        if not campo.obrigatorio:
            continue
        if campo.campo not in campos_mapeados:
            # O que fazer depende do parâmetro: um dado da empresa pode ser informado
            # uma vez para todos; a informação do titular é de cada pessoa, e só um arquivo novo com a coluna resolve
            if parametros.pode_ser_igual_para_todos(campo):
                mensagem = "O arquivo não traz este dado para nenhum funcionário."
                acao = "Informar o valor uma vez, para todos (é um dado da empresa)"
            else:
                mensagem = "O arquivo não traz este dado para nenhum funcionário, e ele é único por funcionário."
                acao = "Enviar o arquivo de novo com esta coluna (a informação é única por funcionário)"
            anotar("OBRIGATORIO_SEM_COLUNA", BLOQUEANTE, mensagem, acao, campo=campo.campo)
            continue
        for registro in normalizacao.registros:
            if registro[campo.campo] is None and (registro["_linha"], campo.campo) not in ja_apontados:
                anotar("OBRIGATORIO_VAZIO", BLOQUEANTE, f"Campo obrigatório {campo.campo} vazio.",
                       "Preencher o valor", registro, campo.campo)


def _regras_de_formato(registros: list[dict], campos: list[CampoLayout], campos_mapeados: set,
                       cnpjs_da_empresa: dict, anotar) -> None:
    """3. Formatos e documentos: CPF, CNPJ (e se é desta empresa, de uma filial ou do grupo), CEP, telefone e e-mail."""
    # Em quantos funcionários cada CNPJ aparece: um CNPJ desconhecido repetido é, provavelmente, do grupo
    pessoas_por_cnpj = _pessoas_por_cnpj(registros, campos, campos_mapeados)
    for registro in registros:
        for campo in campos:
            # Só campos com coluna no arquivo e preenchidos
            if campo.campo not in campos_mapeados or not registro[campo.campo]:
                continue
            valor = registro[campo.campo]
            if campo.tipo == TipoCampo.CPF and not cpf_valido(valor):
                anotar("CPF_INVALIDO", BLOQUEANTE, "CPF com dígito verificador inválido.", "Corrigir o CPF",
                       registro, campo.campo, valor)
            elif campo.tipo == TipoCampo.CNPJ:
                _regra_do_cnpj(registro, campo.campo, valor, cnpjs_da_empresa, pessoas_por_cnpj.get(valor, 0), anotar)
            elif campo.tipo == TipoCampo.CEP and len(valor) != 8:
                anotar("CEP_INVALIDO", ALERTA, f"CEP com {len(valor)} dígitos (o certo é 8; pode ter perdido um zero).",
                       "Corrigir ou confirmar o CEP", registro, campo.campo, valor)
            elif campo.tipo == TipoCampo.TELEFONE and len(valor) not in (10, 11):
                anotar("TELEFONE_INVALIDO", AVISO, "Telefone sem DDD ou com dígitos a mais.", "Conferir o telefone",
                       registro, campo.campo, valor)
            elif campo.tipo == TipoCampo.EMAIL and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", valor):
                anotar("EMAIL_INVALIDO", AVISO, "E-mail em formato inválido.", "Conferir o e-mail", registro,
                       campo.campo, valor)


def _pessoas_por_cnpj(registros: list[dict], campos: list[CampoLayout], campos_mapeados: set) -> dict[str, int]:
    """Em quantos funcionários do envio cada CNPJ aparece (em qualquer campo de CNPJ).

    Recebe: os funcionários, os campos do layout e os campos com coluna no arquivo.
    Devolve: {cnpj: quantidade de funcionários}. Exemplo: {"10433218000193": 40, "55667788000190": 3}.
    """
    quantidades = {}
    for registro in registros:
        # Os CNPJs desta pessoa, sem repetir (o mesmo CNPJ em dois campos conta uma vez só)
        cnpjs_da_pessoa = set()
        for campo in campos:
            if campo.tipo == TipoCampo.CNPJ and campo.campo in campos_mapeados and registro[campo.campo]:
                cnpjs_da_pessoa.add(registro[campo.campo])
        # Soma um funcionário em cada CNPJ que ele tem
        for cnpj in cnpjs_da_pessoa:
            quantidades[cnpj] = quantidades.get(cnpj, 0) + 1
    return quantidades


def cnpj_conhecido(cnpj: str, cnpjs_da_empresa: dict) -> bool:
    """True se o CNPJ é da empresa: o principal, uma filial dele ou um CNPJ registrado (filial ou grupo).

    "Mesma raiz" = os mesmos 8 primeiros dígitos, que identificam a empresa; os 6 seguintes identificam o
    estabelecimento (matriz 0001, filiais 0002...). Uma filial de uma empresa do grupo registrada também vale.
    Exemplo: principal 10433218000193 → 10433218000274 (filial) é conhecido.
    """
    raizes_conhecidas = set()
    # A raiz da sede
    if cnpjs_da_empresa.get("principal"):
        raizes_conhecidas.add(cnpjs_da_empresa["principal"][:8])
    # As raízes dos CNPJs registrados (filiais e grupo)
    for registrado in cnpjs_da_empresa.get("registrados", []):
        raizes_conhecidas.add(registrado[:8])
    return cnpj[:8] in raizes_conhecidas


def _regra_do_cnpj(registro: dict, nome_do_campo: str, valor: str, cnpjs_da_empresa: dict, quantas_pessoas: int,
                   anotar) -> None:
    """A regra do CNPJ (ADR-77): dígitos certos e da empresa; se não for, repetido pergunta e sozinho bloqueia.

    - dígito verificador errado → CNPJ_INVALIDO (bloqueia);
    - conhecido (principal, filial ou registrado) → tudo certo;
    - desconhecido e em 2 ou mais funcionários → CNPJ_DO_GRUPO_A_CONFIRMAR (alerta): provavelmente é de uma empresa do
      grupo; a empresa confirma uma vez e o CNPJ entra no cadastro (não pergunta de novo);
    - desconhecido e em 1 funcionário só → CNPJ_DE_OUTRA_EMPRESA (bloqueia): provavelmente um erro de digitação.
    Sem CNPJ principal (empresa desconhecida), só o dígito verificador é conferido.
    """
    if not cnpj_valido(valor):
        anotar("CNPJ_INVALIDO", BLOQUEANTE, "CNPJ com dígito verificador inválido.", "Corrigir o CNPJ",
               registro, nome_do_campo, valor)
        return
    # Sem o CNPJ principal não há com o que comparar; conhecido está certo
    if not cnpjs_da_empresa.get("principal") or cnpj_conhecido(valor, cnpjs_da_empresa):
        return
    # Repetido em vários funcionários: provavelmente do grupo, a empresa confirma
    if quantas_pessoas >= 2:
        anotar(REGRA_CNPJ_DO_GRUPO, ALERTA,
               f"Este CNPJ aparece em {quantas_pessoas} funcionários e não está no cadastro da sua empresa. "
               "É de uma empresa do seu grupo?",
               "Confirmar que é do grupo (ele entra no cadastro e não perguntamos de novo) ou corrigir o CNPJ",
               registro, nome_do_campo, valor)
        return
    # Num funcionário só: provavelmente erro de digitação
    anotar("CNPJ_DE_OUTRA_EMPRESA", BLOQUEANTE,
           "O CNPJ não é da sua empresa nem de uma filial ou empresa do grupo no cadastro.",
           "Corrigir o CNPJ (se for de uma empresa do grupo, peça ao banco para cadastrá-lo)",
           registro, nome_do_campo, valor)


def _campo_e_obrigatorio(campos: list[CampoLayout], nome_do_campo: str) -> bool:
    """True se o campo está no parâmetro e é obrigatório. Ex.: a data_nascimento no layout_v1 → True."""
    for campo in campos:
        if campo.campo == nome_do_campo:
            return campo.obrigatorio
    # O campo nem está no parâmetro
    return False


def _regras_de_datas(registros: list[dict], campos: list[CampoLayout], referencia: date, anotar) -> None:
    """4. Datas coerentes: nascimento no passado, admissão depois dos 14 anos, efetivação depois da admissão.

    A admissão só é comparada com o nascimento quando o nascimento é obrigatório no parâmetro (ADR-143). Com ele
    opcional, um nascimento errado pediria para corrigir a admissão, que está certa, e o campo opcional não pede nada.
    Ex.: nascimento opcional em 2030 e admissão em 2020 → nenhum achado; com o nascimento obrigatório → o nascimento no
    futuro e a admissão antes do nascimento.
    """
    # A comparação da admissão com o nascimento só vale com o nascimento obrigatório
    compara_com_o_nascimento = _campo_e_obrigatorio(campos, "data_nascimento")
    for registro in registros:
        nascimento = registro.get("data_nascimento")
        admissao = registro.get("data_admissao")
        efetivacao = registro.get("data_efetivacao")
        if nascimento and date.fromisoformat(nascimento) > referencia:
            anotar("NASCIMENTO_NO_FUTURO", BLOQUEANTE, "Data de nascimento no futuro.", "Corrigir a data", registro,
                   "data_nascimento", nascimento)
        if compara_com_o_nascimento and nascimento and admissao:
            # Idade na admissão, em anos completos (aproximada por 365 dias)
            idade = (date.fromisoformat(admissao) - date.fromisoformat(nascimento)).days // 365
            if idade < 0:
                anotar("ADMISSAO_ANTES_DO_NASCIMENTO", BLOQUEANTE, "Admissão antes do nascimento.", "Corrigir as datas",
                       registro, "data_admissao", admissao)
            elif idade < 14:
                anotar("ADMISSAO_ANTES_DOS_14", ALERTA, f"Admissão com {idade} anos (o mínimo legal é 14).",
                       "Corrigir ou justificar", registro, "data_admissao", admissao)
        # Datas no formato AAAA-MM-DD podem ser comparadas como texto
        if admissao and efetivacao and efetivacao < admissao:
            anotar("EFETIVACAO_ANTES_DA_ADMISSAO", ALERTA, "Efetivação antes da admissão.", "Corrigir as datas",
                   registro, "data_efetivacao", efetivacao)


# As regras que deixam a linha de fora do envio: a pessoa não vai ao banco por este arquivo (ADR-126, envio parcial).
# São AVISO: não pedem nada à empresa, e o envio segue só com as outras pessoas.
JA_HOMOLOGADO_NA_EMPRESA = "JA_HOMOLOGADO_NA_EMPRESA"      # a pessoa já está cadastrada na empresa
JA_ENVIADO_AO_BANCO = "JA_ENVIADO_AO_BANCO"                # a pessoa está noutro envio que espera a análise do banco
REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA = (JA_HOMOLOGADO_NA_EMPRESA, JA_ENVIADO_AO_BANCO)


def linhas_que_ficam_de_fora(relatorio: "RelatorioValidacao") -> dict[int, "Achado"]:
    """As linhas que não vão ao banco por este envio, cada uma com o achado que diz por quê (ADR-126).

    Recebe: o relatório do Validador. Devolve: {linha do arquivo: achado}.
    Exemplo: CPF da linha 4 já cadastrado → {4: Achado("JA_HOMOLOGADO_NA_EMPRESA", ...)}.
    """
    de_fora = {}
    for achado in relatorio.achados:
        # Só as regras que tiram a pessoa do envio, e só a primeira de cada linha
        if achado.regra_id in REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA and achado.linha not in de_fora:
            de_fora[achado.linha] = achado
    return de_fora


def _duplicidades(registros, homologados, ja_enviados, anotar) -> None:
    """5. Duplicidades: com quem já foi cadastrado ou enviado ao banco (a linha fica de fora) e dentro do arquivo.

    Recebe: registros; homologados (as pessoas já cadastradas na empresa); ja_enviados ({cpf: nome do arquivo} de quem
    está noutro envio esperando o banco); anotar.
    Envio parcial (ADR-126): quem já foi ao banco não vai de novo, e o envio segue com as outras pessoas. O mesmo CPF
    duas vezes no próprio arquivo continua pendência (a empresa tira a linha repetida com um clique): a pessoa ainda
    não foi ao banco, e só a empresa sabe qual das duas linhas está certa.
    """
    # Primeira linha em que cada CPF e cada matrícula apareceu no arquivo
    linha_do_cpf, linha_da_matricula = {}, {}
    cpfs_homologados = set()
    cpf_da_matricula_homologada = {}
    for pessoa in homologados:
        cpfs_homologados.add(pessoa["cpf"])
        if pessoa.get("matricula"):
            cpf_da_matricula_homologada[pessoa["matricula"]] = pessoa["cpf"]
    for registro in registros:
        cpf, matricula = registro.get("cpf"), registro.get("matricula")
        if cpf and cpf in cpfs_homologados:
            # Já cadastrada: fica de fora (todas as linhas dela, repetidas ou não)
            anotar(JA_HOMOLOGADO_NA_EMPRESA, AVISO, "Funcionário já homologado nesta empresa: não entra de novo.",
                   "Nenhuma (a linha será ignorada)", registro, "cpf", cpf)
        elif cpf and cpf in ja_enviados:
            # Já está com o banco, noutro envio: fica de fora deste
            anotar(JA_ENVIADO_AO_BANCO, AVISO,
                   f"Já foi enviada ao banco no arquivo {ja_enviados[cpf]} e está em análise: não vai de novo.",
                   "Nenhuma (a linha fica de fora deste envio)", registro, "cpf", cpf)
        elif cpf and cpf in linha_do_cpf:
            anotar("PESSOA_DUPLICADA", BLOQUEANTE, f"O mesmo CPF já aparece na linha {linha_do_cpf[cpf]}.",
                   "Remover a linha repetida", registro, "cpf", cpf)
        elif matricula and matricula in linha_da_matricula:
            anotar("MATRICULA_DUPLICADA", BLOQUEANTE,
                   f"A matrícula já é de outra pessoa na linha {linha_da_matricula[matricula]}.",
                   "Corrigir a matrícula", registro, "matricula", matricula)
        if cpf not in cpfs_homologados and matricula and cpf_da_matricula_homologada.get(matricula) not in (None, cpf):
            # A matrícula já foi homologada, mas para OUTRO CPF
            anotar("MATRICULA_JA_HOMOLOGADA", ALERTA, "Matrícula já homologada para outra pessoa nesta empresa.",
                   "Corrigir a matrícula", registro, "matricula", matricula)
        # Guarda só a primeira linha de cada um
        if cpf:
            linha_do_cpf.setdefault(cpf, registro["_linha"])
        if matricula:
            linha_da_matricula.setdefault(matricula, registro["_linha"])


# As regras que dizem que o valor da pessoa está errado em si, e não fazem uma pergunta. Num campo opcional, esse valor
# fica em branco nos dados que seguem, sem pendência, e nunca ganha valor padrão (ADR-143).
# As outras regras de um campo opcional só saem do relatório, e o valor fica como veio: a pergunta da IA (a IA importa
# o que achou, sem pergunta), o CNPJ que pode ser do grupo, o valor fora da faixa do parâmetro (ADR-128: é alerta, e
# não recusa), a profissão do cargo (o cargo está certo) e a dúvida de formato da coluna. O valor não convertido já fica
# vazio na padronização. O pedido do banco nunca sai (ver _tirar_as_pendencias_de_campo_opcional). Uma regra nova que
# diga que o valor está errado entra nesta lista.
REGRAS_DE_VALOR_INVALIDO = ("CPF_INVALIDO", "CNPJ_INVALIDO", "CNPJ_DE_OUTRA_EMPRESA", "CEP_INVALIDO",
                            "TELEFONE_INVALIDO", "EMAIL_INVALIDO", "NASCIMENTO_NO_FUTURO",
                            "EFETIVACAO_ANTES_DA_ADMISSAO", "MATRICULA_DUPLICADA", "MATRICULA_JA_HOMOLOGADA",
                            faixa_salarial_cbo.REGRA_CBO_DESCONHECIDO)


def _tirar_as_pendencias_de_campo_opcional(relatorio: "RelatorioValidacao", campos: list[CampoLayout]) -> None:
    """Campo opcional com valor inválido não abre pendência: só os campos obrigatórios pedem correção (ADR-143).

    Recebe: o relatório com os achados e os campos do parâmetro vigente.
    Faz: tira todo achado AUTOMÁTICO preso a um campo opcional: o formato, a data, a duplicidade, a dúvida de coluna,
    o valor não convertido, a pergunta da IA, a profissão do cargo e o CNPJ de outra empresa. Ficam dois:
    - o pedido do especialista do banco (PEDIDO_DO_BANCO): foi uma pessoa que pediu, e não uma regra que achou. A
      pessoa devolvida volta à empresa com o recado dele, mesmo num campo opcional (ex.: "Nome incorreto ou
      incompleto", no nome_completo);
    - o aviso de quem fica de fora do envio, que não é pendência: não pede nada à empresa e diz por que a linha não vai
      ao banco (ADR-126); ele é preso ao cpf.
    O achado tirado que diz que o valor da pessoa está errado (REGRAS_DE_VALOR_INVALIDO) vai para
    relatorio.valores_em_branco: esse valor fica em branco nos dados que seguem (executar grava o branco do sistema).
    Ex.: com só o cpf, o codigo_cbo, a valor_renda e a data_admissao obrigatórios, um CEP "7" não vira pendência e fica
    em branco; um CPF inválido continua sendo pendência, com o valor como veio; o banco apontar o cargo continua sendo
    pendência, com o recado do banco.
    """
    # Os nomes técnicos dos campos opcionais do parâmetro
    campos_opcionais = set()
    for campo in campos:
        if not campo.obrigatorio:
            campos_opcionais.add(campo.campo)
    achados_que_ficam = []
    for achado in relatorio.achados:
        # O aviso de quem fica de fora do envio não é pendência: fica em qualquer campo
        aviso_de_quem_fica_de_fora = achado.regra_id in REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA
        # O pedido explícito do especialista do banco também fica em qualquer campo: foi uma pessoa que pediu
        pedido_do_banco = achado.regra_id.startswith(PREFIXO_DO_PEDIDO_DO_BANCO)
        # Achado preso a um campo opcional sai (achado sem campo, ou de um campo fora do parâmetro, fica)
        if achado.campo in campos_opcionais and not aviso_de_quem_fica_de_fora and not pedido_do_banco:
            # O valor errado de uma pessoa fica em branco; a pergunta só sai
            valor_de_uma_pessoa = achado.linha is not None and achado.valor is not None
            if achado.regra_id in REGRAS_DE_VALOR_INVALIDO and valor_de_uma_pessoa:
                relatorio.valores_em_branco.append(achado)
            continue
        achados_que_ficam.append(achado)
    relatorio.achados = achados_que_ficam


def _tirar_as_pendencias_de_quem_fica_de_fora(relatorio: "RelatorioValidacao") -> None:
    """A pessoa que fica de fora do envio não pede nada à empresa: as outras pendências da linha dela saem (ADR-126).

    Exemplo: a linha 6 já foi enviada ao banco e tem a data de admissão em branco → fica só o aviso "já enviada";
    a empresa não precisa completar o dado de quem não vai neste envio.
    """
    de_fora = linhas_que_ficam_de_fora(relatorio)
    achados_que_ficam = []
    for achado in relatorio.achados:
        # O achado de uma linha que fica de fora só continua se for o próprio motivo de ela ficar de fora
        if achado.linha in de_fora and achado.regra_id not in REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA:
            continue
        achados_que_ficam.append(achado)
    relatorio.achados = achados_que_ficam


# O começo do código das perguntas da IA; o campo vem depois dos dois-pontos ("PERGUNTA_DA_IA:data_admissao")
PREFIXO_DA_PERGUNTA_DA_IA = "PERGUNTA_DA_IA:"


def _perguntas_da_ia(registros: list[dict], perguntas: list[dict], anotar) -> None:
    """Cada pergunta do Leitor de Documentos vira um ALERTA preso à pessoa e ao campo (ADR-73).

    A empresa responde corrigindo o campo (a pergunta some) ou confirmando que está certo assim. O código da regra
    leva o campo, para confirmar uma pergunta não confirmar as outras da mesma pessoa. Pergunta sobre a pessoa toda
    (sem campo) usa "PESSOA". Linha que não existe mais (ex.: pessoa excluída) é ignorada.
    """
    for pergunta in perguntas:
        try:
            registro = _registro_da_linha(registros, pergunta["linha"])
        except KeyError:
            continue
        campo = pergunta.get("campo") or None
        if campo:
            acao = "Corrija o campo com o valor certo ou confirme que está certo assim."
        else:
            acao = "Confira os dados desta pessoa e confirme."
        anotar(PREFIXO_DA_PERGUNTA_DA_IA + (campo or "PESSOA"), ALERTA, pergunta["pergunta"], acao,
               registro=registro, campo=campo, valor=registro.get(campo) if campo else None)


def _pessoas_em_outros_envios(registros: list[dict], outros_envios: dict[str, str], anotar) -> None:
    """A mesma pessoa (mesmo CPF) em outro envio da empresa que ainda não foi cadastrado: BLOQUEANTE.

    Por que bloqueia: se os dois envios fossem ao banco, a pessoa entraria duas vezes (e talvez com dados diferentes).
    A empresa decide em qual envio ela fica, com "Não cadastrar esta pessoa" no outro; a pendência some dos dois.
    """
    for registro in registros:
        cpf = registro.get("cpf")
        if cpf and cpf in outros_envios:
            anotar("PESSOA_EM_OUTRO_ENVIO", BLOQUEANTE,
                   f"Esta pessoa também está em outro envio que ainda não foi cadastrado (arquivo {outros_envios[cpf]}).",
                   "Deixe a pessoa num envio só: use \"Não cadastrar esta pessoa\" aqui ou no outro envio.",
                   registro, "cpf", cpf)


# O começo do código das pendências que o banco apontou; o identificador do apontamento vem depois dos dois-pontos
# ("PEDIDO_DO_BANCO:3f9a0c1d2e4b"), para uma resposta da empresa nunca valer para outro apontamento da mesma pessoa
PREFIXO_DO_PEDIDO_DO_BANCO = "PEDIDO_DO_BANCO:"


def _pedidos_do_banco(registros: list[dict], pedidos: list[dict], anotar) -> None:
    """Cada apontamento do banco que foi para a empresa vira um ALERTA preso à pessoa (e ao campo, se houver; ADR-121).

    A empresa resolve de três jeitos: corrige o campo (o valor fica diferente do que o banco apontou, e a pendência
    some), responde ao banco confirmando ("Está certo assim", que o banco lê na próxima avaliação) ou tira a pessoa do
    envio ("Não cadastrar esta pessoa": a linha some, e a pendência junto).
    Vale em qualquer campo, também no opcional (a limpeza dos opcionais não tira este pedido).
    Exemplo: apontamento do salário com valor_apontado "48000.00"; a empresa corrige para "4800.00" → sem achado; o
    cargo apontado em branco, e a empresa preenche "Analista" → sem achado.
    """
    for pedido in pedidos:
        # A pessoa saiu do envio (ou a linha não existe mais): nada a pedir
        try:
            registro = _registro_da_linha(registros, pedido["linha"])
        except KeyError:
            continue
        campo = pedido["campo"]
        # O campo apontado já foi corrigido pela empresa: o valor de hoje é outro (a mesma conta que o banco lê)
        if apontamentos_do_banco.empresa_mudou_o_valor(pedido, registro):
            continue
        valor_de_hoje = registro.get(campo) if campo else None
        if campo:
            acao = "Corrija o dado ou responda ao banco dizendo que está certo."
        else:
            acao = "Confira os dados desta pessoa e responda ao banco."
        anotar(PREFIXO_DO_PEDIDO_DO_BANCO + pedido["apontamento_id"], ALERTA, "O banco pediu: " + pedido["recado"],
               acao, registro=registro, campo=campo, valor=valor_de_hoje)


def perguntas_em_aberto(perguntas: list[dict], corrigidos: set[tuple[int, str]]) -> list[dict]:
    """As perguntas da IA sem resposta: pergunta sobre um campo que a empresa já corrigiu está respondida.

    corrigidos: (linha, campo) de cada correção aplicada. Ex.: pergunta da linha 5 sobre cpf, e a empresa corrigiu o
    cpf da linha 5 → sai da lista.
    """
    abertas = []
    for pergunta in perguntas:
        if pergunta.get("campo") and (pergunta["linha"], pergunta["campo"]) in corrigidos:
            continue
        abertas.append(pergunta)
    return abertas


def _renda_nao_positiva(registros: list[dict], anotar) -> None:
    """6a. Renda zerada ou negativa."""
    for registro in registros:
        if registro.get("valor_renda") and Decimal(registro["valor_renda"]) <= 0:
            anotar("RENDA_NAO_POSITIVA", BLOQUEANTE, "Renda zerada ou negativa.", "Corrigir o valor", registro,
                   "valor_renda", registro["valor_renda"])


def _valores_fora_da_faixa(registros: list[dict], campos: list[CampoLayout], anotar) -> None:
    """6c. O valor abaixo do mínimo ou acima do máximo do parâmetro (ADR-128): ALERTA, e não recusa.

    Para que serve: o banco põe no parâmetro uma faixa esperada para os campos
    numéricos (o salário começa com o piso de R$ 500,00). Fora dela, pode ser erro de digitação: a empresa confirma que
    está certo ou corrige. A faixa por cargo, com o código CBO, é outra regra (RENDA_FORA_DO_CARGO e a tabela CBO).
    Ex.: salário "R$ 350,00" com mínimo de R$ 500,00 → 'Valor de valor_renda abaixo do mínimo do parâmetro
    (R$ 500,00).'
    """
    for campo in campos:
        # Só os campos com faixa no parâmetro
        if campo.minimo is None and campo.maximo is None:
            continue
        for registro in registros:
            valor_em_texto = registro.get(campo.campo)
            # Vazio: quem aponta é a regra dos obrigatórios
            if valor_em_texto in (None, ""):
                continue
            valor = Decimal(str(valor_em_texto))
            # Zerado ou negativo já é outra pendência (RENDA_NAO_POSITIVA, que bloqueia): não aponta duas vezes
            if valor <= 0:
                continue
            # Abaixo do mínimo ou acima do máximo: a frase diz qual lado e o limite, em reais
            if campo.minimo is not None and valor < campo.minimo:
                lado = f"abaixo do mínimo do parâmetro ({formatacao.em_reais(campo.minimo)})"
            elif campo.maximo is not None and valor > campo.maximo:
                lado = f"acima do máximo do parâmetro ({formatacao.em_reais(campo.maximo)})"
            else:
                continue
            anotar(REGRA_VALOR_FORA_DA_FAIXA, ALERTA, f"Valor de {campo.campo} {lado}.", "Corrigir ou confirmar",
                   registro, campo.campo, valor_em_texto)


def _tem_dados_de_renda(pessoa: dict) -> bool:
    """True se a pessoa tem cargo, tipo de renda e valor."""
    return bool(pessoa.get("cargo") and pessoa.get("tipo_renda") and pessoa.get("valor_renda"))


def _enquadramento_de_renda(registros, homologados, anotar) -> None:
    """6b. Mediana + MAD dos colegas do mesmo cargo e tipo de renda (ADR-14); tabela de referência se poucos."""
    faixas = faixas_de_referencia()
    # (cargo, tipo de renda) -> rendas de todos os colegas (do arquivo e já homologados)
    rendas_por_cargo = {}
    for pessoa in list(registros) + list(homologados):
        if _tem_dados_de_renda(pessoa):
            chave = (pessoa["cargo"], pessoa["tipo_renda"])
            rendas_por_cargo.setdefault(chave, []).append(Decimal(pessoa["valor_renda"]))
    for registro in registros:
        if not _tem_dados_de_renda(registro):
            continue
        valor = Decimal(registro["valor_renda"])
        # Renda zerada ou negativa já foi apontada
        if valor <= 0:
            continue
        chave = (registro["cargo"], registro["tipo_renda"])
        rendas_dos_colegas = rendas_por_cargo.get(chave, [])
        if len(rendas_dos_colegas) >= MINIMO_DE_COLEGAS:
            # Colegas suficientes: compara com a mediana deles
            mediana = statistics.median(rendas_dos_colegas)
            distancias = []
            for renda in rendas_dos_colegas:
                distancias.append(abs(renda - mediana))
            mad = statistics.median(distancias)
            if mad:
                # z robusto: quantos "desvios" a renda está longe da mediana
                z_robusto = abs(valor - mediana) / (mad * FATOR_DO_MAD)
                fora_do_padrao = z_robusto > LIMITE_Z_ROBUSTO
            else:
                # Todos ganham igual (MAD zero): só é alerta abaixo de 1/3 ou acima de 3 vezes a mediana
                fora_do_padrao = not (mediana / 3 <= valor <= mediana * 3)
            comparado_com = f"a mediana do cargo na empresa ({formatacao.em_reais(mediana)}, {len(rendas_dos_colegas)} pessoas)"
        elif chave in faixas:
            # Poucos colegas: usa a faixa de referência do cargo
            mediana = faixas[chave]["mediana"]
            fora_do_padrao = not (faixas[chave]["faixa_minima"] <= valor <= faixas[chave]["faixa_maxima"])
            comparado_com = f"a referência do cargo ({formatacao.em_reais(mediana)}), porque a empresa tem poucos colegas nele"
        else:
            # Cargo sem colegas nem referência: nada a comparar
            continue
        if fora_do_padrao:
            vezes = str((valor / mediana).quantize(Decimal("0.1"))).replace(".", ",")
            anotar("RENDA_FORA_DO_CARGO", ALERTA,
                   f"Renda {vezes}x {comparado_com}. Pode ser erro de digitação; se estiver certa, justifique.",
                   "Corrigir ou justificar", registro, "valor_renda", registro["valor_renda"])


# ---------------- Explicação pelo LLM (só explica) ----------------

def explicar(relatorio: RelatorioValidacao, cliente=None) -> str:
    """Resumo em linguagem simples a partir dos ACHADOS, com o valor de cada um; não muda nenhuma severidade."""
    from services.llm_client import LLMClient
    # O que o LLM precisa: regra, severidade, campo, linha, mensagem e o valor achado (ADR-101)
    achados = []
    for achado in relatorio.achados:
        achados.append({"regra": achado.regra_id, "severidade": achado.severidade, "campo": achado.campo,
                        "linha": achado.linha, "mensagem": achado.mensagem, "valor": achado.valor})
    sistema = (RAIZ / "prompts" / "explicador_validacao_v2.md").read_text(encoding="utf-8")
    cliente = cliente or LLMClient(respostas_mock={"explicar_validacao": _explicacao_simulada})
    return cliente.gerar("explicar_validacao", json.dumps(achados, ensure_ascii=False), sistema).texto


def _explicacao_simulada(prompt: str) -> str:
    """MOCK: resumo montado por regra, no mesmo tom que o prompt pede."""
    achados = json.loads(prompt)
    if not achados:
        return "Tudo certo: nenhuma pendência. O arquivo pode ser homologado."
    textos_por_severidade = ((BLOQUEANTE, "precisam ser corrigidas antes da homologação"),
                             (ALERTA, "precisam de correção ou de uma justificativa"),
                             (AVISO, "são só informativas"))
    partes = []
    for severidade, texto in textos_por_severidade:
        quantidade = 0
        for achado in achados:
            if achado["severidade"] == severidade:
                quantidade += 1
        if quantidade:
            palavra = "pendência" if quantidade == 1 else "pendências"
            partes.append(f"{quantidade} {palavra} {texto}")
    return "Encontramos " + "; ".join(partes) + ". Comece pelas bloqueantes."


# ---------------- Persistência ----------------

def _preparar(conexao) -> None:
    """Cria as tabelas das validações e das resoluções de alerta, se ainda não existirem."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS validacoes (
               processamento_id TEXT PRIMARY KEY,
               relatorio        TEXT NOT NULL,
               criado_em        TEXT NOT NULL
           )"""
    )
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS resolucoes_alerta (
               processamento_id TEXT NOT NULL,
               regra_id         TEXT NOT NULL,
               linha            INTEGER,
               resolucao        TEXT NOT NULL,     -- ERRO_CORRIGIDO, CONFIRMADO, SUSPEITO ou REABERTO
               justificativa    TEXT NOT NULL,
               usuario          TEXT NOT NULL,
               criado_em        TEXT NOT NULL
           )"""
    )


def homologados_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os funcionários já homologados na empresa (para duplicidade e para a renda dos colegas)."""
    processamentos._preparar(conexao)
    linhas = conexao.execute("SELECT cpf, matricula, cargo, tipo_renda, valor_renda FROM funcionarios_homologados "
                             "WHERE empresa_id = ?", (empresa_id,))
    homologados = []
    for cpf, matricula, cargo, tipo_renda, valor_renda in linhas:
        homologados.append({"cpf": cpf, "matricula": matricula, "cargo": cargo, "tipo_renda": tipo_renda,
                            "valor_renda": valor_renda})
    return homologados


def resolucoes(conexao, processamento_id: str) -> dict[tuple[str, int | None], str]:
    """(regra_id, linha) -> resolução mais recente dada pela empresa."""
    _preparar(conexao)
    linhas = conexao.execute("SELECT regra_id, linha, resolucao FROM resolucoes_alerta WHERE processamento_id = ? "
                             "ORDER BY criado_em, rowid", (processamento_id,))
    resolucao_por_alerta = {}
    # Em ordem de criação: a mais recente sobrescreve as anteriores
    for regra_id, linha, resolucao in linhas:
        resolucao_por_alerta[(regra_id, linha)] = resolucao
    return resolucao_por_alerta


# As situações de envio em que as pessoas já foram padronizadas e ainda não foram cadastradas
ESTADOS_COM_PESSOAS_PENDENTES = (EstadoProcessamento.NORMALIZADO, EstadoProcessamento.VALIDACAO_PENDENTE,
                                 EstadoProcessamento.AGUARDANDO_BANCO)
# As situações em que o envio ainda espera a empresa (a validação dele é refeita quando outro envio muda)
ESTADOS_QUE_A_EMPRESA_AINDA_MEXE = (EstadoProcessamento.NORMALIZADO, EstadoProcessamento.VALIDACAO_PENDENTE)
# As situações em que as pessoas do envio estão com a empresa: as de cima e o envio que o banco devolveu (inteiro ou
# só as pessoas apontadas, ADR-121). A mesma pessoa num arquivo novo vira a pendência "pessoa em outro envio": ela
# fica num envio só, e a empresa escolhe qual (ADR-126)
ESTADOS_COM_A_EMPRESA = ESTADOS_QUE_A_EMPRESA_AINDA_MEXE + (EstadoProcessamento.DEVOLVIDO,)


def pessoas_de_outros_envios(conexao, empresa_id: str, processamento_id: str | None,
                             estados=ESTADOS_COM_PESSOAS_PENDENTES) -> dict[str, str]:
    """{cpf: nome do arquivo} das pessoas nos envios da empresa ainda não cadastrados, fora o envio informado.

    Recebe: processamento_id — o envio que fica de fora (None: todos entram); estados — as situações de envio que
    contam (padrão: todos os ainda não cadastrados; ESTADOS_COM_A_EMPRESA ou (AGUARDANDO_BANCO,) separam os envios
    que estão com a empresa dos que já foram ao banco, ADR-126).
    O nome vem com a versão quando a empresa enviou arquivos diferentes com o mesmo nome (ex.: "aurora.xlsx (v1)"),
    para a mensagem nunca parecer falar do próprio arquivo.
    Quem ficou de fora de um envio (já cadastrado ou já com o banco) não conta como pessoa dele.
    """
    from services import correcoes
    nomes = processamentos.nomes_na_tela(conexao, empresa_id)
    pessoas = {}
    for perfil in processamentos.listar(conexao, empresa_id):
        if perfil.processamento_id == processamento_id or perfil.status not in estados:
            continue
        # As linhas que ficam de fora deste outro envio (sem validação guardada, nenhuma)
        relatorio_do_outro = obter(conexao, perfil.processamento_id)
        de_fora = {}
        if relatorio_do_outro is not None:
            de_fora = linhas_que_ficam_de_fora(relatorio_do_outro)
        for registro in correcoes.dados_atuais(conexao, perfil.processamento_id).registros:
            if registro.get("cpf") and registro["_linha"] not in de_fora:
                pessoas.setdefault(registro["cpf"], nomes[perfil.processamento_id])
    return pessoas


def _deixar_em_branco_os_valores_invalidos(conexao, processamento_id: str, empresa_id: str,
                                           valores_em_branco: list[Achado]) -> None:
    """Grava o branco do sistema de cada valor inválido de um campo opcional (ADR-143).

    Recebe: o envio, a empresa e os achados de relatorio.valores_em_branco. Cada um vira uma correção do sistema
    (services/correcoes.py): o valor que veio, o campo em branco e o motivo, que é a mensagem da regra.
    Ex.: o CEP "0131010" da linha 5 → a correção do sistema "Campo opcional com valor inválido: CEP com 7 dígitos
    (o certo é 8; pode ter perdido um zero)."
    """
    from services import correcoes
    valores = []
    for achado in valores_em_branco:
        valores.append({"linha": achado.linha, "campo": achado.campo, "antes": achado.valor,
                        "motivo": "Campo opcional com valor inválido: " + achado.mensagem})
    correcoes.deixar_em_branco_pelo_sistema(conexao, processamento_id, empresa_id, valores)


def executar(conexao, processamento_id: str, empresa_id: str, revalidar_os_outros: bool = True) -> RelatorioValidacao:
    """Valida os dados ATUAIS (padronização + correções aplicadas) e marca os alertas já justificados.

    O valor inválido de um campo opcional não vira pendência e fica em branco nos dados que seguem: a correção do
    sistema guarda o motivo (ADR-143).

    revalidar_os_outros: depois, valida de novo os outros envios da empresa que ainda esperam a empresa, porque a
    mudança neste envio (ex.: tirar uma pessoa) pode resolver ou criar a pendência "pessoa em outro envio" neles.
    """
    from services import correcoes
    _preparar(conexao)
    perfil = processamentos.obter_da_empresa(conexao, processamento_id, empresa_id)
    if perfil is None:
        raise ValueError("Processamento não encontrado.")
    normalizacao = correcoes.dados_atuais(conexao, processamento_id)
    _, campos = parametros.layout_ativo(conexao)
    # As perguntas da IA ainda sem resposta (o campo corrigido pela empresa responde a pergunta)
    corrigidos = set()
    for correcao in correcoes.listar(conexao, processamento_id, status="APLICADA"):
        corrigidos.add((correcao.linha, correcao.campo))
    perguntas = perguntas_em_aberto(perfil.perguntas_da_ia, corrigidos)
    # As pessoas dos outros envios (ADR-126): as que ainda estão com a empresa viram a pendência "pessoa em outro
    # envio"; as que já foram ao banco ficam de fora deste envio. O envio que já está com o banco (validado de novo na
    # aprovação dele) não olha os outros: quem chegou depois é que fica de fora
    outros_envios, ja_enviados = {}, {}
    if perfil.status != EstadoProcessamento.AGUARDANDO_BANCO:
        outros_envios = pessoas_de_outros_envios(conexao, empresa_id, processamento_id, ESTADOS_COM_A_EMPRESA)
        ja_enviados = pessoas_de_outros_envios(conexao, empresa_id, processamento_id,
                                               (EstadoProcessamento.AGUARDANDO_BANCO,))
    relatorio = validar(normalizacao, campos, empresa_id, homologados_da_empresa(conexao, empresa_id),
                        referencia=perfil.data_referencia, perguntas_da_ia=perguntas,
                        outros_envios=outros_envios, ja_enviados=ja_enviados,
                        cnpjs_da_empresa=empresas.cnpjs_conhecidos(conexao, empresa_id),
                        pedidos_do_banco=apontamentos_do_banco.enviados(conexao, processamento_id))
    # A profissão (CBO) de cada pessoa e o salário fora da faixa da profissão ou das outras empresas (ADR-129)
    faixa_salarial_cbo.acrescentar_alertas(conexao, relatorio, normalizacao, empresa_id, processamento_id)
    # Os alertas da profissão seguem a mesma regra: no cargo opcional, não pedem nada à empresa (ADR-143)
    _tirar_as_pendencias_de_campo_opcional(relatorio, campos)
    # O valor inválido de um campo opcional fica em branco nos dados que seguem, com o motivo (ADR-143)
    _deixar_em_branco_os_valores_invalidos(conexao, processamento_id, empresa_id, relatorio.valores_em_branco)
    # Alerta justificado pela empresa continua no relatório, marcado como resolvido
    justificados = resolucoes(conexao, processamento_id)
    for achado in relatorio.achados:
        resolucao = justificados.get((achado.regra_id, achado.linha))
        if achado.severidade == ALERTA and resolucao in RESOLUCOES_DE_JUSTIFICATIVA:
            achado.resolvido = resolucao
    # Guarda o relatório
    achados_em_dicionario = []
    for achado in relatorio.achados:
        achados_em_dicionario.append(asdict(achado))
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Grava ou substitui o relatório deste processamento ("ON CONFLICT": a mesma forma no SQLite e no PostgreSQL)
    conexao.execute("INSERT INTO validacoes (processamento_id, relatorio, criado_em) VALUES (?, ?, ?) "
                    "ON CONFLICT (processamento_id) DO UPDATE SET relatorio = excluded.relatorio, "
                    "criado_em = excluded.criado_em",
                    (processamento_id, json.dumps(achados_em_dicionario, ensure_ascii=False), agora))
    conexao.commit()
    # Pronto para homologar volta para NORMALIZADO; com pendências, fica em VALIDACAO_PENDENTE
    if relatorio.pronto_para_homologar:
        novo_status = EstadoProcessamento.NORMALIZADO
    else:
        novo_status = EstadoProcessamento.VALIDACAO_PENDENTE
    processamentos.atualizar_status(conexao, processamento_id, novo_status)
    regras_encontradas = set()
    for achado in relatorio.achados:
        regras_encontradas.add(achado.regra_id)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Validação", "VALIDADO",
                        {"contagem": relatorio.contagem(), "regras": sorted(regras_encontradas)})
    # Os outros envios da empresa que ainda esperam a empresa: a "pessoa em outro envio" pode ter mudado neles
    if revalidar_os_outros:
        for outro in processamentos.listar(conexao, empresa_id):
            # Este mesmo envio e os que já não esperam a empresa ficam de fora
            if outro.processamento_id == processamento_id or outro.status not in ESTADOS_QUE_A_EMPRESA_AINDA_MEXE:
                continue
            # Só quem já tem uma validação guardada é validado de novo
            if obter(conexao, outro.processamento_id) is not None:
                executar(conexao, outro.processamento_id, empresa_id, revalidar_os_outros=False)
    return relatorio


def obter(conexao, processamento_id: str) -> RelatorioValidacao | None:
    """O último relatório guardado do processamento, ou None se ainda não foi validado."""
    _preparar(conexao)
    linha = conexao.execute("SELECT relatorio FROM validacoes WHERE processamento_id = ?", (processamento_id,)).fetchone()
    if linha is None:
        return None
    achados = []
    for achado in json.loads(linha[0]):
        # Relatório gravado antes do ADR-101: o valor tinha o nome "valor_mascarado"
        if "valor_mascarado" in achado:
            achado["valor"] = achado.pop("valor_mascarado")
        achados.append(Achado(**achado))
    return RelatorioValidacao(achados)


def descartar(conexao, processamento_id: str) -> None:
    """Apaga o relatório do processamento (ex.: o mapeamento mudou e ele deixou de valer).

    Não faz commit: quem chama decide quando gravar, junto com as outras mudanças.
    """
    _preparar(conexao)
    conexao.execute("DELETE FROM validacoes WHERE processamento_id = ?", (processamento_id,))


def registrar_resolucao(conexao, processamento_id: str, regra_id: str, linha: int | None, resolucao: str,
                        justificativa: str, usuario: str) -> None:
    """Como a empresa resolveu um alerta: vira rótulo para um futuro modelo de risco (ADR-14)."""
    if resolucao not in RESOLUCOES_VALIDAS:
        raise ValueError("Resolução deve ser ERRO_CORRIGIDO, CONFIRMADO, SUSPEITO ou REABERTO.")
    if not justificativa.strip():
        raise ValueError("Toda resolução precisa de uma justificativa.")
    _preparar(conexao)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conexao.execute("INSERT INTO resolucoes_alerta VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (processamento_id, regra_id, linha, resolucao, justificativa.strip(), usuario, agora))
    conexao.commit()


def _tem_alerta(relatorio: RelatorioValidacao | None, regra_id: str, linha: int | None) -> bool:
    """True se o relatório tem um ALERTA com esta regra nesta linha."""
    if relatorio is None:
        return False
    for achado in relatorio.achados:
        if achado.regra_id == regra_id and achado.linha == linha and achado.severidade == ALERTA:
            return True
    return False


def justificar_alerta(conexao, processamento_id: str, empresa_id: str, regra_id: str, linha: int | None,
                      resolucao: str, justificativa: str, usuario: str) -> RelatorioValidacao:
    """A empresa confirma (ou marca como suspeito) um alerta, com justificativa; depois, revalida."""
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    if not _tem_alerta(obter(conexao, processamento_id), regra_id, linha):
        raise ValueError("Não há um alerta com essa regra nessa linha.")
    # Um valor que o sistema não conseguiu entender não se confirma: a confirmação é guardada
    # por regra e linha, e fecharia junto outro valor não entendido da mesma pessoa, em outro campo
    if regra_id == REGRA_VALOR_NAO_CONVERTIDO:
        raise ValueError("Um valor que o sistema não conseguiu entender não se confirma: informe o valor certo ou "
                         "deixe a informação em branco.")
    # Erro não se justifica: se resolve corrigindo o valor
    if resolucao not in RESOLUCOES_DE_JUSTIFICATIVA:
        raise ValueError("Na justificativa, use CONFIRMADO ou SUSPEITO (erro se resolve corrigindo o valor).")
    # O CNPJ do alerta "é do grupo?" é lido antes de a validação abaixo tirar o alerta
    cnpj_do_grupo = None
    if regra_id == REGRA_CNPJ_DO_GRUPO and resolucao == "CONFIRMADO":
        cnpj_do_grupo = _cnpj_do_alerta(conexao, processamento_id, linha)
    registrar_resolucao(conexao, processamento_id, regra_id, linha, resolucao, justificativa, usuario)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "ALERTA_JUSTIFICADO",
                        {"regra": regra_id, "linha": linha, "resolucao": resolucao})
    # "Sim, é do nosso grupo": o CNPJ entra no cadastro da empresa, e a validação abaixo tira o alerta de todos
    # (deste envio e dos outros envios da empresa, validados de novo por executar)
    if cnpj_do_grupo:
        empresas.registrar_cnpj_confirmado_pela_empresa(conexao, usuario, empresa_id, cnpj_do_grupo)
        auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "CNPJ_DO_GRUPO_REGISTRADO",
                            {"linha": linha})
    return executar(conexao, processamento_id, empresa_id)


def reabrir_alerta(conexao, processamento_id: str, empresa_id: str, regra_id: str, linha: int | None,
                   usuario: str) -> RelatorioValidacao:
    """Desfaz a confirmação de um alerta ("Desfazer" na conversa): o alerta volta a ficar em aberto.

    Recebe: o envio, a empresa (da sessão), a regra e a linha do alerta, e quem desfez.
    Devolve: o relatório validado de novo. Levanta KeyError (outra empresa) ou ValueError (o alerta não está
    confirmado agora). Como a confirmação, a reabertura fica guardada (quem, quando), e vale a mais recente.
    """
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    # Só um alerta confirmado (a resolução mais recente) pode ser reaberto
    if resolucoes(conexao, processamento_id).get((regra_id, linha)) not in RESOLUCOES_DE_JUSTIFICATIVA:
        raise ValueError("Este alerta não está confirmado: não há o que desfazer.")
    registrar_resolucao(conexao, processamento_id, regra_id, linha, REABERTO, "Confirmação desfeita pela empresa",
                        usuario)
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "ALERTA_REABERTO",
                        {"regra": regra_id, "linha": linha})
    return executar(conexao, processamento_id, empresa_id)


def _cnpj_do_alerta(conexao, processamento_id: str, linha: int | None) -> str:
    """O CNPJ que o alerta "é do grupo?" aponta, lido dos dados atuais do envio (não do texto mostrado na tela).

    Recebe: conexao; o envio; a linha do alerta. Devolve: o CNPJ (14 dígitos). Levanta ValueError se não achar.
    """
    from services import correcoes
    # O campo do alerta (cnpj_empregador ou cnpj_grupo)
    campo_do_alerta = None
    for achado in obter(conexao, processamento_id).achados:
        if achado.regra_id == REGRA_CNPJ_DO_GRUPO and achado.linha == linha:
            campo_do_alerta = achado.campo
    # O valor desse campo na linha do alerta
    for registro in correcoes.dados_atuais(conexao, processamento_id).registros:
        if registro["_linha"] == linha and campo_do_alerta and registro.get(campo_do_alerta):
            return registro[campo_do_alerta]
    raise ValueError("Não achei o CNPJ dessa linha.")
