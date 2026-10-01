/*
  endomarketing_real.js — a aba "Materiais para divulgar" com os materiais publicados DE VERDADE (ADR-115).

  Para que serve: quando a página é servida pela aplicação, busca os materiais que o Santander publicou para a
  empresa de quem entrou e os entrega ao js/endomarketing.js, que desenha a lista:
    - GET /api/empresa/endomarketing → só os materiais PUBLICADOS da empresa da sessão, do mais recente ao mais
      antigo (rascunhos, descartados e retirados nunca chegam aqui);
    - "Baixar arte" → GET /api/empresa/endomarketing/{material_id}/arte (a imagem PNG que o banco publicou).
  O texto para copiar ou baixar é montado no navegador, a partir do título e dos blocos (sem rota própria).
  Servidor fora do ar ou com erro: a lista fica vazia e aparece uma mensagem amigável (nunca os exemplos).
  Enquanto a resposta não chega, a lista e o resumo são barras cinza de "carregando" (marcados no HTML com
  data-aguarda-bloco e data-aguarda-dado; js/carregando_dados.js); liberar_espera_dos_materiais() as tira, no
  sucesso e no erro.
  Aberta sem servidor (dois cliques), a página continua com os materiais de exemplo do js/endomarketing.js.
*/

// Verdadeiro quando a página está ligada à aplicação (o js/endomarketing.js olha isto em "Baixar arte").
let endomarketing_real_ligado = false;

// A mensagem para quando o servidor não responde ou responde com erro.
const MENSAGEM_SEM_SERVIDOR = "Não conseguimos carregar os materiais agora. Tente de novo em alguns minutos; " +
  "se continuar, fale com o seu especialista.";
// A mensagem para quando a sessão terminou (401).
const MENSAGEM_SESSAO_TERMINADA = "A sua sessão terminou. Entre de novo para ver os materiais.";
// A mensagem para quando a arte não pôde ser baixada.
const MENSAGEM_ARTE_INDISPONIVEL = "A arte deste material não está disponível agora. Tente de novo em alguns minutos.";

/**
 * Diz se a tela está ligada à aplicação (materiais de verdade).
 *
 * Recebe: nada. Devolve: true ou false.
 */
function modo_real_do_endomarketing() {
  return endomarketing_real_ligado;
}

/**
 * Busca os materiais publicados para a empresa de quem entrou.
 *
 * Recebe: nada.
 * Devolve: {ok, situacao, materiais} — ok diz se deu certo; situacao é o código HTTP (0 sem conexão);
 *          materiais é a lista da API (vazia em erro).
 */
async function buscar_materiais_publicados() {
  // try/catch: servidor fora do ar, ou resposta que não é JSON, vira um erro com mensagem clara.
  try {
    const resposta = await fetch("/api/empresa/endomarketing");
    // Resposta de erro: não lê o corpo, só guarda o código.
    if (!resposta.ok) {
      return { ok: false, situacao: resposta.status, materiais: [] };
    }
    const materiais = await resposta.json();
    return { ok: true, situacao: resposta.status, materiais: materiais };
  } catch (erro) {
    return { ok: false, situacao: 0, materiais: [] };
  }
}

/**
 * Mostra a mensagem de erro no lugar da lista (e esconde o aviso de lista vazia, que não se aplica).
 *
 * Recebe: situacao — o código HTTP da resposta (0 sem conexão). Devolve: nada.
 */
function mostrar_erro_dos_materiais(situacao) {
  // Sessão terminada tem uma mensagem própria; o resto, a mensagem geral.
  let mensagem = MENSAGEM_SEM_SERVIDOR;
  if (situacao === 401) {
    mensagem = MENSAGEM_SESSAO_TERMINADA;
  }
  const aviso_de_erro = document.querySelector("[data-erro-materiais]");
  aviso_de_erro.textContent = mensagem;
  aviso_de_erro.hidden = false;
  // A lista não foi carregada: fica vazia (sem cartões pela metade) e sem o filtro por tipo.
  document.querySelector("[data-lista-materiais]").replaceChildren();
  document.querySelector("[data-filtros-tipo]").hidden = true;
  // Não dá para dizer que a lista está vazia, nem resumir quantos materiais há.
  document.querySelector("[data-sem-materiais]").hidden = true;
  document.querySelector("[data-resumo-materiais]").textContent = "";
}

/**
 * Tira as barras cinza de "carregando" da lista e do resumo (js/carregando_dados.js): a lista, o aviso de lista
 * vazia ou o aviso de erro já estão na tela.
 *
 * Recebe: nada. Devolve: nada.
 */
function liberar_espera_dos_materiais() {
  // A lista, marcada no HTML com data-aguarda-bloco.
  marcar_como_carregado(document.querySelector("[data-lista-materiais]"));
  // O resumo abaixo do título, marcado com data-aguarda-dado.
  marcar_como_carregado(document.querySelector("[data-resumo-materiais]"));
}

/**
 * O endereço da arte de um material na aplicação.
 *
 * Recebe: material. Devolve: o endereço. Ex.: "/api/empresa/endomarketing/a1b2c3d4e5/arte".
 */
function endereco_da_arte(material) {
  // encodeURIComponent: o id entra no endereço sem quebrar a rota.
  return "/api/empresa/endomarketing/" + encodeURIComponent(material.material_id) + "/arte";
}

/**
 * Baixa a arte (PNG) publicada pelo banco. Busca a imagem antes, para avisar no cartão se ela não vier
 * (em vez de o navegador salvar uma página de erro com nome de imagem).
 *
 * Recebe: material; cartao — o cartão do material (para o recado). Devolve: nada.
 */
async function baixar_arte_de_verdade(material, cartao) {
  // try/catch: sem conexão vira o recado no cartão.
  try {
    const resposta = await fetch(endereco_da_arte(material));
    // Sem arte (404) ou outro erro: avisa no cartão.
    if (!resposta.ok) {
      mostrar_recado_no_cartao(cartao, MENSAGEM_ARTE_INDISPONIVEL);
      return;
    }
    // A imagem chega como um arquivo na memória (Blob) e é salva com o nome do material.
    const imagem = await resposta.blob();
    baixar_arquivo(imagem, nome_do_arquivo(material, "png"));
  } catch (erro) {
    mostrar_recado_no_cartao(cartao, MENSAGEM_ARTE_INDISPONIVEL);
  }
}

/**
 * Liga o modo real: busca os materiais publicados e os entrega à lista (ou mostra o erro).
 *
 * Recebe: nada. Devolve: nada. Página aberta como arquivo: ficam os exemplos.
 */
async function ligar_endomarketing_real() {
  // Aberta como arquivo: não há servidor.
  if (pagina_aberta_como_arquivo()) {
    return;
  }
  endomarketing_real_ligado = true;
  const resultado = await buscar_materiais_publicados();
  // Erro: a mensagem amigável no lugar da lista (e as barras cinza saem).
  if (!resultado.ok) {
    mostrar_erro_dos_materiais(resultado.situacao);
    liberar_espera_dos_materiais();
    return;
  }
  // try/catch: uma lista que a tela não consegue desenhar vira a mensagem de erro (a tela nunca fica cinza para
  // sempre); o erro segue adiante ("throw") para continuar aparecendo no console e nos roteiros de clique.
  try {
    // Deu certo: a lista (vazia mostra o aviso "O Santander ainda não publicou materiais...").
    mostrar_materiais(resultado.materiais);
  } catch (erro) {
    mostrar_erro_dos_materiais(0);
    liberar_espera_dos_materiais();
    throw erro;
  }
  // A lista está pronta: as barras cinza saem.
  liberar_espera_dos_materiais();
}

// Quando o HTML terminar de carregar, liga o modo real (se houver servidor).
document.addEventListener("DOMContentLoaded", ligar_endomarketing_real);
