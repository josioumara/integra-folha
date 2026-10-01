"""Correções de dado pedidas na correção assistida (ADR-16).

Uma correção é um PEDIDO (CorrectionRequest) com antes, depois, motivo, quem propôs e quem aprovou.
Ela só muda o dado depois do clique de uma pessoa da empresa; cancelar não muda nada. O valor novo passa
pelas mesmas regras do Normalizador (um salário "5.200,00" vira 5200.00; "cinco mil" é recusado).
Excluir um registro repetido também é uma correção, com o mesmo controle.
A única correção sem clique é a do próprio sistema: o valor inválido de um campo opcional fica em branco (ADR-143).
"""
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from services import auditoria, normalizador, parametros, processamentos

# Campo especial: retira o registro inteiro (ex.: pessoa repetida no arquivo)
EXCLUIR = "__excluir__"
# O status da correção que o próprio sistema faz: o valor inválido de um campo opcional fica em branco (ADR-143).
# Não é correção da empresa: fica fora das contas dela ("a empresa corrigiu N
# valores", a qualidade da homologação), não se desfaz e só vale enquanto a célula tem o valor que o sistema tirou
EM_BRANCO_PELO_SISTEMA = "EM_BRANCO_PELO_SISTEMA"
# Quem faz a correção do sistema (o mesmo jeito do registro do parâmetro, "sistema (ADR-128)")
SISTEMA = "sistema (ADR-143)"


@dataclass
class Correcao:
    """Um pedido de correção (as colunas da tabela `correcoes`, na mesma ordem)."""

    correcao_id: str
    processamento_id: str
    linha: int                # linha do arquivo, como a empresa vê no Excel
    campo: str                # campo do layout, ou EXCLUIR
    antes: str | None
    depois: str | None        # já padronizado
    motivo: str
    status: str               # PROPOSTA, APLICADA, CANCELADA, DESFEITA (aplicada e depois desfeita pela empresa) ou
                              # EM_BRANCO_PELO_SISTEMA (o valor inválido de um campo opcional, ADR-143)
    proposta_por: str         # quem pediu (a empresa, ou "assistente" em nome dela)
    criado_em: str
    aprovada_por: str | None = None
    decidido_em: str | None = None


def _agora() -> str:
    """Data e hora atuais (UTC), em texto."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _agora_do_lote() -> str:
    """Data e hora atuais (UTC), com microssegundos: a marca de um lote ("Preencher para todos", troca em grupo).

    Por quê: o Desfazer reconhece o lote pela hora (e pelo campo, por quem pediu e pelo motivo). Com a hora só em
    segundos, duas respostas iguais no mesmo campo dentro do mesmo segundo (ex.: "Casado" para dois grupos, em dois
    cliques rápidos) virariam um lote só, e o Desfazer de um desfaria os dois.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _preparar(conexao) -> None:
    """Cria a tabela das correções, se ainda não existir."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS correcoes (
               correcao_id      TEXT PRIMARY KEY,
               processamento_id TEXT NOT NULL,
               linha            INTEGER NOT NULL,
               campo            TEXT NOT NULL,
               antes            TEXT,
               depois           TEXT,
               motivo           TEXT NOT NULL,
               status           TEXT NOT NULL,
               proposta_por     TEXT NOT NULL,
               criado_em        TEXT NOT NULL,
               aprovada_por     TEXT,
               decidido_em      TEXT
           )"""
    )


def listar(conexao, processamento_id: str, status: str | None = None) -> list[Correcao]:
    """As correções do processamento, na ordem em que foram pedidas; com `status`, só as daquele status."""
    _preparar(conexao)
    # As colunas na ordem dos campos de Correcao (nomeadas: no PostgreSQL a tabela tem também a coluna rowid)
    linhas = conexao.execute("SELECT correcao_id, processamento_id, linha, campo, antes, depois, motivo, status, "
                             "proposta_por, criado_em, aprovada_por, decidido_em FROM correcoes "
                             "WHERE processamento_id = ? AND (? IS NULL OR status = ?) "
                             "ORDER BY criado_em, rowid", (processamento_id, status, status))
    correcoes = []
    for linha in linhas:
        correcoes.append(Correcao(*linha))
    return correcoes


def _o_branco_do_sistema_vale(registro: dict, correcao: Correcao) -> bool:
    """True se o branco do sistema ainda vale: a célula tem o mesmo valor inválido que ele tirou (ADR-143).

    Por quê: se depois a empresa pôs outro valor, ou a correção dela que trouxe o valor inválido foi desfeita, o
    branco antigo não pode apagar o valor que está lá agora.
    Ex.: o sistema tirou o CEP "7"; a célula ainda é "7" → True; a empresa corrigiu para "01310100" → False.
    """
    valor_de_agora = registro.get(correcao.campo)
    if valor_de_agora is None:
        return False
    return str(valor_de_agora) == correcao.antes


def aplicar_sobre(normalizacao: normalizador.Normalizacao,
                  aplicadas: list[Correcao]) -> normalizador.Normalizacao:
    """A padronização com as correções que mudam o dado por cima (o original fica intacto, para auditoria).

    aplicadas: as correções APLICADAS e os brancos do sistema (EM_BRANCO_PELO_SISTEMA), na ordem em que foram feitos.
    """
    # Cópia de cada registro, para não mexer no original
    registros = []
    for registro in normalizacao.registros:
        registros.append(dict(registro))
    celulas_corrigidas, linhas_excluidas = set(), set()
    for correcao in aplicadas:
        if correcao.campo == EXCLUIR:
            linhas_excluidas.add(correcao.linha)
            continue
        for registro in registros:
            if registro["_linha"] != correcao.linha:
                continue
            # O branco do sistema só vale enquanto a célula tem o valor inválido que ele tirou
            if correcao.status == EM_BRANCO_PELO_SISTEMA and not _o_branco_do_sistema_vale(registro, correcao):
                continue
            registro[correcao.campo] = correcao.depois
            celulas_corrigidas.add((correcao.linha, correcao.campo))
    # Tira as linhas excluídas
    registros_que_ficam = []
    for registro in registros:
        if registro["_linha"] not in linhas_excluidas:
            registros_que_ficam.append(registro)
    # Valor não convertido que foi corrigido (ou cuja linha saiu) deixa de ser pendência
    nao_convertidos_restantes = []
    for nao_convertido in normalizacao.nao_convertidos:
        corrigido = (nao_convertido["linha"], nao_convertido["campo"]) in celulas_corrigidas
        excluido = nao_convertido["linha"] in linhas_excluidas
        if not corrigido and not excluido:
            nao_convertidos_restantes.append(nao_convertido)
    return replace(normalizacao, registros=registros_que_ficam, nao_convertidos=nao_convertidos_restantes)


def _correcoes_que_mudam_o_dado(conexao, processamento_id: str) -> list[Correcao]:
    """As correções que valem sobre a padronização, na ordem em que foram feitas: as APLICADAS pela empresa e os
    brancos do sistema (ADR-143). As propostas, as canceladas e as desfeitas não mudam nada."""
    que_mudam = []
    for correcao in listar(conexao, processamento_id):
        if correcao.status in ("APLICADA", EM_BRANCO_PELO_SISTEMA):
            que_mudam.append(correcao)
    return que_mudam


def dados_atuais(conexao, processamento_id: str) -> normalizador.Normalizacao:
    """Os dados como estão agora: a padronização com as correções aplicadas e os brancos do sistema (ADR-143)."""
    padronizacao = normalizador.obter(conexao, processamento_id)
    if padronizacao is None:
        raise ValueError("O arquivo ainda não foi padronizado.")
    return aplicar_sobre(padronizacao, _correcoes_que_mudam_o_dado(conexao, processamento_id))


def deixar_em_branco_pelo_sistema(conexao, processamento_id: str, empresa_id: str, valores: list[dict]) -> int:
    """Grava o branco do sistema de cada valor inválido de um campo opcional (ADR-143). Devolve quantos gravou.

    Recebe: o envio, a empresa e os valores [{linha, campo, antes, motivo}], que o Validador aponta
    (validador.REGRAS_DE_VALOR_INVALIDO num campo opcional).
    Faz: cada valor vira uma correção EM_BRANCO_PELO_SISTEMA, com o antes (o valor que veio), o depois vazio, o motivo
    e quem fez ("sistema (ADR-143)"); nenhum valor padrão entra no lugar. A célula apontada por duas regras ganha um
    branco só. Não repete de uma validação para a outra: depois do branco, a célula está vazia e nenhuma regra a aponta
    de novo; se o valor inválido voltar (a empresa o escreveu de novo), é um branco novo, depois da correção dela.
    A trilha registra só os campos e as quantidades, sem nenhum valor da pessoa.
    Ex.: [{linha: 5, campo: "cep_residencial", antes: "7", motivo: "Campo opcional com valor inválido: ..."}] → 1.
    """
    _preparar(conexao)
    # A hora em segundos, como a das correções de um clique: no mesmo segundo, vale a ordem em que foram gravadas
    agora = _agora()
    celulas_ja_em_branco = set()
    quantidade_por_campo = {}
    for valor in valores:
        celula = (valor["linha"], valor["campo"])
        # A mesma célula apontada por outra regra nesta validação: um branco só
        if celula in celulas_ja_em_branco:
            continue
        celulas_ja_em_branco.add(celula)
        correcao = Correcao(uuid.uuid4().hex[:10], processamento_id, valor["linha"], valor["campo"], valor["antes"],
                            None, valor["motivo"], EM_BRANCO_PELO_SISTEMA, SISTEMA, agora, SISTEMA, agora)
        conexao.execute("INSERT INTO correcoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        tuple(vars(correcao).values()))
        # Quantos brancos em cada campo, para a trilha
        quantidade_por_campo[valor["campo"]] = quantidade_por_campo.get(valor["campo"], 0) + 1
    # Nenhum valor inválido: nada a gravar nem a registrar
    if not celulas_ja_em_branco:
        return 0
    conexao.commit()
    # Sem os valores: nada pessoal na trilha
    auditoria.registrar(conexao, processamento_id, empresa_id, "Validação", "VALOR_INVALIDO_EM_BRANCO",
                        {"campos": quantidade_por_campo})
    return len(celulas_ja_em_branco)


def _registro_da_linha(registros: list[dict], linha: int) -> dict | None:
    """O registro de uma linha do arquivo, ou None se ela não existe (ou foi excluída)."""
    for registro in registros:
        if registro["_linha"] == linha:
            return registro
    return None


def propor(conexao, processamento_id: str, empresa_id: str, linha: int, campo: str, novo_valor: str | None,
           motivo: str, proposta_por: str) -> Correcao:
    """Registra o pedido. O valor novo é padronizado agora; se não der, o pedido é recusado com o motivo."""
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    if not motivo.strip():
        raise ValueError("Toda correção precisa de um motivo.")
    registro = _registro_da_linha(dados_atuais(conexao, processamento_id).registros, linha)
    if registro is None:
        raise ValueError(f"A linha {linha} não existe no arquivo (ou já foi excluída).")
    if campo == EXCLUIR:
        antes, depois = "registro", None
    else:
        _, campos = parametros.layout_ativo(conexao)
        campo_do_layout = None
        for campo_existente in campos:
            if campo_existente.campo == campo:
                campo_do_layout = campo_existente
        if campo_do_layout is None:
            raise ValueError(f"O campo {campo!r} não existe no layout.")
        antes = registro.get(campo)
        # Valor vazio apaga o campo; os outros passam pelas regras do Normalizador (NaoConvertido se não der)
        if novo_valor in (None, ""):
            depois = None
        else:
            depois = normalizador.converter_valor(novo_valor, campo_do_layout)
    correcao = Correcao(uuid.uuid4().hex[:10], processamento_id, linha, campo, antes, depois, motivo.strip(),
                        "PROPOSTA", proposta_por, _agora())
    conexao.execute("INSERT INTO correcoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(vars(correcao).values()))
    conexao.commit()
    return correcao


def _campo_do_layout(conexao, campo: str):
    """O campo do layout ativo com este nome (as regras de conversão dependem do tipo dele).

    Levanta ValueError se o campo não existe no layout. Ex.: "estado_civil" → o CampoLayout do estado civil.
    """
    for campo_existente in parametros.layout_ativo(conexao)[1]:
        if campo_existente.campo == campo:
            return campo_existente
    raise ValueError(f"O campo {campo!r} não existe no layout.")


def preencher_para_todos(conexao, processamento_id: str, empresa_id: str, campo: str, novo_valor: str, motivo: str,
                         usuario: str) -> list[str]:
    """Preenche um campo com o mesmo valor em todos os funcionários do envio que estão SEM ele.

    Para que serve: um campo obrigatório que o documento não traz (ex.: o CNPJ num Word em texto corrido, ou a
    unidade, igual para todos) vira uma pendência só; a empresa digita o valor uma vez.
    Recebe: o envio, a empresa, o campo do layout, o valor (digitado do jeito brasileiro), o motivo e quem clicou.
    Devolve: os identificadores das correções criadas, uma por funcionário preenchido (o primeiro identifica o lote
    no "Desfazer", ver desfazer_lote). Levanta KeyError (envio de outra empresa) ou ValueError (campo fora do layout,
    valor que não pode ser padronizado, sem motivo ou ninguém sem o campo).
    Regras: quem já tem o campo NÃO muda (o valor do documento continua valendo, decisão 6); cada funcionário
    preenchido vira uma correção APLICADA, com quem pediu e aprovou (o clique é a decisão humana, ADR-16); o envio é
    validado de novo uma vez só, no fim.
    """
    from services import validador
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    if not motivo.strip():
        raise ValueError("Toda correção precisa de um motivo.")
    if novo_valor in (None, "") or not str(novo_valor).strip():
        raise ValueError("Digite o valor para preencher.")
    campo_do_layout = _campo_do_layout(conexao, campo)
    # Só um dado da empresa pode ser o mesmo para todos: a informação do titular é de cada pessoa (a marcação
    # "Pode ser igual para todos" do parâmetro)
    if not parametros.pode_ser_igual_para_todos(campo_do_layout):
        nome = campo_do_layout.descricao or campo
        raise ValueError(f'A informação "{nome}" é única por funcionário e não pode ser a mesma para todos. Informe '
                         "pessoa a pessoa ou envie o arquivo de novo com essa coluna.")
    # O valor passa uma vez pelas regras do Normalizador (NaoConvertido, que é um ValueError, se não der)
    depois = normalizador.converter_valor(novo_valor, campo_do_layout)
    # Só os funcionários sem o campo
    linhas_sem_o_campo = []
    for registro in dados_atuais(conexao, processamento_id).registros:
        if registro.get(campo) in (None, ""):
            linhas_sem_o_campo.append(registro["_linha"])
    if not linhas_sem_o_campo:
        raise ValueError("Nenhum funcionário deste envio está sem este dado.")
    agora = _agora_do_lote()
    # Uma correção por funcionário, já aplicada (o clique em "Preencher para todos" é a decisão)
    identificadores = []
    for linha in linhas_sem_o_campo:
        correcao = Correcao(uuid.uuid4().hex[:10], processamento_id, linha, campo, None, depois, motivo.strip(),
                            "APLICADA", usuario, agora, usuario, agora)
        conexao.execute("INSERT INTO correcoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        tuple(vars(correcao).values()))
        identificadores.append(correcao.correcao_id)
    conexao.commit()
    # Sem o valor: nada pessoal na trilha
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "CORRECAO_PARA_TODOS",
                        {"campo": campo, "quantidade": len(linhas_sem_o_campo)})
    # Depois de mudar o dado, a revalidação é obrigatória (uma vez, para todas as linhas)
    validador.executar(conexao, processamento_id, empresa_id)
    return identificadores


def trocar_em_varias_linhas(conexao, processamento_id: str, empresa_id: str, linhas: list[int], campo: str,
                            novo_valor: str, motivo: str, usuario: str) -> list[str]:
    """Troca o valor de um campo em várias pessoas do envio de uma vez (pendências em grupo, ADR-120).

    Para que serve: 23 pessoas vieram com "Divorciado(a)" no estado civil; a empresa responde uma vez ("Sim, use
    Divorciado para as 23") e as 23 trocas são feitas juntas.
    Recebe: o envio, a empresa, as linhas do grupo (montadas no servidor, a partir do relatório do Validador), o
    campo, o valor novo (do jeito brasileiro), o motivo e quem pediu.
    Devolve: os identificadores das correções, uma por pessoa (o primeiro identifica o lote no "Desfazer", ver
    desfazer_lote). Levanta KeyError (envio de outra empresa) ou ValueError (sem motivo, sem valor, campo fora do
    layout, valor que não pode ser padronizado, ou nenhuma das linhas ainda no envio).
    Regras: cada troca vira uma correção APLICADA, com quem pediu, o antes e o depois (a mensagem da empresa é a
    decisão, ADR-118); todas com a mesma hora, o que as liga como um lote; o envio é validado de novo uma vez só.
    """
    from services import validador
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    if not motivo.strip():
        raise ValueError("Toda correção precisa de um motivo.")
    if novo_valor in (None, "") or not str(novo_valor).strip():
        raise ValueError("Diga o valor certo para usar em todas.")
    # O valor passa uma vez pelas regras do Normalizador (NaoConvertido, que é um ValueError, se não der)
    depois = normalizador.converter_valor(novo_valor, _campo_do_layout(conexao, campo))
    # Os dados como estão agora (para guardar o "antes" de cada pessoa)
    registros = dados_atuais(conexao, processamento_id).registros
    agora = _agora_do_lote()
    identificadores = []
    for linha in linhas:
        registro = _registro_da_linha(registros, linha)
        # A pessoa saiu do envio (ex.: "não cadastrar" confirmado em outra aba): fica de fora
        if registro is None:
            continue
        correcao = Correcao(uuid.uuid4().hex[:10], processamento_id, linha, campo, registro.get(campo), depois,
                            motivo.strip(), "APLICADA", usuario, agora, usuario, agora)
        conexao.execute("INSERT INTO correcoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        tuple(vars(correcao).values()))
        identificadores.append(correcao.correcao_id)
    if not identificadores:
        raise ValueError("Nenhuma dessas pessoas está mais no envio. Atualize a página.")
    conexao.commit()
    # Sem os valores: nada pessoal na trilha
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "CORRECAO_EM_GRUPO",
                        {"campo": campo, "quantidade": len(identificadores)})
    # Depois de mudar o dado, a revalidação é obrigatória (uma vez, para todas as linhas)
    validador.executar(conexao, processamento_id, empresa_id)
    return identificadores


def _valores_convertidos_por_linha(registros: list[dict], campo_do_layout, valores_por_linha: dict[int, str]) -> dict:
    """Confere e padroniza o valor de cada pessoa: {linha: valor já padronizado}.

    Recebe: os dados atuais do envio; o campo do layout; {linha: valor digitado} (só os preenchidos).
    Levanta ValueError com TODOS os problemas de uma vez, um por linha (ex.: 'Linha 8 (Ana Lima): o valor não é uma
    data válida.'), para a empresa arrumar tudo antes de salvar: nada é gravado pela metade.
    """
    convertidos = {}
    problemas = []
    for linha, valor in valores_por_linha.items():
        registro = _registro_da_linha(registros, linha)
        # A pessoa saiu do envio (ex.: "não cadastrar" confirmado em outra aba) ou a linha não existe
        if registro is None:
            problemas.append(f"Linha {linha}: esta pessoa não está mais no envio. Atualize a página.")
            continue
        # O valor passa pelas regras do Normalizador, como qualquer correção
        try:
            convertidos[linha] = normalizador.converter_valor(valor, campo_do_layout)
        except normalizador.NaoConvertido as erro:
            nome = registro.get("nome_completo") or "sem nome"
            problemas.append(f"Linha {linha} ({nome}): {erro}.")
    if problemas:
        raise ValueError(" ".join(problemas))
    return convertidos


def informar_por_pessoa(conexao, processamento_id: str, empresa_id: str, campo: str, valores_por_linha: dict[int, str],
                        motivo: str, usuario: str) -> list[str]:
    """Grava o valor de um campo que o arquivo inteiro não trouxe, pessoa a pessoa (ADR-124, alternativa B).

    Para que serve: quando a informação não é a mesma para todos (ex.: o código da
    unidade, com funcionários em duas unidades) ou é de cada pessoa (ex.: o CPF numa inclusão de 5 pessoas), a
    empresa informa o valor de cada funcionário numa lista, sem precisar mandar o arquivo de novo.
    Recebe: o envio, a empresa, o campo do layout, {linha: valor digitado} (a linha do arquivo é a chave da pessoa,
    não o CPF), o motivo e quem salvou.
    Devolve: os identificadores das correções, uma por pessoa (o primeiro identifica o lote no "Desfazer", ver
    desfazer_lote). Levanta KeyError (envio de outra empresa) ou ValueError (sem motivo, nenhum valor, campo fora do
    layout, pessoa que saiu do envio ou valor que não pode ser padronizado; a mensagem lista cada linha).
    Regras: cada valor vira uma correção APLICADA, com quem salvou, o antes e o depois (salvar é a decisão, ADR-16);
    todas com a mesma hora, o que as liga como um lote; quem ficou sem valor não muda (e ganha um cartão de revisão
    depois da revalidação); o envio é validado de novo uma vez só.
    """
    from services import validador
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    if not motivo.strip():
        raise ValueError("Toda correção precisa de um motivo.")
    # Só os valores preenchidos contam (quem ficou em branco continua sem o dado)
    preenchidos = {}
    for linha, valor in valores_por_linha.items():
        if valor is not None and str(valor).strip():
            preenchidos[linha] = str(valor).strip()
    if not preenchidos:
        raise ValueError("Preencha o valor de pelo menos uma pessoa.")
    campo_do_layout = _campo_do_layout(conexao, campo)
    # Os dados como estão agora (para achar cada pessoa e guardar o "antes")
    registros = dados_atuais(conexao, processamento_id).registros
    convertidos = _valores_convertidos_por_linha(registros, campo_do_layout, preenchidos)
    agora = _agora_do_lote()
    # Uma correção por pessoa, já aplicada (o clique em "Salvar" é a decisão), na ordem das linhas do arquivo
    identificadores = []
    for linha in sorted(convertidos):
        registro = _registro_da_linha(registros, linha)
        correcao = Correcao(uuid.uuid4().hex[:10], processamento_id, linha, campo, registro.get(campo),
                            convertidos[linha], motivo.strip(), "APLICADA", usuario, agora, usuario, agora)
        conexao.execute("INSERT INTO correcoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        tuple(vars(correcao).values()))
        identificadores.append(correcao.correcao_id)
    conexao.commit()
    # Sem os valores: nada pessoal na trilha
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "CORRECAO_POR_PESSOA",
                        {"campo": campo, "quantidade": len(identificadores)})
    # Depois de mudar o dado, a revalidação é obrigatória (uma vez, para todas as linhas)
    validador.executar(conexao, processamento_id, empresa_id)
    return identificadores


def decidir(conexao, processamento_id: str, empresa_id: str, correcao_id: str, aplicar: bool, usuario: str) -> Correcao:
    """O clique: aplica (e revalida) ou cancela. Só pedidos ainda PROPOSTA podem ser decididos."""
    from services import validador
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    correcao = None
    for correcao_existente in listar(conexao, processamento_id):
        if correcao_existente.correcao_id == correcao_id:
            correcao = correcao_existente
    if correcao is None or correcao.status != "PROPOSTA":
        raise ValueError("Esta correção não está mais aguardando decisão.")
    status = "APLICADA" if aplicar else "CANCELADA"
    conexao.execute("UPDATE correcoes SET status = ?, aprovada_por = ?, decidido_em = ? WHERE correcao_id = ?",
                    (status, usuario, _agora(), correcao_id))
    conexao.commit()
    # Sem os valores: nada pessoal no painel
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", f"CORRECAO_{status}",
                        {"linha": correcao.linha, "campo": correcao.campo})
    if aplicar:
        # Alerta resolvido por correção vira rótulo "erro corrigido" (ADR-14)
        relatorio = validador.obter(conexao, processamento_id)
        if relatorio is not None:
            for achado in relatorio.achados:
                mesma_celula = achado.linha == correcao.linha and achado.campo == correcao.campo
                if achado.severidade == validador.ALERTA and mesma_celula:
                    validador.registrar_resolucao(conexao, processamento_id, achado.regra_id, achado.linha,
                                                  "ERRO_CORRIGIDO", correcao.motivo, usuario)
        # Depois de mudar o dado, a revalidação é obrigatória
        validador.executar(conexao, processamento_id, empresa_id)
    return replace(correcao, status=status, aprovada_por=usuario)


# ---------------- Desfazer (pendências por conversa) ----------------

# O status da correção que foi aplicada e depois desfeita pela empresa: dados_atuais só usa as APLICADAS, então ela
# deixa de valer, mas continua guardada (quem pediu, quem desfez, antes e depois)
DESFEITA = "DESFEITA"


def correcao_pelo_id(conexao, processamento_id: str, correcao_id: str) -> Correcao | None:
    """A correção do envio com este identificador, ou None se não existe."""
    for correcao in listar(conexao, processamento_id):
        if correcao.correcao_id == correcao_id:
            return correcao
    return None


def _mudou_depois(conexao, processamento_id: str, correcao: Correcao) -> bool:
    """True se a mesma célula (linha e campo) recebeu outra correção APLICADA depois desta.

    Por quê: desfazer uma troca antiga por cima de uma mais nova apagaria o que a empresa fez depois.
    """
    # listar devolve em ordem de pedido: tudo o que vem depois desta correção é mais novo
    depois_desta = False
    for outra in listar(conexao, processamento_id, "APLICADA"):
        if outra.correcao_id == correcao.correcao_id:
            depois_desta = True
            continue
        if depois_desta and outra.linha == correcao.linha and outra.campo == correcao.campo:
            return True
    return False


def _marcar_desfeitas(conexao, correcoes_a_desfazer: list[Correcao], usuario: str) -> None:
    """Troca o status das correções para DESFEITA, com quem desfez e quando (não faz commit)."""
    agora = _agora()
    for correcao in correcoes_a_desfazer:
        conexao.execute("UPDATE correcoes SET status = ?, aprovada_por = ?, decidido_em = ? WHERE correcao_id = ?",
                        (DESFEITA, usuario, agora, correcao.correcao_id))


def desfazer(conexao, processamento_id: str, empresa_id: str, correcao_id: str, usuario: str) -> Correcao:
    """Desfaz uma correção aplicada (troca de valor ou "não cadastrar"): o dado volta ao que era e o envio é validado
    de novo (a pendência volta a aparecer, se for o caso).

    Recebe: o envio, a empresa (da sessão), a correção e quem pediu para desfazer.
    Devolve: a correção como estava antes de desfazer (com o antes e o depois, para a tela dizer o que voltou).
    Levanta KeyError (envio de outra empresa) ou ValueError (correção que não existe, que não está aplicada ou cuja
    célula mudou de novo depois).
    """
    from services import validador
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    correcao = correcao_pelo_id(conexao, processamento_id, correcao_id)
    if correcao is None or correcao.status != "APLICADA":
        raise ValueError("Esta troca não está mais valendo: não há o que desfazer.")
    if _mudou_depois(conexao, processamento_id, correcao):
        raise ValueError("Este dado mudou de novo depois desta troca: não dá para desfazer esta.")
    _marcar_desfeitas(conexao, [correcao], usuario)
    conexao.commit()
    # Sem os valores: nada pessoal na trilha
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", "CORRECAO_DESFEITA",
                        {"linha": correcao.linha, "campo": correcao.campo})
    # O dado mudou: a revalidação é obrigatória
    validador.executar(conexao, processamento_id, empresa_id)
    return correcao


def desfazer_lote(conexao, processamento_id: str, empresa_id: str, primeira_correcao_id: str, usuario: str,
                  evento: str = "CORRECAO_PARA_TODOS_DESFEITA") -> int:
    """Desfaz um lote inteiro: um "Preencher para todos" (volta ao vazio) ou uma troca em grupo (ADR-120; volta ao
    valor de antes, e a pendência de cada pessoa reaparece).

    Recebe: o envio, a empresa (da sessão), a primeira correção do lote (preencher_para_todos e
    trocar_em_varias_linhas devolvem os identificadores), quem pediu e o nome do evento na trilha. O lote são as
    correções APLICADAS do mesmo campo, criadas no mesmo instante, pela mesma pessoa e com o mesmo motivo.
    Devolve: quantos funcionários voltaram ao que eram. Levanta KeyError (outra empresa) ou ValueError (lote que não
    existe, já desfeito, ou com alguma célula mudada de novo depois).
    """
    from services import validador
    _preparar(conexao)
    if processamentos.obter_da_empresa(conexao, processamento_id, empresa_id) is None:
        raise KeyError(processamento_id)
    primeira = correcao_pelo_id(conexao, processamento_id, primeira_correcao_id)
    if primeira is None or primeira.status != "APLICADA":
        raise ValueError("Este preenchimento não está mais valendo: não há o que desfazer.")
    # As correções do mesmo lote
    do_lote = []
    for correcao in listar(conexao, processamento_id, "APLICADA"):
        mesmo_lote = (correcao.campo == primeira.campo and correcao.criado_em == primeira.criado_em
                      and correcao.proposta_por == primeira.proposta_por and correcao.motivo == primeira.motivo)
        if mesmo_lote:
            do_lote.append(correcao)
    # Nenhuma célula do lote pode ter mudado depois
    for correcao in do_lote:
        if _mudou_depois(conexao, processamento_id, correcao):
            raise ValueError("Algum desses dados mudou de novo depois: não dá para desfazer o preenchimento.")
    _marcar_desfeitas(conexao, do_lote, usuario)
    conexao.commit()
    # Sem os valores: nada pessoal na trilha
    auditoria.registrar(conexao, processamento_id, empresa_id, "Correção", evento,
                        {"campo": primeira.campo, "quantidade": len(do_lote)})
    validador.executar(conexao, processamento_id, empresa_id)
    return len(do_lote)
