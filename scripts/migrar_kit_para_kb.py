"""Leva o kit de marca de cada empresa para a KB "Kit da marca", a fonte única do kit.

Para que serve: antes, o kit da empresa podia ser gravado direto no cadastro (a escolha entre o padrão e o
próprio, o texto e as cores) e o logo direto na tabela logos_dos_kits, pela tela "Kit de Marca", que saiu. Agora a KB
do kit é a fonte única: a escolha e as cores ficam na ficha da KB, e o logo fica anexado à versão da KB. O cadastro e
o logos_dos_kits viraram só uma cópia derivada, gravada ao publicar ou retirar a KB do kit. Este script leva o que já
está no banco para a KB de cada empresa, sem perder nada:
    - a escolha, o texto e as cores: os do cadastro, quando o banco já gravou um kit ali (é o que a arte usa hoje);
      sem cores no cadastro, ficam as da KB, e o texto só conta no kit próprio. O cadastro que nunca foi mexido (o
      padrão, sem texto, sem cores e sem logo, como a empresa nascia) não conta: vale o que a KB já dizia;
    - o logo: o do cadastro (logos_dos_kits); sem ele, o já anexado à versão da KB ou, numa KB antiga, o arquivo que
      o campo "logo" da ficha apontava (só um nome de arquivo da pasta da empresa, a mesma regra da trava de antes:
      um caminho como "../../.env" nunca é lido);
    - o antigo campo "logo" sai da ficha.
O resultado vira uma versão nova da KB do kit, PUBLICADA e aplicada na empresa (só o kit: o catálogo do agente não
muda). A empresa sem KB do kit ganha uma, montada com o que o cadastro tem; a que só tem o padrão, sem nada, fica
como está. A KB do kit sem versão publicada (retirada) ganha só um rascunho, com o kit e o logo: publicar continua com
o banco, e a empresa fica no padrão até lá.

Pode rodar de novo: a KB que já tem o kit e o logo não ganha versão nova ("já estava na KB").

Não roda sozinho: roda uma vez em cada banco que tinha kit antes de 30/09 (o PostgreSQL local e o do site), com backup
antes e com a porta 8000 parada (ao publicar, o índice do RAG é atualizado, e só um processo por vez abre a pasta
dele). Sem --gravar, só mostra o que faria.

Para rodar (na pasta integra-folha, com o .env do banco que vai receber a migração):
    python scripts/migrar_kit_para_kb.py            mostra o que faria, sem gravar nada
    python scripts/migrar_kit_para_kb.py --gravar   grava e publica
"""
import argparse
import os
import re
import sys
from pathlib import Path

# O script nunca paga a IA: o modo MOCK vale antes de qualquer serviço ler o .env (a trava usa só a lista de frases)
os.environ["MODE"] = "mock"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from models.contratos import Perfil  # noqa: E402
from services import banco, kbs_endomarketing, kbs_publicacao, kit_de_marca  # noqa: E402
from services import empresas as cadastro_de_empresas  # noqa: E402
from services.auth import Usuario  # noqa: E402

# Quem grava e publica as versões da migração (tem espaços, então nunca é o login de alguém)
AUTOR_DA_MIGRACAO = "migração do kit para a KB (scripts/migrar_kit_para_kb.py)"
# De onde veio o kit, na ficha da KB nova de uma empresa que ainda não tinha KB do kit
ORIGEM_DA_MIGRACAO = "Kit do cadastro da empresa, levado para a KB pela migração de 30/09"
# O nome de arquivo que o antigo campo "logo" da ficha podia ter: letras minúsculas, números e "_", .png ou .jpg, sem
# pasta (a mesma regra da trava de antes)
PADRAO_DO_ARQUIVO_DO_LOGO_ANTIGO = re.compile(r"^[a-z0-9_]+\.(png|jpg)$")
# O que a migração faz com cada empresa
NADA, JA_ESTAVA, VERSAO_NOVA, KB_NOVA, RASCUNHO = "nada", "ja_estava", "versao_nova", "kb_nova", "rascunho"
# As ações que gravam alguma coisa
ACOES_QUE_GRAVAM = (VERSAO_NOVA, KB_NOVA, RASCUNHO)
# A frase de cada ação, para o relatório
FRASE_DA_ACAO = {
    NADA: "nada a levar (kit padrão, sem texto, sem cores e sem logo)",
    JA_ESTAVA: "já estava na KB",
    VERSAO_NOVA: "versão nova da KB do kit, publicada",
    KB_NOVA: "KB do kit criada e publicada",
    RASCUNHO: "a KB do kit está sem versão publicada: rascunho novo, a publicar pelo banco",
}


def usuario_da_migracao() -> Usuario:
    """O usuário com que a migração grava e publica: o perfil BANCO (as regras de acesso das KBs exigem o banco)."""
    return Usuario(login=AUTOR_DA_MIGRACAO, perfil=Perfil.BANCO, empresa_id=None)


# ---------------- O que existe no banco ----------------

def cadastro_foi_mexido(empresa: dict, logo_do_cadastro) -> bool:
    """Diz se o banco já gravou um kit no cadastro da empresa: algo diferente de como ela nascia.

    Recebe: a empresa (como services/empresas.py devolve); o logo do cadastro ((bytes, tipo) ou None).
    Exemplo: o padrão, sem texto, sem cores e sem logo → False; o kit próprio com duas cores → True.
    """
    # O kit próprio foi gravado ali
    if empresa["kit_escolhido"] != cadastro_de_empresas.KIT_PADRAO:
        return True
    # Um texto ou uma cor também foram gravados por alguém
    if empresa["kit_texto"] or empresa["kit_cores"]:
        return True
    # Um logo guardado, mesmo no padrão
    return logo_do_cadastro is not None


def kb_do_kit_da_empresa(conexao, empresa_id: str) -> dict | None:
    """A KB do kit da empresa que a migração atualiza: a que tem versão publicada; sem ela, a atualizada por último.

    Devolve o resumo da KB (como kbs_endomarketing.listar devolve), ou None se a empresa não tem KB do kit.
    """
    escolhida = None
    for resumo in kbs_endomarketing.listar(conexao, empresa_id):
        # Só as KBs do kit
        if resumo["tipo"] != kbs_endomarketing.TIPO_DO_KIT:
            continue
        # A que tem versão publicada é a que vale: ela tem a preferência
        if resumo["versao_publicada"] is not None:
            return resumo
        # Sem publicada, a atualizada por último
        if escolhida is None or resumo["atualizado_em"] > escolhida["atualizado_em"]:
            escolhida = resumo
    return escolhida


def logo_do_campo_antigo(empresa_id: str, ficha: dict) -> bytes | None:
    """O logo que o antigo campo "logo" da ficha apontava: o arquivo na pasta da empresa, se for uma imagem válida.

    Só um nome de arquivo (ex.: "logo.png") é aceito; um caminho de pasta nunca é lido. Sem o campo, sem o arquivo ou
    com uma imagem que o sistema não aceita: None.
    """
    nome_do_arquivo = ficha.get("logo", "")
    # Só um nome de arquivo da pasta da empresa (a regra da trava de antes)
    if not PADRAO_DO_ARQUIVO_DO_LOGO_ANTIGO.match(nome_do_arquivo):
        return None
    arquivo = kbs_endomarketing.PASTA_DAS_KBS / empresa_id / nome_do_arquivo
    # O arquivo não existe (ex.: o banco de outra máquina, sem a pasta)
    if not arquivo.is_file():
        return None
    conteudo = arquivo.read_bytes()
    # A mesma conferência do logo de sempre: PNG ou JPEG de verdade, até 500 KB
    try:
        kit_de_marca.conferir_logo(conteudo)
    except ValueError:
        return None
    return conteudo


# ---------------- O texto da KB ----------------

def trocar_texto_da_secao(corpo: str, titulo_da_secao: str, texto_novo: str) -> str:
    """O corpo da KB com o texto de uma seção "## ..." trocado (o título e as outras seções ficam como estão).

    Exemplo: trocar "Identidade" em "## Identidade\\nAntigo\\n\\n## Cores\\n..." → "## Identidade\\nNovo\\n\\n## Cores\\n...".
    Sem a seção, o corpo volta igual.
    """
    resultado = []
    dentro_da_secao = False
    for linha in corpo.splitlines():
        # Um título "## " abre uma seção ("### " não é seção)
        if linha.startswith("## "):
            # A seção que troca: o título e, logo abaixo, o texto novo
            if linha[3:].strip() == titulo_da_secao:
                resultado.extend([linha, texto_novo])
                dentro_da_secao = True
                continue
            # A seção seguinte à trocada: uma linha em branco antes dela, como no modelo
            if dentro_da_secao:
                resultado.append("")
            dentro_da_secao = False
        # As linhas antigas da seção trocada ficam de fora
        if not dentro_da_secao:
            resultado.append(linha)
    return "\n".join(resultado)


def mesma_kb(conteudo_a: str, conteudo_b: str) -> bool:
    """Diz se dois textos de KB dizem o mesmo: a mesma ficha (chave e valor) e as mesmas seções."""
    ficha_a, corpo_a = kbs_endomarketing.separar_ficha(conteudo_a)
    ficha_b, corpo_b = kbs_endomarketing.separar_ficha(conteudo_b)
    return ficha_a == ficha_b and corpo_a.strip() == corpo_b.strip()


# ---------------- O plano de cada empresa ----------------

def plano_da_empresa(conexao, empresa: dict) -> dict:
    """O que a migração faz com uma empresa (sem gravar nada).

    Devolve: {empresa_id, nome, acao, kb_id, versao_de_origem, conteudo, logo, origem_do_kit, origem_do_logo}.
    "acao" é uma das ações do topo; "conteudo" e "logo" são o texto e a imagem da versão a gravar.
    """
    empresa_id = empresa["empresa_id"]
    logo_do_cadastro = kit_de_marca.logo(conexao, empresa_id)
    mexido = cadastro_foi_mexido(empresa, logo_do_cadastro)
    plano = {"empresa_id": empresa_id, "nome": empresa["nome"], "acao": NADA, "kb_id": None,
             "versao_de_origem": None, "conteudo": None, "logo": None, "origem_do_kit": "", "origem_do_logo": ""}
    resumo = kb_do_kit_da_empresa(conexao, empresa_id)
    # A empresa sem KB do kit: com um kit no cadastro, ganha uma; só com o padrão, fica como está
    if resumo is None:
        if mexido:
            plano.update(_plano_da_kb_nova(empresa, logo_do_cadastro))
        return plano
    plano.update(_plano_da_kb_existente(conexao, empresa, resumo["kb_id"], logo_do_cadastro, mexido))
    return plano


def _plano_da_kb_nova(empresa: dict, logo_do_cadastro) -> dict:
    """O plano de uma empresa que tem kit no cadastro e ainda não tem KB do kit: criar a KB com esse kit."""
    logo = None
    origem_do_logo = "nenhum"
    # O logo do cadastro vai junto
    if logo_do_cadastro is not None:
        logo = logo_do_cadastro[0]
        origem_do_logo = "o do cadastro"
    return {"acao": KB_NOVA, "logo": logo, "origem_do_kit": "o do cadastro", "origem_do_logo": origem_do_logo}


def _plano_da_kb_existente(conexao, empresa: dict, kb_id: str, logo_do_cadastro, mexido: bool) -> dict:
    """O plano de uma empresa que já tem KB do kit: a versão nova (ou nada, se ela já diz tudo).

    Parte da versão que vale (a publicada; sem ela, a última). Tira o antigo campo "logo" da ficha e traz o kit e o
    logo do cadastro, quando o banco gravou um kit ali; senão, fica o que a KB já dizia.
    """
    kb = kbs_endomarketing.obter(conexao, kb_id)
    ficha = dict(kb["ficha"])
    corpo = kb["corpo"]
    # O logo que a versão já tem anexado, e o do antigo campo "logo" (que sai da ficha)
    logo_da_versao = kit_de_marca.logo_da_versao(conexao, kb_id, kb["versao"])
    logo_antigo = logo_do_campo_antigo(empresa["empresa_id"], ficha)
    ficha.pop("logo", None)
    logo, origem_do_logo = _logo_para_a_kb(logo_do_cadastro, logo_da_versao, logo_antigo)
    # A escolha, as cores e o texto: os do cadastro, se o banco gravou um kit ali; senão, os que a KB já dizia
    if mexido:
        corpo = _kit_do_cadastro_na_kb(empresa, ficha, corpo)
        origem_do_kit = "o do cadastro"
    else:
        origem_do_kit = "o da KB"
    conteudo = kbs_endomarketing.montar_conteudo(ficha, corpo)
    # O logo de agora, para comparar
    logo_de_agora = None
    if logo_da_versao is not None:
        logo_de_agora = logo_da_versao[0]
    plano = {"kb_id": kb_id, "versao_de_origem": kb["versao"], "conteudo": conteudo, "logo": logo,
             "origem_do_kit": origem_do_kit, "origem_do_logo": origem_do_logo}
    # A versão já diz tudo (a mesma ficha, as mesmas seções e o mesmo logo): nada a gravar
    if mesma_kb(conteudo, kb["conteudo_md"]) and logo == logo_de_agora:
        plano["acao"] = JA_ESTAVA
    # A KB está valendo: a versão nova é publicada
    elif kb["situacao"] == kbs_endomarketing.PUBLICADA:
        plano["acao"] = VERSAO_NOVA
    # A KB está retirada (ou só em rascunho): um rascunho novo, e publicar fica com o banco
    else:
        plano["acao"] = RASCUNHO
    return plano


def _kit_do_cadastro_na_kb(empresa: dict, ficha: dict, corpo: str) -> str:
    """Põe na ficha a escolha e as cores do cadastro (sem cores lá, ficam as da KB). Devolve o corpo, com o texto do
    kit próprio do cadastro na seção "Identidade" quando ele é diferente do que a KB diz (o texto da tela que saiu)."""
    ficha["kit_escolhido"] = empresa["kit_escolhido"]
    # As cores do cadastro, se ele tem (o kit próprio precisa de pelo menos uma: sem elas, ficam as da KB)
    if empresa["kit_cores"]:
        ficha["cores"] = ", ".join(empresa["kit_cores"])
    # O texto só conta no kit próprio (no padrão, a tela mandava o que estivesse na caixa, sem uso na arte)
    if empresa["kit_escolhido"] != cadastro_de_empresas.KIT_PROPRIO or not empresa["kit_texto"]:
        return corpo
    # O texto do cadastro é a identidade cortada em 500 letras quando veio da KB: só um texto diferente muda a seção
    identidade = kbs_endomarketing.texto_da_secao(corpo, "Identidade")
    if empresa["kit_texto"] != identidade[:kbs_endomarketing.LIMITE_DO_TEXTO_DO_KIT].strip():
        return trocar_texto_da_secao(corpo, "Identidade", empresa["kit_texto"])
    return corpo


def _logo_para_a_kb(logo_do_cadastro, logo_da_versao, logo_antigo: bytes | None) -> tuple[bytes | None, str]:
    """O logo que a KB do kit vai ter, e de onde ele veio (para o relatório).

    A ordem: o do cadastro (o que a arte usa hoje); senão, o já anexado à versão; senão, o arquivo do antigo campo
    "logo" da ficha. Nenhum dos três: None.
    """
    if logo_do_cadastro is not None:
        return logo_do_cadastro[0], "o do cadastro"
    if logo_da_versao is not None:
        return logo_da_versao[0], "o anexado à versão"
    if logo_antigo is not None:
        return logo_antigo, "o arquivo do antigo campo \"logo\""
    return None, "nenhum"


# ---------------- Gravar ----------------

def executar_o_plano(conexao, usuario: Usuario, plano: dict) -> dict:
    """Grava o que o plano diz. Devolve o plano com o resultado: a versão gravada, o índice ou o motivo do bloqueio."""
    plano["versao"] = None
    plano["indice_atualizado"] = None
    plano["bloqueio"] = ""
    try:
        if plano["acao"] == KB_NOVA:
            _criar_a_kb(conexao, usuario, plano)
        else:
            _gravar_a_versao(conexao, usuario, plano)
    except kbs_endomarketing.TravaBloqueou as erro:
        # A trava recusou o kit (ex.: próprio sem nenhuma cor): a empresa fica como estava, e o relatório avisa
        plano["bloqueio"] = str(erro)
    return plano


def _criar_a_kb(conexao, usuario: Usuario, plano: dict) -> None:
    """Cria a KB do kit com o kit do cadastro, já publicada, e aplica o kit na empresa."""
    empresa = cadastro_de_empresas.obter(conexao, plano["empresa_id"])
    resultado = kbs_publicacao.publicar_kit_novo(conexao, usuario, plano["empresa_id"], empresa["kit_escolhido"],
                                                 empresa["kit_texto"], empresa["kit_cores"], plano["logo"],
                                                 ORIGEM_DA_MIGRACAO)
    plano["kb_id"] = resultado["kb"]["kb_id"]
    plano["versao"] = resultado["kb"]["versao"]
    plano["indice_atualizado"] = resultado["indice_atualizado"]


def _gravar_a_versao(conexao, usuario: Usuario, plano: dict) -> None:
    """Grava a versão nova da KB do kit, com o logo do plano; publica (versão nova) ou só aplica o kit (rascunho)."""
    # O texto é o da própria KB e o do cadastro: basta a lista de frases do guardrail, sem gastar com IA
    salvo = kbs_endomarketing.salvar(conexao, usuario.login, plano["conteudo"],
                                     versao_de_origem=plano["versao_de_origem"])
    plano["versao"] = salvo["versao"]
    # O logo do plano no rascunho, no lugar do que ele herdou da versão de origem
    if plano["logo"] is None:
        kit_de_marca.tirar_logo_da_versao(conexao, plano["kb_id"], salvo["versao"])
    else:
        kit_de_marca.gravar_logo_da_versao(conexao, plano["kb_id"], salvo["versao"], plano["logo"], usuario.login)
    # A KB estava valendo: a versão nova é publicada e aplicada na empresa
    if plano["acao"] == VERSAO_NOVA:
        publicado = kbs_publicacao.publicar_versao_do_kit(conexao, usuario, plano["kb_id"], salvo["versao"])
        plano["indice_atualizado"] = publicado["indice_atualizado"]
        return
    # A KB estava retirada: a empresa fica no padrão (sem KB do kit publicada), e o rascunho espera o banco
    kbs_publicacao.aplicar_o_kit(conexao, usuario, plano["empresa_id"])


def migrar(conexao, gravar: bool) -> list[dict]:
    """Monta o plano de cada empresa da carteira e, com gravar=True, grava. Devolve os planos, com os resultados."""
    usuario = usuario_da_migracao()
    planos = []
    for empresa in cadastro_de_empresas.listar(conexao):
        plano = plano_da_empresa(conexao, empresa)
        # Só grava quem tem o que gravar, e só com a opção --gravar
        if gravar and plano["acao"] in ACOES_QUE_GRAVAM:
            plano = executar_o_plano(conexao, usuario, plano)
        planos.append(plano)
    return planos


# ---------------- O relatório e a linha de comando ----------------

def linha_do_relatorio(plano: dict) -> str:
    """Uma linha do relatório: a empresa, o que foi (ou seria) feito e de onde vieram o kit e o logo.

    Exemplo: "EMP001 Aurora Alimentos Ltda.: versão nova da KB do kit, publicada (EMP001-KIT-DA-MARCA v2; kit: o do
    cadastro; logo: o do cadastro)".
    """
    linha = f"{plano['empresa_id']} {plano['nome']}: {FRASE_DA_ACAO[plano['acao']]}"
    # A empresa sem nada a fazer não precisa de detalhe
    if plano["acao"] == NADA:
        return linha
    # Qual KB e qual versão: a gravada; a que já estava certa; sem gravar, a versão de onde a nova parte
    if plano.get("versao"):
        qual_versao = f"{plano['kb_id']} v{plano['versao']}"
    elif plano["acao"] == JA_ESTAVA:
        qual_versao = f"{plano['kb_id']} v{plano['versao_de_origem']}"
    elif plano["versao_de_origem"]:
        qual_versao = f"{plano['kb_id']}, a partir da v{plano['versao_de_origem']}"
    else:
        qual_versao = "KB nova"
    linha += f" ({qual_versao}; kit: {plano['origem_do_kit']}; logo: {plano['origem_do_logo']})"
    # O que deu errado ao gravar, ou o índice que ficou para depois
    if plano.get("bloqueio"):
        linha += f" · NÃO GRAVADO: {plano['bloqueio']}"
    if plano.get("indice_atualizado") is False:
        linha += " · índice do RAG não atualizado: rode scripts/indexar_kbs_endomarketing.py com a 8000 parada"
    return linha


def main() -> None:
    """Lê a opção, abre o banco do .env e migra (ou só mostra o que faria)."""
    leitor = argparse.ArgumentParser(description="Leva o kit de cada empresa para a KB do kit (a fonte única).")
    leitor.add_argument("--gravar", action="store_true", help="grava e publica (sem ela, só mostra o que faria)")
    opcoes = leitor.parse_args()
    # O banco do .env (SQLite ou PostgreSQL)
    conexao = banco.conectar()
    print("Banco:", "PostgreSQL" if banco.e_postgres(conexao) else "SQLite", "| gravar:",
          "sim" if opcoes.gravar else "não (só mostra o que faria; use --gravar)")
    try:
        for plano in migrar(conexao, opcoes.gravar):
            print(linha_do_relatorio(plano))
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
