"""Base declarativa e mapeamentos comuns as tabelas do DDL BioSyn."""

from datetime import datetime

from sqlalchemy import FetchedValue
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.tipos import TimestampComFuso


class Base(DeclarativeBase):
    pass


class TimestampsMixin:
    """criado_em / atualizado_em sao responsabilidade exclusiva do banco.

    O DEFAULT SYSTIMESTAMP preenche na insercao e as triggers *_UPD_TRG mantem
    atualizado_em e congelam criado_em em todo UPDATE. A aplicacao nunca escreve
    nessas colunas -- por isso FetchedValue() em vez de default do Python.
    """

    criado_em: Mapped[datetime] = mapped_column(
        TimestampComFuso,
        server_default=FetchedValue(),
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TimestampComFuso,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )
