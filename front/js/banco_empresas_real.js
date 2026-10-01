/*
  banco_empresas_real.js — a tela "Empresas" do Portal Interno com os dados reais da aplicação (ADR-69).

  Para que serve: quando a página é servida pela API, troca as empresas de exemplo (js/banco_empresas.js) pelas
  fichas reais (/api/banco/empresas) e liga os botões à aplicação:
    - Dados: o cadastro da sede (razão social, CNPJ principal, endereço, domínio de e-mail, contrato) e os números;
      "Editar dados"; os CNPJs de filiais e do grupo (opcional, ADR-77), com "Adicionar CNPJ" e "Tirar";
    - "Cadastrar empresa": a empresa nova entra na carteira na hora, com o código novo (ex.: EMP007);
    - Usuários: as pessoas do RH com o último acesso; Desativar e Reativar de verdade; "Convidar usuário" cria o acesso
      com o e-mail do domínio da empresa e uma senha provisória, mostrada UMA vez (a aplicação não manda e-mail);
    - Catálogo de benefícios: os documentos vigentes; "Subir nova versão" publica o documento (.md ou .txt);
    - Visão geral: os números e a grade de funcionários (ADR-112), e o "Baixar CSV" com todas as colunas do cadastro
      da empresa aberta.
  O kit de marca (as cores e o logo) não fica na ficha: é a KB "Kit da marca" da empresa,
  no Endomarketing; o cadastro só guarda uma cópia, que o servidor grava ao publicar ou retirar essa KB.
  As abas Conversa e Contas abertas buscam os próprios dados (js/banco_empresas_conversa.js e
  js/banco_empresas_contas.js), a partir do momento em que as fichas reais chegam (modo_real_das_empresas()).
  Aberta sem servidor (dois cliques), a página continua com o exemplo do layout. Servida pela aplicação, o exemplo
  nunca aparece: a lista e a ficha esperam com a barra cinza (js/carregando_dados.js) e, se o servidor falhar, a
  lista mostra o aviso "Não foi possível carregar agora.".
*/

// Verdadeiro depois que as fichas reais chegaram (os desvios do js/banco_empresas.js olham isto).
let empresas_reais_carregadas = false;

/**
 * Diz se a tela está usando as fichas reais da aplicação.
 *
 * Recebe: nada. Devolve: true ou false.
 */
function modo_real_das_empresas() {
  return empresas_reais_carregadas;
}

/**
 * Escreve a data e a hora no jeito curto ("24/09, 10:12"), no horário do computador.
 *
 * Recebe: texto — data e hora do servidor, ou null. Devolve: o texto curto, ou o texto_se_vazio.
 */
function data_curta_das_empresas(texto, texto_se_vazio) {
  // Sem data: o texto combinado para esse caso.
  if (!texto) {
    return texto_se_vazio;
  }
  // O navegador converte do horário universal para o horário do computador.
  const momento = new Date(texto);
  const dia_e_mes = momento.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const hora = momento.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return dia_e_mes + ", " + hora;
}

/**
 * Escreve uma data AAAA-MM-DD no jeito brasileiro ("2026-12-31" → "31/12/2026").
 *
 * Recebe: texto. Devolve: a data no jeito brasileiro.
 */
function data_brasileira(texto) {
  // Separa ano, mês e dia e junta na ordem brasileira.
  const partes = texto.split("-");
  return partes[2] + "/" + partes[1] + "/" + partes[0];
}

// ===== Aba "Dados" =====

/**
 * Preenche o cabeçalho e a aba Dados da ficha com os dados reais.
 *
 * Recebe: empresa — a ficha real. Devolve: nada.
 */
function mostrar_dados_reais(empresa) {
  const dados = empresa.dados;
  // Resumo do cabeçalho: CNPJ, código e contrato.
  document.querySelector("[data-ficha-resumo]").textContent = "CNPJ " + cnpj_formatado(dados.cnpj) + " · código " +
    empresa.id + " · cliente desde " + data_brasileira(dados.contrato_desde);
  // Empresa: o cadastro.
  preencher_campos("[data-campos-empresa]", [
    ["Razão social", empresa.nome],
    ["CNPJ", cnpj_formatado(dados.cnpj)],
    ["Setor", empresa.setor],
    ["Endereço da sede", dados.endereco_comercial + " · " + empresa.cidade],
    ["Domínio de e-mail", dados.dominio_email],
  ]);
  // O botão "Editar dados" (criado uma vez só, no fim da aba Dados).
  const aba_dos_dados = document.querySelector("[data-conteudo-aba='dados']");
  if (!aba_dos_dados.querySelector("[data-editar-empresa]")) {
    const botao = criar_elemento("button", "botao botao-contorno botao-pequeno", "Editar dados");
    botao.type = "button";
    botao.dataset.editarEmpresa = "";
    aba_dos_dados.append(botao);
  }
  // Contrato: os números reais dos cadastros.
  preencher_campos("[data-campos-contrato]", [
    ["Contrato desde", data_brasileira(dados.contrato_desde)],
    ["Etapa da jornada", empresa.situacao.texto],
    ["Funcionários cadastrados", String(empresa.cadastrados)],
    ["Arquivos enviados", String(empresa.envios)],
    ["Envios com pendência", String(empresa.com_pendencia)],
    ["Último envio", data_curta_das_empresas(empresa.ultimo_envio, "nenhum")],
    ["Contas abertas", texto_das_contas(empresa.contas)],
  ]);
  // Os CNPJs de filiais e do grupo.
  mostrar_cnpjs_reais(empresa);
}

// ----- CNPJs de filiais e do grupo (ADR-77) -----

// Como cada tipo e cada origem aparecem na tabela.
const NOMES_DOS_TIPOS_DE_CNPJ = { FILIAL: "Filial", GRUPO: "Empresa do grupo" };
const NOMES_DAS_ORIGENS_DE_CNPJ = { BANCO: "Banco", EMPRESA: "A empresa, ao confirmar num envio" };

/**
 * Mostra os CNPJs de filiais e do grupo da empresa, cada um com o botão "Tirar".
 *
 * Recebe: empresa — a ficha real (com outros_cnpjs). Devolve: nada.
 */
function mostrar_cnpjs_reais(empresa) {
  // O bloco só aparece com servidor (no exemplo do layout ele fica escondido).
  document.querySelector("[data-bloco-cnpjs]").hidden = false;
  document.querySelector("[data-erro-cnpj]").hidden = true;
  const corpo = document.querySelector("[data-corpo-cnpjs]");
  corpo.replaceChildren();
  // Sem nenhum: uma linha dizendo isso.
  if (empresa.outros_cnpjs.length === 0) {
    const linha = document.createElement("tr");
    const celula = criar_elemento("td", "texto-leve", "Nenhum CNPJ além do principal.");
    celula.colSpan = 4;
    linha.append(celula);
    corpo.append(linha);
    return;
  }
  // Uma linha por CNPJ: número, tipo, quem registrou e o botão "Tirar".
  for (const registrado of empresa.outros_cnpjs) {
    const linha = document.createElement("tr");
    linha.dataset.cnpj = registrado.cnpj;
    // Quem registrou: o banco ou a empresa (com o login e a data).
    const quem = NOMES_DAS_ORIGENS_DE_CNPJ[registrado.origem] + " · " + registrado.registrado_por + " · " +
      data_curta_das_empresas(registrado.registrado_em, "");
    linha.append(criar_elemento("td", "", cnpj_formatado(registrado.cnpj)));
    linha.append(criar_elemento("td", "", NOMES_DOS_TIPOS_DE_CNPJ[registrado.tipo]));
    linha.append(criar_elemento("td", "", quem));
    // "Tirar": dois cliques (o primeiro pede confirmação).
    const acao = document.createElement("td");
    const botao = criar_elemento("button", "botao-descartar", "Tirar");
    botao.type = "button";
    botao.dataset.tirarCnpj = registrado.cnpj;
    acao.append(botao);
    linha.append(acao);
    corpo.append(linha);
  }
}

/**
 * Mostra o erro do bloco dos CNPJs.
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_erro_do_cnpj(texto) {
  const aviso = document.querySelector("[data-erro-cnpj]");
  aviso.textContent = texto;
  aviso.hidden = false;
}

/**
 * Cadastra o CNPJ digitado (filial ou grupo) e mostra a lista atualizada.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
async function adicionar_cnpj_de_verdade(evento) {
  // Não recarrega a página: o pedido vai pela API.
  evento.preventDefault();
  const empresa = estado_das_empresas.empresa_aberta;
  const campo_do_cnpj = document.querySelector("[data-cnpj-novo]");
  const resposta = await postar_json("/api/banco/empresas/" + encodeURIComponent(empresa.id) + "/cnpjs", {
    cnpj: campo_do_cnpj.value, tipo: document.querySelector("[data-cnpj-tipo]").value,
  });
  // Recusado: o motivo aparece embaixo do formulário.
  if (!resposta.ok) {
    mostrar_erro_do_cnpj(texto_do_erro_das_empresas(resposta.dados.detail));
    return;
  }
  // Guarda a lista nova na ficha aberta e mostra.
  empresa.outros_cnpjs = resposta.dados;
  campo_do_cnpj.value = "";
  mostrar_cnpjs_reais(empresa);
}

/**
 * Tira um CNPJ: o primeiro clique pede confirmação; o segundo tira.
 *
 * Recebe: botao — o "Tirar" clicado. Devolve: nada.
 */
async function tirar_cnpj_de_verdade(botao) {
  // Primeiro clique: só pede confirmação.
  if (!botao.dataset.confirmar) {
    botao.dataset.confirmar = "sim";
    botao.textContent = "Clique de novo para tirar";
    return;
  }
  const empresa = estado_das_empresas.empresa_aberta;
  const endereco = "/api/banco/empresas/" + encodeURIComponent(empresa.id) + "/cnpjs/" +
    encodeURIComponent(botao.dataset.tirarCnpj);
  const resposta = await pedir_das_empresas(endereco, { method: "DELETE" });
  if (!resposta.ok) {
    mostrar_erro_do_cnpj(texto_do_erro_das_empresas(resposta.dados.detail));
    return;
  }
  // Guarda a lista que ficou e mostra.
  empresa.outros_cnpjs = resposta.dados;
  mostrar_cnpjs_reais(empresa);
}

/**
 * Escreve o CNPJ com a pontuação ("10433218000193" → "10.433.218/0001-93").
 *
 * Recebe: cnpj — só os dígitos. Devolve: o texto pontuado (ou como veio, se não tiver 14 dígitos).
 */
function cnpj_formatado(cnpj) {
  if (!cnpj || cnpj.length !== 14) {
    return cnpj || "";
  }
  return cnpj.slice(0, 2) + "." + cnpj.slice(2, 5) + "." + cnpj.slice(5, 8) + "/" + cnpj.slice(8, 12) + "-" + cnpj.slice(12);
}

/**
 * O texto das contas abertas da empresa, para a ficha: "20 de 35 (57%)" ou o aviso de que o arquivo não chegou.
 *
 * Recebe: contas — {cadastrados, com_conta, percentual, arquivo_recebido}. Devolve: o texto.
 */
function texto_das_contas(contas) {
  if (!contas.arquivo_recebido) {
    return "o arquivo de contas do banco ainda não chegou";
  }
  return contas.com_conta + " de " + contas.cadastrados + " (" + contas.percentual + "%)";
}

// ===== Aba "Usuários" =====

/**
 * Troca o cabeçalho da tabela de usuários pelas colunas reais (a aplicação guarda o login, não nome e e-mail).
 *
 * Recebe: nada. Devolve: nada.
 */
function trocar_cabecalho_dos_usuarios() {
  // A linha do cabeçalho da tabela de usuários.
  const cabecalho = document.querySelector("[data-corpo-usuarios]").closest("table").querySelector("thead tr");
  cabecalho.replaceChildren();
  // Uma coluna por título; a última (ação) só para leitores de tela.
  for (const titulo of ["Usuário", "Último acesso", "Situação"]) {
    const celula = criar_elemento("th", "", titulo);
    celula.scope = "col";
    cabecalho.append(celula);
  }
  const celula_acao = criar_elemento("th", "", "");
  celula_acao.scope = "col";
  celula_acao.append(criar_elemento("span", "texto-leitor-de-tela", "Ação"));
  cabecalho.append(celula_acao);
}

// ----- A senha provisória na linha da pessoa -----

// A senha provisória que o banco acabou de gerar (na "Nova senha provisória" ou no convite), mostrada na linha da
// pessoa, e só desta vez (ADR-109): { login, senha, titulo }, ou null. Some ao abrir outra empresa, no "Fechar" e ao
// recarregar a página (ela nunca é guardada).
let senha_provisoria_na_tela = null;
// A pessoa cuja "Nova senha provisória" espera a confirmação na própria linha (o login), ou "" quando ninguém espera.
let login_esperando_confirmacao = "";
// A orientação do primeiro acesso, ao lado da senha: o que a pessoa faz com ela (o especialista repassa).
const ORIENTACAO_DO_PRIMEIRO_ACESSO = "Primeiro acesso: entre com esta senha; o sistema pede para criar a sua.";
// O aviso de que a senha não volta (ela não fica guardada em lugar nenhum, ADR-109).
const AVISO_DA_SENHA_QUE_NAO_VOLTA = "Esta senha aparece só agora: ao fechar, ela não volta.";

/**
 * Monta a tabela com as pessoas reais da empresa, cada uma com o botão Desativar ou Reativar e, para quem está ativo,
 * a "Nova senha provisória". A pessoa que espera a confirmação da senha nova tem, na própria linha, a pergunta com os
 * botões "Confirmar" e "Cancelar"; a que acabou de ganhar uma senha tem a senha logo abaixo da linha dela.
 *
 * Recebe: empresa — a ficha real. Devolve: nada.
 */
function mostrar_usuarios_reais(empresa) {
  // Corpo da tabela, vazio antes de montar.
  const corpo = document.querySelector("[data-corpo-usuarios]");
  corpo.replaceChildren();
  // Empresa sem ninguém cadastrado: diz isso numa linha.
  if (empresa.usuarios.length === 0) {
    const linha = criar_elemento("tr", "", "");
    const celula = criar_elemento("td", "", "Ninguém desta empresa tem acesso ao portal ainda.");
    celula.colSpan = 4;
    linha.append(celula);
    corpo.append(linha);
    return;
  }
  // Uma linha por pessoa.
  for (const usuario of empresa.usuarios) {
    const linha = criar_elemento("tr", "", "");
    // O login fica na linha: os roteiros de clique acham a pessoa por ele.
    linha.dataset.linhaDoUsuario = usuario.login;
    linha.append(criar_elemento("td", "", usuario.login));
    linha.append(criar_elemento("td", "", data_curta_das_empresas(usuario.ultimo_acesso, "nunca entrou")));
    // Selo: desativado (cinza), suspenso ou vencido (atenção, ADR-146), senha provisória vencida (atenção, ADR-154),
    // senha resetada ou ativo (verde).
    let selo = SELOS_DOS_USUARIOS["ativo"];
    if (!usuario.ativo) {
      selo = SELOS_DOS_USUARIOS["desativado"];
    } else if (usuario.suspensao) {
      selo = SELOS_DOS_USUARIOS[usuario.suspensao];
    } else if (usuario.senha_provisoria_vencida) {
      selo = SELOS_DOS_USUARIOS["senha_provisoria_vencida"];
    } else if (usuario.senha_provisoria) {
      selo = SELOS_DOS_USUARIOS["senha_provisoria"];
    }
    const celula_situacao = criar_elemento("td", "", "");
    celula_situacao.append(criar_elemento("span", "selo selo-pequeno " + selo.classe, selo.texto));
    linha.append(celula_situacao);
    // Ação: a confirmação da senha nova, quando é esta pessoa que espera; senão, os botões de sempre.
    const celula_acao = criar_elemento("td", "", "");
    if (usuario.login === login_esperando_confirmacao) {
      celula_acao.append(confirmacao_da_nova_senha(usuario.login));
    } else {
      acrescentar_acoes_do_usuario(celula_acao, usuario);
    }
    linha.append(celula_acao);
    corpo.append(linha);
    // A senha nova desta pessoa, logo abaixo da linha dela (a linha e a senha ficam com o mesmo fundo).
    if (senha_provisoria_na_tela && senha_provisoria_na_tela.login === usuario.login) {
      linha.classList.add("linha-com-senha-provisoria");
      corpo.append(linha_da_senha_provisoria(senha_provisoria_na_tela));
    }
  }
}

/**
 * Os botões de sempre de uma pessoa: Desativar ou Reativar e, para quem está ativo, a "Nova senha provisória".
 *
 * Recebe: celula_acao — a célula da ação; usuario — a pessoa. Devolve: nada.
 */
function acrescentar_acoes_do_usuario(celula_acao, usuario) {
  // Quem está ativo e em dia pode ser desativado; o desativado e o suspenso podem ser reativados.
  let texto_do_botao = "Reativar";
  if (usuario.ativo && !usuario.suspensao) {
    texto_do_botao = "Desativar";
  }
  const botao = criar_elemento("button", "botao-nome", texto_do_botao);
  botao.type = "button";
  botao.dataset.alternarUsuario = usuario.login;
  celula_acao.append(botao);
  // A pessoa esqueceu a senha: o banco gera uma provisória nova (só para quem está ativo, ADR-109).
  if (usuario.ativo) {
    const botao_de_senha = criar_elemento("button", "botao-nome", "Nova senha provisória");
    botao_de_senha.type = "button";
    botao_de_senha.dataset.novaSenha = usuario.login;
    celula_acao.append(document.createTextNode(" · "));
    celula_acao.append(botao_de_senha);
  }
}

/**
 * A pergunta da senha nova, na linha da pessoa, com "Confirmar" e "Cancelar" com cara de botão: um texto em
 * negrito não mostra que é para clicar de novo.
 *
 * Recebe: login — a pessoa. Devolve: o bloco pronto.
 */
function confirmacao_da_nova_senha(login) {
  const grupo = criar_elemento("div", "confirmacao-da-senha", "");
  // Leitores de tela anunciam os dois botões como um grupo, com a pessoa no nome.
  grupo.setAttribute("role", "group");
  grupo.setAttribute("aria-label", "Confirmar a senha provisória nova de " + login);
  // Por que confirmar: a pessoa sai do portal na hora e só volta com a senha nova.
  grupo.append(criar_elemento("span", "confirmacao-da-senha-texto", "Gerar uma senha nova? A pessoa sai do portal agora."));
  const confirmar = criar_elemento("button", "botao botao-principal botao-pequeno", "Confirmar");
  confirmar.type = "button";
  confirmar.dataset.confirmarNovaSenha = login;
  const cancelar = criar_elemento("button", "botao botao-contorno botao-pequeno", "Cancelar");
  cancelar.type = "button";
  cancelar.dataset.cancelarNovaSenha = login;
  grupo.append(confirmar, cancelar);
  return grupo;
}

/**
 * A linha logo abaixo da pessoa que acabou de ganhar a senha: a senha, o botão de copiar (com o ícone), a orientação
 * do primeiro acesso e o "Fechar".
 *
 * Recebe: senha_na_tela — { login, senha, titulo }. Devolve: o <tr> pronto.
 * O bloco recebe o foco quando aparece (tabindex="-1"), e o leitor de tela lê a senha (role="status").
 */
function linha_da_senha_provisoria(senha_na_tela) {
  const linha = criar_elemento("tr", "linha-da-senha-provisoria", "");
  const celula = criar_elemento("td", "", "");
  // A linha da senha ocupa a largura da tabela inteira (as 4 colunas)
  celula.colSpan = 4;
  const bloco = criar_elemento("div", "senha-na-linha", "");
  bloco.dataset.senhaNaLinha = senha_na_tela.login;
  bloco.setAttribute("role", "status");
  bloco.tabIndex = -1;
  // 1. O título, a senha em letra de código e o botão de copiar
  const topo = criar_elemento("div", "senha-na-linha-topo", "");
  topo.append(criar_elemento("span", "senha-na-linha-titulo", senha_na_tela.titulo));
  const valor = criar_elemento("code", "senha-na-linha-valor", senha_na_tela.senha);
  valor.dataset.senhaNaLinhaValor = "";
  topo.append(valor, botao_de_copiar_a_senha(senha_na_tela.login));
  // O recado do copiar ("Senha copiada..."), que aparece depois do clique
  const recado = criar_elemento("span", "senha-na-linha-copiada", "");
  recado.dataset.senhaCopiada = "";
  recado.hidden = true;
  topo.append(recado);
  bloco.append(topo);
  // 2. A orientação do primeiro acesso, ali mesmo, e o aviso de que a senha não volta
  bloco.append(criar_elemento("p", "senha-na-linha-orientacao", ORIENTACAO_DO_PRIMEIRO_ACESSO));
  const rodape = criar_elemento("div", "senha-na-linha-rodape", "");
  rodape.append(criar_elemento("span", "senha-na-linha-aviso", AVISO_DA_SENHA_QUE_NAO_VOLTA));
  const fechar = criar_elemento("button", "botao-nome", "Fechar");
  fechar.type = "button";
  fechar.dataset.fecharSenhaDaLinha = "";
  rodape.append(fechar);
  bloco.append(rodape);
  celula.append(bloco);
  linha.append(celula);
  return linha;
}

/**
 * O botão de copiar a senha, com o ícone de copiar e o texto "Copiar".
 *
 * Recebe: login — a pessoa (para o leitor de tela dizer de quem é a senha). Devolve: o botão.
 */
function botao_de_copiar_a_senha(login) {
  const botao = criar_elemento("button", "botao botao-contorno botao-pequeno botao-copiar-senha", "");
  botao.type = "button";
  botao.dataset.copiarSenhaDaLinha = "";
  botao.setAttribute("aria-label", "Copiar a senha provisória de " + login);
  // O ícone (duas folhas sobrepostas), desenhado a partir da biblioteca de ícones da página
  const icone = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icone.setAttribute("class", "icone");
  icone.setAttribute("aria-hidden", "true");
  const uso_do_icone = document.createElementNS("http://www.w3.org/2000/svg", "use");
  uso_do_icone.setAttribute("href", "#icone-copiar");
  icone.append(uso_do_icone);
  botao.append(icone, document.createTextNode("Copiar"));
  return botao;
}

/**
 * Desativa ou reativa de verdade uma pessoa da empresa aberta e redesenha a tabela.
 *
 * Recebe: login — a pessoa. Devolve: nada (espera a resposta do servidor).
 */
async function alternar_usuario_de_verdade(login) {
  // A pessoa na ficha aberta.
  const empresa = estado_das_empresas.empresa_aberta;
  let pessoa = null;
  for (const usuario of empresa.usuarios) {
    if (usuario.login === login) {
      pessoa = usuario;
    }
  }
  // O contrário da situação atual; o suspenso (ainda "ativo") é reativado, e reativar renova o acesso (ADR-146).
  const nova_situacao = !pessoa.ativo || Boolean(pessoa.suspensao);
  // try/catch: servidor fora do ar vira aviso, não erro na tela.
  try {
    const resposta = await fetch("/api/banco/empresas/usuarios/" + encodeURIComponent(login) + "/situacao", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ativo: nova_situacao }),
    });
    // Recusado: mostra o motivo do servidor.
    if (!resposta.ok) {
      const erro = await resposta.json();
      mostrar_aviso_das_empresas("Não foi possível: " + erro.detail);
      return;
    }
  } catch (erro) {
    mostrar_aviso_das_empresas("Sem conexão com o servidor. Tente de novo.");
    return;
  }
  // Deu certo: guarda a nova situação, redesenha e avisa. Reativar renova o acesso: a suspensão acaba.
  pessoa.ativo = nova_situacao;
  if (nova_situacao) {
    pessoa.suspensao = null;
  }
  // Desativada, a pessoa não entra: a senha nova dela (ou a pergunta da senha) sai da linha.
  if (!nova_situacao) {
    tirar_a_senha_da_linha_de(login);
  }
  mostrar_usuarios_reais(empresa);
  if (nova_situacao) {
    mostrar_aviso_das_empresas(login + " pode entrar de novo no Portal Empresa. O acesso vale por mais 12 meses.");
  } else {
    mostrar_aviso_das_empresas(login + " não entra mais no Portal Empresa e saiu na hora. O histórico do que essa pessoa fez continua guardado.");
  }
}

/**
 * O primeiro clique em "Nova senha provisória": a linha da pessoa passa a perguntar, com "Confirmar" e "Cancelar",
 * porque a pessoa sai do portal na hora e só volta com a senha nova. Nada é gerado ainda.
 *
 * Recebe: login — a pessoa. Devolve: nada. O foco vai para o "Confirmar", para quem usa o teclado.
 */
function pedir_confirmacao_da_nova_senha(login) {
  login_esperando_confirmacao = login;
  // Um erro de uma tentativa anterior sai da vista
  document.querySelector("[data-erro-usuarios]").hidden = true;
  mostrar_usuarios_reais(estado_das_empresas.empresa_aberta);
  // O "Confirmar" desta pessoa recebe o foco (compara com cada botão, sem montar seletor com o login)
  for (const botao of document.querySelectorAll("[data-confirmar-nova-senha]")) {
    if (botao.dataset.confirmarNovaSenha === login) {
      botao.focus();
    }
  }
}

/**
 * "Cancelar" na pergunta da senha nova: a linha volta aos botões de sempre, e nada é gerado.
 *
 * Recebe: nada. Devolve: nada.
 */
function cancelar_confirmacao_da_nova_senha() {
  login_esperando_confirmacao = "";
  mostrar_usuarios_reais(estado_das_empresas.empresa_aberta);
}

/**
 * "Confirmar": gera uma senha provisória nova para a pessoa (ela esqueceu a senha) e mostra a senha UMA vez, na linha
 * dela (ADR-109).
 *
 * Recebe: botao — o "Confirmar" da linha da pessoa (o login fica em data-confirmar-nova-senha). Devolve: nada.
 * O botão para enquanto o servidor responde (dois cliques não geram duas senhas). Recusado: o motivo aparece na própria
 * aba, perto da tabela (o aviso do alto ficava fora da vista).
 */
async function gerar_nova_senha_de_verdade(botao) {
  const login = botao.dataset.confirmarNovaSenha;
  const empresa = estado_das_empresas.empresa_aberta;
  botao.disabled = true;
  const resposta = await postar_json("/api/banco/empresas/usuarios/" + encodeURIComponent(login) + "/nova-senha", {});
  // A pergunta terminou, deu certo ou não
  login_esperando_confirmacao = "";
  if (!resposta.ok) {
    mostrar_usuarios_reais(empresa);
    mostrar_erro_dos_usuarios("Não foi possível gerar a senha: " + texto_do_erro_das_empresas(resposta.dados.detail));
    return;
  }
  // Deu certo: marca a pessoa como "senha resetada" e mostra a senha na linha dela
  for (const usuario of empresa.usuarios) {
    if (usuario.login === login) {
      usuario.senha_provisoria = true;
    }
  }
  mostrar_senha_na_linha(empresa, resposta.dados.login, resposta.dados.senha_provisoria, "Senha provisória nova:");
}

/**
 * Mostra a senha que o banco acabou de gerar (na "Nova senha provisória" ou no convite) na linha da pessoa, com o
 * botão de copiar e a orientação do primeiro acesso. É o único lugar em que a senha
 * aparece, e só desta vez (ADR-109).
 *
 * Recebe: empresa — a ficha aberta; login — a pessoa; senha — a senha gerada; titulo — ex.: "Senha provisória nova:".
 * Devolve: nada. A linha entra na vista (sem pular a página inteira) e recebe o foco: o leitor de tela lê a senha.
 * Por quê na linha: numa caixa acima da tabela, ou no aviso do alto da página, a senha ficaria fora da vista ou
 * sem dono claro; na linha, fica claro de quem é a senha.
 */
function mostrar_senha_na_linha(empresa, login, senha, titulo) {
  senha_provisoria_na_tela = { login: login, senha: senha, titulo: titulo };
  // Um erro anterior da aba some: agora deu certo
  document.querySelector("[data-erro-usuarios]").hidden = true;
  mostrar_usuarios_reais(empresa);
  // O bloco da senha desta pessoa (compara com cada bloco, sem montar seletor com o login)
  for (const bloco of document.querySelectorAll("[data-senha-na-linha]")) {
    if (bloco.dataset.senhaNaLinha === login) {
      bloco.scrollIntoView({ block: "nearest" });
      bloco.focus({ preventScroll: true });
    }
  }
}

/**
 * Tira da tela a senha nova e a pergunta da senha, se forem desta pessoa (ex.: ela acabou de ser desativada).
 *
 * Recebe: login — a pessoa. Devolve: nada.
 */
function tirar_a_senha_da_linha_de(login) {
  if (senha_provisoria_na_tela && senha_provisoria_na_tela.login === login) {
    senha_provisoria_na_tela = null;
  }
  if (login_esperando_confirmacao === login) {
    login_esperando_confirmacao = "";
  }
}

/**
 * Esconde a senha da linha, a pergunta da senha e o erro da aba (ao abrir outra empresa, ou no "Fechar").
 *
 * Recebe: nada. Devolve: nada. A senha é apagada da página no próximo desenho da tabela: depois de fechada, ela não
 * volta. Quem chama redesenha a tabela.
 */
function esconder_senha_gerada() {
  senha_provisoria_na_tela = null;
  login_esperando_confirmacao = "";
  document.querySelector("[data-erro-usuarios]").hidden = true;
}

/**
 * "Fechar" na linha da senha: a senha sai da tela (e não volta).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_senha_da_linha() {
  esconder_senha_gerada();
  mostrar_usuarios_reais(estado_das_empresas.empresa_aberta);
}

/**
 * Copia a senha da linha para a área de transferência (o "Ctrl+C"), para colar na mensagem à pessoa.
 *
 * Recebe: botao — o "Copiar" clicado. Devolve: nada (espera o navegador copiar). Sem permissão para copiar, o recado
 * pede para selecionar a senha e copiar à mão (a senha continua à vista).
 */
async function copiar_senha_da_linha(botao) {
  const bloco = botao.closest("[data-senha-na-linha]");
  const recado = bloco.querySelector("[data-senha-copiada]");
  // try/catch: o navegador pode negar a cópia (ex.: fora de https); a senha continua na tela
  try {
    await navigator.clipboard.writeText(bloco.querySelector("[data-senha-na-linha-valor]").textContent);
    recado.textContent = "Senha copiada. Cole na mensagem para a pessoa.";
  } catch (erro) {
    recado.textContent = "Não foi possível copiar sozinho: selecione a senha e copie.";
  }
  recado.hidden = false;
}

/**
 * Mostra um erro da aba Usuários na própria aba (e não no aviso do alto, que fica fora da vista).
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_erro_dos_usuarios(texto) {
  const aviso = document.querySelector("[data-erro-usuarios]");
  aviso.textContent = texto;
  aviso.hidden = false;
  aviso.scrollIntoView({ block: "nearest" });
}

// ===== Aba "Catálogo de benefícios" =====

/**
 * Troca o cabeçalho da tabela do catálogo pelas colunas reais (seções de cada documento vigente).
 *
 * Recebe: nada. Devolve: nada.
 */
function trocar_cabecalho_do_catalogo() {
  // A linha do cabeçalho da tabela do catálogo.
  const cabecalho = document.querySelector("[data-corpo-catalogo]").closest("table").querySelector("thead tr");
  cabecalho.replaceChildren();
  for (const titulo of ["Seção do documento", "Documento", "Versão", "Vigência"]) {
    const celula = criar_elemento("th", "", titulo);
    celula.scope = "col";
    cabecalho.append(celula);
  }
}

/**
 * Monta a tabela do catálogo real: uma linha por seção de cada documento vigente da empresa.
 *
 * Recebe: empresa — a ficha real. Devolve: nada.
 */
function mostrar_catalogo_real(empresa) {
  // Descrição: quantos documentos vigentes a empresa tem.
  let descricao = "Nenhum documento vigente: o Agente de Endomarketing não tem o que usar para esta empresa.";
  // Um documento: singular.
  if (empresa.catalogo.length === 1) {
    descricao = "1 documento vigente, feito pelo banco para esta empresa.";
  }
  // Mais de um: plural.
  if (empresa.catalogo.length > 1) {
    descricao = empresa.catalogo.length + " documentos vigentes, feitos pelo banco para esta empresa.";
  }
  document.querySelector("[data-catalogo-versao]").textContent = descricao;
  // O link "Editar na Base de Conhecimento" abre o Endomarketing já nesta empresa, na guia das KBs (ADR-125)
  document.querySelector("[data-link-kbs-da-empresa]").href = "banco_endomarketing.html?empresa=" +
    encodeURIComponent(empresa.id) + "&aba=base";
  // O aviso de benefício incompleto é do layout (as 3 partes da vitrine); o documento real não tem essas partes.
  document.querySelector("[data-catalogo-aviso]").hidden = true;
  // Corpo da tabela, vazio antes de montar.
  const corpo = document.querySelector("[data-corpo-catalogo]");
  corpo.replaceChildren();
  // Uma linha por seção de cada documento.
  for (const documento of empresa.catalogo) {
    const vigencia = data_brasileira(documento.vigencia_inicio) + " a " + data_brasileira(documento.vigencia_fim);
    for (const secao of documento.secoes) {
      const linha = criar_elemento("tr", "", "");
      linha.append(criar_elemento("td", "", secao), criar_elemento("td", "", documento.titulo));
      linha.append(criar_elemento("td", "", "v" + documento.versao), criar_elemento("td", "", vigencia));
      corpo.append(linha);
    }
  }
}

// ===== Os botões ligados à aplicação =====

/**
 * Trata os cliques que, com servidor, vão para a aplicação (o js/banco_empresas.js desvia para cá).
 *
 * Recebe: botao — o botão clicado. Devolve: true se o clique foi tratado aqui; false se segue o caminho normal.
 */
function tratar_clique_real(botao) {
  if (botao.hasAttribute("data-abrir-convite")) {
    abrir_janela_de_convite();
    // A aplicação não manda e-mail: o recado da janela diz como a pessoa recebe o acesso.
    document.querySelector("#janela-convite .janela-resumo").textContent = "A aplicação não manda e-mail: a senha " +
      "provisória aparece aqui uma vez, para você entregar à pessoa. Ela troca a senha no primeiro acesso.";
    // A aplicação guarda o login (o e-mail), não o nome: o campo do nome sai.
    document.querySelector("[data-convite-nome]").closest("label").hidden = true;
    return true;
  }
  if (botao.hasAttribute("data-cadastrar-empresa")) {
    abrir_janela_da_empresa(null);
    return true;
  }
  if (botao.hasAttribute("data-editar-empresa")) {
    abrir_janela_da_empresa(estado_das_empresas.empresa_aberta);
    return true;
  }
  // A pergunta da senha nova, na linha da pessoa (aba Usuários): confirmar (gera a senha) ou cancelar.
  if (botao.dataset.confirmarNovaSenha) {
    gerar_nova_senha_de_verdade(botao);
    return true;
  }
  if (botao.hasAttribute("data-cancelar-nova-senha")) {
    cancelar_confirmacao_da_nova_senha();
    return true;
  }
  // A senha na linha da pessoa: copiar a senha ou fechar.
  if (botao.hasAttribute("data-copiar-senha-da-linha")) {
    copiar_senha_da_linha(botao);
    return true;
  }
  if (botao.hasAttribute("data-fechar-senha-da-linha")) {
    fechar_senha_da_linha();
    return true;
  }
  // O "Baixar CSV" da Visão geral: o arquivo da empresa aberta
  if (botao.hasAttribute("data-baixar-csv-visao")) {
    baixar_csv_da_visao_geral(botao);
    return true;
  }
  return false;
}

/**
 * Manda um pedido à API e devolve { ok, dados } (sem servidor, ok falso com a mensagem).
 *
 * Recebe: endereco; opcoes — as do fetch. Devolve: { ok, dados }.
 */
async function pedir_das_empresas(endereco, opcoes) {
  try {
    const resposta = await fetch(endereco, opcoes);
    const dados = await resposta.json();
    return { ok: resposta.ok, dados: dados };
  } catch (erro) {
    return { ok: false, dados: { detail: "Sem conexão com o servidor. Tente de novo." } };
  }
}

/**
 * Um pedido POST com JSON.
 *
 * Recebe: endereco; corpo. Devolve: { ok, dados }.
 */
function postar_json(endereco, corpo) {
  return pedir_das_empresas(endereco, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo) });
}

/**
 * O texto de um erro da API (erro de regra vem em texto; erro de formato, em lista).
 *
 * Recebe: detalhe. Devolve: o texto.
 */
function texto_do_erro_das_empresas(detalhe) {
  if (typeof detalhe === "string") {
    return detalhe;
  }
  return "Confira os campos e tente de novo.";
}

// ----- Convite -----

/**
 * Cria o acesso da pessoa (login = e-mail) e mostra a senha provisória UMA vez.
 *
 * Recebe: nada (lê a janela). Devolve: nada.
 */
async function enviar_convite_de_verdade() {
  const empresa = estado_das_empresas.empresa_aberta;
  const email = document.querySelector("[data-convite-email]").value;
  const resposta = await postar_json("/api/banco/empresas/" + encodeURIComponent(empresa.id) + "/convite", { email: email });
  if (!resposta.ok) {
    const aviso = document.querySelector("[data-convite-erro]");
    aviso.textContent = texto_do_erro_das_empresas(resposta.dados.detail);
    aviso.hidden = false;
    return;
  }
  document.getElementById("janela-convite").close();
  await recarregar_e_abrir(empresa.id, "usuarios");
  // A senha aparece na linha da pessoa nova, como a da "Nova senha provisória" (o aviso do alto ficava fora da vista)
  mostrar_senha_na_linha(estado_das_empresas.empresa_aberta, resposta.dados.login, resposta.dados.senha_provisoria,
    "Acesso criado. Senha provisória:");
}

// ----- Empresa nova e editar dados -----

// Os campos da janela da empresa, na ordem do formulário.
const CAMPOS_DA_EMPRESA = ["nome", "cnpj", "setor", "endereco_comercial", "municipio", "uf", "dominio_email", "contrato_desde"];
// A empresa sendo editada (null: empresa nova).
let empresa_em_edicao = null;

/**
 * Abre a janela da empresa: vazia (empresa nova) ou preenchida com o cadastro (editar dados).
 *
 * Recebe: empresa — a ficha, ou null. Devolve: nada.
 */
function abrir_janela_da_empresa(empresa) {
  empresa_em_edicao = empresa;
  let titulo = "Empresa nova";
  let dados = { contrato_desde: new Date().toISOString().slice(0, 10) };
  if (empresa) {
    titulo = empresa.nome;
    dados = empresa.dados;
  }
  document.querySelector("[data-empresa-titulo-janela]").textContent = titulo;
  for (const campo of CAMPOS_DA_EMPRESA) {
    document.querySelector("[data-empresa-campo='" + campo + "']").value = dados[campo] || "";
  }
  document.querySelector("[data-empresa-erro]").hidden = true;
  document.getElementById("janela-empresa").showModal();
}

/**
 * Grava a empresa nova (ou os dados editados) e abre a ficha dela.
 *
 * Recebe: evento — o envio do formulário. Devolve: nada.
 */
async function salvar_empresa(evento) {
  evento.preventDefault();
  const dados = {};
  for (const campo of CAMPOS_DA_EMPRESA) {
    dados[campo] = document.querySelector("[data-empresa-campo='" + campo + "']").value;
  }
  let endereco = "/api/banco/empresas";
  if (empresa_em_edicao) {
    endereco = "/api/banco/empresas/" + encodeURIComponent(empresa_em_edicao.id) + "/dados";
  }
  const resposta = await postar_json(endereco, dados);
  if (!resposta.ok) {
    const aviso = document.querySelector("[data-empresa-erro]");
    aviso.textContent = texto_do_erro_das_empresas(resposta.dados.detail);
    aviso.hidden = false;
    return;
  }
  document.getElementById("janela-empresa").close();
  // A empresa nova é a escolhida: a Carteira congela nela, e o endereço a guarda (o F5 volta nela)
  if (!empresa_em_edicao) {
    estado_das_empresas.escolhendo = false;
    escrever_empresa_no_endereco(resposta.dados.empresa_id);
  }
  await recarregar_e_abrir(resposta.dados.empresa_id, "dados");
  if (empresa_em_edicao) {
    mostrar_aviso_das_empresas("Dados da " + resposta.dados.nome + " atualizados.");
  } else {
    mostrar_aviso_das_empresas(resposta.dados.nome + " entrou na carteira (" + resposta.dados.empresa_id +
      "). Agora convide a primeira pessoa do RH na aba Usuários.");
  }
}

// ===== Carregar as fichas =====

/**
 * Converte a ficha da API para o formato que o js/banco_empresas.js usa na lista e na busca.
 *
 * Recebe: ficha — a empresa da API. Devolve: o objeto da tela (a ficha, mais os campos da lista).
 */
function empresa_no_formato_da_tela(ficha) {
  // A lista mostra "setor · cidade"; a busca procura no nome, na cidade e no CNPJ.
  ficha.endereco_comercial = ficha.dados.endereco_comercial + " · " + ficha.cidade;
  ficha.cnpj = ficha.dados.cnpj;
  ficha.dominio = ficha.dados.dominio_email;
  return ficha;
}

// ===== Aba "Visão geral" (ADR-112) =====

// Todas as colunas do parâmetro vigente (buscadas uma vez só): a grade de funcionários mostra as obrigatórias e o
// detalhe de cada pessoa mostra todas (ADR-143).
let colunas_da_visao = [];

/**
 * Um cartão pequeno de número da Visão geral. Exemplo: (35, "funcionários cadastrados").
 *
 * Recebe: valor; legenda. Devolve: o elemento.
 */
function cartao_de_numero_da_visao(valor, legenda) {
  const cartao = criar_elemento("div", "numero-da-visao", "");
  cartao.append(criar_elemento("strong", "", String(valor)), criar_elemento("span", "", legenda));
  return cartao;
}

/**
 * Mostra a Visão geral da empresa aberta: os números (os mesmos que ela vê em Acompanhar cadastros) e a lista de
 * funcionários na grade do parâmetro, com a Situação primeiro (o "i" em cima da grade explica cada status).
 *
 * Recebe: empresa. Devolve: nada (espera a resposta do servidor). A abertura da lista fica registrada no servidor.
 */
async function mostrar_visao_geral_real(empresa) {
  document.querySelector("[data-visao-sem-servidor]").hidden = true;
  // As colunas do parâmetro, uma vez só
  if (colunas_da_visao.length === 0) {
    colunas_da_visao = await buscar_colunas_do_parametro("/api/banco/colunas_da_consulta");
  }
  const resposta = await pedir_das_empresas("/api/banco/empresas/" + encodeURIComponent(empresa.id) + "/visao_geral", {});
  // Outra empresa foi aberta enquanto esta carregava: não desenha a antiga por cima.
  if (estado_das_empresas.empresa_aberta !== empresa) {
    return;
  }
  if (!resposta.ok) {
    mostrar_aviso_das_empresas("Não foi possível abrir a visão geral: " + texto_do_erro_das_empresas(resposta.dados.detail));
    return;
  }
  const visao = resposta.dados;
  // Os números
  const numeros = document.querySelector("[data-numeros-da-visao]");
  numeros.replaceChildren(
    cartao_de_numero_da_visao(visao.resumo.cadastrados, "funcionários cadastrados"),
    cartao_de_numero_da_visao(visao.resumo.envios, "envios"),
    // As pessoas em análise pelo banco: o mesmo 2º cartão da empresa em Acompanhar cadastros
    cartao_de_numero_da_visao(visao.resumo.pessoas_em_analise, "pessoas em análise pelo banco"),
    cartao_de_numero_da_visao(visao.resumo.com_pendencia, "envios com pendência"));
  // As contas abertas: o número só existe depois que o banco manda o arquivo de contas; antes, um traço.
  if (visao.contas && visao.contas.texto) {
    let com_conta = "—";
    if (visao.contas.com_conta !== null && visao.contas.com_conta !== undefined) {
      com_conta = visao.contas.com_conta;
    }
    numeros.append(cartao_de_numero_da_visao(com_conta, visao.contas.texto));
  }
  // A grade: Situação primeiro, os campos obrigatórios do parâmetro (ADR-143), a Conta e o Incluído
  const colunas_da_grade_da_visao = colunas_obrigatorias(colunas_da_visao);
  montar_cabecalho_da_grade(document.querySelector("[data-cabeca-visao]"), colunas_da_grade_da_visao, ["Situação"],
    BLOCOS_FINAIS_DOS_FUNCIONARIOS);
  const corpo = document.querySelector("[data-corpo-visao]");
  corpo.replaceChildren();
  for (const pessoa of visao.funcionarios) {
    // O clique na pessoa abre o detalhe, com todos os campos do parâmetro
    corpo.append(montar_linha_de_funcionario(pessoa, colunas_da_grade_da_visao, function () {
      abrir_detalhe_do_funcionario(pessoa);
    }));
  }
  document.querySelector("[data-contador-visao]").textContent = visao.funcionarios.length + " funcionários da empresa";
  document.querySelector("[data-visao-sem-funcionarios]").hidden = visao.funcionarios.length > 0;
  // O "Baixar CSV" só aparece quando há alguém para baixar; o erro de uma empresa aberta antes não fica à mostra
  document.querySelector("[data-baixar-csv-visao]").hidden = visao.funcionarios.length === 0;
  document.querySelector("[data-erro-csv-visao]").hidden = true;
  document.querySelector("[data-visao-geral]").hidden = false;
}

/**
 * "Baixar CSV" da Visão geral: pede ao servidor o arquivo com os funcionários da empresa aberta, com todas as colunas
 * do cadastro (os obrigatórios, os opcionais que vieram e a situação), e o entrega ao navegador.
 *
 * Recebe: botao — o "Baixar CSV". Devolve: nada (espera o servidor). O arquivo sai só desta empresa, e o servidor
 * registra quem baixou, quando e quantas pessoas. Deu errado: o motivo aparece logo abaixo do botão.
 * Ex.: na Aurora (EMP001), o navegador baixa "funcionarios_EMP001.csv".
 */
async function baixar_csv_da_visao_geral(botao) {
  const empresa = estado_das_empresas.empresa_aberta;
  const aviso_de_erro = document.querySelector("[data-erro-csv-visao]");
  aviso_de_erro.hidden = true;
  // O botão fica parado enquanto o arquivo vem (dois cliques não pedem dois arquivos)
  botao.disabled = true;
  // try/catch/finally: servidor fora do ar vira o aviso, e o botão sempre volta a funcionar
  try {
    const resposta = await fetch("/api/banco/empresas/" + encodeURIComponent(empresa.id) + "/funcionarios/baixar");
    // Recusado (ex.: a empresa ainda sem funcionários): o motivo do servidor, perto do botão
    if (!resposta.ok) {
      const erro = await pedir_o_texto_do_erro(resposta);
      mostrar_erro_do_csv("Não foi possível baixar o arquivo: " + erro);
      return;
    }
    // O arquivo que o servidor mandou, entregue ao navegador por um link temporário
    const arquivo = await resposta.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(arquivo);
    link.download = "funcionarios_" + empresa.id + ".csv";
    link.click();
    // Libera a memória do arquivo temporário
    URL.revokeObjectURL(link.href);
  } catch (erro) {
    mostrar_erro_do_csv("Sem conexão com o servidor. Tente de novo.");
  } finally {
    botao.disabled = false;
  }
}

/**
 * O texto do erro de uma resposta recusada da API (o "detail" do JSON), ou um texto geral se ela não veio em JSON.
 *
 * Recebe: resposta — a do fetch, já recusada. Devolve: o texto. Ex.: {"detail": "Esta empresa ainda não tem
 * funcionários para baixar."} → esse mesmo texto.
 */
async function pedir_o_texto_do_erro(resposta) {
  // try/catch: a resposta pode não ser JSON (ex.: a página de erro de um servidor no meio do caminho)
  try {
    const dados = await resposta.json();
    return texto_do_erro_das_empresas(dados.detail);
  } catch (erro) {
    return "tente de novo em instantes.";
  }
}

/**
 * Mostra o erro do "Baixar CSV" logo abaixo do botão (e não no aviso do alto, que fica fora da vista).
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_erro_do_csv(texto) {
  const aviso = document.querySelector("[data-erro-csv-visao]");
  aviso.textContent = texto;
  aviso.hidden = false;
}

// O que o detalhe diz no lugar da conta enquanto o banco não a envia (a conta chega ao final da integração, ADR-113).
const CONTA_AINDA_NAO_ENVIADA = "Ainda não enviada pelo banco";

/**
 * O quadro "Informações bancárias" do detalhe: a conta que o banco enviou ao final da integração, ou o aviso de que ela
 * ainda não foi enviada.
 *
 * Recebe: pessoa — um funcionário da Visão geral (codigo_banco, agencia, conta, conta_aberta_em). Devolve: o <section>.
 * Ex.: {conta: "12345-0", agencia: "0001", ...} → "Agência 0001", "Conta salário 12345-0"...
 * Com a conta enviada, um valor vazio vira um traço: o código do banco saiu do arquivo de contas (ADR-149) e só as
 * contas gravadas antes o têm.
 */
function informacoes_bancarias_do_detalhe(pessoa) {
  const secao = secao_do_detalhe("Informações bancárias");
  const lista = secao.querySelector("dl");
  const itens = [
    ["Código do banco", pessoa.codigo_banco],
    ["Agência", pessoa.agencia],
    ["Conta salário", pessoa.conta],
    ["Aberta em", grade_data_brasileira_se_for_data(pessoa.conta_aberta_em || "")],
  ];
  for (const [nome, valor] of itens) {
    const nome_do_item = document.createElement("dt");
    nome_do_item.textContent = nome;
    const valor_do_item = document.createElement("dd");
    // Sem a conta, nenhum dos quatro existe ainda: o aviso no lugar
    valor_do_item.textContent = CONTA_AINDA_NAO_ENVIADA;
    if (pessoa.conta && valor) {
      valor_do_item.textContent = valor;
    } else if (pessoa.conta) {
      // A conta chegou, mas este valor não veio no arquivo (o código do banco, desde o ADR-149): um traço
      valor_do_item.textContent = "—";
    }
    lista.append(nome_do_item, valor_do_item);
  }
  return secao;
}

/**
 * Abre a janela com o detalhe de um funcionário da Visão geral: todos os campos do parâmetro, agrupados, com
 * "Informação não encontrada" no que veio em branco (a grade mostra só os obrigatórios; ADR-143), e a conta no banco.
 *
 * Recebe: pessoa — um funcionário da Visão geral (os campos do parâmetro, situacao, a conta, incluido_em e
 * incluido_por). Devolve: nada. O detalhe usa os dados que já vieram na lista, cuja abertura ficou registrada no
 * servidor (quem do banco viu os dados das pessoas desta empresa).
 */
function abrir_detalhe_do_funcionario(pessoa) {
  const janela = document.getElementById("janela-detalhe-funcionario");
  // O cabeçalho: as iniciais, a situação, o nome (ou o CPF, quando o nome não veio) e o resumo de uma linha
  janela.querySelector("[data-detalhe-iniciais]").textContent = iniciais_do_nome(pessoa.nome_completo);
  janela.querySelector("[data-detalhe-situacao]").textContent = pessoa.situacao || "Cadastrado";
  janela.querySelector("[data-detalhe-nome]").textContent = titulo_do_detalhe(pessoa.nome_completo, pessoa.cpf);
  // Quando e por quem a empresa incluiu a pessoa (ex.: "incluído em 24/09/2026 por rh.aurora")
  let quem_incluiu = "";
  if (pessoa.incluido_em) {
    quem_incluiu = "incluído em " + grade_data_brasileira(pessoa.incluido_em);
    if (pessoa.incluido_por) {
      quem_incluiu = quem_incluiu + " por " + pessoa.incluido_por;
    }
  }
  janela.querySelector("[data-detalhe-resumo]").textContent = juntar_partes_do_resumo([pessoa.cargo, quem_incluiu]);
  // Os grupos do parâmetro (todos os campos) e, no fim, a conta no banco
  const grupos = janela.querySelector("[data-detalhe-grupos]");
  grupos.replaceChildren(...grupos_do_detalhe(colunas_da_visao, pessoa));
  // O que a IA guardou sem rótulo, logo depois dos campos: só quando há alguma (ADR-143, Parte 1)
  acrescentar_informacoes_sem_rotulo(grupos, pessoa);
  grupos.append(informacoes_bancarias_do_detalhe(pessoa));
  janela.showModal();
}

/**
 * Busca as fichas de novo (depois de uma mudança) e abre a empresa, na aba informada.
 *
 * Recebe: empresa_id; aba — "contas", "dados", "usuarios" ou "catalogo". Devolve: nada.
 */
async function recarregar_e_abrir(empresa_id, aba) {
  const resposta = await pedir_das_empresas("/api/banco/empresas", {});
  if (!resposta.ok) {
    return;
  }
  EMPRESAS.length = 0;
  for (const ficha of resposta.dados) {
    EMPRESAS.push(empresa_no_formato_da_tela(ficha));
  }
  abrir_empresa(achar_empresa(empresa_id) || EMPRESAS[0]);
  trocar_aba_da_ficha(aba);
}

/**
 * Busca as fichas reais e troca as empresas de exemplo por elas.
 *
 * Recebe: nada. Devolve: nada. Servidor fora do ar ou página aberta como arquivo: fica o exemplo.
 */
async function carregar_empresas_de_verdade() {
  // Aberta como arquivo: não há servidor.
  if (!window.location.protocol.startsWith("http")) {
    return;
  }
  // try/catch: servidor fora do ar não quebra a tela.
  let fichas = null;
  try {
    const resposta = await fetch("/api/banco/empresas");
    // Recusado: nenhuma empresa de exemplo fica na tela (nem a barra cinza para sempre).
    if (!resposta.ok) {
      mostrar_empresas_indisponiveis();
      return;
    }
    fichas = await resposta.json();
  } catch (erro) {
    // Servidor fora do ar: o mesmo aviso, sem o exemplo.
    mostrar_empresas_indisponiveis();
    return;
  }
  // Troca as empresas de exemplo pelas reais (esvazia a lista e põe as novas).
  EMPRESAS.length = 0;
  for (const ficha of fichas) {
    EMPRESAS.push(empresa_no_formato_da_tela(ficha));
  }
  // A partir daqui, os desvios do js/banco_empresas.js usam as funções deste arquivo.
  empresas_reais_carregadas = true;
  document.querySelector("[data-formulario-empresa]").addEventListener("submit", salvar_empresa);
  // Os CNPJs de filiais e do grupo: adicionar pelo formulário; tirar pelo botão de cada linha.
  document.querySelector("[data-formulario-cnpj]").addEventListener("submit", adicionar_cnpj_de_verdade);
  document.querySelector("[data-corpo-cnpjs]").addEventListener("click", function (evento) {
    const botao = evento.target.closest("[data-tirar-cnpj]");
    if (botao) {
      tirar_cnpj_de_verdade(botao);
    }
  });
  trocar_cabecalho_dos_usuarios();
  trocar_cabecalho_do_catalogo();
  // Abre a empresa pedida no endereço (ex.: ?empresa=EMP002); senão, a primeira.
  const pedida = achar_empresa(new URLSearchParams(window.location.search).get("empresa"));
  // A pedida no endereço já foi escolhida (ex.: vinda do Início, ou o F5 depois de escolher): a Carteira começa
  // congelada nela. Sem pedido, a lista aparece (js/banco_empresas.js).
  estado_das_empresas.escolhendo = pedida === null;
  if (pedida) {
    abrir_empresa(pedida);
  } else {
    abrir_empresa(EMPRESAS[0]);
  }
  // A aba pedida no endereço (ex.: ?aba=conversa, vindo do Início), com a função do js/banco_empresas.js.
  abrir_aba_pedida_no_endereco();
  // As fichas de verdade já estão na tela: a lista e a ficha aberta aparecem (js/carregando_dados.js).
  marcar_todos_como_carregados("[data-lista-empresas], [data-ficha-empresa]");
}

/**
 * O servidor não respondeu: a lista diz que não foi possível carregar e a ficha de exemplo some. Nunca fica uma
 * empresa de exemplo à mostra.
 *
 * Recebe: nada. Devolve: nada.
 */
function mostrar_empresas_indisponiveis() {
  // Esvazia as empresas de exemplo: nenhuma busca depois traz o exemplo de volta.
  EMPRESAS.length = 0;
  // A lista ganha o aviso no lugar das empresas.
  const lista = document.querySelector("[data-lista-empresas]");
  lista.replaceChildren(criar_elemento("li", "painel-vazio", "Não foi possível carregar agora. Atualize a página em instantes."));
  marcar_como_carregado(lista);
  // A ficha (a da empresa de exemplo) some da tela.
  const ficha = document.querySelector("[data-ficha-empresa]");
  ficha.hidden = true;
  marcar_como_carregado(ficha);
  // O que espera dentro da ficha (a conversa e as contas abertas) também sai da espera: a ficha inteira está escondida,
  // e nada fica com a barra de "carregando" para sempre.
  marcar_todos_como_carregados("[data-ficha-empresa] [data-aguarda-dado], [data-ficha-empresa] [data-aguarda-bloco]");
}

// Quando o HTML terminar de carregar, troca o exemplo pelos dados reais (se houver servidor).
document.addEventListener("DOMContentLoaded", carregar_empresas_de_verdade);
