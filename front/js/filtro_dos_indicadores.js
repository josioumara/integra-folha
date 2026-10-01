/*
  filtro_dos_indicadores.js — o filtro do alto do Painel de acompanhamento (aba Indicadores do Portal Interno).

  Para que serve: um filtro no início do relatório, que adapta todo o painel à empresa (pelo nome ou pelo CNPJ) e ao
  estado escolhidos. Um filtro só, com duas escolhas:
    - Empresa: pelo nome ou por qualquer CNPJ dela (js/escolha_de_empresa.js); vazio = todas;
    - Estado (UF): no uso do portal, a UF da SEDE da empresa (o uso é medido por empresa); no planejamento, a UF da
      UNIDADE de trabalho de cada funcionário (a regra das análises: região = endereço comercial).
  Quem desenha o painel lê a escolha em filtro_dos_indicadores e redesenha quando ela muda (evento
  "filtro-dos-indicadores-mudou"): o uso (js/banco_uso.js e js/banco_uso_real.js) e o planejamento
  (js/banco_planejamento.js). A escolha fica no endereço (?empresa=EMP001&uf=SP): o "Ver o uso" do Início abre o painel
  já filtrado, e o F5 não perde a escolha.
*/

// A escolha do filtro: "" quer dizer todas (as empresas, ou os estados).
const filtro_dos_indicadores = { empresa_id: "", uf: "" };

// O aviso quando o que foi digitado não acha uma empresa só.
const AVISO_DE_EMPRESA_NAO_ACHADA = "Nenhuma empresa da carteira com este nome ou CNPJ. Confira ou escolha nas sugestões.";

/**
 * Mostra (ou esconde, com texto vazio) o aviso do filtro.
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_aviso_do_filtro(texto) {
  const aviso = document.querySelector("[data-aviso-filtro-indicadores]");
  aviso.textContent = texto;
  aviso.hidden = texto === "";
}

/**
 * Escreve a escolha do filtro no endereço, sem recarregar a página (o resto do endereço, como ?aba=, fica).
 *
 * Recebe: nada. Devolve: nada.
 */
function escrever_filtro_no_endereco() {
  const endereco = new URL(window.location.href);
  // Empresa e estado: entram quando escolhidos, saem quando voltam para "todas".
  if (filtro_dos_indicadores.empresa_id) {
    endereco.searchParams.set("empresa", filtro_dos_indicadores.empresa_id);
  } else {
    endereco.searchParams.delete("empresa");
  }
  if (filtro_dos_indicadores.uf) {
    endereco.searchParams.set("uf", filtro_dos_indicadores.uf);
  } else {
    endereco.searchParams.delete("uf");
  }
  window.history.replaceState(null, "", endereco.toString());
}

/**
 * Avisa a página que o filtro mudou (o uso e o planejamento redesenham) e guarda a escolha no endereço.
 *
 * Recebe: nada. Devolve: nada.
 */
function avisar_que_o_filtro_mudou() {
  escrever_filtro_no_endereco();
  document.dispatchEvent(new CustomEvent("filtro-dos-indicadores-mudou"));
}

/**
 * Escolhe uma empresa no filtro (usado também pelo clique no nome de uma empresa na tabela do uso).
 *
 * Recebe: id — da empresa, ou "" para todas. Devolve: nada.
 */
function escolher_empresa_no_filtro(id) {
  filtro_dos_indicadores.empresa_id = id;
  // O campo mostra o nome e o CNPJ da escolhida (vazio para todas).
  document.querySelector("[data-filtro-empresa-indicadores]").value = texto_do_campo_para_a_empresa(id);
  mostrar_aviso_do_filtro("");
  avisar_que_o_filtro_mudou();
}

/**
 * A pessoa digitou ou escolheu uma sugestão no campo da empresa: acha a empresa e aplica.
 *
 * Recebe: nada. Devolve: nada. Sem achar uma empresa só, o aviso aparece e o filtro continua como estava.
 */
function empresa_do_filtro_mudou() {
  const digitado = document.querySelector("[data-filtro-empresa-indicadores]").value;
  const id = empresa_pelo_texto(digitado);
  if (id === null) {
    mostrar_aviso_do_filtro(AVISO_DE_EMPRESA_NAO_ACHADA);
    return;
  }
  // A mesma empresa de antes: nada muda (evita redesenhar à toa).
  if (id === filtro_dos_indicadores.empresa_id) {
    mostrar_aviso_do_filtro("");
    return;
  }
  escolher_empresa_no_filtro(id);
}

/**
 * A pessoa trocou o estado: aplica.
 *
 * Recebe: nada. Devolve: nada.
 */
function estado_do_filtro_mudou() {
  filtro_dos_indicadores.uf = document.querySelector("[data-filtro-uf-indicadores]").value;
  avisar_que_o_filtro_mudou();
}

/**
 * "Limpar o filtro": volta para todas as empresas e todos os estados.
 *
 * Recebe: nada. Devolve: nada.
 */
function limpar_o_filtro_dos_indicadores() {
  filtro_dos_indicadores.empresa_id = "";
  filtro_dos_indicadores.uf = "";
  document.querySelector("[data-filtro-empresa-indicadores]").value = "";
  document.querySelector("[data-filtro-uf-indicadores]").value = "";
  mostrar_aviso_do_filtro("");
  avisar_que_o_filtro_mudou();
}

/**
 * Acrescenta estados à lista do filtro (sem repetir), em ordem alfabética.
 *
 * Recebe: ufs — ex.: ["SP", "MG"] (das sedes, pelo uso; e das unidades, pelo planejamento). Devolve: nada.
 * O estado escolhido continua escolhido.
 */
function acrescentar_estados_ao_filtro(ufs) {
  const lista = document.querySelector("[data-filtro-uf-indicadores]");
  // Os estados que já estão na lista (a primeira opção é "Todos", com valor vazio).
  const conhecidos = [];
  for (const opcao of lista.options) {
    if (opcao.value) {
      conhecidos.push(opcao.value);
    }
  }
  for (const uf of ufs) {
    if (uf && !conhecidos.includes(uf)) {
      conhecidos.push(uf);
    }
  }
  conhecidos.sort();
  // Refaz a lista: "Todos" e os estados em ordem.
  lista.replaceChildren(new Option("Todos os estados", ""));
  for (const uf of conhecidos) {
    lista.append(new Option(uf, uf));
  }
  lista.value = filtro_dos_indicadores.uf;
}

/**
 * Lê a escolha do endereço (?empresa=EMP001&uf=SP) e liga o campo, a lista e o botão do filtro.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_filtro_dos_indicadores() {
  const parametros = new URLSearchParams(window.location.search);
  filtro_dos_indicadores.empresa_id = parametros.get("empresa") || "";
  filtro_dos_indicadores.uf = parametros.get("uf") || "";
  // O estado pedido no endereço entra na lista já (os outros chegam com os dados).
  if (filtro_dos_indicadores.uf) {
    acrescentar_estados_ao_filtro([filtro_dos_indicadores.uf]);
  }
  const campo = document.querySelector("[data-filtro-empresa-indicadores]");
  // "change": ao escolher uma sugestão ou sair do campo; Enter também aplica (o formulário não recarrega a página).
  campo.addEventListener("change", empresa_do_filtro_mudou);
  document.querySelector("[data-formulario-filtro-indicadores]").addEventListener("submit", function (evento) {
    evento.preventDefault();
    empresa_do_filtro_mudou();
  });
  document.querySelector("[data-filtro-uf-indicadores]").addEventListener("change", estado_do_filtro_mudou);
  document.querySelector("[data-limpar-filtro-indicadores]").addEventListener("click", limpar_o_filtro_dos_indicadores);
  // Quando a lista das empresas chega: o campo mostra a escolhida (e os estados das sedes entram na lista).
  document.addEventListener("empresas-para-escolher-prontas", function () {
    // A pessoa pode estar digitando: só escreve no campo se ele não está em uso.
    if (document.activeElement !== campo) {
      campo.value = texto_do_campo_para_a_empresa(filtro_dos_indicadores.empresa_id);
    }
    const ufs_das_sedes = [];
    for (const empresa of EMPRESAS_PARA_ESCOLHER) {
      ufs_das_sedes.push(empresa.uf);
    }
    acrescentar_estados_ao_filtro(ufs_das_sedes);
  });
}

// Quando o HTML terminar de carregar, prepara o filtro (antes de o uso e o planejamento desenharem).
document.addEventListener("DOMContentLoaded", preparar_filtro_dos_indicadores);
