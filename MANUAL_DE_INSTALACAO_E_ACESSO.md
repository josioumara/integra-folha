# Integra Folha: manual de instalação e acesso

Este manual explica como **acessar** o Integra Folha no site publicado e como **montar o ambiente** em outra máquina,
do zero até a tela de login: no seu computador (local) ou numa conta da AWS (a mesma arquitetura do site). Cada passo
diz o comando, o que ele faz e o que você deve ver.

> **Dados 100% sintéticos.** Nenhuma empresa, pessoa, CPF ou conta é real. Nenhuma senha aparece neste manual: as
> senhas do site são entregues à banca em separado, e as da sua instalação você mesmo escolhe.

## Sumário

1. [Os três caminhos](#1-os-três-caminhos)
2. [Caminho A: acessar o site publicado](#2-caminho-a-acessar-o-site-publicado)
3. [Caminho B: rodar na sua máquina](#3-caminho-b-rodar-na-sua-máquina)
4. [Caminho C: publicar na sua conta da AWS](#4-caminho-c-publicar-na-sua-conta-da-aws)
5. [Solução de problemas](#5-solução-de-problemas)
6. [Onde está cada coisa](#6-onde-está-cada-coisa)

---

## 1. Os três caminhos

| Caminho | Para quem | O que precisa | Tempo | Custo |
|---|---|---|---|---|
| **A. Acessar o site** | Quem quer usar a ferramenta sem instalar nada | Um navegador e o usuário e a senha recebidos | 1 min | Nenhum |
| **B. Rodar na sua máquina** | Quem quer reproduzir e inspecionar o projeto | Python 3.12 e Git (o Docker é opcional) | 15 a 30 min | Nenhum no modo simulado (`MODE=mock`) |
| **C. Publicar na AWS** | Quem quer a mesma hospedagem do site, na própria conta | Conta da AWS, AWS CLI, Git Bash e um domínio | 1 a 2 h | ≈ US$ 21 por mês, mais a IA por uso |

**Os dois modos da IA.** A aplicação roda em dois modos, escolhidos pela variável `MODE`:

- **`mock` (simulado):** nenhuma chamada sai para um provedor de IA; os agentes devolvem respostas simuladas. Não
  precisa de chave e não tem custo. É o padrão da instalação local e o modo em que a bateria de testes roda.
- **`llm` (IA real):** os agentes chamam os modelos pelo **Amazon Bedrock** (perfil EUA, retenção zero): Claude Sonnet
  4.6 como modelo grande e Amazon Nova 2 Lite como modelo pequeno. Precisa de uma chave do Bedrock e tem custo por uso,
  com teto de gasto por operação, por dia e por mês.

---

## 2. Caminho A: acessar o site publicado

**Endereço:** https://integrafolha.com.br (o `www.integrafolha.com.br` leva para o mesmo lugar). O site só abre em
https, com certificado válido, e fica fora dos buscadores.

### 2.1 Quem entra e o que vê

A ferramenta tem dois portais. O login decide para qual deles você vai.

| Perfil | Login | O portal | Para que usar |
|---|---|---|---|
| **Empresa** (o RH da empresa cliente) | `empresa.aurora` | **Portal Empresa**: Início (com o botão "Cadastrar funcionários"), Acompanhar cadastros, Benefícios do seu time e Materiais de endomarketing | Testar o cadastro do zero: a Aurora não tem histórico |
| **Empresa, com histórico** | `rh.jacamim`, `rh.maremansa`, `rh.buritialto`, `rh.carnaubafina`, `rh.jucaranorte`, `rh.dunaclara`, `rh.mangabadoce`, `rh.pequizeiro`, `rh.tuiuiu`, `rh.lobeira`, `rh.carandaalto`, `rh.enseadaserena`, `rh.cantaria`, `rh.sabiadocampo`, `rh.garoa`, `rh.coxilhaforte` e `rh.imbuiaserena` | **Portal Empresa** | Ver a plataforma "em uso": as 17 empresas da base viva, com cerca de 3 meses de envios, correções, contas abertas e conversas com o banco |
| **Especialista do banco** | `especialista.banco` | **Portal Interno**: Início, Empresas (a ficha de cada uma: visão geral, contas abertas, dados, usuários, catálogo de benefícios e a conversa com o RH), Envios, Endomarketing, Indicadores e o menu Sistema (Parâmetros do layout, Acompanhamento dos agentes e Teto de custo com agentes) | Avaliar os envios, informar as contas abertas, gerar e publicar materiais e acompanhar os agentes |

- **As senhas são entregues à banca em separado.** Nenhuma delas está no código, no Git ou neste manual.
- **A sessão dura 8 horas** e termina ao fechar o navegador. O botão "Sair" encerra a sessão na hora.
- **Cinco senhas erradas bloqueiam o login por 15 minutos.** A resposta é a mesma para um usuário que existe e para um
  que não existe.
- **Uma página de outro perfil volta para a sua página inicial.** Sem login, qualquer página volta para o login.

### 2.2 Um roteiro de 10 minutos para ver a ferramenta funcionando

**Os arquivos para enviar** estão no repositório, na pasta
[`data/avaliacao/prova_por_tipo/`](data/avaliacao/prova_por_tipo/). São 35 arquivos sintéticos, em 7 tipos, do mais
fácil ao mais difícil:

| Tipo | Exemplo | O que mostra |
|---|---|---|
| T1 · Planilha no padrão do banco | `T1_padrao_do_banco_1.xlsx` | O caminho feliz |
| T2 · Colunas fora de ordem, a mais e faltando | `T2_colunas_fora_de_ordem_1.xlsx` | A leitura não depende da ordem |
| T3 · Nomes de coluna parecidos | `T3_nomes_proximos_1.xlsx` | O Agente Interpretador ligando cada coluna ao campo certo |
| T4 · Cabeçalho difícil | `T4_cabecalho_dificil_1.xlsx` | Coluna sem nome e coluna com duas informações |
| T5 · Word com tabela ou fichas | `T5_tabela_ou_fichas_1.docx` | Documento que não é planilha |
| T6 · Word com texto corrido | `T6_texto_corrido_1.docx` | O Agente Leitor transformando frases em cadastro |
| T7 · Word com texto misturado e armadilhas | `T7_texto_misturado_1.docx` | O Agente Conferidor desconfiando da leitura |

**Como empresa** (`empresa.aurora`):
1. No **Início**, clique em **Cadastrar funcionários** e envie um dos arquivos acima.
2. Confira as colunas: cada coluna mostra o campo proposto e quem propôs (a regra, o reuso ou o agente). Aceite ou
   troque.
3. Confira as **4 informações obrigatórias** de cada pessoa: CPF, código da profissão (CBO), renda bruta mensal e
   data de admissão. Os outros campos são opcionais e entram sem pergunta.
4. Em **Acompanhar cadastros**, resolva as pendências conversando com o **Agente de validação**. Ele confere o valor na
   hora; a mudança aparece com o botão "Desfazer".
5. Envie ao banco.

**Como especialista do banco** (`especialista.banco`):
1. Em **Envios**, abra o envio da Aurora. Aponte um problema numa pessoa ou aprove as outras.
2. Em **Empresas**, abra a ficha da empresa: a conversa com o RH, os usuários e as **contas abertas**. O arquivo de
   contas abertas tem uma linha por pessoa, no formato `cpf;status;agencia;conta;data_abertura`.
3. Em **Endomarketing**, escolha a empresa, o tipo de material, o canal e os benefícios, gere o rascunho com o
   **Agente de Endomarketing**, confira e publique. A empresa passa a ver o material em "Materiais de endomarketing".
4. Em **Sistema > Acompanhamento dos agentes**, veja o que cada agente propôs e o quanto as pessoas aprovaram.

> **Qual modo de IA está no site?** O servidor escolhe o modo pela variável `MODE` (seção 4.9). Com `mock`, as
> respostas dos agentes são simuladas; com `llm`, são da IA real pelo Bedrock, com os tetos de gasto ligados.

---

## 3. Caminho B: rodar na sua máquina

A instalação local mais simples usa o **SQLite** (um arquivo, sem servidor de banco) e a IA em **modo simulado**. É o
jeito mais rápido de reproduzir o projeto, sem custo. O PostgreSQL e o Docker ficam como variantes (seções 3.9 e
3.10).

### 3.1 Pré-requisitos

| O quê | Versão | Como conferir |
|---|---|---|
| Sistema | Windows 10 ou 11, macOS ou Linux | — |
| Python | **3.12** | `python --version` (no Windows, também `py -3.12 --version`) |
| Git | qualquer versão recente | `git --version` |
| Espaço em disco | cerca de 1 GB (bibliotecas ~0,5 GB; modelo de embeddings, índices e dados ~0,3 GB) | — |
| Internet | na instalação e na **primeira** montagem do RAG, que baixa o modelo de embeddings (~220 MB) | — |
| Docker Desktop | opcional (só na seção 3.10) | `docker --version` |

> **No Windows, use uma pasta curta** (ex.: `C:\projetos\integra-folha`). O modelo de embeddings tem caminhos
> longos, e uma pasta funda passa do limite de 260 caracteres do Windows (seção 5).

### 3.2 Baixar o código

```bash
git clone https://github.com/josioumara/integra-folha.git
cd integra-folha
```

### 3.3 Criar o ambiente e instalar as bibliotecas

O ambiente virtual (`.venv`) é uma pasta com um Python só do projeto: as bibliotecas dele não se misturam com as do
computador.

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS ou Linux (terminal):**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

> Não é preciso "ativar" o ambiente: todos os comandos deste manual chamam o Python dele direto. No Windows, é
> `.\.venv\Scripts\python.exe`; no macOS e no Linux, `.venv/bin/python`. Daqui em diante, os comandos aparecem no
> formato do Windows. No macOS e no Linux, troque `.\.venv\Scripts\python.exe` por `.venv/bin/python` e `\` por `/`.

### 3.4 Configurar o `.env`

O `.env` guarda a configuração e os segredos da sua instalação. Ele nunca vai para o Git; o modelo versionado é o
`.env.example`.

```powershell
copy .env.example .env        # macOS ou Linux: cp .env.example .env
```

Os valores padrão já servem para a instalação local:

| Variável | Valor padrão | O que faz |
|---|---|---|
| `MODE` | `mock` | IA simulada, sem chave e sem custo. `llm` liga a IA real (seção 3.8) |
| `BANCO` | `sqlite` | O banco é o arquivo `storage/integra_folha.db`. `postgres` usa um servidor PostgreSQL (seção 3.9) |
| `ROTA_DA_IA` | `bedrock` | Por onde a IA real passa: o Amazon Bedrock |
| `MODELO_GRANDE`, `MODELO_PEQUENO` | `claude-sonnet-4-6`, `nova-2-lite` | Os modelos dos agentes no modo `llm` |
| `TETO_DE_GASTO_USD`, `LIMITE_CHAMADAS_LLM_POR_SESSAO` | `10.00`, `50` | Teto de gasto e de chamadas por operação: ao atingir, a IA pausa |
| `LIMITE_UPLOAD_MB` | `5` | Tamanho máximo do arquivo enviado |

**Duas senhas que você escolhe, se for usar** (as linhas já estão no modelo, em branco, marcadas com `[SEGREDO]`):

| Variável | Para que serve |
|---|---|
| `SENHA_DA_BASE_VIVA` | A senha única dos 17 logins `rh.*` da base viva (passo 5 da seção 3.5) |
| `SENHA_DOS_TESTES` | A senha dos usuários de teste dos roteiros de clique (seção 3.11) |

### 3.5 Preparar os dados, os usuários e o RAG

Rode na ordem, da pasta `integra-folha`. Cada comando pode rodar de novo sem estragar nada.

| # | Comando | O que faz | O que você vê |
|---|---|---|---|
| 1 | `.\.venv\Scripts\python.exe scripts\gerar_dados.py` | Gera o "mundo de mentira": 6 empresas, os funcionários com o gabarito e os arquivos de envio em `data/synthetic/envios/` (sempre iguais, pela semente fixa) | A lista dos arquivos gerados |
| 2 | `.\.venv\Scripts\python.exe scripts\criar_usuarios.py` | Cria os dois usuários da demo, `empresa.aurora` (Empresa, EMP001) e `especialista.banco` (Banco). **Pergunta a senha de cada um**, sem mostrar o que é digitado; o banco guarda só o hash | "Usuário ... criado" |
| 3 | `.\.venv\Scripts\python.exe scripts\aplicar_parametro_adr_143.py` | Grava a versão do parâmetro do layout com as **4 informações obrigatórias** (CPF, CBO, renda bruta e admissão), a mesma do site | A versão nova do parâmetro |
| 4 | `.\.venv\Scripts\python.exe scripts\build_index.py` | Monta os índices do RAG (o parâmetro, as regras, o catálogo de benefícios e os mapeamentos aprovados). Na primeira vez, baixa o modelo de embeddings (~220 MB) para `storage/modelos` | A contagem de trechos de cada índice |
| 5 | *(opcional)* `.\.venv\Scripts\python.exe scripts\carregar_base_viva.py` | Carrega a **base viva**: 17 empresas com cerca de 3 meses de uso, sem chamar a IA. Precisa do `SENHA_DA_BASE_VIVA` no `.env`. Com `--tambem-logins-da-demo`, os dois logins da demo passam a usar a mesma senha | "Carregadas: 17 empresas" |
| 6 | *(opcional, depois do 5)* `.\.venv\Scripts\python.exe scripts\indexar_kbs_endomarketing.py` | Põe no RAG as bases de conhecimento (KBs) de endomarketing que a carga publicou | A contagem das KBs indexadas |

> **Por que o passo 3 existe:** o arquivo `data/contratos/layout_v1.csv` é o parâmetro de partida das bases novas e
> dos testes. O script grava por cima dele a versão em uso, pelo mesmo caminho da tela Parâmetros, e a mudança
> aparece no registro das alterações.

> **Sem os índices do RAG, nada quebra:** o Interpretador trabalha sem a busca, e o Endomarketing avisa que o catálogo
> ainda não está pronto. Os índices só melhoram as respostas.

> **Este passo a passo foi testado do zero** (30/09/2026, Windows 11, numa pasta nova, com o SQLite e o modo
> simulado). Os tempos medidos: as bibliotecas em ~3 min (depende da internet); os passos 1 a 3 em segundos; o RAG em
> ~40 s, com o download do modelo; a base viva em ~4 min; as KBs em ~45 s. Depois, o servidor subiu em ~5 s, os três
> tipos de login entraram (`empresa.aurora`, `especialista.banco` e `rh.jacamim`), e uma planilha e um Word em texto
> corrido chegaram ao aceite das colunas.

### 3.6 Ligar a aplicação

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.principal:aplicacao --port 8000
```

A API entrega as telas e as rotas `/api`. Deixe esse terminal aberto: fechar a janela desliga o servidor.

### 3.7 Entrar

Abra **http://localhost:8000/login.html** no navegador e entre com um dos usuários criados no passo 2 (ou com um login
`rh.*` da base viva). O perfil Empresa vai para o Portal Empresa; o perfil Banco, para o Portal Interno. O roteiro de
10 minutos da seção 2.2 vale igual aqui, com os arquivos de `data/avaliacao/prova_por_tipo/` ou os de
`data/synthetic/envios/`.

> Aberta com dois cliques, sem o servidor, a página de login não funciona: ela precisa da API.

### 3.8 Ligar a IA real (opcional, com custo)

A IA real passa pelo **Amazon Bedrock**, na sua conta da AWS: o fornecedor do modelo não vê os pedidos, e a retenção
zero fica gravada na conta.

1. **No console da AWS, região Norte da Virgínia (`us-east-1`):** confira em Amazon Bedrock > Acesso aos modelos que a
   conta usa o **Claude Sonnet 4.6** e o **Amazon Nova 2 Lite**.
2. **Crie uma chave de API do Bedrock** (Amazon Bedrock > Chaves de API > chave de longo prazo). Quem tem a chave gasta
   na sua conta: guarde-a só no `.env` e apague-a no console se vazar.
3. **No `.env`:** `MODE=llm`, `ROTA_DA_IA=bedrock`, `REGIAO_BEDROCK=us-east-1` e a chave em
   `AWS_BEARER_TOKEN_BEDROCK`.
4. **Grave a retenção zero e prove os dois modelos** (custa centavos):
   `.\.venv\Scripts\python.exe scripts\preparar_bedrock.py`. Ele liga a retenção zero na conta, lê de volta e faz uma
   pergunta mínima a cada modelo, mostrando o tempo e o custo.
5. **O detector de ataques do Bedrock Guardrails** (a segunda camada do guardrail de injeção) precisa da permissão
   `bedrock:InvokeGuardrailChecks` no usuário da chave. O script `publicacao/dar_permissao_do_detector.sh
   <usuario-da-chave>` confere, pergunta e grava; rode no AWS CloudShell, com a conta principal.
6. **Os tetos de gasto:** por operação no `.env` (`TETO_DE_GASTO_USD`); por dia e por mês na tela **Sistema > Teto de
   custo com agentes**, do especialista do banco. Ao atingir um teto, a IA pausa o trabalho e nunca devolve resposta
   simulada no lugar da real.

### 3.9 Variante: PostgreSQL na sua máquina

O PostgreSQL é o banco de uso e de produção. Com o PostgreSQL 18 instalado:

1. No `.env`, ponha a conexão do superusuário, usada só na preparação:
   `POSTGRES_ADMIN_URL=postgresql://postgres:<senha>@localhost:5432/postgres`.
2. Crie o usuário da aplicação (sem superpoderes) e os bancos de uso e de testes. O script grava `POSTGRES_URL` e
   `POSTGRES_URL_TESTES` no `.env`:
   `.\.venv\Scripts\python.exe scripts\preparar_postgres.py`.
3. *(Opcional)* Copie para o PostgreSQL o que já existe no SQLite (nunca sobrescreve um banco com dados):
   `.\.venv\Scripts\python.exe scripts\migrar_sqlite_para_postgres.py`.
4. No `.env`, `BANCO=postgres`. Depois, refaça os passos 2 a 6 da seção 3.5 (eles gravam no banco novo).

Para ver as tabelas, conecte o DBeaver ao banco `integra_folha` (passo a passo em `docs/banco_de_dados.md`, seção 9).

### 3.10 Variante: Docker Compose (aplicação e PostgreSQL num comando)

Não precisa instalar o Python nem o PostgreSQL: o `docker-compose.yml` sobe dois contêineres, o banco (PostgreSQL 18)
e a aplicação.

1. No `.env`, preencha, **só com letras e números**, `SENHA_POSTGRES_ADMIN` e `SENHA_POSTGRES_APLICACAO`, e as senhas
   dos dois usuários da demo, `SENHA_USUARIO_EMPRESA` e `SENHA_USUARIO_BANCO`.
2. Suba: `docker compose up --build`.
3. Abra **http://localhost:8000/login.html**.

Na primeira subida, o banco cria o usuário da aplicação, e a aplicação roda `scripts/preparar_servidor.py`, que gera
os dados sintéticos, monta os índices do RAG (baixa o modelo) e cria os dois usuários da demo com as senhas do `.env`.
Depois, grave o parâmetro dos 4 obrigatórios e refaça o RAG **com a aplicação parada** (o índice não aceita dois
processos ao mesmo tempo):

```bash
docker compose stop aplicacao
docker compose run --rm -T aplicacao python scripts/aplicar_parametro_adr_143.py
docker compose run --rm -T aplicacao python scripts/build_index.py
docker compose up -d
```

- Os dados ficam nos volumes `dados_do_banco` e `arquivos_da_aplicacao`, que sobrevivem ao `docker compose down`. Para
  começar do zero: `docker compose down -v` (**apaga os dados**).
- O banco do contêiner atende na porta **5433** da sua máquina, só em `127.0.0.1` (para o DBeaver).
- **Cuidado:** o contêiner recebe o `MODE` e a chave do `.env`. Com `MODE=llm` e a chave preenchida, a aplicação no
  Docker usa a IA real, com custo.
- `docker compose config` mostra a configuração **com as senhas à vista**: use `docker compose config --quiet`.

### 3.11 Rodar os testes

```powershell
$env:MODE="mock"; .\.venv\Scripts\python.exe -m pytest
```

A bateria roda no modo simulado, num banco temporário: o banco da aplicação não é tocado, e nada é cobrado. Os
roteiros de clique (a tela no Chrome, ponta a ponta) ficam em `tests/e2e/`, usam a senha `SENHA_DOS_TESTES` do `.env`
e têm o próprio `README.md`.

---

## 4. Caminho C: publicar na sua conta da AWS

Este caminho monta a mesma hospedagem do site: uma máquina EC2 na Virgínia com três contêineres (o Caddy, a aplicação
e o PostgreSQL), criada por **infraestrutura como código** (CloudFormation). O desenho, o porquê de cada peça e o custo
estão em [`docs/hospedagem.md`](docs/hospedagem.md).

```
Internet ──https──> Caddy (80/443, certificado automático)  ← a única porta aberta para fora
                      └──> Aplicação (FastAPI, 8000, só rede interna) ──> PostgreSQL 18 (sem porta para fora)
                                   └──> Amazon Bedrock (us-east-1, retenção zero)
Backup de toda noite ──> bucket S3 privado (a máquina grava e não consegue apagar)
```

### 4.1 O que será criado e quanto custa

| Recurso | Para quê | Custo por mês |
|---|---|---|
| EC2 `t3.small` (2 GB, Ubuntu 24.04, disco gp3 de 30 GB criptografado) | O computador do site, ligado o tempo todo | US$ 15,18 + US$ 2,40 |
| IP fixo (Elastic IP) | O endereço para o qual o domínio aponta | US$ 3,65 |
| Bucket S3 privado | O backup de toda noite, guardado por 30 dias | centavos |
| Papel IAM da máquina | Grava o backup sem guardar chave nenhuma; não consegue apagar | — |
| Alarme de orçamento (AWS Budgets) | E-mail em 80% e 100% do valor do mês (padrão: US$ 60) | — |
| **Total** | | **≈ US$ 21**, mais a IA por uso |

### 4.2 Pré-requisitos

- Uma conta da AWS e o **AWS CLI v2** configurado (`aws --version`).
- O **Git Bash** (no Windows) ou um terminal (macOS e Linux).
- Um **domínio** cujo DNS você possa editar. Sem domínio próprio, troque `integrafolha.com.br` no
  `publicacao/Caddyfile`, no `publicacao/publicar.sh` e no `publicacao/conferir.sh`.
- Uma **chave SSH** só para o servidor:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/integra-folha-ec2
```

### 4.3 Passo 1: o usuário que publica (uma vez, com a conta principal)

Cria o usuário `integra-publicador`, que só pode o que a publicação usa, e o limite de permissões dos papéis que ele
cria (`integra-limite-dos-papeis`). Assim, a conta principal não é usada no dia a dia.

```bash
aws cloudformation deploy --template-file publicacao/usuario-publicador.yaml --stack-name conta-usuario-publicador \
    --capabilities CAPABILITY_NAMED_IAM --region us-east-1
```

Depois, no console, defina a senha e o MFA do `integra-publicador` e configure um perfil do AWS CLI com ele.

### 4.4 Passo 2: a infraestrutura (a pilha do CloudFormation)

```bash
MEU_IP="$(curl -s https://checkip.amazonaws.com)/32"
aws cloudformation deploy --stack-name integra-folha-producao --template-file publicacao/infraestrutura.yaml \
    --parameter-overrides IpDaUsuaria="$MEU_IP" ChavePublicaSsh="$(cat ~/.ssh/integra-folha-ec2.pub)" \
                          EmailDoOrcamento=<seu-email> \
    --capabilities CAPABILITY_NAMED_IAM --region us-east-1
aws cloudformation describe-stacks --stack-name integra-folha-producao --query "Stacks[0].Outputs" --region us-east-1
```

A saída mostra o **IP fixo**, a máquina, o bucket do backup e o comando do primeiro SSH. A porta 22 fica aberta só
para o seu IP; as portas 80 e 443, para todos.

### 4.5 Passo 3: o DNS

No painel do seu domínio, crie dois registros **A** apontando para o IP fixo: a raiz (`@`) e o `www`. Espere o
`nslookup <seu-dominio>` devolver o IP antes de subir o site: o Caddy só consegue o certificado com o DNS certo.

### 4.6 Passo 4: preparar e proteger o servidor (uma vez)

```bash
scp -i ~/.ssh/integra-folha-ec2 publicacao/blindar_servidor.sh ubuntu@<ip>:/tmp/
ssh -i ~/.ssh/integra-folha-ec2 ubuntu@<ip> "sudo bash /tmp/blindar_servidor.sh"
```

O script põe o fuso de Brasília e as atualizações de segurança automáticas, cria o swap de 2 GB e o usuário `deploy`,
fecha o SSH por senha e para o root, liga o firewall do Ubuntu (22, 80 e 443) e o fail2ban, instala o Docker e o AWS
CLI e cria a pasta `/srv/integra-folha`, que recebe o código pelo `git push`.

Crie o atalho do SSH em `~/.ssh/config` e **teste num terminal novo**, antes de fechar o que está aberto:

```
Host integra-folha
    HostName <ip>
    User deploy
    IdentityFile ~/.ssh/integra-folha-ec2
```

```bash
ssh integra-folha "echo conectado"
git remote add prod integra-folha:/srv/integra-folha
```

### 4.7 Passo 5: o `.env` de produção (só no servidor)

O `.env` de produção mora só no servidor e nasce do modelo `publicacao/.env.exemplo`. O `.env` do seu computador
nunca vai para lá.

```bash
ssh integra-folha
mkdir -p /srv/integra-folha/publicacao && cd /srv/integra-folha
nano publicacao/.env          # cole o conteúdo de publicacao/.env.exemplo e preencha
chmod 600 publicacao/.env
```

- `SENHA_POSTGRES_ADMIN` e `SENHA_POSTGRES_APLICACAO`: gere no próprio servidor, só com letras e números
  (`openssl rand -hex 24`).
- `EMAIL_DO_CERTIFICADO`: o e-mail que o Let's Encrypt usa para avisar de problema no certificado.
- `MODE=mock` para começar; a IA real entra no passo 9.

### 4.8 Passo 6: publicar

Do seu computador, na pasta do repositório, pelo Git Bash:

```bash
bash publicacao/publicar.sh <commit>          # ex.: bash publicacao/publicar.sh main
```

O script manda o código pelo `git push`, **constrói a imagem no servidor a partir do commit** (`git archive`), faz o
backup, troca a versão e roda as provas do `publicacao/conferir.sh`:

- o endereço abre em https, com certificado válido, e o http leva ao https;
- uma página sem login volta ao login, e a API sem login responde 401;
- o `robots.txt` fecha tudo, e as respostas trazem `X-Robots-Tag: noindex`;
- de fora, as portas 8000 (aplicação) e 5432 (banco) estão fechadas;
- a IA é chamada pela Virgínia, onde a retenção zero está gravada;
- a versão no ar é a do commit pedido (o rodapé das telas mostra a data dela).

Se uma prova falhar, o script **volta sozinho à versão anterior** e avisa.

### 4.9 Passo 7: os dados e as senhas do site

No servidor, na pasta `/srv/integra-folha`, com o comando do compose de produção:

```bash
COMPOSE="docker compose --env-file publicacao/.env -f docker-compose.yml -f publicacao/compose.prod.yml"
```

1. **As senhas dos logins:** `bash publicacao/definir_senhas_da_demo.sh` pergunta as senhas dos dois usuários da demo
   (`SENHA_USUARIO_EMPRESA` e `SENHA_USUARIO_BANCO`); `bash publicacao/gravar_senha_do_site.sh` pergunta a senha única
   da base viva (`SENHA_DA_BASE_VIVA`, com pelo menos 12 caracteres). As duas perguntas escondem o que é digitado, e a
   senha vai direto para o `.env` do servidor. Depois, `$COMPOSE up -d`: na subida, o `preparar_servidor.py` cria os
   dois usuários da demo.
   > **A cada subida, o `preparar_servidor.py` recria os dois usuários da demo com as senhas `SENHA_USUARIO_*`.** Para
   > usar uma senha só em todos os logins, digite o mesmo valor nos dois scripts. A opção `--tambem-logins-da-demo`
   > da carga da base viva também põe a senha dela nos dois logins da demo, mas só até a próxima subida.
2. **O parâmetro dos 4 obrigatórios e a base viva,** com a aplicação parada (o índice do RAG não aceita dois
   processos ao mesmo tempo). O compose só passa ao contêiner as variáveis que ele lista, então a senha da base viva
   vai por uma variável exportada, sem aparecer na linha de comando. As linhas da base viva são opcionais:
   ```bash
   $COMPOSE stop aplicacao
   $COMPOSE run --rm -T aplicacao python scripts/aplicar_parametro_adr_143.py < /dev/null
   export SENHA_DA_BASE_VIVA="$(grep ^SENHA_DA_BASE_VIVA= publicacao/.env | cut -d= -f2-)"
   $COMPOSE run --rm -T -e SENHA_DA_BASE_VIVA aplicacao python scripts/carregar_base_viva.py < /dev/null
   unset SENHA_DA_BASE_VIVA
   $COMPOSE run --rm -T aplicacao python scripts/build_index.py < /dev/null
   $COMPOSE run --rm -T aplicacao python scripts/indexar_kbs_endomarketing.py < /dev/null
   $COMPOSE up -d
   ```

### 4.10 Passo 8: o backup de toda noite

```bash
bash publicacao/fazer_backup.sh --agendar      # agenda o backup das 3h (horário de Brasília)
bash publicacao/fazer_backup.sh                # um backup agora
```

O backup leva o banco inteiro (`pg_dump`) e o volume `storage` para o bucket privado. A máquina grava pelo papel dela
e não consegue apagar: um invasor na máquina não apagaria o backup.

### 4.11 Passo 9: ligar a IA real no site (opcional, com custo)

1. Crie uma chave do Bedrock **só de produção** e ponha no `publicacao/.env` do servidor, pelo `nano`
   (`AWS_BEARER_TOKEN_BEDROCK`), com `MODE=llm`, `REGIAO_BEDROCK=us-east-1` e o `TETO_DE_GASTO_USD`.
2. Grave a retenção zero na conta: `aws bedrock put-account-data-retention --mode none --region us-east-1` (no
   CloudShell, com a conta principal), ou rode o `scripts/preparar_bedrock.py` (seção 3.8).
3. Dê à chave a permissão do detector de ataques: `publicacao/dar_permissao_do_detector.sh <usuario-da-chave>`, no
   CloudShell.
4. Suba de novo a aplicação: `$COMPOSE up -d`. Os tetos por dia e por mês ficam na tela **Sistema > Teto de custo com
   agentes**.

### 4.12 Atualizar, voltar e apagar

- **Versão nova:** `bash publicacao/publicar.sh <commit>`. O servidor guarda as 3 últimas imagens.
- **Voltar à versão anterior:** `ssh integra-folha "bash /srv/integra-folha/publicacao/trocar_versao.sh --anterior"`.
- **Apagar tudo:** `aws cloudformation delete-stack --stack-name integra-folha-producao --region us-east-1`. O bucket
  do backup **não** é apagado junto, de propósito.

---

## 5. Solução de problemas

| O que aparece | O que fazer |
|---|---|
| Ao abrir uma página, volta para o login ou para a sua página inicial | Entre com um usuário do perfil da página (seção 2.1). Sem usuários, rode `scripts\criar_usuarios.py` |
| "Senha incorreta" várias vezes e o login não aceita nem a certa | Cinco erros bloqueiam o login por 15 minutos. Espere e tente de novo |
| "Monte os índices antes: python scripts/build_index.py" | Rode o passo 4 da seção 3.5, com o servidor parado |
| `build_index` falha com "Could not load model ... from any source" e, antes, "No such file or directory" | A pasta do projeto está funda demais para o limite de 260 caracteres do Windows. Use uma pasta curta ou ative os caminhos longos do Windows |
| "Gere os arquivos de envio antes: python scripts/gerar_dados.py" | Rode o passo 1 da seção 3.5 (os arquivos de envio não vão para o Git) |
| A carga da base viva para com "SENHA_DA_BASE_VIVA" | Preencha a variável no `.env` (seção 3.4) |
| A carga da base viva para com "nenhum login ativo do perfil BANCO" | Rode antes o `scripts\criar_usuarios.py` |
| "Falta a chave" ou "Falta escolher o modelo" | O `.env` está com `MODE=llm` sem a chave do Bedrock ou sem os modelos. Preencha (seção 3.8) ou volte para `MODE=mock` |
| O envio fica em "Tentar de novo" | A IA real não respondeu ou um teto de gasto foi atingido: o trabalho pausa e nunca vira resposta simulada. Veja a faixa de aviso no alto da tela e o **Sistema > Teto de custo com agentes** |
| "A planilha tem fórmulas" | No Excel, copie tudo e cole como **valores**, salve e envie de novo |
| "O conteúdo não é um CSV" ou "não é uma planilha Excel válida" | A extensão do arquivo não bate com o conteúdo. Salve de novo como `.xlsx` ou `.csv` |
| A porta 8000 está ocupada | Troque a porta: `... uvicorn api.principal:aplicacao --port 8001` e abra `http://localhost:8001/login.html` |
| "BANCO=postgres, mas falta POSTGRES_URL no .env" | Rode `scripts\preparar_postgres.py` (seção 3.9) ou volte para `BANCO=sqlite` |
| `connection refused` na porta 5432 | O serviço do PostgreSQL está parado. No Windows, como administrador: `Start-Service postgresql-x64-18` |
| O ChromaDB reclama de outro processo usando o índice | Pare o servidor (`Ctrl+C`) antes de rodar os scripts que mexem no RAG |
| O PowerShell não deixa ativar o ambiente virtual | Não precisa ativar: chame sempre `.\.venv\Scripts\python.exe` |

---

## 6. Onde está cada coisa

| Pasta ou arquivo | O que tem |
|---|---|
| `MANUAL_DE_INSTALACAO_E_ACESSO.md` | Este manual |
| `apresentacao/` | A apresentação da banca (`CASE_DATAMASTER_T705951_JOSIMARASILVA.pptx`), com os anexos de consulta |
| `api/` | A API FastAPI: login e sessão, o porteiro das páginas e as rotas de cada portal |
| `front/` | As telas (HTML, CSS e JavaScript) do Portal Empresa e do Portal Interno |
| `services/` | A lógica: leitura dos arquivos, padronização, validação, pendências, homologação, contas, endomarketing, guardrail, tetos de gasto |
| `agents/` e `prompts/` | Os agentes de IA e os prompts versionados de cada um |
| `rag/` | Os embeddings locais, os cortes dos trechos e a busca, sempre filtrada pela empresa |
| `workflows/` | O fluxo da empresa em LangGraph, com pausa e retomada |
| `scripts/` | Preparação (dados, usuários, parâmetro, índices, base viva) e medição (experimentos) |
| `data/` | Contratos do layout, catálogos, dados sintéticos, a base viva e os conjuntos de avaliação |
| `eval/` | As métricas e a avaliação |
| `tests/` | A bateria automatizada e os roteiros de clique |
| `publicacao/` | A hospedagem na AWS: CloudFormation, compose de produção, Caddy e os scripts de publicar, conferir e fazer backup |
| `docs/` | A documentação técnica: o case, a arquitetura, as decisões (ADRs), os experimentos, a avaliação, os dados, os prompts, a ética e a privacidade, a segurança, os testes de segurança e a hospedagem |
