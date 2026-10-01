/*
  login.js — interações da tela de login (front ligado à aplicação, ADR-69).

  Para que serve:
    1. o botão "Mostrar" deixa ver a senha digitada (e "Ocultar" esconde de novo);
    2. o botão "Entrar" manda usuário e senha para a API (/api/entrar). Se conferir, a API grava o cookie da
       sessão e diz a página inicial do perfil (EMPRESA ou BANCO), e a tela vai para lá. Se não
       conferir, mostra "Usuário ou senha incorretos.";
    3. a sessão vale 8 horas e acaba ao fechar o navegador. Não há "Lembrar de mim" (ADR-100): ao abrir a tela, o
       usuário que uma versão antiga guardava neste navegador é apagado;
    4. "Esqueci minha senha" abre uma janela que explica o caminho: pedir uma senha
       provisória nova ao especialista do banco; ao entrar com ela, a pessoa cria uma senha só sua (ADR-109). A
       aplicação não manda e-mail, então a tela não pede nada: só explica.

  Segurança: quem confere a senha é o servidor, nunca o navegador. O cookie da sessão é "httponly": este
  JavaScript nem consegue ler o ingresso, só o servidor.
*/

/**
 * Alterna a senha entre visível e escondida.
 *
 * Recebe: nada (lê o campo e o botão pela página). Devolve: nada.
 * Exemplo: senha escondida ("••••") → clique → senha visível ("minhasenha") e o botão vira "Ocultar".
 */
function alternar_visibilidade_da_senha() {
  // Caixa onde a senha é digitada.
  const campo_senha = document.getElementById("campo-senha");
  // Botão "Mostrar/Ocultar".
  const botao_mostrar = document.getElementById("botao-mostrar-senha");
  // Verdadeiro se a senha está escondida agora (tipo "password" mostra bolinhas).
  const senha_esta_escondida = campo_senha.type === "password";

  // Se está escondida, mostra como texto normal.
  if (senha_esta_escondida) {
    campo_senha.type = "text";
    botao_mostrar.textContent = "Ocultar";
  } else {
    // Se está visível, volta a esconder.
    campo_senha.type = "password";
    botao_mostrar.textContent = "Mostrar";
  }

  // Avisa leitores de tela se o botão está "ligado" (senha visível) ou não (acessibilidade).
  botao_mostrar.setAttribute("aria-pressed", String(senha_esta_escondida));
}

/**
 * Mostra o aviso de login recusado.
 *
 * Recebe: texto. Devolve: nada.
 */
function mostrar_aviso_de_login(texto) {
  // O parágrafo do aviso.
  const aviso = document.getElementById("aviso-login");
  // Escreve o texto (como texto puro) e mostra.
  aviso.textContent = texto;
  aviso.hidden = false;
}

// Onde o antigo "Lembrar de mim" guardava o usuário neste navegador (ADR-100)
const CHAVE_DO_ANTIGO_USUARIO_LEMBRADO = "integra_folha_usuario_lembrado";

/**
 * Apaga o usuário que o antigo "Lembrar de mim" guardou neste navegador (limpeza de quem marcou a caixa antes).
 *
 * Recebe: nada. Devolve: nada.
 * try/catch: navegador em modo privado pode recusar o acesso ao armazenamento; aí não há nada para apagar.
 */
function apagar_o_usuario_lembrado_antes() {
  try {
    // Tira a chave antiga; se ela não existe, o navegador simplesmente não faz nada
    window.localStorage.removeItem(CHAVE_DO_ANTIGO_USUARIO_LEMBRADO);
  } catch (erro) {
    // Sem acesso ao armazenamento: segue normalmente
  }
}

/**
 * Abre a janela "Esqueci minha senha", que explica como conseguir uma senha nova.
 *
 * Recebe: evento — o clique no link. Devolve: nada.
 * O link tem href="#": sem o preventDefault, o navegador pularia para o topo e poria "#" no endereço.
 */
function abrir_janela_esqueci_a_senha(evento) {
  // Impede o pulo para "#".
  evento.preventDefault();
  // Abre a janela por cima da tela, escurecendo o fundo.
  document.getElementById("janela-esqueci-a-senha").showModal();
}

/**
 * Fecha a janela "Esqueci minha senha" (botão "Entendi").
 *
 * Recebe: nada. Devolve: nada. O Esc também fecha: é o próprio <dialog> que faz.
 */
function fechar_janela_esqueci_a_senha() {
  document.getElementById("janela-esqueci-a-senha").close();
}

/**
 * Devolve o foco ao link quando a janela fecha (pelo "Entendi" ou pelo Esc), para quem navega pelo teclado.
 *
 * Recebe: nada. Devolve: nada.
 */
function voltar_o_foco_ao_link_da_senha() {
  document.getElementById("link-esqueci-a-senha").focus();
}

/**
 * Trata o clique em "Entrar": manda usuário e senha para a API e, se der certo, abre o portal do perfil.
 *
 * Recebe: evento — o "aviso" do navegador de que o formulário foi enviado.
 * Devolve: nada. "async" quer dizer que a função espera a resposta do servidor sem travar a tela.
 */
async function entrar_no_portal(evento) {
  // Impede o envio padrão do formulário (que recarregaria a página e colocaria a senha no endereço).
  evento.preventDefault();
  // O formulário e o que foi digitado.
  const formulario = document.getElementById("formulario-login");
  const usuario = formulario.elements["usuario"].value;
  const senha = formulario.elements["senha"].value;
  // Esconde um aviso de uma tentativa anterior.
  document.getElementById("aviso-login").hidden = true;

  // Pede à API para entrar. "fetch" é o jeito do navegador de conversar com o servidor.
  // try/catch: se o servidor estiver fora do ar, a tela avisa em vez de quebrar.
  try {
    const resposta = await fetch("/api/entrar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario: usuario, senha: senha }),
    });
    // O servidor respondeu com os dados (ou com o erro), em JSON.
    const dados = await resposta.json();
    // Deu certo: vai para a página inicial do perfil.
    if (resposta.ok) {
      window.location.href = dados.pagina_inicial;
      return;
    }
    // Recusado: mostra a mensagem do servidor ("Usuário ou senha incorretos.").
    mostrar_aviso_de_login(dados.detail);
  } catch (erro) {
    // Sem resposta do servidor.
    mostrar_aviso_de_login("Não foi possível falar com o servidor. Tente de novo em instantes.");
  }
}

/**
 * Liga os botões da tela às funções acima.
 *
 * Recebe: nada. Devolve: nada.
 * É chamada uma vez, quando a página termina de carregar.
 */
function preparar_tela_de_login() {
  // No clique em "Mostrar/Ocultar", alterna a senha.
  document.getElementById("botao-mostrar-senha").addEventListener("click", alternar_visibilidade_da_senha);
  // No envio do formulário (clique em "Entrar" ou Enter), entra no portal.
  document.getElementById("formulario-login").addEventListener("submit", entrar_no_portal);
  // "Esqueci minha senha": abre a janela que explica o caminho; "Entendi" fecha; ao fechar, o foco volta ao link.
  document.getElementById("link-esqueci-a-senha").addEventListener("click", abrir_janela_esqueci_a_senha);
  document.getElementById("botao-entendi-a-senha").addEventListener("click", fechar_janela_esqueci_a_senha);
  document.getElementById("janela-esqueci-a-senha").addEventListener("close", voltar_o_foco_ao_link_da_senha);
  // Limpeza: o usuário que o antigo "Lembrar de mim" guardou neste navegador
  apagar_o_usuario_lembrado_antes();
}

// Quando o HTML terminar de carregar, prepara a tela.
document.addEventListener("DOMContentLoaded", preparar_tela_de_login);
