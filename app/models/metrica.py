"""Tabela METRICAS: catalogo das consultas pre-definidas do lakehouse."""

from __future__ import annotations

from sqlalchemy import Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampsMixin
from app.db.tipos import BooleanoOracle

# Espelha a constraint CK_METRICAS_UNIDADE do DDL.
UNIDADES = ("numero", "percentual")


class Metrica(Base, TimestampsMixin):
    __tablename__ = "metricas"

    id_metrica: Mapped[int] = mapped_column(
        Integer, Sequence("metricas_id_metrica_seq"), primary_key=True
    )
    nome_metrica: Mapped[str] = mapped_column(String(40), unique=True)
    # Nome da view do lakehouse que devolve a metrica. Vem sempre do banco,
    # nunca do cliente -- e o que permite montar o SQL do relatorio com seguranca.
    nome_view: Mapped[str] = mapped_column(String(50), unique=True)
    coluna_filtro: Mapped[str] = mapped_column(String(30))
    descricao: Mapped[str] = mapped_column(String(80))
    unidade: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(BooleanoOracle, default=True)
