"""Tipos de coluna proprios do mapeamento BioSyn."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Dialect, Numeric
from sqlalchemy.types import TypeDecorator


class BooleanoOracle(TypeDecorator[bool]):
    """NUMBER(1) com CHECK (col IN (0,1)) <-> bool do Python.

    O DDL nao usa o tipo BOOLEAN do Oracle 23ai; usa NUMBER(1) com constraint.
    Este decorator deixa `ativo` e `is_admin` serem bool no ORM e nos schemas,
    sem espalhar conversao 0/1 pelos services.
    """

    impl = Numeric(1, 0)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        return 1 if value else 0

    def process_result_value(self, value: Any, dialect: Dialect) -> bool | None:
        if value is None:
            return None
        return bool(value)


def esta_ativo(coluna: Any) -> Any:
    """Filtro `ativo = 1` para as colunas NUMBER(1) do DDL.

    Nao use `coluna.is_(True)`: como a coluna nao e um BOOLEAN nativo, o Oracle
    recebe `ativo IS :param` e recusa com ORA-00908. A comparacao por igualdade
    deixa o BooleanoOracle converter True em 1 no bind.
    """
    return coluna == True  # noqa: E712


class TimestampComFuso(TypeDecorator[datetime]):
    """TIMESTAMP WITH TIME ZONE que sempre chega ao Python como aware, em UTC.

    O python-oracledb em modo thin devolve TSTZ como datetime *naive*,
    descartando o offset sem converter o horario:

        TIMESTAMP '2026-01-01 10:00:00 -05:00'  ->  datetime(2026, 1, 1, 10, 0)
        TIMESTAMP '2026-01-01 15:00:00 +00:00'  ->  datetime(2026, 1, 1, 15, 0)

    Os dois sao o mesmo instante e voltam com horas diferentes. Sem tratamento,
    a API serializaria sem fuso e o front erraria o horario.

    Nossas colunas sao preenchidas por SYSTIMESTAMP, que grava no fuso do banco.
    Como esse fuso e UTC (conferido na inicializacao, em db.session), o valor
    naive que chega e UTC -- e aqui apenas rotulamos como tal.
    """

    impl = TIMESTAMP(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
