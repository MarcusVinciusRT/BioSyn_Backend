"""Logging interno da API (secao 2.5 do contrato).

Sem correlacao com a tabela de auditoria: aqui o objetivo e so conseguir depurar
onde e por que o codigo falhou, em desenvolvimento e depois do lancamento.

Cada requisicao ganha um request_id que aparece em toda linha de log daquele
ciclo e volta ao cliente no cabecalho X-Request-Id -- assim um erro relatado
pelo front se liga ao rastro no servidor.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Rotas que nao geram log de acesso, para nao poluir com ruido de monitoramento.
ROTAS_SILENCIOSAS = frozenset({"/api/v1/health", "/openapi.json", "/docs", "/redoc"})


def request_id_atual() -> str:
    return _request_id.get()


class _FiltroRequestId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configurar_logging(nivel: str = "INFO") -> None:
    formato = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(formato, datefmt="%Y-%m-%dT%H:%M:%S%z"))
    handler.addFilter(_FiltroRequestId())

    raiz = logging.getLogger()
    raiz.handlers.clear()
    raiz.addHandler(handler)
    raiz.setLevel(nivel.upper())

    # O uvicorn.access duplicaria o log que o middleware abaixo ja produz,
    # e sem o request_id.
    logging.getLogger("uvicorn.access").disabled = True
    for ruidoso in ("uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Atribui o request_id e loga metodo, rota, status e latencia.

    Nunca loga corpo de requisicao nem cabecalho Authorization: senha, CPF e
    token jamais entram no arquivo de log.
    """

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.logger = logging.getLogger("biosyn.acesso")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Aceita um id vindo do front/proxy para amarrar o rastro ponta a ponta.
        identificador = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        token = _request_id.set(identificador)
        inicio = time.perf_counter()

        try:
            resposta = await call_next(request)
        except Exception:
            duracao_ms = (time.perf_counter() - inicio) * 1000
            self.logger.exception(
                "%s %s -> excecao nao tratada em %.1fms",
                request.method,
                request.url.path,
                duracao_ms,
            )
            _request_id.reset(token)
            raise

        duracao_ms = (time.perf_counter() - inicio) * 1000
        resposta.headers["X-Request-Id"] = identificador

        if request.url.path not in ROTAS_SILENCIOSAS:
            nivel = logging.WARNING if resposta.status_code >= 500 else logging.INFO
            self.logger.log(
                nivel,
                "%s %s -> %d em %.1fms",
                request.method,
                request.url.path,
                resposta.status_code,
                duracao_ms,
            )

        _request_id.reset(token)
        return resposta
