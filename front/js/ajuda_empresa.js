/*
  ajuda_empresa.js — o "Posso ajudar?" do Portal Empresa vira conversa com o especialista do banco.

  Para que serve: ao clicar no ícone de conversa do cabeçalho (ao lado do sino), abre um painel "Fale com o seu
  especialista",
  com a conversa da empresa e uma caixa para escrever. A mensagem vai para a aba "Conversa" da ficha da empresa no
  Portal Interno (banco_empresas.html?aba=conversa), onde uma PESSOA responde. Cada mensagem leva junto a tela em que a empresa
  estava ("Sobre: Acompanhar cadastros"), para o especialista entender o contexto sem perguntar.

  Depende de: js/conversas.js (guarda e lê as conversas), carregado antes deste arquivo.
  Aparência: css/conversa.css.

  Neste rascunho, quem está logado é a Marina Costa, do RH da Aurora Alimentos (a mesma das telas da empresa).
*/

// A conversa da empresa logada (a Aurora) e o nome de quem escreve.
const CONVERSA_DA_EMPRESA = "aurora";
const AUTORA_DA_EMPRESA = "Marina Costa";

/**
 * Descobre em que tela a empresa está, pelo nome da aba ativa (ex.: "Acompanhar cadastros").
 *
 * Recebe: nada. Devolve: o nome da tela.
 */
function tela_atual_da_empresa() {
  // A aba marcada como ativa no cabeçalho.
  const aba_ativa = document.querySelector(".aba-ativa");
  // Sem aba ativa (não deveria acontecer): usa um nome genérico.
  if (!aba_ativa) {
    return "Portal Empresa";
  }
  // O texto da aba, sem espaços nas pontas.
  return aba_ativa.textContent.trim();
}

/**
 * Cria o painel da conversa (uma vez só) e o coloca no fim da página, escondido.
 *
 * Recebe: nada. Devolve: o painel.
 * O esqueleto é fixo (não tem nada digitado por ninguém); as mensagens entram depois, como texto puro.
 */
function criar_painel_de_conversa() {
  // O painel lateral.
  const painel = document.createElement("aside");
  painel.className = "painel-conversa";
  // Para leitores de tela: é uma janela com nome.
  painel.setAttribute("role", "dialog");
  painel.setAttribute("aria-label", "Fale com o seu especialista");
  // Começa escondido.
  painel.hidden = true;
  // Esqueleto: cabeçalho com o especialista, aviso, lugar das mensagens e a caixa de escrever.
  painel.innerHTML = `
    <div class="conversa-cabecalho">
      <span class="iniciais-usuario">RL</span>
      <div class="conversa-cabecalho-textos">
        <div class="conversa-nome">Rafael Lima</div>
        <div class="conversa-cargo">Seu especialista Santander · responde em até 1 dia útil</div>
      </div>
      <button class="botao-fechar-janela" type="button" aria-label="Fechar a conversa" data-fechar-conversa>
        <svg class="icone" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>
    <p class="conversa-aviso">Conversa com uma pessoa do banco. Não mande senhas nem documentos por aqui.</p>
    <div class="conversa-mensagens" data-mensagens-empresa aria-live="polite"></div>
    <form class="conversa-escrever" data-formulario-empresa novalidate>
      <span class="conversa-sobre" data-sobre-empresa></span>
      <textarea class="campo-entrada" rows="2" maxlength="600" placeholder="Escreva a sua dúvida" aria-label="Sua mensagem" data-texto-empresa></textarea>
      <button class="botao botao-principal botao-pequeno" type="submit">Enviar</button>
    </form>`;
  // Coloca o painel no fim da página.
  document.body.append(painel);
  // Devolve para quem chamou.
  return painel;
}

/**
 * Mostra as mensagens da conversa da empresa no painel.
 *
 * Recebe: painel. Devolve: nada.
 */
function mostrar_mensagens_da_empresa(painel) {
  // Lugar das mensagens.
  const lista = painel.querySelector("[data-mensagens-empresa]");
  // Esvazia antes de montar.
  lista.replaceChildren();
  // A conversa da empresa, lida do que está guardado agora (com servidor, a da empresa de quem entrou).
  const conversa = conversa_da_empresa_logada(CONVERSA_DA_EMPRESA);
  // Sem conversa ainda (não deveria acontecer): nada a mostrar.
  if (!conversa) {
    return;
  }
  // Uma bolha por mensagem.
  for (const mensagem of conversa.mensagens) {
    // Na tela da empresa, "minha" é a mensagem da empresa (fica à direita).
    lista.append(montar_bolha(mensagem, mensagem.de === "empresa"));
  }
  // Rola até a última mensagem.
  lista.scrollTop = lista.scrollHeight;
}

/**
 * Abre ou fecha o painel da conversa.
 *
 * Recebe: painel. Devolve: nada.
 */
function alternar_painel_de_conversa(painel) {
  // Se está escondido, abre; se está aberto, fecha.
  painel.hidden = !painel.hidden;
  // Ao abrir: atualiza as mensagens, o "Sobre" e põe o cursor na caixa de escrever.
  if (!painel.hidden) {
    mostrar_mensagens_da_empresa(painel);
    painel.querySelector("[data-sobre-empresa]").textContent = "Sobre: " + tela_atual_da_empresa();
    painel.querySelector("[data-texto-empresa]").focus();
  }
}

/**
 * Envia a mensagem da empresa: guarda na conversa e mostra no painel.
 *
 * Recebe: evento — o envio do formulário; painel. Devolve: nada.
 */
function enviar_mensagem_da_empresa(evento, painel) {
  // Impede o envio padrão do formulário (que recarregaria a página).
  evento.preventDefault();
  // A caixa de texto e o que foi escrito.
  const caixa = painel.querySelector("[data-texto-empresa]");
  const texto = caixa.value.trim();
  // Mensagem vazia: não envia.
  if (texto === "") {
    return;
  }
  // Guarda a mensagem, com a tela de onde ela saiu.
  acrescentar_mensagem(conversa_da_empresa_logada(CONVERSA_DA_EMPRESA).id, { de: "empresa", autor: AUTORA_DA_EMPRESA, contexto: tela_atual_da_empresa(), texto: texto });
  // Limpa a caixa.
  caixa.value = "";
  // Mostra a conversa atualizada.
  mostrar_mensagens_da_empresa(painel);
}

/**
 * Prepara o "Posso ajudar?": cria o painel e liga o botão, o X, o Esc e o envio.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_ajuda_da_empresa() {
  // O "Posso ajudar?" é um ícone no cabeçalho, ao lado do sino; o canto da tela é do
  // "Cadastrar funcionários" (js/novo_envio.js). Página sem cabeçalho de usuário: nada a fazer.
  const acoes_do_usuario = document.querySelector(".acoes-usuario");
  if (!acoes_do_usuario) {
    return;
  }
  // O ícone: dois balões de conversa (quem responde é uma pessoa, não a IA).
  const botao = document.createElement("button");
  botao.type = "button";
  // Classe própria (não "botao-avisos"): o cabeçalho procura o sino por essa classe e não pode achar este ícone
  botao.className = "botao-conversa";
  botao.setAttribute("aria-label", "Posso ajudar? Fale com o seu especialista do banco");
  botao.title = "Posso ajudar? Fale com o seu especialista do banco";
  botao.innerHTML = '<svg class="icone" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M19 9h1a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-1v3l-4-3h-3"/></svg>';
  // Fica antes do sino.
  acoes_do_usuario.prepend(botao);
  // Cria o painel (escondido).
  const painel = criar_painel_de_conversa();
  // Clique no botão: abre ou fecha.
  botao.addEventListener("click", function () { alternar_painel_de_conversa(painel); });
  // Clique no X: fecha.
  painel.querySelector("[data-fechar-conversa]").addEventListener("click", function () { painel.hidden = true; });
  // Envio do formulário: manda a mensagem.
  painel.querySelector("[data-formulario-empresa]").addEventListener("submit", function (evento) { enviar_mensagem_da_empresa(evento, painel); });
  // Com servidor, quando as conversas chegam (ou são atualizadas), redesenha o painel aberto.
  document.addEventListener("conversas-carregadas", function () {
    if (!painel.hidden) {
      mostrar_mensagens_da_empresa(painel);
    }
  });
  // Tecla Esc: fecha o painel, se estiver aberto.
  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape" && !painel.hidden) {
      painel.hidden = true;
    }
  });
}

// Quando o HTML terminar de carregar, prepara o "Posso ajudar?".
document.addEventListener("DOMContentLoaded", preparar_ajuda_da_empresa);
