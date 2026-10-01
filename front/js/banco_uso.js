/*
  banco_uso.js — dados e cliques da parte "uso das empresas" do Painel de acompanhamento (aba Indicadores do Portal
  Interno): os números do uso, o funil do envio, a linha do tempo da empresa e a tabela "Uso do portal por empresa".

  Para que serve:
    1. guarda o uso de exemplo de cada empresa em setembro (funil, tabela e linha do tempo);
    2. desenha o funil do envio e calcula onde está a MAIOR PERDA;
    3. mostra a linha do tempo da empresa escolhida, com a pista do motivo quando houver;
    4. segue o filtro do alto do painel (js/filtro_dos_indicadores.js): com uma
       empresa escolhida, o funil, a linha do tempo e a tabela são só dela; sem empresa, o funil soma as empresas do
       estado escolhido (ou a carteira toda), a linha do tempo pede para escolher uma empresa e a tabela mostra as
       empresas do estado (UF da sede). Clicar no nome de uma empresa na tabela escolhe ela no filtro.

  Atenção: é um rascunho de layout, com números fictícios. No sistema real, o funil sai dos eventos de
  auditoria que a ferramenta já grava (entrada, envio à IA, conferência, envio ao banco, aprovação).
*/

// ===== 1. Dados de exemplo =====

// As 5 etapas do funil, na ordem.
const ETAPAS_DO_FUNIL = [
  "Abriram \"Cadastrar funcionários\"",
  "Mandaram um arquivo para os agentes",
  "Conferiram a lista",
  "Enviaram ao banco",
  "Aprovados pelo banco",
];

// Uso de cada empresa (e da carteira toda) em setembro.
const USO_DAS_EMPRESAS = {
  "carteira": {
    nome: "Carteira toda",
    funil: [32, 23, 17, 16, 11],
    motivo: "9 vezes alguém abriu a tela e saiu sem mandar arquivo. Vale olhar se a tela inicial explica bem o que mandar.",
    linha_do_tempo: [],
    pista: "",
  },
  "aurora": {
    nome: "Aurora Alimentos", uf: "SP",
    ultimo_acesso: "Hoje, 08h12", acessos: 14, envios: 3, descartes: 1, onde_parou: "Em dia",
    funil: [7, 5, 4, 3, 2],
    motivo: "Uma leitura descartada: a planilha era do mês errado.",
    linha_do_tempo: [
      "01/08 · contrato assinado; Marina Costa e Paulo Andrade convidados",
      "01/08 · carga inicial com 290 funcionários, aprovada em 05/08",
      "02/09 · inclusão com 22 funcionários, aprovada no mesmo dia",
      "24/09 · inclusão com 26 funcionários: 24 esperando você e 2 com a empresa",
      "Hoje, 08h15 · mandou uma dúvida pelo \"Posso ajudar?\"",
    ],
    pista: "",
  },
  "horizonte": {
    nome: "Horizonte Logística", uf: "MG",
    ultimo_acesso: "Ontem, 17h38", acessos: 11, envios: 5, descartes: 2, onde_parou: "Leitura em andamento (dúvida sobre a coluna Turno)",
    funil: [9, 7, 5, 5, 3],
    motivo: "Duas leituras descartadas, e um envio devolvido por ser repetido.",
    linha_do_tempo: [
      "01/08 · carga inicial com 540 funcionários, aprovada em 06/08",
      "18/09 · inclusão devolvida: os 40 funcionários já tinham vindo na carga inicial",
      "Ontem, 17h30 · começou uma leitura nova e parou na coluna Turno",
      "Ontem, 17h40 · mandou a dúvida pelo \"Posso ajudar?\"",
    ],
    pista: "A leitura está parada esperando a sua resposta sobre a coluna Turno.",
  },
  "brisa": {
    nome: "Brisa Tecnologia", uf: "SC",
    ultimo_acesso: "22/09, 14h05", acessos: 5, envios: 3, descartes: 0, onde_parou: "Em dia",
    funil: [4, 3, 3, 3, 3],
    motivo: "Uma vez abriu a tela e saiu sem mandar arquivo.",
    linha_do_tempo: [
      "01/08 · carga inicial com 116 funcionários, aprovada em 04/08",
      "21/09 · inclusão com 12 funcionários, aprovada no mesmo dia",
    ],
    pista: "",
  },
  "vale-verde": {
    nome: "Vale Verde Serviços", uf: "PR",
    ultimo_acesso: "03/09, 16h20", acessos: 2, envios: 0, descartes: 2, onde_parou: "Descartou a leitura 2 vezes; sem acesso há 22 dias",
    funil: [3, 2, 0, 0, 0],
    motivo: "As duas leituras foram descartadas antes da conferência.",
    linha_do_tempo: [
      "01/08 · contrato assinado; Tatiane Rocha e Márcio Lemos convidados (Márcio nunca aceitou)",
      "02/08 · Tatiane entrou pela primeira vez e só olhou",
      "03/09, 14h10 · mandou uma planilha: o Agente Interpretador deixou 31 dos 44 campos de fora; Tatiane descartou a leitura",
      "03/09, 16h02 · mandou um PDF escaneado escuro: o Agente Leitor não conseguiu ler; Tatiane descartou de novo",
      "Desde 03/09 · nenhum acesso",
    ],
    pista: "A planilha tinha o cabeçalho na linha 4 (acima dele, o logotipo e o título da empresa). Ofereça ajuda: basta apagar as 3 primeiras linhas ou mandar o Excel original.",
  },
  "prisma": {
    nome: "Prisma Comércio", uf: "PE",
    ultimo_acesso: "Hoje, 07h48", acessos: 9, envios: 4, descartes: 0, onde_parou: "Em dia (inclusão esperando você)",
    funil: [5, 4, 4, 4, 3],
    motivo: "Uma vez abriu a tela e saiu sem mandar arquivo.",
    linha_do_tempo: [
      "01/08 · carga inicial com 780 funcionários, aprovada em 07/08",
      "Setembro · duas inclusões aprovadas (80 funcionários)",
      "Hoje, 07h52 · inclusão com 31 funcionários, esperando você",
    ],
    pista: "",
  },
  "atlantico": {
    nome: "Atlântico Saúde", uf: "BA",
    ultimo_acesso: "23/09, 16h07", acessos: 6, envios: 1, descartes: 1, onde_parou: "Carga inicial esperando o banco (atrasada)",
    funil: [4, 2, 1, 1, 0],
    motivo: "Uma leitura descartada; a outra virou a carga inicial, que espera o banco.",
    linha_do_tempo: [
      "01/08 · contrato assinado; Cláudia Ramos convidada",
      "10/09 · primeira leitura descartada (faltavam os CPFs)",
      "23/09, 16h05 · carga inicial com 205 funcionários enviada ao banco",
      "24/09 · passou do prazo de 1 dia útil sem avaliação do banco",
    ],
    pista: "Quem está segurando agora é o banco: a carga inicial passou do prazo.",
  },
};

// A ordem das empresas na tabela.
const ORDEM_DAS_EMPRESAS = ["aurora", "horizonte", "brisa", "vale-verde", "prisma", "atlantico"];

// ===== 2. Funil =====

/**
 * Acha onde o funil perde mais gente: entre qual etapa e a seguinte.
 *
 * Recebe: funil — lista de números, um por etapa. Devolve: { posicao, perda } (posicao = etapa de cima).
 * Exemplo: [32, 23, 17, 16, 11] → { posicao: 0, perda: 9 } (entre "Abriram" e "Mandaram").
 */
function maior_perda_do_funil(funil) {
  // Começa pela primeira passagem.
  let maior = { posicao: 0, perda: funil[0] - funil[1] };
  // Compara as outras passagens.
  for (let posicao = 1; posicao < funil.length - 1; posicao++) {
    // Quantos se perderam nesta passagem.
    const perda = funil[posicao] - funil[posicao + 1];
    // Se perdeu mais, vira a maior.
    if (perda > maior.perda) {
      maior = { posicao: posicao, perda: perda };
    }
  }
  // Devolve a maior perda.
  return maior;
}

/**
 * Desenha as barras do funil e o aviso da maior perda.
 *
 * Recebe: uso — os dados da empresa (ou da carteira). Devolve: nada.
 */
function mostrar_funil(uso) {
  // Lista do funil.
  const lista = document.querySelector("[data-funil]");
  // Esvazia antes de desenhar.
  lista.replaceChildren();
  // O primeiro número é o 100% das barras.
  const topo = uso.funil[0];
  // A maior perda, para destacar a etapa logo depois dela (onde as pessoas "sumiram").
  const maior = maior_perda_do_funil(uso.funil);
  // Uma barra por etapa.
  uso.funil.forEach(function (quantidade, posicao) {
    // Item do funil.
    const item = document.createElement("li");
    item.className = "etapa-funil";
    // A etapa logo depois da maior perda fica destacada em laranja.
    if (posicao === maior.posicao + 1 && maior.perda > 0) {
      item.classList.add("etapa-funil-perda");
    }
    // Nome da etapa e número.
    const rotulo = document.createElement("span");
    rotulo.className = "etapa-funil-rotulo";
    rotulo.textContent = ETAPAS_DO_FUNIL[posicao];
    const numero = document.createElement("strong");
    numero.textContent = String(quantidade);
    // A barra: largura proporcional ao topo (sem topo, nenhuma barra).
    const barra = document.createElement("span");
    barra.className = "etapa-funil-barra";
    const porcentagem = topo > 0 ? Math.round((quantidade / topo) * 100) : 0;
    barra.style.setProperty("--porcentagem", String(porcentagem));
    // Junta e coloca no funil.
    item.append(rotulo, numero, barra);
    lista.append(item);
  });
  // Aviso da maior perda.
  const aviso = document.querySelector("[data-maior-perda]");
  // Ninguém se perdeu no caminho (ou não houve envio): não há maior perda para apontar.
  if (maior.perda <= 0) {
    aviso.textContent = "Nenhuma perda no funil. " + uso.motivo;
    return;
  }
  aviso.textContent = "Maior perda: entre " + ETAPAS_DO_FUNIL[maior.posicao] + " e " + ETAPAS_DO_FUNIL[maior.posicao + 1] + " (" + maior.perda + "). " + uso.motivo;
}

// ===== 3. Linha do tempo =====

/**
 * Mostra a linha do tempo e a pista do motivo da empresa escolhida.
 *
 * Recebe: id — a empresa (ou "carteira"). Devolve: nada.
 */
function mostrar_linha_do_tempo(id) {
  // Os dados da escolha.
  const uso = USO_DAS_EMPRESAS[id];
  // Título e lista.
  const titulo = document.querySelector("[data-titulo-linha-do-tempo]");
  const lista = document.querySelector("[data-linha-do-tempo]");
  lista.replaceChildren();
  // Carteira toda: não há uma linha do tempo só; pede para escolher uma empresa.
  if (id === "carteira") {
    titulo.textContent = "Escolha uma empresa";
    lista.append(criar_item_da_linha("Escolha uma empresa no filtro do alto (ou clique no nome dela na tabela) para ver o que ela fez, dia a dia."));
  } else {
    titulo.textContent = uso.nome;
    // Um item por acontecimento.
    for (const acontecimento of uso.linha_do_tempo) {
      lista.append(criar_item_da_linha(acontecimento));
    }
  }
  // Pista do motivo: só aparece quando existe.
  document.querySelector("[data-pista-motivo]").hidden = uso.pista === "";
  document.querySelector("[data-pista-motivo-texto]").textContent = uso.pista;
  // Link para a ficha da empresa (não existe para a carteira toda).
  const link = document.querySelector("[data-link-ficha]");
  link.hidden = id === "carteira";
  link.href = "banco_empresas.html?empresa=" + id;
}

/**
 * Cria um item da linha do tempo.
 *
 * Recebe: texto. Devolve: o elemento <li>.
 */
function criar_item_da_linha(texto) {
  // Item com o texto puro.
  const item = document.createElement("li");
  item.textContent = texto;
  // Devolve o item.
  return item;
}

// ===== 4. Tabela por empresa =====

/**
 * Monta a tabela de uso, uma linha por empresa do filtro do alto.
 *
 * Recebe: ids — as empresas que entram, na ordem da carteira. Devolve: nada.
 */
function mostrar_tabela_de_uso(ids) {
  // Corpo da tabela: esvazia antes de montar.
  const corpo = document.querySelector("[data-corpo-uso]");
  corpo.replaceChildren();
  // Nenhuma empresa no filtro: uma linha dizendo isso.
  if (ids.length === 0) {
    const linha_vazia = document.createElement("tr");
    const celula_vazia = document.createElement("td");
    celula_vazia.colSpan = 6;
    celula_vazia.textContent = "Nenhuma empresa da carteira neste filtro.";
    linha_vazia.append(celula_vazia);
    corpo.append(linha_vazia);
    return;
  }
  // Uma linha por empresa, na ordem da carteira.
  for (const id of ids) {
    // Os dados da empresa.
    const uso = USO_DAS_EMPRESAS[id];
    // A linha.
    const linha = document.createElement("tr");
    // Nome como botão: escolhe a empresa no filtro do alto (o painel inteiro passa a ser dela).
    const celula_nome = document.createElement("td");
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "botao-nome";
    botao.dataset.escolherEmpresa = id;
    botao.textContent = uso.nome;
    celula_nome.append(botao);
    linha.append(celula_nome);
    // As outras colunas, como texto.
    for (const valor of [uso.ultimo_acesso, uso.acessos, uso.envios, uso.descartes, uso.onde_parou]) {
      const celula = document.createElement("td");
      celula.textContent = String(valor);
      linha.append(celula);
    }
    // Empresa parada (sem envios e com descartes) fica destacada.
    if (uso.envios === 0) {
      linha.classList.add("linha-atencao");
    }
    // Coloca a linha na tabela.
    corpo.append(linha);
  }
}

// ===== 5. O filtro do alto do painel =====

/**
 * As empresas que entram no uso com o filtro do alto: a escolhida, ou as do estado (UF da sede), ou todas.
 *
 * Recebe: nada (lê filtro_dos_indicadores). Devolve: os ids, na ordem da carteira.
 */
function empresas_do_uso_no_filtro() {
  const escolhidas = [];
  for (const id of ORDEM_DAS_EMPRESAS) {
    const uso = USO_DAS_EMPRESAS[id];
    // Uma empresa escolhida: só ela entra.
    const passa_na_empresa = !filtro_dos_indicadores.empresa_id || id === filtro_dos_indicadores.empresa_id;
    // Um estado escolhido: só as empresas com a sede nele.
    const passa_no_estado = !filtro_dos_indicadores.uf || uso.uf === filtro_dos_indicadores.uf;
    if (passa_na_empresa && passa_no_estado) {
      escolhidas.push(id);
    }
  }
  return escolhidas;
}

/**
 * O funil de várias empresas somado etapa por etapa, no formato que mostrar_funil desenha.
 *
 * Recebe: ids — as empresas. Devolve: { funil, motivo }. Exemplo: [7, 5] e [3, 1] → funil [10, 6].
 */
function funil_somado(ids) {
  const funil = [];
  // Cada etapa começa do zero.
  for (let posicao = 0; posicao < ETAPAS_DO_FUNIL.length; posicao++) {
    funil.push(0);
  }
  // Soma o funil de cada empresa.
  for (const id of ids) {
    const funil_da_empresa = USO_DAS_EMPRESAS[id].funil;
    for (let posicao = 0; posicao < funil.length; posicao++) {
      funil[posicao] = funil[posicao] + (funil_da_empresa[posicao] || 0);
    }
  }
  return { funil: funil, motivo: "Cada envio conta uma vez em cada etapa." };
}

/**
 * O texto acima do funil, dizendo o que ele soma.
 *
 * Recebe: ids — as empresas do filtro. Devolve: o texto.
 */
function texto_sobre_o_funil(ids) {
  if (filtro_dos_indicadores.empresa_id) {
    return USO_DAS_EMPRESAS[filtro_dos_indicadores.empresa_id].nome + ": cada envio conta uma vez em cada etapa.";
  }
  // No singular com uma empresa; no plural com mais.
  let empresas = ids.length + " empresas";
  if (ids.length === 1) {
    empresas = "1 empresa";
  }
  if (filtro_dos_indicadores.uf) {
    return "Empresas com sede em " + filtro_dos_indicadores.uf + " (" + empresas + "), somadas: cada envio conta uma vez em cada etapa.";
  }
  return "Carteira toda (" + empresas + "), somada: cada envio conta uma vez em cada etapa.";
}

/**
 * Redesenha o funil, a linha do tempo e a tabela com o filtro do alto.
 *
 * Recebe: nada. Devolve: nada. Os números do alto (com servidor) são refeitos pelo js/banco_uso_real.js.
 */
function aplicar_filtro_no_uso() {
  // Servidor fora do ar: o uso ficou com os avisos (js/banco_uso_real.js) e não há nada para redesenhar.
  if (!Object.hasOwn(USO_DAS_EMPRESAS, "carteira")) {
    return;
  }
  const ids = empresas_do_uso_no_filtro();
  // A empresa do filtro que não existe no uso (endereço antigo ou empresa removida): tratada como nenhuma.
  const empresa_escolhida = filtro_dos_indicadores.empresa_id;
  const tem_empresa = Boolean(empresa_escolhida) && Object.hasOwn(USO_DAS_EMPRESAS, empresa_escolhida);
  // O funil: o da empresa escolhida, ou a soma das empresas do filtro.
  if (tem_empresa) {
    mostrar_funil(USO_DAS_EMPRESAS[empresa_escolhida]);
  } else {
    mostrar_funil(funil_somado(ids));
  }
  document.querySelector("[data-sobre-o-funil]").textContent = texto_sobre_o_funil(ids);
  // A linha do tempo: a da empresa escolhida; sem empresa, o pedido para escolher uma no filtro.
  if (tem_empresa) {
    mostrar_linha_do_tempo(empresa_escolhida);
  } else {
    mostrar_linha_do_tempo("carteira");
  }
  mostrar_tabela_de_uso(ids);
}

/**
 * Prepara a tela: o clique no nome das empresas da tabela e o desenho com o filtro do alto.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_tela_de_uso() {
  // Clique no nome da empresa na tabela: escolhe ela no filtro do alto e sobe até o filtro.
  document.querySelector("[data-corpo-uso]").addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-escolher-empresa]");
    if (botao) {
      escolher_empresa_no_filtro(botao.dataset.escolherEmpresa);
      document.querySelector("[data-formulario-filtro-indicadores]").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  // O filtro mudou: redesenha o uso.
  document.addEventListener("filtro-dos-indicadores-mudou", aplicar_filtro_no_uso);
  // Aberta como arquivo (o protótipo): as empresas de exemplo vão para a escolha e o uso é desenhado agora.
  // Com servidor, quem faz isso é o js/banco_uso_real.js, quando o uso real chega.
  if (!window.location.protocol.startsWith("http")) {
    const empresas_de_exemplo = [];
    for (const id of ORDEM_DAS_EMPRESAS) {
      empresas_de_exemplo.push({ id: id, nome: USO_DAS_EMPRESAS[id].nome, uf: USO_DAS_EMPRESAS[id].uf });
    }
    registrar_empresas_para_escolher(empresas_de_exemplo);
    aplicar_filtro_no_uso();
  }
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_uso);
