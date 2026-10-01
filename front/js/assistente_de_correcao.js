/*
  assistente_de_correcao.js — o cartão de cada pendência, que é uma conversa com o agente, nas telas Cadastrar e
  Acompanhar (ADR-118, que substitui o "Perguntar à IA" do ADR-99; servidor em
  services/assistente_na_tela.py).

  Para que serve: a pendência se resolve CONVERSANDO, e o cartão tem cara de conversa, e não de um campo de
  formulário. O cartão, sempre aberto, tem:
    - no alto, o nome da pessoa à esquerda e o nome simples do campo à direita;
    - a pergunta num balão do agente, à esquerda, com o selo "✦ Agente de validação" e o valor lido dentro
      (ex.: 'No arquivo veio "Solteiro(a)", que não está na lista. Qual é o certo?');
    - as respostas rápidas (pílulas, como no WhatsApp): um clique responde (ex.: "Solteiro", "Não cadastrar esta
      pessoa") ou põe a frase na caixa para completar;
    - a caixa "Responda ao agente..." com o botão de enviar (➤);
    - no fim, numa linha cinza pequena, o arquivo e a data do envio (em Acompanhar).
  A resposta da pessoa vira um balão à direita ("você"); enquanto o agente trabalha, um balão com os pontinhos e o
  "Processando… N s". O agente já ajusta o dado, e o balão dele diz "Pronto: Estado civil = Solteiro." com o Desfazer; a
  tela que chamou refaz os dados dela (a função "ao_mudar"). Se a pendência sumiu: na conferência do Cadastrar, ela
  aparece no aviso "Resolvido agora", com o mesmo Desfazer; em Acompanhar, o cartão
  fica no lugar, verde, até a pessoa ir para outro cartão, e depois mora no filtro "Resolvidas", com a conversa
  guardada no servidor (montar_conversa_resolvida, só de leitura). Pedido sobre outro dado é recusado pelo servidor
  (balão âmbar), e nada muda. Com mais de 4 balões, os mais antigos se recolhem em "Ver a conversa inteira (N)".
  Não mandar uma informação (tirar a pessoa do envio, deixar um campo em branco) pede confirmação: o balão do agente
  pergunta e traz dois botões ("Sim, não cadastrar" / "Cancelar"); a escolha vira o balão da pessoa e fica registrada
  na trilha do envio. O agente se apresenta como "Agente de validação".

  O joinha (ADR-151): embaixo de cada resposta do agente, e embaixo da pergunta nas pendências de pergunta da leitura
  (a do Agente Leitor ou do Agente Conferidor), a pessoa diz se ajudou. O joinha mora em js/opiniao_dos_agentes.js,
  que a página carrega logo depois deste arquivo; aqui ficam só as chamadas e a posição de cada resposta na conversa
  ("ordem"), que vem do servidor.

  A conversa encerrada (ADR-153): depois de algumas respostas sem valor ("não sei", "não tenho"), o agente agradece e
  encerra a conversa; a resposta chega com "encerrada", e o balão dele ganha a marca "Conversa encerrada". A pendência
  continua aberta, e a caixa continua valendo: quem descobrir o valor pode escrever de novo.

  Pendências em grupo (ADR-120): quando várias pessoas vieram com o mesmo valor fora
  da lista (ex.: 23 com "Divorciado(a)"), cada pendência traz o mesmo "grupo", e o cartão vira o do grupo: o título
  "23 pessoas com o mesmo valor", uma pergunta só, as respostas rápidas para todas ('Sim, use "Divorciado" para as
  23'), "Ver quem são" e "Responder uma a uma" (um cartão por pessoa, com o botão para voltar a responder todas de uma
  vez). A mensagem vai com em_grupo, e o servidor aplica em todas, com um Desfazer para o grupo inteiro.

  Como a conversa sobrevive à lista refeita: cada conversa fica guardada nesta página (as falas, se está inteira, o
  texto ainda não enviado e se está esperando o agente), pela chave "envio|regra|linha". Quando a lista é montada de novo
  (depois de uma ação ou da atualização automática), cada pendência pega de volta a sua conversa.

  Uso:
    cartao.append(...montar_cartao_da_pendencia(pendencia, ao_mudar));
      pendencia: {processamento_id, regra_id, linha, nome, nome_do_campo, pergunta, problema, sugestoes, origem, grupo,
                  nomes_do_grupo, pedido_do_banco}
      (sugestoes: [{texto, envia, acao?}]; com "acao", o clique não fala com o agente: "informar_pessoa_a_pessoa"
      abre a lista no próprio cartão (ADR-124); as outras viram o evento "acao-do-cartao-da-pendencia", que a tela
      trata, ex.: "descartar_e_enviar_outro";
      origem: o texto da linha cinza, ex.: "folha.xlsx · 24/09"; vazio = sem a linha;
      grupo: o do servidor, ou null; nomes_do_grupo: as pessoas do grupo, para o "Ver quem são", ou vazio;
      pedido_do_banco: true quando o banco apontou o problema, e o cartão ganha o selo "Pedido do banco", ADR-121)
    if (esta_no_modo_grupo(pendencia)) { ... }   // a tela mostra um cartão só para o grupo
    lugar.replaceChildren(...montar_avisos_de_resolvidos_agora(chaves_das_pendencias_abertas));
    if (alguma_conversa_em_andamento()) { ... }   // a atualização automática espera
*/

// Cada conversa guardada nesta página, pela chave da pendência (ver chave_da_conversa).
const conversas_guardadas = {};
// O que o agente mudou há pouco, pela chave da pendência: vira o aviso "Resolvido agora" quando a pendência some.
const resolvidos_agora = {};
// O relógio que atualiza o "Processando… N s" a cada segundo (ligado só enquanto alguma conversa espera o agente).
let relogio_do_processando = null;
// De quanto em quanto tempo o contador do "Processando" anda: 1 segundo.
const UM_SEGUNDO = 1000;
// Quantos balões a conversa mostra antes de recolher os mais antigos.
const BALOES_A_MOSTRA = 4;
// O selo dos balões do agente: o nome que a pessoa vê (no código, o agente é o Assistente de Correção)
const SELO_DO_AGENTE = "✦ Agente de validação";
// A resposta rápida que abre, no próprio cartão, a lista "Informar pessoa a pessoa" (ADR-124; a mesma do servidor)
const ACAO_INFORMAR_PESSOA_A_PESSOA = "informar_pessoa_a_pessoa";

/**
 * Cria um elemento com classe e texto (ajuda curta, para a conversa ficar legível).
 *
 * Recebe: tag; classe ("" = nenhuma); texto ("" = nenhum). Devolve: o elemento.
 */
function criar_elemento_da_conversa(tag, classe, texto) {
  const elemento = document.createElement(tag);
  // A classe, quando há
  if (classe) {
    elemento.className = classe;
  }
  // O texto, sempre como texto (nunca como HTML: o que a pessoa escreveu não vira código na página)
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * A chave que identifica a conversa de uma pendência: o envio, a regra, a linha e o campo (a mesma do servidor, em
 * services/conversas_das_pendencias.py).
 *
 * Recebe: pendencia — {processamento_id, regra_id, linha, campo}. Devolve: o texto da chave.
 * Ex.: {processamento_id: "a1b2", regra_id: "CPF_INVALIDO", linha: 7, campo: "cpf"} → "a1b2|CPF_INVALIDO|7|cpf".
 * Por que o campo: o arquivo sem 11 colunas obrigatórias gera 11 pendências
 * com a mesma regra e sem linha; sem o campo, os 11 cartões dividiam a mesma conversa.
 */
function chave_da_conversa(pendencia) {
  // Uma pendência já resolvida (filtro "Resolvidas"): a chave vem pronta do servidor
  if (pendencia.chave_fixa) {
    return pendencia.chave_fixa;
  }
  // No cartão do grupo, a conversa é uma só para todas as pessoas (na conferência, as linhas do grupo a dividem)
  if (esta_no_modo_grupo(pendencia)) {
    return "grupo|" + pendencia.grupo.chave;
  }
  return pendencia.processamento_id + "|" + pendencia.regra_id + "|" + pendencia.linha + "|" + (pendencia.campo || "");
}

// ===== Pendências em grupo (ADR-120) =====

// Os grupos que a pessoa preferiu responder uma a uma, pela chave do grupo (valem até a página ser recarregada).
const grupos_uma_a_uma = {};

/**
 * Diz se a pendência aparece no cartão do grupo: ela faz parte de um grupo (várias pessoas com o mesmo valor fora da
 * lista) e a pessoa não pediu para responder uma a uma.
 *
 * Recebe: pendencia — com grupo ({chave, quantidade, ...} ou null). Devolve: true ou false.
 */
function esta_no_modo_grupo(pendencia) {
  return Boolean(pendencia.grupo) && !(pendencia.grupo.chave in grupos_uma_a_uma);
}

/**
 * A linha que a conversa manda ao servidor: no grupo, a da pessoa que o representa (o servidor refaz o grupo a partir
 * dela); fora dele, a da própria pendência.
 *
 * Recebe: pendencia. Devolve: o número da linha (ou null, na pendência do arquivo inteiro).
 */
function linha_da_conversa(pendencia) {
  if (esta_no_modo_grupo(pendencia)) {
    return pendencia.grupo.linha_do_representante;
  }
  return pendencia.linha;
}

/**
 * A pendência como o cartão do grupo mostra: o número de pessoas no título, e a pergunta e as respostas rápidas do
 * grupo (que valem para todas).
 *
 * Recebe: pendencia — com grupo. Devolve: uma cópia com nome, pergunta e sugestoes do grupo.
 * Ex.: grupo de 23 com "Divorciado(a)" → nome "23 pessoas com o mesmo valor".
 */
function pendencia_do_cartao_do_grupo(pendencia) {
  const copia = Object.assign({}, pendencia);
  copia.nome = pendencia.grupo.quantidade + " pessoas com o mesmo valor";
  // O título do cartão do grupo (ex.: 'Ajuste na informação "Estado civil" de 4 pessoas'), quando o servidor manda
  copia.titulo_do_cartao = pendencia.grupo.titulo_do_cartao || "";
  copia.problema_do_cartao = pendencia.grupo.problema_do_cartao || "";
  copia.pergunta = pendencia.grupo.pergunta;
  copia.sugestoes = pendencia.grupo.sugestoes;
  return copia;
}

/**
 * Troca o jeito de responder um grupo: uma a uma (um cartão por pessoa) ou todas de uma vez (o cartão do grupo), e
 * pede à tela para montar a lista de novo.
 *
 * Recebe: chave_do_grupo; uma_a_uma — true ou false; ao_mudar — o que a tela faz para se refazer.
 * Devolve: uma promessa.
 */
async function responder_o_grupo(chave_do_grupo, uma_a_uma, ao_mudar) {
  if (uma_a_uma) {
    grupos_uma_a_uma[chave_do_grupo] = true;
  } else {
    delete grupos_uma_a_uma[chave_do_grupo];
  }
  await ao_mudar();
}

/**
 * A lista das pessoas do grupo, cada nome um botão que abre a ficha dela, com o campo do grupo em destaque.
 *
 * Recebe: pendencia — com processamento_id e campo; pessoas — [{nome, linha}]. Devolve: o elemento da lista.
 */
function montar_lista_das_pessoas_do_grupo(pendencia, pessoas) {
  const lista = criar_elemento_da_conversa("p", "nomes-do-grupo", "");
  for (let posicao = 0; posicao < pessoas.length; posicao = posicao + 1) {
    const pessoa = pessoas[posicao];
    // Uma vírgula entre os nomes
    if (posicao > 0) {
      lista.append(", ");
    }
    const botao = criar_elemento_da_conversa("button", "botao-nome nome-do-grupo", pessoa.nome);
    botao.type = "button";
    botao.dataset.fichaDaPessoa = String(pessoa.linha);
    botao.title = "Ver a ficha completa de " + pessoa.nome;
    // O clique abre a ficha da pessoa, com o campo do grupo em destaque
    botao.addEventListener("click", function () {
      abrir_ficha_da_pendencia(pendencia.processamento_id, pessoa.linha, pendencia.campo, botao);
    });
    lista.append(botao);
  }
  return lista;
}

/**
 * As ações do cartão do grupo: "Ver quem são (N)" (a lista de nomes abre e fecha) e "Responder uma a uma".
 *
 * Recebe: pendencia — com grupo e, se a tela souber, nomes_do_grupo ([{nome, linha}]); ao_mudar. Devolve: o elemento.
 */
function montar_acoes_do_grupo(pendencia, ao_mudar) {
  const lugar = criar_elemento_da_conversa("div", "acoes-do-grupo", "");
  const nomes = pendencia.nomes_do_grupo || [];
  // Quem são: só quando a tela mandou os nomes (Acompanhar); na conferência, as pessoas já estão na tabela
  if (nomes.length > 0) {
    const botao_dos_nomes = criar_elemento_da_conversa("button", "botao-nome", "Ver quem são (" + nomes.length + ")");
    botao_dos_nomes.type = "button";
    botao_dos_nomes.dataset.verQuemSao = "";
    botao_dos_nomes.setAttribute("aria-expanded", "false");
    const lista_de_nomes = montar_lista_das_pessoas_do_grupo(pendencia, nomes);
    lista_de_nomes.hidden = true;
    lista_de_nomes.dataset.nomesDoGrupo = "";
    // O clique mostra ou esconde os nomes
    botao_dos_nomes.addEventListener("click", function () {
      lista_de_nomes.hidden = !lista_de_nomes.hidden;
      botao_dos_nomes.setAttribute("aria-expanded", String(!lista_de_nomes.hidden));
    });
    lugar.append(botao_dos_nomes);
    lugar.append(lista_de_nomes);
  }
  // Para as exceções (ex.: uma das 23 é casada): um cartão por pessoa
  const botao_uma_a_uma = criar_elemento_da_conversa("button", "botao-nome", "Responder uma a uma");
  botao_uma_a_uma.type = "button";
  botao_uma_a_uma.dataset.responderUmaAUma = "";
  botao_uma_a_uma.addEventListener("click", function () {
    responder_o_grupo(pendencia.grupo.chave, true, ao_mudar);
  });
  lugar.prepend(botao_uma_a_uma);
  return lugar;
}

/**
 * No cartão de uma pessoa de um grupo respondido uma a uma: o botão para voltar a responder todas de uma vez.
 *
 * Recebe: pendencia — com grupo; ao_mudar. Devolve: o botão.
 */
function montar_botao_todas_de_uma_vez(pendencia, ao_mudar) {
  const texto = "Responder as " + pendencia.grupo.quantidade + " de uma vez";
  const botao = criar_elemento_da_conversa("button", "botao-nome botao-todas-de-uma-vez", texto);
  botao.type = "button";
  botao.dataset.responderTodasDeUmaVez = "";
  botao.addEventListener("click", function () {
    responder_o_grupo(pendencia.grupo.chave, false, ao_mudar);
  });
  return botao;
}

// ===== O título do cartão e a ficha completa da pessoa (ADR-120) =====

/**
 * O título do cartão: o que o servidor mandou (ex.: 'Ajuste na informação "Estado civil" de Ana Lima') ou, sem ele
 * (o protótipo aberto como arquivo), o nome da pessoa.
 *
 * Recebe: pendencia. Devolve: o texto.
 */
function titulo_do_cartao(pendencia) {
  return pendencia.titulo_do_cartao || pendencia.nome || "";
}

/**
 * Diz se o cartão ganha o botão "Ver a ficha completa": só a pendência de uma pessoa (com linha), de um envio de
 * verdade, com a página servida pelo servidor.
 *
 * Recebe: pendencia. Devolve: true ou false.
 */
function tem_ficha(pendencia) {
  const tem_linha = pendencia.linha !== null && pendencia.linha !== undefined;
  const pagina_do_servidor = window.location.protocol.startsWith("http");
  return tem_linha && Boolean(pendencia.processamento_id) && pagina_do_servidor;
}

/**
 * O botão "Ver a ficha completa" do cartão de uma pessoa.
 *
 * Recebe: pendencia. Devolve: o botão.
 */
function montar_botao_da_ficha(pendencia) {
  const botao = criar_elemento_da_conversa("button", "botao-nome botao-ver-ficha", "Ver a ficha completa");
  botao.type = "button";
  botao.dataset.verFicha = "";
  // O clique abre a ficha da pessoa, com a informação deste cartão em destaque
  botao.addEventListener("click", function () {
    abrir_ficha_da_pendencia(pendencia.processamento_id, pendencia.linha, campo_em_destaque_na_ficha(pendencia),
      botao);
  });
  return botao;
}

/**
 * A informação que a ficha destaca ("Em revisão"): a que o servidor mandou em campo_em_revisao. Nos problemas da
 * pessoa inteira (repetida, em outro arquivo), ele manda null, e nada fica em destaque. Sem o campo (protótipo), o
 * campo da pendência.
 *
 * Recebe: pendencia. Devolve: o nome técnico do campo, ou null.
 */
function campo_em_destaque_na_ficha(pendencia) {
  if (pendencia.campo_em_revisao !== undefined) {
    return pendencia.campo_em_revisao;
  }
  return pendencia.campo || null;
}

// A janela da ficha, criada na primeira vez (a mesma para as duas telas).
let janela_da_ficha_da_pendencia = null;
// O botão que abriu a ficha (o foco volta para ele ao fechar).
let botao_que_abriu_a_ficha = null;

/**
 * A janela da ficha: cria na primeira vez (cabeçalho com o nome, o lugar dos grupos e o botão Fechar) e devolve.
 *
 * Recebe: nada. Devolve: o <dialog>.
 */
function janela_da_ficha() {
  if (janela_da_ficha_da_pendencia) {
    return janela_da_ficha_da_pendencia;
  }
  const janela = criar_elemento_da_conversa("dialog", "janela-beneficio janela-ficha janela-ficha-da-pendencia", "");
  janela.id = "janela-ficha-da-pendencia";
  janela.setAttribute("aria-labelledby", "janela-ficha-da-pendencia-nome");
  const conteudo = criar_elemento_da_conversa("div", "janela-conteudo", "");
  // O cabeçalho: "Ficha completa", o nome e a linha do arquivo
  const cabecalho = criar_elemento_da_conversa("div", "janela-cabecalho", "");
  const textos = criar_elemento_da_conversa("div", "janela-cabecalho-textos", "");
  textos.append(criar_elemento_da_conversa("span", "sobretitulo", "Ficha completa"));
  const nome = criar_elemento_da_conversa("h2", "janela-titulo", "");
  nome.id = "janela-ficha-da-pendencia-nome";
  nome.dataset.nomeDaFicha = "";
  textos.append(nome);
  const resumo = criar_elemento_da_conversa("p", "janela-resumo", "");
  resumo.dataset.resumoDaFicha = "";
  textos.append(resumo);
  cabecalho.append(textos);
  conteudo.append(cabecalho);
  // O lugar dos grupos de campos (ou do "carregando" e do erro)
  const grupos = criar_elemento_da_conversa("div", "ficha-grupos", "");
  grupos.dataset.gruposDaFicha = "";
  conteudo.append(grupos);
  // O botão Fechar (o Esc também fecha: é o jeito do <dialog>)
  const botoes = criar_elemento_da_conversa("div", "janela-botoes", "");
  const fechar = criar_elemento_da_conversa("button", "botao botao-contorno", "Fechar");
  fechar.type = "button";
  fechar.dataset.fecharFichaDaPendencia = "";
  fechar.addEventListener("click", function () {
    janela.close();
  });
  botoes.append(fechar);
  conteudo.append(botoes);
  janela.append(conteudo);
  // Ao fechar (pelo botão ou pelo Esc), o foco volta para o botão que abriu
  janela.addEventListener("close", function () {
    if (botao_que_abriu_a_ficha && botao_que_abriu_a_ficha.isConnected) {
      botao_que_abriu_a_ficha.focus();
    }
  });
  document.body.append(janela);
  janela_da_ficha_da_pendencia = janela;
  return janela;
}

/**
 * Abre a ficha completa de uma pessoa do envio, com a informação em revisão em destaque.
 *
 * Recebe: processamento_id; linha — a linha da pessoa no arquivo; campo — o campo em revisão (fica em destaque);
 *         botao — o que foi clicado (o foco volta para ele). Devolve: uma promessa.
 */
async function abrir_ficha_da_pendencia(processamento_id, linha, campo, botao) {
  const janela = janela_da_ficha();
  botao_que_abriu_a_ficha = botao;
  const grupos = janela.querySelector("[data-grupos-da-ficha]");
  // Enquanto o servidor responde: "Carregando a ficha..."
  janela.querySelector("[data-nome-da-ficha]").textContent = "";
  janela.querySelector("[data-resumo-da-ficha]").textContent = "";
  grupos.replaceChildren(criar_elemento_da_conversa("p", "ficha-carregando", "Carregando a ficha..."));
  if (!janela.open) {
    janela.showModal();
  }
  const endereco = "/api/empresa/cadastro/" + encodeURIComponent(processamento_id) + "/ficha?linha=" +
    encodeURIComponent(linha);
  // try/catch: servidor fora do ar vira a mensagem de erro, não quebra a tela
  let ficha = null;
  try {
    const resposta = await fetch(endereco);
    if (resposta.ok) {
      ficha = await resposta.json();
    }
  } catch (erro) {
    ficha = null;
  }
  if (ficha === null) {
    const aviso_de_erro = criar_elemento_da_conversa("p", "erro-pendencia", "Não foi possível carregar a ficha agora.");
    grupos.replaceChildren(aviso_de_erro);
    return;
  }
  desenhar_a_ficha(janela, ficha, campo);
}

/**
 * Desenha a ficha na janela: o nome, a linha e os grupos de campos, com o campo em revisão em destaque.
 *
 * Recebe: janela; ficha — {linha, nome, grupos: [{grupo, campos: [...]}]}; campo — o campo em revisão.
 * Devolve: nada. A janela rola até o campo em destaque.
 */
function desenhar_a_ficha(janela, ficha, campo) {
  janela.querySelector("[data-nome-da-ficha]").textContent = ficha.nome || "Pessoa da linha " + ficha.linha;
  janela.querySelector("[data-resumo-da-ficha]").textContent =
    "Linha " + ficha.linha + " do arquivo · os dados como o sistema está considerando agora";
  const grupos = janela.querySelector("[data-grupos-da-ficha]");
  const partes = [];
  for (const grupo of ficha.grupos) {
    partes.push(montar_grupo_da_ficha_da_pendencia(grupo, campo));
  }
  grupos.replaceChildren(...partes);
  // Rola até o campo em destaque (no meio da janela)
  const em_destaque = grupos.querySelector("[data-campo-em-revisao]");
  if (em_destaque) {
    em_destaque.scrollIntoView({ block: "center" });
  }
}

/**
 * Um grupo da ficha (ex.: "Funcionário"), com cada campo numa linha: o nome e o valor.
 *
 * Recebe: grupo — {grupo, campos}; campo_em_revisao. Devolve: o <section>.
 */
function montar_grupo_da_ficha_da_pendencia(grupo, campo_em_revisao) {
  const secao = criar_elemento_da_conversa("section", "ficha-grupo", "");
  secao.append(criar_elemento_da_conversa("h3", "ficha-grupo-titulo", grupo.grupo));
  const lista = criar_elemento_da_conversa("div", "campos-da-ficha", "");
  for (const campo of grupo.campos) {
    lista.append(montar_campo_da_ficha(campo, campo.campo === campo_em_revisao));
  }
  secao.append(lista);
  return secao;
}

/**
 * Uma linha da ficha: o nome do campo e o valor (vazio = "—"). O campo em revisão ganha destaque, o selo "Em
 * revisão" e o que veio no arquivo; os outros com pendência, a marca "Também com pendência".
 *
 * Recebe: campo — {campo, nome, valor, obrigatorio, com_pendencia, valor_lido}; em_revisao — true no campo do
 *         cartão. Devolve: o elemento.
 */
function montar_campo_da_ficha(campo, em_revisao) {
  let classe = "campo-da-ficha";
  if (em_revisao) {
    classe = classe + " campo-em-revisao";
  } else if (campo.com_pendencia) {
    classe = classe + " campo-com-pendencia";
  }
  const linha = criar_elemento_da_conversa("div", classe, "");
  linha.dataset.campoDaFicha = campo.campo;
  // O nome do campo (com * quando é obrigatório)
  let nome = campo.nome;
  if (campo.obrigatorio) {
    nome = nome + " *";
  }
  const nome_do_campo = criar_elemento_da_conversa("span", "nome-do-campo-da-ficha", nome);
  const valor = criar_elemento_da_conversa("span", "valor-do-campo-da-ficha", campo.valor || "—");
  linha.append(nome_do_campo, valor);
  // O campo em revisão: o selo e o que veio no arquivo
  if (em_revisao) {
    linha.dataset.campoEmRevisao = "";
    nome_do_campo.prepend(criar_elemento_da_conversa("span", "selo-em-revisao", "Em revisão"));
    if (campo.valor_lido) {
      linha.append(criar_elemento_da_conversa("span", "veio-no-arquivo",
        "No arquivo veio: \"" + campo.valor_lido + "\""));
    }
  } else if (campo.com_pendencia) {
    linha.append(criar_elemento_da_conversa("span", "tambem-com-pendencia", "Também com pendência"));
  }
  return linha;
}

/**
 * A conversa guardada de uma chave; cria uma vazia na primeira vez.
 *
 * Recebe: chave. Devolve: {falas, inteira, rascunho, processando_desde, devolver_o_foco, ao_mudar,
 *   lista_pessoa_a_pessoa}.
 *   falas: [{quem: "empresa" | "ia" | "erro", texto, fontes, aplicado, recusado, remapeado}];
 *   inteira: true quando a pessoa pediu para ver todos os balões (senão, só os últimos BALOES_A_MOSTRA);
 *   processando_desde: a hora (em milissegundos) em que a mensagem saiu, ou null quando não espera o agente;
 *   devolver_o_foco: true depois de uma resposta, para o cursor voltar à caixa quando ela for desenhada de novo;
 *   lista_pessoa_a_pessoa: a lista "Informar pessoa a pessoa" aberta no cartão (as pessoas, o que foi digitado e
 *     marcado), ou null quando fechada (ver abrir_lista_pessoa_a_pessoa).
 */
function conversa_guardada(chave) {
  // Primeira vez desta pendência: uma conversa vazia
  if (!(chave in conversas_guardadas)) {
    conversas_guardadas[chave] = {
      falas: [], inteira: false, rascunho: "", processando_desde: null, devolver_o_foco: false, ao_mudar: null,
      lista_pessoa_a_pessoa: null,
    };
  }
  return conversas_guardadas[chave];
}

/**
 * Diz se alguma conversa está esperando a resposta do agente (a atualização automática não refaz a lista nessa hora).
 *
 * Recebe: nada. Devolve: true ou false.
 */
function alguma_conversa_em_andamento() {
  // Procura uma conversa com a mensagem ainda sem resposta
  for (const chave in conversas_guardadas) {
    if (conversas_guardadas[chave].processando_desde !== null) {
      return true;
    }
  }
  return false;
}

/**
 * O endereço das rotas do assistente de um envio.
 *
 * Recebe: processamento_id. Devolve: o texto. Ex.: "/api/empresa/cadastro/a1b2/assistente".
 */
function endereco_do_assistente(processamento_id) {
  return "/api/empresa/cadastro/" + encodeURIComponent(processamento_id) + "/assistente";
}

/**
 * Pede algo às rotas do assistente e devolve {ok, dados}. Erro sem JSON vira uma mensagem geral.
 *
 * Recebe: endereco; corpo — o que mandar (vai como JSON). Devolve: uma promessa de {ok, dados}.
 */
async function pedir_ao_assistente(endereco, corpo) {
  // try/catch: servidor fora do ar vira uma fala de erro, não quebra a tela
  try {
    const resposta = await fetch(endereco, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo),
    });
    const dados = await resposta.json();
    return { ok: resposta.ok, dados: dados };
  } catch (erro) {
    return { ok: false, dados: { detail: "Não consegui falar com o servidor agora. Tente de novo." } };
  }
}

/**
 * O texto de erro que o servidor mandou (uma frase) ou uma mensagem geral.
 *
 * Recebe: dados — a resposta do servidor. Devolve: o texto.
 */
function texto_do_erro_do_assistente(dados) {
  // Erro de regra: o servidor já manda a frase pronta
  if (dados && typeof dados.detail === "string") {
    return dados.detail;
  }
  return "Não foi possível agora. Tente de novo.";
}

// ===== O cartão =====

/**
 * As partes do cartão de uma pendência: o cabeçalho (nome e campo), a conversa e a linha cinza.
 *
 * Recebe: pendencia — ver o "Uso" no alto do arquivo; ao_mudar — o que a tela faz depois que o agente mudou algo.
 * Devolve: a lista de elementos, para a tela pôr dentro do cartão dela (Acompanhar: <article>; Cadastrar: <div>).
 */
function montar_cartao_da_pendencia(pendencia_recebida, ao_mudar) {
  // Várias pessoas com o mesmo valor: o cartão é do grupo (título, pergunta e respostas valem para todas)
  const no_grupo = esta_no_modo_grupo(pendencia_recebida);
  let pendencia = pendencia_recebida;
  if (no_grupo) {
    pendencia = pendencia_do_cartao_do_grupo(pendencia_recebida);
  }
  const partes = [];
  // Em cima: o título do ajuste (ex.: 'Ajuste na informação "Estado civil" de Ana Lima') e, no
  // cartão de uma pessoa, o botão "Ver a ficha completa" à direita
  const cabecalho = criar_elemento_da_conversa("div", "ajuste-cabecalho", "");
  cabecalho.append(criar_elemento_da_conversa("span", "ajuste-titulo", titulo_do_cartao(pendencia)));
  // O banco apontou um problema nesta pessoa (ADR-121): o selo avisa que o pedido veio do banco, e não da leitura
  if (pendencia.pedido_do_banco) {
    const selo = criar_elemento_da_conversa("span", "selo selo-pequeno selo-atencao selo-pedido-do-banco",
      "Pedido do banco");
    // A marca que os roteiros de clique procuram
    selo.dataset.seloPedidoDoBanco = "";
    cabecalho.append(selo);
  }
  if (!no_grupo && tem_ficha(pendencia)) {
    cabecalho.append(montar_botao_da_ficha(pendencia));
  }
  partes.push(cabecalho);
  // Embaixo do título, o problema do cartão, curto e só dele (um cartão nunca trata mais de um problema, ADR-120).
  // Ex.: "Problema: a pessoa também está em outro arquivo que ainda não foi ao banco"
  if (pendencia.problema_do_cartao) {
    const problema = criar_elemento_da_conversa("p", "ajuste-problema", "");
    problema.dataset.problemaDoCartao = "";
    problema.append(criar_elemento_da_conversa("strong", "", "Problema: "), pendencia.problema_do_cartao);
    partes.push(problema);
  }
  // A conversa: a pergunta do agente, as respostas, as respostas rápidas e a caixa
  partes.push(montar_conversa_da_pendencia(pendencia, ao_mudar));
  // No grupo: ver quem são e responder uma a uma; numa pessoa de um grupo aberto: voltar a responder todas juntas
  if (no_grupo) {
    partes.push(montar_acoes_do_grupo(pendencia, ao_mudar));
  } else if (pendencia.grupo) {
    partes.push(montar_botao_todas_de_uma_vez(pendencia, ao_mudar));
  }
  // Embaixo, cinza e pequeno: de que arquivo e de quando
  if (pendencia.origem) {
    partes.push(criar_elemento_da_conversa("p", "ajuste-origem", pendencia.origem));
  }
  return partes;
}

// ===== Desenhar a conversa =====

/**
 * Monta a conversa de uma pendência (sempre aberta).
 *
 * Recebe: pendencia; ao_mudar — o que a tela faz depois que o agente mudou algo (refaz a lista e os números).
 * Devolve: o elemento da conversa.
 */
function montar_conversa_da_pendencia(pendencia, ao_mudar) {
  const chave = chave_da_conversa(pendencia);
  // A tela pode ter mudado o "ao_mudar": guarda o mais novo (o Desfazer do aviso usa)
  conversa_guardada(chave).ao_mudar = ao_mudar;
  const bloco = criar_elemento_da_conversa("div", "conversa-ia-pendencia", "");
  bloco.dataset.chaveConversa = chave;
  // Guarda a pendência no próprio bloco: redesenhar precisa dela
  bloco.dados_da_pendencia = pendencia;
  desenhar_conversa(bloco);
  return bloco;
}

/**
 * Desenha (ou redesenha) a conversa a partir do que está guardado: os balões, as respostas rápidas e a caixa.
 *
 * Recebe: bloco — o elemento da conversa. Devolve: nada.
 */
function desenhar_conversa(bloco) {
  const pendencia = bloco.dados_da_pendencia;
  const guardada = conversa_guardada(bloco.dataset.chaveConversa);
  const baloes = montar_baloes(pendencia, guardada);
  const partes = [];
  // Muitos balões: os mais antigos se recolhem, e o botão mostra a conversa inteira (ou recolhe de novo)
  if (baloes.length > BALOES_A_MOSTRA) {
    partes.push(montar_botao_da_conversa_inteira(bloco, guardada, baloes.length));
  }
  const historico = criar_elemento_da_conversa("div", "historico-conversa-ia", "");
  historico.append(...baloes_a_mostra(baloes, guardada));
  partes.push(historico);
  // Esperando o agente: o balão com os pontinhos e o contador
  if (guardada.processando_desde !== null) {
    historico.append(montar_balao_do_processando(guardada));
  }
  partes.push(montar_respostas_rapidas(bloco, pendencia, guardada));
  // A lista "Informar pessoa a pessoa", quando aberta (ADR-124); enquanto o servidor grava, ela sai da tela
  const lista = guardada.lista_pessoa_a_pessoa;
  const mostrar_a_lista = lista !== null && !lista.enviada;
  if (mostrar_a_lista) {
    partes.push(montar_lista_pessoa_a_pessoa(bloco, pendencia, lista));
  }
  const formulario = montar_formulario(pendencia, guardada);
  partes.push(formulario);
  bloco.replaceChildren(...partes);
  // A lista acabou de chegar: o cursor vai para a caixa da primeira pessoa (a pessoa já pode digitar)
  if (mostrar_a_lista && lista.focar && !lista.carregando) {
    lista.focar = false;
    const primeira_caixa = bloco.querySelector("[data-valor-da-pessoa]");
    if (primeira_caixa) {
      primeira_caixa.focus();
    }
    return;
  }
  // Depois de uma resposta, o cursor volta para a caixa (a pessoa pode responder de novo sem clicar)
  if (guardada.devolver_o_foco && guardada.processando_desde === null) {
    guardada.devolver_o_foco = false;
    formulario.querySelector("[data-caixa-da-conversa]").focus();
  }
}

/**
 * Todos os balões da conversa, em ordem: a pergunta do agente e depois cada fala.
 *
 * Recebe: pendencia; guardada. Devolve: a lista de elementos.
 */
function montar_baloes(pendencia, guardada) {
  // A pergunta; enquanto o servidor não manda, a mensagem do Validador
  const pergunta = montar_balao_da_ia(pendencia.pergunta || pendencia.problema, "");
  pergunta.dataset.perguntaDaPendencia = "";
  // A pergunta que o Agente Leitor ou o Agente Conferidor fez ao ler o documento ganha o joinha (ADR-151)
  acrescentar_opiniao_na_pergunta(pergunta, pendencia);
  const baloes = [pergunta];
  for (const fala of guardada.falas) {
    baloes.push(montar_fala(pendencia, fala));
  }
  return baloes;
}

/**
 * Os balões que ficam à vista: todos (conversa inteira) ou só os últimos BALOES_A_MOSTRA.
 *
 * Recebe: baloes; guardada. Devolve: a lista de elementos.
 */
function baloes_a_mostra(baloes, guardada) {
  if (guardada.inteira || baloes.length <= BALOES_A_MOSTRA) {
    return baloes;
  }
  return baloes.slice(baloes.length - BALOES_A_MOSTRA);
}

/**
 * O botão "Ver a conversa inteira (N)" (ou "Recolher o começo da conversa", com ela inteira à vista).
 *
 * Recebe: bloco; guardada; total — quantos balões a conversa tem. Devolve: o botão.
 */
function montar_botao_da_conversa_inteira(bloco, guardada, total) {
  let texto = "Ver a conversa inteira (" + total + ")";
  if (guardada.inteira) {
    texto = "Recolher o começo da conversa";
  }
  const botao = criar_elemento_da_conversa("button", "botao-nome botao-conversa-inteira", texto);
  botao.type = "button";
  botao.dataset.conversaInteira = "";
  botao.setAttribute("aria-expanded", String(guardada.inteira));
  // O clique troca e redesenha (a escolha fica guardada: volta igual quando a lista é refeita)
  botao.addEventListener("click", function () {
    guardada.inteira = !guardada.inteira;
    desenhar_conversa(bloco);
  });
  return botao;
}

/**
 * Um balão do agente, à esquerda, com o selo "✦ Agente de validação".
 *
 * Recebe: texto; classe_extra ("" = nenhuma; ex.: "fala-recusada" para o balão âmbar). Devolve: o elemento.
 */
function montar_balao_da_ia(texto, classe_extra) {
  let classe = "balao balao-ia fala-ia";
  if (classe_extra) {
    classe = classe + " " + classe_extra;
  }
  const balao = criar_elemento_da_conversa("div", classe, "");
  balao.append(criar_elemento_da_conversa("span", "selo-ia", SELO_DO_AGENTE));
  balao.append(criar_elemento_da_conversa("p", "", texto));
  return balao;
}

/**
 * Um balão da pessoa, à direita, marcado "você".
 *
 * Recebe: texto. Devolve: o elemento.
 */
function montar_balao_da_pessoa(texto) {
  const balao = criar_elemento_da_conversa("div", "balao balao-voce fala-empresa", "");
  balao.append(criar_elemento_da_conversa("p", "", texto));
  balao.append(criar_elemento_da_conversa("span", "marca-voce", "você"));
  return balao;
}

/**
 * Uma fala da conversa, no balão certo. A do agente traz as fontes e, quando mudou algo, o Desfazer.
 *
 * Recebe: pendencia; fala. Devolve: o elemento do balão.
 */
function montar_fala(pendencia, fala) {
  // A pessoa: balão à direita
  if (fala.quem === "empresa") {
    return montar_balao_da_pessoa(fala.texto);
  }
  // Erro ou recusa: balão âmbar do agente
  let classe_extra = "";
  if (fala.quem === "erro") {
    classe_extra = "fala-recusada fala-erro";
  } else if (fala.recusado) {
    classe_extra = "fala-recusada";
  }
  const balao = montar_balao_da_ia(fala.texto, classe_extra);
  // As fontes do layout que apoiaram a resposta (RAG), em letra menor
  if (fala.fontes && fala.fontes.length > 0) {
    balao.append(criar_elemento_da_conversa("p", "fontes-da-ia", "Fontes: " + fala.fontes.join("; ")));
  }
  // A pergunta de confirmação ainda aberta: os dois botões dentro do balão
  if (fala.confirmacao && !fala.confirmacao.decidida) {
    balao.append(montar_botoes_da_confirmacao(pendencia, fala));
  }
  // O que o agente mudou: o Desfazer (ou "Desfeito") dentro do balão
  if (fala.aplicado) {
    balao.classList.add("mudanca-da-ia");
    balao.append(montar_desfazer_do_balao(pendencia, fala.aplicado));
  }
  // O agente pediu para reler uma coluna: as colunas voltam para o aceite
  if (fala.remapeado) {
    const link = criar_elemento_da_conversa("a", "link-seta", "Conferir as colunas de novo");
    link.href = "cadastrar.html?envio=" + encodeURIComponent(pendencia.processamento_id);
    balao.append(link);
  }
  // O agente encerrou a conversa depois das respostas sem valor (ADR-153): a marca fica no balão dele
  if (fala.encerrada) {
    balao.append(montar_marca_de_conversa_encerrada());
  }
  // A resposta do agente ganha o joinha, embaixo de tudo (js/opiniao_dos_agentes.js, ADR-151)
  acrescentar_opiniao_na_resposta(balao, pendencia, fala);
  return balao;
}

/**
 * A marca "Conversa encerrada" no balão do agente que encerrou a conversa (ADR-153). A pendência continua aberta.
 *
 * Recebe: nada. Devolve: o elemento.
 */
function montar_marca_de_conversa_encerrada() {
  const marca = criar_elemento_da_conversa("p", "conversa-encerrada",
    "Conversa encerrada. A pendência continua aberta.");
  // A marca que os roteiros de clique procuram
  marca.dataset.conversaEncerrada = "";
  return marca;
}

/**
 * Os dois botões de uma pergunta de confirmação do agente (ex.: "Sim, não cadastrar" e "Cancelar").
 *
 * Recebe: pendencia; fala — com confirmacao {correcao_id, sim, nao}. Devolve: o elemento com os dois botões.
 */
function montar_botoes_da_confirmacao(pendencia, fala) {
  const lugar = criar_elemento_da_conversa("div", "confirmacao-do-balao", "");
  const sim = criar_elemento_da_conversa("button", "botao botao-principal botao-pequeno", fala.confirmacao.sim);
  sim.type = "button";
  sim.dataset.confirmarSim = "";
  const nao = criar_elemento_da_conversa("button", "botao botao-contorno botao-pequeno", fala.confirmacao.nao);
  nao.type = "button";
  nao.dataset.confirmarNao = "";
  // Esperando outra resposta do agente: os botões ficam parados
  const conversa = conversa_guardada(chave_da_conversa(pendencia));
  sim.disabled = conversa.processando_desde !== null;
  nao.disabled = conversa.processando_desde !== null;
  sim.addEventListener("click", function () {
    responder_a_confirmacao(pendencia, fala, true);
  });
  nao.addEventListener("click", function () {
    responder_a_confirmacao(pendencia, fala, false);
  });
  lugar.append(sim, nao);
  return lugar;
}

/**
 * O Desfazer dentro do balão do agente: o botão, ou "Desfeito" depois do clique, ou nada quando não dá para desfazer.
 *
 * Recebe: pendencia; aplicado — {resumo, desfazer, desfeito}. Devolve: o elemento (vazio quando não há o que mostrar).
 */
function montar_desfazer_do_balao(pendencia, aplicado) {
  const lugar = criar_elemento_da_conversa("div", "desfazer-do-balao", "");
  // Já desfeito: só o registro
  if (aplicado.desfeito) {
    lugar.append(criar_elemento_da_conversa("strong", "", "Desfeito"));
    return lugar;
  }
  // Dá para desfazer: o botão
  if (aplicado.desfazer) {
    lugar.append(montar_botao_desfazer(pendencia, aplicado));
  }
  return lugar;
}

/**
 * O botão Desfazer de uma mudança do agente (no balão e no aviso "Resolvido agora").
 *
 * Recebe: pendencia; aplicado. Devolve: o botão.
 */
function montar_botao_desfazer(pendencia, aplicado) {
  const botao = criar_elemento_da_conversa("button", "botao botao-contorno botao-pequeno", "Desfazer");
  botao.type = "button";
  botao.dataset.desfazerMudanca = "";
  botao.addEventListener("click", function () {
    desfazer_o_que_a_ia_fez(botao, pendencia, aplicado);
  });
  return botao;
}

/**
 * O balão do agente enquanto ele trabalha: os pontinhos e o "Processando… N s", que anda a cada segundo.
 *
 * Recebe: guardada. Devolve: o elemento.
 */
function montar_balao_do_processando(guardada) {
  const balao = criar_elemento_da_conversa("div", "balao balao-ia balao-processando", "");
  balao.append(criar_elemento_da_conversa("span", "selo-ia", SELO_DO_AGENTE));
  // Os três pontinhos que "pulam" (css/estilos.css)
  const pontinhos = criar_elemento_da_conversa("span", "pontinhos", "");
  pontinhos.setAttribute("aria-hidden", "true");
  pontinhos.append(criar_elemento_da_conversa("span", "", ""), criar_elemento_da_conversa("span", "", ""),
    criar_elemento_da_conversa("span", "", ""));
  const contador = criar_elemento_da_conversa("span", "processando-ia cronometro-ia", "");
  contador.dataset.contadorProcessando = String(guardada.processando_desde);
  contador.setAttribute("role", "status");
  escrever_segundos_do_processando(contador);
  balao.append(pontinhos, contador);
  return balao;
}

/**
 * Escreve no contador quantos segundos já se passaram desde que a mensagem saiu.
 *
 * Recebe: contador — o elemento (a hora de saída fica em data-contador-processando). Devolve: nada.
 */
function escrever_segundos_do_processando(contador) {
  const saiu_em = Number(contador.dataset.contadorProcessando);
  // Segundos inteiros desde a saída
  const segundos = Math.floor((Date.now() - saiu_em) / UM_SEGUNDO);
  contador.textContent = "Processando… " + segundos + " s";
}

/**
 * Faz andar todos os contadores na tela; sem ninguém esperando, desliga o relógio.
 *
 * Recebe: nada. Devolve: nada.
 */
function andar_os_contadores() {
  for (const contador of document.querySelectorAll("[data-contador-processando]")) {
    escrever_segundos_do_processando(contador);
  }
  // Ninguém mais esperando o agente: o relógio para
  if (!alguma_conversa_em_andamento()) {
    clearInterval(relogio_do_processando);
    relogio_do_processando = null;
  }
}

/**
 * As respostas rápidas (pílulas): um clique responde ao agente ou põe a frase na caixa para completar.
 *
 * Recebe: bloco; pendencia — com sugestoes [{texto, envia}]; guardada. Devolve: o elemento (vazio sem sugestões).
 * Ex.: "Solteiro" e "Não cadastrar esta pessoa" (respondem na hora); "O valor para todos é: " (vai para a caixa).
 */
function montar_respostas_rapidas(bloco, pendencia, guardada) {
  const lugar = criar_elemento_da_conversa("div", "respostas-rapidas", "");
  const sugestoes = pendencia.sugestoes || [];
  for (const sugestao of sugestoes) {
    const botao = criar_elemento_da_conversa("button", "resposta-rapida", sugestao.texto);
    botao.type = "button";
    botao.dataset.sugestaoDaConversa = "";
    // Um botão de ação (ex.: descartar a leitura e enviar outro arquivo) leva o nome dela, para a tela achar
    if (sugestao.acao) {
      botao.dataset.acaoDoCartao = sugestao.acao;
    }
    // Esperando o agente: nada de mandar outra
    botao.disabled = guardada.processando_desde !== null;
    botao.addEventListener("click", function () {
      usar_sugestao(bloco, pendencia, sugestao);
    });
    lugar.append(botao);
  }
  return lugar;
}

/**
 * O clique numa resposta rápida: faz a ação da tela ("acao"), manda a frase ao agente ("envia") ou a põe na caixa
 * para completar.
 *
 * Recebe: bloco; pendencia; sugestao — {texto, envia, acao?}. Devolve: nada.
 */
function usar_sugestao(bloco, pendencia, sugestao) {
  // "Informar pessoa a pessoa" (ADR-124): a lista abre dentro do próprio cartão
  if (sugestao.acao === ACAO_INFORMAR_PESSOA_A_PESSOA) {
    abrir_lista_pessoa_a_pessoa(bloco, pendencia);
    return;
  }
  // Um botão que faz algo na tela, sem mensagem ao agente (ex.: "Descartar a leitura e enviar outro arquivo", na
  // coluna que o arquivo inteiro não trouxe): a tela que mostra o cartão cuida da ação
  if (sugestao.acao) {
    document.dispatchEvent(new CustomEvent("acao-do-cartao-da-pendencia", {
      detail: { acao: sugestao.acao, processamento_id: pendencia.processamento_id },
    }));
    return;
  }
  // Frase completa: vira o balão da pessoa e vai para o agente
  if (sugestao.envia) {
    mandar_mensagem(pendencia, sugestao.texto);
    return;
  }
  // Frase para completar (ex.: o valor para todos): vai para a caixa
  const caixa = bloco.querySelector("[data-caixa-da-conversa]");
  caixa.value = sugestao.texto;
  conversa_guardada(bloco.dataset.chaveConversa).rascunho = caixa.value;
  caixa.focus();
  // Frase com "..." (ex.: "A matrícula tem ... dígitos"): o "..." fica marcado, e o que a pessoa digitar entra no lugar
  const lugar_do_valor = caixa.value.indexOf("...");
  if (lugar_do_valor >= 0) {
    caixa.setSelectionRange(lugar_do_valor, lugar_do_valor + 3);
    return;
  }
  // Senão, o cursor no fim da frase, onde a pessoa vai escrever
  caixa.setSelectionRange(caixa.value.length, caixa.value.length);
}

// ===== Informar pessoa a pessoa (ADR-124) =====
//
// Quando a informação que o arquivo inteiro não trouxe não é a mesma para todos (ex.: duas unidades) ou é de cada
// pessoa (ex.: o CPF), a empresa diz o valor de cada funcionário numa lista dentro do cartão. A chave de cada pessoa é
// a LINHA do arquivo (não o CPF, que pode estar faltando); o nome abre a ficha, para reconhecer quem é. No dado da
// empresa, dá para marcar várias pessoas e usar o mesmo valor nelas ("Usar nos marcados"). Salvar vira uma rodada da
// conversa: o balão "Informei pessoa a pessoa (N pessoas).", o "Pronto: ..." do agente e o Desfazer do lote inteiro.

/**
 * O endereço da lista de uma pendência (as pessoas do envio, para a coluna do campo da pendência).
 *
 * Recebe: pendencia. Devolve: o texto. Ex.: "/api/empresa/cadastro/a1b2/pessoas_para_informar?campo=cpf".
 */
function endereco_da_lista_pessoa_a_pessoa(pendencia) {
  return "/api/empresa/cadastro/" + encodeURIComponent(pendencia.processamento_id) +
    "/pessoas_para_informar?campo=" + encodeURIComponent(pendencia.campo || "");
}

/**
 * "1 pessoa" ou "N pessoas".
 *
 * Recebe: quantidade. Devolve: o texto.
 */
function texto_de_pessoas(quantidade) {
  if (quantidade === 1) {
    return "1 pessoa";
  }
  return quantidade + " pessoas";
}

/**
 * Diz se alguma lista "Informar pessoa a pessoa" está aberta (a atualização automática não refaz a lista nessa hora).
 *
 * Recebe: nada. Devolve: true ou false.
 */
function alguma_lista_pessoa_a_pessoa_aberta() {
  for (const chave in conversas_guardadas) {
    if (conversas_guardadas[chave].lista_pessoa_a_pessoa) {
      return true;
    }
  }
  return false;
}

/**
 * Abre a lista dentro do cartão: busca as pessoas do envio e desenha uma caixa para cada uma.
 *
 * Recebe: bloco — a conversa do cartão; pendencia. Devolve: uma promessa.
 * A lista fica guardada na conversa (guardada.lista_pessoa_a_pessoa): o que a pessoa digitou volta se a tela for
 * refeita, e a atualização automática espera enquanto ela está aberta.
 */
async function abrir_lista_pessoa_a_pessoa(bloco, pendencia) {
  const chave = bloco.dataset.chaveConversa;
  const guardada = conversa_guardada(chave);
  // Já aberta: nada a buscar de novo
  if (guardada.lista_pessoa_a_pessoa !== null) {
    return;
  }
  const lista = {
    carregando: true, erro: "", informacao: "", igual_para_todos: false, pessoas: [], valores: {}, marcados: {},
    valor_dos_marcados: "", enviada: false, focar: true,
  };
  guardada.lista_pessoa_a_pessoa = lista;
  redesenhar_a_chave(chave);
  // try/catch: servidor fora do ar vira o aviso de erro na lista, não quebra a tela
  try {
    const resposta = await fetch(endereco_da_lista_pessoa_a_pessoa(pendencia));
    const dados = await resposta.json();
    if (resposta.ok) {
      lista.informacao = dados.informacao;
      lista.igual_para_todos = Boolean(dados.igual_para_todos);
      lista.pessoas = dados.pessoas;
    } else {
      lista.erro = texto_do_erro_do_assistente(dados);
    }
  } catch (erro) {
    lista.erro = "Não consegui buscar as pessoas agora. Tente de novo.";
  }
  lista.carregando = false;
  redesenhar_a_chave(chave);
}

/**
 * A lista, como está guardada: o título, a marcação em lote (só no dado da empresa), uma linha por pessoa, o aviso de
 * erro e os botões "Salvar" e "Cancelar".
 *
 * Recebe: bloco; pendencia; lista — a guardada. Devolve: o elemento.
 */
function montar_lista_pessoa_a_pessoa(bloco, pendencia, lista) {
  const caixa = criar_elemento_da_conversa("div", "lista-pessoa-a-pessoa", "");
  caixa.dataset.listaPessoaAPessoa = "";
  // Buscando as pessoas: só o aviso
  if (lista.carregando) {
    caixa.append(criar_elemento_da_conversa("p", "lista-pessoa-a-pessoa-dica", "Buscando as pessoas do arquivo…"));
    return caixa;
  }
  // O título e a dica (sem pessoas, por um erro, só o aviso e o Cancelar)
  if (lista.pessoas.length > 0) {
    caixa.append(criar_elemento_da_conversa("p", "lista-pessoa-a-pessoa-titulo",
      'Informe "' + lista.informacao + '" de cada pessoa'));
    caixa.append(criar_elemento_da_conversa("p", "lista-pessoa-a-pessoa-dica",
      "Quem ficar em branco continua sem esta informação e ganha um cartão de revisão."));
  }
  // No dado da empresa, o mesmo valor para várias pessoas de uma vez (ex.: as da mesma unidade)
  if (lista.igual_para_todos && lista.pessoas.length > 0) {
    caixa.append(montar_lote_dos_marcados(bloco, lista));
  }
  const linhas = criar_elemento_da_conversa("div", "lista-pessoa-a-pessoa-linhas", "");
  for (const pessoa of lista.pessoas) {
    linhas.append(montar_linha_da_pessoa(bloco, pendencia, lista, pessoa));
  }
  if (lista.pessoas.length > 0) {
    caixa.append(linhas);
  }
  // O aviso de erro (ex.: nenhum valor preenchido; o servidor não achou as pessoas)
  const erro = criar_elemento_da_conversa("p", "erro-pendencia", lista.erro);
  erro.dataset.erroDaListaPessoaAPessoa = "";
  erro.hidden = !lista.erro;
  caixa.append(erro, montar_botoes_da_lista(bloco, pendencia, lista));
  return caixa;
}

/**
 * A marcação em lote do dado da empresa: "Marcar todos", o valor e "Usar nos marcados".
 *
 * Recebe: bloco; lista. Devolve: o elemento.
 */
function montar_lote_dos_marcados(bloco, lista) {
  const lote = criar_elemento_da_conversa("div", "lista-pessoa-a-pessoa-lote", "");
  // "Marcar todos": marca (ou desmarca) cada pessoa, no lugar (sem redesenhar: a rolagem da lista fica onde está)
  const rotulo = criar_elemento_da_conversa("label", "lista-pessoa-a-pessoa-marcar-todos", "");
  const marcar_todos = criar_elemento_da_conversa("input", "", "");
  marcar_todos.type = "checkbox";
  marcar_todos.dataset.marcarTodos = "";
  marcar_todos.checked = todas_marcadas(lista);
  marcar_todos.addEventListener("change", function () {
    for (const pessoa of lista.pessoas) {
      lista.marcados[pessoa.linha] = marcar_todos.checked;
    }
    for (const caixinha of bloco.querySelectorAll("[data-marcar-pessoa]")) {
      caixinha.checked = marcar_todos.checked;
    }
  });
  rotulo.append(marcar_todos, " Marcar todos");
  // O valor para as pessoas marcadas (o que foi digitado fica guardado)
  const valor = criar_elemento_da_conversa("input", "campo-entrada campo-pequeno", "");
  valor.dataset.valorDosMarcados = "";
  valor.placeholder = "Valor para os marcados";
  valor.maxLength = 300;
  valor.setAttribute("aria-label", '"' + lista.informacao + '" para as pessoas marcadas');
  valor.value = lista.valor_dos_marcados;
  valor.addEventListener("input", function () {
    lista.valor_dos_marcados = valor.value;
  });
  const usar = criar_elemento_da_conversa("button", "botao botao-contorno botao-pequeno", "Usar nos marcados");
  usar.type = "button";
  usar.dataset.usarNosMarcados = "";
  usar.addEventListener("click", function () {
    usar_valor_nos_marcados(bloco, lista);
  });
  lote.append(rotulo, valor, usar);
  return lote;
}

/**
 * Diz se todas as pessoas da lista estão marcadas (o "Marcar todos" fica marcado).
 *
 * Recebe: lista. Devolve: true ou false (false também sem pessoas).
 */
function todas_marcadas(lista) {
  for (const pessoa of lista.pessoas) {
    if (!lista.marcados[pessoa.linha]) {
      return false;
    }
  }
  return lista.pessoas.length > 0;
}

/**
 * O nome da pessoa na lista, ou "Pessoa da linha N" quando o arquivo não trouxe o nome.
 *
 * Recebe: pessoa — {linha, nome, matricula}. Devolve: o texto.
 */
function nome_na_lista(pessoa) {
  return pessoa.nome || ("Pessoa da linha " + pessoa.linha);
}

/**
 * O que ajuda a reconhecer a pessoa, embaixo do nome. Ex.: "Matrícula 00123 · linha 8"; sem matrícula, "Linha 8 do
 * arquivo".
 *
 * Recebe: pessoa. Devolve: o texto.
 */
function detalhe_da_pessoa(pessoa) {
  if (pessoa.matricula) {
    return "Matrícula " + pessoa.matricula + " · linha " + pessoa.linha;
  }
  return "Linha " + pessoa.linha + " do arquivo";
}

/**
 * Uma linha da lista: a marcação (só no dado da empresa), o nome (abre a ficha), o detalhe e a caixa do valor.
 *
 * Recebe: bloco; pendencia; lista; pessoa. Devolve: o elemento.
 */
function montar_linha_da_pessoa(bloco, pendencia, lista, pessoa) {
  const linha = criar_elemento_da_conversa("div", "linha-pessoa-a-pessoa", "");
  linha.dataset.linhaPessoa = String(pessoa.linha);
  // A marcação, só no dado da empresa (a informação de cada pessoa nunca recebe o mesmo valor em lote)
  if (lista.igual_para_todos) {
    const marcar = criar_elemento_da_conversa("input", "", "");
    marcar.type = "checkbox";
    marcar.dataset.marcarPessoa = String(pessoa.linha);
    marcar.checked = Boolean(lista.marcados[pessoa.linha]);
    marcar.setAttribute("aria-label", "Marcar " + nome_na_lista(pessoa));
    marcar.addEventListener("change", function () {
      lista.marcados[pessoa.linha] = marcar.checked;
      // O "Marcar todos" acompanha
      const marcar_todos = bloco.querySelector("[data-marcar-todos]");
      if (marcar_todos) {
        marcar_todos.checked = todas_marcadas(lista);
      }
    });
    linha.append(marcar);
  }
  // O nome abre a ficha completa (para reconhecer quem é); embaixo, a matrícula e a linha do arquivo
  const quem = criar_elemento_da_conversa("div", "linha-pessoa-a-pessoa-quem", "");
  const nome = criar_elemento_da_conversa("button", "botao-nome", nome_na_lista(pessoa));
  nome.type = "button";
  nome.title = "Ver a ficha completa";
  nome.addEventListener("click", function () {
    abrir_ficha_da_pendencia(pendencia.processamento_id, pessoa.linha, null, nome);
  });
  quem.append(nome, criar_elemento_da_conversa("span", "linha-pessoa-a-pessoa-detalhe", detalhe_da_pessoa(pessoa)));
  // A caixa do valor (o que foi digitado fica guardado)
  const valor = criar_elemento_da_conversa("input", "campo-entrada campo-pequeno", "");
  valor.dataset.valorDaPessoa = String(pessoa.linha);
  valor.maxLength = 300;
  valor.value = lista.valores[pessoa.linha] || "";
  valor.setAttribute("aria-label", '"' + lista.informacao + '" de ' + nome_na_lista(pessoa));
  valor.addEventListener("input", function () {
    lista.valores[pessoa.linha] = valor.value;
  });
  linha.append(quem, valor);
  return linha;
}

/**
 * Mostra (ou esconde, com texto vazio) o aviso de erro da lista, no lugar.
 *
 * Recebe: bloco; lista; texto. Devolve: nada.
 */
function mostrar_erro_da_lista(bloco, lista, texto) {
  lista.erro = texto;
  const erro = bloco.querySelector("[data-erro-da-lista-pessoa-a-pessoa]");
  if (erro) {
    erro.textContent = texto;
    erro.hidden = !texto;
  }
}

/**
 * "Usar nos marcados": põe o valor na caixa de cada pessoa marcada e desmarca todas (para a próxima leva, ex.: as da
 * outra unidade). Tudo no lugar, sem redesenhar a lista.
 *
 * Recebe: bloco; lista. Devolve: nada.
 */
function usar_valor_nos_marcados(bloco, lista) {
  const valor = lista.valor_dos_marcados.trim();
  // Sem valor: diz o que falta
  if (!valor) {
    mostrar_erro_da_lista(bloco, lista, "Escreva o valor para as pessoas marcadas.");
    return;
  }
  let quantas = 0;
  for (const pessoa of lista.pessoas) {
    if (lista.marcados[pessoa.linha]) {
      lista.valores[pessoa.linha] = valor;
      lista.marcados[pessoa.linha] = false;
      quantas = quantas + 1;
    }
  }
  // Ninguém marcado: diz o que falta
  if (quantas === 0) {
    mostrar_erro_da_lista(bloco, lista, "Marque as pessoas que recebem este valor.");
    return;
  }
  mostrar_erro_da_lista(bloco, lista, "");
  // As caixas e as marcações, no lugar
  for (const caixa of bloco.querySelectorAll("[data-valor-da-pessoa]")) {
    caixa.value = lista.valores[caixa.dataset.valorDaPessoa] || "";
  }
  for (const caixinha of bloco.querySelectorAll("[data-marcar-pessoa], [data-marcar-todos]")) {
    caixinha.checked = false;
  }
  lista.valor_dos_marcados = "";
  bloco.querySelector("[data-valor-dos-marcados]").value = "";
}

/**
 * Os botões da lista: "Salvar" (grava todos de uma vez) e "Cancelar" (fecha sem gravar).
 *
 * Recebe: bloco; pendencia; lista. Devolve: o elemento.
 */
function montar_botoes_da_lista(bloco, pendencia, lista) {
  const botoes = criar_elemento_da_conversa("div", "lista-pessoa-a-pessoa-botoes", "");
  const salvar = criar_elemento_da_conversa("button", "botao botao-principal botao-pequeno", "Salvar");
  salvar.type = "button";
  salvar.dataset.salvarListaPessoaAPessoa = "";
  salvar.disabled = lista.pessoas.length === 0;
  salvar.addEventListener("click", function () {
    salvar_lista_pessoa_a_pessoa(bloco, pendencia);
  });
  const cancelar = criar_elemento_da_conversa("button", "botao-nome", "Cancelar");
  cancelar.type = "button";
  cancelar.dataset.cancelarListaPessoaAPessoa = "";
  cancelar.addEventListener("click", function () {
    conversa_guardada(bloco.dataset.chaveConversa).lista_pessoa_a_pessoa = null;
    desenhar_conversa(bloco);
  });
  botoes.append(salvar, cancelar);
  return botoes;
}

/**
 * "Salvar": manda o valor de cada pessoa (vazio = fica sem) como uma rodada da conversa do cartão. Deu certo: a lista
 * fecha, e o chat mostra o "Pronto: ..." com o Desfazer. Recusado (ex.: uma data que não existe): o motivo aparece no
 * chat, com a linha e o nome, e a lista volta com o que foi digitado.
 *
 * Recebe: bloco; pendencia. Devolve: uma promessa.
 */
async function salvar_lista_pessoa_a_pessoa(bloco, pendencia) {
  const chave = bloco.dataset.chaveConversa;
  const guardada = conversa_guardada(chave);
  const lista = guardada.lista_pessoa_a_pessoa;
  // Já esperando uma resposta: não manda de novo
  if (lista === null || guardada.processando_desde !== null) {
    return;
  }
  // O valor de cada pessoa, e quantas foram preenchidas
  const valores = [];
  let preenchidas = 0;
  for (const pessoa of lista.pessoas) {
    const valor = (lista.valores[pessoa.linha] || "").trim();
    valores.push({ linha: pessoa.linha, valor: valor });
    if (valor) {
      preenchidas = preenchidas + 1;
    }
  }
  if (preenchidas === 0) {
    mostrar_erro_da_lista(bloco, lista, "Preencha o valor de pelo menos uma pessoa.");
    return;
  }
  mostrar_erro_da_lista(bloco, lista, "");
  // Enquanto o servidor grava, a lista sai da tela (ficam o balão da pessoa e o "Processando")
  lista.enviada = true;
  const endereco = "/api/empresa/cadastro/" + encodeURIComponent(pendencia.processamento_id) + "/informar_por_pessoa";
  const balao_da_pessoa = "Informei pessoa a pessoa (" + texto_de_pessoas(preenchidas) + ").";
  const deu_certo = await falar_e_esperar(pendencia, balao_da_pessoa, endereco,
    { campo: pendencia.campo, valores: valores });
  if (deu_certo) {
    guardada.lista_pessoa_a_pessoa = null;
  } else {
    lista.enviada = false;
  }
  redesenhar_a_chave(chave);
}

/**
 * A caixa "Responda ao agente..." e o botão de enviar (➤). O texto ainda não enviado fica guardado (volta se a lista for
 * refeita).
 *
 * Recebe: pendencia; guardada. Devolve: o <form>.
 */
function montar_formulario(pendencia, guardada) {
  const formulario = criar_elemento_da_conversa("form", "formulario-conversa-ia", "");
  const caixa = criar_elemento_da_conversa("input", "campo-entrada campo-pequeno", "");
  caixa.dataset.caixaDaConversa = "";
  caixa.placeholder = "Responda ao agente...";
  caixa.maxLength = 1000;
  caixa.setAttribute("aria-label", "Sua resposta para o agente sobre esta pendência de " + pendencia.nome);
  caixa.value = guardada.rascunho;
  // O botão de enviar é só o ícone ➤; o nome "Enviar" fica para quem usa leitor de tela
  const enviar = criar_elemento_da_conversa("button", "botao-enviar-conversa", "➤");
  enviar.type = "submit";
  enviar.setAttribute("aria-label", "Enviar");
  enviar.title = "Enviar";
  // Esperando o agente: a caixa e o botão ficam parados
  const esperando = guardada.processando_desde !== null;
  caixa.disabled = esperando;
  enviar.disabled = esperando;
  // Cada letra digitada fica guardada
  caixa.addEventListener("input", function () {
    guardada.rascunho = caixa.value;
  });
  // Enviar: a mensagem vai para o agente
  formulario.addEventListener("submit", function (evento) {
    evento.preventDefault();
    const mensagem = caixa.value.trim();
    if (mensagem) {
      mandar_mensagem(pendencia, mensagem);
    }
  });
  formulario.append(caixa, enviar);
  return formulario;
}

/**
 * Redesenha, em toda a tela, a conversa e o aviso de uma chave (depois de uma fala nova, de um Desfazer...).
 *
 * Recebe: chave. Devolve: nada. A lista pode ter sido refeita enquanto o agente pensava: acha o bloco novo pela chave.
 */
function redesenhar_a_chave(chave) {
  for (const bloco of document.querySelectorAll("[data-chave-conversa]")) {
    if (bloco.dataset.chaveConversa === chave) {
      desenhar_conversa(bloco);
    }
  }
  // A conversa de uma pendência resolvida (filtro "Resolvidas"), só de leitura
  for (const bloco of document.querySelectorAll("[data-conversa-resolvida]")) {
    if (bloco.dataset.conversaResolvida === chave) {
      desenhar_conversa_resolvida(bloco);
    }
  }
  for (const aviso of document.querySelectorAll("[data-aviso-resolvido]")) {
    if (aviso.dataset.avisoResolvido === chave) {
      aviso.replaceWith(montar_aviso_de_resolvido(chave));
    }
  }
}

// ===== Conversar, confirmar e desfazer =====

/**
 * Manda a mensagem ao agente: o balão da pessoa aparece na hora, com o contador; a resposta, quando chegar.
 *
 * Recebe: pendencia; mensagem. Devolve: uma promessa (termina depois da resposta e da tela refeita).
 */
async function mandar_mensagem(pendencia, mensagem) {
  const guardada = conversa_guardada(chave_da_conversa(pendencia));
  // Já esperando uma resposta: não manda outra por cima
  if (guardada.processando_desde !== null) {
    return;
  }
  guardada.rascunho = "";
  // A pergunta vai para o servidor, que monta a pendência de verdade pela regra e pela linha
  // No cartão do grupo, em_grupo diz ao servidor que a resposta vale para todas as pessoas com o mesmo valor
  await falar_e_esperar(pendencia, mensagem, endereco_do_assistente(pendencia.processamento_id),
    {
      regra_id: pendencia.regra_id, linha: linha_da_conversa(pendencia), mensagem: mensagem,
      em_grupo: esta_no_modo_grupo(pendencia),
      // O campo: a mesma regra aparece uma vez por campo na mesma linha (o servidor acha a pendência certa por ele)
      campo: pendencia.campo || null,
    });
}

/**
 * A escolha numa pergunta de confirmação do agente (ex.: "Sim, não cadastrar", "Sim, usar como CPF" ou "Cancelar"):
 * os dois botões somem, a escolha vira o balão da pessoa, e o servidor aplica (com Desfazer) ou deixa como estava.
 *
 * Recebe: pendencia; fala — a fala do agente com a confirmação aberta; confirmar — true ("sim") ou false ("não").
 * Devolve: uma promessa.
 */
async function responder_a_confirmacao(pendencia, fala, confirmar) {
  const guardada = conversa_guardada(chave_da_conversa(pendencia));
  // Já esperando uma resposta, ou já decidida: nada a fazer
  if (guardada.processando_desde !== null || fala.confirmacao.decidida) {
    return;
  }
  // A escolha fica registrada na fala: os botões não voltam mais
  fala.confirmacao.decidida = true;
  let texto_da_escolha = fala.confirmacao.nao;
  if (confirmar) {
    texto_da_escolha = fala.confirmacao.sim;
  }
  // "Confirma que a coluna X é o CPF?" (ADR-124): a rota da troca de coluna, com a coluna e o campo
  if (fala.confirmacao.tipo === "coluna") {
    await falar_e_esperar(pendencia, texto_da_escolha,
      endereco_do_assistente(pendencia.processamento_id) + "/usar_coluna",
      { campo: fala.confirmacao.campo, coluna: fala.confirmacao.coluna, confirmar: confirmar });
    return;
  }
  await falar_e_esperar(pendencia, texto_da_escolha, endereco_do_assistente(pendencia.processamento_id) + "/confirmar",
    { correcao_id: fala.confirmacao.correcao_id, confirmar: confirmar });
}

/**
 * O caminho comum de uma fala da pessoa: o balão "você" e o contador na hora; o pedido ao servidor; a resposta do
 * agente no balão dele; e, se o dado mudou, a tela refeita.
 *
 * Recebe: pendencia; texto — o que aparece no balão da pessoa; endereco — a rota; corpo — o que mandar.
 * Devolve: uma promessa de true (o servidor aceitou) ou false (recusou; a explicação virou um balão âmbar).
 */
async function falar_e_esperar(pendencia, texto, endereco, corpo) {
  const chave = chave_da_conversa(pendencia);
  const guardada = conversa_guardada(chave);
  // O balão da pessoa e o contador, na hora
  guardada.falas.push({ quem: "empresa", texto: texto });
  guardada.processando_desde = Date.now();
  ligar_o_relogio_do_processando();
  redesenhar_a_chave(chave);
  const resposta = await pedir_ao_assistente(endereco, corpo);
  guardada.processando_desde = null;
  // A pessoa pode responder de novo sem clicar na caixa
  guardada.devolver_o_foco = true;
  // Recusado pelo servidor (ex.: pendência que já foi resolvida): a explicação vira um balão âmbar
  if (!resposta.ok) {
    guardada.falas.push({ quem: "erro", texto: texto_do_erro_do_assistente(resposta.dados) });
    redesenhar_a_chave(chave);
    return false;
  }
  const fala = fala_da_resposta(resposta.dados);
  guardada.falas.push(fala);
  // O agente mudou algo: guarda para o aviso "Resolvido agora" (aparece se a pendência sumir)
  if (fala.aplicado) {
    resolvidos_agora[chave] = { pendencia: pendencia, aplicado: fala.aplicado };
  }
  redesenhar_a_chave(chave);
  // Mudou dado ou colunas: a tela refaz a lista e os números
  if (fala.aplicado || fala.remapeado) {
    await guardada.ao_mudar();
  }
  return true;
}

/**
 * Transforma a resposta do servidor numa fala do agente.
 *
 * Recebe: dados — {mensagem, acao, fontes, aplicado, remapeado, recusado, confirmacao, encerrada}. Devolve: a fala.
 */
function fala_da_resposta(dados) {
  // O que mudou, com espaço para marcar o Desfazer depois
  let aplicado = null;
  if (dados.aplicado) {
    aplicado = { resumo: dados.aplicado.resumo, desfazer: dados.aplicado.desfazer, desfeito: false };
  }
  // A pergunta de confirmação (ex.: tirar a pessoa do envio; usar outra coluna para o dado que faltou, com o tipo
  // "coluna", a coluna e o campo), com espaço para marcar que já foi respondida
  let confirmacao = null;
  if (dados.confirmacao) {
    confirmacao = {
      correcao_id: dados.confirmacao.correcao_id, sim: dados.confirmacao.sim, nao: dados.confirmacao.nao,
      tipo: dados.confirmacao.tipo || "retirada", coluna: dados.confirmacao.coluna || null,
      campo: dados.confirmacao.campo || null, decidida: false,
    };
  }
  return {
    quem: "ia", texto: dados.mensagem, fontes: dados.fontes || [], aplicado: aplicado, confirmacao: confirmacao,
    recusado: Boolean(dados.recusado), remapeado: Boolean(dados.remapeado),
    // A posição da resposta na conversa guardada no servidor: é por ela que o joinha vota (ADR-151)
    ordem: dados.ordem,
    // O agente encerrou a conversa depois das respostas sem valor (ADR-153): o balão ganha a marca
    encerrada: Boolean(dados.encerrada),
  };
}

/**
 * Diz se alguma pergunta de confirmação do agente ainda espera a escolha da pessoa (a atualização automática espera).
 *
 * Recebe: nada. Devolve: true ou false.
 */
function alguma_confirmacao_aberta() {
  for (const chave in conversas_guardadas) {
    for (const fala of conversas_guardadas[chave].falas) {
      if (fala.confirmacao && !fala.confirmacao.decidida) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Liga o relógio do "Processando… N s" (uma vez só, mesmo com várias conversas esperando).
 *
 * Recebe: nada. Devolve: nada.
 */
function ligar_o_relogio_do_processando() {
  if (relogio_do_processando === null) {
    relogio_do_processando = setInterval(andar_os_contadores, UM_SEGUNDO);
  }
}

/**
 * O Desfazer: volta o que o agente mudou (o servidor valida o envio de novo, e a pendência volta a aparecer).
 *
 * Recebe: botao — o Desfazer clicado; pendencia; aplicado — {resumo, desfazer: {tipo, id}}. Devolve: uma promessa.
 */
async function desfazer_o_que_a_ia_fez(botao, pendencia, aplicado) {
  const chave = chave_da_conversa(pendencia);
  const guardada = conversa_guardada(chave);
  botao.disabled = true;
  const resposta = await pedir_ao_assistente(endereco_do_assistente(pendencia.processamento_id) + "/desfazer",
    aplicado.desfazer);
  // Recusado (ex.: o envio já foi para o banco): a explicação vira uma fala de erro, e o aviso mostra também
  if (!resposta.ok) {
    const texto_do_erro = texto_do_erro_do_assistente(resposta.dados);
    guardada.falas.push({ quem: "erro", texto: texto_do_erro });
    if (chave in resolvidos_agora) {
      resolvidos_agora[chave].erro = texto_do_erro;
    }
    redesenhar_a_chave(chave);
    return;
  }
  // Desfeito: marca a mudança, tira o aviso e conta na conversa
  aplicado.desfeito = true;
  delete resolvidos_agora[chave];
  guardada.falas.push({ quem: "ia", texto: resposta.dados.resumo || "Desfeito: o dado voltou a ser o de antes." });
  redesenhar_a_chave(chave);
  // A pendência volta: a tela refaz a lista e os números
  await guardada.ao_mudar();
}

// ===== A conversa de uma pendência já resolvida (filtro "Resolvidas" de Acompanhar; ADR-120) =====

/**
 * A pendência resolvida no formato que as falas usam: o envio e a chave da conversa guardada no servidor.
 *
 * Recebe: resolvida — um item de /api/empresa/pendencias/resolvidas. Devolve: {processamento_id, nome, chave_fixa}.
 */
function pendencia_da_resolvida(resolvida) {
  return {
    processamento_id: resolvida.processamento_id, nome: resolvida.titulo, chave_fixa: resolvida.chave, grupo: null,
  };
}

/**
 * A posição da última mudança que ainda vale na conversa guardada (é nela que fica o Desfazer).
 *
 * Recebe: conversa — as falas do servidor. Devolve: a posição, ou -1 se nenhuma mudança vale.
 */
function posicao_da_ultima_mudanca(conversa) {
  let ultima = -1;
  for (let posicao = 0; posicao < conversa.length; posicao = posicao + 1) {
    const aplicado = conversa[posicao].aplicado;
    // Uma mudança que não foi desfeita
    if (aplicado && !aplicado.desfeito) {
      ultima = posicao;
    }
  }
  return ultima;
}

/**
 * Põe na memória da página a conversa guardada no servidor, quando a página ainda não a tem (ex.: depois do F5).
 *
 * Recebe: resolvida; ao_mudar — o que a tela faz depois de um Desfazer. Devolve: a conversa guardada.
 * A pergunta do agente (o 1º balão) fica de fora da memória: ela é desenhada à parte. Só a última mudança que ainda
 * vale ganha o Desfazer. Se a pendência voltar a ficar em aberto, o cartão dela mostra a conversa inteira.
 */
function guardar_a_conversa_do_servidor(resolvida, ao_mudar) {
  const guardada = conversa_guardada(resolvida.chave);
  guardada.ao_mudar = ao_mudar;
  // A página já tem a conversa (ela foi feita aqui): vale a da memória
  if (guardada.falas.length > 0) {
    return guardada;
  }
  const ultima_mudanca = posicao_da_ultima_mudanca(resolvida.conversa);
  for (let posicao = 0; posicao < resolvida.conversa.length; posicao = posicao + 1) {
    const fala = resolvida.conversa[posicao];
    // A pergunta do agente não vai para a memória
    if (fala.pergunta) {
      continue;
    }
    // O que mudou; o Desfazer só na última mudança que vale
    let aplicado = null;
    if (fala.aplicado) {
      let desfazer = null;
      if (posicao === ultima_mudanca) {
        desfazer = fala.aplicado.desfazer;
      }
      aplicado = { resumo: fala.aplicado.resumo, desfazer: desfazer, desfeito: Boolean(fala.aplicado.desfeito) };
    }
    guardada.falas.push({
      quem: fala.quem, texto: fala.texto, fontes: fala.fontes || [], aplicado: aplicado, confirmacao: null,
      recusado: Boolean(fala.recusado), remapeado: false,
      // A posição do balão na conversa guardada: é por ela que o joinha vota (ADR-151)
      ordem: fala.ordem,
    });
  }
  return guardada;
}

/**
 * Monta a conversa de uma pendência resolvida, só de leitura: a pergunta do agente e as falas, sem caixa e sem
 * respostas rápidas; o Desfazer fica no balão da última mudança que ainda vale.
 *
 * Recebe: resolvida; ao_mudar. Devolve: o elemento da conversa.
 */
function montar_conversa_resolvida(resolvida, ao_mudar) {
  guardar_a_conversa_do_servidor(resolvida, ao_mudar);
  const bloco = criar_elemento_da_conversa("div", "conversa-ia-pendencia conversa-somente-leitura", "");
  bloco.dataset.conversaResolvida = resolvida.chave;
  // Guarda a resolvida no próprio bloco: redesenhar precisa dela
  bloco.dados_da_resolvida = resolvida;
  desenhar_conversa_resolvida(bloco);
  return bloco;
}

/**
 * Desenha (ou redesenha) a conversa de uma pendência resolvida a partir da memória.
 *
 * Recebe: bloco — o elemento da conversa. Devolve: nada.
 */
function desenhar_conversa_resolvida(bloco) {
  const resolvida = bloco.dados_da_resolvida;
  const pendencia = pendencia_da_resolvida(resolvida);
  const historico = criar_elemento_da_conversa("div", "historico-conversa-ia", "");
  // A pergunta do agente, como estava no cartão
  for (const fala of resolvida.conversa) {
    if (fala.pergunta) {
      const pergunta = montar_balao_da_ia(fala.texto, "");
      pergunta.dataset.perguntaDaPendencia = "";
      // A pergunta da leitura ganha o joinha também aqui (ADR-151)
      acrescentar_opiniao_na_pergunta(pergunta, pendencia);
      historico.append(pergunta);
      break;
    }
  }
  // As falas, com o Desfazer da última mudança
  for (const fala of conversa_guardada(resolvida.chave).falas) {
    historico.append(montar_fala(pendencia, fala));
  }
  bloco.replaceChildren(historico);
}

// ===== O aviso "Resolvido agora" =====

/**
 * Os avisos "Resolvido agora" das pendências que o agente resolveu e que saíram da lista.
 *
 * Recebe: chaves_abertas — as chaves das pendências que ainda estão na lista (as que continuam abertas não ganham
 *         aviso: a conversa delas já mostra o que mudou). Devolve: a lista de elementos (pode ser vazia).
 */
function montar_avisos_de_resolvidos_agora(chaves_abertas) {
  const avisos = [];
  for (const chave in resolvidos_agora) {
    if (!chaves_abertas.includes(chave)) {
      avisos.push(montar_aviso_de_resolvido(chave));
    }
  }
  return avisos;
}

/**
 * Um aviso "Resolvido agora": de quem, o que mudou e o Desfazer.
 *
 * Recebe: chave. Devolve: o elemento. Ex.: "Resolvido agora · Luíza Ramos · CPF: 123... → 529... [Desfazer]".
 */
function montar_aviso_de_resolvido(chave) {
  const resolvido = resolvidos_agora[chave];
  const aviso = criar_elemento_da_conversa("div", "aviso-resolvido-agora", "");
  aviso.dataset.avisoResolvido = chave;
  // Já desfeito (ou tirado da lista): o aviso fica vazio e escondido
  if (!resolvido) {
    aviso.hidden = true;
    return aviso;
  }
  aviso.append(criar_elemento_da_conversa("strong", "", "Resolvido agora"));
  // De quem: a pessoa (ou o arquivo inteiro)
  let de_quem = resolvido.pendencia.nome || "";
  if (de_quem) {
    de_quem = de_quem + " · ";
  }
  aviso.append(criar_elemento_da_conversa("span", "", de_quem + resolvido.aplicado.resumo));
  // O Desfazer, quando dá
  if (resolvido.aplicado.desfazer) {
    aviso.append(montar_botao_desfazer(resolvido.pendencia, resolvido.aplicado));
  }
  // Um erro do último Desfazer, se houve
  if (resolvido.erro) {
    aviso.append(criar_elemento_da_conversa("span", "erro-pendencia", resolvido.erro));
  }
  return aviso;
}
