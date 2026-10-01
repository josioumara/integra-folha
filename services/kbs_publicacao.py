"""O que as KBs publicadas alimentam: a vitrine da empresa, o catálogo do agente, o kit da marca e o contexto (ADR-125).

As KBs ficam em services/kbs_endomarketing.py. Este arquivo leva as PUBLICADAS para onde elas valem:
1. Vitrine "Benefícios do seu time" (Portal da Empresa): mostra SÓ as KBs de benefício publicadas e vigentes da
   empresa, mais a KB de canais de atendimento. A vitrine lê de documentos_da_vitrine(), no mesmo formato do
   catálogo, e por isso a tela da vitrine não muda.
2. Catálogo do agente: o Agente de Endomarketing busca no catálogo de benefícios (ADR-19). Ao publicar, o catálogo da
   empresa ganha uma versão nova montada das KBs publicadas; a versão anterior fica guardada.
3. Kit da marca: a KB do kit é a FONTE ÚNICA do kit da empresa. A versão publicada vira a
   cópia derivada que a arte lê: a escolha (próprio ou padrão), o texto e as cores no cadastro da empresa, e o logo
   anexado à versão na tabela dos logos. Retirada a KB do kit, a empresa volta ao padrão. A prévia só de leitura da
   tela de gerar o material ("kit em uso") também sai daqui.
4. Contexto do agente: o pacote pronto das KBs publicadas (gerais, kit, jornada, atendimento, benefícios e landing
   page) que um agente recebe para escrever o material.
Cada "aplicar na empresa" fica registrado na tabela kbs_publicacoes.
"""
import json
import uuid
from datetime import date, datetime, timezone

from rag import kbs_endomarketing as indice_das_kbs
from services import catalogo
from services import empresas as cadastro_de_empresas
from services import endomarketing_do_banco, kbs_endomarketing, kit_de_marca, portal_do_banco
from services.permissoes import autorizar

# Os tipos de KB de empresa que mudam a vitrine e o catálogo, e o que muda o kit
TIPOS_DA_VITRINE = ("beneficio", "atendimento")
TIPO_DO_KIT = kbs_endomarketing.TIPO_DO_KIT
# O título do catálogo de uma empresa que ainda não tem nenhum
TITULO_PADRAO_DO_CATALOGO = "Pacote de benefícios {nome}"
# A ordem das KBs no contexto do agente: primeiro as regras, depois a marca, a jornada e os benefícios
ORDEM_DO_CONTEXTO = ("guardrails", "termos_proibidos", "diretrizes", "tom_de_voz", "canais", "glossario",
                     "kit_da_marca", "jornada", "atendimento", "beneficio", "landing_page")


# ---------------- 1. A vitrine: as KBs publicadas no formato do catálogo ----------------

def secao_de_catalogo_do_beneficio(kb: dict) -> str:
    """Um benefício em Markdown no formato do catálogo: "## título", "Categoria:", o resumo e as três partes.

    Recebe: a KB (com "ficha" e "corpo"). Devolve: o texto. As "Condições" entram no resumo, logo abaixo dele.
    Exemplo de saída: "## Conta salário\\nCategoria: Conta e dia a dia\\nSem tarifa.\\n### Como funciona\\n..."
    """
    corpo = kb["corpo"]
    linhas = [f"## {kb['titulo']}", f"{catalogo.MARCA_DA_CATEGORIA} {kb['ficha'].get('categoria', '')}"]
    # O resumo e as condições formam o texto de abertura do benefício
    linhas.append(kbs_endomarketing.texto_da_secao(corpo, "Resumo"))
    condicoes = kbs_endomarketing.texto_da_secao(corpo, "Condições")
    if condicoes:
        linhas.append(condicoes)
    # As três partes da janela de detalhes da vitrine, com os mesmos nomes do catálogo
    for nome_da_parte in catalogo.PARTES_DO_BENEFICIO:
        linhas.append(f"### {nome_da_parte}")
        linhas.append(kbs_endomarketing.texto_da_secao(corpo, nome_da_parte))
    return "\n".join(linhas)


def secoes_de_catalogo_do_atendimento(kb: dict) -> str:
    """A KB de atendimento no formato do catálogo: as seções "Onde consultar" e "Canais de dúvidas"."""
    linhas = []
    for titulo_da_secao in catalogo.SECOES_DE_ATENDIMENTO:
        linhas.append(f"## {titulo_da_secao}")
        linhas.append(kbs_endomarketing.texto_da_secao(kb["corpo"], titulo_da_secao))
    return "\n".join(linhas)


def documentos_da_vitrine(conexao, empresa_id: str, dia: date | None = None) -> list[dict]:
    """As KBs publicadas e vigentes da empresa que a vitrine mostra, cada uma como um "documento" do catálogo.

    Recebe: conexao; empresa_id (da sessão: a Empresa A nunca vê a KB da B); dia (sem informar, hoje).
    Devolve: [{empresa_id, titulo, versao, vigencia_inicio, vigencia_fim, conteudo_md}], primeiro os benefícios,
    depois o atendimento. KB em rascunho, retirada, substituída ou vencida não aparece.
    """
    documentos = []
    for tipo in TIPOS_DA_VITRINE:
        for kb in kbs_endomarketing.kbs_publicadas(conexao, dono=empresa_id, tipo=tipo, dia=dia):
            # O texto no formato do catálogo, conforme o tipo
            if tipo == "beneficio":
                texto = secao_de_catalogo_do_beneficio(kb)
            else:
                texto = secoes_de_catalogo_do_atendimento(kb)
            documentos.append({"empresa_id": empresa_id, "titulo": kb["titulo"], "versao": kb["versao"],
                               "vigencia_inicio": kb["vigencia_inicio"], "vigencia_fim": kb["vigencia_fim"],
                               "conteudo_md": texto})
    return documentos


# ---------------- 2. O catálogo do agente ----------------

def _titulo_do_catalogo(conexao, empresa_id: str, nome_da_empresa: str) -> str:
    """O título do documento do catálogo da empresa: o que ela já tem (assim a versão nova o substitui) ou o padrão."""
    for documento in catalogo.documentos_mais_recentes(conexao):
        if documento["empresa_id"] == empresa_id:
            return documento["titulo"]
    return TITULO_PADRAO_DO_CATALOGO.format(nome=nome_da_empresa)


def markdown_do_catalogo(conexao, empresa_id: str, nome_da_empresa: str) -> dict | None:
    """O catálogo da empresa montado das KBs publicadas: {titulo, vigencia_inicio, vigencia_fim, conteudo_md}.

    A vigência vai do início mais antigo ao fim mais distante das KBs usadas. Sem nenhuma KB publicada: None.
    """
    documentos = documentos_da_vitrine(conexao, empresa_id)
    if not documentos:
        return None
    partes = [f"# {TITULO_PADRAO_DO_CATALOGO.format(nome=nome_da_empresa)} (das KBs publicadas)"]
    inicios = []
    fins = []
    for documento in documentos:
        partes.append(documento["conteudo_md"])
        inicios.append(documento["vigencia_inicio"])
        fins.append(documento["vigencia_fim"])
    return {"titulo": _titulo_do_catalogo(conexao, empresa_id, nome_da_empresa), "vigencia_inicio": min(inicios),
            "vigencia_fim": max(fins), "conteudo_md": "\n\n".join(partes) + "\n"}


def _aplicar_catalogo(conexao, usuario, empresa_id: str, nome_da_empresa: str) -> dict:
    """Grava o catálogo montado das KBs como versão nova (a mesma função da tela do banco, que refaz o índice)."""
    montado = markdown_do_catalogo(conexao, empresa_id, nome_da_empresa)
    if montado is None:
        return {"aplicado": False, "motivo": "A empresa não tem KB de benefício ou de atendimento publicada."}
    resultado = portal_do_banco.nova_versao_do_catalogo(conexao, usuario, empresa_id, montado["titulo"],
                                                        montado["vigencia_inicio"], montado["vigencia_fim"],
                                                        montado["conteudo_md"])
    return {"aplicado": True, "titulo": montado["titulo"], "versao": resultado["versao"],
            "indice_atualizado": resultado["indice_atualizado"]}


# ---------------- 3. O kit da marca e o logo ----------------

def _kit_publicado(conexao, empresa_id: str) -> dict | None:
    """A KB de kit da marca publicada e vigente da empresa (há no máximo uma por empresa na prática)."""
    kits = kbs_endomarketing.kbs_publicadas(conexao, dono=empresa_id, tipo=TIPO_DO_KIT)
    if not kits:
        return None
    return kits[0]


def _aplicar_kit(conexao, usuario, empresa_id: str) -> dict:
    """A KB do kit publicada vira a cópia derivada do kit da empresa, que a arte lê.

    Copia a escolha (próprio ou padrão), o texto da identidade e as cores para o cadastro da empresa, e o logo anexado
    à versão publicada para a tabela dos logos (sem logo na versão, a cópia fica sem). Sem KB do kit publicada e
    vigente (ex.: acabou de ser retirada), a empresa volta ao padrão (ver _voltar_ao_padrao).
    Devolve: {aplicado, kit_escolhido, kb_id, versao, logo} ou, sem nada a aplicar, {aplicado: False, motivo, logo}.
    """
    kit = _kit_publicado(conexao, empresa_id)
    # Sem versão publicada e vigente: o kit em vigor é o padrão
    if kit is None:
        return _voltar_ao_padrao(conexao, usuario, empresa_id)
    # A escolha, o texto e as cores da versão publicada vão para o cadastro da empresa
    definicao = kbs_endomarketing.kit_da_versao(kit["ficha"], kit["corpo"])
    cadastro_de_empresas.definir_kit(conexao, usuario, empresa_id, definicao["escolhido"], definicao["texto"],
                                     definicao["cores"])
    # O logo anexado à versão publicada vai para a cópia derivada; versão sem logo tira o logo da cópia
    logo = kit_de_marca.logo_da_versao(conexao, kit["kb_id"], kit["versao"])
    if logo is None:
        kit_de_marca.tirar_logo(conexao, empresa_id)
    else:
        kit_de_marca.gravar_logo(conexao, empresa_id, logo[0], usuario.login)
    return {"aplicado": True, "kit_escolhido": definicao["escolhido"], "kb_id": kit["kb_id"], "versao": kit["versao"],
            "logo": logo is not None}


def _voltar_ao_padrao(conexao, usuario, empresa_id: str) -> dict:
    """Sem KB do kit publicada: a cópia derivada volta ao kit padrão, sem texto, sem cores e sem logo.

    A empresa que nunca teve KB do kit fica como está: o kit dela ainda não passou para a KB (é o caso de antes da
    migração, scripts/migrar_kit_para_kb.py). Assim, nenhum "aplicar" apaga um kit que ainda não tem a KB como fonte.
    As versões da KB (com as cores e o logo) continuam guardadas: publicar uma delas de novo traz o kit de volta.
    """
    if not _tem_kb_do_kit(conexao, empresa_id):
        return {"aplicado": False, "motivo": "A empresa não tem KB do kit da marca: o kit fica como está.",
                "logo": False}
    cadastro_de_empresas.definir_kit(conexao, usuario, empresa_id, cadastro_de_empresas.KIT_PADRAO, "", [])
    kit_de_marca.tirar_logo(conexao, empresa_id)
    return {"aplicado": True, "kit_escolhido": cadastro_de_empresas.KIT_PADRAO, "kb_id": None, "versao": None,
            "logo": False}


def _tem_kb_do_kit(conexao, empresa_id: str) -> bool:
    """Diz se a empresa tem alguma KB do kit da marca, em qualquer situação (rascunho, publicada ou retirada)."""
    for kb in kbs_endomarketing.listar(conexao, empresa_id):
        if kb["tipo"] == TIPO_DO_KIT:
            return True
    return False


def kit_em_uso(conexao, usuario, empresa_id: str) -> dict:
    """O kit que a arte da empresa usa agora, para a prévia só de leitura da tela de gerar o material.

    Recebe: usuario (só o BANCO); empresa_id. Devolve: {escolhido, nome, cores, tem_logo, endereco_do_logo, kb_id,
    kb_versao}. O kit é o da cópia derivada, a mesma que a arte lê (endomarketing_do_banco.kit_da_empresa); "cores"
    traz as 5 cores da arte (cor_principal, cor_escura, cor_fundo, cor_texto e cor_apoio). kb_id e kb_versao dizem
    qual versão publicada da KB do kit a tela manda editar (None sem KB do kit publicada e vigente). No kit padrão o
    logo não entra na arte: tem_logo é False e endereco_do_logo é None, mesmo com um logo guardado.
    KeyError se a empresa não existe.
    Exemplo: {"escolhido": "proprio", "nome": "Kit da Aurora Alimentos Ltda.", "cores": {"cor_principal": "#e8772e",
    ...}, "tem_logo": True, "endereco_do_logo": "/api/banco/empresas/EMP001/kit/logo", "kb_id": "EMP001-KIT-DA-MARCA",
    "kb_versao": 1}.
    """
    autorizar(usuario, "gerar_material")
    kit = endomarketing_do_banco.kit_da_empresa(conexao, empresa_id)
    # As 5 cores da arte (as mesmas chaves do kit padrão)
    cores = {}
    for chave in endomarketing_do_banco.CORES_DO_KIT_PADRAO:
        cores[chave] = kit[chave]
    # A versão publicada da KB do kit, para o link "Editar na KB"
    publicado = _kit_publicado(conexao, empresa_id)
    kb_id = None
    kb_versao = None
    if publicado is not None:
        kb_id = publicado["kb_id"]
        kb_versao = publicado["versao"]
    return {"escolhido": kit["escolhido"], "nome": kit["nome"], "cores": cores,
            "tem_logo": kit["endereco_do_logo"] is not None, "endereco_do_logo": kit["endereco_do_logo"],
            "kb_id": kb_id, "kb_versao": kb_versao}


# ---------------- 3b. O kit gravado pelos scripts (a migração e a carga da base viva) ----------------

def aplicar_o_kit(conexao, usuario, empresa_id: str) -> dict:
    """Aplica só o kit da empresa (a cópia derivada a partir da KB do kit publicada), sem mexer no catálogo.

    Recebe: usuario (só o BANCO); empresa_id. Devolve o que _aplicar_kit devolve.
    """
    autorizar(usuario, "editar_parametros")
    return _aplicar_kit(conexao, usuario, empresa_id)


def publicar_versao_do_kit(conexao, usuario, kb_id: str, versao: int, atualizar_indice: bool = True) -> dict:
    """Publica uma versão da KB do kit e aplica só o kit na empresa dona dela (a escolha, as cores e o logo).

    É o caminho dos scripts que gravam o kit: o catálogo do agente não muda com o kit, então não ganha versão nova,
    e a aplicação não entra no registro da tela (o autor fica gravado na própria versão). atualizar_indice=False deixa
    o índice do RAG como está (a carga da base viva promete não mexer nele; o kit entra na próxima indexação
    completa, scripts/indexar_kbs_endomarketing.py). Devolve: {kb, kit, indice_atualizado}.
    """
    autorizar(usuario, "editar_parametros")
    kb = kbs_endomarketing.publicar(conexao, usuario.login, kb_id, versao)
    kit = _aplicar_kit(conexao, usuario, kb["dono"])
    indice_atualizado = False
    if atualizar_indice:
        indice_atualizado = _atualizar_kb_no_indice(conexao, kb_id)
    return {"kb": kb, "kit": kit, "indice_atualizado": indice_atualizado}


def publicar_kit_novo(conexao, usuario, empresa_id: str, escolhido: str, texto: str, cores: list[str],
                      logo: bytes | None, origem: str, atualizar_indice: bool = True) -> dict:
    """Cria a KB do kit de uma empresa que ainda não tem uma, já publicada, com o kit informado, e aplica o kit.

    Recebe: usuario (só o BANCO); a empresa; a escolha, o texto da identidade e as cores; logo (os bytes da imagem,
    ou None); origem (de onde veio o kit, para a ficha); atualizar_indice (ver publicar_versao_do_kit).
    Devolve o que publicar_versao_do_kit devolve. TravaBloqueou se o kit não passa na trava (ex.: próprio sem cor).
    """
    autorizar(usuario, "editar_parametros")
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    conteudo = kbs_endomarketing.conteudo_do_kit_novo(conexao, empresa_id, empresa["nome"], escolhido, texto, cores,
                                                      origem)
    # O texto do kit é do banco (ou dos arquivos do case): basta a lista de frases do guardrail, sem gastar com IA
    salvo = kbs_endomarketing.salvar(conexao, usuario.login, conteudo)
    # O logo vai no rascunho, antes de publicar
    if logo is not None:
        kit_de_marca.gravar_logo_da_versao(conexao, salvo["kb_id"], salvo["versao"], logo, usuario.login)
    return publicar_versao_do_kit(conexao, usuario, salvo["kb_id"], salvo["versao"], atualizar_indice)


# ---------------- 4. Aplicar na empresa e o registro das aplicações ----------------

def _preparar(conexao) -> None:
    """Cria a tabela que registra cada vez que as KBs foram aplicadas numa empresa."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS kbs_publicacoes (
               publicacao_id  TEXT PRIMARY KEY,
               empresa_id     TEXT NOT NULL,
               resultado_json TEXT NOT NULL,     -- o que foi aplicado: catálogo, kit, logo e índice
               feito_em       TEXT NOT NULL,
               feito_por      TEXT NOT NULL
           )"""
    )
    conexao.commit()


def _atualizar_kb_no_indice(conexao, kb_id: str) -> bool:
    """Troca no índice de busca só os trechos desta KB. Devolve se deu certo.

    Uma falha do índice (ex.: sem o modelo de embeddings) não desfaz a publicação: a KB continua publicada, e o
    índice inteiro pode ser refeito depois com scripts/indexar_kbs_endomarketing.py.
    """
    try:
        indice_das_kbs.atualizar_uma_kb(conexao, kb_id)
    except Exception:  # noqa: BLE001 (qualquer falha do índice vira "índice não atualizado" na resposta)
        return False
    return True


def aplicar_na_empresa(conexao, usuario, empresa_id: str) -> dict:
    """Aplica as KBs publicadas da empresa: o catálogo do agente e o kit (a escolha, as cores e o logo da versão
    publicada da KB do kit; sem ela, o padrão). Fica registrado.

    Recebe: conexao; usuario (só o BANCO); empresa_id. Devolve: {empresa_id, catalogo, kit}.
    KeyError se a empresa não existe.
    """
    autorizar(usuario, "editar_parametros")
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    resultado = {"empresa_id": empresa_id,
                 "catalogo": _aplicar_catalogo(conexao, usuario, empresa_id, empresa["nome"]),
                 "kit": _aplicar_kit(conexao, usuario, empresa_id)}
    _preparar(conexao)
    conexao.execute("INSERT INTO kbs_publicacoes (publicacao_id, empresa_id, resultado_json, feito_em, feito_por) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, empresa_id, json.dumps(resultado, ensure_ascii=False),
                     datetime.now(timezone.utc).isoformat(timespec="seconds"), usuario.login))
    conexao.commit()
    return resultado


def aplicacoes(conexao, empresa_id: str | None = None, limite: int = 50) -> list[dict]:
    """As aplicações registradas, da mais recente para a mais antiga: [{empresa_id, resultado, feito_em, feito_por}]."""
    _preparar(conexao)
    consulta = conexao.execute(
        "SELECT empresa_id, resultado_json, feito_em, feito_por FROM kbs_publicacoes "
        "WHERE (? IS NULL OR empresa_id = ?) ORDER BY feito_em DESC LIMIT ?",
        (empresa_id, empresa_id, limite),
    )
    registros = []
    for empresa, resultado_json, feito_em, feito_por in consulta:
        registros.append({"empresa_id": empresa, "resultado": json.loads(resultado_json), "feito_em": feito_em,
                          "feito_por": feito_por})
    return registros


def donos_disponiveis(conexao) -> list[dict]:
    """Os donos que a tela oferece: as KBs gerais, o Santander e cada empresa da carteira ([{dono, nome}])."""
    donos = [{"dono": kbs_endomarketing.DONO_GERAL, "nome": "Diretrizes gerais"},
             {"dono": kbs_endomarketing.DONO_SANTANDER, "nome": "Santander (banco parceiro)"}]
    for empresa in cadastro_de_empresas.listar(conexao):
        donos.append({"dono": empresa["empresa_id"], "nome": empresa["nome"]})
    return donos


def _conferir_empresa_do_dono(conexao, ficha: dict) -> None:
    """Uma KB de empresa só pode ser gravada para uma empresa da carteira (KeyError se ela não existe)."""
    if kbs_endomarketing.e_codigo_de_empresa(ficha.get("dono", "")):
        cadastro_de_empresas.obter(conexao, ficha["dono"])


def salvar_kb(conexao, usuario, ficha: dict, corpo: str, kb_id: str | None = None) -> dict:
    """Grava uma KB nova (kb_id None) ou uma versão nova da KB kb_id, como rascunho, depois da trava.

    Recebe: usuario (só o BANCO); ficha e corpo (o formulário da tela). Devolve o que kbs_endomarketing.salvar
    devolve. TravaBloqueou se a trava bloquear.
    """
    autorizar(usuario, "editar_parametros")
    _conferir_empresa_do_dono(conexao, ficha)
    # Numa versão nova, a KB precisa existir
    if kb_id:
        kbs_endomarketing.obter(conexao, kb_id)
    conteudo = kbs_endomarketing.conteudo_do_formulario(conexao, ficha, corpo, kb_id)
    return kbs_endomarketing.salvar(conexao, usuario.login, conteudo)


def verificar_kb(conexao, usuario, ficha: dict, corpo: str, kb_id: str | None = None) -> list[dict]:
    """Roda a trava no formulário sem gravar a KB (os achados ficam registrados para a Telemetria)."""
    autorizar(usuario, "editar_parametros")
    conteudo = kbs_endomarketing.conteudo_do_formulario(conexao, ficha, corpo, kb_id)
    return kbs_endomarketing.verificar(conexao, usuario.login, conteudo)


def _muda_a_empresa(kb: dict) -> bool:
    """Diz se publicar ou retirar esta KB muda o que a empresa vê (vitrine, catálogo ou kit)."""
    return kbs_endomarketing.e_codigo_de_empresa(kb["dono"]) and kb["tipo"] in TIPOS_DA_VITRINE + (TIPO_DO_KIT,)


def publicar_kb(conexao, usuario, kb_id: str, versao: int) -> dict:
    """Publica a versão da KB (com a trava) e, se ela for de uma empresa e mudar a vitrine ou o kit, aplica na empresa.

    Devolve: {kb, aplicacao} (aplicacao é None quando a KB não muda o que a empresa vê).
    """
    autorizar(usuario, "editar_parametros")
    kb = kbs_endomarketing.publicar(conexao, usuario.login, kb_id, versao)
    aplicacao = None
    if _muda_a_empresa(kb):
        aplicacao = aplicar_na_empresa(conexao, usuario, kb["dono"])
    return {"kb": kb, "aplicacao": aplicacao, "indice_atualizado": _atualizar_kb_no_indice(conexao, kb_id)}


def retirar_kb(conexao, usuario, kb_id: str) -> dict:
    """Retira a versão publicada da KB e, se ela mudava a vitrine ou o kit da empresa, aplica de novo na empresa."""
    autorizar(usuario, "editar_parametros")
    kb = kbs_endomarketing.retirar(conexao, usuario.login, kb_id)
    aplicacao = None
    if _muda_a_empresa(kb):
        aplicacao = aplicar_na_empresa(conexao, usuario, kb["dono"])
    return {"kb": kb, "aplicacao": aplicacao, "indice_atualizado": _atualizar_kb_no_indice(conexao, kb_id)}


def revisar_kb(conexao, usuario, kb_id: str, nova_vigencia_fim: str) -> dict:
    """Revisa a vigência da KB e, se a versão revisada já saiu publicada e muda a empresa, aplica na empresa."""
    autorizar(usuario, "editar_parametros")
    kb = kbs_endomarketing.revisar(conexao, usuario.login, kb_id, nova_vigencia_fim)
    aplicacao = None
    if kb["situacao"] == kbs_endomarketing.PUBLICADA and _muda_a_empresa(kb):
        aplicacao = aplicar_na_empresa(conexao, usuario, kb["dono"])
    return {"kb": kb, "aplicacao": aplicacao, "indice_atualizado": _atualizar_kb_no_indice(conexao, kb_id)}


def enviar_logo_da_kb(conexao, usuario, kb_id: str, versao: int, conteudo: bytes) -> dict:
    """O especialista anexa (ou troca) o logo de um rascunho da KB do kit. Devolve {kb_id, versao, tem_logo: True}.

    O logo só passa a valer para a arte quando esse rascunho for publicado (aí o "aplicar na empresa" o copia).
    """
    autorizar(usuario, "editar_parametros")
    return kbs_endomarketing.anexar_logo_ao_rascunho(conexao, usuario.login, kb_id, versao, conteudo)


def tirar_logo_da_kb(conexao, usuario, kb_id: str, versao: int) -> dict:
    """O especialista tira o logo de um rascunho da KB do kit. Devolve {kb_id, versao, tem_logo: False}."""
    autorizar(usuario, "editar_parametros")
    return kbs_endomarketing.tirar_logo_do_rascunho(conexao, kb_id, versao)


def logo_da_kb(conexao, usuario, kb_id: str, versao: int) -> tuple[bytes, str]:
    """A imagem do logo de uma versão da KB do kit, em qualquer situação, para o editor mostrar: (bytes, tipo)."""
    autorizar(usuario, "editar_parametros")
    return kbs_endomarketing.imagem_do_logo(conexao, kb_id, versao)


# ---------------- 5. O contexto pronto para o agente ----------------

def _posicao_no_contexto(kb: dict) -> int:
    """A posição do tipo da KB na ordem do contexto (tipos fora da lista vão para o fim)."""
    if kb["tipo"] in ORDEM_DO_CONTEXTO:
        return ORDEM_DO_CONTEXTO.index(kb["tipo"])
    return len(ORDEM_DO_CONTEXTO)


def contexto_do_agente(conexao, empresa_id: str) -> dict:
    """O pacote de KBs publicadas e vigentes que o agente recebe para escrever o material de UMA empresa.

    Entram: as KBs GERAIS; o kit da empresa (o do Santander quando ela não tem kit próprio publicado); a jornada da
    empresa (sem ela, a jornada padrão); o atendimento, os benefícios e a landing page da empresa. A prateleira do
    Santander fica de fora: ela é a base das empresas, não a oferta de uma empresa.
    Devolve: {empresa_id, kbs: [{kb_id, versao, tipo, dono, titulo}], texto}. KeyError se a empresa não existe.
    """
    cadastro_de_empresas.obter(conexao, empresa_id)
    gerais = kbs_endomarketing.kbs_publicadas(conexao, dono=kbs_endomarketing.DONO_GERAL)
    da_empresa = kbs_endomarketing.kbs_publicadas(conexao, dono=empresa_id)
    tipos_da_empresa = set()
    for kb in da_empresa:
        tipos_da_empresa.add(kb["tipo"])
    escolhidas = list(da_empresa)
    # A jornada padrão só entra se a empresa não tem a dela
    for kb in gerais:
        if kb["tipo"] == "jornada" and "jornada" in tipos_da_empresa:
            continue
        escolhidas.append(kb)
    # O kit do Santander entra quando a empresa não tem kit próprio publicado
    kit_da_empresa = _kit_publicado(conexao, empresa_id)
    if kit_da_empresa is None or kit_da_empresa["ficha"].get("kit_escolhido") != kbs_endomarketing.KIT_PROPRIO:
        for kb in kbs_endomarketing.kbs_publicadas(conexao, dono=kbs_endomarketing.DONO_SANTANDER, tipo=TIPO_DO_KIT):
            escolhidas.append(kb)
        # O kit da empresa que diz "padrao" não precisa ir junto (o do Santander já diz tudo)
        if kit_da_empresa is not None:
            escolhidas.remove(kit_da_empresa)
    escolhidas.sort(key=_posicao_no_contexto)
    lista = []
    partes_do_texto = []
    for kb in escolhidas:
        lista.append({"kb_id": kb["kb_id"], "versao": kb["versao"], "tipo": kb["tipo"], "dono": kb["dono"],
                      "titulo": kb["titulo"]})
        # Cada KB no texto com a fonte (o id e a versão), para o agente citar de onde veio
        partes_do_texto.append(f"[KB {kb['kb_id']} v{kb['versao']}]\n{kb['corpo']}")
    return {"empresa_id": empresa_id, "kbs": lista, "texto": "\n\n".join(partes_do_texto)}
