/*
  simulador_de_rentabilidade.js — a guia "Simulador de Rentabilidade" da aba Indicadores do Portal Interno.

  Para que serve: simular quanto uma empresa (ou a
  carteira toda) pode render, em seções:
    1. a empresa da simulação (nome ou CNPJ; vazio = todas), com js/escolha_de_empresa.js;
    2. as premissas globais oficiais (horizonte e os 3 MOB), TRAVADAS: só mudam em Configuração › Premissas
       financeiras;
    3. o ajuste dessas premissas SÓ nesta simulação (campo vazio = vale a oficial);
    4. os clientes que a empresa enviou (cadastrados + em análise pelo banco), TRAVADOS;
    5. a estimativa de clientes da especialista, que SUBSTITUI os enviados quando preenchida;
    6. as quatro taxas estimadas: % novas contas, % correntista (não folha), % correntista (folha) e %
       ativos entre os correntistas (sem valor oficial nem padrão: sem uma delas, a simulação espera; ADR-26);
    7. o resultado, refeito a cada ajuste, com a MESMA conta da aplicação (services/planejamento.py,
       simular_rentabilidade):
         novas contas           = base × % novas contas × MOB cliente novo
         não folha ativos       = base × % não folha × % ativos × (MOB folha − MOB não folha)
         o resto                = sem rentabilidade nova (o inativo, o folha, que já traz o MOB maior, e quem não
                                  abre conta)
    8. o que o retorno do banco já confirmou, como REFERÊNCIA (travado), com as taxas observadas.
  Os campos que dependem da especialista têm a cor de destaque (css/banco_indicadores.css, .campo-do-especialista),
  e a taxa que falta ganha o aviso "Falta informar". "Salvar esta simulação" pede um nome e guarda a empresa, os
  valores, a base e o resultado; "Visualizar" abre uma janela com a simulação salva detalhada e
  "Reabrir" põe tudo de volta no simulador.

  Aberta como arquivo (o protótipo), os números vêm dos exemplos de js/banco_planejamento.js e a conta é feita aqui.
  Servida pela aplicação, tudo vem do servidor:
    - GET /api/banco/premissas: as premissas oficiais (a seção travada);
    - GET /api/banco/planejamento/base: os clientes que a empresa enviou (conta que custa: uma vez por empresa);
    - POST /api/banco/planejamento/ganho: a conta, sem gravar nada (a cada ajuste, meio segundo depois da digitação);
    - GET e POST /api/banco/planejamento/simulacoes: as simulações salvas.
  Os exemplos nunca aparecem com o servidor (js/carregando_dados.js): os números esperam com a barra cinza e, se o
  servidor falhar, entra um traço ("—"). Usa as formatações e o pedido ao servidor de js/banco_planejamento.js.
*/

// ===== 1. Constantes =====

// As premissas globais (as oficiais, que a especialista pode trocar só na simulação), na ordem da tela.
const PREMISSAS_GLOBAIS = ["horizonte_meses", "mob_cliente_folha", "mob_cliente_nao_folha",
  "mob_cliente_novo_conquistado"];

// As três taxas estimadas pela especialista (de 0 a 100), sem valor oficial.
const TAXAS_DO_SIMULADOR = ["percentual_novas_contas", "percentual_nao_folha", "percentual_folha",
  "percentual_ativos"];

// As taxas que dividem a mesma base de clientes (juntas, até 100%).
const TAXAS_QUE_DIVIDEM_A_BASE = ["percentual_novas_contas", "percentual_nao_folha", "percentual_folha"];

// Todos os campos do simulador, com o nome que aparece para a pessoa (os mesmos do servidor).
const TITULOS_DO_SIMULADOR = {
  horizonte_meses: "Horizonte da projeção",
  mob_cliente_folha: "MOB cliente folha",
  mob_cliente_nao_folha: "MOB cliente não folha",
  mob_cliente_novo_conquistado: "MOB cliente novo conquistado",
  percentual_novas_contas: "% novas contas",
  percentual_nao_folha: "% correntista (não folha)",
  percentual_folha: "% correntista (folha)",
  percentual_ativos: "% ativos entre os correntistas",
  clientes_estimados: "Clientes (sua estimativa)",
};

// As premissas oficiais de exemplo (só o protótipo): a v1 do business case (data/parametros/premissas_v1.json).
const PREMISSAS_OFICIAIS_DE_EXEMPLO = {
  versao: "v1",
  valores: { horizonte_meses: 12, mob_cliente_folha: "2090.62", mob_cliente_nao_folha: "1724.00",
    mob_cliente_novo_conquistado: "2090.62" },
};

// O maior número de clientes que uma simulação aceita (o mesmo do servidor: 10 milhões).
const MAXIMO_DE_CLIENTES = 10000000;

// Quanto o simulador espera a pessoa parar de digitar antes de refazer a conta (meio segundo, em milissegundos).
const ESPERA_DA_DIGITACAO = 500;

// O estado do simulador: as premissas oficiais ({versao, valores}), os clientes que a empresa enviou, a empresa da
// simulação ("" = todas), a espera da digitação, o número do último pedido da base (para ignorar resposta atrasada de
// uma empresa que já não está escolhida) e, só no protótipo, as simulações salvas nesta aba.
const estado_do_simulador = { oficiais: null, base_da_empresa: null, empresa_id: "", espera: null,
  pedido_da_base: 0, salvas_no_exemplo: [], simulacao_na_janela: null };

// ===== 2. Os campos =====

/**
 * Diz se a página está ligada à aplicação (servida por http) ou aberta como arquivo (o protótipo).
 *
 * Recebe: nada. Devolve: true com o servidor.
 */
function simulador_com_servidor() {
  return window.location.protocol.startsWith("http");
}

/**
 * O campo de um valor do simulador.
 *
 * Recebe: nome — ex.: "percentual_novas_contas". Devolve: o <input>.
 */
function campo_do_simulador(nome) {
  return document.querySelector("[data-premissa-simulador='" + nome + "']");
}

/**
 * Os valores que estão nos campos, como texto sem espaços nas pontas ("" = vazio).
 *
 * Recebe: nada. Devolve: { horizonte_meses: "", mob_cliente_folha: "2200", ..., clientes_estimados: "1200" }.
 */
function valores_digitados() {
  const valores = {};
  for (const nome of Object.keys(TITULOS_DO_SIMULADOR)) {
    valores[nome] = campo_do_simulador(nome).value.trim();
  }
  return valores;
}

/**
 * Os valores no formato do servidor: a premissa global vazia não vai (vale a oficial); as taxas e a estimativa vão
 * mesmo vazias (vazio = sem valor).
 *
 * Recebe: valores (de valores_digitados). Devolve: o dicionário para o pedido.
 */
function valores_para_o_servidor(valores) {
  const enviados = {};
  for (const nome of Object.keys(valores)) {
    // Premissa global vazia: o servidor usa a oficial
    if (PREMISSAS_GLOBAIS.includes(nome) && valores[nome] === "") {
      continue;
    }
    enviados[nome] = valores[nome];
  }
  return enviados;
}

/**
 * Os valores que a conta usa: a premissa global vazia vira a oficial (no protótipo; com o servidor, ele faz isso).
 *
 * Recebe: valores (de valores_digitados). Devolve: os mesmos, com as globais preenchidas.
 */
function valores_com_as_oficiais(valores) {
  const usados = Object.assign({}, valores);
  for (const nome of PREMISSAS_GLOBAIS) {
    if (usados[nome] === "") {
      usados[nome] = String(estado_do_simulador.oficiais.valores[nome]);
    }
  }
  return usados;
}

/**
 * Põe nos campos os valores de uma simulação salva: a premissa global igual à oficial fica vazia (vale a oficial).
 *
 * Recebe: valores — { horizonte_meses, ..., clientes_estimados } (null ou ausente = vazio). Devolve: nada.
 */
function preencher_campos(valores) {
  for (const nome of Object.keys(TITULOS_DO_SIMULADOR)) {
    let valor_do_campo = "";
    if (!sem_valor(valores[nome])) {
      valor_do_campo = String(valores[nome]);
    }
    // A premissa global igual à oficial não precisa ficar no campo de ajuste
    if (PREMISSAS_GLOBAIS.includes(nome) && igual_a_oficial(nome, valor_do_campo)) {
      valor_do_campo = "";
    }
    campo_do_simulador(nome).value = valor_do_campo;
  }
  marcar_o_que_falta();
}

/**
 * Diz se um valor é igual ao oficial daquela premissa (números comparados pelo valor: "1724" = "1724.00").
 *
 * Recebe: nome; valor (texto). Devolve: true se é igual (ou se ainda não há oficiais).
 */
function igual_a_oficial(nome, valor) {
  if (estado_do_simulador.oficiais === null || valor === "") {
    return valor === "";
  }
  return Number(estado_do_simulador.oficiais.valores[nome]) === Number(valor);
}

/**
 * Marca as taxas vazias com o aviso "Falta informar" (a classe vai no rótulo do campo; o texto vem do CSS).
 *
 * Recebe: nada. Devolve: nada.
 */
function marcar_o_que_falta() {
  for (const nome of TAXAS_DO_SIMULADOR) {
    const campo = campo_do_simulador(nome);
    campo.closest(".campo").classList.toggle("campo-falta-informar", campo.value.trim() === "");
  }
}

// ===== 3. As seções travadas: premissas oficiais, clientes enviados e o que o banco confirmou =====

/**
 * Mostra as premissas oficiais na seção travada e a versão delas.
 *
 * Recebe: oficiais — { versao: "v1", valores: { horizonte_meses, os 3 MOB } }. Devolve: nada.
 */
function mostrar_premissas_oficiais(oficiais) {
  for (const nome of PREMISSAS_GLOBAIS) {
    const rotulo = document.querySelector("[data-oficial-de='" + nome + "']");
    rotulo.textContent = texto_da_premissa(nome, oficiais.valores[nome]);
    marcar_como_carregado(rotulo);
  }
  const versao = document.querySelector("[data-versao-oficial]");
  versao.textContent = "oficiais " + oficiais.versao;
  marcar_como_carregado(versao);
  // Os placeholders dos campos de ajuste mostram a oficial ("oficial: R$ 2.090,62")
  for (const nome of PREMISSAS_GLOBAIS) {
    campo_do_simulador(nome).placeholder = "oficial: " + texto_da_premissa(nome, oficiais.valores[nome]);
  }
}

/**
 * Mostra os clientes que a empresa enviou (cadastrados, em análise e o total, que é a base sem estimativa).
 *
 * Recebe: base — { cadastrados, em_analise, enviados }. Devolve: nada.
 */
function mostrar_base_da_empresa(base) {
  for (const nome of ["cadastrados", "em_analise", "enviados"]) {
    const numero = document.querySelector("[data-base-empresa='" + nome + "']");
    numero.textContent = formatar_numero(base[nome]);
    marcar_como_carregado(numero);
  }
}

/**
 * Formata uma taxa observada (texto do servidor, ex.: "32.8") como porcentagem, ou "—" sem retorno do banco.
 *
 * Recebe: taxa (texto ou null). Devolve: ex.: "32,8%" ou "—".
 */
function texto_da_taxa_observada(taxa) {
  if (sem_valor(taxa)) {
    return "—";
  }
  return formatar_porcentagem(taxa);
}

/**
 * Mostra o que o retorno do banco já confirmou (referência travada), com as taxas observadas e o realizado.
 *
 * Recebe: confirmado — { com_retorno, contas_abertas, falso_nao_folha, ja_eram_folha, taxas_observadas (novas_contas,
 * nao_folha, folha e ativos):
 * {novas_contas, nao_folha}, realizado: {total} }. Devolve: nada.
 */
function mostrar_confirmado(confirmado) {
  const textos = {
    com_retorno: formatar_numero(confirmado.com_retorno),
    contas_abertas: formatar_numero(confirmado.contas_abertas),
    falso_nao_folha: formatar_numero(confirmado.falso_nao_folha),
    ja_eram_folha: formatar_numero(confirmado.ja_eram_folha),
    taxa_novas_contas: texto_da_taxa_observada(confirmado.taxas_observadas.novas_contas),
    taxa_nao_folha: texto_da_taxa_observada(confirmado.taxas_observadas.nao_folha),
    taxa_folha: texto_da_taxa_observada(confirmado.taxas_observadas.folha),
    taxa_ativos: texto_da_taxa_observada(confirmado.taxas_observadas.ativos),
    realizado: formatar_reais(confirmado.realizado.total),
  };
  for (const nome of Object.keys(textos)) {
    const numero = document.querySelector("[data-confirmado-de='" + nome + "']");
    numero.textContent = textos[nome];
    marcar_como_carregado(numero);
  }
  // Sem nenhum retorno ainda, a nota diz por que as taxas observadas estão vazias
  let nota = "As taxas observadas são de quem já teve o retorno do banco: servem de referência para as suas.";
  if (confirmado.com_retorno === 0) {
    nota = "O banco ainda não devolveu o arquivo de contas desta base: ainda não há taxa observada.";
  }
  document.querySelector("[data-nota-confirmado]").textContent = nota;
}

// ===== 4. O resultado =====

/**
 * Formata uma quantidade estimada de clientes (texto do servidor, ex.: "93.6"), com uma casa. Ex.: "93,6".
 *
 * Recebe: pessoas (texto ou número). Devolve: o texto.
 */
function clientes_estimados_em_texto(pessoas) {
  return Number(pessoas).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/**
 * Desenha a tabela do resultado: uma linha por grupo de clientes (os que não rendem ficam em cinza).
 *
 * Recebe: linhas — [{ grupo, pessoas, conta, ganho, rende }] (vazia quando falta taxa). Devolve: nada.
 */
function mostrar_linhas_do_resultado(linhas) {
  const corpo = document.querySelector("[data-corpo-aberturas]");
  corpo.replaceChildren();
  // Sem as taxas: uma linha só, explicando
  if (linhas.length === 0) {
    const linha = criar_linha(["Informe as três taxas para ver a rentabilidade por grupo.", "", "", ""]);
    corpo.append(linha);
  }
  for (const grupo of linhas) {
    const linha = criar_linha([grupo.grupo, clientes_estimados_em_texto(grupo.pessoas), grupo.conta,
      formatar_reais(grupo.ganho)]);
    linha.dataset.abertura = grupo.grupo;
    // O grupo que não traz rentabilidade nova fica em cinza
    if (!grupo.rende) {
      linha.classList.add("linha-sem-rentabilidade");
    }
    corpo.append(linha);
  }
  marcar_como_carregado(document.querySelector("[data-tabela-aberturas]"));
}

/**
 * Quantos clientes trazem rentabilidade nova: a soma das linhas que rendem.
 *
 * Recebe: linhas (do resultado). Devolve: o número (pode ter casa decimal, é estimativa).
 */
function clientes_que_rendem(linhas) {
  let soma = 0;
  for (const grupo of linhas) {
    if (grupo.rende) {
      soma = soma + Number(grupo.pessoas);
    }
  }
  return soma;
}

/**
 * Mostra o resultado inteiro: a base usada, quantos rendem, o total, a tabela, o selo das premissas e a referência.
 *
 * Recebe: dados — { valores, alteradas, versao_premissas, base: {clientes, origem}, simulacao: {linhas, total,
 * falta}, confirmado } (o formato do servidor). Devolve: nada.
 */
function mostrar_resultado_do_simulador(dados) {
  const simulacao = dados.simulacao;
  // A base: os clientes que a empresa enviou ou a estimativa da especialista
  document.querySelector("[data-ganho='clientes']").textContent = formatar_numero(dados.base.clientes);
  let legenda_da_base = "clientes na base (os que a empresa enviou)";
  if (dados.base.origem === "estimativa") {
    legenda_da_base = "clientes na base (a sua estimativa)";
  }
  document.querySelector("[data-ganho-legenda-base]").textContent = legenda_da_base;
  // Quantos rendem e o total: "—" enquanto falta uma taxa
  const falta_taxa = simulacao.total === null;
  let texto_dos_que_rendem = "—";
  let texto_do_total = "—";
  if (!falta_taxa) {
    texto_dos_que_rendem = clientes_estimados_em_texto(clientes_que_rendem(simulacao.linhas));
    texto_do_total = formatar_reais(simulacao.total);
  }
  document.querySelector("[data-ganho='rendem']").textContent = texto_dos_que_rendem;
  document.querySelector("[data-ganho='total']").textContent = texto_do_total;
  document.querySelector("[data-ganho-legenda-total]").textContent = "rentabilidade em " +
    texto_da_premissa("horizonte_meses", dados.valores.horizonte_meses);
  // O aviso do que falta (nada é suposto)
  const aviso = document.querySelector("[data-falta-simulacao]");
  aviso.hidden = !falta_taxa;
  if (falta_taxa) {
    aviso.textContent = "Para simular, informe: " + simulacao.falta.join(", ") + ". O sistema não supõe esses valores.";
  }
  mostrar_linhas_do_resultado(simulacao.linhas);
  // O selo: as oficiais (com a versão) ou a simulação, com quantas premissas globais foram mudadas
  const selo = document.querySelector("[data-origem-premissas]");
  if (dados.alteradas.length === 0) {
    selo.textContent = "Premissas oficiais " + dados.versao_premissas;
  } else {
    selo.textContent = "Simulação: " + no_singular_ou_plural(dados.alteradas.length, "premissa mudada",
      "premissas mudadas");
  }
  mostrar_confirmado(dados.confirmado);
  // O resultado está na tela: sai da espera (js/carregando_dados.js)
  marcar_todos_como_carregados("[data-ganho], [data-origem-premissas]");
}

/**
 * O servidor não respondeu: traço no que ainda esperava (o que já mostra um dado de verdade fica como está).
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_simulador_indisponivel() {
  const seletor = "[data-simulador] [data-aguarda-dado]";
  for (const elemento of document.querySelectorAll(seletor)) {
    mostrar_dado_indisponivel(elemento);
  }
  // A tabela: sem as linhas de exemplo, só quando ainda não tinha dado de verdade
  const tabela = document.querySelector("[data-tabela-aberturas]");
  if (!tabela.hasAttribute("data-dado-pronto")) {
    document.querySelector("[data-corpo-aberturas]").replaceChildren();
    marcar_como_carregado(tabela);
  }
}

// ===== 5. A conta no protótipo (a MESMA do servidor) =====

/**
 * Arredonda para centavos (evita "0,30000000004" das contas com vírgula do computador).
 *
 * Recebe: valor. Devolve: o valor com 2 casas.
 */
function em_centavos_no_simulador(valor) {
  return Math.round(valor * 100) / 100;
}

/**
 * Uma linha do resultado no protótipo, no formato do servidor.
 *
 * Recebe: grupo; pessoas (número); conta (texto); ganho (número); rende (true/false). Devolve: a linha.
 */
function linha_no_exemplo(grupo, pessoas, conta, ganho, rende) {
  return { grupo: grupo, pessoas: pessoas.toFixed(1), conta: conta, ganho: String(em_centavos_no_simulador(ganho)),
    rende: rende };
}

/**
 * A simulação no protótipo, com a MESMA conta de services/planejamento.py (simular_rentabilidade).
 *
 * Recebe: clientes (a base); valores (os usados, com as globais preenchidas). Devolve: { clientes, linhas, total,
 * falta }. Ex.: 312 clientes, 30%, 40%, 20% e 75% ativos → 93,6 × 2.090,62 + 93,6 × 366,62.
 */
function simular_no_exemplo(clientes, valores) {
  const falta = [];
  for (const nome of TAXAS_DO_SIMULADOR) {
    if (sem_valor(valores[nome])) {
      falta.push(TITULOS_DO_SIMULADOR[nome]);
    }
  }
  if (falta.length > 0) {
    return { clientes: clientes, linhas: [], total: null, falta: falta };
  }
  const diferenca_de_mob = Number(valores.mob_cliente_folha) - Number(valores.mob_cliente_nao_folha);
  const mob_novo = Number(valores.mob_cliente_novo_conquistado);
  const novas_contas = clientes * Number(valores.percentual_novas_contas) / 100;
  const nao_folha = clientes * Number(valores.percentual_nao_folha) / 100;
  const folha = clientes * Number(valores.percentual_folha) / 100;
  // Dos correntistas, os ativos (o inativo não traz rentabilidade)
  const fracao_ativos = Number(valores.percentual_ativos) / 100;
  const nao_folha_ativos = nao_folha * fracao_ativos;
  const folha_ativos = folha * fracao_ativos;
  const linhas = [
    linha_no_exemplo("Novas contas", novas_contas, "× MOB cliente novo (R$ " + mob_novo.toFixed(2) + ")",
      novas_contas * mob_novo, true),
    linha_no_exemplo("Correntistas não folha · ativos (folha identificada)", nao_folha_ativos,
      "× (MOB folha − MOB não folha) = R$ " + diferenca_de_mob.toFixed(2), nao_folha_ativos * diferenca_de_mob, true),
    linha_no_exemplo("Correntistas não folha · inativos", nao_folha - nao_folha_ativos, "inativo: sem rentabilidade",
      0, false),
    linha_no_exemplo("Correntistas folha · ativos", folha_ativos, "já traz o MOB folha: sem rentabilidade nova", 0,
      false),
    linha_no_exemplo("Correntistas folha · inativos", folha - folha_ativos, "inativo: sem rentabilidade", 0, false),
    linha_no_exemplo("Resto da base (não abrem conta)", clientes - novas_contas - nao_folha - folha,
      "sem rentabilidade", 0, false),
  ];
  // O total é a soma das linhas, já em centavos
  let total = 0;
  for (const linha of linhas) {
    total = total + Number(linha.ganho);
  }
  return { clientes: clientes, linhas: linhas, total: String(em_centavos_no_simulador(total)), falta: [] };
}

/**
 * Quanto a parte é do todo, em % com uma casa, como texto; null quando o todo é zero (sem divisão por zero).
 *
 * Recebe: parte; todo. Devolve: ex.: (3, 10) → "30.0"; (1, 0) → null.
 */
function porcentagem_observada(parte, todo) {
  if (todo === 0) {
    return null;
  }
  return (100 * parte / todo).toFixed(1);
}

/**
 * O que o retorno do banco já confirmou, no protótipo (a mesma conta de planejamento.retorno_confirmado).
 *
 * Recebe: valores (os usados). Devolve: o formato do servidor.
 */
function confirmado_no_exemplo(valores) {
  const resumo = somar(empresas_de_exemplo_com(estado_do_simulador.empresa_id, ""));
  const com_retorno = resumo.cadastrados - resumo.aguardando_retorno;
  const diferenca_de_mob = Number(valores.mob_cliente_folha) - Number(valores.mob_cliente_nao_folha);
  const mob_novo = Number(valores.mob_cliente_novo_conquistado);
  // Só o falso não folha ativo entra no realizado (o inativo não traz rentabilidade)
  const realizado = resumo.falso_nao_folha_ativos * diferenca_de_mob + resumo.contas_abertas * mob_novo;
  const taxas = { novas_contas: porcentagem_observada(resumo.contas_abertas, com_retorno),
    nao_folha: porcentagem_observada(resumo.falso_nao_folha, com_retorno),
    folha: porcentagem_observada(resumo.ja_eram_folha, com_retorno),
    ativos: porcentagem_observada(resumo.correntistas_ativos, resumo.correntistas_marcados) };
  return { com_retorno: com_retorno, contas_abertas: resumo.contas_abertas, falso_nao_folha: resumo.falso_nao_folha,
    ja_eram_folha: resumo.ja_eram_folha, taxas_observadas: taxas,
    realizado: { total: String(em_centavos_no_simulador(realizado)) } };
}

/**
 * Confere os valores no protótipo (com o servidor, quem confere é ele, com as mesmas regras).
 *
 * Recebe: valores (os usados). Devolve: o recado do primeiro problema, ou "" se está tudo certo.
 */
function recado_do_simulador_no_exemplo(valores) {
  // O horizonte: meses inteiros, de 1 a 60
  const horizonte = Number(valores.horizonte_meses);
  if (!/^[0-9]+$/.test(valores.horizonte_meses) || horizonte < 1 || horizonte > 60) {
    return "O horizonte da projeção precisa ser um número inteiro de meses, de 1 a 60.";
  }
  // Os três MOB: maiores que zero
  for (const nome of ["mob_cliente_folha", "mob_cliente_nao_folha", "mob_cliente_novo_conquistado"]) {
    if (Number(valores[nome]) <= 0) {
      return "\"" + TITULOS_DO_SIMULADOR[nome] + "\" precisa ser maior que zero.";
    }
  }
  // As taxas: vazias ou de 0 a 100
  for (const nome of TAXAS_DO_SIMULADOR) {
    if (!sem_valor(valores[nome]) && (Number(valores[nome]) < 0 || Number(valores[nome]) > 100)) {
      return "\"" + TITULOS_DO_SIMULADOR[nome] + "\": informe uma porcentagem entre 0% e 100%, com no máximo 2 " +
        "casas depois da vírgula.";
    }
  }
  // Novas contas, correntista não folha e correntista folha são partes da mesma base
  let soma_das_partes = 0;
  for (const nome of TAXAS_QUE_DIVIDEM_A_BASE) {
    soma_das_partes = soma_das_partes + Number(valores[nome] || 0);
  }
  if (soma_das_partes > 100) {
    return "% novas contas + % correntista (não folha) + % correntista (folha) passam de 100%: a base de clientes " +
      "não comporta. Confira as três taxas.";
  }
  // A estimativa: inteiro de 0 ao máximo
  const estimativa = valores.clientes_estimados;
  if (!sem_valor(estimativa) && (!/^[0-9]+$/.test(estimativa) || Number(estimativa) > MAXIMO_DE_CLIENTES)) {
    return "O número de clientes precisa ser inteiro, sem pontos nem vírgulas (ex.: 1200), até 10 milhões.";
  }
  return "";
}

/**
 * A simulação inteira no protótipo, no mesmo formato da resposta do servidor.
 *
 * Recebe: valores (os digitados). Devolve: { valores, alteradas, versao_premissas, base, simulacao, confirmado }.
 */
function resultado_no_exemplo(valores) {
  const usados = valores_com_as_oficiais(valores);
  // A estimativa substitui os enviados
  let base = { clientes: estado_do_simulador.base_da_empresa.enviados, origem: "empresa" };
  if (usados.clientes_estimados !== "") {
    base = { clientes: Number(usados.clientes_estimados), origem: "estimativa" };
  }
  const alteradas = [];
  for (const nome of PREMISSAS_GLOBAIS) {
    if (valores[nome] !== "" && !igual_a_oficial(nome, valores[nome])) {
      alteradas.push(nome);
    }
  }
  return { valores: usados, alteradas: alteradas, versao_premissas: estado_do_simulador.oficiais.versao, base: base,
    simulacao: simular_no_exemplo(base.clientes, usados), confirmado: confirmado_no_exemplo(usados) };
}

// ===== 6. Refazer a conta =====

/**
 * Refaz a conta com os valores dos campos: no servidor (sem gravar) ou, no protótipo, aqui.
 *
 * Recebe: nada. Devolve: nada. Espera as premissas oficiais e os clientes da empresa chegarem.
 */
async function atualizar_simulador() {
  marcar_o_que_falta();
  if (estado_do_simulador.oficiais === null || estado_do_simulador.base_da_empresa === null) {
    return;
  }
  const valores = valores_digitados();
  // No protótipo, a conta é feita aqui
  if (!simulador_com_servidor()) {
    const recado = recado_do_simulador_no_exemplo(valores_com_as_oficiais(valores));
    mostrar_recado("[data-erro-simulador]", recado);
    if (!recado) {
      mostrar_resultado_do_simulador(resultado_no_exemplo(valores));
    }
    return;
  }
  // Com o servidor: a mesma conta da aplicação; nada é gravado
  const resposta = await pedir_ao_servidor("/api/banco/planejamento/ganho", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filtros: { empresa_id: estado_do_simulador.empresa_id },
      premissas: valores_para_o_servidor(valores), clientes_da_empresa: estado_do_simulador.base_da_empresa.enviados }),
  });
  // Valor recusado (ou servidor fora): o recado aparece e o último resultado fica (sem resultado ainda, um traço)
  if (!resposta.ok) {
    let recado = "Confira os valores da simulação.";
    if (typeof resposta.dados.detail === "string") {
      recado = resposta.dados.detail;
    }
    mostrar_recado("[data-erro-simulador]", recado);
    mostrar_simulador_indisponivel();
    return;
  }
  mostrar_recado("[data-erro-simulador]", "");
  mostrar_resultado_do_simulador(resposta.dados);
}

/**
 * A pessoa mudou um campo: espera ela parar de digitar e refaz a conta (evita um pedido por tecla).
 *
 * Recebe: nada. Devolve: nada.
 */
function simulador_mudou() {
  marcar_o_que_falta();
  marcar_ajustes_na_simulacao_aberta();
  window.clearTimeout(estado_do_simulador.espera);
  estado_do_simulador.espera = window.setTimeout(atualizar_simulador, ESPERA_DA_DIGITACAO);
}

/**
 * "Voltar às premissas oficiais": os campos de ajuste das premissas globais ficam vazios e a conta se refaz.
 *
 * Recebe: nada. Devolve: nada. As taxas e a estimativa de clientes ficam como estão.
 */
function voltar_as_premissas_oficiais() {
  for (const nome of PREMISSAS_GLOBAIS) {
    campo_do_simulador(nome).value = "";
  }
  mostrar_recado("[data-aviso-simulacao]", "");
  marcar_ajustes_na_simulacao_aberta();
  atualizar_simulador();
}

// ===== 7. Carregar as premissas oficiais e os clientes da empresa =====

/**
 * Busca as premissas oficiais vigentes (no protótipo, as de exemplo) e refaz a conta.
 *
 * Recebe: nada. Devolve: nada. Os campos da pessoa nunca mudam sozinhos.
 */
async function carregar_premissas_oficiais() {
  if (!simulador_com_servidor()) {
    estado_do_simulador.oficiais = PREMISSAS_OFICIAIS_DE_EXEMPLO;
  } else {
    const resposta = await pedir_ao_servidor("/api/banco/premissas");
    if (!resposta.ok) {
      mostrar_simulador_indisponivel();
      return;
    }
    estado_do_simulador.oficiais = { versao: "v" + resposta.dados.versao, valores: resposta.dados.vigente };
  }
  mostrar_premissas_oficiais(estado_do_simulador.oficiais);
  atualizar_simulador();
}

/**
 * Busca os clientes que a empresa da simulação enviou (no protótipo, a soma do exemplo) e refaz a conta.
 *
 * Recebe: nada. Devolve: nada. Uma resposta atrasada de uma empresa que já não está escolhida é ignorada.
 */
async function carregar_base_da_empresa() {
  estado_do_simulador.pedido_da_base = estado_do_simulador.pedido_da_base + 1;
  const este_pedido = estado_do_simulador.pedido_da_base;
  let base = null;
  if (!simulador_com_servidor()) {
    const empresas = empresas_de_exemplo_com(estado_do_simulador.empresa_id, "");
    const soma = somar(empresas);
    let em_analise = 0;
    for (const empresa of empresas) {
      em_analise = em_analise + empresa.em_analise;
    }
    base = { cadastrados: soma.cadastrados, em_analise: em_analise, enviados: soma.cadastrados + em_analise };
  } else {
    const endereco = "/api/banco/planejamento/base?" +
      new URLSearchParams({ empresa_id: estado_do_simulador.empresa_id }).toString();
    const resposta = await pedir_ao_servidor(endereco);
    // Outra empresa foi escolhida enquanto esta resposta vinha: ela não vale mais
    if (este_pedido !== estado_do_simulador.pedido_da_base) {
      return;
    }
    if (!resposta.ok) {
      mostrar_simulador_indisponivel();
      return;
    }
    base = resposta.dados;
  }
  estado_do_simulador.base_da_empresa = base;
  mostrar_base_da_empresa(base);
  atualizar_simulador();
}

// ===== 8. A empresa da simulação =====

/**
 * Escreve o que está sendo simulado ("Simulando a carteira toda." ou a empresa).
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_empresa_da_simulacao() {
  let texto = "Simulando a carteira toda.";
  const empresa = empresa_para_escolher_pelo_id(estado_do_simulador.empresa_id);
  if (empresa !== null) {
    texto = "Simulando " + empresa.nome + ".";
  }
  document.querySelector("[data-sobre-a-simulacao]").textContent = texto;
}

/**
 * Escolhe a empresa da simulação ("" = todas), busca os clientes dela e refaz a conta.
 *
 * Recebe: id. Devolve: nada.
 */
function escolher_empresa_no_simulador(id) {
  estado_do_simulador.empresa_id = id;
  document.querySelector("[data-empresa-simulador]").value = texto_do_campo_para_a_empresa(id);
  mostrar_recado("[data-aviso-empresa-simulador]", "");
  mostrar_empresa_da_simulacao();
  carregar_base_da_empresa();
}

/**
 * A pessoa digitou ou escolheu uma sugestão no campo da empresa: acha a empresa e simula.
 *
 * Recebe: nada. Devolve: nada. Sem achar uma empresa só, o aviso aparece e a simulação continua como estava.
 */
function empresa_do_simulador_mudou() {
  const id = empresa_pelo_texto(document.querySelector("[data-empresa-simulador]").value);
  if (id === null) {
    mostrar_recado("[data-aviso-empresa-simulador]",
      "Nenhuma empresa da carteira com este nome ou CNPJ. Confira ou escolha nas sugestões.");
    return;
  }
  if (id === estado_do_simulador.empresa_id) {
    mostrar_recado("[data-aviso-empresa-simulador]", "");
    return;
  }
  marcar_ajustes_na_simulacao_aberta();
  escolher_empresa_no_simulador(id);
}

// ===== 9. As simulações salvas =====

/**
 * A empresa de uma simulação salva, pelo nome ("carteira toda" quando não escolheu nenhuma).
 *
 * Recebe: simulacao — { filtros: { empresa_id } }. Devolve: ex.: "Aurora Alimentos" ou "carteira toda".
 */
function empresa_da_simulacao(simulacao) {
  const filtros = simulacao.filtros || {};
  const empresa = empresa_para_escolher_pelo_id(filtros.empresa_id || "");
  if (empresa !== null) {
    return empresa.nome;
  }
  // Uma empresa que não está mais na lista: o código dela
  if (filtros.empresa_id) {
    return filtros.empresa_id;
  }
  return "carteira toda";
}

/**
 * O texto de uma simulação salva na lista: nome, quem, quando, a empresa, a base e a rentabilidade.
 *
 * Recebe: simulacao — { nome, usuario, criado_em, filtros, base, ganho_total }. Devolve: o texto.
 * Ex.: "Cenário otimista · rafael.lima · 28/09/2026 14:40 · Aurora Alimentos · 312 clientes · R$ 223.139,19".
 */
function texto_da_simulacao(simulacao) {
  // Simulação antiga, de antes do nome
  const partes = [simulacao.nome || "Simulação sem nome", simulacao.usuario, formatar_data_e_hora(simulacao.criado_em),
    empresa_da_simulacao(simulacao)];
  // A base (as simulações de antes do Simulador de Rentabilidade não têm)
  if (simulacao.base) {
    partes.push(no_singular_ou_plural(simulacao.base.clientes, "cliente", "clientes"));
  }
  // O total, ou o aviso de que faltou taxa
  if (sem_valor(simulacao.ganho_total)) {
    partes.push("sem as taxas");
  } else {
    partes.push(formatar_reais(simulacao.ganho_total));
  }
  return partes.join(" · ");
}

/**
 * Um botão pequeno da linha de uma simulação salva ("Visualizar" ou "Reabrir").
 *
 * Recebe: texto (o que aparece); rotulo (o que o leitor de tela diz); marca (o atributo data- que o roteiro acha);
 * acao (a função chamada no clique). Devolve: o <button>.
 */
function botao_da_simulacao(texto, rotulo, marca, acao) {
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "botao botao-contorno botao-mini";
  botao.textContent = texto;
  botao.setAttribute("aria-label", rotulo);
  botao.setAttribute(marca, "");
  botao.addEventListener("click", acao);
  return botao;
}

/**
 * Desenha a lista das simulações salvas, cada uma com os botões "Visualizar" e "Reabrir".
 *
 * Recebe: simulacoes — da mais recente para a mais antiga. Devolve: nada.
 */
function desenhar_simulacoes(simulacoes) {
  const lista = document.querySelector("[data-simulacoes-salvas]");
  lista.replaceChildren();
  // Nenhuma salva ainda
  if (simulacoes.length === 0) {
    const vazio = document.createElement("li");
    vazio.textContent = "Nenhuma simulação salva ainda.";
    lista.append(vazio);
  }
  for (const simulacao of simulacoes) {
    const item = document.createElement("li");
    item.className = "simulacao-salva";
    // O nome da simulação marca o item (o roteiro de teste acha a linha por ele)
    item.dataset.simulacaoSalva = simulacao.nome;
    const texto = document.createElement("span");
    texto.textContent = texto_da_simulacao(simulacao);
    const nome = simulacao.nome || "sem nome";
    const botoes = document.createElement("span");
    botoes.className = "botoes-da-simulacao";
    botoes.append(
      botao_da_simulacao("Visualizar", "Visualizar a simulação " + nome, "data-visualizar-simulacao", function () {
        abrir_janela_da_simulacao(simulacao);
      }),
      botao_da_simulacao("Reabrir", "Reabrir a simulação " + nome, "data-reabrir-simulacao", function () {
        reabrir_simulacao(simulacao);
      }));
    item.append(texto, " ", botoes);
    lista.append(item);
  }
  marcar_como_carregado(lista);
}

// ===== 9b. A janela "Visualizar" =====

/**
 * Um valor travado da janela (o mesmo quadro cinza das seções travadas do simulador).
 *
 * Recebe: nome (ex.: "MOB cliente folha"); valor (o texto). Devolve: o <div>.
 */
function quadro_travado(nome, valor) {
  const quadro = document.createElement("div");
  quadro.className = "rotulo-travado";
  const titulo = document.createElement("span");
  titulo.textContent = nome;
  const numero = document.createElement("strong");
  numero.textContent = valor;
  quadro.append(titulo, numero);
  return quadro;
}

/**
 * Uma taxa salva como aparece na janela: "30%", ou "—" quando a simulação não tinha essa taxa.
 *
 * Recebe: valor (texto, ex.: "30.00", ou null). Devolve: o texto.
 */
function taxa_salva_em_texto(valor) {
  if (sem_valor(valor)) {
    return "—";
  }
  return formatar_porcentagem(valor);
}

/**
 * Os quadros da base de clientes da simulação salva: o número e de onde ele veio.
 *
 * Recebe: simulacao. Devolve: a lista de quadros.
 */
function quadros_da_base(simulacao) {
  // As simulações de antes do Simulador de Rentabilidade não guardaram a base
  if (!simulacao.base) {
    return [quadro_travado("Clientes", "não guardado")];
  }
  let origem = "os que a empresa enviou";
  if (simulacao.base.origem === "estimativa") {
    origem = "a sua estimativa";
  }
  return [quadro_travado("Clientes", formatar_numero(simulacao.base.clientes)), quadro_travado("De onde veio", origem)];
}

/**
 * Desenha as linhas "Rentabilidade por grupo" da simulação salva, como estavam quando ela foi salva.
 *
 * Recebe: simulacao. Devolve: nada. Sem o detalhe guardado (simulação antiga) ou sem as taxas, uma linha explica.
 */
function mostrar_linhas_da_janela(simulacao) {
  const corpo = document.querySelector("[data-janela-simulacao-linhas]");
  corpo.replaceChildren();
  let linhas = [];
  if (simulacao.simulacao) {
    linhas = simulacao.simulacao.linhas;
  }
  // Nada por grupo para mostrar: o motivo, numa linha
  if (linhas.length === 0) {
    let motivo = "Simulação salva antes do detalhe por grupo: só o total foi guardado.";
    if (simulacao.simulacao) {
      motivo = "Salva sem todas as taxas: não há rentabilidade por grupo.";
    }
    corpo.append(criar_linha([motivo, "", "", ""]));
  }
  for (const grupo of linhas) {
    const linha = criar_linha([grupo.grupo, clientes_estimados_em_texto(grupo.pessoas), grupo.conta,
      formatar_reais(grupo.ganho)]);
    // O grupo que não traz rentabilidade nova fica em cinza, como no simulador
    if (!grupo.rende) {
      linha.classList.add("linha-sem-rentabilidade");
    }
    corpo.append(linha);
  }
}

/**
 * "Visualizar": abre a janela com a simulação salva inteira (quem, quando, empresa, total, base, premissas, taxas e
 * a rentabilidade por grupo), sem mexer no que está no simulador.
 *
 * Recebe: simulacao — uma das salvas (o formato de GET /api/banco/planejamento/simulacoes). Devolve: nada.
 */
function abrir_janela_da_simulacao(simulacao) {
  estado_do_simulador.simulacao_na_janela = simulacao;
  const valores = simulacao.valores || {};
  document.querySelector("[data-janela-simulacao-titulo]").textContent = simulacao.nome || "Simulação sem nome";
  document.querySelector("[data-janela-simulacao-resumo]").textContent = "Salva por " + simulacao.usuario + " em " +
    formatar_data_e_hora(simulacao.criado_em) + " · " + empresa_da_simulacao(simulacao);
  // O total em destaque (sem as taxas, um traço)
  let total = "—";
  if (!sem_valor(simulacao.ganho_total)) {
    total = formatar_reais(simulacao.ganho_total);
  }
  document.querySelector("[data-janela-simulacao-total]").textContent = total;
  document.querySelector("[data-janela-simulacao-legenda-total]").textContent = "Rentabilidade em " +
    texto_da_premissa("horizonte_meses", valores.horizonte_meses);
  document.querySelector("[data-janela-simulacao-base]").replaceChildren(...quadros_da_base(simulacao));
  // As premissas globais que ela usou, com a versão oficial de onde partiu
  document.querySelector("[data-janela-simulacao-versao]").textContent = "oficiais " + simulacao.versao_premissas;
  const premissas = [];
  for (const nome of PREMISSAS_GLOBAIS) {
    premissas.push(quadro_travado(TITULOS_DO_SIMULADOR[nome], texto_da_premissa(nome, valores[nome])));
  }
  document.querySelector("[data-janela-simulacao-premissas]").replaceChildren(...premissas);
  // As taxas que ela usou
  const taxas = [];
  for (const nome of TAXAS_DO_SIMULADOR) {
    taxas.push(quadro_travado(TITULOS_DO_SIMULADOR[nome], taxa_salva_em_texto(valores[nome])));
  }
  document.querySelector("[data-janela-simulacao-taxas]").replaceChildren(...taxas);
  mostrar_linhas_da_janela(simulacao);
  document.querySelector("[data-janela-simulacao]").showModal();
}

/**
 * Fecha a janela "Visualizar".
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_janela_da_simulacao() {
  document.querySelector("[data-janela-simulacao]").close();
}

/**
 * "Reabrir no simulador", de dentro da janela: fecha a janela e põe a simulação no simulador.
 *
 * Recebe: nada. Devolve: nada.
 */
function reabrir_da_janela() {
  fechar_janela_da_simulacao();
  reabrir_simulacao(estado_do_simulador.simulacao_na_janela);
}

// ===== 9c. A simulação salva que está aberta =====

/**
 * Mostra a etiqueta "Simulação salva: <nome>" no alto do simulador (sem os ajustes: está como foi salva).
 *
 * Recebe: nome (o da simulação). Devolve: nada.
 */
function mostrar_simulacao_aberta(nome) {
  document.querySelector("[data-nome-simulacao-aberta]").textContent = nome;
  document.querySelector("[data-ajustes-simulacao-aberta]").hidden = true;
  document.querySelector("[data-simulacao-aberta]").hidden = false;
}

/**
 * A pessoa mudou algo no simulador: se há uma simulação salva aberta, a etiqueta avisa "com ajustes não salvos".
 *
 * Recebe: nada. Devolve: nada. Sem simulação aberta, nada muda.
 */
function marcar_ajustes_na_simulacao_aberta() {
  if (document.querySelector("[data-simulacao-aberta]").hidden) {
    return;
  }
  document.querySelector("[data-ajustes-simulacao-aberta]").hidden = false;
}

/**
 * O × da etiqueta: deixa de olhar para a simulação salva (os campos ficam como estão).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_simulacao_aberta() {
  document.querySelector("[data-simulacao-aberta]").hidden = true;
  mostrar_recado("[data-aviso-simulacao]", "");
}

// O respiro entre o cabeçalho grudado no alto e o começo do simulador, depois de subir a tela (em pixels).
const RESPIRO_ACIMA_DO_SIMULADOR = 16;

/**
 * Sobe a tela até o início do cartão do simulador (o título e a etiqueta da simulação aberta), com uma rolagem suave.
 *
 * Recebe: nada. Devolve: nada.
 * Por quê: o cabeçalho do Portal Interno fica grudado no alto (.topo-banco) e cobriria o começo do cartão; a conta
 * desconta a altura dele, para o começo do cartão ficar à vista.
 */
function subir_ate_o_simulador() {
  const cartao = document.querySelector("[data-simulador]");
  // A altura do cabeçalho grudado (zero se a página não tiver um)
  const cabecalho = document.querySelector(".topo-banco");
  let altura_do_cabecalho = 0;
  if (cabecalho) {
    altura_do_cabecalho = cabecalho.getBoundingClientRect().height;
  }
  // Onde o cartão está na página inteira, menos o cabeçalho e o respiro
  const destino = cartao.getBoundingClientRect().top + window.scrollY - altura_do_cabecalho - RESPIRO_ACIMA_DO_SIMULADOR;
  window.scrollTo({ top: destino, behavior: "smooth" });
}

/**
 * "Reabrir": põe os valores e a empresa da simulação salva de volta no simulador, refaz a conta, sobe a tela até o
 * início do simulador e mostra o nome dela na etiqueta do alto.
 *
 * Recebe: simulacao — { nome, valores, filtros }. Devolve: nada. As premissas oficiais não mudam.
 */
function reabrir_simulacao(simulacao) {
  mostrar_simulacao_aberta(simulacao.nome || "Simulação sem nome");
  subir_ate_o_simulador();
  preencher_campos(simulacao.valores);
  mostrar_recado("[data-aviso-simulacao]", "Os valores da simulação \"" + (simulacao.nome || "sem nome") +
    "\" estão no simulador. As premissas oficiais não mudaram.");
  // A empresa que ela usou (vazio = todas); a conta se refaz com os clientes que essa empresa enviou hoje
  const filtros_salvos = simulacao.filtros || {};
  escolher_empresa_no_simulador(filtros_salvos.empresa_id || "");
}

/**
 * Mostra as simulações salvas no servidor (da mais recente para a mais antiga).
 *
 * Recebe: nada. Devolve: nada.
 */
async function mostrar_simulacoes_da_api() {
  const resposta = await pedir_ao_servidor("/api/banco/planejamento/simulacoes");
  if (!resposta.ok) {
    // Sem a lista: o aviso de falha, nunca o exemplo
    const lista = document.querySelector("[data-simulacoes-salvas]");
    if (!lista.hasAttribute("data-dado-pronto")) {
      const aviso = document.createElement("li");
      aviso.textContent = AVISO_DE_FALHA_NO_PLANEJAMENTO;
      lista.replaceChildren(aviso);
      marcar_como_carregado(lista);
    }
    return;
  }
  desenhar_simulacoes(resposta.dados);
}

/**
 * "Salvar esta simulação": confere o nome e guarda (no servidor, com quem salvou; no protótipo, só na lista).
 *
 * Recebe: evento — o envio do formulário do nome. Devolve: nada.
 */
async function salvar_simulacao(evento) {
  evento.preventDefault();
  const campo_do_nome = document.querySelector("[data-nome-simulacao]");
  const nome = campo_do_nome.value.trim();
  mostrar_recado("[data-aviso-simulacao]", "");
  // O nome é obrigatório
  if (nome === "") {
    mostrar_recado("[data-erro-salvar-simulacao]", "Dê um nome à simulação para salvar.");
    campo_do_nome.focus();
    return;
  }
  // Sem as premissas oficiais ou os clientes da empresa, não há simulação para salvar
  if (estado_do_simulador.oficiais === null || estado_do_simulador.base_da_empresa === null) {
    mostrar_recado("[data-erro-salvar-simulacao]", "Espere a simulação carregar para salvar.");
    return;
  }
  mostrar_recado("[data-erro-salvar-simulacao]", "");
  const valores = valores_digitados();
  // No protótipo: a simulação entra só na lista da tela
  if (!simulador_com_servidor()) {
    const resultado = resultado_no_exemplo(valores);
    estado_do_simulador.salvas_no_exemplo.unshift({ nome: nome, usuario: "rafael.lima",
      criado_em: new Date().toISOString(), valores: resultado.valores,
      filtros: { empresa_id: estado_do_simulador.empresa_id }, base: resultado.base,
      ganho_total: resultado.simulacao.total, simulacao: resultado.simulacao,
      versao_premissas: estado_do_simulador.oficiais.versao });
    desenhar_simulacoes(estado_do_simulador.salvas_no_exemplo);
    campo_do_nome.value = "";
    mostrar_recado("[data-aviso-simulacao]", "Simulação \"" + nome + "\" salva.");
    // O que está no simulador agora é a simulação que acabou de ser salva
    mostrar_simulacao_aberta(nome);
    return;
  }
  const botao = document.querySelector("[data-salvar-simulacao]");
  // Evita salvar duas vezes com dois cliques rápidos
  botao.disabled = true;
  const resposta = await pedir_ao_servidor("/api/banco/planejamento/simulacoes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome: nome, filtros: { empresa_id: estado_do_simulador.empresa_id },
      premissas: valores_para_o_servidor(valores), clientes_da_empresa: estado_do_simulador.base_da_empresa.enviados }),
  });
  botao.disabled = false;
  if (!resposta.ok) {
    let recado = "Não foi possível salvar agora.";
    if (typeof resposta.dados.detail === "string") {
      recado = resposta.dados.detail;
    }
    mostrar_recado("[data-erro-salvar-simulacao]", recado);
    return;
  }
  campo_do_nome.value = "";
  mostrar_recado("[data-aviso-simulacao]", "Simulação \"" + resposta.dados.nome +
    "\" salva. As premissas oficiais não mudaram.");
  // O que está no simulador agora é a simulação que acabou de ser salva
  mostrar_simulacao_aberta(resposta.dados.nome);
  mostrar_simulacoes_da_api();
}

// ===== 10. Preparação =====

/**
 * Busca de novo o que vem do servidor (as oficiais, os clientes da empresa e as salvas) sem mexer nos campos.
 *
 * Recebe: nada. Devolve: nada. Chamada quando a pessoa volta para a aba do navegador.
 */
function recarregar_simulador() {
  carregar_premissas_oficiais();
  carregar_base_da_empresa();
  if (simulador_com_servidor()) {
    mostrar_simulacoes_da_api();
  }
}

/**
 * Liga os campos e os botões do simulador e carrega o que ele precisa.
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_simulador() {
  // A empresa: ao escolher uma sugestão, sair do campo ou apertar Enter; "Todas as empresas" limpa.
  const campo_da_empresa = document.querySelector("[data-empresa-simulador]");
  campo_da_empresa.addEventListener("change", empresa_do_simulador_mudou);
  document.querySelector("[data-formulario-empresa-simulador]").addEventListener("submit", function (evento) {
    evento.preventDefault();
    empresa_do_simulador_mudou();
  });
  document.querySelector("[data-todas-no-simulador]").addEventListener("click", function () {
    marcar_ajustes_na_simulacao_aberta();
    escolher_empresa_no_simulador("");
  });
  // O × da etiqueta da simulação aberta
  document.querySelector("[data-fechar-simulacao-aberta]").addEventListener("click", fechar_simulacao_aberta);
  // A lista das empresas chegou: o campo mostra a empresa da simulação (se a pessoa não estiver digitando nele).
  document.addEventListener("empresas-para-escolher-prontas", function () {
    if (document.activeElement !== campo_da_empresa) {
      campo_da_empresa.value = texto_do_campo_para_a_empresa(estado_do_simulador.empresa_id);
    }
    mostrar_empresa_da_simulacao();
  });
  // Cada campo da especialista: refaz a conta quando ela para de digitar
  for (const campo of document.querySelectorAll("[data-premissa-simulador]")) {
    campo.addEventListener("input", simulador_mudou);
  }
  // Enter num campo não recarrega a página: refaz a conta na hora
  document.querySelector("[data-formulario-simulador]").addEventListener("submit", function (evento) {
    evento.preventDefault();
    atualizar_simulador();
  });
  document.querySelector("[data-voltar-oficiais]").addEventListener("click", voltar_as_premissas_oficiais);
  document.querySelector("[data-formulario-salvar-simulacao]").addEventListener("submit", salvar_simulacao);
  // A janela "Visualizar": o X e "Fechar" fecham; "Reabrir no simulador" leva a simulação para os campos
  for (const botao of document.querySelectorAll("[data-fechar-janela-simulacao]")) {
    botao.addEventListener("click", fechar_janela_da_simulacao);
  }
  document.querySelector("[data-reabrir-da-janela]").addEventListener("click", reabrir_da_janela);
  // Ao voltar para a aba do navegador, os números travados se atualizam (os campos da pessoa ficam)
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      recarregar_simulador();
    }
  });
  // Com o servidor, nada do exemplo pode aparecer: a lista de exemplo sai já
  if (simulador_com_servidor()) {
    document.querySelector("[data-simulacoes-salvas]").replaceChildren();
  }
  marcar_o_que_falta();
  recarregar_simulador();
}

// Quando o HTML terminar de carregar, prepara o simulador.
document.addEventListener("DOMContentLoaded", preparar_simulador);
