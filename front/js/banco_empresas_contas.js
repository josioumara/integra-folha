/*
  banco_empresas_contas.js — a aba "Contas abertas" da ficha da empresa no Portal Interno.

  Para que serve: o especialista carrega, na ficha de cada empresa, o arquivo de contas abertas DESSA empresa
  (ADR-122). A aba:
    1. mostra, em destaque, a orientação: o arquivo é desta empresa (a da ficha aberta), e cada linha traz o CPF de
       um funcionário Cadastrado nela, o status, a agência, a conta e a data de abertura; um CPF que não está
       Cadastrado nesta empresa recusa o arquivo inteiro. Com servidor, o texto vem dele
       (GET /api/banco/empresas/{id}/contas/layout): a tela diz exatamente o que o código confere;
    2. tem o botão "Carregar Contas Abertas", que abre a janela (js/janela_contas_abertas.js) para ESTA empresa: o
       botão leva a empresa nos atributos data-empresa-id e data-empresa-nome;
       Logo abaixo, a legenda do status de cada linha: "1 = Conta nova · 2 = Já era correntista" (ADR-149), também
       vinda do servidor;
    3. mostra o último arquivo e o histórico dos arquivos confirmados desta empresa
       (GET /api/banco/empresas/{id}/contas/historico), com quantas baixas foram contas novas e quantas foram
       correntistas;
    4. depois de uma baixa (evento "contas-abertas-carregadas" da janela), a ficha, o histórico e o aviso verde se
       atualizam sem recarregar a página.

  Aberta como arquivo (o protótipo), a aba mostra uma orientação e um histórico de exemplo. Servida pela aplicação, o
  exemplo nunca aparece: a orientação, o último arquivo e o histórico esperam com a barra cinza (js/carregando_dados.js)
  e, se o servidor falhar, mostram "Não foi possível carregar agora." ou um traço.

  Depende de: js/janela_contas_abertas.js (texto_dos_tipos_de_conta, que escreve "N novas contas · M correntistas").
*/

// O histórico de exemplo do protótipo (página aberta como arquivo). Dados 100% fictícios.
const HISTORICO_DE_CONTAS_DE_EXEMPLO = [
  { nome_arquivo: "contas_abertas_semana_38.csv", enviado_por: "Rafael Lima", enviado_em: "2026-09-18T10:12:00",
    linhas: 41, novas: 38, carteira_depois: { com_conta: 243, cadastrados: 312 },
    tipos_das_novas: { nova_conta: 30, correntista: 8 } },
  { nome_arquivo: "contas_abertas_semana_37.csv", enviado_por: "Rafael Lima", enviado_em: "2026-09-11T09:40:00",
    linhas: 57, novas: 55, carteira_depois: { com_conta: 205, cadastrados: 312 },
    tipos_das_novas: { nova_conta: 41, correntista: 14 } },
];

// A legenda do status no protótipo (com servidor, vem de legenda_do_status do layout).
const LEGENDA_DO_STATUS_DE_EXEMPLO = "1 = Conta nova · 2 = Já era correntista";

// Cada busca das contas ganha um número; uma resposta atrasada de uma empresa aberta antes não desenha por cima.
let numero_da_busca_de_contas = 0;

// ===== 1. Pequenas ferramentas =====

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como código).
 *
 * Recebe: etiqueta ("tr", "td"...); classe (ou ""); texto (ou ""). Devolve: o elemento.
 */
function criar_nas_contas_da_empresa(etiqueta, classe, texto) {
  // Cria o elemento vazio.
  const elemento = document.createElement(etiqueta);
  // Classe só quando veio uma.
  if (classe) {
    elemento.className = classe;
  }
  // Texto como texto puro.
  if (texto !== "") {
    elemento.textContent = texto;
  }
  // Devolve o elemento.
  return elemento;
}

/**
 * Escreve as contas da empresa depois de um arquivo: "N de M (P%)".
 *
 * Recebe: carteira_depois — {com_conta, cadastrados}, ou null em arquivos antigos. Devolve: o texto.
 * Exemplo: {com_conta: 20, cadastrados: 35} → "20 de 35 (57%)"; null → "—".
 */
function texto_das_contas_depois(carteira_depois) {
  // Arquivo antigo, que não guardava esse número: um traço.
  if (!carteira_depois) {
    return "—";
  }
  // Sem cadastrados, o percentual é 0 (e não uma divisão por zero).
  let percentual = 0;
  if (carteira_depois.cadastrados > 0) {
    percentual = Math.round(100 * carteira_depois.com_conta / carteira_depois.cadastrados);
  }
  // Junta o texto.
  return carteira_depois.com_conta + " de " + carteira_depois.cadastrados + " (" + percentual + "%)";
}

/**
 * Escreve uma data e hora do servidor só com a data, no jeito brasileiro.
 *
 * Recebe: texto — ex.: "2026-09-18T10:12:00". Devolve: ex.: "18/09/2026".
 */
function data_do_arquivo_de_contas(texto) {
  // O navegador converte e escreve no jeito brasileiro.
  return new Date(texto).toLocaleDateString("pt-BR");
}

// ===== 2. Desenhar a aba =====

/**
 * Escreve a orientação e a legenda do status.
 *
 * Recebe: texto_da_orientacao; legenda — o texto dos dois códigos (ex.: "1 = Conta nova · 2 = Já era correntista"),
 * ou "—". Devolve: nada.
 */
function mostrar_orientacao_das_contas(texto_da_orientacao, legenda) {
  // O texto da orientação.
  const orientacao = document.querySelector("[data-orientacao-contas]");
  orientacao.textContent = texto_da_orientacao;
  // A legenda do status.
  const legenda_do_status = document.querySelector("[data-legenda-status]");
  legenda_do_status.textContent = legenda;
  // Os dois saem da espera (js/carregando_dados.js).
  marcar_como_carregado(orientacao);
  marcar_como_carregado(legenda_do_status);
}

/**
 * Monta uma linha do histórico: data, arquivo, linhas, baixas, novas contas e correntistas, contas da empresa
 * depois e quem carregou.
 *
 * Recebe: arquivo — um item do histórico. Devolve: o elemento <tr>.
 */
function montar_linha_do_historico_da_empresa(arquivo) {
  // A linha da tabela.
  const linha = criar_nas_contas_da_empresa("tr", "", "");
  // Os valores, na ordem das colunas. Arquivo de antes do tipo de conta: um traço na coluna dos tipos.
  const valores = [data_do_arquivo_de_contas(arquivo.enviado_em), arquivo.nome_arquivo, String(arquivo.linhas),
    "+" + arquivo.novas, texto_dos_tipos_de_conta(arquivo.tipos_das_novas),
    texto_das_contas_depois(arquivo.carteira_depois), arquivo.enviado_por];
  // Uma célula por valor.
  for (const valor of valores) {
    linha.append(criar_nas_contas_da_empresa("td", "", valor));
  }
  // Devolve a linha pronta.
  return linha;
}

/**
 * Põe uma linha só no histórico, com um recado (ex.: "Nenhum arquivo confirmado ainda.").
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_recado_no_historico(texto) {
  // Uma célula que ocupa as 7 colunas.
  const celula = criar_nas_contas_da_empresa("td", "", texto);
  celula.colSpan = 7;
  // A linha com a célula.
  const linha = criar_nas_contas_da_empresa("tr", "", "");
  linha.append(celula);
  // Troca o conteúdo da tabela pela linha.
  document.querySelector("[data-historico-contas]").replaceChildren(linha);
}

/**
 * Mostra o histórico dos arquivos da empresa e o "Último arquivo".
 *
 * Recebe: arquivos — do mais novo para o mais antigo. Devolve: nada.
 */
function mostrar_historico_das_contas(arquivos) {
  // O corpo da tabela, vazio antes de montar.
  const corpo = document.querySelector("[data-historico-contas]");
  corpo.replaceChildren();
  // Uma linha por arquivo.
  for (const arquivo of arquivos) {
    corpo.append(montar_linha_do_historico_da_empresa(arquivo));
  }
  // Nenhum arquivo ainda: uma linha dizendo isso.
  if (arquivos.length === 0) {
    mostrar_recado_no_historico("Nenhum arquivo de contas desta empresa confirmado ainda.");
  }
  // O "Último arquivo": o mais recente (o primeiro da lista).
  let ultimo = "nenhum ainda";
  if (arquivos.length > 0) {
    ultimo = data_do_arquivo_de_contas(arquivos[0].enviado_em) + ", por " + arquivos[0].enviado_por;
  }
  const ultimo_arquivo = document.querySelector("[data-ultimo-arquivo-contas]");
  ultimo_arquivo.textContent = "Último arquivo: " + ultimo;
  // O histórico e o último arquivo saem da espera.
  marcar_como_carregado(ultimo_arquivo);
  marcar_como_carregado(document.querySelector("[data-bloco-historico-contas]"));
}

/**
 * Mostra a aba com os dados de exemplo do protótipo (página aberta como arquivo).
 *
 * Recebe: empresa — a de exemplo do js/banco_empresas.js. Devolve: nada.
 */
function mostrar_contas_de_exemplo(empresa) {
  // A orientação de exemplo, com o nome da empresa.
  mostrar_orientacao_das_contas("O arquivo é da " + empresa.nome + ", a empresa desta ficha: cada linha traz o CPF " +
    "de um funcionário Cadastrado nela, o status e a agência, a conta salário e a data de abertura dessa conta. " +
    "Um CPF que não está Cadastrado na " + empresa.nome + " recusa o arquivo inteiro.", LEGENDA_DO_STATUS_DE_EXEMPLO);
  // Empresa ainda sem cadastro: nenhum arquivo; as outras, o histórico de exemplo.
  let arquivos = HISTORICO_DE_CONTAS_DE_EXEMPLO;
  if (empresa.contrato.contas === "sem cadastro") {
    arquivos = [];
  }
  mostrar_historico_das_contas(arquivos);
}

// ===== 3. Com servidor =====

/**
 * Pede um endereço da API e devolve os dados, ou null se o servidor recusou ou não respondeu.
 *
 * Recebe: endereco. Devolve: os dados (JSON) ou null.
 */
async function buscar_da_api_de_contas(endereco) {
  // try/catch: servidor fora do ar vira null, não erro na tela.
  try {
    const resposta = await fetch(endereco);
    // Recusado (ex.: 404 de empresa que não existe): null.
    if (!resposta.ok) {
      return null;
    }
    // Deu certo: os dados.
    return await resposta.json();
  } catch (erro) {
    return null;
  }
}

/**
 * Busca, para a empresa aberta, a orientação (do layout) e o histórico, e desenha a aba.
 *
 * Recebe: empresa — a ficha real. Devolve: nada (espera as respostas do servidor).
 */
async function carregar_contas_reais(empresa) {
  // Esta busca ganha um número; se outra começar antes de esta terminar, esta não desenha.
  numero_da_busca_de_contas = numero_da_busca_de_contas + 1;
  const numero_desta_busca = numero_da_busca_de_contas;
  // O começo dos endereços desta empresa. Ex.: "/api/banco/empresas/EMP001/contas".
  const endereco_da_empresa = "/api/banco/empresas/" + encodeURIComponent(empresa.id) + "/contas";
  // As duas perguntas ao servidor, ao mesmo tempo.
  const respostas = await Promise.all([
    buscar_da_api_de_contas(endereco_da_empresa + "/layout"),
    buscar_da_api_de_contas(endereco_da_empresa + "/historico"),
  ]);
  // Outra empresa foi aberta (ou a mesma, de novo) enquanto esperava: não desenha a resposta antiga.
  if (numero_desta_busca !== numero_da_busca_de_contas) {
    return;
  }
  // A orientação e a legenda do status, do layout.
  mostrar_orientacao_do_servidor(respostas[0]);
  // O histórico desta empresa.
  mostrar_historico_do_servidor(respostas[1]);
}

/**
 * Mostra a orientação vinda do layout, ou o aviso de que não carregou.
 *
 * Recebe: layout — de /api/banco/empresas/{id}/contas/layout, ou null. Devolve: nada.
 */
function mostrar_orientacao_do_servidor(layout) {
  // Sem resposta: o aviso no lugar da orientação e um traço na legenda (nunca um texto inventado).
  if (!layout) {
    mostrar_orientacao_das_contas("Não foi possível carregar a orientação agora. Atualize a página em instantes.", "—");
    return;
  }
  // O texto e a legenda, exatamente como o servidor os escreve.
  mostrar_orientacao_das_contas(layout.orientacao_da_empresa, layout.legenda_do_status);
}

/**
 * Mostra o histórico vindo do servidor, ou o aviso de que não carregou.
 *
 * Recebe: arquivos — de /api/banco/empresas/{id}/contas/historico, ou null. Devolve: nada.
 */
function mostrar_historico_do_servidor(arquivos) {
  // Deu certo: o histórico.
  if (arquivos) {
    mostrar_historico_das_contas(arquivos);
    return;
  }
  // Sem resposta: o aviso no lugar dos arquivos e do último arquivo (nunca o exemplo).
  mostrar_recado_no_historico("Não foi possível carregar agora. Atualize a página em instantes.");
  const ultimo_arquivo = document.querySelector("[data-ultimo-arquivo-contas]");
  ultimo_arquivo.textContent = "Último arquivo: não foi possível carregar agora.";
  marcar_como_carregado(ultimo_arquivo);
  marcar_como_carregado(document.querySelector("[data-bloco-historico-contas]"));
}

// ===== 4. A empresa aberta e o fim de uma baixa =====

/**
 * Mostra a aba Contas abertas da empresa aberta (chamada pelo js/banco_empresas.js quando a ficha muda de empresa).
 *
 * Recebe: empresa — a da ficha. Devolve: nada.
 */
function mostrar_contas_da_empresa(empresa) {
  // O botão "Carregar Contas Abertas" leva a empresa para a janela (js/janela_contas_abertas.js).
  const botao = document.querySelector("[data-conteudo-aba='contas'] [data-abrir-carregar-contas]");
  // Outra empresa: o aviso verde da empresa anterior some.
  if (botao.dataset.empresaId !== empresa.id) {
    document.querySelector("[data-aviso-contas]").hidden = true;
  }
  botao.dataset.empresaId = empresa.id;
  botao.dataset.empresaNome = empresa.nome;
  // Com as fichas reais: os dados do servidor.
  if (modo_real_das_empresas()) {
    carregar_contas_reais(empresa);
    return;
  }
  // Servida pela aplicação, mas as fichas reais ainda não chegaram: a aba espera, com a barra cinza.
  if (pagina_servida_pelo_servidor()) {
    return;
  }
  // Aberta como arquivo: o exemplo do protótipo.
  mostrar_contas_de_exemplo(empresa);
}

/**
 * A janela terminou uma baixa: a ficha (números, Visão geral e histórico) e o aviso verde mudam na hora.
 *
 * Recebe: evento — "contas-abertas-carregadas", com detail.texto e detail.empresa_id. Devolve: nada.
 */
async function quando_as_contas_sao_carregadas(evento) {
  // A empresa aberta agora.
  const empresa_aberta = estado_das_empresas.empresa_aberta;
  // A baixa foi de outra empresa (a pessoa trocou de ficha nesse meio-tempo): nada a mudar aqui.
  if (!empresa_aberta || empresa_aberta.id !== evento.detail.empresa_id) {
    return;
  }
  // Com servidor: busca as fichas de novo e reabre a empresa na aba Contas abertas (js/banco_empresas_real.js).
  if (modo_real_das_empresas()) {
    await recarregar_e_abrir(empresa_aberta.id, "contas");
  }
  // O aviso verde, com o texto da janela.
  document.querySelector("[data-aviso-contas-texto]").textContent = evento.detail.texto;
  document.querySelector("[data-aviso-contas]").hidden = false;
}

// Quando a janela terminar uma baixa, a aba se atualiza.
document.addEventListener("contas-abertas-carregadas", quando_as_contas_sao_carregadas);
