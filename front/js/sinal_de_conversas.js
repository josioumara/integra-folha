/*
  sinal_de_conversas.js — o sinal das conversas abertas (a "bolinha" com o número), no Portal Interno.

  Para que serve: o especialista precisa ver, de qualquer tela do banco, que há empresas esperando por ele na Conversa.
  Uma conversa está ABERTA quando tem mensagem e ainda não foi marcada como
  respondida: ou ela espera a resposta dele (a última mensagem é da empresa), ou ele já respondeu e ainda não marcou.
  Este arquivo:
    1. busca no servidor as empresas com a conversa aberta (GET /api/banco/conversas/abertas): ao abrir a tela, de 15
       em 15 segundos com a tela à vista, ao voltar para ela e logo depois de uma mensagem ou de uma marcação gravada
       (o evento "conversa-gravada", do js/conversas.js);
    2. põe o total na bolinha ao lado de "Empresas", no menu do alto de todas as telas do banco. Ele acha sozinho o
       link do menu e usa a bolinha que já está lá (ou cria uma), sem mudar o menu de cada página. É o ÚNICO arquivo
       que escreve esse número;
    3. no Início, põe no cartão "mensagens de empresas sem resposta" quantas conversas abertas esperam o especialista
       (as que têm a última mensagem da empresa);
    4. guarda a última resposta em window.conversas_abertas e avisa as outras partes da tela com o evento
       "conversas-abertas-atualizadas" (no document), para elas não buscarem de novo. A aba Conversa e a Carteira da
       tela Empresas (js/banco_empresas_conversa.js) põem a bolinha de cada empresa com isso.

  A resposta do servidor: {"empresas": [{"empresa_id", "sem_resposta", "ultima_mensagem_em"}], "total": <quantas>}.
  Sem nenhuma aberta, a bolinha some. Enquanto a primeira resposta não chega, o número espera com a barra cinza
  (js/carregando_dados.js); se o servidor falhar, entra um traço, nunca um número de exemplo. Aberta como arquivo (o
  protótipo, com dois cliques), nada muda: fica o exemplo escrito no HTML.
*/

// De quanto em quanto tempo o sinal é buscado de novo, com a tela à vista (em milissegundos): o ritmo das conversas.
const INTERVALO_DO_SINAL = 15000;

// O endereço das conversas abertas (services/mensagens.py, só o perfil BANCO).
const ENDERECO_DAS_CONVERSAS_ABERTAS = "/api/banco/conversas/abertas";

// A última resposta do servidor (null enquanto a primeira não chega). As outras partes da tela leem daqui.
window.conversas_abertas = null;

// O número da busca mais recente: uma resposta mais velha, que chegue depois de uma mais nova, é ignorada.
let numero_da_ultima_busca = 0;

// ===== 1. A bolinha do menu e o cartão do Início =====

/**
 * Acha a bolinha do menu, ao lado de "Empresas": a que o HTML já traz ou uma nova, criada no fim do link.
 *
 * Recebe: nada. Devolve: o elemento da bolinha, ou null nas páginas sem o menu do banco.
 */
function bolinha_do_menu() {
  // O link "Empresas" do menu do alto.
  const link = document.querySelector(".abas-banco a.aba[href='banco_empresas.html']");
  // Página sem o menu do banco: não há onde pôr a bolinha.
  if (!link) {
    return null;
  }
  // A bolinha que o HTML já traz.
  let bolinha = link.querySelector("[data-contador-mensagens]");
  // Não tem: cria uma, igual às outras bolinhas do menu, escondida até o número chegar.
  if (!bolinha) {
    bolinha = document.createElement("span");
    bolinha.className = "contador-aba";
    bolinha.setAttribute("data-contador-mensagens", "");
    bolinha.hidden = true;
    link.append(bolinha);
  }
  // Devolve a bolinha.
  return bolinha;
}

/**
 * A dica da bolinha do menu (aparece ao passar o mouse), no singular ou no plural.
 *
 * Recebe: total — quantas conversas abertas. Devolve: o texto.
 * Exemplos: 1 → "1 conversa aberta: sem resposta ou ainda não marcada como respondida";
 * 3 → "3 conversas abertas: sem resposta ou ainda não marcadas como respondidas".
 */
function dica_da_bolinha_do_menu(total) {
  // Plural com 2 ou mais.
  let dica = total + " conversas abertas: sem resposta ou ainda não marcadas como respondidas";
  // Singular com 1.
  if (total === 1) {
    dica = "1 conversa aberta: sem resposta ou ainda não marcada como respondida";
  }
  // Devolve a dica pronta.
  return dica;
}

/**
 * Escreve o total na bolinha do menu (ela some quando o total é 0).
 *
 * Recebe: total — quantas conversas abertas. Devolve: nada.
 */
function escrever_bolinha_do_menu(total) {
  // A bolinha do menu (null nas páginas sem o menu do banco).
  const bolinha = bolinha_do_menu();
  if (!bolinha) {
    return;
  }
  // O número e a dica.
  bolinha.textContent = String(total);
  bolinha.title = dica_da_bolinha_do_menu(total);
  // Nenhuma conversa aberta: a bolinha some.
  bolinha.hidden = total === 0;
  // O número de verdade chegou: sai a barra de "carregando" (js/carregando_dados.js).
  marcar_como_carregado(bolinha);
}

/**
 * No Início, o cartão "mensagens de empresas sem resposta": quantas conversas abertas esperam o especialista.
 *
 * Recebe: empresas — as conversas abertas da resposta do servidor. Devolve: nada. Nas outras telas, não faz nada.
 */
function escrever_numero_do_inicio(empresas) {
  // O número do cartão (só existe no Início).
  const numero = document.querySelector("[data-numero-mensagens]");
  if (!numero) {
    return;
  }
  // Conta as abertas que esperam a resposta do especialista (a última mensagem é da empresa).
  let sem_resposta = 0;
  for (const empresa of empresas) {
    if (empresa.sem_resposta) {
      sem_resposta = sem_resposta + 1;
    }
  }
  // Escreve o número e tira a barra de "carregando".
  numero.textContent = String(sem_resposta);
  marcar_como_carregado(numero);
}

/**
 * O servidor não entregou o sinal: um traço na bolinha do menu e no cartão do Início, nunca o número de exemplo.
 *
 * Recebe: nada. Devolve: nada. Um número que já veio do servidor fica como está (ver mostrar_dado_indisponivel).
 */
function mostrar_sinal_indisponivel() {
  mostrar_dado_indisponivel(bolinha_do_menu());
  mostrar_dado_indisponivel(document.querySelector("[data-numero-mensagens]"));
}

// ===== 2. Buscar no servidor =====

/**
 * Busca as empresas com a conversa aberta e atualiza a bolinha do menu, o cartão do Início e as outras partes da tela.
 *
 * Recebe: nada. Devolve: nada. Uma resposta que chegue depois de outra mais nova é ignorada (não volta o número velho).
 */
async function buscar_conversas_abertas() {
  // O número desta busca: a mais nova de todas, por enquanto.
  numero_da_ultima_busca = numero_da_ultima_busca + 1;
  const numero_desta_busca = numero_da_ultima_busca;
  // try/catch: servidor fora do ar não quebra a tela (entra o traço).
  let dados = null;
  try {
    const resposta = await fetch(ENDERECO_DAS_CONVERSAS_ABERTAS);
    // Recusado ou com erro: o traço, sem deixar o exemplo à mostra.
    if (!resposta.ok) {
      mostrar_sinal_indisponivel();
      return;
    }
    dados = await resposta.json();
  } catch (erro) {
    mostrar_sinal_indisponivel();
    return;
  }
  // Uma busca mais nova já foi pedida: esta resposta é velha e fica de fora.
  if (numero_desta_busca !== numero_da_ultima_busca) {
    return;
  }
  // Guarda a resposta para as outras partes da tela.
  window.conversas_abertas = dados;
  // O total no menu e, no Início, as que esperam o especialista.
  escrever_bolinha_do_menu(dados.total);
  escrever_numero_do_inicio(dados.empresas);
  // Avisa as outras partes da tela (a Carteira e a aba Conversa da tela Empresas).
  document.dispatchEvent(new CustomEvent("conversas-abertas-atualizadas", { detail: dados }));
}

/**
 * Busca o sinal de novo só com a tela à vista (numa aba escondida do navegador, espera a pessoa voltar).
 *
 * Recebe: nada. Devolve: nada. Chamada de 15 em 15 segundos e quando a pessoa volta para a aba do navegador.
 */
function buscar_com_a_tela_a_vista() {
  // Aba do navegador escondida: nada a fazer agora.
  if (document.hidden) {
    return;
  }
  // À vista: busca.
  buscar_conversas_abertas();
}

/**
 * A conversa aberta de uma empresa, na última resposta do servidor.
 *
 * Recebe: empresa_id (ex.: "EMP001"). Devolve: {empresa_id, sem_resposta, ultima_mensagem_em}, ou null (a conversa
 * está fechada, ainda não tem mensagem ou o sinal ainda não chegou). Usada pela aba Conversa e pela Carteira
 * (js/banco_empresas_conversa.js).
 */
function conversa_aberta_da_empresa(empresa_id) {
  // O sinal ainda não chegou: nenhuma aberta, por enquanto (nunca um exemplo).
  if (window.conversas_abertas === null) {
    return null;
  }
  // Procura a empresa entre as abertas.
  for (const empresa of window.conversas_abertas.empresas) {
    if (empresa.empresa_id === empresa_id) {
      return empresa;
    }
  }
  // Não está entre as abertas.
  return null;
}

/**
 * Liga o sinal: busca agora, de tempos em tempos, ao voltar para a tela e logo depois de uma mensagem gravada.
 *
 * Recebe: nada. Devolve: nada. Aberta como arquivo (o protótipo, sem servidor): fica o exemplo do HTML.
 */
function ligar_sinal_de_conversas() {
  // Sem servidor, não há o que buscar.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // A primeira busca.
  buscar_conversas_abertas();
  // De tempos em tempos, com a tela à vista.
  setInterval(buscar_com_a_tela_a_vista, INTERVALO_DO_SINAL);
  // Ao voltar para a aba do navegador.
  document.addEventListener("visibilitychange", buscar_com_a_tela_a_vista);
  // Logo depois de uma mensagem ou de uma marcação gravada (js/conversas.js).
  document.addEventListener("conversa-gravada", buscar_conversas_abertas);
}

// Quando o HTML terminar de carregar, liga o sinal.
document.addEventListener("DOMContentLoaded", ligar_sinal_de_conversas);
