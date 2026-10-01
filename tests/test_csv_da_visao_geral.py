"""O "Baixar CSV" da Visão geral do especialista.

O que estes testes provam:
- o arquivo tem todas as colunas do cadastro: os campos obrigatórios do parâmetro (sempre, mesmo vazios), os opcionais
  que vieram para alguém da empresa (o que não veio para ninguém fica de fora), a situação, a conta e a inclusão;
- as colunas seguem a marca "obrigatorio" do parâmetro, e não uma lista escrita no código (variações novas: outro
  conjunto de obrigatórios, um opcional que veio para uma pessoa só, um opcional só com espaços);
- o padrão dos outros arquivos que o sistema baixa: separador ";", UTF-8 com a marca do Excel e a proteção contra
  fórmula do Excel;
- o arquivo sai só da empresa pedida (uma empresa nunca vê a outra) e só para o perfil BANCO: 401 sem login, 403 para
  a empresa, 404 para a empresa que não existe e 400 para a empresa ainda sem funcionários;
- cada download fica registrado nos acessos da empresa (quem, o tipo e quantas pessoas).

A lista das pessoas e as colunas do parâmetro são trocadas por listas de mentira (monkeypatch): cada teste diz
exatamente o que a empresa tem. O caminho de verdade, com a carga da Aurora cadastrada, é conferido no roteiro de
clique ficha_da_empresa.
"""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from api.principal import aplicacao
from models.contratos import Perfil
from services import acompanhamento, auth, portal_do_banco

# Senha dos usuários de teste deste arquivo (tem os 8 caracteres mínimos)
SENHA_DE_TESTE = "senha-de-teste-123"
# Os logins deste arquivo (únicos: o banco temporário é o mesmo da bateria inteira)
LOGIN_DO_BANCO = "csv.visao.banco"
LOGIN_DA_EMPRESA = "csv.visao.empresa"
# A marca do começo do arquivo que avisa o Excel de que ele é UTF-8
MARCA_DO_UTF8 = "﻿"
# As colunas do fim do arquivo, depois dos campos do parâmetro
COLUNAS_DO_FIM = ["Situação", "Código do banco", "Agência", "Conta salário", "Conta salário aberta em", "Incluído em",
                  "Incluído por"]


def coluna(campo: str, rotulo: str, obrigatorio: bool) -> dict:
    """Uma coluna do parâmetro no formato de acompanhamento.colunas_da_consulta (o grupo e o tipo não importam aqui)."""
    return {"campo": campo, "rotulo": rotulo, "grupo": "Titular", "tipo": "TEXTO", "obrigatorio": obrigatorio,
            "descricao": ""}


# O parâmetro de mentira de hoje: os 4 obrigatórios do ADR-143 e dois opcionais
COLUNAS_DE_HOJE = [
    coluna("cpf", "CPF", True),
    coluna("nome_completo", "Nome completo", False),
    coluna("codigo_cbo", "Código CBO", True),
    coluna("telefone_celular", "Telefone celular", False),
    coluna("data_admissao", "Data admissão", True),
    coluna("valor_renda", "Valor renda", True),
]


def pessoa(cpf: str, situacao: str, **outros) -> dict:
    """Um funcionário no formato da lista da Visão geral, só com o que o teste precisa.

    Ex.: pessoa("529.982.247-25", "Cadastrado", nome_completo="Ana") → {"cpf": ..., "situacao": ..., ...}.
    """
    registro = {"cpf": cpf, "situacao": situacao, "codigo_cbo": "", "data_admissao": "2021-06-18",
                "valor_renda": "2726.00", "nome_completo": "", "telefone_celular": "", "incluido_em": "",
                "incluido_por": ""}
    registro.update(outros)
    return registro


# As pessoas de cada empresa, na lista de mentira (a EMP002 existe na semente e tem outra gente)
PESSOAS_POR_EMPRESA = {
    "EMP001": [
        pessoa("529.982.247-25", "Conta aberta", nome_completo="Ana Souza", codigo_cbo="411010", agencia="0001",
               conta="45962-0", conta_aberta_em="2026-09-24", incluido_em="2026-09-24T10:00:00+00:00",
               incluido_por="rh.aurora"),
        pessoa("111.444.777-35", "Pendente", incluido_em="2026-09-29T08:30:00+00:00", incluido_por="rh.aurora"),
    ],
    "EMP002": [
        pessoa("390.533.447-05", "Cadastrado", nome_completo="Bruno da Horizonte"),
    ],
}


@pytest.fixture(scope="module", autouse=True)
def usuarios_de_teste():
    """Um especialista do banco e uma pessoa do RH da Aurora, uma vez para este arquivo."""
    conexao = auth.conectar()
    auth.cadastrar_usuario(conexao, LOGIN_DO_BANCO, SENHA_DE_TESTE, Perfil.BANCO)
    auth.cadastrar_usuario(conexao, LOGIN_DA_EMPRESA, SENHA_DE_TESTE, Perfil.EMPRESA, "EMP001")
    conexao.close()


@pytest.fixture
def carteira_de_mentira(monkeypatch):
    """Troca a lista das pessoas e as colunas do parâmetro pelas de mentira. Devolve os dois, para o teste mudar.

    A lista respeita a empresa pedida, como a de verdade (acompanhamento.todos_os_funcionarios_da_empresa): uma empresa
    sem pessoas na lista de mentira devolve a lista vazia.
    """
    colunas = list(COLUNAS_DE_HOJE)
    pessoas_por_empresa = {}
    for empresa_id, pessoas in PESSOAS_POR_EMPRESA.items():
        pessoas_por_empresa[empresa_id] = list(pessoas)

    def todos_os_funcionarios_de_mentira(conexao, empresa_id):
        """As pessoas da empresa pedida (e só dela)."""
        return pessoas_por_empresa.get(empresa_id, [])

    def colunas_de_mentira(conexao):
        """As colunas do parâmetro de mentira."""
        return colunas

    monkeypatch.setattr(acompanhamento, "todos_os_funcionarios_da_empresa", todos_os_funcionarios_de_mentira)
    monkeypatch.setattr(acompanhamento, "colunas_da_consulta", colunas_de_mentira)
    return {"colunas": colunas, "pessoas": pessoas_por_empresa}


def navegador_logado(login: str) -> TestClient:
    """Um navegador de mentira já logado com o usuário informado."""
    navegador = TestClient(aplicacao, follow_redirects=False)
    resposta = navegador.post("/api/entrar", json={"usuario": login, "senha": SENHA_DE_TESTE})
    assert resposta.status_code == 200
    return navegador


def especialista() -> auth.Usuario:
    """O usuário do banco, para chamar o serviço direto."""
    return auth.Usuario(login=LOGIN_DO_BANCO, perfil=Perfil.BANCO, empresa_id=None)


def linhas_do_arquivo(conteudo: bytes) -> list[list[str]]:
    """As linhas do CSV, já separadas pelo ";" (sem a marca do UTF-8 do começo)."""
    texto = conteudo.decode("utf-8")
    assert texto.startswith(MARCA_DO_UTF8)
    return list(csv.reader(io.StringIO(texto[len(MARCA_DO_UTF8):]), delimiter=";"))


def arquivo_pelo_servico(empresa_id: str) -> tuple[list[list[str]], str]:
    """O arquivo de uma empresa pedido direto ao serviço. Devolve (as linhas, o nome do arquivo)."""
    conexao = auth.conectar()
    try:
        conteudo, nome = portal_do_banco.arquivo_dos_funcionarios_da_empresa(conexao, especialista(), empresa_id)
    finally:
        conexao.close()
    return linhas_do_arquivo(conteudo), nome


# ---------- As colunas ----------

def test_o_arquivo_tem_os_obrigatorios_os_opcionais_que_vieram_e_as_colunas_do_fim(carteira_de_mentira):
    linhas, nome = arquivo_pelo_servico("EMP001")
    assert nome == "funcionarios_EMP001.csv"
    # Os obrigatórios na ordem do layout, depois o opcional que veio (o telefone não veio para ninguém), e o fim
    assert linhas[0] == ["CPF", "Código CBO", "Data admissão", "Valor renda", "Nome completo"] + COLUNAS_DO_FIM
    # Uma linha por pessoa, com os valores como a grade os recebe e a data da inclusão sem a hora
    assert linhas[1] == ["529.982.247-25", "411010", "2021-06-18", "2726.00", "Ana Souza", "Conta aberta", "",
                         "0001", "45962-0", "2026-09-24", "2026-09-24", "rh.aurora"]
    # A pessoa pendente, sem conta: as colunas da conta vazias, e o obrigatório que não veio também vazio
    assert linhas[2] == ["111.444.777-35", "", "2021-06-18", "2726.00", "", "Pendente", "", "", "", "",
                         "2026-09-29", "rh.aurora"]
    assert len(linhas) == 3


def test_as_colunas_seguem_a_marca_do_parametro_e_nao_uma_lista_do_codigo(carteira_de_mentira):
    """Variação nova: o banco marca outros campos como obrigatórios; o arquivo acompanha sozinho."""
    colunas = carteira_de_mentira["colunas"]
    colunas.clear()
    colunas.extend([coluna("nome_completo", "Nome completo", True), coluna("cpf", "CPF", False),
                    coluna("valor_renda", "Valor renda", True), coluna("telefone_celular", "Telefone celular", False)])
    linhas, _ = arquivo_pelo_servico("EMP001")
    # Os obrigatórios (nome e renda), mesmo com uma pessoa sem nome; o CPF, agora opcional, entra porque veio
    assert linhas[0] == ["Nome completo", "Valor renda", "CPF"] + COLUNAS_DO_FIM


def test_o_opcional_que_veio_para_uma_pessoa_so_entra_e_o_so_com_espacos_fica_de_fora(carteira_de_mentira):
    """Variações novas: o opcional que veio para uma pessoa só entra; o que só tem espaços conta como vazio."""
    pessoas = carteira_de_mentira["pessoas"]["EMP001"]
    pessoas[1] = dict(pessoas[1], telefone_celular="(19) 99876-5432")
    pessoas[0] = dict(pessoas[0], nome_completo="   ")
    linhas, _ = arquivo_pelo_servico("EMP001")
    assert linhas[0] == ["CPF", "Código CBO", "Data admissão", "Valor renda", "Telefone celular"] + COLUNAS_DO_FIM
    assert linhas[1][4] == "" and linhas[2][4] == "(19) 99876-5432"


def test_valor_com_cara_de_formula_vira_texto(carteira_de_mentira):
    """A proteção contra fórmula do Excel, a mesma dos outros arquivos ("CSV injection")."""
    pessoas = carteira_de_mentira["pessoas"]["EMP001"]
    pessoas[0] = dict(pessoas[0], nome_completo="=HYPERLINK(\"http://golpe\")", incluido_por="@rh")
    linhas, _ = arquivo_pelo_servico("EMP001")
    assert linhas[1][4] == "'=HYPERLINK(\"http://golpe\")"
    assert linhas[1][-1] == "'@rh"


def test_o_arquivo_usa_o_separador_e_a_codificacao_dos_outros_arquivos(carteira_de_mentira):
    conexao = auth.conectar()
    try:
        conteudo, _ = portal_do_banco.arquivo_dos_funcionarios_da_empresa(conexao, especialista(), "EMP001")
    finally:
        conexao.close()
    # A marca do UTF-8 (os 3 bytes do começo), o ";" entre as colunas e o acento certo
    assert conteudo.startswith("﻿".encode("utf-8"))
    primeira_linha = conteudo.decode("utf-8").splitlines()[0]
    assert primeira_linha.startswith("﻿CPF;Código CBO;") and "Situação" in primeira_linha


# ---------- Só a empresa pedida, só o banco ----------

def test_uma_empresa_nunca_aparece_no_arquivo_da_outra(carteira_de_mentira):
    linhas_da_aurora, _ = arquivo_pelo_servico("EMP001")
    linhas_da_horizonte, nome = arquivo_pelo_servico("EMP002")
    texto_da_aurora = str(linhas_da_aurora)
    assert "390.533.447-05" not in texto_da_aurora and "Bruno" not in texto_da_aurora
    assert nome == "funcionarios_EMP002.csv" and len(linhas_da_horizonte) == 2
    assert "529.982.247-25" not in str(linhas_da_horizonte)


def test_a_rota_so_do_banco_com_o_arquivo_e_o_acesso_registrado(carteira_de_mentira):
    banco = navegador_logado(LOGIN_DO_BANCO)
    resposta = banco.get("/api/banco/empresas/EMP001/funcionarios/baixar")
    assert resposta.status_code == 200
    # O navegador baixa com o nome da empresa, não guarda cópia, e o tipo é o do CSV
    assert resposta.headers["Content-Disposition"] == "attachment; filename=\"funcionarios_EMP001.csv\""
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.headers["Content-Type"].startswith("text/csv")
    assert linhas_do_arquivo(resposta.content)[1][0] == "529.982.247-25"
    # O download ficou registrado: quem, o tipo e quantas pessoas (nunca o CPF)
    conexao = auth.conectar()
    ultimo_acesso = acompanhamento.acessos_da_empresa(conexao, "EMP001")[-1]
    conexao.close()
    assert (ultimo_acesso["login"], ultimo_acesso["tipo"], ultimo_acesso["quantidade"]) == (LOGIN_DO_BANCO,
                                                                                            "DOWNLOAD", 2)


def test_sem_login_401_empresa_403_e_empresa_que_nao_existe_404(carteira_de_mentira):
    endereco = "/api/banco/empresas/EMP001/funcionarios/baixar"
    assert TestClient(aplicacao).get(endereco).status_code == 401
    # A empresa não baixa pela porta do banco, nem a própria lista
    assert navegador_logado(LOGIN_DA_EMPRESA).get(endereco).status_code == 403
    assert navegador_logado(LOGIN_DO_BANCO).get("/api/banco/empresas/NAO_EXISTE/funcionarios/baixar").status_code == 404


def test_empresa_sem_funcionarios_da_400_com_o_motivo(carteira_de_mentira):
    """A EMP003 existe na semente, mas não tem ninguém na lista de mentira: não há o que baixar."""
    resposta = navegador_logado(LOGIN_DO_BANCO).get("/api/banco/empresas/EMP003/funcionarios/baixar")
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Esta empresa ainda não tem funcionários para baixar."


def test_a_lista_de_verdade_de_uma_empresa_sem_envios_tambem_da_400():
    """Sem a lista de mentira: a empresa da semente, num banco sem envios, ainda não tem funcionários."""
    resposta = navegador_logado(LOGIN_DO_BANCO).get("/api/banco/empresas/EMP004/funcionarios/baixar")
    assert resposta.status_code == 400
