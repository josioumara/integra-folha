/*
  kit_da_marca.js — o kit de marca dentro da KB "Kit da marca".

  Para que serve: a KB "Kit da marca" de cada empresa é a FONTE ÚNICA do kit: a escolha entre o
  próprio e o padrão, as cores e o logo. O cadastro da empresa só guarda uma cópia, que o servidor grava ao publicar
  ou retirar a KB. Este arquivo cuida do kit nas telas das KBs (a aba Endomarketing do Portal Interno):
    1. as cores: as amostras (círculos coloridos) no editor, na janela da KB e no "Kit em uso" da guia do material;
    2. o logo no editor da KB (só no kit de uma empresa: o kit padrão do Santander não leva logo): a prévia, a
       conferência do arquivo na hora (PNG ou JPEG de verdade, até 500 KB) e o "Tirar o logo". O logo vai para a
       versão que o "Salvar rascunho" grava (POST /api/banco/kbs-endomarketing/{kb_id}/versoes/{versao}/logo);
    3. na janela de uma KB de kit: as cores e o logo daquela versão.
  Quem chama: o js/banco_beneficios.js (o editor e a janela) e o js/banco_endomarketing.js (o "Kit em uso"). Usa do
  js/banco_beneficios.js: estado_das_kbs, ENDERECO_DAS_KBS, pedir_as_kbs, texto_do_erro_das_kbs,
  criar_elemento_das_kbs e dono_e_empresa.

  Por que a prévia do editor é um desenho (<canvas>), e não uma imagem (<img>): a política de conteúdo do site (a CSP,
  em api/principal.py) só deixa uma imagem vir de um endereço do próprio site. O arquivo que a pessoa acabou de
  escolher ainda está só no computador dela e não tem esse endereço; desenhado no canvas, ele aparece sem endereço
  nenhum (o mesmo jeito da arte, no js/arte_do_material.js). Nada é enviado antes do "Salvar rascunho".
  Segurança: só uma cor no formato #rrggbb entra no estilo da página.
*/

// Uma cor no formato que a trava aceita: "#" e 6 letras ou números hexadecimais (ex.: "#1f7a4d")
const COR_EM_HEXADECIMAL = /^#[0-9a-fA-F]{6}$/;
// O maior logo aceito, em bytes (500 KB, o mesmo limite do servidor)
const LIMITE_DO_LOGO_EM_BYTES = 500 * 1024;
// O começo de todo PNG (8 bytes fixos) e de todo JPEG (3 bytes fixos): a "assinatura" do formato, a mesma que o
// servidor confere. Um arquivo de outro tipo renomeado para "logo.png" não começa assim.
const ASSINATURA_DO_PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const ASSINATURA_DO_JPEG = [0xff, 0xd8, 0xff];
// A regra e a gravidade do aviso da trava para o kit próprio sem logo (combinadas com o servidor)
const REGRA_DO_AVISO_DE_LOGO = "Logo";
const GRAVIDADE_DE_AVISO = "AVISO";
// O maior tamanho do desenho da prévia do logo, em pixels (o dobro do que aparece na tela, para ficar nítido)
const LARGURA_MAXIMA_DA_PREVIA = 480;
const ALTURA_MAXIMA_DA_PREVIA = 192;

// ---------------- 1. As cores ----------------

/**
 * As cores válidas de um texto como "#1f7a4d, #155535" (as que não estão no formato #rrggbb ficam de fora).
 *
 * Recebe: texto (pode ser vazio). Devolve: a lista. Exemplo: "#1f7a4d, azul, #155535" → ["#1f7a4d", "#155535"].
 */
function cores_validas(texto) {
  const cores = [];
  for (const pedaco of (texto || "").split(",")) {
    const cor = pedaco.trim();
    // Só entra a cor no formato que a arte entende; o resto a trava aponta
    if (COR_EM_HEXADECIMAL.test(cor)) {
      cores.push(cor);
    }
  }
  return cores;
}

/**
 * Desenha as amostras (círculos coloridos) das cores num elemento .amostras-cores.
 *
 * Recebe: elemento; cores — ex.: ["#1f7a4d", "#155535"]. Devolve: nada.
 * Só uma cor no formato #rrggbb vai para o estilo da página: um texto qualquer nunca vira outra coisa ali.
 */
function preencher_amostras_de_cor(elemento, cores) {
  elemento.replaceChildren();
  for (const cor of cores) {
    // Fora do formato: fica de fora
    if (!COR_EM_HEXADECIMAL.test(cor)) {
      continue;
    }
    const amostra = criar_elemento_das_kbs("span", "", "");
    amostra.style.background = cor;
    // Passando o mouse, a cor aparece escrita
    amostra.title = cor;
    elemento.append(amostra);
  }
}

/**
 * As amostras das cores digitadas no editor (a cada letra e quando o editor abre).
 */
function mostrar_amostras_do_editor() {
  const cores = cores_validas(document.querySelector('[data-editor-campo="cores"]').value);
  preencher_amostras_de_cor(document.querySelector("[data-amostras-do-editor]"), cores);
}

// ---------------- 2. O logo: o endereço, a busca, a conferência e o desenho da prévia ----------------

/**
 * O endereço do logo de uma versão da KB. Exemplo: ("EMP001-KIT-DA-MARCA", 3) →
 * "/api/banco/kbs-endomarketing/EMP001-KIT-DA-MARCA/versoes/3/logo".
 */
function endereco_do_logo_da_versao(kb_id, versao) {
  return ENDERECO_DAS_KBS + "/" + encodeURIComponent(kb_id) + "/versoes/" + versao + "/logo";
}

/**
 * Busca o logo de uma versão da KB, como arquivo na memória.
 *
 * Recebe: kb_id; versao. Devolve: a imagem (um Blob), ou null quando a versão não tem logo (404) ou o servidor não
 * responde. "no-store": o navegador não usa um logo guardado de antes (o de um rascunho pode ter mudado).
 */
async function buscar_logo_da_versao(kb_id, versao) {
  // try/catch: sem conexão, fica como "sem logo"
  try {
    const resposta = await fetch(endereco_do_logo_da_versao(kb_id, versao), { cache: "no-store" });
    if (!resposta.ok) {
      return null;
    }
    return await resposta.blob();
  } catch (erro) {
    return null;
  }
}

/**
 * Diz se os bytes começam pela assinatura dada.
 *
 * Recebe: bytes (Uint8Array); assinatura (lista de números). Devolve: true ou false.
 * Exemplo: os bytes de um PNG com ASSINATURA_DO_PNG → true; os de um texto → false.
 */
function comeca_com_a_assinatura(bytes, assinatura) {
  // Arquivo menor que a assinatura não pode ser a imagem
  if (bytes.length < assinatura.length) {
    return false;
  }
  // Compara byte a byte
  for (let posicao = 0; posicao < assinatura.length; posicao = posicao + 1) {
    if (bytes[posicao] !== assinatura[posicao]) {
      return false;
    }
  }
  return true;
}

/**
 * Lê a imagem do arquivo no formato que o canvas desenha (ImageBitmap).
 *
 * Recebe: arquivo — um File ou Blob. Devolve: a imagem, ou null se o navegador não conseguiu ler (arquivo estragado).
 */
async function ler_imagem(arquivo) {
  // try/catch: um arquivo com a assinatura certa, mas estragado no meio, não vira imagem
  try {
    return await createImageBitmap(arquivo);
  } catch (erro) {
    return null;
  }
}

/**
 * Confere o arquivo de logo escolhido antes de aceitá-lo: vazio, grande demais, que não é PNG nem JPEG de verdade, ou
 * que o navegador não consegue ler.
 *
 * Recebe: arquivo (File). Devolve: o texto do problema, ou "" quando está tudo certo.
 * Olha a assinatura (os primeiros bytes), como o servidor, que confere de novo ao receber.
 */
async function problema_do_arquivo_de_logo(arquivo) {
  if (arquivo.size === 0) {
    return "O arquivo do logo está vazio.";
  }
  if (arquivo.size > LIMITE_DO_LOGO_EM_BYTES) {
    return "O logo passou de 500 KB. Diminua a imagem e tente de novo.";
  }
  // Os 8 primeiros bytes do arquivo, lidos no próprio navegador (nada é enviado ainda)
  const inicio = new Uint8Array(await arquivo.slice(0, 8).arrayBuffer());
  const e_png = comeca_com_a_assinatura(inicio, ASSINATURA_DO_PNG);
  const e_jpeg = comeca_com_a_assinatura(inicio, ASSINATURA_DO_JPEG);
  if (!e_png && !e_jpeg) {
    return "O logo precisa ser uma imagem PNG ou JPEG (um arquivo de outro tipo renomeado não serve).";
  }
  // A assinatura está certa: confere se a imagem inteira se deixa ler
  const imagem = await ler_imagem(arquivo);
  if (!imagem) {
    return "Não foi possível ler esta imagem. Confira o arquivo do logo.";
  }
  imagem.close();
  return "";
}

/**
 * Desenha um logo que está na memória do navegador (o arquivo escolhido ou o logo buscado) na prévia do editor, um
 * <canvas>; sem logo, a prévia some.
 *
 * Recebe: tela — o <canvas>; arquivo — um File ou Blob, ou null. Devolve: nada (a leitura da imagem termina sozinha).
 * Cada desenho ganha um número: se outro for pedido enquanto a imagem é lida, só o último aparece.
 */
async function desenhar_logo_na_previa(tela, arquivo) {
  const este_desenho = Number(tela.dataset.desenho || "0") + 1;
  tela.dataset.desenho = String(este_desenho);
  // Sem logo: a prévia some
  if (!arquivo) {
    tela.hidden = true;
    return;
  }
  const imagem = await ler_imagem(arquivo);
  // Outro desenho foi pedido enquanto esta imagem era lida: este não vale mais
  if (tela.dataset.desenho !== String(este_desenho)) {
    return;
  }
  // O navegador não conseguiu ler: a prévia fica escondida
  if (!imagem) {
    tela.hidden = true;
    return;
  }
  // A escala que faz o logo caber no tamanho máximo, sem aumentar um logo pequeno
  const escala = Math.min(1, LARGURA_MAXIMA_DA_PREVIA / imagem.width, ALTURA_MAXIMA_DA_PREVIA / imagem.height);
  tela.width = Math.max(1, Math.round(imagem.width * escala));
  tela.height = Math.max(1, Math.round(imagem.height * escala));
  tela.getContext("2d").drawImage(imagem, 0, 0, tela.width, tela.height);
  // A imagem lida já foi desenhada: libera a memória dela
  imagem.close();
  tela.hidden = false;
}

// ---------------- 3. O logo no editor ----------------

/**
 * Diz se o editor está numa KB de kit de uma empresa: só ela leva logo (o kit padrão do Santander não leva).
 */
function editor_no_kit_de_empresa() {
  const tipo = document.querySelector('[data-editor-campo="tipo"]').value;
  const dono = document.querySelector('[data-editor-campo="dono"]').value;
  return tipo === "kit_da_marca" && dono_e_empresa(dono);
}

/**
 * Mostra ou esconde o bloco do logo no editor (só no kit de uma empresa).
 */
function mostrar_bloco_do_logo() {
  document.querySelector("[data-logo-do-editor]").hidden = !editor_no_kit_de_empresa();
}

/**
 * O número da última versão da KB (a mais nova, em qualquer situação). Exemplo: v1, v2 e v3 → 3.
 */
function ultima_versao_da_kb(kb) {
  let ultima = 0;
  for (const versao of kb.versoes) {
    ultima = Math.max(ultima, versao.versao);
  }
  return ultima;
}

/**
 * Prepara o logo do editor que está abrindo: a KB nova começa sem logo; a versão nova mostra o logo da versão de
 * partida (a que estava aberta na janela).
 *
 * Recebe: kb — a versão de partida (ou null numa KB nova). Devolve: nada (o logo chega sozinho, depois).
 * O que fica guardado em estado_das_kbs.logo_do_editor:
 *   imagem_base   — o logo da versão de partida (um Blob), ou null se ela não tem;
 *   arquivo_novo  — o arquivo escolhido agora (um File), que vai para a versão nova ao salvar, ou null;
 *   tirar         — true depois de "Tirar o logo": a versão nova vai sem logo;
 *   herda_da_base — true quando a versão de partida é a última: o servidor copia o logo dela para a versão nova;
 *   carregando    — a busca do logo da versão de partida, enquanto não termina (salvar espera por ela).
 */
function preparar_logo_no_editor(kb) {
  const logo = { imagem_base: null, arquivo_novo: null, tirar: false, herda_da_base: true, carregando: null };
  estado_das_kbs.logo_do_editor = logo;
  // Limpa o que ficou de um editor aberto antes
  document.querySelector("[data-arquivo-logo-do-editor]").value = "";
  mostrar_erro_do_logo_no_editor("");
  // Só a versão nova de uma KB de kit de empresa tem de onde vir um logo
  if (kb && kb.tipo === "kit_da_marca" && dono_e_empresa(kb.dono)) {
    logo.herda_da_base = kb.versao === ultima_versao_da_kb(kb);
    // O servidor diz se a versão tem logo (tem_logo): só então ele é buscado
    if (kb.tem_logo) {
      logo.carregando = carregar_logo_da_base(logo, kb);
    }
  }
  mostrar_logo_no_editor();
}

/**
 * Busca o logo da versão de partida e o mostra no editor.
 *
 * Recebe: logo — o estado do logo deste editor; kb — a versão de partida. Devolve: nada.
 */
async function carregar_logo_da_base(logo, kb) {
  logo.imagem_base = await buscar_logo_da_versao(kb.kb_id, kb.versao);
  logo.carregando = null;
  // O editor foi aberto de novo (para outra KB) enquanto o logo chegava: este logo não é mais o dele
  if (estado_das_kbs.logo_do_editor !== logo) {
    return;
  }
  mostrar_logo_no_editor();
}

/**
 * O logo que a versão nova vai ter, do jeito que o editor está agora: o arquivo escolhido; senão, o logo da versão
 * de partida (se a pessoa não o tirou); senão, nenhum.
 *
 * Recebe: nada. Devolve: um File, um Blob ou null.
 */
function logo_que_a_versao_nova_vai_ter() {
  const logo = estado_das_kbs.logo_do_editor;
  // Editor ainda não aberto: nenhum logo
  if (!logo) {
    return null;
  }
  if (logo.arquivo_novo) {
    return logo.arquivo_novo;
  }
  if (logo.imagem_base && !logo.tirar) {
    return logo.imagem_base;
  }
  return null;
}

/**
 * Atualiza, no editor, a prévia do logo, o botão "Tirar o logo" e o recado de quando não há logo.
 */
function mostrar_logo_no_editor() {
  const imagem = logo_que_a_versao_nova_vai_ter();
  desenhar_logo_na_previa(document.querySelector("[data-previa-logo-do-editor]"), imagem);
  // "Tirar o logo" só aparece quando há um logo à vista
  document.querySelector("[data-tirar-logo-do-editor]").hidden = !imagem;
  // Sem logo: o recado ("carregando" enquanto o logo da versão de partida não chega)
  const sem_logo = document.querySelector("[data-sem-logo-no-editor]");
  sem_logo.hidden = Boolean(imagem);
  sem_logo.textContent = "Nenhum logo nesta versão.";
  if (estado_das_kbs.logo_do_editor.carregando) {
    sem_logo.textContent = "Carregando o logo desta versão...";
  }
}

/**
 * Mostra o aviso de problema do logo no editor (texto vazio esconde o aviso).
 */
function mostrar_erro_do_logo_no_editor(texto) {
  const aviso = document.querySelector("[data-erro-logo-do-editor]");
  aviso.textContent = texto;
  aviso.hidden = !texto;
}

/**
 * A pessoa escolheu um arquivo de logo: confere e, se estiver certo, ele passa a ser o logo da versão nova.
 * Com problema, o aviso aparece e o logo de antes continua.
 */
async function escolher_arquivo_de_logo() {
  const campo = document.querySelector("[data-arquivo-logo-do-editor]");
  const arquivo = campo.files[0];
  // A pessoa fechou a escolha sem arquivo: nada muda
  if (!arquivo) {
    return;
  }
  const problema = await problema_do_arquivo_de_logo(arquivo);
  if (problema) {
    campo.value = "";
    mostrar_erro_do_logo_no_editor(problema);
    return;
  }
  estado_das_kbs.logo_do_editor.arquivo_novo = arquivo;
  mostrar_erro_do_logo_no_editor("");
  mostrar_logo_no_editor();
}

/**
 * "Tirar o logo": a versão nova vai sem logo (o arquivo escolhido, se havia, também sai).
 */
function tirar_logo_no_editor() {
  const logo = estado_das_kbs.logo_do_editor;
  logo.arquivo_novo = null;
  logo.tirar = true;
  document.querySelector("[data-arquivo-logo-do-editor]").value = "";
  mostrar_erro_do_logo_no_editor("");
  mostrar_logo_no_editor();
}

/**
 * Tira da lista de achados o aviso de "kit próprio sem logo" quando o editor tem um logo para mandar: a trava não vê
 * o arquivo antes de o rascunho ser salvo (ele vai logo depois).
 *
 * Recebe: achados — a lista da trava. Devolve: a lista para mostrar.
 */
function achados_para_o_editor(achados) {
  // Sem logo para mandar, os achados valem do jeito que vieram
  if (!editor_no_kit_de_empresa() || !logo_que_a_versao_nova_vai_ter()) {
    return achados;
  }
  const para_mostrar = [];
  for (const achado of achados) {
    const e_o_aviso_do_logo = achado.regra === REGRA_DO_AVISO_DE_LOGO && achado.gravidade === GRAVIDADE_DE_AVISO;
    if (!e_o_aviso_do_logo) {
      para_mostrar.push(achado);
    }
  }
  return para_mostrar;
}

/**
 * Depois de salvar o rascunho, deixa o logo da versão nova igual ao que o editor mostrava.
 *
 * Recebe: kb_id; versao — a versão que acabou de ser gravada. Devolve: "" (deu certo, ou nada a fazer) ou o motivo
 * da recusa do servidor.
 * O servidor já cria a versão nova com o logo da ÚLTIMA versão da KB. Então:
 *   - com arquivo escolhido: ele vai para a versão nova;
 *   - com "Tirar o logo": o logo herdado sai;
 *   - sem mudança, partindo da última versão: o logo herdado já é o certo;
 *   - sem mudança, partindo de outra versão (ex.: a publicada, com um rascunho mais novo): o herdado é o da última,
 *     e não o que a pessoa viu; o da versão de partida é gravado (ou o herdado sai, se ela não tinha logo).
 */
async function gravar_logo_na_versao_nova(kb_id, versao) {
  // Fora do kit de uma empresa, não há logo
  if (!editor_no_kit_de_empresa()) {
    return "";
  }
  const logo = estado_das_kbs.logo_do_editor;
  // Espera o logo da versão de partida chegar: sem ele, não se sabe o que a pessoa viu
  if (logo.carregando) {
    await logo.carregando;
  }
  const endereco = endereco_do_logo_da_versao(kb_id, versao);
  if (logo.arquivo_novo) {
    return enviar_logo_para_a_versao(endereco, logo.arquivo_novo);
  }
  if (logo.tirar) {
    return tirar_logo_da_versao(endereco);
  }
  if (logo.herda_da_base) {
    return "";
  }
  if (logo.imagem_base) {
    return enviar_logo_para_a_versao(endereco, logo.imagem_base);
  }
  return tirar_logo_da_versao(endereco);
}

/**
 * Manda um logo para uma versão da KB (multipart, com o arquivo no campo "arquivo").
 *
 * Recebe: endereco — o do logo da versão; imagem — um File ou um Blob. Devolve: "" ou o motivo da recusa.
 */
async function enviar_logo_para_a_versao(endereco, imagem) {
  // Um Blob (o logo buscado de outra versão) não tem nome: ganha um, com a extensão do tipo
  let nome_do_arquivo = imagem.name;
  if (!nome_do_arquivo && imagem.type === "image/jpeg") {
    nome_do_arquivo = "logo.jpg";
  } else if (!nome_do_arquivo) {
    nome_do_arquivo = "logo.png";
  }
  const formulario = new FormData();
  formulario.append("arquivo", imagem, nome_do_arquivo);
  // Sem "Content-Type": o navegador monta o multipart sozinho, com a separação certa
  const resposta = await pedir_as_kbs(endereco, { method: "POST", body: formulario });
  if (!resposta.ok) {
    return texto_do_erro_das_kbs(resposta.dados.detail);
  }
  return "";
}

/**
 * Tira o logo de uma versão da KB.
 *
 * Recebe: endereco — o do logo da versão. Devolve: "" (tirou, ou a versão já estava sem logo: 404) ou o motivo da
 * recusa do servidor.
 */
async function tirar_logo_da_versao(endereco) {
  // try/catch: sem conexão, o recado de sempre
  try {
    const resposta = await fetch(endereco, { method: "DELETE" });
    // 404: a versão já estava sem logo, que é o que se queria
    if (resposta.ok || resposta.status === 404) {
      return "";
    }
    const dados = await resposta.json();
    return texto_do_erro_das_kbs(dados.detail);
  } catch (erro) {
    return "Sem conexão com o servidor. Tente de novo.";
  }
}

// ---------------- 4. O kit na janela de uma KB ----------------

/**
 * Na janela de uma KB de kit: as amostras das cores e o logo da versão aberta (o logo, só no kit de uma empresa).
 *
 * Recebe: kb — a versão aberta (com tem_logo, que o servidor manda). Devolve: nada.
 * O logo vem do endereço do próprio site (a política de conteúdo aceita), com "?momento=" para o navegador buscar o
 * de agora, e não um guardado de antes (o logo de um rascunho pode ter mudado).
 */
function mostrar_kit_na_janela(kb) {
  const linha = document.querySelector("[data-kb-kit]");
  const imagem = document.querySelector("[data-kb-kit-logo]");
  const texto = document.querySelector("[data-kb-kit-texto]");
  // Some com o logo de uma KB aberta antes
  imagem.removeAttribute("src");
  imagem.hidden = true;
  linha.hidden = kb.tipo !== "kit_da_marca";
  if (linha.hidden) {
    return;
  }
  preencher_amostras_de_cor(document.querySelector("[data-kb-kit-cores]"), cores_validas(kb.ficha.cores));
  // O kit padrão do Santander não leva logo
  if (!dono_e_empresa(kb.dono)) {
    texto.textContent = "O kit padrão não leva logo.";
    return;
  }
  // Sem logo nesta versão: só o recado
  if (!kb.tem_logo) {
    texto.textContent = "Sem logo nesta versão.";
    return;
  }
  imagem.src = endereco_do_logo_da_versao(kb.kb_id, kb.versao) + "?momento=" + Date.now();
  imagem.hidden = false;
  texto.textContent = texto_do_logo_da_versao(kb);
}

/**
 * O texto ao lado do logo na janela da KB: no kit padrão, o logo fica guardado, mas não entra na arte.
 *
 * Recebe: kb — a versão aberta, com logo. Devolve: o texto. Exemplo: kit padrão → "Logo desta versão: só entra na
 * arte com o kit próprio."
 */
function texto_do_logo_da_versao(kb) {
  if (kb.ficha.kit_escolhido === "proprio") {
    return "Logo desta versão.";
  }
  return "Logo desta versão: só entra na arte com o kit próprio.";
}
