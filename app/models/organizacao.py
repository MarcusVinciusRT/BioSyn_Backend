"""Tabela ORGANIZACOES."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampsMixin
from app.db.tipos import BooleanoOracle

if TYPE_CHECKING:
    from app.models.endereco import Endereco


class Organizacao(Base, TimestampsMixin):
    __tablename__ = "organizacoes"

    id_organizacao: Mapped[int] = mapped_column(
        Integer, Sequence("organizacoes_id_organizacao"), primary_key=True
    )
    nome_organizacao: Mapped[str] = mapped_column(String(100), unique=True)
    enderecos_id_endereco: Mapped[int] = mapped_column(
        Integer, ForeignKey("enderecos.id_endereco")
    )
    ativo: Mapped[bool] = mapped_column(BooleanoOracle, default=True)

    endereco: Mapped[Endereco] = relationship(lazy="raise")
