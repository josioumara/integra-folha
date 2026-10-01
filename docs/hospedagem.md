# Hospedagem

> **A estrutura usada para publicar o site.** Diz onde o Integra Folha roda, com que peças, por que cada escolha foi
> feita, quanto custa e como publicar, conferir, voltar e recuperar.

> **Como ler.** Cada conceito técnico vem explicado numa frase simples, com um exemplo do próprio projeto. O que já
> está no ar aparece como ✅; o que está planejado, mas ainda não foi feito, como ⏳. Nenhum segredo aparece aqui:
> só onde cada um mora e quem o gera. Conferido na AWS em 2026-09-29.

**Endereço:** https://integrafolha.com.br · **No ar desde:** 2026-09-29, 13h45 · **Versão:** `308aa6e` (a IA em
modo mock) · **Região:** Virgínia (`us-east-1`) · **Credencial da publicação:** o usuário `integra-publicador` da
AWS (ADR-132) · **Modelo da infraestrutura:** `publicacao/infraestrutura.yaml` (pilha `integra-folha-producao`)

## 1. A arquitetura

O site roda numa única máquina na AWS. Dentro dela, o Docker separa três "caixas" (contêineres): o Caddy, a
aplicação e o banco. Só o Caddy fala com a internet.

```
                         Internet (quem acessa o site)
                                        │  https (443)   http (80) só redireciona para o https
                                        ▼
┌──────────────────────── Máquina EC2 t3.small · Ubuntu 24.04 · IP fixo 18.208.25.225 ────────────────────────┐
│  Firewall da AWS + firewall do Ubuntu (ufw): entram só 22 (SSH, só do IP de quem administra), 80 e 443    │
│                                                                                                            │
│   ┌─────────────┐   rede interna    ┌──────────────────────────┐   rede interna   ┌──────────────────────┐  │
│   │   Caddy     │ ────────────────▶ │  Aplicação (API FastAPI  │ ───────────────▶ │  Banco (PostgreSQL   │  │
│   │ https auto. │   aplicacao:8000  │  + telas), sem porta     │   banco:5432     │  18), sem porta      │  │
│   └─────────────┘                   │  para fora               │                  │  para fora           │  │
│                                     └────────────┬─────────────┘                  └──────────────────────┘  │
│                                                  │ volume "storage": índices do RAG e arquivos enviados       │
└──────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┘
                                                   │
                  ┌────────────────────────────────┴──────────────────────────────┐
                  ▼                                                               ▼
     AWS Bedrock (a IA, us-east-1, retenção zero)               Bucket S3 privado do backup (toda noite)
```

- **Proxy reverso (o Caddy):** é a recepção do prédio. Recebe todo visitante, confere o "crachá" (o https) e leva o
  pedido até a sala certa (a aplicação). A aplicação nunca fica exposta direto na internet.
- **Contêiner:** uma caixa isolada com um programa e tudo o que ele precisa. A mesma imagem roda igual no computador
  local e no servidor (ADR-35, ADR-108).

## 2. Os recursos na AWS, e o porquê de cada um

Tudo sai de um modelo só, o `publicacao/infraestrutura.yaml` (**infraestrutura como código**, com o CloudFormation).
É a planta da casa: com ela, a hospedagem inteira é recriada ou apagada com um comando, sem clique no console.

| Recurso | O que é no projeto | Por que assim |
|---|---|---|
| Região **Virgínia** (`us-east-1`) | Onde tudo roda | A mais barata, e a mesma do Bedrock (a IA fica perto e a retenção zero está gravada lá) |
| Máquina **EC2 `t3.small`** (2 GB) | O computador do site, ligado o tempo todo | A medição da memória (seção 8) cabe em 2 GB com o swap; o site precisa estar disponível a qualquer hora |
| **Swap de 2 GB** | Um pedaço do disco usado como memória extra | A primeira subida da aplicação (monta os índices do RAG) passa de 2 GB por alguns segundos |
| CPU em modo **"standard"** | A máquina não usa CPU extra paga | A `t3` nasce em "unlimited" e pode cobrar a mais sem aviso |
| **Disco gp3 de 30 GB**, criptografado | O sistema, as imagens do Docker, o banco e os arquivos | Folga para 3 versões da imagem (~1,1 GB cada) e o banco |
| **IP fixo** (Elastic IP) | O endereço `18.208.25.225`, que o domínio aponta | O IP comum muda quando a máquina reinicia, e o site sumiria |
| **Firewall** (Security Group) | O que pode entrar na máquina | Seção 3 |
| **Papel da máquina** (IAM role `integra-folha-maquina`) | A "credencial" que a máquina usa para gravar o backup | Nenhuma chave fica guardada no servidor; e o papel só grava, nunca apaga |
| **Bucket S3 privado** (`integra-folha-backup-<conta>`) | O depósito do backup | Privado, criptografado, com versões; apaga sozinho o que passa de 30 dias; sobrevive se a pilha for apagada |
| **Alarme de orçamento** (AWS Budgets, US$ 60/mês) | Um e-mail em 80% e 100% do valor, e quando a previsão do mês passa dele | Avisa antes de o gasto sair do previsto (só avisa, não desliga nada) |
| **Usuário `integra-publicador`** (fora desta pilha) | Quem cria e muda esses recursos | Não é a conta principal: só pode o que a publicação usa (ADR-132) |

## 3. A rede: o que está aberto e o que está fechado

Duas barreiras, uma por fora (o firewall da AWS) e uma por dentro (o `ufw` do Ubuntu):

| Porta | Para quê | Quem entra |
|---|---|---|
| 22 (SSH) | Entrar no servidor para publicar | **Só o IP de quem administra**, e só com a chave (sem senha, sem o root) |
| 80 (http) | Pegar o certificado e mandar o visitante para o https | Todos |
| 443 (https, TCP e UDP) | O site | Todos |
| 8000 (a aplicação) | — | **Fechada**: o Caddy chega nela pela rede interna do Docker |
| 5432 (o banco) | — | **Fechada**: só a aplicação fala com ele, pela rede interna |

- **O fail2ban** bloqueia quem erra a entrada pelo SSH várias vezes.
- **As atualizações de segurança** do Ubuntu são automáticas (`unattended-upgrades`).
- **Armadilha conhecida:** o Docker ignora o `ufw`. Por isso, nenhum serviço ganha porta para fora além do Caddy
  (`publicacao/compose.prod.yml` tira as portas da aplicação e do banco).

## 4. O domínio, o DNS e o https

- **Domínio:** `integrafolha.com.br`, registrado no registro.br. O `www` leva para o endereço sem `www`.
- **DNS** é a "lista telefônica" da internet: traduz o nome `integrafolha.com.br` no IP `18.208.25.225`. A zona fica
  no próprio registro.br, em modo avançado, com dois registros **A** (a raiz e o `www`), editados à mão (fora da AWS).
- **https:** o Caddy pede o certificado ao **Let's Encrypt** (uma autoridade gratuita) na primeira subida e o renova
  sozinho antes de vencer. O navegador passa a usar sempre https no endereço (HSTS).
- **Fora dos buscadores:** o site responde com `X-Robots-Tag: noindex`, e o `robots.txt` fecha tudo (ADR-100).

## 5. Os segredos: onde cada um mora e quem o gera

Nenhum segredo fica no Git, em mensagens ou na documentação.

| Segredo | Onde mora | Quem gera |
|---|---|---|
| Senhas do banco (administrador e aplicação) | `publicacao/.env` **no servidor** (só o dono lê: `chmod 600`) | Geradas no próprio servidor, na criação; nunca exibidas |
| Senha dos logins do site (os 17 da base viva e os dois da demo, `empresa.aurora` e `especialista.banco`), `SENHA_DA_BASE_VIVA` | O mesmo `.env` do servidor | Quem administra, pelo `publicacao/gravar_senha_do_site.sh` (digitada escondida, com pelo menos 12 caracteres; **diferente da senha local**) ✅ 30/09 |
| Chave do Bedrock (IA) | O mesmo `.env` do servidor | Quem administra a conta, uma chave **só de produção** ⏳ (a IA real ainda não foi ligada). A chave precisa também da permissão do detector de ataques do Bedrock Guardrails (ADR-147), gravada com a conta principal pelo `publicacao/dar_permissao_do_detector.sh`, no CloudShell. A chave do ambiente local já tem essa permissão (30/09) |
| Chave SSH | A parte privada só no computador local (`~/.ssh/integra-folha-ec2`); a AWS guarda só a pública | Gerada no computador local |
| Credencial do backup | Não existe chave: a máquina usa o papel dela | A AWS, a cada hora |
| Credencial do usuário `integra-publicador` | O `aws login` (expira em 12 h) | Quem administra, no navegador, com MFA |

O `.env` local (do computador) **nunca vai para o servidor**: o de produção nasce do modelo sem valores
`publicacao/.env.exemplo`.

## 6. Como publicar, conferir e voltar

**Quem decide:** uma versão nova só vai ao ar com aprovação explícita. Ela sai da `main`, com a bateria de testes
rodada antes.

1. **Mandar o código:** o commit vai para o servidor pelo `git push` (com o compose, o Caddy e os scripts).
2. **Construir:** a imagem sai **do commit** (`git archive`), e não da pasta de trabalho, e é construída **no
   servidor** (o Docker Desktop não cabe na memória do computador local; ADR-134). A etiqueta da imagem é o código
   do commit: dá para saber exatamente o que está no ar.
3. **Backup antes de trocar:** é o ponto de volta, se a versão nova mudar o banco.
4. **Trocar:** `publicacao/trocar_versao.sh` anota a versão anterior e sobe a nova. O servidor guarda as 3 últimas.
5. **Conferir** (`publicacao/conferir.sh`), as provas de toda publicação:
   - o endereço abre em https, com certificado válido;
   - uma página sem login volta para o login, e a API sem login responde 401;
   - o `robots.txt` tem `Disallow: /`, e as respostas trazem o `X-Robots-Tag: noindex`;
   - de fora, só as portas 22, 80 e 443; o 8000 e o 5432 estão fechados;
   - a IA é chamada pela Virgínia, onde a retenção zero está gravada (ADR-135);
   - a versão no ar é a do commit pedido, e o rodapé mostra a data dela (ADR-133).
6. **Voltar:** se uma prova falhar, o `publicar.sh` volta **sozinho** à versão anterior e avisa.

Tudo isso roda com um comando: `bash publicacao/publicar.sh <commit>`.

**A primeira publicação (2026-09-29, versão `ac93d15`):**

| Prova | Resultado |
|---|---|
| https com certificado válido | ✅ Let's Encrypt, para `integrafolha.com.br` e `www`, válido até 28/12/2026 (renovação automática) |
| http leva ao https | ✅ 308 |
| Página sem login vai ao login; API sem login | ✅ vai ao `login.html`; ✅ 401 |
| Fora dos buscadores | ✅ `robots.txt` com `Disallow: /`; ✅ `X-Robots-Tag: noindex` |
| Portas | ✅ 8000 e 5432 fechadas por fora; no servidor, só 22, 80 e 443 |
| IA pela Virgínia | ✅ `REGIAO_BEDROCK=us-east-1` |
| Versão no ar | ✅ `ac93d156e2e8`; o rodapé mostra "Atualizado em 29/09/2026 às 11:52" (ADR-133) |
| Login com usuário inexistente | ✅ 401 (o banco responde) |

**As publicações seguintes:**

| Data | Versão | O que mudou no site | Provas |
|---|---|---|---|
| 2026-09-30 | `308aa6e` (antes: `ac93d15`) | O Consultor saiu (ADR-144); só 4 obrigatórios (ADR-143), com o parâmetro gravado no banco do site pelo `scripts/aplicar_parametro_adr_143.py` e o índice do RAG refeito; as "Informações sem rótulo"; a base viva (17 empresas, `scripts/carregar_base_viva.py`, sem IA) com a senha nova do site. A IA continua em `mock` | ✅ 11 de 11, antes e depois da carga |

**Quando a versão muda o banco** (um parâmetro, uma carga de dados), o passo é feito **no servidor**, depois da troca e
com o backup da troca como ponto de volta: a aplicação para, o script roda num contêiner de uma vez só
(`docker compose run --rm -T aplicacao python scripts/<script>.py`), e a aplicação sobe de novo.

## 7. O backup e a restauração

- **O que entra:** o banco inteiro (`pg_dump`) e o volume `storage` (os índices do RAG e os arquivos enviados). O
  modelo de embeddings fica de fora, porque é baixado de novo sozinho.
- **Quando:** toda noite, às 3h (horário de Brasília), e antes de cada troca de versão
  (`publicacao/fazer_backup.sh`).
- **Onde:** no bucket privado, em `backup/<data e hora>/`. A máquina grava pelo papel dela e **não consegue
  apagar**: um invasor na máquina não apagaria o backup.
- **Por quanto tempo:** 30 dias; o bucket apaga o mais velho sozinho.
- **O primeiro backup:** ✅ 2026-09-29, 13h45 (o banco com 6,6 KB e o `storage` com 686 KB; o site acabou de nascer).
- **A regra provada:** ✅ na máquina, `aws s3 cp` é permitido, e `aws s3 rm` e `aws s3 ls` respondem `AccessDenied`.
- **A restauração testada:** ⏳ backup que nunca foi restaurado não vale. O teste será feito uma vez e registrado
  aqui (o passo a passo e o tempo que levou).

## 8. O custo

**A medição que decidiu o tamanho da máquina** (2026-09-29, a aplicação no Docker do computador, sem IA):

| Momento | Aplicação | Banco |
|---|---|---|
| Parada | 140 MB | 66 MB |
| Em uso (17 planilhas enviadas) | ~1,0 GB | ~70 MB |
| Primeira subida (monta os índices do RAG) | 1,56 GB (pico) | 68 MB |

Com o Ubuntu, o Docker e o Caddy (~0,4 GB), o servidor usa ~1,5 GB em uso e ~2,0 GB na primeira subida: cabe na
`t3.small` (2 GB) com o swap. A `t3.medium` (4 GB) fica como o degrau seguinte, se a memória passar de ~80%.
**No servidor, depois da publicação:** 740 MB usados de 1,9 GB em repouso, com 58 MB de swap (a aplicação com
246 MB, o banco com 31 MB e o Caddy com 21 MB).

**O custo previsto** (preços conferidos na AWS em 2026-09-29, sob demanda, 730 horas por mês):

| Item | Preço | Por mês |
|---|---|---|
| Máquina `t3.small` | US$ 0,0208/hora | US$ 15,18 |
| IP fixo (IPv4 público) | US$ 0,005/hora | US$ 3,65 |
| Disco gp3 de 30 GB | US$ 0,08/GB por mês | US$ 2,40 |
| Backup no S3 | centavos | < US$ 0,50 |
| **Total da hospedagem** | | **≈ US$ 21/mês** |
| IA (Bedrock) | por uso | ⏳ desligada; o teto mensal é definido antes de ligar |

- **O custo real** de cada mês fica registrado aqui. ⏳
- **Máquina parada também custa:** o IP fixo e o disco continuam cobrando (~US$ 6/mês). Por isso o site fica ligado
  o tempo todo: ele precisa estar disponível a qualquer hora (ADR-134).

## 9. As decisões, os riscos e os próximos passos

**As decisões** (o detalhe de cada uma está em `decisoes.md`):

| ADR | Decisão |
|---|---|
| 132 | A publicação usa um usuário próprio (`integra-publicador`), e não a conta principal, com um limite nos papéis que ele cria |
| 134 | Virgínia e `t3.small` ligada o tempo todo, com swap, escolhida pela medição da memória |
| 135 | Retenção zero do Bedrock gravada na conta (vale para o perfil "us.", porque é conferida na região de origem) |
| 136 | Backup diário no S3 privado, gravado pelo papel da máquina, sem poder apagar |
| 137 | O Caddy como proxy reverso e https automático; a aplicação e o banco sem porta para fora |
| 100 | O site fora dos buscadores (`noindex` e `robots.txt`) |
| 108 e 110 | A aplicação em contêiner, rodando com um usuário sem poderes de administrador |

**Os riscos:**

| Risco | O que reduz |
|---|---|
| Memória apertada na `t3.small` com a IA real e vários usos ao mesmo tempo | O swap; a memória conferida de tempos em tempos; a troca para a `t3.medium` leva ~2 minutos |
| O IP de quem administra mudar e fechar a porta 22 | Atualizar o parâmetro `IpDaUsuaria` da pilha (um comando) |
| Gasto de IA fora do previsto | A IA desligada até definir o teto mensal; o teto por sessão; o alarme de orçamento. A versão seguinte da aplicação já traz o teto por dia e por mês (ADR-131) |
| Uma versão nova estragar o site | A conferência automática e a volta sozinha à versão anterior; o backup antes de cada troca |
| A chave do Bedrock vazar: a política padrão das chaves (`AmazonBedrockLimitedAccess`) também cria recursos que cobram caro, como a capacidade reservada de um modelo | A chave só no `.env` do servidor (`chmod 600`); o alarme de orçamento. Proposta: a chave de produção só com as permissões que a aplicação usa |
| Perda da máquina | O modelo recria tudo; o backup no S3 restaura os dados |

**Os próximos passos:**
- ⏳ Ligar a IA real, depois de definir o teto mensal (o ADR-131, já na `main`, traz o teto por mês, gravado pelo
  especialista na tela) e com uma chave do Bedrock só de produção.
  - A chave de produção recebe também a permissão do detector de ataques (ADR-147): quem administra a conta roda o
    `publicacao/dar_permissao_do_detector.sh <usuario-da-chave>` no CloudShell, com a conta principal. O script confere
    antes, pergunta e só então grava.
  - Na chave local, a permissão foi gravada em 30/09 e provada com 3 chamadas reais: o ataque teve nota 0,8 (suspeito),
    e as mensagens de RH tiveram 0,0. Cada chamada levou de 1,1 a 1,9 s a partir do Brasil, e o custo foi de
    US$ 0,00024.
- ⏳ Corrigir a primeira subida de uma imagem nova: o `preparar_servidor.py` tenta regravar `data/golden/*.json`,
  que o usuário sem poderes do contêiner não pode gravar (um reinício; os dados ficam completos). A correção é na
  aplicação.
- ⏳ Chamar o Bedrock pelo papel da máquina, sem chave nenhuma no servidor (depende de uma mudança na aplicação).
  Nesse caminho, a permissão `bedrock:InvokeGuardrailChecks` entra no papel da máquina (`infraestrutura.yaml`) e no
  limite `integra-limite-dos-papeis` (`usuario-publicador.yaml`, a pilha que só a conta principal atualiza).
- ⏳ Testar a restauração do backup e registrar aqui.
- ⏳ Registrar o custo real do primeiro mês.
