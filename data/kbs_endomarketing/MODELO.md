# Modelo padrão das KBs de endomarketing (ADR-125)

Toda KB desta pasta segue este modelo. A conferência automática (a "trava", em `services/kbs_endomarketing.py`)
recusa a KB que foge dele. Os arquivos daqui são a **versão 1** do repositório: na primeira vez, eles são carregados
no banco de dados como **publicados**. Depois disso, as KBs são criadas, editadas e revisadas pela tela
**Benefícios** do Portal Interno, e cada gravação vira uma versão nova.

## 1. Onde fica cada KB

```
data/kbs_endomarketing/
├── MODELO.md                  este arquivo (não é uma KB)
├── gerais/                    as regras que valem para todas as empresas (dono GERAL)
├── santander/                 o kit da marca do banco e a prateleira de benefícios (dono SANTANDER)
└── EMP001/ … EMP006/          as KBs de cada empresa (dono = o código da empresa)
    └── logo.png               o logo fictício da empresa, anexado à versão 1 da KB do kit
                               (gerado por scripts/gerar_logos_das_kbs.py)
```

Nome do arquivo: `<tipo>_<assunto>.md`, sem acento e sem espaço (ex.: `beneficio_conta_salario.md`).

## 2. A ficha (as primeiras linhas de toda KB)

A KB começa com uma ficha entre duas linhas `---`. Cada linha é `chave: valor`.

```
---
id: EMP001-BEN-CONTA-SALARIO
titulo: Conta salário sem tarifa
tipo: beneficio
dono: EMP001
vigencia_inicio: 2026-01-01
vigencia_fim: 2026-12-31
origem: Prateleira pública do Santander (reescrito); valores fictícios
categoria: Conta e dia a dia
---
```

| Chave | Obrigatória | O que é |
|---|---|---|
| `id` | sim | Único no repositório. Letras maiúsculas, números e hífen. Começa pelo dono (`GER-`, `SAN-`, `EMP001-`) |
| `titulo` | sim | O nome que aparece na tela e na vitrine |
| `tipo` | sim | Um dos tipos da tabela 3 |
| `dono` | sim | `GERAL`, `SANTANDER` ou o código da empresa (`EMP001`) |
| `vigencia_inicio`, `vigencia_fim` | sim | `AAAA-MM-DD`. Vencida, a KB aparece em "Para revisar" |
| `origem` | sim | De onde veio o texto: "Prateleira pública do Santander (reescrito)" ou "Exemplo criado para o case" |
| `categoria` | só em `beneficio` | Uma das 4 categorias da vitrine: `Conta e dia a dia`, `Crédito`, `Proteção`, `Investimentos` |
| `prateleira` | não (só em `beneficio` de empresa) | O `id` do benefício da prateleira do Santander de que ele deriva |
| `kit_escolhido` | só em `kit_da_marca` | `proprio` (a empresa tem kit) ou `padrao` (usa o padrão Santander) |
| `cores` | só em `kit_da_marca` | Até 5 cores `#rrggbb`, separadas por vírgula. A 1ª é a principal; a 2ª, a do rodapé |

**O logo não é chave da ficha.** A KB do kit é a fonte única das cores, do logo e da escolha entre o padrão e o
próprio. O logo é uma imagem (PNG ou JPEG, até 500 KB) anexada a cada **versão** da KB, pelo editor da tela: só um
rascunho recebe ou perde o logo, e uma versão nova nasce com o logo da versão em que se baseia. Na versão 1, entra o
`logo.png` da pasta da empresa. Ao publicar a KB do kit, o kit (a escolha, as cores e o logo) vai para a empresa; ao
retirá-la, a empresa volta ao padrão.

## 3. Os tipos e as seções obrigatórias

Depois da ficha vem o título (`# ...`) e as seções (`## ...`). As seções da tabela são obrigatórias, com texto.
Pode haver seções a mais.

| Tipo | Dono | Seções obrigatórias |
|---|---|---|
| `tom_de_voz` | GERAL | Quem fala · Personalidade · Como escrever · Exemplos certo e errado |
| `termos_proibidos` | GERAL | Por que existe · Termos proibidos · Expressões sob condição |
| `guardrails` | GERAL | O que o agente nunca faz · O que o agente sempre faz · Quando recusar |
| `diretrizes` | GERAL | Regras de comunicação · Avisos obrigatórios · Dados e privacidade |
| `canais` | GERAL | E-mail · Mural ou intranet · WhatsApp |
| `glossario` | GERAL | Termos |
| `jornada` | GERAL ou empresa | Visão geral · Passo a passo · Documentos necessários · Prazos · Dúvidas comuns |
| `kit_da_marca` | SANTANDER ou empresa | Identidade · Cores · Tipografia · Logo · Tom da marca · Assinatura · O que não fazer |
| `beneficio` | SANTANDER (prateleira) ou empresa | Resumo · Como funciona · Quem pode usar · Como contratar · Condições · Mensagem principal · O que não dizer |
| `landing_page` | empresa | Objetivo · Chamada principal · Seções da página · Botões · Perguntas frequentes · Avisos legais |
| `atendimento` | empresa | Onde consultar · Canais de dúvidas |

## 4. As regras da trava (o que bloqueia a gravação e a publicação)

1. **Ficha completa** e com os valores permitidos (tabela 2); vigência com o fim depois do início.
2. **Seções obrigatórias** do tipo, todas com texto.
3. **Termos proibidos:** nenhum termo da tabela da KB `GER-TERMOS-PROIBIDOS` pode aparecer. As seções que citam o
   proibido de propósito ficam de fora: "O que não dizer", "O que não fazer", "Exemplos certo e errado", "Termos
   proibidos", "Expressões sob condição" e "O que o agente nunca faz".
4. **Valor sempre marcado:** toda linha com `R$` ou `%` precisa ter a palavra `simulação` (os valores do case são
   fictícios; o valor real vem da proposta do banco).
5. **Sem dado pessoal:** nada com cara de CPF.
6. **Sem ordem para a IA:** o guardrail de injeção do projeto (ADR-38) confere o texto inteiro.

**Só avisa (não bloqueia):** KB vencida; benefício com categoria que a vitrine não conhece; kit próprio sem logo (a
arte sai só com as cores e o nome da empresa).

## 5. Como escrever

- Português do Brasil, frases curtas, "você" para o funcionário.
- Todo benefício diz **para quem é** e **o que depende de análise** ("sujeito a análise de crédito").
- Nada de número inventado fora de "Condições", e nenhum número sem "(simulação)".
- A empresa fala com o funcionário; o Santander é o **banco parceiro**. Não escrever como se o texto fosse oficial
  do banco.
