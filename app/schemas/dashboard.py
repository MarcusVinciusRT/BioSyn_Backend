"""Schemas da secao 4 (Dashboard).

A API nao processa nem agrega dado nenhum aqui: devolve a lista de abas
configuradas e o front embute o painel correspondente em um iframe.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AbaDashboard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_dashboard: int
    nome_aba: str
    # Grafia com dois "b" vem da coluna do DDL. Mantida no JSON de proposito:
    # e o nome que o front ja consome.
    url_embbed: str


class ListaAbas(BaseModel):
    # Envelope "abas", nao "itens" -- e o que o contrato especifica nesta rota.
    abas: list[AbaDashboard]
