# Integra Folha

Prova de conceito da certificação de Engenharia de IA: a empresa envia a lista de funcionários **no
formato que já tem**, a IA entende as colunas, regras padronizam e validam, um humano aprova o que é
sensível e, depois da homologação, o banco planeja a conquista desses clientes com uma equipe de
agentes. **Dados 100% sintéticos.**

> **Para acessar e instalar:** [`MANUAL_DE_INSTALACAO_E_ACESSO.md`](MANUAL_DE_INSTALACAO_E_ACESSO.md) (o site publicado,
> a instalação local, com Docker e na AWS). **A apresentação da banca:** [`apresentacao/`](apresentacao/).

| Documento | Conteúdo |
|---|---|
| [`docs/case.md`](docs/case.md) | O case: dor, solução, business case, escopo e como provamos |
| [`docs/arquitetura.md`](docs/arquitetura.md) | Desenho da solução, componentes e segurança |
| [`docs/decisoes.md`](docs/decisoes.md) | Decisões e porquês (ADRs) |
| [`docs/dados.md`](docs/dados.md) | Ciclo de vida dos dados e ficha do dataset sintético |
| [`docs/banco_de_dados.md`](docs/banco_de_dados.md) | Os bancos (PostgreSQL ou SQLite, checkpoints, ChromaDB) e os arquivos: o que guardam, a avaliação que escolheu o PostgreSQL, como inspecionar (DBeaver) e o que usar se a aplicação crescer |
| [`docs/avaliacao.md`](docs/avaliacao.md) | O que medimos, com que amostra, os resultados, os negativos e o que falta |
| [`docs/experimentos.md`](docs/experimentos.md) | Histórico de cada experimento: o que testamos, com qual modelo, recall, precisão e a decisão |
| [`docs/prompts.md`](docs/prompts.md) | Cada prompt versionado, o que ele diz e por quê |
| [`docs/model_card_interpretador.md`](docs/model_card_interpretador.md) | Ficha do Interpretador: uso, limites e avaliação |
| [`docs/etica_privacidade.md`](docs/etica_privacidade.md) | Premissas e matriz de cenários de ética e privacidade |
| [`docs/seguranca.md`](docs/seguranca.md) | Segurança: site, login, acesso aos dados, IA e prompt, arquivos, segredos, hospedagem, lacunas e o teste de cada controle |
| [`docs/proximos_passos.md`](docs/proximos_passos.md) | Plano até produção e melhorias |

> **Estado:** fluxo completo construído e medido em modo MOCK. O arquivo vai do envio à homologação e ao
> planejamento do banco (só números agregados, sem IA), com Endomarketing, o desempenho da IA (aba Telemetria) e guardrails. A IA real entra quando o
> provedor for escolhido; o que já foi medido e o que falta estão em [`docs/avaliacao.md`](docs/avaliacao.md).

## Pré-requisitos

- Python 3.12 (3.11+)
- Git
- Docker Desktop (opcional; usado para empacotar e publicar)

## Como rodar (Windows, PowerShell)

```powershell
cd integra-folha
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Configuração: copie o modelo (as senhas ficam em branco na sua máquina)
copy .env.example .env

# Cria os dois usuários da demo: o script pergunta a senha de cada um
.\.venv\Scripts\python.exe scripts\criar_usuarios.py

# Liga a aplicação (a API entrega as páginas do front e as rotas /api)
.\.venv\Scripts\python.exe -m uvicorn api.principal:aplicacao --port 8000
```

Depois, abra `http://localhost:8000/login.html` no navegador. O perfil EMPRESA vai para o Portal Empresa e o perfil
BANCO para o Portal Interno (as telas do especialista). Página de outro perfil volta para a sua. Aberto com dois
cliques (sem o servidor), o login do `front/` não funciona.

Usuários da demo: `empresa.aurora` (EMPRESA, EMP001) e `especialista.banco` (BANCO), com as senhas que você
digitou ao rodar o script. Nesta versão existem só esses dois perfis: o que a empresa vê e o que o banco vê (o banco
tem a gestão completa; o perfil CIENTISTA saiu em 2026-09-26). As senhas não ficam
em arquivo nenhum: o banco guarda só o hash.

**Modo MOCK:** com `MODE=mock` no `.env` (padrão), nenhuma chamada vai a um provedor de IA; as
respostas são simuladas. Não precisa de chave e não tem custo.

**Para a demo completa**, gere também os dados e os índices do RAG antes de abrir a tela (uma vez):

```powershell
.\.venv\Scripts\python.exe scripts\gerar_dados.py
.\.venv\Scripts\python.exe scripts\build_index.py
```

Sem os índices, nada quebra (ADR-63): o Interpretador usa a configuração sem busca (B2), o Assistente
conversa sem trechos de apoio e o Endomarketing avisa que o catálogo ainda não está pronto.

### Banco de dados: SQLite (padrão) ou PostgreSQL

Sem configurar nada, a aplicação usa o **SQLite** (um arquivo em `storage/`, sem servidor): é o jeito mais rápido de
reproduzir o projeto. O banco de uso e de produção é o **PostgreSQL** (ADR-67). Para ligá-lo:

```powershell
# 1. Com o PostgreSQL instalado, ponha no .env a conexão do superusuário (só para a preparação):
#    POSTGRES_ADMIN_URL=postgresql://postgres:SENHA@localhost:5432/postgres
# 2. Cria o usuário da aplicação (sem superpoderes) e os bancos; grava POSTGRES_URL e POSTGRES_URL_TESTES no .env
.\.venv\Scripts\python.exe scripts\preparar_postgres.py
# 3. (Opcional) Copia para o PostgreSQL o que já existe no SQLite; nunca sobrescreve um banco com dados
.\.venv\Scripts\python.exe scripts\migrar_sqlite_para_postgres.py
# 4. No .env: BANCO=postgres
```

Para ver as tabelas, conecte o **DBeaver** ao banco `integra_folha` (passo a passo em `docs/banco_de_dados.md`, seção 9).

## Configuração (`.env`)

| Variável | Para que serve | Padrão |
|---|---|---|
| `MODE` | `mock` (respostas simuladas, sem chave nem custo) ou `llm` (provedor real) | `mock` |
| `LIMITE_CHAMADAS_LLM_POR_SESSAO` | Chamadas reais por sessão antes de cair para MOCK | `50` |
| `TETO_DE_GASTO_USD` | Gasto máximo por sessão, em dólares, antes de cair para MOCK (a trava final é o crédito de cada conta) | `10.00` |
| `BANCO` | `sqlite` (um arquivo, sem servidor) ou `postgres` (servidor PostgreSQL; ADR-67) | `sqlite` |
| `CAMINHO_BANCO` | Banco SQLite (usuários, arquivos, estados, planejamento), quando `BANCO=sqlite` | `storage/integra_folha.db` |
| `POSTGRES_URL`, `POSTGRES_URL_TESTES` | Conexões do usuário da aplicação com o banco de uso e o de testes (gravadas por `scripts/preparar_postgres.py`) | vazio |
| `POSTGRES_ADMIN_URL` | Conexão do superusuário, usada **só** por `scripts/preparar_postgres.py` | vazio |
| `SENHA_USUARIO_*` | Senhas dos usuários da demo, **só no servidor**; na sua máquina, em branco | vazio |
| `SENHA_DA_BASE_VIVA` | Senha única dos logins da base viva, usada por `scripts/carregar_base_viva.py`; **só no `.env`** | vazio |
| `SENHA_DOS_TESTES` | Senha dos usuários de teste, lida pelos testes e pelos roteiros de clique (`tests/e2e/apoio.py`); **só no `.env`** | vazio |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Chaves dos provedores de IA na rota direta; **só no `.env`**, nunca no código nem no Git | vazio |
| `ROTA_DA_IA` | `bedrock` (a nossa conta na AWS, perfil EUA; o fornecedor do modelo não vê o pedido; ADR-96) ou `direta` (APIs da OpenAI e da Anthropic) | `direta` |
| `AWS_BEARER_TOKEN_BEDROCK`, `REGIAO_BEDROCK` | Chave do Bedrock (**só no `.env`**) e a região de onde as chamadas saem | vazio, `us-east-1` |
| `MODELO_GRANDE`, `MODELO_PEQUENO` | Modelos que os agentes usam no modo `llm` (saem da comparação de modelos, ADR-11) | vazio |
| `LIMITE_UPLOAD_MB` | Tamanho máximo do arquivo enviado | `5` |
| `PASTA_UPLOADS`, `PASTA_HOMOLOGADOS` | Originais recebidos e arquivos finais homologados (fora do Git) | `storage/...` |
| `CAMINHO_CHECKPOINTS` | Onde o fluxo guarda o ponto em que cada arquivo parou, quando `BANCO=sqlite` (no PostgreSQL, fica no próprio banco) | `storage/checkpoints.db` |

O `.env` nunca vai para o Git; o modelo versionado é o `.env.example`.

### Como recriar o `.env`

Os segredos (chaves de API e senhas) ficam **só** no `.env` e no gerenciador de senhas, numa nota "Integra Folha -
.env" (decisão de 2026-09-26). O `.env` não vai para o Git **nem para a cópia de segurança**. Numa máquina nova, ou
depois de restaurar uma cópia:

1. `copy .env.example .env`
2. Preencha as linhas marcadas com `[SEGREDO]` no `.env.example`, com o que está no gerenciador de senhas. As outras
   já vêm com o valor padrão. Chave de API perdida se gera de novo no painel do provedor; chave vazada se apaga lá.
3. Confira sem gastar nada: `.\.venv\Scripts\python.exe -m pytest tests/test_provedores_de_ia.py`.

### Cópia de segurança

```powershell
# Só conta o que iria (sem copiar)
.\.venv\Scripts\python.exe scripts\copia_de_seguranca.py --simular
# Copia D:\AI_Payroll_Hub para G:\Meu Drive\ProjetoIA\AAAAMMDD_HHMM, com uma cópia do banco PostgreSQL
.\.venv\Scripts\python.exe scripts\copia_de_seguranca.py
```

Fica de fora o que não se deve ou não precisa guardar: o `.env` (segredos), os ambientes virtuais, os modelos
baixados e os índices do RAG (refeitos pelo `scripts/build_index.py`). Para rodar sozinha todo dia às 7h30, crie a
tarefa no Agendador de Tarefas do Windows (uma vez, no PowerShell):

```powershell
schtasks /Create /SC DAILY /ST 07:30 /TN "Integra Folha - copia" /TR "D:\AI_Payroll_Hub\integra-folha\.venv\Scripts\python.exe D:\AI_Payroll_Hub\integra-folha\scripts\copia_de_seguranca.py"
```

## Solução de problemas

| O que aparece | O que fazer |
|---|---|
| Ao abrir uma página, volta para o login ou para a sua página inicial | Entre com um usuário do perfil da página (ver "Quem vê o quê"). Sem usuários, rode `scripts\criar_usuarios.py`. |
| "Falta a chave da OpenAI / Anthropic" ou "Falta escolher o modelo" | O `.env` está com `MODE=llm`, mas falta `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` ou `MODELO_GRANDE`/`MODELO_PEQUENO`. Preencha, ou volte para `MODE=mock`. |
| "Monte os índices antes: python scripts/build_index.py" | Rode `scripts\build_index.py`. Na primeira vez ele baixa o modelo de embeddings (~220 MB, precisa de internet) para `storage\modelos`. |
| `build_index` falha com "Could not load model ... from any source" e, antes, "No such file or directory" | O caminho do arquivo do modelo passou do limite do Windows (260 caracteres): a pasta do projeto está funda demais. Coloque o projeto numa pasta curta (ex.: `D:\AI_Payroll_Hub`) ou ative os caminhos longos do Windows. |
| "Gere os arquivos de envio antes: python scripts/gerar_dados.py" | Rode `scripts\gerar_dados.py` (os arquivos de envio não vão para o Git). |
| "A prova ou as métricas mudaram depois do congelamento" | Algum arquivo da prova mudou. Se foi sem querer, desfaça (`git checkout <arquivo>`). Se foi de propósito, recongele dizendo o motivo: `scripts\congelar_avaliacao.py "motivo"`. |
| "A planilha tem fórmulas (ex.: célula ...)" | No Excel, copie tudo e cole como **valores**, salve e envie de novo. |
| "O conteúdo não é um CSV (texto)" ou "não é uma planilha Excel válida" | A extensão do arquivo não bate com o conteúdo. Salve de novo como `.xlsx` ou `.csv`. |
| A porta 8000 está ocupada | `.\.venv\Scripts\python.exe -m uvicorn api.principal:aplicacao --port 8001` (e abra `http://localhost:8001/login.html`) |
| "BANCO=postgres, mas falta POSTGRES_URL no .env" | Rode `scripts\preparar_postgres.py` (precisa de `POSTGRES_ADMIN_URL`), ou volte para `BANCO=sqlite`. |
| `connection refused` / `Connection refused` na porta 5432 | O serviço do PostgreSQL está parado: no PowerShell como administrador, `Start-Service postgresql-x64-18`. |
| Os testes no PostgreSQL | `$env:BANCO_DOS_TESTES="postgres"; .\.venv\Scripts\python.exe -m pytest` roda a bateria inteira no banco de testes (nunca no da aplicação). |
| O PowerShell não deixa ativar o ambiente virtual | Não precisa ativar: chame sempre `.\.venv\Scripts\python.exe`, como nos comandos deste README. |

## Quem vê o quê

| Perfil | Páginas |
|---|---|
| EMPRESA | Portal Empresa: Início, Cadastrar funcionários, Acompanhar cadastros, Benefícios do seu time, Materiais de endomarketing (só a lista dos que o banco publicou, para baixar) |
| BANCO | Portal Interno: Início, Empresas (com os usuários de cada uma e o kit de marca, com o logo), Endomarketing (gerar, publicar e retirar os materiais de cada empresa, ADR-115), Avaliar envios, Mensagens, Contas abertas, Planejamento, Telemetria (Uso das empresas e Desempenho da IA), Parâmetros |
| Todos | Minha senha (no cabeçalho de todas as páginas) |

O porteiro da API (`pagina_permitida`, em `api/principal.py`) confere o perfil antes de entregar cada página: digitar o
endereço de uma página de outro perfil leva de volta à sua página inicial, e sem login, ao login. Cada rota `/api`
confere o perfil de novo. A sessão dura 8 horas e acaba ao fechar o navegador: o F5 não desloga; "Sair" encerra a
sessão de verdade (ADR-40).

## Segurança: matriz de permissões e riscos

### Quem pode fazer o quê (conferido também nos serviços, não só na tela)

| Operação | EMPRESA | BANCO | Onde é conferido |
|---|:---:|:---:|---|
| Enviar arquivo, aceitar mapeamento, corrigir, justificar, homologar | ✅ só da própria empresa | — | `processamentos.obter_da_empresa` (empresa vazia é recusada) |
| Conversar com o Assistente de Correção | ✅ só da própria empresa | — | idem + guardrail na mensagem |
| Gerar, publicar e retirar material de Endomarketing; subir o logo do kit (ADR-115) | — | ✅ de qualquer empresa da carteira, com os benefícios escolhidos | rotas `/api/banco/empresas/{id}/endomarketing/...` e `/kit/logo` (só BANCO) + `acesso.gerar_material` |
| Ver e baixar os materiais de Endomarketing publicados (texto e arte) | ✅ só os publicados da própria empresa | — | `GET /api/empresa/endomarketing` (empresa vem do login) |
| Ver a conta aberta de cada funcionário (agência, conta, data de abertura) | ✅ só dos próprios funcionários, por consentimento dado na abertura (ADR-102) | — | `acompanhamento.ficha_do_funcionario`, `acompanhamento.lista_para_baixar` |
| Ver o número de funcionários sem conta | ✅ o total exato da própria empresa (cartão do Início) | ✅ o total de cada empresa, como sugestão de lembrete no Endomarketing | `endomarketing.consultar_resumo_equipe` |
| Planejamento e salvar simulação | — | ✅ só números agregados | rotas `/api/banco/planejamento/...` (só BANCO) + `acesso.salvar_simulacao` |
| Editar o layout e o catálogo de benefícios | — | ✅ | rotas `/api/banco/...` (só BANCO) / `acesso.adicionar_documento` |
| Gerir as pessoas das empresas (convidar, gerar nova senha provisória, ativar) | — | ✅ (não a si mesmo) | `acesso.*` |
| Ver o desempenho da IA (execuções dos agentes) | — | ✅ sem CPF nem texto de mensagem | `acesso.execucoes_do_painel` |
| Trocar a própria senha | ✅ | ✅ | exige a senha atual |

A tabela que os serviços usam é `PERFIS_POR_OPERACAO` (`services/permissoes.py`); um teste garante que
a API e os serviços dos portais não chamam uma operação sensível sem passar pela porta `services/acesso.py`.

### Riscos e o que os barra

| Risco | O que barra | Teste |
|---|---|---|
| Ordem escondida para a IA numa célula, cabeçalho, mensagem, pergunta ou documento | Guardrail de injeção (lista + segunda opinião de modelo pequeno no modo LLM); texto de fora vai ao LLM como DADO | `test_adversarial.py` 1, 2, 5; `test_seguranca.py` (prova: 100% de detecção, 0% de falso alarme) |
| A IA "aprovar" ou homologar algo | A IA só propõe; aceite, correção e homologação são cliques humanos no fluxo | `test_adversarial.py` 3, 14 |
| Envenenar o conhecimento do RAG pelo chat | Só o mapeamento homologado por pessoa vira histórico, como par estruturado | `test_adversarial.py` 4 |
| Uma empresa ver dados de outra | Filtro por empresa nos serviços e no RAG; empresa vem do login | `test_adversarial.py` 6 |
| Acesso sem login ou com perfil errado | Porteiro das páginas, checagem em cada rota da API e na porta dos serviços | `test_adversarial.py` 8; `test_api_front.py`; `test_seguranca.py` |
| Gasto descontrolado com IA | Limite de chamadas e teto de gasto por sessão; ao atingir, cai para MOCK | `test_adversarial.py` 9; `test_seguranca.py` |
| Laço entre agentes | Limites: 2 handoffs por arquivo e 20 ciclos de correção | `test_adversarial.py` 11 |
| Identificar quem não tem conta | O Planejamento do banco só mostra números agregados; a empresa vê a conta só dos próprios funcionários, por consentimento dado na abertura (ADR-102); o comunicado do Endomarketing não cita pessoas | `test_planejamento.py` (nenhum CPF sai do planejamento); `test_acompanhamento.py` |
| Número inventado pela IA | Guardrail de saída: todo número do material tem de vir do trecho citado do catálogo (Endomarketing) | `test_endomarketing.py` |
| Arquivo falso, fórmula, planilha gigante | Tipo pelo conteúdo, fórmulas recusadas, limites de linhas e colunas | `test_seguranca.py` |
| Fórmula executada ao abrir o arquivo final (CSV injection) | Apóstrofo antes de `=`, `+`, `@`... no arquivo homologado | `test_seguranca.py` |
| Dado pessoal em log ou painel | Execuções e eventos só com identificadores, etapas e contagens | `test_painel.py` |
| Dado pessoal no pedido à IA | A IA vê os dados, mas só pelo AWS Bedrock (perfil EUA, retenção zero, sem acesso do fornecedor do modelo); modelos que guardam pedidos são recusados antes de sair (ADR-96, ADR-101) | `test_provedores_de_ia.py` |

Riscos que ficam para produção (fora do MVP): autenticação corporativa (SSO), segredo em cofre de chaves,
validação jurídica do consentimento para informar a conta ao empregador (sigilo bancário) e da base legal (ver
`docs/etica_privacidade.md`).

## Spike de pausa e retomada

A prova de que o fluxo para esperando uma pessoa e continua de onde parou, mesmo depois de reiniciar o servidor, é o
teste `tests/test_spike_pausa_retomada.py` (o grafo do spike fica em `workflows/spike_grafo.py`):

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_spike_pausa_retomada.py
```

## Dados, avaliação e RAG

```powershell
# Dados sintéticos (empresas, funcionários, arquivos de envio com erros e gabarito)
.\.venv\Scripts\python.exe scripts\gerar_dados.py
# Cabeçalhos de treino e prova, calibração e medição do baseline B0 (sem IA)
.\.venv\Scripts\python.exe scripts\gerar_cabecalhos.py
.\.venv\Scripts\python.exe scripts\calibrar_b0.py
# Congela a prova e as métricas antes de medir (só de novo se a prova mudar de propósito, com o motivo)
.\.venv\Scripts\python.exe scripts\congelar_avaliacao.py "prova inicial da Fase 14"
.\.venv\Scripts\python.exe scripts\avaliar_interpretador.py B0
# Fluxo da empresa de ponta a ponta nos 9 arquivos (MOCK, num banco temporário: o banco local não é tocado)
.\.venv\Scripts\python.exe scripts\avaliar_fluxo.py
# Endomarketing: fidelidade às fontes, isolamento, recusa e guardrail de saída (busca real no catálogo)
.\.venv\Scripts\python.exe scripts\avaliar_endomarketing.py
# Guardrail de injeção: lista, classificador e os dois juntos (o classificador só no modo LLM)
.\.venv\Scripts\python.exe scripts\avaliar_guardrail.py
# Comparação dos modelos de IA selecionados (dinheiro de verdade: precisa das chaves no .env; teto US$ 25)
.\.venv\Scripts\python.exe scripts\comparar_modelos.py
# Índices do RAG (baixa o modelo de embeddings local na primeira vez, ~220 MB) e medição
.\.venv\Scripts\python.exe scripts\build_index.py
.\.venv\Scripts\python.exe scripts\avaliar_rag.py
# Ver o que está nos índices do RAG (ChromaDB): coleções, exemplos e uma busca de teste
.\.venv\Scripts\python.exe scripts\ver_indices_rag.py --buscar "salário bruto"
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Os roteiros de clique (a tela, no Chrome, cada um num banco temporário e sem custo) ficam fora do `pytest`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests\e2e\requirements.txt   # uma vez
.\.venv\Scripts\python.exe tests\e2e\rodar.py
```

Detalhes e como escrever um roteiro novo em `tests/e2e/README.md` (ADR-84).

## O front (ADR-69)

As páginas ficam em `front/` (HTML, CSS e JavaScript) e são entregues pela API FastAPI (`api/principal.py`), que usa
os serviços de `services/` e confere o login e o perfil em cada página e em cada rota. É a única interface da
aplicação: as telas antigas em Streamlit saíram depois que o front novo passou a cobrir o que elas faziam (ADR-108).
Para ligar, veja "Como rodar" acima.

## Docker

### Com Docker Compose: aplicação + PostgreSQL num comando (recomendado)

Não precisa instalar o PostgreSQL: o `docker-compose.yml` sobe dois contêineres, o banco (imagem oficial do
PostgreSQL 18) e a aplicação (ADR-67).

1. No `.env`, preencha:
   - `SENHA_POSTGRES_ADMIN` e `SENHA_POSTGRES_APLICACAO`: senhas do administrador e do usuário da aplicação no banco
     do contêiner, **só letras e números** (a segunda vai dentro do endereço de conexão);
   - `SENHA_USUARIO_EMPRESA` e `SENHA_USUARIO_BANCO`: os dois usuários da demo.
2. Suba:

```powershell
docker compose up --build
```

3. Abra `http://localhost:8000/login.html` (a API atende as telas e as rotas `/api`, ADR-108).

Na **primeira** subida:
- o banco roda `docker/postgres/criar_usuario_da_aplicacao.sh`, que cria o usuário da aplicação (sem poderes de
  administrador) e o banco;
- a aplicação espera o banco ficar pronto e roda `scripts/preparar_servidor.py`;
- a própria aplicação cria as tabelas no primeiro uso.

Os dados ficam nos volumes `dados_do_banco` (PostgreSQL) e `arquivos_da_aplicacao` (índices, modelo, arquivos), que
sobrevivem a `docker compose down`. Para começar do zero: `docker compose down -v` (**apaga os dados**). Para ver o
banco no DBeaver: host `localhost`, porta **5433**, banco `integra_folha`, usuário `integra_folha_app`.

Cuidados (aprendidos na primeira subida real, 2026-09-25):
- O contêiner recebe o `MODE` e as chaves de API do `.env`. Com `MODE=llm` e chaves preenchidas, a aplicação no Docker
  usa a **IA real** (com custo). Para subir sem custo, sobrescreva com um segundo arquivo do Compose, por exemplo
  `docker compose -f docker-compose.yml -f sem_chaves.yml up`, em que `sem_chaves.yml` define, no serviço
  `aplicacao`, `MODE: mock`, `OPENAI_API_KEY: ""`, `ANTHROPIC_API_KEY: ""` e `AWS_BEARER_TOKEN_BEDROCK: ""`. No PowerShell 5.1, `$env:OPENAI_API_KEY = ''`
  **não** funciona: variável vazia é apagada, e o Compose volta a ler o `.env`.
- `docker compose config` mostra a configuração final **com as senhas e chaves à vista**: não use em tela
  compartilhada nem copie a saída.
- A aplicação roda com o usuário `integra`, **sem poderes de administrador** (ADR-110). Um volume
  `arquivos_da_aplicacao` criado antes dessa mudança pertence ao administrador, e a aplicação não consegue escrever
  nele ("Permission denied" na subida). Corrija uma vez o dono (`docker compose run --rm --user root aplicacao chown
  -R integra:integra /app/storage`) ou recrie o volume com `docker compose down -v` (**apaga os dados**; índices e
  modelo são refeitos na subida).

### Só a aplicação (SQLite, sem servidor de banco)

```powershell
docker build -t integra_folha .
docker run -p 8000:8000 --env-file .env -e BANCO=sqlite integra_folha
```

Numa hospedagem com PostgreSQL gerenciado (ex.: Railway), é este mesmo contêiner, com `BANCO=postgres` e
`POSTGRES_URL` (o endereço que a hospedagem fornece) nos segredos.

### O que acontece na subida

Na subida, o container roda `scripts/preparar_servidor.py` antes de ligar a API. Ele gera só o que falta:
- os dados sintéticos;
- os índices do RAG (baixa o modelo na primeira vez, precisa de internet);
- os dois usuários da demo, **só** se `SENHA_USUARIO_EMPRESA` e `SENHA_USUARIO_BANCO` estiverem nos segredos da
  hospedagem (e apaga os usuários de perfis que não existem mais, como o antigo CIENTISTA).

Sem as senhas, ele avisa e segue: no servidor ninguém digita nada (ADR-64).

## Estrutura

```
api/                    A API FastAPI: login e sessão, o porteiro das páginas e as rotas /api de cada portal
front/                  As páginas (HTML), a aparência (css/) e os scripts (js/) do Portal Empresa e do Portal Interno
services/               Lógica: configuração, LLM, login, permissões e porta de acesso, parâmetros, catálogo, ingestão,
                        padronização, validação, correção, homologação, guardrail, execuções, planejamento, painel
agents/                 Agentes de IA: Interpretador, Assistente de Correção, Endomarketing
prompts/                Prompts versionados de cada agente e do guardrail
rag/                    Embeddings locais, cortes dos trechos e busca (com filtro por empresa)
baselines/              Baseline B0 (sem IA)
eval/                   Métricas (acurácia geral e por campo, abstenção, IC 95%), congelamento da prova e avaliações
                        do fluxo e do Endomarketing
models/                 Contratos (tipos de campo, estados, perfis, layout)
workflows/              Fluxo da empresa em LangGraph (pausas, retomada, limites) e o grafo do spike
scripts/                Preparação e medição (vocabulário, usuários, dados, cabeçalhos, B0, índices, congelamento,
                        RAG, fluxo, Endomarketing, guardrail)
data/contratos/         Layout v1 (os ~45 campos do parâmetro) e regras de validação
data/parametros/        Premissas financeiras v1 e catálogo de benefícios das 6 empresas
data/synthetic/         Dados sintéticos gerados (envios fora do Git)
data/golden/            Gabarito de cada arquivo de envio
data/avaliacao/         Prova e treino, consultas do RAG, casos do Endomarketing e do guardrail,
                        congelamento e resultados
data/mock/              Cadastro das 6 empresas da demo (empresas.json)
data/vocabulario/       Sinônimos de colunas, divididos em treino e teste
tests/                  Testes automatizados
docs/                   Documentação exigida pelo enunciado
```
