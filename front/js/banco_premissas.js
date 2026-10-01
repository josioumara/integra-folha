/*
  banco_premissas.js — a tela "Premissas financeiras" da Configuração do Portal Interno.

  Para que serve: o especialista do banco grava aqui as premissas financeiras OFICIAIS do planejamento. A tela:
    - mostra a versão vigente (horizonte em meses e os três MOB em reais) e quando e por quem ela foi gravada. As
      taxas (% novas contas, % correntistas não folha, % correção de folha) não são oficiais: ficam só no Simulador
      de Rentabilidade;
    - começa o formulário com os valores vigentes; "Salvar como nova versão oficial" confere os valores, abre uma
      janela de confirmação com o que muda (de → para) e, com "Confirmar e salvar", manda ao servidor;
    - mostra o registro de todas as versões: número, quem gravou, quando e o que mudou.
  O servidor (POST /api/banco/premissas) confere tudo de novo e grava a versão nova; as antigas nunca são apagadas.
  Os números se atualizam sozinhos ao voltar para a aba e de minuto em minuto, sem apagar o que a pessoa está
  digitando (critério das telas do projeto).
*/

// As premissas da tela, na ordem, com o nome que aparece para a pessoa (o mesmo do registro feito no servidor)
const TITULOS_DAS_PREMISSAS = {
  horizonte_meses: "Horizonte da projeção",
  mob_cliente_folha: "MOB cliente folha",
  mob_cliente_nao_folha: "MOB cliente não folha",
  mob_cliente_novo_conquistado: "MOB cliente novo conquistado",
};

// De quanto em quanto tempo a tela pergunta de novo ao servidor (1 minuto, em milissegundos)
const INTERVALO_DA_ATUALIZACAO = 60000;

// O que veio do servidor: a versão vigente (número e valores) e o maior horizonte aceito
const estado_das_premissas = { versao: null, vigente: null, horizonte_maximo: 60 };

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta (ex.: "td"); classe (ou vazio); texto (ou vazio). Devolve: o elemento.
 */
function criar_elemento_premissa(etiqueta, classe, texto) {
  // O elemento novo, ainda fora da página
  const elemento = document.createElement(etiqueta);
  // A classe, quando há
  if (classe) {
    elemento.className = classe;
  }
  // O texto, quando há
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Um valor em reais no padrão brasileiro.
 *
 * Recebe: valor — texto com ponto nos centavos (ex.: "2090.62"). Devolve: ex.: "R$ 2.090,62".
 */
function em_reais_premissa(valor) {
  // O número com separador de milhar e sempre duas casas (os centavos)
  const numero_formatado = Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return "R$ " + numero_formatado;
}

/**
 * O horizonte em meses, com singular e plural.
 *
 * Recebe: meses — ex.: 12. Devolve: ex.: "12 meses" (ou "1 mês").
 */
function em_meses(meses) {
  if (Number(meses) === 1) {
    return "1 mês";
  }
  return meses + " meses";
}

/**
 * O valor de uma premissa como aparece na tela.
 *
 * Recebe: nome — ex.: "mob_cliente_folha"; valor. Devolve: ex.: "R$ 2.090,62" ou "12 meses".
 */
function texto_da_premissa(nome, valor) {
  // O horizonte é contado em meses; o resto é dinheiro
  if (nome === "horizonte_meses") {
    return em_meses(valor);
  }
  return em_reais_premissa(valor);
}

/**
 * Transforma o momento gravado (UTC, "2026-09-28T17:40:00+00:00") na data e hora daqui ("28/09/2026 14:40").
 *
 * Recebe: momento. Devolve: o texto.
 */
function data_e_hora_da_premissa(momento) {
  const data = new Date(momento);
  return data.toLocaleDateString("pt-BR") + " " + data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Mostra a versão vigente: o número, quando e por quem foi gravada e os 4 valores.
 *
 * Recebe: dados — o JSON de /api/banco/premissas. Devolve: nada.
 */
function mostrar_versao_vigente(dados) {
  // O selo com o número da versão
  document.querySelector("[data-versao-vigente]").textContent = "v" + dados.versao;
  // A versão vigente é a primeira do registro (o registro vem da mais nova para a mais antiga)
  const gravacao_vigente = dados.registro[0];
  document.querySelector("[data-vigente-desde]").textContent =
    "Gravada em " + data_e_hora_da_premissa(gravacao_vigente.criado_em) + " por " + gravacao_vigente.criado_por + ".";
  // Cada um dos 4 valores, no quadro dele
  for (const nome of Object.keys(TITULOS_DAS_PREMISSAS)) {
    document.querySelector("[data-valor-vigente='" + nome + "']").textContent = texto_da_premissa(nome, dados.vigente[nome]);
  }
}

/**
 * Põe os valores vigentes nos campos do formulário.
 *
 * Recebe: vigente — {horizonte_meses, mob_cliente_folha, ...}. Devolve: nada.
 */
function preencher_formulario_de_premissas(vigente) {
  for (const nome of Object.keys(TITULOS_DAS_PREMISSAS)) {
    // O campo recebe o valor como texto (ex.: "2090.62"), do jeito que o campo numérico entende
    document.querySelector("[data-campo-premissa='" + nome + "']").value = String(vigente[nome]);
  }
  // O limite do horizonte que o servidor aceita, no campo e na explicação
  document.querySelector("[data-campo-premissa='horizonte_meses']").max = String(estado_das_premissas.horizonte_maximo);
  document.querySelector("[data-horizonte-maximo]").textContent = String(estado_das_premissas.horizonte_maximo);
}

/**
 * Desenha o registro das versões: cada versão, quando, quem e o que mudou.
 *
 * Recebe: registro — [{versao, criado_em, criado_por, mudancas}]. Devolve: nada.
 */
function desenhar_registro_das_premissas(registro) {
  const corpo = document.querySelector("[data-corpo-registro-premissas]");
  // Tira as linhas de antes (inclusive as de exemplo do protótipo)
  corpo.replaceChildren();
  for (const versao of registro) {
    const linha = criar_elemento_premissa("tr", "", "");
    // Marca a linha com o número da versão (o roteiro de teste acha a linha por ele)
    linha.dataset.versaoPremissas = String(versao.versao);
    linha.append(criar_elemento_premissa("td", "", "v" + versao.versao));
    linha.append(criar_elemento_premissa("td", "", data_e_hora_da_premissa(versao.criado_em)));
    linha.append(criar_elemento_premissa("td", "", versao.criado_por));
    // O que mudou: uma frase por linha (ex.: "MOB cliente folha: R$ 2.090,62 → R$ 2.150,00")
    const celula_das_mudancas = criar_elemento_premissa("td", "", "");
    const lista = criar_elemento_premissa("ul", "lista-mudancas", "");
    for (const mudanca of versao.mudancas) {
      lista.append(criar_elemento_premissa("li", "", mudanca));
    }
    celula_das_mudancas.append(lista);
    linha.append(celula_das_mudancas);
    corpo.append(linha);
  }
}

/**
 * Mostra o que veio do servidor: a versão vigente, o registro e (quando pedido) os valores no formulário.
 *
 * Recebe: dados — o JSON de /api/banco/premissas; refazer_formulario — true para pôr os valores vigentes nos campos.
 * Devolve: nada.
 */
function mostrar_premissas(dados, refazer_formulario) {
  // Guarda a versão vigente: a confirmação compara o formulário com ela
  estado_das_premissas.versao = dados.versao;
  estado_das_premissas.vigente = dados.vigente;
  estado_das_premissas.horizonte_maximo = dados.horizonte_maximo_meses;
  mostrar_versao_vigente(dados);
  desenhar_registro_das_premissas(dados.registro);
  if (refazer_formulario) {
    preencher_formulario_de_premissas(dados.vigente);
  }
  // Os valores reais estão na tela: saem da espera (js/carregando_dados.js)
  marcar_todos_como_carregados("[data-versao-vigente], [data-vigente-desde], [data-valor-vigente], [data-tabela-registro-premissas]");
}

/**
 * Mostra (ou esconde) um recado de erro.
 *
 * Recebe: seletor — onde; texto (ou vazio, para esconder). Devolve: nada.
 */
function mostrar_erro_premissas(seletor, texto) {
  const erro = document.querySelector(seletor);
  erro.hidden = !texto;
  erro.textContent = texto || "";
}

/**
 * Os valores que estão nos campos do formulário, como texto sem espaços nas pontas.
 *
 * Recebe: nada. Devolve: {horizonte_meses: "12", mob_cliente_folha: "2090.62", ...}.
 */
function valores_do_formulario() {
  const valores = {};
  for (const nome of Object.keys(TITULOS_DAS_PREMISSAS)) {
    valores[nome] = document.querySelector("[data-campo-premissa='" + nome + "']").value.trim();
  }
  return valores;
}

/**
 * Confere os valores antes de abrir a confirmação (o servidor confere de novo ao gravar).
 *
 * Recebe: valores — os do formulário. Devolve: o recado do primeiro problema, ou "" se está tudo certo.
 * Ex.: "MOB cliente folha" = "0" devolve "\"MOB cliente folha\" precisa ser maior que zero.".
 */
function recado_de_valor_invalido(valores) {
  // O horizonte: só algarismos, de 1 ao máximo
  const horizonte = valores.horizonte_meses;
  const horizonte_e_inteiro = /^[0-9]+$/.test(horizonte);
  if (!horizonte_e_inteiro || Number(horizonte) < 1 || Number(horizonte) > estado_das_premissas.horizonte_maximo) {
    return "O horizonte da projeção precisa ser um número inteiro de meses, de 1 a " + estado_das_premissas.horizonte_maximo + ".";
  }
  // O dinheiro: número com no máximo 2 casas depois do ponto, maior que zero
  for (const nome of Object.keys(TITULOS_DAS_PREMISSAS)) {
    if (nome === "horizonte_meses") {
      continue;
    }
    const valor = valores[nome];
    // Campo vazio (ou com algo que não é número, que o campo numérico entrega vazio)
    if (valor === "") {
      return "Informe o valor de \"" + TITULOS_DAS_PREMISSAS[nome] + "\", em reais.";
    }
    // Algarismos, e depois do ponto no máximo dois (os centavos)
    const formato_de_dinheiro = /^[0-9]+(\.[0-9]{1,2})?$/.test(valor);
    if (!formato_de_dinheiro) {
      return "\"" + TITULOS_DAS_PREMISSAS[nome] + "\": use no máximo 2 casas depois da vírgula (os centavos).";
    }
    if (Number(valor) <= 0) {
      return "\"" + TITULOS_DAS_PREMISSAS[nome] + "\" precisa ser maior que zero.";
    }
  }
  return "";
}

/**
 * Diz se um valor do formulário é igual ao vigente (dinheiro e % comparados pelos centavos: "1724" = "1724.00").
 *
 * Recebe: nome — a premissa; valor_novo — o texto do formulário. Devolve: true se não mudou.
 */
function premissa_igual_a_vigente(nome, valor_novo) {
  const valor_vigente = estado_das_premissas.vigente[nome];
  if (nome === "horizonte_meses") {
    return Number(valor_novo) === Number(valor_vigente);
  }
  return Number(valor_novo).toFixed(2) === Number(valor_vigente).toFixed(2);
}

/**
 * O que muda do vigente para o formulário, em frases (de → para), iguais às do registro feito no servidor.
 *
 * Recebe: valores — os do formulário. Devolve: ex.: ["MOB cliente folha: R$ 2.090,62 → R$ 2.150,00"].
 */
function mudancas_do_formulario(valores) {
  const mudancas = [];
  for (const nome of Object.keys(TITULOS_DAS_PREMISSAS)) {
    // Igual ao vigente: não entra
    if (premissa_igual_a_vigente(nome, valores[nome])) {
      continue;
    }
    const de = texto_da_premissa(nome, estado_das_premissas.vigente[nome]);
    const para = texto_da_premissa(nome, valores[nome]);
    mudancas.push(TITULOS_DAS_PREMISSAS[nome] + ": " + de + " → " + para);
  }
  return mudancas;
}

/**
 * "Salvar como nova versão oficial": confere os valores e abre a janela de confirmação com o que muda.
 *
 * Recebe: nada. Devolve: nada.
 */
function abrir_confirmacao_das_premissas() {
  // Sem a versão vigente (servidor fora do ar), não há com o que comparar
  if (estado_das_premissas.vigente === null) {
    mostrar_erro_premissas("[data-erro-premissas]", "As premissas vigentes ainda não carregaram. Tente de novo em instantes.");
    return;
  }
  const valores = valores_do_formulario();
  // Valor que o servidor recusaria: avisa aqui mesmo
  const recado = recado_de_valor_invalido(valores);
  if (recado) {
    mostrar_erro_premissas("[data-erro-premissas]", recado);
    return;
  }
  const mudancas = mudancas_do_formulario(valores);
  // Nada mudou: não há versão nova para gravar
  if (mudancas.length === 0) {
    mostrar_erro_premissas("[data-erro-premissas]", "Nada mudou nas premissas: mude um valor antes de salvar.");
    return;
  }
  mostrar_erro_premissas("[data-erro-premissas]", "");
  // O título diz qual versão será criada (a próxima depois da vigente)
  document.querySelector("[data-titulo-janela-premissas]").textContent =
    "Salvar a v" + (estado_das_premissas.versao + 1) + " como nova versão oficial?";
  // A lista do que muda
  const lista = document.querySelector("[data-mudancas-janela-premissas]");
  lista.replaceChildren();
  for (const mudanca of mudancas) {
    lista.append(criar_elemento_premissa("li", "", mudanca));
  }
  mostrar_erro_premissas("[data-erro-janela-premissas]", "");
  document.querySelector("[data-janela-premissas]").showModal();
}

/**
 * "Confirmar e salvar": manda os valores ao servidor, que grava a versão nova, e mostra a tela atualizada.
 *
 * Recebe: nada. Devolve: nada.
 */
async function confirmar_e_salvar_premissas() {
  const botao = document.querySelector("[data-confirmar-premissas]");
  // Evita gravar duas vezes com dois cliques rápidos
  botao.disabled = true;
  try {
    const resposta = await fetch("/api/banco/premissas", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(valores_do_formulario()),
    });
    const dados = await resposta.json();
    // Recusado: a mensagem do servidor aparece na janela, que continua aberta
    if (!resposta.ok) {
      mostrar_erro_premissas("[data-erro-janela-premissas]", typeof dados.detail === "string" ? dados.detail : "Confira os valores e tente de novo.");
      return;
    }
    // Gravado: a tela mostra a versão nova, o registro e os valores novos no formulário
    mostrar_premissas(dados, true);
    document.querySelector("[data-janela-premissas]").close();
    document.querySelector("[data-aviso-premissas-texto]").textContent =
      "Versão v" + dados.versao + " gravada como oficial. Ela vale para os cálculos e as simulações novas.";
    document.querySelector("[data-aviso-premissas]").hidden = false;
  } catch (erro) {
    mostrar_erro_premissas("[data-erro-janela-premissas]", "Não foi possível falar com o servidor. Tente de novo em instantes.");
  } finally {
    botao.disabled = false;
  }
}

/**
 * Diz se a pessoa está no meio de algo na tela: a janela aberta, um campo em uso ou um valor mudado e não salvo.
 *
 * Recebe: nada. Devolve: true se a atualização automática não pode mexer no formulário.
 */
function pessoa_esta_mexendo_nas_premissas() {
  // A janela de confirmação está aberta
  if (document.querySelector("[data-janela-premissas]").open) {
    return true;
  }
  // O cursor está num campo do formulário
  if (document.activeElement && document.activeElement.hasAttribute("data-campo-premissa")) {
    return true;
  }
  // Ainda não carregou nada: não há o que proteger
  if (estado_das_premissas.vigente === null) {
    return false;
  }
  // Algum campo difere do vigente (valor digitado e ainda não salvo)
  const valores = valores_do_formulario();
  for (const nome of Object.keys(TITULOS_DAS_PREMISSAS)) {
    if (!premissa_igual_a_vigente(nome, valores[nome])) {
      return true;
    }
  }
  return false;
}

/**
 * O servidor não respondeu: os valores de exemplo viram traço e o registro sai da espera, vazio.
 *
 * Recebe: nada. Devolve: nada. O recado de erro embaixo do formulário diz o que aconteceu.
 */
function liberar_premissas_sem_dado() {
  // Cada número vira "—" (se já mostrava o de verdade, fica como está)
  for (const elemento of document.querySelectorAll("[data-versao-vigente], [data-vigente-desde], [data-valor-vigente]")) {
    mostrar_dado_indisponivel(elemento);
  }
  // O registro: só as linhas de exemplo saem (um registro de verdade já mostrado continua)
  const tabela = document.querySelector("[data-tabela-registro-premissas]");
  if (!tabela.hasAttribute("data-dado-pronto")) {
    document.querySelector("[data-corpo-registro-premissas]").replaceChildren();
  }
  marcar_como_carregado(tabela);
}

/**
 * Pede ao servidor a versão vigente e o registro, e mostra.
 *
 * Recebe: refazer_formulario — true para pôr os valores vigentes nos campos (na abertura da tela e quando a pessoa
 * não está mexendo neles). Devolve: nada.
 */
async function carregar_premissas(refazer_formulario) {
  try {
    const resposta = await fetch("/api/banco/premissas");
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro_premissas("[data-erro-premissas]", typeof dados.detail === "string" ? dados.detail : "Não foi possível abrir as premissas.");
      liberar_premissas_sem_dado();
      return;
    }
    mostrar_premissas(dados, refazer_formulario);
  } catch (erro) {
    mostrar_erro_premissas("[data-erro-premissas]", "Não foi possível falar com o servidor. Tente de novo em instantes.");
    liberar_premissas_sem_dado();
  }
}

/**
 * A atualização automática: pergunta de novo ao servidor e só refaz o formulário se a pessoa não está mexendo nele.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_premissas_sozinho() {
  // Aba escondida: espera a pessoa voltar (o evento de visibilidade chama de novo)
  if (document.hidden) {
    return;
  }
  carregar_premissas(!pessoa_esta_mexendo_nas_premissas());
}

/**
 * Liga os botões da tela, busca as premissas e liga a atualização automática. Chamada uma vez, ao carregar a página.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_tela_de_premissas() {
  document.querySelector("[data-salvar-premissas]").addEventListener("click", abrir_confirmacao_das_premissas);
  document.querySelector("[data-confirmar-premissas]").addEventListener("click", confirmar_e_salvar_premissas);
  document.querySelector("[data-voltar-premissas]").addEventListener("click", function () {
    document.querySelector("[data-janela-premissas]").close();
  });
  // Enter num campo não recarrega a página: abre a confirmação, como o botão
  document.querySelector("[data-formulario-premissas]").addEventListener("submit", function (evento) {
    evento.preventDefault();
    abrir_confirmacao_das_premissas();
  });
  // Primeira carga: os valores vigentes entram no formulário
  carregar_premissas(true);
  // Ao voltar para a aba e de minuto em minuto, os números se atualizam
  document.addEventListener("visibilitychange", atualizar_premissas_sozinho);
  window.setInterval(atualizar_premissas_sozinho, INTERVALO_DA_ATUALIZACAO);
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_premissas);
