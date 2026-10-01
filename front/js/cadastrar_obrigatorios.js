/*
  cadastrar_obrigatorios.js — as informações obrigatórias do parâmetro na tela "Cadastrar funcionários" (ADR-143).

  Para que serve:
    - antes do envio, a tela diz quais informações o arquivo precisa ter, lidas do parâmetro vigente do banco (hoje:
      o CPF, o código da profissão pela CBO, a renda bruta mensal e a data de admissão). Nada disso é escrito aqui: se o
      banco marcar mais um campo na tela Parâmetros, ele aparece sozinho;
    - guarda quais campos são obrigatórios para as outras partes da tela: o aceite das colunas (js/cadastrar_real.js)
      e a conferência da lista (js/cadastrar_conferencia_real.js) pedem confirmação só deles.
  As colunas do parâmetro vêm de /api/empresa/colunas_da_consulta (as mesmas da grade de funcionários) e são buscadas
  uma vez só. Aberta como arquivo (o protótipo, sem servidor), o quadro fica escondido e o aceite fica numa parte só.
  Usa do js/grade_do_parametro.js: buscar_colunas_do_parametro e colunas_obrigatorias.
*/

// A busca das colunas do parâmetro: uma "promessa" (o resultado que ainda vai chegar), dividida por todas as partes
// da tela que pedirem, para o servidor ser consultado uma vez só. null antes da primeira busca.
let busca_das_colunas_do_cadastro = null;
// Os nomes técnicos dos campos obrigatórios do parâmetro vigente, depois que chegam do servidor (ex.: ["cpf",
// "codigo_cbo", "data_admissao", "valor_renda"]). null enquanto não chegaram (ou sem servidor): o aceite das colunas
// fica numa parte só, como antes.
let campos_obrigatorios_do_cadastro = null;

/**
 * As colunas do parâmetro vigente ({campo, rotulo, grupo, tipo, obrigatorio, descricao}), buscadas uma vez só.
 *
 * Recebe: nada. Devolve: uma promessa com a lista (vazia sem servidor ou com erro).
 * Com a resposta, os campos obrigatórios ficam guardados (campos_obrigatorios_do_cadastro). Se a busca falhar, a
 * próxima chamada tenta de novo (a lista vazia não fica guardada).
 */
async function colunas_do_parametro_no_cadastro() {
  // A primeira chamada começa a busca; as outras esperam a mesma
  if (busca_das_colunas_do_cadastro === null) {
    busca_das_colunas_do_cadastro = buscar_colunas_do_parametro("/api/empresa/colunas_da_consulta");
  }
  const colunas = await busca_das_colunas_do_cadastro;
  // Sem resposta: a próxima chamada tenta de novo
  if (colunas.length === 0) {
    busca_das_colunas_do_cadastro = null;
    return colunas;
  }
  // Com resposta: os campos obrigatórios ficam guardados para o aceite das colunas
  campos_obrigatorios_do_cadastro = nomes_dos_campos_obrigatorios(colunas);
  return colunas;
}

/**
 * Os nomes técnicos dos campos obrigatórios de uma lista de colunas do parâmetro.
 *
 * Recebe: colunas. Devolve: a lista de nomes. Ex.: [{campo: "cpf", obrigatorio: true}, {campo: "sexo", obrigatorio:
 * false}] → ["cpf"].
 */
function nomes_dos_campos_obrigatorios(colunas) {
  const nomes = [];
  for (const coluna of colunas_obrigatorias(colunas)) {
    nomes.push(coluna.campo);
  }
  return nomes;
}

/**
 * Um item do quadro "O arquivo precisa ter": o nome do campo, em negrito, e a descrição que o banco escreveu no
 * parâmetro. Ex.: "CPF: CPF do funcionário".
 *
 * Recebe: coluna. Devolve: o <li>.
 */
function item_do_campo_obrigatorio(coluna) {
  const item = document.createElement("li");
  const nome = document.createElement("strong");
  nome.textContent = coluna.rotulo;
  item.appendChild(nome);
  // A descrição do banco, quando ele escreveu uma
  if (coluna.descricao) {
    item.append(": " + coluna.descricao);
  }
  return item;
}

/**
 * Mostra, acima do envio, as informações que o arquivo precisa ter: uma por campo obrigatório do parâmetro vigente.
 * Depois, guarda os campos obrigatórios e separa o aceite das colunas, se ele já estiver na tela.
 *
 * Recebe: nada. Devolve: nada. Sem servidor (o protótipo), o quadro fica escondido; com erro, ele diz que não foi
 * possível carregar agora (nunca uma lista de exemplo).
 */
async function mostrar_campos_obrigatorios_do_envio() {
  // Aberta como arquivo: não há parâmetro para ler
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  const quadro = document.querySelector("[data-campos-obrigatorios]");
  const lista = document.querySelector("[data-lista-campos-obrigatorios]");
  const aviso_de_erro = document.querySelector("[data-erro-campos-obrigatorios]");
  const colunas = await colunas_do_parametro_no_cadastro();
  const obrigatorias = colunas_obrigatorias(colunas);
  lista.replaceChildren();
  // Sem resposta do servidor: o quadro diz que não carregou, sem inventar a lista
  if (obrigatorias.length === 0) {
    lista.hidden = true;
    aviso_de_erro.hidden = false;
    quadro.hidden = false;
    return;
  }
  for (const coluna of obrigatorias) {
    lista.appendChild(item_do_campo_obrigatorio(coluna));
  }
  lista.hidden = false;
  aviso_de_erro.hidden = true;
  quadro.hidden = false;
  // Os campos obrigatórios já estão guardados: o aceite das colunas que já estiver na tela é separado agora
  separar_as_colunas_opcionais();
}

// Quando o HTML terminar de carregar, busca o parâmetro e mostra o quadro.
document.addEventListener("DOMContentLoaded", mostrar_campos_obrigatorios_do_envio);
