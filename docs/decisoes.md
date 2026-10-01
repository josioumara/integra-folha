# Decisões de arquitetura (ADRs)

Cada decisão do Integra Folha (nome do projeto até o ADR-103: AI Payroll Hub) registrada no formato **ADR** (*Architecture Decision Record*):
o problema, as **opções disponíveis**, o que escolhemos, **por quê**, o que aceitamos perder e como
vamos comprovar. O desenho resultante está em [arquitetura.md](arquitetura.md).

**Status:** ✅ decidida · 🧪 decidida, mas a comprovar com medição · ⏳ pendente (depende do dono do projeto) · 🔁 substituída por uma decisão posterior

**Origem:** `§` = seção do plano v1.8 · "Negócio" = decisão ou premissa da área de negócio · "Técnica" = decisão de engenharia.

## Índice

| ADR | Decisão | Status |
|---|---|---|
| **A. Princípios** | | |
| [01](#adr-01) | IA onde há ambiguidade, regra onde há certeza, humano onde há risco | ✅ |
| [02](#adr-02) | Workflow no fluxo da empresa; multiagente só onde há ganho | 🧪 |
| **B. Conhecimento e IA** | | |
| [03](#adr-03) | O banco descreve o layout num parâmetro (não há manual) | ✅ |
| [04](#adr-04) | Tipos de campo de um catálogo fechado | ✅ |
| [05](#adr-05) | Interpretador com LLM, e o valor do RAG é medido | 🧪 |
| [06](#adr-06) | Fine-Tuning de modelo pequeno como diferencial | ✅ fora desta versão ([80](#adr-80)) |
| [07](#adr-07) | Saídas estruturadas validadas e prompts com abstenção | ✅ |
| [08](#adr-08) | ChromaDB como base vetorial | ✅ |
| [09](#adr-09) | Corte dos documentos por campo ou por seção | ✅ |
| [10](#adr-10) | Isolamento entre empresas no RAG por filtro de metadado | ✅ |
| [11](#adr-11) | Provedor de LLM | ✅ |
| [70](#adr-70) | A memória que aprende: mapeamentos aprovados pelo banco entram na busca (mínimo de 2 empresas: [116](#adr-116)) | ✅ |
| **C. Etapas determinísticas** | | |
| [12](#adr-12) | Normalizador sem LLM | ✅ |
| [13](#adr-13) | Validador: regras decidem, LLM só explica | ✅ |
| [14](#adr-14) | Enquadramento de renda por mediana do cargo | ✅ |
| **D. Agentes e orquestração** | | |
| [15](#adr-15) | LangGraph para orquestrar | ✅ |
| [16](#adr-16) | Onde o humano decide | ✅ |
| [17](#adr-17) | Handoff do Assistente de Correção para o Interpretador | ✅ |
| [18](#adr-18) | Consultor como supervisor de 3 subagentes (em uso desde o [117](#adr-117): agente único) | 🧪 |
| [19](#adr-19) | Endomarketing como agente único com RAG (quem gera passou a ser o banco: [115](#adr-115)) | ✅ |
| [20](#adr-20) | Ferramentas fechadas, sem SQL livre | ✅ |
| **E. Dados e negócio** | | |
| [21](#adr-21) | Dados 100% sintéticos, gerados com seed | ✅ |
| [22](#adr-22) | Layout fictício com ~44 campos | ✅ |
| [23](#adr-23) | Carga inicial + inclusões; desligamentos fora | ✅ |
| [24](#adr-24) | Reaproveitar o mapeamento homologado nas inclusões | ✅ |
| [25](#adr-25) | Motor determinístico de planejamento, sem ofertas | ✅ |
| [26](#adr-26) | Premissas financeiras parametrizáveis, sem taxa padrão | ✅ |
| [27](#adr-27) | Região, segmento e ciclo de vida | ✅ |
| **F. Privacidade, ética e segurança** | | |
| [28](#adr-28) | Três finalidades para os dados (LGPD) | ✅ |
| [29](#adr-29) | Campos proibidos para uso comercial | ✅ |
| [30](#adr-30) | Número agregado com mínimo de pessoas (sigilo bancário) (revisto pelo [102](#adr-102)) | 🔁 |
| [102](#adr-102) | A empresa vê a conta aberta de cada funcionário dela, para pagar o salário | ✅ |
| [103](#adr-103) | O projeto passa a se chamar Integra Folha também no Git, no banco e no deck | ✅ |
| [104](#adr-104) | A IA decide dividir uma coluna; a regra divide todas as linhas; a empresa comenta e a IA refaz só aquela coluna | 🧪 |
| [105](#adr-105) | Sem o modelo de linguagem no detector; o rótulo vem da IA; um conferidor de outra IA, ligado após a prova (EXP-015) | ✅ |
| [106](#adr-106) | Plano B da IA no Bedrock: Claude Sonnet 4.6 medido; Nova e Haiku 4.5 fora do formato | 🔁 [107](#adr-107) |
| [107](#adr-107) | Formato garantido no Interpretador pelo Bedrock; plano B Sonnet 4.6 + Nova 2 Lite | ✅ |
| [108](#adr-108) | O contêiner sobe a API e o Streamlit sai do código; pronto para a AWS atrás de https | 🧪 (falta construir a imagem) |
| [109](#adr-109) | Senha provisória obrigatória de trocar e nova senha pelo banco no front novo | ✅ |
| [110](#adr-110) | Lacunas de segurança fechadas: limite de tentativas de login, cabeçalhos do navegador (CSP), limite do pedido na entrada e contêiner sem administrador | 🧪 |
| [111](#adr-111) | Consulta de funcionários com todos os campos do parâmetro, obrigatórios marcados e "Informação não encontrada" | ✅ |
| [112](#adr-112) | Visão geral da empresa no banco (números e lista de funcionários); Situação primeiro e legenda dos status | ✅ |
| [113](#adr-113) | "Conta aberta" como a última situação do funcionário; a conta em colunas separadas (código do banco, agência, conta) | ✅ |
| [114](#adr-114) | Situação "Aguardando envio": sem pendência, mas o envio ainda está com a empresa | ✅ |
| [115](#adr-115) | O banco gera o endomarketing; a empresa só baixa e divulga | ✅ |
| [116](#adr-116) | O aprendizado do RAG exige 2 empresas confirmando o mesmo par | ✅ |
| [117](#adr-117) | Consultor simplificado: agente único em uso; o supervisor fica só no experimento | 🧪 |
| [118](#adr-118) | Pendências resolvidas por conversa com a IA, que aplica na hora, presa à pendência, com Desfazer | ✅ |
| [119](#adr-119) | Arquivo de contas abertas com layout fixo, recusado inteiro com qualquer divergência | ✅ |
| [120](#adr-120) | Pendências em grupo (uma pergunta para o mesmo valor em várias pessoas) e "Resolvidas" com a conversa guardada | ✅ |
| [121](#adr-121) | O especialista aponta problema por pessoa e aprova os outros, devolvendo só os apontados | ✅ |
| [124](#adr-124) | Informação de cada pessoa ou igual para todos: uma marcação do parâmetro, lida pelo Validador, pelo agente e pelo RAG | ✅ |
| [134](#adr-134) | Hospedagem: uma EC2 t3.small na Virgínia, ligada o tempo todo, com swap, e a infraestrutura como código | ✅ |
| [135](#adr-135) | Retenção zero do Bedrock gravada na conta (modo none, na Virgínia) | ✅ |
| [136](#adr-136) | Backup diário no S3 privado, gravado pelo papel da máquina, que não consegue apagar | 🧪 (falta testar a restauração) |
| [137](#adr-137) | O Caddy como porteiro: https automático, e a aplicação e o banco sem porta para fora | ✅ |
| [154](#adr-154) | A senha provisória vence em 48 h; vencida, o login recusa com o aviso, e o banco gera uma nova | ✅ |
| [155](#adr-155) | O "Baixar lista" de Acompanhar traz a grade inteira (todas as situações), e a recusa aparece ao lado do botão | ✅ |
| [31](#adr-31) | Mascaramento antes do LLM (revisto pelo [101](#adr-101)) | 🔁 |
| [101](#adr-101) | Com a IA pelo AWS Bedrock, ela vê os dados reais: saem a máscara e as etiquetas | ✅ |
| [32](#adr-32) | Login com cadastro de usuários por perfil | ✅ |
| **G. Plataforma** | | |
| [33](#adr-33) | Streamlit como interface | ✅ |
| [34](#adr-34) | SQLite como banco (substituído pelo ADR-67) | 🔁 |
| [67](#adr-67) | PostgreSQL como banco, com o SQLite pela mesma porta | ✅ |
| [68](#adr-68) | Docker de verdade: subida sem custo e Streamlit sem estatísticas de uso | ✅ |
| [69](#adr-69) | Novo front (páginas do layout) ligado por uma API FastAPI, com porteiro por perfil | ✅ |
| [71](#adr-71) | Pontos de salvamento apagados 90 dias depois de o envio acabar | 🧪 |
| [35](#adr-35) | Docker em container com processo contínuo | ⏳ |
| [36](#adr-36) | Cliente de LLM isolado, modo MOCK e proteção de custo | ✅ |
| [38](#adr-38) | Defesa em camadas contra prompt injection | ✅ |
| [39](#adr-39) | Processamento em andamento guardado na URL | ✅ |
| [40](#adr-40) | Sessão lembrada por cookie: o F5 não desloga | ✅ |
| **H. Avaliação** | | |
| [37](#adr-37) | Experimento controlado B0–B5 com significância estatística | ✅ |
| [41](#adr-41) | Baseline B0 calibrado numa validação tirada do treino, nunca na prova | ✅ |
| [42](#adr-42) | Embeddings locais e ajustes da busca medidos nas consultas de teste | ✅ |
| [152](#adr-152) | A fidelidade do Endomarketing pelo RAGAS, com o juiz de outra família, como filtro e sem calibração humana | ✅ |
| **I. Leitura do arquivo** | | |
| [43](#adr-43) | Na leitura, toda célula vira texto; nada é convertido antes do Normalizador | ✅ |
| [44](#adr-44) | Amostras para a IA: formato mascarado, categorias à mostra (revisto pelo [101](#adr-101)) | 🔁 |
| **J. Agente Interpretador** | | |
| [45](#adr-45) | Interpretador em MOCK que recebe o prompt de verdade, e caminhos de falha previstos | ✅ |
| **K. Normalizador** | | |
| [46](#adr-46) | Normalizador: converter só o que tem certeza; a dúvida vira decisão da empresa | ✅ |
| **L. Validador** | | |
| [47](#adr-47) | Severidade por regra, renda por "z robusto" e explicação só com os achados | ✅ |

---

## A. Princípios

<a id="adr-01"></a>
### ADR-01 · IA onde há ambiguidade, regra onde há certeza, humano onde há risco ✅

**Contexto.** É preciso decidir, etapa por etapa, quem faz o trabalho: um LLM, uma regra escrita em
código ou uma pessoa.

| Opção | A favor | Contra |
|---|---|---|
| LLM em tudo | Rápido de montar; flexível | Resultado muda a cada execução; pode errar valores financeiros; caro; difícil de auditar |
| Regras em tudo | Previsível e barato | Não entende colunas nunca vistas; exige mapeamento manual por empresa (é a dor atual) |
| Humano em tudo | Máximo controle | É exatamente o processo que faz 50,4% das empresas desistirem |
| **Cada um onde é melhor** | Usa a força de cada um | Exige desenhar as fronteiras com cuidado |

**Decisão.** LLM só onde há ambiguidade real (entender colunas, conversar, interpretar perguntas).
Regras onde o resultado é derivável (converter, validar, calcular). Humano onde há risco (aceitar
mapeamento ambíguo, aprovar correções, homologar).

**Por quê.** Num banco, valor financeiro errado e decisão sem responsável não são aceitáveis. O LLM
entra onde nenhuma regra resolveria.

**Trade-off aceito.** Mais componentes para construir e integrar do que um "LLM faz tudo".

**Como comprovamos.** Testes golden de integridade (valores e linhas preservados) e experimento que
mede o ganho do LLM sobre o baseline sem LLM (B0 × B3, ADR-37).

**Origem.** §3, §4.

<a id="adr-02"></a>
### ADR-02 · Workflow no fluxo da empresa; multiagente só onde há ganho 🧪

**Contexto.** Definições usadas no projeto: **workflow** = o código decide o próximo passo;
**agente** = o LLM decide; **multiagente** = vários agentes interagem (delegam, passam o controle).

| Opção | A favor | Contra |
|---|---|---|
| Workflow em tudo | Previsível e auditável | Rígido na conversa; não chega a ser multiagente |
| Um agente autônomo coordenando tudo | Flexível | Imprevisível num fluxo que mexe em dado financeiro; difícil de auditar |
| Multiagente livre (agentes negociando entre si) | "Multiagente" no sentido mais amplo | Caro, lento, difícil de testar e de explicar quem decidiu o quê |
| **Workflow + multiagente pontual** | Controle onde há dinheiro; autonomia onde há conversa | Duas formas de orquestrar no mesmo sistema |

**Decisão.** O fluxo da empresa é um workflow com caminhos fixos, com um handoff entre agentes
(ADR-17). O fluxo do banco é multiagente com supervisor (ADR-18).

**Por quê.** Multiagente custa mais e é menos previsível. Só se justifica onde a tarefa se divide
naturalmente (perguntas compostas do especialista) ou onde a conversa precisa devolver trabalho a
outro agente (remapeamento).

**Trade-off aceito.** Menos autonomia entre agentes em troca de rastreabilidade.

**Como comprovamos.** Comparação agente único × supervisor no Consultor (ADR-18); Painel Técnico
mostrando cada handoff e delegação.

**Origem.** Decisão do dono do projeto, 2026-09-23.

---

## B. Conhecimento e IA

<a id="adr-03"></a>
### ADR-03 · O banco descreve o layout num parâmetro (não há manual) ✅

**Contexto.** O plano previa um "manual de integração fictício e extenso" como base do RAG. Na
realidade, esse manual não existe: há só o arquivo-modelo que a empresa preenche.

| Opção | A favor | Contra |
|---|---|---|
| Inventar um manual extenso (plano) | Dá volume para o RAG | Artificial; a banca pode dizer que o manual foi inflado para justificar o RAG |
| Layout fixo no código | Simples | Cada mudança de layout exige programador e deploy |
| Copiar o layout real do banco | Realista | Material interno; não pode entrar no projeto |
| **Parâmetro cadastrado numa tela** | Reflete o que existe; layout novo = versão nova, sem código | Exige construir a tela e o versionamento |

**Decisão.** O banco cadastra, numa tela, cada campo que quer receber: nome, descrição, tipo,
obrigatório, regra, "não confundir com", sensível, uso comercial permitido e exemplo. Cada gravação
gera uma versão.

**Por quê.** É a forma honesta de dar conhecimento à IA sem inventar documentos, e torna a solução
escalável: outro layout é outro parâmetro.

**Trade-off aceito.** A qualidade do mapeamento depende de o banco descrever bem os campos.

**Como comprovamos.** Demo ao vivo: cadastrar campos de benefício e PLR e processar um arquivo que
os contém, sem mudar código.

**Origem.** Negócio, 2026-09-23 (desvio do §4).

<a id="adr-04"></a>
### ADR-04 · Tipos de campo de um catálogo fechado ✅

**Contexto.** Se o banco pode criar campos, alguém precisa definir como cada um é convertido e
validado.

| Opção | A favor | Contra |
|---|---|---|
| Tipo livre, conversão feita pelo LLM | Flexível | Conversão de valor financeiro fica imprevisível |
| LLM gera código de conversão para cada campo | Flexível | Código gerado em produção, difícil de auditar e testar |
| **Catálogo fechado** (TEXTO, CPF, CNPJ, CEP, UF, TELEFONE, EMAIL, MATRICULA, DECIMAL_MONETARIO, DATA, DOMINIO) | Conversão e validação testadas uma vez, reusadas em todo campo | Tipo novo exige programar |

**Decisão.** O banco escolhe o tipo de cada campo dentro do catálogo. O tipo decide a conversão
(Normalizador) e a validação (Validador).

**Por quê.** Mantém o que mexe em dado 100% determinístico e faz 44 campos custarem uns 11 tipos,
não 44 regras.

**Trade-off aceito.** Um formato realmente novo exige um tipo novo no código.

**Como comprovamos.** Teste que recusa parâmetro com tipo fora do catálogo; testes unitários por tipo.

**Origem.** Técnica, 2026-09-23 (deriva do §4).

<a id="adr-05"></a>
### ADR-05 · Interpretador com LLM, e o valor do RAG é medido 🧪

**Contexto.** O Interpretador precisa dizer que "Sal. Bruto Mês" é `salario_bruto`. Há várias formas
de dar a ele o conhecimento necessário.

| Opção | A favor | Contra |
|---|---|---|
| B0 · Dicionário de sinônimos + fuzzy, sem LLM | Barato, previsível | Falha em nomes nunca vistos e ambíguos |
| B1 · LLM só com nomes e tipos dos campos | Simples | Não sabe o significado nem as armadilhas |
| B2 · LLM com parâmetro completo + todo o histórico no prompt | Vê tudo; sem risco de busca errada | Paga pelo contexto inteiro a cada chamada, e ele cresce com o histórico |
| B3 · LLM com parâmetro completo + RAG no histórico | Prompt menor; cita a fonte | Depende de a busca trazer o trecho certo |

**Decisão.** Implementar B0 a B3 com o mesmo código e medir. A configuração do fluxo principal será
a que vencer em acerto, custo e latência.

**Por quê.** Com 44 campos o parâmetro cabe no prompt, então o RAG não é óbvio. O que cresce é o
histórico de mapeamentos homologados, e é nele que o RAG precisa provar valor. Assumir o RAG sem
medir é o erro que a banca procura.

**Trade-off aceito.** Se o RAG perder, ele sai do Interpretador (continua no Assistente de Correção e
no Endomarketing) e o resultado negativo vai para o relatório.

**Como comprovamos.** ADR-37: acurácia por campo com IC 95%, abstenção correta, custo e latência.

**Origem.** §4 (adaptado ao ADR-03).

<a id="adr-06"></a>
### ADR-06 · Fine-Tuning de modelo pequeno como diferencial ✅ (fechado no ADR-80: fora desta versão)

**Contexto.** O enunciado pede "RAG, fine-tuning ou outro" e a avaliação. Pergunta de negócio: um
modelo pequeno ajustado iguala o grande com RAG a custo e latência menores?

| Opção | A favor | Contra |
|---|---|---|
| Sem Fine-Tuning | Simples | Perde o diferencial e a resposta à pergunta de custo |
| Fine-Tuning obrigatório | Diferencial garantido | Entrega depende do acesso ao ajuste |
| **Diferencial: B4 (pequeno sem ajuste) e B5 (pequeno ajustado)** | Aprofunda sem arriscar a entrega | Trabalho extra de dataset e treino |
| Ajuste por API gerenciada | Servido pelo mesmo cliente de LLM | Depende do provedor oferecer |
| Ajuste LoRA em modelo aberto | Independe do provedor | Servir exige GPU; avaliação fica offline |

**Decisão.** Fine-Tuning como diferencial, com B4 como controle para isolar o efeito do ajuste. O
modelo ajustado só vira padrão se igualar B3 com custo e latência menores. **Pendente:** API
gerenciada ou LoRA, conforme o provedor (ADR-11).

**Por quê.** O RAG avaliado já atende ao enunciado; o ajuste responde uma pergunta de custo sem pôr a
entrega em risco.

**Trade-off aceito.** Se o acesso falhar, registra-se a decisão e segue-se com B0–B3.

**Quando testar o acesso (2026-09-24).** O plano previa um treino mínimo no dia 1. Como o dataset de
treino só nasce na Fase 2 e o teste depende do provedor escolhido, o treino mínimo acontece depois da
escolha do provedor e **antes da Fase 3**, ainda a tempo de retirar B4–B5 sem retrabalho.

**Adiado (2026-09-25).** OpenAI e Anthropic não oferecem ajuste fino viável (ADR-11); o caminho seria um modelo aberto na
Together AI (LoRA). O dono do projeto adiou a decisão para depois da comparação de modelos: se um modelo pequeno barato já
chegar perto dos grandes, o argumento de custo enfraquece e sobra o de soberania dos dados (modelo aberto rodando dentro
do banco).

**Como comprovamos.** B4 × B5 (efeito do ajuste) e B5 × B3 (viabilidade do modelo pequeno).

**Origem.** §4, §8 (v1.7).

<a id="adr-07"></a>
### ADR-07 · Saídas estruturadas validadas e prompts com abstenção ✅

**Contexto.** A saída de um agente vira entrada de outro componente. Texto livre quebra a integração.

| Opção | A favor | Contra |
|---|---|---|
| Texto livre, interpretado depois | Simples | Frágil; erro silencioso |
| JSON sem validação | Estruturado | Campo faltando ou tipo errado passa adiante |
| **Schema Pydantic + nova tentativa informando o erro** | Erro detectado na fronteira | Uma chamada extra quando falha |
| Sempre dar uma resposta | Nunca "trava" | Chuta quando não sabe |
| **Política de abstenção (AMBIGUO)** | Pede confirmação em vez de chutar | Mais pendências para o humano |

**Decisão.** Toda resposta de LLM é validada por schema; prompts versionados em `prompts/`, com
papel, contrato de saída, restrições, abstenção e exemplos só do conjunto de treino; temperatura baixa.

**Por quê.** "Vencimentos" pode ser bruto, líquido ou crédito. Chutar é pior que perguntar.

**Trade-off aceito.** A empresa confirma mais campos do que confirmaria com um modelo "confiante".

**Como comprovamos.** Precisão e recall da abstenção; teste de saída inválida rejeitada;
concordância em 5 execuções do mesmo arquivo.

**Origem.** §4 (engenharia de prompts).

<a id="adr-08"></a>
### ADR-08 · ChromaDB como base vetorial ✅

| Opção | A favor | Contra |
|---|---|---|
| **ChromaDB** | Roda local, sem servidor; guarda metadados e filtra por eles; persiste em disco | Não é o que se usaria em grande escala |
| FAISS | Muito rápido | É uma biblioteca de busca: metadados e persistência ficam por nossa conta |
| pgvector (PostgreSQL) | Busca vetorial junto do banco relacional | Exige um servidor PostgreSQL |
| Serviço gerenciado | Escala sem esforço | Custo, conta externa e dados saindo do ambiente |

**Decisão.** ChromaDB. **Por quê.** O volume do MVP é pequeno e o filtro por metadado é essencial
(ADR-10). **Trade-off aceito.** Em produção, reavaliar por volume e infraestrutura do banco.
**Origem.** §8, §20.

<a id="adr-09"></a>
### ADR-09 · Corte dos documentos por campo ou por seção ✅

| Opção | A favor | Contra |
|---|---|---|
| Pedaços de tamanho fixo (ex.: 500 caracteres) | Genérico | Pode separar uma condição do produto a que ela se refere |
| **Pela estrutura do documento** | Cada trecho faz sentido sozinho | Depende de o documento ter estrutura |

**Decisão.** Um trecho por unidade de sentido: no parâmetro, **um campo**; no histórico, **um
mapeamento homologado** (coluna → campo, empresa, versão); nas regras, **uma regra**; no catálogo de
benefícios (Markdown), **uma seção `##`**. Dois refinamentos: (1) cada trecho carrega o caminho de
origem (ex.: "Horizonte › Catálogo de benefícios v2 › Conta salário"), porque uma seção lida sozinha
nem sempre diz de que empresa ou produto fala; (2) seção longa demais é dividida por parágrafo,
repetindo o título. **Por quê.** O agente recebe trechos completos, e a fonte citada aponta para algo
inteligível. **Trade-off aceito.** Depende de os documentos terem estrutura (o formulário do catálogo
e o parâmetro garantem isso). **Como comprovamos.** hit@k nas consultas de teste; o k de cada base é
escolhido pela medição.
**Origem.** §Fase 2; técnica, 2026-09-23.

<a id="adr-10"></a>
### ADR-10 · Isolamento entre empresas no RAG por filtro de metadado ✅

| Opção | A favor | Contra |
|---|---|---|
| Instrução no prompt ("não mostre outras empresas") | Trivial | Um texto malicioso pode furar |
| Um índice separado por empresa | Isolamento físico | Mais índices para manter |
| **Um índice com filtro obrigatório por empresa** | O documento de outra empresa nem chega ao LLM; um índice só | O filtro precisa estar em toda consulta |

**Decisão.** Filtro por `empresa` (e vigência) aplicado no serviço de busca, a partir do usuário
logado, nunca a partir do texto do pedido. **Como comprovamos.** Teste em que a Empresa A pede o
pacote da B. **Origem.** Técnica, 2026-09-23.

<a id="adr-11"></a>
### ADR-11 · Provedor de LLM ✅

**Contexto.** Todo o sistema chama o LLM por um cliente isolado (ADR-36), então trocar de provedor
não muda o resto do código.

| Critério | Por que importa |
|---|---|
| Saída estruturada confiável | ADR-07 |
| Modelo pequeno com Fine-Tuning disponível | ADR-06 |
| Custo por arquivo e teto de gasto | Link público (ADR-36) |
| Política de dados e retenção | Em produção, aprovação corporativa |
| Latência | Experiência da empresa e do especialista |

**Opções.** Os grandes provedores comerciais de LLM ou modelos abertos hospedados. **Origem.** §8, §20.

**Levantamento de mercado (2026-09-24, páginas oficiais de preço; preço por 1 milhão de tokens, entrada / saída).**

| Provedor | Modelo grande | Modelo pequeno | Fine-Tuning para o B5 |
|---|---|---|---|
| OpenAI | gpt-5.4: US$ 2,50 / 15 | gpt-5-mini: US$ 0,25 / 2,00 | ❌ A plataforma de ajuste está sendo encerrada e **não aceita usuários novos** |
| Anthropic | Claude Sonnet 5: US$ 2 / 10 | Claude Haiku 4.5: US$ 1 / 5 | ❌ Não existe na API da Claude; no Amazon Bedrock, só o antigo Claude 3 Haiku, só na região de Oregon |
| Google | Gemini 3.1 Pro: US$ 2 / 12 | Gemini 3.8 Flash: US$ 0,75 / 3,75 (promocional até dez/2026); Flash-Lite: US$ 0,25 / 1,50 | ⚠️ Fora da API pública; só na plataforma empresarial do Google Cloud, em modelos mais antigos (2.5) |
| Together AI (modelos abertos) | — | Qwen 3.5 9B, Llama 3.1 8B | ✅ LoRA por API: US$ 0,34 por 1M tokens de treino, mínimo US$ 4 por treino |

Fontes: developers.openai.com/api/docs/pricing · platform.claude.com/docs/en/about-claude/pricing ·
ai.google.dev/gemini-api/docs/pricing e /model-tuning · aws.amazon.com (Claude 3 Haiku no Bedrock) ·
together.ai/pricing. Os tokenizadores são diferentes (os modelos Claude 4.7 em diante geram ~30% mais tokens
para o mesmo texto), então preço por token não é custo por arquivo: o custo real sai da medição.

**Consequência para o ADR-06.** Nenhum dos dois provedores preferidos pelo dono do projeto (OpenAI e
Anthropic) oferece ajuste fino hoje. Para o B4 × B5 isolar o efeito do ajuste, os dois precisam da **mesma
base**: o caminho viável é um modelo aberto pequeno na Together (B4 = sem ajuste, B5 = ajustado com LoRA),
com o provedor principal cuidando de B1–B3 e dos agentes. Falta confirmar se o modelo ajustado é servido por
token ou exige servidor dedicado.

**OpenAI × Anthropic nos critérios deste ADR (avaliação de 2026-09-24).** Fine-Tuning: nenhum dos dois.
Custo do modelo grande (o que faz quase todo o trabalho): Sonnet 5 é mais barato por token, mas gera mais
tokens, e na prática fica perto de empatar. Modelo pequeno (só o classificador do guardrail): gpt-5-mini é bem
mais barato, mas pesa pouco na conta. Saída estruturada: os dois atendem, e o código valida com contrato e nova
tentativa de qualquer forma. Política de dados: por padrão, nenhum dos dois treina com dados da API (confirmar
os termos na criação da conta; os dados do projeto são sintéticos). **Leitura: empate técnico no papel.**

**Recomendação registrada.** Decidir por **medição**, não por preferência: rodar o B3 nas mesmas 30 planilhas
da prova congelada com os dois provedores (menos de US$ 1 por provedor) e comparar acurácia por campo,
abstenção, custo e latência; o vencedor vira o provedor de tudo. Se só um provedor for contratado, a
inclinação por custo-qualidade do modelo grande é levemente para a Anthropic, com a ressalva de que a
recomendação foi feita pelo Claude Code, um modelo da própria Anthropic (conflito de interesse declarado).

**Custo projetado.** Com o tamanho medido das chamadas (`scripts/medir_tamanho_dos_pedidos.py`), uma interpretação custa
de US$ 0,004 (GPT-5-mini) a US$ 0,035 (GPT-5.4), e o plano de avaliação inteiro com um provedor fica na casa de
US$ 30 a 40. Detalhe e cenários em `docs/avaliacao.md`, seção 12.

**Triagem e seleção (decisão do dono do projeto, 2026-09-24).** Correção do levantamento acima: a linha atual da OpenAI é a
família GPT-6 (`gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`); o GPT-5.4 é de geração anterior. Dos 27 modelos à venda
nos dois provedores preferidos, a regra de corte (geração anterior; linha atual acima de US$ 4 / 20) deixa 5 para
testar: `gpt-6-sol`, `gpt-6-luna`, `claude-opus-5-5`, `claude-sonnet-5` e `claude-haiku-4-5`. Teto da comparação:
US$ 25. Os cortados podem ser testados no fim do projeto, se algum resultado pedir. Gráfico e tabela em
`docs/avaliacao.md`, seção 12.

**Decisão:** o provedor e os modelos grande e pequeno saem da medição dos 5 (B3 nas mesmas 30 planilhas).

**Confirmado pelo dono do projeto (2026-09-25), depois da medição (EXP-008):** `MODELO_GRANDE=claude-sonnet-5` (maior acurácia por campo, 84,4%, a US$ 0,056 por planilha) e `MODELO_PEQUENO=gpt-6-luna` (US$ 0,002 por planilha, para as tarefas simples, como o classificador do guardrail). Dois provedores, um por papel: o cliente isolado (ADR-36) escolhe o provedor pelo nome do modelo (`services/provedores_de_ia.py`). Teto de gasto por sessão: US$ 10 (`TETO_DE_GASTO_USD`).

**Resultado da medição (2026-09-25, US$ 6,21).** Acurácia por campo nas 30 planilhas: `claude-sonnet-5` 84,4% (IC 81,1–87,5%),
`claude-opus-5-5` 82,3%, `claude-haiku-4-5` 81,6%, `gpt-6-sol` 77,6%, `gpt-6-luna` 76,3%; B0 53,4%. 0 respostas fora
do contrato. O Sonnet ficou acima dos dois modelos da OpenAI com intervalos que não se cruzam; o Opus custou o dobro do
Sonnet sem acertar mais. Detalhe em `docs/avaliacao.md`, seção 12. **Escolha dos modelos do MVP: pendente do dono do
projeto.**

---

## C. Etapas determinísticas

<a id="adr-12"></a>
### ADR-12 · Normalizador sem LLM ✅

| Opção | A favor | Contra |
|---|---|---|
| LLM converte os valores | Lida com formatos estranhos | Pode errar "R$ 5.200,50" por 100×; resultado muda entre execuções; custo por linha |
| **Regras a partir do tipo do campo (ADR-04)** | Reproduzível, sem custo, auditável | Formato inconclusivo precisa de humano |

**Decisão.** Com o mapeamento aprovado, a conversão é consequência do tipo. Formato inconclusivo
(01/02 é 1º de fevereiro ou 2 de janeiro?) vira pendência, nunca chute.
**Como comprovamos.** Golden por arquivo; "R$ 5.200,50" e "5200.5" viram o mesmo valor; zeros à
esquerda preservados. **Origem.** §4.

<a id="adr-13"></a>
### ADR-13 · Validador: regras decidem, LLM só explica ✅

| Opção | A favor | Contra |
|---|---|---|
| LLM valida | Flexível | Bloqueio de pagamento dependeria de um modelo probabilístico |
| **Regras decidem; LLM transforma o achado em linguagem clara** | Bloqueio sempre explicável e reproduzível | Regras precisam ser escritas e mantidas |

**Decisão.** Achados em BLOQUEANTE, ALERTA e AVISO, sempre por regra; o LLM só explica, sem mudar o
status. **Como comprovamos.** Erros injetados aparecem na linha certa; precisão e recall das
validações. **Origem.** §4.

<a id="adr-14"></a>
### ADR-14 · Enquadramento de renda por mediana do cargo ✅

**Contexto.** Empresas às vezes informam renda muito acima ou abaixo do esperado, por erro ou
possível fraude. O arquivo é uma carga inicial: **não existe salário anterior** para comparar.

| Opção | A favor | Contra |
|---|---|---|
| Média e desvio-padrão do cargo | Conhecido | Um único valor extremo puxa a média e esconde o erro |
| **Mediana + MAD do cargo** | Não se deixa puxar por extremos; explicável em uma frase | Precisa de amostra mínima por cargo |
| Isolation Forest (scikit-learn) | Detecta padrões combinados | Caixa-preta: difícil dizer por que alertou |
| Modelo supervisionado de risco | Mais preciso | Não há exemplos rotulados de fraude |

**Decisão.** Mediana + MAD por cargo e tipo de renda (CLT e pró-labore separados); tabela de
referência quando a amostra é pequena; nas inclusões, os colegas já homologados são a referência.
Resultado é **alerta**, nunca acusação.

**Por quê.** A mensagem "renda 6,8× a mediana do cargo" é entendida pela empresa e pela banca.

**Trade-off aceito.** Detecta só distância do padrão do cargo, não combinações sutis.

**Como comprovamos.** Outliers injetados viram alerta. As resoluções humanas (erro, confirmado,
suspeito) são guardadas como rótulos para um futuro modelo de risco (próximos passos).

**Origem.** Negócio + técnica, 2026-09-23.

---

## D. Agentes e orquestração

<a id="adr-15"></a>
### ADR-15 · LangGraph para orquestrar ✅

| Opção | A favor | Contra |
|---|---|---|
| Python puro | Controle total | Pausar, gravar estado e retomar teriam de ser reinventados |
| Frameworks de "equipes de agentes" que conversam | Rápidos para multiagente livre | Pouco controle de estados e de pausas humanas; menos previsíveis |
| **LangGraph** | Estados e transições explícitos; pausa (interrupt) e retomada com checkpoint em SQLite; suporta supervisor e handoff | Curva de aprendizado; integração com o Streamlit precisa ser provada |

**Decisão.** LangGraph. **Por quê.** O human-in-the-loop exige pausar o fluxo, esperar dias se for
preciso e retomar do mesmo ponto, e o mesmo framework cobre o supervisor e o handoff.
**Trade-off aceito.** O Streamlit reexecuta a página a cada clique: pausa e retomada são o maior risco
técnico. **Como comprovamos.** Spike da Fase 0: pausar, recarregar a página e retomar.
**Origem.** §8, §12.

<a id="adr-16"></a>
### ADR-16 · Onde o humano decide ✅

> **Alterado pelo [ADR-118](#adr-118) (2026-09-28):** nas pendências (Acompanhar e Cadastrar), a mensagem da empresa
> na conversa com a IA é a decisão humana: a IA aplica na hora, presa ao campo e à linha da pendência, com Desfazer.
>
> **Alterado pelo [ADR-115](#adr-115) (2026-09-28):** a aprovação dos textos do Endomarketing passou a ser do
> especialista do banco, que confere e publica; a empresa só baixa o que foi publicado.

| Opção | A favor | Contra |
|---|---|---|
| Automação total | Rápida | Sem responsável por decisões sensíveis |
| Humano aprova tudo | Controle | Recria o trabalho manual que causa a desistência |
| **Humano em pontos definidos** | Controle onde há risco, fluidez no resto | Exige critério de "ambíguo" e "sensível" |

**Decisão.** Humano decide em: mapeamento ambíguo ou crítico, correção de dado, justificativa de
alerta, homologação, e aprovação dos textos do Endomarketing. **Como comprovamos.** Teste "nada muda
sem clique"; métrica de homologação sem edição manual. **Origem.** §4, §7.

<a id="adr-17"></a>
### ADR-17 · Handoff do Assistente de Correção para o Interpretador ✅

**Contexto.** Na correção, a empresa pode revelar que uma coluna foi mal entendida ("essa 'Valor' é o
salário líquido").

| Opção | A favor | Contra |
|---|---|---|
| Recomeçar o processamento | Simples | A empresa refaz tudo; aumenta a desistência |
| Empresa edita o mapeamento à mão | Direto | Volta ao trabalho técnico que queremos evitar |
| **Assistente passa o controle ao Interpretador** | A informação da conversa corrige o mapeamento | Interação entre agentes precisa de limites |

**Decisão.** O Assistente decide chamar `solicitar_remapeamento`; o novo mapeamento volta ao aceite
humano e segue para normalização e validação; há limite de handoffs. **Como comprovamos.** Teste
"a coluna Valor é o salário líquido". **Origem.** Dono do projeto, 2026-09-23.

<a id="adr-18"></a>
### ADR-18 · Consultor como supervisor de 3 subagentes 🧪

> **Alterado pelo [ADR-117](#adr-117) (2026-09-28):** a aplicação passou a usar o **agente único**; o supervisor fica no código como o outro braço da comparação (ADR-60).

**Contexto.** O especialista do banco faz perguntas que cruzam visões: "onde concentro esforço no
próximo mês e quanto isso rende?".

| Opção | A favor | Contra |
|---|---|---|
| **Agente único** com todas as ferramentas | Mais barato e rápido | Prompt e ferramentas demais num só agente; pode errar mais em perguntas compostas |
| **Supervisor + subagentes** (Planejamento, Projeção Financeira, Situação da Integração) | Cada subagente focado; pergunta composta é dividida | Mais chamadas ao LLM |
| Agentes conversando livremente | Flexível | Imprevisível e caro |

**Decisão.** Supervisor + 3 subagentes, e **as duas primeiras opções são comparadas** nas mesmas
perguntas golden. **Por quê.** É onde a tarefa se divide naturalmente. **Trade-off aceito.** Se o
agente único empatar com menor custo, isso fica registrado como resultado.
**Como comprovamos.** Exatidão numérica, custo e latência, agente único × supervisor.
**Origem.** Dono do projeto, 2026-09-23.

<a id="adr-19"></a>
### ADR-19 · Endomarketing como agente único com RAG ✅

> **Alterado pelo [ADR-115](#adr-115) (2026-09-28):** o agente continua único e com o catálogo da empresa, mas quem
> gera é o especialista do banco, que escolhe os benefícios de cada material e publica; a empresa não gera nem aprova,
> só baixa e divulga os publicados.

**Contexto.** O banco não faz oferta ativa para quem não é correntista; quem orienta o funcionário é
a empresa. Ela precisa de material sobre os benefícios que o banco definiu para ela.

| Opção | A favor | Contra |
|---|---|---|
| Material fixo, igual para todas | Simples | Não reflete o pacote de cada empresa |
| **Agente com RAG no catálogo da empresa** | Material sob medida, com fontes | Risco de inventar condição de produto |
| Supervisor + subagentes | — | Uma tarefa e uma ferramenta principal: só custo extra |

**Decisão.** Agente único; catálogo em Markdown por empresa, mantido pelo banco; cada afirmação cita a
fonte; recusa quando a informação falta; a empresa aprova antes de usar. **Por quê.** É o uso mais
clássico de RAG no projeto (muitos documentos em texto, que mudam e são filtrados por empresa).
**Como comprovamos.** Fidelidade às fontes, hit@k, recusa e isolamento. **Origem.** Dono do projeto,
2026-09-23.

<a id="adr-20"></a>
### ADR-20 · Ferramentas fechadas, sem SQL livre ✅

| Opção | A favor | Contra |
|---|---|---|
| LLM escreve SQL (text-to-SQL) | Responde qualquer pergunta | Pode ler dados indevidos, errar a conta ou alterar dados |
| **Ferramentas fechadas com filtros tipados** | Cada acesso é autorizado e testável | Pergunta nova pode exigir ferramenta nova |

**Decisão.** Cada agente só chama as ferramentas do seu papel (allowlist); autorização checada no
serviço de dados, não no prompt. **Como comprovamos.** Tentativa de SQL bloqueada; subagente não
chama ferramenta de outro papel. **Origem.** §4, §7.

---

## E. Dados e negócio

<a id="adr-21"></a>
### ADR-21 · Dados 100% sintéticos, gerados com seed ✅

| Opção | A favor | Contra |
|---|---|---|
| Dados reais anonimizados | Realistas | Risco de reidentificação; exige aprovação |
| Dados públicos | Disponíveis | Não existem folhas de pagamento públicas com esse formato |
| **Gerador sintético com seed fixa** | Reproduzível; erros injetados com gabarito (golden) | Realismo depende do gerador |

**Decisão.** Gerador com seed; vocabulário de teste separado do de treino antes de qualquer geração.
**Como comprovamos.** Mesma seed, mesmos dados; teste que garante vocabulário de teste fora do treino.
**Origem.** §14.

<a id="adr-22"></a>
### ADR-22 · Layout fictício com ~44 campos ✅

| Opção | A favor | Contra |
|---|---|---|
| ~10 campos (plano) | Menos trabalho | Irreal; o dicionário B0 quase resolveria sozinho |
| Copiar o layout real | Fiel | Material interno |
| **~44 campos fictícios na escala e nos grupos do real** | Ambiguidades reais (endereço residencial × comercial, admissão × efetivação, salário × PLR) | Mais dados para gerar |

**Decisão.** Grupos: titular, documento, endereço residencial, telefones, e-mails, cadastro
empresarial, renda, endereço comercial; benefícios e PLR como campos opcionais. **Origem.** Negócio,
2026-09-23.

<a id="adr-23"></a>
### ADR-23 · Carga inicial + inclusões; desligamentos fora ✅

| Opção | A favor | Contra |
|---|---|---|
| Só carga inicial | Simples | Cada contratado não informado vira um novo falso não folha |
| **Inicial + inclusões, tipo definido por regra** | Cobre a vida real; a empresa não escolhe nada | Regras de duplicidade entre cargas |
| Incluir desligamentos | Completo | O banco já detecta quando o salário deixa de cair |

**Decisão.** Empresa sem funcionários homologados → INICIAL; com → INCLUSAO. Desligamentos fora.
**Pendente para depois:** funcionário que troca de empresa. **Origem.** Negócio, 2026-09-23.

<a id="adr-24"></a>
### ADR-24 · Reaproveitar o mapeamento homologado nas inclusões ✅

| Opção | A favor | Contra |
|---|---|---|
| Chamar o LLM a cada arquivo | Simples | Custo e espera repetidos; empresa reaprova o que já aprovou |
| **Reusar o mapeamento aprovado quando as colunas são as mesmas** | Sem custo de LLM; sem nova aprovação | Precisa detectar mudança de colunas |

**Decisão.** Colunas iguais → mapeamento reaproveitado; só colunas novas ou diferentes vão ao LLM.
**Como comprovamos.** Painel Técnico mostra a inclusão sem chamada ao LLM. **Origem.** Técnica,
2026-09-23.

**Correção (2026-09-25, auditoria da seção 10).** Desde a avaliação do banco (ADR-69, passo 15), o aceite da empresa
não é mais o fim: o banco pode devolver o envio. Mas o reuso continuava valendo a partir do aceite da empresa, e a tela
dizia "as colunas são as de um envio que o banco já aprovou", o que podia ser falso (envio devolvido ou descartado).
Agora `mapeamentos.ultimo_aprovado` só considera mapeamentos de envios **HOMOLOGADOS** (aprovados pelo banco), e o aviso
é sempre verdadeiro. Teste: `tests/test_interpretador.py::test_sem_a_aprovacao_do_banco_nao_ha_reuso`.

<a id="adr-25"></a>
### ADR-25 · Motor determinístico de planejamento, sem ofertas ✅

| Opção | A favor | Contra |
|---|---|---|
| LLM calcula as oportunidades | Flexível | Números inventados; não auditável |
| Motor gera listas de pessoas para ofertas | Uso comercial direto | Contraria a finalidade dos dados (ADR-28) |
| **Motor determinístico com números agregados para planejamento** | Auditável; responde o que o especialista precisa | Não serve para campanhas individuais |

**Decisão.** O motor responde: quantas contas abrir, onde, novos × já correntistas, ganho projetado.
Só agregados; a tabela por funcionário existe apenas internamente, para rastrear os números.
**Como comprovamos.** Contagens batem com o golden; nenhuma saída expõe dado individual.
**Origem.** §5 + dono do projeto, 2026-09-23.

<a id="adr-26"></a>
### ADR-26 · Premissas financeiras parametrizáveis, sem taxa padrão ✅

| Opção | A favor | Contra |
|---|---|---|
| Valores fixos no código | Simples | Mudar premissa exige deploy; não fica registrado |
| **Tabela versionada, editada pelo banco** | Cada projeção registra a versão usada | Uma tela a mais |
| Taxa de conquista padrão | Projeção sempre pronta | Projeta ganho com uma taxa que ninguém escolheu |
| **Taxa sempre informada pelo especialista** | Conservador e explícito | Um passo a mais na simulação |

**Decisão.** Valores iniciais do business case (MOB folha R$ 2.090,62; não folha R$ 1.724,00;
cliente novo R$ 2.090,62; 12 meses). Correntista recuperado = n × (folha − não folha); não
correntista = n × taxa × MOB de cliente novo. Sem taxa, a simulação é recusada e o Consultor pede
a taxa. **Origem.** Dono do projeto, 2026-09-23.

<a id="adr-27"></a>
### ADR-27 · Região, segmento e ciclo de vida ✅

**Decisão.** Região = **endereço comercial** (onde o banco precisa estar para abrir as contas; o
residencial responderia "qual agência fica perto de casa"). Segmento = **filtro**, sempre lido da base
oficial, nunca inferido pelo salário. **Ciclo de vida e portabilidade saem**: com carga inicial e sem
desligamentos, não há eventos para acompanhar. **Origem.** Dono do projeto, 2026-09-23.

---

## F. Privacidade, ética e segurança

<a id="adr-28"></a>
### ADR-28 · Três finalidades para os dados (LGPD) ✅

**Premissa da área de negócio** (em produção, validada pelo jurídico): o contrato banco × empresa
autoriza (1) vincular o CPF à base de funcionários e (2) a análise de risco da empresa e do
funcionário. (3) Oferta ativa só para **correntista com autorização**, dada na abertura da conta.
Ser cliente é ser correntista.

| Opção | A favor | Contra |
|---|---|---|
| Uso comercial livre dos dados da folha | Máximo aproveitamento | Fere a finalidade; risco regulatório e de reputação |
| **Finalidades separadas + marcação `correntista` e `autoriza_oferta_ativa`** | Recuperar o falso não folha é reconhecer vínculo, não vender | Parte do potencial fica com a empresa (endomarketing), não com o banco |

**Como comprovamos.** Teste: `autoriza_oferta_ativa` só com `correntista`; nenhuma saída individual.

<a id="adr-29"></a>
### ADR-29 · Campos proibidos para uso comercial ✅

| Opção | A favor | Contra |
|---|---|---|
| Prometer no documento que o motor não usa atributos sensíveis | Nenhum esforço | Promessa não testada |
| Remover os campos do cadastro | Elimina o risco | Os campos são necessários para vínculo e risco |
| **Marcação `uso_comercial_permitido` por campo no parâmetro** | Regra configurável e testável | Uma coluna a mais no parâmetro |

**Decisão.** Sexo, estado civil, nacionalidade e data de nascimento = N. O motor só lê campos com S.
Por minimização, no layout v1 só ficam com S os campos de que o motor precisa: CPF e matrícula (para
cruzar com a base do banco), CNPJ, unidade de trabalho e endereço comercial (região).
**Como comprovamos.** Teste de colunas proibidas. **Origem.** §7 + dono do projeto, 2026-09-23.

<a id="adr-30"></a>
### ADR-30 · Número agregado com mínimo de pessoas (sigilo bancário) 🔁

> **Revisto pelo [ADR-102](#adr-102) (2026-09-27):** a empresa passa a ver a conta de cada funcionário dela (agência,
> número e data de abertura), com o consentimento dado na abertura da conta; o mínimo de pessoas saiu. Continuam só
> em agregado o Consultor e o motor de planejamento do banco.
>
> **Alterado pelo [ADR-115](#adr-115) (2026-09-28):** o total de funcionários sem conta, que o Endomarketing mostrava
> à empresa, passou a ser uma sugestão para o especialista do banco (gerar o lembrete) no Portal Interno.

| Opção | A favor | Contra |
|---|---|---|
| Não mostrar nada à empresa | Sem risco | A empresa não dimensiona a comunicação interna |
| Mostrar o número exato sempre | Útil | Numa empresa pequena, o número quase identifica as pessoas |
| **Só no nível da empresa, com mínimo de pessoas** | Útil e protege empresas pequenas | Abaixo do mínimo, a informação é menos precisa |

**Decisão.** Agregado só da empresa inteira; abaixo do mínimo (parâmetro, inicial 10) mostra "menos
de 10"; nunca identifica ninguém. Premissa a validar com o jurídico. **Origem.** Dono do projeto,
2026-09-23.

<a id="adr-31"></a>
### ADR-31 · Mascaramento antes do LLM 🔁

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** com a IA pelo AWS Bedrock (ADR-96), a IA vê os dados reais e a máscara
> saiu do caminho da IA. Continua valendo: o conteúdo do arquivo vai delimitado e é tratado como dado, nunca como
> instrução; os registros (auditoria, telemetria) continuam sem dado pessoal.

| Opção | A favor | Contra |
|---|---|---|
| Enviar o arquivo completo ao LLM | Máximo contexto | Dado pessoal saindo para um provedor externo |
| **Só cabeçalhos e amostras mascaradas** | Minimização (LGPD) | Menos contexto para casos raros |

**Decisão.** CPF, salário, endereço e demais campos marcados como sensíveis são mascarados em prompts
e logs; o conteúdo do arquivo é delimitado e tratado como dado, nunca como instrução.
**Como comprovamos.** Teste de mascaramento; célula "ignore as instruções" não muda o resultado.
**Origem.** §7.

<a id="adr-32"></a>
### ADR-32 · Login com cadastro de usuários por perfil ✅

| Opção | A favor | Contra |
|---|---|---|
| Perfil escolhido na tela (simulado) | Simples | Não prova isolamento nenhum |
| Login social (OIDC: Google, Microsoft) | Sem senhas próprias | Não carrega perfil nem empresa; exige configurar provedor de identidade |
| **Usuário e senha com cadastro (perfil e empresa)** | O perfil vem do cadastro; prova o isolamento | Senhas a gerenciar (hash, secrets) |

**Decisão.** Tabela `usuarios` com `senha_hash`, `perfil` e `empresa_id`; um usuário por papel na
demo. Na máquina local, o script de criação **pergunta as senhas na tela** e não as grava em arquivo;
no servidor, elas vêm dos segredos da hospedagem. Na Fase 1, uma tela **Usuários** (perfil BANCO)
permite cadastrar, redefinir senha e desativar, como na vida real, em que o banco cria o acesso da
empresa ao fechar o contrato; cada usuário pode trocar a própria senha. Senha com no mínimo 8
caracteres; usuário desativado não entra, mas o histórico é preservado. Cada tela confere o perfil ao
abrir (não basta esconder do menu), e um teste abre todas as telas com todos os perfis. **Como comprovamos.** Acesso sem login negado; Empresa A não vê a B. **Origem.** Dono do
projeto, 2026-09-23.

---

## G. Plataforma

<a id="adr-33"></a>
### ADR-33 · Streamlit como interface ✅

| Opção | A favor | Contra |
|---|---|---|
| **Streamlit** | Telas em Python, rápido de construir | Reexecuta a página a cada clique; não é para produção em escala |
| FastAPI + React | Arquitetura de produção | Dobra o esforço; a banca avalia a IA, não o frontend |
| Gradio | Ótimo para demo de um modelo | Fraco para aplicação com várias telas e perfis |

**Decisão.** Streamlit, com a lógica isolada em `services/`, `agents/` e `opportunities/`, para
trocar a interface no futuro sem reescrever regras. As telas ficam em `telas/`, montadas pelo
`st.navigation` conforme o perfil. O nome `pages/`, previsto no plano, foi evitado porque o Streamlit
trata essa pasta de forma especial (cria um menu automático com todas as telas, para qualquer usuário). **Origem.** §8.

<a id="adr-34"></a>
### ADR-34 · SQLite como banco 🔁 (substituído pelo ADR-67)

| Opção | A favor | Contra |
|---|---|---|
| **SQLite** | Um arquivo, zero configuração; também guarda os checkpoints do LangGraph | Um escritor por vez; não escala para muitos usuários |
| PostgreSQL | Produção | Exige servidor |
| DuckDB | Excelente para análise | Não é feito para estado transacional da aplicação |

**Decisão.** SQLite no MVP; PostgreSQL em produção; DuckDB como evolução analítica. **Origem.** §8, §20.

**Revisto em 2026-09-25** (o dono do projeto perguntou se valia usar o PostgreSQL já, por ter um instalado): mantido o SQLite no
MVP. Medido: a troca revisaria 15 arquivos (91 comandos SQL), 8 comandos só do SQLite, 5 PRAGMA, o ponto de salvamento
do LangGraph e 24 arquivos de teste, e tiraria a reprodutibilidade sem servidor de banco. Critérios de troca e plano
em `docs/banco_de_dados.md`.

<a id="adr-35"></a>
### ADR-35 · Docker em container com processo contínuo ⏳

| Opção | A favor | Contra |
|---|---|---|
| Plataforma serverless (ex.: Vercel) | Simples | O Streamlit precisa de processo contínuo e estado; não atende |
| Streamlit Community Cloud / Hugging Face Spaces | Gratuito | Menos controle de disco e segredos |
| **Render ou Railway (container Docker)** | Disco persistente, secrets, mesmo container da máquina local | Custo mensal pequeno |

**Decisão.** Docker obrigatório (roda igual no servidor e na máquina do avaliador). A certificação
permite qualquer servidor. O desenvolvimento acontece na máquina local; **na banca, a demo roda
publicada numa hospedagem com login**, e a máquina local é o plano B. O avaliador recebe as duas
formas (o enunciado aceita instruções de execução **ou** link). Primeira publicação de ensaio no fim da
Fase 1, para descobrir problemas de servidor cedo; publicação final na Fase 15. **Pendente:** Render
ou Railway. **Origem.** §8.

<a id="adr-36"></a>
### ADR-36 · Cliente de LLM isolado, modo MOCK e proteção de custo ✅

| Opção | A favor | Contra |
|---|---|---|
| Chamar a API do provedor em cada módulo | Direto | Trocar de provedor exige mexer em tudo; sem controle central de custo |
| **`llm_client.py` único, com modo MOCK** | Troca de provedor num lugar; demo e testes sem chave | Uma camada a mais |

**Decisão.** Todo acesso ao LLM passa por `llm_client.py`. Link público protegido por login, limite
por sessão, teto de gasto no provedor e queda automática para MOCK. Chaves só no servidor.
**Como comprovamos.** Testes rodam em MOCK; limite atingido → MOCK sem erro. **Origem.** §8, §13.


<a id="adr-38"></a>
### ADR-38 · Defesa em camadas contra prompt injection ✅

> **Alterado pelo [ADR-147](#adr-147) (2026-09-30):** a segunda opinião das mensagens de fora passa do modelo pequeno
> para o detector de ataques do Bedrock Guardrails (`InvokeGuardrailChecks`), com um tempo máximo por checagem. A lista
> de padrões continua na frente, e a KB do Endomarketing fica só com a lista.

**Contexto.** Texto externo entra no sistema por cinco portas: células e cabeçalhos do arquivo, chat
com o Assistente de Correção, documentos do catálogo, perguntas ao Consultor e o histórico de
mapeamentos que alimenta o RAG. Nenhum modelo separa instrução de dado com garantia total.

| Opção | A favor | Contra |
|---|---|---|
| Só instruir o modelo ("ignore comandos no texto") | Trivial | Contornável; é a defesa mais fraca |
| Filtro de palavras que bloqueia o arquivo | Simples | Falso positivo trava a empresa; ataque criativo passa |
| **Defesa em camadas, limitando o que uma injeção consegue fazer** | Mesmo que a injeção funcione, o dano é contido | Mais controles para construir e testar |

Para a camada de detecção, também havia opções:

| Detector | A favor | Contra |
|---|---|---|
| **Lista de padrões** ("ignore as instruções", "você agora é", "aprove") | Barato, instantâneo, explicável | Um disfarce novo passa |
| **Classificador por modelo pequeno** ("este texto contém uma ordem? sim/não") | Pega disfarces que a lista não pega | Custo e latência por chamada; também pode errar |
| **Os dois, com a taxa de acerto medida** | Um cobre o ponto cego do outro; a escolha final vem do teste | Duas peças para manter |

**Decisão.** Nove camadas, sendo a detecção concentrada num componente próprio, o **Guardrail de
injeção** (`services/guardrail_injecao.py`), que é a porta de entrada e de saída de todo texto
externo:

- **Entrada.** Lista de padrões + classificador por modelo pequeno (em modo MOCK, só a lista).
  Trecho suspeito vindo de **célula ou cabeçalho** é **substituído** por `[conteúdo removido pelo
  guardrail]` antes de chegar ao LLM e vira AVISO para a empresa. Mensagem suspeita no **chat** ou
  pergunta ao Consultor segue, mas marcada como suspeita. Documento do catálogo suspeito é
  **recusado no upload**. Todo acionamento gera um `AgentRunEvent` no Painel Técnico.
- **Saída.** Confere se a resposta está no schema, se os campos propostos existem no parâmetro, se os
  números vieram das ferramentas e se as afirmações do Endomarketing têm fonte. O que falhar é
  descartado.

As demais camadas: (1) minimização: o LLM vê só cabeçalhos e amostras mascaradas; (2) delimitação:
conteúdo externo entre marcadores, tratado como dado; (3) ferramentas fechadas, com permissão vinda
do usuário logado; (4) etapas críticas sem LLM; (5) aprovação humana; (6) proteção do RAG: só
mapeamentos homologados por humano entram no histórico, como pares estruturados, e o catálogo só é
enviado pelo perfil BANCO.

**Por quê.** A pergunta certa não é "a injeção pode acontecer?", mas "o que ela consegue fazer se
acontecer?". O guardrail reduz as tentativas que chegam ao LLM; as outras camadas garantem que, se
uma passar, no pior caso ela muda o texto de uma explicação. Não altera dado, não acessa outra
empresa, não inventa número e não homologa nada.

**Trade-off aceito.** A detecção gera alguns falsos positivos. Por isso, no arquivo, o trecho é
removido e a empresa é avisada, mas o processamento não trava; no chat, a conversa segue marcada.

**Como comprovamos.** Um conjunto de tentativas de ataque (e de textos normais parecidos) mede a
taxa de detecção e de falso alarme da lista, do classificador e dos dois juntos (Fase 14). Testes
adversariais da Fase 13: célula e cabeçalho com instrução, resposta maliciosa no chat, documento do
catálogo com instrução, pergunta pedindo dados de outra empresa, tentativa de envenenar o histórico.
**Origem.** §7 + dono do projeto e técnica, 2026-09-24.


<a id="adr-39"></a>
### ADR-39 · Processamento em andamento guardado na URL ✅

**Contexto.** O fluxo pausa esperando uma pessoa (ADR-15). Para retomar, a tela precisa saber qual
processamento estava aberto. O plano previa guardar esse identificador no `st.session_state` do
Streamlit. O spike da Fase 0 mostrou o problema: **o `st.session_state` se perde quando a página é
recarregada**, porque o navegador abre uma sessão nova.

| Opção | A favor | Contra |
|---|---|---|
| Só `st.session_state` (plano) | Simples | Recarregar a página "esquece" o processamento; o fluxo fica órfão |
| Cookie no navegador | Invisível para a pessoa | Exige componente extra; comportamento varia entre navegadores |
| **Identificador na URL** (`?processamento=...`), com o estado no checkpointer SQLite | Sobrevive ao recarregamento; o link pode ser reaberto depois | O identificador aparece na barra de endereço |

**Decisão.** O identificador do processamento fica na URL; o estado do fluxo, no checkpointer SQLite.
**Por quê.** Recarregar a página é o cenário de teste do plano (§17) e precisa funcionar sem truque.
**Trade-off aceito.** O identificador é visível. Ele é aleatório, não contém dado pessoal, e o acesso
continua exigindo login com o perfil certo (a checagem de que o processamento pertence à empresa do
usuário entra na Fase 8). **Como comprovamos.** Spike da Fase 0 e
`tests/test_spike_pausa_retomada.py`. **Origem.** Técnica, 2026-09-24 (Fase 0).


<a id="adr-40"></a>
### ADR-40 · Sessão lembrada por cookie: o F5 não desloga ✅

**Contexto.** No teste da Fase 1, o usuário notou que o F5 desloga. O Streamlit guarda o login na
memória da aba, e o F5 abre uma sessão nova (o mesmo fenômeno do ADR-39). Isso deixa a demo frágil e
cumpre só pela metade o teste do plano "recarregar a página no meio da correção retoma o fluxo".

| Opção | A favor | Contra |
|---|---|---|
| Aceitar: F5 = sair | Zero código; o mais seguro | Um F5 acidental na banca desloga; parece defeito |
| **Cookie de sessão com validade** | Comportamento de site normal; a demo fica robusta | Mais código e mais uma parte de segurança para testar |
| Login nativo do Streamlit (OIDC) | Mantém a sessão sem esforço | Já descartado no ADR-32: não carrega perfil nem empresa |
| Pacote de terceiros para cookies | Pronto para usar | Dependência extra; o Streamlit 1.64 já lê cookies e permite gravá-los com um script próprio |

**Decisão.** Ao entrar, o sistema gera um ingresso aleatório de 256 bits, guarda **só o hash SHA-256**
no banco (tabela `sessoes`) e grava o ingresso num cookie (`SameSite=Strict`, `Secure` em HTTPS)
com validade de **8 horas**. A cada abertura, o ingresso é conferido: existe, não venceu, não foi
cancelado e o usuário continua ativo. "Sair" cancela o ingresso no banco e apaga o cookie. Senha
redefinida pelo banco ou usuário desativado derruba todas as sessões da pessoa. Leitura com
`st.context.cookies` (nativo); gravação com um script curto escrito pelo sistema
(`st.html(..., unsafe_allow_javascript=True)`), sem pacote de terceiros.

**Por quê.** SHA-256, e não bcrypt: a senha é escolhida por uma pessoa e pode ser fraca, por isso usa
um hash lento; o ingresso tem 256 bits sorteados, e nenhuma tentativa em massa o adivinha.

**Trade-off aceito.** Gravado por script, o cookie não pode ser `HttpOnly` (invisível para
JavaScript). O risco é um script malicioso na página lê-lo; é mitigado porque o sistema não exibe
HTML vindo de usuários ou de arquivos, e o ingresso vence em 8 horas e morre no "Sair". Em produção,
o cookie seria gravado pelo servidor, com `HttpOnly`.

**Como comprovamos.** `tests/test_sessoes.py` (validade, cancelamento, usuário desativado, senha
redefinida, ingresso inventado ou em formato estranho, só hash no banco) e teste de login pela
entrada. No navegador: entrar, apertar F5 e continuar logado; "Sair" e voltar à tela de login.
**Origem.** Teste do usuário na Fase 1 + recomendação técnica aprovada, 2026-09-24.

---

## H. Avaliação

<a id="adr-37"></a>
### ADR-37 · Experimento controlado B0–B5 com significância estatística ✅

| Opção | A favor | Contra |
|---|---|---|
| Avaliar nos 6 arquivos da demo | Rápido | Amostra pequena demais para concluir qualquer coisa |
| Avaliar "no olho" | Nenhum | Não convence uma banca técnica |
| **≥300 conjuntos de cabeçalhos, vocabulário de teste nunca visto no treino, IC 95% por bootstrap** | Conclusões com significância | Exige gerador e dataset |

**Decisão.** B0–B3 obrigatórios, B4–B5 diferenciais; mesmo conjunto de teste para todos; métricas
por campo; consistência em 5 execuções; resultado negativo também é registrado. A mesma lógica vale
para o Consultor (ADR-18) e o Endomarketing (fidelidade às fontes). **Origem.** §4, §10.

<a id="adr-41"></a>
### ADR-41 · Baseline B0 calibrado numa validação tirada do treino, nunca na prova ✅

O B0 (sinônimos + RapidFuzz, sem IA) tem dois "botões": o comparador de textos e o limite de
semelhança. Quem os escolhe olhando a prova infla o resultado, como quem estuda com o gabarito.

| Opção | A favor | Contra |
|---|---|---|
| Fixar os botões "no chute" (ex.: `ratio` 85) | Simples | B0 artificialmente fraco (25% por campo): a IA "ganharia" de um espantalho, e a banca percebe |
| Escolher pelo resultado na prova | O melhor número | Vazamento: a prova deixa de medir a capacidade de generalizar |
| **Separar 20% dos termos de TREINO como validação e escolher ali** | B0 honesto e forte; a prova continua intocada | Um script a mais (`scripts/calibrar_b0.py`) |

**Decisão.** `calibrar_b0.py` testa 4 comparadores x 6 limites em 300 cabeçalhos feitos com os termos
de validação (que o B0 não conhece) e grava a melhor combinação pelo **acerto geral** em
`data/avaliacao/calibracao_b0.json`. Resultado: `WRatio` com limite 75 (57,6% na validação). Só
depois a prova foi rodada, uma vez: **acurácia por campo 50,9% (IC 95% 49,5% a 52,2%), acerto geral
52,1%, abstenção: recall 59,4% e precisão 47,7%**, 7,5 ms e custo zero por arquivo
(`data/avaliacao/resultados/B0.json`).

**Leitura do resultado.** O B0 acerta metade dos campos e não sabe reconhecer ambiguidade: mapeia
"Proventos" para algum campo com confiança em vez de pedir ajuda. É exatamente aí que o LLM (B1 a
B5) precisa provar que vale o custo.

**Trade-off aceito.** A validação tem menos termos que o treino inteiro, então os botões escolhidos
podem não ser os ótimos para o vocabulário completo. Preferimos isso a qualquer contato com a prova.

**Como comprovamos.** `tests/test_avaliacao.py`: validação sem termos da prova nem do ajuste; B0 lê a
calibração gravada; nada da prova nos exemplos de treino; geração reprodutível; métricas e IC.
**Origem.** Fase 2, bloco 3, 2026-09-24 (modo despertador).

<a id="adr-42"></a>
### ADR-42 · Embeddings locais e ajustes da busca medidos nas consultas de teste ✅

**Contexto.** O RAG precisa transformar texto em números que representem o significado
(embeddings) para achar trechos parecidos com a pergunta, mesmo sem palavras em comum.

| Opção | A favor | Contra |
|---|---|---|
| Embeddings do provedor de LLM | Qualidade alta | Depende do provedor (ainda não escolhido), custa por chamada e manda texto para fora |
| `multilingual-e5-large` (2,2 GB) ou `mpnet-base` (1 GB), locais | Melhores em textos longos | Pesados para uma hospedagem simples (memória) |
| **`paraphrase-multilingual-MiniLM-L12-v2` via fastembed (220 MB, local)** | Multilíngue, sem PyTorch, sem chave, sem custo, roda em qualquer máquina | Versão comprimida: sensível a maiúsculas; menos precisa em textos longos |

**Decisão.** MiniLM multilíngue local, guardado em `storage/modelos/` (fora do Git). Quatro ajustes,
cada um motivado por um erro diagnosticado nas consultas de teste, e não por tentativa e erro:

1. **Tudo em minúsculas** (índice e pergunta): "Salario Mensal Bruto" e "salario mensal bruto"
   ficavam a 0,85 de distância, como assuntos diferentes; em minúsculas o modelo se comporta bem.
2. **Texto lido × texto comparado:** o agente lê o trecho com o caminho de origem; a busca compara só
   o assunto. Frases repetidas em todos os trechos ("foi homologada como") pesavam mais que o conteúdo.
   O mapeamento é comparado junto com a descrição do campo ("Vlr Salário: salário bruto mensal...").
3. **Diversidade no layout:** no máximo um trecho por campo. Cinco sinônimos de `valor_renda`
   empurravam para fora a regra de enquadramento de renda.
4. **k e corte pela medição** (`scripts/avaliar_rag.py` → `data/avaliacao/resultados/rag.json`):
   layout k=4 (hit@4 = 100%), catálogo k=2 (hit@2 = 100%); catálogo corta acima de 0,80 (respostas
   certas até 0,68; perguntas sem resposta a partir de 0,92).

**Achado honesto.** No layout, as distâncias das perguntas com e sem resposta se encostam
(0,587 × 0,588): a distância não serve para dizer "não encontrei". Ali quem se abstém é o
Interpretador (`NAO_MAPEADO`), medido nas Fases 4 e 14. O corte do layout (0,70) só descarta o que é
claramente outro assunto.

**Trade-off aceito.** 10 consultas por índice é pouco para afirmar muita coisa: os números orientam o
k e o corte, e a Fase 14 mede com mais perguntas. Os ajustes foram feitos olhando essas consultas;
por isso a Fase 14 usa perguntas novas.

**Como comprovamos.** `tests/test_rag.py`: as 10 consultas de cada índice, cada empresa só recebe o
próprio catálogo, documento fora da vigência não volta, busca sem empresa é recusada, nenhum CPF nos
índices, trecho começa pelo caminho de origem, seção longa dividida repetindo o título, um trecho por
campo. **Origem.** Fase 2, bloco 4, 2026-09-24 (modo despertador).

## I. Leitura do arquivo (Fase 3)

<a id="adr-43"></a>
### ADR-43 · Na leitura, toda célula vira texto; nada é convertido antes do Normalizador ✅

| Opção | A favor | Contra |
|---|---|---|
| Deixar o pandas adivinhar os tipos | Uma linha de código | `00123` vira `123`, CPF perde o zero, `01/02` vira fevereiro ou janeiro sem ninguém saber |
| **Tudo como texto, exatamente como veio; conversão só no Normalizador, com regra e teste** | Nada se perde nem muda em silêncio | O Normalizador tem mais trabalho (e é para isso que ele existe) |

**Decisão.** CSV: codificação descoberta (UTF-8, senão Windows-1252) e separador detectado; XLSX:
número e data do Excel viram texto, e a data lida como `AAAA-MM-DD` gera um aviso para a empresa.
Coluna gravada como número no Excel (onde os zeros à esquerda já se perderam antes do envio) é
sinalizada no perfil. O cabeçalho é achado por regra (primeira linha com ≥60% das colunas e maioria de
texto), porque há relatórios com título antes dele. Reenvio idêntico (mesmo hash SHA-256, mesma
empresa) não cria outro processamento. O original fica guardado intacto em `storage/uploads/`.
**Como comprovamos.** `tests/test_ingestao.py`: os 9 arquivos sintéticos lidos sem gabarito, com
cabeçalho, linhas, separador e codificação iguais aos do gabarito; CPF e matrícula intactos; data do CSV
não transformada; recusas; deduplicação. **Origem.** Plano, Fase 3; 2026-09-24 (modo despertador).

<a id="adr-44"></a>
### ADR-44 · Amostras para a IA: formato mascarado, categorias à mostra 🔁

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** as amostras passaram a ser os 3 primeiros valores diferentes da coluna,
> como estão no arquivo (`ingestao.amostras`, prompt `interpretador_v2`).

O Interpretador precisa ver o **jeito** dos dados para entender uma coluna, sem ver os dados de ninguém.

| Opção | A favor | Contra |
|---|---|---|
| Mandar valores reais | Máximo contexto | Dado pessoal saindo para um provedor externo |
| Não mandar amostra nenhuma | Zero risco | "Código" ou "Valor" ficam impossíveis de entender |
| Mascarar tudo | Seguro | "Analista, Vendedor" viraria "Xxxxxxxx": a IA perde a pista de que é o cargo |
| **Mascarar pelo formato (dígito → 9, letra → x) e mostrar só colunas de categorias** | Formato preservado (`999.999.999-99`, `R$ 9.999,99`); cargo, UF e tipo de renda visíveis | Uma coluna de texto livre com poucos valores repetidos apareceria (ex.: bairro numa empresa pequena) |

**Decisão.** Coluna é "de categorias" quando tem pelo menos 10 valores e no máximo 20% de valores
distintos: aí os valores reais aparecem, porque não identificam ninguém. Qualquer outra coluna mostra
só o formato mascarado. **Trade-off aceito.** O caso do bairro repetido; mitigado porque o nome da
pessoa e o CPF nunca têm poucos valores distintos. **Como comprovamos.** Teste: nenhuma amostra dos 9
arquivos contém CPF ou nome real; CPF mascarado só com 9; UF à mostra. **Origem.** ADR-31 aplicado; Fase 3.

## J. Agente Interpretador (Fase 4)

<a id="adr-45"></a>
### ADR-45 · Interpretador em MOCK que recebe o prompt de verdade, e caminhos de falha previstos ✅

**Contexto.** O provedor de LLM ainda não foi escolhido (ADR-11), mas o fluxo da empresa precisa
funcionar e ser testado de ponta a ponta.

| Opção | A favor | Contra |
|---|---|---|
| MOCK devolvendo um JSON fixo | Simples | Não testa prompt, contrato nem guardrail; não serve para arquivo novo |
| MOCK lendo o gabarito do arquivo | Demo "perfeita" | Usa a resposta certa; não funciona para arquivo enviado na hora |
| **MOCK que recebe o prompt montado e responde no contrato (dicionário do B0 + regras de ambiguidade)** | Todo o caminho roda igual ao real: prompt → resposta → contrato → guardrail → aceite | A qualidade é a do B0, não a de uma IA; e ele é rotulado MOCK em toda tela |

**Decisão.** O simulador lê o bloco `<arquivo_da_empresa>` do prompt e responde como um LLM responderia,
usando só o vocabulário de treino. Caminhos de falha: resposta fora do contrato → nova tentativa com o
erro; segunda falha → plano de emergência com as sugestões do dicionário, **todas** para confirmação
humana; sem o índice do RAG → configuração B2 (histórico inteiro no prompt), com aviso. Reuso (ADR-24):
coluna com o mesmo nome no último mapeamento **aprovado** da empresa, se o campo ainda existe no layout
vigente, não vai para a IA.

**Trade-off aceito.** Números do MOCK nunca entram na avaliação: B1 a B5 só com o provedor real.
**Como comprovamos.** `tests/test_interpretador.py`: Aurora mapeada como o gabarito; "Vencimentos" vira
AMBIGUO; saída inválida rejeitada e corrigida na segunda tentativa; duas falhas caem no plano de
emergência; guardrail de saída (campo inexistente, coluna e fonte inventadas, disputa pelo mesmo campo);
inclusão com as mesmas colunas não chama o LLM; só a coluna nova vai para o LLM; aceite exige decisão nas
ambíguas; modo LLM sem provedor avisa em vez de esconder. **Origem.** Fase 4, 2026-09-24 (modo despertador).

## K. Normalizador (Fase 5)

<a id="adr-46"></a>
### ADR-46 · Normalizador: converter só o que tem certeza; a dúvida vira decisão da empresa ✅

O ADR-12 decidiu que o Normalizador não usa LLM. Este registra **como** ele decide sem adivinhar.

| Situação | Opções | Decisão | Por quê |
|---|---|---|---|
| Data "01/09/2026" (dia e mês ≤ 12) | Supor DD/MM (padrão brasileiro) · pedir sempre à empresa · **olhar as outras datas do arquivo** | Convenção do **arquivo**: se alguma data de qualquer coluna tem dia > 12, vale para todas; se nenhuma desempata, a coluna fica pendente | Um sistema de RH exporta todas as datas do mesmo jeito. Supor seria arriscado; perguntar sempre, cansativo |
| CPF que o Excel guardou como número e perdeu o zero | Completar sempre · recusar sempre · **completar só se o dígito verificador confirmar** | Recompor só com o DV válido | O DV transforma o palpite em verificação |
| Matrícula que perdeu o zero | Completar com um tamanho padrão · **perguntar o número de dígitos** | Pendência da coluna; a empresa informa | Matrícula não tem dígito verificador: não há como confirmar |
| Número mal formado ("12,5.3") ou por extenso | Tentar interpretar · **não converter** | Só padrões exatos (1.234,56 ou 1,234.56); o resto vira pendência | Salário errado é pior que salário pendente |
| Valor fora da lista de um domínio | Aceitar como veio · **converter sinônimo conhecido, recusar o resto** | Lista em `data/contratos/dominios_v1.json` | O motor e os relatórios dependem de valores padronizados |

**Como é garantido.** Cada coluna recebe só operações da lista permitida (allowlist), derivadas do tipo do
campo e do mapeamento **aprovado**; operação ou coluna fora disso é recusada. Valor não convertido fica
vazio no registro e listado com o motivo; a conferência confere linhas, vazios e a soma dos salários.
**Como comprovamos.** `tests/test_normalizador.py`: os 9 arquivos da demo batem com o gabarito em valor e
identidade (exceções: só as células com erro injetado); "R$ 5.200,50" = "5200.5"; data ambígua vira
pendência e a decisão da empresa resolve; CPF recomposto só com DV; allowlist; soma dos salários.
**Origem.** Plano, Fase 5; 2026-09-24 (modo despertador).

## L. Validador (Fase 6)

<a id="adr-47"></a>
### ADR-47 · Severidade por regra, renda por "z robusto" e explicação só com os achados ✅

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** a explicação continua só com os achados, mas agora cada achado leva o
> valor que a regra encontrou (prompt `explicador_validacao_v2`). A severidade continua decidida pela regra.

O ADR-13 decidiu que as regras decidem e o LLM só explica; o ADR-14, mediana + MAD por cargo. Este
registra os números e as severidades.

| Regra | Severidade | Por quê |
|---|---|---|
| CPF/CNPJ com DV inválido, CNPJ de outra empresa, obrigatório vazio ou sem coluna, pessoa ou matrícula duplicada no arquivo, valor obrigatório não convertido, data de coluna sem decisão, nascimento no futuro, admissão antes do nascimento, renda zerada | BLOQUEANTE | Não dá para homologar um cadastro assim |
| Renda fora do padrão do cargo, CEP com dígitos faltando, admissão antes dos 14 anos, efetivação antes da admissão, matrícula já homologada para outra pessoa, valor opcional não convertido | ALERTA | Pode estar certo: a empresa corrige **ou justifica** |
| Telefone ou e-mail mal formado, funcionário já homologado (reenvio) | AVISO | Informativo; não impede a homologação |

**Renda.** "Z robusto" = distância até a mediana dividida por 1,4826 × MAD; acima de **3,5** é ALERTA
(limite clássico para esse tipo de medida). Com menos de **5 colegas** no mesmo cargo e tipo de renda,
vale a tabela de referência (60% a 160% da mediana). Nas inclusões, os colegas já homologados entram na
conta. A mensagem diz quantas vezes a mediana e pede justificativa; nunca fala em fraude.

**LLM.** Recebe só os achados (regra, severidade, campo, linha, mensagem), sem valores; devolve um resumo.
A severidade não passa por ele. A resolução de cada alerta (ERRO_CORRIGIDO, CONFIRMADO, SUSPEITO), com
justificativa obrigatória, é guardada como rótulo para um futuro modelo de risco.

**Achado sobre os dados sintéticos.** A primeira execução apontou 13 pessoas "admitidas antes dos 14
anos": o gerador sorteava nascimento e admissão sem relação. O gerador foi corrigido **sem mudar a
sequência do sorteio** (só 28 datas de nascimento mudaram; o resto dos dados ficou idêntico).

**Como comprovamos.** `tests/test_validador.py`: nos 9 arquivos da demo, o Validador acha **exatamente**
os erros injetados, na linha certa, e nada além (precisão e recall de 100% na demo); CPF inválido
bloqueia; renda 10× é alerta sem acusação; cargo com poucos colegas usa a referência; a explicação não
muda severidade nem recebe dado pessoal. **Origem.** Plano, Fase 6; 2026-09-24 (modo despertador).

## M. Correção assistida e homologação (Fase 7)

<a id="adr-48"></a>
### ADR-48 · Correção como pedido com clique, Assistente com lista fechada de ações e homologação com checksum ✅

**Opções.** (a) O Assistente de Correção edita o dado direto quando entende o que a empresa quis dizer;
(b) o Assistente só **propõe**, e o dado muda com o clique de uma pessoa.

**Decisão: (b).** Cada correção é um pedido (CorrectionRequest) com antes, depois, motivo, quem pediu,
quem aprovou e horário. Cancelar não muda nada; aplicar muda o dado e **revalida na hora**. O valor
novo passa pelas mesmas regras do Normalizador ("5.200,00" vira 5200.00; "cinco mil" é recusado).
Excluir uma linha repetida é uma correção como as outras. O original padronizado nunca é alterado: os
dados atuais são a padronização com as correções aplicadas por cima (auditoria completa).

**O Assistente.** O LLM escolhe **uma ação de uma lista fechada** (responder, explicar a regra, propor
correção, propor exclusão, preparar justificativa de alerta, pedir remapeamento), validada por contrato.
A mensagem da empresa passa pelo guardrail de injeção antes do LLM; as fontes do RAG vão junto da
explicação. A **única** ação executada na hora é o handoff para o Interpretador (ADR-17): ele não muda
dado, reinterpreta só a coluna citada, devolve o mapeamento ao aceite humano e apaga a padronização e a
validação antigas. Limite de **2 handoffs por arquivo**.

**Alertas.** A empresa corrige (rótulo ERRO_CORRIGIDO, gravado sozinho) ou justifica (CONFIRMADO ou
SUSPEITO, com texto obrigatório). Alerta justificado continua no relatório, marcado, e não trava mais.

**Homologação.** Só sem BLOQUEANTE e sem ALERTA em aberto, sempre revalidando antes. O arquivo final
(CSV `;`, UTF-8, campos na ordem do layout) leva só os registros autorizados: sem linhas excluídas e sem
quem já estava homologado na empresa. Checksum SHA-256 e relatório de qualidade (recebidos,
homologados, excluídos, corrigidos, justificados, avisos). Os funcionários entram em
`funcionarios_homologados`; o histórico recebe **só pares estruturados** (coluna → campo, empresa,
versão do layout) do mapeamento aprovado. Nada do chat e nenhuma célula viram conhecimento (ADR-38).

**Trade-off.** Mais cliques para a empresa do que uma correção automática; em troca, nenhuma edição
silenciosa, e cada mudança tem dono e motivo, o que o banco precisa para confiar no cadastro.

**Como comprovamos.** `tests/test_correcao.py` (19 testes): o pedido não muda o dado até o clique;
cancelar não altera nada; correção aplicada some com o erro na revalidação; o valor novo passa pelo
Normalizador; alerta justificado e rótulo ERRO_CORRIGIDO; o Assistente propõe, explica com fonte e recusa
injeção; "a coluna Vencimentos é o salário líquido" gera remapeamento (a coluna sai), novo aceite e
revalidação (falta a renda); limite de handoffs; homologação recusada com pendência; arquivo final com
checksum e sem a linha repetida; histórico só com pares aprovados; inclusão não repete quem já foi
homologado. **Origem.** Plano, Fase 7; 2026-09-24 (modo despertador).

## N. Orquestração (Fase 8)

<a id="adr-49"></a>
### ADR-49 · Fluxo da empresa em LangGraph: o grafo decide a próxima etapa, os serviços continuam donos das regras ✅

**Opções.** (a) Cada tela chama os serviços em sequência (como até a Fase 7); (b) um grafo LangGraph com
estados explícitos, pausas para a pessoa e ponto de salvamento por arquivo.

**Decisão: (b), ligando os serviços que já existem.** Nenhuma regra foi reescrita no grafo: cada etapa
chama um serviço (Interpretador, Normalizador, Validador, correções, homologação) e só decide **para onde
o arquivo vai**. Etapas: perfilar → recuperar_conhecimento → interpretar → aprovar_mapeamento (pausa) →
padronizar → validar → aguardar_correcao (pausa) ou aprovar_homologacao (pausa) → liberar_planejamento.
Cada etapa escreve o próximo passo no estado; as setas possíveis de cada uma ficam numa tabela
(`DESTINOS`), que também desenha o fluxo.

**Como fica seguro.**
- **Pausa e retomada:** ponto de salvamento SQLite com `thread_id = processamento_id` (o padrão provado
  no spike, ADR-15/39). Iniciar de novo não recomeça; retomar sem pausa à espera é recusado.
- **Estado sem dado pessoal:** só identificadores, situação, contagens, decisões de coluna e códigos.
- **Handoff:** se o Assistente devolveu o mapeamento ao aceite, qualquer resposta leva o fluxo de volta a
  `aprovar_mapeamento` (e conta um handoff).
- **Falha não vira sucesso:** etapa que quebra grava a execução como ERRO (só o tipo do erro) e o arquivo
  para em `aguardar_nova_tentativa`. Mais de **3** falhas: REJEITADO. Resposta fora do contrato do LLM já
  é tratada dentro do Interpretador (nova tentativa e plano de emergência, ADR-45); um tempo esgotado no
  provedor chega aqui como falha.
- **Limite de ciclos de correção:** **20** pedidos de revalidação; passou, REJEITADO ("reenvie o arquivo
  corrigido"). A rejeição guarda um **código** de motivo, nunca texto livre.
- **Uma liberação só:** `liberar_planejamento` roda uma vez, depois da homologação. É ali que o motor da
  Fase 9 vai ser ligado.
- **Observabilidade:** cada etapa grava um AgentRunEvent (`services/execucoes.py`): etapa, agente (IA,
  regra ou pessoa), início, fim, duração, status, modelo, versão do prompt, tipo de erro, guardrail e
  origem (REAL ou MOCK). Tokens e custo ficam vazios até o provedor medir (ADR-36).

**Na tela.** Os botões que fazem o arquivo andar (Interpretar, Aceitar, decidir colunas, Homologar)
entregam a decisão ao fluxo por `fluxo.responder`, que recusa com mensagem quando o arquivo está em
outra etapa. Pedidos de correção e justificativas continuam nos serviços (cada um já revalida); na hora
de homologar, o fluxo revalida e só então homologa. A aba Envio mostra a etapa atual, o desenho do
fluxo com a etapa destacada e as execuções; a aba Mapeamento mostra a falha com "Tentar de novo" ou o
encerramento. O `st.session_state` não guarda o fluxo: o `processamento_id` vai na barra de endereço
(ADR-39) e o ponto de salvamento guarda o resto.

**Trade-off.** Mais uma peça (o grafo e o seu arquivo de salvamento) e a regra de não mudar dados antes do
`interrupt()` nas etapas de pausa; em troca, o caminho de cada arquivo fica explícito, auditável e
retomável, e as voltas (correção, handoff, falha) deixam de depender da tela.

**Como comprovamos.** `tests/test_fluxo_empresa.py` (18 testes): caminho completo da Aurora com a volta
para a correção; homologação e liberação uma única vez; retomada sem refazer o Interpretador; aceite sem
decisão pergunta de novo; handoff volta ao aceite; decisão de coluna padroniza de novo; rejeição; arquivo
incompleto nunca chega a HOMOLOGADO; falha do LLM para o arquivo e a nova tentativa segue; falhas
repetidas e limite de ciclos encerram; outra empresa não mexe; estado sem CPF nem nome; a ponte com a
tela leva ao aceite depois do handoff, homologa a partir da correção e recusa ação de outra etapa. Na tela
(`tests/test_permissoes_e_telas.py`): a etapa atual aparece depois de interpretar; a correção até a
homologação passa pelo fluxo.
**Origem.** Plano, Fase 8; 2026-09-24 (modo despertador).

## O. Motor de planejamento (Fase 9)

<a id="adr-50"></a>
### ADR-50 · Motor de planejamento: lê só o necessário, guarda o hash do CPF e entrega só agregados ✅

O ADR-25 decidiu o motor determinístico sem ofertas; os ADRs 26 a 29, as premissas, a região, as
finalidades e os campos proibidos. Este registra como o motor foi construído.

**Quando roda.** Uma vez por arquivo, na etapa `liberar_planejamento` do fluxo (ADR-49), logo depois da
homologação. Lê o **arquivo final homologado**, nunca os dados em correção.

**O que lê.** Só 5 campos: CPF (para cruzar com a base do banco), unidade de trabalho (código e nome),
município e UF comerciais (a região, ADR-27). Antes de ler, confere no layout **ativo** que todos estão
liberados para uso comercial; se o banco bloquear um deles numa versão nova do layout, o motor **não
roda** (erro claro). Salário, cargo, sexo, nascimento e os demais nem chegam ao motor.

**Classificação**, cruzando com a base oficial (sintética) do banco: NAO_CORRENTISTA (conta a abrir),
CORRENTISTA_SEM_VINCULO (falso não folha a reconhecer), CORRENTISTA_COM_VINCULO e SEM_DADOS_SUFICIENTES.
Autorização de oferta ativa só conta para correntista; a leitura da base **recusa** autorização sem
conta. O segmento vem da base (quem não está nela fica "Sem segmento"), nunca do salário.

**Onde guarda.**
| Tabela | O que tem | Quem vê |
|---|---|---|
| `planejamento_funcionario` | Uma linha por pessoa **com o SHA-256 do CPF**, a classificação, a região e o segmento; chave (empresa, hash) | Ninguém: interna, para rastrear os números |
| `resumo_planejamento` | Visão (VIEW) com as contagens por empresa, região e segmento, sempre em dia | O Cockpit (e o Consultor, na Fase 11) |
| `simulacao_ganho` | Cada simulação salva: quem, filtros, taxa, **versão das premissas**, contagens e ganhos | O Cockpit |

**Por que o hash e não o CPF.** O motor só precisa saber se a pessoa **já foi contada** naquela empresa
(o arquivo de inclusão não pode recontar ninguém). O hash responde isso sem guardar o CPF numa tabela a
mais: minimização (LGPD).

**Trade-off.** O Cockpit fica zerado até alguma empresa homologar (antes, mostrava números de exemplo);
em troca, todo número é rastreável até um arquivo homologado. A MOCK de planejamento foi removida.

**Como comprovamos.** `tests/test_planejamento.py` (15 testes): as contagens da Aurora batem com a conta
feita à mão direto da base; o motor recusa arquivo não homologado; a inclusão da Brisa conta só as 2
pessoas novas e rodar de novo não soma nada; filtros e somas; nenhuma saída tem CPF, e as tabelas por
região só têm região e contagens; a tabela interna guarda só o hash; autorização só de correntista e só
somada; a base nunca tem autorização sem conta; o motor só lê os seus 5 campos liberados e para se a UF
for bloqueada no layout; fórmula do ganho, sem taxa padrão, simulação salva com a versão das premissas.
Na tela: salvar a simulação no Cockpit. **Origem.** Plano, Fase 9; 2026-09-24 (modo despertador).

## P. Cockpit do Banco (Fase 10)

<a id="adr-51"></a>
### ADR-51 · Cockpit sem conta na tela, com fonte rastreável e premissas reproduzíveis ✅

**Decisão.** O Cockpit só **mostra**: toda contagem vem da visão `resumo_planejamento` e da tabela do
motor, e toda conta de dinheiro vem de `services/planejamento.py` (até a conversão de "20%" em 0,20).
- **Filtros:** empresa, UF da unidade, segmento (base oficial) e **data de referência da carga** (a data
  que a empresa informou no envio; o motor passou a guardá-la, com migração para bancos antigos).
- **Cards:** empresas integradas, funcionários processados, contas a abrir, correntistas a reconhecer,
  autorizam contato; rótulos "dados sintéticos", "ESTIMATIVA" e a versão das premissas com os valores.
- **Premissas reproduzíveis:** o especialista escolhe a versão (a ativa vem primeiro). Uma versão nova
  muda o cenário; escolher a anterior reproduz exatamente o resultado antigo.
- **Fonte rastreável:** "De onde vêm os números" lista cada arquivo homologado, a carga, a data e
  quantas pessoas ele trouxe; nenhum CPF.
- **Área "Pergunte ao AI Payroll Hub"** reservada para o Consultor (Fase 11), que vai usar as mesmas
  consultas.

**Trade-off.** Mais filtros e uma escolha a mais (a versão das premissas); em troca, qualquer número da
tela pode ser refeito e explicado para a banca e para a auditoria.

**Como comprovamos.** `tests/test_planejamento.py`: os cards batem com a contagem feita direto na tabela
do motor e respeitam o filtro de empresa; filtro pela data de referência; a fonte aponta o arquivo e as
35 pessoas da Aurora, sem CPF; a v2 muda o ganho e a v1 escolhida de novo dá o mesmo ganho de antes; a
taxa vira fração no serviço; banco antigo ganha a coluna da data. **Origem.** Plano, Fase 10;
2026-09-24 (modo despertador).

## Q. Agente Consultor (Fase 11)

<a id="adr-52"></a>
### ADR-52 · Consultor: política no código, ferramentas fechadas e todo número conferido na saída ✅

O ADR-18 decidiu supervisor + 3 subagentes (e a comparação com agente único); o ADR-20, ferramentas
fechadas. Este registra como foi construído.

**Camadas, na ordem de uma pergunta.**
1. **Política no código, antes do LLM:** ordem para a IA (guardrail de injeção), pedido de lista de
   pessoas, de CPF, de nomes ou de SQL são recusados sem chamar o LLM. Uma regra no prompt pode ser
   contornada; uma regra no código, não.
2. **Supervisor:** divide a pergunta em tarefas (contrato Pydantic), no máximo **3 delegações**, uma por
   subagente. Não consulta dados. Assunto fora de planejamento, projeção e integração: FORA_DO_ESCOPO.
3. **Subagentes:** cada um devolve UMA chamada de ferramenta (contrato). A permissão (allowlist por
   papel) e os filtros tipados (empresa e UF existentes, taxa entre 0 e 1, campo extra recusado) são
   conferidos em `agents/ferramentas_do_consultor.py`. Não existe SQL livre.
4. **Ferramentas:** `consultar_planejamento`, `simular_ganho`, `comparar_cenarios`,
   `consultar_status_integracao`. Só leem pelos serviços (os mesmos do Cockpit) e devolvem contagens,
   dinheiro projetado com as premissas, população (quem entra no número) e fonte. Sem taxa, `simular_ganho`
   **não simula**: devolve o pedido da taxa (ADR-26).
5. **Síntese com guardrail de saída:** todo número do texto precisa existir nos resultados das ferramentas
   (a taxa pode aparecer em %). Se a redação citar um número de fora, ela é trocada pela resposta montada
   só com os números, e isso fica nas limitações. A resposta traz situação (RESPONDIDO, PEDE_TAXA,
   SEM_DADOS, FORA_DO_ESCOPO, RECUSADO, FALHA), a trilha de delegações, premissas, população, fontes e
   limitações.

**Agente único.** A mesma pergunta pode ir a um LLM com todas as ferramentas (`arquitetura="agente_unico"`),
com os mesmos contratos, a mesma allowlist e a mesma síntese. É a base da comparação da Fase 14 (o ADR-18
continua 🧪 até lá).

**MOCK.** Simuladores leem o pedido de verdade (palavras da pergunta, empresa, UF, segmento, taxas em %)
e respondem no contrato; a síntese do MOCK é a própria resposta montada só com os números. Não é medição de IA.

**Trade-off.** A resposta montada é menos fluente que uma redação livre; em troca, nenhum número da
resposta pode ser inventado, e a banca consegue refazer cada um pela trilha.

**Como comprovamos.** `tests/test_consultor.py` (27 testes) e `data/avaliacao/consultor_golden.json`: as 3
perguntas de demo (inclusive a composta, com os 3 subagentes) delegam certo, com os filtros e as taxas
certas; os números são os das consultas de planejamento; sem taxa pede a taxa; sem homologação, "sem
evidência"; fora do escopo recusa; lista, CPF, SQL e injeção recusados sem LLM; ferramenta de outro papel
e filtros inválidos barrados; número inventado trocado; limite de delegações; supervisor fora do contrato
vira FALHA; agente único chega aos mesmos números. **Origem.** Plano, Fase 11; 2026-09-24 (modo despertador).

<a id="adr-53"></a>
### ADR-53 · Endomarketing: rascunho em blocos com fonte, conferido na saída e aprovado pela empresa ✅

> **Alterado pelo [ADR-115](#adr-115) (2026-09-28):** o pedido (tipo, canal, destaque e agora os benefícios) é feito
> pelo especialista do banco; a busca fica restrita aos benefícios escolhidos, mais os canais de atendimento. A
> conferência de saída não muda. "Aprovação" virou **publicação pelo banco** (RASCUNHO → PUBLICADO ou DESCARTADO;
> PUBLICADO → RETIRADO); a empresa vê e baixa só os publicados. As sugestões (total sem conta e kit de boas-vindas)
> aparecem ao especialista.

O ADR-19 decidiu o agente único com RAG no catálogo da empresa; o ADR-30, o agregado com mínimo de
pessoas. Este registra como foi construído.

**Pedido.** A empresa escolhe o tipo (comunicado interno, FAQ ou kit de boas-vindas) e, se quiser, um
destaque. O destaque passa pelo guardrail de injeção (é dado, não instrução).

**Busca.** Várias buscas por tipo de material, sempre com `empresa_id` do **usuário logado** e só em
documentos vigentes (ADR-10); trecho de outra empresa é descartado de novo no agente (defesa em dobro).
Destaque que não traz nenhum trecho vira aviso: "o catálogo não traz informação sobre isso", e nada é
escrito sobre o assunto. Sem nenhum trecho: SEM_EVIDENCIA, nada é guardado.

**Saída em blocos, conferida.** O LLM devolve título e blocos, cada um com as fontes (contrato). A
conferência remove o bloco que cita fonte que não veio da busca ou que traz número que não está nos
trechos citados (um "24 meses" onde o catálogo diz "12 meses" não passa). O que sai vai para a tela.

**Aprovação.** Todo material nasce RASCUNHO; só a própria empresa aprova ou descarta; só o aprovado pode
ser baixado (Markdown, com a fonte de cada bloco).

**Equipe sem conta (ADR-30).** Só o total da empresa inteira, do motor de planejamento; abaixo do mínimo
das premissas (inicial 10) aparece "menos de 10" e nenhum número exato. Nunca uma lista.

**Kit de boas-vindas.** Cada inclusão homologada sem kit vira sugestão na aba; gerado o kit (ligado à
inclusão), a sugestão some.

**Trade-off.** O texto em blocos, cada um com fonte, é menos corrido que um comunicado livre; em troca,
a empresa sabe de onde veio cada frase, e nenhuma condição de produto é inventada.

**Como comprovamos.** `tests/test_endomarketing.py` (14 testes): nos 3 tipos, todo bloco cita fonte do
catálogo da própria empresa e a busca só foi feita nela; o prazo aparece como no catálogo; aprovação só
pela própria empresa e uma vez; número e fonte inventados removidos; assunto fora do catálogo recusado;
sem trecho, sem evidência; destaque com injeção recusado; "menos de 10" abaixo do mínimo; o total da
empresa igual ao do planejamento; sugestão de kit até o kit ser gerado; MOCK reproduzível. Na tela:
gerar, ver a fonte, aprovar. **Origem.** Plano, Fase 11; 2026-09-24 (modo despertador).

## R. Painel Técnico (Fase 12)

<a id="adr-54"></a>
### ADR-54 · Painel Técnico só com execuções reais, sem dado pessoal e sem número inventado ✅

**Decisão.** As execuções falsas (MOCK) da Fase 2 saíram; o painel lê só o que o sistema grava:
- **Execuções (AgentRunEvent):** as etapas do fluxo (ADR-49) e, agora, o **Consultor** (uma execução
  por pergunta e uma por delegação, com o subagente e a ferramenta), o **Endomarketing** (uma por
  pedido de material) e o **Assistente de Correção** (uma por rodada, com a ação escolhida). Guardrail
  que barra vira situação **BLOQUEADO** com `guardrail_disparado`. Nada do texto das mensagens entra: só
  etapa, agente, horários, duração, situação, tipo de erro, modelo e versão do prompt.
- **Visão geral:** cards (execuções, processamentos e consultas, erro ou bloqueio, guardrails,
  intervenções humanas, tokens e custo) calculados da **mesma lista** que a tabela mostra; latência e
  falhas por agente; arquivos recebidos, homologados e a taxa de homologação. Filtros por agente, modelo
  e período.
- **Por execução:** a linha do tempo de um arquivo ou consulta, juntando execuções e eventos da auditoria
  (correções, revalidações, handoffs, injeções barradas, homologação).
- **Avaliação:** o que já foi medido (B0 com IC 95%, hit@k dos dois índices do RAG) e, marcado como tal,
  o que espera o provedor ou a Fase 14 (B1 a B5, agente único × supervisor, fidelidade do Endomarketing);
  métricas proxy de negócio do motor de planejamento.
- **"Não medido":** sem medição do provedor, tokens e custo aparecem escritos, nunca como zero.

**Trade-off.** O painel começa vazio numa instalação nova (antes, mostrava exemplos); em troca, todo
número dele é rastreável até uma execução ou um evento de verdade.

**Como comprovamos.** `tests/test_painel.py` (8 testes): cada envio gera as execuções do fluxo, na ordem;
os cards batem com a contagem feita direto na tabela; as delegações do Consultor e a recusa (BLOQUEADO)
aparecem; a linha do tempo junta correção, revalidação e injeção barrada, em ordem; filtros; nenhum CPF
e nenhuma palavra da mensagem da empresa; latência soma as execuções; a aba de avaliação separa o medido
do que espera o provedor. Na tela: execuções reais e a história de uma consulta.
**Origem.** Plano, Fase 12; 2026-09-24 (modo despertador).

## S. Guardrails e segurança (Fase 13)

<a id="adr-55"></a>
### ADR-55 · Arquivo conferido pelo conteúdo, exportação sem fórmula e guardrail medido com prova separada ✅

**Arquivo.**
- **Tipo pelo conteúdo, não pelo nome:** `.xlsx` precisa começar com a assinatura de zip (`PK`); `.csv`
  não pode começar como zip, PDF ou programa, nem ter byte nulo. Um PDF renomeado para `.xlsx` é recusado.
- **Limites do MVP:** 20.000 linhas e 200 colunas (além dos 5 MB).
- **Fórmulas recusadas:** a leitura usa o valor que o Excel guardou; se a fórmula não foi recalculada, o
  valor pode estar velho ou vazio, sem ninguém perceber. A mensagem diz a célula e pede "colar valores".

**Exportação (CSV injection).** No arquivo homologado, célula que começa com `=`, `+`, `@`, tabulação,
quebra de linha ou `-` seguido de texto ganha um apóstrofo: o Excel abre como texto, não executa.
Números (inclusive negativos) ficam como estão.

**Guardrail de injeção.**
- **Casos com prova separada** (`data/avaliacao/guardrail_casos.json`): ataques e textos normais parecidos
  (o que mede o falso alarme), em "desenvolvimento" (usado para ajustar os padrões) e "prova" (só medido),
  como no ADR-37.
- **Antes do ajuste**, a lista acertava 80% dos ataques da prova e dava 10% de falso alarme ("Você agora é
  um correntista...", "esqueça todas as instruções" e "finja ser" escapavam ou disparavam errado).
  **Depois do ajuste só no desenvolvimento** (padrão de "esqueça", "você agora é" só com papel de IA,
  "finja ser/que", senha e chave só com "sua"): **100% de detecção e 0% de falso alarme na prova**. São
  conjuntos pequenos (10 + 10): a lista é uma camada, e a proteção principal continua sendo o que a IA
  não tem poder de fazer (aprovar, homologar, ver outra empresa, rodar SQL).
- **Segunda opinião** (`verificar_mensagem`): mensagens (chat, perguntas, destaques, documentos do
  catálogo, dica do handoff) passam pela lista e, no modo LLM, por um modelo pequeno com o prompt
  `guardrail_v1` (SUSPEITO ou NORMAL). Células de planilha ficam só com a lista (custo). No MOCK, só a lista.
- **Saída:** a conferência de contrato, campos do parâmetro, números e fontes já existe em cada agente
  (ADRs 38, 45, 52 e 53).

**Como comprovamos.** `tests/test_seguranca.py` (20 testes) e `scripts/avaliar_guardrail.py` (resultado em
`data/avaliacao/resultados/guardrail.json`, mostrado no Painel Técnico). **Origem.** Plano, Fase 13;
2026-09-24 (modo despertador).

<a id="adr-56"></a>
### ADR-56 · Perfis conferidos nos serviços, empresa vazia nunca vira "todas" e teto de gasto ✅

**Problema achado.** `processamentos.obter(..., empresa_id=None)` quer dizer "sem filtro". Se uma operação de
empresa recebesse `empresa_id` vazio (ex.: de um usuário do banco, que não tem empresa), ela abriria o
arquivo de qualquer empresa. Só a tela impedia isso.

**Decisão.**
- **Escopo de empresa no serviço:** as operações de empresa (correção, justificativa, homologação,
  mapeamento, padronização, validação, fluxo e Assistente) usam `obter_da_empresa`, que **recusa empresa
  vazia** (AcessoNegado). O `obter` sem filtro fica só para leituras internas do banco (motor e planejamento).
- **Porta das operações sensíveis (`services/acesso.py`):** consultar o Consultor, salvar simulação,
  editar layout, premissas e catálogo, gerir usuários, ver as execuções do painel e gerar material de
  Endomarketing passam por uma porta que confere o perfil com a tabela `PERFIS_POR_OPERACAO`
  (`services/permissoes.py`). A empresa e o login vêm SEMPRE do usuário logado. Operação desconhecida é
  negada; ninguém desativa o próprio usuário. Um teste garante que **nenhuma tela chama essas operações
  sem a porta**.
- **Teto de gasto por sessão:** além do limite de chamadas, o cliente de LLM soma o custo que o provedor
  informar e, atingido o teto, cai para MOCK dizendo o motivo. Sem custo informado, nada é somado (nunca
  inventado). O **valor** do teto é decisão de orçamento do dono do projeto: fica no `.env`
  (`TETO_DE_GASTO_USD`). **Decidido em 2026-09-25: US$ 10 por sessão**; a trava final é o limite de crédito
  que o dono do projeto configurou em cada conta dos provedores.

**Trade-off.** Uma camada a mais entre tela e serviço; em troca, o perfil errado é barrado mesmo que alguém
chame o serviço por fora da tela, e o isolamento entre empresas não depende de a tela lembrar de filtrar.

**Como comprovamos.** `tests/test_seguranca.py`: para cada operação, só os perfis da tabela passam e sem
login ninguém passa; operação desconhecida e empresa sem empresa são negadas; a porta barra o perfil errado
chamando o serviço direto; ninguém desativa a si mesmo; empresa vazia é negada no serviço; nenhuma tela
pula a porta; o teto de gasto cai para MOCK na terceira chamada e sem custo nada é somado.
**Origem.** Plano, Fase 13; 2026-09-24 (modo despertador).

<a id="adr-57"></a>
### ADR-57 · Ataques reunidos num arquivo só e matriz de permissões e riscos no README ✅

**Opções.** (a) Deixar cada proteção testada só no arquivo do seu módulo; (b) reunir os 14 ataques do
checklist num arquivo próprio, escrito do ponto de vista de quem ataca, e publicar a matriz no README.

**Decisão.** (b). `tests/test_adversarial.py` tem um teste por ataque (numerados como no checklist): ordem
escondida em célula e em cabeçalho, LLM que tenta aprovar, envenenar o RAG pelo chat, ordem no catálogo,
ver outra empresa, SQL livre, acesso sem login, estourar o limite, ferramenta de outro papel, laço entre
agentes, identificar quem não tem conta, grupo pequeno demais e a IA tentando homologar. O README ganhou a
seção "Segurança: matriz de permissões e riscos": quem pode fazer o quê (e onde isso é conferido) e cada
risco com o que o barra e o teste que prova.

**Trade-off.** Alguns ataques repetem o que os testes de cada módulo já cobrem; em troca, a banca e quem
revisa têm uma lista única, legível de ponta a ponta, e a matriz do README aponta para a prova.

**Como comprovamos.** `tests/test_adversarial.py` (16 testes); suíte completa com 438 testes passando.
**Origem.** Plano, Fase 13; 2026-09-24 (modo despertador).

<a id="adr-58"></a>
### ADR-58 · Prova e métricas congeladas por impressão digital antes de medir ✅

**Problema.** O ADR-37 manda congelar o golden, o vocabulário de teste e as métricas antes de rodar B1 a B5.
Sem um mecanismo, "congelado" seria só uma promessa: bastaria editar um gabarito ou a forma de contar o
acerto depois de ver o resultado, e ninguém perceberia.

| Opção | A favor | Contra |
|---|---|---|
| Confiar no histórico do Git | Nada a construir | Ninguém confere o histórico antes de cada medição |
| Deixar os arquivos só-leitura | Simples | Não vale em outra máquina nem no Git; não diz o que mudou |
| **Foto com a impressão digital (SHA-256) de cada arquivo, conferida pelos scripts de medição** | Qualquer mudança é percebida e a medição se recusa a rodar; recongelar exige motivo, gravado com a data | Um arquivo e um script a mais |

**Decisão.** `eval/congelamento.py` fotografa 16 arquivos (prova do Interpretador, vocabulário de teste,
calibração do B0, consultas do RAG, perguntas golden do Consultor, casos do guardrail, os 9 gabaritos e
`eval/metricas.py`) em `data/avaliacao/congelamento.json`. `avaliar_interpretador`, `avaliar_rag` e
`avaliar_guardrail` chamam `exigir_prova_congelada()` antes de medir. A impressão digital troca CRLF por
LF antes de calcular, para a foto valer no Windows e no Linux. Recongelar: `scripts/congelar_avaliacao.py
"motivo"`.

**Junto: acurácia de cada campo.** O B0 passa a gravar a acurácia separada por campo do layout, do pior
para o melhor, e o Painel Técnico mostra os 10 piores. Resultado: o número geral de 50,9% esconde campos
com **0% de acerto** (`valor_renda`, `matricula`, `municipio_residencial`, `nome_unidade`...), em que o
nome da coluna no vocabulário de teste não se parece com nenhum sinônimo do treino. É nesses campos que
a IA (B1 a B5) precisa mostrar ganho. Os números gerais do B0 não mudaram.

**Trade-off.** Toda mudança intencional na prova custa um recongelamento com motivo; é esse atrito que
torna o congelamento real.

**Como comprovamos.** `tests/test_congelamento.py`: a prova do repositório bate com a foto (também depois
da suíte inteira, que regenera os dados); CRLF e LF dão a mesma impressão digital; alterado, removido e
novo são percebidos; prova alterada ou não congelada para a medição; recongelar sem motivo é recusado; a
soma por campo bate com a acurácia geral. **Origem.** Plano, Fase 14; 2026-09-24 (modo despertador).

<a id="adr-59"></a>
### ADR-59 · Fluxo avaliado de ponta a ponta com uma pessoa simulada pelo gabarito ✅

**Problema.** A Fase 14 pede medir o workflow (conclusão, retomada, intervenções humanas, erros por etapa) e
as métricas proxy de negócio (homologação sem edição manual e tempo até a homologação). Os testes de cada
fase provam regras isoladas; faltava um número do caminho inteiro.

| Opção | A favor | Contra |
|---|---|---|
| Medir só no uso real (pessoas usando o Portal) | Tempo e decisões reais | Não existe uso real antes do piloto |
| Medir cada etapa em separado | Já existe (testes das Fases 3 a 8) | Não mostra o arquivo chegando ao fim nem a retomada |
| **Rodar os 9 arquivos pelo fluxo inteiro, com uma pessoa simulada que decide pelo gabarito** | Reprodutível; usa os mesmos serviços e o mesmo fluxo do Portal; mede o caminho inteiro | Em MOCK, a interpretação e o tempo não são os de um modelo real, e o tempo da pessoa não entra |

**Decisão.** `eval/avaliacao_do_fluxo.py` processa as cargas iniciais e depois as inclusões num banco
temporário. A pessoa simulada aceita o mapeamento do gabarito, decide o formato das colunas (zeros, datas),
exclui linha repetida, justifica alerta e corrige erro com o valor verdadeiro, sempre pelos serviços do
Portal (pedido + clique). Cada decisão é entregue a um fluxo reaberto do ponto de salvamento. Um cenário de
falha (provedor fora do ar) roda num banco à parte. `scripts/avaliar_fluxo.py` grava
`data/avaliacao/resultados/fluxo.json`, mostrado no Painel Técnico; o código da avaliação entrou no
congelamento (ADR-58).

**Resultado (MOCK).** 9 de 9 arquivos homologados; **9 de 9 erros injetados achados na linha certa e
nenhum achado fora do gabarito**; 5 de 9 homologados sem edição manual de valor (os outros 4 tinham um erro
que só a empresa sabe corrigir: CPF, data de admissão, valor por extenso e matrícula repetida); 3,8
intervenções humanas e 0,9 ciclo de correção por arquivo; **0 etapas refeitas em 26 retomadas**; as
inclusões reaproveitam o mapeamento aprovado; com o provedor fora do ar, o arquivo para em "tentar de
novo" e não vira sucesso.

**Trade-off.** A pessoa simulada sempre acerta, então a avaliação não mede erro humano nem o tempo da
pessoa, que só aparece no uso real (proxy de tempo = tempo de máquina). O que ela prova é o fluxo: regras,
pausas, retomada e controle humano.

**Como comprovamos.** `tests/test_avaliacao_do_fluxo.py` (8 testes): todos homologados; todo erro achado e
nada além; inclusões depois das cargas e com reuso; nenhuma etapa refeita; falha sem falso sucesso; proxies
batem com as decisões contadas; o CPF só é corrigido pela pessoa. **Origem.** Plano, Fase 14; 2026-09-24
(modo despertador).

<a id="adr-60"></a>
### ADR-60 · Consultor comparado: agente único × supervisor, com casos de controle e chamadas contadas 🧪

> **Nota do [ADR-117](#adr-117) (2026-09-28):** com o empate e as chamadas a mais do supervisor, a aplicação passou a usar o agente único; a comparação continua, agora para dizer se o supervisor volta.

**Problema.** O ADR-18 escolheu supervisor com 3 subagentes e prometeu comparar com um agente único nas
mesmas perguntas (exatidão, custo, latência). O golden tinha 3 perguntas, todas com resposta: não media o
que o Consultor faz quando NÃO deve responder com números.

**Decisão.**
- **Golden ampliado:** 6 perguntas com resposta (subagentes, ferramentas, filtros e taxas esperados, agora
  também comparação de cenários e integração de uma empresa) e 6 **casos de controle**: pedir a taxa, dizer
  que não há dados, recusar lista de CPFs, SQL e ordem para a IA, e reconhecer pergunta fora do escopo.
  Recongelado com motivo (ADR-58).
- **Medição** (`eval/avaliacao_do_consultor.py`, `scripts/avaliar_consultor.py`): cada caso roda nas duas
  arquiteturas num banco temporário com Aurora e Vale Verde homologadas pelo fluxo. Um "contador" fica entre o
  Consultor e o cliente de IA e conta cada chamada (e soma o custo quando o provedor informa). A conferência de
  cada pergunta é a mesma do teste do Consultor (situação, subagentes, ferramentas, filtros exatos, taxas e
  nenhum número de fora).

**Resultado (MOCK).** As duas arquiteturas acertam 12 de 12, com textos idênticos. Chamadas à IA: o
**supervisor faz 2 + uma por subagente** (3 nas perguntas simples, 5 na composta); o **agente único faz
sempre 2**. Nas perguntas com resposta, são 3,3 × 2 chamadas em média: o supervisor custa cerca de **67% mais
chamadas**. As recusas não chamam a IA nenhuma vez. Custo em dólar: "não medido" (sem provedor).

**Leitura.** Em MOCK, a exatidão é a do simulador (as duas usam as mesmas regras), então **ainda não decide**
qual arquitetura é melhor: isso depende de a IA real errar mais ao escolher várias ferramentas de uma vez
(agente único) do que ao dividir a pergunta (supervisor). O que já está medido é o preço estrutural do
supervisor. Com o provedor escolhido, o mesmo script mede exatidão, custo e latência reais, e o ADR-18 é
confirmado ou revisto com esse número (resultado negativo também é registrado, ADR-37).

**Trade-off.** 12 casos são poucos para intervalo de confiança; servem para achar diferença grande e erro de
roteamento. Ampliar o golden é barato (um JSON), mas exige recongelar.

**Como comprovamos.** `tests/test_avaliacao_do_consultor.py` (6 testes): tudo certo nas duas em MOCK;
recusas sem chamada à IA; supervisor = 2 + subagentes e agente único = 2; custo "não medido" sem provedor; o
contador soma o custo informado; a conferência pega filtro, ferramenta e taxa errados.
**Origem.** Plano, Fase 14; 2026-09-24 (modo despertador).

<a id="adr-61"></a>
### ADR-61 · Endomarketing medido: fidelidade, isolamento, guardrail adulterado e um resultado negativo ✅

> **Nota do [ADR-115](#adr-115) (2026-09-28):** com o banco gerando, o especialista escolhe os benefícios de cada
> material. A avaliação congelada continua chamando o agente sem benefícios escolhidos (busca pelo RAG), e por isso
> mede o mesmo que antes.

**Problema.** A Fase 14 pede medir o Endomarketing: hit@k do catálogo, fidelidade às fontes, recusa quando
falta informação e isolamento. O hit@k já era medido (`scripts/avaliar_rag.py`); faltava o resto.

**Decisão.** `data/avaliacao/endomarketing_casos.json` (congelado) e `eval/avaliacao_do_endomarketing.py`,
com a busca REAL no catálogo (`scripts/avaliar_endomarketing.py`, banco temporário):
- **Fidelidade e isolamento:** todo tipo de material para toda empresa (18); conta os blocos que passaram na
  conferência e os que citam fonte de fora da empresa.
- **Guardrail adulterado:** cada bloco aprovado é adulterado de propósito (número trocado, fonte inventada,
  fonte real de OUTRA empresa) e conferido de novo contra o catálogo inteiro da empresa. Isso mede a
  conferência sem depender da IA: todo adulterado tem de cair e todo original tem de ficar.
- **Destaques:** 4 assuntos que o catálogo da empresa traz (tem de achar a seção) e 4 que não traz, três
  deles presentes no catálogo de outra empresa (tem de avisar e não citar a outra).

**Resultado.** 18 de 18 materiais; **83 de 83 blocos fiéis; 0 fontes de outra empresa**; **202 de 202
blocos adulterados barrados** e 83 de 83 originais mantidos; 4 de 4 destaques existentes achados na seção
certa. **Resultado negativo: 0 de 4 destaques ausentes foram avisados.** A busca devolve a seção mais parecida
da própria empresa (ex.: "seguro de vida" na Aurora traz "Onde consultar" e "Crédito consignado", a 0,62 e
0,69), então nada falso é escrito e
nada vaza de outra empresa, mas a empresa não é avisada de que o assunto não existe no catálogo dela.

**Por que não resolvemos com a distância.** Medimos, num conjunto de **desenvolvimento** com outros assuntos
(12 destaques), a distância do trecho mais parecido: quando o catálogo tem o assunto, de 0,26 a **0,64**;
quando não tem, a partir de **0,44**. As faixas se cruzam: nenhuma distância máxima separa "tem" de "não tem"
sem errar dos dois lados. É a mesma lição do ADR-42 no layout. Decidir que o catálogo não cobre um assunto
parecido com outro é trabalho de leitura, isto é, da IA: o contrato já tem o campo `nao_encontrado`, e o
prompt manda preenchê-lo. O simulador MOCK não faz esse papel, e não o "ensinamos" a passar nesta prova
(seria ajustar o simulador ao gabarito).

**Trade-off.** Até o provedor ser escolhido, a demo em MOCK não avisa sobre destaque parecido com outro
assunto (só sobre assunto muito distante). Quando o provedor existir, o mesmo script mede o aviso da IA real
nesses 4 casos congelados.

**Como comprovamos.** `tests/test_avaliacao_do_endomarketing.py` (6 testes): com uma busca que não acha o
assunto, o aviso sai e a outra empresa não é citada; todo material fiel e isolado; destaques existentes
achados; toda adulteração barrada e todo original mantido; a fonte da adulteração é mesmo de outra empresa; o
resultado gravado com a busca real registra que as faixas de distância se cruzam. **Origem.** Plano, Fase 14;
2026-09-24 (modo despertador).

<a id="adr-62"></a>
### ADR-62 · Guardrail de injeção medido por camadas: lista, classificador e os dois juntos 🧪

> **Alterado pelo [ADR-147](#adr-147) (2026-09-30):** o classificador passa a ser o Bedrock Guardrails, ligado sem
> experimento antes, pela regra da usuária de 30/09. A medição por camadas continua possível em
> `scripts/avaliar_guardrail.py`, mas não é mais portão.

**Problema.** O guardrail tem duas camadas na entrada (ADR-55): a lista de padrões e, no modo LLM, uma
segunda opinião de um modelo pequeno. A Fase 14 pede a detecção e o falso alarme de cada uma e das duas
juntas, para saber se o classificador paga o custo de uma chamada a mais por mensagem.

**Decisão.** A segunda opinião virou uma função própria (`guardrail_injecao.segunda_opiniao`), usada por
`verificar_mensagem` (comportamento igual). `scripts/avaliar_guardrail.py` mede na prova: a lista sozinha, o
classificador sozinho e os dois juntos. Sem provedor, as duas últimas ficam **"aguardando o provedor de IA"**,
nunca um número inventado (no MOCK não há modelo de verdade para classificar). O Painel mostra as três linhas.

**Resultado hoje.** Lista: 100% de detecção e 0% de falso alarme na prova (ADR-55). Classificador e
"juntos": aguardando o provedor.

**Trade-off.** "Juntos" nunca detecta menos que a lista (é um "ou"), mas pode ter mais falso alarme e custa
uma chamada por mensagem. A decisão de manter o classificador depende desse número, a medir com o provedor.

**Como comprovamos.** `tests/test_seguranca.py`: a segunda opinião usa só o modelo; em MOCK as camadas do
modelo aguardam o provedor; no modo LLM (com um classificador de teste) as três camadas são medidas e "juntos"
detecta pelo menos o que cada uma detecta; o Painel mostra as camadas. **Origem.** Plano, Fase 14;
2026-09-24 (modo despertador).

<a id="adr-63"></a>
### ADR-63 · Servidor sem os índices do RAG: nada quebra, cada agente segue do seu jeito ✅

**Problema achado no ensaio de máquina limpa (Fase 15).** Sem os índices (servidor novo, disco que não
guarda arquivos, ou alguém que pulou o `build_index`), a busca do ChromaDB levanta um erro próprio da
biblioteca. O Interpretador já se protegia (o fluxo usa a B2 sem índice), mas o **Assistente de Correção** e
o **Endomarketing** mostrariam uma exceção na tela do Portal.

**Decisão.** A camada do RAG passa a avisar com um erro do projeto, `rag.busca.IndiceAusente`, e cada agente
decide como seguir:
- **Assistente de Correção:** continua conversando sobre a pendência, só que sem trechos de apoio
  (o prompt recebe "(nenhum)" e a resposta sai sem fontes);
- **Endomarketing:** responde com a situação `INDISPONIVEL` e a mensagem "o catálogo de benefícios ainda não
  está pronto neste servidor", não guarda rascunho e grava a execução como erro `IndiceAusente` (o Painel
  Técnico mostra o motivo, sem confundir com erro da IA).

**Por que um erro próprio, e não "conferir antes se o índice existe".** A conferência prévia faria os testes
dependerem do índice real da máquina. Com o erro próprio, os testes simulam o servidor sem índice com uma
busca que levanta `IndiceAusente`, sem tocar em nada.

**Achado junto (documentado no README).** Com o projeto numa pasta muito funda, o caminho do arquivo do modelo
de embeddings passa de 260 caracteres (limite do Windows) e o `build_index` falha com "Could not load model
... from any source". Solução: pasta curta ou caminhos longos ativados no Windows.

**Segundo achado do mesmo ensaio: índice vazio que "mentia".** Quando o modelo não baixava, o `build_index` já tinha criado
a coleção e ela ficava vazia. `indice_disponivel()` dizia "sim", o fluxo escolhia a B3 e cada busca tentava baixar o
modelo de novo, com esperas de ~40 s. Agora `gravar_colecao` calcula os vetores **antes** de mexer no índice (se falhar,
o índice antigo continua intacto e nada vazio fica para trás), e `indice_disponivel` só diz "sim" se o índice tiver
trechos.

**Como comprovamos.** `tests/test_sem_indice.py` (5 testes): a busca numa pasta vazia levanta
`IndiceAusente`; o Endomarketing avisa, não guarda nada e grava o erro certo; o Assistente responde sem fontes;
um `build_index` que falha no cálculo dos vetores não deixa índice vazio; índice vazio conta como indisponível.
**Origem.** Plano, Fase 15 (execução do zero em máquina limpa); 2026-09-24 (modo despertador).

<a id="adr-64"></a>
### ADR-64 · Servidor se prepara sozinho na subida; ensaio de máquina limpa ✅

**Problema.** Na hospedagem, o disco pode começar vazio a cada subida, e ninguém está lá para rodar scripts
ou digitar senha. Sem dados e sem índices, a demo abre pela metade; e o `criar_usuarios.py`, sem as senhas
nos segredos, ficaria parado esperando alguém digitar.

**Decisão.** `scripts/preparar_servidor.py` roda antes do Streamlit (o `Dockerfile` chama os dois em
sequência) e gera **só o que falta**: dados sintéticos, se a pasta dos envios está vazia; índices do RAG, se
algum não está disponível (índice vazio conta como ausente, ADR-63); e os três usuários da demo **somente**
se as três senhas estiverem nos segredos. Faltando uma, avisa e segue, sem nunca perguntar nada. Rodar de
novo não refaz dados nem índices.

**Ensaio de máquina limpa (2026-09-24).** O repositório foi clonado numa pasta vazia, com um ambiente virtual
novo e só os comandos do README: `pip install`, `.env` do modelo, `gerar_dados`, `build_index` (baixou o
modelo), todas as medições e o `pytest`. Resultado: **491 testes passando** e **todas as medições com os
mesmos números** (B0, RAG, fluxo, Consultor, Endomarketing e guardrail); os resultados regravados só
mudaram nos tempos. A prova congelada passou na conferência mesmo com o checkout do Windows (fim de linha
CRLF), como o ADR-58 previa. O ensaio achou os dois problemas do ADR-63 (tela quebrando sem índice e índice
vazio "mentindo") e o limite de 260 caracteres do Windows no caminho do modelo (README).

**Trade-off.** A primeira subida demora mais (baixa o modelo, ~220 MB) e precisa de internet. A imagem Docker
em si **ainda não foi construída**: falta o Docker Desktop nesta máquina e a hospedagem é decisão do dono
do projeto.

**Como comprovamos.** `tests/test_preparar_servidor.py` (5 testes): pasta vazia pede dados; servidor vazio
gera dados e índices sem perguntar senha; servidor pronto não refaz nada; faltando uma senha, ninguém é
criado; com as três, os usuários entram. **Origem.** Plano, Fase 15; 2026-09-24 (modo despertador).

<a id="adr-65"></a>
### ADR-65 · Comparação de modelos com dinheiro de verdade: amostra congelada, teto e nenhuma resposta simulada 🧪

**Problema.** A escolha do provedor sai de medição (ADR-11): os 5 modelos da triagem precisam fazer a mesma tarefa,
nas mesmas condições, gastando dinheiro real, sem risco de estourar o orçamento nem de medir resposta simulada.

**Decisão.**
- **Ligação com os provedores** (`services/provedores_de_ia.py`): o provedor sai do nome do modelo; a OpenAI
  usa a Responses API (com `temperature=0`; se o modelo recusar, refaz sem e anota); a Anthropic usa a Messages
  API, que na versão atual **não tem `temperature`** (a consistência vem do contrato validado e da medição de
  consistência). Tokens de entrada, saída e raciocínio vêm do próprio provedor; o custo, da tabela de preços do
  projeto. Chave e modelos só no `.env`; falta de chave ou de modelo **avisa**, não cai escondido no MOCK.
- **Comparação** (`eval/comparacao_de_modelos.py`, `scripts/comparar_modelos.py`): B3 em **30 planilhas sorteadas
  com semente fixa** e **congeladas** (ADR-58); o B0 entra como régua; os modelos rodam do mais barato para o mais
  caro; **teto de US$ 25** acumulado (inclui o que rodadas anteriores gastaram); **resposta do MOCK nunca é
  pontuada** (vira falha do provedor); 3 falhas seguidas deixam o modelo "indisponível"; o resultado é gravado
  depois de cada modelo e a rodada seguinte não cobra de novo os completos; sem chave, nada é chamado.
- **Os testes nunca alcançam as chaves reais:** o `conftest.py` zera as variáveis antes de o `.env` ser lido.

**Condição justa.** A planilha da prova tem só os nomes das colunas, a mesma informação do B0. No uso real a IA
também vê amostras mascaradas, então o resultado da comparação é conservador para a IA.

**Trade-off.** 30 planilhas dão intervalo de confiança mais largo que a prova inteira (300); em troca, o custo
cabe no orçamento e permite comparar 5 modelos. O vencedor será medido na prova inteira (B1–B3).

**Como comprovamos.** `tests/test_provedores_de_ia.py` (9 testes) e `tests/test_comparacao_de_modelos.py`
(8 testes), todos com provedores de mentira: roteamento e custo; texto, tokens e raciocínio; temperatura
recusada; erros que não são escondidos; falta de chave; teto que corta; modelo indisponível sem pontuar MOCK;
rodada seguinte sem cobrança repetida. **Origem.** Decisão do dono do projeto, 2026-09-24.

<a id="adr-66"></a>
### ADR-66 · Histórico de experimentos: um registro imutável por avaliação e um documento gerado ✅

**Problema.** Os arquivos de resultado (`data/avaliacao/resultados/`) são regravados a cada medição: o número de
hoje apaga o de ontem. Sem guardar cada experimento, não dá para contar a história das melhorias (o que testamos,
com qual modelo, o que mudou e o que decidimos), que a banca pede e o slide executivo precisa.

**Decisão.** Cada avaliação vira um **registro imutável** em `data/avaliacao/experimentos/EXP-NNN_nome.json` (numeração
em sequência; um registro nunca sobrescreve outro), com a data, a pergunta, o que foi testado, a amostra, o modo (sem
IA, MOCK ou IA real), as métricas de cada configuração ou modelo (acurácia, **recall e precisão da abstenção**, custo,
tempo...), a leitura, a decisão, a fonte e o commit. `docs/experimentos.md` é **gerado** a partir dos registros
(`scripts/gerar_historico_de_experimentos.py`): linha do tempo, evolução de acurácia, recall e precisão do
Interpretador e o detalhe de cada experimento. Medir e registrar são dois passos: a leitura e a decisão são humanas
(`scripts/registrar_experimento.py`, depois de ler os números). Os 8 experimentos já feitos foram registrados com os
números dos arquivos de resultado do dia (EXP-001 a EXP-008).

**Trade-off.** Um passo a mais depois de cada medição; em troca, nenhum resultado se perde e a história pode ser
conferida (cada registro aponta para a fonte e o commit).

**Como comprovamos.** `tests/test_historico_de_experimentos.py` (7 testes): numeração em sequência; nada é
sobrescrito; registro incompleto é recusado; só métricas medidas entram; o documento traz linha do tempo e evolução;
os registros do projeto estão completos; o documento está em dia com os registros. **Origem.** Pedido do dono do
projeto, 2026-09-25.

<a id="adr-67"></a>
### ADR-67 · PostgreSQL como banco, com o SQLite pela mesma porta ✅

**Problema.** O SQLite (ADR-34) servia bem ao MVP, mas a banca avalia a escolha do banco, e a ferramenta vai receber
todos os funcionários das empresas conveniadas: cerca de **1,04 milhão** (os 520.220 falso não folha são metade).
O tamanho não é o problema (medido: cerca de 2 KB por funcionário, ≈ 2 a 3 GB no total, o que o SQLite guarda sem
esforço). O problema é o uso: muitas empresas gravando ao mesmo tempo, o Cockpit consultando durante as cargas, mais
de uma cópia da aplicação, usuários e permissões no banco, cópia de segurança e réplica.

| Opção | A favor | Contra |
|---|---|---|
| Manter o SQLite | Zero servidor; reprodução imediata | Uma gravação por vez; sem usuários no banco; sem réplica; um disco só |
| **PostgreSQL** | Muitas gravações ao mesmo tempo; usuários, permissões e regra por linha; réplica e volta a qualquer ponto (PITR); tipos rígidos; pgvector; ponto de salvamento **oficial** do LangGraph; oferta gerenciada em todas as nuvens | Um servidor para instalar e manter |
| MariaDB / MySQL | Concorrência, usuários e réplica parecidos; já instalado na máquina | Ponto de salvamento do LangGraph só comunitário; ecossistema de RAG em banco menor; sem regra por linha nativa |

**Decisão.** PostgreSQL 18 no uso da aplicação (máquina local agora; produção depois), com o SQLite mantido como
alternativa pela **mesma porta** (`services/banco.py`, escolhida por `BANCO` no `.env`): os testes rodam em qualquer
máquina e quem clona o projeto reproduz tudo sem servidor. A aplicação entra com o usuário `ai_payroll_hub_app`,
**sem poderes de administrador** (menor privilégio); o superusuário só prepara o servidor
(`scripts/preparar_postgres.py`). O ponto de salvamento do LangGraph fica no mesmo banco (`PostgresSaver`). Os dados
locais foram copiados por `scripts/migrar_sqlite_para_postgres.py` (tabelas e pontos de salvamento, com
conferência das contagens; nunca sobrescreve um PostgreSQL com dados). Avaliação completa e recomendações para o
crescimento em `docs/banco_de_dados.md` (seções 7 e 8).

**O que a porta resolve** (as diferenças que sobram entre os dois): o sinal dos valores (`?` × `%s`); o número
automático (`AUTOINCREMENT` × `BIGSERIAL`); a coluna `rowid`, que o PostgreSQL não tem (a porta a acrescenta, para a
ordem de gravação continuar igual); "criar a visão se não existir"; a lista de colunas; as somas, que no PostgreSQL
chegam como `Decimal`; e **quando a transação abre**. Este último foi achado pela bateria de testes: no PostgreSQL,
uma simples leitura deixava a transação aberta, segurando uma trava que fazia outra conexão esperar para sempre ao
recriar a visão do planejamento. A porta agora abre transação só antes de gravar, como o `sqlite3` do Python, e
a visão só é criada se ainda não existe. SQL que só o SQLite entendia foi reescrito na forma que os dois aceitam:
7 `INSERT OR REPLACE/IGNORE` viraram `ON CONFLICT`, 3 `PRAGMA` viraram `banco.colunas_da_tabela`, as somas com
condição viraram `SUM(CASE WHEN ...)` e um `SELECT *` virou a lista de colunas.

**Instalação com Docker (2026-09-25).** O `docker-compose.yml` sobe a imagem oficial do PostgreSQL 18 e a aplicação
num comando. Na primeira subida, `docker/postgres/criar_usuario_da_aplicacao.sh` cria o usuário da aplicação (sem
superpoderes) e o banco; a aplicação espera o teste de saúde do banco e cria as tabelas no primeiro uso. Senhas só
no `.env`; dados em volumes; a porta do banco só abre em `127.0.0.1`. Na hospedagem, o mesmo contêiner da aplicação
com um PostgreSQL gerenciado. **Subiu de verdade em 2026-09-25** (Docker Desktop 4.91; ver ADR-68); antes disso, o script
do banco foi rodado contra o PostgreSQL local (`tests/test_docker_compose.py`, 7 testes). Os scripts de avaliação passaram a
forçar um SQLite temporário, para nunca gravar no banco de uso, e o `build_index` lê o layout e o catálogo pela
porta única.

**Trade-off.** Um servidor para manter e uma camada de tradução para entender; em troca, o banco que a produção
precisa já roda desde o MVP, e a prova de que os dois bancos se comportam igual é a mesma bateria de testes.

**Como comprovamos.** A bateria inteira roda nos dois bancos (`$env:BANCO_DOS_TESTES="postgres"` faz cada teste
ganhar um esquema novo no banco de testes). `tests/test_banco.py` (9 testes): tradução dos comandos; somas como
inteiro; leitura que não trava outra conexão; visão não recriada; rollback; usuário da aplicação sem superpoderes;
migração com contagens iguais, login com a mesma senha, contador de id continuado e o fluxo no mesmo ponto; migração
que recusa sobrescrever. Migração dos dados locais: 18 tabelas com contagens iguais e o processamento em andamento
no mesmo ponto do fluxo (mesmo estado e mesmas gravações pendentes). **Origem.** Pedido do dono do projeto,
2026-09-25 (ponto de avaliação da banca).

<a id="adr-68"></a>
### ADR-68 · Docker de verdade: subida sem custo e Streamlit sem estatísticas de uso ✅

**Problema.** A primeira subida real do `docker compose` (2026-09-25) mostrou três riscos que o papel não mostrava:
(1) o contêiner herda do `.env` o `MODE=llm` e as chaves de API, então um teste "só para ver se sobe" usaria a IA real,
com custo; (2) no PowerShell 5.1, apagar a chave com `$env:OPENAI_API_KEY = ''` não funciona (variável vazia é
removida e o Compose volta a ler o `.env`), e `docker compose config` imprime senhas e chaves na tela; (3) o Streamlit,
por padrão, **manda estatísticas de uso** para os servidores dele e mostra um botão "Deploy" a quem usa a aplicação.

| Opção | A favor | Contra |
|---|---|---|
| Tirar `MODE` e chaves do `docker-compose.yml` | Nunca há custo por engano | A demo publicada precisa da IA real; teria de voltar |
| **Segundo arquivo do Compose para subir sem custo** | O `docker-compose.yml` continua o da produção; o teste sem custo é explícito | Um arquivo a mais no comando |
| Confiar em lembrar de trocar o `.env` | Nada a fazer | Fácil de esquecer; gasto real sem querer |

**Decisão.** O `docker-compose.yml` continua igual (é o da produção). Para subir sem custo, um segundo arquivo do
Compose sobrescreve, só no serviço `aplicacao`, `MODE: mock` e as duas chaves vazias (receita no README, "Cuidados").
`docker compose config` nunca é usado com a saída à vista. E `.streamlit/config.toml` (versionado, sem nenhum segredo)
desliga as estatísticas de uso (`gatherUsageStats = false`) e deixa a barra do canto no modo mínimo (sem "Deploy").

**Subida real (2026-09-25).** Imagem construída; banco saudável em cerca de 6 segundos; usuário da aplicação sem
superpoderes (sem superusuário, sem criar banco, sem criar papel); o `preparar_servidor.py` montou os índices do RAG
(baixou o modelo de embeddings) e **não** criou os usuários da demo, porque as senhas deles não estavam definidas (é o
comportamento do ADR-64); a tela de login abriu na porta 8501 sem erros de JavaScript. Dentro do contêiner, `MODE=mock`
e as duas chaves com 0 caracteres. A imagem não contém o `.env` nem a pasta `storage/` (`.dockerignore`).

**Trade-off.** O comando de teste fica mais longo. O login no contêiner ainda não foi testado: depende das senhas dos
usuários da demo, que são credenciais do dono do projeto.

**Como comprovamos.** Na subida real: a variável `MODE` e o tamanho das chaves conferidos dentro do contêiner; a
imagem inspecionada sem `.env`; o log sem a linha "Collecting usage statistics" e a tela sem o botão "Deploy" depois
do `config.toml`; a bateria inteira (539 testes) passando. **Origem.** Modo despertador, 2026-09-25.

<a id="adr-69"></a>
### ADR-69 · Novo front (páginas do layout) ligado por uma API FastAPI, com porteiro por perfil ✅

**Status.** Decidido pelo dono do projeto em 2026-09-25: a forma da integração é esta (API FastAPI + páginas do
layout), e o ramo `integracao-front` foi juntado à `main`. Até essa data, era provisório num ramo separado. O
Streamlit continua funcionando, sem nenhuma mudança.

**Problema.** O layout aprovado (Portal Empresa e Portal do Banco, `D:\AI_Payroll_Hub\Layout_App`) é HTML, CSS e
JavaScript puros, com dados de exemplo. Para virar a ferramenta, as páginas precisam falar com os serviços que já
existem (login, sessões, envios, agentes, planejamento), sem reescrever a lógica que os 539 testes protegem.

| Opção | A favor | Contra |
|---|---|---|
| **Páginas do layout + API (FastAPI) chamando os serviços atuais** | O layout aprovado vira o front sem perder nada; os serviços e os testes ficam como estão; API com contrato claro | Um segundo servidor para manter; cada tela precisa das suas rotas |
| HTML do layout dentro do Streamlit | Um servidor só | O Streamlit redesenha a página inteira a cada clique; o JavaScript do layout não conversa bem com ele |
| Streamlit só para o banco, layout só para a empresa | Menos trabalho agora | Duas experiências diferentes; o Portal do Banco desenhado ficaria de fora |

**Decisão (provisória).** As páginas do layout foram copiadas para `front/` (o layout em `Layout_App` continua como
referência de desenho). `api/principal.py` é o servidor: entrega as páginas e responde em `/api`. Primeiro passo:
- `POST /api/entrar`, `GET /api/eu` e `GET /api/sair`, reaproveitando `services/auth.py` e `services/sessoes.py`
  (mesma senha bcrypt, mesmo ingresso com só o hash no banco, mesma validade de 8 horas);
- o cookie da sessão é **httponly** (o JavaScript da página não consegue lê-lo, ao contrário do cookie gravado pelo
  Streamlit, ADR-40), **SameSite=Strict** e **secure** em https;
- a mesma mensagem para qualquer login recusado (não revela se o usuário existe);
- um **porteiro** (middleware) antes de cada página: sem login, volta ao login; página de outro perfil, volta à
  página inicial do próprio perfil. Páginas da empresa só para EMPRESA; do banco só para BANCO; a aba técnica só para
  CIENTISTA (provisório, ver a decisão pendente sobre o perfil CIENTISTA);
- toda página guardada pelo porteiro sai com **`Cache-Control: no-store`**.

**Achado do teste de ponta a ponta.** No navegador de verdade, depois do "Sair", a página do banco abria de novo: o
navegador mostrava a cópia guardada (cache) sem perguntar ao servidor, e o porteiro nem ficava sabendo. O `no-store`
resolve, e virou teste. O teste com o `TestClient` sozinho não pegaria isso, porque ele não guarda cópias.

**Trade-off.** Dois servidores enquanto o Streamlit existir; as telas do front ainda mostram os dados de exemplo do
layout (os próximos passos ligam cada tela aos serviços, uma de cada vez, com testes). O porteiro consulta o banco a
cada página (uma leitura pequena por pedido).

**Como comprovamos.** `tests/test_api_front.py` (15 testes, também no PostgreSQL): login de cada perfil e a página
inicial certa; cookie httponly e SameSite=Strict; resposta sem senha nem ingresso; a mesma recusa para senha errada,
usuário inexistente e desativado, sem gravar cookie; formato do pedido conferido; `/api/eu` com e sem login; "Sair"
que invalida até o ingresso copiado; login e aparência abertos; páginas barradas sem login e por perfil; `no-store`;
nenhum arquivo de fora da pasta `front/` entregue (tentativas com `../.env`). E um teste de ponta a ponta no Chrome
(servidor numa porta própria, SQLite temporário): 10 verificações, inclusive o cookie invisível ao JavaScript e o
"Sair" de verdade. **Origem.** Sugestão provisória registrada em 2026-09-25; modo despertador.

**Passo 2 · Acompanhar cadastros com dados reais.** `services/acompanhamento.py` monta a tela a partir do que a
aplicação já guarda, sem tabela nova: os envios vêm da tabela de processamentos (quando, quem, linhas, situação em
linguagem simples, sem o nome do arquivo) e os funcionários vêm dos arquivos finais das homologações (uma pessoa uma
vez só, pelo envio mais recente). Rotas `GET /api/empresa/resumo`, `/api/empresa/envios` e `/api/empresa/funcionarios`,
**só para o perfil EMPRESA** e sempre com a empresa **da sessão** (um `?empresa_id=` no endereço é ignorado). O CPF sai
mascarado; saem só os campos que a tela e a ficha usam (minimização: nada de nome da mãe, PIS, documento ou
naturalidade). O salário sai, porque a tela aprovada o mostra e o dado é da própria empresa. A tabela do front troca a
amostra pelos funcionários reais quando a página é servida pela API; aberta sem servidor, continua com a amostra.
**Fica para depois:** o CPF inteiro na ficha e no download, com registro na auditoria (T10), e os envios e pendências
reais na mesma tela. **Como comprovamos:** `tests/test_acompanhamento.py` (9 testes, SQLite e PostgreSQL): máscara do
CPF, envio homologado com quem enviou, campos permitidos, **Empresa A nunca vê a B** (serviço e API), inclusão sem
repetir pessoa, resumo com envio em andamento, 401 sem login e 403 para o banco. Ponta a ponta no Chrome: 35
funcionários reais da Aurora, CPF mascarado, filtro de unidades refeito e a ficha com CNPJ e histórico reais.

**Passo 3 · Envios e pendências reais em Acompanhar cadastros.** Cada envio traz a **linha do tempo** com as datas
tiradas da trilha de auditoria (Enviado → Lido pela IA → Conferido por você → Cadastrado), com a etapa em que ele parou
marcada. A etapa "Análise do banco" do layout ainda não existe na aplicação: entra quando a avaliação do banco existir.
`GET /api/empresa/pendencias` devolve os achados do Validador em aberto nos envios da empresa (bloqueante vira
"Corrigir dado"; alerta não justificado, "Confirmar"), com o nome da pessoa e o que fazer; os valores vêm mascarados pelo
próprio Validador. Na tela, as pendências reais aparecem só para leitura: corrigir por esta tela depende de ligar o
fluxo de cadastro ("Cadastrar funcionários"), o próximo passo. O teste de ponta a ponta achou um **empate na ordem dos
envios** criados no mesmo segundo; `processamentos.listar` passou a desempatar pela ordem de gravação (`rowid`, que a
porta do banco também oferece no PostgreSQL). **Como comprovamos:** 5 testes novos (linha do tempo completa e parada,
pendências com nome e sem CPF inteiro, sem pendência depois de cadastrado, desempate) e as 4 rotas da empresa recusando
sem login e para o banco; ponta a ponta no Chrome: Aurora com 2 envios na ordem certa e "Tudo em dia!", Brisa com a
pendência real e os números do resumo batendo com a lista.

**Passo 4 · Resolver pendências pela tela nova e resumo real.** `POST /api/empresa/pendencias/corrigir` e `/confirmar`
usam os MESMOS serviços do Streamlit (`correcoes.propor` + `correcoes.decidir`; `validador.justificar_alerta`), então as
duas telas ficam consistentes. Digitar o valor e clicar em "Salvar correção" já é a decisão humana: o pedido e a
aplicação ficam registrados com quem propôs e quem aprovou (o mesmo login), antes e depois, e o envio é validado de novo.
O valor passa pelas regras do Normalizador (ex.: "ontem" é recusado com "formato de data desconhecido"); motivo e
justificativa são obrigatórios. A pessoa repetida se resolve tirando a linha repetida (a correção especial EXCLUIR),
não corrigindo o CPF. Envio de outra empresa responde 404, sem dizer se ele existe. Os números do alto da tela passam a
ser os reais (cadastrados, envios em andamento, envios); a abertura das contas, que a aplicação ainda não recebe,
aparece como "ainda não chegou" em vez do percentual de exemplo. **Como comprovamos:** 7 testes novos (corrigir,
recusar valor e motivo vazio, outra empresa, confirmar com e sem justificativa, tirar a linha repetida, e as rotas na
API com 400/404/401), também no PostgreSQL; ponta a ponta no Chrome com Horizonte, Prisma e Brisa (10 verificações).

**Passo 5 · CPF inteiro só na ficha e no download, sempre registrado.** Na lista, o CPF continua mascarado. Os dois
únicos lugares com o CPF inteiro são a ficha (`GET /api/empresa/funcionarios/{id}`) e o download (`POST
/api/empresa/funcionarios/baixar`, com as pessoas que estão filtradas na tela). A pessoa é pedida por um identificador
(envio.posição no arquivo final), nunca pelo CPF no endereço; identificador de outra empresa dá 404 na ficha e é
ignorado no download. Cada acesso fica em **`acessos_a_dados`** (quem, quando, ficha ou download, quantas pessoas),
uma tabela própria porque a trilha de auditoria é organizada por envio; o CPF nunca é gravado ali. O CSV sai para o
Excel (";" e UTF-8 com a marca), com toda célula protegida contra fórmula (a mesma `neutralizar_formula` da
homologação), e as duas respostas saem com `Cache-Control: no-store`. **Como comprovamos:** 5 testes novos (ficha com
CPF inteiro e acesso registrado; ficha de outra empresa barrada sem registrar; download só com as pessoas da empresa,
CPF inteiro e quantidade registrada; download vazio recusado; célula "=HYPERLINK" neutralizada) e o teste de API (200,
404, 400, 403 e os cabeçalhos), também no PostgreSQL; ponta a ponta no Chrome: ficha com o CPF inteiro, download com as
4 pessoas filtradas e os dois acessos registrados. Cumpre o T10 (download auditado) do checklist.

**Passo 6 · Cadastrar funcionários: o servidor.** `services/cadastro.py` liga o recebimento do arquivo
(`processamentos.receber_arquivo`) ao fluxo em LangGraph (`workflows/fluxo_empresa.py`), sem regra nova: enviar roda o
fluxo até a IA propor o mapeamento; a leitura devolve as colunas com o campo proposto, a justificativa, o que precisa de
decisão (AMBIGUO) e os obrigatórios sem coluna; aceitar, homologar e descartar entregam o clique à pausa certa do fluxo
(`fluxo_empresa.responder` / `retomar`), o mesmo caminho do Streamlit. Rotas `/api/empresa/cadastro/enviar` (arquivo
pelo formulário do navegador), `/{id}` (leitura), `/{id}/aceitar`, `/{id}/homologar` e `/{id}/descartar`, só EMPRESA e
com a empresa da sessão. Homologar com pendência revalida e, se a pendência continua, recusa com a etapa em que o
arquivo está (nada é cadastrado). `python-multipart` fixado no `requirements.txt` (o envio de arquivo precisa dele e,
até aqui, ele só vinha por tabela). A tela ainda usa a simulação do layout: ligá-la é o próximo passo. **Como
comprovamos:** `tests/test_cadastro.py` (10 testes, SQLite e PostgreSQL): o fluxo até o mapeamento, o aceite sem
decidir a ambígua (não avança e explica), do aceite à homologação (a inclusão entra na lista), homologar com pendência
recusado sem cadastrar, descartar, reenvio idêntico, arquivo que não serve, outra empresa barrada (serviço e API) e as
recusas 401/403.

**Passo 7 · Cadastrar funcionários: a tela.** Com a página servida pela API, escolher ou arrastar um arquivo deixa de
ser simulação (`front/js/cadastrar_real.js`): o arquivo vai ao servidor, o painel da IA conta o que ela leu de verdade
(linhas, colunas reconhecidas, deixadas de fora, as que pedem escolha, o reuso do mapeamento aprovado e o reenvio), e o
bloco novo "resultado-real" mostra cada coluna com o campo proposto e o motivo. Nas colunas ambíguas, a pessoa escolhe
entre os candidatos da IA ou "Deixar de fora"; aceitar sem escolher volta com o recado do fluxo. Depois do aceite, a
tela mostra só o botão da etapa: "Cadastrar os funcionários" (sem pendência), "Resolver as pendências em Acompanhar
cadastros" (com pendência) ou "Ver em Acompanhar cadastros" (fim); "Descartar esta leitura" vale enquanto o fluxo
espera uma decisão. Os botões de exemplo continuam sendo a demonstração animada do layout, marcados como
"demonstração". Nesta versão, um arquivo por envio (a leitura multiformato é um passo futuro). **Como comprovamos:**
ponta a ponta no Chrome (SQLite temporário, MOCK): Atlântico com a coluna ambígua recusada sem escolha e aceita com
"Deixar de fora", seguindo para as pendências; Aurora (inclusão, mapeamento reaproveitado) cadastrada, com a lista de
Acompanhar crescendo de 35 para 40; Horizonte descartada sem cadastrar (13 verificações). O teste mostrou que o
arquivo `.xlsx` da demo muda a cada geração (o Excel grava a hora), então o teste de ponta a ponta sempre começa de
um banco limpo.

**Passo 8 · Portal do Banco: Planejamento e Consultor com dados reais.** `services/portal_do_banco.py` só formata para a
tela o que `services/planejamento.py` e o Agente Consultor já fazem (nenhuma conta nova): opções de filtro com os valores
que existem nos números do motor, indicadores, resumo, por empresa e por região, o ganho com a mesma fórmula (sem taxa:
recusado; dinheiro em texto, para não perder centavos), as simulações salvas com quem simulou e o Consultor (MOCK sem
provedor), com fontes e limitações. Rotas `/api/banco/planejamento`, `/filtros`, `/ganho`, `/simulacoes` e
`/api/banco/consultor`, só para o perfil BANCO; operação fora do perfil vinda dos serviços vira 403 (o ajudante da API
passou a se chamar `executar_acao`, porque serve aos dois portais). A tela do Planejamento, servida pela API, troca os
exemplos pelos números reais, projeta o ganho no servidor e pergunta ao Consultor de verdade; aberta sem servidor,
continua a demonstração. **Como comprovamos:** `tests/test_portal_do_banco.py` (7 testes): filtros, números iguais aos
do serviço com e sem filtro, a mesma fórmula e a recusa sem taxa, simulação só do banco, Consultor só do banco e sem CPF
nem nome de funcionário, e as rotas com 401/403. Ponta a ponta no Chrome: 40 funcionários da Aurora, 16 contas a abrir,
12 a reconhecer, total com 15% = R$ 9.416,93 calculado no servidor, simulação salva e o Consultor respondendo com a
fonte e a limitação.

**Passo 9 · Início do banco e aba Técnico com dados reais.** O Início (`GET /api/banco/inicio`, só BANCO) monta a
carteira a partir dos mesmos números que cada empresa vê em Acompanhar cadastros: cadastrados, envios, em andamento,
com pendência e a situação ("Sem carga", "Com pendência", "Em andamento", "Em dia"); a fila "O que precisa de você"
começa pelas empresas sem carga (as que mais arriscam desistir, a meta do business case), depois as paradas em
pendência e as em andamento. Só contagens: nenhum funcionário. O que a aplicação ainda não tem aparece de outro jeito:
o primeiro cartão mostra os envios em andamento (a avaliação do banco ainda não existe) e o último, os cadastrados
(o arquivo de contas abertas ainda não chega). A aba Técnico (`GET /api/tecnico/painel`) mostra as execuções gravadas
pelos agentes com os campos técnicos (etapa, agente, situação, tempo, tokens e custo, "não medido" em MOCK); a
permissão é conferida no serviço (`acesso.execucoes_do_painel`, hoje o perfil CIENTISTA). **Como comprovamos:** 3
testes novos (carteira com a situação de cada empresa e a fila começando pela sem carga; painel técnico só para o
cientista e sem dado de pessoa; rotas por perfil). Ponta a ponta no Chrome: 6 empresas, fila de 5 itens, 40
cadastrados, especialista barrado na aba Técnico e o cientista vendo as 23 execuções reais.

**Passo 10 · Uso das empresas com dados reais.** A tela (`GET /api/banco/uso`, só BANCO) usa apenas o que a
aplicação já grava, sem tabela nova: os **acessos** e o último acesso saem das sessões de login (cada entrada no
portal cria uma sessão, ligada à empresa pelo usuário); o **funil** sai dos eventos da auditoria de cada envio
(arquivo recebido → a IA leu as colunas → colunas conferidas → cadastrado), contando cada envio uma vez por etapa;
os **descartes** são as leituras encerradas pela empresa; a **linha do tempo** são os mesmos eventos em ordem, só
com a data e o que aconteceu. Nenhum funcionário aparece. **Opção descartada:** gravar "abriu a tela de cadastro" para
manter a primeira etapa do funil do layout; seria um registro novo de navegação só para a tela, então essa etapa sai no
modo real (o exemplo do layout continua com ela). A pista do motivo e o tempo até a avaliação do banco também ficam
fora: o primeiro não é registrado e o segundo depende da avaliação pelo banco, que ainda não existe; o cartão mostra
"—" em vez de um número inventado. **Como comprovamos:** 1 teste novo do serviço (acessos pelas sessões, funil da
empresa que cadastrou e da que parou no aceite, linha do tempo sem dado pessoal, funil da carteira = soma) e as
rotas por perfil; os mesmos testes passam no PostgreSQL. Ponta a ponta no Chrome: 13 conferências (6 empresas na
tabela, funil de 4 etapas, "Nunca entrou" para quem não entrou, cartões reais, linha do tempo da Aurora, empresa
pedida no endereço, nenhum CPF, nenhum erro de JavaScript).

**Passo 11 · Empresas com dados reais.** A ficha de cada empresa (`GET /api/banco/empresas`, só BANCO) junta o que a
aplicação já tem: nome, setor e cidade; os números do contrato (os mesmos do Início); as pessoas do RH cadastradas
(perfil EMPRESA), com o último acesso tirado das sessões e **nunca a senha**; e os documentos vigentes do catálogo de
benefícios da empresa, com versão, vigência e seções. O banco **desativa ou reativa** uma pessoa pela tela
(`POST /api/banco/empresas/usuarios/{login}/situacao`), pela mesma porta de acesso do Streamlit
(`acesso.definir_ativo`: confere o perfil de quem pede e derruba as sessões do desativado na hora). **Regra nova:**
esta rota só mexe em pessoas de empresa; um usuário do banco ou do cientista é recusado (400), para a tela de uma
empresa nunca desligar quem trabalha no banco. **O que continua como demonstração, com aviso honesto na tela:** o
convite por e-mail (hoje o banco cadastra a pessoa na tela Usuários do Streamlit), o kit de endomarketing (não é
gravado), a nova versão do catálogo por esta tela (hoje pela tela Parâmetros) e o cadastro de empresa nova; CNPJ,
endereço completo e domínio de e-mail ainda não são cadastrados. **Opção descartada:** inventar nome e e-mail para as
pessoas; a aplicação guarda o login, e a tabela mostra o login. **Como comprovamos:** 2 testes novos do serviço
(ficha com usuários, último acesso e catálogo só da própria empresa; desativar derruba a sessão, reativar devolve o
acesso, usuário do banco e login inexistente recusados, a empresa não desativa ninguém) e as rotas por perfil; os
mesmos testes passam no PostgreSQL. Ponta a ponta no Chrome: 15 conferências (6 empresas, ficha real, desativar
derruba a sessão aberta do RH e barra o login, reativar devolve, convite avisa, catálogo com as seções, empresa pelo
endereço, nenhum CPF e nenhum erro de JavaScript).

**Passo 12 · Aba Telemetria: Uso e Técnico unificados (decisão do usuário, 2026-09-25).** No teste do usuário, as
abas Uso e Técnico "pareciam a mesma tela". **Causa:** o menu mostrava todas as abas para todos os perfis, e o
porteiro devolvia cada perfil à sua página; o cientista clicava em "Uso" e caía de novo no Técnico. **Decisão do
usuário:** uma aba só, **Telemetria**, com duas sub-abas: **Uso das empresas** (acessos, funil, linha do tempo) e
**Desempenho da IA** (nome provisório; qualidade por modelo, custo, experimentos e execuções dos agentes), visível
para o especialista (BANCO) e para o cientista de dados (CIENTISTA), "para simplificar a visão de acessos". **O que
mudou:** `front/banco_telemetria.html` substitui `banco_uso.html` e `banco_tecnico.html`; rotas
`/api/banco/telemetria/uso` e `/api/banco/telemetria/ia` (BANCO ou CIENTISTA); a operação `ver_execucoes`
(`services/permissoes.py`) passa a valer também para o BANCO (as execuções só têm campos técnicos, nenhum dado de
pessoa); o cientista entra direto em `banco_telemetria.html?aba=ia`; `/api/eu` devolve as páginas que o perfil abre
(`paginas_permitidas`, pela mesma regra do porteiro) e `js/menu_por_perfil.js` esconde as abas que o perfil não abre
(o cientista vê só Telemetria). O Painel Técnico do Streamlit continua só do CIENTISTA. **Trade-off:** o especialista
passa a ver custo e execuções da IA (sem dado de pessoa); ganha-se um lugar só para acompanhar a ferramenta, e o
Painel Técnico do plano (§3) continua existindo, agora como sub-aba. **Como comprovamos:** testes do porteiro, das
rotas e da porta de acesso atualizados (empresa barrada nas duas rotas; banco e cientista passam), teste novo das
páginas por perfil; 604 testes. Ponta a ponta no Chrome: 12 conferências (menus por perfil, troca de sub-aba, dados
reais nas duas, cientista direto no Desempenho da IA, páginas antigas fora do ar, nenhum erro de JavaScript).

**Passo 13 · Início, Benefícios e Endomarketing da empresa com dados reais.** `services/portal_da_empresa.py` junta o
que os serviços já têm, sempre da empresa da sessão: o **Início** (`GET /api/empresa/inicio`: nome, números dos
cadastros, etapa da jornada, linhas a corrigir e quantos ainda não têm conta, só o total da empresa e com mínimo de
pessoas, ADR-30); os **Benefícios** (`GET /api/empresa/beneficios`: as seções do catálogo vigente, separadas em
benefícios e atendimento; a divisão em seções foi para `catalogo.secoes_do_documento`, usada também pela ficha do
banco); e o **Endomarketing** com o agente de verdade (`POST /api/empresa/endomarketing/gerar`, `GET
/api/empresa/endomarketing`, `.../sugestoes` e `POST .../{id}/decidir`). **Regra nova:** o kit de boas-vindas só se
liga a uma inclusão **da própria empresa** que ainda espera o kit (o identificador vem da tela e é conferido). **O que
o agente ainda não faz, com aviso na tela em vez de fingir:** o "Lembrete de conta" (a sugestão vira um comunicado
sobre abrir a conta), os ajustes "mais curto / formal / próximo" e a edição do texto (no modo real, o texto aprovado é
o que foi conferido com o catálogo; para mudar, gera-se de novo). O catálogo real não tem categorias nem as partes
"Como funciona / Quem pode usar / Como contratar" do layout: o cartão mostra o texto do catálogo como ele é, com a
fonte. **Como comprovamos:** 7 testes novos (Início antes e depois da carga; benefícios só da própria empresa e sem
Markdown; rascunho com fontes aprovado só pela própria empresa; destaque com ordem para a IA recusado; kit só para
inclusão da própria empresa; rotas só do perfil EMPRESA); 611 testes. Ponta a ponta no Chrome: 19 conferências.
**Alterado pelo [ADR-115](#adr-115) (2026-09-28):** as rotas `POST /api/empresa/endomarketing/gerar`,
`POST .../{id}/decidir` e `GET .../sugestoes` saíram; a empresa só lista os materiais publicados
(`GET /api/empresa/endomarketing`) e baixa a arte (`GET .../{id}/arte`). Gerar, publicar e retirar são do banco.

**Passo 14 · Mensagens do "Posso ajudar?" no banco de dados.** As conversas entre a empresa e o especialista saem do
navegador (localStorage) e vão para `services/mensagens.py` (tabelas `mensagens_de_ajuda` e `conversas_resolvidas`).
Continua sendo **conversa entre pessoas**: nenhuma IA responde. Regras: a empresa lê e escreve só a **própria**
conversa (a empresa vem da sessão, mesmo que a tela peça outra); só o banco vê todas, responde a uma empresa da carteira
e marca como resolvida; mensagem nova reabre a conversa; mensagem vazia ou com mais de 2.000 caracteres é recusada;
o cientista não conversa com as empresas; o autor gravado é o login. Rotas: `GET/POST /api/empresa/conversa`,
`GET /api/banco/conversas`, `POST /api/banco/conversas/{empresa_id}` e `.../resolver`. No front, `js/conversas.js`
usa o servidor quando a página vem da API (e o navegador, sem servidor) e busca as conversas de novo a cada 15
segundos, para a resposta do outro lado aparecer sozinha; o contador da aba Mensagens passa a ser real. **Opção
descartada:** atualização instantânea (WebSocket); para uma conversa de ajuda, 15 segundos bastam e o servidor fica
simples. **Como comprovamos:** 4 testes novos (conversa entre os dois lados, resolvida e reaberta, recusas, rotas por
perfil), também no PostgreSQL; 615 testes. Ponta a ponta no Chrome: 8 conferências (a empresa escreve, o banco vê com
o contexto e o contador, responde e resolve, a empresa vê a resposta depois de recarregar, outra empresa não vê).

**Passo 15 · Avaliação dos envios pelo banco (aprovar ou devolver com motivo).** O layout aprovado pelo usuário
previa que o especialista avalia cada envio antes do cadastro. **O que mudou no fluxo (LangGraph):** o clique final da
empresa ("Enviar ao banco", antes "Homologar") confere de novo que não há pendência e põe o envio em
`AGUARDANDO_BANCO` (estado novo), com o evento `ENVIADO_AO_BANCO`; o fluxo para na pausa nova **`avaliar_no_banco`**.
Aprovado pelo banco, o arquivo é homologado **naquele momento** (funcionários cadastrados, planejamento liberado; o
`homologado_por` passa a ser quem aprovou) e o evento é `APROVADO_PELO_BANCO`. Devolvido, o envio vai para `DEVOLVIDO`
(estado novo), com o motivo na auditoria (`DEVOLVIDO_PELO_BANCO`, até 500 caracteres) e como recado da pausa de
correção; a empresa ajusta e envia de novo. Devolver sem motivo é recusado. **Onde aparece:** a aba Envios do banco
(`services/avaliacao_do_banco.py`: fila, trilha, alertas confirmados pela empresa, pessoas com o CPF mascarado; rotas
`/api/banco/envios`, `.../pessoas` e `.../avaliar`, operação nova `avaliar_envios` só do BANCO); o Início do banco
(envios esperando e atrasados, e "Avaliar o envio" no topo da fila do dia); Acompanhar da empresa ("Em análise pelo
banco", "Devolvido pelo banco" com o motivo, a etapa "Enviado ao banco" na linha do tempo); e o **Streamlit** (o
Portal diz "Enviar ao banco" e o Cockpit ganhou "Envios esperando a sua avaliação"), para quem ainda usa as telas
antigas não ficar travado. **O que ficou de fora, com aviso:** pedir ajuste de uma pessoa só (o pedido vai no motivo da
devolução do envio inteiro) e contar os valores padronizados pela IA ("—"). **Trade-off:** um passo humano a mais antes
do cadastro (e a avaliação do fluxo, EXP-004, conta essa decisão; recongelada com o motivo). **Como comprovamos:**
testes do fluxo (envio → avaliação → aprovado; devolvido com motivo → reenviado → aprovado; devolver sem motivo pede de
novo), 4 testes novos da avaliação (fila, pessoas mascaradas, devolver e aprovar, só o banco, rotas), testes das telas
do Streamlit (a empresa envia e o especialista aprova pelo Cockpit), também no PostgreSQL; 621 testes. Ponta a ponta no
Chrome: 12 conferências (Início com o envio esperando, fila, trilha, CPF mascarado, devolução com motivo, a empresa vê
o motivo, reenvia, o banco aprova e a empresa vê cadastrado).

**Passo 16 · Contas abertas: o arquivo semanal do banco dá baixa por funcionário.** `services/contas_abertas.py`
(tabelas `contas_abertas` e `arquivos_de_contas`). O especialista sobe o arquivo (CSV ou Excel, lido pela mesma
ingestão das empresas, com o guardrail); a coluna de CPF é achada pelo nome. O sistema confere os dígitos de cada CPF,
procura entre os funcionários cadastrados da carteira e devolve uma **prévia** (novas, repetidas, fora da carteira,
inválidas e o que muda em cada empresa) **sem gravar nada**; só o "Confirmar a baixa" grava as contas novas (com o
arquivo e a data), e descartar apaga os CPFs da prévia. **Privacidade:** a prévia e o histórico nunca mostram o CPF
inteiro; CPF de fora da carteira não é guardado depois da decisão; a **empresa** vê só o total da empresa inteira e só a
partir do mínimo de pessoas das premissas (ADR-30, hoje 10), nunca quem abriu. Operação nova `dar_baixa_em_contas`, só
do BANCO. Rotas `POST /api/banco/contas/conferir`, `.../{id}/confirmar`, `.../{id}/descartar` e
`GET /api/banco/contas/historico`; o resumo da empresa (`/api/empresa/resumo`) ganha `contas`. **Onde aparece:** a tela
Contas abertas (prévia, confirmação e histórico reais), o Início do banco (percentual da carteira), a ficha de cada
empresa, o Acompanhar da empresa (o anel e as frases com o total) e a etapa 4 da jornada no Início da empresa. **Fora
desta versão:** a divisão por unidade e por envio no painel da empresa (a tela mostra só o total). **Como
comprovamos:** 4 testes novos (prévia sem gravar e sem CPF inteiro; confirmar, repetida na semana seguinte, descartar e
histórico; a empresa vê só o total e só o banco sobe; rotas por perfil), também no PostgreSQL; 626 testes. Ponta a ponta
no Chrome: a prévia (20 novas, 1 repetida, 1 fora, 1 inválida), a baixa, o histórico, o Início do banco (57%), o Início e
o Acompanhar da empresa ("20 de 35"), CPF sempre mascarado.

**Passo 17 · Cadastrar: formato de coluna, conferência da lista, "Ajude a IA a acertar" e vários arquivos.** Tudo
com o que o servidor já tinha, ligado à tela (`services/cadastro.py`): (1) **formato de coluna** — a dúvida de uma
coluna inteira (datas dia/mês ou mês/dia; quantos dígitos tem a matrícula) aparece na leitura e em Acompanhar, e a
decisão (`POST .../formato`) vai para o fluxo (`decidir_colunas`), que padroniza de novo; (2) **conferência da lista**
— a lista do jeito que vai para o banco (`GET .../lista`), com "Corrigir" em cada linha (`POST .../lista/corrigir`: o
pedido é registrado com quem corrigiu e o motivo fixo "Corrigido pela empresa na conferência da lista", aplicado e
revalidado); a exibição segue a regra de Acompanhar (CPF mascarado; nome da mãe, PIS, documento e endereço residencial
completo mascarados; o resto como está); (3) **"Conferi a lista"** — o "Enviar ao banco" só liga depois de marcar, e
fica registrado (`LISTA_CONFERIDA`), aparecendo na trilha do banco; (4) **"Ajude a IA a acertar"** (`POST .../reler`) —
a IA relê UMA coluna com a dica da empresa (o mesmo remapeamento do Assistente de Correção: guardrail na dica, limite de
2 releituras) e o mapeamento volta ao aceite; (5) **vários arquivos** — cada arquivo vira um envio próprio. **Achado do
ponta a ponta (corrigido):** no aceite, só as colunas ambíguas deixavam escolher o campo; se a IA erra uma coluna
"reconhecida" (ex.: depois de uma releitura), a empresa não tinha como corrigir. Agora toda coluna tem a escolha, com o
campo da IA marcado, e só as colunas mudadas vão para o servidor. **Fora desta versão:** a dica livre sobre o arquivo
inteiro (a releitura é sempre de uma coluna). **Como comprovamos:** 4 testes novos (formato de coluna e a coluna da
pendência em Acompanhar; conferência, correção registrada e "Conferi a lista" na trilha do banco; releitura com dica,
recusa de dica vazia ou com ordem para a IA e de outra empresa; rotas só da empresa dona), também no PostgreSQL; 630
testes. Ponta a ponta no Chrome: 12 conferências.

**Passo 18 · Cadastro das empresas no banco de dados: empresa nova, editar dados, convite, kit e catálogo.** As
empresas deixaram de ser só o arquivo `data/mock/empresas.json`: agora ficam na tabela `empresas`
(`services/empresas.py`), que começa com as 6 da **semente** (o arquivo ganhou CNPJ, endereço comercial, domínio de
e-mail e data do contrato; os CNPJs são os mesmos dos dados sintéticos) e cresce quando o especialista cadastra uma
empresa nova (código seguinte, ex.: EMP007; CNPJ com dígitos conferidos e sem repetir; domínio de e-mail; UF). **Decisão
de arquitetura:** `dados_mock.empresas()`, usada em 28 lugares (inclusive dentro do Consultor e de validadores que não
recebem a conexão), continua com o mesmo nome e formato, mas lê da tabela, com a lista guardada em memória por 5
segundos e renovada na hora quando uma empresa é criada ou editada. **Opção descartada:** passar a conexão por esses 28
lugares, que mexeria em componentes já medidos (Consultor). **Trade-off:** outro processo (o Streamlit) vê uma empresa
nova em até 5 segundos. Também: **editar dados** e **kit de endomarketing** (padrão ou próprio, com descrição e até 5
cores) gravados; **convite de usuário** — login = e-mail do domínio da empresa, com senha provisória aleatória mostrada
UMA vez ao especialista (a aplicação não manda e-mail; a pessoa troca no primeiro acesso); **nova versão do catálogo**
pela tela (.md ou .txt até 200 KB, guardrail de injeção, a versão anterior fica guardada) e o índice de busca do
catálogo é refeito na hora (só ele; alguns segundos, embeddings locais). Operação nova `editar_empresas`, só do BANCO.
Rotas `POST /api/banco/empresas`, `.../{id}/dados`, `.../{id}/kit`, `.../{id}/convite` e `.../{id}/catalogo`.
**Cuidado de teste:** o índice fica em `storage/indices` (pasta fixa); um ponta a ponta que publica catálogo num banco
de teste reescreve o índice, que precisa ser refeito do banco real (`scripts/build_index.py`). **Como comprovamos:** 5
testes novos (semente e empresa nova na lista na hora; CNPJ repetido e inválido; editar e kit; convite só do domínio e a
senha provisória entra; catálogo novo passa pelo guardrail e aparece na vitrine; rotas por perfil), também no
PostgreSQL; 636 testes. Ponta a ponta no Chrome: 13 conferências (empresa nova, CNPJ repetido, editar, convite, kit,
catálogo, a pessoa convidada entra e vê a vitrine da empresa nova).

**Passo 19 · Cabeçalho real, contadores e "Minha senha".** `services/cabecalho.py` + `GET /api/cabecalho` (qualquer
perfil logado) e `js/cabecalho_real.js` em todas as 12 telas com login: o nome fixo do layout ("Marina Costa",
"Rafael Lima") dá lugar ao login de quem entrou, com o papel ("RH · <empresa>", "Especialista do banco", "Cientista de
dados") e as iniciais tiradas do login; o **sino** conta o que pede atenção (banco: envios esperando a avaliação +
conversas sem resposta; empresa: pendências para corrigir + envios devolvidos) e leva à tela onde se resolve; a aba
**Envios** do banco mostra os envios esperando. Clicar no nome abre **"Minha senha"** (`POST /api/minha-senha`): senha
atual, nova e confirmação (tamanho mínimo de `auth.TAMANHO_MINIMO_SENHA`); é o caminho da senha provisória do convite.
**Como comprovamos:** 3 testes novos (iniciais; cabeçalho por perfil com os contadores; troca de senha com confirmação
diferente, senha atual errada, senha curta, a nova entra e a antiga não; sem login, 401), também no PostgreSQL; 639
testes. Ponta a ponta no Chrome: 8 conferências (cabeçalho real nas 7 telas do banco, aba Envios e sino com os números
reais, senha errada recusada, nova senha entra, cabeçalho da empresa).

<a id="adr-70"></a>
### ADR-70 · A memória que aprende: mapeamentos aprovados pelo banco entram na busca do RAG ✅

> **Alterado pelo [ADR-116](#adr-116) (2026-09-28):** o mínimo de empresas que confirmam o mesmo par subiu de 1 para 2.

**Problema.** Cada envio aprovado grava no banco os pares "coluna da planilha → campo do layout" que a empresa aceitou
(tabela `historico_mapeamentos`, ADR-38). Mas o índice do RAG era montado só a partir do histórico **sintético**
(`data/synthetic/historico_mapeamentos.csv`): a tabela do banco era gravada e ninguém lia. A mesma empresa já se
beneficiava (o último mapeamento aprovado é reaproveitado, ADR-24), mas **entre empresas a IA não aprendia**: se a
Aurora aprovou "Sal. Bruto → valor_renda", a planilha da Cedro com "Sal. Bruto" começava do zero. Nos tipos de memória
da IA (apresentação, slides 15 a 17), era a **memória episódica** sem ciclo de aprendizado.

| Opção | A favor | Contra |
|---|---|---|
| Deixar como está | Nada muda; avaliação intacta | A IA não aprende com o uso; o banco guarda um histórico que não serve para nada |
| Juntar os pares aprovados no índice do layout | Uma busca só | A avaliação congelada mediria um índice que muda com o uso; o par de uma empresa poderia ensinar errado as outras |
| **Índice próprio de mapeamentos aprovados, com regras de entrada e interruptor** | O ciclo fecha; a avaliação continua medindo o conhecimento congelado; cada risco tem uma regra | Um índice a mais; o índice é refeito a cada aprovação |
| Ajuste fino (Fine-Tuning) com os pares | O modelo "aprende de verdade" | Depende do provedor (ADR-06); não é auditável nem apagável par a par |

**Decisão.** Um terceiro índice no ChromaDB, `mapeamentos_aprovados` (`rag/aprendizado.py`):
- **Quando entra:** o histórico só é gravado quando o **banco aprova o envio** (a homologação acontece na aprovação,
  ADR-69 passo 15). Logo depois, `homologacao.homologar` chama `aprendizado.aprender_depois_da_aprovacao`, que refaz o
  índice inteiro a partir da tabela. O `scripts/build_index.py` também refaz o índice (servidor novo, máquina nova).
- **Regras de entrada** (cada uma contra um risco):
  - pelo menos `MINIMO_DE_EMPRESAS_PARA_APRENDER` empresas aprovaram o mesmo par. **Hoje 1** (regra do dono do projeto,
    2026-09-25: basta o banco aprovar); com 2, uma empresa sozinha não consegue ensinar errado as outras;
  - o campo existe no layout ativo;
  - o nome da coluna passa no guardrail e tem até 60 caracteres: ele vai parar no pedido de **outras** empresas, então
    não pode carregar uma instrução escondida;
  - nenhum nome ou código de empresa no trecho: só "aprovada por N empresa(s)" (a fonte citada é
    "Mapeamentos aprovados › coluna");
  - **conflito** (a mesma coluna aprovada como campos diferentes): cada trecho avisa o outro campo, e a IA pode pedir
    ajuda em vez de escolher sozinha.
- **Como a busca usa:** `search_rules` junta os candidatos do índice do layout e do índice dos aprovados, ordena pela
  distância e mantém um trecho por campo (como antes). O trecho aprovado compara **só o nome da coluna**: esta memória
  serve para reconhecer o mesmo cabeçalho de novo. Com a descrição do campo junto (o jeito do histórico sintético,
  ADR-42), o cabeçalho idêntico ficava atrás de outros trechos (distância 0,573 contra 0,559 de um campo errado, no
  teste); só com o nome, ele vem primeiro.
- **O interruptor:** a busca só consulta os aprovados quando a aplicação liga o aprendizado
  (`busca.ligar_mapeamentos_aprovados()`, chamado ao abrir a API e o Streamlit). Os scripts de avaliação não ligam:
  a prova congelada (ADR-58) continua medindo o mesmo conhecimento, sem nenhum arquivo congelado alterado. Nos testes,
  `APRENDIZADO_DO_RAG=desligado` (`tests/conftest.py`) faz o pedido para ligar ser ignorado, e nenhuma homologação de
  teste toca o índice real.
- **Falha no índice** (ex.: modelo de embeddings ausente) não desfaz a aprovação do banco: fica um aviso no terminal,
  e o próximo `build_index` refaz o índice a partir do histórico.

**Trade-off.** Refazer o índice inteiro a cada aprovação custa alguns segundos de embeddings locais (sem IA externa,
sem custo); com milhares de pares, a evolução é acrescentar só os pares novos. Com o mínimo de 1 empresa, uma empresa
que aprove um par errado de propósito influencia as outras até alguém perceber; a defesa é a avaliação do banco em
cada envio, e subir o mínimo para 2 é mudar um número. O nome da coluna pode citar a própria empresa ("Salário
Aurora"); o risco é baixo (é um cabeçalho, não um dado pessoal) e o guardrail barra o que tem cara de instrução.
O ganho medido na prova ainda não existe: a prova mede o conhecimento congelado de propósito; medir o ganho do
aprendizado pede uma prova própria (planilhas "de volta", com cabeçalhos já aprovados), registrada como evolução.

**Como comprovamos.** `tests/test_aprendizado_rag.py` (15 testes): par aprovado por 1 empresa entra; com mínimo 2,
a mesma empresa duas vezes (com maiúsculas e espaços diferentes) não basta e a segunda empresa faz entrar; campo fora
do layout não entra; coluna com instrução, longa demais ou vazia não entra; nenhum código de empresa no trecho;
conflito avisado nos dois trechos; desligado, a busca ignora os aprovados; ligado, o cabeçalho aprovado vem primeiro;
ligado sem índice de aprovados, a busca segue; nos testes, ligar é ignorado; desligado, a aprovação não cria índice;
ligado, a aprovação refaz o índice; falha no índice não levanta erro. Em `tests/test_correcao.py`, a homologação da
Aurora com o aprendizado ligado leva todos os pares do histórico ao índice, sem o código da empresa.
`tests/test_rag.py`: o `build_index` monta os três índices (nenhum aprovado num banco novo). **Origem.** Pedido do
dono do projeto, 2026-09-25 (regra: basta o banco aprovar).

<a id="adr-71"></a>
### ADR-71 · Pontos de salvamento (checkpoints) apagados 90 dias depois de o envio acabar 🧪

**Status.** Decidido como provisório: o prazo de 90 dias vale até o dono do projeto (ou o jurídico, em produção)
definir a política de retenção. Mudar o prazo é mudar um número (`PRAZO_EM_DIAS`).

**Problema.** Cada envio tem um ponto de salvamento do LangGraph (ADR-15, ADR-49): a memória de curto prazo do fluxo,
que deixa a empresa sair e voltar do mesmo ponto. Ele **nunca era apagado**, nem depois de o envio acabar. Com
~1 milhão de funcionários em milhares de envios, as tabelas `checkpoint*` só cresceriam, guardando o estado de
envios que ninguém mais vai retomar. E havia um risco escondido: se alguém apagasse esse ponto à mão, o LangGraph
diria "ainda não começou", e um `iniciar` recomeçaria o envio do zero, com IA e tudo.

| Opção | A favor | Contra |
|---|---|---|
| Nunca apagar | Nada a fazer | As tabelas crescem sem limite; guarda estado sem uso |
| Apagar logo que o envio acaba | Menos espaço | Perde o retrato do fluxo quando alguém ainda pode ter dúvida sobre um envio recente |
| **Apagar depois de um prazo, com as telas e o fluxo protegidos** | Espaço sob controle; envio recente intacto; nada recomeça | Um prazo a definir; um script a agendar |

**Decisão.** `services/pontos_de_salvamento.py`: o ponto de salvamento de um envio HOMOLOGADO ou REJEITADO é
apagado (`delete_thread`, do próprio LangGraph, no SQLite e no PostgreSQL) quando o evento de encerramento na
auditoria passou de 90 dias. Envio em andamento nunca é apagado. O apagamento vira o evento
`PONTO_DE_SALVAMENTO_APAGADO` na auditoria; rodar de novo não repete nada. `scripts/limpar_pontos_de_salvamento.py`
roda à mão ou numa tarefa agendada. **Proteções no fluxo** (`workflows/fluxo_empresa.py`): sem ponto de salvamento,
um envio encerrado continua "concluído" (a situação é montada a partir do envio e da auditoria, com o motivo do
encerramento), e `iniciar` nunca recomeça um envio encerrado.

**Trade-off.** Depois da limpeza, o "retrato" interno do fluxo (contagens da última validação, decisões de coluna)
não aparece mais para aquele envio; o que importa continua guardado: o envio, o arquivo final com checksum, o
mapeamento aprovado, o histórico e toda a auditoria. O script precisa ser agendado (no servidor, uma tarefa diária).

**Como comprovamos.** `tests/test_pontos_de_salvamento.py` (5 testes): antes do prazo nada é apagado; depois do
prazo, o ponto some, o evento vai para a auditoria e rodar de novo não repete; sem o ponto, o envio continua
concluído, `iniciar` não recomeça e a leitura do novo front mostra "Concluído"; envio esperando o banco não é
apagado; envio descartado guarda o motivo depois da limpeza. **Origem.** Achado na preparação do capítulo de memória
(2026-09-25); feito no modo despertador, sem decisão pendente além do prazo.

**Passo 20 · Correções da auditoria da seção 10 (2026-09-25).** Uma conferência item a item do checklist contra o
código achou quatro defeitos, corrigidos: (1) o **reuso do mapeamento** valia desde o aceite da empresa, com o aviso
falso "o banco já aprovou" (correção no ADR-24); (2) a **arte do endomarketing** tinha o rodapé e o nome da Aurora
fixos para qualquer empresa: agora o rodapé é a fonte do trecho (texto do próprio material) e o nome vem do cabeçalho
(`GET /api/cabecalho` ganhou `nome_da_empresa`); (3) **não havia como retomar um envio** pela tela nova: em Acompanhar,
cada envio que espera a empresa tem "Continuar este envio", que abre `cadastrar.html?envio=<id>` no ponto em que parou
(envio de outra empresa ou inexistente volta para a escolha do arquivo); (4) o botão **"Criar lembrete para a equipe"**
não levava a lugar nenhum: agora abre o endomarketing com um comunicado sobre abrir a conta (o tipo "lembrete" ainda
não existe no agente). **Como comprovamos:** teste novo do reuso; o teste do cabeçalho confere o nome da empresa; ponta
a ponta no Chrome com um usuário da Brisa (outra empresa que não a Aurora): 7 conferências no endomarketing (botão,
assunto, tipo, nome e kit da Brisa, rodapé com a fonte do catálogo da Brisa) e 5 na retomada (botão em Acompanhar,
Cadastrar aberto no aceite das colunas, envio inexistente volta para a escolha do arquivo), sem erro de JavaScript.

**Passo 21 · O "i" de ajuda em cada coluna da conferência (2026-09-25).** A lista para conferir
(`cadastro.lista_para_conferir`) passou a mandar, para cada campo, o que o banco escreveu no **parâmetro do layout**:
descrição, regra ("como deve vir"), "não confundir com", exemplo e se é obrigatório. Na tela real, cada coluna ganha o
"i", que abre o mesmo balão do protótipo com esses textos ("Definido pelo banco no layout de cadastro"). O exemplo de um
campo **sensível** (nome, CPF, endereço...) não vai para a tela, pela mesma regra do índice do RAG; o balão explica "Não
mostramos exemplo de dado pessoal". Não foi preciso um parâmetro novo: a descrição do layout já é escrita em linguagem
simples. **Como comprovamos:** teste novo (`test_cada_campo_da_conferencia_traz_a_ajuda_do_layout`); ponta a ponta no
Chrome com um envio da Brisa: um "i" por coluna (25), balão com a regra e o exemplo da matrícula, CPF sem exemplo, Esc
fecha, sem erro de JavaScript.

<a id="adr-72"></a>

### ADR-72 · Word no cadastro: tabela e fichas por regra, texto corrido pela IA vendo só etiquetas 🧪

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** o texto corrido vai para a IA como a empresa mandou; as etiquetas
> saíram. Tabela e fichas continuam por regra, sem IA.

**Status.** Feito e testado com a IA simulada (MOCK). A leitura do texto corrido foi refeita no **ADR-73** (a v1
falhou no primeiro Word real: resposta cortada no limite de tokens); tabela, fichas e o resto deste ADR continuam valendo.

**Problema.** A ideia do produto é "mande do jeito que estiver": a empresa sobe o arquivo que já tem e a IA organiza.
No primeiro teste do dono do projeto, um Word (.docx) foi recusado ("formato não aceito"), e a tela prometia PDF, foto e
print, que o servidor não lia. O Word pode vir com tabela, em fichas ("Nome: ... / CPF: ...") ou em **texto corrido**
("A Maria Souza, CPF ..., entrou em 05/03 como analista"). O texto corrido só uma IA organiza, mas a regra do projeto é
que a IA **não vê os dados das pessoas** (ADR-31).

| Opção | A favor | Contra |
|---|---|---|
| Só Word com tabela | Sem IA, sem custo | Não atende o "do jeito que estiver" |
| Mandar o texto inteiro para a IA | Mais simples; a IA entende melhor | Quebra o ADR-31: nome, CPF e salário vão para o provedor |
| **Degraus: tabela e fichas por regra; texto corrido pela IA, com os dados trocados por etiquetas** | Sem custo quando dá; no texto corrido a IA vê só a estrutura | Nome escrito todo em minúsculas passa; regra de etiquetas a manter |

**Decisão.** `services/leitura_de_word.py` tenta, em ordem: (1) a maior **tabela** do documento (tabelas com o mesmo
cabeçalho, partidas pela virada de página, voltam a ser uma); (2) **fichas** "Rótulo: valor", quando pelo menos 80% das
linhas têm esse jeito (rótulo sem número, para "Funcionário 1: A Maria..." não virar ficha); (3) **texto corrido**, pelo
novo **Agente Leitor de Documentos** (`agents/leitor_de_documentos.py`, prompt `leitor_de_documentos_v1`).
Antes da IA: o guardrail de entrada tira o parágrafo com cara de ordem (ADR-38) e a **pseudonimização**
(`services/pseudonimizacao.py`) troca cada dado por uma etiqueta: e-mail, CNPJ, CPF, data, valor, CEP, telefone e
números viram `[CPF_1]`, `[DATA_1]`...; palavra com maiúscula (nome, rua, cidade) vira `[TEXTO_n]`, menos as palavras
comuns de uma lista fixa e as siglas dos estados. A IA devolve a tabela com as etiquetas; a troca de volta acontece
aqui dentro. **Guardrail de saída:** a resposta precisa caber no contrato `RespostaLeitorDeDocumentos` (fora dele,
segunda tentativa com o motivo; falhou de novo, o arquivo é recusado com explicação); célula com etiqueta inexistente ou
palavra que não está no documento é apagada, e a empresa é avisada para completar. **Quando não consegue, pergunta:** os
trechos que a IA não encaixou voltam como `duvidas` (novo campo do `FileProfile`), mostradas na tela ("A IA ficou com
dúvida"); dado que falta vira pendência, como na planilha. Sem nenhum funcionário, o arquivo é recusado com a dúvida
da IA na mensagem. **Uma chamada só:** a tabela lida do Word fica guardada ao lado do original (`<id>.leitura.json`);
as etapas seguintes usam essa tabela, e o reenvio idêntico é conferido antes da leitura, então a IA não é paga de novo.
O uso da IA vai para a auditoria (`TEXTO_CORRIDO_LIDO`: modo, modelo, custo e contagens, nada pessoal). Depois da
leitura, o caminho é o mesmo da planilha (retrato, Interpretador, aceite, conferência, banco). `.doc` antigo é recusado
com o caminho para converter. A tela (`front/cadastrar.html`) passou a prometer só Excel, CSV e Word, com "Em breve: PDF,
foto e print de conversa"; o seletor aceita `.xlsx,.csv,.docx`; o limite exibido passou a 5 MB (o real do `.env`).
Nova dependência: `python-docx==1.2.0`.

**Trade-off.** A IA entende um pouco menos com etiquetas do que com o texto real (ex.: não sabe se `[TEXTO_4]` é rua ou
cidade sem o contexto "Rua"). Nome escrito todo em minúsculas não é reconhecido como nome e passa para a IA (limite
registrado no próprio arquivo). Documento com mais de ~40 mil caracteres (~100 funcionários) é recusado com o pedido de
dividir. O dicionário B0 (régua dos experimentos) liga "Salário" sozinho a `complemento_comercial`; não foi mexido para
não mudar os números do EXP (com a IA real, quem decide é o Interpretador).

**Como comprovamos.** `tests/test_leitura_de_word.py` (19 testes): as etiquetas escondem nome, CPF, data, salário,
endereço, telefone e e-mail e voltam ao texto original letra por letra; tabela, tabela partida e fichas são lidas **sem
chamar a IA** (um cliente que falha se for chamado); o texto corrido vira a tabela com os valores de verdade; **o pedido
que chega à IA não tem nenhum nome, CPF, data ou salário**; o que a IA inventa é apagado e avisado; a pessoa sem CPF vira
pergunta; resposta fora do contrato duas vezes recusa; parágrafo com ordem para a IA sai antes da leitura; `.doc`, docx
falso e Word vazio são recusados; a IA é chamada **uma vez** (carregar a tabela e reenviar não chamam de novo); a
auditoria registra o uso sem dado pessoal; o cadastro chega ao aceite das colunas com as dúvidas. Ponta a ponta no
Chrome (servidor em MOCK, porta 8765): 10 conferências (título e seletor honestos, mensagem do painel, 3 funcionários
lidos de um e-mail de RH fictício, aviso de texto corrido, dúvida da funcionária sem CPF, colunas reconhecidas, `.doc`
recusado com "Salvar como"), sem erro de JavaScript. 682 testes no SQLite; os do Word e da ingestão também no PostgreSQL.
**Origem.** Primeiro teste do dono do projeto na plataforma (2026-09-25): "a empresa sobe o arquivo do jeito que está e
a IA trata... e quando não conseguir, pergunta".

<a id="adr-73"></a>

### ADR-73 · Leitor de Documentos v2: uma pessoa por chamada, campos do layout e etiquetas que dizem o tipo 🧪

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** a "decisão pendente" entre etiquetas e "a IA vê os dados" foi fechada
> pelo segundo (98,9% contra 91,3% no EXP-010). Saíram `LEITOR_VE_OS_DADOS` e `juntar_blocos_sem_pessoa`; o módulo
> das etiquetas virou `services/detector_de_dados.py`, usado só para achar dados (aviso de parágrafo esquecido,
> rótulo do campo e simulador MOCK), nunca para esconder algo da IA.

**Status.** Feito e medido com IA real (EXP-010). A escolha entre etiquetas e "a IA vê os dados" é decisão pendente do
dono do projeto; até lá vale o padrão, etiquetas (`LEITOR_VE_OS_DADOS=nao`). Substitui a leitura de texto corrido do
ADR-72 (tabela e fichas por regra continuam iguais).

**Problema.** O primeiro teste do dono do projeto com um Word real (13 fichas misturadas, sem tabela) foi recusado. O
diagnóstico com a IA real mostrou a causa: a v1 pedia a tabela inteira numa chamada só; o Sonnet 5 "pensou" até o limite
de 16 mil tokens de saída e a resposta veio **vazia** (com etiquetas) ou quase no limite (vendo os dados). Além disso,
as etiquetas da v1 escondiam os rótulos ("Registro", "Fone", "CTPS" viravam `[TEXTO_n]`) e quebravam números (um RG
virava 4 etiquetas); e as colunas de nome livre obrigavam uma segunda interpretação (Interpretador).

| Opção | A favor | Contra |
|---|---|---|
| Aumentar o limite de tokens da v1 | Uma linha de código | Custo e tempo crescem com o documento; uma célula ruim derruba tudo |
| **Linha de montagem: blocos por pessoa + campos do layout por bloco** | Chamadas pequenas, em paralelo; um bloco ruim não derruba o arquivo; formato garantido; sem segunda interpretação | Mais chamadas por documento; a divisão em blocos vira mais um ponto de falha |
| Mandar o documento sem etiquetas | Mais simples e mais preciso | Muda o ADR-31: o provedor vê nome, CPF e salário |

**Decisão.** (1) **Cliente de IA**: o provedor Anthropic aceita **esforço** (`effort`, padrão low no leitor) e **formato
garantido** (`output_config.format` com esquema JSON); resposta cortada no limite é informada (`cortada`). (2) **Blocos**:
o modelo pequeno recebe o documento com linhas numeradas e aponta onde começa cada pessoa (prompt
`leitor_segmentacao_v2`); vale só o começo (cada bloco vai até a próxima pessoa), e um bloco sem pista de pessoa se junta
ao de cima; se a resposta não servir, uma regra divide pelos títulos. (3) **Leitura**: o modelo grande lê um bloco por
chamada (4 em paralelo) e preenche **direto os campos do layout** (o parâmetro do banco, com descrição e "não confundir
com", vai no papel do agente), com o trecho de prova e perguntas (prompt `leitor_de_documentos_v4`: terceiros não
entram; renda é o fixo mensal bruto; dois valores, "ilegível" ou "a confirmar" viram pergunta). (4) **Conferência**:
campo fora do layout sai; valor com algo que não está no bloco é apagado e avisado; o mesmo campo com dois valores vira
pergunta. (5) **Etiquetas v2** (`services/pseudonimizacao.py`): números trocados inteiros (RG, PIS, telefone e CEP com
espaço, data por extenso, CPF com espaços); palavras decididas por um **detector local** (spaCy `pt_core_news_md`, que roda
na máquina) mais a frequência do português (wordfreq) e um vocabulário de RH; a etiqueta diz o **tipo** sem mostrar o
valor (`[NOME_n]`, `[LUGAR_n]`, `[CELULAR_n]`); nome composto vira uma etiqueta só, sem a sigla do estado; no e-mail, só
a parte antes do @ fica escondida; 8 dígitos depois de uma UF viram `[CEP_n]`. (6) **Provedor fora do ar**: no modo
real, a queda para a resposta simulada vira `IAIndisponivel` e a empresa recebe "tente de novo" (antes, a leitura seguia
com a simulação, sem aviso). (7) Normalizador: data por extenso, ano com 2 dígitos e telefone com +55.

**Trade-off.** Com etiquetas, o texto misturado (N5) perde cerca de 7 pontos de acerto (os campos que faltam viram
pendência ou pergunta, não chute) e fica mais lento (32 s × 24 s por documento de 8 pessoas). O detector local traz uma
dependência nova (spaCy e o modelo, ~40 MB) e não é perfeito: nome todo em minúsculas passa, e palavras muito comuns que
também são sobrenome podem passar. Cerca de US$ 0,02 por funcionário lido de texto corrido (tabela e fichas: zero).

**Como comprovamos.** EXP-010 (US$ 6,00 no total, com IA real). Prova (conjunto nunca usado para ajustar), acerto por
campo com etiquetas × vendo os dados: N1 e N2 (regra) 100%; N3 100% × 100%; N4 100% × 100%; N5 91,3% × 98,9%. Teste às
cegas (o documento do dono do projeto, 12 pessoas): **92,3% × 99,5%**, contra 0% da v1. Nos dois modos: todas as
armadilhas respeitadas, todas as perguntas feitas, nenhum dado de terceiro vazado. Testes: `tests/test_leitura_de_word.py`
(etiquetas v2, blocos, conferência, provedor fora do ar), `tests/test_avaliacao_do_leitor.py` (régua e documentos
congelados), `tests/test_provedores_de_ia.py` (esforço, formato, resposta cortada), `tests/test_normalizador.py` (datas e
telefone). **Origem.** Pedido do dono do projeto (2026-09-25): "estruturar melhor o agente para ler diversos formatos" e
"rodar o mesmo conjunto de teste duas vezes, com etiquetas e com a IA vendo os dados... e depois decidimos".

**Passo 2 · As perguntas da IA na conferência, não numa lista solta (2026-09-25, pedido do dono do projeto).** No
primeiro teste, a tela mostrava "O que a IA percebeu" e "A IA ficou com dúvida" como listas, ANTES das colunas, sem
dizer como resolver; com milhares de funcionários, viraria uma parede de texto. Agora: (1) a leitura vira **uma frase**
("Texto corrido: a IA montou a lista com 12 funcionários") e os outros avisos ficam em "Ver detalhes da leitura",
recolhido, depois das colunas; (2) as colunas vêm primeiro; (3) cada pergunta da IA fica **presa à pessoa e ao campo**
(`FileProfile.perguntas_da_ia` = {linha, campo, pergunta}) e vira um ALERTA do Validador (`PERGUNTA_DA_IA:<campo>`): a
empresa responde na conferência, embaixo do nome da pessoa, corrigindo o valor (a pergunta some) ou com "Está certo
assim" (fica registrado com quem confirmou; rota `POST /api/empresa/cadastro/{id}/lista/confirmar`); pergunta sobre um
campo que já tem algo a CORRIGIR vira a explicação dessa correção ("A IA perguntou: ..."), num item só; (4) a conferência
tem **contadores** (pessoas, com pendência, para corrigir, para confirmar, perguntas da IA), o filtro **"Mostrar só quem
tem pendência"** (ligado por padrão), "Mostrar mais" com quantas faltam, e abre sozinha quando há pendências. Descartado:
"o banco resolve depois do envio" (quem sabe a data certa ou o CPF que faltou é a empresa; o vaivém é o que faz desistir).
Achado junto: a divisão em blocos por regra tomava "Olá, pessoal do banco!" por título e juntava o documento inteiro
num bloco só (corrigido). **Como comprovamos:** `tests/test_perguntas_da_ia.py` (5 testes: alerta na linha e no campo,
pendências e contadores na lista, corrigir responde, "Está certo assim" confirma, corrigir um campo não responde as
outras); ponta a ponta no Chrome (14 conferências: frase de resumo, ordem resumo → colunas → detalhes, contador das
perguntas, contadores e filtro na conferência, CPF vazio e pergunta num item só, correção aberta no campo, pendência e
pergunta somem ao corrigir, filtro sem pendências, lista inteira sem o filtro), sem erro de JavaScript. 710 testes.

**Passo 3 · O jeito da empresa virando o padrão do banco, também no texto corrido (2026-09-25, pedido do dono do
projeto).** No Word em texto corrido, a tela "Como a IA leu as colunas" mostrava `cpf → cpf`, `nome_completo →
nome_completo`: o leitor v2 já preenche os campos do banco, e a tradução que a empresa precisa ver sumia. Agora o leitor
guarda, por campo, **os rótulos que a empresa usou** (o texto logo antes do valor no trecho de prova, sem dado nenhum:
"Registro do cliente", "cpf_formatado", "entrou em") e em quantas pessoas o dado apareceu
(`FileProfile.origem_das_colunas`). A tabela passa a se chamar "Como a IA leu o seu documento", com a coluna "No seu
documento" (ex.: "Admissão", "Entrou dia", "Início" → `data_admissao`, em 12 de 12 pessoas); sem rótulo, "Pelo lugar no
texto". **Otimização junto:** no texto corrido, o mapeamento usa o que o Leitor já leu (origem "leitor") e **não chama a
IA do Interpretador** (antes, uma chamada paga só para ligar `cpf` a `cpf`); a tela não diz mais "reaproveitei um envio
aprovado" nesse caso. **Como comprovamos:** testes do rótulo (dados, etiquetas, artigos e "como" ficam de fora), da
origem das colunas e do mapeamento sem IA (`chamou_llm` falso, modelo "leitor de documentos"); ponta a ponta no Chrome
(15 conferências, incluindo "No seu documento" e o filtro redesenhando depois de uma correção). 714 testes.

<a id="adr-74"></a>

### ADR-74 · Navegação do Portal Empresa: "Cadastrar funcionários" em todas as páginas e a lista pendente da empresa ✅

**Status.** Decidido pelo dono do projeto em 2026-09-25 (sugestão de navegação dele; decisões A, B e C abaixo).

**Problema.** Mandar funcionários é o foco do portal, mas o envio ficava numa aba, e a correção ficava espalhada: um
grid confuso no Cadastrar e os cartões de pendência em Acompanhar cadastros. Cada arquivo era um envio isolado; a
empresa não via o conjunto do que estava pendente, e a mesma pessoa podia ir ao banco em dois envios.

| Opção | A favor | Contra |
|---|---|---|
| Manter a aba e a correção no Cadastrar | Nada a mudar | Correção em dois lugares; grid difícil com milhares de pessoas |
| Juntar os arquivos num envio só | Uma coisa só | Cada arquivo tem colunas e mapeamento próprios; perde o rastro de qual arquivo trouxe cada pessoa |
| **(A) Lista pendente da empresa: cada arquivo continua um envio por trás; na tela, uma lista só, com cruzamento entre envios e um "Enviar ao banco" para tudo o que está pronto** | Rastro por arquivo mantido; correção num lugar só; o banco vê de onde veio cada pessoa | Validar um envio passa a olhar os outros (mais consultas) |

**Decisão.** (1) **Botão "Cadastrar funcionários" (B)** no canto de todas as páginas (onde ficava o "Posso ajudar?"),
abrindo uma janela com a tela de envio (`front/js/novo_envio.js`; a tela é carregada do zero a cada clique); os links
antigos para a tela de envio abrem a janela; **a aba saiu do menu (C)**. (2) O **"Posso ajudar?" virou um ícone de
conversa** ao lado do sino. (3) **Ao aceitar as colunas**, a janela leva para Acompanhar cadastros, com o recado do que
fazer; o mesmo arquivo de novo é avisado e não segue. (4) **Acompanhar cadastros é o lugar de resolver tudo:** bloco
"Pronto para enviar ao banco" (envios sem pendência, a lista de cada um com CPF mascarado, "Conferi a lista" e um
"Enviar ao banco"; rotas `GET /api/empresa/prontos_para_o_banco` e `POST /api/empresa/enviar_ao_banco`); nos cartões:
informar o valor, "Está certo assim" (porquê opcional), "Não cadastrar esta pessoa", "Deixar este campo em branco" (só
campo não obrigatório), a pergunta da IA junto da correção do mesmo campo; nos envios: "Trocar o arquivo deste envio"
(dois cliques: descarta e abre a janela). (5) **Cruzamento entre envios:** a mesma pessoa (CPF) em outro envio ainda
não cadastrado vira pendência BLOQUEANTE nos dois (`PESSOA_EM_OUTRO_ENVIO`); validar um envio valida de novo os outros
que esperam a empresa; um arquivo em que todas as pessoas já estão cadastradas ou num envio pendente é recusado antes
de virar envio ("Nada novo para enviar"); envio descartado não conta como reenvio.

**Trade-off.** Cada validação consulta os outros envios pendentes da empresa (poucos, na prática). "Aceitar sugestão da
IA" nos cartões ficou para depois (o Assistente de Correção é conversa; cada sugestão seria uma chamada paga). Campo
obrigatório que o documento não traz (ex.: CNPJ do empregador no Word em texto corrido) ainda não tem "preencher para
todos" pela tela.

**Como comprovamos.** Testes: `test_lista_pendente_envia_ao_banco_tudo_o_que_esta_pronto`,
`test_envio_com_pendencia_nao_esta_pronto`, `test_acompanhar_junta_a_pergunta_da_ia_ao_cartao_de_correcao`,
`test_mesma_pessoa_em_dois_envios_vira_pendencia_nos_dois_e_some_quando_sai_de_um`,
`test_arquivo_sem_ninguem_novo_e_recusado`, `test_depois_de_descartar_o_mesmo_arquivo_vira_um_envio_novo`. Ponta a
ponta no Chrome: navegação (10 conferências: botão e ícone de conversa nas 4 páginas, janela, aceite levando a
Acompanhar, janela do zero, arquivo repetido) e Acompanhar (12 conferências: pronto para o banco, lista com CPF
mascarado, "Conferi a lista", envio e recado, pergunta junto da correção, "Não cadastrar esta pessoa", "Trocar o
arquivo"), sem erro de JavaScript. 719 testes.

<a id="adr-75"></a>

### ADR-75 · Janela de cadastro: uma linha por rótulo do documento, "Ajustado por você" com conferência do tipo e releitura de várias colunas ✅

**Contexto (2026-09-25, teste do usuário com o Word dele).** Na janela "Cadastrar funcionários": (1) a leitura de texto
corrido leva minutos e a tela não mostrava o tempo; (2) "No seu documento" juntava, numa linha por **campo do banco**,
todos os rótulos que a empresa usou: se a IA pôs dois dados diferentes no mesmo campo, não dava para corrigir só um;
(3) trocar o campo de uma coluna não mudava a situação nem avisava quando o tipo não batia; (4) nos detalhes da leitura
aparecia "Pessoa 5, campo tipo_documento: a IA escreveu algo que não está no documento", sem dizer quem é a pessoa e com
cara de "a IA inventa"; (5) o "Ajude a IA a acertar" aceitava uma coluna só e mostrava "cpf → cpf" (o nome do banco
dos dois lados).

**Opções (item 2).**

| Opção | Ganho | Custo |
|---|---|---|
| Manter uma linha por campo, com os rótulos juntos | Tabela curta | A empresa não corrige um agrupamento errado da IA |
| **Uma coluna por rótulo do documento ("Admissão", "Documento fiscal", "Sem rótulo 1"), cada uma já com o campo que o Leitor leu** | A empresa vê o jeito dela virando o padrão do banco, com um exemplo, e troca o campo de uma linha só | Mais linhas; um campo pode vir de várias colunas (o aceite, a padronização e a conferência "nada some" passam a juntar colunas do mesmo campo) |

**Decisão.** (1) **Cronômetro** ao lado do status da IA, do envio até a resposta (e na releitura). (2) **Tabela do
texto corrido por rótulo** (`services/leitura_de_word.tabela_pelos_rotulos`): o Leitor guarda o rótulo de cada valor
por pessoa (`rotulos_das_pessoas`); palavras de ligação das pontas saem ("com salário de" → "salário"); o mesmo rótulo
em dois campos vira "entrou (1)", "entrou (2)"; a origem da coluna diz o campo (`{campo, rotulo, pessoas}`), o
mapeamento a propõe sem IA e a tela mostra **um exemplo** de cada linha (mascarado como na conferência; CPF sempre
mascarado). Várias colunas podem ir para o mesmo campo **se nunca tiverem valor na mesma pessoa** (senão o aceite
recusa, dizendo quais); a decisão de formato de data numa coluna vale para as outras do mesmo campo, e a dúvida aparece
uma vez por campo. A régua do EXP-010 junta as colunas de volta por campo (`linhas_pelos_campos`): o experimento
continua comparável. (3) **Trocar o campo vale** (a empresa conhece o arquivo): a situação vira **"Ajustado por você"**
e a tela confere na hora, sem gravar, se os valores servem para o campo novo (`POST .../conferir_coluna`, a mesma
conversão da padronização; no campo de texto, estranha valor sem letra). Tipo que não bate = selo "Ajustado · confira o
tipo" e o alerta dizendo quantos valores não servem; se aceitar assim, eles ficam em branco e viram pendência para
revisar em Acompanhar. (4) **O valor que não está no documento vira pergunta presa à pessoa** ("A IA leu "RG" neste
campo, mas não achou isso escrito assim no documento... informe o valor certo"), respondida no cartão da pessoa em
Acompanhar; nos detalhes, quem não tem nome aparece pelo começo do trecho, nunca "Pessoa N". A regra "não inventar"
já está no prompt de todo agente que escreve (Leitor: "copie como está; não corrija, não complete, não converta";
Assistente, Interpretador, Explicador, Consultor, Endomarketing) **e** o código confere a saída: foi a conferência que
pegou o valor trocado. (5) **"Ajude a IA a acertar" com até 5 colunas**, cada uma com a sua dica, contando como UMA
releitura (`mapeamentos.reinterpretar_colunas`, um evento de auditoria com as colunas); a escolha mostra o documento
(rótulo e exemplo) e como a IA leu.

**Trade-off.** Texto corrido com muitos jeitos de escrever o mesmo dado gera mais linhas na tabela (o exemplo e a
contagem de pessoas ajudam a ler). O prompt do Leitor não mudou (mudar pede nova medição com IA real).

**Como comprovamos.** Testes: `test_rotulos_do_mesmo_campo_se_completam_e_a_empresa_pode_trocar_um`,
`test_duas_colunas_da_mesma_pessoa_no_mesmo_campo_sao_recusadas`, `test_o_que_a_ia_inventa_e_apagado_e_avisado`
(agora pergunta presa à pessoa, sem "Pessoa N"), `test_conferir_valores_para_o_campo_escolhido_pela_empresa`,
`test_api_confere_a_coluna_e_rele_varias`, `test_varias_colunas_numa_releitura_contam_como_uma`. Ponta a ponta no
Chrome (14 conferências: cronômetro liga e para, uma linha por rótulo com exemplo e CPF mascarado, CPF na data de
admissão gera o alerta, voltar desfaz, campo de texto fica "Ajustado por você" sem alerta, duas colunas relidas de uma
vez, detalhes sem "Pessoa N"), sem erro de JavaScript. 724 testes.

<a id="adr-76"></a>

### ADR-76 · Parâmetro do layout com "dado pessoal protegido": tela do banco com registro, etiquetas e máscaras pela marcação, e divisão de coluna ✅

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** a marcação virou "Dado pessoal (LGPD)": só classifica o campo no
> inventário de dados pessoais do banco (base do RIPD). Ela não esconde mais nada, nem da IA nem da tela. A tela do
> banco, o registro das alterações e a divisão de coluna continuam iguais.

**Contexto (2026-09-25, pedidos do usuário).** (1) Uma coluna com vários dados numa célula (o endereço inteiro) só
podia ir para UM campo da lista. (2) A marcação de dado sensível do parâmetro deveria decidir o que vira etiqueta
antes da IA: o que não é marcado pode ir como está. (3) Faltava a tela do parâmetro no novo front, com os campos
sensíveis já marcados e o registro de cada alteração (quem, quando, o quê). (4) Em "Como a IA leu", o exemplo do campo
marcado deveria aparecer com só uma parte à mostra, e o do campo sem marcação, com o valor, para mostrar o tipo de
informação.

**Sobre a LGPD (o que o usuário perguntou).** "Dado pessoal sensível" na LGPD (art. 5º, II) é uma categoria estreita
(origem racial, religião, saúde, biometria...): nenhum campo do layout está nela. Mas a LGPD protege TODO dado pessoal
(qualquer dado de pessoa identificável: nome, CPF, endereço, salário). Por isso a marcação do sistema se chama **"dado
pessoal protegido"**: marca o que identifica ou expõe a pessoa. Etiquetar só o marcado é uma medida de minimização e
segurança (art. 6º, III e VII; art. 46), e não basta sozinha: mandar dado pessoal (mesmo sem a marcação) a um provedor
de IA continua pedindo base legal (o contrato banco × empresa), contrato de operador com o provedor (sem treino com os
dados, retenção), regras de transferência internacional (art. 33) e o relatório de impacto (RIPD). Isso fica para o
jurídico validar, como as outras premissas de privacidade.

**Opções (item 2).**

| Opção | Ganho | Custo |
|---|---|---|
| Etiqueta em todo dado (como era) | O mais protegido | O banco não governa o que a IA vê; dado da empresa (CNPJ) escondido sem motivo |
| Etiqueta por CAMPO marcado | Exatamente o que o banco marcou | Impossível antes da IA: ela é chamada justamente para descobrir de qual campo é cada pedaço |
| **Etiqueta por TIPO de dado: vira etiqueta o tipo que pode preencher algum campo marcado** | O parâmetro governa; funciona antes da IA; tipo sem nenhum campo marcado vai como está | Um tipo com um só campo marcado esconde todos os dados dele (ex.: data_nascimento marcada esconde todas as datas) |

**Decisão.** (1) **Dividir em vários campos** (`services/divisao.py`): na escolha do campo, "Dividir em vários
campos…" abre o destino (Endereço residencial, Endereço comercial, Cidade e UF de nascimento), com **prévia** mascarada
pelo parâmetro. A divisão é **por regra, sem IA e sem custo** (CEP, UF no fim, cortes em vírgula, " - " e barra; rua,
número, complemento, bairro, cidade); com um pedaço só e sem UF, não chuta bairro ou cidade: ele sobra e a tela avisa.
Cada parte vira uma coluna nova ("Endereço · rua"), ligada ao campo e "Ajustado por você"; a original fica de fora; a
tabela nova é gravada ao lado do original (`guardar_tabela_do_envio`), que continua intacto. Só antes do aceite.
(2) **Etiquetas pela marcação** (`pseudonimizacao.etiquetas_protegidas`): um tipo de etiqueta é usado quando pode
preencher algum campo marcado; com o layout v1, só o CNPJ (dado da empresa) passa a ir como está. O Interpretador
continua vendo amostras mascaradas pelo formato em todas as colunas (antes do mapeamento não se sabe o campo).
(3) **Tela "Parâmetros"** no Portal do Banco (`banco_parametros.html`, só BANCO): campos por grupo, tipo do catálogo
fechado, obrigatório, **dado pessoal protegido** (já marcado nos 20 campos que identificam ou expõem a pessoa), uso
comercial, textos que a IA lê, campo novo, tirar campo; "Gravar nova versão" só com mudança; embaixo, o **registro das
alterações** (versão, quando, quem e o que mudou, em frases: "cpf · obrigatório: não → sim"). Rotas
`GET/POST /api/banco/parametros/layout`. (4) **Exemplo em "Como a IA leu"**, na planilha e no Word: campo marcado →
só uma parte à mostra (`ingestao.mascarar_uma_parte`: "He*** Du*** Ra***", "(71) *****-**34"); sem marcação → o valor;
coluna sem campo → só uma parte; CPF sempre com a máscara do CPF.

**Trade-off.** A divisão por regra erra endereços fora do comum (a prévia mostra antes, e o que falta vira pendência).
O índice do RAG com os textos do layout é refeito pelo `scripts/build_index.py` (o prompt já usa o layout vigente).

**Como comprovamos.** Testes: `test_a_regra_separa_as_partes_do_endereco`,
`test_sem_uf_um_pedaco_sozinho_nao_vira_bairro_nem_cidade`, `test_cidade_e_uf_da_naturalidade`,
`test_dividir_a_coluna_do_endereco_no_envio`, `test_o_parametro_do_layout_decide_o_que_vira_etiqueta`,
`test_tela_de_parametros_so_do_banco_grava_versao_e_registra_quem_mudou_o_que`,
`test_mudancas_do_layout_em_frases_curtas`. Ponta a ponta no Chrome (13 conferências: exemplo mascarado na planilha,
cargo com o valor, prévia sem a rua inteira, partes ligadas aos campos, aceite; aba Parâmetros, 44 campos, CPF marcado,
gravar só com mudança, registro com quem e o quê, desfazer registrado), sem erro de JavaScript. 731 testes.

**Passo 2 (mesmo dia).** (a) **O índice da IA se refaz sozinho** ao gravar os parâmetros (tela nova e Streamlit):
`rag/indice_do_layout.refazer_em_segundo_plano` começa na hora, numa linha de trabalho ao lado (a tela não espera);
se falhar, o índice antigo continua valendo e o aviso vai para o registro do servidor; testes e avaliações não tocam o
índice real (mesmo interruptor da memória que aprende). `scripts/build_index.py` usa a mesma função. (b) **A ordem
dentro da célula quase não importa:** a rua é achada pelo tipo de via (Rua, Av., Travessa...) e o bairro pela palavra
"Bairro", em qualquer posição; só bairro × cidade sem rótulo seguem a ordem de costume (bairro antes da cidade). Testes:
`test_a_ordem_dentro_da_celula_quase_nao_importa`,
`test_gravar_o_layout_refaz_o_indice_da_ia_so_com_os_indices_vivos_ligados`. 733 testes.

**Passo 3 (2026-09-26, decisões do usuário).** (a) **Marcação de dado pessoal protegido:** marca o que identifica a
pessoa sozinho (nome, CPF, nome da mãe, PIS, número do documento, rua, número e complemento de casa, telefones,
e-mails) ou junto com outro dado (nascimento e CEP de casa). Saíram da marcação: sexo, estado civil, nacionalidade,
bairro e cidade de casa e salário (sozinhos não identificam ninguém). Gravada como versão 2 do layout no banco da
aplicação, com registro ("claude.code (pedido do usuário em 2026-09-26)"), e o índice refeito. Efeito nas etiquetas:
os valores em dinheiro passam a ir como estão para a IA; datas continuam etiquetadas (o nascimento é protegido).
A versão 1 dos arquivos (`layout_v1.csv`, usada em banco novo, nos testes e no EXP-010) não mudou.
(b) **Formatos de data** (`normalizador.converter_data`): além de dia/mês/ano, mês/dia/ano (americano), ano curto,
ano primeiro com traço, número de série do Excel e mês escrito em português, agora aceita ano primeiro com barra ou
ponto (2026/09/01), data com hora depois (01/09/2026 08:30, 2026-09-01T08:30:00, 9/14/2026 8:30 PM), compacta
(20260901, 01092026), ordinal ("1º de maio de 2020") e mês escrito em inglês ("14-Sep-2024", "Sep 14, 1991",
"May 3rd, 2020"). Dia/mês × mês/dia continua sem suposição: decide a própria data (parte > 12), as outras datas da
coluna e do arquivo ou, sem desempate, a empresa (uma vez por campo). A pseudonimização também reconhece o mês em
inglês como data. Testes: `test_formatos_de_data_em_portugues_ingles_e_outros` (14 formatos),
`test_data_ambigua_com_ano_curto_ou_compacta_espera_a_decisao_da_empresa`,
`test_data_com_mes_em_ingles_tambem_vira_etiqueta`. 749 testes.

**Passo 4 (2026-09-26, decisões do usuário).** (a) **O padrão da marcação mudou também na versão 1 dos arquivos**
(`data/contratos/layout_v1.csv`, usada em banco novo, como o da hospedagem, nos testes e nas medições): sexo, estado
civil, nacionalidade, bairro e cidade de casa e salário saíram da marcação. O banco do contêiner Docker (porta 5433)
guardou a versão 1 antiga: ao subir de novo, gravar a marcação pela tela Parâmetros ou recriar o banco dele.
(b) **Datas escritas por extenso** (`services/datas_por_extenso.py`, em português e inglês): o nome do mês é a âncora;
o dia e o ano podem vir em palavras ("quatorze de setembro de mil novecentos e noventa e um", "primeiro de maio de
dois mil e vinte", "September fourteenth, nineteen ninety-one"). A pseudonimização acha essas datas dentro do texto
corrido e as esconde numa etiqueta [DATA_n] (a data de nascimento é protegida).
(c) **A lista completa de formatos de data** (`normalizador.converter_data`):

| Grupo | Exemplos |
|---|---|
| Números, dia primeiro ou mês primeiro | 14/09/2026 · 9/14/2026 · 14.09.26 · 14-09-2026 · 14 09 2026 · 14 / 09 / 2026 |
| Ano primeiro | 2026-09-14 · 2026/09/14 · 2026.9.14 |
| Compacta | 20260914 · 14092026 |
| Excel | célula de data · número de série 46266 · 46266.5 (com a hora na fração) |
| Mês escrito (português e inglês) | 14 de setembro de 2026 · 14 set 2026 · 14/set/26 · 8 de jul. de 2024 · 1º de maio de 2020 · 14-Sep-2026 · Sep 14, 2026 · May 3rd, 2020 · the 14th of September 2026 |
| Tudo por extenso | quatorze de setembro de mil novecentos e noventa e um · primeiro de maio de dois mil e vinte · dia 3 de março de dois mil e vinte e quatro · September fourteenth, nineteen ninety-one · March 3rd, twenty twenty-four |
| Com o que não é data em volta | segunda-feira, 14/09/2026 · Mon, Sep 14 2026 · dia 14/09/2026 · 14/09/2026 08:30 · às 10h · 14h30 · 8:30 PM · 2026-09-14T08:30:00Z · -03:00 |
| Recusadas, com o motivo | só mês e ano (09/2026, setembro de 2026): "a data não tem o dia"; data que não existe (31/02): "data inexistente" |

Dia/mês × mês/dia continua sem suposição (a própria data, a coluna, o arquivo ou a empresa decidem).

**Testes a refazer (pedido do usuário: registrar agora e fazer depois).** Nada foi rodado neste passo.

| O quê | Custo | Por quê |
|---|---|---|
| Bateria automática (`python -m pytest`) | Grátis | Mudaram o padrão da marcação (máscaras de tela, pendências do validador, Streamlit), o normalizador (espaço como separador, dia da semana, "dia"/"em", hora com "às" e fuso, "falta o dia") e a pseudonimização (datas por extenso viram etiqueta). Dois testes foram ajustados ao padrão novo sem rodar (salário e CNPJ agora vão sem etiqueta) |
| Testes de clique no Chrome (`e2e_*.py`) | Grátis | Os exemplos de "Como a IA leu" mudam (salário, cidade e bairro aparecem inteiros) |
| EXP-010, prova e teste às cegas, nos 2 modos | Cerca de US$ 6 (IA real) | As etiquetas mudaram (salário e CNPJ sem etiqueta; data por extenso e mês em inglês com etiqueta) e o Word passou a ser montado por rótulo: os números de 2026-09-25 (91,3% × 98,9% no N5) já não descrevem a configuração atual |
| EXP-008 e B1–B3 do Interpretador | IA real | Os exemplos dos campos que saíram da marcação passam a entrar no índice do RAG e no prompt (`rag/trechos.py` só guarda exemplo de campo não protegido): a busca e o pedido mudaram |
| Seu teste às cegas na plataforma (porta 8000) | IA real | Mesmo motivo do EXP-010, agora com o seu arquivo |


<a id="adr-77"></a>

### ADR-77 · Empresa cadastrada pela sede; filiais e grupo vêm no arquivo e se confirmam uma vez ✅

**Contexto (2026-09-26, pedido do usuário).** Uma empresa pode ter um CNPJ principal, filiais e outras empresas do
mesmo grupo, e vários endereços comerciais (um ou mais por empresa). Cadastrar tudo isso no banco é trabalhoso e
fica desatualizado; quem sabe onde cada funcionário trabalha é o RH.

**Decisão.**
1. **Aba Empresas (especialista):** cadastra o geral da empresa, a **sede** (razão social, CNPJ principal, endereço da
   sede), e, **se tiver a informação, sem obrigação**, as **filiais e os CNPJs do grupo**.
2. **No arquivo, funcionário por funcionário:** o **CNPJ de onde a pessoa trabalha** (`cnpj_empregador`) e o
   **endereço comercial completo** (CEP, rua, número, bairro, cidade, UF: agora obrigatórios; complemento opcional).
   Campo novo opcional `cnpj_grupo`: o CNPJ principal do grupo, quando o empregador é outra empresa do grupo.
3. **Regra do CNPJ no arquivo:**

| O CNPJ encontrado | O que acontece |
|---|---|
| CNPJ principal cadastrado | Validado |
| Mesma raiz do principal (os 8 primeiros dígitos: filial) | Validado automaticamente |
| Filial ou CNPJ do grupo já no cadastro | Validado |
| Raiz diferente, fora do cadastro, repetido em várias pessoas | Pergunta à empresa: "este CNPJ é de uma empresa do seu grupo?" |
| Fora do cadastro e em uma pessoa só | Pendência: provável erro de digitação |

4. **A empresa confirma uma vez, e vale para sempre:** o "é do grupo" entra **automaticamente** no cadastro da empresa
   (o especialista vê, com o registro de quem confirmou e quando), e a pergunta não se repete para outros
   funcionários nem em envios futuros.

**Aplicado já (2026-09-26):** layout padrão (`layout_v1.csv`) e versão 4 no banco local, com registro: `cnpj_grupo`
novo; `logradouro_comercial`, `numero_comercial` e `bairro_comercial` obrigatórios (24 obrigatórios no total).

**Implementado (2026-09-26, despertador, ciclo 5):**
- **Cadastro:** tabela `cnpjs_das_empresas` (empresa, CNPJ, tipo FILIAL ou GRUPO, origem BANCO ou EMPRESA, quando e
  quem). O CNPJ principal continua na tabela `empresas`. `services/empresas.py`: `adicionar_cnpj` (só o BANCO; confere
  os dígitos; filial precisa da mesma raiz da sede e grupo de outra raiz; não repete o principal nem um já
  registrado), `remover_cnpj`, `cnpjs_conhecidos` (o que o Validador usa) e `registrar_cnpj_confirmado_pela_empresa`
  (entra sozinho; confirmar duas vezes não duplica).
- **Validador:** `_regra_do_cnpj` troca a regra antiga ("raiz diferente bloqueia sempre"). Conta em quantos
  funcionários do envio cada CNPJ aparece (`_pessoas_por_cnpj`): desconhecido em 2 ou mais vira o alerta
  `CNPJ_DO_GRUPO_A_CONFIRMAR` ("Este CNPJ aparece em N funcionários e não está no cadastro da sua empresa. É de uma
  empresa do seu grupo?"); desconhecido em 1 só continua `CNPJ_DE_OUTRA_EMPRESA` (bloqueia, com a dica de pedir ao
  banco para cadastrar). Vale para os dois campos de CNPJ (`cnpj_empregador` e `cnpj_grupo`). Na aplicação, a
  validação lê o cadastro do banco de dados; chamada sozinha (testes e avaliação), usa o CNPJ principal do arquivo das
  empresas fictícias, como antes.
- **Confirmação:** em Acompanhar, o cartão desse alerta tem o botão **"Sim, é do nosso grupo"**. `justificar_alerta`
  lê o CNPJ dos dados atuais do envio (não do texto da tela), registra a resposta, põe o CNPJ no cadastro e valida de
  novo este envio e os outros da empresa: o alerta sai de todos os funcionários e não volta em envios futuros. A
  auditoria ganha o evento `CNPJ_DO_GRUPO_REGISTRADO`.
- **Aba Empresas:** "Endereço da sede" no lugar de "Endereço comercial"; bloco **"CNPJs de filiais e do grupo
  (opcional)"** com a lista (tipo e quem registrou: o banco ou a empresa, ao confirmar num envio), "Adicionar CNPJ" e
  "Tirar" (dois cliques). Rotas `POST /api/banco/empresas/{id}/cnpjs` e `DELETE /api/banco/empresas/{id}/cnpjs/{cnpj}`;
  a ficha (`GET /api/banco/empresas`) traz `outros_cnpjs`.

**Trade-off.** Um CNPJ errado repetido em várias linhas (ex.: copiado e colado) vira a pergunta "é do grupo?" em vez
de bloquear; se a empresa confirmar por engano, o especialista vê na ficha quem confirmou e tira o CNPJ. Um CNPJ do
grupo com um funcionário só bloqueia até o banco cadastrá-lo.

**Como comprovar.** `tests/test_cnpjs_das_empresas.py` (cadastro e motivos de recusa, só o BANCO, a regra nos 4 casos,
confirmar uma vez tira o alerta dos dois e um terceiro funcionário com o mesmo CNPJ não é perguntado, rotas com 403,
400 e 404). Ponta a ponta de clique `e2e_cnpj_grupo.py` (scratchpad da sessão a36903b5, porta 8766).

<a id="adr-78"></a>

### ADR-78 · Dois perfis nesta versão: EMPRESA e BANCO (sai o CIENTISTA) ✅

**Contexto (2026-09-26, decisão do usuário).** A versão tinha três perfis: EMPRESA, BANCO e CIENTISTA (o cientista de
dados via só a aba Telemetria e o Painel Técnico do Streamlit). O usuário quer simplificar: nesta versão basta
demonstrar o que o banco enxerga e o que a empresa enxerga; o banco tem a gestão completa da ferramenta.

**Opções.** A · manter o perfil separado (separação de funções, um login a mais); B · permissão "acesso técnico"
dentro do perfil BANCO (mais regra para construir); **C · acabar com o perfil**, e o especialista vê tudo.

**Decisão.** C. Saem: o perfil `CIENTISTA` (`models/contratos.py`), o usuário `cientista.dados` (scripts, Compose,
`.env.example`, README), o Painel Técnico do Streamlit (`telas/painel_tecnico.py`; o desempenho da IA continua na
sub-aba "Desempenho da IA" do banco), o `menu_por_perfil.js` e o `paginas_permitidas` do `/api/eu` (existiam só para
esconder abas do cientista) e o `usuario_da_telemetria` (a Telemetria usa a guarda do banco). Banco criado antes: a
preparação do servidor apaga os usuários de perfis que não existem mais, com as sessões deles
(`auth.remover_usuarios_de_perfis_extintos`); o banco local já foi limpo.

**Trade-off.** Perde a separação de funções entre quem cuida da IA e quem opera a carteira; volta como evolução
(gestão de acesso mais fina), sem mudar o resto.

**Como comprovamos.** `test_so_existem_os_perfis_da_empresa_e_do_banco`,
`test_usuario_de_perfil_que_nao_existe_mais_e_apagado_com_as_sessoes`,
`test_trilha_do_banco_ve_as_execucoes_do_arquivo_sem_cpf` (a trilha 3 do ponta a ponta passou para o banco). 741
testes.


<a id="adr-80"></a>

### ADR-80 · Sem Fine-Tuning nesta versão: RAG para o conhecimento que muda ✅

**Contexto (2026-09-26, decisão 5 do usuário).** O plano previa o B5: um modelo pequeno ajustado (Fine-Tuning) com
RAG, comparado ao B4 (o mesmo modelo sem ajuste). O ADR-06 deixou a decisão aberta até existir provedor e dataset.
O dataset de treino existe (`cabecalhos_treino.jsonl`, 1.500 planilhas); o provedor foi escolhido (ADR-11).

**Opções.** A · treinar agora e medir o B5; **B · ficar só com o RAG** (mais a memória que aprende, ADR-70);
C · os dois agora.

**Decisão.** B. Fecha o ADR-06.

| | RAG (o que usamos) | Fine-Tuning |
|---|---|---|
| O que muda | O que a IA **consulta** antes de responder | O **comportamento** do próprio modelo |
| Campo novo no layout | Vale na hora: o índice é refeito ao gravar (ADR-76) | Precisa treinar de novo |
| Catálogo de cada empresa | Um filtro por empresa na busca (ADR-10) | Um modelo por empresa: inviável |
| Explica a resposta? | Sim, cita a fonte | Não diz de onde veio |
| Dado pessoal | Não entra no índice | O treino guarda o que viu; "esquecer" um dado exige treinar de novo |
| Custo | Índice local, sem custo de API para indexar | Treino + hospedar o modelo ajustado; nem todo provedor permite ajustar os modelos escolhidos |
| Onde ganha | Conhecimento que muda (layout, catálogo, mapeamentos aprovados) | Formato fixo, volume muito alto, resposta rápida e barata |

**Quando o Fine-Tuning passa a fazer sentido (e sempre junto com o RAG, não no lugar dele):**
1. **Volume muito alto:** com ≈ 1,04 milhão de funcionários (a premissa de dimensionamento), o custo por chamada
   começa a pesar; um modelo pequeno ajustado ao formato do layout responde mais barato e mais rápido.
2. **Modelo aberto dentro do banco** (ADR-81): o banco controla o modelo, pode ajustá-lo e o dado não sai.
3. **Um formato de saída que o modelo erra sempre**, mesmo com exemplos no prompt.

**Por que não agora.** Sem ajuste, a IA já sai de 53% (dicionário, B0) para 84% nas colunas (EXP-008), e o que
muda toda semana (layout, catálogo, mapeamentos aprovados) está no RAG, que não precisa de treino.

**Trade-off.** O B5 fica sem número, e a banca não vê a comparação B4 × B5. Em troca, não há custo de treino nem um
modelo ajustado para manter a cada mudança do layout. O dataset de treino continua pronto para quando o volume
justificar.

**Como comprovar.** A avaliação B0 a B4 continua (`docs/avaliacao.md`); o índice refeito ao gravar o layout
(`rag/indice_do_layout.py`, ADR-76) e a memória que aprende (ADR-70) mostram o conhecimento novo valendo sem treino.

<a id="adr-81"></a>

### ADR-81 · Privacidade da IA: etiquetas sempre que a IA for externa; em produção, a IA dentro do perímetro do banco 🔁

> **Revista pelo [ADR-101](#adr-101) (2026-09-27):** a IA foi para dentro de uma nuvem contratada (Bedrock, ADR-96) e, como
> este ADR já previa para esse caso, passou a ver os dados.

**Contexto (2026-09-26, decisão 2 do usuário).** O EXP-010 mediu o "preço da privacidade" na leitura do Word em
texto corrido: com etiquetas no lugar do dado protegido, 91,3% no nível 5 da prova e 92,3% no teste às cegas; com
a IA vendo os dados, 98,9% e 99,5%. A IA de hoje é **externa** (API da Anthropic e da OpenAI).

**Opções.** **A · etiquetas sempre** no dado marcado como protegido (ADR-76); A+ · etiquetas com IA externa e dados
só com modelo local; B · a IA externa vê os dados, sob contrato com o provedor.

**Decisão.** A nesta versão. O dilema "etiquetas × acerto" só existe porque a IA é externa. Em produção, o banco
leva a IA para dentro do seu perímetro, e aí ela pode ver os dados:

| Caminho | Exemplo | O dado sai do banco? | Custo, ordem de grandeza | Quando escolher |
|---|---|---|---|---|
| **Hoje (a demo)** | API da Anthropic e da OpenAI, com etiquetas no dado protegido | Sai só o texto com etiquetas | Centavos por arquivo (medido: ≈ US$ 0,01 a 0,05 por documento) | Prova de conceito, dados sintéticos |
| **Nuvem que o banco já contrata** | Claude no Amazon Bedrock, no Google Vertex AI ou no Microsoft Foundry (Azure) | Fica no contrato de nuvem do banco; o provedor do modelo não vê os pedidos | Por uso, como a API, no faturamento da nuvem do banco | O banco já tem a nuvem homologada; quer o melhor acerto (IA vendo os dados: 98,9% × 91,3% no N5 do EXP-010) |
| **Modelo aberto no servidor do banco** | gpt-oss-120b (uma placa de 80 GB) ou Qwen3 (de 4B a 235B), servidos com vLLM | **Não sai** | Placa H100: ≈ US$ 1,50 a 7 por hora alugada, ou compra; sem custo por chamada | Volume muito alto (≈ 1,04 milhão de funcionários), exigência de dado no país, ou junto com Fine-Tuning |
| ~~API de modelo aberto de terceiros~~ | Groq, Together, OpenRouter | **Sai** | Centavos | Não resolve a privacidade: é externo de novo |

**Ressalva de LGPD na nuvem.** Em São Paulo, o Bedrock oferece os modelos Claude só com roteamento global: o pedido
pode ser processado fora do Brasil, o que é transferência internacional de dados (LGPD, art. 33) e passa pelo
jurídico do banco. Quem precisa do dado no país escolhe o modelo aberto num servidor do banco no Brasil.

**No radar (opcional).** EXP-011: um modelo aberto pequeno (ex.: Qwen3-4B) na máquina local, na mesma prova do
EXP-010, para medir acerto e tempo com custo de API zero. A máquina de desenvolvimento tem placa de 4 GB: serve de
experimento, não para a demo.

**Trade-off.** Na demo, perde-se de 7 a 8 pontos no texto corrido (a leitura de tabela e de fichas não usa IA e não
perde nada). Em troca, a regra é fácil de defender: "dado pessoal protegido nunca sai para uma IA externa".

**Como comprovar.** `pseudonimizacao.etiquetas_protegidas` e os testes da pseudonimização (ADR-76); EXP-010 em
`docs/avaliacao.md`.

**Fontes (consultadas em 2026-09-26; preços e regiões mudam, conferir na hora de contratar):**
- Amazon Bedrock, proteção de dados: os provedores dos modelos não têm acesso aos pedidos e respostas
  (https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html).
- Amazon Bedrock, modelos por região: em São Paulo (sa-east-1), os modelos Claude aparecem só com roteamento global
  (https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html).
- Claude no Microsoft Foundry (Azure), disponível desde jul/2026 (https://claude.com/blog/claude-in-microsoft-foundry;
  https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models).
- Claude no Google Cloud (Vertex AI), com endpoints por região e multirregião
  (https://platform.claude.com/docs/en/build-with-claude/claude-on-vertex-ai).
- gpt-oss-120b e gpt-oss-20b, pesos abertos, licença Apache 2.0: o 120b roda numa placa de 80 GB e o 20b em 16 GB
  (https://openai.com/index/introducing-gpt-oss/; https://huggingface.co/openai/gpt-oss-120b).
- Qwen3, pesos abertos, licença Apache 2.0, de 0,6B a 235B parâmetros, roda com vLLM, SGLang ou Ollama
  (https://github.com/QwenLM/Qwen3).
- Aluguel de placa H100 de 80 GB: de US$ 1,49 a US$ 6,98 por hora, mediana de US$ 3,44 em set/2026
  (https://intuitionlabs.ai/articles/h100-rental-prices-cloud-comparison;
  https://www.thundercompute.com/blog/nvidia-h100-pricing).

<a id="adr-82"></a>

### ADR-82 · Os indicadores de "Desempenho da IA" passam a ser os do dia a dia 🧪

**Contexto (2026-09-26, decisão 4 do usuário).** A sub-aba "Desempenho da IA" (Telemetria) mostra hoje os resultados
dos experimentos (B0 a B5, prova congelada). O usuário quer acompanhar ali o que faz sentido no dia a dia; os
experimentos vão para a apresentação executiva.

**Decisão.** A sub-aba fica, com o nome atual, e os indicadores serão revistos. **Proposta, para o usuário revisar
antes de construir:**

| Indicador | Pergunta que responde | De onde vem |
|---|---|---|
| Colunas aceitas sem mudança | Quanto a empresa confia na sugestão da IA? | Aceite das colunas × plano sugerido |
| Colunas que a empresa mudou, por campo | Onde a IA erra mais esta semana? | Aceite das colunas |
| Perguntas da IA por envio e as respondidas | A IA está pedindo ajuda demais? | Perguntas do Leitor e do Interpretador |
| Valores que a IA apontou e o código não achou no documento | A IA está tentando inventar? | Conferência do Leitor (decisão 6) |
| Tempo de leitura por arquivo | A IA está lenta? | Eventos de execução |
| Custo por arquivo e do mês × teto | Quanto a IA custa? | Tokens dos eventos |
| Chamadas com erro ou provedor fora do ar | A IA está disponível? | Eventos de execução |
| Alertas do guardrail (injeção, número inventado) | Alguém tentou enganar a IA? | Eventos do guardrail |

**Falta.** O ok do usuário na lista; depois, a sub-aba com esses números e os experimentos só na apresentação.

<a id="adr-83"></a>

### ADR-83 · "Preencher para todos": o campo que o documento não traz, digitado uma vez ✅

> **Alterado pelo [ADR-124](#adr-124) (2026-09-28):** o valor para todos vale só para o dado da empresa (CNPJ,
> unidade, endereço comercial e data de referência da renda: a marcação "Pode ser igual para todos" do parâmetro). A
> informação de cada pessoa, como o CPF, só chega num arquivo novo, com a coluna.

**Contexto.** Um Word em texto corrido quase nunca fala do CNPJ do empregador nem da unidade: o documento descreve
pessoas, não a empresa. O campo obrigatório vira a pendência "O arquivo não tem coluna para…" do arquivo inteiro, e
a tela só dizia "incluir a coluna e reenviar". Na prática, o envio nunca ficava pronto.

**Opções.** A · pedir à empresa para trocar o arquivo; B · puxar o valor do cadastro da empresa sozinho (errado
quando o funcionário é de uma filial ou do grupo, ADR-77); **C · a empresa digita o valor uma vez, e ele entra em
quem está sem o dado**.

**Decisão.** C.
- `correcoes.preencher_para_todos`: padroniza o valor uma vez pelas regras do Normalizador; grava uma correção
  APLICADA por funcionário sem o campo, com quem clicou (o clique é a decisão humana, ADR-16); registra na trilha
  `CORRECAO_PARA_TODOS` com o campo e quantos, sem o valor; valida o envio de novo uma vez só.
- **Quem já tem o dado não muda:** o valor do documento continua valendo (decisão 6).
- **Validador:** um campo sem coluna, mas preenchido por correção, conta como presente, e o valor passa pelas mesmas
  regras (ex.: um CNPJ de outra raiz em todos vira a pergunta "é do grupo?", ADR-77).
- **Tela (Acompanhar):** o cartão do "Arquivo inteiro" ganha "Valor para todos" + **"Preencher para todos"**; o
  cartão de campo obrigatório vazio de uma pessoa ganha "Usar este valor em todos que estão sem este dado".
- Rota `POST /api/empresa/pendencias/preencher_para_todos` (só o RH da própria empresa).

**Trade-off.** Um valor digitado errado vai para todos de uma vez; em compensação, o Validador confere o valor na
hora, e cada pessoa pode ser corrigida depois pelo cartão dela.

**Como comprovar.** `tests/test_preencher_para_todos.py` (o campo que o arquivo não traz, as regras valendo sobre o
valor, quem já tem o dado não muda, as recusas) e `tests/test_acompanhamento.py::test_api_preenche_para_todos_so_na_propria_empresa`.
Ponta a ponta de clique `e2e_preencher.py` (scratchpad da sessão a36903b5, porta 8766).

<a id="adr-84"></a>

### ADR-84 · Roteiros de clique no repositório (`tests/e2e/`), fora da bateria rápida ✅

**Contexto.** Cada mudança de tela era conferida por um roteiro de clique no Playwright, escrito na pasta de
rascunho da sessão e rodado contra um servidor montado à mão (banco temporário, variáveis de ambiente, porta). Os
roteiros não iam para o Git: quem clona o projeto não consegue repetir a conferência, e a próxima sessão depende de
achar o rascunho certo.

**Opções.** A · deixar como estava; B · roteiros dentro do `pytest`; **C · pasta `tests/e2e/` com um executor que
monta o ambiente sozinho, fora do `pytest`**.

**Decisão.** C.
- `tests/e2e/rodar.py`: para cada roteiro, cria uma pasta temporária com um SQLite novo, roda o `preparar()` do
  roteiro num processo separado (a configuração lê o ambiente ao ser importada), sobe a API numa porta livre, em
  MOCK e com as chaves vazias (nada de custo, mesmo com o `.env` preenchido), percorre as telas no Chrome
  (`channel="chrome"`), desliga o servidor e apaga a pasta. Um passo "FALHOU" ou um erro de JavaScript reprova.
- `tests/e2e/apoio.py`: os usuários de teste e o `entrar`. `tests/e2e/roteiros/`: um arquivo por roteiro
  (`DESCRICAO`, `preparar`, `percorrer`): `acompanhar`, `cnpj_do_grupo`, `conferencia_da_lista`,
  `divisao_do_endereco`, `janela_de_cadastro`, `navegacao`, `parametros` e `preencher_para_todos`. O Word e a
  planilha de exemplo são criados pelo `apoio.py` na pasta temporária.
- `tests/e2e/requirements.txt` fixa o Playwright 1.63.0, fora do `requirements.txt` principal, para não pesar a
  imagem do Docker. Os arquivos não começam com `test_`: o `pytest` não os recolhe.

**Trade-off.** Os roteiros levam dezenas de segundos cada e precisam do Chrome instalado; por isso ficam fora da
bateria rápida e são rodados ao mexer numa tela. O roteiro antigo do Word (`e2e_word.py`, do rascunho) não foi
trazido: a tela dele mudou, e o `conferencia_da_lista` cobre o mesmo Word na tela atual.

**Como comprovar.** `python tests/e2e/rodar.py`: 8 roteiros, 74 passos, "tudo certo" (2026-09-26); o `pytest`
continua recolhendo 752 testes.

<a id="adr-85"></a>

### ADR-85 · Catálogo com categoria e as três partes da vitrine, sem quebrar o texto livre ✅

**Contexto.** A vitrine "Benefícios do seu time" foi desenhada com filtros por categoria e uma janela com "Como
funciona", "Quem pode usar" e "Como contratar". O catálogo real (um Markdown por empresa, ADR-19) era texto livre: a
tela escondia os filtros e mostrava o texto inteiro. E o catálogo da Aurora tinha só 3 dos benefícios que o layout
mostrava.

**Opções.** A · campos novos numa tabela do catálogo (o banco preencheria um formulário); **B · convenções no próprio
Markdown**, lidas por regra; C · deixar a IA separar as partes (custo e risco de inventar).

**Decisão.** B.
- Em cada benefício (`## Título`): uma linha `Categoria: Conta e dia a dia | Crédito | Proteção | Investimentos` e as
  partes `### Como funciona`, `### Quem pode usar`, `### Como contratar`. `catalogo.partes_do_beneficio` separa por
  regra; `catalogo.o_que_falta_no_beneficio` diz o que falta.
- **Compatível com o texto livre:** catálogo sem as convenções continua valendo; a vitrine mostra o texto como está,
  sem inventar parte nenhuma. Categoria desconhecida não vira filtro.
- `/api/empresa/beneficios` traz `categoria`, `resumo` e `partes` de cada benefício; o `texto` do quadro de dúvidas
  vem sem as marcas do Markdown. A vitrine mostra só os filtros das categorias que o catálogo usa.
- **O banco fica sabendo:** publicar uma versão devolve `incompletos` (benefício e o que falta), e o recado da aba
  Empresas lista o que completar. A versão grava assim mesmo.
- **Endomarketing:** cada trecho vai ao pedido numa linha só (a fonte na frente), sem a linha da categoria e com
  "### Como funciona" virando "Como funciona:". Antes, uma segunda linha do trecho perdia a fonte.
- **Catálogo da Aurora:** as 3 seções de antes (com o mesmo texto de abertura) ganharam categoria e as partes, e
  entraram salário antecipado, cartão de crédito com cashback e primeiro investimento. **Sem seguro de vida, de
  propósito:** a avaliação congelada do Endomarketing (EXP-006) usa "seguro de vida em grupo" como assunto que o
  catálogo da Aurora não traz. As consultas congeladas do RAG continuam valendo (34 trechos no índice do catálogo).

**Trade-off.** O banco precisa escrever o catálogo seguindo a convenção; o recado da publicação ajuda. As medições do
EXP-006 (fidelidade com a IA real) foram feitas com o catálogo antigo da Aurora; refazer custa dinheiro e fica com o
usuário. O banco local (PostgreSQL) guarda o catálogo publicado: para ver o novo na porta 8000, o banco publica uma
versão nova pela aba Empresas (o arquivo está em `data/parametros/catalogo/`).

**Como comprovar.** `tests/test_parametros_e_catalogo.py` (partes, o que falta, a vitrine da Aurora com 6 benefícios
completos), `tests/test_empresas.py` (a publicação avisa o incompleto), `tests/test_rag.py` e as avaliações
congeladas; roteiro de clique `vitrine_de_beneficios` (filtros e janela com as três partes).

<a id="adr-86"></a>

### ADR-86 · Envios paginados no servidor ✅

**Contexto.** Acompanhar mostrava os envios 5 por vez, mas buscava a lista inteira: para cada envio, o servidor
montava a linha do tempo (eventos da auditoria) e lia a homologação. Uma empresa grande pode ter centenas de envios.

**Opções.** A · manter a lista inteira e esconder na tela; **B · página no banco de dados (LIMIT e OFFSET)**, com o
total à parte; C · rolagem infinita.

**Decisão.** B.
- `processamentos.listar_pagina` (a mesma ordem de `listar`: do mais recente para o mais antigo, desempate pela
  ordem de gravação) e `processamentos.contar`.
- `acompanhamento.pagina_de_envios(conexao, empresa_id, inicio, quantidade)` monta só os envios da página e devolve
  `{envios, total, inicio, quantidade}`; quantidade de 1 a 50. `envios_da_empresa` continua para o resumo e os
  portais, com a montagem de cada envio num lugar só (`_envio_para_a_tela`).
- Rota `GET /api/empresa/envios/pagina?inicio=&quantidade=`; a rota da lista inteira (`/api/empresa/envios`) saiu,
  porque ninguém mais a usava.
- Tela: a primeira página traz os 5 mais recentes; "Mostrar mais envios" busca a próxima e põe no fim; "Mostrando X
  de Y" usa o total do servidor. Sem servidor, o exemplo do layout continua como antes.

**Trade-off.** Depois de resolver uma pendência, a lista volta à primeira página (a tela recarrega os envios).

**Como comprovar.** `tests/test_acompanhamento.py::test_pagina_de_envios_monta_so_a_pagina_pedida` (as páginas
juntas dão a lista inteira, na mesma ordem; limites recusados) e o roteiro de clique `envios_paginados`.

<a id="adr-87"></a>

### ADR-87 · A arte do endomarketing usa o kit que o banco gravou ✅

> **Alterado pelo [ADR-115](#adr-115) (2026-09-28):** a arte é desenhada no Portal Interno, com o kit da empresa, e
> guardada ao publicar; a empresa baixa a imagem validada pelo banco. A rota `GET /api/empresa/endomarketing/kit`
> saiu. O kit próprio ganhou o logo (PNG ou JPEG até 500 KB, com a assinatura conferida): deixou de ser evolução.

**Contexto.** O especialista escolhe, na aba Empresas, o kit de endomarketing de cada empresa: o padrão Santander ou
um kit próprio (descrição e até 5 cores). A arte ("a IA escreve, o molde desenha") ainda usava um kit fixo do
protótipo: o padrão, ou o kit de exemplo da Aurora com `?kit=aurora` no endereço.

**Decisão.**
- `portal_da_empresa.kit_visual_da_empresa`: padrão → as cores do Santander, sem assinatura; kit próprio → a 1ª cor
  gravada é a principal (a faixa de cima), a 2ª é a do rodapé (sem ela, a principal escurecida a 70%), e a
  assinatura é o nome da empresa. Kit próprio sem cores fica nas cores do padrão, com a assinatura.
- Rota `GET /api/empresa/endomarketing/kit` (só o RH da empresa; cada empresa recebe o próprio kit).
- A tela da empresa põe esse kit em `KITS_VISUAIS.servidor`, e a arte e o recado "Kit visual: … · definido pelo
  banco" passam a usá-lo. Sem servidor, o protótipo continua como antes.
- Na aba Empresas, o campo das cores diz o papel de cada uma.

**Trade-off.** O logo ainda é texto (a marca e a assinatura escritas no molde): subir o arquivo de logo aprovado é
evolução. O kit não tem vigência própria (o item "kit vencido não é usado" do T19 fica para quando houver).

**Como comprovar.** `tests/test_portal_da_empresa.py::test_t19_arte_usa_o_kit_que_o_banco_definiu` e o roteiro de
clique `arte_com_o_kit` (a faixa da arte sai na cor gravada pelo banco, conferida no pixel do desenho).

**Complemento (T18, arte fiel ao texto).** A arte anota no próprio desenho tudo o que escreveu (a marca, a
assinatura, o título, a frase e o rodapé com a fonte): no rótulo de acessibilidade, para quem usa leitor de tela, e
em `data-textos-da-arte`, para a conferência. O roteiro `arte_fiel_ao_texto` gera um material e confere, nos três
moldes, que todo texto da arte é o título, um trecho ou a fonte de um trecho do material (fora a marca do kit).
Corrigido junto: com um material de um trecho só, a arte quebrava (pegava sempre o segundo trecho).

<a id="adr-88"></a>

### ADR-88 · Mais formatos por regra: Excel antigo (.xls), LibreOffice (.ods) e texto (.txt) ✅

**Contexto.** A tela aceitava Excel (.xlsx), CSV e Word (.docx). Muitas empresas ainda exportam Excel antigo ou usam
o LibreOffice, e o RH às vezes manda um texto simples. PDF, foto e print de conversa precisam de IA com visão e
continuam para depois.

**Decisão.**
- **.xls e .ods:** lidos pelo pandas (motores `xlrd` e `odf`), célula por célula, com o mesmo tratamento do .xlsx
  (número marcado como número, data em AAAA-MM-DD com aviso, aviso das outras abas). A assinatura dos bytes confere
  com a extensão: .xls é OLE (o formato antigo da Microsoft); .ods é zip.
- **.txt:** `texto_parece_tabela` decide por regra: se a maioria das linhas tem o mesmo número de um separador
  (";", tab, "|", ou 2 ou mais vírgulas), é lido como CSV; senão, vira um Word em memória (um parágrafo por linha) e
  segue o caminho do Word: fichas "Rótulo: valor" por regra, texto corrido pelo Leitor, com etiquetas.
- A tabela lida do .txt fica guardada ao lado do original, como a do Word: as etapas seguintes não chamam a IA de
  novo.
- `requirements.txt` fixa `pandas==3.0.6` (já vinha com o Streamlit; agora é usado direto), `xlrd==2.0.2` e
  `odfpy==1.4.1`. A tela diz os formatos novos e o seletor de arquivo os aceita.

**Trade-off.** No .xls e no .ods, a fórmula não é detectada (o pandas entrega só o valor gravado); no .xlsx ela
continua recusada.

**Como comprovar.** `tests/test_formatos_de_arquivo.py` (o .xls de teste em `tests/dados/`, gerado uma vez com a
biblioteca xlwt; o .ods feito na hora; os dois tipos de .txt; as assinaturas; a regra da tabela).

<a id="adr-89"></a>

### ADR-89 · Word do LibreOffice (.odt) e texto formatado (.rtf), convertidos para os caminhos que já existem ✅

**Contexto.** Depois do ADR-88, faltavam os documentos de texto que não são .docx: o .odt (LibreOffice) e o .rtf.

**Opções.** A · um leitor para cada formato; **B · converter para o que já é lido** (o .odt vira Word; o .rtf vira
texto); C · pedir à empresa que salve como .docx.

**Decisão.** B, em `services/conversao_de_documentos.py`, sem IA.
- **.odt → Word em memória:** os parágrafos, os títulos, os itens de lista e as tabelas, na mesma ordem (célula
  repetida do ODF expandida; linha sem texto fora). Segue o caminho do Word: tabela e fichas por regra, texto corrido
  pelo Leitor, com etiquetas. Um pacote do LibreOffice que não é documento de texto (ex.: uma planilha .ods com o
  nome .odt) é recusado com o caminho certo.
- **.rtf → texto** (biblioteca `striprtf`, fixada em `striprtf==0.0.33`): os acentos escritos como código voltam a
  ser letras; a linha de tabela vira as células separadas por "|". Segue o caminho do .txt.
- **A regra "o texto parece uma tabela?" ficou melhor:** as linhas antes da primeira com separador (um título como
  "Lista de funcionários") não contam, e a tabela precisa de pelo menos 2 linhas iguais.
- As assinaturas conferem com a extensão (.odt é zip; .rtf começa com "{\\rtf"); a tabela lida fica guardada,
  como a do Word; a tela anuncia e aceita os dois formatos.

**Trade-off.** A formatação do documento (negrito, cores, imagens) não importa e se perde na conversão; só o texto e
as tabelas contam, que é o que a leitura usa.

**Como comprovar.** `tests/test_formatos_de_arquivo.py`: .odt com tabela (por regra) e em texto corrido (Leitor),
.rtf com tabela, título e acento, e as extensões trocadas recusadas.

<a id="adr-90"></a>

### ADR-90 · A estrutura da planilha, por regra: total, sem cabeçalho, células mescladas e abas vazias ✅

**Contexto.** A leitura já achava o cabeçalho abaixo de um título. Quatro jeitos comuns de montar a planilha ainda
davam errado: a linha de total no fim virava um "funcionário" cheio de pendências; a planilha sem cabeçalho perdia a
primeira pessoa (virava o nome das colunas); a unidade mesclada em várias linhas só valia para a primeira; e uma capa
vazia antes da lista fazia a leitura recusar o arquivo.

**Decisão (sem IA, com aviso à empresa em cada caso).**
- **Linha de total:** `linha_parece_de_total`: alguma célula é "Total", "Total geral", "Subtotal", "Totais",
  "Soma" ou "Quantidade de funcionários" (sem acento, com ou sem ":"), e a linha não tem CPF válido. Fica de fora.
- **Sem cabeçalho:** `linha_parece_dado`: se a linha escolhida como cabeçalho tem CPF ou CNPJ válido, ou uma data,
  ela é uma pessoa. As colunas viram "Coluna 1, 2…" e a IA descobre cada uma pelas amostras (mascaradas).
- **Células mescladas (.xlsx):** a planilha é aberta inteira (não só para leitura) para ver os grupos mesclados; o
  valor da primeira célula vale para todas as células do grupo.
- **Abas:** é lida a primeira aba com conteúdo (no .xlsx, .xls e .ods), e o aviso diz qual.

**Trade-off.** Abrir o .xlsx inteiro gasta mais memória que a leitura "só para leitura"; com o limite de 5 MB por
arquivo, cabe com folga. Um cabeçalho com uma data no nome de uma coluna (ex.: "Admissão 01/09/2026") seria lido como
pessoa; é raro, e o aviso da tela mostra o que aconteceu.

**Como comprovar.** `tests/test_estrutura_da_planilha.py` (os quatro casos e as duas regras) e a bateria inteira,
com as avaliações congeladas, sem mudança.

<a id="adr-91"></a>

### ADR-91 · A consulta de funcionários mostra todos: cadastrados, em análise e pendentes ✅

> **Revisto pelo [ADR-155](#adr-155) (2026-09-30), só no download:** o "Baixar lista" traz a grade inteira, em todas as
> situações. A ficha continua só de quem já foi cadastrado.

**Contexto.** A tabela de funcionários de Acompanhar tem o filtro "Cadastrado / Em análise / Pendente", mas a API só
devolvia os cadastrados: os outros dois filtros nunca tinham ninguém.

**Decisão.**
- `acompanhamento.todos_os_funcionarios_da_empresa`: os cadastrados (como antes, com o id para a ficha e o
  download), mais as pessoas dos envios ainda não cadastrados, lidas dos dados atuais do envio (padronização +
  correções): "Em análise" (envio mandado ao banco) e "Pendente" (envio com a empresa ou devolvido pelo banco), com
  a primeira pendência da pessoa, ou "Ainda não enviado ao banco".
- A mesma pessoa (CPF) aparece uma vez, na situação mais adiantada (cadastrado > em análise > pendente). Envio
  descartado não entra; envio antes do aceite das colunas ainda não tem pessoas.
- **Sem vazar o CPF inteiro:** a função interna `_cadastrados_por_cpf` guarda o CPF só na chave do dicionário; a
  pessoa que sai para a tela leva o CPF mascarado. Em análise e pendentes vêm sem id: a ficha com o CPF inteiro e o
  download são só de quem já foi cadastrado (os outros ainda podem mudar).
- `GET /api/empresa/funcionarios` passa a devolver a consulta completa; a tela usa a situação e a pendência do
  servidor.

**Trade-off.** A lista continua filtrada na tela, sem paginação no servidor: uma empresa típica tem centenas ou
poucos milhares de funcionários. A paginação fica como evolução, junto com a busca no servidor.

**Como comprovar.** `tests/test_acompanhamento.py::test_todos_os_funcionarios_com_a_situacao_de_cada_um` e os
testes de sigilo (T9, T17), que continuam passando.

**Complemento (o histórico da ficha).** Cada pessoa da consulta traz o código do envio em que entrou (não é dado
pessoal). A ficha busca a linha do tempo desse envio (`GET /api/empresa/envios/{id}/linha_do_tempo`, só da empresa
da sessão; de outra empresa, 404) e mostra as etapas reais com a data e a hora: enviado (e por quem), lido pela IA,
conferido, enviado ao banco, cadastrado; e a pendência da pessoa, se houver. Antes, o histórico era um texto fixo.
Comprovado por `test_api_linha_do_tempo_do_envio_da_ficha` e pelo roteiro de clique `acompanhar`.

<a id="adr-92"></a>

### ADR-92 · Mensagem de recusa que diz o caminho, formato por formato ✅

**Contexto.** Todo formato fora da lista recebia a mesma frase ("Formato .x não aceito…"), e uma planilha protegida
por senha aparecia como "corrompida". A empresa não sabia o que fazer.

**Decisão.** `ingestao.CAMINHO_POR_FORMATO_NAO_LIDO` diz, para cada formato conhecido que ainda não é lido, o caminho
de hoje:
- **PDF:** exportar a lista do sistema para Excel ou CSV, ou copiar o texto para um Word;
- **fotos** (.jpg, .png, .heic, .webp…): mandar a lista em planilha ou texto, ou digitar numa planilha;
- **Numbers e Pages (Apple):** exportar para Excel ou Word;
- **compactados** (.zip, .rar, .7z): descompactar e enviar o arquivo de dentro.
E o **Excel ou Word protegido por senha** (o Office grava o arquivo criptografado no formato OLE, não em zip) recebe
"O arquivo está protegido por senha… tire a senha e envie de novo", em vez de "corrompido".

**Trade-off.** A lista dos formatos com caminho é mantida à mão; um formato desconhecido continua com a frase geral,
que diz os formatos aceitos.

**Como comprovar.** `tests/test_ingestao.py::test_recusa_arquivo_invalido` (PDF, foto, Numbers, zip, .xlsx e .docx
protegidos, e um programa .exe).

<a id="adr-93"></a>

### ADR-93 · Endomarketing: "Lembrete de conta" para toda a equipe e o canal que decide o tamanho (prompt v2) 🧪

> **Alterado pelo [ADR-150](#adr-150) (2026-09-30):** o WhatsApp continua com até 3 blocos, mas o limite não corta
> mais: os blocos a mais se juntam no último, e todo benefício escolhido aparece em qualquer canal.

> **Alterado pelo [ADR-115](#adr-115) (2026-09-28):** o tipo "Lembrete de conta" e o canal são escolhidos pelo
> especialista do banco, na aba Endomarketing do Portal Interno; o corte do WhatsApp por regra continua igual.

**Contexto.** A tela de Endomarketing oferecia o tipo "Lembrete de conta" e a escolha do canal (e-mail, mural,
WhatsApp), mas o agente não conhecia nenhum dos dois: o lembrete ficava desligado, e o canal não chegava ao agente.

**Decisão.**
- **Prompt `endomarketing_v2`** (a v1 fica intacta: foi ela que o EXP-006 mediu): o tipo `lembrete_conta`, escrito
  para toda a equipe, como convite, sem nunca dizer ou sugerir que alguém ainda não tem conta (o banco não informa
  isso à empresa, ADR-30); e o canal, que muda o tamanho, nunca o conteúdo.
- **O corte do WhatsApp é por regra:** depois da conferência das fontes, no máximo 3 blocos, com aviso. Não depende
  de a IA obedecer.
- O canal chega ao agente (`canal` na rota, no serviço e na porta de acesso) e fica gravado no material; canal
  desconhecido é recusado. A tela liga o "Lembrete de conta" com a explicação do sigilo bancário.

**Pendente (🧪, custa dinheiro):** medir a v2 com a IA real na mesma avaliação do EXP-006 (fidelidade às fontes e o
lembrete sem falar de quem tem conta). Em modo simulado, a avaliação continua passando.

**Como comprovar.** `tests/test_endomarketing.py` (o lembrete e o corte do WhatsApp) e o roteiro de clique
`lembrete_no_whatsapp`.

<a id="adr-94"></a>

### ADR-94 · O prazo de resposta de 1 dia útil, medido nas conversas de ajuda ✅

**Contexto.** O "Posso ajudar?" liga a empresa ao especialista do banco. O desenho pedia um prazo de resposta de
1 dia útil, medido; a aba Mensagens só separava "Sem resposta" de "Respondida".

**Decisão.**
- `mensagens.prazo_de_um_dia_util`: o prazo é o mesmo horário do próximo dia útil; sábado e domingo não contam
  (mensagem no fim de semana conta a partir de segunda, 0h). Feriados ficam como evolução.
- `mensagens.prazo_das_respostas`: cada vez que a empresa escreve e fica esperando (mensagens seguidas contam como
  uma) é uma pergunta; conta as respondidas, as respondidas no prazo (e o percentual), as esperando e as atrasadas.
  Conversa resolvida pelo banco sem resposta escrita não conta como esperando.
- Rota `GET /api/banco/conversas/prazo` (só o banco). Na aba Mensagens: o resumo acima da lista ("Prazo de 1 dia
  útil: 9 de 10 perguntas respondidas no prazo (90%) · 1 atrasada") e o selo **"Atrasada"** na conversa esperando há
  mais de 1 dia útil.

**Trade-off.** O prazo ignora feriados e o horário comercial (conta as 24 horas do dia útil); é a medida simples que
o desenho pedia, e fica fácil de trocar numa função só.

**Como comprovar.** `tests/test_mensagens.py` (as três datas do prazo; respondida no prazo, fora do prazo, esperando
atrasada e conversa resolvida; a rota só do banco) e o roteiro de clique `prazo_das_mensagens`.

<a id="adr-95"></a>

### ADR-95 · O progresso do envio ao vivo, em frases curtas ✅

**Contexto.** Com a IA real, ler um Word em texto corrido leva dezenas de segundos, e a tela só mostrava o
cronômetro. O desenho pedia mensagens curtas enquanto o fluxo roda. Havia também um defeito escondido: a rota de
envio era assíncrona, mas fazia o trabalho pesado nela mesma, e o servidor não atendia mais nada enquanto lia.

**Opções.** A · passar uma função de aviso por toda a cadeia (cadastro → processamentos → ingestão → Word → Leitor);
B · WebSocket ou SSE com o fluxo inteiro; **C · um código do pedido e uma "variável de contexto" (contextvars), com a
tela perguntando a cada segundo**.

**Decisão.** C.
- `services/progresso.py`: `comecar` prende o código do pedido à tarefa, `anotar("frase")` escreve a frase do
  momento (fora de um pedido com código, não faz nada), `frase_do_pedido` devolve a frase só para quem enviou. As
  frases ficam na memória do servidor, sem dado de ninguém.
- As frases: "Lendo o arquivo.", "É um texto corrido: a IA está separando o texto por pessoa.", "A IA está lendo N
  trecho(s) do texto.", "A IA leu k de N trecho(s).", "Conferindo cada valor com o documento." e "A IA está
  entendendo cada coluna e ligando ao layout do banco."
- A rota de envio recebe `pedido_de_progresso` e roda o trabalho numa linha de execução à parte
  (`run_in_threadpool`); `GET /api/empresa/cadastro/progresso/{código}` devolve a frase. A tela sorteia o código,
  manda com o arquivo e mostra a frase no painel da IA a cada segundo.

**Trade-off.** Perguntar a cada segundo é mais simples que uma conexão aberta (SSE), com um pedido pequeno por
segundo durante a leitura. Um servidor reiniciado esquece as frases (a tela volta ao cronômetro).

**Como comprovar.** `tests/test_progresso.py` (o módulo; as frases na ordem num Word em texto corrido, sem dado de
ninguém; a rota só para quem enviou) e os 14 roteiros de clique, que enviam arquivos pela rota nova.

### ADR-71, revisto (2026-09-26, decisão do usuário) · Pontos de salvamento guardados para sempre ✅

A limpeza de 90 dias sai (`services/pontos_de_salvamento.py` e `scripts/limpar_pontos_de_salvamento.py` foram
removidos). Porquê: o ponto não tem dado pessoal, ocupa pouco e mostra onde cada envio parou, o que ajuda a empresa e
o banco a reconstituir a história (ex.: dois bancos no mesmo contrato, e a empresa descobre meses depois que deixou de
enviar parte da equipe). A proteção para ponto perdido continua (`fluxo_empresa._situacao_de_envio_encerrado`): o
envio encerrado aparece como concluído e nunca recomeça. Testes: `test_ponto_de_salvamento_fica_guardado_depois_do_fim`,
`test_ponto_perdido_o_envio_continua_concluido_e_nao_recomeca`, `test_envio_descartado_mostra_o_motivo_mesmo_sem_o_ponto`.
### ADR-30, confirmado (2026-09-26, decisão do usuário) · Conta aberta só em agregado, com a lei na tela ✅

A empresa continua vendo só totais (mínimo de 10 pessoas por grupo; lembrete para toda a equipe). A tela passa a
explicar o porquê com a lei: a nota do quadro "Abertura das contas" de Acompanhar (sempre à mostra) cita a **Lei
Complementar nº 105/2001** (sigilo bancário: o banco não informa ao empregador se uma pessoa é cliente sem a
autorização dela), e a etapa 4 da Home lembra a lei numa linha. A opção "pessoa por pessoa, só com autorização" fica
como evolução, depois do jurídico. Teste: `test_quadro_de_contas_explica_o_sigilo_bancario_pela_lei`.
**Revisto pelo ADR-102 (2026-09-27):** a opção "pessoa por pessoa, com autorização" foi adotada.

<a id="adr-79"></a>

### ADR-79 · Segredos fora da cópia de segurança; `.env.example` como modelo ✅

**Contexto (2026-09-26, decisão do usuário).** A cópia diária do projeto vai para o Google Drive. O `.env` tem as chaves
de API e as senhas.

**Opções.** A · copiar o `.env` junto (restaurar é só copiar, mas as chaves ficam espalhadas em várias cópias com
data); **B · não copiar e guardar os segredos num gerenciador de senhas**; C · copiar num arquivo com senha (mais uma
senha para lembrar).

**Decisão.** B. O `scripts/copia_de_seguranca.py` copia `D:\AI_Payroll_Hub` para `G:\Meu Drive\ProjetoIA\AAAAMMDD_HHMM`
sem o `.env`, sem ambientes virtuais, modelos baixados e índices (refeitos), e junta uma cópia do PostgreSQL
(`pg_dump`). O `.env.example` marca cada segredo com `[SEGREDO]`, diz onde conseguir e explica como recriar o `.env`;
o README ganhou "Como recriar o `.env`" e "Cópia de segurança" (com a tarefa diária do Agendador do Windows, que o
usuário cria). **Trade-off:** restaurar pede uns 5 minutos para preencher o `.env` pelo gerenciador de senhas.
**Testes:** `test_o_que_fica_de_fora`, `test_copia_com_data_sem_os_segredos`. Simulação real: 1.183 arquivos, 55 MB.

<a id="adr-96"></a>

### ADR-96 · A IA pelo AWS Bedrock, no perfil EUA, com retenção zero 🟨

**Contexto (2026-09-27, pergunta do usuário).** "E se um dado pessoal vazar para a IA porque o rótulo está errado?"
Os testes com casos bagunçados mostraram que a máscara decide pelo conteúdo (um CPF com rótulo aleatório sai como
`999.999.999-99`), mas acharam furos: coluna repetida vai sem máscara ("CPF do gestor", "Nome do gestor"), o cabeçalho
vai sem conferência, e no texto corrido passam nome em minúsculas, nome grudado ("MariaSouza") e CPF por extenso.
Qualquer filtro na frente da IA é um detector, e detector erra. A pergunta passou a ser: **quem recebe o pedido?**

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · APIs diretas (Anthropic e OpenAI), como era | Simples; já medida | O fornecedor do modelo recebe o pedido, pelas regras dele |
| B · IA local (modelo aberto nesta máquina, Ollama) | O dado nunca sai do computador | **EXP-011:** placa de 4 GB; 11 min numa planilha de 18 colunas, duas respostas fora do contrato, **0 de 18** acertos (granite4.2:3b); inviável aqui e na demo |
| C · Bedrock, perfil global | Mesmos modelos; ~10% mais barato | O pedido pode ser processado em qualquer região do mundo |
| **D · Bedrock, perfil EUA** | Mesmos modelos (Sonnet 5 e GPT-6 Luna); roda em contas operadas pela AWS, **sem acesso do fornecedor** aos pedidos; geografia fixa (EUA e Canadá) e registrada em cada chamada; uma fatura só | 10% a mais que o global; o dado sai do Brasil (como já saía na opção A) |

**Decisão.** D. `ROTA_DA_IA=bedrock` no `.env`; a troca fica toda em `services/provedores_de_ia.py` (a porta única de
saída): o nome vira `us.<fornecedor>.<modelo>`, os clientes oficiais da Anthropic e da OpenAI apontam para o endereço
do Bedrock com a chave do Bedrock. O perfil `us` fica no código, não no `.env`: mudar a geografia do dado pede ADR.

**Duas travas contra os modelos que guardam os pedidos** (decisão do usuário: ficam fora por proteção):
1. no código, `MODELOS_QUE_GUARDAM_PEDIDOS` (Claude Fable 5 e 5.1, GPT-6 Astra e a linha GPT-5.x que guarda pedidos
   por até 30 dias para detectar abuso, pela documentação do Bedrock de 2026-09-27): o pedido é recusado antes de sair,
   em qualquer rota;
2. na conta, a retenção zero (`data_retention_mode: none`, gravada por `scripts/preparar_bedrock.py`): com ela, o
   próprio Bedrock recusa qualquer modelo que exija guardar.

**Por quê.** Não existe filtro que garanta 100% num arquivo bagunçado; o que dá para garantir é o destino. No Bedrock,
os modelos rodam em contas da AWS às quais o fornecedor não tem acesso, e a AWS não grava pedidos por padrão (nos dois
modelos do projeto). É a mesma confiança que um banco já dá à nuvem onde guarda os próprios dados, com as regras que
já conhece (LGPD, art. 33, e Resolução CMN nº 4.893/2021). A máscara e as etiquetas continuavam como segunda camada;
saíram no ADR-101.

**Trade-off.**
- **O dado sai do Brasil**: nenhum dos dois modelos roda na região de São Paulo (lá, só no perfil global). É
  transferência internacional (LGPD, art. 33), responsabilidade do banco como controlador: cláusulas-padrão no
  contrato com a AWS e aviso de privacidade; para banco, também a Resolução CMN nº 4.893/2021 (comunicar o Banco
  Central e garantir o acesso dele aos dados). Vai para o jurídico, junto com a premissa de privacidade.
- **10% a mais** no custo (perfil EUA); o teto da sessão conta o acréscimo nas duas marcas, por segurança.
- **Sem formato garantido no Claude** pelo Bedrock: o Leitor de Documentos volta a pedir o JSON no texto (ele já confere
  e refaz a resposta errada); a prova diz se isso muda o acerto.

**Como comprovar.** `tests/test_provedores_de_ia.py`: perfil EUA com a marca do fornecedor, endereço da AWS nos dois
clientes, sem formato garantido no Claude, aviso de chave faltando, recusa dos modelos que guardam pedidos antes de
qualquer cliente ser criado (nas duas rotas) e o acréscimo de 10%. **Pendente (🧪, com a chave):**
`scripts/preparar_bedrock.py` (retenção zero gravada e lida de volta; os dois modelos respondendo com ela) e
`scripts/medir_pelo_bedrock.py` (as mesmas 30 planilhas da prova congelada; a régua é a comparação pelas APIs
diretas: Sonnet 5 84,4% e Luna 76,3% de acurácia por campo).

**Origem.** Conversa de 2026-09-27; EXP-011 (IA local) registrado como resultado negativo.

<a id="adr-97"></a>

### ADR-97 · Na tela, os dados sem máscara; a máscara só no que vai para a IA ✅

**Contexto (2026-09-27, pedido do usuário).** A empresa via o CPF e outros dados pessoais mascarados nas telas dela
("***.982.247-**", "He*** Du*** Ra***"). A pergunta do usuário: "quando ela está vendo, já não é a IA que está
exibindo, e sim o sistema; e essas informações ela tem, pois foi ela que enviou". E o especialista do banco tem
autorização contratual da empresa para ver tudo, porque vai ligar o funcionário ao banco.

**Opções.** A · manter a máscara na tela (protege de quem olha por cima do ombro, mas atrapalha corrigir um CPF);
**B · mostrar inteiro na tela e manter a máscara só no caminho da IA, registrando quem abriu cada lista**; C · botão
"mostrar" por pessoa (mais cliques; a lista continua ilegível).

**Decisão.** B. O CPF sai inteiro e formatado (`acompanhamento.formatar_cpf`) na lista de funcionários, na
conferência, nos exemplos de "Como a IA leu", na prévia da divisão do endereço, nas pessoas do envio no Portal do
Banco e nas linhas "de fora" do arquivo de contas abertas. Saíram `mascarar_cpf` (Python e JavaScript) e
`ingestao.mascarar_uma_parte`, que só serviam à tela. **Não mudou:** a máscara e as etiquetas de tudo o que vai para
a IA (ADR-31, ADR-44, ADR-72), a máscara do Validador (a pendência que o Assistente de Correção recebe) e a conta
aberta só em agregado para a empresa (ADR-30, sigilo bancário). A máscara da IA e a do Validador saíram depois, no
ADR-101; a conta aberta em agregado continua.

**A prestação de contas continua.** Abrir a lista de funcionários (empresa) e a lista de pessoas de um envio (banco)
passa a ficar registrado em `acessos_a_dados` (tipo `LISTA`: quem, quando e quantas pessoas; nunca o CPF), como já
eram a ficha e o download. A resposta com CPF inteiro vai com `Cache-Control: no-store`.

**Trade-off.** Quem olha a tela por cima do ombro vê o CPF inteiro; a proteção passa a ser o login, o registro de
acesso e a minimização dos campos (a lista continua só com os campos que a tela usa).

**Como comprovar.** `tests/test_acompanhamento.py` (CPF formatado; a lista registra quem abriu, com `no-store`),
`tests/test_avaliacao_do_banco.py` (CPF inteiro e o acesso do especialista registrado), `tests/test_cadastro_conferencia.py`,
`tests/test_divisao.py`, `tests/test_contas_abertas.py`, `tests/test_leitura_de_word.py` e os roteiros de clique
`acompanhar`, `divisao_do_endereco` e `janela_de_cadastro`. Nenhum agente usa os dados de tela (conferido no código).

<a id="adr-98"></a>

### ADR-98 · O sistema se chama Integra Folha, sem a marca do banco ✅

**Contexto (2026-09-27, decisão do usuário).** O portal usava o nome e o vermelho do Santander ("Portal Empresa
Santander", "Parceira Santander", "Especialista Folha · Santander"). O sistema vai ser publicado com login na internet
e não pode parecer um sistema oficial do banco.

**Decisão.** O nome do produto é **Integra Folha** em todas as telas (logotipo, títulos das abas do navegador,
rodapés). Onde o texto fala do banco como instituição, passa a dizer "o banco" ("o salário é pago pelo banco", "seu
especialista do banco"); o kit padrão do endomarketing vira "Padrão do banco", com a marca Integra Folha na arte.
Uma paleta própria substitui o vermelho (bloco seguinte). O caso de negócio da apresentação não muda.

**Como comprovar.** Nenhuma menção a "Santander" em `front/*.html`, `front/js/*.js` e `services/*.py`;
`tests/test_portal_da_empresa.py` e os roteiros `arte_fiel_ao_texto`, `arte_com_o_kit`, `navegacao`,
`lembrete_no_whatsapp` e `vitrine_de_beneficios` passando.

**ADR-98, paleta (mesmo dia).** O vermelho sai. Cor da marca: verde-petróleo `#0e6b6f` (contraste de cerca de 6:1 com
branco), escura `#0a4f52`, clara `#e2f2f1`, sobre fundo escuro `#5ed3c7` e o tom dos degradês `#a8dcd6`; sucesso
(verde) e atenção (âmbar) continuam. Os nomes deixam de dizer a cor: `--vermelho-santander` → `--cor-marca` (e as
derivadas), `botao-vermelho` → `botao-principal`, `botao-contorno-vermelho` → `botao-contorno`. O kit padrão do
endomarketing usa a mesma cor. Testes: os 804 e os 15 roteiros de clique.

**ADR-98, paleta revista (mesmo dia, pedido do usuário: "algo mais vivo, pode ser um tom de vermelho").** O
verde-petróleo sai. Cor da marca: carmim vivo `#d62839` (contraste de cerca de 5:1 com branco; puxa levemente para o
rosa, para não lembrar o vermelho puro do banco), escura `#9e1b32` (vinho), clara `#fde8ea`, sobre fundo escuro
`#ff6b7a` e degradê `#f7b2ba`. Os nomes neutros ficam como estão.

**ADR-98, textos (mesmo dia, pedido do usuário).** "Integra Folha" é o sistema; **"Integra" é a empresa** que ocupa o
lugar do banco nos textos ("Sua equipe na Integra", "Parceira Integra desde agosto de 2026", "Especialista Integra",
"o salário é pago pela Integra"). Numa mesma tela, a Integra aparece nos títulos e destaques; os detalhes usam formas
curtas ("conosco", "na conta"), para não repetir. As frases de processo ("Enviar ao banco", "Análise do banco") ficam
como estão até decisão do usuário.

<a id="adr-99"></a>

### ADR-99 · O Assistente de Correção no front: "Perguntar à IA" em cada pendência ✅

> **Alterado pelo [ADR-118](#adr-118) (2026-09-28):** a conversa virou o único jeito de resolver a pendência: a IA
> aplica na hora, presa ao campo e à linha, com Desfazer; saíram as rotas `/assistente/decidir` e `/assistente/justificar`.

**Contexto (2026-09-27).** O Assistente de Correção (ADR-16, 17 e 20) só existia no Streamlit, que não está mais em uso:
no front, o "Corrigir com o assistente" da Home abria as pendências sem IA. Sem ele, o projeto perdia um dos agentes
e o exemplo de repasse entre agentes (Assistente → Interpretador). O usuário aprovou trazer o agente antes de remover
o Streamlit.

**Decisão.** Um "Perguntar à IA" em cada pendência, nas telas Cadastrar (conferência da lista) e Acompanhar (cartões
de pendência), com uma conversa curta logo abaixo (`front/js/assistente_de_correcao.js`). O servidor
(`services/assistente_na_tela.py`, rotas `/api/empresa/cadastro/{envio}/assistente`, `/decidir` e `/justificar`):
- **monta a pendência a partir do Validador** (o navegador só diz a regra e a linha; não consegue mandar um texto
  qualquer como pendência) e o valor dela vai mascarado para a IA (desde o ADR-101, vai o valor real);
- **propor não é aplicar** (ADR-16): a correção proposta fica PROPOSTA até o "Aplicar", que usa o mesmo
  `correcoes.decidir` das outras telas (aplica, revalida e registra quem propôs, o assistente, e quem decidiu);
- a justificativa de alerta só vale com o "Confirmar"; o repasse ao Interpretador volta o fluxo para o aceite das
  colunas (`fluxo_empresa.retomar(..., "revalidar")`, como no "Ajude a IA a acertar");
- só enquanto o envio está na correção ou na conferência; mensagem com até 1.000 caracteres, com o guardrail de
  injeção do agente; cada conversa entra na Telemetria.

**Trade-off.** A mensagem da empresa vai inteira para a IA (é o texto dela; pode conter o valor certo); com a rota
Bedrock (ADR-96), fica na nossa conta, sem retenção.

**Como comprovar.** `tests/test_assistente_na_tela.py` (8 testes: proposta só aplica no clique, recusar não muda nada,
pergunta sem proposta, justificativa só com a confirmação, repasse volta ao aceite, pendência vem do servidor, ordem
para a IA barrada, rotas só da empresa dona) e os roteiros `assistente_de_correcao` e `acompanhar`.

**ADR-98, revisto de novo (mesmo dia, decisão do usuário).** O modelo final: **Integra Folha é o sistema e o
Santander é o banco parceiro.** A tela de login (pública) não cita o Santander. Depois do login, os textos voltam a
falar do Santander ("Sua equipe no Santander", "Especialista Folha · Santander", o kit "Padrão Santander") e o
cabeçalho de todas as telas mostra o selo **"Banco parceiro: Santander"** (`.selo-banco-parceiro`, escondido no
celular). A "Integra" como empresa sai. Continuam: o nome Integra Folha no logotipo e nos títulos, a paleta carmim e
"Portal Interno" nas telas do especialista. Testes: os do portal e os 17 roteiros de clique.

<a id="adr-100"></a>

### ADR-100 · Site publicado com cuidado: invisível aos buscadores, porteiro por lista de liberação ✅

**Contexto (2026-09-27, pedidos do usuário antes da publicação).** O site vai para a internet com login: buscadores
não podem achá-lo e nenhuma tela pode abrir sem login. No teste, apareceu uma brecha: o porteiro guardava só "o que
termina em .html", e `/HOME.HTML`, `/home.html.` e `/banco_inicio.html/` abriam a página sem login (no Windows, o
arquivo é achado mesmo assim). Os dados continuavam protegidos (a API responde 401), mas a tela abria.

**Decisão.**
- **Porteiro por lista de liberação** (`pagina_precisa_de_login`): tudo exige login, menos `/login.html`,
  `/robots.txt`, `/css/`, `/js/` e `/api/` (a API confere a sessão em cada rota). Qualquer variação de endereço cai no
  "exige login".
- **Buscadores:** `robots.txt` com `Disallow: /`; cabeçalho `X-Robots-Tag: noindex, nofollow, noarchive` em toda
  resposta, inclusive nos desvios (o middleware fica registrado depois do porteiro, para envolvê-lo);
  `<meta name="robots">` em cada página; sem `/openapi.json` (o mapa das rotas da API).
- **"Lembrar de mim"** (a caixa não fazia nada): marcado, a sessão vale 7 dias e o usuário vem preenchido na próxima
  vez (só o usuário, nunca a senha); desmarcado, o cookie é de sessão (some ao fechar o navegador; no servidor, 8 h).
  > **Alterado em 2026-09-28 (pedido da usuária):** o "Lembrar de mim" saiu ("lembrar de mim não está funcionando
  > (retira ele)"). Toda sessão vale 8 horas e o cookie é sempre de sessão (some ao fechar o navegador); a tela apaga
  > o usuário que a caixa tinha guardado no navegador. Prova: `tests/test_api_front.py` (cookie sempre de sessão,
  > mesmo com o campo `lembrar` de uma tela antiga, e sessão de 8 horas) e o roteiro `tela_de_login`, que substituiu
  > o `lembrar_de_mim`.
- **Rodapé:** em todas as telas depois do login, a nota "Integra Folha é um projeto acadêmico de engenharia de IA. A
  parceria com o Santander é ilustrativa: este não é um sistema oficial do banco, e todos os dados são fictícios." No
  login, a nota fala só do projeto (sem citar o banco).
- **Cabeçalho mais limpo:** sai "Portal Empresa / Portal Interno · Folha de Pagamento" ao lado da marca, e sai o sino
  de avisos (não levava a nada útil); o total de avisos do servidor saiu junto.

**Trade-off.** Com 7 dias de sessão, um computador compartilhado com a caixa marcada fica logado; a caixa vem
desmarcada e o "Sair" continua cancelando a sessão no servidor.

**Como comprovar.** `tests/test_api_front.py` (variações do endereço, robots e X-Robots-Tag, sem openapi, cookie de
7 dias ou de sessão, validade da sessão), `tests/test_cabecalho.py` e o roteiro `lembrar_de_mim` (hoje `tela_de_login`). Os roteiros
`acompanhar` e `navegacao` passaram a esperar a janela de cadastro carregar por inteiro antes de mandar o arquivo
(corrida do roteiro, que ficou frequente com as páginas maiores).

<a id="adr-101"></a>

### ADR-101 · Com a IA pelo AWS Bedrock, ela vê os dados reais: saem a máscara e as etiquetas ✅

**Contexto (2026-09-27, decisão do usuário).** "Já decidimos que rodar na AWS resolve isso e que assim a IA pode ver os
dados da pessoa." O ADR-96 levou a IA para o Bedrock (o fornecedor do modelo não vê o pedido; retenção zero na conta),
mas deixou a máscara e as etiquetas como "segunda camada". Essas travas custavam acerto e travavam funções novas: no
EXP-010, o Leitor acertou 91,3% com etiquetas contra 98,9% lendo os dados; o Interpretador via "Xxxxx Xxxxx" no lugar
de um nome; a divisão de coluna não podia pedir ajuda à IA com o endereço real.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · manter as travas como segunda camada (ADR-96) | Duas proteções | Acerto menor; cada função nova precisa contornar a máscara; o detector erra de qualquer jeito (ADR-96) |
| B · travas ligadas só na rota direta (APIs da Anthropic e da OpenAI) | Protege se a rota voltar | Dois comportamentos para medir e explicar; a rota direta é provisória, até a chave do Bedrock |
| **C · a IA vê os dados; a proteção é o destino (Bedrock) e o controle de acesso** | Mais acerto; código mais simples; uma regra só | A proteção depende de a IA rodar pelo Bedrock com retenção zero |

**Decisão.** C. O que mudou:
- **Interpretador:** as amostras são os 3 primeiros valores diferentes de cada coluna, como estão no arquivo
  (`ingestao.amostras`); sai `ingestao.mascarar`. Prompt `interpretador_v2` (a regra 6 diz que as amostras são reais e
  continuam sendo dado).
- **Leitor de Documentos:** lê o texto real. Saem `LEITOR_VE_OS_DADOS` (`.env` e `config.py`), a troca por etiquetas
  e `juntar_blocos_sem_pessoa`. O prompt continua o `leitor_de_documentos_v4`, o mesmo que mediu 98,9% no modo "a IA vê
  os dados". O módulo `pseudonimizacao.py` virou `detector_de_dados.py`: só acha dados (aviso de parágrafo esquecido,
  o rótulo que a empresa usou, sem nome de ninguém, e o simulador MOCK). Sai `etiquetas_protegidas`.
- **Validador e Assistente de Correção:** a pendência guarda o valor real (`Achado.valor`, antes `valor_mascarado`;
  relatório antigo é lido pelo nome velho). O explicador recebe o valor de cada achado (prompt
  `explicador_validacao_v2`).
- **RAG:** o exemplo do parâmetro entra no índice também no campo de dado pessoal.
- **Telas:** o balão de ajuda mostra o exemplo de todo campo; a marcação do parâmetro virou **"Dado pessoal (LGPD)"**,
  uma classificação para o inventário de dados pessoais do banco (base do RIPD), que não esconde nada.

**O que continua (não é trava sobre o que a IA vê):** isolamento entre empresas e perfis; registro de quem abre cada
lista (ADR-97); conta aberta só em agregado para a empresa (ADR-30; revisto depois pelo ADR-102); oferta ativa só para correntista autorizado
(ADR-28, ADR-29); o Consultor e o motor só com números agregados; o guardrail de injeção (o conteúdo do arquivo é dado,
nunca instrução); as duas travas contra modelos que guardam pedidos (ADR-96); auditoria e telemetria sem dado pessoal.

**Trade-off.**
- **A proteção agora é o destino.** Enquanto a chave do Bedrock não chega, o `.env` está em `ROTA_DA_IA=direta`, e o
  dado vai para as APIs da Anthropic e da OpenAI. Hoje isso não expõe ninguém, porque todos os dados do projeto são
  fictícios. Com dado real, só pelo Bedrock.
- **Jurídico:** a transferência internacional (LGPD, art. 33) e a premissa de privacidade continuam com o jurídico
  (ADR-96).
- **Medições:** o prompt do Interpretador mudou (v1 → v2). A comparação de modelos (EXP-008) usou só os nomes das
  colunas, sem amostras, então os números dela continuam valendo como estão; o uso real, com as amostras, precisa ser
  medido de novo com IA real e o prompt v2 (já estava na lista "refazer os testes").

**Como comprovar.** `tests/test_ingestao.py` (amostras são os primeiros valores diferentes; nome e UF como estão),
`tests/test_interpretador.py` (o prompt leva exemplos reais dentro do bloco de dado), `tests/test_leitura_de_word.py`
(a IA lê nome, CPF, data e salário reais, sem etiqueta; o rótulo nunca leva o nome de alguém; aviso de parágrafo
esquecido com o texto original), `tests/test_validador.py` (o CPF inválido vem com os 11 dígitos; o explicador recebe
o valor), `tests/test_rag.py` (o exemplo do CPF entra no índice), `tests/test_cadastro_conferencia.py` (o balão traz o
exemplo do dado pessoal) e `tests/test_api_front.py` (o registro diz "dado pessoal (LGPD)"). Com a chave do Bedrock:
refazer o EXP-008 (B1 a B3) e o EXP-010 com IA real.

**Origem.** Conversa de 2026-09-27, depois do teste do usuário na tela (a coluna de endereço inteiro deixada de fora).

<a id="adr-102"></a>

### ADR-102 · A empresa vê a conta aberta de cada funcionário dela, para pagar o salário ✅

**Contexto (2026-09-27, decisão do usuário).** "A conta aberta pode aparecer por funcionário para a empresa: o banco
devolve essa informação porque depois a empresa precisa fazer o pagamento para o funcionário." Até aqui (ADR-30,
confirmado em 26/09), a empresa via só o total de contas abertas, e só a partir de 10 pessoas. Mas quem paga a folha
precisa saber a agência e a conta de cada um: sem isso, o cadastro no banco não vira salário na conta.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · só o total, com mínimo de pessoas (ADR-30) | Nenhum dado individual sai do banco | A empresa não consegue pagar o salário na conta nova; o objetivo do produto (a folha no banco) não se fecha |
| B · só "abriu / não abriu" por pessoa | Ajuda a cobrar quem falta | Sem agência e conta, a empresa ainda não paga |
| **C · agência, número e data de abertura de cada funcionário, só para a empresa dele** | Fecha o ciclo: cadastro → conta → salário | Depende do consentimento do funcionário (premissa para o jurídico) |

**Decisão.** C.
- **Arquivo semanal do banco:** passa a ter o número da conta (CPF, data de abertura, agência e conta). Cada coluna
  serve a um campo só ("Data de abertura da conta" é a data, não a conta). A tabela `contas_abertas` ganhou a coluna
  `conta` (acrescentada sem perder as baixas já feitas).
- **Empresa:** a lista de funcionários, a ficha e o CSV baixado de "Acompanhar cadastros" mostram a conta de quem já
  abriu (`contas_abertas.contas_da_empresa`, sempre filtrado pela empresa da sessão). Quem não abriu aparece como
  "Ainda não abriu".
- **Sai o mínimo de pessoas:** a premissa `minimo_pessoas_agregado` foi removida. O cartão mostra o total ("20 de 35
  já abriram a conta (57%)"); sem ninguém cadastrado, "Nenhum funcionário cadastrado ainda.". O Agente de
  Endomarketing informa o total exato de quem ainda não tem conta; o comunicado continua sem citar ninguém, porque vai
  para toda a equipe.
- **A nota da tela** troca "Por que só totais?" por "Onde ver a conta de cada funcionário?", com a base legal.

**Base legal (premissa a validar com o jurídico).** A Lei Complementar nº 105/2001 diz que não viola o sigilo a
revelação de informações com o consentimento expresso do interessado (art. 1º, § 3º, V). A premissa: ao abrir a conta
para receber o salário, o funcionário autoriza o banco a informar agência e número ao empregador, como já acontece em
folha de pagamento. É o mesmo desenho da oferta ativa (autorização dada na abertura da conta, ADR-29).

**O que continua.** Cada empresa só vê os próprios funcionários; abrir a lista, a ficha e o download fica registrado
(ADR-97); oferta ativa só para correntista autorizado (ADR-28, ADR-29); o Consultor e o motor de planejamento do banco
continuam só com números agregados.

**Trade-off.** Sem o consentimento na abertura da conta, a empresa não poderia ver a conta; se o jurídico exigir uma
autorização separada, entra uma marcação por pessoa no arquivo semanal e a tela mostra só a de quem autorizou.

**Como comprovar.** `tests/test_contas_abertas.py` (a coluna "Data de abertura da conta" não vira a conta; a conta de
cada um fica só com a empresa dele; a lista, a ficha e o download trazem agência, conta e data de quem abriu, e
vazio para quem não abriu; o texto de empresa sem cadastrados), `tests/test_acompanhamento.py`,
`tests/test_endomarketing.py`, `tests/test_portal_da_empresa.py`, `tests/test_parametros_e_catalogo.py` e
`tests/test_api_front.py` (a coluna "Conta" e a nota com a lei).

**Origem.** Conversa de 2026-09-27, durante o teste da navegação.

<a id="adr-103"></a>

### ADR-103 · O projeto passa a se chamar Integra Folha também no Git, no banco e no deck ✅

**Contexto (2026-09-27, pedido do usuário).** "Nome do deck e do projeto, inclusive no git, precisa ser uma referência
a Integra Folha (integra-folha no git, por exemplo)." As telas já diziam Integra Folha (ADR-98), mas a pasta do
repositório, o banco de dados, o Docker, a documentação e o deck continuavam "AI Payroll Hub".

**Decisão.**
- **Repositório:** a pasta passou de `ai-payroll-hub` para `integra-folha` (o histórico de commits é o mesmo).
- **PostgreSQL:** os bancos viraram `integra_folha` e `integra_folha_testes`, e o usuário da aplicação,
  `integra_folha_app` (renomeados no servidor, com a mesma senha; o `.env` só trocou os nomes).
- **SQLite e sessão:** `storage/integra_folha.db`; o cookie de sessão virou `integra_folha_sessao` (quem estava logado
  entra de novo uma vez).
- **Textos:** telas, documentação, README, Docker, scripts e testes dizem Integra Folha.
- **Deck:** nova versão com o nome Integra Folha e "Portal Interno" no lugar de "Portal do Banco" (ADR-98).

**O que fica com o nome antigo, de propósito.**
- O histórico: as ADRs anteriores, os experimentos (`docs/experimentos.md`, gerado de registros imutáveis) e os dados
  de avaliação congelados.
- Os prompts já em uso: o nome aparece só no papel dado à IA ("Você é o Agente Interpretador do AI Payroll Hub") e não
  chega a ninguém; trocar pediria nova versão e nova medição. Muda na próxima versão de cada prompt.
- A pasta raiz `D:\AI_Payroll_Hub` e o vault do Obsidian: renomear quebraria a memória do projeto no Claude Code e os
  links do vault. Podem mudar depois, com calma.

**Como comprovar.** A bateria inteira (os testes do Docker Compose conferem `integra_folha_app` e o banco
`integra_folha`; os da cópia de segurança, o arquivo `banco_integra_folha.dump`) e o roteiro `lembrar_de_mim` (hoje `tela_de_login`; o
cookie novo).

<a id="adr-104"></a>

### ADR-104 · A IA decide dividir uma coluna; a regra divide as linhas; o comentário da empresa refaz só aquela coluna 🧪

**Contexto (2026-09-27, teste do usuário na tela).** Numa importação, a coluna trazia o endereço inteiro, e a IA a
deixou de fora: ela só sabia ligar uma coluna a UM campo. A saída existia (a opção "Dividir em vários campos…", ADR-76),
mas escondida e feita à mão. O pedido do usuário: "o layout já deve vir com a marcação de campo dividido, com a
sugestão de divisão que a IA fez, e cada parte com o campo correspondente"; a IA deve "olhar a estrutura de qualquer
campo" e decidir quando dividir; se a divisão estiver errada, a empresa escreve um comentário e refaz só aquela coluna,
sem reprocessar o arquivo.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · regra fixa só para endereço | Sem custo | Não generaliza ("Cidade/UF", "banco / agência / conta"...) |
| B · a IA divide cada linha | Flexível | Custo e tempo crescem com as linhas (≈ 1 milhão de funcionários); duas leituras podem dividir diferente |
| **C · a IA decide a divisão (ferramenta e campo de cada parte); a regra divide todas as linhas; só as linhas difíceis voltam à IA** | Generaliza; custo quase zero por linha; mesmo resultado sempre; a IA só entra onde a regra não resolve | Depende de a ferramenta cobrir o formato; linha que nem a IA divide vira pendência |

**Decisão.** C.
- **Interpretador (prompt `interpretador_v3`):** para a coluna com mais de uma informação, responde `DIVIDIR` com a
  proposta: a ferramenta (`endereco`, `cidade_uf` ou `separador`, com o sinal) e o campo de cada parte. Ele olha as
  amostras reais (ADR-101) para decidir.
- **Conferência (guardrail de saída, ADR-38):** ferramenta que não existe, parte que a ferramenta não conhece ou
  nenhuma parte com campo → a coluna fica de fora, com o motivo; campo fora do layout ou repetido → a parte fica sem
  campo (`services/divisao_da_coluna.conferir_proposta`).
- **Aplicação (`services/divisao_da_coluna.aplicar`):** a regra de `services/divisao.py` divide todas as linhas; cada
  parte vira uma coluna ("Endereço · rua") ligada ao campo, e a original fica de fora, com a proposta guardada. As
  linhas que a regra não dividiu por inteiro (até 50 por coluna) vão para a IA pequena (prompt `divisor_de_linhas_v1`),
  e só vale o pedaço que está na célula ("a IA aponta, o código copia").
- **Tela:** a coluna chega "Dividida pela IA", com a prévia (a célula e as partes das primeiras linhas); cada parte vem
  logo abaixo, recuada, com o campo (dá para trocar ali). O botão **"Refazer a divisão desta coluna"** só liga com o
  comentário escrito; a IA relê só essa coluna, com o comentário e a divisão anterior (como dado), no máximo 2 vezes
  (`cadastro.refazer_divisao`, rota `/refazer_divisao`). O comentário passa pelo guardrail de injeção.
- **A divisão à mão continua** e agora passa pelo mesmo serviço (sem código duplicado).

**Trade-off.** A regra cobre endereço, cidade/UF e separador simples; um formato fora disso depende das linhas
difíceis irem à IA (até 50 por coluna) ou vira pendência. Cada refazer é uma chamada à IA grande.

**Como comprovar.** `tests/test_divisao.py` (a coluna já chega dividida, com a prévia; o comentário refaz só a coluna,
até o limite; o aceite leva as partes aos campos; a divisão à mão; o separador; a proposta fora do layout; o pedaço
que não está na célula é descartado) e o roteiro de clique `divisao_do_endereco` (prévia, botão só com comentário,
refazer e aceite). **Pendente (🧪):** medir com a IA real se ela propõe DIVIDIR nas colunas certas (e não nas outras)
e o acerto da divisão, junto com a nova medição do Interpretador pelo Bedrock.

<a id="adr-105"></a>

### ADR-105 · Sem o modelo de linguagem no detector; o rótulo vem da IA; um conferidor de outra IA, desligado até medir 🧪

**Contexto (2026-09-27, perguntas do usuário).** "Precisamos do detector de dados? Não podemos deixar tudo com a
IA?" Desde o ADR-101 o detector não esconde nada da IA; sobraram três usos (o aviso de parágrafo esquecido, o rótulo
que a tela mostra e o simulador do modo MOCK). A medição (sem IA real) mostrou:
- **custo** do modelo de linguagem (spaCy `pt_core_news_md` e wordfreq): cerca de 262 MB na imagem, 267 MB de memória
  a mais (a API ia de 211 MB para 478 MB) e 1,5 s na primeira leitura de texto corrido;
- **aviso de parágrafo esquecido**: igual com e sem o modelo em 816 de 816 parágrafos;
- **rótulo**: sem o modelo, só com as regras, 0 nomes de pessoa em 1.549 rótulos (com o modelo, 1); mas a regra
  falha em texto solto ("técnico de manutenção. Nasceu em"), e os documentos de teste são sintéticos (a medida é
  otimista);
- **MOCK**: 29,0% × 29,8% dos campos, 10 vezes mais rápido sem o modelo.
E a pergunta seguinte: "então não faz mais sentido um agente novo que confere?"

**Opções e decisão, uso por uso.**

| Uso | Opções | Decisão | Por quê |
|---|---|---|---|
| Aviso de parágrafo esquecido | modelo · regra · IA | **Regra** (padrões de CPF, data, R$, CEP, telefone, e-mail) | É a conferência INDEPENDENTE do trabalho da IA; se a própria IA conferisse, o mesmo erro que a fez esquecer alguém a faria não ver. Custo zero e 816/816 |
| Rótulo do dado | regra · IA | **IA** (o Leitor devolve o "rotulo"; prompt `leitor_de_documentos_v5`), **conferido pela regra** (`conferir_rotulo`: só vale o que está no documento, sem número nem e-mail) | Em texto solto a regra é frágil; a IA já lê o trecho, e devolver o rótulo custa cerca de 9% a mais por documento |
| Simulador MOCK | modelo · regra | **Regra** | O MOCK existe para testar sem IA e sem custo |
| Erros de entendimento (CPF da pessoa errada, datas trocadas, bônus como salário) | nenhuma conferência · regra · agente conferidor | **Agente Conferidor da Leitura** (modelo pequeno, de OUTRO fornecedor que o do Leitor), **desligado** (`CONFERIDOR_DA_LEITURA=nao`) até o EXP-015 | Nenhuma regra pega esses erros; mas o conferidor dobra as chamadas de IA e pode gerar alarme falso: liga só se a medição mostrar que vale |

**O que mudou no código.** Saíram o spaCy, o modelo e o wordfreq (`requirements.txt` e o ambiente; a lista de
palavras de ligação foi copiada para `data/vocabulario/palavras_de_ligacao.txt`); o detector ficou só com regras
(toda palavra com maiúscula fora das listas vira `[TEXTO_n]`). O Leitor usa o prompt v5 e confere o rótulo da IA; a
regra antiga do rótulo virou a do simulador. Novos: `agents/conferidor_da_leitura.py`, o prompt
`conferidor_da_leitura_v1` e `scripts/avaliar_conferidor.py` (EXP-015: planta datas trocadas, CPF e salário de outra
pessoa, sempre com valores que estão no documento, e mede acerto, alarme falso, custo e tempo).

**Trade-off.** O rótulo pela IA custa cerca de 9% a mais por documento e depende de a IA seguir a regra 3 (sem dado
no rótulo; o código barra número e e-mail, não um nome). O conferidor, se ligado, dobra as chamadas por documento.

**Como comprovar.** `tests/test_leitura_de_word.py` (o rótulo da IA só vale se está no documento e não tem dado; o
rótulo do simulador para antes de qualquer dado; a marcação por regra), `tests/test_conferidor_da_leitura.py` (a
suspeita só vale sobre pessoa e campo que existem; desligado, não chama; ligado, cada suspeita vira pergunta presa à
pessoa e ao campo; o EXP-015 planta valores do documento) e a bateria inteira sem o spaCy instalado (821 testes).
**Pendente (🧪, com a chave do Bedrock e o ok do gasto):** refazer o EXP-010 com o Leitor v5 e rodar o EXP-015
(estimativa: US$ 4 a 6 no total).

**Atualização (2026-09-27, EXP-015, prova pequena, US$ 0,01):** com o plano B (o pequeno é o Nova 2 Lite, de outro
fornecedor que o Sonnet 4.6 do Leitor), o conferidor achou **18 de 18** erros plantados nos 5 documentos do conjunto de
desenvolvimento, com **4 alarmes falsos** (todos no N5) em 22 suspeitas. **Ligado** (`CONFERIDOR_DA_LEITURA=sim` no
`.env`): um erro desses que passa leva o salário ou o CPF de uma pessoa para outra; um alarme falso custa uma pergunta
de confirmação. A medição completa (conjunto de prova) entra nos experimentos finais, depois da aprovação da ferramenta.


<a id="adr-106"></a>

### ADR-106 · Plano B da IA no Bedrock, se o Sonnet 5 e o GPT-6 Luna não forem liberados ⏳

**Contexto (2026-09-27, pedido do usuário).** "Quero começar a pesar a possibilidade de usar outros modelos
disponíveis na AWS caso a liberação dos outros dois não funcione." O Sonnet 5 e o GPT-6 Luna continuam com
`403 not available for this account` (o aceite dos termos no Marketplace falhou com o cartão recusado; ADR-96).

**O que a conta libera.** Consulta ao catálogo (sem custo) e uma pergunta de até 10 tokens a 27 modelos de texto:
- **bloqueados (403):** Claude Sonnet 5, Opus 5 e 5.5, GPT-6 Sol e Luna, Grok 4.6 (os mais novos);
- **liberados:** Claude Sonnet 4.6 e Haiku 4.5; Amazon Nova (Pro, 2 Lite, Lite, Micro), que é da própria AWS e não
  passa pelo Marketplace; e os de pesos abertos (Mistral Large 3, DeepSeek V3.2, Qwen3, Kimi, GLM-5, gpt-oss e outros).

**Medição (EXP-012).** Os 4 candidatos principais nas mesmas 30 planilhas do EXP-008 (B3, com RAG, código da
comparação congelado), medidos ao mesmo tempo, um por trilha:

| Modelo | Acurácia por campo (IC 95%) | Fora do formato | Custo por planilha | Tempo por planilha |
|---|---|---|---|---|
| Referência: Sonnet 5 (APIs diretas, EXP-008) | 84,4% (81,1 a 87,5) | 0 | US$ 0,056 | 33,5 s |
| **Claude Sonnet 4.6** | **82,1% (78,8 a 85,2)** | 1 | US$ 0,059 | 19,7 s |
| Claude Haiku 4.5 | 65,8% (52,5 a 77,6) | 13 | US$ 0,023 | 15,2 s |
| Amazon Nova 2 Lite | 31,0% (17,1 a 45,7) | 37 | US$ 0,012 | 14,0 s |
| Amazon Nova Pro | 6,6% (1,0 a 14,5) | 52 | US$ 0,018 | 13,6 s |

Leitura: o **Sonnet 4.6 empata com o Sonnet 5** (os intervalos se sobrepõem), com o mesmo custo e mais rápido. O
Nova e o Haiku perdem por **formato**, não necessariamente por entendimento: o Nova devolve a lista de colunas solta,
`[...]`, em vez de `{"itens": [...]}`, e o Interpretador rejeita (o dicionário assume em 26 das 30 planilhas no Nova
Pro). O Haiku 4.5, que fez 81,6% pelas APIs diretas com 0 respostas fora do formato, errou o formato 13 vezes pelo
Bedrock (causa não investigada). Além disso, o Haiku 4.5 tem aposentadoria anunciada a partir de 15/10/2026.

**Opções.**

| Opção | Ganho | Custo |
|---|---|---|
| A · esperar a liberação do Sonnet 5 e do Luna | Os modelos já escolhidos (ADR-11) | Depende do suporte da AWS; sem data |
| **B · Sonnet 4.6 como modelo grande enquanto não libera** | Mesmo acerto medido, mesmo custo, funciona hoje | Geração anterior; o pequeno fica em aberto |
| C · Nova (sem Marketplace, o mais garantido) | Não depende de aceite de termos | Hoje não segue o formato; precisaria de "ferramenta forçada" e nova medição |

**Atualizado no mesmo dia pelo ADR-107:** com o formato garantido, o Nova 2 Lite, o Qwen3 235B e o Haiku 4.5 chegam perto do Sonnet 4.6 por uma fração do custo; o papel do pequeno vai ser escolhido nas 30 planilhas (feito no EXP-014: ver o ADR-107).

**Recomendação.** B, com o **Sonnet 4.6 também no papel do pequeno** até haver um pequeno que siga o formato (o custo
por planilha é de centavos). Próximo passo, se o usuário aprovar o gasto (≈ US$ 1 a 2): o **formato garantido** pelo
Converse (`outputConfig.textFormat`, suportado no Sonnet 4.6 e no Haiku 4.5, pela documentação da AWS) e a
"ferramenta forçada" no Nova (o Nova não tem formato garantido), e medir de novo o Haiku e o Nova 2 Lite.

**O que mudou no código.** `services/provedores_de_ia.py` ganhou a terceira forma de chamada, a **API geral do
Bedrock (Converse)**, para os modelos que o endereço compatível com o fornecedor não atende (medido: o Sonnet 4.6 dá
"não existe" no endereço da Anthropic; o Nova é da Amazon): nomes do Bedrock (`NOME_NO_BEDROCK`), limite de saída do
Nova Pro (10.000 tokens), nova tentativa com espera quando o Bedrock pede (429/503) e refazer sem temperatura se o
modelo recusar. Preços do Nova em `data/avaliacao/precos_so_no_bedrock.json` (API de preços da AWS, 2026-09-27), à
parte da triagem de 24/09. `scripts/medir_pelo_bedrock.py` mede vários modelos ao mesmo tempo (`--modelos`, teto por
modelo, `--juntar`, `--saida`) e mostra cada um no painel de acompanhamento (`scripts/painel_de_status.py`, fora do
Git a saída em `storage/painel/`).

**Pendente fora do código.** A retenção zero da conta continua em `inherit`: a chave não tem permissão para gravar
(`403`); gravar no console da AWS (administrador) ou dar a permissão à chave. Os testes de 27/09 usaram só dados
fictícios.

**Como comprovar.** `tests/test_provedores_de_ia.py` (Converse: endereço, chave, texto sem o raciocínio, limite do
Nova, espera e nova tentativa, sem temperatura, erros que não se escondem, Nova recusado na rota direta, preço do
Nova) e o EXP-012 (`data/avaliacao/resultados/comparacao_plano_b_bedrock.json`).


<a id="adr-107"></a>

### ADR-107 · Formato garantido no Interpretador pelo Bedrock; plano B Sonnet 4.6 + Nova 2 Lite ✅

> **Estendido pelo [ADR-150](#adr-150) (2026-09-30):** o Agente de Endomarketing também pede o formato garantido, com
> o esquema do material.

**Contexto (2026-09-27, pergunta do usuário).** "E não tem outros modelos, até da própria AWS, que poderiam ter uma
performance melhor?" No EXP-012 (ADR-106), o Nova e o Haiku 4.5 perderam por **formato**, não por entendimento: o
Nova devolvia a lista solta `[...]` no lugar de `{"itens": [...]}`, e o contrato recusava. O Interpretador nunca
tinha pedido o formato garantido ao provedor (só pedia o JSON no texto do prompt).

**O que cada modelo aceita (sondagem de 27/09, pedidos mínimos).**

| Jeito de garantir | Como vai no pedido (API Converse) | Modelos |
|---|---|---|
| Esquema | `outputConfig.textFormat` com o esquema JSON | Sonnet 4.6, Haiku 4.5, Mistral Large 3, DeepSeek V3.2, Qwen3 VL 235B, Kimi K3 |
| Ferramenta forçada | `toolConfig` com uma ferramenta obrigatória (`toolChoice`); o preenchimento é a resposta | Nova Pro e Nova 2 Lite (recusam o esquema: "doesn't support the outputConfig field") |

**Opções.**

| Opção | Ganho | Custo |
|---|---|---|
| A · só o JSON pedido no texto (como antes) | Nada muda | O Nova e o Haiku pelo Bedrock perdem por embalagem |
| B · consertar a leitura (aceitar a lista solta) | Simples | Remenda um formato; cada modelo pode errar de outro jeito |
| **C · formato garantido pelo provedor** (esquema ou ferramenta forçada, conforme o modelo) | O modelo é obrigado a seguir o esquema; o contrato e o guardrail continuam conferindo o conteúdo | Um esquema a manter junto do contrato; opção nova no `.env` |

**Decisão.** C, atrás de uma opção: `INTERPRETADOR_FORMATO_GARANTIDO` (padrão `nao`: o Interpretador fica como foi
medido no EXP-008). O esquema (`esquema_da_resposta`) é o mesmo formato que o prompt v3 já pedia, com as regras do
Bedrock (todo objeto fecha a porta a campos extras e exige todos os seus campos). O parâmetro do esquema só vai
quando a opção está ligada, porque o medidor congelado da comparação de modelos não o conhece; o script de medição
usa um adaptador que mede do mesmo jeito e repassa o esquema.

**Medição (EXP-013, triagem: 10 primeiras planilhas da amostra do EXP-008, 7 modelos ao mesmo tempo, US$ 1,12).**

| Modelo | Sem formato garantido (EXP-012, 30 planilhas) | Com formato garantido (10 planilhas) | Custo por planilha | Tempo |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 82,1% | 81,2% | US$ 0,052 | 16 s |
| Qwen3 VL 235B | — | 81,2% | US$ 0,009 | 38 s |
| Claude Haiku 4.5 | 65,8% | 81,2% | US$ 0,017 | 10 s |
| Amazon Nova 2 Lite | 31,0% | 78,8% | US$ 0,008 | 10 s |
| Amazon Nova Pro | 6,6% | 77,6% | US$ 0,012 | 16 s |
| Mistral Large 3 | — | 77,0% | US$ 0,006 | 9 s |
| DeepSeek V3.2 | — | 69,1% | US$ 0,008 | 38 s |
| Dicionário sem IA (B0) | 53,4% | 52,7% | US$ 0 | — |

Leitura: respostas fora do contrato caíram a 0 (1 no Nova Pro). Os seis primeiros cabem na margem de erro de uma
triagem de 10 planilhas; o que os separa é custo, tempo e o quanto pedem ajuda quando devem (Mistral: 87%). O Kimi K3
ficou de fora: US$ 0,21 por planilha na prova rápida, 4 vezes o Sonnet 4.6.

**Trade-off.** Um esquema a manter em sincronia com o contrato (`RespostaInterpretador`) e com o prompt; a medida é
de uma triagem (10 planilhas), não da amostra inteira.

**Medição completa (EXP-014, as 30 planilhas do EXP-008, 7 modelos em paralelo, US$ 3,30).**

| Modelo | Acurácia por campo (IC 95%) | Pede ajuda quando deve | Custo por planilha | Tempo |
|---|---|---|---|---|
| Referência: Sonnet 5 (EXP-008) | 84,4% (81,1 a 87,5) | 98,8% | US$ 0,056 | 33,5 s |
| Claude Haiku 4.5 | 84,4% (80,8 a 87,9) | 92,9% | US$ 0,017 | 9,9 s |
| Qwen3 VL 235B | 84,0% (80,5 a 87,1), 28 de 30 | 100% | US$ 0,008 | 37,8 s |
| **Claude Sonnet 4.6** | **82,9% (79,7 a 86,0)** | **100%** | US$ 0,050 | 15,8 s |
| Mistral Large 3 | 81,8% (78,2 a 85,5) | 96,4% | US$ 0,006 | 9,8 s |
| **Amazon Nova 2 Lite** | **81,6% (78,7 a 84,7)** | **98,8%** | **US$ 0,008** | **9,2 s** |
| Amazon Nova Pro | 78,2% (66,7 a 87,0), 28 de 30 | 96,2% | US$ 0,015 | 24,8 s |
| DeepSeek V3.2 | 76,3% (71,9 a 80,4) | 100% | US$ 0,007 | 37,8 s |
| Referência: GPT-6 Luna (EXP-008) | 76,3% (72,7 a 80,4) | 100% | US$ 0,002 | 29,7 s |

Leitura: com o formato garantido, cinco modelos liberados na conta ficam entre 81,6% e 84,4%, todos acima do Luna.
O Nova Pro ainda errou o formato 13 vezes com a ferramenta forçada e teve 2 erros 424 do Bedrock; o Qwen3 teve 2
erros 500 e é lento (38 s por planilha).

**Decisão (aprovada pela usuária em 2026-09-27).** Plano B com o formato garantido ligado:
- **grande: Claude Sonnet 4.6.** Acerto do Sonnet 5 dentro da margem e pede ajuda em 100% das colunas em que devia (o
  ADR-07 prefere perguntar a chutar). O Haiku 4.5 acerta igual e custa um terço, mas tem aposentadoria anunciada a
  partir de 15/10/2026 e pede ajuda menos vezes (92,9%);
- **pequeno: Amazon Nova 2 Lite.** 5 pontos acima do Luna, o mais rápido, menos de 1 centavo de dólar por planilha e
  da própria AWS: não depende do aceite no Marketplace, que é o que trava a conta hoje.
Ligado no mesmo dia: `ROTA_DA_IA=bedrock`, `MODELO_GRANDE=claude-sonnet-4-6`, `MODELO_PEQUENO=nova-2-lite` e
`INTERPRETADOR_FORMATO_GARANTIDO=sim` (`.env` e `.env.example`). Vale enquanto a conta não liberar o Sonnet 5 e o Luna
(ADR-11); quando liberar, a volta é medida de novo com o formato garantido. **Pendente:** a retenção zero da conta
(console da AWS; a chave não tem permissão). Os modelos do plano B não estão entre os que guardam pedidos.

**Usos do modelo pequeno conferidos antes de ligar.** Divisão do texto em blocos (Leitor) e linhas difíceis da
divisão de coluna: se a resposta vier fora do formato, a regra assume (nada quebra). Classificador do guardrail de
injeção: 5 de 5 certos com o Nova 2 Lite (3 ataques, 2 textos normais); como o Nova às vezes enfeita com markdown, o
veredito passou a ser lido sem os símbolos (`veredito_e_suspeito`: `**SUSPEITO**` não vira NORMAL). O esquema do
Leitor (45 campos) foi aceito pelo Sonnet 4.6 no Converse. A medição desses usos entra no EXP-010 refeito.

**Como comprovar.** `tests/test_interpretador.py` (desligado, a chamada é a de antes; ligado, o esquema vai; todo
objeto do esquema fecha a porta e exige os campos; os status são os do contrato), `tests/test_provedores_de_ia.py`
(esquema em `outputConfig`; ferramenta forçada no Nova, e o preenchimento vira o texto; sem esquema, nada muda;
nomes completos dos abertos; Haiku pelo Converse; abertos recusados na rota direta), o EXP-013
(`data/avaliacao/resultados/triagem_formato_garantido_bedrock.json`) e o EXP-014
(`data/avaliacao/resultados/formato_garantido_30_bedrock.json`).


<a id="adr-108"></a>

### ADR-108 · O contêiner sobe a API, não mais o Streamlit, que saiu do código; pronto para a AWS atrás de https 🧪

**Contexto (2026-09-27).** A publicação na AWS é prioridade (desvio de 27/09), e o front novo (HTML + API FastAPI)
substituiu as telas do Streamlit. O `Dockerfile` e o `docker-compose.yml` ainda subiam o Streamlit na porta 8501.

**Decisão.** O contêiner sobe a API (`uvicorn api.principal:aplicacao`, porta 8000), que atende as telas e as rotas
`/api`, depois do `scripts/preparar_servidor.py` (como antes). O uvicorn roda com `--proxy-headers` e
`--forwarded-allow-ips='*'`: na AWS, o https termina no balanceador de carga e a aplicação recebe http; confiando no
`X-Forwarded-Proto`, ela marca o cookie de login como seguro (só https). O Compose passa também as opções do plano B e
do conferidor (`INTERPRETADOR_FORMATO_GARANTIDO`, `CONFERIDOR_DA_LEITURA`, `LEITOR_ESFORCO`), e a rota padrão é o
Bedrock.

**Feito em seguida (2026-09-27).** A redefinição de senha foi portada (ADR-109) e o código do Streamlit saiu:
`app.py`, `components/`, `telas/`, o spike com tela (`spikes/spike_pausa_retomada.py`; a prova do spike continua em
`tests/test_spike_pausa_retomada.py`), `.streamlit/`, a linha dele no `.gitignore` e o `streamlit` do
`requirements.txt` (no lugar, o `uvicorn`, que o contêiner usa e antes só vinha como dependência do ChromaDB). Saiu
também o que só servia às telas antigas: o mapa de telas (`PERFIS_POR_TELA`, `pode_acessar`, `telas_do_perfil`, em
`services/permissoes.py`) e `acesso.salvar_layout` (o front grava o layout pela rota `/api/banco/parametros/layout`).
Cada verificação feita pelas telas do Streamlit ganhou (ou já tinha) equivalente fora delas:

| Regra verificada pelas telas antigas | Onde fica agora |
|---|---|
| Cada perfil só abre as suas páginas; página desconhecida é negada; sem login nada abre | `test_api_front.py`: toda página tem um único perfil dono; cada página × EMPRESA, BANCO e sem login; `pagina_permitida` com página inventada |
| Login cria a sessão e abre a página do perfil | `test_api_front.py` (login, cookie, página inicial de cada perfil) |
| O portal mostra só a empresa do usuário; o envio de outra empresa não aparece | `test_acompanhamento.py`, `test_cadastro.py`, `test_cadastro_conferencia.py`, `test_assistente_na_tela.py` (404 para outra empresa) |
| Interpretar, aceitar, padronizar, validar, corrigir com clique, enviar ao banco, homologar só com a aprovação do banco | `test_cadastro.py`, `test_assistente_na_tela.py`, `test_acompanhamento.py`, `test_avaliacao_do_banco.py`, `test_fluxo_empresa.py` |
| O chat recusa mensagem com ordem para a IA | `test_assistente_na_tela.py`, `test_adversarial.py` (3) |
| Sem taxa informada, nada de ganho; a simulação guarda quem simulou e a versão das premissas | `test_portal_do_banco.py` (serviço e API) |
| O Consultor responde com as fontes e recusa SQL | `test_portal_do_banco.py` (API), `test_consultor.py`, `test_adversarial.py` (7) |
| Endomarketing: rascunho com fonte, só a própria empresa aprova (desde o ADR-115: o banco gera e publica; a empresa vê só os publicados dela) | `test_portal_da_empresa.py`, `test_endomarketing.py` |
| Pessoa cadastrada aparece na lista na hora | `test_empresas.py` (convite aparece na ficha da empresa) |
| As três trilhas da demo, de ponta a ponta | `test_ponta_a_ponta.py`, agora pela API (TestClient) |
| Sem login, nada abre (ataque 8) | `test_adversarial.py` (página, rota da API e serviço) |
| Nenhuma tela chama operação sensível sem a porta `services/acesso.py` | `test_seguranca.py`, agora sobre a API e os serviços dos portais |

Saiu sem substituto só o que era do próprio Streamlit: o mapa "toda tela tem arquivo e permissão" (o equivalente no
front é "toda página tem um perfil dono") e o bug de a lista de usuários só atualizar depois de sair e entrar (era do
cache do Streamlit). **O que o front ainda não tem** e só existia nas telas antigas: editar as premissas financeiras
(a porta `acesso.salvar_premissas` e o serviço continuam, testados), a tabela "De onde vêm os números" do Cockpit
(`planejamento.por_arquivo`, ADR-51, continua testado), importar o layout de uma planilha, cadastrar usuário do banco
pela tela (hoje por `scripts/criar_usuarios.py`) e a página Sobre.

**Trade-off.** Até o Streamlit sair, a imagem carregava uma biblioteca que não usava (tamanho maior); isso acabou.

**Como comprovar.** `docker compose config --quiet` válido. Sem o Streamlit, a bateria inteira passa em modo MOCK
(869 testes, 18 falhas esperadas marcadas), com os testes de página × perfil em `tests/test_api_front.py` e as trilhas
em `tests/test_ponta_a_ponta.py`. **Pendente (🧪):** construir e subir a imagem (o Docker
Desktop estava desligado; C: com 16 GB livres) e abrir `http://localhost:8000/login.html` pelo contêiner.


<a id="adr-109"></a>

### ADR-109 · Senha provisória obrigatória de trocar; o banco gera nova senha no front novo ✅

> **Estendido pelo [ADR-154](#adr-154) (2026-09-30):** a senha provisória vence em 48 horas, contadas de quando o banco
> a gerou. Vencida, o login recusa com o aviso, e o especialista gera uma nova.

**Contexto (2026-09-27).** Para tirar o Streamlit (ADR-108), faltava portar uma função que só existia lá: o banco
redefinir a senha de quem esqueceu. A usuária perguntou se isso era do "momento zero" (primeiro acesso). São dois
momentos: o **convite** (primeiro acesso, já no front novo) e a **redefinição** (esqueceu a senha, depois). Olhando o
código, apareceu uma falha: o convite dizia que a pessoa "troca a senha no primeiro acesso", mas **nada obrigava** a
troca, e a senha provisória (vista pelo especialista do banco) podia valer para sempre.

**Opções.**

| Opção | Ganho | Custo |
|---|---|---|
| A · o banco digita a senha nova da pessoa (como no Streamlit) | Simples | O banco conhece a senha para sempre; nada obriga a trocar |
| **B · o banco gera uma senha provisória, que aparece uma vez, e a troca é obrigatória no próximo acesso** | Só a pessoa conhece a senha definitiva; convite e redefinição funcionam igual | Uma coluna nova e um passo a mais no primeiro login |
| C · "esqueci minha senha" por e-mail | O banco nem vê a senha | A aplicação não manda e-mail nesta versão |

**Decisão.** B.
- `usuarios.senha_provisoria` (0 ou 1; bancos antigos ganham a coluna com 0). O convite e o botão novo **"Nova senha
  provisória"** (tela Empresas → Usuários, com confirmação no próprio botão) gravam 1; a troca pela própria pessoa grava 0
  e não aceita a mesma senha.
- A redefinição derruba na hora as sessões abertas da pessoa (como já fazia a desativação).
- Com a marca ligada, a API só entrega o cabeçalho, "quem sou eu", a troca de senha e o "Sair": todas as rotas da
  empresa e do banco respondem 403 (`exigir_senha_definitiva`). No front, o cabeçalho abre "Minha senha" em **modo
  obrigatório** (sem "Cancelar", sem fechar com Esc) e recarrega a página depois da troca.
- A rota nova `POST /api/banco/empresas/usuarios/{login}/nova-senha` é só do BANCO e só para pessoas de empresa.

**Trade-off.** A senha provisória aparece na tela do especialista (a aplicação não manda e-mail); o risco fica limitado
porque ela só serve para a própria troca. Em produção, SSO corporativo ou "esqueci a senha" por e-mail.

**Como comprovar.** `tests/test_api_front.py`: com a senha provisória, os dados da empresa dão 403 e o cabeçalho pede a
troca; trocar pela mesma senha é recusado; depois da troca, a mesma sessão é liberada. O banco gera a nova senha: a sessão
aberta cai, a senha antiga para de valer e a nova entra como provisória. A empresa não gera senha (403), e o banco não usa
a rota para outro usuário do banco (400).


<a id="adr-110"></a>

### ADR-110 · Lacunas de segurança fechadas: limite de tentativas de login, cabeçalhos do navegador, limite do pedido na entrada e contêiner sem administrador 🧪

**Contexto (2026-09-27).** O capítulo de Segurança (`seguranca.md`, seção 8) listou quatro lacunas que dependiam só de
código e precisavam fechar antes da publicação na AWS: (2) nada impedia tentar muitas senhas seguidas; (4) as
respostas não traziam os cabeçalhos que mandam o navegador se proteger; (5) a API recebia o arquivo inteiro antes de
conferir os 5 MB; (8, em parte) o contêiner rodava como administrador (`root`).

**Opções e decisão, lacuna por lacuna.**

*1. Limite de tentativas de login.*

| Opção | Ganho | Custo |
|---|---|---|
| A · contador na memória do servidor | Simples, sem tabela | Some a cada reinício e não vale com mais de uma cópia do servidor |
| **B · tabela `tentativas_de_login` no banco** | Sobrevive ao reinício, vale para várias cópias, funciona no SQLite e no PostgreSQL pela mesma porta | Uma tabela a mais (com limpeza das linhas vencidas) |
| C · limite por endereço de rede (IP) | Barra quem tenta muitos logins de um lugar só | Atrás do balanceador da AWS, o IP real vem num cabeçalho que só é confiável lá; na máquina local, todos são 127.0.0.1 |

Decisão: **B**. 5 senhas erradas seguidas para o mesmo login, dentro de 15 minutos, bloqueiam esse login por 15
minutos; login certo zera. Durante o bloqueio, a senha **nem é conferida** (senão quem tenta saberia quando acertou).
**Qual mensagem:** um aviso claro (**429**, "Muitas tentativas seguidas com este usuário. Por segurança, o acesso ficou
bloqueado. Tente de novo em N minutos.", com o cabeçalho `Retry-After`), e não a mensagem de sempre ("Usuário ou senha
incorretos."). Com a de sempre, a pessoa que lembrou a senha certa leria "incorretos" e acharia que a senha mudou. O
aviso **não revela se o usuário existe** (ADR-69), porque a contagem é pelo login **digitado**: um login inventado é
bloqueado do mesmo jeito, com a mesma resposta. O login digitado passou a ter até 200 caracteres (vai para a tabela).

*2. Cabeçalhos de proteção do navegador.* Um middleware (`proteger_o_navegador`) põe em toda resposta:
`Content-Security-Policy`, `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: same-origin` e, **só quando a conexão é https**, `Strict-Transport-Security: max-age=31536000`. A
política de conteúdo foi conferida contra o front (todos os scripts e estilos são arquivos do próprio site; de fora, só
o Google Fonts):

```
default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com;
style-src-attr 'unsafe-inline'; font-src https://fonts.gstatic.com; object-src 'none'; base-uri 'self';
form-action 'self'; frame-ancestors 'self'
```

Três escolhas: (a) **script só de arquivo do site**: o único script escrito dentro de uma página (`cadastrar.html`)
virou `front/js/em_janela.js`; (b) **quadro só do próprio site** (`SAMEORIGIN`/`'self'`) em vez de "ninguém"
(`DENY`/`'none'`), porque a janela "Cadastrar funcionários" mostra o `cadastrar.html` num quadro; (c) o **atributo
`style="..."` liberado** (`style-src-attr 'unsafe-inline'`), porque as páginas o usam em barras e anéis de porcentagem
e estilo não roda código; o bloco `<style>` continua proibido. HSTS sem `includeSubDomains`: o domínio ainda está sendo
reservado e pode ter outros subdomínios. Com o `nosniff`, a API fixa o tipo do `.js` e do `.css` (no Windows, o
registro do sistema às vezes diz que `.js` é texto).

*3. Limite do pedido na entrada.*

| Opção | Ganho | Custo |
|---|---|---|
| A · ler o arquivo em pedaços dentro da rota | Simples | O FastAPI já recebeu e guardou o formulário inteiro antes de a rota rodar |
| **B · middleware que confere o `Content-Length` antes de receber, mais leitura só até o limite na rota** | O pedido grande é recusado sem ser guardado; a rota nunca lê mais que o limite + 1 byte | Pedido "em pedaços" (sem `Content-Length`) precisa ser recusado |
| C · só no servidor de entrada (balanceador, WAF) | Barra antes da aplicação | Não existe na máquina local nem nos testes; fica como segunda barreira na publicação |

Decisão: **B**. Acima de 5 MB + 64 KB (a folga do "envelope" do formulário), **413** com a mesma frase de sempre
("Arquivo maior que o limite de 5 MB."); pedido sem tamanho declarado, **411**; arquivo que passa do limite por menos
que a folga, **400** com a mesma frase, lido só até o limite + 1 byte (rota de envio da empresa e arquivo de contas do
banco). Conferido com o uvicorn de verdade: 8 MB e 100 MB recebem o 413 com a mensagem (httpx e requests), sem
conexão quebrada.

*4. Contêiner sem administrador.* O `Dockerfile` cria o usuário `integra` (com pasta pessoal, para o cache das
bibliotecas) e termina com `USER integra`. Ele é dono **só** de `/app/storage` (o volume do Compose) e de
`/app/data/synthetic` (os dados que o `scripts/preparar_servidor.py` gera na subida); o código continua do
administrador, só para leitura. A porta 8000 não exige administrador.

**Trade-off.** O bloqueio por login permite que alguém bloqueie **de propósito** o login de outra pessoa por 15
minutos (aceito: é curto, e a alternativa, não bloquear, deixa a força bruta livre); o limite não é por endereço de
rede (tentar uma senha em muitos logins não é barrado; fica para a publicação, com o IP confiável do balanceador, ou
para o SSO em produção). A tela antiga do Streamlit não ganhou o limite (sai com o Streamlit, ADR-108). O
`style="..."` segue liberado na CSP. Um volume `arquivos_da_aplicacao` criado antes desta mudança pertence ao
administrador e precisa ter o dono corrigido uma vez (passo no README).

**Como comprovar.** `tests/test_tentativas_de_login.py` (5º erro bloqueia por 15 minutos; minutos arredondados para
cima; erros espalhados não somam; acerto zera; erro durante o bloqueio não o apaga; limpeza das linhas vencidas),
`tests/test_protecoes_do_site.py` (pela API: nem a senha certa entra no bloqueio; login inexistente recebe a mesma
resposta; fim do bloqueio; cabeçalhos em toda resposta; HSTS só em https; CSP sem script inline; as páginas do front
cabem na CSP; 413, 400 e 411 no tamanho do pedido), `tests/test_dockerfile.py` (linha `USER` antes da subida, dono só
das pastas de escrita) e o roteiro de clique `protecao_do_navegador` (as 13 páginas dos dois portais e a janela do
envio no Chrome, sem nenhum bloqueio da CSP; com o script antigo de volta dentro da página, o roteiro reprova). Os
18 roteiros de clique passam com a política ligada (as expressões soltas do Playwright, que ele roda com `eval`,
viraram funções; a CSP não foi afrouxada para os testes). O
serviço de tentativas também rodou num esquema temporário do PostgreSQL de testes. **Pendente (🧪):** construir e subir
a imagem com o usuário novo (o Docker Desktop estava desligado).


<a id="adr-111"></a>

### ADR-111 · Consulta de funcionários com todos os campos do parâmetro, obrigatórios marcados ✅

**Contexto (2026-09-27, pedido da usuária).** "No grid consulta funcionário, todos os campos do arquivo de parâmetros
que queremos receber precisam aparecer. E ali precisa ficar claro quais eram as colunas obrigatórias (com uma marcação
na coluna) e, na linha, quando a IA identificou o valor, aparecer de fato o valor identificado, e quando não,
informação não encontrada." A grade tinha 9 colunas fixas, e a API escondia 21 campos por uma regra de minimização
(nome da mãe, PIS, documento, naturalidade, escolaridade e o endereço residencial completo).

**Opções.**

| Opção | Ganho | Custo |
|---|---|---|
| A · manter a grade curta e mostrar tudo só na ficha | Tabela sem rolar para o lado | Não mostra, de relance, o que a IA identificou em cada campo |
| **B · uma coluna por campo do parâmetro vigente, com a marca de obrigatório e a frase fixa no vazio** | A empresa confere, campo a campo, o que foi identificado e o que falta; um campo novo do banco aparece sozinho | A tabela rola para o lado (45 campos) |

**Decisão.** B. A lista fixa `CAMPOS_PARA_A_EMPRESA` saiu: a consulta usa **todos os campos do parâmetro vigente**
(`campos_para_a_empresa`), na ordem do layout. A rota nova `GET /api/empresa/colunas_da_consulta` devolve cada
coluna com o rótulo legível (`rotulo_do_campo`: "data_admissao" → "Data admissão"), o grupo, o tipo, a descrição e
se é obrigatória. A grade monta o cabeçalho em dois níveis (o grupo em cima, o campo embaixo), com **"*" na cor da
marca** nas obrigatórias (o leitor de tela diz "obrigatório") e a descrição do banco ao passar o mouse; cada célula
mostra o valor formatado pelo tipo (data, dinheiro, CNPJ, telefone, CEP) ou **"Informação não encontrada"** em cinza e
itálico. Conta, Incluído e Situação continuam no fim. Uma legenda acima da grade explica a marca e a frase.

**Mudança consciente.** A minimização da consulta (Passo 2 do ADR de acompanhamento) deixa de valer para a própria
empresa: são dados que ela mesma enviou, e ver o que a IA identificou é o objetivo da tela. Continuam o isolamento entre
empresas, o registro de cada abertura da lista e o `no-store` na resposta.

**Complemento no mesmo dia (a usuária não via o ajuste; "e também na tela do especialista do banco").**
- **A tela do especialista** (Envios → pessoas do envio) ganhou a mesma grade: `pessoas_do_envio` traz "campos" com
  todos os campos do parâmetro, a rota `GET /api/banco/colunas_da_consulta` dá as colunas, e as duas telas usam o mesmo
  código de montagem (`front/js/grade_do_parametro.js`); no banco, depois dos campos vêm Situação e Ação.
- **Por que o ajuste não aparecia:** os `.js` e `.css` iam sem instrução de cache, e o navegador usava a cópia antiga
  do `acompanhar.js`. Agora saem com `Cache-Control: no-cache` (o navegador pergunta "mudou?" a cada abertura; sem
  mudança, o servidor só responde "não mudou").

**Como comprovar.** `tests/test_acompanhamento.py` (as colunas são os campos do parâmetro, na ordem, com a mesma marca
de obrigatório; o rótulo legível; a lista traz todos os campos), `tests/test_avaliacao_do_banco.py` (as pessoas do envio
trazem todos os campos do parâmetro), `tests/test_api_front.py` (as mesmas colunas para os dois perfis, cada um pela
sua rota; `no-cache` no js e no css) e os roteiros de clique `grade_de_funcionarios` (45 + 3 colunas, 24 marcas de
obrigatório, "Informação não encontrada" no vazio, CPF formatado, legenda, ficha pelo nome) e `grade_do_especialista`
(45 + 2 colunas na tela Envios do banco, as mesmas marcas e a mesma frase).


<a id="adr-112"></a>

### ADR-112 · Visão geral da empresa na aba Empresas do banco; Situação primeiro e legenda dos status ✅

**Contexto (2026-09-27, pedidos da usuária).** (1) "O correto seria clicar em acompanhar a empresa e aí aparecer a
tela com a visão geral da empresa e a lista de funcionários" — na aba Empresas do banco, a ficha só tinha Dados,
Usuários, Catálogo e Kit. (2) Na grade da empresa: "trazer a informação Situação para a primeira coluna e, ao invés do
'i' de informação, trazer a legenda do que é cada status em cima do grid."

**Decisão.**
- A ficha da empresa ganhou a aba **Visão geral**, a primeira e a que abre ao clicar na empresa: os números que a
  própria empresa vê em Acompanhar cadastros (cadastrados, envios, em andamento, com pendência e contas abertas) e a
  **mesma lista de funcionários** da consulta da empresa, na grade do parâmetro (ADR-111). Rota
  `GET /api/banco/empresas/{empresa_id}/visao_geral` (operação nova `consultar_funcionarios`, só BANCO; `no-store`;
  cada abertura registrada nos acessos da empresa, como as pessoas de um envio). No banco, o nome é só texto (a ficha
  com o histórico é da tela da empresa).
- Nas duas listas de funcionários (empresa e Visão geral do banco): **Situação na primeira coluna**; o sinal de
  pendência ao lado do selo saiu; acima da grade, a **legenda dos status** (Cadastrado, Em análise, Pendente, cada um
  com o selo da sua cor e o que quer dizer). A lista de pessoas de um envio (tela Envios) continua com Situação e Ação
  no fim, porque a Ação depende da situação.
- A montagem da linha, das legendas e do cabeçalho fica toda em `front/js/grade_do_parametro.js`, comum às telas.

**Mudança consciente.** O banco passa a ver a lista de funcionários de cada empresa da carteira, com o CPF inteiro, e
não só as pessoas de um envio em avaliação. Base: a mesma autorização contratual já usada na avaliação dos envios
(decisão da usuária de 2026-09-27). O Consultor e o motor de planejamento continuam só com números agregados.

**Como comprovar.** `tests/test_api_front.py` (a visão geral é só do banco, com `no-store` e o acesso registrado; a
empresa recebe 403; empresa inexistente, 404) e o roteiro de clique `grade_de_funcionarios` (a Situação é a primeira
coluna, a legenda dos 3 status, sem o sinal de pendência; no banco, a ficha abre na Visão geral, com os números, a
mesma grade de 45 + 3 colunas e a lista de funcionários).


<a id="adr-113"></a>

### ADR-113 · "Conta aberta" é a última situação do funcionário; a conta em colunas separadas ✅

**Contexto (2026-09-28, pedido da usuária).** "O último status possível para uma informação do cliente deveria ser
'Conta aberta' e o número da conta na coluna correspondente (separada por código do banco, agência e número da conta).
Sendo que o banco é quem sempre envia essa informação, e o status é atualizado depois do banco enviar a informação da
conta." A lista mostrava "Cadastrado" mesmo depois da baixa da conta, e a conta numa coluna só ("Ag. 0001 · 12345-0",
com a data embaixo). O arquivo semanal de contas do banco não tinha o código do banco.

**Decisão.**
- A jornada da pessoa na lista passa a ter quatro situações: Pendente → Em análise → Cadastrado → **Conta aberta**. Só
  o banco leva à última: quando o especialista confirma a baixa do arquivo semanal de contas (ADR-69, passo 16), a
  pessoa com conta passa a "Conta aberta" (`situacao_do_cadastrado`). O selo é verde cheio, para se distinguir do
  "Cadastrado" (verde claro), e a legenda dos status segue a ordem da jornada.
- A conta aparece em **quatro colunas** no fim da grade, nas duas telas (empresa e Visão geral do banco): Código do
  banco, Agência, Conta e Aberta em; sem conta, um traço claro. O download ganha a coluna "Código do banco", e a
  situação no arquivo baixado segue a mesma regra.
- O arquivo de contas aceita a coluna "Código do banco" (procurada por último, para "banco" não tomar colunas como
  "Agência do banco").
- **Revisto no mesmo dia (usuária: "nunca assuma nenhuma informação enviada pelo banco nessa versão").** O 033
  automático saiu. O arquivo precisa trazer **CPF, Código do banco, Agência e Conta** (`COLUNAS_OBRIGATORIAS`; sem uma
  delas, o arquivo é recusado dizendo qual falta); uma linha sem código do banco, agência ou conta não dá baixa e aparece
  na prévia com o motivo. A data de abertura é opcional. A situação "Conta aberta" não vem no arquivo: entra sozinha
  quando o banco devolve a relação e confirma a baixa. Baixa antiga, sem o código gravado, mostra "—".
- **Fica para depois da POC:** a coluna "Informação padrão" (default) no parâmetro, para o banco dizer o valor fixo que
  espera num campo (`docs/proximos_passos.md`).
- **Complemento (2026-09-28, pedido da usuária):** as colunas da conta ficam sob o grupo **"Informações bancárias"**,
  com a nota "enviadas pelo banco ao final da integração" (na legenda e ao passar o mouse no grupo); o "Incluído" ganhou
  o grupo próprio "Inclusão" (antes, os dois ficavam sob "Na consulta"). As legendas ficam sempre uma abaixo da outra.

> **Alterado pelo [ADR-119](#adr-119) (2026-09-28):** o arquivo de contas passou a ter **layout fixo** (.csv com
> `cpf;codigo_banco;agencia;conta;data_abertura`, todas obrigatórias), e qualquer divergência recusa o arquivo
> inteiro; o carregamento saiu da tela Contas abertas para a janela "Carregar Contas Abertas" de Avaliar envios.

**Como comprovar.** `tests/test_contas_abertas.py` (o código do banco e a situação "Conta aberta" depois da baixa; as
outras colunas lidas certo; sem a coluna do código do banco, o arquivo é recusado; linha sem agência não dá baixa; o
download com "Código do banco" e "Conta aberta")
e o roteiro de clique `grade_de_funcionarios` (legenda com os 4 status; 3 pessoas em "Conta aberta" depois da baixa;
as colunas separadas com 033 e a agência; as mesmas 3 contas na Visão geral do banco).


<a id="adr-114"></a>

### ADR-114 · Situação "Aguardando envio": a pessoa sem pendência num envio que ainda não foi ao banco ✅

**Contexto (2026-09-28, pedido da usuária).** "Tem um outro status possível: o cliente que não tem pendência (a IA
conseguiu achar tudo o que precisava), só que a empresa ainda não enviou os dados para o banco porque está corrigindo
casos pendentes. 'Aguardando envio da empresa' ou algo mais curto e ainda assim intuitivo." Antes, essa pessoa aparecia
como "Pendente", com o texto "Ainda não enviado ao banco", como se tivesse algo a corrigir.

**Decisão.** A situação **"Aguardando envio"** (curta e serve às duas telas: para a empresa, lembra que falta ela
enviar; para o banco, diz que ainda não chegou). No envio que está com a empresa, quem tem pendência própria continua
"Pendente" (com a pendência); quem não tem fica "Aguardando envio" (sem pendência). A ordem da legenda (ajustada pela
usuária no mesmo dia): Aguardando envio, Pendente, Em análise, Cadastrado, Conta aberta. Selo cinza (neutro): não pede
ação sobre a pessoa.

**Como comprovar.** `tests/test_acompanhamento.py` (a carga da Aurora com a pendência do CPF: quem tem pendência fica
"Pendente", os outros "Aguardando envio"; a inclusão sem nenhuma pendência: os 5 "Aguardando envio") e o roteiro de
clique `grade_de_funcionarios` (a legenda com os 5 status).


<a id="adr-115"></a>

### ADR-115 · O banco gera o endomarketing; a empresa só baixa e divulga ✅

**Contexto (2026-09-28, decisão da usuária).** "A empresa não vai mais gerar o material do endomarketing, quem vai
fazer isso é o especialista do banco: ele vai conseguir subir um kit de marca para as imagens, ele vai definir quais
benefícios colocar em cada um dos materiais. E pra empresa só aparece uma lista de materiais que ela pode baixar e
usar. Quero essa mudança principalmente por uma questão de risco da empresa divulgar algum benefício do Santander sem a
validação do Santander. Então o banco gera e ela comunica." Até aqui (ADR-19, ADR-53), o RH da empresa escolhia o tipo
e o destaque, a IA escrevia com o catálogo da empresa, e a **própria empresa** aprovava e baixava. O guardrail de
saída já barrava condição inventada, mas a palavra final sobre um texto que fala de produto do banco era da empresa,
não do banco.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · como estava: a empresa gera e aprova (ADR-53) | Autonomia e rapidez para o RH | O banco não valida o que é divulgado sobre os produtos dele: um texto aprovado pela empresa pode sair com um benefício fora de contexto, de uma versão antiga do catálogo ou com uma ênfase que o banco não autorizou |
| B · a empresa gera; o banco aprova antes de liberar | A empresa continua pedindo o que quer | Duas filas (a empresa pede, o banco revisa pedidos que não escolheu); a empresa espera sem saber quando; o kit de marca e os benefícios continuam decididos por quem não responde pela oferta |
| **C · o banco gera, confere e publica; a empresa só baixa e divulga** | Quem responde pela oferta decide o que é dito, com quais benefícios e com qual marca; a empresa recebe o material pronto | Mais trabalho para o especialista; a empresa perde a autonomia de escrever; a vazão depende do banco |

**Decisão.** C.
- **Quem gera:** o especialista do banco, na aba nova **Endomarketing** do Portal Interno
  (`front/banco_endomarketing.html`, no menu depois de "Empresas"): escolhe a empresa, o tipo (comunicado, FAQ, kit de
  boas-vindas ou lembrete de conta), o canal (e-mail, mural ou WhatsApp) e, se quiser, um destaque. Gerar material
  passa a ser operação do perfil BANCO. Saem as rotas da empresa que geravam, decidiam, sugeriam e davam o kit
  (`POST /api/empresa/endomarketing/gerar`, `POST .../{id}/decidir`, `GET .../sugestoes` e `GET .../kit`).
- **Benefícios escolhidos pelo especialista:** em cada material, ele marca quais benefícios do catálogo vigente da
  empresa entram (pelo menos 1; um benefício que não está no catálogo vigente é recusado). Os trechos que vão à IA são
  **só desses benefícios, mais os canais de atendimento**, que fecham todo material. O destaque continua passando pelo
  guardrail de injeção; um destaque que os benefícios escolhidos não trazem é recusado, com aviso na tela.
- **O guardrail de saída continua:** bloco sem fonte, com fonte que não veio dos trechos ou com número que não está no
  trecho citado sai (ADR-53, ADR-61). O prompt continua o `endomarketing_v3`; a avaliação congelada (EXP-006) continua
  chamando o agente sem benefícios escolhidos, com a busca pelo RAG, e mede o mesmo que antes.
- **As situações do material:** RASCUNHO → **PUBLICADO** (a empresa passa a ver) ou DESCARTADO; PUBLICADO →
  **RETIRADO** (a empresa deixa de ver; ex.: o benefício mudou ou saiu do catálogo). Fica gravado quem publicou e quem
  retirou, e quando. Só um rascunho pode ser publicado ou descartado; só um publicado pode ser retirado.
- **A arte é gerada no banco e guardada:** ao publicar, o especialista envia a imagem PNG desenhada no navegador dele
  com o kit da empresa (até 2 MB; a assinatura do PNG é conferida). Ela fica guardada na tabela `artes_dos_materiais`
  (base64 em texto), e a empresa baixa **exatamente a imagem que o banco validou**, não um desenho refeito na tela dela.
- **O kit de marca ganha o logo:** o kit próprio da empresa passa a ter o logo (PNG ou JPEG até 500 KB; a assinatura
  do arquivo é conferida, não só a extensão), guardado na tabela `logos_dos_kits` (base64 em texto) e usado na arte. O
  kit padrão do banco continua sem logo.
- **O que a empresa vê:** em "Materiais de endomarketing", só a lista dos materiais **publicados** da própria empresa,
  do mais recente ao mais antigo, para baixar o texto (um .txt montado no navegador a partir do título e dos blocos) e
  a arte. Os materiais antigos, aprovados pela empresa no modelo anterior (situação APROVADO), **não aparecem mais para
  ela**; no banco, aparecem como "Aprovado pela empresa (modelo anterior)".
- **Sugestões no Portal Interno:** o total de funcionários da empresa ainda sem conta (sugere o lembrete, sempre para
  toda a equipe, sem citar ninguém) e as inclusões homologadas que ainda esperam o kit de boas-vindas (o kit gerado
  fica ligado à inclusão, e a sugestão some).

**Por quê.** O benefício é do banco: é o banco que responde pela oferta, pelas condições e pela marca. Com a empresa
gerando e aprovando, um material podia ser divulgado sem que o banco soubesse. Agora a IA escreve, o guardrail confere
cada bloco e uma pessoa do banco dá a palavra final antes de o texto chegar a qualquer funcionário: o **controle de
publicação** fica com quem responde pelo produto. A empresa continua com o que só ela faz bem: comunicar à própria
equipe.

**Trade-off aceito.**
- **Mais trabalho para o especialista:** todo material passa por ele (escolher os benefícios, conferir, gerar a arte,
  publicar e, quando preciso, retirar).
- **A empresa perde a autonomia de escrever:** não pede mais um material sob medida pela tela; para algo novo, fala
  com o especialista (o "Posso ajudar?").
- **A vazão depende do banco:** se o especialista não gera, a empresa fica sem material. **Mitigação:** as sugestões
  automáticas do Portal Interno (lembrete quando há funcionários sem conta; kit de boas-vindas para cada inclusão
  homologada) e a lista de empresas com o número de rascunhos e de publicados de cada uma mostram ao especialista o que
  falta gerar.

**Altera** o ADR-16 (a aprovação dos textos passa a ser do banco), o ADR-19 e o ADR-53 (quem pede, quem aprova e o que
a busca usa), o ADR-30 (o total sem conta vira sugestão para o banco), o ADR-87 (o kit vai à arte no banco, a rota do
kit da empresa sai e o logo deixa de ser evolução), o ADR-93 (o lembrete e o canal são escolhidos pelo especialista) e o
passo 13 do ADR-69 (as rotas de endomarketing da empresa). Cada um ganhou a nota "Alterado pelo ADR-115", sem apagar o
histórico; o ADR-61 ganhou uma nota dizendo que a avaliação congelada não muda.

**Como comprovar.** `tests/test_endomarketing.py` (os trechos só dos benefícios escolhidos e dos canais de atendimento;
benefício fora do catálogo vigente e lista vazia recusados; publicar, descartar e retirar só nas situações certas; o
guardrail de saída, o lembrete e o corte do WhatsApp continuam), `tests/test_portal_da_empresa.py` (a empresa vê só
os publicados da própria empresa, nunca rascunho, descartado, retirado ou aprovado no modelo anterior; a arte só da
própria empresa e só de material publicado; as rotas antigas de gerar e aprovar não existem mais) e
`tests/test_endomarketing_do_banco.py` (o kit com as cores e o logo, que só entra no kit próprio; o logo com a
assinatura errada, vazio ou acima de 500 KB recusado; a arte que não é PNG não publica; o ciclo gerar → publicar com
arte → retirar pela API, com a empresa vendo e depois deixando de ver; o kit de boas-vindas só para a inclusão da
própria empresa; as rotas do banco só para o BANCO). `tests/test_seguranca.py` confere que só o BANCO gera, publica e
retira, e `tests/seguranca/test_seg_acesso.py` (A-27, refeito) que a outra empresa não baixa a arte alheia nem usa as
rotas do banco. Roteiros de clique: `tests/e2e/roteiros/endomarketing_do_banco.py` (o especialista escolhe os benefícios,
gera, publica e retira; a empresa vê o material e depois deixa de ver), `arte_fiel_ao_texto.py`, `arte_com_o_kit.py`
e `lembrete_no_whatsapp.py` (agora pela tela do banco).

**Origem.** Decisão da usuária, 2026-09-28 ("o banco gera e ela comunica").


<a id="adr-116"></a>
### ADR-116 · O aprendizado do RAG exige 2 empresas confirmando o mesmo par ✅

**Contexto (2026-09-28, decisão da usuária).** No ADR-70, bastava **1 empresa** ter um par "coluna → campo" aprovado
pelo banco para ele entrar no índice `mapeamentos_aprovados`, que o Interpretador de **todas** as empresas consulta.
A auditoria de avaliação dos agentes (vault, `04-Avaliacao/Plano de avaliacao dos agentes`) apontou o risco de
**envenenamento do aprendizado**: um par errado de uma empresa só, por engano ou de propósito, que o banco deixou passar
na avaliação do envio, passaria a ser sugerido para as outras. Pergunta da usuária: "já podemos tomar a decisão de
limitar mais: precisa considerar mais empresas confirmando a mesma informação".

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · manter 1 empresa (ADR-70) | A IA aprende no primeiro envio aprovado | Um erro isolado vira sugestão para todas as empresas; a única defesa é o banco perceber na avaliação |
| **B · 2 empresas diferentes** | Uma empresa sozinha não ensina nada às outras; um cabeçalho comum (ex.: "Sal. Bruto") aparece logo em 2 empresas | Um cabeçalho usado por uma empresa só nunca entra no índice compartilhado |
| C · 3 ou mais empresas | Mais proteção | Com poucas empresas no começo, quase nada é aprendido; o ganho de proteção sobre o B é pequeno |

**Decisão.** B: `MINIMO_DE_EMPRESAS_PARA_APRENDER = 2` (`rag/aprendizado.py`). A mesma empresa aprovando o par
várias vezes (com maiúsculas ou espaços diferentes) continua contando uma vez só.

**Por quê.** O índice compartilhado é uma memória **coletiva**: faz sentido que uma informação só vire conhecimento de
todos quando duas fontes independentes concordam. A própria empresa **não perde nada**: o reuso do que ela mesma já
aprovou (ADR-24, `services/mapeamentos.py`) não passa por este índice, então as inclusões dela continuam aproveitando
o mapeamento anterior desde o primeiro envio.

**Trade-off.** Um cabeçalho exclusivo de uma empresa não ajuda as outras. É o custo aceito: um cabeçalho que só uma
empresa usa também é o que menos ajudaria as demais. Com o volume de produção (milhares de empresas), a medição do
ganho pode indicar outro número; mudar é trocar uma constante.

**Como comprovamos.** `tests/test_aprendizado_rag.py`:
- a regra atual é 2;
- um par aprovado por 2 empresas entra, com a fonte e "por 2 empresa(s)";
- uma empresa sozinha, mesmo aprovando duas vezes, não ensina, e a segunda empresa faz entrar;
- os testes das outras regras (campo fora do layout, coluna perigosa, nenhum código de empresa no trecho, conflito,
  índice refeito na aprovação) passaram a usar 2 empresas, para cada um continuar barrando pela própria regra, e não
  pela contagem.

Em `tests/seguranca/test_seg_ia.py`, o D-31 e os achados **D-32** (cabeçalho com nome e CPF) e **D-33** (ordem
disfarçada no nome da coluna) passaram a usar 2 empresas pelo mesmo motivo. O D-32 e o D-33 continuam como falha
esperada (a regra que falta continua faltando), mas ficam **atenuados**: agora uma empresa sozinha não leva esse texto
para as outras. Em `tests/test_correcao.py`, o teste do caminho aprovação → índice desce o mínimo para 1, porque
homologa só a Aurora.

**Medição pendente:** o teste de envenenamento (injetar um par errado e contar em quantas buscas de outras empresas ele
aparece no topo), no plano de avaliação.

**Altera** o ADR-70 (regras de entrada). **Origem.** Decisão da usuária, 2026-09-28.


<a id="adr-117"></a>
### ADR-117 · Consultor simplificado: agente único em uso; o supervisor fica só no experimento 🧪

**Contexto (2026-09-28, decisão da usuária).** A auditoria de avaliação dos agentes (vault,
`04-Avaliacao/Plano de avaliacao dos agentes`) perguntou quanto o Consultor ganha de fato. Ele usa as **mesmas
consultas da tela de Planejamento** e, por regra, não pode inventar número; o que ele acrescenta é juntar fontes numa
resposta só (planejamento, ganho e situação da integração), comparar cenários de taxa lado a lado e pedir a taxa
quando ela falta. A arquitetura supervisor + 3 subagentes (ADR-18) fazia, no pior caso, perto de 15 chamadas à IA
por pergunta, e no EXP-005 (MOCK) empatou com o agente único (12 de 12 nas duas) fazendo cerca de **67% mais
chamadas** (2,25 × 1,42 por caso). O enunciado não exige um assistente de conversa (o tema escolhido é o 2); o
Consultor é o componente do tema 1 e o único agente do projeto com ferramentas. Pergunta da usuária: "tenho dúvidas
se vale para esse projeto manter esse agente". Decisão: "por enquanto vamos manter de forma simplificada".

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · manter o supervisor + 3 subagentes (ADR-18) | Nenhum retrabalho | Complexidade e chamadas a mais sem ganho medido |
| **B · agente único com as 4 ferramentas; o supervisor só como braço do experimento** | Menos chamadas, menos pontos de falha e de ataque; continua o agente com ferramentas e a comparação medida de arquiteturas | O supervisor fica no código só para medir |
| C · tirar o Consultor (a comparação de cenários vai para a tela, sem IA) | Menos código, custo e superfície de ataque | Perde o único agente com ferramentas e a comparação de arquiteturas; retrabalho no deck, na documentação e nos testes |

**Decisão.** B. `agents/consultor.py` ganha `ARQUITETURA_PADRAO = AGENTE_UNICO`: a tela de Planejamento, o botão
"Perguntar ao Consultor" e a API usam o agente único (`services/acesso.py`). Um LLM recebe a pergunta e escolhe, de
uma vez, as ferramentas (`consultar_planejamento`, `simular_ganho`, `comparar_cenarios`,
`consultar_status_integracao`); a permissão e os filtros de cada ferramenta continuam conferidos pelo dono dela
(`agents/ferramentas_do_consultor.py`), e o guardrail de entrada, a síntese e o guardrail de saída não mudam. O
supervisor continua disponível com `arquitetura="supervisor"`, usado só pela avaliação
(`eval/avaliacao_do_consultor.py`). Na Telemetria, cada ferramenta aparece como "Consultor (agente único)", não
mais como "Subagente".

**Por quê.** Com a mesma exatidão medida, o mais simples vence: menos chamadas, menos custo, menos latência e menos
lugares onde uma resposta fora do contrato pode travar a pergunta. O que o supervisor prometia (acertar mais em
perguntas compostas) ainda não foi provado; se a medição com IA real mostrar que ele compra exatidão, a troca volta
a ser uma constante.

**Trade-off.** Um prompt só escolhe todas as ferramentas, e uma pergunta composta pode sair com uma ferramenta a
menos. Mitigação: a pergunta composta está no golden (`pergunta_composta`), e a medição com IA real mostra se isso
acontece.

**Como comprovamos.**
- `tests/test_consultor.py`: sem informar a arquitetura, a pergunta vai pelo agente único e é respondida; nas
  perguntas golden, as duas arquiteturas usam as mesmas ferramentas e respondem o mesmo texto; os testes que são do
  supervisor (limite de delegações, supervisor fora do contrato, subagente que escolhe ferramenta de outro papel,
  subagente que corrige o filtro) passaram a pedir o supervisor explicitamente.
- `tests/test_painel.py`: a Telemetria grava "Consultor (agente único)" na pergunta e na ferramenta.
- `tests/seguranca/test_seg_ia.py`: D-05, D-06 e D-10 do supervisor pedem o supervisor explicitamente; **o D-10
  ganhou a versão do agente único** (o motivo do "fora do escopo" vai para a tela sem conferência), como falha
  esperada: a brecha existe também no caminho de produção.
- **Medição pendente** (bateria final, depois da aprovação do orçamento): as duas arquiteturas com IA real no golden
  ampliado, com exatidão, chamadas, custo e latência.

**Altera** o ADR-18 (a arquitetura em uso) e o ADR-60 (o supervisor vira o braço de comparação). **Origem.** Decisão
da usuária, 2026-09-28.

<a id="adr-118"></a>
### ADR-118 · Pendências resolvidas por conversa com a IA, que aplica na hora, presa à pendência, com Desfazer ✅

**Contexto (2026-09-28, pedido da usuária).** Em "Pendências para você" (Acompanhar) cada pendência tinha campos
para digitar o valor certo e o motivo, botões de um clique e, à parte, o "Perguntar à IA", em que a IA só PROPUNHA e a
empresa clicava em "Aplicar" (ADR-16). A usuária pediu: (1) mostrar sempre a informação que gerou a dúvida (ex.: o
CPF lido, quando o dígito verificador não bate); (2) nada de campo para digitar: a pessoa explica à IA e ela já
processa, com um contador de "processando"; (3) uma conversa de verdade, que abre e fecha; (4) no fim da lista, dois
botões sempre à vista: descartar a leitura, e descartar e enviar outro arquivo; (5) a conversa só aceita orientação
sobre a informação da pendência, nunca sobre outra.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · manter: a IA propõe e a empresa clica em "Aplicar" | Controle humano explícito | Um passo a mais em cada pendência; a pessoa repete o que acabou de escrever |
| **B · a IA aplica na hora e mostra o que mudou, com Desfazer** | A mensagem da pessoa é a decisão; mais rápido; o erro de entendimento se desfaz num clique | Uma interpretação errada muda o dado até alguém desfazer |
| C · a IA aplica sem Desfazer | O mais simples | Um valor errado que passa na regra some da lista e não tem volta pela conversa |

**Decisão.** B, nas duas telas (Acompanhar e a conferência do Cadastrar), decidida pela usuária em 4 perguntas:
- **A mensagem da empresa é a decisão humana.** A IA escolhe uma ação de uma lista fechada (`responder`,
  `explicar_regra`, `corrigir`, `nao_cadastrar`, `confirmar_alerta`, `preencher_para_todos`, `escolher_formato`,
  `solicitar_remapeamento`, `fora_do_assunto`; prompt `assistente_correcao_v2`), e o serviço da tela
  (`services/assistente_na_tela.py`) aplica e valida o envio de novo. A correção entra já APLICADA, com o login de quem
  escreveu, o antes, o depois e a frase como motivo.
- **Presa à pendência, no código.** Campo e linha são sempre os da pendência; a releitura de coluna só vale para as
  colunas ligadas a esse campo. O que a IA mandar diferente é recusado e nada muda
  (`agents/assistente_correcao.py::_fora_da_pendencia`), com a resposta "Aqui eu só ajusto <campo> de <pessoa>". O
  guardrail de injeção continua antes do LLM.
- **Desfazer** (`POST /api/empresa/cadastro/{id}/assistente/desfazer`): a correção vira DESFEITA (os dados atuais só
  usam as APLICADAS), o lote do "para todos" volta inteiro, e a confirmação de um alerta é reaberta; o envio é validado
  de novo e a pendência volta. Recusado se a mesma célula mudou depois ou se o envio já foi ao banco. Sem Desfazer: a
  escolha de formato de uma coluna e "Sim, é do nosso grupo" (põe o CNPJ no cadastro da empresa).
- **O valor lido à mostra** em cada pendência (`valor_lido`: CPF formatado, data dd/mm/aaaa, renda em reais; exemplos
  da coluna nas dúvidas de formato; "o arquivo veio sem este dado" quando falta), inteiro, como já era na conferência
  do Cadastrar: é o dado da própria empresa.
- **Os botões de um clique viram respostas rápidas** na conversa (`sugestoes`: pílulas; algumas a pessoa completa com
  o valor). Num campo de lista, as primeiras são os valores aceitos do parâmetro; no máximo 8.
- **O cartão é uma conversa, e curta** (2ª e 3ª rodadas com a usuária: o primeiro desenho tinha texto demais; o
  segundo, sem balões, "parecia um campo simples e não um chat com a IA"): o nome e o campo no alto; a `pergunta` da
  IA num balão, UMA frase com o valor lido dentro (ex.: `No arquivo veio "Solteiro(a)", que não está na lista. Qual é
  o certo?`, montada por regra em `services/pergunta_da_pendencia.py`, sem nome técnico de campo); as respostas
  rápidas; a caixa "Responda à IA..."; as respostas da pessoa em balões; "Pronto: <campo> = <valor>" com Desfazer no
  balão da IA; a linha cinza "arquivo · data".
- **Variações de gênero nos campos de lista** ("Solteiro(a)", "solteiro/a", "Solteira", "Viúva") passam a ser
  entendidas pelo Normalizador, só quando casam com um item da lista do parâmetro; não viram mais pendência. Os envios
  que ainda estavam com a empresa são padronizados de novo pelo script
  `scripts/padronizar_de_novo_os_envios_pendentes.py` (sem IA; as correções e confirmações da empresa continuam
  valendo).
- **Descartar, sempre à vista:** o rodapé da lista tem "Descartar a leitura" e "Descartar a leitura e enviar outro
  arquivo", para o arquivo do filtro; com "Todos os arquivos" e mais de um arquivo, a janela pede o arquivo.
- As rotas `/assistente/decidir` e `/assistente/justificar` saíram. As rotas manuais (`/api/empresa/pendencias/...`)
  continuam na API, mas a tela das pendências não as usa mais.
- **4ª rodada (texto mais natural, confirmação e log; usuária: "algo assim.. mais natural" e "quando o usuário falar
  pra não subir uma informação, precisa de confirmação e precisa entrar em log").** A fala do agente passa a ter o
  campo, pela descrição do parâmetro (sem os parênteses e sem o final "do funcionário"; o artigo "o/a" só quando a
  1ª palavra é conhecida, senão "O arquivo veio sem este dado de Diego: <campo>"), e o primeiro nome da pessoa (ex.: `O CPF de Maria veio "123.456.789-00", e o dígito verificador não bate. Qual
  é o CPF certo?`). Num campo de lista, o agente só dá um **palpite quando é seguro**
  (`normalizador.palpite_na_lista`): o valor vira um item da lista pelas regras da padronização, ou um único item se
  parece muito com ele (semelhança do `difflib` ≥ 0,85, com folga de 0,1 sobre o 2º); na dúvida, sem palpite, e o
  agente pede para escolher. Com palpite, a fala termina em `Acredito que o certo é "Solteiro". Posso usar?`, e a
  primeira resposta rápida é `Sim, use "Solteiro"`. **Não subir uma informação pede confirmação:** "não cadastrar esta
  pessoa" e "deixar em branco" não valem na hora; a retirada fica PROPOSTA, o agente pergunta ("Confirma que não
  vamos cadastrar Diego neste envio? Fica registrado com o seu nome.") e a pessoa responde pela rota
  `POST /api/empresa/cadastro/{id}/assistente/confirmar` (`{correcao_id, confirmar}`): o "sim" aplica, com Desfazer, e
  o "Cancelar" deixa tudo como estava. Essas duas frases saíram das respostas rápidas (ficam só os valores da lista, o
  palpite, "Está certo assim" nos alertas e o formato): "se a pessoa quiser ela diz isso pra IA, e a IA pede
  confirmação". **Log:** cada confirmação e cada cancelamento entram na trilha de auditoria do envio
  (`RETIRADA_CONFIRMADA_PELA_EMPRESA` e `RETIRADA_CANCELADA_PELA_EMPRESA`), com o login, a linha, o campo (ou "pessoa
  inteira") e a frase da pessoa, sem nenhum valor pessoal; o banco vê, na trilha de "Avaliar envios", quantas
  retiradas a empresa confirmou, e a linha do tempo técnica conta os dois eventos como decisão humana.
- **5ª rodada (a IA escreve, com diretriz de tom de voz; usuária: "eu só dei exemplos... a LLM precisa responder de
  forma mais natural... uma diretriz de tom de voz que transmita essa questão da seriedade").** A primeira fala do
  Agente de validação sobre cada pendência passa a ser escrita pela IA (`agents/redator_de_perguntas.py`, modelo
  pequeno, prompt `pergunta_da_pendencia_v1`), numa chamada por envio, só com as pendências ainda sem pergunta; a
  pergunta fica guardada (`services/perguntas_das_pendencias.py`, chave envio + regra + linha + valor lido) e só é
  escrita de novo quando o valor lido muda. A **diretriz de tom de voz** mora num arquivo só
  (`prompts/tom_de_voz_do_agente_de_validacao.md`), lido pelos dois prompts do agente (a pergunta e a conversa): sério,
  cordial, direto, sem gíria, emoji ou exclamação, sem culpar ninguém, sem termo técnico, até duas frases, o valor
  entre aspas e uma pergunta só no fim. **Conferência no código:** a frase precisa ter até 220 caracteres, um único
  "?" no fim, o valor lido (quando a regra pede) e o palpite entre aspas (quando há), e nada de "_", "!" ou "regra";
  o que não passa é trocado pela **frase de reserva** (`services/pergunta_da_pendencia.py`), reescrita para ficar
  sempre certa com qualquer descrição do parâmetro (o nome do campo vai entre aspas como "a informação", o que fecha
  o defeito "...onde o funcionário trabalha de ninguém"); o modo MOCK usa as próprias reservas. **Nunca bloqueia a
  lista:** com a IA fora, lenta (8 s) ou fora do formato, valem as reservas, nada é guardado, e a falha fica na
  Telemetria (cada chamada é gravada como a dos outros agentes, com o modelo e a versão do prompt). **Custo:** uma
  chamada ao modelo pequeno por envio com pendência nova (e por valor lido que mudou), não por abertura da lista. As
  falas que o servidor monta na conversa (confirmação, "Pronto", recusa, "Tudo bem, nada mudou", valor recusado)
  foram revistas pela mesma diretriz.

**Por quê.** A pessoa já disse o que quer; pedir um clique de "Aplicar" depois é repetir. O risco de a IA entender
errado fica coberto de três jeitos: o que mudou aparece escrito ("CPF: X → Y"), o Desfazer volta num clique, e a trava
no código impede a IA de mexer em outro campo ou em outra pessoa. A trava fecha o achado de segurança **D-21**
(proposta fora da pendência em discussão).

**Trade-off.** Entre a mensagem e o Desfazer, o dado fica com o valor que a IA entendeu; um valor errado que passa na
regra some da lista de pendências (fica o aviso "Resolvido agora", com Desfazer, até a página ser recarregada). Cada
mensagem é uma chamada à IA (custo por pendência, no modo real).

**Como comprovamos.**
- `tests/test_assistente_na_tela.py`: aplicar na hora (corrigir, não cadastrar, confirmar, para todos, formato); a
  trava (outro campo, outra linha, coluna de outro campo → recusado, nada muda); fora do assunto; desfazer de cada
  tipo e as recusas; `valor_lido` e `sugestoes` nas duas listas; rotas com 401, 403 e outra empresa.
- `tests/test_pergunta_da_pendencia.py`: a pergunta de cada regra, com o valor, o campo e a pessoa e sem nome técnico
  de campo; o palpite só quando é seguro ("Casdo" → "Casado"; "Salário" e "Superior complet" sem palpite); `Sim, use
  "..."` corrige; as respostas rápidas sem "não cadastrar" e sem "deixar em branco".
- 5ª rodada, em `tests/test_perguntas_das_pendencias.py` (IA falsa, sem custo): resposta boa aparece e fica guardada (a lista
  abre de novo sem chamar a IA); resposta ruim (sem "?", com nome técnico, sem o valor, com "!", com duas perguntas)
  cai na reserva; IA fora do ar, fora do formato ou lenta cai na reserva e a falha fica na Telemetria; valor lido
  mudado escreve de novo; os dois prompts usam a mesma diretriz. Em `tests/test_pergunta_da_pendencia.py`, a frase do
  arquivo inteiro fica certa com a descrição longa do código da unidade.
- 4ª rodada, em `tests/test_assistente_na_tela.py`: "não cadastrar" e "deixar em branco" pedem confirmação e só valem
  com o "sim"; o "Cancelar" não muda nada; campo obrigatório não fica em branco; os dois eventos na trilha, sem valor
  pessoal; a rota `/assistente/confirmar` com 401, 403 e outra empresa.
- Testes do Normalizador e do script: "Solteiro(a)" e "Divorciado/a" viram o item da lista; "Solteirx" e "Noiva"
  continuam recusados; um envio antigo com essas pendências fica sem elas depois do script, e um envio descartado fica
  de fora.
- `tests/seguranca/test_seg_ia.py`: o D-21 deixou de ser falha esperada e passa; o D-18 foi adaptado à resposta nova.
- Roteiro de clique `pendencias_por_conversa` (valor lido, conversa que abre e fecha, contador, "Resolvido agora" e
  Desfazer, fora do assunto recusado, rodapé com os dois botões, o mesmo na conferência do Cadastrar).

**Altera** o ADR-16 (nas pendências, a mensagem é a decisão) e o ADR-17 (a releitura fica presa às colunas do campo
da pendência). **Origem.** Pedido da usuária, 2026-09-28.

<a id="adr-119"></a>

### ADR-119 · Arquivo de contas abertas com layout fixo, recusado inteiro com qualquer divergência ✅

> **Alterado pelo [ADR-122](#adr-122) (2026-09-28):** o arquivo passou a ser carregado **por empresa**, na ficha da
> empresa (aba "Contas abertas"), com a 1ª coluna `cnpj_empresa`; o CPF precisa estar Cadastrado nessa empresa.


**Contexto (2026-09-28, pedido da usuária).** "Na tela de Envios deveria ter um botão de 'Carregar Contas Abertas' e
abrir o popup para carregar as contas (bem parecido com o envio de arquivos da empresa)... aqui o layout é definido e
padrão, qualquer coisa diferente do layout definido o sistema deveria reclamar e não deixar. E se o sistema encontrar
divergência, não deixar importar até o especialista corrigir: funcionários que estão no arquivo e não foram enviados,
duplicidade de CPF, duplicidade de conta e demais situações. E deixar muito claro o formato do arquivo esperado e as
validações que o sistema faz." Antes, o serviço achava as colunas por palavras parecidas (aceitava CSV e Excel com
qualquer ordem e nome) e **pulava** as linhas com problema, dando baixa nas outras.

**Opções.** (a) Manter a leitura tolerante e só mostrar mais avisos; (b) layout fixo e recusa do arquivo inteiro.

**Decisão (b), com as escolhas da usuária:**
- **Layout fixo:** `.csv` separado por `;`, cabeçalho exatamente `cpf;codigo_banco;agencia;conta;data_abertura`,
  nessa ordem, todas obrigatórias. CPF com 11 dígitos e dígitos verificadores válidos; código do banco com 3 dígitos;
  agência com 4; conta com 1 a 12 dígitos, traço e o dígito; data DD/MM/AAAA que existe e não é futura. Excel não é
  aceito.
- **Qualquer divergência recusa o arquivo inteiro** (nada é gravado; o registro do arquivo fica `RECUSADO`, só com
  contagens e sem CPF). São 15 tipos: do arquivo (não é .csv de texto, sem linhas, cabeçalho diferente, linha sem as 5
  colunas), de cada linha (coluna vazia, CPF, código do banco, agência, conta ou data inválidos, CPF repetido no
  arquivo, mesma conta em CPFs diferentes) e da carteira (CPF que não está **Cadastrado** — o motivo diz se está em
  análise no banco, ainda com a empresa ou nunca foi enviado —, CPF que já tem outra conta gravada, conta já gravada
  para outro CPF).
- **Só avisa:** o CPF que vem de novo com a **mesma** conta já gravada (a linha é ignorada).
- **Fonte única:** colunas, formatos e conferências ficam em constantes de `services/contas_abertas.py`, e a rota
  `GET /api/banco/contas/layout` as entrega à tela, que explica exatamente o que o código confere.
- **Onde:** o botão "Carregar Contas Abertas" em Avaliar envios abre a janela (`front/js/janela_contas_abertas.js`):
  o formato com o modelo para baixar, as conferências, e depois a recusa (linha, CPF, problema e como corrigir, com a
  lista para baixar) ou a prévia com o "Confirmar a baixa". A tela Contas abertas vira histórico, com o mesmo botão.
- CPF cadastrado em duas empresas ganha a baixa nas duas.

**Porquê.** O arquivo é do próprio banco e alimenta o que a empresa vê para pagar o salário (ADR-102): uma baixa
parcial esconde o problema e deixa contas erradas ou faltando sem ninguém perceber. Recusar tudo força a correção na
origem, e a lista de divergências diz o que corrigir.

**Trade-off.** Um único erro segura a semana inteira de baixas até o arquivo ser corrigido; e o formato não tolera
variações que antes passavam (Excel, outra ordem de colunas).

**Como comprovar.** `tests/test_contas_abertas.py` (30 testes: cada tipo de divergência trava; arquivo limpo gera a
prévia e a baixa; a mesma conta só avisa; outra conta e conta de outro CPF travam; confirmar recusado dá 400; a rota do
layout com 401, 403 e 200; CPF em duas empresas) e o roteiro de clique `carregar_contas_abertas`.

**Altera** o ADR-113 (a leitura das colunas) e o passo 16 do ADR-69 (onde e como o arquivo é carregado). **Origem.**
Pedido da usuária, 2026-09-28.

<a id="adr-120"></a>

### ADR-120 · Pendências em grupo (uma pergunta para o mesmo valor em várias pessoas) e "Resolvidas" com a conversa guardada ✅

**Contexto (2026-09-28, pedido da usuária).** Depois do ADR-118, cada pessoa com um valor fora da lista ganhava um
cartão próprio: um arquivo com 23 pessoas em "Divorciado(a)" virava 23 conversas iguais. A usuária perguntou "como o
agente melhora pra entender que Solteiro(a) → Solteiro?... ou qdo acontecer algo assim com muita frequência na base ele
já perguntar de uma vez... tipo Percebi que... vc enviou dessa forma 'Solteiro (a)'. Vou considerar como
'Solteira'", e combinou uma escada de três degraus: (1) regra fixa no Normalizador para o que é óbvio (feita no
ADR-118: as variações de gênero); (2) **uma pergunta para todos os valores iguais do arquivo** (este ADR); (3) um
dicionário aprendido por empresa, que vale sozinho nos próximos arquivos dela (próximo passo). Pediu também que a
decisão entre na documentação e na apresentação executiva.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · manter um cartão por pessoa | Nenhuma decisão vale para quem a empresa não viu | 23 respostas iguais; a empresa desiste no meio |
| **B · um cartão para o grupo, a resposta vale para todas, com Desfazer e "Responder uma a uma"** | Uma resposta; as exceções continuam possíveis; volta num clique | Uma resposta errada muda 23 pessoas até o Desfazer |
| C · o agente assume o palpite sozinho em todas | Nenhuma pergunta | Decide pela empresa um dado dela, sem ela ver (contraria o ADR-118) |

**Decisão.** B, nas duas telas (Acompanhar e a conferência do Cadastrar):
- **Quando agrupa** (`services/pendencias_em_grupo.py`): valor fora da lista (`VALOR_NAO_CONVERTIDO`) de uma pessoa,
  num **campo de lista fechada** do parâmetro, com o **mesmo valor lido** (sem diferença de maiúsculas e de espaços
  nas pontas) em **2 ou mais pessoas do mesmo arquivo** (`MINIMO_PARA_AGRUPAR`). Campos livres (salário, data, CPF)
  nunca agrupam: cada pessoa tem o seu valor.
- **A lista continua com uma pendência por pessoa** (`GET /api/empresa/pendencias` e a conferência); cada uma traz o
  mesmo `grupo` ({chave, quantidade, linha_do_representante, valor_lido, palpite, pergunta, sugestoes}). Quem junta o
  cartão é a tela, e **os números continuam contando pessoas** (o cartão do grupo vale por N no alto, nos filtros e no
  aviso do arquivo): o mesmo número bate em todas as telas.
- **O cartão do grupo:** o título "23 pessoas com o mesmo valor"; uma pergunta só, escrita pela IA (prompt
  `pergunta_da_pendencia_v2`, com "quantidade_de_pessoas"; a conferência exige o número em algarismos) ou a reserva
  (`'23 pessoas deste arquivo vieram com a informação "Estado civil" como "Divorciado(a)", que não está entre as opções
  aceitas. Acredito que o certo é "Divorciado" para todas. Posso usar?'`); as respostas rápidas para todas (`Sim, use
  "Divorciado" para as 23` e os outros valores da lista); "Ver quem são (23)"; **"Responder uma a uma"** (um cartão por
  pessoa, cada um com "Responder as 23 de uma vez"). Na conferência do Cadastrar, cada linha do grupo mostra o cartão
  do grupo, e a conversa é uma só.
- **A resposta vale para todas:** a mensagem vai com `em_grupo` (`POST /api/empresa/cadastro/{id}/assistente`), e o
  servidor **refaz o grupo a partir do relatório do Validador** (o navegador nunca manda a lista de pessoas). Um valor
  vira uma correção APLICADA por pessoa, todas com a mesma hora (`correcoes.trocar_em_varias_linhas`), com o login, o
  antes, o depois e a frase como motivo; na trilha, `CORRECAO_EM_GRUPO` com o campo e a quantidade, sem valor pessoal.
  O agente sabe do grupo (prompt `assistente_correcao_v3`, regra 8).
- **Desfazer do grupo inteiro** (tipo `grupo`): as N correções voltam juntas (`desfazer_lote`, que passa a
  reconhecer o lote pelo campo, a hora, quem pediu e o motivo) e as pendências reaparecem; trilha
  `CORRECAO_EM_GRUPO_DESFEITA`.
- **No cartão do grupo, só um valor para todas muda dado.** "Não cadastrar", "deixar em branco" ou confirmar não
  valem ali (são decisões pessoa a pessoa): o agente responde que isso se faz pelo "Responder uma a uma", e nada muda.
- Se o grupo se desfez no meio (as outras pessoas foram resolvidas uma a uma), a resposta vale só para a pessoa.
- **2ª rodada: "Pendências em aberto" e "Resolvidas", com a conversa guardada** (usuária: "a IA sempre precisa
  colocar no CHAT exatamente o que resolveu, se a pessoa quiser abrir de novo a conversa que teve com a IA ela pode
  e uma vez que foi resolvido e a pessoa foi para outro card, deveria ir para o filtro resolvidos... e sumir da tela";
  escolhas dela: guardar no servidor, até o arquivo ir ao banco, o nome "Resolvidas", sair ao mexer em outro cartão):
  - **as falas de mudança dizem exatamente o que mudou:** de quem, a informação, o antes e o depois
    (`Pronto: troquei a informação "Estado civil" de Ana de "Solteirx" para "Solteiro".`; no grupo, `... em 3
    pessoas: Ana, Bia e Caio.`; `Pronto: tirei Davi Melo (linha 5) deste envio...`; `Pronto: deixei a informação
    ... em branco (no arquivo veio "...")`; na confirmação de um alerta, o valor confirmado). Corrige também o nome
    que sumia na fala e no resumo de "não cadastrar" (era lido depois de a pessoa sair dos dados);
  - **a conversa fica guardada no servidor** (`services/conversas_das_pendencias.py`, tabela
    `conversas_das_pendencias`, um balão por linha): a pergunta que a pessoa viu, o que ela escreveu, a resposta com o
    que mudou, a escolha na confirmação e o Desfazer ("Desfeito" no balão e o que voltou). Quem grava é o servidor;
    a chave é a mesma da tela (`<envio>|<regra>|<linha>` ou `grupo|<envio>|<campo>|<valor>`). A conversa tem dado
    pessoal da própria empresa: só a empresa dona do envio a lê; a trilha continua sem valor pessoal;
  - **`GET /api/empresa/pendencias/resolvidas`:** as conversas cuja última mudança ainda vale e cuja pendência saiu,
    só dos envios que ainda estão com a empresa (depois do banco ou do descarte, somem), da mais recente para a mais
    antiga, com de quem, a informação, a quantidade, o resumo, quem e quando, e os balões;
  - **a tela:** os filtros viram "Pendências em aberto (N)" e "Resolvidas (M)" (contando pessoas; o filtro por
    arquivo vale para os dois). O cartão resolvido fica no lugar, verde, com o "Pronto: ..." e o Desfazer, até a
    pessoa mexer em outro cartão ou trocar o filtro; aí desliza para fora. Em "Resolvidas", cada item tem o resumo,
    "Resolvida em dd/mm · hh:mm por <login>" e "Ver a conversa (N)", só de leitura, com o Desfazer na última
    mudança. O aviso "Resolvido agora" no alto de Acompanhar sai (continua na conferência do Cadastrar).
- **3ª rodada: o título do cartão e a ficha completa** (usuária: "o titulo do card precisa tá mais claro, tipo:
  'Ajuste no campo XXXX no arquivo inteiro', 'Ajuste na informação do CNPJ'. E naquele card seria interessante um
  botão onde o usuário clica e vê a ficha completa... com os campos que o sistema já está considerando e com a
  informação que está sendo revisada em destaque"):
  - **o título vem do servidor** (`acompanhamento.titulo_do_cartao`), igual em Acompanhar, no Cadastrar e em
    Resolvidas: `Ajuste na informação "Estado civil" de Ana Lima`; `Conferir a informação "Valor da renda" de Ana
    Lima` (alerta; o valor fora da lista é sempre "Ajuste"); `... no arquivo inteiro`; `Ajuste no formato da coluna
    "Admissão" no arquivo inteiro`; `... de 4 pessoas` (grupo). O rótulo do campo à direita saiu;
  - **"Ver a ficha completa"** no cartão de uma pessoa (e em cada nome de "Ver quem são", no grupo):
    `GET /api/empresa/cadastro/{id}/ficha?linha=N` (`services/ficha_da_pendencia.py`) devolve os campos que o
    sistema está considerando (os que têm coluna no arquivo, mais os com pendência na linha), na ordem e nos grupos do
    parâmetro, com o valor já corrigido; os com pendência vêm marcados, com o que veio no arquivo. A janela destaca o
    campo do cartão ("Em revisão", "No arquivo veio: ...") e marca de leve os outros com pendência. Só a empresa dona
    do envio (404 para outra; o login é conferido antes da linha), e cada abertura fica registrada como a ficha dos
    cadastrados (LGPD).
- **Defeito corrigido: a pendência é regra + linha + CAMPO** (achado pela usuária no teste de 2026-09-28: "achei
  confuso como o agente tratou a resolução"). Desde o ADR-118, a pendência era identificada só pela regra e pela
  linha; mas a mesma regra aparece uma vez por campo na mesma linha (ex.: o arquivo sem 11 colunas obrigatórias gera
  11 `OBRIGATORIO_SEM_COLUNA` no arquivo inteiro; uma pessoa com dois obrigatórios vazios gera dois
  `OBRIGATORIO_VAZIO`). Os 11 cartões dividiam a mesma conversa e a mesma pergunta guardada (a da UF aparecia no
  cartão da matrícula), e o valor respondido podia ir para outro campo. Agora o campo entra na identidade em tudo: o
  pedido da conversa (`campo`), a busca do achado, a chave da conversa (`<envio>|<regra>|<linha>|<campo>`), a chave da
  pergunta guardada (as perguntas antigas são escritas de novo) e o grupo. O agente simulado (modo MOCK) passa a
  entender a resposta curta, sem pergunta, numa coluna que o arquivo não trouxe (ex.: "SP") como o valor para todos.
  Teste: `test_a_mesma_regra_em_campos_diferentes_nao_se_mistura`.
- **Um cartão, um problema** (usuária, 2026-09-28: "um card nunca pode tratar mais de um problema (pra facilitar a
  gestão e entendimento do especialista)... O CPF veio com problema... e depois fala... Esse cliente tbm apareceu no
  arquivo X"). O Validador prende "a pessoa repetida" e "a pessoa em outro arquivo" ao CPF (é por ele que acha a
  pessoa); por isso esses cartões se chamavam `Ajuste na informação "CPF" de Fulano`, igual ao do CPF inválido, e a IA
  recebia o CPF lido e falava dele. Agora: (1) cada cartão tem, embaixo do título, a linha **"Problema: ..."**, curta
  e só dele (`acompanhamento.problema_do_cartao`: ex. "CPF com o dígito verificador errado", "a pessoa também está
  em outro arquivo que ainda não foi ao banco ("folha_set.xlsx")"); (2) nas regras da pessoa inteira
  (`REGRAS_DA_PESSOA`), o título é `Ajuste no cadastro de Fulano`; (3) a IA que escreve a pergunta não recebe o CPF
  nem o nome da informação nessas regras (nem no id da pendência), e o prompt `pergunta_da_pendencia_v3` ganha a
  regra "cada pendência é UM problema: fale só do que está em o_que_aconteceu". Testes em
  `tests/test_ficha_da_pendencia.py` (títulos e problemas diferentes, a IA sem o CPF, toda pendência com o seu
  problema) e o roteiro `pendencias_em_grupo` (a linha "Problema:").
- **Arquivos diferentes com o mesmo nome ganham a versão** (usuária, 2026-09-28: "selecionei o arquivo aurora carga
  inicial e apareceu... o usuário X também está no arquivo aurora carga inicial que ainda não foi ao banco... no mesmo
  arquivo, não faz sentido"; "o sistema precisa identificar isso... marcar como v1, v2 e mostrar na tela para o
  usuário selecionar cada uma das versões"). A empresa tinha enviado dois arquivos diferentes com o mesmo nome; a
  regra estava certa (era o outro envio), mas o nome igual fazia parecer o mesmo arquivo. Agora
  `processamentos.nomes_na_tela` dá a cada envio o nome da tela: o nome que se repete na empresa (sem diferença de
  maiúsculas) ganha "(v1)", "(v2)"... pela ordem de chegada, contando todos os envios (os descartados e os que já
  foram ao banco também), para a versão de um arquivo nunca mudar depois. Vale no filtro de arquivos das pendências
  (`aurora_carga_inicial.xlsx (v2) · 3 pendências`), na linha de baixo do cartão, em Resolvidas, nos "Prontos para
  enviar ao banco" e na mensagem "a pessoa também está em outro arquivo ... ("aurora_carga_inicial.xlsx (v1)")". A
  mensagem guardada no relatório de um envio antigo muda na próxima validação dele. **O aviso já no envio:** a
  leitura do Cadastrar traz `aviso_do_nome` ('Você já enviou outro arquivo com o nome "x". Para não confundir, este
  aparece como "x (v2)" nas pendências e na lista para o banco.'), que a IA escreve entre as mensagens da leitura
  (também no envio de vários arquivos de uma vez). Teste: `tests/test_arquivos_com_o_mesmo_nome.py`.
- **A ficha não destaca o CPF nos problemas da pessoa inteira** (usuária, 2026-09-28): no cartão "a pessoa também
  está em outro arquivo", a ficha abria com o CPF "Em revisão". Agora cada pendência traz `campo_em_revisao` (None
  nas `REGRAS_DA_PESSOA`), a ficha não destaca nada nelas, e o CPF não ganha "Também com pendência" por causa delas.
- **Conversas gravadas com a chave antiga** (sem o campo) continuam lidas: em "Resolvidas", a chave de 3 partes vale
  para qualquer campo daquela regra e linha (sem isso, a rota quebraria com as conversas já guardadas). Teste:
  `test_conversa_gravada_com_a_chave_antiga_nao_quebra_as_resolvidas`.
- **Revisão do pedido (2026-09-28), duas travas contra misturar pendências:**
  - **Um valor que o sistema não entendeu não se confirma "como está"** (já era o desenho do ADR-118, rodada 3, para
    o valor fora da lista; faltava a trava). A confirmação de um alerta é guardada por regra e linha
    (`resolucoes_alerta`), sem o campo: confirmar o estado civil "Casdo" de uma pessoa fecharia junto o sexo "X"
    dela, se os dois fossem opcionais. Agora o agente explica ("O sistema não conseguiu entender esse valor, então
    ele não pode ser confirmado como está (se preferir, a informação pode ficar em branco). Qual é o valor certo?") e
    `validador.justificar_alerta` recusa essa regra também nas rotas antigas. Corrigir e deixar em branco já são
    por campo.
  - **O lote do Desfazer com a hora em microssegundos** (`correcoes._agora_do_lote`, no "Preencher para todos" e na
    troca em grupo): com a hora em segundos, duas respostas iguais no mesmo campo dentro do mesmo segundo viravam um
    lote só.
  Testes em `tests/test_pendencias_em_grupo.py` (`test_dois_lotes_iguais_no_mesmo_segundo_se_desfazem_separados` e
  `test_valor_nao_entendido_nao_se_confirma`).
- **A lista de envios mostra o nome do arquivo, com a versão** (usuária, 2026-09-28: "não enxergo a primeira versão do
  arquivo que está como v2 e na sessão dos envios não vejo o nome dos arquivos que foram enviados"). O "(v2)" aparecia
  nas pendências, mas a "(v1)" não aparecia em lugar nenhum: ela podia estar sem pendência, já no banco ou descartada, e
  a lista de envios não tinha o nome (passo 2 do ADR-69: "sem o nome do arquivo"). Agora cada envio da lista traz
  `nome_arquivo` (`processamentos.nomes_na_tela`) e o cartão o mostra no título ("folha_setembro.csv (v1)"), com o
  tipo, a data, quantos e quem na linha de baixo; os descartados continuam na lista, com o nome. **Altera** o passo 2
  do ADR-69 (os envios passam a mostrar o nome do arquivo). Teste:
  `test_a_lista_de_envios_mostra_o_nome_com_a_versao_mesmo_do_descartado` e o roteiro `arquivos_com_o_mesmo_nome`.
- **A dúvida de formato das datas repetia a pergunta** (usuária, 2026-09-28: "Respondi... As datas estão em dia/mês
  (DD/MM/AAAA)... o agente voltou a me perguntar a mesma pergunta na mesma conversa"). Dois defeitos:
  - **o agente simulado (MOCK) nunca entendia a escolha das datas:** ele procurava "dia/mes" com a barra, num texto
    já normalizado ("dia mes"); agora reconhece "dia mes"/"dd mm" e "mes dia"/"mm dd" (vale a ordem citada primeiro);
  - **a dúvida de formato não tinha campo** (a mesma raiz do "campo na identidade"): o Validador anotava
    `DATA_AMBIGUA` e `ZEROS_A_ESQUERDA` sem linha e sem campo, com a coluna só no texto. Com duas colunas de data em
    dúvida, os dois cartões dividiam a conversa, a resposta decidia a PRIMEIRA coluna (não a do cartão) e o agente
    emendava "Ainda há um problema:" com a mesma pergunta. Agora o Normalizador põe o campo da coluna na dúvida (há no
    máximo uma por campo) e o Validador o grava no achado; o agente nunca transforma uma dúvida de formato em "valor
    para todos". As padronizações de antes da correção continuam sem o campo até serem feitas de novo.
  Teste: `tests/test_duvida_de_formato_por_coluna.py`.

**Por quê.** A escada da usuária: assumir só o que é óbvio (degrau 1) ou o que a própria empresa já confirmou (degrau
3); no meio, perguntar **uma vez** para o grupo. A empresa continua decidindo, vê quem são e pode tratar exceções; o
Desfazer cobre o erro de entendimento.

**Trade-off.** Entre a resposta e o Desfazer, as N pessoas ficam com o valor escolhido; quem tinha uma exceção no meio
do grupo precisa abrir "uma a uma" antes de responder. Com 2 como mínimo, um par de pessoas já vira "2 pessoas com o
mesmo valor" (o número fica numa constante, fácil de subir).

**Como comprovamos.** `tests/test_pendencias_em_grupo.py` (9 testes): o grupo na lista (uma pendência por pessoa, o
mesmo grupo, a pergunta com o número e sem nome, `Sim, use "Casado" para as 3`); maiúsculas e espaços não separam;
campo livre, pessoa sozinha e arquivo inteiro não agrupam; a resposta vale para as três, com a trilha sem valor
pessoal, e o Desfazer volta as três (desfazer de novo é recusado); um valor da lista também vale para todas; "não
cadastrar" no grupo não muda nada; fora do grupo, vale só para a pessoa; o grupo desfeito responde só pela pessoa; a
conferência do Cadastrar marca o mesmo grupo; a pergunta da IA sem o número cai na reserva. Roteiro de clique
`pendencias_em_grupo` (um cartão para três, o número do alto igual ao do servidor, "Ver quem são", "Responder uma a
uma" e a volta, a resposta para as três com "Resolvido agora" e Desfazer, e o mesmo cartão nas três linhas da
conferência). 2ª rodada: `tests/test_conversas_das_pendencias.py` (7 testes: a conversa guardada com a pergunta vista
e a chave igual à da tela; pendência em aberto e conversa sem mudança não são resolvidas; o Desfazer tira da lista e
fica na conversa; o grupo é uma resolvida só; a confirmação de "não cadastrar" entra na conversa; envio descartado e
outra empresa sem resolvidas; a rota com 401, 403 e cada empresa só a sua), as falas novas nos testes do assistente,
a rota nova na varredura B-07 e no A-23 da bateria de segurança, e o roteiro `pendencias_em_grupo` ampliado (os dois
filtros, o cartão que fica até mexer em outro, "Resolvidas" com a conversa, depois do F5, e o Desfazer). 3ª rodada:
`tests/test_ficha_da_pendencia.py` (o título de cada caso; as pendências, o grupo e a conferência com o título; a
ficha com os campos considerados, o marcado e o valor lido, o valor já corrigido, o acesso registrado, linha fora e
outra empresa recusadas; a rota com 401, 403, 404 e 400), a rota da ficha no A-23, e os roteiros `pendencias_em_grupo`
e `pendencias_por_conversa` (títulos novos, a ficha com o destaque, o Esc, a ficha pelo nome no grupo).

**Altera** o ADR-118 (o cartão da pendência pode ser do grupo). **Próximo passo** (degrau 3): o dicionário aprendido
por empresa, entre empresas só com 2 confirmando a mesma troca (mesmo princípio do ADR-116). **Origem.** Pedido da
usuária, 2026-09-28.

<a id="adr-121"></a>

### ADR-121 · O especialista aponta problema por pessoa e aprova os outros, devolvendo só os apontados ✅

**Contexto (2026-09-28, pedido da usuária).** "Na tela Envios [...] tem dois filtros 'Todos' e 'Só com alerta ou
ajuste'... esses filtros não fazem sentido porque, quando chega nessa etapa, a empresa já fez os ajustes, e hoje o
especialista só tem a opção de devolver o envio inteiro. Poderíamos colocar em cada linha um campo para o especialista
indicar uma pendência específica por pessoa e, além de devolver o arquivo inteiro, devolver os funcionários que ele
indicou com problema [...] e, na linha do tempo, registrar essa volta de um jeito fácil de entender." Antes, o pedido de
ajuste de uma pessoa ia escrito no motivo da devolução do envio inteiro (o botão "Pedir ajuste" do protótipo ficava
escondido na aplicação). Além disso, a linha do tempo usava a primeira data de cada etapa: depois de uma devolução,
mostrava "Aprovação das contas enviadas" como a etapa atual, como se o envio estivesse com o banco.

**Opções.** (a) Devolver só os marcados, mas o envio inteiro volta e ninguém é aprovado antes; (b) aprovar as outras
pessoas na hora e devolver só as apontadas, no mesmo envio "meio aprovado"; (c) aprovar as outras na hora e mandar as
apontadas num **envio de devolução** novo, ligado ao de origem.

**Decisão (c), com as escolhas da usuária (respostas 1 a 4):**
- **Apontar problema** em qualquer pessoa do envio que espera o banco, com ou sem alerta: motivo de uma lista fechada
  (salário, CPF, nome, cargo, data de admissão, outro dado, pessoa que não parece ser da empresa, outro) e recado de 15
  a 400 letras. O apontamento fica em rascunho até a decisão; dá para trocar e desfazer
  (`services/apontamentos_do_banco.py`).
- **Três botões:** "Aprovar o envio" (sem apontamento); "Aprovar N e devolver M" (com apontamento, e não com todos); e
  "Devolver o envio inteiro" (com motivo; os apontamentos feitos viram pendências do próprio envio).
- **Aprovar N e devolver M:** as N são cadastradas na hora (a homologação deixa as linhas devolvidas de fora); as M vão
  para um envio de devolução (`services/devolucao_por_pessoa.py`), com os dados atuais delas, o mapeamento aprovado e
  as respostas que a empresa já tinha dado aos alertas. O fluxo dele começa parado na correção
  (`fluxo_empresa.comecar_na_correcao`), sem passar de novo pela leitura nem pela IA.
- **Na empresa,** cada apontamento é a pendência "Pedido do banco" da pessoa (regra `PEDIDO_DO_BANCO:<id>` do
  Validador, com as palavras do especialista, que a IA não reescreve). Ela corrige o campo (a pendência some, porque o
  valor mudou), responde que está certo (o banco lê a resposta) ou tira a pessoa. Depois manda de novo, pelo caminho de
  sempre.
- **Tirar a pessoa não volta ao banco para confirmar** (resposta 3): se não sobra ninguém no envio de devolução, ele se
  encerra sozinho, e isso fica nas idas e voltas.
- **Linha do tempo sempre para a frente:** "Enviado ao banco" mostra a última vez; a aprovação fica laranja com
  "Devolvido: 2 pessoas" (ou "o envio inteiro") até a empresa mandar de novo; no envio de origem, verde clarinho com
  "33 de 35 aprovadas · 2 devolvidas" (depois, "35 de 35 aprovadas" ou "34 de 35 aprovadas · 1 saiu do envio"). A
  história inteira fica no bloco **"Idas e voltas com o banco"**, igual nos dois portais (`services/idas_e_voltas.py`).
- **Na tela do banco:** filtros "Todos", "Confirmados pela empresa (N)" e "Apontados por você (N)"; o bloco "Respostas
  aos seus apontamentos" mostra o que a empresa fez com cada um ("corrigiu o salário: antes → depois", "respondeu",
  "tirou a pessoa do envio").
- O recado de devolução do envio inteiro continua à vista até a empresa mandar de novo (antes sumia na primeira
  correção).

**Porquê.** O objetivo do case é diminuir a desistência das empresas e abrir as contas: segurar 33 pessoas certas por
causa de 2 atrasa as contas e o salário de todas. O envio é a unidade de cadastro em todo o sistema (as situações
"Cadastrado", "Em análise" e "Pendente", o arquivo final do banco): com um envio novo para as devolvidas, nada disso
muda, e a opção (b) teria de reescrever todas as contas das telas. É o mesmo "envio-filho" estudado para o envio parcial
em `docs/proximos_passos.md`.

**Trade-off.** A empresa passa a ver um envio a mais na lista (o de devolução, com a linha "Devolução do envio de
28/09 (2 pessoas)"). O envio de devolução não refaz a padronização: se a empresa pedisse para reler as colunas nele, a
releitura partiria do arquivo inteiro (não acontece hoje, porque as decisões de coluna já vêm do envio de origem).

**Como comprovar.** `tests/test_devolucao_por_pessoa.py` (8 testes: apontar, trocar e desfazer; cada botão só na
situação certa; aprovar os outros e devolver o apontado, com a lista de funcionários, a pendência, a linha do tempo e as
idas e voltas; a empresa corrige e o banco aprova; a empresa responde que está certo; tirar a última pessoa encerra a
devolução; devolver o envio inteiro com apontamento; as rotas com 401, 403, 404 e 400) e os roteiros de clique
`devolver_por_pessoa_banco` e `devolver_por_pessoa_empresa`.

**Altera** o ADR-69 (a avaliação do banco ganha a aprovação em parte) e o ADR-114 (a pessoa devolvida volta a
"Pendente", no envio de devolução). **Origem.** Pedido da usuária, 2026-09-28.

<a id="adr-124"></a>

### ADR-124 · Informação de cada pessoa ou igual para todos: uma marcação do parâmetro, lida pelo Validador, pelo agente e pelo RAG ✅

**Contexto (2026-09-28, pedido da usuária).** Testando Acompanhar, a usuária viu o cartão 'Ajuste na informação "CPF"
no arquivo inteiro', com a pergunta 'Nenhum funcionário deste arquivo veio com a informação "CPF". Se for a mesma para
todos, qual é?'. Nas palavras dela: "CPF é uma informação única por cliente... nunca será igual pra base toda... assim
como qualquer informação do titular... únicas coisas no arquivo de parâmetro que podem ser igual pra todos são
Cadastro empresarial e Endereço comercial... isso precisa virar regra no arquivo de parâmetros e o validador precisa
considerar isso". O "Preencher para todos" (ADR-83) valia para qualquer campo obrigatório que o arquivo inteiro não
trouxe, e o agente (ADR-118) aceitava "o valor para todos é ..." em qualquer um deles.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · uma lista fixa no código | Rápido | Regra de negócio escondida no código; o banco não vê nem muda; cada layout novo pede programador |
| B · só uma frase no prompt do agente | Nenhuma mudança de dado | A IA pode esquecer; a tela, o Validador e o "Preencher para todos" continuariam aceitando |
| **C · uma marcação por campo no parâmetro ("Pode ser igual para todos"), versionada, que o Validador, a trava do agente, a frase da tela e o RAG leem** | O banco decide na tela Parâmetros; vale para qualquer campo novo; a trava é do código, não da IA | Mais uma coluna no parâmetro para o banco cuidar |

**Decisão.** C.
- **A marcação:** `CampoLayout.igual_para_todos` (S/N no `data/contratos/layout_v1.csv`; na tela Parâmetros, a
  coluna "Igual para todos" e a caixa "Pode ser igual para todos os funcionários do arquivo"). No layout v1, **só os
  dados da empresa**: `cnpj_empregador`, `cnpj_grupo`, `codigo_unidade`, `nome_unidade`, todo o endereço comercial e
  a `data_referencia_renda` (escolhas dela: o cargo, a admissão e a efetivação são de cada pessoa). O resto (o CPF, o
  nome, a matrícula, o nascimento, o endereço de casa, o cargo, a renda...) é de cada pessoa.
- **Versões antigas do parâmetro**, gravadas antes da marcação: vale a mesma lista (`parametros.IGUAIS_PARA_TODOS_POR_PADRAO`,
  `pode_ser_igual_para_todos`). O registro das alterações compara pelo valor que vale: a primeira gravação da tela
  depois da marcação não aparece como 45 mudanças; mudar a marcação aparece como as outras ("sim → não").
- **O Validador** (`OBRIGATORIO_SEM_COLUNA`): no dado da empresa, "Informar o valor uma vez, para todos (é um dado da
  empresa)"; na informação de cada pessoa, "O arquivo não traz este dado para nenhum funcionário, e ele é de cada
  pessoa" e "Enviar o arquivo de novo com esta coluna".
- **As travas no código:** `correcoes.preencher_para_todos` recusa a informação de cada pessoa ('A informação "CPF"
  é de cada pessoa e não pode ser a mesma para todos...'), e o agente também (`_nao_serve_para_a_pendencia`, que
  explica e aponta o botão "Descartar a leitura e enviar outro arquivo"): a pendência leva `igual_para_todos` para o
  agente e a regra 9 do prompt `assistente_correcao_v3` diz o mesmo, mas quem garante é o código.
- **A fala e o cartão:** a pergunta de reserva diz 'O arquivo não trouxe a informação "CPF", que é de cada pessoa e não
  pode ser a mesma para todos. Quer enviar o arquivo de novo com essa coluna?'; a da IA (prompt
  `pergunta_da_pendencia_v3`, regra 8) só passa na conferência com "cada pessoa" na frase; a chave da pergunta guardada
  mudou, para a frase antiga ("Se for a mesma para todos") não voltar. A resposta rápida do cartão é o botão
  **"Descartar a leitura e enviar outro arquivo"**, que abre a mesma janela de descarte do rodapé (a empresa confirma)
  e, descartado, a janela "Cadastrar funcionários".
- **O RAG:** o trecho de cada campo diz "Pode ser o mesmo para todos os funcionários do arquivo (dado da empresa)." ou
  "É de cada pessoa: nunca é o mesmo para todos os funcionários do arquivo.", e a regra "Informação de cada pessoa ou
  igual para todos" entra em `data/contratos/regras_v1.json` (19 regras). A tela Parâmetros refaz o índice ao gravar.

**Quando o valor não é o mesmo para todos (2ª rodada, 2026-09-28).** A usuária perguntou: "Quando a IA perguntar...
essa informação é a mesma pra todos e ele falar que não é... qual a alternativa de correção para o usuário?". Hoje não
havia saída no cartão: o agente simulado perguntava de novo "Qual é o valor para todos?" (um laço), a IA real não
tinha instrução para o caso, e a conferência do Cadastrar só corrige as colunas que vieram no arquivo. Opções: A ·
enviar de novo, com a coluna; B · informar pessoa a pessoa, numa lista do cartão; C · enviar só a coluna que faltou,
juntada ao envio pelo CPF; e a que não se recomenda, usar o valor da maioria e corrigir as exceções depois (elas
ficariam erradas sem cartão). **Decisão da usuária: A + B.** C fica para depois da POC (`docs/proximos_passos.md`): ela
depende de uma chave confiável, e só vale com todos os CPFs do envio válidos e sem repetição (a dúvida dela: "quando o
cpf vier inconsistente... não teríamos uma chave por pessoa confiável").
- **O cartão da coluna que falta** oferece "Informar pessoa a pessoa" e "Descartar a leitura e enviar outro arquivo";
  no dado da empresa, antes deles, **"Não é a mesma para todos"**, e o agente mostra os dois caminhos sem mudar nada
  (o agente simulado entende a frase; a IA real, pela regra 10 do prompt `assistente_correcao_v3`). A pergunta da
  informação de cada pessoa passa a ser '... Quer informar pessoa a pessoa ou enviar o arquivo de novo com essa
  coluna?'.
- **A lista pessoa a pessoa:** a chave de cada pessoa é a **linha do arquivo** (a mesma de toda correção), não o CPF,
  que pode estar faltando ou errado; o nome (que abre a ficha), a matrícula e a linha servem para reconhecer quem é.
  "Usar nos marcados" (o mesmo valor em várias pessoas) só no dado da empresa. O CPF informado passa pelas regras do
  CPF (dígito, repetido no arquivo, em outro envio).
- **Salvar** (`POST /api/empresa/cadastro/{id}/informar_por_pessoa`, com `GET .../pessoas_para_informar?campo=` para a
  lista): um valor por pessoa, num lote com um Desfazer só (`correcoes.informar_por_pessoa`, tipo `por_pessoa`), na
  trilha `CORRECAO_POR_PESSOA` com o campo e quantos, sem valor; é uma rodada da conversa do cartão ("Pronto: informei
  "Código da unidade" de 3 pessoas: Ana, Bia e Caio."), que vai para "Resolvidas". Quem fica em branco ganha o seu
  cartão (a coluna passa a contar como presente). Um valor que não serve não grava nada, e a mensagem diz a linha e o
  nome.

**A informação que faltou está em outra coluna (3ª rodada, 2026-09-28).** No cartão do CPF sem coluna, a usuária
respondeu "Na verdade o campo matrícula é o CPF" e recebeu "Aqui eu só ajusto a informação CPF": a trava da conversa
só aceitava a coluna do próprio campo (e o CPF não tinha nenhuma), e o agente simulado tratava "matrícula" como outro
assunto. Ela pediu que o sistema veja se a coluna já é usada em outro campo (que precisa ser revisto), confira os
valores com as regras do campo (no CPF, o dígito verificador) e decida por essa conferência. **Decisões dela:** a troca
acontece na hora, em Acompanhar (o "Sim" vale como o aceite dessa coluna), e só quando a **maioria** dos valores passa.
- **A ação `usar_coluna`** (prompt `assistente_correcao_v3`, regra 11): só no cartão da informação que o arquivo
  inteiro não trouxe; a coluna vem pelo nome ("a coluna Registro é o CPF") ou pelo campo que ela alimenta hoje ("a
  matrícula é o CPF": o pedido à IA leva o mapeamento atual). A trava recusa a ação nos outros cartões.
- **A conferência** (`services/coluna_do_campo_que_falta.conferir`): a mesma da tela de colunas
  (`normalizador.conferir_valores_para_o_campo`), com o **dígito verificador** do CPF e do CNPJ (`conferir_digito`).
  A conversa diz o resultado ('Conferi a coluna "Registro" (hoje lida como "Matrícula") com as regras de "CPF", com o
  dígito verificador: 35 de 35 valores passaram.'), o que muda ('"Matrícula" fica sem coluna e ganha um cartão de revisão') e
  pergunta, com **"Sim, usar como CPF"** e "Cancelar". Sem a maioria, nada é oferecido, e a conversa lembra os dois
  caminhos.
- **A troca** (`usar_coluna`, rota `POST /api/empresa/cadastro/{id}/assistente/usar_coluna`): o servidor confere tudo
  de novo, troca o campo da coluna sem a IA (`mapeamentos.trocar_o_campo_da_coluna`, trilha
  `COLUNA_TROCADA_NA_CONVERSA` com a coluna e os campos, sem valores) e refaz a leitura pelo caminho de sempre do aceite
  (`cadastro.aceitar_mapeamento`: padronização e conferências; as decisões de formato já tomadas continuam). O CPF que
  não passou vira um cartão de revisão de cada pessoa; o Desfazer (tipo `coluna`) volta a coluna para o campo de antes. "Cancelar"
  fica na trilha (`COLUNA_RECUSADA_PELA_EMPRESA`). Vale para qualquer informação que faltou, com as regras dela.
- **Diferente do handoff ao Interpretador** (ADR-17): lá, a empresa diz que a coluna do campo foi mal entendida, e a IA
  relê a coluna (o mapeamento volta ao aceite); aqui, o campo é o da pendência e foi dito pela empresa: a conferência é
  determinística, e a IA não precisa reler.

**Por quê.** A regra é do negócio do banco (o que o layout aceita), então mora no **parâmetro**, onde o banco a vê e
muda, e não no código nem só no prompt. A IA **lê** a regra (RAG e prompt) para conversar bem, mas quem **garante** é
o código (Validador e travas), como nas outras regras (ADR-118: a IA decide a conversa, o código decide o dado).
Generalizar é acrescentar marcações ao parâmetro, não código por campo.

**Trade-off.** A empresa não pode "tapar" o CPF de todos, mesmo com pressa: ou informa pessoa a pessoa, ou manda o
arquivo de novo. Num arquivo grande, a lista pessoa a pessoa é trabalhosa (o caminho é enviar de novo). A marcação é
mais uma decisão do banco na tela Parâmetros; errada (ex.: o CPF marcado como "igual para todos"), o sistema aceitaria
o mesmo valor para todos, e o registro das alterações mostra quem marcou.

**Como comprovamos.** `tests/test_parametros_e_catalogo.py` (o v1 com os 12 campos; a lista padrão numa versão antiga
e a marcação mandando; S/N/vazio no arquivo; o registro sem mudança falsa), `tests/test_validador.py` (a mensagem e a
ação de cada caso), `tests/test_preencher_para_todos.py` (o CPF recusado, nada gravado),
`tests/test_assistente_na_tela.py` (a conversa com o CPF sem coluna não aplica nada e explica; o botão do cartão),
`tests/test_pergunta_da_pendencia.py` (a frase de reserva), `tests/test_perguntas_das_pendencias.py` (a conferência
da frase da IA e a chave nova), `tests/test_rag.py` (o trecho do CPF e o do CNPJ) e
`tests/test_acompanhamento.py::test_api_preenche_para_todos_so_na_propria_empresa` (400 na admissão, 200 num dado da
empresa). Roteiros `pendencias_em_grupo` (a data de nascimento sem coluna com "de cada pessoa" e o botão, a janela de
descarte, o CNPJ pedindo o valor uma vez, o descarte de ponta a ponta) e `parametros` (a coluna nova, sem mudança falsa
no registro). 2ª rodada: `tests/test_informar_pessoa_a_pessoa.py` (9 testes: as respostas rápidas de cada caso; "Não é
a mesma para todos" sem mudar nada e sem o laço; a lista pela linha, sem CPF no arquivo; o CPF pessoa a pessoa com a
trilha sem valor, a conversa em "Resolvidas" e o Desfazer; quem fica em branco ganha um cartão de revisão; o mesmo CPF em duas
pessoas vira pendência; valor que não serve não grava nada; as recusas; as rotas com 401, 403, 404 e 400), as duas
rotas na varredura A-23 da segurança e o roteiro `pendencias_em_grupo` ampliado ("Não é a mesma para todos", a lista
do código da unidade com "Usar nos marcados", o "Pronto" e o cartão de quem ficou em branco). 3ª rodada:
`tests/test_coluna_do_campo_que_falta.py` (8 testes: a conferência com o dígito do CPF e o campo de hoje; "a
matrícula é o CPF" e "a coluna Registro é o CPF" viram a proposta, sem mudar nada; a coluna que não parece CPF não é
oferecida; o "Sim" troca, refaz a leitura, registra na trilha e o Desfazer volta; "Cancelar" não muda nada; a trava
nos outros cartões; a rota com 401, 404 e 200), a rota no A-23 e o roteiro novo `coluna_do_campo_que_falta`.

**Altera** o ADR-83 (o "Preencher para todos" vale só para o dado da empresa). **Origem.** Pedido da usuária,
2026-09-28.

<a id="adr-122"></a>

### ADR-122 · Portal Interno reorganizado: Conversa e Contas abertas na ficha da empresa, Indicadores e Configuração ✅

**Contexto.** Pedido da usuária (2026-09-28): "Quero que a ordem do menu da visão do especialista seja Inicio,
Empresas, Envio. A parte de mensagem pode ser migrada para a própria aba da empresa [...] uma aba chamada "Conversa".
Contas abertas tbm precisa ser migrado pra lá, pq aí o especialista vai subir um arquivo de contas aberta por empresa.
É importante que ao subir o arquivo tenhamos um campo que identifique que aquele arquivo realmente é daquela empresa
[...]. A parte de planejamento & Telemetria deveriam se juntar [...]. E parametros deveria subir para uma engrenagem na
parte de cima, escrito configuração". O menu tinha 9 abas (Início, Empresas, Endomarketing, Envios, Mensagens, Contas
abertas, Telemetria, Planejamento, Parâmetros), e o arquivo de contas abertas era um só para a carteira inteira.

**Opções para provar que o arquivo é da empresa.** (a) Uma coluna `cnpj_empresa` em cada linha; (b) o CNPJ digitado na
tela antes de subir; (c) os dois.

**Decisão (a) e o menu novo, todas pela recomendação:**
- **Menu:** Início · Empresas · Envios · Endomarketing · Indicadores. O número de mensagens sem resposta passa para a
  aba Empresas, e cada empresa da lista ganha um selo com as suas.
- **Ficha da empresa** (`banco_empresas.html?empresa=<id>&aba=<aba>`): Visão geral, **Conversa** (tudo o que a tela
  Mensagens fazia, para a conversa daquela empresa), **Contas abertas** (orientação, botão "Carregar Contas Abertas" e
  o histórico da empresa), Dados, Usuários, Catálogo de benefícios e Kit de endomarketing.
- **Arquivo de contas por empresa:** o layout fixo do ADR-119 ganha a 1ª coluna `cnpj_empresa` (cabeçalho
  `cnpj_empresa;cpf;codigo_banco;agencia;conta;data_abertura`). Toda linha precisa trazer um CNPJ desta empresa
  (principal, filial ou grupo, ADR-77), e cada CPF precisa estar Cadastrado **nesta** empresa; senão, o arquivo inteiro
  é recusado (tipos novos `cnpj_invalido` e `cnpj_de_outra_empresa`; `cpf_nao_cadastrado` diz se o CPF está em outra
  empresa). A orientação fica escrita na aba e na janela. Rotas: `GET /api/banco/empresas/{id}/contas/layout`,
  `POST /api/banco/empresas/{id}/contas/conferir` e `GET /api/banco/empresas/{id}/contas/historico` (saem as rotas da
  carteira inteira); confirmar e descartar continuam por arquivo. `arquivos_de_contas` ganha `empresa_id`, e os arquivos
  antigos, sem empresa, não entram no histórico de nenhuma.
- **Indicadores** (`banco_indicadores.html?aba=painel|consultor`), o lugar para avaliar os números da carteira, com
  duas guias (2ª rodada, depois do 1º teste da usuária: "toda a parte de Planejamento (a parte fixa do relatório) + a
  parte do Uso das empresas deveria virar um relatório só... Tipo... Dash de acompanhamento"):
  - **Painel de acompanhamento:** um relatório só, na ordem números do alto (uso do portal e planejamento das contas),
    onde as empresas travam (funil e linha do tempo), potencial (ganho projetado em 12 meses, por empresa e por região)
    e o uso do portal por empresa. As duas tabelas por empresa ficam separadas, porque medem coisas diferentes (o
    potencial obedece aos filtros e só tem empresas com cadastro aprovado; o uso é a carteira inteira);
  - **Converse com o Consultor:** o agente Consultor na guia inteira, com o que ele responde e o que não faz (nunca
    listas de pessoas). O nome mantém o do agente (escolha da usuária entre "Converse com o Consultor", "Pergunte ao
    Consultor" e "Consultor estratégico").
- **Configuração:** uma engrenagem com a palavra "Configuração", no topo, ao lado do usuário, abre um menu com
  **Parâmetros do layout** (`banco_parametros.html`) e **Acompanhamento dos agentes** (`banco_agentes.html`). Esta tela
  reúne o que era a sub-aba "Desempenho da IA" (custo e uso, qualidade EXP-008, experimentos, execuções recentes) e,
  no alto, **um cartão por agente de IA** na ordem do fluxo (Leitor de documentos, Conferidor da leitura,
  Interpretador, Assistente de Correção, Agente de validação, Endomarketing, Consultor): o que ele faz, quantas vezes
  trabalhou, quantas deram certo, com erro ou barradas pelo guardrail, com IA real × simulada, duração média, última
  execução e custo ("não medido" quando nada foi medido). O Consultor conta as perguntas, não as ferramentas de cada
  resposta. O Leitor e o Conferidor ainda não gravam em `execucoes_agentes`: o cartão diz que o trabalho deles ainda não
  é registrado (nunca "Ainda não trabalhou", que seria falso). Rota: `GET /api/banco/telemetria/ia`, que ganhou
  `cartoes_por_agente`.
- Saem as telas `banco_mensagens.html`, `banco_contas.html`, `banco_telemetria.html` e `banco_planejamento.html`.
- **3ª rodada** (depois do 2º teste da usuária):
  - **Tempo até a avaliação do banco:** o cartão do uso passa a ter a média em dias úteis (segunda a sexta, no horário
    de Brasília; feriados ainda contam, e a legenda avisa) entre o envio da empresa ao banco e a decisão do banco
    (aprovar ou devolver), só dos envios já decididos, com as datas que a auditoria já gravava;
  - **Busca por CNPJ no funil:** acha a empresa por qualquer CNPJ dela (principal, filial ou grupo), com ou sem
    pontuação;
  - **Simulador no "Quanto a carteira pode render":** as premissas ficam à vista e cada uma é editável só na simulação,
    com "Voltar às premissas oficiais"; salvar pede um nome e guarda os próprios valores;
  - **Premissas financeiras oficiais** viram o 3º item da engrenagem Configuração (`banco_premissas.html`): a vigente,
    a nova versão oficial (com confirmação) e o registro de cada versão (quem, quando, de → para). Palavras dela:
    "lá no menu de configuração o especialista deveria conseguir salvar as novas premissas oficiais (com registro de
    log)";
  - **Acompanhamento dos agentes:** filtro por período (7, 30 ou 90 dias, tudo, ou de/até) e a **aceitação** de cada
    agente (aprovadas sem mudança, corrigidas e recusadas, com o percentual), explicada na tela como a acurácia na
    operação, diferente da acurácia contra gabarito dos experimentos; "não medido", com o porquê, quando não há dado
    (Consultor: ninguém avalia as respostas; Agente de validação: ele não sugere a resposta). O Leitor de documentos e
    o Conferidor da leitura passam a gravar cada trabalho em `execucoes_agentes`. A linha do tempo dos experimentos vai
    até o EXP-015 e a nota do modelo fala do plano B do ADR-107;
  - a regra da base do banco e do tipo de conta ficou no **ADR-123**.
- **4ª rodada** (depois do 3º teste da usuária: "Tira o campo de cnpj e empresa do funil e coloca um filtro no inicio
  do relatório que filtra a empresa (nome e cnpj)... uma vez selecionado ele deveria adaptar toda a visão de
  indicadores para aquela empresa, coloca o filtro de estado tbm e no planejamento de conta pode tirar os filtros que
  estão lá tbm / A parte de simulação deixa no Menu dentro dos indicadores [...] No simulador é necessário escolher a
  empresa (via nome ou CNPJ) pra fazer uma simulação ou todas... E aí o sistema mostra as aberturas de potencial de
  contas novas, correntistas (ativo, inativo) e etc."):
  - **um filtro só, no alto do Painel de acompanhamento**: a empresa (pelo nome, um pedaço dele ou qualquer CNPJ dela,
    com ou sem pontuação) e o **estado**, valendo para o relatório inteiro (números do uso e do planejamento, funil,
    linha do tempo e as duas tabelas). O estado é a UF da **sede** no uso do portal (medido por empresa) e a da
    **unidade de trabalho** no planejamento (a regra das análises); a nota do filtro diz isso. A escolha fica no
    endereço (`?empresa=&uf=`). Saem a escolha da empresa e a busca por CNPJ do funil, e os filtros próprios do
    planejamento (empresa, região e data de referência);
  - **Indicadores com três guias:** Painel de acompanhamento · **Simulador de Rentabilidade** · Converse com o
    Consultor (`?aba=painel|simulador|consultor`);
  - **no simulador**, a empresa da simulação (nome ou CNPJ, ou todas) e a tabela **"De onde vem o ganho"**: no
    realizado, as contas novas, os correntistas ativos e os inativos; no potencial, quem aguarda e deve ser correntista
    e quem aguarda e deve virar conta nova (pessoas estimadas, com uma casa). As somas batem com o ganho total
    (`services/planejamento.py`, `aberturas_do_ganho`). A simulação salva guarda a empresa, e "Reabrir" volta a ela.
    **Substituído na 5ª rodada** pelo Simulador de Rentabilidade do ADR-123 (base de clientes × três taxas).

**Porquê.** O especialista trabalha empresa por empresa: a conversa, as contas e o cadastro de uma empresa ficam no
mesmo lugar. A coluna de CNPJ prova, pelo próprio conteúdo, que o arquivo é daquela empresa (digitar o CNPJ na tela
não provaria nada sobre o conteúdo); e o CPF preso à empresa impede dar baixa numa empresa com o arquivo de outra.

**Trade-off.** Um arquivo por empresa: o banco precisa gerar o arquivo separado (ou filtrá-lo) e o especialista sobe um
por empresa. A visão da carteira inteira das conversas deixou de ser uma tela: fica o número no menu e os selos da lista.

**Como comprovar.** `tests/test_contas_abertas.py` (CNPJ certo, de filial ou grupo, de outra empresa, inválido, coluna
faltando, CPF de outra empresa, histórico por empresa, 401/403/404, rotas antigas fora); os roteiros de clique
`menu_do_portal_interno`, `conversa_na_ficha_da_empresa`, `carregar_contas_abertas`, `prazo_das_mensagens`,
`parametros`, `painel_de_indicadores` (com o filtro do alto e o simulador), `acompanhamento_dos_agentes`,
`premissas_financeiras` e `sem_exemplos_no_portal_interno`; `tests/test_tempo_e_cnpj_do_uso.py`;
`tests/test_cartoes_dos_agentes.py` (ordem, nomes juntados, agente sem execução, Leitor e Conferidor sem registro,
erro/bloqueado, real × simulada, custo só quando medido, 401/403).

**Altera** o ADR-119 (layout e onde o arquivo é carregado) e o desvio de 2026-09-25 (a sub-aba "Desempenho da IA"
vira a tela "Acompanhamento dos agentes", no menu da engrenagem Configuração). **Origem.** Pedido da usuária,
2026-09-28 (quatro rodadas).

### ADR-123 · O arquivo de contas é a fonte sobre o funcionário: sai a base do banco; tipo de conta e situação do correntista ✅

**Contexto.** Pedido da usuária (2026-09-28, 3ª rodada do ADR-122): "Precisamos definir uma regra quando o banco for
enviar o arquivo de contas abertas: Se for uma nova conta precisa vir com a informação de nova conta e se o funcionário
já era um correntista precisa vir informado isso.. tipo: 1 - Nova Conta, 2 - Correntista ... essa orientação precisa
estar no formulário de envio... dessa forma conseguimos gerar com confiança a marcação de contas abrir, correntistas a
reconhecer (marcação de folha) e correntistas ativos. Nessa versão pode tirar a visão de correntistas que autorizam
contato". Perguntada sobre o que fazer quando o tipo do arquivo não batesse com a base do banco: "Teoricamente...
estamos tirando essa base do banco e a informação que o sistema vai enxergar do funcionário é o csv que o banco
devolve". Sobre "correntistas ativos": "tem o cliente que é ATIVO no banco e INATIVO... (Podemos indicar no arquivo
ATIVO E INATIVO... mas isso só pode aparecer para o especialista do banco, nunca pra empresa)". Até aqui, o motor de
planejamento (ADR-25) classificava cada funcionário homologado cruzando o CPF com a base oficial fictícia do banco
(`base_banco.csv`: correntista, segmento, `autoriza_oferta_ativa`).

**Opções.** (a) A base continua prevendo quem é correntista na homologação, e o arquivo confirma e prevalece;
(b) só o arquivo: a base sai, e cada Cadastrado fica aguardando o retorno do banco até o arquivo dizer o tipo.

**Decisão (b), "Só o arquivo":**
- **A base do banco sai do motor.** Cada funcionário homologado fica **aguardando o retorno do banco**.
- **O arquivo de contas ganha três colunas** (layout fixo do ADR-119, por empresa no ADR-122):
  `cnpj_empresa;cpf;codigo_banco;agencia;conta;data_abertura;tipo_conta;situacao_correntista;folha_ja_identificada`.
  `tipo_conta`: `1` = Nova conta, `2` = Correntista (a conta que ele já tinha). `situacao_correntista`: `ATIVO` ou
  `INATIVO`. `folha_ja_identificada`: `S` (a folha do correntista já era identificada pelo banco) ou `N` (não era: é o
  **falso não folha**, o ponto central do business case). As duas últimas são obrigatórias no tipo 2 e vazias no tipo
  1; qualquer outro valor recusa o arquivo inteiro. Palavras dela sobre a folha: "Para os correntistas o banco também
  deveria informar (folha estava identificada anteriormente ou Não... pq com isso conseguimos a marcação do grande
  ponto do projeto.. os clientes que estão com a gente e não identificamos como folha)". A orientação está escrita na
  aba Contas abertas da ficha da empresa e na janela de envio.
- **Planejamento:** Cadastrados · Aguardando retorno · **Falso não folha recuperados** (em destaque, ativos ×
  inativos) · Contas novas (informativo) · Correntistas que já eram folha (sem ganho novo, ativos × inativos). O banco **sempre** informa o tipo (palavras dela: "ele sempre informa o status,
  ou seja, se é conta aberta, se é correntista e etc... nunca deveria vir vazio"): tipo vazio recusa o arquivo, e uma
  conta gravada antes da coluna do tipo conta como **aguardando retorno** (o status dela ainda não foi dito); quando
  ela vier de novo num arquivo, ganha o tipo (aprovado pela usuária). Não há um número de "retorno sem o tipo".
- **Ganho** (estimativa, não receita; palavras dela: "O falso não folha gera ganho e os clientes com conta nova tbm.
  O falso não folha é a premissa do nosso BC e conta nova informativo no sistema já que o sistema vai ter a visão do
  todo"): **realizado** = falso não folha **ativo** × (MOB folha − MOB não folha) + contas novas × MOB de cliente
  novo; quem já era folha e o **inativo** não somam (6ª rodada: "Hoje já sabemos que esse cliente tem conta com a
  gente, mas na simulação ele não trás rentabilidade nenhuma"; o ativo "ou é um folha e traz o mob maior ou é um folha
  não identificado e traz um mob menor"). O **potencial** é do Simulador de Rentabilidade (abaixo).
- **Simulador de Rentabilidade** (5ª rodada, pedido da usuária em 2026-09-28: "o correntista ele não trás
  rentabilidade, a nova conta traz a rentabilidade do correntista e o folha identificado a diferença do que ele não
  trazia"). A guia de Indicadores tem seções, e os campos que dependem da especialista têm a cor de destaque:
  1. a empresa (nome ou CNPJ) ou todas;
  2. as premissas globais oficiais (horizonte e os 3 MOB), **travadas**;
  3. o ajuste delas **só nesta simulação** (vazio = vale a oficial);
  4. os clientes que a empresa enviou (cadastrados + em análise pelo banco), **travados**;
  5. a **estimativa de clientes** da especialista, que **substitui** os enviados (escolha dela);
  6. as **taxas estimadas** (6ª rodada): % novas contas, % correntista (não folha), % correntista (folha) e % ativos
     entre os correntistas (a % correção de folha saiu);
  7. o resultado, refeito a cada ajuste;
  8. o que o banco já confirmou, **à parte, como referência** (com as taxas observadas, inclusive a % folha e a %
     ativos, e o realizado; escolha dela).

  A conta (`planejamento.simular_rentabilidade`): base × % novas contas × MOB cliente novo + base × % não folha ×
  % ativos × (MOB folha − MOB não folha); o correntista folha (já traz o MOB maior), o inativo e o resto da base não
  rendem nada novo. As três partes da base (novas contas, não folha e folha) não passam de 100%. As taxas existem
  **só na simulação**, sem
  valor oficial nem padrão (escolha dela: "Só na simulação"): sem uma delas, a simulação diz o que falta. Por isso as
  premissas oficiais voltam a ser só o horizonte e os 3 MOB (saem as duas % da 3ª rodada, e a taxa de conquista sai
  do simulador). Os clientes enviados vêm de uma rota própria (`GET /api/banco/planejamento/base`), pedida uma vez por
  empresa, porque contar os em análise monta a lista inteira de funcionários; a tela manda esse número em cada
  simulação. A simulação salva guarda a empresa, os valores, a base (número e origem) e o resultado; na lista das
  salvas, **"Visualizar"** (7ª rodada) abre uma janela com ela inteira (quem, quando, empresa, total, base,
  premissas, taxas e a rentabilidade por grupo), sem mexer no simulador, e "Reabrir" a põe nos campos, sobe a tela até o início do
  simulador e mostra a etiqueta "Simulação salva: <nome>" (8ª rodada), que avisa "com ajustes não salvos" quando algo
  muda depois.
- **O Consultor**, até o pedido "consultor-modelo-novo" (escolha dela: "Depois, num pedido próprio"), responde só o
  realizado e diz que o potencial se calcula no Simulador de Rentabilidade; as ferramentas mantêm o contrato de hoje.
- **O que a empresa vê** (pedido da usuária, 2026-09-28, escolhida "Mostrar o tipo"): a situação do funcionário
  passa de "Cadastrado" para **"Conta aberta"** (tipo 1) ou **"Já é correntista"** (tipo 2), as duas com o código do
  banco, a agência, a conta e a data, para pagar o salário; o cartão de Acompanhar diz "X de Y já têm conta no banco
  (P%): N abriram a conta agora e M já eram correntistas"; o Início diz quantos estão "ainda sem conta informada pelo
  banco". A situação ATIVO/INATIVO e a folha já identificada (o falso não folha) continuam só no Portal Interno
  (escolha dela: "Só o banco"): nenhuma rota da empresa as devolve (teste).
- **Uma conta só** (escolhida pela usuária): `contas_abertas.retorno_da_empresa` classifica cada Cadastrado com a
  MESMA regra do painel de Indicadores (`planejamento.classificar`) e alimenta o cartão e o Início da empresa, a lista
  de funcionários, a linha do tempo do envio, a carteira, o Início e a Visão geral do banco, a prévia do arquivo e a
  sugestão do Endomarketing. O teste `test_o_mesmo_numero_em_todas_as_telas` prova que os números batem.
- **Sai** "correntistas que autorizaram contato" e o filtro de segmento, que vinham da base.

- **A limpeza do banco de dados é um script de uma vez só** (`scripts/tirar_a_base_do_planejamento.py`), rodado na
  junção, antes de religar a porta 8000: apaga a visão `resumo_planejamento` e as colunas `classificacao`,
  `autoriza_contato` e `segmento`. Não é uma migração automática porque o banco de dados é um só para todos os
  servidores, e a versão anterior, no ar, ainda as lê.

**Porquê.** O retorno do banco é a informação confirmada sobre cada funcionário; uma base prevista em paralelo criaria
dois números para a mesma pessoa. Com o tipo no arquivo, o banco marca com confiança as contas abertas e as folhas
reconhecidas (o "falso não folha" recuperado), e o especialista vê quem é ativo ou inativo.

**Trade-off.** Antes do arquivo, o sistema não sabe quem é correntista: o potencial depende das taxas estimadas pela
especialista (as taxas observadas do retorno servem de referência). Sai o filtro por segmento. Até o pedido
"consultor-modelo-novo", o Consultor não simula o potencial.

**Como comprovar.** `tests/test_contas_abertas.py` (tipo e situação: cada divergência trava; contagens; a empresa nunca
vê a situação), `tests/test_planejamento.py` (motor sem a base; resumo pelo retorno; realizado conferido à mão; a
simulação conferida à mão, 312 clientes com 30% / 40% / 20% e 75% ativos = R$ 229.997,66; o realizado só com o
falso não folha ativo; sem taxa a simulação espera; os valores
recusados; a base = cadastrados + em análise; a simulação salva; `test_o_mesmo_numero_em_todas_as_telas`),
`tests/test_premissas_oficiais.py` (as taxas não entram na versão oficial), roteiros `carregar_contas_abertas`,
`grade_de_funcionarios` ("Conta aberta" e "Já é correntista" na lista e no filtro), `painel_de_indicadores` (o
simulador em seções, a cor de destaque, "Falta informar", a estimativa, a referência, o botão "Voltar às
premissas oficiais" menor e à direita, e "Reabrir") e
`premissas_financeiras`.

**Altera** o ADR-25 (o motor não cruza mais a base oficial), o ADR-119 e o ADR-122 (layout do arquivo) e a premissa de
negócio de 2026-09-23 (oferta ativa só para correntista com autorização, com a base fictícia marcando `correntista` e
`autoriza_oferta_ativa`): nesta versão não há base nem oferta ativa, e o motor continua só com números agregados, sem
listas de pessoas. O desvio entra na tabela do `CLAUDE.md` pelo orquestrador, com a confirmação da usuária.
**Origem.** Pedido da usuária, 2026-09-28.

### ADR-125 · Repositório de KBs de endomarketing, com trava, versões e a vitrine só com as publicadas ✅

> **Alterado pelo [ADR-147](#adr-147) (2026-09-30):** a trava deixa de chamar a IA (a segunda opinião) ao salvar a KB.
> A frase de ordem para a IA é conferida só pela lista, como no kit de marca e na carga dos arquivos.

**Contexto (2026-09-28, pedido da usuária ao agente construtor).** "Quero que você construa KBs de endomarketing
simulando benefícios que o banco pode oferecer [...] isenções, taxas, cartões, pontos e programa de relacionamento [...]
de prateleira do site público do Santander [...] padronizadas [...] numa tela de benefícios do painel na visão do
especialista [...] organizadas por empresa [...] jornada de contratação, LPs [...] KBs gerais que falem do tom de voz,
termos proibidos e diretrizes [...] e o KIT da marca de cada empresa e do Santander." Depois: guardrails com trava e o
registro do que ela aponta, consultável na Telemetria; telas para cadastrar, editar e revisar KB vencida; a vitrine da
empresa e o kit escolhido vindos das KBs; "na vitrine de benefícios da empresa, só deveria considerar KBs de benefícios
publicadas". Antes, o conhecimento do agente era um documento Markdown por empresa (o catálogo, ADR-19), subido à mão,
sem modelo fixo, sem tom de voz, sem termos proibidos e sem kit de marca descrito.

**Opções.** (a) Continuar com um documento livre por empresa; (b) KBs só em arquivos do projeto, sem tela;
(c) **um repositório de KBs padronizadas no banco de dados, com versões e situação, carregado dos arquivos na primeira
vez, com uma tela de gestão e uma trava automática**.

**Decisão (c):**
- **Modelo único** (`data/kbs_endomarketing/MODELO.md`): uma ficha (`id`, `titulo`, `tipo`, `dono`, vigência, `origem`
  e, conforme o tipo, `categoria`, `prateleira`, `kit_escolhido`, `cores`, `logo`) e as seções obrigatórias de cada um
  dos 11 tipos. Três grupos de dono: **GERAL** (tom de voz, termos proibidos, guardrails, diretrizes, canais,
  glossário, jornada padrão), **SANTANDER** (kit da marca padrão e a prateleira: 14 benefícios) e cada **empresa**
  (benefícios, jornada, landing page, kit da marca e canais de atendimento). Versão 1: 85 KBs.
- **Prateleira pública, valores fictícios:** os nomes dos produtos vieram de páginas públicas do Santander (Esfera,
  Rewards, cartão SX, pacote para quem é da folha, portabilidade, consignado, antecipação do 13º); o texto é reescrito,
  e todo valor em R$ ou % leva "(simulação)".
- **Trava** (`services/kbs_endomarketing.py`), ao salvar, publicar e revisar: **bloqueia** ficha incompleta, seção
  obrigatória vazia, termo proibido (a lista sai da **KB publicada** de termos proibidos: publicar uma versão nova dela
  muda a regra, sem código), valor sem "simulação", número com cara de CPF, frase de ordem para a IA (o guardrail do
  ADR-38) e logo com caminho de pasta; **só avisa** KB vencida e categoria que a vitrine não conhece. Todo achado é
  gravado (`kbs_achados_da_trava`) e aparece no **Acompanhamento dos agentes** (engrenagem Configuração), seção
  **"Guardrails das KBs"**.
- **Onde fica a tela** (escolha da usuária, 29/09, depois do menu novo do ADR-122): **dentro de Endomarketing**. O
  menu continua com as 5 abas; a tela "Benefícios e KBs" marca Endomarketing e abre pelo botão do Endomarketing, pela
  ficha da empresa (aba Catálogo) e pelo Acompanhamento dos agentes.
- **Versões e situação** (`kbs_endomarketing`): gravar cria um **rascunho**; publicar deixa a versão **publicada** e a
  anterior **substituída**; retirar tira a publicada; **revisar** renova a vigência numa versão nova. KB vencida ou
  vencendo em 30 dias aparece em "Para revisar".
- **A vitrine da empresa mostra só as KBs de benefício publicadas e vigentes dela** (`portal_da_empresa`, via
  `kbs_publicacao.documentos_da_vitrine`), no mesmo formato do catálogo: o front da vitrine não mudou.
- **Aplicar na empresa** (automático ao publicar ou retirar um benefício, o atendimento ou o kit; e pelo botão): o
  catálogo do agente ganha uma versão nova montada das KBs publicadas (a anterior fica guardada), o kit próprio recebe
  as cores da KB e o logo fictício (`scripts/gerar_logos_das_kbs.py`). Registrado em `kbs_publicacoes`.
- **Índice do RAG:** coleção nova `kbs_endomarketing`, com a etiqueta do dono; `buscar_kbs(empresa_id, ...)` só olha
  GERAL, SANTANDER e a própria empresa. Publicar troca no índice só aquela KB; a coleção inteira é montada por
  `scripts/indexar_kbs_endomarketing.py`. O pacote pronto para um agente sai em `GET .../contexto/{empresa_id}`.
- **Ajuste autorizado pela usuária** (exceção à regra "só cria" do construtor, 2026-09-28): a vitrine passou a ler as
  KBs (`services/portal_da_empresa.py`), e **saiu a subida manual do catálogo** (a rota
  `POST /api/banco/empresas/{id}/catalogo`, o botão e a janela da ficha da empresa), para nada chegar à vitrine sem
  passar pela trava. A aba "Catálogo de benefícios" da ficha continua, só de leitura, com o link para Benefícios.

**Porquê.** Um texto de banco vira promessa: a trava impede que "crédito garantido" ou uma taxa inventada cheguem ao
material, e o registro mostra o que ela barrou. O modelo fixo faz toda KB responder às mesmas perguntas (para quem é,
como funciona, como contratar, a condição), que é o que o agente e a vitrine precisam. As versões com situação deixam o
especialista preparar a mudança sem tirar do ar o que vale hoje.

**Trade-off.** O agente atual (`agents/endomarketing.py`, prompt `endomarketing_v3`) continua lendo o catálogo, agora
montado das KBs: os benefícios chegam, mas o tom de voz, os termos proibidos e o kit ainda não entram no prompt (o
contexto está pronto em `/contexto`; ligar ao prompt é um pedido próprio). Até a primeira aplicação de cada empresa, o
catálogo do agente é o da versão 1 dos arquivos. A tabela de termos proibidos compara palavras inteiras: uma variação
nova ("garantidíssimo") precisa entrar na tabela.

**Como comprovar.** `tests/test_kbs_endomarketing.py` (28 testes: os arquivos passam na trava e cada empresa tem as KBs
obrigatórias e um logo válido; cada regra da trava; a lista de termos sai da KB publicada; rascunho, publicar,
substituir, retirar e revisar; a vitrine só com as publicadas e sem outra empresa; aplicar na empresa grava catálogo,
kit e logo; o contexto sem outra empresa; as rotas só do BANCO, com 401, 403, 404, 400 com os achados e 422 para campo
gigante; a subida manual saiu; a busca no índice nunca traz outra empresa; a troca de uma KB no índice; a carga inicial feita por duas telas ao mesmo tempo não duplica) e o roteiro de
clique `beneficios_do_banco` (17 passos).

**Altera** o ADR-19 (o catálogo deixa de ser subido à mão: passa a ser montado das KBs publicadas) e completa o ADR-115
(o material do banco passa a ter tom, termos e kit descritos). **Origem.** Pedido da usuária, 2026-09-28.

**Revisão de 2026-09-29 (a tela; a regra não muda).** Pedido da usuária no revisor de telas:
- **As KBs vão para as guias do Endomarketing.** A empresa é escolhida primeiro (nada aparece sem ela), e embaixo ficam
  as guias **Base de Conhecimento** (as KBs da empresa, com os Benefícios numa aba própria, a primeira), **Regras
  gerais** (diretrizes gerais e Santander, iguais para todas as empresas) e **Material para Comunicação**. A tela
  "Benefícios e KBs" foi **aposentada**: o endereço antigo leva às guias, e os links da ficha da empresa e do
  Acompanhamento dos agentes apontam para elas.
- **Sai o botão "Aplicar na empresa" e a linha da última aplicação.** Publicar, retirar e renovar já aplicavam sozinhos;
  para a pessoa, isso é transparente ("Pode tirar", usuária). O serviço e a rota de aplicar continuam, sem botão.
- **"Aguardando publicação":** as versões novas (rascunho), com quem salvou, data e hora, Visualizar e Publicar.
- **"Histórico anterior":** as versões mais antigas que a atual abrem **congeladas** (cor de gelo, selo "Congelada"),
  só para consulta: sem editar, publicar ou retirar, com a navegação entre elas.
- **Prova:** roteiros `endomarketing_em_secoes` e `beneficios_do_banco` (este passou para as guias).

---

### ADR-132 · Credencial da publicação: o usuário `integra-publicador`, com permissões só de publicar, no lugar da conta principal ✅

**Contexto (2026-09-29, primeira sessão do agente publicador).** A entrada na AWS pelo CLI é o `aws login` (sem chave
de acesso guardada no computador). No primeiro login, a identidade devolvida foi a **conta principal** (`...:root`), que
pode tudo, inclusive mexer na cobrança e fechar a conta. Um agente automatizado com esse poder transforma qualquer
engano em risco para a conta inteira.

**Opções.** (a) Seguir com a conta principal; (b) um usuário com a política pronta de administrador; (c) **um usuário
só para publicar, criado por um modelo CloudFormation versionado, com as permissões mínimas e um limite para os papéis
que ele criar**.

**Decisão (c)** (escolha da usuária, 29/09), em `publicacao/usuario-publicador.yaml`, pilha `conta-usuario-publicador`:
- **Usuário `integra-publicador`,** com senha e MFA definidos pela dona da conta no console (nada disso passa pela
  conversa nem pelo Git). A entrada é pelo `aws login` (política da AWS `SignInLocalDevelopmentAccess`).
- **O que ele pode:** pilhas `integra-*`; EC2 só na Virgínia (`us-east-1`) e só `t3.micro`, `t3.small` e `t3.medium`;
  buckets `integra-*`; o alarme de orçamento; preços e custos (leitura); ler o IAM e o Bedrock.
- **Os freios:** compras de longo prazo (reservas, hosts dedicados) são negadas; ele não altera a pilha das próprias
  permissões (o nome não começa com `integra-`); todo papel `integra-*` que ele cria é **obrigado** a levar o limite
  `integra-limite-dos-papeis`, que no máximo grava o backup (sem apagar), chama o Bedrock e manda métricas e logs; tirar
  esse limite é negado.
- **A conta principal** fica com a dona, para a cobrança, a retenção zero do Bedrock e a chave de produção. Ela tem MFA
  e nenhuma chave de acesso (conferido em 29/09). Mudar as permissões do publicador é uma atualização da pilha, feita
  por ela.

**Porquê.** É o princípio do menor privilégio: o agente só alcança o que a publicação usa, e um erro dele não chega à
cobrança, a outras regiões nem a máquinas caras. O limite dos papéis fecha a porta da "autopromoção" (criar um papel
com mais poder e usá-lo pela máquina). Como é código, a banca vê exatamente o que ele pode, e dá para recriar ou apagar.

**Trade-off.** Uma permissão que faltar só aparece na hora do uso (um "acesso negado") e exige a dona da conta para
atualizar a pilha. As prévias de mudança do CloudFormation ficaram sem regra própria: não foi possível confirmar na
documentação se são autorizadas pela pilha; se a publicação for barrada, entra uma regra restrita às pilhas `integra-`.

**Como comprovar.** `aws sts get-caller-identity --profile integra-publicacao` devolve `user/integra-publicador`;
`aws cloudformation delete-stack --stack-name conta-usuario-publicador` responde `AccessDenied`;
`aws ec2 run-instances --dry-run --instance-type m5.large ...` responde `UnauthorizedOperation`, e o mesmo ensaio com
`t3.small` responde `DryRunOperation` (permitido; nada é criado). Todos rodados em 29/09.

**Origem.** Decisão da usuária, 2026-09-29, na preparação das ferramentas do agente publicador.

### ADR-128 · Parâmetro do layout: tipo de renda com OUTROS, matrícula opcional, sexo obrigatório e mínimo e máximo nos campos de valor ✅

**Contexto (2026-09-29, decisões da usuária sobre a rodada 02 do QA com IA real).** O relatório
`QA_Jornada/Relatorio_Rodada_02_Pendencias_IA_Real.md` (seção 5) levou ao negócio quatro perguntas, e o D27 do
`QA_Jornada/Dificuldades.md` mostrou uma coluna de tipo de renda marcada como "ambígua" só porque os valores estavam
fora da lista. As respostas da usuária:
1. "Mensal" e "Horária" **só contam como CLT se a empresa informar**; o sistema nunca deduz. A lista ganha **OUTROS**.
   Um valor fora da lista não é dúvida sobre a coluna: é pendência da pessoa, tratada no cartão.
2. A **matrícula** deixa de ser obrigatória: a empresa que não usa matrícula (QA11: "a gente não usa matrícula
   aqui") envia sem ela, e o funcionário é identificado pelo CPF. A primeira decisão foi tirá-la do parâmetro; a
   usuária perguntou se isso não facilitava um problema que a IA não resolveu, e a decisão final foi **opcional, no
   parâmetro**: a origem era a regra (campo obrigatório sem saída), não a IA, e tirar o campo tiraria da avaliação os
   casos difíceis de matrícula (confusão com CPF e código da unidade, zeros à esquerda, repetida). O QA confere na
   próxima rodada (D38 em `QA_Jornada/Dificuldades.md`).
3. O **sexo é obrigatório**: a empresa precisa informar; sem ele, nasce uma pendência.
4. Os campos numéricos ganham **mínimo e máximo opcionais** no parâmetro; o salário começa com o **piso de R$ 500,00**;
   fora da faixa, **alerta**, e não recusa. (A faixa por cargo com o código CBO é outra frente.)

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| A · converter Mensal/Horária em CLT por sinônimo | O cartão some | O sistema assumiria um vínculo que a empresa não disse (contra "nada do banco é assumido") |
| **B · OUTROS na lista fechada, sem sinônimo de CLT; a regra geral "valor fora da lista não é dúvida de coluna" no conhecimento da IA** | A empresa escolhe no cartão (CLT, PRO_LABORE ou OUTROS); vale para qualquer lista | Um cartão por valor desconhecido (agrupado pelo ADR-120) |
| A' · piso do salário fixo no código | Rápido | Regra de negócio escondida; o banco não muda |
| **B' · `minimo` e `maximo` no parâmetro (CampoLayout), editáveis na tela Parâmetros, lidos pelo Validador e pelo RAG** | O banco decide e muda sem programador; vale para qualquer campo de valor | Mais dois atributos para o banco cuidar |

**Decisão.** B e B'.
- **Contrato** (`models/contratos.py`): `CampoLayout` ganha `minimo` e `maximo` (Decimal, opcionais). Aceitam o jeito de
  a pessoa escrever ("500", "500,00", "R$ 1.500,50", "2.000"); só valem nos tipos de valor (`TIPOS_COM_FAIXA`, hoje o
  `DECIMAL_MONETARIO`), e o mínimo não passa do máximo.
- **Layout v1** (`data/contratos/layout_v1.csv`): `matricula` opcional; `sexo` obrigatório; `valor_renda` com
  mínimo de 500,00; as regras de texto dizem isso (a matrícula, quando vem, continua única e com os zeros). **Lista** (`dominios_v1.json`): `tipo_renda` = CLT, PRO_LABORE ou
  OUTROS; "outros/outro/outra" viram OUTROS; nenhum jeito de dizer "mensal" ou "por hora" vira CLT.
- **Validador** (`services/validador.py`): a regra nova `VALOR_FORA_DA_FAIXA` (ALERTA, "Corrigir ou confirmar"), que
  não repete o alerta num valor zerado ou negativo (já bloqueado por `RENDA_NAO_POSITIVA`). O sexo vazio cai nas
  regras de obrigatório de sempre (`OBRIGATORIO_VAZIO`, `OBRIGATORIO_SEM_COLUNA` com "de cada pessoa",
  `VALOR_NAO_CONVERTIDO` bloqueante para "não informado").
- **Cartão**: a pergunta da faixa (`services/pergunta_da_pendencia.py`), a linha "Problema: valor fora da faixa
  esperada pelo banco" e o botão "Está certo assim"; no tipo de renda, os botões CLT, PRO_LABORE e OUTROS.
- **Tela Parâmetros** (`front/banco_parametros.html`, `front/js/banco_parametros.js`): a coluna "Faixa" na lista e o
  "Mínimo" e o "Máximo" na janela do campo, que aparecem só num tipo de valor; o registro das alterações diz o antes e
  o depois em reais ("valor_renda · mínimo: sem limite → R$ 500,00").
- **Regra geral "campo que o banco tira do parâmetro nunca é proposto"** (achada ao testar a saída da matrícula): o
  simulador do Interpretador (MOCK) e o plano de emergência só propõem campos do layout vigente; o histórico de
  mapeamentos do índice do RAG (`rag/trechos.py`) passa a ter o mesmo filtro que o índice dos aprovados já tinha.
  Antes, um campo tirado na tela Parâmetros ainda era sugerido e virava uma dúvida de coluna sem saída.
- **Conhecimento da IA** (`regras_v1.json`): a matrícula é opcional e o funcionário é identificado pelo CPF; a regra
  nova "Mínimo e máximo do parâmetro"; e a frase do D27 na regra `tipo_dominio` (valor fora da lista é pendência da
  pessoa, não dúvida da coluna).
- **Mundo sintético congelado**: as empresas fictícias exportam as colunas de uma lista própria
  (`CAMPOS_DO_MUNDO_SINTETICO`, em `scripts/montar_envios.py`), e não mais as do layout vigente. Assim, uma mudança no
  parâmetro não muda os arquivos, os sorteios nem as medições. O sexo, obrigatório agora, entra no fim do arquivo
  das empresas que não o mandavam, com o nome "Sexo" e sem sorteio (`OBRIGATORIOS_ACRESCENTADOS_NO_FIM`): cada
  gabarito ganhou só a linha `"Sexo": "sexo"`. Com o ok da usuária, a prova foi **recongelada** (ADR-58;
  `scripts/congelar_avaliacao.py`, 2026-09-29, com o motivo registrado): nenhuma medição tinha sido feita desde a
  mudança.
- **Banco que já está em uso**: `scripts/aplicar_parametro_adr_128.py` grava a próxima versão do parâmetro com só estas
  mudanças, mantendo o que o banco já editou na tela (roda uma vez; rodar de novo não grava nada). Depois, o índice do
  RAG é refeito (`scripts/build_index.py`).

**Porquê.** São regras de negócio: ficam no parâmetro, que o banco vê e muda, e o código só lê. Nada do banco é
assumido: o tipo de renda e o sexo vêm da empresa, e a faixa é um alerta que a empresa confirma.

**Trade-off.** Os envios que já estão em andamento continuam com a versão do parâmetro com que foram lidos até serem
revalidados. A avaliação do fluxo ganha uma coluna mapeada (o sexo) em 6 arquivos. **Em espera, com a usuária:** o
prompt `interpretador_v4` (a regra do D27 dentro do prompt); até lá, o D27 é tratado pelo conhecimento que a IA
consulta (a regra `tipo_dominio`). **Próximo passo combinado** (usuária, 2026-09-29): quando a empresa diz que não tem,
não usa ou não consegue enviar um campo obrigatório, o Agente de validação explica que o campo é obrigatório e pede
que ela fale com o especialista do banco que atende a empresa (entra depois da junção do pedido `cartoes-que-conferem`).

**Como comprovar.** `tests/test_parametros_do_layout.py` (97 testes, com variações novas de cada caso, nenhuma tirada
dos arquivos do QA) e o roteiro de clique `parametros_do_layout`.

**Origem.** Decisões da usuária, 2026-09-29 (pedido `parametros-do-layout`).

### ADR-130 · Leitor de fichas: abas ligadas por um identificador e fichas escritas em texto ✅

**Contexto (2026-09-29, achados D05 e D24 do QA da jornada, com a IA real).** A leitura de tabela
(`services/ingestao.py`) entende uma linha por funcionário e um dado por coluna. Dois jeitos comuns de arquivo
escapavam dela:
- **uma planilha com várias abas** (os dados pessoais numa, o contrato noutra): só a aba com mais CPFs era lida, e o
  cargo, a admissão e o salário viravam "o arquivo não trouxe";
- **fichas escritas em texto**, inteiras numa célula ou em pedaços espalhados por linhas e abas, com uma coluna que diz
  de quem é cada pedaço. Cada linha virava uma "pessoa": nomes como "CEP ... falar (19) 9...", CPF igual ao e-mail, de
  24 a 43 cartões para 3 ou 4 funcionários, e o CPF com dígito errado passava.

**Opções.** (a) Mudar a leitura de tabela para entender esses formatos; (b) pedir à empresa que arrume o arquivo;
(c) **um leitor novo, que reconhece só esses formatos e convive com a leitura de sempre** (regra do agente construtor:
só cria, nunca ajusta).

**Decisão (c): `services/leitura_de_fichas.py`**, chamado no começo de `ingestao.ler_arquivo`. Se ele não reconhece o
arquivo, devolve `None`, e a leitura de sempre segue sem mudança nenhuma.
- **Reconhecer só pela forma dos dados, nunca pelo nome de uma coluna ou de um arquivo** (cláusula de generalização da
  usuária): o que decide é quantas abas há, que colunas têm identificador e que células juntam vários dados.
- **A) Abas ligadas (sem IA).** Duas ou mais abas com cabeçalho, e uma coluna de identificador em comum (todo valor tem
  número; o CPF vem antes de qualquer outro, como a matrícula), com pelo menos metade dos valores de cada aba presentes
  na aba principal (a mesma que a leitura de sempre escolheria). As colunas se juntam numa tabela só, uma linha por
  pessoa. O CPF que o Excel gravou como número e perdeu o zero da frente casa do mesmo jeito.
  - A pessoa que só está numa aba **entra com o que tem, com aviso** (decisão da usuária, 29/09).
  - O identificador repetido numa aba (um histórico, por exemplo) não liga, com aviso do motivo.
  - A aba que não se liga fica de fora, e a leitura de sempre passa a dizer o que fazer: "junte tudo numa aba só, ou
    ponha o CPF em cada aba" (1 linha acrescentada em `_resultado_da_planilha`, com o ok da usuária).
- **B) Fichas em texto (com a IA).** Uma coluna de texto longo em que pelo menos metade das células junta 2 tipos de
  dado ou mais (CPF, data, valor, CEP, telefone, e-mail, documento, pelo detector do projeto), numa tabela sem coluna
  própria de CPF.
  - **A referência** é a coluna curta que se repete e separa os CPFs, um por grupo; uma coluna que junta dois CPFs no
    mesmo grupo (como "origem") **não serve**, para nunca misturar duas pessoas. Sem referência, cada linha é uma
    ficha inteira; se mais da metade das linhas não tem CPF, são pedaços de ninguém, e o arquivo é **recusado com uma
    mensagem que diz o que fazer**.
  - **Os pedaços de cada pessoa viram um texto só** (o pedaço com o CPF primeiro), lido pelo **Agente Leitor de
    Documentos, sem mudar nada nele nem no prompt**, **uma pessoa por vez** (várias ao mesmo tempo). O guardrail de
    injeção tira o pedaço com cara de ordem antes de a IA ler.
  - **A conferência por regra, depois da IA:** um nome não tem número, "@" nem mais de 8 palavras (senão sai e vira
    pergunta); todo CPF tem o dígito verificador conferido (senão vira pergunta presa à pessoa); o mesmo CPF em duas
    pessoas vira pergunta nas duas.
  - **A leitura fica guardada** (`.leitura.json`, como a do Word; 3 linhas acrescentadas em `processamentos.py`): as
    etapas seguintes não chamam a IA de novo.
  - Na Telemetria, o Leitor aparece uma vez por pessoa (ok da usuária): o custo é o mesmo.

**Porquê.** O arquivo difícil é o que mais faz a empresa desistir. Juntar pela referência (e não pela posição da
linha) e ler uma pessoa por vez tira da IA o trabalho de adivinhar quem é quem, que era onde ela errava. A regra depois
da IA pega o que nenhuma IA deveria deixar passar (um CPF inválido). Como o leitor é separado, a leitura de tabela, que
já estava medida e testada, não muda.

**Trade-off.** Mais uma leitura para manter; os limites (texto longo, metade das células, 2 tipos de dado) são
escolhas, que um arquivo muito diferente pode não atingir (aí segue a leitura de sempre, como antes). A IA é chamada uma
vez por pessoa (2 chamadas: a divisão e a leitura). Os rótulos que a IA não acha no texto aparecem como "Sem rótulo N"
na tela de colunas, como já acontece no Word em texto corrido.

**Medição com a IA real** (Sonnet 4.6 + Nova 2 Lite, Bedrock; 29/09; US$ 0,35 nos 4 arquivos altos do QA): 3, 4, 3 e
3 pessoas, com o nome e o CPF certos em todas (antes: 24 a 43 cartões). A data sem convenção e o salário de duas
propostas sem assinatura viraram perguntas (sem valor escolhido pela IA), e o CPF com dígito errado virou pergunta.
Ficou para o Conferidor da Leitura: perguntas a mais (e-mail "corporativo", benefício separado do salário), que já
acontecem no Word (D26, ADR-131).

**Testes.** `tests/test_leitura_de_fichas.py` (35 testes, todos com planilhas montadas no próprio teste e 3 variações
ou mais por caso: rótulos, separador, ordem, formato .xlsx/.ods/.csv/.txt e valores diferentes) e o roteiro de clique
`leitura_de_fichas`. **Origem.** Pedido da usuária pelo orquestrador (D05 e D24 do `qa-jornada`), 2026-09-29.

### ADR-129 · Faixa salarial por profissão (CBO) com dados públicos da RAIS, e o alerta de salário fora dela ✅

**Contexto (2026-09-29, pedido da usuária ao agente construtor).** Esta decisão nasceu da decisão (d) do relatório da
rodada 02 do QA: faltava um piso para o salário. A usuária pediu:
- a tabela oficial de profissões (CBO) dentro da aplicação;
- uma faixa de salário, com mínimo e máximo, para cada código, calculada com dados públicos, e com a fonte e a data
  em cada linha;
- que o cargo enviado pela empresa chegue a um código CBO;
- pelo menos um alerta quando o salário sai da faixa da profissão, da própria empresa ou das outras empresas. Das
  outras, só o agregado. O alerta nunca recusa o envio;
- uma tela do banco para consultar e editar a faixa, guardando quem mudou e quando e mantendo a calculada ao lado;
- arquivos de teste novos.

Antes disso, o Validador já comparava o salário com os colegas de cargo da própria empresa (`RENDA_FORA_DO_CARGO`,
ADR-14). Com poucos colegas, usava uma tabela **sintética** de 14 cargos.

**Opções.**
- **Base:**
  - (a) RAIS 2025, o estoque de todos os vínculos formais em 31/12, com 3,8 GB compactados;
  - (b) Novo CAGED 2025, só o salário de admissão, com 0,5 GB. Ele puxa a faixa para baixo;
  - (c) sites de salário, que não são oficiais nem reprodutíveis.
- **Como o cargo chega ao código:**
  - (1) uma coluna "Código CBO" no arquivo, com o nome do cargo quando ela não vier;
  - (2) só a coluna;
  - (3) só o nome do cargo, com a confirmação da empresa.
- **Medida:** os percentis 5 e 95, ou os percentis 10 e 90.

**Decisão** (a usuária aprovou todas as recomendações do contrato):
- **Os dados:**
  - **a base é a RAIS 2025,** do Ministério do Trabalho: os microdados públicos, sem identificação, baixados do FTP
    do PDET;
  - **quem entra:** os vínculos CLT (tipos 10, 15, 20, 25, 60, 65, 70 e 75) ativos em 31/12, com 30 horas semanais
    ou mais, não intermitentes, com remuneração nominal de dezembro maior que zero. Ficam fora o estatutário, o
    aprendiz, o temporário e o diretor sem vínculo;
  - **o mínimo e o máximo:** o percentil 5 e o percentil 95 da remuneração de dezembro;
  - **o valor de corte:** a profissão com menos de 30 vínculos usa a faixa da **família** (os 4 primeiros dígitos,
    marcada como "FAMILIA"). Se a família também tiver menos de 30, fica "sem dados" e não gera alerta;
  - **sem correção monetária:** a tela mostra o ano da base, e o banco edita se quiser;
  - **o resultado:** 40.366.698 vínculos entraram na conta. Das 2.694 profissões da CBO,
    2.365 ficaram com faixa própria, 281 com a da família e 48 sem dados;
  - **os arquivos:**
    - os brutos ficam em `storage/fontes_publicas/`, fora do Git;
    - no Git, só `data/cbo/`: a CBO em UTF-8 (2.694 profissões, 7.778 sinônimos e 626 famílias), a tabela de faixas
      e o `fontes.json`, com o endereço, a data e a soma de conferência (SHA-256) de cada arquivo.
    - `scripts/calcular_faixas_cbo.py` refaz tudo.
- **O cargo chega ao código pela opção (1).**
  - **A coluna "Código CBO" do arquivo:**
    - é o campo `codigo_cbo` do parâmetro, que o banco cria na tela Parâmetros;
    - aceita "4110-10", "411010", "4110.10" e o número lido do Excel;
    - o código que não existe vira o `CBO_DESCONHECIDO` (ALERTA).
  - **Sem a coluna, o nome do cargo** (`services/tabela_cbo.py`, sem IA):
    - é comparado com os títulos e os sinônimos oficiais, por regras gerais: maiúsculas, acentos, ordem das palavras,
      plural, feminino, abreviações comuns, nível na carreira (júnior, pleno, sênior, I, II) e o "em geral" da CBO;
    - só uma profissão combinando é uma sugestão, que vira o `CBO_A_CONFIRMAR` (ALERTA, um por cargo);
    - um nome genérico ou de mais de uma profissão vira o `CBO_NAO_ENCONTRADO` (AVISO, não bloqueia).
  - **A resposta fica em `cbo_dos_cargos`:**
    - "Está certo assim" grava a profissão do cargo;
    - desfazer ou recusar tira a profissão;
    - nada é assumido: o cargo sem resposta não é comparado.
- **O alerta `RENDA_FORA_DA_PROFISSAO` (ALERTA, um por pessoa):**
  - vale para o salário CLT e cita as faixas de que o salário saiu:
    - a pública, em uso: a calculada ou a editada pelo banco;
    - a das **outras empresas** na mesma profissão, com os percentis 5 e 95 dos funcionários já cadastrados. Ela só
      aparece com pelo menos **2 empresas e 10 pessoas**, e só com os dois números;
  - o `RENDA_FORA_DO_CARGO` da própria empresa continua como estava. Uma pessoa pode ter os dois alertas (decisão da
    usuária).
- **Liga com o campo:** tudo isso só acontece quando o parâmetro vigente tem o campo `codigo_cbo`. Sem ele, o envio
  fica como era, o que é a garantia do "só cria".
- **A tela:** a seção "Faixas salariais por profissão (CBO)" da página Parâmetros, só do BANCO (`api/rotas_faixas_cbo.py`):
  - buscar por código ou por palavras do título e dos sinônimos;
  - editar o mínimo e o máximo: nunca o mínimo maior que o máximo, valores maiores que zero e até R$ 1 milhão;
  - guardar quem e quando (`faixas_salariais_cbo_alteracoes`);
  - "Voltar ao calculado".

**Porquê.**
- A faixa de uma empresa só funciona com colegas suficientes, e a tabela sintética não cobria as profissões de
  verdade. A RAIS é a fonte oficial mais completa de salário por ocupação no Brasil.
- Os percentis 5 e 95 deixam de fora os extremos (erros e casos raros) sem gerar alarme a cada salário comum, e ainda
  pegam o erro de digitação ("2.500" lido "2,50") e o salário cem vezes maior.
- O código da CBO é o mesmo que a folha já usa no eSocial. Por isso a coluna é o caminho principal, e o nome do cargo,
  o de reserva.

**Trade-off.**
- **A remuneração de dezembro de 2025 não é corrigida** até a data do envio: a faixa envelhece.
  - A tela mostra o ano, e o cálculo é refeito com a RAIS seguinte.
- **A remuneração inclui as variáveis do mês**, como comissões e horas extras, então o máximo fica acima do salário de
  contrato.
- **O mínimo pode ficar abaixo do salário mínimo** (ex.: Recepcionista, R$ 1.295,10), porque a remuneração de dezembro
  de quem teve faltas ou afastamento no mês também entra. O piso de 500 do parâmetro (outra frente) cuida do valor
  absurdo.
- **No modo simulado (`MODE=mock`), a leitura das colunas não reconhece a coluna do CBO sozinha.** O vocabulário do
  simulador é o do experimento B0 e não foi mudado: no teste, a empresa escolhe o campo no aceite das colunas. Com a IA
  real, a descrição do campo leva a IA à coluna.
- **Recalcular com uma RAIS nova acrescenta as profissões que faltam, mas não muda as que já estão na tabela.** Com
  isso, a edição do banco nunca se perde; trocar a base exige uma migração própria.
- **A busca pelo nome pode sugerir uma profissão estreita** quando a CBO tem só um sinônimo com aquele nome (ex.:
  "Mecânico"). Por isso a empresa sempre confirma, e na dúvida a resposta certa é recusar e mandar a coluna.
- **A faixa das outras empresas depende de os cargos delas terem profissão.** Isso vem do arquivo ou da confirmação.

**Como comprovar.**
- **`tests/test_faixa_salarial_cbo.py`,** com 103 testes e cada regra com 3 ou mais variações novas:
  - sem o campo, nada muda;
  - o código em vários formatos, e o código inválido;
  - o nome do cargo em várias formas, o nome genérico e o ambíguo;
  - fora da faixa, nos limites, o pró-labore, "sem dados" e a faixa editada;
  - a pergunta, a confirmação, desfazer e recusar;
  - a faixa das outras empresas só com 2 empresas e 10 pessoas, sem nada delas na mensagem;
  - a edição, com os valores inválidos, quem e quando e voltar ao calculado;
  - a carga sem duplicar nem apagar a edição;
  - as rotas só do BANCO (401, 403, 404, 400 e 422);
  - um envio de verdade, do recebimento ao "Está certo".
- **Os roteiros de clique** `faixas_por_profissao` e `alerta_de_salario_por_profissao`.
- **Os arquivos de teste** em `D:\AI_Payroll_Hub\Imports_Arquivos_CBO`, com o `REGISTRO_IMPORTS_CBO.txt`, gerados por
  `scripts/gerar_arquivos_cbo.py`.

**Completa** o ADR-14: o enquadramento de renda ganha duas referências de fora da empresa.
**Origem:** pedido da usuária, 2026-09-29 (pedido `faixa-salarial-cbo` do construtor).

### ADR-127 · O cartão de pendência só diz "Pronto" quando o valor confere ✅

**Contexto (2026-09-29, pedido cartoes-que-conferem, aberto pelo orquestrador com o ok da usuária).** O QA da jornada,
com a IA real, achou cinco furos nas pendências por conversa (ADR-118): **D04** o CPF com o dígito errado recebia
"Pronto: preenchi a informação CPF", e só depois nascia o cartão do dígito errado; **D23** "os dados estão todos na
coluna transcrição" fazia o Nome completo virar a ficha inteira da pessoa (a conferência da coluna aceitava qualquer
texto com uma letra); **D25** uma pergunta ("o que é empresa do grupo? ...") virava confirmação; **D15** o CNPJ e o
endereço da empresa, que o cadastro já tem, eram pedidos de novo (o endereço em 6 cartões); **D22** a conversa devolveu
o envio à leitura das colunas, os 43 cartões sumiram, e o Acompanhar disse "Tudo em dia!". A usuária pediu também uma
**cláusula de generalização**: corrigir com regra geral, nunca com o caso do QA, e testar cada caso com variações novas.

**Opções.** (a) Ajustar o prompt do agente para cada caso; (b) **travas no código, antes de qualquer "Pronto"**, que
valem para qualquer frase, empresa ou arquivo, e o prompt só como segunda chance.

**Decisão (b), em cinco regras gerais:**
- **O valor é conferido antes de entrar** (`services/conferencia_do_valor.py`): a mesma padronização do arquivo, o
  dígito verificador do CPF e do CNPJ, e a regra do nome de pessoa. Não confere: nada muda, e a conversa diz "Esse CPF
  não confere: ... Nada mudou. Qual é o CPF certo?" (ou "O valor ... não serve para a informação ..."). Vale para a
  troca de uma pessoa, o "para todos" e o cartão do grupo.
- **Um nome de pessoa não tem números nem mais de 10 palavras** (Nome completo e Nome da mãe; o Nome da unidade fica de
  fora, porque "Loja 12" é um nome de unidade). A conferência da coluna indicada na conversa usa a mesma regra: a ficha
  inteira numa célula não passa, e a troca não é oferecida.
- **Uma mensagem com "?" nunca confirma nem muda um dado** (`agents/assistente_correcao.py`): se o modelo escolher
  mudar (corrigir com valor, confirmar, preencher para todos, escolher o formato ou reler uma coluna), ele recebe a
  regra e responde de novo; se insistir, a fala fixa diz que nada mudou. "Não cadastrar", "deixar em branco" e "usar
  outra coluna" continuam, porque só propõem e a pessoa confirma num botão.
- **O que o sistema já sabe da empresa é oferecido** (`services/dados_da_empresa_no_envio.py`): no dado que falta (a
  coluna que o arquivo não trouxe ou a célula vazia), o cartão do CNPJ do empregador ganha "Usar o CNPJ da empresa
  (...)" e o de cada pedaço do endereço comercial, "Usar o endereço da empresa (...)". O clique (ou "é o CNPJ da nossa
  empresa", sem "?" e sem "não") preenche todos os funcionários sem o dado, sem IA, e o endereço inteiro sai de uma vez,
  com um Desfazer só. O endereço do cadastro é dividido pela regra do ADR-76; a cidade e a UF vêm das colunas
  próprias; **o que o cadastro não tem (hoje, o CEP e o bairro) não é inventado**: a fala diz o que faltou.
- **Nunca "Tudo em dia" com um envio parado nas colunas:** a rota `GET /api/empresa/envios-parados-nas-colunas` lista
  os envios em "Esperando você conferir as colunas", e o Acompanhar mostra um aviso para cada um ("Voltou para a
  leitura das colunas", quando ele já teve conversa de pendência), com o botão "Continuar a conferência das colunas".
  A conversa que devolve o envio às colunas diz isso na própria fala.

**Porquê.** A trava no código vale para qualquer frase e qualquer modelo; o prompt sozinho erra justamente nos casos
que ninguém previu. Conferir antes do "Pronto" é o que a empresa espera de um "Pronto".

**Trade-off.** O "?" é uma regra simples: "Está certo assim?" dita como afirmação com ponto de interrogação não
confirma (a pessoa confirma pelo botão ou sem o "?"). Um nome com número de verdade (raro) precisa ir sem o número. O
botão da empresa só completa o dado que falta: um CNPJ que veio errado no arquivo a empresa corrige, porque pode ser de
uma filial. A pergunta que o modelo erra custa uma chamada a mais ao modelo.

**Como comprovar.** `tests/test_cartoes_que_conferem.py` (51 testes: cada caso do QA com pelo menos 3 variações novas,
em outras palavras, formatos e ordens; o CPF e o CNPJ certos continuam valendo; nomes de verdade continuam passando; a
pergunta nunca confirma, e sem "?" a confirmação vale; a frase da empresa com negação, pergunta ou no cartão errado não
vale; o endereço sai inteiro e volta num Desfazer; o envio parado aparece; a rota nova com 401, 403 e sem a outra
empresa), o teste antigo do CPF errado em `tests/test_assistente_na_tela.py` (agora nada muda) e o roteiro de clique
`cartoes_que_conferem`. **Nada dos arquivos do QA entrou em prompt ou em base de conhecimento.**

**Completa** o ADR-118 (pendências por conversa) e o ADR-124 (a coluna que falta em outra coluna). **Origem.** QA da
jornada, rodadas 01 e 02 (D04, D15, D22, D23 e D25), 2026-09-29.

<a id="adr-126"></a>

### ADR-126 · Envio parcial: quem já foi ao banco fica de fora; a lista final com o valor dos cartões e um número só de pendências ✅

**Contexto (2026-09-29, QA da jornada, rodadas 01 e 02, com a IA real).** Três achados da etapa "Conferir e enviar":
- **D01 (alta):** a lista "Confira a lista que vai para o banco" mostrava "Informação não encontrada" em todo campo
  preenchido pelos cartões (CNPJ, unidade, admissão, renda...): 126 células num arquivo de 5 pessoas. A lista só
  mostrava os campos que tinham coluna no arquivo.
- **D09 (média):** a conferência dizia "0 com pendência", o painel ao lado "14 para revisar" e Acompanhar, 14. A
  conferência não contava as informações que faltam no arquivo inteiro, e o painel somava o relatório cru (contando a
  pergunta da IA que já é explicação de uma correção).
- **Decisão (e) da usuária:** "pode aceitar envio parcial". Quem a empresa manda de novo e **já foi enviado ao banco**
  é barrado; a tela diz quem e por quê, e o sistema segue só com os outros. Antes, a mesma pessoa noutro envio ainda
  não cadastrado virava a pendência BLOQUEANTE `PESSOA_EM_OUTRO_ENVIO` nos dois envios, inclusive no que já estava com
  o banco (que ficava sem poder ser aprovado).

**Opções (envio parcial).** (a) manter a pendência e a empresa tirar a pessoa à mão; (b) tirar as linhas repetidas do
arquivo antes de virar envio (perde o rastro do que a empresa mandou); (c) **a linha fica no envio, marcada pelo
Validador como "fica de fora"**, como já acontecia com quem já está cadastrado (`JA_HOMOLOGADO_NA_EMPRESA`).

**Decisão (c):**
- **Regra nova `JA_ENVIADO_AO_BANCO` (AVISO):** o CPF está noutro envio da empresa que espera a análise do banco. A
  linha fica de fora deste envio, com o motivo "Já foi enviada ao banco no arquivo X e está em análise: não vai de
  novo". As duas regras que tiram a linha do envio ficam numa lista só (`validador.REGRAS_QUE_DEIXAM_A_LINHA_DE_FORA`),
  lida pela homologação, pela tela do banco, pela conferência e pelo "Pronto para enviar".
- **Quem fica de fora não pede nada à empresa:** as outras pendências da linha dela saem (não faz sentido completar o
  dado de quem não vai).
- **O envio que já está com o banco não olha os envios novos:** quem chegou depois é que fica de fora. O banco
  continua podendo aprovar.
- **Casos de borda:**
  - o mesmo CPF duas vezes no próprio arquivo **continua pendência** (`PESSOA_DUPLICADA`): a pessoa ainda não foi ao
    banco, e só a empresa sabe qual linha está certa. Se esse CPF já foi ao banco, as duas linhas ficam de fora;
  - **devolvido pelo banco (ADR-121):** não é "já enviado". Enquanto a pessoa está no envio de devolução (situação
    `DEVOLVIDO`, que antes não entrava na checagem entre envios), a mesma pessoa num arquivo novo é a pendência
    `PESSOA_EM_OUTRO_ENVIO` (ela fica num envio só). Tirada da devolução, ela pode voltar num arquivo novo;
  - já cadastrado: continua `JA_HOMOLOGADO_NA_EMPRESA`, agora também listado para a empresa com o motivo;
  - **todos já mandados antes:** o arquivo é recusado antes de virar envio, com o porquê em números ("Nada novo para
    enviar: as 5 pessoas deste arquivo já foram mandadas antes (3 já cadastrada(s), 2 em análise no banco). Nada foi
    enviado"); o envio em que todos ficaram de fora não aparece como pronto.
- **Na tela:** o bloco "N pessoas ficam de fora deste envio" (nome, CPF e motivo) na conferência do Cadastrar e na
  janela "Pronto para enviar ao banco" de Acompanhar; a linha do envio pronto diz "2 pessoas · 2 ficam de fora (já
  mandadas antes)"; o recado depois do envio conta quem ficou de fora (`front/js/quem_fica_de_fora.js`).

**D01.** A lista para conferir mostra os campos com coluna no arquivo **e os que ganharam valor depois** (nos cartões,
"para todos" ou pessoa a pessoa): é o que vai para o banco (`cadastro._campos_da_lista`).

**D09.** Um resumo só, calculado no servidor (`cadastro.resumo_das_pendencias`): `para_revisar` = pendências de pessoas
(corrigir e confirmar) + informações que faltam no arquivo inteiro, com a mesma junção da pergunta da IA à correção que
Acompanhar faz; `prontas` = pessoas sem pendência, zero enquanto falta informação no arquivo. O painel "Linhas do
arquivo", os contadores da conferência (com "N informações faltam no arquivo" e o aviso de que o cartão delas fica em
Acompanhar) e os cartões de Acompanhar dão o mesmo número.

**Porquê.** O objetivo do case é diminuir a desistência: travar um arquivo inteiro por causa de pessoas que já estão com
o banco faz a empresa refazer o trabalho à toa. A regra é geral (o CPF, depois de padronizado, contra os envios que
esperam o banco), e não depende do arquivo, da coluna nem do jeito de escrever o CPF.

**Trade-off.** A validação de um envio consulta a validação guardada dos outros (poucos envios por empresa). Um envio
validado antes de o outro ser aprovado pelo banco continua dizendo "em análise" até a próxima validação (o efeito é o
mesmo: a linha fica de fora). A linha idêntica repetida no próprio arquivo continua pedindo um clique ("tirar a linha
repetida"); barrá-la sozinha mudaria o gabarito dos experimentos (`eval/`).

**Como comprovar.** `tests/test_conferir_e_enviar.py` (24 testes, com planilhas montadas no teste e variações: a pessoa
já enviada em outra posição, com o CPF escrito de outro jeito, com o nome e a matrícula mudados; já cadastrada; o banco
aprova o envio antigo com um arquivo novo aberto; três recusas do arquivo sem ninguém novo; o CPF duas vezes; o
devolvido; três arquivos para o número único; três jeitos de o valor chegar à lista) e os roteiros de clique
`conferir_e_enviar` (novo), `conferencia_da_lista` e `acompanhar`.

**Altera** o ADR-74 (a pessoa noutro envio que já está com o banco deixa de ser pendência nos dois) e completa o ADR-121
(o envio devolvido entra na checagem entre envios). **Origem.** QA da jornada (D01, D09) e decisão (e) da usuária,
2026-09-29.

<a id="adr-133"></a>

### ADR-133 · A data da versão no rodapé de todas as telas ("Atualizado em ..."), vinda do commit ✅

> **Oculto nesta versão (2026-09-30, a pedido da usuária, antes da publicação final), como no ADR-148:** o lugar do
> rótulo nas 17 telas ganha a marca `data-oculto-nesta-versao`, e o `js/data_da_versao.js` pula os lugares marcados
> (nem pede a data ao servidor). A rota `/api/versao` e o código ficam; para voltar, basta tirar a marca das telas.
> O roteiro `data_da_versao` confere que o rótulo não aparece.

**Contexto (2026-09-29, pedido data-de-atualizacao-no-rodape).** A usuária pediu: "O site principal precisa ter um
label no final com a última data de atualização". Ela decidiu que a data é a da **versão** (o último commit da versão
principal que está rodando), e não a da publicação nem a hora de agora. No site publicado na AWS, a imagem Docker não
leva a pasta `.git`, então a data precisa chegar por outro caminho.

**Opções.** (a) A data de agora, na hora de montar a página: mostraria uma data falsa; (b) uma variável de ambiente
passada pelo script de publicação (`docker build --build-arg`): exige mudar o `publicar.sh` e o Dockerfile, e uma
imagem montada sem ela fica sem data; (c) **um arquivo com o marcador `$Format:%cI$` e a regra `export-subst` do
`.gitattributes`**: o próprio `git archive`, que o `publicar.sh` já usa para montar a imagem, troca o marcador pela
data do commit. Na máquina local, o Git responde direto.

**Decisão (c), com a variável como reserva.** O serviço `services/versao_da_aplicacao.py` procura a data, uma vez ao
subir, nesta ordem: a variável `DATA_DA_VERSAO` (ISO 8601 com fuso), o arquivo `versao_da_aplicacao.txt` preenchido
pelo `git archive` e o `git log -1 --format=%cI`. Sem nenhuma, **não há rótulo**: nunca se mostra uma data inventada.
A rota `GET /api/versao` (sem login, porque a tela de login também mostra) devolve só o texto pronto,
`{"texto": "Atualizado em 29/09/2026 às 14:30"}` (horário de Brasília, UTC−3) ou `{"texto": null}`, sem o código do
commit nem nenhum dado de empresa. O `front/js/data_da_versao.js` preenche o parágrafo escondido
`[data-data-da-versao]` do rodapé das 14 telas (login, as 5 da empresa e as 8 do Portal Interno), que só aparece
quando o texto chega.

**Porquê.** A data sai de uma fonte só para todas as telas, e o caminho da publicação não muda: a imagem montada pelo
`git archive` já leva a data certa. O rótulo nunca mente: sem data confiável, ele não aparece.

**Trade-off.** Uma rota a mais abre sem login. Ela diz só a data da versão, que a tela de login mostra de qualquer
jeito. Os testes de segurança listam a rota entre as liberadas (`tests/seguranca/test_seg_acesso.py`). Uma imagem
montada com `docker compose build` direto da pasta (sem o `git archive`) fica sem rótulo, a menos que se passe
`DATA_DA_VERSAO`. A data é lida ao subir: uma versão nova aparece depois de religar o servidor, e a tela aberta mostra
a nova data ao ser recarregada.

**Como comprovar.** `tests/test_versao_da_aplicacao.py` (16 testes: a leitura da data, o horário de Brasília com
commits de outros fusos, com Git, sem Git e sem o programa git, o arquivo preenchido, com o marcador e ilegível, o `git archive`
de verdade trocando o marcador, a ordem das fontes, a leitura uma vez só, a rota sem login e sem data, e as 14 telas
com o lugar e o script), as 3 listas de rotas liberadas em `tests/seguranca/test_seg_acesso.py` e o roteiro de clique
`data_da_versao` (o login, a Home e Acompanhar da empresa e o Início do banco com a data do Git; sem data ou com erro
500, o rótulo não aparece).

**Origem.** Pedido da usuária, 2026-09-29.

<a id="adr-131"></a>

### ADR-131 · Custo da IA em cada execução, teto de gasto por dia e por mês (a IA pausa) e o Conferidor só com a dúvida forte ✅

**Contexto (2026-09-29, rodada 02 do QA da jornada com a IA real; achados D28 e D26).**
- **D28:** a tabela `execucoes_agentes` tinha as colunas de tokens e de custo, mas gravava tudo vazio: quem registrava
  a execução não via as chamadas feitas dentro do agente. E o teto de gasto do `LLMClient` valia por cliente, e cada
  pedido cria o seu: cem pedidos de US$ 0,50 passavam, um por um, por baixo do teto de US$ 10. O QA mediu o gasto por
  fora (`ligar_a_medicao`).
- **D26:** o Conferidor da Leitura (ADR-105) aparecia como "Uma segunda IA desconfia deste valor: o documento diz que o
  CPF é do cliente, não do funcionário Confira no seu arquivo..." (jargão, sem pontuação, uma ordem no lugar de uma
  pergunta) e levantava dúvida falsa sobre o salário por causa do vale-alimentação.

**Opções.**
- **Custo:** (a) cada agente devolve o próprio uso e quem registra soma; (b) **uma medição por execução**, em que o
  cliente de IA anota cada resposta e quem registra entrega o que ela somou; (c) uma ferramenta de rastreamento
  externa (Langfuse ou Phoenix).
- **Teto:** (a) manter o teto por cliente; (b) um teto por sessão de usuário; (c) **um teto por dia, somado no banco,
  valendo para a aplicação inteira**.
- **Conferidor:** (a) só trocar o texto fixo; (b) pedir a confiança à IA e perguntar só na "alta"; (c) **exigir o valor
  que o documento dá para a pessoa e o campo, descartar a suspeita quando é o mesmo valor lido, e montar a pergunta
  pelo código**.

**Decisão.**
- **Custo, (b):** `services/uso_da_ia.py` abre uma medição por execução (`with uso_da_ia.medir() as uso:`), guardada
  numa variável de contexto do Python: cada pedido à API tem a sua, e uma medição aberta dentro de outra não soma na de
  fora (nada conta duas vezes). O `LLMClient.gerar` anota toda resposta na medição aberta. O `execucoes.registrar`
  recebe o `uso` e grava tokens e custo; sem medição, ficam vazios ("não medido", ADR-36). Onde há chamadas em outra
  linha de execução, o uso vai explícito: o Leitor desconta a parte do Conferidor (cada um paga o seu) e o Redator de
  perguntas leva o contexto junto (`copy_context`). No Consultor, o custo vai só na linha da pergunta inteira, e as
  linhas das ferramentas ficam sem custo.
- **A queda para o MOCK deixa de passar por "OK":** se a IA real deveria ter respondido e caiu para a resposta simulada
  (limite, teto da sessão ou provedor fora), a execução vira ERRO, com o tipo `IAIndisponivel`. Isso cobre o achado
  2 do plano de avaliação (a queda silenciosa), do lado da medição. (O teto de gasto da aplicação não cai mais para
  o MOCK: ele pausa a IA; ver a revisão abaixo.)
- **Teto, (c):** `services/teto_de_gasto.py` soma o custo de toda chamada real na tabela `gasto_da_ia_por_dia` (uma
  linha por dia do calendário de Brasília; o mês é a soma dos dias). Há dois tetos, o do **dia** e o do **mês**, e o
  que for atingido primeiro pausa a IA (ver a revisão abaixo). O teto do cliente continua valendo. Se o banco falhar
  na conta do teto, a chamada segue e o erro vai para o log: a conta do teto nunca derruba o trabalho da empresa.
- **Tela** (Acompanhamento dos agentes): o cartão fixo "US$ 10 por sessão" virou o **gasto de hoje e do mês × os
  tetos**, que chama a atenção e diz qual teto pausou a IA quando um deles é atingido. Entrou a tabela **"Custo da IA por etapa"** (por agente e etapa: as
  execuções, quantas foram medidas, os tokens e o custo total e médio). Os cartões dos agentes e as execuções recentes
  já mostravam o custo, que agora chega.
- **Conferidor, (c), prompt `conferidor_da_leitura_v2`:** a regra geral é que citar outro valor perto não é erro. A IA
  devolve o `valor_no_documento`, e o código descarta a suspeita quando ele é o mesmo valor lido, escrito de outro
  jeito (a mesma data, o mesmo número em dinheiro, os mesmos dígitos em CPF e outros números, o texto sem pontuação
  nos outros campos; ver a revisão abaixo). O
  código também descarta o valor longo, com várias linhas, com "?" ou com link. A pergunta é montada pelo código:
  "Confira este valor: no documento está X, mas ficou Y. Qual é o certo?", com o salário em reais. O texto livre da
  IA (o motivo) não vai mais para a tela. A contagem de aceitação reconhece o começo novo e o da v1.

**Porquê.** Sem o custo por execução, a pergunta "quanto custa um arquivo, uma empresa, um funcionário?" não tinha
resposta: é a família de custo do plano de avaliação. O teto por dia é o único que protege o bolso quando muitos pedidos
pequenos se somam; o do mês protege o orçamento do site publicado (US$ 20 por mês). No Conferidor, cada alarme falso vira trabalho para a empresa. A regra "só com o valor certo do
documento, e diferente do lido" é geral: não depende de palavra, arquivo ou empresa. E a pergunta montada pelo código
é sempre curta, sem jargão e sem espaço para um link vindo da IA.

**Trade-off.**
- A medição depende de a execução abrir o `medir()`: um agente novo que não abrir a medição continua com o custo vazio
  ("não medido", nunca um zero). O teto do dia soma assim mesmo, porque é o cliente que soma.
- Uma chamada que passa do tempo limite (o Redator) termina depois do registro: o custo dela entra no teto do dia, mas
  não na linha da execução.
- Cada chamada real faz algumas leituras e uma gravação a mais no banco (a conta dos tetos).
- **Risco conhecido:** a conferência do teto e a soma do custo não são uma operação só. Pedidos ao mesmo tempo podem
  passar juntos pela conferência e ultrapassar o teto em poucas chamadas (centavos). O teto do cliente continua
  limitando cada pedido. Uma trava no banco resolveria, ao custo de fila entre os pedidos: fica para quando o volume
  pedir.
- **Pedido futuro:** um arquivo que precisa da IA (Word, fichas) é recusado durante a pausa, e a empresa envia de novo
  depois. Guardar o arquivo e processá-lo sozinho quando o teto liberar fica para um pedido novo.
- As outras quedas para o MOCK continuam devolvendo a resposta simulada ao agente, como antes (o Leitor já recusava).
  Agora elas aparecem como ERRO na Telemetria.
- No Conferidor, a suspeita sem o valor certo no documento (ex.: um bônus lido como salário, sem o salário escrito)
  deixa de virar pergunta: perde-se um pouco de recall para ganhar muito em alarme falso. Uma data escrita por extenso
  no documento ("9 de setembro de 2026") não se iguala a "09/09/2026", e ainda pode gerar uma pergunta.

**Como comprovar.**
- **EXP-016** (IA real, US$ 0,13): nos mesmos documentos e com 3 repetições, os alarmes falsos caíram de 7 a 10 para
  **0** nas armadilhas e de 3 a 4 para **0** no desenvolvimento. Os erros de verdade seguem todos achados (5/5 e 18/18),
  e as perguntas simples passaram de 0% para 100%. O conjunto de armadilhas é novo, sintético e foi congelado antes da
  primeira medição.
- **`tests/test_uso_e_teto_da_ia.py`** (26 testes):
  - a medição soma só as chamadas de dentro dela, a de dentro não soma na de fora, e a medição atravessa para outra
    linha de execução com o contexto;
  - a execução grava tokens e custo, e sem medição eles ficam vazios;
  - a queda para o MOCK vira ERRO com o tipo certo;
  - os tetos começam em US$ 20 e moram no banco, `gravar_teto` recusa 8 valores impossíveis, o gasto do mês soma só
    os dias do mês (com a virada do ano), o teto do dia e o do mês pausam a IA sem resposta simulada, subir o teto
    libera na hora, o MOCK nunca pausa, o modelo sem preço avisa no log, e o banco fora do ar não derruba a chamada;
  - a pausa em cada lugar: o envio espera sem contar como falha (5 pausas seguidas, nenhuma rejeição), a leitura de
    Word recusa o arquivo com o recado e leva a execução com ERRO, o Consultor grava o ERRO, e a API devolve 503
    com o recado da empresa ou do banco, conforme a rota;
  - o dia do teto é o de Brasília;
  - a leitura separa o uso do Leitor do uso do Conferidor;
  - a etapa do fluxo grava o uso do seu trabalho;
  - o custo por etapa não inventa zero;
  - a aceitação reconhece a pergunta nova e a da v1.
- **`tests/test_tentar_de_novo.py`** (5 testes): o envio pausado pelo teto do dia ou do mês fica guardado e só volta
  com o teto livre; uma falha comum também é retomada; outra empresa recebe 404 mesmo com o teto atingido; o envio
  em outra etapa recebe 400; e, pela API, 503 com o recado, 404 para outra empresa e 200 com a leitura ao liberar.
- **`tests/test_conferidor_da_leitura.py`**, com variações que ninguém usou (outros formatos de dinheiro, CPF, data e
  texto; valores impróprios; a régua da pergunta):
  - o mesmo valor escrito de outro jeito não pergunta;
  - o valor diferente pergunta;
  - sem o valor do documento, ou com valor impróprio, a suspeita cai;
  - a pergunta é simples e não leva o motivo;
  - os zeros do fim contam: um salário 10× maior ou menor, um CPF sem os zeros e uma data diferente perguntam, e o
    mesmo valor em outro formato (padrão americano, ISO, sem zeros à esquerda) não pergunta; o conversor de
    dinheiro recusa o que não é dinheiro.
- **`tests/seguranca/test_seg_ia.py`:** o D-26 (link no motivo) deixou de ser `xfail`.

**Revisão de 2026-09-29 (revisor-codigo e decisão da usuária).**
- **Conserto (o revisor bloqueou):** a comparação "é o mesmo valor?" do Conferidor tirava os zeros do fim dos dígitos,
  e por isso "650.00" = "R$ 6.500,00" e o CPF "12345678900" = "123456789": a dúvida forte (um salário 10× errado) era
  descartada. Agora cada tipo tem a sua regra geral: **datas** comparam a data (dd/mm/aaaa, aaaa-mm-dd, com barra,
  traço ou ponto); **dinheiro** (com "R$", centavos ou milhar) vira número, no padrão brasileiro ou americano; **CPF e
  outros números** comparam todos os dígitos; **texto** compara sem pontuação nem maiúsculas.
  - **Efeito no EXP-016, provado sem gastar:** o resultado bruto guarda só as suspeitas que passaram pelo filtro, então
    não dá para recalcular. Uma varredura cruzou cada valor lido (e plantado) com cada número de cada documento dos
    dois conjuntos: nas 18 armadilhas, **nenhum** par muda de resposta; no desenvolvimento, só um (o número da casa
    "30" × um "3" citado). Nenhum salário, CPF ou data colide: os achados (5/5 e 18/18) e os alarmes falsos de salário,
    CPF e data do EXP-016 não dependiam do defeito. Uma nova medição com a IA real (≈ US$ 0,05) confirmaria, com o ok
    da usuária.
- **A IA pausa e avisa (decisão da usuária):** atingido o teto do dia ou do mês, o cliente de IA levanta
  `TetoDeGastoAtingido`, e nenhuma resposta simulada entra no lugar da real.
  - **Envio da empresa:** a etapa vai para `aguardar_nova_tentativa`, **sem contar como falha** (nunca chega às 3 que
    rejeitam o envio), com o recado "A análise automática está indisponível agora. Seu envio fica guardado, e o
    banco já foi avisado." (o texto não manda clicar em nada até o botão existir; decisão da usuária). O envio não
    se perde e é retomado pela rota abaixo.
  - **Arquivo que precisa da IA para ser lido (Word, fichas):** é recusado com "A análise automática está indisponível
    agora; tente enviar de novo mais tarde.", e a empresa continua com ele (decisão da usuária).
  - **Assistente de Correção, Consultor e Endomarketing:** a API devolve 503 com o recado de quem está na tela (o do
    banco diz que é o teto e que ele pode ser ajustado).
  - **O banco fica sabendo:** toda pausa grava uma execução com ERRO e o tipo `TetoDeGastoAtingido` na Telemetria, e o
    cartão do teto no Acompanhamento dos agentes diz qual teto pausou a IA.
- **A rota "tentar de novo" (decisão da usuária: a rota agora, o botão no pedido do `desenvolvedor`):**
  `POST /api/empresa/cadastro/{processamento_id}/tentar_de_novo` (`cadastro.tentar_de_novo`), sem corpo. Confere,
  nesta ordem: (1) o envio é da empresa da sessão, senão **404** (o isolamento vem antes de qualquer recado);
  (2) o envio está em `aguardar_nova_tentativa`, senão **400** com o motivo; (3) o teto ainda está atingido: **503**
  com o recado, sem mexer no fluxo (o envio continua guardado). Liberado, o fluxo refaz a etapa que parou e a rota
  devolve **200** com a leitura do envio. Serve também para a etapa que falhou por outro motivo. O botão na tela e a
  retomada automática quando o teto liberar ficam no pedido `pagina-do-teto-da-ia`, que troca o texto do aviso
  quando o botão existir.
- **Os tetos moram no banco de dados (decisão da usuária):** a tabela `limites_de_gasto_da_ia` guarda o teto do **dia**
  e o do **mês** (os dois começam em **US$ 20**), com quando e quem mudou. `teto_de_gasto.ler_tetos` e
  `teto_de_gasto.gravar_teto` (valor maior que zero e até US$ 1.000, com quem mudou) ficam prontos para a tela do
  especialista, que é o pedido `pagina-do-teto-da-ia` do `desenvolvedor` (a tela que lê e ajusta os tetos, e a
  retomada do envio pausado). Saiu o `TETO_DE_GASTO_DIARIO_USD` do `.env`.
- **Sugestões do revisor aplicadas:** a chamada real sem preço na tabela avisa no log qual modelo ficou de fora do teto;
  comentários e "recebe/devolve" em `teto_de_gasto.py` e `uso_da_ia.py`; o risco da conferência não atômica ficou
  registrado no trade-off.
- **2ª rodada do revisor:** a conferência do teto roda antes de cada chamada real, e antes ela criava as tabelas,
  gravava os tetos iniciais e confirmava a transação a cada leitura (umas 3 vezes por chamada, inclusive na conexão
  de quem chamou). Agora a leitura só cria as tabelas, se faltarem, uma vez por operação, e não grava nada: o teto
  que ninguém mudou vale o valor inicial, e a linha só nasce quando o especialista grava um valor.

**Altera** o ADR-105 (o prompt do Conferidor e o texto da pergunta) e o ADR-36 (tokens e custo passam a ser gravados).
**Origem.** Pedido da usuária pelo orquestrador (QA da jornada, D26 e D28), 2026-09-29.

---

<a id="adr-134"></a>

### ADR-134 · Hospedagem: uma EC2 t3.small na Virgínia, ligada o tempo todo, com swap, e a infraestrutura como código ✅

**Contexto (2026-09-29, agente publicador).** A demo da banca roda publicada (desvio de 2026-09-24; prioridade desde
2026-09-27). Faltava escolher onde, em que tamanho e como. A medição da memória, com a aplicação no Docker do
computador e sem IA, deu: a API com 140 MB parada, ~1,0 GB em uso (17 planilhas) e **1,56 GB de pico na primeira
subida** (quando monta os índices do RAG); o banco com ~70 MB. Com o Ubuntu, o Docker e o Caddy (~0,4 GB), o servidor
fica com ~1,5 GB em uso e ~2,0 GB na primeira subida.

**Opções.** (a) `t3.medium` (4 GB) ligada o tempo todo, ≈ US$ 36/mês; (b) **`t3.small` (2 GB) com 2 GB de swap,
ligada o tempo todo, ≈ US$ 21/mês**; (c) `t3.small` ligada só quando usada, com desligamento automático (60 minutos
sem uso e às 23h), ≈ US$ 6/mês parada mais US$ 0,02 por hora ligada.

**Decisão (b)** (escolha da usuária, 29/09: "não sei quando a banca vai avaliar... deixa ligado"). Tudo sai de um
modelo só, `publicacao/infraestrutura.yaml` (CloudFormation, pilha `integra-folha-producao`):
- **a máquina:** Ubuntu 24.04 (a imagem vem do parâmetro público da Canonical), disco gp3 de 30 GB criptografado, CPU
  em modo `standard` (a `t3` nasce em "unlimited" e pode cobrar CPU extra) e o acesso seguro aos próprios dados
  (IMDSv2);
- **o IP fixo** (`18.208.25.225`), o firewall (ADR-137), o bucket do backup e o papel da máquina (ADR-136) e o
  **alarme de orçamento** de US$ 60/mês (e-mail em 80% e 100%, e quando a previsão do mês passa do valor);
- **a região da Virgínia** (`us-east-1`): a mais barata, e a mesma de onde a aplicação chama o Bedrock (ADR-135);
- **a imagem sai do commit** (`git archive`), e não da pasta de trabalho, e é **construída no servidor** (escolha da
  usuária, 29/09): o Docker Desktop reserva 3 a 4 GB e não cabe na memória do computador com os terminais abertos
  (o vigia da memória parou a construção local com 0,7 GB de folga). A etiqueta da imagem é o código do commit;
- **publicar, conferir e voltar** num comando (`publicacao/publicar.sh`), com a volta automática à versão anterior
  se uma das provas do `publicacao/conferir.sh` falhar. Versão nova só com o "publica" da usuária.

**Porquê.** A medição cabe em 2 GB com o swap, pela metade do preço da `t3.medium`. A banca pode avaliar a qualquer
hora, e uma máquina desligada não abre. Como código, a hospedagem é recriada ou apagada com um comando, e a banca vê
exatamente o que existe.

**Trade-off.** A folga em uso intenso é pequena (~0,4 GB): com a IA real e vários usos ao mesmo tempo, a máquina pode
usar o swap e ficar mais lenta. O degrau é a `t3.medium` (o parâmetro `TipoDaMaquina` da pilha; ~2 minutos fora do ar).
A máquina ligada cobra mesmo sem visitas. É uma máquina só: se ela cair, o site cai (a volta é recriar pelo modelo e
restaurar o backup).

**Como comprovar.** A pilha em `CREATE_COMPLETE`; o `bash publicacao/conferir.sh <etiqueta>` com as 11 provas "OK"
(29/09, versão `ac93d15`); no servidor, `free -m` com 740 MB usados de 1,9 GB em repouso.
**Origem.** Pedido da usuária ao agente publicador, 2026-09-29.

---

<a id="adr-135"></a>

### ADR-135 · Retenção zero do Bedrock gravada na conta (modo none, na Virgínia) ✅

**Contexto (2026-09-29).** O ADR-101 (a IA vê os dados reais) diz que "a proteção depende de a IA rodar pelo Bedrock
com retenção zero". Conferida pela API, a conta estava em `inherit` nas três regiões dos EUA: sem regra própria, cada
modelo seguia o próprio padrão. Os modelos em uso (Sonnet 4.6 e Nova 2 Lite) não guardam os pedidos, mas isso era a
regra de cada modelo, e não uma trava da conta. A configuração não tem tela no console: só se grava pela API.

**Opções.** (a) Deixar em `inherit`; (b) **gravar `none` só na Virgínia**, a região de onde a aplicação chama a IA;
(c) gravar `none` nas três regiões dos EUA.

**Decisão (b)** (escolha da usuária, 29/09). Ela gravou pelo CloudShell, com a conta principal
(`aws bedrock put-account-data-retention --mode none --region us-east-1`, 09:19 UTC), e o publicador conferiu pela
leitura. O `.env` de produção fixa `REGIAO_BEDROCK=us-east-1`, e o `conferir.sh` prova isso a cada publicação.

**Porquê.** Com o perfil geográfico "us.", os pedidos são processados em três regiões, mas o modo de retenção **é
conferido na região de origem da chamada** (AWS Security Blog, "Enforce zero data retention on Amazon Bedrock...",
seção "Data retention and cross-Region inference"). Com `none`, a própria AWS barra, na origem, os modelos que exigem
guardar os pedidos por até 30 dias (hoje o GPT-5.6 Luna e o Claude Fable 5, entre outros): é a segunda trava do
ADR-96, agora na conta. O Sonnet 4.6 e o Nova 2 Lite não estão na lista dos que guardam e continuam funcionando.

**Trade-off.** Se alguém mudar a região de chamada da aplicação, a trava deixa de valer (por isso a prova no
`conferir.sh`). Mesmo com `none`, a AWS pode reter conteúdo marcado como abuso sexual infantil, por obrigação legal. Um
modelo novo que exija retenção fica indisponível até uma decisão explícita.

**Como comprovar.** `aws bedrock get-account-data-retention --region us-east-1` devolve `"mode": "none"`; a prova "IA
chamada pela Virgínia" do `conferir.sh`. Conceito explicado no vault (`01-Fundamentos/Retenção zero`).
**Origem.** Pergunta da usuária ao agente publicador ("antes de decidir, quero entender"), 2026-09-29.

---

<a id="adr-136"></a>

### ADR-136 · Backup diário no S3 privado, gravado pelo papel da máquina, que não consegue apagar 🧪

**Contexto (2026-09-29).** O site guarda dados que só existem no servidor (os envios, os mapeamentos homologados e os
índices do RAG). Uma versão nova que estrague o banco, ou a perda da máquina, não pode levar tudo junto.

**Opções.** (a) Cópias do disco inteiro (snapshots do EBS); (b) **o `pg_dump` do banco e um pacote do volume
`storage`, mandados para um bucket S3 privado**; (c) sem backup.

**Decisão (b)**, em `publicacao/fazer_backup.sh`:
- **o que entra:** o banco inteiro e o volume `storage` (índices do RAG e arquivos enviados), sem o modelo de
  embeddings, que é baixado de novo sozinho;
- **quando:** toda noite às 3h (horário de Brasília) e antes de cada troca de versão (o ponto de volta, se a versão
  nova mexer no banco);
- **onde:** `s3://integra-folha-backup-<conta>/backup/<data e hora>/`, num bucket privado (bloqueio de acesso
  público), criptografado, com versões, que apaga sozinho o que passa de 30 dias e **sobrevive se a pilha for
  apagada**;
- **quem grava:** o papel da máquina, sem chave nenhuma guardada no servidor, e só com permissão de **gravar** na pasta
  `backup/`: não consegue apagar nem listar.

**Porquê.** O arquivo é pequeno e portátil (restaura em outra máquina, ou no computador), custa centavos, e um invasor
na máquina não apagaria o backup.

**Trade-off.** A janela de perda é de até um dia. **A restauração ainda não foi testada:** backup que nunca foi
restaurado não vale. O teste fica registrado no `docs/hospedagem.md` quando for feito.

**Como comprovar.** Em 29/09: o primeiro backup (banco com 6,6 KB e `storage` com 686 KB) no bucket; na máquina,
`aws s3 cp` permitido, e `aws s3 rm` e `aws s3 ls` com `AccessDenied`.
**Origem.** A ficha do agente publicador (pedido da usuária), 2026-09-29.

---

<a id="adr-137"></a>

### ADR-137 · O Caddy como porteiro: https automático, e a aplicação e o banco sem porta para fora ✅

**Contexto (2026-09-29).** O site precisa de https com certificado válido, e a aplicação (porta 8000) e o banco (porta
5432) não podem ficar abertos para a internet. Há uma armadilha conhecida: o Docker publica portas passando por cima do
firewall do Ubuntu (`ufw`).

**Opções.** (a) **O Caddy** (proxy reverso com https automático do Let's Encrypt, numa configuração de poucas linhas);
(b) Nginx com o certbot (mais peças e a renovação por um agendador); (c) o balanceador de carga da AWS com um
certificado da própria AWS (cerca de US$ 16/mês a mais).

**Decisão (a).** Em `publicacao/compose.prod.yml`, o Caddy é o **único serviço com portas** (80, 443 e 443/udp); a
aplicação e o banco ficam com `ports: !reset []` e só se falam pela rede interna do Docker. O `publicacao/Caddyfile`
atende `integrafolha.com.br`, manda o `www` para ele (301), comprime as respostas e pede o https sempre (HSTS de um
ano). O uvicorn confia no cabeçalho do Caddy (`--proxy-headers`, ADR-108) e marca o cookie de login como seguro.

**Porquê.** O menor custo e o menor número de peças: o certificado sai e se renova sozinho, e a configuração cabe numa
tela. A banca entende o desenho: uma porta de entrada, e o resto trancado.

**Trade-off.** O volume `dados_do_caddy` guarda o certificado e não pode ser apagado (pedir de novo tem limite por
semana no Let's Encrypt). O cabeçalho HSTS sai duas vezes (do Caddy e da aplicação), sem efeito prático. Nenhum serviço
novo pode ganhar porta sem passar pelo Caddy.

**Como comprovar.** O `conferir.sh`: o http leva ao https (308), o certificado é válido (Let's Encrypt, até
28/12/2026), a porta 8000 e a 5432 fechadas por fora e, no servidor, só 22, 80 e 443 escutando para fora.
**Origem.** A ficha do agente publicador (pedido da usuária), 2026-09-29.

### ADR-138 · Acompanhar: os números 2 a 2, a conversa no painel do lado e a grade que mostra o valor que acabou de mudar ✅

**Contexto (2026-09-29, pedido acompanhar-layout-e-grade).** A usuária pediu duas coisas na tela "Acompanhar
cadastros": (1) "quando a IA corrigir um valor, o grid abaixo [...] precisa ser atualizado com esse valor"; (2) os 4
números "organizados 2 a 2", com o "Depois do cadastro" do lado deles, e a conversa com a IA, "que hoje abre ali mesmo",
aberta na seção do lado, "para ver a conversa do momento de forma mais organizada". Na investigação, a grade **já**
recebia o valor novo em todos os caminhos (cartão, "para todos", CNPJ/endereço da empresa, pessoa a pessoa, valor
digitado e Desfazer), mas só **depois** de a lista de pendências voltar do servidor. Com a IA de verdade, essa lista pode
levar alguns segundos, porque a IA escreve as perguntas novas. Além disso, o valor fica numa das ~46 colunas, muitas
vezes fora da tela, sem nenhum sinal de que mudou.

**Opções.** Grade: (a) recarregar a página inteira depois de cada mudança: perde a conversa e a rolagem; (b) a rota da
conversa devolver a linha nova da grade: muda o servidor e duplica o que `/api/empresa/funcionarios` já faz; (c)
**buscar a grade junto com as pendências e destacar a célula que mudou**. Layout: (a) a conversa continuar dentro do
cartão; (b) uma janela por cima da tela; (c) **um painel do lado, que acompanha a rolagem e mostra uma coisa por
vez: o "Depois do cadastro" ou a conversa do cartão escolhido**. Com a conversa aberta, o "Depois do cadastro" some ou
vira uma aba; no celular, a conversa abre embaixo do cartão ou em tela cheia.

**Decisão.** Grade (c) e layout (c), com as escolhas da usuária: **o "Depois do cadastro" some e volta ao fechar**, e
**no celular a conversa abre em tela cheia**, com o "Voltar à lista".
- **A grade.** O `recarregar_a_tela_inteira` busca os funcionários antes de esperar as pendências. A tela compara a lista
  nova com a anterior, pela mesma pessoa (o envio com o CPF, ou o envio com o nome, porque a correção pode ter mudado
  justamente o CPF), e a célula de cada campo que mudou fica amarela por 20 segundos, com a dica "Valor atualizado
  agora". A regra vale para qualquer campo e qualquer arquivo, sem nenhum nome de coluna fixo. A grade e a lista final
  ("Conferir e enviar", ADR-126) leem os mesmos dados atuais do servidor (`correcoes.dados_atuais`).
- **O bloco de cima.** Duas colunas: à esquerda, os 4 números (2 a 2) e, embaixo, a lista das pendências; à direita, o
  painel do lado (`position: sticky`). Os cartões da lista ficam **compactos**: o título, o problema, a pergunta do
  agente em até 2 linhas, o "Abrir a conversa ›" e o arquivo. O clique abre a conversa no painel, e o cartão fica
  marcado. A conversa é a mesma de antes (`js/assistente_de_correcao.js`), só em outro lugar
  (`front/js/painel_da_conversa.js`). Resolvida, ela continua no painel com o "Pronto" e o Desfazer. O X (ou o Esc)
  fecha. Se o cartão sair da lista ou ficar escondido por um filtro, o painel volta sozinho ao "Depois do cadastro".
  O "Ver a conversa" das Resolvidas também abre no painel. O "Pronto para enviar ao banco" passou para logo abaixo do
  bloco. No celular (até 1024 px): os números, o "Depois do cadastro" e a lista, e a conversa em tela cheia.

**Porquê.** A pessoa vê a conversa inteira do lado, sem a lista "pular", e vê na grade o que a IA acabou de mudar. A
grade não depende mais da velocidade da IA. Nada muda no servidor nem no que a IA responde.

**Trade-off.** O destaque não acha a pessoa quando a mesma correção muda o CPF **e** o nome ao mesmo tempo, ou quando há
dois homônimos sem CPF no mesmo envio: o valor novo aparece, só não fica amarelo. A conversa agora pede um clique a mais
(escolher o cartão). Os roteiros de clique que conversavam dentro do cartão passaram a abrir o cartão e usar o painel.

**Como comprovar.** O roteiro de clique `acompanhar_layout_e_grade` confere: os números 2 a 2 com o painel do lado e a
lista embaixo; os cartões compactos; a conversa no painel; o CPF corrigido na grade, destacado, sem recarregar a página;
o Desfazer, com o CPF de antes na grade; o X; a resolvida no painel; e o celular (a ordem, sem rolagem para o lado, e a
tela cheia com o "Voltar à lista"). Os roteiros antigos de Acompanhar continuam verdes, ajustados ao painel.

**Origem.** Pedido da usuária, 2026-09-29.

<a id="adr-139"></a>

### ADR-139 · A página "Teto de gasto da IA", a faixa de aviso e a retomada automática dos envios pausados ✅

**Contexto (2026-09-29, pedido pagina-do-teto-da-ia).** O ADR-131 fez a IA pausar quando o gasto do dia ou do mês chega
ao teto e guardou os dois tetos no banco de dados, com as funções `ler_tetos` e `gravar_teto` prontas. A usuária
pediu: "o teto precisa ser configurável para o banco poder ajustar. Precisamos criar uma página pra quando isso
acontecer o especialista conseguir ajustar". Ela também decidiu que os envios parados pelo teto voltam sozinhos quando
o teto sobe ou quando o dia (ou o mês) vira, e que a tela da empresa ganha o botão "Tentar de novo" (a rota é do
ADR-131).

**Opções.**
- **Onde o especialista acessa:**
  - (a) um item novo no menu da engrenagem;
  - (b) só a Telemetria;
  - (c) o painel dos dados da IA, mais uma faixa no alto das outras telas enquanto a IA estiver pausada.
- **O registro das mudanças:**
  - (a) só a última mudança, que a tabela `limites_de_gasto_da_ia` já guarda;
  - (b) o histórico completo, numa tabela nova.
- **A retomada automática:**
  - (a) só quando o teto sobe;
  - (b) quando o teto sobe e numa conferência periódica, que pega a virada do dia e do mês.

**Decisão.** Acesso (c), histórico (b) e retomada (b), escolhidos pela usuária: "como estamos falando de IA,
precisamos ter uma forma de acessar no painel dos dados da IA", mais a faixa no alto das outras telas.
- **Página `banco_teto_da_ia.html`** (só BANCO). Ela mostra:
  - a situação: "funcionando" ou "pausada", desde quando e quando a IA volta sozinha;
  - o gasto de hoje × o teto do dia e o gasto do mês × o teto do mês;
  - quantos envios de empresas estão esperando. É só o número, nunca a lista (ADR-102);
  - um campo e um botão para cada teto, com a última mudança (quem e quando);
  - o histórico das mudanças.
  - **"Desde quando"** é a primeira chamada barrada pelo teto (a execução com o tipo `TetoDeGastoAtingido`) no período
    atual, contada a partir da última mudança de um teto. Sem chamada barrada, não há "desde".
- **Os avisos do ajuste:**
  - antes de salvar, e de novo na resposta do servidor, a página avisa quando o valor não passa do gasto já feito
    (a IA fica pausada) e quando o teto do dia passa do do mês (o do dia nunca pausaria);
  - as recusas são as regras do `gravar_teto`: não é número, zero ou negativo, acima de US$ 1.000 ou período
    desconhecido. Somam-se o mesmo valor ("nada mudou") e NaN ou infinito, que as comparações do `gravar_teto`
    deixariam passar.
- **Acesso:**
  - o link "Ver e ajustar o teto" fica no cartão do teto em Acompanhamento dos agentes;
  - a faixa amarela "A IA está pausada" (`js/aviso_do_teto_da_ia.js`) aparece nas outras 7 telas do Portal Interno
    só com o teto atingido. Ela é atualizada ao voltar para a aba e a cada minuto;
  - a engrenagem não ganhou item.
- **Rotas (só BANCO):**
  - `GET /api/banco/teto_da_ia`: a situação;
  - `POST /api/banco/teto_da_ia`, com `{periodo, valor_usd}`: um teto por vez, pelo `gravar_teto`, e mais uma linha
    em `mudancas_do_teto_da_ia`;
  - `GET /api/banco/teto_da_ia/aviso`, com `{atingido}`: a consulta leve da faixa.
  - O serviço é `services/pagina_do_teto_da_ia.py`. A regra do teto continua só em `services/teto_de_gasto.py`.
- **Retomada automática:**
  - um envio é "pausado pelo teto" quando está em `aguardar_nova_tentativa` com o recado da pausa. O parado por outra
    falha continua esperando o clique;
  - a retomada chama o mesmo `cadastro.tentar_de_novo` do botão;
  - ela roda em segundo plano depois do `POST` que libera a IA e a cada 5 minutos. A conferência periódica é uma linha
    de fundo ligada na partida do servidor (`router.on_startup`), e os testes não a ligam;
  - só uma retomada roda de cada vez, e ela para quando um teto é atingido de novo.
- **Tela da empresa (Cadastrar):**
  - o envio parado ganha o botão "Tentar de novo";
  - o recado do envio pausado passou a ser: "A análise automática está indisponível agora. Seu envio fica guardado:
    clique em "Tentar de novo" mais tarde." (`RECADO_DO_ENVIO_PAUSADO`, aplicado em `leitura_do_envio`);
  - o recado geral do 503 não mudou, porque aparece também no Assistente de Correção, onde não há o botão.

**Porquê.** O especialista vê a pausa onde já olha os dados da IA, e é avisado em qualquer tela enquanto a IA está
parada. O histórico completo deixa cada mudança de dinheiro auditável. A retomada automática cumpre o que o aviso à
empresa promete ("seu envio fica guardado") sem depender de ela voltar. A regra do teto continua num lugar só.

**Trade-off.**
- Os envios pausados são achados pelas execuções com o tipo da pausa, conferindo o fluxo de cada um. Com milhares de
  envios pausados, a conta da página fica lenta. Hoje são poucos.
- **Risco conhecido:** a trava da retomada vale só para ela. Se a empresa clicar em "Tentar de novo" no mesmo instante
  em que a retomada pega o mesmo envio, as duas podem se cruzar. A trava fica na memória de um servidor: com vários
  processos (publicação com mais de um trabalhador), cada um teria a sua retomada.
- O teto e a linha do histórico vão numa transação só: a linha entra primeiro, sem confirmar, e o `gravar_teto`
  confirma as duas. Se ele recusar o valor, a linha é desfeita (revisão do revisor-codigo).
- Os envios esperando são os que têm a pausa como **última** execução. Um envio pausado que depois ganhou outra
  execução sem sair do lugar não volta sozinho e continua esperando o clique da empresa (a saída segura).
- A virada do dia aparece em até 5 minutos.

**Como comprovar.**
- `tests/test_pagina_do_teto_da_ia.py` (33 testes), que prova:
  - a situação num banco novo;
  - o ajuste e o histórico, com a vírgula do português;
  - 11 recusas sem gravar nada;
  - os avisos;
  - o "desde quando", sem contar a pausa de antes de um ajuste;
  - subir o teto libera na hora;
  - só o envio parado pelo teto volta;
  - a retomada para no teto, segue depois de um envio que quebra e não roda em dobro;
  - a retomada em segundo plano nunca derruba nada;
  - a linha de fundo liga uma vez só, na partida;
  - pela API: 401, 403, só o número de envios, 400 com o motivo e o envio que volta depois do `POST`.
- O roteiro de clique `teto_de_gasto_da_ia` percorre as duas pontas:
  - a empresa vê o recado e o botão, e o clique com a IA pausada não muda nada;
  - a faixa e o link levam à página, que mostra a pausa, recusa o teto negativo e avisa antes de salvar;
  - subir os tetos libera a IA, e o envio volta sozinho.

**Altera** o ADR-131: o recado do envio pausado e o botão "Tentar de novo".
**Origem.** Pedido da usuária pelo orquestrador, 2026-09-29.

### ADR-145 · A falha da IA real pausa o trabalho e nunca vira resposta simulada ✅

> **Alterado pelo [ADR-147](#adr-147) (2026-09-30):** na checagem do Bedrock Guardrails (a nova segunda opinião do
> guardrail de injeção), o tempo estourado não pausa: a mensagem segue com o resultado da lista, e a Telemetria
> registra. A pausa continua valendo para a IA que prepara as respostas.

**Contexto (2026-09-29, pedido quatro-obrigatorios-e-falha-pausa).** Fora do MOCK, o cliente de IA
(`services/llm_client.py`) trocava a resposta por uma simulada, sem erro, em três casos:
- o limite de 50 chamadas da operação;
- o teto de US$ 10 do cliente;
- qualquer falha do provedor (fora do ar, sem permissão, tempo esgotado).

Era a "queda para o MOCK" do ADR-36, feita para a demo local não travar. Só o teto do dia e do mês pausava (ADR-131), e
só o Leitor de Documentos recusava a resposta simulada (EXP-010). Com a IA real no site, uma empresa de verdade
receberia um mapeamento simulado, e errado, sem saber. O achado veio do levantamento do desenho forte (item 4 dos
insumos do arquiteto). A usuária decidiu: a falha pausa o envio, com a mesma pausa e o "Tentar de novo" do ADR-139;
nunca simula no servidor; o MOCK de reserva fica só na máquina local, ligado por uma chave do `.env`.

**Opções.**
- (a) manter a queda para o MOCK e marcar na tela que a resposta foi simulada;
- (b) cada agente conferir se a resposta veio simulada, como o Leitor já fazia;
- (c) o cliente de IA levantar o erro, e cada lugar que chama a IA pausar do seu jeito.

**Decisão.** (c).
- **O cliente de IA** levanta `IAIndisponivel` nos três casos.
  - A classe saiu do Leitor e passou a morar no cliente; o nome continua valendo no Leitor.
  - A mensagem é o recado da pausa para a empresa. O motivo técnico fica no atributo `motivo` e nunca vai para a tela.
    O registro do servidor guarda o que aconteceu: o limite da operação, o teto do cliente ou só o tipo do erro do
    provedor, porque a mensagem dele pode trazer endereços internos (sugestão do revisor-codigo).
- **O MOCK de reserva:** a chave `MOCK_DE_RESERVA=sim` do `.env` devolve o comportamento antigo, só na máquina local
  (a demo sem rede e as medições, que recusam a resposta simulada e contam a falha). O padrão é `nao`.
  - O servidor nunca recebe a chave: o contêiner só recebe as variáveis listadas no `docker-compose.yml`, e o `.env`
    não entra na imagem (`.dockerignore`). Um teste confere os arquivos.
  - A bateria de testes força a chave desligada (`tests/conftest.py`): o `.env` de quem roda não muda o resultado.
- **Onde a IA pausa:**
  - **o fluxo da empresa:** a etapa fica em `aguardar_nova_tentativa`, com o recado da pausa, sem contar como falha.
    Nenhuma quantidade de falhas rejeita o envio. A tela já mostra o botão "Tentar de novo" (ADR-139), que refaz a
    etapa;
  - **a conversa com o Agente de validação e o material do Endomarketing:** gravam o ERRO, e a API avisa com 503;
  - **a leitura de Word e de fichas:** o documento não entra ("indisponível agora; tente de novo"), como já era. O
    Conferidor que não responde também para a leitura; antes, ela seguia sem a conferência;
  - **o guardrail de injeção sem a segunda opinião:** a mensagem não passa; antes, passava como normal;
  - **a API:** um aviso 503 próprio. A empresa recebe o recado da pausa; o especialista do banco recebe "A IA não
    respondeu agora (falha no provedor de IA), e nada foi simulado no lugar...".
- **A Telemetria:** o ERRO com o tipo `IAIndisponivel` (`execucoes.registrar_queda_da_ia`), ao lado do
  `TetoDeGastoAtingido`.
- **O que não mudou, de propósito:**
  - as perguntas dos cartões: sem a IA, o cartão usa a frase de reserva, que é um texto fixo, e não uma simulação;
  - a retomada automática continua só para a pausa do teto. Não se sabe quando o provedor volta, e tentar sozinho a
    cada 5 minutos encheria a Telemetria de ERROs: o envio parado pela falha espera o clique da empresa;
  - o erro de configuração (falta a chave ou o modelo no `.env`) continua um erro visível.

**Porquê.** Uma resposta inventada nunca pode passar por real: é a mesma regra do ADR-36 para os números da
Telemetria. A pausa que já existia para o teto dá à empresa um caminho conhecido: o envio fica guardado e volta pelo
"Tentar de novo". Levantar o erro num lugar só, o cliente, cobre todo agente, até os que vierem depois.

**Trade-off.**
- Com um provedor instável, a empresa clica "Tentar de novo" mais vezes. Antes, recebia a simulação sem saber.
- A comparação de modelos congelada (`eval/comparacao_de_modelos.py`) conta a falha do provedor pela resposta
  simulada. Ela roda com `MOCK_DE_RESERVA=sim`; sem a chave, a primeira falha para a medição inteira, sem número errado.
- O Conferidor que falha derruba a leitura inteira, e não só a conferência. É a saída mais segura: nada segue pela
  metade.
- O servidor medido do `qa-jornada` (`tests/jornadas/ambiente_da_jornada.py`), ao chegar ao teto da rodada, passa a
  pausar os envios em vez de responder com o MOCK.

**Como comprovar.**
- `tests/test_falha_da_ia_pausa.py` (8 testes), que prova:
  - a etapa pausa sem contar como falha e grava o ERRO;
  - o envio fica guardado, sem mapeamento simulado, e volta quando o provedor volta;
  - a conversa e o Endomarketing gravam o ERRO e deixam o aviso subir;
  - a leitura para quando o Conferidor não responde;
  - o guardrail sem a segunda opinião pausa;
  - a API avisa com 503 e o recado certo, sem o detalhe técnico;
  - a chave nunca chega ao servidor.
- `tests/test_llm_client.py`: os três casos pausam; com a reserva, caem para o MOCK como antes.
- Os testes que esperavam a resposta simulada passaram a esperar a pausa: `tests/test_adversarial.py` (ataque 9),
  `tests/test_seguranca.py`, `tests/test_provedores_de_ia.py` e, em `tests/seguranca/test_seg_entradas.py`, o C-25 e o
  C-26.

**Altera** o ADR-36: a queda para o MOCK vira a reserva da máquina local. **Amplia** o ADR-131 e o ADR-139: a mesma
pausa, agora também pela falha da IA.
**Origem.** Pedido da usuária pelo orquestrador (plano de fechamento), 2026-09-29.

### ADR-146 · O acesso da empresa expira sozinho: 90 dias sem uso ou 12 meses de validade ✅

**Contexto (2026-09-30, conversa sobre a gestão de acesso).** Quem sai de uma empresa cliente continua com o login do
Integra Folha, e o RH nem sempre avisa o banco. O especialista do banco já podia desativar uma pessoa, mas só se alguém
lembrasse. A usuária pediu uma solução "super simples de implementar" para a empresa, que já desse uma gestão melhor.
O login da empresa já é um e-mail do domínio dela (`services/portal_do_banco.py`), e o botão "Ativar/Desativar" já
existe na gestão de usuários do Portal Interno.

**Opções.**
- (a) um provedor de identidade de mercado (Cognito, Auth0) com administração delegada por empresa;
- (b) um código no e-mail corporativo a cada login (o acesso morre quando a empresa apaga o e-mail);
- (c) o acesso esquecido expira sozinho, conferido no próprio login, sem nenhum serviço novo.

**Decisão.** (c), com o que já existe:
- **Duas colunas** na tabela `usuarios`: `ultimo_acesso` e `acesso_valido_ate` (AAAA-MM-DD). Vazias em quem já existia:
  a contagem começa no próximo login, e ninguém é bloqueado no dia da mudança.
- **No login** (`api/principal.py`, `conferir_usuario_e_senha`), **depois da senha certa**: a pessoa de empresa que não
  entra há mais de 90 dias, ou com a validade vencida, recebe 403 com o motivo e o caminho ("Peça ao especialista do
  banco para reativar"). A tela de login já mostra o `detail` do servidor e não mudou. O login certo grava o dia do
  acesso, e quem ainda não tinha validade ganha 12 meses.
- **A senha errada** continua com a mensagem de sempre: quem não sabe a senha não descobre que o acesso está suspenso.
- **O perfil BANCO** não entra nessas regras (o caminho dele é o SSO do banco, na produção).
- **A tela do banco mostra a suspensão e reativa** (corrigido na revisão do `revisor-codigo`, 30/09: a pessoa suspensa
  continua com a marca "ativo", e a tela só mostrava "Desativar"). A lista de usuários (`GET /api/banco/empresas`) traz
  `suspensao` ("sem_uso", "vencido" ou vazio, `auth.suspensao_do_acesso`); a tela mostra o selo "Suspenso (sem uso)" ou
  "Acesso vencido" e o botão **"Reativar"**, que usa a rota de ativar que já existia. Reativar
  (`auth.definir_ativo`) renova o acesso: a contagem recomeça hoje, e a validade passa a ser de mais 12 meses.
- Os prazos ficam em `services/auth.py` (`DIAS_SEM_USO_PARA_SUSPENDER = 90`, `DIAS_DE_VALIDADE_DO_ACESSO = 365`).

**Porquê.** Cobre o caso mais comum, o acesso que ninguém lembrou de tirar, com cerca de 100 linhas e sem depender de
um serviço de fora. Obriga uma revisão anual, e o especialista reativa com o gesto que já conhece.

**Trade-off.**
- Quem usa pouco (menos de uma vez a cada 90 dias) precisa pedir a reativação ao banco.
- Não resolve o desligamento na hora: a pessoa que saiu ontem ainda entra até completar 90 dias sem uso. Esse caso fica
  com a evolução (código no e-mail corporativo, administrador da empresa, e o SSO do banco para os especialistas).
- A suspensão é conferida no login: uma sessão já aberta vale até vencer (8 horas).

**Teste que comprova.** `tests/test_validade_do_acesso.py`, 5 casos:
- 91 dias sem entrar → 403 com a mensagem da falta de uso;
- validade vencida → 403 com a mensagem do acesso vencido;
- senha errada de quem está suspenso → 401 com a mensagem de sempre;
- o especialista do banco parado e vencido entra;
- o banco vê a suspensão na lista, o "Reativar" (a rota da tela) renova, e a pessoa volta a entrar com a validade de
  mais 12 meses.

**Origem.** Pedido da usuária, 2026-09-30 (a mesma conversa dos achados de segurança, na cópia
`dev/achados-seguranca`). Entra no desenho `Entregaveis_Case/Integra_Folha_Arquitetura_Seguranca_AWS.html`.

---

<a id="adr-147"></a>
### ADR-147 · O detector de ataques do Bedrock Guardrails vira a segunda opinião do guardrail de injeção, e a KB salva sem IA ✅

**Contexto (2026-09-30).** A usuária pediu para avaliar "ligar o Amazon Bedrock Guardrails e a complexidade". O
guardrail de injeção (ADR-38) tem duas camadas na entrada: a lista de 12 frases e, com a IA real, a segunda opinião de
um modelo pequeno (hoje o Nova 2 Lite, com o prompt `guardrail_v1`, que responde SUSPEITO ou NORMAL). Essa segunda
opinião tem três problemas:
- nunca foi medida com a IA real (ADR-62);
- depende de interpretar o texto do modelo (o negrito do Nova obrigou a limpeza em `veredito_e_suspeito`);
- deixa lento o salvar da KB do Endomarketing, porque lê a KB inteira.

A avaliação completa, com as fontes, está em `.claude/agent-memory/arquiteto/pedidos/avaliacao_bedrock_guardrails.md`.

**Opções.**

| Opção | A favor | Contra |
|---|---|---|
| (a) Manter o modelo pequeno | Nada muda | Não medido; depende de interpretar texto; lento na KB |
| **(b) A API `InvokeGuardrailChecks` do Bedrock Guardrails** (lançada em 16/06/2026) | Só detecta: devolve uma nota de 0 a 1 por categoria (JAILBREAK, PROMPT_INJECTION e PROMPT_LEAKAGE), e o nosso código decide pelo limiar. Não cria recurso na conta. Custa US$ 0,08 por 1.000 unidades de texto | A documentação não diz o nível (Standard ou Classic) nem se o pedido roda em outra região dos EUA |
| (c) A API `ApplyGuardrail`, com um guardrail criado na conta | O português do nível Standard está documentado | O recurso no CloudFormation, o perfil `us.guardrail.v1:0` (obrigatório no Standard) e mais permissões; US$ 0,15 por 1.000 unidades |
| (d) O `guardrailConfig` em cada chamada do modelo | Confere a entrada e a saída | Cobra e confere a planilha e o documento inteiros (falso alarme nos dados); prende a segurança à chamada; só no Converse |

**Decisão: a opção (b),** escolhida pela usuária em 30/09, **sem experimento antes.** A regra dela, de 30/09: "Para os
próximos ajustes não precisamos fazer as medições".
- **As mensagens de fora passam pela lista e, com a IA real, pelo detector de ataques do Bedrock Guardrails,** no lugar
  do modelo pequeno. São cinco: o chat do Assistente de Correção, o comentário "Refazer", a dica sobre a coluna, o
  destaque do Endomarketing e o documento do catálogo (`guardrail_injecao.verificar_mensagem`).
  - A mensagem é suspeita quando alguma das 3 categorias tem nota igual ou maior que o limiar: 0,6 para começar, numa
    constante.
- **O tempo máximo por checagem** (pedido da usuária; 3 s para começar, numa constante): se estourar, a mensagem segue
  com o resultado da lista, e a Telemetria registra "estourou".
  - É uma exceção consciente ao ADR-145, só nesta checagem: a lista já rodou, e as camadas seguintes seguram o dano.
  - **Os outros erros** (403 sem permissão, 429, 5xx, a resposta sem notas, a rede fora) seguem o mesmo caminho, sem
    nova tentativa, com o tipo do erro na Telemetria (ex.: "HTTP403"). **Confirmado pela usuária em 30/09** ("falha do
    Guardrails = segue com a lista"). Assim, uma permissão que falta aparece na Telemetria e no registro do servidor
    ("falta a permissão bedrock:InvokeGuardrailChecks"), em vez de travar todas as conversas.
  - **O teto do dia ou do mês atingido** continua pausando, como qualquer chamada à IA (ADR-131).
- **Em paralelo, quando der** (pedido da usuária): quando a mensagem vai depois para a IA (o chat do Assistente e o
  destaque do Endomarketing), a checagem roda junto com a preparação da resposta.
  - Se der suspeito, a resposta é descartada e a mensagem é recusada.
  - O texto já foi à IA, mas no mesmo destino aprovado, e a IA não tem ferramenta para agir.
  - Onde complicar, fica em sequência, com o tempo máximo segurando a espera.
  - **Como ficou:** em paralelo nos dois lugares. A preparação só lê e pergunta à IA; o que muda o cadastro (a decisão
    do Assistente) e o que grava o rascunho do Endomarketing vêm só depois do resultado da checagem. A checagem tem um
    cliente e uma medição só dela e não toca no banco de quem chamou: a Telemetria é gravada depois de juntar as duas.
- **A Telemetria de cada checagem:** o tempo, o resultado (normal, suspeito, estourou ou erro) e o custo, **sem o
  texto**. O custo entra também no teto do dia e do mês (ADR-131), pela porta única de saída
  (`services/llm_client.py`).
  - **Como ficou:** cada checagem é uma execução do agente "Bedrock Guardrails" (cartão próprio no Acompanhamento dos
    agentes, sem mudar a tela), com a etapa `checar_mensagem:<resultado>` e o status OK, BLOQUEADO ou ERRO. O custo
    soma uma vez só: na execução da checagem, e não na de quem chamou.
  - **As unidades de texto** ficam no registro do servidor, porque a tabela das execuções não tem coluna para elas (o
    custo as traduz: 1 unidade = US$ 0,00008).
  - **O envio e a empresa:** no chat e no destaque, a checagem leva os de quem chamou. No comentário "Refazer", na dica
    sobre a coluna e no documento do catálogo, que não mudaram, ela grava com "-".
- **Sem guardar o resultado de textos iguais,** que complica (a usuária: "se complicar").
- **No MOCK, nada chama a AWS:** vale só a lista, como hoje.
- **A KB do Endomarketing salva sem a IA** (escolha da usuária):
  - a trava fica com as conferências fixas: a ficha e as seções, os termos proibidos, os valores com "(simulação)", o
    CPF, a lista de frases e a vigência. A KB só vale depois que uma pessoa publica;
  - o parâmetro `usar_segunda_opiniao` sai de `services/kbs_endomarketing.py`, porque o kit de marca e a carga dos
    arquivos já não a usavam;
  - o motivo: a KB é escrita só pelo banco e é, por natureza, uma lista de regras para o agente, e qualquer detector de
    "ordem para a IA" tende a marcá-la.
- **Ficam de fora:**
  - o filtro de dados pessoais: contraria o ADR-101, e o Bedrock não tem CPF, CNPJ nem PIS;
  - o guardrail preso à chamada do modelo;
  - as células da planilha, que ficam só com a lista;
  - por enquanto, o documento do Leitor: a API dá uma nota para o pedido inteiro, sem dizer o parágrafo. É evolução.

**Porquê.**
- É um detector feito para isso, no mesmo destino já aprovado (Bedrock, EUA; ADR-96 e ADR-101).
- O português é "otimizado e suportado" nos ataques ao prompt no nível Standard. O PROMPT_LEAKAGE, que só existe no
  Standard, está na API nova.
- Troca uma peça não medida sem recurso novo na conta: só a permissão `bedrock:InvokeGuardrailChecks`, que a política
  padrão das chaves (`AmazonBedrockLimitedAccess`, v9) não traz.

**Trade-off.**
- **Um ataque que a lista e o detector não pegam continua possível.** As camadas seguintes limitam o dano: o texto de fora
  vai como dado, o contrato e o guardrail de saída conferem a resposta, e uma pessoa aprova.
- **O falso alarme em mensagem legítima de RH** ("desconsidere a linha 3"): o limiar é uma constante, e a recusa já
  explica e pede para reescrever.
- **O tempo estourado deixa a mensagem passar só com a lista:** é disponibilidade no lugar de uma camada, com o registro
  na Telemetria.
- **A API nova não documenta o nível nem a região de processamento.** Se o português decepcionar, o caminho é a opção
  (c).
- **A LGPD:** o texto vai a mais um serviço do Bedrock, no mesmo destino.
  - Pela ficha de serviço da AWS (15/09/2026), o conteúdo não treina modelos e só apareceria nos registros de invocação,
    que estão desligados.
  - A página da retenção zero (ADR-135) fala da inferência dos modelos e não cita o Guardrails. O ponto fica com o
    jurídico (`seguranca.md`, seção 8, item 10).

**O custo** (preços públicos de 30/09/2026): US$ 0,08 por 1.000 unidades de texto. Uma unidade tem até 1.000
caracteres, e cada texto arredonda para cima.
- Na demo e no QA: menos de US$ 0,10.
- No business case (~1,04 milhão de funcionários, 12 meses): cerca de US$ 17 por ano nas mensagens.

**Como comprovar** ✅ (em MOCK, com o "detector de mentira" de `tests/test_provedores_de_ia.py`; nada sai da máquina):
- **o pedido e a resposta** (`tests/test_provedores_de_ia.py`, os `test_detector_*`): o endereço da região, a chave,
  as 3 categorias; a maior nota, as unidades arredondadas para cima e o custo; os erros sobem só com o código;
- **o guardrail** (`tests/test_bedrock_guardrails.py`):
  - o limiar (0,6 já é suspeito, em qualquer categoria);
  - a lista vem antes, e o texto vazio não chama;
  - o tempo estourado e os erros (403, 429, 500, 503, a resposta sem notas, a rede fora, a rota sem o Bedrock) seguem
    com a lista, sem nova tentativa, e ficam na Telemetria;
  - o teto atingido pausa sem chamar; o custo entra no teto do dia e na execução da checagem, uma vez só;
  - o MOCK faz zero chamadas, também nos dois agentes;
  - o texto nunca vai para a Telemetria nem para o registro do servidor;
- **o paralelo:** a resposta do chat e o rascunho do destaque são preparados enquanto o detector checa (o detector de
  mentira espera o sinal da preparação) e descartados no "suspeito", sem mudar nada e sem guardar o rascunho;
- **a KB:** salvar, conferir e publicar não chamam o detector, e a lista continua barrando a ordem clara;
- **o cartão** "Bedrock Guardrails" conta as checagens, os bloqueios, os erros e o custo;
- **as quebras de propósito** (o limiar, o paralelo, o descarte, o tempo máximo, a medição própria e o erro que
  pausaria) foram todas pegas pelos testes;
- **o `seguranca`:** os ataques D-36 em diante, em `tests/seguranca/test_seg_ia.py` (a fazer, ⏳);
- **uma chamada real de prova** (menos de US$ 0,001), depois que a permissão for dada, com o ok dela (a fazer, ⏳).

**As fontes (consultadas em 30/09/2026):**
- **A API:** https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeGuardrailChecks.html
  (`POST /guardrail-checks/invoke`, no endereço `bedrock-runtime`) e
  https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-invoke-guardrail-checks.html ("without creating
  individual guardrail resources"; US East (N. Virginia) está entre as regiões).
- **O anúncio:** https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-guardrails-api-ai/ (16/06/2026).
- **A permissão:** https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-invoke-guardrail-checks-permissions.html
  (`bedrock:InvokeGuardrailChecks`, com `Resource: "*"`).
- **O preço:** https://aws.amazon.com/bedrock/pricing/.
- **Os idiomas e os níveis:** https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html
  e https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-tiers.html.
- **O perfil `us.`:** a API não chama modelo, então não usa perfil de inferência. A chamada vai ao endereço da Virgínia
  (`bedrock-runtime.us-east-1`), o mesmo da IA (ADR-135).

**Altera:**
- o ADR-38: o detector da segunda opinião;
- o ADR-62: a medição por camadas deixa de ser portão;
- o ADR-125: a KB salva sem a IA;
- o ADR-145: o tempo estourado da checagem segue com a lista.

**Origem.** Pedido da usuária pelo orquestrador, 2026-09-30. Na mesma data, ela aprovou "Sim, liga hoje" e "Sim, igual
ao kit", e mandou pelo orquestrador o tempo máximo, o paralelo e o tempo na Telemetria. O Bedrock Guardrails entra no
desenho `Entregaveis_Case/Integra_Folha_Arquitetura_Seguranca_AWS.html` e no `arquitetura.md`.

---

<a id="adr-148"></a>
### ADR-148 · O Simulador de Rentabilidade, as Premissas financeiras e o big number do falso não folha ficam ocultos nesta versão ✅

**Contexto (2026-09-30, a lista de últimos ajustes da usuária).** Para a versão final, a usuária decidiu tirar da vista
do Portal Interno três peças: a guia "Simulador de Rentabilidade" dos Indicadores (ADR-123), a tela "Premissas
financeiras" do menu da engrenagem (ADR-122) e o cartão "falso não folha recuperados" do Painel de acompanhamento. Na
mesma lista, o menu "Configuração" virou "Sistema", com a engrenagem.

**Opções.**
- (a) apagar o código das três peças: a tela, os scripts, as rotas e os testes;
- (b) ocultar: o código fica no projeto, mas nada aparece (nem no menu, nem nas guias, nem nos links), e o endereço
  guardado leva a uma tela que existe.

**Decisão: (b), a escolha da usuária** ("ocultar, e não apagar"):
- **o que não pode rodar fica numa caixa `<template>`** (o navegador guarda o que está dentro sem desenhar nem rodar):
  as guias, o Simulador inteiro, o script dele e o link do painel, em `banco_indicadores.html`, e o item "Premissas
  financeiras" do menu, em cada tela do banco;
- **o cartão do falso não folha fica com `hidden`**, porque o `js/banco_planejamento.js` continua escrevendo nele;
- **tudo leva a marca `data-oculto-nesta-versao`** ("simulador", "premissas" ou "falso-nao-folha"): uma busca acha o
  que religar ou apagar;
- **o endereço das Premissas leva aos Indicadores:** o porteiro (`api/principal.py`, `PAGINAS_OCULTAS_NESTA_VERSAO`)
  desvia o dono da tela (o perfil BANCO), também nas variações que o Windows abre como o mesmo arquivo (maiúsculas e
  barra, ponto ou espaço no fim). O `?aba=simulador` cai no painel (`js/banco_indicadores.js`);
- **nada muda por trás:** as rotas `/api/banco/premissas` e `/api/banco/planejamento/*`, os serviços e as tabelas
  continuam, e o painel e a projeção seguem lendo as premissas oficiais.

**Porquê.** É a decisão dela para a versão final. Ocultar leva poucas linhas, não mexe em serviço, rota nem tabela, e
volta rápido: basta tirar as caixas e o `hidden`, devolver o "simulador" à lista de guias e tirar a página da lista das
ocultas. A retirada de vez fica para uma evolução.

**Trade-off.** O projeto carrega código oculto (o HTML e o script do Simulador, a tela e o script das Premissas, as
rotas e os testes delas), em troca de uma retirada rápida e reversível. Os roteiros de clique do Simulador e da
gravação das Premissas saíram (estão no Git, na tag `antes-do-menu-e-indicadores`); a gravação das premissas continua
provada pela API (`tests/test_premissas_oficiais.py`).

**Teste que comprova.**
- `tests/test_api_front.py`: o banco vai de `banco_premissas.html` para os Indicadores, também nas 6 variações do
  endereço; a empresa continua indo para a home dela, e quem não entrou, para o login;
- `tests/test_telas_ocultas.py`: no HTML à vista, nenhum link para as telas ocultas, nem guias, nem o Simulador, nem o
  script dele; o cartão com `hidden`; o botão "Sistema" nas 9 telas do banco; e o código dentro das caixas;
- os roteiros `menu_do_portal_interno`, `painel_de_indicadores` e `premissas_financeiras`, no Chrome.

**Altera** o ADR-122 (o menu da engrenagem vira "Sistema", sem as Premissas, e os Indicadores ficam sem guias) e o
ADR-123 (o Simulador fica oculto).
**Origem.** Pedido da usuária pelo orquestrador (a frente A dos últimos ajustes), 2026-09-30.

---

<a id="adr-149"></a>
### ADR-149 · O arquivo de contas abertas vira "cpf;status;agencia;conta;data_abertura", e o correntista é um grupo só ✅

**Contexto (2026-09-30, a lista de últimos ajustes da usuária).** O arquivo que o banco devolve tinha 9 colunas
(ADR-119, ADR-122 e a 3ª rodada do pedido menu-do-banco): o CNPJ da empresa, o código do banco, a agência, a conta, a
data, o tipo e, no correntista, a situação (ATIVO ou INATIVO) e a folha já identificada (S ou N). A usuária simplificou:
o arquivo é "exatamente `cpf;status;agencia;conta;data_abertura`", com o status 1 = conta nova e 2 = já era
correntista, e a data como `2026-09-29`. Saem o CNPJ (a empresa é a da ficha aberta na tela), o código do banco, a
situação e a folha.

**Opções.**
- (a) aceitar os dois formatos, o antigo e o novo;
- (b) só o formato novo.

**Decisão: (b), a escolha da usuária.**
- **o layout** (`services/contas_abertas.py`, a fonte única que a tela mostra) passa a ter 5 colunas; o arquivo antigo
  é recusado pelo cabeçalho, e o motivo diz as colunas que faltam e as que sobram. A data vem como AAAA-MM-DD e fica
  gravada como DD/MM/AAAA, igual às contas antigas;
- **a empresa do arquivo é a da tela:** sem o CNPJ, o que prova a empresa são os CPFs, que precisam estar Cadastrados
  nela (um CPF de outra empresa recusa o arquivo inteiro, e o motivo diz qual);
- **a conta é comparada pela agência e pelo número** (o código do banco saiu); as contas antigas, com o código do
  banco, continuam as mesmas contas;
- **o esquema do banco de dados não muda:** o código do banco fica vazio nas baixas novas, e as colunas da situação e
  da folha ficam na tabela, sem uso;
- **o planejamento conta o correntista num grupo só** (`services/planejamento.py`): sem a situação e a folha, saem as
  contagens de ativos, inativos, falso não folha e de quem já era folha. O ganho realizado passa a ser correntistas ×
  (MOB folha − MOB não folha) + contas novas × MOB cliente novo: o correntista que chega pelo projeto é o cliente que já
  estava no banco e passa a ter a folha reconhecida (a premissa do business case). O Painel mostra o cartão e a coluna
  "Correntistas" (o cartão do falso não folha já estava oculto, ADR-148).

**Porquê.** É o arquivo que ela quer que os sistemas do banco gerem: menos colunas, e nenhuma que dependa de outra (a
situação e a folha só valiam no correntista). A baixa e o que a empresa vê continuam: a situação da pessoa vira "Conta
aberta" ou "Já é correntista", com a agência, o número e a data para pagar o salário (ADR-102).

**Trade-off.** O banco perde a divisão dos correntistas (ativos × inativos, falso não folha × já era folha): o ganho
realizado conta todo correntista como folha recuperada, e pode ficar maior que o de antes (o inativo e quem já era
folha não somavam). O código do banco some das contas novas (a grade mostra um traço nessa coluna). Um arquivo gerado
no formato antigo precisa ser refeito.

**Teste que comprova.**
- `tests/test_contas_abertas.py`: o layout novo, cada conferência que trava, o formato antigo recusado com o motivo, a
  data AAAA-MM-DD, o arquivo de outra empresa recusado pelos CPFs, a conta antiga com o código do banco, a baixa com a
  data gravada como DD/MM/AAAA, a visão da empresa e as rotas (401 e 403);
- `tests/test_planejamento.py`: o resumo com o correntista num grupo só, a situação e a folha antigas ignoradas e o
  ganho realizado conferido à mão;
- os roteiros `carregar_contas_abertas` e `painel_de_indicadores`, no Chrome.

**Altera** o ADR-119 e o ADR-122 (o layout e a prova da empresa) e o ADR-123 (a divisão dos correntistas e o ganho
realizado).
**Origem.** Pedido da usuária pelo orquestrador (a frente B dos últimos ajustes), 2026-09-30.

---

<a id="adr-150"></a>
### ADR-150 · O Endomarketing no formato garantido e as 4 correções do EXP-019 (prompt v5) ✅

**Contexto (2026-09-30).** O EXP-019 passou o Agente de Endomarketing por todas as combinações da tela, em MOCK e, numa
amostra, com a IA real (o Sonnet 4.6 pelo Bedrock). Achou quatro defeitos, três deles no nosso código:
1. **O JSON quebrado:** 34 de 120 chamadas reais deram FALHA (28%; 49% no mural). A IA copiava do catálogo nomes de
   menu entre aspas retas sem o escape, o texto do JSON fechava no meio, e o material inteiro se perdia.
2. **O link com a pontuação colada:** 44 dos 86 materiais gerados perderam um bloco legítimo. A conferência dos links
   de saída lia o link com a vírgula ou o ponto da frase ("…/pagina,") e não o achava no catálogo.
3. **O aviso do destaque fora do catálogo acertava 29% em MOCK.** O código comparava as duas seções mais parecidas com
   o destaque, e a segunda quase sempre era o atendimento (que entra em todo material) ou um benefício escolhido
   parecido. Com a IA real, a própria IA avisava (26 de 26).
4. **O WhatsApp deixava benefícios escolhidos de fora:** 16 de 20, sem aviso. O prompt pedia "no máximo 3 blocos", e o
   código cortava os blocos do fim.

**Opções.**

| Defeito | Opções | Escolhida |
|---|---|---|
| JSON quebrado | (a) pedir no prompt o escape das aspas; (b) consertar o JSON no código; (c) o **formato garantido** (o esquema vai com o pedido, como no Interpretador, ADR-107), com uma segunda tentativa para o provedor sem esquema | (c) |
| Link com pontuação | (a) mudar a expressão dos links (mexeria também na troca por "[link removido]" das outras telas); (b) tirar a pontuação do fim só na comparação dos links de saída | (b) |
| Aviso do destaque | (a) tirar o atendimento da comparação (o destaque sobre o atendimento daria alarme falso em 32 de 39 casos da grade de teste); (b) apertar o corte da distância (depende de uma medição); (c) o nome citado primeiro e, senão, só a seção mais parecida, com o corte num parâmetro que começa no valor de hoje | (c) |
| WhatsApp | (a) tirar o limite do canal (a tela diz "até 3 trechos"); (b) só avisar o que ficou de fora; (c) todo benefício escolhido aparece: o prompt manda juntar os benefícios nos blocos, o código completa o que ficou sem bloco e junta os blocos a mais no último, em vez de cortar | (c) |

**Decisão: as quatro opções (c) e (b) da tabela, no prompt v5, que vira o padrão sem medir antes** (a regra da
usuária de 30/09). A remedição com a IA real vem depois da junção (o `cientista-dados`, até US$ 2).
- **O formato garantido** (`agents/endomarketing.py`, `esquema_da_resposta`): todo pedido leva o esquema do material.
  Pelo Bedrock, o Sonnet 4.6 vai pela API Converse, que obriga o modelo a seguir o esquema. Vale nas duas versões do
  prompt (a v5 e a v3 da chave desligada), porque é o contrato da resposta, o mesmo desde a v1.
  - **A resposta fora do formato ganha uma segunda tentativa, com o motivo** (como no Interpretador). É a rede de
    proteção para o provedor que não aceita o esquema: no endereço da Anthropic no Bedrock, ele não vai. Duas
    respostas fora do formato continuam FALHA.
  - **"Pelo menos uma fonte por bloco" sai do contrato e fica na conferência,** porque o formato garantido não aceita
    limite no tamanho de uma lista. O bloco sem fonte sai com a observação, e o resto do material continua.
  - Regra 11 do prompt: para destacar um nome dentro do texto, aspas curvas ou simples.
- **Os links de saída sem a pontuação** (`services/guardrail_injecao.py`, `links_no_texto`): a comparação usa o
  endereço sem `.,;:!?)]>"'”’»` no fim, nos dois lados. Não abre brecha, porque só sai pontuação do fim, e o endereço que
  sobra precisa ser idêntico ao do trecho citado. A troca por "[link removido]" (`tirar_links`) não mudou.
- **O aviso do destaque** (`_destaques_fora_da_escolha`):
  1. o nome de uma seção que entrou, escrito no destaque, cobre (a busca confunde nomes parecidos, como "conta salário"
     e "salário antecipado");
  2. senão, decide só a seção mais parecida (`SECOES_COMPARADAS_COM_O_DESTAQUE = 1`), dentro de um corte próprio,
     `DISTANCIA_MAXIMA_DO_DESTAQUE`, hoje igual ao geral do catálogo (0,80).
- **Todo benefício escolhido aparece, em qualquer canal:**
  - o pedido leva `<beneficios_escolhidos>`, e a regra 10 do prompt pede todos (no WhatsApp, vários num bloco, com a
    fonte de cada um);
  - o código completa o benefício que ficou sem bloco (a IA deixou de fora, ou a conferência tirou o bloco dele) com a
    primeira frase do próprio catálogo, com a fonte, antes do atendimento, e a observação avisa
    (`completar_os_beneficios`). A frase também passa pelos termos proibidos;
  - no WhatsApp, os blocos a mais se juntam no último que cabe (`ajustar_ao_canal`), em vez de sair. O simulador do
    MOCK segue a mesma regra do prompt: no WhatsApp, a primeira frase de cada trecho, em até 3 blocos.

**Porquê.** O formato garantido tira a FALHA pela raiz, e já foi provado com o mesmo modelo no Interpretador
(ADR-107). As outras três correções são regras gerais do código, e não um remendo para as empresas do EXP-019: valem
para qualquer catálogo, qualquer link e qualquer destaque. Medido em MOCK, sem IA, na grade do EXP-019 (a função nova
contra a regra de antes, no índice copiado): o aviso do destaque fora do catálogo foi de 13 de 45 (29%, o número do
EXP) para 26 de 45 (58%); o pedido normal, de 26 para 32 de 32; e nenhum alarme falso novo (45 de 45 no destaque sobre o
atendimento, 12 de 12 quando o benefício foi escolhido).

**Trade-off.**
- A frase que completa um benefício é a do catálogo, fora do tom de voz; a observação avisa, e o especialista confere
  antes de publicar.
- No WhatsApp, o último bloco fica maior quando a IA escreve blocos demais.
- A seção mais parecida pode ser outra parecida (o alarme falso da busca); o nome escrito cobre esse caso. Com todos os
  benefícios marcados, o aviso ainda depende do corte (0 de 6 na grade): só a medição da separação "o catálogo tem" ×
  "não tem" pela distância diz o valor certo (a F3 do `cientista-dados`).
- A segunda tentativa dobra o tempo e o custo na resposta fora do formato, que deve ficar rara.

**Teste que comprova.** `tests/test_endomarketing_v5.py` (70 casos; 44 falham no código de antes, e os outros 26 são
as guardas que valem nos dois): o esquema em todo pedido e no corpo que chega ao Bedrock, as regras do esquema, o
catálogo com aspas, a segunda tentativa, a FALHA, o bloco sem fonte, os links com cada pontuação e os inventados, o
aviso do destaque (o nome, a mais parecida, o atendimento, o corte) e o WhatsApp com todos os benefícios nas 6 empresas
da semente e nos 4 tipos. Também `tests/test_endomarketing.py` e `tests/test_endomarketing_com_as_kbs.py`.

**Falta medir.** Com a IA real, nas mesmas combinações do EXP-019 (a semente 20260930), antes × depois, pareado: a
FALHA, os blocos removidos, os benefícios escolhidos sem bloco e o aviso do destaque. E o corte do destaque (F3).

**Altera** o ADR-93 (o limite do WhatsApp junta, não corta) e **estende** o ADR-107 (o formato garantido) ao
Endomarketing.
**Origem.** O EXP-019 e a F5 do plano "fechar as avaliações", aprovados pela usuária em 30/09, pelo orquestrador.

---

<a id="adr-151"></a>
### ADR-151 · O joinha nas respostas dos agentes, com a satisfação de cada agente no Acompanhamento dos agentes ✅

**Contexto (2026-09-30, a lista final da usuária, item 10).** Faltava a visão da opinião de quem usa o sistema. A
usuária pediu o joinha para cima e para baixo nas interações com os agentes, os dados sintéticos disso e uma seção para o
especialista ver a satisfação (primeiro nos Indicadores; no teste, ela pediu a seção no Acompanhamento dos agentes). Os
lugares do joinha, na escolha dela: a conversa da pendência (o Agente de validação), o material do Endomarketing (o
especialista avalia o texto que o agente escreveu) e as perguntas do Leitor e do Conferidor ao ler o documento.

**Opções.**
- onde fica o voto: (a) em cada resposta de um agente, uma linha por pessoa e por resposta; (b) uma nota só, no fim da
  conversa;
- o comentário: (a) só no joinha para baixo, visto só por quem votou, com só a contagem para o banco; (b) nos dois
  joinhas; (c) o banco lê os textos;
- os números: (a) contados a cada abertura da tela, só agregados; (b) uma tabela de resumo por dia.

**Decisão.**
- **O voto é por resposta, a opção (a).** A tabela nova `opinioes_dos_agentes` guarda o tipo e a referência da
  interação, o agente, quem votou e o perfil, a empresa, o envio, o voto, o comentário, a origem e as datas. A chave é
  (tipo, referência, login): mudar de ideia troca o voto, sem somar dois, e clicar de novo no joinha marcado retira o
  voto.
- **As três interações:**
  - a resposta do Agente de validação: a conversa guardada (ADR-120) passa a mandar à tela a posição de cada balão
    ("ordem"), e o voto aponta "<chave da conversa>|<ordem>". Só o balão do agente aceita o voto (nem a fala da pessoa,
    nem a pergunta que abre o cartão). O joinha fica dentro do balão e vai junto para a janela da conversa do
    Acompanhar;
  - a pergunta da leitura: a pendência "PERGUNTA_DA_IA:<campo>" (ADR-73) ganha o joinha no balão da pergunta. Quem
    perguntou é o Conferidor quando o texto começa com a frase fixa dele (ADR-131); senão, é o Leitor;
  - o material do Endomarketing: o especialista vota no rascunho e na janela "Ver".
- **No Portal Interno, não há conversa com o Assistente de Correção.** Ele é o mesmo Agente de validação da empresa, e a
  aba Conversa do banco é entre pessoas. Por isso, o joinha dele fica só na empresa, e o banco vê o resultado no
  Acompanhamento dos agentes (decisão da usuária).
- **O isolamento:** a empresa vota e lê os votos só nos envios dela (o de outra empresa é "não encontrado", 404); o
  banco vota só no material da empresa aberta.
- **O comentário, a opção (a):** opcional, só no joinha para baixo ("O que faltou?"), com até 200 letras. Enviado, ele
  fica à vista embaixo do joinha de quem votou ("Seu comentário: …", com o "Editar"). Isso vale também depois do F5,
  onde o joinha volta: na pergunta da leitura, no material e na conversa das Resolvidas (pedido da usuária no teste). O
  servidor devolve o comentário só a quem votou. Ele não vai para nenhuma IA e não aparece para o banco, que vê só
  quantos há, porque o texto pode trazer dado pessoal.
- **A seção do banco, a opção (a):** "O que as pessoas acham das respostas dos agentes", na tela Acompanhamento dos
  agentes (menu Sistema), logo depois dos cartões do trabalho de cada agente. Ela segue o período do alto da tela (7, 30
  ou 90 dias, Tudo ou De/até; as datas são as de Brasília, com as duas pontas dentro) e se atualiza como o resto da tela
  (ao voltar para a aba e de minuto em minuto). Cada agente tem um cartão com:
  - a satisfação (a parte dos votos com o joinha para cima) e a barra dela;
  - os votos e a contagem dos comentários;
  - a linha das 12 semanas que terminam no fim do período (a semana vira à meia-noite de Brasília), com a comparação
    das 4 primeiras semanas com as 4 últimas. A comparação só aparece com pelo menos 5 votos em cada ponta; com menos,
    a tela diz que são poucos votos para comparar.

  A mesma tendência também aparece numa tabela. Só números agregados, como no resto do banco (ADR-117 e ADR-144). A
  primeira versão ficou na parte 5 dos Indicadores, com o filtro de empresa e estado; saiu de lá com a mudança.
- **As rotas** (`api/rotas_opiniao_dos_agentes.py`): `POST` e `GET /api/empresa/opinioes` (a empresa),
  `POST` e `GET /api/banco/empresas/{empresa_id}/opinioes` (o material) e `GET /api/banco/telemetria/opinioes?de=&ate=`
  (a seção, ao lado das outras consultas da tela).
- **Os dados de demonstração:** o `scripts/gerar_opinioes_dos_agentes.py`, sem IA e com a semente fixa, põe cerca de
  570 votos em 90 dias nas empresas da base viva, com as taxas diferentes por agente: o Agente de validação sobe de 70%
  para 88%, o Leitor fica em 72%, o Conferidor em 60% e o Endomarketing em 85%. Os votos levam a origem "carga
  sintética", e o `--remover` tira só eles. No PostgreSQL de todos, a carga só roda com `--confirmo-o-postgres`,
  depois da cópia de segurança.

**Porquê.** O voto por resposta diz qual agente falha e em qual tipo de resposta. É o sinal que as avaliações
automáticas não têm: as métricas medem a resposta contra o gabarito, e o joinha mede o que a pessoa achou. No
Acompanhamento dos agentes, a satisfação fica ao lado do que já se mede de cada agente (as execuções e a aceitação), sem
expor quem votou nem o texto do comentário.

**Trade-off.**
- A satisfação é uma opinião, e não uma medida de acerto. Uma semana com poucos votos oscila muito; por isso a
  comparação junta 4 semanas de cada ponta e pede pelo menos 5 votos em cada uma.
- A conversa em aberto não volta da memória depois do F5, e com ela somem os joinhas das respostas antigas. Nas
  Resolvidas, a conversa e os joinhas voltam.
- O banco não lê o texto dos comentários nesta versão. Fica como evolução uma leitura, com a máscara dos dados pessoais,
  para quem melhora os agentes.
- Os números da seção são contados a cada abertura: a tabela é pequena. Com milhões de votos, vira um resumo por dia.
- Os scripts do joinha dividem os nomes com os outros scripts da página (no navegador, uma função repetida substitui a
  outra): um teste confere que nenhum nome se repete nas páginas que os carregam.

**Teste que comprova.**
- `tests/test_opiniao_dos_agentes.py`:
  - a posição da resposta na conversa, na confirmação e nas Resolvidas;
  - trocar e retirar o voto, duas pessoas do mesmo RH e a conversa do grupo;
  - só a resposta do agente aceita o voto; o voto, o tipo e o comentário fora da regra são recusados;
  - a pergunta da leitura (do Leitor e do Conferidor) e o material do Endomarketing;
  - os números da seção: a satisfação, o período pelas datas de Brasília, a tendência de 12 semanas até o fim do
    período, a comparação das pontas, e nenhum login nem comentário na resposta;
  - as rotas: 401, 403, 404 e 400;
  - a tela usa os mesmos nomes e limites do servidor, a seção fica no Acompanhamento dos agentes (e não nos
    Indicadores), e nenhum nome dos scripts do joinha se repete nas páginas;
- `tests/test_gerar_opinioes_dos_agentes.py`:
  - as empresas do banco, quem vota, a origem e as datas;
  - a semente fixa e o `--remover`;
  - as taxas por agente e o volume da base viva;
  - a recusa do PostgreSQL sem a confirmação;
- o roteiro `opiniao_dos_agentes`, no Chrome.

**Altera** o ADR-120: a conversa guardada passa a mandar à tela a posição de cada balão.
**Origem.** Pedido da usuária pelo orquestrador (a lista final, item 10), 2026-09-30; o lugar da seção e o comentário à
vista, no teste dela, no mesmo dia.

---

<a id="adr-154"></a>
### ADR-152 · A fidelidade do Endomarketing pelo RAGAS num ambiente separado, com o juiz de outra família, como filtro e sem calibração humana ✅

**Contexto (2026-09-30).** O EXP-019 mostrou ONDE o Endomarketing gera um rascunho; faltava medir se o que ele escreve é
fiel ao catálogo, a métrica de geração do RAG prevista no plano de avaliação (a faithfulness e a answer relevancy do
RAGAS, com um LLM como juiz). Havia três obstáculos:
1. o RAGAS 0.4 traz um langchain que briga com o do `.venv` do projeto (o langchain-core e o LangGraph);
2. o juiz precisa rodar pelo Bedrock, com as regras de privacidade do ADR-101, e ser de outra família que o gerador (o
   Sonnet 4.6), para não "concordar consigo mesmo";
3. o RAGAS foi feito para perguntas e respostas em inglês, e o Endomarketing escreve material de marketing em
   português.

**Opções.**

| Ponto | Opções | Escolhida |
|---|---|---|
| Onde o RAGAS roda | (a) no `.venv` do projeto; (b) num ambiente separado (`.venv-avaliacao`, `requirements-avaliacao.txt`); (c) o mesmo algoritmo reescrito com o `llm_client`, sem o RAGAS | (b) |
| Como o juiz chega ao Bedrock | (a) o langchain-aws (boto3); (b) o nosso juiz, pela rota do projeto (`provedores_de_ia.chamar_pelo_converse`, com o formato garantido e o custo com os 10%), ligado às classes do RAGAS como "subclasse virtual" (`register`) | (b) |
| O juiz | (a) um Claude (mesma família do gerador); (b) o Mistral Large 3 (US$ 0,50 e 1,50 por milhão); (c) o Nova Pro | (b), com o (c) de reserva (não foi preciso: 0 erro de formato em 1.347 chamadas) |
| A pergunta da fidelidade | (a) o pedido do especialista; (b) uma pergunta neutra ("O que este trecho do material diz?") | (b) |
| O título | (a) um bloco como os outros; (b) à parte | (b) |
| Como ler o número do juiz | (a) como a régua; (b) como estimativa conservadora e filtro, conferida por outro juiz de IA e por uma conferência caso a caso; (c) calibrado por rótulos humanos | (b); o (c) não foi feito |

**Decisão.**
- **O RAGAS 0.4.3 mora no `.venv-avaliacao`,** com as versões fixas (o `langchain-community` 0.3.31, porque a 0.4
  tirou um módulo que o RAGAS importa). O código da medição (`eval/ragas_do_endomarketing.py`) só importa, no topo, o
  que vem com o Python, e roda nos dois ambientes: a preparação, que usa o banco e o agente, no `.venv` do projeto, e o
  juiz no separado.
- **O juiz é o Mistral Large 3, pela rota do projeto,** com o formato garantido (o esquema que o RAGAS pede vai com o
  pedido) e um teto em dólares que vale para as 4 medições que correm juntas (a reserva antes de cada chamada).
- **Os prompts do RAGAS são traduzidos pelo próprio RAGAS** (`BasePrompt.adapt`, com a instrução), conferidos à mão e
  gravados em `data/avaliacao/ragas_prompts_portugues.json`: toda medição usa a mesma tradução.
- **Três adaptações ao marketing em português, vistas nos ensaios:**
  1. a pergunta da fidelidade é neutra: com o pedido inteiro, o juiz tirava afirmações do PEDIDO ("a Brisa deve abrir
     uma conta no canal WhatsApp");
  2. o título conta à parte: numa frase de efeito, o RAGAS tira afirmações sobre o próprio texto ("o texto dá
     boas-vindas"), que não são fato do catálogo (70 das 117 "inventadas" dos títulos);
  3. a relevância usa a pergunta de cada tipo, tirada do prompt do agente (o canal fica de fora, porque ele muda o
     tamanho, e não o conteúdo).
- **O contexto de cada bloco é o que a IA recebeu:** os trechos que ele cita e a linha dos fatos do pedido (quem
  assina e que o banco é o parceiro da folha). A afirmação que a fonte citada não sustenta é conferida de novo contra
  todos os trechos (citada errado × inventada).
- **O número do juiz é lido como estimativa conservadora e filtro, sem calibração humana:** o que o juiz aprova tende
  a valer; o que ele aponta vai para revisão. Junto dele vão a concordância com outro juiz de IA (o GPT, nos 50 blocos
  da planilha) e a conferência de 10 casos pelo agente que mede (uma IA).

**Porquê.** O EXP-020 mostrou que o juiz, sozinho, não é régua: a concordância entre dois juízes de IA (GPT × Mistral,
n = 50) é de kappa 0,25 ("razoável"). Mas ele serve de filtro: quando o Mistral diz "fiel", o GPT concorda em 24 de 25;
quando ele aponta problema, o GPT concorda em só 8 de 25. A conferência do agente (uma IA, 10 casos) mostrou o motivo:
a 1ª conferência do RAGAS nega afirmações que estão no trecho citado. Então a fidelidade do RAGAS (0,87) subestima; o
GPT achou 41 de 50 blocos inteiros no trecho citado (82%). Rodar pela rota do projeto mantém a privacidade e o custo
iguais aos da aplicação.

**Trade-off.**
- Dois ambientes Python para manter, e o RAGAS preso numa versão.
- **Sem calibração humana:** todos os números comparam juízes de IA entre si; não se sabe o quanto eles erram juntos.
  Uma amostra rotulada por uma pessoa é a evolução, antes de usar o número como meta.
- As adaptações afastam a medição do RAGAS "de fábrica"; ficam anotadas no código e no EXP.
- A fidelidade não mede omissão: um bloco que deixa de fora uma condição que o trecho traz não perde ponto se o que ele
  afirma está no trecho.

**Teste que comprova.**
- `tests/test_ragas_do_endomarketing.py`, no `.venv` do projeto, com o juiz falso (22 casos): a separação dos blocos,
  a pergunta, os fatos do pedido, a conferência do catálogo, os sorteios, a planilha, o juiz (o formato, o custo e o
  teto), a contagem das afirmações, o título à parte, a pergunta neutra, os CSVs e o kappa com as contas feitas à mão.
- `tests/test_ragas_no_ambiente_separado.py`, no `.venv-avaliacao` (pulado na bateria), com 4 casos: o nosso juiz e os
  nossos embeddings dentro da Faithfulness e da AnswerRelevancy do RAGAS, e a tradução pelo `adapt`.

**Origem.** A F1 do plano "fechar as avaliações", pelo orquestrador; os 50 rótulos de comparação vieram de outro juiz
de IA (o GPT), fora da aplicação.

<a id="adr-153"></a>
### ADR-153 · A conversa da pendência confere o valor com todas as regras, mostra o dado e encerra depois de 3 respostas sem valor (prompt v4) ✅

**Contexto (2026-09-30).** No teste da usuária, o Agente de validação (a conversa de cada pendência) teve dois
defeitos:
1. **O valor errado aceito:** o cartão dizia que o código da profissão (CBO) estava vazio; ela escreveu um código que
   não existe ("C900"), o agente disse "Pronto", a pendência saiu da lista e nasceu OUTRO cartão ("são 6 dígitos, como
   4110-10"). Duas causas: a conferência antes do "Pronto" (ADR-127) roda a padronização e o dígito, mas não a regra da
   CBO oficial, que mora no Validador (o alerta CBO_DESCONHECIDO, ADR-129); e o "resolvida" olhava só a mesma regra
   (o obrigatório vazio saiu, e o alerta novo não contava).
2. **A pergunta repetida, sem o dado:** a cada "não sei", o agente respondia "diga o valor certo ou confirme que o dado
   está correto", sem dizer qual dado nem o que veio no arquivo. O modelo não vê a conversa inteira, e a IA simulada
   tinha uma fala de reserva fixa.

**Opções.**

| Defeito | Opções | Escolhida |
|---|---|---|
| Valor errado aceito | (a) copiar a regra da CBO (e as outras do Validador) na conferência de antes; (b) rodar o Validador numa cópia dos dados, sem gravar (exigiria separar o cálculo da gravação no `validador.executar`, fora deste pedido, e a regra da CBO grava a profissão do cargo); (c) **gravar a troca, comparar o relatório de antes com o de depois e, se nascer um achado de valor errado, voltar a troca na hora**, com o mesmo Desfazer da tela | (c) |
| O alerta que só pergunta (ex.: o salário fora da faixa da profissão nova) | (a) recusar o valor; (b) deixar a troca e avisar na mesma fala | (b) |
| Contar as respostas sem valor | (a) pelas palavras, no código; (b) pela ação do modelo; (c) **a ação nova do modelo ("sem_valor") com uma trava no código** (a frase clara de "não sei" que o modelo respondeu só com outra pergunta também conta) | (c) |
| Mostrar o dado | (a) só pelo prompt; (b) **pelo prompt e por uma trava no código** (a pergunta sem o dado ganha a frase "No arquivo, ... veio como ...") | (b) |

**Decisão.**
- **Conferir na hora** (`services/assistente_na_tela.py`, `_conferir_o_que_mudou`): o valor novo (a correção de uma
  pessoa, o grupo e o "preencher para todos") passa pela padronização e pelo dígito antes (ADR-127) e, depois da troca,
  pelo relatório refeito pelo Validador de verdade. É recusado quando nasce um achado que diz que o valor está errado
  (um BLOQUEANTE ou uma das `REGRAS_DE_VALOR_INVALIDO`: a CBO oficial, a pessoa repetida no arquivo, a pessoa em outro
  envio...) ou quando a própria pendência continua aberta com uma regra dessas. A troca volta pelo mesmo Desfazer, a
  trilha registra `VALOR_RECUSADO_NA_CONVERSA` (quem, a linha, o campo e as regras, sem valor) e a fala diz o que está
  errado (a mensagem da regra, sem nome técnico; na outra pessoa, de quem é), "Nada mudou.", o que a informação tem hoje
  e a pergunta com o exemplo do parâmetro. A recusa da padronização ganha também "O certo:" (a primeira parte da regra
  do parâmetro). O alerta que só pergunta fica, avisado na mesma fala ("Atenção: ... Ficou um cartão para você
  conferir."), e o aviso de quem fica de fora do envio também.
- **Mostrar o dado:** toda pergunta do agente sobre uma pessoa diz a informação e o que veio no arquivo (ou que veio
  vazio): o prompt pede (regra 12, com o campo novo `valor_na_tela`) e o código garante (`_com_o_dado_do_arquivo`).
- **O limite:** `LIMITE_DE_RESPOSTAS_SEM_VALOR = 3`. A ação nova `sem_valor` não muda nada; o balão do agente fica
  marcado (`sem_valor`, `encerrada`) em `conversas_das_pendencias`, e a conta é das respostas sem valor desde o último
  encerramento. Na 1ª e na 2ª, o agente ajuda a achar o dado sem repetir a fala (o campo novo
  `respostas_sem_valor_antes`); na 3ª, o encerramento educado, fixo no código: agradece, diz que a pendência continua
  aberta e pede para revisar a informação no arquivo (ou com o funcionário) e enviar de novo. A resposta chega com
  `encerrada`, e a tela mostra "Conversa encerrada. A pendência continua aberta."; a caixa continua valendo.
- **O prompt `assistente_correcao_v4`** (a padrão sem medir antes, pela regra de 30/09) e, no mesmo texto, "única por
  funcionário" no lugar de "de cada pessoa": nas regras 9 e 10 da v4, na fala do agente e no prompt
  `pergunta_da_pendencia_v4`, cuja conferência do redator passa a pedir essas palavras. O RAG fica como está (a tela
  não o mostra, e a troca pediria um índice novo).

**Porquê.** O Validador é a fonte única das regras: a conversa usa o próprio Validador em vez de copiar regras, e
qualquer regra nova de valor errado passa a valer na conversa sem mudar este código. As travas ficam no código, e não
só no prompt: o limite e o dado do arquivo valem com qualquer modelo, inclusive o que não seguir o prompt.

**Trade-off.**
- A troca recusada é gravada e desfeita: a trilha mostra a correção aplicada e a desfeita (com o evento que diz por
  quê), e o envio é validado duas vezes a mais nessa rodada.
- Um alerta que só pergunta, trazido por um valor certo, ainda vira um cartão (avisado na mesma fala).
- Depois de recarregar a página, a conversa de uma pendência aberta volta vazia (ela mora na página); a conta das
  respostas sem valor continua no servidor.

**Teste que comprova.** `tests/test_conferir_na_hora.py` (40 casos, em MOCK): o código da profissão fora da CBO em 4
formas (e com uma IA que "acreditou" no valor), o código certo em 5 formas, o salário que sai da faixa da profissão, o
código errado escrito errado de novo, o CPF de outra pessoa (em cima e embaixo), o dígito com o jeito certo e o exemplo,
a pergunta que ganha o dado (e a que já o tem), as 3 respostas sem valor em 3 jeitos de dizer, a conta que recomeça, a
recusa que não conta, a IA que só pergunta de novo e a rota. Também os testes ajustados em
`tests/test_assistente_na_tela.py`, `tests/test_cartoes_que_conferem.py` e `tests/test_perguntas_das_pendencias.py`, e o
roteiro de clique `conferir_na_hora`.

**Estende** o ADR-127 (a conferência antes do "Pronto") a todas as regras do Validador. **Origem.** O teste da usuária
na conversa da pendência, aprovado por ela em 30/09, pelo orquestrador.

---

### ADR-154 · A senha provisória vence em 48 h ✅

**Contexto (2026-09-30, teste da usuária).** A senha provisória que o especialista do banco gera no convite ou na "Nova
senha provisória" (ADR-109) obriga a troca no primeiro acesso, mas valia para sempre enquanto a pessoa não entrasse.
Uma senha que o especialista viu, entregue por um canal qualquer e esquecida, continuava abrindo o portal meses depois.
A usuária pediu que ela vença em 48 horas e que a tela de login diga a quem pedir.

**Opções.**
- (a) deixar como estava: a troca obrigatória no primeiro acesso já protege depois do uso;
- (b) um prazo fixo, contado da geração e conferido no login;
- (c) um link de uso único mandado por e-mail (a aplicação não manda e-mail).

**Decisão.** (b): a senha provisória vence em 48 h.
- **Uma coluna nova** na tabela `usuarios`: `senha_provisoria_gerada_em` (a hora em UTC, no formato ISO). Ela entra pela
  preparação da tabela (`auth.preparar_tabela`), como as colunas do ADR-146.
  - O convite e a "Nova senha provisória" gravam a hora (`auth.cadastrar_usuario` e `auth.redefinir_senha`).
  - A troca feita pela própria pessoa apaga a hora, e a senha passa a ser definitiva.
- **O prazo** fica em `services/auth.py`: `VALIDADE_DA_SENHA_PROVISORIA_HORAS = 48`, contadas de quando o especialista
  gerou a senha. A conta usa UTC e não muda com o fuso nem com o horário de verão.
- **No login** (`conferir_usuario_e_senha`), **depois da senha certa** e da suspensão do ADR-146:
  - a senha provisória vencida recebe 403, sem criar a sessão, com o aviso "A sua senha provisória venceu. Peça uma
    nova ao especialista do banco que cuida do relacionamento com a sua empresa.";
  - **não conta como senha errada**: a pessoa digitou a senha certa, e o bloqueio por tentativas (ADR-110) não anda;
  - a senha errada continua com a mensagem de sempre, e quem não sabe a senha não descobre que ela venceu.
- **Quem já está com uma senha provisória no dia da mudança** ganha a hora da mudança, gravada quando a coluna nasce.
  O prazo de 48 h conta dali, e não do passado, e ninguém fica com a senha vencida na hora. Uma provisória sem a hora
  (um caminho que não a gravou) não vence: a regra nunca bloqueia alguém por falta da hora.
- **A grade de usuários do banco** (Empresas, aba Usuários) mostra o selo "Senha provisória vencida", e o "i" da grade
  explica o selo e diz que a senha provisória vale por 48 horas. O botão "Nova senha provisória", que já existia, gera
  outra e zera o prazo.
- **A tela de login** passa a dizer "Primeiro acesso ou esqueceu a senha? Fale com o especialista do banco que cuida do
  relacionamento com a sua empresa."

**Porquê.** Fecha a janela da senha que o especialista viu e ninguém usou, na mesma forma do ADR-146: a regra é
conferida no login, sem serviço novo. O caminho da pessoa continua o mesmo, pedir ao especialista.

**Trade-off.**
- Quem recebe a senha e demora mais de 2 dias para entrar precisa pedir outra ao banco.
- A regra é conferida no login: uma sessão aberta dentro do prazo vale até vencer (8 horas), e a troca obrigatória
  acontece nela.
- Quem já tinha uma senha provisória no dia da mudança tem 48 horas, contadas da mudança, para entrar e trocá-la;
  depois, pede outra ao banco.

**Teste que comprova.** `tests/test_validade_da_senha_provisoria.py`, com 8 casos:
- a conta das 48 horas: no limite, a senha ainda vale; um minuto depois, venceu; a definitiva e a sem hora não vencem;
- dentro do prazo, a senha entra e cai na troca obrigatória;
- vencida, o login recusa com o aviso e sem cookie de sessão, e repetir a senha 6 vezes não bloqueia; a senha errada
  continua com a mensagem de sempre;
- a provisória sem a hora continua entrando;
- num banco antigo, sem a coluna, quem já tinha a provisória ganha a hora da mudança e só vence 48 horas depois;
- a "Nova senha provisória" zera o prazo;
- o convite grava a hora, e a troca pela pessoa a apaga;
- a grade do banco mostra a vencida; a empresa recebe 403, e quem não entrou, 401.

Os roteiros `tela_de_login` (o texto e o aviso na tela) e `senha_provisoria_na_aba` (o selo) conferem a tela.

**Estende** o ADR-109 (a senha provisória) e segue a forma do ADR-146 (a validade do acesso).
**Origem.** O teste da usuária, em 2026-09-30, aprovado por ela pelo orquestrador. Entra no desenho da arquitetura
atual (o `docs/seguranca.md` fica com o `arquiteto`).

---

<a id="adr-155"></a>
### ADR-155 · O "Baixar lista" de Acompanhar traz a grade inteira, em todas as situações ✅

**Contexto (2026-09-30, defeito achado pela usuária: "não tá baixando a lista").** O ADR-91 pôs na consulta de
funcionários quem ainda está em andamento (Em análise, Pendente e, depois, Aguardando envio, do ADR-114), mas deixou o
download só para os cadastrados ("os outros ainda podem mudar"). A tela mandava ao servidor só as pessoas com `id`.
- Numa grade sem nenhum cadastrado (a empresa com o primeiro envio ainda com o banco, ou um filtro numa dessas
  situações), a lista ia vazia, o servidor recusava (400) e a tela não dizia nada. No servidor da máquina local, as 3
  tentativas do dia deram 400.
- Com cadastrados, o arquivo saía sem as pessoas em andamento, diferente da grade.

**Opções.**
- (a) manter o download só de cadastrados e só explicar a recusa ao lado do botão;
- (b) o arquivo igual à grade com os filtros, em todas as situações, como o "Baixar CSV" da Visão geral do banco já faz.

**Decisão.** (b).
- **Um identificador de download para cada pessoa da lista** (`id_para_baixar`):
  - o cadastrado usa o mesmo `id` da ficha (o envio e a posição no arquivo final);
  - quem está em andamento usa o envio e a linha do arquivo (`envio.linhaN`). A marca "linha" nunca se confunde com a
    posição no arquivo final: depois do cadastro, o identificador antigo não acha ninguém, em vez de trazer outra
    pessoa.
- **O arquivo** (`acompanhamento.lista_para_baixar`) sai com as pessoas da mesma lista da grade
  (`todos_os_funcionarios_da_empresa`), na situação que a grade mostra. As colunas não mudam.
- **A ficha continua só de cadastrados:** quem está em andamento segue sem `id`.
- **Só a empresa da sessão:** o identificador de outra empresa é ignorado, e o pedido sem ninguém da empresa continua
  recusado (400), sem nenhum dado.
- **A tela:**
  - o botão manda o `id_para_baixar` de quem aparece com a busca e o filtro;
  - a recusa ("Nenhum funcionário para baixar com esses filtros.") ou a falha aparecem logo abaixo do botão, à vista;
  - com servidor, a amostra do protótipo nunca é baixada: antes de a lista chegar, o recado pede para tentar de novo.

**Porquê.** O botão promete "a lista que está na tela": o arquivo tem de ser a grade. O motivo do ADR-91 (os dados em
andamento ainda podem mudar) fica visível na coluna Situação. O CPF dessas pessoas já aparece inteiro na lista
(ADR-97), e o download continua registrado com a quantidade de pessoas.

**Trade-off.**
- O arquivo pode trazer valores que ainda vão mudar (Pendente, Aguardando envio); a coluna Situação avisa.
- O servidor monta a lista da grade de novo para o download (uma leitura a mais dos envios), como a própria lista faz.

**Teste que comprova.** `tests/test_baixar_lista_de_acompanhar.py`, com 7 casos:
- a empresa só com o envio em andamento baixa a grade: as colunas certas, uma linha por pessoa, a situação de cada uma
  e o acesso registrado;
- o envio com o banco sai "Em análise", e o filtro de situação vale;
- uma empresa nunca baixa as pessoas da outra, nem misturando os identificadores;
- o identificador de quem estava em andamento não vale depois do cadastro;
- sem login, 401; o banco, 403;
- cada pessoa da lista tem um identificador de download, sem repetir.

O roteiro de clique `baixar_lista_de_acompanhar` baixa a grade na tela de 1366 × 768 (sem filtro, com o filtro e com a
busca por CPF) e confere o recado logo abaixo do botão quando a grade está vazia.

**Revê** o ADR-91 (o download só de cadastrados). **Origem.** O defeito achado pela usuária em 2026-09-30, corrigido
com o ok do orquestrador.
