"""Tabela DASHBOARD_CONFIGS."""

from __future__ import annotations

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampsMixin
from app.db.tipos import BooleanoOracle


class DashboardConfig(Base, TimestampsMixin):
    __tablename__ = "dashboard_configs"

    id_dashboard: Mapped[int] = mapped_column(
        Integer, Sequence("dashboard_configs_id_dashboard"), primary_key=True
    )
    nome_aba: Mapped[str] = mapped_column(String(50), unique=True)
    url_embbed: Mapped[str] = mapped_column(String(1000))
    ordem: Mapped[int] = mapped_column(Integer, default=1)
    ativo: Mapped[bool] = mapped_column(BooleanoOracle, default=True)
