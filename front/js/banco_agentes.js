/*
  banco_agentes.js — a tela "Acompanhamento dos agentes" (Configuração do Portal Interno) com os dados que a aplicação
  gravou (front ligado à aplicação, ADR-69). Substitui o antigo js/banco_telemetria_ia.js, da sub-aba "Desempenho da
  IA" de Indicadores.

  Para que serve: quando a página é servida pela API, busca /api/banco/telemetria/ia no período escolhido e troca os
  exemplos do protótipo pelos dados reais. O servidor já manda só o que aconteceu de verdade: as execuções simuladas
  (a IA em MOCK) ficam de fora de todos os números, e a aceitação conta só as propostas feitas com o modelo real.
    0. o PERÍODO: as pílulas Últimos 7 dias, Últimos 30 dias (o padrão), Últimos 90 dias,
       Tudo e De/até. O período escolhido fica no endereço (?periodo=7|30|90|tudo, ou ?de=AAAA-MM-DD&ate=AAAA-MM-DD
       no De/até), e a tela pede ao servidor só o que caiu nele (?de=&ate=);
    1. um cartão por agente (cartoes_por_agente, na ordem do fluxo): o que ele faz, quantas vezes trabalhou com o
       modelo real, quantas deram certo, com erro ou barradas pelo guardrail, a duração média, a última execução, o
       custo e a ACEITAÇÃO (quantas propostas as pessoas aprovaram sem mudança, corrigiram ou recusaram, e o percentual
       das aprovadas; "não medido" com o porquê quando não há como medir). Três jeitos de um cartão aparecer:
         - o trabalho do agente ainda não é gravado nas execuções (registra_o_trabalho = false): o cartão diz isso, sem
           números (dizer que ele não trabalhou seria falso);
         - o trabalho é gravado, mas nenhuma execução com o modelo real no período: o cartão diz isso, sem números
           ("Sem execuções com o modelo real no período", ou "Ainda sem execuções com o modelo real", em Tudo);
         - o agente trabalhou com o modelo real: as contagens e os detalhes;
    2. a tabela "Custo dos agentes por etapa": por agente e etapa, as execuções, os tokens e o custo total e médio
       (ADR-131);
    3. a tabela "Execuções recentes dos agentes": quando, agente, empresa, etapa, situação e custo ("sem modelo" nas
       etapas que não usam IA, como a Regra e as decisões das pessoas).
  Os números de custo do alto (o gasto de hoje e do mês × os tetos e o custo do período) estão ocultos nesta versão
  (ADR-148): o código continua escrevendo neles, escondidos, para voltarem rápido numa evolução.
  Custo e tokens aparecem como "não medido" quando o provedor não mediu: nunca um zero inventado.
  Nenhum dado de pessoa aparece: só etapas, tempos e contagens.

  Servida pela aplicação, os exemplos nunca aparecem (js/carregando_dados.js): os blocos esperam com a barra cinza até
  os dados chegarem; se o servidor falhar, entra o aviso "Não foi possível carregar agora.", nunca o exemplo. Com a
  aba à vista, a tela se atualiza sozinha a cada minuto e ao voltar para a aba (os números acompanham o servidor sem
  recarregar a página); se uma dessas atualizações falhar, os dados de instantes atrás continuam na tela.
  Aberta como arquivo (dois cliques), a página continua com os exemplos do protótipo (as pílulas só mudam o texto).
*/

// O aviso que entra no lugar de um bloco quando o servidor não respondeu (nunca o exemplo).
const AVISO_DE_FALHA_NOS_AGENTES = "Não foi possível carregar agora.";

// O que o cartão diz quando o trabalho do agente ainda não é gravado nas execuções.
const TEXTO_DO_AGENTE_SEM_REGISTRO = "O trabalho deste agente ainda não é registrado no acompanhamento.";

// O que o cartão diz quando o agente nunca rodou com o modelo real (período "Tudo"). As execuções simuladas (MOCK) e os
// dados carregados sem o agente não contam: dizer "não trabalhou" enganaria quem viu dados prontos nas telas.
const TEXTO_DO_AGENTE_SEM_EXECUCAO_REAL = "Ainda sem execuções com o modelo real.";

// O que o cartão diz quando o agente não rodou com o modelo real dentro do período escolhido.
const TEXTO_DO_AGENTE_SEM_EXECUCAO_REAL_NO_PERIODO = "Sem execuções com o modelo real no período.";

// O custo que o provedor não mediu (nunca um zero inventado).
const TEXTO_DO_CUSTO_NAO_MEDIDO = "não medido";

// O custo de uma etapa que não usa IA (uma regra, uma decisão de pessoa): nenhum modelo foi chamado.
const TEXTO_DA_ETAPA_SEM_MODELO = "sem modelo";

// A aceitação que não tem como ser medida, ou sem nenhuma proposta decidida no período (nunca um zero inventado).
const TEXTO_DA_ACEITACAO_NAO_MEDIDA = "não medido";

// De quanto em quanto tempo a tela busca os números de novo, com a aba à vista: 60 000 milissegundos (1 minuto).
const INTERVALO_DA_ATUALIZACAO_EM_MILISSEGUNDOS = 60000;

// Quantos dias cada pílula pronta cobre, contando hoje.
const DIAS_DE_CADA_PERIODO = { "7": 7, "30": 30, "90": 90 };

// O período com que a tela abre quando o endereço não diz nenhum.
const PERIODO_PADRAO = "30";

// Os dois tipos de período que não são pílulas de dias.
const PERIODO_TUDO = "tudo";
const PERIODO_DE_ATE = "de_ate";

// Se a tela já mostra dados de verdade: uma atualização automática que falhar não troca esses dados pelo aviso.
const situacao_do_acompanhamento = { ja_mostra_dados_reais: false };

// O período que está valendo: o tipo ("7", "30", "90", "tudo" ou "de_ate") e as datas no formato do servidor
// (AAAA-MM-DD; "" = sem limite daquele lado).
const periodo_escolhido = { tipo: PERIODO_PADRAO, de: "", ate: "" };

// O número do último pedido feito ao servidor: a resposta de um pedido antigo (de outro período) é ignorada.
const pedidos_ao_servidor = { ultimo: 0 };

// ===== Pequenas ajudas de texto =====

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta (ex.: "p"); classe (ou "" para nenhuma); texto (ou "" para nenhum). Devolve: o elemento.
 * Ex.: criar_elemento_dos_agentes("h3", "cartao-agente-nome", "Interpretador").
 */
function criar_elemento_dos_agentes(etiqueta, classe, texto) {
  const elemento = document.createElement(etiqueta);
  // A classe, quando há.
  if (classe) {
    elemento.className = classe;
  }
  // O texto, quando há.
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Escreve um número inteiro no jeito brasileiro (ponto nos milhares).
 *
 * Recebe: numero. Devolve: o texto. Ex.: 1840 → "1.840".
 */
function numero_em_texto(numero) {
  return Number(numero).toLocaleString("pt-BR");
}

/**
 * Escreve uma quantidade com a palavra no singular ou no plural (português certo).
 *
 * Recebe: quantidade; singular; plural. Devolve: o texto.
 * Ex.: (1, "execução", "execuções") → "1 execução"; (3, "execução", "execuções") → "3 execuções".
 */
function quantidade_com_palavra(quantidade, singular, plural) {
  // Só o 1 leva o singular ("0 execuções", "1 execução", "2 execuções").
  if (quantidade === 1) {
    return numero_em_texto(quantidade) + " " + singular;
  }
  return numero_em_texto(quantidade) + " " + plural;
}

/**
 * Escreve um percentual no jeito brasileiro, com no máximo uma casa.
 *
 * Recebe: percentual (0 a 100). Devolve: o texto. Ex.: 90.9 → "90,9%"; 50 → "50%".
 */
function percentual_em_texto(percentual) {
  return Number(percentual).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
}

/**
 * Escreve a data e a hora completas de uma execução, no horário do computador.
 *
 * Recebe: texto — data e hora do servidor (ISO), ou null. Devolve: o texto. Ex.: "28/09/2026, 10:12"; null → "—".
 */
function data_e_hora_completas(texto) {
  // Sem data (o agente nunca rodou): um traço.
  if (!texto) {
    return "—";
  }
  const momento = new Date(texto);
  return momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }) + ", " +
    momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Escreve a duração média em segundos, com duas casas.
 *
 * Recebe: segundos, ou null. Devolve: o texto. Ex.: 0.4213 → "0,42 s"; null → "—".
 */
function duracao_em_texto(segundos) {
  // Sem duração medida: um traço.
  if (segundos === null || segundos === undefined) {
    return "—";
  }
  return Number(segundos).toFixed(2).replace(".", ",") + " s";
}

/**
 * Escreve um custo em dólar, com quatro casas; "não medido" quando o provedor não mediu.
 *
 * Recebe: custo em dólar, ou null. Devolve: o texto. Ex.: 0.0312 → "US$ 0,0312"; null → "não medido".
 */
function custo_em_texto(custo) {
  // Sem medição: diz isso, nunca um zero inventado.
  if (custo === null || custo === undefined) {
    return TEXTO_DO_CUSTO_NAO_MEDIDO;
  }
  return "US$ " + Number(custo).toFixed(4).replace(".", ",");
}

// ===== O período =====

/**
 * Escreve uma data do computador no formato que o servidor entende (AAAA-MM-DD), no dia do computador.
 *
 * Recebe: data (um Date). Devolve: o texto. Ex.: 28 de setembro de 2026 → "2026-09-28".
 */
function data_no_formato_do_servidor(data) {
  const ano = String(data.getFullYear());
  // getMonth conta os meses a partir de 0 (janeiro = 0): soma 1.
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  const dia = String(data.getDate()).padStart(2, "0");
  return ano + "-" + mes + "-" + dia;
}

/**
 * Escreve uma data do servidor (AAAA-MM-DD) no jeito brasileiro.
 *
 * Recebe: texto. Devolve: o texto. Ex.: "2026-09-28" → "28/09/2026".
 */
function data_em_texto_brasileiro(texto) {
  const partes = texto.split("-");
  return partes[2] + "/" + partes[1] + "/" + partes[0];
}

/**
 * True se o texto é uma data no formato do servidor (AAAA-MM-DD). Ex.: "2026-09-28" → true; "28/09" → false.
 */
function e_data_do_servidor(texto) {
  return /^\d{4}-\d{2}-\d{2}$/.test(texto || "");
}

/**
 * As datas de uma pílula pronta: de (dias - 1) dias atrás até hoje, no dia do computador.
 *
 * Recebe: dias (ex.: 30). Devolve: {de, ate}. Ex.: 30, hoje 28/09/2026 → {de: "2026-08-30", ate: "2026-09-28"}.
 */
function datas_dos_ultimos_dias(dias) {
  const hoje = new Date();
  const comeco = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  // Hoje conta como um dos dias: volta (dias - 1) dias.
  comeco.setDate(comeco.getDate() - (dias - 1));
  return { de: data_no_formato_do_servidor(comeco), ate: data_no_formato_do_servidor(hoje) };
}

/**
 * Troca o período que está valendo (sem buscar nada: quem chama decide).
 *
 * Recebe: tipo ("7", "30", "90", "tudo" ou "de_ate"); de e ate — as datas do De/até (ignoradas nos outros tipos).
 * Devolve: nada.
 */
function definir_periodo(tipo, de, ate) {
  periodo_escolhido.tipo = tipo;
  // Pílula de dias: as datas saem de hoje.
  if (DIAS_DE_CADA_PERIODO[tipo]) {
    const datas = datas_dos_ultimos_dias(DIAS_DE_CADA_PERIODO[tipo]);
    periodo_escolhido.de = datas.de;
    periodo_escolhido.ate = datas.ate;
    return;
  }
  // Tudo: sem limite nenhum.
  if (tipo === PERIODO_TUDO) {
    periodo_escolhido.de = "";
    periodo_escolhido.ate = "";
    return;
  }
  // De/até: as datas que a pessoa escolheu.
  periodo_escolhido.de = de;
  periodo_escolhido.ate = ate;
}

/**
 * Lê o período do endereço da página (ele fica lá para a pessoa voltar ao mesmo recorte ou mandar o link).
 *
 * Recebe: nada. Devolve: nada (preenche periodo_escolhido).
 * Ex.: "?periodo=7" → Últimos 7 dias; "?de=2026-09-01&ate=2026-09-15" → De/até; nada (ou algo estranho) → o padrão.
 */
function ler_periodo_do_endereco() {
  const parametros = new URLSearchParams(window.location.search);
  const de = parametros.get("de") || "";
  const ate = parametros.get("ate") || "";
  // De/até com as duas datas certas e na ordem.
  if (e_data_do_servidor(de) && e_data_do_servidor(ate) && de <= ate) {
    definir_periodo(PERIODO_DE_ATE, de, ate);
    return;
  }
  // Uma pílula pronta conhecida.
  const tipo = parametros.get("periodo") || "";
  if (DIAS_DE_CADA_PERIODO[tipo] || tipo === PERIODO_TUDO) {
    definir_periodo(tipo, "", "");
    return;
  }
  // Nada (ou um valor que a tela não conhece): o padrão.
  definir_periodo(PERIODO_PADRAO, "", "");
}

/**
 * Guarda o período no endereço da página, sem recarregar e sem criar uma entrada nova no "Voltar" do navegador.
 *
 * Recebe: nada. Devolve: nada. Ex.: Últimos 7 dias → "banco_agentes.html?periodo=7".
 */
function guardar_periodo_no_endereco() {
  const endereco = new URL(window.location.href);
  // Tira o período anterior, qualquer que fosse.
  endereco.searchParams.delete("periodo");
  endereco.searchParams.delete("de");
  endereco.searchParams.delete("ate");
  // De/até leva as datas; as pílulas levam o nome delas.
  if (periodo_escolhido.tipo === PERIODO_DE_ATE) {
    endereco.searchParams.set("de", periodo_escolhido.de);
    endereco.searchParams.set("ate", periodo_escolhido.ate);
  } else {
    endereco.searchParams.set("periodo", periodo_escolhido.tipo);
  }
  window.history.replaceState(null, "", endereco);
}

/**
 * O endereço da consulta ao servidor, com as datas do período (Tudo vai sem datas).
 *
 * Recebe: nada. Devolve: o texto. Ex.: "/api/banco/telemetria/ia?de=2026-08-30&ate=2026-09-28".
 */
function endereco_da_consulta() {
  const parametros = new URLSearchParams();
  // Só as datas que existem (vazio = sem limite daquele lado).
  if (periodo_escolhido.de) {
    parametros.set("de", periodo_escolhido.de);
  }
  if (periodo_escolhido.ate) {
    parametros.set("ate", periodo_escolhido.ate);
  }
  const consulta = parametros.toString();
  // Sem datas: a rota sem nada devolve tudo.
  if (!consulta) {
    return "/api/banco/telemetria/ia";
  }
  return "/api/banco/telemetria/ia?" + consulta;
}

/**
 * O período por extenso, para a linha embaixo das pílulas.
 *
 * Recebe: nada. Devolve: o texto.
 * Ex.: "Mostrando os últimos 30 dias (de 30/08/2026 a 28/09/2026): os cartões, o custo por etapa e as execuções
 * recentes."; Tudo → "Mostrando tudo o que a aplicação gravou: ...".
 */
function texto_do_periodo() {
  const o_que_muda = ": os cartões, o custo por etapa e as execuções recentes.";
  // Tudo.
  if (periodo_escolhido.tipo === PERIODO_TUDO) {
    return "Mostrando tudo o que a aplicação gravou" + o_que_muda;
  }
  const datas = "de " + data_em_texto_brasileiro(periodo_escolhido.de) + " a " +
    data_em_texto_brasileiro(periodo_escolhido.ate);
  // De/até: só as datas.
  if (periodo_escolhido.tipo === PERIODO_DE_ATE) {
    return "Mostrando " + datas + o_que_muda;
  }
  // Pílula de dias: quantos dias e as datas.
  return "Mostrando os últimos " + periodo_escolhido.tipo + " dias (" + datas + ")" + o_que_muda;
}

/**
 * Marca a pílula do período que está valendo (cor e aria-pressed), mostra as datas do De/até quando é ele, e escreve
 * o período por extenso.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_periodo_escolhido() {
  for (const pilula of document.querySelectorAll("[data-escolha-do-periodo] [data-periodo]")) {
    const escolhida = pilula.getAttribute("data-periodo") === periodo_escolhido.tipo;
    // A classe pinta a pílula; o aria-pressed conta a quem usa leitor de tela que ela está ligada.
    pilula.classList.toggle("filtro-rapido-ativo", escolhida);
    pilula.setAttribute("aria-pressed", String(escolhida));
  }
  // As datas do De/até só aparecem quando ele está escolhido.
  document.querySelector("[data-formulario-de-ate]").hidden = periodo_escolhido.tipo !== PERIODO_DE_ATE;
  document.querySelector("[data-texto-do-periodo]").textContent = texto_do_periodo();
}

/**
 * Mostra (ou esconde, com texto vazio) o aviso de data errada do De/até.
 *
 * Recebe: texto — o aviso, ou "" para esconder. Devolve: nada.
 */
function mostrar_erro_do_periodo(texto) {
  const aviso = document.querySelector("[data-erro-do-periodo]");
  aviso.textContent = texto;
  aviso.hidden = !texto;
}

/**
 * Um período novo passou a valer: guarda no endereço, mostra e busca os números dele.
 *
 * Recebe: nada. Devolve: nada.
 */
function periodo_mudou() {
  mostrar_erro_do_periodo("");
  mostrar_periodo_escolhido();
  // Aberta como arquivo: não há servidor (só o texto muda).
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  guardar_periodo_no_endereco();
  // Os números na tela são de outro período: se a busca nova falhar, o aviso entra no lugar deles.
  situacao_do_acompanhamento.ja_mostra_dados_reais = false;
  carregar_acompanhamento_dos_agentes();
}

/**
 * O clique numa pílula: as de dias e Tudo valem na hora; De/até abre as datas e espera o "Aplicar".
 *
 * Recebe: evento — o clique. Devolve: nada.
 */
function clicar_numa_pilula(evento) {
  const tipo = evento.currentTarget.getAttribute("data-periodo");
  // De/até: abre as duas datas, já com o período de agora, e põe o cursor na primeira.
  if (tipo === PERIODO_DE_ATE) {
    document.querySelector("[data-campo-de]").value = periodo_escolhido.de;
    document.querySelector("[data-campo-ate]").value = periodo_escolhido.ate;
    document.querySelector("[data-formulario-de-ate]").hidden = false;
    document.querySelector("[data-campo-de]").focus();
    return;
  }
  definir_periodo(tipo, "", "");
  periodo_mudou();
}

/**
 * O "Aplicar" do De/até: confere as duas datas e, se estiverem certas, passa a valer esse período.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
function aplicar_de_ate(evento) {
  // O formulário não recarrega a página: a tela busca os números sozinha.
  evento.preventDefault();
  const de = document.querySelector("[data-campo-de]").value;
  const ate = document.querySelector("[data-campo-ate]").value;
  // As duas datas são necessárias.
  if (!e_data_do_servidor(de) || !e_data_do_servidor(ate)) {
    mostrar_erro_do_periodo("Escolha as duas datas: de quando e até quando.");
    return;
  }
  // O começo não pode vir depois do fim (as datas AAAA-MM-DD comparam certo como texto).
  if (de > ate) {
    mostrar_erro_do_periodo("A data de começo vem depois da data de fim: confira as datas.");
    return;
  }
  definir_periodo(PERIODO_DE_ATE, de, ate);
  periodo_mudou();
}

// ===== Os cartões dos agentes =====

/**
 * O que diz o cartão do agente que não rodou com o modelo real: "Ainda sem execuções com o modelo real." em Tudo;
 * "Sem execuções com o modelo real no período." nos outros períodos (ele pode ter rodado antes do período).
 *
 * Recebe: nada. Devolve: o texto.
 */
function texto_de_quem_nao_trabalhou() {
  if (periodo_escolhido.tipo === PERIODO_TUDO) {
    return TEXTO_DO_AGENTE_SEM_EXECUCAO_REAL;
  }
  return TEXTO_DO_AGENTE_SEM_EXECUCAO_REAL_NO_PERIODO;
}

/**
 * Monta a linha do alto do cartão: o nome do agente.
 *
 * Recebe: nome. Devolve: o elemento.
 */
function montar_topo_do_cartao(nome) {
  const topo = criar_elemento_dos_agentes("div", "cartao-agente-topo", "");
  topo.append(criar_elemento_dos_agentes("h3", "cartao-agente-nome", nome));
  return topo;
}

/**
 * Monta as três contagens do agente: quantas deram certo, com erro e barradas pelo guardrail.
 *
 * Recebe: cartao. Devolve: a lista (<ul>). Ex.: "12 deram certo", "1 com erro", "0 barradas pelo guardrail".
 */
function montar_contagens_do_agente(cartao) {
  const lista = criar_elemento_dos_agentes("ul", "cartao-agente-contagens", "");
  lista.append(criar_elemento_dos_agentes("li", "selo selo-sucesso selo-pequeno",
    quantidade_com_palavra(cartao.deram_certo, "deu certo", "deram certo")));
  lista.append(criar_elemento_dos_agentes("li", "selo selo-atencao selo-pequeno",
    quantidade_com_palavra(cartao.com_erro, "com erro", "com erro")));
  lista.append(criar_elemento_dos_agentes("li", "selo selo-marca selo-pequeno",
    quantidade_com_palavra(cartao.barradas_pelo_guardrail, "barrada pelo guardrail", "barradas pelo guardrail")));
  return lista;
}

/**
 * Acrescenta uma linha de detalhe (rótulo e valor) à lista de detalhes do cartão.
 *
 * Recebe: detalhes — a lista (<dl>); rotulo; valor. Devolve: nada.
 * O custo "não medido" sai em cinza (classe celula-sem-dado), como nas tabelas.
 */
function acrescentar_detalhe(detalhes, rotulo, valor) {
  const linha = criar_elemento_dos_agentes("div", "", "");
  const valor_na_tela = criar_elemento_dos_agentes("dd", "", valor);
  // Valor que não foi medido: em cinza.
  if (valor === TEXTO_DO_CUSTO_NAO_MEDIDO) {
    valor_na_tela.className = "celula-sem-dado";
  }
  linha.append(criar_elemento_dos_agentes("dt", "", rotulo), valor_na_tela);
  detalhes.append(linha);
}

/**
 * Monta as três contagens da aceitação: aprovadas sem mudança, corrigidas e recusadas.
 *
 * Recebe: aceitacao — {aprovadas, corrigidas, recusadas, ...}. Devolve: a lista (<ul>).
 * "corrigidas" null quer dizer que o agente não tem essa situação (ex.: o material do Endomarketing não é editado):
 * aparece "corrigidas: não se aplica", nunca um zero.
 */
function montar_contagens_da_aceitacao(aceitacao) {
  const lista = criar_elemento_dos_agentes("ul", "cartao-agente-contagens", "");
  lista.append(criar_elemento_dos_agentes("li", "selo selo-sucesso selo-pequeno",
    quantidade_com_palavra(aceitacao.aprovadas, "aprovada sem mudança", "aprovadas sem mudança")));
  // Corrigidas: o número, ou "não se aplica" quando o agente não tem essa situação.
  if (aceitacao.corrigidas === null || aceitacao.corrigidas === undefined) {
    lista.append(criar_elemento_dos_agentes("li", "selo selo-neutro selo-pequeno", "corrigidas: não se aplica"));
  } else {
    lista.append(criar_elemento_dos_agentes("li", "selo selo-atencao selo-pequeno",
      quantidade_com_palavra(aceitacao.corrigidas, "corrigida", "corrigidas")));
  }
  lista.append(criar_elemento_dos_agentes("li", "selo selo-marca selo-pequeno",
    quantidade_com_palavra(aceitacao.recusadas, "recusada", "recusadas")));
  return lista;
}

/**
 * Monta o bloco da aceitação no pé do cartão: o percentual das aprovadas sem mudança, as três contagens e de onde o
 * número vem; sem medida, "não medido" e o porquê.
 *
 * Recebe: cartao — com aceitacao ({aprovadas, corrigidas, recusadas, percentual_aprovadas, fonte} ou null) e
 * aceitacao_sem_medida_porque (texto ou null). Devolve: o elemento, com data-aceitacao.
 */
function montar_aceitacao_do_agente(cartao) {
  const bloco = criar_elemento_dos_agentes("div", "cartao-agente-aceitacao", "");
  // Os roteiros de teste acham o bloco por esta marca.
  bloco.setAttribute("data-aceitacao", "");
  const topo = criar_elemento_dos_agentes("p", "cartao-agente-aceitacao-topo", "");
  topo.append(criar_elemento_dos_agentes("span", "", "Aceitação"));
  const aceitacao = cartao.aceitacao;
  // Sem medida: "não medido" em cinza e o porquê (nunca um zero inventado).
  if (!aceitacao) {
    topo.append(criar_elemento_dos_agentes("strong", "celula-sem-dado", TEXTO_DA_ACEITACAO_NAO_MEDIDA));
    bloco.append(topo);
    if (cartao.aceitacao_sem_medida_porque) {
      bloco.append(criar_elemento_dos_agentes("p", "cartao-agente-aceitacao-fonte",
        cartao.aceitacao_sem_medida_porque));
    }
    return bloco;
  }
  // Com medida: o percentual grande, a legenda, as contagens e de onde vem.
  topo.append(criar_elemento_dos_agentes("strong", "", percentual_em_texto(aceitacao.percentual_aprovadas)));
  bloco.append(topo,
    criar_elemento_dos_agentes("p", "cartao-agente-aceitacao-legenda", "das propostas aprovadas sem mudança"),
    montar_contagens_da_aceitacao(aceitacao),
    criar_elemento_dos_agentes("p", "cartao-agente-aceitacao-fonte", aceitacao.fonte));
  return bloco;
}

/**
 * Monta um cartão de agente, num dos três jeitos (sem registro, sem execução com o modelo real, ou com o trabalho),
 * sempre com a aceitação no pé.
 *
 * Recebe: cartao — um item de cartoes_por_agente ({agente, nome_na_tela, o_que_faz, registra_o_trabalho, execucoes,
 * deram_certo, com_erro, barradas_pelo_guardrail, duracao_media_s, ultima_execucao, custo_usd, aceitacao,
 * aceitacao_sem_medida_porque}; o servidor manda só as execuções com o modelo real). Devolve: o elemento <article>, com
 * data-cartao-agente.
 */
function montar_cartao_do_agente(cartao) {
  const artigo = criar_elemento_dos_agentes("article", "cartao cartao-agente", "");
  // O identificador do agente (ex.: "interpretador"): os roteiros de teste acham o cartão por ele.
  artigo.setAttribute("data-cartao-agente", cartao.agente);
  const descricao = criar_elemento_dos_agentes("p", "cartao-agente-descricao", cartao.o_que_faz);
  // 1. O trabalho deste agente ainda não é gravado: diz isso, sem números de execução.
  if (cartao.registra_o_trabalho === false) {
    artigo.append(montar_topo_do_cartao(cartao.nome_na_tela), descricao,
      criar_elemento_dos_agentes("p", "cartao-agente-sem-registro", TEXTO_DO_AGENTE_SEM_REGISTRO),
      montar_aceitacao_do_agente(cartao));
    return artigo;
  }
  // 2. É gravado, mas nenhuma execução com o modelo real no período: o aviso diz isso, sem números (nada inventado).
  if (cartao.execucoes === 0) {
    const aviso = criar_elemento_dos_agentes("p", "cartao-agente-sem-registro", texto_de_quem_nao_trabalhou());
    // Os roteiros de teste acham o aviso por esta marca.
    aviso.setAttribute("data-sem-execucao-real", "");
    artigo.append(montar_topo_do_cartao(cartao.nome_na_tela), descricao, aviso, montar_aceitacao_do_agente(cartao));
    return artigo;
  }
  // 3. Trabalhou com o modelo real: quantas vezes (o número grande), as contagens e os detalhes.
  const total = criar_elemento_dos_agentes("p", "cartao-agente-total", "");
  total.append(criar_elemento_dos_agentes("strong", "", numero_em_texto(cartao.execucoes)));
  // A palavra no singular ou no plural, sem repetir o número (o espaço separa a palavra do número).
  let palavra_do_total = " execuções";
  if (cartao.execucoes === 1) {
    palavra_do_total = " execução";
  }
  total.append(palavra_do_total);
  const detalhes = criar_elemento_dos_agentes("dl", "cartao-agente-detalhes", "");
  acrescentar_detalhe(detalhes, "Duração média", duracao_em_texto(cartao.duracao_media_s));
  acrescentar_detalhe(detalhes, "Última execução", data_e_hora_completas(cartao.ultima_execucao));
  acrescentar_detalhe(detalhes, "Custo", custo_em_texto(cartao.custo_usd));
  artigo.append(montar_topo_do_cartao(cartao.nome_na_tela), descricao, total, montar_contagens_do_agente(cartao),
    detalhes, montar_aceitacao_do_agente(cartao));
  return artigo;
}

/**
 * O resumo do alto dos cartões: quantos agentes trabalharam com o modelo real, de quantos acompanhados.
 *
 * Recebe: cartoes — a lista cartoes_por_agente. Devolve: o texto.
 * Ex. (Tudo): "Com o modelo real: 2 de 7 agentes já trabalharam"; num período: "Com o modelo real: 2 de 7 agentes
 * trabalharam no período"; nenhum: "Com o modelo real: nenhum dos 7 agentes trabalhou no período".
 */
function resumo_dos_cartoes(cartoes) {
  // Quantos agentes têm pelo menos uma execução com o modelo real.
  let agentes_que_trabalharam = 0;
  for (const cartao of cartoes) {
    if (cartao.execucoes > 0) {
      agentes_que_trabalharam = agentes_que_trabalharam + 1;
    }
  }
  const em_tudo = periodo_escolhido.tipo === PERIODO_TUDO;
  // Nenhum trabalhou.
  if (agentes_que_trabalharam === 0) {
    let quando = " no período";
    if (em_tudo) {
      quando = " ainda";
    }
    return "Com o modelo real: nenhum dos " + quantidade_com_palavra(cartoes.length, "agente", "agentes") +
      " trabalhou" + quando;
  }
  // O verbo concorda com quantos trabalharam ("1 ... trabalhou", "2 ... trabalharam").
  let verbo = "trabalharam";
  if (agentes_que_trabalharam === 1) {
    verbo = "trabalhou";
  }
  // Em Tudo: "já trabalhou"; num período: "trabalhou no período".
  let frase_do_verbo = verbo + " no período";
  if (em_tudo) {
    frase_do_verbo = "já " + verbo;
  }
  return "Com o modelo real: " + numero_em_texto(agentes_que_trabalharam) + " de " +
    quantidade_com_palavra(cartoes.length, "agente", "agentes") + " " + frase_do_verbo;
}

/**
 * Põe um recado no lugar dos cartões (ex.: o aviso de falha), ocupando a grade inteira.
 *
 * Recebe: recado — o texto. Devolve: nada.
 */
function mostrar_recado_nos_cartoes(recado) {
  document.querySelector("[data-cartoes-agentes]").replaceChildren(
    criar_elemento_dos_agentes("p", "grade-agentes-recado", recado));
}

/**
 * Troca os cartões de exemplo pelos cartões reais, na ordem que o servidor mandou (a ordem do fluxo).
 *
 * Recebe: cartoes — a lista cartoes_por_agente. Devolve: nada.
 */
function mostrar_cartoes_dos_agentes(cartoes) {
  // Nenhum agente na lista: diz isso em vez de deixar a grade vazia.
  if (cartoes.length === 0) {
    document.querySelector("[data-sobretitulo-agentes]").textContent = "Gravado pela aplicação";
    mostrar_recado_nos_cartoes("Nenhum agente para mostrar.");
    return;
  }
  document.querySelector("[data-sobretitulo-agentes]").textContent = resumo_dos_cartoes(cartoes);
  // Um cartão por agente, na ordem da lista.
  const grade = document.querySelector("[data-cartoes-agentes]");
  grade.replaceChildren();
  for (const cartao of cartoes) {
    grade.append(montar_cartao_do_agente(cartao));
  }
}

// ===== O custo do período =====

/**
 * Escreve o custo da IA no período (o 3º número do bloco "Custo e uso da IA").
 *
 * Recebe: visao — o resumo do servidor ({custo_usd: número, ou "não medido"}). Devolve: nada.
 */
function mostrar_custo_do_periodo(visao) {
  const valor = document.querySelector("[data-custo-do-periodo]");
  // Medido: em dólar, na cor normal.
  if (typeof visao.custo_usd === "number") {
    valor.textContent = custo_em_texto(visao.custo_usd);
    valor.classList.remove("celula-sem-dado");
    return;
  }
  // Nada medido no período: "não medido", em cinza (nunca um zero inventado).
  valor.textContent = TEXTO_DO_CUSTO_NAO_MEDIDO;
  valor.classList.add("celula-sem-dado");
}

// ===== O teto de gasto (dia e mês) e o custo por etapa (ADR-131) =====

/**
 * Um valor em dólar com 2 casas e vírgula. Ex.: 20 → "US$ 20,00".
 */
function dolar_com_duas_casas(valor) {
  // O número com 2 casas, trocando o ponto decimal pela vírgula do português.
  return "US$ " + Number(valor).toFixed(2).replace(".", ",");
}

/**
 * Escreve o gasto com IA de hoje e do mês, com os tetos (o 1º número do bloco "Custo e uso da IA").
 *
 * Recebe: teto — {gasto_dia_usd, teto_dia_usd, gasto_mes_usd, teto_mes_usd, atingido} do servidor, em que
 * atingido é "dia", "mes" ou null (ou nada, num servidor antigo). Devolve: nada.
 * Ex.: {gasto_dia_usd: 1.2345, teto_dia_usd: 20, gasto_mes_usd: 7.5, teto_mes_usd: 20, atingido: null} →
 * "hoje US$ 1,2345 de US$ 20,00 · no mês US$ 7,5000 de US$ 20,00".
 */
function mostrar_teto_de_gasto(teto) {
  const valor = document.querySelector("[data-teto-de-gasto]");
  const cartao = document.querySelector("[data-cartao-teto-de-gasto]");
  const legenda = document.querySelector("[data-legenda-teto-de-gasto]");
  // Sem a informação (servidor antigo): fica "não medido", em cinza.
  if (!teto || typeof teto.gasto_dia_usd !== "number") {
    valor.textContent = TEXTO_DO_CUSTO_NAO_MEDIDO;
    valor.classList.add("celula-sem-dado");
    return;
  }
  // O gasto de hoje e o do mês, cada um com o seu teto, em dólar.
  valor.textContent = "hoje " + custo_em_texto(teto.gasto_dia_usd) + " de " + dolar_com_duas_casas(teto.teto_dia_usd) +
    " · no mês " + custo_em_texto(teto.gasto_mes_usd) + " de " + dolar_com_duas_casas(teto.teto_mes_usd);
  valor.classList.remove("celula-sem-dado");
  // Atingido: o cartão chama a atenção e a legenda diz qual teto pausou a IA e até quando.
  cartao.classList.toggle("cartao-numero-atencao", Boolean(teto.atingido));
  if (teto.atingido === "dia") {
    legenda.textContent = "teto do dia atingido: os agentes estão pausados até a meia-noite (horário de " +
      "Brasília) ou até o teto ser ajustado";
  } else if (teto.atingido === "mes") {
    legenda.textContent = "teto do mês atingido: os agentes estão pausados até o dia 1º do mês que vem ou até o " +
      "teto ser ajustado";
  } else {
    legenda.textContent = "custo com agentes de hoje e do mês, somando a aplicação inteira, e os tetos " +
      "(atingido um deles, os agentes pausam e as empresas veem um aviso)";
  }
}

/**
 * Monta a tabela "Custo da IA por etapa": uma linha por agente e etapa.
 *
 * Recebe: linhas — a lista custo_por_etapa do servidor ({agente, etapa, execucoes, medidas, tokens_entrada,
 * tokens_saida, custo_usd, custo_medio_usd}). Devolve: nada. Sem linhas, um recado.
 */
function mostrar_custo_por_etapa(linhas) {
  const corpo = document.querySelector("[data-corpo-custo-por-etapa]");
  corpo.replaceChildren();
  // Nenhuma execução dos agentes com o modelo real no período: um recado ocupando as 6 colunas.
  if (!Array.isArray(linhas) || linhas.length === 0) {
    const linha_do_recado = document.createElement("tr");
    const celula_do_recado = document.createElement("td");
    celula_do_recado.colSpan = 6;
    celula_do_recado.textContent = "Nenhuma execução dos agentes com o modelo real no período.";
    linha_do_recado.append(celula_do_recado);
    corpo.append(linha_do_recado);
    return;
  }
  for (const dados of linhas) {
    // Os tokens: "pedido / resposta", ou "não medido".
    let tokens = TEXTO_DO_CUSTO_NAO_MEDIDO;
    if (dados.tokens_entrada !== null && dados.tokens_entrada !== undefined) {
      tokens = Number(dados.tokens_entrada).toLocaleString("pt-BR") + " / " +
        Number(dados.tokens_saida || 0).toLocaleString("pt-BR");
    }
    // As execuções: quantas e, se nem todas foram medidas, quantas foram (com singular e plural certos).
    let execucoes = numero_em_texto(dados.execucoes);
    if (dados.medidas !== dados.execucoes) {
      execucoes = execucoes + " (" + quantidade_com_palavra(dados.medidas, "medida", "medidas") + ")";
    }
    const linha = document.createElement("tr");
    for (const texto of [dados.agente, dados.etapa, execucoes, tokens, custo_em_texto(dados.custo_usd),
                         custo_em_texto(dados.custo_medio_usd)]) {
      const celula = document.createElement("td");
      celula.textContent = texto;
      // O que não foi medido sai em cinza, como nas outras tabelas.
      if (texto === TEXTO_DO_CUSTO_NAO_MEDIDO) {
        celula.classList.add("celula-sem-dado");
      }
      linha.append(celula);
    }
    corpo.append(linha);
  }
}

// ===== As execuções recentes =====

/**
 * Põe uma linha só na tabela das execuções, com um recado ocupando as 5 colunas.
 *
 * Recebe: recado — o texto (ex.: o aviso de falha). Devolve: nada.
 */
function mostrar_recado_nas_execucoes(recado) {
  // A linha e a célula larga do recado.
  const linha = document.createElement("tr");
  const celula = document.createElement("td");
  celula.colSpan = 5;
  celula.textContent = recado;
  linha.append(celula);
  // A tabela passa a ter só essa linha.
  document.querySelector("[data-corpo-execucoes]").replaceChildren(linha);
}

/**
 * Escreve a data e a hora de uma execução no jeito curto ("25/09, 10:12"), no horário do computador.
 *
 * Recebe: texto — data e hora do servidor. Devolve: o texto curto.
 */
function quando_curto(texto) {
  const momento = new Date(texto);
  return momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + ", " +
    momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * O custo de uma execução em texto: em dólar quando medido; "sem modelo" na etapa que não chama modelo nenhum (uma
 * regra, uma decisão de pessoa, os agentes pausados); "não medido" quando o modelo rodou, mas o provedor não mediu.
 *
 * Recebe: execucao ({modelo, custo_usd, ...}). Devolve: o texto.
 * Ex.: {modelo: "claude-sonnet-4-6", custo_usd: 0.0142} → "US$ 0,0142"; {modelo: null, custo_usd: null} → "sem modelo".
 */
function custo_da_execucao(execucao) {
  // Medido pelo provedor: em dólar.
  if (typeof execucao.custo_usd === "number") {
    return custo_em_texto(execucao.custo_usd);
  }
  // Nenhum modelo foi chamado nesta etapa: não há custo de IA para medir.
  if (!execucao.modelo) {
    return TEXTO_DA_ETAPA_SEM_MODELO;
  }
  // O modelo rodou, mas o provedor não mediu: nunca um zero inventado.
  return TEXTO_DO_CUSTO_NAO_MEDIDO;
}

/**
 * O resumo do alto da tabela: execuções, processamentos, erros e decisões humanas, com singular e plural certos.
 *
 * Recebe: visao — o resumo do servidor (só as execuções reais). Devolve: o texto.
 * Ex.: "Gravadas no período, sem as simuladas: 12 execuções em 3 envios · 1 com erro ou bloqueio · 2 decisões humanas".
 */
function resumo_das_execucoes(visao) {
  // Em Tudo, sem "no período".
  let comeco = "Gravadas no período, sem as simuladas: ";
  if (periodo_escolhido.tipo === PERIODO_TUDO) {
    comeco = "Gravadas pela aplicação, sem as simuladas: ";
  }
  return comeco + quantidade_com_palavra(visao.execucoes, "execução", "execuções") + " em " +
    quantidade_com_palavra(visao.processamentos, "envio", "envios") + " · " +
    quantidade_com_palavra(visao.com_erro_ou_bloqueio, "com erro ou bloqueio", "com erro ou bloqueio") + " · " +
    quantidade_com_palavra(visao.intervencoes_humanas, "decisão humana", "decisões humanas");
}

/**
 * Troca a tabela de exemplo pelas execuções reais, as mais recentes primeiro.
 *
 * Recebe: dados — a resposta do servidor ({visao, recentes, ...}). Devolve: nada.
 */
function mostrar_execucoes_recentes(dados) {
  document.querySelector("[data-sobretitulo-execucoes]").textContent = resumo_das_execucoes(dados.visao);
  const corpo = document.querySelector("[data-corpo-execucoes]");
  corpo.replaceChildren();
  // Uma linha por execução: quando, agente, empresa, o que fez e o custo.
  for (const execucao of dados.recentes) {
    const linha = document.createElement("tr");
    const o_que_fez = execucao.etapa + " · " + execucao.status + " · " +
      Number(execucao.duracao_s).toFixed(2).replace(".", ",") + " s";
    const valores = [quando_curto(execucao.inicio), execucao.agente, execucao.empresa, o_que_fez];
    for (const valor of valores) {
      linha.append(criar_elemento_dos_agentes("td", "", valor));
    }
    // O custo: em cinza quando não é um valor em dólar ("sem modelo" ou "não medido"), como nas outras tabelas.
    const custo = custo_da_execucao(execucao);
    let classe_do_custo = "";
    if (typeof execucao.custo_usd !== "number") {
      classe_do_custo = "celula-sem-dado";
    }
    linha.append(criar_elemento_dos_agentes("td", classe_do_custo, custo));
    corpo.append(linha);
  }
  // Nenhuma execução: diz isso em vez de deixar a tabela vazia.
  if (dados.recentes.length === 0) {
    let recado = "Nenhuma execução real gravada no período.";
    if (periodo_escolhido.tipo === PERIODO_TUDO) {
      recado = "Nenhuma execução real gravada ainda.";
    }
    mostrar_recado_nas_execucoes(recado);
  }
}

// ===== Buscar e atualizar =====

/**
 * Tira os blocos, os sobretítulos e os números de custo da espera (a barra cinza some e o que foi posto neles
 * aparece). Os números de custo do alto estão ocultos nesta versão, mas também saem da espera: nada fica esperando
 * para sempre.
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_a_tela_dos_agentes() {
  marcar_como_carregado(document.querySelector("[data-sobretitulo-agentes]"));
  marcar_como_carregado(document.querySelector("[data-cartoes-agentes]"));
  marcar_como_carregado(document.querySelector("[data-custo-do-periodo]"));
  marcar_como_carregado(document.querySelector("[data-teto-de-gasto]"));
  marcar_como_carregado(document.querySelector("[data-sobretitulo-execucoes]"));
  marcar_como_carregado(document.querySelector("[data-tabela-execucoes]"));
}

/**
 * O servidor não respondeu: sobretítulos gerais e o aviso nos blocos, nunca os exemplos.
 *
 * Recebe: nada. Devolve: nada. Se a tela já mostra dados de verdade do mesmo período (uma atualização automática
 * falhou), eles ficam: números certos de instantes atrás são melhores que um aviso.
 */
function mostrar_agentes_indisponiveis() {
  // Já há dados de verdade na tela: mantém.
  if (situacao_do_acompanhamento.ja_mostra_dados_reais) {
    return;
  }
  // Os sobretítulos de exemplo dão lugar a um texto geral.
  document.querySelector("[data-sobretitulo-agentes]").textContent = "Gravado pela aplicação";
  document.querySelector("[data-sobretitulo-execucoes]").textContent = "Gravadas pela aplicação";
  // O custo do período e o gasto × os tetos viram um traço.
  document.querySelector("[data-custo-do-periodo]").textContent = "—";
  document.querySelector("[data-teto-de-gasto]").textContent = "—";
  mostrar_recado_nos_cartoes(AVISO_DE_FALHA_NOS_AGENTES);
  mostrar_recado_nas_execucoes(AVISO_DE_FALHA_NOS_AGENTES);
  liberar_a_tela_dos_agentes();
}

/**
 * Busca os dados do período na API e troca os exemplos pelos cartões, pelo custo e pelas execuções reais.
 *
 * Recebe: nada. Devolve: nada. Aberta como arquivo, não faz nada (ficam os exemplos do protótipo).
 * Se a pessoa trocar de período enquanto a busca anda, a resposta antiga é ignorada (vale a do último pedido).
 */
async function carregar_acompanhamento_dos_agentes() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // O número deste pedido: se outro começar depois, este deixa de valer.
  pedidos_ao_servidor.ultimo = pedidos_ao_servidor.ultimo + 1;
  const numero_deste_pedido = pedidos_ao_servidor.ultimo;
  let dados = null;
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch(endereco_da_consulta());
    // Chegou depois de um pedido mais novo: ignora.
    if (numero_deste_pedido !== pedidos_ao_servidor.ultimo) {
      return;
    }
    // Recusado ou com erro: o aviso, nunca o exemplo.
    if (!resposta.ok) {
      mostrar_agentes_indisponiveis();
      return;
    }
    dados = await resposta.json();
  } catch (erro) {
    // Servidor fora do ar: o aviso, nunca o exemplo (se ainda for o pedido que vale).
    if (numero_deste_pedido === pedidos_ao_servidor.ultimo) {
      mostrar_agentes_indisponiveis();
    }
    return;
  }
  // Chegou depois de um pedido mais novo: ignora.
  if (numero_deste_pedido !== pedidos_ao_servidor.ultimo) {
    return;
  }
  // Os cartões (uma resposta sem a lista conta como nenhum agente, nunca como exemplo).
  let cartoes = [];
  if (Array.isArray(dados.cartoes_por_agente)) {
    cartoes = dados.cartoes_por_agente;
  }
  mostrar_cartoes_dos_agentes(cartoes);
  mostrar_custo_do_periodo(dados.visao);
  mostrar_teto_de_gasto(dados.teto_de_gasto);
  mostrar_custo_por_etapa(dados.custo_por_etapa);
  mostrar_execucoes_recentes(dados);
  // Os dados reais estão na tela: saem da espera.
  situacao_do_acompanhamento.ja_mostra_dados_reais = true;
  liberar_a_tela_dos_agentes();
}

/**
 * Busca os dados de novo, só se a aba do navegador estiver à vista (aba escondida não gasta o servidor).
 *
 * Recebe: nada. Devolve: nada. Numa pílula de dias, as datas andam com o relógio (ex.: virou o dia).
 */
function atualizar_se_a_aba_esta_a_vista() {
  if (document.visibilityState === "visible") {
    // As pílulas de dias contam a partir de hoje: refaz as datas antes de buscar. Só o texto do período muda: as
    // datas do De/até, se a pessoa estiver escolhendo, continuam abertas e com o que ela digitou.
    if (DIAS_DE_CADA_PERIODO[periodo_escolhido.tipo]) {
      definir_periodo(periodo_escolhido.tipo, "", "");
      document.querySelector("[data-texto-do-periodo]").textContent = texto_do_periodo();
    }
    carregar_acompanhamento_dos_agentes();
  }
}

/**
 * Liga as pílulas e o formulário do De/até.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_escolha_do_periodo() {
  for (const pilula of document.querySelectorAll("[data-escolha-do-periodo] [data-periodo]")) {
    pilula.addEventListener("click", clicar_numa_pilula);
  }
  document.querySelector("[data-formulario-de-ate]").addEventListener("submit", aplicar_de_ate);
}

/**
 * Prepara a tela: o período do endereço, as pílulas, a primeira busca, a atualização a cada minuto e a atualização
 * ao voltar para a aba.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_acompanhamento_dos_agentes() {
  ler_periodo_do_endereco();
  mostrar_periodo_escolhido();
  preparar_escolha_do_periodo();
  carregar_acompanhamento_dos_agentes();
  // Aberta como arquivo: sem servidor, não há o que atualizar.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // A cada minuto, com a aba à vista. (O endereço sem período já quer dizer o padrão, 30 dias: ele só ganha o
  // período quando a pessoa escolhe outro, e os outros roteiros continuam achando a tela por "banco_agentes.html".)
  window.setInterval(atualizar_se_a_aba_esta_a_vista, INTERVALO_DA_ATUALIZACAO_EM_MILISSEGUNDOS);
  // Ao voltar para a aba (ela estava escondida atrás de outra).
  document.addEventListener("visibilitychange", atualizar_se_a_aba_esta_a_vista);
}

// Quando o HTML terminar de carregar, troca os exemplos pelos dados reais (se houver servidor).
document.addEventListener("DOMContentLoaded", preparar_acompanhamento_dos_agentes);
