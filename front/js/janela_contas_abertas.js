/*
  janela_contas_abertas.js — a janela "Carregar Contas Abertas" do Portal Interno.

  Para que serve: o especialista do banco carrega o arquivo de contas abertas DE UMA EMPRESA, que os sistemas do banco
  geram, por uma janela que se abre por cima da tela (bem parecida com a janela em que a empresa manda os
  funcionários). O botão fica na aba "Contas abertas" da ficha de cada empresa: o
  arquivo é sempre de uma empresa só, a da ficha aberta. Desde o ADR-149, o arquivo é
  "cpf;status;agencia;conta;data_abertura", sem o CNPJ: um CPF que não está Cadastrado nesta empresa recusa o arquivo
  inteiro. O status diz o que o banco fez com o funcionário: "1 = Conta nova · 2 = Já era correntista"; a legenda fica
  em destaque na orientação, e a prévia conta as contas novas e os correntistas.

  Como a janela funciona, em 4 etapas:
    1. "escolher": mostra a ORIENTAÇÃO da empresa (o arquivo precisa ser dela), o FORMATO FIXO do arquivo e TODAS as
       conferências que o sistema faz. O texto vem do servidor (/api/banco/empresas/{empresa_id}/contas/layout): a
       tela explica exatamente o que o código confere;
    2. "conferindo": o arquivo vai ao servidor (/api/banco/empresas/{empresa_id}/contas/conferir), que confere o
       layout, cada linha e os CPFs e as contas da empresa;
    3a. "recusado": com QUALQUER divergência, o arquivo inteiro é recusado e nada é gravado. A janela mostra cada
        problema (linha, CPF, o que está errado e como corrigir) e repete a orientação da empresa, para o especialista
        corrigir e carregar de novo;
    3b. "pronto": sem divergência, a prévia mostra quantas contas ganham baixa e o que muda na empresa. Só no
        "Confirmar a baixa" as contas são gravadas (/api/banco/contas/{arquivo_id}/confirmar);
    4. "feito": a baixa foi gravada. A tela de trás é avisada pelo evento "contas-abertas-carregadas", que leva o texto
       do aviso (detail.texto) e a empresa (detail.empresa_id).
  Fechar a janela com uma prévia aberta descarta a prévia (/api/banco/contas/{arquivo_id}/descartar; nada fica pela
  metade).

  Uso numa página: um botão com o atributo data-abrir-carregar-contas e a empresa nos atributos data-empresa-id e
  data-empresa-nome (ex.: data-empresa-id="EMP001" data-empresa-nome="Aurora Alimentos"), e este arquivo carregado.
  Só funciona com o servidor (aberta como arquivo, a janela avisa que precisa dele).
  Depende de: css/banco_ficha.css (o destaque da orientação), carregado na tela Empresas.
*/

// A janela (o <dialog>), criada no primeiro clique e reaproveitada depois.
let janela_de_contas = null;
// A empresa do arquivo: { empresa_id, nome }, recebida ao abrir a janela.
let empresa_da_janela = null;
// O formato do arquivo e a orientação da empresa, como o servidor os descreve (buscados a cada vez que a janela abre).
let layout_de_contas = null;
// A prévia que está na janela: a recusada (para baixar a lista) ou a pronta (para confirmar ou descartar).
let previa_na_janela = null;

/**
 * Cria um elemento com classe e texto (o texto entra sempre como texto puro, nunca como HTML).
 *
 * Recebe: etiqueta ("div", "p"...); classe (ou ""); texto (ou ""). Devolve: o elemento.
 */
function criar_na_janela_de_contas(etiqueta, classe, texto) {
  const elemento = document.createElement(etiqueta);
  // Classe só quando veio uma.
  if (classe) {
    elemento.className = classe;
  }
  // Texto como texto puro: um CPF ou motivo nunca vira código na página.
  if (texto !== "") {
    elemento.textContent = texto;
  }
  return elemento;
}

/**
 * Escolhe entre o singular e o plural pela quantidade.
 *
 * Recebe: quantidade; singular; plural. Devolve: "1 linha" ou "3 linhas".
 */
function quantidade_com_palavra(quantidade, singular, plural) {
  // 1 fica no singular; 0 e 2 em diante, no plural.
  if (quantidade === 1) {
    return "1 " + singular;
  }
  return quantidade + " " + plural;
}

/**
 * Escreve "N (P%)" das contas de uma empresa.
 *
 * Recebe: contas; cadastrados. Devolve: o texto. Exemplo: (20, 35) → "20 (57%)".
 */
function contas_e_percentual_na_janela(contas, cadastrados) {
  // Sem cadastrados, o percentual é 0 (e não uma divisão por zero).
  let percentual = 0;
  if (cadastrados > 0) {
    percentual = Math.round(100 * contas / cadastrados);
  }
  return contas + " (" + percentual + "%)";
}

/**
 * Escreve quantas contas são contas novas e quantas são de correntistas (um grupo só, ADR-149). Só do banco.
 *
 * Recebe: tipos — {nova_conta, correntista}, ou null (arquivo de antes do status). Devolve: o texto. Usado também
 * pela aba da ficha (js/banco_empresas_contas.js). Um arquivo de antes do ADR-149 guardava também a divisão dos
 * correntistas: ela não aparece.
 * Exemplo: {nova_conta: 2, correntista: 1} → "2 contas novas · 1 correntista"; null → "—".
 */
function texto_dos_tipos_de_conta(tipos) {
  // Arquivo antigo, que não guardava o status: um traço (nada é suposto).
  if (!tipos) {
    return "—";
  }
  // As contas novas e os correntistas, no singular ou no plural.
  return quantidade_com_palavra(tipos.nova_conta, "conta nova", "contas novas") + " · " +
    quantidade_com_palavra(tipos.correntista, "correntista", "correntistas");
}

// ===== Montar a janela =====

/**
 * O endereço da API de contas da empresa da janela.
 *
 * Recebe: final — o fim do endereço ("layout" ou "conferir"). Devolve: o endereço.
 * Exemplo: com a empresa "EMP001", "layout" → "/api/banco/empresas/EMP001/contas/layout".
 */
function endereco_de_contas_da_empresa(final) {
  // encodeURIComponent: o código da empresa entra no endereço sem virar outra coisa.
  return "/api/banco/empresas/" + encodeURIComponent(empresa_da_janela.empresa_id) + "/contas/" + final;
}

/**
 * Cria o cabeçalho da janela: o título (que cita a empresa, escrito ao abrir) e o X de fechar.
 *
 * Recebe: nada. Devolve: o elemento do cabeçalho.
 */
function criar_cabecalho_da_janela_de_contas() {
  const cabecalho = criar_na_janela_de_contas("div", "janela-cabecalho", "");
  // Os textos do cabeçalho: o que é e o título (o nome da empresa entra em abrir_janela_de_contas).
  const textos = criar_na_janela_de_contas("div", "janela-cabecalho-textos", "");
  const titulo = criar_na_janela_de_contas("h2", "janela-titulo", "Carregar Contas Abertas");
  titulo.setAttribute("data-titulo-janela-contas", "");
  textos.append(criar_na_janela_de_contas("span", "sobretitulo", "Arquivo de contas abertas do banco"), titulo);
  // O X de fechar (um "×" em texto: esta janela abre em telas com ícones diferentes).
  const fechar = criar_na_janela_de_contas("button", "botao-fechar-janela botao-fechar-janela-texto", "×");
  fechar.type = "button";
  fechar.setAttribute("aria-label", "Fechar");
  fechar.addEventListener("click", fechar_janela_de_contas);
  cabecalho.append(textos, fechar);
  return cabecalho;
}

/**
 * Cria a etapa 1 ("escolher"): a área de arrastar o arquivo, o formato esperado e as conferências.
 *
 * Recebe: nada. Devolve: o elemento da etapa (os blocos do formato são preenchidos por montar_formato_na_janela).
 */
function criar_etapa_escolher() {
  const etapa = criar_na_janela_de_contas("div", "etapa-janela-contas", "");
  etapa.setAttribute("data-etapa-janela-contas", "escolher");
  // A orientação da empresa, em destaque, antes de tudo (preenchida quando o layout chega do servidor).
  const orientacao = criar_bloco_de_orientacao();
  orientacao.setAttribute("data-orientacao-janela-contas", "");
  etapa.append(orientacao);
  // A regra principal, logo no alto.
  etapa.append(criar_na_janela_de_contas("p", "janela-resumo",
    "O layout do arquivo é fixo. Se algo estiver fora do formato abaixo, ou se o sistema achar qualquer divergência, " +
    "o arquivo inteiro é recusado e nada é gravado, até você corrigir e carregar de novo."));
  // A área de arrastar (o mesmo visual da janela de envio da empresa).
  const zona = criar_na_janela_de_contas("div", "zona-envio zona-envio-janela-contas", "");
  zona.setAttribute("data-zona-arquivo-contas", "");
  zona.append(criar_na_janela_de_contas("h3", "zona-envio-titulo", "Arraste o arquivo .csv para cá"));
  // O <label> abre a janela do sistema para escolher o arquivo (o campo em si fica escondido).
  const botao_escolher = criar_na_janela_de_contas("label", "botao botao-principal", "Escolher arquivo");
  botao_escolher.htmlFor = "campo-arquivo-contas-janela";
  const campo = criar_na_janela_de_contas("input", "", "");
  campo.type = "file";
  campo.id = "campo-arquivo-contas-janela";
  campo.accept = ".csv";
  campo.hidden = true;
  campo.setAttribute("data-campo-arquivo-contas-janela", "");
  // Escolheu o arquivo: vai direto para a conferência.
  campo.addEventListener("change", function () {
    if (campo.files.length > 0) {
      conferir_arquivo_na_janela(campo.files[0]);
    }
  });
  zona.append(botao_escolher, campo,
    criar_na_janela_de_contas("p", "zona-envio-formatos", "Só .csv separado por ponto e vírgula (;)"));
  ligar_arrastar_e_soltar(zona);
  // Os dois blocos de explicação, lado a lado em tela larga: o formato e as conferências.
  const explicacao = criar_na_janela_de_contas("div", "explicacao-contas", "");
  const bloco_formato = criar_na_janela_de_contas("section", "bloco-explicacao-contas", "");
  bloco_formato.setAttribute("data-formato-contas", "");
  bloco_formato.append(criar_na_janela_de_contas("p", "", "Carregando o formato do arquivo…"));
  const bloco_conferencias = criar_na_janela_de_contas("section", "bloco-explicacao-contas", "");
  bloco_conferencias.setAttribute("data-conferencias-contas", "");
  explicacao.append(bloco_formato, bloco_conferencias);
  etapa.append(zona, explicacao);
  return etapa;
}

/**
 * Cria o bloco da orientação da empresa: o título, o texto e a legenda do status (o mesmo destaque da aba da ficha).
 *
 * Recebe: nada. Devolve: o elemento do bloco, com o texto "Carregando…" até o layout chegar.
 */
function criar_bloco_de_orientacao() {
  // O bloco em destaque (css/banco_ficha.css).
  const bloco = criar_na_janela_de_contas("section", "orientacao-contas orientacao-janela-contas", "");
  // O título e o texto.
  bloco.append(criar_na_janela_de_contas("h3", "ficha-grupo-titulo", "O arquivo precisa ser desta empresa"));
  const texto = criar_na_janela_de_contas("p", "orientacao-contas-texto", "Carregando a orientação…");
  texto.setAttribute("data-texto-orientacao", "");
  // A legenda do status, em destaque (preenchida com a do servidor).
  const status = criar_na_janela_de_contas("p", "orientacao-contas-tipos", "Status em cada linha: ");
  const legenda = criar_na_janela_de_contas("strong", "", "");
  legenda.setAttribute("data-legenda-orientacao", "");
  status.append(legenda);
  bloco.append(texto, status);
  return bloco;
}

/**
 * Preenche um bloco de orientação com o texto e a legenda do status que vieram do servidor.
 *
 * Recebe: bloco — o de criar_bloco_de_orientacao; layout — da empresa. Devolve: nada.
 */
function preencher_bloco_de_orientacao(bloco, layout) {
  // O texto, exatamente como o servidor o escreve (a tela diz o que o código confere).
  bloco.querySelector("[data-texto-orientacao]").textContent = layout.orientacao_da_empresa;
  // A legenda do status, como o servidor a escreve ("1 = Conta nova · 2 = Já era correntista").
  bloco.querySelector("[data-legenda-orientacao]").textContent = layout.legenda_do_status;
}

/**
 * Cria uma etapa vazia (as etapas 2, 3 e 4 são preenchidas quando o servidor responde).
 *
 * Recebe: nome — "conferindo", "recusado", "pronto" ou "feito". Devolve: o elemento da etapa.
 */
function criar_etapa_vazia(nome) {
  const etapa = criar_na_janela_de_contas("div", "etapa-janela-contas", "");
  etapa.setAttribute("data-etapa-janela-contas", nome);
  etapa.hidden = true;
  return etapa;
}

/**
 * Cria a janela inteira (escondida) e a põe no fim da página.
 *
 * Recebe: nada. Devolve: a janela.
 */
function criar_janela_de_contas() {
  const janela = criar_na_janela_de_contas("dialog", "janela-beneficio janela-contas-abertas", "");
  janela.setAttribute("aria-label", "Carregar Contas Abertas");
  janela.setAttribute("data-janela-contas-abertas", "");
  // O bloco interno com o espaçamento e as etapas.
  const conteudo = criar_na_janela_de_contas("div", "janela-conteudo", "");
  conteudo.append(criar_cabecalho_da_janela_de_contas(), criar_etapa_escolher());
  for (const nome of ["conferindo", "recusado", "pronto", "feito"]) {
    conteudo.append(criar_etapa_vazia(nome));
  }
  janela.append(conteudo);
  // A tecla Esc fecha pelo mesmo caminho do X (que descarta a prévia aberta).
  janela.addEventListener("cancel", function (evento) {
    evento.preventDefault();
    fechar_janela_de_contas();
  });
  document.body.append(janela);
  return janela;
}

/**
 * Mostra uma etapa da janela e esconde as outras.
 *
 * Recebe: nome — "escolher", "conferindo", "recusado", "pronto" ou "feito". Devolve: o elemento da etapa mostrada.
 */
function mostrar_etapa_da_janela(nome) {
  let etapa_mostrada = null;
  for (const etapa of janela_de_contas.querySelectorAll("[data-etapa-janela-contas]")) {
    // Só a etapa pedida fica à mostra.
    etapa.hidden = etapa.getAttribute("data-etapa-janela-contas") !== nome;
    if (!etapa.hidden) {
      etapa_mostrada = etapa;
    }
  }
  // Volta ao alto da janela, para a pessoa ler a etapa desde o começo.
  janela_de_contas.scrollTop = 0;
  return etapa_mostrada;
}

/**
 * Liga a área de arrastar: soltar o arquivo nela é o mesmo que escolher pelo botão.
 *
 * Recebe: zona — a área tracejada. Devolve: nada.
 */
function ligar_arrastar_e_soltar(zona) {
  // Com o arquivo passando por cima, a área se destaca (e o navegador não abre o arquivo numa aba).
  zona.addEventListener("dragover", function (evento) {
    evento.preventDefault();
    zona.classList.add("arrastando");
  });
  // Saiu de cima sem soltar: volta ao normal.
  zona.addEventListener("dragleave", function () {
    zona.classList.remove("arrastando");
  });
  // Soltou: confere o primeiro arquivo.
  zona.addEventListener("drop", function (evento) {
    evento.preventDefault();
    zona.classList.remove("arrastando");
    if (evento.dataTransfer.files.length > 0) {
      conferir_arquivo_na_janela(evento.dataTransfer.files[0]);
    }
  });
}

// ===== Etapa 1: o formato e as conferências (vêm do servidor) =====

/**
 * Monta a tabela das colunas do arquivo: coluna, o que é, formato e exemplo.
 *
 * Recebe: colunas — a lista do layout. Devolve: o elemento da tabela (dentro de uma área que rola de lado).
 */
function montar_tabela_das_colunas(colunas) {
  const area = criar_na_janela_de_contas("div", "tabela-rolavel", "");
  const tabela = criar_na_janela_de_contas("table", "tabela-montada tabela-formato-contas", "");
  // O cabeçalho da tabela.
  const cabecalho = criar_na_janela_de_contas("tr", "", "");
  for (const titulo of ["Ordem", "Coluna", "O que é", "Formato", "Exemplo"]) {
    const celula = criar_na_janela_de_contas("th", "", titulo);
    celula.scope = "col";
    cabecalho.append(celula);
  }
  const thead = criar_na_janela_de_contas("thead", "", "");
  thead.append(cabecalho);
  // Uma linha por coluna do arquivo, na ordem em que ela tem de vir.
  const corpo = criar_na_janela_de_contas("tbody", "", "");
  let ordem = 1;
  for (const coluna of colunas) {
    const linha = criar_na_janela_de_contas("tr", "", "");
    const celula_nome = criar_na_janela_de_contas("td", "", "");
    celula_nome.append(criar_na_janela_de_contas("code", "", coluna.nome));
    const celula_exemplo = criar_na_janela_de_contas("td", "", "");
    celula_exemplo.append(criar_na_janela_de_contas("code", "", coluna.exemplo));
    linha.append(criar_na_janela_de_contas("td", "", String(ordem)), celula_nome,
      criar_na_janela_de_contas("td", "", coluna.titulo), criar_na_janela_de_contas("td", "", coluna.formato),
      celula_exemplo);
    corpo.append(linha);
    ordem = ordem + 1;
  }
  tabela.append(thead, corpo);
  area.append(tabela);
  return area;
}

/**
 * Preenche o bloco "Formato do arquivo esperado": extensão, separador, cabeçalho exato, colunas e um exemplo.
 *
 * Recebe: layout — de /api/banco/empresas/{empresa_id}/contas/layout. Devolve: nada.
 */
function montar_formato_na_janela(layout) {
  const bloco = janela_de_contas.querySelector("[data-formato-contas]");
  bloco.replaceChildren();
  bloco.append(criar_na_janela_de_contas("h3", "titulo-explicacao-contas", "Formato do arquivo esperado"));
  // As regras do arquivo como um todo.
  const regras = criar_na_janela_de_contas("ul", "lista-regras-contas", "");
  regras.append(criar_na_janela_de_contas("li", "", "Arquivo " + layout.extensao + ", com os valores separados por " +
    "ponto e vírgula (" + layout.separador + ")."));
  // Um arquivo por empresa: a da ficha aberta (o arquivo não traz o CNPJ; os CPFs precisam estar Cadastrados nela).
  regras.append(criar_na_janela_de_contas("li", "", "Um arquivo por empresa: este é o da " + empresa_da_janela.nome +
    ", e cada CPF precisa estar Cadastrado nela."));
  // O status: o que o banco fez com cada funcionário (a legenda do servidor, em negrito).
  const regra_do_status = criar_na_janela_de_contas("li", "", "Em toda linha, o status: ");
  regra_do_status.setAttribute("data-regra-status", "");
  regra_do_status.append(criar_na_janela_de_contas("strong", "", layout.legenda_do_status),
    document.createTextNode(". No status 2, a agência, a conta salário e a data são as da conta que o funcionário " +
      "já tinha. A data vem como ano-mês-dia (AAAA-MM-DD)."));
  regras.append(regra_do_status);
  regras.append(criar_na_janela_de_contas("li", "", "A 1ª linha é o cabeçalho, exatamente assim, com as " +
    layout.colunas.length + " colunas nesta ordem:"));
  bloco.append(regras, criar_na_janela_de_contas("pre", "codigo-layout-contas", layout.cabecalho));
  // As colunas, uma por linha, com o formato de cada uma.
  bloco.append(montar_tabela_das_colunas(layout.colunas));
  // Um exemplo de arquivo pronto: o cabeçalho e as linhas de exemplo.
  bloco.append(criar_na_janela_de_contas("p", "rotulo-exemplo-contas", "Exemplo de arquivo certo:"));
  let exemplo = layout.cabecalho;
  for (const linha of layout.exemplo_de_linhas) {
    exemplo = exemplo + "\n" + linha;
  }
  bloco.append(criar_na_janela_de_contas("pre", "codigo-layout-contas", exemplo));
  // O modelo para baixar: o mesmo exemplo, num arquivo .csv.
  const baixar = criar_na_janela_de_contas("button", "botao botao-contorno botao-pequeno", "Baixar o modelo (.csv)");
  baixar.type = "button";
  baixar.setAttribute("data-baixar-modelo-contas", "");
  baixar.addEventListener("click", function () {
    baixar_arquivo_de_texto("modelo_contas_abertas.csv", exemplo + "\n");
  });
  bloco.append(baixar);
}

/**
 * Monta a lista de um grupo de conferências (ex.: "No arquivo").
 *
 * Recebe: titulo_do_grupo; validacoes — as do grupo. Devolve: o elemento do grupo.
 */
function montar_grupo_de_conferencias(titulo_do_grupo, validacoes) {
  const grupo = criar_na_janela_de_contas("div", "grupo-conferencias-contas", "");
  grupo.append(criar_na_janela_de_contas("h4", "", titulo_do_grupo));
  const lista = criar_na_janela_de_contas("ul", "lista-conferencias-contas", "");
  for (const validacao of validacoes) {
    // O título em negrito e a descrição do que é conferido.
    const item = criar_na_janela_de_contas("li", "", "");
    item.setAttribute("data-conferencia", validacao.tipo);
    item.append(criar_na_janela_de_contas("strong", "", validacao.titulo),
      document.createTextNode(": " + validacao.descricao));
    lista.append(item);
  }
  grupo.append(lista);
  return grupo;
}

/**
 * Separa as conferências de um grupo (ex.: "arquivo", "linha" ou "carteira") e se travam ou só avisam.
 *
 * Recebe: validacoes; grupo; trava (true ou false). Devolve: a lista filtrada.
 */
function conferencias_do_grupo(validacoes, grupo, trava) {
  const escolhidas = [];
  for (const validacao of validacoes) {
    if (validacao.grupo === grupo && validacao.trava === trava) {
      escolhidas.push(validacao);
    }
  }
  return escolhidas;
}

// Os nomes dos grupos de conferência que a tela conhece, na ordem em que o sistema confere.
const NOMES_DOS_GRUPOS_DE_CONFERENCIA = [
  ["arquivo", "No arquivo"],
  ["empresa", "A empresa do arquivo"],
  ["linha", "Em cada linha"],
  ["carteira", "Com a empresa e os cadastros dela"],
];

/**
 * Lista os grupos das conferências, com o nome de cada um: os conhecidos na ordem certa e, no fim, os que o servidor
 * mandar e a tela ainda não conhece (com o próprio código como nome).
 *
 * Recebe: validacoes — as do layout. Devolve: [[grupo, nome], ...].
 * Exemplo: validações dos grupos "linha" e "arquivo" → [["arquivo", "No arquivo"], ["linha", "Em cada linha"]].
 */
function grupos_das_conferencias(validacoes) {
  // Os grupos que aparecem nas validações do servidor.
  const grupos_presentes = [];
  for (const validacao of validacoes) {
    if (!grupos_presentes.includes(validacao.grupo)) {
      grupos_presentes.push(validacao.grupo);
    }
  }
  // Primeiro os conhecidos, na ordem da tela.
  const grupos = [];
  const conhecidos = [];
  for (const grupo_conhecido of NOMES_DOS_GRUPOS_DE_CONFERENCIA) {
    conhecidos.push(grupo_conhecido[0]);
    if (grupos_presentes.includes(grupo_conhecido[0])) {
      grupos.push(grupo_conhecido);
    }
  }
  // Depois os que a tela não conhece, com o código como nome.
  for (const grupo_presente of grupos_presentes) {
    if (!conhecidos.includes(grupo_presente)) {
      grupos.push([grupo_presente, grupo_presente]);
    }
  }
  // Devolve a lista na ordem de mostrar.
  return grupos;
}

/**
 * Preenche o bloco "O que o sistema confere": as conferências que recusam o arquivo e as que só avisam.
 *
 * Recebe: layout — de /api/banco/empresas/{empresa_id}/contas/layout. Devolve: nada.
 */
function montar_conferencias_na_janela(layout) {
  const bloco = janela_de_contas.querySelector("[data-conferencias-contas]");
  bloco.replaceChildren();
  bloco.append(criar_na_janela_de_contas("h3", "titulo-explicacao-contas", "O que o sistema confere"));
  bloco.append(criar_na_janela_de_contas("p", "aviso-trava-contas",
    "Qualquer um destes problemas recusa o arquivo inteiro. Nada é gravado até você corrigir e carregar de novo."));
  // Os grupos que travam, na ordem em que o sistema confere (os conhecidos primeiro; um grupo novo do servidor entra
  // no fim com o próprio nome, para nenhuma conferência ficar sem explicação na tela).
  const grupos = grupos_das_conferencias(layout.validacoes);
  for (const grupo of grupos) {
    const validacoes = conferencias_do_grupo(layout.validacoes, grupo[0], true);
    if (validacoes.length > 0) {
      bloco.append(montar_grupo_de_conferencias(grupo[1], validacoes));
    }
  }
  // O que só avisa (não recusa o arquivo), de todos os grupos.
  const avisos = [];
  for (const grupo of grupos) {
    for (const validacao of conferencias_do_grupo(layout.validacoes, grupo[0], false)) {
      avisos.push(validacao);
    }
  }
  if (avisos.length > 0) {
    bloco.append(montar_grupo_de_conferencias("Só avisa (não recusa o arquivo)", avisos));
  }
}

/**
 * Busca no servidor o formato do arquivo e a orientação da empresa da janela, e preenche a etapa 1.
 *
 * Recebe: nada. Devolve: nada. Sem servidor: um aviso no lugar do formato (nunca um formato inventado).
 * Busca a cada abertura: a orientação muda de uma empresa para outra.
 */
async function carregar_formato_de_contas() {
  // A empresa desta busca (se a janela for reaberta para outra empresa no meio, a resposta antiga não desenha).
  const empresa_desta_busca = empresa_da_janela;
  // O que o servidor mandou (ou null, se não respondeu).
  let layout = null;
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  try {
    const resposta = await fetch(endereco_de_contas_da_empresa("layout"));
    // Recusado (ex.: empresa que não existe): segue para o aviso.
    if (resposta.ok) {
      layout = await resposta.json();
    }
  } catch (erro) {
    layout = null;
  }
  // A janela foi reaberta para outra empresa enquanto esperava: não desenha.
  if (empresa_desta_busca !== empresa_da_janela) {
    return;
  }
  // Sem resposta: o aviso no lugar do formato e da orientação.
  if (!layout) {
    const bloco = janela_de_contas.querySelector("[data-formato-contas]");
    bloco.replaceChildren(criar_na_janela_de_contas("p", "aviso-trava-contas",
      "Não foi possível carregar o formato do arquivo agora. Feche a janela e tente de novo."));
    janela_de_contas.querySelector("[data-orientacao-janela-contas] [data-texto-orientacao]").textContent =
      "Não foi possível carregar a orientação agora.";
    janela_de_contas.querySelector("[data-orientacao-janela-contas] [data-legenda-orientacao]").textContent = "—";
    return;
  }
  // Guarda o layout (a recusa repete a orientação) e preenche a etapa 1.
  layout_de_contas = layout;
  preencher_bloco_de_orientacao(janela_de_contas.querySelector("[data-orientacao-janela-contas]"), layout);
  montar_formato_na_janela(layout);
  montar_conferencias_na_janela(layout);
}

// ===== Etapa 2: mandar o arquivo =====

/**
 * Manda o arquivo ao servidor e mostra a recusa (com cada divergência) ou a prévia pronta para confirmar.
 *
 * Recebe: arquivo — o File escolhido ou solto na área. Devolve: nada.
 */
async function conferir_arquivo_na_janela(arquivo) {
  // A etapa "conferindo", com o nome do arquivo.
  const etapa = mostrar_etapa_da_janela("conferindo");
  etapa.replaceChildren(criar_na_janela_de_contas("p", "texto-conferindo-contas",
    "Conferindo " + arquivo.name + ": o layout, cada linha e os CPFs e as contas da " + empresa_da_janela.nome +
    "…"));
  // O campo volta a vazio: escolher o mesmo arquivo corrigido de novo dispara a conferência outra vez.
  janela_de_contas.querySelector("[data-campo-arquivo-contas-janela]").value = "";
  const formulario = new FormData();
  formulario.append("arquivo", arquivo);
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  let dados = null;
  try {
    const resposta = await fetch(endereco_de_contas_da_empresa("conferir"), { method: "POST", body: formulario });
    dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro_na_janela("Não foi possível conferir o arquivo: " + dados.detail);
      return;
    }
  } catch (erro) {
    mostrar_erro_na_janela("Sem conexão com o servidor. Tente de novo.");
    return;
  }
  previa_na_janela = dados;
  // Com divergência, recusa; sem, a prévia para confirmar.
  if (dados.pode_importar) {
    mostrar_previa_pronta(dados);
  } else {
    mostrar_recusa(dados);
  }
}

/**
 * Mostra um erro que não é do conteúdo do arquivo (ex.: sem conexão) e o botão de tentar de novo.
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_erro_na_janela(texto) {
  const etapa = mostrar_etapa_da_janela("conferindo");
  etapa.replaceChildren(criar_na_janela_de_contas("p", "aviso-contas aviso-contas-recusado", texto),
    criar_botao_de_voltar("Tentar de novo"));
}

/**
 * Cria o botão que volta à etapa 1 (para carregar o arquivo corrigido).
 *
 * Recebe: texto do botão. Devolve: o botão.
 */
function criar_botao_de_voltar(texto) {
  const botao = criar_na_janela_de_contas("button", "botao botao-principal", texto);
  botao.type = "button";
  botao.setAttribute("data-voltar-a-escolher", "");
  botao.addEventListener("click", function () {
    previa_na_janela = null;
    mostrar_etapa_da_janela("escolher");
  });
  return botao;
}

// ===== Etapa 3a: o arquivo recusado =====

/**
 * Monta a tabela das divergências: linha, CPF, o problema e como corrigir.
 *
 * Recebe: divergencias — a lista da prévia. Devolve: o elemento (numa área que rola).
 */
function montar_tabela_de_divergencias(divergencias) {
  // O título fica congelado no alto enquanto a lista rola
  const area = criar_na_janela_de_contas("div", "tabela-rolavel tabela-divergencias-contas tabela-com-titulo-fixo", "");
  const tabela = criar_na_janela_de_contas("table", "tabela-montada", "");
  // O cabeçalho.
  const cabecalho = criar_na_janela_de_contas("tr", "", "");
  for (const titulo of ["Linha", "CPF", "Problema", "Como corrigir"]) {
    const celula = criar_na_janela_de_contas("th", "", titulo);
    celula.scope = "col";
    cabecalho.append(celula);
  }
  const thead = criar_na_janela_de_contas("thead", "", "");
  thead.append(cabecalho);
  // Uma linha por divergência (a linha 0 é o arquivo inteiro, que nem deu para ler).
  const corpo = criar_na_janela_de_contas("tbody", "", "");
  corpo.setAttribute("data-divergencias-contas", "");
  for (const divergencia of divergencias) {
    let numero_da_linha = String(divergencia.linha);
    if (divergencia.linha === 0) {
      numero_da_linha = "arquivo";
    }
    const linha = criar_na_janela_de_contas("tr", "", "");
    linha.setAttribute("data-tipo", divergencia.tipo);
    linha.append(criar_na_janela_de_contas("td", "", numero_da_linha),
      criar_na_janela_de_contas("td", "celula-cpf", divergencia.cpf || "—"),
      criar_na_janela_de_contas("td", "", divergencia.motivo),
      criar_na_janela_de_contas("td", "", divergencia.como_corrigir));
    corpo.append(linha);
  }
  tabela.append(thead, corpo);
  area.append(tabela);
  return area;
}

/**
 * Soma quantas divergências o arquivo teve (pela contagem por tipo, que conta todas, mesmo além das mostradas).
 *
 * Recebe: previa. Devolve: o total.
 */
function total_de_divergencias(previa) {
  let total = 0;
  for (const tipo of previa.divergencias_por_tipo) {
    total = total + tipo.quantidade;
  }
  return total;
}

/**
 * Mostra a recusa: o total, a contagem por tipo, a tabela com cada problema e os botões.
 *
 * Recebe: previa — da API, com pode_importar = false. Devolve: nada.
 */
function mostrar_recusa(previa) {
  const etapa = mostrar_etapa_da_janela("recusado");
  const total = total_de_divergencias(previa);
  // O aviso vermelho: recusado, nada gravado, o que fazer.
  etapa.replaceChildren(criar_na_janela_de_contas("p", "aviso-contas aviso-contas-recusado",
    "Arquivo recusado: " + quantidade_com_palavra(total, "divergência encontrada", "divergências encontradas") +
    " em " + previa.nome_arquivo + ". Nenhuma conta foi gravada. Corrija o arquivo e carregue de novo."));
  etapa.firstChild.setAttribute("data-aviso-recusa", "");
  // A orientação da empresa, repetida: o arquivo de outra empresa (ou com CPF que não é daqui) cai aqui.
  if (layout_de_contas) {
    const orientacao = criar_bloco_de_orientacao();
    orientacao.setAttribute("data-orientacao-na-recusa", "");
    preencher_bloco_de_orientacao(orientacao, layout_de_contas);
    etapa.append(orientacao);
  }
  // A contagem por tipo, em etiquetas.
  const etiquetas = criar_na_janela_de_contas("ul", "etiquetas-divergencias-contas", "");
  for (const tipo of previa.divergencias_por_tipo) {
    etiquetas.append(criar_na_janela_de_contas("li", "selo selo-atencao", tipo.titulo + ": " + tipo.quantidade));
  }
  etapa.append(etiquetas, montar_tabela_de_divergencias(previa.divergencias));
  // Muitas divergências: a tabela mostra só as primeiras (o servidor limita), e diz isso.
  if (previa.divergencias.length < total) {
    etapa.append(criar_na_janela_de_contas("p", "nota-tabela", "Mostrando as primeiras " +
      previa.divergencias.length + " de " + total + ". Corrija estas e carregue de novo para ver as demais."));
  }
  // Os botões: baixar a lista (para quem gera o arquivo corrigir) e carregar o arquivo corrigido.
  const botoes = criar_na_janela_de_contas("div", "janela-botoes", "");
  const baixar = criar_na_janela_de_contas("button", "botao botao-contorno", "Baixar a lista de divergências (.csv)");
  baixar.type = "button";
  baixar.addEventListener("click", baixar_lista_de_divergencias);
  botoes.append(baixar, criar_botao_de_voltar("Carregar o arquivo corrigido"));
  etapa.append(botoes);
}

/**
 * Tira do texto o que quebraria uma célula do .csv (o ponto e vírgula e as quebras de linha).
 *
 * Recebe: texto. Devolve: o texto limpo. Ex.: "a; b" → "a, b".
 */
function texto_para_celula_csv(texto) {
  return String(texto || "").replaceAll(";", ",").replaceAll("\n", " ");
}

/**
 * Baixa a lista de divergências da recusa na tela, em .csv (linha, CPF, problema, como corrigir).
 *
 * Recebe: nada. Devolve: nada.
 */
function baixar_lista_de_divergencias() {
  if (!previa_na_janela) {
    return;
  }
  let conteudo = "linha;cpf;problema;como_corrigir\n";
  for (const divergencia of previa_na_janela.divergencias) {
    conteudo = conteudo + divergencia.linha + ";" + texto_para_celula_csv(divergencia.cpf) + ";" +
      texto_para_celula_csv(divergencia.motivo) + ";" + texto_para_celula_csv(divergencia.como_corrigir) + "\n";
  }
  baixar_arquivo_de_texto("divergencias_contas_abertas.csv", conteudo);
}

/**
 * Faz o navegador baixar um texto como arquivo.
 *
 * Recebe: nome_do_arquivo; conteudo. Devolve: nada.
 * O "﻿" no começo (a marca de UTF-8) faz o Excel abrir os acentos certos.
 */
function baixar_arquivo_de_texto(nome_do_arquivo, conteudo) {
  const arquivo = new Blob(["﻿" + conteudo], { type: "text/csv;charset=utf-8" });
  // Um link temporário, clicado pelo código e jogado fora.
  const link = document.createElement("a");
  link.href = URL.createObjectURL(arquivo);
  link.download = nome_do_arquivo;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

// ===== Etapa 3b: a prévia pronta para confirmar =====

/**
 * Cria um número grande da prévia (ex.: "38 contas novas").
 *
 * Recebe: valor; texto; classe_extra. Devolve: o elemento.
 */
function criar_numero_da_previa(valor, texto, classe_extra) {
  const bloco = criar_na_janela_de_contas("div", "mini-numero " + classe_extra, "");
  bloco.append(criar_na_janela_de_contas("strong", "", String(valor)), criar_na_janela_de_contas("span", "", texto));
  return bloco;
}

/**
 * Monta a tabela do que muda em cada empresa: cadastrados, contas antes, novas e depois.
 *
 * Recebe: por_empresa — da prévia (a última linha é a "Carteira"). Devolve: o elemento.
 */
function montar_tabela_por_empresa(por_empresa) {
  const area = criar_na_janela_de_contas("div", "tabela-rolavel", "");
  const tabela = criar_na_janela_de_contas("table", "tabela-montada", "");
  const cabecalho = criar_na_janela_de_contas("tr", "", "");
  for (const titulo of ["Empresa", "Cadastrados", "Contas antes", "Novas", "Contas depois"]) {
    const celula = criar_na_janela_de_contas("th", "", titulo);
    celula.scope = "col";
    cabecalho.append(celula);
  }
  const thead = criar_na_janela_de_contas("thead", "", "");
  thead.append(cabecalho);
  const corpo = criar_na_janela_de_contas("tbody", "", "");
  for (const empresa of por_empresa) {
    const linha = criar_na_janela_de_contas("tr", "", "");
    // A linha da carteira inteira fica em destaque.
    if (empresa.empresa === "Carteira") {
      linha.className = "linha-total";
    }
    linha.append(criar_na_janela_de_contas("td", "", empresa.empresa),
      criar_na_janela_de_contas("td", "", String(empresa.cadastrados)),
      criar_na_janela_de_contas("td", "", contas_e_percentual_na_janela(empresa.antes, empresa.cadastrados)),
      criar_na_janela_de_contas("td", "celula-novas", "+" + empresa.novas),
      criar_na_janela_de_contas("td", "", contas_e_percentual_na_janela(empresa.depois, empresa.cadastrados)));
    corpo.append(linha);
  }
  tabela.append(thead, corpo);
  area.append(tabela);
  return area;
}

/**
 * Conta os avisos de um tipo (ex.: "ja_tinha_conta", as linhas ignoradas).
 *
 * Recebe: avisos — da prévia; tipo. Devolve: quantos avisos são desse tipo.
 */
function quantidade_de_avisos_do_tipo(avisos, tipo) {
  let quantidade = 0;
  for (const aviso of avisos) {
    if (aviso.tipo === tipo) {
      quantidade = quantidade + 1;
    }
  }
  return quantidade;
}

/**
 * Monta a lista dos avisos: as linhas ignoradas (a mesma conta já estava gravada) e as contas antigas, gravadas sem
 * o status, que ganham o status deste arquivo.
 *
 * Recebe: avisos — da prévia. Devolve: o elemento <details> (fechado), ou null sem avisos.
 * Exemplo de título: "Ver 3 linhas ignoradas (a mesma conta já estava gravada) e 1 conta antiga que ganha o status".
 */
function montar_lista_de_avisos(avisos) {
  if (avisos.length === 0) {
    return null;
  }
  // As partes do título, só dos tipos de aviso que apareceram.
  const partes = [];
  const ignoradas = quantidade_de_avisos_do_tipo(avisos, "ja_tinha_conta");
  if (ignoradas > 0) {
    partes.push(quantidade_com_palavra(ignoradas, "linha ignorada", "linhas ignoradas") +
      " (a mesma conta já estava gravada)");
  }
  const completadas = quantidade_de_avisos_do_tipo(avisos, "status_completado");
  if (completadas > 0) {
    partes.push(quantidade_com_palavra(completadas, "conta antiga que ganha o status",
      "contas antigas que ganham o status"));
  }
  const detalhes = criar_na_janela_de_contas("details", "detalhes-linhas-fora", "");
  detalhes.append(criar_na_janela_de_contas("summary", "", "Ver " + partes.join(" e ")));
  const lista = criar_na_janela_de_contas("ul", "lista-linhas-fora", "");
  for (const aviso of avisos) {
    const item = criar_na_janela_de_contas("li", "", "");
    item.append(criar_na_janela_de_contas("strong", "", "Linha " + aviso.linha + " · " + aviso.cpf),
      document.createTextNode(" · " + aviso.motivo));
    lista.append(item);
  }
  detalhes.append(lista);
  return detalhes;
}

/**
 * Mostra a prévia sem divergência: os números, os avisos, o que muda por empresa e os botões de decidir.
 *
 * Recebe: previa — da API, com pode_importar = true. Devolve: nada.
 */
function mostrar_previa_pronta(previa) {
  const etapa = mostrar_etapa_da_janela("pronto");
  // O aviso verde: o arquivo passou em todas as conferências.
  etapa.replaceChildren(criar_na_janela_de_contas("p", "aviso-contas aviso-contas-certo",
    previa.nome_arquivo + ": " + quantidade_com_palavra(previa.linhas, "linha conferida", "linhas conferidas") +
    ", nenhuma divergência. Nada foi gravado ainda: confira e confirme a baixa."));
  // Os números: contas que ganham baixa, divididas em contas novas e correntistas, e as ignoradas.
  const tipos = previa.tipos_das_novas;
  const numeros = criar_na_janela_de_contas("div", "mini-numeros", "");
  const numero_das_novas_contas = criar_numero_da_previa(tipos.nova_conta, "contas novas (status 1)", "");
  numero_das_novas_contas.setAttribute("data-previa-novas-contas", "");
  const numero_dos_correntistas = criar_numero_da_previa(tipos.correntista, "já eram correntistas (status 2)", "");
  numero_dos_correntistas.setAttribute("data-previa-correntistas", "");
  numeros.append(criar_numero_da_previa(previa.novas, "contas vão ganhar baixa", "mini-numero-sucesso"),
    numero_das_novas_contas, numero_dos_correntistas,
    criar_numero_da_previa(quantidade_de_avisos_do_tipo(previa.avisos, "ja_tinha_conta"),
      "linhas ignoradas (a mesma conta já estava gravada)", ""));
  // Contas antigas, gravadas sem o status, que ganham o status deste arquivo (só quando há alguma).
  if (previa.completadas > 0) {
    numeros.append(criar_numero_da_previa(previa.completadas, "contas antigas ganham o status", ""));
  }
  etapa.append(numeros);
  // A lista dos avisos, se houver.
  const avisos = montar_lista_de_avisos(previa.avisos);
  if (avisos) {
    etapa.append(avisos);
  }
  // O que muda em cada empresa (só quando há conta nova).
  if (previa.por_empresa.length > 0) {
    etapa.append(montar_tabela_por_empresa(previa.por_empresa));
  }
  // O que a empresa passa a ver.
  etapa.append(criar_na_janela_de_contas("p", "nota-sigilo",
    "Depois da baixa, a empresa vê a conta salário de cada funcionário dela (agência, número e data de abertura), " +
    "para pagar o salário, e a situação da pessoa passa a ser \"Conta aberta\" (status 1) ou \"Já é correntista\" " +
    "(status 2)."));
  // Os botões de decidir.
  const botoes = criar_na_janela_de_contas("div", "janela-botoes", "");
  const descartar = criar_na_janela_de_contas("button", "botao botao-contorno", "Descartar esta leitura");
  descartar.type = "button";
  descartar.addEventListener("click", descartar_previa_na_janela);
  const confirmar = criar_na_janela_de_contas("button", "botao botao-principal",
    "Confirmar a baixa de " + quantidade_com_palavra(previa.novas, "conta", "contas"));
  confirmar.type = "button";
  confirmar.setAttribute("data-confirmar-baixa-janela", "");
  // Sem conta nova, mas com contas antigas que ganham o status: o botão grava só o status.
  if (previa.novas === 0 && previa.completadas > 0) {
    confirmar.textContent = "Gravar o status de " + quantidade_com_palavra(previa.completadas, "conta antiga",
      "contas antigas");
  }
  // Sem conta nova e sem status a gravar, não há o que confirmar.
  if (previa.novas === 0 && previa.completadas === 0) {
    confirmar.disabled = true;
    confirmar.textContent = "Nenhuma conta nova neste arquivo";
  }
  confirmar.addEventListener("click", confirmar_baixa_na_janela);
  botoes.append(descartar, confirmar);
  etapa.append(botoes);
}

// ===== Decidir: confirmar ou descartar =====

/**
 * Confirma a baixa da prévia: grava as contas e avisa a tela de trás.
 *
 * Recebe: nada. Devolve: nada.
 */
async function confirmar_baixa_na_janela() {
  if (!previa_na_janela || !previa_na_janela.arquivo_id) {
    return;
  }
  // Trava o botão contra o clique duplo.
  const botao = janela_de_contas.querySelector("[data-confirmar-baixa-janela]");
  botao.disabled = true;
  let dados = null;
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  try {
    const resposta = await fetch("/api/banco/contas/" + encodeURIComponent(previa_na_janela.arquivo_id) +
      "/confirmar", { method: "POST" });
    dados = await resposta.json();
    if (!resposta.ok) {
      mostrar_erro_na_janela("Não foi possível confirmar a baixa: " + dados.detail);
      previa_na_janela = null;
      return;
    }
  } catch (erro) {
    botao.disabled = false;
    return;
  }
  previa_na_janela = null;
  mostrar_baixa_feita(dados);
}

/**
 * Escreve o texto do fim da baixa: quantos passaram a ter conta (contas novas e correntistas) e quantas
 * contas antigas ganharam o status.
 *
 * Recebe: resultado — da confirmação ({novas, tipos_das_novas, completadas}). Devolve: o texto.
 * Exemplo: "Baixa feita na Aurora Alimentos: 3 funcionários passaram a ter conta (2 contas novas · 1
 * correntista). As telas da empresa já mostram os números novos."
 */
function texto_da_baixa_feita(resultado) {
  // Só contas antigas ganharam o status: ninguém passou a ter conta agora.
  if (resultado.novas === 0) {
    return "Status gravado na " + empresa_da_janela.nome + ": " + quantidade_com_palavra(resultado.completadas,
      "conta antiga ganhou", "contas antigas ganharam") + " o status.";
  }
  let texto = "Baixa feita na " + empresa_da_janela.nome + ": " +
    quantidade_com_palavra(resultado.novas, "funcionário passou", "funcionários passaram") +
    " a ter conta (" + texto_dos_tipos_de_conta(resultado.tipos_das_novas) + ").";
  // Contas antigas que também ganharam o status neste arquivo.
  if (resultado.completadas > 0) {
    texto = texto + " " + quantidade_com_palavra(resultado.completadas, "conta antiga ganhou",
      "contas antigas ganharam") + " o status.";
  }
  return texto + " As telas da empresa já mostram os números novos.";
}

/**
 * Mostra a etapa final e avisa a página de trás (a aba Contas abertas da ficha recarrega o histórico).
 *
 * Recebe: resultado — da confirmação ({novas, tipos_das_novas, completadas}). Devolve: nada.
 */
function mostrar_baixa_feita(resultado) {
  const etapa = mostrar_etapa_da_janela("feito");
  const novas = resultado.novas;
  const texto = texto_da_baixa_feita(resultado);
  etapa.replaceChildren(criar_na_janela_de_contas("p", "aviso-contas aviso-contas-certo", texto));
  etapa.firstChild.setAttribute("data-aviso-baixa-feita", "");
  const botoes = criar_na_janela_de_contas("div", "janela-botoes", "");
  const fechar = criar_na_janela_de_contas("button", "botao botao-principal", "Fechar");
  fechar.type = "button";
  fechar.addEventListener("click", fechar_janela_de_contas);
  botoes.append(fechar);
  etapa.append(botoes);
  // A tela de trás escuta este evento para se atualizar (a aba Contas abertas da ficha da empresa).
  document.dispatchEvent(new CustomEvent("contas-abertas-carregadas",
    { detail: { novas: novas, texto: texto, empresa_id: empresa_da_janela.empresa_id } }));
}

/**
 * Descarta a prévia pronta no servidor (nada é gravado) e volta à etapa 1.
 *
 * Recebe: nada. Devolve: nada.
 */
async function descartar_previa_na_janela() {
  await descartar_previa_aberta();
  mostrar_etapa_da_janela("escolher");
}

/**
 * Se há uma prévia pronta (guardada como pendente no servidor), descarta. Recusadas não guardam nada: nada a fazer.
 *
 * Recebe: nada. Devolve: nada.
 */
async function descartar_previa_aberta() {
  const previa = previa_na_janela;
  previa_na_janela = null;
  if (!previa || !previa.arquivo_id) {
    return;
  }
  // try/catch: se o servidor não responder, a prévia fica pendente e nunca vira baixa sem o "Confirmar".
  try {
    await fetch("/api/banco/contas/" + encodeURIComponent(previa.arquivo_id) + "/descartar", { method: "POST" });
  } catch (erro) {
    return;
  }
}

// ===== Abrir e fechar =====

/**
 * Abre a janela do zero, na etapa 1, para uma empresa, e carrega o formato do arquivo e a orientação dela.
 *
 * Recebe: empresa — { empresa_id, nome }. Ex.: { empresa_id: "EMP001", nome: "Aurora Alimentos" }. Devolve: nada.
 */
function abrir_janela_de_contas(empresa) {
  // Criada no primeiro clique; depois, reaproveitada.
  if (!janela_de_contas) {
    janela_de_contas = criar_janela_de_contas();
  }
  // Guarda a empresa e começa sem prévia e sem o layout de antes (que pode ser de outra empresa).
  empresa_da_janela = empresa;
  previa_na_janela = null;
  layout_de_contas = null;
  // O título cita a empresa (e o leitor de tela anuncia o mesmo).
  const titulo = "Carregar Contas Abertas · " + empresa.nome;
  janela_de_contas.querySelector("[data-titulo-janela-contas]").textContent = titulo;
  janela_de_contas.setAttribute("aria-label", titulo);
  // A orientação e o formato voltam a "carregando" até o servidor responder.
  janela_de_contas.querySelector("[data-orientacao-janela-contas] [data-texto-orientacao]").textContent =
    "Carregando a orientação…";
  janela_de_contas.querySelector("[data-orientacao-janela-contas] [data-legenda-orientacao]").textContent = "…";
  janela_de_contas.querySelector("[data-formato-contas]").replaceChildren(
    criar_na_janela_de_contas("p", "", "Carregando o formato do arquivo…"));
  janela_de_contas.querySelector("[data-conferencias-contas]").replaceChildren();
  // Mostra a etapa 1 e abre.
  mostrar_etapa_da_janela("escolher");
  janela_de_contas.showModal();
  // Aberta como arquivo (sem servidor): avisa em vez de tentar.
  if (!window.location.protocol.startsWith("http")) {
    janela_de_contas.querySelector("[data-orientacao-janela-contas] [data-texto-orientacao]").textContent =
      "O arquivo é da " + empresa.nome + ": cada linha traz o CPF de um funcionário Cadastrado nela, o status e a " +
      "agência, a conta salário e a data de abertura dessa conta.";
    // A legenda do status (a mesma do servidor; aberta como arquivo, não há servidor para perguntar).
    janela_de_contas.querySelector("[data-orientacao-janela-contas] [data-legenda-orientacao]").textContent =
      "1 = Conta nova · 2 = Já era correntista";
    janela_de_contas.querySelector("[data-formato-contas]").replaceChildren(criar_na_janela_de_contas("p",
      "aviso-trava-contas", "Para carregar o arquivo, abra o Portal Interno pelo servidor."));
    return;
  }
  // Com servidor: o formato e a orientação desta empresa.
  carregar_formato_de_contas();
}

/**
 * Fecha a janela. Uma prévia pronta ainda não confirmada é descartada (nada fica pela metade).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_janela_de_contas() {
  descartar_previa_aberta();
  janela_de_contas.close();
}

/**
 * Abre a janela para a empresa que o botão clicado leva (atributos data-empresa-id e data-empresa-nome).
 *
 * Recebe: evento — o clique no botão. Devolve: nada. Botão sem empresa (a ficha ainda não abriu nenhuma): nada.
 */
function abrir_janela_pelo_botao(evento) {
  // O botão clicado (mesmo que o clique caia num texto dentro dele).
  const botao = evento.currentTarget;
  // Sem empresa no botão: não há para quem carregar.
  if (!botao.dataset.empresaId) {
    return;
  }
  // Abre a janela para a empresa do botão.
  abrir_janela_de_contas({ empresa_id: botao.dataset.empresaId, nome: botao.dataset.empresaNome });
}

/**
 * Liga os botões "Carregar Contas Abertas" da página (os que têm data-abrir-carregar-contas).
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_botoes_de_carregar_contas() {
  // Cada botão abre a janela para a empresa que ele leva.
  for (const botao of document.querySelectorAll("[data-abrir-carregar-contas]")) {
    botao.addEventListener("click", abrir_janela_pelo_botao);
  }
}

// Quando o HTML terminar de carregar, liga os botões.
document.addEventListener("DOMContentLoaded", preparar_botoes_de_carregar_contas);
