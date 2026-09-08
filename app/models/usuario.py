"""Tabela USUARIOS."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampsMixin
from app.db.tipos import BooleanoOracle

if TYPE_CHECKING:
    from app.models.cargo import Cargo
    from app.models.endereco import Endereco
    from app.models.organizacao import Organizacao


class Usuario(Base, TimestampsMixin):
    __tablename__ = "usuarios"

    id_usuario: Mapped[int] = mapped_column(
        Integer, Sequence("usuarios_id_usuario_seq"), primary_key=True
    )
    cpf: Mapped[str] = mapped_column(String(11), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    telefone: Mapped[str] = mapped_column(String(15), unique=True)
    # Hash bcrypt. Nunca sai em resposta da API, em nenhuma rota.
    senha: Mapped[str] = mapped_column(String(255))
    nome: Mapped[str] = mapped_column(String(60))
    sobrenome: Mapped[str] = mapped_column(String(60))
    # Derivado de nome + sobrenome pela API, nunca enviado pelo cliente:
    # e a coluna usada na busca (indice funcional IDX_USUARIOS_NC).
    nome_completo: Mapped[str] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(BooleanoOracle, default=False)
    ativo: Mapped[bool] = mapped_column(BooleanoOracle, default=True)

    cargos_id_cargo: Mapped[int] = mapped_column(Integer, ForeignKey("cargos.id_cargo"))
    enderecos_id_endereco: Mapped[int] = mapped_column(
        Integer, ForeignKey("enderecos.id_endereco")
    )
    organizacoes_id_organizacao: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizacoes.id_organizacao")
    )

    # lazy="raise": um acesso nao planejado estoura no teste em vez de virar
    # N+1 silencioso em producao. Quem precisa da relacao usa joinedload.
    cargo: Mapped[Cargo] = relationship(lazy="raise")
    endereco: Mapped[Endereco] = relationship(lazy="raise")
    organizacao: Mapped[Organizacao] = relationship(lazy="raise")
