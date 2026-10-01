/*
  banco_agentes_kbs.js — a seção "Guardrails das KBs" do Acompanhamento dos agentes (engrenagem Configuração) do
  Portal Interno (ADR-125).

  Para que serve: mostra o que a TRAVA das KBs de endomarketing apontou, do mais recente para o mais antigo: quando,
  em qual KB, de qual dono (diretrizes gerais, Santander ou empresa), em que momento (carga inicial, salvar, publicar,
  revisar ou conferir), a regra, se bloqueou ou só avisou, o detalhe, o trecho e quem fez. Em cima, três números:
  quantos bloqueios, quantos avisos e quantas KBs tiveram achados, contados pelo servidor em TODOS os achados gravados
  (a tabela mostra só os mais recentes). Dá para filtrar por dono.

  Os dados vêm de /api/banco/kbs-endomarketing/achados (só o perfil BANCO). Todo texto entra com textContent.
  Os dados são pedidos quando a página abre e quando o filtro muda. Servida pela aplicação, os números e a tabela
  esperam com a barra cinza até o dado chegar (js/carregando_dados.js); se o servidor falhar, os números viram "—" e
  aparece o aviso, nunca um zero inventado.
*/

// O endereço das rotas das KBs.
const ENDERECO_DOS_ACHADOS = "/api/banco/kbs-endomarketing";
// O nome de cada momento da trava, para a tabela.
const NOME_DO_MOMENTO_DA_TRAVA = { CARGA_INICIAL: "Carga inicial", SALVAR: "Salvar", PUBLICAR: "Publicar",
                                   REVISAR: "Revisar", VERIFICAR: "Conferir" };

/**
 * Pede à API e devolve { ok, dados } (sem conexão: ok falso, com um recado).
 */
async function pedir_os_achados(endereco) {
  try {
    const resposta = await fetch(endereco);
    return { ok: resposta.ok, dados: await resposta.json() };
  } catch (erro) {
    return { ok: false, dados: { detail: "Sem conexão com o servidor." } };
  }
}

/**
 * Uma célula de tabela com o texto (e a classe, se houver).
 */
function celula_do_achado(texto, classe) {
  const celula = document.createElement("td");
  celula.textContent = texto;
  if (classe) {
    celula.className = classe;
  }
  return celula;
}

/**
 * A data e a hora em "DD/MM/AAAA HH:MM" (horário do navegador). Exemplo: "2026-09-28T20:05:00+00:00" → "28/09/2026 17:05".
 */
function data_e_hora_do_achado(momento) {
  const data = new Date(momento);
  return data.toLocaleDateString("pt-BR") + " " + data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Preenche os três números do alto com os totais que o servidor contou em todos os achados: bloqueios, avisos e KBs
 * com achados.
 *
 * Recebe: totais — {bloqueios, avisos, kbs_com_achados}. Devolve: nada. Ex.: {bloqueios: 9, ...} → "9".
 */
function mostrar_numeros_dos_achados(totais) {
  document.querySelector("[data-kbs-bloqueios]").textContent = Number(totais.bloqueios).toLocaleString("pt-BR");
  document.querySelector("[data-kbs-avisos]").textContent = Number(totais.avisos).toLocaleString("pt-BR");
  document.querySelector("[data-kbs-afetadas]").textContent = Number(totais.kbs_com_achados).toLocaleString("pt-BR");
}

/**
 * Tira os três números e a tabela da espera (a barra cinza some e o dado aparece).
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_os_achados() {
  marcar_como_carregado(document.querySelector("[data-kbs-bloqueios]"));
  marcar_como_carregado(document.querySelector("[data-kbs-avisos]"));
  marcar_como_carregado(document.querySelector("[data-kbs-afetadas]"));
  marcar_como_carregado(document.querySelector("[data-tabela-achados-kbs]"));
}

/**
 * O servidor não respondeu: os números viram "—" (se ainda não mostravam um dado de verdade), a tabela sai da espera
 * e o aviso aparece. Nunca um zero inventado.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_achados_indisponiveis() {
  mostrar_dado_indisponivel(document.querySelector("[data-kbs-bloqueios]"));
  mostrar_dado_indisponivel(document.querySelector("[data-kbs-avisos]"));
  mostrar_dado_indisponivel(document.querySelector("[data-kbs-afetadas]"));
  marcar_como_carregado(document.querySelector("[data-tabela-achados-kbs]"));
  const aviso = document.querySelector("[data-sem-achados-kbs]");
  aviso.textContent = "Não foi possível ler os achados agora.";
  aviso.hidden = false;
}

/**
 * Monta a tabela dos achados (ou o aviso de "nenhum achado").
 */
function montar_tabela_dos_achados(achados) {
  const corpo = document.querySelector("[data-corpo-achados-kbs]");
  corpo.replaceChildren();
  for (const achado of achados) {
    const linha = document.createElement("tr");
    linha.append(celula_do_achado(data_e_hora_do_achado(achado.feito_em), ""));
    linha.append(celula_do_achado(achado.kb_id + (achado.versao ? " v" + achado.versao : ""), ""));
    linha.append(celula_do_achado(achado.dono, ""));
    linha.append(celula_do_achado(NOME_DO_MOMENTO_DA_TRAVA[achado.momento] || achado.momento, ""));
    linha.append(celula_do_achado(achado.regra, ""));
    if (achado.gravidade === "BLOQUEIA") {
      linha.append(celula_do_achado("Bloqueou", "celula-bloqueia"));
    } else {
      linha.append(celula_do_achado("Aviso", "celula-aviso"));
    }
    linha.append(celula_do_achado(achado.detalhe + (achado.trecho ? " · “" + achado.trecho + "”" : ""), ""));
    linha.append(celula_do_achado(achado.feito_por, ""));
    corpo.append(linha);
  }
  // Sem nenhum achado: o recado de que todas as KBs passaram (o texto volta ao normal depois de uma falha)
  const aviso = document.querySelector("[data-sem-achados-kbs]");
  aviso.textContent = "Nenhum achado: todas as KBs passaram na trava.";
  aviso.hidden = achados.length > 0;
}

/**
 * Busca os achados (do dono escolhido no filtro, ou de todos) e atualiza a sub-aba.
 */
async function carregar_achados_das_kbs() {
  const dono = document.querySelector("[data-filtro-dono-achados]").value;
  let endereco = ENDERECO_DOS_ACHADOS + "/achados";
  if (dono) {
    endereco = endereco + "?dono=" + encodeURIComponent(dono);
  }
  const resposta = await pedir_os_achados(endereco);
  // Recusado, com erro ou sem os totais: "—" e o aviso, nunca um número inventado
  if (!resposta.ok || !resposta.dados.totais) {
    mostrar_achados_indisponiveis();
    return;
  }
  mostrar_numeros_dos_achados(resposta.dados.totais);
  montar_tabela_dos_achados(resposta.dados.achados);
  liberar_os_achados();
}

/**
 * Enche o filtro de donos (todos, gerais, Santander e cada empresa) e liga a troca.
 */
async function preparar_filtro_dos_achados() {
  const filtro = document.querySelector("[data-filtro-dono-achados]");
  const resposta = await pedir_os_achados(ENDERECO_DOS_ACHADOS + "/modelos");
  if (resposta.ok) {
    for (const item of resposta.dados.donos) {
      const opcao = document.createElement("option");
      opcao.value = item.dono;
      opcao.textContent = item.nome;
      filtro.append(opcao);
    }
  }
  filtro.addEventListener("change", carregar_achados_das_kbs);
}

/**
 * O começo: só com o servidor (aberta como arquivo, a sub-aba fica com o aviso).
 */
async function comecar_guardrails_das_kbs() {
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  await preparar_filtro_dos_achados();
  await carregar_achados_das_kbs();
}

comecar_guardrails_das_kbs();
