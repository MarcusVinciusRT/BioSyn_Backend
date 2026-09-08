"""Consultas dos dados de apoio: cargos e organizacoes."""

from __future__ import annotations

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session

from app.db.tipos import esta_ativo
from app.models import Cargo, Organizacao


def _ordem_por_nome(coluna):  # type: ignore[no-untyped-def]
    """Ordenacao linguistica em portugues.

    O ORDER BY binario do Oracle compara code points: "Épico" e "Órgão" cairiam
    depois de "Zelador", e "agente" depois de "Zelador" tambem. NLS_SORT=BINARY_AI
    ignora acento e caixa, que e o que o usuario espera ver num select.
    """
    return func.nlssort(coluna, literal_column("'NLS_SORT=BINARY_AI'"))


def listar_cargos_ativos(db: Session) -> list[Cargo]:
    consulta: Select[tuple[Cargo]] = (
        select(Cargo)
        .where(esta_ativo(Cargo.ativo))
        .order_by(_ordem_por_nome(Cargo.nome_cargo))
    )
    return list(db.execute(consulta).scalars().all())


def listar_organizacoes_ativas(db: Session) -> list[Organizacao]:
    consulta: Select[tuple[Organizacao]] = (
        select(Organizacao)
        .where(esta_ativo(Organizacao.ativo))
        .order_by(_ordem_por_nome(Organizacao.nome_organizacao))
    )
    return list(db.execute(consulta).scalars().all())
