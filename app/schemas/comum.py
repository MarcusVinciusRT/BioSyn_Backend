"""Tipos compartilhados pelos schemas de resposta."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import PlainSerializer

from app.core.config import get_settings


@lru_cache
def _fuso() -> ZoneInfo:
    return ZoneInfo(get_settings().fuso_horario)


def para_fuso_local(valor: datetime) -> datetime:
    """Converte para o fuso de apresentacao configurado.

    Internamente tudo trafega em UTC; toda saida visivel ao usuario -- JSON,
    nome de arquivo, cabecalho de planilha -- passa por aqui. Sem isso, partes
    diferentes da mesma resposta mostram horarios diferentes.
    """
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone(_fuso())


def _serializar(valor: datetime) -> str:
    """ISO 8601 com fuso, como a secao 2.1 do contrato exige.

    Os segundos sao truncados: o contrato exemplifica com
    "2026-08-22T15:02:44-03:00", sem fracao, e microssegundo de banco nao
    interessa a nenhum consumidor da API.
    """
    return para_fuso_local(valor).replace(microsecond=0).isoformat()


# Use em todo campo de data/hora de resposta.
DataHora = Annotated[datetime, PlainSerializer(_serializar, return_type=str)]
