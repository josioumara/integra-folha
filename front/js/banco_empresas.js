/*
  banco_empresas.js — dados e cliques da tela "Empresas" do Portal Interno.

  Para que serve:
    1. guarda os dados de exemplo das 6 empresas da carteira;
    2. monta a lista (com busca) e a ficha da empresa escolhida, com 6 abas: Visão geral, Conversa, Contas abertas,
       Dados, Usuários e Catálogo de benefícios. O endereço escolhe a empresa e a aba
       (ex.: ?empresa=EMP001&aba=conversa);
       - na lista, as empresas com conversa aberta vêm primeiro, sem limite, e depois as últimas cadastradas;
       - escolhida a empresa, a Carteira "congela" nela, como a escolha do Endomarketing: a lista some e fica só a
         escolhida, com o botão "Trocar empresa", que traz a lista de volta;
    3. as abas Conversa e Contas abertas têm arquivos próprios (js/banco_empresas_conversa.js e
       js/banco_empresas_contas.js): esta ficha só avisa a eles qual empresa foi aberta;
    4. na aba Usuários: convidar (só com e-mail do domínio da empresa) e desativar;
    5. na aba Catálogo: mostra a versão vigente e AVISA quando um benefício não tem as 3 partes.
  O kit de marca não fica na ficha: ele é a KB "Kit da marca" de cada empresa, editada
  no Endomarketing (js/banco_beneficios.js).

  Atenção: é um rascunho de layout. Nada é gravado: recarregar a página volta tudo ao início.
  Dados: 100% fictícios (as empresas são as da base sintética do projeto).
*/

// ===== 1. Dados de exemplo =====

// Catálogo padrão (versão 1), usado pelas empresas que ainda não têm catálogo próprio.
const CATALOGO_PADRAO = {
  versao: "Versão 1 · vigente de 01/08/2026 a 31/12/2026 · padrão Santander",
  beneficios: [
    { nome: "Conta sem mensalidade", categoria: "Conta e dia a dia", partes: [true, true, true] },
    { nome: "Crédito consignado", categoria: "Crédito", partes: [true, true, true] },
    { nome: "Salário antecipado", categoria: "Crédito", partes: [true, true, true] },
  ],
};

// As 6 empresas da carteira.
const EMPRESAS = [
  {
    id: "aurora",
    nome: "Aurora Alimentos",
    razao_social: "Aurora Alimentos Ltda.",
    setor: "Indústria",
    cnpj: "10.433.218/0001-93",
    endereco_comercial: "Av. das Indústrias, 1500 · Campinas/SP",
    dominio: "aurora.com.br",
    contrato: { desde: "01/08/2026", etapa: "Arquivos de inclusão", aprovados: "312", contas: "243 (78%)" },
    situacao: { texto: "Em inclusões", classe: "selo-sucesso" },
    usuarios: [
      { nome: "Marina Costa", email: "marina.costa@aurora.com.br", ultimo_acesso: "Hoje, 08h12", situacao: "ativo" },
      { nome: "Paulo Andrade", email: "paulo.andrade@aurora.com.br", ultimo_acesso: "02/09, 10h40", situacao: "ativo" },
    ],
    catalogo: {
      versao: "Versão 3 · vigente de 01/09/2026 a 31/12/2026 · feita para a Aurora",
      beneficios: [
        { nome: "Conta sem mensalidade", categoria: "Conta e dia a dia", partes: [true, true, true] },
        { nome: "Crédito consignado", categoria: "Crédito", partes: [true, true, true] },
        { nome: "Salário antecipado", categoria: "Crédito", partes: [true, true, true] },
        { nome: "Cartão com cashback", categoria: "Conta e dia a dia", partes: [true, true, true] },
        { nome: "Seguro de vida acessível", categoria: "Proteção", partes: [true, true, true] },
        { nome: "Primeiro investimento", categoria: "Investimentos", partes: [true, true, false] },
      ],
    },
  },
  {
    id: "horizonte",
    nome: "Horizonte Logística",
    razao_social: "Horizonte Logística Ltda.",
    setor: "Logística",
    cnpj: "88.805.929/0001-39",
    endereco_comercial: "Rua dos Transportes, 220 · Contagem/MG",
    dominio: "horizontelog.com.br",
    contrato: { desde: "01/08/2026", etapa: "Arquivos de inclusão", aprovados: "540", contas: "402 (74%)" },
    situacao: { texto: "Em inclusões", classe: "selo-sucesso" },
    usuarios: [
      { nome: "Sérgio Matos", email: "sergio.matos@horizontelog.com.br", ultimo_acesso: "Ontem, 17h38", situacao: "ativo" },
    ],
    catalogo: CATALOGO_PADRAO,
  },
  {
    id: "brisa",
    nome: "Brisa Tecnologia",
    razao_social: "Brisa Tecnologia Ltda.",
    setor: "Tecnologia",
    cnpj: "22.332.061/0001-99",
    endereco_comercial: "Rod. SC-401, 8600 · Florianópolis/SC",
    dominio: "brisatec.com.br",
    contrato: { desde: "01/08/2026", etapa: "Arquivos de inclusão", aprovados: "128", contas: "115 (90%)" },
    situacao: { texto: "Em inclusões", classe: "selo-sucesso" },
    usuarios: [
      { nome: "Helena Duarte", email: "helena.duarte@brisatec.com.br", ultimo_acesso: "22/09, 14h05", situacao: "ativo" },
    ],
    catalogo: CATALOGO_PADRAO,
  },
  {
    id: "vale-verde",
    nome: "Vale Verde Serviços",
    razao_social: "Vale Verde Serviços Ltda.",
    setor: "Serviços",
    cnpj: "66.938.011/0001-25",
    endereco_comercial: "Rua XV de Novembro, 950 · Curitiba/PR",
    dominio: "valeverde.com.br",
    contrato: { desde: "01/08/2026", etapa: "Carga inicial não enviada", aprovados: "nenhum", contas: "sem cadastro" },
    situacao: { texto: "Parada há 55 dias", classe: "selo-atencao" },
    usuarios: [
      { nome: "Tatiane Rocha", email: "tatiane.rocha@valeverde.com.br", ultimo_acesso: "03/09, 16h20", situacao: "ativo" },
      { nome: "Márcio Lemos", email: "marcio.lemos@valeverde.com.br", ultimo_acesso: "nunca entrou", situacao: "convite" },
    ],
    catalogo: CATALOGO_PADRAO,
  },
  {
    id: "prisma",
    nome: "Prisma Comércio",
    razao_social: "Prisma Comércio Ltda.",
    setor: "Varejo",
    cnpj: "39.155.963/0001-08",
    endereco_comercial: "Av. Agamenon Magalhães, 3000 · Recife/PE",
    dominio: "prismacomercio.com.br",
    contrato: { desde: "01/08/2026", etapa: "Arquivos de inclusão", aprovados: "860", contas: "511 (59%)" },
    situacao: { texto: "Em inclusões", classe: "selo-sucesso" },
    usuarios: [
      { nome: "Jonas Pereira", email: "jonas.pereira@prismacomercio.com.br", ultimo_acesso: "Hoje, 07h48", situacao: "ativo" },
      { nome: "Luana Siqueira", email: "luana.siqueira@prismacomercio.com.br", ultimo_acesso: "15/09, 09h10", situacao: "ativo" },
    ],
    catalogo: CATALOGO_PADRAO,
  },
  {
    id: "atlantico",
    nome: "Atlântico Saúde",
    razao_social: "Atlântico Saúde Ltda.",
    setor: "Saúde",
    cnpj: "33.155.206/0001-40",
    endereco_comercial: "Av. Tancredo Neves, 1200 · Salvador/BA",
    dominio: "atlanticosaude.com.br",
    contrato: { desde: "01/08/2026", etapa: "Carga inicial em análise", aprovados: "205 em análise", contas: "sem cadastro" },
    situacao: { texto: "Carga em análise", classe: "selo-marca" },
    usuarios: [
      { nome: "Cláudia Ramos", email: "claudia.ramos@atlanticosaude.com.br", ultimo_acesso: "23/09, 16h07", situacao: "ativo" },
    ],
    catalogo: CATALOGO_PADRAO,
  },
];

// Os nomes das 3 partes que a vitrine de benefícios mostra, na ordem das colunas do catálogo.
const PARTES_DO_BENEFICIO = ["Como funciona", "Quem pode usar", "Como contratar"];

// Selos das situações dos usuários.
const SELOS_DOS_USUARIOS = {
  "ativo": { texto: "Ativo", classe: "selo-sucesso" },
  "convite": { texto: "Convite enviado", classe: "selo-marca" },
  "desativado": { texto: "Desativado", classe: "selo-neutro" },
  // O acesso da empresa que expirou sozinho (ADR-146): a pessoa continua ativa, mas não entra até o banco reativar.
  "sem_uso": { texto: "Suspenso (sem uso)", classe: "selo-atencao" },
  "vencido": { texto: "Acesso vencido", classe: "selo-atencao" },
  // O banco resetou a senha (ou convidou) e a pessoa ainda não cadastrou a dela: some quando ela trocar a senha.
  "senha_provisoria": { texto: "Senha resetada (aguardando nova)", classe: "selo-marca" },
  // Essa senha provisória passou das 48 horas (ADR-154): a pessoa só entra com uma nova ("Nova senha provisória").
  "senha_provisoria_vencida": { texto: "Senha provisória vencida", classe: "selo-atencao" },
};

// ===== 2. Estado da tela =====

// O que a tela está mostrando agora.
const estado_das_empresas = {
  empresa_aberta: null,   // a empresa da ficha
  aba: "visao",           // a aba da ficha (a Visão geral abre primeiro, ADR-112)
  busca: "",              // o texto da busca
  escolhendo: true,       // true: a Carteira mostra a busca e a lista; false: "congelada" na empresa escolhida
  abertas_desenhadas: "", // os códigos das empresas com conversa aberta, na ordem em que a lista as desenhou
};

// ===== 3. Pequenas ferramentas =====

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro).
 *
 * Recebe: etiqueta; classes; texto. Devolve: o elemento.
 */
function criar_elemento(etiqueta, classes, texto) {
  // Cria o elemento vazio.
  const elemento = document.createElement(etiqueta);
  // Põe as classes, se houver.
  if (classes) {
    elemento.className = classes;
  }
  // Põe o texto, se houver.
  if (texto) {
    elemento.textContent = texto;
  }
  // Devolve o elemento.
  return elemento;
}

/**
 * Procura uma empresa pelo identificador.
 *
 * Recebe: id — ex.: "aurora". Devolve: a empresa, ou null.
 */
function achar_empresa(id) {
  // Olha empresa por empresa.
  for (const empresa of EMPRESAS) {
    // Achou: devolve.
    if (empresa.id === id) {
      return empresa;
    }
  }
  // Não achou.
  return null;
}

/**
 * Mostra o aviso verde no alto da página.
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_aviso_das_empresas(texto) {
  // Escreve o texto e mostra o aviso.
  document.querySelector("[data-aviso-empresas-texto]").textContent = texto;
  document.querySelector("[data-aviso-empresas]").hidden = false;
}

/**
 * Preenche uma lista de campos (nome à esquerda, valor à direita) da ficha.
 *
 * Recebe: seletor — onde; campos — lista de [nome, valor]. Devolve: nada.
 */
function preencher_campos(seletor, campos) {
  // O lugar da lista.
  const lista = document.querySelector(seletor);
  // Esvazia antes de montar.
  lista.replaceChildren();
  // Um par nome/valor por campo.
  for (const campo of campos) {
    lista.append(criar_elemento("dt", "", campo[0]), criar_elemento("dd", "", campo[1]));
  }
}

// ===== 4. Lista das empresas =====

/**
 * A cidade da empresa, tirada do endereço comercial.
 *
 * Recebe: empresa. Devolve: a cidade.
 * Exemplo: "Av. das Indústrias, 1500 · Campinas/SP" → "Campinas/SP"; sem " · " (fichas reais), o endereço inteiro.
 */
function cidade_da_empresa(empresa) {
  // Endereço completo: a cidade vem depois do " · ".
  if (empresa.endereco_comercial.includes(" · ")) {
    return empresa.endereco_comercial.split(" · ")[1];
  }
  // Só a cidade (fichas reais).
  return empresa.endereco_comercial;
}

/**
 * A empresa no formato da lista comum da Carteira e do Endomarketing (empresas_para_mostrar, em
 * js/escolha_de_empresa.js).
 *
 * Recebe: empresa — da tela (a de exemplo ou a ficha real). Devolve: { codigo, nome, cidade, cnpjs, cadastrada_em,
 * empresa }. Os CNPJs vão só com os números: o principal e, com servidor, os de filiais e do grupo (ADR-77).
 * Exemplo: a Aurora → { codigo: "EMP001", nome: "Aurora Alimentos Ltda.", cidade: "Campinas/SP",
 * cnpjs: ["10433218000193"], cadastrada_em: "2026-09-25T12:00:00+00:00", empresa: a própria ficha }.
 */
function empresa_para_a_lista(empresa) {
  // O CNPJ principal, sem a pontuação (a de exemplo vem pontuada; a real, só com os números)
  const cnpjs = [so_os_numeros(empresa.cnpj)];
  // Os de filiais e do grupo, que só a ficha real traz
  for (const registrado of empresa.outros_cnpjs || []) {
    cnpjs.push(registrado.cnpj);
  }
  return { codigo: empresa.id, nome: empresa.nome, cidade: cidade_da_empresa(empresa), cnpjs: cnpjs,
    cadastrada_em: empresa.cadastrada_em || "", empresa: empresa };
}

/**
 * Os códigos das empresas com conversa aberta, na ordem em que a Carteira as mostra: primeiro as que esperam a
 * resposta do especialista e, em cada grupo, a da mensagem mais antiga (a que espera há mais tempo).
 *
 * Recebe: nada. Lê window.conversas_abertas, a última resposta de GET /api/banco/conversas/abertas que o script do
 * sinal da Conversa guarda ({empresas: [{empresa_id, sem_resposta, ultima_mensagem_em}], total}).
 * Devolve: a lista de códigos. Sem o script ou sem a resposta (ex.: o servidor ainda não respondeu), a lista vem vazia:
 * "nenhuma conversa aberta", sem erro. Exemplo: [{empresa_id: "EMP002", sem_resposta: false}, {empresa_id: "EMP005",
 * sem_resposta: true}] → ["EMP005", "EMP002"].
 */
function codigos_com_conversa_aberta() {
  // A resposta guardada pelo script do sinal (ou nada)
  const resposta = window.conversas_abertas;
  // Sem resposta, ou num formato que não é o combinado: nenhuma conversa aberta
  if (!resposta || !Array.isArray(resposta.empresas)) {
    return [];
  }
  // Uma cópia da lista, para ordenar sem mexer na resposta que outras partes da tela também leem
  const conversas = resposta.empresas.slice();
  conversas.sort(conversa_mais_urgente_primeiro);
  // Só os códigos, na ordem
  const codigos = [];
  for (const conversa of conversas) {
    codigos.push(conversa.empresa_id);
  }
  return codigos;
}

/**
 * Compara duas conversas abertas para a Carteira: a que espera a resposta do especialista vem antes; no mesmo grupo,
 * a da última mensagem mais antiga vem antes.
 *
 * Recebe: conversa_a e conversa_b — {empresa_id, sem_resposta, ultima_mensagem_em (data e hora ISO)}. Devolve: um
 * número negativo quando a conversa_a vem antes, positivo quando vem depois (o jeito que o sort() do JavaScript pede).
 * As datas vêm do servidor no mesmo formato ISO: em texto, a ordem das letras é a do tempo.
 */
function conversa_mais_urgente_primeiro(conversa_a, conversa_b) {
  // A que espera a resposta do especialista primeiro
  if (conversa_a.sem_resposta && !conversa_b.sem_resposta) {
    return -1;
  }
  if (!conversa_a.sem_resposta && conversa_b.sem_resposta) {
    return 1;
  }
  // No mesmo grupo, a última mensagem mais antiga primeiro
  const data_a = conversa_a.ultima_mensagem_em || "";
  const data_b = conversa_b.ultima_mensagem_em || "";
  if (data_a < data_b) {
    return -1;
  }
  if (data_a > data_b) {
    return 1;
  }
  return 0;
}

/**
 * A empresa em que a Carteira está "congelada": a escolhida, enquanto o especialista não clica em "Trocar empresa".
 *
 * Recebe: nada. Devolve: a empresa aberta, ou null quando a Carteira mostra a busca e a lista.
 */
function empresa_congelada_na_carteira() {
  // Escolhendo outra (ou nenhuma aberta ainda): a lista inteira aparece
  if (estado_das_empresas.escolhendo || !estado_das_empresas.empresa_aberta) {
    return null;
  }
  return estado_das_empresas.empresa_aberta;
}

/**
 * Monta a lista das empresas. Com a Carteira congelada, só a empresa escolhida. Escolhendo: as empresas com conversa
 * aberta primeiro, todas; depois, sem busca, as últimas cadastradas e, com busca, as que combinam com o nome, a cidade
 * ou o CNPJ. As últimas nunca passam do que cabe sem rolagem.
 *
 * Recebe: nada. Devolve: nada. A escolha é a mesma função do Endomarketing (js/escolha_de_empresa.js).
 * Quem estava com o foco numa empresa da lista (navegando pelo teclado) continua nela depois de redesenhar.
 */
function mostrar_lista_de_empresas() {
  // A lista da página.
  const lista = document.querySelector("[data-lista-empresas]");
  // A empresa que estava com o foco, antes de redesenhar (ou "").
  const codigo_com_foco = codigo_da_empresa_com_foco(lista);
  // Esvazia antes de montar.
  lista.replaceChildren();
  // As empresas com conversa aberta, na ordem da Carteira (guardadas para saber, depois, se a ordem mudou).
  const codigos_abertos = codigos_com_conversa_aberta();
  estado_das_empresas.abertas_desenhadas = codigos_abertos.join(",");
  // A empresa escolhida, com a Carteira congelada nela (ou null).
  const empresa_congelada = empresa_congelada_na_carteira();
  // As que aparecem: só a escolhida; ou as abertas e as últimas cadastradas (ou as que combinam com a busca).
  let escolhidas = { empresas: [], aviso: "" };
  if (empresa_congelada) {
    escolhidas.empresas.push(empresa_para_a_lista(empresa_congelada));
  } else {
    // As empresas da carteira no formato da lista comum.
    const empresas_da_carteira = [];
    for (const empresa of EMPRESAS) {
      empresas_da_carteira.push(empresa_para_a_lista(empresa));
    }
    escolhidas = empresas_para_mostrar(empresas_da_carteira, estado_das_empresas.busca, codigos_abertos);
  }
  for (const escolhida of escolhidas.empresas) {
    // A empresa da tela, com o setor, a cidade e a situação.
    const empresa = escolhida.empresa;
    // Botão da empresa (mesmo visual dos itens das outras filas).
    const botao = criar_elemento("button", "botao-envio-fila", "");
    botao.type = "button";
    botao.dataset.abrirEmpresa = empresa.id;
    // Destaca a empresa aberta.
    if (empresa === estado_das_empresas.empresa_aberta) {
      botao.classList.add("botao-envio-fila-aberto");
      botao.setAttribute("aria-current", "true");
    }
    // Nome, cidade e selo da situação.
    botao.append(criar_elemento("span", "botao-envio-fila-empresa", empresa.nome));
    botao.append(criar_elemento("span", "botao-envio-fila-detalhe", empresa.setor + " · " + cidade_da_empresa(empresa)));
    botao.append(criar_elemento("span", "selo selo-pequeno " + empresa.situacao.classe, empresa.situacao.texto));
    // Item da lista com o botão.
    const item = criar_elemento("li", "", "");
    item.append(botao);
    lista.append(item);
  }
  // Aviso quando a busca não acha nada.
  document.querySelector("[data-sem-empresas]").hidden = lista.children.length > 0;
  // O aviso de que há outras empresas fora da lista (some quando todas cabem).
  const aviso_das_ultimas = document.querySelector("[data-aviso-ultimas-empresas]");
  aviso_das_ultimas.textContent = escolhidas.aviso;
  aviso_das_ultimas.hidden = escolhidas.aviso === "";
  // Congelada: a busca some e o "Trocar empresa" aparece; escolhendo, o contrário.
  document.querySelector("[data-campo-busca-da-carteira]").hidden = Boolean(empresa_congelada);
  document.querySelector("[data-trocar-empresa]").hidden = !empresa_congelada;
  // O foco volta à empresa em que estava, se ela continua na lista.
  devolver_o_foco_a_empresa(lista, codigo_com_foco);
  // O selo das mensagens que esperam resposta, em cada empresa da lista (js/banco_empresas_conversa.js).
  atualizar_selos_de_mensagens();
}

/**
 * O código da empresa da lista que está com o foco (ex.: quem navega pelo teclado parou nela).
 *
 * Recebe: lista — o <ul> das empresas. Devolve: o código, ou "" quando o foco está fora da lista.
 */
function codigo_da_empresa_com_foco(lista) {
  // O elemento com o foco agora (a página inteira, quando ninguém tem)
  const com_foco = document.activeElement;
  // Só conta um botão de empresa de dentro da lista
  if (!com_foco || !lista.contains(com_foco) || !com_foco.dataset.abrirEmpresa) {
    return "";
  }
  return com_foco.dataset.abrirEmpresa;
}

/**
 * Devolve o foco ao botão de uma empresa da lista, depois de redesenhar.
 *
 * Recebe: lista — o <ul> das empresas; codigo — o da empresa ("" = ninguém tinha o foco). Devolve: nada.
 * Compara com cada botão, sem montar seletor com o código (um texto estranho nunca vira código na página).
 */
function devolver_o_foco_a_empresa(lista, codigo) {
  // Ninguém da lista tinha o foco: nada a devolver
  if (codigo === "") {
    return;
  }
  for (const botao of lista.querySelectorAll("[data-abrir-empresa]")) {
    if (botao.dataset.abrirEmpresa === codigo) {
      botao.focus();
    }
  }
}

/**
 * O especialista escolheu uma empresa na lista: a ficha dela abre e a Carteira "congela" nela (só ela aparece, com o
 * "Trocar empresa"). O endereço guarda a empresa: o F5 volta nela.
 *
 * Recebe: empresa. Devolve: nada.
 */
function escolher_empresa(empresa) {
  // A escolha terminou: a Carteira se recolhe na empresa escolhida
  estado_das_empresas.escolhendo = false;
  escrever_empresa_no_endereco(empresa.id);
  abrir_empresa(empresa);
  // O foco fica no cartão da escolhida (o botão foi desenhado de novo), para quem usa o teclado não se perder
  const cartao_da_escolhida = document.querySelector("[data-lista-empresas] [data-abrir-empresa]");
  if (cartao_da_escolhida) {
    cartao_da_escolhida.focus();
  }
}

/**
 * "Trocar empresa": a busca e a lista voltam, com o cursor na busca. A ficha continua sendo da empresa escolhida até
 * o especialista clicar em outra (como no Endomarketing).
 *
 * Recebe: nada. Devolve: nada.
 */
function trocar_de_empresa_na_carteira() {
  estado_das_empresas.escolhendo = true;
  mostrar_lista_de_empresas();
  document.querySelector("[data-busca-empresas]").focus();
}

/**
 * Escreve a empresa no endereço, sem recarregar a página (ex.: "banco_empresas.html?empresa=EMP002").
 *
 * Recebe: codigo — o da empresa. Devolve: nada. O resto do endereço (ex.: ?aba=) fica como está.
 * replaceState troca o endereço mostrado sem recarregar e sem criar um passo a mais no "Voltar". Aberta como arquivo
 * (sem servidor), o navegador pode recusar: a tela segue igual, só o F5 não guarda a escolha.
 */
function escrever_empresa_no_endereco(codigo) {
  // try/catch: um navegador que recusa trocar o endereço não pode travar a escolha da empresa
  try {
    const endereco = new URL(window.location.href);
    endereco.searchParams.set("empresa", codigo);
    window.history.replaceState(null, "", endereco.toString());
  } catch (erro) {
    return;
  }
}

/**
 * As conversas abertas mudaram (o script do sinal da Conversa buscou de novo): a lista se refaz só se a ordem das
 * empresas com conversa aberta mudou, para não redesenhar à toa por baixo de quem está usando a tela.
 *
 * Recebe: nada. Devolve: nada. É chamada pelo evento "conversas-abertas-atualizadas" (no document).
 */
function quando_as_conversas_abertas_mudam() {
  // As fichas não chegaram (o servidor falhou): a lista fica com o aviso "Não foi possível carregar agora"
  if (EMPRESAS.length === 0) {
    return;
  }
  // A ordem de agora igual à da lista desenhada: nada muda na tela
  if (codigos_com_conversa_aberta().join(",") === estado_das_empresas.abertas_desenhadas) {
    return;
  }
  mostrar_lista_de_empresas();
}

// ===== 5. Ficha da empresa =====

/**
 * Abre a ficha de uma empresa, na aba escolhida.
 *
 * Recebe: empresa. Devolve: nada.
 */
function abrir_empresa(empresa) {
  // Guarda qual empresa está aberta.
  estado_das_empresas.empresa_aberta = empresa;
  // Cabeçalho da ficha.
  document.querySelector("[data-ficha-setor]").textContent = empresa.setor;
  document.querySelector("[data-ficha-nome]").textContent = empresa.nome;
  // Selo da situação.
  const selo = document.querySelector("[data-ficha-situacao]");
  selo.className = "selo " + empresa.situacao.classe;
  selo.textContent = empresa.situacao.texto;
  // Resumo e aba "Dados": com servidor, os dados reais (js/banco_empresas_real.js); senão, o exemplo.
  if (modo_real_das_empresas()) {
    mostrar_dados_reais(empresa);
    // A Visão geral: os números e a lista de funcionários da empresa (ADR-112).
    mostrar_visao_geral_real(empresa);
  } else {
    mostrar_dados_de_exemplo(empresa);
  }

  // A conversa e as contas abertas da empresa (js/banco_empresas_conversa.js e js/banco_empresas_contas.js).
  mostrar_conversa_da_empresa(empresa);
  mostrar_contas_da_empresa(empresa);
  // As outras duas abas.
  mostrar_usuarios(empresa);
  mostrar_catalogo(empresa);
  // Redesenha a lista para destacar a empresa aberta.
  mostrar_lista_de_empresas();
}

/**
 * Preenche o resumo do cabeçalho e a aba Dados com os dados de exemplo do layout.
 *
 * Recebe: empresa. Devolve: nada.
 */
function mostrar_dados_de_exemplo(empresa) {
  // Resumo do cabeçalho: CNPJ e data do contrato.
  document.querySelector("[data-ficha-resumo]").textContent = "CNPJ " + empresa.cnpj + " · cliente desde " + empresa.contrato.desde;
  // Aba "Dados": empresa e contrato.
  preencher_campos("[data-campos-empresa]", [
    ["Razão social", empresa.razao_social],
    ["CNPJ", empresa.cnpj],
    ["Setor", empresa.setor],
    ["Endereço comercial", empresa.endereco_comercial],
    ["Domínio de e-mail", empresa.dominio],
  ]);
  preencher_campos("[data-campos-contrato]", [
    ["Contrato desde", empresa.contrato.desde],
    ["Etapa da jornada", empresa.contrato.etapa],
    ["Funcionários aprovados", empresa.contrato.aprovados],
    ["Contas abertas", empresa.contrato.contas],
    ["Especialista", "Rafael Lima"],
  ]);
}

/**
 * Troca a aba visível da ficha.
 *
 * Recebe: aba — "visao", "conversa", "contas", "dados", "usuarios" ou "catalogo". Devolve: nada.
 */
function trocar_aba_da_ficha(aba) {
  // Guarda a aba escolhida.
  estado_das_empresas.aba = aba;
  // Liga só o botão da aba escolhida.
  for (const botao of document.querySelectorAll("[data-aba-ficha]")) {
    // Verdadeiro para o botão da aba escolhida.
    const e_a_escolhida = botao.dataset.abaFicha === aba;
    botao.classList.toggle("aba-ficha-ativa", e_a_escolhida);
    // Leitores de tela sabem qual aba está escolhida.
    botao.setAttribute("aria-selected", String(e_a_escolhida));
  }
  // Mostra só o conteúdo da aba escolhida.
  for (const conteudo of document.querySelectorAll("[data-conteudo-aba]")) {
    conteudo.hidden = conteudo.dataset.conteudoAba !== aba;
  }
}

// ===== 6. Aba "Usuários" =====

/**
 * Monta a tabela de usuários da empresa.
 *
 * Recebe: empresa. Devolve: nada.
 */
function mostrar_usuarios(empresa) {
  // Com servidor: as pessoas reais, com Desativar e Reativar de verdade.
  if (modo_real_das_empresas()) {
    // Ao abrir uma empresa, a senha gerada para outra (ou antes) não fica à mostra (js/banco_empresas_real.js)
    esconder_senha_gerada();
    mostrar_usuarios_reais(empresa);
    return;
  }
  // Corpo da tabela.
  const corpo = document.querySelector("[data-corpo-usuarios]");
  // Esvazia antes de montar.
  corpo.replaceChildren();
  // Uma linha por usuário.
  for (const usuario of empresa.usuarios) {
    // Linha com nome, e-mail e último acesso.
    const linha = criar_elemento("tr", "", "");
    linha.append(criar_elemento("td", "", usuario.nome), criar_elemento("td", "", usuario.email), criar_elemento("td", "", usuario.ultimo_acesso));
    // Selo da situação.
    const selo = SELOS_DOS_USUARIOS[usuario.situacao];
    const celula_situacao = criar_elemento("td", "", "");
    celula_situacao.append(criar_elemento("span", "selo selo-pequeno " + selo.classe, selo.texto));
    linha.append(celula_situacao);
    // Ação: desativar quem está ativo; quem está desativado não tem ação.
    const celula_acao = criar_elemento("td", "", "");
    if (usuario.situacao !== "desativado") {
      const botao = criar_elemento("button", "botao-nome", "Desativar");
      botao.type = "button";
      botao.dataset.desativarUsuario = usuario.email;
      celula_acao.append(botao);
    }
    linha.append(celula_acao);
    // Coloca a linha na tabela.
    corpo.append(linha);
  }
}

/**
 * Desativa um usuário da empresa aberta (ele deixa de entrar no portal).
 *
 * Recebe: email. Devolve: nada.
 */
function desativar_usuario(email) {
  // A empresa aberta.
  const empresa = estado_das_empresas.empresa_aberta;
  // Procura o usuário pelo e-mail.
  for (const usuario of empresa.usuarios) {
    // Achou: desativa.
    if (usuario.email === email) {
      usuario.situacao = "desativado";
      mostrar_aviso_das_empresas(usuario.nome + " não entra mais no Portal Empresa. O histórico do que essa pessoa fez continua guardado.");
    }
  }
  // Redesenha a tabela.
  mostrar_usuarios(empresa);
}

/**
 * Abre a janela de convite.
 *
 * Recebe: nada. Devolve: nada.
 */
function abrir_janela_de_convite() {
  // Nome da empresa no título.
  document.querySelector("[data-convite-empresa]").textContent = estado_das_empresas.empresa_aberta.nome;
  // Formulário limpo.
  document.querySelector("[data-convite-nome]").value = "";
  document.querySelector("[data-convite-email]").value = "";
  document.querySelector("[data-convite-erro]").hidden = true;
  // Abre a janela.
  document.getElementById("janela-convite").showModal();
}

/**
 * Confere o convite e diz o que está errado (ou "" se estiver tudo certo).
 *
 * Recebe: nome; email; empresa. Devolve: o texto do erro, ou "".
 * Regra de segurança: só e-mail do domínio da empresa. Assim ninguém convida, por engano ou de propósito,
 * uma pessoa de fora (ex.: um e-mail pessoal) para ver os dados dos funcionários.
 */
function erro_do_convite(nome, email, empresa) {
  // Nome curto demais.
  if (nome.trim().length < 3) {
    return "Escreva o nome completo da pessoa.";
  }
  // E-mail fora do domínio da empresa.
  if (!email.trim().toLowerCase().endsWith("@" + empresa.dominio)) {
    return "Use um e-mail do domínio da empresa (@" + empresa.dominio + ").";
  }
  // E-mail repetido.
  for (const usuario of empresa.usuarios) {
    if (usuario.email === email.trim().toLowerCase()) {
      return "Esta pessoa já tem acesso.";
    }
  }
  // Tudo certo.
  return "";
}

/**
 * Envia o convite: a pessoa entra na tabela como "Convite enviado".
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
function enviar_convite(evento) {
  // Impede o fechamento automático da janela.
  evento.preventDefault();
  // Com servidor, o acesso é criado de verdade (js/banco_empresas_real.js).
  if (modo_real_das_empresas()) {
    enviar_convite_de_verdade();
    return;
  }
  // A empresa e o que foi digitado.
  const empresa = estado_das_empresas.empresa_aberta;
  const nome = document.querySelector("[data-convite-nome]").value;
  const email = document.querySelector("[data-convite-email]").value;
  // Confere.
  const erro = erro_do_convite(nome, email, empresa);
  // Com erro: mostra e não fecha.
  if (erro) {
    const aviso = document.querySelector("[data-convite-erro]");
    aviso.textContent = erro;
    aviso.hidden = false;
    return;
  }
  // Acrescenta o usuário como convite enviado.
  empresa.usuarios.push({ nome: nome.trim(), email: email.trim().toLowerCase(), ultimo_acesso: "nunca entrou", situacao: "convite" });
  // Fecha a janela, redesenha e avisa.
  document.getElementById("janela-convite").close();
  mostrar_usuarios(empresa);
  mostrar_aviso_das_empresas("Convite enviado para " + email.trim().toLowerCase() + ". Vale por 7 dias.");
}

// ===== 7. Aba "Catálogo de benefícios" =====

/**
 * Monta a tabela do catálogo e o aviso de benefícios incompletos.
 *
 * Recebe: empresa. Devolve: nada.
 */
function mostrar_catalogo(empresa) {
  // Com servidor: os documentos vigentes reais da empresa.
  if (modo_real_das_empresas()) {
    mostrar_catalogo_real(empresa);
    return;
  }
  // Versão e vigência.
  document.querySelector("[data-catalogo-versao]").textContent = empresa.catalogo.versao;
  // Corpo da tabela.
  const corpo = document.querySelector("[data-corpo-catalogo]");
  corpo.replaceChildren();
  // Frases dos benefícios que estão faltando alguma parte.
  const faltas = [];
  // Uma linha por benefício.
  for (const beneficio of empresa.catalogo.beneficios) {
    // Nome e categoria.
    const linha = criar_elemento("tr", "", "");
    linha.append(criar_elemento("td", "", beneficio.nome), criar_elemento("td", "", beneficio.categoria));
    // Uma célula por parte: "Tem" (verde) ou "Falta" (laranja).
    beneficio.partes.forEach(function (tem_a_parte, posicao) {
      // Célula da parte.
      const celula = criar_elemento("td", "", "");
      // Selo verde ou laranja.
      celula.append(criar_elemento("span", "selo selo-pequeno " + (tem_a_parte ? "selo-sucesso" : "selo-atencao"), tem_a_parte ? "Tem" : "Falta"));
      linha.append(celula);
      // Guarda a frase da falta para o aviso.
      if (!tem_a_parte) {
        faltas.push(beneficio.nome + " (falta \"" + PARTES_DO_BENEFICIO[posicao] + "\")");
      }
    });
    // Coloca a linha na tabela.
    corpo.append(linha);
  }
  // Aviso: só aparece se algum benefício estiver incompleto.
  const aviso = document.querySelector("[data-catalogo-aviso]");
  aviso.hidden = faltas.length === 0;
  aviso.textContent = "Incompleto: " + faltas.join("; ") + ". A vitrine da empresa mostra essa parte vazia até a próxima versão.";
}

// ===== 8. Ligações dos cliques =====

/**
 * Trata os cliques da página num lugar só.
 *
 * Recebe: evento. Devolve: nada.
 */
function tratar_clique_nas_empresas(evento) {
  // O botão clicado.
  const botao = evento.target.closest("button");
  // Fora de botão: nada a fazer.
  if (!botao) {
    return;
  }
  // Escolher uma empresa da lista: a ficha abre e a Carteira congela nela.
  if (botao.dataset.abrirEmpresa) {
    escolher_empresa(achar_empresa(botao.dataset.abrirEmpresa));
    return;
  }
  // "Trocar empresa": a busca e a lista voltam.
  if (botao.hasAttribute("data-trocar-empresa")) {
    trocar_de_empresa_na_carteira();
    return;
  }
  // Trocar a aba da ficha.
  if (botao.dataset.abaFicha) {
    trocar_aba_da_ficha(botao.dataset.abaFicha);
    return;
  }
  // Desativar um usuário.
  if (botao.dataset.desativarUsuario) {
    desativar_usuario(botao.dataset.desativarUsuario);
    return;
  }
  // Desativar ou reativar uma pessoa de verdade (fichas reais).
  if (botao.dataset.alternarUsuario) {
    alternar_usuario_de_verdade(botao.dataset.alternarUsuario);
    return;
  }
  // Gerar uma senha provisória nova para quem esqueceu a senha (fichas reais, ADR-109): o primeiro clique pergunta, na
  // própria linha da pessoa, com "Confirmar" e "Cancelar" (js/banco_empresas_real.js).
  if (botao.dataset.novaSenha) {
    pedir_confirmacao_da_nova_senha(botao.dataset.novaSenha);
    return;
  }
  // Com servidor, convite, empresa nova e editar dados vão para a aplicação (js/banco_empresas_real.js).
  if (modo_real_das_empresas() && tratar_clique_real(botao)) {
    return;
  }
  // Abrir a janela de convite.
  if (botao.hasAttribute("data-abrir-convite")) {
    abrir_janela_de_convite();
    return;
  }
  // Cadastrar empresa nova (tela ainda não desenhada neste rascunho).
  if (botao.hasAttribute("data-cadastrar-empresa")) {
    mostrar_aviso_das_empresas("O cadastro de empresa nova (CNPJ, contrato e primeiro usuário) é o próximo passo do layout.");
    return;
  }
  // Fechar a janela (X ou Cancelar).
  if (botao.hasAttribute("data-fechar-janela")) {
    botao.closest("dialog").close();
  }
}

/**
 * Prepara a tela: liga cliques, busca e convite, e abre a empresa pedida no endereço (ou a primeira).
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_tela_de_empresas() {
  // Todos os cliques passam por uma função só.
  document.addEventListener("click", tratar_clique_nas_empresas);
  // Busca: filtra a lista a cada letra.
  document.querySelector("[data-busca-empresas]").addEventListener("input", function (evento) {
    estado_das_empresas.busca = evento.target.value.trim().toLowerCase();
    mostrar_lista_de_empresas();
  });
  // Envio do convite.
  document.querySelector("[data-formulario-convite]").addEventListener("submit", enviar_convite);
  // As conversas abertas chegaram (ou mudaram): as empresas delas vêm primeiro na lista (js da Conversa, no menu).
  document.addEventListener("conversas-abertas-atualizadas", quando_as_conversas_abertas_mudam);
  // A empresa pedida no endereço (ex.: ?empresa=aurora); senão, a primeira.
  const pedida = achar_empresa(new URLSearchParams(window.location.search).get("empresa"));
  // A empresa pedida no endereço já foi escolhida (ex.: vinda do Início): a Carteira começa congelada nela. Sem pedido,
  // a lista aparece, e a ficha mostra a primeira empresa até o especialista escolher.
  estado_das_empresas.escolhendo = pedida === null;
  abrir_empresa(pedida ? pedida : EMPRESAS[0]);
  // A aba pedida no endereço (ex.: ?aba=conversa), se houver.
  abrir_aba_pedida_no_endereco();
}

/**
 * Abre a aba da ficha pedida no endereço (ex.: banco_empresas.html?empresa=EMP001&aba=contas).
 *
 * Recebe: nada. Devolve: nada. Sem "aba" no endereço, ou com uma aba que não existe, a ficha fica como está.
 * Só troca se a aba pedida existe na ficha: compara com cada botão de aba, sem montar seletor com o texto do endereço
 * (um texto estranho no endereço nunca vira código na página).
 */
function abrir_aba_pedida_no_endereco() {
  // O nome da aba no endereço (ou null, sem "aba").
  const aba_pedida = new URLSearchParams(window.location.search).get("aba");
  // Olha cada botão de aba da ficha.
  for (const botao_da_aba of document.querySelectorAll("[data-aba-ficha]")) {
    // Achou a aba pedida: troca para ela.
    if (botao_da_aba.dataset.abaFicha === aba_pedida) {
      trocar_aba_da_ficha(aba_pedida);
    }
  }
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_empresas);
