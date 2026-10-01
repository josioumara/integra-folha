/*
  carregando_dados.js — impede que os dados de exemplo apareçam quando a tela está ligada ao servidor.

  Para que serve: as telas nasceram do protótipo e trazem, escritos no HTML, números e listas de exemplo (ex.: "312
  funcionários com cadastro aprovado"). Servidas pela aplicação, sem este arquivo, esses exemplos apareceriam por um
  instante a cada "Atualizar" (F5), até o servidor responder, e dariam a impressão de números aleatórios. Por isso:
    - servida pelo servidor, a página ganha a marca "aguardando-dados" antes de aparecer;
    - todo elemento marcado no HTML com data-aguarda-dado (um número) ou data-aguarda-bloco (uma lista) mostra uma
      barra cinza de "carregando" (o "esqueleto", no jargão de telas) no lugar do exemplo;
    - quando o dado de verdade chega, o script da tela chama marcar_como_carregado(elemento) e o dado aparece;
    - se o servidor falhar, mostrar_dado_indisponivel(elemento) põe um traço ("—"): nunca um número inventado.
  Aberta como arquivo (o protótipo, com dois cliques), nada muda: os exemplos continuam à mostra.

  Carregado no <head>, depois do CSS, para a marca entrar antes de a página ser desenhada (sem "piscar"). Fica num
  arquivo .js, e não escrito dentro da página, por causa da política de conteúdo do site (ADR-110).
*/

// Servida pelo servidor ("http:" ou "https:")? Então marca a página inteira como esperando os dados.
if (window.location.protocol.startsWith("http")) {
  document.documentElement.classList.add("aguardando-dados");
}

/**
 * Mostra o dado de um elemento: tira a barra de "carregando" (o dado de verdade já foi posto nele).
 *
 * Recebe: elemento — o elemento marcado com data-aguarda-dado ou data-aguarda-bloco (ou null, que é ignorado).
 * Devolve: nada. Ex.: marcar_como_carregado(document.querySelector("[data-resumo-aprovados]")).
 */
function marcar_como_carregado(elemento) {
  // Elemento que não existe nesta tela: nada a fazer.
  if (!elemento) {
    return;
  }
  // A marca "pronto" desliga a barra de "carregando" (css/estilos.css, seção "Esperando os dados").
  elemento.setAttribute("data-dado-pronto", "");
}

/**
 * Mostra os dados de vários elementos de uma vez.
 *
 * Recebe: seletor — o seletor CSS dos elementos. Devolve: nada.
 * Ex.: marcar_todos_como_carregados("[data-grade-numeros] [data-aguarda-dado]").
 */
function marcar_todos_como_carregados(seletor) {
  // Cada elemento encontrado ganha a marca "pronto".
  for (const elemento of document.querySelectorAll(seletor)) {
    marcar_como_carregado(elemento);
  }
}

/**
 * O servidor não respondeu: põe um traço no lugar do número (nunca o exemplo) e tira a barra de "carregando".
 *
 * Recebe: elemento — o elemento do número (ou null, que é ignorado). Devolve: nada.
 * Se o elemento já mostra um dado de verdade (ex.: a atualização automática falhou uma vez), ele fica como está: um
 * número certo de instantes atrás é melhor que um traço.
 */
function mostrar_dado_indisponivel(elemento) {
  // Elemento que não existe nesta tela: nada a fazer.
  if (!elemento) {
    return;
  }
  // Já tem dado de verdade: mantém.
  if (elemento.hasAttribute("data-dado-pronto")) {
    return;
  }
  // O traço diz "sem dado agora", sem inventar valor.
  elemento.textContent = "—";
  marcar_como_carregado(elemento);
}
