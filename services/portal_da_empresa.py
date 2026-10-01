"""Portal Empresa no novo front: o Início, os Benefícios do time e o Endomarketing, com dados reais (ADR-69).

Para que serve: dá às telas do Portal Empresa (front/home.html, beneficios.html e endomarketing.html) o que a
aplicação já tem, sempre da empresa de quem entrou (a empresa vem da sessão, nunca da tela):
    - Início: nome da empresa, os números dos cadastros e a etapa em que ela está (carga inicial e inclusões);
    - Benefícios: SÓ as KBs de benefício PUBLICADAS e vigentes da empresa, mais a KB de canais de atendimento
      (ADR-125), no mesmo formato do catálogo e separadas em benefícios e atendimento;
    - Endomarketing: a lista dos materiais que o banco gerou e PUBLICOU para a empresa, para ela baixar o texto e a
      arte e divulgar. A empresa não gera material (ADR-115): quem gera e valida é o especialista do banco.
Este arquivo NÃO tem regra nova: só junta e formata o que os serviços de sempre devolvem.
"""
from agents import endomarketing
from services import acompanhamento, catalogo, contas_abertas, dados_mock, kbs_publicacao


# ---------------- Início ----------------

def _etapas_da_jornada(envios: list[dict]) -> dict:
    """Em que etapa do cadastro a empresa está: a carga inicial (se já foi cadastrada) e as inclusões.

    Recebe: os envios da empresa (do mais recente para o mais antigo, como Acompanhar devolve).
    Devolve: {carga_inicial: {enviado_em, cadastrados} ou None, inclusoes: {envios, cadastrados}}.
    Exemplo: uma carga inicial cadastrada com 35 pessoas e nenhuma inclusão →
             {carga_inicial: {"enviado_em": "...", "cadastrados": 35}, inclusoes: {"envios": 0, "cadastrados": 0}}.
    """
    carga_inicial = None
    envios_de_inclusao = 0
    cadastrados_por_inclusao = 0
    for envio in envios:
        # A carga inicial que já virou cadastro (as descartadas não contam)
        if envio["tipo_carga"] == "INICIAL" and envio["situacao"] == "Cadastrado":
            carga_inicial = {"enviado_em": envio["enviado_em"], "cadastrados": envio["cadastrados"]}
        # Cada arquivo de inclusão que não foi descartado
        if envio["tipo_carga"] == "INCLUSAO" and envio["situacao"] != "Descartado":
            envios_de_inclusao = envios_de_inclusao + 1
            cadastrados_por_inclusao = cadastrados_por_inclusao + envio["cadastrados"]
    return {"carga_inicial": carga_inicial,
            "inclusoes": {"envios": envios_de_inclusao, "cadastrados": cadastrados_por_inclusao}}


def inicio_da_empresa(conexao, empresa_id: str) -> dict:
    """O Início do Portal Empresa: nome, números dos cadastros, etapa da jornada e pendências a corrigir.

    Recebe: conexao; empresa_id (da sessão). Devolve: {empresa, numeros, jornada, linhas_para_corrigir, sem_conta,
    contas} (contas: o total da empresa no arquivo semanal do banco).
    Só números da própria empresa: nenhum funcionário aparece aqui (a conta de cada um fica na lista de funcionários,
    ADR-102). sem_conta é o total da empresa, o mesmo cálculo do Agente de Endomarketing.
    """
    envios = acompanhamento.envios_da_empresa(conexao, empresa_id)
    # Quantas pendências pedem correção (as que só pedem confirmação não travam o cadastro)
    linhas_para_corrigir = 0
    for pendencia in acompanhamento.pendencias_da_empresa(conexao, empresa_id):
        if pendencia["tipo"] == "corrigir":
            linhas_para_corrigir = linhas_para_corrigir + 1
    # Os números, com as pessoas em análise pelo banco (o mesmo 2º cartão de Acompanhar cadastros)
    numeros = acompanhamento.resumo_da_empresa(conexao, empresa_id)
    numeros["pessoas_em_analise"] = acompanhamento.pessoas_em_analise_pelo_banco(conexao, empresa_id)
    return {
        "empresa": dados_mock.nome_da_empresa(empresa_id),
        "numeros": numeros,
        "jornada": _etapas_da_jornada(envios),
        "linhas_para_corrigir": linhas_para_corrigir,
        "sem_conta": endomarketing.consultar_resumo_equipe(conexao, empresa_id),
        "contas": contas_abertas.contas_para_a_empresa(conexao, empresa_id),
    }


# ---------------- Benefícios do time ----------------

def _texto_corrido(separado: dict) -> str:
    """O benefício em texto corrido, para o quadro de dúvidas: o resumo e cada parte com o nome dela.

    Recebe: o resultado de catalogo.partes_do_beneficio. Devolve: o texto, sem as marcas "###" do Markdown.
    Exemplo: resumo "Taxa negociada." + como_funciona "Parcelas na folha." → "Taxa negociada.\\nComo funciona: Parcelas
    na folha."
    """
    linhas = []
    if separado["resumo"]:
        linhas.append(separado["resumo"])
    # As partes na ordem da vitrine, com o nome de cada uma
    for nome, chave in catalogo.PARTES_DO_BENEFICIO.items():
        if separado["partes"].get(chave):
            linhas.append(nome + ": " + separado["partes"][chave])
    return "\n".join(linhas)


def beneficios_da_empresa(conexao, empresa_id: str) -> dict:
    """As KBs publicadas e vigentes da empresa (ADR-125), separadas em benefícios e atendimento.

    Recebe: conexao; empresa_id (da sessão: a empresa A nunca vê o catálogo da B).
    Devolve: {empresa, documentos: [{titulo, versao, vigencia_fim}], beneficios: [...], atendimento: [...]},
    cada seção como {titulo, texto, documento, versao}. O texto vem sem as marcas de negrito do Markdown ("**").
    Cada benefício traz também categoria (a chave do filtro, ou None), resumo e partes ({como_funciona,
    quem_pode_usar, como_contratar}, as que a KB tiver): a vitrine só mostra o que as KBs publicadas dizem.
    KB em rascunho, retirada ou vencida não aparece; "documento" e "versao" são o título e a versão da KB.
    """
    documentos = []
    beneficios = []
    atendimento = []
    for documento in kbs_publicacao.documentos_da_vitrine(conexao, empresa_id):
        documentos.append({"titulo": documento["titulo"], "versao": documento["versao"],
                           "vigencia_fim": documento["vigencia_fim"]})
        for secao in catalogo.secoes_do_documento(documento["conteudo_md"]):
            texto_sem_negrito = secao["texto"].replace("**", "")
            # A seção com a fonte (documento e versão), para a tela dizer de onde veio cada texto
            item = {"titulo": secao["titulo"], "texto": texto_sem_negrito,
                    "documento": documento["titulo"], "versao": documento["versao"]}
            if secao["titulo"] in catalogo.SECOES_DE_ATENDIMENTO:
                atendimento.append(item)
            else:
                # O benefício ganha a categoria (filtro da vitrine) e as três partes da janela de detalhes
                separado = catalogo.partes_do_beneficio(texto_sem_negrito)
                item.update({"categoria": separado["categoria"], "resumo": separado["resumo"],
                             "partes": separado["partes"], "texto": _texto_corrido(separado)})
                beneficios.append(item)
    return {"empresa": dados_mock.nome_da_empresa(empresa_id), "documentos": documentos,
            "beneficios": beneficios, "atendimento": atendimento}


# ---------------- Endomarketing: só os materiais que o banco publicou (ADR-115) ----------------

def _material_para_a_empresa(material: dict) -> dict:
    """Um material publicado no formato da tela da empresa: o que ela precisa para ler e baixar, e nada mais.

    Recebe: o material como endomarketing.listar devolve. Devolve: {material_id, tipo, nome_do_tipo, canal,
    nome_do_canal, titulo, blocos, publicado_em, tem_arte}. Quem gerou, o modelo e as observações ficam no banco.
    """
    conteudo = material["conteudo"]
    # Materiais antigos não guardavam o canal: eram de e-mail
    canal = conteudo.get("canal", endomarketing.CANAL_PADRAO)
    return {"material_id": material["material_id"], "tipo": material["tipo"],
            "nome_do_tipo": endomarketing.TIPOS[material["tipo"]]["nome"], "canal": canal,
            "nome_do_canal": endomarketing.CANAIS[canal]["nome"], "titulo": conteudo["titulo"],
            "blocos": conteudo["blocos"], "publicado_em": material["publicado_em"], "tem_arte": material["tem_arte"]}


def materiais_da_empresa(conexao, empresa_id: str) -> list[dict]:
    """Os materiais que o banco PUBLICOU para a empresa, do mais recente ao mais antigo, prontos para baixar.

    Recebe: conexao; empresa_id (da sessão). Devolve: [material no formato de _material_para_a_empresa].
    Rascunhos, descartados, retirados e os antigos aprovados pela própria empresa nunca aparecem aqui: a empresa só
    divulga o que o banco validou.
    """
    materiais = []
    for material in endomarketing.listar(conexao, empresa_id, endomarketing.PUBLICADO):
        materiais.append(_material_para_a_empresa(material))
    return materiais


def arte_do_material(conexao, empresa_id: str, material_id: str) -> bytes:
    """A imagem PNG da arte de um material PUBLICADO da empresa.

    Recebe: conexao; empresa_id (da sessão); material_id (da tela). Devolve: os bytes da imagem.
    Material de outra empresa, não publicado ou sem arte: KeyError (vira 404, sem dizer se ele existe).
    """
    material = endomarketing.obter(conexao, empresa_id, material_id)
    # Só o que está publicado pode ser baixado (um material retirado deixa de ser baixável na hora)
    if material["status"] != endomarketing.PUBLICADO:
        raise KeyError(material_id)
    return endomarketing.arte(conexao, empresa_id, material_id)
