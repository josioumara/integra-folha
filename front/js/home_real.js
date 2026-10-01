/*
  home_real.js — o Início do Portal Empresa com os dados reais da empresa de quem entrou (ADR-69).

  Para que serve: quando a página é servida pela API, troca o exemplo (Aurora, 312 aprovados...) pelos dados reais:
    - o nome da empresa e a jornada do cadastro (contrato → carga inicial → inclusões → contas abertas);
    - os quatro números (cadastrados, pessoas em análise pelo banco, arquivos enviados, linhas para corrigir);
    - os benefícios do catálogo da empresa (js/beneficios_do_catalogo.js);
    - quantos cadastrados ainda estão sem conta informada pelo banco (aguardam o arquivo de contas do banco; podem já
      ser correntistas, ADR-123), o total da empresa (a conta de cada um fica em Acompanhar; ADR-102).
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout.

  Sem exemplo à mostra: servida pela aplicação, cada exemplo marcado no HTML
  (data-aguarda-dado e data-aguarda-bloco) fica atrás de uma barra cinza até o dado real chegar (js/carregando_dados.js).
  Este arquivo libera cada um deles nos dois caminhos:
    - deu certo: o dado real entra e o elemento é marcado como carregado;
    - o servidor falhou (fora do ar ou resposta com erro): os números viram "—" e as listas dizem
      "Não foi possível carregar agora.". Nunca fica o exemplo, e nunca fica a barra cinza para sempre.

  O que ainda não existe na aplicação: a data do contrato e o arquivo de contas abertas do banco. A tela diz isso,
  em vez de mostrar um número inventado.
*/

// O aviso que aparece no lugar de uma lista quando o servidor não respondeu.
const AVISO_DE_FALHA_NO_CARREGAMENTO = "Não foi possível carregar agora.";

/**
 * Escreve uma data do servidor no jeito brasileiro curto ("24/09/2026").
 *
 * Recebe: texto — data e hora do servidor. Devolve: a data.
 */
function data_do_inicio(texto) {
  // O navegador lê a data do servidor e escreve no formato do Brasil (dia/mês/ano).
  return new Date(texto).toLocaleDateString("pt-BR");
}

/**
 * Cria um item da jornada do cadastro (a lista de etapas ao lado das boas-vindas).
 *
 * Recebe: situacao — "concluida", "atual" ou "futura"; marcador — o número da etapa; nome; detalhe.
 * Devolve: o <li> da etapa. Etapa concluída ganha o visto verde, como no layout.
 */
function criar_etapa(situacao, marcador, nome, detalhe) {
  // O item da lista e a bolinha da esquerda (o marcador).
  const etapa = criar_no_cartao("li", "etapa", "");
  const caixa_do_marcador = criar_no_cartao("span", "etapa-marcador", "");
  // Etapa concluída: fica verde e a bolinha mostra o visto.
  if (situacao === "concluida") {
    etapa.classList.add("etapa-concluida");
    caixa_do_marcador.append(criar_icone("icone-visto"));
  } else {
    // Etapa ainda não concluída: a bolinha mostra o número da etapa.
    caixa_do_marcador.textContent = String(marcador);
  }
  // Etapa atual: ganha a cor da marca.
  if (situacao === "atual") {
    etapa.classList.add("etapa-atual");
  }
  // À direita da bolinha: o nome da etapa e o detalhe embaixo.
  const textos = criar_no_cartao("div", "", "");
  textos.append(criar_no_cartao("div", "etapa-nome", nome), criar_no_cartao("div", "etapa-detalhe", detalhe));
  // Junta a bolinha e os textos no item.
  etapa.append(caixa_do_marcador, textos);
  return etapa;
}

/**
 * Monta a jornada real: contrato, carga inicial, inclusões e contas abertas.
 *
 * Recebe: dados — o Início da API. Devolve: nada.
 */
function mostrar_jornada_real(dados) {
  // A lista de etapas: sai o exemplo do layout.
  const lista = document.querySelector("[data-inicio-etapas]");
  lista.replaceChildren();
  // A carga inicial (ou null, se ainda não foi enviada) e o resumo das inclusões.
  const carga = dados.jornada.carga_inicial;
  const inclusoes = dados.jornada.inclusoes;
  // 1. Contrato: a empresa já é conveniada (a data do contrato ainda não é cadastrada na aplicação).
  lista.append(criar_etapa("concluida", 1, "Contrato de folha assinado", "Empresa conveniada"));
  // 2. Carga inicial: feita ou pendente.
  if (carga) {
    // Feita: quantos foram cadastrados e em que dia.
    lista.append(criar_etapa("concluida", 2, "Carga inicial enviada e cadastrada",
      carga.cadastrados + " funcionários cadastrados em " + data_do_inicio(carga.enviado_em)));
  } else {
    // Pendente: é a etapa atual, com o caminho para mandar o arquivo.
    lista.append(criar_etapa("atual", 2, "Carga inicial", "Mande o arquivo com a sua equipe em \"Cadastrar funcionários\""));
  }
  // 3. Inclusões: o resumo dos arquivos de inclusão (só começam depois da carga inicial).
  const detalhe_das_inclusoes = inclusoes.envios + " arquivo(s) · +" + inclusoes.cadastrados + " cadastrados · " +
    dados.numeros.pessoas_em_analise + " em análise pelo banco · " + dados.linhas_para_corrigir + " para corrigir";
  if (carga) {
    // Com a carga inicial feita, as inclusões são a etapa atual.
    lista.append(criar_etapa("atual", 3, "Arquivos de inclusão", detalhe_das_inclusoes));
  } else {
    // Sem a carga inicial, as inclusões ainda estão no futuro.
    lista.append(criar_etapa("futura", 3, "Arquivos de inclusão", "Depois da carga inicial"));
  }
  // 4. Contas abertas: o total da empresa no arquivo semanal do banco (ou o aviso de que ainda não chegou).
  let situacao_das_contas = "futura";
  // Só vira etapa atual quando a carga inicial foi feita e o arquivo de contas do banco já chegou.
  if (carga && dados.contas.arquivo_recebido) {
    situacao_das_contas = "atual";
  }
  lista.append(criar_etapa(situacao_das_contas, 4, "Equipe com conta aberta",
    dados.contas.texto + " · a conta salário de cada funcionário está em Acompanhar cadastros"));
  // A jornada real está na tela: sai a barra cinza.
  marcar_como_carregado(lista);
}

/**
 * Cria um dos quatro cartões de números, no mesmo desenho do layout.
 *
 * Recebe: icone; valor; legenda; link — {texto, endereco} ou null. Devolve: o cartão.
 */
function criar_cartao_de_numero(icone, valor, legenda, link) {
  // O cartão, com o ícone no alto.
  const cartao = criar_no_cartao("div", "cartao cartao-numero", "");
  const caixa_do_icone = criar_no_cartao("span", "cartao-numero-icone", "");
  caixa_do_icone.append(criar_icone(icone));
  // O ícone, o número grande e a legenda embaixo dele.
  cartao.append(caixa_do_icone, criar_no_cartao("div", "cartao-numero-valor", String(valor)),
    criar_no_cartao("div", "cartao-numero-legenda", legenda));
  // Link opcional (ex.: "Acompanhar cadastros").
  if (link) {
    // O link com a setinha no fim.
    const ancora = criar_no_cartao("a", "link-seta", link.texto + " ");
    ancora.href = link.endereco;
    ancora.append(criar_icone("icone-seta"));
    cartao.append(ancora);
  }
  return cartao;
}

/**
 * Monta os quatro cartões de números com os valores recebidos.
 *
 * Recebe: valores — {cadastrados, em_analise, envios, para_corrigir} (números, ou "—" quando o servidor falhou);
 * legenda_em_analise — a legenda do 2º cartão (no singular ou no plural). Devolve: nada.
 * Os cartões novos não têm a marca de "esperando": os de exemplo (com a barra cinza) saem da grade.
 */
function montar_cartoes_de_numeros(valores, legenda_em_analise) {
  // A grade dos números: saem os cartões de exemplo.
  const grade = document.querySelector("[data-inicio-numeros]");
  grade.replaceChildren();
  // 1º cartão: funcionários cadastrados.
  grade.append(criar_cartao_de_numero("icone-equipe", valores.cadastrados, "funcionários cadastrados", null));
  // 2º cartão: as pessoas em análise pelo banco (o mesmo 2º cartão de Acompanhar cadastros).
  grade.append(criar_cartao_de_numero("icone-analise", valores.em_analise, legenda_em_analise, null));
  // 3º cartão: arquivos enviados, com o caminho para acompanhar.
  grade.append(criar_cartao_de_numero("icone-documento", valores.envios, "arquivos enviados",
    { texto: "Acompanhar cadastros", endereco: "acompanhar.html" }));
  // 4º cartão: linhas para corrigir, com o caminho para o assistente.
  grade.append(criar_cartao_de_numero("icone-ia", valores.para_corrigir, "linhas para corrigir",
    { texto: "Corrigir com o assistente", endereco: "acompanhar.html#pendencias" }));
}

/**
 * Troca os quatro números de exemplo pelos reais.
 *
 * Recebe: dados — o Início da API. Devolve: nada.
 */
function mostrar_numeros_reais(dados) {
  // Os números que a API mandou.
  const numeros = dados.numeros;
  // A legenda do 2º cartão no singular quando é uma pessoa só.
  let legenda_em_analise = "pessoas em análise pelo banco";
  if (numeros.pessoas_em_analise === 1) {
    legenda_em_analise = "pessoa em análise pelo banco";
  }
  // Os quatro valores reais, na ordem dos cartões.
  const valores = {
    cadastrados: numeros.cadastrados,
    em_analise: numeros.pessoas_em_analise,
    envios: numeros.envios,
    para_corrigir: dados.linhas_para_corrigir,
  };
  montar_cartoes_de_numeros(valores, legenda_em_analise);
}

/**
 * Busca o Início da empresa na API.
 *
 * Recebe: nada. Devolve: os dados do Início, ou null se o servidor estiver fora do ar ou responder com erro.
 */
async function buscar_inicio_da_empresa() {
  // try/catch: servidor fora do ar não quebra a tela (vira null, e a tela mostra "—").
  try {
    const resposta = await fetch("/api/empresa/inicio");
    // Resposta com erro (ex.: 500 ou sessão vencida): sem dados.
    if (!resposta.ok) {
      return null;
    }
    return await resposta.json();
  } catch (erro) {
    return null;
  }
}

/**
 * Mostra o Início real: boas-vindas, anel, jornada, números e quantos ainda estão sem conta informada pelo banco.
 *
 * Recebe: dados — o Início da API. Devolve: nada. Cada elemento que esperava o dado é liberado aqui.
 */
function mostrar_inicio_real(dados) {
  // Boas-vindas: o selo não inventa a data do contrato (ela ainda não é cadastrada na aplicação).
  const selo = document.querySelector("[data-inicio-selo]");
  selo.replaceChildren(criar_icone("icone-parceria"), document.createTextNode(" Parceira Santander"));
  marcar_como_carregado(selo);
  // O título com o nome real da empresa.
  const titulo = document.querySelector("[data-inicio-titulo]");
  titulo.replaceChildren(document.createTextNode(frase_com_o_nome("Olá, ", dados.empresa) + " "),
    criar_no_cartao("span", "destaque-titulo-leve", "Que bom ter vocês por aqui."));
  marcar_como_carregado(titulo);
  // O anel: o total de cadastrados.
  const numero_do_anel = document.querySelector("[data-inicio-anel-numero]");
  numero_do_anel.textContent = String(dados.numeros.cadastrados);
  marcar_como_carregado(numero_do_anel);
  // A legenda do anel.
  const legenda_do_anel = document.querySelector("[data-inicio-anel-legenda]");
  legenda_do_anel.textContent = "cadastrados";
  marcar_como_carregado(legenda_do_anel);
  // A jornada e os quatro números (as duas funções liberam o que montam).
  mostrar_jornada_real(dados);
  mostrar_numeros_reais(dados);
  // Sem conta: o total da empresa (a conta de cada um aparece na lista de funcionários).
  const numero_sem_conta = document.querySelector("[data-inicio-sem-conta-numero]");
  numero_sem_conta.textContent = dados.sem_conta.texto;
  marcar_como_carregado(numero_sem_conta);
  // O convite é para divulgar os materiais que o Santander preparou (a empresa não cria material, ADR-115).
  const texto_sem_conta = document.querySelector("[data-inicio-sem-conta-texto]");
  texto_sem_conta.textContent = frase_de_quem_esta_sem_conta(dados.sem_conta.quantidade);
  marcar_como_carregado(texto_sem_conta);
}

/**
 * A frase ao lado do número de quem está sem conta informada pelo banco, no singular ou no plural.
 *
 * Recebe: quantidade (ou null quando o servidor não respondeu: vale o plural). Devolve: o texto.
 * Por quê "sem conta informada pelo banco": o número é de quem aguarda o arquivo de
 * contas do banco, e parte dessas pessoas pode já ser correntista (ADR-123); "não têm conta" seria afirmar demais.
 */
function frase_de_quem_esta_sem_conta(quantidade) {
  if (quantidade === 1) {
    return "funcionário cadastrado ainda sem conta informada pelo banco. Divulgar os materiais do Santander ajuda a equipe a abrir.";
  }
  return "funcionários cadastrados ainda sem conta informada pelo banco. Divulgar os materiais do Santander ajuda a equipe a abrir.";
}

/**
 * O servidor não respondeu o Início: nenhum exemplo fica na tela e nenhuma barra cinza fica para sempre.
 *
 * Recebe: nada. Devolve: nada. Números viram "—"; a jornada diz que não foi possível carregar; os textos ficam
 * genéricos (sem o nome de empresa do exemplo).
 */
function mostrar_inicio_indisponivel() {
  // O selo, sem a data do exemplo.
  const selo = document.querySelector("[data-inicio-selo]");
  selo.replaceChildren(criar_icone("icone-parceria"), document.createTextNode(" Parceira Santander"));
  marcar_como_carregado(selo);
  // O título sem o nome da empresa (o do exemplo nunca aparece).
  const titulo = document.querySelector("[data-inicio-titulo]");
  titulo.replaceChildren(document.createTextNode("Olá! "),
    criar_no_cartao("span", "destaque-titulo-leve", "Que bom ter vocês por aqui."));
  marcar_como_carregado(titulo);
  // O anel: traço no número e a legenda de sempre.
  mostrar_dado_indisponivel(document.querySelector("[data-inicio-anel-numero]"));
  const legenda_do_anel = document.querySelector("[data-inicio-anel-legenda]");
  legenda_do_anel.textContent = "cadastrados";
  marcar_como_carregado(legenda_do_anel);
  // A jornada: sai o exemplo e entra o aviso.
  const lista = document.querySelector("[data-inicio-etapas]");
  lista.replaceChildren(criar_no_cartao("li", "etapa-detalhe", AVISO_DE_FALHA_NO_CARREGAMENTO));
  marcar_como_carregado(lista);
  // Os quatro cartões com traço no lugar dos números.
  const valores_indisponiveis = { cadastrados: "—", em_analise: "—", envios: "—", para_corrigir: "—" };
  montar_cartoes_de_numeros(valores_indisponiveis, "pessoas em análise pelo banco");
  // Sem conta: traço no número e o convite de sempre.
  mostrar_dado_indisponivel(document.querySelector("[data-inicio-sem-conta-numero]"));
  const texto_sem_conta = document.querySelector("[data-inicio-sem-conta-texto]");
  texto_sem_conta.textContent = frase_de_quem_esta_sem_conta(null);
  marcar_como_carregado(texto_sem_conta);
}

/**
 * Busca o Início real na API e troca o exemplo por ele (ou por "—", se o servidor falhar).
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: fica o exemplo do protótipo.
 */
async function carregar_inicio_da_empresa() {
  // Aberta como arquivo: não há servidor, e o exemplo do protótipo continua à mostra.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // Os dados do Início (ou null, se o servidor falhou).
  const dados = await buscar_inicio_da_empresa();
  // Servidor falhou: traço nos números, aviso na jornada, nenhum exemplo.
  if (dados === null) {
    mostrar_inicio_indisponivel();
    return;
  }
  // try/catch: se algum dado vier num formato inesperado, a tela não fica com a barra cinza para sempre.
  try {
    mostrar_inicio_real(dados);
  } catch (erro) {
    // Mostra o traço e o aviso no lugar do que faltou montar...
    mostrar_inicio_indisponivel();
    // ...e deixa o erro aparecer no console do navegador (e nos roteiros de clique), para ser corrigido.
    throw erro;
  }
}

/**
 * Busca os benefícios do catálogo da empresa e troca os cartões de exemplo por eles.
 *
 * Recebe: nada. Devolve: nada. Servidor fora do ar: aviso no lugar dos cartões (nunca os de exemplo).
 */
async function carregar_beneficios_do_inicio() {
  // Aberta como arquivo: não há servidor, e os cartões de exemplo continuam à mostra.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // A frase acima dos cartões e a grade dos cartões.
  const descricao = document.querySelector("[data-inicio-descricao-beneficios]");
  const grade = document.querySelector("[data-grade-beneficios]");
  // O catálogo da empresa (ou null, se o servidor falhou).
  const beneficios = await buscar_beneficios_da_empresa();
  // Servidor falhou: frase sem o nome da empresa e o aviso no lugar dos cartões.
  if (!beneficios) {
    descricao.textContent = "Vantagens que o banco definiu para os funcionários da sua empresa.";
    marcar_como_carregado(descricao);
    grade.replaceChildren(criar_no_cartao("p", "descricao-secao", AVISO_DE_FALHA_NO_CARREGAMENTO));
    marcar_como_carregado(grade);
    return;
  }
  // A frase com o nome real da empresa.
  descricao.textContent = frase_com_o_nome("Vantagens que o banco definiu para os funcionários da ", beneficios.empresa);
  marcar_como_carregado(descricao);
  // Os cartões do catálogo real.
  mostrar_beneficios_reais(grade, beneficios.beneficios);
  // Catálogo vazio: diz isso, em vez de deixar a grade em branco.
  if (beneficios.beneficios.length === 0) {
    grade.replaceChildren(criar_no_cartao("p", "descricao-secao", "O banco ainda não definiu os benefícios da sua empresa."));
  }
  // Os benefícios reais estão na tela: sai a barra cinza.
  marcar_como_carregado(grade);
}

// Quando o HTML terminar de carregar, troca o exemplo pelos dados reais (se houver servidor).
// As duas buscas correm ao mesmo tempo: uma falha no Início não impede os benefícios de aparecerem.
document.addEventListener("DOMContentLoaded", carregar_inicio_da_empresa);
document.addEventListener("DOMContentLoaded", carregar_beneficios_do_inicio);
