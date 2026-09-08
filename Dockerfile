# Python 3.13: o pydantic-core ainda nao tem wheel para 3.14 e a compilacao falha.
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primeiro: a camada so e refeita quando o requirements muda.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Usuario sem privilegio: se a aplicacao for comprometida, o atacante nao e root.
RUN useradd --create-home --uid 10001 biosyn \
    && chown -R biosyn:biosyn /app
USER biosyn

# O wallet NAO vai na imagem: monte como volume ou secret do orquestrador, para
# a credencial nao ficar gravada em camada de imagem.
#   docker run -v /caminho/wallet:/app/wallet:ro --env-file .env ...
ENV WALLET_DIR=/app/wallet

# O Render (e a maioria dos PaaS) injeta a porta em $PORT. O EXPOSE e so
# documentacao; quem manda e o CMD abaixo.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
porta=os.environ.get('PORT','8000'); \
sys.exit(0 if urllib.request.urlopen(f'http://localhost:{porta}/api/v1/health', timeout=5).status==200 else 1)"

# Forma shell de proposito: a forma exec (["uvicorn", ...]) nao expande $PORT,
# e o servico subiria na porta errada -- o Render derruba o deploy por timeout
# sem dizer o motivo.
#
# --proxy-headers: sem isso, atras do balanceador do Render todas as tentativas
# de login chegam com o IP do proxy e o limite de tentativas vira global.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} \
    --proxy-headers --forwarded-allow-ips '*'
