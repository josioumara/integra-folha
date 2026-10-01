/*
  conferir.js — a CONFERÊNCIA da lista, última etapa da tela "Cadastrar funcionários".

  Para que serve: depois que a IA lê o envio, a pessoa do RH vê a lista inteira, do jeito que vai para o
  banco, antes de enviar. É a validação humana final: se a IA errou em algo, é aqui que se corrige.
    - Cada coluna mostra o campo do banco, o nome que ela tinha no arquivo e a confiança da IA, e tem um "i"
      com a explicação do campo (o que é, como deve vir, o que não confundir, exemplo), vinda do parâmetro do layout.
    - O que a IA mudou em relação ao arquivo aparece em azul; passando o mouse, vê-se o valor original.
    - Qualquer valor pode ser corrigido com um clique; o que a pessoa corrige fica verde.
    - Quem ainda tem ajuste pendente aparece em laranja e não vai no envio (fica guardado até corrigir).
    - Filtros "Todos", "Só o que a IA mudou" e "Só com ajuste", e busca por nome.
    - O envio só é liberado depois que a pessoa marca "Conferi a lista".
    - "Descartar esta leitura" (arquivo errado) pede confirmação dizendo o que se perde e volta ao começo.
      Não existe "fazer outro envio" aqui: mais funcionários são outro envio, feito depois deste.

  Dados: 100% fictícios, os mesmos do roteiro em cadastrar.js (inclusão da Aurora com 28 linhas, ou o print
  de conversa com 3 funcionários). No sistema real, esta lista viria da padronização (Normalizador) do envio.
  Este arquivo é carregado depois do cadastrar.js e usa dele a variável envio_atual.
*/

// ===== Dados da conferência: cenário "tabela" (inclusão da Aurora, 28 linhas) =====

// As colunas, na ordem em que aparecem: campo do banco, nome amigável, nome no arquivo e confiança da IA.
const COLUNAS_DA_TABELA = [
  { campo: "matricula", rotulo: "Matrícula", no_arquivo: "ID Funcionário", confianca: "alta" },
  { campo: "nome_completo", rotulo: "Nome", no_arquivo: "Funcionário", confianca: "alta" },
  { campo: "cpf", rotulo: "CPF", no_arquivo: "Nº CPF", confianca: "alta" },
  { campo: "data_nascimento", rotulo: "Nascimento", no_arquivo: "Data Nasc", confianca: "alta" },
  { campo: "cargo", rotulo: "Cargo", no_arquivo: "Função", confianca: "alta" },
  { campo: "data_admissao", rotulo: "Admissão", no_arquivo: "Início", confianca: "media" },
  { campo: "data_efetivacao", rotulo: "Efetivação", no_arquivo: "Fim da Experiência", confianca: "media" },
  { campo: "valor_renda", rotulo: "Salário", no_arquivo: "Remuneração", confianca: "alta" },
  { campo: "tipo_renda", rotulo: "Tipo de renda", no_arquivo: "Tipo de Vínculo", confianca: "alta" },
  { campo: "data_referencia_renda", rotulo: "Referência do salário", no_arquivo: "Referência Salarial", confianca: "alta" },
  { campo: "telefone_celular", rotulo: "Celular", no_arquivo: "Móvel", confianca: "alta" },
  { campo: "email_corporativo", rotulo: "E-mail corporativo", no_arquivo: "E-mail Trabalho", confianca: "alta" },
  { campo: "cep_residencial", rotulo: "CEP", no_arquivo: "Código Postal", confianca: "alta" },
  { campo: "logradouro_residencial", rotulo: "Endereço", no_arquivo: "Endereço Residencial", confianca: "alta" },
  { campo: "numero_residencial", rotulo: "Número", no_arquivo: "Número", confianca: "alta" },
  { campo: "bairro_residencial", rotulo: "Bairro", no_arquivo: "Bairro Casa", confianca: "alta" },
  { campo: "municipio_residencial", rotulo: "Cidade", no_arquivo: "Cidade Residência", confianca: "alta" },
  { campo: "uf_residencial", rotulo: "UF", no_arquivo: "Sigla UF", confianca: "alta" },
  { campo: "cnpj_empregador", rotulo: "CNPJ", no_arquivo: "Nº CNPJ", confianca: "alta" },
  { campo: "codigo_unidade", rotulo: "Código da unidade", no_arquivo: "Centro de Custo", confianca: "alta" },
  { campo: "nome_unidade", rotulo: "Unidade", no_arquivo: "Local de Trabalho", confianca: "alta" },
  { campo: "cep_comercial", rotulo: "CEP da unidade", no_arquivo: "CEP Com.", confianca: "alta" },
  { campo: "municipio_comercial", rotulo: "Cidade da unidade", no_arquivo: "Cidade da Unidade", confianca: "alta" },
  { campo: "uf_comercial", rotulo: "UF da unidade", no_arquivo: "Estado Empresa", confianca: "alta" },
];

// Os dados que se repetem por unidade (vêm do cadastro da empresa, iguais para todo mundo da unidade).
const DADOS_DAS_UNIDADES = {
  "AUR-01": { nome_unidade: "Fábrica Campinas", cep_comercial: "13069-000", municipio_comercial: "Campinas", cidade: "Campinas" },
  "AUR-02": { nome_unidade: "Centro de Distribuição Jundiaí", cep_comercial: "13214-206", municipio_comercial: "Jundiaí", cidade: "Jundiaí" },
  "AUR-03": { nome_unidade: "Escritório São Paulo", cep_comercial: "04578-910", municipio_comercial: "São Paulo", cidade: "São Paulo" },
};

// As 28 pessoas do envio, na ordem do arquivo (a posição na lista é a linha do arquivo).
const PESSOAS_DA_INCLUSAO = [
  { nome: "Otávio Cardoso Lopes", cpf: "246.813.579-54", nascimento: "07/12/2003", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2450, celular: "(19) 99888-1020", endereco: "Rua Barão de Jaguara", numero: "1210", bairro: "Jardim do Lago", cep: "13050-120", unidade: "AUR-01" },
  { nome: "Patrícia Azevedo Reis", cpf: "813.579.246-65", nascimento: "15/01/1994", cargo: "Analista de logística", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3250, celular: "(11) 98345-6612", endereco: "Rua do Retiro", numero: "455", bairro: "Engordadouro", cep: "13209-000", unidade: "AUR-02" },
  { nome: "Rodrigo Tavares Silva", cpf: "579.246.813-76", nascimento: "23/09/1986", cargo: "Motorista", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3420, celular: "(11) 99654-7743", endereco: "Av. Jundiaí", numero: "88", bairro: "Ponte São João", cep: "13218-000", unidade: "AUR-02" },
  { nome: "Sofia Mendes Araújo", cpf: "135.792.468-87", nascimento: "05/03/1998", cargo: "Assistente administrativa", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3050, celular: "(11) 97123-9087", endereco: "Rua Domingos de Morais", numero: "2100", bairro: "Saúde", cep: "04036-000", unidade: "AUR-03" },
  { nome: "Carlos Eduardo Nunes", cpf: "792.468.135-98", nascimento: "16/08/1996", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 48000, celular: "(19) 98821-5566", endereco: "Rua Ferreira Penteado", numero: "730", bairro: "Vila Teixeira", cep: "13010-040", unidade: "AUR-01" },
  { nome: "Lucas Ferreira Prado", cpf: "357.918.246-12", nascimento: "19/04/2000", cargo: "Operador de máquinas", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3180, celular: "(19) 99102-3344", endereco: "Rua Carlos Gomes", numero: "54", bairro: "Botafogo", cep: "13020-130", unidade: "AUR-01" },
  { nome: "Rafael Moreira Lima", cpf: "***.482.917-**", nascimento: "10/10/1992", cargo: "Operador de máquinas", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3180, celular: "(19) 99333-4455", endereco: "Rua Delfino Cintra", numero: "310", bairro: "Bonfim", cep: "13070-720", unidade: "AUR-01" },
  { nome: "Mariana Alves de Souza", cpf: "468.257.913-20", nascimento: "27/06/1997", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2450, celular: "(19) 98761-2090", endereco: "Rua Luzitana", numero: "1020", bairro: "Centro", cep: "13015-121", unidade: "AUR-01" },
  { nome: "Thiago Santos Ribeiro", cpf: "912.648.357-31", nascimento: "02/02/1991", cargo: "Técnico de manutenção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 4380, celular: "(19) 99541-7788", endereco: "Av. Brasil", numero: "1550", bairro: "Jardim Guanabara", cep: "13073-148", unidade: "AUR-01" },
  { nome: "Beatriz Lopes Martins", cpf: "624.813.579-42", nascimento: "30/09/1995", cargo: "Conferente", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2780, celular: "(11) 98870-3321", endereco: "Rua Barão de Jundiaí", numero: "900", bairro: "Centro", cep: "13201-010", unidade: "AUR-02" },
  { nome: "Gustavo Henrique Rocha", cpf: "138.264.957-53", nascimento: "11/11/1989", cargo: "Conferente", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2780, celular: "(11) 99870-4411", endereco: "Rua Rangel Pestana", numero: "140", bairro: "Vila Arens", cep: "13202-000", unidade: "AUR-02" },
  { nome: "Vanessa Cristina Dias", cpf: "759.136.284-64", nascimento: "24/12/1993", cargo: "Analista de RH", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 6200, celular: "(11) 99432-1188", endereco: "Rua Vergueiro", numero: "3185", bairro: "Vila Mariana", cep: "04101-300", unidade: "AUR-03" },
  { nome: "Felipe Cunha Barros", cpf: "284.957.613-75", nascimento: "08/08/2001", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2980, celular: "(19) 98110-5623", endereco: "Rua José Paulino", numero: "620", bairro: "Centro", cep: "13013-001", unidade: "AUR-01" },
  { nome: "Aline Rodrigues Pinto", cpf: "591.372.846-86", nascimento: "13/05/1999", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2450, celular: "(19) 99011-8877", endereco: "Rua Maria Monteiro", numero: "77", bairro: "Cambuí", cep: "13025-151", unidade: "AUR-01" },
  { nome: "Juliana Castro Pires", cpf: "468.135.792-09", nascimento: "01/02/1995", cargo: "Técnica de qualidade", admissao: "12/11/2026", efetivacao: "10/02/2027", salario: 4120, celular: "(19) 98444-5566", endereco: "Rua Proença", numero: "215", bairro: "Guanabara", cep: "13073-000", unidade: "AUR-01" },
  { nome: "Eduardo Martins Faria", cpf: "846.291.537-97", nascimento: "21/07/1987", cargo: "Líder de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 5350, celular: "(19) 99200-6655", endereco: "Rua Sampainho", numero: "402", bairro: "Cambuí", cep: "13025-300", unidade: "AUR-01" },
  { nome: "Camila Souza Moreira", cpf: "173.846.925-08", nascimento: "09/10/1998", cargo: "Assistente administrativa", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3050, celular: "(11) 97555-3210", endereco: "Rua Tutóia", numero: "1100", bairro: "Paraíso", cep: "04007-005", unidade: "AUR-03" },
  { nome: "Rafaela Nogueira Costa", cpf: "362.715.948-19", nascimento: "17/03/2002", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2450, celular: "(19) 98322-7700", endereco: "Rua Uruguai", numero: "36", bairro: "Taquaral", cep: "13076-000", unidade: "AUR-01" },
  { nome: "João Victor Silva", cpf: "695.183.472-20", nascimento: "25/12/1996", cargo: "Motorista", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3420, celular: "(11) 98111-0922", endereco: "Av. Nove de Julho", numero: "1500", bairro: "Anhangabaú", cep: "13208-056", unidade: "AUR-02" },
  { nome: "Larissa Teixeira Lima", cpf: "437.629.815-31", nascimento: "04/04/2001", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2450, celular: "(19) 99870-1188", endereco: "Rua Olavo Bilac", numero: "81", bairro: "Cambuí", cep: "13024-110", unidade: "AUR-01" },
  { nome: "Bruno Almeida Santos", cpf: "518.943.276-42", nascimento: "12/06/1994", cargo: "Técnico de qualidade", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 4120, celular: "(19) 98233-4567", endereco: "Rua Coronel Quirino", numero: "1330", bairro: "Cambuí", cep: "13025-002", unidade: "AUR-01" },
  { nome: "Natália Freitas Gomes", cpf: "284.617.953-53", nascimento: "28/01/1993", cargo: "Analista de logística", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 5900, celular: "(11) 99887-6543", endereco: "Rua Petronilha Antunes", numero: "222", bairro: "Eloy Chaves", cep: "13212-000", unidade: "AUR-02" },
  { nome: "Pedro Henrique Castro", cpf: "963.428.715-64", nascimento: "03/03/1990", cargo: "Operador de máquinas", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3180, celular: "(19) 99456-3210", endereco: "Rua Irmã Serafina", numero: "860", bairro: "Centro", cep: "13015-201", unidade: "AUR-01" },
  { nome: "Isadora Campos Reis", cpf: "731.594.286-75", nascimento: "16/09/1999", cargo: "Assistente administrativa", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3050, celular: "(11) 97766-5544", endereco: "Rua Estado de Israel", numero: "520", bairro: "Vila Clementino", cep: "04022-001", unidade: "AUR-03" },
  { nome: "André Luiz Pereira", cpf: "147.852.963-86", nascimento: "20/11/1985", cargo: "Motorista", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3420, celular: "(11) 98321-9087", endereco: "Rua Zacarias de Góes", numero: "305", bairro: "Vila Rio Branco", cep: "13215-000", unidade: "AUR-02" },
  { nome: "Letícia Barbosa Nunes", cpf: "852.369.741-97", nascimento: "30/07/1999", cargo: "Auxiliar de produção", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 2450, celular: "(19) 98109-2233", endereco: "Rua Dr. Quirino", numero: "1488", bairro: "Centro", cep: "13015-082", unidade: "AUR-01" },
  { nome: "Marcos Vinícius Rocha", cpf: "369.258.147-08", nascimento: "14/02/1992", cargo: "Operador de máquinas", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 3180, celular: "(19) 99300-4455", endereco: "Rua Paula Bueno", numero: "95", bairro: "Taquaral", cep: "13076-110", unidade: "AUR-01" },
  { nome: "Daniela Moura Lopes", cpf: "741.963.852-19", nascimento: "06/05/1997", cargo: "Técnica de qualidade", admissao: "22/09/2026", efetivacao: "21/12/2026", salario: 4120, celular: "(19) 98877-0101", endereco: "Rua Hermantino Coelho", numero: "400", bairro: "Mansões Santo Antônio", cep: "13087-500", unidade: "AUR-01" },
];

// O que a IA mudou em relação ao arquivo: linha → { campo: valor como estava no arquivo }. São 12 valores.
const ALTERACOES_DA_IA_NA_TABELA = {
  2: { valor_renda: "3250" },
  4: { data_nascimento: "5/3/98" },
  5: { telefone_celular: "19988215566" },
  8: { nome_completo: "MARIANA ALVES DE SOUZA" },
  10: { cep_residencial: "13201010" },
  11: { uf_residencial: "sp" },
  13: { valor_renda: "R$2.980" },
  16: { data_admissao: "22-09-2026" },
  19: { email_corporativo: "Joao.Silva@Aurora.com.br " },
  21: { valor_renda: "4.120" },
  24: { telefone_celular: "(11)97766-5544" },
  26: { data_nascimento: "1999-07-30" },
};

// As linhas que ainda precisam de ajuste (as mesmas dos cartões do resultado) e o campo com problema.
const AJUSTES_DA_TABELA = {
  7: { campo: "cpf", nome: "Rafael Moreira Lima", sugestao: "" },
  15: { campo: "data_admissao", nome: "Juliana Castro Pires", sugestao: "12/09/2026" },
};

// ===== Dados da conferência: cenário "conversa" (3 funcionários) =====

// Na conversa não há colunas no arquivo: "no_arquivo" diz de onde a IA tirou o dado.
const COLUNAS_DA_CONVERSA = [
  { campo: "nome_completo", rotulo: "Nome", no_arquivo: "nome citado", confianca: "alta" },
  { campo: "cpf", rotulo: "CPF", no_arquivo: "CPF citado", confianca: "alta" },
  { campo: "data_nascimento", rotulo: "Nascimento", no_arquivo: "\"nasceu em\"", confianca: "alta" },
  { campo: "cargo", rotulo: "Cargo", no_arquivo: "cargo citado", confianca: "alta" },
  { campo: "data_admissao", rotulo: "Admissão", no_arquivo: "\"começa segunda\"", confianca: "media" },
  { campo: "valor_renda", rotulo: "Salário", no_arquivo: "\"salário de\"", confianca: "alta" },
  { campo: "nome_unidade", rotulo: "Unidade", no_arquivo: "\"na unidade de\"", confianca: "alta" },
];

// As 3 pessoas da conversa, já montadas pela IA.
const PESSOAS_DA_CONVERSA = [
  { nome_completo: "Carla Mendes Souza", cpf: "318.472.965-40", data_nascimento: "14/03/1998", cargo: "Auxiliar de produção", data_admissao: "28/09/2026", valor_renda: "R$ 2.400,00", nome_unidade: "Fábrica Campinas" },
  { nome_completo: "Diego Ramos Teixeira", cpf: "205.639.184-11", data_nascimento: "02/05/1995", cargo: "Auxiliar de produção", data_admissao: "28/09/2026", valor_renda: "R$ 2.400,00", nome_unidade: "Fábrica Campinas" },
  { nome_completo: "Paula Nogueira Lins", cpf: "", data_nascimento: "11/11/1990", cargo: "Analista de qualidade", data_admissao: "28/09/2026", valor_renda: "R$ 4.100,00", nome_unidade: "Fábrica Campinas" },
];

// O que a IA interpretou a partir do texto solto da conversa (o "valor original" é o trecho da mensagem).
const ALTERACOES_DA_IA_NA_CONVERSA = {
  1: { data_admissao: "começa segunda, dia 28", valor_renda: "salário de 2.400", nome_unidade: "na unidade de Campinas" },
  2: { cargo: "mesmo cargo da Carla", data_admissao: "começa na mesma segunda", valor_renda: "mesmo salário" },
  3: { data_admissao: "também dia 28" },
};

// O dado que faltou na conversa.
const AJUSTES_DA_CONVERSA = {
  3: { campo: "cpf", nome: "Paula Nogueira Lins", sugestao: "" },
};

// ===== Ajuda de cada campo (o "i" do cabeçalho) =====

/*
  O que aparece no balão do "i" de cada coluna. Vem do PARÂMETRO DO LAYOUT, que o banco cadastra na tela de
  Parâmetros (data/contratos/layout_v1.csv na ferramenta): descrição, regra, "não confundir com", exemplo e se é
  obrigatório. Aqui os textos já estão reescritos em linguagem simples, para o RH. Na ferramenta real, esse texto
  simples seria um campo novo do parâmetro ("explicação para a empresa"); sem ele, o balão mostraria a descrição
  técnica do banco.
*/
const AJUDA_DOS_CAMPOS = {
  matricula: { o_que_e: "O número que identifica o funcionário dentro da sua empresa.", como_preencher: "Como está no seu sistema de RH, com os zeros à esquerda. Não pode repetir.", nao_confundir: "CPF e código da unidade.", exemplo: "001528", obrigatorio: true },
  nome_completo: { o_que_e: "O nome completo do funcionário.", como_preencher: "Sem abreviar, como no documento.", nao_confundir: "Nome da mãe e nome da unidade.", exemplo: "Otávio Cardoso Lopes", obrigatorio: true },
  cpf: { o_que_e: "O CPF do funcionário.", como_preencher: "Os 11 números. O último par de números confere os outros, por isso um dígito trocado é percebido.", nao_confundir: "CNPJ, PIS/NIS e número do RG.", exemplo: "246.813.579-54", obrigatorio: true },
  data_nascimento: { o_que_e: "A data de nascimento do funcionário.", como_preencher: "Uma data no passado (dia/mês/ano).", nao_confundir: "Data de admissão e data de emissão do documento.", exemplo: "07/12/2003", obrigatorio: true },
  cargo: { o_que_e: "O cargo ou a função do funcionário.", como_preencher: "Como está no seu cadastro. Serve para comparar salários de pessoas do mesmo cargo.", nao_confundir: "Escolaridade e unidade.", exemplo: "Auxiliar de produção", obrigatorio: true },
  data_admissao: { o_que_e: "A data em que o funcionário foi contratado.", como_preencher: "Uma data que já passou ou é hoje: não pode estar no futuro.", nao_confundir: "Data de efetivação (fim da experiência) e data de nascimento.", exemplo: "22/09/2026", obrigatorio: true },
  data_efetivacao: { o_que_e: "A data em que o funcionário foi efetivado, ou seja, o fim do período de experiência.", como_preencher: "Igual ou depois da data de admissão. Se ainda não houver, pode ficar em branco.", nao_confundir: "Data de admissão.", exemplo: "21/12/2026", obrigatorio: false },
  valor_renda: { o_que_e: "O salário bruto mensal, antes dos descontos (ou o pró-labore, para sócios).", como_preencher: "Em reais, com centavos.", nao_confundir: "Salário líquido, valor depositado, PLR e benefícios (vale-refeição, por exemplo).", exemplo: "R$ 2.450,00", obrigatorio: true },
  tipo_renda: { o_que_e: "O tipo de vínculo que gera o salário.", como_preencher: "Salário mensal (carteira assinada, CLT) ou pró-labore (sócios).", nao_confundir: "O valor do salário.", exemplo: "Salário mensal", obrigatorio: true },
  data_referencia_renda: { o_que_e: "O mês a que o salário informado se refere.", como_preencher: "Uma data válida; normalmente o primeiro dia do mês.", nao_confundir: "Data de admissão.", exemplo: "01/09/2026", obrigatorio: true },
  telefone_celular: { o_que_e: "O celular do funcionário.", como_preencher: "DDD e o número com 9 dígitos.", nao_confundir: "Telefone fixo.", exemplo: "(19) 99888-1020", obrigatorio: false },
  email_corporativo: { o_que_e: "O e-mail de trabalho do funcionário.", como_preencher: "Um endereço de e-mail válido.", nao_confundir: "E-mail pessoal.", exemplo: "otavio.lopes@aurora.com.br", obrigatorio: false },
  cep_residencial: { o_que_e: "O CEP da casa do funcionário.", como_preencher: "Os 8 números do CEP.", nao_confundir: "CEP da unidade onde ele trabalha.", exemplo: "13050-120", obrigatorio: true },
  logradouro_residencial: { o_que_e: "A rua, avenida etc. da casa do funcionário.", como_preencher: "Sem o número (ele tem coluna própria).", nao_confundir: "Endereço da unidade de trabalho.", exemplo: "Rua Barão de Jaguara", obrigatorio: true },
  numero_residencial: { o_que_e: "O número da casa do funcionário.", como_preencher: "O número, ou S/N quando não houver.", nao_confundir: "Número do endereço da unidade.", exemplo: "1210", obrigatorio: true },
  bairro_residencial: { o_que_e: "O bairro onde o funcionário mora.", como_preencher: "O nome do bairro.", nao_confundir: "Bairro da unidade de trabalho.", exemplo: "Jardim do Lago", obrigatorio: true },
  municipio_residencial: { o_que_e: "A cidade onde o funcionário mora.", como_preencher: "O nome da cidade.", nao_confundir: "Cidade da unidade de trabalho e cidade onde nasceu.", exemplo: "Campinas", obrigatorio: true },
  uf_residencial: { o_que_e: "O estado onde o funcionário mora.", como_preencher: "A sigla com 2 letras.", nao_confundir: "Estado da unidade de trabalho e estado onde nasceu.", exemplo: "SP", obrigatorio: true },
  cnpj_empregador: { o_que_e: "O CNPJ da sua empresa, a empregadora.", como_preencher: "Os 14 números do CNPJ.", nao_confundir: "CPF do funcionário e código da unidade.", exemplo: "12.345.678/0001-95", obrigatorio: true },
  codigo_unidade: { o_que_e: "O código da unidade (filial) onde o funcionário trabalha.", como_preencher: "Como está no seu cadastro de unidades.", nao_confundir: "Matrícula e CNPJ.", exemplo: "AUR-01", obrigatorio: true },
  nome_unidade: { o_que_e: "O nome da unidade (filial) onde o funcionário trabalha.", como_preencher: "Como a unidade é conhecida na empresa.", nao_confundir: "Nome do funcionário e departamento interno.", exemplo: "Fábrica Campinas", obrigatorio: true },
  cep_comercial: { o_que_e: "O CEP da unidade onde o funcionário trabalha.", como_preencher: "Os 8 números do CEP.", nao_confundir: "CEP da casa do funcionário.", exemplo: "13069-000", obrigatorio: true },
  municipio_comercial: { o_que_e: "A cidade da unidade onde o funcionário trabalha.", como_preencher: "O nome da cidade.", nao_confundir: "Cidade onde o funcionário mora.", exemplo: "Campinas", obrigatorio: true },
  uf_comercial: { o_que_e: "O estado da unidade onde o funcionário trabalha.", como_preencher: "A sigla com 2 letras.", nao_confundir: "Estado onde o funcionário mora.", exemplo: "SP", obrigatorio: true },
  email_pessoal: { o_que_e: "O e-mail pessoal do funcionário, fora do trabalho.", como_preencher: "Um endereço de e-mail válido. Se não houver, pode ficar em branco.", nao_confundir: "E-mail corporativo (do trabalho).", exemplo: "otavio.lopes@gmail.com", obrigatorio: false },
};

/**
 * Abre o balão de ajuda de um campo, logo abaixo do "i" clicado.
 *
 * Recebe: botao — o "i" clicado (o campo fica em data-campo; o nome amigável, em data-rotulo).
 * Devolve: nada.
 */
function abrir_ajuda_do_campo(botao) {
  const ajuda = AJUDA_DOS_CAMPOS[botao.dataset.campo];
  const balao = document.querySelector("[data-balao-ajuda]");
  // Preenche o balão com os textos do parâmetro (se é obrigatório: pela marca do parâmetro vigente, quando há
  // servidor).
  balao.querySelector("[data-ajuda-titulo]").textContent = botao.dataset.rotulo;
  balao.querySelector("[data-ajuda-obrigatorio]").textContent =
    campo_e_obrigatorio_na_demonstracao(botao.dataset.campo, ajuda) ? "Obrigatório" : "Opcional";
  balao.querySelector("[data-ajuda-o-que-e]").textContent = ajuda.o_que_e;
  balao.querySelector("[data-ajuda-como]").textContent = ajuda.como_preencher;
  balao.querySelector("[data-ajuda-nao-confundir]").textContent = ajuda.nao_confundir;
  balao.querySelector("[data-ajuda-exemplo]").textContent = ajuda.exemplo;
  balao.hidden = false;
  // Posição: logo abaixo do "i", sem passar da borda direita da tela.
  // "fixed" prende o balão à janela, para ele não ser cortado pela caixa da tabela, que rola por dentro.
  const posicao_do_botao = botao.getBoundingClientRect();
  const esquerda_maxima = window.innerWidth - balao.offsetWidth - 16;
  balao.style.top = (posicao_do_botao.bottom + 8) + "px";
  balao.style.left = Math.max(16, Math.min(posicao_do_botao.left - 12, esquerda_maxima)) + "px";
}

/**
 * Fecha o balão de ajuda (se estiver aberto).
 *
 * Recebe: nada. Devolve: nada.
 */
function fechar_ajuda_do_campo() {
  document.querySelector("[data-balao-ajuda]").hidden = true;
}

// ===== Os obrigatórios do parâmetro na demonstração (ADR-143) =====

/**
 * Se um campo é obrigatório na demonstração: pela marca do parâmetro vigente, quando a tela é servida pela aplicação
 * (campos_obrigatorios_do_cadastro, do js/cadastrar_obrigatorios.js); aberta como arquivo, pela ajuda de exemplo.
 *
 * Recebe: campo — o nome técnico; ajuda — a ajuda de exemplo do campo. Devolve: true ou false.
 */
function campo_e_obrigatorio_na_demonstracao(campo, ajuda) {
  if (campos_obrigatorios_do_cadastro === null) {
    return ajuda.obrigatorio;
  }
  return campos_obrigatorios_do_cadastro.includes(campo);
}

/**
 * As colunas que a conferência da demonstração mostra: com a lista dos obrigatórios do parâmetro vigente (a tela
 * servida pela aplicação), só as colunas deles, como na conferência de verdade (a empresa confirma só os
 * obrigatórios); aberta como arquivo, todas as colunas do exemplo.
 *
 * Recebe: colunas — as do cenário. Devolve: a lista de colunas a mostrar.
 * Ex.: com CPF, CBO, renda e admissão obrigatórios, a tabela da Aurora mostra CPF, Admissão e Salário (o exemplo não
 * tem a coluna do CBO).
 */
function colunas_para_conferir(colunas) {
  if (campos_obrigatorios_do_cadastro === null) {
    return colunas;
  }
  const obrigatorias = [];
  for (const coluna of colunas) {
    if (campos_obrigatorios_do_cadastro.includes(coluna.campo)) {
      obrigatorias.push(coluna);
    }
  }
  return obrigatorias;
}

// ===== Estado da conferência (muda durante o uso) =====

// Colunas que entraram depois, por orientação da empresa (js/orientar.js). Cada uma:
// { coluna: {campo, rotulo, no_arquivo, confianca}, valores: {linha: valor}, originais: {linha: texto no arquivo} }
const colunas_adicionadas = [];
// Campos cuja leitura a empresa confirmou (ex.: "Início é mesmo a admissão"): perdem o selo "confira".
const campos_confirmados_pela_empresa = {};

// Qual filtro está ligado: "todos", "alterados" ou "ajuste".
let filtro_da_conferencia = "todos";
// Quantos valores a pessoa corrigiu na conferência (clicando na célula).
let quantidade_corrigida_na_conferencia = 0;

// ===== Montagem das linhas =====

/**
 * Escreve um salário no padrão brasileiro. Ex.: 3250 → "R$ 3.250,00".
 *
 * Recebe: valor — número. Devolve: o texto em reais.
 */
function salario_em_reais(valor) {
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Um e-mail a partir do nome: primeiro e último nome, sem acento, no domínio dado.
 *
 * Recebe: nome — o nome completo; dominio — ex.: "aurora.com.br". Devolve: o e-mail.
 * Exemplo: ("João Victor Silva", "aurora.com.br") → "joao.silva@aurora.com.br".
 */
function email_a_partir_do_nome(nome, dominio) {
  // normalize("NFD") separa a letra do acento; o replace tira os acentos que ficaram soltos.
  const sem_acento = nome.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  // O primeiro e o último pedaço do nome.
  const partes = sem_acento.split(" ");
  return partes[0] + "." + partes[partes.length - 1] + "@" + dominio;
}

/**
 * Transforma uma pessoa do envio numa linha com todos os campos do banco.
 *
 * Recebe: pessoa — um item de PESSOAS_DA_INCLUSAO; numero_da_linha — a linha no arquivo (começa em 1).
 * Devolve: { campo: valor } com os 24 campos da tabela.
 */
function linha_completa(pessoa, numero_da_linha) {
  // Os dados da unidade da pessoa (nome, CEP e cidade da unidade).
  const unidade = DADOS_DAS_UNIDADES[pessoa.unidade];
  return {
    // Matrícula em sequência, a partir da última da Aurora (001527).
    matricula: String(1527 + numero_da_linha).padStart(6, "0"),
    nome_completo: pessoa.nome,
    cpf: pessoa.cpf,
    data_nascimento: pessoa.nascimento,
    cargo: pessoa.cargo,
    data_admissao: pessoa.admissao,
    data_efetivacao: pessoa.efetivacao,
    valor_renda: salario_em_reais(pessoa.salario),
    tipo_renda: "Salário mensal",
    data_referencia_renda: "01/09/2026",
    telefone_celular: pessoa.celular,
    email_corporativo: email_a_partir_do_nome(pessoa.nome, "aurora.com.br"),
    cep_residencial: pessoa.cep,
    logradouro_residencial: pessoa.endereco,
    numero_residencial: pessoa.numero,
    bairro_residencial: pessoa.bairro,
    municipio_residencial: unidade.cidade,
    uf_residencial: "SP",
    cnpj_empregador: "12.345.678/0001-95",
    codigo_unidade: pessoa.unidade,
    nome_unidade: unidade.nome_unidade,
    cep_comercial: unidade.cep_comercial,
    municipio_comercial: unidade.municipio_comercial,
    uf_comercial: "SP",
  };
}

/**
 * Os dados da conferência do cenário atual: colunas, linhas, alterações da IA e ajustes.
 *
 * Recebe: nada (usa envio_atual, do cadastrar.js). Devolve: { colunas, linhas, alteracoes, ajustes }.
 */
function dados_da_conferencia() {
  // Cenário "conversa": os dados já estão prontos.
  if (envio_atual.cenario.id_do_resultado === "resultado-conversa") {
    return { colunas: COLUNAS_DA_CONVERSA, linhas: PESSOAS_DA_CONVERSA,
      alteracoes: ALTERACOES_DA_IA_NA_CONVERSA, ajustes: AJUSTES_DA_CONVERSA };
  }
  // Cenário "tabela": monta as 28 linhas completas.
  const linhas = [];
  PESSOAS_DA_INCLUSAO.forEach(function (pessoa, posicao) {
    linhas.push(linha_completa(pessoa, posicao + 1));
  });
  const dados = { colunas: COLUNAS_DA_TABELA.slice(), linhas: linhas, alteracoes: {}, ajustes: AJUSTES_DA_TABELA };
  // Copia as alterações da IA (a cópia pode ganhar as das colunas adicionadas sem mexer na lista original).
  for (const numero in ALTERACOES_DA_IA_NA_TABELA) {
    dados.alteracoes[numero] = Object.assign({}, ALTERACOES_DA_IA_NA_TABELA[numero]);
  }
  acrescentar_colunas_adicionadas(dados);
  return dados;
}

/**
 * Junta aos dados as colunas que entraram por orientação da empresa (ex.: "Obs RH" usada como e-mail pessoal).
 *
 * Recebe: dados — { colunas, linhas, alteracoes } do cenário "tabela". Devolve: nada (muda os dados recebidos).
 * Cada valor novo conta como "alterado pela IA", com o texto original da coluna no arquivo.
 */
function acrescentar_colunas_adicionadas(dados) {
  for (const adicionada of colunas_adicionadas) {
    dados.colunas.push(adicionada.coluna);
    dados.linhas.forEach(function (linha, posicao) {
      const numero_da_linha = posicao + 1;
      // Linha sem valor nessa coluna fica em branco (a IA não inventa).
      linha[adicionada.coluna.campo] = adicionada.valores[numero_da_linha] || "";
      if (adicionada.valores[numero_da_linha]) {
        if (!dados.alteracoes[numero_da_linha]) {
          dados.alteracoes[numero_da_linha] = {};
        }
        dados.alteracoes[numero_da_linha][adicionada.coluna.campo] = adicionada.originais[numero_da_linha];
      }
    });
  }
}

/**
 * Diz se o ajuste de uma pessoa já foi resolvido nos cartões do resultado (e com qual valor).
 *
 * Recebe: ajuste — { campo, nome, sugestao }.
 * Devolve: o valor corrigido (texto) se já foi resolvido; null se ainda está pendente.
 */
function valor_do_ajuste_resolvido(ajuste) {
  // O cartão do ajuste dessa pessoa, no resultado do cenário atual.
  const resultado = document.getElementById(envio_atual.cenario.id_do_resultado);
  for (const cartao of resultado.querySelectorAll("[data-ajuste]")) {
    const e_da_pessoa = cartao.querySelector(".ajuste-titulo").textContent.includes(ajuste.nome);
    if (e_da_pessoa && cartao.classList.contains("ajuste-resolvido")) {
      // Se a pessoa digitou o valor no cartão, é ele; senão, é a sugestão aceita.
      const campo_digitado = cartao.querySelector("input");
      if (campo_digitado && campo_digitado.value.trim()) {
        return campo_digitado.value.trim();
      }
      return ajuste.sugestao || "corrigido";
    }
  }
  // Nenhum cartão resolvido para essa pessoa.
  return null;
}

// ===== Tabela da conferência =====

/**
 * Monta o cabeçalho da tabela: nome do campo, nome no arquivo e selo quando a confiança é média.
 *
 * Recebe: colunas — a lista de colunas do cenário. Devolve: nada (preenche o <thead>).
 */
function montar_cabecalho(colunas) {
  const linha_do_cabecalho = document.querySelector("[data-cabecalho-conferencia]");
  linha_do_cabecalho.innerHTML = "";
  // Primeira coluna: o número da linha no arquivo.
  const coluna_da_linha = document.createElement("th");
  coluna_da_linha.textContent = "Linha";
  linha_do_cabecalho.appendChild(coluna_da_linha);
  for (const coluna of colunas) {
    const celula = document.createElement("th");
    // Nome amigável do campo do banco.
    celula.textContent = coluna.rotulo;
    // O "i" de ajuda: abre a explicação do campo (texto do parâmetro do layout).
    const botao_de_ajuda = document.createElement("button");
    botao_de_ajuda.type = "button";
    botao_de_ajuda.className = "botao-ajuda-campo";
    botao_de_ajuda.textContent = "i";
    botao_de_ajuda.dataset.campo = coluna.campo;
    botao_de_ajuda.dataset.rotulo = coluna.rotulo;
    botao_de_ajuda.setAttribute("aria-label", "O que é " + coluna.rotulo + "?");
    celula.appendChild(botao_de_ajuda);
    // Embaixo, de onde veio: "no arquivo: Remuneração".
    const origem = document.createElement("span");
    origem.className = "cabecalho-origem";
    origem.textContent = "no arquivo: " + coluna.no_arquivo;
    celula.appendChild(origem);
    // Confiança média: um selo avisa que vale olhar essa coluna com mais atenção.
    // Se a empresa já confirmou a leitura (pela orientação), o selo vira "confirmada por você".
    if (coluna.confianca === "media") {
      const selo = document.createElement("span");
      if (campos_confirmados_pela_empresa[coluna.campo]) {
        selo.className = "selo selo-sucesso selo-pequeno";
        selo.textContent = "confirmada por você";
      } else {
        selo.className = "selo selo-atencao selo-pequeno";
        selo.textContent = "confira";
      }
      celula.appendChild(selo);
    }
    linha_do_cabecalho.appendChild(celula);
  }
}

/**
 * Monta uma célula da tabela, com a cor certa: alterada pela IA, com ajuste pendente ou normal.
 *
 * Recebe: valor — o texto; original — o valor no arquivo, se a IA mudou (senão, undefined);
 *         pendente — true se é o campo com ajuste pendente.
 * Devolve: o <td> pronto.
 */
function montar_celula(valor, original, pendente) {
  const celula = document.createElement("td");
  celula.textContent = valor || "—";
  // Clicar na célula deixa editar o valor ali mesmo.
  celula.contentEditable = "true";
  celula.spellcheck = false;
  // Campo com ajuste pendente: laranja.
  if (pendente) {
    celula.className = "celula-com-ajuste";
    celula.title = "Precisa de ajuste antes de enviar";
  } else if (original !== undefined) {
    // Alterado pela IA: azul, com o valor original ao passar o mouse.
    celula.className = "celula-alterada";
    celula.title = "No arquivo estava: " + original;
  }
  // Quando a pessoa muda o valor, a célula fica verde e conta como correção dela.
  celula.addEventListener("input", function () {
    if (!celula.classList.contains("celula-corrigida")) {
      celula.className = "celula-corrigida";
      celula.title = "Corrigido por você";
      quantidade_corrigida_na_conferencia = quantidade_corrigida_na_conferencia + 1;
      atualizar_resumo_da_conferencia();
    }
  });
  return celula;
}

/**
 * Monta a tabela inteira da conferência, respeitando o filtro e a busca.
 *
 * Recebe: nada. Devolve: nada (preenche o <tbody>).
 */
function montar_tabela_da_conferencia() {
  const dados = dados_da_conferencia();
  // Com servidor, só as colunas dos campos obrigatórios do parâmetro (ADR-143); sem, todas as do exemplo
  const colunas = colunas_para_conferir(dados.colunas);
  montar_cabecalho(colunas);
  const corpo = document.querySelector("[data-corpo-conferencia]");
  corpo.innerHTML = "";
  // O texto buscado, em minúsculas.
  const busca = document.querySelector("[data-busca-conferencia]").value.trim().toLowerCase();
  dados.linhas.forEach(function (linha, posicao) {
    const numero_da_linha = posicao + 1;
    const alteracoes = dados.alteracoes[numero_da_linha] || {};
    const ajuste = dados.ajustes[numero_da_linha];
    // O ajuste está pendente se existe e ainda não foi resolvido nos cartões.
    const valor_resolvido = ajuste ? valor_do_ajuste_resolvido(ajuste) : null;
    const pendente = Boolean(ajuste) && valor_resolvido === null;
    // Filtros: "só o que a IA mudou" e "só com ajuste".
    if (filtro_da_conferencia === "alterados" && Object.keys(alteracoes).length === 0) {
      return;
    }
    if (filtro_da_conferencia === "ajuste" && !pendente) {
      return;
    }
    // Busca pelo nome.
    if (busca && !linha.nome_completo.toLowerCase().includes(busca)) {
      return;
    }
    corpo.appendChild(montar_linha_da_conferencia(linha, numero_da_linha, colunas, alteracoes, ajuste,
      valor_resolvido));
  });
  atualizar_resumo_da_conferencia();
}

/**
 * Monta a linha de uma pessoa na tabela da conferência.
 *
 * Recebe: linha — { campo: valor }; numero_da_linha; colunas; alteracoes — { campo: original };
 *         ajuste — o ajuste da linha (ou undefined); valor_resolvido — o valor corrigido nos cartões (ou null).
 * Devolve: o <tr> pronto.
 */
function montar_linha_da_conferencia(linha, numero_da_linha, colunas, alteracoes, ajuste, valor_resolvido) {
  const tr = document.createElement("tr");
  // Linha com ajuste pendente fica com o fundo alaranjado inteiro.
  const pendente = Boolean(ajuste) && valor_resolvido === null;
  if (pendente) {
    tr.className = "linha-pendente";
  }
  // Primeira célula: número da linha (e o aviso de que não vai no envio, se pendente).
  const celula_numero = document.createElement("td");
  celula_numero.className = "celula-numero";
  celula_numero.textContent = numero_da_linha;
  if (pendente) {
    celula_numero.title = "Fica guardado até você corrigir; não vai neste envio";
  }
  tr.appendChild(celula_numero);
  for (const coluna of colunas) {
    // O ajuste já resolvido nos cartões aparece com o valor corrigido, em verde.
    if (ajuste && ajuste.campo === coluna.campo && valor_resolvido !== null) {
      const celula = montar_celula(valor_resolvido, undefined, false);
      celula.className = "celula-corrigida";
      celula.title = "Corrigido por você";
      tr.appendChild(celula);
      continue;
    }
    const e_o_campo_pendente = pendente && ajuste.campo === coluna.campo;
    tr.appendChild(montar_celula(linha[coluna.campo], alteracoes[coluna.campo], e_o_campo_pendente));
  }
  return tr;
}

// ===== Resumo e envio =====

/**
 * Escreve a quantidade com o texto no singular ou no plural.
 *
 * Recebe: quantidade — número; singular e plural — o texto de cada caso.
 * Devolve: o texto. Ex.: (1, "valor ajustado", "valores ajustados") → "1 valor ajustado"; com 12 → "12 valores ajustados".
 */
function quantidade_com_texto(quantidade, singular, plural) {
  // Só 1 fica no singular.
  if (quantidade === 1) {
    return "1 " + singular;
  }
  return quantidade + " " + plural;
}

/**
 * Atualiza os números do rodapé e dos filtros, e o texto do botão de envio.
 *
 * Recebe: nada. Devolve: nada.
 */
function atualizar_resumo_da_conferencia() {
  const dados = dados_da_conferencia();
  // Quantos valores a IA mudou e quantas linhas mudaram.
  let valores_alterados = 0;
  let linhas_alteradas = 0;
  for (const numero in dados.alteracoes) {
    valores_alterados = valores_alterados + Object.keys(dados.alteracoes[numero]).length;
    linhas_alteradas = linhas_alteradas + 1;
  }
  // Quantas linhas ainda têm ajuste pendente.
  let pendentes = 0;
  for (const numero in dados.ajustes) {
    if (valor_do_ajuste_resolvido(dados.ajustes[numero]) === null) {
      pendentes = pendentes + 1;
    }
  }
  const prontos = dados.linhas.length - pendentes;
  // Contagens nos filtros.
  document.querySelector("[data-contagem-conferencia='todos']").textContent = "(" + dados.linhas.length + ")";
  document.querySelector("[data-contagem-conferencia='alterados']").textContent = "(" + linhas_alteradas + ")";
  document.querySelector("[data-contagem-conferencia='ajuste']").textContent = "(" + pendentes + ")";
  // A frase do rodapé.
  let frase = quantidade_com_texto(prontos, "pronto para enviar", "prontos para enviar") + " · " +
    quantidade_com_texto(valores_alterados, "valor ajustado pelos agentes", "valores ajustados pelos agentes") + " · " +
    quantidade_com_texto(quantidade_corrigida_na_conferencia, "corrigido por você", "corrigidos por você");
  if (pendentes > 0) {
    frase = frase + " · " + quantidade_com_texto(pendentes, "guardado até você corrigir", "guardados até você corrigir");
  }
  document.querySelector("[data-resumo-conferencia]").textContent = frase;
  // O botão diz quantos vão.
  document.querySelector("[data-enviar-conferido]").textContent = "Enviar " + prontos + " funcionários para o banco";
  document.querySelector("[data-enviar-conferido]").dataset.quantidade = prontos;
}

/**
 * Abre a conferência (a partir do botão "Conferir a lista" do resultado).
 *
 * Recebe: nada. Devolve: nada.
 */
function abrir_conferencia() {
  const conferencia = document.getElementById("etapa-conferencia");
  conferencia.hidden = false;
  montar_tabela_da_conferencia();
  // Leva a tela até a conferência, com uma rolagem suave.
  conferencia.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Troca o filtro da conferência e remonta a tabela.
 *
 * Recebe: botao — o filtro clicado (o nome fica em data-filtro-conferencia). Devolve: nada.
 */
function trocar_filtro_da_conferencia(botao) {
  filtro_da_conferencia = botao.dataset.filtroConferencia;
  // Só o filtro clicado fica destacado.
  for (const outro of document.querySelectorAll("[data-filtro-conferencia]")) {
    outro.classList.toggle("filtro-rapido-ativo", outro === botao);
  }
  montar_tabela_da_conferencia();
}

/**
 * Envia a lista conferida: no protótipo, leva para "Acompanhar cadastros" com o aviso de recebimento.
 *
 * Recebe: nada. Devolve: nada.
 * No sistema real, grava quem conferiu e quando, e manda os funcionários para a análise do banco.
 */
function enviar_lista_conferida() {
  const quantidade = document.querySelector("[data-enviar-conferido]").dataset.quantidade;
  window.location.href = "acompanhar.html?enviado=" + quantidade;
}

// ===== Descartar a leitura (arquivo errado) =====

/**
 * Abre a confirmação de descarte, dizendo qual arquivo e quantos funcionários serão apagados.
 *
 * Recebe: nada (usa envio_atual, do cadastrar.js). Devolve: nada.
 */
function pedir_confirmacao_do_descarte() {
  const quantidade = envio_atual.cenario.total_de_registros;
  document.querySelector("[data-texto-descartar]").textContent =
    "Nada foi enviado ao banco. Os " + quantidade + " funcionários lidos de \"" + envio_atual.nome_exibido +
    "\" e as correções feitas nesta tela serão apagados. Depois, você escolhe outro arquivo.";
  document.getElementById("janela-descartar").showModal();
}

/**
 * Descarta a leitura e volta para a escolha do arquivo (no protótipo, recarrega a página).
 *
 * Recebe: nada. Devolve: nada.
 * No sistema real, o envio não enviado é apagado (ou marcado como descartado, com quem e quando).
 */
function descartar_leitura() {
  window.location.href = "cadastrar.html";
}

/**
 * Liga os botões da conferência. É chamada quando a página termina de carregar.
 *
 * Recebe: nada. Devolve: nada.
 */
function preparar_conferencia() {
  // Os botões "Conferir a lista" dos dois resultados.
  for (const botao of document.querySelectorAll("[data-botao-conferir]")) {
    botao.addEventListener("click", abrir_conferencia);
  }
  // Filtros.
  for (const botao of document.querySelectorAll("[data-filtro-conferencia]")) {
    botao.addEventListener("click", function () {
      trocar_filtro_da_conferencia(botao);
    });
  }
  // Busca pelo nome.
  document.querySelector("[data-busca-conferencia]").addEventListener("input", montar_tabela_da_conferencia);
  // A caixa "Conferi a lista" libera o botão de envio.
  const caixa = document.querySelector("[data-conferi-a-lista]");
  const botao_enviar = document.querySelector("[data-enviar-conferido]");
  caixa.addEventListener("change", function () {
    botao_enviar.disabled = !caixa.checked;
  });
  botao_enviar.addEventListener("click", enviar_lista_conferida);
  // O "i" de ajuda das colunas. A escuta fica no cabeçalho inteiro, porque ele é refeito a cada filtro.
  document.querySelector("[data-cabecalho-conferencia]").addEventListener("click", function (evento) {
    const botao = evento.target.closest(".botao-ajuda-campo");
    if (botao) {
      // Impede que este mesmo clique "suba" até a página e feche o balão na hora.
      evento.stopPropagation();
      abrir_ajuda_do_campo(botao);
    }
  });
  // Fecha o balão: clique fora dele, tecla Esc ou rolagem (da página ou da tabela).
  document.addEventListener("click", function (evento) {
    if (!evento.target.closest("[data-balao-ajuda]")) {
      fechar_ajuda_do_campo();
    }
  });
  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") {
      fechar_ajuda_do_campo();
    }
  });
  window.addEventListener("scroll", fechar_ajuda_do_campo);
  document.querySelector(".tabela-conferencia-caixa").addEventListener("scroll", fechar_ajuda_do_campo);
  // "Descartar esta leitura" (no resultado e no fim da conferência) e a janela de confirmação.
  for (const botao of document.querySelectorAll("[data-descartar-leitura]")) {
    botao.addEventListener("click", pedir_confirmacao_do_descarte);
  }
  document.querySelector("[data-confirmar-descarte]").addEventListener("click", descartar_leitura);
  document.querySelector("[data-cancelar-descarte]").addEventListener("click", function () {
    document.getElementById("janela-descartar").close();
  });
}

// Espera o HTML carregar inteiro antes de ligar tudo.
document.addEventListener("DOMContentLoaded", preparar_conferencia);
