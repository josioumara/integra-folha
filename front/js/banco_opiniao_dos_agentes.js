/*
  banco_opiniao_dos_agentes.js — a seção "O que as pessoas acham das respostas dos agentes", na tela Acompanhamento dos
  agentes do Portal Interno: a opinião das pessoas sobre os agentes de IA, pelo joinha (ADR-151; servidor em
  services/opiniao_dos_agentes.py, rota /api/banco/telemetria/opinioes).

  O que a seção mostra:
    - o resumo: os votos de todos os agentes juntos no período;
    - um cartão por agente: a satisfação (a parte dos votos com o joinha para cima), a barra da mesma parte, os votos
      para cima e para baixo, quantos votos têm comentário (só a contagem) e a linha das 12 semanas que terminam no fim
      do período, com a comparação das 4 primeiras semanas com as 4 últimas ("Subiu 12 pontos");
    - a mesma tendência numa tabela, em "Ver a tendência em tabela": a leitura sem gráfico e sem mouse.
  O período é o do alto da tela (js/banco_agentes.js, periodo_escolhido: as datas de e até): ao trocar a pílula ou
  aplicar o De/até, os números são pedidos de novo, e os cartões antigos ficam apagados até os novos chegarem (a tela
  não pula). Como o resto da tela, a seção se atualiza sozinha ao voltar para a aba e de minuto em minuto.
  A linha das semanas: a escala vai sempre de 0 a 100% (a mesma em todos os cartões, para comparar um agente com o
  outro). A semana sem voto fica sem ponto: a linha se interrompe, nunca um zero inventado. O último ponto com voto
  ganha a cor de destaque. Passar o mouse mostra a semana, a satisfação e os votos; com o gráfico em foco (Tab), as
  setas do teclado fazem o mesmo.
  Só números agregados: a rota nunca traz quem votou nem o texto dos comentários.
  Aberta como arquivo (o protótipo), a seção mostra só o aviso de que as opiniões aparecem com a aplicação ligada.
  Os nomes deste arquivo não podem repetir os dos outros scripts da página (no navegador, eles dividem os mesmos
  nomes: uma função repetida substitui a outra). O teste tests/test_opiniao_dos_agentes.py confere isso.
*/

// O que a seção lembra: os dados que chegaram, o período do último pedido e o número dele (uma resposta atrasada de um
// período antigo nunca passa por cima da mais nova)
const estado_das_opinioes = { dados: null, periodo_pedido: "", numero_do_pedido: 0 };
// De quanto em quanto tempo a seção se atualiza sozinha com a aba à vista (o mesmo ritmo do resto da tela: 1 minuto)
const INTERVALO_DAS_OPINIOES_EM_MILISSEGUNDOS = 60000;
// O aviso que entra no lugar dos cartões quando o servidor não respondeu
const AVISO_DE_OPINIOES_INDISPONIVEIS = "Não foi possível carregar agora.";
// Os elementos desta parte que esperam os dados (a barra cinza de "carregando", js/carregando_dados.js)
const SELETOR_DOS_QUE_ESPERAM_AS_OPINIOES = "[data-bloco-de='opinioes'] [data-aguarda-dado], " +
  "[data-bloco-de='opinioes'] [data-aguarda-bloco]";
// O tamanho do desenho da linha das semanas (as unidades internas do SVG; na tela, ele ocupa a largura do cartão)
const LARGURA_DA_LINHA = 240;
const ALTURA_DA_LINHA = 56;
// A folga das bordas, para o ponto de destaque (raio 4 + o anel de 2) não ser cortado
const FOLGA_DA_LINHA = 7;
// Quantas semanas a linha mostra, quantas a comparação junta em cada ponta e o mínimo de votos em cada ponta para
// comparar (as mesmas contas do servidor)
const SEMANAS_DA_TENDENCIA_NA_TELA = 12;
const SEMANAS_DA_COMPARACAO_NA_TELA = 4;
const MINIMO_DE_VOTOS_PARA_COMPARAR_NA_TELA = 5;

/**
 * Escreve uma porcentagem no jeito brasileiro, com no máximo uma casa. Ex.: 82 → "82%"; 66.7 → "66,7%".
 *
 * Recebe: valor — um número de 0 a 100. Devolve: o texto.
 */
function porcentagem_em_texto(valor) {
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
}

/**
 * Escreve uma quantidade com a palavra no singular ou no plural. Ex.: (1, "voto", "votos") → "1 voto".
 *
 * Recebe: quantidade; singular; plural. Devolve: o texto.
 */
function quantidade_em_texto(quantidade, singular, plural) {
  if (quantidade === 1) {
    return "1 " + singular;
  }
  return quantidade.toLocaleString("pt-BR") + " " + plural;
}

/**
 * O dia e o mês de uma segunda-feira do servidor. Ex.: "2026-09-21" → "21/09".
 *
 * Recebe: texto — a data ISO. Devolve: o texto curto.
 */
function dia_e_mes_da_semana(texto) {
  const partes = texto.split("-");
  return partes[2] + "/" + partes[1];
}

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro).
 *
 * Recebe: etiqueta; classe ("" = nenhuma); texto ("" = nenhum). Devolve: o elemento.
 */
function criar_elemento_das_opinioes(etiqueta, classe, texto) {
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
 * Cria um elemento de desenho (SVG) com os atributos dados.
 *
 * Recebe: etiqueta — ex.: "path"; atributos — {nome: valor}. Devolve: o elemento.
 */
function criar_desenho(etiqueta, atributos) {
  const elemento = document.createElementNS("http://www.w3.org/2000/svg", etiqueta);
  for (const nome of Object.keys(atributos)) {
    elemento.setAttribute(nome, String(atributos[nome]));
  }
  return elemento;
}

// ===== O pedido ao servidor =====

/**
 * O endereço da rota, com as datas do período do alto da tela (o "Tudo" vai sem datas).
 *
 * Recebe: nada. Devolve: o texto. Ex.: "/api/banco/telemetria/opinioes?de=2026-09-01&ate=2026-09-30".
 */
function endereco_das_opinioes() {
  const parametros = new URLSearchParams();
  // Só as datas que existem (vazio = sem limite daquele lado)
  if (periodo_escolhido.de) {
    parametros.set("de", periodo_escolhido.de);
  }
  if (periodo_escolhido.ate) {
    parametros.set("ate", periodo_escolhido.ate);
  }
  return "/api/banco/telemetria/opinioes?" + parametros.toString();
}

/**
 * Pede os números ao servidor e desenha a parte. Enquanto chegam, os cartões de antes ficam apagados.
 *
 * Recebe: nada. Devolve: uma promessa. Página aberta como arquivo: nada acontece (fica o aviso do protótipo).
 */
async function carregar_opinioes_dos_agentes() {
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // O número deste pedido: se outro sair antes de este voltar, a resposta deste é ignorada
  estado_das_opinioes.numero_do_pedido = estado_das_opinioes.numero_do_pedido + 1;
  const numero_deste_pedido = estado_das_opinioes.numero_do_pedido;
  const endereco = endereco_das_opinioes();
  estado_das_opinioes.periodo_pedido = endereco;
  const parte = document.querySelector("[data-parte-opinioes]");
  parte.classList.add("opinioes-recarregando");
  let dados = null;
  // try/catch: servidor fora do ar não quebra a tela
  try {
    const resposta = await fetch(endereco);
    if (resposta.ok) {
      dados = await resposta.json();
    }
  } catch (erro) {
    dados = null;
  }
  // Um pedido mais novo já saiu: este não desenha nada
  if (numero_deste_pedido !== estado_das_opinioes.numero_do_pedido) {
    return;
  }
  parte.classList.remove("opinioes-recarregando");
  if (dados === null) {
    mostrar_opinioes_indisponiveis();
    return;
  }
  estado_das_opinioes.dados = dados;
  desenhar_as_opinioes();
}

/**
 * O servidor não respondeu: o aviso no lugar dos cartões e do resumo (nunca números de exemplo).
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_opinioes_indisponiveis() {
  document.querySelector("[data-resumo-das-opinioes]").textContent = AVISO_DE_OPINIOES_INDISPONIVEIS;
  const aviso = criar_elemento_das_opinioes("p", "painel-vazio painel-vazio-neutro", AVISO_DE_OPINIOES_INDISPONIVEIS);
  document.querySelector("[data-cartoes-das-opinioes]").replaceChildren(aviso);
  document.querySelector("[data-cabecalho-da-tendencia]").replaceChildren();
  document.querySelector("[data-corpo-da-tendencia]").replaceChildren();
  marcar_todos_como_carregados(SELETOR_DOS_QUE_ESPERAM_AS_OPINIOES);
}

// ===== O desenho da parte =====

/**
 * Desenha o resumo, os cartões e a tabela a partir dos dados guardados.
 *
 * Recebe: nada. Devolve: nada.
 */
function desenhar_as_opinioes() {
  const dados = estado_das_opinioes.dados;
  document.querySelector("[data-resumo-das-opinioes]").textContent = texto_do_resumo(dados);
  const cartoes = [];
  for (const agente of dados.agentes) {
    cartoes.push(montar_cartao_da_opiniao(agente));
  }
  document.querySelector("[data-cartoes-das-opinioes]").replaceChildren(...cartoes);
  montar_tabela_da_tendencia(dados);
  // Tudo na tela: a barra cinza de "carregando" some
  marcar_todos_como_carregados(SELETOR_DOS_QUE_ESPERAM_AS_OPINIOES);
}

/**
 * O resumo do período, com os votos de todos os agentes juntos (o período por extenso já está no alto da tela).
 *
 * Recebe: dados — a resposta da rota. Devolve: o texto.
 * Ex.: "No período: 412 votos, 81% de joinha para cima, 38 com comentário." ou "Nenhum voto no período.".
 */
function texto_do_resumo(dados) {
  const total = dados.total;
  // Nenhum voto no período: diz isso, sem porcentagem inventada
  if (total.votos === 0) {
    return "Nenhum voto no período.";
  }
  // O comentário: "nenhum com comentário", "1 com comentário" ou "38 com comentário"
  let comentarios = total.com_comentario.toLocaleString("pt-BR") + " com comentário";
  if (total.com_comentario === 0) {
    comentarios = "nenhum com comentário";
  }
  return "No período: " + quantidade_em_texto(total.votos, "voto", "votos") + ", " +
    porcentagem_em_texto(total.satisfacao) + " de joinha para cima, " + comentarios + ".";
}

/**
 * O cartão de um agente: o nome, o que ele faz, a satisfação, a barra, os votos, a linha das semanas e a comparação.
 *
 * Recebe: agente — um item de "agentes" da rota. Devolve: o <article>.
 */
function montar_cartao_da_opiniao(agente) {
  const cartao = criar_elemento_das_opinioes("article", "cartao cartao-opiniao", "");
  cartao.dataset.cartaoOpiniao = agente.agente;
  cartao.append(criar_elemento_das_opinioes("h3", "cartao-opiniao-nome", agente.nome));
  cartao.append(criar_elemento_das_opinioes("p", "cartao-opiniao-o-que-faz", agente.o_que_faz));
  // A satisfação do período, grande; sem voto, um traço (nunca um zero inventado)
  const valor = criar_elemento_das_opinioes("div", "cartao-opiniao-valor", "—");
  valor.dataset.satisfacaoDoAgente = "";
  const legenda = criar_elemento_das_opinioes("div", "cartao-opiniao-legenda", "sem votos no período");
  if (agente.satisfacao !== null) {
    valor.textContent = porcentagem_em_texto(agente.satisfacao);
    legenda.textContent = "de joinha para cima";
  }
  cartao.append(valor, legenda, montar_barra_da_satisfacao(agente));
  cartao.append(criar_elemento_das_opinioes("p", "cartao-opiniao-votos", texto_dos_votos(agente)));
  cartao.append(montar_linha_das_semanas(agente));
  cartao.append(montar_comparacao(agente.comparacao));
  return cartao;
}

/**
 * A barra da satisfação: a parte cheia é a dos votos com o joinha para cima; o fundo, o resto.
 *
 * Recebe: agente. Devolve: o elemento (vazio, só o fundo, quando não há voto).
 */
function montar_barra_da_satisfacao(agente) {
  const barra = criar_elemento_das_opinioes("div", "barra-da-satisfacao", "");
  // Para o leitor de tela, a barra diz o número (o desenho sozinho não diz nada)
  barra.setAttribute("role", "img");
  barra.setAttribute("aria-label", "Sem votos no período");
  if (agente.satisfacao !== null) {
    const parte_cheia = criar_elemento_das_opinioes("span", "barra-da-satisfacao-parte", "");
    // A largura da parte cheia é a própria satisfação (ex.: 82% da barra)
    parte_cheia.style.width = agente.satisfacao + "%";
    barra.append(parte_cheia);
    barra.setAttribute("aria-label", porcentagem_em_texto(agente.satisfacao) + " de joinha para cima");
  }
  return barra;
}

/**
 * A linha dos votos do período. Ex.: "128 para cima · 28 para baixo · 156 votos · 12 com comentário".
 *
 * Recebe: agente. Devolve: o texto ("Nenhum voto no período." quando não há).
 */
function texto_dos_votos(agente) {
  if (agente.votos === 0) {
    return "Nenhum voto no período.";
  }
  const partes = [
    agente.para_cima.toLocaleString("pt-BR") + " para cima",
    agente.para_baixo.toLocaleString("pt-BR") + " para baixo",
    quantidade_em_texto(agente.votos, "voto", "votos"),
  ];
  // O comentário só entra quando há algum (a contagem, nunca o texto)
  if (agente.com_comentario > 0) {
    partes.push(agente.com_comentario.toLocaleString("pt-BR") + " com comentário");
  }
  return partes.join(" · ");
}

/**
 * A frase da comparação das pontas da tendência. Ex.: "▲ Subiu 12 pontos nas 12 semanas: de 74% para 86%.".
 *
 * Recebe: comparacao — {no_comeco, no_fim, diferenca, ...} do servidor (a diferença vem vazia quando falta voto numa
 * ponta ou há poucos votos nela). Devolve: o <p>, com a classe da direção (a cor nunca vem sozinha: a seta e a
 * palavra dizem o mesmo).
 */
function montar_comparacao(comparacao) {
  const frase = criar_elemento_das_opinioes("p", "comparacao-opiniao", "");
  // Falta voto numa das pontas: não há o que comparar (e a frase diz qual ponta falta)
  if (comparacao.no_comeco === null && comparacao.no_fim === null) {
    frase.textContent = "Sem votos nas " + SEMANAS_DA_TENDENCIA_NA_TELA + " semanas.";
    return frase;
  }
  if (comparacao.no_comeco === null) {
    frase.textContent = "Ainda sem votos nas " + SEMANAS_DA_COMPARACAO_NA_TELA +
      " primeiras semanas para comparar.";
    return frase;
  }
  if (comparacao.no_fim === null) {
    frase.textContent = "Sem votos nas " + SEMANAS_DA_COMPARACAO_NA_TELA + " últimas semanas para comparar.";
    return frase;
  }
  // Votos nas duas pontas, mas poucos numa delas: a diferença seria obra do acaso
  if (comparacao.diferenca === null) {
    frase.textContent = "Poucos votos para comparar: menos de " + MINIMO_DE_VOTOS_PARA_COMPARAR_NA_TELA + " nas " +
      SEMANAS_DA_COMPARACAO_NA_TELA + " primeiras ou nas " + SEMANAS_DA_COMPARACAO_NA_TELA + " últimas semanas.";
    return frase;
  }
  const de_para = ": de " + porcentagem_em_texto(comparacao.no_comeco) + " para " +
    porcentagem_em_texto(comparacao.no_fim) + ".";
  const pontos = Math.abs(comparacao.diferenca);
  const pontos_em_texto = pontos.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " ponto";
  let plural = "s";
  if (pontos === 1) {
    plural = "";
  }
  const nas_semanas = " nas " + SEMANAS_DA_TENDENCIA_NA_TELA + " semanas";
  if (comparacao.diferenca > 0) {
    frase.classList.add("comparacao-subiu");
    frase.textContent = "▲ Subiu " + pontos_em_texto + plural + nas_semanas + de_para;
  } else if (comparacao.diferenca < 0) {
    frase.classList.add("comparacao-caiu");
    frase.textContent = "▼ Caiu " + pontos_em_texto + plural + nas_semanas + de_para;
  } else {
    frase.textContent = "Igual" + nas_semanas + de_para;
  }
  return frase;
}

// ===== A linha das semanas =====

/**
 * Onde fica, no desenho, a semana de número "posicao" (0 = a mais antiga). Devolve o x, em unidades do SVG.
 *
 * Recebe: posicao; quantas — o número de semanas. Devolve: o número.
 */
function x_da_semana(posicao, quantas) {
  const passo = (LARGURA_DA_LINHA - 2 * FOLGA_DA_LINHA) / (quantas - 1);
  return FOLGA_DA_LINHA + posicao * passo;
}

/**
 * A altura, no desenho, de uma satisfação (0% embaixo, 100% em cima). Devolve o y, em unidades do SVG.
 *
 * Recebe: satisfacao — de 0 a 100. Devolve: o número.
 */
function y_da_satisfacao(satisfacao) {
  const altura_util = ALTURA_DA_LINHA - 2 * FOLGA_DA_LINHA;
  return FOLGA_DA_LINHA + (100 - satisfacao) * altura_util / 100;
}

/**
 * Os trechos da linha: cada trecho junta semanas seguidas com voto (a semana sem voto interrompe a linha).
 *
 * Recebe: tendencia — as semanas do servidor. Devolve: a lista de trechos, cada um uma lista de posições.
 * Ex.: satisfações [70, null, 80, 90] → [[0], [2, 3]].
 */
function trechos_da_linha(tendencia) {
  const trechos = [];
  let trecho_atual = [];
  for (let posicao = 0; posicao < tendencia.length; posicao = posicao + 1) {
    if (tendencia[posicao].satisfacao === null) {
      // A semana sem voto fecha o trecho que vinha antes
      if (trecho_atual.length > 0) {
        trechos.push(trecho_atual);
      }
      trecho_atual = [];
    } else {
      trecho_atual.push(posicao);
    }
  }
  if (trecho_atual.length > 0) {
    trechos.push(trecho_atual);
  }
  return trechos;
}

/**
 * A posição da última semana com voto, ou -1 quando nenhuma teve voto.
 *
 * Recebe: tendencia. Devolve: o número.
 */
function ultima_semana_com_voto(tendencia) {
  let ultima = -1;
  for (let posicao = 0; posicao < tendencia.length; posicao = posicao + 1) {
    if (tendencia[posicao].satisfacao !== null) {
      ultima = posicao;
    }
  }
  return ultima;
}

/**
 * O texto de uma semana, para a dica do mouse e para o leitor de tela.
 * Ex.: "Semana de 21/09: 86% de joinha para cima, em 14 votos." ou "Semana de 21/09: nenhum voto.".
 *
 * Recebe: semana — {semana, votos, satisfacao}. Devolve: o texto.
 */
function texto_da_semana(semana) {
  const comeco = "Semana de " + dia_e_mes_da_semana(semana.semana) + ": ";
  if (semana.satisfacao === null) {
    return comeco + "nenhum voto.";
  }
  return comeco + porcentagem_em_texto(semana.satisfacao) + " de joinha para cima, em " +
    quantidade_em_texto(semana.votos, "voto", "votos") + ".";
}

/**
 * A linha das últimas 12 semanas de um agente, com a dica que aparece ao passar o mouse (ou ao usar as setas).
 *
 * Recebe: agente. Devolve: o elemento que envolve o desenho e a dica.
 */
function montar_linha_das_semanas(agente) {
  const tendencia = agente.tendencia;
  const quantas = tendencia.length;
  const lugar = criar_elemento_das_opinioes("div", "linha-das-semanas", "");
  // Com o foco (Tab), as setas percorrem as semanas; o leitor de tela ouve a dica
  lugar.tabIndex = 0;
  lugar.setAttribute("aria-label", "Satisfação do " + agente.nome + " nas últimas " + quantas +
    " semanas. Use as setas para percorrer as semanas.");
  const desenho = criar_desenho("svg", {
    viewBox: "0 0 " + LARGURA_DA_LINHA + " " + ALTURA_DA_LINHA, class: "linha-das-semanas-desenho",
    "aria-hidden": "true", focusable: "false",
  });
  // A linha de base (0%), fina e apagada
  desenho.append(criar_desenho("line", {
    x1: FOLGA_DA_LINHA, x2: LARGURA_DA_LINHA - FOLGA_DA_LINHA, y1: y_da_satisfacao(0), y2: y_da_satisfacao(0),
    class: "linha-das-semanas-base",
  }));
  // A mira: a linha vertical que acompanha o mouse (escondida até ele chegar)
  const mira = criar_desenho("line", { x1: 0, x2: 0, y1: FOLGA_DA_LINHA, y2: y_da_satisfacao(0),
    class: "linha-das-semanas-mira" });
  mira.style.visibility = "hidden";
  desenho.append(mira);
  desenhar_os_trechos(desenho, tendencia);
  // O ponto de destaque: a última semana com voto
  const ultima = ultima_semana_com_voto(tendencia);
  if (ultima >= 0) {
    desenho.append(criar_desenho("circle", {
      cx: x_da_semana(ultima, quantas), cy: y_da_satisfacao(tendencia[ultima].satisfacao), r: 4,
      class: "linha-das-semanas-destaque",
    }));
  }
  const dica = criar_elemento_das_opinioes("div", "linha-das-semanas-dica", "");
  // O leitor de tela lê a dica quando ela muda (as setas do teclado)
  dica.setAttribute("aria-live", "polite");
  dica.hidden = true;
  lugar.append(desenho, dica);
  ligar_a_mira(lugar, desenho, mira, dica, tendencia);
  return lugar;
}

/**
 * Desenha os trechos da linha e os pontos soltos (uma semana com voto entre duas sem voto).
 *
 * Recebe: desenho — o <svg>; tendencia. Devolve: nada.
 */
function desenhar_os_trechos(desenho, tendencia) {
  const quantas = tendencia.length;
  for (const trecho of trechos_da_linha(tendencia)) {
    // Uma semana só: um ponto pequeno (uma linha precisa de dois pontos)
    if (trecho.length === 1) {
      desenho.append(criar_desenho("circle", {
        cx: x_da_semana(trecho[0], quantas), cy: y_da_satisfacao(tendencia[trecho[0]].satisfacao), r: 2.5,
        class: "linha-das-semanas-ponto",
      }));
      continue;
    }
    // Várias semanas seguidas: "M" começa o traço no primeiro ponto, "L" liga cada ponto seguinte
    let caminho = "";
    for (const posicao of trecho) {
      let comando = "L";
      if (caminho === "") {
        comando = "M";
      }
      caminho = caminho + comando + x_da_semana(posicao, quantas).toFixed(1) + " " +
        y_da_satisfacao(tendencia[posicao].satisfacao).toFixed(1) + " ";
    }
    desenho.append(criar_desenho("path", { d: caminho.trim(), class: "linha-das-semanas-traco" }));
  }
}

/**
 * Liga a mira: o mouse (ou as setas, com o foco) escolhe a semana mais perto, e a dica mostra os números dela.
 *
 * Recebe: lugar; desenho; mira; dica; tendencia. Devolve: nada.
 */
function ligar_a_mira(lugar, desenho, mira, dica, tendencia) {
  const quantas = tendencia.length;
  let semana_escolhida = quantas - 1;
  // Mostra a semana: a mira nela e a dica com os números (a dica fica sempre dentro do cartão, em cima da linha)
  function mostrar_a_semana(posicao) {
    semana_escolhida = posicao;
    const x = x_da_semana(posicao, quantas);
    mira.setAttribute("x1", String(x));
    mira.setAttribute("x2", String(x));
    mira.style.visibility = "visible";
    dica.textContent = texto_da_semana(tendencia[posicao]);
    dica.hidden = false;
  }
  // Esconde a mira e a dica
  function esconder_a_semana() {
    mira.style.visibility = "hidden";
    dica.hidden = true;
  }
  // O mouse sobre o desenho: a semana mais perto do x dele
  desenho.addEventListener("pointermove", function (evento) {
    const retangulo = desenho.getBoundingClientRect();
    const x_no_desenho = (evento.clientX - retangulo.left) * LARGURA_DA_LINHA / retangulo.width;
    const passo = (LARGURA_DA_LINHA - 2 * FOLGA_DA_LINHA) / (quantas - 1);
    let posicao = Math.round((x_no_desenho - FOLGA_DA_LINHA) / passo);
    posicao = Math.max(0, Math.min(quantas - 1, posicao));
    mostrar_a_semana(posicao);
  });
  desenho.addEventListener("pointerleave", esconder_a_semana);
  // O foco pelo teclado começa na semana de agora; as setas andam uma semana
  lugar.addEventListener("focus", function () {
    mostrar_a_semana(semana_escolhida);
  });
  lugar.addEventListener("blur", esconder_a_semana);
  lugar.addEventListener("keydown", function (evento) {
    if (evento.key === "ArrowLeft" && semana_escolhida > 0) {
      evento.preventDefault();
      mostrar_a_semana(semana_escolhida - 1);
    } else if (evento.key === "ArrowRight" && semana_escolhida < quantas - 1) {
      evento.preventDefault();
      mostrar_a_semana(semana_escolhida + 1);
    }
  });
}

// ===== A tabela da tendência =====

/**
 * A tabela das últimas 12 semanas: uma linha por semana, uma coluna por agente. Cada célula: a satisfação e os votos.
 *
 * Recebe: dados — a resposta da rota. Devolve: nada.
 */
function montar_tabela_da_tendencia(dados) {
  const cabecalho = document.createElement("tr");
  cabecalho.append(criar_elemento_das_opinioes("th", "", "Semana"));
  for (const agente of dados.agentes) {
    const titulo = criar_elemento_das_opinioes("th", "", agente.nome);
    titulo.scope = "col";
    cabecalho.append(titulo);
  }
  document.querySelector("[data-cabecalho-da-tendencia]").replaceChildren(cabecalho);
  const linhas = [];
  for (let posicao = 0; posicao < dados.semanas.length; posicao = posicao + 1) {
    const linha = document.createElement("tr");
    const semana = criar_elemento_das_opinioes("th", "", "Semana de " + dia_e_mes_da_semana(dados.semanas[posicao]));
    semana.scope = "row";
    linha.append(semana);
    for (const agente of dados.agentes) {
      linha.append(criar_elemento_das_opinioes("td", "", celula_da_semana(agente.tendencia[posicao])));
    }
    linhas.push(linha);
  }
  document.querySelector("[data-corpo-da-tendencia]").replaceChildren(...linhas);
}

/**
 * O texto de uma célula da tabela. Ex.: "86% · 14 votos"; sem voto, "—".
 *
 * Recebe: semana — {votos, satisfacao}. Devolve: o texto.
 */
function celula_da_semana(semana) {
  if (semana.satisfacao === null) {
    return "—";
  }
  return porcentagem_em_texto(semana.satisfacao) + " · " + quantidade_em_texto(semana.votos, "voto", "votos");
}

// ===== O período do alto da tela e a atualização sozinha =====

/**
 * Depois de um clique no período do alto (uma pílula ou o "Aplicar" do De/até): se o período mudou, pede os números
 * de novo.
 *
 * Recebe: nada. Devolve: nada. Por que conferir: a pílula "De/até" só abre as datas, e um "Aplicar" com a data errada
 * não muda nada; nesses casos, a seção não pede de novo.
 * O js/banco_agentes.js trata o clique antes (ele se ligou primeiro): quando esta função roda, periodo_escolhido já
 * tem o período novo.
 */
function periodo_do_alto_pode_ter_mudado() {
  if (endereco_das_opinioes() !== estado_das_opinioes.periodo_pedido) {
    carregar_opinioes_dos_agentes();
  }
}

/**
 * A atualização sozinha: com a aba à vista, pede os números de novo (os votos novos aparecem sem recarregar a página).
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_as_opinioes_se_a_aba_esta_a_vista() {
  if (document.visibilityState === "visible") {
    carregar_opinioes_dos_agentes();
  }
}

/**
 * Liga a seção ao período do alto e à atualização sozinha, e pede os números da primeira vez.
 *
 * Recebe: nada. Devolve: nada. Roda quando a página termina de carregar, depois do js/banco_agentes.js (que já leu o
 * período do endereço).
 */
function preparar_opinioes_dos_agentes() {
  // As pílulas do período e o "Aplicar" do De/até, os mesmos do resto da tela
  for (const pilula of document.querySelectorAll("[data-escolha-do-periodo] [data-periodo]")) {
    pilula.addEventListener("click", periodo_do_alto_pode_ter_mudado);
  }
  document.querySelector("[data-formulario-de-ate]").addEventListener("submit", periodo_do_alto_pode_ter_mudado);
  // Ao voltar para a aba e de minuto em minuto, com a aba à vista
  document.addEventListener("visibilitychange", atualizar_as_opinioes_se_a_aba_esta_a_vista);
  window.setInterval(atualizar_as_opinioes_se_a_aba_esta_a_vista, INTERVALO_DAS_OPINIOES_EM_MILISSEGUNDOS);
  carregar_opinioes_dos_agentes();
}

// Quando o HTML terminar de carregar, liga a seção e pede os números (depois do js/banco_agentes.js)
document.addEventListener("DOMContentLoaded", preparar_opinioes_dos_agentes);
