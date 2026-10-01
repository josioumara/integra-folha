/*
  conversas.js — as conversas de ajuda entre as empresas e o especialista do banco (os dois portais usam).

  Para que serve: guarda e entrega as conversas do "Posso ajudar?". A empresa escreve pelo Portal Empresa
  (js/ajuda_empresa.js) e o especialista responde pelo Portal Interno, na aba "Conversa" da ficha de cada empresa
  (js/banco_empresas_conversa.js). É uma conversa ENTRE PESSOAS: nenhuma IA responde por ninguém.
  No Portal Interno, os números das conversas (a bolinha ao lado de "Empresas", no menu, e o cartão do Início) são do
  js/sinal_de_conversas.js. Logo depois de gravar uma mensagem ou uma marcação, este arquivo avisa com o evento
  "conversa-gravada", e o sinal é buscado de novo na hora.

  Onde as conversas ficam neste rascunho: no próprio navegador ("localStorage", uma gavetinha que cada
  site tem no navegador e que sobrevive a recarregar a página). Assim, uma mensagem mandada na tela da
  empresa aparece na tela do banco, no mesmo computador. Se o navegador não deixar guardar (janela
  anônima, por exemplo), tudo funciona igual, só que se perde ao recarregar.
  Com a página ligada à aplicação (ADR-69), as conversas ficam no banco de dados (services/mensagens.py): a
  empresa lê e escreve só a própria conversa, o banco vê todas; cada mensagem registra quem escreveu e quando.
  A tela busca as conversas de novo a cada 15 segundos, para a resposta do outro lado aparecer sozinha.

  Dados: 100% fictícios.
*/

// Nome da "gaveta" no navegador onde as conversas ficam guardadas.
const CHAVE_DAS_CONVERSAS = "integra_folha_conversas_v1";
// De quanto em quanto tempo a tela busca as conversas de novo no servidor (em milissegundos).
const INTERVALO_DE_ATUALIZACAO = 15000;
// Com servidor: as conversas vindas da aplicação e o perfil de quem entrou (null = sem servidor, usa o navegador).
let conversas_do_servidor = null;
let perfil_das_conversas = null;

// Conversas de exemplo, usadas na primeira vez (ou se a gaveta estiver vazia).
const CONVERSAS_INICIAIS = [
  {
    id: "aurora",
    empresa: "Aurora Alimentos",
    resolvida: false,
    mensagens: [
      { de: "empresa", autor: "Marina Costa", quando: "Hoje, 08h15", contexto: "Cadastrar funcionários", texto: "Bom dia! Uma funcionária está afastada pelo INSS desde agosto. Ela entra no arquivo de inclusão?" },
    ],
  },
  {
    id: "horizonte",
    empresa: "Horizonte Logística",
    resolvida: false,
    mensagens: [
      { de: "empresa", autor: "Sérgio Matos", quando: "Ontem, 17h40", contexto: "Cadastrar funcionários · leitura em andamento", texto: "O Agente Interpretador deixou de fora a coluna Turno. Preciso mandar essa informação para o banco?" },
    ],
  },
  {
    id: "brisa",
    empresa: "Brisa Tecnologia",
    resolvida: true,
    mensagens: [
      { de: "empresa", autor: "Helena Duarte", quando: "21/09, 09h02", contexto: "Acompanhar cadastros", texto: "Consigo baixar a lista de quem já foi cadastrado?" },
      { de: "banco", autor: "Rafael Lima", quando: "21/09, 09h20", contexto: "", texto: "Consegue, sim: em Acompanhar cadastros, na parte Funcionários, use o botão \"Baixar lista\". O arquivo abre direto no Excel." },
      { de: "empresa", autor: "Helena Duarte", quando: "21/09, 09h31", contexto: "", texto: "Achei. Obrigada!" },
    ],
  },
];

/**
 * Lê as conversas guardadas no navegador. Se não houver nada (ou se o navegador não deixar ler),
 * devolve uma cópia das conversas de exemplo.
 *
 * Recebe: nada. Devolve: a lista de conversas.
 */
function ler_conversas() {
  // Com servidor: uma cópia das conversas vindas da aplicação.
  if (conversas_do_servidor !== null) {
    return JSON.parse(JSON.stringify(conversas_do_servidor));
  }
  // try/catch: se o navegador bloquear a gaveta, o erro é "pego" e a tela segue com os exemplos.
  try {
    // O texto guardado (ou null, se nunca foi guardado).
    const texto_guardado = window.localStorage.getItem(CHAVE_DAS_CONVERSAS);
    // Se havia algo, transforma o texto de volta em lista (JSON é o formato de texto dos dados).
    if (texto_guardado) {
      return JSON.parse(texto_guardado);
    }
  } catch (erro) {
    // Sem gaveta: segue para os exemplos.
  }
  // Cópia dos exemplos (copiar evita mexer na lista original por engano).
  return JSON.parse(JSON.stringify(CONVERSAS_INICIAIS));
}

/**
 * Guarda as conversas no navegador.
 *
 * Recebe: conversas — a lista inteira. Devolve: nada.
 */
function guardar_conversas(conversas) {
  // try/catch: se o navegador não deixar guardar, a conversa só não sobrevive a recarregar a página.
  try {
    // Transforma a lista em texto e guarda na gaveta.
    window.localStorage.setItem(CHAVE_DAS_CONVERSAS, JSON.stringify(conversas));
  } catch (erro) {
    // Sem gaveta: nada a fazer.
  }
}

/**
 * Procura a conversa de uma empresa.
 *
 * Recebe: conversas — a lista; id — ex.: "aurora". Devolve: a conversa, ou null.
 */
function achar_conversa(conversas, id) {
  // Olha conversa por conversa.
  for (const conversa of conversas) {
    // Achou: devolve.
    if (conversa.id === id) {
      return conversa;
    }
  }
  // Não achou.
  return null;
}

/**
 * Verdadeiro se a conversa espera resposta do banco: não está resolvida e a última mensagem é da empresa.
 *
 * Recebe: conversa. Devolve: true ou false.
 */
function conversa_espera_o_banco(conversa) {
  // Resolvida não espera ninguém.
  if (conversa.resolvida) {
    return false;
  }
  // Conversa ainda sem mensagem (a empresa ainda não escreveu) também não espera ninguém.
  if (conversa.mensagens.length === 0) {
    return false;
  }
  // A última mensagem da conversa.
  const ultima = conversa.mensagens[conversa.mensagens.length - 1];
  // Espera o banco se quem falou por último foi a empresa.
  return ultima.de === "empresa";
}

/**
 * A conversa em que uma mensagem vai entrar: a que já existe ou, quando o especialista começa a conversa com uma
 * empresa que ainda não escreveu, uma nova e vazia, que entra na lista.
 *
 * Recebe: conversas — a lista; id — a empresa; nome_da_empresa — o nome, usado só na conversa nova.
 * Devolve: a conversa. Exemplo: a Vale Verde nunca escreveu → {id: "EMP004", empresa: "Vale Verde...", mensagens: []}.
 */
function conversa_para_escrever(conversas, id, nome_da_empresa) {
  // A conversa que já existe.
  const conversa = achar_conversa(conversas, id);
  if (conversa) {
    return conversa;
  }
  // Ainda não existe: começa uma, vazia e aberta, e a põe na lista.
  const conversa_nova = { id: id, empresa: nome_da_empresa, resolvida: false, mensagens: [] };
  conversas.push(conversa_nova);
  // Devolve a conversa nova.
  return conversa_nova;
}

/**
 * Hora de agora no formato das mensagens ("Hoje, 10h05").
 *
 * Recebe: nada. Devolve: o texto.
 */
function hora_de_agora() {
  // Data e hora do computador.
  const agora = new Date();
  // Hora e minuto com dois dígitos.
  const hora = String(agora.getHours()).padStart(2, "0");
  const minuto = String(agora.getMinutes()).padStart(2, "0");
  // Junta no formato das mensagens.
  return "Hoje, " + hora + "h" + minuto;
}

/**
 * Acrescenta uma mensagem a uma conversa e guarda tudo.
 *
 * Recebe: id — a conversa; mensagem — { de, autor, contexto, texto } (a hora é posta aqui); nome_da_empresa — usado
 * só quando a conversa ainda não existe (o especialista começando a conversa; a empresa sempre tem a dela).
 * Devolve: a lista de conversas atualizada.
 */
function acrescentar_mensagem(id, mensagem, nome_da_empresa) {
  // Com servidor: mostra na hora e grava na aplicação (js abaixo, "Conversas no servidor").
  if (conversas_do_servidor !== null) {
    return acrescentar_mensagem_no_servidor(id, mensagem, nome_da_empresa);
  }
  // Lê o que está guardado agora (o outro portal pode ter escrito algo nesse meio-tempo).
  const conversas = ler_conversas();
  // A conversa da empresa (ou uma nova, se o especialista está começando a conversa).
  const conversa = conversa_para_escrever(conversas, id, nome_da_empresa);
  // Carimba a hora.
  mensagem.quando = hora_de_agora();
  // Acrescenta no fim da conversa.
  conversa.mensagens.push(mensagem);
  // Mensagem nova reabre a conversa, se ela estava resolvida.
  conversa.resolvida = false;
  // Guarda.
  guardar_conversas(conversas);
  // Devolve a lista atualizada.
  return conversas;
}

/**
 * Monta a bolha de uma mensagem (usada nos dois portais).
 *
 * Recebe: mensagem — { autor, quando, contexto, texto }; e_minha — true se foi quem está vendo que escreveu.
 * Devolve: o elemento pronto.
 * Exemplo: na tela da empresa, a mensagem da Marina é "minha" (à direita); na tela do banco, a do Rafael.
 */
function montar_bolha(mensagem, e_minha) {
  // A bolha: à direita e clara, na cor da marca, se é minha; à esquerda e cinza se é da outra pessoa.
  const bolha = document.createElement("div");
  bolha.className = e_minha ? "bolha bolha-minha" : "bolha";
  // Linha de cima: quem e quando.
  const quem = document.createElement("span");
  quem.className = "bolha-quem";
  quem.textContent = mensagem.autor + " · " + mensagem.quando;
  // O texto da mensagem (textContent: entra como texto puro, nunca como código).
  const texto = document.createElement("p");
  texto.className = "bolha-texto";
  texto.textContent = mensagem.texto;
  // Junta quem e texto.
  bolha.append(quem, texto);
  // Se a mensagem tem contexto (a tela de onde veio), mostra embaixo.
  if (mensagem.contexto) {
    const sobre = document.createElement("span");
    sobre.className = "bolha-sobre";
    sobre.textContent = "Sobre: " + mensagem.contexto;
    bolha.append(sobre);
  }
  // Devolve a bolha pronta.
  return bolha;
}

/**
 * O servidor não entregou as conversas: avisa as telas, para trocarem o exemplo pelo aviso (nunca o exemplo).
 *
 * Recebe: nada. Devolve: nada. Ex.: a aba Conversa da ficha da empresa, no banco, mostra "Não foi possível carregar".
 */
function avisar_conversas_indisponiveis() {
  // As telas que mostram as conversas trocam o exemplo pelo aviso.
  document.dispatchEvent(new Event("conversas-indisponiveis"));
}

/**
 * Marca uma conversa como resolvida (só o banco faz isso) e guarda.
 *
 * Recebe: id — a conversa. Devolve: nada.
 */
function marcar_conversa_resolvida(id) {
  // Com servidor: grava na aplicação.
  if (conversas_do_servidor !== null) {
    resolver_conversa_no_servidor(id);
    return;
  }
  const conversas = ler_conversas();
  achar_conversa(conversas, id).resolvida = true;
  guardar_conversas(conversas);
}

/**
 * A conversa da empresa de quem está vendo o Portal Empresa.
 *
 * Recebe: id_de_exemplo — a conversa usada sem servidor (ex.: "aurora"). Devolve: a conversa, ou null.
 * Com servidor, a aplicação devolve uma conversa só: a da empresa de quem entrou.
 */
function conversa_da_empresa_logada(id_de_exemplo) {
  if (conversas_do_servidor !== null) {
    return ler_conversas()[0];
  }
  return achar_conversa(ler_conversas(), id_de_exemplo);
}

// ===== Conversas no servidor (com a página ligada à aplicação) =====

/**
 * Escreve a data e a hora de uma mensagem gravada no jeito curto das bolhas ("24/09, 10h05").
 *
 * Recebe: texto — data e hora do servidor. Devolve: o texto curto.
 */
function quando_da_mensagem(texto) {
  const momento = new Date(texto);
  const dia_e_mes = momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const hora = String(momento.getHours()).padStart(2, "0");
  const minuto = String(momento.getMinutes()).padStart(2, "0");
  return dia_e_mes + ", " + hora + "h" + minuto;
}

/**
 * Busca as conversas na aplicação (a da empresa, ou todas, para o banco) e avisa as telas para redesenhar.
 *
 * Recebe: nada. Devolve: nada. Sem servidor ou sem resposta, as conversas continuam no navegador.
 */
async function carregar_conversas_do_servidor() {
  // Qual endereço, conforme o perfil: a empresa lê a própria conversa; o banco, todas.
  let endereco = "/api/banco/conversas";
  if (perfil_das_conversas === "EMPRESA") {
    endereco = "/api/empresa/conversa";
  }
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch(endereco);
    // Recusado ou com erro: avisa que as conversas não chegaram (sem deixar o exemplo à mostra).
    if (!resposta.ok) {
      avisar_conversas_indisponiveis();
      return;
    }
    let conversas = await resposta.json();
    // A empresa recebe uma conversa só: vira uma lista de uma, como a do banco.
    if (perfil_das_conversas === "EMPRESA") {
      conversas = [conversas];
    }
    // A hora de cada mensagem no jeito das bolhas.
    for (const conversa of conversas) {
      for (const mensagem of conversa.mensagens) {
        mensagem.quando = quando_da_mensagem(mensagem.quando);
      }
    }
    conversas_do_servidor = conversas;
  } catch (erro) {
    // Servidor fora do ar: avisa que as conversas não chegaram (sem deixar o exemplo à mostra).
    avisar_conversas_indisponiveis();
    return;
  }
  // Avisa as telas (a ajuda da empresa e a aba Conversa da ficha da empresa, no banco).
  document.dispatchEvent(new Event("conversas-carregadas"));
}

/**
 * Uma mensagem ou uma marcação acabou de ser gravada: avisa as outras partes da tela e busca as conversas de novo.
 *
 * Recebe: nada. Devolve: a busca das conversas (uma promessa). O aviso "conversa-gravada" faz o sinal das conversas
 * abertas (js/sinal_de_conversas.js) ser buscado na hora, sem esperar a próxima volta de 15 segundos.
 */
function depois_de_gravar_na_conversa() {
  // Avisa: o sinal das conversas abertas mudou.
  document.dispatchEvent(new Event("conversa-gravada"));
  // Busca as conversas de novo (a hora e o autor reais da mensagem gravada).
  return carregar_conversas_do_servidor();
}

/**
 * Mostra a mensagem na hora e grava na aplicação; depois busca as conversas de novo (com a hora e o autor reais).
 *
 * Recebe: id — a conversa (o banco precisa; a empresa escreve sempre na própria); mensagem; nome_da_empresa — usado
 * só quando o especialista começa a conversa. Devolve: as conversas.
 */
function acrescentar_mensagem_no_servidor(id, mensagem, nome_da_empresa) {
  // Mostra na hora: acrescenta na cópia local enquanto o servidor grava (numa conversa nova, se ainda não existe).
  const conversa = conversa_para_escrever(conversas_do_servidor, id, nome_da_empresa);
  mensagem.quando = hora_de_agora();
  conversa.mensagens.push(mensagem);
  conversa.resolvida = false;
  // Grava: a empresa na própria conversa; o banco na conversa aberta.
  let endereco = "/api/banco/conversas/" + encodeURIComponent(id);
  if (perfil_das_conversas === "EMPRESA") {
    endereco = "/api/empresa/conversa";
  }
  fetch(endereco, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texto: mensagem.texto, contexto: mensagem.contexto }),
  }).then(depois_de_gravar_na_conversa);
  return ler_conversas();
}

/**
 * Marca a conversa como resolvida na aplicação (só o banco) e busca as conversas de novo.
 *
 * Recebe: id — a conversa. Devolve: nada.
 */
function resolver_conversa_no_servidor(id) {
  achar_conversa(conversas_do_servidor, id).resolvida = true;
  fetch("/api/banco/conversas/" + encodeURIComponent(id) + "/resolver", { method: "POST" }).then(depois_de_gravar_na_conversa);
}

/**
 * Liga as conversas no servidor: descobre quem entrou, busca as conversas e atualiza de tempos em tempos.
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: fica o navegador.
 */
async function ligar_conversas_no_servidor() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // try/catch: servidor fora do ar não quebra a tela.
  try {
    const resposta = await fetch("/api/eu");
    // Sem saber quem entrou, não há conversas: avisa, para não ficar o exemplo à mostra.
    if (!resposta.ok) {
      avisar_conversas_indisponiveis();
      return;
    }
    perfil_das_conversas = (await resposta.json()).perfil;
  } catch (erro) {
    // Servidor fora do ar: avisa, para não ficar o exemplo à mostra.
    avisar_conversas_indisponiveis();
    return;
  }
  // Só a empresa e o banco conversam.
  if (perfil_das_conversas !== "EMPRESA" && perfil_das_conversas !== "BANCO") {
    return;
  }
  await carregar_conversas_do_servidor();
  // Busca de novo de tempos em tempos: a resposta do outro lado aparece sem recarregar a página.
  setInterval(carregar_conversas_do_servidor, INTERVALO_DE_ATUALIZACAO);
}

// Quando o HTML terminar de carregar, com servidor, passa a usar as conversas gravadas na aplicação.
document.addEventListener("DOMContentLoaded", ligar_conversas_no_servidor);
