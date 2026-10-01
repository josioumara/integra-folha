/*
  cabecalho_real.js — o cabeçalho de todas as telas com os dados de quem entrou, e a janela "Minha senha" (ADR-69).

  Para que serve: o layout tinha um nome fixo e números inventados no cabeçalho. Com a página ligada à aplicação
  (/api/cabecalho), o cabeçalho mostra:
    - quem entrou (o login) e o papel ("RH · <empresa>" ou "Especialista do banco"), com as iniciais;
    - no Portal Interno, o número da aba Envios (os envios esperando a avaliação) e, na faixa escura do alto,
      quantas empresas a carteira tem. O número da aba Empresas (as conversas abertas) é do js/sinal_de_conversas.js,
      que o busca de novo de tempos em tempos.
  Clicar no nome abre a janela "Minha senha": a pessoa troca a própria senha (ex.: a senha provisória do convite).
  Com a senha provisória (convite ou redefinição pelo banco, ADR-109), a janela abre sozinha e não fecha sem a troca:
  até lá, a API não entrega nenhum dado para essa sessão.
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout.
  Servida pela aplicação, os números de exemplo do cabeçalho nunca aparecem: esperam atrás da barra cinza
  (js/carregando_dados.js) e, se o servidor falhar, viram um traço.
*/

// O começo do texto da faixa escura do Portal Interno (a carteira do especialista), com ou sem o número de empresas
const TEXTO_DA_FAIXA_DA_CARTEIRA = "Sua carteira";

/**
 * Preenche o cabeçalho com os dados de quem entrou e os contadores.
 *
 * Recebe: dados — da API (/api/cabecalho). Devolve: nada.
 */
function preencher_cabecalho(dados) {
  document.querySelector(".nome-usuario").textContent = dados.login;
  document.querySelector(".empresa-usuario").textContent = dados.papel;
  document.querySelector(".iniciais-usuario").textContent = dados.iniciais;
  // O nome de exemplo esperava escondido (js/carregando_dados.js): agora aparece o de verdade.
  liberar_cabecalho();
  // A aba Envios do Portal Interno: os envios esperando a avaliação.
  const aba_de_envios = document.querySelector("a.aba[href='banco_envios.html'] .contador-aba");
  if (aba_de_envios) {
    aba_de_envios.textContent = String(dados.envios_para_avaliar);
    aba_de_envios.hidden = dados.envios_para_avaliar === 0;
    // O número de verdade chegou: sai a barra de "carregando".
    marcar_como_carregado(aba_de_envios);
  }
  // A faixa escura do Portal Interno: quantas empresas a carteira tem.
  const faixa_da_carteira = document.querySelector("[data-faixa-carteira]");
  if (faixa_da_carteira) {
    faixa_da_carteira.textContent = TEXTO_DA_FAIXA_DA_CARTEIRA + " · " + dados.empresas_na_carteira + " empresas";
    marcar_como_carregado(faixa_da_carteira);
  }
}

// ===== "Minha senha" =====

/**
 * Cria a janela "Minha senha" (uma vez só) e a põe no fim da página.
 *
 * Recebe: nada. Devolve: a janela (<dialog>). O esqueleto é fixo; nada digitado entra como HTML.
 */
function criar_janela_de_senha() {
  const janela = document.createElement("dialog");
  janela.className = "janela-beneficio";
  janela.id = "janela-minha-senha";
  janela.setAttribute("aria-label", "Minha senha");
  janela.innerHTML =
    '<form class="janela-conteudo" method="dialog" novalidate data-formulario-senha>' +
    '<div class="janela-cabecalho"><div class="janela-cabecalho-textos"><span class="sobretitulo">Minha senha</span>' +
    '<h2 class="janela-titulo">Trocar a minha senha</h2></div></div>' +
    '<p class="janela-resumo">Recebeu uma senha provisória? Troque por uma só sua. Pelo menos 8 caracteres.</p>' +
    '<label class="campo"><span class="campo-rotulo">Senha atual</span><input class="campo-entrada" type="password" autocomplete="current-password" data-senha-atual></label>' +
    '<label class="campo campo-com-espaco"><span class="campo-rotulo">Nova senha</span><input class="campo-entrada" type="password" autocomplete="new-password" data-senha-nova></label>' +
    '<label class="campo campo-com-espaco"><span class="campo-rotulo">Repita a nova senha</span><input class="campo-entrada" type="password" autocomplete="new-password" data-senha-confirmacao></label>' +
    '<p class="aviso-campo" data-senha-erro hidden></p>' +
    '<div class="janela-botoes"><button class="botao botao-contorno" type="button" data-cancelar-senha>Cancelar</button>' +
    '<button class="botao botao-principal" type="submit">Trocar a senha</button></div></form>';
  document.body.append(janela);
  janela.querySelector("[data-cancelar-senha]").addEventListener("click", function () {
    janela.close();
  });
  janela.querySelector("[data-formulario-senha]").addEventListener("submit", trocar_minha_senha);
  // A tecla Esc fecha uma janela; no modo obrigatório (senha provisória), ela não pode fechar sem a troca.
  janela.addEventListener("cancel", function (evento) {
    if (janela.dataset.obrigatoria === "sim") {
      evento.preventDefault();
    }
  });
  return janela;
}

/**
 * Abre a janela "Minha senha", com os campos limpos.
 *
 * Recebe: obrigatoria — true quando a pessoa está com a senha provisória (convite ou redefinição, ADR-109): a
 * janela explica o motivo, esconde o "Cancelar" e não fecha com Esc; só a troca libera a tela. Devolve: nada.
 */
function abrir_janela_de_senha(obrigatoria) {
  const janela = document.getElementById("janela-minha-senha") || criar_janela_de_senha();
  for (const campo of janela.querySelectorAll("input")) {
    campo.value = "";
  }
  janela.querySelector("[data-senha-erro]").hidden = true;
  // O modo da janela: normal (a pessoa escolheu trocar) ou obrigatório (senha provisória).
  const modo_obrigatorio = obrigatoria === true;
  janela.dataset.obrigatoria = "nao";
  if (modo_obrigatorio) {
    janela.dataset.obrigatoria = "sim";
  }
  janela.querySelector("[data-cancelar-senha]").hidden = modo_obrigatorio;
  let recado = "Recebeu uma senha provisória? Troque por uma só sua. Pelo menos 8 caracteres.";
  if (modo_obrigatorio) {
    recado = "Você entrou com uma senha provisória, entregue pelo banco. Por segurança, crie agora uma senha só sua " +
      "(pelo menos 8 caracteres). Em \"Senha atual\", digite a provisória.";
  }
  janela.querySelector(".janela-resumo").textContent = recado;
  janela.showModal();
}

/**
 * Manda a troca da senha. Deu certo: a janela fecha e um aviso confirma.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
async function trocar_minha_senha(evento) {
  evento.preventDefault();
  const janela = document.getElementById("janela-minha-senha");
  const aviso = janela.querySelector("[data-senha-erro]");
  const corpo = {
    senha_atual: janela.querySelector("[data-senha-atual]").value,
    nova_senha: janela.querySelector("[data-senha-nova]").value,
    confirmacao: janela.querySelector("[data-senha-confirmacao]").value,
  };
  try {
    const resposta = await fetch("/api/minha-senha", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo) });
    if (!resposta.ok) {
      const dados = await resposta.json();
      aviso.textContent = typeof dados.detail === "string" ? dados.detail : "Preencha os três campos.";
      aviso.hidden = false;
      return;
    }
  } catch (erro) {
    aviso.textContent = "Sem conexão com o servidor. Tente de novo.";
    aviso.hidden = false;
    return;
  }
  // Era a troca obrigatória: recarrega a página, que agora pode buscar os dados (a API liberou a sessão).
  if (janela.dataset.obrigatoria === "sim") {
    window.location.reload();
    return;
  }
  janela.close();
  document.querySelector(".nome-usuario").title = "Senha trocada agora";
  document.querySelector(".empresa-usuario").textContent = document.querySelector(".empresa-usuario").textContent + " · senha trocada";
}

/**
 * Mostra o bloco de quem entrou: tira a barra cinza de "carregando" do nome, da empresa e das iniciais.
 *
 * Recebe: nada. Devolve: nada. Enquanto os dados não chegam, o nome de exemplo do layout nunca aparece
 * (css/estilos.css, seção "Esperando os dados").
 */
function liberar_cabecalho() {
  // A marca "pronto" no bloco inteiro desliga a barra cinza dos três textos.
  document.querySelector(".usuario-logado").setAttribute("data-dado-pronto", "");
}

/**
 * O servidor não respondeu: o cabeçalho fica sem nome (um traço), nunca com o nome de exemplo do layout.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_cabecalho_sem_dado() {
  // Traço no nome; a empresa e as iniciais ficam vazias.
  document.querySelector(".nome-usuario").textContent = "—";
  document.querySelector(".empresa-usuario").textContent = "";
  document.querySelector(".iniciais-usuario").textContent = "";
  liberar_cabecalho();
  // No Portal Interno, o número da aba Envios vira um traço (nunca o número de exemplo). O da aba Empresas é do
  // js/sinal_de_conversas.js.
  mostrar_dado_indisponivel(document.querySelector("a.aba[href='banco_envios.html'] .contador-aba"));
  // A faixa escura fica só com "Sua carteira", sem número (e sem a região e o total do exemplo).
  const faixa_da_carteira = document.querySelector("[data-faixa-carteira]");
  if (faixa_da_carteira) {
    faixa_da_carteira.textContent = TEXTO_DA_FAIXA_DA_CARTEIRA;
    marcar_como_carregado(faixa_da_carteira);
  }
}

/**
 * Liga o cabeçalho real: busca os dados, preenche e deixa o nome abrir "Minha senha".
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: fica o exemplo. Sem resposta do servidor: um traço.
 */
async function ligar_cabecalho_real() {
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  try {
    const resposta = await fetch("/api/cabecalho");
    // Recusado (ex.: sessão vencida): sem o nome, e sem o exemplo
    if (!resposta.ok) {
      mostrar_cabecalho_sem_dado();
      return;
    }
    const dados = await resposta.json();
    preencher_cabecalho(dados);
    // Senha provisória (convite ou redefinição): a primeira coisa é trocá-la (ADR-109).
    if (dados.senha_provisoria) {
      abrir_janela_de_senha(true);
    }
  } catch (erro) {
    // Servidor fora do ar: sem o nome, e sem o exemplo
    mostrar_cabecalho_sem_dado();
    return;
  }
  // O nome de quem entrou abre "Minha senha" (clique ou teclado).
  const usuario = document.querySelector(".usuario-logado");
  usuario.setAttribute("role", "button");
  usuario.setAttribute("tabindex", "0");
  usuario.title = "Minha senha";
  usuario.style.cursor = "pointer";
  usuario.addEventListener("click", function () {
    abrir_janela_de_senha(false);
  });
  usuario.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter" || evento.key === " ") {
      evento.preventDefault();
      abrir_janela_de_senha(false);
    }
  });
}

// Quando o HTML terminar de carregar, liga o cabeçalho real (se houver servidor).
document.addEventListener("DOMContentLoaded", ligar_cabecalho_real);
