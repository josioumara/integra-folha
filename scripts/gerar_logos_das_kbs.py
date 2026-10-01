"""Gera o logo fictício de cada empresa a partir da KB do kit da marca dela (ADR-125).

Para que serve: as artes do endomarketing usam o logo da empresa quando o kit é próprio. As empresas do case são
fictícias e não têm logo; este script desenha um logo simples para cada uma, com as cores da KB do kit:
um círculo com a inicial e, ao lado, o nome da empresa. O arquivo vai para data/kbs_endomarketing/<empresa>/logo.png,
o nome fixo que a carga da versão 1 anexa à KB do kit (o logo não é mais um campo da ficha).

Como rodar (da pasta integra-folha): .venv\\Scripts\\python.exe scripts\\gerar_logos_das_kbs.py
Não usa IA nem banco de dados: só lê as KBs da pasta e grava as imagens. Rodar de novo refaz as imagens iguais.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Deixa o Python achar a pasta services/ quando o script roda direto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import kbs_endomarketing  # noqa: E402

# O tamanho da imagem do logo (largura e altura, em pixels) e o do círculo com a inicial
LARGURA, ALTURA = 640, 200
DIAMETRO_DO_CIRCULO = 150
# O tamanho das letras: a inicial dentro do círculo e o nome ao lado
TAMANHO_DA_INICIAL, TAMANHO_DO_NOME = 96, 44
# O prefixo do título das KBs de kit ("Kit da marca Aurora Alimentos" → "Aurora Alimentos")
PREFIXO_DO_TITULO = "Kit da marca "


def nome_da_marca(titulo_do_kit: str) -> str:
    """O nome da empresa a partir do título da KB do kit.

    Exemplo: "Kit da marca Aurora Alimentos" → "Aurora Alimentos".
    """
    if titulo_do_kit.startswith(PREFIXO_DO_TITULO):
        return titulo_do_kit[len(PREFIXO_DO_TITULO):]
    return titulo_do_kit


def desenhar_logo(nome: str, cor_principal: str, cor_do_nome: str) -> Image.Image:
    """Desenha o logo: fundo transparente, um círculo na cor principal com a inicial em branco e o nome ao lado.

    Recebe: o nome da empresa e as duas cores ("#rrggbb"). Devolve: a imagem.
    """
    # Fundo transparente (RGBA: vermelho, verde, azul e transparência)
    imagem = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    # O círculo, centralizado na altura, com uma margem à esquerda
    margem = (ALTURA - DIAMETRO_DO_CIRCULO) // 2
    caixa_do_circulo = (margem, margem, margem + DIAMETRO_DO_CIRCULO, margem + DIAMETRO_DO_CIRCULO)
    desenho.ellipse(caixa_do_circulo, fill=cor_principal)
    # A inicial em branco, no meio do círculo ("mm" = o ponto de referência é o meio do texto)
    centro_do_circulo = (margem + DIAMETRO_DO_CIRCULO // 2, ALTURA // 2)
    fonte_da_inicial = ImageFont.load_default(size=TAMANHO_DA_INICIAL)
    desenho.text(centro_do_circulo, nome[0].upper(), fill="#ffffff", font=fonte_da_inicial, anchor="mm")
    # O nome ao lado do círculo, alinhado pelo meio da altura ("lm" = começa à esquerda, no meio)
    inicio_do_nome = (margem * 2 + DIAMETRO_DO_CIRCULO, ALTURA // 2)
    fonte_do_nome = ImageFont.load_default(size=TAMANHO_DO_NOME)
    desenho.text(inicio_do_nome, nome, fill=cor_do_nome, font=fonte_do_nome, anchor="lm")
    return imagem


def gerar_logos() -> list[Path]:
    """Gera o logo de cada empresa que tem KB de kit próprio, com cores. Devolve os arquivos gravados."""
    gravados = []
    for arquivo_do_kit in sorted(kbs_endomarketing.PASTA_DAS_KBS.glob("EMP*/kit_da_marca.md")):
        ficha, _ = kbs_endomarketing.separar_ficha(arquivo_do_kit.read_text(encoding="utf-8"))
        cores = kbs_endomarketing.cores_do_kit(ficha)
        # Kit padrão ou sem cores: não há o que desenhar
        if ficha.get("kit_escolhido") != kbs_endomarketing.KIT_PROPRIO or not cores:
            continue
        # A 1ª cor é a principal (o círculo); a 2ª, a escura (o nome); sem a 2ª, o nome vai na principal
        cor_do_nome = cores[1] if len(cores) > 1 else cores[0]
        imagem = desenhar_logo(nome_da_marca(ficha.get("titulo", "")), cores[0], cor_do_nome)
        # O nome fixo que a carga da versão 1 procura na pasta da KB do kit
        destino = arquivo_do_kit.parent / kbs_endomarketing.ARQUIVO_DO_LOGO_NA_PASTA
        # optimize: o PNG sai menor (o limite do logo no sistema é 500 KB)
        imagem.save(destino, format="PNG", optimize=True)
        gravados.append(destino)
    return gravados


if __name__ == "__main__":
    for caminho in gerar_logos():
        print(f"{caminho} ({caminho.stat().st_size // 1024} KB)")
