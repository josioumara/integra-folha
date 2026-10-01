/*
  painel_da_conversa.js — a janela da conversa na tela "Acompanhar cadastros" (ADR-138).

  Para que serve: a lista das pendências mostra cartões compactos (o título, o problema, a pergunta do agente em até 2
  linhas e o arquivo). Ao clicar num cartão, a conversa com o Agente de validação abre numa janela por cima da tela (um
  <dialog>, a janela pronta do navegador, que escurece o fundo):
    - a conversa é a mesma de sempre (js/assistente_de_correcao.js): a pergunta, as respostas rápidas, a caixa, os
      botões do grupo, o "pessoa a pessoa", as confirmações e o Desfazer. As rotas e o agente também. Só mudou o lugar
      onde ela aparece;
    - o cartão escolhido fica marcado na lista (borda e fundo da marca);
    - resolvida pela conversa, a pendência continua aberta na janela, verde, com o "Pronto: ..." e o Desfazer, até a
      pessoa fechar;
    - no filtro "Resolvidas", o "Ver a conversa" também abre a conversa guardada na janela (só de leitura);
    - o X, o Esc e o clique fora da janela fecham a conversa (no celular, o "Voltar à lista");
    - quando a lista é refeita (depois de uma mudança feita pela conversa), a janela acompanha: mostra a conversa de novo
      com os dados novos, ou fecha se o cartão saiu da lista (ex.: o arquivo foi descartado).
  Com a janela aberta, a atualização automática da tela espera (js/acompanhar.js, pessoa_esta_no_meio_de_algo).
  No celular (tela até 1024 px), a janela ocupa a tela inteira (css/acompanhar_painel.css).

  Usa, do js/acompanhar.js: criar, recarregar_a_tela_inteira; do js/assistente_de_correcao.js:
  montar_cartao_da_pendencia, montar_conversa_resolvida.
*/

// O que está aberto na janela: null (nada; a janela está fechada) ou {tipo, chave}. O tipo é "pendencia" (um cartão da
// lista das abertas) ou "resolvida" (um cartão do filtro "Resolvidas"); a chave é a da conversa ("envio|regra|linha").
// Ex.: {tipo: "pendencia", chave: "env-1|CPF_INVALIDO|5"}.
let aberta_no_painel = null;

// O celular (e o tablet): até esta largura, a janela ocupa a tela inteira (a mesma do css/acompanhar_painel.css).
const LARGURA_DA_TELA_CHEIA = "(max-width: 1024px)";

/**
 * A janela da conversa (o <dialog> do acompanhar.html).
 *
 * Recebe: nada. Devolve: o elemento.
 */
function janela_da_conversa() {
  return document.querySelector("[data-painel-da-conversa]");
}

// ===== Achar os cartões da lista =====

/**
 * O seletor dos cartões de um tipo: as pendências abertas ou as resolvidas.
 *
 * Recebe: tipo — "pendencia" ou "resolvida". Devolve: o seletor CSS. Ex.: "resolvida" → "[data-resolvida]".
 */
function seletor_dos_cartoes(tipo) {
  if (tipo === "resolvida") {
    return "[data-resolvida]";
  }
  return "[data-pendencia]";
}

/**
 * O cartão da lista cuja conversa está aberta na janela.
 *
 * Recebe: nada. Devolve: o elemento do cartão, ou null (nada aberto, ou o cartão não está mais na lista).
 */
function cartao_aberto_no_painel() {
  // Nada aberto: não há cartão escolhido
  if (aberta_no_painel === null) {
    return null;
  }
  // Procura, entre os cartões do mesmo tipo (abertas ou resolvidas), o que tem a chave da conversa aberta
  for (const cartao of document.querySelectorAll(seletor_dos_cartoes(aberta_no_painel.tipo))) {
    if (cartao.dataset.chavePendencia === aberta_no_painel.chave) {
      return cartao;
    }
  }
  // Nenhum tem a chave: o cartão saiu da lista (ex.: o arquivo foi descartado)
  return null;
}

/**
 * Marca na lista o cartão cuja conversa está aberta (e tira a marca dos outros).
 *
 * Recebe: nada. Devolve: nada.
 */
function marcar_o_cartao_escolhido() {
  const escolhido = cartao_aberto_no_painel();
  for (const cartao of document.querySelectorAll("[data-pendencia], [data-resolvida]")) {
    const e_o_escolhido = cartao === escolhido;
    cartao.classList.toggle("ajuste-escolhido", e_o_escolhido);
    // Quem usa leitor de tela ouve qual cartão está aberto
    if (e_o_escolhido) {
      cartao.setAttribute("aria-current", "true");
    } else {
      cartao.removeAttribute("aria-current");
    }
  }
}

// ===== Abrir e fechar =====

/**
 * Mostra o cartão da conversa na janela, e abre a janela se ela estava fechada.
 *
 * Recebe: titulo — o título do ajuste (vai para o alto da janela); partes — os elementos do cartão; resolvida —
 * true quando a pendência já foi resolvida (a faixa verde, sem a caixa e as respostas rápidas).
 * Devolve: nada.
 */
function mostrar_no_painel(titulo, partes, resolvida) {
  // O cartão da conversa, com a mesma cara dos cartões de pendência (css/estilos.css e css/acompanhar_painel.css)
  const cartao = criar("div", "ajuste ajuste-no-painel", "");
  cartao.classList.toggle("ajuste-resolvido", resolvida);
  cartao.append(...partes);
  document.querySelector("[data-titulo-da-conversa]").textContent = titulo;
  document.querySelector("[data-corpo-da-conversa]").replaceChildren(cartao);
  // A janela abre por cima da tela (já aberta, ela só troca o conteúdo: a lista pode ter sido refeita)
  const janela = janela_da_conversa();
  if (!janela.open) {
    janela.showModal();
  }
  // No celular, a janela ocupa a tela inteira e a página de trás não rola
  document.body.classList.toggle("conversa-em-tela-cheia", window.matchMedia(LARGURA_DA_TELA_CHEIA).matches);
  marcar_o_cartao_escolhido();
}

/**
 * Tira o título do cabeçalho do cartão que vai para a janela (o título já fica no alto dela, em letra maior).
 *
 * Recebe: partes — os elementos do cartão. Devolve: o texto do título ("" se não houver).
 * O resto do cabeçalho fica (ex.: o selo "Pedido do banco" e o botão da ficha).
 */
function tirar_o_titulo_do_cabecalho(partes) {
  let titulo = "";
  for (const parte of partes) {
    // Só o cabeçalho tem o título; as outras partes (o problema, a conversa, o arquivo) ficam como estão
    if (!parte.classList.contains("ajuste-cabecalho")) {
      continue;
    }
    const titulo_do_cartao = parte.querySelector(".ajuste-titulo");
    // Achou o título: guarda o texto e tira o elemento (ele vai para o alto da janela, e não se repete)
    if (titulo_do_cartao) {
      titulo = titulo_do_cartao.textContent;
      titulo_do_cartao.remove();
    }
  }
  return titulo;
}

/**
 * As partes que vão para a janela: todas, menos o cabeçalho que ficou vazio sem o título.
 *
 * Recebe: partes. Devolve: a lista nova, sem o cabeçalho vazio.
 */
function partes_que_ficam(partes) {
  const ficam = [];
  for (const parte of partes) {
    // O cabeçalho que ficou sem nada (sem o título, sem selo e sem o botão da ficha) não vai
    const cabecalho_vazio = parte.classList.contains("ajuste-cabecalho") && parte.children.length === 0;
    if (!cabecalho_vazio) {
      ficam.push(parte);
    }
  }
  return ficam;
}

/**
 * Mostra na janela a conversa de uma pendência aberta (ou resolvida há pouco, ainda à vista na lista).
 *
 * Recebe: cartao — o cartão compacto da lista (traz a pendência em cartao.pendencia_do_cartao). Devolve: nada.
 * A conversa é montada de novo a partir da pendência: o que já foi dito está guardado na página, pela chave
 * (js/assistente_de_correcao.js), e volta igual.
 */
function mostrar_a_pendencia_no_painel(cartao) {
  const partes = montar_cartao_da_pendencia(cartao.pendencia_do_cartao, recarregar_a_tela_inteira);
  const titulo = tirar_o_titulo_do_cabecalho(partes);
  const resolvida = cartao.hasAttribute("data-resolvido-a-vista");
  // Resolvida há pouco: o selo "✓ Resolvida" também na janela
  const partes_do_painel = partes_que_ficam(partes);
  if (resolvida) {
    partes_do_painel.unshift(criar("span", "selo-resolvida", "✓ Resolvida"));
  }
  mostrar_no_painel(titulo, partes_do_painel, resolvida);
}

/**
 * Mostra na janela a conversa guardada de uma pendência já resolvida (filtro "Resolvidas"), só de leitura.
 *
 * Recebe: cartao — o cartão da lista das resolvidas (traz a resolvida em cartao.resolvida). Devolve: nada.
 */
function mostrar_a_resolvida_no_painel(cartao) {
  const resolvida = cartao.resolvida;
  // O que mudou e quem resolveu, quando (os mesmos textos do cartão da lista)
  const resumo = criar("p", "resumo-da-resolvida", resolvida.resumo);
  const quem_e_quando = cartao.querySelector(".quem-resolveu").cloneNode(true);
  // A conversa guardada no servidor, com o Desfazer quando ainda dá para desfazer
  const conversa = montar_conversa_resolvida(resolvida, recarregar_a_tela_inteira);
  mostrar_no_painel(resolvida.titulo, [resumo, quem_e_quando, conversa], true);
}

/**
 * Abre na janela a conversa de um cartão da lista (e marca o cartão como o escolhido).
 *
 * Recebe: cartao — um cartão das abertas ([data-pendencia]) ou das resolvidas ([data-resolvida]). Devolve: nada.
 */
function abrir_a_conversa_do_cartao(cartao) {
  if (cartao.hasAttribute("data-resolvida")) {
    aberta_no_painel = { tipo: "resolvida", chave: cartao.dataset.chavePendencia };
    mostrar_a_resolvida_no_painel(cartao);
  } else {
    aberta_no_painel = { tipo: "pendencia", chave: cartao.dataset.chavePendencia };
    mostrar_a_pendencia_no_painel(cartao);
  }
  // No computador, o cursor vai para a caixa da conversa (a pessoa já pode responder); no celular, o teclado
  // abriria sozinho por cima da pergunta, então o foco fica no "Voltar à lista"
  focar_a_conversa();
}

/**
 * Põe o foco no lugar certo da conversa que acabou de abrir.
 *
 * Recebe: nada. Devolve: nada.
 */
function focar_a_conversa() {
  // Os botões procurados dentro da janela (a conversa do "Posso ajudar?" tem outro X com a mesma marca)
  const janela = janela_da_conversa();
  if (window.matchMedia(LARGURA_DA_TELA_CHEIA).matches) {
    janela.querySelector("[data-voltar-a-lista]").focus();
    return;
  }
  const caixa = document.querySelector("[data-corpo-da-conversa] [data-caixa-da-conversa]");
  // A resolvida não tem caixa: o foco vai para o X
  if (caixa && !caixa.disabled && caixa.offsetParent !== null) {
    caixa.focus();
  } else {
    janela.querySelector("[data-fechar-conversa]").focus();
  }
}

/**
 * Fecha a conversa: a janela fecha, e nenhum cartão fica marcado.
 *
 * Recebe: devolver_o_foco — true quando a PESSOA fechou (o X, o Esc, o clique fora ou o "Voltar à lista"): o foco
 * volta ao "Abrir a conversa" do cartão que estava aberto, e quem usa o teclado continua de onde parou. Quando é a tela
 * que fecha (o cartão saiu da lista), o foco fica onde está. Devolve: nada.
 * A mensagem digitada e ainda não enviada não se perde: a conversa guarda o rascunho pela chave a cada letra
 * (js/assistente_de_correcao.js), e ele volta quando a pessoa abrir o mesmo cartão de novo.
 */
function fechar_a_conversa(devolver_o_foco) {
  // O cartão que estava aberto, antes de esquecer qual era (é para ele que o foco volta)
  const cartao = cartao_aberto_no_painel();
  // Esquecer primeiro: o aviso "close" da janela, que vem a seguir, vê que a tela já cuidou de tudo
  aberta_no_painel = null;
  const janela = janela_da_conversa();
  if (janela.open) {
    janela.close();
  }
  // A conversa sai da janela
  document.querySelector("[data-corpo-da-conversa]").replaceChildren();
  // No celular, a página de trás volta a rolar
  document.body.classList.remove("conversa-em-tela-cheia");
  // Nenhum cartão fica marcado na lista
  marcar_o_cartao_escolhido();
  // Quem fechou foi a pessoa: o foco volta ao botão do cartão
  if (devolver_o_foco === true && cartao) {
    const botao = cartao.querySelector("[data-abrir-conversa]");
    if (botao) {
      botao.focus();
    }
  }
}

/**
 * "Voltar à lista" (celular): fecha a conversa e leva a pessoa de volta ao cartão em que ela estava.
 *
 * Recebe: nada. Devolve: nada.
 */
function voltar_a_lista() {
  const cartao = cartao_aberto_no_painel();
  fechar_a_conversa(true);
  if (cartao) {
    cartao.scrollIntoView({ block: "center" });
  }
}

// ===== A janela acompanha a lista =====

/**
 * Depois que a lista das pendências é refeita, a janela acompanha: a conversa aberta é montada de novo com os dados
 * novos, ou fecha se o cartão dela saiu da lista.
 *
 * Recebe: nada. Devolve: nada.
 * Ex.: o agente corrigiu o CPF → a pendência continua à vista, verde, e a janela mostra o "Pronto" e o Desfazer; o
 * arquivo foi descartado → o cartão sumiu, e a janela fecha.
 */
function refazer_o_painel_depois_da_lista() {
  if (aberta_no_painel === null) {
    return;
  }
  const cartao = cartao_aberto_no_painel();
  // O cartão saiu da lista (ou ficou escondido pelos filtros): a conversa fecha
  if (cartao === null || cartao.hidden) {
    fechar_a_conversa(false);
    return;
  }
  if (aberta_no_painel.tipo === "resolvida") {
    mostrar_a_resolvida_no_painel(cartao);
  } else {
    mostrar_a_pendencia_no_painel(cartao);
  }
}

/**
 * Fecha a conversa se o cartão dela saiu da lista ou foi escondido (ex.: a lista foi para o filtro "Resolvidas", ou o
 * filtro de arquivo mudou).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_se_o_cartao_escolhido_saiu() {
  if (aberta_no_painel === null) {
    return;
  }
  const cartao = cartao_aberto_no_painel();
  // A lista à vista pode estar escondida inteira (o filtro mostra a outra)
  const lista = cartao && cartao.closest("[data-lista-pendencias], [data-lista-resolvidas]");
  if (cartao === null || cartao.hidden || (lista && lista.hidden)) {
    fechar_a_conversa(false);
    return;
  }
  marcar_o_cartao_escolhido();
}

// ===== Ligar tudo =====

/**
 * O clique num cartão da lista abre a conversa dele na janela.
 *
 * Recebe: evento — o clique na lista. Devolve: nada.
 * Os botões e os links de dentro do cartão (ex.: "Ver a ficha completa") fazem só o que eles fazem; o "Abrir a
 * conversa" e o resto do cartão abrem a conversa.
 */
function ao_clicar_num_cartao(evento) {
  const cartao = evento.target.closest("[data-pendencia], [data-resolvida]");
  // Fora de um cartão, ou num cartão de exemplo do protótipo (aberto sem servidor, com a conversa dentro dele)
  if (!cartao || (!cartao.pendencia_do_cartao && !cartao.resolvida)) {
    return;
  }
  const botao_ou_link = evento.target.closest("button, a");
  const e_o_abrir_a_conversa = botao_ou_link && botao_ou_link.hasAttribute("data-abrir-conversa");
  // Outro botão do cartão: não abre a conversa
  if (botao_ou_link && !e_o_abrir_a_conversa) {
    return;
  }
  abrir_a_conversa_do_cartao(cartao);
}

/**
 * Liga a janela da conversa: o clique nos cartões, o X, o "Voltar à lista", o clique fora da janela e o Esc.
 *
 * Recebe: nada. Devolve: nada. Chamada uma vez, pelo iniciar_a_tela (js/acompanhar.js).
 */
function preparar_a_janela_da_conversa() {
  // Os cartões das abertas e das resolvidas (a escuta fica em cada lista: o clique "sobe" do cartão até ela)
  for (const lista of document.querySelectorAll("[data-lista-pendencias], [data-lista-resolvidas]")) {
    lista.addEventListener("click", ao_clicar_num_cartao);
  }
  const janela = janela_da_conversa();
  // O X de dentro da janela (a conversa do "Posso ajudar?" tem outro X com a mesma marca): a pessoa fechou, e o foco
  // volta ao cartão
  janela.querySelector("[data-fechar-conversa]").addEventListener("click", function () {
    fechar_a_conversa(true);
  });
  janela.querySelector("[data-voltar-a-lista]").addEventListener("click", voltar_a_lista);
  // O clique no fundo escurecido cai na própria janela (fora do conteúdo): fecha, como as outras janelas da tela
  janela.addEventListener("click", function (evento) {
    if (evento.target === janela) {
      fechar_a_conversa(true);
    }
  });
  // O Esc fecha a janela pelo próprio navegador: aqui a tela arruma o resto (a marca do cartão e o foco). Quando foi a
  // tela que fechou (fechar_a_conversa), a conversa já foi esquecida, e não há nada a fazer. O aviso "close" chega um
  // instante depois de a janela fechar: se nesse meio-tempo outra conversa abriu (a janela está aberta de novo), ele
  // não fecha a conversa nova.
  janela.addEventListener("close", function () {
    if (aberta_no_painel !== null && !janela.open) {
      fechar_a_conversa(true);
    }
  });
}
