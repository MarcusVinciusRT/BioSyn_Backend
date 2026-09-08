"""Consultas encapsuladas por agregado. Services falam com o banco so por aqui."""

from app.repositories import (
    alerta_repository,
    apoio_repository,
    dashboard_repository,
    metrica_repository,
    usuario_repository,
)

__all__ = [
    "alerta_repository",
    "apoio_repository",
    "dashboard_repository",
    "metrica_repository",
    "usuario_repository",
]
