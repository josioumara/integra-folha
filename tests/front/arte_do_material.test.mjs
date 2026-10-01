/*
  arte_do_material.test.mjs — os testes do desenho da arte do endomarketing (front/js/arte_do_material.js), no Node.

  Para que serve: a arte é desenhada no navegador (canvas), mas as contas do desenho não precisam de navegador: o molde
  de cada canal, o tamanho da imagem, o texto sem o nome do canal e o lugar de cada texto. Aqui, o arquivo da tela roda
  no Node, dentro de uma "caixa de areia" (o módulo vm, que roda um código separado do resto), com um canvas de
  mentira que só anota o que foi pintado e mede o texto de um jeito simples.

  O que ele confere (escolhido o canal, só aparece a arte daquele canal, e sem o nome do canal entre parênteses na
  imagem):
    - cada canal tem o seu molde, no tamanho certo: e-mail 1200 × 400, mural 1240 × 1754 (A4 em 150 dpi), WhatsApp
      1080 × 1080;
    - a arte não escreve o nome do canal entre parênteses, em nenhuma grafia, e deixa os outros parênteses;
    - tudo o que a arte escreve vem do material (ou é a marca e a assinatura do kit), e todo texto fica dentro da
      imagem, mesmo com título e frase compridos;
    - o logo cabe no seu lugar (a faixa de cima ou a coluna do banner), e a imagem quadrada continua o desenho de antes.

  Como rodar: node --test tests/front/arte_do_material.test.mjs
  (o pytest tests/test_arte_do_material_no_node.py roda este arquivo, para ele entrar na bateria).
*/
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import assert from "node:assert/strict";

// ===== Preparação: o arquivo da tela, um canvas de mentira e os dados de exemplo =====

// O arquivo da arte, lido como texto (o mesmo que o navegador carrega).
const CODIGO_DA_ARTE = readFileSync(new URL("../../front/js/arte_do_material.js", import.meta.url), "utf-8");

// O tamanho que cada canal deve ter: [largura, altura], em pixels.
const TAMANHO_DO_CANAL = { email: [1200, 400], mural: [1240, 1754], whatsapp: [1080, 1080] };

// Quanto cada letra ocupa no canvas de mentira, em relação ao tamanho da letra (perto do que a Nunito Sans ocupa).
const LARGURA_DE_UMA_LETRA = 0.55;

/**
 * O tamanho da letra escrito na propriedade "font" do pincel. Exemplo: "800 88px 'Nunito Sans'" → 88.
 *
 * Recebe: fonte — o texto da propriedade font. Devolve: o número (sem letra escolhida: 10, o padrão do canvas).
 */
function tamanho_da_letra(fonte) {
  // Procura o número que vem antes de "px".
  const achado = /(\d+(?:\.\d+)?)px/.exec(fonte);
  if (achado === null) {
    return 10;
  }
  return Number(achado[1]);
}

/**
 * Carrega o arquivo da arte numa caixa de areia nova, com o que o navegador daria a ele: as letras já prontas
 * (document.fonts.ready) e, para o logo, um fetch e um createImageBitmap de mentira.
 *
 * Recebe: tamanho_do_logo — { width, height } da imagem que o createImageBitmap de mentira devolve.
 * Devolve: a função que pega um nome de dentro do arquivo. Exemplo: pegar("molde_do_canal").
 */
function carregar_a_arte(tamanho_do_logo) {
  // O fetch de mentira: responde que deu certo, com um arquivo qualquer.
  async function fetch_de_mentira() {
    return { ok: true, blob: async function () { return {}; } };
  }
  // O createImageBitmap de mentira: a "imagem" só tem o tamanho.
  async function imagem_de_mentira() {
    return tamanho_do_logo;
  }
  const ambiente = vm.createContext({
    document: { fonts: { ready: Promise.resolve() } },
    fetch: fetch_de_mentira,
    createImageBitmap: imagem_de_mentira,
  });
  // Roda o arquivo da tela dentro da caixa de areia (como se fosse a página carregando o script).
  vm.runInContext(CODIGO_DA_ARTE, ambiente);
  // Pegar um nome (uma função ou uma constante) de dentro da caixa de areia.
  function pegar(nome) {
    return vm.runInContext(nome, ambiente);
  }
  return pegar;
}

/**
 * Um canvas de mentira: guarda o tamanho e os atributos, anota tudo o que o desenho pinta (textos, retângulos e
 * imagens) e mede o texto de um jeito simples (cada letra ocupa LARGURA_DE_UMA_LETRA do tamanho da letra).
 *
 * Recebe: nada. Devolve: { canvas, pintura, atributos }.
 */
function criar_canvas_de_mentira() {
  const pintura = { textos: [], retangulos: [], imagens: [] };
  const contexto = {
    font: "",
    fillStyle: "",
    // A largura do texto com a letra atual.
    measureText: function (texto) {
      return { width: texto.length * tamanho_da_letra(this.font) * LARGURA_DE_UMA_LETRA };
    },
    // Anota o texto pintado: onde (x e a linha de base y), o tamanho da letra e a largura.
    fillText: function (texto, x, y) {
      pintura.textos.push({ texto: texto, x: x, y: y, tamanho: tamanho_da_letra(this.font),
        largura: this.measureText(texto).width });
    },
    // Anota os retângulos pintados, com a cor.
    fillRect: function (x, y, largura, altura) {
      pintura.retangulos.push({ x: x, y: y, largura: largura, altura: altura, cor: this.fillStyle });
    },
    beginPath: function () {},
    // O quadro de cantos arredondados do logo também é anotado como retângulo.
    roundRect: function (x, y, largura, altura) {
      pintura.retangulos.push({ x: x, y: y, largura: largura, altura: altura, cor: this.fillStyle });
    },
    fill: function () {},
    // Anota onde o logo foi desenhado.
    drawImage: function (imagem, x, y, largura, altura) {
      pintura.imagens.push({ x: x, y: y, largura: largura, altura: altura });
    },
  };
  const atributos = {};
  const canvas = {
    width: 300,
    height: 150,
    dataset: {},
    setAttribute: function (nome, valor) {
      atributos[nome] = valor;
    },
    getContext: function () {
      return contexto;
    },
  };
  return { canvas: canvas, pintura: pintura, atributos: atributos };
}

// O kit padrão (sem logo e sem assinatura), com as cores do kit padrão do banco.
const KIT_PADRAO = { nome: "Padrão Santander", marca: "Santander", assinatura: "", cor_principal: "#ec0000",
  cor_escura: "#9b0000", cor_fundo: "#ffffff", cor_texto: "#222222", cor_apoio: "#5c6366", endereco_do_logo: null };

// Um kit próprio sem logo, com uma assinatura comprida (o nome da empresa).
const KIT_COM_ASSINATURA = { nome: "Kit da Cooperativa", marca: "Santander",
  assinatura: "Cooperativa Agroindustrial dos Produtores do Vale Verde", cor_principal: "#0f7b3f",
  cor_escura: "#094d27", cor_fundo: "#f7faf8", cor_texto: "#1b1b1b", cor_apoio: "#4d5a52", endereco_do_logo: null };

// Um kit próprio com logo (o endereço só precisa existir: o fetch é de mentira).
const KIT_COM_LOGO = { nome: "Kit da Metalúrgica", marca: "Santander", assinatura: "Metalúrgica Horizonte",
  cor_principal: "#1d4ed8", cor_escura: "#1e3a8a", cor_fundo: "#ffffff", cor_texto: "#111827", cor_apoio: "#4b5563",
  endereco_do_logo: "/api/banco/empresas/EMP099/kit/logo" };

// Um material curto, como o do WhatsApp.
const MATERIAL_CURTO = {
  titulo: "Sua conta salário chegou",
  blocos: [
    { texto: "Olá, equipe!", fontes: ["Pacote Folha › Conta salário"] },
    { texto: "Receba o salário sem tarifa de manutenção.", fontes: ["Pacote Folha › Conta salário"] },
  ],
};

// Um material comprido, como o do e-mail e do mural, com uma palavra comprida (um endereço de site) na frase.
const MATERIAL_COMPRIDO = {
  titulo: "Comunicado para toda a equipe: os benefícios da nova conta salário e como aproveitar cada um deles já no " +
    "primeiro pagamento do mês",
  blocos: [
    { texto: "Temos uma novidade para contar a todos.", fontes: ["Pacote Folha › Conta salário"] },
    { texto: "A conta salário não cobra tarifa de manutenção, o salário pode ser antecipado em parte quando for " +
      "preciso, o cartão de débito vem sem anuidade e a portabilidade para outro banco é gratuita. Veja todas as " +
      "condições em https://www.exemplo-de-banco-parceiro.com.br/conta-salario/beneficios-da-folha e fale com o RH " +
      "se tiver dúvida sobre como começar a usar os benefícios.",
    fontes: ["Pacote Folha › Conta salário", "Pacote Folha › Salário antecipado", "Pacote Folha › Portabilidade"] },
  ],
};

/**
 * Desenha a arte de um material num canvas de mentira e devolve tudo o que ficou anotado.
 *
 * Recebe: pegar — a função da caixa de areia; material; kit; canal — "email", "mural" ou "whatsapp".
 * Devolve: { canvas, pintura, atributos, textos_da_arte } (textos_da_arte: a lista que a arte anotou no canvas).
 */
async function desenhar_no_canal(pegar, material, kit, canal) {
  const { canvas, pintura, atributos } = criar_canvas_de_mentira();
  const chave_do_molde = pegar("molde_do_canal")(canal);
  await pegar("desenhar_arte_do_material")(canvas, material, kit, chave_do_molde);
  // A lista que a arte anotou (lida aqui fora, com o JSON daqui: dá para comparar com as listas do teste).
  const textos_da_arte = JSON.parse(canvas.dataset.textosDaArte);
  return { canvas: canvas, pintura: pintura, atributos: atributos, textos_da_arte: textos_da_arte };
}

/**
 * Os textos que a arte pode escrever: a marca e a assinatura do kit e, do material, o título, o texto de cada bloco e
 * a fonte de cada bloco, sem o nome do canal entre parênteses.
 *
 * Recebe: pegar; material; kit. Devolve: a lista dos textos permitidos.
 */
function textos_permitidos(pegar, material, kit) {
  const texto_sem_o_canal = pegar("texto_sem_o_canal");
  const permitidos = [kit.marca, texto_sem_o_canal(material.titulo)];
  // A assinatura só quando o kit tem uma.
  if (kit.assinatura) {
    permitidos.push(kit.assinatura);
  }
  // O texto e a fonte de cada bloco.
  for (const bloco of material.blocos) {
    permitidos.push(texto_sem_o_canal(bloco.texto));
    permitidos.push(texto_sem_o_canal("Fonte: " + bloco.fontes.join("; ")));
  }
  return permitidos;
}

// ===== O molde de cada canal =====

test("cada canal tem o seu molde, no tamanho certo", function () {
  const pegar = carregar_a_arte(null);
  const moldes = pegar("MOLDES_DA_ARTE");
  // Canal a canal: o molde escolhido tem a largura e a altura do canal.
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    const molde = moldes[pegar("molde_do_canal")(canal)];
    assert.deepEqual([molde.largura, molde.altura], TAMANHO_DO_CANAL[canal], "canal " + canal);
  }
});

test("o cartaz do mural é o A4 (21 × 29,7 cm) em 150 pontos por polegada", function () {
  const pegar = carregar_a_arte(null);
  const cartaz = pegar("MOLDES_DA_ARTE")[pegar("molde_do_canal")("mural")];
  // Uma polegada tem 25,4 mm: pixels = milímetros ÷ 25,4 × pontos por polegada.
  const largura_do_a4 = Math.round(210 / 25.4 * 150);
  const altura_do_a4 = Math.round(297 / 25.4 * 150);
  assert.deepEqual([cartaz.largura, cartaz.altura], [largura_do_a4, altura_do_a4]);
});

test("cada canal tem um molde diferente, e um canal desconhecido fica com a imagem quadrada", function () {
  const pegar = carregar_a_arte(null);
  const molde_do_canal = pegar("molde_do_canal");
  // Os três canais: três moldes diferentes.
  const moldes_dos_canais = new Set([molde_do_canal("email"), molde_do_canal("mural"), molde_do_canal("whatsapp")]);
  assert.equal(moldes_dos_canais.size, 3);
  // Canal que a tela não conhece: a imagem quadrada, a do WhatsApp.
  assert.equal(molde_do_canal("sms"), molde_do_canal("whatsapp"));
  assert.equal(molde_do_canal(undefined), molde_do_canal("whatsapp"));
});

test("o desenho deixa o canvas no tamanho do canal e anota o molde desenhado", async function () {
  const pegar = carregar_a_arte(null);
  // Canal a canal: o canvas fica com o tamanho real da imagem daquele canal.
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    const desenho = await desenhar_no_canal(pegar, MATERIAL_CURTO, KIT_PADRAO, canal);
    assert.deepEqual([desenho.canvas.width, desenho.canvas.height], TAMANHO_DO_CANAL[canal], "canal " + canal);
    assert.equal(desenho.canvas.dataset.moldeDesenhado, pegar("molde_do_canal")(canal), "canal " + canal);
  }
});

test("a descrição do formato, para a tela, diz o nome e o tamanho (e que o cartaz é para imprimir)", function () {
  const pegar = carregar_a_arte(null);
  const descricao_do_molde = pegar("descricao_do_molde");
  const molde_do_canal = pegar("molde_do_canal");
  assert.equal(descricao_do_molde(molde_do_canal("email")), "Banner para e-mail · 1200 × 400 px");
  assert.equal(descricao_do_molde(molde_do_canal("mural")),
    "Cartaz A4 para mural · 1240 × 1754 px · A4 em 150 dpi, para imprimir");
  assert.equal(descricao_do_molde(molde_do_canal("whatsapp")), "Imagem quadrada para WhatsApp · 1080 × 1080 px");
});

// ===== O texto sem o nome do canal entre parênteses =====

test("o nome do canal entre parênteses sai do texto da arte, em qualquer grafia", function () {
  const texto_sem_o_canal = carregar_a_arte(null)("texto_sem_o_canal");
  // Cada par: o texto que a IA poderia escrever e o que vai para a arte.
  const casos = [
    ["Sua conta salário (E-mail)", "Sua conta salário"],
    ["Sua conta salário (e-mail)", "Sua conta salário"],
    ["Sua conta salário (E-MAIL)", "Sua conta salário"],
    ["Sua conta salário (Email)", "Sua conta salário"],
    ["Sua conta salário (E‑mail)", "Sua conta salário"],
    ["Sua conta salário (Mural)", "Sua conta salário"],
    ["Sua conta salário (Mural ou intranet)", "Sua conta salário"],
    ["Sua conta salário (Intranet)", "Sua conta salário"],
    ["Sua conta salário (WhatsApp)", "Sua conta salário"],
    ["Sua conta salário (whatsapp)", "Sua conta salário"],
    ["Sua conta salário (Whats App)", "Sua conta salário"],
    ["Sua conta salário [WhatsApp]", "Sua conta salário"],
    ["Sua conta salário (versão para o WhatsApp)", "Sua conta salário"],
    ["Sua conta salário ( Zap )", "Sua conta salário"],
    ["(E-mail) Sua conta salário", "Sua conta salário"],
    ["Sua conta (WhatsApp): o que muda", "Sua conta: o que muda"],
    ["Sua conta (Mural) e os benefícios (E-mail)", "Sua conta e os benefícios"],
  ];
  for (const [texto_da_ia, texto_da_arte] of casos) {
    assert.equal(texto_sem_o_canal(texto_da_ia), texto_da_arte, texto_da_ia);
  }
});

test("os outros parênteses e o canal fora de parênteses continuam no texto", function () {
  const texto_sem_o_canal = carregar_a_arte(null)("texto_sem_o_canal");
  // Textos que não mudam: o parêntese não fala de canal, ou o canal faz parte da frase.
  const textos_que_ficam = [
    "Conta salário (sem tarifa)",
    "Comunicado (2026)",
    "Fale com a gente pelo WhatsApp da agência",
    "Veja no mural da empresa",
    "Pagamento pela Zapata (fornecedor)",
    "Fonte: Pacote Folha › Conta salário",
    "",
  ];
  for (const texto of textos_que_ficam) {
    assert.equal(texto_sem_o_canal(texto), texto, texto);
  }
});

test("a arte não escreve o nome do canal entre parênteses, em nenhum molde", async function () {
  const pegar = carregar_a_arte(null);
  // Um material em que a IA pôs o canal no título e na frase.
  const material_com_o_canal = {
    titulo: "Sua conta salário chegou (E-mail)",
    blocos: [
      { texto: "Olá, equipe!", fontes: ["Pacote Folha › Conta salário"] },
      { texto: "Receba o salário sem tarifa (WhatsApp).", fontes: ["Pacote Folha › Conta salário"] },
    ],
  };
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    const desenho = await desenhar_no_canal(pegar, material_com_o_canal, KIT_PADRAO, canal);
    // Nem na lista anotada, nem no que foi pintado.
    for (const texto of desenho.textos_da_arte) {
      assert.ok(!/\((e-mail|whatsapp)\)/i.test(texto), "canal " + canal + ": " + texto);
    }
    for (const pintado of desenho.pintura.textos) {
      assert.ok(!/\((e-mail|whatsapp)\)/i.test(pintado.texto), "canal " + canal + ": " + pintado.texto);
    }
    // O título e a frase continuam, sem o parêntese.
    assert.ok(desenho.textos_da_arte.includes("Sua conta salário chegou"), "canal " + canal);
    assert.ok(desenho.textos_da_arte.includes("Receba o salário sem tarifa."), "canal " + canal);
  }
});

test("um título que é só o nome do canal some da arte, sem deixar um texto vazio", async function () {
  const pegar = carregar_a_arte(null);
  const material_so_com_o_canal = { titulo: "(WhatsApp)", blocos: MATERIAL_CURTO.blocos };
  const desenho = await desenhar_no_canal(pegar, material_so_com_o_canal, KIT_PADRAO, "whatsapp");
  assert.ok(!desenho.textos_da_arte.includes(""));
  assert.ok(!desenho.textos_da_arte.includes("(WhatsApp)"));
});

// ===== Tudo o que a arte escreve vem do material, e fica dentro da imagem =====

test("tudo o que a arte escreve vem do material ou é a marca e a assinatura do kit", async function () {
  const pegar = carregar_a_arte({ width: 400, height: 100 });
  // Todas as combinações: os três canais, os três kits e os dois materiais.
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    for (const kit of [KIT_PADRAO, KIT_COM_ASSINATURA, KIT_COM_LOGO]) {
      for (const material of [MATERIAL_CURTO, MATERIAL_COMPRIDO]) {
        const desenho = await desenhar_no_canal(pegar, material, kit, canal);
        const permitidos = textos_permitidos(pegar, material, kit);
        const caso = "canal " + canal + ", " + kit.nome + ", título \"" + material.titulo.slice(0, 20) + "\"";
        // A lista anotada: só textos permitidos.
        for (const texto of desenho.textos_da_arte) {
          assert.ok(permitidos.includes(texto), caso + ": texto novo na arte: " + texto);
        }
        // O que foi pintado, linha a linha: cada linha é um pedaço de um texto permitido.
        for (const pintado of desenho.pintura.textos) {
          const faz_parte = permitidos.some(function (permitido) {
            return permitido.includes(pintado.texto);
          });
          assert.ok(faz_parte, caso + ": linha pintada que não vem do material: " + pintado.texto);
        }
      }
    }
  }
});

test("todo texto fica dentro da imagem, mesmo com título e frase compridos", async function () {
  const pegar = carregar_a_arte({ width: 400, height: 100 });
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    for (const kit of [KIT_PADRAO, KIT_COM_ASSINATURA, KIT_COM_LOGO]) {
      for (const material of [MATERIAL_CURTO, MATERIAL_COMPRIDO]) {
        const desenho = await desenhar_no_canal(pegar, material, kit, canal);
        const [largura, altura] = TAMANHO_DO_CANAL[canal];
        const caso = "canal " + canal + ", " + kit.nome + ", título \"" + material.titulo.slice(0, 20) + "\"";
        for (const pintado of desenho.pintura.textos) {
          // Da esquerda à direita: começa depois da borda e termina antes da outra (meio pixel de folga no arredondamento).
          assert.ok(pintado.x >= 0 && pintado.x + pintado.largura <= largura + 0.5,
            caso + ": passou da largura: " + pintado.texto);
          // De cima a baixo: o alto das letras (a base menos o tamanho) e a base ficam dentro.
          assert.ok(pintado.y - pintado.tamanho >= 0 && pintado.y <= altura, caso + ": passou da altura: " + pintado.texto);
          // Nenhum texto fica menor que a menor letra da arte.
          assert.ok(pintado.tamanho >= pegar("MENOR_LETRA"), caso + ": letra pequena demais: " + pintado.texto);
        }
      }
    }
  }
});

test("o texto do material fica fora da faixa da marca (e, no banner, fora da coluna da marca)", async function () {
  const pegar = carregar_a_arte({ width: 400, height: 100 });
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    for (const material of [MATERIAL_CURTO, MATERIAL_COMPRIDO]) {
      const desenho = await desenhar_no_canal(pegar, material, KIT_COM_ASSINATURA, canal);
      // O primeiro retângulo depois do fundo é a faixa (ou a coluna) da marca, na cor principal.
      const marca_da_arte = desenho.pintura.retangulos[1];
      assert.equal(marca_da_arte.cor, KIT_COM_ASSINATURA.cor_principal, "canal " + canal);
      // Os textos que não são a marca nem a assinatura: o título, a frase e o rodapé.
      for (const pintado of desenho.pintura.textos) {
        const e_do_kit = [KIT_COM_ASSINATURA.marca, KIT_COM_ASSINATURA.assinatura].some(function (texto_do_kit) {
          return texto_do_kit.includes(pintado.texto);
        });
        if (e_do_kit) {
          continue;
        }
        if (canal === "email") {
          // No banner, o texto começa depois da coluna.
          assert.ok(pintado.x >= marca_da_arte.largura, "banner: texto em cima da coluna: " + pintado.texto);
        } else {
          // Na imagem quadrada e no cartaz, o alto das letras fica abaixo da faixa.
          assert.ok(pintado.y - pintado.tamanho >= marca_da_arte.altura, canal + ": texto na faixa: " + pintado.texto);
        }
      }
    }
  }
});

// ===== O logo =====

test("o logo cabe na faixa de cima (ou na coluna do banner), comprido ou quadrado, e a arte anota que ele entrou",
  async function () {
    // Um logo comprido e um quadrado.
    for (const tamanho_do_logo of [{ width: 800, height: 100 }, { width: 64, height: 64 }]) {
      const pegar = carregar_a_arte(tamanho_do_logo);
      for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
        const desenho = await desenhar_no_canal(pegar, MATERIAL_CURTO, KIT_COM_LOGO, canal);
        const caso = "canal " + canal + ", logo " + tamanho_do_logo.width + " × " + tamanho_do_logo.height;
        assert.equal(desenho.canvas.dataset.arteComLogo, "sim", caso);
        assert.equal(desenho.pintura.imagens.length, 1, caso);
        const logo = desenho.pintura.imagens[0];
        // O lugar do logo: a faixa (ou a coluna) da marca, o primeiro retângulo depois do fundo.
        const marca_da_arte = desenho.pintura.retangulos[1];
        assert.ok(logo.x >= 0 && logo.x + logo.largura <= marca_da_arte.largura, caso + ": passou da largura");
        assert.ok(logo.y >= 0 && logo.y + logo.altura <= marca_da_arte.altura, caso + ": passou da altura");
        // Com logo, a assinatura não é escrita (o nome da empresa já está no logo).
        assert.ok(!desenho.textos_da_arte.includes(KIT_COM_LOGO.assinatura), caso);
      }
    }
  });

test("a imagem quadrada continua o desenho de antes: a faixa de 14% no alto e o logo à direita, no meio da faixa",
  async function () {
    const pegar = carregar_a_arte({ width: 64, height: 64 });
    const desenho = await desenhar_no_canal(pegar, MATERIAL_CURTO, KIT_COM_LOGO, "whatsapp");
    // A faixa: de ponta a ponta, com 14% da altura, na cor principal.
    const faixa = desenho.pintura.retangulos[1];
    assert.deepEqual([faixa.x, faixa.y, faixa.largura, faixa.altura], [0, 0, 1080, Math.round(1080 * 0.14)]);
    assert.equal(faixa.cor, KIT_COM_LOGO.cor_principal);
    // O logo: na metade direita, cobrindo a linha do meio da faixa (o roteiro arte_com_o_kit procura o logo ali).
    const logo = desenho.pintura.imagens[0];
    const meio_da_faixa = Math.floor(faixa.altura / 2);
    assert.ok(logo.x >= 1080 / 2);
    assert.ok(logo.y <= meio_da_faixa && logo.y + logo.altura >= meio_da_faixa);
  });

test("sem logo, a arte anota que o logo não entrou e não desenha imagem", async function () {
  const pegar = carregar_a_arte(null);
  for (const canal of Object.keys(TAMANHO_DO_CANAL)) {
    const desenho = await desenhar_no_canal(pegar, MATERIAL_CURTO, KIT_COM_ASSINATURA, canal);
    assert.equal(desenho.canvas.dataset.arteComLogo, "nao", "canal " + canal);
    assert.equal(desenho.pintura.imagens.length, 0, "canal " + canal);
    // Sem logo, a assinatura do kit próprio aparece.
    assert.ok(desenho.textos_da_arte.includes(KIT_COM_ASSINATURA.assinatura), "canal " + canal);
  }
});

// ===== Vários pedidos de desenho =====

test("com dois pedidos seguidos no mesmo canvas, vale o último (ex.: o rascunho de outro canal aberto no meio)",
  async function () {
    const pegar = carregar_a_arte(null);
    const desenhar = pegar("desenhar_arte_do_material");
    const { canvas } = criar_canvas_de_mentira();
    // Dois pedidos sem esperar o primeiro: o do e-mail e, logo depois, o do mural.
    const primeiro = desenhar(canvas, MATERIAL_CURTO, KIT_PADRAO, pegar("molde_do_canal")("email"));
    const segundo = desenhar(canvas, MATERIAL_CURTO, KIT_PADRAO, pegar("molde_do_canal")("mural"));
    await Promise.all([primeiro, segundo]);
    // Ficou o cartaz A4 do mural.
    assert.deepEqual([canvas.width, canvas.height], TAMANHO_DO_CANAL.mural);
    assert.equal(canvas.dataset.moldeDesenhado, pegar("molde_do_canal")("mural"));
  });
