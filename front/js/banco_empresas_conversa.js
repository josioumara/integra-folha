/*
  banco_empresas_conversa.js — a aba "Conversa" da ficha da empresa no Portal Interno.

  Para que serve: o especialista lê e responde, na ficha de cada empresa, as dúvidas que ela manda pelo "Posso
  ajudar?" do Portal Empresa. Cada conversa fica na ficha da própria empresa (ADR-122). É conversa ENTRE PESSOAS:
  nenhuma IA responde pelo banco. Este arquivo:
    1. mostra a conversa da empresa aberta: as bolhas (quem escreveu, quando e "Sobre: <tela>"), a situação (sem
       resposta, atrasada, respondida ou resolvida) e a caixa para escrever;
    2. deixa o especialista escrever para a empresa (a mensagem aparece no "Posso ajudar?" dela). O botão diz
       "Responder" quando a última mensagem é da empresa e "Enviar" quando é dele ou quando a conversa ainda está
       vazia: aí é ele quem começa. As "Respostas prontas" só preenchem a caixa: o especialista revisa e decide enviar;
    3. deixa o especialista marcar a conversa como respondida: o botão fica em cima do chat, no canto direito, só com a
       conversa aberta, e some depois de marcada;
    4. põe a bolinha das conversas abertas na aba "Conversa" (que fica no canto direito das abas) e na linha de cada
       empresa da Carteira, à esquerda. Aberta é a conversa sem resposta do especialista ou ainda não marcada como
       respondida; o número é 1 (a conversa daquela empresa), e o total fica no menu, ao lado de "Empresas". As
       bolinhas vêm do js/sinal_de_conversas.js (evento "conversas-abertas-atualizadas"): o mesmo dado do menu;
    5. mostra, acima da lista, o prazo de resposta de 1 dia útil da carteira (ADR-94).

  Depende de: js/conversas.js (guarda e lê as conversas, desenha as bolhas e as busca de novo no servidor a cada 15
  segundos), js/sinal_de_conversas.js (as conversas abertas) e js/banco_empresas.js (a ficha: chama
  mostrar_conversa_da_empresa quando uma empresa é aberta, e atualizar_selos_de_mensagens quando monta a Carteira).

  A atualização automática nunca apaga o que o especialista está digitando: redesenha as bolhas e as bolinhas, mas não
  toca na caixa. A caixa só é limpa quando a mensagem é enviada ou quando outra empresa é aberta.

  Aberta como arquivo (o protótipo), as conversas são as de exemplo do js/conversas.js e quem responde é o Rafael Lima.
  Servida pela aplicação, as conversas de exemplo nunca aparecem: a situação e as bolhas esperam, com a barra cinza
  (js/carregando_dados.js), até as conversas do servidor chegarem (evento "conversas-carregadas"). Se o servidor
  falhar (evento "conversas-indisponiveis"), entra o aviso "Não foi possível carregar agora." e um traço na situação.
*/

// Nome de quem responde pelo banco no protótipo (página aberta como arquivo, sem servidor).
const AUTOR_DO_BANCO_NO_PROTOTIPO = "Rafael Lima";

// O aviso que substitui a conversa quando o servidor não respondeu.
const AVISO_DE_CONVERSA_INDISPONIVEL = "Não foi possível carregar agora.";

// O número da bolinha de uma empresa: a conversa aberta dela (cada empresa tem uma conversa só).
const NUMERO_DA_BOLINHA_DA_EMPRESA = "1";

/**
 * Diz se a página foi servida pela aplicação (e não aberta como arquivo, com dois cliques).
 *
 * Recebe: nada. Devolve: true ou false. Exemplo: "http://localhost:8000/banco_empresas.html" → true.
 */
function pagina_servida_pelo_servidor() {
  // "http:" ou "https:": veio do servidor; "file:": aberta como arquivo.
  return window.location.protocol.startsWith("http");
}

// O que a aba está mostrando agora.
const estado_da_conversa = {
  empresa_id: null,                                   // a empresa da ficha (ex.: "EMP001"; no protótipo, "aurora")
  nome_da_empresa: "",                                // o nome dela, para o aviso de conversa vazia
  conversas_prontas: !pagina_servida_pelo_servidor(), // no protótipo, as de exemplo já servem; com servidor, esperam
  indisponivel: false,                                // true quando o servidor não entregou as conversas
  mensagens_mostradas: -1,                            // quantas bolhas estão na tela (para rolar só quando chega nova)
};

// As empresas esperando resposta há mais de 1 dia útil (vêm do servidor; vazio sem servidor).
let empresas_com_resposta_atrasada = new Set();

// ===== 1. A situação da conversa =====

/**
 * Diz se a conversa já pode ser desenhada: no protótipo, sempre; com servidor, só depois que as fichas reais das
 * empresas e as conversas do servidor chegaram (antes disso, a tela espera com a barra cinza).
 *
 * Recebe: nada. Devolve: true ou false.
 */
function conversa_pode_ser_desenhada() {
  // Protótipo: as conversas de exemplo servem.
  if (!pagina_servida_pelo_servidor()) {
    return true;
  }
  // Com servidor: as fichas reais (js/banco_empresas_real.js) e as conversas do servidor precisam ter chegado.
  return modo_real_das_empresas() && estado_da_conversa.conversas_prontas;
}

/**
 * Diz a situação da conversa, com o texto e a cor do selo.
 *
 * Recebe: conversa. Devolve: { texto, classe }.
 */
function selo_da_conversa(conversa) {
  // Resolvida: verde.
  if (conversa.resolvida) {
    return { texto: "Resolvida", classe: "selo-sucesso" };
  }
  // Esperando o banco há mais de 1 dia útil: cor da marca (ADR-94).
  if (conversa_espera_o_banco(conversa) && empresas_com_resposta_atrasada.has(conversa.id)) {
    return { texto: "Atrasada", classe: "selo-marca" };
  }
  // Esperando o banco: laranja.
  if (conversa_espera_o_banco(conversa)) {
    return { texto: "Sem resposta", classe: "selo-atencao" };
  }
  // O banco respondeu e a empresa ainda não voltou: cinza.
  return { texto: "Respondida", classe: "selo-neutro" };
}

/**
 * O nome do botão de mandar: "Responder" quando a última mensagem é da empresa (ela espera a resposta) e "Enviar"
 * quando é do especialista ou quando a conversa ainda está vazia.
 *
 * Recebe: conversa (ou null, quando a empresa nunca escreveu). Devolve: o texto do botão.
 * Exemplos: empresa, banco, empresa → "Responder"; empresa, banco → "Enviar"; sem mensagens → "Enviar".
 */
function nome_do_botao_de_mandar(conversa) {
  // Conversa vazia (ou que ainda não existe): quem começa é o especialista.
  if (!conversa || conversa.mensagens.length === 0) {
    return "Enviar";
  }
  // A última mensagem da conversa.
  const ultima = conversa.mensagens[conversa.mensagens.length - 1];
  // A empresa falou por último: é uma resposta.
  if (ultima.de === "empresa") {
    return "Responder";
  }
  // O especialista falou por último: é mais uma mensagem dele.
  return "Enviar";
}

/**
 * Acerta a caixa de escrever para a conversa: o nome do botão e a frase de dentro da caixa (sem mexer no texto
 * digitado).
 *
 * Recebe: conversa (ou null). Devolve: nada.
 */
function acertar_caixa_de_escrever(conversa) {
  // "Responder" ou "Enviar".
  const nome_do_botao = nome_do_botao_de_mandar(conversa);
  document.querySelector("[data-botao-de-mandar]").textContent = nome_do_botao;
  // A frase de dentro da caixa acompanha o botão: resposta ou mensagem.
  let frase_da_caixa = "Escreva a sua mensagem";
  if (nome_do_botao === "Responder") {
    frase_da_caixa = "Escreva a sua resposta";
  }
  document.querySelector("[data-texto-banco]").placeholder = frase_da_caixa;
}

// ===== 2. As bolinhas das conversas abertas: na Carteira e na aba =====

/**
 * A dica da bolinha de uma empresa (aparece ao passar o mouse).
 *
 * Recebe: aberta — a conversa aberta da empresa ({empresa_id, sem_resposta, ultima_mensagem_em}). Devolve: o texto.
 * Exemplos: "Conversa aberta: esperando a sua resposta · atrasada (mais de 1 dia útil)";
 * "Conversa aberta: você já respondeu; falta marcar como respondida".
 */
function dica_da_bolinha_da_empresa(aberta) {
  // O especialista já respondeu e ainda não marcou.
  let dica = "Conversa aberta: você já respondeu; falta marcar como respondida";
  // A empresa espera a resposta dele.
  if (aberta.sem_resposta) {
    dica = "Conversa aberta: esperando a sua resposta";
  }
  // Esperando há mais de 1 dia útil (ADR-94): a dica avisa.
  if (aberta.sem_resposta && empresas_com_resposta_atrasada.has(aberta.empresa_id)) {
    dica = dica + " · atrasada (mais de 1 dia útil)";
  }
  // Devolve a dica pronta.
  return dica;
}

/**
 * Escreve na bolinha o que ela diz: o número, a dica e se a empresa espera a resposta do especialista.
 *
 * Recebe: bolinha — o elemento; aberta — a conversa aberta da empresa. Devolve: nada.
 * A marca data-sinal-conversa ("sem-resposta" ou "respondida") serve aos roteiros de clique.
 */
function escrever_bolinha_da_empresa(bolinha, aberta) {
  // O número: a conversa aberta desta empresa.
  bolinha.textContent = NUMERO_DA_BOLINHA_DA_EMPRESA;
  // A dica ao passar o mouse.
  bolinha.title = dica_da_bolinha_da_empresa(aberta);
  // Esperando o especialista, ou esperando ele marcar como respondida.
  let espera = "respondida";
  if (aberta.sem_resposta) {
    espera = "sem-resposta";
  }
  bolinha.setAttribute("data-sinal-conversa", espera);
}

/**
 * Põe (ou tira) a bolinha da conversa aberta em cada empresa da Carteira, à esquerda.
 *
 * Recebe: nada. Devolve: nada. Chamada pelo js/banco_empresas.js a cada vez que a Carteira é montada e aqui, a cada
 * sinal novo das conversas abertas. Mexe só na bolinha de cada linha: a busca e o resto da lista ficam como estão.
 * O nome ficou o de antes (quando era o selo das mensagens), porque o js/banco_empresas.js chama por ele.
 */
function atualizar_selos_de_mensagens() {
  // Passa por cada empresa da Carteira.
  for (const botao of document.querySelectorAll("[data-lista-empresas] [data-abrir-empresa]")) {
    // A conversa aberta desta empresa (null: fechada, sem mensagem ou o sinal ainda não chegou).
    const aberta = conversa_aberta_da_empresa(botao.dataset.abrirEmpresa);
    // A bolinha que a linha já tem (ou null).
    let bolinha = botao.querySelector("[data-sinal-conversa]");
    // Conversa fechada: a bolinha some, e a linha volta ao espaço de sempre.
    if (!aberta) {
      if (bolinha) {
        bolinha.remove();
      }
      botao.classList.remove("linha-com-conversa-aberta");
      continue;
    }
    // Primeira vez: cria a bolinha no fim da linha (o css/banco_ficha.css a põe no canto de cima, à direita).
    if (!bolinha) {
      bolinha = document.createElement("span");
      bolinha.className = "contador-aba bolinha-da-carteira";
      botao.append(bolinha);
    }
    // A linha abre espaço para a bolinha, e a bolinha diz o que é.
    botao.classList.add("linha-com-conversa-aberta");
    escrever_bolinha_da_empresa(bolinha, aberta);
  }
}

/**
 * Mostra (ou esconde) a bolinha na aba "Conversa" da empresa aberta.
 *
 * Recebe: nada. Devolve: nada. A bolinha some com a conversa fechada, vazia ou antes de o sinal chegar.
 */
function atualizar_bolinha_da_aba_conversa() {
  // A bolinha da aba (já está no HTML, escondida).
  const bolinha = document.querySelector("[data-contador-conversa]");
  // A conversa aberta da empresa da ficha (ou null).
  const aberta = conversa_aberta_da_empresa(estado_da_conversa.empresa_id);
  // Fechada: some.
  if (!aberta) {
    bolinha.hidden = true;
    bolinha.removeAttribute("data-sinal-conversa");
    return;
  }
  // Aberta: o número, a dica e a marca, à vista.
  escrever_bolinha_da_empresa(bolinha, aberta);
  bolinha.hidden = false;
}

/**
 * O sinal das conversas abertas chegou (ou mudou): redesenha as bolinhas da Carteira e da aba.
 *
 * Recebe: nada. Devolve: nada. Chamada pelo evento "conversas-abertas-atualizadas" (js/sinal_de_conversas.js).
 */
function quando_o_sinal_chega() {
  atualizar_selos_de_mensagens();
  atualizar_bolinha_da_aba_conversa();
}

// ===== 3. A conversa da empresa aberta =====

/**
 * Abre a conversa de uma empresa (chamada pelo js/banco_empresas.js quando a ficha muda de empresa).
 *
 * Recebe: empresa — a da ficha (com id e nome). Devolve: nada.
 * Trocou de empresa: a caixa é limpa (o texto era para a outra empresa). A mesma empresa de novo (ex.: depois de
 * editar os dados, a ficha é reaberta): a caixa fica como está.
 */
function mostrar_conversa_da_empresa(empresa) {
  // Outra empresa: limpa a caixa e o aviso de erro, e a próxima conversa rola até o fim.
  if (empresa.id !== estado_da_conversa.empresa_id) {
    document.querySelector("[data-texto-banco]").value = "";
    document.querySelector("[data-erro-banco]").hidden = true;
    estado_da_conversa.mensagens_mostradas = -1;
  }
  // Guarda qual empresa está aberta.
  estado_da_conversa.empresa_id = empresa.id;
  estado_da_conversa.nome_da_empresa = empresa.nome;
  // A bolinha da aba é a desta empresa.
  atualizar_bolinha_da_aba_conversa();
  // Desenha a conversa (ou espera, se as conversas do servidor ainda não chegaram).
  desenhar_conversa_aberta();
}

/**
 * Mostra a aba de uma empresa que ainda não escreveu: o aviso no lugar das bolhas e a caixa para o especialista
 * começar a conversa, com o botão "Enviar".
 *
 * Recebe: nada. Devolve: nada. Sem conversa, não há o que marcar como respondida nem respostas prontas.
 */
function mostrar_conversa_vazia() {
  // O selo: nenhuma mensagem ainda.
  const selo = document.querySelector("[data-conversa-situacao]");
  selo.className = "selo selo-neutro";
  selo.textContent = "Nenhuma mensagem";
  // O aviso no lugar das bolhas.
  const aviso = document.createElement("p");
  aviso.className = "painel-vazio painel-vazio-neutro";
  aviso.textContent = estado_da_conversa.nome_da_empresa + " ainda não escreveu pelo \"Posso ajudar?\". " +
    "Se quiser, comece a conversa: a sua mensagem aparece para a empresa no mesmo lugar.";
  document.querySelector("[data-mensagens-banco]").replaceChildren(aviso);
  estado_da_conversa.mensagens_mostradas = 0;
  // Nada a marcar como respondida.
  document.querySelector("[data-marcar-respondida]").hidden = true;
  // A caixa aparece para começar a conversa, sem as respostas prontas (não há o que responder).
  document.querySelector("[data-formulario-banco]").hidden = false;
  document.querySelector("[data-respostas-prontas]").hidden = true;
  acertar_caixa_de_escrever(null);
}

/**
 * Desenha a conversa da empresa aberta: a situação, as bolhas e a caixa de escrever.
 *
 * Recebe: nada. Devolve: nada. Não mexe no texto que está sendo digitado na caixa.
 */
function desenhar_conversa_aberta() {
  // O servidor não entregou as conversas: fica o aviso (redesenhar traria as de exemplo do navegador).
  if (estado_da_conversa.indisponivel) {
    return;
  }
  // As conversas ainda não chegaram: a aba continua esperando, com a barra cinza.
  if (!conversa_pode_ser_desenhada()) {
    return;
  }
  // A conversa da empresa aberta, lida do que está guardado agora.
  const conversa = achar_conversa(ler_conversas(), estado_da_conversa.empresa_id);
  // Nenhuma conversa (a empresa ainda não escreveu, e o especialista também não): a aba vazia.
  if (!conversa || conversa.mensagens.length === 0) {
    mostrar_conversa_vazia();
  } else {
    desenhar_bolhas_e_situacao(conversa);
  }
  // A situação e as bolhas já são as de verdade: saem da espera (js/carregando_dados.js).
  marcar_todos_como_carregados("[data-conversa-situacao], [data-mensagens-banco]");
}

/**
 * Desenha uma conversa com mensagens: o selo da situação, o "Marcar como respondida", as bolhas e a caixa.
 *
 * Recebe: conversa. Devolve: nada.
 */
function desenhar_bolhas_e_situacao(conversa) {
  // Selo da situação.
  const situacao = selo_da_conversa(conversa);
  const selo = document.querySelector("[data-conversa-situacao]");
  selo.className = "selo " + situacao.classe;
  selo.textContent = situacao.texto;
  // "Marcar como respondida": só com a conversa aberta; depois de marcada, some.
  document.querySelector("[data-marcar-respondida]").hidden = conversa.resolvida;
  // O lugar das bolhas e onde a pessoa estava lendo (para não pular de lugar numa atualização sem novidade).
  const lugar = document.querySelector("[data-mensagens-banco]");
  const posicao_da_leitura = lugar.scrollTop;
  lugar.replaceChildren();
  // Uma bolha por mensagem; na tela do banco, "minha" é a mensagem do banco.
  for (const mensagem of conversa.mensagens) {
    lugar.append(montar_bolha(mensagem, mensagem.de === "banco"));
  }
  // Chegou mensagem nova (ou a conversa acabou de abrir): rola até a última. Senão, fica onde a pessoa estava.
  if (conversa.mensagens.length !== estado_da_conversa.mensagens_mostradas) {
    lugar.scrollTop = lugar.scrollHeight;
  } else {
    lugar.scrollTop = posicao_da_leitura;
  }
  estado_da_conversa.mensagens_mostradas = conversa.mensagens.length;
  // A caixa aparece, com as respostas prontas (o texto que já estava nela fica).
  document.querySelector("[data-formulario-banco]").hidden = false;
  document.querySelector("[data-respostas-prontas]").hidden = false;
  // "Responder" ou "Enviar", conforme quem falou por último.
  acertar_caixa_de_escrever(conversa);
}

// ===== 4. Escrever e marcar como respondida =====

/**
 * Quem assina a mensagem na bolha que aparece na hora (antes de o servidor devolver a conversa gravada).
 *
 * Recebe: nada. Devolve: o nome. Com servidor, é quem entrou (o nome do cabeçalho), nunca o nome de exemplo;
 * aberta como arquivo, o especialista do protótipo. Ex.: "teste.banco".
 */
function autor_da_resposta() {
  // Sem servidor (protótipo): o nome de exemplo.
  if (!pagina_servida_pelo_servidor()) {
    return AUTOR_DO_BANCO_NO_PROTOTIPO;
  }
  // Com servidor: o login de quem entrou, já escrito no cabeçalho por js/cabecalho_real.js.
  return document.querySelector(".nome-usuario").textContent;
}

/**
 * Manda a mensagem do especialista para a empresa aberta: uma resposta ou o começo da conversa.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
function mandar_para_a_empresa(evento) {
  // Impede o envio padrão do formulário (a página não recarrega).
  evento.preventDefault();
  // A caixa e o texto escrito.
  const caixa = document.querySelector("[data-texto-banco]");
  const texto = caixa.value.trim();
  // Mensagem vazia: avisa e não manda.
  if (texto === "") {
    document.querySelector("[data-erro-banco]").hidden = false;
    return;
  }
  // Esconde o aviso de mensagem vazia de antes.
  document.querySelector("[data-erro-banco]").hidden = true;
  // Guarda a mensagem na conversa (com servidor, grava na aplicação e busca a conversa de novo). O nome da empresa
  // só é usado quando a conversa ainda não existe (o especialista começando).
  acrescentar_mensagem(estado_da_conversa.empresa_id,
    { de: "banco", autor: autor_da_resposta(), contexto: "", texto: texto }, estado_da_conversa.nome_da_empresa);
  // Limpa a caixa: a mensagem já foi.
  caixa.value = "";
  // Redesenha a conversa com a mensagem (as bolinhas mudam quando o sinal chega, logo depois de gravar).
  desenhar_conversa_aberta();
}

/**
 * Marca a conversa da empresa aberta como respondida (no servidor, "resolvida").
 *
 * Recebe: nada. Devolve: nada.
 */
function marcar_conversa_aberta_como_respondida() {
  // Sem conversa (a empresa ainda não escreveu): nada a marcar.
  if (!achar_conversa(ler_conversas(), estado_da_conversa.empresa_id)) {
    return;
  }
  // A conversa vira resolvida (com servidor, gravada na aplicação; js/conversas.js).
  marcar_conversa_resolvida(estado_da_conversa.empresa_id);
  // Redesenha o selo e o botão, que some (as bolinhas mudam quando o sinal chega, logo depois de gravar).
  desenhar_conversa_aberta();
}

/**
 * Trata os cliques da aba Conversa: respostas prontas e "Marcar como respondida".
 *
 * Recebe: evento — o clique. Devolve: nada.
 */
function tratar_clique_na_conversa(evento) {
  // O botão clicado (o clique pode cair num texto ou ícone dentro do botão).
  const botao = evento.target.closest("button");
  // Fora de botão: nada a fazer.
  if (!botao) {
    return;
  }
  // Resposta pronta: só preenche a caixa (o especialista revisa antes de enviar).
  if (botao.dataset.respostaPronta) {
    const caixa = document.querySelector("[data-texto-banco]");
    caixa.value = botao.dataset.respostaPronta;
    caixa.focus();
    return;
  }
  // Marcar como respondida.
  if (botao.hasAttribute("data-marcar-respondida")) {
    marcar_conversa_aberta_como_respondida();
  }
}

// ===== 5. Prazo de resposta de 1 dia útil (ADR-94) =====

/**
 * Monta o texto do resumo do prazo, com singular e plural certos.
 *
 * Recebe: prazo — de /api/banco/conversas/prazo. Devolve: o texto.
 * Exemplo: "Prazo de 1 dia útil: 9 de 10 perguntas respondidas no prazo (90%) · 1 atrasada".
 */
function texto_do_prazo(prazo) {
  // Nenhuma pergunta respondida ainda.
  let texto = "Prazo de 1 dia útil: nenhuma pergunta respondida ainda";
  // Com respostas: quantas dentro do prazo.
  if (prazo.respondidas === 1) {
    texto = "Prazo de 1 dia útil: " + prazo.no_prazo + " de 1 pergunta respondida no prazo (" +
      prazo.percentual_no_prazo + "%)";
  }
  if (prazo.respondidas > 1) {
    texto = "Prazo de 1 dia útil: " + prazo.no_prazo + " de " + prazo.respondidas + " perguntas respondidas no prazo (" +
      prazo.percentual_no_prazo + "%)";
  }
  // As que passaram do prazo, no singular ou no plural.
  if (prazo.atrasadas === 1) {
    texto = texto + " · 1 atrasada";
  }
  if (prazo.atrasadas > 1) {
    texto = texto + " · " + prazo.atrasadas + " atrasadas";
  }
  // Devolve o texto pronto.
  return texto;
}

/**
 * Busca o prazo de resposta de 1 dia útil e mostra o resumo acima da lista das empresas.
 *
 * Recebe: nada. Devolve: nada. Sem servidor, o resumo fica escondido.
 */
async function carregar_prazo_das_respostas() {
  // try/catch: servidor fora do ar não quebra a tela (o resumo só não aparece).
  let prazo = null;
  try {
    const resposta = await fetch("/api/banco/conversas/prazo");
    // Recusado: o resumo continua como estava.
    if (!resposta.ok) {
      return;
    }
    prazo = await resposta.json();
  } catch (erro) {
    return;
  }
  // As empresas atrasadas (para o selo "Atrasada" e a dica das bolinhas).
  empresas_com_resposta_atrasada = new Set(prazo.atrasadas_por_empresa);
  // O resumo acima da lista.
  const resumo = document.querySelector("[data-prazo-respostas]");
  resumo.textContent = texto_do_prazo(prazo);
  resumo.hidden = false;
  // Redesenha a situação da conversa aberta e as dicas das bolinhas, com as atrasadas.
  desenhar_conversa_aberta();
  quando_o_sinal_chega();
}

// ===== 6. Servidor: as conversas chegaram (ou não) =====

/**
 * As conversas do servidor chegaram (primeira vez ou a atualização de 15 em 15 segundos): redesenha a conversa aberta,
 * sem tocar no que está sendo digitado.
 *
 * Recebe: nada. Devolve: nada.
 */
function quando_as_conversas_chegam() {
  // As conversas de verdade chegaram: a aba volta a desenhar (mesmo depois de uma falha).
  estado_da_conversa.conversas_prontas = true;
  estado_da_conversa.indisponivel = false;
  // Redesenha a conversa aberta.
  desenhar_conversa_aberta();
  // O prazo muda quando uma conversa muda (resposta nova, conversa resolvida).
  carregar_prazo_das_respostas();
}

/**
 * O servidor não entregou as conversas: o aviso no lugar das bolhas e um traço na situação. Nunca as de exemplo.
 *
 * Recebe: nada. Devolve: nada. Se a conversa de verdade já está na tela (ex.: a atualização automática falhou uma
 * vez), ela fica como está.
 */
function quando_as_conversas_falham() {
  // A conversa do servidor já está na tela: mantém.
  if (estado_da_conversa.conversas_prontas) {
    return;
  }
  // Daqui em diante, redesenhar fica desligado (traria o exemplo do navegador).
  estado_da_conversa.indisponivel = true;
  // A situação: um traço, sem cor.
  const selo = document.querySelector("[data-conversa-situacao]");
  selo.className = "selo selo-neutro";
  mostrar_dado_indisponivel(selo);
  // As bolhas: só o aviso.
  const aviso = document.createElement("p");
  aviso.className = "painel-vazio";
  aviso.textContent = AVISO_DE_CONVERSA_INDISPONIVEL;
  const lugar = document.querySelector("[data-mensagens-banco]");
  lugar.replaceChildren(aviso);
  marcar_como_carregado(lugar);
  // Sem conversa, não há o que escrever nem marcar.
  document.querySelector("[data-formulario-banco]").hidden = true;
  document.querySelector("[data-marcar-respondida]").hidden = true;
}

/**
 * Prepara a aba Conversa: liga o formulário, os cliques e a escuta das conversas e do sinal.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_aba_conversa() {
  // Envio da mensagem.
  document.querySelector("[data-formulario-banco]").addEventListener("submit", mandar_para_a_empresa);
  // Os cliques da aba (respostas prontas e "Marcar como respondida").
  document.querySelector("[data-conteudo-aba='conversa']").addEventListener("click", tratar_clique_na_conversa);
  // Com servidor, quando as conversas chegam (ou são atualizadas), redesenha mantendo o texto da caixa.
  document.addEventListener("conversas-carregadas", quando_as_conversas_chegam);
  // Com servidor, se as conversas não vieram: o aviso, nunca as de exemplo.
  document.addEventListener("conversas-indisponiveis", quando_as_conversas_falham);
  // O sinal das conversas abertas chegou ou mudou: as bolinhas da Carteira e da aba (js/sinal_de_conversas.js).
  document.addEventListener("conversas-abertas-atualizadas", quando_o_sinal_chega);
}

// Quando o HTML terminar de carregar, prepara a aba.
document.addEventListener("DOMContentLoaded", preparar_aba_conversa);
