# Bancos de dados: o que guardamos, onde, por quê e para onde crescer

O projeto usa **três tipos de armazenamento**, cada um para um tipo de trabalho, e **arquivos versionados no Git**
para o que precisa ser conferido e reproduzido. Este capítulo explica cada um, a avaliação que levou ao
**PostgreSQL** (ADR-67), como inspecionar os dados e o que usar se a aplicação crescer.

## 1. Visão geral

| Onde | Tipo | O que guarda | Quem usa | Vai para o Git? |
|---|---|---|---|---|
| **PostgreSQL** (banco `integra_folha`) | **Banco relacional** (servidor) | Tudo o que a ferramenta opera: usuários, arquivos e cada etapa deles, planejamento, parâmetros, auditoria e o ponto de salvamento do fluxo | Todas as telas e serviços | Não (dados de uso) |
| `storage/integra_folha.db` e `storage/checkpoints.db` | Relacional (SQLite, um arquivo) | O mesmo conteúdo, quando `BANCO=sqlite`: é o banco dos testes automáticos e de quem clona o projeto sem instalar servidor | Testes e reprodução | Não |
| `storage/indices/` | **Banco vetorial** (ChromaDB) | O conhecimento do RAG em forma de significado: layout, regras, mapeamentos homologados e catálogos | Interpretador, Assistente de Correção, Endomarketing | Não (é refeito por `scripts/build_index.py`) |
| `data/` (JSON, CSV, Markdown) | Arquivos | Parâmetros de partida, dados sintéticos, gabaritos, a prova da avaliação, resultados e o histórico de experimentos | Scripts de geração e de avaliação | **Sim** |
| `storage/uploads/`, `storage/homologados/` | Arquivos | O original enviado pela empresa e o arquivo final homologado | Portal | Não |

### A diferença, em uma frase cada

- **Banco relacional:** uma planilha muito organizada, com tabelas, colunas e regras. Responde perguntas exatas:
  "quais arquivos da Aurora estão homologados?".
- **Banco vetorial:** uma biblioteca organizada por **assunto**, não por título. Cada trecho vira um vetor de
  números que representa o significado dele, e a busca responde "o que é **parecido** com isto?". Assim,
  "Remuneração" encontra `valor_renda` mesmo sem palavra em comum.
- **Ponto de salvamento:** o "salvar jogo" do fluxo. Guarda em que etapa cada arquivo está, para continuar do mesmo
  ponto mesmo se a página for recarregada.
- **SQLite × PostgreSQL:** o SQLite é um caderno que fica numa gaveta (um arquivo, uma pessoa escreve por vez); o
  PostgreSQL é um cartório com balcão (um servidor que atende muitos ao mesmo tempo, confere quem é cada um e guarda
  cópias).

## 2. Um só código para os dois bancos: a porta `services/banco.py`

Todo o sistema abre o banco por uma única porta. A variável `BANCO` do `.env` escolhe: `postgres` (o uso na
máquina e a produção) ou `sqlite` (o padrão: testes e reprodução sem servidor). O código escreve SQL que funciona nos
dois; a porta cuida das poucas diferenças:

| Diferença | SQLite | PostgreSQL | Como a porta resolve |
|---|---|---|---|
| Sinal dos valores no comando | `?` | `%s` | Traduz sozinha |
| Número automático de linha | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | Traduz sozinha |
| Ordem de gravação (`rowid`) | Existe escondida em toda tabela | Não existe | Acrescenta a coluna `rowid` em cada tabela criada lá |
| "Criar a visão se não existir" | `CREATE VIEW IF NOT EXISTS` | Não existe | Confere se a visão existe antes de criar |
| Lista de colunas | `PRAGMA table_info` | `information_schema.columns` | `banco.colunas_da_tabela()` |
| Quando a transação abre | Só antes de uma gravação | Antes de qualquer comando | Abre só antes de gravar (uma leitura não segura "travas") |
| Tipo das somas | Inteiro | `numeric` (Decimal) | Devolve inteiro, como o SQLite |

O que é igual nos dois ficou igual no código: `INSERT ... ON CONFLICT (...) DO UPDATE` (gravar ou atualizar) e
`ON CONFLICT DO NOTHING` (gravar só se ainda não existe) substituíram os `INSERT OR REPLACE/IGNORE`, que só o SQLite
entende. Somas com condição usam `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`, que os dois aceitam.

**Por que manter o SQLite também:** qualquer pessoa (inclusive a banca) clona o projeto e roda tudo sem instalar um
servidor, e os testes rodam em qualquer máquina. **A prova de que os dois se comportam igual:** a mesma bateria de
testes roda nos dois bancos (seção 9).

## 3. As tabelas da aplicação

As tabelas são criadas pelos próprios serviços na primeira vez que são usadas. Colunas novas entram por migração
simples, que acrescenta sem apagar nada (ex.: `data_referencia`).

| Grupo | Tabelas | O que guardam |
|---|---|---|
| Acesso | `usuarios`, `sessoes`, `tentativas_de_login` | Usuários com perfil e empresa (a senha só como *hash*; `ultimo_acesso` e `acesso_valido_ate`, a validade do acesso da empresa, ADR-146); sessões de 8 horas; as senhas erradas recentes de cada login digitado, para o bloqueio de 15 minutos depois de 5 erros (ADR-110) |
| O arquivo, etapa por etapa | `processamentos`, `mapeamentos`, `normalizacoes`, `validacoes`, `correcoes`, `resolucoes_alerta`, `homologacoes` | O retrato do arquivo, a proposta de mapeamento e o aceite, os dados padronizados, os achados, cada correção (pedido e clique), as justificativas e o relatório da homologação com o checksum |
| Quem já foi homologado | `funcionarios_homologados`, `historico_mapeamentos` | Base das inclusões (quem já entrou) e dos mapeamentos aprovados que o RAG reaproveita |
| Planejamento do banco | `planejamento_funcionario`, visão `resumo_planejamento`, `simulacao_ganho` | Só os 5 campos liberados e o **hash do CPF** (nunca o CPF); a visão soma os números do Cockpit; as simulações salvas |
| Parâmetros | `parametros`, `catalogo_documentos` | Layout e premissas **versionados** (cada mudança é uma versão nova); o catálogo de benefícios de cada empresa, com vigência |
| Rastreabilidade | `execucoes_agentes`, `eventos` | Cada etapa e agente executado (a Telemetria) e a auditoria de decisões |
| Endomarketing (ADR-115) | `materiais_endomarketing`, `logos_dos_kits`, `artes_dos_materiais` | Os materiais que o especialista do banco gera, com os benefícios escolhidos e a situação (RASCUNHO, PUBLICADO, DESCARTADO, RETIRADO; APROVADO só nos antigos, do modelo em que a empresa aprovava), quem publicou ou retirou e quando; o logo do kit de marca de cada empresa e a arte de cada material publicado, as duas imagens em **base64 num campo de texto** (funciona igual no PostgreSQL e no SQLite, sem pasta de arquivos a mais) |
| Fluxo (LangGraph) | `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` | O ponto de salvamento de cada arquivo (criadas pela biblioteca do LangGraph) |
| Opinião sobre os agentes (ADR-151) | `opinioes_dos_agentes` | O joinha de cada pessoa em cada interação com um agente (a chave é o tipo, a referência e o login: mudar de ideia troca o voto): o agente, o perfil, a empresa, o envio, o voto, o comentário opcional do 👎, a origem (`tela` ou `carga sintética`, os dados de demonstração) e as datas. O Acompanhamento dos agentes lê só os números agregados |

**O que liga tudo:** o `processamento_id`, o identificador de cada arquivo enviado. Todas as tabelas do grupo "o
arquivo, etapa por etapa" usam ele.

**Dados pessoais (sintéticos no MVP):**
- ficam em `normalizacoes` (os dados padronizados), `correcoes` (valor antes e depois), `funcionarios_homologados`
  (CPF, matrícula, cargo e renda, para detectar quem já entrou) e nos arquivos de `storage/uploads` e
  `storage/homologados`;
- o planejamento guarda só o hash do CPF;
- o Painel e a auditoria guardam só identificadores, etapas e contagens.
- o comentário do joinha (`opinioes_dos_agentes`) pode trazer dado pessoal: ele não vai para nenhuma IA, só quem votou
  o vê, e o Acompanhamento dos agentes mostra só quantos comentários há.

## 4. O ponto de salvamento do fluxo

O fluxo da empresa (`workflows/fluxo_empresa.py`) é um grafo do LangGraph que **para** esperando uma pessoa
(aceite, correção, homologação). A cada pausa, o estado é gravado: uma "linha do tempo" por arquivo
(`thread_id = processamento_id`). Com `BANCO=postgres`, ele fica nas tabelas `checkpoint*` do **mesmo** banco da
aplicação (biblioteca oficial `langgraph-checkpoint-postgres`); com `BANCO=sqlite`, no arquivo
`storage/checkpoints.db`. Por isso recarregar a página não refaz nenhuma etapa: medido, 0 etapas refeitas em 26
retomadas (ADR-49, ADR-59).

## 5. O banco vetorial do RAG (ChromaDB)

| Coleção | Trechos | O que tem | Filtro obrigatório |
|---|---|---|---|
| `conhecimento_layout` | 241 | 44 campos do layout, 18 regras de validação, 179 mapeamentos homologados (só vocabulário de treino) | — |
| `catalogo_beneficios` | 31 | As seções do catálogo de cada uma das 6 empresas | **empresa do usuário logado** e **vigência** |

- **Como vira vetor:** o modelo de embeddings `paraphrase-multilingual-MiniLM-L12-v2` roda **na máquina** (sem chave,
  sem custo, sem mandar texto para fora) e transforma cada trecho em **384 números**.
- **Como mede parecido:** pela distância de cosseno. 0 é o mesmo significado; quanto maior, mais diferente.
- **Cada trecho tem três partes:** o texto que o agente lê, as **etiquetas** (empresa, fonte, versão, vigência) e o
  vetor.
- **O índice não vai para o Git:** é refeito do zero a partir das fontes vigentes (`scripts/build_index.py`).

## 6. Por que a avaliação fica em arquivos, e não no banco

A prova da avaliação, os gabaritos, os resultados e o histórico de experimentos ficam em `data/`, **no Git**:
- cada mudança fica registrada com data e autor, e dá para comparar versões;
- a **prova congelada** (ADR-58) confere a impressão digital (SHA-256) de cada arquivo antes de medir. Numa tabela, um
  número poderia mudar sem deixar rastro;
- qualquer pessoa reproduz as medições com os comandos do README.

## 7. Avaliação: qual banco relacional usar (capacidades e entregas)

Avaliação **conceitual**: compara o que cada banco entrega para esta aplicação, com o volume da premissa de negócio.
Não é um teste de carga; os números de volume vêm do tamanho medido dos dados do projeto.

### 7.1 O volume esperado

- **Premissa de negócio:** os 520.220 clientes "falso não folha" são cerca de 50% dos funcionários das empresas
  conveniadas; a ferramenta recebe **todos**, então cerca de **1,04 milhão de funcionários** na carga inicial, mais
  os arquivos de inclusão (funcionários novos) ao longo do tempo.
- **Tamanho medido:** cada funcionário ocupa cerca de **1,5 KB** nos dados padronizados (medido no arquivo de teste:
  51.769 bytes para 35 pessoas, com o log das decisões), mais algumas centenas de bytes nas tabelas de homologados e
  de planejamento.
- **Estimativa:** 1,04 milhão × cerca de 2 KB ≈ **2 GB**, e perto de **3 GB** com os índices. É um volume
  **pequeno** para qualquer banco relacional moderno.

**Conclusão importante:** o tamanho, sozinho, não decide. O SQLite guarda 2 GB sem esforço (o limite teórico dele é
de terabytes). O que decide é **como** esses dados são usados: muitas empresas enviando arquivos ao mesmo tempo,
especialistas consultando o Cockpit enquanto isso, mais de uma cópia da aplicação, controle de acesso e cópia de
segurança.

### 7.2 As opções comparadas

| Critério | **SQLite** | **PostgreSQL** | **MariaDB / MySQL** |
|---|---|---|---|
| Como funciona | Um arquivo dentro da aplicação, sem servidor | Servidor próprio, acessado pela rede | Servidor próprio, acessado pela rede |
| Gravações ao mesmo tempo | **Uma por vez** (as outras esperam na fila) | Muitas ao mesmo tempo (cada transação vê a sua "foto" dos dados, sem travar quem só lê) | Muitas ao mesmo tempo (motor InnoDB) |
| Mais de uma cópia da aplicação | Não (o arquivo fica num disco só) | Sim | Sim |
| Acessos e segurança | Quem abre o arquivo vê tudo; sem usuários no banco | Usuários e permissões por tabela, regra por linha (ex.: cada empresa só vê as suas), conexão criptografada | Usuários e permissões, conexão criptografada |
| Estabilidade e recuperação | Cópia do arquivo; sem réplica nativa | Réplica em tempo real, volta a qualquer momento do passado (PITR), décadas de uso em bancos e governo | Réplica e cluster (Galera); muito usado na web |
| Integridade dos dados | Tipos flexíveis (aceita texto numa coluna de número) | Tipos rígidos: recusa dado do tipo errado | Rígido no modo estrito |
| Ecossistema de IA | — | **pgvector** (busca por significado no próprio banco) e o ponto de salvamento **oficial** do LangGraph | Busca vetorial nas versões recentes; ponto de salvamento do LangGraph só em pacote comunitário |
| Oferta gerenciada nas nuvens | Não se aplica | Todas as grandes nuvens e vários serviços especializados | Todas as grandes nuvens |
| Custo de licença | Zero | Zero (código aberto) | Zero (código aberto) |
| Operação | Nenhuma | Um servidor para manter (ou um serviço gerenciado) | Um servidor para manter (ou um serviço gerenciado) |
| Reprodução por quem clona o projeto | Imediata | Exige instalar o servidor | Exige instalar o servidor |

### 7.3 A decisão (ADR-67)

**PostgreSQL** para o uso da aplicação (máquina local e produção), com o **SQLite** mantido como alternativa pela
mesma porta, para os testes e para quem só quer reproduzir o projeto.

- **Acessos:** o PostgreSQL separa quem administra de quem usa. A aplicação entra com um usuário **sem poderes de
  administrador** (`integra_folha_app`): se a senha dele vazar, não dá poder sobre o servidor (princípio do menor
  privilégio). O SQLite não tem usuários: quem tem o arquivo tem tudo.
- **Estabilidade:** muitas empresas enviando arquivos e o especialista consultando o Cockpit ao mesmo tempo, sem fila
  de gravação; cópia de segurança com volta a qualquer ponto do passado; réplica para continuar no ar se um servidor
  cair.
- **Integridade:** tipos rígidos recusam dado errado na entrada; no SQLite, o erro só apareceria depois.
- **IA:** o mesmo servidor pode guardar os vetores do RAG (pgvector) e o ponto de salvamento do LangGraph tem versão
  oficial.
- **Por que não MariaDB/MySQL:** entregariam concorrência e acessos parecidos, mas perdem no ecossistema de IA desta
  aplicação (sem ponto de salvamento oficial do LangGraph; pgvector é o caminho mais usado para RAG em banco
  relacional) e no controle por linha.

**O que custou (medido):** 1 arquivo novo (`services/banco.py`), 9 comandos reescritos para a forma que os dois
bancos aceitam, 3 consultas de estrutura trocadas por uma função, o ponto de salvamento do LangGraph trocado e a
bateria de testes preparada para rodar nos dois bancos.

## 8. Se a aplicação crescer

| Estágio | Sinal | O que usar |
|---|---|---|
| **Hoje (MVP e demo)** | Poucos usuários, uma cópia da aplicação | PostgreSQL num servidor só (ou SQLite para reproduzir) |
| **Piloto com empresas reais** | Dezenas de empresas enviando no mesmo dia | PostgreSQL **gerenciado** numa nuvem (backup automático, PITR, criptografia em repouso); um "pool" de conexões (um porteiro que reaproveita conexões); regra por linha para separar as empresas também no banco |
| **Escala do banco (≈1 milhão de funcionários e crescendo)** | Muitas cópias da aplicação; Cockpit pesado ao mesmo tempo que as cargas | Réplica só de leitura para o Cockpit e o Painel; tabelas grandes divididas por data de referência (particionamento); migrações formais de estrutura (ex.: Alembic) |
| **RAG em produção** | Catálogos e mapeamentos de milhares de empresas | Vetores no próprio PostgreSQL (pgvector), com o filtro de empresa na mesma consulta; ou um banco vetorial gerenciado. A troca fica isolada em `rag/busca.py` |
| **Análises pesadas** | Séries históricas, painéis com anos de dados | Um banco analítico ao lado (ex.: DuckDB ou o data warehouse do banco), alimentado pelo PostgreSQL; a aplicação continua no PostgreSQL |

## 9. Como inspecionar e testar

### Ver os dados do PostgreSQL (DBeaver)

O **DBeaver Community** está instalado. Para conectar:
1. abrir o DBeaver → **Nova conexão** (ícone de tomada com "+") → **PostgreSQL** → Avançar;
2. **Host:** `localhost` · **Porta:** `5432` · **Banco:** `integra_folha` · **Usuário:** `integra_folha_app`;
3. **Senha:** está no `.env`, na linha `POSTGRES_URL` (o trecho entre `integra_folha_app:` e `@localhost`);
4. se o DBeaver pedir para baixar o *driver*, aceitar; **Testar conexão** → **Concluir**;
5. as tabelas ficam em `integra_folha` → `Esquemas` → `public` → `Tabelas`. A visão `resumo_planejamento` fica em
   `Visões`.

**Só leitura:** editar na mão pula as regras de negócio e a auditoria. Para mudar dados, use as telas.

### Outras inspeções

| O que ver | Como |
|---|---|
| Tabelas do SQLite (quando `BANCO=sqlite`) | No VS Code, a extensão **SQLite Viewer**: clicar em `storage/integra_folha.db` |
| O conteúdo do ChromaDB | `python scripts/ver_indices_rag.py` (coleções, contagens e exemplos); com `--buscar "texto"` mostra os trechos parecidos e a distância; com `--empresa EMP002` busca no catálogo da empresa |
| Os experimentos | `docs/experimentos.md` (gerado a partir de `data/avaliacao/experimentos/`) |

### Preparar o PostgreSQL numa máquina nova

1. instalar o PostgreSQL e pôr a conexão do superusuário em `POSTGRES_ADMIN_URL` no `.env`;
2. `python scripts/preparar_postgres.py`: cria o usuário da aplicação e os bancos `integra_folha` e
   `integra_folha_testes`, e grava `POSTGRES_URL` e `POSTGRES_URL_TESTES` no `.env` (a senha nunca é mostrada);
3. (opcional) `python scripts/migrar_sqlite_para_postgres.py`: copia os dados do SQLite (tabelas e pontos de
   salvamento), confere as contagens e **nunca sobrescreve** um PostgreSQL que já tenha dados;
4. `BANCO=postgres` no `.env`.

### Com Docker (sem instalar o PostgreSQL)

`docker compose up --build` sobe o PostgreSQL oficial e a aplicação juntos (passo a passo no README, seção
"Docker"). Na primeira subida, `docker/postgres/criar_usuario_da_aplicacao.sh` cria o usuário da aplicação e o
banco; as tabelas nascem no primeiro uso. Para o DBeaver, use a porta **5433** (aberta só na própria máquina).

### Rodar os testes nos dois bancos

- `python -m pytest`: no SQLite (padrão, em qualquer máquina). As provas de `tests/test_banco.py` que precisam do
  PostgreSQL rodam quando `POSTGRES_URL_TESTES` existe, e são puladas quando não existe;
- no PowerShell, `$env:BANCO_DOS_TESTES="postgres"; python -m pytest`: a mesma bateria no banco de **testes** do
  PostgreSQL (nunca no da aplicação). Cada teste ganha um esquema novo (uma "pasta" de tabelas), apagado no fim.
