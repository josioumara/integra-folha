# Imagem da aplicação: a mesma aplicação roda igual na máquina local e no servidor (ADR-35)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Um usuário sem poderes de administrador para rodar a aplicação (ADR-110). Por padrão, tudo num contêiner roda como
# "root", o administrador: se alguém conseguisse invadir a aplicação, poderia mexer em tudo dentro do contêiner. Com um
# usuário comum, o invasor fica preso ao que esse usuário pode fazer.
# - o código (/app) continua sendo do administrador: o usuário da aplicação lê, mas não consegue alterar o programa;
# - o usuário da aplicação é dono só do que ele precisa escrever: /app/storage (banco SQLite, índices do RAG, modelo de
#   embeddings, arquivos enviados; é o volume do docker-compose) e /app/data/synthetic (os dados de exemplo que o
#   scripts/preparar_servidor.py gera na subida);
# - ele tem uma pasta pessoal (/home/integra), onde as bibliotecas guardam o que baixam por conta própria (cache).
# Na primeira subida, o Docker cria o volume vazio copiando a pasta /app/storage da imagem, com o mesmo dono.
RUN useradd --create-home --home-dir /home/integra --shell /usr/sbin/nologin integra \
    && mkdir -p /app/storage /app/data/synthetic \
    && chown -R integra:integra /app/storage /app/data/synthetic

# Sem chave de API, a aplicação roda em modo MOCK
ENV MODE=mock

# A API (FastAPI) atende as telas do front e as rotas /api na mesma porta
EXPOSE 8000

# Daqui em diante (e na subida), tudo roda como o usuário sem poderes
USER integra

# Na subida, gera só o que falta (dados, índices do RAG e, com as senhas nos segredos, os usuários) e depois sobe a
# API (ADR-64, ADR-108). PORT é definido pela hospedagem; localmente, usa 8000.
# --proxy-headers e --forwarded-allow-ips: na AWS, o https termina no balanceador de carga e a aplicação recebe http;
# com estas opções, ela confia no cabeçalho X-Forwarded-Proto e marca o cookie de login como seguro (só https)
CMD ["sh", "-c", "python scripts/preparar_servidor.py && uvicorn api.principal:aplicacao --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
