"""Configuração central do Integra Folha.

Tudo o que muda entre máquinas (modo, limites, caminhos, senhas, chaves) vem do arquivo .env,
nunca do código. O .env.example mostra quais variáveis existem.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Raiz do repositório (a pasta integra-folha/)
RAIZ = Path(__file__).resolve().parent.parent

# Lê as variáveis do arquivo .env (se existir) para o ambiente
load_dotenv(RAIZ / ".env")

# "mock" roda sem chave e sem custo; "llm" usa o provedor real (ADR-36)
MODO = os.getenv("MODE", "mock").strip().lower()

# Acima deste número de chamadas numa operação (um envio, uma conversa, uma leitura), a IA pausa (proteção de custo;
# ADR-145: antes, caía para o MOCK)
LIMITE_CHAMADAS_LLM_POR_SESSAO = int(os.getenv("LIMITE_CHAMADAS_LLM_POR_SESSAO", "50"))
# Teto de gasto por operação, em dólares: atingido, a IA também pausa.
# O valor padrão é de 10 dólares; a trava final é o crédito de cada conta
TETO_DE_GASTO_USD = float(os.getenv("TETO_DE_GASTO_USD", "10.00"))
# O MOCK de reserva (ADR-145): "sim" faz a IA real que não responde (o provedor falhou, ou a operação passou do limite
# de chamadas ou do teto acima) cair para a resposta simulada, como era antes. Só para a máquina local: a demo sem
# rede e as medições, que recusam a resposta simulada e contam a falha. Padrão "nao": a IA que não responde PAUSA o
# trabalho, e nada é simulado. O servidor nunca recebe esta chave: o contêiner só recebe as variáveis listadas no
# docker-compose.yml, e um teste confere que ela não está lá (tests/test_falha_da_ia_pausa.py)
MOCK_DE_RESERVA = os.getenv("MOCK_DE_RESERVA", "nao").strip().lower() == "sim"

# Chaves dos provedores de IA (ADR-11): ficam SÓ no .env, nunca no código nem no Git.
# Vazias, o modo LLM avisa que falta a chave (o modo MOCK não precisa delas)
CHAVE_OPENAI = os.getenv("OPENAI_API_KEY", "").strip()
CHAVE_ANTHROPIC = os.getenv("ANTHROPIC_API_KEY", "").strip()
# Os modelos que o sistema usa quando um agente pede "grande" ou "pequeno" (decididos pela comparação, ADR-11).
# Vazios, o modo LLM avisa que falta escolher o modelo
MODELO_GRANDE = os.getenv("MODELO_GRANDE", "").strip()
MODELO_PEQUENO = os.getenv("MODELO_PEQUENO", "").strip()

# Por onde a chamada à IA passa (ADR-96): "bedrock" (a nuvem da AWS, na nossa conta: o
# fornecedor do modelo não vê o pedido) ou "direta" (as APIs da Anthropic e da OpenAI, como era antes)
ROTA_DA_IA = os.getenv("ROTA_DA_IA", "direta").strip().lower()
# A chave do Bedrock (criada no console da AWS): fica SÓ no .env, nunca no código nem no Git
CHAVE_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip()
# A região da AWS de onde as chamadas saem (Norte da Virgínia: é de lá que o perfil "EUA" do Bedrock funciona)
REGIAO_BEDROCK = os.getenv("REGIAO_BEDROCK", "us-east-1").strip()

# Conferidor da Leitura (ADR-105): uma segunda IA (o modelo pequeno, de outro fornecedor) confere o que o Leitor
# entendeu. Ligado no .env desde a prova do EXP-015 (18 de 18 erros achados); o padrão do código continua "nao"
CONFERIDOR_DA_LEITURA = os.getenv("CONFERIDOR_DA_LEITURA", "nao").strip().lower() == "sim"
# Leitor de Documentos (ADR-73): o quanto a IA "pensa" antes de preencher os campos de cada pessoa: "low", "medium" ou "high"
LEITOR_ESFORCO = os.getenv("LEITOR_ESFORCO", "low").strip().lower()
# Interpretador (ADR-107): pedir o FORMATO GARANTIDO ao provedor (o modelo é obrigado a seguir o esquema da
# resposta). "nao" (padrão) mantém o Interpretador como foi medido no EXP-008; "sim" manda o esquema ao provedor
# (no Bedrock, pela API Converse; na rota direta, só o Claude usa, e a OpenAI ignora)
INTERPRETADOR_FORMATO_GARANTIDO = os.getenv("INTERPRETADOR_FORMATO_GARANTIDO", "nao").strip().lower() == "sim"
# Agente de Endomarketing: "sim" (padrão) usa o prompt padrão (hoje a v5, ADR-150), que leva o tom de voz e os termos
# proibidos das KBs gerais publicadas, a assinatura do kit em uso e a lista dos benefícios escolhidos; "nao" volta para
# o prompt v3, que fica como histórico
ENDOMARKETING_COM_AS_KBS = os.getenv("ENDOMARKETING_COM_AS_KBS", "sim").strip().lower() == "sim"

# Qual banco a aplicação usa (ADR-67): "sqlite" (um arquivo, sem servidor; padrão dos testes e de quem clona o
# projeto) ou "postgres" (servidor PostgreSQL; o ambiente local de uso e a produção)
BANCO = os.getenv("BANCO", "sqlite").strip().lower()
# Conexões do PostgreSQL (só no .env): a da aplicação, a dos testes e a do superusuário (só para preparar o servidor)
POSTGRES_URL = os.getenv("POSTGRES_URL", "").strip()
POSTGRES_URL_TESTES = os.getenv("POSTGRES_URL_TESTES", "").strip()
POSTGRES_ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "").strip()

# Banco SQLite da aplicação
CAMINHO_BANCO = RAIZ / os.getenv("CAMINHO_BANCO", "storage/integra_folha.db")

# Upload: tamanho máximo aceito no MVP e pasta onde o arquivo original fica guardado (fora do Git)
LIMITE_UPLOAD_MB = int(os.getenv("LIMITE_UPLOAD_MB", "5"))
PASTA_UPLOADS = RAIZ / os.getenv("PASTA_UPLOADS", "storage/uploads")
PASTA_HOMOLOGADOS = RAIZ / os.getenv("PASTA_HOMOLOGADOS", "storage/homologados")  # arquivos finais (fora do Git)

# Pontos de salvamento do fluxo da empresa (LangGraph): onde cada processamento parou (fora do Git)
CAMINHO_CHECKPOINTS = RAIZ / os.getenv("CAMINHO_CHECKPOINTS", "storage/checkpoints.db")
