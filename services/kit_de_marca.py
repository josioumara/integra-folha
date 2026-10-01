"""Kit de marca do endomarketing: o LOGO da empresa, que entra nas artes quando o kit é o próprio (ADR-115).

Para que serve: as artes dos materiais (comunicado, FAQ, kit de boas-vindas, lembrete) são desenhadas na tela do banco
com o kit da empresa. A FONTE ÚNICA do kit é a KB "Kit da marca" de cada empresa: as
cores e a escolha entre o padrão e o próprio ficam na ficha da KB, e o logo fica anexado a cada VERSÃO da KB (tabela
logos_das_kbs). Quando a KB do kit é publicada ou retirada, o "aplicar na empresa" (services/kbs_publicacao.py) copia o
kit da versão publicada para dois lugares, que são só uma CÓPIA DERIVADA, lida pela arte: as cores no cadastro da
empresa (services/empresas.py) e o logo na tabela logos_dos_kits, daqui.

Também confere as imagens que chegam pela tela (o logo e a arte que o banco publica): a conferência olha a ASSINATURA
do arquivo (os primeiros bytes, que dizem o formato de verdade), não só o nome. Assim, um arquivo qualquer renomeado
para "logo.png" é recusado.

A imagem é guardada como texto (base64), para funcionar igual no SQLite e no PostgreSQL.
Exemplo de base64: os bytes de uma imagem viram letras e números ("iVBORw0KGgo..."), que cabem numa coluna de texto.
"""
import base64
from datetime import datetime, timezone

# O começo de todo arquivo PNG (8 bytes fixos) e de todo JPEG (3 bytes fixos): a "assinatura" do formato
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"
ASSINATURA_JPEG = b"\xff\xd8\xff"
# O tipo de cada formato, do jeito que o navegador entende ("tipo MIME")
TIPO_PNG, TIPO_JPEG = "image/png", "image/jpeg"
# O maior logo aceito: 500 KB (um logo para arte de comunicado não precisa de mais)
LIMITE_DO_LOGO = 500 * 1024
# A maior arte aceita: 2 MB (a imagem desenhada na tela do banco fica bem abaixo disso)
LIMITE_DA_ARTE = 2 * 1024 * 1024


def tipo_da_imagem(conteudo: bytes) -> str | None:
    """O formato da imagem pela assinatura dos primeiros bytes.

    Recebe: os bytes do arquivo. Devolve: "image/png", "image/jpeg" ou None (não é nenhum dos dois).
    Exemplo: um PNG de verdade → "image/png"; um texto renomeado para ".png" → None.
    """
    # PNG: os 8 primeiros bytes são sempre os mesmos
    if conteudo.startswith(ASSINATURA_PNG):
        return TIPO_PNG
    # JPEG: os 3 primeiros bytes são sempre os mesmos
    if conteudo.startswith(ASSINATURA_JPEG):
        return TIPO_JPEG
    # Qualquer outra coisa não é aceita
    return None


def conferir_logo(conteudo: bytes) -> str:
    """Confere o logo enviado: PNG ou JPEG de verdade, com até 500 KB. Devolve o tipo; senão, ValueError."""
    # Arquivo vazio não é logo
    if not conteudo:
        raise ValueError("O arquivo do logo está vazio.")
    # Acima do limite, recusa com o tamanho aceito
    if len(conteudo) > LIMITE_DO_LOGO:
        raise ValueError("O logo passou de 500 KB. Envie uma imagem menor.")
    # O formato é conferido pela assinatura, não pelo nome do arquivo
    tipo = tipo_da_imagem(conteudo)
    if tipo is None:
        raise ValueError("O logo precisa ser uma imagem PNG ou JPEG.")
    return tipo


def conferir_arte(conteudo: bytes) -> None:
    """Confere a arte que a tela do banco envia ao publicar: PNG de verdade, com até 2 MB. Senão, ValueError."""
    # Arte vazia ou grande demais é recusada
    if not conteudo:
        raise ValueError("A imagem da arte chegou vazia.")
    if len(conteudo) > LIMITE_DA_ARTE:
        raise ValueError("A imagem da arte passou de 2 MB.")
    # A arte é sempre PNG (é o que o desenho da tela gera)
    if tipo_da_imagem(conteudo) != TIPO_PNG:
        raise ValueError("A arte precisa ser uma imagem PNG.")


def _agora() -> str:
    """O momento atual, em texto ISO (UTC), para gravar nas tabelas."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------- A cópia derivada: o logo da empresa, que a arte lê ----------------

def _preparar(conexao) -> None:
    """Cria a tabela dos logos das empresas (a cópia derivada), se ainda não existir (um logo por empresa)."""
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS logos_dos_kits (
               empresa_id    TEXT PRIMARY KEY,
               tipo          TEXT NOT NULL,     -- image/png ou image/jpeg
               imagem_base64 TEXT NOT NULL,
               enviado_em    TEXT NOT NULL,
               enviado_por   TEXT NOT NULL
           )"""
    )


def gravar_logo(conexao, empresa_id: str, conteudo: bytes, usuario: str) -> None:
    """Grava (ou troca) o logo da empresa na cópia derivada, depois de conferir a imagem.

    Quem chama é o "aplicar na empresa" (com o logo da versão publicada da KB do kit) e a semente das empresas.
    Recebe: conexao; empresa_id; conteudo (os bytes do arquivo); usuario (quem aplicou). Devolve: nada.
    """
    # Confere antes de gravar: formato e tamanho
    tipo = conferir_logo(conteudo)
    _preparar(conexao)
    # Um logo por empresa: o novo substitui o anterior
    conexao.execute("DELETE FROM logos_dos_kits WHERE empresa_id = ?", (empresa_id,))
    conexao.execute("INSERT INTO logos_dos_kits (empresa_id, tipo, imagem_base64, enviado_em, enviado_por) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (empresa_id, tipo, base64.b64encode(conteudo).decode("ascii"), _agora(), usuario))
    conexao.commit()


def tirar_logo(conexao, empresa_id: str) -> None:
    """Apaga o logo da empresa (a arte volta a usar só as cores e o nome)."""
    _preparar(conexao)
    conexao.execute("DELETE FROM logos_dos_kits WHERE empresa_id = ?", (empresa_id,))
    conexao.commit()


def logo(conexao, empresa_id: str) -> tuple[bytes, str] | None:
    """O logo da empresa: (bytes da imagem, tipo). Sem logo gravado: None."""
    _preparar(conexao)
    linha = conexao.execute("SELECT imagem_base64, tipo FROM logos_dos_kits WHERE empresa_id = ?",
                            (empresa_id,)).fetchone()
    # Sem linha, a empresa não tem logo
    if linha is None:
        return None
    return base64.b64decode(linha[0]), linha[1]


def tem_logo(conexao, empresa_id: str) -> bool:
    """Diz se a empresa tem logo gravado."""
    return logo(conexao, empresa_id) is not None


# ---------------- A fonte: o logo de cada versão da KB do kit ----------------

def _preparar_logos_das_versoes(conexao) -> None:
    """Cria a tabela dos logos das versões das KBs do kit, se ainda não existir (no máximo um logo por versão).

    A chave é a da versão da KB (kb_id, versao): cada versão guarda o próprio logo, e uma versão nova nasce com uma
    cópia do logo da versão em que se baseia (services/kbs_endomarketing.py).
    """
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS logos_das_kbs (
               kb_id         TEXT NOT NULL,
               versao        INTEGER NOT NULL,
               tipo          TEXT NOT NULL,     -- image/png ou image/jpeg
               imagem_base64 TEXT NOT NULL,
               enviado_em    TEXT NOT NULL,
               enviado_por   TEXT NOT NULL,
               PRIMARY KEY (kb_id, versao)
           )"""
    )


def gravar_logo_da_versao(conexao, kb_id: str, versao: int, conteudo: bytes, usuario: str) -> None:
    """Grava (ou troca) o logo de uma versão da KB do kit, depois de conferir a imagem.

    Recebe: conexao; kb_id e versao (a versão da KB); conteudo (os bytes do arquivo); usuario (quem enviou).
    Devolve: nada. Imagem inválida (não é PNG nem JPEG, vazia ou com mais de 500 KB): ValueError.
    """
    # Confere antes de gravar: formato (pela assinatura) e tamanho
    tipo = conferir_logo(conteudo)
    _preparar_logos_das_versoes(conexao)
    # Um logo por versão: o novo substitui o anterior
    conexao.execute("DELETE FROM logos_das_kbs WHERE kb_id = ? AND versao = ?", (kb_id, versao))
    conexao.execute("INSERT INTO logos_das_kbs (kb_id, versao, tipo, imagem_base64, enviado_em, enviado_por) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (kb_id, versao, tipo, base64.b64encode(conteudo).decode("ascii"), _agora(), usuario))
    conexao.commit()


def tirar_logo_da_versao(conexao, kb_id: str, versao: int) -> None:
    """Apaga o logo de uma versão da KB do kit (as outras versões ficam como estão)."""
    _preparar_logos_das_versoes(conexao)
    conexao.execute("DELETE FROM logos_das_kbs WHERE kb_id = ? AND versao = ?", (kb_id, versao))
    conexao.commit()


def logo_da_versao(conexao, kb_id: str, versao: int) -> tuple[bytes, str] | None:
    """O logo de uma versão da KB do kit: (bytes da imagem, tipo). Sem logo nessa versão: None."""
    _preparar_logos_das_versoes(conexao)
    linha = conexao.execute("SELECT imagem_base64, tipo FROM logos_das_kbs WHERE kb_id = ? AND versao = ?",
                            (kb_id, versao)).fetchone()
    # Sem linha, a versão não tem logo
    if linha is None:
        return None
    return base64.b64decode(linha[0]), linha[1]


def copiar_logo_da_versao(conexao, kb_id: str, versao_de_origem: int, versao_nova: int) -> bool:
    """Copia o logo de uma versão para outra da mesma KB: a versão nova nasce com o logo da versão de origem.

    Recebe: conexao; kb_id; versao_de_origem (de onde vem o logo); versao_nova (quem recebe).
    Devolve: se havia logo para copiar. Quem enviou a imagem e quando continuam os do envio original.
    """
    _preparar_logos_das_versoes(conexao)
    linha = conexao.execute("SELECT tipo, imagem_base64, enviado_em, enviado_por FROM logos_das_kbs "
                            "WHERE kb_id = ? AND versao = ?", (kb_id, versao_de_origem)).fetchone()
    # A versão de origem não tem logo: a nova também fica sem
    if linha is None:
        return False
    tipo, imagem_base64, enviado_em, enviado_por = linha
    # A versão nova recebe a mesma imagem (se já tinha um logo, ele é trocado)
    conexao.execute("DELETE FROM logos_das_kbs WHERE kb_id = ? AND versao = ?", (kb_id, versao_nova))
    conexao.execute("INSERT INTO logos_das_kbs (kb_id, versao, tipo, imagem_base64, enviado_em, enviado_por) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (kb_id, versao_nova, tipo, imagem_base64, enviado_em, enviado_por))
    conexao.commit()
    return True
