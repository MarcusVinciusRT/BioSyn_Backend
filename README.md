# BioSyn — Backend

API da plataforma BioSyn, de dados em saúde pública. FastAPI sobre Oracle
Autonomous Database.

## Arquitetura

A API é única, mas conversa com quatro backends distintos:

| Backend | O que atende | Acesso |
|---|---|---|
| OLTP (8 tabelas do DDL) | Login, usuários, cargos, organizações, log de alertas | leitura e escrita |
| Lakehouse `GOLD` | Relatórios | somente leitura |
| Select AI (Oracle) | Chat em linguagem natural | somente leitura |
| SMTP | Envio dos alertas | serviço externo |

O dashboard não toca em banco nenhum: a API devolve as URLs de embed e o front
renderiza os painéis em iframe.

O fluxo de uma requisição é sempre o mesmo:

```
rota (api/v1/routes)        valida entrada e saída, injeta dependências
  └─ serviço (services)     regra de negócio, transação, erros de domínio
       ├─ repositório       consultas ORM
       └─ integração        SMTP, Select AI, lakehouse
```

Duas regras de camada: **a rota nunca importa um model** e **o serviço nunca
levanta `HTTPException`**. Serviços levantam `AppError` com um código do
catálogo, e um único handler traduz para o envelope de erro.

## Requisitos

- **Python 3.13** — não use 3.14: o `pydantic-core` ainda não tem wheel para
  essa versão e a compilação a partir do fonte falha.
- Wallet do Oracle ADB (mTLS) ou a connection string TLS.

## Como rodar

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # preencha as variáveis
```

Descompacte o wallet em `wallet/` (a pasta é ignorada pelo git). Depois:

```bash
.venv/bin/python scripts/seed_dados_apoio.py
.venv/bin/python scripts/criar_admin.py --email admin@saude.gov.br \
  --nome Maria --sobrenome Santos --cpf 12345678901 --telefone 11987654321
.venv/bin/uvicorn app.main:app --reload
```

Não existe autocadastro: sem rodar `criar_admin.py` não há como entrar na
aplicação. A senha é pedida interativamente se você omitir `--senha`, o que
evita deixá-la no histórico do shell.

Documentação interativa em <http://localhost:8000/docs> — fechada quando
`AMBIENTE=prod`.

## Testes

```bash
.venv/bin/pytest                     # tudo
.venv/bin/pytest -m "not banco"      # só o que roda sem Oracle (use em CI)
```

Os testes marcados com `banco` falam com o ADB de verdade e limpam o que criam.

## Variáveis de ambiente

Todas documentadas em `.env.example`. As que costumam dar trabalho:

| Variável | Observação |
|---|---|
| `WALLET_DIR` | Caminho relativo (`./wallet`) é resolvido a partir da raiz do projeto. |
| `WALLET_PASSWORD` | **Obrigatório** se o wallet tiver senha — sem ele o driver trava pedindo a passphrase. |
| `ALERTA_CANAL` | `console` (padrão, não envia nada), `smtp` ou `brevo`. No Render gratuito, **só `brevo` funciona**. |
| `SMTP_SENHA` | No Gmail, use uma **senha de app**, não a do login. Espaços são removidos. |
| `SMTP_REMETENTE` | No Gmail e no Outlook, precisa ser igual ao `SMTP_USUARIO`. |
| `LAKEHOUSE_MODO` | `fallback` agrega de `GOLD.INTERNACOES`; `views` usa as views de `METRICAS.nome_view`. |
| `AMBIENTE` | `prod` fecha `/docs`, `/redoc` e `/openapi.json`. |

## Deploy

```bash
docker build -t biosyn-backend .
docker run -p 8000:8000 --env-file .env \
  -v "$PWD/wallet:/app/wallet:ro" biosyn-backend
```

O wallet **não vai na imagem** — é montado como volume, para a credencial não
ficar gravada numa camada. Rode sempre com `--proxy-headers` atrás de um
balanceador (o `CMD` do Dockerfile já faz isso): sem ele, todas as tentativas de
login chegam com o IP do proxy e o limite de tentativas vira global.

## Deploy no Render

O pipeline é: **push na `main` → GitHub Actions roda os testes → só se passarem,
o Render publica.** O auto-deploy nativo do Render fica desligado
(`autoDeploy: false`) justamente para que uma suíte quebrada não vá ao ar.

### 1. Wallet: uma variável, não arquivos

O wallet é segredo, está fora do git, e o Render não tem disco persistente para
montá-lo. A saída é mandar o `.zip` inteiro codificado em base64:

```bash
base64 -i wallet/wallet-dbdatasus.zip | tr -d '\n'
```

Cole o resultado em `WALLET_BASE64` no painel do Render (são ~34 mil
caracteres, cabe sem problema) e **deixe `WALLET_DIR` vazio** — o base64 tem
precedência. Na inicialização a aplicação materializa o wallet num diretório
temporário com permissão restrita, que morre junto com o processo. O código
recusa zip com caminho suspeito e restringe as permissões dos arquivos
extraídos (`app/db/wallet.py`).

Você **não sobe o arquivo `.env`** para lugar nenhum. O Render injeta as
variáveis direto no ambiente do processo, e a aplicação lê de lá — o `.env` é
só uma comodidade local, e o app roda sem ele existir.

### 2. Criar o serviço

**New → Blueprint**, aponte para este repositório. O `render.yaml` define build,
start command, health check e as variáveis. Preencha no painel as marcadas com
`sync: false`:

`DB_PASSWORD`, `WALLET_PASSWORD`, `BREVO_API_KEY`,
`BREVO_REMETENTE` e `CORS_ORIGENS` (a origem do front, separada por vírgula).

O `JWT_SECRET` o próprio Render gera — não reaproveite o local.

### 3. Ligar o deploy ao pipeline

No Render, **Settings → Deploy Hook**, copie a URL. No GitHub, em
**Settings → Secrets and variables → Actions → New repository secret**, crie
`RENDER_DEPLOY_HOOK` com essa URL. É o único segredo que o pipeline precisa.

### CORS quando o front ainda não subiu

CORS é uma restrição do **navegador**, não da API: o que vale é a origem de onde
a página está aberta, não onde a API mora. Três consequências práticas:

- **Postman, curl e Insomnia ignoram CORS.** O time pode testar hoje, sem
  configuração nenhuma.
- **O `/docs` também funciona**, porque é servido pela própria API.
- **Enquanto o front roda local** (`npm run dev`) apontando para a API
  publicada, a origem é `http://localhost:5173` — que já é o padrão. Não é
  preciso saber a URL de produção para o time começar.

Quando o front publicar, acrescente a URL dele em `CORS_ORIGENS`. Se for Vercel
ou Netlify, use também `CORS_ORIGENS_REGEX`: essas plataformas criam uma URL
nova a cada preview, e uma lista fixa quebraria em todo PR do front.

```
CORS_ORIGENS_REGEX=https://biosyn-front(-git-[a-z0-9-]+)?\.vercel\.app
```

O padrão é comparado com `fullmatch`, então já fica ancorado nas duas pontas —
`https://biosyn-front.vercel.app.atacante.com` não passa. Ainda assim, seja
específico: `https://.*` libera a internet inteira.

### Detalhes que costumam derrubar o deploy

- **O Render gratuito bloqueia as portas SMTP (25, 465 e 587).** O canal
  `smtp` funciona local, mas no Render a conexão é cortada antes de sair e
  `POST /alertas` responde `502 FALHA_ENVIO_ALERTA`. Lá, use
  `ALERTA_CANAL=brevo`, que envia por HTTPS. A conta gratuita da Brevo manda
  ~300 e-mails/dia; a chave sai de *SMTP & API → API Keys* e o remetente
  precisa estar cadastrado em *Senders*. Com remetente Gmail, a Brevo troca
  o domínio de envio por `@brevosend.com` e mantém o nome "BioSyn".

- **`AMBIENTE=homolog`, não `prod`** — em `prod` a API fecha `/docs`, e é
  justamente por ali que o time de front consulta o contrato.
- **A porta vem de `$PORT`.** O `startCommand` já usa. No Dockerfile, o `CMD`
  está na forma *shell* de propósito: a forma exec não expande variável, o
  serviço subiria na porta errada e o Render derrubaria por timeout sem dizer
  o motivo.
- **Plano gratuito hiberna** após ~15 min sem tráfego, e a primeira requisição
  depois disso leva perto de um minuto (o pool do Oracle é recriado junto).
  Avise o time de front, ou use um plano pago se atrapalhar.
- **`--proxy-headers`** já está no comando: sem ele, atrás do balanceador do
  Render todas as tentativas de login chegam com o IP do proxy e o limite de
  tentativas vira global.

## Decisões que divergem do documento de contrato

O documento original é a referência; onde nos afastamos dele, foi por um motivo:

| Decisão | Por quê |
|---|---|
| Alertas por **e-mail**, não SMS | Não existe SMS gratuito para números brasileiros (A2P é regulado e exige provedor contratado). Os destinatários são os próprios usuários cadastrados, para quem e-mail é o canal natural. Nem a tabela nem a rota mudaram. |
| `FALHA_ENVIO_ALERTA` no lugar de `FALHA_GATEWAY_SMS` | Um código dizendo "SMS" num sistema que manda e-mail engana quem for depurar. |
| Consulta ao banco a cada requisição autenticada | O documento sugere confiar só no token. Sem a consulta, um usuário desativado continuaria operando com privilégio de administrador até o token vencer — até 30 minutos. |
| Códigos `METODO_NAO_PERMITIDO` (405) e `MUITAS_TENTATIVAS` (429) | Não constam na tabela de status do contrato, mas o framework emite 405 de qualquer forma, e sem o 429 o login fica aberto a força bruta. |
| `linhas_retornadas` via `COUNT(*)` sobre o SQL gerado | O contrato pede o campo, mas `showsql` e `narrate` não devolvem contagem. Envolver o SQL em `COUNT(*)` dá o número real sem gastar uma terceira chamada ao modelo. |

## Limitações conhecidas

- **O schema `GOLD` é recriado periodicamente** e isso derruba o `SELECT` do
  backend. Quando `POST /relatorios` responder `502 FALHA_LAKEHOUSE`, um ADMIN
  restaura rodando `scripts/grants_gold.sql`. Na recriação de 2026-09-08 a
  coluna `UF` virou `ESTADO` — o nome da coluna vive em `METRICAS.coluna_filtro`,
  então uma renomeação dessas se resolve com um `UPDATE`, sem mexer em código.
  Surgiram também `GOLD.LEITOS` e `GOLD.OBITOS`, ainda não usadas por métrica
  nenhuma.
- **Select AI indisponível no ambiente atual.** O profile `APP_PROFILE` está
  correto (provider OCI, modelo `cohere.command-a-03-2025`, região
  `sa-saopaulo-1`), mas a chamada trava sem retornar erro — falha também no SQL
  Developer. Depende de credencial/política IAM do lado do ADMIN do ADB. A rota
  responde `502 FALHA_MODELO` ao estourar `AI_TIMEOUT_SEGUNDOS`.
- **As views de métrica não existem.** O modo `fallback` agrega direto de
  `GOLD.INTERNACOES`. Quando as views subirem, troque `LAKEHOUSE_MODO=views`:
  a chave `nome_view` é a mesma nos dois modos.
- **As URLs de embed do dashboard são marcadores.** Substitua em
  `dashboard_configs.url_embbed` pelas URLs reais do Power BI.
- **O limite de tentativas de login vive na memória do processo.** Com várias
  réplicas, cada uma tem o seu contador. Para valer no conjunto, precisa de um
  contador compartilhado.
- **O envio de alertas é síncrono.** Para uma UF com milhares de usuários, vale
  medir antes do lançamento. Fila assíncrona ficou fora do escopo.
- **A URL de embed vai crua no JSON** — quem abrir o DevTools copia o link e
  acessa o painel fora da plataforma. Aceito nesta versão, como o próprio
  documento registra.

## Fora de escopo nesta versão

Histórico de conversas do chat, persistência de relatórios, rastreio de entrega
dos alertas, refresh token, logout no servidor, autocadastro e recuperação de
senha.
