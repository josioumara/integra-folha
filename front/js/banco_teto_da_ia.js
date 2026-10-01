/*
  banco_teto_da_ia.js — a tela "Teto de gasto da IA" do Portal Interno (ADR-139).

  Para que serve: o especialista do banco vê e ajusta o teto de gasto com IA. A tela:
    - mostra a situação da IA (funcionando, ou pausada desde quando e até quando), o gasto de hoje e do mês com os
      tetos e quantos envios de empresas esperam a IA voltar (só o número);
    - tem um campo e um botão para cada teto. Antes de salvar, avisa quando o valor digitado não passa do gasto já
      feito (a IA ficaria pausada) e quando o teto do dia passa do do mês. Depois de salvar, mostra o que o servidor
      disse (os avisos e quantos envios voltam para a análise);
    - mostra o histórico das mudanças (quando, quem, qual teto, de → para).
  O servidor (GET e POST /api/banco/teto_da_ia) confere tudo de novo e grava. Os números se atualizam sozinhos ao
  voltar para a aba e de minuto em minuto, sem apagar o que a pessoa está digitando (critério das telas do projeto).
*/

// Os dois tetos, na ordem da tela
const PERIODOS_DO_TETO = ["dia", "mes"];
// O nome de cada teto nas frases (ex.: "o teto do dia")
const NOMES_DOS_TETOS = { dia: "do dia", mes: "do mês" };
// O gasto que cada teto compara, e como ele se chama na frase
const GASTO_DE_CADA_TETO = { dia: "gasto_dia_usd", mes: "gasto_mes_usd" };
const NOME_DO_GASTO = { dia: "de hoje", mes: "do mês" };
// Até quando a IA fica pausada por cada teto
const PAUSA_ATE = { dia: "a meia-noite (horário de Brasília)", mes: "o dia 1º do mês que vem" };

// De quanto em quanto tempo a tela pergunta de novo ao servidor (1 minuto, em milissegundos)
const INTERVALO_DA_ATUALIZACAO_DO_TETO = 60000;

// O que veio do servidor na última leitura (null até a primeira resposta)
const estado_do_teto = { situacao: null };

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta (ex.: "td"); classe (ou vazio); texto (ou vazio). Devolve: o elemento.
 */
function criar_elemento_do_teto(etiqueta, classe, texto) {
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
 * Um valor em dólar no padrão brasileiro, com 2 casas (ou até 4, para os gastos pequenos).
 *
 * Recebe: valor — número; casas_no_maximo — 2 para os tetos, 4 para os gastos. Devolve: ex.: "US$ 20,00".
 */
function em_dolares(valor, casas_no_maximo) {
  // O número com separador de milhar e pelo menos duas casas
  const numero_formatado = Number(valor).toLocaleString("pt-BR",
    { minimumFractionDigits: 2, maximumFractionDigits: casas_no_maximo });
  return "US$ " + numero_formatado;
}

/**
 * Transforma um momento gravado (UTC, ex.: "2026-09-29T17:40:00+00:00") na data e hora daqui ("29/09/2026 14:40").
 *
 * Recebe: momento. Devolve: o texto.
 */
function data_e_hora_do_teto(momento) {
  const data = new Date(momento);
  return data.toLocaleDateString("pt-BR") + " " + data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Quantos envios esperam, com singular e plural. Ex.: 1 → "1 envio"; 3 → "3 envios".
 */
function texto_dos_envios(quantidade) {
  if (quantidade === 1) {
    return "1 envio";
  }
  return quantidade + " envios";
}

/**
 * A frase da situação da IA, para o alto da tela.
 *
 * Recebe: situacao — o JSON do servidor. Devolve: o texto.
 * Ex.: pausada pelo dia desde 14:32 → "A IA está pausada desde 29/09/2026 14:32: o teto do dia foi atingido. Ela
 * volta sozinha à meia-noite (horário de Brasília) ou quando o teto subir."
 */
function frase_da_situacao(situacao) {
  // Nenhum teto atingido
  if (!situacao.atingido) {
    return "Os agentes estão funcionando: nenhum teto foi atingido.";
  }
  // Pausada: desde quando (se alguém já chamou a IA depois que o teto foi atingido)
  let frase = "Os agentes estão pausados";
  if (situacao.pausada_desde) {
    frase = frase + " desde " + data_e_hora_do_teto(situacao.pausada_desde);
  }
  frase = frase + ": o teto " + NOMES_DOS_TETOS[situacao.atingido] + " foi atingido. Eles voltam sozinhos " +
    situacao.volta_quando + " ou quando o teto subir.";
  // Ninguém chamou a IA desde então: ainda não há "desde"
  if (!situacao.pausada_desde) {
    frase = frase + " Ninguém chamou os agentes desde que o teto foi atingido.";
  }
  return frase;
}

/**
 * Mostra a situação da IA: o selo, a frase, o gasto de cada período e os envios esperando.
 *
 * Recebe: situacao — o JSON do servidor. Devolve: nada.
 */
function mostrar_situacao_do_teto(situacao) {
  const pausada = Boolean(situacao.atingido);
  // O selo: verde "funcionando" ou laranja "pausada"
  const selo = document.querySelector("[data-selo-situacao-teto]");
  selo.textContent = pausada ? "pausados" : "funcionando";
  selo.classList.toggle("selo-atencao", pausada);
  selo.classList.toggle("selo-sucesso", !pausada);
  // O cartão ganha a faixa laranja em cima enquanto a IA está pausada
  document.querySelector("[data-cartao-situacao-teto]").classList.toggle("cartao-numero-atencao", pausada);
  document.querySelector("[data-texto-situacao-teto]").textContent = frase_da_situacao(situacao);
  // O gasto de cada período, com o seu teto
  for (const periodo of PERIODOS_DO_TETO) {
    const gasto = em_dolares(situacao[GASTO_DE_CADA_TETO[periodo]], 4);
    const teto = em_dolares(situacao["teto_" + periodo + "_usd"], 2);
    document.querySelector("[data-gasto-teto='" + periodo + "']").textContent = gasto + " de " + teto;
  }
  document.querySelector("[data-envios-esperando]").textContent = texto_dos_envios(situacao.envios_esperando);
  // O maior teto aceito, na explicação dos campos
  document.querySelector("[data-teto-maximo]").textContent =
    Number(situacao.teto_maximo_usd).toLocaleString("pt-BR", { minimumFractionDigits: 2 });
}

/**
 * Mostra, embaixo de cada campo, quem mudou o teto por último e quando.
 *
 * Recebe: ultimas_mudancas — {dia: {alterado_em, alterado_por} ou null, mes: ...}. Devolve: nada.
 */
function mostrar_ultimas_mudancas(ultimas_mudancas) {
  for (const periodo of PERIODOS_DO_TETO) {
    const mudanca = ultimas_mudancas[periodo];
    let texto = "Valor inicial: ninguém mudou ainda.";
    if (mudanca) {
      texto = "Mudado em " + data_e_hora_do_teto(mudanca.alterado_em) + " por " + mudanca.alterado_por + ".";
    }
    document.querySelector("[data-ultima-mudanca='" + periodo + "']").textContent = texto;
  }
}

/**
 * Desenha o histórico das mudanças: quando, quem, qual teto e de → para.
 *
 * Recebe: historico — [{periodo, valor_antigo_usd, valor_novo_usd, alterado_em, alterado_por}]. Devolve: nada.
 */
function desenhar_historico_do_teto(historico) {
  const corpo = document.querySelector("[data-corpo-historico-teto]");
  // Tira as linhas de antes (inclusive as de exemplo do protótipo)
  corpo.replaceChildren();
  // Ninguém mudou os tetos ainda: um recado ocupando as 4 colunas
  if (historico.length === 0) {
    const linha_do_recado = criar_elemento_do_teto("tr", "", "");
    const celula_do_recado = criar_elemento_do_teto("td", "", "Nenhuma mudança ainda: os dois tetos estão no valor inicial.");
    celula_do_recado.colSpan = 4;
    linha_do_recado.append(celula_do_recado);
    corpo.append(linha_do_recado);
    return;
  }
  for (const mudanca of historico) {
    const linha = criar_elemento_do_teto("tr", "", "");
    linha.append(criar_elemento_do_teto("td", "", data_e_hora_do_teto(mudanca.alterado_em)));
    linha.append(criar_elemento_do_teto("td", "", mudanca.alterado_por));
    linha.append(criar_elemento_do_teto("td", "", NOMES_DOS_TETOS[mudanca.periodo]));
    linha.append(criar_elemento_do_teto("td", "",
      em_dolares(mudanca.valor_antigo_usd, 2) + " → " + em_dolares(mudanca.valor_novo_usd, 2)));
    corpo.append(linha);
  }
}

/**
 * Diz se a pessoa está mexendo no campo de um teto: com o cursor nele, ou com um valor digitado e não salvo.
 *
 * Recebe: periodo — "dia" ou "mes". Devolve: true se a atualização automática não pode trocar o valor do campo.
 */
function pessoa_esta_mexendo_no_teto(periodo) {
  const campo = document.querySelector("[data-campo-teto='" + periodo + "']");
  // O cursor está no campo
  if (document.activeElement === campo) {
    return true;
  }
  // Ainda não carregou nada: não há o que proteger
  if (estado_do_teto.situacao === null) {
    return false;
  }
  // O valor do campo difere do teto que vale (digitado e ainda não salvo)
  return campo.value !== "" && Number(campo.value) !== Number(estado_do_teto.situacao["teto_" + periodo + "_usd"]);
}

/**
 * Mostra o que veio do servidor e, nos campos em que a pessoa não está mexendo, põe o teto que vale.
 *
 * Recebe: situacao — o JSON de /api/banco/teto_da_ia; periodo_salvo — o teto que acabou de ser gravado (o campo
 * dele sempre recebe o valor novo), ou null. Devolve: nada.
 */
function mostrar_teto(situacao, periodo_salvo) {
  estado_do_teto.situacao = situacao;
  mostrar_situacao_do_teto(situacao);
  mostrar_ultimas_mudancas(situacao.ultimas_mudancas);
  desenhar_historico_do_teto(situacao.historico);
  for (const periodo of PERIODOS_DO_TETO) {
    // O campo recebe o teto que vale, se a pessoa não estiver digitando nele (ou se ele acabou de ser salvo)
    if (periodo === periodo_salvo || !pessoa_esta_mexendo_no_teto(periodo)) {
      document.querySelector("[data-campo-teto='" + periodo + "']").value = String(situacao["teto_" + periodo + "_usd"]);
    }
    atualizar_previa_do_teto(periodo);
  }
  // Os valores reais estão na tela: saem da espera (js/carregando_dados.js)
  marcar_todos_como_carregados("[data-selo-situacao-teto], [data-texto-situacao-teto], [data-gasto-teto], " +
    "[data-envios-esperando], [data-ultima-mudanca], [data-tabela-historico-teto]");
}

/**
 * O aviso antes de salvar: o valor digitado não passa do gasto já feito, ou o teto do dia passa do do mês.
 *
 * Recebe: periodo — o teto do campo. Devolve: nada. O aviso some quando o valor está bem (ou vazio).
 */
function atualizar_previa_do_teto(periodo) {
  const previa = document.querySelector("[data-previa-teto='" + periodo + "']");
  const valor = Number(document.querySelector("[data-campo-teto='" + periodo + "']").value);
  const situacao = estado_do_teto.situacao;
  // Sem dado do servidor ou sem valor para comparar: nenhum aviso
  if (situacao === null || !(valor > 0)) {
    previa.hidden = true;
    return;
  }
  const avisos = [];
  // O valor não passa do gasto do período: a IA ficaria pausada
  const gasto = situacao[GASTO_DE_CADA_TETO[periodo]];
  if (valor <= gasto) {
    avisos.push("Com " + em_dolares(valor, 2) + ", o teto " + NOMES_DOS_TETOS[periodo] + " não passa do gasto " +
      NOME_DO_GASTO[periodo] + " (" + em_dolares(gasto, 4) + "): os agentes ficam pausados até " + PAUSA_ATE[periodo] +
      " ou até o teto subir.");
  }
  // O teto do dia acima do do mês: o do dia nunca chega a pausar
  const teto_do_dia = periodo === "dia" ? valor : situacao.teto_dia_usd;
  const teto_do_mes = periodo === "mes" ? valor : situacao.teto_mes_usd;
  if (teto_do_dia > teto_do_mes) {
    avisos.push("O teto do dia fica maior que o do mês: o do mês é atingido antes.");
  }
  previa.textContent = avisos.join(" ");
  previa.hidden = avisos.length === 0;
}

/**
 * Mostra (ou esconde) o recado de erro embaixo dos campos.
 *
 * Recebe: texto (ou vazio, para esconder). Devolve: nada.
 */
function mostrar_erro_do_teto(texto) {
  const erro = document.querySelector("[data-erro-teto]");
  erro.hidden = !texto;
  erro.textContent = texto || "";
}

/**
 * Mostra, depois de salvar, o aviso verde e os avisos amarelos do servidor.
 *
 * Recebe: periodo — o teto salvo; situacao — a resposta do servidor. Devolve: nada.
 */
function mostrar_resultado_do_ajuste(periodo, situacao) {
  // O aviso verde: o teto gravado e, se a IA voltou, os envios que voltam para a análise
  let texto = "Teto " + NOMES_DOS_TETOS[periodo] + " gravado: " + em_dolares(situacao["teto_" + periodo + "_usd"], 2) + ".";
  if (situacao.ia_liberada && situacao.envios_esperando > 0) {
    texto = texto + " Os agentes voltaram: " + texto_dos_envios(situacao.envios_esperando) +
      (situacao.envios_esperando === 1 ? " volta" : " voltam") + " para a análise agora.";
  }
  document.querySelector("[data-aviso-teto-texto]").textContent = texto;
  document.querySelector("[data-aviso-teto]").hidden = false;
  // Os avisos amarelos (ex.: o teto novo não passa do gasto de hoje)
  const lugar_dos_avisos = document.querySelector("[data-avisos-do-ajuste]");
  lugar_dos_avisos.replaceChildren();
  for (const aviso of situacao.avisos || []) {
    lugar_dos_avisos.append(criar_elemento_do_teto("p", "aviso-envio-parado", aviso));
  }
  lugar_dos_avisos.hidden = lugar_dos_avisos.children.length === 0;
}

/**
 * "Salvar o teto do dia" (ou do mês): confere o campo, manda ao servidor e mostra a tela atualizada.
 *
 * Recebe: periodo — "dia" ou "mes". Devolve: nada.
 */
async function salvar_teto(periodo) {
  const campo = document.querySelector("[data-campo-teto='" + periodo + "']");
  const botao = document.querySelector("[data-salvar-teto='" + periodo + "']");
  // Campo vazio (ou com algo que não é número, que o campo numérico entrega vazio)
  if (campo.value.trim() === "") {
    mostrar_erro_do_teto("Informe o teto " + NOMES_DOS_TETOS[periodo] + ", em dólares.");
    return;
  }
  mostrar_erro_do_teto("");
  // Evita gravar duas vezes com dois cliques rápidos
  botao.disabled = true;
  try {
    const resposta = await fetch("/api/banco/teto_da_ia", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ periodo: periodo, valor_usd: campo.value.trim() }),
    });
    const dados = await resposta.json();
    // Recusado: a mensagem do servidor aparece embaixo dos campos
    if (!resposta.ok) {
      mostrar_erro_do_teto(typeof dados.detail === "string" ? dados.detail : "Confira o valor e tente de novo.");
      return;
    }
    // Gravado: a tela mostra a situação nova, com o valor gravado no campo
    mostrar_teto(dados, periodo);
    mostrar_resultado_do_ajuste(periodo, dados);
  } catch (erro) {
    mostrar_erro_do_teto("Não foi possível falar com o servidor. Tente de novo em instantes.");
  } finally {
    botao.disabled = false;
  }
}

/**
 * O servidor não respondeu: os números de exemplo viram traço e o histórico sai da espera, vazio.
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_teto_sem_dado() {
  // Cada número vira "—" (se já mostrava o de verdade, fica como está)
  for (const elemento of document.querySelectorAll("[data-selo-situacao-teto], [data-texto-situacao-teto], " +
    "[data-gasto-teto], [data-envios-esperando], [data-ultima-mudanca]")) {
    mostrar_dado_indisponivel(elemento);
  }
  // O histórico: só as linhas de exemplo saem (um histórico de verdade já mostrado continua)
  const tabela = document.querySelector("[data-tabela-historico-teto]");
  if (!tabela.hasAttribute("data-dado-pronto")) {
    document.querySelector("[data-corpo-historico-teto]").replaceChildren();
  }
  marcar_como_carregado(tabela);
}

/**
 * Pede ao servidor a situação do teto e mostra.
 *
 * Recebe: nada. Devolve: nada.
 */
async function carregar_teto() {
  try {
    const resposta = await fetch("/api/banco/teto_da_ia");
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro_do_teto(typeof dados.detail === "string" ? dados.detail : "Não foi possível abrir o teto de gasto.");
      liberar_teto_sem_dado();
      return;
    }
    mostrar_teto(dados, null);
  } catch (erro) {
    mostrar_erro_do_teto("Não foi possível falar com o servidor. Tente de novo em instantes.");
    liberar_teto_sem_dado();
  }
}

/**
 * A atualização automática: pergunta de novo ao servidor, com a aba à vista.
 *
 * Recebe: nada. Devolve: nada. Os campos em que a pessoa está mexendo ficam como estão (ver mostrar_teto).
 */
function atualizar_teto_sozinho() {
  // Aba escondida: espera a pessoa voltar (o evento de visibilidade chama de novo)
  if (document.hidden) {
    return;
  }
  carregar_teto();
}

/**
 * Liga os campos e botões, busca a situação e liga a atualização automática. Chamada uma vez, ao carregar a página.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_tela_do_teto() {
  for (const periodo of PERIODOS_DO_TETO) {
    // Salvar pelo botão ou pelo Enter no campo (sem recarregar a página)
    document.querySelector("[data-formulario-teto='" + periodo + "']").addEventListener("submit", function (evento) {
      evento.preventDefault();
      salvar_teto(periodo);
    });
    // O aviso antes de salvar acompanha o que a pessoa digita
    document.querySelector("[data-campo-teto='" + periodo + "']").addEventListener("input", function () {
      atualizar_previa_do_teto(periodo);
    });
  }
  carregar_teto();
  // Ao voltar para a aba e de minuto em minuto, os números se atualizam
  document.addEventListener("visibilitychange", atualizar_teto_sozinho);
  window.setInterval(atualizar_teto_sozinho, INTERVALO_DA_ATUALIZACAO_DO_TETO);
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_do_teto);
