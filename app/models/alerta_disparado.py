"""Tabela ALERTA_DISPARADOS: log de um disparo de alerta por UF.

A tabela nao amarra canal nenhum: guarda mensagem, UF de destino, quantos
receberam e quem disparou. Serviu para SMS e serve para e-mail sem mudanca.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CHAR, ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampsMixin

if TYPE_CHECKING:
    from app.models.usuario import Usuario


class AlertaDisparado(Base, TimestampsMixin):
    __tablename__ = "alerta_disparados"

    id_alerta: Mapped[int] = mapped_column(
        Integer, Sequence("alerta_disparados_id_alerta"), primary_key=True
    )
    mensagem: Mapped[str] = mapped_column(String(500))
    estado_uf_destino: Mapped[str] = mapped_column(CHAR(2))
    # Quantidade de destinatarios aceitos pelo canal nesse disparo. Nao ha
    # rastreio de entrega individual.
    destinatarios: Mapped[int] = mapped_column(Integer, default=0)
    usuarios_id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id_usuario")
    )

    usuario: Mapped[Usuario] = relationship(lazy="raise")
