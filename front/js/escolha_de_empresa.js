/*
  escolha_de_empresa.js — acha uma empresa da carteira pelo nome ou pelo CNPJ (Portal Interno).

  Para que serve: o filtro do alto do Painel de acompanhamento e o Simulador de
  Rentabilidade (aba Indicadores) escolhem a empresa pelo nome ou por qualquer CNPJ dela (principal, filial ou grupo).
  Este arquivo guarda a lista das empresas da carteira e faz as duas coisas que as duas escolhas precisam:
    1. preencher as sugestões dos campos (cada <datalist data-lista-de-empresas>), com "Nome · CNPJ";
    2. transformar o que a pessoa digitou no id da empresa (ou "todas", com o campo vazio).
  Quem entrega a lista é o js/banco_uso_real.js (com servidor: nome, CNPJs e UF da sede de cada empresa) ou o
  js/banco_uso.js (protótipo, só com os nomes), chamando registrar_empresas_para_escolher.

  E a lista de empresas da Carteira (aba Empresas) e a da "Escolha a empresa"
  (aba Endomarketing) usam a MESMA função, empresas_para_mostrar (no fim deste arquivo): sem busca, só as últimas
  empresas cadastradas, com o aviso "Últimas empresas cadastradas. Pesquise para encontrar outras."; com busca, as que
  combinam com o nome (ou a cidade) ou com um pedaço de qualquer CNPJ delas. Nunca mais que cabe sem rolagem.
  Na Carteira, as empresas com conversa aberta vêm antes de todas, sem limite: a
  Carteira passa os códigos delas à mesma função.
*/

// As empresas da carteira que podem ser escolhidas: [{ id, nome, cnpjs: ["10433218000193", ...], uf }].
const EMPRESAS_PARA_ESCOLHER = [];

/**
 * Tira do texto tudo o que não é número (pontos, barra, traço e espaços).
 *
 * Recebe: texto. Devolve: só os números, em texto. Exemplo: "10.433.218/0001-93" → "10433218000193".
 */
function so_os_numeros(texto) {
  let numeros = "";
  // Junta um caractere de cada vez, só os que são número.
  for (const caractere of texto) {
    if (caractere >= "0" && caractere <= "9") {
      numeros = numeros + caractere;
    }
  }
  return numeros;
}

/**
 * Escreve um CNPJ com a pontuação. Exemplo: "10433218000193" → "10.433.218/0001-93".
 *
 * Recebe: cnpj — os 14 números. Devolve: o texto pontuado (o que não tem 14 números volta como veio).
 */
function cnpj_pontuado(cnpj) {
  if (cnpj.length !== 14) {
    return cnpj;
  }
  return cnpj.slice(0, 2) + "." + cnpj.slice(2, 5) + "." + cnpj.slice(5, 8) + "/" + cnpj.slice(8, 12) + "-" +
    cnpj.slice(12);
}

/**
 * O texto que representa a empresa no campo e nas sugestões: "Nome · CNPJ principal".
 *
 * Recebe: empresa — um item de EMPRESAS_PARA_ESCOLHER. Devolve: o texto. Sem CNPJ (protótipo), só o nome.
 */
function rotulo_da_empresa(empresa) {
  if (empresa.cnpjs.length === 0) {
    return empresa.nome;
  }
  return empresa.nome + " · " + cnpj_pontuado(empresa.cnpjs[0]);
}

/**
 * Acha a empresa pelo id. Recebe: id. Devolve: o item de EMPRESAS_PARA_ESCOLHER, ou null.
 */
function empresa_para_escolher_pelo_id(id) {
  for (const empresa of EMPRESAS_PARA_ESCOLHER) {
    if (empresa.id === id) {
      return empresa;
    }
  }
  return null;
}

/**
 * Guarda a lista das empresas da carteira e refaz as sugestões de todos os campos de escolha da página.
 *
 * Recebe: empresas — [{ id, nome, cnpjs (pode faltar), uf (pode faltar) }]. Devolve: nada.
 * Depois avisa a página (evento "empresas-para-escolher-prontas"), para os campos mostrarem o nome da escolhida.
 */
function registrar_empresas_para_escolher(empresas) {
  // Esvazia e guarda de novo (a lista pode chegar mais de uma vez).
  EMPRESAS_PARA_ESCOLHER.length = 0;
  for (const empresa of empresas) {
    EMPRESAS_PARA_ESCOLHER.push({ id: empresa.id, nome: empresa.nome, cnpjs: empresa.cnpjs || [],
      uf: empresa.uf || "" });
  }
  // Cada lista de sugestões ganha uma opção por empresa ("Nome · CNPJ").
  for (const sugestoes of document.querySelectorAll("[data-lista-de-empresas]")) {
    sugestoes.replaceChildren();
    for (const empresa of EMPRESAS_PARA_ESCOLHER) {
      const opcao = document.createElement("option");
      opcao.value = rotulo_da_empresa(empresa);
      sugestoes.append(opcao);
    }
  }
  document.dispatchEvent(new CustomEvent("empresas-para-escolher-prontas"));
}

/**
 * Transforma o que a pessoa digitou (ou escolheu nas sugestões) na empresa.
 *
 * Recebe: texto. Devolve: "" para todas as empresas (campo vazio); o id da empresa quando acha uma só; ou null quando
 * não acha nenhuma (ou acha mais de uma pelo pedaço do nome).
 * Aceita, nesta ordem: o rótulo da sugestão ("Aurora Alimentos · 10.433.218/0001-93"); um CNPJ de 14 números, com ou
 * sem pontuação (qualquer CNPJ da empresa); o nome inteiro; e um pedaço do nome que só uma empresa tem.
 */
function empresa_pelo_texto(texto) {
  const digitado = texto.trim();
  // Campo vazio: todas as empresas.
  if (digitado === "") {
    return "";
  }
  // 1. O rótulo de uma sugestão, igualzinho.
  for (const empresa of EMPRESAS_PARA_ESCOLHER) {
    if (rotulo_da_empresa(empresa) === digitado) {
      return empresa.id;
    }
  }
  // 2. Um CNPJ: 14 números (com ou sem pontuação), de qualquer empresa.
  const numeros = so_os_numeros(digitado);
  if (numeros.length === 14) {
    for (const empresa of EMPRESAS_PARA_ESCOLHER) {
      if (empresa.cnpjs.includes(numeros)) {
        return empresa.id;
      }
    }
    return null;
  }
  // 3 e 4. O nome inteiro ou um pedaço dele (sem diferença de maiúsculas).
  const procurado = digitado.toLowerCase();
  const com_o_pedaco = [];
  for (const empresa of EMPRESAS_PARA_ESCOLHER) {
    const nome = empresa.nome.toLowerCase();
    if (nome === procurado) {
      return empresa.id;
    }
    if (nome.includes(procurado)) {
      com_o_pedaco.push(empresa.id);
    }
  }
  // Um pedaço do nome só vale quando só uma empresa tem.
  if (com_o_pedaco.length === 1) {
    return com_o_pedaco[0];
  }
  return null;
}

/**
 * O texto que o campo de escolha mostra para a empresa escolhida ("" para todas).
 *
 * Recebe: id — da empresa, ou "". Devolve: o rótulo, ou "" (o campo vazio quer dizer todas as empresas).
 */
function texto_do_campo_para_a_empresa(id) {
  const empresa = empresa_para_escolher_pelo_id(id);
  if (empresa === null) {
    return "";
  }
  return rotulo_da_empresa(empresa);
}

// ===== A lista de empresas da Carteira e do Endomarketing =====

// Quantas empresas a lista mostra: duas fileiras de quatro cartões, sem rolagem por dentro da lista.
const QUANTAS_EMPRESAS_NA_LISTA = 8;
// O aviso quando a lista mostra só as últimas cadastradas.
const AVISO_DAS_ULTIMAS_EMPRESAS = "Últimas empresas cadastradas. Pesquise para encontrar outras.";
// O aviso quando a busca acha mais empresas do que cabem na lista.
const AVISO_DA_BUSCA_COM_MUITAS = "Últimas empresas cadastradas com essa busca. Digite mais para encontrar outras.";

/**
 * O texto sem acentos e em minúsculas, para a busca achar "Logística" digitando "logistica".
 *
 * Recebe: texto. Devolve: o texto comparável. Exemplo: "Atlântico Saúde" → "atlantico saude".
 * Como: normalize("NFD") separa cada letra do acento dela ("á" vira "a" + "´"); os acentos soltos ficam na faixa
 * de códigos 0300 a 036F e são deixados de fora, um caractere de cada vez.
 */
function texto_sem_acentos(texto) {
  let comparavel = "";
  for (const caractere of texto.normalize("NFD")) {
    // O acento solto (a faixa 0300 a 036F) sai; o resto fica
    if (caractere < "̀" || caractere > "ͯ") {
      comparavel = comparavel + caractere;
    }
  }
  return comparavel.toLowerCase();
}

/**
 * Diz se o texto tem alguma letra (a busca pelo nome) ou só números e pontuação (a busca pelo CNPJ).
 *
 * Recebe: texto. Devolve: true ou false. Exemplo: "Aurora" → true; "10.433.218/0001" → false.
 * Como: uma letra tem a forma maiúscula diferente da minúscula; número, ponto, barra e traço, não.
 */
function tem_letra(texto) {
  for (const caractere of texto) {
    if (caractere.toLowerCase() !== caractere.toUpperCase()) {
      return true;
    }
  }
  return false;
}

/**
 * Diz se uma empresa combina com a busca: o nome (ou a cidade) tem o texto buscado, sem diferença de acento e de
 * maiúscula; ou, numa busca só com números, algum CNPJ dela (principal, filial ou grupo) tem esses números.
 *
 * Recebe: empresa — { nome, cidade (pode ser ""), cnpjs: ["10433218000193", ...] }; busca — o que foi digitado.
 * Devolve: true ou false. Exemplos: "aurora" acha a Aurora Alimentos; "10.433.218" acha a Aurora pelo CNPJ.
 */
function empresa_combina_com_a_busca(empresa, busca) {
  const procurado = texto_sem_acentos(busca.trim());
  // Sem busca: todas combinam
  if (procurado === "") {
    return true;
  }
  // O nome ou a cidade com o texto buscado
  if (texto_sem_acentos(empresa.nome).includes(procurado)) {
    return true;
  }
  if (texto_sem_acentos(empresa.cidade || "").includes(procurado)) {
    return true;
  }
  // Uma busca com letras é só pelo nome e pela cidade
  if (tem_letra(procurado)) {
    return false;
  }
  // Só números e pontuação: um pedaço de algum CNPJ da empresa (a pontuação digitada não conta)
  const numeros = so_os_numeros(procurado);
  if (numeros === "") {
    return false;
  }
  for (const cnpj of empresa.cnpjs) {
    if (cnpj.includes(numeros)) {
      return true;
    }
  }
  return false;
}

/**
 * O número do código da empresa (ex.: "EMP024" → 24), para desempatar duas empresas cadastradas no mesmo instante.
 *
 * Recebe: codigo. Devolve: o número (0 quando o código não tem número).
 */
function numero_do_codigo(codigo) {
  const numeros = so_os_numeros(codigo || "");
  if (numeros === "") {
    return 0;
  }
  return Number(numeros);
}

/**
 * Compara duas empresas para a lista: a cadastrada por último vem primeiro (no empate, o código maior, que o
 * cadastro dá em ordem: EMP024 depois de EMP023).
 *
 * Recebe: empresa_a e empresa_b — { codigo, cadastrada_em (data e hora ISO, ou "") }. Devolve: um número negativo
 * quando a empresa_a vem antes, positivo quando vem depois (o jeito que o sort() do JavaScript pede).
 * As datas vêm do servidor no mesmo formato ISO, no horário universal: em texto, a ordem das letras é a do tempo.
 */
function cadastrada_por_ultimo_primeiro(empresa_a, empresa_b) {
  const data_a = empresa_a.cadastrada_em || "";
  const data_b = empresa_b.cadastrada_em || "";
  // A data mais recente primeiro
  if (data_a > data_b) {
    return -1;
  }
  if (data_a < data_b) {
    return 1;
  }
  // Mesma data: o código maior primeiro
  return numero_do_codigo(empresa_b.codigo) - numero_do_codigo(empresa_a.codigo);
}

/**
 * As empresas que a lista mostra e o aviso embaixo dela. É a MESMA função na Carteira e no Endomarketing.
 *
 * Recebe: empresas — [{ codigo, nome, cidade, cnpjs, cadastrada_em, ... }] (cada tela põe junto o que precisa para
 * desenhar o cartão); busca — o que foi digitado (ou ""); codigos_primeiro — opcional: os códigos das empresas que
 * vêm antes de todas, na ordem desta lista e sem limite (a Carteira passa as empresas com conversa aberta; o
 * Endomarketing não passa nada). Devolve: { empresas: as que aparecem, aviso: o texto
 * embaixo da lista (ou "") }. As que aparecem são as de codigos_primeiro que combinam com a busca, todas, e depois as
 * outras, no máximo QUANTAS_EMPRESAS_NA_LISTA, a cadastrada por último primeiro.
 * Sem busca: as últimas cadastradas, com o aviso quando ficam outras de fora. Com busca: as que combinam, com o aviso
 * quando são mais do que cabem. Exemplo: 28 empresas e busca "" → as 8 últimas e AVISO_DAS_ULTIMAS_EMPRESAS; com
 * codigos_primeiro = ["EMP003"], a EMP003 primeiro e, depois dela, as 8 últimas cadastradas sem a EMP003.
 */
function empresas_para_mostrar(empresas, busca, codigos_primeiro) {
  // Sem a lista das que vêm primeiro (o Endomarketing), nenhuma passa na frente
  const lista_dos_primeiros = codigos_primeiro || [];
  // As que vêm primeiro: na ordem pedida, sem limite, e só as que combinam com a busca (um código repetido na lista
  // conta uma vez só: a empresa nunca aparece duas vezes)
  const que_vem_primeiro = [];
  for (const codigo of lista_dos_primeiros) {
    for (const empresa of empresas) {
      const ja_esta_na_lista = que_vem_primeiro.includes(empresa);
      if (empresa.codigo === codigo && !ja_esta_na_lista && empresa_combina_com_a_busca(empresa, busca)) {
        que_vem_primeiro.push(empresa);
      }
    }
  }
  // As outras que combinam com a busca (sem busca, todas), sem repetir as que já vieram primeiro
  const que_combinam = [];
  for (const empresa of empresas) {
    if (empresa_combina_com_a_busca(empresa, busca) && !lista_dos_primeiros.includes(empresa.codigo)) {
      que_combinam.push(empresa);
    }
  }
  // A cadastrada por último primeiro
  que_combinam.sort(cadastrada_por_ultimo_primeiro);
  // Só as que cabem sem rolagem
  const que_aparecem = que_combinam.slice(0, QUANTAS_EMPRESAS_NA_LISTA);
  // O aviso só quando ficaram empresas de fora
  let aviso = "";
  if (que_combinam.length > que_aparecem.length) {
    aviso = AVISO_DAS_ULTIMAS_EMPRESAS;
    if (busca.trim() !== "") {
      aviso = AVISO_DA_BUSCA_COM_MUITAS;
    }
  }
  // As que vêm primeiro na frente das outras
  return { empresas: que_vem_primeiro.concat(que_aparecem), aviso: aviso };
}
