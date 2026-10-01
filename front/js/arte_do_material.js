/*
  arte_do_material.js — o desenho da ARTE de um material de endomarketing, no navegador (canvas).

  Para que serve: pega um material já gerado pelo Agente de Endomarketing (título e blocos com as fontes) e o kit
  visual da empresa (cores, marca, assinatura e, quando houver, o logo) e desenha uma imagem pronta para divulgar.
  A arte tem o formato do CANAL do material, e só a arte desse canal aparece e é publicada:
    - e-mail: um banner deitado (1200 × 400 px), com a marca numa coluna à esquerda e o texto à direita;
    - mural: um cartaz em pé no tamanho A4 (1240 × 1754 px, o A4 em 150 dpi), para imprimir;
    - WhatsApp: uma imagem quadrada (1080 × 1080 px), com o texto curto do canal.
  Os três têm o mesmo estilo: as cores e o logo do kit, a marca sobre a cor principal, o título em negrito, a frase de
  um bloco, a fonte desse bloco no rodapé e uma tira na cor escura embaixo.

  Por que o navegador desenha, e não a IA (ADR-87):
    - a IA não gera imagem: o texto da arte é o MESMO do material, que já foi conferido com o catálogo;
    - todo texto da arte vem do material (o título, a frase de um bloco e a fonte desse bloco no rodapé); fora isso,
      só a marca e a assinatura do kit. Nada novo aparece na imagem;
    - a arte não escreve o nome do canal entre parênteses: se o título da IA vier com
      "(E-mail)" ou "(WhatsApp)", o parêntese sai da imagem (texto_sem_o_canal). Na tela, fora da imagem, o canal
      continua aparecendo;
    - a arte anota no próprio canvas tudo o que escreveu (anotar_textos_da_arte), para quem usa leitor de tela e para
      os roteiros de clique conferirem que ela é fiel ao texto.

  O kit vem da API (GET /api/banco/empresas/{id}/endomarketing, campo "kit"):
    { nome, marca, assinatura, cor_principal, cor_escura, cor_fundo, cor_texto, cor_apoio, endereco_do_logo }
  endereco_do_logo é null quando a empresa não tem logo ou usa o kit padrão (o logo só entra no kit próprio).

  Quem usa: a aba "Endomarketing" do Portal Interno (js/banco_endomarketing.js). Funções principais:
    molde_do_canal(canal), descricao_do_molde(chave_do_molde) e desenhar_arte_do_material(canvas, material, kit,
    chave_do_molde).
  Os testes no Node (tests/front/arte_do_material.test.mjs) rodam este arquivo com um canvas de mentira: o tamanho de
  cada canal, o texto sem o canal e todo texto dentro da imagem.
*/

// ===== Os moldes: um para cada canal =====

// Cada molde: o nome na tela, o tamanho real da imagem (em pixels), o tamanho inicial das letras do título e da frase
// (elas diminuem se o texto não couber) e uma nota sobre o formato, quando ela ajuda quem vai usar a arte.
const MOLDES_DA_ARTE = {
  // O WhatsApp: a imagem quadrada, que o aplicativo mostra inteira na conversa.
  cartao: { nome: "Imagem quadrada para WhatsApp", largura: 1080, altura: 1080, tamanho_titulo: 88, tamanho_frase: 48,
    nota: "" },
  // O mural: o cartaz em pé no tamanho A4 (21 × 29,7 cm) com 150 pontos por polegada (dpi), boa resolução para imprimir.
  cartaz: { nome: "Cartaz A4 para mural", largura: 1240, altura: 1754, tamanho_titulo: 120, tamanho_frase: 64,
    nota: "A4 em 150 dpi, para imprimir" },
  // O e-mail: o banner deitado, que vai no alto da mensagem.
  email: { nome: "Banner para e-mail", largura: 1200, altura: 400, tamanho_titulo: 52, tamanho_frase: 28, nota: "" },
};

// O molde de cada canal do material (WhatsApp → imagem quadrada; mural → cartaz A4; e-mail → banner).
const MOLDE_DO_CANAL = { whatsapp: "cartao", mural: "cartaz", email: "email" };

// A família de letras da arte: a mesma da página (Nunito Sans), com reservas se ela não carregar.
const LETRA_DA_ARTE = "'Nunito Sans', 'Segoe UI', Arial, sans-serif";

// O menor tamanho de letra da arte: o texto encolhe para caber, mas nunca abaixo disto (para continuar legível).
const MENOR_LETRA = 12;

// Os logos já baixados, pelo endereço (para não buscar de novo a cada desenho).
const LOGOS_GUARDADOS = {};

// Um trecho entre parênteses ou entre colchetes, com os espaços antes dele. Exemplo: " (E-mail)" ou " [WhatsApp]".
// É uma "expressão regular", um molde de texto: "espaços, abre ( ou [, qualquer coisa sem outro parêntese dentro,
// fecha ) ou ]". O que está dentro fica guardado (o "grupo" entre os parênteses sem barra) para a conferência do canal.
const TRECHO_ENTRE_PARENTESES = /\s*[\(\[]([^\(\)\[\]]*)[\)\]]/g;

// As palavras que dizem um canal de divulgação, sem acento e em minúsculas ("e-mail" vira "email" antes de comparar).
const PALAVRAS_DOS_CANAIS = ["email", "mural", "intranet", "whatsapp", "whats", "zap"];

// ===== Apoio =====

/**
 * O molde de um canal. Exemplo: molde_do_canal("mural") → "cartaz".
 *
 * Recebe: canal — "email", "mural" ou "whatsapp". Devolve: a chave do molde (canal desconhecido: "cartao").
 */
function molde_do_canal(canal) {
  // O canal tem um molde próprio: usa ele.
  if (MOLDE_DO_CANAL[canal]) {
    return MOLDE_DO_CANAL[canal];
  }
  // Canal sem molde próprio: a imagem quadrada, que serve para quase tudo.
  return "cartao";
}

/**
 * O formato de um molde, escrito para a tela (fora da imagem).
 *
 * Recebe: chave_do_molde — "cartao", "cartaz" ou "email".
 * Devolve: o texto. Exemplo: descricao_do_molde("cartaz") → "Cartaz A4 para mural · 1240 × 1754 px · A4 em 150 dpi,
 * para imprimir".
 */
function descricao_do_molde(chave_do_molde) {
  const molde = MOLDES_DA_ARTE[chave_do_molde];
  // O nome e o tamanho real da imagem.
  let descricao = molde.nome + " · " + molde.largura + " × " + molde.altura + " px";
  // A nota, quando o molde tem uma (hoje, só o cartaz A4).
  if (molde.nota) {
    descricao = descricao + " · " + molde.nota;
  }
  return descricao;
}

/**
 * Esquece o logo guardado de um endereço (depois que o banco troca ou tira o logo da empresa).
 *
 * Recebe: endereco — o endereco_do_logo do kit. Devolve: nada.
 */
function esquecer_logo_guardado(endereco) {
  // Apaga da memória: o próximo desenho busca o logo de novo.
  delete LOGOS_GUARDADOS[endereco];
}

/**
 * Busca o logo da empresa e o prepara para o desenho. Guarda o resultado para as próximas vezes.
 *
 * Recebe: endereco — o endereco_do_logo do kit (ou null).
 * Devolve: a imagem pronta para desenhar (ImageBitmap), ou null (sem logo, ou o logo não carregou).
 * Por que fetch + createImageBitmap, e não <img>: a imagem vem do próprio site e não precisa de endereço "blob:",
 * que a política de conteúdo do servidor (CSP) não libera para imagens. E o canvas continua podendo virar PNG.
 */
async function carregar_logo(endereco) {
  // Kit sem logo: nada a buscar.
  if (!endereco) {
    return null;
  }
  // Já buscado antes: devolve o guardado.
  if (endereco in LOGOS_GUARDADOS) {
    return LOGOS_GUARDADOS[endereco];
  }
  // try/catch: logo que não carrega não impede a arte (ela sai sem o logo).
  let imagem = null;
  try {
    // "no-store": pega sempre o logo atual (o banco pode ter trocado há pouco).
    const resposta = await fetch(endereco, { cache: "no-store" });
    // Só uma resposta de sucesso vira imagem.
    if (resposta.ok) {
      // O arquivo recebido (PNG ou JPEG).
      const arquivo = await resposta.blob();
      // Converte o arquivo numa imagem que o canvas sabe desenhar.
      imagem = await createImageBitmap(arquivo);
    }
  } catch (erro) {
    // Fica sem logo.
    imagem = null;
  }
  // Guarda para os próximos desenhos.
  LOGOS_GUARDADOS[endereco] = imagem;
  return imagem;
}

// ===== O texto da arte (sempre o do material, sem o nome do canal entre parênteses) =====

/**
 * Diz se um trecho (o que estava entre parênteses) fala de um canal de divulgação.
 *
 * Recebe: trecho — ex.: "E-mail", "versão para WhatsApp", "Mural ou intranet" ou "sem tarifa".
 * Devolve: true ou false. Exemplo: fala_de_um_canal("E-MAIL") → true; fala_de_um_canal("sem tarifa") → false.
 * Como: tira os acentos, passa para minúsculas, junta o que o hífen separa ("e-mail" → "email") e procura, palavra
 * por palavra, uma das PALAVRAS_DOS_CANAIS. Só vale a palavra inteira: "Zapata" não é "zap".
 */
function fala_de_um_canal(trecho) {
  // normalize("NFD") separa cada letra do seu acento; o replace tira os acentos que ficaram soltos.
  const sem_acento = trecho.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  // Tira os hífens (o do teclado e os tipográficos): "e-mail" vira "email"; "whats-app", "whatsapp".
  const sem_hifen = sem_acento.replace(/[-‐-―]/g, "");
  // Separa em palavras: tudo o que não é letra nem número separa uma palavra da outra.
  const palavras = sem_hifen.split(/[^a-z0-9]+/);
  for (const palavra of palavras) {
    // Uma palavra de canal basta.
    if (PALAVRAS_DOS_CANAIS.includes(palavra)) {
      return true;
    }
  }
  return false;
}

/**
 * O texto que vai para a arte: sem os trechos entre parênteses (ou colchetes) que falam de um canal.
 *
 * Recebe: texto — ex.: "Sua conta salário (E-mail)". Devolve: ex.: "Sua conta salário".
 * Os outros parênteses ficam: "Conta salário (sem tarifa)" continua igual. Nada entra no lugar: a arte continua
 * dizendo só o que o material diz (ADR-87), sem o rótulo do canal.
 */
function texto_sem_o_canal(texto) {
  // Olha cada trecho entre parênteses: some quando fala de um canal; senão, fica como estava.
  const sem_o_canal = texto.replace(TRECHO_ENTRE_PARENTESES, function (trecho_inteiro, dentro_dos_parenteses) {
    // Fala de um canal: sai, junto com o espaço antes dele.
    if (fala_de_um_canal(dentro_dos_parenteses)) {
      return "";
    }
    // Não fala: fica igual.
    return trecho_inteiro;
  });
  // Tira os espaços que sobraram nas pontas (ex.: "(E-mail) Sua conta" vira "Sua conta").
  return sem_o_canal.trim();
}

/**
 * O bloco do material que vai na arte: o segundo (o primeiro costuma ser a abertura) ou, se só houver um, ele.
 *
 * Recebe: material — { titulo, blocos: [{ texto, fontes }] }. Devolve: o bloco escolhido.
 */
function bloco_da_arte(material) {
  // Dois ou mais blocos: o segundo traz o benefício (o primeiro é a abertura).
  if (material.blocos.length > 1) {
    return material.blocos[1];
  }
  // Um bloco só: ele mesmo.
  return material.blocos[0];
}

/**
 * O rodapé da arte: a fonte do bloco desenhado, do jeito que o material mostra. Exemplo: "Fonte: Pacote Folha › Conta salário".
 *
 * Recebe: bloco — { texto, fontes }. Devolve: o texto do rodapé.
 */
function rodape_da_arte(bloco) {
  // As fontes do bloco, separadas por "; " (o mesmo jeito da tela do material).
  return "Fonte: " + bloco.fontes.join("; ");
}

/**
 * Os três textos do material que vão para a arte, já sem o nome do canal entre parênteses.
 *
 * Recebe: material — { titulo, blocos: [{ texto, fontes }] }.
 * Devolve: { titulo, frase, rodape }. Exemplo: para o título "Sua conta salário (E-mail)", o titulo é "Sua conta salário".
 */
function textos_do_material_para_a_arte(material) {
  // O bloco que vai na arte (a frase e a fonte dele).
  const bloco = bloco_da_arte(material);
  return {
    titulo: texto_sem_o_canal(material.titulo),
    frase: texto_sem_o_canal(bloco.texto),
    rodape: texto_sem_o_canal(rodape_da_arte(bloco)),
  };
}

// ===== Medir o texto (não pinta nada: só calcula; por isso os testes no Node conferem) =====

/**
 * Quebra um texto em linhas que cabem numa largura, palavra por palavra.
 *
 * Recebe: contexto — o "pincel" do canvas (já com a letra escolhida); texto; largura_maxima — em pixels.
 * Devolve: a lista de linhas. Exemplo: "Conta salário sem tarifa" numa largura curta → ["Conta salário", "sem tarifa"].
 */
function quebrar_em_linhas(contexto, texto, largura_maxima) {
  const linhas = [];
  let linha_atual = "";
  // Uma palavra de cada vez.
  for (const palavra of texto.split(" ")) {
    // A linha como ficaria com mais esta palavra (a primeira palavra da linha entra sem espaço antes).
    let tentativa = palavra;
    if (linha_atual) {
      tentativa = linha_atual + " " + palavra;
    }
    // measureText diz quantos pixels o texto ocupa com a letra atual. Passou da largura: a palavra vai para a próxima linha.
    if (contexto.measureText(tentativa).width > largura_maxima && linha_atual) {
      linhas.push(linha_atual);
      linha_atual = palavra;
    } else {
      linha_atual = tentativa;
    }
  }
  // A última linha, se sobrou alguma coisa.
  if (linha_atual) {
    linhas.push(linha_atual);
  }
  return linhas;
}

/**
 * A largura da linha mais larga de uma lista, com a letra atual do pincel.
 *
 * Recebe: contexto; linhas — a lista de textos. Devolve: a largura em pixels (lista vazia: 0).
 */
function largura_da_linha_mais_larga(contexto, linhas) {
  let maior = 0;
  // Mede uma linha de cada vez e guarda a maior.
  for (const linha of linhas) {
    const largura = contexto.measureText(linha).width;
    if (largura > maior) {
      maior = largura;
    }
  }
  return maior;
}

/**
 * Diz se um texto cabe num espaço com um tamanho de letra: na altura (todas as linhas) e na largura (nenhuma linha
 * passa da borda).
 *
 * Recebe: contexto; texto; largura e altura_maxima — em pixels; tamanho — da letra; peso — "800", "700" ou "400".
 * Devolve: true ou false.
 */
function bloco_cabe(contexto, texto, largura, altura_maxima, tamanho, peso) {
  // Escolhe a letra no tamanho a testar e quebra o texto em linhas com ela.
  contexto.font = peso + " " + tamanho + "px " + LETRA_DA_ARTE;
  const linhas = quebrar_em_linhas(contexto, texto, largura);
  // Cada linha ocupa 1,2 vez o tamanho da letra (o espaço entre linhas).
  const cabe_na_altura = linhas.length * tamanho * 1.2 <= altura_maxima;
  // Uma palavra comprida demais (um endereço de site, por exemplo) fica sozinha numa linha e pode passar da largura.
  const cabe_na_largura = largura_da_linha_mais_larga(contexto, linhas) <= largura;
  return cabe_na_altura && cabe_na_largura;
}

/**
 * Mede um bloco de texto que precisa caber num espaço: se não couber, diminui a letra até caber. Nunca corta o texto,
 * para não mudar o que o material diz.
 *
 * Recebe: contexto; texto; largura e altura_maxima — em pixels; tamanho_inicial — da letra; peso — "800", "700" ou
 * "400". Devolve: { linhas, tamanho, altura, peso }.
 */
function medir_bloco(contexto, texto, largura, altura_maxima, tamanho_inicial, peso) {
  let tamanho = tamanho_inicial;
  // Diminui a letra de 2 em 2 enquanto o texto não cabe (e nunca abaixo da MENOR_LETRA).
  while (tamanho - 2 >= MENOR_LETRA && !bloco_cabe(contexto, texto, largura, altura_maxima, tamanho, peso)) {
    tamanho = tamanho - 2;
  }
  // As linhas no tamanho escolhido.
  contexto.font = peso + " " + tamanho + "px " + LETRA_DA_ARTE;
  const linhas = quebrar_em_linhas(contexto, texto, largura);
  return { linhas: linhas, tamanho: tamanho, altura: linhas.length * tamanho * 1.2, peso: peso };
}

/**
 * O tamanho de letra com que um texto cabe numa linha só: começa no tamanho pedido e diminui até caber.
 *
 * Recebe: contexto; texto; largura_maxima — em pixels; tamanho_inicial; peso. Devolve: o tamanho (em pixels).
 * Exemplo: a assinatura "Aurora Alimentos" no espaço que sobra ao lado da marca.
 */
function tamanho_que_cabe_numa_linha(contexto, texto, largura_maxima, tamanho_inicial, peso) {
  let tamanho = tamanho_inicial;
  contexto.font = peso + " " + tamanho + "px " + LETRA_DA_ARTE;
  // Diminui de 2 em 2 enquanto o texto passa da largura (e nunca abaixo da MENOR_LETRA).
  while (contexto.measureText(texto).width > largura_maxima && tamanho - 2 >= MENOR_LETRA) {
    tamanho = tamanho - 2;
    contexto.font = peso + " " + tamanho + "px " + LETRA_DA_ARTE;
  }
  return tamanho;
}

/**
 * Arruma o título e a frase numa caixa: mede os dois (a letra diminui se precisar) e calcula onde cada um começa,
 * com os dois juntos no meio da altura da caixa.
 *
 * Recebe: contexto (o pincel, só para medir); textos — { titulo, frase }; caixa — { x, y, largura, altura };
 *         molde — os tamanhos iniciais das letras; altura_da_barra — a barra de destaque entre os dois (0 = sem barra).
 * Devolve: { titulo, frase, y_do_titulo, y_da_barra, y_da_frase } — os dois blocos medidos e o alto de cada peça.
 */
function arrumar_titulo_e_frase(contexto, textos, caixa, molde, altura_da_barra) {
  // O respiro entre o título e a frase acompanha o tamanho da frase.
  const respiro = Math.round(molde.tamanho_frase * 0.6);
  // O espaço entre os dois: o respiro e, com a barra, a barra e mais um respiro.
  let espaco_entre = respiro;
  if (altura_da_barra > 0) {
    espaco_entre = respiro + altura_da_barra + respiro;
  }
  // O título ocupa no máximo 45% da altura da caixa; a frase, o que sobra.
  const titulo = medir_bloco(contexto, textos.titulo, caixa.largura, caixa.altura * 0.45, molde.tamanho_titulo, "800");
  const altura_livre_da_frase = caixa.altura - titulo.altura - espaco_entre;
  const frase = medir_bloco(contexto, textos.frase, caixa.largura, altura_livre_da_frase, molde.tamanho_frase, "400");
  // Os dois juntos, centralizados na altura da caixa.
  const altura_do_texto = titulo.altura + espaco_entre + frase.altura;
  const y_do_titulo = caixa.y + (caixa.altura - altura_do_texto) / 2;
  return {
    titulo: titulo,
    frase: frase,
    y_do_titulo: y_do_titulo,
    y_da_barra: y_do_titulo + titulo.altura + respiro,
    y_da_frase: y_do_titulo + titulo.altura + espaco_entre,
  };
}

/**
 * Mede o quadro branco do logo: o logo cabe dentro, com um respiro em volta, na proporção da imagem, sem passar da
 * largura máxima do quadro.
 *
 * Recebe: logo — a imagem (tem width e height); altura_do_quadro e largura_maxima_do_quadro — em pixels.
 * Devolve: { largura, altura, respiro, largura_do_logo, altura_do_logo }.
 */
function medir_quadro_do_logo(logo, altura_do_quadro, largura_maxima_do_quadro) {
  // O respiro em volta do logo: 12% da altura do quadro.
  const respiro = Math.round(altura_do_quadro * 0.12);
  // O logo ocupa a altura que sobra dentro do quadro; a largura acompanha a proporção da imagem.
  let altura_do_logo = altura_do_quadro - 2 * respiro;
  let largura_do_logo = Math.round(logo.width * altura_do_logo / logo.height);
  // A largura máxima do logo: a do quadro, menos o respiro dos dois lados.
  const largura_maxima_do_logo = largura_maxima_do_quadro - 2 * respiro;
  if (largura_do_logo > largura_maxima_do_logo) {
    // Logo muito comprido: encolhe pela largura, mantendo a proporção.
    altura_do_logo = Math.round(altura_do_logo * largura_maxima_do_logo / largura_do_logo);
    largura_do_logo = largura_maxima_do_logo;
  }
  return {
    largura: largura_do_logo + 2 * respiro,
    altura: altura_do_quadro,
    respiro: respiro,
    largura_do_logo: largura_do_logo,
    altura_do_logo: altura_do_logo,
  };
}

// ===== Pintar as peças (as mesmas nos três moldes) =====

/**
 * Pinta um bloco já medido, a partir de um ponto.
 *
 * Recebe: contexto; bloco — o resultado de medir_bloco; x e y — onde o bloco começa (o alto); cor. Devolve: nada.
 */
function pintar_bloco(contexto, bloco, x, y, cor) {
  // A letra e a cor com que o bloco foi medido.
  contexto.font = bloco.peso + " " + bloco.tamanho + "px " + LETRA_DA_ARTE;
  contexto.fillStyle = cor;
  // Uma linha embaixo da outra (fillText escreve a partir da linha de base das letras).
  for (let posicao = 0; posicao < bloco.linhas.length; posicao = posicao + 1) {
    contexto.fillText(bloco.linhas[posicao], x, y + bloco.tamanho + posicao * bloco.tamanho * 1.2);
  }
}

/**
 * Pinta o fundo da arte inteira na cor de fundo do kit.
 *
 * Recebe: contexto; molde; kit. Devolve: nada.
 */
function pintar_fundo(contexto, molde, kit) {
  // Um retângulo do tamanho da arte inteira, na cor de fundo.
  contexto.fillStyle = kit.cor_fundo;
  contexto.fillRect(0, 0, molde.largura, molde.altura);
}

/**
 * Pinta a tira de baixo, de ponta a ponta, na cor escura do kit.
 *
 * Recebe: contexto; molde; kit; altura_da_tira — em pixels. Devolve: nada.
 */
function pintar_tira_escura(contexto, molde, kit, altura_da_tira) {
  // Um retângulo encostado no pé da arte, de uma borda à outra, na cor escura.
  contexto.fillStyle = kit.cor_escura;
  contexto.fillRect(0, molde.altura - altura_da_tira, molde.largura, altura_da_tira);
}

/**
 * Pinta o rodapé (a fonte do bloco desenhado) numa linha só: se não couber na largura, a letra diminui.
 *
 * Recebe: contexto; texto; x e y_da_base — onde a linha começa (y é a linha de base das letras); largura_maxima;
 *         tamanho_inicial — da letra; cor. Devolve: nada.
 */
function pintar_rodape(contexto, texto, x, y_da_base, largura_maxima, tamanho_inicial, cor) {
  // O tamanho com que o rodapé cabe numa linha (uma fonte comprida encolhe).
  const tamanho = tamanho_que_cabe_numa_linha(contexto, texto, largura_maxima, tamanho_inicial, "400");
  // Letra normal (peso 400), na cor pedida, escrita a partir do ponto dado.
  contexto.font = "400 " + tamanho + "px " + LETRA_DA_ARTE;
  contexto.fillStyle = cor;
  contexto.fillText(texto, x, y_da_base);
}

/**
 * Pinta o título (na cor do texto) e a frase (na cor de apoio) numa caixa, com a barra de destaque entre os dois
 * quando o molde pede.
 *
 * Recebe: contexto; textos — { titulo, frase }; caixa — { x, y, largura, altura }; molde; kit;
 *         altura_da_barra — em pixels (0 = sem barra). Devolve: nada.
 */
function pintar_titulo_e_frase(contexto, textos, caixa, molde, kit, altura_da_barra) {
  // Primeiro mede e calcula onde cada peça fica; depois pinta.
  const arrumacao = arrumar_titulo_e_frase(contexto, textos, caixa, molde, altura_da_barra);
  // O título, na cor do texto.
  pintar_bloco(contexto, arrumacao.titulo, caixa.x, arrumacao.y_do_titulo, kit.cor_texto);
  // A barra de destaque: na cor principal, com um quarto da largura da caixa (só no molde que a usa).
  if (altura_da_barra > 0) {
    contexto.fillStyle = kit.cor_principal;
    contexto.fillRect(caixa.x, arrumacao.y_da_barra, Math.round(caixa.largura * 0.25), altura_da_barra);
  }
  // A frase, na cor de apoio, logo abaixo.
  pintar_bloco(contexto, arrumacao.frase, caixa.x, arrumacao.y_da_frase, kit.cor_apoio);
}

/**
 * Pinta o quadro branco de cantos arredondados e o logo dentro dele (assim um logo de qualquer cor aparece bem sobre
 * a cor principal do kit).
 *
 * Recebe: contexto; logo — a imagem; quadro — o resultado de medir_quadro_do_logo; x e y — o canto de cima, à
 * esquerda, do quadro. Devolve: nada.
 */
function pintar_quadro_do_logo(contexto, logo, quadro, x, y) {
  // O quadro é branco; beginPath começa um desenho novo (para o fill pintar só o quadro).
  contexto.fillStyle = "#ffffff";
  contexto.beginPath();
  // roundRect desenha um retângulo com os cantos arredondados.
  contexto.roundRect(x, y, quadro.largura, quadro.altura, Math.round(quadro.altura * 0.15));
  contexto.fill();
  // O logo, centralizado na altura do quadro, depois do respiro da esquerda.
  const y_do_logo = y + Math.round((quadro.altura - quadro.altura_do_logo) / 2);
  contexto.drawImage(logo, x + quadro.respiro, y_do_logo, quadro.largura_do_logo, quadro.altura_do_logo);
}

/**
 * Pinta a faixa de cima (imagem quadrada e cartaz A4): a faixa na cor principal, a marca à esquerda e, à direita, o
 * logo da empresa (se houver) ou a assinatura do kit próprio (o nome da empresa), sem um encostar no outro.
 *
 * Recebe: contexto; kit; logo — a imagem ou null; molde; margem; altura_da_faixa.
 * Devolve: a lista dos textos pintados na faixa (para a anotação da arte).
 */
function pintar_faixa_da_marca(contexto, kit, logo, molde, margem, altura_da_faixa) {
  const textos_pintados = [];
  // A faixa, na cor principal do kit, de ponta a ponta.
  contexto.fillStyle = kit.cor_principal;
  contexto.fillRect(0, 0, molde.largura, altura_da_faixa);
  // A marca, em branco e negrito, à esquerda.
  const tamanho_da_marca = Math.round(altura_da_faixa * 0.42);
  contexto.fillStyle = "#ffffff";
  contexto.font = "800 " + tamanho_da_marca + "px " + LETRA_DA_ARTE;
  contexto.fillText(kit.marca, margem, altura_da_faixa * 0.64);
  textos_pintados.push(kit.marca);
  // Com logo: ele ocupa a direita da faixa (o nome da empresa já está no logo), no máximo 40% da largura da arte.
  if (logo) {
    const quadro = medir_quadro_do_logo(logo, Math.round(altura_da_faixa * 0.7), Math.round(molde.largura * 0.4));
    // Encostado na margem direita, centralizado na altura da faixa.
    const x_do_quadro = molde.largura - margem - quadro.largura;
    const y_do_quadro = Math.round((altura_da_faixa - quadro.altura) / 2);
    pintar_quadro_do_logo(contexto, logo, quadro, x_do_quadro, y_do_quadro);
    return textos_pintados;
  }
  // Sem logo e sem assinatura (kit padrão): só a marca.
  if (!kit.assinatura) {
    return textos_pintados;
  }
  // O espaço que sobra à direita da marca, com um respiro entre os dois (a letra ainda é a da marca).
  const espaco_livre = molde.largura - 2 * margem - contexto.measureText(kit.marca).width - margem;
  // A assinatura começa menor que a marca e encolhe até caber no espaço livre.
  const tamanho = tamanho_que_cabe_numa_linha(contexto, kit.assinatura, espaco_livre,
    Math.round(tamanho_da_marca * 0.7), "700");
  contexto.font = "700 " + tamanho + "px " + LETRA_DA_ARTE;
  // Encostada na margem direita.
  const largura_da_assinatura = contexto.measureText(kit.assinatura).width;
  contexto.fillText(kit.assinatura, molde.largura - margem - largura_da_assinatura, altura_da_faixa * 0.62);
  textos_pintados.push(kit.assinatura);
  return textos_pintados;
}

/**
 * Pinta a coluna da marca (banner do e-mail): a coluna na cor principal, de cima a baixo, com a marca no alto e, no
 * pé, o logo da empresa (se houver) ou a assinatura do kit próprio.
 *
 * Recebe: contexto; kit; logo — a imagem ou null; molde; margem; largura_da_coluna; altura_da_tira — a tira escura de
 * baixo (o pé da coluna fica acima dela).
 * Devolve: a lista dos textos pintados na coluna (para a anotação da arte).
 */
function pintar_coluna_da_marca(contexto, kit, logo, molde, margem, largura_da_coluna, altura_da_tira) {
  const textos_pintados = [];
  // A coluna, na cor principal do kit.
  contexto.fillStyle = kit.cor_principal;
  contexto.fillRect(0, 0, largura_da_coluna, molde.altura);
  // A largura livre dentro da coluna, sem as margens.
  const largura_livre = largura_da_coluna - 2 * margem;
  // A marca, em branco e negrito, no alto da coluna (encolhe até caber na largura livre).
  const tamanho_da_marca = tamanho_que_cabe_numa_linha(contexto, kit.marca, largura_livre,
    Math.round(molde.altura * 0.13), "800");
  contexto.fillStyle = "#ffffff";
  contexto.font = "800 " + tamanho_da_marca + "px " + LETRA_DA_ARTE;
  contexto.fillText(kit.marca, margem, margem + tamanho_da_marca);
  textos_pintados.push(kit.marca);
  // O pé da coluna: onde o logo ou a assinatura terminam, acima da tira escura, com uma margem.
  const pe_da_coluna = molde.altura - altura_da_tira - margem;
  // Com logo: o quadro branco no pé da coluna, com 30% da altura da arte.
  if (logo) {
    const quadro = medir_quadro_do_logo(logo, Math.round(molde.altura * 0.3), largura_livre);
    pintar_quadro_do_logo(contexto, logo, quadro, margem, pe_da_coluna - quadro.altura);
    return textos_pintados;
  }
  // Sem logo e sem assinatura (kit padrão): só a marca.
  if (!kit.assinatura) {
    return textos_pintados;
  }
  // A assinatura no pé da coluna, em branco: pode ocupar mais de uma linha (o nome da empresa pode ser comprido).
  const assinatura = medir_bloco(contexto, kit.assinatura, largura_livre, Math.round(molde.altura * 0.3),
    Math.round(tamanho_da_marca * 0.7), "700");
  pintar_bloco(contexto, assinatura, margem, pe_da_coluna - assinatura.altura, "#ffffff");
  textos_pintados.push(kit.assinatura);
  return textos_pintados;
}

// ===== As composições: o mesmo estilo, arrumado para o formato de cada canal =====

/**
 * A imagem quadrada do WhatsApp (1080 × 1080): a faixa da marca no alto, o título e a frase no meio, a fonte no
 * rodapé e a tira escura embaixo. É o desenho do antigo "cartão".
 *
 * Recebe: contexto; molde; kit; logo (ou null); textos — { titulo, frase, rodape }.
 * Devolve: a lista dos textos pintados, na ordem (para a anotação da arte).
 */
function pintar_imagem_quadrada(contexto, molde, kit, logo, textos) {
  // As medidas: a margem (7% da largura) e a faixa de cima (14% da altura).
  const margem = Math.round(molde.largura * 0.07);
  const altura_da_faixa = Math.round(molde.altura * 0.14);
  pintar_fundo(contexto, molde, kit);
  const textos_pintados = pintar_faixa_da_marca(contexto, kit, logo, molde, margem, altura_da_faixa);
  // A caixa do texto: da faixa (com meia margem) até o rodapé (com margem e meia).
  const caixa = {
    x: margem,
    y: altura_da_faixa + margem * 0.5,
    largura: molde.largura - 2 * margem,
    altura: molde.altura - altura_da_faixa - margem * 1.9,
  };
  pintar_titulo_e_frase(contexto, textos, caixa, molde, kit, 0);
  // O rodapé: a fonte do bloco, perto do pé, e a tira escura fina embaixo.
  pintar_rodape(contexto, textos.rodape, margem, molde.altura - margem * 0.6, caixa.largura,
    Math.round(molde.tamanho_frase * 0.55), kit.cor_apoio);
  pintar_tira_escura(contexto, molde, kit, 12);
  textos_pintados.push(textos.titulo, textos.frase, textos.rodape);
  return textos_pintados;
}

/**
 * O cartaz A4 do mural (1240 × 1754, para imprimir): a faixa da marca no alto, o título grande, uma barra na cor
 * principal, a frase, a fonte no rodapé e uma tira escura mais grossa embaixo. As letras são maiores, para ler de longe.
 *
 * Recebe: contexto; molde; kit; logo (ou null); textos — { titulo, frase, rodape }.
 * Devolve: a lista dos textos pintados, na ordem (para a anotação da arte).
 */
function pintar_cartaz_a4(contexto, molde, kit, logo, textos) {
  // As medidas: a margem (8% da largura), a faixa de cima (12% da altura) e a tira de baixo (2% da altura).
  const margem = Math.round(molde.largura * 0.08);
  const altura_da_faixa = Math.round(molde.altura * 0.12);
  const altura_da_tira = Math.round(molde.altura * 0.02);
  pintar_fundo(contexto, molde, kit);
  const textos_pintados = pintar_faixa_da_marca(contexto, kit, logo, molde, margem, altura_da_faixa);
  // O rodapé fica logo acima da tira escura, com meia margem de respiro.
  const tamanho_do_rodape = Math.round(molde.tamanho_frase * 0.55);
  const base_do_rodape = molde.altura - altura_da_tira - margem * 0.5;
  // A caixa do texto: da faixa até o rodapé, com uma margem de cada lado.
  const topo_da_caixa = altura_da_faixa + margem;
  const caixa = {
    x: margem,
    y: topo_da_caixa,
    largura: molde.largura - 2 * margem,
    altura: base_do_rodape - tamanho_do_rodape - margem - topo_da_caixa,
  };
  // A barra entre o título e a frase: quem olha o mural de longe vê o título primeiro.
  pintar_titulo_e_frase(contexto, textos, caixa, molde, kit, Math.round(molde.altura * 0.008));
  pintar_rodape(contexto, textos.rodape, margem, base_do_rodape, caixa.largura, tamanho_do_rodape, kit.cor_apoio);
  pintar_tira_escura(contexto, molde, kit, altura_da_tira);
  textos_pintados.push(textos.titulo, textos.frase, textos.rodape);
  return textos_pintados;
}

/**
 * O banner do e-mail (1200 × 400): a coluna da marca à esquerda (a marca no alto, o logo ou a assinatura no pé), o
 * título e a frase à direita, a fonte no rodapé e a tira escura embaixo.
 *
 * Recebe: contexto; molde; kit; logo (ou null); textos — { titulo, frase, rodape }.
 * Devolve: a lista dos textos pintados, na ordem (para a anotação da arte).
 */
function pintar_banner_de_email(contexto, molde, kit, logo, textos) {
  // As medidas: a margem (10% da altura), a coluna da marca (28% da largura) e a tira de baixo.
  const margem = Math.round(molde.altura * 0.1);
  const largura_da_coluna = Math.round(molde.largura * 0.28);
  const altura_da_tira = 12;
  pintar_fundo(contexto, molde, kit);
  const textos_pintados = pintar_coluna_da_marca(contexto, kit, logo, molde, margem, largura_da_coluna, altura_da_tira);
  // O texto começa depois da coluna, com uma margem.
  const x_do_texto = largura_da_coluna + margem;
  const largura_do_texto = molde.largura - x_do_texto - margem;
  // O rodapé fica perto do pé, acima da tira escura.
  const tamanho_do_rodape = Math.round(molde.tamanho_frase * 0.55);
  const base_do_rodape = molde.altura - altura_da_tira - margem * 0.6;
  // A caixa do texto: do alto (com uma margem) até o rodapé (com meia margem).
  const caixa = {
    x: x_do_texto,
    y: margem,
    largura: largura_do_texto,
    altura: base_do_rodape - tamanho_do_rodape - margem * 0.5 - margem,
  };
  pintar_titulo_e_frase(contexto, textos, caixa, molde, kit, 0);
  pintar_rodape(contexto, textos.rodape, x_do_texto, base_do_rodape, largura_do_texto, tamanho_do_rodape, kit.cor_apoio);
  pintar_tira_escura(contexto, molde, kit, altura_da_tira);
  textos_pintados.push(textos.titulo, textos.frase, textos.rodape);
  return textos_pintados;
}

// ===== O desenho =====

/**
 * Anota no próprio canvas o que foi escrito nele (ADR-87: a arte não tem texto que o material não tenha).
 *
 * Recebe: canvas; textos — tudo o que foi pintado, na ordem; molde — a chave do molde; com_logo — true ou false.
 * Devolve: nada.
 * O rótulo de acessibilidade lê a arte para quem usa leitor de tela; data-textos-da-arte guarda a mesma lista para a
 * conferência automática (roteiro de clique arte_fiel_ao_texto); data-molde-desenhado e data-arte-com-logo dizem aos
 * roteiros que o desenho terminou, em qual molde e se o logo entrou.
 */
function anotar_textos_da_arte(canvas, textos, molde, com_logo) {
  // Só os textos que apareceram de fato (um título que era só o nome do canal fica vazio e não entra).
  const textos_escritos = [];
  for (const texto of textos) {
    if (texto) {
      textos_escritos.push(texto);
    }
  }
  // O rótulo que o leitor de tela lê, com todos os textos da arte.
  canvas.setAttribute("aria-label", "Prévia da arte: " + textos_escritos.join(" · "));
  // A mesma lista, para os roteiros de clique conferirem, e o molde que acabou de ser desenhado.
  canvas.dataset.textosDaArte = JSON.stringify(textos_escritos);
  canvas.dataset.moldeDesenhado = molde;
  // "sim" ou "nao" (texto: os atributos da página só guardam texto).
  if (com_logo) {
    canvas.dataset.arteComLogo = "sim";
  } else {
    canvas.dataset.arteComLogo = "nao";
  }
}

/**
 * Desenha a arte de um material num canvas, no molde do canal, com as cores, a marca e o logo do kit da empresa.
 * O texto é o do próprio material: o título e a frase de um bloco, com a fonte desse bloco no rodapé, sem o nome do
 * canal entre parênteses. Fora isso, só a marca e a assinatura do kit. A IA não desenha e a arte não inventa texto
 * (ADR-87).
 *
 * Recebe: canvas — o elemento <canvas> da página; material — { titulo, blocos: [{ texto, fontes }] };
 *         kit — o kit da empresa (cores, marca, assinatura, endereco_do_logo); chave_do_molde — "cartao", "cartaz" ou
 *         "email" (o de cada canal: molde_do_canal).
 * Devolve: nada (espera as letras e o logo carregarem e desenha). Se outro desenho for pedido no mesmo canvas enquanto
 * este espera, este desiste (vale sempre o último pedido).
 * Exemplo: await desenhar_arte_do_material(canvas, material, kit, molde_do_canal("mural")).
 */
async function desenhar_arte_do_material(canvas, material, kit, chave_do_molde) {
  // Numera o pedido: se outro chegar enquanto este espera, só o mais novo desenha.
  const numero_do_pedido = Number(canvas.dataset.pedidoDeDesenho || "0") + 1;
  canvas.dataset.pedidoDeDesenho = String(numero_do_pedido);
  // Até o desenho novo terminar, o canvas não diz que está pronto (quem espera, como o "Publicar", espera este).
  delete canvas.dataset.moldeDesenhado;
  // Espera as letras da página carregarem (senão o canvas desenharia com a letra reserva).
  await document.fonts.ready;
  // O logo da empresa (só no kit próprio com logo; senão, null).
  const logo = await carregar_logo(kit.endereco_do_logo);
  // Chegou um pedido mais novo enquanto esperava: desiste deste.
  if (canvas.dataset.pedidoDeDesenho !== String(numero_do_pedido)) {
    return;
  }
  // O molde pedido (o do canal do rascunho): o tamanho e as letras.
  const molde = MOLDES_DA_ARTE[chave_do_molde];
  // O canvas passa a ter o tamanho real da imagem (a página o mostra menor, pelo CSS).
  canvas.width = molde.largura;
  canvas.height = molde.altura;
  // O "pincel" de desenho em duas dimensões do canvas.
  const contexto = canvas.getContext("2d");
  // Os textos do material que vão para a arte (sem o nome do canal entre parênteses).
  const textos = textos_do_material_para_a_arte(material);
  // Cada molde tem a sua composição: o banner do e-mail, o cartaz A4 do mural ou a imagem quadrada do WhatsApp.
  let textos_pintados = [];
  if (chave_do_molde === "email") {
    textos_pintados = pintar_banner_de_email(contexto, molde, kit, logo, textos);
  } else if (chave_do_molde === "cartaz") {
    textos_pintados = pintar_cartaz_a4(contexto, molde, kit, logo, textos);
  } else {
    textos_pintados = pintar_imagem_quadrada(contexto, molde, kit, logo, textos);
  }
  // O que ficou escrito na arte: a marca (e a assinatura), o título, a frase e o rodapé.
  anotar_textos_da_arte(canvas, textos_pintados, chave_do_molde, logo !== null);
}
