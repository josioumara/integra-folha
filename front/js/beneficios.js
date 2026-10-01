/*
  beneficios.js — filtros e busca da aba "Benefícios do seu time".

  Para que serve: mostra só os benefícios da categoria escolhida ("Conta e dia a dia", "Crédito"...) e que tenham o
  texto buscado no título ou no resumo. A janela de detalhes de cada benefício é do js/janela_beneficio.js (a mesma
  da home).
  A categoria de cada cartão fica em data-categoria, no HTML.
*/

// A categoria escolhida ("todas" = sem filtro).
let categoria_escolhida = "todas";

/**
 * Diz se um cartão de benefício deve aparecer com a categoria e a busca atuais.
 *
 * Recebe: cartao — o <article> do benefício; texto_buscado — a busca, em minúsculas.
 * Devolve: true se o cartão aparece.
 */
function beneficio_aparece(cartao, texto_buscado) {
  // Categoria: "todas" deixa passar qualquer uma.
  if (categoria_escolhida !== "todas" && cartao.dataset.categoria !== categoria_escolhida) {
    return false;
  }
  // Busca no título e no resumo do cartão.
  const texto_do_cartao = (cartao.querySelector(".beneficio-titulo").textContent + " " +
    cartao.querySelector(".beneficio-texto").textContent).toLowerCase();
  return texto_do_cartao.includes(texto_buscado);
}

/**
 * Esconde os cartões que não passam no filtro e mostra o aviso quando nenhum sobra.
 *
 * Recebe: nada. Devolve: nada.
 */
function filtrar_beneficios() {
  // O texto buscado, sem espaços nas pontas e em minúsculas.
  const texto_buscado = document.querySelector("[data-busca-beneficio]").value.trim().toLowerCase();
  let quantidade_na_tela = 0;
  for (const cartao of document.querySelectorAll("[data-grade-beneficios] .cartao-beneficio")) {
    const aparece = beneficio_aparece(cartao, texto_buscado);
    cartao.hidden = !aparece;
    if (aparece) {
      quantidade_na_tela = quantidade_na_tela + 1;
    }
  }
  // Nenhum cartão: aparece o aviso.
  document.querySelector("[data-sem-beneficios]").hidden = quantidade_na_tela > 0;
}

/**
 * Troca a categoria escolhida e refaz o filtro.
 *
 * Recebe: botao — o filtro clicado (a categoria fica em data-categoria-filtro). Devolve: nada.
 */
function escolher_categoria(botao) {
  categoria_escolhida = botao.dataset.categoriaFiltro;
  // Só o filtro clicado fica destacado.
  for (const outro of document.querySelectorAll("[data-categoria-filtro]")) {
    outro.classList.toggle("filtro-rapido-ativo", outro === botao);
  }
  filtrar_beneficios();
}

/**
 * Liga os filtros e a busca. É chamada quando a página termina de carregar.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_vitrine_de_beneficios() {
  for (const botao of document.querySelectorAll("[data-categoria-filtro]")) {
    botao.addEventListener("click", function () {
      escolher_categoria(botao);
    });
  }
  // A busca refaz o filtro a cada letra.
  document.querySelector("[data-busca-beneficio]").addEventListener("input", filtrar_beneficios);
}

// Espera o HTML carregar inteiro antes de ligar tudo.
document.addEventListener("DOMContentLoaded", preparar_vitrine_de_beneficios);
