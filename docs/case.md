# O case: Integra Folha

> Case da certificação de Engenharia de IA. **Tema 2 — Automação e Extração de Conhecimento**, com um
> componente do tema 1 (Assistência e Interação) no Assistente de Correção, no Consultor e no
> Endomarketing. Todos os dados são sintéticos (`dados.md`).

## 1. A dor

Para pagar o salário dos funcionários de uma empresa, o banco precisa receber a lista desses
funcionários num layout próprio. Hoje, **a empresa adapta o arquivo à mão**: cada sistema de RH gera
nomes de coluna, formatos e estruturas diferentes, e o banco só tem um arquivo-modelo, sem manual.

O resultado:

- **50,4% das empresas desistem** antes de concluir o envio;
- funcionários dessas empresas que já são correntistas ficam **"falso não folha"**: o banco não
  reconhece que o salário deles cai ali, e perde o relacionamento que viria com isso.

## 2. A solução

A empresa envia a folha **no formato que já tem**. O sistema faz a ponte:

1. **O banco descreve o layout num parâmetro** (uma tela, com tipos de um catálogo fechado), sem programar.
2. **A IA interpreta as colunas** (Agente Interpretador, com RAG no parâmetro e no histórico de
   mapeamentos homologados) e pede ajuda quando há ambiguidade.
3. **Regras padronizam e validam** (sem LLM): CPF, datas, valores, duplicidades e renda incoerente com o cargo.
4. **Um assistente conduz a correção** até a homologação, com aprovação humana no que é sensível.
5. Depois da homologação, **o banco planeja**: quantas contas abrir, onde, quantos já são correntistas e
   o ganho projetado, com um **Consultor** (supervisor + 3 subagentes) que responde em linguagem natural.
   Só números agregados; nunca ofertas nem listas de pessoas.
6. **O banco gera, a empresa comunica:** o especialista do banco usa o **Agente de Endomarketing** para
   produzir o material de cada empresa (comunicado, FAQ, kit de boas-vindas, lembrete), com os benefícios que ele
   escolhe do catálogo daquela empresa e o kit de marca dela; cada frase cita a fonte. O especialista confere e
   publica; a empresa baixa e divulga aos funcionários. Assim, nenhum benefício é divulgado sem a validação do banco
   (ADR-115).

Princípio de desenho: **IA onde há ambiguidade, regra onde há certeza, humano onde há risco.**
Detalhes em `arquitetura.md`; os porquês em `decisoes.md`.

## 3. O valor (business case)

| Indicador | Hoje | Com a solução |
|---|---|---|
| Desistência das empresas | 50,4% | 20% (meta) |
| Clientes falso não folha | 520.220 | 206.437 (313.783 recuperados) |
| MOB por cliente em 12 meses | R$ 1.724,00 | R$ 2.090,62 (+R$ 366,62) |

**≈ R$ 115 MM em 12 meses** (313.783 × R$ 366,62). Premissa: o falso não folha cai na mesma proporção
da desistência (−60%). É **estimativa de potencial**, não receita realizada. Fonte: área de negócio.

**Base do business case:** estudo interno do banco que mediu a diferença, nos primeiros 12 meses de relacionamento,
entre o cliente folha identificado desde o dia 1 e o que nasce sem essa identificação. A curva foi extrapolada até a
estabilização do cliente folha, em cerca de 30 meses de MOB (2,5 anos de maturação das safras). **Referência:
fev/2026** (todos os números da tabela).

**Como 12 meses medidos viram uma curva de 30 meses:** as safras mais antigas de clientes folha mostram o formato da
curva até ela parar de subir (a estabilização). A premissa é que a diferença medida nos 12 primeiros meses siga esse
mesmo formato. Vale pedir à área de negócio uma faixa de sensibilidade (ex.: a diferença crescendo menos que o
previsto).
No sistema, esses valores são a versão 1 da tabela de premissas financeiras (parametrizável e versionada).

## 4. Quem usa

| Perfil | Tela | Para quê |
|---|---|---|
| EMPRESA (RH) | Portal da Empresa | Enviar a folha, conferir o mapeamento, corrigir, homologar e comunicar benefícios |
| BANCO (especialista) | Portal do Banco: Início, Empresas, Envios, Mensagens, Contas abertas, Telemetria, Planejamento, Parâmetros | Avaliar os envios, planejar a conquista, projetar ganhos, manter layout, premissas e catálogo, e acompanhar o uso e o desempenho da IA |

Nesta versão há só dois perfis: o banco tem a gestão completa (ADR-78). Uma gestão de acesso mais fina é evolução.

## 5. Escopo do MVP

**Dentro:** carga inicial e inclusões (tipo automático), parâmetro do layout pelo banco, interpretação
com IA + RAG, normalização e validação por regras, correção com aprovação humana, motor de
planejamento e cockpit, Consultor com subagentes, Endomarketing, avaliação B0–B4 (o Fine-Tuning foi avaliado e fica
para quando o volume justificar, ADR-80), guardrails e telemetria.

**Fora:** dados reais; desligamentos (o banco já detecta quando o salário deixa de cair); ofertas
individuais e campanhas; ciclo de vida do cliente; modelo de risco de renda (próximo passo);
integração bancária, SSO e infraestrutura de produção.

## 6. Como provamos que funciona

- **Experimento B0–B5** no Interpretador: a mesma prova de 300 cabeçalhos nunca vistos, do dicionário
  sem IA (B0) ao modelo pequeno ajustado (B5), com IC 95% por bootstrap. **B0 já medido: 50,9% por
  campo** (IC 95% 49,5% a 52,2%): é a régua que a IA precisa vencer.
- **RAG medido** com consultas de teste (hit@k) e isolamento entre empresas testado.
- **Testes da jornada** com arquivos que têm erros escondidos de propósito e gabarito.

## 7. Onde está cada coisa

| Documento | Conteúdo |
|---|---|
| `arquitetura.md` | Desenho, componentes, jornadas, RAG, segurança, escalabilidade |
| `decisoes.md` | 42 decisões (ADRs) com opções, porquê, trade-off e teste |
| `dados.md` | Ciclo de vida dos dados e ficha do dataset sintético |
| `etica_privacidade.md` | Premissas, matriz de cenários e limites |
| `proximos_passos.md` | Caminho até produção e melhorias |
| `../README.md` | Como rodar localmente |
