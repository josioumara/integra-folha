"""Leva ao banco o texto atual do arquivo de uma KB de endomarketing: grava como versão nova e publica (ADR-125).

Para que serve: as KBs do projeto (data/kbs_endomarketing/) entram no banco uma vez só, na primeira carga, como a
versão 1. Quando o arquivo muda depois (ex.: o exemplo da KB geral de tom de voz passou a dizer "[empresa]"
no lugar do nome de uma empresa), o banco que já existe (o PostgreSQL local e o do site) continua com o texto antigo.
Este script leva o texto novo pelo mesmo caminho do editor da KB: grava a versão (salvar) e a publica (publicar),
sempre passando pela trava das KBs (services/kbs_endomarketing.py).

Como rodar (da pasta integra-folha; o banco é o do .env; faça o backup antes):
    .venv\\Scripts\\python.exe scripts\\republicar_kb_do_arquivo.py GER-TOM-DE-VOZ

O que ele garante:
- sem IA paga: o script roda no modo MOCK, e a trava usa só a lista de frases do guardrail de injeção, como em toda
  gravação de KB (a KB nunca chama a IA; ADR-147);
- pode rodar de novo: se a versão publicada já tem o texto do arquivo, nada muda; se uma execução anterior gravou o
  rascunho e parou antes de publicar, ele publica esse rascunho, sem gravar outro;
- só as KBs GERAIS e as do SANTANDER: a publicação da KB de uma empresa muda o catálogo e o kit dela, e isso é da tela
  da KB (services/kbs_publicacao.py);
- só a KB que está publicada: a KB retirada foi uma decisão do especialista, e o script não a publica de novo.
O índice de busca das KBs não muda (o agente lê o texto publicado direto do banco). Para refazê-lo, use
scripts/indexar_kbs_endomarketing.py, com a porta 8000 parada.
"""
import os
import sys
from pathlib import Path

# O modo MOCK antes de importar o projeto: a trava não pergunta nada à IA paga (a configuração lê o modo ao carregar,
# e o .env não troca uma variável que já existe)
os.environ["MODE"] = "mock"

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from services import banco, kbs_endomarketing  # noqa: E402

# Quem aparece como autor da versão gravada e de quem a publicou
AUTOR = "sistema (republicação do arquivo do projeto)"
# Os donos das KBs que o script aceita: as gerais e as do banco parceiro
DONOS_ACEITOS = (kbs_endomarketing.DONO_GERAL, kbs_endomarketing.DONO_SANTANDER)


def texto_do_arquivo(kb_id: str) -> str:
    """O texto do arquivo do projeto que tem a KB pedida (a ficha e as seções).

    Recebe: kb_id (ex.: "GER-TOM-DE-VOZ"). Devolve: o texto do arquivo .md cuja ficha tem esse id.
    Levanta KeyError se nenhum arquivo de data/kbs_endomarketing/ tem a KB.
    """
    for caminho in sorted(kbs_endomarketing.PASTA_DAS_KBS.rglob("*.md")):
        # O arquivo do modelo explica o formato: não é uma KB
        if caminho.name == kbs_endomarketing.ARQUIVO_DO_MODELO:
            continue
        conteudo = caminho.read_text(encoding="utf-8")
        ficha, _ = kbs_endomarketing.separar_ficha(conteudo)
        # O arquivo certo é o que tem o id pedido na ficha
        if ficha.get("id") == kb_id:
            return conteudo
    raise KeyError(f"Nenhum arquivo em data/kbs_endomarketing tem a KB {kb_id}.")


def mesmo_texto(texto_guardado: str, texto_do_arquivo_atual: str) -> bool:
    """Diz se os dois textos são iguais, sem ligar para o fim de linha (Windows ou Linux) nem para as pontas."""
    # O fim de linha do Windows vira o do Linux, e as linhas em branco das pontas saem
    guardado = texto_guardado.replace("\r\n", "\n").strip()
    atual = texto_do_arquivo_atual.replace("\r\n", "\n").strip()
    return guardado == atual


def rascunho_com_o_texto(conexao, kb_id: str, conteudo: str) -> int | None:
    """O número do rascunho da KB que já tem o texto do arquivo (uma execução que parou antes de publicar), ou None."""
    for resumo in kbs_endomarketing.obter(conexao, kb_id)["versoes"]:
        # Só o rascunho interessa: a versão substituída ou retirada não volta sozinha
        if resumo["situacao"] != kbs_endomarketing.RASCUNHO:
            continue
        versao = kbs_endomarketing.obter(conexao, kb_id, resumo["versao"])
        if mesmo_texto(versao["conteudo_md"], conteudo):
            return resumo["versao"]
    return None


def republicar(conexao, kb_id: str) -> dict:
    """Grava o texto atual do arquivo da KB como versão nova e a publica, se ainda não for o texto publicado.

    Recebe: conexao (o banco da aplicação); kb_id. Devolve: {kb_id, versao, acao}, em que a ação é "nada" (a versão
    publicada já tem o texto do arquivo), "publicou o rascunho" ou "gravou e publicou".
    Levanta KeyError (sem arquivo ou sem a KB no banco), ValueError (KB de empresa ou sem versão publicada) e
    kbs_endomarketing.TravaBloqueou (a trava achou um problema no texto novo).
    """
    conteudo = texto_do_arquivo(kb_id)
    ficha, _ = kbs_endomarketing.separar_ficha(conteudo)
    # A KB de uma empresa muda o catálogo e o kit dela: isso é da tela da KB, e não deste script
    if ficha.get("dono") not in DONOS_ACEITOS:
        raise ValueError(f"A KB {kb_id} é da empresa {ficha.get('dono')}: publique pela tela da KB.")
    # A KB precisa existir no banco (KeyError se não existe); na primeira vez, a carga inicial já traz o arquivo
    kbs_endomarketing.obter(conexao, kb_id)
    publicada = kbs_endomarketing.versao_publicada(conexao, kb_id)
    # Sem versão publicada, a KB foi retirada pelo especialista: o script não desfaz essa decisão
    if publicada is None:
        raise ValueError(f"A KB {kb_id} não está publicada (foi retirada): publique pela tela, se for o caso.")
    # A versão publicada já tem o texto do arquivo: nada a fazer
    if mesmo_texto(publicada["conteudo_md"], conteudo):
        return {"kb_id": kb_id, "versao": publicada["versao"], "acao": "nada"}
    # Um rascunho com o mesmo texto (de uma execução que parou antes de publicar) é publicado, sem gravar outro
    versao = rascunho_com_o_texto(conexao, kb_id, conteudo)
    acao = "publicou o rascunho"
    if versao is None:
        # A versão nova, pela trava (só conferências fixas, sem a IA)
        gravada = kbs_endomarketing.salvar(conexao, AUTOR, conteudo)
        versao = gravada["versao"]
        acao = "gravou e publicou"
    # Publica: a trava roda de novo, e a versão publicada de antes vira "substituída"
    kbs_endomarketing.publicar(conexao, AUTOR, kb_id, versao)
    return {"kb_id": kb_id, "versao": versao, "acao": acao}


def principal(argumentos: list[str]) -> int:
    """Roda o script para a KB pedida na linha de comando. Devolve o código de saída (0 = certo)."""
    # Um argumento só: o id da KB
    if len(argumentos) != 1:
        print("Uso: python scripts/republicar_kb_do_arquivo.py <kb_id>   (ex.: GER-TOM-DE-VOZ)")
        return 2
    kb_id = argumentos[0]
    # Abre o banco da aplicação pela porta única (SQLite ou PostgreSQL, conforme o .env; ADR-67)
    conexao = banco.conectar()
    # try/finally: a conexão fecha mesmo se der erro
    try:
        resultado = republicar(conexao, kb_id)
    except kbs_endomarketing.TravaBloqueou as bloqueio:
        # A trava achou um problema: nada foi publicado, e cada achado aparece para quem rodou
        print(f"{kb_id}: a trava bloqueou o texto do arquivo. Nada foi publicado.")
        for achado in bloqueio.achados:
            print(f"  - {achado['regra']}: {achado['detalhe']} {achado['trecho']}")
        return 1
    except (KeyError, ValueError) as erro:
        # Sem arquivo, sem a KB no banco, KB de empresa ou KB retirada: explica e não mexe em nada
        print(f"{kb_id}: {erro}")
        return 1
    finally:
        conexao.close()
    # O que aconteceu, numa linha
    if resultado["acao"] == "nada":
        print(f"{kb_id}: a versão publicada (v{resultado['versao']}) já tem o texto do arquivo. Nada mudou.")
    else:
        print(f"{kb_id}: {resultado['acao']} a versão v{resultado['versao']}.")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
