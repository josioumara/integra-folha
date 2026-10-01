/*
  levar_ao_endomarketing.js — leva o endereço antigo "banco_beneficios.html" para as guias do Endomarketing.

  Para que serve: a tela "Benefícios e KBs" foi aposentada (ADR-125). As KBs ficam nas
  guias da aba Endomarketing: "Base de Conhecimento" (as de cada empresa) e "Regras gerais" (as que valem para todas).
  Quem ainda abrir o endereço antigo, por um favorito ou um link velho, é levado para o lugar certo:
    - banco_beneficios.html?dono=EMP001    → banco_endomarketing.html?empresa=EMP001&aba=base
    - banco_beneficios.html?dono=GERAL     → banco_endomarketing.html?aba=regras
    - banco_beneficios.html (sem dono)     → banco_endomarketing.html?aba=regras
  (as regras gerais aparecem depois que a pessoa escolhe a empresa, como tudo nas guias.)
*/

/**
 * Monta o endereço novo a partir do "?dono=" do endereço antigo.
 *
 * Recebe: nada (lê o endereço da página). Devolve: o endereço novo, em texto.
 * Exemplo: "?dono=EMP002" → "banco_endomarketing.html?empresa=EMP002&aba=base".
 */
function endereco_no_endomarketing() {
  // O dono pedido no endereço antigo (null quando não tem).
  const dono = new URLSearchParams(window.location.search).get("dono");
  // Uma empresa (código como "EMP001"): a guia Base de Conhecimento dela.
  if (dono && /^EMP\d{3}$/.test(dono)) {
    return "banco_endomarketing.html?empresa=" + encodeURIComponent(dono) + "&aba=base";
  }
  // As diretrizes gerais, o Santander ou nenhum dono: a guia Regras gerais.
  return "banco_endomarketing.html?aba=regras";
}

// replace troca o endereço sem deixar a página antiga no "Voltar" do navegador.
window.location.replace(endereco_no_endomarketing());
