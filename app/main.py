"""BioSyn API — plataforma integrada de dados em saude publica."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as router_v1
from app.core.config import get_settings
from app.core.handlers import registrar_handlers
from app.core.logging import RequestIdMiddleware, configurar_logging
from app.db.session import encerrar_banco, iniciar_banco


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    iniciar_banco()
    yield
    encerrar_banco()


def criar_app() -> FastAPI:
    settings = get_settings()
    configurar_logging(settings.log_level)

    # Em producao a documentacao interativa fica fechada: ela expoe a superficie
    # inteira da API (rotas, schemas, exemplos) a quem so tem a URL.
    documentacao_aberta = settings.ambiente != "prod"

    app = FastAPI(
        title="BioSyn API",
        description="Plataforma integrada de dados em saude publica.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if documentacao_aberta else None,
        redoc_url="/redoc" if documentacao_aberta else None,
        openapi_url="/openapi.json" if documentacao_aberta else None,
    )

    # CORS por ultimo no add_middleware = mais externo na pilha, para que a
    # resposta de erro tambem carregue os cabecalhos de CORS.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origens,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    registrar_handlers(app)
    app.include_router(router_v1, prefix=settings.api_prefixo)
    return app


app = criar_app()
