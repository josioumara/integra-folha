/*
  banco_envios.js — dados e cliques da tela "Avaliar envios" do Portal Interno.

  Para que serve:
    1. guarda os envios de exemplo (4 esperando avaliação e 2 já avaliados);
    2. monta a fila em cima e abre um envio embaixo (trilha da IA, idas e voltas com o banco, alertas e a
       tabela das pessoas);
    3. deixa o especialista "Aceitar" um alerta ou APONTAR UM PROBLEMA em qualquer pessoa (motivo de uma lista
       fechada + recado para a empresa), e desfazer o apontamento (ADR-121);
    4. a decisão, com três caminhos:
       - "Aprovar o envio" (quando ninguém foi apontado): todos ficam cadastrados;
       - "Aprovar N e devolver M" (com apontamentos): os N sem apontamento ficam cadastrados na hora e os M
         apontados voltam para a empresa num envio de devolução, cada apontamento virando uma pendência;
       - "Devolver o envio inteiro" (com motivo): ninguém é cadastrado; os apontamentos vão junto como pendências.

  Atenção: sem servidor, é um rascunho de layout (nada é gravado). Com a página ligada à aplicação
  (js/banco_envios_real.js), a fila, as pessoas, os apontamentos e a decisão são reais, e cada decisão vira um
  registro de auditoria (quem, quando e o motivo). Os desvios estão marcados com "Com servidor" nas funções abaixo.

  Dados: 100% fictícios. As pessoas da Aurora são as mesmas da conferência do Portal Empresa
  (js/conferir.js). As da Atlântico, da Prisma, da Brisa e dos envios avaliados são geradas por uma regra fixa
  (sempre os mesmos nomes), só para encher a tabela.
*/

// ===== 1. Dados de exemplo =====

// As colunas da grade vindas do parâmetro vigente (ADR-111), preenchidas pelo js/banco_envios_real.js quando há
// servidor: só os campos obrigatórios (ADR-143). Vazia: a tabela fica com as colunas de exemplo (Funcionário, CPF,
// Admissão, Salário).
let colunas_da_grade = [];
// Todas as colunas do parâmetro vigente, para a ficha (o detalhe) da pessoa: o clique numa pessoa mostra tudo.
let colunas_do_detalhe = [];

/**
 * Dá a cada pessoa da lista o número da linha dela no arquivo (a linha 1 é o cabeçalho; a 1ª pessoa é a linha 2).
 *
 * Recebe: pessoas — a lista. Devolve: a mesma lista, com "linha" em cada pessoa.
 * Por quê: o apontamento do especialista é preso à LINHA da pessoa, como no servidor (dois nomes iguais não se
 * confundem).
 */
function numerar_linhas(pessoas) {
  // Uma volta para cada pessoa, na ordem do arquivo.
  for (let posicao = 0; posicao < pessoas.length; posicao++) {
    // A 1ª pessoa fica na linha 2 (a linha 1 do arquivo é o cabeçalho).
    pessoas[posicao].linha = posicao + 2;
  }
  // Devolve a lista numerada.
  return pessoas;
}

// Pessoas do envio de inclusão da Aurora (24/09): as mesmas da conferência do Portal Empresa.
// Rafael Moreira Lima e Juliana Castro Pires ficaram com a empresa para ajuste e não vieram para o banco.
// Natália tem um alerta confirmado pela empresa; o Thiago já tem um problema apontado pelo especialista (exemplo).
const PESSOAS_DA_AURORA = numerar_linhas([
  { nome: "Otávio Cardoso Lopes", cpf: "246.813.579-54", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2450 },
  { nome: "Patrícia Azevedo Reis", cpf: "813.579.246-65", cargo: "Analista de logística", admissao: "22/09/2026", salario: 3250 },
  { nome: "Rodrigo Tavares Silva", cpf: "579.246.813-76", cargo: "Motorista", admissao: "22/09/2026", salario: 3420 },
  { nome: "Sofia Mendes Araújo", cpf: "135.792.468-87", cargo: "Assistente administrativa", admissao: "22/09/2026", salario: 3050 },
  { nome: "Carlos Eduardo Nunes", cpf: "792.468.135-98", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 48000, situacao: "aguardando" },
  { nome: "Lucas Ferreira Prado", cpf: "357.918.246-12", cargo: "Operador de máquinas", admissao: "22/09/2026", salario: 3180 },
  { nome: "Mariana Alves de Souza", cpf: "468.257.913-20", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2450 },
  { nome: "Thiago Santos Ribeiro", cpf: "912.648.357-31", cargo: "Técnico de manutenção", admissao: "22/09/2026", salario: 4380,
    apontamento: { motivo: "cargo", motivo_texto: "Cargo incorreto", recado: "O cargo veio como Técnico de manutenção, mas o salário é de auxiliar. Pode confirmar o cargo?" } },
  { nome: "Beatriz Lopes Martins", cpf: "624.813.579-42", cargo: "Conferente", admissao: "22/09/2026", salario: 2780 },
  { nome: "Gustavo Henrique Rocha", cpf: "138.264.957-53", cargo: "Conferente", admissao: "22/09/2026", salario: 2780 },
  { nome: "Vanessa Cristina Dias", cpf: "759.136.284-64", cargo: "Analista de RH", admissao: "22/09/2026", salario: 6200 },
  { nome: "Felipe Cunha Barros", cpf: "284.957.613-75", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2980 },
  { nome: "Aline Rodrigues Pinto", cpf: "591.372.846-86", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2450 },
  { nome: "Eduardo Martins Faria", cpf: "846.291.537-97", cargo: "Líder de produção", admissao: "22/09/2026", salario: 5350 },
  { nome: "Camila Souza Moreira", cpf: "173.846.925-08", cargo: "Assistente administrativa", admissao: "22/09/2026", salario: 3050 },
  { nome: "Rafaela Nogueira Costa", cpf: "362.715.948-19", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2450 },
  { nome: "João Victor Silva", cpf: "695.183.472-20", cargo: "Motorista", admissao: "22/09/2026", salario: 3420 },
  { nome: "Larissa Teixeira Lima", cpf: "437.629.815-31", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2450 },
  { nome: "Bruno Almeida Santos", cpf: "518.943.276-42", cargo: "Técnico de qualidade", admissao: "22/09/2026", salario: 4120 },
  { nome: "Natália Freitas Gomes", cpf: "284.617.953-53", cargo: "Analista de logística", admissao: "22/09/2026", salario: 5900, situacao: "alerta", confirmado_pela_empresa: true },
  { nome: "Pedro Henrique Castro", cpf: "963.428.715-64", cargo: "Operador de máquinas", admissao: "22/09/2026", salario: 3180 },
  { nome: "Isadora Campos Reis", cpf: "731.594.286-75", cargo: "Assistente administrativa", admissao: "22/09/2026", salario: 3050 },
  { nome: "André Luiz Pereira", cpf: "147.852.963-86", cargo: "Motorista", admissao: "22/09/2026", salario: 3420 },
  { nome: "Letícia Barbosa Nunes", cpf: "852.369.741-97", cargo: "Auxiliar de produção", admissao: "22/09/2026", salario: 2450 },
]);

// Primeiros nomes usados para gerar as pessoas dos outros envios.
const PRIMEIROS_NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor", "Irene", "Jorge", "Karina", "Leonardo", "Márcia", "Nelson", "Olívia", "Paulo", "Queila", "Renato", "Simone", "Tiago"];
// Sobrenomes usados para gerar as pessoas dos outros envios.
const SOBRENOMES = ["Almeida", "Barros", "Cardoso", "Duarte", "Esteves", "Fonseca", "Guimarães", "Hora", "Ivo", "Jardim", "Leal", "Macedo", "Neves", "Orsini", "Pacheco", "Quintela", "Rezende", "Sampaio", "Toledo", "Vieira", "Xavier"];

// Cargos e salários comuns da Atlântico Saúde (hospital).
const CARGOS_DA_ATLANTICO = [
  { cargo: "Técnico de enfermagem", salario: 3200 },
  { cargo: "Enfermeira", salario: 6100 },
  { cargo: "Recepcionista", salario: 2400 },
  { cargo: "Auxiliar de limpeza", salario: 1900 },
  { cargo: "Farmacêutico", salario: 7200 },
];

// Cargos e salários comuns da Prisma Comércio (varejo).
const CARGOS_DA_PRISMA = [
  { cargo: "Operador de caixa", salario: 2100 },
  { cargo: "Repositor", salario: 1950 },
  { cargo: "Vendedor", salario: 2600 },
  { cargo: "Fiscal de loja", salario: 2900 },
];

/**
 * Gera uma lista de pessoas fictícias por uma regra fixa (sempre os mesmos nomes, na mesma ordem).
 *
 * Recebe: quantidade — quantas pessoas; cargos — lista de { cargo, salario }; ano_minimo — o ano de
 *         admissão mais antigo (carga inicial tem gente antiga; inclusão, gente recém-admitida).
 * Devolve: uma lista de pessoas { linha, nome, cpf, cargo, admissao, salario }.
 * Exemplo: gerar_pessoas(2, CARGOS_DA_PRISMA, 2026) → [{ nome: "Ana Duarte Fonseca", ... }, { ... }]
 */
function gerar_pessoas(quantidade, cargos, ano_minimo) {
  // Lista que vai sendo preenchida.
  const pessoas = [];
  // Uma volta para cada pessoa.
  for (let posicao = 0; posicao < quantidade; posicao++) {
    // Nome: um primeiro nome e dois sobrenomes, escolhidos pela posição (a mesma posição gera o mesmo nome).
    const primeiro_nome = PRIMEIROS_NOMES[posicao % PRIMEIROS_NOMES.length];
    const primeiro_sobrenome = SOBRENOMES[(posicao * 7 + 3) % SOBRENOMES.length];
    const segundo_sobrenome = SOBRENOMES[(posicao * 3 + 5) % SOBRENOMES.length];
    // O cargo gira pela lista de cargos da empresa.
    const cargo_escolhido = cargos[posicao % cargos.length];
    // Três dígitos do meio do CPF, só para variar os exemplos.
    const meio_do_cpf = String(100 + ((posicao * 37) % 900));
    // Dia e mês de admissão variando pela posição.
    const dia = String(1 + ((posicao * 7) % 27)).padStart(2, "0");
    const mes = String(1 + ((posicao * 5) % 9)).padStart(2, "0");
    // Ano entre o mínimo e 2026.
    const ano = ano_minimo + (posicao % (2027 - ano_minimo));
    // Salário do cargo com uma pequena variação (até R$ 200).
    const salario = cargo_escolhido.salario + (posicao % 5) * 50;
    // Junta tudo numa pessoa (a linha 1 do arquivo é o cabeçalho, então a 1ª pessoa é a linha 2).
    pessoas.push({
      linha: posicao + 2,
      nome: primeiro_nome + " " + primeiro_sobrenome + " " + segundo_sobrenome,
      cpf: "***." + meio_do_cpf + "." + String(posicao).padStart(3, "0") + "-**",
      cargo: cargo_escolhido.cargo,
      admissao: dia + "/" + mes + "/" + ano,
      salario: salario,
    });
  }
  // Devolve a lista pronta.
  return pessoas;
}

/**
 * Marca uma pessoa da lista com alerta de salário (confirmado pela empresa) e troca o salário por um valor fora
 * do padrão.
 *
 * Recebe: pessoas — a lista; posicao — qual pessoa; vezes_o_normal — quantas vezes o salário comum.
 * Devolve: a pessoa alterada (para montar o texto do alerta).
 */
function marcar_salario_fora_do_padrao(pessoas, posicao, vezes_o_normal) {
  // A pessoa escolhida.
  const pessoa = pessoas[posicao];
  // Salário multiplicado, simulando um zero a mais ou um valor digitado errado.
  pessoa.salario = pessoa.salario * vezes_o_normal;
  // Fica marcada como "alerta" até o especialista decidir.
  pessoa.situacao = "alerta";
  // A empresa confirmou o valor antes de enviar (é o que aparece no filtro "Confirmados pela empresa").
  pessoa.confirmado_pela_empresa = true;
  // Devolve para quem chamou.
  return pessoa;
}

// Pessoas da carga inicial da Atlântico (205, com admissões desde 2015).
const PESSOAS_DA_ATLANTICO = gerar_pessoas(205, CARGOS_DA_ATLANTICO, 2015);
// Três salários fora do padrão na carga da Atlântico, que viram alertas.
const ALERTA_ATLANTICO_1 = marcar_salario_fora_do_padrao(PESSOAS_DA_ATLANTICO, 17, 10);
const ALERTA_ATLANTICO_2 = marcar_salario_fora_do_padrao(PESSOAS_DA_ATLANTICO, 58, 9);
const ALERTA_ATLANTICO_3 = marcar_salario_fora_do_padrao(PESSOAS_DA_ATLANTICO, 122, 10);

// As 2 pessoas que o banco devolveu à Brisa em 21/09 (as mesmas 2 primeiras do envio de 21/09, pela regra fixa).
const PESSOAS_DEVOLVIDAS_DA_BRISA = gerar_pessoas(2, CARGOS_DA_PRISMA, 2026);

/**
 * Formata um valor em reais, no jeito brasileiro.
 *
 * Recebe: valor — um número. Devolve: o texto. Exemplo: 48000 → "R$ 48.000,00".
 */
function formatar_reais(valor) {
  // Ferramenta pronta do navegador para formatar moeda.
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Monta o texto de um alerta de salário fora do padrão do cargo.
 *
 * Recebe: pessoa — { linha, nome, cargo, salario }; vezes — quantas vezes acima do comum.
 * Devolve: um alerta { linha, nome, selo, texto, estado }.
 */
function alerta_de_salario(pessoa, vezes) {
  // O alerta segue o mesmo formato dos alertas do Validador (renda julgada pela mediana do cargo).
  return {
    linha: pessoa.linha,
    nome: pessoa.nome,
    selo: "Salário fora do padrão do cargo",
    texto: "O salário de " + formatar_reais(pessoa.salario) + " é cerca de " + vezes + " vezes o comum para " + pessoa.cargo + " nesta empresa.",
    estado: "aberto",
  };
}

// Todos os envios da tela. "situacao": aguardando (na fila), aprovado ou devolvido.
// "origem": o texto do envio de devolução (null nos outros); "idas_e_voltas": as rodadas com o banco;
// "respostas_aos_apontamentos": o que a empresa respondeu aos problemas apontados na rodada anterior.
const ENVIOS = [
  {
    id: "atlantico-carga",
    empresa: "Atlântico Saúde",
    tipo: "Carga inicial",
    detalhe: "Enviada em 23/09 às 16h05 por Cláudia Ramos · Salvador/BA",
    situacao: "aguardando",
    origem: null,
    prazo: { texto: "Passou do prazo de 1 dia útil", classe: "selo-atencao" },
    valores_padronizados: 311,
    trilha: [
      "Planilha com 205 funcionários, enviada por Cláudia Ramos.",
      "Primeira carga da empresa: o Agente Interpretador reconheceu 41 dos 44 campos do layout. Três com confiança média (\"Dt Adm\" → admissão, \"Remuneração\" → salário e \"Turno\" deixado de fora). Ao aprovar, este mapeamento passa a valer para as inclusões da empresa.",
      "311 valores padronizados pelo Normalizador (datas, telefones e CEP), com o valor original guardado.",
      "Cláudia Ramos marcou \"Conferi a lista\" e corrigiu 4 valores antes de enviar.",
      "Nenhuma pessoa ficou com a empresa para ajuste.",
    ],
    idas_e_voltas: [
      { quando: "2026-09-23T16:05:00-03:00", tipo: "enviado", texto: "1º envio ao banco" },
    ],
    respostas_aos_apontamentos: [],
    alertas: [alerta_de_salario(ALERTA_ATLANTICO_1, 10), alerta_de_salario(ALERTA_ATLANTICO_2, 9), alerta_de_salario(ALERTA_ATLANTICO_3, 10)],
    pessoas: PESSOAS_DA_ATLANTICO,
  },
  {
    id: "aurora-inclusao",
    empresa: "Aurora Alimentos",
    tipo: "Inclusão",
    detalhe: "Enviada em 24/09 às 14h32 por Marina Costa · Campinas/SP",
    situacao: "aguardando",
    origem: null,
    prazo: { texto: "Prazo: hoje", classe: "selo-marca" },
    valores_padronizados: 12,
    trilha: [
      "Planilha com 26 funcionários, enviada por Marina Costa.",
      "Colunas iguais às do envio de agosto, que o banco já aprovou: o mapeamento foi reaproveitado, sem chamar o Agente Interpretador.",
      "12 valores padronizados pelo Normalizador (datas, telefones e CEP), com o valor original guardado.",
      "Marina Costa marcou \"Conferi a lista\" e corrigiu 1 valor antes de enviar.",
      "2 pessoas ficaram com a empresa para ajuste (CPF inválido e data no futuro) e não vieram para você.",
    ],
    idas_e_voltas: [
      { quando: "2026-09-24T14:32:00-03:00", tipo: "enviado", texto: "1º envio ao banco" },
    ],
    respostas_aos_apontamentos: [],
    alertas: [
      {
        linha: 6,
        nome: "Carlos Eduardo Nunes",
        selo: "Salário fora do padrão do cargo",
        texto: "O salário de R$ 48.000,00 é cerca de 10 vezes o comum para Auxiliar de produção nesta empresa.",
        estado: "aguardando",
        nota: "Você pediu confirmação em 24/09 às 16h10. Aguardando a empresa.",
      },
      {
        linha: 21,
        nome: "Natália Freitas Gomes",
        selo: "Salário acima do padrão do cargo",
        texto: "O salário de R$ 5.900,00 é cerca de 1,8 vez o comum para Analista de logística nesta empresa. Pode ser uma promoção recente.",
        estado: "aberto",
      },
    ],
    pessoas: PESSOAS_DA_AURORA,
  },
  {
    id: "prisma-inclusao",
    empresa: "Prisma Comércio",
    tipo: "Inclusão",
    detalhe: "Enviada hoje às 07h52 por Jonas Pereira · Recife/PE",
    situacao: "aguardando",
    origem: null,
    prazo: { texto: "Prazo: segunda, 28/09", classe: "selo-neutro" },
    valores_padronizados: 9,
    trilha: [
      "Planilha com 31 funcionários, enviada por Jonas Pereira.",
      "Colunas iguais às do envio anterior, que o banco já aprovou: o mapeamento foi reaproveitado, sem chamar o Agente Interpretador.",
      "9 valores padronizados pelo Normalizador, com o valor original guardado.",
      "Jonas Pereira marcou \"Conferi a lista\" sem corrigir nenhum valor.",
      "Nenhuma pessoa ficou com a empresa para ajuste.",
    ],
    idas_e_voltas: [],
    respostas_aos_apontamentos: [],
    alertas: [],
    pessoas: gerar_pessoas(31, CARGOS_DA_PRISMA, 2026),
  },
  {
    id: "brisa-devolucao",
    empresa: "Brisa Tecnologia",
    tipo: "Inclusão",
    detalhe: "Reenviada em 25/09 às 11h20 por Helena Duarte · Florianópolis/SC",
    situacao: "aguardando",
    origem: "Devolução do envio de 21/09 (2 pessoas)",
    prazo: { texto: "Prazo: segunda, 28/09", classe: "selo-neutro" },
    valores_padronizados: 0,
    trilha: [
      "As 2 pessoas que você devolveu em 21/09 voltaram, com as respostas da empresa.",
      "Helena Duarte respondeu os 2 pedidos e mandou de novo ao banco.",
    ],
    idas_e_voltas: [
      { quando: "2026-09-21T09:40:00-03:00", tipo: "enviado", texto: "1º envio ao banco" },
      { quando: "2026-09-21T10:12:00-03:00", tipo: "aprovado_em_parte", texto: "O banco aprovou 10 e devolveu 2 (" + PESSOAS_DEVOLVIDAS_DA_BRISA[0].nome + ": Confirmar o salário; " + PESSOAS_DEVOLVIDAS_DA_BRISA[1].nome + ": CPF incorreto)" },
      { quando: "2026-09-25T11:20:00-03:00", tipo: "enviado", texto: "2º envio ao banco" },
    ],
    respostas_aos_apontamentos: [
      {
        nome: PESSOAS_DEVOLVIDAS_DA_BRISA[0].nome,
        motivo: "Confirmar o salário",
        recado: "O salário de R$ 21.000,00 parece ter um zero a mais para Operador de caixa. Pode confirmar?",
        resposta: "A empresa corrigiu o salário: 21000.00 → 2100.00",
      },
      {
        nome: PESSOAS_DEVOLVIDAS_DA_BRISA[1].nome,
        motivo: "CPF incorreto",
        recado: "O CPF não confere com o nome na Receita. Pode conferir no documento?",
        resposta: "A empresa confirmou: \"O CPF está certo, conferimos no documento.\"",
      },
    ],
    alertas: [],
    pessoas: PESSOAS_DEVOLVIDAS_DA_BRISA,
  },
  {
    id: "brisa-inclusao",
    empresa: "Brisa Tecnologia",
    tipo: "Inclusão",
    detalhe: "Enviada em 21/09 às 09h40 por Helena Duarte · Florianópolis/SC",
    situacao: "aprovado",
    origem: null,
    resultado: "Aprovado por você em 21/09 às 10h12: 10 funcionários cadastrados e 2 devolvidos à empresa num envio de devolução.",
    prazo: { texto: "Aprovado", classe: "selo-sucesso" },
    valores_padronizados: 3,
    trilha: [
      "Planilha com 12 funcionários, enviada por Helena Duarte.",
      "Colunas iguais às do envio anterior: mapeamento reaproveitado.",
      "3 valores padronizados pelo Normalizador.",
      "Helena Duarte marcou \"Conferi a lista\".",
    ],
    idas_e_voltas: [
      { quando: "2026-09-21T09:40:00-03:00", tipo: "enviado", texto: "1º envio ao banco" },
      { quando: "2026-09-21T10:12:00-03:00", tipo: "aprovado_em_parte", texto: "O banco aprovou 10 e devolveu 2 (" + PESSOAS_DEVOLVIDAS_DA_BRISA[0].nome + ": Confirmar o salário; " + PESSOAS_DEVOLVIDAS_DA_BRISA[1].nome + ": CPF incorreto)" },
    ],
    respostas_aos_apontamentos: [],
    alertas: [],
    pessoas: gerar_pessoas(12, CARGOS_DA_PRISMA, 2026),
  },
  {
    id: "horizonte-inclusao",
    empresa: "Horizonte Logística",
    tipo: "Inclusão",
    detalhe: "Enviada em 18/09 às 11h03 por Sérgio Matos · Contagem/MG",
    situacao: "devolvido",
    origem: null,
    resultado: "Devolvido por você em 18/09: envio repetido. \"Estes 40 funcionários já vieram na carga inicial. Mande só os admitidos depois de 01/08.\"",
    prazo: { texto: "Devolvido", classe: "selo-atencao" },
    valores_padronizados: 22,
    trilha: [
      "Planilha com 40 funcionários, enviada por Sérgio Matos.",
      "Colunas iguais às da carga inicial: mapeamento reaproveitado.",
      "22 valores padronizados pelo Normalizador.",
      "Sérgio Matos marcou \"Conferi a lista\".",
    ],
    idas_e_voltas: [
      { quando: "2026-09-18T11:03:00-03:00", tipo: "enviado", texto: "1º envio ao banco" },
      { quando: "2026-09-18T15:40:00-03:00", tipo: "devolvido", texto: "O banco devolveu o envio inteiro: \"Estes 40 funcionários já vieram na carga inicial.\"" },
    ],
    respostas_aos_apontamentos: [],
    alertas: [],
    pessoas: gerar_pessoas(40, CARGOS_DA_PRISMA, 2021),
  },
];

// Nomes amigáveis dos motivos de "Devolver o envio inteiro", para mostrar no resultado.
const NOMES_DOS_MOTIVOS = {
  "arquivo-errado": "arquivo errado",
  "muitos-erros": "erros demais para corrigir pessoa por pessoa",
  "duplicado": "envio repetido",
  "outro": "outro motivo",
};

// Quantas pessoas a tabela mostra de cada vez.
const PESSOAS_POR_VEZ = 20;

// O aviso da janela "Apontar problema" quando falta algo (a mesma frase do HTML; volta a cada abertura).
const AVISO_PADRAO_DO_APONTAMENTO = "Escolha o motivo e escreva um recado com pelo menos 15 letras.";

// ===== 2. Estado da tela (o que está escolhido agora) =====

// O que a tela está mostrando neste momento.
const estado_da_tela = {
  filtro_da_fila: "aguardando",   // "aguardando" ou "avaliados"
  envio_aberto: null,             // o envio mostrado embaixo da fila
  filtro_de_pessoas: "todos",     // "todos", "confirmados" ou "apontados"
  busca: "",                      // o texto digitado na busca
  quantas_mostrar: PESSOAS_POR_VEZ, // quantas linhas a tabela mostra
  linha_do_apontamento: null,     // a linha da pessoa na janela "Apontar problema"
  alertas_aceitos: {},            // { id do envio: [nomes dos alertas aceitos] } (sobrevive a recarregar a fila)
};

// ===== 3. Pequenas ferramentas =====

/**
 * Cria um elemento da página com classe e texto.
 *
 * Recebe: etiqueta — o tipo ("li", "span"...); classes — texto com as classes (ou ""); texto — o conteúdo.
 * Devolve: o elemento criado (ainda fora da página).
 * Por que textContent: o texto entra como texto puro, nunca como código. Isso importa para o que as
 * pessoas digitam (ex.: o recado do apontamento), que assim não consegue "virar" um pedaço da página.
 */
function criar_elemento(etiqueta, classes, texto) {
  // Cria o elemento vazio.
  const elemento = document.createElement(etiqueta);
  // Põe as classes, se houver.
  if (classes) {
    elemento.className = classes;
  }
  // Põe o texto, se houver.
  if (texto) {
    elemento.textContent = texto;
  }
  // Devolve pronto para ser colocado na página.
  return elemento;
}

/**
 * Escreve um número com a palavra no singular ou no plural.
 *
 * Recebe: numero; singular — ex.: "pessoa"; plural — ex.: "pessoas". Devolve: o texto.
 * Exemplo: numero_com_palavra(1, "pessoa", "pessoas") → "1 pessoa"; (3, ...) → "3 pessoas"; (0, ...) → "0 pessoas".
 */
function numero_com_palavra(numero, singular, plural) {
  // Só o 1 fica no singular (em português, "0 pessoas" é plural).
  if (numero === 1) {
    return "1 " + singular;
  }
  // Os outros números ficam no plural.
  return numero + " " + plural;
}

/**
 * Escolhe a forma certa de uma palavra para o número (sem escrever o número).
 *
 * Recebe: numero; singular — ex.: "fica"; plural — ex.: "ficam". Devolve: a palavra.
 */
function no_singular_ou_plural(numero, singular, plural) {
  // Só o 1 pede o singular.
  if (numero === 1) {
    return singular;
  }
  // Os outros números pedem o plural.
  return plural;
}

/**
 * Escreve a data e a hora no jeito curto ("24/09 às 14h32").
 *
 * Recebe: texto — data e hora (ex.: "2026-09-24T14:32:00-03:00"), ou null. Devolve: o texto curto.
 */
function quando_foi_enviado(texto) {
  // Sem data: diz isso, sem inventar.
  if (!texto) {
    return "data não registrada";
  }
  // Converte o texto numa data do navegador (no fuso de quem olha a tela).
  const momento = new Date(texto);
  // Dia e mês com dois dígitos ("24/09").
  const dia_e_mes = momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  // Hora e minuto com dois dígitos ("14" e "32").
  const hora = String(momento.getHours()).padStart(2, "0");
  const minuto = String(momento.getMinutes()).padStart(2, "0");
  // Junta tudo: "24/09 às 14h32".
  return dia_e_mes + " às " + hora + "h" + minuto;
}

/**
 * Diz a situação de uma pessoa (quem não tem situação marcada está "pronto").
 *
 * Recebe: pessoa. Devolve: "pronto", "alerta", "aguardando" ou "apontado".
 */
function situacao_da_pessoa(pessoa) {
  // Com um problema apontado pelo especialista, é isso que vale (ela sai da aprovação).
  if (pessoa.apontamento) {
    return "apontado";
  }
  // Sem marcação, a pessoa está pronta para aprovar.
  if (!pessoa.situacao) {
    return "pronto";
  }
  // Com marcação, devolve a marcação.
  return pessoa.situacao;
}

/**
 * Conta as pessoas de um envio por situação, e as confirmadas pela empresa.
 *
 * Recebe: envio. Devolve: { pronto, alerta, aguardando, apontado, confirmados }.
 */
function contar_pessoas(envio) {
  // Contadores começando do zero.
  const contagem = { pronto: 0, alerta: 0, aguardando: 0, apontado: 0, confirmados: 0 };
  // Passa por todas as pessoas do envio.
  for (const pessoa of envio.pessoas) {
    // A situação desta pessoa.
    const situacao = situacao_da_pessoa(pessoa);
    // Soma no contador certo.
    if (situacao === "pronto") {
      contagem.pronto = contagem.pronto + 1;
    } else if (situacao === "alerta") {
      contagem.alerta = contagem.alerta + 1;
    } else if (situacao === "aguardando") {
      contagem.aguardando = contagem.aguardando + 1;
    } else {
      contagem.apontado = contagem.apontado + 1;
    }
    // A empresa confirmou um alerta desta pessoa antes de enviar (conta no filtro "Confirmados pela empresa").
    if (pessoa.confirmado_pela_empresa) {
      contagem.confirmados = contagem.confirmados + 1;
    }
  }
  // Devolve os números.
  return contagem;
}

/**
 * Procura um envio pelo identificador.
 *
 * Recebe: id — ex.: "aurora-inclusao". Devolve: o envio, ou null se não existir.
 */
function achar_envio(id) {
  // Olha envio por envio.
  for (const envio of ENVIOS) {
    // Achou: devolve.
    if (envio.id === id) {
      return envio;
    }
  }
  // Não achou.
  return null;
}

/**
 * Procura uma pessoa pela linha do arquivo dentro do envio aberto.
 *
 * Recebe: linha — número ou texto (os botões guardam em texto, ex.: "9"). Devolve: a pessoa, ou null.
 */
function achar_pessoa_pela_linha(linha) {
  // Olha pessoa por pessoa do envio aberto.
  for (const pessoa of estado_da_tela.envio_aberto.pessoas) {
    // Compara como texto: "9" (do botão) e 9 (da pessoa) são a mesma linha.
    if (String(pessoa.linha) === String(linha)) {
      return pessoa;
    }
  }
  // Não achou (ex.: alerta do arquivo inteiro, que não é de uma pessoa).
  return null;
}

/**
 * Verdadeiro se o envio está na fila (esperando avaliação).
 *
 * Recebe: envio. Devolve: true ou false.
 */
function envio_esta_aguardando(envio) {
  // Só "aguardando" está na fila; aprovado e devolvido já foram avaliados.
  return envio.situacao === "aguardando";
}

// ===== 4. Fila de envios (em cima) =====

/**
 * Monta a fila de envios, conforme o filtro escolhido ("Esperando você" ou "Avaliados").
 *
 * Recebe: nada (lê o estado da tela). Devolve: nada.
 */
function mostrar_fila() {
  // A lista da página.
  const lista = document.querySelector("[data-lista-fila]");
  // Esvazia antes de montar de novo.
  lista.replaceChildren();
  // Contadores para os dois filtros.
  let quantos_aguardando = 0;
  let quantos_avaliados = 0;

  // Passa por todos os envios.
  for (const envio of ENVIOS) {
    // Verdadeiro se o envio está esperando avaliação.
    const aguardando = envio_esta_aguardando(envio);
    // Soma no contador certo.
    if (aguardando) {
      quantos_aguardando = quantos_aguardando + 1;
    } else {
      quantos_avaliados = quantos_avaliados + 1;
    }
    // Verdadeiro se o envio pertence ao filtro escolhido.
    const combina_com_filtro = (estado_da_tela.filtro_da_fila === "aguardando") === aguardando;
    // Fora do filtro: não entra na lista.
    if (!combina_com_filtro) {
      continue;
    }
    // Entra na lista.
    lista.append(montar_item_da_fila(envio));
  }

  // Atualiza os números dos filtros.
  document.querySelector("[data-contagem-fila='aguardando']").textContent = "(" + quantos_aguardando + ")";
  document.querySelector("[data-contagem-fila='avaliados']").textContent = "(" + quantos_avaliados + ")";
  // Atualiza o número na cor da marca da aba "Envios" no cabeçalho.
  document.querySelector("[data-contador-aba-envios]").textContent = String(quantos_aguardando);
  // Sem nenhum envio esperando, o número da aba some.
  document.querySelector("[data-contador-aba-envios]").hidden = quantos_aguardando === 0;
}

/**
 * Monta um item da fila: um botão com a empresa, a origem (envio de devolução), o tipo, a quantidade e o prazo.
 *
 * Recebe: envio. Devolve: o elemento <li> pronto.
 */
function montar_item_da_fila(envio) {
  // Item da lista.
  const item = criar_elemento("li", "", "");
  // O botão que abre o envio.
  const botao = criar_elemento("button", "botao-envio-fila", "");
  botao.type = "button";
  // Guarda qual envio o botão abre.
  botao.dataset.abrirEnvio = envio.id;
  // Marca o envio aberto agora, para ele aparecer destacado.
  if (estado_da_tela.envio_aberto === envio) {
    botao.classList.add("botao-envio-fila-aberto");
    botao.setAttribute("aria-current", "true");
  }
  // Nome da empresa.
  botao.append(criar_elemento("span", "botao-envio-fila-empresa", envio.empresa));
  // Envio de devolução: diz de onde ele veio (ex.: "Devolução do envio de 28/09 (2 pessoas)").
  if (envio.origem) {
    botao.append(criar_elemento("span", "botao-envio-fila-origem", envio.origem));
  }
  // Tipo e quantidade de pessoas (singular ou plural certo).
  botao.append(criar_elemento("span", "botao-envio-fila-detalhe", envio.tipo + " · " + numero_com_palavra(envio.pessoas.length, "funcionário", "funcionários")));
  // Selo do prazo (ou do resultado, para os avaliados).
  botao.append(criar_elemento("span", "selo selo-pequeno " + envio.prazo.classe, envio.prazo.texto));
  // Coloca o botão no item.
  item.append(botao);
  // Devolve o item pronto.
  return item;
}

// ===== 5. Envio aberto (embaixo) =====

/**
 * Abre um envio embaixo da fila: cabeçalho, números, trilha, idas e voltas, alertas, tabela e decisão.
 *
 * Recebe: envio. Devolve: nada.
 */
function abrir_envio(envio) {
  // Guarda qual envio está aberto e volta os filtros das pessoas ao começo.
  estado_da_tela.envio_aberto = envio;
  estado_da_tela.filtro_de_pessoas = "todos";
  estado_da_tela.busca = "";
  estado_da_tela.quantas_mostrar = PESSOAS_POR_VEZ;
  // Limpa a caixa de busca.
  document.querySelector("[data-busca-pessoas]").value = "";
  // Volta o filtro "Todos" a ficar ligado.
  marcar_filtro_ligado("[data-filtro-pessoas]", "todos", "filtroPessoas");
  // Os alertas que o especialista já aceitou continuam aceitos (mesmo depois de a fila ser recarregada).
  reaplicar_alertas_aceitos(envio);

  // Cabeçalho do envio.
  document.querySelector("[data-envio-tipo]").textContent = envio.tipo;
  document.querySelector("[data-envio-empresa]").textContent = envio.empresa;
  document.querySelector("[data-envio-detalhe]").textContent = envio.detalhe;
  // Envio de devolução: a linha "Devolução do envio de ..." logo abaixo do nome da empresa.
  const linha_da_origem = document.querySelector("[data-envio-origem]");
  linha_da_origem.hidden = !envio.origem;
  linha_da_origem.textContent = envio.origem || "";
  // Selo do prazo.
  const selo_prazo = document.querySelector("[data-envio-prazo]");
  selo_prazo.className = "selo " + envio.prazo.classe;
  selo_prazo.textContent = envio.prazo.texto;

  // Trilha "Como este envio chegou até você".
  const trilha = document.querySelector("[data-trilha-envio]");
  // Esvazia a trilha anterior.
  trilha.replaceChildren();
  // Um item por passo.
  for (const passo of envio.trilha) {
    trilha.append(criar_elemento("li", "", passo));
  }
  // As rodadas com o banco e o que a empresa respondeu aos apontamentos (cada bloco só com lista não vazia).
  mostrar_idas_e_voltas(envio);
  mostrar_respostas_aos_apontamentos(envio);

  // Números, alertas, tabela e decisão (partes que mudam quando o especialista age).
  atualizar_partes_do_envio();
  // Redesenha a fila, para destacar o envio aberto.
  mostrar_fila();
}

/**
 * Reabre um envio sem perder o que a pessoa estava fazendo na tabela (filtro, busca e "mostrar mais").
 * Usada depois de cada ação gravada no servidor (apontar, desfazer), quando a fila é recarregada.
 *
 * Recebe: envio — o envio (já recarregado). Devolve: nada.
 */
function reabrir_envio_mantendo_a_tela(envio) {
  // Guarda o que a pessoa tinha escolhido, antes de abrir_envio voltar tudo ao começo.
  const filtro_escolhido = estado_da_tela.filtro_de_pessoas;
  const busca_digitada = estado_da_tela.busca;
  const texto_da_caixa_de_busca = document.querySelector("[data-busca-pessoas]").value;
  const quantas_estavam_na_tela = estado_da_tela.quantas_mostrar;
  // Abre o envio (monta tudo de novo, com os dados novos).
  abrir_envio(envio);
  // Devolve o filtro, a busca e a quantidade de linhas que a pessoa via.
  estado_da_tela.filtro_de_pessoas = filtro_escolhido;
  estado_da_tela.busca = busca_digitada;
  estado_da_tela.quantas_mostrar = quantas_estavam_na_tela;
  document.querySelector("[data-busca-pessoas]").value = texto_da_caixa_de_busca;
  marcar_filtro_ligado("[data-filtro-pessoas]", filtro_escolhido, "filtroPessoas");
  // Redesenha a tabela com o filtro e a busca de antes.
  mostrar_pessoas();
}

/**
 * Redesenha as partes do envio aberto que mudam com as decisões: números, filtros, alertas, tabela e decisão.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_partes_do_envio() {
  // O envio aberto.
  const envio = estado_da_tela.envio_aberto;
  // Quantas pessoas em cada situação.
  const contagem = contar_pessoas(envio);
  // Quantos alertas ainda estão abertos.
  const alertas_abertos = contar_alertas_abertos(envio);

  // Os quatro números.
  document.querySelector("[data-numero-pessoas]").textContent = String(envio.pessoas.length);
  document.querySelector("[data-numero-alterados]").textContent = String(envio.valores_padronizados);
  document.querySelector("[data-numero-alertas]").textContent = String(alertas_abertos);
  document.querySelector("[data-numero-aguardando]").textContent = String(contagem.aguardando);
  // Os números dos filtros das pessoas: "Confirmados pela empresa (N)" e "Apontados por você (N)".
  document.querySelector("[data-contagem-pessoas='confirmados']").textContent = "(" + contagem.confirmados + ")";
  document.querySelector("[data-contagem-pessoas='apontados']").textContent = "(" + contagem.apontado + ")";

  // Alertas, tabela e decisão.
  mostrar_alertas(envio);
  mostrar_pessoas();
  mostrar_decisao(envio, contagem, alertas_abertos);
}

// ===== 6. Idas e voltas com o banco e respostas aos apontamentos =====

/**
 * Monta o bloco "Idas e voltas com o banco": uma linha por rodada (enviado, devolvido, aprovado em parte...).
 * O bloco some quando a lista é vazia.
 *
 * Recebe: envio. Devolve: nada.
 */
function mostrar_idas_e_voltas(envio) {
  // O bloco e a lista dentro dele.
  const bloco = document.querySelector("[data-bloco-idas-e-voltas]");
  const lista = document.querySelector("[data-lista-idas-e-voltas]");
  // Esvazia a lista anterior.
  lista.replaceChildren();
  // Sem nenhuma rodada: o bloco some.
  bloco.hidden = envio.idas_e_voltas.length === 0;
  // Uma linha por rodada.
  for (const rodada of envio.idas_e_voltas) {
    // A linha ganha a cor do tipo (ex.: "ida-e-volta-devolvido" fica na cor de atenção).
    const item = criar_elemento("li", "ida-e-volta ida-e-volta-" + rodada.tipo, "");
    // Guarda o tipo, para os roteiros de clique acharem a linha.
    item.dataset.tipo = rodada.tipo;
    // Quando foi, em destaque, e o que aconteceu.
    item.append(criar_elemento("span", "ida-e-volta-quando", quando_foi_enviado(rodada.quando)));
    item.append(criar_elemento("span", "ida-e-volta-texto", rodada.texto));
    // Põe a linha na lista.
    lista.append(item);
  }
}

/**
 * Monta o bloco "Respostas aos seus apontamentos": o que a empresa fez com cada problema apontado na rodada
 * anterior (corrigiu, confirmou ou tirou a pessoa). O bloco some quando a lista é vazia.
 *
 * Recebe: envio. Devolve: nada.
 */
function mostrar_respostas_aos_apontamentos(envio) {
  // O bloco e a lista dentro dele.
  const bloco = document.querySelector("[data-bloco-respostas]");
  const lista = document.querySelector("[data-lista-respostas]");
  // Esvazia a lista anterior.
  lista.replaceChildren();
  // Sem nenhuma resposta: o bloco some.
  bloco.hidden = envio.respostas_aos_apontamentos.length === 0;
  // Um cartão por resposta.
  for (const resposta of envio.respostas_aos_apontamentos) {
    // O item da lista.
    const item = criar_elemento("li", "resposta-ao-apontamento", "");
    // Quem e qual foi o motivo apontado.
    item.append(criar_elemento("strong", "", resposta.nome + " · " + resposta.motivo));
    // O recado que o especialista mandou.
    item.append(criar_elemento("span", "resposta-ao-apontamento-recado", "Seu recado: \"" + resposta.recado + "\""));
    // O que a empresa respondeu.
    item.append(criar_elemento("span", "resposta-ao-apontamento-resposta", resposta.resposta));
    // Põe o item na lista.
    lista.append(item);
  }
}

// ===== 7. Alertas do Validador =====

/**
 * Verdadeiro se o alerta ainda espera a decisão do especialista (nem aceito, nem com problema apontado).
 *
 * Recebe: alerta. Devolve: true ou false.
 */
function alerta_esta_aberto(alerta) {
  // Já decidido (aceito ou esperando a empresa): não está aberto.
  if (alerta.estado !== "aberto") {
    return false;
  }
  // A pessoa do alerta (null no alerta do arquivo inteiro).
  const pessoa = achar_pessoa_pela_linha(alerta.linha);
  // Com um problema apontado na pessoa, o alerta está decidido: ela volta para a empresa.
  if (pessoa && pessoa.apontamento) {
    return false;
  }
  // Senão, continua aberto.
  return true;
}

/**
 * Conta os alertas de um envio que ainda esperam decisão do especialista.
 *
 * Recebe: envio (o envio aberto). Devolve: um número.
 */
function contar_alertas_abertos(envio) {
  // Contador.
  let abertos = 0;
  // Passa por todos os alertas.
  for (const alerta of envio.alertas) {
    // Só os abertos contam.
    if (alerta_esta_aberto(alerta)) {
      abertos = abertos + 1;
    }
  }
  // Devolve o total.
  return abertos;
}

/**
 * Monta a lista de alertas do envio aberto, cada um com as ações possíveis.
 *
 * Recebe: envio. Devolve: nada.
 */
function mostrar_alertas(envio) {
  // O bloco inteiro dos alertas e a lista dentro dele.
  const bloco = document.querySelector("[data-bloco-alertas]");
  const lista = document.querySelector("[data-lista-alertas]");
  // Esvazia a lista anterior.
  lista.replaceChildren();
  // Sem alertas: o bloco some.
  bloco.hidden = envio.alertas.length === 0;
  // Um cartão por alerta.
  for (const alerta of envio.alertas) {
    lista.append(montar_cartao_de_alerta(envio, alerta));
  }
}

/**
 * Monta o cartão de um alerta: nome, selo, explicação e botões (ou a nota do que já foi decidido).
 *
 * Recebe: envio; alerta. Devolve: o elemento <article> pronto.
 */
function montar_cartao_de_alerta(envio, alerta) {
  // Cartão no mesmo estilo das pendências do Portal Empresa.
  const cartao = criar_elemento("article", "ajuste", "");
  // Guarda o nome, para os botões saberem de quem é o alerta.
  cartao.dataset.alerta = alerta.nome;
  // Linha de cima: nome e selo.
  const cabecalho = criar_elemento("div", "ajuste-cabecalho", "");
  cabecalho.append(criar_elemento("span", "ajuste-titulo", alerta.nome));
  cabecalho.append(criar_elemento("span", "selo selo-atencao selo-pequeno", alerta.selo));
  cartao.append(cabecalho);
  // A explicação do Validador.
  cartao.append(criar_elemento("p", "ajuste-problema", alerta.texto));
  // A pessoa do alerta (null no alerta do arquivo inteiro).
  const pessoa = achar_pessoa_pela_linha(alerta.linha);

  // Problema apontado nesta pessoa: o alerta está decidido, com a nota do apontamento (o "Desfazer" fica na tabela).
  if (pessoa && pessoa.apontamento && envio_esta_aguardando(envio)) {
    cartao.classList.add("ajuste-decidido");
    cartao.append(criar_elemento("p", "nota-decisao", "Você apontou um problema (" + pessoa.apontamento.motivo_texto + "): \"" + pessoa.apontamento.recado + "\" Ao decidir o envio, a pessoa volta para a empresa."));
    return cartao;
  }
  // Alerta já decidido: mostra a nota e para por aqui (sem botões).
  if (alerta.estado !== "aberto") {
    cartao.classList.add("ajuste-decidido");
    cartao.append(criar_elemento("p", "nota-decisao", alerta.nota));
    return cartao;
  }
  // Envio já avaliado: sem botões.
  if (!envio_esta_aguardando(envio)) {
    return cartao;
  }

  // Botões: aceitar o valor como está, ou apontar um problema (a pessoa volta para a empresa com o recado).
  const botoes = criar_elemento("div", "ajuste-botoes", "");
  // Aceitar: o especialista conferiu e o valor é plausível.
  const botao_aceitar = criar_elemento("button", "botao botao-contorno botao-pequeno", "Aceitar como está");
  botao_aceitar.type = "button";
  botao_aceitar.dataset.aceitarAlerta = alerta.nome;
  botoes.append(botao_aceitar);
  // Apontar problema: só quando o alerta é de uma pessoa da tabela (o do arquivo inteiro não tem a quem apontar).
  if (pessoa) {
    const botao_apontar = criar_elemento("button", "botao botao-principal botao-pequeno", "Apontar problema");
    botao_apontar.type = "button";
    botao_apontar.dataset.apontarProblema = String(pessoa.linha);
    botoes.append(botao_apontar);
  }
  // Coloca os botões no cartão.
  cartao.append(botoes);
  // Devolve o cartão pronto.
  return cartao;
}

/**
 * O especialista aceita o alerta: a pessoa volta a "pronto" e o alerta fica registrado como aceito.
 *
 * Recebe: nome — de quem é o alerta. Devolve: nada.
 */
function aceitar_alerta(nome) {
  // O envio aberto.
  const envio = estado_da_tela.envio_aberto;
  // Guarda o aceite na memória da tela, para ele continuar valendo quando a fila for recarregada do servidor.
  if (!estado_da_tela.alertas_aceitos[envio.id]) {
    estado_da_tela.alertas_aceitos[envio.id] = [];
  }
  estado_da_tela.alertas_aceitos[envio.id].push(nome);
  // Marca o alerta como aceito e a pessoa como pronta.
  reaplicar_alertas_aceitos(envio);
  // Redesenha números, alertas, tabela e decisão.
  atualizar_partes_do_envio();
}

/**
 * Marca como aceitos os alertas que o especialista já aceitou neste envio (pode ser chamada várias vezes).
 * Por quê: com servidor, cada apontamento recarrega a fila, e o envio chega de novo com os alertas abertos; o
 * aceite é uma conferência da tela e não pode se perder no meio do trabalho.
 *
 * Recebe: envio. Devolve: nada.
 */
function reaplicar_alertas_aceitos(envio) {
  // Os nomes dos alertas aceitos neste envio (nenhum, se o especialista não aceitou nada).
  const nomes_aceitos = estado_da_tela.alertas_aceitos[envio.id];
  // Nada aceito: nada a fazer.
  if (!nomes_aceitos) {
    return;
  }
  // Passa por todos os alertas do envio.
  for (const alerta of envio.alertas) {
    // Só os aceitos e ainda abertos mudam.
    if (!nomes_aceitos.includes(alerta.nome) || alerta.estado !== "aberto") {
      continue;
    }
    // O alerta fica aceito, com a nota.
    alerta.estado = "aceito";
    alerta.nota = "Você aceitou o valor como está. Fica registrado quem aceitou e quando.";
    // A pessoa do alerta volta a ficar pronta para aprovar.
    for (const pessoa of envio.pessoas) {
      if (String(pessoa.linha) === String(alerta.linha) && pessoa.situacao === "alerta") {
        delete pessoa.situacao;
      }
    }
  }
}

// ===== 8. Tabela das pessoas =====

/**
 * Verdadeiro se a pessoa aparece com o filtro e a busca atuais.
 *
 * Recebe: pessoa. Devolve: true ou false.
 */
function pessoa_aparece(pessoa) {
  // Filtro "Confirmados pela empresa": só quem teve um alerta confirmado pela empresa antes do envio.
  if (estado_da_tela.filtro_de_pessoas === "confirmados" && !pessoa.confirmado_pela_empresa) {
    return false;
  }
  // Filtro "Apontados por você": só quem tem um problema apontado pelo especialista.
  if (estado_da_tela.filtro_de_pessoas === "apontados" && !pessoa.apontamento) {
    return false;
  }
  // Sem busca: aparece.
  if (!estado_da_tela.busca) {
    return true;
  }
  // Nome e cargo juntos, em minúsculas, para buscar nos dois.
  const onde_procurar = (pessoa.nome + " " + pessoa.cargo).toLowerCase();
  // Aparece se o texto buscado estiver no nome ou no cargo.
  if (onde_procurar.includes(estado_da_tela.busca)) {
    return true;
  }
  // Ou no CPF: compara só os números, com ou sem ponto e traço.
  return cpf_combina_com_a_busca(pessoa.cpf, estado_da_tela.busca);
}

// Quantos números a busca precisa ter para procurar no CPF (com menos, "1" acharia quase todo mundo)
const MINIMO_DE_NUMEROS_NA_BUSCA_POR_CPF = 3;

/**
 * Só os números de um texto. Exemplo: "123.456.789-09" → "12345678909".
 *
 * Recebe: texto (pode ser vazio ou nulo). Devolve: os números, em texto.
 */
function somente_os_numeros(texto) {
  // "\D" é qualquer caractere que não é número: troca todos por nada.
  return String(texto || "").replace(/\D/g, "");
}

/**
 * Diz se o CPF da pessoa contém os números buscados. Exemplo: CPF "123.456.789-09" e busca "456.789" → true.
 *
 * Recebe: cpf; busca (o texto digitado). Devolve: true ou false (busca com menos de 3 números não procura no CPF).
 */
function cpf_combina_com_a_busca(cpf, busca) {
  const numeros_da_busca = somente_os_numeros(busca);
  if (numeros_da_busca.length < MINIMO_DE_NUMEROS_NA_BUSCA_POR_CPF) {
    return false;
  }
  return somente_os_numeros(cpf).includes(numeros_da_busca);
}

/**
 * Monta a tabela das pessoas do envio aberto, respeitando filtro, busca e o "mostrar mais".
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_pessoas() {
  // O envio aberto.
  const envio = estado_da_tela.envio_aberto;
  // Corpo da tabela.
  const corpo = document.querySelector("[data-corpo-pessoas]");
  // Esvazia antes de montar.
  corpo.replaceChildren();
  // Quantas pessoas combinam com filtro e busca (mesmo as que não cabem na tela agora).
  let quantas_combinam = 0;

  // Passa por todas as pessoas.
  for (const pessoa of envio.pessoas) {
    // Não combina: pula.
    if (!pessoa_aparece(pessoa)) {
      continue;
    }
    // Combina: conta.
    quantas_combinam = quantas_combinam + 1;
    // Só entra na tabela até o limite do "mostrar mais".
    if (quantas_combinam <= estado_da_tela.quantas_mostrar) {
      corpo.append(montar_linha_da_pessoa(envio, pessoa));
    }
  }

  // Quantas estão na tela agora (o menor entre as que combinam e o limite).
  const quantas_na_tela = Math.min(quantas_combinam, estado_da_tela.quantas_mostrar);
  // "Mostrando 20 de 205 funcionários" (com "1 funcionário" no singular).
  document.querySelector("[data-contador-pessoas]").textContent = "Mostrando " + quantas_na_tela + " de " + numero_com_palavra(quantas_combinam, "funcionário", "funcionários");
  // O botão "Mostrar mais" só aparece se sobrou gente fora da tela.
  document.querySelector("[data-mostrar-mais-pessoas]").hidden = quantas_combinam <= estado_da_tela.quantas_mostrar;
}

// Selo de cada situação: texto e cor.
const SELOS_DAS_SITUACOES = {
  "pronto": { texto: "Pronto", classe: "selo-sucesso" },
  "alerta": { texto: "Alerta", classe: "selo-atencao" },
  "aguardando": { texto: "Aguardando a empresa", classe: "selo-neutro" },
  "apontado": { texto: "Apontado por você", classe: "selo-marca" },
};

/**
 * Monta a linha de uma pessoa na tabela.
 *
 * Recebe: envio; pessoa. Devolve: o elemento <tr> pronto (com "data-linha-pessoa" = a linha do arquivo).
 */
function montar_linha_da_pessoa(envio, pessoa) {
  // Com as colunas do parâmetro (dados de verdade), uma célula por campo obrigatório, e depois Situação e Ação
  // (ADR-111 e ADR-143).
  if (colunas_da_grade.length > 0 && pessoa.campos) {
    // A linha da tabela, com a linha do arquivo guardada (os botões e os roteiros de clique acham a pessoa por ela).
    const linha_da_grade = criar_elemento("tr", "", "");
    linha_da_grade.dataset.linhaPessoa = String(pessoa.linha);
    // Uma célula por campo da grade; o valor do primeiro é o botão que abre a ficha (o jeito de quem usa o teclado).
    let e_a_primeira_coluna = true;
    for (const coluna of colunas_da_grade) {
      const valor = pessoa.campos[coluna.campo];
      if (e_a_primeira_coluna) {
        linha_da_grade.append(celula_do_nome_com_ficha(pessoa, texto_do_botao_do_detalhe(coluna, valor)));
      } else {
        linha_da_grade.append(celula_do_valor(coluna, valor));
      }
      e_a_primeira_coluna = false;
    }
    // As duas últimas células: Situação e Ação.
    const finais_da_grade = celulas_de_situacao_e_acao(envio, pessoa);
    linha_da_grade.append(finais_da_grade[0], finais_da_grade[1]);
    // A linha inteira abre a ficha da pessoa, com todos os campos
    abrir_o_detalhe_ao_clicar_na_linha(linha_da_grade, function () {
      abrir_ficha_da_pessoa(String(pessoa.linha));
    });
    // Devolve a linha pronta.
    return linha_da_grade;
  }
  // Linha da tabela, com a linha do arquivo guardada.
  const linha = criar_elemento("tr", "", "");
  linha.dataset.linhaPessoa = String(pessoa.linha);
  // Célula com nome e cargo (cargo menor, embaixo); o nome é o botão que abre a ficha completa.
  const celula_nome = celula_do_nome_com_ficha(pessoa, pessoa.nome);
  celula_nome.classList.add("celula-duas-linhas");
  celula_nome.append(criar_elemento("span", "", pessoa.cargo));
  // CPF inteiro (o especialista tem autorização contratual da empresa), admissão e salário.
  const celula_cpf = criar_elemento("td", "", pessoa.cpf);
  const celula_admissao = criar_elemento("td", "", pessoa.admissao);
  const celula_salario = criar_elemento("td", "", formatar_reais(pessoa.salario));
  // Junta as células na linha (a situação e a ação vêm da função comum às duas formas da tabela).
  const finais = celulas_de_situacao_e_acao(envio, pessoa);
  linha.append(celula_nome, celula_cpf, celula_admissao, celula_salario, finais[0], finais[1]);
  // Devolve a linha pronta.
  return linha;
}

/**
 * A célula do nome: um botão que abre a ficha completa da pessoa.
 *
 * Recebe: pessoa; nome — o texto do botão (no exemplo, o nome; com os dados de verdade, o valor do primeiro campo da
 * grade, ex.: o CPF, porque o nome não é obrigatório no parâmetro de hoje). Devolve: o <td>.
 */
function celula_do_nome_com_ficha(pessoa, nome) {
  const celula = criar_elemento("td", "", "");
  const botao = criar_elemento("button", "botao-nome", nome);
  botao.type = "button";
  // A linha da pessoa: o clique acha a pessoa por ela (ver tratar_clique).
  botao.dataset.abrirFichaPessoa = String(pessoa.linha);
  botao.setAttribute("aria-label", "Ver a ficha completa de " + nome);
  celula.append(botao);
  return celula;
}

// ===== Baixar a lista do envio =====

/**
 * Baixa a lista das pessoas do envio aberto, a mesma da grade, num arquivo .csv que o Excel abre.
 *
 * Recebe: nada. Devolve: nada; o navegador baixa o arquivo.
 * Com os dados de verdade, o arquivo vem do servidor (todos os campos do parâmetro, com o CPF inteiro, e o download
 * fica registrado nos acessos da empresa). Aberta como arquivo (protótipo), o arquivo é montado com os exemplos.
 */
function baixar_lista_do_envio() {
  const envio = estado_da_tela.envio_aberto;
  // Dados de verdade: um link temporário para a rota do servidor, que o navegador "clica" sozinho
  if (modo_real_dos_envios()) {
    const link = document.createElement("a");
    link.href = "/api/banco/envios/" + encodeURIComponent(envio.id) + "/baixar";
    link.download = "";
    link.click();
    return;
  }
  // Protótipo: o cabeçalho e uma linha por pessoa de exemplo
  const linhas_do_arquivo = ["Linha no arquivo;Nome;CPF;Cargo;Admissão;Salário;Situação na avaliação"];
  for (const pessoa of envio.pessoas) {
    const valores = [pessoa.linha, pessoa.nome, pessoa.cpf, pessoa.cargo, pessoa.admissao, formatar_reais(pessoa.salario),
      SELOS_DAS_SITUACOES[situacao_da_pessoa(pessoa)].texto];
    linhas_do_arquivo.push(valores.join(";"));
  }
  // "\ufeff" no começo avisa o Excel que o arquivo é UTF-8 (senão os acentos saem errados)
  const arquivo = new Blob(["\ufeff" + linhas_do_arquivo.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(arquivo);
  link.download = "envio_" + envio.id + ".csv";
  link.click();
  // Libera a memória do arquivo temporário
  URL.revokeObjectURL(link.href);
}

// ===== Ficha completa da pessoa =====
// As iniciais do círculo da ficha vêm de iniciais_do_nome, no js/grade_do_parametro.js (a mesma das outras telas).

/**
 * Um grupo da ficha (ex.: "Titular"), com o nome e o valor de cada campo.
 *
 * Recebe: titulo; campos — lista de {nome, valor, obrigatorio}; valor vazio vira "Informação não encontrada".
 * Devolve: o elemento <section>.
 */
function montar_grupo_da_ficha_da_pessoa(titulo, campos) {
  const grupo = criar_elemento("section", "ficha-grupo", "");
  grupo.append(criar_elemento("h3", "ficha-grupo-titulo", titulo));
  // A lista de campos: <dt> é o nome do campo, <dd> é o valor.
  const lista = criar_elemento("dl", "ficha-campos", "");
  for (const campo of campos) {
    const nome_do_campo = criar_elemento("dt", "", campo.nome);
    // Campo obrigatório no parâmetro: a mesma marca "*" do cabeçalho da grade.
    if (campo.obrigatorio) {
      const marca = criar_elemento("span", "marca-obrigatorio", "*");
      marca.setAttribute("aria-label", "obrigatório");
      nome_do_campo.append(marca);
    }
    const valor = criar_elemento("dd", "", "");
    if (campo.valor) {
      valor.textContent = campo.valor;
    } else {
      // Campo que não veio no arquivo: a mesma frase da grade.
      valor.append(criar_elemento("span", "valor-nao-encontrado", "Informação não encontrada"));
    }
    lista.append(nome_do_campo, valor);
  }
  grupo.append(lista);
  return grupo;
}

/**
 * Os grupos de campos da pessoa, na ordem do parâmetro vigente do banco (dados de verdade), ou os campos do
 * protótipo num grupo só (aberta como arquivo).
 *
 * Recebe: pessoa. Devolve: a lista de elementos <section>.
 * Com os dados de verdade, são TODOS os campos do parâmetro (a grade mostra só os obrigatórios; ADR-143), montados
 * pelo js/grade_do_parametro.js, o mesmo detalhe das outras telas.
 */
function grupos_da_ficha_da_pessoa(pessoa) {
  // Protótipo (sem as colunas do parâmetro): os campos de exemplo.
  if (colunas_do_detalhe.length === 0 || !pessoa.campos) {
    return [montar_grupo_da_ficha_da_pessoa("Dados do funcionário", [
      { nome: "Nome completo", valor: pessoa.nome, obrigatorio: true },
      { nome: "CPF", valor: pessoa.cpf, obrigatorio: true },
      { nome: "Cargo", valor: pessoa.cargo, obrigatorio: false },
      { nome: "Data de admissão", valor: pessoa.admissao, obrigatorio: false },
      { nome: "Salário", valor: formatar_reais(pessoa.salario), obrigatorio: false },
    ])];
  }
  // Dados de verdade: todos os campos, juntados pelo grupo do parâmetro, na ordem em que os grupos aparecem.
  return grupos_do_detalhe(colunas_do_detalhe, pessoa.campos);
}

/**
 * O bloco "Avaliação do banco" da ficha: o que a empresa confirmou sobre a pessoa e o problema apontado.
 *
 * Recebe: envio; pessoa. Devolve: o <section>, ou null quando não há nada a mostrar.
 */
function avaliacao_na_ficha(envio, pessoa) {
  const itens = [];
  // Os alertas desta pessoa que a empresa confirmou antes de enviar
  for (const alerta of envio.alertas) {
    if (alerta.linha !== undefined && String(alerta.linha) === String(pessoa.linha)) {
      itens.push(alerta.selo + ": " + alerta.texto);
    }
  }
  // O problema apontado pelo especialista, ainda sem decisão
  if (pessoa.apontamento) {
    itens.push("Apontado por você (" + pessoa.apontamento.motivo_texto + "): \"" + pessoa.apontamento.recado + "\"");
  }
  if (itens.length === 0) {
    return null;
  }
  const bloco = criar_elemento("section", "ficha-grupo ficha-grupo-avaliacao", "");
  bloco.dataset.fichaAvaliacao = "";
  bloco.append(criar_elemento("h3", "ficha-grupo-titulo", "Avaliação do banco"));
  const lista = criar_elemento("ul", "ficha-avaliacao-lista", "");
  for (const item of itens) {
    lista.append(criar_elemento("li", "", item));
  }
  bloco.append(lista);
  return bloco;
}

/**
 * Os botões do pé da ficha: "Voltar" e, com o envio esperando o banco, "Apontar problema" ou "Desfazer o apontamento".
 *
 * Recebe: envio; pessoa. Devolve: a lista de botões.
 */
function botoes_da_ficha(envio, pessoa) {
  const voltar = criar_elemento("button", "botao botao-contorno", "Voltar");
  voltar.type = "button";
  voltar.dataset.fecharJanela = "";
  const botoes = [voltar];
  // Envio já avaliado, ou pessoa que espera a empresa: a ficha é só para ler
  if (!envio_esta_aguardando(envio) || situacao_da_pessoa(pessoa) === "aguardando") {
    return botoes;
  }
  // Os mesmos botões da tabela (o clique passa por tratar_clique, que fecha a ficha antes)
  if (pessoa.apontamento) {
    const desfazer = criar_elemento("button", "botao botao-contorno", "Desfazer o apontamento");
    desfazer.type = "button";
    desfazer.dataset.desfazerApontamento = String(pessoa.linha);
    botoes.push(desfazer);
  } else {
    const apontar = criar_elemento("button", "botao botao-principal", "Apontar problema");
    apontar.type = "button";
    apontar.dataset.apontarProblema = String(pessoa.linha);
    botoes.push(apontar);
  }
  return botoes;
}

/**
 * Abre a ficha completa de uma pessoa do envio aberto: todos os campos do parâmetro, agrupados, e a avaliação.
 *
 * Recebe: linha — a linha da pessoa no arquivo (do botão do nome). Devolve: nada; mostra a janela.
 */
function abrir_ficha_da_pessoa(linha) {
  const pessoa = achar_pessoa_pela_linha(linha);
  if (!pessoa) {
    return;
  }
  const envio = estado_da_tela.envio_aberto;
  // Cabeçalho: iniciais, situação, nome e um resumo de uma linha
  document.querySelector("[data-ficha-iniciais]").textContent = iniciais_do_nome(pessoa.nome);
  document.querySelector("[data-ficha-situacao]").textContent = SELOS_DAS_SITUACOES[situacao_da_pessoa(pessoa)].texto;
  // O nome não é obrigatório no parâmetro de hoje (ADR-143): sem ele, o título é o CPF
  document.querySelector("[data-ficha-nome]").textContent = titulo_do_detalhe(pessoa.nome, pessoa.cpf);
  const partes_do_resumo = [];
  if (pessoa.cargo) {
    partes_do_resumo.push(pessoa.cargo);
  }
  if (pessoa.cpf) {
    partes_do_resumo.push("CPF " + pessoa.cpf);
  }
  partes_do_resumo.push("linha " + pessoa.linha + " do arquivo");
  document.querySelector("[data-ficha-resumo]").textContent = partes_do_resumo.join(" · ");
  // Os grupos de campos e, no fim, a avaliação
  const grupos = document.querySelector("[data-ficha-grupos]");
  grupos.replaceChildren();
  for (const grupo of grupos_da_ficha_da_pessoa(pessoa)) {
    grupos.append(grupo);
  }
  // O que a IA guardou sem rótulo, logo depois dos campos: só quando há alguma (js/grade_do_parametro.js; ADR-143,
  // Parte 1)
  acrescentar_informacoes_sem_rotulo(grupos, pessoa);
  const avaliacao = avaliacao_na_ficha(envio, pessoa);
  if (avaliacao) {
    grupos.append(avaliacao);
  }
  // Os botões do pé
  document.querySelector("[data-ficha-botoes]").replaceChildren(...botoes_da_ficha(envio, pessoa));
  // Abre por cima da página, escurecendo o fundo
  document.getElementById("janela-ficha-pessoa").showModal();
}

/**
 * Fecha a ficha da pessoa, se estiver aberta (antes de abrir outra janela a partir dela).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_ficha_da_pessoa() {
  const ficha = document.getElementById("janela-ficha-pessoa");
  if (ficha.open) {
    ficha.close();
  }
}

/**
 * As duas últimas células da linha de uma pessoa: a situação (com o recado, se houver apontamento) e a ação
 * ("Apontar problema" ou "Desfazer").
 *
 * Recebe: envio; pessoa. Devolve: [a célula da situação, a célula da ação].
 */
function celulas_de_situacao_e_acao(envio, pessoa) {
  // A situação da pessoa e o selo dela.
  const situacao = situacao_da_pessoa(pessoa);
  const selo = SELOS_DAS_SITUACOES[situacao];
  // Célula da situação, com o selo.
  const celula_situacao = criar_elemento("td", "celula-situacao-pessoa", "");
  const elemento_do_selo = criar_elemento("span", "selo selo-pequeno " + selo.classe, selo.texto);
  celula_situacao.append(elemento_do_selo);
  // Com problema apontado: o selo ganha a marca para os roteiros, e o recado aparece embaixo (inteiro ao passar o mouse).
  if (pessoa.apontamento) {
    elemento_do_selo.dataset.seloApontado = "";
    const texto_do_recado = pessoa.apontamento.motivo_texto + ": \"" + pessoa.apontamento.recado + "\"";
    const recado = criar_elemento("span", "recado-do-apontamento", texto_do_recado);
    recado.dataset.recadoApontamento = "";
    recado.title = texto_do_recado;
    celula_situacao.append(recado);
  }

  // Célula da ação.
  const celula_acao = criar_elemento("td", "", "");
  // Envio já avaliado, ou pessoa que espera a empresa: sem botões.
  if (!envio_esta_aguardando(envio) || situacao === "aguardando") {
    return [celula_situacao, celula_acao];
  }
  // Com problema apontado: "Desfazer" tira o apontamento (a pessoa volta para a aprovação).
  if (pessoa.apontamento) {
    const botao_desfazer = criar_elemento("button", "botao-nome", "Desfazer");
    botao_desfazer.type = "button";
    botao_desfazer.dataset.desfazerApontamento = String(pessoa.linha);
    botao_desfazer.setAttribute("aria-label",
      "Desfazer o problema apontado em " + titulo_do_detalhe(pessoa.nome, pessoa.cpf));
    celula_acao.append(botao_desfazer);
    return [celula_situacao, celula_acao];
  }
  // Sem apontamento: "Apontar problema" abre a janela com o motivo e o recado.
  const botao_apontar = criar_elemento("button", "botao-nome", "Apontar problema");
  botao_apontar.type = "button";
  botao_apontar.dataset.apontarProblema = String(pessoa.linha);
  botao_apontar.setAttribute("aria-label", "Apontar problema em " + titulo_do_detalhe(pessoa.nome, pessoa.cpf));
  celula_acao.append(botao_apontar);
  // Devolve as duas células.
  return [celula_situacao, celula_acao];
}

// ===== 9. Decisão: aprovar, aprovar e devolver os apontados, ou devolver o envio inteiro =====

/**
 * Quantas pessoas ficam cadastradas se o especialista decidir agora: todos, menos os apontados e quem espera a
 * empresa.
 *
 * Recebe: contagem — pessoas por situação. Devolve: um número.
 */
function quantas_seriam_aprovadas(contagem) {
  // Pronto e alerta aceito (que volta a "pronto") entram; o alerta aberto também conta, pois só se decide sem ele.
  return contagem.pronto + contagem.alerta;
}

/**
 * Escreve a frase da barra de decisão e guarda a frase inteira para aparecer ao passar o mouse (a barra, discreta,
 * mostra no máximo duas linhas).
 *
 * Recebe: resumo — o parágrafo da frase; texto. Devolve: nada.
 */
function escrever_resumo_da_decisao(resumo, texto) {
  resumo.textContent = texto;
  resumo.title = texto;
}

/**
 * Mostra a barra de decisão (envio na fila) ou o resultado (envio já avaliado).
 *
 * Recebe: envio; contagem — pessoas por situação; alertas_abertos — quantos alertas faltam decidir.
 * Devolve: nada.
 */
function mostrar_decisao(envio, contagem, alertas_abertos) {
  // A barra, o resultado, o botão de aprovar, a frase e a confirmação do "Aprovar e devolver".
  const barra = document.querySelector("[data-barra-decisao]");
  const resultado = document.querySelector("[data-resultado-avaliacao]");
  const botao_aprovar = document.querySelector("[data-aprovar-envio]");
  const resumo = document.querySelector("[data-resumo-decisao]");
  // Toda vez que a barra é redesenhada, volta ao normal (a confirmação some).
  esconder_confirmacao_da_decisao();

  // Envio já avaliado: esconde a barra e mostra o resultado.
  if (!envio_esta_aguardando(envio)) {
    barra.hidden = true;
    resultado.hidden = false;
    resultado.textContent = envio.resultado;
    // Devolvido fica cinza (não é um sucesso); aprovado fica verde.
    resultado.classList.toggle("painel-vazio-neutro", envio.situacao === "devolvido");
    return;
  }

  // Envio na fila: mostra a barra e esconde o resultado.
  barra.hidden = false;
  resultado.hidden = true;
  // O botão de aprovar volta a aparecer e a funcionar (cada caso abaixo ajusta).
  botao_aprovar.hidden = false;
  botao_aprovar.disabled = false;

  // Com alerta aberto, não dá para aprovar: o especialista decide cada alerta antes.
  if (alertas_abertos > 0) {
    botao_aprovar.disabled = true;
    botao_aprovar.textContent = "Decida os alertas para aprovar";
    botao_aprovar.dataset.decisao = "";
    escrever_resumo_da_decisao(resumo, "Falta decidir " + numero_com_palavra(alertas_abertos, "alerta", "alertas") + ": aceite o valor ou aponte um problema.");
    return;
  }

  // Quantas ficam cadastradas e quantas voltam para a empresa.
  const aprovadas = quantas_seriam_aprovadas(contagem);
  const apontadas = contagem.apontado;
  // A frase de quem continua com a empresa (vazia se ninguém).
  const frase_de_quem_espera = frase_de_quem_espera_a_empresa(contagem.aguardando);

  // Sem nenhum apontamento: "Aprovar o envio".
  if (apontadas === 0) {
    botao_aprovar.textContent = "Aprovar o envio";
    botao_aprovar.dataset.decisao = "aprovar";
    escrever_resumo_da_decisao(resumo, "Ao aprovar, " + numero_com_palavra(aprovadas, "funcionário", "funcionários") + " " + no_singular_ou_plural(aprovadas, "fica cadastrado", "ficam cadastrados") + " e a empresa vê isso na hora." + frase_de_quem_espera);
    return;
  }

  // Todos apontados: não sobra ninguém para aprovar, então só faz sentido devolver o envio inteiro.
  if (aprovadas === 0) {
    botao_aprovar.hidden = true;
    botao_aprovar.dataset.decisao = "";
    escrever_resumo_da_decisao(resumo, "Você apontou problema " + no_singular_ou_plural(apontadas, "na única pessoa", "em todas as " + apontadas + " pessoas") + " deste envio: não sobra ninguém para aprovar. Use \"Devolver o envio inteiro\"; os problemas apontados vão junto, como pendências para a empresa.");
    return;
  }

  // Com apontamentos: "Aprovar N e devolver M".
  botao_aprovar.textContent = "Aprovar " + numero_com_palavra(aprovadas, "pessoa", "pessoas") + " e devolver " + apontadas;
  botao_aprovar.dataset.decisao = "aprovar_e_devolver_marcados";
  escrever_resumo_da_decisao(resumo, frase_de_aprovar_e_devolver(aprovadas, apontadas) + frase_de_quem_espera);
}

/**
 * A frase que explica o "Aprovar N e devolver M".
 *
 * Recebe: aprovadas; apontadas. Devolve: o texto.
 * Exemplo: (33, 2) → "Ao decidir, 33 funcionários ficam cadastrados na hora e 2 pessoas apontadas voltam para a
 *          empresa num envio de devolução, com o seu recado."
 */
function frase_de_aprovar_e_devolver(aprovadas, apontadas) {
  // Quem fica cadastrado (singular ou plural).
  const parte_dos_cadastrados = numero_com_palavra(aprovadas, "funcionário", "funcionários") + " " + no_singular_ou_plural(aprovadas, "fica cadastrado", "ficam cadastrados") + " na hora";
  // Quem volta para a empresa (singular ou plural).
  const parte_dos_devolvidos = numero_com_palavra(apontadas, "pessoa apontada volta", "pessoas apontadas voltam") + " para a empresa num envio de devolução, com o seu recado";
  // Junta as duas partes.
  return "Ao decidir, " + parte_dos_cadastrados + " e " + parte_dos_devolvidos + ".";
}

/**
 * A frase de quem continua com a empresa até ela responder (vazia quando ninguém).
 *
 * Recebe: quantas — pessoas aguardando a empresa. Devolve: o texto (começa com espaço) ou "".
 */
function frase_de_quem_espera_a_empresa(quantas) {
  // Ninguém esperando: nada a dizer.
  if (quantas === 0) {
    return "";
  }
  // "1 continua" ou "3 continuam" com a empresa.
  return " " + quantas + " " + no_singular_ou_plural(quantas, "continua", "continuam") + " com a empresa até ela responder.";
}

/**
 * O clique no botão de aprovar: "Aprovar o envio" decide na hora; "Aprovar N e devolver M" pede confirmação na
 * própria barra (o envio se divide e não dá para desfazer).
 *
 * Recebe: nada. Devolve: nada.
 */
function aprovar_envio() {
  // Qual decisão o botão está oferecendo agora.
  const decisao = document.querySelector("[data-aprovar-envio]").dataset.decisao;
  // "Aprovar e devolver": primeiro a confirmação, na própria barra.
  if (decisao === "aprovar_e_devolver_marcados") {
    mostrar_confirmacao_da_decisao();
    return;
  }
  // Com servidor, a aprovação é gravada na aplicação (js/banco_envios_real.js).
  if (modo_real_dos_envios()) {
    avaliar_de_verdade("aprovar", "");
    return;
  }
  // O envio aberto e as contagens.
  const envio = estado_da_tela.envio_aberto;
  const contagem = contar_pessoas(envio);
  const aprovadas = quantas_seriam_aprovadas(contagem);
  // Marca o envio como aprovado.
  envio.situacao = "aprovado";
  envio.prazo = { texto: "Aprovado", classe: "selo-sucesso" };
  // Texto do resultado, que fica no lugar da barra de decisão.
  envio.resultado = "Aprovado por você agora. " + numero_com_palavra(aprovadas, "funcionário cadastrado", "funcionários cadastrados") + "." + frase_de_quem_espera_a_empresa(contagem.aguardando);
  // A rodada entra nas idas e voltas.
  anotar_ida_e_volta(envio, "aprovado", "O banco aprovou " + aprovadas);
  // Aviso verde no alto da página.
  mostrar_aviso("Envio aprovado. A " + envio.empresa + " já vê " + numero_com_palavra(aprovadas, "funcionário", "funcionários") + " como " + no_singular_ou_plural(aprovadas, "cadastrado", "cadastrados") + ".");
  // Redesenha o envio e a fila.
  abrir_envio(envio);
}

/**
 * Mostra a confirmação do "Aprovar N e devolver M" no lugar da frase e dos botões da barra.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_confirmacao_da_decisao() {
  // As contagens do envio aberto.
  const contagem = contar_pessoas(estado_da_tela.envio_aberto);
  const aprovadas = quantas_seriam_aprovadas(contagem);
  // A frase da confirmação: o que acontece e que não dá para desfazer.
  const texto = "Confirma? " + frase_de_aprovar_e_devolver(aprovadas, contagem.apontado) + " Não dá para desfazer.";
  document.querySelector("[data-confirmacao-decisao-texto]").textContent = texto;
  // Troca a frase e os botões normais pela confirmação.
  document.querySelector("[data-resumo-decisao]").hidden = true;
  document.querySelector("[data-botoes-decisao]").hidden = true;
  document.querySelector("[data-confirmacao-decisao]").hidden = false;
  // O botão "Sim" volta a funcionar (fica desligado enquanto o servidor responde).
  document.querySelector("[data-confirmar-decisao]").disabled = false;
}

/**
 * Esconde a confirmação e volta a frase e os botões normais da barra.
 *
 * Recebe: nada. Devolve: nada.
 */
function esconder_confirmacao_da_decisao() {
  // A confirmação some.
  document.querySelector("[data-confirmacao-decisao]").hidden = true;
  // A frase e os botões voltam.
  document.querySelector("[data-resumo-decisao]").hidden = false;
  document.querySelector("[data-botoes-decisao]").hidden = false;
}

/**
 * O especialista confirmou o "Aprovar N e devolver M": os N ficam cadastrados e os M voltam para a empresa num
 * envio de devolução.
 *
 * Recebe: nada. Devolve: nada.
 */
function confirmar_aprovar_e_devolver() {
  // O "Sim" fica desligado, para um segundo clique não mandar a decisão duas vezes.
  document.querySelector("[data-confirmar-decisao]").disabled = true;
  // Com servidor, a decisão é gravada na aplicação (js/banco_envios_real.js).
  if (modo_real_dos_envios()) {
    avaliar_de_verdade("aprovar_e_devolver_marcados", "");
    return;
  }
  // Sem servidor (protótipo): divide o envio na tela.
  dividir_envio_no_prototipo(estado_da_tela.envio_aberto);
}

/**
 * Protótipo: o envio aberto vira "Aprovado" com as pessoas sem apontamento, e as apontadas vão para um envio de
 * devolução novo na fila dos avaliados ("Devolvido", esperando a empresa).
 *
 * Recebe: envio. Devolve: nada.
 */
function dividir_envio_no_prototipo(envio) {
  // Separa quem fica no envio de quem volta (apontado), e conta quem fica cadastrado.
  const ficam_no_envio = [];
  const devolvidas = [];
  let quantas_aprovadas = 0;
  for (const pessoa of envio.pessoas) {
    // Apontada: vai para o envio de devolução.
    if (pessoa.apontamento) {
      devolvidas.push(pessoa);
      continue;
    }
    // As outras ficam no envio de origem.
    ficam_no_envio.push(pessoa);
    // Quem espera a empresa fica no envio, mas não é cadastrado agora.
    if (situacao_da_pessoa(pessoa) !== "aguardando") {
      quantas_aprovadas = quantas_aprovadas + 1;
    }
  }
  // O texto da rodada: "O banco aprovou 33 e devolveu 2 (Ana: Confirmar o salário; João: CPF incorreto)".
  const motivos_de_cada_uma = [];
  for (const pessoa of devolvidas) {
    motivos_de_cada_uma.push(pessoa.nome + ": " + pessoa.apontamento.motivo_texto);
  }
  const texto_da_rodada = "O banco aprovou " + quantas_aprovadas + " e devolveu " + devolvidas.length + " (" + motivos_de_cada_uma.join("; ") + ")";
  // O dia de hoje no jeito curto ("28/09"), para a origem do envio de devolução.
  const dia_de_hoje = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  // O envio de devolução, com as pessoas apontadas (e o recado de cada uma), esperando a empresa.
  const envio_de_devolucao = {
    id: envio.id + "-devolucao",
    empresa: envio.empresa,
    tipo: envio.tipo,
    detalhe: "Devolvido por você agora · esperando a empresa responder",
    situacao: "devolvido",
    origem: "Devolução do envio de " + dia_de_hoje + " (" + numero_com_palavra(devolvidas.length, "pessoa", "pessoas") + ")",
    resultado: "Devolvido à empresa agora: " + numero_com_palavra(devolvidas.length, "pessoa apontada", "pessoas apontadas") + " por você. Quando a empresa responder, o envio volta para a sua fila.",
    prazo: { texto: "Devolvido", classe: "selo-atencao" },
    valores_padronizados: 0,
    trilha: ["Criado agora com as pessoas que você apontou no envio de origem."],
    idas_e_voltas: [],
    respostas_aos_apontamentos: [],
    alertas: [],
    pessoas: devolvidas,
  };
  // O envio de origem fica sem as apontadas e vira "Aprovado".
  envio.pessoas = ficam_no_envio;
  envio.situacao = "aprovado";
  envio.prazo = { texto: "Aprovado", classe: "selo-sucesso" };
  envio.resultado = "Aprovado por você agora: " + numero_com_palavra(quantas_aprovadas, "funcionário cadastrado", "funcionários cadastrados") + " e " + numero_com_palavra(devolvidas.length, "pessoa devolvida", "pessoas devolvidas") + " à empresa num envio de devolução.";
  // A rodada entra nas idas e voltas dos dois envios.
  anotar_ida_e_volta(envio, "aprovado_em_parte", texto_da_rodada);
  envio_de_devolucao.idas_e_voltas = envio.idas_e_voltas.slice();
  // O envio de devolução entra na fila.
  ENVIOS.push(envio_de_devolucao);
  // Aviso no alto da página.
  mostrar_aviso("Pronto: " + numero_com_palavra(quantas_aprovadas, "funcionário cadastrado", "funcionários cadastrados") + ", e " + numero_com_palavra(devolvidas.length, "pessoa voltou", "pessoas voltaram") + " para a " + envio.empresa + " com o seu recado.");
  // Redesenha o envio e a fila.
  abrir_envio(envio);
}

/**
 * Protótipo: acrescenta uma rodada nas idas e voltas do envio, com a data e a hora de agora.
 *
 * Recebe: envio; tipo — "enviado", "devolvido", "aprovado_em_parte" ou "aprovado"; texto. Devolve: nada.
 */
function anotar_ida_e_volta(envio, tipo, texto) {
  // A rodada nova, no fim da lista (a linha do tempo sempre anda para a frente).
  envio.idas_e_voltas.push({ quando: new Date().toISOString(), tipo: tipo, texto: texto });
}

/**
 * Mostra o aviso verde no alto da página e leva a tela até ele.
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_aviso(texto) {
  // O aviso e o lugar do texto.
  const aviso = document.querySelector("[data-aviso-decisao]");
  document.querySelector("[data-aviso-decisao-texto]").textContent = texto;
  // Mostra o aviso.
  aviso.hidden = false;
  // Rola a página até o aviso, para a pessoa ver o que aconteceu.
  aviso.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ===== 10. Janelas "Apontar problema" e "Devolver o envio inteiro" =====

/**
 * Abre a janela "Apontar problema" para uma pessoa (se ela já tem apontamento, vem preenchida para trocar).
 *
 * Recebe: linha — a linha da pessoa no arquivo. Devolve: nada.
 */
function abrir_janela_de_apontar(linha) {
  // A pessoa da linha.
  const pessoa = achar_pessoa_pela_linha(linha);
  // Guarda de quem é o apontamento.
  estado_da_tela.linha_do_apontamento = linha;
  // Nome no título da janela.
  document.querySelector("[data-ajuste-nome]").textContent = pessoa.nome;
  // Formulário limpo (ou com o apontamento atual, para trocar).
  let motivo_atual = "";
  let recado_atual = "";
  if (pessoa.apontamento) {
    motivo_atual = pessoa.apontamento.motivo;
    recado_atual = pessoa.apontamento.recado;
  }
  document.querySelector("[data-ajuste-motivo]").value = motivo_atual;
  document.querySelector("[data-ajuste-mensagem]").value = recado_atual;
  // O aviso volta à frase de sempre e fica escondido.
  const aviso = document.querySelector("[data-ajuste-erro]");
  aviso.textContent = AVISO_PADRAO_DO_APONTAMENTO;
  aviso.hidden = true;
  // O botão de confirmar volta a funcionar (fica desligado enquanto o servidor responde).
  document.querySelector("[data-confirmar-apontamento]").disabled = false;
  // Abre a janela (showModal escurece o fundo e prende o foco dentro dela).
  document.getElementById("janela-pedir-ajuste").showModal();
}

/**
 * Verdadeiro se o motivo foi escolhido e a mensagem tem pelo menos 15 letras.
 *
 * Recebe: motivo; mensagem. Devolve: true ou false.
 * Por quê: a empresa precisa entender o pedido; "ver" ou "ok" não ajudam ninguém.
 */
function motivo_e_mensagem_validos(motivo, mensagem) {
  // Os dois precisam estar preenchidos, e a mensagem com um mínimo de conteúdo.
  return motivo !== "" && mensagem.trim().length >= 15;
}

/**
 * Confirma o "Apontar problema": a pessoa sai da aprovação e, ao decidir o envio, volta para a empresa com o recado.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
function confirmar_apontamento(evento) {
  // Impede o fechamento automático da janela; ela só fecha se tudo estiver certo.
  evento.preventDefault();
  // O que foi escolhido e escrito.
  const campo_do_motivo = document.querySelector("[data-ajuste-motivo]");
  const motivo = campo_do_motivo.value;
  const recado = document.querySelector("[data-ajuste-mensagem]").value;
  // Faltou algo: mostra o aviso e não fecha.
  if (!motivo_e_mensagem_validos(motivo, recado)) {
    document.querySelector("[data-ajuste-erro]").hidden = false;
    return;
  }
  // A linha da pessoa.
  const linha = estado_da_tela.linha_do_apontamento;
  // Com servidor, o apontamento é gravado na aplicação (a janela só fecha se o servidor aceitar).
  if (modo_real_dos_envios()) {
    document.querySelector("[data-confirmar-apontamento]").disabled = true;
    apontar_de_verdade(linha, motivo, recado.trim());
    return;
  }
  // O texto do motivo, como aparece na lista (ex.: "Confirmar o salário").
  const motivo_texto = campo_do_motivo.options[campo_do_motivo.selectedIndex].textContent;
  // Protótipo: a pessoa fica com o apontamento.
  achar_pessoa_pela_linha(linha).apontamento = { motivo: motivo, motivo_texto: motivo_texto, recado: recado.trim() };
  // Fecha a janela.
  document.getElementById("janela-pedir-ajuste").close();
  // Redesenha números, alertas, tabela e decisão.
  atualizar_partes_do_envio();
}

/**
 * Desfaz o problema apontado numa pessoa: ela volta para a aprovação.
 *
 * Recebe: linha — a linha da pessoa no arquivo. Devolve: nada.
 */
function desfazer_apontamento(linha) {
  // Com servidor, o apontamento é apagado na aplicação.
  if (modo_real_dos_envios()) {
    desfazer_de_verdade(linha);
    return;
  }
  // Protótipo: a pessoa fica sem apontamento.
  achar_pessoa_pela_linha(linha).apontamento = null;
  // Redesenha números, alertas, tabela e decisão.
  atualizar_partes_do_envio();
}

/**
 * Abre a janela "Devolver o envio inteiro".
 *
 * Recebe: nada. Devolve: nada.
 */
function abrir_janela_de_devolver() {
  // Empresa e tipo no título da janela.
  const envio = estado_da_tela.envio_aberto;
  document.querySelector("[data-devolver-empresa]").textContent = envio.tipo + " da " + envio.empresa;
  // Formulário limpo.
  document.querySelector("[data-devolver-motivo]").value = "";
  document.querySelector("[data-devolver-mensagem]").value = "";
  document.querySelector("[data-devolver-confirmo]").checked = false;
  document.querySelector("[data-devolver-erro]").hidden = true;
  // Abre a janela.
  document.getElementById("janela-devolver").showModal();
}

/**
 * Confirma a devolução: o envio inteiro volta para a empresa, com o motivo, e sai da fila. Os problemas que o
 * especialista apontou vão junto, como pendências da empresa.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
function confirmar_devolucao(evento) {
  // Impede o fechamento automático da janela.
  evento.preventDefault();
  // O que foi escolhido, escrito e marcado.
  const motivo = document.querySelector("[data-devolver-motivo]").value;
  const mensagem = document.querySelector("[data-devolver-mensagem]").value;
  const confirmou = document.querySelector("[data-devolver-confirmo]").checked;
  // Faltou algo: mostra o aviso e não fecha.
  if (!motivo_e_mensagem_validos(motivo, mensagem) || !confirmou) {
    document.querySelector("[data-devolver-erro]").hidden = false;
    return;
  }
  // Com servidor, a devolução é gravada na aplicação, com o motivo que a empresa vai ler.
  if (modo_real_dos_envios()) {
    document.getElementById("janela-devolver").close();
    avaliar_de_verdade("devolver", NOMES_DOS_MOTIVOS[motivo] + ": " + mensagem.trim());
    return;
  }
  // Marca o envio como devolvido, com o motivo e a mensagem.
  const envio = estado_da_tela.envio_aberto;
  const apontadas = contar_pessoas(envio).apontado;
  envio.situacao = "devolvido";
  envio.prazo = { texto: "Devolvido", classe: "selo-atencao" };
  envio.resultado = "Devolvido por você agora (" + NOMES_DOS_MOTIVOS[motivo] + "): \"" + mensagem.trim() + "\" Nenhum funcionário deste envio foi cadastrado.";
  // Os problemas apontados vão junto: o resultado diz quantos.
  if (apontadas > 0) {
    envio.resultado = envio.resultado + " " + numero_com_palavra(apontadas, "problema apontado foi junto", "problemas apontados foram junto") + ", como " + no_singular_ou_plural(apontadas, "pendência", "pendências") + " para a empresa.";
  }
  // A rodada entra nas idas e voltas.
  anotar_ida_e_volta(envio, "devolvido", "O banco devolveu o envio inteiro: \"" + mensagem.trim() + "\"");
  // Fecha a janela.
  document.getElementById("janela-devolver").close();
  // Aviso no alto da página.
  mostrar_aviso("Envio devolvido. A " + envio.empresa + " vê o motivo em Acompanhar cadastros e pode reenviar.");
  // Redesenha o envio e a fila.
  abrir_envio(envio);
}

// ===== 11. Filtros e ligações dos cliques =====

/**
 * Liga visualmente um filtro do grupo e desliga os outros.
 *
 * Recebe: seletor — o grupo de botões; valor — o filtro escolhido; chave — o nome do "data-" no botão.
 * Devolve: nada.
 */
function marcar_filtro_ligado(seletor, valor, chave) {
  // Passa por todos os botões do grupo.
  for (const botao of document.querySelectorAll(seletor)) {
    // Liga só o do valor escolhido.
    botao.classList.toggle("filtro-rapido-ativo", botao.dataset[chave] === valor);
  }
}

/**
 * Trata todos os cliques da página num lugar só (a "delegação de eventos").
 * Em vez de ligar cada botão criado pelo JavaScript, a página inteira escuta e vê em que botão foi.
 *
 * Recebe: evento — o clique. Devolve: nada.
 */
function tratar_clique(evento) {
  // O botão mais próximo de onde a pessoa clicou (o clique pode cair num ícone dentro do botão).
  const botao = evento.target.closest("button");
  // Clique fora de botão: nada a fazer.
  if (!botao) {
    return;
  }
  // Abrir um envio da fila.
  if (botao.dataset.abrirEnvio) {
    abrir_envio(achar_envio(botao.dataset.abrirEnvio));
    return;
  }
  // Filtro da fila ("Esperando você" ou "Avaliados").
  if (botao.dataset.filtroFila) {
    estado_da_tela.filtro_da_fila = botao.dataset.filtroFila;
    marcar_filtro_ligado("[data-filtro-fila]", botao.dataset.filtroFila, "filtroFila");
    mostrar_fila();
    return;
  }
  // Filtro das pessoas ("Todos", "Confirmados pela empresa" ou "Apontados por você").
  if (botao.dataset.filtroPessoas) {
    estado_da_tela.filtro_de_pessoas = botao.dataset.filtroPessoas;
    estado_da_tela.quantas_mostrar = PESSOAS_POR_VEZ;
    marcar_filtro_ligado("[data-filtro-pessoas]", botao.dataset.filtroPessoas, "filtroPessoas");
    mostrar_pessoas();
    return;
  }
  // Aceitar um alerta.
  if (botao.dataset.aceitarAlerta) {
    aceitar_alerta(botao.dataset.aceitarAlerta);
    return;
  }
  // Abrir a ficha completa de uma pessoa (clique no nome, na tabela).
  if (botao.dataset.abrirFichaPessoa) {
    abrir_ficha_da_pessoa(botao.dataset.abrirFichaPessoa);
    return;
  }
  // Apontar problema numa pessoa (da tabela, do cartão do alerta ou da ficha, que fecha antes).
  if (botao.dataset.apontarProblema) {
    fechar_ficha_da_pessoa();
    abrir_janela_de_apontar(botao.dataset.apontarProblema);
    return;
  }
  // Desfazer o problema apontado numa pessoa (da tabela ou da ficha, que fecha antes).
  if (botao.dataset.desfazerApontamento) {
    fechar_ficha_da_pessoa();
    desfazer_apontamento(botao.dataset.desfazerApontamento);
    return;
  }
  // Baixar a lista do envio (a mesma da grade).
  if (botao.hasAttribute("data-baixar-envio")) {
    baixar_lista_do_envio();
    return;
  }
  // Mostrar mais 20 pessoas.
  if (botao.hasAttribute("data-mostrar-mais-pessoas")) {
    estado_da_tela.quantas_mostrar = estado_da_tela.quantas_mostrar + PESSOAS_POR_VEZ;
    mostrar_pessoas();
    return;
  }
  // Aprovar o envio (ou, com apontamentos, pedir a confirmação do "Aprovar e devolver").
  if (botao.hasAttribute("data-aprovar-envio")) {
    aprovar_envio();
    return;
  }
  // "Sim, aprovar e devolver" na confirmação da barra.
  if (botao.hasAttribute("data-confirmar-decisao")) {
    confirmar_aprovar_e_devolver();
    return;
  }
  // "Voltar" na confirmação da barra: nada muda.
  if (botao.hasAttribute("data-cancelar-decisao")) {
    esconder_confirmacao_da_decisao();
    return;
  }
  // Abrir a janela de devolver.
  if (botao.hasAttribute("data-abrir-devolver")) {
    abrir_janela_de_devolver();
    return;
  }
  // Fechar qualquer janela (X ou Cancelar).
  if (botao.hasAttribute("data-fechar-janela")) {
    botao.closest("dialog").close();
  }
}

/**
 * Trata a digitação na busca de pessoas: filtra a tabela a cada letra.
 *
 * Recebe: evento — a digitação. Devolve: nada.
 */
function tratar_busca(evento) {
  // Guarda o texto em minúsculas e sem espaços nas pontas.
  estado_da_tela.busca = evento.target.value.trim().toLowerCase();
  // Volta a mostrar do começo.
  estado_da_tela.quantas_mostrar = PESSOAS_POR_VEZ;
  // Redesenha a tabela.
  mostrar_pessoas();
}

/**
 * Prepara a tela: liga os cliques e abre o envio pedido no endereço (ou o primeiro da fila).
 *
 * Recebe: nada. Devolve: nada. É chamada uma vez, quando a página termina de carregar.
 */
function preparar_tela_de_envios() {
  // Todos os cliques passam por uma função só.
  document.addEventListener("click", tratar_clique);
  // Busca na tabela de pessoas.
  document.querySelector("[data-busca-pessoas]").addEventListener("input", tratar_busca);
  // Envio dos dois formulários das janelas.
  document.querySelector("[data-formulario-ajuste]").addEventListener("submit", confirmar_apontamento);
  document.querySelector("[data-formulario-devolver]").addEventListener("submit", confirmar_devolucao);

  // O envio pedido no endereço (ex.: ?envio=aurora-inclusao), vindo dos botões do Início.
  const envio_pedido = achar_envio(new URLSearchParams(window.location.search).get("envio"));
  // Se o endereço não pediu nenhum (ou pediu um que não existe), abre o primeiro da fila.
  if (envio_pedido) {
    abrir_envio(envio_pedido);
  } else {
    abrir_envio(ENVIOS[0]);
  }
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_envios);
