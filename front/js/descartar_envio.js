/*
  descartar_envio.js — a janela "Descartar esta leitura?" (com a escolha do arquivo), a mesma nas telas Cadastrar e
  Acompanhar.

  Para que serve: enquanto o envio não foi ao banco, a empresa pode desistir dele (ex.: quer mandar um arquivo mais
  organizado). Antes de descartar, a janela pergunta se ela tem certeza e explica o que vai acontecer:
    - nada foi enviado ao banco;
    - a leitura (quantas pessoas e quantas correções) é apagada e ninguém é cadastrado;
    - o envio fica na lista como "Descartado", com a data e o nome de quem descartou (o registro fica guardado);
    - depois, dá para mandar outro arquivo.
  Concordando, o servidor encerra o envio e grava o evento DESCARTADO_PELA_EMPRESA na trilha (services/cadastro.py).
  Cada tela decide o que fazer depois (a Cadastrar volta para a escolha do arquivo; a Acompanhar atualiza a lista).

  Com mais de um arquivo possível (ex.: as pendências de Acompanhar com "Todos os arquivos" no filtro), a janela
  pergunta primeiro QUAL arquivo: o botão de descartar só liga depois da escolha.

  Uso:
    const descartou = await perguntar_e_descartar(processamento_id);            // true se descartou
    const descartado = await perguntar_qual_arquivo_e_descartar(arquivos);      // o envio descartado, ou null
      arquivos: [{processamento_id, nome_arquivo}]
*/

// A janela é criada uma vez só, na primeira vez que alguém pede para descartar.
let janela_de_descarte = null;

/**
 * Cria um elemento com classe e texto (ajuda curta, para a janela ficar legível).
 *
 * Recebe: tag; classe ("" = nenhuma); texto ("" = nenhum). Devolve: o elemento.
 */
function criar_elemento_do_descarte(tag, classe, texto) {
  const elemento = document.createElement(tag);
  if (classe) {
    elemento.className = classe;
  }
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Cria a escolha do arquivo (escondida até ser preciso): "Qual arquivo você quer descartar?".
 *
 * Recebe: nada. Devolve: o <label> com a lista de arquivos.
 */
function criar_escolha_do_arquivo() {
  const escolha = criar_elemento_do_descarte("label", "campo escolha-do-arquivo-a-descartar", "");
  escolha.dataset.escolhaDoArquivo = "";
  escolha.hidden = true;
  const rotulo = criar_elemento_do_descarte("span", "campo-rotulo", "Qual arquivo você quer descartar?");
  const lista = criar_elemento_do_descarte("select", "campo-entrada", "");
  lista.dataset.arquivoADescartar = "";
  escolha.append(rotulo, lista);
  return escolha;
}

/**
 * Cria a janela de descarte (um <dialog>, a janela pronta do navegador: escurece o fundo e fecha com Esc).
 *
 * Recebe: nada. Devolve: a janela, já colocada na página.
 */
function criar_janela_de_descarte() {
  const janela = criar_elemento_do_descarte("dialog", "janela-beneficio", "");
  janela.setAttribute("aria-labelledby", "titulo-janela-de-descarte");
  const conteudo = criar_elemento_do_descarte("div", "janela-conteudo", "");
  const titulo = criar_elemento_do_descarte("h2", "janela-titulo", "Descartar esta leitura?");
  titulo.id = "titulo-janela-de-descarte";
  const introducao = criar_elemento_do_descarte("p", "janela-resumo", "Veja o que acontece se você descartar:");
  // A lista do que acontece: preenchida a cada abertura (a quantidade de pessoas muda de envio para envio)
  const o_que_acontece = criar_elemento_do_descarte("ul", "lista-do-descarte", "");
  o_que_acontece.dataset.oQueAcontece = "";
  // O erro, se o servidor recusar (ex.: o envio já foi para o banco)
  const erro = criar_elemento_do_descarte("p", "erro-pendencia", "");
  erro.dataset.erroDoDescarte = "";
  erro.hidden = true;
  // Os dois botões: desistir (o padrão, à esquerda) e confirmar
  const botoes = criar_elemento_do_descarte("div", "janela-botoes", "");
  const continuar = criar_elemento_do_descarte("button", "botao botao-contorno", "Continuar com este envio");
  continuar.type = "button";
  continuar.dataset.continuarEnvio = "";
  const confirmar = criar_elemento_do_descarte("button", "botao botao-principal", "Sim, descartar");
  confirmar.type = "button";
  confirmar.dataset.confirmarDescarte = "";
  botoes.append(continuar, confirmar);
  conteudo.append(titulo, criar_escolha_do_arquivo(), introducao, o_que_acontece, erro, botoes);
  janela.append(conteudo);
  document.body.append(janela);
  return janela;
}

/**
 * Preenche a lista "o que acontece" com os números do envio.
 *
 * Recebe: janela; perdido — {funcionarios, correcoes} vindo do servidor, ou null se não deu para saber.
 * Devolve: nada.
 */
function preencher_o_que_acontece(janela, perdido) {
  let leitura = "A leitura deste arquivo é apagada, e ninguém dele é cadastrado.";
  // Com os números, a frase diz exatamente o que se perde
  if (perdido !== null) {
    leitura = "A leitura de " + perdido.funcionarios + " funcionário(s) e " + perdido.correcoes +
      " correção(ões) que você fez é apagada, e ninguém deste arquivo é cadastrado.";
  }
  const itens = [
    "Nada foi enviado ao banco.",
    leitura,
    "O envio fica na sua lista como “Descartado”, com a data e o seu nome: o registro fica guardado.",
    "Depois, você pode enviar outro arquivo, mais organizado, quando quiser.",
  ];
  const lista = janela.querySelector("[data-o-que-acontece]");
  lista.replaceChildren();
  for (const texto of itens) {
    lista.append(criar_elemento_do_descarte("li", "", texto));
  }
}

/**
 * Busca no servidor o que se perde com o descarte de um envio e escreve na janela.
 *
 * Recebe: janela; processamento_id. Devolve: uma promessa. Sem os números, a frase fica geral.
 */
async function mostrar_o_que_se_perde(janela, processamento_id) {
  let perdido = null;
  // try/catch: sem servidor, a frase geral basta
  try {
    const resposta = await fetch("/api/empresa/cadastro/" + encodeURIComponent(processamento_id) + "/o_que_se_perde");
    if (resposta.ok) {
      perdido = await resposta.json();
    }
  } catch (erro) {
    perdido = null;
  }
  preencher_o_que_acontece(janela, perdido);
}

/**
 * Monta a escolha do arquivo: mostrada com mais de um arquivo, escondida com um só.
 *
 * Recebe: janela; arquivos — [{processamento_id, nome_arquivo}] ou null (um envio só, já escolhido). Devolve: nada.
 */
function montar_escolha_do_arquivo(janela, arquivos) {
  const escolha = janela.querySelector("[data-escolha-do-arquivo]");
  const lista = janela.querySelector("[data-arquivo-a-descartar]");
  lista.replaceChildren();
  escolha.hidden = arquivos === null;
  if (arquivos === null) {
    return;
  }
  // A primeira opção pede a escolha (nenhum arquivo vem marcado sozinho)
  lista.add(new Option("Escolha o arquivo", ""));
  for (const arquivo of arquivos) {
    lista.add(new Option(arquivo.nome_arquivo, arquivo.processamento_id));
  }
}

/**
 * Abre a janela e espera a decisão. Com uma lista de arquivos, pede primeiro qual descartar.
 *
 * Recebe: processamento_id — o envio (ou null, quando vem a lista); arquivos — [{processamento_id, nome_arquivo}] ou
 *         null. Devolve: uma promessa que vira o processamento_id descartado, ou null se a empresa desistiu.
 * Se o servidor recusar, a janela continua aberta com a explicação (a empresa pode desistir ou tentar de novo).
 */
async function abrir_janela_e_descartar(processamento_id, arquivos) {
  if (janela_de_descarte === null) {
    janela_de_descarte = criar_janela_de_descarte();
  }
  const janela = janela_de_descarte;
  const erro = janela.querySelector("[data-erro-do-descarte]");
  const confirmar = janela.querySelector("[data-confirmar-descarte]");
  const continuar = janela.querySelector("[data-continuar-envio]");
  const lista_de_arquivos = janela.querySelector("[data-arquivo-a-descartar]");
  // O envio escolhido: o que veio, ou o que a pessoa escolher na lista
  let escolhido = processamento_id;
  montar_escolha_do_arquivo(janela, arquivos);
  erro.hidden = true;
  // Sem arquivo escolhido, o botão de descartar fica desligado
  confirmar.disabled = escolhido === null;
  if (escolhido === null) {
    preencher_o_que_acontece(janela, null);
  } else {
    await mostrar_o_que_se_perde(janela, escolhido);
  }
  janela.showModal();
  // Espera a decisão: a promessa só termina quando a empresa descarta ou desiste
  return new Promise(function (terminar) {
    // Escolheu um arquivo na lista: os números passam a ser os dele
    async function ao_escolher() {
      escolhido = lista_de_arquivos.value || null;
      confirmar.disabled = escolhido === null;
      erro.hidden = true;
      if (escolhido === null) {
        preencher_o_que_acontece(janela, null);
        return;
      }
      await mostrar_o_que_se_perde(janela, escolhido);
    }
    // Desistir: pelo botão ou pelo Esc (o Esc fecha a janela sozinho e dispara "close")
    function ao_desistir() {
      janela.close();
    }
    function ao_fechar() {
      continuar.removeEventListener("click", ao_desistir);
      confirmar.removeEventListener("click", ao_confirmar);
      lista_de_arquivos.removeEventListener("change", ao_escolher);
      janela.removeEventListener("close", ao_fechar);
      // Descartou: devolve qual envio; desistiu: null
      let descartado = null;
      if (janela.dataset.descartou === "sim") {
        descartado = escolhido;
      }
      delete janela.dataset.descartou;
      terminar(descartado);
    }
    // Confirmar: pede o descarte ao servidor; deu certo, fecha e avisa quem chamou
    async function ao_confirmar() {
      confirmar.disabled = true;
      const mensagem = await pedir_o_descarte(escolhido);
      if (mensagem !== null) {
        confirmar.disabled = false;
        erro.textContent = mensagem;
        erro.hidden = false;
        return;
      }
      janela.dataset.descartou = "sim";
      janela.close();
    }
    continuar.addEventListener("click", ao_desistir);
    confirmar.addEventListener("click", ao_confirmar);
    lista_de_arquivos.addEventListener("change", ao_escolher);
    janela.addEventListener("close", ao_fechar);
  });
}

/**
 * Pede ao servidor o descarte de um envio.
 *
 * Recebe: processamento_id. Devolve: uma promessa de null (descartou) ou do texto do erro para mostrar.
 */
async function pedir_o_descarte(processamento_id) {
  const endereco = "/api/empresa/cadastro/" + encodeURIComponent(processamento_id) + "/descartar";
  // try/catch: sem servidor, a mensagem geral
  try {
    const resposta = await fetch(endereco, { method: "POST" });
    if (resposta.ok) {
      return null;
    }
    // A explicação do servidor, quando ele manda uma frase (ex.: "o envio já foi para o banco")
    const dados = await resposta.json();
    if (typeof dados.detail === "string") {
      return dados.detail;
    }
  } catch (erro) {
    // Resposta sem JSON ou servidor fora do ar: fica a mensagem geral
  }
  return "Não foi possível descartar agora. Tente de novo.";
}

/**
 * Pergunta se a empresa tem certeza e, se ela confirmar, descarta o envio no servidor.
 *
 * Recebe: processamento_id — o envio. Devolve: uma promessa que vira true se descartou, false se desistiu.
 */
async function perguntar_e_descartar(processamento_id) {
  const descartado = await abrir_janela_e_descartar(processamento_id, null);
  return descartado !== null;
}

/**
 * Pergunta qual arquivo descartar (entre vários) e, se a empresa confirmar, descarta o escolhido.
 *
 * Recebe: arquivos — [{processamento_id, nome_arquivo}]. Devolve: uma promessa do processamento_id descartado, ou
 * null se a empresa desistiu.
 */
async function perguntar_qual_arquivo_e_descartar(arquivos) {
  return abrir_janela_e_descartar(null, arquivos);
}
