"""Aba "Endomarketing" do Portal Interno: o especialista do banco gera, confere e publica os materiais (ADR-115).

Para que serve: dá à tela front/banco_endomarketing.html o que ela precisa para cada empresa da carteira:
    - o kit de marca (cores do kit e o logo), para desenhar a arte. O kit vem da KB "Kit da marca" da empresa, a
      fonte única (services/kbs_publicacao.py copia a versão publicada para o cadastro e para o logo que se lê aqui);
    - os benefícios do catálogo vigente da empresa, para o especialista marcar os que entram em cada material;
    - as sugestões (quantos ainda não têm conta; inclusões que ainda não ganharam o kit de boas-vindas);
    - os materiais da empresa, com a situação de cada um (rascunho, publicado, descartado, retirado).
E recebe as ações: gerar o rascunho, publicar (com a arte), descartar e retirar. O logo e as cores se mudam na KB.

Por que o banco gera e a empresa só baixa (ADR-115): risco de a empresa divulgar um benefício do Santander sem a
validação do Santander. O banco gera e valida; a empresa comunica.
As operações sensíveis passam pela porta (services/acesso.py), que confere de novo o perfil BANCO.
"""
from agents import endomarketing
from services import acesso, catalogo, kit_de_marca, portal_do_banco
from services import empresas as cadastro_de_empresas
from services.permissoes import autorizar

# As cores do kit padrão (as mesmas do molde da arte: faixa, rodapé, fundo, texto e texto de apoio)
CORES_DO_KIT_PADRAO = {"cor_principal": "#d62839", "cor_escura": "#9e1b32", "cor_fundo": "#ffffff",
                       "cor_texto": "#222222", "cor_apoio": "#5c6366"}


# ---------------- O kit de marca ----------------

def _escurecer(cor: str) -> str:
    """Uma versão mais escura da cor (70% de cada componente), para o rodapé quando o banco deu uma cor só.

    Recebe: a cor em "#rrggbb". Devolve: a cor escurecida. Exemplo: "#1f7a4d" → "#155535".
    """
    componentes = []
    # Os três pares de dígitos: vermelho, verde e azul, de 0 a 255
    for posicao in (1, 3, 5):
        valor = int(cor[posicao:posicao + 2], 16)
        componentes.append(format(int(valor * 0.7), "02x"))
    return "#" + "".join(componentes)


def kit_da_empresa(conexao, empresa_id: str) -> dict:
    """O kit de marca da empresa, pronto para a arte do endomarketing.

    Lê a cópia derivada (o cadastro e o logo da empresa), que o "aplicar na empresa" grava a partir da versão
    publicada da KB do kit (services/kbs_publicacao.py).
    Recebe: conexao; empresa_id. Devolve: {escolhido ("padrao" ou "proprio"), nome, marca, assinatura, cor_principal,
    cor_escura, cor_fundo, cor_texto, cor_apoio, tem_logo, endereco_do_logo}.
    Kit próprio: a 1ª cor gravada é a principal (a faixa de cima) e a 2ª, a do rodapé (sem a 2ª, a principal
    escurecida); a assinatura é o nome da empresa; o logo entra se foi enviado. Kit padrão: as cores do padrão, sem
    assinatura e sem logo. KeyError se a empresa não existe.
    """
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    kit = dict(CORES_DO_KIT_PADRAO)
    tem_logo = kit_de_marca.tem_logo(conexao, empresa_id)
    # Kit padrão: nada da empresa na arte (o logo, se existir, fica guardado para quando o kit próprio voltar)
    if empresa["kit_escolhido"] != cadastro_de_empresas.KIT_PROPRIO:
        kit.update({"escolhido": "padrao", "nome": "Padrão Santander", "marca": "Santander", "assinatura": "",
                    "tem_logo": tem_logo, "endereco_do_logo": None})
        return kit
    # Kit próprio: o nome e a assinatura da empresa, e o logo quando houver
    endereco_do_logo = None
    if tem_logo:
        endereco_do_logo = f"/api/banco/empresas/{empresa_id}/kit/logo"
    kit.update({"escolhido": "proprio", "nome": "Kit da " + empresa["nome"], "marca": "Santander",
                "assinatura": empresa["nome"], "tem_logo": tem_logo, "endereco_do_logo": endereco_do_logo})
    cores = empresa["kit_cores"]
    # A 1ª cor é a faixa; a 2ª, o rodapé (ou a 1ª escurecida)
    if cores:
        kit["cor_principal"] = cores[0]
        kit["cor_escura"] = _escurecer(cores[0])
    if len(cores) > 1:
        kit["cor_escura"] = cores[1]
    return kit


def logo_da_empresa(conexao, usuario, empresa_id: str) -> tuple[bytes, str]:
    """O logo da empresa (bytes, tipo), para a prévia e para a arte. Sem logo: KeyError (vira 404)."""
    autorizar(usuario, "editar_empresas")
    # A empresa precisa existir (KeyError vira 404); num banco novo, isto põe a semente, que nasce com o logo da KB
    cadastro_de_empresas.obter(conexao, empresa_id)
    logo = kit_de_marca.logo(conexao, empresa_id)
    if logo is None:
        raise KeyError(empresa_id)
    return logo


# ---------------- Os materiais ----------------

def material_para_o_banco(material: dict) -> dict:
    """Um material no formato da tela do banco (contrato do ADR-115).

    Recebe: o material como endomarketing.listar devolve. Devolve: {material_id, tipo, nome_do_tipo, canal,
    nome_do_canal, titulo, blocos, observacoes, beneficios, status, nome_do_status, criado_em, criado_por,
    publicado_em, publicado_por, retirado_em, retirado_por, tem_arte}.
    """
    conteudo = material["conteudo"]
    # Materiais antigos não guardavam o canal nem os benefícios: e-mail e lista vazia
    canal = conteudo.get("canal", endomarketing.CANAL_PADRAO)
    return {"material_id": material["material_id"], "tipo": material["tipo"],
            "nome_do_tipo": endomarketing.TIPOS[material["tipo"]]["nome"], "canal": canal,
            "nome_do_canal": endomarketing.CANAIS[canal]["nome"], "titulo": conteudo["titulo"],
            "blocos": conteudo["blocos"], "observacoes": conteudo.get("observacoes", []),
            "beneficios": conteudo.get("beneficios", []), "status": material["status"],
            "nome_do_status": endomarketing.NOME_DA_SITUACAO[material["status"]],
            "criado_em": material["criado_em"], "criado_por": material["criado_por"],
            "publicado_em": material["publicado_em"], "publicado_por": material["publicado_por"],
            "retirado_em": material["retirado_em"], "retirado_por": material["retirado_por"],
            "tem_arte": material["tem_arte"]}


def empresas_do_endomarketing(conexao, usuario) -> list[dict]:
    """As empresas da carteira para o seletor da aba, com quantos rascunhos e publicados cada uma tem.

    Devolve: [{empresa_id, nome, rascunhos, publicados, cnpjs, cadastrada_em}], na ordem do código. cnpjs: todos os
    CNPJs da empresa, só com os números (o principal primeiro, depois filiais e grupo, ADR-77), para a busca pelo
    CNPJ; cadastrada_em: quando ela entrou na carteira, para a lista mostrar as últimas cadastradas.
    """
    autorizar(usuario, "gerar_material")
    # Quando cada empresa entrou na carteira
    datas_de_cadastro = cadastro_de_empresas.datas_de_cadastro(conexao)
    empresas = []
    for empresa in cadastro_de_empresas.listar(conexao):
        rascunhos = 0
        publicados = 0
        # Conta as situações dos materiais desta empresa
        for material in endomarketing.listar(conexao, empresa["empresa_id"]):
            if material["status"] == endomarketing.RASCUNHO:
                rascunhos += 1
            elif material["status"] == endomarketing.PUBLICADO:
                publicados += 1
        empresas.append({"empresa_id": empresa["empresa_id"], "nome": empresa["nome"], "rascunhos": rascunhos,
                         "publicados": publicados,
                         # Os CNPJs para a busca: a mesma função da busca por CNPJ do Painel de acompanhamento
                         "cnpjs": portal_do_banco.cnpjs_para_a_busca(conexao, empresa),
                         "cadastrada_em": datas_de_cadastro.get(empresa["empresa_id"])})
    return empresas


def _beneficios_para_escolher(conexao, empresa_id: str) -> list[dict]:
    """Os benefícios do catálogo vigente da empresa, com o resumo e a categoria, para as caixas de marcar.

    Devolve: [{titulo, resumo, categoria}], sem repetir o mesmo benefício de dois documentos.
    """
    beneficios = []
    titulos_vistos = set()
    for documento in catalogo.documentos_vigentes(conexao, empresa_id):
        for secao in catalogo.secoes_do_documento(documento["conteudo_md"]):
            # Atendimento não é benefício (entra sozinho em todo material) e repetido sai
            if secao["titulo"] in catalogo.SECOES_DE_ATENDIMENTO or secao["titulo"] in titulos_vistos:
                continue
            titulos_vistos.add(secao["titulo"])
            partes = catalogo.partes_do_beneficio(secao["texto"].replace("**", ""))
            beneficios.append({"titulo": secao["titulo"], "resumo": partes["resumo"],
                               "categoria": partes["categoria"]})
    return beneficios


def tela_da_empresa(conexao, usuario, empresa_id: str) -> dict:
    """Tudo o que a aba mostra para uma empresa: kit, benefícios, sugestões, materiais, tipos e canais.

    Recebe: conexao; usuario (da sessão, perfil BANCO); empresa_id (escolhido na tela). KeyError se não existe.
    """
    autorizar(usuario, "gerar_material")
    empresa = cadastro_de_empresas.obter(conexao, empresa_id)
    materiais = []
    for material in endomarketing.listar(conexao, empresa_id):
        materiais.append(material_para_o_banco(material))
    tipos = []
    for chave, tipo in endomarketing.TIPOS.items():
        tipos.append({"chave": chave, "nome": tipo["nome"]})
    canais = []
    for chave, canal in endomarketing.CANAIS.items():
        canais.append({"chave": chave, "nome": canal["nome"], "maximo_de_blocos": canal["maximo_de_blocos"]})
    return {"empresa": {"empresa_id": empresa_id, "nome": empresa["nome"]},
            "kit": kit_da_empresa(conexao, empresa_id),
            "beneficios": _beneficios_para_escolher(conexao, empresa_id),
            "sugestoes": {"sem_conta": endomarketing.consultar_resumo_equipe(conexao, empresa_id),
                          "kits": endomarketing.sugestoes_de_kit(conexao, empresa_id)},
            "materiais": materiais, "tipos": tipos, "canais": canais}


def _envio_pede_kit(conexao, empresa_id: str, processamento_id: str) -> bool:
    """Diz se o envio é uma inclusão cadastrada DESTA empresa que ainda espera o kit de boas-vindas.

    Por quê: o identificador vem da tela; sem esta conferência, o kit de uma empresa ficaria ligado ao envio de outra.
    """
    for sugestao in endomarketing.sugestoes_de_kit(conexao, empresa_id):
        if sugestao["processamento_id"] == processamento_id:
            return True
    return False


def gerar_material(conexao, usuario, empresa_id: str, tipo: str, canal: str, beneficios: list[str],
                   destaque: str = "", processamento_id: str | None = None) -> dict:
    """O especialista pede ao Agente de Endomarketing um rascunho para a empresa, com os benefícios marcados.

    Recebe: tipo; canal; beneficios (os nomes marcados; pelo menos um); destaque (pode ser vazio);
    processamento_id (só no kit de boas-vindas de uma inclusão, vindo da sugestão).
    Devolve: {situacao, mensagem, material_id, material (formato do banco, ou None), observacoes}.
    """
    # A empresa precisa existir (KeyError vira 404)
    cadastro_de_empresas.obter(conexao, empresa_id)
    # O envio ligado ao kit precisa ser desta empresa (e ainda sem kit)
    if processamento_id and not _envio_pede_kit(conexao, empresa_id, processamento_id):
        raise ValueError("Este envio não espera um kit de boas-vindas.")
    resultado = acesso.gerar_material(conexao, usuario, empresa_id, tipo, beneficios, destaque=destaque,
                                      processamento_id=processamento_id, canal=canal)
    # O material guardado, no formato da tela (só quando o rascunho foi gerado)
    material = None
    if resultado.material_id:
        material = material_para_o_banco(endomarketing.obter(conexao, empresa_id, resultado.material_id))
    return {"situacao": resultado.situacao, "mensagem": resultado.mensagem, "material_id": resultado.material_id,
            "material": material, "observacoes": resultado.observacoes}


def publicar_material(conexao, usuario, empresa_id: str, material_id: str, arte_png: bytes | None) -> dict:
    """Publica o rascunho para a empresa, com a arte desenhada na tela (se veio). Devolve o material atualizado."""
    # A arte é conferida antes de gravar: PNG de verdade e até 2 MB
    if arte_png is not None:
        kit_de_marca.conferir_arte(arte_png)
    acesso.publicar_material(conexao, usuario, empresa_id, material_id, arte_png)
    return material_para_o_banco(endomarketing.obter(conexao, empresa_id, material_id))


def descartar_material(conexao, usuario, empresa_id: str, material_id: str) -> dict:
    """Descarta um rascunho (a empresa nunca o vê). Devolve o material atualizado."""
    acesso.descartar_material(conexao, usuario, empresa_id, material_id)
    return material_para_o_banco(endomarketing.obter(conexao, empresa_id, material_id))


def retirar_material(conexao, usuario, empresa_id: str, material_id: str) -> dict:
    """Retira um material publicado (a empresa deixa de ver e de baixar). Devolve o material atualizado."""
    acesso.retirar_material(conexao, usuario, empresa_id, material_id)
    return material_para_o_banco(endomarketing.obter(conexao, empresa_id, material_id))


def arte_do_material(conexao, usuario, empresa_id: str, material_id: str) -> bytes:
    """A imagem PNG da arte de um material da empresa (qualquer situação), para o banco conferir. Sem arte: KeyError."""
    autorizar(usuario, "gerar_material")
    return endomarketing.arte(conexao, empresa_id, material_id)
