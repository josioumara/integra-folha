/*
  banco_faixas_cbo.js — a seção "Faixas salariais por profissão (CBO)" da página Parâmetros do Portal Interno (ADR-129).

  Para que serve: o especialista do banco consulta e edita a faixa de salário de cada profissão da tabela oficial (CBO).
  O Validador usa essa faixa para avisar a empresa quando um salário sai dela (o alerta nunca recusa o arquivo).
    - A busca procura por código ("4110" ou "4110-10") ou por palavras do título ("motor cam"); mostra 50 de cada vez,
      com "Mostrando 1–50 de 2.694" e o botão "Ver mais 50";
    - cada linha mostra o mínimo, o máximo e de onde a faixa veio (a RAIS, do Ministério do Trabalho, ou o banco);
    - "Editar" abre a janela: o mínimo e o máximo novos (o mínimo nunca maior que o máximo), a faixa calculada dos
      dados públicos (que continua guardada) e o registro das alterações; "Voltar ao calculado" desfaz a edição.
  Rotas: GET /api/banco/cbo?busca=, PUT /api/banco/cbo/{codigo}/faixa, POST /api/banco/cbo/{codigo}/faixa/voltar e
  GET /api/banco/cbo/{codigo}/alteracoes (api/rotas_faixas_cbo.py).
  Este arquivo não usa nada dos outros scripts da página: ele tem as próprias funções de apoio.
*/

// As profissões já mostradas da última busca, quantas batem com ela no total e a profissão aberta na janela
const estado_das_faixas = { faixas: [], total: 0, faixa_em_edicao: null };
// Espera depois da última tecla antes de buscar (não busca a cada letra)
const ESPERA_DA_BUSCA_EM_MS = 300;
// O relógio da espera da busca
let relogio_da_busca_cbo = null;
// De onde saiu a faixa calculada, em palavras
const NIVEL_EM_PALAVRAS = {
  OCUPACAO: "da profissão",
  FAMILIA: "da família da profissão (poucos vínculos na profissão)",
  SEM_DADOS: "sem dados suficientes",
};

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta; classe; texto. Devolve: o elemento.
 */
function criar_elemento_cbo(etiqueta, classe, texto) {
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
 * Um valor em reais no jeito brasileiro ("2500.5" → "R$ 2.500,50"); vazio → "—".
 *
 * Recebe: o valor como texto ou número. Devolve: o texto.
 */
function em_reais_cbo(valor) {
  if (valor === null || valor === undefined || valor === "") {
    return "—";
  }
  // O navegador separa "R$" do número com um espaço especial (que não quebra a linha): vira um espaço comum
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/\s/g, " ");
}

/**
 * Uma data e hora gravadas (ISO, UTC) no jeito brasileiro, no horário local ("29/09/2026, 14:05").
 *
 * Recebe: o texto ISO. Devolve: o texto.
 */
function data_e_hora_cbo(texto_iso) {
  if (!texto_iso) {
    return "";
  }
  return new Date(texto_iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/**
 * A mensagem de erro que o servidor mandou, ou uma frase de reserva.
 *
 * Recebe: os dados da resposta; a frase de reserva. Devolve: o texto.
 */
function mensagem_do_erro_cbo(dados, reserva) {
  if (dados && typeof dados.detail === "string") {
    return dados.detail;
  }
  return reserva;
}

/**
 * Mostra (ou esconde, com texto vazio) uma mensagem de erro.
 *
 * Recebe: o seletor do parágrafo de erro; o texto.
 */
function mostrar_erro_cbo(seletor, texto) {
  const paragrafo = document.querySelector(seletor);
  paragrafo.textContent = texto;
  paragrafo.hidden = !texto;
}

/**
 * De onde veio a faixa em uso, numa frase curta para a coluna "Origem".
 *
 * Recebe: a faixa. Devolve: o texto. Ex.: "RAIS 2025 - MTE, da profissão (1.234 vínculos)" ou
 * "Editada por especialista.banco em 29/09/2026, 14:05".
 */
function origem_da_faixa(faixa) {
  if (faixa.editado_por) {
    return "Editada por " + faixa.editado_por + " em " + data_e_hora_cbo(faixa.editado_em);
  }
  if (faixa.nivel === "SEM_DADOS") {
    return faixa.fonte + ": sem dados suficientes (não gera alerta)";
  }
  const vinculos = Number(faixa.vinculos_na_base).toLocaleString("pt-BR");
  return faixa.fonte + ", " + NIVEL_EM_PALAVRAS[faixa.nivel] + " (" + vinculos + " vínculos)";
}

/**
 * Desenha a tabela das profissões da última busca.
 */
function desenhar_faixas() {
  const corpo = document.querySelector("[data-corpo-faixas-cbo]");
  corpo.replaceChildren();
  for (const faixa of estado_das_faixas.faixas) {
    const linha = document.createElement("tr");
    linha.dataset.codigoCbo = faixa.codigo_cbo;
    linha.append(criar_elemento_cbo("td", "celula-nome-parametro", faixa.codigo_formatado));
    // O título e, quando a busca bateu num sinônimo, o sinônimo embaixo
    const celula_do_titulo = criar_elemento_cbo("td", "", faixa.titulo);
    if (faixa.sinonimo) {
      celula_do_titulo.append(criar_elemento_cbo("div", "nota-tabela", "Também chamada de: " + faixa.sinonimo));
    }
    linha.append(celula_do_titulo);
    linha.append(criar_elemento_cbo("td", "", em_reais_cbo(faixa.minimo)));
    linha.append(criar_elemento_cbo("td", "", em_reais_cbo(faixa.maximo)));
    linha.append(criar_elemento_cbo("td", "celula-motivo", origem_da_faixa(faixa)));
    const celula_da_acao = document.createElement("td");
    const botao = criar_elemento_cbo("button", "botao-descartar", "Editar");
    botao.type = "button";
    botao.addEventListener("click", function () {
      abrir_janela_da_faixa(faixa);
    });
    celula_da_acao.append(botao);
    linha.append(celula_da_acao);
    corpo.append(linha);
  }
  // Nenhuma profissão: a frase no lugar da tabela vazia
  document.querySelector("[data-sem-faixas-cbo]").hidden = estado_das_faixas.faixas.length > 0;
  mostrar_quantas_faltam();
}

/**
 * Mostra quantas profissões estão na tabela e quantas batem com a busca ("Mostrando 1–50 de 2.694 profissões"), e o
 * botão "Ver mais 50" enquanto faltar alguma.
 */
function mostrar_quantas_faltam() {
  const mostradas = estado_das_faixas.faixas.length;
  const total = estado_das_faixas.total;
  const frase = document.querySelector("[data-quantas-cbo]");
  frase.hidden = mostradas === 0;
  frase.textContent = "Mostrando 1–" + mostradas.toLocaleString("pt-BR") + " de " + total.toLocaleString("pt-BR")
    + " profissões. A busca acha qualquer uma pelo código ou pelo nome.";
  document.querySelector("[data-ver-mais-cbo]").hidden = mostradas >= total;
}

/**
 * Mostra, embaixo do título, como a faixa calculada foi feita (vem do servidor: base, quem entra, percentis, corte).
 *
 * Recebe: a medida ({base, quem_entra, valor, minimo, maximo, corte}).
 */
function mostrar_a_medida(medida) {
  const paragrafo = document.querySelector("[data-medida-cbo]");
  if (!medida || !medida.base) {
    paragrafo.hidden = true;
    return;
  }
  paragrafo.textContent = "Como a faixa é calculada: " + medida.base + "; " + medida.quem_entra + ". O mínimo é o "
    + medida.minimo + " e o máximo, o " + medida.maximo + " da " + medida.valor + ". " + medida.corte + ".";
  paragrafo.hidden = false;
}

/**
 * Busca as profissões no servidor e desenha a tabela.
 *
 * Recebe: mais — true no "Ver mais" (acrescenta as próximas 50 às que já estão); false numa busca nova (recomeça).
 */
async function buscar_faixas_cbo(mais) {
  const busca = document.querySelector("[data-busca-cbo]").value.trim();
  // Numa busca nova, começa da primeira; no "Ver mais", da próxima depois das que já aparecem
  let inicio = 0;
  if (mais === true) {
    inicio = estado_das_faixas.faixas.length;
  }
  mostrar_erro_cbo("[data-erro-faixas-cbo]", "");
  try {
    const resposta = await fetch("/api/banco/cbo?busca=" + encodeURIComponent(busca) + "&inicio=" + inicio);
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro_cbo("[data-erro-faixas-cbo]", mensagem_do_erro_cbo(dados, "Não foi possível buscar as profissões."));
      return;
    }
    // No "Ver mais", as novas entram depois das que já aparecem; numa busca nova, substituem
    if (mais === true) {
      estado_das_faixas.faixas = estado_das_faixas.faixas.concat(dados.faixas);
    } else {
      estado_das_faixas.faixas = dados.faixas;
    }
    estado_das_faixas.total = dados.total;
    mostrar_a_medida(dados.medida);
    desenhar_faixas();
  } catch (erro) {
    mostrar_erro_cbo("[data-erro-faixas-cbo]", "Sem conexão com o servidor. Tente de novo.");
  }
}

/**
 * Espera a pessoa parar de digitar e então busca.
 */
function buscar_depois_de_digitar() {
  clearTimeout(relogio_da_busca_cbo);
  relogio_da_busca_cbo = setTimeout(function () {
    buscar_faixas_cbo(false);
  }, ESPERA_DA_BUSCA_EM_MS);
}

/**
 * Abre a janela de edição de uma profissão, preenchida com a faixa em uso.
 *
 * Recebe: a faixa.
 */
function abrir_janela_da_faixa(faixa) {
  estado_das_faixas.faixa_em_edicao = faixa;
  document.querySelector("[data-titulo-janela-cbo]").textContent =
    "Faixa da profissão " + faixa.codigo_formatado + " (" + faixa.titulo + ")";
  document.querySelector("[data-minimo-cbo]").value = faixa.minimo || "";
  document.querySelector("[data-maximo-cbo]").value = faixa.maximo || "";
  // A faixa calculada, que continua guardada
  let calculada = "Calculada dos dados públicos: sem dados suficientes nesta profissão.";
  if (faixa.minimo_calculado) {
    calculada = "Calculada dos dados públicos (" + faixa.fonte + ", " + NIVEL_EM_PALAVRAS[faixa.nivel] + "): de "
      + em_reais_cbo(faixa.minimo_calculado) + " a " + em_reais_cbo(faixa.maximo_calculado) + ".";
  }
  document.querySelector("[data-calculada-cbo]").textContent = calculada;
  // "Voltar ao calculado" só aparece quando a faixa foi editada
  document.querySelector("[data-voltar-cbo]").hidden = !faixa.editado_por;
  mostrar_erro_cbo("[data-erro-janela-cbo]", "");
  carregar_alteracoes(faixa.codigo_cbo);
  document.querySelector("[data-janela-cbo]").showModal();
}

/**
 * Carrega e mostra o registro das alterações da profissão aberta.
 *
 * Recebe: o código da profissão.
 */
async function carregar_alteracoes(codigo) {
  const lista = document.querySelector("[data-alteracoes-cbo]");
  lista.replaceChildren();
  try {
    const resposta = await fetch("/api/banco/cbo/" + encodeURIComponent(codigo) + "/alteracoes");
    const dados = await resposta.json();
    if (!resposta.ok) {
      return;
    }
    for (const alteracao of dados.alteracoes) {
      let acao = "mudou de ";
      if (alteracao.acao === "VOLTOU_AO_CALCULADO") {
        acao = "voltou ao calculado, de ";
      }
      const texto = data_e_hora_cbo(alteracao.alterado_em) + ": " + alteracao.alterado_por + " " + acao
        + em_reais_cbo(alteracao.minimo_antes) + " a " + em_reais_cbo(alteracao.maximo_antes) + " para "
        + em_reais_cbo(alteracao.minimo_depois) + " a " + em_reais_cbo(alteracao.maximo_depois) + ".";
      lista.append(criar_elemento_cbo("li", "", texto));
    }
    if (dados.alteracoes.length === 0) {
      lista.append(criar_elemento_cbo("li", "", "Nenhuma alteração: a faixa é a calculada dos dados públicos."));
    }
  } catch (erro) {
    lista.append(criar_elemento_cbo("li", "", "Não foi possível carregar o registro das alterações."));
  }
}

/**
 * Grava na faixa em edição a resposta do servidor e redesenha a tabela.
 *
 * Recebe: a faixa como o servidor devolveu.
 */
function atualizar_faixa_na_tabela(faixa_nova) {
  const faixas = estado_das_faixas.faixas;
  for (let posicao = 0; posicao < faixas.length; posicao++) {
    if (faixas[posicao].codigo_cbo === faixa_nova.codigo_cbo) {
      // O sinônimo é da busca, e não da faixa: fica o que estava
      faixa_nova.sinonimo = faixas[posicao].sinonimo;
      faixas[posicao] = faixa_nova;
    }
  }
  desenhar_faixas();
}

/**
 * Mostra o aviso verde da seção por alguns segundos.
 *
 * Recebe: o texto.
 */
function mostrar_aviso_cbo(texto) {
  const aviso = document.querySelector("[data-aviso-cbo]");
  aviso.textContent = texto;
  aviso.hidden = false;
  setTimeout(function () {
    aviso.hidden = true;
  }, 5000);
}

/**
 * Manda ao servidor a mudança da faixa aberta (editar ou voltar ao calculado) e fecha a janela se deu certo.
 *
 * Recebe: o endereço; o método (PUT ou POST); o corpo (ou null); o aviso de sucesso.
 */
async function gravar_faixa(endereco, metodo, corpo, aviso) {
  mostrar_erro_cbo("[data-erro-janela-cbo]", "");
  const opcoes = { method: metodo, headers: { "Content-Type": "application/json" } };
  if (corpo) {
    opcoes.body = JSON.stringify(corpo);
  }
  try {
    const resposta = await fetch(endereco, opcoes);
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro_cbo("[data-erro-janela-cbo]", mensagem_do_erro_cbo(dados, "Confira os valores e tente de novo."));
      return;
    }
    atualizar_faixa_na_tabela(dados);
    document.querySelector("[data-janela-cbo]").close();
    mostrar_aviso_cbo(aviso + " " + dados.codigo_formatado + " (" + dados.titulo + ").");
  } catch (erro) {
    mostrar_erro_cbo("[data-erro-janela-cbo]", "Sem conexão com o servidor. Tente de novo.");
  }
}

/**
 * "Salvar": o mínimo e o máximo digitados. O servidor confere (o mínimo nunca maior que o máximo).
 */
function salvar_faixa() {
  const codigo = estado_das_faixas.faixa_em_edicao.codigo_cbo;
  const corpo = {
    minimo: document.querySelector("[data-minimo-cbo]").value.trim(),
    maximo: document.querySelector("[data-maximo-cbo]").value.trim(),
  };
  gravar_faixa("/api/banco/cbo/" + encodeURIComponent(codigo) + "/faixa", "PUT", corpo, "Faixa salva:");
}

/**
 * "Voltar ao calculado": a faixa em uso volta a ser a dos dados públicos.
 */
function voltar_faixa_ao_calculado() {
  const codigo = estado_das_faixas.faixa_em_edicao.codigo_cbo;
  gravar_faixa("/api/banco/cbo/" + encodeURIComponent(codigo) + "/faixa/voltar", "POST", null,
    "Faixa de volta à calculada:");
}

/**
 * Liga os botões e a busca, e faz a primeira busca (vazia: as primeiras profissões da tabela).
 */
function iniciar_faixas_cbo() {
  document.querySelector("[data-busca-cbo]").addEventListener("input", buscar_depois_de_digitar);
  document.querySelector("[data-salvar-cbo]").addEventListener("click", salvar_faixa);
  document.querySelector("[data-voltar-cbo]").addEventListener("click", voltar_faixa_ao_calculado);
  document.querySelector("[data-cancelar-cbo]").addEventListener("click", function () {
    document.querySelector("[data-janela-cbo]").close();
  });
  document.querySelector("[data-ver-mais-cbo]").addEventListener("click", function () {
    buscar_faixas_cbo(true);
  });
  buscar_faixas_cbo(false);
}

// Começa quando a página terminar de carregar (a seção fica antes dos outros scripts da página)
document.addEventListener("DOMContentLoaded", iniciar_faixas_cbo);
