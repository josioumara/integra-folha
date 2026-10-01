/*
  banco_parametros.js — a tela "Parâmetros" do Portal Interno: o layout que o banco quer receber (ADR-76).

  Para que serve: mostra os campos do layout vigente numa lista SÓ DE LEITURA. Para mudar, o especialista usa uma
  janela:
    - "+ Novo campo" abre a janela vazia;
    - "Editar" (em cada campo) abre a mesma janela preenchida;
    - "Salvar" na janela JÁ GRAVA: o servidor confere, grava uma versão nova (as antigas ficam) e o registro das
      alterações (quem, quando, o quê) aparece embaixo da lista;
    - "Tirar este campo" (só ao editar) pede confirmação com um segundo clique e grava na hora.
  A lista inteira é mandada a /api/banco/parametros/layout a cada gravação (o servidor compara com a versão vigente
  para escrever o registro).
*/

// Os campos da versão vigente (como vieram do servidor), o catálogo de tipos, a busca e o campo aberto na janela.
const estado_dos_parametros = { campos: [], tipos: [], busca: "", campo_em_edicao: null };

// As marcações e os textos da janela (o nome do atributo do campo em cada caixa ou linha de texto).
// "igual_para_todos": o campo pode ter o mesmo valor para todos os funcionários do arquivo (um dado da empresa)
const MARCACOES_DO_CAMPO = ["obrigatorio", "sensivel", "uso_comercial_permitido", "igual_para_todos"];
const TEXTOS_DO_CAMPO = ["descricao", "regra", "nao_confundir_com", "exemplo"];
// A faixa esperada (ADR-128): o mínimo e o máximo, só nos tipos de valor (o servidor recusa nos outros)
const LIMITES_DO_CAMPO = ["minimo", "maximo"];
const TIPOS_COM_FAIXA = ["DECIMAL_MONETARIO"];

/**
 * Um limite gravado ("500.00") como a pessoa lê ("R$ 500,00").
 *
 * Recebe: valor — texto com ponto decimal. Devolve: o texto em reais.
 */
function limite_em_reais(valor) {
  // O número com ponto de milhar e duas casas; o "R$ " com espaço comum, igual ao registro que o servidor escreve
  const numero = Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return "R$ " + numero;
}

/**
 * A faixa do campo na lista. Ex.: mínimo 500 → "a partir de R$ 500,00"; os dois → "R$ 500,00 a R$ 9.000,00";
 * sem faixa → "—".
 *
 * Recebe: campo. Devolve: o texto.
 */
function texto_da_faixa(campo) {
  const tem_minimo = campo.minimo !== null && campo.minimo !== undefined;
  const tem_maximo = campo.maximo !== null && campo.maximo !== undefined;
  if (tem_minimo && tem_maximo) {
    return limite_em_reais(campo.minimo) + " a " + limite_em_reais(campo.maximo);
  }
  if (tem_minimo) {
    return "a partir de " + limite_em_reais(campo.minimo);
  }
  if (tem_maximo) {
    return "até " + limite_em_reais(campo.maximo);
  }
  return "—";
}

/**
 * Um limite gravado ("1500.50") no jeito de digitar da janela ("1500,50"); sem limite, vazio.
 *
 * Recebe: valor. Devolve: o texto.
 */
function limite_para_a_janela(valor) {
  if (valor === null || valor === undefined) {
    return "";
  }
  return String(valor).replace(".", ",");
}

/**
 * Mostra o mínimo e o máximo na janela só quando o tipo escolhido é de valor.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_faixa_conforme_o_tipo() {
  const tipo = document.querySelector("[data-campo-tipo]").value;
  document.querySelector("[data-faixa-do-campo]").hidden = !TIPOS_COM_FAIXA.includes(tipo);
}

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro).
 *
 * Recebe: etiqueta; classe; texto. Devolve: o elemento.
 */
function criar_elemento_parametro(etiqueta, classe, texto) {
  const elemento = document.createElement(etiqueta);
  if (classe) {
    elemento.className = classe;
  }
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * "Sim" ou "—" para uma marcação na lista (a lista é só de leitura).
 *
 * Recebe: marcado — true ou false. Devolve: o texto.
 */
function sim_ou_nao(marcado) {
  if (marcado) {
    return "Sim";
  }
  return "—";
}

/**
 * Desenha a lista de campos, agrupada pelo grupo do campo, com o filtro da busca.
 *
 * Recebe: nada. Devolve: nada.
 */
function desenhar_campos() {
  const corpo = document.querySelector("[data-corpo-parametros]");
  corpo.replaceChildren();
  const busca = estado_dos_parametros.busca.toLowerCase();
  let grupo_atual = null;
  for (const campo of estado_dos_parametros.campos) {
    // A busca olha o nome técnico e a descrição
    const texto_do_campo = (campo.campo + " " + (campo.descricao || "")).toLowerCase();
    if (busca && !texto_do_campo.includes(busca)) {
      continue;
    }
    // Uma linha de título a cada grupo novo
    if (campo.grupo !== grupo_atual) {
      grupo_atual = campo.grupo;
      const linha_do_grupo = criar_elemento_parametro("tr", "linha-grupo-parametro", "");
      const celula_do_grupo = criar_elemento_parametro("th", "", grupo_atual);
      celula_do_grupo.colSpan = 9;
      celula_do_grupo.scope = "colgroup";
      linha_do_grupo.append(celula_do_grupo);
      corpo.append(linha_do_grupo);
    }
    const linha = criar_elemento_parametro("tr", "", "");
    linha.dataset.campo = campo.campo;
    linha.append(criar_elemento_parametro("td", "celula-nome-parametro", campo.campo));
    linha.append(criar_elemento_parametro("td", "", campo.tipo));
    linha.append(criar_elemento_parametro("td", "celula-marcar", sim_ou_nao(campo.obrigatorio)));
    linha.append(criar_elemento_parametro("td", "celula-marcar", sim_ou_nao(campo.sensivel)));
    linha.append(criar_elemento_parametro("td", "celula-marcar", sim_ou_nao(campo.uso_comercial_permitido)));
    linha.append(criar_elemento_parametro("td", "celula-marcar", sim_ou_nao(campo.igual_para_todos)));
    // A faixa esperada do valor (ADR-128), ou "—"
    const celula_da_faixa = criar_elemento_parametro("td", "", texto_da_faixa(campo));
    celula_da_faixa.dataset.faixa = campo.campo;
    linha.append(celula_da_faixa);
    linha.append(criar_elemento_parametro("td", "celula-motivo", campo.descricao || ""));
    // "Editar": abre a janela preenchida com este campo
    const celula_da_acao = criar_elemento_parametro("td", "celula-acoes-parametro", "");
    const editar = criar_elemento_parametro("button", "botao-descartar", "Editar");
    editar.type = "button";
    editar.dataset.editarCampo = campo.campo;
    editar.addEventListener("click", function () {
      abrir_janela_do_campo(campo);
    });
    celula_da_acao.append(editar);
    linha.append(celula_da_acao);
    corpo.append(linha);
  }
}

/**
 * Transforma o momento gravado (UTC, "2026-09-25T21:40:00+00:00") na data e hora daqui ("25/09/2026 18:40").
 *
 * Recebe: momento. Devolve: o texto.
 */
function data_e_hora(momento) {
  const data = new Date(momento);
  return data.toLocaleDateString("pt-BR") + " " + data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Desenha o registro das alterações: cada versão, quem gravou, quando e o que mudou.
 *
 * Recebe: registro — [{versao, criado_em, criado_por, mudancas}]. Devolve: nada.
 */
function desenhar_registro(registro) {
  const corpo = document.querySelector("[data-corpo-registro]");
  corpo.replaceChildren();
  for (const versao of registro) {
    const linha = criar_elemento_parametro("tr", "", "");
    linha.append(criar_elemento_parametro("td", "", "v" + versao.versao));
    linha.append(criar_elemento_parametro("td", "", data_e_hora(versao.criado_em)));
    linha.append(criar_elemento_parametro("td", "", versao.criado_por));
    const celula_das_mudancas = criar_elemento_parametro("td", "", "");
    const lista = criar_elemento_parametro("ul", "lista-mudancas", "");
    for (const mudanca of versao.mudancas) {
      lista.append(criar_elemento_parametro("li", "", mudanca));
    }
    celula_das_mudancas.append(lista);
    linha.append(celula_das_mudancas);
    corpo.append(linha);
  }
}

/**
 * Mostra o que veio do servidor: a versão, os campos, o catálogo de tipos e o registro.
 *
 * Recebe: dados — {versao, campos, tipos, registro}. Devolve: nada.
 */
function mostrar_parametros(dados) {
  estado_dos_parametros.campos = dados.campos;
  estado_dos_parametros.tipos = dados.tipos;
  document.querySelector("[data-versao-vigente]").textContent = "v" + dados.versao;
  // O catálogo de tipos na escolha da janela
  const escolha_do_tipo = document.querySelector("[data-campo-tipo]");
  escolha_do_tipo.replaceChildren();
  for (const tipo of dados.tipos) {
    escolha_do_tipo.add(new Option(tipo, tipo));
  }
  desenhar_campos();
  desenhar_registro(dados.registro);
}

/**
 * Mostra (ou esconde) um recado de erro.
 *
 * Recebe: seletor — onde; texto (ou vazio). Devolve: nada.
 */
function mostrar_erro(seletor, texto) {
  const erro = document.querySelector(seletor);
  erro.hidden = !texto;
  erro.textContent = texto || "";
}

/**
 * Abre a janela do campo: vazia (campo novo) ou preenchida (editar).
 *
 * Recebe: campo — o campo a editar, ou null para um campo novo. Devolve: nada.
 */
function abrir_janela_do_campo(campo) {
  estado_dos_parametros.campo_em_edicao = campo;
  const novo = campo === null;
  document.querySelector("[data-titulo-janela-campo]").textContent = novo ? "Novo campo" : "Editar " + campo.campo;
  // O nome técnico só se escolhe no campo novo (mudar o nome seria outro campo)
  const nome = document.querySelector("[data-campo-nome]");
  nome.value = novo ? "" : campo.campo;
  nome.disabled = !novo;
  document.querySelector("[data-campo-grupo]").value = novo ? "" : campo.grupo;
  document.querySelector("[data-campo-tipo]").value = novo ? estado_dos_parametros.tipos[0] : campo.tipo;
  for (const marcacao of MARCACOES_DO_CAMPO) {
    document.querySelector("[data-campo-marcacao='" + marcacao + "']").checked = novo ? false : campo[marcacao];
  }
  for (const texto of TEXTOS_DO_CAMPO) {
    document.querySelector("[data-campo-texto='" + texto + "']").value = novo ? "" : (campo[texto] || "");
  }
  // O mínimo e o máximo (vazio = sem limite), visíveis só num tipo de valor
  for (const limite of LIMITES_DO_CAMPO) {
    document.querySelector("[data-campo-limite='" + limite + "']").value = novo ? "" : limite_para_a_janela(campo[limite]);
  }
  mostrar_faixa_conforme_o_tipo();
  // "Tirar este campo": só ao editar, e volta ao texto de sempre
  const tirar = document.querySelector("[data-tirar-campo]");
  tirar.hidden = novo;
  tirar.dataset.confirmar = "";
  tirar.textContent = "Tirar este campo";
  mostrar_erro("[data-erro-janela-campo]", "");
  document.querySelector("[data-janela-campo]").showModal();
}

/**
 * O campo como ficou na janela (o nome técnico, o grupo, o tipo, as marcações e os textos).
 *
 * Recebe: nada. Devolve: o campo.
 */
function campo_da_janela() {
  const campo = {
    campo: document.querySelector("[data-campo-nome]").value.trim(),
    grupo: document.querySelector("[data-campo-grupo]").value.trim(),
    tipo: document.querySelector("[data-campo-tipo]").value,
  };
  for (const marcacao of MARCACOES_DO_CAMPO) {
    campo[marcacao] = document.querySelector("[data-campo-marcacao='" + marcacao + "']").checked;
  }
  for (const texto of TEXTOS_DO_CAMPO) {
    campo[texto] = document.querySelector("[data-campo-texto='" + texto + "']").value;
  }
  // O mínimo e o máximo só num tipo de valor; nos outros, sem faixa (o servidor converte "500,00" em número)
  const tem_faixa = TIPOS_COM_FAIXA.includes(campo.tipo);
  for (const limite of LIMITES_DO_CAMPO) {
    const digitado = document.querySelector("[data-campo-limite='" + limite + "']").value.trim();
    // Vazio ou tipo sem faixa: sem limite
    campo[limite] = null;
    if (tem_faixa && digitado) {
      campo[limite] = digitado;
    }
  }
  return campo;
}

/**
 * Grava a lista inteira de campos como uma versão nova. O servidor confere e devolve a tela atualizada.
 *
 * Recebe: campos — a lista nova; recado — o aviso verde se der certo. Devolve: true se gravou.
 */
async function gravar_campos(campos, recado) {
  try {
    const resposta = await fetch("/api/banco/parametros/layout", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campos: campos }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro("[data-erro-janela-campo]", typeof dados.detail === "string" ? dados.detail : "Confira o campo e tente de novo.");
      return false;
    }
    mostrar_parametros(dados);
    document.querySelector("[data-aviso-parametros-texto]").textContent =
      recado + " Versão v" + dados.versao + " gravada; a busca do Agente Interpretador se atualiza sozinha em alguns segundos.";
    document.querySelector("[data-aviso-parametros]").hidden = false;
    return true;
  } catch (erro) {
    mostrar_erro("[data-erro-janela-campo]", "Não foi possível falar com o servidor. Tente de novo em instantes.");
    return false;
  }
}

/**
 * "Salvar" na janela: põe o campo novo no fim da lista, ou troca o campo editado, e grava na hora.
 *
 * Recebe: nada. Devolve: nada.
 */
async function salvar_campo() {
  const campo = campo_da_janela();
  if (!campo.campo || !campo.grupo) {
    mostrar_erro("[data-erro-janela-campo]", "Informe o nome técnico e o grupo do campo.");
    return;
  }
  const editando = estado_dos_parametros.campo_em_edicao;
  const campos_novos = [];
  for (const existente of estado_dos_parametros.campos) {
    // No campo novo, o nome não pode repetir um que já existe
    if (editando === null && existente.campo === campo.campo) {
      mostrar_erro("[data-erro-janela-campo]", "Já existe um campo \"" + campo.campo + "\".");
      return;
    }
    // Ao editar, o campo editado entra no lugar dele
    if (editando !== null && existente.campo === editando.campo) {
      campos_novos.push(campo);
    } else {
      campos_novos.push(existente);
    }
  }
  if (editando === null) {
    campos_novos.push(campo);
  }
  const recado = editando === null ? "Campo " + campo.campo + " incluído." : "Campo " + campo.campo + " alterado.";
  if (await gravar_campos(campos_novos, recado)) {
    document.querySelector("[data-janela-campo]").close();
  }
}

/**
 * "Tirar este campo": o primeiro clique pede confirmação; o segundo tira o campo da lista e grava na hora.
 *
 * Recebe: nada. Devolve: nada.
 */
async function tirar_campo() {
  const botao = document.querySelector("[data-tirar-campo]");
  if (botao.dataset.confirmar !== "sim") {
    botao.dataset.confirmar = "sim";
    botao.textContent = "Clique de novo para tirar";
    return;
  }
  const tirado = estado_dos_parametros.campo_em_edicao.campo;
  const campos_novos = [];
  for (const existente of estado_dos_parametros.campos) {
    if (existente.campo !== tirado) {
      campos_novos.push(existente);
    }
  }
  if (await gravar_campos(campos_novos, "Campo " + tirado + " tirado.")) {
    document.querySelector("[data-janela-campo]").close();
  }
}

/**
 * Pede ao servidor o layout vigente e o registro, e mostra.
 *
 * Recebe: nada. Devolve: nada.
 */
async function carregar_parametros() {
  try {
    const resposta = await fetch("/api/banco/parametros/layout");
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro("[data-erro-parametros]", typeof dados.detail === "string" ? dados.detail : "Não foi possível abrir os parâmetros.");
      // Sem os parâmetros: traço no lugar da versão de exemplo ("v1") e as tabelas saem da espera (vazias).
      liberar_parametros_sem_dado();
      return;
    }
    mostrar_parametros(dados);
    // Os parâmetros reais estão na tela: a versão e as tabelas saem da espera (js/carregando_dados.js).
    marcar_todos_como_carregados("[data-versao-vigente], [data-tabela-parametros], [data-tabela-registro]");
  } catch (erro) {
    mostrar_erro("[data-erro-parametros]", "Não foi possível falar com o servidor. Tente de novo em instantes.");
    // Servidor fora do ar: traço na versão e as tabelas saem da espera (vazias), nunca um exemplo.
    liberar_parametros_sem_dado();
  }
}

/**
 * O servidor não respondeu: a versão de exemplo ("v1") vira traço e as tabelas saem da espera, vazias.
 *
 * Recebe: nada. Devolve: nada. O recado de erro embaixo da lista diz o que aconteceu.
 */
function liberar_parametros_sem_dado() {
  // A versão vira "—" (se já mostrava a de verdade, fica como está).
  mostrar_dado_indisponivel(document.querySelector("[data-versao-vigente]"));
  // As duas tabelas aparecem vazias: só o cabeçalho, sem linha de exemplo.
  marcar_todos_como_carregados("[data-tabela-parametros], [data-tabela-registro]");
}

/**
 * Liga os botões da tela e busca os parâmetros. É chamada uma vez, quando a página termina de carregar.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_tela_de_parametros() {
  document.querySelector("[data-novo-campo]").addEventListener("click", function () {
    abrir_janela_do_campo(null);
  });
  document.querySelector("[data-salvar-campo]").addEventListener("click", salvar_campo);
  document.querySelector("[data-tirar-campo]").addEventListener("click", tirar_campo);
  // Trocou o tipo na janela: o mínimo e o máximo aparecem (tipo de valor) ou somem
  document.querySelector("[data-campo-tipo]").addEventListener("change", mostrar_faixa_conforme_o_tipo);
  document.querySelector("[data-cancelar-campo]").addEventListener("click", function () {
    document.querySelector("[data-janela-campo]").close();
  });
  document.querySelector("[data-busca-campo]").addEventListener("input", function (evento) {
    estado_dos_parametros.busca = evento.target.value;
    desenhar_campos();
  });
  carregar_parametros();
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_parametros);
