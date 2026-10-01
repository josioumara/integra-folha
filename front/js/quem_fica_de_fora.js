/*
 * Quem fica de fora do envio (envio parcial, ADR-126).
 *
 * Para que serve: quando a empresa manda de novo alguém que já foi ao banco (num envio ainda em análise) ou que já
 * está cadastrado, essa linha não vai de novo, e o envio segue só com as outras pessoas. As duas telas que mostram a
 * lista que vai para o banco (a conferência de "Cadastrar funcionários" e a janela "Pronto para enviar ao banco" de
 * "Acompanhar cadastros") usam este bloco para dizer quem ficou de fora e por quê.
 *
 * Os dados vêm do servidor, em "ficam_de_fora": [{linha, nome, cpf, motivo}] (services/cadastro.py).
 */

/**
 * O número com a palavra certa no singular ou no plural.
 *
 * Recebe: quantidade; singular; plural. Devolve: o texto. Ex.: (1, "pessoa", "pessoas") → "1 pessoa";
 * (3, "pessoa", "pessoas") → "3 pessoas".
 */
function quantidade_no_singular_ou_plural(quantidade, singular, plural) {
  if (quantidade === 1) {
    return "1 " + singular;
  }
  return quantidade + " " + plural;
}

/**
 * Cria um elemento com classe e texto (o texto entra como texto, nunca como HTML).
 *
 * Recebe: etiqueta (ex.: "li"); classe ("" = sem classe); texto. Devolve: o elemento.
 */
function criar_elemento_de_quem_fica_de_fora(etiqueta, classe, texto) {
  const elemento = document.createElement(etiqueta);
  if (classe) {
    elemento.className = classe;
  }
  elemento.textContent = texto;
  return elemento;
}

/**
 * O título do bloco. Ex.: 2 → "2 pessoas ficam de fora deste envio"; 1 → "1 pessoa fica de fora deste envio".
 *
 * Recebe: quantidade. Devolve: o texto.
 */
function titulo_de_quem_fica_de_fora(quantidade) {
  if (quantidade === 1) {
    return "1 pessoa fica de fora deste envio";
  }
  return quantidade + " pessoas ficam de fora deste envio";
}

/**
 * Monta o bloco "N pessoas ficam de fora deste envio": uma linha por pessoa, com o nome, o CPF e o motivo.
 *
 * Recebe: pessoas — [{linha, nome, cpf, motivo}]. Devolve: o bloco, ou null quando ninguém fica de fora.
 * Exemplo de linha: "Linha 6 · Ana Lima · 529.982.247-25 — Já foi enviada ao banco no arquivo aurora.xlsx e está em
 * análise: não vai de novo."
 */
function montar_bloco_de_quem_fica_de_fora(pessoas) {
  if (!pessoas || pessoas.length === 0) {
    return null;
  }
  const bloco = criar_elemento_de_quem_fica_de_fora("div", "quem-fica-de-fora", "");
  bloco.setAttribute("role", "note");
  bloco.append(criar_elemento_de_quem_fica_de_fora("p", "quem-fica-de-fora-titulo",
    titulo_de_quem_fica_de_fora(pessoas.length)));
  bloco.append(criar_elemento_de_quem_fica_de_fora("p", "quem-fica-de-fora-explicacao",
    "Não vão de novo e não pedem nada a você: o envio segue só com as outras pessoas."));
  const lista = criar_elemento_de_quem_fica_de_fora("ul", "quem-fica-de-fora-lista", "");
  for (const pessoa of pessoas) {
    // Quem é: a linha no arquivo, o nome (se veio) e o CPF
    const partes = ["Linha " + pessoa.linha];
    if (pessoa.nome) {
      partes.push(pessoa.nome);
    }
    if (pessoa.cpf) {
      partes.push(pessoa.cpf);
    }
    const item = criar_elemento_de_quem_fica_de_fora("li", "", "");
    item.append(criar_elemento_de_quem_fica_de_fora("strong", "", partes.join(" · ")));
    item.append(document.createTextNode(" — " + pessoa.motivo));
    lista.append(item);
  }
  bloco.append(lista);
  return bloco;
}
