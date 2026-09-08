"""Consultas sobre DASHBOARD_CONFIGS."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.tipos import esta_ativo
from app.models import DashboardConfig


def listar_abas_ativas(db: Session) -> list[DashboardConfig]:
    """Abas ativas na ordem de exibicao definida pela coluna `ordem`.

    O desempate por id mantem a ordem estavel quando duas abas sao configuradas
    com o mesmo valor de `ordem` -- sem ele, o banco pode devolver em ordem
    diferente a cada consulta e as abas trocariam de lugar no front.
    """
    consulta: Select[tuple[DashboardConfig]] = (
        select(DashboardConfig)
        .where(esta_ativo(DashboardConfig.ativo))
        .order_by(DashboardConfig.ordem, DashboardConfig.id_dashboard)
    )
    return list(db.execute(consulta).scalars().all())
