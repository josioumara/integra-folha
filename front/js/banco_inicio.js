/*
  banco_inicio.js — o Início do Portal Interno com os dados reais da carteira (front ligado à aplicação, ADR-69).

  Para que serve: quando a página é servida pela API, troca os números, a fila "O que precisa de você" e a tabela
  da carteira do exemplo pelos da aplicação (/api/banco/inicio). Só contagens: nenhum funcionário aparece aqui.
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout.

  O que ainda não existe na aplicação, e por isso aparece de outro jeito com os dados reais:
    - a avaliação dos envios pelo banco: o primeiro cartão mostra os envios em andamento nas empresas;
    - o arquivo de contas abertas: o último cartão diz que o dado ainda não chegou.
  O número das mensagens do "Posso ajudar?" sem resposta vem do js/sinal_de_conversas.js.

  O filtro da fila: em cima de "O que precisa de você", a pessoa escolhe uma empresa e
  um prazo. Os prazos têm os nomes que a fila já mostra: "Dentro do prazo" e "Passou do prazo" (de 1 dia útil, o
  prazo que o banco promete para avaliar um envio). Só o envio que espera a avaliação do banco tem prazo; os outros
  itens (empresa sem carga, com pendência ou em andamento) aparecem em "Todos". O filtro trabalha na lista que já
  chegou: trocar a empresa ou o prazo não pede nada ao servidor.

  Servida pela aplicação, os exemplos do layout nunca aparecem: esperam atrás da
  barra cinza (js/carregando_dados.js) até os dados chegarem; se o servidor falhar, os números viram um traço e as
  listas dizem que não foi possível carregar. Nunca sobra um exemplo.
*/

// O aviso que entra no lugar de uma lista quando o servidor não respondeu
const AVISO_DE_FALHA_NO_INICIO = "Não foi possível carregar agora. Atualize a página em instantes.";

// O aviso da fila quando o filtro escolhido não deixa nenhum item
const AVISO_DE_FILA_SEM_ITEM_NO_FILTRO = "Nada com este filtro. Escolha outra empresa ou outro prazo.";

// O aviso da fila quando não há nada esperando o especialista
const AVISO_DE_FILA_VAZIA = "Nada pedindo a sua atenção agora.";

// Os títulos das colunas da carteira com os dados reais (o layout tinha "Aprovados" e "Contas abertas")
const COLUNAS_DA_CARTEIRA = ["Empresa", "Cadastrados", "Envios", "Situação"];

// Os prazos do filtro da fila, na ordem dos botões: "todos" mostra tudo; os outros, só os envios naquele prazo
const PRAZOS_DO_FILTRO = ["todos", "dentro", "passou"];

// Tudo o que esta tela marcou para esperar os dados (os números do alto, a fila e a carteira)
const SELETOR_DO_QUE_ESPERA_NO_INICIO = "[data-inicio-subtitulo], [data-inicio-andamento-valor], " +
  "[data-inicio-andamento-legenda], [data-inicio-andamento-selo], [data-inicio-mensagens-selo], " +
  "[data-inicio-parada-valor], [data-inicio-parada-selo], [data-inicio-contas-valor], [data-inicio-contas-legenda], " +
  "[data-inicio-contas-selo], [data-fila-do-dia], [data-titulo-carteira], [data-tabela-carteira], [data-nota-carteira]";

// O estado do filtro da fila: os itens que o servidor mandou, o nome de cada empresa (pelo código dela), a empresa
// escolhida ("" = todas) e o prazo escolhido ("todos", "dentro" ou "passou")
const estado_da_fila = { itens: [], nomes_das_empresas: {}, empresa: "", prazo: "todos" };

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro).
 *
 * Recebe: etiqueta; classe; texto. Devolve: o elemento.
 */
function criar_no_inicio(etiqueta, classe, texto) {
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
 * Junta a quantidade com a palavra no singular ou no plural.
 *
 * Recebe: quantidade; singular; plural. Devolve: o texto.
 * Exemplos: (1, "empresa", "empresas") → "1 empresa"; (3, "item", "itens") → "3 itens"; (0, "item", "itens") → "0 itens".
 */
function quantidade_com_palavra_no_inicio(quantidade, singular, plural) {
  // Um só: a palavra no singular.
  if (quantidade === 1) {
    return "1 " + singular;
  }
  // Zero ou mais de um: a palavra no plural.
  return quantidade + " " + plural;
}

/**
 * Monta um item da fila "O que precisa de você", no mesmo formato do layout.
 *
 * Recebe: item — {titulo, detalhe, urgente, empresa_id}. Devolve: o elemento <li>.
 */
function montar_item_da_fila_real(item) {
  // O item: urgente ganha a faixa laranja.
  const linha = criar_no_inicio("li", item.urgente ? "item-fila item-fila-urgente" : "item-fila", "");
  // O ícone (alerta para urgente; prancheta para o resto).
  const icone = criar_no_inicio("span", "item-fila-icone", "");
  icone.innerHTML = item.urgente ? "<svg class=\"icone\"><use href=\"#icone-alerta\"/></svg>" : "<svg class=\"icone\"><use href=\"#icone-avaliar\"/></svg>";
  // Título e detalhe.
  const textos = criar_no_inicio("div", "", "");
  textos.append(criar_no_inicio("div", "item-fila-titulo", item.titulo), criar_no_inicio("div", "item-fila-detalhe", item.detalhe));
  // O botão leva ao envio (quando o item é uma avaliação) ou à ficha da empresa.
  let botao = criar_no_inicio("a", "botao botao-contorno botao-pequeno", "Ver a empresa");
  botao.href = "banco_empresas.html?empresa=" + encodeURIComponent(item.empresa_id);
  if (item.envio_id) {
    botao = criar_no_inicio("a", "botao botao-principal botao-pequeno", "Avaliar");
    botao.href = "banco_envios.html?envio=" + encodeURIComponent(item.envio_id);
  }
  linha.append(icone, textos, botao);
  return linha;
}

/**
 * Diz em que prazo está um item da fila: só o envio que espera a avaliação do banco tem prazo (1 dia útil).
 *
 * Recebe: item — {titulo, detalhe, urgente, empresa_id, envio_id}. Devolve: "passou", "dentro" ou "" (sem prazo).
 * A regra é a do servidor (services/portal_do_banco.py, _fila_do_dia; tests/test_filtro_do_inicio.py a confere): o
 * envio que passou do prazo vem com "urgente"; o que está dentro do prazo vem sem. Os outros itens (empresa sem carga,
 * com pendência ou em andamento) não têm envio para avaliar e, por isso, não têm prazo.
 * Exemplos: {envio_id: "P1", urgente: true} → "passou"; {envio_id: "P1", urgente: false} → "dentro";
 *           {empresa_id: "EMP002", urgente: true} (empresa sem carga) → "".
 */
function prazo_do_item_da_fila(item) {
  // Sem envio para avaliar: o item não tem prazo.
  if (!item.envio_id) {
    return "";
  }
  // O envio que passou do prazo vem marcado como urgente.
  if (item.urgente) {
    return "passou";
  }
  // O resto dos envios está dentro do prazo.
  return "dentro";
}

/**
 * Diz se um item da fila passa no filtro escolhido (a empresa e o prazo).
 *
 * Recebe: item; empresa — o código da empresa ("" = todas); prazo — "todos", "dentro" ou "passou".
 * Devolve: true se o item deve aparecer.
 * Exemplos: (envio atrasado da EMP002, "", "passou") → true; (o mesmo, "EMP003", "todos") → false;
 *           (empresa sem carga, "", "dentro") → false (ela não tem prazo).
 */
function item_passa_no_filtro(item, empresa, prazo) {
  // Com uma empresa escolhida, só os itens dela.
  if (empresa && item.empresa_id !== empresa) {
    return false;
  }
  // "Todos": qualquer item, inclusive os que não têm prazo.
  if (prazo === "todos") {
    return true;
  }
  // "Dentro do prazo" ou "Passou do prazo": só os envios nesse prazo.
  return prazo_do_item_da_fila(item) === prazo;
}

/**
 * Conta quantos itens da empresa escolhida cabem em cada prazo do filtro (os números dos botões).
 *
 * Recebe: itens — a fila inteira; empresa — o código da empresa ("" = todas). Devolve: {todos, dentro, passou}.
 * Exemplo: a fila com 2 envios da EMP002 (um atrasado) e 1 empresa sem carga, com empresa "" → {todos: 3, dentro: 1,
 * passou: 1}.
 */
function contar_itens_por_prazo(itens, empresa) {
  const contagens = { todos: 0, dentro: 0, passou: 0 };
  // Cada prazo, contado com o mesmo filtro que a lista usa (o número do botão é o que o clique vai mostrar).
  for (const prazo of PRAZOS_DO_FILTRO) {
    for (const item of itens) {
      if (item_passa_no_filtro(item, empresa, prazo)) {
        contagens[prazo] = contagens[prazo] + 1;
      }
    }
  }
  return contagens;
}

/**
 * Preenche a escolha de empresa do filtro com as empresas que têm algum item na fila, em ordem alfabética.
 *
 * Recebe: nada (usa o estado da fila). Devolve: nada. A primeira opção continua sendo "Todas as empresas".
 */
function montar_escolha_de_empresas_da_fila() {
  const escolha = document.querySelector("[data-filtro-fila-empresa]");
  // As empresas da fila, sem repetir: {código: nome}.
  const empresas_da_fila = {};
  for (const item of estado_da_fila.itens) {
    // O nome vem da carteira; se faltar, o código da empresa (nunca um nome inventado).
    empresas_da_fila[item.empresa_id] = estado_da_fila.nomes_das_empresas[item.empresa_id] || item.empresa_id;
  }
  // Os códigos em ordem alfabética do nome (localeCompare compara como o português: "Á" vem junto do "A").
  const codigos = Object.keys(empresas_da_fila);
  codigos.sort(function (codigo_a, codigo_b) {
    return empresas_da_fila[codigo_a].localeCompare(empresas_da_fila[codigo_b], "pt-BR");
  });
  // Recomeça a lista com a opção "Todas as empresas" e põe uma opção por empresa.
  const opcao_todas = criar_no_inicio("option", "", "Todas as empresas");
  opcao_todas.value = "";
  escolha.replaceChildren(opcao_todas);
  for (const codigo of codigos) {
    const opcao = criar_no_inicio("option", "", empresas_da_fila[codigo]);
    opcao.value = codigo;
    escolha.append(opcao);
  }
  // A escolha volta para "Todas as empresas" (a lista acabou de ser montada).
  escolha.value = "";
}

/**
 * Acende o botão do prazo escolhido e escreve a contagem de cada um, na empresa escolhida.
 *
 * Recebe: contagens — {todos, dentro, passou}. Devolve: nada. Ex.: "Passou do prazo (2)".
 */
function mostrar_botoes_do_prazo(contagens) {
  for (const botao of document.querySelectorAll("[data-filtro-fila-prazo]")) {
    // Verdadeiro para o botão do prazo escolhido.
    const e_o_escolhido = botao.dataset.filtroFilaPrazo === estado_da_fila.prazo;
    // A classe pinta o botão ligado; aria-pressed conta ao leitor de tela qual está ligado.
    botao.classList.toggle("filtro-rapido-ativo", e_o_escolhido);
    botao.setAttribute("aria-pressed", String(e_o_escolhido));
  }
  // A contagem de cada prazo, entre parênteses, como na fila da aba Envios.
  for (const contagem of document.querySelectorAll("[data-contagem-fila-prazo]")) {
    contagem.textContent = "(" + contagens[contagem.dataset.contagemFilaPrazo] + ")";
  }
}

/**
 * Escreve a linha "Mostrando X de Y itens" embaixo do filtro, só quando algum filtro está ligado.
 *
 * Recebe: mostrados — quantos itens passaram no filtro. Devolve: nada. Sem filtro, a linha fica vazia (e some).
 */
function mostrar_resumo_da_fila(mostrados) {
  const resumo = document.querySelector("[data-resumo-da-fila]");
  // Nenhum filtro ligado (todas as empresas e todos os prazos): a lista inteira está à vista, e o resumo some.
  if (!estado_da_fila.empresa && estado_da_fila.prazo === "todos") {
    resumo.textContent = "";
    return;
  }
  const total = estado_da_fila.itens.length;
  resumo.textContent = "Mostrando " + mostrados + " de " + quantidade_com_palavra_no_inicio(total, "item", "itens") + ".";
}

/**
 * Redesenha a fila com o filtro escolhido: os itens que passam, as contagens dos botões e o resumo.
 *
 * Recebe: nada (usa o estado da fila). Devolve: nada. Nenhum pedido ao servidor: a fila é a que já chegou.
 */
function mostrar_fila_filtrada() {
  const fila = document.querySelector("[data-fila-do-dia]");
  fila.replaceChildren();
  // Os itens que passam no filtro, na ordem que o servidor mandou (do mais urgente para o menos urgente).
  let mostrados = 0;
  for (const item of estado_da_fila.itens) {
    if (item_passa_no_filtro(item, estado_da_fila.empresa, estado_da_fila.prazo)) {
      fila.append(montar_item_da_fila_real(item));
      mostrados = mostrados + 1;
    }
  }
  // Nenhum item com este filtro: um aviso no lugar da lista, para a tela não ficar em branco.
  if (mostrados === 0) {
    fila.append(criar_no_inicio("li", "item-fila item-fila-vazio", AVISO_DE_FILA_SEM_ITEM_NO_FILTRO));
  }
  mostrar_botoes_do_prazo(contar_itens_por_prazo(estado_da_fila.itens, estado_da_fila.empresa));
  mostrar_resumo_da_fila(mostrados);
}

/**
 * Mostra a fila que o servidor mandou, com o filtro no começo (todas as empresas e todos os prazos).
 *
 * Recebe: dados — a resposta de /api/banco/inicio ({fila, carteira, ...}). Devolve: nada.
 * Com a fila vazia, entra só o aviso de que nada espera o especialista, e o filtro fica escondido.
 */
function mostrar_fila_do_dia(dados) {
  // O nome de cada empresa da carteira, pelo código (para a escolha de empresa do filtro).
  estado_da_fila.nomes_das_empresas = {};
  for (const empresa of dados.carteira) {
    estado_da_fila.nomes_das_empresas[empresa.id] = empresa.nome;
  }
  // A fila inteira, e o filtro de volta ao começo.
  estado_da_fila.itens = dados.fila;
  estado_da_fila.empresa = "";
  estado_da_fila.prazo = "todos";
  const filtro = document.querySelector("[data-filtro-da-fila]");
  // Fila vazia: o aviso, sem filtro (não há o que filtrar).
  if (dados.fila.length === 0) {
    filtro.hidden = true;
    document.querySelector("[data-fila-do-dia]").replaceChildren(
      criar_no_inicio("li", "item-fila item-fila-vazio", AVISO_DE_FILA_VAZIA));
    return;
  }
  // Com itens: a escolha de empresas, o filtro à mostra e a lista inteira.
  montar_escolha_de_empresas_da_fila();
  filtro.hidden = false;
  mostrar_fila_filtrada();
}

/**
 * Liga o filtro da fila: a troca de empresa e o clique num prazo redesenham a lista.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_filtro_da_fila() {
  // A empresa escolhida mudou: guarda e redesenha.
  const escolha = document.querySelector("[data-filtro-fila-empresa]");
  escolha.addEventListener("change", function () {
    estado_da_fila.empresa = escolha.value;
    mostrar_fila_filtrada();
  });
  // Clique num prazo: guarda e redesenha.
  for (const botao of document.querySelectorAll("[data-filtro-fila-prazo]")) {
    botao.addEventListener("click", function () {
      estado_da_fila.prazo = botao.dataset.filtroFilaPrazo;
      mostrar_fila_filtrada();
    });
  }
}

/**
 * Monta a célula "Envios" da carteira, em duas linhas: quantos envios e, embaixo, quantos estão em andamento.
 *
 * Recebe: empresa — uma linha da carteira da API. Devolve: o elemento <td>.
 * Exemplos: 3 envios, 1 em andamento → "3 envios" / "1 em andamento"; 2 envios, 0 em andamento → "2 envios" /
 * "nenhum em andamento"; nenhum envio → "nenhum envio" (uma linha só).
 * As duas linhas, em vez de "3 (1 em andamento)" numa linha só, deixam a coluna estreita (a tabela cabe no
 * cartão sem rolar para o lado).
 */
function montar_celula_de_envios(empresa) {
  const celula = criar_no_inicio("td", "celula-duas-linhas", "");
  // Sem envio nenhum: uma linha só.
  if (empresa.envios === 0) {
    celula.textContent = "nenhum envio";
    return celula;
  }
  // A primeira linha: quantos envios a empresa já fez.
  celula.append(quantidade_com_palavra_no_inicio(empresa.envios, "envio", "envios"));
  // A segunda linha, menor e cinza (o span da celula-duas-linhas): quantos ainda estão em andamento.
  let em_andamento = "nenhum em andamento";
  if (empresa.em_andamento > 0) {
    em_andamento = empresa.em_andamento + " em andamento";
  }
  celula.append(criar_no_inicio("span", "", em_andamento));
  return celula;
}

/**
 * Monta uma linha da tabela da carteira: empresa (com a cidade), cadastrados, envios e situação.
 *
 * Recebe: empresa — uma linha da carteira da API. Devolve: o elemento <tr>.
 */
function montar_linha_da_carteira_real(empresa) {
  const linha = criar_no_inicio("tr", "", "");
  // Nome e cidade.
  const celula_nome = criar_no_inicio("td", "celula-duas-linhas", "");
  const link = criar_no_inicio("a", "link-empresa", empresa.nome);
  link.href = "banco_empresas.html?empresa=" + encodeURIComponent(empresa.id);
  celula_nome.append(link, criar_no_inicio("span", "", empresa.cidade));
  // Cadastrados e envios.
  const celula_cadastrados = criar_no_inicio("td", "", String(empresa.cadastrados));
  const celula_envios = montar_celula_de_envios(empresa);
  // Situação.
  const celula_situacao = criar_no_inicio("td", "", "");
  celula_situacao.append(criar_no_inicio("span", "selo selo-pequeno " + empresa.situacao.classe, empresa.situacao.texto));
  linha.append(celula_nome, celula_cadastrados, celula_envios, celula_situacao);
  return linha;
}

/**
 * A saudação do título conforme a hora do dia (o layout tinha "Bom dia, Rafael.", com o nome do exemplo).
 *
 * Recebe: nada. Devolve: o texto. Ex.: às 15h, "Boa tarde.".
 */
function saudacao_da_hora() {
  // A hora de agora, de 0 a 23.
  const hora = new Date().getHours();
  // Antes do meio-dia: bom dia.
  if (hora < 12) {
    return "Bom dia.";
  }
  // Até as 18h: boa tarde.
  if (hora < 18) {
    return "Boa tarde.";
  }
  // Depois das 18h: boa noite.
  return "Boa noite.";
}

/**
 * Troca os títulos das colunas da carteira pelos dos dados reais.
 *
 * Recebe: nada. Devolve: nada.
 */
function montar_cabecalho_da_carteira() {
  // A linha dos títulos da tabela, esvaziada.
  const cabecalho = document.querySelector(".tabela-carteira thead tr");
  cabecalho.replaceChildren();
  // Um título por coluna.
  for (const titulo of COLUNAS_DA_CARTEIRA) {
    const celula = criar_no_inicio("th", "", titulo);
    celula.scope = "col";
    cabecalho.append(celula);
  }
}

/**
 * O servidor não entregou o Início: traço nos números, aviso nas listas e nenhum exemplo à mostra.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_inicio_indisponivel() {
  // O subtítulo diz o que aconteceu, sem inventar número.
  document.querySelector("[data-inicio-subtitulo]").textContent = "Não foi possível carregar a sua carteira agora.";
  // Os três números do Início viram um traço (o de mensagens vem do js/sinal_de_conversas.js).
  mostrar_dado_indisponivel(document.querySelector("[data-inicio-andamento-valor]"));
  mostrar_dado_indisponivel(document.querySelector("[data-inicio-parada-valor]"));
  mostrar_dado_indisponivel(document.querySelector("[data-inicio-contas-valor]"));
  // As legendas ficam só com o que o número quer dizer (as do exemplo traziam números inventados).
  document.querySelector("[data-inicio-andamento-legenda]").textContent = "envios esperando a sua avaliação";
  document.querySelector("[data-inicio-contas-legenda]").textContent = "funcionários da carteira com a conta aberta";
  // Os selos do exemplo (prazo, mensagem mais antiga, empresa parada, contas novas) saem.
  const selos_do_exemplo = document.querySelectorAll("[data-inicio-andamento-selo], [data-inicio-mensagens-selo], " +
    "[data-inicio-parada-selo], [data-inicio-contas-selo]");
  for (const selo of selos_do_exemplo) {
    selo.hidden = true;
  }
  // A fila do dia: um item com o aviso, no lugar dos itens de exemplo (o filtro continua escondido).
  const fila = document.querySelector("[data-fila-do-dia]");
  fila.replaceChildren(criar_no_inicio("li", "item-fila", AVISO_DE_FALHA_NO_INICIO));
  // A carteira: título sem número e os títulos reais das colunas.
  document.querySelector("[data-titulo-carteira]").textContent = "Empresas conveniadas";
  montar_cabecalho_da_carteira();
  // Uma linha só, com o aviso ocupando as quatro colunas.
  const linha_do_aviso = criar_no_inicio("tr", "", "");
  const celula_do_aviso = criar_no_inicio("td", "celula-sem-dado", AVISO_DE_FALHA_NO_INICIO);
  celula_do_aviso.colSpan = COLUNAS_DA_CARTEIRA.length;
  linha_do_aviso.append(celula_do_aviso);
  document.querySelector("[data-corpo-carteira]").replaceChildren(linha_do_aviso);
  // A nota embaixo da tabela, sem a data do exemplo.
  document.querySelector("[data-nota-carteira]").textContent =
    "Os números de cada empresa aparecem quando o servidor responder.";
  // Tudo sai da espera: agora aparecem o traço e os avisos.
  marcar_todos_como_carregados(SELETOR_DO_QUE_ESPERA_NO_INICIO);
}

/**
 * O texto do selo do primeiro cartão: quantos envios passaram do prazo de 1 dia útil.
 *
 * Recebe: atrasados — quantos envios passaram do prazo (1 ou mais). Devolve: o texto.
 * Exemplos: 1 → "1 passou do prazo de 1 dia útil"; 3 → "3 passaram do prazo de 1 dia útil".
 */
function texto_do_selo_do_prazo(atrasados) {
  // Um só: o verbo no singular.
  if (atrasados === 1) {
    return "1 passou do prazo de 1 dia útil";
  }
  // Mais de um: o verbo no plural.
  return atrasados + " passaram do prazo de 1 dia útil";
}

/**
 * Busca o Início na API e troca o exemplo pelos dados reais. Sem servidor, nada muda.
 *
 * Recebe: nada. Devolve: nada.
 */
async function carregar_inicio_de_verdade() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // A saudação não depende do servidor: sai já, pela hora do dia (sem o nome do exemplo).
  const saudacao = document.querySelector("[data-inicio-saudacao]");
  saudacao.textContent = saudacao_da_hora();
  marcar_como_carregado(saudacao);
  // try/catch: servidor fora do ar não quebra a tela.
  let dados = null;
  try {
    const resposta = await fetch("/api/banco/inicio");
    // Recusado ou com erro: traço e avisos, nunca o exemplo.
    if (!resposta.ok) {
      mostrar_inicio_indisponivel();
      return;
    }
    dados = await resposta.json();
  } catch (erro) {
    // Servidor fora do ar: traço e avisos, nunca o exemplo.
    mostrar_inicio_indisponivel();
    return;
  }
  const numeros = dados.numeros;
  // Subtítulo: quantas empresas e quantos itens a fila tem (com o singular certo: "1 empresa", "1 item").
  document.querySelector("[data-inicio-subtitulo]").textContent = "Sua carteira tem " +
    quantidade_com_palavra_no_inicio(numeros.empresas, "empresa", "empresas") + " e " +
    quantidade_com_palavra_no_inicio(dados.fila.length, "item", "itens") + " pedindo atenção.";
  // Primeiro cartão: envios esperando a sua avaliação (e quantos passaram do prazo).
  document.querySelector("[data-inicio-andamento-valor]").textContent = numeros.envios_para_avaliar;
  document.querySelector("[data-inicio-andamento-legenda]").textContent = "envios esperando a sua avaliação";
  const selo_do_prazo = document.querySelector("[data-inicio-andamento-selo]");
  selo_do_prazo.hidden = numeros.envios_atrasados === 0;
  selo_do_prazo.textContent = texto_do_selo_do_prazo(numeros.envios_atrasados);
  // Terceiro cartão: empresas sem nenhuma carga.
  document.querySelector("[data-inicio-parada-valor]").textContent = numeros.empresas_sem_carga;
  document.querySelector("[data-inicio-parada-selo]").hidden = true;
  // Último cartão: as contas abertas da carteira (do arquivo semanal); antes do primeiro arquivo, os cadastrados.
  const contas = numeros.contas;
  if (contas.arquivo_recebido) {
    document.querySelector("[data-inicio-contas-valor]").textContent = contas.percentual + "%";
    document.querySelector("[data-inicio-contas-legenda]").textContent =
      contas.com_conta + " de " + contas.cadastrados + " funcionários cadastrados já abriram a conta";
  } else {
    document.querySelector("[data-inicio-contas-valor]").textContent = numeros.cadastrados;
    document.querySelector("[data-inicio-contas-legenda]").textContent = "funcionários cadastrados na carteira (contas abertas: o arquivo do banco ainda não chegou)";
  }
  document.querySelector("[data-inicio-contas-selo]").hidden = true;
  // Segundo cartão: a mensagem mais antiga do exemplo sai (o número de mensagens vem do js/sinal_de_conversas.js).
  document.querySelector("[data-inicio-mensagens-selo]").hidden = true;
  // A fila do dia, com o filtro por empresa e pelo prazo.
  mostrar_fila_do_dia(dados);
  // A carteira: cabeçalho com as colunas reais e uma linha por empresa.
  document.querySelector("[data-titulo-carteira]").textContent =
    quantidade_com_palavra_no_inicio(numeros.empresas, "empresa conveniada", "empresas conveniadas");
  montar_cabecalho_da_carteira();
  const corpo = document.querySelector("[data-corpo-carteira]");
  corpo.replaceChildren();
  for (const empresa of dados.carteira) {
    corpo.append(montar_linha_da_carteira_real(empresa));
  }
  document.querySelector("[data-nota-carteira]").textContent = "Números reais dos cadastros de cada empresa. \"Sem carga\": contrato assinado e nenhum arquivo enviado.";
  // Os dados de verdade estão no lugar: sai a barra de "carregando" de todos.
  marcar_todos_como_carregados(SELETOR_DO_QUE_ESPERA_NO_INICIO);
}

// Quando o HTML terminar de carregar, liga o filtro da fila e troca o exemplo pelos dados reais (se houver servidor).
document.addEventListener("DOMContentLoaded", preparar_filtro_da_fila);
document.addEventListener("DOMContentLoaded", carregar_inicio_de_verdade);
