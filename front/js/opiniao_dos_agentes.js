/*
  opiniao_dos_agentes.js — o joinha (para cima e para baixo) nas respostas dos agentes de IA (ADR-151; servidor em
  services/opiniao_dos_agentes.py).

  Para que serve: quem usa o sistema diz, com um clique, se a resposta de um agente ajudou. O banco acompanha a
  satisfação de cada agente na tela Acompanhamento dos agentes (js/banco_opiniao_dos_agentes.js), só com números.

  Onde o joinha aparece:
    - Portal Empresa (Cadastrar e Acompanhar, também na janela da conversa e em "Resolvidas"): embaixo de cada resposta
      do Agente de validação, e embaixo da pergunta que o Agente Leitor ou o Agente Conferidor fez ao ler o documento
      (a pendência "PERGUNTA_DA_IA:<campo>"). Os ganchos ficam em js/assistente_de_correcao.js: montar_fala chama
      acrescentar_opiniao_na_resposta; montar_baloes e desenhar_conversa_resolvida chamam
      acrescentar_opiniao_na_pergunta;
    - Portal Interno (aba Endomarketing): no rascunho e na janela "Ver" de cada material, sobre o texto que o Agente de
      Endomarketing escreveu (js/banco_endomarketing.js chama mostrar_opiniao_do_material).

  Como funciona:
    - a pergunta curta ("Esta resposta ajudou?") e os dois botões, com o desenho da mão (não é emoji: fica igual em
      todo computador). O clique grava na hora, e o botão escolhido fica colorido (aria-pressed diz isso aos leitores
      de tela);
    - clicar no outro joinha troca o voto; clicar de novo no joinha marcado retira o voto (um voto por pessoa, nunca
      dois);
    - depois do joinha para baixo, abre "O que faltou? (opcional)", com até 200 letras, "Enviar" e "Agora não". Sem
      comentário, fica o link "Contar o que faltou" para abrir de novo. Enviado, o comentário fica à vista embaixo do
      joinha ("Seu comentário: "…""), com o "Editar"; só quem votou o vê (o banco vê só quantos comentários há);
    - o resultado aparece ao lado dos botões, à vista: "Obrigado pela opinião.", "Voto retirado.", "Comentário
      enviado." ou o erro.

  Os votos já dados: na primeira vez em que um joinha aparece, a tela pede ao servidor os votos desta pessoa naquele
  envio (empresa) ou nos materiais daquela empresa (banco), uma vez só, e marca os botões. A conversa é redesenhada
  muitas vezes (a cada resposta e a cada atualização da lista): o joinha é refeito a partir desta memória, sem pedir de
  novo, e o comentário ainda não enviado volta como estava. Um clique no joinha não refaz a lista nem a conversa: só o
  próprio joinha muda.
  Página aberta como arquivo (o protótipo): o joinha não aparece, porque não há servidor para guardar o voto.

  Uso:
    acrescentar_opiniao_na_resposta(balao, pendencia, fala);   // fala: {quem: "ia", ordem, ...}
    acrescentar_opiniao_na_pergunta(balao, pendencia);          // só quando a pendência é uma pergunta da leitura
    mostrar_opiniao_do_material(lugar, empresa_id, material);   // material: {material_id, ...}
*/

// Os tipos de interação, os mesmos do servidor
const TIPO_RESPOSTA_DA_CONVERSA = "resposta_da_conversa";
const TIPO_PERGUNTA_DA_LEITURA = "pergunta_da_leitura";
const TIPO_MATERIAL_DO_ENDOMARKETING = "material_do_endomarketing";
// Os dois votos
const VOTO_PARA_CIMA = "para_cima";
const VOTO_PARA_BAIXO = "para_baixo";
// O começo da regra das perguntas da leitura (a pendência "PERGUNTA_DA_IA:cpf", services/validador.py)
const REGRA_DA_PERGUNTA_DA_LEITURA = "PERGUNTA_DA_IA:";
// O começo da chave de uma conversa de grupo (a pergunta do grupo não é de um agente da leitura)
const COMECO_DA_CHAVE_DO_GRUPO = "grupo|";
// O maior comentário (o mesmo limite do servidor)
const TAMANHO_MAXIMO_DO_COMENTARIO_DO_JOINHA = 200;
// O desenho de cada mão, em contorno como os outros ícones do sistema (os traços do conjunto de ícones Feather, de uso
// livre, licença MIT)
const DESENHO_DO_JOINHA = {
  para_cima: "M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 " +
    "2 0 0 1 2-2h3",
  para_baixo: "M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 " +
    "4v7a2.31 2.31 0 0 1-2.33 2H17",
};
// O nome de cada botão para quem usa leitor de tela
const NOME_DO_BOTAO_DO_JOINHA = { para_cima: "Sim, ajudou", para_baixo: "Não ajudou" };
// Os avisos que aparecem ao lado dos botões
const AVISO_DO_VOTO = "Obrigado pela opinião.";
const AVISO_DO_VOTO_RETIRADO = "Voto retirado.";
const AVISO_DO_COMENTARIO = "Comentário enviado. Obrigado!";
const AVISO_DE_FALHA_DO_JOINHA = "Não foi possível registrar agora. Tente de novo.";

// Os votos já conhecidos desta pessoa, pela chave "<tipo>|<referencia>": {voto, comentario}
const opinioes_conhecidas = {};
// O estado de cada joinha na tela, pela mesma chave: {enviando, aviso, erro, comentario_aberto, rascunho}
const estados_dos_joinhas = {};
// As listas de votos já pedidas ao servidor (pelo endereço), para pedir uma vez só
const listas_de_opinioes_pedidas = {};

/**
 * Diz se o joinha funciona nesta página: só servida pela aplicação (http ou https), nunca aberta como arquivo.
 *
 * Recebe: nada. Devolve: true ou false.
 */
function joinha_funciona_aqui() {
  return window.location.protocol.startsWith("http");
}

/**
 * A chave de um joinha: o tipo e a referência juntos. Ex.: "pergunta_da_leitura|a1b2|4|cpf".
 *
 * Recebe: opcoes — {tipo, referencia, ...}. Devolve: o texto.
 */
function chave_do_joinha(opcoes) {
  return opcoes.tipo + "|" + opcoes.referencia;
}

/**
 * O estado de um joinha na tela (criado vazio na primeira vez).
 *
 * Recebe: chave. Devolve: {enviando, aviso, erro, comentario_aberto, rascunho}.
 */
function estado_do_joinha(chave) {
  if (!(chave in estados_dos_joinhas)) {
    estados_dos_joinhas[chave] = { enviando: false, aviso: "", erro: false, comentario_aberto: false, rascunho: "" };
  }
  return estados_dos_joinhas[chave];
}

/**
 * O voto já conhecido desta pessoa num joinha, ou null.
 *
 * Recebe: chave. Devolve: "para_cima", "para_baixo" ou null.
 */
function voto_conhecido(chave) {
  if (chave in opinioes_conhecidas) {
    return opinioes_conhecidas[chave].voto;
  }
  return null;
}

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro).
 *
 * Recebe: etiqueta; classe ("" = nenhuma); texto ("" = nenhum). Devolve: o elemento.
 */
function criar_elemento_do_joinha(etiqueta, classe, texto) {
  const elemento = document.createElement(etiqueta);
  if (classe) {
    elemento.className = classe;
  }
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * O desenho de uma mão (joinha para cima ou para baixo), no idioma do SVG.
 *
 * Recebe: voto — "para_cima" ou "para_baixo". Devolve: o elemento <svg>.
 */
function desenho_do_joinha(voto) {
  const endereco_do_svg = "http://www.w3.org/2000/svg";
  const desenho = document.createElementNS(endereco_do_svg, "svg");
  desenho.setAttribute("class", "icone joinha-icone");
  desenho.setAttribute("viewBox", "0 0 24 24");
  // O desenho é só enfeite: o nome do botão diz o que ele faz
  desenho.setAttribute("aria-hidden", "true");
  const traco = document.createElementNS(endereco_do_svg, "path");
  traco.setAttribute("d", DESENHO_DO_JOINHA[voto]);
  desenho.append(traco);
  return desenho;
}

// ===== Os votos já dados (pedidos ao servidor uma vez) =====

/**
 * Pede ao servidor os votos desta pessoa numa lista (um envio ou os materiais de uma empresa), uma vez só, e marca os
 * joinhas que já estão na tela.
 *
 * Recebe: endereco — a rota da lista. Devolve: uma promessa (termina quando a lista chega, ou logo, se já foi pedida).
 */
async function carregar_opinioes(endereco) {
  // Já pedida (ou a caminho): nada a fazer
  if (endereco in listas_de_opinioes_pedidas) {
    return;
  }
  listas_de_opinioes_pedidas[endereco] = true;
  // try/catch: servidor fora do ar deixa os botões sem marca (a pessoa ainda pode votar)
  try {
    const resposta = await fetch(endereco);
    if (!resposta.ok) {
      return;
    }
    const dados = await resposta.json();
    for (const opiniao of dados.opinioes) {
      opinioes_conhecidas[opiniao.tipo + "|" + opiniao.referencia] = { voto: opiniao.voto, comentario: opiniao.comentario };
    }
  } catch (erro) {
    return;
  }
  redesenhar_os_joinhas("");
}

/**
 * Redesenha os joinhas da tela (todos, ou só os de uma chave), sem mexer no resto da conversa.
 *
 * Recebe: chave — a de um joinha, ou "" para todos. Devolve: nada.
 */
function redesenhar_os_joinhas(chave) {
  for (const elemento of document.querySelectorAll("[data-joinha]")) {
    if (chave === "" || elemento.dataset.joinha === chave) {
      desenhar_joinha(elemento);
    }
  }
}

// ===== O joinha =====

/**
 * Monta um joinha: a pergunta curta, os dois botões e, quando for o caso, o comentário e o aviso.
 *
 * Recebe: opcoes — {tipo, referencia, pergunta (ex.: "Esta resposta ajudou?"), endereco_do_voto,
 * endereco_da_lista}. Devolve: o elemento (vazio até os votos já dados chegarem, se ainda não chegaram).
 */
function montar_joinha(opcoes) {
  const elemento = criar_elemento_do_joinha("div", "joinha", "");
  elemento.dataset.joinha = chave_do_joinha(opcoes);
  // As opções ficam no próprio elemento: redesenhar precisa delas
  elemento.opcoes_do_joinha = opcoes;
  desenhar_joinha(elemento);
  // Os votos já dados desta pessoa (uma vez por lista); quando chegarem, o joinha é redesenhado
  carregar_opinioes(opcoes.endereco_da_lista);
  return elemento;
}

/**
 * Desenha (ou redesenha) um joinha a partir do que está guardado nesta página.
 *
 * Recebe: elemento — o do joinha. Devolve: nada. Se a pessoa estava escrevendo o comentário, o cursor volta para a
 * caixa, no fim do texto.
 */
function desenhar_joinha(elemento) {
  const opcoes = elemento.opcoes_do_joinha;
  const chave = elemento.dataset.joinha;
  const estado = estado_do_joinha(chave);
  const voto = voto_conhecido(chave);
  // O cursor estava na caixa do comentário deste joinha?
  const caixa_de_antes = elemento.querySelector("[data-comentario-do-joinha]");
  const estava_escrevendo = caixa_de_antes !== null && document.activeElement === caixa_de_antes;
  const linha = criar_elemento_do_joinha("div", "joinha-linha", "");
  // role="group": os leitores de tela anunciam os dois botões juntos, com a pergunta como nome
  linha.setAttribute("role", "group");
  linha.setAttribute("aria-label", opcoes.pergunta);
  linha.append(criar_elemento_do_joinha("span", "joinha-pergunta", opcoes.pergunta));
  linha.append(montar_botao_do_joinha(elemento, VOTO_PARA_CIMA, voto, estado));
  linha.append(montar_botao_do_joinha(elemento, VOTO_PARA_BAIXO, voto, estado));
  // Joinha para baixo sem comentário, com a caixa fechada: o link para contar o que faltou
  const tem_comentario = chave in opinioes_conhecidas && Boolean(opinioes_conhecidas[chave].comentario);
  if (voto === VOTO_PARA_BAIXO && !tem_comentario && !estado.comentario_aberto) {
    linha.append(montar_link_do_comentario(elemento));
  }
  // O resultado do último clique, ao lado dos botões (role="status": o leitor de tela lê sozinho)
  const aviso = criar_elemento_do_joinha("span", "joinha-aviso", estado.aviso);
  aviso.setAttribute("role", "status");
  aviso.dataset.avisoDoJoinha = "";
  if (estado.erro) {
    aviso.classList.add("joinha-aviso-erro");
  }
  linha.append(aviso);
  const partes = [linha];
  // O comentário que a pessoa deixou, à vista embaixo do joinha dela, com o "Editar" (com a caixa aberta, ele está nela)
  if (voto === VOTO_PARA_BAIXO && tem_comentario && !estado.comentario_aberto) {
    partes.push(montar_comentario_dado(elemento, opinioes_conhecidas[chave].comentario));
  }
  // Depois do joinha para baixo: a caixa "O que faltou? (opcional)"
  if (estado.comentario_aberto) {
    partes.push(montar_comentario_do_joinha(elemento));
  }
  elemento.replaceChildren(...partes);
  // A pessoa estava escrevendo: o cursor volta para a caixa nova, no fim do texto
  if (estava_escrevendo) {
    focar_a_caixa_do_comentario(elemento);
  }
}

/**
 * Um botão do joinha (para cima ou para baixo), marcado quando é o voto desta pessoa.
 *
 * Recebe: elemento — o do joinha; voto_do_botao; voto — o voto atual (ou null); estado. Devolve: o botão.
 */
function montar_botao_do_joinha(elemento, voto_do_botao, voto, estado) {
  const botao = criar_elemento_do_joinha("button", "joinha-botao joinha-" + voto_do_botao, "");
  botao.type = "button";
  botao.append(desenho_do_joinha(voto_do_botao));
  botao.setAttribute("aria-label", NOME_DO_BOTAO_DO_JOINHA[voto_do_botao]);
  // aria-pressed: o botão "apertado" é o voto desta pessoa (o CSS pinta pelo mesmo atributo)
  botao.setAttribute("aria-pressed", String(voto === voto_do_botao));
  botao.dataset.botaoDoJoinha = voto_do_botao;
  // Enquanto o voto vai ao servidor, os botões ficam parados (um clique duplo não manda dois pedidos)
  botao.disabled = estado.enviando;
  botao.addEventListener("click", function () {
    votar_no_joinha(elemento, voto_do_botao);
  });
  return botao;
}

/**
 * O link "Contar o que faltou", que abre a caixa do comentário (para quem votou para baixo sem comentar).
 *
 * Recebe: elemento — o do joinha. Devolve: o botão com cara de link.
 */
function montar_link_do_comentario(elemento) {
  const link = criar_elemento_do_joinha("button", "botao-nome joinha-link", "Contar o que faltou");
  link.type = "button";
  link.dataset.abrirComentarioDoJoinha = "";
  link.addEventListener("click", function () {
    estado_do_joinha(elemento.dataset.joinha).comentario_aberto = true;
    desenhar_joinha(elemento);
    focar_a_caixa_do_comentario(elemento);
  });
  return link;
}

/**
 * O comentário que a pessoa deixou, embaixo do joinha dela: "Seu comentário: "…"" e o "Editar", que abre a caixa com o
 * texto dentro.
 *
 * Recebe: elemento — o do joinha; comentario — o texto guardado. Devolve: o <p>. O texto entra como texto puro.
 */
function montar_comentario_dado(elemento, comentario) {
  const linha = criar_elemento_do_joinha("p", "joinha-comentario-dado", "");
  linha.dataset.comentarioDadoNoJoinha = "";
  linha.append(criar_elemento_do_joinha("span", "joinha-comentario-dado-rotulo", "Seu comentário: "));
  // <q>: o navegador põe as aspas em volta do texto
  linha.append(criar_elemento_do_joinha("q", "", comentario));
  const editar = criar_elemento_do_joinha("button", "botao-nome joinha-link", "Editar");
  editar.type = "button";
  editar.dataset.editarComentarioDoJoinha = "";
  editar.addEventListener("click", function () {
    const estado = estado_do_joinha(elemento.dataset.joinha);
    // A caixa abre com o comentário de agora, para a pessoa mudar
    estado.rascunho = comentario;
    estado.comentario_aberto = true;
    estado.aviso = "";
    desenhar_joinha(elemento);
    focar_a_caixa_do_comentario(elemento);
  });
  linha.append(" ", editar);
  return linha;
}

/**
 * A caixa "O que faltou? (opcional)", com "Enviar" e "Agora não".
 *
 * Recebe: elemento — o do joinha. Devolve: o <form>.
 */
function montar_comentario_do_joinha(elemento) {
  const chave = elemento.dataset.joinha;
  const estado = estado_do_joinha(chave);
  const formulario = criar_elemento_do_joinha("form", "joinha-comentario", "");
  const rotulo = criar_elemento_do_joinha("label", "joinha-comentario-rotulo", "");
  rotulo.append(criar_elemento_do_joinha("span", "", "O que faltou? (opcional)"));
  const caixa = criar_elemento_do_joinha("input", "campo-entrada campo-pequeno joinha-comentario-caixa", "");
  caixa.type = "text";
  caixa.maxLength = TAMANHO_MAXIMO_DO_COMENTARIO_DO_JOINHA;
  caixa.autocomplete = "off";
  caixa.placeholder = "Ex.: não entendeu o que eu pedi";
  caixa.value = estado.rascunho;
  caixa.dataset.comentarioDoJoinha = "";
  // O que a pessoa escreve fica guardado: volta igual se a conversa for redesenhada
  caixa.addEventListener("input", function () {
    estado.rascunho = caixa.value;
  });
  rotulo.append(caixa);
  const enviar = criar_elemento_do_joinha("button", "botao botao-principal botao-pequeno", "Enviar");
  enviar.type = "submit";
  enviar.disabled = estado.enviando;
  enviar.dataset.enviarComentarioDoJoinha = "";
  const agora_nao = criar_elemento_do_joinha("button", "botao-nome joinha-link", "Agora não");
  agora_nao.type = "button";
  agora_nao.addEventListener("click", function () {
    estado.comentario_aberto = false;
    estado.aviso = "";
    desenhar_joinha(elemento);
  });
  // Enter ou "Enviar": manda o comentário (o formulário não recarrega a página)
  formulario.addEventListener("submit", function (evento) {
    evento.preventDefault();
    enviar_comentario_do_joinha(elemento);
  });
  formulario.append(rotulo, enviar, agora_nao);
  return formulario;
}

/**
 * Põe o cursor na caixa do comentário de um joinha, no fim do texto.
 *
 * Recebe: elemento — o do joinha. Devolve: nada.
 */
function focar_a_caixa_do_comentario(elemento) {
  const caixa = elemento.querySelector("[data-comentario-do-joinha]");
  if (caixa) {
    caixa.focus();
    caixa.setSelectionRange(caixa.value.length, caixa.value.length);
  }
}

// ===== Votar e comentar =====

/**
 * Manda o voto ao servidor e devolve {ok, dados}. Servidor fora do ar vira a mensagem geral.
 *
 * Recebe: opcoes — as do joinha; voto — "para_cima", "para_baixo" ou null (retirar); comentario — ou null.
 * Devolve: uma promessa de {ok, dados}.
 */
async function mandar_o_voto(opcoes, voto, comentario) {
  try {
    const resposta = await fetch(opcoes.endereco_do_voto, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tipo: opcoes.tipo, referencia: opcoes.referencia, voto: voto, comentario: comentario }),
    });
    const dados = await resposta.json();
    return { ok: resposta.ok, dados: dados };
  } catch (erro) {
    return { ok: false, dados: { detail: AVISO_DE_FALHA_DO_JOINHA } };
  }
}

/**
 * O texto do erro que o servidor mandou (uma frase), ou a mensagem geral.
 *
 * Recebe: dados — a resposta do servidor. Devolve: o texto.
 */
function texto_do_erro_do_joinha(dados) {
  if (dados && typeof dados.detail === "string") {
    return dados.detail;
  }
  return AVISO_DE_FALHA_DO_JOINHA;
}

/**
 * O clique num joinha: vota, troca o voto ou, no joinha já marcado, retira o voto.
 *
 * Recebe: elemento — o do joinha; voto_do_botao — o do botão clicado. Devolve: uma promessa.
 * Depois do joinha para baixo, a caixa do comentário abre, com o cursor nela.
 */
async function votar_no_joinha(elemento, voto_do_botao) {
  const opcoes = elemento.opcoes_do_joinha;
  const chave = elemento.dataset.joinha;
  const estado = estado_do_joinha(chave);
  // Um pedido de cada vez
  if (estado.enviando) {
    return;
  }
  // O joinha já marcado, clicado de novo: retira o voto
  let voto_novo = voto_do_botao;
  if (voto_conhecido(chave) === voto_do_botao) {
    voto_novo = null;
  }
  estado.enviando = true;
  estado.aviso = "";
  estado.erro = false;
  redesenhar_os_joinhas(chave);
  const resposta = await mandar_o_voto(opcoes, voto_novo, null);
  estado.enviando = false;
  // Recusado: o motivo aparece ao lado dos botões, e o voto de antes continua
  if (!resposta.ok) {
    estado.aviso = texto_do_erro_do_joinha(resposta.dados);
    estado.erro = true;
    redesenhar_os_joinhas(chave);
    return;
  }
  opinioes_conhecidas[chave] = { voto: resposta.dados.voto, comentario: resposta.dados.comentario };
  // O joinha para baixo abre a caixa do comentário; os outros a fecham
  estado.comentario_aberto = voto_novo === VOTO_PARA_BAIXO;
  estado.aviso = AVISO_DO_VOTO;
  if (voto_novo === null) {
    estado.aviso = AVISO_DO_VOTO_RETIRADO;
  }
  redesenhar_os_joinhas(chave);
  if (estado.comentario_aberto) {
    focar_a_caixa_do_comentario(elemento);
  }
}

/**
 * "Enviar" o comentário: grava o joinha para baixo com o texto (vazio: só fecha a caixa).
 *
 * Recebe: elemento — o do joinha. Devolve: uma promessa.
 */
async function enviar_comentario_do_joinha(elemento) {
  const opcoes = elemento.opcoes_do_joinha;
  const chave = elemento.dataset.joinha;
  const estado = estado_do_joinha(chave);
  const texto = estado.rascunho.trim();
  // Um pedido de cada vez
  if (estado.enviando) {
    return;
  }
  // Nada escrito: a caixa fecha, e o voto fica como está
  if (texto === "") {
    estado.comentario_aberto = false;
    desenhar_joinha(elemento);
    return;
  }
  estado.enviando = true;
  estado.aviso = "";
  estado.erro = false;
  redesenhar_os_joinhas(chave);
  const resposta = await mandar_o_voto(opcoes, VOTO_PARA_BAIXO, texto);
  estado.enviando = false;
  // Recusado (ex.: texto longo demais): o motivo aparece, e o texto continua na caixa
  if (!resposta.ok) {
    estado.aviso = texto_do_erro_do_joinha(resposta.dados);
    estado.erro = true;
    redesenhar_os_joinhas(chave);
    return;
  }
  opinioes_conhecidas[chave] = { voto: resposta.dados.voto, comentario: resposta.dados.comentario };
  estado.comentario_aberto = false;
  estado.rascunho = "";
  estado.aviso = AVISO_DO_COMENTARIO;
  redesenhar_os_joinhas(chave);
}

// ===== Os ganchos das telas =====

/**
 * O joinha embaixo de uma resposta do Agente de validação (Portal Empresa).
 *
 * Recebe: balao — o balão do agente; pendencia — {processamento_id, ...} (a da conversa); fala — {quem, ordem, ...}.
 * Devolve: nada. Só a resposta do agente com a posição guardada no servidor ganha o joinha (o aviso de erro, a fala da
 * pessoa e o que ainda não foi guardado, não).
 */
function acrescentar_opiniao_na_resposta(balao, pendencia, fala) {
  if (!joinha_funciona_aqui() || fala.quem !== "ia" || typeof fala.ordem !== "number") {
    return;
  }
  const envio = pendencia.processamento_id;
  balao.append(montar_joinha({
    tipo: TIPO_RESPOSTA_DA_CONVERSA,
    // A chave da conversa (a mesma do servidor) e a posição da resposta nela
    referencia: chave_da_conversa(pendencia) + "|" + fala.ordem,
    pergunta: "Esta resposta ajudou?",
    endereco_do_voto: "/api/empresa/opinioes",
    endereco_da_lista: "/api/empresa/opinioes?envio=" + encodeURIComponent(envio),
  }));
}

/**
 * O joinha embaixo da pergunta que o Agente Leitor ou o Agente Conferidor fez ao ler o documento (Portal Empresa).
 *
 * Recebe: balao — o balão da pergunta; pendencia — a do cartão (ou a de uma resolvida). Devolve: nada.
 * Só a pendência de pergunta da leitura ganha o joinha: a chave da conversa diz a regra. Ex.: a chave
 * "a1b2|PERGUNTA_DA_IA:cpf|4|cpf" vira a referência "a1b2|4|cpf" (o envio, a linha e o campo da pergunta).
 */
function acrescentar_opiniao_na_pergunta(balao, pendencia) {
  if (!joinha_funciona_aqui()) {
    return;
  }
  const chave = chave_da_conversa(pendencia);
  // A conversa de um grupo não é de uma pergunta da leitura
  if (chave.startsWith(COMECO_DA_CHAVE_DO_GRUPO)) {
    return;
  }
  // "<envio>|<regra>|<linha>|<campo>": só a regra das perguntas da leitura, com a linha da pessoa
  const partes = chave.split("|");
  if (partes.length < 3 || !partes[1].startsWith(REGRA_DA_PERGUNTA_DA_LEITURA) || partes[2] === "null") {
    return;
  }
  // O campo da pergunta vem depois dos dois-pontos da regra ("PESSOA" quando é sobre a pessoa toda)
  const campo_da_pergunta = partes[1].slice(REGRA_DA_PERGUNTA_DA_LEITURA.length);
  balao.append(montar_joinha({
    tipo: TIPO_PERGUNTA_DA_LEITURA,
    referencia: partes[0] + "|" + partes[2] + "|" + campo_da_pergunta,
    pergunta: "Esta pergunta fez sentido?",
    endereco_do_voto: "/api/empresa/opinioes",
    endereco_da_lista: "/api/empresa/opinioes?envio=" + encodeURIComponent(partes[0]),
  }));
}

/**
 * O joinha sobre o texto que o Agente de Endomarketing escreveu (Portal Interno: o rascunho e a janela "Ver").
 *
 * Recebe: lugar — o elemento onde o joinha entra (ou null, que é ignorado); empresa_id — a empresa aberta na aba;
 * material — {material_id, ...}. Devolve: nada. O lugar é esvaziado antes (o joinha do material anterior sai).
 */
function mostrar_opiniao_do_material(lugar, empresa_id, material) {
  if (!lugar || !joinha_funciona_aqui()) {
    return;
  }
  const endereco = "/api/banco/empresas/" + encodeURIComponent(empresa_id) + "/opinioes";
  lugar.replaceChildren(montar_joinha({
    tipo: TIPO_MATERIAL_DO_ENDOMARKETING,
    referencia: material.material_id,
    pergunta: "O texto do Agente de Endomarketing ficou bom?",
    endereco_do_voto: endereco,
    endereco_da_lista: endereco,
  }));
}
