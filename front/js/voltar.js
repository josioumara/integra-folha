/*
  voltar.js — o link "Voltar" das páginas de texto (Privacidade e LGPD, Termos de uso).

  Para que serve: quem chegou pelo rodapé de uma tela do Integra Folha volta para ela, do jeito que estava; quem abriu
  o endereço direto (sem uma tela do site antes) segue o endereço do próprio link, a tela de login.

  Por que um arquivo: a política de conteúdo do site não deixa escrever script dentro da página
  (tests/test_protecoes_do_site.py confere).
  Como sabe de onde a pessoa veio: pelo document.referrer, o endereço da página anterior. O servidor manda
  "Referrer-Policy: same-origin", então esse endereço só existe quando a página anterior é do próprio site.
*/

// Diz se a pessoa chegou aqui vindo de uma tela do próprio site
function veio_de_uma_tela_do_site() {
  // O começo dos endereços do site (ex.: "https://integrafolha.com.br/")
  const comeco_do_site = window.location.origin + "/";
  // A página anterior começa com o endereço do site?
  return document.referrer.startsWith(comeco_do_site);
}

// Liga cada link "Voltar" da página (a marca data-voltar)
function ligar_os_links_de_voltar() {
  // Os links "Voltar" desta página (em geral, um só, na faixa de cima)
  const links_de_voltar = document.querySelectorAll("[data-voltar]");
  for (const link of links_de_voltar) {
    link.addEventListener("click", function (evento) {
      // Veio de uma tela do site: volta para ela, em vez de seguir o endereço do link
      if (veio_de_uma_tela_do_site()) {
        evento.preventDefault();
        window.history.back();
      }
      // Senão, o link segue o próprio endereço (a tela de login)
    });
  }
}

ligar_os_links_de_voltar();
