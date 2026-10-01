/*
  data_da_versao.js — o rótulo "Atualizado em 29/09/2026 às 14:30" no fim de todas as telas (ADR-133).

  Para que serve: mostrar, no rodapé, quando a aplicação foi atualizada pela última vez. A data é a da
  VERSÃO que o servidor está rodando (o último commit), e quem a descobre é o servidor, na rota /api/versao, que é a
  fonte única para todas as telas (inclusive a de login, sem entrar).

  Como funciona:
    1. cada tela tem, no rodapé, um parágrafo vazio e ESCONDIDO com a marca "data-data-da-versao";
    2. este script pede o texto ao servidor;
    3. chegou um texto: ele é escrito no parágrafo, que aparece;
    4. sem texto (o servidor não sabe a data) ou sem resposta (erro, servidor fora do ar): o parágrafo continua
       escondido. Nunca aparece uma data de exemplo nem inventada.

  Oculto nesta versão (ADR-148): o parágrafo de cada tela tem a marca "data-oculto-nesta-versao", e este script pula
  os marcados. Sem nenhum lugar livre, ele nem pergunta a data ao servidor, e o rótulo não aparece em tela nenhuma.
  Para voltar a mostrar, basta tirar a marca das telas.
*/

// Pede o texto ao servidor e preenche os rótulos da tela
async function mostrar_data_da_versao() {
  // Os lugares do rótulo nesta tela (em geral, um só, no rodapé), menos os ocultos nesta versão
  const lugares_do_rotulo = document.querySelectorAll("[data-data-da-versao]:not([data-oculto-nesta-versao])");
  // A tela não tem o lugar (ou ele está oculto): nada a fazer (e nem pergunta ao servidor)
  if (lugares_do_rotulo.length === 0) {
    return;
  }
  // O texto do rótulo (continua vazio se algo der errado)
  let texto_do_rotulo = null;
  // try/catch: sem rede ou com o servidor fora do ar, a tela segue normal, só sem o rótulo
  try {
    // Pede o texto; "no-store" faz o navegador perguntar de novo em vez de usar uma resposta guardada
    const resposta = await fetch("/api/versao", { cache: "no-store" });
    // Só uma resposta certa (200) é lida
    if (resposta.ok) {
      // O JSON é { "texto": "Atualizado em ..." } ou { "texto": null }
      const dados = await resposta.json();
      texto_do_rotulo = dados.texto;
    }
  } catch (erro) {
    // Sem resposta: o rótulo fica escondido
    texto_do_rotulo = null;
  }
  // Sem texto (ou algo que não é texto): o rótulo fica escondido
  if (typeof texto_do_rotulo !== "string" || texto_do_rotulo === "") {
    return;
  }
  // Escreve o texto em cada lugar e mostra o parágrafo
  for (const lugar of lugares_do_rotulo) {
    // textContent: o texto entra como texto, nunca como código da página
    lugar.textContent = texto_do_rotulo;
    // Tira o "escondido"
    lugar.hidden = false;
  }
}

// Roda quando a página termina de montar (o script fica no fim da página, mas assim vale em qualquer lugar)
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mostrar_data_da_versao);
} else {
  mostrar_data_da_versao();
}
