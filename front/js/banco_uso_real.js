/*
  banco_uso_real.js — a parte "uso das empresas" do Painel de acompanhamento (aba Indicadores) com os dados reais da
  aplicação (ADR-69).

  Para que serve: quando a página é servida pela API, troca o uso de exemplo (js/banco_uso.js) pelo que a
  aplicação grava de verdade (/api/banco/telemetria/uso):
    - acessos e último acesso: as entradas no portal (cada login cria uma sessão);
    - funil: os eventos da auditoria de cada envio (arquivo recebido → IA leu → colunas conferidas → cadastrado);
    - linha do tempo: os mesmos eventos, em ordem, com a data e a hora;
    - tempo até a avaliação do banco: a média, em dias úteis (segunda a sexta), entre o envio da empresa ao banco e a
      decisão do banco (aprovar ou devolver), só dos envios já decididos; o servidor faz a conta
      (services/portal_do_banco.py, tempo_ate_a_avaliacao) e esta tela só escreve o número ("1,3");
    - os CNPJs e a UF da sede de cada empresa, para o filtro do alto do painel (js/filtro_dos_indicadores.js):
      com uma empresa ou um estado escolhido, os quatro números do alto são refeitos só com as empresas do filtro
      (o tempo até a avaliação junta as empresas pela média ponderada: soma dos dias ÷ soma das avaliações).
  Só o uso do portal pelo RH: nenhum funcionário aparece aqui.
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout.
  Servida pela aplicação, o exemplo nunca aparece (js/carregando_dados.js): os números e as listas esperam com a barra
  cinza até o uso real chegar; se o servidor falhar, entra um traço ("—") nos números e o aviso "Não foi possível
  carregar agora." nas listas, nunca o exemplo.
  No painel, o uso divide a tela com o planejamento (js/banco_planejamento.js): cada bloco diz de quem é o dado
  (data-bloco-de="uso" ou "planejamento"), e este arquivo só libera os blocos do uso.

  O que o layout mostra e a aplicação ainda não grava: "abriu a tela de cadastro" (a primeira etapa do funil do
  exemplo) e a pista do motivo. Por isso, no modo real, o funil começa em "Mandaram um arquivo" e a pista não aparece.
*/

/**
 * Escreve a data e a hora no jeito curto ("24/09, 10:12"), no horário do computador.
 *
 * Recebe: texto — data e hora do servidor (ex.: "2026-09-24T13:12:00+00:00"), ou null.
 * Devolve: o texto curto, ou "Nunca entrou" se não houver data.
 */
function data_curta_do_uso(texto) {
  // Sem data: a empresa ainda não entrou no portal.
  if (!texto) {
    return "Nunca entrou";
  }
  // O navegador converte do horário universal para o horário do computador.
  const momento = new Date(texto);
  const dia_e_mes = momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const hora = momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return dia_e_mes + ", " + hora;
}

/**
 * O texto do motivo de uma empresa, pelos descartes (o único motivo que a aplicação já registra).
 *
 * Recebe: empresa — os dados reais da empresa. Devolve: o texto (vazio se não houve descarte).
 * Exemplo: descartes 2 → "2 leituras descartadas pela empresa."
 */
function motivo_real(empresa) {
  // Sem descarte: nada a explicar.
  if (empresa.descartes === 0) {
    return "";
  }
  // Uma leitura só: singular.
  if (empresa.descartes === 1) {
    return "1 leitura descartada pela empresa.";
  }
  // Mais de uma: plural.
  return empresa.descartes + " leituras descartadas pela empresa.";
}

/**
 * Converte a empresa da API para o formato que o js/banco_uso.js desenha.
 *
 * Recebe: empresa — {id, nome, cnpjs, ultimo_acesso, acessos, envios, descartes, onde_parou, funil, linha_do_tempo}.
 * Devolve: o objeto no formato de USO_DAS_EMPRESAS.
 */
function uso_no_formato_da_tela(empresa) {
  // Cada acontecimento vira uma linha de texto: "24/09, 10:12 · mandou um arquivo".
  const linha_do_tempo = [];
  for (const acontecimento of empresa.linha_do_tempo) {
    linha_do_tempo.push(data_curta_do_uso(acontecimento.quando) + " · " + acontecimento.o_que);
  }
  // Empresa sem nenhum acontecimento: diz isso em vez de deixar a lista vazia.
  if (linha_do_tempo.length === 0) {
    linha_do_tempo.push("Nenhum arquivo enviado até agora.");
  }
  // O formato da tela (a pista do motivo ainda não existe na aplicação).
  return {
    nome: empresa.nome,
    // Todos os CNPJs da empresa, só com os números, e a UF da sede (o filtro do alto procura e filtra por eles).
    cnpjs: empresa.cnpjs,
    uf: empresa.uf,
    ultimo_acesso: data_curta_do_uso(empresa.ultimo_acesso),
    acessos: empresa.acessos,
    envios: empresa.envios,
    descartes: empresa.descartes,
    onde_parou: empresa.onde_parou,
    funil: empresa.funil,
    motivo: motivo_real(empresa),
    linha_do_tempo: linha_do_tempo,
    pista: "",
  };
}

/**
 * Preenche o subtítulo e os três primeiros cartões do topo com os números reais da carteira.
 *
 * Recebe: empresas — as da API que entram no filtro do alto. Devolve: nada.
 * O quarto cartão (tempo até a avaliação do banco) é preenchido por mostrar_tempo_ate_a_avaliacao.
 */
function mostrar_cartoes_reais(empresas) {
  // Soma a carteira: empresas que já entraram, envios e descartes.
  let empresas_que_entraram = 0;
  let envios = 0;
  let descartes = 0;
  for (const empresa of empresas) {
    // Empresa com pelo menos uma entrada no portal.
    if (empresa.acessos > 0) {
      empresas_que_entraram = empresas_que_entraram + 1;
    }
    envios = envios + empresa.envios;
    descartes = descartes + empresa.descartes;
  }
  // Subtítulo: os números valem desde o começo (não só o mês), para as empresas do filtro do alto.
  document.querySelector("[data-uso-subtitulo]").textContent = "Quem entra, quando, quantos envios faz e onde trava. Desde o começo." +
    texto_do_filtro_no_uso();
  // Primeiro cartão: "3 de 6" (o "de 6" menor, como no layout).
  const total = document.createElement("span");
  total.className = "cartao-numero-total";
  total.textContent = "de " + empresas.length;
  document.querySelector("[data-uso-entraram-valor]").replaceChildren(String(empresas_que_entraram) + " ", total);
  document.querySelector("[data-uso-entraram-legenda]").textContent = "empresas já entraram no portal";
  // Segundo e terceiro cartões: envios e descartes.
  document.querySelector("[data-uso-envios-valor]").textContent = String(envios);
  document.querySelector("[data-uso-envios-legenda]").textContent = "arquivos enviados pelas empresas";
  document.querySelector("[data-uso-descartes-valor]").textContent = String(descartes);
}

/**
 * Preenche o quarto cartão: o tempo, em dias úteis, do envio da empresa ao banco até a decisão do banco.
 *
 * Recebe: tempo — {media_em_dias_uteis (ex.: 1.3, ou null), avaliacoes (quantas decisões), periodo (ex.: "desde o
 * começo")}, já calculado pelo servidor. Devolve: nada.
 * Exemplo: {media_em_dias_uteis: 1.3, avaliacoes: 3} → "1,3" e "dia útil, em média, do envio à decisão do banco
 * (aprovar ou devolver), em 3 avaliações desde o começo. Só segunda a sexta; feriados ainda contam."
 */
function mostrar_tempo_ate_a_avaliacao(tempo) {
  const valor = document.querySelector("[data-uso-tempo-valor]");
  const legenda = document.querySelector("[data-uso-tempo-legenda]");
  // Nenhum envio decidido pelo banco no período: sem número (nunca um zero inventado).
  if (tempo.media_em_dias_uteis === null) {
    valor.textContent = "—";
    legenda.textContent = "tempo até a avaliação do banco: ainda não há envio avaliado pelo banco no período (" +
      tempo.periodo + ")";
    return;
  }
  // O número com uma casa decimal, no jeito brasileiro ("1,3").
  valor.textContent = tempo.media_em_dias_uteis.toLocaleString("pt-BR",
    { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  // Menos de 2 fica no singular ("1,3 dia útil"); de 2 em diante, no plural ("2,5 dias úteis").
  let unidade = "dia útil";
  if (tempo.media_em_dias_uteis >= 2) {
    unidade = "dias úteis";
  }
  // Uma avaliação ou várias.
  let avaliacoes = tempo.avaliacoes + " avaliações";
  if (tempo.avaliacoes === 1) {
    avaliacoes = "1 avaliação";
  }
  legenda.textContent = unidade + ", em média, do envio à decisão do banco (aprovar ou devolver), em " + avaliacoes +
    " " + tempo.periodo + ". Só segunda a sexta; feriados ainda contam.";
}

/**
 * O pedaço do subtítulo que diz o filtro do alto (vazio sem filtro).
 *
 * Recebe: nada. Devolve: ex.: " Empresa: Aurora Alimentos." ou " Estado da sede: SP.".
 */
function texto_do_filtro_no_uso() {
  if (filtro_dos_indicadores.empresa_id && USO_DAS_EMPRESAS[filtro_dos_indicadores.empresa_id]) {
    return " Empresa: " + USO_DAS_EMPRESAS[filtro_dos_indicadores.empresa_id].nome + ".";
  }
  if (filtro_dos_indicadores.uf) {
    return " Estado da sede: " + filtro_dos_indicadores.uf + ".";
  }
  return "";
}

/**
 * Junta o tempo até a avaliação de várias empresas pela média ponderada (cada avaliação pesa igual).
 *
 * Recebe: empresas — as da API do filtro, cada uma com tempo_ate_a_avaliacao {avaliacoes, soma_em_dias_uteis}.
 * Devolve: {media_em_dias_uteis (ou null), avaliacoes, periodo}, no formato de mostrar_tempo_ate_a_avaliacao.
 * Exemplo: 2 avaliações somando 3 dias e 1 somando 1 dia → 4 ÷ 3 = 1,3.
 */
function tempo_juntado(empresas) {
  let avaliacoes = 0;
  let soma_dos_dias = 0;
  for (const empresa of empresas) {
    avaliacoes = avaliacoes + empresa.tempo_ate_a_avaliacao.avaliacoes;
    soma_dos_dias = soma_dos_dias + empresa.tempo_ate_a_avaliacao.soma_em_dias_uteis;
  }
  // Nenhuma decisão do banco nas empresas do filtro: sem número (nunca um zero inventado).
  if (avaliacoes === 0) {
    return { media_em_dias_uteis: null, avaliacoes: 0, periodo: "desde o começo" };
  }
  // Uma casa decimal, como o servidor ("1,3").
  const media = Math.round((soma_dos_dias / avaliacoes) * 10) / 10;
  return { media_em_dias_uteis: media, avaliacoes: avaliacoes, periodo: "desde o começo" };
}

// As empresas como a API mandou (com o tempo e a UF): o filtro do alto refaz os números a partir delas.
const EMPRESAS_REAIS_DO_USO = [];

/**
 * Refaz os quatro números do alto só com as empresas do filtro do alto.
 *
 * Recebe: nada. Devolve: nada. Sem o uso real (protótipo ou servidor fora), não faz nada.
 */
function mostrar_numeros_do_uso_no_filtro() {
  if (EMPRESAS_REAIS_DO_USO.length === 0) {
    return;
  }
  // As empresas do filtro, pelos ids que o js/banco_uso.js escolhe (a mesma regra do funil e da tabela).
  const ids = empresas_do_uso_no_filtro();
  const do_filtro = [];
  for (const empresa of EMPRESAS_REAIS_DO_USO) {
    if (ids.includes(empresa.id)) {
      do_filtro.push(empresa);
    }
  }
  mostrar_cartoes_reais(do_filtro);
  mostrar_tempo_ate_a_avaliacao(tempo_juntado(do_filtro));
}

// O aviso que entra no lugar de uma lista quando o servidor não respondeu (nunca o exemplo).
const AVISO_DE_FALHA_NO_USO = "Não foi possível carregar agora.";

// Os elementos dos blocos do uso que esperam os dados (marcados no HTML com data-aguarda-dado ou data-aguarda-bloco).
// O painel também tem blocos do planejamento, que o js/banco_planejamento.js libera.
const SELETOR_DOS_QUE_ESPERAM_O_USO = "[data-bloco-de='uso'] [data-aguarda-dado], " +
  "[data-bloco-de='uso'] [data-aguarda-bloco]";

/**
 * O servidor não respondeu: tira todo o exemplo dos blocos do uso e põe traços e avisos no lugar.
 *
 * Recebe: nada. Devolve: nada. Os cartões ficam com "—", as legendas com o texto geral (sem número de exemplo),
 * o funil, a linha do tempo e a tabela com o aviso; as empresas de exemplo saem (o filtro não as desenha).
 */
function mostrar_uso_indisponivel() {
  // Subtítulo sem o mês de exemplo.
  document.querySelector("[data-uso-subtitulo]").textContent = "Quem entra, quando, quantos envios faz e onde trava.";
  // Os quatro números viram traço.
  for (const seletor of ["[data-uso-entraram-valor]", "[data-uso-envios-valor]", "[data-uso-descartes-valor]",
    "[data-uso-tempo-valor]"]) {
    mostrar_dado_indisponivel(document.querySelector(seletor));
  }
  // As legendas perdem o período de exemplo ("nos últimos 7 dias", "no mês").
  document.querySelector("[data-uso-entraram-legenda]").textContent = "empresas já entraram no portal";
  document.querySelector("[data-uso-envios-legenda]").textContent = "arquivos enviados pelas empresas";
  document.querySelector("[data-uso-tempo-legenda]").textContent = "tempo até a avaliação do banco";
  // O funil e a linha do tempo: só o aviso.
  document.querySelector("[data-funil]").replaceChildren(criar_item_da_linha(AVISO_DE_FALHA_NO_USO));
  document.querySelector("[data-linha-do-tempo]").replaceChildren(criar_item_da_linha(AVISO_DE_FALHA_NO_USO));
  // Sem a maior perda, sem o título da empresa, sem a pista e sem o link da ficha.
  document.querySelector("[data-maior-perda]").textContent = "";
  document.querySelector("[data-titulo-linha-do-tempo]").textContent = "Linha do tempo";
  document.querySelector("[data-pista-motivo]").hidden = true;
  document.querySelector("[data-link-ficha]").hidden = true;
  // A tabela: uma linha só, com o aviso ocupando as 6 colunas.
  const linha_do_aviso = document.createElement("tr");
  const celula_do_aviso = document.createElement("td");
  celula_do_aviso.colSpan = 6;
  celula_do_aviso.textContent = AVISO_DE_FALHA_NO_USO;
  linha_do_aviso.append(celula_do_aviso);
  document.querySelector("[data-corpo-uso]").replaceChildren(linha_do_aviso);
  document.querySelector("#titulo-tabela-uso").textContent = "Acessos e envios";
  // Sem o uso real, o filtro do alto não redesenha o uso (desenharia o exemplo): as empresas de exemplo saem.
  for (const id of Object.keys(USO_DAS_EMPRESAS)) {
    delete USO_DAS_EMPRESAS[id];
  }
  ORDEM_DAS_EMPRESAS.length = 0;
  // Tudo sai da espera: aparecem os traços e os avisos.
  marcar_todos_como_carregados(SELETOR_DOS_QUE_ESPERAM_O_USO);
}

/**
 * Busca o uso real na API e troca o exemplo da tela por ele.
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: fica o exemplo. Servidor fora do ar: traços e avisos.
 */
async function carregar_uso_de_verdade() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // try/catch: servidor fora do ar não quebra a tela.
  let dados = null;
  try {
    const resposta = await fetch("/api/banco/telemetria/uso");
    // Recusado ou com erro: traços e avisos, nunca o exemplo.
    if (!resposta.ok) {
      mostrar_uso_indisponivel();
      return;
    }
    dados = await resposta.json();
  } catch (erro) {
    // Servidor fora do ar: traços e avisos, nunca o exemplo.
    mostrar_uso_indisponivel();
    return;
  }
  // Troca as etapas do funil pelas que a aplicação registra (esvazia a lista e põe as novas).
  ETAPAS_DO_FUNIL.length = 0;
  for (const etapa of dados.etapas) {
    ETAPAS_DO_FUNIL.push(etapa);
  }
  // Troca o uso de exemplo pelo real: primeiro apaga as empresas de exemplo.
  for (const id of Object.keys(USO_DAS_EMPRESAS)) {
    delete USO_DAS_EMPRESAS[id];
  }
  // A carteira toda: o funil somado de todas as empresas.
  USO_DAS_EMPRESAS["carteira"] = {
    nome: "Carteira toda",
    funil: dados.carteira.funil,
    motivo: "Cada envio conta uma vez em cada etapa.",
    linha_do_tempo: [],
    pista: "",
  };
  // As empresas, na ordem da carteira.
  ORDEM_DAS_EMPRESAS.length = 0;
  for (const empresa of dados.empresas) {
    USO_DAS_EMPRESAS[empresa.id] = uso_no_formato_da_tela(empresa);
    ORDEM_DAS_EMPRESAS.push(empresa.id);
  }
  // As empresas como vieram (com o tempo e a UF), para refazer os números a cada filtro.
  EMPRESAS_REAIS_DO_USO.length = 0;
  for (const empresa of dados.empresas) {
    EMPRESAS_REAIS_DO_USO.push(empresa);
  }
  // As empresas vão para o filtro do alto e para o simulador (nome, CNPJs e UF da sede).
  registrar_empresas_para_escolher(dados.empresas);
  document.querySelector("#titulo-tabela-uso").textContent = "Acessos e envios desde o começo";
  // Os quatro números, o funil, a linha do tempo e a tabela, com o filtro do alto (ex.: ?empresa=EMP002 do Início).
  mostrar_numeros_do_uso_no_filtro();
  aplicar_filtro_no_uso();
  // O uso real está na tela: tudo sai da espera (a barra cinza some e os dados aparecem).
  marcar_todos_como_carregados(SELETOR_DOS_QUE_ESPERAM_O_USO);
}

// Quando o HTML terminar de carregar, troca o exemplo pelos dados reais (se houver servidor).
document.addEventListener("DOMContentLoaded", carregar_uso_de_verdade);
// O filtro do alto mudou: os quatro números do alto também (o funil, a linha e a tabela são do js/banco_uso.js).
document.addEventListener("filtro-dos-indicadores-mudou", mostrar_numeros_do_uso_no_filtro);
