/*
  banco_indicadores.js — as guias da aba "Indicadores" do Portal Interno.

  Para que serve: a aba Indicadores tem duas guias, cada uma ocupando a tela inteira. Nesta versão (ADR-148), o
  Simulador de Rentabilidade fica oculto e a tela mostra só o Painel de acompanhamento, sem guias:
    - "painel": o Painel de acompanhamento, a única guia à vista (um relatório só com o planejamento e o uso das
      empresas, com o filtro do alto; dados em js/banco_planejamento.js, js/banco_uso.js e js/banco_uso_real.js);
    - "simulador": o Simulador de Rentabilidade (js/simulador_de_rentabilidade.js), OCULTO. O HTML dele, os botões das
      guias e o script ficam em caixas <template> do banco_indicadores.html, que o navegador guarda sem desenhar; aqui,
      o endereço antigo ?aba=simulador cai no painel.
  Este arquivo só troca a guia visível. Com as guias de volta (tirando as caixas), o clique numa guia muda o endereço
  junto (sem recarregar a página), para o "Atualizar" (F5) e o "Voltar" manterem a guia.
  Os endereços antigos continuam funcionando (links guardados e o botão do Início de antes):
    - ?aba=planejamento e ?aba=uso abrem o painel (as duas partes estão nele);
    - ?aba=consultor e "#consultor" abrem o painel: a conversa com o Consultor saiu do sistema (ADR-144), e a âncora
      sozinha não pede guia nenhuma;
    - ?aba=simulador abre o painel: o Simulador está oculto nesta versão (ADR-148);
    - ?aba=uso&empresa=<id> abre o painel filtrado por essa empresa e rola até "Onde as empresas travam" (quem lê a
      empresa do endereço é o filtro do alto, js/filtro_dos_indicadores.js).
*/

// As guias que estão à vista nesta tela; a primeira é a que abre quando o endereço não pede nenhuma.
// O "simulador" saiu da lista enquanto está oculto (ADR-148); para religar, volte-o para cá e tire as caixas <template>.
const GUIAS_DOS_INDICADORES = ["painel"];

// Os nomes de ?aba= que não são guias à vista (das sub-abas e das guias de antes) e a guia onde cada um cai hoje.
const GUIA_DE_CADA_ENDERECO_ANTIGO = {
  planejamento: "painel",
  uso: "painel",
  consultor: "painel",
  // O Simulador de Rentabilidade, oculto nesta versão (ADR-148): quem guardou o link vê o painel.
  simulador: "painel",
};

/**
 * Mostra a guia escolhida e esconde as outras.
 *
 * Recebe: guia — o nome da guia (hoje, só "painel"). Devolve: nada.
 */
function trocar_guia_dos_indicadores(guia) {
  // Liga só o botão da guia escolhida (com as guias ocultas, não há botão nenhum, e o laço não faz nada).
  for (const botao of document.querySelectorAll("[data-aba-indicadores]")) {
    // Verdadeiro para o botão da guia escolhida.
    const e_a_escolhida = botao.dataset.abaIndicadores === guia;
    // A classe desenha a linha colorida embaixo da guia escolhida.
    botao.classList.toggle("aba-ficha-ativa", e_a_escolhida);
    // Leitores de tela sabem qual guia está escolhida.
    botao.setAttribute("aria-selected", String(e_a_escolhida));
  }
  // Mostra só o conteúdo da guia escolhida.
  for (const conteudo of document.querySelectorAll("[data-conteudo-indicadores]")) {
    // hidden esconde a guia que não foi escolhida.
    conteudo.hidden = conteudo.dataset.conteudoIndicadores !== guia;
  }
}

/**
 * Diz qual guia o endereço pede; se não pede nenhuma que esteja à vista, a primeira (o painel).
 *
 * Recebe: nada. Devolve: o nome da guia.
 * Exemplos: "?aba=painel" → "painel"; "?aba=uso" e "?aba=consultor" (antigos) → "painel"; "?aba=simulador" (oculta)
 * → "painel"; só a âncora antiga "#consultor" → "painel" (a primeira guia).
 */
function guia_pedida_no_endereco() {
  // O valor de "aba" no endereço (null quando não tem).
  const pedida = new URLSearchParams(window.location.search).get("aba");
  // Uma guia que está à vista: é ela.
  if (GUIAS_DOS_INDICADORES.includes(pedida)) {
    return pedida;
  }
  // Um nome antigo ou oculto (planejamento, uso, consultor ou simulador): a guia onde ele cai hoje.
  if (Object.hasOwn(GUIA_DE_CADA_ENDERECO_ANTIGO, pedida)) {
    return GUIA_DE_CADA_ENDERECO_ANTIGO[pedida];
  }
  // Qualquer outra coisa (nada, ou um nome que não existe, como o antigo "ia"): a primeira guia.
  return GUIAS_DOS_INDICADORES[0];
}

/**
 * Escreve a guia no endereço, sem recarregar a página (o F5 e o "Voltar" continuam na mesma guia).
 *
 * Recebe: guia — o nome da guia. Devolve: nada.
 * Exemplo: no painel com "?aba=uso&empresa=EMP002", clicar numa guia "outra" deixa "?aba=outra&empresa=EMP002".
 * A empresa escolhida fica no endereço (o painel volta com ela) e a âncora antiga "#consultor" sai.
 */
function escrever_guia_no_endereco(guia) {
  // O endereço atual, para trocar só o "aba".
  const endereco = new URL(window.location.href);
  endereco.searchParams.set("aba", guia);
  // A âncora antiga sai: quem manda é o ?aba=.
  endereco.hash = "";
  // replaceState troca o endereço mostrado sem recarregar a página nem criar um passo a mais no "Voltar".
  window.history.replaceState(null, "", endereco.toString());
}

/**
 * Leva a tela até "Onde as empresas travam" quando o endereço traz uma empresa (ex.: o "Ver o uso" do Início).
 *
 * Recebe: nada. Devolve: nada. Sem empresa no endereço, a tela fica no alto.
 */
function rolar_ate_a_empresa_pedida() {
  // A empresa pedida no endereço (null quando não tem).
  const empresa_pedida = new URLSearchParams(window.location.search).get("empresa");
  // Sem empresa: nada a fazer.
  if (!empresa_pedida) {
    return;
  }
  // A parte com o funil e a linha do tempo da empresa.
  const parte_das_travas = document.querySelector("[data-parte-painel='travas']");
  // "start": o título da parte fica no alto da tela.
  parte_das_travas.scrollIntoView({ block: "start" });
}

/**
 * Prepara as guias: liga os cliques (quando há botões) e abre a guia pedida no endereço (ou o painel).
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_guias_dos_indicadores() {
  // Clique numa guia: troca a guia e o endereço (com as guias ocultas, não há botão, e o laço não faz nada).
  for (const botao of document.querySelectorAll("[data-aba-indicadores]")) {
    botao.addEventListener("click", function () {
      // A guia do botão clicado.
      const guia = botao.dataset.abaIndicadores;
      trocar_guia_dos_indicadores(guia);
      escrever_guia_no_endereco(guia);
    });
  }
  // O link "Simulador de Rentabilidade" do painel troca de guia sem recarregar a página (o filtro do alto fica).
  // Oculto nesta versão (ADR-148): o link está numa caixa <template>, e este laço não acha nenhum.
  for (const link of document.querySelectorAll("[data-ir-para-simulador]")) {
    link.addEventListener("click", function (evento) {
      evento.preventDefault();
      trocar_guia_dos_indicadores("simulador");
      escrever_guia_no_endereco("simulador");
      window.scrollTo(0, 0);
    });
  }
  // A guia pedida no endereço (já traduzida, se o endereço for antigo ou de uma guia oculta).
  const guia_pedida = guia_pedida_no_endereco();
  trocar_guia_dos_indicadores(guia_pedida);
  // No painel, com uma empresa no endereço, a tela vai direto ao funil e à linha do tempo dela.
  if (guia_pedida === "painel") {
    rolar_ate_a_empresa_pedida();
  }
}

// Quando o HTML terminar de carregar, prepara as guias.
document.addEventListener("DOMContentLoaded", preparar_guias_dos_indicadores);
