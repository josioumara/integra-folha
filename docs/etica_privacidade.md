# Ética, privacidade e responsabilidade

> Responde ao enunciado: **premissas, análises e técnicas aplicadas para garantir ética, privacidade e
> responsabilidade, com os cenários cobertos.** Decisões em `decisoes.md` (ADR-28 a ADR-30, ADR-10,
> ADR-16, ADR-38, ADR-96, ADR-97, ADR-101 e ADR-102); dados em `dados.md`.

> **Aviso.** As finalidades e o sigilo abaixo são **premissas da área de negócio** para o MVP. Em
> produção, precisam ser validadas pelo jurídico do banco. Não são parecer jurídico.

## 1. Premissas

### 1.1 Três finalidades para os dados da folha (ADR-28)

| Finalidade | Quem autoriza | O que o sistema faz |
|---|---|---|
| 1. Vincular o CPF à base de funcionários da empresa | Contrato banco × empresa | Cruza o arquivo homologado com a base do banco |
| 2. Análise de risco da empresa e do funcionário | Contrato banco × empresa | Enquadramento de renda pelo cargo (alerta, nunca acusação) |
| 3. Oferta ativa | O próprio cliente, **só se for correntista** e autorizar na abertura da conta | Nada individual: o motor de planejamento só produz números agregados |

Recuperar o **falso não folha** é **reconhecer um vínculo que já existe**, não vender. A base
sintética marca `correntista` e `autoriza_oferta_ativa`, e um teste garante que a autorização só existe
para correntista.

### 1.2 Sigilo bancário e conta do funcionário (ADR-30, revisto pelo ADR-102)

A empresa **vê a conta aberta de cada funcionário dela**: agência, número da conta e data de abertura,
na lista de funcionários, na ficha e no CSV da tela "Acompanhar cadastros". É nessa conta que ela paga
o salário. O arquivo semanal de contas abertas do banco traz CPF, data de abertura, agência e conta.

**Premissa de consentimento.** Ao abrir a conta para receber o salário, o funcionário autoriza o banco
a informar esses dados ao empregador. A Lei Complementar nº 105/2001 (art. 1º, § 3º, V) diz que não
viola o sigilo a revelação feita com o consentimento expresso do interessado. É premissa a validar
com o jurídico.

Saiu o **mínimo de pessoas** do ADR-30 (a premissa `minimo_pessoas_agregado` foi removida). O cartão
da empresa mostra o total ("20 de 35 já abriram a conta (57%)"); sem ninguém cadastrado, "Nenhum
funcionário cadastrado ainda.". Na aba Endomarketing do Portal Interno, o especialista do banco vê o total
exato de funcionários sem conta de cada empresa, como sugestão de lembrete (ADR-115), mas o comunicado não cita
pessoas, porque vai para toda a equipe.

**Continua valendo:** cada empresa só vê os próprios funcionários (isolamento); quem abre uma lista
fica registrado (ADR-97); oferta ativa só para correntista autorizado (ADR-28, ADR-29); o Consultor
e o motor de planejamento do banco só trabalham com números agregados.

### 1.3 Minimização por campo (ADR-29)

Cada campo do parâmetro do layout tem a marca `uso_comercial_permitido`. No layout v1, **só 8 dos 44**
campos têm S: `matricula`, `cpf`, `cnpj_empregador`, `codigo_unidade`, `nome_unidade`, `cep_comercial`,
`municipio_comercial` e `uf_comercial`, exatamente o necessário para cruzar com a base do banco e
agrupar por região comercial. Sexo, estado civil, nacionalidade, data de nascimento, renda e endereço
residencial continuam no cadastro (vínculo e risco), mas **o motor não os lê**.

## 2. Matriz de cenários

| Cenário | Premissa e técnica aplicada | Como é verificado | Situação |
|---|---|---|---|
| **Finalidade (LGPD)** | Três finalidades separadas; oferta ativa só com autorização do correntista; o motor não gera ofertas nem listas de pessoas | Teste da base sintética (`autoriza_oferta_ativa` só com `correntista`); motor sem saída individual | Base ✅ · motor na Fase 9 |
| **Minimização por campo** | Motor lê só campos com `uso_comercial_permitido = S` | Teste de colunas proibidas | Parâmetro ✅ · teste na Fase 9 |
| **Sigilo bancário** | A empresa vê a conta de cada funcionário dela, por consentimento dado na abertura (ADR-102); o Consultor e o motor do banco, só agregados; o comunicado do Endomarketing não cita pessoas | Teste: a empresa só recebe as contas dos próprios funcionários; o Consultor recusa listas | ✅ · consentimento com o jurídico |
| **Privacidade pelo destino** | A IA vê os dados reais (amostras, texto do documento, valor da pendência), porque roda só numa nuvem contratada: AWS Bedrock, perfil EUA, retenção zero, sem acesso do fornecedor do modelo (seção 6). Logs, auditoria e telemetria continuam sem dado pessoal | Testes da porta de saída da IA (perfil EUA, recusa dos modelos que guardam pedidos); painel sem CPF ou salário | Código ✅ · conta ⏳ (chave do Bedrock) (ADR-96, ADR-101) |
| **Dados sintéticos** | Nenhum dado real; seed fixa; e-mails em domínio `.example` | Testes de reprodutibilidade; ficha do dataset | ✅ (`dados.md`) |
| **Índices do RAG sem dado de funcionário** | O índice guarda o parâmetro, com o exemplo que o banco cadastrou (também no campo de dado pessoal: é um exemplo, não uma pessoa; ADR-101); o histórico guarda nomes de colunas, não pessoas | Teste: o exemplo do parâmetro entra no índice; o histórico só com pares de colunas homologados | ✅ (`tests/test_rag.py`) |
| **Isolamento entre empresas** | A empresa vem do usuário logado, nunca do texto; filtro obrigatório por empresa e vigência na busca | Teste: cada empresa só recebe o próprio catálogo; pedir o pacote de outra não traz nada dela | ✅ (`tests/test_rag.py`) |
| **Controle de acesso** | Perfil vem do cadastro; o porteiro da API confere o perfil antes de entregar cada página, e cada rota confere de novo | Todas as páginas × todos os perfis, e sem login | ✅ (`tests/test_api_front.py`) |
| **Senhas e sessões** | Senha só como hash (bcrypt); sessão com ingresso aleatório e só o hash no banco; revogada ao sair, redefinir senha ou desativar | Testes de autenticação e sessão | ✅ (`tests/test_auth.py`, `tests/test_sessoes.py`) |
| **Prompt injection** | Guardrail na entrada (remove o trecho, marca o chat, recusa documento) e conferência na saída (schema, campos do parâmetro, números das ferramentas, fontes) | Testes de ataque; taxa de detecção e de alarme falso | Catálogo ✅ · arquivo e chat nas Fases 3, 7 e 13 |
| **Vieses e discriminação** | Segmento vem da base oficial (só filtro); atributos sensíveis fora do motor; renda atípica é **alerta**, corrigido ou justificado pela empresa | Teste de colunas proibidas; texto do alerta revisado | Fases 6 e 9 |
| **Supervisão humana** | Aceite de mapeamento ambíguo, correções, justificativas, homologação, publicação dos textos do Endomarketing pelo especialista do banco (ADR-115) e mudança de parâmetros exigem clique (ADR-16) | Testes de fluxo com pausa e retomada | Spike ✅ · fluxo nas Fases 7 e 8 |
| **Transparência** | Mapeamento com justificativa e fonte; Endomarketing cita a fonte do catálogo, e só o banco publica o que a empresa divulga (ADR-115); estimativa sempre rotulada, com premissas visíveis | Tela de aceite; fidelidade às fontes medida | Fases 4, 10 e 14 |
| **Números inventados** | Números vêm do motor determinístico; Consultor e subagentes só respondem com dados das ferramentas | Testes golden do Consultor | Fase 11 |
| **Execução descontrolada** | Limite de iterações e de laço entre agentes; limite de chamadas por sessão com queda para MOCK | Testes de limite | Cliente de LLM ✅ · laços nas Fases 7 e 11 |
| **Onde a IA roda** | AWS Bedrock, perfil EUA, na conta do projeto; modelos que guardam pedidos recusados no código e na conta; embeddings rodam localmente. Até a chave do Bedrock, rota direta (APIs da Anthropic e da OpenAI), só com dados fictícios. Transferência internacional (LGPD, art. 33) com o jurídico | `tests/test_provedores_de_ia.py`; com a chave, `scripts/preparar_bedrock.py` (retenção zero gravada e lida de volta) | ADR-96 🟨 (chave e jurídico pendentes) |
| **Responsabilidade e auditoria** | Cada execução registra versão de prompt, modelo, dados e decisão humana; execuções falsas do painel são rotuladas MOCK e nunca exibem número inventado | Telemetria; model card do Interpretador | Painel MOCK ✅ · eventos reais na Fase 12 |

## 3. O que um ataque bem-sucedido **não** consegue fazer

Mesmo que uma injeção passe pela portaria, o desenho limita o estrago:

- **Alterar dado:** correções só valem com clique humano; o Normalizador não usa LLM.
- **Ver outra empresa:** o filtro vem do login, não do texto; o documento de outra empresa nem chega ao agente.
- **Inventar número:** os números vêm do motor; a resposta do Consultor é conferida com as ferramentas.
- **Mapear para campo inexistente:** o destino só é aceito se existir no parâmetro vigente.

## 4. Limites conhecidos

- As premissas de finalidade, sigilo e consentimento (conta informada ao empregador, ADR-102) são da área de
  negócio; a validação jurídica é pré-requisito de produção.
- A detecção de injeção por padrões tem alarme falso e falha; por isso é uma camada entre várias, e as
  taxas são medidas na Fase 13.
- Dados sintéticos não reproduzem todos os vieses de dados reais; um piloto precisa de nova análise de impacto.
- A IA vê os dados reais: a privacidade depende de ela rodar pelo Bedrock, com retenção zero. A rota direta só serve
  para dados fictícios.

## 5. Onde a IA poderia inventar, e o que a segura (decisão 6)

**A regra:** a IA aponta, o código copia. O valor sempre sai do documento que a pessoa enviou; a IA nunca apaga um
campo; toda dúvida vira uma pergunta que diz a pessoa, o campo e o trecho exato. **Por quê:** o documento continua
sendo a referência de quem o enviou; o que aparece na tela tem de ser achado lá.

| Agente | O que ele poderia inventar | O que segura | Onde está |
|---|---|---|---|
| Interpretador | Uma coluna que não existe, um campo fora do layout, uma fonte | Guardrail de saída: o que não existe vira pendência; a empresa aceita as colunas; as amostras reais entram como dado, nunca como instrução | `agents/interpretador.py` (ADR-38) |
| Leitor de Documentos | Um valor que não está no documento (ex.: um CPF "corrigido") | O código procura o valor, palavra por palavra, no bloco da pessoa e copia de lá; não achou, fica o trecho que a IA citou e uma pergunta com o parágrafo; nenhum campo é apagado; parágrafo com dado fora dos blocos vira aviso | `leitor_de_documentos.pedaco_do_bloco`, `conferir_pessoa`, `avisar_paragrafos_com_dado_fora_dos_blocos` |
| Assistente de Correção | Um valor novo que ninguém pediu | Só propõe; vale com o clique da pessoa, e o envio é validado de novo | `assistente_correcao`, `correcoes` (ADR-16) |
| Explicação do Validador | Mudar a gravidade de uma pendência | A gravidade vem da regra; o LLM recebe o valor de cada achado, mas só explica: não muda a gravidade nem o valor | ADR-13, ADR-101 |
| Consultor | Um número | Todo número do texto tem de ter vindo das ferramentas; senão, a redação é trocada pelos números das ferramentas | `consultor.numeros_fora_dos_resultados` |
| Endomarketing | Um benefício fora do catálogo ou não escolhido pelo banco | A IA recebe só os trechos dos benefícios que o especialista escolheu (mais os canais de atendimento); todo bloco cita uma fonte desses trechos; sem fonte ou com número fora do trecho, sai; o especialista do banco publica antes de a empresa ver (ADR-115) | `agents/endomarketing.py` |

## 6. Privacidade pelo destino: onde a IA roda (ADR-81, ADR-96, ADR-101)

Nenhum filtro na frente da IA garante 100% num arquivo bagunçado: detector erra (ADR-96). O que dá para garantir é
**quem recebe o pedido**. Por isso a IA vê os dados reais (ADR-101), e a proteção vem de três coisas:

- **O destino.** A IA roda pelo AWS Bedrock, no perfil EUA, na conta do projeto. Os modelos rodam em contas da AWS às
  quais o fornecedor do modelo não tem acesso, e a conta tem retenção zero. Os modelos que guardam pedidos por até 30
  dias ficam de fora duas vezes: no código e na conta (ADR-96).
- **O controle de acesso.** A empresa vem do login e só vê o que é dela; cada perfil só abre as suas telas; quem abre
  uma lista com dados fica registrado (ADR-97).
- **O registro sem dado pessoal.** Auditoria e telemetria guardam identificadores, etapas e contagens, nunca o conteúdo.

As regras sobre o uso dos dados não mudam: oferta ativa só para correntista autorizado (ADR-28, ADR-29); Consultor e
motor só com números agregados; o conteúdo do arquivo é dado, nunca instrução (ADR-38). A empresa vê a conta só dos
próprios funcionários, por consentimento dado na abertura (ADR-102).

Ver os dados também acerta mais: no EXP-010, o Leitor acertou 98,9% lendo os dados, contra 91,3% com etiquetas no
lugar dos dados pessoais (o modo usado até o ADR-101).

**Enquanto a chave do Bedrock não chega,** o `.env` usa `ROTA_DA_IA=direta` (APIs da Anthropic e da OpenAI). Isso
não expõe ninguém, porque todos os dados do projeto são fictícios. Com dado real, só pelo Bedrock.

| Caminho | Exemplo | O dado sai do banco? | Custo, ordem de grandeza | Quando escolher |
|---|---|---|---|---|
| **Hoje (o projeto)** | Sonnet 5 e GPT-6 Luna no AWS Bedrock, perfil EUA, retenção zero | Sai para a conta do projeto na AWS; o fornecedor do modelo não vê o pedido | Centavos por arquivo (medido nas APIs diretas: ≈ US$ 0,01 a 0,05 por documento; +10% no perfil EUA) | Prova de conceito, dados fictícios |
| **Nuvem que o banco já contrata** | Claude no Amazon Bedrock, no Google Vertex AI ou no Microsoft Foundry (Azure) | Fica no contrato de nuvem do banco; o provedor do modelo não vê os pedidos | Por uso, como a API, no faturamento da nuvem do banco | O banco já tem a nuvem homologada: é o desenho de hoje, na conta do banco |
| **Modelo aberto no servidor do banco** | gpt-oss-120b (uma placa de 80 GB) ou Qwen3 (de 4B a 235B), servidos com vLLM | **Não sai** | Placa H100: ≈ US$ 1,50 a 7 por hora alugada, ou compra; sem custo por chamada | Volume muito alto (≈ 1,04 milhão de funcionários), exigência de dado no país, ou junto com Fine-Tuning |
| ~~API de modelo aberto de terceiros~~ | Groq, Together, OpenRouter | **Sai** | Centavos | Não resolve a privacidade: é externo de novo |

Os dois modelos do projeto não rodam na região de São Paulo; lá, o Bedrock oferece o Claude só com roteamento global.
Nos dois casos, o dado sai do Brasil: é transferência internacional de dados (LGPD, art. 33; para banco, também a
Resolução CMN nº 4.893/2021), que continua com o jurídico. Quem precisa do dado no país escolhe o modelo aberto no
servidor do banco. Fontes no ADR-81 e no ADR-96.
