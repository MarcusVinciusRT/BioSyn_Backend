"""Tabela LOGS_AUDITORIA.

Somente leitura para a aplicacao: quem escreve aqui sao as triggers *_AUD_TRG,
na mesma transacao da DML. A API nunca insere nesta tabela.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, FetchedValue, Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.tipos import TimestampComFuso


class LogAuditoria(Base):
    __tablename__ = "logs_auditoria"

    id_log: Mapped[int] = mapped_column(
        Integer, Sequence("logs_auditoria_id_log_seq"), primary_key=True
    )
    id_linha: Mapped[int] = mapped_column(Integer)
    tabela: Mapped[str] = mapped_column(String(40))
    acao: Mapped[str] = mapped_column(String(10))
    dados_antigos: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dados_novos: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usuario_db: Mapped[str] = mapped_column(String(50), server_default=FetchedValue())
    criado_em: Mapped[datetime] = mapped_column(
        TimestampComFuso, server_default=FetchedValue()
    )
