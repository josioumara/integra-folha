/*
  cadastrar_conferencia_real.js — na tela "Cadastrar funcionários", com a aplicação: o formato das colunas, a
  conferência da lista e o "Ajude a IA a acertar" (ADR-69, passo 17).

  Para que serve: depois que a empresa aceita as colunas, o fluxo padroniza e valida. Antes de enviar ao banco:
    1. formato de coluna: quando uma coluna inteira tem dúvida (datas dia/mês ou mês/dia; quantos dígitos a matrícula
       tem), a empresa escolhe e a aplicação padroniza de novo;
    2. conferência da lista: a lista do jeito que vai para o banco, com as colunas dos campos obrigatórios do parâmetro
       (ADR-143: a empresa confirma só os obrigatórios; o clique na pessoa mostra todos os campos dela) e "Corrigir" em
       cada linha (a correção fica registrada com quem corrigiu, é aplicada e o envio é validado de novo). Embaixo de
       cada pessoa com pendência, o que falta, o valor que o arquivo trouxe e a conversa com a IA, que resolve a
       pendência (js/assistente_de_correcao.js). Contadores e o filtro "só quem tem
       pendência" deixam a lista usável com milhares de funcionários;
    3. "Ajude a IA a acertar": a empresa escolhe uma ou mais colunas (até 5) e conta o que cada uma contém; a IA relê
       SÓ essas colunas e elas voltam para o aceite (tudo conta como uma releitura; no máximo 2 por envio; cada dica
       passa pelo guardrail de injeção);
    4. "Conferi a lista": sem marcar, o botão "Enviar ao banco" fica desligado; marcado, fica registrado e o banco vê.
  Usa do js/cadastrar_real.js: envio_de_verdade, pedir_a_api, mostrar_resultado_real, mostrar_erro_real,
  texto_do_erro, criar_elemento_real, nome_de_origem, ligar_cronometro e parar_cronometro. Do js/grade_do_parametro.js:
  colunas_obrigatorias, celula_do_cabecalho, celula_do_valor, abrir_o_detalhe_ao_clicar_na_linha e TEXTO_SEM_VALOR.
  Do js/cadastrar_obrigatorios.js: colunas_do_parametro_no_cadastro.
*/

// Quantas linhas a conferência mostra de cada vez.
const LINHAS_POR_VEZ = 20;
// As colunas da lista (sem rolar para o lado): a linha do arquivo, os campos
// OBRIGATÓRIOS do parâmetro vigente (ADR-143: a empresa confirma só os obrigatórios),
// a situação e as ações. Os demais campos aparecem na ficha da pessoa, aberta em "Ver todos os dados" ou no clique na
// linha, em grade que se ajusta à largura da tela.
const COLUNAS_ANTES_DOS_CAMPOS = ["Linha"];
const COLUNAS_DEPOIS_DOS_CAMPOS = ["Situação", ""];
// O campo que dá o nome da pessoa nos cartões das pendências (o nome técnico do layout).
const CAMPO_DO_NOME = "nome_completo";
// As etapas em que a lista já foi padronizada e ainda não foi para o banco.
const ETAPAS_DA_CONFERENCIA_REAL = ["aguardar_correcao", "aprovar_homologacao"];

// Quantas colunas a empresa pode explicar numa releitura (o mesmo limite de services/cadastro.py).
const MAXIMO_DE_COLUNAS_POR_RELEITURA = 5;
// As colunas que podem ser relidas (as da última leitura), para montar cada linha do "Ajude a IA a acertar".
let colunas_para_reler = [];

// O que a conferência está mostrando: a lista vinda da aplicação, quantas linhas aparecem, o filtro e as colunas dos
// campos obrigatórios ({campo, rotulo, tipo, obrigatorio, descricao}, na ordem do layout).
const estado_da_conferencia = {
  lista: null, quantas_mostrar: LINHAS_POR_VEZ, so_pendencias: true, colunas_da_lista: [],
};

// ===== Mostrar as partes conforme a etapa =====

/**
 * Mostra só as partes que fazem sentido na etapa do fluxo. Chamada a cada leitura nova (js/cadastrar_real.js).
 *
 * Recebe: leitura — o que o servidor devolveu. Devolve: nada.
 */
function mostrar_partes_da_conferencia(leitura) {
  const na_conferencia = ETAPAS_DA_CONFERENCIA_REAL.includes(leitura.etapa);
  // Formato de coluna: só quando há dúvida.
  mostrar_formatos_pendentes(leitura.formatos_pendentes || []);
  // Conferência e "Conferi a lista": entre a padronização e o envio ao banco.
  const bloco_da_conferencia = document.querySelector("[data-real-bloco-conferencia]");
  bloco_da_conferencia.hidden = !na_conferencia;
  document.querySelector("[data-real-conferi]").hidden = leitura.etapa !== "aprovar_homologacao";
  // Uma leitura nova invalida a lista mostrada: é buscada de novo quando a pessoa abrir.
  estado_da_conferencia.lista = null;
  // Com pendências a resolver, a conferência já vem aberta (é ali que se resolve).
  if (na_conferencia && leitura.etapa === "aguardar_correcao") {
    bloco_da_conferencia.open = true;
  }
  if (na_conferencia && bloco_da_conferencia.open) {
    carregar_lista_para_conferir();
  }
  // "Ajude a IA a acertar": do aceite até o envio ao banco.
  const pode_reler = leitura.etapa === "aprovar_mapeamento" || na_conferencia;
  document.querySelector("[data-real-bloco-ajude]").hidden = !pode_reler;
  montar_colunas_para_reler(leitura.colunas || []);
  atualizar_botao_de_envio();
}

/**
 * Liga o "Enviar ao banco" só depois de marcar "Conferi a lista".
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_botao_de_envio() {
  const caixa = document.querySelector("[data-real-conferi-caixa]");
  document.querySelector("[data-real-homologar]").disabled = !caixa.checked;
}

// ===== 1. Formato de coluna =====

/**
 * Monta a escolha do formato de cada coluna com dúvida.
 *
 * Recebe: pendentes — [{coluna, tipo, mensagem}]. Devolve: nada.
 */
function mostrar_formatos_pendentes(pendentes) {
  const bloco = document.querySelector("[data-real-bloco-formatos]");
  const lista = document.querySelector("[data-real-lista-formatos]");
  lista.replaceChildren();
  bloco.hidden = pendentes.length === 0;
  for (const pendente of pendentes) {
    const item = criar_elemento_real("div", "ajuste", "");
    item.append(criar_elemento_real("p", "ajuste-titulo", "Coluna \"" + pendente.coluna + "\""),
      criar_elemento_real("p", "ajuste-problema", pendente.mensagem));
    const botoes = criar_elemento_real("div", "ajuste-botoes", "");
    if (pendente.tipo === "DATA_AMBIGUA") {
      botoes.append(botao_de_formato(pendente.coluna, "DMY", "Dia/mês (DD/MM/AAAA)", null),
        botao_de_formato(pendente.coluna, "MDY", "Mês/dia (MM/DD/AAAA)", null));
    } else {
      const digitos = criar_elemento_real("input", "campo-entrada campo-pequeno", "");
      digitos.type = "number";
      digitos.min = "1";
      digitos.max = "20";
      digitos.placeholder = "Quantos dígitos? (ex.: 5)";
      digitos.setAttribute("aria-label", "Quantos dígitos a matrícula tem");
      botoes.append(digitos, botao_de_formato(pendente.coluna, null, "Usar este número de dígitos", digitos));
    }
    item.append(botoes);
    lista.append(item);
  }
}

/**
 * Cria um botão que manda a decisão de formato de uma coluna.
 *
 * Recebe: coluna; decisao ("DMY"/"MDY", ou null quando vem dos dígitos); texto; campo_de_digitos (ou null).
 * Devolve: o botão.
 */
function botao_de_formato(coluna, decisao, texto, campo_de_digitos) {
  const botao = criar_elemento_real("button", "botao botao-contorno botao-pequeno", texto);
  botao.type = "button";
  botao.addEventListener("click", async function () {
    let decisao_final = decisao;
    if (campo_de_digitos) {
      decisao_final = "zeros:" + campo_de_digitos.value;
    }
    botao.disabled = true;
    const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/formato", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coluna: coluna, decisao: decisao_final }),
    });
    botao.disabled = false;
    if (!resposta.ok) {
      mostrar_erro_real(texto_do_erro(resposta.dados.detail));
      return;
    }
    envio_de_verdade.leitura = resposta.dados;
    mostrar_resultado_real(resposta.dados);
  });
  return botao;
}

// ===== 2. Conferência da lista =====

/**
 * Busca a lista do jeito que vai para o banco e desenha a tabela.
 *
 * Recebe: nada. Devolve: nada.
 */
async function carregar_lista_para_conferir() {
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/lista", {});
  if (!resposta.ok) {
    mostrar_erro_da_conferencia(texto_do_erro(resposta.dados.detail));
    return;
  }
  // As colunas da lista: os campos obrigatórios do parâmetro vigente (js/cadastrar_obrigatorios.js; ADR-143)
  const colunas_do_parametro = await colunas_do_parametro_no_cadastro();
  estado_da_conferencia.colunas_da_lista = colunas_obrigatorias_da_lista(resposta.dados, colunas_do_parametro);
  estado_da_conferencia.lista = resposta.dados;
  desenhar_lista_para_conferir();
}

/**
 * As colunas dos campos obrigatórios na lista da conferência: as do parâmetro vigente (com o nome e o tipo de cada
 * campo, como na grade de funcionários). Se o parâmetro não respondeu, as obrigatórias que a própria lista marca, com
 * o nome técnico em palavras. Nos dois casos, a escolha vem da marca "obrigatório" do parâmetro, nunca de uma lista
 * escrita aqui.
 *
 * Recebe: lista — a da conferência (campos: [{campo, descricao, obrigatorio, ...}]); colunas_do_parametro — as da
 * consulta (vazia sem resposta). Devolve: [{campo, rotulo, tipo, obrigatorio, descricao}].
 */
function colunas_obrigatorias_da_lista(lista, colunas_do_parametro) {
  const do_parametro = colunas_obrigatorias(colunas_do_parametro);
  if (do_parametro.length > 0) {
    return do_parametro;
  }
  // Sem o parâmetro: as marcadas na lista, com o valor mostrado como veio (tipo texto)
  const da_lista = [];
  for (const campo of lista.campos) {
    if (campo.obrigatorio) {
      da_lista.push({ campo: campo.campo, rotulo: rotulo_do_campo(campo.campo), tipo: "TEXTO", obrigatorio: true,
        descricao: campo.descricao || "" });
    }
  }
  return da_lista;
}

/**
 * Quantas colunas a lista da conferência tem agora: a linha, uma por campo obrigatório, a situação e as ações.
 * As linhas que ocupam a largura inteira (as pendências, a ficha e a correção de uma pessoa) usam este número.
 *
 * Recebe: nada. Devolve: o número. Ex.: com os 4 obrigatórios de hoje, 1 + 4 + 2 = 7.
 */
function quantas_colunas_na_lista() {
  return COLUNAS_ANTES_DOS_CAMPOS.length + estado_da_conferencia.colunas_da_lista.length +
    COLUNAS_DEPOIS_DOS_CAMPOS.length;
}

/**
 * Mostra (ou esconde) a mensagem de erro da conferência.
 *
 * Recebe: texto — a mensagem ("" esconde). Devolve: nada.
 */
function mostrar_erro_da_conferencia(texto) {
  const erro = document.querySelector("[data-real-erro-conferencia]");
  erro.textContent = texto;
  erro.hidden = texto === "";
}

/**
 * Transforma o nome técnico de um campo em rótulo curto ("data_admissao" → "data admissao").
 *
 * Recebe: campo. Devolve: o rótulo.
 */
function rotulo_do_campo(campo) {
  return campo.split("_").join(" ");
}

/**
 * Desenha a lista da conferência: uma linha curta por pessoa (a linha do arquivo, os campos obrigatórios, a situação e
 * as ações). Os demais campos ficam na ficha da pessoa ("Ver todos os dados"), para a tabela nunca precisar rolar para
 * o lado.
 *
 * Recebe: nada (usa estado_da_conferencia). Devolve: nada.
 */
function desenhar_lista_para_conferir() {
  const lista = estado_da_conferencia.lista;
  // O cabeçalho: a linha, os campos obrigatórios do parâmetro (com a marca "*" e a descrição do banco ao passar o
  // mouse, como na grade de funcionários), a situação e as ações.
  const cabecalho = criar_elemento_real("tr", "", "");
  for (const titulo of COLUNAS_ANTES_DOS_CAMPOS) {
    cabecalho.append(criar_elemento_real("th", "", titulo));
  }
  for (const coluna of estado_da_conferencia.colunas_da_lista) {
    cabecalho.append(celula_do_cabecalho(coluna));
  }
  for (const titulo of COLUNAS_DEPOIS_DOS_CAMPOS) {
    cabecalho.append(criar_elemento_real("th", "", titulo));
  }
  document.querySelector("[data-real-cabeca-conferencia]").replaceChildren(cabecalho);
  // Os contadores, sempre do envio inteiro.
  mostrar_contadores_da_conferencia(lista.contagem);
  // Quem não vai por este envio (já foi ao banco ou já está cadastrado), e por quê
  mostrar_quem_fica_de_fora_na_conferencia(lista.ficam_de_fora);
  // O que a IA resolveu há pouco e saiu da lista, com o Desfazer
  mostrar_resolvidos_agora_na_conferencia(lista);
  // As linhas do filtro ("só quem tem pendência" ou todas), de LINHAS_POR_VEZ em LINHAS_POR_VEZ.
  const linhas_do_filtro = linhas_filtradas(lista);
  const corpo = document.querySelector("[data-real-corpo-conferencia]");
  corpo.replaceChildren();
  const visiveis = linhas_do_filtro.slice(0, estado_da_conferencia.quantas_mostrar);
  for (const linha of visiveis) {
    const tr = montar_linha_para_conferir(lista, linha);
    corpo.append(tr);
    // Embaixo da pessoa, o que falta resolver nela.
    if (linha.pendencias.length > 0) {
      corpo.append(montar_pendencias_da_linha(lista, linha));
    }
  }
  // Filtro ligado e nada pendente: diz que está tudo resolvido.
  if (linhas_do_filtro.length === 0) {
    const vazio = criar_elemento_real("tr", "", "");
    const celula = criar_elemento_real("td", "", "Nenhuma pessoa com pendência. Desmarque o filtro para ver a lista inteira.");
    celula.colSpan = quantas_colunas_na_lista();
    vazio.append(celula);
    corpo.append(vazio);
  }
  // "Mostrar mais": quantas linhas ainda faltam aparecer no filtro atual
  const botao_de_mais = document.querySelector("[data-real-mais-linhas]");
  const faltam = linhas_do_filtro.length - estado_da_conferencia.quantas_mostrar;
  botao_de_mais.hidden = faltam <= 0;
  if (faltam > 0) {
    botao_de_mais.textContent = "Mostrar mais " + Math.min(LINHAS_POR_VEZ, faltam) + " (faltam " + faltam + ")";
  }
  mostrar_erro_da_conferencia("");
}

/**
 * As linhas que a conferência mostra: só as com pendência (filtro ligado) ou todas.
 *
 * Recebe: lista. Devolve: a lista de linhas.
 */
function linhas_filtradas(lista) {
  // O estado do filtro é lido da própria caixa (a lista pode ter sido recarregada enquanto a pessoa clicava)
  estado_da_conferencia.so_pendencias = document.querySelector("[data-real-so-pendencias]").checked;
  if (!estado_da_conferencia.so_pendencias) {
    return lista.linhas;
  }
  const com_pendencia = [];
  for (const linha of lista.linhas) {
    if (linha.pendencias.length > 0) {
      com_pendencia.push(linha);
    }
  }
  return com_pendencia;
}

/**
 * Mostra os contadores da conferência: o total para revisar (o mesmo número do painel "Linhas do arquivo" e de
 * "Acompanhar cadastros"), as pessoas, as com pendência, o que corrigir, o que confirmar, o que falta no arquivo
 * inteiro e as perguntas da IA (com milhares de funcionários, é o tamanho do trabalho em uma olhada).
 *
 * Recebe: contagem — {para_revisar, linhas, linhas_com_pendencia, corrigir, confirmar, no_arquivo, perguntas_da_ia}.
 * Devolve: nada.
 * Por que o total e o "falta no arquivo" (ADR-126): sem as informações que o arquivo inteiro não trouxe, a
 * conferência diria "0 com pendência" enquanto o painel ao lado diz "14 para revisar".
 */
function mostrar_contadores_da_conferencia(contagem) {
  const area = document.querySelector("[data-real-contadores-conferencia]");
  area.replaceChildren();
  const itens = [
    [quantidade_no_singular_ou_plural(contagem.para_revisar, "para revisar", "para revisar"), contagem.para_revisar > 0],
    [quantidade_no_singular_ou_plural(contagem.linhas, "pessoa na lista", "pessoas na lista"), false],
    [quantidade_no_singular_ou_plural(contagem.linhas_com_pendencia, "pessoa com pendência", "pessoas com pendência"),
      contagem.linhas_com_pendencia > 0],
    [contagem.corrigir + " para corrigir", contagem.corrigir > 0],
    [contagem.confirmar + " para confirmar", false],
    [quantidade_no_singular_ou_plural(contagem.no_arquivo, "informação falta no arquivo",
      "informações faltam no arquivo"), contagem.no_arquivo > 0],
    [quantidade_no_singular_ou_plural(contagem.perguntas_da_ia, "pergunta dos agentes", "perguntas dos agentes"), false],
  ];
  for (const [texto, chama_atencao] of itens) {
    let classe = "contador-conferencia";
    if (chama_atencao) {
      classe = "contador-conferencia contador-atencao";
    }
    area.append(criar_elemento_real("span", classe, texto));
  }
  // O que falta no arquivo inteiro não é de uma pessoa: o cartão dele fica em "Acompanhar cadastros"
  const aviso = document.querySelector("[data-real-aviso-no-arquivo]");
  aviso.hidden = contagem.no_arquivo === 0;
  if (contagem.no_arquivo === 1) {
    aviso.textContent = "Falta 1 informação no arquivo inteiro (vale para todas as pessoas). Ela se resolve em " +
      "\"Acompanhar cadastros\", num cartão só.";
  } else {
    aviso.textContent = "Faltam " + contagem.no_arquivo + " informações no arquivo inteiro (valem para todas as " +
      "pessoas). Elas se resolvem em \"Acompanhar cadastros\", um cartão para cada uma.";
  }
}

/**
 * Mostra quem fica de fora deste envio e por quê (envio parcial, ADR-126), acima da lista.
 *
 * Recebe: pessoas — [{linha, nome, cpf, motivo}] (vazio: o bloco some). Devolve: nada.
 */
function mostrar_quem_fica_de_fora_na_conferencia(pessoas) {
  const lugar = document.querySelector("[data-real-ficam-de-fora]");
  lugar.replaceChildren();
  const bloco = montar_bloco_de_quem_fica_de_fora(pessoas);
  if (bloco) {
    lugar.append(bloco);
  }
  lugar.hidden = bloco === null;
}

/**
 * Monta a linha com as pendências de uma pessoa: cada uma no mesmo cartão-conversa de Acompanhar.
 *
 * Recebe: lista; linha — {linha, valores, pendencias}. Devolve: o <tr> das pendências.
 * A pendência se resolve conversando: o cartão tem o nome e o campo, a pergunta num
 * balão da IA, as respostas rápidas e a caixa para responder. O "Corrigir" da linha inteira continua na própria linha.
 */
function montar_pendencias_da_linha(lista, linha) {
  const tr_das_pendencias = criar_elemento_real("tr", "linha-pendencias-real", "");
  const celula = criar_elemento_real("td", "", "");
  celula.colSpan = quantas_colunas_na_lista();
  // Os campos que já têm algo para CORRIGIR: a pergunta da IA sobre o mesmo campo se resolve junto e não ganha cartão
  // (ex.: "CPF obrigatório vazio" + "o CPF dela vem depois": corrigido o CPF, as duas somem)
  const campos_a_corrigir = [];
  for (const pendencia of linha.pendencias) {
    if (pendencia.tipo === "corrigir" && pendencia.campo) {
      campos_a_corrigir.push(pendencia.campo);
    }
  }
  for (const pendencia of linha.pendencias) {
    if (pendencia.pergunta_da_ia && pendencia.campo && campos_a_corrigir.includes(pendencia.campo)) {
      continue;
    }
    celula.append(montar_item_de_pendencia(lista, linha, pendencia));
  }
  tr_das_pendencias.append(celula);
  return tr_das_pendencias;
}

/**
 * Monta uma pendência: o cartão-conversa (js/assistente_de_correcao.js), sem a linha do arquivo (a tela é de um envio).
 *
 * Recebe: lista; linha; pendencia. Devolve: o <div> da pendência.
 */
function montar_item_de_pendencia(lista, linha, pendencia) {
  const pendencia_da_conversa = pendencia_para_a_conversa(lista, linha, pendencia);
  const item = criar_elemento_real("div", "pendencia-real", "");
  item.dataset.chavePendencia = chave_da_conversa(pendencia_da_conversa);
  // Qualquer mudança feita pela conversa busca a lista e a leitura de novo
  item.append(...montar_cartao_da_pendencia(pendencia_da_conversa, atualizar_conferencia_depois_do_assistente));
  return item;
}

/**
 * A pendência no formato do cartão (js/assistente_de_correcao.js): o envio, a regra, a linha, de quem, o campo e a
 * pergunta.
 *
 * Recebe: lista; linha; pendencia. Devolve: {processamento_id, regra_id, linha, nome, nome_do_campo, pergunta,
 * problema, sugestoes, origem, grupo, titulo_do_cartao}.
 */
function pendencia_para_a_conversa(lista, linha, pendencia) {
  // O nome da pessoa, para o cartão dizer de quem é o dado
  let nome = linha.valores[CAMPO_DO_NOME] || "";
  if (!nome) {
    nome = "Pessoa da linha " + linha.linha;
  }
  let nome_do_campo = "";
  if (pendencia.campo) {
    nome_do_campo = descricao_do_campo(lista, pendencia.campo);
  }
  return {
    processamento_id: envio_de_verdade.id, regra_id: pendencia.regra_id, linha: linha.linha, nome: nome,
    nome_do_campo: nome_do_campo, pergunta: pendencia.pergunta, problema: pendencia.problema,
    sugestoes: pendencia.sugestoes || [], origem: "",
    // O pedido do especialista do banco sobre esta pessoa ganha o selo "Pedido do banco" no cartão (ADR-121)
    pedido_do_banco: Boolean(pendencia.pedido_do_banco),
    // Várias pessoas com o mesmo valor fora da lista (ADR-120): cada linha delas mostra o cartão do grupo, e a
    // resposta numa vale para todas (js/assistente_de_correcao.js)
    grupo: pendencia.grupo || null,
    // O título do cartão, pronto do servidor (ex.: 'Ajuste na informação "CPF" de Ana Lima')
    titulo_do_cartao: pendencia.titulo_do_cartao || "",
    // O problema do cartão, curto e só dele (um cartão, um problema; ADR-120)
    problema_do_cartao: pendencia.problema_do_cartao || "",
    // O campo da pendência (identifica a pendência e a conversa)
    campo: pendencia.campo || null,
    // A informação em destaque na ficha completa (null nos problemas da pessoa inteira)
    campo_em_revisao: pendencia.campo_em_revisao,
  };
}

/**
 * O nome do campo em linguagem simples: a descrição do parâmetro ou, sem ela, o nome técnico com espaços.
 *
 * Recebe: lista — com campos [{campo, descricao}]; campo. Devolve: o texto. Ex.: "cpf" → "CPF do funcionário".
 */
function descricao_do_campo(lista, campo) {
  for (const campo_da_lista of lista.campos) {
    if (campo_da_lista.campo === campo && campo_da_lista.descricao) {
      return campo_da_lista.descricao;
    }
  }
  return rotulo_do_campo(campo);
}

/**
 * Refaz os avisos "Resolvido agora" da conferência (o que a IA resolveu há pouco, com o Desfazer).
 *
 * Recebe: lista — a lista inteira (as pendências abertas de todas as linhas, mesmo as ainda não mostradas).
 * Devolve: nada.
 */
function mostrar_resolvidos_agora_na_conferencia(lista) {
  const chaves_abertas = [];
  for (const linha of lista.linhas) {
    for (const pendencia of linha.pendencias) {
      chaves_abertas.push(chave_da_conversa(pendencia_para_a_conversa(lista, linha, pendencia)));
    }
  }
  const lugar = document.querySelector("[data-real-resolvidos-agora]");
  lugar.replaceChildren(...montar_avisos_de_resolvidos_agora(chaves_abertas));
}

/**
 * Depois de uma mudança feita pela conversa com a IA (ou de um Desfazer), busca de novo a lista e a leitura do envio.
 *
 * Recebe: nada. Devolve: uma promessa. A correção revalidou o envio: as pendências e a etapa podem ter mudado.
 */
async function atualizar_conferencia_depois_do_assistente() {
  await carregar_lista_para_conferir();
  const leitura = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id), {});
  if (leitura.ok) {
    envio_de_verdade.leitura = leitura.dados;
    mostrar_resultado_real(leitura.dados);
  }
}

/**
 * Abre o balão de ajuda de um campo com os textos reais do parâmetro do layout (o mesmo balão do protótipo).
 *
 * Recebe: botao — o "i" clicado. Devolve: nada.
 * Texto vazio no parâmetro vira "—" (o banco não escreveu nada sobre aquilo).
 */
function abrir_ajuda_do_campo_real(botao) {
  let campo = null;
  for (const campo_da_lista of estado_da_conferencia.lista.campos) {
    if (campo_da_lista.campo === botao.dataset.campoReal) {
      campo = campo_da_lista;
    }
  }
  if (campo === null) {
    return;
  }
  const balao = document.querySelector("[data-balao-ajuda]");
  balao.querySelector("[data-ajuda-titulo]").textContent = rotulo_do_campo(campo.campo);
  balao.querySelector("[data-ajuda-obrigatorio]").textContent = campo.obrigatorio ? "Obrigatório" : "Opcional";
  balao.querySelector("[data-ajuda-o-que-e]").textContent = campo.descricao || "—";
  balao.querySelector("[data-ajuda-como]").textContent = campo.regra || "—";
  balao.querySelector("[data-ajuda-nao-confundir]").textContent = campo.nao_confundir_com || "—";
  // O exemplo do parâmetro do banco (sem exemplo, um traço)
  balao.querySelector("[data-ajuda-exemplo]").textContent = campo.exemplo || "—";
  balao.hidden = false;
  // Posição: logo abaixo do "i", sem passar da borda direita da tela (o mesmo cálculo do protótipo)
  const posicao_do_botao = botao.getBoundingClientRect();
  const esquerda_maxima = window.innerWidth - balao.offsetWidth - 16;
  balao.style.top = (posicao_do_botao.bottom + 8) + "px";
  balao.style.left = Math.max(16, Math.min(posicao_do_botao.left - 12, esquerda_maxima)) + "px";
}

/**
 * Monta a linha curta de uma pessoa: linha do arquivo, os campos obrigatórios, situação e as ações ("Ver todos os
 * dados" e "Corrigir"). O clique na linha abre (ou fecha) a ficha da pessoa, como o "Ver todos os dados".
 *
 * Recebe: lista; linha — {linha, valores, pendencias}. Devolve: o <tr>.
 * Ex.: "4 · 529.982.247-25 · 411010 · 05/03/2026 · R$ 2.450,00 · 1 pendência · Ver todos os dados · Corrigir".
 */
function montar_linha_para_conferir(lista, linha) {
  const tr = criar_elemento_real("tr", "", "");
  // O número da linha no arquivo, para a empresa achar a pessoa no documento dela
  tr.append(criar_elemento_real("td", "", String(linha.linha)));
  // Os campos obrigatórios do parâmetro (ADR-143): o valor que vai para o banco, ou "Informação não encontrada"
  for (const coluna of estado_da_conferencia.colunas_da_lista) {
    tr.append(celula_do_valor(coluna, linha.valores[coluna.campo]));
  }
  // A situação: quantas pendências a pessoa tem, ou "Tudo certo"
  let situacao = "Tudo certo";
  if (linha.pendencias.length === 1) {
    situacao = "1 pendência";
  }
  if (linha.pendencias.length > 1) {
    situacao = linha.pendencias.length + " pendências";
  }
  const celula_da_situacao = criar_elemento_real("td", "", "");
  let classe_da_situacao = "situacao-linha-ok";
  if (linha.pendencias.length > 0) {
    classe_da_situacao = "selo-linha-com-pendencia";
  }
  celula_da_situacao.append(criar_elemento_real("span", classe_da_situacao, situacao));
  tr.append(celula_da_situacao);
  // As ações: abrir a ficha com todos os campos e corrigir um valor
  const acao = criar_elemento_real("td", "acoes-linha-real", "");
  const ver_dados = criar_elemento_real("button", "botao-nome", "Ver todos os dados");
  ver_dados.type = "button";
  ver_dados.setAttribute("aria-expanded", "false");
  ver_dados.addEventListener("click", function () {
    alternar_ficha_da_linha(tr, ver_dados, lista, linha);
  });
  const corrigir = criar_elemento_real("button", "botao-nome", "Corrigir");
  corrigir.type = "button";
  corrigir.addEventListener("click", function () {
    abrir_correcao_da_linha(tr, lista, linha);
  });
  acao.append(ver_dados, corrigir);
  tr.append(acao);
  // A linha inteira abre (ou fecha) a ficha, como o "Ver todos os dados"
  abrir_o_detalhe_ao_clicar_na_linha(tr, function () {
    alternar_ficha_da_linha(tr, ver_dados, lista, linha);
  });
  return tr;
}

/**
 * Abre ou fecha, logo abaixo da pessoa, a ficha com todos os campos dela.
 *
 * Recebe: tr — a linha da pessoa; botao — o "Ver todos os dados" (troca o texto); lista; linha. Devolve: nada.
 */
function alternar_ficha_da_linha(tr, botao, lista, linha) {
  const proxima = tr.nextElementSibling;
  // Ficha aberta: fecha
  if (proxima && proxima.classList.contains("linha-ficha-real")) {
    proxima.remove();
    botao.textContent = "Ver todos os dados";
    botao.setAttribute("aria-expanded", "false");
    return;
  }
  // Ficha fechada: abre logo abaixo da pessoa (antes das pendências dela)
  tr.after(montar_ficha_da_linha(lista, linha));
  botao.textContent = "Esconder os dados";
  botao.setAttribute("aria-expanded", "true");
}

/**
 * Monta a ficha de uma pessoa: cada campo do layout com o rótulo, o "i" de ajuda e o valor, numa grade que quebra
 * em quantas colunas couberem na tela (nunca rola para o lado).
 *
 * Recebe: lista; linha — {linha, valores}. Devolve: o <tr> da ficha.
 */
function montar_ficha_da_linha(lista, linha) {
  const tr_da_ficha = criar_elemento_real("tr", "linha-ficha-real", "");
  const celula = criar_elemento_real("td", "", "");
  celula.colSpan = quantas_colunas_na_lista();
  const grade = criar_elemento_real("div", "grade-ficha-real", "");
  for (const campo of lista.campos) {
    const item = criar_elemento_real("div", "item-ficha-real", "");
    // O rótulo, com o "i" que abre o balão do que o banco escreveu no parâmetro do layout sobre o campo
    const rotulo = criar_elemento_real("span", "rotulo-ficha-real", rotulo_do_campo(campo.campo));
    const botao_de_ajuda = criar_elemento_real("button", "botao-ajuda-campo", "i");
    botao_de_ajuda.type = "button";
    botao_de_ajuda.dataset.campoReal = campo.campo;
    botao_de_ajuda.setAttribute("aria-label", "O que é " + rotulo_do_campo(campo.campo) + "?");
    rotulo.append(botao_de_ajuda);
    // O valor; campo em branco aparece como "Informação não encontrada" (a mesma frase da grade; ADR-143)
    const valor = criar_elemento_real("span", "valor-ficha-real", "");
    if (linha.valores[campo.campo]) {
      valor.textContent = linha.valores[campo.campo];
    } else {
      valor.append(criar_elemento_real("span", "valor-nao-encontrado", TEXTO_SEM_VALOR));
    }
    item.append(rotulo, valor);
    grade.append(item);
  }
  celula.append(grade);
  // O que a IA guardou sem rótulo, embaixo dos campos: só quando há alguma (js/grade_do_parametro.js; ADR-143, Parte 1)
  acrescentar_informacoes_sem_rotulo(celula, linha);
  tr_da_ficha.append(celula);
  return tr_da_ficha;
}

/**
 * Abre, logo abaixo da linha, o formulário de correção: o campo, o valor certo e "Salvar".
 *
 * Recebe: tr — a linha da tabela (o formulário entra logo depois dela); lista; linha;
 * campo_inicial — o campo que já vem escolhido (ex.: o da pendência), ou nada. Devolve: nada.
 */
function abrir_correcao_da_linha(tr, lista, linha, campo_inicial) {
  // Só um formulário aberto por vez.
  const aberto = document.querySelector(".linha-correcao-real");
  if (aberto) {
    aberto.remove();
  }
  const formulario = criar_elemento_real("tr", "linha-correcao-real", "");
  const celula = criar_elemento_real("td", "", "");
  celula.colSpan = quantas_colunas_na_lista();
  const escolha = criar_elemento_real("select", "campo-entrada campo-pequeno", "");
  escolha.setAttribute("aria-label", "Campo a corrigir");
  for (const campo of lista.campos) {
    escolha.append(new Option(rotulo_do_campo(campo.campo), campo.campo));
  }
  // O campo da pendência já vem escolhido; se ele não está na lista (ex.: CPF sem coluna), entra na escolha
  if (campo_inicial) {
    let ja_tem = false;
    for (const opcao of escolha.options) {
      if (opcao.value === campo_inicial) {
        ja_tem = true;
      }
    }
    if (!ja_tem) {
      escolha.append(new Option(rotulo_do_campo(campo_inicial), campo_inicial));
    }
    escolha.value = campo_inicial;
  }
  const valor = criar_elemento_real("input", "campo-entrada campo-pequeno", "");
  valor.placeholder = "Valor certo (vazio apaga)";
  valor.setAttribute("aria-label", "Valor certo");
  const salvar = criar_elemento_real("button", "botao botao-principal botao-pequeno", "Salvar");
  salvar.type = "button";
  salvar.addEventListener("click", function () {
    salvar_correcao_da_lista(salvar, linha.linha, escolha.value, valor.value);
  });
  const cancelar = criar_elemento_real("button", "botao-nome", "Cancelar");
  cancelar.type = "button";
  cancelar.addEventListener("click", function () {
    formulario.remove();
  });
  celula.append("Linha " + linha.linha + ": ", escolha, valor, salvar, cancelar);
  formulario.append(celula);
  tr.after(formulario);
}

/**
 * Manda a correção de um valor; a lista volta atualizada e a leitura é buscada de novo (as pendências podem mudar).
 *
 * Recebe: botao; numero_da_linha; campo; valor. Devolve: nada.
 */
async function salvar_correcao_da_lista(botao, numero_da_linha, campo, valor) {
  botao.disabled = true;
  const endereco = "/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id);
  const resposta = await pedir_a_api(endereco + "/lista/corrigir", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ linha: numero_da_linha, campo: campo, valor: valor }),
  });
  botao.disabled = false;
  if (!resposta.ok) {
    mostrar_erro_da_conferencia(texto_do_erro(resposta.dados.detail));
    return;
  }
  estado_da_conferencia.lista = resposta.dados;
  desenhar_lista_para_conferir();
  // A correção revalidou o envio: a leitura (pendências, etapa) pode ter mudado.
  const leitura = await pedir_a_api(endereco, {});
  if (leitura.ok) {
    envio_de_verdade.leitura = leitura.dados;
    mostrar_resultado_real(leitura.dados);
  }
}

// ===== 3. "Ajude a IA a acertar" =====

/**
 * Como a coluna aparece na escolha do "Ajude a IA a acertar": o que está no documento (com um exemplo) e como a IA
 * leu. Ex.: “Admissão” (ex.: “05/03/2026”) → lida como Data de admissão; na planilha, o nome da coluna.
 *
 * Recebe: coluna — da leitura. Devolve: o texto.
 */
function descricao_da_coluna_para_reler(coluna) {
  // O jeito da empresa (no texto corrido, o rótulo; na planilha, o nome da coluna), nunca o nome do campo do banco
  let descricao = nome_de_origem(coluna);
  if (coluna.exemplo) {
    descricao = descricao + " (ex.: \u201c" + coluna.exemplo + "\u201d)";
  }
  if (coluna.campo) {
    return descricao + " \u2192 lida como " + rotulo_do_campo(coluna.campo);
  }
  return descricao + " \u2192 deixada de fora";
}

/**
 * Guarda as colunas que podem ser relidas e volta o "Ajude a IA a acertar" para uma linha só, vazia.
 *
 * Recebe: colunas — as colunas da leitura. Devolve: nada.
 */
function montar_colunas_para_reler(colunas) {
  // Primeiro as que a IA deixou de fora (é o caso mais comum de pedir ajuda), depois as lidas
  colunas_para_reler = [];
  for (const coluna of colunas) {
    if (!coluna.campo) {
      colunas_para_reler.push(coluna);
    }
  }
  for (const coluna of colunas) {
    if (coluna.campo) {
      colunas_para_reler.push(coluna);
    }
  }
  document.querySelector("[data-real-pedidos-de-releitura]").replaceChildren();
  adicionar_pedido_de_releitura();
}

/**
 * Acrescenta uma linha ao "Ajude a IA a acertar": a escolha da coluna, a explicação e "Tirar".
 *
 * Recebe: nada. Devolve: nada. Com o limite de colunas atingido, não acrescenta.
 */
function adicionar_pedido_de_releitura() {
  const lista = document.querySelector("[data-real-pedidos-de-releitura]");
  if (lista.children.length >= MAXIMO_DE_COLUNAS_POR_RELEITURA) {
    return;
  }
  const copia = document.getElementById("modelo-pedido-de-releitura").content.cloneNode(true);
  const linha = copia.querySelector("[data-pedido-de-releitura]");
  const escolha = linha.querySelector("[data-releitura-coluna]");
  for (const coluna of colunas_para_reler) {
    escolha.append(new Option(descricao_da_coluna_para_reler(coluna), coluna.coluna));
  }
  // "Tirar" some a linha (a primeira fica: sempre há pelo menos uma)
  linha.querySelector("[data-releitura-tirar]").addEventListener("click", function () {
    linha.remove();
    atualizar_botoes_de_releitura();
  });
  lista.append(copia);
  atualizar_botoes_de_releitura();
}

/**
 * Mostra "Tirar" só quando há mais de uma linha e esconde "+ Explicar outra coluna" no limite.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_botoes_de_releitura() {
  const linhas = document.querySelectorAll("[data-pedido-de-releitura]");
  for (const linha of linhas) {
    linha.querySelector("[data-releitura-tirar]").hidden = linhas.length === 1;
  }
  document.querySelector("[data-real-mais-uma-coluna]").hidden = linhas.length >= MAXIMO_DE_COLUNAS_POR_RELEITURA;
}

/**
 * Pede que a IA releia as colunas escolhidas, cada uma com a sua dica (tudo conta como UMA releitura).
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
async function pedir_releitura(evento) {
  evento.preventDefault();
  // As linhas do formulário: [{coluna, dica}]
  const pedidos = [];
  for (const linha of document.querySelectorAll("[data-pedido-de-releitura]")) {
    pedidos.push({
      coluna: linha.querySelector("[data-releitura-coluna]").value,
      dica: linha.querySelector("[data-releitura-dica]").value,
    });
  }
  const botao = document.querySelector("[data-real-pedir-releitura]");
  botao.disabled = true;
  ligar_cronometro();
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/reler", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ colunas: pedidos }),
  });
  parar_cronometro();
  botao.disabled = false;
  if (!resposta.ok) {
    mostrar_erro_real(texto_do_erro(resposta.dados.detail));
    return;
  }
  document.querySelector("[data-real-bloco-ajude]").open = false;
  envio_de_verdade.leitura = resposta.dados;
  mostrar_resultado_real(resposta.dados);
  document.querySelector("[data-real-subtitulo]").textContent =
    "O Agente Interpretador releu " + pedidos.length + " coluna(s) com as suas dicas. Confira as colunas e " +
    "aceite de novo.";
}

/**
 * Liga as partes desta tela: abrir a conferência, mostrar mais linhas, "Conferi a lista" e a releitura.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_conferencia_real() {
  const bloco_da_conferencia = document.querySelector("[data-real-bloco-conferencia]");
  bloco_da_conferencia.addEventListener("toggle", function () {
    if (bloco_da_conferencia.open && estado_da_conferencia.lista === null) {
      carregar_lista_para_conferir();
    }
  });
  document.querySelector("[data-real-mais-linhas]").addEventListener("click", function () {
    estado_da_conferencia.quantas_mostrar = estado_da_conferencia.quantas_mostrar + LINHAS_POR_VEZ;
    desenhar_lista_para_conferir();
  });
  document.querySelector("[data-real-conferi-caixa]").addEventListener("change", atualizar_botao_de_envio);
  // O filtro "Mostrar só quem tem pendência": volta para o começo da lista a cada troca
  document.querySelector("[data-real-so-pendencias]").addEventListener("change", function (evento) {
    estado_da_conferencia.so_pendencias = evento.target.checked;
    estado_da_conferencia.quantas_mostrar = LINHAS_POR_VEZ;
    // Lista já carregada: redesenha; ainda chegando: busca (e desenha com o filtro novo)
    if (estado_da_conferencia.lista !== null) {
      desenhar_lista_para_conferir();
    } else {
      carregar_lista_para_conferir();
    }
  });
  document.querySelector("[data-real-formulario-ajude]").addEventListener("submit", pedir_releitura);
  document.querySelector("[data-real-mais-uma-coluna]").addEventListener("click", adicionar_pedido_de_releitura);
  // O "i" de ajuda dos campos, dentro da ficha de cada pessoa. A escuta fica no corpo inteiro da lista, porque as
  // fichas são refeitas a cada desenho
  document.querySelector("[data-real-corpo-conferencia]").addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-campo-real]");
    if (botao) {
      // Impede que este mesmo clique "suba" até a página e feche o balão na hora (js/conferir.js fecha ao clicar fora)
      evento.stopPropagation();
      abrir_ajuda_do_campo_real(botao);
    }
  });
}

// Quando o HTML terminar de carregar, liga as partes.
document.addEventListener("DOMContentLoaded", preparar_conferencia_real);
