/*
  beneficios_real.js — a aba "Benefícios do seu time" com o catálogo REAL da empresa de quem entrou (ADR-69).

  Para que serve: quando a página é servida pela API, troca o exemplo da Aurora pelo catálogo que o banco definiu
  para a empresa (/api/empresa/beneficios):
    - os cartões: um por seção do catálogo que é benefício (js/beneficios_do_catalogo.js);
    - o quadro de dúvidas: o que o catálogo diz, seção por seção, com a fonte;
    - o quadro de atendimento: as seções "Onde consultar" e "Canais de dúvidas", linha por linha.
  Os filtros por categoria mostram só as categorias que o catálogo da empresa usa; a busca continua.

  O exemplo nunca aparece com servidor: o que o HTML marca com data-aguarda-dado
  e data-aguarda-bloco fica como barra cinza (js/carregando_dados.js) até o catálogo chegar. Se o servidor falhar,
  entra um aviso ("Não foi possível carregar agora."), nunca o exemplo da Aurora.
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout.
*/

// O recado curto no lugar de uma lista que não pôde ser carregada.
const RECADO_SEM_CATALOGO = "Não foi possível carregar agora.";

/**
 * Diz se a página está ligada à aplicação.
 *
 * Recebe: nada. Devolve: true (servida pela aplicação) ou false (aberta como arquivo, com dois cliques).
 * Exemplo: "http://127.0.0.1:8000/beneficios.html" → true; "file:///D:/.../beneficios.html" → false.
 */
function beneficios_com_servidor() {
  // Servida pela aplicação, o endereço começa com "http" (ou "https").
  return window.location.protocol.startsWith("http");
}

/**
 * Tira do quadro de dúvidas as perguntas que estão nele (as de exemplo do HTML, ou as de uma tentativa anterior).
 *
 * Recebe: quadro — o cartão das dúvidas. Devolve: nada.
 */
function tirar_perguntas_do_quadro(quadro) {
  // Cada pergunta é um <details> que abre e fecha.
  for (const pergunta of quadro.querySelectorAll("details.pergunta-frequente")) {
    pergunta.remove();
  }
}

/**
 * Tira do quadro de atendimento os canais que estão nele (os de exemplo do HTML, ou os de uma tentativa anterior).
 *
 * Recebe: quadro — o cartão do atendimento. Devolve: nada.
 */
function tirar_canais_do_quadro(quadro) {
  // Cada canal é uma linha com ícone, nome e contato.
  for (const canal of quadro.querySelectorAll(".canal-atendimento")) {
    canal.remove();
  }
}

/**
 * Monta a pergunta de uma seção do catálogo: o título (que abre e fecha), o texto e a fonte.
 *
 * Recebe: secao — {titulo, texto, documento, versao}. Devolve: o <details> pronto.
 * Exemplo de fonte: "Pacote de benefícios Aurora · versão 1 · "Conta salário"".
 */
function criar_pergunta_da_secao(secao) {
  // O <details> abre e fecha sozinho ao clicar no <summary>.
  const pergunta = criar_no_cartao("details", "pergunta-frequente", "");
  // O título da seção é a pergunta que aparece fechada.
  const titulo_da_pergunta = criar_no_cartao("summary", "", secao.titulo);
  // O texto da seção é a resposta.
  const resposta = criar_no_cartao("p", "", secao.texto);
  // De onde veio a resposta: documento, versão e seção.
  const texto_da_fonte = secao.documento + " · versão " + secao.versao + " · \"" + secao.titulo + "\"";
  const fonte = criar_no_cartao("span", "fonte-resposta", texto_da_fonte);
  pergunta.append(titulo_da_pergunta, resposta, fonte);
  return pergunta;
}

/**
 * Monta o quadro de dúvidas: uma pergunta que abre e fecha para cada seção do catálogo.
 *
 * Recebe: secoes — os benefícios e o atendimento, na ordem. Devolve: nada.
 */
function mostrar_duvidas_reais(secoes) {
  // O título do quadro passa a dizer de onde vêm as respostas.
  document.querySelector("[data-titulo-duvidas]").textContent = "O que o catálogo da empresa diz";
  const quadro = document.querySelector("[data-quadro-duvidas]");
  // Tira as perguntas de exemplo.
  tirar_perguntas_do_quadro(quadro);
  // Uma pergunta por seção, antes do botão "Ver as perguntas frequentes para a equipe".
  const botao_do_faq = quadro.querySelector("a.botao");
  for (const secao of secoes) {
    quadro.insertBefore(criar_pergunta_da_secao(secao), botao_do_faq);
  }
}

/**
 * Monta a linha de um canal de atendimento: o ícone, o nome em negrito e o contato embaixo.
 *
 * Recebe: nome — ex.: "Central de atendimento"; contato — ex.: "0800 000 0001". Devolve: a linha pronta.
 */
function criar_canal_de_atendimento(nome, contato) {
  // A linha do canal.
  const canal = criar_no_cartao("div", "canal-atendimento", "");
  // O ícone, numa caixa redonda.
  const caixa_do_icone = criar_no_cartao("span", "envio-icone", "");
  caixa_do_icone.append(criar_icone("icone-pergunta"));
  // O nome em negrito e o contato embaixo.
  const textos = criar_no_cartao("div", "", "");
  textos.append(criar_no_cartao("strong", "", nome), criar_no_cartao("span", "", contato));
  canal.append(caixa_do_icone, textos);
  return canal;
}

/**
 * Monta o quadro de atendimento: cada linha das seções de atendimento vira um canal.
 *
 * Recebe: atendimento — as seções "Onde consultar" e "Canais de dúvidas". Devolve: nada.
 * Exemplo: "- Central de atendimento: 0800 000 0001" → canal "Central de atendimento" com "0800 000 0001".
 */
function mostrar_canais_reais(atendimento) {
  const quadro = document.querySelector("[data-canais-atendimento]");
  // Tira os canais de exemplo.
  tirar_canais_do_quadro(quadro);
  for (const secao of atendimento) {
    // Cada linha do texto da seção pode ser um canal.
    for (const linha of secao.texto.split("\n")) {
      // Tira o "- " do começo da lista e os espaços das pontas.
      const linha_limpa = linha.replace(/^- /, "").trim();
      // Linha vazia não vira canal.
      if (!linha_limpa) {
        continue;
      }
      // "Nome: contato" vira o nome em negrito e o contato embaixo; sem ":", a linha inteira é o contato.
      const posicao_dos_dois_pontos = linha_limpa.indexOf(": ");
      let nome = secao.titulo;
      let contato = linha_limpa;
      if (posicao_dos_dois_pontos !== -1) {
        nome = linha_limpa.slice(0, posicao_dos_dois_pontos);
        contato = linha_limpa.slice(posicao_dos_dois_pontos + 2);
      }
      quadro.append(criar_canal_de_atendimento(nome, contato));
    }
  }
}

/**
 * Escreve de onde vem o catálogo: documento, versão e vigência de cada documento vigente.
 *
 * Recebe: dados — o catálogo da API. Devolve: nada.
 */
function mostrar_origem_do_catalogo(dados) {
  // Uma parte por documento vigente: "título · versão N · vigente até DD/MM/AAAA".
  const partes = [];
  for (const documento of dados.documentos) {
    partes.push(documento.titulo + " · versão " + documento.versao + " · vigente até " + data_brasileira_do_catalogo(documento.vigencia_fim));
  }
  let texto = "Catálogo definido pelo banco para a " + dados.empresa + " · " + partes.join(" | ");
  // Nenhum documento vigente: a vitrine fica vazia e a tela diz por quê.
  if (partes.length === 0) {
    texto = frase_com_o_nome("O banco ainda não publicou um catálogo vigente para a ", dados.empresa);
  }
  document.querySelector("[data-origem-catalogo]").textContent = texto;
}

/**
 * Escreve uma data AAAA-MM-DD no jeito brasileiro ("2026-12-31" → "31/12/2026").
 *
 * Recebe: texto. Devolve: a data no jeito brasileiro.
 */
function data_brasileira_do_catalogo(texto) {
  // Separa ano, mês e dia pelo "-".
  const partes = texto.split("-");
  // Monta de trás para a frente: dia/mês/ano.
  return partes[2] + "/" + partes[1] + "/" + partes[0];
}

/**
 * Mostra só os filtros das categorias que o catálogo da empresa usa ("Todos" aparece sempre).
 *
 * Recebe: beneficios — os benefícios da API (cada um com a sua categoria, quando o catálogo diz). Devolve: nada.
 */
function mostrar_filtros_do_catalogo(beneficios) {
  // As categorias usadas, sem repetir (um Set guarda cada valor uma vez só).
  const categorias_do_catalogo = new Set();
  for (const beneficio of beneficios) {
    // Benefício sem categoria aparece só em "Todos".
    if (beneficio.categoria) {
      categorias_do_catalogo.add(beneficio.categoria);
    }
  }
  for (const filtro of document.querySelectorAll("[data-categoria-filtro]")) {
    const categoria = filtro.dataset.categoriaFiltro;
    // Esconde o filtro de uma categoria que o catálogo não usa (o "Todos" nunca some).
    filtro.hidden = categoria !== "todas" && !categorias_do_catalogo.has(categoria);
  }
}

/**
 * Troca todo o exemplo da página pelo catálogo real.
 *
 * Recebe: dados — o catálogo da API ({empresa, documentos, beneficios, atendimento}). Devolve: nada.
 */
function mostrar_catalogo_real(dados) {
  // Subtítulo com o nome real da empresa.
  const comeco_do_subtitulo = frase_com_o_nome("Vantagens que o banco definiu para os funcionários da ", dados.empresa);
  document.querySelector("[data-beneficios-subtitulo]").textContent = comeco_do_subtitulo + " Consulte, tire dúvidas e divulgue para a equipe.";
  // De onde vem o catálogo (documento, versão e vigência).
  mostrar_origem_do_catalogo(dados);
  // Os filtros: "Todos" e as categorias que o catálogo da empresa usa.
  mostrar_filtros_do_catalogo(dados.beneficios);
  // Os cartões (js/beneficios_do_catalogo.js), as dúvidas e o atendimento.
  mostrar_beneficios_reais(document.querySelector("[data-grade-beneficios]"), dados.beneficios);
  mostrar_duvidas_reais(dados.beneficios.concat(dados.atendimento));
  mostrar_canais_reais(dados.atendimento);
}

/**
 * Tira as barras cinza de "carregando" de tudo o que esperava o catálogo (os dados já estão nos elementos).
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_espera_dos_beneficios() {
  // Os textos (subtítulo, origem, filtros) e as listas (cartões, dúvidas, atendimento) marcados no HTML.
  marcar_todos_como_carregados("main [data-aguarda-dado], main [data-aguarda-bloco]");
}

/**
 * O servidor não respondeu: um aviso no lugar de cada parte do catálogo, nunca o exemplo da Aurora.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_beneficios_indisponiveis() {
  // Subtítulo sem nome de empresa (o do HTML é o exemplo da Aurora).
  document.querySelector("[data-beneficios-subtitulo]").textContent =
    "Vantagens que o banco definiu para os funcionários da sua empresa. Consulte, tire dúvidas e divulgue para a equipe.";
  // A linha "de onde vem o catálogo" vira o aviso principal da página.
  document.querySelector("[data-origem-catalogo]").textContent =
    "Não foi possível carregar o catálogo agora. Tente de novo em alguns minutos.";
  // Sem catálogo, não há categoria para filtrar: fica só o "Todos".
  mostrar_filtros_do_catalogo([]);
  // Os cartões de exemplo saem; o recado ocupa a linha inteira da grade.
  const recado_dos_cartoes = criar_no_cartao("p", "painel-vazio painel-vazio-neutro", RECADO_SEM_CATALOGO);
  recado_dos_cartoes.style.gridColumn = "1 / -1";
  document.querySelector("[data-grade-beneficios]").replaceChildren(recado_dos_cartoes);
  // As perguntas de exemplo saem; o recado fica antes do botão das perguntas frequentes.
  const quadro_das_duvidas = document.querySelector("[data-quadro-duvidas]");
  tirar_perguntas_do_quadro(quadro_das_duvidas);
  quadro_das_duvidas.insertBefore(criar_no_cartao("p", "conferencia-nota", RECADO_SEM_CATALOGO), quadro_das_duvidas.querySelector("a.botao"));
  // Os canais de exemplo saem; o recado fica no lugar deles.
  const quadro_do_atendimento = document.querySelector("[data-canais-atendimento]");
  tirar_canais_do_quadro(quadro_do_atendimento);
  quadro_do_atendimento.append(criar_no_cartao("p", "conferencia-nota", RECADO_SEM_CATALOGO));
  // Tudo pronto: as barras cinza saem e aparecem os avisos.
  liberar_espera_dos_beneficios();
}

/**
 * Busca o catálogo real e troca o exemplo por ele (ou pelo aviso, se o servidor falhar).
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: fica o exemplo.
 */
async function carregar_beneficios_de_verdade() {
  // Aberta como arquivo (o protótipo): fica o exemplo do layout.
  if (!beneficios_com_servidor()) {
    return;
  }
  const dados = await buscar_beneficios_da_empresa();
  // Servidor fora do ar ou com erro: o aviso no lugar do exemplo.
  if (!dados) {
    mostrar_beneficios_indisponiveis();
    return;
  }
  // try/catch: um catálogo que a tela não consegue desenhar também vira o aviso (a tela nunca fica cinza para
  // sempre); o erro segue adiante ("throw") para continuar aparecendo no console e nos roteiros de clique.
  try {
    mostrar_catalogo_real(dados);
  } catch (erro) {
    mostrar_beneficios_indisponiveis();
    throw erro;
  }
  // Deu certo: as barras cinza saem e aparece o catálogo.
  liberar_espera_dos_beneficios();
}

// Quando o HTML terminar de carregar, troca o exemplo pelos dados reais (se houver servidor).
document.addEventListener("DOMContentLoaded", carregar_beneficios_de_verdade);
