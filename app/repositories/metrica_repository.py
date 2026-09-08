"""Consultas sobre METRICAS: o catalogo de metricas pre-definidas."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session

from app.db.tipos import esta_ativo
from app.models import Metrica


def listar_ativas(db: Session) -> list[Metrica]:
    consulta: Select[tuple[Metrica]] = (
        select(Metrica)
        .where(esta_ativo(Metrica.ativo))
        .order_by(
            func.nlssort(Metrica.nome_metrica, literal_column("'NLS_SORT=BINARY_AI'"))
        )
    )
    return list(db.execute(consulta).scalars().all())


def buscar_ativas_por_ids(db: Session, ids: Iterable[int]) -> dict[int, Metrica]:
    """Indexadas por id, para o service detectar quais nao existem no catalogo."""
    ids = list(ids)
    if not ids:
        return {}
    consulta = select(Metrica).where(
        Metrica.id_metrica.in_(ids), esta_ativo(Metrica.ativo)
    )
    return {m.id_metrica: m for m in db.execute(consulta).scalars().all()}
