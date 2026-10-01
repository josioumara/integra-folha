/*
  banco_planejamento.js — a parte do planejamento no Painel de acompanhamento (aba Indicadores do Portal Interno). O
  Simulador de Rentabilidade fica em js/simulador_de_rentabilidade.js, que usa as
  formatações e o pedido ao servidor daqui. A conversa com o Consultor saiu do sistema (ADR-144).

  Para que serve:
    1. mostra os números do planejamento, sem a base do banco: cada Cadastrado
       aguarda o retorno do banco até o arquivo de contas dizer o status; os números são Cadastrados, aguardando o
       retorno, contas novas (status 1) e correntistas (status 2, um grupo só desde o ADR-149: o arquivo não diz mais
       se a folha já era identificada nem se o correntista é ativo). O banco sempre informa o status; uma conta
       gravada sem ele (antes da coluna existir) conta como aguardando;
    1b. os números do painel seguem o filtro do alto (js/filtro_dos_indicadores.js):
       a empresa (nome ou CNPJ) e o estado, que aqui é a UF da unidade de trabalho de cada funcionário.

  Aberta como arquivo (o protótipo), os números vêm dos exemplos abaixo. Servida pela aplicação, tudo vem do
  servidor, e os exemplos nunca aparecem (js/carregando_dados.js): os números esperam com a barra cinza; se o servidor
  falhar, entra um traço ("—") e o aviso "Não foi possível carregar agora." nas tabelas. No painel, o planejamento
  divide a tela com o uso das empresas (js/banco_uso_real.js): cada bloco diz de quem é o dado
  (data-bloco-de="planejamento" ou "uso"), e este arquivo só libera os blocos do planejamento.
*/

// ===== 1. Dados de exemplo (só o protótipo, aberto como arquivo) =====

// Números agregados de cada empresa com cadastro aprovado (somam 1.840 Cadastrados); em_analise são os que a empresa
// enviou e o banco ainda avalia (a seção "Clientes que a empresa enviou" do simulador).
const NUMEROS_DAS_EMPRESAS = [
  { id: "aurora", em_analise: 12, nome: "Aurora Alimentos", uf: "SP", municipio: "Campinas", aguardando_retorno: 173, contas_abertas: 82, correntistas_marcados: 57 },
  { id: "horizonte", em_analise: 20, nome: "Horizonte Logística", uf: "MG", municipio: "Contagem", aguardando_retorno: 305, contas_abertas: 140, correntistas_marcados: 95 },
  { id: "brisa", em_analise: 5, nome: "Brisa Tecnologia", uf: "SC", municipio: "Florianópolis", aguardando_retorno: 62, contas_abertas: 36, correntistas_marcados: 30 },
  { id: "prisma", em_analise: 31, nome: "Prisma Comércio", uf: "PE", municipio: "Recife", aguardando_retorno: 491, contas_abertas: 220, correntistas_marcados: 149 },
];

// ===== 2. Filtros e somas (protótipo) =====

/**
 * As empresas de exemplo que passam na empresa e no estado pedidos (protótipo).
 *
 * Recebe: empresa_id (ou "" para todas); uf (ou "" para todos). Devolve: a lista das que passam.
 */
function empresas_de_exemplo_com(empresa_id, uf) {
  const escolhidas = [];
  for (const empresa of NUMEROS_DAS_EMPRESAS) {
    // Verdadeiro se a empresa passa em cada escolha (vazio deixa passar qualquer uma).
    const passa_na_empresa = !empresa_id || empresa.id === empresa_id;
    const passa_na_uf = !uf || empresa.uf === uf;
    if (passa_na_empresa && passa_na_uf) {
      escolhidas.push(empresa);
    }
  }
  return escolhidas;
}

/**
 * As empresas do painel no protótipo: as do filtro do alto.
 *
 * Recebe: nada. Devolve: a lista.
 */
function empresas_filtradas() {
  return empresas_de_exemplo_com(filtro_dos_indicadores.empresa_id, filtro_dos_indicadores.uf);
}

/**
 * Soma os números de uma lista de empresas, no mesmo formato do resumo que o servidor manda.
 *
 * Recebe: empresas. Devolve: { empresas, cadastrados, aguardando_retorno, contas_abertas, correntistas_marcados }.
 */
function somar(empresas) {
  // Tudo começa do zero.
  const soma = { empresas: 0, cadastrados: 0, aguardando_retorno: 0, contas_abertas: 0, correntistas_marcados: 0 };
  // Os campos que se somam direto, empresa por empresa
  const campos_somados = ["aguardando_retorno", "contas_abertas", "correntistas_marcados"];
  for (const empresa of empresas) {
    soma.empresas = soma.empresas + 1;
    for (const campo of campos_somados) {
      soma[campo] = soma[campo] + empresa[campo];
    }
  }
  // Cadastrados = cada pessoa está em uma situação só.
  soma.cadastrados = soma.aguardando_retorno + soma.contas_abertas + soma.correntistas_marcados;
  return soma;
}

// ===== 3. Formatação =====

/**
 * Formata um número inteiro no jeito brasileiro. Exemplo: 1840 → "1.840".
 *
 * Recebe: numero. Devolve: o texto.
 */
function formatar_numero(numero) {
  return numero.toLocaleString("pt-BR");
}

/**
 * Formata um valor em reais. Exemplo: 175244.36 (ou o texto "175244.36") → "R$ 175.244,36".
 *
 * Recebe: valor (número ou texto com ponto nos centavos). Devolve: o texto.
 */
function formatar_reais(valor) {
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Formata uma porcentagem. Exemplo: "35.50" → "35,5%".
 *
 * Recebe: valor (número ou texto). Devolve: o texto.
 */
function formatar_porcentagem(valor) {
  return Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + "%";
}

/**
 * O momento gravado (UTC, "2026-09-28T17:40:00+00:00") na data e hora daqui ("28/09/2026 14:40").
 *
 * Recebe: momento. Devolve: o texto.
 */
function formatar_data_e_hora(momento) {
  const data = new Date(momento);
  return data.toLocaleDateString("pt-BR") + " " + data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Diz se uma premissa está sem valor (null do servidor, ou campo vazio).
 *
 * Recebe: valor. Devolve: true se não há valor.
 */
function sem_valor(valor) {
  return valor === null || valor === undefined || String(valor).trim() === "";
}

/**
 * O valor de uma premissa global (o horizonte ou um MOB) como aparece na tela.
 *
 * Recebe: nome — ex.: "mob_cliente_folha"; valor. Devolve: ex.: "R$ 2.090,62" ou "12 meses" (e "1 mês").
 */
function texto_da_premissa(nome, valor) {
  if (nome === "horizonte_meses") {
    // Singular e plural
    if (Number(valor) === 1) {
      return "1 mês";
    }
    return valor + " meses";
  }
  return formatar_reais(valor);
}

/**
 * Põe uma frase no singular ou no plural, conforme a quantidade.
 *
 * Recebe: quantidade; singular; plural. Devolve: ex.: "1 premissa mudada" ou "2 premissas mudadas".
 */
function no_singular_ou_plural(quantidade, singular, plural) {
  if (quantidade === 1) {
    return quantidade + " " + singular;
  }
  return quantidade + " " + plural;
}

/**
 * Cria uma linha de tabela com os valores dados.
 *
 * Recebe: valores — lista de textos. Devolve: o <tr>.
 */
function criar_linha(valores) {
  const linha = document.createElement("tr");
  // Uma célula por valor (texto puro, nunca HTML).
  for (const valor of valores) {
    const celula = document.createElement("td");
    celula.textContent = valor;
    linha.append(celula);
  }
  return linha;
}

// ===== 4. Os números do planejamento =====

/**
 * Mostra os números de cima do planejamento: cada elemento [data-numero] do bloco recebe o número do resumo com o
 * mesmo nome.
 *
 * Recebe: resumo — as contagens (cadastrados, aguardando_retorno, contas_abertas, correntistas_marcados); empresas —
 * quantas empresas entram. Devolve: nada.
 * Um número que o resumo não tem mais (ex.: o falso não folha, que saiu com o ADR-149) recebe um traço: nunca fica
 * com o número de exemplo do protótipo.
 */
function mostrar_numeros(resumo, empresas) {
  for (const elemento of document.querySelectorAll("[data-bloco-de='planejamento'] [data-numero]")) {
    const nome = elemento.dataset.numero;
    // Quantas empresas entram vem à parte; o resto, do resumo
    let valor = resumo[nome];
    if (nome === "empresas") {
      valor = empresas;
    }
    // Sem esse número no resumo: um traço
    if (valor === undefined || valor === null) {
      elemento.textContent = "—";
    } else {
      elemento.textContent = formatar_numero(valor);
    }
  }
}

/**
 * Preenche as tabelas "Potencial por empresa" e "Potencial por região".
 *
 * Recebe: por_empresa — [{empresa, cadastrados, aguardando_retorno, contas_abertas, correntistas_marcados}];
 * por_regiao — [{uf, municipio, ...as mesmas contagens}]. Devolve: nada.
 */
function mostrar_tabelas(por_empresa, por_regiao) {
  const corpo_por_empresa = document.querySelector("[data-corpo-por-empresa]");
  corpo_por_empresa.replaceChildren();
  for (const linha of por_empresa) {
    corpo_por_empresa.append(criar_linha([linha.empresa, formatar_numero(linha.cadastrados),
      formatar_numero(linha.aguardando_retorno), formatar_numero(linha.contas_abertas),
      formatar_numero(linha.correntistas_marcados)]));
  }
  const corpo_por_regiao = document.querySelector("[data-corpo-por-regiao]");
  corpo_por_regiao.replaceChildren();
  for (const linha of por_regiao) {
    corpo_por_regiao.append(criar_linha([linha.uf + " · " + linha.municipio, formatar_numero(linha.cadastrados),
      formatar_numero(linha.aguardando_retorno), formatar_numero(linha.contas_abertas),
      formatar_numero(linha.correntistas_marcados)]));
  }
}

/**
 * As linhas das tabelas no protótipo: uma por empresa (cada empresa de exemplo tem uma unidade só).
 *
 * Recebe: empresas. Devolve: { por_empresa, por_regiao }, no formato do servidor.
 */
function tabelas_do_exemplo(empresas) {
  const por_empresa = [];
  const por_regiao = [];
  for (const empresa of empresas) {
    // A soma de uma empresa só, no formato do resumo
    const soma = somar([empresa]);
    por_empresa.push({ empresa: empresa.nome, cadastrados: soma.cadastrados, aguardando_retorno: soma.aguardando_retorno,
      contas_abertas: soma.contas_abertas, correntistas_marcados: soma.correntistas_marcados });
    por_regiao.push({ uf: empresa.uf, municipio: empresa.municipio, cadastrados: soma.cadastrados,
      aguardando_retorno: soma.aguardando_retorno, contas_abertas: soma.contas_abertas,
      correntistas_marcados: soma.correntistas_marcados });
  }
  return { por_empresa: por_empresa, por_regiao: por_regiao };
}

// ===== 5. Recados =====

/**
 * Mostra (ou esconde) um recado de erro.
 *
 * Recebe: seletor — onde; texto (ou vazio, para esconder). Devolve: nada.
 */
function mostrar_recado(seletor, texto) {
  const recado = document.querySelector(seletor);
  recado.hidden = !texto;
  recado.textContent = texto || "";
}

// ===== 7. A tela inteira =====

/**
 * Recalcula e redesenha os números e as tabelas do painel conforme o filtro do alto.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_planejamento() {
  // O servidor não respondeu ao abrir: a tela fica com os traços e os avisos (nunca volta ao exemplo).
  if (servidor_indisponivel) {
    return;
  }
  // Com a página ligada à aplicação, os números vêm do servidor.
  if (usando_a_api) {
    atualizar_com_a_api();
    return;
  }
  // Protótipo: as empresas escolhidas e a soma delas
  const empresas = empresas_filtradas();
  const soma = somar(empresas);
  mostrar_numeros(soma, soma.empresas);
  const tabelas = tabelas_do_exemplo(empresas);
  mostrar_tabelas(tabelas.por_empresa, tabelas.por_regiao);
}

// ===== 8. Dados de verdade (API, ADR-69) =====

// Verdadeiro quando a página está ligada à aplicação e os números vêm do servidor (e não dos exemplos acima).
let usando_a_api = false;

// Verdadeiro quando a página é servida pela aplicação, mas o servidor não respondeu ao abrir: sem exemplo nenhum.
let servidor_indisponivel = false;

// O aviso que entra nas tabelas e na lista quando o servidor não respondeu (nunca o exemplo).
const AVISO_DE_FALHA_NO_PLANEJAMENTO = "Não foi possível carregar agora.";

// Os números e textos da parte de cima e das tabelas que esperam o servidor.
const SELETOR_DOS_NUMEROS_E_TABELAS = "[data-bloco-de='planejamento'] [data-numero][data-aguarda-dado], " +
  "[data-tabela-por-empresa], [data-tabela-por-regiao]";

// As colunas das tabelas do planejamento (para o recado ocupar a linha inteira).
const COLUNAS_DAS_TABELAS = 5;

/**
 * Põe uma linha só numa tabela, com um recado ocupando todas as colunas.
 *
 * Recebe: seletor — o corpo da tabela; recado — o texto. Devolve: nada.
 */
function mostrar_recado_na_tabela_do_planejamento(seletor, recado) {
  const linha = document.createElement("tr");
  const celula = document.createElement("td");
  celula.colSpan = COLUNAS_DAS_TABELAS;
  celula.textContent = recado;
  linha.append(celula);
  document.querySelector(seletor).replaceChildren(linha);
}

/**
 * O servidor não respondeu: traço nos números, aviso nas tabelas, nunca o exemplo.
 *
 * Recebe: nada. Devolve: nada. O que já mostra um dado de verdade continua como está.
 */
function mostrar_planejamento_indisponivel() {
  for (const elemento of document.querySelectorAll("[data-bloco-de='planejamento'] [data-numero]")) {
    mostrar_dado_indisponivel(elemento);
  }
  // As tabelas: o aviso, só quando ainda estavam esperando
  if (!document.querySelector("[data-tabela-por-empresa]").hasAttribute("data-dado-pronto")) {
    mostrar_recado_na_tabela_do_planejamento("[data-corpo-por-empresa]", AVISO_DE_FALHA_NO_PLANEJAMENTO);
    mostrar_recado_na_tabela_do_planejamento("[data-corpo-por-regiao]", AVISO_DE_FALHA_NO_PLANEJAMENTO);
  }
  marcar_todos_como_carregados("[data-tabela-por-empresa], [data-tabela-por-regiao]");
}

/**
 * Os filtros do painel no formato da API, pelo filtro do alto ("" = todos). A data de referência não é escolhida.
 *
 * Recebe: nada. Devolve: { empresa_id, uf, data_referencia }.
 */
function filtros_da_tela() {
  return { empresa_id: filtro_dos_indicadores.empresa_id, uf: filtro_dos_indicadores.uf, data_referencia: "" };
}

/**
 * Pede algo à API e devolve { ok, dados }. Nunca quebra: sem servidor, ok falso com a mensagem.
 *
 * Recebe: endereco; opcoes (do fetch). Devolve: { ok, dados }.
 */
async function pedir_ao_servidor(endereco, opcoes) {
  try {
    const resposta = await fetch(endereco, opcoes);
    return { ok: resposta.ok, dados: await resposta.json() };
  } catch (erro) {
    return { ok: false, dados: { detail: "Não foi possível falar com o servidor." } };
  }
}

/**
 * Busca os estados das unidades na API e liga a tela aos dados de verdade. Aberta como arquivo, nada muda.
 *
 * Recebe: nada. Devolve: nada.
 */
async function ligar_a_api() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  usando_a_api = true;
  const resposta = await pedir_ao_servidor("/api/banco/planejamento/filtros");
  // Sem os filtros, a tela não liga: traços e avisos.
  if (!resposta.ok) {
    servidor_indisponivel = true;
    mostrar_planejamento_indisponivel();
    return;
  }
  // Os estados das unidades de trabalho entram no filtro do alto (as empresas chegam pelo uso, com os CNPJs)
  acrescentar_estados_ao_filtro(resposta.dados.ufs);
  atualizar_planejamento();
}

/**
 * Busca os números com o filtro do alto e desenha números e tabelas.
 *
 * Recebe: nada. Devolve: nada.
 */
async function atualizar_com_a_api() {
  const endereco = "/api/banco/planejamento?" + new URLSearchParams(filtros_da_tela()).toString();
  const resposta = await pedir_ao_servidor(endereco);
  // Sem os números: traço no que ainda esperava (o que já tinha dado de verdade fica).
  if (!resposta.ok) {
    mostrar_planejamento_indisponivel();
    return;
  }
  mostrar_numeros(resposta.dados.resumo, resposta.dados.indicadores.empresas_integradas);
  mostrar_tabelas(resposta.dados.por_empresa, resposta.dados.por_regiao);
  // Os números reais estão na tela: saem da espera.
  marcar_todos_como_carregados(SELETOR_DOS_NUMEROS_E_TABELAS);
}

// ===== 9. Preparação =====

/**
 * Liga o filtro do alto e desenha a parte do planejamento no painel.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_tela_de_planejamento() {
  // O filtro do alto mudou: os números e as tabelas do painel se refazem.
  document.addEventListener("filtro-dos-indicadores-mudou", atualizar_planejamento);
  // Com servidor: liga aos dados de verdade. Aberta como arquivo: desenha o exemplo.
  if (window.location.protocol.startsWith("http")) {
    ligar_a_api();
    return;
  }
  atualizar_planejamento();
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_planejamento);
