# Próximos passos: do MVP à produção no banco

> Responde ao enunciado: **plano de implementação, desafios e melhorias futuras.** O mesmo conteúdo
> está no slide 18 da apresentação executiva, sem datas.

## 1. Como a solução foi construída

Quinze fases em quatro blocos, e cada fase só começa depois que a anterior foi testada:

| Bloco | Fases | O que entrega |
|---|---|---|
| 1 · Fundação | 0 a 2 | Contratos, telas por perfil, dados sintéticos, parâmetros versionados, RAG e baseline B0 |
| 2 · Jornada da empresa | 3 a 8 | Upload, interpretação, normalização, validação, correção e homologação, orquestrados com pausa e retomada |
| 3 · Inteligência do banco | 9 a 12 | Motor de planejamento, cockpit, Consultor com subagentes, Endomarketing e telemetria |
| 4 · Prova | 13 a 15 | Guardrails testados, avaliação B0–B5, publicação e ensaio |

## 2. Como chega ao banco

| Etapa | O que acontece | Principal desafio |
|---|---|---|
| 1 · MVP | Demo publicada com login e dados sintéticos | Provar valor com evidência medida, não com impressão |
| 2 · Piloto | Empresas reais, em grupo controlado | Adoção pelas empresas; medir a queda real da desistência contra um grupo de comparação |
| 3 · Integração | Esteira de folha, cadastro e layouts oficiais do banco | Sistemas legados e o layout real, que hoje é material interno |
| 4 · Produção segura | SSO corporativo, hospedagem interna, PostgreSQL, interface web | Aprovação do provedor de IA (ou modelo interno) e validação jurídica das finalidades |
| 5 · Evolução | Aprender com correções homologadas e novos formatos | Governança contínua: monitorar qualidade, custo e deriva dos modelos |

## 3. Melhorias previstas

| Melhoria | Por quê | Ponto de partida no MVP |
|---|---|---|
| **Modelo de risco de renda** | Hoje o enquadramento é por regra (mediana e desvio do cargo); um modelo supervisionado pode separar erro de digitação de fraude | Os alertas justificados ou corrigidos pela empresa viram rótulos |
| **Funcionário que troca de empresa** | Quem chega de outra empresa já homologada precisa de regra de transferência do vínculo | Pendência de negócio registrada; o arquivo de inclusão já detecta quem está homologado na empresa |
| **Produção** | SSO no lugar do login próprio e PostgreSQL gerenciado (a interface web já substituiu o Streamlit, ADR-108) | Lógica isolada em `services/`: as telas e o banco trocaram e trocam sem reescrever as regras (ADR-33, ADR-34) |
| **Embeddings maiores** | Modelos maiores entendem melhor textos longos | Troca isolada em `rag/embeddings.py`; medir com as consultas de teste antes (ADR-42) |
| **Informação padrão (default) no parâmetro** (pedido da usuária, 2026-09-28; depois da POC) | Quando o banco espera um valor fixo num campo, ele o informa numa coluna nova do parâmetro, e o sistema usa esse valor ao gerar o arquivo, tenha a empresa mandado o campo ou não | O parâmetro do layout já é versionado e editado pelo banco (`services/parametros.py`, tela Parâmetros); o valor entraria na padronização, antes da homologação |
| **Envio parcial: as pessoas prontas de um arquivo com pendências** (pedido da usuária, 2026-09-28; depois da POC) | Mandar ao banco as pessoas "Aguardando envio" de vários arquivos de uma vez, sem esperar as pendências das outras pessoas do mesmo arquivo | Hoje o arquivo é a unidade de validação, avaliação e homologação; o caminho estudado é dividir o envio num "envio-filho" só com as pessoas prontas, que entra direto na avaliação do banco (estimativa: 4 a 5 h). Até lá: filtro de pendências por arquivo e "Não cadastrar esta pessoa" |
| **Enviar só a coluna que faltou** (ADR-124, alternativa C; depois da POC) | Num arquivo grande sem uma coluna que não é a mesma para todos, a empresa manda uma planilha pequena só com o CPF e essa coluna, sem refazer a leitura do arquivo inteiro | Só vale com todos os CPFs do envio válidos e sem repetição (a chave precisa ser confiável; dúvida da usuária, 2026-09-28); fora disso, o caminho é enviar o arquivo de novo. Hoje: "Informar pessoa a pessoa" no cartão (a chave é a linha do arquivo) e "Descartar a leitura e enviar outro arquivo" |
| **Avaliação contínua** | Planilhas reais trarão problemas que o gerador não imaginou | Conjuntos de prova versionados e scripts de avaliação reprodutíveis |

## 4. Riscos e como tratar

| Risco | Tratamento |
|---|---|
| Premissa de finalidade não aceita pelo jurídico | O motor já só lê campos autorizados e só gera agregados; ajustar o parâmetro, não o código |
| Custo de LLM acima do previsto | Reuso do mapeamento nas inclusões (sem IA) e modelo pequeno ajustado (B5) |
| Prompt injection em arquivo real | Defesa em camadas, medida (detecção × alarme falso) e revisada no piloto |
| Resistência das empresas | O Portal aceita o arquivo como ele é; o piloto mede a adoção antes de escalar |
| Empresa esperando material de endomarketing (quem gera e publica é o banco, ADR-115) | Sugestões automáticas no Portal Interno (lembrete quando há funcionários sem conta; kit de boas-vindas a cada inclusão homologada) e a contagem de rascunhos e publicados por empresa; no piloto, medir o tempo entre a sugestão e a publicação |
