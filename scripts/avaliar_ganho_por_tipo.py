"""Mede o ganho da IA por tipo de arquivo, na prova de data/avaliacao/prova_por_tipo/, pelo caminho da tela.

Cada arquivo da prova passa pelo MESMO caminho da tela "Cadastrar funcionários" (services/cadastro.py: enviar_arquivo,
aceitar_mapeamento e decidir_formato), num banco SQLite novo e temporário para cada arquivo: é o primeiro envio de uma
empresa, sem um mapeamento de envio anterior para reaproveitar. Uma "pessoa simulada" responde só o que o sistema
pergunta, sempre pelo gabarito: a coluna em dúvida, a coluna que o aceite recusou (duas colunas no mesmo campo) e o
formato de uma coluna (data ou zeros à esquerda). As pendências das pessoas ficam sem resposta: são o trabalho que
sobra para a empresa (a régua de eval/ganho_por_tipo.py conta tudo).

Os dois braços, no mesmo arquivo:
- sem_ia: MODE=mock. O Interpretador vira o dicionário B0 com as regras do simulador (agents/interpretador.py,
  simular_llm); a tabela e as fichas do Word são lidas por regra; o texto corrido vai com a IA fora do ar, e a
  aplicação recusa o documento (é o que ela faz sem a IA: a falha da IA pausa e nunca simula, ADR-145);
- com_ia: MODE=llm. O que a aplicação faz hoje: o Interpretador com o formato garantido, o Leitor de Documentos e o
  Conferidor da Leitura, pelo Bedrock. GASTA DINHEIRO: só com a aprovação e com a trava de custo (--teto-usd).

A segurança da medição:
- nunca o banco de todos: BANCO=sqlite, um arquivo temporário por envio (o script para se não for SQLite);
- o índice do RAG é uma cópia (storage/indices_da_medicao), e o aprendizado do RAG fica desligado;
- o parâmetro do layout é a foto da versão em uso (parametro_do_layout.json, lida do PostgreSQL só para ler);
- a prova precisa estar congelada, e cada arquivo precisa bater com a impressão digital do manifesto;
- toda chamada à IA passa por services/llm_client.py: um contador em volta dela soma o custo da medição inteira, e a
  trava para antes do arquivo que passaria do teto.

Uso (na pasta do repositório):
  python scripts/avaliar_ganho_por_tipo.py --etapa parametro           (lê o PostgreSQL só para ler; grava a foto)
  python scripts/avaliar_ganho_por_tipo.py --etapa medir --braco sem_ia [--ensaio T1_padrao_do_banco_1.xlsx ...]
  python scripts/avaliar_ganho_por_tipo.py --etapa medir --braco com_ia --teto-usd 5      (IA real: custa)
  python scripts/avaliar_ganho_por_tipo.py --etapa resumir
Saída: data/avaliacao/resultados/ganho_por_tipo_<braço>.json (o que ficou de cada arquivo) e ganho_por_tipo.json (o
resumo por tipo, com o ganho). O --ensaio mede só os arquivos citados, sem conferir o congelamento e sem gravar.
"""
import argparse
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

# Pasta raiz do projeto, para importar os módulos ao rodar o script diretamente
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Onde a prova e os resultados ficam
PASTA_DA_PROVA = RAIZ / "data" / "avaliacao" / "prova_por_tipo"
CAMINHO_DO_MANIFESTO = PASTA_DA_PROVA / "manifesto.json"
CAMINHO_DO_PARAMETRO = PASTA_DA_PROVA / "parametro_do_layout.json"
PASTA_DOS_RESULTADOS = RAIZ / "data" / "avaliacao" / "resultados"
# A cópia do índice do RAG que a medição usa (nunca o storage/indices, que é o da aplicação)
PASTA_DO_INDICE_DA_MEDICAO = RAIZ / "storage" / "indices_da_medicao"
# Quem "envia" os arquivos (aparece só nos bancos temporários)
LOGIN_DA_MEDICAO = "medicao.ganho.por.tipo"
# O custo esperado de cada arquivo com IA, antes de haver medida (a trava usa o maior entre este e o já medido).
# Uma chamada do Interpretador custa ≈ US$ 0,053 (a média da telemetria da aplicação); a leitura do texto corrido, ≈ US$ 0,02
# por pessoa (EXP-010), com folga
CUSTO_ESPERADO_POR_GRUPO_USD = {"planilha": 0.08, "tabela": 0.08, "texto_corrido": 0.45}
# Quantas vezes a pessoa simulada tenta resolver o aceite recusado antes de desistir
TENTATIVAS_DO_ACEITE = 3
# Quantas decisões de formato de coluna, no máximo, num arquivo
DECISOES_DE_FORMATO = 10


# ============================== O ambiente (antes de importar a aplicação) ==============================

def modo_do_braco(braco: str, simular: bool) -> str:
    """O modo da IA no braço: "llm" (a IA real) só no com IA de verdade; o sem IA e o ensaio simulado usam "mock"."""
    if braco == "com_ia" and not simular:
        return "llm"
    return "mock"


def preparar_o_ambiente(braco: str, simular: bool) -> Path:
    """Liga as variáveis de ambiente do braço ANTES de importar a aplicação (a configuração é lida na importação).

    Recebe: o braço e se o com IA é só simulado (o ensaio que percorre o caminho do com IA sem gastar).
    Devolve: a pasta temporária da medição (os bancos de cada arquivo, os envios e o controle do fluxo ficam nela).
    O .env da pasta continua valendo para o resto (a chave do Bedrock, os modelos), mas estas variáveis vêm antes.
    """
    pasta = Path(tempfile.mkdtemp(prefix=f"ganho_por_tipo_{braco}_"))
    os.environ["MODE"] = modo_do_braco(braco, simular)
    # Nunca o PostgreSQL de todos: cada arquivo abre o seu SQLite; este é só o banco padrão da medição
    os.environ["BANCO"] = "sqlite"
    os.environ["POSTGRES_URL"] = ""
    os.environ["CAMINHO_BANCO"] = str(pasta / "banco_padrao_da_medicao.db")
    os.environ["CAMINHO_CHECKPOINTS"] = str(pasta / "controle_do_fluxo.db")
    os.environ["PASTA_UPLOADS"] = str(pasta / "envios")
    os.environ["PASTA_HOMOLOGADOS"] = str(pasta / "homologados")
    # O RAG: a cópia do índice, sem aprender nada com os envios da medição
    os.environ["PASTA_INDICES"] = str(PASTA_DO_INDICE_DA_MEDICAO)
    os.environ["APRENDIZADO_DO_RAG"] = "desligado"
    # O modelo de vetores só é lido: vale o da pasta indicada fora, ou o do repositório
    os.environ.setdefault("PASTA_MODELOS", str(RAIZ / "storage" / "modelos"))
    # A falha da IA nunca vira simulação (ADR-145): um arquivo que falha fica marcado, e não é medido como "sem IA"
    os.environ["MOCK_DE_RESERVA"] = "nao"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    return pasta


def ler_opcoes() -> argparse.Namespace:
    """A etapa, o braço, o teto de custo e, no ensaio, os arquivos."""
    leitor = argparse.ArgumentParser(description="Mede o ganho da IA por tipo de arquivo (prova por tipo).")
    leitor.add_argument("--etapa", choices=["parametro", "medir", "resumir"], required=True)
    leitor.add_argument("--braco", choices=["sem_ia", "com_ia"], help="na etapa medir: sem ou com a IA real")
    leitor.add_argument("--teto-usd", type=float, default=0.0, help="com IA: o gasto máximo da medição, em dólares")
    leitor.add_argument("--ensaio", nargs="*", default=None, help="mede só estes arquivos, sem gravar o resultado")
    leitor.add_argument("--simular", action="store_true",
                        help="só no ensaio: percorre o caminho do com IA em MOCK, sem gastar (testa o script)")
    opcoes = leitor.parse_args()
    # O com IA simulado nunca vira resultado: só vale no ensaio
    if opcoes.simular and opcoes.ensaio is None:
        leitor.error("--simular só vale com --ensaio")
    return opcoes


# Rodado como script: lê as opções e liga o ambiente do braço ANTES de importar a aplicação. Importado (ex.: por um
# teste), nada disso acontece
OPCOES = None
PASTA_DA_MEDICAO = None
if __name__ == "__main__":
    OPCOES = ler_opcoes()
    if OPCOES.etapa == "medir":
        PASTA_DA_MEDICAO = preparar_o_ambiente(OPCOES.braco, OPCOES.simular)

from eval import congelamento, ganho_por_tipo  # noqa: E402
from models.contratos import CampoLayout  # noqa: E402
from rag import busca  # noqa: E402
from services import (banco, cadastro, config, correcoes, llm_client, mapeamentos, parametros,  # noqa: E402
                      validador)


# ============================== A foto do parâmetro ==============================

def gravar_a_foto_do_parametro() -> dict:
    """Lê a versão em uso do parâmetro do layout no PostgreSQL (só lendo) e grava a foto ao lado da prova.

    Por que uma foto: a medição roda em bancos novos, que nasceriam com o layout do arquivo do projeto (v1). A foto é o
    parâmetro que a aplicação usa hoje (os 4 obrigatórios do ADR-143 e o codigo_cbo), e ela fica congelada com a prova:
    medir de novo usa o mesmo parâmetro, mesmo que o do banco mude depois.
    """
    import psycopg
    from dotenv import dotenv_values

    endereco = dotenv_values(RAIZ / ".env").get("POSTGRES_URL")
    # A transação só de leitura: nada é gravado no banco de todos
    with psycopg.connect(endereco, options="-c default_transaction_read_only=on") as conexao:
        linha = conexao.execute("SELECT versao, conteudo FROM parametros WHERE tipo = 'layout' "
                                "ORDER BY versao DESC LIMIT 1").fetchone()
    versao, conteudo = linha
    foto = {"versao": versao, "lida_em": date.today().isoformat(), "de_onde": "PostgreSQL da aplicação (só leitura)",
            "campos": json.loads(conteudo)}
    CAMINHO_DO_PARAMETRO.write_text(json.dumps(foto, ensure_ascii=False, indent=1), encoding="utf-8")
    return foto


def campos_da_foto() -> tuple[dict, dict]:
    """A foto do parâmetro e {nome do campo: CampoLayout}."""
    foto = json.loads(CAMINHO_DO_PARAMETRO.read_text(encoding="utf-8"))
    campos_por_nome = {}
    for campo in foto["campos"]:
        campos_por_nome[campo["campo"]] = CampoLayout(**campo)
    return foto, campos_por_nome


# ============================== A conta das chamadas à IA ==============================

class ContaDaIA:
    """Soma, em todas as chamadas à IA desta medição, quantas foram reais, quantas simuladas e quanto custaram.

    Toda chamada passa por LLMClient.gerar: a conta embrulha esse método. O Leitor chama a IA em paralelo (4 pessoas ao
    mesmo tempo), por isso a soma usa uma trava de linha de execução (Lock), para duas somas não se atropelarem.
    """

    def __init__(self):
        self.trava = threading.Lock()
        self.custo_total_usd = 0.0
        self.custo_do_arquivo_usd = 0.0
        self.reais_do_arquivo = 0
        self.simuladas_do_arquivo = 0
        self.por_tarefa = {}
        self._gerar_original = llm_client.LLMClient.gerar

    def ligar(self) -> None:
        """Troca LLMClient.gerar por uma versão que conta cada chamada e depois chama a original."""
        conta = self

        def gerar_contando(cliente, tarefa, *argumentos, **opcoes):
            """Chama a IA como sempre e anota a chamada (a resposta volta igual)."""
            resposta = conta._gerar_original(cliente, tarefa, *argumentos, **opcoes)
            conta.anotar(tarefa, resposta)
            return resposta

        llm_client.LLMClient.gerar = gerar_contando

    def anotar(self, tarefa: str, resposta) -> None:
        """Soma uma resposta: real ou simulada, e o custo (quando o provedor informa)."""
        with self.trava:
            if resposta.modo == "llm":
                self.reais_do_arquivo += 1
            else:
                self.simuladas_do_arquivo += 1
            custo = resposta.custo_usd or 0.0
            self.custo_do_arquivo_usd += custo
            self.custo_total_usd += custo
            self.por_tarefa[tarefa] = self.por_tarefa.get(tarefa, 0) + 1

    def comecar_arquivo(self) -> None:
        """Zera as contas do arquivo (o total da medição continua somando)."""
        with self.trava:
            self.custo_do_arquivo_usd = 0.0
            self.reais_do_arquivo = 0
            self.simuladas_do_arquivo = 0
            self.por_tarefa = {}


class ClienteSemIA(llm_client.LLMClient):
    """O braço sem IA no texto corrido: a IA está fora do ar, e toda chamada falha como na vida real."""

    def gerar(self, tarefa, *argumentos, **opcoes):
        """Nunca responde: levanta IAIndisponivel, como a aplicação com a IA fora do ar (ADR-145)."""
        raise llm_client.IAIndisponivel("braço sem IA da medição: a IA fica fora do ar de propósito")


# ============================== A pessoa simulada ==============================

@dataclass
class ContextoDoArquivo:
    """O que a pessoa simulada sabe do arquivo: a empresa, o gabarito, os valores certos e os campos do parâmetro."""

    empresa_id: str                 # a empresa que envia (a do manifesto)
    entrada: dict                   # a entrada do arquivo no manifesto (as pessoas e o que cada coluna devia virar)
    valores_por_pessoa: dict        # {pessoa_id: {campo: valor certo}}
    campos_por_nome: dict           # {nome do campo: CampoLayout} da foto do parâmetro
    esperadas_por_nome: dict        # {nome da coluna: o que ela devia virar}
    tamanho_da_matricula: int       # quantos dígitos a matrícula tem (para a dúvida dos zeros à esquerda)


def montar_o_contexto(empresa_id: str, entrada: dict, valores_por_pessoa: dict,
                      campos_por_nome: dict) -> ContextoDoArquivo:
    """Junta o que a pessoa simulada precisa saber de um arquivo."""
    esperadas_por_nome = {}
    for esperada in ganho_por_tipo.colunas_esperadas(entrada):
        esperadas_por_nome[ganho_por_tipo._nome_limpo(esperada["nome"])] = esperada
    # A matrícula da primeira pessoa do arquivo (todas têm o mesmo tamanho, ex.: "09001")
    primeira_pessoa = entrada["gabarito"][0]["pessoa_id"]
    tamanho_da_matricula = len(valores_por_pessoa[primeira_pessoa]["matricula"])
    return ContextoDoArquivo(empresa_id, entrada, valores_por_pessoa, campos_por_nome, esperadas_por_nome,
                             tamanho_da_matricula)


def grupo_do_arquivo(entrada: dict) -> str:
    """"planilha" (T1 a T4), "tabela" (T5: tabela ou fichas, lidas por regra) ou "texto_corrido" (T6 e T7)."""
    if entrada["tipo"] == "T5":
        return "tabela"
    if entrada["tipo"] in ("T6", "T7"):
        return "texto_corrido"
    return "planilha"


def escolha_pelo_exemplo(coluna: dict, contexto: ContextoDoArquivo) -> str:
    """O campo de uma coluna que o gabarito não nomeia, decidido pelo exemplo (como uma pessoa olhando o valor).

    Serve para as partes de uma coluna dividida e para as colunas do texto corrido (cada rótulo que a IA achou).
    Procura, entre os candidatos que a IA sugeriu (ou todos os campos), aquele em que o exemplo da coluna é o valor
    certo de alguém do arquivo. Nenhum bate: a coluna fica de fora.
    """
    exemplo = coluna.get("exemplo") or ""
    candidatos = coluna.get("candidatos") or list(contexto.campos_por_nome)
    for campo in candidatos:
        for gabarito in contexto.entrada["gabarito"]:
            valor_certo = contexto.valores_por_pessoa[gabarito["pessoa_id"]].get(campo, "")
            if exemplo and valor_certo and ganho_por_tipo.valor_certo(valor_certo, exemplo,
                                                                      contexto.campos_por_nome[campo]):
                return campo
    return mapeamentos.IGNORAR


def escolha_pelo_gabarito(coluna: dict, contexto: ContextoDoArquivo) -> str:
    """O que a pessoa simulada responde sobre uma coluna: o campo certo, ou ignorar.

    A coluna que junta o nome e o CPF, quando o sistema não propôs dividir, vai para o CPF: a empresa guarda o
    obrigatório (a tela não divide nome e CPF sem a IA).
    """
    esperada = contexto.esperadas_por_nome.get(ganho_por_tipo._nome_limpo(coluna["coluna"]))
    if esperada is None:
        return escolha_pelo_exemplo(coluna, contexto)
    if esperada["esperado"] in ("AMBIGUO", "NAO_MAPEADO"):
        return mapeamentos.IGNORAR
    if esperada["esperado"] == "DIVIDIR":
        return "cpf"
    return esperada["esperado"]


def campos_citados_no_erro(erro: str, campos_por_nome: dict) -> list[str]:
    """Os campos do layout que o recado do aceite recusado cita (ex.: "Mais de uma coluna para o mesmo campo: cpf")."""
    # Vírgulas e parênteses viram espaço, para achar o nome técnico inteiro ("(cpf)" → " cpf ")
    recado = " " + erro.replace(",", " ").replace("(", " ").replace(")", " ") + " "
    citados = []
    for campo in campos_por_nome:
        # O nome técnico aparece inteiro, entre espaços (codigo_unidade não conta como codigo_cbo)
        if f" {campo} " in recado:
            citados.append(campo)
    return citados


def campo_de_cada_coluna(leitura: dict, escolhas: dict) -> dict:
    """O campo em que cada coluna está agora: a escolha da pessoa ou o que o sistema propôs."""
    campos = {}
    for coluna in leitura["colunas"]:
        campos[coluna["coluna"]] = escolhas.get(coluna["coluna"], coluna["campo"])
    return campos


def resolver_o_aceite_recusado(leitura: dict, escolhas: dict, contexto: ContextoDoArquivo) -> int:
    """A pessoa corrige as colunas do campo que o aceite recusou. Devolve quantas colunas ela mudou (as perguntas).

    Só mexe nas colunas que estão no campo citado pelo recado e que, pelo gabarito, não são daquele campo.
    """
    mudadas = 0
    campo_atual = campo_de_cada_coluna(leitura, escolhas)
    for campo in campos_citados_no_erro(leitura["erro"] or "", contexto.campos_por_nome):
        for coluna in leitura["colunas"]:
            if campo_atual.get(coluna["coluna"]) != campo:
                continue
            certa = escolha_pelo_gabarito(coluna, contexto)
            if certa != campo:
                escolhas[coluna["coluna"]] = certa
                mudadas += 1
    return mudadas


def decidir_os_formatos(conexao, processamento_id: str, leitura: dict, contexto: ContextoDoArquivo,
                        cliente) -> tuple[dict, int]:
    """A pessoa decide o formato das colunas em dúvida: datas dia/mês (a empresa é brasileira) e a matrícula com os
    zeros do gabarito. Devolve (a leitura depois, quantas decisões)."""
    decisoes = 0
    while leitura.get("formatos_pendentes") and decisoes < DECISOES_DE_FORMATO:
        pendente = leitura["formatos_pendentes"][0]
        if pendente["tipo"] == "DATA_AMBIGUA":
            decisao = "DMY"
        else:
            decisao = f"zeros:{contexto.tamanho_da_matricula}"
        leitura = cadastro.decidir_formato(conexao, contexto.empresa_id, processamento_id, pendente["coluna"], decisao,
                                           cliente=cliente)
        decisoes += 1
    return leitura, decisoes


def responder_as_colunas_em_duvida(leitura: dict, contexto: ContextoDoArquivo) -> dict:
    """As respostas da pessoa às colunas em que o sistema pediu ajuda: {coluna: campo ou ignorar}."""
    escolhas = {}
    for coluna in leitura["colunas"]:
        if coluna["precisa_decidir"]:
            escolhas[coluna["coluna"]] = escolha_pelo_gabarito(coluna, contexto)
    return escolhas


def enviar_como_a_empresa(conexao, conteudo: bytes, cliente, contexto: ContextoDoArquivo) -> dict:
    """Passa o arquivo pela tela, com a pessoa simulada respondendo só o que o sistema pergunta. Devolve o bruto."""
    entrada = contexto.entrada
    bruto = {"arquivo": entrada["arquivo"], "tipo": entrada["tipo"], "recusado": None, "travado_no_aceite": None,
             "perguntas_de_coluna": 0, "perguntas_de_formato": 0}
    try:
        leitura = cadastro.enviar_arquivo(conexao, contexto.empresa_id, LOGIN_DA_MEDICAO, conteudo, entrada["arquivo"],
                                          cliente=cliente)
    except ValueError as erro:
        # Arquivo recusado pelo sistema (ex.: o texto corrido sem a IA): nada é cadastrado
        bruto["recusado"] = f"{type(erro).__name__}: {erro}"
        return bruto
    processamento_id = leitura["processamento_id"]
    bruto["processamento_id"] = processamento_id
    bruto["colunas_propostas"] = _colunas_em_resumo(leitura["colunas"])
    bruto["duvidas_da_leitura"] = list(leitura.get("duvidas") or [])
    # O sistema parou antes do aceite (ex.: a IA caiu): o arquivo fica marcado
    if leitura["etapa"] != "aprovar_mapeamento":
        bruto["travado_no_aceite"] = f"etapa {leitura['etapa']}: {leitura.get('erro')}"
        return bruto
    # As colunas em dúvida: a pessoa responde cada uma pelo gabarito
    escolhas = responder_as_colunas_em_duvida(leitura, contexto)
    bruto["perguntas_de_coluna"] = len(escolhas)
    leitura = cadastro.aceitar_mapeamento(conexao, contexto.empresa_id, LOGIN_DA_MEDICAO, processamento_id, escolhas,
                                          cliente=cliente)
    # O aceite recusado (duas colunas no mesmo campo): a pessoa corrige as colunas do campo citado e tenta de novo
    for _tentativa in range(TENTATIVAS_DO_ACEITE):
        if leitura["etapa"] != "aprovar_mapeamento":
            break
        mudadas = resolver_o_aceite_recusado(leitura, escolhas, contexto)
        if mudadas == 0:
            break
        bruto["perguntas_de_coluna"] += mudadas
        leitura = cadastro.aceitar_mapeamento(conexao, contexto.empresa_id, LOGIN_DA_MEDICAO, processamento_id,
                                              escolhas, cliente=cliente)
    if leitura["etapa"] == "aprovar_mapeamento":
        bruto["travado_no_aceite"] = leitura.get("erro") or "o aceite não passou"
        return bruto
    # O formato das colunas em dúvida (datas, zeros à esquerda)
    leitura, bruto["perguntas_de_formato"] = decidir_os_formatos(conexao, processamento_id, leitura, contexto, cliente)
    bruto["etapa_final"] = leitura["etapa"]
    bruto["erro_final"] = leitura.get("erro")
    return bruto


def _colunas_em_resumo(colunas: list[dict]) -> list[dict]:
    """As colunas da leitura só com o que a medição usa: nome, campo, se pediu decisão e os candidatos."""
    resumo = []
    for coluna in colunas:
        resumo.append({"coluna": coluna["coluna"], "campo": coluna["campo"], "precisa_decidir": coluna["precisa_decidir"],
                       "candidatos": coluna.get("candidatos", []), "origem": coluna.get("origem"),
                       "dividida": bool(coluna.get("divisao"))})
    return resumo


def guardar_o_resultado(conexao, bruto: dict) -> None:
    """Acrescenta ao bruto os dados do envio depois do aceite, as pendências abertas e as colunas aprovadas."""
    processamento_id = bruto.get("processamento_id")
    if not processamento_id or bruto["recusado"] or bruto["travado_no_aceite"]:
        return
    dados = correcoes.dados_atuais(conexao, processamento_id)
    relatorio = validador.obter(conexao, processamento_id)
    registros = []
    for registro in dados.registros:
        registros.append(_registro_em_texto(registro))
    bruto["registros"] = registros
    # As pendências abertas, uma por cartão da tela (a mesma lista de cadastro.resumo_das_pendencias)
    bruto["pendencias"] = cadastro._pendencias_abertas(relatorio) if relatorio is not None else []
    bruto["resumo_das_pendencias"] = cadastro.resumo_das_pendencias(relatorio, dados.registros)
    bruto["regras_das_pendencias"] = _regras_abertas(relatorio)
    plano, _situacao = mapeamentos.obter(conexao, processamento_id)
    colunas_finais = []
    for item in plano.itens:
        partes = None
        if item.divisao is not None:
            partes = []
            for parte in item.divisao.partes:
                partes.append(parte.campo)
        colunas_finais.append({"coluna": item.coluna, "campo": item.campo, "status": item.status.value,
                               "origem": item.origem, "partes": partes})
    bruto["colunas_finais"] = colunas_finais


def _registro_em_texto(registro: dict) -> dict:
    """O registro com os valores em texto (datas e números viram texto), com a linha do arquivo."""
    em_texto = {}
    for campo, valor in registro.items():
        if valor is None:
            continue
        if campo == "_linha":
            em_texto[campo] = valor
        elif not campo.startswith("_"):
            em_texto[campo] = str(valor)
    return em_texto


def _regras_abertas(relatorio) -> dict:
    """Quantas pendências abertas há de cada regra (ex.: {"OBRIGATORIO_VAZIO": 15}), para explicar as perguntas."""
    contagem = {}
    if relatorio is None:
        return contagem
    for achado in relatorio.achados:
        aberta = achado.severidade == validador.BLOQUEANTE or (achado.severidade == validador.ALERTA
                                                                 and not achado.resolvido)
        if aberta:
            contagem[achado.regra_id] = contagem.get(achado.regra_id, 0) + 1
    return contagem


# ============================== Um arquivo, um banco novo ==============================

def preparar_o_banco(conexao, foto: dict) -> None:
    """Grava no banco novo a foto do parâmetro em uso (a versão nasce da v1 dos arquivos e vira a da foto)."""
    parametros.salvar_layout(conexao, foto["campos"], f"medição do ganho por tipo (foto da v{foto['versao']})")


def medir_um_arquivo(contexto: ContextoDoArquivo, braco: str, foto: dict, conta: ContaDaIA) -> dict:
    """Mede um arquivo num banco SQLite novo. Devolve o bruto (o que ficou do envio), com o tempo e o custo."""
    entrada = contexto.entrada
    conteudo = (PASTA_DA_PROVA / entrada["arquivo"]).read_bytes()
    # O texto corrido sem IA vai com a IA fora do ar; o resto usa os clientes padrão do modo (MOCK ou real)
    cliente = None
    if braco == "sem_ia" and grupo_do_arquivo(entrada) == "texto_corrido":
        cliente = ClienteSemIA(modo="mock")
    conta.comecar_arquivo()
    conexao = banco.conectar(PASTA_DA_MEDICAO / f"banco_{Path(entrada['arquivo']).stem}.db")
    try:
        preparar_o_banco(conexao, foto)
        inicio = time.perf_counter()
        bruto = enviar_como_a_empresa(conexao, conteudo, cliente, contexto)
        bruto["segundos"] = round(time.perf_counter() - inicio, 2)
        guardar_o_resultado(conexao, bruto)
    finally:
        # O banco do arquivo fecha mesmo se a medição quebrar no meio
        conexao.close()
    bruto["braco"] = braco
    bruto["custo_usd"] = round(conta.custo_do_arquivo_usd, 6)
    bruto["chamadas_reais"] = conta.reais_do_arquivo
    bruto["chamadas_simuladas"] = conta.simuladas_do_arquivo
    bruto["chamadas_por_tarefa"] = dict(conta.por_tarefa)
    return bruto


# ============================== A medição inteira ==============================

def conferir_antes_de_medir(braco: str, ensaio: bool, simular: bool) -> None:
    """Para a medição se o ambiente não é o combinado: SQLite, o modo do braço, a cópia do índice e a prova congelada."""
    if config.BANCO != "sqlite":
        raise SystemExit("A medição só roda no SQLite temporário (nunca no banco de todos).")
    modo_esperado = modo_do_braco(braco, simular)
    if config.MODO != modo_esperado:
        raise SystemExit(f"O braço {braco} precisa de MODE={modo_esperado}, e está {config.MODO}.")
    if not PASTA_DO_INDICE_DA_MEDICAO.exists():
        raise SystemExit("Falta a cópia do índice do RAG em storage/indices_da_medicao (copie o storage/indices).")
    if not ensaio:
        congelamento.exigir_prova_congelada()


def conferir_as_impressoes_digitais(manifesto: dict) -> None:
    """Cada arquivo da prova precisa ser exatamente o do manifesto (o mesmo SHA-256)."""
    for entrada in manifesto["arquivos"]:
        if congelamento.impressao_digital(PASTA_DA_PROVA / entrada["arquivo"]) != entrada["sha256"]:
            raise SystemExit(f"O arquivo {entrada['arquivo']} não bate com o manifesto: a prova mudou.")


def ordem_dos_arquivos(manifesto: dict, so_estes: list[str] | None) -> list[dict]:
    """Os arquivos na ordem da medição: o arquivo 1 de cada tipo, depois o 2, e assim por diante.

    Assim, se a trava de custo parar a medição, todo tipo fica com o mesmo número de arquivos (ou um a menos).
    """
    ordem = sorted(manifesto["arquivos"], key=_numero_e_tipo)
    if so_estes is None:
        return ordem
    escolhidos = []
    for entrada in ordem:
        if entrada["arquivo"] in so_estes:
            escolhidos.append(entrada)
    return escolhidos


def _numero_e_tipo(entrada: dict) -> tuple[int, str]:
    """A chave de ordem: o número do arquivo e depois o tipo."""
    return entrada["numero"], entrada["tipo"]


def custo_esperado(entrada: dict, brutos: dict) -> float:
    """Quanto o próximo arquivo deve custar: o maior entre o esperado do grupo e o maior já medido no mesmo grupo."""
    grupo = grupo_do_arquivo(entrada)
    maior = CUSTO_ESPERADO_POR_GRUPO_USD[grupo]
    for bruto in brutos.values():
        if grupo_do_arquivo(bruto) == grupo:
            maior = max(maior, bruto["custo_usd"])
    return maior


def aquecer_o_rag() -> None:
    """Uma busca no RAG antes da medição: o modelo de vetores carrega uma vez só, fora do tempo do primeiro arquivo."""
    busca.search_rules("CPF do funcionário")


def bruto_que_quebrou(entrada: dict, braco: str, erro: Exception, conta: ContaDaIA) -> dict:
    """O registro de um arquivo em que a MEDIÇÃO quebrou (um erro deste script, e não do sistema medido).

    A régua deixa esse arquivo de fora dos dois braços; o custo gasto nele continua contado.
    """
    return {"arquivo": entrada["arquivo"], "tipo": entrada["tipo"], "braco": braco, "recusado": None,
            "travado_no_aceite": None, "erro_da_medicao": f"{type(erro).__name__}: {erro}", "segundos": 0.0,
            "perguntas_de_coluna": 0, "perguntas_de_formato": 0, "custo_usd": round(conta.custo_do_arquivo_usd, 6),
            "chamadas_reais": conta.reais_do_arquivo, "chamadas_simuladas": conta.simuladas_do_arquivo}


def medir(braco: str, teto_usd: float, ensaio: list[str] | None, simular: bool) -> dict:
    """Mede os arquivos da prova num braço. Devolve {arquivo: bruto}; grava o resultado a cada arquivo."""
    conferir_antes_de_medir(braco, ensaio is not None, simular)
    manifesto = json.loads(CAMINHO_DO_MANIFESTO.read_text(encoding="utf-8"))
    conferir_as_impressoes_digitais(manifesto)
    foto, campos_por_nome = campos_da_foto()
    valores_por_pessoa = ganho_por_tipo.valores_das_pessoas(manifesto)
    aquecer_o_rag()
    conta = ContaDaIA()
    conta.ligar()
    brutos = {}
    for entrada in ordem_dos_arquivos(manifesto, ensaio):
        # A trava de custo: com IA, para antes do arquivo que passaria do teto
        if braco == "com_ia" and conta.custo_total_usd + custo_esperado(entrada, brutos) > teto_usd:
            print(f"Trava de custo: parou antes de {entrada['arquivo']} (gasto US$ {conta.custo_total_usd:.2f}).")
            break
        # A empresa que envia é a do manifesto (o CNPJ do arquivo é o dela)
        contexto = montar_o_contexto(manifesto["empresa_id"], entrada, valores_por_pessoa, campos_por_nome)
        try:
            bruto = medir_um_arquivo(contexto, braco, foto, conta)
        except Exception as erro:  # noqa: BLE001 - um arquivo que quebra a medição não derruba a medição paga
            bruto = bruto_que_quebrou(entrada, braco, erro, conta)
        brutos[entrada["arquivo"]] = bruto
        _mostrar(bruto, conta)
        # Grava a cada arquivo: se a medição parar no meio, o que já foi medido (e pago) não se perde
        gravar_brutos(braco, brutos, ensaio is not None)
    print(f"Medição {braco}: {len(brutos)} arquivos, US$ {conta.custo_total_usd:.4f}. Pasta: {PASTA_DA_MEDICAO}")
    return brutos


def _mostrar(bruto: dict, conta: ContaDaIA) -> None:
    """Uma linha por arquivo no terminal, para acompanhar a medição."""
    situacao = bruto["recusado"] or bruto["travado_no_aceite"] or bruto.get("erro_da_medicao") or bruto.get("etapa_final")
    resumo = bruto.get("resumo_das_pendencias") or {}
    print(f"{datetime.now():%H:%M:%S} {bruto['arquivo']}: {situacao} | colunas perguntadas "
          f"{bruto['perguntas_de_coluna']} | pendências {resumo.get('para_revisar', '-')} | prontas "
          f"{resumo.get('prontas', '-')} | {bruto['segundos']} s | US$ {bruto['custo_usd']:.4f} | reais "
          f"{bruto['chamadas_reais']}, simuladas {bruto['chamadas_simuladas']} | total US$ {conta.custo_total_usd:.4f}",
          flush=True)


def gravar_brutos(braco: str, brutos: dict, ensaio: bool) -> Path:
    """Grava o que ficou de cada arquivo do braço em data/avaliacao/resultados/ganho_por_tipo_<braço>.json.

    No ensaio, grava só na pasta temporária da medição (para conferir a régua), nunca nos resultados.
    """
    caminho = PASTA_DOS_RESULTADOS / f"ganho_por_tipo_{braco}.json"
    if ensaio:
        caminho = PASTA_DA_MEDICAO / f"ensaio_{braco}.json"
    registro = {"braco": braco, "medido_em": datetime.now().isoformat(timespec="seconds"),
                "modelo_grande": config.MODELO_GRANDE if braco == "com_ia" else "mock (dicionário B0 e regras)",
                "modelo_pequeno": config.MODELO_PEQUENO if braco == "com_ia" else "mock",
                "arquivos": brutos}
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return caminho


# ============================== O resumo ==============================

def resumir() -> dict:
    """Junta os dois braços na régua (eval/ganho_por_tipo.py) e grava o resumo por tipo."""
    manifesto = json.loads(CAMINHO_DO_MANIFESTO.read_text(encoding="utf-8"))
    _foto, campos_por_nome = campos_da_foto()
    brutos = {}
    for braco in ("sem_ia", "com_ia"):
        caminho = PASTA_DOS_RESULTADOS / f"ganho_por_tipo_{braco}.json"
        brutos[braco] = {}
        if caminho.exists():
            brutos[braco] = json.loads(caminho.read_text(encoding="utf-8"))["arquivos"]
    resultado = ganho_por_tipo.relatorio(manifesto, brutos["sem_ia"], brutos["com_ia"], campos_por_nome)
    resumo = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "por_tipo": resultado["por_tipo"]}
    caminho = PASTA_DOS_RESULTADOS / "ganho_por_tipo.json"
    caminho.write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    _mostrar_o_resumo(resultado["por_tipo"])
    return resumo


def _numero(valor) -> str:
    """Um número com uma casa, ou "—" quando não há (ex.: as perguntas de um tipo em que todo arquivo voltou)."""
    if valor is None:
        return "—"
    return f"{valor:.1f}"


def _mostrar_o_resumo(por_tipo: dict) -> None:
    """A tabela por tipo no terminal: sem IA × com IA, nas medidas principais."""
    for tipo, linha in por_tipo.items():
        sem_ia = linha["sem_ia"]
        texto = (f"{tipo} {linha['nome']}: SEM IA campo {sem_ia['acerto_por_campo']:.1%} | 4 obrig. "
                 f"{sem_ia['obrigatorios_certos']:.1%} | sem pergunta {sem_ia['sem_pergunta']:.1%} | perguntas/arq. "
                 f"{_numero(sem_ia['perguntas_por_arquivo'])} | recusados {sem_ia['recusados']}")
        if linha["com_ia"]:
            com_ia = linha["com_ia"]
            ganho = linha["ganho"]
            texto += (f"\n    COM IA campo {com_ia['acerto_por_campo']:.1%} | 4 obrig. {com_ia['obrigatorios_certos']:.1%}"
                      f" | sem pergunta {com_ia['sem_pergunta']:.1%} | perguntas/arq. {_numero(com_ia['perguntas_por_arquivo'])}"
                      f" | US$ {com_ia['custo_usd']:.3f} | p50 {com_ia['segundos_p50']:.0f} s"
                      f"\n    GANHO campo {ganho['acerto_por_campo']['diferenca']:+.1%} (p Holm "
                      f"{ganho['acerto_por_campo']['valor_p_holm']:.3g}) | 4 obrig. "
                      f"{ganho['obrigatorios_certos']['diferenca']:+.1%}")
        print(texto)


if __name__ == "__main__":
    if OPCOES.etapa == "parametro":
        foto_gravada = gravar_a_foto_do_parametro()
        print(f"Foto do parâmetro v{foto_gravada['versao']} gravada ({len(foto_gravada['campos'])} campos).")
    elif OPCOES.etapa == "medir":
        if OPCOES.braco is None:
            raise SystemExit("Diga o braço: --braco sem_ia ou --braco com_ia.")
        if OPCOES.braco == "com_ia" and OPCOES.teto_usd <= 0:
            raise SystemExit("Com IA real, diga o teto de custo: --teto-usd (ex.: 5).")
        brutos_da_medicao = medir(OPCOES.braco, OPCOES.teto_usd, OPCOES.ensaio, OPCOES.simular)
        print("Gravado em", gravar_brutos(OPCOES.braco, brutos_da_medicao, OPCOES.ensaio is not None))
    else:
        resumir()
