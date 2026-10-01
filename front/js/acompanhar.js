/*
  acompanhar.js — dados de exemplo e interações da aba "Acompanhar cadastros".

  Para que serve:
    - monta a tabela de funcionários a partir da lista FUNCIONARIOS_DA_AURORA (dados 100% fictícios);
    - faz a busca (nome, CPF, matrícula ou cargo) e os filtros (situação e unidade), com o "Limpar filtros";
    - abre a ficha completa de um funcionário numa janela, com os campos agrupados como no layout do banco;
    - baixa a lista que está na tela, em CSV (abre no Excel);
    - mostra as pendências com o valor que o arquivo trouxe e a conversa com o agente, que é o jeito de resolvê-las
      (js/assistente_de_correcao.js); o rodapé da lista tem os dois botões de
      descartar a leitura (do arquivo do filtro). Os cartões da lista são compactos e a conversa abre no painel do
      lado (js/painel_da_conversa.js; ADR-138);
    - destaca na grade o valor que acabou de mudar (pela conversa, pelo "para todos" ou pelo Desfazer; ADR-138);
    - mostra os envios 5 por vez ("Mostrar mais envios") e abre ou fecha todos de uma vez;
    - quando o banco devolve só algumas pessoas (ADR-121): a etapa devolvida em laranja, o bloco "Idas e voltas com o
      banco" embaixo da linha do tempo e, no envio de devolução, a linha de onde ele veio.

  No sistema real, a lista viria do banco de dados (tabela funcionarios_homologados e os envios em andamento),
  sempre filtrada pela empresa de quem está logado. Aqui ela está escrita à mão só para desenhar a tela.
  Ela traz 20 pessoas como amostra das 338 da Aurora (312 cadastradas, 24 em análise e 2 pendentes).

  Arquivos enviados NÃO ficam guardados nesta versão: no lugar
  deles, cada funcionário mostra quando foi incluído e por qual usuário do RH (colunas "Incluído").

  A conta de cada funcionário (agência, número e data de abertura) aparece na tabela, na ficha e no download: é
  nela que a empresa paga o salário, e o funcionário autoriza isso ao abrir a conta (ADR-102).
*/

// ============ DADOS DE EXEMPLO ============

// As unidades da Aurora, com o endereço comercial de cada uma (vai para a ficha).
const UNIDADES_DA_AURORA = {
  "Fábrica · Campinas": { codigo: "AUR-01", endereco: "Rod. Anhanguera, km 98 · Distrito Industrial · Campinas/SP · 13069-000" },
  "Centro de distribuição · Jundiaí": { codigo: "AUR-02", endereco: "Av. Antonio Frederico Ozanam, 5200 · Jundiaí/SP · 13214-206" },
  "Escritório · São Paulo": { codigo: "AUR-03", endereco: "Av. das Nações Unidas, 12901 · Brooklin · São Paulo/SP · 04578-910" },
};

// CNPJ fictício da Aurora Alimentos Ltda. (EMP001 da base sintética).
const CNPJ_DA_AURORA = "12.345.678/0001-95";

// Os funcionários de exemplo. Cada um traz os campos mais usados do layout; a ficha completa os demais.
const FUNCIONARIOS_DA_AURORA = [
  { nome: "Ana Beatriz Souza", cpf: "321.654.987-01", matricula: "001245", cargo: "Auxiliar de produção", unidade: "Fábrica · Campinas", admissao: "05/08/2026", salario: 2450.00, nascimento: "14/03/1998", sexo: "Feminino", estado_civil: "Solteira", celular: "(19) 98812-4410", email: "ana.souza@email.com", bairro: "Jardim Proença", cidade: "Campinas/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Bruno Henrique Alves", cpf: "456.123.789-22", matricula: "001246", cargo: "Operador de máquinas", unidade: "Fábrica · Campinas", admissao: "05/08/2026", salario: 3180.00, nascimento: "02/11/1991", sexo: "Masculino", estado_civil: "Casado", celular: "(19) 99745-2031", email: "bruno.alves@email.com", bairro: "Vila Industrial", cidade: "Campinas/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Camila Ferreira Rocha", cpf: "789.456.123-33", matricula: "001247", cargo: "Técnica de qualidade", unidade: "Fábrica · Campinas", admissao: "05/08/2026", salario: 4120.00, nascimento: "21/07/1993", sexo: "Feminino", estado_civil: "Casada", celular: "(19) 98133-7720", email: "", bairro: "Taquaral", cidade: "Campinas/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Diego Martins Pereira", cpf: "147.258.369-44", matricula: "001248", cargo: "Líder de produção", unidade: "Fábrica · Campinas", admissao: "05/08/2026", salario: 5350.00, nascimento: "30/01/1987", sexo: "Masculino", estado_civil: "Casado", celular: "(19) 99201-5588", email: "diego.pereira@email.com", bairro: "Cambuí", cidade: "Campinas/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Eduarda Lima Castro", cpf: "258.369.147-55", matricula: "001249", cargo: "Conferente", unidade: "Centro de distribuição · Jundiaí", admissao: "05/08/2026", salario: 2780.00, nascimento: "09/09/2000", sexo: "Feminino", estado_civil: "Solteira", celular: "(11) 98456-0192", email: "eduarda.castro@email.com", bairro: "Vila Arens", cidade: "Jundiaí/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Felipe Augusto Ramos", cpf: "369.147.258-66", matricula: "001250", cargo: "Motorista", unidade: "Centro de distribuição · Jundiaí", admissao: "05/08/2026", salario: 3420.00, nascimento: "17/05/1984", sexo: "Masculino", estado_civil: "Divorciado", celular: "(11) 99310-8874", email: "", bairro: "Anhangabaú", cidade: "Jundiaí/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Gabriela Nunes Teixeira", cpf: "951.753.852-77", matricula: "001251", cargo: "Analista de logística", unidade: "Centro de distribuição · Jundiaí", admissao: "05/08/2026", salario: 5900.00, nascimento: "25/12/1995", sexo: "Feminino", estado_civil: "Solteira", celular: "(11) 98877-3345", email: "gabriela.teixeira@email.com", bairro: "Eloy Chaves", cidade: "Jundiaí/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Henrique Duarte Melo", cpf: "753.951.456-88", matricula: "001252", cargo: "Assistente administrativo", unidade: "Escritório · São Paulo", admissao: "05/08/2026", salario: 3050.00, nascimento: "08/04/1999", sexo: "Masculino", estado_civil: "Solteiro", celular: "(11) 97654-2210", email: "henrique.melo@email.com", bairro: "Vila Mariana", cidade: "São Paulo/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Isabela Moura Campos", cpf: "852.456.951-99", matricula: "001253", cargo: "Analista de RH", unidade: "Escritório · São Paulo", admissao: "05/08/2026", salario: 6200.00, nascimento: "12/10/1990", sexo: "Feminino", estado_civil: "Casada", celular: "(11) 99876-1123", email: "isabela.campos@email.com", bairro: "Moema", cidade: "São Paulo/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "João Pedro Barbosa", cpf: "159.357.486-10", matricula: "001254", cargo: "Coordenador financeiro", unidade: "Escritório · São Paulo", admissao: "05/08/2026", salario: 11800.00, nascimento: "03/06/1982", sexo: "Masculino", estado_civil: "Casado", celular: "(11) 98123-4567", email: "joao.barbosa@email.com", bairro: "Pinheiros", cidade: "São Paulo/SP", situacao: "Cadastrado", tipo_de_envio: "Carga inicial", incluido_em: "01/08/2026", incluido_por: "Marina Costa" },
  { nome: "Larissa Gomes Pinto", cpf: "357.159.684-21", matricula: "001498", cargo: "Auxiliar de produção", unidade: "Fábrica · Campinas", admissao: "01/09/2026", salario: 2450.00, nascimento: "19/02/2002", sexo: "Feminino", estado_civil: "Solteira", celular: "(19) 99456-7788", email: "larissa.pinto@email.com", bairro: "São Bernardo", cidade: "Campinas/SP", situacao: "Cadastrado", tipo_de_envio: "Inclusão", incluido_em: "02/09/2026", incluido_por: "Paulo Andrade" },
  { nome: "Marcelo Vieira Costa", cpf: "486.159.357-32", matricula: "001499", cargo: "Operador de máquinas", unidade: "Fábrica · Campinas", admissao: "01/09/2026", salario: 3180.00, nascimento: "11/08/1989", sexo: "Masculino", estado_civil: "Casado", celular: "(19) 98765-0099", email: "", bairro: "Jardim Chapadão", cidade: "Campinas/SP", situacao: "Cadastrado", tipo_de_envio: "Inclusão", incluido_em: "02/09/2026", incluido_por: "Paulo Andrade" },
  { nome: "Natália Ribeiro Dias", cpf: "684.357.159-43", matricula: "001500", cargo: "Conferente", unidade: "Centro de distribuição · Jundiaí", admissao: "01/09/2026", salario: 2780.00, nascimento: "28/03/1997", sexo: "Feminino", estado_civil: "Solteira", celular: "(11) 99021-3344", email: "natalia.dias@email.com", bairro: "Vila Rio Branco", cidade: "Jundiaí/SP", situacao: "Cadastrado", tipo_de_envio: "Inclusão", incluido_em: "02/09/2026", incluido_por: "Paulo Andrade" },
  { nome: "Otávio Cardoso Lopes", cpf: "246.813.579-54", matricula: "001521", cargo: "Auxiliar de produção", unidade: "Fábrica · Campinas", admissao: "22/09/2026", salario: 2450.00, nascimento: "07/12/2003", sexo: "Masculino", estado_civil: "Solteiro", celular: "(19) 99888-1020", email: "otavio.lopes@email.com", bairro: "Jardim do Lago", cidade: "Campinas/SP", situacao: "Em análise", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
  { nome: "Patrícia Azevedo Reis", cpf: "813.579.246-65", matricula: "001522", cargo: "Analista de logística", unidade: "Centro de distribuição · Jundiaí", admissao: "22/09/2026", salario: 5900.00, nascimento: "15/01/1994", sexo: "Feminino", estado_civil: "Casada", celular: "(11) 98345-6612", email: "patricia.reis@email.com", bairro: "Engordadouro", cidade: "Jundiaí/SP", situacao: "Em análise", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
  { nome: "Rodrigo Tavares Silva", cpf: "579.246.813-76", matricula: "001523", cargo: "Motorista", unidade: "Centro de distribuição · Jundiaí", admissao: "22/09/2026", salario: 3420.00, nascimento: "23/09/1986", sexo: "Masculino", estado_civil: "Casado", celular: "(11) 99654-7743", email: "", bairro: "Ponte São João", cidade: "Jundiaí/SP", situacao: "Em análise", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
  { nome: "Sofia Mendes Araújo", cpf: "135.792.468-87", matricula: "001524", cargo: "Assistente administrativo", unidade: "Escritório · São Paulo", admissao: "22/09/2026", salario: 3050.00, nascimento: "04/05/2001", sexo: "Feminino", estado_civil: "Solteira", celular: "(11) 97123-9087", email: "sofia.araujo@email.com", bairro: "Saúde", cidade: "São Paulo/SP", situacao: "Em análise", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
  { nome: "Carlos Eduardo Nunes", cpf: "792.468.135-98", matricula: "001525", cargo: "Auxiliar de produção", unidade: "Fábrica · Campinas", admissao: "22/09/2026", salario: 48000.00, nascimento: "16/08/1996", sexo: "Masculino", estado_civil: "Solteiro", celular: "(19) 98222-6061", email: "carlos.nunes@email.com", bairro: "Vila Teixeira", cidade: "Campinas/SP", situacao: "Em análise", pendencia: "O banco pediu confirmação do salário", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
  { nome: "Rafael Moreira Lima", cpf: "***.482.917-**", matricula: "001526", cargo: "Operador de máquinas", unidade: "Fábrica · Campinas", admissao: "22/09/2026", salario: 3180.00, nascimento: "10/10/1992", sexo: "Masculino", estado_civil: "Casado", celular: "(19) 99333-4455", email: "rafael.lima@email.com", bairro: "Bonfim", cidade: "Campinas/SP", situacao: "Pendente", pendencia: "CPF inválido: confira no documento", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
  { nome: "Juliana Castro Pires", cpf: "468.135.792-09", matricula: "001527", cargo: "Técnica de qualidade", unidade: "Fábrica · Campinas", admissao: "12/11/2026", salario: 4120.00, nascimento: "01/02/1995", sexo: "Feminino", estado_civil: "Solteira", celular: "(19) 98444-5566", email: "juliana.pires@email.com", bairro: "Guanabara", cidade: "Campinas/SP", situacao: "Pendente", pendencia: "Data de admissão no futuro", tipo_de_envio: "Inclusão", incluido_em: "24/09/2026", incluido_por: "Marina Costa" },
];

// Quantas pessoas a Aurora tem no total (a tabela mostra só a amostra acima). Com os dados de verdade (API),
// vira o tamanho da lista que o servidor devolveu.
let total_de_funcionarios_da_empresa = 338;

// Verdadeiro quando a tabela está com os funcionários de verdade, vindos da API (e não com a amostra acima).
let usando_dados_de_verdade = false;

// As colunas da grade vindas do parâmetro vigente do banco (ADR-111): uma por campo OBRIGATÓRIO (ADR-143), com rótulo,
// grupo e a marca. Vazia enquanto a página mostra a amostra do protótipo (aberta sem servidor).
let colunas_do_parametro = [];
// Todas as colunas do parâmetro vigente, para a ficha: o clique numa pessoa mostra todos os campos (ADR-143).
let todas_as_colunas_do_parametro = [];


// Quantos envios aparecem por vez (uma empresa pode ter centenas; a página não pode virar um rolo sem fim).
const ENVIOS_POR_VEZ = 5;
// Quantos envios estão aparecendo agora (cresce de 5 em 5 com "Mostrar mais envios").
let envios_aparecendo = ENVIOS_POR_VEZ;
// Com servidor: quantos envios a empresa tem (a tela recebe só uma página por vez; null = exemplo, sem servidor).
let total_de_envios_no_servidor = null;

// ============ FORMATAÇÃO ============

/**
 * Escreve um valor em reais, no padrão brasileiro.
 *
 * Recebe: valor — número (ex.: 2450).
 * Devolve: o texto "R$ 2.450,00".
 */
function formatar_em_reais(valor) {
  // toLocaleString com "pt-BR" põe o ponto do milhar e a vírgula dos centavos.
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}


/**
 * A classe de cor do selo de cada situação.
 *
 * Recebe: situacao — "Cadastrado", "Em análise" ou "Pendente".
 * Devolve: a classe do selo (verde, azul da marca ou laranja).
 */
function classe_do_selo(situacao) {
  // Cadastrado = concluído (verde).
  if (situacao === "Cadastrado") {
    return "selo-sucesso";
  }
  // Em análise = aguardando o banco.
  if (situacao === "Em análise") {
    return "selo-marca";
  }
  // Pendente = a empresa precisa agir.
  return "selo-atencao";
}

// ============ BUSCA E FILTROS ============

/**
 * Só os números de um texto (tira pontos, traço, espaços e letras).
 *
 * Recebe: texto (pode vir vazio, null ou undefined). Devolve: o texto só com os números.
 * Exemplo: "529.982.247-25" → "52998224725"; "Ana" → "".
 */
function somente_os_numeros_do_texto(texto) {
  const numeros = [];
  for (const caractere of String(texto || "")) {
    // Um caractere de "0" a "9" é número; o resto sai
    if (caractere >= "0" && caractere <= "9") {
      numeros.push(caractere);
    }
  }
  return numeros.join("");
}

/**
 * Diz se um funcionário aparece com a busca e os filtros escolhidos.
 *
 * Recebe: funcionario — um item de FUNCIONARIOS_DA_AURORA.
 * Devolve: true se ele deve aparecer na tabela.
 * A busca é sempre pelo CPF: valem só os números, com ou sem pontos e traço (ex.: "529.982" e "529982" acham o
 * "529.982.247-25"); um texto sem número nenhum não é um CPF e não acha ninguém. O filtro de unidade está oculto nesta
 * versão: com a lista escondida, ele fica em "Todas as unidades" e não tira ninguém.
 */
function funcionario_aparece(funcionario) {
  // O que foi digitado na busca, e só os números dele.
  const texto_buscado = document.querySelector("[data-busca]").value.trim();
  const numeros_buscados = somente_os_numeros_do_texto(texto_buscado);
  // A situação e a unidade escolhidas nas listas (vazio = todas).
  const situacao_escolhida = document.querySelector("[data-filtro-situacao]").value;
  const unidade_escolhida = document.querySelector("[data-filtro-unidade]").value;

  // Com algo digitado, a busca procura no CPF.
  if (texto_buscado !== "") {
    // Um texto sem número nenhum não é um CPF: ninguém aparece.
    if (numeros_buscados === "") {
      return false;
    }
    // Os números digitados precisam estar dentro dos números do CPF.
    if (!somente_os_numeros_do_texto(funcionario.cpf).includes(numeros_buscados)) {
      return false;
    }
  }
  // Filtro de situação.
  if (situacao_escolhida && funcionario.situacao !== situacao_escolhida) {
    return false;
  }
  // Filtro de unidade.
  if (unidade_escolhida && funcionario.unidade !== unidade_escolhida) {
    return false;
  }
  // Passou em tudo.
  return true;
}

/**
 * Acrescenta uma célula à linha da tabela, com um texto principal e, se houver, um texto de apoio embaixo.
 *
 * Recebe: linha — o <tr>; texto_principal — o que aparece em cima;
 *         texto_de_apoio — o que aparece embaixo, menor e em cinza ("" = nada).
 * Devolve: nada; a célula entra no fim da linha.
 * Exemplo: acrescentar_celula(linha, "01/08/2026", "por Marina Costa").
 */
function acrescentar_celula(linha, texto_principal, texto_de_apoio) {
  // A célula com o texto principal.
  const celula = document.createElement("td");
  celula.textContent = texto_principal;
  // O texto de apoio vai numa linha própria, com a classe que o deixa menor e cinza.
  if (texto_de_apoio) {
    celula.className = "celula-duas-linhas";
    const apoio = document.createElement("span");
    apoio.textContent = texto_de_apoio;
    celula.appendChild(apoio);
  }
  linha.appendChild(celula);
}

/**
 * Monta a linha da tabela de um funcionário.
 *
 * Recebe: funcionario — um item de FUNCIONARIOS_DA_AURORA.
 * Devolve: o elemento <tr> pronto para entrar na tabela.
 */
function montar_linha(funcionario) {
  // Com as colunas do parâmetro (dados de verdade), a linha tem uma célula por campo (ADR-111).
  if (colunas_do_parametro.length > 0) {
    return montar_linha_do_parametro(funcionario);
  }
  // A linha da tabela.
  const linha = document.createElement("tr");
  // O nome é um botão: clicar (ou apertar Enter nele) abre a ficha completa.
  const celula_do_nome = document.createElement("td");
  const botao_do_nome = document.createElement("button");
  botao_do_nome.type = "button";
  botao_do_nome.className = "botao-nome";
  botao_do_nome.textContent = funcionario.nome;
  botao_do_nome.addEventListener("click", function () {
    abrir_ficha(funcionario);
  });
  celula_do_nome.appendChild(botao_do_nome);
  linha.appendChild(celula_do_nome);

  // CPF (inteiro: a empresa vê os dados que ela enviou) e matrícula: texto simples.
  acrescentar_celula(linha, funcionario.cpf, "");
  acrescentar_celula(linha, funcionario.matricula, "");
  // Cargo em cima e unidade embaixo (duas informações numa coluna só, para a tabela caber na tela).
  acrescentar_celula(linha, funcionario.cargo, funcionario.unidade);
  // Admissão e salário: texto simples.
  acrescentar_celula(linha, funcionario.admissao, "");
  acrescentar_celula(linha, formatar_em_reais(funcionario.salario), "");
  // Conta, incluído e situação: as mesmas colunas finais da grade do parâmetro.
  acrescentar_colunas_da_consulta(linha, funcionario);
  return linha;
}

/**
 * Acrescenta as três colunas que não vêm do parâmetro: a conta no banco, quem incluiu e quando, e a situação.
 *
 * Recebe: linha — o <tr>; funcionario. Devolve: nada; as células entram no fim da linha.
 */
function acrescentar_colunas_da_consulta(linha, funcionario) {
  // A conta no banco: agência e número em cima, a data de abertura embaixo (ou "Ainda não abriu").
  if (funcionario.conta) {
    acrescentar_celula(linha, "Ag. " + funcionario.agencia + " · " + funcionario.conta, "aberta em " + funcionario.conta_aberta_em);
  } else {
    acrescentar_celula(linha, "Ainda não abriu", "");
  }
  // Quando e por quem o funcionário foi incluído.
  acrescentar_celula(linha, funcionario.incluido_em, "por " + funcionario.incluido_por);

  // A última coluna: o selo da situação (e o aviso de pendência, se houver).
  const celula_da_situacao = document.createElement("td");
  const selo = document.createElement("span");
  selo.className = "selo selo-pequeno " + classe_do_selo(funcionario.situacao);
  selo.textContent = funcionario.situacao;
  celula_da_situacao.appendChild(selo);
  // Quem tem pendência ganha um ponto laranja ao lado, com a explicação ao passar o mouse.
  if (funcionario.pendencia) {
    const aviso = document.createElement("span");
    aviso.className = "aviso-pendencia";
    aviso.title = funcionario.pendencia;
    aviso.textContent = "!";
    aviso.setAttribute("aria-label", "Pendência: " + funcionario.pendencia);
    celula_da_situacao.appendChild(aviso);
  }
  linha.appendChild(celula_da_situacao);
}

// ===== Grade com todos os campos do parâmetro (ADR-111; a montagem comum fica em js/grade_do_parametro.js) =====

/**
 * Monta a linha de um funcionário com uma célula por campo obrigatório do parâmetro (ADR-143): o valor identificado, ou
 * "Informação não encontrada" quando o campo veio vazio. A linha inteira abre a ficha, com todos os campos; o valor
 * do primeiro campo é o botão que abre pelo teclado.
 *
 * Recebe: funcionario (com funcionario.campos, os campos vindos da API). Devolve: o <tr>.
 */
function montar_linha_do_parametro(funcionario) {
  // A montagem comum (js/grade_do_parametro.js): Situação primeiro, os campos, a Conta e o Incluído.
  const linha = montar_linha_de_funcionario(funcionario.campos, colunas_do_parametro, function () {
    abrir_ficha(funcionario);
  });
  // O valor que acabou de mudar (pela conversa com a IA, pelo "para todos" ou pelo Desfazer) fica destacado
  destacar_as_celulas_que_mudaram(linha, funcionario);
  return linha;
}

// ===== O valor que acabou de mudar, destacado na grade (ADR-138) =====

// Por quanto tempo a célula que mudou fica destacada: 20 segundos, o bastante para a pessoa rolar até a grade.
const TEMPO_DO_DESTAQUE_DA_CELULA = 20000;
// As células que acabaram de mudar, cada uma pela chave "pessoa|campo", com a hora (em milissegundos) em que o
// destaque acaba. Ex.: {"env-1|cpf|529.982.247-25|cpf": 1759150000000}.
let celulas_que_mudaram = {};

/**
 * As chaves que acham a mesma pessoa na lista de antes e na de agora: o envio com o CPF e o envio com o nome.
 *
 * Recebe: funcionario — um item de FUNCIONARIOS_DA_AURORA. Devolve: a lista de chaves (vazia sem CPF e sem nome).
 * Por que duas: a correção pode ter mudado o próprio CPF (aí o nome acha a pessoa) ou o próprio nome (aí o CPF acha).
 * Ex.: {envio: "env-1", cpf: "529.982.247-25", nome: "Ana Lima"} → ["env-1|cpf|529.982.247-25", "env-1|nome|Ana Lima"].
 */
function chaves_da_pessoa(funcionario) {
  const envio = funcionario.envio || "";
  const chaves = [];
  if (funcionario.cpf) {
    chaves.push(envio + "|cpf|" + funcionario.cpf);
  }
  if (funcionario.nome) {
    chaves.push(envio + "|nome|" + funcionario.nome);
  }
  return chaves;
}

/**
 * Cada pessoa de uma lista pelas chaves dela (ver chaves_da_pessoa).
 *
 * Recebe: funcionarios — a lista. Devolve: um Map {chave: funcionario}. A chave de duas pessoas ao mesmo tempo (ex.:
 * dois homônimos no mesmo envio) fica com null: ela não serve para achar ninguém.
 */
function pessoas_pelas_chaves(funcionarios) {
  const pessoas = new Map();
  for (const funcionario of funcionarios) {
    for (const chave of chaves_da_pessoa(funcionario)) {
      // Repetida: não serve para achar ninguém
      if (pessoas.has(chave)) {
        pessoas.set(chave, null);
      } else {
        pessoas.set(chave, funcionario);
      }
    }
  }
  return pessoas;
}

/**
 * A mesma pessoa na lista de antes, por qualquer uma das chaves dela.
 *
 * Recebe: funcionario (da lista de agora); pessoas_de_antes (ver pessoas_pelas_chaves). Devolve: a pessoa, ou null
 * (pessoa nova, ou que não dá para achar com certeza).
 */
function a_mesma_pessoa_antes(funcionario, pessoas_de_antes) {
  for (const chave of chaves_da_pessoa(funcionario)) {
    const achada = pessoas_de_antes.get(chave);
    if (achada) {
      return achada;
    }
  }
  return null;
}

/**
 * O valor de um campo em texto, para comparar o de antes com o de agora (vazio e ausente contam igual).
 *
 * Recebe: valor. Devolve: o texto. Ex.: null → ""; 2450 → "2450".
 */
function valor_para_comparar(valor) {
  if (valor === null || valor === undefined) {
    return "";
  }
  return String(valor);
}

/**
 * Compara a lista de antes com a de agora e guarda as células que mudaram, para a grade destacar.
 *
 * Recebe: funcionarios_de_antes (vazia na primeira carga: nada é destacado); funcionarios_de_agora. Devolve: nada.
 * Sem nenhuma mudança (ex.: a atualização ao voltar para a aba), os destaques de antes continuam até acabar o tempo.
 */
function marcar_as_celulas_que_mudaram(funcionarios_de_antes, funcionarios_de_agora) {
  const pessoas_de_antes = pessoas_pelas_chaves(funcionarios_de_antes);
  const fim_do_destaque = Date.now() + TEMPO_DO_DESTAQUE_DA_CELULA;
  const mudaram_agora = {};
  let alguma_mudou = false;
  for (const funcionario of funcionarios_de_agora) {
    const antes = a_mesma_pessoa_antes(funcionario, pessoas_de_antes);
    // Pessoa nova, ou que não dá para achar: nada a comparar
    if (!antes) {
      continue;
    }
    // Cada campo do parâmetro: mudou, vira destaque
    for (const coluna of colunas_do_parametro) {
      const valor_de_antes = valor_para_comparar(antes.campos[coluna.campo]);
      const valor_de_agora = valor_para_comparar(funcionario.campos[coluna.campo]);
      if (valor_de_antes !== valor_de_agora) {
        mudaram_agora[chaves_da_pessoa(funcionario)[0] + "|" + coluna.campo] = fim_do_destaque;
        alguma_mudou = true;
      }
    }
  }
  // Houve mudança: os destaques passam a ser os dela
  if (alguma_mudou) {
    celulas_que_mudaram = mudaram_agora;
  }
}

/**
 * Destaca, na linha de um funcionário, as células cujo valor acabou de mudar (fundo amarelo que se apaga devagar).
 *
 * Recebe: linha — o <tr> montado; funcionario. Devolve: nada.
 * A linha tem a Situação na primeira célula e, depois, uma célula por coluna do parâmetro, na mesma ordem.
 */
function destacar_as_celulas_que_mudaram(linha, funcionario) {
  const chaves = chaves_da_pessoa(funcionario);
  // Sem CPF e sem nome, não há como saber se a pessoa mudou
  if (chaves.length === 0) {
    return;
  }
  const agora = Date.now();
  for (const [posicao, coluna] of colunas_do_parametro.entries()) {
    const fim_do_destaque = celulas_que_mudaram[chaves[0] + "|" + coluna.campo];
    // Não mudou, ou o destaque já acabou
    if (!fim_do_destaque || fim_do_destaque <= agora) {
      continue;
    }
    // + 1: a primeira célula é a da Situação
    const celula = linha.children[posicao + 1];
    celula.classList.add("celula-que-mudou");
    celula.dataset.celulaQueMudou = coluna.campo;
    celula.title = "Valor atualizado agora";
  }
}

/**
 * Busca na API as colunas do parâmetro vigente e monta o cabeçalho da grade (com a legenda).
 *
 * Recebe: nada. Devolve: nada. Se a API não responder, a grade fica com as colunas da amostra.
 */
async function carregar_colunas_do_parametro() {
  // Todas as colunas vão para a ficha; a grade fica só com as obrigatórias (pela marca do parâmetro, nunca por uma
  // lista escrita aqui)
  todas_as_colunas_do_parametro = await buscar_colunas_do_parametro("/api/empresa/colunas_da_consulta");
  colunas_do_parametro = colunas_obrigatorias(todas_as_colunas_do_parametro);
  if (colunas_do_parametro.length === 0) {
    return;
  }
  // Situação primeiro; Conta e Incluído no fim.
  montar_cabecalho_da_grade(document.querySelector("[data-cabeca-tabela]"), colunas_do_parametro, ["Situação"],
    BLOCOS_FINAIS_DOS_FUNCIONARIOS);
  // A legenda da grade aparece junto com ela: a marca de obrigatório e a frase do vazio (o que é cada status fica no
  // "i" em cima da grade, js/legenda_dos_status.js).
  document.querySelector("[data-legenda-grade]").hidden = false;
}

/**
 * Refaz a tabela com quem aparece nos filtros atuais e atualiza o contador.
 *
 * Recebe: nada. Devolve: nada (só muda a tela).
 */
function atualizar_tabela() {
  // O corpo da tabela é esvaziado e preenchido de novo.
  const corpo_da_tabela = document.querySelector("[data-corpo-tabela]");
  corpo_da_tabela.innerHTML = "";
  // Conta quantos aparecem.
  let quantidade_na_tela = 0;
  for (const funcionario of FUNCIONARIOS_DA_AURORA) {
    if (funcionario_aparece(funcionario)) {
      corpo_da_tabela.appendChild(montar_linha(funcionario));
      quantidade_na_tela = quantidade_na_tela + 1;
    }
  }
  // Frase do contador, acima da tabela ("amostra do protótipo" só quando não são os dados de verdade).
  let frase_do_contador = "Mostrando " + quantidade_na_tela + " de " + total_de_funcionarios_da_empresa + " funcionários";
  if (!usando_dados_de_verdade) {
    frase_do_contador = frase_do_contador + " (amostra do protótipo)";
  }
  document.querySelector("[data-contador-resultados]").textContent = frase_do_contador;
  // Sem ninguém: mostra o aviso de busca vazia.
  document.querySelector("[data-sem-resultados]").hidden = quantidade_na_tela > 0;
}

/**
 * "Limpar filtros": zera a busca e os filtros de situação e de unidade, e refaz a tabela.
 *
 * Recebe: nada. Devolve: nada.
 */
function limpar_filtros() {
  document.querySelector("[data-busca]").value = "";
  document.querySelector("[data-filtro-situacao]").value = "";
  document.querySelector("[data-filtro-unidade]").value = "";
  atualizar_tabela();
}

// ============ FICHA DO FUNCIONÁRIO ============

/**
 * Monta um grupo de campos da ficha (ex.: "Titular"), como uma lista de nome e valor.
 *
 * Recebe: titulo — o nome do grupo; campos — lista de pares [nome do campo, valor].
 * Devolve: o elemento <section> do grupo.
 * Exemplo: montar_grupo_da_ficha("Renda", [["Valor", "R$ 2.450,00"]]).
 */
function montar_grupo_da_ficha(titulo, campos) {
  // O bloco do grupo, com o título em cima.
  const grupo = document.createElement("section");
  grupo.className = "ficha-grupo";
  const titulo_do_grupo = document.createElement("h3");
  titulo_do_grupo.className = "ficha-grupo-titulo";
  titulo_do_grupo.textContent = titulo;
  grupo.appendChild(titulo_do_grupo);
  // A lista de campos: <dt> é o nome do campo, <dd> é o valor.
  const lista = document.createElement("dl");
  lista.className = "ficha-campos";
  for (const [nome_do_campo, valor] of campos) {
    const nome = document.createElement("dt");
    nome.textContent = nome_do_campo;
    const conteudo = document.createElement("dd");
    // Campo vazio aparece como um traço, para ficar claro que não foi informado.
    conteudo.textContent = valor || "—";
    lista.appendChild(nome);
    lista.appendChild(conteudo);
  }
  grupo.appendChild(lista);
  return grupo;
}

/**
 * Os grupos da ficha com os campos da amostra do protótipo (aberta sem servidor), nos grupos do layout do banco.
 *
 * Recebe: grupos — o lugar da ficha onde os grupos entram; funcionario — um item de FUNCIONARIOS_DA_AURORA.
 * Devolve: nada. Com os dados de verdade, a ficha usa os campos do parâmetro (ver abrir_ficha).
 */
function montar_grupos_da_amostra(grupos, funcionario) {
  // Os dados da unidade (código e endereço comercial): os da amostra vêm da tabela de unidades de exemplo; um
  // funcionário da API, sem as colunas do parâmetro, traz os dele (e, sem nenhum, a unidade fica em branco).
  let unidade = UNIDADES_DA_AURORA[funcionario.unidade];
  if (funcionario.codigo_unidade || !unidade) {
    unidade = { codigo: funcionario.codigo_unidade || "", endereco: funcionario.endereco_comercial || "" };
  }
  grupos.appendChild(montar_grupo_da_ficha("Titular", [
    ["Nome completo", funcionario.nome],
    ["CPF", funcionario.cpf],
    ["Data de nascimento", funcionario.nascimento],
    ["Sexo", funcionario.sexo],
    ["Estado civil", funcionario.estado_civil],
  ]));
  grupos.appendChild(montar_grupo_da_ficha("Contato e endereço", [
    ["Celular", funcionario.celular],
    ["E-mail pessoal", funcionario.email],
    ["Bairro", funcionario.bairro],
    ["Município", funcionario.cidade],
  ]));
  grupos.appendChild(montar_grupo_da_ficha("Vínculo com a empresa", [
    ["CNPJ do empregador", funcionario.cnpj || CNPJ_DA_AURORA],
    ["Unidade", unidade.codigo + " · " + funcionario.unidade],
    ["Cargo", funcionario.cargo],
    ["Data de admissão", funcionario.admissao],
    ["Endereço comercial", unidade.endereco],
  ]));
  grupos.appendChild(montar_grupo_da_ficha("Renda", [
    ["Tipo de renda", funcionario.tipo_renda || "Salário mensal"],
    ["Valor", formatar_em_reais(funcionario.salario)],
  ]));
}

/**
 * Abre a janela com a ficha completa de um funcionário.
 *
 * Recebe: funcionario — um item de FUNCIONARIOS_DA_AURORA.
 * Devolve: nada; mostra a janela.
 * Com os dados de verdade, a ficha mostra TODOS os campos do parâmetro, nos grupos dele, com "Informação não
 * encontrada" no que veio em branco (a grade mostra só os obrigatórios; ADR-143).
 */
function abrir_ficha(funcionario) {
  // O cabeçalho: as iniciais, a situação, o nome (ou o CPF, quando o nome não veio) e um resumo de uma linha
  document.getElementById("janela-ficha-iniciais").textContent = iniciais_do_nome(funcionario.nome);
  document.getElementById("janela-ficha-situacao").textContent = funcionario.situacao;
  document.getElementById("janela-ficha-nome").textContent = titulo_do_detalhe(funcionario.nome, funcionario.cpf);
  // O resumo pula o que não veio (o cargo, a unidade e a matrícula não são obrigatórios no parâmetro de hoje)
  let matricula = "";
  if (funcionario.matricula) {
    matricula = "matrícula " + funcionario.matricula;
  }
  document.getElementById("janela-ficha-resumo").textContent =
    juntar_partes_do_resumo([funcionario.cargo, funcionario.unidade, matricula]);
  // Os grupos da ficha: com os dados de verdade, todos os campos do parâmetro; na amostra, os campos de exemplo
  const grupos = document.getElementById("janela-ficha-grupos");
  grupos.innerHTML = "";
  if (funcionario.campos && todas_as_colunas_do_parametro.length > 0) {
    grupos.append(...grupos_do_detalhe(todas_as_colunas_do_parametro, funcionario.campos));
  } else {
    montar_grupos_da_amostra(grupos, funcionario);
  }
  // O que a IA guardou sem rótulo, logo depois dos campos: só quando há alguma (js/grade_do_parametro.js; ADR-143,
  // Parte 1). A pessoa da API é o funcionario.campos; na amostra, ele não existe e a seção não aparece
  acrescentar_informacoes_sem_rotulo(grupos, funcionario.campos);
  // A conta onde a empresa paga o salário (vazia enquanto a pessoa não abriu).
  grupos.appendChild(montar_grupo_da_ficha("Conta no banco", [
    ["Agência", funcionario.agencia || "Ainda não abriu"],
    ["Conta salário", funcionario.conta || "Ainda não abriu"],
    ["Aberta em", funcionario.conta_aberta_em || "—"],
  ]));

  // Histórico do cadastro dessa pessoa.
  const historico = document.getElementById("janela-ficha-historico");
  historico.innerHTML = "";
  const passos_do_historico = [
    funcionario.tipo_de_envio + " em " + funcionario.incluido_em + ", por " + funcionario.incluido_por,
    "Lido e conferido pelos agentes",
  ];
  // Verdadeiro quando o banco já informou a conta da pessoa: aberta agora ou a que ela já tinha (ADR-113, ADR-123).
  const tem_conta_informada = funcionario.situacao === "Conta aberta" || funcionario.situacao === "Já é correntista";
  if (funcionario.situacao === "Cadastrado" || tem_conta_informada) {
    passos_do_historico.push("Cadastro concluído pelo banco");
  }
  // A última etapa: o banco mandou a conta da pessoa. Conta nova: "Conta aberta em"; quem já era cliente: a conta dele.
  if (funcionario.situacao === "Conta aberta") {
    passos_do_historico.push("Conta aberta em " + funcionario.conta_aberta_em + " · banco " + funcionario.campos.codigo_banco +
      " · agência " + funcionario.agencia + " · conta salário " + funcionario.conta);
  }
  if (funcionario.situacao === "Já é correntista") {
    passos_do_historico.push("Já era correntista: conta de " + funcionario.conta_aberta_em + " · banco " +
      funcionario.campos.codigo_banco + " · agência " + funcionario.agencia + " · conta salário " + funcionario.conta);
  }
  if (funcionario.situacao === "Em análise") {
    passos_do_historico.push("Em análise pelo banco (retorno em até 1 dia útil)");
  }
  if (funcionario.pendencia) {
    passos_do_historico.push("Pendência: " + funcionario.pendencia);
  }
  for (const passo of passos_do_historico) {
    const item = document.createElement("li");
    item.textContent = passo;
    historico.appendChild(item);
  }
  // Abre a janela por cima da página, escurecendo o fundo.
  document.getElementById("janela-ficha").showModal();
  // Com os dados de verdade, a ficha também pede a pessoa ao servidor (cada abertura fica registrada).
  if (funcionario.id) {
    mostrar_cpf_inteiro_na_ficha(funcionario.id);
  }
  // Com os dados de verdade, o histórico vem das etapas reais do envio, com as datas.
  if (funcionario.envio) {
    mostrar_historico_real_na_ficha(funcionario);
  }
}

/**
 * Troca o histórico da ficha pelas etapas reais do envio da pessoa, com a data de cada uma.
 *
 * Recebe: funcionario — com envio (o código do envio) e pendencia. Devolve: nada. Sem resposta, fica o histórico
 * simples. Exemplo: "Arquivo carregado · 24/09 · 10:12 (por rh.aurora)", "Lido pela IA · 24/09 · 10:13",
 * "Aprovação das contas enviadas · 25/09 · 09:00", "Contas abertas · 30/09 · 08:00 · 22 de 35 contas (63%)".
 */
async function mostrar_historico_real_na_ficha(funcionario) {
  // try/catch: servidor fora do ar não quebra a ficha.
  let etapas = null;
  try {
    const resposta = await fetch("/api/empresa/envios/" + encodeURIComponent(funcionario.envio) + "/linha_do_tempo");
    if (!resposta.ok) {
      return;
    }
    etapas = await resposta.json();
  } catch (erro) {
    return;
  }
  const historico = document.getElementById("janela-ficha-historico");
  historico.innerHTML = "";
  for (const etapa of etapas) {
    // Só as etapas que já aconteceram, e a atual (onde o envio está parado)
    if (!etapa.feito && !etapa.atual) {
      continue;
    }
    let texto = etapa.nome + " · " + data_e_hora_curtas(etapa.quando);
    // A atual ainda não aconteceu; a devolvida pelo banco, sim (fica a data da devolução e o detalhe dela)
    if (etapa.atual && !etapa.devolvido) {
      texto = etapa.nome + " · ainda não";
    }
    // A primeira etapa diz quem carregou o arquivo
    if (etapa.nome === "Arquivo carregado") {
      texto = texto + " (por " + funcionario.incluido_por + ")";
    }
    // O detalhe da etapa: quantos do envio já têm conta, ou quantas pessoas o banco aprovou e devolveu
    if (etapa.detalhe) {
      texto = texto + " · " + etapa.detalhe;
    }
    const item = document.createElement("li");
    item.textContent = texto;
    historico.appendChild(item);
  }
  // A pendência da pessoa, quando houver, fecha o histórico
  if (funcionario.pendencia) {
    const item = document.createElement("li");
    item.textContent = "Pendência: " + funcionario.pendencia;
    historico.appendChild(item);
  }
}

/**
 * Pede ao servidor a ficha da pessoa (a abertura fica registrada) e confere o CPF da ficha aberta.
 *
 * Recebe: identificador — o id da pessoa (envio.posição). Devolve: nada.
 * Se o servidor recusar ou não responder, a ficha continua com o CPF que veio na lista.
 */
async function mostrar_cpf_inteiro_na_ficha(identificador) {
  // try/catch: servidor fora do ar não quebra a ficha.
  try {
    const resposta = await fetch("/api/empresa/funcionarios/" + encodeURIComponent(identificador));
    if (!resposta.ok) {
      return;
    }
    const ficha = await resposta.json();
    // Procura, na ficha aberta, o valor do campo "cpf" (marcado pelo detalhe do js/grade_do_parametro.js) e troca
    const valor_do_cpf = document.querySelector("#janela-ficha-grupos [data-campo-do-detalhe='cpf']");
    if (valor_do_cpf && ficha.cpf) {
      valor_do_cpf.textContent = ficha.cpf;
    }
  } catch (erro) {
    // Sem resposta: fica o CPF que veio na lista.
  }
}

/**
 * Fecha a janela da ficha.
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_ficha() {
  document.getElementById("janela-ficha").close();
}

// ============ DOWNLOAD DA LISTA ============

/**
 * Baixa, em CSV, os funcionários que estão aparecendo na tabela (com os filtros aplicados).
 *
 * Recebe: nada. Devolve: nada; o navegador baixa "funcionarios.csv" (do servidor) ou, com a página aberta como arquivo
 * (sem servidor), a amostra "funcionarios_aurora.csv".
 * O separador é ";" porque é o que o Excel em português espera.
 */
function baixar_lista_em_csv() {
  // Com servidor (a página aberta pelo endereço), o arquivo vem sempre do servidor (com o CPF inteiro, e o download
  // fica registrado): a amostra do protótipo nunca é baixada, nem antes de a lista de verdade chegar.
  if (window.location.protocol.startsWith("http")) {
    baixar_lista_do_servidor();
    return;
  }
  // Cabeçalho do arquivo.
  const linhas_do_arquivo = ["Nome;CPF;Matrícula;Cargo;Unidade;Admissão;Salário;Incluído em;Incluído por;Situação"];
  // Uma linha por funcionário que está na tela.
  for (const funcionario of FUNCIONARIOS_DA_AURORA) {
    if (funcionario_aparece(funcionario)) {
      const valores = [funcionario.nome, funcionario.cpf, funcionario.matricula, funcionario.cargo,
        funcionario.unidade, funcionario.admissao, formatar_em_reais(funcionario.salario), funcionario.incluido_em,
        funcionario.incluido_por, funcionario.situacao];
      linhas_do_arquivo.push(valores.join(";"));
    }
  }
  // "﻿" no começo avisa o Excel que o arquivo é UTF-8 (senão os acentos saem errados).
  const conteudo = "﻿" + linhas_do_arquivo.join("\n");
  // Um "arquivo na memória" (Blob) e um link temporário que o navegador clica sozinho.
  const arquivo = new Blob([conteudo], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(arquivo);
  link.download = "funcionarios_aurora.csv";
  link.click();
  // Libera a memória do arquivo temporário.
  URL.revokeObjectURL(link.href);
}

// A frase quando o download não deu certo e o servidor não explicou o motivo (ou não respondeu).
const FRASE_DO_DOWNLOAD_QUE_FALHOU = "Não foi possível baixar a lista agora. Tente de novo em instantes.";
// A frase quando a pessoa clica antes de a lista de verdade chegar (ou quando ela não carregou).
const FRASE_DA_LISTA_QUE_AINDA_NAO_CHEGOU = "A lista de funcionários ainda não carregou. Tente de novo em instantes.";

/**
 * Mostra o recado do download logo abaixo do botão "Baixar lista", ou o esconde.
 *
 * Recebe: texto — a frase ("" esconde o recado). Devolve: nada.
 * Fica perto do botão, à vista: um aviso no alto da página ficaria fora da vista de quem está na lista, lá embaixo.
 */
function mostrar_recado_do_download(texto) {
  const recado = document.querySelector("[data-recado-do-download]");
  recado.textContent = texto;
  recado.hidden = texto === "";
}

/**
 * A frase da recusa do download, para mostrar ao lado do botão.
 *
 * Recebe: resposta — a resposta recusada do servidor. Devolve: o texto.
 * Ex.: 400 {"detail": "Nenhum funcionário para baixar com esses filtros."} → essa frase; 401 → "Sessão expirada.
 * Entre de novo."; erro interno (sem frase) → FRASE_DO_DOWNLOAD_QUE_FALHOU.
 */
async function frase_da_recusa_do_download(resposta) {
  // try/catch: o erro interno do servidor vem em texto simples, e não em JSON.
  try {
    const corpo = await resposta.json();
    // A frase que o servidor escreveu para a pessoa.
    if (typeof corpo.detail === "string") {
      return corpo.detail;
    }
  } catch (erro) {
    // Sem JSON: fica a frase geral.
  }
  return FRASE_DO_DOWNLOAD_QUE_FALHOU;
}

/**
 * Pede ao servidor o arquivo com as pessoas que estão na tela (com os filtros) e o entrega ao navegador.
 *
 * Recebe: nada. Devolve: nada; o navegador baixa "funcionarios.csv", com as mesmas pessoas da grade, em todas as
 * situações (ADR-155). Se não der, o motivo aparece logo abaixo do botão.
 * A tela manda só os identificadores; o servidor confere que são da empresa logada, põe o CPF inteiro e registra
 * quem baixou, quando e quantas pessoas.
 */
async function baixar_lista_do_servidor() {
  // O recado de um download anterior sai.
  mostrar_recado_do_download("");
  // A lista de verdade ainda não chegou: a tabela não tem o que baixar (e a amostra do protótipo nunca vai).
  if (!usando_dados_de_verdade) {
    mostrar_recado_do_download(FRASE_DA_LISTA_QUE_AINDA_NAO_CHEGOU);
    return;
  }
  // O identificador de download de cada pessoa que aparece na tabela agora: cadastrados e quem ainda está em
  // andamento (em análise, pendente ou aguardando envio).
  const identificadores = [];
  for (const funcionario of FUNCIONARIOS_DA_AURORA) {
    if (funcionario_aparece(funcionario) && funcionario.id_para_baixar) {
      identificadores.push(funcionario.id_para_baixar);
    }
  }
  // try/catch: servidor fora do ar não quebra a tela; o recado avisa.
  try {
    const resposta = await fetch("/api/empresa/funcionarios/baixar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identificadores: identificadores }),
    });
    // Recusado (ex.: ninguém na tabela com esses filtros, ou a sessão expirou): o motivo aparece ao lado do botão.
    if (!resposta.ok) {
      mostrar_recado_do_download(await frase_da_recusa_do_download(resposta));
      return;
    }
    // O arquivo que o servidor mandou, entregue ao navegador por um link temporário.
    const arquivo = await resposta.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(arquivo);
    link.download = "funcionarios.csv";
    link.click();
    // Libera a memória do arquivo temporário.
    URL.revokeObjectURL(link.href);
  } catch (erro) {
    // Sem resposta: nada é baixado, e a pessoa fica sabendo.
    mostrar_recado_do_download(FRASE_DO_DOWNLOAD_QUE_FALHOU);
  }
}

// ============ PENDÊNCIAS ============

// Quanto tempo o cartão resolvido fica na tela, com o "Pronto!", antes de sair da lista (em milissegundos).
const TEMPO_DO_PRONTO = 1500;

/**
 * Troca o filtro das pendências: "Pendências em aberto" ou "Resolvidas".
 *
 * Recebe: botao_do_filtro — o botão clicado (o filtro fica em data-filtro-pendencia).
 * Devolve: nada. Trocar o filtro tira da tela os cartões que acabaram de ser resolvidos (eles vão para "Resolvidas").
 */
function filtrar_pendencias(botao_do_filtro) {
  // Só o botão clicado fica destacado (é ele que diz o filtro escolhido).
  for (const botao of document.querySelectorAll("[data-filtro-pendencia]")) {
    botao.classList.toggle("filtro-rapido-ativo", botao === botao_do_filtro);
  }
  dispensar_os_resolvidos_a_vista(null);
  aplicar_filtros_das_pendencias();
}

/**
 * O filtro escolhido: "abertas" (Pendências em aberto) ou "resolvidas".
 *
 * Recebe: nada. Devolve: o texto do filtro.
 */
function filtro_escolhido() {
  const botao_ativo = document.querySelector("[data-filtro-pendencia].filtro-rapido-ativo");
  // Nenhum destacado: as abertas
  if (!botao_ativo) {
    return "abertas";
  }
  return botao_ativo.dataset.filtroPendencia;
}

/**
 * Esconde os cartões de outro arquivo e conta quantos ficaram à vista.
 *
 * Recebe: seletor — o seletor CSS dos cartões; arquivo_escolhido — o envio do filtro ("" = todos).
 * Devolve: quantos cartões ficaram à vista.
 */
function filtrar_cartoes_pelo_arquivo(seletor, arquivo_escolhido) {
  let quantidade_na_tela = 0;
  for (const cartao of document.querySelectorAll(seletor)) {
    const e_do_arquivo = arquivo_escolhido === "" || cartao.dataset.arquivoPendencia === arquivo_escolhido;
    cartao.hidden = !e_do_arquivo;
    if (e_do_arquivo) {
      quantidade_na_tela = quantidade_na_tela + 1;
    }
  }
  return quantidade_na_tela;
}

/**
 * Mostra só o que o filtro escolhido pede (as abertas ou as resolvidas) do arquivo escolhido, com o aviso do
 * arquivo, o rodapé e a dica de rolagem.
 *
 * Recebe: nada (lê o filtro destacado e a lista de arquivos). Devolve: nada.
 */
function aplicar_filtros_das_pendencias() {
  const arquivo_escolhido = document.querySelector("[data-filtro-arquivo-pendencias]").value;
  // Os dois tipos de cartão seguem o arquivo escolhido
  const abertas_na_tela = filtrar_cartoes_pelo_arquivo("[data-pendencia]", arquivo_escolhido);
  const resolvidas_na_tela = filtrar_cartoes_pelo_arquivo("[data-resolvida]", arquivo_escolhido);
  mostrar_a_vista_do_filtro(abertas_na_tela, resolvidas_na_tela);
  // O aviso do arquivo fala do que falta resolver: só na vista das abertas
  if (filtro_escolhido() === "resolvidas") {
    document.querySelector("[data-aviso-arquivo-pendente]").hidden = true;
  } else {
    mostrar_aviso_do_arquivo(arquivo_escolhido);
  }
  // O rodapé dos descartes fala do arquivo escolhido.
  atualizar_rodape_das_pendencias();
  // A lista mudou de tamanho: confere se ainda precisa da dica de rolagem.
  mostrar_dica_de_rolagem_se_precisar();
  // O cartão da conversa aberta no painel ficou escondido pelo filtro: a conversa fecha (js/painel_da_conversa.js)
  fechar_se_o_cartao_escolhido_saiu();
}

/**
 * Mostra a lista do filtro escolhido e esconde a outra, com as mensagens de lista vazia de cada uma.
 *
 * Recebe: abertas_na_tela e resolvidas_na_tela — quantos cartões de cada tipo ficaram à vista no arquivo escolhido.
 * Devolve: nada.
 * Nas abertas: a lista, ou o "Tudo em dia!" sem nenhuma pendência, ou "Nenhuma pendência em aberto neste arquivo".
 * Nas resolvidas: a lista, ou "Nenhuma pendência resolvida ainda".
 */
function mostrar_a_vista_do_filtro(abertas_na_tela, resolvidas_na_tela) {
  const vendo_resolvidas = filtro_escolhido() === "resolvidas";
  // Nenhum cartão aberto na lista (de nenhum arquivo)
  const sem_nenhuma_aberta = document.querySelectorAll("[data-pendencia]").length === 0;
  const lista_das_resolvidas = document.querySelector("[data-lista-resolvidas]");
  // A lista das resolvidas não carregou: ela mostra o aviso dela
  const resolvidas_indisponiveis = lista_das_resolvidas.hasAttribute("data-indisponivel");
  // Vista das abertas
  document.querySelector("[data-lista-pendencias]").hidden = vendo_resolvidas || sem_nenhuma_aberta;
  // O "Tudo em dia!" nunca aparece com um envio parado na conferência das colunas (ADR-127): o aviso dele fica sozinho
  const tem_envio_parado = envios_parados_nas_colunas.length > 0;
  document.querySelector("[data-sem-pendencias]").hidden = vendo_resolvidas || !sem_nenhuma_aberta || tem_envio_parado;
  document.querySelector("[data-sem-pendencias-do-tipo]").hidden =
    vendo_resolvidas || sem_nenhuma_aberta || abertas_na_tela > 0;
  // O rodapé dos descartes só com pendência aberta à vista
  document.querySelector("[data-rodape-pendencias]").hidden = vendo_resolvidas || sem_nenhuma_aberta;
  // Vista das resolvidas
  lista_das_resolvidas.hidden = !vendo_resolvidas || (resolvidas_na_tela === 0 && !resolvidas_indisponiveis);
  document.querySelector("[data-sem-resolvidas]").hidden =
    !vendo_resolvidas || resolvidas_na_tela > 0 || resolvidas_indisponiveis;
}

// O nome de cada arquivo com pendência, pelo envio (preenchido a cada busca das pendências de verdade).
const nomes_dos_arquivos_com_pendencia = {};

/**
 * O aviso do arquivo escolhido: enquanto ele tiver pendência, não vai para o banco; sem nenhuma, já está pronto.
 *
 * Recebe: arquivo_escolhido — o envio escolhido no filtro ("" = todos: sem aviso). Devolve: nada.
 */
function mostrar_aviso_do_arquivo(arquivo_escolhido) {
  const aviso = document.querySelector("[data-aviso-arquivo-pendente]");
  if (arquivo_escolhido === "") {
    aviso.hidden = true;
    return;
  }
  const nome_do_arquivo = nomes_dos_arquivos_com_pendencia[arquivo_escolhido] || "Este arquivo";
  // O cartão do grupo conta cada pessoa dele
  const abertas = somar_pendencias("[data-arquivo-pendencia='" + arquivo_escolhido + "']:not(.ajuste-resolvido)");
  aviso.classList.toggle("aviso-arquivo-pronto", abertas === 0);
  if (abertas === 0) {
    aviso.textContent = nome_do_arquivo + ": todas as pendências foram resolvidas. O arquivo já aparece em \"Pronto para " +
      "enviar ao banco\", no alto da página.";
  } else {
    // Singular ou plural, certo (1 pendência / 3 pendências)
    let pendencias_em_texto = abertas + " pendências";
    if (abertas === 1) {
      pendencias_em_texto = "1 pendência";
    }
    aviso.textContent = nome_do_arquivo + " ainda tem " + pendencias_em_texto + ". Ele só fica disponível para " +
      "envio ao banco depois que todas forem resolvidas.";
  }
  aviso.hidden = false;
}

/**
 * Refaz a lista de arquivos do filtro com os arquivos que têm pendência (e quantas), mantendo a escolha atual.
 *
 * Recebe: pendencias — os itens de /api/empresa/pendencias. Devolve: nada.
 */
function montar_filtro_de_arquivos(pendencias) {
  const filtro = document.querySelector("[data-filtro-arquivo-pendencias]");
  const escolhido = filtro.value;
  // Quantas pendências cada arquivo tem, na ordem em que aparecem
  const quantas_por_arquivo = {};
  const ordem_dos_arquivos = [];
  for (const pendencia of pendencias) {
    if (!(pendencia.processamento_id in quantas_por_arquivo)) {
      quantas_por_arquivo[pendencia.processamento_id] = 0;
      ordem_dos_arquivos.push(pendencia.processamento_id);
    }
    quantas_por_arquivo[pendencia.processamento_id] = quantas_por_arquivo[pendencia.processamento_id] + 1;
    nomes_dos_arquivos_com_pendencia[pendencia.processamento_id] = pendencia.nome_arquivo;
  }
  // Tira as opções antigas, deixando só "Todos os arquivos" (a primeira)
  while (filtro.options.length > 1) {
    filtro.remove(1);
  }
  // Cada arquivo com a versão, quando o nome se repete (vem do servidor: "aurora.xlsx (v2)") e quantas pendências
  // tem, no singular ou no plural. Ex.: "aurora_carga_inicial.xlsx (v2) · 3 pendências"
  for (const processamento_id of ordem_dos_arquivos) {
    const quantas = quantas_por_arquivo[processamento_id];
    let pendencias_em_texto = quantas + " pendências";
    if (quantas === 1) {
      pendencias_em_texto = "1 pendência";
    }
    const texto = nomes_dos_arquivos_com_pendencia[processamento_id] + " · " + pendencias_em_texto;
    filtro.add(new Option(texto, processamento_id));
  }
  // O arquivo escolhido que ficou sem pendência continua escolhido: o aviso diz que ele já está pronto
  if (escolhido && !(escolhido in quantas_por_arquivo)) {
    filtro.add(new Option(nomes_dos_arquivos_com_pendencia[escolhido] + " · sem pendência", escolhido));
  }
  filtro.value = escolhido;
  // O filtro só aparece com pendência de verdade na tela
  document.querySelector("[data-bloco-filtro-arquivo]").hidden = ordem_dos_arquivos.length === 0 && !escolhido;
}

/**
 * Mostra a dica "Role a lista..." e o esmaecido na base só quando há mais pendências do que cabem no painel.
 *
 * Recebe: nada. Devolve: nada.
 * scrollHeight é a altura de todo o conteúdo da lista; clientHeight é a parte que aparece.
 */
function mostrar_dica_de_rolagem_se_precisar() {
  const lista = document.querySelector("[data-lista-pendencias]");
  // Se o conteúdo é mais alto do que o espaço visível, tem coisa escondida embaixo.
  const tem_mais_embaixo = !lista.hidden && lista.scrollHeight > lista.clientHeight;
  document.querySelector("[data-dica-rolagem]").hidden = !tem_mais_embaixo;
  lista.classList.toggle("lista-com-rolagem", tem_mais_embaixo);
}

/**
 * Escreve nos filtros quantas pendências há: "Pendências em aberto (3)" e "Resolvidas (5)".
 *
 * Recebe: nada. Devolve: nada.
 * As duas contam pessoas: o cartão de um grupo vale por todas as pessoas dele. O cartão que acabou de ser resolvido e
 * ainda está à vista (faixa verde) já não conta como aberto. Sem a lista das resolvidas, o número dela vira "—".
 */
function atualizar_contagem_dos_filtros() {
  const contagem = {
    abertas: String(somar_pendencias("[data-pendencia]:not(.ajuste-resolvido)")),
    resolvidas: String(somar_pendencias("[data-resolvida]")),
  };
  // A lista das resolvidas não carregou: o número dela fica em traço
  if (document.querySelector("[data-lista-resolvidas]").hasAttribute("data-indisponivel")) {
    contagem.resolvidas = "—";
  }
  // Escreve cada número entre parênteses no filtro correspondente.
  for (const lugar of document.querySelectorAll("[data-contagem-tipo]")) {
    lugar.textContent = "(" + contagem[lugar.dataset.contagemTipo] + ")";
  }
}

/**
 * Só no protótipo (a página aberta como arquivo): resolve uma pendência de exemplo, marca como resolvida, atualiza a
 * contagem e a situação na tabela.
 *
 * Recebe: botao — o botão clicado dentro da pendência.
 * Devolve: nada.
 * No sistema real, quem resolve é a conversa com o agente (js/assistente_de_correcao.js), que grava a correção com quem
 * pediu e valida o envio de novo.
 */
function resolver_pendencia(botao) {
  // O cartão da pendência e o nome da pessoa.
  const pendencia = botao.closest("[data-pendencia]");
  const nome_da_pessoa = pendencia.querySelector(".ajuste-titulo").textContent;
  // Faixa verde e, no lugar das respostas rápidas e da caixa, o balão do agente dizendo que resolveu.
  pendencia.classList.add("ajuste-resolvido");
  pendencia.querySelector(".respostas-rapidas").remove();
  pendencia.querySelector(".formulario-conversa-ia").replaceWith(montar_balao_da_ia("Pronto! Resolvido.", ""));
  // Depois de um instante, o cartão sai da lista (a pendência está resolvida) e a contagem é refeita.
  setTimeout(function () {
    pendencia.remove();
    atualizar_total_de_pendencias();
    // Refaz o filtro escolhido, para avisar se o tipo ficou vazio.
    filtrar_pendencias(document.querySelector("[data-filtro-pendencia].filtro-rapido-ativo"));
  }, TEMPO_DO_PRONTO);
  // A pessoa passa a "Em análise" na tabela e perde o aviso de pendência.
  for (const funcionario of FUNCIONARIOS_DA_AURORA) {
    if (funcionario.nome === nome_da_pessoa) {
      funcionario.situacao = "Em análise";
      funcionario.pendencia = "";
    }
  }
  atualizar_total_de_pendencias();
  atualizar_tabela();
}

// Os envios parados na conferência das colunas (ADR-127), preenchidos a cada busca das pendências de verdade.
// Com um deles, a tela nunca diz "Tudo em dia".
let envios_parados_nas_colunas = [];

/**
 * Busca os envios que esperam a conferência das colunas e monta um aviso para cada um, com o botão para continuar.
 *
 * Recebe: nada. Devolve: nada. Servidor fora do ar: a lista fica vazia (a lista de pendências já avisa o erro).
 * Por que existe (ADR-127): na conversa, o agente pode devolver o envio à leitura das colunas; as pendências dele somem
 * até as colunas serem conferidas de novo, e a tela dizia "Tudo em dia!" com o envio parado.
 */
async function carregar_envios_parados_nas_colunas() {
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/empresa/envios-parados-nas-colunas");
    envios_parados_nas_colunas = resposta.ok ? await resposta.json() : [];
  } catch (erro) {
    envios_parados_nas_colunas = [];
  }
  montar_avisos_dos_envios_parados();
}

/**
 * Monta um aviso por envio parado: o título, o texto e o botão "Continuar a conferência das colunas", que abre a
 * janela do envio nas colunas (js/novo_envio.js desvia os links para cadastrar.html).
 *
 * Recebe: nada (usa envios_parados_nas_colunas). Devolve: nada.
 */
function montar_avisos_dos_envios_parados() {
  const lugar = document.querySelector("[data-envios-parados]");
  lugar.replaceChildren();
  for (const envio of envios_parados_nas_colunas) {
    const aviso = criar("div", "aviso-envio-parado", "");
    aviso.dataset.envioParado = envio.processamento_id;
    aviso.append(criar("span", "aviso-envio-parado-titulo", envio.titulo),
      criar("p", "aviso-envio-parado-texto", envio.texto));
    const continuar = criar("a", "botao botao-principal botao-pequeno", "Continuar a conferência das colunas");
    continuar.href = "cadastrar.html?envio=" + encodeURIComponent(envio.processamento_id);
    continuar.dataset.continuarEnvio = envio.processamento_id;
    aviso.append(continuar);
    lugar.append(aviso);
  }
  lugar.hidden = envios_parados_nas_colunas.length === 0;
}

/**
 * A legenda do cartão de pendências do resumo, em português certo (singular e plural).
 *
 * Recebe: abertas — quantas pendências faltam. Devolve: o texto.
 * Ex.: 0 pendências e 1 envio parado → "envio esperando você conferir as colunas".
 */
function legenda_do_cartao_de_pendencias(abertas) {
  if (abertas > 0) {
    return "pendências para você fechar os cadastros";
  }
  if (envios_parados_nas_colunas.length === 1) {
    return "envio esperando você conferir as colunas";
  }
  if (envios_parados_nas_colunas.length > 1) {
    return "envios esperando você conferir as colunas";
  }
  return "nenhuma pendência para fechar os cadastros";
}

/**
 * Recalcula quantas pendências faltam e atualiza o número no resumo.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_total_de_pendencias() {
  // As pendências ainda abertas (sem a faixa verde); o cartão do grupo conta cada pessoa dele.
  const abertas = somar_pendencias("[data-pendencia]:not(.ajuste-resolvido)");
  // Sobrou algum cartão na lista (aberto ou ainda mostrando o "Pronto!")?
  const cartoes_na_lista = document.querySelectorAll("[data-pendencia]").length;
  // Tudo em dia: nenhuma pendência aberta E nenhum envio parado na conferência das colunas (ADR-127)
  const tudo_em_dia = abertas === 0 && envios_parados_nas_colunas.length === 0;
  document.querySelector("[data-total-pendencias]").textContent = abertas;
  // Os números entre parênteses nos filtros.
  atualizar_contagem_dos_filtros();

  // Atalho "Pendências" do topo: o número some quando não há pendência.
  const contador_do_atalho = document.querySelector("[data-atalho-pendencias]");
  contador_do_atalho.textContent = abertas;
  contador_do_atalho.hidden = tudo_em_dia;

  // Cartão do resumo: laranja com "Resolver agora" enquanto houver pendência; verde com "Tudo em dia" sem nenhuma.
  const cartao = document.querySelector("[data-cartao-pendencias]");
  cartao.classList.toggle("cartao-numero-atencao", !tudo_em_dia);
  cartao.classList.toggle("cartao-numero-em-dia", tudo_em_dia);
  document.querySelector("[data-legenda-pendencias]").textContent = legenda_do_cartao_de_pendencias(abertas);
  document.querySelector("[data-link-pendencias]").hidden = tudo_em_dia;
  document.querySelector("[data-selo-em-dia]").hidden = !tudo_em_dia;
  // O ícone troca de triângulo de alerta para o visto.
  document.querySelector("[data-icone-pendencias]").setAttribute("href", tudo_em_dia ? "#icone-visto" : "#icone-alerta");

  // Painel: os filtros só saem sem nenhuma pendência, nem aberta nem resolvida (o "Tudo em dia!" fica sozinho).
  const sem_nenhuma_resolvida = document.querySelectorAll("[data-resolvida]").length === 0;
  document.querySelector("[data-filtros-pendencias]").hidden = cartoes_na_lista === 0 && sem_nenhuma_resolvida;
  // A vista do filtro escolhido: a lista (ou o "Tudo em dia!"), o rodapé e a dica de rolagem.
  aplicar_filtros_das_pendencias();
}

/**
 * Só para o protótipo: abrir a página com "?muitas-pendencias" no endereço enche a lista com 100 pendências.
 *
 * Recebe: nada. Devolve: nada.
 * As 97 extras são cópias dos 3 cartões de exemplo, numeradas, só para ver como o painel se comporta.
 */
function simular_muitas_pendencias_se_pedido() {
  // Só quando o endereço pede.
  if (!window.location.search.includes("muitas-pendencias")) {
    return;
  }
  const lista = document.querySelector("[data-lista-pendencias]");
  // Os 3 cartões originais servem de molde.
  const moldes = Array.from(lista.querySelectorAll("[data-pendencia]"));
  // Cria 97 cópias, alternando os moldes, até completar 100.
  for (let numero = 4; numero <= 100; numero = numero + 1) {
    const copia = moldes[numero % moldes.length].cloneNode(true);
    copia.querySelector(".ajuste-titulo").textContent = "Funcionário de exemplo " + numero;
    lista.appendChild(copia);
  }
}

/**
 * Só para o protótipo: abrir a página com "?sem-pendencias" no endereço mostra direto o estado "Tudo em dia!".
 *
 * Recebe: nada. Devolve: nada.
 * Exemplo: acompanhar.html?sem-pendencias
 */
function simular_sem_pendencias_se_pedido() {
  // location.search é o trecho do endereço depois do "?".
  if (!window.location.search.includes("sem-pendencias")) {
    return;
  }
  // Tira todas as pendências da lista, como se já tivessem sido resolvidas.
  for (const pendencia of document.querySelectorAll("[data-pendencia]")) {
    pendencia.remove();
  }
  // Ninguém fica com pendência na tabela.
  for (const funcionario of FUNCIONARIOS_DA_AURORA) {
    if (funcionario.situacao === "Pendente") {
      funcionario.situacao = "Em análise";
    }
    funcionario.pendencia = "";
  }
}

// ============ AVISO DE RECEBIMENTO ============

/**
 * Mostra "Recebemos!" quando a pessoa chega da conferência do cadastro (endereço com "?enviado=26").
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_aviso_de_recebimento() {
  // URLSearchParams lê os pedaços do endereço depois do "?", como "enviado=26".
  const parametros = new URLSearchParams(window.location.search);
  // Chegando da janela "Cadastrar funcionários" (js/novo_envio.js): diz o que fazer agora
  const recados = {
    colunas_aceitas: "Colunas aceitas! Agora é aqui: resolva as pendências abaixo e envie ao banco.",
    ja_enviado: "Esse arquivo já tinha sido enviado. O envio dele está na lista abaixo.",
  };
  if (recados[parametros.get("aviso")]) {
    document.querySelector("[data-aviso-recebido-texto]").textContent = recados[parametros.get("aviso")];
    document.querySelector("[data-aviso-recebido]").hidden = false;
    return;
  }
  const quantidade = parametros.get("enviado");
  if (!quantidade) {
    return;
  }
  let texto = "Recebemos! Os " + quantidade + " funcionários conferidos por você estão em análise pelo banco. " +
    "Retorno em até 1 dia útil.";
  // Quem já tinha ido ao banco (ou já estava cadastrado) não foi de novo (envio parcial, ADR-126)
  const de_fora = Number(parametros.get("de_fora") || 0);
  if (de_fora === 1) {
    texto = texto + " 1 pessoa que já tinha sido mandada antes ficou de fora.";
  } else if (de_fora > 1) {
    texto = texto + " " + de_fora + " pessoas que já tinham sido mandadas antes ficaram de fora.";
  }
  document.querySelector("[data-aviso-recebido-texto]").textContent = texto;
  document.querySelector("[data-aviso-recebido]").hidden = false;
}

// ============ ABERTURA DAS CONTAS (CASOS DE EXEMPLO) ============

/**
 * Só para o protótipo: mostra o painel "Abertura das contas" num caso que a Aurora não tem.
 *   ?unidade-unica        → a empresa tem uma unidade só: "Por unidade" dá lugar a "Por envio".
 *
 * Recebe: nada. Devolve: nada.
 * No sistema real, quem decide o caso é o serviço, pela quantidade de unidades e de aprovados da empresa.
 */
function simular_casos_da_abertura_das_contas() {
  // O trecho do endereço depois do "?".
  const pedido = window.location.search;
  // Uma unidade só: troca o bloco por unidade pelo bloco por envio.
  if (pedido.includes("unidade-unica")) {
    document.querySelector("[data-contas-por-unidade]").hidden = true;
    document.querySelector("[data-contas-por-envio]").hidden = false;
  }
}

// ============ ENVIOS ============

/**
 * O texto do rodapé da lista de envios, com singular e plural certos.
 *
 * Recebe: quantidade_na_tela — quantos envios aparecem; total — quantos a empresa tem.
 * Devolve: o texto. Exemplos: (1, 1) → "Mostrando 1 de 1 envio"; (5, 7) → "Mostrando 5 de 7 envios".
 */
function texto_do_contador_de_envios(quantidade_na_tela, total) {
  // "envio" no singular só quando o total é 1
  let palavra = "envios";
  if (total === 1) {
    palavra = "envio";
  }
  return "Mostrando " + quantidade_na_tela + " de " + total + " " + palavra;
}

/**
 * Mostra só os primeiros envios (quantos couberem em envios_aparecendo) e atualiza o rodapé da lista.
 *
 * Recebe: nada. Devolve: nada.
 * Exemplo: com 100 envios, aparecem os 5 mais recentes e "Mostrando 5 de 100 envios".
 */
function mostrar_envios() {
  // Com servidor, a lista já tem só as páginas pedidas: o total vem do servidor.
  if (total_de_envios_no_servidor !== null) {
    mostrar_rodape_dos_envios_reais();
    return;
  }
  // Todos os envios, do mais recente para o mais antigo (é a ordem do HTML).
  const envios = document.querySelectorAll("[data-envio]");
  // Esconde quem passou do limite.
  envios.forEach(function (envio, posicao) {
    envio.hidden = posicao >= envios_aparecendo;
  });
  // Quantos estão na tela de verdade (o limite pode ser maior que o total).
  const quantidade_na_tela = Math.min(envios_aparecendo, envios.length);
  document.querySelector("[data-contador-envios]").textContent =
    texto_do_contador_de_envios(quantidade_na_tela, envios.length);
  // O botão "Mostrar mais" só aparece se ainda sobrar envio escondido.
  document.querySelector("[data-mostrar-mais-envios]").hidden = quantidade_na_tela >= envios.length;
}

/**
 * Traz os próximos 5 envios.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_mais_envios() {
  // Com servidor: busca a próxima página.
  if (total_de_envios_no_servidor !== null) {
    buscar_pagina_de_envios(document.querySelectorAll("[data-lista-envios] [data-envio]").length);
    return;
  }
  envios_aparecendo = envios_aparecendo + ENVIOS_POR_VEZ;
  mostrar_envios();
}

/**
 * O rodapé da lista com os envios reais: "Mostrando X de Y envios" e o "Mostrar mais", se ainda sobrar.
 *
 * Recebe: nada. Devolve: nada. X é quantos já vieram do servidor; Y, o total da empresa.
 */
function mostrar_rodape_dos_envios_reais() {
  const quantidade_na_tela = document.querySelectorAll("[data-lista-envios] [data-envio]").length;
  document.querySelector("[data-contador-envios]").textContent =
    texto_do_contador_de_envios(quantidade_na_tela, total_de_envios_no_servidor);
  document.querySelector("[data-mostrar-mais-envios]").hidden = quantidade_na_tela >= total_de_envios_no_servidor;
}

/**
 * Busca uma página de envios no servidor e põe os cartões no fim da lista.
 *
 * Recebe: inicio — quantos envios pular (0 = a primeira página). Devolve: nada.
 * Exemplo: com 5 cartões na tela, buscar_pagina_de_envios(5) traz do 6º ao 10º.
 */
async function buscar_pagina_de_envios(inicio) {
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/empresa/envios/pagina?inicio=" + inicio + "&quantidade=" + ENVIOS_POR_VEZ);
    // Recusado: a lista avisa que não carregou (nunca fica com os envios de exemplo)
    if (!resposta.ok) {
      mostrar_envios_indisponiveis();
      return;
    }
    const pagina = await resposta.json();
    const lista = document.querySelector("[data-lista-envios]");
    // A primeira página troca os exemplos (ou a lista antiga); as seguintes vão para o fim.
    if (inicio === 0) {
      lista.replaceChildren();
    }
    for (const envio of pagina.envios) {
      lista.append(montar_cartao_de_envio(envio));
    }
    total_de_envios_no_servidor = pagina.total;
    mostrar_rodape_dos_envios_reais();
    // Os envios de verdade estão na tela: sai a barra de "carregando"
    marcar_como_carregado(lista);
    marcar_como_carregado(document.querySelector("[data-contador-envios]"));
  } catch (erro) {
    // Servidor fora do ar: a lista avisa que não carregou.
    mostrar_envios_indisponiveis();
  }
}

/**
 * O servidor não respondeu na primeira carga: a lista de envios avisa, sem os envios de exemplo.
 *
 * Recebe: nada. Devolve: nada. Se os envios de verdade já estavam na tela (ex.: falhou só a atualização
 * automática), eles ficam.
 */
function mostrar_envios_indisponiveis() {
  // A lista com o aviso no lugar dos exemplos.
  mostrar_lista_indisponivel(document.querySelector("[data-lista-envios]"));
  // O rodapé ("Mostrando X de Y") fica vazio.
  const contador = document.querySelector("[data-contador-envios]");
  if (!contador.hasAttribute("data-dado-pronto")) {
    contador.textContent = "";
    marcar_como_carregado(contador);
  }
}

/**
 * Troca o conteúdo de exemplo de uma lista por um aviso de que ela não carregou.
 *
 * Recebe: lista — o elemento marcado com data-aguarda-bloco. Devolve: nada.
 * Lista que já mostra dados de verdade fica como está (a falha foi numa atualização, não na primeira carga).
 */
function mostrar_lista_indisponivel(lista) {
  // Já tem dado de verdade: mantém.
  if (lista.hasAttribute("data-dado-pronto")) {
    return;
  }
  // O aviso no lugar dos exemplos.
  lista.replaceChildren(criar("p", "painel-vazio", "Não foi possível carregar agora. Atualize a página em instantes."));
  marcar_como_carregado(lista);
}

/**
 * Abre todos os envios que estão na tela; se já estiverem todos abertos, fecha todos.
 *
 * Recebe: botao — o botão "Expandir todos / Recolher todos", cujo texto muda junto.
 * Devolve: nada.
 */
function abrir_ou_fechar_todos_os_envios(botao) {
  // Só os envios visíveis contam (os escondidos pelo "Mostrar mais" ficam como estão).
  const envios_na_tela = document.querySelectorAll("[data-envio]:not([hidden])");
  // Se algum estiver fechado, a ação é abrir todos; senão, fechar todos.
  let algum_fechado = false;
  for (const envio of envios_na_tela) {
    if (!envio.open) {
      algum_fechado = true;
    }
  }
  for (const envio of envios_na_tela) {
    envio.open = algum_fechado;
  }
  // O texto do botão diz o que o próximo clique vai fazer.
  botao.textContent = algum_fechado ? "Recolher todos" : "Expandir todos";
}

// ============ DADOS DE VERDADE (API, ADR-69) ============

/**
 * Troca uma data do jeito do banco de dados ("2021-06-18") pelo jeito brasileiro ("18/06/2021").
 *
 * Recebe: texto — a data no formato ano-mês-dia (ou vazio). Devolve: a data dia/mês/ano (ou "").
 */
function data_no_formato_brasileiro(texto) {
  // Vazio ou fora do formato: devolve como veio.
  if (!texto || texto.length < 10) {
    return texto || "";
  }
  // Os pedaços da data: ano, mês e dia (só os 10 primeiros caracteres, sem a hora).
  const pedacos = texto.slice(0, 10).split("-");
  // Monta dia/mês/ano.
  return pedacos[2] + "/" + pedacos[1] + "/" + pedacos[0];
}

/**
 * Junta os pedaços preenchidos de um texto com um separador, pulando os vazios.
 *
 * Recebe: pedacos — lista de textos; separador — ex.: " · ". Devolve: o texto junto.
 * Exemplo: juntar_preenchidos(["Rua A", "", "Campinas/SP"], " · ") → "Rua A · Campinas/SP".
 */
function juntar_preenchidos(pedacos, separador) {
  // Só os pedaços com algum texto.
  const preenchidos = [];
  for (const pedaco of pedacos) {
    if (pedaco && pedaco.trim() !== "") {
      preenchidos.push(pedaco.trim());
    }
  }
  // Junta com o separador.
  return preenchidos.join(separador);
}

/**
 * Põe a pontuação no CNPJ. Exemplo: "10433218000193" → "10.433.218/0001-93" (outro tamanho volta como veio).
 *
 * Recebe: cnpj. Devolve: o CNPJ pontuado.
 */
function formatar_cnpj(cnpj) {
  // Só formata quando tem os 14 dígitos.
  if (!cnpj || cnpj.length !== 14) {
    return cnpj;
  }
  // Pedaço por pedaço: 2.3.3/4-2.
  return cnpj.slice(0, 2) + "." + cnpj.slice(2, 5) + "." + cnpj.slice(5, 8) + "/" + cnpj.slice(8, 12) + "-" + cnpj.slice(12);
}

/**
 * Põe a pontuação no celular. Exemplo: "69997853045" → "(69) 99785-3045" (outro tamanho volta como veio).
 *
 * Recebe: celular. Devolve: o celular pontuado.
 */
function formatar_celular(celular) {
  // Só formata quando tem 11 dígitos (DDD + 9 dígitos).
  if (!celular || celular.length !== 11) {
    return celular;
  }
  // (DDD) 9XXXX-XXXX.
  return "(" + celular.slice(0, 2) + ") " + celular.slice(2, 7) + "-" + celular.slice(7);
}

/**
 * Transforma um funcionário vindo da API no formato que a tabela e a ficha desta tela usam.
 *
 * Recebe: pessoa — um item de /api/empresa/funcionarios (campos do layout do banco, CPF inteiro e formatado).
 * Devolve: um objeto no formato dos exemplos (nome, cpf, matricula, cargo, unidade...).
 */
function funcionario_da_api(pessoa) {
  // O endereço comercial montado numa linha só (para a ficha), pulando o que não veio no arquivo.
  const rua_e_numero = juntar_preenchidos([pessoa.logradouro_comercial, pessoa.numero_comercial], ", ");
  const cidade_e_uf = juntar_preenchidos([pessoa.municipio_comercial, pessoa.uf_comercial], "/");
  const endereco_comercial = juntar_preenchidos([rua_e_numero, pessoa.bairro_comercial, cidade_e_uf, pessoa.cep_comercial], " · ");
  // O objeto no formato da tela.
  return {
    nome: pessoa.nome_completo,
    cpf: pessoa.cpf,
    matricula: pessoa.matricula,
    cargo: pessoa.cargo,
    unidade: pessoa.nome_unidade,
    codigo_unidade: pessoa.codigo_unidade,
    endereco_comercial: endereco_comercial,
    cnpj: formatar_cnpj(pessoa.cnpj_empregador),
    admissao: data_no_formato_brasileiro(pessoa.data_admissao),
    salario: Number(pessoa.valor_renda),
    tipo_renda: pessoa.tipo_renda,
    nascimento: data_no_formato_brasileiro(pessoa.data_nascimento),
    sexo: pessoa.sexo,
    estado_civil: pessoa.estado_civil,
    celular: formatar_celular(pessoa.telefone_celular),
    email: pessoa.email_pessoal,
    bairro: pessoa.bairro_residencial,
    cidade: juntar_preenchidos([pessoa.municipio_residencial, pessoa.uf_residencial], "/"),
    // O identificador (envio.posição): é com ele que a ficha pede o CPF inteiro. Só os cadastrados têm.
    id: pessoa.id,
    // O identificador de download: todos têm, cadastrados ou não. O "Baixar lista" manda o de quem aparece (ADR-155).
    id_para_baixar: pessoa.id_para_baixar,
    // O envio em que a pessoa entrou: a ficha busca a linha do tempo dele (o histórico com as datas).
    envio: pessoa.envio,
    // A situação vem do servidor: Cadastrado, Em análise (com o banco) ou Pendente (com a primeira pendência).
    situacao: pessoa.situacao || "Cadastrado",
    pendencia: pessoa.pendencia,
    tipo_de_envio: pessoa.tipo_de_envio,
    incluido_em: data_no_formato_brasileiro(pessoa.incluido_em),
    incluido_por: pessoa.incluido_por,
    // A conta no banco, do arquivo semanal de contas abertas (vazia enquanto a pessoa não abriu).
    agencia: pessoa.agencia,
    conta: pessoa.conta,
    conta_aberta_em: pessoa.conta_aberta_em,
    // Todos os campos do parâmetro, como vieram da API: a grade mostra cada um numa coluna (ADR-111).
    campos: pessoa,
  };
}

/**
 * Refaz a lista do filtro de unidades com as unidades que aparecem nos funcionários de verdade.
 *
 * Recebe: nada. Devolve: nada.
 */
function refazer_filtro_de_unidades() {
  // A lista do filtro.
  const filtro = document.querySelector("[data-filtro-unidade]");
  // Os nomes das unidades, sem repetir (um Set guarda cada valor uma vez só).
  const unidades = new Set();
  for (const funcionario of FUNCIONARIOS_DA_AURORA) {
    unidades.add(funcionario.unidade);
  }
  // Tira as opções de exemplo, deixando só "Todas as unidades" (a primeira).
  while (filtro.options.length > 1) {
    filtro.remove(1);
  }
  // Uma opção por unidade, em ordem alfabética.
  for (const unidade of Array.from(unidades).sort()) {
    filtro.add(new Option(unidade, unidade));
  }
}

/**
 * Busca na API os funcionários de verdade da empresa logada e troca a amostra por eles.
 *
 * Recebe: nada. Devolve: nada. "async": espera a resposta do servidor sem travar a tela.
 * Se a página foi aberta sem servidor (dois cliques no arquivo) ou a API não responder, a amostra continua.
 */
async function carregar_funcionarios_de_verdade() {
  // Aberta como arquivo (file://): não há servidor para perguntar.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // try/catch: se o servidor não responder, a tela segue com a amostra em vez de quebrar.
  try {
    // Pede os funcionários da empresa logada (a empresa vem da sessão, no servidor).
    const resposta = await fetch("/api/empresa/funcionarios");
    // Recusado: a tabela avisa que não carregou (nunca fica com a amostra).
    if (!resposta.ok) {
      mostrar_funcionarios_indisponiveis();
      return;
    }
    // A lista em JSON.
    const pessoas = await resposta.json();
    // A lista de antes (só se já era a de verdade): é com ela que a grade acha o valor que acabou de mudar
    let funcionarios_de_antes = [];
    if (usando_dados_de_verdade) {
      funcionarios_de_antes = FUNCIONARIOS_DA_AURORA.slice();
    }
    // Esvazia a amostra e põe os funcionários de verdade no lugar.
    FUNCIONARIOS_DA_AURORA.length = 0;
    for (const pessoa of pessoas) {
      FUNCIONARIOS_DA_AURORA.push(funcionario_da_api(pessoa));
    }
    // O total agora é o tamanho da lista de verdade.
    total_de_funcionarios_da_empresa = FUNCIONARIOS_DA_AURORA.length;
    usando_dados_de_verdade = true;
    // As colunas do parâmetro vigente (uma por campo, com a marca de obrigatório), antes de desenhar a tabela.
    await carregar_colunas_do_parametro();
    // O que mudou desde a lista de antes (ex.: o CPF que a IA corrigiu) fica destacado na grade
    marcar_as_celulas_que_mudaram(funcionarios_de_antes, FUNCIONARIOS_DA_AURORA);
    // Filtro de unidades e tabela refeitos.
    refazer_filtro_de_unidades();
    atualizar_tabela();
    // Os funcionários de verdade estão na tela: sai a barra de "carregando" da tabela, do contador e do filtro
    liberar_a_consulta_de_funcionarios();
  } catch (erro) {
    // Servidor fora do ar: a tabela avisa que não carregou.
    mostrar_funcionarios_indisponiveis();
  }
}

/**
 * Tira a barra de "carregando" da consulta de funcionários: a tabela, o contador e o filtro de unidades.
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_a_consulta_de_funcionarios() {
  marcar_como_carregado(document.querySelector("[data-tabela-funcionarios]"));
  marcar_como_carregado(document.querySelector("[data-contador-resultados]"));
  marcar_como_carregado(document.querySelector("[data-filtro-unidade]"));
}

/**
 * O servidor não respondeu na primeira carga: a consulta fica vazia, com o aviso no contador (sem a amostra).
 *
 * Recebe: nada. Devolve: nada. Se os funcionários de verdade já estavam na tela, eles ficam.
 */
function mostrar_funcionarios_indisponiveis() {
  // Já tem dado de verdade: mantém.
  if (document.querySelector("[data-tabela-funcionarios]").hasAttribute("data-dado-pronto")) {
    return;
  }
  // Tira a amostra da lista (senão ela voltaria ao digitar na busca); a tabela e o filtro ficam vazios.
  FUNCIONARIOS_DA_AURORA.length = 0;
  total_de_funcionarios_da_empresa = 0;
  refazer_filtro_de_unidades();
  atualizar_tabela();
  // O aviso de "ninguém encontrado" não vale aqui: o problema é o servidor.
  document.querySelector("[data-sem-resultados]").hidden = true;
  document.querySelector("[data-contador-resultados]").textContent =
    "Não foi possível carregar a lista de funcionários agora. Atualize a página em instantes.";
  liberar_a_consulta_de_funcionarios();
}

/**
 * Escreve a data e a hora de um evento no jeito curto da linha do tempo ("24/09 · 10:12"), no horário local.
 *
 * Recebe: texto — data e hora no formato do servidor (ex.: "2026-09-24T13:12:00+00:00"), ou null.
 * Devolve: o texto curto, ou "" se não houver data.
 */
function data_e_hora_curtas(texto) {
  // Sem data: nada.
  if (!texto) {
    return "";
  }
  // O navegador converte do horário universal para o horário do computador.
  const momento = new Date(texto);
  const dia_e_mes = momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const hora = momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return dia_e_mes + " · " + hora;
}

/**
 * A classe de cor do selo de um envio, pela situação.
 *
 * Recebe: situacao — ex.: "Cadastrado". Devolve: a classe (verde, laranja, cinza ou a da marca).
 */
function classe_do_selo_do_envio(situacao) {
  // Concluído: verde.
  if (situacao === "Cadastrado") {
    return "selo-sucesso";
  }
  // Pede ação da empresa: laranja (inclusive o envio que o banco devolveu com um motivo).
  if (situacao === "Com pendências para corrigir" || situacao === "Esperando você conferir as colunas" ||
    situacao === "Devolvido pelo banco") {
    return "selo-atencao";
  }
  // Descartado: cinza.
  if (situacao === "Descartado") {
    return "selo-neutro";
  }
  // Em andamento: a cor da marca.
  return "selo-marca";
}

/**
 * Cria um elemento com classe e texto (o texto entra como texto puro, nunca como código).
 *
 * Recebe: etiqueta; classe; texto. Devolve: o elemento.
 */
function criar(etiqueta, classe, texto) {
  // O elemento vazio.
  const elemento = document.createElement(etiqueta);
  // A classe, se houver.
  if (classe) {
    elemento.className = classe;
  }
  // O texto, se houver.
  if (texto) {
    elemento.textContent = texto;
  }
  return elemento;
}

// As situações em que as colunas ainda não foram conferidas (a janela do envio abre nele)
const SITUACOES_DO_ACEITE_DAS_COLUNAS = ["Recebido", "Esperando você conferir as colunas"];
// As situações em que o envio espera a empresa e ainda não foi ao banco (dá para trocar o arquivo)
const SITUACOES_QUE_ESPERAM_A_EMPRESA = ["Recebido", "Esperando você conferir as colunas", "Colunas conferidas",
  "Pronto para enviar", "Com pendências para corrigir", "Devolvido pelo banco"];

/**
 * Monta o cartão (recolhível) de um envio de verdade, no mesmo formato dos exemplos do HTML.
 *
 * Recebe: envio — um item de /api/empresa/envios/pagina. Devolve: o elemento <details>.
 */
function montar_cartao_de_envio(envio) {
  // O cartão recolhível: começa aberto se ainda não foi cadastrado (é o que pede atenção).
  const cartao = criar("details", "cartao envio", "");
  cartao.dataset.envio = "";
  cartao.open = envio.situacao !== "Cadastrado" && envio.situacao !== "Descartado";
  // O cabeçalho clicável.
  const cabecalho = criar("summary", "envio-cabecalho", "");
  const icone = criar("span", "envio-icone", "");
  icone.innerHTML = "<svg class=\"icone\"><use href=\"#icone-documento\"/></svg>";
  // O nome do arquivo no título, para a empresa reconhecer cada envio pelo arquivo que mandou,
  // com a versão quando a empresa enviou outro arquivo com o mesmo nome (ex.: "aurora.xlsx (v1)"); embaixo, o tipo, a
  // data, quantos e quem. Sem o nome (servidor antigo), o título volta a ser o tipo e a data.
  const textos = criar("span", "envio-textos", "");
  const tipo_e_data = envio.tipo + " · " + data_no_formato_brasileiro(envio.enviado_em);
  let titulo = tipo_e_data;
  let comeco_da_linha_de_baixo = "";
  if (envio.nome_arquivo) {
    titulo = envio.nome_arquivo;
    comeco_da_linha_de_baixo = tipo_e_data + " · ";
  }
  const titulo_do_envio = criar("span", "envio-titulo", titulo);
  titulo_do_envio.dataset.nomeDoArquivo = "";
  textos.append(titulo_do_envio);
  let quantos = envio.linhas + " funcionários no arquivo";
  if (envio.cadastrados !== null) {
    quantos = envio.cadastrados + " cadastrados de " + envio.linhas;
  }
  textos.append(criar("span", "envio-arquivos", comeco_da_linha_de_baixo + quantos + " · enviado por " +
    envio.enviado_por));
  // Envio de devolução (as pessoas que o banco devolveu de outro envio): de onde ele veio, no próprio cabeçalho
  if (envio.origem) {
    textos.append(montar_linha_da_origem(envio.origem));
  }
  // Envio descartado: quem descartou e quando, no próprio cabeçalho (o cartão descartado abre fechado)
  if (envio.descarte) {
    textos.append(criar("span", "nota-do-descarte", "Descartado por " + envio.descarte.por + " em " +
      data_e_hora_curtas(envio.descarte.quando) + ". Nada foi enviado ao banco."));
  }
  // O selo da situação e a setinha.
  const selo = criar("span", "selo " + classe_do_selo_do_envio(envio.situacao), envio.situacao);
  const seta = criar("span", "", "");
  seta.innerHTML = "<svg class=\"icone envio-seta\" aria-hidden=\"true\"><use href=\"#icone-abrir\"/></svg>";
  cabecalho.append(icone, textos, selo, seta.firstChild);
  cartao.append(cabecalho);
  // Devolvido pelo banco: o recado do especialista vem antes da linha do tempo.
  if (envio.motivo_da_devolucao) {
    cartao.append(criar("p", "aviso-incompleto", "O banco devolveu: \"" + envio.motivo_da_devolucao +
      "\" Ajuste em Cadastrar funcionários e envie de novo."));
  }
  // A linha do tempo: feitas em verde, a atual na cor da marca, a devolvida pelo banco em laranja, as que faltam em cinza.
  const linha_do_tempo = criar("ol", "linha-do-tempo", "");
  for (const etapa of envio.linha_do_tempo) {
    let classe = "passo";
    if (etapa.devolvido) {
      // Devolvida pelo banco (o envio inteiro ou algumas pessoas): bolinha laranja, com o detalhe embaixo (ADR-121)
      classe = "passo passo-devolvido";
    } else if (etapa.feito && etapa.parcial) {
      // Feita só em parte ("Contas abertas" com parte das contas, ou "Aprovação" com pessoas devolvidas): verde
      // clarinho, para não parecer concluída
      classe = "passo passo-feito passo-parcial";
    } else if (etapa.feito) {
      classe = "passo passo-feito";
    } else if (etapa.atual) {
      classe = "passo passo-atual";
    }
    const passo = criar("li", classe, "");
    passo.append(criar("span", "passo-marca", ""), criar("span", "passo-nome", etapa.nome),
      criar("span", "passo-data", data_e_hora_curtas(etapa.quando)));
    // O detalhe embaixo da data: "22 de 35 contas (63%)" em "Contas abertas"; "33 de 35 aprovadas · 2 devolvidas"
    // ou "Devolvido: 2 pessoas" em "Aprovação das contas enviadas"
    if (etapa.detalhe) {
      passo.append(criar("span", "passo-data passo-detalhe", etapa.detalhe));
    }
    linha_do_tempo.append(passo);
  }
  cartao.append(linha_do_tempo);
  // Cada rodada com o banco (enviado, devolvido, aprovado em parte, aprovado), só quando o envio já foi ao banco
  if (envio.idas_e_voltas && envio.idas_e_voltas.length > 0) {
    cartao.append(montar_idas_e_voltas(envio.idas_e_voltas));
  }
  // As ações do envio, numa linha no fim do cartão (css/acompanhar_painel.css): "Descartar este envio" no canto
  // esquerdo, em letra menor, e "Conferir arquivo" no canto direito, discreto
  const acoes = criar("div", "acoes-do-envio", "");
  // Envio que ainda não foi ao banco: dá para descartar (ex.: para mandar um arquivo mais organizado)
  if (SITUACOES_QUE_ESPERAM_A_EMPRESA.includes(envio.situacao)) {
    acoes.append(botao_de_descartar_o_envio(envio));
  }
  // Colunas ainda por conferir: a janela do envio abre nele (js/novo_envio.js); o resto se resolve aqui mesmo
  if (SITUACOES_DO_ACEITE_DAS_COLUNAS.includes(envio.situacao)) {
    const continuar = criar("a", "link-conferir-arquivo", "Conferir arquivo");
    continuar.href = "cadastrar.html?envio=" + encodeURIComponent(envio.processamento_id);
    continuar.dataset.continuarEnvio = envio.processamento_id;
    // Ao passar o mouse, o que o link faz por inteiro
    continuar.title = "Conferir as colunas deste envio";
    acoes.append(continuar);
  }
  // Sem nenhuma ação (o envio já foi ao banco), a linha não entra
  if (acoes.children.length > 0) {
    cartao.append(acoes);
  }
  return cartao;
}

// ===== Idas e voltas com o banco (ADR-121: o banco devolve só algumas pessoas) =====

// Os tipos de ida e volta que o servidor manda, cada um com a sua cor de bolinha (os outros ficam cinza).
const TIPOS_DE_IDA_E_VOLTA = ["enviado", "devolvido", "aprovado_em_parte", "aprovado"];

/**
 * A linha do cabeçalho de um envio de devolução, dizendo de que envio as pessoas vieram.
 *
 * Recebe: origem — {processamento_id, enviado_em, texto}. Devolve: o elemento <span>.
 * Exemplo: "Devolução do envio de 28/09 (2 pessoas)".
 */
function montar_linha_da_origem(origem) {
  // O texto já vem pronto do servidor (com singular e plural certos)
  const linha = criar("span", "nota-da-origem", origem.texto);
  // A marca que os roteiros de clique procuram
  linha.dataset.origemDoEnvio = origem.processamento_id;
  return linha;
}

/**
 * Escreve a data e a hora de uma ida e volta no jeito curto do bloco, no horário local.
 *
 * Recebe: texto — data e hora no formato do servidor (ex.: "2026-09-28T13:10:00+00:00"), ou null.
 * Devolve: o texto curto, ou "" se não houver data. Exemplo: "28/09 às 10h10".
 */
function data_da_ida_e_volta(texto) {
  // Sem data: nada.
  if (!texto) {
    return "";
  }
  // O navegador converte do horário universal para o horário do computador.
  const momento = new Date(texto);
  const dia_e_mes_da_rodada = momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  // A hora e os minutos com dois dígitos cada ("09" e "05"), para ficar "09h05"
  const hora = String(momento.getHours()).padStart(2, "0");
  const minutos = String(momento.getMinutes()).padStart(2, "0");
  return dia_e_mes_da_rodada + " às " + hora + "h" + minutos;
}

/**
 * Monta o bloco "Idas e voltas com o banco": uma linha por rodada, com a bolinha do tipo, a data curta e o texto.
 *
 * Recebe: idas_e_voltas — [{quando, tipo, texto}] (tipo: enviado, devolvido, aprovado_em_parte ou aprovado).
 * Devolve: o elemento <section>.
 * Exemplo de linha: "28/09 às 10h10 · O banco aprovou 33 e devolveu 2 (Ana Souza: Confirmar o salário; ...)".
 */
function montar_idas_e_voltas(idas_e_voltas) {
  // O bloco, com o título em cima
  const bloco = criar("section", "idas-e-voltas", "");
  bloco.dataset.idasEVoltas = "";
  bloco.append(criar("h4", "idas-e-voltas-titulo", "Idas e voltas com o banco"));
  // A lista, da rodada mais antiga para a mais nova (a ordem em que o servidor manda)
  const lista = criar("ol", "idas-e-voltas-lista", "");
  for (const rodada of idas_e_voltas) {
    lista.append(montar_linha_da_ida_e_volta(rodada));
  }
  bloco.append(lista);
  return bloco;
}

/**
 * Monta uma linha do bloco "Idas e voltas com o banco".
 *
 * Recebe: rodada — {quando, tipo, texto}. Devolve: o elemento <li>.
 * A cor da bolinha segue a da linha do tempo: marca = enviado, laranja = devolvido, verde clarinho = aprovado em
 * parte, verde = aprovado.
 */
function montar_linha_da_ida_e_volta(rodada) {
  // A classe da cor só para os tipos conhecidos (um tipo novo fica com a bolinha cinza, sem quebrar a tela)
  let classe = "ida-e-volta";
  if (TIPOS_DE_IDA_E_VOLTA.includes(rodada.tipo)) {
    classe = classe + " ida-e-volta-" + rodada.tipo;
  }
  const linha = criar("li", classe, "");
  // O tipo fica guardado na linha: os roteiros de clique conferem por ele
  linha.dataset.idaEVolta = rodada.tipo;
  // A bolinha, a data curta e o texto que o servidor mandou
  linha.append(criar("span", "ida-e-volta-marca", ""), criar("span", "ida-e-volta-quando", data_da_ida_e_volta(rodada.quando)),
    criar("span", "ida-e-volta-texto", rodada.texto));
  return linha;
}

/**
 * "Descartar este envio": a janela pergunta e explica o que acontece (js/descartar_envio.js). Descartou: as listas
 * da página são atualizadas (o envio passa a aparecer como "Descartado") e o aviso aparece em cima dos envios.
 *
 * Recebe: envio. Devolve: o botão.
 */
function botao_de_descartar_o_envio(envio) {
  // Com cara de link e em letra menor (css/acompanhar_painel.css): fica no canto esquerdo da linha das ações
  const botao = criar("button", "botao-nome botao-descartar-envio", "Descartar este envio");
  botao.type = "button";
  botao.addEventListener("click", async function () {
    const descartou = await perguntar_e_descartar(envio.processamento_id);
    if (!descartou) {
      return;
    }
    // A tela inteira, inclusive os números do alto (o envio descartado sai de "em andamento")
    recarregar_a_tela_inteira();
    document.querySelector("[data-aviso-descartado]").hidden = false;
  });
  return botao;
}

/**
 * Busca na API os envios de verdade da empresa logada e troca os exemplos por eles.
 *
 * Recebe: nada. Devolve: nada. Sem servidor (ou sem sessão), os exemplos continuam.
 */
async function carregar_envios_de_verdade() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // A primeira página (os 5 mais recentes); "Mostrar mais envios" busca as seguintes.
  await buscar_pagina_de_envios(0);
}

/**
 * Recarrega a tela inteira: pendências, envios, funcionários, os números do alto e os prontos para o banco.
 *
 * Recebe: nada. Devolve: uma promessa (espera as pendências, que são o que a pessoa está olhando).
 * É o único jeito de refazer a tela depois de uma mudança, para nenhuma ação esquecer uma parte (ex.: um descarte
 * que refizesse só a lista deixaria os números do alto velhos). Usada depois de uma correção pela tela, de
 * uma proposta do agente aplicada (js/assistente_de_correcao.js), de um descarte, ao fechar a janela "Cadastrar
 * funcionários" e na atualização automática.
 * A grade dos funcionários é buscada JUNTO com as pendências, e não depois delas (ADR-138): com a IA de verdade, a
 * lista de pendências pode levar alguns segundos (a IA escreve as perguntas novas), e a grade ficaria esse tempo
 * todo com o valor antigo.
 */
async function recarregar_a_tela_inteira() {
  // A grade sai na frente: não espera a lista de pendências
  carregar_funcionarios_de_verdade();
  await carregar_pendencias_de_verdade();
  carregar_envios_de_verdade();
  carregar_resumo_de_verdade();
  // Uma pendência resolvida pode deixar um envio pronto para o banco
  carregar_prontos_de_verdade();
}

/**
 * Monta o cartão de uma pendência de verdade, no mesmo formato dos exemplos (conta nos filtros e no resumo).
 *
 * Recebe: pendencia — um item de /api/empresa/pendencias. Devolve: o elemento <article>.
 * O cartão é uma conversa com o Agente de validação: o nome e o campo, a pergunta
 * num balão do agente, as respostas rápidas, a caixa para responder e o arquivo com a data
 * (js/assistente_de_correcao.js).
 */
function montar_cartao_de_pendencia(pendencia, nomes_dos_grupos) {
  // O cartão, com o tipo usado pelos filtros ("corrigir" ou "confirmar").
  const cartao = criar("article", "ajuste", "");
  cartao.dataset.pendencia = "";
  cartao.dataset.tipoPendencia = pendencia.tipo;
  // O envio (arquivo) da pendência: o filtro por arquivo usa
  cartao.dataset.arquivoPendencia = pendencia.processamento_id;
  // A chave da conversa: o aviso "Resolvido agora" sabe quais pendências continuam na lista
  cartao.dataset.chavePendencia = chave_da_conversa(pendencia);
  // A linha cinza de baixo: o arquivo e o dia do envio (ex.: "folha_setembro.xlsx · 24/09")
  const pendencia_do_cartao = Object.assign({}, pendencia);
  pendencia_do_cartao.origem = pendencia.nome_arquivo + " · " + dia_e_mes(pendencia.enviado_em);
  // O cartão do grupo vale por todas as pessoas dele nas contagens (os números batem com as outras telas)
  if (esta_no_modo_grupo(pendencia)) {
    cartao.dataset.quantidade = String(pendencia.grupo.quantidade);
    pendencia_do_cartao.nomes_do_grupo = nomes_dos_grupos[pendencia.grupo.chave] || [];
  }
  // O cartão da lista é compacto (ADR-138): a conversa abre no painel do lado (js/painel_da_conversa.js), que monta
  // o cartão inteiro a partir desta pendência
  cartao.classList.add("ajuste-compacto");
  cartao.pendencia_do_cartao = pendencia_do_cartao;
  cartao.append(...partes_do_cartao_compacto(pendencia_do_cartao));
  return cartao;
}

/**
 * As partes do cartão compacto da lista (ADR-138): o título (com o
 * selo "Pedido do banco" e o botão da ficha), o problema, a pergunta do agente em até 2 linhas, o "Abrir a conversa" e
 * o arquivo. A conversa em si (a caixa, as respostas rápidas, os botões do grupo) fica no painel do lado.
 *
 * Recebe: pendencia_do_cartao. Devolve: a lista de elementos.
 */
function partes_do_cartao_compacto(pendencia_do_cartao) {
  // O cartão inteiro, do mesmo jeito que o painel monta (js/assistente_de_correcao.js); a lista fica só com o resumo
  const partes = montar_cartao_da_pendencia(pendencia_do_cartao, recarregar_a_tela_inteira);
  const compacto = [];
  let pergunta = "";
  for (const parte of partes) {
    // A conversa não fica na lista: dela, só a pergunta do agente, para a prévia
    if (parte.classList.contains("conversa-ia-pendencia")) {
      pergunta = parte.dados_da_pendencia.pergunta || parte.dados_da_pendencia.problema || "";
      continue;
    }
    // O título, o problema e o arquivo ficam; os botões do grupo vão para o painel
    const fica = parte.classList.contains("ajuste-cabecalho") || parte.classList.contains("ajuste-problema")
      || parte.classList.contains("ajuste-origem");
    if (fica) {
      compacto.push(parte);
    }
  }
  // A prévia da pergunta e o botão, antes da linha cinza do arquivo (que é sempre a última, quando existe)
  const previa = criar("p", "ajuste-previa", pergunta);
  previa.dataset.previaDaPergunta = "";
  const botao = criar("button", "botao-abrir-conversa", "Abrir a conversa ›");
  botao.type = "button";
  botao.dataset.abrirConversa = "";
  const ultima = compacto[compacto.length - 1];
  if (ultima && ultima.classList.contains("ajuste-origem")) {
    compacto.splice(compacto.length - 1, 0, previa, botao);
  } else {
    compacto.push(previa, botao);
  }
  return compacto;
}

/**
 * Diz se a pendência não ganha cartão próprio porque já está no cartão do grupo dela: ela faz parte de um grupo que
 * aparece junto (a pessoa não pediu "Responder uma a uma") e não é quem representa o grupo.
 *
 * Recebe: pendencia — um item de /api/empresa/pendencias. Devolve: true ou false.
 */
function fica_no_cartao_do_grupo(pendencia) {
  return esta_no_modo_grupo(pendencia) && pendencia.linha !== pendencia.grupo.linha_do_representante;
}

/**
 * As pessoas de cada grupo, na ordem da lista (para o "Ver quem são" do cartão do grupo: cada nome abre a ficha).
 *
 * Recebe: pendencias — os itens de /api/empresa/pendencias. Devolve: {chave do grupo: [{nome, linha}]}.
 */
function nomes_de_cada_grupo(pendencias) {
  const nomes = {};
  for (const pendencia of pendencias) {
    if (!pendencia.grupo) {
      continue;
    }
    if (!(pendencia.grupo.chave in nomes)) {
      nomes[pendencia.grupo.chave] = [];
    }
    nomes[pendencia.grupo.chave].push({ nome: pendencia.nome, linha: pendencia.linha });
  }
  return nomes;
}

/**
 * Quantas pendências um cartão representa: 1, ou o número de pessoas no cartão do grupo.
 *
 * Recebe: cartao — o <article> da pendência. Devolve: o número.
 */
function pendencias_do_cartao(cartao) {
  return Number(cartao.dataset.quantidade || 1);
}

/**
 * Soma as pendências dos cartões que casam com o seletor (o cartão do grupo conta cada pessoa dele).
 *
 * Recebe: seletor — o seletor CSS dos cartões. Devolve: o total.
 */
function somar_pendencias(seletor) {
  let total = 0;
  for (const cartao of document.querySelectorAll(seletor)) {
    total = total + pendencias_do_cartao(cartao);
  }
  return total;
}

/**
 * O dia e o mês de uma data do banco de dados. Ex.: "2026-09-24T10:31:00" → "24/09".
 *
 * Recebe: texto — a data no formato ano-mês-dia (ou vazio). Devolve: "dd/mm" (ou "").
 */
function dia_e_mes(texto) {
  // A data brasileira inteira ("24/09/2026") sem o ano
  return data_no_formato_brasileiro(texto).slice(0, 5);
}

// ===== O cartão resolvido que fica à vista, e a lista "Resolvidas" =====

// Quanto tempo o cartão resolvido leva para deslizar para fora (o mesmo da animação em css/estilos.css).
const TEMPO_DA_SAIDA_DO_RESOLVIDO = 300;
// Se o último movimento da pessoa foi no teclado (o foco que chega por Tab também conta como "mexer no cartão").
let ultimo_movimento_pelo_teclado = false;

/**
 * Cada cartão da lista pela chave da conversa, na ordem da tela.
 *
 * Recebe: lista — o elemento da lista das pendências. Devolve: um Map {chave: cartão}.
 */
function cartoes_pela_chave(lista) {
  const cartoes = new Map();
  for (const cartao of lista.querySelectorAll("[data-chave-pendencia]")) {
    cartoes.set(cartao.dataset.chavePendencia, cartao);
  }
  return cartoes;
}

/**
 * Põe de volta, no mesmo lugar, os cartões que a conversa acabou de resolver e que continuam à vista.
 *
 * Recebe: lista — a lista já refeita com as pendências abertas; ordem_antiga — as chaves dos cartões antes de refazer.
 * Devolve: nada.
 * O cartão resolvido não está mais entre as pendências do servidor; ele volta a partir do que a conversa guardou
 * (resolvidos_agora, em js/assistente_de_correcao.js), logo depois do cartão que vinha antes dele. Ele sai quando a
 * pessoa mexe em outro cartão ou troca o filtro (dispensar_os_resolvidos_a_vista).
 */
function repor_os_resolvidos_a_vista(lista, ordem_antiga) {
  const abertas = cartoes_pela_chave(lista);
  // O último cartão que ficou na lista, andando pela ordem de antes (é depois dele que o resolvido entra)
  let anterior = null;
  for (const chave of ordem_antiga) {
    // Continua aberta: vira a referência para o próximo
    if (abertas.has(chave)) {
      anterior = abertas.get(chave);
      continue;
    }
    // Não foi resolvida pela conversa agora (ex.: saiu por outro motivo): não volta
    if (!(chave in resolvidos_agora)) {
      continue;
    }
    const cartao = montar_cartao_de_pendencia(resolvidos_agora[chave].pendencia, {});
    marcar_como_resolvido_a_vista(cartao);
    // Logo depois do anterior, ou no começo da lista
    if (anterior) {
      anterior.after(cartao);
    } else {
      lista.prepend(cartao);
    }
    anterior = cartao;
  }
}

/**
 * Deixa o cartão com cara de resolvido: a faixa verde, o selo "✓ Resolvida" e sem a caixa e as respostas rápidas
 * (css/estilos.css). A conversa, com o "Pronto: ..." e o Desfazer, continua à vista.
 *
 * Recebe: cartao — o <article> da pendência. Devolve: nada.
 */
function marcar_como_resolvido_a_vista(cartao) {
  cartao.classList.add("ajuste-resolvido");
  cartao.dataset.resolvidoAVista = "";
  cartao.querySelector(".ajuste-cabecalho").append(criar("span", "selo-resolvida", "✓ Resolvida"));
}

/**
 * Tira da tela os cartões resolvidos que ainda estavam à vista: eles deslizam para fora e passam a morar em
 * "Resolvidas" (a lista das resolvidas já os traz, do servidor).
 *
 * Recebe: cartao_que_fica — o cartão resolvido em que a pessoa mexeu (ele não sai), ou null. Devolve: nada.
 */
function dispensar_os_resolvidos_a_vista(cartao_que_fica) {
  // Com "reduzir movimento" ligado no computador, sai na hora
  let tempo_da_saida = TEMPO_DA_SAIDA_DO_RESOLVIDO;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    tempo_da_saida = 0;
  }
  for (const cartao of document.querySelectorAll("[data-lista-pendencias] [data-resolvido-a-vista]")) {
    // O cartão em que a pessoa mexeu, e o que já está saindo, ficam como estão
    if (cartao === cartao_que_fica || cartao.classList.contains("ajuste-saindo")) {
      continue;
    }
    // Não volta mais quando a lista for refeita
    delete resolvidos_agora[cartao.dataset.chavePendencia];
    cartao.classList.add("ajuste-saindo");
    // Terminada a animação, o cartão sai e a lista se ajusta (o "Tudo em dia!" aparece se não sobrou nenhuma)
    setTimeout(function () {
      cartao.remove();
      atualizar_total_de_pendencias();
      // Era o cartão da conversa aberta no painel: a conversa fecha
      fechar_se_o_cartao_escolhido_saiu();
    }, tempo_da_saida);
  }
}

/**
 * A pessoa mexeu num cartão da lista das pendências: se foi em outro cartão, os resolvidos à vista saem.
 *
 * Recebe: cartao — o cartão em que ela clicou ou que ganhou o foco (null fora de um cartão). Devolve: nada.
 */
function quando_mexe_num_cartao(cartao) {
  // Fora de um cartão (ex.: o espaço entre eles): nada
  if (!cartao) {
    return;
  }
  // Mexer no próprio cartão resolvido (ex.: o Desfazer) não o tira da tela
  if (cartao.hasAttribute("data-resolvido-a-vista")) {
    dispensar_os_resolvidos_a_vista(cartao);
    return;
  }
  dispensar_os_resolvidos_a_vista(null);
}

/**
 * Liga as escutas que tiram o cartão resolvido da tela quando a pessoa vai para outro cartão.
 *
 * Recebe: nada. Devolve: nada.
 * O cartão é achado NA HORA do clique (a conversa pode redesenhar o botão clicado logo em seguida, e aí ele já não
 * estaria dentro do cartão), mas a saída acontece DEPOIS de o clique terminar (setTimeout): assim o botão recebe o
 * clique antes de a lista se mexer. O foco conta só quando chega pelo teclado (pelo mouse, o clique já cuida).
 */
function preparar_a_saida_dos_resolvidos() {
  const lista = document.querySelector("[data-lista-pendencias]");
  document.addEventListener("keydown", function () {
    ultimo_movimento_pelo_teclado = true;
  });
  document.addEventListener("pointerdown", function () {
    ultimo_movimento_pelo_teclado = false;
  });
  // A fase de captura (true): o cartão é achado antes de o botão clicado ser redesenhado
  lista.addEventListener("click", function (evento) {
    const cartao = evento.target.closest("[data-pendencia]");
    setTimeout(function () {
      quando_mexe_num_cartao(cartao);
    }, 0);
  }, true);
  lista.addEventListener("focusin", function (evento) {
    if (ultimo_movimento_pelo_teclado) {
      quando_mexe_num_cartao(evento.target.closest("[data-pendencia]"));
    }
  });
}

/**
 * Diz se o título da resolvida já diz qual é o campo: o título novo começa com "Ajuste" ou "Conferir"; o das
 * conversas guardadas antes desse formato é só o nome da pessoa.
 *
 * Recebe: titulo. Devolve: true ou false.
 */
function titulo_ja_diz_o_campo(titulo) {
  const texto = titulo || "";
  return texto.startsWith("Ajuste") || texto.startsWith("Conferir");
}

/**
 * Monta o cartão de uma pendência já resolvida (filtro "Resolvidas"): de quem, o campo, o que mudou, quando e por quem,
 * e o "Ver a conversa", que abre a conversa guardada no painel do lado (ADR-138).
 *
 * Recebe: resolvida — um item de /api/empresa/pendencias/resolvidas. Devolve: o <article>.
 */
function montar_cartao_de_resolvida(resolvida) {
  const cartao = criar("article", "ajuste ajuste-resolvido ajuste-da-lista-resolvidas", "");
  cartao.dataset.resolvida = "";
  cartao.dataset.chavePendencia = resolvida.chave;
  cartao.dataset.arquivoPendencia = resolvida.processamento_id;
  // O grupo resolvido vale por todas as pessoas dele no número do filtro
  cartao.dataset.quantidade = String(resolvida.quantidade || 1);
  // Em cima: o título do ajuste (ex.: 'Ajuste na informação "Estado civil" de Ana Lima'); numa conversa antiga, o
  // título é só o nome da pessoa, e o campo continua à direita
  const cabecalho = criar("div", "ajuste-cabecalho", "");
  cabecalho.append(criar("span", "ajuste-titulo", resolvida.titulo));
  if (resolvida.nome_do_campo && !titulo_ja_diz_o_campo(resolvida.titulo)) {
    cabecalho.append(criar("span", "ajuste-campo", resolvida.nome_do_campo));
  }
  // O que mudou e quem resolveu, quando
  const resumo = criar("p", "resumo-da-resolvida", resolvida.resumo);
  resumo.dataset.resumoDaResolvida = "";
  const quem_e_quando = criar("p", "quem-resolveu",
    "Resolvida em " + data_e_hora_curtas(resolvida.resolvida_em) + " por " + resolvida.resolvida_por);
  // A conversa guardada abre no painel do lado (ADR-138; js/painel_da_conversa.js), que a monta a partir da resolvida
  cartao.resolvida = resolvida;
  const botao = criar("button", "botao-nome", "Ver a conversa (" + resolvida.conversa.length + ")");
  botao.type = "button";
  botao.dataset.verAConversa = "";
  botao.dataset.abrirConversa = "";
  // Embaixo, cinza: o arquivo e o dia do envio
  const origem = criar("p", "ajuste-origem", resolvida.nome_arquivo + " · " + dia_e_mes(resolvida.enviado_em));
  cartao.append(cabecalho, resumo, quem_e_quando, botao, origem);
  return cartao;
}

/**
 * Busca na API as pendências resolvidas pela conversa (enquanto o arquivo não foi ao banco) e monta a lista delas.
 *
 * Recebe: nada. Devolve: uma promessa. Com o servidor em erro, a lista avisa e o número do filtro fica em "—".
 */
async function carregar_resolvidas_de_verdade() {
  const lista = document.querySelector("[data-lista-resolvidas]");
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/empresa/pendencias/resolvidas");
    if (!resposta.ok) {
      mostrar_resolvidas_indisponiveis();
      return;
    }
    const resolvidas = await resposta.json();
    lista.removeAttribute("data-indisponivel");
    lista.replaceChildren();
    for (const resolvida of resolvidas) {
      lista.append(montar_cartao_de_resolvida(resolvida));
    }
  } catch (erro) {
    mostrar_resolvidas_indisponiveis();
  }
}

/**
 * A lista das resolvidas não carregou: o aviso no lugar dela.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_resolvidas_indisponiveis() {
  const lista = document.querySelector("[data-lista-resolvidas]");
  lista.setAttribute("data-indisponivel", "");
  const texto_do_erro = "Não foi possível carregar as resolvidas agora.";
  lista.replaceChildren(criar("p", "painel-vazio painel-vazio-neutro", texto_do_erro));
}

// ===== Rodapé das pendências: descartar a leitura =====

/**
 * Os arquivos a que o rodapé se refere: o do filtro ou, com "Todos os arquivos", os que têm pendência na lista.
 *
 * Recebe: nada. Devolve: [{processamento_id, nome_arquivo}] (vazio sem pendência de verdade na tela).
 */
function arquivos_do_rodape() {
  const escolhido = document.querySelector("[data-filtro-arquivo-pendencias]").value;
  // Um arquivo escolhido no filtro: é ele
  if (escolhido) {
    return [{ processamento_id: escolhido, nome_arquivo: nomes_dos_arquivos_com_pendencia[escolhido] || "Este arquivo" }];
  }
  // "Todos os arquivos": cada arquivo com cartão na lista, uma vez só, na ordem da lista
  const arquivos = [];
  const ja_contados = [];
  for (const cartao of document.querySelectorAll("[data-lista-pendencias] [data-arquivo-pendencia]")) {
    const processamento_id = cartao.dataset.arquivoPendencia;
    if (!ja_contados.includes(processamento_id)) {
      ja_contados.push(processamento_id);
      arquivos.push({ processamento_id: processamento_id, nome_arquivo: nomes_dos_arquivos_com_pendencia[processamento_id] });
    }
  }
  return arquivos;
}

/**
 * Escreve no rodapé a que arquivo os botões se referem, e esconde o rodapé sem pendência na tela.
 *
 * Recebe: nada. Devolve: nada. Aberta como arquivo (o protótipo), o rodapé de exemplo fica como está.
 */
function atualizar_rodape_das_pendencias() {
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  const rodape = document.querySelector("[data-rodape-pendencias]");
  const texto = document.querySelector("[data-arquivo-do-rodape]");
  const arquivos = arquivos_do_rodape();
  // Sem arquivo (ou com o "Tudo em dia!" no lugar da lista): nada a descartar por aqui
  rodape.hidden = arquivos.length === 0 || document.querySelector("[data-lista-pendencias]").hidden;
  // Um arquivo: o nome dele; vários: a janela vai perguntar qual
  if (arquivos.length === 1) {
    texto.textContent = "Arquivo: " + arquivos[0].nome_arquivo;
  } else {
    texto.textContent = arquivos.length + " arquivos na lista. Ao descartar, você escolhe qual.";
  }
  marcar_como_carregado(texto);
}

/**
 * Os botões do rodapé: descarta a leitura do arquivo (perguntando qual, se houver vários) e, no segundo botão, já
 * abre um envio novo.
 *
 * Recebe: e_enviar_outro — true no "Descartar a leitura e enviar outro arquivo". Devolve: uma promessa.
 */
async function descartar_pelo_rodape(e_enviar_outro) {
  // Aberta como arquivo: não há servidor
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  const arquivos = arquivos_do_rodape();
  // Um arquivo: a janela de sempre; vários: a janela pergunta qual
  let descartado = null;
  if (arquivos.length === 1) {
    const descartou = await perguntar_e_descartar(arquivos[0].processamento_id);
    if (descartou) {
      descartado = arquivos[0].processamento_id;
    }
  } else if (arquivos.length > 1) {
    descartado = await perguntar_qual_arquivo_e_descartar(arquivos);
  }
  // Desistiu: nada muda
  if (descartado === null) {
    return;
  }
  await mostrar_a_tela_sem_o_arquivo_descartado(e_enviar_outro);
}

/**
 * Depois de descartar a leitura de um arquivo: a lista volta a "Todos os arquivos", a tela é refeita, o aviso
 * "descartado" aparece e, no "e enviar outro arquivo", abre um envio novo.
 *
 * Recebe: e_enviar_outro — true para já abrir a janela "Cadastrar funcionários". Devolve: uma promessa.
 */
async function mostrar_a_tela_sem_o_arquivo_descartado(e_enviar_outro) {
  // O arquivo descartado sai do filtro: a lista volta a "Todos os arquivos"
  document.querySelector("[data-filtro-arquivo-pendencias]").value = "";
  await recarregar_a_tela_inteira();
  document.querySelector("[data-aviso-descartado]").hidden = false;
  // "e enviar outro arquivo": abre a janela "Cadastrar funcionários"
  if (e_enviar_outro) {
    abrir_um_envio_novo();
  }
}

/**
 * O botão "Descartar a leitura e enviar outro arquivo" dentro de um cartão (a coluna que falta de uma informação de
 * cada pessoa, como o CPF: só um arquivo novo resolve). O cartão avisa com o evento
 * "acao-do-cartao-da-pendencia" (js/assistente_de_correcao.js), e a tela descarta a leitura DAQUELE arquivo, com a
 * mesma janela que pergunta e explica (js/descartar_envio.js).
 *
 * Recebe: evento — o detail traz {acao, processamento_id}. Devolve: uma promessa.
 */
async function fazer_a_acao_do_cartao(evento) {
  const acao = evento.detail.acao;
  // Só esta ação existe por enquanto; outra, desconhecida, não faz nada
  if (acao !== "descartar_e_enviar_outro") {
    return;
  }
  // Aberta como arquivo: não há servidor
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // A janela pergunta; desistiu, nada muda
  const descartou = await perguntar_e_descartar(evento.detail.processamento_id);
  if (!descartou) {
    return;
  }
  await mostrar_a_tela_sem_o_arquivo_descartado(true);
}

/**
 * Abre um envio novo: a janela "Cadastrar funcionários" do botão do canto (js/novo_envio.js) ou, sem ela, a tela.
 *
 * Recebe: nada. Devolve: nada.
 */
function abrir_um_envio_novo() {
  const botao_do_canto = document.querySelector(".botao-cadastrar-funcionarios");
  if (botao_do_canto) {
    botao_do_canto.click();
    return;
  }
  window.location.href = "cadastrar.html";
}

/**
 * Transforma o "detail" de um erro da API em texto para a pessoa.
 *
 * Recebe: detalhe — texto (erro de regra) ou lista (formato do pedido errado, ex.: campo vazio).
 * Devolve: o texto da mensagem.
 */
function explicacao_do_erro(detalhe) {
  // Erro de regra: já vem em texto simples.
  if (typeof detalhe === "string") {
    return detalhe;
  }
  // Formato do pedido: algum campo faltou.
  return "Preencha os campos antes de salvar.";
}

/**
 * Busca na API as pendências de verdade da empresa logada e troca os exemplos por elas.
 *
 * Recebe: nada. Devolve: nada. Sem servidor (ou sem sessão), os exemplos continuam.
 */
async function carregar_pendencias_de_verdade() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/empresa/pendencias");
    // Recusado: o cartão e a lista avisam que não carregou (nunca ficam com as pendências de exemplo)
    if (!resposta.ok) {
      mostrar_pendencias_indisponiveis();
      return;
    }
    const pendencias = await resposta.json();
    // Os nomes de cada grupo (várias pessoas com o mesmo valor fora da lista), para o "Ver quem são" do cartão
    const nomes_dos_grupos = nomes_de_cada_grupo(pendencias);
    // A ordem dos cartões antes de refazer a lista (o resolvido à vista volta no mesmo lugar)
    const lista = document.querySelector("[data-lista-pendencias]");
    const ordem_antiga = Array.from(cartoes_pela_chave(lista).keys());
    // Esvazia a lista de exemplos e põe as pendências de verdade: um cartão por pessoa, ou um só para o grupo.
    lista.replaceChildren();
    for (const pendencia of pendencias) {
      if (fica_no_cartao_do_grupo(pendencia)) {
        continue;
      }
      lista.append(montar_cartao_de_pendencia(pendencia, nomes_dos_grupos));
    }
    // O que a conversa acabou de resolver continua à vista, com o "Pronto: ..." e o Desfazer, até ela ir para outro
    repor_os_resolvidos_a_vista(lista, ordem_antiga);
    // As resolvidas (filtro "Resolvidas"), com a conversa guardada no servidor
    await carregar_resolvidas_de_verdade();
    // Os envios parados na conferência das colunas (o aviso e o botão para continuar; ADR-127)
    await carregar_envios_parados_nas_colunas();
    // O filtro por arquivo (com a escolha de antes)
    montar_filtro_de_arquivos(pendencias);
    // Refaz os números (resumo, filtros e atalho) e a vista do filtro escolhido ("Tudo em dia!" sem nenhuma aberta).
    atualizar_total_de_pendencias();
    // As pendências de verdade estão na tela: sai a barra de "carregando" da lista e dos números
    liberar_as_pendencias();
    // O painel do lado acompanha a lista: a conversa aberta volta com os dados novos, ou fecha se o cartão saiu
    refazer_o_painel_depois_da_lista();
  } catch (erro) {
    // Servidor fora do ar: o cartão e a lista avisam que não carregou.
    mostrar_pendencias_indisponiveis();
  }
}

/**
 * Tira a barra de "carregando" de tudo o que conta pendências: a lista, o 3º cartão, o atalho e os filtros.
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_as_pendencias() {
  marcar_como_carregado(document.querySelector("[data-lista-pendencias]"));
  marcar_todos_como_carregados("[data-cartao-pendencias] [data-aguarda-dado]");
  marcar_como_carregado(document.querySelector("[data-atalho-pendencias]"));
  marcar_todos_como_carregados("[data-contagem-tipo]");
}

/**
 * O servidor não respondeu na primeira carga: um traço no 3º cartão e no atalho, e o aviso na lista.
 *
 * Recebe: nada. Devolve: nada. Se as pendências de verdade já estavam na tela, elas ficam.
 */
function mostrar_pendencias_indisponiveis() {
  // Já tem dado de verdade: mantém.
  if (document.querySelector("[data-lista-pendencias]").hasAttribute("data-dado-pronto")) {
    return;
  }
  // Traço no número do cartão e no atalho; sem o "Resolver agora", que levaria a uma lista vazia.
  mostrar_dado_indisponivel(document.querySelector("[data-total-pendencias]"));
  mostrar_dado_indisponivel(document.querySelector("[data-atalho-pendencias]"));
  document.querySelector("[data-link-pendencias]").hidden = true;
  // Os filtros por tipo contavam os exemplos: saem os números.
  for (const contagem of document.querySelectorAll("[data-contagem-tipo]")) {
    contagem.textContent = "";
  }
  // Sem as pendências de verdade, não há arquivo para descartar por aqui (o rodapé de exemplo sai).
  document.querySelector("[data-rodape-pendencias]").hidden = true;
  marcar_como_carregado(document.querySelector("[data-arquivo-do-rodape]"));
  // A lista com o aviso, e o resto liberado.
  mostrar_lista_indisponivel(document.querySelector("[data-lista-pendencias]"));
  liberar_as_pendencias();
}

/**
 * Busca na API o resumo de verdade da empresa logada e troca os números de exemplo do alto da tela.
 *
 * Recebe: nada. Devolve: nada. Sem servidor (ou sem sessão), os números de exemplo continuam.
 * A abertura das contas vem do arquivo semanal do banco (services/contas_abertas.py): o total da empresa aqui (a
 * conta de cada pessoa vem na lista); antes do primeiro arquivo, a tela diz que o dado ainda não chegou.
 */
async function carregar_resumo_de_verdade() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/empresa/resumo");
    // Recusado: traço nos números (nunca os de exemplo)
    if (!resposta.ok) {
      mostrar_resumo_indisponivel();
      return;
    }
    const resumo = await resposta.json();
    // Cadastrados: o número de verdade, sem o selo de exemplo "+22 em setembro".
    document.querySelector("[data-resumo-aprovados]").textContent = resumo.cadastrados;
    document.querySelector("[data-selo-aprovados]").hidden = true;
    // Segundo cartão: as PESSOAS em análise pelo banco, o mesmo total do filtro "Em análise" da lista de funcionários
    // (e não os "envios em andamento", que somariam também os envios com pendência).
    document.querySelector("[data-resumo-andamento-valor]").textContent = resumo.pessoas_em_analise;
    document.querySelector("[data-resumo-andamento-legenda]").textContent = legenda_de_quem_esta_em_analise(resumo.pessoas_em_analise);
    // O selo "Retorno em até 1 dia útil" é só do exemplo: o prazo do banco não é assumido aqui.
    document.querySelector("[data-resumo-andamento-selo]").hidden = true;
    // Atalho "Envios" do topo.
    document.querySelector("[data-atalho-envios]").textContent = resumo.envios;
    // Abertura das contas: o total real, ou o aviso de que ainda não chegou.
    mostrar_contas_reais(resumo.contas);
    // Os números de verdade estão na tela: sai a barra de "carregando"
    liberar_os_numeros_do_resumo();
  } catch (erro) {
    // Servidor fora do ar: traço nos números.
    mostrar_resumo_indisponivel();
  }
}

/**
 * Tira a barra de "carregando" dos números que vêm do resumo: os cartões 1, 2 e 4, o atalho "Envios" e as contas.
 *
 * Recebe: nada. Devolve: nada. (O 3º cartão, das pendências, é liberado quando a lista de pendências chega.)
 */
function liberar_os_numeros_do_resumo() {
  // O 5º cartão (os cadastrados ainda sem conta) entra junto com o 4º, porque vem da mesma conta das contas abertas
  const seletores = ["[data-resumo-aprovados]", "[data-selo-aprovados]", "[data-resumo-andamento-valor]",
    "[data-resumo-andamento-legenda]", "[data-resumo-andamento-selo]", "[data-resumo-contas-valor]",
    "[data-resumo-contas-legenda]", "[data-resumo-sem-conta-valor]", "[data-resumo-sem-conta-legenda]",
    "[data-atalho-envios]", "[data-contas-total]", "[data-contas-por-unidade]"];
  // Cada um ganha a marca "pronto".
  for (const seletor of seletores) {
    marcar_como_carregado(document.querySelector(seletor));
  }
}

/**
 * O servidor não respondeu na primeira carga: traço nos números do alto e aviso na abertura das contas.
 *
 * Recebe: nada. Devolve: nada. Se os números de verdade já estavam na tela (ex.: falhou só a atualização
 * automática de 30 segundos), eles ficam.
 */
function mostrar_resumo_indisponivel() {
  // Já tem dado de verdade: mantém.
  if (document.querySelector("[data-resumo-aprovados]").hasAttribute("data-dado-pronto")) {
    return;
  }
  // Traço no lugar de cada número.
  const seletores = ["[data-resumo-aprovados]", "[data-resumo-andamento-valor]", "[data-resumo-contas-valor]",
    "[data-resumo-sem-conta-valor]", "[data-atalho-envios]"];
  for (const seletor of seletores) {
    mostrar_dado_indisponivel(document.querySelector(seletor));
  }
  // A legenda do 5º cartão sai do exemplo (ela trazia a porcentagem do protótipo)
  document.querySelector("[data-resumo-sem-conta-legenda]").textContent = LEGENDA_DOS_CADASTRADOS_SEM_CONTA;
  // Os selos de exemplo ("+22 em setembro", "Retorno em até 1 dia útil") saem.
  document.querySelector("[data-selo-aprovados]").hidden = true;
  document.querySelector("[data-resumo-andamento-selo]").hidden = true;
  // A abertura das contas: sem os números de exemplo, com o aviso de que não carregou.
  mostrar_contas_sem_dado();
  document.querySelector("[data-contas-poucos-titulo]").textContent = "Não foi possível carregar a abertura das contas";
  document.querySelector("[data-contas-poucos-texto]").textContent = "Atualize a página em instantes.";
  liberar_os_numeros_do_resumo();
}

/**
 * A legenda do segundo cartão, no singular ou no plural.
 *
 * Recebe: quantidade — quantas pessoas estão em análise pelo banco.
 * Devolve: o texto. Ex.: 1 → "pessoa em análise pelo banco"; 12 → "pessoas em análise pelo banco".
 */
function legenda_de_quem_esta_em_analise(quantidade) {
  // Uma pessoa só: singular.
  if (quantidade === 1) {
    return "pessoa em análise pelo banco";
  }
  // Zero ou mais de uma: plural.
  return "pessoas em análise pelo banco";
}

// A legenda do 5º cartão sem o número (o banco ainda não mandou o arquivo de contas, ou o servidor não respondeu).
const LEGENDA_DOS_CADASTRADOS_SEM_CONTA = "funcionários cadastrados ainda sem conta";

/**
 * Mostra, no 5º cartão do alto, quantos funcionários cadastrados ainda não abriram a conta (o número que só o painel
 * "Depois do cadastro" mostrava; o painel está oculto nesta versão).
 *
 * Recebe: quantidade — quantos ainda não abriram (null: o banco ainda não mandou o arquivo de contas); percentual — a
 * parte dos cadastrados que eles são (ex.: 22). Devolve: nada.
 * Ex.: (69, 22) → "69" e "funcionários cadastrados ainda sem conta (22%)"; (1, 3) → "1" e "funcionário cadastrado
 * ainda sem conta (3%)"; (null, null) → "—" e a legenda sem número.
 */
function mostrar_cadastrados_sem_conta(quantidade, percentual) {
  const valor = document.querySelector("[data-resumo-sem-conta-valor]");
  const legenda = document.querySelector("[data-resumo-sem-conta-legenda]");
  // Sem o arquivo de contas: um traço, nunca um número inventado
  if (quantidade === null) {
    valor.textContent = "—";
    legenda.textContent = LEGENDA_DOS_CADASTRADOS_SEM_CONTA;
    return;
  }
  valor.textContent = quantidade;
  // Uma pessoa só: a legenda no singular
  let texto_da_legenda = LEGENDA_DOS_CADASTRADOS_SEM_CONTA;
  if (quantidade === 1) {
    texto_da_legenda = "funcionário cadastrado ainda sem conta";
  }
  legenda.textContent = texto_da_legenda + " (" + percentual + "%)";
}

/**
 * Mostra a abertura das contas de verdade: os cartões do alto (o 4º e o 5º) e o painel "Abertura das contas" (oculto
 * nesta versão, mas preenchido, para voltar pronto).
 *
 * Recebe: contas — {arquivo_recebido, texto, percentual, com_conta, cadastrados} da API. Devolve: nada.
 * Sem percentual (o arquivo ainda não chegou): o aviso no lugar dos números.
 */
function mostrar_contas_reais(contas) {
  // Sem número para mostrar: o aviso de que o arquivo ainda não chegou.
  if (contas.percentual === null) {
    document.querySelector("[data-resumo-contas-valor]").textContent = "—";
    document.querySelector("[data-resumo-contas-legenda]").textContent = contas.texto;
    mostrar_cadastrados_sem_conta(null, null);
    mostrar_contas_sem_dado();
    return;
  }
  // Cartão do alto: o percentual da empresa inteira.
  document.querySelector("[data-resumo-contas-valor]").textContent = contas.percentual + "%";
  document.querySelector("[data-resumo-contas-legenda]").textContent = contas.texto;
  // O 5º cartão: os cadastrados que ainda não abriram a conta (o resto até 100%)
  mostrar_cadastrados_sem_conta(contas.cadastrados - contas.com_conta, 100 - contas.percentual);
  // Painel: o anel e as duas frases (sem a divisão por unidade e por envio, que a aplicação ainda não calcula).
  document.querySelector("[data-contas-total]").hidden = false;
  document.querySelector("[data-contas-por-unidade]").hidden = true;
  document.querySelector("[data-contas-por-envio]").hidden = true;
  document.querySelector("[data-contas-poucos]").hidden = true;
  document.querySelector("[data-contas-anel]").style.setProperty("--porcentagem", String(contas.percentual));
  document.querySelector("[data-contas-anel-numero]").textContent = contas.percentual + "%";
  const sem_conta = contas.cadastrados - contas.com_conta;
  const frase = document.querySelector("[data-contas-frase]");
  frase.replaceChildren(criar("strong", "", contas.com_conta + " de " + contas.cadastrados),
    document.createTextNode(" funcionários cadastrados já abriram a conta."));
  const frase_leve = document.querySelector("[data-contas-frase-leve]");
  frase_leve.replaceChildren(criar("strong", "", sem_conta + " (" + (100 - contas.percentual) + "%)"),
    document.createTextNode(" ainda não abriram: um lembrete ajuda."));
}

/**
 * No painel "Abertura das contas", troca os números de exemplo por um aviso de que o dado ainda não chegou.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_contas_sem_dado() {
  // Os blocos de números de exemplo somem.
  for (const seletor of ["[data-contas-total]", "[data-contas-por-unidade]", "[data-contas-por-envio]"]) {
    document.querySelector(seletor).hidden = true;
  }
  // O quadro de aviso aparece, com o texto de "ainda sem dado".
  document.querySelector("[data-contas-poucos]").hidden = false;
  document.querySelector("[data-contas-poucos-titulo]").textContent = "A abertura das contas ainda não chegou";
  document.querySelector("[data-contas-poucos-texto]").textContent =
    "Os números aparecem assim que o banco enviar o arquivo de contas abertas da sua equipe.";
}

// ============ LIGANDO TUDO ============

/**
 * Liga os botões, a busca e os filtros, e monta a tabela pela primeira vez.
 *
 * Recebe: nada. Devolve: nada.
 */
function iniciar_a_tela() {
  // Busca: refaz a tabela a cada letra digitada.
  document.querySelector("[data-busca]").addEventListener("input", atualizar_tabela);
  // Listas de situação e unidade.
  document.querySelector("[data-filtro-situacao]").addEventListener("change", atualizar_tabela);
  document.querySelector("[data-filtro-unidade]").addEventListener("change", atualizar_tabela);
  // "Limpar filtros": zera a busca e os dois filtros.
  document.querySelector("[data-limpar-filtros]").addEventListener("click", limpar_filtros);
  // Filtro das pendências por arquivo (trocar tira da tela os cartões que acabaram de ser resolvidos).
  document.querySelector("[data-filtro-arquivo-pendencias]").addEventListener("change", function () {
    dispensar_os_resolvidos_a_vista(null);
    aplicar_filtros_das_pendencias();
  });
  // O cartão resolvido sai quando a pessoa mexe em outro cartão.
  preparar_a_saida_dos_resolvidos();
  // A janela da conversa: o clique num cartão abre a conversa dele por cima da tela (js/painel_da_conversa.js).
  preparar_a_janela_da_conversa();
  // Os dois filtros das pendências: "Pendências em aberto" e "Resolvidas".
  for (const botao of document.querySelectorAll("[data-filtro-pendencia]")) {
    botao.addEventListener("click", function () {
      filtrar_pendencias(botao);
    });
  }
  // Só no protótipo: os botões dos cartões de exemplo resolvem a pendência de mentira. A escuta fica na lista
  // inteira (e não em cada botão): o clique "sobe" do botão até a lista.
  document.querySelector("[data-lista-pendencias]").addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-resolver-pendencia]");
    if (botao && !window.location.protocol.startsWith("http")) {
      resolver_pendencia(botao);
    }
  });
  // O rodapé das pendências: os dois jeitos de descartar a leitura.
  document.querySelector("[data-descartar-pelo-rodape]").addEventListener("click", function () {
    descartar_pelo_rodape(false);
  });
  document.querySelector("[data-descartar-e-enviar-outro]").addEventListener("click", function () {
    descartar_pelo_rodape(true);
  });
  // Baixar a lista.
  document.querySelector("[data-baixar-lista]").addEventListener("click", baixar_lista_em_csv);
  // Fechar a ficha: botão X e botão "Voltar".
  for (const botao of document.querySelectorAll("[data-fechar-ficha]")) {
    botao.addEventListener("click", fechar_ficha);
  }
  // Fechar a ficha clicando no fundo escurecido (o clique cai na própria janela, fora do conteúdo).
  const janela = document.getElementById("janela-ficha");
  janela.addEventListener("click", function (evento) {
    if (evento.target === janela) {
      fechar_ficha();
    }
  });
  // Envios: "Mostrar mais" e "Expandir todos / Recolher todos".
  document.querySelector("[data-mostrar-mais-envios]").addEventListener("click", mostrar_mais_envios);
  const botao_de_expandir = document.querySelector("[data-expandir-envios]");
  botao_de_expandir.addEventListener("click", function () {
    abrir_ou_fechar_todos_os_envios(botao_de_expandir);
  });
  // Primeira montagem: estados de exemplo (se pedidos no endereço), pendências, tabela e envios.
  simular_sem_pendencias_se_pedido();
  simular_muitas_pendencias_se_pedido();
  simular_casos_da_abertura_das_contas();
  mostrar_aviso_de_recebimento();
  atualizar_total_de_pendencias();
  atualizar_tabela();
  mostrar_envios();
  // Com a API ligada, troca os exemplos pelos dados de verdade da empresa logada.
  carregar_funcionarios_de_verdade();
  carregar_envios_de_verdade();
  carregar_pendencias_de_verdade();
  carregar_resumo_de_verdade();
  // O bloco "Pronto para enviar ao banco"
  preparar_prontos_para_o_banco();
  carregar_prontos_de_verdade();
  // Mantém a tela em dia sozinha: ao fechar a janela do envio, ao voltar para a aba e de tempos em tempos
  preparar_atualizacao_automatica();
}

// ============ ATUALIZAÇÃO AUTOMÁTICA (para os números do alto não ficarem parados) ============

// De quanto em quanto tempo os números do alto são buscados de novo, com a aba à vista: 30 segundos.
const INTERVALO_DA_ATUALIZACAO_AUTOMATICA = 30000;

/**
 * Diz se a pessoa está no meio de alguma coisa que refazer a tela atrapalharia.
 *
 * Recebe: nada. Devolve: true ou false.
 * Ex.: uma janela aberta (ficha, conferência, descarte), o cursor num campo, uma mensagem escrita numa conversa e
 * ainda não enviada, ou uma conversa esperando o agente. Refazer a lista de pendências nessa hora atrapalharia.
 */
function pessoa_esta_no_meio_de_algo() {
  // Alguma janela aberta na tela.
  if (document.querySelector("dialog[open]")) {
    return true;
  }
  // Alguma conversa com o agente esperando a resposta (o "Processando… N s").
  if (alguma_conversa_em_andamento()) {
    return true;
  }
  // Alguma pergunta de confirmação do agente esperando a escolha (ex.: "Sim, não cadastrar" / "Cancelar").
  if (alguma_confirmacao_aberta()) {
    return true;
  }
  // Alguma lista "Informar pessoa a pessoa" aberta num cartão (ADR-124): a pessoa está preenchendo.
  if (alguma_lista_pessoa_a_pessoa_aberta()) {
    return true;
  }
  // O cursor está num campo (escrevendo ou escolhendo).
  const campo_em_uso = document.activeElement;
  if (campo_em_uso && ["INPUT", "TEXTAREA", "SELECT"].includes(campo_em_uso.tagName)) {
    return true;
  }
  // Alguma mensagem escrita numa conversa e ainda não enviada (a conversa abre na janela [data-painel-da-conversa]).
  const campos_das_conversas = "[data-lista-pendencias] input, [data-lista-pendencias] textarea, " +
    "[data-painel-da-conversa] input, [data-painel-da-conversa] textarea";
  for (const campo of document.querySelectorAll(campos_das_conversas)) {
    if (campo.value !== "") {
      return true;
    }
  }
  // Nada em andamento.
  return false;
}

/**
 * Quando a pessoa volta para esta aba (ex.: depois de olhar outro sistema), traz a tela em dia.
 *
 * Recebe: nada. Devolve: nada.
 * No meio de alguma coisa, só os números do alto mudam; o resto espera, para não apagar o que ela está fazendo.
 */
function atualizar_ao_voltar_para_a_aba() {
  // A aba foi escondida (e não mostrada): nada a fazer.
  if (document.visibilityState !== "visible") {
    return;
  }
  // No meio de algo: só os números.
  if (pessoa_esta_no_meio_de_algo()) {
    carregar_resumo_de_verdade();
    return;
  }
  // Livre: a tela inteira.
  recarregar_a_tela_inteira();
}

/**
 * De tempos em tempos, busca de novo os números do alto (ex.: o banco aprovou um envio enquanto a tela estava aberta).
 *
 * Recebe: nada. Devolve: nada.
 * Só os números: é uma consulta leve e não mexe nas listas que a pessoa está olhando. Com a aba escondida, não busca.
 */
function atualizar_os_numeros_de_tempos_em_tempos() {
  // Ninguém está vendo a aba: não gasta consulta.
  if (document.visibilityState !== "visible") {
    return;
  }
  // Os números do alto.
  carregar_resumo_de_verdade();
}

/**
 * Liga as três atualizações automáticas da tela.
 *
 * Recebe: nada. Devolve: nada.
 * 1. Fechar a janela "Cadastrar funcionários" (js/novo_envio.js avisa com o evento "janela-do-envio-fechada"): o
 *    envio novo entra nos números e nas listas.
 * 2. Voltar para a aba: a tela é trazida em dia.
 * 3. A cada 30 segundos, com a aba à vista: os números do alto.
 */
function preparar_atualizacao_automatica() {
  // 1. A janela do envio foi fechada.
  document.addEventListener("janela-do-envio-fechada", recarregar_a_tela_inteira);
  // Um botão de ação dentro de um cartão (ex.: "Descartar a leitura e enviar outro arquivo")
  document.addEventListener("acao-do-cartao-da-pendencia", fazer_a_acao_do_cartao);
  // 2. A aba voltou a aparecer.
  document.addEventListener("visibilitychange", atualizar_ao_voltar_para_a_aba);
  // 3. O relógio dos números.
  setInterval(atualizar_os_numeros_de_tempos_em_tempos, INTERVALO_DA_ATUALIZACAO_AUTOMATICA);
}

// ============ PRONTO PARA ENVIAR AO BANCO (a lista pendente da empresa) ============

// Os envios prontos da última busca (a janela da conferência monta a grade de cada um).
let envios_prontos = [];

/**
 * Busca os envios sem pendência e mostra o bloco "Pronto para enviar ao banco" (some quando não há nenhum).
 *
 * Recebe: nada. Devolve: nada.
 */
async function carregar_prontos_de_verdade() {
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  try {
    const resposta = await fetch("/api/empresa/prontos_para_o_banco");
    if (!resposta.ok) {
      return;
    }
    envios_prontos = await resposta.json();
    const lista = document.querySelector("[data-lista-prontos]");
    lista.replaceChildren();
    let pessoas = 0;
    // Um item por envio: o arquivo, quando foi enviado, quantas pessoas vão e quantas ficam de fora (ADR-126)
    for (const pronto of envios_prontos) {
      let texto = pronto.nome_arquivo + " · enviado em " + data_no_formato_brasileiro(pronto.enviado_em) + " · " +
        quantidade_no_singular_ou_plural(pronto.pessoas, "pessoa", "pessoas");
      const de_fora = (pronto.ficam_de_fora || []).length;
      if (de_fora > 0) {
        texto = texto + " · " + quantidade_no_singular_ou_plural(de_fora, "fica de fora (já mandada antes)",
          "ficam de fora (já mandadas antes)");
      }
      lista.append(criar("li", "", texto));
      pessoas = pessoas + pronto.pessoas;
    }
    document.querySelector("[data-prontos]").hidden = envios_prontos.length === 0;
    // O atalho "Prontos para enviar" do "Ir para": só aparece com envio pronto, com o número de envios
    document.querySelector("[data-atalho-prontos]").hidden = envios_prontos.length === 0;
    document.querySelector("[data-atalho-contagem-prontos]").textContent = envios_prontos.length;
    document.querySelector("[data-enviar-prontos]").textContent =
      "Enviar ao banco (" + envios_prontos.length + " envio(s), " + pessoas + " pessoa(s))";
  } catch (erro) {
    // Servidor fora do ar: o bloco continua escondido.
  }
}

/**
 * Abre a janela da conferência: a grade completa de cada envio pronto, o aceite desmarcado e o envio desligado.
 *
 * Recebe: nada. Devolve: nada (espera as listas do servidor).
 */
async function abrir_conferencia_dos_prontos() {
  const janela = document.getElementById("janela-conferir-envio");
  const caixa = document.querySelector("[data-conferi-prontos]");
  // Cada abertura começa sem o aceite: a pessoa confere de novo
  caixa.checked = false;
  document.querySelector("[data-enviar-prontos]").disabled = true;
  document.querySelector("[data-erro-prontos]").hidden = true;
  const grades = document.querySelector("[data-grades-dos-prontos]");
  grades.replaceChildren(criar("p", "nota-tabela", "Carregando a lista..."));
  janela.showModal();
  // As colunas do parâmetro: a grade mostra as obrigatórias, e o detalhe de cada pessoa, todas (ADR-143)
  const colunas = await buscar_colunas_do_parametro("/api/empresa/colunas_da_consulta");
  grades.replaceChildren();
  for (const pronto of envios_prontos) {
    grades.append(await grade_do_envio_pronto(pronto, colunas));
  }
}

/**
 * A grade de um envio pronto: o nome do arquivo e uma linha por pessoa, com os campos obrigatórios do parâmetro (o
 * valor que vai para o banco, ou "Informação não encontrada"); o clique numa pessoa mostra todos os campos dela.
 *
 * Recebe: pronto — {processamento_id, nome_arquivo, enviado_em, pessoas}; colunas — todas as colunas do parâmetro.
 * Devolve: o bloco pronto (título e tabela).
 */
async function grade_do_envio_pronto(pronto, colunas) {
  const bloco = criar("section", "grade-do-envio-pronto", "");
  bloco.append(criar("h3", "grade-do-envio-pronto-titulo", pronto.nome_arquivo + " · " +
    quantidade_no_singular_ou_plural(pronto.pessoas, "pessoa", "pessoas")));
  // Quem fica de fora deste envio, e por quê (envio parcial, ADR-126; js/quem_fica_de_fora.js)
  const quem_fica_de_fora = montar_bloco_de_quem_fica_de_fora(pronto.ficam_de_fora);
  if (quem_fica_de_fora) {
    bloco.append(quem_fica_de_fora);
  }
  const resposta = await fetch("/api/empresa/cadastro/" + encodeURIComponent(pronto.processamento_id) + "/lista");
  if (!resposta.ok) {
    bloco.append(criar("p", "erro-pendencia", "Não foi possível abrir a lista deste envio agora."));
    return bloco;
  }
  const lista = await resposta.json();
  // A grade rola por dentro, com a linha do título congelada
  const moldura = criar("div", "tabela-rolavel tabela-com-titulo-fixo", "");
  const tabela = criar("table", "tabela-montada", "");
  const cabeca = document.createElement("thead");
  const corpo = document.createElement("tbody");
  tabela.append(cabeca, corpo);
  moldura.append(tabela);
  // O cabeçalho dos campos obrigatórios do parâmetro (ADR-143): grupos em cima, campos embaixo, "*" (sem colunas da
  // tela). A empresa confirma só os obrigatórios; o resto que a IA achou vai junto, e aparece no detalhe da pessoa.
  const colunas_da_grade = colunas_obrigatorias(colunas);
  montar_cabecalho_da_grade(cabeca, colunas_da_grade, [], []);
  // A linha de cada pessoa é a da grade comum das pessoas de um envio (js/grade_do_parametro.js)
  for (const linha of lista.linhas) {
    corpo.append(linha_de_pessoa_do_envio(linha, colunas, colunas_da_grade));
  }
  bloco.append(moldura);
  return bloco;
}

/**
 * "Enviar ao banco": manda tudo o que está pronto. Deu certo: a tela volta com o recado de recebimento.
 *
 * Recebe: botao. Devolve: nada.
 */
async function enviar_prontos_ao_banco(botao) {
  const erro = document.querySelector("[data-erro-prontos]");
  erro.hidden = true;
  botao.disabled = true;
  try {
    const resposta = await fetch("/api/empresa/enviar_ao_banco", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conferi_a_lista: document.querySelector("[data-conferi-prontos]").checked }),
    });
    const corpo = await resposta.json();
    if (resposta.ok) {
      window.location.href = "acompanhar.html?enviado=" + corpo.pessoas + "&de_fora=" + (corpo.ficaram_de_fora || 0);
      return;
    }
    erro.textContent = explicacao_do_erro(corpo.detail);
  } catch (falha) {
    erro.textContent = "Não foi possível falar com o servidor. Tente de novo em instantes.";
  }
  erro.hidden = false;
  botao.disabled = false;
}

/**
 * Liga o bloco dos prontos: o botão que abre a janela da conferência, o "Voltar", o aceite e o "Enviar ao banco".
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_prontos_para_o_banco() {
  const caixa = document.querySelector("[data-conferi-prontos]");
  const botao = document.querySelector("[data-enviar-prontos]");
  document.querySelector("[data-abrir-conferencia-prontos]").addEventListener("click", abrir_conferencia_dos_prontos);
  document.querySelector("[data-fechar-conferencia-prontos]").addEventListener("click", function () {
    document.getElementById("janela-conferir-envio").close();
  });
  // O envio só liga depois do aceite: a pessoa viu a lista inteira
  caixa.addEventListener("change", function () {
    botao.disabled = !caixa.checked;
  });
  botao.addEventListener("click", function () {
    enviar_prontos_ao_banco(botao);
  });
}

// Espera o HTML carregar inteiro antes de ligar tudo.
document.addEventListener("DOMContentLoaded", iniciar_a_tela);
