"""Tabela CARGOS."""

from __future__ import annotations

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampsMixin
from app.db.tipos import BooleanoOracle


class Cargo(Base, TimestampsMixin):
    __tablename__ = "cargos"

    id_cargo: Mapped[int] = mapped_column(
        Integer, Sequence("cargos_id_cargo_seq"), primary_key=True
    )
    nome_cargo: Mapped[str] = mapped_column(String(100), unique=True)
    ativo: Mapped[bool] = mapped_column(BooleanoOracle, default=True)
