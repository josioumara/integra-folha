/*
  menu_configuracao.js — o menu da engrenagem "Sistema" (o antigo "Configuração"), no alto de todas as telas do Portal
  Interno.

  Para que serve: a engrenagem (ao lado do nome de quem entrou) é um botão que abre um menu pequeno com as telas do
  Sistema (ADR-148):
    - Parâmetros do layout (banco_parametros.html): o layout do arquivo que o banco quer receber;
    - Acompanhamento dos agentes (banco_agentes.html): o trabalho, a qualidade e o custo dos agentes de IA;
    - Teto de custo com agentes (banco_teto_da_ia.html): o gasto com os agentes no dia e no mês, e os dois tetos.
  As Premissas financeiras (banco_premissas.html) ficam ocultas nesta versão (ADR-148): o item continua no HTML de cada
  tela, dentro de uma caixa <template> que o navegador guarda sem mostrar. Por isso as setas do teclado andam só entre
  os itens à vista: a busca pelos links (querySelectorAll) não entra na caixa.
  O nome deste arquivo e das classes (menu-configuracao, botao-configuracao) ficou o antigo; o que a pessoa vê é
  "Sistema".
  Este arquivo só abre e fecha o menu:
    - clique no botão (ou Enter / Espaço, que o navegador já trata como clique num <button>) abre ou fecha;
    - seta para baixo no botão abre o menu e põe o foco no primeiro item; dentro do menu, as setas andam entre os itens;
    - Esc fecha e devolve o foco ao botão; clicar fora do menu, ou sair dele com o Tab, também fecha.
  O botão diz aos leitores de tela se o menu está aberto (aria-expanded) e qual lista ele controla (aria-controls).

  É um "menu de navegação que abre e fecha" (no jargão, um disclosure): os itens são links comuns, e cada um leva à
  sua tela. Nas telas do Sistema, o HTML já vem com o botão marcado e o item da tela atual com aria-current="page".
*/

/**
 * Diz se o menu do Sistema está aberto agora.
 *
 * Recebe: botao — o botão da engrenagem. Devolve: true se o menu está aberto.
 */
function menu_de_configuracao_esta_aberto(botao) {
  // O próprio botão guarda a situação do menu (aria-expanded="true" quando aberto).
  return botao.getAttribute("aria-expanded") === "true";
}

/**
 * Abre o menu do Sistema.
 *
 * Recebe: botao — o botão da engrenagem; lista — a lista dos itens. Devolve: nada.
 */
function abrir_menu_de_configuracao(botao, lista) {
  // A lista aparece embaixo do botão.
  lista.hidden = false;
  // O botão avisa os leitores de tela que o menu abriu.
  botao.setAttribute("aria-expanded", "true");
}

/**
 * Fecha o menu do Sistema.
 *
 * Recebe: botao — o botão da engrenagem; lista — a lista dos itens. Devolve: nada.
 */
function fechar_menu_de_configuracao(botao, lista) {
  // A lista some.
  lista.hidden = true;
  // O botão avisa os leitores de tela que o menu fechou.
  botao.setAttribute("aria-expanded", "false");
}

/**
 * Leva o foco para outro item do menu, com as setas do teclado (do último, a seta para baixo volta ao primeiro).
 *
 * Recebe: lista — a lista dos itens; passo — 1 (seta para baixo) ou -1 (seta para cima). Devolve: nada.
 * Ex.: com o foco no 1º item, passo 1 leva ao 2º; com o foco no botão (fora da lista), passo 1 leva ao 1º.
 */
function mover_o_foco_no_menu_de_configuracao(lista, passo) {
  // Os links do menu, na ordem da tela (os de um item oculto, dentro de <template>, não entram: ADR-148).
  const itens = Array.from(lista.querySelectorAll("a"));
  // Onde o foco está agora (-1 quando ele não está em nenhum item, ex.: no botão).
  const posicao_atual = itens.indexOf(document.activeElement);
  // A próxima posição: com o foco fora da lista, a seta para baixo vai ao primeiro e a seta para cima ao último.
  let proxima_posicao = posicao_atual + passo;
  if (posicao_atual === -1 && passo < 0) {
    proxima_posicao = itens.length - 1;
  }
  // Passou do fim: volta ao começo; passou do começo: vai para o fim (o menu "dá a volta").
  if (proxima_posicao >= itens.length) {
    proxima_posicao = 0;
  }
  if (proxima_posicao < 0) {
    proxima_posicao = itens.length - 1;
  }
  itens[proxima_posicao].focus();
}

/**
 * Prepara o menu da engrenagem: liga o clique no botão, o teclado, o clique fora e a saída com o Tab.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar. Tela sem o menu: nada muda.
 */
function preparar_menu_de_configuracao() {
  // O menu inteiro (botão + lista); uma tela sem ele não tem o que preparar.
  const menu = document.querySelector("[data-menu-configuracao]");
  if (!menu) {
    return;
  }
  const botao = menu.querySelector("[data-botao-configuracao]");
  const lista = menu.querySelector("[data-itens-configuracao]");

  // Clique no botão (ou Enter / Espaço): abre se estava fechado; fecha se estava aberto.
  botao.addEventListener("click", function () {
    if (menu_de_configuracao_esta_aberto(botao)) {
      fechar_menu_de_configuracao(botao, lista);
      return;
    }
    abrir_menu_de_configuracao(botao, lista);
  });

  // Teclado dentro do menu (no botão ou num item).
  menu.addEventListener("keydown", function (evento) {
    // Esc: fecha e devolve o foco ao botão, para a pessoa não se perder na página.
    if (evento.key === "Escape" && menu_de_configuracao_esta_aberto(botao)) {
      evento.preventDefault();
      fechar_menu_de_configuracao(botao, lista);
      botao.focus();
      return;
    }
    // Seta para baixo: abre o menu (se preciso) e vai ao próximo item.
    if (evento.key === "ArrowDown") {
      evento.preventDefault();
      abrir_menu_de_configuracao(botao, lista);
      mover_o_foco_no_menu_de_configuracao(lista, 1);
      return;
    }
    // Seta para cima: abre o menu (se preciso) e vai ao item anterior.
    if (evento.key === "ArrowUp") {
      evento.preventDefault();
      abrir_menu_de_configuracao(botao, lista);
      mover_o_foco_no_menu_de_configuracao(lista, -1);
    }
  });

  // Clique em qualquer lugar fora do menu: fecha.
  document.addEventListener("click", function (evento) {
    if (!menu.contains(evento.target)) {
      fechar_menu_de_configuracao(botao, lista);
    }
  });

  // O foco saiu do menu (ex.: Tab depois do último item): fecha. relatedTarget é o elemento que recebeu o foco.
  menu.addEventListener("focusout", function (evento) {
    if (evento.relatedTarget && !menu.contains(evento.relatedTarget)) {
      fechar_menu_de_configuracao(botao, lista);
    }
  });
}

// Quando o HTML terminar de carregar, prepara o menu da engrenagem.
document.addEventListener("DOMContentLoaded", preparar_menu_de_configuracao);
