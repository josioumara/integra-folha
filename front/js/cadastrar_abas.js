/*
  cadastrar_abas.js — as duas abas do resultado da leitura, na tela "Cadastrar funcionários".

  Para que serve: depois que o agente lê o arquivo, o resultado aparece em duas abas:
    1. "Funcionários": a grade com as informações obrigatórias de cada pessoa do arquivo (as do parâmetro vigente do
       banco), como o agente leu. O clique numa pessoa abre, logo abaixo, tudo o que ele encontrou dela. É a mesma grade
       do "Conferir a lista e enviar para o banco", em Acompanhar cadastros (a linha vem do js/grade_do_parametro.js);
    2. "Como o agente leu": o que a tela já mostrava (as colunas, os detalhes da leitura, o formato das colunas e a
       conferência da lista).
  O cabeçalho do resultado, o recado das ações e os botões (aceitar, enviar, descartar) ficam fora das abas.

  Qual aba abre: antes do aceite das colunas, "Funcionários"; depois dele, "Como o agente leu" (é lá que a conferência
  resolve as pendências). A aba que a pessoa escolher fica aberta até a etapa do envio mudar. Quando o aceite volta com
  um recado sobre as colunas, a tela vai para "Como o agente leu", onde está a coluna que falta decidir.

  Os valores vêm da prévia do servidor (/api/empresa/cadastro/<envio>/previa, só leitura): a mesma padronização do
  aceite, sem gravar nada. A prévia é buscada de novo a cada leitura nova do envio (ex.: depois de dividir uma coluna).

  Usa, do js/cadastrar_real.js: envio_de_verdade, pedir_a_api, texto_do_erro, SELETOR_DAS_ESCOLHAS_DO_ACEITE,
  OPCAO_IGNORAR e OPCAO_DIVIDIR; do js/grade_do_parametro.js: colunas_obrigatorias, montar_cabecalho_da_grade e
  linha_de_pessoa_do_envio; do js/cadastrar_obrigatorios.js: colunas_do_parametro_no_cadastro.
*/

// Os nomes das duas abas (os mesmos do atributo data-aba-do-resultado, no HTML).
const ABA_DOS_FUNCIONARIOS = "funcionarios";
const ABA_DAS_COLUNAS = "colunas";
// A classe da aba aberta (css/cadastrar_abas.css).
const CLASSE_DA_ABA_ATIVA = "aba-do-resultado-ativa";
// A etapa do fluxo em que a empresa ainda confere as colunas (antes do aceite).
const ETAPA_DO_ACEITE_DAS_COLUNAS = "aprovar_mapeamento";

// O que as abas estão mostrando:
// - aba_aberta: o nome da aba à vista;
// - etapa: a etapa da última leitura do envio (quando ela muda, a aba padrão da etapa nova abre);
// - previa_desatualizada: true quando chegou uma leitura nova e a prévia ainda não foi buscada de novo;
// - pedido_da_previa: o número do último pedido da prévia (a resposta de um pedido antigo é deixada de lado).
const estado_das_abas = {
  aba_aberta: ABA_DOS_FUNCIONARIOS, etapa: undefined, previa_desatualizada: true, pedido_da_previa: 0,
};

// ===== Abrir as abas =====

/**
 * A aba que abre em cada etapa do envio: antes do aceite das colunas, "Funcionários"; depois, "Como o agente leu".
 *
 * Recebe: etapa — a etapa da leitura (ex.: "aprovar_mapeamento", "aguardar_correcao" ou null quando terminou).
 * Devolve: o nome da aba. Ex.: "aprovar_mapeamento" → "funcionarios"; "aguardar_correcao" → "colunas".
 */
function aba_padrao_da_etapa(etapa) {
  if (etapa === ETAPA_DO_ACEITE_DAS_COLUNAS) {
    return ABA_DOS_FUNCIONARIOS;
  }
  return ABA_DAS_COLUNAS;
}

/**
 * Abre uma das abas: marca o botão dela e mostra o conteúdo dela (o da outra aba fica escondido).
 *
 * Recebe: nome — ABA_DOS_FUNCIONARIOS ou ABA_DAS_COLUNAS. Devolve: nada.
 * Abrir "Funcionários" com a prévia desatualizada busca a prévia de novo; com a prévia em dia, só refaz o aviso de
 * cima dela (a pessoa pode ter trocado o campo de uma coluna na outra aba).
 */
function abrir_a_aba_do_resultado(nome) {
  estado_das_abas.aba_aberta = nome;
  for (const botao of document.querySelectorAll("[data-aba-do-resultado]")) {
    const e_a_aba_escolhida = botao.dataset.abaDoResultado === nome;
    botao.classList.toggle(CLASSE_DA_ABA_ATIVA, e_a_aba_escolhida);
    // O leitor de tela diz qual aba está aberta
    botao.setAttribute("aria-selected", String(e_a_aba_escolhida));
    // Só a aba aberta entra na ordem do Tab; as setas do teclado levam à outra (o jeito padrão das abas)
    if (e_a_aba_escolhida) {
      botao.removeAttribute("tabindex");
    } else {
      botao.setAttribute("tabindex", "-1");
    }
  }
  // O conteúdo da aba escolhida aparece; o da outra fica escondido
  for (const painel of document.querySelectorAll("[data-painel-do-resultado]")) {
    painel.hidden = painel.dataset.painelDoResultado !== nome;
  }
  // A aba dos funcionários: busca a prévia se ela ficou velha; senão, só refaz o aviso de cima da grade
  if (nome === ABA_DOS_FUNCIONARIOS && estado_das_abas.previa_desatualizada) {
    carregar_a_previa();
  } else if (nome === ABA_DOS_FUNCIONARIOS) {
    mostrar_o_aviso_da_previa();
  }
}

/**
 * Chamada a cada leitura nova do envio (js/cadastrar_real.js, no fim de mostrar_resultado_real): a prévia fica
 * desatualizada e, se a etapa mudou, abre a aba padrão da etapa nova; na mesma etapa, a aba escolhida fica.
 *
 * Recebe: leitura — o que o servidor devolveu (com a etapa). Devolve: nada.
 * Ex.: a primeira leitura, no aceite das colunas → "Funcionários"; o aceite na tela inteira, com pendências →
 * "Como o agente leu", com a conferência aberta.
 */
function mostrar_as_abas_do_resultado(leitura) {
  estado_das_abas.previa_desatualizada = true;
  // A etapa mudou (a primeira leitura, ou o aceite das colunas): a aba padrão da etapa nova
  if (leitura.etapa !== estado_das_abas.etapa) {
    estado_das_abas.etapa = leitura.etapa;
    abrir_a_aba_do_resultado(aba_padrao_da_etapa(leitura.etapa));
    return;
  }
  // A mesma etapa: a aba escolhida continua (com a prévia buscada de novo, se for a dos funcionários)
  abrir_a_aba_do_resultado(estado_das_abas.aba_aberta);
}

/**
 * As setas do teclado (e o Home e o End) passam de uma aba para a outra, como nas abas de qualquer sistema.
 *
 * Recebe: evento — a tecla apertada com o foco numa aba. Devolve: nada. Outras teclas seguem o caminho normal.
 */
function ao_apertar_uma_tecla_nas_abas(evento) {
  let nome_da_aba = null;
  // Para a esquerda (ou o começo): a primeira aba
  if (evento.key === "ArrowLeft" || evento.key === "Home") {
    nome_da_aba = ABA_DOS_FUNCIONARIOS;
  }
  // Para a direita (ou o fim): a segunda aba
  if (evento.key === "ArrowRight" || evento.key === "End") {
    nome_da_aba = ABA_DAS_COLUNAS;
  }
  if (nome_da_aba === null) {
    return;
  }
  // A tecla não rola a página: ela troca a aba, e o foco vai junto
  evento.preventDefault();
  abrir_a_aba_do_resultado(nome_da_aba);
  document.querySelector("[data-aba-do-resultado='" + nome_da_aba + "']").focus();
}

// ===== A 1ª aba: a grade dos funcionários do arquivo =====

/**
 * Escreve, em cima da grade, quantas pessoas ela tem (ou por que ela está vazia).
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_a_contagem_da_previa(texto) {
  document.querySelector("[data-real-contagem-da-previa]").textContent = texto;
}

/**
 * A frase da contagem, no singular ou no plural.
 *
 * Recebe: quantidade — quantas pessoas a grade tem. Devolve: o texto.
 * Ex.: 0 → "Nenhum funcionário encontrado no arquivo."; 1 → "1 funcionário no arquivo."; 12 → "12 funcionários no
 * arquivo.".
 */
function texto_da_contagem_da_previa(quantidade) {
  if (quantidade === 0) {
    return "Nenhum funcionário encontrado no arquivo.";
  }
  if (quantidade === 1) {
    return "1 funcionário no arquivo.";
  }
  return quantidade + " funcionários no arquivo.";
}

/**
 * Tira da grade o cabeçalho e as linhas (antes de desenhar de novo, ou quando a prévia não carregou).
 *
 * Recebe: nada. Devolve: nada.
 */
function esvaziar_a_grade_da_previa() {
  document.querySelector("[data-real-cabeca-da-previa]").replaceChildren();
  document.querySelector("[data-real-corpo-da-previa]").replaceChildren();
}

/**
 * Quantas colunas ainda esperam a escolha da empresa na aba "Como o agente leu" (o agente pediu ajuda, e a pessoa
 * ainda não escolheu o campo). Os valores delas não aparecem na grade até o aceite.
 *
 * Recebe: nada. Devolve: o número. Só conta o que a tela pergunta: a coluna em dúvida entre campos que não são
 * obrigatórios já vem em "Deixar de fora", sem pergunta (js/cadastrar_real.js).
 */
function colunas_esperando_escolha() {
  let esperando = 0;
  for (const escolha of document.querySelectorAll(SELETOR_DAS_ESCOLHAS_DO_ACEITE)) {
    // A coluna em que o agente pediu ajuda e que continua em "Escolha o campo" (valor vazio)
    if (escolha.dataset.precisaDecidir && escolha.value === "") {
      esperando = esperando + 1;
    }
  }
  return esperando;
}

/**
 * Quantas colunas a pessoa mudou na aba "Como o agente leu" de um jeito que a grade ainda não mostra: a grade é a
 * leitura do agente, e as escolhas da pessoa só valem no aceite.
 *
 * Recebe: nada. Devolve: o número.
 * Ex.: a coluna "Início", que o agente leu como admissão, trocada para nascimento → 1; a coluna em dúvida que ficou em
 * "Deixar de fora" → 0 (a grade já a deixa de fora).
 */
function colunas_mudadas_depois_da_previa() {
  let mudadas = 0;
  for (const escolha of document.querySelectorAll(SELETOR_DAS_ESCOLHAS_DO_ACEITE)) {
    const campo_escolhido = escolha.value;
    // "Dividir em vários campos" ainda não é uma escolha: a divisão só vale depois de feita
    if (campo_escolhido === OPCAO_DIVIDIR) {
      continue;
    }
    let mudou = false;
    if (escolha.dataset.original !== undefined) {
      // A coluna que o agente leu (ou deixou de fora): mudou se a pessoa trocou o campo
      mudou = campo_escolhido !== escolha.dataset.original;
    } else {
      // A coluna em dúvida: muda a grade quando a pessoa escolhe um campo (deixar de fora é o que a grade já faz)
      mudou = campo_escolhido !== "" && campo_escolhido !== OPCAO_IGNORAR;
    }
    if (mudou) {
      mudadas = mudadas + 1;
    }
  }
  return mudadas;
}

/**
 * O aviso em cima da grade, antes do aceite das colunas: as colunas que esperam a escolha da empresa e as que ela
 * mudou (a grade ainda não mostra essas mudanças). Sem nada a dizer, o aviso some.
 *
 * Recebe: nada. Devolve: nada. Depois do aceite, a grade já é a lista que vai para o banco: não há aviso.
 */
function mostrar_o_aviso_da_previa() {
  const aviso = document.querySelector("[data-real-aviso-da-previa]");
  const frases = [];
  if (estado_das_abas.etapa === ETAPA_DO_ACEITE_DAS_COLUNAS) {
    const esperando = colunas_esperando_escolha();
    const mudadas = colunas_mudadas_depois_da_previa();
    // As colunas que esperam a escolha: os valores delas ainda não estão na grade
    if (esperando === 1) {
      frases.push("1 coluna espera a sua escolha em \"Como o agente leu\": até lá, os valores dela não aparecem aqui.");
    }
    if (esperando > 1) {
      frases.push(esperando + " colunas esperam a sua escolha em \"Como o agente leu\": até lá, os valores delas não " +
        "aparecem aqui.");
    }
    // As colunas que a pessoa mudou: a grade mostra a leitura do agente até o aceite
    if (mudadas === 1) {
      frases.push("Você mudou o campo de 1 coluna em \"Como o agente leu\": a lista com a sua escolha aparece " +
        "depois de aceitar as colunas.");
    }
    if (mudadas > 1) {
      frases.push("Você mudou o campo de " + mudadas + " colunas em \"Como o agente leu\": a lista com as suas " +
        "escolhas aparece depois de aceitar as colunas.");
    }
  }
  aviso.textContent = frases.join(" ");
  aviso.hidden = frases.length === 0;
}

/**
 * A frase de cima da grade, conforme a etapa: antes do aceite, a leitura do agente; depois, a lista que vai ao banco.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_a_nota_da_previa() {
  let nota = "As informações obrigatórias de cada funcionário do arquivo, como o agente leu. Clique numa pessoa " +
    "para ver tudo o que ele encontrou dela.";
  // Depois do aceite: são os dados que vão para o banco, com as correções feitas
  if (estado_das_abas.etapa !== ETAPA_DO_ACEITE_DAS_COLUNAS) {
    nota = "As informações obrigatórias de cada funcionário, do jeito que vão para o banco. Clique numa pessoa para " +
      "ver todos os dados dela.";
  }
  document.querySelector("[data-real-nota-da-previa]").textContent = nota;
}

/**
 * Desenha a grade da 1ª aba: o cabeçalho com os campos obrigatórios do parâmetro e uma linha por pessoa. O clique na
 * pessoa abre, logo abaixo, todos os campos dela (a linha comum das pessoas de um envio, js/grade_do_parametro.js).
 *
 * Recebe: previa — {pronta, linhas} do servidor; colunas — todas as colunas do parâmetro vigente (vazia se o
 * parâmetro não respondeu). Devolve: nada.
 */
function desenhar_a_previa(previa, colunas) {
  const colunas_da_grade = colunas_obrigatorias(colunas);
  esvaziar_a_grade_da_previa();
  mostrar_a_nota_da_previa();
  mostrar_o_aviso_da_previa();
  // O agente ainda não terminou de ler as colunas: não há pessoas para mostrar
  if (!previa.pronta) {
    mostrar_a_contagem_da_previa("O agente ainda não terminou de ler as colunas deste arquivo.");
    return;
  }
  // Sem as colunas do parâmetro, a grade não tem como ser montada (nunca uma grade de exemplo)
  if (colunas_da_grade.length === 0) {
    mostrar_a_contagem_da_previa("Não foi possível carregar agora a lista das informações obrigatórias.");
    return;
  }
  // O cabeçalho: os campos obrigatórios, com o grupo em cima e a marca "*" (sem colunas próprias desta tela)
  montar_cabecalho_da_grade(document.querySelector("[data-real-cabeca-da-previa]"), colunas_da_grade, [], []);
  const corpo = document.querySelector("[data-real-corpo-da-previa]");
  for (const linha of previa.linhas) {
    corpo.append(linha_de_pessoa_do_envio(linha, colunas, colunas_da_grade));
  }
  mostrar_a_contagem_da_previa(texto_da_contagem_da_previa(previa.linhas.length));
}

/**
 * Busca a prévia do envio no servidor e desenha a grade da 1ª aba.
 *
 * Recebe: nada. Devolve: nada ("async": espera o servidor sem travar a tela).
 * Se o servidor recusar, a grade fica vazia com o motivo, e a próxima leitura (ou a volta a esta aba) tenta de novo.
 * Se outra busca começar antes desta responder, vale a mais nova.
 */
async function carregar_a_previa() {
  // Sem envio na tela, não há o que buscar
  if (envio_de_verdade === null || envio_de_verdade.id === null) {
    return;
  }
  estado_das_abas.previa_desatualizada = false;
  // O número deste pedido: se outro começar antes da resposta, esta resposta fica de lado
  estado_das_abas.pedido_da_previa = estado_das_abas.pedido_da_previa + 1;
  const numero_do_pedido = estado_das_abas.pedido_da_previa;
  mostrar_a_contagem_da_previa("Carregando os funcionários do arquivo…");
  const resposta = await pedir_a_api("/api/empresa/cadastro/" + encodeURIComponent(envio_de_verdade.id) + "/previa", {});
  // As colunas do parâmetro: a grade mostra as obrigatórias, e o detalhe de cada pessoa, todas
  const colunas = await colunas_do_parametro_no_cadastro();
  // Chegou a resposta de um pedido antigo: a do pedido mais novo é que vale
  if (numero_do_pedido !== estado_das_abas.pedido_da_previa) {
    return;
  }
  // Recusado: a grade fica vazia, com o motivo (nunca uma lista de exemplo), e a prévia volta a ficar velha
  if (!resposta.ok) {
    estado_das_abas.previa_desatualizada = true;
    esvaziar_a_grade_da_previa();
    mostrar_a_contagem_da_previa("Não foi possível mostrar os funcionários agora: " + texto_do_erro(resposta.dados.detail));
    return;
  }
  desenhar_a_previa(resposta.dados, colunas);
}

// ===== Ligar tudo =====

/**
 * Liga as abas: o clique em cada uma e as setas do teclado.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_as_abas_do_resultado() {
  for (const botao of document.querySelectorAll("[data-aba-do-resultado]")) {
    botao.addEventListener("click", function () {
      abrir_a_aba_do_resultado(botao.dataset.abaDoResultado);
    });
  }
  document.querySelector("[data-abas-do-resultado]").addEventListener("keydown", ao_apertar_uma_tecla_nas_abas);
}

// Quando o HTML terminar de carregar, liga as abas.
document.addEventListener("DOMContentLoaded", preparar_as_abas_do_resultado);
