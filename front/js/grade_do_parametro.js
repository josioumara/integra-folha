/*
  grade_do_parametro.js — a grade de funcionários montada pelo parâmetro do banco (ADR-111 e ADR-143).

  Para que serve: as telas que mostram funcionários (a consulta e o "Conferir e enviar" da empresa, em acompanhar.html;
  a conferência da lista, em cadastrar.html; as pessoas de um envio, na tela Envios do banco; e a Visão geral da
  empresa, na tela Empresas do banco) usam a MESMA grade:
    - uma coluna por campo OBRIGATÓRIO do parâmetro vigente (só os obrigatórios; ADR-143), na ordem do layout, com o
      grupo do campo numa linha em cima;
    - "*" na cor da marca nas colunas obrigatórias (e a descrição do banco ao passar o mouse);
    - em cada célula, o valor identificado (formatado pelo tipo: data, dinheiro, CNPJ, telefone, CEP) ou a frase
      "Informação não encontrada";
    - o clique na pessoa abre o DETALHE, com todos os campos do parâmetro, agrupados (Titular, Renda...), e a mesma
      frase no que veio em branco.
    - quando a IA guardou alguma informação sem rótulo (a dúvida entre campos opcionais), o detalhe ganha a seção
      "Informações sem rótulo", no fim dos grupos (ADR-143, Parte 1). Ela nunca aparece na grade.
  Quais campos são obrigatórios vem da marca "obrigatorio" do parâmetro, nunca de uma lista escrita aqui: se o banco
  marcar mais um campo na tela Parâmetros, ele aparece na grade sozinho.
  As colunas vêm da API (/api/empresa/colunas_da_consulta ou /api/banco/colunas_da_consulta); cada tela junta, no
  fim, as colunas dela (ex.: Conta, Incluído e Situação na empresa; Situação e Ação no banco).
*/

// O texto de uma célula cujo valor não veio no arquivo (ou não foi identificado).
const TEXTO_SEM_VALOR = "Informação não encontrada";

/**
 * Uma data "AAAA-MM-DD" no jeito brasileiro. Exemplo: "2026-08-05" → "05/08/2026" (outro formato volta como veio).
 *
 * Recebe: valor. Devolve: o texto.
 */
function grade_data_brasileira(valor) {
  const pedacos = valor.slice(0, 10).split("-");
  if (pedacos.length !== 3) {
    return valor;
  }
  return pedacos[2] + "/" + pedacos[1] + "/" + pedacos[0];
}

/**
 * Uma data "AAAA-MM-DD" vira "dd/mm/aaaa"; qualquer outro texto (ex.: agência "1234", ou uma data que já veio
 * "12/09/2026") volta como veio.
 *
 * Recebe: valor. Devolve: o texto.
 */
function grade_data_brasileira_se_for_data(valor) {
  const pedacos = valor.split("-");
  if (pedacos.length === 3 && pedacos[0].length === 4) {
    return grade_data_brasileira(valor);
  }
  return valor;
}

/**
 * Um valor em reais. Exemplo: "3180.00" → "R$ 3.180,00" (texto que não é número volta como veio).
 *
 * Recebe: valor. Devolve: o texto.
 */
function grade_em_reais(valor) {
  const numero = Number(valor);
  if (Number.isNaN(numero)) {
    return valor;
  }
  return numero.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Pontua CNPJ (14 dígitos), telefone (10 ou 11 dígitos) e CEP (8 dígitos); outro tamanho volta como veio.
 *
 * Recebe: tipo — "CNPJ", "TELEFONE" ou "CEP"; valor. Devolve: o texto pontuado.
 * Exemplos: ("CEP", "13010000") → "13010-000"; ("TELEFONE", "1932345678") → "(19) 3234-5678".
 */
function grade_pontuar(tipo, valor) {
  if (tipo === "CNPJ" && valor.length === 14) {
    return valor.slice(0, 2) + "." + valor.slice(2, 5) + "." + valor.slice(5, 8) + "/" + valor.slice(8, 12) + "-" +
      valor.slice(12);
  }
  if (tipo === "TELEFONE" && valor.length === 11) {
    return "(" + valor.slice(0, 2) + ") " + valor.slice(2, 7) + "-" + valor.slice(7);
  }
  if (tipo === "TELEFONE" && valor.length === 10) {
    return "(" + valor.slice(0, 2) + ") " + valor.slice(2, 6) + "-" + valor.slice(6);
  }
  if (tipo === "CEP" && valor.length === 8) {
    return valor.slice(0, 5) + "-" + valor.slice(5);
  }
  return valor;
}

/**
 * O valor de um campo do jeito que a pessoa lê, pelo tipo do campo no parâmetro.
 *
 * Recebe: coluna — {campo, tipo, ...}; valor — o texto que veio da API (não vazio).
 * Devolve: o texto pronto para a célula. Exemplo: ({tipo: "DATA"}, "2026-08-05") → "05/08/2026".
 */
function texto_do_valor(coluna, valor) {
  if (coluna.tipo === "DATA") {
    return grade_data_brasileira(valor);
  }
  if (coluna.tipo === "DECIMAL_MONETARIO") {
    return grade_em_reais(valor);
  }
  return grade_pontuar(coluna.tipo, valor);
}

/**
 * A célula de um campo: o valor identificado, ou "Informação não encontrada" (mais clara e em itálico) se veio vazio.
 *
 * Recebe: coluna; valor — o texto do campo (pode ser vazio, null ou undefined). Devolve: o <td>.
 */
function celula_do_valor(coluna, valor) {
  const celula = document.createElement("td");
  if (!valor) {
    const sem_valor = document.createElement("span");
    sem_valor.className = "valor-nao-encontrado";
    sem_valor.textContent = TEXTO_SEM_VALOR;
    celula.appendChild(sem_valor);
    return celula;
  }
  celula.textContent = texto_do_valor(coluna, String(valor));
  return celula;
}

/**
 * A célula do cabeçalho de um campo: o rótulo e, se o campo é obrigatório no parâmetro, a marca "*".
 *
 * Recebe: coluna. Devolve: o <th>. Passar o mouse mostra a descrição que o banco escreveu no parâmetro.
 */
function celula_do_cabecalho(coluna) {
  const celula = document.createElement("th");
  celula.scope = "col";
  celula.textContent = coluna.rotulo;
  celula.title = coluna.descricao;
  if (coluna.obrigatorio) {
    celula.classList.add("coluna-obrigatoria");
    celula.title = coluna.descricao + " (obrigatório no parâmetro do banco)";
    const marca = document.createElement("span");
    marca.className = "marca-obrigatorio";
    marca.textContent = "*";
    // Leitor de tela: diz "obrigatório" em vez de "asterisco".
    marca.setAttribute("aria-label", "obrigatório");
    celula.appendChild(marca);
  }
  return celula;
}

/**
 * Acrescenta ao cabeçalho um bloco de colunas próprias da tela (fora do parâmetro), com um grupo por cima.
 *
 * Recebe: linha_dos_grupos e linha_dos_campos — as duas linhas do cabeçalho; nome_do_grupo; titulos; nota — o texto
 * que aparece ao passar o mouse no grupo ("" = nenhum). Devolve: nada. Sem títulos, não acrescenta nada.
 */
function acrescentar_colunas_da_tela(linha_dos_grupos, linha_dos_campos, nome_do_grupo, titulos, nota) {
  if (titulos.length === 0) {
    return;
  }
  const celula_do_grupo = document.createElement("th");
  celula_do_grupo.scope = "colgroup";
  celula_do_grupo.textContent = nome_do_grupo;
  celula_do_grupo.colSpan = titulos.length;
  if (nota) {
    celula_do_grupo.title = nota;
  }
  linha_dos_grupos.appendChild(celula_do_grupo);
  for (const titulo of titulos) {
    const celula = document.createElement("th");
    celula.scope = "col";
    celula.textContent = titulo;
    linha_dos_campos.appendChild(celula);
  }
}

/**
 * Monta o cabeçalho da grade em duas linhas: em cima, o grupo (Titular, Endereço residencial...); embaixo, o nome de
 * cada campo. Antes dos campos, as colunas da tela (ex.: a Situação); depois, os blocos finais, cada um com o seu grupo
 * (ex.: "Informações bancárias" e "Inclusão").
 *
 * Recebe: cabeca — o <thead>; colunas — as colunas do parâmetro; titulos_iniciais — os títulos antes dos campos (lista
 * vazia: nenhum); blocos_finais — [{grupo, titulos, nota}, ...] depois dos campos. Devolve: nada.
 */
function montar_cabecalho_da_grade(cabeca, colunas, titulos_iniciais, blocos_finais) {
  const linha_dos_grupos = document.createElement("tr");
  linha_dos_grupos.className = "linha-de-grupos";
  const linha_dos_campos = document.createElement("tr");
  // As colunas da tela que vêm antes dos campos (ex.: a Situação)
  acrescentar_colunas_da_tela(linha_dos_grupos, linha_dos_campos, "Situação", titulos_iniciais, "");
  // Campos seguidos do mesmo grupo dividem uma célula de grupo só (colSpan = quantos campos o grupo tem).
  let celula_do_grupo = null;
  let grupo_anterior = null;
  for (const coluna of colunas) {
    if (coluna.grupo !== grupo_anterior) {
      celula_do_grupo = document.createElement("th");
      celula_do_grupo.scope = "colgroup";
      celula_do_grupo.textContent = coluna.grupo;
      celula_do_grupo.colSpan = 1;
      linha_dos_grupos.appendChild(celula_do_grupo);
      grupo_anterior = coluna.grupo;
    } else {
      celula_do_grupo.colSpan = celula_do_grupo.colSpan + 1;
    }
    linha_dos_campos.appendChild(celula_do_cabecalho(coluna));
  }
  // Os blocos da própria tela, no fim, cada um com o seu grupo.
  for (const bloco of blocos_finais) {
    acrescentar_colunas_da_tela(linha_dos_grupos, linha_dos_campos, bloco.grupo, bloco.titulos, bloco.nota);
  }
  cabeca.replaceChildren(linha_dos_grupos, linha_dos_campos);
  // A tabela ganha a classe da grade (células numa linha só, a linha dos grupos colorida).
  cabeca.closest("table").classList.add("grade-do-parametro");
}

// ===== A lista de funcionários (consulta da empresa e visão da empresa no banco) =====

// Os status de um funcionário na lista, com a cor do selo. O que cada um quer dizer vem do servidor, no "i" em cima da
// grade (js/legenda_dos_status.js, com os textos de services/legenda_dos_status.py; o teste
// tests/test_legenda_dos_status.py confere que o texto e a cor daqui batem com os de lá). A ordem é a da jornada:
// "Aguardando envio" vem antes de "Pendente". Os dois últimos são "Conta aberta" e "Já é
// correntista": só o banco muda para eles, ao mandar a conta da pessoa com o tipo (ADR-113, ADR-123).
const STATUS_DOS_FUNCIONARIOS = [
  { situacao: "Aguardando envio", classe: "selo-neutro" },
  { situacao: "Pendente", classe: "selo-atencao" },
  { situacao: "Em análise", classe: "selo-marca" },
  { situacao: "Cadastrado", classe: "selo-sucesso" },
  { situacao: "Conta aberta", classe: "selo-conta-aberta" },
  { situacao: "Já é correntista", classe: "selo-conta-aberta" },
];

// Os blocos de colunas do fim da grade de funcionários, cada um com o seu grupo no cabeçalho:
// - "Informações bancárias": a conta da pessoa, que o banco envia ao final da integração (ADR-113);
// - "Inclusão": quem da empresa incluiu a pessoa, e quando.
const NOTA_DAS_INFORMACOES_BANCARIAS =
  "Enviadas pelo banco ao final da integração, quando a conta salário da pessoa é aberta.";
const BLOCOS_FINAIS_DOS_FUNCIONARIOS = [
  { grupo: "Informações bancárias", titulos: ["Código do banco", "Agência", "Conta salário", "Aberta em"],
    nota: NOTA_DAS_INFORMACOES_BANCARIAS },
  { grupo: "Inclusão", titulos: ["Incluído"], nota: "" },
];

/**
 * A classe de cor do selo de uma situação. Exemplo: "Cadastrado" → "selo-sucesso" (situação desconhecida: a de atenção).
 *
 * Recebe: situacao. Devolve: a classe.
 */
function classe_do_selo_do_status(situacao) {
  for (const status of STATUS_DOS_FUNCIONARIOS) {
    if (status.situacao === situacao) {
      return status.classe;
    }
  }
  return "selo-atencao";
}

/**
 * Uma célula com um texto em cima e outro menor embaixo. Exemplo: ("01/08/2026", "por Marina Costa").
 *
 * Recebe: texto_principal; texto_de_apoio ("" = nenhum). Devolve: o <td>.
 */
function celula_de_duas_linhas(texto_principal, texto_de_apoio) {
  const celula = document.createElement("td");
  celula.textContent = texto_principal;
  if (texto_de_apoio) {
    celula.className = "celula-duas-linhas";
    const apoio = document.createElement("span");
    apoio.textContent = texto_de_apoio;
    celula.appendChild(apoio);
  }
  return celula;
}

/**
 * Monta a linha de um funcionário: a Situação primeiro, depois uma célula por campo da grade (o valor ou
 * "Informação não encontrada") e, no fim, a Conta e o Incluído.
 *
 * Recebe: pessoa — um funcionário da API (campos do parâmetro, situacao, agencia, conta, conta_aberta_em, incluido_em,
 * incluido_por); colunas — as colunas da grade (os obrigatórios do parâmetro, ver colunas_obrigatorias);
 * ao_clicar_na_pessoa — função que abre o detalhe da pessoa (ou null: a linha é só para ler). Devolve: o <tr>.
 * Com a função, a linha inteira abre o detalhe, e o valor do primeiro campo vira o botão que abre pelo teclado.
 */
function montar_linha_de_funcionario(pessoa, colunas, ao_clicar_na_pessoa) {
  const linha = document.createElement("tr");
  // 1. A situação, com o selo da cor do status (o "i" em cima da grade explica cada um)
  const celula_da_situacao = document.createElement("td");
  const selo = document.createElement("span");
  selo.className = "selo selo-pequeno " + classe_do_selo_do_status(pessoa.situacao);
  selo.textContent = pessoa.situacao || "Cadastrado";
  celula_da_situacao.appendChild(selo);
  linha.appendChild(celula_da_situacao);
  // 2. Os campos da grade; com a função, o primeiro vira o botão que abre o detalhe (o jeito de quem usa o teclado)
  let e_a_primeira_coluna = true;
  for (const coluna of colunas) {
    const valor = pessoa[coluna.campo];
    if (e_a_primeira_coluna && ao_clicar_na_pessoa) {
      linha.appendChild(celula_com_botao_do_detalhe(coluna, valor, ao_clicar_na_pessoa));
    } else {
      linha.appendChild(celula_do_valor(coluna, valor));
    }
    e_a_primeira_coluna = false;
  }
  // 3. A conta no banco, em colunas separadas (código do banco, agência, número e data de abertura). Enquanto o banco
  //    não manda a conta, as quatro ficam com um traço claro.
  for (const valor_da_conta of [pessoa.codigo_banco, pessoa.agencia, pessoa.conta, pessoa.conta_aberta_em]) {
    if (pessoa.conta && valor_da_conta) {
      linha.appendChild(celula_de_duas_linhas(grade_data_brasileira_se_for_data(valor_da_conta), ""));
    } else {
      const celula_vazia = document.createElement("td");
      const traco = document.createElement("span");
      traco.className = "valor-nao-encontrado";
      traco.textContent = "—";
      celula_vazia.appendChild(traco);
      linha.appendChild(celula_vazia);
    }
  }
  // 4. Quem incluiu e quando
  let quem_incluiu = "";
  if (pessoa.incluido_por) {
    quem_incluiu = "por " + pessoa.incluido_por;
  }
  linha.appendChild(celula_de_duas_linhas(grade_data_brasileira(pessoa.incluido_em || ""), quem_incluiu));
  // 5. A linha inteira abre o detalhe da pessoa (sem a função, ela é só para ler)
  if (ao_clicar_na_pessoa) {
    abrir_o_detalhe_ao_clicar_na_linha(linha, ao_clicar_na_pessoa);
  }
  return linha;
}

/**
 * Busca as colunas do parâmetro na API.
 *
 * Recebe: endereco — "/api/empresa/colunas_da_consulta" ou "/api/banco/colunas_da_consulta".
 * Devolve: a lista de colunas, ou [] se a API não responder (a tela fica com as colunas de exemplo).
 */
async function buscar_colunas_do_parametro(endereco) {
  try {
    const resposta = await fetch(endereco);
    if (!resposta.ok) {
      return [];
    }
    return await resposta.json();
  } catch (erro) {
    return [];
  }
}

// ===== Só os obrigatórios na grade; o detalhe com tudo (ADR-143) =====

// O texto do botão da primeira coluna quando a pessoa não tem valor nesse campo (a linha continua abrindo o detalhe).
const TEXTO_DO_BOTAO_DO_DETALHE = "Ver detalhe";
// O título do grupo dos campos que o parâmetro deixou sem grupo (no detalhe, cada campo fica num grupo).
const GRUPO_SEM_NOME = "Outras informações";

/**
 * As colunas da grade: só os campos obrigatórios do parâmetro vigente, na ordem do layout.
 *
 * Recebe: colunas — todas as colunas do parâmetro ({campo, rotulo, grupo, tipo, obrigatorio, descricao}).
 * Devolve: a lista só com as obrigatórias. Ex.: no parâmetro de hoje (v7), CPF, Código cbo, Data admissão e Valor
 * renda. A escolha vem da marca "obrigatorio" do parâmetro: se o banco marcar mais um campo, ele entra sozinho.
 */
function colunas_obrigatorias(colunas) {
  const obrigatorias = [];
  for (const coluna of colunas) {
    // Só o campo marcado como obrigatório no parâmetro vai para a grade
    if (coluna.obrigatorio) {
      obrigatorias.push(coluna);
    }
  }
  return obrigatorias;
}

/**
 * O texto do botão que abre o detalhe, na primeira coluna da grade: o valor do campo do jeito que a pessoa lê, ou
 * "Ver detalhe" quando o campo veio vazio (a pessoa sempre tem como abrir o detalhe).
 *
 * Recebe: coluna; valor. Devolve: o texto.
 * Ex.: ({tipo: "CPF"}, "529.982.247-25") → "529.982.247-25"; ({tipo: "CPF"}, "") → "Ver detalhe".
 */
function texto_do_botao_do_detalhe(coluna, valor) {
  if (!valor) {
    return TEXTO_DO_BOTAO_DO_DETALHE;
  }
  return texto_do_valor(coluna, String(valor));
}

/**
 * A célula do primeiro campo da linha: o valor dentro de um botão que abre o detalhe da pessoa. É por ele que quem usa
 * o teclado abre o detalhe; com o mouse, a linha inteira abre (ver abrir_o_detalhe_ao_clicar_na_linha).
 *
 * Recebe: coluna; valor — o texto do campo (pode vir vazio); ao_clicar — a função que abre o detalhe.
 * Devolve: o <td>. Ex.: CPF "529.982.247-25" → o botão "529.982.247-25"; sem valor → o botão "Ver detalhe".
 */
function celula_com_botao_do_detalhe(coluna, valor, ao_clicar) {
  const celula = document.createElement("td");
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "botao-nome";
  // O texto do botão: o valor do jeito que a pessoa lê, ou "Ver detalhe" quando o campo veio vazio
  const texto_do_botao = texto_do_botao_do_detalhe(coluna, valor);
  let descricao_para_o_leitor = "sem " + coluna.rotulo;
  if (valor) {
    descricao_para_o_leitor = coluna.rotulo + " " + texto_do_botao;
  }
  botao.textContent = texto_do_botao;
  // O leitor de tela diz para que o botão serve. Ex.: "Ver o detalhe da pessoa (CPF 529.982.247-25)"
  botao.setAttribute("aria-label", "Ver o detalhe da pessoa (" + descricao_para_o_leitor + ")");
  botao.addEventListener("click", ao_clicar);
  celula.appendChild(botao);
  return celula;
}

/**
 * Faz a linha inteira de uma pessoa abrir o detalhe dela, com todas as informações.
 *
 * Recebe: linha — o <tr>; ao_clicar — a função que abre o detalhe. Devolve: nada.
 * O clique num botão, link ou campo de dentro da linha (ex.: "Apontar problema") faz só o que ele faz; e quem está
 * selecionando um texto da linha (ex.: para copiar o CPF) não abre nada.
 */
function abrir_o_detalhe_ao_clicar_na_linha(linha, ao_clicar) {
  // A classe muda o cursor e a cor ao passar o mouse (css/estilos.css): mostra que a linha abre algo
  linha.classList.add("linha-clicavel");
  linha.addEventListener("click", function (evento) {
    // O clique foi num controle de dentro da linha: ele cuida do próprio clique
    if (evento.target.closest("button, a, input, select, textarea, label")) {
      return;
    }
    // A pessoa está selecionando um texto da linha: não abre
    if (String(window.getSelection()) !== "") {
      return;
    }
    ao_clicar();
  });
}

/**
 * O nome de um campo no detalhe (o <dt>), com a marca "*" quando o campo é obrigatório no parâmetro.
 *
 * Recebe: coluna. Devolve: o <dt>. Passar o mouse mostra a descrição que o banco escreveu no parâmetro.
 */
function nome_do_detalhe(coluna) {
  const nome = document.createElement("dt");
  nome.textContent = coluna.rotulo;
  nome.title = coluna.descricao || "";
  if (coluna.obrigatorio) {
    const marca = document.createElement("span");
    marca.className = "marca-obrigatorio";
    marca.textContent = "*";
    // Leitor de tela: diz "obrigatório" em vez de "asterisco"
    marca.setAttribute("aria-label", "obrigatório");
    nome.appendChild(marca);
  }
  return nome;
}

/**
 * O valor de um campo no detalhe (o <dd>): o texto do jeito que a pessoa lê, ou "Informação não encontrada".
 *
 * Recebe: coluna; valor (pode vir vazio). Devolve: o <dd>, marcado com o nome do campo (data-campo-do-detalhe), para a
 * tela achar um valor depois (ex.: trocar o CPF pelo que o servidor mandou ao registrar a abertura).
 */
function valor_do_detalhe(coluna, valor) {
  const conteudo = document.createElement("dd");
  conteudo.dataset.campoDoDetalhe = coluna.campo;
  // Campo em branco: a mesma frase da grade, mais clara e em itálico
  if (!valor) {
    const sem_valor = document.createElement("span");
    sem_valor.className = "valor-nao-encontrado";
    sem_valor.textContent = TEXTO_SEM_VALOR;
    conteudo.appendChild(sem_valor);
    return conteudo;
  }
  conteudo.textContent = texto_do_valor(coluna, String(valor));
  return conteudo;
}

/**
 * Um grupo ainda vazio do detalhe (ex.: "Titular"): o quadro com o título e a lista onde os campos entram.
 *
 * Recebe: titulo. Devolve: o <section class="ficha-grupo">, com o <dl class="ficha-campos"> dentro.
 */
function secao_do_detalhe(titulo) {
  const secao = document.createElement("section");
  secao.className = "ficha-grupo";
  const titulo_do_grupo = document.createElement("h3");
  titulo_do_grupo.className = "ficha-grupo-titulo";
  titulo_do_grupo.textContent = titulo;
  const lista = document.createElement("dl");
  lista.className = "ficha-campos";
  secao.append(titulo_do_grupo, lista);
  return secao;
}

/**
 * Os grupos do detalhe de uma pessoa: TODOS os campos do parâmetro, juntados pelo grupo do parâmetro (Titular,
 * Endereço residencial, Renda...), na ordem em que os grupos aparecem no layout.
 *
 * Recebe: colunas — todas as colunas do parâmetro; valores — {campo: valor} da pessoa (campo que falta conta como
 * vazio). Devolve: a lista de <section>. O campo em branco aparece como "Informação não encontrada".
 * Ex.: ([{campo: "cpf", grupo: "Titular", ...}], {cpf: "529.982.247-25"}) → [o grupo "Titular", com o CPF].
 */
function grupos_do_detalhe(colunas, valores) {
  const nomes_dos_grupos = [];
  const secao_de_cada_grupo = {};
  for (const coluna of colunas) {
    // O grupo do campo no parâmetro (sem grupo, o de "Outras informações")
    const grupo = coluna.grupo || GRUPO_SEM_NOME;
    // Primeiro campo deste grupo: o quadro do grupo nasce, na ordem em que aparece no layout
    if (!secao_de_cada_grupo[grupo]) {
      secao_de_cada_grupo[grupo] = secao_do_detalhe(grupo);
      nomes_dos_grupos.push(grupo);
    }
    // O valor da pessoa neste campo (os valores podem não trazer o campo: conta como vazio)
    let valor = "";
    if (valores && valores[coluna.campo]) {
      valor = valores[coluna.campo];
    }
    const lista_do_grupo = secao_de_cada_grupo[grupo].querySelector("dl");
    lista_do_grupo.append(nome_do_detalhe(coluna), valor_do_detalhe(coluna, valor));
  }
  // Os quadros, na ordem dos grupos
  const secoes = [];
  for (const nome_do_grupo of nomes_dos_grupos) {
    secoes.push(secao_de_cada_grupo[nome_do_grupo]);
  }
  return secoes;
}

/**
 * A linha do detalhe que abre logo abaixo de uma pessoa, dentro da própria tabela (nas grades que já estão numa
 * janela, como o "Conferir e enviar"): todos os campos, agrupados.
 *
 * Recebe: colunas — todas as colunas do parâmetro; valores — {campo: valor}; quantas_colunas — quantas colunas a
 * tabela tem (a célula do detalhe ocupa a largura inteira). Devolve: o <tr class="linha-do-detalhe">.
 */
function linha_do_detalhe(colunas, valores, quantas_colunas) {
  const linha = document.createElement("tr");
  linha.className = "linha-do-detalhe";
  const celula = document.createElement("td");
  celula.colSpan = quantas_colunas;
  const grupos = document.createElement("div");
  grupos.className = "ficha-grupos";
  grupos.append(...grupos_do_detalhe(colunas, valores));
  celula.appendChild(grupos);
  linha.appendChild(celula);
  return linha;
}

/**
 * Abre ou fecha, logo abaixo da linha de uma pessoa, a linha do detalhe dela.
 *
 * Recebe: linha — o <tr> da pessoa; montar_o_detalhe — função que devolve a linha do detalhe (só é chamada para abrir).
 * Devolve: true se abriu; false se fechou.
 */
function alternar_detalhe_da_linha(linha, montar_o_detalhe) {
  const proxima = linha.nextElementSibling;
  // O detalhe já está aberto logo abaixo: fecha
  if (proxima && proxima.classList.contains("linha-do-detalhe")) {
    proxima.remove();
    return false;
  }
  // Fechado: abre logo abaixo da pessoa
  linha.after(montar_o_detalhe());
  return true;
}

/**
 * A linha de uma pessoa de um envio: um valor por campo obrigatório (ou "Informação não encontrada"). O clique na pessoa
 * abre, logo abaixo, todos os campos dela, agrupados, e no fim as "Informações sem rótulo", quando ela tem alguma
 * (ADR-143, Parte 1).
 *
 * Recebe: linha_da_lista — {linha, valores, informacoes_sem_rotulo} (a lista do envio, ou a prévia dele);
 * colunas — todas as colunas do parâmetro; colunas_da_grade — só as obrigatórias. Devolve: o <tr>.
 * É a mesma linha nas duas grades de pessoas de um envio: a do "Conferir a lista e enviar para o banco", em Acompanhar
 * cadastros, e a da aba "Funcionários", no resultado da leitura em Cadastrar funcionários.
 */
function linha_de_pessoa_do_envio(linha_da_lista, colunas, colunas_da_grade) {
  const tr = document.createElement("tr");
  // Abre (ou fecha) o detalhe da pessoa logo abaixo dela, com todos os campos
  const abrir_ou_fechar_o_detalhe = function () {
    alternar_detalhe_da_linha(tr, function () {
      const detalhe = linha_do_detalhe(colunas, linha_da_lista.valores, colunas_da_grade.length);
      // O que a IA guardou sem rótulo, no fim dos grupos: só quando há alguma (ADR-143, Parte 1)
      acrescentar_informacoes_sem_rotulo(detalhe.querySelector(".ficha-grupos"), linha_da_lista);
      return detalhe;
    });
  };
  // Um valor por campo da grade; o primeiro é o botão que abre o detalhe (o jeito de quem usa o teclado)
  let e_a_primeira_coluna = true;
  for (const coluna of colunas_da_grade) {
    const valor = linha_da_lista.valores[coluna.campo];
    if (e_a_primeira_coluna) {
      tr.append(celula_com_botao_do_detalhe(coluna, valor, abrir_ou_fechar_o_detalhe));
    } else {
      tr.append(celula_do_valor(coluna, valor));
    }
    e_a_primeira_coluna = false;
  }
  // A linha inteira abre o detalhe
  abrir_o_detalhe_ao_clicar_na_linha(tr, abrir_ou_fechar_o_detalhe);
  return tr;
}

/**
 * As iniciais de um nome, para o círculo do detalhe. Exemplo: "Ana Paula Souza" → "AS".
 *
 * Recebe: nome (pode vir vazio: o nome não é obrigatório no parâmetro de hoje). Devolve: uma ou duas letras, ou vazio.
 */
function iniciais_do_nome(nome) {
  const partes = String(nome || "").trim().split(" ");
  if (!partes[0]) {
    return "";
  }
  let iniciais = partes[0][0];
  // Com mais de um nome, junta a primeira letra do último.
  if (partes.length > 1) {
    iniciais = iniciais + partes[partes.length - 1][0];
  }
  return iniciais.toUpperCase();
}

/**
 * O título do detalhe de uma pessoa: o nome, se veio; senão, o CPF; senão, uma frase que diz que o nome não veio.
 *
 * Recebe: nome; cpf (os dois podem vir vazios: só o CPF é obrigatório no parâmetro de hoje). Devolve: o texto.
 * Ex.: ("", "529.982.247-25") → "CPF 529.982.247-25".
 */
function titulo_do_detalhe(nome, cpf) {
  if (nome) {
    return nome;
  }
  if (cpf) {
    return "CPF " + cpf;
  }
  return "Funcionário sem nome informado";
}

/**
 * Junta as partes de uma linha de resumo, pulando as vazias.
 *
 * Recebe: partes — lista de textos (vazio, null e undefined são pulados). Devolve: o texto.
 * Ex.: ["Analista", "", "CPF 529.982.247-25"] → "Analista · CPF 529.982.247-25".
 */
function juntar_partes_do_resumo(partes) {
  const preenchidas = [];
  for (const parte of partes) {
    if (parte) {
      preenchidas.push(parte);
    }
  }
  return preenchidas.join(" · ");
}

// ===== As informações sem rótulo (ADR-143, Parte 1) =====
// Quando a IA fica em dúvida entre dois ou mais campos OPCIONAIS do parâmetro (ex.: a coluna "C.E.P" pode ser o CEP
// residencial ou o comercial), ela não escolhe: guarda o valor como veio, sem rótulo, para o banco entender depois o
// que dá para reaproveitar. O servidor manda essa lista em cada pessoa, na chave
// "informacoes_sem_rotulo". O detalhe da pessoa mostra a lista numa seção própria, nas 5 listas de funcionários.
// Ela nunca aparece na grade, nunca vira o valor de um campo e não entra nas análises.

// O título da seção, no detalhe da pessoa.
const TITULO_DAS_INFORMACOES_SEM_ROTULO = "Informações sem rótulo";
// A frase que explica a seção para quem lê o detalhe.
const EXPLICACAO_DAS_INFORMACOES_SEM_ROTULO = "O Agente Interpretador encontrou estas informações, mas não teve " +
  "certeza de qual campo são. Elas ficam guardadas e não entram nas análises.";
// O nome que aparece no lugar da coluna quando o arquivo não deu nome a ela.
const COLUNA_SEM_NOME = "Coluna sem nome";

/**
 * As informações sem rótulo de uma pessoa, só as que têm um valor escrito.
 *
 * Recebe: pessoa — um item da API (pode vir sem a chave "informacoes_sem_rotulo", ou nem vir: null ou undefined).
 * Devolve: a lista [{coluna, valor, candidatos}], vazia quando não há nada.
 * Ex.: {informacoes_sem_rotulo: [{coluna: "C.E.P", valor: "01310-100", candidatos: [...]}]} → a lista com o "C.E.P";
 * {cpf: "529.982.247-25"} (sem a chave) → [].
 * Por que aceitar a falta da chave: a tela funciona igual antes de o servidor passar a mandá-la.
 */
function informacoes_sem_rotulo_da_pessoa(pessoa) {
  // Sem a pessoa, ou sem a lista: nada a mostrar
  if (!pessoa || !Array.isArray(pessoa.informacoes_sem_rotulo)) {
    return [];
  }
  const com_valor = [];
  for (const informacao of pessoa.informacoes_sem_rotulo) {
    // O valor como texto: um item sem valor (ou só com espaços) não tem o que mostrar
    let valor = "";
    if (informacao && informacao.valor !== null && informacao.valor !== undefined) {
      valor = String(informacao.valor).trim();
    }
    if (valor !== "") {
      com_valor.push(informacao);
    }
  }
  return com_valor;
}

/**
 * Os campos que a IA indicou para uma informação sem rótulo, numa frase: "A", "A ou B", "A, B ou C".
 *
 * Recebe: candidatos — [{campo, rotulo}] (o rótulo é o nome que a pessoa lê; sem ele, vale o nome técnico do campo).
 * Devolve: o texto, ou "" sem candidatos.
 * Ex.: [{campo: "cep_residencial", rotulo: "CEP residencial"}, {campo: "cep_comercial", rotulo: "CEP comercial"}] →
 * "CEP residencial ou CEP comercial".
 */
function texto_dos_candidatos_sem_rotulo(candidatos) {
  const nomes = [];
  for (const candidato of candidatos || []) {
    // O rótulo legível do campo; sem ele, o nome técnico
    let nome = "";
    if (candidato) {
      nome = candidato.rotulo || candidato.campo || "";
    }
    if (nome) {
      nomes.push(nome);
    }
  }
  // Nenhum ou um só: o próprio nome (ou nada)
  if (nomes.length <= 1) {
    return nomes.join("");
  }
  // Dois ou mais: vírgulas entre os primeiros e "ou" antes do último
  const ultimo_nome = nomes.pop();
  return nomes.join(", ") + " ou " + ultimo_nome;
}

/**
 * A linha de uma informação sem rótulo: a coluna do arquivo, o valor como veio e os campos que ela pode ser.
 *
 * Recebe: informacao — {coluna, valor, candidatos}. Devolve: o <li>.
 * Ex.: {coluna: "C.E.P", valor: "01310-100", candidatos: [CEP residencial, CEP comercial]} →
 * "C.E.P: 01310-100 · pode ser: CEP residencial ou CEP comercial".
 * O valor vem do arquivo da empresa: ele é escrito como texto (textContent), nunca como HTML.
 */
function linha_da_informacao_sem_rotulo(informacao) {
  const linha = document.createElement("li");
  // O nome da coluna no arquivo, em destaque
  const coluna = document.createElement("strong");
  coluna.textContent = informacao.coluna || COLUNA_SEM_NOME;
  linha.appendChild(coluna);
  // O valor, como veio do arquivo, sem conversão
  let texto = ": " + String(informacao.valor);
  // Os campos que a IA indicou (sem nenhum, a linha fica só com o valor)
  const candidatos = texto_dos_candidatos_sem_rotulo(informacao.candidatos);
  if (candidatos) {
    texto = texto + " · pode ser: " + candidatos;
  }
  linha.appendChild(document.createTextNode(texto));
  return linha;
}

/**
 * A seção "Informações sem rótulo" do detalhe de uma pessoa: o título, a frase que explica e uma linha por informação.
 *
 * Recebe: pessoa — um item da API. Devolve: o <section>, ou null quando a pessoa não tem nenhuma informação sem rótulo
 * (sem a chave, ou com a lista vazia): aí a seção não aparece.
 */
function secao_das_informacoes_sem_rotulo(pessoa) {
  const informacoes = informacoes_sem_rotulo_da_pessoa(pessoa);
  if (informacoes.length === 0) {
    return null;
  }
  // O quadro, no mesmo jeito dos grupos do detalhe, mas com a borda tracejada (css/estilos.css): não é um campo
  const secao = document.createElement("section");
  secao.className = "ficha-grupo ficha-grupo-sem-rotulo";
  // A marca para as telas e os roteiros de teste acharem a seção
  secao.dataset.informacoesSemRotulo = "";
  const titulo = document.createElement("h3");
  titulo.className = "ficha-grupo-titulo";
  titulo.textContent = TITULO_DAS_INFORMACOES_SEM_ROTULO;
  const explicacao = document.createElement("p");
  explicacao.className = "nota-sem-rotulo";
  explicacao.textContent = EXPLICACAO_DAS_INFORMACOES_SEM_ROTULO;
  // Uma linha por informação, na ordem em que o servidor mandou
  const lista = document.createElement("ul");
  lista.className = "lista-sem-rotulo";
  for (const informacao of informacoes) {
    lista.appendChild(linha_da_informacao_sem_rotulo(informacao));
  }
  secao.append(titulo, explicacao, lista);
  return secao;
}

/**
 * Acrescenta ao detalhe de uma pessoa a seção "Informações sem rótulo", se ela tiver alguma.
 *
 * Recebe: lugar — onde os grupos do detalhe ficam (ex.: o <div class="ficha-grupos">); pessoa — o item da API.
 * Devolve: nada. Sem informação sem rótulo, o detalhe fica como está.
 */
function acrescentar_informacoes_sem_rotulo(lugar, pessoa) {
  const secao = secao_das_informacoes_sem_rotulo(pessoa);
  if (secao) {
    lugar.appendChild(secao);
  }
}
