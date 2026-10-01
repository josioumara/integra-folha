"""O cadastro das empresas da carteira no banco de dados (ADR-69, passo 18).

Para que serve: as empresas não ficam só num arquivo fixo (data/mock/empresas.json): ficam na tabela
`empresas`, que começa com as 6 empresas fictícias do arquivo (a "semente") e cresce quando o especialista cadastra uma
empresa nova no Portal do Banco. O especialista também edita os dados (CNPJ, endereço comercial, domínio de e-mail).
O kit de endomarketing de cada empresa (padrão Santander ou kit próprio, com o texto e as cores) fica aqui só como
CÓPIA DERIVADA: a fonte única é a KB "Kit da marca" da empresa, e quem grava o kit aqui é o "aplicar na empresa", ao
publicar ou retirar essa KB (services/kbs_publicacao.py). A semente já nasce com o kit da KB dos arquivos do projeto.

Como o resto da aplicação enxerga as empresas: pela mesma função de sempre, dados_mock.empresas(), que passou a ler
desta tabela (lista_em_memoria abaixo). A lista fica guardada em memória por alguns segundos, para não abrir o banco
a cada nome de empresa mostrado numa tela, e é renovada na hora quando uma empresa é criada ou editada neste processo.
Outro processo (ex.: um segundo servidor da API) vê a mudança em até TEMPO_DA_LISTA_EM_MEMORIA segundos.

Regras: só o perfil BANCO cadastra e edita (operação editar_empresas); o CNPJ precisa ter os dígitos verificadores
certos e não pode repetir; o domínio de e-mail é o que o convite de usuário exige (ninguém de fora da empresa).

CNPJs da empresa (ADR-77): a tabela `empresas` guarda o CNPJ principal (a sede). A tabela `cnpjs_das_empresas` guarda
os outros, quando o banco tem a informação: filiais (mesma raiz, os 8 primeiros dígitos) e empresas do grupo (outra
raiz). O especialista cadastra e tira esses CNPJs; a empresa também faz um entrar sozinho quando confirma, num envio,
que um CNPJ repetido no arquivo é do grupo. O Validador usa essa lista (cnpjs_conhecidos) para não perguntar de novo.
"""
import json
import re
import time
import unicodedata
from datetime import date, datetime, timezone

from services import auth, dados_mock, kbs_endomarketing, kit_de_marca
from services.detector_de_dados import SIGLAS_DOS_ESTADOS
from services.documentos import cnpj_valido
from services.permissoes import autorizar

# Por quanto tempo (em segundos) a lista de empresas fica guardada em memória antes de ser lida de novo
TEMPO_DA_LISTA_EM_MEMORIA = 5
# Os kits de endomarketing que o banco pode escolher
KIT_PADRAO, KIT_PROPRIO = "padrao", "proprio"
# Quem gravou as empresas da semente (e o logo delas)
AUTOR_DA_SEMENTE = "semente (data/mock/empresas.json)"
# Os tipos de CNPJ além do principal (ADR-77): filial (mesma raiz da sede) ou empresa do grupo (outra raiz)
CNPJ_FILIAL, CNPJ_GRUPO = "FILIAL", "GRUPO"
# Quem registrou o CNPJ: o especialista do banco, na aba Empresas, ou a própria empresa, ao confirmar no envio
ORIGEM_BANCO, ORIGEM_EMPRESA = "BANCO", "EMPRESA"
# As colunas da tabela, na ordem das consultas
COLUNAS = ("empresa_id", "nome", "setor", "municipio", "uf", "cnpj", "endereco_comercial", "dominio_email",
           "contrato_desde", "kit_escolhido", "kit_texto", "kit_cores")

# A lista guardada em memória e quando ela foi lida (0 = nunca)
_lista_guardada = {"empresas": None, "lida_em": 0.0}


def _preparar(conexao) -> None:
    """Cria a tabela das empresas e, na primeira vez, põe as 6 empresas da semente, com o kit da KB do kit de cada uma."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS empresas (
               empresa_id          TEXT PRIMARY KEY,
               nome                TEXT NOT NULL,
               setor               TEXT NOT NULL,
               municipio           TEXT NOT NULL,
               uf                  TEXT NOT NULL,
               cnpj                TEXT NOT NULL,
               endereco_comercial  TEXT NOT NULL,
               dominio_email       TEXT NOT NULL,
               contrato_desde      TEXT NOT NULL,
               kit_escolhido       TEXT NOT NULL,
               kit_texto           TEXT NOT NULL,
               kit_cores           TEXT NOT NULL,
               criado_em           TEXT NOT NULL,
               criado_por          TEXT NOT NULL
           )"""
    )
    # Os outros CNPJs da empresa (ADR-77): filiais e empresas do grupo. O principal (a sede) fica na tabela empresas.
    # A chave (empresa_id, cnpj) impede o mesmo CNPJ duas vezes na mesma empresa.
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS cnpjs_das_empresas (
               empresa_id      TEXT NOT NULL,
               cnpj            TEXT NOT NULL,
               tipo            TEXT NOT NULL,
               origem          TEXT NOT NULL,
               registrado_em   TEXT NOT NULL,
               registrado_por  TEXT NOT NULL,
               PRIMARY KEY (empresa_id, cnpj)
           )"""
    )
    quantidade = conexao.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    if quantidade == 0:
        agora = _agora()
        for empresa in dados_mock.sementes_das_empresas():
            # O kit com que a empresa nasce: o da KB do kit dela nos arquivos do projeto (a fonte única)
            kit = _kit_da_semente(empresa["empresa_id"])
            conexao.execute(
                "INSERT INTO empresas (empresa_id, nome, setor, municipio, uf, cnpj, endereco_comercial, dominio_email, "
                "contrato_desde, kit_escolhido, kit_texto, kit_cores, criado_em, criado_por) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (empresa["empresa_id"], empresa["nome"], empresa["setor"], empresa["municipio"], empresa["uf"],
                 empresa["cnpj"], empresa["endereco_comercial"], empresa["dominio_email"], empresa["contrato_desde"],
                 kit["escolhido"], kit["texto"], json.dumps(kit["cores"]), agora, AUTOR_DA_SEMENTE))
            # O logo.png da pasta da KB do kit vai para a cópia derivada que a arte lê
            if kit["logo"] is not None:
                kit_de_marca.gravar_logo(conexao, empresa["empresa_id"], kit["logo"], AUTOR_DA_SEMENTE)
        conexao.commit()


def _kit_da_semente(empresa_id: str) -> dict:
    """O kit com que uma empresa da semente nasce: o que a KB do kit dela define nos arquivos do projeto (a versão 1).

    Por quê: a KB do kit é a fonte única. Num banco novo, a versão 1 das KBs sai desses
    mesmos arquivos, já publicada; assim, a cópia derivada (o kit no cadastro e o logo, que a arte lê) começa igual a ela.
    Devolve: {escolhido, texto, cores, logo (os bytes ou None)}. Sem KB do kit na pasta: o padrão, vazio e sem logo.
    """
    kit = kbs_endomarketing.kit_dos_arquivos(empresa_id)
    # A empresa sem KB do kit nos arquivos nasce com o kit padrão
    if kit is None:
        return {"escolhido": KIT_PADRAO, "texto": "", "cores": [], "logo": None}
    return kit


def _agora() -> str:
    """A data e hora de agora, no horário universal (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _linha_em_dicionario(linha) -> dict:
    """Uma linha da tabela como dicionário (as cores do kit voltam como lista)."""
    empresa = dict(zip(COLUNAS, linha))
    empresa["kit_cores"] = json.loads(empresa["kit_cores"])
    return empresa


def listar(conexao) -> list[dict]:
    """Todas as empresas da carteira, na ordem do código (EMP001, EMP002...).

    Recebe: conexao. Devolve: [{empresa_id, nome, setor, municipio, uf, cnpj, endereco_comercial, dominio_email,
    contrato_desde, kit_escolhido, kit_texto, kit_cores}].
    """
    _preparar(conexao)
    empresas = []
    for linha in conexao.execute("SELECT " + ", ".join(COLUNAS) + " FROM empresas ORDER BY empresa_id"):
        empresas.append(_linha_em_dicionario(linha))
    return empresas


def datas_de_cadastro(conexao) -> dict:
    """Quando cada empresa entrou na carteira (a coluna criado_em), para as listas mostrarem as últimas cadastradas.

    Recebe: conexao. Devolve: {empresa_id: a data e a hora do cadastro, em texto ISO no horário universal}.
    Exemplo: {"EMP001": "2026-09-25T12:00:00+00:00", "EMP024": "2026-09-30T10:05:00+00:00"}.
    Por quê à parte: a Carteira e o Endomarketing mostram só as últimas empresas
    cadastradas; o listar() continua igual para quem já o usa.
    """
    _preparar(conexao)
    datas = {}
    # Uma linha por empresa: o código e o momento do cadastro
    for empresa_id, criado_em in conexao.execute("SELECT empresa_id, criado_em FROM empresas"):
        datas[empresa_id] = criado_em
    return datas


def obter(conexao, empresa_id: str) -> dict:
    """Uma empresa pelo código. Levanta KeyError se ela não existe."""
    for empresa in listar(conexao):
        if empresa["empresa_id"] == empresa_id:
            return empresa
    raise KeyError(empresa_id)


def lista_em_memoria() -> list[dict]:
    """A lista de empresas guardada em memória (renovada a cada TEMPO_DA_LISTA_EM_MEMORIA segundos).

    Recebe: nada. Devolve: a lista, no formato de listar. É o que dados_mock.empresas() devolve para toda a aplicação.
    """
    passou = time.monotonic() - _lista_guardada["lida_em"]
    if _lista_guardada["empresas"] is None or passou > TEMPO_DA_LISTA_EM_MEMORIA:
        conexao = auth.conectar()
        try:
            _guardar_na_memoria(listar(conexao))
        finally:
            conexao.close()
    return _lista_guardada["empresas"]


def esquecer_lista_em_memoria() -> None:
    """Esquece a lista guardada: a próxima leitura vem do banco (usado nos testes, que trocam de banco a cada teste)."""
    _lista_guardada["empresas"] = None
    _lista_guardada["lida_em"] = 0.0


def _guardar_na_memoria(empresas: list[dict]) -> None:
    """Troca a lista guardada em memória pela lista informada, marcando a hora."""
    _lista_guardada["empresas"] = empresas
    _lista_guardada["lida_em"] = time.monotonic()


def _somente_digitos(texto: str) -> str:
    """Tira pontos, barras, traços e espaços: "10.433.218/0001-93" → "10433218000193"."""
    digitos = ""
    for caractere in texto or "":
        if caractere.isdigit():
            digitos = digitos + caractere
    return digitos


def _dados_conferidos(conexao, dados: dict, empresa_id_atual: str | None) -> dict:
    """Confere e limpa os dados de uma empresa (nova ou editada). Levanta ValueError com o motivo.

    Recebe: dados — {nome, setor, municipio, uf, cnpj, endereco_comercial, dominio_email, contrato_desde};
    empresa_id_atual — a empresa editada (o CNPJ dela não conta como repetido), ou None numa empresa nova.
    Devolve: os dados limpos (CNPJ só com dígitos, UF em maiúsculas, domínio em minúsculas e sem "@").
    """
    limpos = {}
    for campo in ("nome", "setor", "municipio", "uf", "cnpj", "endereco_comercial", "dominio_email", "contrato_desde"):
        # Sem os caracteres invisíveis ou de controle (C-23) e sem os espaços das pontas
        limpos[campo] = _sem_caracteres_invisiveis(str(dados.get(campo) or "")).strip()
    limpos["cnpj"] = _somente_digitos(limpos["cnpj"])
    limpos["uf"] = limpos["uf"].upper()
    limpos["dominio_email"] = limpos["dominio_email"].lower().lstrip("@")
    if len(limpos["nome"]) < 3:
        raise ValueError("Escreva a razão social da empresa.")
    if not cnpj_valido(limpos["cnpj"]):
        raise ValueError("O CNPJ não confere (confira os dígitos).")
    if not re.fullmatch(r"[A-Z]{2}", limpos["uf"]):
        raise ValueError("A UF tem 2 letras (ex.: SP).")
    # Duas letras não bastam: a sigla precisa ser de um estado (C-21; "ZZ" passava)
    if limpos["uf"] not in SIGLAS_DOS_ESTADOS:
        raise ValueError("A UF não existe: use a sigla de um estado (ex.: SP).")
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", limpos["dominio_email"]):
        raise ValueError("O domínio de e-mail é a parte depois do @ (ex.: empresa.com.br).")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", limpos["contrato_desde"]):
        raise ValueError("A data do contrato vem como AAAA-MM-DD.")
    # O formato certo não basta: o dia precisa existir no calendário (C-21; "2026-02-30" passava)
    if not _data_existe(limpos["contrato_desde"]):
        raise ValueError("A data do contrato não existe: confira o dia e o mês.")
    for campo in ("setor", "municipio", "endereco_comercial"):
        if not limpos[campo]:
            raise ValueError("Preencha o setor, o município e o endereço comercial.")
    for empresa in listar(conexao):
        if empresa["cnpj"] == limpos["cnpj"] and empresa["empresa_id"] != empresa_id_atual:
            raise ValueError("Já existe uma empresa com este CNPJ na carteira (" + empresa["nome"] + ").")
    return limpos


def _sem_caracteres_invisiveis(texto: str) -> str:
    """O texto sem os caracteres invisíveis e de controle (C-23).

    Por quê: "Empresa\\u202eAVON" aparece na tela com a direção invertida, e um caractere de largura zero não se vê;
    os dois servem para um nome enganar quem lê. Categoria "Cf" = formatação invisível (inversão de direção, largura
    zero); "Cc" = controle (NUL, campainha, quebra de linha, que um campo de cadastro de uma linha não tem).
    Exemplo: "Empresa\\u202eAVON\\u200b" → "EmpresaAVON".
    """
    # Guarda só as letras que não são invisíveis nem de controle
    letras_visiveis = []
    for letra in texto:
        if unicodedata.category(letra) not in ("Cf", "Cc"):
            letras_visiveis.append(letra)
    return "".join(letras_visiveis)


def _data_existe(texto: str) -> bool:
    """True se o texto AAAA-MM-DD é um dia que existe no calendário. Ex.: "2026-02-28" → True; "2026-02-30" → False."""
    try:
        # O Python recusa (ValueError) o dia que não existe
        date.fromisoformat(texto)
    except ValueError:
        return False
    return True


def _proximo_codigo(conexao) -> str:
    """O código da próxima empresa: EMP + o maior número já usado + 1 (ex.: EMP006 → EMP007)."""
    maior = 0
    for empresa in listar(conexao):
        numero = _somente_digitos(empresa["empresa_id"])
        if numero and int(numero) > maior:
            maior = int(numero)
    return "EMP" + str(maior + 1).zfill(3)


def cadastrar(conexao, usuario, dados: dict) -> dict:
    """O especialista cadastra uma empresa nova na carteira. Devolve a empresa, com o código novo.

    Recebe: conexao; usuario (só o BANCO); dados (ver _dados_conferidos). Levanta ValueError com o motivo.
    """
    autorizar(usuario, "editar_empresas")
    _preparar(conexao)
    limpos = _dados_conferidos(conexao, dados, None)
    empresa_id = _proximo_codigo(conexao)
    conexao.execute(
        "INSERT INTO empresas (empresa_id, nome, setor, municipio, uf, cnpj, endereco_comercial, dominio_email, "
        "contrato_desde, kit_escolhido, kit_texto, kit_cores, criado_em, criado_por) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (empresa_id, limpos["nome"], limpos["setor"], limpos["municipio"], limpos["uf"], limpos["cnpj"],
         limpos["endereco_comercial"], limpos["dominio_email"], limpos["contrato_desde"], KIT_PADRAO, "", "[]",
         _agora(), usuario.login))
    conexao.commit()
    _guardar_na_memoria(listar(conexao))
    return obter(conexao, empresa_id)


def atualizar(conexao, usuario, empresa_id: str, dados: dict) -> dict:
    """O especialista edita os dados de uma empresa. Devolve a empresa atualizada.

    Recebe: conexao; usuario (só o BANCO); empresa_id; dados (ver _dados_conferidos). Levanta KeyError/ValueError.
    """
    autorizar(usuario, "editar_empresas")
    obter(conexao, empresa_id)
    limpos = _dados_conferidos(conexao, dados, empresa_id)
    conexao.execute(
        "UPDATE empresas SET nome = ?, setor = ?, municipio = ?, uf = ?, cnpj = ?, endereco_comercial = ?, "
        "dominio_email = ?, contrato_desde = ? WHERE empresa_id = ?",
        (limpos["nome"], limpos["setor"], limpos["municipio"], limpos["uf"], limpos["cnpj"],
         limpos["endereco_comercial"], limpos["dominio_email"], limpos["contrato_desde"], empresa_id))
    conexao.commit()
    _guardar_na_memoria(listar(conexao))
    return obter(conexao, empresa_id)


def definir_kit(conexao, usuario, empresa_id: str, escolhido: str, texto: str = "", cores: list | None = None) -> dict:
    """Grava o kit de endomarketing da empresa na cópia derivada: o padrão Santander ou um kit próprio.

    Quem chama é o "aplicar na empresa", com o kit da versão publicada da KB do kit (services/kbs_publicacao.py): a
    tela não grava mais aqui direto (a KB é a fonte única).
    Recebe: escolhido — "padrao" ou "proprio"; texto — a descrição do kit próprio (logo, cores, moldes aprovados);
    cores — até 5 cores em "#rrggbb". Devolve: a empresa. O kit próprio precisa de descrição.
    """
    autorizar(usuario, "editar_empresas")
    obter(conexao, empresa_id)
    if escolhido not in (KIT_PADRAO, KIT_PROPRIO):
        raise ValueError("Escolha o kit padrão ou o kit próprio.")
    cores_limpas = []
    for cor in (cores or [])[:5]:
        if re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
            cores_limpas.append(cor.lower())
    texto_limpo = (texto or "").strip()[:500]
    if escolhido == KIT_PROPRIO and not texto_limpo:
        raise ValueError("Descreva o kit próprio (logo, cores e moldes aprovados pela empresa).")
    conexao.execute("UPDATE empresas SET kit_escolhido = ?, kit_texto = ?, kit_cores = ? WHERE empresa_id = ?",
                    (escolhido, texto_limpo, json.dumps(cores_limpas), empresa_id))
    conexao.commit()
    _guardar_na_memoria(listar(conexao))
    return obter(conexao, empresa_id)


# ---------------- Os outros CNPJs da empresa: filiais e grupo (ADR-77) ----------------

def cnpjs_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os CNPJs de filiais e do grupo registrados para a empresa, na ordem em que entraram.

    Recebe: conexao; empresa_id. Devolve: [{cnpj, tipo (FILIAL ou GRUPO), origem (BANCO ou EMPRESA), registrado_em,
    registrado_por}]. O CNPJ principal (a sede) não entra: ele fica no cadastro da empresa.
    """
    _preparar(conexao)
    registrados = []
    consulta = ("SELECT cnpj, tipo, origem, registrado_em, registrado_por FROM cnpjs_das_empresas "
                "WHERE empresa_id = ? ORDER BY registrado_em, cnpj")
    for linha in conexao.execute(consulta, (empresa_id,)):
        registrados.append(dict(zip(("cnpj", "tipo", "origem", "registrado_em", "registrado_por"), linha)))
    return registrados


def cnpjs_conhecidos(conexao, empresa_id: str) -> dict:
    """O que o Validador precisa saber dos CNPJs da empresa.

    Recebe: conexao; empresa_id. Devolve: {"principal": o CNPJ da sede (ou None, se a empresa não existe),
    "registrados": [os CNPJs de filiais e do grupo]}.
    Exemplo: {"principal": "10433218000193", "registrados": ["55667788000190"]}.
    """
    try:
        principal = obter(conexao, empresa_id)["cnpj"]
    except KeyError:
        principal = None
    registrados = []
    for registro in cnpjs_da_empresa(conexao, empresa_id):
        registrados.append(registro["cnpj"])
    return {"principal": principal, "registrados": registrados}


def _cnpj_conferido(conexao, empresa: dict, cnpj: str, tipo: str) -> str:
    """Confere um CNPJ de filial ou do grupo antes de gravar. Devolve só os dígitos; levanta ValueError com o motivo."""
    limpo = _somente_digitos(cnpj)
    if tipo not in (CNPJ_FILIAL, CNPJ_GRUPO):
        raise ValueError("Escolha se o CNPJ é de uma filial ou de uma empresa do grupo.")
    if not cnpj_valido(limpo):
        raise ValueError("O CNPJ não confere (confira os dígitos).")
    if limpo == empresa["cnpj"]:
        raise ValueError("Este já é o CNPJ principal da empresa.")
    # Filial é o mesmo CNPJ "raiz" (os 8 primeiros dígitos) da sede; empresa do grupo tem outra raiz
    mesma_raiz = limpo[:8] == empresa["cnpj"][:8]
    if tipo == CNPJ_FILIAL and not mesma_raiz:
        raise ValueError("Uma filial tem os mesmos 8 primeiros dígitos do CNPJ da sede. Se não tem, é do grupo.")
    if tipo == CNPJ_GRUPO and mesma_raiz:
        raise ValueError("Este CNPJ tem a mesma raiz da sede: é uma filial.")
    for registrado in cnpjs_da_empresa(conexao, empresa["empresa_id"]):
        if registrado["cnpj"] == limpo:
            raise ValueError("Este CNPJ já está no cadastro da empresa.")
    return limpo


def _gravar_cnpj(conexao, empresa_id: str, cnpj: str, tipo: str, origem: str, quem: str) -> None:
    """Grava um CNPJ de filial ou do grupo (sem conferir: quem chama já conferiu)."""
    conexao.execute("INSERT INTO cnpjs_das_empresas (empresa_id, cnpj, tipo, origem, registrado_em, registrado_por) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (empresa_id, cnpj, tipo, origem, _agora(), quem))
    conexao.commit()


def adicionar_cnpj(conexao, usuario, empresa_id: str, cnpj: str, tipo: str) -> list[dict]:
    """O especialista cadastra um CNPJ de filial ou de uma empresa do grupo (não é obrigatório: só quando o banco sabe).

    Recebe: conexao; usuario (só o BANCO); empresa_id; cnpj (com ou sem pontuação); tipo (FILIAL ou GRUPO).
    Devolve: a lista atualizada (ver cnpjs_da_empresa). Levanta KeyError (empresa não existe) ou ValueError (motivo).
    """
    autorizar(usuario, "editar_empresas")
    empresa = obter(conexao, empresa_id)
    limpo = _cnpj_conferido(conexao, empresa, cnpj, tipo)
    _gravar_cnpj(conexao, empresa_id, limpo, tipo, ORIGEM_BANCO, usuario.login)
    return cnpjs_da_empresa(conexao, empresa_id)


def remover_cnpj(conexao, usuario, empresa_id: str, cnpj: str) -> list[dict]:
    """O especialista tira um CNPJ de filial ou do grupo do cadastro da empresa.

    Recebe: conexao; usuario (só o BANCO); empresa_id; cnpj. Devolve: a lista atualizada. Levanta KeyError se o CNPJ
    não está no cadastro. Os envios já cadastrados não mudam; o próximo envio com esse CNPJ volta a perguntar.
    """
    autorizar(usuario, "editar_empresas")
    obter(conexao, empresa_id)
    limpo = _somente_digitos(cnpj)
    apagados = conexao.execute("DELETE FROM cnpjs_das_empresas WHERE empresa_id = ? AND cnpj = ?",
                               (empresa_id, limpo)).rowcount
    conexao.commit()
    if apagados == 0:
        raise KeyError(cnpj)
    return cnpjs_da_empresa(conexao, empresa_id)


def registrar_cnpj_confirmado_pela_empresa(conexao, login: str, empresa_id: str, cnpj: str) -> None:
    """A empresa confirmou, num envio, que um CNPJ repetido no arquivo é do grupo: ele entra no cadastro sozinho.

    Recebe: conexao; login (quem confirmou); empresa_id; cnpj. Devolve: nada. Se o CNPJ já está no cadastro, não faz
    nada (confirmar duas vezes não duplica). Assim, nenhum outro funcionário nem outro envio pergunta de novo.
    Chamado pelo Validador (justificar_alerta), que já conferiu que o alerta existe e que o envio é da empresa.
    """
    limpo = _somente_digitos(cnpj)
    for registrado in cnpjs_da_empresa(conexao, empresa_id):
        if registrado["cnpj"] == limpo:
            return
    # Mesma raiz da sede é filial; outra raiz é empresa do grupo
    tipo = CNPJ_GRUPO
    if limpo[:8] == obter(conexao, empresa_id)["cnpj"][:8]:
        tipo = CNPJ_FILIAL
    _gravar_cnpj(conexao, empresa_id, limpo, tipo, ORIGEM_EMPRESA, login)
