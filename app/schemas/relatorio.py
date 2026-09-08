"""Schemas da secao 6 (Relatorios).

Relatorios sao gerados sob demanda e nao sao persistidos: o usuario escolhe as
metricas e o periodo, a API consulta o lakehouse e devolve o resultado.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comum import DataHora

FORMATOS = ("json", "csv", "xlsx")
MAXIMO_METRICAS = 20


# --- Catalogo --------------------------------------------------------------

class MetricaCatalogo(BaseModel):
    id_metrica: int
    # O contrato chama de "nome" aqui; a coluna do DDL e nome_metrica.
    nome: str
    descricao: str


class CatalogoMetricas(BaseModel):
    metricas: list[MetricaCatalogo]


# --- Requisicao ------------------------------------------------------------

class Periodo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inicio: date
    fim: date


class MetricaSolicitada(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id_metrica: int = Field(gt=0)
    # Recorte opcional, aplicado na coluna que METRICAS.coluna_filtro indica.
    filtro: str | None = Field(default=None, max_length=100)


class RelatorioRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # O teto existe para uma requisicao nao virar 200 consultas ao lakehouse.
    metricas: list[MetricaSolicitada] = Field(min_length=1, max_length=MAXIMO_METRICAS)
    periodo: Periodo
    # json para o front renderizar; csv ou xlsx para download do arquivo pronto.
    formato: Literal["json", "csv", "xlsx"] = "json"


# --- Resposta --------------------------------------------------------------

class ResultadoMetrica(BaseModel):
    """Formato padronizado, em vez de uma lista de objetos por metrica.

    E o que permite ao front montar a tabela genericamente, sem conhecer o nome
    dos campos: uma metrica nova nao exige mudanca no front.
    """

    id_metrica: int
    nome: str
    filtro: str | None
    valor: float | None
    unidade: str


class RelatorioResponse(BaseModel):
    gerado_em: DataHora
    periodo: Periodo
    resultados: list[ResultadoMetrica]
