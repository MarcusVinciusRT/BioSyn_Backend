"""Engine e sessao SQLAlchemy sobre o Oracle Autonomous Database.

Um unico engine atende os tres usos do banco: OLTP transacional (tabelas do DDL),
leitura do lakehouse GOLD (relatorios) e Select AI (chat). O usuario APP_BACKEND
escreve no proprio schema e le GOLD.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db import wallet

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _criar_engine(settings: Settings) -> Engine:
    """Cria o engine com um pool do proprio oracledb (thin mode, sem Instant Client)."""
    parametros_pool: dict[str, object] = {
        "user": settings.db_user,
        "password": settings.db_password,
        "dsn": settings.db_dsn,
        "min": settings.db_pool_min,
        "max": settings.db_pool_max,
        "increment": 1,
    }

    # mTLS: o diretorio vem de WALLET_BASE64 (hospedagem) ou de WALLET_DIR
    # (desenvolvimento). Em TLS puro nao ha wallet e o DSN carrega tudo.
    diretorio = wallet.preparar(settings.wallet_base64, settings.caminho_wallet)
    if diretorio:
        parametros_pool["config_dir"] = diretorio
        parametros_pool["wallet_location"] = diretorio
        if settings.wallet_password:
            parametros_pool["wallet_password"] = settings.wallet_password

    pool = oracledb.create_pool(**parametros_pool)  # type: ignore[arg-type]

    # NullPool: quem faz o pooling e o oracledb (acima). Sem isso o SQLAlchemy
    # empilharia um QueuePool proprio por cima, dobrando as conexoes.
    return create_engine(
        "oracle+oracledb://",
        creator=pool.acquire,
        poolclass=NullPool,
        echo=False,
        future=True,
    )


def iniciar_banco() -> None:
    """Chamado no lifespan do FastAPI."""
    global _engine, _SessionLocal
    if _engine is not None:
        return
    settings = get_settings()
    _engine = _criar_engine(settings)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    logger.info("pool oracle iniciado dsn=%s wallet=%s", settings.db_dsn, settings.usa_wallet)
    _conferir_fuso_do_banco()


def _conferir_fuso_do_banco() -> None:
    """Torna explicita a suposicao do TimestampComFuso.

    O driver descarta o offset das colunas TIMESTAMP WITH TIME ZONE, e nos
    tratamos o valor que sobra como UTC. Isso so vale porque SYSTIMESTAMP grava
    no fuso do banco e esse fuso e UTC. Se um dia deixar de ser, os horarios da
    API saem errados em silencio -- entao conferimos e gritamos no log.
    """
    try:
        with get_engine().connect() as conexao:
            fuso = conexao.execute(text("SELECT DBTIMEZONE FROM DUAL")).scalar_one()
    except Exception:
        logger.warning("nao foi possivel conferir o DBTIMEZONE")
        return

    if str(fuso).strip() in ("+00:00", "UTC"):
        logger.info("fuso do banco: %s", fuso)
    else:
        logger.error(
            "DBTIMEZONE=%s, esperado +00:00. Os timestamps da API sairao com o "
            "fuso errado: revise TimestampComFuso em app/db/tipos.py",
            fuso,
        )


def encerrar_banco() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
        logger.info("pool oracle encerrado")


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Banco nao iniciado. iniciar_banco() nao foi chamado.")
    return _engine


def criar_sessao() -> Session:
    """Sessao crua, sem gerenciamento. Quem chama fecha -- e o que a dependencia
    get_db faz por requisicao."""
    if _SessionLocal is None:
        raise RuntimeError("Banco nao iniciado. iniciar_banco() nao foi chamado.")
    return _SessionLocal()


@contextmanager
def sessao() -> Iterator[Session]:
    """Sessao com commit/rollback automatico. Uso fora do ciclo de request."""
    if _SessionLocal is None:
        raise RuntimeError("Banco nao iniciado. iniciar_banco() nao foi chamado.")
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def banco_saudavel() -> bool:
    """Ping usado pela rota /health."""
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1 FROM DUAL")).scalar_one()
        return True
    except Exception:
        logger.exception("health check do banco falhou")
        return False
