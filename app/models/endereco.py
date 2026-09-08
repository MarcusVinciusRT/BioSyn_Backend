"""Tabela ENDERECOS."""

from __future__ import annotations

from sqlalchemy import CHAR, Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampsMixin
from app.db.tipos import BooleanoOracle

# Espelha a constraint CK_TIPO_LOGRADOURO do DDL. Repetir aqui deixa a API
# recusar o valor com 422 em vez de deixar o banco estourar ORA-02290.
TIPOS_LOGRADOURO = (
    "Alameda", "Avenida", "Beco", "Condomínio", "Estrada",
    "Loteamento", "Praça", "Rodovia", "Rua", "Travessa",
)


class Endereco(Base, TimestampsMixin):
    __tablename__ = "enderecos"

    id_endereco: Mapped[int] = mapped_column(
        Integer, Sequence("enderecos_id_endereco_seq"), primary_key=True
    )
    tipo_logradouro: Mapped[str] = mapped_column(String(15))
    logradouro: Mapped[str] = mapped_column(String(120))
    numero: Mapped[str] = mapped_column(String(10))
    cep: Mapped[str] = mapped_column(String(8))
    estado_uf: Mapped[str] = mapped_column(CHAR(2))
    cidade: Mapped[str] = mapped_column(String(50))
    complemento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ativo: Mapped[bool] = mapped_column(BooleanoOracle, default=True)
