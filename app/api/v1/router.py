"""Agregador das rotas da v1."""

from fastapi import APIRouter

from app.api.v1.routes import (
    alertas,
    apoio,
    auth,
    chat,
    dashboards,
    health,
    relatorios,
    usuarios,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(dashboards.router)
router.include_router(alertas.router)
router.include_router(relatorios.router)
router.include_router(chat.router)
router.include_router(usuarios.router)
router.include_router(apoio.router)
