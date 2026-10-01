"""A legenda dos status: o que quer dizer cada situação de cada grade, numa fonte única.

Para que serve: em cima de toda grade que tem a coluna "Situação", a tela mostra um "i" (front/js/legenda_dos_status.js).
Ao passar o mouse nele, ou clicar, abre um balão que explica cada situação daquela grade. As explicações ficam SÓ aqui,
ao lado de cada situação, e chegam à tela por duas rotas (api/rotas_legenda_dos_status.py):
    - a do banco, com as grades do Portal Interno: a carteira de empresas (Início e Empresas), os funcionários da
      Visão geral, os usuários da empresa e as pessoas de um envio;
    - a da empresa, só com as grades que ela vê: os funcionários de Acompanhar, as colunas lidas e a conferência da
      lista em Cadastrar.

De onde vem o texto de cada situação:
    - quando a situação nasce no servidor, o texto é a MESMA constante que o serviço usa (ex.:
      acompanhamento.SITUACAO_PENDENTE). Se o nome mudar lá, a legenda muda junto;
    - a situação da empresa na carteira nasce em services/portal_do_banco.py (_situacao_da_empresa), e as que nascem na
      tela (o selo dos usuários, o das pessoas do envio e dois da leitura das colunas) são escritas aqui com o mesmo
      texto e a mesma cor. O teste tests/test_legenda_dos_status.py confere que os dois lados continuam iguais.
A cor ("classe") é a do selo que a grade mostra, para a pessoa reconhecer o selo no balão.

Regras dos textos: a linguagem de quem usa a tela; nenhuma ação atribuída à "IA" (quem age é o agente, pelo nome:
o Agente Interpretador lê as colunas, e o Agente de validação conversa sobre as pendências); nenhum dado de empresa ou
de pessoa. É texto fixo, igual para todos, e por isso não precisa do banco de dados.
"""
from models.contratos import StatusMapeamento
from services import acompanhamento, auth, cadastro, contas_abertas

# As cores dos selos, as mesmas classes do front/css/estilos.css
# Selo verde: algo concluído
SELO_VERDE = "selo-sucesso"
# Selo laranja: algo que pede atenção
SELO_LARANJA = "selo-atencao"
# Selo claro da cor da marca: algo em andamento
SELO_DA_MARCA = "selo-marca"
# Selo cinza: algo neutro
SELO_CINZA = "selo-neutro"
# Selo verde cheio: a conta da pessoa já existe (a última situação de um funcionário)
SELO_VERDE_CHEIO = "selo-conta-aberta"
# Selo azul da coluna em que a empresa trocou o campo
SELO_AJUSTADO = "selo-ajustado"
# Selo da coluna dividida em partes
SELO_DIVIDIDO = "selo-dividido"

# As situações que nascem na tela, com o mesmo texto de lá (o teste confere que os dois lados batem)
# O selo dos usuários (front/js/banco_empresas.js, SELOS_DOS_USUARIOS)
USUARIO_ATIVO = "Ativo"
USUARIO_COM_SENHA_PROVISORIA = "Senha resetada (aguardando nova)"
USUARIO_SUSPENSO_SEM_USO = "Suspenso (sem uso)"
USUARIO_COM_ACESSO_VENCIDO = "Acesso vencido"
USUARIO_COM_SENHA_PROVISORIA_VENCIDA = "Senha provisória vencida"
USUARIO_DESATIVADO = "Desativado"
# O selo das pessoas de um envio (front/js/banco_envios.js, SELOS_DAS_SITUACOES)
PESSOA_PRONTA = "Pronto"
PESSOA_COM_ALERTA = "Alerta"
PESSOA_APONTADA = "Apontado por você"
# Duas situações de uma coluna lida (front/js/cadastrar_real.js)
COLUNA_AJUSTADA_COM_TIPO_A_CONFERIR = "Ajustado · confira o tipo"
COLUNA_FORA_POR_NAO_SER_OBRIGATORIA = "Fica de fora (não é obrigatória)"
# A situação de uma pessoa na conferência da lista (front/js/cadastrar_conferencia_real.js)
PESSOA_SEM_PENDENCIA = "Tudo certo"
# Na conferência, a grade escreve quantas pendências a pessoa tem ("1 pendência", "2 pendências"): a legenda resume
PESSOA_COM_PENDENCIA = "1 pendência ou mais"

# A situação da empresa na carteira (services/portal_do_banco.py, _situacao_da_empresa)
EMPRESA_SEM_CARGA = "Sem carga"
EMPRESA_COM_PENDENCIA = "Com pendência"
EMPRESA_EM_ANDAMENTO = "Em andamento"
EMPRESA_EM_DIA = "Em dia"


def _situacao(texto: str, classe: str, explicacao: str) -> dict:
    """Uma situação da legenda: o texto do selo, a cor dele e o que ela quer dizer.

    Recebe: texto (o que o selo mostra); classe (a cor do selo); explicacao (uma ou duas frases).
    Devolve: {"texto", "classe", "explicacao"}.
    Exemplo: _situacao("Pendente", "selo-atencao", "Falta a empresa resolver...") →
    {"texto": "Pendente", "classe": "selo-atencao", "explicacao": "Falta a empresa resolver..."}.
    """
    return {"texto": texto, "classe": classe, "explicacao": explicacao}


def situacoes_dos_funcionarios() -> list[dict]:
    """As situações de um funcionário na lista (Acompanhar, na empresa; a Visão geral da empresa, no banco).

    Devolve: a lista, na ordem da jornada (a mesma do filtro da tela): Aguardando envio, Pendente, Em análise,
    Cadastrado, Conta aberta e Já é correntista. As duas últimas só o banco muda, ao mandar a conta da pessoa
    (ADR-113, ADR-123).
    """
    # Os textos das duas últimas vêm do tipo de conta que o banco informa (1 = conta nova, 2 = já era cliente)
    conta_aberta = contas_abertas.SITUACAO_NA_EMPRESA_DO_TIPO[contas_abertas.TIPO_NOVA_CONTA]
    ja_e_correntista = contas_abertas.SITUACAO_NA_EMPRESA_DO_TIPO[contas_abertas.TIPO_CORRENTISTA]
    return [
        _situacao(acompanhamento.SITUACAO_AGUARDANDO_ENVIO, SELO_CINZA,
                  "Os dados desta pessoa estão completos. O envio vai ao banco depois que as pendências das outras "
                  "pessoas forem resolvidas."),
        _situacao(acompanhamento.SITUACAO_PENDENTE, SELO_LARANJA,
                  "Falta a empresa resolver um dado desta pessoa (uma pendência)."),
        _situacao(acompanhamento.SITUACAO_EM_ANALISE, SELO_DA_MARCA,
                  "O banco está conferindo o envio desta pessoa."),
        _situacao(acompanhamento.SITUACAO_CADASTRADO, SELO_VERDE,
                  "Já está no cadastro do banco. Falta abrir a conta."),
        _situacao(conta_aberta, SELO_VERDE_CHEIO,
                  "O banco abriu uma conta nova para a pessoa. É nela que o salário é pago."),
        _situacao(ja_e_correntista, SELO_VERDE_CHEIO,
                  "A pessoa já era cliente do banco. O banco informou a conta que ela já tinha, e é nela que o "
                  "salário é pago."),
    ]


def situacoes_das_empresas() -> list[dict]:
    """As situações de uma empresa na carteira do banco (o Início e a lista da Carteira, em Empresas).

    Devolve: a lista, na ordem em que a situação é decidida (services/portal_do_banco.py, _situacao_da_empresa): sem
    envio nenhum; com um envio com pendência; com um envio ainda a caminho; e o resto, em dia.
    """
    return [
        _situacao(EMPRESA_SEM_CARGA, SELO_LARANJA,
                  "A empresa ainda não enviou nenhum arquivo de funcionários. Vale um contato para ajudar no primeiro "
                  "envio."),
        _situacao(EMPRESA_COM_PENDENCIA, SELO_LARANJA,
                  "Um envio da empresa tem dados a corrigir. Quem corrige é a empresa, antes de o envio vir ao "
                  "banco."),
        _situacao(EMPRESA_EM_ANDAMENTO, SELO_DA_MARCA,
                  "Um envio da empresa ainda não terminou: ela está conferindo a leitura, o envio espera a avaliação "
                  "do banco (aba Envios) ou voltou do banco para ajuste."),
        _situacao(EMPRESA_EM_DIA, SELO_VERDE,
                  "Todos os envios da empresa terminaram: cadastrados, ou descartados pela própria empresa. Nada "
                  "espera por você nem por ela."),
    ]


def situacoes_dos_usuarios() -> list[dict]:
    """As situações de uma pessoa da empresa na aba Usuários do banco (o acesso dela ao Portal Empresa).

    Devolve: a lista: ativo, com a senha provisória, com a senha provisória vencida, suspenso por falta de uso, com o
    acesso vencido e desativado. Os prazos vêm das mesmas constantes que suspendem o acesso e que vencem a senha
    provisória (services/auth.py, ADR-146 e ADR-154).
    """
    # Os prazos do acesso da empresa, em dias (ex.: 90 e 365), e o da senha provisória, em horas (ex.: 48)
    dias_sem_uso = str(auth.DIAS_SEM_USO_PARA_SUSPENDER)
    dias_de_validade = str(auth.DIAS_DE_VALIDADE_DO_ACESSO)
    horas_da_senha_provisoria = str(auth.VALIDADE_DA_SENHA_PROVISORIA_HORAS)
    return [
        _situacao(USUARIO_ATIVO, SELO_VERDE,
                  "A pessoa entra no Portal Empresa com a própria senha."),
        _situacao(USUARIO_COM_SENHA_PROVISORIA, SELO_DA_MARCA,
                  "O banco criou o acesso ou gerou uma senha provisória nova, que vale por " +
                  horas_da_senha_provisoria + " horas. No primeiro acesso, o sistema pede para a pessoa criar a "
                  "própria senha, e o selo some quando ela cria."),
        _situacao(USUARIO_COM_SENHA_PROVISORIA_VENCIDA, SELO_LARANJA,
                  "A senha provisória passou das " + horas_da_senha_provisoria + " horas sem ser trocada, e o login "
                  "recusa. A pessoa só entra com uma nova: clique em Nova senha provisória."),
        _situacao(USUARIO_SUSPENSO_SEM_USO, SELO_LARANJA,
                  "A pessoa ficou mais de " + dias_sem_uso + " dias sem entrar, e o acesso foi suspenso sozinho. "
                  "Ela só entra de novo depois que você clicar em Reativar."),
        _situacao(USUARIO_COM_ACESSO_VENCIDO, SELO_LARANJA,
                  "O acesso vale por " + dias_de_validade + " dias depois de criado ou renovado, e esse prazo "
                  "passou. Reativar renova o acesso."),
        _situacao(USUARIO_DESATIVADO, SELO_CINZA,
                  "O banco desativou o acesso. A pessoa não entra até ser reativada."),
    ]


def situacoes_das_pessoas_do_envio() -> list[dict]:
    """As situações de uma pessoa de um envio, na avaliação do banco (aba Envios).

    Devolve: a lista: pronta para aprovar, com um alerta que a empresa confirmou e com um problema apontado pelo
    especialista (ADR-121).
    """
    return [
        _situacao(PESSOA_PRONTA, SELO_VERDE,
                  "Nada a conferir nesta pessoa: ela entra no cadastro quando você aprovar o envio."),
        _situacao(PESSOA_COM_ALERTA, SELO_LARANJA,
                  "O sistema achou um dado fora do comum nesta pessoa (ex.: o salário fora da faixa da profissão), e "
                  "a empresa confirmou que está certo antes de enviar. Confira e decida: aprovar com o envio ou "
                  "apontar um problema."),
        _situacao(PESSOA_APONTADA, SELO_DA_MARCA,
                  "Você apontou um problema nesta pessoa. Na decisão do envio, ela volta para a empresa ajustar, e as "
                  "outras podem seguir para o cadastro. O Desfazer tira o apontamento."),
    ]


def situacoes_das_colunas() -> list[dict]:
    """As situações de uma coluna do arquivo na leitura das colunas (Cadastrar, as duas tabelas das colunas lidas).

    Devolve: a lista, na ordem em que a empresa costuma ver: as reconhecidas e as em dúvida, as que ela ajustou, as
    divididas e as que ficam de fora. Os textos que nascem no servidor são as constantes de services/cadastro.py.
    """
    return [
        _situacao(cadastro.SITUACAO_DA_COLUNA[StatusMapeamento.PROPOSTO], SELO_VERDE,
                  "O agente que leu o arquivo reconheceu o campo do cadastro desta coluna. Se não for esse, troque o "
                  "campo."),
        _situacao(cadastro.SITUACAO_DA_COLUNA[StatusMapeamento.AMBIGUO], SELO_LARANJA,
                  "O Agente Interpretador ficou em dúvida entre alguns campos. Escolha o certo para seguir."),
        _situacao(cadastro.SITUACAO_AJUSTADA_PELA_EMPRESA, SELO_AJUSTADO,
                  "Você trocou o campo que o agente propôs. Vale a sua escolha."),
        _situacao(COLUNA_AJUSTADA_COM_TIPO_A_CONFERIR, SELO_LARANJA,
                  "Você trocou o campo, mas parte dos valores da coluna não serve para ele (ex.: um CPF num campo de "
                  "data). Se aceitar assim, esses valores ficam em branco; num campo obrigatório, viram pendência."),
        _situacao(cadastro.SITUACAO_DIVIDIDA_PELA_IA, SELO_DIVIDIDO,
                  "O Agente Interpretador separou esta coluna em partes, uma por campo (ex.: o endereço inteiro numa "
                  "célula vira rua, número e cidade). Confira a prévia logo abaixo da coluna."),
        _situacao(cadastro.SITUACAO_PARTE_DA_IA, SELO_DIVIDIDO,
                  "Esta linha é uma das partes de uma coluna que o Agente Interpretador separou."),
        _situacao(cadastro.SITUACAO_DIVIDIDA_PELA_EMPRESA, SELO_CINZA,
                  "Você separou esta coluna em partes, uma por campo."),
        _situacao(cadastro.SITUACAO_DA_COLUNA[StatusMapeamento.NAO_MAPEADO], SELO_CINZA,
                  "A coluna não corresponde a nenhum campo do cadastro e não vai para o banco. Se ela tiver um dado "
                  "do cadastro, escolha o campo."),
        _situacao(COLUNA_FORA_POR_NAO_SER_OBRIGATORIA, SELO_CINZA,
                  "O Agente Interpretador ficou em dúvida entre campos que não são obrigatórios. A coluna fica de "
                  "fora do cadastro, sem pergunta, e o valor fica guardado no detalhe da pessoa. Se quiser, escolha "
                  "um dos campos."),
    ]


def situacoes_da_conferencia() -> list[dict]:
    """As situações de uma pessoa na conferência da lista, antes de enviar ao banco (Cadastrar).

    Devolve: a lista: sem pendência e com pendência. Na grade, a segunda diz quantas ("1 pendência", "3 pendências").
    """
    return [
        _situacao(PESSOA_SEM_PENDENCIA, SELO_VERDE,
                  "Nenhuma pendência nesta pessoa: ela vai para o banco do jeito que está na lista."),
        _situacao(PESSOA_COM_PENDENCIA, SELO_LARANJA,
                  "Falta resolver um ou mais dados desta pessoa. Responda ao Agente de validação na conversa logo "
                  "abaixo dela, ou use Corrigir."),
    ]


def legendas_do_banco() -> dict:
    """As legendas das grades do Portal Interno (a rota GET /api/banco/legenda_dos_status).

    Devolve: {grade: [situações]}, com as grades "empresas", "funcionarios", "usuarios" e "pessoas_do_envio".
    Ex.: legendas_do_banco()["usuarios"][0] → {"texto": "Ativo", "classe": "selo-sucesso", "explicacao": "..."}.
    """
    return {
        "empresas": situacoes_das_empresas(),
        "funcionarios": situacoes_dos_funcionarios(),
        "usuarios": situacoes_dos_usuarios(),
        "pessoas_do_envio": situacoes_das_pessoas_do_envio(),
    }


def legendas_da_empresa() -> dict:
    """As legendas das grades do Portal Empresa (a rota GET /api/empresa/legenda_dos_status).

    Devolve: {grade: [situações]}, só com as grades que a empresa vê: "funcionarios", "colunas" e "conferencia". Nada
    das grades do banco (a carteira, os usuários e a avaliação dos envios).
    """
    return {
        "funcionarios": situacoes_dos_funcionarios(),
        "colunas": situacoes_das_colunas(),
        "conferencia": situacoes_da_conferencia(),
    }
