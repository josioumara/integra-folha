"""O progresso do envio ao vivo (ADR-95): as frases que a tela mostra enquanto o servidor lê.

O que estes testes provam:
- fora de um pedido com código, anotar não faz nada; dentro, a frase do momento fica guardada para quem enviou;
- outra pessoa (outro login) não lê o progresso do pedido; código com formato estranho não é aceito;
- um Word em texto corrido passa pelas frases na ordem: lendo o arquivo, separando por pessoa, lendo N trechos,
  "leu k de N", conferindo e entendendo as colunas; nenhuma frase tem dado de uma pessoa;
- a rota só devolve a frase para quem enviou (404 para o resto).
"""
import io

from docx import Document
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import auth, banco, cadastro, progresso
from tests.test_correcao import busca_falsa

SENHA_DE_TESTE = "senha-de-teste-123"
# Um texto corrido com duas pessoas (dados fictícios)
PARAGRAFOS = [
    "Seguem os novos funcionários.",
    "A Helena Duarte Ramos, CPF 529.982.247-25, entrou em 02/09/2026 como analista, com salário de R$ 5.200,00.",
    "O Rafael Monteiro Siqueira, CPF 111.444.777-35, começou em 08/09/2026 como assistente, salário de R$ 2.750,00.",
]


def word_em_texto_corrido() -> bytes:
    """O Word de teste, feito na hora."""
    documento = Document()
    for paragrafo in PARAGRAFOS:
        documento.add_paragraph(paragrafo)
    memoria = io.BytesIO()
    documento.save(memoria)
    return memoria.getvalue()


def test_anotar_fora_de_um_pedido_nao_faz_nada_e_o_dono_le_a_frase():
    progresso.anotar("sem pedido")
    assert progresso.frase_do_pedido("pedido-sem-dono-1", "rh") is None
    bilhete = progresso.comecar("pedido-de-teste-1", "rh.aurora")
    try:
        assert progresso.frase_do_pedido("pedido-de-teste-1", "rh.aurora") == "Recebi o arquivo."
        progresso.anotar("A IA leu 1 de 2 pessoa(s).")
        assert progresso.frase_do_pedido("pedido-de-teste-1", "rh.aurora") == "A IA leu 1 de 2 pessoa(s)."
        # Outra pessoa não lê o progresso do pedido
        assert progresso.frase_do_pedido("pedido-de-teste-1", "rh.horizonte") is None
    finally:
        progresso.terminar(bilhete)
    # Depois de terminar, anotar não muda mais a frase guardada
    progresso.anotar("depois do fim")
    assert progresso.frase_do_pedido("pedido-de-teste-1", "rh.aurora") == "A IA leu 1 de 2 pessoa(s)."
    assert progresso.codigo_valido("3f2a9c1e-1234-4bcd-9f00-abcdef123456")
    assert not progresso.codigo_valido("curto") and not progresso.codigo_valido("<script>alert(1)</script>")


def test_word_em_texto_corrido_passa_pelas_frases_na_ordem(tmp_path, monkeypatch):
    frases = []
    anotar_original = progresso.anotar

    def anotar_e_guardar(texto):
        frases.append(texto)
        anotar_original(texto)

    monkeypatch.setattr(progresso, "anotar", anotar_e_guardar)
    conexao = banco.conectar(tmp_path / "teste.db")
    bilhete = progresso.comecar("pedido-do-word-1", "rh.aurora")
    try:
        cadastro.enviar_arquivo(conexao, "EMP001", "rh.aurora", word_em_texto_corrido(), "novos.docx",
                                busca=busca_falsa)
    finally:
        progresso.terminar(bilhete)
        conexao.close()
    assert frases[0] == "Lendo o arquivo."
    assert "É um texto corrido: o Agente Leitor está separando o texto por pessoa." in frases
    # A IA simulada divide o texto em 3 trechos (a abertura do e-mail e as 2 pessoas)
    assert "O Agente Leitor está lendo 3 trecho(s) do texto." in frases and "O Agente Leitor leu 3 de 3 trecho(s)." in frases
    assert frases.index("O Agente Leitor leu 3 de 3 trecho(s).") < frases.index("Conferindo cada valor com o documento.")
    assert frases[-1] == "Os agentes estão entendendo cada coluna e ligando ao layout do banco."
    # Nenhuma frase tem dado de alguém
    for frase in frases:
        assert "Helena" not in frase and "529" not in frase


def test_rota_do_progresso_so_para_quem_enviou(tmp_path, monkeypatch):
    conectar_original = auth.conectar
    caminho = tmp_path / "api_progresso.db"
    monkeypatch.setattr(auth, "conectar", lambda caminho_pedido=None: conectar_original(caminho))
    conexao = conectar_original(caminho)
    auth.cadastrar_usuario(conexao, "rh.aurora", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    auth.cadastrar_usuario(conexao, "rh.horizonte", SENHA_DE_TESTE, Perfil.EMPRESA, "EMP002")
    conexao.close()
    bilhete = progresso.comecar("pedido-da-rota-1", "rh.aurora")
    progresso.terminar(bilhete)
    aurora, horizonte = TestClient(aplicacao), TestClient(aplicacao)
    aurora.post("/api/entrar", json={"usuario": "rh.aurora", "senha": SENHA_DE_TESTE})
    horizonte.post("/api/entrar", json={"usuario": "rh.horizonte", "senha": SENHA_DE_TESTE})
    assert aurora.get("/api/empresa/cadastro/progresso/pedido-da-rota-1").json() == {"texto": "Recebi o arquivo."}
    assert horizonte.get("/api/empresa/cadastro/progresso/pedido-da-rota-1").status_code == 404
    assert aurora.get("/api/empresa/cadastro/progresso/pedido-que-nao-existe").status_code == 404
