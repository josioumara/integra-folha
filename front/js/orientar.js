/*
  orientar.js — o bloco "Ajude a IA a acertar", dentro da conferência da lista, na tela de cadastro.
  Fica na conferência (recolhido) porque é conferindo a lista que a pessoa percebe o erro da IA.

  Para que serve: a empresa conhece o próprio arquivo melhor do que a IA. Se a IA deixou de fora algo que
  deveria usar, ou entendeu uma coluna de um jeito diferente, a empresa pode orientar a releitura:
    1. "O que a IA deixou de fora": as colunas ignoradas, com uma amostra do conteúdo e o motivo. O botão
       "Usar esta coluna" deixa escolher o campo do banco; a IA relê SÓ aquela coluna (rápido e barato).
    2. "Dizer algo à IA sobre este arquivo": um texto livre; "Reler com a minha orientação" faz a IA reler o
       envio levando a orientação em conta. No máximo 2 releituras por envio (cada uma custa uma chamada de IA).
  Nome técnico: refinamento com feedback humano ("humano no circuito"). A conferência mostra o que mudou.

  Cuidados (os mesmos da ferramenta real):
    - O texto livre vai para a IA: passa antes pelo guardrail de injeção. Pedido para ignorar as regras não
      tem efeito e não gasta releitura.
    - A orientação muda a INTERPRETAÇÃO do arquivo; nunca inventa dado nem pula as validações do banco.
    - Tudo fica registrado (quem pediu, o texto e o que mudou), e a correção aprovada vira histórico para os
      próximos envios da empresa.

  ATENÇÃO — protótipo: aqui a "IA" responde por palavras-chave, só para desenhar a experiência. No sistema real,
  a orientação vai para o Interpretador junto com o arquivo. Usa do guardrail.js: parece_tentativa_de_burla;
  do cadastrar.js: envio_atual, esperar,
  mostrar_ia_pensando e escrever_mensagem; e do conferir.js: colunas_adicionadas, campos_confirmados_pela_empresa,
  email_a_partir_do_nome, PESSOAS_DA_INCLUSAO e montar_tabela_da_conferencia.
*/

// ===== Dados =====

// Quantas releituras com orientação cada envio pode ter.
const LIMITE_DE_RELEITURAS = 2;

// Onde as respostas da IA deste bloco aparecem (a conversa pequena dentro do bloco).
const ID_DA_CONVERSA_DE_ORIENTACAO = "conversa-orientacao";

// Campos do layout que o arquivo não trouxe e que a coluna ignorada poderia preencher.
const CAMPOS_QUE_A_COLUNA_PODE_PREENCHER = [
  { campo: "email_pessoal", rotulo: "E-mail pessoal" },
  { campo: "telefone_residencial", rotulo: "Telefone fixo" },
  { campo: "nome_mae", rotulo: "Nome da mãe" },
  { campo: "estado_civil", rotulo: "Estado civil" },
  { campo: "escolaridade", rotulo: "Escolaridade" },
];

// As linhas (do arquivo) em que a coluna "Obs RH" traz um e-mail pessoal. Nas outras 10, ela está em branco.
const LINHAS_COM_EMAIL_NA_OBS = [1, 2, 3, 4, 6, 8, 9, 10, 12, 13, 14, 16, 18, 19, 21, 22, 24, 27];

// ===== Estado =====

// Quantas releituras com orientação ainda sobram neste envio.
let releituras_restantes = LIMITE_DE_RELEITURAS;
// Se a coluna "Obs RH" já foi aproveitada (para não aproveitar duas vezes).
let obs_rh_ja_aproveitada = false;

// ===== Mostrar o bloco =====

/**
 * Ajusta o bloco "Ajude a IA a acertar" ao cenário do envio (chamada pelo cadastrar.js, em mostrar_resultado).
 * O bloco fica dentro da conferência: aparece quando a pessoa abre a lista para conferir.
 *
 * Recebe: nada. Devolve: nada.
 * No cenário "conversa" não há coluna ignorada que sirva (só "Bom dia" e "kkk"): fica só o texto livre, e o selo
 * "1 coluna deixada de fora" some do resumo do bloco.
 */
function preparar_ajude_a_ia() {
  const e_tabela = envio_atual.cenario.id_do_resultado === "resultado-tabela";
  document.querySelector("[data-colunas-ignoradas]").hidden = !e_tabela;
  document.querySelector("[data-selo-deixadas-de-fora]").hidden = !e_tabela;
  atualizar_botao_de_releitura();
}

/**
 * Atualiza o botão "Reler com a minha orientação" com quantas releituras sobram (e desliga no fim).
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_botao_de_releitura() {
  const botao = document.querySelector("[data-reler-com-orientacao]");
  const campo_de_texto = document.querySelector("[data-texto-orientacao]");
  botao.textContent = "Reler com a minha orientação (" + releituras_restantes + " de " + LIMITE_DE_RELEITURAS + ")";
  // Sem releituras: o texto e o botão desligam, e aparece a explicação.
  const acabou = releituras_restantes === 0;
  botao.disabled = acabou;
  campo_de_texto.disabled = acabou;
  document.querySelector("[data-limite-releituras]").hidden = !acabou;
}

// ===== Caminho 1: usar uma coluna que a IA deixou de fora =====

/**
 * Aproveita a coluna "Obs RH" no campo escolhido pela pessoa.
 *
 * Recebe: nada (o campo vem da lista ao lado do botão). Devolve: nada.
 * Só "E-mail pessoal" combina com o conteúdo da coluna; com outro campo, a IA explica por que não usou.
 */
async function usar_coluna_ignorada() {
  const lista = document.querySelector("[data-campo-da-coluna]");
  const rotulo_escolhido = lista.options[lista.selectedIndex].text;
  // A pessoa ainda não escolheu o campo.
  if (!lista.value) {
    await escrever_mensagem("Escolha na lista qual informação a coluna \"Obs RH\" traz.", "alerta", ID_DA_CONVERSA_DE_ORIENTACAO);
    return;
  }
  await mostrar_ia_pensando(ID_DA_CONVERSA_DE_ORIENTACAO);
  // O conteúdo da coluna são e-mails: só o campo "E-mail pessoal" combina.
  if (lista.value !== "email_pessoal") {
    await escrever_mensagem("Reli a coluna \"Obs RH\" como " + rotulo_escolhido + ", mas o que tem nela são e-mails, não " +
      rotulo_escolhido.toLowerCase() + ". Não usei, para não gravar dado errado. Escolha outro campo ou me explique no texto abaixo.",
      "alerta", ID_DA_CONVERSA_DE_ORIENTACAO);
    return;
  }
  aproveitar_obs_rh_como_email_pessoal();
  await escrever_mensagem("Entendi: a coluna \"Obs RH\" traz o e-mail pessoal. Reli só essa coluna: " +
    LINHAS_COM_EMAIL_NA_OBS.length + " funcionários ganharam o e-mail pessoal; os outros " +
    (PESSOAS_DA_INCLUSAO.length - LINHAS_COM_EMAIL_NA_OBS.length) +
    " estavam em branco e continuam assim (não vou inventar). Confira na lista: a coluna nova está em azul.",
    "sucesso", ID_DA_CONVERSA_DE_ORIENTACAO);
}

/**
 * Coloca a coluna "E-mail pessoal" (vinda da "Obs RH") na conferência e marca a coluna como aproveitada.
 *
 * Recebe: nada. Devolve: nada.
 */
function aproveitar_obs_rh_como_email_pessoal() {
  // Não aproveita duas vezes.
  if (obs_rh_ja_aproveitada) {
    return;
  }
  obs_rh_ja_aproveitada = true;
  // O e-mail de cada linha que tem e-mail na coluna, e o texto como estava no arquivo.
  const valores = {};
  const originais = {};
  for (const numero_da_linha of LINHAS_COM_EMAIL_NA_OBS) {
    const pessoa = PESSOAS_DA_INCLUSAO[numero_da_linha - 1];
    const email = email_a_partir_do_nome(pessoa.nome, "gmail.com");
    valores[numero_da_linha] = email;
    originais[numero_da_linha] = "Obs RH: \"e-mail pessoal " + email + "\"";
  }
  colunas_adicionadas.push({
    coluna: { campo: "email_pessoal", rotulo: "E-mail pessoal", no_arquivo: "Obs RH", confianca: "alta" },
    valores: valores,
    originais: originais,
  });
  // O cartão da coluna ignorada passa a dizer que ela foi usada.
  document.querySelector("[data-situacao-obs-rh]").className = "selo selo-sucesso selo-pequeno";
  document.querySelector("[data-situacao-obs-rh]").textContent = "Usada como e-mail pessoal";
  document.querySelector("[data-acoes-obs-rh]").hidden = true;
  // O selo do resumo do bloco deixa de chamar atenção: não sobrou coluna deixada de fora.
  document.querySelector("[data-selo-deixadas-de-fora]").hidden = true;
  atualizar_conferencia_se_aberta();
}

// ===== Caminho 2: orientação em texto livre =====

/**
 * Relê o envio com a orientação da pessoa. No protótipo, a resposta sai de palavras-chave do texto.
 *
 * Recebe: nada (o texto vem da caixa). Devolve: nada.
 */
async function reler_com_orientacao() {
  const caixa = document.querySelector("[data-texto-orientacao]");
  const orientacao = caixa.value.trim();
  // Sem texto, não há o que reler.
  if (!orientacao) {
    await escrever_mensagem("Escreva o que eu devo saber sobre o seu arquivo.", "alerta", ID_DA_CONVERSA_DE_ORIENTACAO);
    return;
  }
  // A orientação da pessoa aparece na conversa, como uma fala dela.
  mostrar_fala_da_pessoa(orientacao);
  caixa.value = "";
  await mostrar_ia_pensando(ID_DA_CONVERSA_DE_ORIENTACAO);
  // Guardrail: pedido para ignorar as regras não tem efeito e não gasta releitura.
  if (parece_tentativa_de_burla(orientacao)) {
    await escrever_mensagem("Não posso seguir essa orientação: ela pede para deixar de lado as regras do banco. " +
      "Nada foi alterado, e isso não gastou uma releitura.", "alerta", ID_DA_CONVERSA_DE_ORIENTACAO);
    return;
  }
  // Daqui em diante é uma releitura de verdade: gasta uma das duas.
  releituras_restantes = releituras_restantes - 1;
  atualizar_botao_de_releitura();
  await responder_a_orientacao(orientacao.toLowerCase());
}

/**
 * A resposta da IA a uma orientação, conforme o assunto (protótipo: por palavras-chave).
 *
 * Recebe: orientacao — o texto em minúsculas. Devolve: nada.
 */
async function responder_a_orientacao(orientacao) {
  // Fala da coluna "Obs RH" ou de e-mail: aproveita a coluna como e-mail pessoal.
  if (orientacao.includes("obs") || orientacao.includes("e-mail") || orientacao.includes("email")) {
    // Se a coluna já tinha sido aproveitada pelo caminho 1, a IA só avisa.
    if (obs_rh_ja_aproveitada) {
      await escrever_mensagem("A coluna \"Obs RH\" já está sendo usada como e-mail pessoal. Nada mais mudou.",
        "normal", ID_DA_CONVERSA_DE_ORIENTACAO);
      return;
    }
    aproveitar_obs_rh_como_email_pessoal();
    await escrever_mensagem("Reli o arquivo com a sua orientação: a coluna \"Obs RH\" virou o e-mail pessoal de " +
      LINHAS_COM_EMAIL_NA_OBS.length + " funcionários. Confira na lista, em azul.", "sucesso", ID_DA_CONVERSA_DE_ORIENTACAO);
    return;
  }
  // Fala da coluna "Início": a empresa confirma que é a admissão; a coluna perde o "confira".
  if (orientacao.includes("início") || orientacao.includes("inicio") || orientacao.includes("admissão")) {
    campos_confirmados_pela_empresa.data_admissao = true;
    atualizar_conferencia_se_aberta();
    await escrever_mensagem("Obrigado! Mantive \"Início\" como a data de admissão, agora confirmada por você. " +
      "Na lista, a coluna Admissão troca o \"confira\" por \"confirmada por você\".", "sucesso", ID_DA_CONVERSA_DE_ORIENTACAO);
    return;
  }
  // Qualquer outro assunto: a IA relê, mas não acha o que mudar, e diz isso com honestidade.
  await escrever_mensagem("Reli o arquivo com a sua orientação, mas não encontrei nada para mudar a partir dela. " +
    "Se algo ainda estiver errado, corrija direto na lista da conferência.", "normal", ID_DA_CONVERSA_DE_ORIENTACAO);
}

/**
 * Mostra o texto da pessoa na conversa do bloco, alinhado à direita (como numa conversa de mensagens).
 *
 * Recebe: texto — a orientação. Devolve: nada.
 */
function mostrar_fala_da_pessoa(texto) {
  const fala = document.createElement("div");
  fala.className = "fala-da-pessoa";
  fala.textContent = texto;
  document.getElementById(ID_DA_CONVERSA_DE_ORIENTACAO).appendChild(fala);
}

/**
 * Refaz a tabela da conferência, se ela já estiver aberta, para mostrar o que a orientação mudou.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_conferencia_se_aberta() {
  if (!document.getElementById("etapa-conferencia").hidden) {
    montar_tabela_da_conferencia();
  }
}

// ===== Ligando tudo =====

/**
 * Liga os botões do bloco. É chamada quando a página termina de carregar.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_orientacao() {
  document.querySelector("[data-usar-coluna]").addEventListener("click", usar_coluna_ignorada);
  document.querySelector("[data-reler-com-orientacao]").addEventListener("click", reler_com_orientacao);
  // A lista de campos que a coluna ignorada pode preencher, montada a partir dos dados acima.
  const lista = document.querySelector("[data-campo-da-coluna]");
  for (const opcao of CAMPOS_QUE_A_COLUNA_PODE_PREENCHER) {
    const item = document.createElement("option");
    item.value = opcao.campo;
    item.textContent = opcao.rotulo;
    lista.appendChild(item);
  }
}

// Espera o HTML carregar inteiro antes de ligar tudo.
document.addEventListener("DOMContentLoaded", preparar_orientacao);
