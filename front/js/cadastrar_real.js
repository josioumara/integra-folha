/*
  cadastrar_real.js — o envio de VERDADE na tela "Cadastrar funcionários" (front ligado à aplicação, ADR-69).

  Para que serve: quando a página é servida pela API (http://...), escolher ou arrastar um arquivo deixa de ser
  simulação. O arquivo vai para o servidor, a IA lê de verdade (o fluxo em LangGraph) e a tela mostra:
    1. no painel da IA: mensagens a partir do que ela realmente leu e as colunas reconhecidas;
    2. no bloco "resultado-real": cada coluna, o campo proposto e o motivo; nas colunas ambíguas, a pessoa escolhe.
       No Word em texto corrido, cada jeito de a empresa chamar o dado é uma linha, com um exemplo do valor lido.
       Quando a pessoa troca o campo, a linha vira "Ajustado por você" e a tela confere na hora se os valores servem
       para o campo novo (tipo diferente = alerta; se aceitar assim, o que não serve vira pendência para revisar).
       Uma coluna com vários dados numa célula (o endereço inteiro) pode ser dividida em vários campos, com prévia.
       Com a lista dos obrigatórios do parâmetro (js/cadastrar_obrigatorios.js), só as colunas das informações
       obrigatórias ficam em cima para a empresa confirmar; as outras descem, fechadas, e entram sem pergunta (ADR-143);
    3. "Aceitar as colunas": o fluxo padroniza e valida. Sem pendências, aparece "Enviar ao banco"; os
       funcionários ficam cadastrados quando o especialista do banco aprovar (ADR-69, passo 15);
       com pendências, o caminho é "Acompanhar cadastros", onde elas se resolvem;
    4. "Descartar esta leitura": encerra o envio sem cadastrar ninguém.

  Os botões de exemplo continuam sendo a demonstração animada do js/cadastrar.js.
  Usa funções do js/cadastrar.js (marcar_etapa, mostrar_ia_pensando, escrever_mensagem), carregado antes.
*/

// A escolha que deixa uma coluna de fora (a mesma de services/mapeamentos.py).
const OPCAO_IGNORAR = "(ignorar coluna)";
// A situação da coluna cujo campo a empresa trocou (a mesma de services/cadastro.py).
const SITUACAO_AJUSTADA = "Ajustado por você";
// A escolha que abre a divisão da coluna em vários campos (ex.: o endereço inteiro numa célula, ADR-76).
const OPCAO_DIVIDIR = "(dividir)";
// A situação da coluna que a IA dividiu e a de cada parte dela (as mesmas de services/cadastro.py, ADR-104).
const SITUACAO_DIVIDIDA_PELA_IA = "Dividida pelo Agente Interpretador";
const SITUACAO_PARTE_DA_IA = "Dividido pelo Agente Interpretador";

// O envio de verdade que está na tela (id e a última leitura devolvida pelo servidor), ou null.
let envio_de_verdade = null;

// Verdadeiro quando a tela está dentro da janela "Cadastrar funcionários" (js/novo_envio.js): ao aceitar as
// colunas, a pessoa segue para "Acompanhar cadastros", onde as pendências são resolvidas e o envio vai ao banco.
const TELA_EM_JANELA = new URLSearchParams(window.location.search).get("em_janela") !== null;

// O cronômetro do painel da IA: o relógio que conta e a hora em que começou (null = parado).
const cronometro = { relogio: null, inicio: null };

/**
 * Liga o cronômetro ao lado do status da IA ("0:00", "0:01"...): a leitura de um texto corrido leva minutos, e a
 * pessoa vê que a IA continua trabalhando.
 *
 * Recebe: nada. Devolve: nada. Ligar de novo recomeça do zero.
 */
function ligar_cronometro() {
  parar_cronometro();
  const mostrador = document.getElementById("cronometro-ia");
  cronometro.inicio = Date.now();
  mostrador.textContent = "0:00";
  mostrador.hidden = false;
  // A cada segundo, o tempo desde o início, em minutos:segundos
  cronometro.relogio = window.setInterval(function () {
    const segundos_passados = Math.floor((Date.now() - cronometro.inicio) / 1000);
    const minutos = Math.floor(segundos_passados / 60);
    const segundos = segundos_passados % 60;
    mostrador.textContent = minutos + ":" + String(segundos).padStart(2, "0");
  }, 1000);
}

/**
 * Para o cronômetro. O tempo final continua à mostra (ex.: "1:42"), para a pessoa saber quanto levou.
 *
 * Recebe: nada. Devolve: nada.
 */
function parar_cronometro() {
  if (cronometro.relogio !== null) {
    window.clearInterval(cronometro.relogio);
    cronometro.relogio = null;
  }
}

/**
 * Leva a página inteira (não só a janela) para "Acompanhar cadastros", no envio indicado.
 *
 * Recebe: processamento_id; aviso — o recado que Acompanhar mostra no topo ("colunas_aceitas", "ja_enviado").
 * Devolve: nada.
 */
function ir_para_acompanhar(processamento_id, aviso) {
  window.top.location.href = "acompanhar.html?envio=" + encodeURIComponent(processamento_id) + "&aviso=" + aviso;
}

/**
 * Verdadeiro quando a página está ligada à aplicação (servida pela API), e não aberta como arquivo.
 *
 * Recebe: nada. Devolve: true ou false.
 */
function modo_de_verdade() {
  // "http:" ou "https:" = servida pelo servidor; "file:" = aberta com dois cliques.
  return window.location.protocol.startsWith("http");
}

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro).
 *
 * Recebe: etiqueta; classe; texto. Devolve: o elemento.
 */
function criar_elemento_real(etiqueta, classe, texto) {
  // O elemento vazio.
  const elemento = document.createElement(etiqueta);
  // A classe, se houver.
  if (classe) {
    elemento.className = classe;
  }
  // O texto, se houver.
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Manda um pedido à API e devolve { ok, dados }. Nunca quebra: sem servidor, devolve ok falso com a mensagem.
 *
 * Recebe: endereco; opcoes — as do fetch (método, corpo...). Devolve: { ok, dados }.
 */
async function pedir_a_api(endereco, opcoes) {
  // try/catch: servidor fora do ar vira mensagem, não quebra a tela.
  try {
    const resposta = await fetch(endereco, opcoes);
    const dados = await resposta.json();
    return { ok: resposta.ok, dados: dados };
  } catch (erro) {
    return { ok: false, dados: { detail: "Não foi possível falar com o servidor. Tente de novo em instantes." } };
  }
}

/**
 * Transforma o "detail" de um erro em texto (erro de regra vem em texto; erro de formato vem em lista).
 *
 * Recebe: detalhe. Devolve: o texto.
 */
function texto_do_erro(detalhe) {
  // Erro de regra: já é texto simples.
  if (typeof detalhe === "string") {
    return detalhe;
  }
  // Erro de formato do pedido.
  return "Não foi possível concluir. Confira o que foi preenchido.";
}

// ===== 1. Enviar e mostrar a leitura no painel da IA =====

/**
 * Envia um arquivo de verdade: mostra o painel da IA, manda o arquivo ao servidor e mostra o que ela leu.
 *
 * Recebe: lista_de_arquivos — os arquivos escolhidos ou arrastados. Devolve: nada.
 * Cada arquivo vira um envio próprio: a tela conduz o primeiro, e os outros são enviados em seguida (cada um espera
 * as colunas conferidas em "Acompanhar cadastros").
 */
async function enviar_arquivo_de_verdade(lista_de_arquivos) {
  // Já há um envio em andamento: não começa outro.
  if (envio_de_verdade !== null) {
    return;
  }
  // O primeiro arquivo (os outros, se houver, ficam para o próximo envio).
  const arquivo = lista_de_arquivos[0];
  envio_de_verdade = { id: null, leitura: null };
  // Troca a área de envio pelo painel da IA.
  document.getElementById("etapa-envio").hidden = true;
  document.getElementById("etapa-leitura").hidden = false;
  document.getElementById("arquivo-nome").textContent = arquivo.name;
  document.getElementById("arquivo-detalhes").textContent = "Enviando…";
  ligar_cronometro();
  marcar_etapa(1);
  await mostrar_ia_pensando();
  // Documento e texto: a IA procura os funcionários no documento (tabela, fichas ou texto corrido); planilha: lê as colunas.
  const nome_em_minusculas = arquivo.name.toLowerCase();
  let e_documento = false;
  for (const extensao of [".docx", ".odt", ".txt", ".rtf"]) {
    if (nome_em_minusculas.endsWith(extensao)) {
      e_documento = true;
    }
  }
  if (e_documento) {
    await escrever_mensagem("Recebi o documento " + arquivo.name + ". Vou procurar os funcionários no texto e montar a lista.", "normal");
  } else {
    await escrever_mensagem("Recebi " + arquivo.name + ". Vou ler as colunas e conferir os dados.", "normal");
  }

  // O arquivo vai no formato de formulário do navegador ("FormData"), com o código para perguntar o progresso.
  const formulario = new FormData();
  formulario.append("arquivo", arquivo);
  const codigo_do_progresso = sortear_codigo_do_progresso();
  formulario.append("pedido_de_progresso", codigo_do_progresso);
  marcar_etapa(2);
  // Enquanto o servidor lê, a tela pergunta a frase do momento a cada segundo (ADR-95)
  const relogio_do_progresso = setInterval(function () {
    mostrar_progresso_do_envio(codigo_do_progresso);
  }, INTERVALO_DO_PROGRESSO);
  const resposta = await pedir_a_api("/api/empresa/cadastro/enviar", { method: "POST", body: formulario });
  clearInterval(relogio_do_progresso);

  // A resposta chegou: o cronômetro para (o tempo final fica à mostra).
  parar_cronometro();
  // Recusado (ex.: formato que não serve): a IA explica e a tela volta para a escolha do arquivo.
  if (!resposta.ok) {
    await escrever_mensagem(texto_do_erro(resposta.dados.detail), "alerta");
    document.getElementById("texto-status-ia").textContent = "Arquivo não aceito";
    envio_de_verdade = null;
    document.getElementById("etapa-envio").hidden = false;
    return;
  }

  // Deu certo: guarda a leitura e conta o que a IA achou.
  envio_de_verdade.id = resposta.dados.processamento_id;
  envio_de_verdade.leitura = resposta.dados;
  // Na janela, o mesmo arquivo já enviado (e com as colunas já aceitas) não segue: a tela avisa e aponta o envio.
  if (TELA_EM_JANELA && resposta.dados.duplicado && resposta.dados.etapa !== "aprovar_mapeamento") {
    await avisar_arquivo_ja_enviado(resposta.dados);
    return;
  }
  await contar_a_leitura_no_painel(resposta.dados);
  mostrar_resultado_real(resposta.dados);
  // Os outros arquivos, se houver: cada um vira um envio próprio.
  await enviar_os_outros_arquivos(lista_de_arquivos);
}

// De quanto em quanto tempo a tela pergunta o progresso do envio (em milissegundos)
const INTERVALO_DO_PROGRESSO = 1000;

/**
 * Um código novo para o pedido (o servidor anota o progresso nele; só quem enviou consegue ler).
 *
 * Recebe: nada. Devolve: o código (ex.: "3f2a9c1e-...").
 */
function sortear_codigo_do_progresso() {
  // crypto.randomUUID existe nos navegadores atuais; o resto é um plano B com a hora e um sorteio
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return "pedido-" + Date.now() + "-" + Math.floor(Math.random() * 1000000);
}

/**
 * Pergunta ao servidor a frase do momento do envio e mostra no painel da IA (ex.: "A IA leu 5 de 12 pessoa(s).").
 *
 * Recebe: codigo — o código do pedido. Devolve: nada. Sem resposta, a frase anterior continua.
 */
async function mostrar_progresso_do_envio(codigo) {
  // try/catch: um pedido que falha não quebra a tela (o próximo tenta de novo).
  try {
    const resposta = await fetch("/api/empresa/cadastro/progresso/" + encodeURIComponent(codigo));
    if (!resposta.ok) {
      return;
    }
    const progresso = await resposta.json();
    document.getElementById("texto-status-ia").textContent = progresso.texto;
  } catch (erro) {
    return;
  }
}

/**
 * Avisa, no painel da IA, que o arquivo já tinha sido enviado, com um botão para ver o envio em Acompanhar.
 *
 * Recebe: leitura — o envio que já existia. Devolve: nada.
 */
async function avisar_arquivo_ja_enviado(leitura) {
  await escrever_mensagem("Este arquivo já foi enviado antes, com estes mesmos dados. Não criei outro envio: ele está em \"Acompanhar cadastros\".", "alerta");
  const botao = criar_elemento_real("button", "botao botao-contorno botao-pequeno", "Ver em Acompanhar cadastros");
  botao.type = "button";
  botao.addEventListener("click", function () {
    ir_para_acompanhar(leitura.processamento_id, "ja_enviado");
  });
  document.getElementById("conversa-ia").append(botao);
  document.getElementById("texto-status-ia").textContent = "Arquivo já enviado";
  envio_de_verdade = null;
}

/**
 * Envia os arquivos que vieram junto com o primeiro: cada um vira um envio próprio, e a IA conta o que aconteceu.
 *
 * Recebe: lista_de_arquivos — todos os escolhidos (o primeiro já foi). Devolve: nada.
 */
async function enviar_os_outros_arquivos(lista_de_arquivos) {
  for (let posicao = 1; posicao < lista_de_arquivos.length; posicao++) {
    const arquivo = lista_de_arquivos[posicao];
    const formulario = new FormData();
    formulario.append("arquivo", arquivo);
    const resposta = await pedir_a_api("/api/empresa/cadastro/enviar", { method: "POST", body: formulario });
    if (resposta.ok) {
      await escrever_mensagem("Também recebi " + arquivo.name + " (" + resposta.dados.linhas + " linhas): as colunas dele " +
        "esperam você em \"Acompanhar cadastros\".", "normal");
      // O mesmo nome de outro arquivo já enviado: o aviso da versão (ex.: "aurora.xlsx (v2)")
      if (resposta.dados.aviso_do_nome) {
        await escrever_mensagem(resposta.dados.aviso_do_nome, "alerta");
      }
    } else {
      await escrever_mensagem("Não consegui ler " + arquivo.name + ": " + texto_do_erro(resposta.dados.detail), "alerta");
    }
  }
}

/**
 * Conta, no painel da IA, o que ela leu de verdade: linhas, colunas reconhecidas e o que precisa de decisão.
 *
 * Recebe: leitura — o que o servidor devolveu. Devolve: nada.
 */
async function contar_a_leitura_no_painel(leitura) {
  // Contagens das colunas por situação.
  let reconhecidas = 0;
  let para_decidir = 0;
  let deixadas_de_fora = 0;
  for (const coluna of leitura.colunas) {
    if (coluna.precisa_decidir) {
      para_decidir = para_decidir + 1;
    } else if (coluna.campo) {
      reconhecidas = reconhecidas + 1;
    } else {
      deixadas_de_fora = deixadas_de_fora + 1;
    }
  }
  // Detalhes do arquivo e contadores do lado direito.
  document.getElementById("arquivo-detalhes").textContent = leitura.tipo + " · " + leitura.linhas + " linhas · " + leitura.colunas.length + " colunas";
  document.getElementById("selo-tipo-envio").textContent = leitura.tipo;
  document.getElementById("selo-tipo-envio").hidden = false;
  document.getElementById("contador-lidas").textContent = leitura.linhas;
  // As colunas reconhecidas, uma por linha, com a aparência de confiança do layout.
  mostrar_colunas_no_painel(leitura.colunas);
  // As mensagens da IA, a partir do que ela leu.
  await mostrar_ia_pensando();
  if (leitura.reaproveitou_mapeamento) {
    await escrever_mensagem("As colunas são as mesmas de um envio que o banco já aprovou. Reaproveitei o mapeamento.", "normal");
  }
  if (leitura_de_texto_corrido(leitura)) {
    await escrever_mensagem("Achei " + leitura.linhas + " funcionário(s) e " + reconhecidas + " tipos de dado no texto. Abaixo, como vocês chamaram cada um e o campo do banco.", "normal");
  } else {
    await escrever_mensagem("Li " + leitura.linhas + " linhas. Reconheci " + reconhecidas + " colunas; " + deixadas_de_fora + " ficaram de fora.", "normal");
  }
  // As perguntas da IA sobre trechos que ela não conseguiu ler (Word em texto corrido).
  if (leitura.perguntas_da_ia > 0) {
    // Na janela, a resposta é em "Acompanhar cadastros"; na tela inteira, na conferência logo abaixo.
    let onde_responder = "na conferência, depois de aceitar as colunas";
    if (TELA_EM_JANELA) {
      onde_responder = "em \"Acompanhar cadastros\", depois de aceitar as colunas";
    }
    await escrever_mensagem("Tenho " + leitura.perguntas_da_ia + " pergunta(s) sobre funcionários. Não vou chutar: você responde " + onde_responder + ".", "alerta");
  }
  if (leitura.duvidas && leitura.duvidas.length > 0) {
    await escrever_mensagem(leitura.duvidas.length + " trecho(s) do documento eu não consegui ler. Veja em \"Ver detalhes da leitura\".", "alerta");
  }
  if (para_decidir > 0) {
    await escrever_mensagem(para_decidir + " coluna(s) podem ser mais de um campo. Não vou chutar: escolha abaixo.", "alerta");
  }
  if (leitura.duplicado) {
    await escrever_mensagem("Este arquivo já tinha sido enviado: continuei o mesmo envio, sem criar outro.", "alerta");
  }
  // Outro arquivo (diferente) com o mesmo nome já foi enviado: este ganha a versão, ex.: "aurora.xlsx (v2)"
  // (o texto vem pronto do servidor)
  if (leitura.aviso_do_nome) {
    await escrever_mensagem(leitura.aviso_do_nome, "alerta");
  }
  // O painel fica concluído.
  marcar_etapa(5);
  document.getElementById("painel-ia").classList.add("concluido");
  document.getElementById("texto-status-ia").textContent = "Leitura concluída";
}

/**
 * Diz se a leitura veio de um Word em texto corrido (as colunas vieram do Leitor de Documentos, origem "leitor").
 *
 * Recebe: leitura. Devolve: true ou false.
 */
function leitura_de_texto_corrido(leitura) {
  for (const coluna of leitura.colunas) {
    if (coluna.origem === "leitor") {
      return true;
    }
  }
  return false;
}

/**
 * Como a empresa chamou o dado: no texto corrido, o rótulo do documento ("Registro do cliente", "Documento fiscal");
 * na planilha, o nome da coluna.
 *
 * Recebe: coluna — da leitura. Devolve: o texto.
 * No texto corrido, cada jeito de chamar o dado é uma linha própria: se a IA juntou dois dados diferentes no mesmo
 * campo, a pessoa troca o campo só daquela linha. O exemplo (ver celula_de_origem) mostra qual pedaço é qual.
 */
function nome_de_origem(coluna) {
  if (coluna.origem !== "leitor") {
    return coluna.coluna;
  }
  if (coluna.no_documento.length === 0) {
    return "Sem rótulo (o Agente Leitor achou pelo lugar no texto)";
  }
  const entre_aspas = [];
  for (const rotulo of coluna.no_documento) {
    entre_aspas.push("\u201c" + rotulo + "\u201d");
  }
  return entre_aspas.join(", ");
}

/**
 * A célula da primeira coluna da tabela: o nome de origem e, no texto corrido, um exemplo do valor lido e em quantas
 * pessoas o dado apareceu.
 *
 * Recebe: coluna; total_de_pessoas — quantas pessoas o envio tem. Devolve: o <td>.
 * Ex.: “Admissão” · ex.: “05/03/2026” · em 8 de 12 pessoa(s).
 */
function celula_de_origem(coluna, total_de_pessoas) {
  const celula = criar_elemento_real("td", "", nome_de_origem(coluna));
  // O exemplo mostra qual pedaço do documento foi para este campo (o valor vem inteiro, como está no arquivo da empresa)
  if (coluna.exemplo) {
    celula.append(criar_elemento_real("span", "exemplo-da-coluna", "ex.: \u201c" + coluna.exemplo + "\u201d"));
  }
  if (coluna.origem === "leitor" && coluna.pessoas) {
    celula.append(criar_elemento_real("span", "celula-motivo bloco-pequeno",
      "em " + coluna.pessoas + " de " + total_de_pessoas + " pessoa(s)"));
  }
  return celula;
}

/**
 * Lista as colunas no cartão "Colunas reconhecidas" do painel, com o selo do layout.
 *
 * Recebe: colunas — as da leitura. Devolve: nada.
 */
function mostrar_colunas_no_painel(colunas) {
  // A lista e o selo do total.
  const lista = document.getElementById("lista-campos");
  lista.replaceChildren();
  let reconhecidas = 0;
  for (const coluna of colunas) {
    // O molde de linha de campo do layout.
    const copia = document.getElementById("modelo-campo").content.cloneNode(true);
    const linha = copia.querySelector(".coluna-mapeada");
    const selo = copia.querySelector(".coluna-confianca");
    copia.querySelector(".coluna-arquivo").textContent = nome_de_origem(coluna);
    copia.querySelector(".coluna-banco").textContent = coluna.campo || "—";
    // Reconhecida = verde; para decidir = laranja; deixada de fora = cinza e apagada.
    let aparencia = APARENCIA_DA_CONFIANCA.alta;
    if (coluna.precisa_decidir) {
      aparencia = APARENCIA_DA_CONFIANCA.media;
    } else if (coluna.situacao === SITUACAO_AJUSTADA) {
      aparencia = { classe_do_selo: "selo-ajustado" };
      reconhecidas = reconhecidas + 1;
    } else if (!coluna.campo) {
      aparencia = APARENCIA_DA_CONFIANCA.ignorada;
      linha.classList.add("coluna-ignorada");
    } else {
      reconhecidas = reconhecidas + 1;
    }
    selo.classList.add(aparencia.classe_do_selo);
    selo.textContent = coluna.situacao;
    lista.appendChild(linha);
  }
  document.getElementById("total-campos").textContent = reconhecidas + " de " + colunas.length;
}

// ===== 2. O bloco do resultado de verdade =====

/**
 * Mostra (ou atualiza) o bloco do resultado com a leitura atual: colunas, recado e os botões da etapa.
 *
 * Recebe: leitura. Devolve: nada.
 */
function mostrar_resultado_real(leitura) {
  // O bloco.
  const bloco = document.getElementById("resultado-real");
  bloco.hidden = false;
  // Título e etapa.
  document.querySelector("[data-real-tipo]").textContent = leitura.tipo;
  document.querySelector("[data-real-titulo]").textContent = leitura.linhas + " linhas lidas";
  document.querySelector("[data-real-subtitulo]").textContent = texto_da_etapa(leitura);
  document.querySelector("[data-real-etapa]").textContent = leitura.nome_da_etapa;
  document.querySelector("[data-real-reuso]").hidden = !leitura.reaproveitou_mapeamento;
  // Os avisos da leitura e as dúvidas da IA.
  mostrar_avisos_e_duvidas(leitura);
  // Recado do fluxo (ex.: coluna ambígua sem decisão).
  mostrar_erro_real(leitura.erro);
  // As colunas (com escolha só enquanto o aceite está aberto).
  montar_tabela_de_colunas(leitura);
  // Os botões da etapa.
  mostrar_botoes_da_etapa(leitura);
  // Os contadores "prontas" e "para revisar" do painel da IA.
  atualizar_contadores_do_painel(leitura);
  // Formato de coluna, conferência da lista e "Ajude a IA a acertar" (js/cadastrar_conferencia_real.js).
  mostrar_partes_da_conferencia(leitura);
  // As duas abas do resultado, "Funcionários" e "Como o agente leu" (js/cadastrar_abas.js).
  mostrar_as_abas_do_resultado(leitura);
}

// A regra da leitura, mostrada junto do resumo: o valor sempre sai do documento; o que falta vira pendência.
const REGRA_DA_LEITURA = "Os agentes não inventam dado: tudo vem do seu arquivo, e o que falta ou não confere " +
  "vira pendência para você completar.";

/**
 * Mostra a leitura em uma frase, o contador das perguntas da IA e os detalhes recolhidos (ADR-73).
 *
 * Recebe: leitura — com "avisos" (o primeiro é o resumo), "duvidas" (trechos que a IA não leu, de ninguém) e
 * "perguntas_da_ia" (quantas perguntas presas a funcionários, respondidas na conferência). Devolve: nada.
 */
function mostrar_avisos_e_duvidas(leitura) {
  const avisos = leitura.avisos || [];
  const trechos_nao_lidos = leitura.duvidas || [];
  const perguntas = leitura.perguntas_da_ia || 0;
  // 1. A leitura numa frase: o primeiro aviso (ex.: "Texto corrido: a IA montou a lista com 12 funcionários").
  // Junto, a regra da leitura, dita à pessoa: a IA não inventa o que falta (decisão 6).
  const resumo = document.querySelector("[data-real-resumo-leitura]");
  resumo.textContent = avisos.length > 0 ? avisos[0] + " " + REGRA_DA_LEITURA : "";
  resumo.hidden = avisos.length === 0;
  // 2. As perguntas sobre funcionários: só o contador e onde responder (a resposta é na conferência).
  const aviso_das_perguntas = document.querySelector("[data-real-aviso-perguntas]");
  // Antes do aceite, diz onde vai responder; na conferência, aponta para baixo.
  if (leitura.etapa === "aprovar_mapeamento") {
    let onde_responder = "na conferência";
    if (TELA_EM_JANELA) {
      onde_responder = "em \"Acompanhar cadastros\"";
    }
    aviso_das_perguntas.textContent = "O Agente Leitor e o Agente Conferidor têm " + perguntas +
      " pergunta(s) sobre funcionários (ex.: um CPF que não " +
      "veio, duas datas diferentes). Você responde " + onde_responder + ", logo depois de aceitar as colunas: " +
      "corrigindo o valor ou confirmando que está certo.";
  } else {
    aviso_das_perguntas.textContent = "O Agente Leitor e o Agente Conferidor fizeram " + perguntas +
      " pergunta(s) sobre funcionários. Responda na " +
      "conferência abaixo, embaixo do nome de cada pessoa.";
  }
  aviso_das_perguntas.hidden = perguntas === 0;
  // 3. Os detalhes, recolhidos: os outros avisos e os trechos que a IA não conseguiu ler.
  const detalhes = avisos.slice(1).concat(trechos_nao_lidos);
  const lista = document.querySelector("[data-real-lista-detalhes]");
  lista.replaceChildren();
  for (const aviso of avisos.slice(1)) {
    lista.appendChild(criar_elemento_real("p", "sugestao-ia", aviso));
  }
  for (const trecho of trechos_nao_lidos) {
    lista.appendChild(criar_elemento_real("p", "sugestao-ia duvida-ia", trecho));
  }
  document.querySelector("[data-real-titulo-detalhes]").textContent = "Ver detalhes da leitura (" + detalhes.length + ")";
  document.querySelector("[data-real-bloco-detalhes]").hidden = detalhes.length === 0;
  document.querySelector("[data-real-nota-trechos]").hidden = trechos_nao_lidos.length === 0;
}

/**
 * Atualiza os contadores "prontas" e "para revisar" do painel da IA com o resumo único das pendências.
 *
 * Recebe: leitura — com "resumo_das_pendencias" ({para_revisar, prontas, ...}, o mesmo da conferência e de
 * "Acompanhar cadastros"; null antes do aceite das colunas). Devolve: nada.
 * Antes do aceite das colunas, os dados não foram conferidos: os dois mostram "—".
 * Por que o número vem pronto do servidor (ADR-126): somado aqui, ele contaria a pergunta da IA que já é
 * explicação de uma correção e não bateria com a conferência nem com Acompanhar.
 */
function atualizar_contadores_do_painel(leitura) {
  const campo_prontas = document.getElementById("contador-prontas");
  const campo_revisar = document.getElementById("contador-revisar");
  const resumo = leitura.resumo_das_pendencias;
  // Sem o resumo (aceite das colunas ainda aberto): os dados ainda não foram conferidos.
  if (!resumo) {
    campo_prontas.textContent = "—";
    campo_revisar.textContent = "—";
    return;
  }
  campo_revisar.textContent = resumo.para_revisar;
  campo_prontas.textContent = resumo.prontas;
}

/**
 * Explica, em uma frase, o que a pessoa faz agora, conforme a etapa do fluxo.
 *
 * Recebe: leitura. Devolve: o texto.
 */
function texto_da_etapa(leitura) {
  if (leitura.etapa === "aprovar_mapeamento") {
    // A empresa confirma só as colunas das informações obrigatórias (ADR-143)
    return "Confira como o agente leu as colunas das informações obrigatórias, escolha o campo onde ele pediu " +
      "ajuda e aceite. As outras informações entram sem pergunta.";
  }
  if (leitura.etapa === "aguardar_correcao") {
    return "Colunas aceitas. Alguns dados precisam de ajuste antes do cadastro.";
  }
  if (leitura.etapa === "aprovar_homologacao") {
    return "Colunas aceitas e dados conferidos: nenhuma pendência. Pode enviar ao banco.";
  }
  if (leitura.etapa === "avaliar_no_banco") {
    return "Enviado ao banco: o especialista avalia em até 1 dia útil. Os funcionários ficam cadastrados quando ele aprovar.";
  }
  // Parado esperando uma nova tentativa: o envio está guardado e o botão "Tentar de novo" retoma (ADR-139).
  if (leitura.etapa === "aguardar_nova_tentativa") {
    return "A análise parou antes de terminar. Seu envio está guardado.";
  }
  if (leitura.terminou) {
    return "Envio encerrado.";
  }
  return "Uma etapa não terminou. Tente de novo em instantes.";
}

/**
 * Mostra (ou esconde) o recado de erro no bloco do resultado.
 *
 * Recebe: texto (ou null). Devolve: nada.
 */
function mostrar_erro_real(texto) {
  const erro = document.querySelector("[data-real-erro]");
  erro.hidden = !texto;
  erro.textContent = texto || "";
}

/**
 * Monta a tabela das colunas. Enquanto o aceite está aberto, cada coluna ambígua ganha a escolha do campo.
 *
 * Recebe: leitura. Devolve: nada.
 * No fim, as colunas que não são das informações obrigatórias descem para "Outras informações do arquivo" (ADR-143;
 * ver separar_as_colunas_opcionais): a empresa confirma só as obrigatórias.
 */
function montar_tabela_de_colunas(leitura) {
  const corpo = document.querySelector("[data-real-corpo-colunas]");
  corpo.replaceChildren();
  // A tabela das outras informações também começa vazia (as linhas descem para ela na separação)
  document.querySelector("[data-real-corpo-colunas-opcionais]").replaceChildren();
  const aceite_aberto = leitura.etapa === "aprovar_mapeamento";
  // Word em texto corrido: não há colunas; a primeira coluna mostra como a empresa chamou cada dado (ADR-73). O título
  // vale para as duas tabelas (a das obrigatórias e a das outras informações).
  const texto_corrido = leitura_de_texto_corrido(leitura);
  for (const titulo_da_coluna_do_arquivo of document.querySelectorAll("[data-real-titulo-coluna-arquivo]")) {
    titulo_da_coluna_do_arquivo.textContent = texto_corrido ? "No seu documento" : "Coluna no seu arquivo";
  }
  document.querySelector("[data-real-titulo-colunas]").textContent =
    texto_corrido ? "Como o Agente Leitor leu o seu documento" :
      "Como o Agente Interpretador leu as colunas do seu arquivo";
  for (const coluna of leitura.colunas) {
    // A parte de uma coluna dividida fica recuada, logo abaixo da coluna de onde saiu.
    const linha = criar_elemento_real("tr", coluna.parte_de ? "linha-parte-da-divisao" : "", "");
    // O grupo da linha (a coluna, com as partes dela) e os campos que ela alimenta: é por eles que a separação decide
    // se a coluna é de uma informação obrigatória (ADR-143)
    linha.dataset.grupoDaColuna = coluna.parte_de || coluna.coluna;
    linha.dataset.camposDaColuna = campos_da_coluna_lida(coluna).join(" ");
    // Os campos que a IA indicou para a coluna, mesmo sem pedir a escolha (a coluna reaproveitada de um envio anterior
    // vem assim): é por eles que a nota "Fica guardada sem rótulo" decide (ADR-143, Parte 1)
    linha.dataset.candidatosDaColuna = (coluna.candidatos || []).join(" ");
    linha.append(celula_de_origem(coluna, leitura.linhas));
    // O campo: com o aceite aberto, sempre uma escolha (a ambígua pede a escolha; a reconhecida pode ser trocada,
    // se a IA errou); depois do aceite, texto. A coluna já dividida não tem campo: os campos estão nas partes.
    const celula_do_campo = criar_elemento_real("td", "", "");
    let escolha = null;
    if (coluna.divisao) {
      celula_do_campo.textContent = "Nas partes abaixo";
    } else if (coluna.precisa_decidir && aceite_aberto) {
      escolha = montar_escolha_do_campo(coluna);
    } else if (aceite_aberto) {
      escolha = montar_troca_do_campo(coluna, leitura.campos_do_layout);
    } else {
      celula_do_campo.textContent = coluna.campo || "—";
    }
    if (escolha !== null) {
      celula_do_campo.append(escolha);
    }
    linha.append(celula_do_campo);
    // A situação, com a cor (a original fica guardada para voltar se a pessoa desfizer a troca).
    const celula_da_situacao = criar_elemento_real("td", "", "");
    const selo = criar_elemento_real("span", "selo selo-pequeno " + classe_da_situacao(coluna), coluna.situacao);
    selo.dataset.textoOriginal = coluna.situacao;
    selo.dataset.classeOriginal = classe_da_situacao(coluna);
    celula_da_situacao.append(selo);
    linha.append(celula_da_situacao);
    // O motivo, em letra menor.
    const celula_do_motivo = criar_elemento_real("td", "celula-motivo", coluna.justificativa);
    linha.append(celula_do_motivo);
    corpo.append(linha);
    // A coluna que a IA dividiu: a prévia e o pedido para refazer, logo abaixo dela (antes das partes). Ela vai junto
    // com a coluna na separação (o mesmo grupo).
    if (coluna.divisao && coluna.situacao === SITUACAO_DIVIDIDA_PELA_IA && aceite_aberto) {
      const conferencia_da_divisao = montar_conferencia_da_divisao(coluna);
      conferencia_da_divisao.dataset.grupoDaColuna = coluna.coluna;
      corpo.append(conferencia_da_divisao);
    }
    // Trocar o campo muda a situação na hora e confere o tipo dos valores.
    if (escolha !== null) {
      escolha.addEventListener("change", function () {
        // Escolheu: a marca de "falta escolher" sai (ela volta se o aceite for recusado de novo)
        escolha.classList.remove(CLASSE_DA_ESCOLHA_QUE_FALTA);
        escolha.removeAttribute("aria-invalid");
        quando_a_pessoa_troca_o_campo(escolha, selo, celula_do_motivo, linha);
        // A nota "Fica guardada sem rótulo" acompanha a escolha: some quando se escolhe um campo (ADR-143, Parte 1)
        atualizar_nota_sem_rotulo(linha);
      });
    }
  }
  // Campos obrigatórios que nenhuma coluna alimenta.
  const obrigatorios = document.querySelector("[data-real-obrigatorios]");
  obrigatorios.hidden = leitura.obrigatorios_sem_coluna.length === 0;
  obrigatorios.textContent = "Campos obrigatórios sem coluna no arquivo: " + leitura.obrigatorios_sem_coluna.join(", ") +
    ". Eles viram pendência para você completar.";
  // Só as colunas das informações obrigatórias ficam em cima; as outras descem, fechadas (ADR-143)
  separar_as_colunas_opcionais();
}

// ===== O aceite só das informações obrigatórias (ADR-143) =====

// A situação da coluna em dúvida entre campos que não são obrigatórios: fica de fora, sem pergunta.
const SITUACAO_FICA_DE_FORA = "Fica de fora (não é obrigatória)";

/**
 * Os campos que uma coluna da leitura alimenta, ou pode alimentar: o campo proposto e, na coluna em que a IA pediu
 * ajuda, os candidatos.
 *
 * Recebe: coluna — da leitura. Devolve: a lista de nomes técnicos (vazia na coluna deixada de fora).
 * Ex.: {campo: "cpf"} → ["cpf"]; {precisa_decidir: true, candidatos: ["telefone_celular", "telefone_residencial"]} →
 * os dois candidatos.
 */
function campos_da_coluna_lida(coluna) {
  const campos = [];
  if (coluna.campo) {
    campos.push(coluna.campo);
  }
  // A coluna em dúvida pode ir para qualquer um dos candidatos
  if (coluna.precisa_decidir) {
    for (const candidato of coluna.candidatos || []) {
      campos.push(candidato);
    }
  }
  return campos;
}

/**
 * Os grupos de linhas do aceite que alimentam (ou podem alimentar) uma informação obrigatória do parâmetro. Um grupo é
 * a coluna do arquivo com as partes dela, quando a coluna foi dividida (o endereço inteiro numa célula, ADR-104).
 *
 * Recebe: linhas — as <tr> das colunas (marcadas com data-grupo-da-coluna e data-campos-da-coluna).
 * Devolve: um Set com os nomes dos grupos. Ex.: a coluna "Documento", lida como cpf → Set {"Documento"}.
 */
function grupos_com_campo_obrigatorio(linhas) {
  const grupos = new Set();
  for (const linha of linhas) {
    // Os campos da linha, separados por espaço (ex.: "telefone_celular telefone_residencial")
    for (const campo of linha.dataset.camposDaColuna.split(" ")) {
      if (campos_obrigatorios_do_cadastro.includes(campo)) {
        grupos.add(linha.dataset.grupoDaColuna);
      }
    }
  }
  return grupos;
}

/**
 * A coluna em dúvida só entre campos que não são obrigatórios fica de fora, sem pergunta: a escolha dela já vem em
 * "Deixar de fora", e a pessoa ainda pode escolher um dos campos se quiser (ADR-143: a IA não pergunta do opcional).
 *
 * Recebe: linha — a <tr> da coluna, já no bloco das outras informações. Devolve: nada.
 * Só mexe na escolha que ainda está em "Escolha o campo": o que a pessoa já escolheu fica como está.
 */
function deixar_de_fora_sem_pergunta(linha) {
  const escolha = linha.querySelector("select[data-precisa-decidir]");
  // Coluna sem dúvida, ou dúvida que a pessoa já resolveu
  if (!escolha || escolha.value !== "") {
    return;
  }
  // "Deixar de fora" vai no aceite, como se a pessoa tivesse escolhido (o servidor não trava por esta coluna)
  escolha.value = OPCAO_IGNORAR;
  // A marca de "falta escolher" (de um aceite recusado antes) sai: esta coluna não pede escolha
  escolha.classList.remove(CLASSE_DA_ESCOLHA_QUE_FALTA);
  escolha.removeAttribute("aria-invalid");
  // O selo diz que a coluna fica de fora; é também a situação a que ela volta se a pessoa desfizer outra escolha
  const selo = linha.querySelector(".selo");
  selo.dataset.textoOriginal = SITUACAO_FICA_DE_FORA;
  selo.dataset.classeOriginal = "selo-neutro";
  pintar_selo(selo, SITUACAO_FICA_DE_FORA, "selo-neutro");
}

/**
 * Separa o aceite das colunas em duas partes: em cima, as colunas das informações obrigatórias do parâmetro (a empresa
 * confirma essas); embaixo, fechadas em "Outras informações do arquivo", as demais, que entram sem pergunta
 * (ADR-143).
 *
 * Recebe: nada (usa campos_obrigatorios_do_cadastro, do js/cadastrar_obrigatorios.js). Devolve: nada.
 * Sem a lista dos obrigatórios (ela ainda não chegou, ou a página está sem servidor), tudo fica numa tabela só, como
 * antes. Quando a lista chega depois, a separação é feita: as linhas só mudam de lugar, e as escolhas feitas ficam.
 */
function separar_as_colunas_opcionais() {
  // Sem a lista dos obrigatórios: uma tabela só
  if (campos_obrigatorios_do_cadastro === null) {
    return;
  }
  const corpo_principal = document.querySelector("[data-real-corpo-colunas]");
  const corpo_das_outras = document.querySelector("[data-real-corpo-colunas-opcionais]");
  const linhas_das_colunas = corpo_principal.querySelectorAll("tr[data-campos-da-coluna]");
  const grupos_obrigatorios = grupos_com_campo_obrigatorio(linhas_das_colunas);
  // As linhas dos grupos que não alimentam nenhum obrigatório descem, na mesma ordem (Array.from: a lista não muda
  // enquanto as linhas saem da tabela de cima)
  for (const linha of Array.from(corpo_principal.querySelectorAll("tr[data-grupo-da-coluna]"))) {
    if (!grupos_obrigatorios.has(linha.dataset.grupoDaColuna)) {
      corpo_das_outras.append(linha);
      deixar_de_fora_sem_pergunta(linha);
    }
  }
  // A nota "Fica guardada sem rótulo" nas colunas em dúvida só entre opcionais que ficam de fora (ADR-143, Parte 1)
  atualizar_as_notas_sem_rotulo();
  // O bloco das outras aparece só com alguma coluna, e o título diz quantas
  const quantas_outras = corpo_das_outras.querySelectorAll("tr[data-campos-da-coluna]").length;
  document.querySelector("[data-real-bloco-colunas-opcionais]").hidden = quantas_outras === 0;
  document.querySelector("[data-real-titulo-colunas-opcionais]").textContent = "Outras informações do arquivo (" +
    quantidade_no_singular_ou_plural(quantas_outras, "coluna", "colunas") + ", sem precisar da sua confirmação)";
  // Nenhuma coluna ficou em cima: a tabela diz isso, em vez de ficar vazia (o aviso dos obrigatórios sem coluna vem
  // logo abaixo)
  if (corpo_principal.querySelectorAll("tr[data-campos-da-coluna]").length === 0) {
    const linha_vazia = criar_elemento_real("tr", "", "");
    const celula = criar_elemento_real("td", "nota-tabela",
      "Nenhuma coluna do arquivo foi lida como informação obrigatória.");
    celula.colSpan = 4;
    linha_vazia.append(celula);
    corpo_principal.replaceChildren(linha_vazia);
  }
  // A nota de cima explica a separação
  document.querySelector("[data-real-nota-obrigatorias]").hidden = false;
}

// ===== A coluna que fica guardada sem rótulo (ADR-143, Parte 1) =====

// A nota da coluna em dúvida só entre campos opcionais que fica de fora: o valor dela não se perde, fica guardado.
const NOTA_GUARDADA_SEM_ROTULO = "Fica guardada sem rótulo";
// O que a nota explica ao passar o mouse.
const EXPLICACAO_DA_NOTA_SEM_ROTULO = "O Agente Interpretador não teve certeza de qual campo é esta coluna. " +
  "O valor de cada pessoa fica guardado, sem entrar nas análises, e aparece no detalhe dela.";

/**
 * Verdadeiro quando a coluna fica guardada sem rótulo: ela fica de fora ("Deixar de fora" escolhido), sem divisão, e
 * os campos que a IA indicou para ela, contando só os do parâmetro vigente, são todos opcionais (pelo menos um). É a
 * mesma regra do servidor, que guarda o valor de cada pessoa (services/informacoes_sem_rotulo.py): o candidato que
 * não está no parâmetro vigente não conta.
 *
 * Recebe: linha — a <tr> da coluna no aceite (marcada com data-candidatos-da-coluna). Devolve: true ou false.
 * Ex.: "C.E.P", em dúvida entre o CEP residencial e o comercial, em "Deixar de fora" → true; a mesma coluna com um dos
 * CEPs escolhido → false (vira um campo normal); "Documento", em dúvida entre o CPF (obrigatório) e o RG → false (a
 * dúvida com um obrigatório continua pedindo a escolha); "Religião", que a IA deixou de fora sem candidato → false.
 * Vale também para a coluna reaproveitada do aceite de um envio anterior (numa inclusão): ela já vem em "Deixar de
 * fora", sem pedir a escolha, mas com os mesmos candidatos.
 */
function coluna_fica_guardada_sem_rotulo(linha) {
  const escolha = linha.querySelector("select[data-coluna]");
  // Só a coluna com "Deixar de fora" escolhido (a coluna dividida não tem escolha: os campos estão nas partes dela)
  if (!escolha || escolha.value !== OPCAO_IGNORAR) {
    return false;
  }
  // Sem a lista dos obrigatórios (ou sem a leitura), não dá para saber se a dúvida é só entre opcionais
  if (campos_obrigatorios_do_cadastro === null || !envio_de_verdade || !envio_de_verdade.leitura) {
    return false;
  }
  // Os campos do parâmetro vigente (os nomes técnicos que a leitura traz)
  const campos_do_parametro = envio_de_verdade.leitura.campos_do_layout || [];
  // Quantos dos campos indicados pela IA estão no parâmetro vigente
  let candidatos_do_parametro = 0;
  for (const candidato of linha.dataset.candidatosDaColuna.split(" ")) {
    // O candidato fora do parâmetro vigente não conta (nem o texto vazio, da coluna sem candidato)
    if (!campos_do_parametro.includes(candidato)) {
      continue;
    }
    // Um candidato obrigatório basta: a dúvida é da empresa, e a coluna não fica guardada
    if (campos_obrigatorios_do_cadastro.includes(candidato)) {
      return false;
    }
    candidatos_do_parametro = candidatos_do_parametro + 1;
  }
  // Sem nenhum candidato do parâmetro, a coluna é desconhecida: não fica guardada
  return candidatos_do_parametro > 0;
}

/**
 * Põe ou tira a nota "Fica guardada sem rótulo" embaixo do selo da situação de uma coluna, conforme a escolha dela
 * agora.
 *
 * Recebe: linha — a <tr> da coluna. Devolve: nada.
 */
function atualizar_nota_sem_rotulo(linha) {
  // Tira a nota de antes, se houver (a escolha pode ter mudado)
  const nota_de_antes = linha.querySelector("[data-nota-sem-rotulo]");
  if (nota_de_antes) {
    nota_de_antes.remove();
  }
  if (!coluna_fica_guardada_sem_rotulo(linha)) {
    return;
  }
  const nota = criar_elemento_real("span", "nota-sem-rotulo-da-coluna", NOTA_GUARDADA_SEM_ROTULO);
  nota.dataset.notaSemRotulo = "";
  nota.title = EXPLICACAO_DA_NOTA_SEM_ROTULO;
  // Logo depois do selo da situação
  linha.querySelector(".selo").after(nota);
}

/**
 * Refaz a nota "Fica guardada sem rótulo" em todas as colunas do aceite: as de cima e as de "Outras informações do
 * arquivo".
 *
 * Recebe: nada. Devolve: nada. É chamada quando as colunas se separam (a lista dos obrigatórios pode chegar depois).
 */
function atualizar_as_notas_sem_rotulo() {
  // As linhas das duas tabelas (a de cima e a das outras informações)
  const linhas_das_colunas = document.querySelectorAll("[data-real-corpo-colunas] tr[data-campos-da-coluna], " +
    "[data-real-corpo-colunas-opcionais] tr[data-campos-da-coluna]");
  for (const linha of linhas_das_colunas) {
    atualizar_nota_sem_rotulo(linha);
  }
}

/**
 * A classe do selo da situação: verde (reconhecida), laranja (escolha o campo), cinza (deixada de fora), azul
 * (a empresa trocou o campo: "Ajustado por você").
 *
 * Recebe: coluna. Devolve: o nome da classe.
 */
function classe_da_situacao(coluna) {
  if (coluna.precisa_decidir) {
    return "selo-atencao";
  }
  // A coluna que a IA dividiu e cada parte dela: o selo da divisão
  if (coluna.situacao === SITUACAO_DIVIDIDA_PELA_IA || coluna.situacao === SITUACAO_PARTE_DA_IA) {
    return "selo-dividido";
  }
  if (coluna.situacao === SITUACAO_AJUSTADA) {
    return "selo-ajustado";
  }
  if (!coluna.campo) {
    return "selo-neutro";
  }
  return "selo-sucesso";
}

/**
 * A conferência da divisão que a IA fez numa coluna: a prévia, parte por parte, e o pedido para refazer (ADR-104).
 *
 * Recebe: coluna — com "divisao" ({partes, previa: {colunas, linhas}, refazer_restantes}). Devolve: a <tr> pronta.
 * O botão "Refazer a divisão desta coluna" só liga quando a pessoa escreve o que está errado: a IA refaz SÓ esta
 * coluna, com o comentário; o resto do arquivo continua como está.
 */
function montar_conferencia_da_divisao(coluna) {
  const divisao = coluna.divisao;
  const linha = criar_elemento_real("tr", "linha-divisao", "");
  const celula = criar_elemento_real("td", "", "");
  celula.colSpan = 4;
  const area = criar_elemento_real("div", "area-divisao", "");
  area.dataset.conferenciaDaDivisao = coluna.coluna;
  area.append(criar_elemento_real("p", "ajuste-titulo",
    "O Agente Interpretador viu mais de uma informação em cada célula e dividiu esta coluna em " +
    divisao.partes.length + " partes. Confira as primeiras linhas:"));
  // A prévia: a célula como está no arquivo e, ao lado, cada parte
  const tabela = criar_elemento_real("table", "tabela-montada tabela-previa-divisao", "");
  const cabeca = criar_elemento_real("tr", "", "");
  cabeca.append(criar_elemento_real("th", "", "No seu arquivo"));
  for (const nome_da_parte of divisao.previa.colunas) {
    cabeca.append(criar_elemento_real("th", "", nome_da_parte));
  }
  tabela.append(cabeca);
  for (const valores of divisao.previa.linhas) {
    const linha_da_previa = criar_elemento_real("tr", "", "");
    for (const valor of valores) {
      linha_da_previa.append(criar_elemento_real("td", "", valor || "—"));
    }
    tabela.append(linha_da_previa);
  }
  area.append(tabela);
  area.append(criar_elemento_real("p", "nota-tabela",
    "Cada parte está logo abaixo, com o campo do banco; se só o campo de uma parte estiver errado, troque ali mesmo. " +
    "O que não coube em nenhuma parte fica em branco e vira pendência: nada é inventado."));
  // Sem tentativas: só o aviso
  if (divisao.refazer_restantes === 0) {
    area.append(criar_elemento_real("p", "alerta-do-tipo",
      "O Agente Interpretador já refez esta divisão o máximo de vezes. Ajuste o campo de cada parte abaixo ou " +
      "deixe a coluna de fora."));
    celula.append(area);
    linha.append(celula);
    return linha;
  }
  // O comentário e o botão: o botão só liga com o comentário escrito
  const comentario = criar_elemento_real("textarea", "campo-entrada", "");
  comentario.rows = 2;
  comentario.maxLength = 500;
  comentario.placeholder = "Algo errado na divisão? Conte para o Agente Interpretador (ex.: é o endereço do " +
    "trabalho, não o de casa).";
  comentario.setAttribute("aria-label", "O que está errado na divisão da coluna " + coluna.coluna);
  comentario.dataset.comentarioDaDivisao = "";
  const botoes = criar_elemento_real("div", "ajuste-botoes", "");
  const refazer = criar_elemento_real("button", "botao botao-principal botao-pequeno", "Refazer a divisão desta coluna");
  refazer.type = "button";
  refazer.disabled = true;
  refazer.dataset.refazerDivisao = "";
  const restantes = criar_elemento_real("span", "nota-tabela",
    "Você pode pedir mais " + divisao.refazer_restantes + " vez(es).");
  botoes.append(refazer, restantes);
  area.append(comentario, botoes);
  // O botão liga e desliga conforme o comentário
  comentario.addEventListener("input", function () {
    refazer.disabled = comentario.value.trim() === "";
  });
  refazer.addEventListener("click", function () {
    refazer_a_divisao(coluna.coluna, comentario.value, refazer);
  });
  celula.append(area);
  linha.append(celula);
  return linha;
}

/**
 * Pede à IA para refazer a divisão de UMA coluna com o comentário da pessoa, e redesenha a tabela.
 *
 * Recebe: coluna; comentario; botao — fica desligado enquanto a IA trabalha. Devolve: nada.
 */
async function refazer_a_divisao(coluna, comentario, botao) {
  botao.disabled = true;
  botao.textContent = "O Agente Interpretador está refazendo…";
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/refazer_divisao", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coluna: coluna, comentario: comentario }),
  });
  if (!resposta.ok) {
    botao.disabled = false;
    botao.textContent = "Refazer a divisão desta coluna";
    mostrar_erro_real(texto_do_erro(resposta.dados.detail));
    return;
  }
  envio_de_verdade.leitura = resposta.dados;
  mostrar_resultado_real(resposta.dados);
  document.querySelector("[data-real-subtitulo]").textContent =
    "O Agente Interpretador refez a divisão de \"" + coluna + "\" com o seu comentário: confira as partes e " +
    "aceite as colunas.";
}

/**
 * Troca a aparência do selo da situação.
 *
 * Recebe: selo; texto; classe. Devolve: nada.
 */
function pintar_selo(selo, texto, classe) {
  selo.className = "selo selo-pequeno " + classe;
  selo.textContent = texto;
}

/**
 * A pessoa trocou o campo de uma coluna: a situação vira "Ajustado por você" e a tela confere, no servidor, se os
 * valores da coluna servem para o campo novo. Se não servem (tipo diferente), aparece o alerta e o selo fica laranja.
 * Voltar ao campo que a IA propôs desfaz tudo.
 *
 * Recebe: escolha — o <select>; selo — o da situação; celula_do_motivo — onde o alerta aparece; linha — a <tr>
 *         (a divisão abre logo abaixo dela). Devolve: nada.
 * A escolha vale: se a pessoa aceitar mesmo com o alerta, os valores que não servem viram pendência em Acompanhar.
 */
async function quando_a_pessoa_troca_o_campo(escolha, selo, celula_do_motivo, linha) {
  // Tira o alerta de uma troca anterior
  const alerta_antigo = celula_do_motivo.querySelector(".alerta-do-tipo");
  if (alerta_antigo) {
    alerta_antigo.remove();
  }
  // Fecha a divisão aberta nesta linha, se houver
  fechar_divisao(linha);
  // "Dividir em vários campos…": abre a escolha do destino e a prévia, logo abaixo da linha
  if (escolha.value === OPCAO_DIVIDIR) {
    abrir_divisao(escolha, linha);
    return;
  }
  // Voltou ao que a IA propôs (ou ainda não escolheu): a situação original
  const voltou_ao_original = escolha.dataset.original !== undefined && escolha.value === escolha.dataset.original;
  if (voltou_ao_original || escolha.value === "") {
    pintar_selo(selo, selo.dataset.textoOriginal, selo.dataset.classeOriginal);
    return;
  }
  pintar_selo(selo, SITUACAO_AJUSTADA, "selo-ajustado");
  // "Deixar de fora" não tem tipo para conferir
  if (escolha.value === OPCAO_IGNORAR) {
    return;
  }
  const campo_escolhido = escolha.value;
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/conferir_coluna", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coluna: escolha.dataset.coluna, campo: campo_escolhido }),
  });
  // A pessoa trocou de novo enquanto a resposta vinha: vale a última troca
  if (escolha.value !== campo_escolhido) {
    return;
  }
  if (resposta.ok && resposta.dados.mensagem) {
    pintar_selo(selo, "Ajustado · confira o tipo", "selo-atencao");
    celula_do_motivo.append(criar_elemento_real("span", "alerta-do-tipo", resposta.dados.mensagem));
  }
}

/**
 * Fecha a área de divisão aberta logo abaixo da linha, se houver.
 *
 * Recebe: linha — a <tr> da coluna. Devolve: nada.
 */
function fechar_divisao(linha) {
  const proxima = linha.nextElementSibling;
  if (proxima && proxima.classList.contains("linha-divisao")) {
    proxima.remove();
  }
}

/**
 * Abre, logo abaixo da coluna, a divisão em vários campos: para onde dividir, a prévia e "Dividir esta coluna".
 *
 * Recebe: escolha — o <select> da coluna; linha — a <tr> da coluna. Devolve: nada.
 * Nada é gravado até "Dividir esta coluna". "Cancelar" volta a escolha ao que era.
 */
function abrir_divisao(escolha, linha) {
  const linha_da_divisao = criar_elemento_real("tr", "linha-divisao", "");
  const celula = criar_elemento_real("td", "", "");
  celula.colSpan = 4;
  const area = criar_elemento_real("div", "area-divisao", "");
  area.append(criar_elemento_real("p", "ajuste-titulo",
    "Esta coluna tem vários dados em cada célula? Escolha para onde dividir e confira a prévia."));
  // A orientação: o que ajuda a divisão a acertar e o que acontece com o que não couber
  area.append(criar_elemento_real("p", "nota-tabela",
    "Dica: a divisão acerta mais quando as partes vêm separadas por vírgula ou traço (“Rua das Flores, 123, " +
    "Centro, São Paulo - SP, 01234-567”). Rua, número, complemento, UF e CEP são achados em qualquer posição; " +
    "sem a palavra “Bairro”, o bairro precisa vir antes da cidade. O que não couber não é inventado: fica " +
    "em branco e vira pendência para você completar em “Acompanhar cadastros”."));
  // Para onde dividir (ex.: Endereço residencial)
  const destino = criar_elemento_real("select", "campo-entrada campo-pequeno", "");
  destino.setAttribute("aria-label", "Dividir em");
  destino.dataset.destinoDaDivisao = "";
  for (const nome of envio_de_verdade.leitura.destinos_da_divisao) {
    destino.add(new Option(nome, nome));
  }
  const previa = criar_elemento_real("div", "previa-divisao", "");
  const botoes = criar_elemento_real("div", "ajuste-botoes", "");
  const dividir = criar_elemento_real("button", "botao botao-principal botao-pequeno", "Dividir esta coluna");
  dividir.type = "button";
  dividir.dataset.dividirColuna = "";
  const cancelar = criar_elemento_real("button", "botao-descartar", "Cancelar");
  cancelar.type = "button";
  botoes.append(dividir, cancelar);
  area.append(destino, previa, botoes);
  celula.append(area);
  linha_da_divisao.append(celula);
  linha.after(linha_da_divisao);
  // A prévia muda com o destino
  destino.addEventListener("change", function () {
    mostrar_previa_da_divisao(escolha.dataset.coluna, destino.value, previa);
  });
  cancelar.addEventListener("click", function () {
    escolha.value = escolha.dataset.original || "";
    linha_da_divisao.remove();
  });
  dividir.addEventListener("click", function () {
    dividir_a_coluna(escolha.dataset.coluna, destino.value, dividir);
  });
  mostrar_previa_da_divisao(escolha.dataset.coluna, destino.value, previa);
}

/**
 * Pede ao servidor como a coluna ficaria dividida e mostra os primeiros exemplos, parte por parte.
 *
 * Recebe: coluna; destino; area — onde a prévia aparece. Devolve: nada.
 * Os valores aparecem como estão no arquivo da empresa.
 */
async function mostrar_previa_da_divisao(coluna, destino, area) {
  area.replaceChildren(criar_elemento_real("p", "nota-tabela", "Preparando a prévia…"));
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/previa_da_divisao", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coluna: coluna, destino: destino }),
  });
  area.replaceChildren();
  if (!resposta.ok) {
    area.append(criar_elemento_real("p", "erro-pendencia", texto_do_erro(resposta.dados.detail)));
    return;
  }
  // Uma tabela pequena: uma coluna por parte, uma linha por exemplo
  const tabela = criar_elemento_real("table", "tabela-montada tabela-previa-divisao", "");
  const cabeca = criar_elemento_real("tr", "", "");
  for (const parte of resposta.dados.partes) {
    cabeca.append(criar_elemento_real("th", "", parte.nome));
  }
  tabela.append(cabeca);
  for (const exemplo of resposta.dados.exemplos) {
    const linha = criar_elemento_real("tr", "", "");
    for (const parte of resposta.dados.partes) {
      linha.append(criar_elemento_real("td", "", exemplo.partes[parte.parte] || "—"));
    }
    tabela.append(linha);
  }
  area.append(tabela);
  // O que a regra não soube onde pôr (não vai para campo nenhum)
  if (resposta.dados.linhas_com_sobra > 0) {
    area.append(criar_elemento_real("p", "alerta-do-tipo",
      resposta.dados.linhas_com_sobra + " linha(s) têm um pedaço que não deu para saber se é bairro ou cidade " +
      "(ou que sobrou): ele não vai para campo nenhum. Se o campo for obrigatório, vira pendência depois do aceite."));
  }
}

/**
 * Divide a coluna de verdade: cada parte vira uma coluna nova, ligada ao seu campo, e a tabela é redesenhada.
 *
 * Recebe: coluna; destino; botao — "Dividir esta coluna" (fica desligado enquanto espera). Devolve: nada.
 */
async function dividir_a_coluna(coluna, destino, botao) {
  botao.disabled = true;
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/dividir", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coluna: coluna, destino: destino }),
  });
  botao.disabled = false;
  if (!resposta.ok) {
    mostrar_erro_real(texto_do_erro(resposta.dados.detail));
    return;
  }
  envio_de_verdade.leitura = resposta.dados;
  mostrar_resultado_real(resposta.dados);
  document.querySelector("[data-real-subtitulo]").textContent =
    "A coluna \"" + coluna + "\" foi dividida: confira cada parte abaixo e aceite as colunas.";
}

/**
 * A lista de escolha do campo de uma coluna ambígua: os candidatos que a IA indicou e "Deixar de fora".
 *
 * Recebe: coluna. Devolve: o elemento <select>, marcado com a coluna (data-coluna).
 */
function montar_escolha_do_campo(coluna) {
  const escolha = criar_elemento_real("select", "campo-entrada campo-pequeno", "");
  escolha.dataset.coluna = coluna.coluna;
  // A coluna em que a IA pediu ajuda: o aceite recusado sem escolha marca esta lista (marcar_as_colunas_sem_escolha)
  escolha.dataset.precisaDecidir = "sim";
  escolha.setAttribute("aria-label", "Campo da coluna " + coluna.coluna);
  // Primeira opção: pedir a escolha.
  escolha.add(new Option("Escolha o campo", ""));
  // Os candidatos da IA.
  for (const candidato of coluna.candidatos) {
    escolha.add(new Option(candidato, candidato));
  }
  // Deixar a coluna de fora.
  escolha.add(new Option("Deixar de fora", OPCAO_IGNORAR));
  acrescentar_opcao_de_dividir(escolha);
  return escolha;
}

/**
 * Acrescenta "Dividir em vários campos…" à lista, quando o layout tem para onde dividir (ex.: endereço residencial).
 *
 * Recebe: escolha — o <select>. Devolve: nada.
 */
function acrescentar_opcao_de_dividir(escolha) {
  const destinos = envio_de_verdade.leitura.destinos_da_divisao || [];
  if (destinos.length > 0) {
    escolha.add(new Option("Dividir em vários campos…", OPCAO_DIVIDIR));
  }
}

/**
 * A lista para trocar o campo de uma coluna que a IA já reconheceu (ou deixou de fora), se ela errou.
 *
 * Recebe: coluna; campos_do_layout — todos os campos. Devolve: o <select>, com o campo atual marcado.
 * data-original guarda o campo da IA: só a coluna que a pessoa MUDOU vai para o servidor.
 */
function montar_troca_do_campo(coluna, campos_do_layout) {
  const escolha = criar_elemento_real("select", "campo-entrada campo-pequeno", "");
  escolha.dataset.coluna = coluna.coluna;
  // Deixada de fora pela IA: o original é "Deixar de fora".
  let original = OPCAO_IGNORAR;
  if (coluna.campo) {
    original = coluna.campo;
  }
  escolha.dataset.original = original;
  escolha.setAttribute("aria-label", "Campo da coluna " + coluna.coluna);
  for (const campo of campos_do_layout) {
    escolha.add(new Option(campo, campo));
  }
  escolha.add(new Option("Deixar de fora", OPCAO_IGNORAR));
  acrescentar_opcao_de_dividir(escolha);
  escolha.value = original;
  return escolha;
}

/**
 * Mostra só os botões que fazem sentido na etapa atual.
 *
 * Recebe: leitura. Devolve: nada.
 */
function mostrar_botoes_da_etapa(leitura) {
  document.querySelector("[data-real-aceitar]").hidden = leitura.etapa !== "aprovar_mapeamento";
  document.querySelector("[data-real-homologar]").hidden = leitura.etapa !== "aprovar_homologacao";
  document.querySelector("[data-real-ir-pendencias]").hidden = leitura.etapa !== "aguardar_correcao";
  // "Tentar de novo": só com o envio parado esperando uma nova tentativa (ADR-139).
  document.querySelector("[data-real-tentar-de-novo]").hidden = leitura.etapa !== "aguardar_nova_tentativa";
  // Acompanhar: depois do fim ou enquanto o banco avalia.
  const esperando_o_banco = leitura.etapa === "avaliar_no_banco";
  document.querySelector("[data-real-ir-acompanhar]").hidden = !leitura.terminou && !esperando_o_banco;
  // Descartar vale enquanto o fluxo espera uma decisão da empresa (não depois do fim, nem com o banco avaliando).
  document.querySelector("[data-real-descartar]").hidden = leitura.terminou || esperando_o_banco;
}

// ===== 3. As ações: aceitar, cadastrar e descartar (a janela do descarte fica em js/descartar_envio.js) =====

// As escolhas de campo do aceite, nas duas tabelas: a das informações obrigatórias e a das outras (ADR-143).
const SELETOR_DAS_ESCOLHAS_DO_ACEITE = "[data-real-corpo-colunas] select, [data-real-corpo-colunas-opcionais] select";

/**
 * Junta as escolhas da pessoa: { coluna: campo }, das ambíguas decididas e das reconhecidas que ela trocou.
 * Escolha vazia não entra (o servidor avisa); coluna que ficou como a IA leu também não (não foi mudada).
 *
 * Recebe: nada. Devolve: o dicionário das escolhas (das duas tabelas do aceite).
 */
function escolhas_das_colunas() {
  const escolhas = {};
  for (const escolha of document.querySelectorAll(SELETOR_DAS_ESCOLHAS_DO_ACEITE)) {
    const mudou = escolha.dataset.original === undefined || escolha.value !== escolha.dataset.original;
    if (escolha.value !== "" && escolha.value !== OPCAO_DIVIDIR && mudou) {
      escolhas[escolha.dataset.coluna] = escolha.value;
    }
  }
  return escolhas;
}

/**
 * Depois do descarte: a tela volta limpa para a escolha do arquivo, com o aviso de que a leitura foi descartada.
 *
 * Recebe: nada. Devolve: nada. Recarrega a página sem o envio no endereço (e com "descartado=1", que liga o aviso);
 * dentro da janela "Cadastrar funcionários", continua dentro dela.
 */
function voltar_para_a_escolha_do_arquivo() {
  const endereco = new URL(window.location.href);
  // Sem o envio no endereço, a tela abre na escolha do arquivo
  endereco.searchParams.delete("envio");
  endereco.searchParams.set("descartado", "1");
  window.location.replace(endereco.toString());
}

/**
 * Mostra, em cima da escolha do arquivo, o aviso de que a última leitura foi descartada.
 *
 * Recebe: nada. Devolve: nada. Só mostra quando o endereço traz "descartado=1".
 */
function mostrar_aviso_de_descarte() {
  if (new URLSearchParams(window.location.search).get("descartado") === null) {
    return;
  }
  document.querySelector("[data-aviso-descartado]").hidden = false;
}

// O texto do botão de uma ação enquanto o servidor trabalha (ex.: o aceite padroniza e valida o arquivo inteiro)
const TEXTO_DO_BOTAO_ESPERANDO = "Aguarde…";
// A classe da coluna que ainda espera a escolha do campo depois de um aceite recusado (css/estilos.css)
const CLASSE_DA_ESCOLHA_QUE_FALTA = "escolha-que-falta";

/**
 * Leva o recado (ou o erro) de uma ação para a vista: nenhum botão de ação fica mudo.
 *
 * Para que serve: o recado fica no alto do cartão, acima da tabela das colunas, e o botão fica embaixo dela. Sem
 * isso, quem clicava em "Aceitar as colunas" com uma coluna ainda sem escolha não via nada mudar perto do botão.
 * Recebe: nada. Devolve: nada. Sem recado à vista (a caixa escondida), não faz nada.
 */
function levar_o_recado_para_a_vista() {
  const recado = document.querySelector("[data-real-erro]");
  // Nada para mostrar: a tela fica onde está
  if (recado.hidden) {
    return;
  }
  // Rola a página (ou a janela "Cadastrar funcionários") até o recado, no meio da tela
  recado.scrollIntoView({ block: "center" });
}

/**
 * Marca as colunas em que a IA pediu a escolha do campo e que continuam sem escolha (a borda na cor da marca).
 *
 * Recebe: nada. Devolve: nada. A marca sai sozinha quando a pessoa escolhe o campo (montar_tabela_de_colunas).
 * Ex.: a coluna "Vencimentos" com "Escolha o campo" ainda selecionado → marcada e anunciada como inválida.
 */
function marcar_as_colunas_sem_escolha() {
  for (const escolha of document.querySelectorAll(SELETOR_DAS_ESCOLHAS_DO_ACEITE)) {
    // Só a coluna em que a IA pediu ajuda e que continua em "Escolha o campo" (valor vazio)
    if (escolha.dataset.precisaDecidir && escolha.value === "") {
      escolha.classList.add(CLASSE_DA_ESCOLHA_QUE_FALTA);
      // O leitor de tela também diz que o campo precisa de atenção
      escolha.setAttribute("aria-invalid", "true");
      // Se ela está nas outras informações (fechadas), o bloco abre, para a pessoa ver o que falta
      const bloco_fechado = escolha.closest("details");
      if (bloco_fechado) {
        bloco_fechado.open = true;
      }
    }
  }
}

/**
 * Faz uma ação do envio (aceitar ou cadastrar) e mostra a leitura que volta.
 *
 * Recebe: botao — o botão clicado (fica desligado enquanto espera); acao — "aceitar" ou "homologar";
 *         corpo — o que mandar (ou null). Devolve: nada.
 */
async function fazer_acao_do_envio(botao, acao, corpo) {
  // Enquanto o servidor trabalha, o botão diz "Aguarde…" (um botão só desligado parece morto)
  const texto_do_botao = botao.textContent;
  botao.disabled = true;
  botao.textContent = TEXTO_DO_BOTAO_ESPERANDO;
  const opcoes = { method: "POST" };
  if (corpo !== null) {
    opcoes.headers = { "Content-Type": "application/json" };
    opcoes.body = JSON.stringify(corpo);
  }
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/" + acao, opcoes);
  // A resposta chegou: o botão volta ao normal
  botao.disabled = false;
  botao.textContent = texto_do_botao;
  // Recusado: mostra a explicação à vista e mantém a tela como está.
  if (!resposta.ok) {
    mostrar_erro_real(texto_do_erro(resposta.dados.detail));
    // O aceite recusado fala das colunas: a aba "Como o agente leu" abre, com a tabela delas (js/cadastrar_abas.js)
    if (acao === "aceitar") {
      abrir_a_aba_do_resultado(ABA_DAS_COLUNAS);
    }
    levar_o_recado_para_a_vista();
    return;
  }
  // Na janela, com as colunas aceitas, o resto acontece em "Acompanhar cadastros".
  if (TELA_EM_JANELA && acao === "aceitar" && resposta.dados.etapa !== "aprovar_mapeamento") {
    ir_para_acompanhar(envio_de_verdade.id, "colunas_aceitas");
    return;
  }
  // Deu certo: mostra a nova situação.
  envio_de_verdade.leitura = resposta.dados;
  mostrar_resultado_real(resposta.dados);
  // O servidor respondeu, mas o fluxo não avançou e voltou com um recado (ex.: "Escolha o campo (ou ignore) destas
  // colunas: Vencimentos"): as colunas que faltam ficam marcadas, e o recado vem para a vista
  if (resposta.dados.erro) {
    // As colunas que faltam estão na aba "Como o agente leu" (js/cadastrar_abas.js)
    abrir_a_aba_do_resultado(ABA_DAS_COLUNAS);
    marcar_as_colunas_sem_escolha();
    levar_o_recado_para_a_vista();
  }
  // Mensagem final quando o envio terminou.
  if (acao === "homologar" && resposta.dados.etapa === "avaliar_no_banco") {
    document.querySelector("[data-real-subtitulo]").textContent = "Enviado ao banco! Acompanhe a avaliação em \"Acompanhar cadastros\".";
  }
}

/**
 * Liga os botões do bloco do resultado e troca o envio simulado pelo de verdade quando há servidor.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_envio_de_verdade() {
  // O recado das ações é anunciado pelo leitor de tela assim que aparece (role="alert")
  document.querySelector("[data-real-erro]").setAttribute("role", "alert");
  // Aceitar as colunas.
  const botao_aceitar = document.querySelector("[data-real-aceitar]");
  botao_aceitar.addEventListener("click", function () {
    fazer_acao_do_envio(botao_aceitar, "aceitar", { escolhas: escolhas_das_colunas() });
  });
  // Cadastrar.
  const botao_homologar = document.querySelector("[data-real-homologar]");
  botao_homologar.addEventListener("click", function () {
    // Vai junto se a pessoa marcou "Conferi a lista" (fica registrado para o banco ver).
    const conferiu = document.querySelector("[data-real-conferi-caixa]").checked;
    fazer_acao_do_envio(botao_homologar, "homologar", { conferi_a_lista: conferiu });
  });
  // Tentar de novo: retoma o envio parado; com a IA ainda pausada, o recado do servidor aparece e nada muda.
  const botao_tentar_de_novo = document.querySelector("[data-real-tentar-de-novo]");
  botao_tentar_de_novo.addEventListener("click", function () {
    fazer_acao_do_envio(botao_tentar_de_novo, "tentar_de_novo", null);
  });
  // Descartar: a janela pergunta e explica o que acontece (js/descartar_envio.js); descartou, a tela volta limpa.
  const botao_descartar = document.querySelector("[data-real-descartar]");
  botao_descartar.addEventListener("click", async function () {
    const descartou = await perguntar_e_descartar(envio_de_verdade.id);
    if (descartou) {
      voltar_para_a_escolha_do_arquivo();
    }
  });
  // Voltou de um descarte: o aviso aparece em cima da escolha do arquivo
  mostrar_aviso_de_descarte();
}

/**
 * Abre um envio que já existe, pedido no endereço ("cadastrar.html?envio=<id>", vindo de Acompanhar cadastros).
 *
 * Recebe: nada. Devolve: nada. Sem "envio" no endereço, ou página aberta como arquivo, não faz nada.
 * O servidor só devolve envio da empresa de quem entrou (de outra empresa, a resposta é 404 e a tela avisa).
 */
async function retomar_envio_do_endereco() {
  const processamento_id = new URLSearchParams(window.location.search).get("envio");
  if (!processamento_id || !modo_de_verdade()) {
    return;
  }
  envio_de_verdade = { id: processamento_id, leitura: null };
  // Troca a área de envio pelo painel da IA, como num envio novo
  document.getElementById("etapa-envio").hidden = true;
  document.getElementById("etapa-leitura").hidden = false;
  document.getElementById("arquivo-nome").textContent = "Envio já recebido";
  document.getElementById("arquivo-detalhes").textContent = "Abrindo…";
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(processamento_id), {});
  // Envio que não existe ou de outra empresa: volta para a escolha do arquivo
  if (!resposta.ok) {
    envio_de_verdade = null;
    document.getElementById("etapa-envio").hidden = false;
    document.getElementById("etapa-leitura").hidden = true;
    mostrar_erro_real("Não encontrei este envio. Veja os seus envios em \"Acompanhar cadastros\".");
    return;
  }
  envio_de_verdade.leitura = resposta.dados;
  await escrever_mensagem("Voltei ao seu envio de " + resposta.dados.linhas + " linhas. Continue de onde parou.", "normal");
  await contar_a_leitura_no_painel(resposta.dados);
  mostrar_resultado_real(resposta.dados);
}

// Quando o HTML terminar de carregar, liga os botões do envio de verdade e abre o envio pedido no endereço, se houver.
document.addEventListener("DOMContentLoaded", preparar_envio_de_verdade);
document.addEventListener("DOMContentLoaded", retomar_envio_do_endereco);
