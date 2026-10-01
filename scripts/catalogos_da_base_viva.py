"""Os catálogos da base viva: as 17 empresas, as profissões, os nomes e os estilos de arquivo (desenho §3.8).

Para que serve: a "base viva" são dados 100% sintéticos que fazem a plataforma parecer em uso. São 17 empresas novas,
além das 6 fictícias de sempre, cada uma com o RH que entra no portal, os envios em várias etapas da jornada, os
funcionários cadastrados (com o código da profissão, o CBO), as contas que o banco abriu, os acessos e as conversas.
Este arquivo guarda só o que é FIXO e escrito à mão (as empresas, as profissões de cada setor, as listas de nomes e
os jeitos de cada sistema de RH escrever o arquivo). Quem sorteia as pessoas e grava os arquivos é o
scripts/gerar_base_viva.py; quem põe tudo no banco de dados é o scripts/carregar_base_viva.py.

Regras que valem para tudo aqui (as regras do projeto):
    - nada é real: os nomes das empresas foram inventados e conferidos numa busca, para não coincidir com marca
      conhecida (30/09/2026); os domínios de e-mail terminam em ".example", um nome reservado que nunca é de ninguém
      (norma RFC 2606); as ruas e os bairros são genéricos;
    - a região de cada empresa é a do cadastro dela (UF e município): as unidades de trabalho ficam no mesmo município;
    - nada daqui entra na IA: nenhum exemplo vai para prompt, regra ou base do RAG.

As datas não estão aqui: cada envio diz só quantos DIAS ÚTEIS antes da carga ele chegou. Assim a plataforma continua
"recente" em qualquer dia em que a carga rodar (na máquina local ou na hospedagem final).
"""
from datetime import date

# A data de referência do gerador: as datas DENTRO dos arquivos (nascimento, admissão...) são sorteadas contando a
# partir dela. É fixa, e não "hoje", para o mesmo conjunto poder ser refeito igual (regra da semente fixa)
REFERENCIA_DO_GERADOR = date(2026, 9, 30)

# O código do banco parceiro nos arquivos de contas abertas (o layout fixo pede 3 dígitos; o exemplo dele é o 033)
CODIGO_DO_BANCO = "033"

# ================================ As profissões ================================
# Cada cargo aparece sempre com o MESMO código CBO (da tabela oficial em data/cbo): assim a comparação de salário
# entre empresas (a faixa das outras empresas, ADR-129) junta pessoas que fazem de fato a mesma coisa.
# "tipo_renda": CLT para os empregados; PRO_LABORE só para o sócio (a comparação por profissão é só do CLT).
PROFISSOES = {
    # Administração (aparece em quase todas as empresas)
    "Assistente administrativo": {"cbo": "411010", "tipo_renda": "CLT"},
    "Auxiliar de escritório": {"cbo": "411005", "tipo_renda": "CLT"},
    "Auxiliar de pessoal": {"cbo": "411030", "tipo_renda": "CLT"},
    "Analista de recursos humanos": {"cbo": "252405", "tipo_renda": "CLT"},
    "Gerente administrativo": {"cbo": "142105", "tipo_renda": "CLT"},
    "Técnico em segurança do trabalho": {"cbo": "351605", "tipo_renda": "CLT"},
    "Almoxarife": {"cbo": "414105", "tipo_renda": "CLT"},
    "Recepcionista": {"cbo": "422105", "tipo_renda": "CLT"},
    "Faxineiro": {"cbo": "514320", "tipo_renda": "CLT"},
    "Sócio-administrador": {"cbo": "121010", "tipo_renda": "PRO_LABORE"},
    # Indústria
    "Montador de eletrônicos": {"cbo": "731110", "tipo_renda": "CLT"},
    "Alimentador de linha de produção": {"cbo": "784205", "tipo_renda": "CLT"},
    "Técnico de manutenção eletrônica": {"cbo": "313205", "tipo_renda": "CLT"},
    "Inspetor de qualidade": {"cbo": "391205", "tipo_renda": "CLT"},
    "Operador de empilhadeira": {"cbo": "782220", "tipo_renda": "CLT"},
    "Operador de máquinas": {"cbo": "862150", "tipo_renda": "CLT"},
    "Embalador": {"cbo": "784105", "tipo_renda": "CLT"},
    "Eletricista de manutenção": {"cbo": "951105", "tipo_renda": "CLT"},
    "Soldador": {"cbo": "724315", "tipo_renda": "CLT"},
    "Caldeireiro": {"cbo": "724410", "tipo_renda": "CLT"},
    "Prensista": {"cbo": "724515", "tipo_renda": "CLT"},
    # Alimentos: pescados e frigorífico
    "Magarefe": {"cbo": "848520", "tipo_renda": "CLT"},
    "Desossador": {"cbo": "848515", "tipo_renda": "CLT"},
    "Abatedor": {"cbo": "848505", "tipo_renda": "CLT"},
    "Operador de caldeira": {"cbo": "862120", "tipo_renda": "CLT"},
    "Supervisor de produção": {"cbo": "840105", "tipo_renda": "CLT"},
    "Conferente de carga": {"cbo": "414215", "tipo_renda": "CLT"},
    # Campo
    "Trabalhador agropecuário": {"cbo": "621005", "tipo_renda": "CLT"},
    "Tratorista": {"cbo": "641015", "tipo_renda": "CLT"},
    "Gerente de produção agropecuária": {"cbo": "141115", "tipo_renda": "CLT"},
    # Transporte e logística
    "Motorista de caminhão": {"cbo": "782510", "tipo_renda": "CLT"},
    "Motorista de ônibus": {"cbo": "782405", "tipo_renda": "CLT"},
    "Motorista de entregas": {"cbo": "782305", "tipo_renda": "CLT"},
    "Ajudante de motorista": {"cbo": "783225", "tipo_renda": "CLT"},
    "Auxiliar de logística": {"cbo": "414140", "tipo_renda": "CLT"},
    "Analista de logística": {"cbo": "252715", "tipo_renda": "CLT"},
    "Supervisor de logística": {"cbo": "410240", "tipo_renda": "CLT"},
    # Confecção
    "Costureira": {"cbo": "763215", "tipo_renda": "CLT"},
    "Cortador de tecidos": {"cbo": "763110", "tipo_renda": "CLT"},
    "Operadora de acabamento": {"cbo": "763320", "tipo_renda": "CLT"},
    "Vendedor de loja": {"cbo": "521110", "tipo_renda": "CLT"},
    # Hotelaria
    "Recepcionista de hotel": {"cbo": "422120", "tipo_renda": "CLT"},
    "Camareira": {"cbo": "513315", "tipo_renda": "CLT"},
    "Garçom": {"cbo": "513405", "tipo_renda": "CLT"},
    "Cozinheiro": {"cbo": "513205", "tipo_renda": "CLT"},
    "Auxiliar de cozinha": {"cbo": "513505", "tipo_renda": "CLT"},
    "Governanta": {"cbo": "513115", "tipo_renda": "CLT"},
    "Porteiro": {"cbo": "517405", "tipo_renda": "CLT"},
    "Gerente de hotel": {"cbo": "141505", "tipo_renda": "CLT"},
    # Educação
    "Professora de educação infantil": {"cbo": "231105", "tipo_renda": "CLT"},
    "Professor de português": {"cbo": "231335", "tipo_renda": "CLT"},
    "Professor de educação física": {"cbo": "231315", "tipo_renda": "CLT"},
    "Auxiliar de desenvolvimento infantil": {"cbo": "331110", "tipo_renda": "CLT"},
    "Inspetor de alunos": {"cbo": "334105", "tipo_renda": "CLT"},
    "Coordenadora pedagógica": {"cbo": "239405", "tipo_renda": "CLT"},
    # Construção civil
    "Pedreiro": {"cbo": "715210", "tipo_renda": "CLT"},
    "Servente de obras": {"cbo": "717020", "tipo_renda": "CLT"},
    "Armador": {"cbo": "715305", "tipo_renda": "CLT"},
    "Carpinteiro": {"cbo": "715505", "tipo_renda": "CLT"},
    "Pintor de obras": {"cbo": "716610", "tipo_renda": "CLT"},
    "Encanador": {"cbo": "724110", "tipo_renda": "CLT"},
    "Mestre de obras": {"cbo": "710205", "tipo_renda": "CLT"},
    "Engenheiro civil": {"cbo": "214205", "tipo_renda": "CLT"},
    # Tecnologia
    "Analista de desenvolvimento de sistemas": {"cbo": "212405", "tipo_renda": "CLT"},
    "Analista de suporte": {"cbo": "212420", "tipo_renda": "CLT"},
    "Técnico de suporte ao usuário": {"cbo": "317210", "tipo_renda": "CLT"},
    "Designer gráfico": {"cbo": "766155", "tipo_renda": "CLT"},
    # Saúde
    "Técnico de enfermagem": {"cbo": "322205", "tipo_renda": "CLT"},
    "Enfermeiro": {"cbo": "223505", "tipo_renda": "CLT"},
    "Auxiliar de enfermagem": {"cbo": "322230", "tipo_renda": "CLT"},
    "Recepcionista de clínica": {"cbo": "422110", "tipo_renda": "CLT"},
    "Médico clínico": {"cbo": "225125", "tipo_renda": "CLT"},
    "Fisioterapeuta": {"cbo": "223605", "tipo_renda": "CLT"},
    "Técnico em radiologia": {"cbo": "324115", "tipo_renda": "CLT"},
    "Auxiliar de laboratório": {"cbo": "515215", "tipo_renda": "CLT"},
    "Biomédico": {"cbo": "221205", "tipo_renda": "CLT"},
    # Rochas ornamentais
    "Polidor de pedras": {"cbo": "712220", "tipo_renda": "CLT"},
    "Marmorista": {"cbo": "716525", "tipo_renda": "CLT"},
    "Operador de guindaste": {"cbo": "782115", "tipo_renda": "CLT"},
    # Farmácias
    "Balconista de farmácia": {"cbo": "521130", "tipo_renda": "CLT"},
    "Farmacêutico": {"cbo": "223405", "tipo_renda": "CLT"},
    "Operador de caixa": {"cbo": "421125", "tipo_renda": "CLT"},
    "Gerente de loja": {"cbo": "141415", "tipo_renda": "CLT"},
    "Repositor de mercadorias": {"cbo": "521125", "tipo_renda": "CLT"},
    "Auxiliar de manipulação": {"cbo": "515210", "tipo_renda": "CLT"},
    # Atendimento
    "Operador de telemarketing": {"cbo": "422310", "tipo_renda": "CLT"},
    "Supervisor de atendimento": {"cbo": "420135", "tipo_renda": "CLT"},
    # Móveis
    "Marceneiro": {"cbo": "771105", "tipo_renda": "CLT"},
    "Montador de móveis": {"cbo": "774105", "tipo_renda": "CLT"},
    "Serrador de madeira": {"cbo": "773120", "tipo_renda": "CLT"},
    "Torneiro de madeira": {"cbo": "773355", "tipo_renda": "CLT"},
}

# Os cargos de cada setor, com o peso (quantas pessoas de cada 100, mais ou menos). O sócio não está aqui: toda empresa
# tem 1 ou 2 sócios, sorteados à parte (scripts/gerar_base_viva.py)
CARGOS_POR_SETOR = {
    "eletronica": [("Montador de eletrônicos", 40), ("Alimentador de linha de produção", 18),
                   ("Técnico de manutenção eletrônica", 8), ("Inspetor de qualidade", 7),
                   ("Operador de empilhadeira", 5), ("Almoxarife", 4), ("Assistente administrativo", 6),
                   ("Analista de recursos humanos", 2), ("Técnico em segurança do trabalho", 2),
                   ("Faxineiro", 5), ("Gerente administrativo", 1)],
    "pescados": [("Magarefe", 22), ("Embalador", 20), ("Alimentador de linha de produção", 14),
                 ("Operador de caldeira", 4), ("Conferente de carga", 6), ("Motorista de caminhão", 8),
                 ("Supervisor de produção", 3), ("Auxiliar de escritório", 6), ("Faxineiro", 5),
                 ("Assistente administrativo", 4), ("Gerente administrativo", 1)],
    "frigorifico": [("Magarefe", 20), ("Desossador", 18), ("Abatedor", 12), ("Embalador", 14),
                    ("Operador de caldeira", 3), ("Conferente de carga", 5), ("Motorista de caminhão", 7),
                    ("Supervisor de produção", 3), ("Inspetor de qualidade", 4), ("Auxiliar de escritório", 5),
                    ("Técnico em segurança do trabalho", 2), ("Faxineiro", 4), ("Gerente administrativo", 1)],
    "agropecuaria": [("Trabalhador agropecuário", 50), ("Tratorista", 18), ("Motorista de caminhão", 10),
                     ("Auxiliar de escritório", 8), ("Gerente de produção agropecuária", 4)],
    "confeccao": [("Costureira", 45), ("Cortador de tecidos", 10), ("Operadora de acabamento", 12),
                  ("Embalador", 8), ("Inspetor de qualidade", 5), ("Vendedor de loja", 8),
                  ("Auxiliar de escritório", 5), ("Assistente administrativo", 3), ("Gerente administrativo", 1)],
    "logistica": [("Motorista de caminhão", 26), ("Ajudante de motorista", 14), ("Conferente de carga", 12),
                  ("Operador de empilhadeira", 10), ("Auxiliar de logística", 16), ("Analista de logística", 5),
                  ("Supervisor de logística", 3), ("Assistente administrativo", 6), ("Gerente administrativo", 1)],
    "transporte": [("Motorista de ônibus", 40), ("Motorista de caminhão", 16), ("Ajudante de motorista", 10),
                   ("Auxiliar de logística", 8), ("Eletricista de manutenção", 5), ("Assistente administrativo", 8),
                   ("Supervisor de logística", 3), ("Auxiliar de pessoal", 3), ("Gerente administrativo", 1)],
    "hotelaria": [("Camareira", 22), ("Garçom", 16), ("Cozinheiro", 10), ("Auxiliar de cozinha", 12),
                  ("Recepcionista de hotel", 12), ("Governanta", 3), ("Porteiro", 7), ("Faxineiro", 8),
                  ("Auxiliar de escritório", 5), ("Gerente de hotel", 1)],
    "educacao": [("Professora de educação infantil", 30), ("Professor de português", 12),
                 ("Professor de educação física", 8), ("Auxiliar de desenvolvimento infantil", 20),
                 ("Inspetor de alunos", 8), ("Coordenadora pedagógica", 4), ("Recepcionista", 6),
                 ("Faxineiro", 8), ("Cozinheiro", 4)],
    "construcao": [("Pedreiro", 24), ("Servente de obras", 26), ("Armador", 10), ("Carpinteiro", 10),
                   ("Pintor de obras", 7), ("Encanador", 5), ("Mestre de obras", 3), ("Engenheiro civil", 3),
                   ("Almoxarife", 3), ("Técnico em segurança do trabalho", 2), ("Assistente administrativo", 4)],
    "tecnologia": [("Analista de desenvolvimento de sistemas", 45), ("Analista de suporte", 15),
                   ("Técnico de suporte ao usuário", 15), ("Designer gráfico", 6),
                   ("Analista de recursos humanos", 4), ("Assistente administrativo", 8),
                   ("Gerente administrativo", 3)],
    "saude": [("Técnico de enfermagem", 28), ("Enfermeiro", 12), ("Auxiliar de enfermagem", 10),
              ("Recepcionista de clínica", 14), ("Médico clínico", 8), ("Fisioterapeuta", 6),
              ("Técnico em radiologia", 6), ("Auxiliar de laboratório", 6), ("Biomédico", 3), ("Faxineiro", 7)],
    "rochas": [("Polidor de pedras", 26), ("Marmorista", 20), ("Operador de máquinas", 18),
               ("Operador de empilhadeira", 8), ("Operador de guindaste", 5), ("Motorista de caminhão", 8),
               ("Assistente administrativo", 6), ("Técnico em segurança do trabalho", 2)],
    "farmacias": [("Balconista de farmácia", 36), ("Farmacêutico", 14), ("Operador de caixa", 16),
                  ("Repositor de mercadorias", 10), ("Auxiliar de manipulação", 6), ("Gerente de loja", 6),
                  ("Motorista de entregas", 4), ("Auxiliar de escritório", 5)],
    "atendimento": [("Operador de telemarketing", 78), ("Supervisor de atendimento", 7),
                    ("Técnico de suporte ao usuário", 3), ("Analista de recursos humanos", 2),
                    ("Auxiliar de pessoal", 3), ("Assistente administrativo", 4), ("Recepcionista", 2),
                    ("Gerente administrativo", 1)],
    "metalurgia": [("Soldador", 22), ("Caldeireiro", 14), ("Prensista", 16), ("Operador de máquinas", 16),
                   ("Eletricista de manutenção", 6), ("Inspetor de qualidade", 6), ("Almoxarife", 4),
                   ("Operador de empilhadeira", 5), ("Técnico em segurança do trabalho", 2),
                   ("Assistente administrativo", 5), ("Gerente administrativo", 1)],
    "moveis": [("Marceneiro", 24), ("Montador de móveis", 26), ("Serrador de madeira", 12), ("Torneiro de madeira", 8),
               ("Operador de máquinas", 10), ("Embalador", 8), ("Motorista de caminhão", 5),
               ("Assistente administrativo", 6), ("Gerente administrativo", 1)],
}

# ================================ As 17 empresas ================================
# Cada empresa: o cadastro (o que o especialista do banco preenche), o setor dos cargos, o estilo do arquivo que o
# sistema de RH dela gera, o kit de marca e a história dos envios.
# Cada envio: o tipo (INICIAL ou INCLUSAO), a etapa em que ele está hoje ("destino"), quantos dias úteis antes da carga
# ele chegou, quantas pessoas novas traz e o que aconteceu no caminho:
#   - destino CADASTRADO: o banco aprovou (as pessoas estão cadastradas); EM_ANALISE: espera o banco;
#     PENDENTE: tem pendências com a empresa; PRONTO: sem pendência, espera a empresa enviar ao banco;
#     DEVOLVIDO: o banco devolveu com um motivo; NO_ACEITE: espera a empresa conferir as colunas;
#   - "erros": os erros de digitação que vieram no arquivo (nos 4 campos obrigatórios). No CADASTRADO, a empresa
#     corrigiu todos antes de enviar; no PENDENTE, eles continuam lá (são as pendências da tela);
#   - "ja_cadastrados": quantas pessoas já cadastradas vieram de novo no arquivo (ficam de fora, com um aviso);
#   - "pro_labore_alto": o sócio com pró-labore acima da referência (o alerta que a empresa confirmou);
#   - "contas": quantos dias úteis depois da aprovação o banco devolveu o arquivo de contas, e que parte das pessoas
#     já tinha conta nele (sem "contas", o banco ainda não devolveu).
EMPRESAS = [
    {"chave": "jacamim", "nome": "Jacamim Eletrônica da Amazônia Ltda.", "setor": "Indústria",
     "cargos": "eletronica", "municipio": "Manaus", "uf": "AM", "ddd": "92", "prefixo_do_cep": "690",
     "bairros": ["Distrito Industrial", "Cidade Nova", "Japiim", "Flores", "Aleixo", "Parque Dez"],
     "endereco_comercial": "Avenida das Seringueiras, 1850", "unidades": [("MAO-01", "Fábrica Distrito Industrial"),
                                                                        ("MAO-02", "Centro de Distribuição")],
     "filiais": 1, "estilo": "siglas", "contrato_dias_uteis": 66, "acessos_extras": 7,
     "kit": {"escolhido": "proprio", "texto": "Logo com o jacamim em verde-escuro; cores verde-floresta e amarelo; "
                                              "cartazes nos refeitórios e no quadro de avisos da fábrica.",
             "cores": ["#1f5f3b", "#f2b705", "#ffffff"]},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 62, "pessoas": 340,
          "erros": ["cpf_digitado_errado", "admissao_vazia"], "pro_labore_alto": True,
          "contas": {"dias_uteis_depois": 4, "parte": 0.92}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 40, "pessoas": 26, "ja_cadastrados": 3,
          "contas": {"dias_uteis_depois": 5, "parte": 0.88}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 19, "pessoas": 32,
          "contas": {"dias_uteis_depois": 4, "parte": 0.70}},
         {"tipo": "INCLUSAO", "destino": "EM_ANALISE", "dias_uteis": 1, "pessoas": 22},
     ]},
    {"chave": "mare_mansa", "nome": "Maré Mansa Pescados Ltda.", "setor": "Alimentos",
     "cargos": "pescados", "municipio": "Belém", "uf": "PA", "ddd": "91", "prefixo_do_cep": "660",
     "bairros": ["Reduto", "Umarizal", "Marco", "Pedreira", "Guamá", "Telégrafo"],
     "endereco_comercial": "Rodovia do Pescador, 420", "unidades": [("BEL-01", "Entreposto do Porto")],
     "filiais": 0, "estilo": "classico", "contrato_dias_uteis": 60, "acessos_extras": 5,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 57, "pessoas": 150,
          "erros": ["cbo_desconhecido"], "contas": {"dias_uteis_depois": 3, "parte": 0.85}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 30, "pessoas": 18,
          "contas": {"dias_uteis_depois": 6, "parte": 0.80}},
         {"tipo": "INCLUSAO", "destino": "PENDENTE", "dias_uteis": 2, "pessoas": 12,
          "erros": ["cbo_desconhecido", "cpf_digitado_errado", "admissao_vazia"]},
     ]},
    {"chave": "buriti_alto", "nome": "Buriti Alto Agropecuária Ltda.", "setor": "Agronegócio",
     "cargos": "agropecuaria", "municipio": "Palmas", "uf": "TO", "ddd": "63", "prefixo_do_cep": "770",
     "bairros": ["Plano Diretor Norte", "Plano Diretor Sul", "Taquaralto", "Aureny"],
     "endereco_comercial": "Rodovia TO-050, Km 12", "unidades": [("PMW-01", "Fazenda Buriti Alto")],
     "filiais": 0, "estilo": "enxuta", "contrato_dias_uteis": 9, "acessos_extras": 2,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "PENDENTE", "dias_uteis": 4, "pessoas": 22,
          "erros": ["cbo_vazio", "cbo_vazio", "cbo_desconhecido"]},
     ]},
    {"chave": "carnauba_fina", "nome": "Carnaúba Fina Confecções Ltda.", "setor": "Têxtil",
     "cargos": "confeccao", "municipio": "Fortaleza", "uf": "CE", "ddd": "85", "prefixo_do_cep": "600",
     "bairros": ["Montese", "Parangaba", "Messejana", "Aldeota", "Jacarecanga", "Fátima"],
     "endereco_comercial": "Rua das Rendeiras, 715", "unidades": [("FOR-01", "Fábrica Parangaba"),
                                                               ("FOR-02", "Loja Centro")],
     "filiais": 1, "estilo": "planilha", "contrato_dias_uteis": 58, "acessos_extras": 6,
     "kit": {"escolhido": "proprio", "texto": "Logo da carnaúba em traço fino; cores terracota e areia; peças para "
                                              "o mural da fábrica e mensagens curtas para o celular.",
             "cores": ["#b5542c", "#e9d8a6", "#264653"]},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 54, "pessoas": 270,
          "erros": ["cpf_digitado_errado", "cbo_desconhecido", "salario_vazio"],
          "contas": {"dias_uteis_depois": 4, "parte": 0.90}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 26, "pessoas": 24,
          "contas": {"dias_uteis_depois": 5, "parte": 0.75}},
         {"tipo": "INCLUSAO", "destino": "PRONTO", "dias_uteis": 2, "pessoas": 16},
     ]},
    {"chave": "jucara_norte", "nome": "Juçara Norte Logística Ltda.", "setor": "Logística",
     "cargos": "logistica", "municipio": "São Luís", "uf": "MA", "ddd": "98", "prefixo_do_cep": "650",
     "bairros": ["Itaqui", "Anjo da Guarda", "Cohama", "Renascença", "Monte Castelo"],
     "endereco_comercial": "Avenida dos Portuários, 3300", "unidades": [("SLZ-01", "Armazém Itaqui")],
     "filiais": 0, "estilo": "esocial", "contrato_dias_uteis": 40, "acessos_extras": 4,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 36, "pessoas": 84,
          "contas": {"dias_uteis_depois": 4, "parte": 0.85}},
         {"tipo": "INCLUSAO", "destino": "EM_ANALISE", "dias_uteis": 4, "pessoas": 11},
     ]},
    {"chave": "duna_clara", "nome": "Duna Clara Hotelaria Ltda.", "setor": "Turismo e hotelaria",
     "cargos": "hotelaria", "municipio": "Natal", "uf": "RN", "ddd": "84", "prefixo_do_cep": "590",
     "bairros": ["Ponta Negra", "Capim Macio", "Lagoa Nova", "Tirol", "Petrópolis"],
     "endereco_comercial": "Avenida da Orla, 2200", "unidades": [("NAT-01", "Hotel Ponta Negra"),
                                                              ("NAT-02", "Receptivo e Passeios")],
     "filiais": 0, "empresa_do_grupo": True, "estilo": "classico", "contrato_dias_uteis": 42, "acessos_extras": 5,
     "kit": {"escolhido": "proprio", "texto": "Logo com a duna em tons de areia e azul do mar; comunicados no "
                                              "refeitório dos funcionários e no aplicativo de mensagens.",
             "cores": ["#e9c46a", "#1d6fa3", "#fefae0"]},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 38, "pessoas": 124,
          "erros": ["admissao_vazia"], "contas": {"dias_uteis_depois": 5, "parte": 0.80}},
         {"tipo": "INCLUSAO", "destino": "DEVOLVIDO", "dias_uteis": 6, "pessoas": 16},
     ]},
    {"chave": "mangaba_doce", "nome": "Colégio Mangaba Doce Ltda.", "setor": "Educação",
     "cargos": "educacao", "municipio": "João Pessoa", "uf": "PB", "ddd": "83", "prefixo_do_cep": "580",
     "bairros": ["Bancários", "Mangabeira", "Tambaú", "Cabo Branco", "Torre"],
     "endereco_comercial": "Rua das Mangabeiras, 88", "unidades": [("JPA-01", "Colégio Sede")],
     "filiais": 0, "estilo": "enxuta", "contrato_dias_uteis": 7, "acessos_extras": 2,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "EM_ANALISE", "dias_uteis": 2, "pessoas": 24},
     ]},
    {"chave": "pequizeiro", "nome": "Pequizeiro Construções Ltda.", "setor": "Construção civil",
     "cargos": "construcao", "municipio": "Goiânia", "uf": "GO", "ddd": "62", "prefixo_do_cep": "740",
     "bairros": ["Setor Bueno", "Setor Oeste", "Jardim América", "Setor Marista", "Vila Nova", "Setor Pedro Ludovico"],
     "endereco_comercial": "Avenida do Cerrado, 1400", "unidades": [("GYN-01", "Escritório Central"),
                                                                 ("GYN-02", "Obra Residencial Setor Bueno"),
                                                                 ("GYN-03", "Obra Comercial Jardim América")],
     "filiais": 0, "estilo": "descritiva", "contrato_dias_uteis": 55, "acessos_extras": 6,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 50, "pessoas": 215,
          "erros": ["cpf_digitado_errado", "cbo_desconhecido"], "contas": {"dias_uteis_depois": 4, "parte": 0.88}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 22, "pessoas": 30,
          "contas": {"dias_uteis_depois": 5, "parte": 0.70}},
         {"tipo": "INCLUSAO", "destino": "NO_ACEITE", "dias_uteis": 1, "pessoas": 15},
     ]},
    {"chave": "tuiuiu", "nome": "Tuiuiú Transportes Ltda.", "setor": "Transporte",
     "cargos": "transporte", "municipio": "Cuiabá", "uf": "MT", "ddd": "65", "prefixo_do_cep": "780",
     "bairros": ["Porto", "Coxipó", "Centro Norte", "Jardim Imperial", "Boa Esperança"],
     "endereco_comercial": "Avenida das Garças, 980", "unidades": [("CGB-01", "Garagem Coxipó")],
     "filiais": 0, "estilo": "esocial", "contrato_dias_uteis": 38, "acessos_extras": 4,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 34, "pessoas": 138,
          "contas": {"dias_uteis_depois": 4, "parte": 0.85}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 9, "pessoas": 12,
          "contas": {"dias_uteis_depois": 3, "parte": 0.50}},
     ]},
    {"chave": "lobeira", "nome": "Lobeira Sistemas Ltda.", "setor": "Tecnologia",
     "cargos": "tecnologia", "municipio": "Brasília", "uf": "DF", "ddd": "61", "prefixo_do_cep": "700",
     "bairros": ["Asa Norte", "Asa Sul", "Sudoeste", "Guará", "Águas Claras"],
     "endereco_comercial": "Setor Comercial Norte, Quadra 4, Bloco B", "unidades": [("BSB-01", "Escritório Asa Norte")],
     "filiais": 0, "estilo": "planilha", "contrato_dias_uteis": 33, "acessos_extras": 5,
     "kit": {"escolhido": "proprio", "texto": "Logo com o fruto da lobeira em roxo; cores roxo e grafite; "
                                              "comunicados pelo canal interno de mensagens.",
             "cores": ["#5a2a82", "#3d3d3d", "#f4f4f4"]},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 29, "pessoas": 78,
          "erros": ["admissao_vazia"], "contas": {"dias_uteis_depois": 4, "parte": 0.80}},
         {"tipo": "INCLUSAO", "destino": "PENDENTE", "dias_uteis": 2, "pessoas": 7,
          "erros": ["cbo_desconhecido", "cbo_desconhecido"]},
     ]},
    {"chave": "caranda_alto", "nome": "Frigorífico Carandá Alto Ltda.", "setor": "Alimentos",
     "cargos": "frigorifico", "municipio": "Campo Grande", "uf": "MS", "ddd": "67", "prefixo_do_cep": "790",
     "bairros": ["Moreninhas", "Aero Rancho", "Coophavila", "Tiradentes", "Nova Lima", "Guanandi"],
     "endereco_comercial": "Rodovia do Gado, Km 8", "unidades": [("CGR-01", "Planta Industrial"),
                                                              ("CGR-02", "Centro de Distribuição")],
     "filiais": 1, "estilo": "classico", "contrato_dias_uteis": 65, "acessos_extras": 8,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 63, "pessoas": 420,
          "erros": ["cpf_digitado_errado", "cbo_desconhecido", "admissao_vazia"], "pro_labore_alto": True,
          "contas": {"dias_uteis_depois": 4, "parte": 0.93}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 43, "pessoas": 36, "ja_cadastrados": 4,
          "contas": {"dias_uteis_depois": 4, "parte": 0.90}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 23, "pessoas": 34,
          "contas": {"dias_uteis_depois": 5, "parte": 0.80}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 6, "pessoas": 30,
          "contas": {"dias_uteis_depois": 3, "parte": 0.40}},
     ]},
    {"chave": "enseada_serena", "nome": "Clínicas Enseada Serena Ltda.", "setor": "Saúde",
     "cargos": "saude", "municipio": "Rio de Janeiro", "uf": "RJ", "ddd": "21", "prefixo_do_cep": "220",
     "bairros": ["Botafogo", "Tijuca", "Méier", "Copacabana", "Campo Grande", "Barra da Tijuca"],
     "endereco_comercial": "Rua das Enseadas, 640", "unidades": [("RIO-01", "Clínica Botafogo"),
                                                              ("RIO-02", "Clínica Tijuca")],
     "filiais": 1, "estilo": "descritiva", "contrato_dias_uteis": 48, "acessos_extras": 6,
     "kit": {"escolhido": "proprio", "texto": "Logo com a onda em azul-petróleo; cores azul-petróleo e branco; "
                                              "comunicados impressos para as recepções das clínicas.",
             "cores": ["#006d77", "#83c5be", "#ffffff"]},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 45, "pessoas": 190,
          "erros": ["cpf_digitado_errado", "salario_vazio"], "contas": {"dias_uteis_depois": 4, "parte": 0.88}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 16, "pessoas": 22,
          "contas": {"dias_uteis_depois": 4, "parte": 0.68}},
         {"tipo": "INCLUSAO", "destino": "EM_ANALISE", "dias_uteis": 1, "pessoas": 18},
     ]},
    {"chave": "cantaria", "nome": "Cantaria Capixaba Granitos Ltda.", "setor": "Mineração",
     "cargos": "rochas", "municipio": "Cachoeiro de Itapemirim", "uf": "ES", "ddd": "28", "prefixo_do_cep": "293",
     "bairros": ["Aeroporto", "Ferroviários", "Independência", "Santo Antônio", "Coramara"],
     "endereco_comercial": "Rodovia do Mármore, Km 3", "unidades": [("CAC-01", "Serraria e Polimento")],
     "filiais": 0, "estilo": "siglas", "contrato_dias_uteis": 16, "acessos_extras": 3,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 12, "pessoas": 70},
     ]},
    {"chave": "sabia_do_campo", "nome": "Farmácias Sabiá do Campo Ltda.", "setor": "Varejo",
     "cargos": "farmacias", "municipio": "Belo Horizonte", "uf": "MG", "ddd": "31", "prefixo_do_cep": "301",
     "bairros": ["Savassi", "Funcionários", "Pampulha", "Barreiro", "Venda Nova", "Santa Efigênia"],
     "endereco_comercial": "Avenida dos Ipês, 2750", "unidades": [("BHZ-01", "Loja Savassi"), ("BHZ-02", "Loja Pampulha"),
                                                               ("BHZ-03", "Loja Barreiro"),
                                                               ("BHZ-04", "Central de Manipulação")],
     "filiais": 2, "estilo": "planilha", "contrato_dias_uteis": 61, "acessos_extras": 7,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 58, "pessoas": 280,
          "erros": ["cbo_desconhecido", "admissao_vazia"], "contas": {"dias_uteis_depois": 5, "parte": 0.90}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 33, "pessoas": 30, "ja_cadastrados": 2,
          "contas": {"dias_uteis_depois": 4, "parte": 0.85}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 12, "pessoas": 24,
          "contas": {"dias_uteis_depois": 3, "parte": 0.60}},
         {"tipo": "INCLUSAO", "destino": "PENDENTE", "dias_uteis": 1, "pessoas": 16,
          "erros": ["cpf_digitado_errado", "pessoa_repetida", "cbo_desconhecido", "salario_dez_vezes"]},
     ]},
    {"chave": "garoa", "nome": "Garoa Atendimento Ltda.", "setor": "Serviços",
     "cargos": "atendimento", "municipio": "São Paulo", "uf": "SP", "ddd": "11", "prefixo_do_cep": "013",
     "bairros": ["Bela Vista", "Liberdade", "Barra Funda", "Mooca", "Santana", "Butantã", "Tatuapé"],
     "endereco_comercial": "Rua da Garoa Fina, 1100", "unidades": [("SAO-01", "Central Barra Funda"),
                                                                ("SAO-02", "Central Mooca")],
     "filiais": 1, "estilo": "siglas", "contrato_dias_uteis": 64, "acessos_extras": 9,
     "kit": {"escolhido": "proprio", "texto": "Logo com a nuvem em cinza-azulado; cores cinza e laranja; "
                                              "comunicados nas telas das centrais de atendimento.",
             "cores": ["#5c6b7a", "#f28c28", "#ffffff"]},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 61, "pessoas": 470,
          "erros": ["cpf_digitado_errado", "cbo_desconhecido", "admissao_vazia", "salario_vazio"],
          "contas": {"dias_uteis_depois": 4, "parte": 0.91}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 41, "pessoas": 42,
          "contas": {"dias_uteis_depois": 5, "parte": 0.88}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 25, "pessoas": 38,
          "contas": {"dias_uteis_depois": 4, "parte": 0.82}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 10, "pessoas": 30,
          "contas": {"dias_uteis_depois": 3, "parte": 0.55}},
         {"tipo": "INCLUSAO", "destino": "EM_ANALISE", "dias_uteis": 3, "pessoas": 24},
     ]},
    {"chave": "coxilha_forte", "nome": "Metalúrgica Coxilha Forte Ltda.", "setor": "Metalurgia",
     "cargos": "metalurgia", "municipio": "Caxias do Sul", "uf": "RS", "ddd": "54", "prefixo_do_cep": "950",
     "bairros": ["São Pelegrino", "Exposição", "Pio X", "Cinquentenário", "Kayser"],
     "endereco_comercial": "Rua dos Ferreiros, 530", "unidades": [("CXJ-01", "Fábrica de Estruturas")],
     "filiais": 0, "estilo": "descritiva", "contrato_dias_uteis": 44, "acessos_extras": 5,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 40, "pessoas": 250,
          "erros": ["cbo_desconhecido", "cpf_digitado_errado"], "contas": {"dias_uteis_depois": 4, "parte": 0.87}},
         {"tipo": "INCLUSAO", "destino": "CADASTRADO", "dias_uteis": 14, "pessoas": 26,
          "contas": {"dias_uteis_depois": 4, "parte": 0.65}},
     ]},
    {"chave": "imbuia_serena", "nome": "Móveis Imbuia Serena Ltda.", "setor": "Indústria moveleira",
     "cargos": "moveis", "municipio": "São Bento do Sul", "uf": "SC", "ddd": "47", "prefixo_do_cep": "892",
     "bairros": ["Centro", "Serra Alta", "Rio Negro", "Oxford", "Colonial"],
     "endereco_comercial": "Rua dos Marceneiros, 260", "unidades": [("SBS-01", "Fábrica de Móveis")],
     "filiais": 0, "estilo": "esocial", "contrato_dias_uteis": 24, "acessos_extras": 3,
     "kit": {"escolhido": "padrao"},
     "envios": [
         {"tipo": "INICIAL", "destino": "CADASTRADO", "dias_uteis": 20, "pessoas": 108,
          "erros": ["admissao_vazia"], "contas": {"dias_uteis_depois": 5, "parte": 0.70}},
     ]},
]

# O motivo da devolução do banco (o envio DEVOLVIDO): um pedido que a empresa entende e resolve mandando de novo
MOTIVO_DA_DEVOLUCAO = ("Os salários dos garçons vieram sem a média das gorjetas e das comissões. Informe a renda "
                       "bruta mensal (salário fixo mais a média dos últimos 3 meses) e envie de novo.")

# ================================ As pessoas ================================
# Nomes comuns no Brasil, combinados ao acaso: nenhuma combinação é de propósito o nome de alguém
NOMES_FEMININOS = ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena", "Isabela",
                   "Juliana", "Karina", "Larissa", "Mariana", "Natália", "Olívia", "Patrícia", "Rafaela", "Sabrina",
                   "Tatiane", "Vanessa", "Yasmin", "Aline", "Bruna", "Cláudia", "Débora", "Elaine", "Flávia",
                   "Giovana", "Jéssica", "Kelly", "Luana", "Marta", "Nayara", "Priscila", "Renata", "Simone",
                   "Tereza", "Valéria", "Adriana", "Cristiane", "Francisca", "Joana", "Lúcia", "Mônica", "Rosana",
                   "Sandra", "Luciana", "Carolina", "Letícia", "Amanda"]
NOMES_MASCULINOS = ["André", "Bruno", "Carlos", "Diego", "Eduardo", "Felipe", "Gabriel", "Henrique", "Igor",
                    "João", "Kaique", "Leonardo", "Marcelo", "Nicolas", "Otávio", "Paulo", "Rafael", "Samuel",
                    "Thiago", "Vinícius", "Wagner", "Alexandre", "Caio", "Daniel", "Emerson", "Fábio", "Gustavo",
                    "Hugo", "Júlio", "Luciano", "Matheus", "Nelson", "Pedro", "Renato", "Sérgio", "Tiago",
                    "Vitor", "Wellington", "Antônio", "Francisco", "José", "Luiz", "Raimundo", "Roberto", "Marcos",
                    "Ricardo", "Fernando", "Rodrigo", "Lucas", "Jorge"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes",
              "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes", "Vieira",
              "Barbosa", "Rocha", "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques", "Machado",
              "Mendes", "Freitas", "Cardoso", "Ramos", "Gonçalves", "Santana", "Teixeira", "Araújo", "Pinto",
              "Correia", "Cavalcanti", "Moura", "Campos", "Barros", "Monteiro", "Borges", "Batista", "Farias",
              "Castro", "Miranda", "Brito", "Pacheco", "Sales", "Queiroz", "Bezerra", "Leite", "Macedo", "Rezende",
              "Siqueira", "Figueiredo", "Tavares", "Aguiar", "Xavier", "Magalhães", "Assis", "Paiva", "Prado",
              "Coelho", "Guimarães", "Peixoto", "Viana", "Neves"]
# Ruas genéricas (o número e o CEP são sorteados à parte)
RUAS = ["Rua das Acácias", "Rua dos Girassóis", "Rua das Palmeiras", "Rua do Sol Nascente", "Rua das Hortênsias",
        "Rua Três Marias", "Rua do Horizonte", "Rua das Andorinhas", "Avenida das Nações", "Rua da Esperança",
        "Rua dos Pinheiros Altos", "Travessa da Paz", "Rua das Violetas", "Rua do Bosque", "Rua das Orquídeas",
        "Avenida Beira Rio", "Rua da Alvorada", "Rua dos Ipês Amarelos", "Rua das Mangueiras", "Rua do Mirante",
        "Rua das Gaivotas", "Rua do Cruzeiro", "Rua Santa Clara", "Rua São Pedro", "Rua da Liberdade",
        "Rua das Flores do Campo", "Rua dos Cravos", "Avenida Central", "Rua do Comércio", "Rua Nova"]
# Os complementos que aparecem em parte dos endereços
COMPLEMENTOS = ["Apto 101", "Apto 204", "Casa 2", "Bloco B", "Fundos", "Apto 32", "Sala 5", "Casa A"]
# Os provedores de e-mail pessoal: todos terminam em ".example" (nunca são de ninguém)
PROVEDORES_DE_EMAIL = ["correio.example", "caixapostal.example", "meuemail.example"]

# ================================ Os estilos de arquivo ================================
# Cada sistema de RH escreve o arquivo do seu jeito: o formato, o separador, as datas, o dinheiro, o CBO, o sexo e o
# nome de cada coluna. A lista "colunas" diz, na ordem, o cabeçalho e o campo do layout que ele alimenta.
# O CBO aparece de 4 jeitos (regra geral 7 do desenho): "4110-10", "411010", "4110.10" e "4110 10".
ESTILOS_DE_ARQUIVO = {
    # Sistema de folha "clássico": ponto e vírgula, datas DD/MM/AAAA, dinheiro "3.450,00"
    "classico": {
        "formato": "csv", "separador": ";", "codificacao": "utf-8-sig", "data": "dd/mm/aaaa",
        "dinheiro": "brasileiro_com_milhar", "cbo": "com_traco", "sexo": "letra", "vinculo": "sigla",
        "colunas": [("Matrícula", "matricula"), ("Nome Completo", "nome_completo"), ("CPF", "cpf"),
                    ("Data de Nascimento", "data_nascimento"), ("Sexo", "sexo"), ("Estado Civil", "estado_civil"),
                    ("Escolaridade", "escolaridade"), ("Nome da Mãe", "nome_mae"), ("RG", "numero_documento"),
                    ("Órgão Emissor", "orgao_emissor"), ("UF do RG", "uf_emissor"), ("CEP", "cep_residencial"),
                    ("Endereço", "logradouro_residencial"), ("Número", "numero_residencial"),
                    ("Complemento", "complemento_residencial"), ("Bairro", "bairro_residencial"),
                    ("Cidade", "municipio_residencial"), ("UF", "uf_residencial"), ("Celular", "telefone_celular"),
                    ("E-mail Pessoal", "email_pessoal"), ("CNPJ do Empregador", "cnpj_empregador"),
                    ("Código da Unidade", "codigo_unidade"), ("Unidade", "nome_unidade"), ("Cargo", "cargo"),
                    ("CBO", "codigo_cbo"), ("Data de Admissão", "data_admissao"), ("Vínculo", "tipo_renda"),
                    ("Salário Bruto", "valor_renda"), ("Mês de Referência do Salário", "data_referencia_renda"),
                    ("Cidade de Trabalho", "municipio_comercial"), ("UF de Trabalho", "uf_comercial")],
    },
    # Exportação com siglas em maiúsculas: vírgula, datas AAAA-MM-DD, dinheiro "3450.00", CBO sem traço
    "siglas": {
        "formato": "csv", "separador": ",", "codificacao": "utf-8", "data": "aaaa-mm-dd",
        "dinheiro": "ponto_decimal", "cbo": "so_digitos", "sexo": "letra", "vinculo": "sigla",
        "colunas": [("MATRICULA", "matricula"), ("NOME", "nome_completo"), ("NR_CPF", "cpf"),
                    ("DT_NASC", "data_nascimento"), ("SEXO", "sexo"), ("NR_PIS", "nis_pis"), ("DS_CARGO", "cargo"),
                    ("CD_CBO", "codigo_cbo"), ("DT_ADMISSAO", "data_admissao"), ("DT_EFETIVACAO", "data_efetivacao"),
                    ("TP_VINCULO", "tipo_renda"), ("VL_SALARIO", "valor_renda"), ("CNPJ_ESTAB", "cnpj_empregador"),
                    ("CD_UNIDADE", "codigo_unidade"), ("NM_UNIDADE", "nome_unidade"), ("CEP_RES", "cep_residencial"),
                    ("LOGRADOURO_RES", "logradouro_residencial"), ("NUM_RES", "numero_residencial"),
                    ("BAIRRO_RES", "bairro_residencial"), ("CIDADE_RES", "municipio_residencial"),
                    ("UF_RES", "uf_residencial"), ("TEL_CELULAR", "telefone_celular"),
                    ("EMAIL_CORP", "email_corporativo"), ("CEP_TRAB", "cep_comercial"),
                    ("LOGRADOURO_TRAB", "logradouro_comercial"), ("NUM_TRAB", "numero_comercial"),
                    ("BAIRRO_TRAB", "bairro_comercial"), ("CIDADE_TRAB", "municipio_comercial"),
                    ("UF_TRAB", "uf_comercial")],
    },
    # Planilha do Excel montada pelo RH: células de texto, datas DD/MM/AAAA, dinheiro "3450,00", CBO com ponto
    "planilha": {
        "formato": "xlsx", "separador": None, "codificacao": None, "data": "dd/mm/aaaa",
        "dinheiro": "virgula_decimal", "cbo": "com_ponto", "sexo": "por_extenso", "vinculo": "por_extenso",
        "colunas": [("Código do Funcionário", "matricula"), ("Nome do Colaborador", "nome_completo"),
                    ("Documento CPF", "cpf"), ("Nascimento", "data_nascimento"), ("Gênero", "sexo"),
                    ("Estado Civil", "estado_civil"), ("Função", "cargo"), ("Código da Ocupação (CBO)", "codigo_cbo"),
                    ("Data de Entrada", "data_admissao"), ("Regime", "tipo_renda"),
                    ("Remuneração Mensal", "valor_renda"), ("Filial (CNPJ)", "cnpj_empregador"),
                    ("Local de Trabalho", "nome_unidade"), ("Município do Local de Trabalho", "municipio_comercial"),
                    ("Estado do Local de Trabalho", "uf_comercial"), ("Celular", "telefone_celular"),
                    ("E-mail", "email_pessoal"), ("Nacionalidade", "nacionalidade"),
                    ("Naturalidade", "municipio_naturalidade"), ("UF de Naturalidade", "uf_naturalidade")],
    },
    # Exportação no jeito do eSocial: ponto e vírgula, texto no padrão do Windows, nomes de campo do eSocial
    "esocial": {
        "formato": "csv", "separador": ";", "codificacao": "cp1252", "data": "dd/mm/aaaa",
        "dinheiro": "virgula_decimal", "cbo": "so_digitos", "sexo": "letra", "vinculo": "sigla",
        "colunas": [("cpfTrab", "cpf"), ("nmTrab", "nome_completo"), ("sexo", "sexo"), ("dtNascto", "data_nascimento"),
                    ("estCiv", "estado_civil"), ("grauInstr", "escolaridade"), ("nisTrab", "nis_pis"),
                    ("matricula", "matricula"), ("nmCargo", "cargo"), ("codCBO", "codigo_cbo"),
                    ("dtAdm", "data_admissao"), ("tpVinculo", "tipo_renda"), ("vrSalFx", "valor_renda"),
                    ("cnpjEstab", "cnpj_empregador"), ("nmLocal", "nome_unidade"), ("cep", "cep_residencial"),
                    ("dscLograd", "logradouro_residencial"), ("nrLograd", "numero_residencial"),
                    ("bairro", "bairro_residencial"), ("nmCid", "municipio_residencial"), ("uf", "uf_residencial"),
                    ("fonePrinc", "telefone_celular"), ("municipioTrabalho", "municipio_comercial"),
                    ("ufTrabalho", "uf_comercial")],
    },
    # Planilha enxuta das empresas pequenas: só o essencial
    "enxuta": {
        "formato": "csv", "separador": ";", "codificacao": "utf-8", "data": "dd/mm/aaaa",
        "dinheiro": "brasileiro_com_milhar", "cbo": "com_traco", "sexo": "letra", "vinculo": "sigla",
        "colunas": [("Nome", "nome_completo"), ("CPF", "cpf"), ("Nascimento", "data_nascimento"), ("Sexo", "sexo"),
                    ("Cargo", "cargo"), ("CBO", "codigo_cbo"), ("Admissão", "data_admissao"), ("Salário", "valor_renda"),
                    ("Tipo", "tipo_renda"), ("Unidade", "nome_unidade"), ("Cidade", "municipio_comercial"),
                    ("UF", "uf_comercial"), ("Telefone", "telefone_celular")],
    },
    # Cabeçalhos longos e explicados (sistema que exporta "para o banco")
    "descritiva": {
        "formato": "csv", "separador": ";", "codificacao": "utf-8-sig", "data": "dd/mm/aaaa",
        "dinheiro": "brasileiro_com_milhar", "cbo": "com_espaco", "sexo": "letra", "vinculo": "por_extenso",
        "colunas": [("Número de matrícula", "matricula"), ("Nome completo do empregado", "nome_completo"),
                    ("Número do CPF", "cpf"), ("Data de nascimento", "data_nascimento"), ("Sexo (F/M)", "sexo"),
                    ("Estado civil", "estado_civil"), ("Grau de instrução", "escolaridade"),
                    ("Nome da mãe", "nome_mae"), ("Número do PIS", "nis_pis"), ("Cargo ocupado", "cargo"),
                    ("Código Brasileiro de Ocupação", "codigo_cbo"), ("Data de admissão na empresa", "data_admissao"),
                    ("Data de efetivação", "data_efetivacao"), ("Tipo de contrato", "tipo_renda"),
                    ("Salário bruto mensal (R$)", "valor_renda"), ("CNPJ do estabelecimento", "cnpj_empregador"),
                    ("CNPJ do grupo", "cnpj_grupo"), ("Código da unidade", "codigo_unidade"),
                    ("Nome da unidade", "nome_unidade"), ("CEP residencial", "cep_residencial"),
                    ("Logradouro", "logradouro_residencial"), ("Número", "numero_residencial"),
                    ("Complemento", "complemento_residencial"), ("Bairro", "bairro_residencial"),
                    ("Município", "municipio_residencial"), ("UF", "uf_residencial"),
                    ("Telefone residencial", "telefone_residencial"), ("Telefone celular", "telefone_celular"),
                    ("E-mail corporativo", "email_corporativo"), ("CEP do trabalho", "cep_comercial"),
                    ("Endereço do trabalho", "logradouro_comercial"), ("Número do trabalho", "numero_comercial"),
                    ("Bairro do trabalho", "bairro_comercial"), ("Município do trabalho", "municipio_comercial"),
                    ("UF do trabalho", "uf_comercial")],
    },
}

# ================================ As conversas com o banco ================================
# As mensagens do balão "Posso ajudar?" (conversa entre pessoas: nenhuma IA responde). Cada conversa diz de que
# empresa é, se o banco já marcou como resolvida e as mensagens (quantos dias úteis antes da carga, a hora, quem
# escreveu, a tela de onde a empresa escreveu e o texto)
CONVERSAS = [
    {"empresa": "mare_mansa", "resolvida": False, "mensagens": [
        (2, "15:12", "EMPRESA", "Pendências", "Boa tarde! No arquivo de admitidos deste mês, o sistema diz que o código "
                                              "CBO de uma pessoa não existe. Onde conferimos esse código?"),
        (2, "16:40", "BANCO", "", "Boa tarde! O CBO tem 6 dígitos e está no contrato de trabalho e no eSocial de cada "
                                  "pessoa (ex.: 8485-20). A contabilidade de vocês também tem essa informação."),
    ]},
    {"empresa": "jucara_norte", "resolvida": False, "mensagens": [
        (3, "15:05", "EMPRESA", "Acompanhar cadastros", "Enviamos o arquivo de inclusão ontem cedo. Tem previsão "
                                                         "para a aprovação? Os motoristas novos começam na segunda."),
    ]},
    {"empresa": "duna_clara", "resolvida": False, "mensagens": [
        (5, "09:30", "EMPRESA", "Acompanhar cadastros", "Recebemos a devolução do arquivo. Os garçons têm salário fixo "
                                                        "e comissão: mandamos só o fixo. Precisa mesmo da média?"),
        (5, "10:55", "BANCO", "", "Precisa, sim: a renda bruta mensal é o fixo mais a média das comissões e gorjetas "
                                  "dos últimos 3 meses. Assim a conta e o crédito ficam do tamanho certo."),
        (4, "14:20", "EMPRESA", "Acompanhar cadastros", "Entendido. Vamos ajustar com a contabilidade e enviar de "
                                                        "novo esta semana."),
    ]},
    {"empresa": "caranda_alto", "resolvida": True, "mensagens": [
        (61, "08:50", "EMPRESA", "Acompanhar cadastros", "Bom dia. Quando as contas dos funcionários ficam "
                                                         "disponíveis para o pagamento da folha?"),
        (61, "09:35", "BANCO", "", "Bom dia! Depois da aprovação do cadastro, o banco abre as contas em alguns dias "
                                   "úteis. A agência e o número de cada conta aparecem na lista de funcionários."),
        (61, "09:41", "EMPRESA", "Acompanhar cadastros", "Perfeito, obrigado!"),
    ]},
    {"empresa": "garoa", "resolvida": True, "mensagens": [
        (39, "16:10", "EMPRESA", "Cadastrar funcionários", "Abrimos uma central nova na Mooca. Os funcionários dela "
                                                           "vão no mesmo arquivo de inclusão?"),
        (38, "09:05", "BANCO", "", "Podem ir no mesmo arquivo, sim. Informem a unidade de trabalho de cada pessoa "
                                   "(código e nome da unidade), como vocês já fazem."),
    ]},
    {"empresa": "enseada_serena", "resolvida": True, "mensagens": [
        (44, "11:25", "EMPRESA", "Cadastrar funcionários", "Uma das sócias também atende na clínica. Ela entra como "
                                                           "pró-labore ou como CLT?"),
        (44, "13:02", "BANCO", "", "Como pró-labore, se ela é sócia e recebe como sócia. O tipo de renda "
                                   "\"pró-labore\" já existe no arquivo."),
    ]},
    {"empresa": "carnauba_fina", "resolvida": True, "mensagens": [
        (2, "17:15", "EMPRESA", "Acompanhar cadastros", "O arquivo com as 16 contratações do mês ficou sem "
                                                        "pendências. Podemos enviar ao banco?"),
        (1, "08:40", "BANCO", "", "Podem, sim. É só clicar em \"Enviar ao banco\" no envio. Avaliamos em até 1 dia "
                                  "útil."),
    ]},
    {"empresa": "buriti_alto", "resolvida": False, "mensagens": [
        (3, "07:55", "EMPRESA", "Pendências", "Não sabemos o CBO de dois tratoristas contratados por empreitada. "
                                              "Podemos mandar sem?"),
    ]},
]
