/*
  em_janela.js — marca a tela de envio quando ela abre dentro da janela "Cadastrar funcionários".

  Para que serve: a janela (js/novo_envio.js) mostra cadastrar.html?em_janela=1 num quadro. Com a marca "em-janela"
  na página, o estilo esconde o cabeçalho, o título e a conferência: depois de aceitar as colunas, tudo segue em
  "Acompanhar cadastros".

  Por que num arquivo, e não escrito dentro do cadastrar.html: a política de conteúdo do
  site (Content-Security-Policy, ADR-110) só deixa rodar scripts que vêm de arquivos .js do próprio site. Um script
  escrito dentro da página seria bloqueado, e é justamente assim que um código injetado chegaria.
  Carregado no começo do <body>, antes do resto da tela aparecer, para a página não "piscar" com o cabeçalho.
*/

// O endereço tem "em_janela"? Então a tela está dentro da janela: marca a página inteira.
if (new URLSearchParams(window.location.search).get("em_janela")) {
  document.documentElement.classList.add("em-janela");
}
