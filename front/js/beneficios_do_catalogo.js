/*
  beneficios_do_catalogo.js — monta os cartões de benefício a partir do catálogo REAL da empresa (ADR-69).

  Para que serve: o Início (home.html) e a aba "Benefícios do seu time" (beneficios.html) mostram os mesmos
  cartões. Com a página ligada à aplicação, cada seção do catálogo que o banco definiu para a empresa vira um cartão:
    - título: o título da seção (ex.: "Crédito consignado");
    - resumo: a primeira frase do resumo do benefício;
    - categoria (data-categoria, para os filtros da vitrine), quando o catálogo diz a categoria;
    - detalhes (na janela do js/janela_beneficio.js): "Como funciona", "Quem pode usar" e "Como contratar", quando o
      catálogo tem essas partes; senão, o texto do catálogo como ele é. E sempre de onde ele veio (documento, versão
      e seção). A tela nunca inventa uma parte que o catálogo não traz.
*/

// As três partes da janela de detalhes, na ordem: a chave que vem da API e o nome que aparece na tela.
const PARTES_DO_BENEFICIO = [
  ["como_funciona", "Como funciona"],
  ["quem_pode_usar", "Quem pode usar"],
  ["como_contratar", "Como contratar"],
];

/**
 * A primeira frase de um texto do catálogo, para o resumo do cartão.
 *
 * Recebe: texto — o texto da seção. Devolve: a primeira frase (ou a primeira linha, se não houver ponto final).
 * Exemplo: "Taxa negociada para a Aurora. Sujeito a análise." → "Taxa negociada para a Aurora."
 */
function primeira_frase(texto) {
  // Junta as linhas num texto corrido (listas com "- " viram frases seguidas).
  const texto_corrido = texto.split("\n").join(" ").replace(/- /g, "").trim();
  // Onde termina a primeira frase (o primeiro ". ").
  const fim_da_frase = texto_corrido.indexOf(". ");
  // Sem ponto final no meio: o texto inteiro é a frase.
  if (fim_da_frase === -1) {
    return texto_corrido;
  }
  return texto_corrido.slice(0, fim_da_frase + 1);
}

/**
 * Termina uma frase com o nome da empresa, sem ponto duplo quando o nome já acaba em ponto.
 *
 * Recebe: comeco — o começo da frase; nome — o nome da empresa. Devolve: a frase com um ponto final só.
 * Exemplo: ("Olá, ", "Aurora Alimentos Ltda.") → "Olá, Aurora Alimentos Ltda." (e não "Ltda..").
 */
function frase_com_o_nome(comeco, nome) {
  if (nome.endsWith(".")) {
    return comeco + nome;
  }
  return comeco + nome + ".";
}

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta; classe; texto. Devolve: o elemento.
 */
function criar_no_cartao(etiqueta, classe, texto) {
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
 * Cria o desenho (ícone SVG) usado pelos cartões, a partir de um símbolo que a página já tem.
 *
 * Recebe: nome_do_simbolo — ex.: "icone-cartao". Devolve: o elemento <svg>.
 * Por quê: ícone SVG precisa ser criado com createElementNS (o "endereço" do SVG), senão o navegador não desenha.
 */
function criar_icone(nome_do_simbolo) {
  const endereco_do_svg = "http://www.w3.org/2000/svg";
  const icone = document.createElementNS(endereco_do_svg, "svg");
  icone.setAttribute("class", "icone");
  const uso = document.createElementNS(endereco_do_svg, "use");
  uso.setAttribute("href", "#" + nome_do_simbolo);
  icone.append(uso);
  return icone;
}

/**
 * Monta o cartão de um benefício do catálogo real.
 *
 * Recebe: secao — {titulo, texto, documento, versao}. Devolve: o <article> do cartão.
 */
function criar_cartao_de_beneficio(secao) {
  // O cartão guarda o título em data-beneficio (identifica o benefício na página).
  const cartao = criar_no_cartao("article", "cartao cartao-beneficio", "");
  cartao.dataset.beneficio = secao.titulo;
  // A categoria vira o filtro da vitrine ("sem" quando o catálogo não diz: aparece só em "Todos").
  cartao.dataset.categoria = secao.categoria || "sem";
  // Topo: o ícone.
  const topo = criar_no_cartao("div", "beneficio-topo", "");
  const caixa_do_icone = criar_no_cartao("span", "beneficio-icone", "");
  caixa_do_icone.append(criar_icone("icone-cartao"));
  topo.append(caixa_do_icone);
  // Título e resumo.
  cartao.append(topo, criar_no_cartao("h3", "beneficio-titulo", secao.titulo),
    criar_no_cartao("p", "beneficio-texto", primeira_frase(secao.resumo || secao.texto)));
  // Detalhes escondidos (a janela copia daqui): as partes do catálogo (ou o texto inteiro) e a fonte.
  const detalhes = criar_no_cartao("dl", "beneficio-detalhes", "");
  detalhes.hidden = true;
  let tem_partes = false;
  for (const [chave, nome] of PARTES_DO_BENEFICIO) {
    // Só as partes que o catálogo traz
    if (secao.partes && secao.partes[chave]) {
      detalhes.append(criar_no_cartao("dt", "", nome), criar_no_cartao("dd", "", secao.partes[chave]));
      tem_partes = true;
    }
  }
  // Catálogo só com texto corrido: o texto como ele é.
  if (!tem_partes) {
    detalhes.append(criar_no_cartao("dt", "", "O que diz o catálogo"), criar_no_cartao("dd", "", secao.texto));
  }
  detalhes.append(criar_no_cartao("dt", "", "De onde vem"),
    criar_no_cartao("dd", "", secao.documento + " · versão " + secao.versao + " · seção \"" + secao.titulo + "\""));
  cartao.append(detalhes);
  // Ações: ver detalhes (abre a janela) e ver os materiais que o Santander preparou para divulgar (ADR-115).
  const acoes = criar_no_cartao("div", "beneficio-acoes", "");
  const botao = criar_no_cartao("button", "link-seta botao-ver-detalhes", "Ver detalhes ");
  botao.type = "button";
  botao.append(criar_icone("icone-seta"));
  botao.addEventListener("click", function () {
    abrir_detalhes_do_beneficio(cartao);
  });
  const divulgar = criar_no_cartao("a", "link-divulgar", "Ver materiais");
  divulgar.href = "endomarketing.html";
  acoes.append(botao, divulgar);
  cartao.append(acoes);
  return cartao;
}

/**
 * Troca os cartões de exemplo de uma grade pelos benefícios reais.
 *
 * Recebe: grade — o elemento da grade; beneficios — as seções da API. Devolve: nada.
 */
function mostrar_beneficios_reais(grade, beneficios) {
  // Esvazia os cartões de exemplo.
  grade.replaceChildren();
  // Um cartão por benefício.
  for (const secao of beneficios) {
    grade.append(criar_cartao_de_beneficio(secao));
  }
}

/**
 * Busca o catálogo da empresa de quem entrou.
 *
 * Recebe: nada. Devolve: os dados da API ({empresa, documentos, beneficios, atendimento}) ou null (sem servidor).
 */
async function buscar_beneficios_da_empresa() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return null;
  }
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/empresa/beneficios");
    if (!resposta.ok) {
      return null;
    }
    return await resposta.json();
  } catch (erro) {
    return null;
  }
}
