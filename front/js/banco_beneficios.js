/*
  banco_beneficios.js — as KBs de endomarketing (ADR-125) dentro da aba "Endomarketing" do Portal Interno.

  Para que serve: mostra as KBs de um dono, abre cada KB com as seções e as versões, e faz as ações do especialista:
  criar, editar (versão nova), conferir na trava, publicar, retirar e revisar a vigência.
  Quem escolhe o dono é o js/banco_endomarketing.js, chamando abrir_kbs_do_dono():
    - guia "Base de Conhecimento": as KBs da empresa escolhida no topo, com os Benefícios na primeira aba;
    - guia "Regras gerais": as que valem para todas as empresas, as diretrizes gerais ("GERAL") ou as do Santander
      ("SANTANDER": o kit padrão e a prateleira de benefícios).
  A antiga tela "Benefícios e KBs" (banco_beneficios.html) foi aposentada: o endereço dela leva para cá.

  Publicar, retirar ou renovar uma KB da empresa já atualiza sozinho a vitrine, o catálogo do agente e o kit (o
  servidor aplica na empresa; não há botão "Aplicar"). Quando isso acontece, este arquivo avisa a página (evento
  "kbs-aplicadas") para a guia do material oferecer os benefícios do catálogo novo.
  "Aguardando publicação": as versões novas (rascunho) com quem salvou, data e hora, "Visualizar" e "Publicar".
  "Histórico anterior": na janela de uma KB, as versões mais antigas que a atual abrem CONGELADAS (cor de gelo, selo
  "Congelada", sem nenhuma ação), com a navegação entre elas.
  O kit da marca (a KB "Kit da marca" é a fonte única do kit da empresa): no editor,
  a escolha entre o próprio e o padrão, as cores (com as amostras) e o LOGO, que vai para a versão gravada como
  rascunho (PNG ou JPEG, até 500 KB); a janela de uma KB de kit mostra as cores e o logo daquela versão. As peças do
  kit ficam no js/kit_da_marca.js; quem aplica o kit na empresa é o servidor, ao publicar ou retirar a KB.

  Segurança: todo texto que vem da API entra na tela com textContent (nunca como HTML). O Markdown das KBs é lido
  linha a linha e vira elementos (parágrafo, lista, tabela, negrito) montados um a um.

  Ordem do arquivo: 1. estado e pedidos à API · 2. peças da tela · 3. o dono aberto · 4. a lista de KBs · 5. o
  Markdown · 6. a janela de uma KB · 7. o editor · 8. as ações · 9. a confirmação · 10. o começo.
*/

// ---------------- 1. Estado e pedidos à API ----------------

// O que a tela guarda enquanto está aberta.
const estado_das_kbs = {
  modelos: null,          // os tipos (com as seções), as categorias, os kits e os donos (da rota /modelos)
  kbs: [],                // todas as KBs (uma linha por KB), de todos os donos
  dono: null,             // o dono aberto: a empresa (ex.: "EMP001"), "GERAL" ou "SANTANDER"
  tipo: "todos",          // a aba de tipo escolhida
  filtro: "todas",        // "todas", "revisar" ou "rascunho"
  kb_aberta: null,        // a KB mostrada na janela (com as seções e as versões)
  kb_editada: null,       // o id da KB no editor (null = KB nova)
  corpo_do_modelo: "",    // o texto do modelo posto no editor (para saber se a pessoa já escreveu algo)
  acao_confirmada: null,  // o que o botão da janela de confirmação faz
  logo_do_editor: null,   // o logo no editor de uma KB de kit (ver preparar_logo_no_editor, no js/kit_da_marca.js)
};

// O endereço-base das rotas das KBs.
const ENDERECO_DAS_KBS = "/api/banco/kbs-endomarketing";

// O tipo que abre primeiro: os benefícios, numa aba só deles (nos donos que podem ter benefício).
const TIPO_DOS_BENEFICIOS = "beneficio";

/**
 * Manda um pedido à API e devolve a resposta já lida.
 *
 * Recebe: endereco; opcoes — as do fetch. Devolve: { ok, dados } — em erro, dados.detail traz o motivo (um texto ou,
 * quando a trava bloqueou, { mensagem, achados }). Sem conexão, { ok: false } com uma mensagem clara.
 */
async function pedir_as_kbs(endereco, opcoes) {
  try {
    const resposta = await fetch(endereco, opcoes);
    const dados = await resposta.json();
    return { ok: resposta.ok, dados: dados };
  } catch (erro) {
    return { ok: false, dados: { detail: "Sem conexão com o servidor. Tente de novo." } };
  }
}

/**
 * Um pedido POST com um corpo em JSON (ou sem corpo).
 *
 * Recebe: endereco; corpo — o objeto a enviar (ou null). Devolve: { ok, dados }.
 */
function postar_nas_kbs(endereco, corpo) {
  const opcoes = { method: "POST", headers: { "Content-Type": "application/json" } };
  // Sem corpo, manda um objeto vazio (a API espera JSON)
  opcoes.body = JSON.stringify(corpo || {});
  return pedir_as_kbs(endereco, opcoes);
}

/**
 * O texto do erro da API para a pessoa: a mensagem da trava, o texto do erro ou um recado padrão.
 *
 * Recebe: detalhe — o "detail" da resposta. Devolve: o texto.
 */
function texto_do_erro_das_kbs(detalhe) {
  if (detalhe && typeof detalhe === "object" && detalhe.mensagem) {
    return detalhe.mensagem;
  }
  if (typeof detalhe === "string") {
    return detalhe;
  }
  return "Não deu certo. Confira os campos e tente de novo.";
}

// ---------------- 2. Peças da tela ----------------

/**
 * Cria um elemento com a classe e o texto (o texto entra sempre como texto, nunca como HTML).
 *
 * Recebe: tag; classe (pode ser ""); texto (pode ser ""). Devolve: o elemento.
 */
function criar_elemento_das_kbs(tag, classe, texto) {
  const elemento = document.createElement(tag);
  if (classe) {
    elemento.className = classe;
  }
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Um botão pequeno com o texto e a ação do clique.
 *
 * Recebe: texto; classe_extra ("botao-principal" ou "botao-contorno"); ao_clicar. Devolve: o botão.
 */
function botao_das_kbs(texto, classe_extra, ao_clicar) {
  const botao = criar_elemento_das_kbs("button", "botao botao-pequeno " + classe_extra, texto);
  botao.type = "button";
  botao.addEventListener("click", ao_clicar);
  return botao;
}

/**
 * Um ícone da biblioteca da página (o <symbol> com aquele id), montado como elemento SVG.
 *
 * Recebe: nome — o id do símbolo (ex.: "icone-documento"). Devolve: o <svg>.
 */
function icone_das_kbs(nome) {
  // O SVG precisa ser criado com o "endereço" dele; senão o navegador não o desenha
  const endereco_do_svg = "http://www.w3.org/2000/svg";
  const desenho = document.createElementNS(endereco_do_svg, "svg");
  desenho.setAttribute("class", "icone");
  const uso = document.createElementNS(endereco_do_svg, "use");
  uso.setAttribute("href", "#" + nome);
  desenho.append(uso);
  return desenho;
}

/**
 * Um selo (etiqueta) colorido. Recebe: texto; tipo — "sucesso", "atencao", "marca" ou "neutro". Devolve: o selo.
 */
function selo_das_kbs(texto, tipo) {
  return criar_elemento_das_kbs("span", "selo selo-pequeno selo-" + tipo, texto);
}

/**
 * Uma data "AAAA-MM-DD" (ou com hora) no formato "DD/MM/AAAA". Exemplo: "2026-12-31" → "31/12/2026".
 */
function data_das_kbs(data_em_texto) {
  if (!data_em_texto) {
    return "";
  }
  const partes = data_em_texto.slice(0, 10).split("-");
  return partes[2] + "/" + partes[1] + "/" + partes[0];
}

/**
 * Um momento gravado pela API (ISO, em UTC) com data e hora no fuso de quem vê. Exemplo:
 * "2026-09-29T15:04:00+00:00" → "29/09/2026 às 12:04" (no horário de Brasília).
 */
function data_e_hora_das_kbs(momento_em_texto) {
  if (!momento_em_texto) {
    return "";
  }
  const momento = new Date(momento_em_texto);
  const data = momento.toLocaleDateString("pt-BR");
  const hora = momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return data + " às " + hora;
}

/**
 * Mostra o aviso verde no alto da página (e rola até ele). Recebe: texto. Devolve: nada.
 */
function mostrar_aviso_das_kbs(texto) {
  const aviso = document.querySelector("[data-aviso-kbs]");
  document.querySelector("[data-aviso-kbs-texto]").textContent = texto;
  aviso.hidden = false;
  aviso.scrollIntoView({ behavior: "smooth", block: "center" });
}

/**
 * O selo da vigência de uma KB: vencida, vence em breve, futura ou nada (vigente).
 *
 * Recebe: vigencia — "vigente", "vence_em_breve", "vencida" ou "futura"; fim — a data de fim. Devolve: o selo ou null.
 */
function selo_da_vigencia(vigencia, fim) {
  if (vigencia === "vencida") {
    return selo_das_kbs("Vencida em " + data_das_kbs(fim), "atencao");
  }
  if (vigencia === "vence_em_breve") {
    return selo_das_kbs("Vence em " + data_das_kbs(fim), "atencao");
  }
  if (vigencia === "futura") {
    return selo_das_kbs("Começa depois", "neutro");
  }
  return null;
}

/**
 * O selo da situação: "Publicada vN", "Rascunho vN", "Retirada"...
 *
 * Recebe: situacao; versao. Devolve: o selo.
 */
function selo_da_situacao(situacao, versao) {
  const nomes = { PUBLICADA: "Publicada", RASCUNHO: "Rascunho", RETIRADA: "Retirada", SUBSTITUIDA: "Substituída" };
  const cores = { PUBLICADA: "sucesso", RASCUNHO: "marca", RETIRADA: "neutro", SUBSTITUIDA: "neutro" };
  return selo_das_kbs((nomes[situacao] || situacao) + " v" + versao, cores[situacao] || "neutro");
}

/**
 * O nome do dono para a tela (ex.: "EMP001" → "Aurora Alimentos Ltda."). Dono desconhecido volta como está.
 */
function nome_do_dono(dono) {
  for (const item of estado_das_kbs.modelos.donos) {
    if (item.dono === dono) {
      return item.nome;
    }
  }
  return dono;
}

/**
 * Diz se o dono é uma empresa (um código como "EMP001").
 */
function dono_e_empresa(dono) {
  return /^EMP\d{3}$/.test(dono);
}

// ---------------- 3. O dono aberto ----------------

/**
 * As KBs de um dono (da lista guardada). Recebe: dono. Devolve: a lista.
 */
function kbs_do_dono(dono) {
  const lista = [];
  for (const kb of estado_das_kbs.kbs) {
    if (kb.dono === dono) {
      lista.push(kb);
    }
  }
  return lista;
}

/**
 * Diz se o dono pode ter KB de benefício (as empresas e o Santander, com a prateleira; as diretrizes gerais, não).
 */
function dono_tem_beneficios(dono) {
  for (const opcao of tipos_do_dono(dono)) {
    if (opcao[0] === TIPO_DOS_BENEFICIOS) {
      return true;
    }
  }
  return false;
}

/**
 * Abre um dono: a frase de apoio, as abas de tipo (Benefícios primeiro, quando ele pode ter) e a lista das KBs.
 *
 * Recebe: dono. Devolve: nada.
 */
function escolher_dono(dono) {
  estado_das_kbs.dono = dono;
  // A aba que abre: a dos Benefícios; nas diretrizes gerais (que não têm benefício), "Todas"
  estado_das_kbs.tipo = "todos";
  if (dono_tem_beneficios(dono)) {
    estado_das_kbs.tipo = TIPO_DOS_BENEFICIOS;
  }
  // A frase de apoio de cada grupo
  let descricao = "As KBs desta empresa: benefícios, jornada, landing page, kit da marca e canais de atendimento.";
  if (dono === "GERAL") {
    descricao = "As regras que valem para todas as empresas: tom de voz, termos proibidos, guardrails, diretrizes, canais, glossário e a jornada padrão.";
  } else if (dono === "SANTANDER") {
    descricao = "O kit da marca padrão e a prateleira de benefícios, a base dos benefícios de cada empresa.";
  }
  document.querySelector("[data-descricao-dono]").textContent = descricao;
  montar_abas_de_tipos();
  montar_lista_de_kbs();
}

// ---------------- 4. As abas de tipo e a lista de KBs ----------------

/**
 * As abas de tipo do dono: "Benefícios" primeiro (sempre, mesmo sem nenhuma KB, para a pessoa saber onde criar; só
 * nos donos que podem ter benefício), depois os outros tipos que ele tem e, por último, "Todas".
 *
 * Recebe: quantidade_por_tipo — ex.: { beneficio: 3, jornada: 1 }. Devolve: [[chave, nome da aba]].
 * Exemplo: → [["beneficio", "Benefícios (3)"], ["jornada", "Jornada (1)"], ["todos", "Todas (4)"]].
 */
function abas_do_dono(quantidade_por_tipo) {
  const opcoes = [];
  let total = 0;
  const tem_beneficios = dono_tem_beneficios(estado_das_kbs.dono);
  for (const tipo of estado_das_kbs.modelos.tipos) {
    const quantidade = quantidade_por_tipo[tipo.tipo] || 0;
    total = total + quantidade;
    // Os benefícios têm a aba deles com o nome "Benefícios"; entram na frente de todas
    if (tipo.tipo === TIPO_DOS_BENEFICIOS && tem_beneficios) {
      opcoes.unshift([tipo.tipo, "Benefícios (" + quantidade + ")"]);
    } else if (quantidade > 0) {
      opcoes.push([tipo.tipo, tipo.nome + " (" + quantidade + ")"]);
    }
  }
  opcoes.push(["todos", "Todas (" + total + ")"]);
  return opcoes;
}

/**
 * Monta as abas de tipo do dono aberto (ver abas_do_dono), com a escolhida marcada.
 */
function montar_abas_de_tipos() {
  const abas = document.querySelector("[data-abas-tipos]");
  abas.replaceChildren();
  // Conta as KBs por tipo
  const quantidade_por_tipo = {};
  for (const kb of kbs_do_dono(estado_das_kbs.dono)) {
    quantidade_por_tipo[kb.tipo] = (quantidade_por_tipo[kb.tipo] || 0) + 1;
  }
  const opcoes = abas_do_dono(quantidade_por_tipo);
  for (const opcao of opcoes) {
    const aba = criar_elemento_das_kbs("button", "aba-ficha", opcao[1]);
    aba.type = "button";
    aba.setAttribute("role", "tab");
    const escolhida = opcao[0] === estado_das_kbs.tipo;
    aba.classList.toggle("aba-ficha-ativa", escolhida);
    aba.setAttribute("aria-selected", String(escolhida));
    aba.addEventListener("click", function () {
      estado_das_kbs.tipo = opcao[0];
      montar_abas_de_tipos();
      montar_lista_de_kbs();
    });
    abas.append(aba);
  }
}

/**
 * Diz se a KB entra na lista, pelo tipo escolhido e pelo filtro (todas, para revisar, rascunhos).
 */
function kb_entra_na_lista(kb) {
  if (estado_das_kbs.tipo !== "todos" && kb.tipo !== estado_das_kbs.tipo) {
    return false;
  }
  if (estado_das_kbs.filtro === "revisar") {
    return kb.para_revisar;
  }
  if (estado_das_kbs.filtro === "rascunho") {
    return kb.situacao_da_ultima === "RASCUNHO";
  }
  return true;
}

/**
 * Uma linha da lista: ícone, título, detalhe (tipo, categoria, vigência), selos e o botão "Abrir".
 *
 * Recebe: kb (o resumo da lista). Devolve: o <li>.
 */
function montar_linha_da_kb(kb) {
  const linha = criar_elemento_das_kbs("li", "item-fila item-kb", "");
  const icone = criar_elemento_das_kbs("span", "item-fila-icone", "");
  icone.append(icone_das_kbs("icone-documento"));
  linha.append(icone);
  const textos = criar_elemento_das_kbs("div", "", "");
  textos.append(criar_elemento_das_kbs("div", "item-fila-titulo", kb.titulo));
  // O detalhe: o tipo, a categoria (nos benefícios) e até quando vale
  let detalhe = kb.nome_do_tipo;
  if (kb.categoria) {
    detalhe = detalhe + " · " + kb.categoria;
  }
  detalhe = detalhe + " · vale até " + data_das_kbs(kb.vigencia_fim) + " · " + kb.kb_id;
  textos.append(criar_elemento_das_kbs("div", "item-fila-detalhe", detalhe));
  // Os selos: a versão publicada, o rascunho mais novo e a vigência
  const selos = criar_elemento_das_kbs("div", "selos-da-kb", "");
  if (kb.versao_publicada) {
    selos.append(selo_da_situacao("PUBLICADA", kb.versao_publicada));
  } else {
    selos.append(selo_das_kbs("Sem versão publicada", "neutro"));
  }
  if (kb.situacao_da_ultima === "RASCUNHO") {
    selos.append(selo_da_situacao("RASCUNHO", kb.ultima_versao));
  }
  const vigencia = selo_da_vigencia(kb.vigencia, kb.vigencia_fim);
  if (vigencia) {
    selos.append(vigencia);
  }
  textos.append(selos);
  linha.append(textos);
  linha.append(botao_das_kbs("Abrir", "botao-contorno", function () {
    abrir_kb(kb.kb_id, null);
  }));
  return linha;
}

/**
 * Monta a lista de KBs do dono, com o tipo e o filtro escolhidos.
 */
function montar_lista_de_kbs() {
  const lista = document.querySelector("[data-lista-kbs]");
  lista.replaceChildren();
  for (const kb of kbs_do_dono(estado_das_kbs.dono)) {
    if (kb_entra_na_lista(kb)) {
      lista.append(montar_linha_da_kb(kb));
    }
  }
  marcar_como_carregado(lista);
  document.querySelector("[data-sem-kbs]").hidden = lista.children.length > 0;
  // A lista "Aguardando publicação" muda junto (depois de salvar, publicar ou trocar de empresa)
  montar_aguardando_publicacao();
}

/**
 * Uma linha de "Aguardando publicação": o título, o tipo e a versão nova, quem a salvou e quando (data e hora), e os
 * botões "Visualizar" (abre a versão nova na janela) e "Publicar" (ela passa a valer).
 *
 * Recebe: kb (o resumo da lista, com a última versão em rascunho). Devolve: o <li>.
 */
function montar_linha_aguardando(kb) {
  const linha = criar_elemento_das_kbs("li", "item-fila item-kb item-aguardando", "");
  linha.dataset.kbAguardando = kb.kb_id;
  const icone = criar_elemento_das_kbs("span", "item-fila-icone", "");
  icone.append(icone_das_kbs("icone-documento"));
  linha.append(icone);
  const textos = criar_elemento_das_kbs("div", "", "");
  textos.append(criar_elemento_das_kbs("div", "item-fila-titulo", kb.titulo));
  // O tipo, a versão nova e a que vale hoje (ou que nenhuma vale ainda)
  let detalhe = kb.nome_do_tipo + " · versão " + kb.ultima_versao + " · ";
  if (kb.versao_publicada) {
    detalhe = detalhe + "hoje vale a versão " + kb.versao_publicada;
  } else {
    detalhe = detalhe + "ainda sem versão publicada";
  }
  textos.append(criar_elemento_das_kbs("div", "item-fila-detalhe", detalhe));
  // O registro: quem salvou a versão nova e quando
  textos.append(criar_elemento_das_kbs("div", "item-fila-detalhe registro-aguardando",
    "Salva por " + kb.atualizado_por + " em " + data_e_hora_das_kbs(kb.atualizado_em)));
  const selos = criar_elemento_das_kbs("div", "selos-da-kb", "");
  selos.append(selo_da_situacao("RASCUNHO", kb.ultima_versao));
  textos.append(selos);
  linha.append(textos);
  // Os dois botões, lado a lado
  const acoes = criar_elemento_das_kbs("div", "acoes-aguardando", "");
  acoes.append(botao_das_kbs("Visualizar", "botao-contorno", function () {
    abrir_kb(kb.kb_id, kb.ultima_versao);
  }));
  acoes.append(botao_das_kbs("Publicar", "botao-principal", function () {
    publicar_versao(kb.kb_id, kb.ultima_versao, false);
  }));
  linha.append(acoes);
  return linha;
}

/**
 * Monta "Aguardando publicação": as KBs do dono cuja versão mais nova é um rascunho (de qualquer tipo, fora das abas
 * e dos filtros), com o contador. Só a página embutida no Endomarketing tem esta lista.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_aguardando_publicacao() {
  const lista = document.querySelector("[data-lista-aguardando]");
  // Página sem a lista (a tela inteira): nada a fazer
  if (!lista) {
    return;
  }
  lista.replaceChildren();
  for (const kb of kbs_do_dono(estado_das_kbs.dono)) {
    if (kb.situacao_da_ultima === "RASCUNHO") {
      lista.append(montar_linha_aguardando(kb));
    }
  }
  document.querySelector("[data-contador-aguardando]").textContent = String(lista.children.length);
  document.querySelector("[data-sem-aguardando]").hidden = lista.children.length > 0;
}

/**
 * Busca de novo todas as KBs e remonta a tela (depois de gravar, publicar, retirar...).
 */
async function recarregar_kbs() {
  const resposta = await pedir_as_kbs(ENDERECO_DAS_KBS);
  if (!resposta.ok) {
    mostrar_aviso_das_kbs(texto_do_erro_das_kbs(resposta.dados.detail));
    return;
  }
  estado_das_kbs.kbs = resposta.dados.kbs;
  montar_abas_de_tipos();
  montar_lista_de_kbs();
}

// ---------------- 5. O Markdown das KBs, montado em elementos ----------------

/**
 * Põe um texto com **negrito** dentro do elemento: os pedaços entre "**" viram <strong>, o resto vira texto.
 *
 * Recebe: elemento; texto. Devolve: nada. Exemplo: "Sem **tarifa** no pacote" → "Sem ", <strong>tarifa</strong>, " no pacote".
 */
function por_texto_com_negrito(elemento, texto) {
  const pedacos = texto.split("**");
  for (let posicao = 0; posicao < pedacos.length; posicao = posicao + 1) {
    // Os pedaços de posição ímpar ficaram entre dois "**"
    if (posicao % 2 === 1) {
      elemento.append(criar_elemento_das_kbs("strong", "", pedacos[posicao]));
    } else {
      elemento.append(document.createTextNode(pedacos[posicao]));
    }
  }
}

/**
 * As células de uma linha de tabela do Markdown ("| a | b |" → ["a", "b"]).
 */
function celulas_da_linha(linha) {
  const celulas = [];
  for (const celula of linha.trim().replace(/^\|/, "").replace(/\|$/, "").split("|")) {
    celulas.push(celula.trim());
  }
  return celulas;
}

/**
 * Diz se a linha é a de traços que separa o cabeçalho de uma tabela ("|---|---|").
 */
function e_linha_de_tracos(linha) {
  return /^\|?[\s:\-|]+\|?$/.test(linha.trim());
}

/**
 * Monta o texto de uma seção: parágrafos, listas ("- " ou "1. "), subtítulos ("### ") e tabelas ("| ... |").
 *
 * Recebe: texto (o Markdown da seção). Devolve: um <div> com os elementos. Nada vira HTML cru.
 */
function montar_markdown(texto) {
  const caixa = criar_elemento_das_kbs("div", "texto-da-kb", "");
  let lista_aberta = null;
  let tabela_aberta = null;
  for (const linha_original of texto.split("\n")) {
    const linha = linha_original.trim();
    // Linha de tabela: abre a tabela (a 1ª linha é o cabeçalho) ou acrescenta uma linha
    if (linha.startsWith("|")) {
      lista_aberta = null;
      if (e_linha_de_tracos(linha)) {
        continue;
      }
      const cabecalho = tabela_aberta === null;
      if (cabecalho) {
        tabela_aberta = criar_elemento_das_kbs("table", "tabela-da-kb", "");
        caixa.append(tabela_aberta);
      }
      const linha_da_tabela = criar_elemento_das_kbs("tr", "", "");
      for (const celula of celulas_da_linha(linha)) {
        const elemento = criar_elemento_das_kbs(cabecalho ? "th" : "td", "", "");
        por_texto_com_negrito(elemento, celula);
        linha_da_tabela.append(elemento);
      }
      tabela_aberta.append(linha_da_tabela);
      continue;
    }
    tabela_aberta = null;
    // Item de lista: "- texto" ou "1. texto"
    const item = linha.match(/^(-|\d+\.)\s+(.*)$/);
    if (item) {
      if (lista_aberta === null) {
        lista_aberta = criar_elemento_das_kbs(item[1] === "-" ? "ul" : "ol", "lista-da-kb", "");
        caixa.append(lista_aberta);
      }
      const elemento = criar_elemento_das_kbs("li", "", "");
      por_texto_com_negrito(elemento, item[2]);
      lista_aberta.append(elemento);
      continue;
    }
    lista_aberta = null;
    // Linha vazia só separa os blocos
    if (linha === "") {
      continue;
    }
    // Subtítulo dentro da seção
    if (linha.startsWith("### ")) {
      caixa.append(criar_elemento_das_kbs("h5", "subtitulo-interno-da-kb", linha.slice(4)));
      continue;
    }
    // O resto é parágrafo
    const paragrafo = criar_elemento_das_kbs("p", "", "");
    por_texto_com_negrito(paragrafo, linha);
    caixa.append(paragrafo);
  }
  return caixa;
}

// ---------------- 6. A janela de uma KB ----------------

/**
 * Busca a KB (a versão pedida, ou a publicada/última) e abre a janela com as seções, as versões e as ações.
 *
 * Recebe: kb_id; versao (ou null). Devolve: nada.
 */
async function abrir_kb(kb_id, versao) {
  let endereco = ENDERECO_DAS_KBS + "/" + encodeURIComponent(kb_id);
  if (versao) {
    endereco = endereco + "?versao=" + versao;
  }
  const resposta = await pedir_as_kbs(endereco);
  if (!resposta.ok) {
    mostrar_aviso_das_kbs(texto_do_erro_das_kbs(resposta.dados.detail));
    return;
  }
  estado_das_kbs.kb_aberta = resposta.dados;
  preencher_janela_da_kb();
  const janela = document.getElementById("janela-kb");
  if (!janela.open) {
    janela.showModal();
  }
}

/**
 * Preenche a janela com a KB aberta: título, selos, ficha, seções, versões e botões.
 */
function preencher_janela_da_kb() {
  const kb = estado_das_kbs.kb_aberta;
  document.querySelector("[data-kb-sobretitulo]").textContent = kb.nome_do_tipo + " · " + nome_do_dono(kb.dono);
  document.querySelector("[data-kb-titulo]").textContent = kb.titulo;
  const selos = document.querySelector("[data-kb-selos]");
  selos.replaceChildren(selo_da_situacao(kb.situacao, kb.versao));
  // Versão do histórico anterior: o selo "Congelada" diz que ela não vale mais
  if (versao_esta_no_historico(kb, kb.versao)) {
    selos.append(selo_das_kbs("Congelada", "congelada"));
  }
  const vigencia = selo_da_vigencia(kb.vigencia, kb.vigencia_fim);
  if (vigencia) {
    selos.append(vigencia);
  }
  // A ficha numa linha
  let ficha = kb.kb_id + " · vale de " + data_das_kbs(kb.vigencia_inicio) + " a " + data_das_kbs(kb.vigencia_fim);
  ficha = ficha + " · origem: " + (kb.ficha.origem || "—");
  if (kb.ficha.categoria) {
    ficha = ficha + " · categoria: " + kb.ficha.categoria;
  }
  if (kb.ficha.cores) {
    ficha = ficha + " · cores: " + kb.ficha.cores;
  }
  document.querySelector("[data-kb-ficha]").textContent = ficha;
  // No kit da marca: as cores e o logo desta versão (js/kit_da_marca.js)
  mostrar_kit_na_janela(kb);
  // As seções
  const secoes = document.querySelector("[data-kb-secoes]");
  secoes.replaceChildren();
  for (const secao of kb.secoes) {
    const bloco = criar_elemento_das_kbs("section", "secao-da-kb", "");
    bloco.append(criar_elemento_das_kbs("h4", "titulo-da-secao-da-kb", secao.titulo));
    bloco.append(montar_markdown(secao.texto));
    secoes.append(bloco);
  }
  montar_versoes_da_kb(kb);
  montar_botoes_da_kb(kb);
  // Uma versão do histórico anterior aparece congelada: a cor de gelo, a faixa e a navegação entre as antigas
  const congelada = versao_esta_no_historico(kb, kb.versao);
  document.getElementById("janela-kb").classList.toggle("janela-kb-congelada", congelada);
  montar_faixa_congelada(kb);
  // Some com o erro, os achados e a revisão de uma KB aberta antes
  document.querySelector("[data-kb-erro]").hidden = true;
  document.querySelector("[data-kb-achados]").hidden = true;
  document.querySelector("[data-kb-revisar]").hidden = true;
}

// ---------------- 6.1 O histórico anterior (versões congeladas) ----------------

/**
 * A versão que vale hoje: a publicada; sem publicada, a mais nova (ex.: uma retirada).
 *
 * Recebe: kb (com "versoes"). Devolve: o número da versão. Exemplo: v1 substituída, v2 publicada, v3 rascunho → 2.
 */
function versao_atual_da_kb(kb) {
  let mais_nova = 0;
  for (const versao of kb.versoes) {
    if (versao.situacao === "PUBLICADA") {
      return versao.versao;
    }
    mais_nova = Math.max(mais_nova, versao.versao);
  }
  return mais_nova;
}

/**
 * Diz se a versão é do histórico anterior (mais antiga que a atual): congelada, só para consulta.
 *
 * Recebe: kb; numero_da_versao. Devolve: true ou false. Exemplo: com a v2 publicada, a v1 → true e a v3 (rascunho) → false.
 */
function versao_esta_no_historico(kb, numero_da_versao) {
  return numero_da_versao < versao_atual_da_kb(kb);
}

/**
 * As versões do histórico anterior, da mais recente para a mais antiga.
 *
 * Recebe: kb. Devolve: a lista de versões (os itens de kb.versoes). Exemplo: v1, v2 antigas e v3 atual → [v2, v1].
 */
function versoes_do_historico(kb) {
  const anteriores = [];
  for (const versao of kb.versoes) {
    if (versao_esta_no_historico(kb, versao.versao)) {
      anteriores.push(versao);
    }
  }
  // Da mais recente para a mais antiga
  anteriores.sort(function (primeira, segunda) {
    return segunda.versao - primeira.versao;
  });
  return anteriores;
}

/**
 * O texto de quando a versão deixou de valer: a próxima versão publicada depois dela.
 *
 * Recebe: kb; numero_da_versao. Devolve: o texto (ou "" se não há registro).
 * Exemplo: "Substituída pela versão 3, publicada por rafael.lima em 29/09/2026 às 10:12."
 */
function texto_da_substituicao(kb, numero_da_versao) {
  let substituta = null;
  for (const versao of kb.versoes) {
    const e_mais_nova = versao.versao > numero_da_versao && versao.publicado_em;
    // A primeira publicada depois dela é a que a substituiu
    if (e_mais_nova && (!substituta || versao.versao < substituta.versao)) {
      substituta = versao;
    }
  }
  if (!substituta) {
    return "";
  }
  return "Substituída pela versão " + substituta.versao + ", publicada por " + substituta.publicado_por + " em " +
    data_e_hora_das_kbs(substituta.publicado_em) + ".";
}

/**
 * A faixa de gelo no alto da janela, quando a versão aberta é do histórico: o que ela é, que não vale mais, e a
 * navegação entre as versões antigas (mais antiga, mais recente e voltar à atual).
 *
 * Recebe: kb (a KB aberta). Devolve: nada.
 */
function montar_faixa_congelada(kb) {
  const faixa = document.querySelector("[data-kb-congelada]");
  // A página sem a faixa (HTML antigo) ou versão que não é do histórico: nada a mostrar
  if (!faixa) {
    return;
  }
  faixa.hidden = !versao_esta_no_historico(kb, kb.versao);
  if (faixa.hidden) {
    return;
  }
  const historico = versoes_do_historico(kb);
  // A posição da versão aberta no histórico (0 = a mais recente das antigas)
  let posicao = 0;
  for (let indice = 0; indice < historico.length; indice = indice + 1) {
    if (historico[indice].versao === kb.versao) {
      posicao = indice;
    }
  }
  const texto = "Versão " + kb.versao + " congelada (" + (posicao + 1) + " de " + historico.length +
    " no histórico). Só para consulta: não vale para a vitrine nem para o agente, e não pode ser editada nem publicada. " +
    texto_da_substituicao(kb, kb.versao);
  document.querySelector("[data-kb-congelada-texto]").textContent = texto;
  // A navegação: a mais antiga fica no fim da lista, a mais recente no começo
  const navegacao = document.querySelector("[data-kb-navegacao-historico]");
  navegacao.replaceChildren();
  if (posicao < historico.length - 1) {
    navegacao.append(botao_das_kbs("‹ Versão mais antiga", "botao-contorno", function () {
      abrir_kb(kb.kb_id, historico[posicao + 1].versao);
    }));
  }
  if (posicao > 0) {
    navegacao.append(botao_das_kbs("Versão mais recente ›", "botao-contorno", function () {
      abrir_kb(kb.kb_id, historico[posicao - 1].versao);
    }));
  }
  navegacao.append(botao_das_kbs("Voltar à versão atual", "botao-principal", function () {
    abrir_kb(kb.kb_id, versao_atual_da_kb(kb));
  }));
}

/**
 * A lista das versões: situação, quem criou e quando; botão "Ver" e, no rascunho ou na retirada que não é do
 * histórico, "Publicar". As versões do histórico anterior aparecem congeladas (cor de gelo, sem "Publicar").
 */
function montar_versoes_da_kb(kb) {
  const lista = document.querySelector("[data-kb-versoes]");
  lista.replaceChildren();
  for (const versao of kb.versoes) {
    const linha = criar_elemento_das_kbs("li", "versao-da-kb", "");
    const congelada = versao_esta_no_historico(kb, versao.versao);
    linha.classList.toggle("versao-da-kb-congelada", congelada);
    linha.append(selo_da_situacao(versao.situacao, versao.versao));
    if (congelada) {
      linha.append(selo_das_kbs("Congelada", "congelada"));
    }
    let texto = "criada por " + versao.criado_por + " em " + data_e_hora_das_kbs(versao.criado_em);
    if (versao.publicado_em) {
      texto = texto + " · publicada por " + versao.publicado_por + " em " + data_e_hora_das_kbs(versao.publicado_em);
    }
    linha.append(criar_elemento_das_kbs("span", "versao-da-kb-texto", texto));
    // "Ver" mostra aquela versão na janela (a que está aberta não precisa)
    if (versao.versao !== kb.versao) {
      linha.append(botao_das_kbs("Ver", "botao-contorno", function () {
        abrir_kb(kb.kb_id, versao.versao);
      }));
    }
    // Publicar: o rascunho ou a retirada atual; uma versão congelada nunca volta a valer
    const pode_publicar = versao.situacao === "RASCUNHO" || versao.situacao === "RETIRADA";
    if (pode_publicar && !congelada) {
      linha.append(botao_das_kbs("Publicar", "botao-principal", function () {
        publicar_versao(kb.kb_id, versao.versao, true);
      }));
    }
    lista.append(linha);
  }
}

/**
 * Os botões do rodapé da janela: editar (versão nova), revisar a vigência e retirar a publicada.
 */
function montar_botoes_da_kb(kb) {
  const botoes = document.querySelector("[data-kb-botoes]");
  botoes.replaceChildren();
  // Versão congelada: nenhuma ação (a navegação do histórico fica na faixa de gelo, no alto)
  if (versao_esta_no_historico(kb, kb.versao)) {
    return;
  }
  // O histórico anterior: abre a mais recente das versões antigas, já congelada
  const historico = versoes_do_historico(kb);
  if (historico.length > 0) {
    const botao_do_historico = botao_das_kbs("Histórico anterior (" + historico.length + ")", "botao-contorno", function () {
      abrir_kb(kb.kb_id, historico[0].versao);
    });
    botao_do_historico.dataset.kbHistorico = "";
    botoes.append(botao_do_historico);
  }
  // Retirar só existe se alguma versão está publicada
  let tem_publicada = false;
  for (const versao of kb.versoes) {
    if (versao.situacao === "PUBLICADA") {
      tem_publicada = true;
    }
  }
  if (tem_publicada) {
    botoes.append(botao_das_kbs("Retirar", "botao-contorno", function () {
      pedir_confirmacao_das_kbs("Retirar esta KB?", "A versão publicada deixa de valer para a vitrine da empresa e para o agente. As versões ficam guardadas.",
        "Retirar", function () { return retirar_kb(kb.kb_id); });
    }));
  }
  botoes.append(botao_das_kbs("Revisar vigência", "botao-contorno", function () {
    document.querySelector("[data-kb-revisar]").hidden = false;
  }));
  botoes.append(botao_das_kbs("Editar (versão nova)", "botao-principal", function () {
    document.getElementById("janela-kb").close();
    abrir_editor(kb);
  }));
}

/**
 * Mostra a lista de achados da trava num elemento da tela (bloqueios e avisos, com o trecho).
 *
 * Recebe: lista (o <ul>); achados. Devolve: nada.
 */
function mostrar_achados(lista, achados) {
  lista.replaceChildren();
  for (const achado of achados) {
    const classe = achado.gravidade === "BLOQUEIA" ? "achado-bloqueia" : "achado-aviso";
    const linha = criar_elemento_das_kbs("li", classe, "");
    linha.append(criar_elemento_das_kbs("strong", "", achado.regra + ": "));
    linha.append(document.createTextNode(achado.detalhe));
    if (achado.trecho) {
      linha.append(criar_elemento_das_kbs("span", "achado-trecho", "“" + achado.trecho + "”"));
    }
    lista.append(linha);
  }
  lista.hidden = achados.length === 0;
}

// ---------------- 7. O editor ----------------

/**
 * Enche um <select> com as opções. Recebe: seletor; opcoes — [[valor, rótulo]]; escolhido. Devolve: nada.
 */
function encher_opcoes(seletor, opcoes, escolhido) {
  const campo = document.querySelector(seletor);
  campo.replaceChildren();
  for (const opcao of opcoes) {
    const elemento = criar_elemento_das_kbs("option", "", opcao[1]);
    elemento.value = opcao[0];
    elemento.selected = opcao[0] === escolhido;
    campo.append(elemento);
  }
}

/**
 * Os tipos que o dono pode ter (ex.: GERAL não tem benefício; empresa não tem tom de voz). Devolve [[tipo, nome]].
 */
function tipos_do_dono(dono) {
  const opcoes = [];
  for (const tipo of estado_das_kbs.modelos.tipos) {
    const empresa_pode = dono_e_empresa(dono) && tipo.donos.includes("EMPRESA");
    if (tipo.donos.includes(dono) || empresa_pode) {
      opcoes.push([tipo.tipo, tipo.nome]);
    }
  }
  return opcoes;
}

/**
 * O texto inicial do corpo de uma KB nova: o título e cada seção obrigatória do tipo, vazia.
 *
 * Exemplo (canais): "# Título\n\n## E-mail\n\n## Mural ou intranet\n\n## WhatsApp\n".
 */
function corpo_do_modelo(tipo, titulo) {
  let corpo = "# " + (titulo || "Título da KB") + "\n";
  for (const item of estado_das_kbs.modelos.tipos) {
    if (item.tipo === tipo) {
      for (const secao of item.secoes) {
        corpo = corpo + "\n## " + secao + "\n\n";
      }
    }
  }
  return corpo;
}

/**
 * Mostra só os campos do tipo escolhido (categoria no benefício; a escolha, as cores e o logo no kit).
 */
function mostrar_campos_do_tipo() {
  const tipo = document.querySelector('[data-editor-campo="tipo"]').value;
  for (const campo of document.querySelectorAll("[data-so-no-tipo]")) {
    campo.hidden = campo.dataset.soNoTipo !== tipo;
  }
  // O logo tem regra própria: só no kit de uma empresa (js/kit_da_marca.js)
  mostrar_bloco_do_logo();
}

/**
 * Troca o tipo (ou o dono) de uma KB nova: atualiza os campos e, se a pessoa ainda não escreveu, o modelo do corpo.
 */
function trocar_tipo_no_editor() {
  mostrar_campos_do_tipo();
  const corpo = document.querySelector("[data-editor-corpo]");
  // Só troca o corpo se ele ainda é o modelo (nunca apaga o que a pessoa escreveu)
  if (corpo.value === estado_das_kbs.corpo_do_modelo) {
    const tipo = document.querySelector('[data-editor-campo="tipo"]').value;
    estado_das_kbs.corpo_do_modelo = corpo_do_modelo(tipo, document.querySelector('[data-editor-campo="titulo"]').value);
    corpo.value = estado_das_kbs.corpo_do_modelo;
  }
}

/**
 * Abre o editor: vazio (KB nova, com o dono escolhido na tela) ou com a KB aberta (versão nova).
 *
 * Recebe: kb (ou null). Devolve: nada.
 */
function abrir_editor(kb) {
  estado_das_kbs.kb_editada = kb ? kb.kb_id : null;
  const dono = kb ? kb.dono : estado_das_kbs.dono;
  document.querySelector("[data-editor-titulo]").textContent = kb ? "Nova versão: " + kb.titulo : "Nova KB";
  // O dono é sempre o aberto na guia (a empresa, GERAL ou SANTANDER); o tipo é livre só numa KB nova
  const donos = [];
  for (const item of estado_das_kbs.modelos.donos) {
    donos.push([item.dono, item.nome]);
  }
  encher_opcoes('[data-editor-campo="dono"]', donos, dono);
  // O tipo que já vem escolhido: o da KB; numa KB nova, o da aba aberta (ex.: Benefícios)
  let tipo_escolhido = kb ? kb.tipo : null;
  if (!kb && estado_das_kbs.tipo !== "todos") {
    tipo_escolhido = estado_das_kbs.tipo;
  }
  encher_opcoes('[data-editor-campo="tipo"]', tipos_do_dono(dono), tipo_escolhido);
  document.querySelector('[data-editor-campo="dono"]').disabled = true;
  document.querySelector('[data-editor-campo="tipo"]').disabled = Boolean(kb);
  // As opções fixas: categorias e kits
  const categorias = [];
  for (const categoria of estado_das_kbs.modelos.categorias) {
    categorias.push([categoria, categoria]);
  }
  encher_opcoes('[data-editor-campo="categoria"]', categorias, kb ? kb.ficha.categoria : null);
  encher_opcoes('[data-editor-campo="kit_escolhido"]', [["proprio", "Kit próprio da empresa"], ["padrao", "Padrão Santander"]],
    kb ? kb.ficha.kit_escolhido : "proprio");
  // Os campos de texto da ficha
  const ficha = kb ? kb.ficha : {};
  const hoje = new Date().toISOString().slice(0, 10);
  const padroes = { titulo: "", vigencia_inicio: hoje, vigencia_fim: hoje.slice(0, 4) + "-12-31",
                    origem: "Exemplo criado para o case", prateleira: "", cores: "" };
  for (const chave of Object.keys(padroes)) {
    document.querySelector('[data-editor-campo="' + chave + '"]').value = ficha[chave] || padroes[chave];
  }
  // O corpo: o da KB, ou o modelo do tipo
  const corpo = document.querySelector("[data-editor-corpo]");
  estado_das_kbs.corpo_do_modelo = kb ? "" : corpo_do_modelo(document.querySelector('[data-editor-campo="tipo"]').value, "");
  corpo.value = kb ? kb.corpo : estado_das_kbs.corpo_do_modelo;
  // No kit da marca: as amostras das cores e o logo da versão de partida (js/kit_da_marca.js)
  mostrar_amostras_do_editor();
  preparar_logo_no_editor(kb);
  mostrar_campos_do_tipo();
  document.querySelector("[data-editor-erro]").hidden = true;
  document.querySelector("[data-editor-achados]").hidden = true;
  document.getElementById("janela-editor-kb").showModal();
}

/**
 * O formulário do editor como a API espera: { ficha, corpo }.
 */
function pedido_do_editor() {
  const ficha = {};
  for (const campo of document.querySelectorAll("[data-editor-campo]")) {
    // Campos escondidos (de outro tipo) vão vazios
    const escondido = campo.closest("[data-so-no-tipo]") && campo.closest("[data-so-no-tipo]").hidden;
    ficha[campo.dataset.editorCampo] = escondido ? "" : campo.value;
  }
  return { ficha: ficha, corpo: document.querySelector("[data-editor-corpo]").value };
}

/**
 * Mostra o erro do editor: a lista de achados (trava) ou a mensagem.
 */
function mostrar_erro_do_editor(detalhe) {
  const aviso = document.querySelector("[data-editor-erro]");
  aviso.textContent = texto_do_erro_das_kbs(detalhe);
  aviso.hidden = false;
  if (detalhe && detalhe.achados) {
    mostrar_achados(document.querySelector("[data-editor-achados]"), achados_para_o_editor(detalhe.achados));
  }
}

/**
 * "Conferir na trava": roda a trava sem gravar e mostra os achados (ou "tudo certo").
 */
async function conferir_no_editor() {
  let endereco = ENDERECO_DAS_KBS + "/verificar";
  if (estado_das_kbs.kb_editada) {
    endereco = endereco + "?kb_id=" + encodeURIComponent(estado_das_kbs.kb_editada);
  }
  const resposta = await postar_nas_kbs(endereco, pedido_do_editor());
  const aviso = document.querySelector("[data-editor-erro]");
  if (!resposta.ok) {
    mostrar_erro_do_editor(resposta.dados.detail);
    return;
  }
  // O aviso de "kit sem logo" sai quando o editor tem um logo para mandar junto (js/kit_da_marca.js)
  const achados = achados_para_o_editor(resposta.dados.achados);
  mostrar_achados(document.querySelector("[data-editor-achados]"), achados);
  // Sem achados, o recado de que está tudo certo; com achados, a própria lista já diz o que mudar
  aviso.textContent = "Tudo certo: a trava não apontou nada.";
  aviso.hidden = achados.length > 0;
}

/**
 * "Salvar rascunho": grava a KB nova (ou a versão nova), manda o logo do kit para ela e abre a KB salva.
 *
 * O botão fica desligado enquanto grava: dois cliques seguidos não criam dois rascunhos.
 */
async function salvar_no_editor() {
  const botao = document.querySelector("[data-editor-salvar]");
  botao.disabled = true;
  // try/finally: o botão volta a funcionar mesmo se algo der errado no meio
  try {
    await gravar_o_que_o_editor_tem();
  } finally {
    botao.disabled = false;
  }
}

/**
 * Grava o rascunho e, no kit de uma empresa, o logo da versão nova; depois fecha o editor e abre a versão salva.
 *
 * Recebe: nada (lê o editor). Devolve: nada. Se o servidor recusar a mudança do logo, o rascunho fica salvo com o
 * logo que herdou, e o motivo aparece na janela da versão (o "Editar (versão nova)" deixa tentar de novo).
 */
async function gravar_o_que_o_editor_tem() {
  let endereco = ENDERECO_DAS_KBS;
  if (estado_das_kbs.kb_editada) {
    endereco = endereco + "/" + encodeURIComponent(estado_das_kbs.kb_editada) + "/versoes";
  }
  const resposta = await postar_nas_kbs(endereco, pedido_do_editor());
  if (!resposta.ok) {
    mostrar_erro_do_editor(resposta.dados.detail);
    return;
  }
  const salva = resposta.dados;
  // O logo vai para a versão que acabou de nascer, antes de a janela dela abrir (js/kit_da_marca.js)
  const erro_do_logo = await gravar_logo_na_versao_nova(salva.kb_id, salva.versao);
  document.getElementById("janela-editor-kb").close();
  // O dono e a aba aberta continuam os mesmos; a lista e "Aguardando publicação" ganham a versão nova
  await recarregar_kbs();
  mostrar_aviso_das_kbs("Rascunho v" + salva.versao + " gravado. Ele só vale depois de publicado.");
  await abrir_kb(salva.kb_id, salva.versao);
  // A mudança do logo não foi aceita: o motivo fica à vista na janela da versão salva
  if (erro_do_logo) {
    mostrar_erro_na_janela("O rascunho v" + salva.versao + " foi salvo, mas a mudança do logo não: " + erro_do_logo +
      " Use \"Editar (versão nova)\" para tentar de novo.");
  }
}

// ---------------- 8. As ações: publicar, retirar e revisar ----------------

/**
 * Quando o servidor já aplicou a mudança na empresa (vitrine, catálogo do agente e kit), avisa a página: a guia do
 * material passa a oferecer os benefícios do catálogo novo. Para a pessoa, isso é transparente (sem mensagem).
 *
 * Recebe: aplicacao — o que o servidor devolveu (null quando a KB não muda o que a empresa vê). Devolve: nada.
 */
function avisar_que_a_empresa_mudou(aplicacao) {
  if (!aplicacao) {
    return;
  }
  document.dispatchEvent(new CustomEvent("kbs-aplicadas", { detail: { empresa_id: aplicacao.empresa_id } }));
}

/**
 * Mostra o erro de uma ação dentro da janela da KB (com os achados, se a trava bloqueou).
 */
function mostrar_erro_na_janela(detalhe) {
  const aviso = document.querySelector("[data-kb-erro]");
  aviso.textContent = texto_do_erro_das_kbs(detalhe);
  aviso.hidden = false;
  if (detalhe && detalhe.achados) {
    mostrar_achados(document.querySelector("[data-kb-achados]"), detalhe.achados);
  }
}

/**
 * Publica a versão (a trava roda de novo).
 *
 * Recebe: kb_id; versao; abrir_depois — true para mostrar a versão publicada na janela (quem publica pela janela);
 * false quando publica pela lista "Aguardando publicação". Devolve: nada.
 * Se a trava barrar, a janela da versão abre (ou continua aberta) com o motivo.
 */
async function publicar_versao(kb_id, versao, abrir_depois) {
  const endereco = ENDERECO_DAS_KBS + "/" + encodeURIComponent(kb_id) + "/versoes/" + versao + "/publicar";
  const resposta = await postar_nas_kbs(endereco, null);
  if (!resposta.ok) {
    // Publicada pela lista (janela fechada): abre a versão para o motivo aparecer nela
    if (!document.getElementById("janela-kb").open) {
      await abrir_kb(kb_id, versao);
    }
    mostrar_erro_na_janela(resposta.dados.detail);
    return;
  }
  await recarregar_kbs();
  mostrar_aviso_das_kbs("Versão " + versao + " publicada.");
  avisar_que_a_empresa_mudou(resposta.dados.aplicacao);
  if (abrir_depois) {
    abrir_kb(kb_id, versao);
  }
}

/**
 * Retira a versão publicada. Recebe: kb_id. Devolve: { ok, erro } para a janela de confirmação.
 */
async function retirar_kb(kb_id) {
  const resposta = await postar_nas_kbs(ENDERECO_DAS_KBS + "/" + encodeURIComponent(kb_id) + "/retirar", null);
  if (!resposta.ok) {
    return { ok: false, erro: texto_do_erro_das_kbs(resposta.dados.detail) };
  }
  await recarregar_kbs();
  mostrar_aviso_das_kbs("KB retirada: ela deixou de valer.");
  avisar_que_a_empresa_mudou(resposta.dados.aplicacao);
  abrir_kb(kb_id, null);
  return { ok: true };
}

/**
 * Revisa a vigência com a data escolhida na janela.
 */
async function revisar_kb_aberta() {
  const kb = estado_das_kbs.kb_aberta;
  const nova_data = document.querySelector("[data-kb-nova-vigencia]").value;
  const endereco = ENDERECO_DAS_KBS + "/" + encodeURIComponent(kb.kb_id) + "/revisar";
  const resposta = await postar_nas_kbs(endereco, { vigencia_fim: nova_data });
  if (!resposta.ok) {
    mostrar_erro_na_janela(resposta.dados.detail);
    return;
  }
  await recarregar_kbs();
  mostrar_aviso_das_kbs("Vigência renovada até " + data_das_kbs(nova_data) + ".");
  avisar_que_a_empresa_mudou(resposta.dados.aplicacao);
  abrir_kb(kb.kb_id, resposta.dados.kb.versao);
}

// ---------------- 9. A janela de confirmação ----------------

/**
 * Abre a janela de confirmação. O botão principal roda a ação (que devolve { ok, erro }).
 *
 * Recebe: titulo; texto; rotulo_do_botao; acao. Devolve: nada.
 */
function pedir_confirmacao_das_kbs(titulo, texto, rotulo_do_botao, acao) {
  const janela = document.getElementById("janela-confirmacao-kb");
  janela.querySelector("[data-confirmacao-titulo]").textContent = titulo;
  janela.querySelector("[data-confirmacao-texto]").textContent = texto;
  janela.querySelector("[data-confirmar-acao]").textContent = rotulo_do_botao;
  janela.querySelector("[data-confirmacao-erro]").hidden = true;
  estado_das_kbs.acao_confirmada = acao;
  janela.showModal();
}

/**
 * O clique em "confirmar": roda a ação e fecha a janela (ou mostra o erro nela).
 */
async function confirmar_acao_das_kbs() {
  const janela = document.getElementById("janela-confirmacao-kb");
  const resultado = await estado_das_kbs.acao_confirmada();
  if (!resultado.ok) {
    const aviso = janela.querySelector("[data-confirmacao-erro]");
    aviso.textContent = resultado.erro;
    aviso.hidden = false;
    return;
  }
  janela.close();
}

// ---------------- 10. O começo ----------------

/**
 * Liga os cliques fixos da página (filtros, nova KB, editor, janelas e confirmação).
 */
function ligar_cliques_das_kbs() {
  for (const botao of document.querySelectorAll("[data-filtro-kbs]")) {
    botao.addEventListener("click", function () {
      estado_das_kbs.filtro = botao.dataset.filtroKbs;
      for (const outro of document.querySelectorAll("[data-filtro-kbs]")) {
        outro.classList.toggle("filtro-rapido-ativo", outro === botao);
      }
      montar_lista_de_kbs();
    });
  }
  document.querySelector("[data-nova-kb]").addEventListener("click", function () {
    abrir_editor(null);
  });
  document.querySelector('[data-editor-campo="tipo"]').addEventListener("change", trocar_tipo_no_editor);
  // O kit da marca no editor: as amostras das cores a cada letra, e o logo (escolher o arquivo e tirar)
  document.querySelector('[data-editor-campo="cores"]').addEventListener("input", mostrar_amostras_do_editor);
  document.querySelector("[data-arquivo-logo-do-editor]").addEventListener("change", escolher_arquivo_de_logo);
  document.querySelector("[data-tirar-logo-do-editor]").addEventListener("click", tirar_logo_no_editor);
  document.querySelector("[data-editor-conferir]").addEventListener("click", conferir_no_editor);
  document.querySelector("[data-editor-salvar]").addEventListener("click", salvar_no_editor);
  document.querySelector("[data-kb-confirmar-revisao]").addEventListener("click", revisar_kb_aberta);
  // O "confirmar" da janela das KBs (a página tem outra janela de confirmação: a dos materiais)
  document.querySelector("#janela-confirmacao-kb [data-confirmar-acao]").addEventListener("click", confirmar_acao_das_kbs);
  // Todo "X" e todo "Cancelar" das janelas das KBs fecham a janela em que estão
  for (const botao of document.querySelectorAll("#janela-kb [data-fechar-janela], #janela-editor-kb [data-fechar-janela], #janela-confirmacao-kb [data-fechar-janela]")) {
    botao.addEventListener("click", function () {
      botao.closest("dialog").close();
    });
  }
}

/**
 * Carrega os modelos (os tipos, as categorias e os donos) uma vez só e liga os cliques fixos.
 *
 * Recebe: nada. Devolve: true se os modelos chegaram; false se não (o aviso já foi mostrado).
 */
async function preparar_modelos_das_kbs() {
  // Já carregados: nada a fazer
  if (estado_das_kbs.modelos) {
    return true;
  }
  const modelos = await pedir_as_kbs(ENDERECO_DAS_KBS + "/modelos");
  if (!modelos.ok) {
    mostrar_aviso_das_kbs(texto_do_erro_das_kbs(modelos.dados.detail));
    return false;
  }
  estado_das_kbs.modelos = modelos.dados;
  ligar_cliques_das_kbs();
  return true;
}

/**
 * Mostra as KBs de um dono: a empresa escolhida no topo (guia Base de Conhecimento) ou "GERAL"/"SANTANDER" (guia
 * Regras gerais). Quem chama é o js/banco_endomarketing.js, a cada empresa, guia ou grupo de regras escolhido.
 *
 * Recebe: dono — ex.: "EMP001" ou "GERAL". Devolve: nada (espera as respostas do servidor).
 */
async function abrir_kbs_do_dono(dono) {
  // Guarda quem foi pedido: se outro for escolhido no meio, a resposta antiga não é desenhada
  estado_das_kbs.dono = dono;
  // Enquanto as KBs dele não chegam, a guia fica sem as do dono anterior
  document.querySelector("[data-abas-tipos]").replaceChildren();
  document.querySelector("[data-lista-kbs]").replaceChildren();
  // A marca de "pronto" sai até as KBs deste dono chegarem (quem espera por ela, como os roteiros, espera de novo)
  document.querySelector("[data-lista-kbs]").removeAttribute("data-dado-pronto");
  document.querySelector("[data-lista-aguardando]").replaceChildren();
  document.querySelector("[data-sem-kbs]").hidden = true;
  const preparou = await preparar_modelos_das_kbs();
  if (!preparou || estado_das_kbs.dono !== dono) {
    return;
  }
  const resposta = await pedir_as_kbs(ENDERECO_DAS_KBS);
  if (estado_das_kbs.dono !== dono) {
    return;
  }
  if (!resposta.ok) {
    mostrar_aviso_das_kbs(texto_do_erro_das_kbs(resposta.dados.detail));
    return;
  }
  estado_das_kbs.kbs = resposta.dados.kbs;
  escolher_dono(dono);
}
