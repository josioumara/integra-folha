"""A diretriz de tom de voz do Agente de validação, num lugar só: sério, cordial e direto nos dois prompts do agente
(pendências por conversa, ADR-118).

Para que serve: os dois prompts do agente que fala com a empresa sobre as pendências (a pergunta de cada pendência e a
conversa) usam a MESMA diretriz. Ela mora em prompts/tom_de_voz_do_agente_de_validacao.md; cada prompt tem o marcador
{tom_de_voz}, que é trocado pelo texto da diretriz na hora de montar o pedido. Mudar o tom é mudar um arquivo só.
"""
import re
from functools import lru_cache
from pathlib import Path

# Pasta raiz do projeto (para achar o arquivo da diretriz)
RAIZ = Path(__file__).resolve().parent.parent
# O arquivo da diretriz e o marcador que os prompts usam
ARQUIVO_DA_DIRETRIZ = RAIZ / "prompts" / "tom_de_voz_do_agente_de_validacao.md"
MARCADOR = "{tom_de_voz}"


@lru_cache(maxsize=1)
def diretriz() -> str:
    """O texto da diretriz: tudo abaixo de "## DIRETRIZ" no arquivo (o cabeçalho é explicação para quem lê)."""
    texto = ARQUIVO_DA_DIRETRIZ.read_text(encoding="utf-8")
    return re.split(r"^## DIRETRIZ\s*$", texto, flags=re.M)[1].strip()


def com_a_diretriz(sistema: str) -> str:
    """O papel do agente com a diretriz no lugar do marcador {tom_de_voz}. Ex.: "{tom_de_voz}\n\nSua tarefa..." →
    "Você é o Agente de validação...\n\nSua tarefa..."."""
    return sistema.replace(MARCADOR, diretriz())
