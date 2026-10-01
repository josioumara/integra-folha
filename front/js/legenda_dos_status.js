/*
  legenda_dos_status.js — o "i" em cima de cada grade que tem a coluna "Situação".

  Para que serve: ao passar o mouse no "i", ou clicar nele, abre um balão que explica cada situação daquela grade, com
  o selo da mesma cor da grade. As explicações vêm do servidor (services/legenda_dos_status.py), pela rota do portal:
  /api/banco/legenda_dos_status ou /api/empresa/legenda_dos_status. Nenhum texto de explicação fica escrito aqui.

  Como uma tela usa: uma linha em cima da grade, e este arquivo faz o resto quando a página carrega.
    <div class="linha-do-i-dos-status" data-legenda-dos-status="funcionarios" data-portal="empresa"></div>
    - data-legenda-dos-status: qual grade (uma chave que a rota devolve: "funcionarios", "colunas", "usuarios"...);
    - data-portal: "banco" ou "empresa" (qual das duas rotas consultar).

  Como funciona para quem usa:
    - com o mouse: passar em cima abre, e sair de cima fecha; clicar deixa o balão fixo, aberto, e clicar de novo fecha;
    - no celular (toque) e no teclado (Tab até o "i", e Enter ou espaço): cada toque abre ou fecha;
    - Esc fecha e devolve o foco ao "i"; clicar fora, ou sair dele com o Tab, também fecha.
  O balão fica preso à janela ("position: fixed"), para não ser cortado pela caixa da tabela que rola por dentro, e
  acompanha o "i" quando a página rola. Só um balão fica aberto de cada vez.
  Os textos chegam na primeira abertura (uma consulta só por página, que serve a todos os "i" dela). Enquanto isso,
  aparece a barra cinza de "carregando"; com erro, "Não foi possível carregar agora." (nunca um texto de exemplo).
  Os estilos ficam em css/legenda_dos_status.css.
*/

// As duas rotas, uma por portal (só estas: o atributo da página nunca vira um endereço qualquer)
const ROTA_DA_LEGENDA_POR_PORTAL = {
  banco: "/api/banco/legenda_dos_status",
  empresa: "/api/empresa/legenda_dos_status",
};
// Os textos fixos do balão (as explicações das situações vêm do servidor)
const TITULO_DO_BALAO_DOS_STATUS = "O que quer dizer cada situação";
const NOME_DO_I_PARA_LEITOR_DE_TELA = "O que quer dizer cada situação desta lista";
const AVISO_DE_LEGENDA_INDISPONIVEL = "Não foi possível carregar agora.";
// A distância, em pixels, entre o "i" e o balão, e a margem mínima até a borda da janela
const DISTANCIA_ENTRE_O_I_E_O_BALAO = 8;
const MARGEM_ATE_A_BORDA_DA_JANELA = 16;
// Quanto tempo (em milissegundos) o balão aberto pelo mouse espera antes de fechar: dá tempo de o mouse ir do "i" ao
// balão sem que ele feche no caminho
const ESPERA_PARA_FECHAR_O_BALAO = 250;

// A consulta de cada portal, feita uma vez: a mesma promessa serve a todos os "i" da página
const consultas_das_legendas = {};
// O "i" que está com o balão aberto agora (só um de cada vez), ou null
let legenda_aberta = null;
// Um número para dar a cada balão um id próprio (o "i" aponta para ele com aria-controls)
let quantos_baloes_foram_montados = 0;

/**
 * Busca as legendas de um portal no servidor, uma vez só por página.
 *
 * Recebe: portal — "banco" ou "empresa". Devolve: uma promessa com {grade: [{texto, classe, explicacao}]}, ou com
 * null se o servidor não respondeu (a próxima abertura tenta de novo).
 */
function buscar_legendas_do_portal(portal) {
  // Já pediu antes: a mesma resposta serve
  if (consultas_das_legendas[portal]) {
    return consultas_das_legendas[portal];
  }
  // Pede ao servidor e guarda a promessa, para os outros "i" da página não pedirem de novo
  consultas_das_legendas[portal] = pedir_legendas(ROTA_DA_LEGENDA_POR_PORTAL[portal]).then(function (legendas) {
    // Sem resposta: esquece a consulta, para tentar de novo na próxima abertura
    if (legendas === null) {
      delete consultas_das_legendas[portal];
    }
    return legendas;
  });
  return consultas_das_legendas[portal];
}

/**
 * Faz o pedido a uma rota da legenda.
 *
 * Recebe: rota — o endereço. Devolve: uma promessa com o JSON da resposta, ou com null (erro, sem login, sem servidor).
 */
async function pedir_legendas(rota) {
  try {
    const resposta = await fetch(rota, { credentials: "same-origin" });
    // O servidor recusou (ex.: a sessão expirou): sem legenda
    if (!resposta.ok) {
      return null;
    }
    return await resposta.json();
  } catch (erro) {
    // Sem servidor (a página aberta como arquivo) ou sem rede: sem legenda
    return null;
  }
}

/**
 * Cria um elemento com a classe e o texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta; classe ("" = nenhuma); texto ("" = nenhum). Devolve: o elemento.
 */
function criar_elemento_da_legenda(etiqueta, classe, texto) {
  const elemento = document.createElement(etiqueta);
  // A classe, se houver
  if (classe) {
    elemento.className = classe;
  }
  // O texto, se houver
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Transforma a linha marcada na página no "i" com o balão (fechado).
 *
 * Recebe: marcador — o <div data-legenda-dos-status data-portal>. Devolve: nada.
 * O "i" e o balão ficam dentro de uma caixa do tamanho do "i", à direita da linha: é ela que sente o mouse (passar
 * na linha vazia, à esquerda, não abre nada).
 */
function montar_o_i_da_grade(marcador) {
  quantos_baloes_foram_montados = quantos_baloes_foram_montados + 1;
  const id_do_balao = "balao-dos-status-" + quantos_baloes_foram_montados;
  // A caixa do "i" com o balão
  const caixa = criar_elemento_da_legenda("span", "caixa-do-i-dos-status", "");
  // O "i": um botão (o teclado chega nele com o Tab), que diz se o balão está aberto
  const botao = criar_elemento_da_legenda("button", "botao-i-dos-status", "i");
  botao.type = "button";
  botao.setAttribute("aria-label", NOME_DO_I_PARA_LEITOR_DE_TELA);
  botao.setAttribute("aria-expanded", "false");
  botao.setAttribute("aria-controls", id_do_balao);
  botao.dataset.botaoDaLegenda = "";
  // O balão, fechado até alguém abrir
  const balao = criar_elemento_da_legenda("div", "balao-dos-status", "");
  balao.id = id_do_balao;
  balao.setAttribute("role", "region");
  balao.setAttribute("aria-label", TITULO_DO_BALAO_DOS_STATUS);
  // tabindex -1: o clique no texto do balão (ex.: para copiar) põe o foco nele, dentro da caixa, e o balão fixo não
  // fecha; o Tab não passa por ele
  balao.tabIndex = -1;
  balao.hidden = true;
  balao.dataset.balaoDaLegenda = "";
  caixa.append(botao, balao);
  marcador.append(caixa);
  // O que a página precisa lembrar deste "i"
  const legenda = {
    marcador: marcador,
    caixa: caixa,
    botao: botao,
    balao: balao,
    grade: marcador.dataset.legendaDosStatus,
    portal: marcador.dataset.portal,
    aberta: false,
    fixa: false,
    espera_para_fechar: null,
  };
  ligar_os_eventos_do_i(legenda);
}

/**
 * Liga o mouse, o clique e o teclado de um "i".
 *
 * Recebe: legenda — o que montar_o_i_da_grade guardou. Devolve: nada.
 */
function ligar_os_eventos_do_i(legenda) {
  // O mouse entrou no "i" ou no balão: abre (sem fixar) e desiste de fechar. O toque do celular não conta aqui: nele,
  // quem abre e fecha é o clique.
  legenda.caixa.addEventListener("pointerenter", function (evento) {
    if (evento.pointerType !== "mouse") {
      return;
    }
    cancelar_o_fechamento(legenda);
    if (!legenda.aberta) {
      abrir_o_balao(legenda, false);
    }
  });
  // O mouse saiu: o balão que não está fixo fecha, depois de uma pequena espera
  legenda.caixa.addEventListener("pointerleave", function (evento) {
    if (evento.pointerType !== "mouse" || legenda.fixa) {
      return;
    }
    legenda.espera_para_fechar = window.setTimeout(function () {
      fechar_o_balao(legenda);
    }, ESPERA_PARA_FECHAR_O_BALAO);
  });
  // O clique (ou o toque, ou o Enter): fecha o balão fixo; senão, deixa aberto e fixo
  legenda.botao.addEventListener("click", function () {
    if (legenda.aberta && legenda.fixa) {
      fechar_o_balao(legenda);
      return;
    }
    abrir_o_balao(legenda, true);
  });
  // O foco saiu da caixa com o Tab: fecha (quem usa o teclado não fica com um balão perdido na tela)
  legenda.caixa.addEventListener("focusout", function (evento) {
    if (legenda.aberta && !legenda.caixa.contains(evento.relatedTarget)) {
      fechar_o_balao(legenda);
    }
  });
}

/**
 * Desiste de fechar um balão que ia fechar (o mouse voltou para o "i" ou para o balão).
 *
 * Recebe: legenda. Devolve: nada.
 */
function cancelar_o_fechamento(legenda) {
  if (legenda.espera_para_fechar !== null) {
    window.clearTimeout(legenda.espera_para_fechar);
    legenda.espera_para_fechar = null;
  }
}

/**
 * Abre o balão de um "i": fecha o outro que estiver aberto, põe o balão no lugar e escreve as explicações.
 *
 * Recebe: legenda; fixar — true quando veio de um clique (o balão fica aberto mesmo com o mouse longe).
 * Devolve: nada.
 */
function abrir_o_balao(legenda, fixar) {
  cancelar_o_fechamento(legenda);
  // Só um balão aberto de cada vez
  if (legenda_aberta !== null && legenda_aberta !== legenda) {
    fechar_o_balao(legenda_aberta);
  }
  // O clique fixa o balão; o mouse em cima não tira a fixação de quem já está fixo
  if (fixar) {
    legenda.fixa = true;
  }
  // Já estava aberto: só muda a fixação
  if (legenda.aberta) {
    return;
  }
  legenda.aberta = true;
  legenda_aberta = legenda;
  legenda.botao.setAttribute("aria-expanded", "true");
  legenda.balao.hidden = false;
  // As explicações: da resposta guardada, ou a barra de "carregando" até ela chegar
  escrever_as_explicacoes(legenda);
  posicionar_o_balao(legenda);
}

/**
 * Fecha o balão de um "i".
 *
 * Recebe: legenda. Devolve: nada.
 */
function fechar_o_balao(legenda) {
  cancelar_o_fechamento(legenda);
  legenda.aberta = false;
  legenda.fixa = false;
  legenda.botao.setAttribute("aria-expanded", "false");
  legenda.balao.hidden = true;
  // Era o aberto: agora nenhum está
  if (legenda_aberta === legenda) {
    legenda_aberta = null;
  }
}

/**
 * Escreve no balão o título e as explicações da grade, pedindo ao servidor se ainda não pediu.
 *
 * Recebe: legenda. Devolve: nada (a resposta chega depois e o balão se atualiza, se continuar aberto).
 */
function escrever_as_explicacoes(legenda) {
  const titulo = criar_elemento_da_legenda("p", "balao-dos-status-titulo", TITULO_DO_BALAO_DOS_STATUS);
  // Enquanto espera: a barra cinza de "carregando" (o leitor de tela ouve "Carregando")
  const carregando = criar_elemento_da_legenda("div", "balao-dos-status-carregando", "");
  carregando.setAttribute("role", "status");
  carregando.setAttribute("aria-label", "Carregando");
  legenda.balao.replaceChildren(titulo, carregando);
  // Portal desconhecido na página: não há rota para pedir
  if (!ROTA_DA_LEGENDA_POR_PORTAL[legenda.portal]) {
    mostrar_legenda_indisponivel(legenda);
    return;
  }
  buscar_legendas_do_portal(legenda.portal).then(function (legendas) {
    // O balão fechou enquanto a resposta vinha: nada a fazer (ele escreve de novo quando abrir)
    if (!legenda.aberta) {
      return;
    }
    // Sem resposta, ou sem esta grade na resposta: o aviso, nunca um texto inventado
    if (legendas === null || !Array.isArray(legendas[legenda.grade])) {
      mostrar_legenda_indisponivel(legenda);
      return;
    }
    legenda.balao.replaceChildren(titulo, lista_das_situacoes(legendas[legenda.grade]));
    // O balão cresceu: confere que ele ainda cabe na janela
    posicionar_o_balao(legenda);
  });
}

/**
 * Troca a barra de "carregando" pelo aviso de que a legenda não veio.
 *
 * Recebe: legenda. Devolve: nada.
 */
function mostrar_legenda_indisponivel(legenda) {
  const titulo = criar_elemento_da_legenda("p", "balao-dos-status-titulo", TITULO_DO_BALAO_DOS_STATUS);
  const aviso = criar_elemento_da_legenda("p", "balao-dos-status-aviso", AVISO_DE_LEGENDA_INDISPONIVEL);
  legenda.balao.replaceChildren(titulo, aviso);
  posicionar_o_balao(legenda);
}

/**
 * A lista do balão: um item por situação, com o selo (da mesma cor da grade) e o que ele quer dizer.
 *
 * Recebe: situacoes — [{texto, classe, explicacao}]. Devolve: o <ul>.
 * Ex.: {texto: "Pendente", classe: "selo-atencao", explicacao: "Falta a empresa..."} → o selo laranja "Pendente" e,
 * embaixo, a frase.
 */
function lista_das_situacoes(situacoes) {
  const lista = criar_elemento_da_legenda("ul", "lista-do-balao-dos-status", "");
  for (const situacao of situacoes) {
    const item = criar_elemento_da_legenda("li", "item-do-balao-dos-status", "");
    const selo = criar_elemento_da_legenda("span", "selo selo-pequeno " + situacao.classe, situacao.texto);
    const explicacao = criar_elemento_da_legenda("span", "explicacao-do-balao-dos-status", situacao.explicacao);
    item.append(selo, explicacao);
    lista.append(item);
  }
  return lista;
}

/**
 * Põe o balão logo abaixo do "i", com a borda direita alinhada à dele (o "i" fica no canto direito da grade), sem
 * passar das bordas da janela. Sem espaço embaixo, o balão abre em cima do "i".
 *
 * Recebe: legenda. Devolve: nada.
 */
function posicionar_o_balao(legenda) {
  const posicao_do_i = legenda.botao.getBoundingClientRect();
  const largura_do_balao = legenda.balao.offsetWidth;
  const altura_do_balao = legenda.balao.offsetHeight;
  // A borda direita do balão na borda direita do "i"...
  let esquerda = posicao_do_i.right - largura_do_balao;
  // ...sem passar da borda direita da janela, nem da esquerda
  const esquerda_maxima = window.innerWidth - largura_do_balao - MARGEM_ATE_A_BORDA_DA_JANELA;
  esquerda = Math.max(MARGEM_ATE_A_BORDA_DA_JANELA, Math.min(esquerda, esquerda_maxima));
  // Embaixo do "i"...
  let topo = posicao_do_i.bottom + DISTANCIA_ENTRE_O_I_E_O_BALAO;
  // ...ou em cima dele, quando embaixo não cabe e em cima cabe
  const topo_em_cima = posicao_do_i.top - DISTANCIA_ENTRE_O_I_E_O_BALAO - altura_do_balao;
  const nao_cabe_embaixo = topo + altura_do_balao > window.innerHeight - MARGEM_ATE_A_BORDA_DA_JANELA;
  if (nao_cabe_embaixo && topo_em_cima >= MARGEM_ATE_A_BORDA_DA_JANELA) {
    topo = topo_em_cima;
  }
  legenda.balao.style.left = esquerda + "px";
  legenda.balao.style.top = topo + "px";
}

/**
 * A página rolou (ou a janela mudou de tamanho): o balão aberto acompanha o "i". Se o "i" saiu da tela, ou sumiu
 * junto com a parte da página em que estava, o balão fecha.
 *
 * Recebe: nada. Devolve: nada.
 */
function acompanhar_o_i_aberto() {
  if (legenda_aberta === null) {
    return;
  }
  const posicao_do_i = legenda_aberta.botao.getBoundingClientRect();
  // O "i" está escondido (a aba ou o bloco dele fechou) ou fora da janela: fecha
  const i_escondido = posicao_do_i.width === 0 && posicao_do_i.height === 0;
  const i_fora_da_janela = posicao_do_i.bottom < 0 || posicao_do_i.top > window.innerHeight;
  if (i_escondido || i_fora_da_janela) {
    fechar_o_balao(legenda_aberta);
    return;
  }
  posicionar_o_balao(legenda_aberta);
}

// ===== Os eventos da página inteira =====

// Esc fecha o balão aberto e devolve o foco ao "i" dele
document.addEventListener("keydown", function (evento) {
  if (evento.key !== "Escape" || legenda_aberta === null) {
    return;
  }
  const botao = legenda_aberta.botao;
  fechar_o_balao(legenda_aberta);
  botao.focus();
});

// Um clique fora do "i" e do balão fecha o balão aberto
document.addEventListener("click", function (evento) {
  if (legenda_aberta !== null && !legenda_aberta.caixa.contains(evento.target)) {
    fechar_o_balao(legenda_aberta);
  }
});

// A página, ou uma caixa que rola por dentro, rolou: o balão acompanha ("true" pega a rolagem das caixas também)
window.addEventListener("scroll", acompanhar_o_i_aberto, true);
// A janela mudou de tamanho (ou o celular virou): o balão acompanha
window.addEventListener("resize", acompanhar_o_i_aberto);

// Monta o "i" em cada linha marcada da página (os scripts ficam no fim da página: as linhas já existem)
for (const marcador of document.querySelectorAll("[data-legenda-dos-status]")) {
  montar_o_i_da_grade(marcador);
}
