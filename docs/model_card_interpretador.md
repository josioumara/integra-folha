# Model card: Agente Interpretador

> Ficha do "modelo" que entende as colunas da planilha. Segue o formato de *model card*: o que é, para que
> serve, para que **não** serve, como foi avaliado e quais são os limites. Onde a informação depende do
> provedor de IA, que ainda não foi escolhido (ADR-11), a ficha diz **"a definir"**. Atualizar quando B1 a B5
> forem medidos.

## 1. O que é

| Item | Valor |
|---|---|
| Tarefa | Para cada coluna de uma planilha de funcionários, dizer qual campo do layout do banco ela alimenta, ou que é ambígua (AMBIGUO), ou que não corresponde a nada (NAO_MAPEADO) |
| Entrada | Nomes das colunas, tipo provável e amostras **reais** (os 3 primeiros valores diferentes de cada coluna, ADR-101); o layout ativo; conhecimento de apoio conforme a configuração (ADR-05) |
| Saída | Um `MappingPlan` validado por contrato (campo, status, justificativa e fontes de cada coluna) |
| Modelo | **A definir** (provedor não escolhido). Configurações previstas: LLM grande (B1 a B3), pequeno (B4) e pequeno ajustado (B5) |
| Régua sem IA | B0: dicionário de sinônimos + comparação aproximada de textos (RapidFuzz `WRatio`, limite 75) |
| Prompt | `prompts/interpretador_v2.md` (ver `docs/prompts.md`); a v1 levava as amostras mascaradas |
| Temperatura | 0 |
| Código | `agents/interpretador.py`, `services/mapeamentos.py`, `baselines/baseline_mapper.py` |

## 2. Uso pretendido

- Propor o mapeamento de uma planilha **nova** para uma **pessoa aceitar**: nada é aplicado sem o aceite da
  empresa (ADR-16).
- Pedir ajuda quando a coluna é ambígua (ex.: "Vencimentos" pode ser bruto, líquido ou valor do crédito), em
  vez de chutar.

## 3. Fora do uso pretendido

- Alterar, corrigir ou converter valores: quem converte é o Normalizador, com regras (ADR-46).
- Decidir severidade de erro, aprovar ou homologar: é da regra e da pessoa (ADR-47, ADR-16).
- Ler a folha inteira: vão só as amostras de cada coluna, e elas são DADO, nunca instrução (ADR-38, ADR-101).
- Planilhas que não sejam listas de funcionários para o layout do banco.

## 4. Dados

- **100% sintéticos** (ADR-21), gerados com semente. Ficha do conjunto em `docs/dados.md`.
- Prova: 300 planilhas (4.306 colunas com campo certo e 746 que deveriam virar pergunta), com vocabulário de
  colunas **nunca visto** no treino nem nos exemplos do prompt (ADR-37).
- Treino (para exemplos e para um Fine-Tuning futuro, fora desta versão, ADR-80): 1.500 planilhas com o vocabulário de treino.
- A prova e as métricas estão **congeladas** por impressão digital (ADR-58).

## 5. Avaliação

| Configuração | Acurácia por campo (IC 95%) | Abstenção: recall / precisão | Tempo por arquivo | Custo |
|---|---|---|---|---|
| B0 (sem IA) | 50,9% (49,5% a 52,2%) | 59,4% / 47,7% | 6 ms | zero |
| B1 a B5 | a definir (aguardando o provedor) | | | |

- **Por campo:** o B0 tem 8 campos com 0% de acerto (`valor_renda`, `matricula`, `nome_unidade` e cinco de
  endereço). É ali que a IA precisa mostrar ganho.
- **No fluxo inteiro** (9 arquivos, MOCK), com o mapeamento aceito por pessoa, os 9 erros injetados foram
  achados e os 9 arquivos homologados (ADR-59).
- Relatório completo: `docs/avaliacao.md`.

## 6. Proteções em volta do modelo

- **Entrada:** texto da planilha vai ao LLM como DADO, entre marcas; células e cabeçalhos com cara de ordem
  para a IA são neutralizados pelo guardrail de injeção (ADR-38, ADR-55).
- **Saída:** campo inexistente, coluna inexistente, fonte que não estava no prompt ou dois campos iguais viram
  pergunta para a empresa; duas respostas fora do contrato caem para as sugestões do B0, todas para confirmação.
- **Reuso:** nas inclusões, colunas já aprovadas não passam pela IA (ADR-24).
- **Custo:** limite de chamadas e teto de gasto por sessão; ao atingir, cai para MOCK (ADR-36, ADR-56).

## 7. Limites conhecidos

- Ainda não há número de qualidade da IA: tudo o que depende do provedor está marcado "a definir".
- O vocabulário sintético imita a variedade de sistemas de RH, mas planilhas reais podem trazer nomes que o
  gerador não imaginou: o piloto precisa medir de novo.
- A consistência em execuções repetidas só pode ser medida com o LLM real (em MOCK, a resposta é sempre igual).
- As medições com IA real feitas até aqui (EXP-008, em `docs/avaliacao.md`) usaram o prompt v1, com amostras
  mascaradas; com a v2, precisam ser refeitas (ADR-101).

## 8. Considerações éticas

- A decisão final é humana; a IA só propõe.
- Privacidade pelo destino: o modelo vê nomes de coluna e amostras reais, e roda só pelo AWS Bedrock (perfil EUA,
  retenção zero, sem acesso do fornecedor do modelo; ADR-96, ADR-101). Enquanto a chave não chega, a rota direta só
  recebe dados fictícios.
- Ver `docs/etica_privacidade.md`.
