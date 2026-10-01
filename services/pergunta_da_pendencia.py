"""As frases de reserva do Agente de validação: a primeira fala sobre cada pendência, pronta, sempre correta.

Para que serve (pendências por conversa): quem escreve a pergunta de cada pendência
é a IA (agents/redator_de_perguntas.py), seguindo a diretriz de tom de voz. Estas frases são a RESERVA:
valem quando a IA está fora, demora, ou escreve algo que não passa na conferência; e são o que o modo MOCK usa.
Por isso elas precisam estar sempre certas, com qualquer nome de campo que o banco escrever no parâmetro:
    - o nome do campo vem da descrição do parâmetro, entre aspas, como "a informação" (que é sempre feminina):
      'Para Diego, a informação "Estado civil" veio como "Solteiro(a)"...'. Assim a frase nunca erra o gênero nem
      junta pedaços que não combinam (ex.: "...onde o funcionário trabalha de ninguém");
    - o valor lido vai entre aspas, e a frase termina com UMA pergunta;
    - nada de nome técnico de campo (nunca "estado_civil").

Como funciona: um dicionário liga cada regra do Validador (services/validador.py) a uma função pequena que monta a
frase. Regra sem função própria usa a mensagem do Validador com " Qual é o valor certo?" (ou " Está certo?", num
alerta).

Exemplos:
    perguntar("CPF_INVALIDO", "BLOQUEANTE", "cpf", "CPF", "123.456.789-00", "...", pessoa="Maria Lima")
        → 'O CPF de Maria veio "123.456.789-00", e o dígito verificador não bate. Qual é o CPF certo?'
    perguntar("OBRIGATORIO_SEM_COLUNA", "BLOQUEANTE", "codigo_unidade", "Código unidade", None, "...",
              descricao="Código da unidade (filial) onde o funcionário trabalha")
        → 'Nenhum funcionário deste arquivo veio com a informação "Código da unidade onde o funcionário trabalha".
           Se for a mesma para todos, qual é?'
"""
import re
from dataclasses import dataclass

# O começo do código das perguntas que a IA fez ao ler um documento (o mesmo de services/validador.py)
PREFIXO_DA_PERGUNTA_DA_IA = "PERGUNTA_DA_IA:"
# O "nome" das pendências do arquivo inteiro (services/acompanhamento.py): não é uma pessoa
SEM_PESSOA = "Arquivo inteiro"
# O começo do "nome" de quem veio sem nome no arquivo (services/acompanhamento.py: "Funcionário da linha 8")
SEM_NOME = "Funcionário da linha"
# Os finais de descrição que só repetem de quem é o dado (a frase já diz a pessoa)
FINAIS_DE_QUEM = (" do funcionário", " da funcionária", " da pessoa")
# As regras de dúvida de formato de uma coluna inteira (o valor lido são exemplos da coluna)
REGRAS_DE_FORMATO = ("DATA_AMBIGUA", "ZEROS_A_ESQUERDA")


@dataclass
class DadosDaPendencia:
    """O que as funções de pergunta usam de uma pendência."""

    severidade: str            # BLOQUEANTE ou ALERTA
    campo: str | None          # o nome técnico do campo (só para trocá-lo no texto padrão; nunca vai para a frase)
    informacao: str            # o nome do campo para a frase, entre aspas (ex.: "Estado civil")
    valor: str | None          # o valor lido, já no jeito da empresa (ex.: "123.456.789-00"), ou None
    mensagem: str              # a mensagem do Validador
    pessoa: str | None         # o primeiro nome da pessoa (ex.: "Diego"), ou None no arquivo inteiro
    palpite: str | None        # o item da lista que o agente acredita ser o certo (só quando é seguro), ou None
    quantidade: int = 1        # quantas pessoas vieram com este mesmo valor (mais de 1 = pergunta do grupo, ADR-120)
    igual_para_todos: bool = True   # False: a informação é de cada pessoa (a marcação do parâmetro)


# ---------------- Pedaços da frase ----------------

def primeiro_nome(nome: str | None) -> str | None:
    """O primeiro nome da pessoa. Ex.: "Diego Azevedo Azevedo" → "Diego"; "Arquivo inteiro", "Funcionário da linha 8"
    (pessoa sem nome no arquivo) ou vazio → None."""
    if not nome or nome == SEM_PESSOA or nome.startswith(SEM_NOME):
        return None
    return nome.split()[0]


def nome_da_informacao(descricao: str | None, rotulo: str) -> str:
    """O nome do campo para a frase: a DESCRIÇÃO do parâmetro, sem o que está entre parênteses e sem o final que só
    repete de quem é o dado; sem descrição, o rótulo curto. Com a 1ª letra maiúscula (vai entre aspas).

    Ex.: "Código da unidade (filial) onde o funcionário trabalha" → "Código da unidade onde o funcionário trabalha";
    "Data de nascimento do funcionário" → "Data de nascimento"; (None, "Tipo renda") → "Tipo renda".
    """
    texto = (descricao or "").strip()
    # Tira o que está entre parênteses (explicação para quem cadastra o parâmetro, não para a frase)
    texto = " ".join(re.sub(r"\([^)]*\)", " ", texto).split())
    # Tira o final "do funcionário" (a frase já diz de quem é)
    for final in FINAIS_DE_QUEM:
        if texto.endswith(final):
            texto = texto[:-len(final)]
    texto = texto or rotulo or "Dado"
    return texto[0].upper() + texto[1:]


def _de_quem(dados: DadosDaPendencia) -> str:
    """" de Diego", para entrar depois de um nome; sem pessoa, nada."""
    if not dados.pessoa:
        return ""
    return " de " + dados.pessoa


def _a_informacao(dados: DadosDaPendencia) -> str:
    """O começo da frase sobre um campo: 'Para Diego, a informação "Estado civil"' (sem pessoa: 'A informação ...')."""
    if dados.pessoa:
        return f'Para {dados.pessoa}, a informação "{dados.informacao}"'
    return f'A informação "{dados.informacao}"'


def _veio(dados: DadosDaPendencia) -> str:
    """ ' veio "X"', ou ' veio vazio' quando o arquivo não trouxe o valor."""
    if dados.valor:
        return f' veio "{dados.valor}"'
    return " veio vazio"


def _veio_como(dados: DadosDaPendencia) -> str:
    """ ' veio como "X"' (depois de "a informação ..."), ou ' veio vazia' sem valor."""
    if dados.valor:
        return f' veio como "{dados.valor}"'
    return " veio vazia"


def _numero_da_linha(mensagem: str) -> str | None:
    """O número da linha citado na mensagem do Validador. Ex.: "O mesmo CPF já aparece na linha 7." → "7"."""
    encontrado = re.search(r"linha (\d+)", mensagem)
    if encontrado:
        return encontrado.group(1)
    return None


def _quem_ou_esta_pessoa(dados: DadosDaPendencia) -> str:
    """O primeiro nome, ou "Esta pessoa" quando não há nome."""
    return dados.pessoa or "Esta pessoa"


# ---------------- Uma função por regra ----------------

def _cpf_invalido(dados: DadosDaPendencia) -> str:
    """Ex.: 'O CPF de Maria veio "123.456.789-00", e o dígito verificador não bate. Qual é o CPF certo?'"""
    return f"O CPF{_de_quem(dados)}{_veio(dados)}, e o dígito verificador não bate. Qual é o CPF certo?"


def _cnpj_invalido(dados: DadosDaPendencia) -> str:
    """Ex.: 'Para Maria, a informação "CNPJ da empresa empregadora" veio como "10433218000100", e o dígito verificador
    não bate. Qual é o CNPJ certo?'"""
    return f"{_a_informacao(dados)}{_veio_como(dados)}, e o dígito verificador não bate. Qual é o CNPJ certo?"


def _cnpj_de_outra_empresa(dados: DadosDaPendencia) -> str:
    """Ex.: 'Para Maria, a informação "CNPJ da empresa empregadora" veio como "...", que não é da sua empresa. Qual é o
    CNPJ certo?'"""
    return f"{_a_informacao(dados)}{_veio_como(dados)}, que não é da sua empresa. Qual é o CNPJ certo?"


def _cnpj_do_grupo(dados: DadosDaPendencia) -> str:
    """Ex.: 'Para Maria, a informação "CNPJ da empresa empregadora" veio como "...", que não está no cadastro da sua
    empresa. É de uma empresa do seu grupo?'"""
    return (f"{_a_informacao(dados)}{_veio_como(dados)}, que não está no cadastro da sua empresa. "
            "É de uma empresa do seu grupo?")


def _cep_invalido(dados: DadosDaPendencia) -> str:
    """Ex.: 'Para Ana, a informação "CEP da casa" veio como "1310100", com 7 dígitos (o certo é 8; pode ter perdido um
    zero). Qual é o CEP certo?'"""
    digitos = len(re.sub(r"\D", "", dados.valor or ""))
    return (f"{_a_informacao(dados)}{_veio_como(dados)}, com {digitos} dígitos (o certo é 8; pode ter perdido um "
            "zero). Qual é o CEP certo?")


def _obrigatorio_vazio(dados: DadosDaPendencia) -> str:
    """Ex.: 'No arquivo, Diego veio sem a informação "Cargo ou função". Qual é?'"""
    return f'No arquivo, {_quem_ou_esta_pessoa(dados)} veio sem a informação "{dados.informacao}". Qual é?'


def _obrigatorio_sem_coluna(dados: DadosDaPendencia) -> str:
    """Ex. (dado da empresa): 'Nenhum funcionário deste arquivo veio com a informação "Código da unidade onde o
    funcionário trabalha". Se for a mesma para todos, qual é?'
    Ex. (de cada pessoa, a marcação do parâmetro): 'O arquivo não trouxe a informação
    "CPF", que é única por funcionário e não pode ser a mesma para todos. Quer informar pessoa a pessoa ou enviar o
    arquivo de novo com essa coluna?' (os dois botões do cartão, ADR-124)"""
    if not dados.igual_para_todos:
        return (f'O arquivo não trouxe a informação "{dados.informacao}", que é única por funcionário e não pode ser a '
                "mesma para todos. Quer informar pessoa a pessoa ou enviar o arquivo de novo com essa coluna?")
    return (f'Nenhum funcionário deste arquivo veio com a informação "{dados.informacao}". Se for a mesma para todos, '
            "qual é?")


def _valor_nao_convertido(dados: DadosDaPendencia) -> str:
    """O valor não foi entendido. Numa lista fechada, com ou sem palpite; nos outros campos, o motivo.

    Ex.: 'Para Diego, a informação "Estado civil" veio como "Solteiro(a)", que não está entre as opções aceitas.
    Acredito que o certo é "Solteiro". Posso usar?'; 'Para Ana, a informação "Data de nascimento" veio como
    "31/02/1990", que não deu para entender (data inexistente). Qual é o valor certo?'
    """
    # Várias pessoas com o mesmo valor: uma pergunta só, para todas
    if dados.quantidade > 1:
        return _valor_nao_convertido_do_grupo(dados)
    comeco = f"{_a_informacao(dados)}{_veio_como(dados)}"
    # Campo de lista: com palpite seguro, o agente propõe; sem, pede para escolher
    if "fora da lista" in dados.mensagem:
        if dados.palpite:
            return (f'{comeco}, que não está entre as opções aceitas. Acredito que o certo é "{dados.palpite}". '
                    "Posso usar?")
        return f"{comeco}, que não está entre as opções aceitas. Qual destas opções é a certa?"
    # O motivo do Normalizador fica entre o primeiro "(" depois de "não reconhecido" e o último ")"
    motivo = re.search(r"não reconhecido \((.*)\)\.?$", dados.mensagem)
    if motivo:
        return f"{comeco}, que não deu para entender ({motivo.group(1)}). Qual é o valor certo?"
    return f"{comeco}, que não deu para entender. Qual é o valor certo?"


def _valor_nao_convertido_do_grupo(dados: DadosDaPendencia) -> str:
    """O mesmo valor fora da lista em várias pessoas do arquivo: uma pergunta para todas (ADR-120), sem nomes.

    Ex.: '23 pessoas deste arquivo vieram com a informação "Estado civil" como "Divorciado(a)", que não está entre as
    opções aceitas. Acredito que o certo é "Divorciado" para todas. Posso usar?'
    """
    comeco = (f'{dados.quantidade} pessoas deste arquivo vieram com a informação "{dados.informacao}" como '
              f'"{dados.valor}", que não está entre as opções aceitas.')
    # Com palpite seguro, o agente propõe; sem, pede para escolher a opção que vale para todas
    if dados.palpite:
        return f'{comeco} Acredito que o certo é "{dados.palpite}" para todas. Posso usar?'
    return f"{comeco} Qual destas opções vale para todas?"


def _nascimento_no_futuro(dados: DadosDaPendencia) -> str:
    """Ex.: 'A data de nascimento de Ana veio "05/01/2030", que está no futuro. Qual é a data certa?'"""
    return f"A data de nascimento{_de_quem(dados)}{_veio(dados)}, que está no futuro. Qual é a data certa?"


def _admissao_antes_do_nascimento(dados: DadosDaPendencia) -> str:
    """Ex.: 'A data de admissão de Ana veio "01/03/1980", antes do nascimento. Qual é a data certa?'"""
    return f"A data de admissão{_de_quem(dados)}{_veio(dados)}, antes do nascimento. Qual é a data certa?"


def _admissao_antes_dos_14(dados: DadosDaPendencia) -> str:
    """Ex.: 'Com a admissão em "01/03/2020", Ana tinha 12 anos (o mínimo é 14). Está certo?'"""
    idade = re.search(r"Admissão com (\d+) anos", dados.mensagem)
    anos = f"{idade.group(1)} anos" if idade else "menos de 14 anos"
    return f'Com a admissão em "{dados.valor}", {_quem_ou_esta_pessoa(dados)} tinha {anos} (o mínimo é 14). Está certo?'


def _efetivacao_antes_da_admissao(dados: DadosDaPendencia) -> str:
    """Ex.: 'A data de efetivação de Ana veio "01/01/2020", antes da admissão. Está certa?'"""
    return f"A data de efetivação{_de_quem(dados)}{_veio(dados)}, antes da admissão. Está certa?"


def _pessoa_duplicada(dados: DadosDaPendencia) -> str:
    """Ex.: 'Diego aparece duas vezes no arquivo (a outra é a linha 7). Posso tirar esta linha?'"""
    linha = _numero_da_linha(dados.mensagem)
    onde = f" (a outra é a linha {linha})" if linha else ""
    return f"{_quem_ou_esta_pessoa(dados)} aparece duas vezes no arquivo{onde}. Posso tirar esta linha?"


def _matricula_duplicada(dados: DadosDaPendencia) -> str:
    """Ex.: 'A matrícula de Diego veio "00012", que já é de outra pessoa (linha 4). Qual é a matrícula certa?'"""
    linha = _numero_da_linha(dados.mensagem)
    onde = f" (linha {linha})" if linha else ""
    return f"A matrícula{_de_quem(dados)}{_veio(dados)}, que já é de outra pessoa{onde}. Qual é a matrícula certa?"


def _matricula_ja_homologada(dados: DadosDaPendencia) -> str:
    """Ex.: 'A matrícula de Diego veio "00012", que já é de outra pessoa cadastrada na empresa. Está certa?'"""
    return f"A matrícula{_de_quem(dados)}{_veio(dados)}, que já é de outra pessoa cadastrada na empresa. Está certa?"


def _pessoa_em_outro_envio(dados: DadosDaPendencia) -> str:
    """Ex.: 'Diego também está no arquivo "folha_set.xlsx", que ainda não foi ao banco. Posso tirar Diego deste
    arquivo?'"""
    arquivo = re.search(r"\(arquivo (.+)\)\.?$", dados.mensagem)
    qual = f' no arquivo "{arquivo.group(1)}"' if arquivo else " em outro arquivo"
    quem = _quem_ou_esta_pessoa(dados)
    tirar = f"Posso tirar {dados.pessoa} deste arquivo?" if dados.pessoa else "Posso tirar esta pessoa deste arquivo?"
    return f"{quem} também está{qual}, que ainda não foi ao banco. {tirar}"


def _renda_nao_positiva(dados: DadosDaPendencia) -> str:
    """Ex.: 'A renda de João veio "R$ 0,00", zerada ou negativa. Qual é a renda certa?'"""
    return f"A renda{_de_quem(dados)}{_veio(dados)}, zerada ou negativa. Qual é a renda certa?"


def _renda_fora_do_cargo(dados: DadosDaPendencia) -> str:
    """Ex.: 'A renda de João veio "R$ 48.000,00", bem acima do comum para o cargo. Está certa?'

    Acima ou abaixo vem das "vezes" que o Validador escreveu ("Renda 9,6x a mediana..."): mais de 1 é acima.
    """
    vezes = re.search(r"Renda (\d+(?:,\d+)?)x", dados.mensagem)
    lado = "fora do"
    if vezes:
        lado = "bem acima do" if float(vezes.group(1).replace(",", ".")) > 1 else "bem abaixo do"
    return f"A renda{_de_quem(dados)}{_veio(dados)}, {lado} comum para o cargo. Está certa?"


def _valor_fora_da_faixa(dados: DadosDaPendencia) -> str:
    """O valor fora do mínimo ou do máximo do parâmetro (ADR-128): um alerta, que se confirma ou se corrige.

    Ex.: 'Para João, a informação "Salário bruto mensal" veio como "R$ 350,00", abaixo do mínimo do parâmetro
    (R$ 500,00). Está certo?'
    """
    # O lado e o limite vêm da mensagem do Validador ("Valor de valor_renda abaixo do mínimo do parâmetro (R$ 500,00).")
    lado = re.search(r"((?:abaixo|acima) d[oa] (?:mínimo|máximo) do parâmetro \([^)]*\))", dados.mensagem)
    fora = lado.group(1) if lado else "fora da faixa esperada pelo banco"
    return f"{_a_informacao(dados)}{_veio_como(dados)}, {fora}. Está certo?"


def _data_ambigua(dados: DadosDaPendencia) -> str:
    """Ex.: 'As datas desta coluna vieram assim: "03/04/1990, 05/06/1985". Estão em dia/mês ou mês/dia?'"""
    if dados.valor:
        return f'As datas desta coluna vieram assim: "{dados.valor}". Estão em dia/mês ou mês/dia?'
    return "As datas desta coluna estão em dia/mês ou mês/dia?"


def _zeros_a_esquerda(dados: DadosDaPendencia) -> str:
    """Ex.: 'As matrículas vieram assim: "12, 345", e podem ter perdido zeros à esquerda. Com quantos dígitos elas
    ficam?'"""
    exemplos = f' assim: "{dados.valor}",' if dados.valor else ""
    return f"As matrículas vieram{exemplos} e podem ter perdido zeros à esquerda. Com quantos dígitos elas ficam?"


def _conferencia_de_totais(dados: DadosDaPendencia) -> str:
    """A leitura não bateu com o arquivo: o caminho é enviar de novo."""
    return "A leitura não bateu com o total de linhas do arquivo. Quer descartar e enviar o arquivo de novo?"


# Cada regra do Validador e a função que monta a pergunta dela
PERGUNTA_POR_REGRA = {
    "CPF_INVALIDO": _cpf_invalido,
    "CNPJ_INVALIDO": _cnpj_invalido,
    "CNPJ_DE_OUTRA_EMPRESA": _cnpj_de_outra_empresa,
    "CNPJ_DO_GRUPO_A_CONFIRMAR": _cnpj_do_grupo,
    "CEP_INVALIDO": _cep_invalido,
    "OBRIGATORIO_VAZIO": _obrigatorio_vazio,
    "OBRIGATORIO_SEM_COLUNA": _obrigatorio_sem_coluna,
    "VALOR_NAO_CONVERTIDO": _valor_nao_convertido,
    "NASCIMENTO_NO_FUTURO": _nascimento_no_futuro,
    "ADMISSAO_ANTES_DO_NASCIMENTO": _admissao_antes_do_nascimento,
    "ADMISSAO_ANTES_DOS_14": _admissao_antes_dos_14,
    "EFETIVACAO_ANTES_DA_ADMISSAO": _efetivacao_antes_da_admissao,
    "PESSOA_DUPLICADA": _pessoa_duplicada,
    "MATRICULA_DUPLICADA": _matricula_duplicada,
    "MATRICULA_JA_HOMOLOGADA": _matricula_ja_homologada,
    "PESSOA_EM_OUTRO_ENVIO": _pessoa_em_outro_envio,
    "RENDA_NAO_POSITIVA": _renda_nao_positiva,
    "RENDA_FORA_DO_CARGO": _renda_fora_do_cargo,
    "VALOR_FORA_DA_FAIXA": _valor_fora_da_faixa,
    "DATA_AMBIGUA": _data_ambigua,
    "ZEROS_A_ESQUERDA": _zeros_a_esquerda,
    "CONFERENCIA_DE_TOTAIS": _conferencia_de_totais,
}


def _pergunta_da_ia(dados: DadosDaPendencia) -> str:
    """A pergunta que a própria IA fez ao ler o documento (ADR-73): já é uma pergunta; garante o "?" no fim."""
    texto = dados.mensagem.strip()
    if texto.endswith("?"):
        return texto
    return texto.rstrip(".") + "?"


def mensagem_sem_nome_tecnico(mensagem: str, campo: str | None, informacao: str) -> str:
    """A mensagem do Validador com o nome técnico do campo trocado pelo nome entre aspas.

    Ex.: ("Campo obrigatório estado_civil vazio.", "estado_civil", "Estado civil") →
    'Campo obrigatório "Estado civil" vazio.'
    """
    if not campo:
        return mensagem.strip()
    return mensagem.strip().replace(campo, f'"{informacao}"')


def _pergunta_padrao(dados: DadosDaPendencia) -> str:
    """Regra sem função própria: a mensagem do Validador, sem nome técnico de campo, com a pergunta no fim."""
    texto = mensagem_sem_nome_tecnico(dados.mensagem, dados.campo, dados.informacao)
    # A pergunta: num alerta, confirmar; nos outros, o valor certo
    if dados.severidade == "ALERTA":
        return texto + " Está certo?"
    return texto + " Qual é o valor certo?"


def perguntar(regra_id: str, severidade: str, campo: str | None, rotulo: str, valor: str | None, mensagem: str,
              pessoa: str | None = None, palpite: str | None = None, descricao: str | None = None,
              quantidade: int = 1, igual_para_todos: bool = True) -> str:
    """A frase de reserva da pendência, com o valor lido dentro, terminando em pergunta.

    Recebe: a regra e a severidade do achado; o campo técnico e o rótulo dele; o valor lido (já no jeito da empresa,
    ver acompanhamento.valor_lido_para_a_tela; None se o arquivo veio sem ele); a mensagem do Validador; o nome da
    pessoa (o primeiro nome entra na frase; "Arquivo inteiro" ou None, nada), o palpite seguro de um campo de lista,
    a descrição do campo no parâmetro (o nome da informação na frase; sem ela, o rótulo), quantas pessoas vieram com
    o mesmo valor (mais de 1: a pergunta do grupo, sem nome, ADR-120) e se a informação pode ser a mesma para todos
    (False: é de cada pessoa, e a frase nunca pede um valor para todos; a marcação do parâmetro).
    Devolve: a frase. Ex.: 'No arquivo, Diego veio sem a informação "Cargo ou função". Qual é?'
    """
    informacao = nome_da_informacao(descricao, rotulo)
    dados = DadosDaPendencia(severidade, campo, informacao, valor, mensagem, primeiro_nome(pessoa), palpite,
                             quantidade, igual_para_todos)
    # As perguntas da IA têm o campo no código da regra ("PERGUNTA_DA_IA:cpf")
    if regra_id.startswith(PREFIXO_DA_PERGUNTA_DA_IA):
        return _pergunta_da_ia(dados)
    funcao = PERGUNTA_POR_REGRA.get(regra_id, _pergunta_padrao)
    return funcao(dados)
