/*
  aviso_do_teto_da_ia.js — a faixa "A IA está pausada" no alto das telas do Portal Interno (ADR-139).

  Para que serve: quando o gasto com IA do dia (ou do mês) chega ao teto, a IA pausa e as empresas veem um aviso
  (ADR-131). O especialista do banco precisa ficar sabendo onde estiver no Portal: esta faixa amarela aparece logo
  abaixo do título da tela, diz qual teto foi atingido e até quando, e leva à página "Teto de gasto da IA"
  (banco_teto_da_ia.html), onde ele ajusta o teto (o acesso fica no menu Sistema, no painel dos dados da IA, o
  Acompanhamento dos agentes, e nesta faixa, só enquanto a IA estiver pausada).
  Com a IA funcionando, nada aparece. A faixa se atualiza ao voltar para a aba e de minuto em minuto. Se o servidor
  não responder, ela também não aparece: nunca um aviso inventado.
*/

// De quanto em quanto tempo a faixa pergunta de novo ao servidor (1 minuto, em milissegundos)
const INTERVALO_DO_AVISO_DO_TETO = 60000;

// O texto de cada teto atingido: qual teto e até quando a IA fica pausada
const TEXTOS_DO_AVISO_DO_TETO = {
  dia: "O teto de gasto do dia foi atingido: a análise automática das empresas espera até a meia-noite (horário de " +
    "Brasília) ou até o teto subir.",
  mes: "O teto de gasto do mês foi atingido: a análise automática das empresas espera até o dia 1º do mês que vem ou " +
    "até o teto subir.",
};

/**
 * Monta a faixa (ainda escondida) e a põe logo abaixo do título da tela. Chamada uma vez.
 *
 * Recebe: nada. Devolve: o elemento da faixa, ou null se a tela não tem onde pô-la.
 */
function montar_faixa_do_teto() {
  const principal = document.querySelector("main");
  // Tela sem área principal: não há onde pôr a faixa
  if (!principal) {
    return null;
  }
  // A caixa centralizada, como o resto da tela
  const caixa = document.createElement("div");
  caixa.className = "conteudo-centralizado envios-parados";
  caixa.setAttribute("data-faixa-teto-da-ia", "");
  caixa.hidden = true;
  // O aviso amarelo: o título, o texto e o link para a página do teto
  const aviso = document.createElement("div");
  aviso.className = "aviso-envio-parado";
  aviso.setAttribute("role", "status");
  const titulo = document.createElement("span");
  titulo.className = "aviso-envio-parado-titulo";
  titulo.textContent = "Os agentes estão pausados";
  const texto = document.createElement("p");
  texto.className = "aviso-envio-parado-texto";
  texto.setAttribute("data-faixa-teto-da-ia-texto", "");
  const link = document.createElement("a");
  link.className = "link-simples";
  link.href = "banco_teto_da_ia.html";
  link.textContent = "Ver e ajustar o teto";
  aviso.append(titulo, texto, link);
  caixa.append(aviso);
  // Logo abaixo do título da tela (ou no começo da área principal, se a tela não tem título)
  const titulo_da_tela = principal.querySelector(".cabecalho-pagina");
  if (titulo_da_tela) {
    titulo_da_tela.after(caixa);
  } else {
    principal.prepend(caixa);
  }
  return caixa;
}

/**
 * Pergunta ao servidor se algum teto foi atingido e mostra (ou esconde) a faixa.
 *
 * Recebe: faixa — o elemento montado por montar_faixa_do_teto. Devolve: nada.
 */
async function atualizar_faixa_do_teto(faixa) {
  try {
    const resposta = await fetch("/api/banco/teto_da_ia/aviso");
    // Sem resposta boa (ex.: a sessão expirou): a faixa fica escondida
    if (!resposta.ok) {
      faixa.hidden = true;
      return;
    }
    const dados = await resposta.json();
    const texto = TEXTOS_DO_AVISO_DO_TETO[dados.atingido];
    // Nenhum teto atingido (ou um valor que a faixa não conhece): escondida
    if (!texto) {
      faixa.hidden = true;
      return;
    }
    faixa.querySelector("[data-faixa-teto-da-ia-texto]").textContent = texto;
    faixa.hidden = false;
  } catch (erro) {
    // Servidor fora do ar: nada de aviso inventado
    faixa.hidden = true;
  }
}

/**
 * Monta a faixa, faz a primeira consulta e liga a atualização automática. Chamada uma vez, ao carregar a página.
 *
 * Recebe: nada. Devolve: nada. Aberta como arquivo (o protótipo), não faz nada: não há servidor para perguntar.
 */
function preparar_faixa_do_teto() {
  // O protótipo aberto com dois cliques não tem servidor
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  const faixa = montar_faixa_do_teto();
  if (!faixa) {
    return;
  }
  atualizar_faixa_do_teto(faixa);
  // Ao voltar para a aba e de minuto em minuto (com a aba à vista), pergunta de novo
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      atualizar_faixa_do_teto(faixa);
    }
  });
  window.setInterval(function () {
    if (!document.hidden) {
      atualizar_faixa_do_teto(faixa);
    }
  }, INTERVALO_DO_AVISO_DO_TETO);
}

// Quando o HTML terminar de carregar, prepara a faixa.
document.addEventListener("DOMContentLoaded", preparar_faixa_do_teto);
