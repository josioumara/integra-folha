/*
  endomarketing.js — a aba "Materiais para divulgar" do Portal da Empresa (menu: "Materiais de endomarketing").

  Para que serve: mostra os materiais que o Santander preparou e publicou para a empresa (ADR-115, "o banco gera, a
  empresa comunica") e deixa a pessoa do RH levá-los para a equipe:
    - cada material vira um cartão: título, tipo, canal, data de publicação por extenso e o texto com as fontes (numa
      parte que abre e fecha);
    - "Copiar texto": copia o título e o texto para colar no e-mail ou no WhatsApp;
    - "Baixar texto": baixa o mesmo texto num arquivo .txt, montado aqui no navegador (sem pedir nada ao servidor);
    - "Baixar arte": só quando o banco publicou uma arte junto (tem_arte), baixa a imagem PNG;
    - o filtro por tipo aparece quando a lista tem mais de um tipo de material.
  A empresa NÃO cria, não ajusta e não aprova material: quem faz isso é o especialista do banco, no Portal Interno.

  ATENÇÃO — protótipo: aberta com dois cliques (sem servidor), a página mostra três materiais de exemplo, escritos
  abaixo. Com servidor, os exemplos nunca são desenhados: o js/endomarketing_real.js busca os materiais publicados
  de verdade e chama mostrar_materiais(); os desvios para o servidor estão marcados com "Com servidor" nas funções
  abaixo.
*/

// ===== Dados de exemplo (só para abrir sem servidor) =====

// Três materiais publicados de exemplo, no mesmo formato que a API devolve (visão da empresa).
const MATERIAIS_DE_EXEMPLO = [
  {
    material_id: "exemplo001", tipo: "comunicado", nome_do_tipo: "Comunicado interno", canal: "email",
    nome_do_canal: "E-mail", titulo: "Seu salário no Santander: conheça as vantagens",
    blocos: [
      { texto: "Oi, time! A partir de agora, o salário de vocês é pago pelo Santander, e isso traz vantagens.",
        fontes: ["Pacote Folha Aurora v1 › Conta salário"] },
      { texto: "O salário cai numa conta salário, sem tarifa de manutenção. Quem preferir pode pedir a portabilidade para outro banco, sem custo.",
        fontes: ["Pacote Folha Aurora v1 › Conta salário"] },
      { texto: "Dúvidas? Fale com a central de atendimento (0800 000 0001, dias úteis, das 8h às 20h).",
        fontes: ["Pacote Folha Aurora v1 › Canais de dúvidas"] },
    ],
    publicado_em: "2026-09-26T14:00:00+00:00", tem_arte: true,
  },
  {
    material_id: "exemplo002", tipo: "faq", nome_do_tipo: "FAQ para funcionários", canal: "whatsapp",
    nome_do_canal: "WhatsApp", titulo: "Perguntas frequentes: seu salário no Santander",
    blocos: [
      { texto: "Preciso abrir conta corrente para receber o salário? Não. O salário cai na conta salário, sem tarifa de manutenção.",
        fontes: ["Pacote Folha Aurora v1 › Conta salário"] },
      { texto: "Posso receber em outro banco? Pode: a portabilidade é sem custo e pode ser pedida a qualquer momento.",
        fontes: ["Pacote Folha Aurora v1 › Conta salário"] },
    ],
    publicado_em: "2026-09-20T10:30:00+00:00", tem_arte: false,
  },
  {
    material_id: "exemplo003", tipo: "kit_boas_vindas", nome_do_tipo: "Kit de boas-vindas", canal: "mural",
    nome_do_canal: "Mural ou intranet", titulo: "Bem-vindo(a) à Aurora!",
    blocos: [
      { texto: "Que bom ter você com a gente! Seu salário vai ser pago pelo Santander. Veja como começar.",
        fontes: ["Pacote Folha Aurora v1 › Conta salário"] },
      { texto: "Se quiser a conta corrente, abra pelo aplicativo com o seu CPF: o pacote Folha Essencial fica sem tarifa por 12 meses.",
        fontes: ["Pacote Folha Aurora v1 › Conta corrente com pacote Folha Essencial"] },
    ],
    publicado_em: "2026-09-10T09:00:00+00:00", tem_arte: true,
  },
];

// O ícone de cada tipo de material (o id do desenho na biblioteca de ícones da página).
const ICONE_DO_TIPO = {
  comunicado: "icone-documento",
  faq: "icone-pergunta",
  kit_boas_vindas: "icone-kit",
  lembrete_conta: "icone-cartao",
};

// Quanto tempo o botão mostra "Copiado!" antes de voltar ao normal (em milissegundos).
const TEMPO_DO_RECADO_DE_COPIA = 1500;

// ===== Estado =====

// Os materiais publicados que a página mostra (os de exemplo, ou os do servidor).
const materiais_publicados = [];
// O tipo escolhido no filtro ("todos" = sem filtro).
let tipo_escolhido = "todos";

// ===== Apoio =====

/**
 * Diz se a página foi aberta com dois cliques (como arquivo), sem servidor.
 *
 * Recebe: nada. Devolve: true (arquivo, sem servidor) ou false (servida pela aplicação).
 * Exemplo: "file:///D:/.../endomarketing.html" → true; "http://127.0.0.1:8000/endomarketing.html" → false.
 */
function pagina_aberta_como_arquivo() {
  // Servida pela aplicação, o endereço começa com "http" (ou "https").
  return !window.location.protocol.startsWith("http");
}

/**
 * Espera um tempo (sem travar a página). Ex.: await esperar(1500).
 *
 * Recebe: milissegundos. Devolve: uma "promessa" que termina depois do tempo.
 */
function esperar(milissegundos) {
  // setTimeout chama a função "terminar" depois do tempo pedido.
  return new Promise(function (terminar) {
    setTimeout(terminar, milissegundos);
  });
}

/**
 * Escreve uma data e hora da API como data por extenso, do jeito brasileiro.
 *
 * Recebe: texto_da_data — no formato da API (ISO), ex.: "2026-09-26T14:00:00+00:00".
 * Devolve: a data por extenso, ex.: "26 de setembro de 2026".
 */
function data_por_extenso(texto_da_data) {
  // Transforma o texto numa data que o navegador entende.
  const data = new Date(texto_da_data);
  // Pede ao navegador o dia, o nome do mês e o ano, em português do Brasil.
  return data.toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" });
}

/**
 * Cria um elemento da página com uma classe e um texto (o texto entra como texto, nunca como HTML).
 *
 * Recebe: etiqueta — ex.: "p"; classe — ex.: "conferencia-nota" (ou "" sem classe); texto (ou "" sem texto).
 * Devolve: o elemento pronto.
 */
function criar_elemento(etiqueta, classe, texto) {
  // O elemento novo.
  const elemento = document.createElement(etiqueta);
  // A classe (aparência), quando há.
  if (classe) {
    elemento.className = classe;
  }
  // textContent: o texto aparece como está, sem virar código na página.
  elemento.textContent = texto;
  return elemento;
}

/**
 * Cria um ícone da biblioteca de ícones da página.
 *
 * Recebe: nome_do_icone — ex.: "icone-documento". Devolve: o <svg> pronto.
 */
function criar_icone(nome_do_icone) {
  // Desenhos SVG precisam ser criados com o "endereço" do SVG (o namespace).
  const endereco_do_svg = "http://www.w3.org/2000/svg";
  const icone = document.createElementNS(endereco_do_svg, "svg");
  icone.setAttribute("class", "icone");
  // <use href="#nome"> "carimba" o desenho guardado no alto da página.
  const carimbo = document.createElementNS(endereco_do_svg, "use");
  carimbo.setAttribute("href", "#" + nome_do_icone);
  icone.append(carimbo);
  return icone;
}

// ===== O texto para divulgar =====

/**
 * O texto do material, pronto para colar ou baixar: o título e os blocos, separados por uma linha em branco.
 * As fontes ficam de fora: elas servem para conferir (aparecem na prévia), não para a equipe ler.
 *
 * Recebe: material — {titulo, blocos: [{texto}]}. Devolve: o texto.
 * Exemplo: {titulo: "Oi", blocos: [{texto: "A"}, {texto: "B"}]} → "Oi\n\nA\n\nB".
 */
function texto_para_divulgar(material) {
  // O título vem primeiro.
  const partes = [material.titulo];
  // Depois, cada bloco do material, na ordem.
  for (const bloco of material.blocos) {
    partes.push(bloco.texto);
  }
  // Uma linha em branco entre as partes.
  return partes.join("\n\n");
}

/**
 * O nome do arquivo para baixar, a partir do título do material (sem acentos, espaços ou símbolos).
 *
 * Recebe: material; extensao — "txt" ou "png". Devolve: o nome do arquivo.
 * Exemplo: título "Bem-vindo(a) à Aurora!" e "txt" → "material_bem_vindo_a_a_aurora.txt".
 */
function nome_do_arquivo(material, extensao) {
  // Separa cada letra do seu acento ("à" vira "a" + acento) e tira os acentos.
  const titulo_sem_acentos = material.titulo.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  // Tudo em minúsculas; o que não for letra ou número vira "_".
  const titulo_com_sublinhados = titulo_sem_acentos.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  // Tira o "_" das pontas e limita o tamanho do nome.
  const titulo_limpo = titulo_com_sublinhados.replace(/^_+|_+$/g, "").slice(0, 60);
  return "material_" + titulo_limpo + "." + extensao;
}

/**
 * Baixa um arquivo que já está no navegador (um "Blob": um pedaço de dados guardado na memória da página).
 *
 * Recebe: arquivo — o Blob; nome — o nome com que o arquivo é salvo. Devolve: nada.
 */
function baixar_arquivo(arquivo, nome) {
  // Um link invisível que aponta para o arquivo na memória, com o nome para salvar.
  const link = document.createElement("a");
  link.href = URL.createObjectURL(arquivo);
  link.download = nome;
  // "Clica" no link: o navegador salva o arquivo.
  link.click();
  // Libera a memória usada pelo endereço do arquivo.
  URL.revokeObjectURL(link.href);
}

// ===== As ações de cada material =====

/**
 * Copia o texto do material para a área de transferência (para colar no e-mail ou no WhatsApp).
 *
 * Recebe: material; botao — o botão clicado, que mostra "Copiado!" por um instante. Devolve: nada.
 */
async function copiar_texto(material, botao) {
  // try/catch: alguns navegadores bloqueiam a cópia fora de um site seguro; aí avisa em vez de falhar calado.
  try {
    await navigator.clipboard.writeText(texto_para_divulgar(material));
    botao.textContent = "Copiado!";
  } catch (erro) {
    botao.textContent = "Não deu para copiar";
  }
  // Depois de um instante, o botão volta ao nome normal.
  await esperar(TEMPO_DO_RECADO_DE_COPIA);
  botao.textContent = "Copiar texto";
}

/**
 * Baixa o texto do material num arquivo .txt, montado aqui no navegador.
 *
 * Recebe: material. Devolve: nada.
 */
function baixar_texto(material) {
  // O texto vira um arquivo de texto simples, com acentos (UTF-8).
  const arquivo = new Blob([texto_para_divulgar(material)], { type: "text/plain;charset=utf-8" });
  baixar_arquivo(arquivo, nome_do_arquivo(material, "txt"));
}

/**
 * Mostra um recado curto dentro do cartão de um material (ex.: a arte não pôde ser baixada).
 *
 * Recebe: cartao — o cartão do material; texto — o recado. Devolve: nada.
 */
function mostrar_recado_no_cartao(cartao, texto) {
  // O parágrafo do recado já existe no cartão, escondido.
  const recado = cartao.querySelector("[data-recado-do-material]");
  recado.textContent = texto;
  recado.hidden = false;
}

/**
 * Baixa a arte (PNG) que o Santander publicou junto com o material.
 *
 * Recebe: material; cartao — o cartão do material (para o recado). Devolve: nada.
 */
function baixar_arte(material, cartao) {
  // Com servidor, a imagem vem da aplicação (js/endomarketing_real.js).
  if (modo_real_do_endomarketing()) {
    baixar_arte_de_verdade(material, cartao);
    return;
  }
  // Sem servidor não há imagem guardada: o protótipo só explica.
  mostrar_recado_no_cartao(cartao, "Na demonstração sem servidor não há arte para baixar. No sistema, vem a imagem que o Santander publicou.");
}

// ===== O cartão de cada material =====

/**
 * Um botão pequeno de ação do cartão.
 *
 * Recebe: texto; ao_clicar — função que recebe o próprio botão. Devolve: o botão.
 */
function botao_de_acao(texto, ao_clicar) {
  // Botão de contorno, pequeno (o mesmo das outras listas do portal).
  const botao = criar_elemento("button", "botao botao-contorno botao-pequeno", texto);
  botao.type = "button";
  // Ao clicar, chama a ação passando o próprio botão (ex.: para mostrar "Copiado!").
  botao.addEventListener("click", function () {
    ao_clicar(botao);
  });
  return botao;
}

/**
 * A prévia do texto: uma parte que abre e fecha, com cada bloco do material e as suas fontes no catálogo.
 *
 * Recebe: material. Devolve: o <details> pronto (começa fechado).
 */
function montar_previa_do_texto(material) {
  // <details> abre e fecha sozinho ao clicar no <summary>.
  const previa = criar_elemento("details", "pergunta-frequente", "");
  previa.append(criar_elemento("summary", "", "Ver o texto e as fontes"));
  // O material como uma folha.
  const folha = criar_elemento("div", "documento-material", "");
  // Cada bloco: o texto e, embaixo, de onde ele veio no catálogo.
  for (const bloco of material.blocos) {
    const trecho = criar_elemento("div", "trecho-material", "");
    trecho.append(criar_elemento("p", "", bloco.texto));
    trecho.append(criar_elemento("span", "fonte-trecho", "Fonte: " + bloco.fontes.join("; ")));
    folha.append(trecho);
  }
  previa.append(folha);
  return previa;
}

/**
 * O cartão de um material: ícone, título, tipo, canal e data; a prévia do texto; os botões e o recado.
 *
 * Recebe: material — um item de materiais_publicados. Devolve: o <article> pronto.
 */
function montar_cartao_do_material(material) {
  // O cartão guarda o id do material (os roteiros de clique e o recado usam).
  const cartao = criar_elemento("article", "cartao painel-acompanhar", "");
  cartao.dataset.material = material.material_id;
  // Linha de cima: ícone do tipo, título e descrição, e o canal num selo.
  const cabecalho = criar_elemento("div", "rascunho-cabecalho", "");
  const caixa_do_icone = criar_elemento("span", "envio-icone", "");
  // Tipo sem ícone próprio usa o documento.
  caixa_do_icone.append(criar_icone(ICONE_DO_TIPO[material.tipo] || "icone-documento"));
  const textos = criar_elemento("div", "envio-textos", "");
  textos.append(criar_elemento("strong", "envio-titulo", material.titulo));
  textos.append(criar_elemento("span", "envio-arquivos",
    material.nome_do_tipo + " · publicado pelo Santander em " + data_por_extenso(material.publicado_em)));
  const selo_do_canal = criar_elemento("span", "selo selo-pequeno selo-neutro", material.nome_do_canal);
  cabecalho.append(caixa_do_icone, textos, selo_do_canal);
  // Os botões: copiar e baixar o texto sempre; baixar a arte só quando o banco publicou uma.
  const acoes = criar_elemento("div", "material-acoes", "");
  // Em tela estreita, os botões descem para a linha de baixo em vez de sair do cartão.
  acoes.style.flexWrap = "wrap";
  acoes.append(botao_de_acao("Copiar texto", function (botao) {
    copiar_texto(material, botao);
  }));
  acoes.append(botao_de_acao("Baixar texto", function () {
    baixar_texto(material);
  }));
  if (material.tem_arte) {
    acoes.append(botao_de_acao("Baixar arte", function () {
      baixar_arte(material, cartao);
    }));
  }
  // O recado do cartão (ex.: a arte não pôde ser baixada), escondido até ser preciso.
  const recado = criar_elemento("p", "conferencia-nota", "");
  recado.dataset.recadoDoMaterial = "";
  recado.hidden = true;
  cartao.append(cabecalho, montar_previa_do_texto(material), acoes, recado);
  return cartao;
}

// ===== A lista e o filtro por tipo =====

/**
 * Os tipos que aparecem na lista, sem repetir e na ordem em que aparecem.
 *
 * Recebe: nada. Devolve: a lista de {tipo, nome}. Ex.: [{tipo: "comunicado", nome: "Comunicado interno"}].
 */
function tipos_da_lista() {
  const tipos = [];
  // As chaves já vistas, para não repetir o tipo.
  const chaves_vistas = [];
  for (const material of materiais_publicados) {
    if (!chaves_vistas.includes(material.tipo)) {
      chaves_vistas.push(material.tipo);
      tipos.push({ tipo: material.tipo, nome: material.nome_do_tipo });
    }
  }
  return tipos;
}

/**
 * Monta os botões do filtro por tipo ("Todos" e um por tipo). Com um tipo só, o filtro fica escondido.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_filtros_de_tipo() {
  const grupo = document.querySelector("[data-filtros-tipo]");
  // Esvazia antes de montar (a lista pode ter mudado).
  grupo.replaceChildren();
  const tipos = tipos_da_lista();
  // O tipo escolhido que não existe mais na lista volta para "todos".
  let tipo_escolhido_existe = false;
  for (const item of tipos) {
    if (item.tipo === tipo_escolhido) {
      tipo_escolhido_existe = true;
    }
  }
  if (!tipo_escolhido_existe) {
    tipo_escolhido = "todos";
  }
  // "Todos" primeiro, depois um botão por tipo.
  const opcoes = [{ tipo: "todos", nome: "Todos" }].concat(tipos);
  for (const opcao of opcoes) {
    const botao = criar_elemento("button", "filtro-rapido", opcao.nome);
    botao.type = "button";
    botao.dataset.filtroTipo = opcao.tipo;
    // O filtro escolhido fica destacado.
    botao.classList.toggle("filtro-rapido-ativo", opcao.tipo === tipo_escolhido);
    botao.addEventListener("click", function () {
      escolher_tipo(opcao.tipo);
    });
    grupo.append(botao);
  }
  // Com menos de dois tipos, filtrar não ajuda: o filtro some.
  grupo.hidden = tipos.length < 2;
}

/**
 * Troca o tipo escolhido no filtro e redesenha a lista.
 *
 * Recebe: tipo — ex.: "faq" ou "todos". Devolve: nada.
 */
function escolher_tipo(tipo) {
  tipo_escolhido = tipo;
  montar_lista_de_materiais();
}

/**
 * O resumo abaixo do título: quantos materiais e quando saiu o mais recente.
 *
 * Recebe: nada. Devolve: o texto (vazio sem materiais).
 * Exemplo: "3 materiais publicados · o mais recente em 26 de setembro de 2026".
 */
function resumo_da_lista() {
  // Sem materiais, o aviso de lista vazia já diz tudo.
  if (materiais_publicados.length === 0) {
    return "";
  }
  // Singular ou plural.
  let quantidade = materiais_publicados.length + " materiais publicados";
  if (materiais_publicados.length === 1) {
    quantidade = "1 material publicado";
  }
  // A lista vem do mais recente ao mais antigo: o primeiro é o mais recente.
  return quantidade + " · o mais recente em " + data_por_extenso(materiais_publicados[0].publicado_em);
}

/**
 * Desenha a lista de materiais, respeitando o filtro por tipo, e o aviso de lista vazia.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_lista_de_materiais() {
  montar_filtros_de_tipo();
  const lista = document.querySelector("[data-lista-materiais]");
  // Esvazia a lista antes de desenhar de novo.
  lista.replaceChildren();
  for (const material of materiais_publicados) {
    // Só os materiais do tipo escolhido (ou todos).
    if (tipo_escolhido === "todos" || material.tipo === tipo_escolhido) {
      lista.append(montar_cartao_do_material(material));
    }
  }
  // Nenhum material publicado: aparece o aviso.
  document.querySelector("[data-sem-materiais]").hidden = materiais_publicados.length > 0;
  document.querySelector("[data-resumo-materiais]").textContent = resumo_da_lista();
}

/**
 * Troca os materiais da página e redesenha a lista. Com servidor, é chamada pelo js/endomarketing_real.js.
 *
 * Recebe: materiais — a lista no formato da API (visão da empresa), do mais recente ao mais antigo.
 * Devolve: nada.
 */
function mostrar_materiais(materiais) {
  // Esvazia a lista atual e põe os materiais novos, na mesma ordem.
  materiais_publicados.length = 0;
  for (const material of materiais) {
    materiais_publicados.push(material);
  }
  montar_lista_de_materiais();
}

// ===== Ligando tudo =====

/**
 * Prepara a página quando o HTML termina de carregar.
 *   - O tipo pedido no endereço (ex.: ?tipo=faq, vindo da aba de benefícios) já abre filtrado.
 *   - Aberta como arquivo: mostra os materiais de exemplo.
 *   - Com servidor: avisa que está carregando; o js/endomarketing_real.js traz os materiais publicados.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_materiais_para_divulgar() {
  // O tipo do endereço, se houver (se não existir na lista, o filtro volta para "todos" sozinho).
  const tipo_do_endereco = new URLSearchParams(window.location.search).get("tipo");
  if (tipo_do_endereco) {
    tipo_escolhido = tipo_do_endereco;
  }
  // Sem servidor: os exemplos.
  if (pagina_aberta_como_arquivo()) {
    mostrar_materiais(MATERIAIS_DE_EXEMPLO);
    return;
  }
  // Com servidor: o recado de espera até os materiais chegarem. O resumo está marcado com data-aguarda-dado, então
  // a frase vira uma barra cinza do tamanho dela (js/carregando_dados.js); o js/endomarketing_real.js a libera.
  document.querySelector("[data-resumo-materiais]").textContent = "Carregando os materiais…";
}

// Espera o HTML carregar inteiro antes de ligar tudo.
document.addEventListener("DOMContentLoaded", preparar_materiais_para_divulgar);
