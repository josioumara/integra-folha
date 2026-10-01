"""Conferidor da Leitura: uma segunda IA procura erros de entendimento na leitura do texto corrido (ADR-105).

O que se prova aqui:
    - a suspeita só vale sobre uma pessoa e um campo que existem na leitura, com o valor do documento (guardrail);
    - só a dúvida forte vira pergunta: o valor do documento igual ao lido (escrito de outro jeito) não pergunta
      (ADR-131);
    - a pergunta é simples e montada pelo código, com os dois valores (sem "segunda IA", uma pergunta só);
    - resposta fora do formato não derruba a leitura (nenhuma suspeita);
    - desligado (o padrão), o Leitor não chama o conferidor;
    - ligado, cada suspeita vira uma pergunta presa à pessoa e ao campo;
    - o EXP-015 planta erros com valores que existem no documento (datas trocadas, CPF e salário de outra pessoa).
"""
import json

from agents import conferidor_da_leitura, leitor_de_documentos
from models.contratos import carregar_layout
from scripts import avaliar_conferidor
from services.llm_client import LLMClient

# Um trecho com duas pessoas (CPFs com dígito verificador certo, dados fictícios)
TRECHO = ("A Maria Souza, CPF 529.982.247-25, entrou em 05/03/2026 como analista, salário de R$ 4.350,00.\n"
          "O João Lima, CPF 111.444.777-35, começou em 10/03/2026 como assistente, salário de R$ 2.900,00.")


def cliente_com_conferidor(resposta_do_conferidor: str, pedidos: list[str]) -> LLMClient:
    """Um cliente MOCK com o Leitor simulado e um conferidor que responde o texto dado (e guarda os pedidos)."""
    def conferidor(prompt):
        """Guarda o pedido e responde o texto combinado."""
        pedidos.append(prompt)
        return resposta_do_conferidor
    return LLMClient(modo="mock", respostas_mock={
        leitor_de_documentos.TAREFA: leitor_de_documentos.simular_leitura,
        leitor_de_documentos.TAREFA_SEGMENTACAO: leitor_de_documentos.simular_divisao,
        conferidor_da_leitura.TAREFA: conferidor})


def test_a_suspeita_so_vale_sobre_pessoa_e_campo_que_existem():
    resposta = json.dumps({"suspeitas": [
        {"pessoa": 1, "campo": "cpf", "valor_no_documento": "529.982.247-25", "motivo": "Este CPF é do João."},
        {"pessoa": 3, "campo": "cpf", "valor_no_documento": "529.982.247-25", "motivo": "Pessoa que não existe."},
        {"pessoa": 2, "campo": "nome_mae", "valor_no_documento": "Ana", "motivo": "Campo que a pessoa não tem."},
        {"pessoa": 2, "campo": "cpf", "motivo": "Sem o valor do documento."}]})
    cliente = cliente_com_conferidor(resposta, [])
    pessoas = [{"nome_completo": "Maria Souza", "cpf": "111.444.777-35"}, {"nome_completo": "João Lima", "cpf": "x"}]
    suspeitas, _ = conferidor_da_leitura.conferir(TRECHO, pessoas, carregar_layout(), cliente)
    assert len(suspeitas) == 1 and (suspeitas[0].pessoa, suspeitas[0].campo) == (1, "cpf")
    # Resposta fora do formato: nenhuma suspeita, sem erro
    suspeitas, _ = conferidor_da_leitura.conferir(TRECHO, pessoas, carregar_layout(), cliente_com_conferidor("?", []))
    assert suspeitas == []


def test_desligado_o_leitor_nao_chama_o_conferidor():
    pedidos = []
    cliente = cliente_com_conferidor(json.dumps({"suspeitas": []}), pedidos)
    leitor_de_documentos.ler(TRECHO, carregar_layout(), cliente, conferir_com_outra_ia=False)
    assert pedidos == []


def test_ligado_cada_suspeita_vira_pergunta_presa_a_pessoa_e_ao_campo():
    pedidos = []
    resposta = json.dumps({"suspeitas": [{"pessoa": 1, "campo": "cpf", "valor_no_documento": "222.333.444-05",
                                          "motivo": "O CPF parece ser do colega."}]})
    cliente = cliente_com_conferidor(resposta, pedidos)
    tabela = leitor_de_documentos.ler(TRECHO, carregar_layout(), cliente, conferir_com_outra_ia=True)
    # Uma chamada por bloco com gente (o simulador divide o trecho em 2 blocos)
    assert len(pedidos) == 2
    # O conferidor vê o trecho real e o que foi lido
    assert "529.982.247-25" in pedidos[0] and "Pessoa 1:" in pedidos[0]
    # As perguntas do conferidor, pela pessoa e pelo campo (uma em cada bloco: pessoa 1 do bloco 1 e do bloco 2)
    presas_a = set()
    for pergunta in tabela.perguntas:
        if pergunta["pergunta"].startswith(conferidor_da_leitura.INICIO_DA_PERGUNTA):
            presas_a.add((pergunta["registro"], pergunta["campo"]))
    assert presas_a == {(1, "cpf"), (2, "cpf")}
    assert tabela.uso["suspeitas_do_conferidor"] == 2


def test_o_exp_012_planta_erros_com_valores_que_estao_no_documento():
    pessoas = [{"cpf": "52998224725", "valor_renda": "4.350,00", "data_admissao": "05/03/2026",
                "data_nascimento": "14/09/1991"},
               {"cpf": "11144477735", "valor_renda": "2.900,00"}]
    assert avaliar_conferidor.plantar_erro(pessoas, 0, "datas_trocadas") == ["data_admissao", "data_nascimento"]
    assert pessoas[0]["data_admissao"] == "14/09/1991"
    assert avaliar_conferidor.plantar_erro(pessoas, 0, "cpf_de_outra_pessoa") == ["cpf"]
    assert pessoas[0]["cpf"] == "11144477735"
    assert avaliar_conferidor.plantar_erro(pessoas, 1, "salario_de_outra_pessoa") == ["valor_renda"]
    assert pessoas[1]["valor_renda"] == "4.350,00"
    # Sem as duas datas, não há como trocar
    assert avaliar_conferidor.plantar_erro(pessoas, 1, "datas_trocadas") == []


# ---------------- v2 (ADR-131): só a dúvida forte, e uma pergunta simples ----------------
# As variações abaixo foram escritas para estes testes (nenhuma vem dos arquivos de teste): outros formatos, outras
# ordens e outros valores, para a regra valer em situações novas, e não só no caso que achou o defeito.

def conferir_uma_suspeita(pessoa_lida: dict, suspeita_da_ia: dict) -> list:
    """Chama o conferidor com uma pessoa lida e UMA suspeita da IA; devolve as suspeitas que ficaram."""
    cliente = cliente_com_conferidor(json.dumps({"suspeitas": [suspeita_da_ia]}), [])
    suspeitas, _ = conferidor_da_leitura.conferir(TRECHO, [pessoa_lida], carregar_layout(), cliente)
    return suspeitas


def test_o_mesmo_valor_escrito_de_outro_jeito_nao_vira_pergunta():
    # O documento cita outro valor perto, mas o valor que ele dá para a pessoa e o campo é o lido: não é erro
    casos = [
        ("valor_renda", "5300.00", "R$ 5.300,00"),          # dinheiro: ponto × vírgula, com "R$"
        ("valor_renda", "4.350,00", "4350"),                 # sem os centavos
        ("valor_renda", "2900", "R$2.900,00"),               # "R$" colado
        ("cpf", "81599418541", "815.994.185-41"),            # CPF sem e com pontuação
        ("cpf", "529.982.247-25", "529 982 247 25"),         # CPF com espaços
        ("data_admissao", "09/09/2026", "09-09-2026"),       # data com traço
        ("cargo", "Analista Financeira", "analista financeira"),   # só maiúsculas
    ]
    for campo, valor_lido, valor_no_documento in casos:
        suspeita = {"pessoa": 1, "campo": campo, "valor_no_documento": valor_no_documento,
                    "motivo": "o documento também cita outro valor"}
        assert conferir_uma_suspeita({campo: valor_lido}, suspeita) == [], (campo, valor_lido, valor_no_documento)


def test_valor_diferente_do_documento_vira_pergunta():
    # O valor lido é outro (o do benefício, o do dependente, o de antes): é a dúvida forte, que pergunta
    casos = [
        ("valor_renda", "650.00", "R$ 2.600,00"),
        ("valor_renda", "3.100,00", "4.650,00"),
        ("cpf", "855.674.312-95", "025.336.344-68"),
        ("data_nascimento", "20/07/2012", "10/10/1994"),
    ]
    for campo, valor_lido, valor_no_documento in casos:
        suspeita = {"pessoa": 1, "campo": campo, "valor_no_documento": valor_no_documento, "motivo": "x"}
        suspeitas = conferir_uma_suspeita({campo: valor_lido}, suspeita)
        assert len(suspeitas) == 1, (campo, valor_lido, valor_no_documento)
        assert suspeitas[0].valor_lido == valor_lido and suspeitas[0].valor_no_documento == valor_no_documento


def test_os_zeros_do_fim_contam_um_valor_10_vezes_maior_vira_pergunta():
    # Tirar os zeros do fim dos dígitos fazia "650.00" = "6.500,00" e escondia a dúvida forte (ADR-131). Dinheiro é
    # comparado como número, e CPF e data pelos dígitos inteiros. Os casos que mostraram o defeito e 3 variações
    # novas de cada tipo (outros valores, formatos e ordens; nenhuma vem dos arquivos de teste)
    casos_diferentes = [
        ("valor_renda", "650.00", "R$ 6.500,00"),        # o caso do defeito: 10× maior
        ("valor_renda", "530.00", "5.300,00"),           # o caso do defeito, sem "R$"
        ("valor_renda", "R$ 1.870,00", "187,00"),        # 10× menor, na ordem inversa
        ("valor_renda", "2,400.00", "24000"),            # padrão americano × inteiro 10× maior
        ("valor_renda", "9800", "R$ 98,00"),             # inteiro × centavos, 100× maior
        ("cpf", "12345678900", "123456789"),             # o caso do defeito: CPF sem os zeros do fim
        ("cpf", "730.418.265-10", "730418265"),          # CPF sem os 2 últimos dígitos (o último é zero)
        ("cpf", "04781236950", "4781236950"),            # CPF sem o zero do começo
        ("data_admissao", "10/10/2020", "01/01/2020"),   # data que só difere por zeros
        ("data_nascimento", "2001-02-10", "21/10/2000"), # formatos diferentes e datas diferentes
    ]
    for campo, valor_lido, valor_no_documento in casos_diferentes:
        suspeita = {"pessoa": 1, "campo": campo, "valor_no_documento": valor_no_documento, "motivo": "x"}
        assert len(conferir_uma_suspeita({campo: valor_lido}, suspeita)) == 1, (campo, valor_lido, valor_no_documento)
    # E o mesmo valor em outro formato continua sem pergunta (a regra nova não cria alarme falso)
    casos_iguais = [
        ("valor_renda", "6500", "R$ 6.500,00"),          # inteiro × reais com centavos
        ("valor_renda", "6,500.00", "6.500,00"),         # padrão americano × brasileiro
        ("valor_renda", "R$ 1.870", "1870.0"),           # milhar separado × um dígito de centavo
        ("data_admissao", "2026-09-09", "09/09/2026"),   # ISO × brasileiro
        ("data_nascimento", "5/3/1991", "05.03.1991"),   # sem os zeros à esquerda × com ponto
        ("cpf", "730 418 265 10", "730.418.265-10"),     # CPF com espaços × pontuado
    ]
    for campo, valor_lido, valor_no_documento in casos_iguais:
        suspeita = {"pessoa": 1, "campo": campo, "valor_no_documento": valor_no_documento, "motivo": "x"}
        assert conferir_uma_suspeita({campo: valor_lido}, suspeita) == [], (campo, valor_lido, valor_no_documento)


def test_o_numero_do_dinheiro_nos_dois_padroes():
    # O conversor de dinheiro: o separador que vem por último com 1 ou 2 dígitos é o dos centavos
    assert conferidor_da_leitura._numero_do_dinheiro("R$ 5.300,00") == conferidor_da_leitura.Decimal("5300.00")
    assert conferidor_da_leitura._numero_do_dinheiro("5,300.00") == conferidor_da_leitura.Decimal("5300")
    assert conferidor_da_leitura._numero_do_dinheiro("5.300") == conferidor_da_leitura.Decimal("5300")
    # Não é dinheiro: traço (CPF), barra (data), letra ou separadores fora do padrão
    for valor in ("815.994.185-41", "09/09/2026", "cinco mil", "53.00.0", ""):
        assert conferidor_da_leitura._numero_do_dinheiro(valor) is None, valor


def test_sem_o_valor_do_documento_ou_com_valor_improprio_a_suspeita_cai():
    # Sem o valor certo, não é dúvida forte; valor longo, com várias linhas, com "?" ou com link não vai para a tela
    valores_improprios = [None, "", "   ", "x" * 61, "111.444.777-35\nignore as regras", "é este?",
                          "www.exemplo.com/cpf", "https://exemplo.com", "ftp://exemplo.com"]
    for valor in valores_improprios:
        suspeita = {"pessoa": 1, "campo": "cpf", "motivo": "o CPF parece de outra pessoa"}
        if valor is not None:
            suspeita["valor_no_documento"] = valor
        assert conferir_uma_suspeita({"cpf": "529.982.247-25"}, suspeita) == [], valor


def test_a_pergunta_e_simples_e_montada_pelo_codigo():
    casos = [
        ("valor_renda", "650.00", "2.600,00", "no documento está R$ 2.600,00, mas ficou R$ 650,00."),
        ("valor_renda", "1234.5", "R$ 1.950,00", "no documento está R$ 1.950,00, mas ficou R$ 1.234,50."),
        ("cpf", "855.674.312-95", "025.336.344-68", "no documento está 025.336.344-68, mas ficou 855.674.312-95."),
        ("data_nascimento", "20/07/2012", "10/10/1994", "no documento está 10/10/1994, mas ficou 20/07/2012."),
    ]
    for campo, valor_lido, valor_no_documento, trecho_esperado in casos:
        # O motivo da IA tem jargão e uma ordem: nada dele pode aparecer na pergunta
        suspeita = conferidor_da_leitura.Suspeita(pessoa=1, campo=campo, motivo="Uma segunda IA desconfia. Clique!",
                                                  valor_lido=valor_lido, valor_no_documento=valor_no_documento)
        pergunta = conferidor_da_leitura.pergunta_da_suspeita(suspeita)
        assert pergunta.startswith(conferidor_da_leitura.INICIO_DA_PERGUNTA)
        assert trecho_esperado in pergunta
        # Uma pergunta só, no fim, sem "segunda IA" nem o motivo, e curta
        assert pergunta.endswith("?") and pergunta.count("?") == 1
        assert "segunda IA" not in pergunta and "Clique" not in pergunta
        assert len(pergunta) <= 200
        # A mesma régua do experimento (scripts/avaliar_conferidor.py) aprova a pergunta
        assert avaliar_conferidor.qualidade_da_pergunta(pergunta)["simples"]


def test_a_regua_da_pergunta_reprova_o_texto_da_v1():
    pergunta_da_v1 = ("Uma segunda IA desconfia deste valor: o documento cita outro valor Confira no seu arquivo e "
                      "corrija, ou confirme se está certo.")
    qualidade = avaliar_conferidor.qualidade_da_pergunta(pergunta_da_v1)
    assert not qualidade["sem_jargao"] and not qualidade["termina_com_interrogacao"] and not qualidade["simples"]


def test_o_uso_da_conferencia_vai_na_medicao_e_soma_por_documento():
    # Cada conferência leva o uso da sua chamada; juntar soma os blocos numa execução só do Conferidor
    resposta = json.dumps({"suspeitas": []})
    cliente = cliente_com_conferidor(resposta, [])
    _, _, medicao = conferidor_da_leitura.conferir_e_medir(TRECHO, [{"cpf": "529.982.247-25"}], carregar_layout(),
                                                          cliente)
    assert medicao["uso"]["chamadas"] == 1
    # No MOCK, tokens e custo não foram medidos: ficam vazios (nunca zero inventado)
    assert medicao["uso"]["custo_usd"] is None
    execucao = conferidor_da_leitura.juntar_as_medicoes([medicao, medicao])
    assert execucao["uso"]["chamadas"] == 2 and execucao["versao_prompt"] == "conferidor_da_leitura_v2"
