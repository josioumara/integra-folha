/*
  banco_envios_real.js — a aba "Envios" do Portal Interno com os envios REAIS da carteira (ADR-69, passo 15; ADR-121).

  Para que serve: quando a página é servida pela API, troca os envios de exemplo (js/banco_envios.js) pelos que as
  empresas mandaram ao banco (/api/banco/envios):
    - a fila: os que esperam a sua avaliação (quem espera há mais tempo vem primeiro) e os já avaliados; o envio de
      devolução traz a "origem" (ex.: "Devolução do envio de 28/09 (2 pessoas)");
    - cada envio: a trilha (como chegou até aqui), as idas e voltas com o banco, as respostas da empresa aos
      apontamentos, os alertas que a empresa confirmou e as pessoas, com o CPF inteiro (a abertura fica registrada
      nos acessos da empresa);
    - o apontamento de um problema numa pessoa (motivo de uma lista fechada + recado) e o "Desfazer", gravados na
      hora (POST e DELETE em /api/banco/envios/{id}/apontamentos);
    - a decisão: "aprovar", "aprovar_e_devolver_marcados" (os sem apontamento ficam cadastrados; os apontados voltam
      para a empresa num envio de devolução) ou "devolver" o envio inteiro com o motivo. A decisão é gravada com
      quem decidiu e quando.
  Toda ação recarrega a fila e reabre o mesmo envio, sem perder o filtro e a busca da tabela.
  O que a aplicação ainda não faz: contar os valores que a IA padronizou (o número aparece como "—").
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout. Servida pela aplicação, o exemplo
  nunca aparece: a fila e o envio aberto esperam com a barra cinza (js/carregando_dados.js) e, se o servidor falhar,
  a fila mostra o aviso "Não foi possível carregar agora.".
*/

// Verdadeiro depois que os envios reais chegaram (os desvios do js/banco_envios.js olham isto).
let envios_reais_carregados = false;

/**
 * Diz se a tela está usando os envios reais da aplicação.
 *
 * Recebe: nada. Devolve: true ou false.
 */
function modo_real_dos_envios() {
  // Verdadeiro só depois que a fila real chegou.
  return envios_reais_carregados;
}

/**
 * Escreve uma data AAAA-MM-DD no jeito brasileiro; outro formato fica como veio.
 *
 * Recebe: texto. Devolve: a data. Exemplo: "2026-09-22" → "22/09/2026".
 */
function data_de_admissao(texto) {
  // Separa ano, mês e dia.
  const partes = texto.split("-");
  // Não é uma data AAAA-MM-DD: devolve como veio.
  if (partes.length !== 3) {
    return texto;
  }
  // Remonta no jeito brasileiro.
  return partes[2] + "/" + partes[1] + "/" + partes[0];
}

/**
 * Devolve a lista recebida, ou uma lista vazia se o servidor não mandou o campo.
 *
 * Recebe: valor — o que veio do servidor. Devolve: uma lista.
 * Por quê: os campos novos do ADR-121 (idas e voltas, respostas) não podem quebrar a tela se faltarem.
 */
function lista_ou_vazia(valor) {
  // Veio uma lista: usa ela.
  if (Array.isArray(valor)) {
    return valor;
  }
  // Não veio: lista vazia (o bloco da tela some).
  return [];
}

/**
 * Converte uma pessoa da API para o formato da tabela do js/banco_envios.js.
 *
 * Recebe: pessoa — {linha, nome, cpf (inteiro, formatado), cargo, admissao, salario (texto), alerta, apontamento,
 *         campos}. Devolve: a pessoa da tela.
 */
function pessoa_no_formato_da_tela(pessoa) {
  // Os dados que a tabela mostra.
  const pessoa_da_tela = {
    linha: pessoa.linha,
    nome: pessoa.nome,
    cpf: pessoa.cpf,
    cargo: pessoa.cargo,
    admissao: data_de_admissao(pessoa.admissao),
    salario: parseFloat(pessoa.salario) || 0,
    // Todos os campos do parâmetro, para a grade (ADR-111).
    campos: pessoa.campos,
    // O que a IA guardou sem rótulo (ADR-143, Parte 1): só a ficha mostra; sem a chave, a lista fica vazia.
    informacoes_sem_rotulo: lista_ou_vazia(pessoa.informacoes_sem_rotulo),
    // A empresa confirmou um alerta desta pessoa antes de enviar (filtro "Confirmados pela empresa").
    confirmado_pela_empresa: pessoa.alerta === true,
    // O problema apontado pelo especialista nesta rodada ({motivo, motivo_texto, recado}), ou null.
    apontamento: pessoa.apontamento || null,
  };
  // Pessoa com alerta confirmado pela empresa espera a decisão do especialista.
  if (pessoa.alerta) {
    pessoa_da_tela.situacao = "alerta";
  }
  // Devolve a pessoa pronta.
  return pessoa_da_tela;
}

/**
 * Converte um envio da API para o formato da fila do js/banco_envios.js.
 *
 * Recebe: envio — da API; pessoas — as pessoas do envio. Devolve: o envio da tela.
 */
function envio_no_formato_da_tela(envio, pessoas) {
  // Os alertas confirmados pela empresa: abertos enquanto o envio espera o banco.
  const alertas = [];
  for (const alerta of envio.alertas) {
    // Envio já avaliado: o alerta foi decidido junto com ele.
    let estado = "aceito";
    if (envio.situacao === "aguardando") {
      estado = "aberto";
    }
    // A linha liga o alerta à pessoa da tabela (para o "Apontar problema" do cartão).
    alertas.push({ linha: alerta.linha, nome: alerta.nome, selo: "Confirmado pela empresa",
      texto: alerta.texto + " " + alerta.confirmacao, estado: estado, nota: "Avaliado junto com o envio." });
  }
  // As pessoas no formato da tabela.
  const pessoas_da_tela = [];
  for (const pessoa of pessoas) {
    const pessoa_da_tela = pessoa_no_formato_da_tela(pessoa);
    // Envio já avaliado: ninguém fica em alerta.
    if (envio.situacao !== "aguardando") {
      delete pessoa_da_tela.situacao;
    }
    pessoas_da_tela.push(pessoa_da_tela);
  }
  // O envio pronto para a tela.
  return {
    id: envio.id,
    empresa: envio.empresa,
    tipo: envio.tipo,
    detalhe: "Enviada ao banco em " + quando_foi_enviado(envio.enviado_em) + " · " + envio.linhas + " linhas no arquivo",
    situacao: envio.situacao,
    // Envio de devolução: o texto de onde ele veio; nos outros, null.
    origem: envio.origem || null,
    prazo: envio.prazo,
    resultado: envio.resultado,
    valores_padronizados: "—",
    trilha: envio.trilha,
    idas_e_voltas: lista_ou_vazia(envio.idas_e_voltas),
    respostas_aos_apontamentos: lista_ou_vazia(envio.respostas_aos_apontamentos),
    alertas: alertas,
    pessoas: pessoas_da_tela,
  };
}

/**
 * Busca a fila real (e as pessoas de cada envio) e troca os envios de exemplo por ela.
 *
 * Recebe: nada. Devolve: true se trocou; false se não há servidor (fica o exemplo).
 */
async function carregar_fila_real() {
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    // A fila da carteira.
    const resposta = await fetch("/api/banco/envios");
    if (!resposta.ok) {
      return false;
    }
    const fila = await resposta.json();
    // As pessoas de cada envio.
    const envios_da_tela = [];
    for (const envio of fila) {
      const resposta_das_pessoas = await fetch("/api/banco/envios/" + encodeURIComponent(envio.id) + "/pessoas");
      let pessoas = [];
      if (resposta_das_pessoas.ok) {
        pessoas = await resposta_das_pessoas.json();
      }
      envios_da_tela.push(envio_no_formato_da_tela(envio, pessoas));
    }
    // Troca os envios de exemplo pelos reais (esvazia a lista e põe os novos).
    ENVIOS.length = 0;
    for (const envio of envios_da_tela) {
      ENVIOS.push(envio);
    }
    return true;
  } catch (erro) {
    return false;
  }
}

/**
 * Troca as opções da lista de motivos da janela "Apontar problema" pela lista fechada do servidor.
 *
 * Recebe: nada. Devolve: nada. Se o servidor não responder, fica a mesma lista escrita no HTML.
 */
async function carregar_motivos_de_apontamento() {
  // try/catch: servidor fora do ar deixa a lista do HTML.
  try {
    const resposta = await fetch("/api/banco/motivos_de_apontamento");
    if (!resposta.ok) {
      return;
    }
    // A lista [{valor, texto}] do servidor.
    const motivos = await resposta.json();
    // A caixa de escolha da janela.
    const campo_do_motivo = document.querySelector("[data-ajuste-motivo]");
    // Esvazia a lista escrita no HTML e põe a primeira opção, vazia, que pede a escolha.
    campo_do_motivo.replaceChildren(criar_opcao_de_motivo("", "Escolha o motivo"));
    // Uma opção por motivo do servidor.
    for (const motivo of motivos) {
      campo_do_motivo.append(criar_opcao_de_motivo(motivo.valor, motivo.texto));
    }
  } catch (erro) {
    return;
  }
}

/**
 * Cria uma opção da lista de motivos.
 *
 * Recebe: valor — ex.: "salario"; texto — ex.: "Confirmar o salário". Devolve: o elemento <option>.
 */
function criar_opcao_de_motivo(valor, texto) {
  // A opção com o texto que a pessoa lê.
  const opcao = criar_elemento("option", "", texto);
  // O valor que vai para o servidor.
  opcao.value = valor;
  return opcao;
}

/**
 * Abre um envio da fila, ou mostra que não há nenhum envio para avaliar.
 *
 * Recebe: id — o envio a abrir (ou null: o primeiro da fila). Devolve: nada.
 */
function abrir_envio_real(id) {
  const painel = document.querySelector("[data-envio-aberto]");
  // Nenhum envio na fila: o painel some e a fila diz que está tudo em dia.
  if (ENVIOS.length === 0) {
    painel.hidden = true;
    mostrar_fila();
    return;
  }
  painel.hidden = false;
  // O envio pedido, se existir; senão, o primeiro da fila.
  const pedido = achar_envio(id);
  if (pedido) {
    abrir_envio(pedido);
  } else {
    abrir_envio(ENVIOS[0]);
  }
}

/**
 * Recarrega a fila do servidor e reabre o mesmo envio, sem perder o filtro, a busca e o "mostrar mais".
 *
 * Recebe: id — o envio que estava aberto. Devolve: nada (espera o servidor).
 */
async function recarregar_e_reabrir(id) {
  // A fila de novo, com os dados que acabaram de mudar.
  await carregar_fila_real();
  // O mesmo envio, já com os dados novos.
  const envio = achar_envio(id);
  // Sumiu da fila (não deveria): abre o primeiro, como na entrada da tela.
  if (!envio) {
    abrir_envio_real(null);
    return;
  }
  // Reabre mantendo o que a pessoa estava fazendo na tabela.
  reabrir_envio_mantendo_a_tela(envio);
}

/**
 * O texto do erro que o servidor mandou, para mostrar na tela.
 *
 * Recebe: dados — o corpo da resposta de erro. Devolve: o texto.
 * Por quê: o servidor manda o motivo em "detail" (texto); num pedido malformado, "detail" vem como lista técnica,
 * que não ajuda quem está na tela.
 */
function texto_do_erro(dados) {
  // O motivo em texto: mostra como veio.
  if (dados && typeof dados.detail === "string") {
    return dados.detail;
  }
  // Outro formato: uma frase simples.
  return "confira os dados e tente de novo.";
}

/**
 * Lê o corpo da resposta como JSON, sem quebrar se ele vier vazio ou em outro formato.
 *
 * Recebe: resposta — do fetch. Devolve: o objeto, ou {} se não der para ler.
 */
async function ler_resposta(resposta) {
  // try/catch: um corpo que não é JSON vira um objeto vazio.
  try {
    return await resposta.json();
  } catch (erro) {
    return {};
  }
}

/**
 * Grava o problema apontado numa pessoa do envio aberto; com sucesso, fecha a janela e reabre o envio.
 *
 * Recebe: linha — a linha da pessoa no arquivo; motivo — o valor da lista fechada (ex.: "salario"); recado — o
 *         texto para a empresa. Devolve: nada (espera o servidor).
 */
async function apontar_de_verdade(linha, motivo, recado) {
  const envio = estado_da_tela.envio_aberto;
  // O aviso dentro da janela, para mostrar a recusa do servidor sem fechar a janela.
  const aviso = document.querySelector("[data-ajuste-erro]");
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  try {
    const resposta = await fetch("/api/banco/envios/" + encodeURIComponent(envio.id) + "/apontamentos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linha: Number(linha), motivo: motivo, recado: recado }),
    });
    // Recusado (ex.: recado curto, envio que não espera mais o banco): o motivo aparece na janela.
    if (!resposta.ok) {
      const dados = await ler_resposta(resposta);
      aviso.textContent = "Não foi possível: " + texto_do_erro(dados);
      aviso.hidden = false;
      document.querySelector("[data-confirmar-apontamento]").disabled = false;
      return;
    }
    // Gravado: fecha a janela e reabre o envio com o apontamento.
    document.getElementById("janela-pedir-ajuste").close();
    await recarregar_e_reabrir(envio.id);
  } catch (erro) {
    aviso.textContent = "Sem conexão com o servidor. Tente de novo.";
    aviso.hidden = false;
    document.querySelector("[data-confirmar-apontamento]").disabled = false;
  }
}

/**
 * Apaga o problema apontado numa pessoa do envio aberto e reabre o envio.
 *
 * Recebe: linha — a linha da pessoa no arquivo. Devolve: nada (espera o servidor).
 */
async function desfazer_de_verdade(linha) {
  const envio = estado_da_tela.envio_aberto;
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  try {
    const endereco = "/api/banco/envios/" + encodeURIComponent(envio.id) + "/apontamentos/" + encodeURIComponent(linha);
    const resposta = await fetch(endereco, { method: "DELETE" });
    // Recusado: o motivo aparece no aviso do alto.
    if (!resposta.ok) {
      const dados = await ler_resposta(resposta);
      mostrar_aviso("Não foi possível desfazer: " + texto_do_erro(dados));
      return;
    }
    // Apagado: reabre o envio sem o apontamento.
    await recarregar_e_reabrir(envio.id);
  } catch (erro) {
    mostrar_aviso("Sem conexão com o servidor. Tente de novo.");
  }
}

/**
 * Grava a decisão do especialista sobre o envio aberto e recarrega a fila.
 *
 * Recebe: decisao — "aprovar", "aprovar_e_devolver_marcados" ou "devolver"; motivo — o recado para a empresa (só
 *         na devolução do envio inteiro). Devolve: nada (espera a resposta do servidor).
 */
async function avaliar_de_verdade(decisao, motivo) {
  const envio = estado_da_tela.envio_aberto;
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  try {
    const resposta = await fetch("/api/banco/envios/" + encodeURIComponent(envio.id) + "/avaliar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisao: decisao, motivo: motivo }),
    });
    const dados = await ler_resposta(resposta);
    // Recusado: o motivo aparece no aviso do alto, e a barra volta ao normal.
    if (!resposta.ok) {
      mostrar_aviso("Não foi possível: " + texto_do_erro(dados));
      atualizar_partes_do_envio();
      return;
    }
    // Recarrega a fila e reabre o mesmo envio, agora avaliado.
    await carregar_fila_real();
    abrir_envio_real(envio.id);
    // O aviso: o resultado e, se houve, o envio de devolução com as pessoas apontadas.
    let aviso = dados.resultado;
    if (dados.envio_de_devolucao) {
      aviso = aviso + " As pessoas apontadas voltaram para a empresa num envio de devolução.";
    }
    mostrar_aviso(aviso + " A " + envio.empresa + " já vê isso em Acompanhar cadastros.");
  } catch (erro) {
    mostrar_aviso("Sem conexão com o servidor. Tente de novo.");
    atualizar_partes_do_envio();
  }
}

/**
 * Liga o modo real: carrega a fila e abre o envio pedido no endereço (ou o primeiro).
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: fica o exemplo.
 */
async function ligar_envios_reais() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  const trocou = await carregar_fila_real();
  // Servidor sem resposta: nenhum envio de exemplo fica na tela (nem a barra cinza para sempre).
  if (!trocou) {
    mostrar_envios_indisponiveis();
    return;
  }
  // A lista fechada de motivos do "Apontar problema", do servidor.
  await carregar_motivos_de_apontamento();
  // As colunas do parâmetro vigente: a ficha da pessoa mostra todas; a tabela de pessoas, uma coluna por campo
  // obrigatório (ADR-111 e ADR-143). A escolha é da marca "obrigatório" do parâmetro, nunca de uma lista daqui.
  colunas_do_detalhe = await buscar_colunas_do_parametro("/api/banco/colunas_da_consulta");
  colunas_da_grade = colunas_obrigatorias(colunas_do_detalhe);
  if (colunas_da_grade.length > 0) {
    montar_cabecalho_da_grade(document.querySelector("[data-cabeca-pessoas]"), colunas_da_grade, [],
      [{ grupo: "Avaliação", titulos: ["Situação", "Ação"], nota: "" }]);
    document.querySelector("[data-legenda-grade]").hidden = false;
  }
  envios_reais_carregados = true;
  abrir_envio_real(new URLSearchParams(window.location.search).get("envio"));
  // Os envios de verdade já estão na tela: a fila, os dois números dos filtros e o envio aberto aparecem.
  marcar_todos_como_carregados("[data-lista-fila], [data-contagem-fila], [data-envio-aberto]");
}

/**
 * O servidor não respondeu: a fila diz que não foi possível carregar, o envio de exemplo some e os números dos
 * filtros viram um traço. Nunca fica um envio de exemplo à mostra.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_envios_indisponiveis() {
  // Esvazia os envios de exemplo: nenhum clique depois traz o exemplo de volta.
  ENVIOS.length = 0;
  // A fila ganha o aviso no lugar dos envios.
  const lista = document.querySelector("[data-lista-fila]");
  lista.replaceChildren(criar_elemento("li", "painel-vazio", "Não foi possível carregar agora. Atualize a página em instantes."));
  marcar_como_carregado(lista);
  // Os números dos dois filtros: um traço, sem inventar valor.
  for (const contagem of document.querySelectorAll("[data-contagem-fila]")) {
    mostrar_dado_indisponivel(contagem);
  }
  // Os filtros da fila ficam desligados: sem envios, não há o que filtrar.
  for (const filtro of document.querySelectorAll("[data-filtro-fila]")) {
    filtro.disabled = true;
  }
  // O envio aberto (o de exemplo) some da tela.
  const painel = document.querySelector("[data-envio-aberto]");
  painel.hidden = true;
  marcar_como_carregado(painel);
}

// Quando o HTML terminar de carregar, liga o modo real (se houver servidor).
document.addEventListener("DOMContentLoaded", ligar_envios_reais);
