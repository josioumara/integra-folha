/*
  cadastrar.js — roteiro da IA na tela "Cadastrar funcionários".

  Para que serve: SIMULA a IA lendo o que a empresa enviou, para desenhar a experiência da tela.
  A empresa pode mandar quase tudo: planilha, texto, Word, PDF, foto ou print de conversa, e
  até vários arquivos de uma vez. Depois do envio:
    1. a IA "pensa" (três pontinhos) e escreve mensagens curtas, palavra por palavra;
       as primeiras mensagens mudam conforme o FORMATO (ler um PDF é diferente de ler uma foto);
    2. o lado direito mostra, ao vivo, o que foi enviado, os campos encontrados e os contadores;
    3. no fim aparece o resultado, com os ajustes e as sugestões da IA;
    4. "Conferir a lista" abre a conferência (js/conferir.js), e o envio acontece no fim dela.

  Dois cenários de conteúdo:
    - "tabela": os dados vêm organizados em colunas (planilha, texto, Word, PDF, foto de lista).
      Segue o envio de inclusão da Aurora Alimentos (data/golden/aurora_inclusao.json).
    - "conversa": os dados vêm soltos no meio de mensagens (print de conversa com o gestor).

  Atenção: nada aqui lê o arquivo de verdade. Com a página ligada à aplicação (servida pela API, ADR-69), escolher
  ou arrastar um arquivo vai para o envio de verdade (js/cadastrar_real.js); os botões de exemplo continuam aqui.
  Um arquivo de imagem enviado pela pessoa segue o cenário "tabela"; só o exemplo "Print de
  conversa" usa o cenário "conversa" (na vida real, a IA reconheceria a conversa pelo conteúdo).

  Organização do arquivo:
    - Dados da simulação (constantes em MAIÚSCULAS): formatos, exemplos, cenários, tempos.
    - Funções pequenas de apoio e de tela.
    - Ações do roteiro (o que muda no lado direito da tela).
    - O roteiro inteiro e o início do envio.
    - Ajustes no resultado e preparação dos botões.
*/

// ===== Dados da simulação: tempos =====

// Tempos da animação, em milissegundos (1000 = 1 segundo). Aumente para deixar tudo mais calmo.
const TEMPO_PENSANDO = 700;          // quanto tempo os três pontinhos aparecem antes de cada mensagem
const TEMPO_POR_PALAVRA = 45;        // intervalo entre uma palavra e outra ao "escrever"
const TEMPO_POR_CAMPO = 110;         // intervalo entre um campo reconhecido e o próximo

// ===== Dados da simulação: formatos =====

// Extensões de arquivo de cada formato. A extensão é o final do nome (".pdf", ".docx"...).
const EXTENSOES_POR_FORMATO = {
  planilha: [".xlsx", ".xls", ".ods", ".csv"],
  texto: [".txt"],
  documento: [".doc", ".docx", ".odt", ".rtf"],
  pdf: [".pdf"],
  imagem: [".png", ".jpg", ".jpeg", ".webp", ".heic"],
};

// Como cada formato aparece na tela: nome curto, ícone e as duas primeiras mensagens da IA.
// {arquivo} é trocado pelo nome do arquivo; {quantidade}, pelo número de arquivos.
const APRESENTACAO_DOS_FORMATOS = {
  planilha: {
    rotulo: "Planilha",
    icone: "#icone-planilha",
    mensagens: [
      "Recebi a planilha {arquivo}. Vou começar a leitura.",
      "Ela tem 28 linhas de funcionários e 25 colunas. O cabeçalho está na primeira linha.",
    ],
  },
  texto: {
    rotulo: "Texto",
    icone: "#icone-texto",
    mensagens: [
      "Recebi o arquivo de texto {arquivo}. Vou começar a leitura.",
      "Os dados estão separados por ponto e vírgula. Encontrei 28 funcionários e 25 campos.",
    ],
  },
  documento: {
    rotulo: "Word",
    icone: "#icone-documento",
    mensagens: [
      "Recebi o documento {arquivo}. Vou procurar os dados dos funcionários no meio do texto.",
      "Encontrei uma tabela depois de dois parágrafos de introdução. Ela tem 28 funcionários e 25 colunas.",
    ],
  },
  pdf: {
    rotulo: "PDF",
    icone: "#icone-pdf",
    mensagens: [
      "Recebi o PDF {arquivo}. Vou ler página por página.",
      "São 2 páginas com uma tabela que continua de uma para a outra. Juntei as partes: 28 funcionários e 25 colunas.",
    ],
  },
  imagem: {
    rotulo: "Imagem",
    icone: "#icone-imagem",
    mensagens: [
      "Recebi a imagem {arquivo}. Vou ler o texto que aparece nela.",
      "É a foto de uma lista impressa, um pouco torta. Endireitei a imagem, li o texto e remontei a tabela: 28 funcionários e 25 colunas.",
    ],
  },
  varios: {
    rotulo: "Vários formatos",
    icone: "#icone-varios",
    mensagens: [
      "Recebi {quantidade} arquivos. Vou ler cada um e juntar tudo num cadastro só.",
      "Juntei os dados de todos os arquivos numa tabela só, sem repetir ninguém: 28 funcionários e 25 campos.",
    ],
  },
  conversa: {
    rotulo: "Print de conversa",
    icone: "#icone-conversa",
    mensagens: [
      "Recebi a imagem {arquivo}. Vou ler o que está escrito nela.",
      "É um print de conversa com 14 mensagens. Separei o que é dado de funcionário do resto: cumprimentos, emojis e combinados.",
    ],
  },
};

// Mensagem comum a todos os envios: o tipo de envio é decidido sozinho.
const MENSAGEM_DO_TIPO_DE_ENVIO = {
  etapa: 1,
  tipo: "normal",
  texto: "A Aurora Alimentos já tem funcionários homologados, então este envio entra como arquivo de inclusão.",
  acao: "mostrar_tipo_de_envio",
};

// ===== Dados da simulação: exemplos da demonstração =====

// O que cada botão de exemplo "envia": arquivos, formato e cenário.
const EXEMPLOS = {
  planilha: {
    arquivos: [{ nome: "funcionarios_inclusao_outubro.xlsx", tamanho: 49152 }],
    formato: "planilha",
    cenario: "tabela",
  },
  pdf: {
    arquivos: [{ nome: "relacao_admitidos_setembro.pdf", tamanho: 212992 }],
    formato: "pdf",
    cenario: "tabela",
  },
  conversa: {
    arquivos: [{ nome: "print_conversa_gestor.png", tamanho: 356352 }],
    formato: "conversa",
    cenario: "conversa",
  },
};

// ===== Dados da simulação: cenários =====

// Aparência dos selos de confiança: "alta", "media" ou "ignorada" (informação fora do cadastro).
const APARENCIA_DA_CONFIANCA = {
  alta: { classe_do_selo: "selo-sucesso", texto_do_selo: "alta" },
  media: { classe_do_selo: "selo-atencao", texto_do_selo: "média" },
  ignorada: { classe_do_selo: "selo-neutro", texto_do_selo: "ignorada" },
};

// Cenário "tabela": colunas do arquivo de inclusão da Aurora e o campo do banco de cada uma.
const CENARIO_TABELA = {
  titulo_dos_contadores: "Linhas do arquivo",
  legenda_lidas: "lidas",
  legenda_prontas: "prontas",
  titulo_dos_campos: "Colunas reconhecidas",
  resumo_dos_campos: "24 reconhecidas",
  detalhes_do_conteudo: "28 linhas · 25 colunas",
  total_de_registros: 28,
  registros_com_ajuste: [7, 15],
  tempo_por_registro: 60,
  id_do_resultado: "resultado-tabela",
  campos: [
    { no_arquivo: "ID Funcionário", campo_do_banco: "matricula", confianca: "alta" },
    { no_arquivo: "Funcionário", campo_do_banco: "nome_completo", confianca: "alta" },
    { no_arquivo: "Nº CPF", campo_do_banco: "cpf", confianca: "alta" },
    { no_arquivo: "Data Nasc", campo_do_banco: "data_nascimento", confianca: "alta" },
    { no_arquivo: "Código Postal", campo_do_banco: "cep_residencial", confianca: "alta" },
    { no_arquivo: "Endereço Residencial", campo_do_banco: "logradouro_residencial", confianca: "alta" },
    { no_arquivo: "Número", campo_do_banco: "numero_residencial", confianca: "alta" },
    { no_arquivo: "Bairro Casa", campo_do_banco: "bairro_residencial", confianca: "alta" },
    { no_arquivo: "Cidade Residência", campo_do_banco: "municipio_residencial", confianca: "alta" },
    { no_arquivo: "Sigla UF", campo_do_banco: "uf_residencial", confianca: "alta" },
    { no_arquivo: "Móvel", campo_do_banco: "telefone_celular", confianca: "alta" },
    { no_arquivo: "E-mail Trabalho", campo_do_banco: "email_corporativo", confianca: "alta" },
    { no_arquivo: "Nº CNPJ", campo_do_banco: "cnpj_empregador", confianca: "alta" },
    { no_arquivo: "Centro de Custo", campo_do_banco: "codigo_unidade", confianca: "alta" },
    { no_arquivo: "Local de Trabalho", campo_do_banco: "nome_unidade", confianca: "alta" },
    { no_arquivo: "Função", campo_do_banco: "cargo", confianca: "alta" },
    { no_arquivo: "Início", campo_do_banco: "data_admissao", confianca: "media" },
    { no_arquivo: "Fim da Experiência", campo_do_banco: "data_efetivacao", confianca: "media" },
    { no_arquivo: "Tipo de Vínculo", campo_do_banco: "tipo_renda", confianca: "alta" },
    { no_arquivo: "Remuneração", campo_do_banco: "valor_renda", confianca: "alta" },
    { no_arquivo: "Referência Salarial", campo_do_banco: "data_referencia_renda", confianca: "alta" },
    { no_arquivo: "CEP Com.", campo_do_banco: "cep_comercial", confianca: "alta" },
    { no_arquivo: "Cidade da Unidade", campo_do_banco: "municipio_comercial", confianca: "alta" },
    { no_arquivo: "Estado Empresa", campo_do_banco: "uf_comercial", confianca: "alta" },
    { no_arquivo: "Obs RH", campo_do_banco: "fora do cadastro", confianca: "ignorada" },
  ],
  mensagens: [
    { etapa: 2, tipo: "normal", texto: "Agora vou ligar cada coluna ao campo certo do cadastro do banco.", acao: "reconhecer_campos" },
    { etapa: 2, tipo: "normal", texto: "As colunas são as mesmas do envio de agosto, que o banco já aprovou. Usei esse histórico como referência.", acao: "" },
    { etapa: 2, tipo: "normal", texto: "\"Início\" poderia ser a admissão ou o começo da experiência. Como já existe \"Fim da Experiência\", entendi \"Início\" como a data de admissão.", acao: "" },
    { etapa: 2, tipo: "alerta", texto: "A coluna \"Obs RH\" não faz parte do cadastro do banco. Vou deixá-la de fora.", acao: "" },
    { etapa: 3, tipo: "normal", texto: "Colunas prontas: 24 reconhecidas e 1 ignorada. Agora vou conferir os dados linha a linha.", acao: "conferir_registros" },
    { etapa: 3, tipo: "normal", texto: "Converti salários como \"R$ 3.250,00\" para o formato numérico do banco.", acao: "" },
    { etapa: 3, tipo: "alerta", texto: "Linha 7: o CPF não passa na conferência dos dígitos. Separei para você revisar.", acao: "" },
    { etapa: 3, tipo: "alerta", texto: "Linha 15: a data de admissão 12/11/2026 está no futuro. Pode ser erro de digitação.", acao: "" },
    { etapa: 4, tipo: "sucesso", texto: "Pronto! 26 funcionários estão prontos para enviar e 2 precisam de um ajuste rápido. Deixei sugestões para você logo abaixo.", acao: "mostrar_resultado" },
  ],
};

// Cenário "conversa": trechos das mensagens e o campo do banco que cada um preenche.
const CENARIO_CONVERSA = {
  titulo_dos_contadores: "Funcionários na conversa",
  legenda_lidas: "encontrados",
  legenda_prontas: "prontos",
  titulo_dos_campos: "Informações encontradas",
  resumo_dos_campos: "12 aproveitadas",
  detalhes_do_conteudo: "14 mensagens · 3 funcionários",
  total_de_registros: 3,
  registros_com_ajuste: [3],
  tempo_por_registro: 400,
  id_do_resultado: "resultado-conversa",
  campos: [
    { no_arquivo: "“Bom dia, Marina!”", campo_do_banco: "não é dado de cadastro", confianca: "ignorada" },
    { no_arquivo: "“Carla Mendes Souza”", campo_do_banco: "nome_completo", confianca: "alta" },
    { no_arquivo: "“CPF 318.***.***-40”", campo_do_banco: "cpf", confianca: "alta" },
    { no_arquivo: "“nasceu em 14/03/1998”", campo_do_banco: "data_nascimento", confianca: "alta" },
    { no_arquivo: "“vai ser auxiliar de produção”", campo_do_banco: "cargo", confianca: "alta" },
    { no_arquivo: "“começa segunda, dia 28”", campo_do_banco: "data_admissao", confianca: "media" },
    { no_arquivo: "“salário de 2.400”", campo_do_banco: "valor_renda", confianca: "alta" },
    { no_arquivo: "“na unidade de Campinas”", campo_do_banco: "nome_unidade", confianca: "alta" },
    { no_arquivo: "“Diego Ramos Teixeira”", campo_do_banco: "nome_completo", confianca: "alta" },
    { no_arquivo: "“CPF 205.***.***-11”", campo_do_banco: "cpf", confianca: "alta" },
    { no_arquivo: "“mesmo cargo da Carla”", campo_do_banco: "cargo", confianca: "media" },
    { no_arquivo: "“Paula Nogueira Lins”", campo_do_banco: "nome_completo", confianca: "alta" },
    { no_arquivo: "“analista de qualidade”", campo_do_banco: "cargo", confianca: "alta" },
    { no_arquivo: "“kkk boa! 👍”", campo_do_banco: "não é dado de cadastro", confianca: "ignorada" },
  ],
  mensagens: [
    { etapa: 2, tipo: "normal", texto: "Aqui os dados não estão em colunas. Vou identificar cada informação pelo contexto da conversa.", acao: "reconhecer_campos" },
    { etapa: 2, tipo: "normal", texto: "\"Começa segunda, dia 28\" virou 28/09/2026, que é a próxima segunda-feira.", acao: "" },
    { etapa: 2, tipo: "normal", texto: "\"Mesmo cargo da Carla\" quer dizer que o Diego também será auxiliar de produção.", acao: "" },
    { etapa: 2, tipo: "alerta", texto: "\"Bom dia, Marina!\" e \"kkk boa!\" não são dados de cadastro. Deixei de fora.", acao: "" },
    { etapa: 3, tipo: "normal", texto: "Montei o cadastro de 3 funcionários a partir da conversa. Agora vou conferir cada um.", acao: "conferir_registros" },
    { etapa: 3, tipo: "alerta", texto: "Paula Nogueira Lins: o CPF dela não aparece em nenhuma mensagem.", acao: "" },
    { etapa: 4, tipo: "sucesso", texto: "Pronto! 2 funcionários estão prontos para enviar e 1 precisa de um dado que não estava na conversa.", acao: "mostrar_resultado" },
  ],
};

// Os cenários pelo nome, para achar o certo a partir do texto "tabela" ou "conversa".
const CENARIOS = {
  tabela: CENARIO_TABELA,
  conversa: CENARIO_CONVERSA,
};

// ===== Estado do envio (muda durante o uso da tela) =====

// O envio em andamento: fica vazio (null) até a pessoa enviar algo.
let envio_atual = null;

// Quantos funcionários estão prontos e quantos ainda têm ajuste pendente (mudam quando a pessoa corrige).
let quantidade_de_prontos = 0;
let quantidade_de_pendentes = 0;

// ===== Funções pequenas de apoio =====

/**
 * Espera um tempo antes de seguir para a próxima linha do roteiro.
 *
 * Recebe: milissegundos — quanto tempo esperar (1000 = 1 segundo).
 * Devolve: uma "promessa" (Promise), que é um aviso de "terminei" que chega depois do tempo.
 * Exemplo: await esperar(500) pausa o roteiro por meio segundo, sem travar a página.
 */
function esperar(milissegundos) {
  // Cria a promessa e pede ao navegador para cumpri-la depois do tempo pedido.
  return new Promise(function (cumprir_promessa) {
    setTimeout(cumprir_promessa, milissegundos);
  });
}

/**
 * Devolve a hora atual no formato "14:32", para mostrar embaixo de cada mensagem.
 */
function hora_atual() {
  // toLocaleTimeString formata a hora no padrão brasileiro, só com hora e minuto.
  return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Transforma um tamanho em bytes num texto fácil de ler.
 *
 * Recebe: tamanho_em_bytes — número (ex.: 49152).
 * Devolve: texto (ex.: "48 KB" ou "1,5 MB").
 */
function formatar_tamanho(tamanho_em_bytes) {
  // 1 KB = 1024 bytes; arredonda e garante pelo menos 1 KB.
  const tamanho_em_kb = Math.max(1, Math.round(tamanho_em_bytes / 1024));
  // Arquivos menores que 1 MB aparecem em KB.
  if (tamanho_em_kb < 1024) {
    return tamanho_em_kb + " KB";
  }
  // Arquivos maiores aparecem em MB, com uma casa decimal e vírgula brasileira.
  const tamanho_em_mb = (tamanho_em_kb / 1024).toFixed(1).replace(".", ",");
  return tamanho_em_mb + " MB";
}

/**
 * Descobre o formato de um arquivo pela extensão do nome.
 *
 * Recebe: nome_do_arquivo — ex.: "relacao.PDF".
 * Devolve: o formato — "planilha", "texto", "documento", "pdf" ou "imagem".
 * Exemplo: descobrir_formato("lista.jpeg") devolve "imagem".
 */
function descobrir_formato(nome_do_arquivo) {
  // Posição do último ponto do nome (onde começa a extensão).
  const posicao_do_ponto = nome_do_arquivo.lastIndexOf(".");
  // Sem ponto no nome: não há extensão para olhar.
  if (posicao_do_ponto === -1) {
    return "documento";
  }
  // Extensão em minúsculas (".PDF" vira ".pdf").
  const extensao = nome_do_arquivo.slice(posicao_do_ponto).toLowerCase();
  // Procura em qual formato essa extensão está.
  for (const formato in EXTENSOES_POR_FORMATO) {
    if (EXTENSOES_POR_FORMATO[formato].includes(extensao)) {
      return formato;
    }
  }
  // Extensão desconhecida: tratada como documento (a IA tentaria ler mesmo assim).
  return "documento";
}

/**
 * Transforma a lista de arquivos do navegador numa lista simples de nome e tamanho.
 *
 * Recebe: lista_do_navegador — a lista que vem do campo de arquivo ou do "arrastar e soltar".
 * Devolve: lista de { nome, tamanho }.
 */
function listar_arquivos(lista_do_navegador) {
  // Lista que vai ser devolvida.
  const arquivos = [];
  // Copia nome e tamanho de cada arquivo.
  for (const arquivo of lista_do_navegador) {
    arquivos.push({ nome: arquivo.name, tamanho: arquivo.size });
  }
  return arquivos;
}

/**
 * Rola a conversa até a última mensagem, para a pessoa sempre ver a mais nova.
 */
function rolar_conversa_para_o_fim() {
  // A área da conversa.
  const conversa = document.getElementById("conversa-ia");
  // Leva a rolagem até o fim (scrollHeight é a altura total do conteúdo).
  conversa.scrollTop = conversa.scrollHeight;
}

// ===== Funções de tela: painel da IA =====

/**
 * Marca a etapa atual no alto do painel: as anteriores ficam verdes e a atual brilha.
 *
 * Recebe: numero_da_etapa_atual — de 1 a 4 (use 5 para marcar todas como concluídas).
 */
function marcar_etapa(numero_da_etapa_atual) {
  // As quatro etapas do painel.
  const etapas = document.querySelectorAll(".etapa-ia");
  // Passa por cada etapa decidindo a aparência dela.
  for (const etapa of etapas) {
    // Número desta etapa, lido do atributo data-numero-etapa do HTML.
    const numero_desta_etapa = Number(etapa.dataset.numeroEtapa);
    // Etapas antes da atual ficam como concluídas (verde).
    etapa.classList.toggle("etapa-ia-concluida", numero_desta_etapa < numero_da_etapa_atual);
    // Só a etapa atual fica ativa (na cor da marca, brilhando).
    etapa.classList.toggle("etapa-ia-ativa", numero_desta_etapa === numero_da_etapa_atual);
  }
}

/**
 * Mostra os três pontinhos de "pensando" por um instante e depois os remove.
 */
async function mostrar_ia_pensando(id_da_conversa = "conversa-ia") {
  // Copia o molde dos três pontinhos.
  const copia_do_modelo = document.getElementById("modelo-digitando").content.cloneNode(true);
  // Pega o bloco principal da cópia (para poder removê-lo depois).
  const bloco_pensando = copia_do_modelo.querySelector(".mensagem-ia");
  // Coloca os pontinhos na conversa escolhida e rola até eles.
  document.getElementById(id_da_conversa).appendChild(bloco_pensando);
  rolar_conversa_para_o_fim();
  // Deixa os pontinhos na tela pelo tempo definido.
  await esperar(TEMPO_PENSANDO);
  // Tira os pontinhos: a mensagem de verdade vai entrar no lugar.
  bloco_pensando.remove();
}

/**
 * Escreve uma mensagem da IA na conversa, palavra por palavra (como se estivesse digitando).
 *
 * Recebe: texto — a mensagem; tipo — "normal", "alerta" (amarela) ou "sucesso" (verde);
 *         id_da_conversa — onde escrever (sem informar, na conversa principal do painel da IA;
 *         o js/orientar.js escreve na conversa do bloco "Ajude a IA a acertar").
 * Exemplo: await escrever_mensagem("Vou começar a leitura.", "normal")
 */
async function escrever_mensagem(texto, tipo, id_da_conversa = "conversa-ia") {
  // Copia o molde de mensagem.
  const copia_do_modelo = document.getElementById("modelo-mensagem-ia").content.cloneNode(true);
  // Bloco inteiro da mensagem (avatar + balão + hora).
  const bloco_mensagem = copia_do_modelo.querySelector(".mensagem-ia");
  // Balão onde o texto vai aparecendo.
  const balao = copia_do_modelo.querySelector(".mensagem-ia-balao");
  // Linha pequena da hora, embaixo do balão.
  const campo_hora = copia_do_modelo.querySelector(".mensagem-ia-hora");

  // Mensagens de alerta e de sucesso ganham cor própria.
  if (tipo !== "normal") {
    bloco_mensagem.classList.add("mensagem-ia-" + tipo);
  }
  // Liga o cursor piscando no fim do texto enquanto a IA "escreve".
  balao.classList.add("escrevendo");
  // Coloca a mensagem (ainda vazia) na conversa escolhida.
  document.getElementById(id_da_conversa).appendChild(bloco_mensagem);

  // Separa o texto em palavras, usando o espaço como divisor.
  const palavras = texto.split(" ");
  // Escreve uma palavra de cada vez.
  for (let posicao = 0; posicao < palavras.length; posicao = posicao + 1) {
    // Da segunda palavra em diante, põe um espaço antes.
    if (posicao > 0) {
      balao.textContent = balao.textContent + " ";
    }
    // Acrescenta a palavra.
    balao.textContent = balao.textContent + palavras[posicao];
    // Mantém a última linha à vista.
    rolar_conversa_para_o_fim();
    // Pausa curta antes da próxima palavra.
    await esperar(TEMPO_POR_PALAVRA);
  }

  // Terminou de escrever: desliga o cursor e mostra a hora.
  balao.classList.remove("escrevendo");
  campo_hora.textContent = hora_atual();
}

/**
 * Ajusta o lado direito do painel para o envio atual: ícone, nome, títulos e legendas.
 */
function preparar_painel_para_o_envio() {
  // Cenário do envio (tabela ou conversa).
  const cenario = envio_atual.cenario;
  // Apresentação do formato (ícone e rótulo).
  const apresentacao = APRESENTACAO_DOS_FORMATOS[envio_atual.formato];
  // Campo com o nome do que foi enviado.
  const campo_nome = document.getElementById("arquivo-nome");

  // Troca o ícone do cartão pelo ícone do formato (ex.: PDF, imagem).
  document.getElementById("icone-do-arquivo").setAttribute("href", apresentacao.icone);
  // Escreve o nome; o title mostra todos os nomes ao passar o mouse (a tela corta nomes longos).
  campo_nome.textContent = envio_atual.nome_exibido;
  campo_nome.title = envio_atual.todos_os_nomes;
  // Títulos e legendas mudam conforme o cenário (linhas de arquivo × pessoas na conversa).
  document.getElementById("titulo-cartao-contadores").textContent = cenario.titulo_dos_contadores;
  document.getElementById("legenda-lidas").textContent = cenario.legenda_lidas;
  document.getElementById("legenda-prontas").textContent = cenario.legenda_prontas;
  document.getElementById("titulo-cartao-campos").textContent = cenario.titulo_dos_campos;
  document.getElementById("total-campos").textContent = "0 de " + cenario.campos.length;
}

// ===== Ações do roteiro (o que muda no lado direito da tela) =====

/**
 * Preenche o cartão do envio com o formato, o tamanho e o que foi encontrado.
 */
async function mostrar_detalhes_do_envio() {
  // Rótulo do formato (ex.: "PDF").
  const rotulo_do_formato = APRESENTACAO_DOS_FORMATOS[envio_atual.formato].rotulo;
  // Escreve os detalhes embaixo do nome.
  document.getElementById("arquivo-detalhes").textContent =
    rotulo_do_formato + " · " + formatar_tamanho(envio_atual.tamanho_total) + " · " + envio_atual.cenario.detalhes_do_conteudo;
}

/**
 * Mostra o selo "Inclusão" no cartão do envio (tipo de envio definido automaticamente).
 */
async function mostrar_tipo_de_envio() {
  // Tira o "hidden" do selo, fazendo ele aparecer.
  document.getElementById("selo-tipo-envio").hidden = false;
}

/**
 * Mostra os campos sendo reconhecidos, um de cada vez, com o selo de confiança.
 */
async function reconhecer_campos() {
  // Lista onde os campos aparecem.
  const lista_de_campos = document.getElementById("lista-campos");
  // Selo que mostra quantos já foram vistos ("3 de 25").
  const selo_total = document.getElementById("total-campos");
  // Campos do cenário atual.
  const campos = envio_atual.cenario.campos;
  // Contador de campos já mostrados.
  let campos_mostrados = 0;

  // Um campo de cada vez, na ordem em que aparecem no arquivo.
  for (const campo of campos) {
    // Copia o molde de linha de campo.
    const copia_do_modelo = document.getElementById("modelo-campo").content.cloneNode(true);
    // Linha inteira (para marcar as ignoradas).
    const linha = copia_do_modelo.querySelector(".coluna-mapeada");
    // Selo de confiança da linha.
    const selo_confianca = copia_do_modelo.querySelector(".coluna-confianca");
    // Aparência do selo conforme a confiança deste campo.
    const aparencia = APARENCIA_DA_CONFIANCA[campo.confianca];

    // Preenche o que está no arquivo e o campo do banco.
    copia_do_modelo.querySelector(".coluna-arquivo").textContent = campo.no_arquivo;
    copia_do_modelo.querySelector(".coluna-banco").textContent = campo.campo_do_banco;
    // Preenche o selo com a cor e o texto da confiança.
    selo_confianca.classList.add(aparencia.classe_do_selo);
    selo_confianca.textContent = aparencia.texto_do_selo;
    // Informação ignorada fica mais apagada.
    if (campo.confianca === "ignorada") {
      linha.classList.add("coluna-ignorada");
    }

    // Coloca a linha na lista e rola até ela.
    lista_de_campos.appendChild(linha);
    lista_de_campos.scrollTop = lista_de_campos.scrollHeight;
    // Atualiza o selo do total.
    campos_mostrados = campos_mostrados + 1;
    selo_total.textContent = campos_mostrados + " de " + campos.length;
    // Pausa curta antes do próximo campo.
    await esperar(TEMPO_POR_CAMPO);
  }

  // No fim, o selo mostra o resumo do cenário.
  selo_total.textContent = envio_atual.cenario.resumo_dos_campos;
}

/**
 * Faz os contadores subirem, um registro por vez, separando os prontos dos que precisam de revisão.
 * Registro = uma linha da tabela ou um funcionário encontrado na conversa.
 */
async function conferir_registros() {
  // Cenário do envio.
  const cenario = envio_atual.cenario;
  // Os três números do cartão de contadores.
  const campo_lidas = document.getElementById("contador-lidas");
  const campo_prontas = document.getElementById("contador-prontas");
  const campo_revisar = document.getElementById("contador-revisar");
  // Contagens que vão subindo.
  let registros_prontos = 0;
  let registros_para_revisar = 0;

  // Confere do primeiro ao último registro.
  for (let numero_do_registro = 1; numero_do_registro <= cenario.total_de_registros; numero_do_registro = numero_do_registro + 1) {
    // Se o registro está na lista de problemas, vai para revisão; senão, está pronto.
    if (cenario.registros_com_ajuste.includes(numero_do_registro)) {
      registros_para_revisar = registros_para_revisar + 1;
    } else {
      registros_prontos = registros_prontos + 1;
    }
    // Mostra os números atualizados.
    campo_lidas.textContent = numero_do_registro;
    campo_prontas.textContent = registros_prontos;
    campo_revisar.textContent = registros_para_revisar;
    // Pausa antes do próximo registro.
    await esperar(cenario.tempo_por_registro);
  }
}

/**
 * Encerra a leitura: o painel fica "concluído" e o resultado do cenário aparece embaixo.
 */
async function mostrar_resultado() {
  // Todas as etapas ficam verdes.
  marcar_etapa(5);
  // O painel troca a borda animada pela verde e para a esfera.
  document.getElementById("painel-ia").classList.add("concluido");
  // Texto do status no alto do painel.
  document.getElementById("texto-status-ia").textContent = "Leitura concluída";
  // Mostra o bloco de resultado do cenário (tabela ou conversa).
  const bloco_resultado = document.getElementById(envio_atual.cenario.id_do_resultado);
  bloco_resultado.hidden = false;
  // Mostra, logo abaixo, o bloco "Ajude a IA a acertar" (js/orientar.js).
  preparar_ajude_a_ia();
  // Espera um instante e rola a página até o resultado, com movimento suave.
  await esperar(400);
  bloco_resultado.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Liga o nome de cada ação do roteiro à função que a executa.
const ACOES_DO_ROTEIRO = {
  mostrar_detalhes_do_envio: mostrar_detalhes_do_envio,
  mostrar_tipo_de_envio: mostrar_tipo_de_envio,
  reconhecer_campos: reconhecer_campos,
  conferir_registros: conferir_registros,
  mostrar_resultado: mostrar_resultado,
};

// ===== O roteiro inteiro =====

/**
 * Monta o roteiro do envio: duas mensagens do formato + a do tipo de envio + as do cenário.
 *
 * Devolve: a lista de passos, na ordem em que a IA vai falar.
 */
function montar_roteiro() {
  // As duas mensagens de abertura do formato (ex.: "Recebi o PDF...").
  const mensagens_do_formato = APRESENTACAO_DOS_FORMATOS[envio_atual.formato].mensagens;
  // Começo do roteiro, igual para todos os cenários.
  const inicio_do_roteiro = [
    { etapa: 1, tipo: "normal", texto: mensagens_do_formato[0], acao: "" },
    { etapa: 1, tipo: "normal", texto: mensagens_do_formato[1], acao: "mostrar_detalhes_do_envio" },
    MENSAGEM_DO_TIPO_DE_ENVIO,
  ];
  // Junta o começo com as mensagens do cenário.
  return inicio_do_roteiro.concat(envio_atual.cenario.mensagens);
}

/**
 * Executa o roteiro da IA do começo ao fim, um passo de cada vez.
 */
async function executar_roteiro_da_ia() {
  // Um passo de cada vez, na ordem do roteiro.
  for (const passo of montar_roteiro()) {
    // Marca a etapa deste passo no alto do painel.
    marcar_etapa(passo.etapa);
    // A IA "pensa" um pouco.
    await mostrar_ia_pensando();
    // Troca {arquivo} e {quantidade} pelos dados reais do envio.
    const texto_com_arquivo = passo.texto.replace("{arquivo}", envio_atual.nome_exibido);
    const texto_final = texto_com_arquivo.replace("{quantidade}", envio_atual.quantidade_de_arquivos);
    // Escreve a mensagem.
    await escrever_mensagem(texto_final, passo.tipo);
    // Se o passo tem uma ação na tela, executa e espera ela terminar.
    if (passo.acao !== "") {
      await ACOES_DO_ROTEIRO[passo.acao]();
    }
  }
}

/**
 * Registra o envio, troca a tela de envio pela da IA trabalhando e começa o roteiro.
 *
 * Recebe: arquivos — lista de { nome, tamanho };
 *         formato — "" para descobrir pela extensão, ou um formato fixo (usado pelos exemplos);
 *         nome_do_cenario — "tabela" ou "conversa".
 */
function iniciar_envio(arquivos, formato, nome_do_cenario) {
  // Se já existe um envio em andamento, não faz nada (evita duas leituras ao mesmo tempo).
  if (envio_atual !== null) {
    return;
  }

  // Soma o tamanho de todos os arquivos e junta os nomes numa frase só.
  let tamanho_total = 0;
  const nomes = [];
  for (const arquivo of arquivos) {
    tamanho_total = tamanho_total + arquivo.tamanho;
    nomes.push(arquivo.nome);
  }

  // Decide o formato: o informado, "varios" se veio mais de um arquivo, ou pela extensão.
  let formato_do_envio = formato;
  if (formato_do_envio === "" && arquivos.length > 1) {
    formato_do_envio = "varios";
  } else if (formato_do_envio === "") {
    formato_do_envio = descobrir_formato(arquivos[0].nome);
  }

  // Nome que aparece na tela: o do arquivo, ou "3 arquivos" quando são vários.
  let nome_exibido = arquivos[0].nome;
  if (arquivos.length > 1) {
    nome_exibido = arquivos.length + " arquivos";
  }

  // Guarda tudo sobre o envio num lugar só, para as outras funções usarem.
  envio_atual = {
    nome_exibido: nome_exibido,
    todos_os_nomes: nomes.join(", "),
    quantidade_de_arquivos: arquivos.length,
    tamanho_total: tamanho_total,
    formato: formato_do_envio,
    cenario: CENARIOS[nome_do_cenario],
  };

  // Números iniciais do resultado: total menos os que precisam de ajuste.
  quantidade_de_pendentes = envio_atual.cenario.registros_com_ajuste.length;
  quantidade_de_prontos = envio_atual.cenario.total_de_registros - quantidade_de_pendentes;

  // Esconde a área de envio, mostra o painel da IA e ajusta o lado direito.
  document.getElementById("etapa-envio").hidden = true;
  document.getElementById("etapa-leitura").hidden = false;
  preparar_painel_para_o_envio();
  // Começa o roteiro.
  executar_roteiro_da_ia();
}

// ===== Ajustes no resultado =====

/**
 * Atualiza o resumo do resultado (número, botão e nota) depois de um ajuste corrigido.
 */
function atualizar_resumo_do_resultado() {
  // Bloco de resultado do cenário atual (só ele está na tela).
  const bloco_resultado = document.getElementById(envio_atual.cenario.id_do_resultado);

  // Número grande de prontos.
  bloco_resultado.querySelector("[data-resultado-prontos]").textContent = quantidade_de_prontos;
  // Texto do botão que abre a conferência (o envio acontece no fim dela).
  bloco_resultado.querySelector("[data-botao-conferir]").textContent =
    "Conferir a lista (" + quantidade_de_prontos + ")";
  // Contadores do lado direito do painel, para ficarem iguais ao resumo.
  document.getElementById("contador-prontas").textContent = quantidade_de_prontos;
  document.getElementById("contador-revisar").textContent = quantidade_de_pendentes;

  // Nota embaixo do botão, conforme quantos ajustes ainda faltam.
  const nota = bloco_resultado.querySelector("[data-resultado-nota]");
  if (quantidade_de_pendentes === 0) {
    nota.textContent = "Tudo pronto! Nenhum ajuste pendente.";
  } else if (quantidade_de_pendentes === 1) {
    nota.textContent = "O 1 com ajuste pendente fica guardado até você corrigir.";
  } else {
    nota.textContent = "Os " + quantidade_de_pendentes + " com ajuste pendente ficam guardados até você corrigir.";
  }
}

/**
 * Marca um ajuste como corrigido (ao aceitar a sugestão ou salvar a correção).
 *
 * Recebe: botao_clicado — o botão "Aceitar sugestão" ou "Salvar".
 */
function resolver_ajuste(botao_clicado) {
  // Cartão do ajuste onde o botão está.
  const cartao_do_ajuste = botao_clicado.closest("[data-ajuste]");
  // Selo da situação ("CPF inválido", "Data no futuro"...).
  const selo_situacao = cartao_do_ajuste.querySelector("[data-situacao-ajuste]");

  // Visual de resolvido: faixa verde.
  cartao_do_ajuste.classList.add("ajuste-resolvido");
  // Selo passa de amarelo para verde, com o texto "Corrigido".
  selo_situacao.classList.replace("selo-atencao", "selo-sucesso");
  selo_situacao.textContent = "Corrigido";
  // Esconde os botões e o campo: não há mais o que fazer neste ajuste.
  cartao_do_ajuste.querySelector("[data-botoes-ajuste]").hidden = true;

  // Um a mais pronto, um a menos pendente.
  quantidade_de_prontos = quantidade_de_prontos + 1;
  quantidade_de_pendentes = quantidade_de_pendentes - 1;
  // Atualiza os números na tela.
  atualizar_resumo_do_resultado();
  // Se a conferência já está aberta, ela mostra a correção na hora (função do js/conferir.js).
  if (!document.getElementById("etapa-conferencia").hidden) {
    montar_tabela_da_conferencia();
  }
}

// ===== Preparação da tela =====

/**
 * Liga os botões e a área de arrastar às funções acima.
 * É chamada uma vez, quando a página termina de carregar.
 */
function preparar_tela_de_cadastro() {
  // Campo escondido que abre a janela de escolher arquivos.
  const campo_arquivo = document.getElementById("campo-arquivo");
  // Área de arrastar e soltar.
  const zona_envio = document.getElementById("zona-envio");

  // Quando a pessoa escolhe arquivos no computador, começa a leitura com eles.
  campo_arquivo.addEventListener("change", function () {
    // Só começa se pelo menos um arquivo foi escolhido.
    if (campo_arquivo.files.length === 0) {
      return;
    }
    // Com a página ligada à aplicação, o envio é de verdade (js/cadastrar_real.js); sem servidor, é a simulação.
    if (modo_de_verdade()) {
      enviar_arquivo_de_verdade(campo_arquivo.files);
      return;
    }
    iniciar_envio(listar_arquivos(campo_arquivo.files), "", "tabela");
  });

  // Botões de exemplo: cada um envia o exemplo do seu formato.
  const botoes_de_exemplo = document.querySelectorAll("[data-exemplo]");
  for (const botao of botoes_de_exemplo) {
    botao.addEventListener("click", function () {
      // Exemplo escolhido, pelo atributo data-exemplo do botão.
      const exemplo = EXEMPLOS[botao.dataset.exemplo];
      iniciar_envio(exemplo.arquivos, exemplo.formato, exemplo.cenario);
    });
  }

  // Arquivo passando por cima da área: destaca a área (e impede o navegador de abrir o arquivo).
  zona_envio.addEventListener("dragover", function (evento) {
    evento.preventDefault();
    zona_envio.classList.add("arrastando");
  });

  // Arquivo saiu de cima da área sem soltar: tira o destaque.
  zona_envio.addEventListener("dragleave", function () {
    zona_envio.classList.remove("arrastando");
  });

  // Arquivos soltos na área: tira o destaque e começa a leitura.
  zona_envio.addEventListener("drop", function (evento) {
    // Impede o navegador de abrir o arquivo numa aba nova.
    evento.preventDefault();
    zona_envio.classList.remove("arrastando");
    // Só começa se veio mesmo algum arquivo.
    if (evento.dataTransfer.files.length === 0) {
      return;
    }
    // Com a página ligada à aplicação, o envio é de verdade (js/cadastrar_real.js); sem servidor, é a simulação.
    if (modo_de_verdade()) {
      enviar_arquivo_de_verdade(evento.dataTransfer.files);
      return;
    }
    iniciar_envio(listar_arquivos(evento.dataTransfer.files), "", "tabela");
  });

  // Botões "Aceitar sugestão" e "Salvar" dos ajustes (dos dois cenários).
  const botoes_de_resolver = document.querySelectorAll("[data-resolver-ajuste]");
  for (const botao of botoes_de_resolver) {
    botao.addEventListener("click", function () {
      resolver_ajuste(botao);
    });
  }
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_cadastro);
