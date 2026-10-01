/*
  novo_envio.js — o botão "Cadastrar funcionários", sempre à mão, em todas as páginas do Portal Empresa.

  Para que serve: mandar funcionários é o foco do portal. O botão fica no
  canto da tela (o "Posso ajudar?" fica no cabeçalho) e abre uma janela por cima da página
  com o envio que já conhecemos: escolher o arquivo, a IA ler, conferir as colunas. Ao aceitar as colunas, a pessoa
  vai para "Acompanhar cadastros", onde as pendências são resolvidas e o envio vai ao banco.
    - Cada clique abre a janela do zero ("resetada"), esperando um envio novo.
    - Os links antigos para a tela de envio ("Continuar este envio", "Enviar uma alteração") abrem a mesma janela.
  A janela carrega a própria tela de envio (cadastrar.html?em_janela=1) num quadro (iframe): tudo o que já funciona
  lá continua igual, sem código repetido.
*/

// O endereço da tela de envio dentro da janela.
const ENDERECO_DO_ENVIO_EM_JANELA = "cadastrar.html?em_janela=1";

/**
 * Cria a janela do envio (escondida) e devolve o <dialog>.
 *
 * Recebe: nada. Devolve: a janela.
 */
function criar_janela_do_envio() {
  const janela = document.createElement("dialog");
  janela.className = "janela-novo-envio";
  janela.setAttribute("aria-label", "Cadastrar funcionários");
  // O cabeçalho da janela: título e o botão de fechar.
  const cabecalho = document.createElement("div");
  cabecalho.className = "janela-novo-envio-cabecalho";
  const titulo = document.createElement("h2");
  titulo.className = "janela-titulo";
  titulo.textContent = "Cadastrar funcionários";
  const fechar = document.createElement("button");
  fechar.type = "button";
  fechar.className = "botao-fechar-janela";
  fechar.setAttribute("aria-label", "Fechar");
  fechar.textContent = "×";
  fechar.addEventListener("click", function () {
    fechar_janela_do_envio(janela);
  });
  cabecalho.append(titulo, fechar);
  // O quadro com a tela de envio.
  const quadro = document.createElement("iframe");
  quadro.className = "janela-novo-envio-quadro";
  quadro.title = "Envio do arquivo de funcionários";
  janela.append(cabecalho, quadro);
  // Fechar pelo Esc também limpa o quadro.
  janela.addEventListener("close", function () {
    quadro.src = "about:blank";
    // Avisa a tela de trás que a janela fechou: um envio pode ter entrado (ex.: Acompanhar cadastros refaz os
    // números e as listas, js/acompanhar.js). Tela que não escuta este aviso simplesmente o ignora.
    document.dispatchEvent(new CustomEvent("janela-do-envio-fechada"));
  });
  document.body.append(janela);
  return janela;
}

/**
 * Abre a janela do envio do zero; com um envio já começado, abre nele.
 *
 * Recebe: janela; processamento_id — o envio a continuar, ou nada para um envio novo. Devolve: nada.
 */
function abrir_janela_do_envio(janela, processamento_id) {
  let endereco = ENDERECO_DO_ENVIO_EM_JANELA;
  if (processamento_id) {
    endereco = endereco + "&envio=" + encodeURIComponent(processamento_id);
  }
  // A hora no endereço obriga o navegador a carregar a tela de novo (nada do envio anterior sobra)
  janela.querySelector("iframe").src = endereco + "&aberta=" + Date.now();
  janela.showModal();
}

/**
 * Fecha a janela do envio e esvazia o quadro.
 *
 * Recebe: janela. Devolve: nada.
 */
function fechar_janela_do_envio(janela) {
  janela.close();
}

/**
 * Transforma o botão do canto da tela em "Cadastrar funcionários".
 *
 * Recebe: botao — o botão flutuante; janela. Devolve: nada.
 */
function preparar_botao_do_canto(botao, janela) {
  botao.classList.add("botao-cadastrar-funcionarios");
  botao.setAttribute("aria-label", "Cadastrar funcionários");
  // O desenho de "pessoa com +", o mesmo do antigo item do menu
  botao.innerHTML = '<svg class="icone" viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="4"/>' +
    '<path d="M2 21c0-4 3-6 7-6s7 2 7 6"/><path d="M19 8v6M16 11h6"/></svg>' +
    '<span class="assistente-texto">Cadastrar funcionários</span>';
  botao.addEventListener("click", function () {
    abrir_janela_do_envio(janela, null);
  });
}

/**
 * Faz os links para a tela de envio abrirem a janela (com o envio do link, quando houver).
 *
 * Recebe: janela. Devolve: nada.
 */
function desviar_links_para_a_janela(janela) {
  document.addEventListener("click", function (evento) {
    const link = evento.target.closest("a[href^='cadastrar.html']");
    if (!link) {
      return;
    }
    evento.preventDefault();
    // "cadastrar.html?envio=abc" → continua o envio abc
    const parametros = new URLSearchParams(link.getAttribute("href").split("?")[1] || "");
    abrir_janela_do_envio(janela, parametros.get("envio"));
  });
}

/**
 * Liga o botão do canto e os links. Na própria tela de envio (ou dentro da janela), não faz nada.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_novo_envio() {
  const botao = document.querySelector(".assistente-flutuante");
  if (!botao) {
    return;
  }
  const janela = criar_janela_do_envio();
  preparar_botao_do_canto(botao, janela);
  desviar_links_para_a_janela(janela);
}

// Quando o HTML terminar de carregar, prepara o botão.
document.addEventListener("DOMContentLoaded", preparar_novo_envio);
