/*
  banco_endomarketing.js — a aba "Endomarketing" do Portal Interno (ADR-115: "o banco gera, a empresa comunica").

  Para que serve: liga a página banco_endomarketing.html à aplicação. O especialista do banco:
    1. escolhe a empresa na faixa do topo (GET /api/banco/endomarketing: a carteira com quantos rascunhos e publicados
       cada uma tem). Até escolher, nada aparece embaixo; escolhida, a faixa se recolhe no nome dela, com "Trocar
       empresa". Embaixo, três guias (como as dos Indicadores; ?aba=base, ?aba=regras ou ?aba=material):
       "Base de Conhecimento", com as KBs dela; "Regras gerais", com as KBs que valem para todas as empresas
       (diretrizes gerais ou Santander); as duas pelo abrir_kbs_do_dono, do js/banco_beneficios.js; e "Material para
       Comunicação", com os passos 2 a 5 abaixo. A empresa e a guia ficam no
       endereço, para o F5 voltar nelas;
    2. vê o "Kit em uso", só para ler (GET /api/banco/empresas/{id}/kit_em_uso: o próprio da empresa ou o padrão,
       com as cores e o logo), e o link "Editar na KB →", que abre a KB "Kit da marca" da empresa, a fonte única do
       kit;
       vê as sugestões e monta o pedido (GET /api/banco/empresas/{id}/endomarketing: kit, catálogo, sugestões,
       materiais, tipos e canais): tipo, canal, os benefícios que entram (pelo menos 1) e "algo a destacar";
    3. gera o rascunho com o Agente de Endomarketing (POST .../endomarketing/gerar) e confere o texto, bloco a bloco,
       com as fontes, e a arte desenhada pelo navegador com o kit da empresa (js/arte_do_material.js), no formato do
       canal do rascunho: banner no e-mail, cartaz A4 no mural, imagem quadrada no WhatsApp. Só a arte desse canal
       aparece e é publicada;
    4. publica para a empresa, mandando junto a arte em PNG (POST .../publicar, multipart), ou descarta;
    5. acompanha os materiais da empresa (Ver, Baixar texto, Baixar arte) e retira um publicado (POST .../retirar).
    6. Diz se o texto que o agente escreveu ficou bom, com o joinha no rascunho e na janela "Ver" (ADR-151;
       js/opiniao_dos_agentes.js). A satisfação aparece no Acompanhamento dos agentes.
  A empresa só vê o que foi publicado. Não há edição livre do texto (ele foi conferido com o catálogo) nem "ajustes
  pela IA": para mudar, gera-se de novo.
  As confirmações (descartar, retirar) aparecem numa janela da própria página, nunca no confirm() do navegador.
  Usa do js/arte_do_material.js: desenhar_arte_do_material, molde_do_canal e descricao_do_molde.
  Enquanto a carteira não chega, a lista de empresas mostra a barra cinza de "carregando" (js/carregando_dados.js);
  se o servidor falhar, entra o aviso "Não foi possível carregar agora.".
*/

// ===== Constantes da tela =====

// O ícone de cada tipo de material (os tipos vêm da API; tipo novo usa o do documento).
const ICONE_DO_TIPO = { comunicado: "icone-documento", faq: "icone-pergunta", kit_boas_vindas: "icone-kit",
  lembrete_conta: "icone-cartao" };
// A frase curta embaixo do nome de cada tipo (tipo novo fica sem frase).
const FRASE_DO_TIPO = { comunicado: "Para e-mail ou mural", faq: "Respostas às dúvidas comuns",
  kit_boas_vindas: "Para quem acabou de chegar", lembrete_conta: "Para toda a equipe abrir a conta" };
// A cor do selo de cada situação do material (as classes .selo-* do css/estilos.css).
const COR_DO_SELO_DA_SITUACAO = { RASCUNHO: "selo-marca", PUBLICADO: "selo-sucesso", RETIRADO: "selo-atencao",
  DESCARTADO: "selo-neutro", APROVADO: "selo-neutro" };
// Os filtros da lista de materiais, na ordem em que aparecem: a chave (a situação) e o nome do botão.
const FILTROS_DE_SITUACAO = [
  ["todos", "Todos"],
  ["RASCUNHO", "Rascunhos"],
  ["PUBLICADO", "Publicados"],
  ["RETIRADO", "Retirados"],
  ["DESCARTADO", "Descartados"],
  ["APROVADO", "Modelo anterior"],
];

// As três guias da empresa escolhida (como as guias dos Indicadores); a primeira abre quando o endereço não pede outra.
const GUIAS_DO_ENDOMARKETING = ["base", "regras", "material"];

// O aviso que entra na lista de empresas quando o servidor não entregou a carteira.
const AVISO_DE_CARTEIRA_INDISPONIVEL = "Não foi possível carregar agora.";

// ===== Estado da tela =====

// Tudo o que a tela precisa lembrar entre um clique e outro.
const estado_do_endomarketing = {
  empresas: [],             // a carteira: [{ empresa_id, nome, rascunhos, publicados }]
  busca: "",                // o texto da busca de empresas, em minúsculas
  empresa_id: null,         // a empresa aberta (ex.: "EMP001"); null = nenhuma escolhida, nada aparece embaixo
  trocando_empresa: false,  // true depois de "Trocar empresa": a busca e a lista voltam a aparecer no topo
  guia: "base",             // a guia aberta: "base", "regras" ou "material"
  dono_das_regras: "GERAL", // na guia Regras gerais: "GERAL" (diretrizes gerais) ou "SANTANDER"
  dados: null,              // o que a API devolveu da empresa aberta (kit, beneficios, sugestoes, materiais...)
  kit_em_uso: null,         // o kit em uso da empresa aberta (rota /kit_em_uso), ou null enquanto não chega
  pedido_do_kit: 0,         // o número do último pedido do kit em uso (só a resposta dele é desenhada)
  inclusao_do_kit: null,    // a inclusão ligada ao kit de boas-vindas (vem da sugestão), ou null
  rascunho: null,           // o material aberto no rascunho (visão do banco), ou null
  molde: "cartao",          // o molde da arte: o do canal do rascunho aberto (molde_do_canal)
  filtro: "todos",          // a situação escolhida no filtro da lista
  acao_a_confirmar: null,   // a função que roda quando a pessoa confirma na janela de confirmação
};

// ===== Apoio =====

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como código).
 *
 * Recebe: etiqueta — ex.: "p"; classes — ex.: "selo selo-pequeno"; texto. Devolve: o elemento.
 */
function criar_elemento_do_endomarketing(etiqueta, classes, texto) {
  const elemento = document.createElement(etiqueta);
  // Põe as classes, se houver.
  if (classes) {
    elemento.className = classes;
  }
  // Põe o texto, se houver (textContent: um texto com "<script>" continua sendo só texto).
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Um ícone da biblioteca da página (o <symbol> com o nome dado).
 *
 * Recebe: nome — ex.: "icone-kit". Devolve: o elemento <svg> pronto.
 */
function criar_icone(nome) {
  // Elementos de desenho (SVG) precisam ser criados no "idioma" do SVG.
  const endereco_do_svg = "http://www.w3.org/2000/svg";
  const desenho = document.createElementNS(endereco_do_svg, "svg");
  desenho.setAttribute("class", "icone");
  // <use> "carimba" o símbolo guardado com esse nome.
  const carimbo = document.createElementNS(endereco_do_svg, "use");
  carimbo.setAttribute("href", "#" + nome);
  desenho.append(carimbo);
  return desenho;
}

/**
 * Manda um pedido à API e devolve a resposta já lida.
 *
 * Recebe: endereco; opcoes — as do fetch (método, corpo...). Devolve: { ok, dados } — dados é o JSON da resposta
 * (em erro, { detail }). Servidor fora do ar vira { ok: false } com uma mensagem clara.
 */
async function pedir_a_api_do_endomarketing(endereco, opcoes) {
  // try/catch: sem conexão (ou resposta que não é JSON), a tela mostra o recado em vez de quebrar.
  try {
    const resposta = await fetch(endereco, opcoes);
    const dados = await resposta.json();
    return { ok: resposta.ok, dados: dados };
  } catch (erro) {
    return { ok: false, dados: { detail: "Sem conexão com o servidor. Tente de novo." } };
  }
}

/**
 * Um pedido POST com um corpo em JSON.
 *
 * Recebe: endereco; corpo — o objeto a enviar. Devolve: { ok, dados }.
 */
function postar_json_do_endomarketing(endereco, corpo) {
  return pedir_a_api_do_endomarketing(endereco, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

/**
 * O texto de um erro da API (erro de regra vem em texto; erro de formato, em lista).
 *
 * Recebe: detalhe — o "detail" da resposta. Devolve: o texto para mostrar.
 */
function texto_do_erro_do_endomarketing(detalhe) {
  // Erro de regra: a API já manda a frase pronta.
  if (typeof detalhe === "string") {
    return detalhe;
  }
  // Erro de formato (lista de campos): uma frase geral.
  return "Confira as escolhas e tente de novo.";
}

/**
 * O endereço de uma rota da empresa aberta. Exemplo: endereco_da_empresa("/endomarketing/gerar") →
 * "/api/banco/empresas/EMP001/endomarketing/gerar".
 *
 * Recebe: complemento — o pedaço depois do código da empresa. Devolve: o endereço inteiro.
 */
function endereco_da_empresa(complemento) {
  // encodeURIComponent: o código entra no endereço sem virar outro caminho.
  return "/api/banco/empresas/" + encodeURIComponent(estado_do_endomarketing.empresa_id) + complemento;
}

/**
 * O endereço de uma ação sobre um material da empresa aberta. Exemplo: ("a1b2", "/retirar") →
 * "/api/banco/empresas/EMP001/endomarketing/a1b2/retirar".
 *
 * Recebe: material_id; acao — "/publicar", "/descartar", "/retirar" ou "/arte". Devolve: o endereço.
 */
function endereco_do_material(material_id, acao) {
  return endereco_da_empresa("/endomarketing/" + encodeURIComponent(material_id) + acao);
}

/**
 * Escreve data e hora do servidor no jeito brasileiro curto. Exemplo: "2026-09-28T12:00:00+00:00" → "28/09/2026, 09:00".
 *
 * Recebe: texto — a data e a hora (ou null). Devolve: o texto curto (vazio quando não há data).
 */
function data_e_hora_do_material(texto) {
  // Sem data: nada a mostrar.
  if (!texto) {
    return "";
  }
  // O navegador converte do horário universal para o do computador.
  const momento = new Date(texto);
  const dia = momento.toLocaleDateString("pt-BR");
  const hora = momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return dia + ", " + hora;
}

/**
 * Mostra o aviso verde no alto da página (ex.: "Publicado para a Aurora Alimentos").
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_aviso_do_endomarketing(texto) {
  document.querySelector("[data-aviso-endomarketing-texto]").textContent = texto;
  document.querySelector("[data-aviso-endomarketing]").hidden = false;
}

/**
 * Esconde o aviso verde do alto (quando a pessoa começa outra coisa).
 *
 * Recebe: nada. Devolve: nada.
 */
function esconder_aviso_do_endomarketing() {
  document.querySelector("[data-aviso-endomarketing]").hidden = true;
}

// ===== 1. A carteira (lista da esquerda) =====

/**
 * Busca a carteira de empresas, com quantos rascunhos e publicados cada uma tem, e redesenha a lista.
 *
 * Recebe: nada. Devolve: true se a carteira chegou; false se não (sem servidor ou sem permissão).
 */
async function carregar_carteira_do_endomarketing() {
  const resposta = await pedir_a_api_do_endomarketing("/api/banco/endomarketing", {});
  // Sem a carteira, não há o que mostrar.
  if (!resposta.ok) {
    return false;
  }
  estado_do_endomarketing.empresas = resposta.dados;
  mostrar_carteira_do_endomarketing();
  // A lista de empresas já é a do servidor: sai da espera (js/carregando_dados.js).
  marcar_como_carregado(document.querySelector("[data-lista-empresas-endomarketing]"));
  return true;
}

/**
 * O servidor não entregou a carteira: a lista de empresas mostra o aviso e sai da espera (nunca fica cinza).
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_carteira_indisponivel() {
  const lista = document.querySelector("[data-lista-empresas-endomarketing]");
  // O aviso, com o visual de "painel vazio", no lugar das empresas.
  const aviso = criar_elemento_do_endomarketing("li", "painel-vazio", AVISO_DE_CARTEIRA_INDISPONIVEL);
  lista.replaceChildren(aviso);
  // A lista sai da espera: o aviso aparece.
  marcar_como_carregado(lista);
}

/**
 * O resumo de uma empresa na lista. Exemplo: { rascunhos: 1, publicados: 2 } → "1 rascunho · 2 publicados".
 *
 * Recebe: empresa — um item da carteira. Devolve: o texto.
 */
function resumo_da_empresa_na_carteira(empresa) {
  // Singular ou plural, conforme a quantidade.
  let rascunhos = empresa.rascunhos + " rascunhos";
  if (empresa.rascunhos === 1) {
    rascunhos = "1 rascunho";
  }
  let publicados = empresa.publicados + " publicados";
  if (empresa.publicados === 1) {
    publicados = "1 publicado";
  }
  return rascunhos + " · " + publicados;
}

/**
 * A empresa no formato da lista comum da Carteira e do Endomarketing (empresas_para_mostrar, em
 * js/escolha_de_empresa.js).
 *
 * Recebe: empresa — um item da carteira do servidor ({empresa_id, nome, rascunhos, publicados, cnpjs,
 * cadastrada_em}). Devolve: { codigo, nome, cidade, cnpjs, cadastrada_em, empresa }. A busca daqui é pelo nome e pelo
 * CNPJ (a cidade fica vazia).
 */
function empresa_do_endomarketing_para_a_lista(empresa) {
  return { codigo: empresa.empresa_id, nome: empresa.nome, cidade: "", cnpjs: empresa.cnpjs || [],
    cadastrada_em: empresa.cadastrada_em || "", empresa: empresa };
}

/**
 * Desenha a lista de empresas, com a empresa aberta em destaque: sem busca, só as últimas cadastradas; com busca, as
 * que combinam com o nome ou com o CNPJ. Nunca mais do que cabe sem rolagem.
 *
 * Recebe: nada. Devolve: nada. A escolha é a mesma função da Carteira (js/escolha_de_empresa.js).
 */
function mostrar_carteira_do_endomarketing() {
  const lista = document.querySelector("[data-lista-empresas-endomarketing]");
  // Esvazia antes de montar.
  lista.replaceChildren();
  // As empresas da carteira no formato da lista comum.
  const empresas_da_carteira = [];
  for (const empresa_da_carteira of estado_do_endomarketing.empresas) {
    empresas_da_carteira.push(empresa_do_endomarketing_para_a_lista(empresa_da_carteira));
  }
  // As que aparecem: as últimas cadastradas, ou as que combinam com a busca.
  const escolhidas = empresas_para_mostrar(empresas_da_carteira, estado_do_endomarketing.busca);
  for (const escolhida of escolhidas.empresas) {
    // A empresa do servidor, com os rascunhos e os publicados.
    const empresa = escolhida.empresa;
    // Cada empresa é um botão largo (o mesmo visual das filas do Portal Interno).
    const botao = criar_elemento_do_endomarketing("button", "botao-envio-fila", "");
    botao.type = "button";
    botao.dataset.abrirEmpresaEndomarketing = empresa.empresa_id;
    // A empresa aberta fica destacada.
    if (empresa.empresa_id === estado_do_endomarketing.empresa_id) {
      botao.classList.add("botao-envio-fila-aberto");
      botao.setAttribute("aria-current", "true");
    }
    botao.append(criar_elemento_do_endomarketing("span", "botao-envio-fila-empresa", empresa.nome));
    botao.append(criar_elemento_do_endomarketing("span", "botao-envio-fila-detalhe", resumo_da_empresa_na_carteira(empresa)));
    // O botão vai dentro de um item da lista.
    const item = criar_elemento_do_endomarketing("li", "", "");
    item.append(botao);
    lista.append(item);
  }
  // Aviso quando a busca não acha nenhuma empresa.
  document.querySelector("[data-sem-empresas-endomarketing]").hidden = lista.children.length > 0;
  // O aviso de que há outras empresas fora da lista (some quando todas cabem).
  const aviso_das_ultimas = document.querySelector("[data-aviso-ultimas-empresas]");
  aviso_das_ultimas.textContent = escolhidas.aviso;
  aviso_das_ultimas.hidden = escolhidas.aviso === "";
  // O topo mostra a lista (escolhendo) ou só a empresa escolhida.
  mostrar_faixa_da_empresa();
}

/**
 * A faixa do topo: com uma empresa escolhida, mostra só o nome dela, os números e "Trocar empresa"; sem empresa
 * (ou depois de "Trocar empresa"), mostra a busca e a lista.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_faixa_da_empresa() {
  const empresa_id = estado_do_endomarketing.empresa_id;
  const escolhida = Boolean(empresa_id) && !estado_do_endomarketing.trocando_empresa;
  document.querySelector("[data-escolha-da-empresa]").hidden = escolhida;
  document.querySelector("[data-empresa-escolhida]").hidden = !escolhida;
  // Sem empresa escolhida, não há nome nem números para mostrar.
  if (!empresa_id) {
    return;
  }
  // O nome e os números vêm da carteira (chegam antes dos dados da empresa).
  for (const empresa of estado_do_endomarketing.empresas) {
    if (empresa.empresa_id === empresa_id) {
      document.querySelector("[data-nome-da-empresa]").textContent = empresa.nome;
      document.querySelector("[data-resumo-da-empresa-escolhida]").textContent = resumo_da_empresa_na_carteira(empresa);
    }
  }
}

/**
 * Mostra a guia escolhida e esconde as outras. As guias Base de Conhecimento e Regras gerais usam o mesmo cartão de
 * KBs (data-conteudo-endomarketing="base regras"): muda o dono, e as KBs dele são abertas.
 *
 * Recebe: guia — "base", "regras" ou "material". Devolve: nada.
 */
function trocar_guia_do_endomarketing(guia) {
  estado_do_endomarketing.guia = guia;
  // Liga só o botão da guia escolhida.
  for (const botao of document.querySelectorAll("[data-guia-endomarketing]")) {
    // Verdadeiro para o botão da guia escolhida.
    const e_a_escolhida = botao.dataset.guiaEndomarketing === guia;
    // A classe desenha a linha colorida embaixo da guia escolhida.
    botao.classList.toggle("aba-ficha-ativa", e_a_escolhida);
    // Leitores de tela sabem qual guia está escolhida.
    botao.setAttribute("aria-selected", String(e_a_escolhida));
  }
  // Mostra só o conteúdo da guia escolhida (um conteúdo pode servir a mais de uma guia, separadas por espaço).
  for (const conteudo of document.querySelectorAll("[data-conteudo-endomarketing]")) {
    conteudo.hidden = !conteudo.dataset.conteudoEndomarketing.split(" ").includes(guia);
  }
  // A escolha entre as diretrizes gerais e o Santander só aparece na guia Regras gerais.
  document.querySelector("[data-escolha-das-regras]").hidden = guia !== "regras";
  abrir_kbs_da_guia();
}

/**
 * Abre as KBs da guia aberta: a empresa escolhida (Base de Conhecimento) ou o grupo de regras (Regras gerais). Na
 * guia do material, e sem empresa escolhida, não há KB a abrir.
 *
 * Recebe: nada. Devolve: nada.
 */
function abrir_kbs_da_guia() {
  if (!estado_do_endomarketing.empresa_id) {
    return;
  }
  if (estado_do_endomarketing.guia === "base") {
    abrir_kbs_do_dono(estado_do_endomarketing.empresa_id);
  } else if (estado_do_endomarketing.guia === "regras") {
    abrir_kbs_do_dono(estado_do_endomarketing.dono_das_regras);
  }
}

/**
 * Na guia Regras gerais, troca entre as diretrizes gerais e as do Santander (os dois botões ficam marcados certo).
 *
 * Recebe: dono — "GERAL" ou "SANTANDER". Devolve: nada.
 */
function escolher_grupo_das_regras(dono) {
  estado_do_endomarketing.dono_das_regras = dono;
  for (const botao of document.querySelectorAll("[data-dono-das-regras]")) {
    const e_o_escolhido = botao.dataset.donoDasRegras === dono;
    botao.classList.toggle("filtro-rapido-ativo", e_o_escolhido);
    botao.setAttribute("aria-pressed", String(e_o_escolhido));
  }
  abrir_kbs_do_dono(dono);
}

/**
 * Diz qual guia o endereço pede (?aba=base, ?aba=regras ou ?aba=material); se não pede nenhuma que exista, a primeira.
 *
 * Recebe: nada. Devolve: o nome da guia. Exemplo: "banco_endomarketing.html?aba=material" → "material".
 */
function guia_do_endomarketing_no_endereco() {
  // O valor de ?aba= (null quando não tem).
  const pedida = new URLSearchParams(window.location.search).get("aba");
  // Uma guia que existe: é ela.
  if (GUIAS_DO_ENDOMARKETING.includes(pedida)) {
    return pedida;
  }
  // Nada, ou um nome que não existe: a primeira guia.
  return GUIAS_DO_ENDOMARKETING[0];
}

/**
 * Escreve um valor no endereço, sem recarregar a página: o F5 e o "Voltar" continuam na mesma empresa e guia.
 *
 * Recebe: chave — "aba" ou "empresa"; valor. Devolve: nada.
 * Exemplo: na Aurora, clicar em "Material para Comunicação" deixa "?empresa=EMP001&aba=material".
 */
function escrever_no_endereco_do_endomarketing(chave, valor) {
  // O endereço atual, para trocar só esta chave.
  const endereco = new URL(window.location.href);
  endereco.searchParams.set(chave, valor);
  // replaceState troca o endereço mostrado sem recarregar a página nem criar um passo a mais no "Voltar".
  window.history.replaceState(null, "", endereco.toString());
}

/**
 * "Trocar empresa": a busca e a lista voltam ao topo, com o cursor na busca. O que está embaixo continua sendo da
 * empresa escolhida até a pessoa clicar em outra.
 *
 * Recebe: nada. Devolve: nada.
 */
function trocar_de_empresa() {
  estado_do_endomarketing.trocando_empresa = true;
  mostrar_faixa_da_empresa();
  document.querySelector("[data-busca-endomarketing]").focus();
}

// ===== 2. A empresa aberta =====

/**
 * Abre uma empresa: busca os dados dela e monta o kit, as sugestões, o formulário e a lista de materiais.
 *
 * Recebe: empresa_id — ex.: "EMP001". Devolve: nada (espera a resposta do servidor).
 */
async function abrir_empresa_do_endomarketing(empresa_id) {
  estado_do_endomarketing.empresa_id = empresa_id;
  // A escolha terminou: o topo se recolhe no nome da empresa.
  estado_do_endomarketing.trocando_empresa = false;
  // A empresa fica no endereço (o F5 volta nela, na mesma guia).
  escrever_no_endereco_do_endomarketing("empresa", empresa_id);
  // Começar outra empresa limpa o que era da anterior (o kit em uso dela também sai, até o desta chegar).
  estado_do_endomarketing.inclusao_do_kit = null;
  estado_do_endomarketing.filtro = "todos";
  esconder_aviso_do_endomarketing();
  esconder_kit_em_uso();
  fechar_rascunho();
  mostrar_carteira_do_endomarketing();
  // As KBs da guia aberta: as da empresa (Base de Conhecimento) ou as regras gerais (js/banco_beneficios.js).
  abrir_kbs_da_guia();
  const resposta = await pedir_a_api_do_endomarketing(endereco_da_empresa("/endomarketing"), {});
  // Outra empresa foi aberta enquanto esta carregava: não desenha a antiga por cima.
  if (estado_do_endomarketing.empresa_id !== empresa_id) {
    return;
  }
  // Erro (ex.: empresa que não existe): avisa e não mostra a área.
  if (!resposta.ok) {
    mostrar_aviso_do_endomarketing("Não foi possível abrir a empresa: " + texto_do_erro_do_endomarketing(resposta.dados.detail));
    return;
  }
  estado_do_endomarketing.dados = resposta.dados;
  // O nome da empresa (no topo) e o kit em uso (ele chega sozinho, sem segurar o resto da tela).
  document.querySelector("[data-nome-da-empresa]").textContent = resposta.dados.empresa.nome;
  mostrar_kit_em_uso();
  // As sugestões e as quatro escolhas.
  mostrar_sugestoes();
  montar_opcoes_de_tipo();
  montar_opcoes_de_canal();
  montar_opcoes_de_beneficio();
  document.querySelector("[data-destaque]").value = "";
  atualizar_aviso_da_inclusao();
  // Os materiais da empresa.
  montar_filtros_de_situacao();
  montar_lista_de_materiais();
  document.querySelector("[data-area-da-empresa]").hidden = false;
}

/**
 * Busca de novo os dados da empresa aberta depois de uma ação (gerar, publicar, descartar, retirar) e atualiza as
 * sugestões, o kit, a lista de materiais e a carteira. As escolhas do formulário ficam como estão.
 *
 * Recebe: nada. Devolve: nada.
 */
async function recarregar_empresa_aberta() {
  const empresa_id = estado_do_endomarketing.empresa_id;
  const resposta = await pedir_a_api_do_endomarketing(endereco_da_empresa("/endomarketing"), {});
  // Falhou, ou outra empresa foi aberta no meio: deixa como está.
  if (!resposta.ok || estado_do_endomarketing.empresa_id !== empresa_id) {
    return;
  }
  estado_do_endomarketing.dados = resposta.dados;
  mostrar_kit_em_uso();
  mostrar_sugestoes();
  montar_filtros_de_situacao();
  montar_lista_de_materiais();
  // Os números da carteira (rascunhos e publicados) mudaram.
  await carregar_carteira_do_endomarketing();
}

/**
 * Uma KB da empresa foi publicada, retirada ou renovada, e o servidor já a aplicou: o catálogo do agente e o kit
 * podem ter mudado. Busca os dados da empresa de novo, remonta os benefícios da escolha 3 (mantendo marcados os que
 * continuam no catálogo) e redesenha a arte do rascunho aberto com o kit de agora.
 *
 * Recebe: evento — o "kbs-aplicadas" (detail.empresa_id). Devolve: nada.
 */
async function atualizar_catalogo_depois_de_aplicar(evento) {
  // Aplicada em outra empresa (a pessoa trocou no meio): não é desta.
  if (evento.detail.empresa_id !== estado_do_endomarketing.empresa_id) {
    return;
  }
  const marcados_antes = beneficios_marcados();
  // O endereço do logo não muda quando a KB troca a imagem: o logo guardado para a arte é esquecido, antes e depois,
  // e o próximo desenho busca o de agora (js/arte_do_material.js).
  esquecer_logo_do_kit();
  await recarregar_empresa_aberta();
  esquecer_logo_do_kit();
  montar_opcoes_de_beneficio();
  // Marca de novo os que a pessoa já tinha escolhido e continuam no catálogo.
  for (const caixa of document.querySelectorAll("input[name='beneficio-material']")) {
    caixa.checked = marcados_antes.includes(caixa.value);
  }
  // Com um rascunho aberto, a arte que vai junto na publicação passa a usar o kit novo.
  if (estado_do_endomarketing.rascunho) {
    mostrar_kit_visual_do_rascunho();
    desenhar_arte_do_rascunho();
  }
}

/**
 * Esquece o logo que a arte guardou para o kit da empresa aberta (sem logo no kit, não há o que esquecer).
 *
 * Recebe: nada. Devolve: nada.
 */
function esquecer_logo_do_kit() {
  // Os dados da empresa ainda não chegaram: nenhum logo foi guardado
  if (!estado_do_endomarketing.dados) {
    return;
  }
  const endereco = estado_do_endomarketing.dados.kit.endereco_do_logo;
  if (endereco) {
    esquecer_logo_guardado(endereco);
  }
}

// ===== 2.1 O kit em uso (só leitura) =====

/**
 * Esconde o "Kit em uso" (ao trocar de empresa, até o kit da nova chegar).
 *
 * Recebe: nada. Devolve: nada.
 */
function esconder_kit_em_uso() {
  estado_do_endomarketing.kit_em_uso = null;
  document.querySelector("[data-kit-em-uso]").hidden = true;
}

/**
 * Mostra o "Kit em uso", só para ler: o kit que a arte usa agora (o próprio da empresa ou o padrão), com as cores e o
 * logo, e o link para a KB do kit (GET /api/banco/empresas/{id}/kit_em_uso).
 *
 * Recebe: nada (usa a empresa aberta). Devolve: nada. Sem a rota (servidor antigo) ou com erro, o bloco fica
 * escondido: a tela nunca mostra um kit que não veio do servidor.
 */
async function mostrar_kit_em_uso() {
  const empresa_id = estado_do_endomarketing.empresa_id;
  // Cada pedido ganha um número: só a resposta do último é desenhada (dois pedidos juntos ou troca de empresa)
  estado_do_endomarketing.pedido_do_kit = estado_do_endomarketing.pedido_do_kit + 1;
  const este_pedido = estado_do_endomarketing.pedido_do_kit;
  const resposta = await pedir_a_api_do_endomarketing(endereco_da_empresa("/kit_em_uso"), {});
  // Chegou atrasada: outro pedido saiu depois deste, ou a pessoa abriu outra empresa.
  if (este_pedido !== estado_do_endomarketing.pedido_do_kit || estado_do_endomarketing.empresa_id !== empresa_id) {
    return;
  }
  // Sem o kit (rota que não existe ou erro): o bloco não aparece.
  if (!resposta.ok) {
    esconder_kit_em_uso();
    return;
  }
  estado_do_endomarketing.kit_em_uso = resposta.dados;
  preencher_kit_em_uso(resposta.dados);
  document.querySelector("[data-kit-em-uso]").hidden = false;
}

/**
 * Preenche o "Kit em uso" com o kit do servidor. Exemplo: "Kit em uso: próprio da Aurora Alimentos", as amostras
 * verde e verde-escuro, o logo e "#1f7a4d · #155535 · com o logo · KB v3".
 *
 * Recebe: kit — { escolhido, nome, cores, tem_logo, endereco_do_logo, kb_id, kb_versao }. Devolve: nada.
 */
function preencher_kit_em_uso(kit) {
  // O nome: "próprio da <empresa>" ou o nome do padrão, como o servidor manda (ex.: "Padrão Santander").
  let nome = kit.nome;
  if (kit.escolhido === "proprio") {
    nome = "próprio da " + estado_do_endomarketing.dados.empresa.nome;
  }
  document.querySelector("[data-kit-em-uso-nome]").textContent = "Kit em uso: " + nome;
  // As amostras da faixa e do rodapé (as cores que mudam de um kit para outro) e o texto delas.
  const cores = cores_do_kit_em_uso(kit.cores);
  preencher_amostras_de_cor(document.querySelector("[data-kit-em-uso-cores]"), cores);
  document.querySelector("[data-kit-em-uso-detalhe]").textContent = detalhe_do_kit_em_uso(kit, cores);
  // O logo em uso (só no kit próprio com logo). O "?momento=" faz o navegador buscar o logo de agora, e não um
  // guardado de antes (o logo muda quando outra versão da KB é publicada).
  const imagem = document.querySelector("[data-kit-em-uso-logo]");
  if (kit.tem_logo && kit.endereco_do_logo) {
    imagem.src = kit.endereco_do_logo + "?momento=" + Date.now();
    imagem.hidden = false;
  } else {
    imagem.removeAttribute("src");
    imagem.hidden = true;
  }
  // O link, aberto numa aba nova, leva à Base de Conhecimento da empresa (o clique normal é o ir_para_a_kb_do_kit).
  document.querySelector("[data-editar-kit-na-kb]").href = "banco_endomarketing.html?empresa=" +
    encodeURIComponent(estado_do_endomarketing.empresa_id) + "&aba=base";
}

/**
 * As cores da faixa e do rodapé do kit em uso, na ordem, só as que estão no formato #rrggbb.
 *
 * Recebe: cores — o objeto do servidor (cor_principal, cor_escura, cor_fundo...), ou nada. Devolve: a lista.
 * Exemplo: { cor_principal: "#1f7a4d", cor_escura: "#155535", cor_fundo: "#ffffff" } → ["#1f7a4d", "#155535"].
 */
function cores_do_kit_em_uso(cores) {
  const lista = [];
  // Resposta sem as cores: nenhuma amostra.
  if (!cores) {
    return lista;
  }
  for (const chave of ["cor_principal", "cor_escura"]) {
    // COR_EM_HEXADECIMAL vem do js/kit_da_marca.js (a mesma regra da trava).
    if (COR_EM_HEXADECIMAL.test(cores[chave] || "")) {
      lista.push(cores[chave]);
    }
  }
  return lista;
}

/**
 * A linha embaixo do nome do kit em uso: as cores, o logo (ou a falta dele) e a versão da KB.
 *
 * Recebe: kit; cores — as que viraram amostra. Devolve: o texto. Exemplo: "#d62839 · #9e1b32 · sem KB de kit
 * publicada".
 */
function detalhe_do_kit_em_uso(kit, cores) {
  const partes = [];
  // As cores escritas, na ordem das amostras.
  if (cores.length > 0) {
    partes.push(cores.join(" · "));
  }
  // O logo no kit próprio; no padrão, de onde vem a escolha.
  if (kit.escolhido === "proprio" && kit.tem_logo) {
    partes.push("com o logo");
  } else if (kit.escolhido === "proprio") {
    partes.push("sem logo: a arte leva o nome da empresa");
  } else if (!kit.kb_id) {
    partes.push("sem KB de kit publicada");
  } else {
    partes.push("escolhido na KB do kit");
  }
  // A versão publicada da KB que vale agora.
  if (kit.kb_versao) {
    partes.push("KB v" + kit.kb_versao);
  }
  return partes.join(" · ");
}

/**
 * "Editar na KB →": abre a KB do kit na janela dela, por cima da guia (ao fechar, a pessoa continua no material).
 * Sem KB de kit publicada, leva à guia Base de Conhecimento, onde a KB é criada ou publicada.
 *
 * Recebe: evento — o clique no link. Devolve: nada.
 */
async function ir_para_a_kb_do_kit(evento) {
  // Com Ctrl, Shift ou a tecla de comando do Mac, o navegador abre o endereço numa aba nova, como em qualquer link.
  if (evento.ctrlKey || evento.shiftKey || evento.metaKey) {
    return;
  }
  // O clique normal fica nesta página (o endereço do link é só para a aba nova).
  evento.preventDefault();
  const kit = estado_do_endomarketing.kit_em_uso;
  if (kit && kit.kb_id) {
    // A janela da KB precisa dos tipos e dos donos, carregados uma vez só (js/banco_beneficios.js).
    const preparou = await preparar_modelos_das_kbs();
    if (preparou) {
      abrir_kb(kit.kb_id, null);
    }
    return;
  }
  trocar_guia_do_endomarketing("base");
  escrever_no_endereco_do_endomarketing("aba", "base");
}

// ===== 3. Sugestões para agora =====

/**
 * Um cartão de sugestão: ícone, sobretítulo, título, texto e o botão.
 *
 * Recebe: icone; sobretitulo; titulo; texto; rotulo_do_botao; ao_clicar — a função do botão. Devolve: o cartão.
 */
function cartao_de_sugestao(icone, sobretitulo, titulo, texto, rotulo_do_botao, ao_clicar) {
  const cartao = criar_elemento_do_endomarketing("article", "cartao cartao-sugestao", "");
  // O ícone, numa bolinha.
  const bolinha = criar_elemento_do_endomarketing("span", "envio-icone", "");
  bolinha.append(criar_icone(icone));
  // Os textos.
  const textos = criar_elemento_do_endomarketing("div", "cartao-sugestao-textos", "");
  textos.append(criar_elemento_do_endomarketing("span", "sobretitulo", sobretitulo));
  textos.append(criar_elemento_do_endomarketing("h3", "cartao-sugestao-titulo", titulo));
  textos.append(criar_elemento_do_endomarketing("p", "cartao-sugestao-texto", texto));
  // O botão que prepara o formulário.
  const botao = criar_elemento_do_endomarketing("button", "botao botao-contorno botao-pequeno", rotulo_do_botao);
  botao.type = "button";
  botao.addEventListener("click", ao_clicar);
  cartao.append(bolinha, textos, botao);
  return cartao;
}

/**
 * Mostra as sugestões da empresa: quantos ainda não têm conta (lembrete) e as inclusões sem kit de boas-vindas.
 * Os números são sempre agregados (o total da empresa), nunca quem é quem.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_sugestoes() {
  const sugestoes = estado_do_endomarketing.dados.sugestoes;
  const area = document.querySelector("[data-sugestoes]");
  // Esvazia antes de montar.
  area.replaceChildren();
  // 1. Funcionários sem conta informada pelo banco (aguardam o retorno do arquivo de contas; ADR-123): sugere o lembrete.
  if (sugestoes.sem_conta && sugestoes.sem_conta.quantidade > 0) {
    // Singular com 1 pessoa; plural a partir de 2.
    let frase_sem_conta = " funcionários cadastrados ainda sem conta informada pelo banco";
    if (sugestoes.sem_conta.quantidade === 1) {
      frase_sem_conta = " funcionário cadastrado ainda sem conta informada pelo banco";
    }
    area.append(cartao_de_sugestao("icone-cartao", "Abertura das contas",
      sugestoes.sem_conta.texto + frase_sem_conta,
      "Um lembrete curto, com o passo a passo, costuma resolver. A empresa divulga para toda a equipe.",
      "Criar lembrete para abrir a conta",
      function () {
        escolher_tipo_do_material("lembrete_conta");
      }));
  }
  // 2. Cada inclusão que ainda não recebeu o kit de boas-vindas: o kit fica ligado a ela.
  for (const inclusao of sugestoes.kits) {
    area.append(cartao_de_sugestao("icone-kit", "Novos funcionários",
      inclusao.funcionarios_novos + " pessoas chegaram (inclusão " + inclusao.arquivo + ")",
      "O kit de boas-vindas explica a conta salário e os primeiros passos, e fica ligado a esta inclusão.",
      "Criar kit de boas-vindas",
      function () {
        estado_do_endomarketing.inclusao_do_kit = inclusao;
        escolher_tipo_do_material("kit_boas_vindas");
      }));
  }
  // Sem nenhuma sugestão, a área some.
  area.hidden = area.children.length === 0;
}

// ===== 4. As quatro escolhas =====

/**
 * Monta os cartões de tipo de material (escolha 1), com os tipos que a API aceita. O primeiro vem marcado.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_opcoes_de_tipo() {
  const area = document.querySelector("[data-opcoes-tipo]");
  area.replaceChildren();
  for (const tipo of estado_do_endomarketing.dados.tipos) {
    const rotulo = criar_elemento_do_endomarketing("label", "opcao-material", "");
    // A bolinha de marcar (escondida pelo CSS: o cartão inteiro mostra a escolha).
    const opcao = document.createElement("input");
    opcao.type = "radio";
    opcao.name = "tipo-material";
    opcao.value = tipo.chave;
    opcao.checked = area.children.length === 0;
    // Trocar o tipo mostra ou esconde o aviso da inclusão ligada ao kit.
    opcao.addEventListener("change", atualizar_aviso_da_inclusao);
    // O ícone do tipo (tipo novo: o do documento).
    let icone = ICONE_DO_TIPO[tipo.chave];
    if (!icone) {
      icone = "icone-documento";
    }
    rotulo.append(opcao, criar_icone(icone), criar_elemento_do_endomarketing("strong", "", tipo.nome));
    // A frase curta embaixo do nome, quando houver.
    if (FRASE_DO_TIPO[tipo.chave]) {
      rotulo.append(criar_elemento_do_endomarketing("span", "", FRASE_DO_TIPO[tipo.chave]));
    }
    // O lembrete vai para toda a equipe: a empresa divulga para todos (quem abriu ela vê em Acompanhar cadastros).
    if (tipo.chave === "lembrete_conta") {
      rotulo.title = "Vai para toda a equipe. Quem ainda não abriu a conta aparece para a empresa em Acompanhar cadastros.";
    }
    area.append(rotulo);
  }
}

/**
 * Monta as opções de canal (escolha 2). O WhatsApp diz quantos trechos cabem. O primeiro vem marcado.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_opcoes_de_canal() {
  const area = document.querySelector("[data-opcoes-canal]");
  area.replaceChildren();
  for (const canal of estado_do_endomarketing.dados.canais) {
    const rotulo = criar_elemento_do_endomarketing("label", "opcao-canal", "");
    const opcao = document.createElement("input");
    opcao.type = "radio";
    opcao.name = "canal-material";
    opcao.value = canal.chave;
    opcao.checked = area.children.length === 0;
    // O nome do canal e, se ele tiver limite, quantos trechos cabem.
    let texto = canal.nome;
    if (canal.maximo_de_blocos) {
      texto = texto + " (até " + canal.maximo_de_blocos + " trechos)";
    }
    rotulo.append(opcao, criar_elemento_do_endomarketing("span", "", texto));
    area.append(rotulo);
  }
}

/**
 * Monta as caixas de marcar dos benefícios do catálogo da empresa (escolha 3). Nenhuma vem marcada: o especialista
 * escolhe o que entra.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_opcoes_de_beneficio() {
  const area = document.querySelector("[data-opcoes-beneficio]");
  area.replaceChildren();
  for (const beneficio of estado_do_endomarketing.dados.beneficios) {
    const rotulo = criar_elemento_do_endomarketing("label", "opcao-canal", "");
    // O resumo do benefício aparece ao parar o mouse em cima.
    rotulo.title = beneficio.resumo;
    const caixa = document.createElement("input");
    caixa.type = "checkbox";
    caixa.name = "beneficio-material";
    caixa.value = beneficio.titulo;
    // Marcar um benefício tira o aviso de "marque pelo menos um".
    caixa.addEventListener("change", function () {
      document.querySelector("[data-erro-beneficios]").hidden = true;
    });
    rotulo.append(caixa, criar_elemento_do_endomarketing("span", "", beneficio.titulo));
    area.append(rotulo);
  }
  // Sem catálogo, o aviso de onde publicá-lo.
  document.querySelector("[data-sem-beneficios]").hidden = estado_do_endomarketing.dados.beneficios.length > 0;
  document.querySelector("[data-erro-beneficios]").hidden = true;
}

/**
 * O valor marcado num grupo de opções (radio). Exemplo: valor_marcado("canal-material") → "email".
 *
 * Recebe: nome — o name do grupo. Devolve: o value da opção marcada, ou null.
 */
function valor_marcado(nome) {
  const marcada = document.querySelector("input[name='" + nome + "']:checked");
  // Nenhuma marcada: null.
  if (!marcada) {
    return null;
  }
  return marcada.value;
}

/**
 * Os benefícios marcados na escolha 3, pelo título. Exemplo: ["Conta salário", "Crédito consignado"].
 *
 * Recebe: nada. Devolve: a lista.
 */
function beneficios_marcados() {
  const marcados = [];
  for (const caixa of document.querySelectorAll("input[name='beneficio-material']:checked")) {
    marcados.push(caixa.value);
  }
  return marcados;
}

/**
 * Marca um tipo de material e leva a tela até o formulário (usado pelas sugestões).
 *
 * Recebe: tipo — a chave do tipo (ex.: "lembrete_conta"). Devolve: nada.
 */
function escolher_tipo_do_material(tipo) {
  const opcao = document.querySelector("input[name='tipo-material'][value='" + tipo + "']");
  // Tipo que a API não oferece: não marca nada.
  if (opcao) {
    opcao.checked = true;
  }
  atualizar_aviso_da_inclusao();
  document.querySelector("[data-opcoes-tipo]").scrollIntoView({ behavior: "smooth", block: "center" });
}

/**
 * Mostra o aviso "Kit ligado à inclusão ..." quando há uma inclusão escolhida E o tipo marcado é o kit.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_aviso_da_inclusao() {
  const inclusao = estado_do_endomarketing.inclusao_do_kit;
  const aviso = document.querySelector("[data-inclusao-do-kit]");
  // Só o kit de boas-vindas fica ligado a uma inclusão.
  const mostrar = inclusao !== null && valor_marcado("tipo-material") === "kit_boas_vindas";
  aviso.hidden = !mostrar;
  if (mostrar) {
    document.querySelector("[data-inclusao-do-kit-texto]").textContent = "Este kit fica ligado à inclusão " +
      inclusao.arquivo + " (" + inclusao.funcionarios_novos + " pessoas).";
  }
}

/**
 * Desfaz a ligação do kit com a inclusão (o kit sai sem inclusão).
 *
 * Recebe: nada. Devolve: nada.
 */
function desligar_inclusao_do_kit() {
  estado_do_endomarketing.inclusao_do_kit = null;
  atualizar_aviso_da_inclusao();
}

// ===== 5. Gerar e mostrar o rascunho =====

/**
 * Mostra um aviso do agente acima do rascunho (ex.: algo pedido que o catálogo não traz).
 *
 * Recebe: texto; tipo — "alerta" (laranja) ou "info" (azul). Devolve: nada.
 */
function mostrar_aviso_do_rascunho(texto, tipo) {
  const aviso = criar_elemento_do_endomarketing("p", "aviso-material aviso-material-" + tipo, texto);
  document.querySelector("[data-avisos-material]").append(aviso);
}

/**
 * Pede o rascunho ao Agente de Endomarketing com as quatro escolhas e o mostra na tela.
 *
 * Recebe: nada. Devolve: nada.
 * Regra da tela (e da API): pelo menos um benefício. O processamento_id só vai no kit de boas-vindas ligado a uma
 * inclusão (vem da sugestão).
 */
async function gerar_rascunho_do_banco() {
  esconder_aviso_do_endomarketing();
  const beneficios = beneficios_marcados();
  // Nenhum benefício marcado: avisa ao lado das caixas e não chama a IA.
  if (beneficios.length === 0) {
    const erro = document.querySelector("[data-erro-beneficios]");
    erro.hidden = false;
    erro.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  const tipo = valor_marcado("tipo-material");
  // A inclusão só entra quando o tipo é mesmo o kit de boas-vindas.
  let processamento_id = null;
  if (tipo === "kit_boas_vindas" && estado_do_endomarketing.inclusao_do_kit) {
    processamento_id = estado_do_endomarketing.inclusao_do_kit.processamento_id;
  }
  const pedido = {
    tipo: tipo,
    canal: valor_marcado("canal-material"),
    beneficios: beneficios,
    destaque: document.querySelector("[data-destaque]").value.trim(),
    processamento_id: processamento_id,
  };
  // Abre a área do rascunho vazia, com a IA "escrevendo".
  const secao = document.querySelector("[data-rascunho]");
  document.querySelector("[data-avisos-material]").replaceChildren();
  document.querySelector("[data-corpo-material]").replaceChildren();
  // O joinha do rascunho anterior sai junto com o texto dele (ADR-151)
  document.querySelector("[data-opiniao-do-rascunho]").replaceChildren();
  document.querySelector("[data-titulo-material]").textContent = "Gerando o rascunho...";
  document.querySelector("[data-resumo-material]").textContent = "";
  document.querySelector("[data-bloco-arte]").hidden = true;
  // A arte anterior deixa de valer: o canvas só diz "pronto" de novo quando a arte do rascunho novo for desenhada.
  delete document.querySelector("[data-previa-arte]").dataset.moldeDesenhado;
  document.querySelector("[data-erro-rascunho]").hidden = true;
  alternar_botoes_do_rascunho(false);
  estado_do_endomarketing.rascunho = null;
  secao.hidden = false;
  secao.scrollIntoView({ behavior: "smooth", block: "start" });
  const escrevendo = document.querySelector("[data-ia-escrevendo]");
  escrevendo.hidden = false;
  // Desliga o botão enquanto a IA escreve (um clique duplo não gera dois rascunhos).
  const botao_gerar = document.querySelector("[data-gerar-material]");
  botao_gerar.disabled = true;
  const resposta = await postar_json_do_endomarketing(endereco_da_empresa("/endomarketing/gerar"), pedido);
  botao_gerar.disabled = false;
  escrevendo.hidden = true;
  // Pedido recusado pela API (ex.: benefício fora do catálogo): mostra o motivo.
  if (!resposta.ok) {
    document.querySelector("[data-titulo-material]").textContent = "O rascunho não foi gerado";
    mostrar_aviso_do_rascunho(texto_do_erro_do_endomarketing(resposta.dados.detail), "alerta");
    return;
  }
  const resultado = resposta.dados;
  // Sem rascunho (recusado, sem evidência no catálogo, falha, IA indisponível): a mensagem e as observações.
  if (resultado.situacao !== "GERADO" || !resultado.material) {
    document.querySelector("[data-titulo-material]").textContent = "O rascunho não foi gerado";
    mostrar_aviso_do_rascunho(resultado.mensagem, "alerta");
    for (const observacao of resultado.observacoes) {
      mostrar_aviso_do_rascunho(observacao, "alerta");
    }
    return;
  }
  // Gerado: mostra o rascunho e a arte, e atualiza a lista (ele já aparece lá como Rascunho).
  abrir_rascunho(resultado.material, resultado.observacoes);
  await recarregar_empresa_aberta();
}

/**
 * Um bloco do material: o texto e, embaixo, as fontes no catálogo.
 *
 * Recebe: bloco — { texto, fontes }. Devolve: o elemento pronto.
 */
function montar_bloco_do_material(bloco) {
  const elemento = criar_elemento_do_endomarketing("div", "trecho-material", "");
  elemento.append(criar_elemento_do_endomarketing("p", "", bloco.texto));
  elemento.append(criar_elemento_do_endomarketing("span", "fonte-trecho", "Fonte: " + bloco.fontes.join("; ")));
  return elemento;
}

/**
 * Abre um material em RASCUNHO na área do rascunho: título, resumo, observações, blocos e a arte.
 *
 * Recebe: material — visão do banco; observacoes — os avisos do agente (lista, pode ser vazia). Devolve: nada.
 */
function abrir_rascunho(material, observacoes) {
  estado_do_endomarketing.rascunho = material;
  const secao = document.querySelector("[data-rascunho]");
  secao.hidden = false;
  document.querySelector("[data-titulo-material]").textContent = material.titulo;
  // O resumo: tipo, canal, os benefícios escolhidos e quem criou.
  document.querySelector("[data-resumo-material]").textContent = material.nome_do_tipo + " · " + material.nome_do_canal +
    " · benefícios: " + material.beneficios.join(", ") + " · criado por " + material.criado_por + " em " +
    data_e_hora_do_material(material.criado_em);
  // As observações do agente (o que ficou de fora e por quê).
  document.querySelector("[data-avisos-material]").replaceChildren();
  for (const observacao of observacoes) {
    mostrar_aviso_do_rascunho(observacao, "alerta");
  }
  // O texto, bloco a bloco, com as fontes.
  const corpo = document.querySelector("[data-corpo-material]");
  corpo.replaceChildren();
  for (const bloco of material.blocos) {
    corpo.append(montar_bloco_do_material(bloco));
  }
  // Embaixo do texto, o joinha do especialista sobre o que o agente escreveu (js/opiniao_dos_agentes.js, ADR-151)
  mostrar_opiniao_do_material(document.querySelector("[data-opiniao-do-rascunho]"), estado_do_endomarketing.empresa_id,
    material);
  document.querySelector("[data-erro-rascunho]").hidden = true;
  alternar_botoes_do_rascunho(true);
  // A arte tem o formato do canal do material (outro rascunho aberto, de outro canal, troca o formato).
  estado_do_endomarketing.molde = molde_do_canal(material.canal);
  mostrar_formato_da_arte();
  mostrar_kit_visual_do_rascunho();
  document.querySelector("[data-bloco-arte]").hidden = false;
  desenhar_arte_do_rascunho();
}

/**
 * Escreve, em cima da arte do rascunho, qual kit ela usa. Exemplo: "Kit visual: Kit da Aurora Alimentos · definido
 * pelo banco para Aurora Alimentos".
 *
 * Recebe: nada (usa o kit da empresa aberta). Devolve: nada.
 */
function mostrar_kit_visual_do_rascunho() {
  document.querySelector("[data-kit-visual]").textContent = "Kit visual: " + estado_do_endomarketing.dados.kit.nome +
    " · definido pelo banco para " + estado_do_endomarketing.dados.empresa.nome;
}

/**
 * Escreve, ao lado da arte, o formato do canal do rascunho, e o passa à prévia (o CSS mostra cada formato num
 * tamanho que cabe na tela). Exemplo: "Banner para e-mail · 1200 × 400 px".
 *
 * Recebe: nada (usa o molde do rascunho aberto). Devolve: nada.
 */
function mostrar_formato_da_arte() {
  // O nome e o tamanho do formato, no selo ao lado do título "Arte que vai junto".
  document.querySelector("[data-formato-da-arte]").textContent = descricao_do_molde(estado_do_endomarketing.molde);
  // A prévia guarda o formato em data-formato (o CSS usa para o tamanho dela na tela).
  document.querySelector("[data-previa-arte]").dataset.formato = estado_do_endomarketing.molde;
}

/**
 * Liga ou desliga os botões "Descartar" e "Publicar" (desligados enquanto a IA escreve ou o pedido está a caminho).
 *
 * Recebe: ligados — true ou false. Devolve: nada.
 */
function alternar_botoes_do_rascunho(ligados) {
  document.querySelector("[data-descartar-material]").disabled = !ligados;
  document.querySelector("[data-publicar-material]").disabled = !ligados;
}

/**
 * Fecha a área do rascunho (depois de publicar ou descartar, ou ao trocar de empresa).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_rascunho() {
  estado_do_endomarketing.rascunho = null;
  document.querySelector("[data-rascunho]").hidden = true;
}

// ===== 6. A arte =====

/**
 * Desenha a arte do rascunho aberto no molde do canal dele, com o kit da empresa.
 *
 * Recebe: nada. Devolve: nada (o desenho termina sozinho, depois que as letras e o logo carregam).
 */
function desenhar_arte_do_rascunho() {
  // Sem rascunho aberto, nada a desenhar.
  if (!estado_do_endomarketing.rascunho) {
    return;
  }
  desenhar_arte_do_material(document.querySelector("[data-previa-arte]"), estado_do_endomarketing.rascunho,
    estado_do_endomarketing.dados.kit, estado_do_endomarketing.molde);
}

/**
 * Transforma o desenho do canvas num arquivo PNG.
 *
 * Recebe: canvas. Devolve: uma "promessa" com o arquivo (Blob), ou null se o navegador não conseguir.
 */
function arte_em_png(canvas) {
  return new Promise(function (terminar) {
    // toBlob transforma o desenho num arquivo de imagem e chama a função quando termina.
    canvas.toBlob(function (arquivo) {
      terminar(arquivo);
    }, "image/png");
  });
}

// ===== 7. Publicar e descartar =====

/**
 * Publica o rascunho para a empresa, com UMA arte: a do canal do rascunho (PNG no campo "arte" de um envio multipart).
 *
 * Recebe: nada. Devolve: nada.
 */
async function publicar_rascunho() {
  const material = estado_do_endomarketing.rascunho;
  // Sem rascunho aberto: nada a publicar.
  if (!material) {
    return;
  }
  alternar_botoes_do_rascunho(false);
  const canvas = document.querySelector("[data-previa-arte]");
  // Espera o desenho ficar pronto no molde do canal (ele espera as letras e o logo).
  await esperar_arte_desenhada(canvas);
  // O formulário do envio: a arte vai como arquivo.
  const formulario = new FormData();
  const arte = await arte_em_png(canvas);
  if (arte) {
    formulario.append("arte", arte, "arte_" + estado_do_endomarketing.molde + ".png");
  }
  // Sem "Content-Type": o navegador monta o multipart sozinho, com a separação certa.
  const resposta = await pedir_a_api_do_endomarketing(endereco_do_material(material.material_id, "/publicar"),
    { method: "POST", body: formulario });
  // Recusado: mostra o motivo embaixo dos botões e deixa tentar de novo.
  if (!resposta.ok) {
    const erro = document.querySelector("[data-erro-rascunho]");
    erro.textContent = "Não publicado: " + texto_do_erro_do_endomarketing(resposta.dados.detail);
    erro.hidden = false;
    alternar_botoes_do_rascunho(true);
    return;
  }
  fechar_rascunho();
  await recarregar_empresa_aberta();
  // O aviso diz onde a empresa encontra o material, com ou sem arte.
  let recado = "Publicado para a " + estado_do_endomarketing.dados.empresa.nome + ": a empresa já vê \"" +
    resposta.dados.titulo + "\" em Materiais de endomarketing";
  if (!arte) {
    recado = recado + " (sem a arte: o navegador não conseguiu gerar a imagem)";
  }
  mostrar_aviso_do_endomarketing(recado + ".");
  document.getElementById("materiais").scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Espera a arte do rascunho terminar de ser desenhada no molde do canal (até 5 segundos).
 *
 * Recebe: canvas. Devolve: uma "promessa" que termina quando o desenho está pronto (ou o tempo acaba).
 */
function esperar_arte_desenhada(canvas) {
  return new Promise(function (terminar) {
    let tentativas = 0;
    // Confere a cada 100 ms se o molde desenhado já é o do canal.
    const relogio = setInterval(function () {
      tentativas = tentativas + 1;
      if (canvas.dataset.moldeDesenhado === estado_do_endomarketing.molde || tentativas >= 50) {
        clearInterval(relogio);
        terminar();
      }
    }, 100);
  });
}

/**
 * Pede a confirmação para descartar o rascunho aberto.
 *
 * Recebe: nada. Devolve: nada.
 */
function pedir_para_descartar_rascunho() {
  const material = estado_do_endomarketing.rascunho;
  // Sem rascunho aberto: nada a descartar.
  if (!material) {
    return;
  }
  pedir_confirmacao("Descartar este rascunho?",
    "\"" + material.titulo + "\" fica guardado aqui como Descartado e nunca aparece para a empresa.",
    "Descartar", async function () {
      return await mudar_situacao_do_material(material, "/descartar", "Rascunho descartado: a empresa não vê \"" +
        material.titulo + "\".");
    });
}

/**
 * Pede a confirmação para retirar um material publicado.
 *
 * Recebe: material — visão do banco, PUBLICADO. Devolve: nada.
 */
function pedir_para_retirar_material(material) {
  const nome_da_empresa = estado_do_endomarketing.dados.empresa.nome;
  pedir_confirmacao("Retirar da empresa?",
    "A " + nome_da_empresa + " deixa de ver \"" + material.titulo + "\" e não consegue mais baixar o texto e a arte. " +
    "O material continua aqui, como Retirado da empresa (ex.: quando o benefício mudou).",
    "Retirar da empresa", async function () {
      return await mudar_situacao_do_material(material, "/retirar", "Retirado: a " + nome_da_empresa +
        " não vê mais \"" + material.titulo + "\".");
    });
}

/**
 * Descarta ou retira um material na aplicação e atualiza a tela.
 *
 * Recebe: material; acao — "/descartar" ou "/retirar"; recado — o aviso de sucesso.
 * Devolve: { ok, mensagem } — em erro, a mensagem para a janela de confirmação.
 */
async function mudar_situacao_do_material(material, acao, recado) {
  const resposta = await postar_json_do_endomarketing(endereco_do_material(material.material_id, acao), {});
  // Recusado (ex.: já não está nesta situação): a janela mostra o motivo.
  if (!resposta.ok) {
    return { ok: false, mensagem: texto_do_erro_do_endomarketing(resposta.dados.detail) };
  }
  // O rascunho descartado sai da área do rascunho.
  if (estado_do_endomarketing.rascunho && estado_do_endomarketing.rascunho.material_id === material.material_id) {
    fechar_rascunho();
  }
  await recarregar_empresa_aberta();
  mostrar_aviso_do_endomarketing(recado);
  return { ok: true, mensagem: "" };
}

// ===== 8. A janela de confirmação =====

/**
 * Abre a janela de confirmação da própria página (nunca o confirm() do navegador).
 *
 * Recebe: titulo; texto; rotulo_do_botao — ex.: "Retirar da empresa"; acao — função assíncrona que devolve
 * { ok, mensagem }. Devolve: nada. A janela fecha sozinha quando a ação dá certo.
 */
function pedir_confirmacao(titulo, texto, rotulo_do_botao, acao) {
  const janela = document.getElementById("janela-confirmacao");
  janela.querySelector("[data-confirmacao-titulo]").textContent = titulo;
  janela.querySelector("[data-confirmacao-texto]").textContent = texto;
  janela.querySelector("[data-confirmar-acao]").textContent = rotulo_do_botao;
  janela.querySelector("[data-confirmar-acao]").disabled = false;
  janela.querySelector("[data-confirmacao-erro]").hidden = true;
  estado_do_endomarketing.acao_a_confirmar = acao;
  // showModal: abre por cima da página, com o fundo escurecido.
  janela.showModal();
}

/**
 * O botão de confirmar da janela: roda a ação guardada e fecha a janela (ou mostra o erro).
 *
 * Recebe: nada. Devolve: nada.
 */
async function confirmar_acao() {
  const janela = document.getElementById("janela-confirmacao");
  const acao = estado_do_endomarketing.acao_a_confirmar;
  // Nada guardado: só fecha.
  if (!acao) {
    janela.close();
    return;
  }
  // Desliga o botão para um clique duplo não repetir a ação.
  const botao = janela.querySelector("[data-confirmar-acao]");
  botao.disabled = true;
  const resultado = await acao();
  // Deu certo: fecha e esquece a ação.
  if (resultado.ok) {
    estado_do_endomarketing.acao_a_confirmar = null;
    janela.close();
    return;
  }
  // Deu errado: mostra o motivo na própria janela.
  const erro = janela.querySelector("[data-confirmacao-erro]");
  erro.textContent = resultado.mensagem;
  erro.hidden = false;
  botao.disabled = false;
}

// ===== 9. Os materiais da empresa =====

/**
 * Quantos materiais a empresa aberta tem numa situação ("todos" conta tudo).
 *
 * Recebe: situacao — ex.: "PUBLICADO". Devolve: o número.
 */
function contar_materiais_na_situacao(situacao) {
  let quantidade = 0;
  for (const material of estado_do_endomarketing.dados.materiais) {
    // "todos" conta qualquer material; as outras chaves, só os da situação.
    if (situacao === "todos" || material.status === situacao) {
      quantidade = quantidade + 1;
    }
  }
  return quantidade;
}

/**
 * Monta os filtros por situação, com a quantidade de cada uma. Situação sem nenhum material não aparece (menos
 * "Todos" e a que estiver escolhida).
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_filtros_de_situacao() {
  const area = document.querySelector("[data-filtros-situacao]");
  area.replaceChildren();
  for (const filtro of FILTROS_DE_SITUACAO) {
    const chave = filtro[0];
    const quantidade = contar_materiais_na_situacao(chave);
    const escolhido = chave === estado_do_endomarketing.filtro;
    // Situação vazia e não escolhida: não precisa de botão.
    if (quantidade === 0 && chave !== "todos" && !escolhido) {
      continue;
    }
    const botao = criar_elemento_do_endomarketing("button", "filtro-rapido", filtro[1] + " (" + quantidade + ")");
    botao.type = "button";
    botao.dataset.filtroSituacao = chave;
    botao.setAttribute("aria-pressed", String(escolhido));
    botao.classList.toggle("filtro-rapido-ativo", escolhido);
    area.append(botao);
  }
}

/**
 * Troca o filtro da lista de materiais.
 *
 * Recebe: botao — o filtro clicado. Devolve: nada.
 */
function escolher_filtro_de_situacao(botao) {
  estado_do_endomarketing.filtro = botao.dataset.filtroSituacao;
  montar_filtros_de_situacao();
  montar_lista_de_materiais();
}

/**
 * Monta a lista de materiais da empresa aberta (do mais recente ao mais antigo), respeitando o filtro.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_lista_de_materiais() {
  const lista = document.querySelector("[data-lista-materiais]");
  lista.replaceChildren();
  for (const material of estado_do_endomarketing.dados.materiais) {
    // Fora do filtro: pula.
    if (estado_do_endomarketing.filtro !== "todos" && material.status !== estado_do_endomarketing.filtro) {
      continue;
    }
    lista.append(montar_material_da_lista(material));
  }
  // Nenhum material no filtro: o aviso.
  document.querySelector("[data-sem-materiais]").hidden = lista.children.length > 0;
}

/**
 * A linha de histórico de um material. Exemplo: "Comunicado interno · E-mail · publicado por especialista.banco em
 * 28/09/2026, 09:00".
 *
 * Recebe: material. Devolve: o texto.
 */
function historico_do_material(material) {
  let historico = material.nome_do_tipo + " · " + material.nome_do_canal;
  // A última coisa que aconteceu com o material: retirado, publicado ou criado.
  if (material.status === "RETIRADO" && material.retirado_em) {
    historico = historico + " · retirado por " + material.retirado_por + " em " + data_e_hora_do_material(material.retirado_em);
  } else if (material.publicado_em) {
    historico = historico + " · publicado por " + material.publicado_por + " em " + data_e_hora_do_material(material.publicado_em);
  } else {
    historico = historico + " · criado por " + material.criado_por + " em " + data_e_hora_do_material(material.criado_em);
  }
  return historico;
}

/**
 * Um botão pequeno de ação da lista.
 *
 * Recebe: texto; ao_clicar — a função do clique. Devolve: o botão.
 */
function botao_de_acao_do_material(texto, ao_clicar) {
  const botao = criar_elemento_do_endomarketing("button", "botao botao-contorno botao-pequeno", texto);
  botao.type = "button";
  botao.addEventListener("click", ao_clicar);
  return botao;
}

/**
 * Um material na lista: ícone, título, histórico, selo da situação e as ações que valem para a situação.
 *
 * Recebe: material — visão do banco. Devolve: o elemento pronto.
 */
function montar_material_da_lista(material) {
  const cartao = criar_elemento_do_endomarketing("article", "cartao material-salvo", "");
  cartao.dataset.materialId = material.material_id;
  cartao.dataset.situacaoDoMaterial = material.status;
  // O ícone do tipo.
  const bolinha = criar_elemento_do_endomarketing("span", "envio-icone", "");
  let icone = ICONE_DO_TIPO[material.tipo];
  if (!icone) {
    icone = "icone-documento";
  }
  bolinha.append(criar_icone(icone));
  // Título e histórico.
  const textos = criar_elemento_do_endomarketing("div", "envio-textos", "");
  textos.append(criar_elemento_do_endomarketing("strong", "envio-titulo", material.titulo));
  textos.append(criar_elemento_do_endomarketing("span", "envio-arquivos", historico_do_material(material)));
  // O selo com o nome da situação, na cor dela.
  let cor = COR_DO_SELO_DA_SITUACAO[material.status];
  if (!cor) {
    cor = "selo-neutro";
  }
  const selo = criar_elemento_do_endomarketing("span", "selo selo-pequeno " + cor, material.nome_do_status);
  selo.dataset.seloDaSituacao = "";
  // As ações.
  const acoes = criar_elemento_do_endomarketing("div", "material-acoes", "");
  // Rascunho: dá para abrir de novo na área do rascunho (para publicar ou descartar).
  if (material.status === "RASCUNHO") {
    acoes.append(botao_de_acao_do_material("Abrir rascunho", function () {
      abrir_rascunho(material, []);
      document.querySelector("[data-rascunho]").scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  }
  acoes.append(botao_de_acao_do_material("Ver", function () {
    ver_material(material);
  }));
  acoes.append(botao_de_acao_do_material("Baixar texto", function () {
    baixar_texto_do_material(material);
  }));
  // A arte só existe depois de publicar (vai junto na publicação).
  if (material.tem_arte) {
    acoes.append(botao_de_acao_do_material("Baixar arte", function () {
      baixar_arte_do_material(material);
    }));
  }
  // Publicado: dá para retirar da empresa.
  if (material.status === "PUBLICADO") {
    const botao_retirar = botao_de_acao_do_material("Retirar da empresa", function () {
      pedir_para_retirar_material(material);
    });
    botao_retirar.dataset.retirarMaterial = "";
    acoes.append(botao_retirar);
  }
  cartao.append(bolinha, textos, selo, acoes);
  return cartao;
}

/**
 * Abre a janela "Ver material": o texto com as fontes, o histórico e a arte publicada (quando há).
 *
 * Recebe: material — visão do banco. Devolve: nada.
 */
function ver_material(material) {
  const janela = document.getElementById("janela-material");
  janela.querySelector("[data-janela-material-tipo]").textContent = material.nome_do_tipo + " · " + material.nome_do_canal;
  janela.querySelector("[data-janela-material-titulo]").textContent = material.titulo;
  janela.querySelector("[data-janela-material-historico]").textContent = material.nome_do_status + " · " +
    historico_do_material(material) + " · benefícios: " + material.beneficios.join(", ");
  // O texto, bloco a bloco.
  const corpo = janela.querySelector("[data-janela-material-corpo]");
  corpo.replaceChildren();
  for (const bloco of material.blocos) {
    corpo.append(montar_bloco_do_material(bloco));
  }
  // O joinha sobre o texto do agente, o mesmo do rascunho (js/opiniao_dos_agentes.js, ADR-151)
  mostrar_opiniao_do_material(janela.querySelector("[data-opiniao-da-janela-material]"),
    estado_do_endomarketing.empresa_id, material);
  // A arte publicada: a imagem vem da própria API (mesmo site).
  const imagem = janela.querySelector("[data-janela-material-arte]");
  if (material.tem_arte) {
    imagem.src = endereco_do_material(material.material_id, "/arte");
    imagem.alt = "Arte publicada de " + material.titulo;
    imagem.hidden = false;
  } else {
    imagem.removeAttribute("src");
    imagem.hidden = true;
  }
  janela.showModal();
}

/**
 * O texto do material para baixar: o título e os blocos, cada um com as fontes.
 *
 * Recebe: material. Devolve: o texto.
 */
function texto_para_baixar(material) {
  const partes = [material.titulo];
  for (const bloco of material.blocos) {
    partes.push(bloco.texto + "\n(Fonte: " + bloco.fontes.join("; ") + ")");
  }
  return partes.join("\n\n");
}

/**
 * Baixa um arquivo com o nome dado, a partir de um endereço (o navegador salva em vez de abrir).
 *
 * Recebe: endereco; nome_do_arquivo. Devolve: nada.
 */
function baixar_do_endereco(endereco, nome_do_arquivo) {
  const link = document.createElement("a");
  link.href = endereco;
  // "download": o navegador salva o arquivo com este nome.
  link.download = nome_do_arquivo;
  document.body.append(link);
  link.click();
  link.remove();
}

/**
 * Baixa o texto do material como arquivo .txt (montado aqui, a partir do título e dos blocos).
 *
 * Recebe: material. Devolve: nada.
 */
function baixar_texto_do_material(material) {
  // O arquivo de texto, em UTF-8 (acentos certos).
  const arquivo = new Blob([texto_para_baixar(material)], { type: "text/plain;charset=utf-8" });
  const endereco = URL.createObjectURL(arquivo);
  baixar_do_endereco(endereco, "material_" + material.material_id + ".txt");
  // Libera a memória do arquivo depois que o download começou.
  setTimeout(function () {
    URL.revokeObjectURL(endereco);
  }, 1000);
}

/**
 * Baixa a arte publicada do material (PNG gravado na publicação).
 *
 * Recebe: material. Devolve: nada.
 */
function baixar_arte_do_material(material) {
  baixar_do_endereco(endereco_do_material(material.material_id, "/arte"), "arte_" + material.material_id + ".png");
}

// ===== 10. Ligando tudo =====

/**
 * Liga os cliques da página (uma vez só) e abre a carteira. É chamada quando a página termina de carregar.
 *
 * Recebe: nada. Devolve: nada. Aberta como arquivo ou sem permissão, mostra o aviso de que precisa do servidor.
 */
async function preparar_endomarketing_do_banco() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    document.querySelector("[data-endomarketing-sem-servidor]").hidden = false;
    return;
  }
  // A lista de empresas: um clique numa empresa a abre (um "ouvinte" só, para a lista inteira).
  document.querySelector("[data-lista-empresas-endomarketing]").addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-abrir-empresa-endomarketing]");
    if (botao) {
      abrir_empresa_do_endomarketing(botao.dataset.abrirEmpresaEndomarketing);
    }
  });
  // A busca de empresas, a cada letra.
  document.querySelector("[data-busca-endomarketing]").addEventListener("input", function (evento) {
    estado_do_endomarketing.busca = evento.target.value.trim().toLowerCase();
    mostrar_carteira_do_endomarketing();
  });
  // Gerar, publicar, descartar e desfazer a inclusão.
  document.querySelector("[data-gerar-material]").addEventListener("click", gerar_rascunho_do_banco);
  document.querySelector("[data-publicar-material]").addEventListener("click", publicar_rascunho);
  document.querySelector("[data-descartar-material]").addEventListener("click", pedir_para_descartar_rascunho);
  document.querySelector("[data-desligar-inclusao]").addEventListener("click", desligar_inclusao_do_kit);
  // "Editar na KB →", no kit em uso: abre a KB do kit.
  document.querySelector("[data-editar-kit-na-kb]").addEventListener("click", ir_para_a_kb_do_kit);
  // Os filtros da lista (montados de novo a cada mudança: um ouvinte só, na área).
  document.querySelector("[data-filtros-situacao]").addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-filtro-situacao]");
    if (botao) {
      escolher_filtro_de_situacao(botao);
    }
  });
  // As janelas: o X e o "Cancelar"/"Fechar" fecham a janela em que estão.
  for (const botao of document.querySelectorAll("[data-fechar-janela]")) {
    botao.addEventListener("click", function () {
      botao.closest("dialog").close();
    });
  }
  // O "confirmar" da janela dos materiais (a das KBs tem o seu, ligado pelo js/banco_beneficios.js).
  document.querySelector("#janela-confirmacao [data-confirmar-acao]").addEventListener("click", confirmar_acao);
  // "Trocar empresa": a busca e a lista voltam ao topo.
  document.querySelector("[data-trocar-empresa]").addEventListener("click", trocar_de_empresa);
  // A guia Regras gerais: diretrizes gerais ou Santander.
  for (const botao of document.querySelectorAll("[data-dono-das-regras]")) {
    botao.addEventListener("click", function () {
      escolher_grupo_das_regras(botao.dataset.donoDasRegras);
    });
  }
  // As três guias: o clique troca a guia e o endereço; ao abrir, vale a guia pedida no endereço (ou a primeira).
  for (const botao of document.querySelectorAll("[data-guia-endomarketing]")) {
    botao.addEventListener("click", function () {
      trocar_guia_do_endomarketing(botao.dataset.guiaEndomarketing);
      escrever_no_endereco_do_endomarketing("aba", botao.dataset.guiaEndomarketing);
    });
  }
  trocar_guia_do_endomarketing(guia_do_endomarketing_no_endereco());
  // Publicar, retirar ou renovar uma KB da empresa muda o catálogo: os benefícios da escolha 3 são refeitos.
  document.addEventListener("kbs-aplicadas", atualizar_catalogo_depois_de_aplicar);
  // A carteira; sem ela (servidor fora do ar ou com erro), o aviso na lista de empresas.
  const carregou = await carregar_carteira_do_endomarketing();
  if (!carregou) {
    mostrar_carteira_indisponivel();
    return;
  }
  // Abre só a empresa pedida no endereço (ex.: ?empresa=EMP002, vindo da ficha da empresa). Sem pedido, nenhuma
  // abre sozinha: a pessoa escolhe no topo, e nada aparece embaixo até lá.
  const pedida = new URLSearchParams(window.location.search).get("empresa");
  let empresa_para_abrir = null;
  for (const empresa of estado_do_endomarketing.empresas) {
    if (empresa.empresa_id === pedida) {
      empresa_para_abrir = empresa;
    }
  }
  if (empresa_para_abrir) {
    await abrir_empresa_do_endomarketing(empresa_para_abrir.empresa_id);
  }
}

// Espera o HTML carregar inteiro antes de ligar tudo.
document.addEventListener("DOMContentLoaded", preparar_endomarketing_do_banco);
