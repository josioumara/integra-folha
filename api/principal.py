"""API do novo front: entrada, saída e o "porteiro" das páginas (ADR-69, decisão provisória).

Para que serve: as páginas do layout aprovado (pasta front/) viram o front de verdade. Este arquivo é o
servidor que as entrega ao navegador e que conversa com os serviços que já existem (login, sessões, e, nos
próximos passos, envios, agentes e planejamento). Começou como uma segunda porta ao lado das telas do
Streamlit; desde o ADR-108, é a única interface da aplicação.

O que existe aqui (primeiro passo):
    - POST /api/entrar: confere usuário e senha (services/auth.py) e cria a sessão (services/sessoes.py);
      o ingresso vai num cookie "httponly", que o JavaScript da página não consegue ler (protege contra roubo);
    - GET  /api/eu: diz quem está logado (ou 401, se ninguém);
    - GET  /api/sair: cancela a sessão, apaga o cookie e volta ao login;
    - GET  /api/versao: o rótulo "Atualizado em ..." do rodapé de todas as telas, sem login (ADR-133);
    - o PORTEIRO: antes de entregar uma página, confere se o perfil pode vê-la. Página do banco só para BANCO,
      página da empresa só para EMPRESA. Sem login, volta ao login;
    - GET /api/empresa/resumo, /envios/pagina, /funcionarios e /pendencias: os dados de "Acompanhar cadastros"
      (services/acompanhamento.py), só para o perfil EMPRESA e sempre da empresa da SESSÃO;
    - GET /api/empresa/pendencias/resolvidas: as pendências resolvidas pela conversa, com a conversa guardada
      (services/conversas_das_pendencias.py, ADR-120), só da empresa da SESSÃO;
    - GET /api/empresa/cadastro/{id}/ficha?linha=N: a ficha completa de uma pessoa do envio, aberta pelo cartão da
      pendência (services/ficha_da_pendencia.py, ADR-120), registrada como acesso;
    - POST /api/empresa/pendencias/corrigir e /confirmar: resolver uma pendência pela tela (services/correcoes.py
      e validador.justificar_alerta), com quem clicou registrado; e
      /preencher_para_todos: o mesmo valor em todos do envio que estão sem um campo (ex.: o CNPJ do empregador);
    - GET /api/empresa/funcionarios (lista), /funcionarios/{id} (ficha) e POST /funcionarios/baixar (CSV): com o
      CPF inteiro (ADR-97); cada acesso fica registrado (quem, quando, quantas pessoas) em acessos_a_dados;
    - /api/empresa/cadastro/...: enviar o arquivo, ver a leitura da IA, aceitar o mapeamento, homologar e
      descartar, sempre pelo fluxo em LangGraph (services/cadastro.py); e /assistente, /assistente/confirmar e
      /assistente/desfazer: a conversa com o Assistente de Correção sobre uma pendência
      (services/assistente_na_tela.py);
    - /api/banco/planejamento/...: o Planejamento (números agregados, ganho, simulações), só para o perfil BANCO
      (services/portal_do_banco.py).

Como rodar (na pasta integra-folha, com o .venv):
    python -m uvicorn api.principal:aplicacao --port 8000
e abrir http://localhost:8000/login.html

Conceitos para leigo:
    - API: o "balcão" do servidor. A página pede algo (ex.: "entrar com este usuário") e recebe a resposta
      em JSON, um formato de texto com os dados arrumados.
    - FastAPI: a biblioteca que monta esse balcão em Python, conferindo sozinha o formato de cada pedido.
    - Cookie httponly: um bilhete que o navegador guarda e devolve a cada pedido, mas que o JavaScript da
      página não enxerga. Mesmo que um código malicioso rode na página, ele não consegue copiar o ingresso.
"""
import logging
import mimetypes
from typing import Annotated
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.mensagem_de_erro import mensagem_para_a_pessoa
from models.contratos import Perfil, TipoCampo
from rag import busca, indice_do_layout
from services import progresso
# A página "Teto de gasto da IA" e a retomada dos envios pausados pelo teto (ADR-139)
from services import pagina_do_teto_da_ia
# As tarefas que rodam depois da resposta (ex.: a retomada dos envios depois de subir o teto)
from fastapi import BackgroundTasks
# A porta das operações sensíveis (confere o perfil de quem pede antes de gravar; ex.: as premissas oficiais)
from services import acesso
from services import (acompanhamento, apontamentos_do_banco, assistente_na_tela, auth, avaliacao_do_banco, cabecalho,
                      cadastro, config, contas_abertas, conversas_das_pendencias, endomarketing_do_banco,
                      ficha_da_pendencia, kbs_publicacao, kit_de_marca, mensagens, parametros, portal_da_empresa,
                      portal_do_banco, sessoes, tentativas_de_login)
from services import empresas as cadastro_de_empresas
# O teto de gasto com IA (ADR-131): a pausa vira um aviso claro para quem está na tela
from services import teto_de_gasto
# A IA real que não respondeu (ADR-145): a mesma pausa, com um aviso claro, e nada simulado no lugar
from services import llm_client
# A data da versão que está rodando, para o rótulo do rodapé (ADR-133)
from services import versao_da_aplicacao

# Com o "nosniff" (ADR-110), o navegador só roda um .js se o servidor disser que ele é JavaScript. No Windows, o
# registro do sistema às vezes diz que .js é "text/plain", e as telas parariam. Estas linhas fixam o tipo certo
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

# Pasta com as páginas do novo front (html, css e js), ao lado da pasta api/
PASTA_DO_FRONT = Path(__file__).resolve().parent.parent / "front"

# Página inicial de cada perfil, logo depois do login
PAGINA_INICIAL_DO_PERFIL = {
    Perfil.EMPRESA: "home.html",
    Perfil.BANCO: "banco_inicio.html",
}

# Páginas da empresa (Portal Empresa): só o perfil EMPRESA abre
PAGINAS_DA_EMPRESA = {"home.html", "cadastrar.html", "acompanhar.html", "beneficios.html", "endomarketing.html"}

# Páginas ocultas nesta versão (ADR-148): o código delas fica no projeto, mas quem abre o endereço volta para outra
# tela do mesmo perfil. Chave: a página oculta; valor: a tela para onde a pessoa vai.
# As Premissas financeiras saíram do menu Sistema; o Painel de acompanhamento continua lendo as premissas oficiais.
PAGINAS_OCULTAS_NESTA_VERSAO = {"banco_premissas.html": "banco_indicadores.html"}

# Mensagem única para qualquer falha no login: não revela se o erro foi no usuário ou na senha
MENSAGEM_LOGIN_RECUSADO = "Usuário ou senha incorretos."


class PedidoDeEntrada(BaseModel):
    """O que a tela de login manda para entrar: usuário e senha (o FastAPI confere que os dois vieram)."""

    # o login digitado (ex.: "empresa.aurora"); até 200 letras: o login digitado vai para a tabela de tentativas
    # (services/tentativas_de_login.py), e um texto gigante não pode ocupar o banco
    usuario: str = Field(max_length=200)
    senha: str              # a senha digitada (nunca é guardada nem devolvida)
    # Não há "Lembrar de mim": um campo "lembrar" mandado por uma tela antiga, guardada no
    # navegador, é ignorado (o pydantic descarta campos que o modelo não declara), e a sessão vale 8 horas do mesmo jeito


def pagina_permitida(perfil: Perfil, nome_da_pagina: str) -> bool:
    """Diz se um perfil pode abrir uma página do front.

    Recebe: perfil — EMPRESA ou BANCO; nome_da_pagina — ex.: "banco_envios.html".
    Devolve: True se pode abrir.
    Exemplos: (EMPRESA, "home.html") → True; (EMPRESA, "banco_inicio.html") → False;
              (BANCO, "banco_indicadores.html") → True; (BANCO, "home.html") → False.
    """
    # Páginas da empresa: só o perfil EMPRESA
    if nome_da_pagina in PAGINAS_DA_EMPRESA:
        return perfil == Perfil.EMPRESA
    # As páginas do banco (inclusive os Indicadores e a Configuração): só o perfil BANCO
    if nome_da_pagina.startswith("banco_"):
        return perfil == Perfil.BANCO
    # Qualquer outra página (não existe hoje): ninguém abre
    return False


def tela_no_lugar_da_pagina_oculta(caminho: str) -> str | None:
    """Diz se o endereço pede uma página oculta nesta versão e, se pede, para qual tela a pessoa vai (ADR-148).

    Recebe: caminho — o endereço pedido (ex.: "/banco_premissas.html").
    Devolve: a tela de volta (ex.: "banco_indicadores.html"), ou None quando a página não está oculta.
    O nome é comparado sem diferença entre maiúsculas e minúsculas e sem a barra, o ponto e o espaço do fim: no
    Windows, "/banco_Premissas.html" e "/banco_premissas.html." abrem o mesmo arquivo que "/banco_premissas.html".
    Exemplos: "/banco_premissas.html" → "banco_indicadores.html"; "/banco_premissas.html/" → "banco_indicadores.html";
              "/banco_parametros.html" → None.
    """
    # O nome da página, sem a barra do começo, sem barra, ponto ou espaço no fim e todo em minúsculas
    nome_da_pagina = caminho.lstrip("/").rstrip("/. ").lower()
    # A tela de volta, se a página está na lista das ocultas (get devolve None quando não está)
    return PAGINAS_OCULTAS_NESTA_VERSAO.get(nome_da_pagina)


# O registro de avisos da API (aparece no terminal do servidor): guarda o detalhe de um erro interno, que nunca vai
# para a tela
registro_de_avisos = logging.getLogger(__name__)
# O tamanho máximo de um código de envio ou de progresso recebido da tela (os nossos têm até 36 letras)
TAMANHO_DO_CODIGO_DO_ENVIO = 64
# O maior "início" de página aceito na lista de envios: nenhuma empresa tem um milhão de envios (B-14, C-19)
MAIOR_INICIO_DE_PAGINA = 1_000_000


# O que abre sem login, pelo endereço exato: a página de login, as páginas de Privacidade e LGPD e de Termos de uso
# (só texto, sem dado nenhum: a pessoa lê antes de entrar) e o recado para os buscadores
ENDERECOS_PUBLICOS = {"/login.html", "/privacidade.html", "/termos_de_uso.html", "/robots.txt"}
# As pastas que abrem sem login: a aparência (css e js, sem dado nenhum) e a API, que confere a sessão em cada rota
PASTAS_PUBLICAS = ("/css/", "/js/", "/api/")
# As rotas da API que abrem sem login: entrar, sair e a data da versão (o rodapé da tela de login mostra)
ENDERECOS_DA_API_SEM_LOGIN = {"/api/entrar", "/api/sair", "/api/versao"}


def pagina_precisa_de_login(caminho: str) -> bool:
    """Diz se um endereço só abre com login. A regra é uma LISTA DE LIBERAÇÃO: tudo exige login, menos o público.

    Recebe: caminho — o endereço pedido (ex.: "/banco_envios.html" ou "/css/estilos.css").
    Devolve: False para o login, as páginas de privacidade e de termos de uso, o robots.txt, /css/, /js/ e /api/;
    True para todo o resto.
    Por que liberar o que é público, e não bloquear as páginas: bloquear "o que termina em .html" deixava passar
    variações do mesmo arquivo ("/HOME.HTML", "/home.html." e "/banco_inicio.html/" abriam a página sem login no
    Windows). Com a lista de liberação, qualquer variação cai no "exige login".
    Exemplos: "/login.html" → False; "/css/estilos.css" → False; "/home.html" → True; "/HOME.HTML" → True.
    """
    # Endereço que tenta "voltar uma pasta" nunca é público, mesmo começando por uma pasta pública (B-21)
    if caminho_tenta_sair_da_pasta(caminho):
        return True
    # Endereços públicos, exatamente como estão escritos
    if caminho in ENDERECOS_PUBLICOS:
        return False
    # Pastas públicas (o começo do endereço)
    for pasta in PASTAS_PUBLICAS:
        if caminho.startswith(pasta):
            return False
    # Todo o resto só abre com login
    return True


def api_sem_login(caminho: str) -> bool:
    """Diz se o endereço é uma rota da API que exige login (todas, menos entrar, sair e a data da versão).

    Exemplos: "/api/eu" → True; "/api/entrar" → False; "/css/estilos.css" → False.
    """
    # Fora da API, ou tentando sair da pasta da API ("/api/../x", B-21): quem cuida é o resto do porteiro
    if not caminho.startswith("/api/") or caminho_tenta_sair_da_pasta(caminho):
        return False
    # As rotas abertas da API
    return caminho not in ENDERECOS_DA_API_SEM_LOGIN


def caminho_tenta_sair_da_pasta(caminho: str) -> bool:
    """Diz se o endereço tenta sair da pasta em que começa, com ".." (voltar uma pasta) ou "\\" (a barra do Windows).

    Por quê (B-21): "/js/%2e%2e/home.html" começa pela pasta pública /js/, mas o servidor de arquivos resolve o ".."
    e entrega front/home.html. O porteiro via "/js/..." e deixava passar sem login.
    Recebe: caminho — o endereço pedido. O servidor já traduziu os códigos "%2e" e "%2f" uma vez; traduzimos de novo
    para pegar também quem codificou duas vezes ("%252e").
    Exemplos: "/js/../home.html" → True; "/js/..\\home.html" → True; "/js/app.js" → False.
    """
    # O endereço com os códigos "%xx" traduzidos mais uma vez
    caminho_traduzido = unquote(caminho)
    # A barra invertida, que o Windows entende como separador de pasta
    if "\\" in caminho_traduzido:
        return True
    # Cada pedaço entre barras: ".." é "voltar uma pasta"
    for pedaco in caminho_traduzido.split("/"):
        if pedaco == "..":
            return True
    # Nenhuma tentativa de sair da pasta
    return False


def usuario_do_pedido(pedido: Request):
    """Devolve o usuário dono do cookie do pedido, se a sessão ainda vale; senão, None.

    Recebe: pedido — o pedido do navegador (traz os cookies). Devolve: o usuário ou None.
    """
    # Abre o banco (SQLite ou PostgreSQL, pelo .env) com a tabela de usuários pronta
    conexao = auth.conectar()
    # Confere o ingresso guardado no cookie (vencido, cancelado ou inventado devolve None)
    usuario = sessoes.validar_sessao(conexao, pedido.cookies.get(sessoes.NOME_COOKIE))
    # Fecha a conexão: cada pedido abre e fecha a sua
    conexao.close()
    # Devolve quem é (ou None)
    return usuario


def dados_publicos_do_usuario(usuario) -> dict:
    """Os dados do usuário que podem ir para a página: login, perfil, empresa e a página inicial.

    Recebe: usuario. Devolve: um dicionário (vira JSON). Nunca inclui senha, hash nem o ingresso.
    """
    # Só o necessário para a tela saber quem está logado e para onde ir
    return {
        "login": usuario.login,
        "perfil": usuario.perfil.value,
        "empresa_id": usuario.empresa_id,
        "pagina_inicial": PAGINA_INICIAL_DO_PERFIL[usuario.perfil],
        # Senha provisória: a primeira coisa na tela é trocá-la (ADR-109)
        "senha_provisoria": usuario.senha_provisoria,
    }


def exigir_senha_definitiva(usuario) -> None:
    """Levanta 403 se a pessoa ainda está com a senha provisória (dada pelo banco no convite ou na redefinição).

    Por quê (ADR-109): a senha provisória foi vista pelo especialista do banco. Até a própria pessoa trocá-la, ela só
    pode ver o cabeçalho, trocar a senha e sair; nenhum dado da empresa nem do banco sai para essa sessão.
    """
    if usuario.senha_provisoria:
        raise HTTPException(status_code=403, detail="Troque a senha provisória antes de continuar: clique no seu "
                                                    "nome, no alto da tela.")


# A aplicação FastAPI (o "balcão"). O nome "aplicacao" é o que o uvicorn procura para ligar o servidor.
# Sem as páginas automáticas de documentação da API (/docs, /redoc e /openapi.json): num site publicado, elas
# entregariam o mapa de todas as rotas para quem não entrou
aplicacao = FastAPI(title="Integra Folha · API do front", docs_url=None, redoc_url=None, openapi_url=None)
# A aplicação usa a memória que aprende: a busca consulta os mapeamentos aprovados pelo banco (ADR-70)
busca.ligar_mapeamentos_aprovados()


@aplicacao.exception_handler(teto_de_gasto.TetoDeGastoAtingido)
async def avisar_a_pausa_pelo_teto(pedido: Request, erro: teto_de_gasto.TetoDeGastoAtingido):
    """A IA foi pausada pelo teto de gasto do dia ou do mês (ADR-131): a pessoa recebe um aviso claro, e não um erro.

    Recebe: o pedido e a pausa. Devolve: 503 ("indisponível agora") com o recado de quem está na tela: o especialista
    do banco (rotas /api/banco/...) fica sabendo que é o teto; a empresa, que a análise volta depois. Quem registrou
    o ERRO na Telemetria foi o agente, antes de a pausa chegar aqui.
    """
    # O especialista do banco pode subir o teto: ele recebe o motivo
    if pedido.url.path.startswith("/api/banco/"):
        recado = teto_de_gasto.RECADO_PARA_O_BANCO
    else:
        recado = teto_de_gasto.RECADO_PARA_A_EMPRESA
    return JSONResponse(status_code=503, content={"detail": recado})


@aplicacao.exception_handler(RequestValidationError)
async def recusar_pedido_fora_do_formato(pedido: Request, erro: RequestValidationError):
    """O pedido não está no formato da rota (campo faltando, texto longo demais, número no lugar errado): 422.

    Recebe: o pedido e a recusa do FastAPI. Devolve: 422 com uma frase e os nomes dos campos com problema.
    Por quê (C-20): a resposta padrão do FastAPI devolve o valor que a pessoa mandou. Um texto com um caractere
    inválido (ex.: "\\ud800", metade de um caractere) não pode ser escrito na resposta, e a recusa virava erro
    interno (500). Aqui o valor enviado nunca volta: só o nome do campo.
    Exemplo: {"detail": "O pedido não está no formato esperado.", "campos": ["motivo"]}
    """
    # O nome de cada campo recusado ("body" e as posições em listas ficam de fora)
    campos = []
    for problema in erro.errors():
        partes_do_nome = []
        for parte in problema["loc"]:
            if isinstance(parte, str) and parte != "body":
                partes_do_nome.append(parte)
        campos.append(".".join(partes_do_nome))
    return JSONResponse(status_code=422, content={"detail": "O pedido não está no formato esperado.",
                                                  "campos": campos})


@aplicacao.exception_handler(llm_client.IAIndisponivel)
async def avisar_a_pausa_pela_falha_da_ia(pedido: Request, erro: llm_client.IAIndisponivel):
    """A IA real não respondeu (o provedor falhou, ou o limite da operação; ADR-145): a pessoa recebe um aviso claro.

    Recebe: o pedido e a falha. Devolve: 503 ("indisponível agora"), como na pausa pelo teto. A empresa recebe o mesmo
    recado da pausa; o especialista do banco (rotas /api/banco/...) fica sabendo que o provedor falhou. O motivo técnico
    nunca vai para a tela: o registro do servidor guarda o que aconteceu (o limite, o teto ou só o tipo do erro do
    provedor), e o ERRO fica na Telemetria (quando o agente o registrou).
    """
    # O especialista do banco vê que foi a falha do provedor (e não o teto)
    if pedido.url.path.startswith("/api/banco/"):
        recado = llm_client.RECADO_DA_FALHA_PARA_O_BANCO
    else:
        recado = teto_de_gasto.RECADO_PARA_A_EMPRESA
    return JSONResponse(status_code=503, content={"detail": recado})


def ligar_a_retomada_do_teto() -> None:
    """Na partida do servidor: liga a retomada que, a cada 5 minutos, devolve à análise os envios parados pelo teto
    de gasto quando o dia (ou o mês) vira (ADR-139). Só roda com o servidor de verdade: os testes não o ligam."""
    pagina_do_teto_da_ia.ligar_retomada_periodica(auth.conectar)


# A retomada entra na lista do que roda quando o servidor liga
aplicacao.router.on_startup.append(ligar_a_retomada_do_teto)


# O recado para os buscadores (Google, Bing...): não indexar, não seguir links e não guardar cópia de nada do site
AVISO_AOS_BUSCADORES = "noindex, nofollow, noarchive"
# O robots.txt: "nenhum robô, em nenhuma página"
CONTEUDO_DO_ROBOTS = "User-agent: *\nDisallow: /\n"


@aplicacao.get("/robots.txt")
def robots():
    """O robots.txt: pede a todos os buscadores que não visitem nenhuma página do site."""
    return Response(CONTEUDO_DO_ROBOTS, media_type="text/plain")


@aplicacao.middleware("http")
async def porteiro_das_paginas(pedido: Request, chamar_o_proximo):
    """O porteiro: roda antes de cada pedido e barra a página que o perfil não pode ver.

    Recebe: pedido; chamar_o_proximo — a função que entrega o que foi pedido (se o porteiro deixar).
    Devolve: a resposta (a página pedida, ou um desvio para o login ou para a página inicial do perfil).
    "Middleware" é isso: um passo que fica no meio do caminho de todo pedido.
    """
    # O endereço pedido (sem o domínio)
    caminho = pedido.url.path
    # A página inicial do site é o login
    if caminho == "/":
        return RedirectResponse("/login.html", status_code=303)
    # Pedido à API sem ninguém logado: 401 aqui, ANTES de o FastAPI conferir o corpo do pedido. Sem isso, o corpo
    # vazio recebia 422 com o nome de cada campo que a rota espera, entregando o "mapa da API" a quem nem entrou
    # (A-19). Entrar, sair e a data da versão continuam abertos
    if api_sem_login(caminho) and usuario_do_pedido(pedido) is None:
        return JSONResponse(status_code=401, content={"detail": "Sessão expirada. Entre de novo."})
    # Pedido que não é uma página guardada (api, css, js, login): segue direto
    if not pagina_precisa_de_login(caminho):
        return await chamar_o_proximo(pedido)
    # Quem está pedindo
    usuario = usuario_do_pedido(pedido)
    # Ninguém logado: volta para o login
    if usuario is None:
        return RedirectResponse("/login.html", status_code=303)
    # Logado, mas a página não é do perfil dele: vai para a página inicial do próprio perfil
    if not pagina_permitida(usuario.perfil, caminho.lstrip("/")):
        return RedirectResponse("/" + PAGINA_INICIAL_DO_PERFIL[usuario.perfil], status_code=303)
    # A página é do perfil, mas está oculta nesta versão (ADR-148): vai para a tela que fica no lugar dela
    tela_de_volta = tela_no_lugar_da_pagina_oculta(caminho)
    if tela_de_volta:
        return RedirectResponse("/" + tela_de_volta, status_code=303)
    # Tudo certo: entrega a página
    resposta = await chamar_o_proximo(pedido)
    # "no-store": o navegador não pode guardar uma cópia desta página. Sem isso, depois do "Sair", o navegador
    # mostrava a cópia guardada sem perguntar ao servidor, e o porteiro nem ficava sabendo (achado no teste
    # de ponta a ponta)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@aplicacao.middleware("http")
async def avisar_os_buscadores(pedido: Request, chamar_o_proximo):
    """Põe em TODA resposta o aviso de não indexar (cabeçalho X-Robots-Tag), inclusive nos desvios para o login.

    Fica registrado DEPOIS do porteiro de propósito: no FastAPI, o último middleware registrado é o primeiro a
    rodar, então este envolve o porteiro e o aviso vale também quando o porteiro desvia para o login.

    Recebe: pedido; chamar_o_proximo — o resto do caminho (o porteiro e a página). Devolve: a resposta com o aviso.
    Por quê: o site é um projeto e não pode aparecer em buscadores. O robots.txt
    pede isso aos buscadores educados; o cabeçalho vale até para quem chega por um link direto.
    """
    resposta = await chamar_o_proximo(pedido)
    resposta.headers["X-Robots-Tag"] = AVISO_AOS_BUSCADORES
    return resposta


# ---------------- Limite do tamanho do pedido e cabeçalhos de proteção do navegador (ADR-110) ----------------

# Folga para o "envelope" do formulário: além do arquivo, o pedido de envio leva o nome do arquivo, o código do
# progresso e as linhas que separam cada parte (multipart). 64 KB sobram muito para isso
FOLGA_DO_FORMULARIO_EM_BYTES = 64 * 1024


def limite_do_arquivo_em_bytes() -> int:
    """O tamanho máximo de um arquivo enviado, em bytes (LIMITE_UPLOAD_MB do .env; 5 MB = 5.242.880 bytes)."""
    return config.LIMITE_UPLOAD_MB * 1024 * 1024


def mensagem_de_arquivo_grande_demais() -> str:
    """A mesma frase da leitura do arquivo (services/ingestao.py). Ex.: "Arquivo maior que o limite de 5 MB."."""
    return f"Arquivo maior que o limite de {config.LIMITE_UPLOAD_MB} MB."


async def ler_arquivo_ate_o_limite(arquivo: UploadFile) -> bytes:
    """Lê o arquivo enviado só até o limite (mais 1 byte, para saber se passou). Passou: recusa com 400.

    Recebe: arquivo — o arquivo do formulário. Devolve: o conteúdo (bytes).
    Por quê: a porta de entrada (limitar_o_tamanho_do_pedido) já barra o pedido grande; esta é a segunda barreira,
    para o arquivo que passa do limite por menos que a folga do formulário. Nunca lê mais que o limite + 1 byte.
    Exemplo: limite de 5 MB e arquivo de 5,01 MB → lê 5 MB + 1 byte e recusa com "Arquivo maior que o limite de 5 MB.".
    """
    # read(n) lê no máximo n bytes: 1 a mais que o limite basta para saber se o arquivo passou dele
    conteudo = await arquivo.read(limite_do_arquivo_em_bytes() + 1)
    # Passou do limite: recusa com a mesma mensagem da leitura (400, como a recusa de formato)
    if len(conteudo) > limite_do_arquivo_em_bytes():
        raise HTTPException(status_code=400, detail=mensagem_de_arquivo_grande_demais())
    return conteudo


@aplicacao.middleware("http")
async def limitar_o_tamanho_do_pedido(pedido: Request, chamar_o_proximo):
    """Recusa, na porta de entrada, o pedido maior que o limite, ANTES de receber o conteúdo dele.

    Recebe: pedido; chamar_o_proximo — o resto do caminho. Devolve: a resposta, ou a recusa com a mensagem clara.
    Como: todo pedido com conteúdo diz o tamanho no cabeçalho Content-Length (o navegador preenche sozinho), e o
    servidor (uvicorn) não aceita receber mais do que foi dito. Então basta ler o cabeçalho: se passar do limite,
    a resposta sai na hora e o arquivo nem chega a ser guardado. Sem isso, a API receberia o arquivo inteiro (até um
    arquivo de 2 GB ocuparia a memória) e só depois conferiria os 5 MB.
    Pedido com conteúdo "em pedaços" (Transfer-Encoding: chunked) não diz o tamanho; as telas nunca mandam assim,
    então ele é recusado (411: "diga o tamanho").
    """
    # O tamanho que o pedido diz ter (em texto; vazio quando não há conteúdo ou quando vem em pedaços)
    tamanho_declarado = pedido.headers.get("content-length")
    # Conteúdo em pedaços, sem o tamanho: não dá para conferir antes, então recusa
    if tamanho_declarado is None and "chunked" in pedido.headers.get("transfer-encoding", "").lower():
        return JSONResponse({"detail": "O pedido precisa informar o tamanho do conteúdo."}, status_code=411)
    # Tamanho que não é um número inteiro: pedido malformado
    if tamanho_declarado is not None and not tamanho_declarado.isdigit():
        return JSONResponse({"detail": "Pedido malformado."}, status_code=400)
    # O maior pedido aceito: o arquivo máximo mais a folga do formulário
    limite_do_pedido = limite_do_arquivo_em_bytes() + FOLGA_DO_FORMULARIO_EM_BYTES
    # Maior que isso: recusa sem receber o conteúdo (413 é o código da web para "grande demais")
    if tamanho_declarado is not None and int(tamanho_declarado) > limite_do_pedido:
        return JSONResponse({"detail": mensagem_de_arquivo_grande_demais()}, status_code=413)
    # Dentro do limite: segue
    return await chamar_o_proximo(pedido)


# A política de conteúdo (Content-Security-Policy, CSP): diz ao navegador de ONDE cada tipo de conteúdo da página pode
# vir. Se alguém conseguir pôr um <script> numa página (ex.: num nome de funcionário), o navegador se recusa a rodá-lo,
# porque ele não veio de um arquivo do próprio site. É a trava automática que faltava à regra do textContent.
DIRETIVAS_DA_POLITICA_DE_CONTEUDO = (
    # Regra geral: tudo só do próprio site (inclui os pedidos à API, as imagens e o quadro da janela de envio)
    "default-src 'self'",
    # Scripts: só os arquivos .js do próprio site. Script escrito dentro da página ("inline") não roda
    "script-src 'self'",
    # Folhas de estilo: as do site e a das fontes do Google (Google Fonts); bloco <style> dentro da página não vale
    "style-src 'self' https://fonts.googleapis.com",
    # O atributo style="..." nas páginas (ex.: a largura de uma barra): liberado. Estilo muda a aparência, não roda
    # código; e as páginas usam esse atributo em vários lugares
    "style-src-attr 'unsafe-inline'",
    # Fontes: os arquivos de fonte do Google Fonts
    "font-src https://fonts.gstatic.com",
    # Plugins antigos (Flash, applets): nenhum
    "object-src 'none'",
    # A "base" dos endereços relativos não pode ser trocada por um código injetado
    "base-uri 'self'",
    # Formulários só enviam para o próprio site
    "form-action 'self'",
    # Quem pode mostrar nossas páginas dentro de um quadro (iframe): só o próprio site. Não "ninguém" ('none'),
    # porque a janela "Cadastrar funcionários" (front/js/novo_envio.js) mostra cadastrar.html num quadro
    "frame-ancestors 'self'",
)
# As diretivas juntas, no formato do cabeçalho: separadas por "; "
POLITICA_DE_CONTEUDO = "; ".join(DIRETIVAS_DA_POLITICA_DE_CONTEUDO)
# HSTS: "nos próximos 365 dias (em segundos), este site só abre por https", mesmo que alguém digite http://
OBRIGAR_HTTPS = "max-age=31536000"


@aplicacao.middleware("http")
async def proteger_o_navegador(pedido: Request, chamar_o_proximo):
    """Põe em TODA resposta os cabeçalhos que mandam o navegador se proteger (registrado por último: é o de fora).

    Recebe: pedido; chamar_o_proximo — o resto do caminho. Devolve: a resposta com os cabeçalhos.
    Os cabeçalhos, em linguagem simples:
    - Content-Security-Policy: de onde a página pode carregar código, estilo e fonte (lista acima);
    - X-Frame-Options SAMEORIGIN: só o próprio site pode mostrar nossas páginas num quadro. Impede um site falso de
      mostrar o nosso "por baixo" de botões dele, para a pessoa clicar sem saber (o golpe chamado clickjacking);
    - X-Content-Type-Options nosniff: o navegador não "adivinha" o tipo de um arquivo. Um arquivo de texto não vira
      script só porque parece um;
    - Referrer-Policy same-origin: ao sair do site por um link, o endereço de onde a pessoa veio não vai junto;
    - Strict-Transport-Security (só em https): o navegador passa a usar sempre https com o site. Em http (a máquina
      local), o cabeçalho não vale e não é enviado.
    """
    try:
        # Deixa o pedido seguir e pega a resposta (a página, o JSON da API ou um desvio para o login)
        resposta = await chamar_o_proximo(pedido)
    except Exception:
        # Algo quebrou por dentro (erro 500). O detalhe fica só no registro do servidor; a pessoa recebe a frase
        # padrão, e esta resposta também ganha os cabeçalhos abaixo (antes, o 500 saía sem eles, B-13)
        registro_de_avisos.exception("Erro interno em %s", pedido.url.path)
        resposta = PlainTextResponse("Internal Server Error", status_code=500)
        # O aviso aos buscadores também (o middleware dele fica por dentro deste e não chegou a rodar)
        resposta.headers["X-Robots-Tag"] = AVISO_AOS_BUSCADORES
    # Toda resposta da API pode trazer dado pessoal (CPF, salário): o navegador não guarda cópia (B-09)
    if pedido.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"
    # De onde a página pode carregar código, estilo e fonte
    resposta.headers["Content-Security-Policy"] = POLITICA_DE_CONTEUDO
    # Só o próprio site mostra nossas páginas num quadro (o mesmo que o frame-ancestors, para navegadores antigos)
    resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
    # O navegador não adivinha o tipo do arquivo
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    # O endereço de origem só vai em pedidos ao próprio site
    resposta.headers["Referrer-Policy"] = "same-origin"
    # https (direto ou pelo balanceador de carga, com --proxy-headers no Dockerfile): obriga https daqui em diante
    if pedido.url.scheme == "https":
        resposta.headers["Strict-Transport-Security"] = OBRIGAR_HTTPS
    return resposta


@aplicacao.middleware("http")
async def conferir_sempre_os_arquivos_do_front(pedido: Request, chamar_o_proximo):
    """Faz o navegador conferir com o servidor, a cada abertura, se o .js ou o .css mudou.

    Por quê: sem nenhuma instrução, o navegador guardava o acompanhar.js antigo e a tela nova
    não aparecia depois de um ajuste. "no-cache" não proíbe guardar: obriga a perguntar "mudou?" antes de usar a cópia
    (o servidor responde "não mudou" com a etiqueta ETag, sem mandar o arquivo de novo, então fica leve).
    """
    resposta = await chamar_o_proximo(pedido)
    caminho = pedido.url.path
    if caminho.endswith(".js") or caminho.endswith(".css"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


def mensagem_de_login_bloqueado(minutos: int) -> str:
    """O aviso de login bloqueado, com os minutos que faltam. Ex.: 12 → "... Tente de novo em 12 minutos."

    Por que um aviso claro, e não a mensagem de sempre ("Usuário ou senha incorretos."): com a mensagem de sempre, a
    pessoa que lembrou a senha certa leria "incorretos" e acharia que a senha mudou. O aviso não revela se o usuário
    existe, porque o bloqueio vale para qualquer login digitado, exista ele ou não (services/tentativas_de_login.py).
    """
    # "1 minuto" no singular; o resto no plural
    palavra_minutos = "minutos"
    if minutos == 1:
        palavra_minutos = "minuto"
    return (f"Muitas tentativas seguidas com este usuário. Por segurança, o acesso ficou bloqueado. "
            f"Tente de novo em {minutos} {palavra_minutos}.")


def recusar_se_bloqueado(conexao, login_digitado: str) -> None:
    """Se o login está bloqueado por senhas erradas, recusa o pedido com 429 e o aviso dos minutos que faltam.

    Recebe: conexao; login_digitado. Devolve: nada (se não está bloqueado, não faz nada).
    429 é o código da web para "muitos pedidos"; o cabeçalho Retry-After diz ao navegador em quantos segundos tentar.
    """
    # Quantos minutos faltam para o fim do bloqueio (0: não está bloqueado)
    minutos = tentativas_de_login.minutos_de_bloqueio(conexao, login_digitado)
    # Bloqueado: recusa, sem conferir a senha
    if minutos > 0:
        raise HTTPException(status_code=429, detail=mensagem_de_login_bloqueado(minutos),
                            headers={"Retry-After": str(minutos * 60)})


def conferir_usuario_e_senha(conexao, login_digitado: str, senha: str):
    """Confere o bloqueio, o usuário e a senha, e conta os erros. Devolve o usuário; recusado, levanta 401 ou 429, ou
    403 com a senha certa, mas o acesso suspenso (ADR-146) ou a senha provisória vencida (ADR-154).

    Recebe: conexao; login_digitado (já sem espaços nas pontas); senha.
    A ordem importa: o bloqueio é conferido ANTES da senha. Durante o bloqueio, nem a senha certa entra; senão quem
    tenta adivinhar continuaria tentando e saberia quando acertou.
    """
    # Login bloqueado: recusa sem nem olhar a senha
    recusar_se_bloqueado(conexao, login_digitado)
    # Confere o login e a senha; desativado, inexistente ou senha errada devolve None
    usuario = auth.autenticar(conexao, login_digitado, senha)
    # Recusado: anota o erro (no 5º seguido, o login fica bloqueado)
    if usuario is None:
        tentativas_de_login.registrar_erro(conexao, login_digitado)
        # Se este foi o 5º erro, o bloqueio começou agora: a pessoa já fica sabendo
        recusar_se_bloqueado(conexao, login_digitado)
        # Senão, a mesma mensagem para qualquer erro (não revela se o usuário existe)
        raise HTTPException(status_code=401, detail=MENSAGEM_LOGIN_RECUSADO)
    # Senha certa, mas o acesso da empresa está suspenso (sem uso há mais de 90 dias, ou vencido): 403 com o motivo
    # e o caminho (ADR-146). Vem DEPOIS da senha: quem não sabe a senha não descobre que o acesso está suspenso
    motivo_da_suspensao = auth.motivo_do_acesso_suspenso(conexao, usuario.login)
    if motivo_da_suspensao is not None:
        raise HTTPException(status_code=403, detail=motivo_da_suspensao)
    # Senha certa, mas provisória e vencida (ela vale por 48 horas, ADR-154): 403 com o aviso, sem criar a sessão e
    # sem contar como senha errada (a pessoa digitou a senha certa). Vem DEPOIS da senha, pelo mesmo motivo acima
    if auth.senha_provisoria_venceu(usuario):
        raise HTTPException(status_code=403, detail=auth.MENSAGEM_SENHA_PROVISORIA_VENCIDA)
    # Deu certo: zera o contador de erros deste login
    tentativas_de_login.registrar_acerto(conexao, usuario.login)
    # Grava o dia deste acesso (e a validade de 12 meses, para quem ainda não tinha)
    auth.registrar_acesso(conexao, usuario.login)
    return usuario


@aplicacao.post("/api/entrar")
def entrar(dados: PedidoDeEntrada, pedido: Request):
    """Confere usuário e senha, cria a sessão e grava o cookie. Devolve quem entrou e para onde ir.

    Recebe: dados — usuário e senha (JSON); pedido — para saber se a conexão é segura (https).
    Devolve: { login, perfil, empresa_id, pagina_inicial }; erro 401 com a mensagem única (senha errada, usuário
    que não existe ou desativado) ou 429 depois de 5 senhas erradas seguidas (login bloqueado por 15 minutos).
    """
    # Abre o banco com a tabela de usuários pronta
    conexao = auth.conectar()
    # try/finally: a conexão fecha mesmo quando o login é recusado
    try:
        # Confere o bloqueio, o usuário e a senha (o login sem espaços nas pontas); recusado, levanta 401 ou 429
        usuario = conferir_usuario_e_senha(conexao, dados.usuario.strip(), dados.senha)
        # Deu certo: cria a sessão (o banco guarda só o hash do ingresso)
        ingresso = sessoes.criar_sessao(conexao, usuario.login)
    finally:
        conexao.close()
    # A resposta em JSON com os dados públicos de quem entrou (montada à mão para poder gravar o cookie)
    resposta_json = JSONResponse(dados_publicos_do_usuario(usuario))
    # O cookie: de sessão (sem max_age, o navegador o apaga ao fechar; no servidor, a sessão vence em 8 horas de
    # qualquer jeito), httponly (o JavaScript não lê), SameSite=Strict (não vai em pedidos vindos de outro site) e
    # secure só em https (no computador local, sem https, o navegador recusaria o cookie)
    resposta_json.set_cookie(
        key=sessoes.NOME_COOKIE,
        value=ingresso,
        httponly=True,
        samesite="strict",
        secure=pedido.url.scheme == "https",
        path="/",
    )
    # Devolve a resposta com o cookie
    return resposta_json


@aplicacao.get("/api/eu")
def quem_sou_eu(pedido: Request):
    """Diz quem está logado. Sem sessão válida, responde 401.

    Recebe: pedido (traz o cookie). Devolve: { login, perfil, empresa_id, pagina_inicial }.
    """
    # Quem é o dono do cookie
    usuario = usuario_do_pedido(pedido)
    # Ninguém logado
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre de novo.")
    # Os dados públicos
    return dados_publicos_do_usuario(usuario)


@aplicacao.get("/api/sair")
def sair(pedido: Request):
    """Cancela a sessão no banco, apaga o cookie e volta ao login.

    Recebe: pedido (traz o cookie). Devolve: um desvio para a página de login.
    É um GET para funcionar num link simples ("Sair"). Um site de fora não consegue deslogar ninguém,
    porque o cookie SameSite=Strict não vai junto em pedidos vindos de outro site.
    """
    # Abre o banco e cancela o ingresso do cookie (se houver)
    conexao = auth.conectar()
    sessoes.encerrar_sessao(conexao, pedido.cookies.get(sessoes.NOME_COOKIE))
    conexao.close()
    # Volta ao login e apaga o cookie do navegador
    resposta = RedirectResponse("/login.html", status_code=303)
    resposta.delete_cookie(sessoes.NOME_COOKIE, path="/")
    return resposta


@aplicacao.get("/api/versao")
def versao():
    """O rótulo do rodapé com a data da versão que está rodando (ADR-133). Não exige login.

    Por que sem login: a tela de login também mostra o rótulo. A rota devolve só o texto pronto, sem nenhum dado de
    empresa nem o código do commit.
    Devolve: {"texto": "Atualizado em 29/09/2026 às 14:30"} ou {"texto": null}, quando não há data confiável (aí o
    rótulo não aparece).
    """
    # O texto a partir da data que o servidor leu ao subir (variável, arquivo da imagem ou Git)
    return versao_da_aplicacao.rotulo_da_versao()


def usuario_da_empresa(pedido: Request):
    """Confere que quem pede está logado E é do perfil EMPRESA. Devolve o usuário (com a empresa dele).

    Recebe: pedido. Devolve: o usuário. Levanta 401 (sem login) ou 403 (outro perfil).
    Por quê: as rotas /api/empresa/... devolvem dados de funcionários; só o RH da própria empresa pode vê-los.
    """
    # Quem é o dono do cookie
    usuario = usuario_do_pedido(pedido)
    # Ninguém logado
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre de novo.")
    # Logado, mas não é da empresa (ex.: especialista do banco)
    if usuario.perfil != Perfil.EMPRESA:
        raise HTTPException(status_code=403, detail="Esta consulta é só do Portal Empresa.")
    # Com a senha provisória, nada de dados até trocá-la
    exigir_senha_definitiva(usuario)
    # É da empresa
    return usuario


@aplicacao.get("/api/empresa/resumo")
def resumo_da_empresa(pedido: Request):
    """Os números do alto de "Acompanhar cadastros": cadastrados, envios, em andamento, com pendência, as pessoas em
    análise pelo banco (o 2º cartão) e as contas.

    A empresa vem da SESSÃO, nunca do pedido: não há como pedir os números de outra empresa. As contas abertas são o
    total da empresa inteira (a conta de cada funcionário fica na lista, ADR-102). A tela pede estes números de novo a
    cada 30 segundos e quando a pessoa volta para a aba.
    """
    # Só o RH da empresa
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, consulta e fecha
    conexao = auth.conectar()
    resumo = acompanhamento.resumo_da_empresa(conexao, usuario.empresa_id)
    # O 2º cartão: as PESSOAS cujo envio está com o banco (o mesmo total do filtro "Em análise" da lista)
    resumo["pessoas_em_analise"] = acompanhamento.pessoas_em_analise_pelo_banco(conexao, usuario.empresa_id)
    resumo["contas"] = contas_abertas.contas_para_a_empresa(conexao, usuario.empresa_id)
    conexao.close()
    return resumo


@aplicacao.get("/api/empresa/envios/{processamento_id}/linha_do_tempo")
def linha_do_tempo_do_envio(processamento_id: str, pedido: Request):
    """As etapas de um envio da empresa logada, com as datas (o histórico da ficha do funcionário)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: acompanhamento.linha_do_tempo_do_envio(conexao, usuario.empresa_id,
                                                                                 processamento_id))


@aplicacao.get("/api/empresa/envios/pagina")
def pagina_de_envios(pedido: Request, inicio: int = Query(0, ge=0, le=MAIOR_INICIO_DE_PAGINA),
                     quantidade: int = Query(5, ge=1, le=50)):
    """Uma página dos envios da empresa logada: {envios, total, inicio, quantidade} ("Mostrar mais envios").

    Os envios vêm do mais recente para o mais antigo, sem o nome dos arquivos. Não existe a rota da lista inteira:
    uma empresa pode ter centenas de envios (ADR-86).

    Ex.: /api/empresa/envios/pagina?inicio=5&quantidade=5 → do 6º ao 10º envio. Quantidade de 1 a 50 (senão, 400).
    """
    # Só o RH da empresa; a empresa vem da sessão
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: acompanhamento.pagina_de_envios(conexao, usuario.empresa_id, inicio,
                                                                         quantidade))


@aplicacao.get("/api/empresa/funcionarios")
def funcionarios_da_empresa(pedido: Request):
    """Todos os funcionários da empresa logada (cadastrados, em análise e pendentes), com o CPF inteiro.

    Cada pessoa traz "situacao" e "pendencia"; só os cadastrados têm "id" (a ficha), e todas têm "id_para_baixar" (o
    download traz a grade inteira, ADR-155). Cada abertura da lista fica registrada (quem, quando e quantas pessoas;
    nunca o CPF), como a ficha e o download.
    """
    # Só o RH da empresa
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, consulta, registra o acesso e fecha
    conexao = auth.conectar()
    funcionarios = acompanhamento.todos_os_funcionarios_da_empresa(conexao, usuario.empresa_id)
    acompanhamento.registrar_acesso(conexao, usuario.empresa_id, usuario.login, acompanhamento.ACESSO_LISTA,
                                    len(funcionarios))
    conexao.close()
    # Resposta com o CPF inteiro: o navegador não pode guardar cópia
    return JSONResponse(funcionarios, headers={"Cache-Control": "no-store"})


@aplicacao.get("/api/empresa/colunas_da_consulta")
def colunas_da_consulta_de_funcionarios(pedido: Request):
    """As colunas da grade de consulta: uma por campo do parâmetro vigente, com rótulo, grupo e se é obrigatório
    (ADR-111). A tela usa para montar o cabeçalho e marcar as colunas obrigatórias."""
    usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: acompanhamento.colunas_da_consulta(conexao))


@aplicacao.get("/api/empresa/pendencias")
def pendencias_da_empresa(pedido: Request):
    """O que a empresa logada ainda precisa corrigir ou confirmar (achados em aberto do Validador)."""
    # Só o RH da empresa
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, consulta e fecha
    conexao = auth.conectar()
    pendencias = acompanhamento.pendencias_da_empresa(conexao, usuario.empresa_id)
    conexao.close()
    return pendencias


@aplicacao.get("/api/empresa/envios-parados-nas-colunas")
def envios_parados_nas_colunas(pedido: Request):
    """Os envios da empresa logada que esperam a conferência das colunas (ADR-127): o Acompanhar avisa, com o botão
    para continuar, e nunca diz "Tudo em dia" com um deles."""
    # Só o RH da empresa, e só os envios dela
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, consulta e fecha
    conexao = auth.conectar()
    parados = acompanhamento.envios_parados_nas_colunas(conexao, usuario.empresa_id)
    conexao.close()
    return parados


@aplicacao.get("/api/empresa/pendencias/resolvidas")
def pendencias_resolvidas_da_empresa(pedido: Request):
    """As pendências que a empresa logada resolveu conversando com a IA, com a conversa guardada (ADR-120), nos
    envios que ainda não foram ao banco."""
    # Só o RH da empresa, e só as conversas dos envios dela
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, consulta e fecha
    conexao = auth.conectar()
    resolvidas = conversas_das_pendencias.resolvidas_da_empresa(conexao, usuario.empresa_id)
    conexao.close()
    return resolvidas


@aplicacao.get("/api/empresa/funcionarios/{identificador}")
def ficha_do_funcionario(identificador: str, pedido: Request):
    """A ficha de uma pessoa com o CPF inteiro (só da empresa da sessão). Cada abertura fica registrada."""
    # Só o RH da empresa
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, busca e fecha (a conexão fecha mesmo se der erro)
    conexao = auth.conectar()
    try:
        ficha = acompanhamento.ficha_do_funcionario(conexao, usuario.empresa_id, usuario.login, identificador)
    except KeyError:
        # Pessoa de outra empresa (ou inexistente): a mesma resposta, sem revelar nada
        raise HTTPException(status_code=404, detail="Funcionário não encontrado.")
    finally:
        conexao.close()
    # Resposta com o CPF inteiro: o navegador não pode guardar cópia
    return JSONResponse(ficha, headers={"Cache-Control": "no-store"})


class PedidoDeDownload(BaseModel):
    """As pessoas que estão na tela (com os filtros aplicados), pelos identificadores."""

    identificadores: list[str] = Field(max_length=100_000)   # teto para ninguém mandar uma lista sem fim


@aplicacao.post("/api/empresa/funcionarios/baixar")
def baixar_funcionarios(dados: PedidoDeDownload, pedido: Request):
    """O CSV (para o Excel) das pessoas pedidas, com o CPF inteiro. Cada download fica registrado com quantas linhas."""
    # Só o RH da empresa
    usuario = usuario_da_empresa(pedido)
    # Abre o banco, monta o arquivo e fecha
    conexao = auth.conectar()
    try:
        conteudo = acompanhamento.lista_para_baixar(conexao, usuario.empresa_id, usuario.login, dados.identificadores)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=mensagem_para_a_pessoa(erro))
    finally:
        conexao.close()
    # O arquivo: o navegador baixa com o nome "funcionarios.csv" e não guarda cópia
    cabecalhos = {"Content-Disposition": "attachment; filename=\"funcionarios.csv\"", "Cache-Control": "no-store"}
    return Response(content=conteudo, media_type="text/csv; charset=utf-8", headers=cabecalhos)


class PedidoDeCorrecao(BaseModel):
    """O que a tela manda para corrigir um dado de uma pendência."""

    processamento_id: str = Field(max_length=TAMANHO_DO_CODIGO_DO_ENVIO)  # o envio
    linha: int                                  # a linha do arquivo
    campo: str = Field(max_length=100)          # o campo do layout (ex.: "data_admissao")
    novo_valor: str = Field(max_length=300)     # o valor correto, digitado do jeito brasileiro
    motivo: str = Field(max_length=300)         # por que corrigiu (obrigatório)


class PedidoDeConfirmacao(BaseModel):
    """O que a tela manda para confirmar que um valor em alerta está certo."""

    processamento_id: str = Field(max_length=TAMANHO_DO_CODIGO_DO_ENVIO)  # o envio
    regra_id: str = Field(max_length=120)       # a regra do alerta (ex.: "RENDA_FORA_DA_FAIXA")
    linha: int | None                           # a linha do arquivo (None: alerta do arquivo inteiro)
    justificativa: str = Field(max_length=300)  # por que está certo (obrigatória)


def executar_acao(acao):
    """Roda uma ação dos serviços (dos dois portais) e traduz os erros em respostas claras.

    Recebe: acao — uma função que faz o trabalho (recebe a conexão aberta aqui) e pode devolver um resultado.
    Devolve: o resultado da ação, ou {"ok": True} se ela não devolver nada. Erro de regra (ValueError) vira 400
    com a mensagem para a pessoa; envio que não é da empresa (KeyError) vira 404, sem dizer se o envio existe
    em outra empresa.
    """
    # Abre o banco
    conexao = auth.conectar()
    # try/finally: a conexão fecha mesmo se der erro
    try:
        resultado = acao(conexao)
    except PermissionError:
        # Operação fora do perfil de quem pediu (services/permissoes.py)
        raise HTTPException(status_code=403, detail="Operação não permitida para o seu perfil.")
    except KeyError:
        raise HTTPException(status_code=404, detail="Envio não encontrado.")
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=mensagem_para_a_pessoa(erro))
    finally:
        conexao.close()
    # Sem resultado: só confirma que deu certo
    if resultado is None:
        return {"ok": True}
    return resultado


@aplicacao.post("/api/empresa/pendencias/corrigir")
def corrigir_pendencia(dados: PedidoDeCorrecao, pedido: Request):
    """Corrige um dado de uma pendência: registra, aplica e valida o envio de novo (só o RH da própria empresa)."""
    # Só o RH da empresa; a empresa vem da sessão
    usuario = usuario_da_empresa(pedido)

    def acao(conexao):
        # O serviço confere que o envio é desta empresa antes de mexer em qualquer coisa
        acompanhamento.corrigir_pendencia(conexao, usuario.empresa_id, usuario.login, dados.processamento_id,
                                          dados.linha, dados.campo, dados.novo_valor, dados.motivo)

    return executar_acao(acao)


class PedidoDePreencherParaTodos(BaseModel):
    """O que a tela manda para preencher um campo em todos do envio que estão sem ele."""

    processamento_id: str = Field(max_length=TAMANHO_DO_CODIGO_DO_ENVIO)  # o envio
    campo: str = Field(max_length=100)              # o campo do layout (ex.: "cnpj_empregador")
    novo_valor: str = Field(max_length=300)         # o valor, igual para todos
    motivo: str = Field(max_length=300)             # por que (obrigatório)


@aplicacao.post("/api/empresa/pendencias/preencher_para_todos")
def preencher_para_todos(dados: PedidoDePreencherParaTodos, pedido: Request):
    """Preenche um campo com o mesmo valor em todos do envio que estão sem ele (só o RH da própria empresa).

    Devolve: {"preenchidos": quantos funcionários}. Quem já tem o campo não muda.
    """
    # Só o RH da empresa; a empresa vem da sessão
    usuario = usuario_da_empresa(pedido)

    def acao(conexao):
        # O serviço confere que o envio é desta empresa, padroniza o valor e valida o envio de novo
        quantidade = acompanhamento.preencher_para_todos(conexao, usuario.empresa_id, usuario.login,
                                                         dados.processamento_id, dados.campo, dados.novo_valor,
                                                         dados.motivo)
        return {"preenchidos": quantidade}

    return executar_acao(acao)


@aplicacao.post("/api/empresa/pendencias/confirmar")
def confirmar_pendencia(dados: PedidoDeConfirmacao, pedido: Request):
    """Confirma que um valor em alerta está certo, com justificativa (só o RH da própria empresa)."""
    # Só o RH da empresa; a empresa vem da sessão
    usuario = usuario_da_empresa(pedido)

    def acao(conexao):
        # O serviço confere que o envio é desta empresa e que o alerta existe
        acompanhamento.confirmar_pendencia(conexao, usuario.empresa_id, usuario.login, dados.processamento_id,
                                           dados.regra_id, dados.linha, dados.justificativa)

    return executar_acao(acao)


# ---------------- Cadastrar funcionários (services/cadastro.py) ----------------

@aplicacao.post("/api/empresa/cadastro/enviar")
async def enviar_arquivo(pedido: Request, arquivo: UploadFile,
                        pedido_de_progresso: str = Form("", max_length=TAMANHO_DO_CODIGO_DO_ENVIO)):
    """Recebe o arquivo da empresa e roda o fluxo até a IA propor o mapeamento. Devolve a leitura.

    "UploadFile": o arquivo vem no formato de formulário do navegador (multipart). O tamanho máximo é conferido na
    porta de entrada (limitar_o_tamanho_do_pedido), de novo aqui ao ler e mais uma vez na leitura
    (services/ingestao.py), sempre com a mesma mensagem para a empresa (ADR-110).
    pedido_de_progresso: o código que a tela sorteou para perguntar o progresso enquanto espera (ADR-95).
    Por que run_in_threadpool: a leitura pode levar dezenas de segundos (IA real); rodando numa linha de execução à
    parte, o servidor continua atendendo os outros pedidos, inclusive o do progresso.
    """
    # Só o RH da empresa; a empresa vem da sessão
    usuario = usuario_da_empresa(pedido)
    # O conteúdo do arquivo, lido só até o limite de tamanho
    conteudo = await ler_arquivo_ate_o_limite(arquivo)

    def acao(conexao):
        # Sem código válido, a leitura roda sem anotar o progresso
        if not progresso.codigo_valido(pedido_de_progresso):
            return cadastro.enviar_arquivo(conexao, usuario.empresa_id, usuario.login, conteudo, arquivo.filename or "")
        bilhete = progresso.comecar(pedido_de_progresso, usuario.login)
        try:
            return cadastro.enviar_arquivo(conexao, usuario.empresa_id, usuario.login, conteudo, arquivo.filename or "")
        finally:
            progresso.terminar(bilhete)

    return await run_in_threadpool(executar_acao, acao)


@aplicacao.get("/api/empresa/cadastro/progresso/{codigo}")
def progresso_do_envio(codigo: str, pedido: Request):
    """A frase do momento do envio em andamento (ex.: "A IA leu 5 de 12 pessoas."), só para quem enviou."""
    usuario = usuario_da_empresa(pedido)
    texto = progresso.frase_do_pedido(codigo, usuario.login)
    if texto is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return {"texto": texto}


@aplicacao.get("/api/empresa/cadastro/{processamento_id}")
def leitura_do_envio(processamento_id: str, pedido: Request):
    """Onde o envio está e o que a IA leu (colunas, campos propostos, o que falta decidir)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.leitura_do_envio(conexao, usuario.empresa_id,
                                                                             processamento_id))


class PedidoDeAceite(BaseModel):
    """As escolhas da pessoa no mapeamento: {coluna: campo}, só das colunas que ela mudou ou decidiu."""

    escolhas: dict[str, str | None] = {}


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/aceitar")
def aceitar_mapeamento(processamento_id: str, dados: PedidoDeAceite, pedido: Request):
    """A pessoa aceita o mapeamento: o fluxo padroniza e valida. Devolve a leitura depois."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.aceitar_mapeamento(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.escolhas))


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/tentar_de_novo")
def tentar_de_novo(processamento_id: str, pedido: Request):
    """Retoma o envio parado em "tentar de novo" (a IA pausada pelo teto de gasto, ou uma etapa que falhou; ADR-131).

    Só a empresa dona do envio (404 para outra). Envio em outra etapa: 400. Teto ainda atingido: 503 com o recado, e
    o envio continua guardado. Devolve a leitura do envio depois de retomar.
    """
    # Só o RH da empresa; a empresa vem da sessão, nunca do pedido
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.tentar_de_novo(conexao, usuario.empresa_id, processamento_id))


class PedidoDeEnvioAoBanco(BaseModel):
    """O clique "Enviar ao banco": se a pessoa marcou "Conferi a lista" (fica registrado para o banco ver)."""

    conferi_a_lista: bool = False


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/homologar")
def homologar_envio(processamento_id: str, pedido: Request, dados: PedidoDeEnvioAoBanco | None = None):
    """O clique final, "Enviar ao banco": sem pendências, o envio vai para a avaliação do banco. Devolve a leitura."""
    usuario = usuario_da_empresa(pedido)
    conferiu = dados is not None and dados.conferi_a_lista
    return executar_acao(lambda conexao: cadastro.homologar(conexao, usuario.empresa_id, usuario.login,
                                                            processamento_id, conferiu_a_lista=conferiu))


class PedidoDeFormato(BaseModel):
    """A decisão de formato de uma coluna inteira: "DMY", "MDY" ou "zeros:N"."""

    coluna: str = Field(max_length=200)
    decisao: str = Field(max_length=20)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/formato")
def decidir_formato(processamento_id: str, dados: PedidoDeFormato, pedido: Request):
    """A empresa decide o formato de uma coluna (datas ou zeros da matrícula); o fluxo padroniza de novo."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.decidir_formato(conexao, usuario.empresa_id, processamento_id,
                                                                  dados.coluna, dados.decisao))


@aplicacao.get("/api/empresa/cadastro/{processamento_id}/lista")
def lista_para_conferir(processamento_id: str, pedido: Request):
    """A lista do jeito que vai para o banco, para a empresa conferir antes de enviar."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.lista_para_conferir(conexao, usuario.empresa_id, processamento_id))


@aplicacao.get("/api/empresa/cadastro/{processamento_id}/previa")
def previa_das_pessoas(processamento_id: str, pedido: Request):
    """As pessoas do envio com os valores como o agente leu: a 1ª aba do resultado de "Cadastrar funcionários".

    Só leitura: nada é gravado. Vale antes do aceite das colunas (a padronização é calculada na hora, com as colunas
    que o agente reconheceu) e depois dele (os dados atuais do envio). Só a empresa dona do envio: sem login, 401; o
    banco, 403; envio de outra empresa, 404, sem dizer se ele existe.
    """
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.previa_da_lista(conexao, usuario.empresa_id, processamento_id))


class PedidoDeCorrecaoNaLista(BaseModel):
    """Um valor corrigido na conferência da lista: a linha, o campo e o valor certo."""

    linha: int
    campo: str = Field(max_length=100)
    valor: str = Field(default="", max_length=300)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/lista/corrigir")
def corrigir_na_lista(processamento_id: str, dados: PedidoDeCorrecaoNaLista, pedido: Request):
    """A empresa corrige um valor na conferência: registrado com quem corrigiu, aplicado e revalidado."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.corrigir_na_conferencia(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.linha, dados.campo, dados.valor))


@aplicacao.get("/api/empresa/prontos_para_o_banco")
def prontos_para_o_banco(pedido: Request):
    """Os envios da empresa sem pendência, prontos para ir ao banco (a lista pendente da empresa)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.envios_prontos_para_o_banco(conexao, usuario.empresa_id))


class PedidoDeEnvioAoBanco(BaseModel):
    """"Enviar ao banco" em Acompanhar cadastros: a pessoa marcou "Conferi a lista"?"""

    conferi_a_lista: bool = False


@aplicacao.post("/api/empresa/enviar_ao_banco")
def enviar_ao_banco(dados: PedidoDeEnvioAoBanco, pedido: Request):
    """Manda ao banco, de uma vez, todos os envios prontos da empresa. Devolve {envios, pessoas}."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.enviar_prontos_ao_banco(
        conexao, usuario.empresa_id, usuario.login, dados.conferi_a_lista))


class PedidoDeConfirmacaoNaLista(BaseModel):
    """"Está certo assim" na conferência: o alerta (regra e linha) e, se a pessoa quiser, o porquê."""

    regra_id: str = Field(max_length=120)
    linha: int
    justificativa: str = Field(default="", max_length=300)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/lista/confirmar")
def confirmar_na_lista(processamento_id: str, dados: PedidoDeConfirmacaoNaLista, pedido: Request):
    """A empresa confirma um alerta ou responde uma pergunta da IA na conferência; o envio é revalidado."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.confirmar_na_conferencia(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.regra_id, dados.linha, dados.justificativa))


class PedidoAoAssistente(BaseModel):
    """Uma mensagem ao Assistente de Correção sobre UMA pendência (a regra e a linha; o texto dela vem do servidor)."""

    regra_id: str = Field(max_length=120)
    linha: int | None = None
    mensagem: str = Field(max_length=assistente_na_tela.TAMANHO_MAXIMO_DA_MENSAGEM)
    # A resposta no cartão do grupo vale para todas as pessoas com o mesmo valor (ADR-120; o grupo é refeito no
    # servidor)
    em_grupo: bool = False
    # O campo da pendência: a mesma regra aparece uma vez por campo na mesma linha (ex.: 11 colunas faltando no arquivo)
    campo: str | None = Field(default=None, max_length=80)


@aplicacao.get("/api/empresa/cadastro/{processamento_id}/ficha")
def ficha_da_pessoa_do_envio(processamento_id: str, pedido: Request, linha: int | None = None):
    """A ficha completa de uma pessoa do envio, aberta pelo cartão da pendência, com os campos considerados e os que
    têm pendência (ADR-120). Só a empresa dona do envio; cada abertura fica registrada.

    A linha é opcional na assinatura para o login ser conferido ANTES (sem login: 401; banco: 403), e só depois a
    falta da linha vira 400.
    """
    usuario = usuario_da_empresa(pedido)
    if linha is None:
        raise HTTPException(status_code=400, detail="Diga de qual linha é a ficha.")
    return executar_acao(lambda conexao: ficha_da_pendencia.ficha_da_linha(
        conexao, usuario.empresa_id, usuario.login, processamento_id, linha))


@aplicacao.get("/api/empresa/cadastro/{processamento_id}/pessoas_para_informar")
def lista_pessoa_a_pessoa(processamento_id: str, pedido: Request, campo: str | None = None):
    """As pessoas do envio para a lista "Informar pessoa a pessoa" do cartão da coluna que o arquivo inteiro não
    trouxe (ADR-124): a linha, o nome e a matrícula de cada uma.

    O campo é opcional na assinatura para o login ser conferido ANTES (sem login: 401; banco: 403), e só depois a
    falta do campo vira 400.
    """
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: assistente_na_tela.pessoas_para_informar(
        conexao, usuario.empresa_id, processamento_id, campo or ""))


class ValorDeUmaPessoa(BaseModel):
    """O valor de uma pessoa na lista "Informar pessoa a pessoa": a linha do arquivo e o valor (vazio = sem valor)."""

    linha: int
    valor: str = Field(default="", max_length=300)


class PedidoPessoaAPessoa(BaseModel):
    """A lista "Informar pessoa a pessoa" de um cartão (ADR-124): o campo e o valor de cada pessoa."""

    campo: str = Field(max_length=80)
    valores: list[ValorDeUmaPessoa] = Field(max_length=5000)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/informar_por_pessoa")
def salvar_lista_pessoa_a_pessoa(processamento_id: str, dados: PedidoPessoaAPessoa, pedido: Request):
    """Salva o valor de cada pessoa (ADR-124): um lote com um Desfazer só; a resposta é uma rodada da conversa do
    cartão, com o "Pronto: ..." e o Desfazer."""
    usuario = usuario_da_empresa(pedido)
    # O que a tela mandou, como a lista que o serviço recebe
    valores = []
    for item in dados.valores:
        valores.append({"linha": item.linha, "valor": item.valor})
    return executar_acao(lambda conexao: assistente_na_tela.informar_por_pessoa(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.campo, valores))


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/assistente")
def conversar_com_o_assistente(processamento_id: str, dados: PedidoAoAssistente, pedido: Request):
    """A empresa conversa com a IA sobre uma pendência; quando ela explica o que quer, a IA já aplica (com Desfazer)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: assistente_na_tela.conversar(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.regra_id, dados.linha, dados.mensagem,
        em_grupo=dados.em_grupo, campo=dados.campo))


class RespostaDaConfirmacao(BaseModel):
    """A resposta da pessoa à pergunta "Confirma que...?" do agente: a retirada proposta e se ela confirma."""

    correcao_id: str = Field(max_length=40)
    confirmar: bool


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/assistente/confirmar")
def confirmar_retirada_do_assistente(processamento_id: str, dados: RespostaDaConfirmacao, pedido: Request):
    """ "Sim, não cadastrar" / "Sim, deixar em branco" (aplica) ou "Cancelar" (nada muda); as duas vão para a trilha."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: assistente_na_tela.confirmar_retirada(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.correcao_id, dados.confirmar))


class RespostaDaColuna(BaseModel):
    """A resposta da pessoa à pergunta "Confirma que a coluna X é a informação Y?" (ADR-124): o campo da pendência, a
    coluna indicada e se ela confirma."""

    campo: str = Field(max_length=80)
    coluna: str = Field(max_length=200)
    confirmar: bool


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/assistente/usar_coluna")
def confirmar_a_coluna_do_assistente(processamento_id: str, dados: RespostaDaColuna, pedido: Request):
    """ "Sim, usar como CPF" (a coluna passa para o campo, a leitura é refeita, com Desfazer) ou "Cancelar" (nada
    muda); as duas vão para a trilha. O servidor confere de novo a pendência e os valores da coluna."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: assistente_na_tela.confirmar_coluna(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.campo, dados.coluna, dados.confirmar))


class PedidoDeDesfazer(BaseModel):
    """ "Desfazer" na conversa: o tipo do que a IA aplicou e o identificador que veio na resposta."""

    tipo: str = Field(max_length=20)            # "correcao", "para_todos", "grupo", "por_pessoa", "coluna" ou
    #                                             "confirmacao"
    id: str = Field(max_length=300)             # o id de aplicado.desfazer (ex.: "a1b2c3d4e5", "REGRA|7" ou
    #                                             "Registro|matricula")


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/assistente/desfazer")
def desfazer_o_que_o_assistente_aplicou(processamento_id: str, dados: PedidoDeDesfazer, pedido: Request):
    """Volta o que a IA aplicou na conversa (troca, "não cadastrar", preencher para todos ou confirmação)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: assistente_na_tela.desfazer(
        conexao, usuario.empresa_id, usuario.login, processamento_id, dados.tipo, dados.id))

class ColunaParaReler(BaseModel):
    """Uma coluna do "Ajude a IA a acertar" e o que a empresa sabe dela (a dica passa pelo guardrail)."""

    coluna: str = Field(max_length=200)
    dica: str = Field(max_length=300)


class PedidoDeReleitura(BaseModel):
    """"Ajude a IA a acertar": uma ou mais colunas, cada uma com a sua dica (tudo conta como uma releitura)."""

    colunas: list[ColunaParaReler] = Field(max_length=10)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/reler")
def reler_colunas(processamento_id: str, dados: PedidoDeReleitura, pedido: Request):
    """A IA relê as colunas indicadas, cada uma com a dica da empresa; o mapeamento volta ao aceite."""
    usuario = usuario_da_empresa(pedido)
    pedidos = []
    for coluna in dados.colunas:
        pedidos.append({"coluna": coluna.coluna, "dica": coluna.dica})
    return executar_acao(lambda conexao: cadastro.reler_colunas(conexao, usuario.empresa_id, processamento_id,
                                                                pedidos))


class PedidoDeDivisao(BaseModel):
    """A coluna que tem vários dados numa célula (ex.: o endereço inteiro) e para onde ela vai ser dividida."""

    coluna: str = Field(max_length=200)
    destino: str = Field(max_length=80)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/previa_da_divisao")
def previa_da_divisao(processamento_id: str, dados: PedidoDeDivisao, pedido: Request):
    """Como a coluna ficaria dividida em partes, sem gravar nada (os exemplos saem com a máscara do parâmetro)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.previa_da_divisao(conexao, usuario.empresa_id, processamento_id,
                                                                    dados.coluna, dados.destino))


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/dividir")
def dividir_coluna(processamento_id: str, dados: PedidoDeDivisao, pedido: Request):
    """Divide a coluna em partes, cada uma ligada ao seu campo (antes do aceite). Devolve a leitura."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.dividir_coluna(conexao, usuario.empresa_id, usuario.login,
                                                                 processamento_id, dados.coluna, dados.destino))


class PedidoParaRefazerADivisao(BaseModel):
    """A coluna que a IA dividiu e o comentário da empresa sobre o que está errado (ADR-104)."""

    coluna: str = Field(max_length=200)
    comentario: str = Field(max_length=500)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/refazer_divisao")
def refazer_divisao(processamento_id: str, dados: PedidoParaRefazerADivisao, pedido: Request):
    """A IA refaz a divisão de UMA coluna com o comentário da empresa (antes do aceite). Devolve a leitura."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.refazer_divisao(conexao, usuario.empresa_id, usuario.login,
                                                                  processamento_id, dados.coluna, dados.comentario))


class PedidoDeConferenciaDaColuna(BaseModel):
    """A coluna do arquivo e o campo que a empresa acabou de escolher para ela."""

    coluna: str = Field(max_length=200)
    campo: str = Field(max_length=80)


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/conferir_coluna")
def conferir_coluna(processamento_id: str, dados: PedidoDeConferenciaDaColuna, pedido: Request):
    """Confere, sem gravar, se os valores da coluna servem para o campo escolhido (a tela avisa na hora)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.conferir_coluna(conexao, usuario.empresa_id, processamento_id,
                                                                  dados.coluna, dados.campo))


@aplicacao.post("/api/empresa/cadastro/{processamento_id}/descartar")
def descartar_envio(processamento_id: str, pedido: Request):
    """"Descartar esta leitura": o envio é encerrado sem cadastrar ninguém. Devolve a leitura depois."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.descartar(conexao, usuario.empresa_id, processamento_id,
                                                            usuario.login))


@aplicacao.get("/api/empresa/cadastro/{processamento_id}/o_que_se_perde")
def o_que_se_perde_ao_descartar(processamento_id: str, pedido: Request):
    """Para a confirmação de "Descartar esta leitura": {funcionarios, correcoes} que se perdem (nada foi ao banco)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: cadastro.o_que_se_perde(conexao, usuario.empresa_id, processamento_id))


# ---------------- Portal Empresa: Início, Benefícios e Endomarketing (services/portal_da_empresa.py) ----------------

@aplicacao.get("/api/empresa/inicio")
def inicio_da_empresa(pedido: Request):
    """O Início do Portal Empresa: nome, números dos cadastros, etapa da jornada e pendências a corrigir."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: portal_da_empresa.inicio_da_empresa(conexao, usuario.empresa_id))


@aplicacao.get("/api/empresa/beneficios")
def beneficios_da_empresa(pedido: Request):
    """O catálogo de benefícios que o banco definiu para a empresa de quem entrou (benefícios e atendimento)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: portal_da_empresa.beneficios_da_empresa(conexao, usuario.empresa_id))


@aplicacao.get("/api/empresa/endomarketing")
def materiais_da_empresa(pedido: Request):
    """Os materiais que o banco PUBLICOU para a empresa de quem entrou, para baixar e divulgar (ADR-115).

    A empresa não gera nem aprova material: quem gera e valida é o especialista do banco.
    """
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: portal_da_empresa.materiais_da_empresa(conexao, usuario.empresa_id))


@aplicacao.get("/api/empresa/endomarketing/{material_id}/arte")
def arte_do_material_da_empresa(material_id: str, pedido: Request):
    """A imagem da arte de um material publicado da empresa de quem entrou (de outra empresa ou retirado: 404)."""
    usuario = usuario_da_empresa(pedido)
    imagem = executar_acao(lambda conexao: portal_da_empresa.arte_do_material(conexao, usuario.empresa_id,
                                                                              material_id))
    # A imagem vai como arquivo para baixar, com um nome simples
    return Response(imagem, media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="arte-{material_id}.png"'})


# ---------------- Cabeçalho e "Minha senha" (services/cabecalho.py; todos os perfis) ----------------

def usuario_logado(pedido: Request):
    """Confere que há alguém logado (qualquer perfil). Devolve o usuário; sem login, 401."""
    usuario = usuario_do_pedido(pedido)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre de novo.")
    return usuario


@aplicacao.get("/api/cabecalho")
def dados_do_cabecalho(pedido: Request):
    """Quem entrou (login, papel, iniciais) e os números que pedem atenção (sino e aba Envios)."""
    usuario = usuario_logado(pedido)
    return executar_acao(lambda conexao: cabecalho.cabecalho(conexao, usuario))


class PedidoDeTrocaDeSenha(BaseModel):
    """A troca da própria senha: a atual (para confirmar que é a pessoa) e a nova, digitada duas vezes."""

    senha_atual: str = Field(max_length=200)
    nova_senha: str = Field(max_length=200)
    confirmacao: str = Field(max_length=200)


@aplicacao.post("/api/minha-senha")
def trocar_minha_senha(dados: PedidoDeTrocaDeSenha, pedido: Request):
    """A pessoa troca a própria senha (ex.: a senha provisória do convite, no primeiro acesso)."""
    usuario = usuario_logado(pedido)
    if dados.nova_senha != dados.confirmacao:
        raise HTTPException(status_code=400, detail="A nova senha e a confirmação não são iguais.")
    # O ingresso desta sessão: é a única que continua depois da troca
    ingresso_atual = pedido.cookies.get(sessoes.NOME_COOKIE)
    return executar_acao(lambda conexao: trocar_senha_contando_os_erros(conexao, usuario.login, dados.senha_atual,
                                                                        dados.nova_senha, ingresso_atual))


def trocar_senha_contando_os_erros(conexao, login: str, senha_atual: str, nova_senha: str,
                                   ingresso_atual: str | None) -> None:
    """Troca a própria senha com o mesmo limite de tentativas do login e derruba as outras sessões.

    Recebe: conexao; login de quem está logado; a senha atual digitada; a nova senha; o ingresso da sessão em uso.
    Por quê (A-06): quem roubou um cookie poderia tentar adivinhar a senha atual aqui sem limite nenhum e, ao acertar,
    trocar a senha e tomar a conta. Por isso, os erros contam no mesmo contador do login: no 5º, bloqueia por 15 minutos.
    Por quê (A-17): quem troca a senha por desconfiar de roubo precisa expulsar as outras sessões.
    Trade-offs, conscientes: a senha atual é conferida duas vezes (aqui e em auth.trocar_propria_senha, ~0,25 s cada);
    e o contador é o mesmo do login, então quem roubou o cookie pode, errando 5 vezes aqui, bloquear o login da
    vítima por 15 minutos. Preferimos isso a deixar a adivinhação sem limite.
    """
    # Login bloqueado (pelo login ou por esta tela): recusa sem nem olhar a senha, como no login
    recusar_se_bloqueado(conexao, login)
    # A senha atual não confere: conta o erro
    if auth.autenticar(conexao, login, senha_atual) is None:
        tentativas_de_login.registrar_erro(conexao, login)
        # Se este foi o 5º erro, o bloqueio começou agora: a pessoa já fica sabendo
        recusar_se_bloqueado(conexao, login)
        # Senão, a mensagem de sempre
        raise ValueError("A senha atual não confere.")
    # Acertou: zera o contador de erros
    tentativas_de_login.registrar_acerto(conexao, login)
    # Grava a nova senha (o serviço confere de novo a senha atual e as regras da senha nova)
    auth.trocar_propria_senha(conexao, login, senha_atual, nova_senha)
    # Derruba as outras sessões abertas; a desta tela continua
    sessoes.encerrar_as_outras_sessoes(conexao, login, ingresso_atual)


# ---------------- Cadastro das empresas (services/empresas.py e services/portal_do_banco.py) ----------------

class DadosDaEmpresa(BaseModel):
    """O cadastro de uma empresa (nova ou editada). O serviço confere cada campo e diz o que está errado."""

    nome: str = Field(max_length=200)
    setor: str = Field(max_length=100)
    municipio: str = Field(max_length=100)
    uf: str = Field(max_length=2)
    cnpj: str = Field(max_length=20)
    endereco_comercial: str = Field(max_length=200)
    dominio_email: str = Field(max_length=100)
    contrato_desde: str = Field(max_length=10)


@aplicacao.post("/api/banco/empresas")
def cadastrar_empresa(dados: DadosDaEmpresa, pedido: Request):
    """O especialista cadastra uma empresa nova na carteira. Devolve a empresa, com o código novo (ex.: EMP007)."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: cadastro_de_empresas.cadastrar(conexao, usuario, dados.model_dump()))


@aplicacao.post("/api/banco/empresas/{empresa_id}/dados")
def atualizar_empresa(empresa_id: str, dados: DadosDaEmpresa, pedido: Request):
    """O especialista edita os dados de uma empresa."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: cadastro_de_empresas.atualizar(conexao, usuario, empresa_id,
                                                                        dados.model_dump()))


class PedidoDeConvite(BaseModel):
    """O e-mail da pessoa do RH que vai ter acesso (do domínio da empresa)."""

    email: str = Field(max_length=200)


@aplicacao.post("/api/banco/empresas/{empresa_id}/convite")
def convidar_usuario(empresa_id: str, dados: PedidoDeConvite, pedido: Request):
    """Dá acesso a uma pessoa do RH: o login é o e-mail, e a senha provisória aparece uma vez para o especialista."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.convidar_usuario(conexao, usuario, empresa_id, dados.email))


class PedidoDeCnpj(BaseModel):
    """Um CNPJ de filial ou de empresa do grupo (ADR-77): o número e o tipo (FILIAL ou GRUPO)."""

    cnpj: str = Field(max_length=20)
    tipo: str = Field(max_length=10)


@aplicacao.post("/api/banco/empresas/{empresa_id}/cnpjs")
def adicionar_cnpj(empresa_id: str, dados: PedidoDeCnpj, pedido: Request):
    """O especialista cadastra um CNPJ de filial ou do grupo (opcional). Devolve a lista dos CNPJs registrados."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: cadastro_de_empresas.adicionar_cnpj(conexao, usuario, empresa_id, dados.cnpj,
                                                                             dados.tipo))


@aplicacao.delete("/api/banco/empresas/{empresa_id}/cnpjs/{cnpj}")
def remover_cnpj(empresa_id: str, cnpj: str, pedido: Request):
    """O especialista tira um CNPJ de filial ou do grupo. Devolve a lista que ficou."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: cadastro_de_empresas.remover_cnpj(conexao, usuario, empresa_id, cnpj))


# ---------------- Endomarketing do banco: gerar, publicar e o kit de marca (services/endomarketing_do_banco.py) ----

@aplicacao.get("/api/banco/endomarketing")
def empresas_do_endomarketing(pedido: Request):
    """As empresas da carteira para o seletor da aba Endomarketing, com quantos rascunhos e publicados cada uma tem."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: endomarketing_do_banco.empresas_do_endomarketing(conexao, usuario))


@aplicacao.get("/api/banco/empresas/{empresa_id}/endomarketing")
def endomarketing_da_empresa(empresa_id: str, pedido: Request):
    """Tudo o que a aba mostra para uma empresa: kit de marca, benefícios, sugestões, materiais, tipos e canais."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: endomarketing_do_banco.tela_da_empresa(conexao, usuario, empresa_id))


class PedidoDeMaterial(BaseModel):
    """O que a aba Endomarketing do banco manda para gerar um rascunho (com teto de tamanho em cada campo)."""

    tipo: str = Field(max_length=30)                # "comunicado", "faq", "kit_boas_vindas" ou "lembrete_conta"
    canal: str = Field(default="email", max_length=20)  # "email", "mural" ou "whatsapp" (decide o tamanho)
    # Os nomes dos benefícios marcados (pelo menos um): até 30, cada um com até 200 letras
    beneficios: list[Annotated[str, Field(max_length=200)]] = Field(default=[], max_length=30)
    destaque: str = Field(default="", max_length=500)
    processamento_id: str | None = Field(default=None, max_length=100)  # só no kit de uma inclusão (da sugestão)


@aplicacao.post("/api/banco/empresas/{empresa_id}/endomarketing/gerar")
def gerar_material(empresa_id: str, dados: PedidoDeMaterial, pedido: Request):
    """O especialista pede ao Agente de Endomarketing um rascunho para a empresa, com os benefícios marcados."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: endomarketing_do_banco.gerar_material(
        conexao, usuario, empresa_id, dados.tipo, dados.canal, dados.beneficios, dados.destaque,
        dados.processamento_id))


@aplicacao.post("/api/banco/empresas/{empresa_id}/endomarketing/{material_id}/publicar")
async def publicar_material(empresa_id: str, material_id: str, pedido: Request, arte: UploadFile | None = None):
    """Publica o rascunho para a empresa, com a arte desenhada na tela (PNG, opcional). A empresa passa a ver."""
    usuario = usuario_do_banco(pedido)
    imagem = None
    if arte is not None:
        # Lê só até o limite da arte (mais 1 byte, para saber se passou); a conferência fica no serviço
        imagem = await arte.read(kit_de_marca.LIMITE_DA_ARTE + 1)
    return executar_acao(lambda conexao: endomarketing_do_banco.publicar_material(conexao, usuario, empresa_id,
                                                                                  material_id, imagem))


@aplicacao.post("/api/banco/empresas/{empresa_id}/endomarketing/{material_id}/descartar")
def descartar_material(empresa_id: str, material_id: str, pedido: Request):
    """Descarta um rascunho: a empresa nunca chega a vê-lo."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: endomarketing_do_banco.descartar_material(conexao, usuario, empresa_id,
                                                                                   material_id))


@aplicacao.post("/api/banco/empresas/{empresa_id}/endomarketing/{material_id}/retirar")
def retirar_material(empresa_id: str, material_id: str, pedido: Request):
    """Retira um material publicado (ex.: o benefício mudou): a empresa deixa de ver e de baixar."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: endomarketing_do_banco.retirar_material(conexao, usuario, empresa_id,
                                                                                 material_id))


@aplicacao.get("/api/banco/empresas/{empresa_id}/endomarketing/{material_id}/arte")
def arte_do_material_do_banco(empresa_id: str, material_id: str, pedido: Request):
    """A imagem da arte de um material da empresa, para o especialista conferir ou baixar (sem arte: 404)."""
    usuario = usuario_do_banco(pedido)
    imagem = executar_acao(lambda conexao: endomarketing_do_banco.arte_do_material(conexao, usuario, empresa_id,
                                                                                   material_id))
    return Response(imagem, media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="arte-{material_id}.png"'})


@aplicacao.get("/api/banco/empresas/{empresa_id}/kit/logo")
def logo_da_empresa(empresa_id: str, pedido: Request):
    """A imagem do logo da empresa, para a prévia e para a arte (sem logo: 404).

    O logo muda só pela KB "Kit da marca" (a fonte única): esta imagem é a cópia da versão publicada.
    """
    usuario = usuario_do_banco(pedido)
    imagem, tipo = executar_acao(lambda conexao: endomarketing_do_banco.logo_da_empresa(conexao, usuario,
                                                                                        empresa_id))
    return Response(imagem, media_type=tipo)


@aplicacao.get("/api/banco/empresas/{empresa_id}/kit_em_uso")
def kit_em_uso(empresa_id: str, pedido: Request):
    """O kit que a arte da empresa usa agora (cores, logo e a versão da KB do kit), para a prévia só de leitura."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: kbs_publicacao.kit_em_uso(conexao, usuario, empresa_id))


# ---------------- Avaliação dos envios pelo banco (services/avaliacao_do_banco.py) ----------------

@aplicacao.get("/api/banco/envios")
def fila_de_envios(pedido: Request):
    """A fila da aba Envios: os envios esperando a avaliação do banco e os já avaliados."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: avaliacao_do_banco.fila_de_envios(conexao, usuario))


@aplicacao.get("/api/banco/colunas_da_consulta")
def colunas_da_consulta_do_banco(pedido: Request):
    """As colunas da grade de pessoas de um envio (tela Envios): uma por campo do parâmetro vigente (ADR-111)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: acompanhamento.colunas_da_consulta(conexao))


@aplicacao.get("/api/banco/envios/{processamento_id}/pessoas")
def pessoas_do_envio(processamento_id: str, pedido: Request):
    """As pessoas de um envio na avaliação do banco, com o CPF inteiro (a abertura fica registrada)."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: avaliacao_do_banco.pessoas_do_envio(conexao, usuario, processamento_id))


class PedidoDeAvaliacao(BaseModel):
    """A decisão do banco sobre um envio. O jeito novo (ADR-121) é "decisao": "aprovar",
    "aprovar_e_devolver_marcados" ou "devolver"; o jeito antigo, "aprovar" (True aprova, False devolve), continua
    valendo. "motivo" é o recado para a empresa na devolução do envio inteiro."""

    aprovar: bool | None = None
    decisao: str | None = Field(default=None, max_length=40)
    motivo: str = Field(default="", max_length=500)


@aplicacao.post("/api/banco/envios/{processamento_id}/avaliar")
def avaliar_envio(processamento_id: str, dados: PedidoDeAvaliacao, pedido: Request):
    """O especialista aprova, aprova os outros e devolve as pessoas apontadas, ou devolve o envio inteiro."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: avaliacao_do_banco.avaliar(conexao, usuario, processamento_id,
                                                                    dados.aprovar, dados.motivo, dados.decisao))


@aplicacao.get("/api/banco/envios/{processamento_id}/baixar")
def baixar_envio(processamento_id: str, pedido: Request):
    """O CSV (para o Excel) com as pessoas do envio, como a grade da tela Envios mostra, com o CPF inteiro. Cada
    download fica registrado nos acessos da empresa, com quantas pessoas."""
    usuario = usuario_do_banco(pedido)
    conteudo, nome_do_arquivo = executar_acao(lambda conexao: avaliacao_do_banco.arquivo_do_envio(conexao, usuario,
                                                                                                  processamento_id))
    # O navegador baixa com o nome do envio e não guarda cópia (o arquivo tem o CPF inteiro)
    cabecalhos = {"Content-Disposition": "attachment; filename=\"" + nome_do_arquivo + "\"",
                  "Cache-Control": "no-store"}
    return Response(content=conteudo, media_type="text/csv; charset=utf-8", headers=cabecalhos)


@aplicacao.get("/api/banco/motivos_de_apontamento")
def motivos_de_apontamento(pedido: Request):
    """Os motivos da lista fechada para apontar um problema numa pessoa: [{valor, texto}] (ADR-121)."""
    usuario_do_banco(pedido)
    return apontamentos_do_banco.motivos()


class PedidoDeApontamento(BaseModel):
    """Um problema numa pessoa do envio: a linha dela, o motivo (da lista) e o recado que a empresa vai ler."""

    linha: int
    motivo: str = Field(max_length=40)
    recado: str = Field(default="", max_length=600)


@aplicacao.post("/api/banco/envios/{processamento_id}/apontamentos")
def apontar_problema(processamento_id: str, dados: PedidoDeApontamento, pedido: Request):
    """O especialista aponta (ou troca) o problema de uma pessoa do envio que espera o banco. Devolve {apontamento}."""
    usuario = usuario_do_banco(pedido)
    apontamento = executar_acao(lambda conexao: avaliacao_do_banco.apontar(conexao, usuario, processamento_id,
                                                                           dados.linha, dados.motivo, dados.recado))
    return {"apontamento": apontamento}


@aplicacao.delete("/api/banco/envios/{processamento_id}/apontamentos/{linha}")
def desfazer_apontamento(processamento_id: str, linha: str, pedido: Request):
    """O especialista desfaz o apontamento de uma pessoa (antes de decidir o envio).

    A linha chega como texto e vira número só depois de conferir o login: assim quem não entrou recebe 401 (e a
    empresa, 403), e não um erro de formato que revelaria a rota antes da conferência (bateria de segurança, A-20).
    """
    usuario = usuario_do_banco(pedido)
    if not linha.isdigit():
        raise HTTPException(status_code=400, detail="Linha inválida.")
    executar_acao(lambda conexao: avaliacao_do_banco.desfazer_apontamento(conexao, usuario, processamento_id,
                                                                          int(linha)))
    return {"ok": True}


# ---------------- Contas abertas: o arquivo do banco, subido POR EMPRESA (services/contas_abertas.py, ADR-122) -------

@aplicacao.get("/api/banco/empresas/{empresa_id}/contas/layout")
def layout_do_arquivo_de_contas(empresa_id: str, pedido: Request):
    """O layout fixo do arquivo de contas abertas de uma empresa: colunas, formatos, o que o sistema confere (fonte
    única da tela), a empresa com os CNPJs que valem no arquivo e a orientação para a tela. 404 se a empresa não existe.
    """
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: contas_abertas.layout_do_arquivo(conexao, empresa_id))


@aplicacao.post("/api/banco/empresas/{empresa_id}/contas/conferir")
async def conferir_arquivo_de_contas(empresa_id: str, pedido: Request, arquivo: UploadFile | None = None):
    """Confere o arquivo de contas abertas de uma empresa e devolve a PRÉVIA da baixa (nada é gravado nas contas ainda).

    Sempre 200 com a prévia, mesmo quando o arquivo é recusado (as divergências vêm nela; um arquivo de outra empresa
    é recusado inteiro). 400 só sem arquivo ou com o arquivo acima do limite de tamanho; 404 se a empresa não existe.
    """
    usuario = usuario_do_banco(pedido)
    # Sem arquivo no formulário: não há o que conferir
    if arquivo is None:
        raise HTTPException(status_code=400, detail="Escolha o arquivo de contas abertas.")
    # O conteúdo do arquivo, lido só até o limite de tamanho (ADR-110)
    conteudo = await ler_arquivo_ate_o_limite(arquivo)

    def acao(conexao):
        return contas_abertas.conferir_arquivo(conexao, usuario, empresa_id, conteudo, arquivo.filename or "")

    return executar_acao(acao)


@aplicacao.post("/api/banco/contas/{arquivo_id}/confirmar")
def confirmar_baixa_de_contas(arquivo_id: str, pedido: Request):
    """Dá baixa nas contas novas da prévia (cada funcionário que abriu a conta)."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: contas_abertas.confirmar_baixa(conexao, usuario, arquivo_id))


@aplicacao.post("/api/banco/contas/{arquivo_id}/descartar")
def descartar_arquivo_de_contas(arquivo_id: str, pedido: Request):
    """Descarta a prévia: nada é gravado."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: contas_abertas.descartar(conexao, usuario, arquivo_id))


@aplicacao.get("/api/banco/empresas/{empresa_id}/contas/historico")
def historico_de_contas(empresa_id: str, pedido: Request):
    """Os arquivos de contas já confirmados desta empresa: quem subiu, quando, quantas baixas (novas contas e
    correntistas, com os ativos e os inativos: só o banco vê) e as contas da empresa depois. 404 se a empresa não
    existe."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: contas_abertas.historico(conexao, usuario, empresa_id))


# ---------------- Conversas do "Posso ajudar?" entre a empresa e o banco (services/mensagens.py) ----------------

class PedidoDeMensagem(BaseModel):
    """Uma mensagem: o texto e, do lado da empresa, a tela de onde ela escreveu (com teto de tamanho)."""

    texto: str = Field(max_length=4000)
    contexto: str = Field(default="", max_length=100)


@aplicacao.get("/api/empresa/conversa")
def conversa_da_empresa(pedido: Request):
    """A conversa da empresa de quem entrou com o especialista do banco."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: mensagens.conversa_da_empresa(conexao, usuario.empresa_id))


@aplicacao.post("/api/empresa/conversa")
def mandar_mensagem_da_empresa(dados: PedidoDeMensagem, pedido: Request):
    """A empresa escreve para o especialista (sempre na própria conversa)."""
    usuario = usuario_da_empresa(pedido)
    return executar_acao(lambda conexao: mensagens.mandar_mensagem(conexao, usuario, dados.texto, dados.contexto))


@aplicacao.get("/api/banco/conversas")
def conversas_da_carteira(pedido: Request):
    """Todas as conversas das empresas da carteira (aba Mensagens do banco)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: mensagens.conversas_da_carteira(conexao))


@aplicacao.get("/api/banco/conversas/prazo")
def prazo_das_respostas(pedido: Request):
    """O prazo de resposta de 1 dia útil: respondidas, no prazo, esperando e atrasadas (aba Mensagens do banco)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: mensagens.prazo_das_respostas(conexao))


@aplicacao.get("/api/banco/conversas/abertas")
def conversas_abertas(pedido: Request):
    """As empresas com a conversa aberta (sem resposta ou ainda não marcada como respondida) e quantas são: o sinal
    (a "bolinha") do menu do alto, da aba Conversa e da Carteira. Só o banco; nenhum texto de mensagem sai daqui."""
    usuario_do_banco(pedido)
    # A lista, da conversa mais recente para a mais antiga (services/mensagens.py)
    empresas = executar_acao(mensagens.empresas_com_conversa_aberta)
    return {"empresas": empresas, "total": len(empresas)}


@aplicacao.post("/api/banco/conversas/{empresa_id}")
def responder_a_empresa(empresa_id: str, dados: PedidoDeMensagem, pedido: Request):
    """O especialista responde a uma empresa."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: mensagens.mandar_mensagem(conexao, usuario, dados.texto,
                                                                   empresa_id=empresa_id))


@aplicacao.post("/api/banco/conversas/{empresa_id}/resolver")
def marcar_conversa_resolvida(empresa_id: str, pedido: Request):
    """O especialista marca a conversa de uma empresa como resolvida."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: mensagens.marcar_resolvida(conexao, usuario, empresa_id))


# ---------------- Portal do Banco: Planejamento (services/portal_do_banco.py) ----------------

def usuario_do_banco(pedido: Request):
    """Confere que quem pede está logado E é do perfil BANCO. Devolve o usuário.

    Recebe: pedido. Devolve: o usuário. Levanta 401 (sem login) ou 403 (outro perfil).
    """
    usuario = usuario_do_pedido(pedido)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre de novo.")
    if usuario.perfil != Perfil.BANCO:
        raise HTTPException(status_code=403, detail="Esta consulta é só do Portal do Banco.")
    # Com a senha provisória, nada de dados até trocá-la (ADR-109)
    exigir_senha_definitiva(usuario)
    return usuario


def filtros_do_endereco(pedido: Request) -> dict:
    """Os filtros do planejamento que vieram no endereço (ex.: ?empresa_id=EMP001&uf=SP)."""
    filtros = {}
    for nome in portal_do_banco.NOMES_DOS_FILTROS:
        filtros[nome] = pedido.query_params.get(nome, "")
    return filtros


@aplicacao.get("/api/banco/inicio")
def inicio_do_banco(pedido: Request):
    """O Início do Portal do Banco: números da carteira, a fila do dia e a carteira por empresa (só contagens)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.inicio_do_banco(conexao))


@aplicacao.get("/api/banco/telemetria/uso")
def uso_das_empresas(pedido: Request):
    """O uso das empresas no Painel de acompanhamento: acessos, envios, descartes, funil, linha do tempo, os CNPJs de
    cada empresa (busca no funil) e o tempo até a avaliação do banco (só o uso do RH e as datas das decisões)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.uso_das_empresas(conexao))


@aplicacao.get("/api/banco/empresas")
def empresas_da_carteira(pedido: Request):
    """A ficha de cada empresa: dados, números do contrato, usuários do RH e catálogo de benefícios (só BANCO)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.empresas_da_carteira(conexao))


def tela_de_parametros(conexao) -> dict:
    """O que a tela de parâmetros mostra: a versão vigente, os campos, o catálogo de tipos e o registro das alterações."""
    versao, campos = parametros.layout_ativo(conexao)
    campos_para_a_tela = []
    for campo in campos:
        campo_para_a_tela = campo.model_dump(mode="json")
        # "Pode ser igual para todos": o valor que vale, mesmo numa versão antiga sem a marcação (a lista padrão)
        campo_para_a_tela["igual_para_todos"] = parametros.pode_ser_igual_para_todos(campo)
        campos_para_a_tela.append(campo_para_a_tela)
    tipos = []
    for tipo in TipoCampo:
        tipos.append(tipo.value)
    return {"versao": versao, "campos": campos_para_a_tela, "tipos": tipos,
            "registro": parametros.registro_do_layout(conexao)}


@aplicacao.get("/api/banco/parametros/layout")
def layout_do_banco(pedido: Request):
    """O layout que o banco quer receber, com o registro de quem mudou o quê e quando (só BANCO)."""
    usuario_do_banco(pedido)
    return executar_acao(tela_de_parametros)


class PedidoDeLayout(BaseModel):
    """A lista inteira de campos do layout, como ficou na tela (vira uma versão nova)."""

    campos: list[dict] = Field(max_length=200)


@aplicacao.post("/api/banco/parametros/layout")
def gravar_layout_do_banco(dados: PedidoDeLayout, pedido: Request):
    """Grava uma versão nova do layout (só BANCO); o registro guarda quem, quando e o que mudou."""
    usuario = usuario_do_banco(pedido)

    def gravar_e_mostrar(conexao):
        """Grava a versão nova, começa a refazer o índice da IA (em segundo plano) e devolve a tela atualizada."""
        parametros.salvar_layout_pela_tela(conexao, dados.campos, usuario.login)
        versao, campos = parametros.layout_ativo(conexao)
        indice_do_layout.refazer_em_segundo_plano(versao, campos)
        return tela_de_parametros(conexao)
    return executar_acao(gravar_e_mostrar)


class PedidoDeSituacaoDoUsuario(BaseModel):
    """Se a pessoa da empresa deve ficar ativa (True) ou desativada (False)."""

    ativo: bool


@aplicacao.post("/api/banco/empresas/usuarios/{login}/situacao")
def ativar_ou_desativar_usuario(login: str, dados: PedidoDeSituacaoDoUsuario, pedido: Request):
    """Desativa (ou reativa) uma pessoa de uma empresa; desativada, ela sai do portal na hora (só BANCO)."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.ativar_ou_desativar_usuario_da_empresa(
        conexao, usuario, login, dados.ativo))


@aplicacao.get("/api/banco/empresas/{empresa_id}/visao_geral")
def visao_geral_da_empresa(empresa_id: str, pedido: Request):
    """Os números e a lista de funcionários de uma empresa, na aba Empresas do especialista (só BANCO, ADR-112).

    A lista traz dados pessoais (CPF inteiro): o navegador não pode guardar cópia, e cada abertura fica registrada.
    """
    usuario = usuario_do_banco(pedido)
    visao = executar_acao(lambda conexao: portal_do_banco.visao_geral_da_empresa(conexao, usuario, empresa_id))
    return JSONResponse(visao, headers={"Cache-Control": "no-store"})


@aplicacao.get("/api/banco/empresas/{empresa_id}/funcionarios/baixar")
def baixar_funcionarios_da_empresa(empresa_id: str, pedido: Request):
    """O "Baixar CSV" da Visão geral: o arquivo (para o Excel) com os funcionários desta empresa, com todas as colunas
    do cadastro (os obrigatórios, os opcionais que vieram, a situação, a conta e a inclusão). Só o perfil BANCO.

    O arquivo tem o CPF: o navegador não guarda cópia, e cada download fica registrado nos acessos da empresa. 404 se
    a empresa não existe; 400 se ela ainda não tem funcionários.
    """
    usuario = usuario_do_banco(pedido)
    conteudo, nome_do_arquivo = executar_acao(
        lambda conexao: portal_do_banco.arquivo_dos_funcionarios_da_empresa(conexao, usuario, empresa_id))
    # O navegador baixa com o nome da empresa (ex.: "funcionarios_EMP001.csv") e não guarda cópia
    cabecalhos = {"Content-Disposition": "attachment; filename=\"" + nome_do_arquivo + "\"",
                  "Cache-Control": "no-store"}
    return Response(content=conteudo, media_type="text/csv; charset=utf-8", headers=cabecalhos)


@aplicacao.post("/api/banco/empresas/usuarios/{login}/nova-senha")
def gerar_nova_senha_provisoria(login: str, pedido: Request):
    """A pessoa da empresa esqueceu a senha: o banco gera uma provisória, que aparece uma vez (só BANCO, ADR-109)."""
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.gerar_nova_senha_provisoria(conexao, usuario, login))


@aplicacao.get("/api/banco/telemetria/ia")
def telemetria_da_ia(pedido: Request):
    """Acompanhamento dos agentes: as execuções reais dos agentes e um cartão por agente de IA, com a aceitação das
    propostas de cada um (só BANCO; a permissão também é conferida no serviço).

    O período vem no endereço: ?de=AAAA-MM-DD&ate=AAAA-MM-DD (inclusive; sem nada = tudo). Data inválida: 400.
    """
    usuario = usuario_do_banco(pedido)
    # As datas do período, como vieram (o serviço confere e converte)
    de = pedido.query_params.get("de", "")
    ate = pedido.query_params.get("ate", "")
    return executar_acao(lambda conexao: portal_do_banco.telemetria_da_ia(conexao, usuario, de, ate))


@aplicacao.get("/api/banco/planejamento/filtros")
def filtros_do_planejamento(pedido: Request):
    """As opções das listas de filtro (empresas, UFs e datas de referência que existem nos números)."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.filtros_do_planejamento(conexao))


@aplicacao.get("/api/banco/planejamento")
def numeros_do_planejamento(pedido: Request):
    """Os números agregados do planejamento com os filtros do endereço.

    JSON: {indicadores, resumo: {cadastrados, aguardando_retorno, contas_abertas, correntistas_marcados (o correntista
    é um grupo só, ADR-149)}, por_empresa, por_regiao}. Só números: nenhuma pessoa. As premissas oficiais ficam em
    /api/banco/premissas.
    """
    usuario_do_banco(pedido)
    filtros = filtros_do_endereco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.numeros_do_planejamento(conexao, filtros))


@aplicacao.get("/api/banco/planejamento/base")
def base_do_simulador(pedido: Request):
    """Os clientes que a empresa enviou (cadastrados + em análise), para a seção travada do Simulador de Rentabilidade.

    Endereço: ?empresa_id=EMP001 (sem empresa: todas as da carteira). JSON: {empresa_id, cadastrados, em_analise,
    enviados}. Só números: nenhuma pessoa. Conta que custa (monta a lista de cada empresa): a tela pede uma vez, quando
    a empresa muda.
    """
    usuario_do_banco(pedido)
    empresa_id = (pedido.query_params.get("empresa_id") or "").strip() or None
    return executar_acao(lambda conexao: portal_do_banco.base_da_empresa(conexao, empresa_id))


class PedidoDeSimulacao(BaseModel):
    """A empresa, os valores que a especialista mudou no simulador e os clientes que a empresa enviou.

    filtros: {"empresa_id"} (vazio: todas as empresas). premissas: {"horizonte_meses", "mob_cliente_folha",
    "mob_cliente_nao_folha", "mob_cliente_novo_conquistado" (a que não vier vale a oficial), "percentual_novas_contas",
    "percentual_nao_folha", "percentual_correcao_folha" (de 0 a 100, sem valor padrão), "clientes_estimados" (a
    estimativa da especialista, que substitui os enviados)}. clientes_da_empresa: os enviados, da rota /base.
    O serviço confere cada valor e recusa com 400 e a mensagem para a pessoa.
    """

    filtros: dict[str, str] = {}
    premissas: dict[str, str | int | float | None] = {}
    clientes_da_empresa: str | int | None = None


class PedidoDeSimulacaoSalva(PedidoDeSimulacao):
    """A simulação para guardar: os mesmos dados, mais o nome (obrigatório; o serviço confere e recusa vazio)."""

    nome: str = Field(default="", max_length=200)


@aplicacao.post("/api/banco/planejamento/ganho")
def simular_ganho(dados: PedidoDeSimulacao, pedido: Request):
    """O Simulador de Rentabilidade: base de clientes × três taxas × premissas globais, SEM gravar nada.

    As premissas oficiais não mudam. Sem uma das três taxas, "simulacao.total" vem vazio (None) e "simulacao.falta"
    diz o que falta (nunca há valor padrão). JSON: {valores, alteradas, versao_premissas, base: {clientes, origem},
    simulacao: {clientes, linhas, total, falta}, confirmado: {..., taxas_observadas, realizado}}.
    """
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.simular(conexao, dados.filtros, dados.premissas,
                                                                 dados.clientes_da_empresa))


@aplicacao.post("/api/banco/planejamento/simulacoes")
def salvar_simulacao(dados: PedidoDeSimulacaoSalva, pedido: Request):
    """Guarda a simulação com o nome, quem simulou, os filtros, os valores e o resultado. Devolve a simulação salva.

    Sem nome: 400. As premissas oficiais não mudam (a gravação oficial é a tela "Premissas financeiras").
    """
    usuario = usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.salvar_simulacao(
        conexao, usuario, dados.nome, dados.filtros, dados.premissas, dados.clientes_da_empresa))


@aplicacao.get("/api/banco/planejamento/simulacoes")
def simulacoes_salvas(pedido: Request):
    """As simulações salvas, da mais recente para a mais antiga: nome, quem, quando, os valores e o ganho."""
    usuario_do_banco(pedido)
    return executar_acao(lambda conexao: portal_do_banco.simulacoes_salvas(conexao))


# ---------------- Premissas financeiras oficiais (engrenagem Configuração) ----------------

@aplicacao.get("/api/banco/premissas")
def premissas_oficiais(pedido: Request):
    """A tela "Premissas financeiras": a versão vigente e o registro de todas as versões (quem, quando e o que mudou).

    Só BANCO (401 sem login, 403 para a empresa). JSON: {versao, vigente: {horizonte_meses, mob_cliente_folha,
    mob_cliente_nao_folha, mob_cliente_novo_conquistado}, horizonte_maximo_meses,
    registro: [{versao, criado_em, criado_por, mudancas}]}. O dinheiro vem como texto com duas casas (ex.: "2090.62").
    As taxas (% novas contas, % não folha, % correção) não são oficiais: ficam só no Simulador de Rentabilidade.
    """
    usuario_do_banco(pedido)
    return executar_acao(parametros.premissas_para_a_tela)


class PedidoDePremissas(BaseModel):
    """Os valores das premissas digitados na tela (texto ou número; o serviço confere cada um)."""

    horizonte_meses: str | int
    mob_cliente_folha: str | int | float
    mob_cliente_nao_folha: str | int | float
    mob_cliente_novo_conquistado: str | int | float


@aplicacao.post("/api/banco/premissas")
def gravar_premissas_oficiais(dados: PedidoDePremissas, pedido: Request):
    """Grava as premissas da tela como a nova versão oficial (v2, v3...), que passa a valer para os cálculos novos.

    Só BANCO. Recusa com 400 e a mensagem para a pessoa: valor zero ou negativo, horizonte fora de 1 a 60 meses ou
    quebrado, dinheiro com mais de 2 casas, ou nada mudou. Devolve a tela atualizada (o mesmo JSON do GET) e as
    frases do que mudou ("mudancas"). As simulações guardadas continuam com a versão que usaram.
    """
    usuario = usuario_do_banco(pedido)

    def conferir_gravar_e_mostrar(conexao):
        """Confere os valores, grava pela porta (services/acesso.py confere o perfil) e devolve a tela atualizada."""
        conferido = parametros.conferir_premissas_da_tela(conexao, dados.model_dump())
        acesso.salvar_premissas(conexao, usuario, conferido["conteudo"])
        tela = parametros.premissas_para_a_tela(conexao)
        tela["mudancas"] = conferido["mudancas"]
        return tela
    return executar_acao(conferir_gravar_e_mostrar)


@aplicacao.get("/api/banco/teto_da_ia")
def teto_da_ia(pedido: Request):
    """A página "Teto de gasto da IA": o gasto de hoje e do mês, os tetos, a pausa e o histórico (ADR-139).

    Só BANCO (401 sem login, 403 para a empresa). JSON: {dia, gasto_dia_usd, teto_dia_usd, gasto_mes_usd,
    teto_mes_usd, atingido, pausada_desde, volta_quando, ultimas_mudancas, envios_esperando, teto_maximo_usd,
    historico} (services/pagina_do_teto_da_ia.py). Dos envios esperando, só o número: nenhuma empresa nem pessoa.
    """
    usuario_do_banco(pedido)
    return executar_acao(pagina_do_teto_da_ia.situacao_da_pagina)


@aplicacao.get("/api/banco/teto_da_ia/aviso")
def aviso_do_teto_da_ia(pedido: Request):
    """A faixa do alto do Portal Interno: {atingido: "dia", "mes" ou null}. Só BANCO. Consulta leve (ADR-139)."""
    usuario_do_banco(pedido)
    return executar_acao(pagina_do_teto_da_ia.aviso_do_teto)


class PedidoDeTetoDaIA(BaseModel):
    """Um teto novo digitado na página: o período ("dia" ou "mes") e o valor em dólares (o serviço confere tudo)."""

    periodo: str = Field(max_length=10)
    valor_usd: float | int | str | None = None


@aplicacao.post("/api/banco/teto_da_ia")
def ajustar_teto_da_ia(dados: PedidoDeTetoDaIA, pedido: Request, tarefas_depois: BackgroundTasks):
    """O especialista muda um teto: grava com quem e quando, e a página volta atualizada, com os avisos (ADR-139).

    Só BANCO. Recusa com 400 e o motivo: valor que não é número, zero ou negativo, acima de US$ 1.000, período
    desconhecido ou nada mudou. Se a IA ficou liberada, os envios parados pelo teto voltam para a análise em segundo
    plano, depois da resposta (a página não espera por eles).
    """
    usuario = usuario_do_banco(pedido)
    situacao = executar_acao(lambda conexao: pagina_do_teto_da_ia.ajustar_teto(
        conexao, usuario.login, dados.periodo, dados.valor_usd))
    # A IA está liberada e há envios esperando: a retomada roda depois da resposta, com uma conexão própria
    if situacao["ia_liberada"] and situacao["envios_esperando"] > 0:
        tarefas_depois.add_task(pagina_do_teto_da_ia.retomar_com_conexao_nova, auth.conectar)
    return situacao


# As KBs de endomarketing (ADR-125): as rotas ficam em api/rotas_kbs_endomarketing.py, só do perfil BANCO.
from api.rotas_kbs_endomarketing import roteador as rotas_das_kbs  # noqa: E402
aplicacao.include_router(rotas_das_kbs)

# A faixa salarial por profissão, CBO (ADR-129): as rotas ficam em api/rotas_faixas_cbo.py, só do perfil BANCO.
from api.rotas_faixas_cbo import roteador as rotas_das_faixas_cbo  # noqa: E402
aplicacao.include_router(rotas_das_faixas_cbo)

# A legenda dos status (o "i" em cima das grades): as rotas ficam em api/rotas_legenda_dos_status.py, uma do banco e
# uma da empresa.
from api.rotas_legenda_dos_status import roteador as rotas_da_legenda_dos_status  # noqa: E402
aplicacao.include_router(rotas_da_legenda_dos_status)

# O joinha nas respostas dos agentes (ADR-151): as rotas ficam em api/rotas_opiniao_dos_agentes.py, as da empresa, as
# do banco e a do Acompanhamento dos agentes.
from api.rotas_opiniao_dos_agentes import roteador as rotas_da_opiniao_dos_agentes  # noqa: E402
aplicacao.include_router(rotas_da_opiniao_dos_agentes)


# As páginas, a aparência e os scripts do front. Montado por último: as rotas /api acima têm prioridade.
# StaticFiles só entrega arquivos de dentro da pasta front/ (pedidos como "/../.env" são recusados).
aplicacao.mount("/", StaticFiles(directory=PASTA_DO_FRONT), name="front")
