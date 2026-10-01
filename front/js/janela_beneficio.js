/*
  janela_beneficio.js — a janela de detalhes dos benefícios, usada na home e na aba "Benefícios do seu time".

  Para que serve: faz a janela de detalhes dos benefícios funcionar.
    - Clicou em "Ver detalhes" num cartão → a janela abre com os dados DAQUELE benefício.
    - Clicou em "Voltar", no X ou fora da janela, ou apertou Esc → a janela fecha.
  Da janela, a pessoa do RH pode seguir para "Ver materiais para divulgar", que abre a aba de endomarketing com os
  materiais que o Santander preparou (a empresa não cria material: ADR-115). O link é fixo, no HTML.

  Como os dados chegam na janela (sem repetir texto no código):
    cada cartão já tem o ícone, o título, o resumo e uma lista escondida com os detalhes.
    A função abaixo COPIA essas partes do cartão clicado para dentro da janela.
    Para criar um benefício novo, basta acrescentar um cartão no HTML.
*/

/**
 * Abre a janela com os detalhes do benefício de um cartão.
 *
 * Recebe: cartao_do_beneficio — o <article> do cartão clicado.
 * Devolve: nada; só mostra a janela na tela.
 * Exemplo: clicar em "Ver detalhes" no cartão "Salário antecipado" abre a janela com
 *          o título "Salário antecipado" e os blocos "Como funciona", "Quem pode usar" e "Como contratar".
 */
function abrir_detalhes_do_beneficio(cartao_do_beneficio) {
  // A janela (<dialog>) que fica no fim da página.
  const janela = document.getElementById("janela-beneficio");

  // Copia o ícone do cartão para o alto da janela.
  const icone_do_cartao = cartao_do_beneficio.querySelector(".beneficio-icone");
  document.getElementById("janela-beneficio-icone").innerHTML = icone_do_cartao.innerHTML;

  // Copia o título do benefício.
  const titulo_do_cartao = cartao_do_beneficio.querySelector(".beneficio-titulo");
  document.getElementById("janela-beneficio-titulo").textContent = titulo_do_cartao.textContent;

  // Copia o resumo (o texto curto que aparece no cartão).
  const resumo_do_cartao = cartao_do_beneficio.querySelector(".beneficio-texto");
  document.getElementById("janela-beneficio-resumo").textContent = resumo_do_cartao.textContent;

  // Copia a lista de detalhes que estava escondida no cartão.
  const detalhes_do_cartao = cartao_do_beneficio.querySelector(".beneficio-detalhes");
  document.getElementById("janela-beneficio-detalhes").innerHTML = detalhes_do_cartao.innerHTML;

  // Abre a janela por cima da página, escurecendo o fundo.
  janela.showModal();
}

/**
 * Fecha a janela de detalhes.
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_detalhes_do_beneficio() {
  // Fecha a janela (a tecla Esc já faz isso sozinha, pelo próprio navegador).
  document.getElementById("janela-beneficio").close();
}

/**
 * Fecha a janela quando a pessoa clica no fundo escurecido, fora do conteúdo.
 *
 * Recebe: evento — o "aviso" do navegador sobre o clique.
 * Devolve: nada.
 * Por que funciona: clicando no fundo, o alvo do clique é a própria janela;
 * clicando no conteúdo, o alvo é algo DENTRO dela (um texto, um botão).
 */
function fechar_ao_clicar_fora(evento) {
  // A janela de detalhes.
  const janela = document.getElementById("janela-beneficio");
  // Só fecha se o clique foi no fundo, e não no conteúdo.
  if (evento.target === janela) {
    fechar_detalhes_do_beneficio();
  }
}

/**
 * Liga os botões da página às funções acima.
 *
 * Recebe: nada. Devolve: nada.
 * É chamada uma vez, quando a página termina de carregar.
 */
function preparar_janela_de_beneficios() {
  // Todos os botões "Ver detalhes" dos cartões.
  const botoes_ver_detalhes = document.querySelectorAll(".botao-ver-detalhes");
  // Todos os botões que fecham a janela ("Voltar" e o X).
  const botoes_de_fechar = document.querySelectorAll("[data-fechar-janela]");

  // Para cada "Ver detalhes", abre a janela com o cartão onde o botão está.
  for (const botao of botoes_ver_detalhes) {
    botao.addEventListener("click", function () {
      // closest sobe na página até achar o cartão que contém este botão.
      abrir_detalhes_do_beneficio(botao.closest(".cartao-beneficio"));
    });
  }

  // Cada botão de fechar fecha a janela.
  for (const botao of botoes_de_fechar) {
    botao.addEventListener("click", fechar_detalhes_do_beneficio);
  }

  // Clique no fundo escurecido também fecha.
  document.getElementById("janela-beneficio").addEventListener("click", fechar_ao_clicar_fora);
}

// Quando o HTML terminar de carregar, prepara a janela.
document.addEventListener("DOMContentLoaded", preparar_janela_de_beneficios);
