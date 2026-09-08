"""Schemas da secao 8 (Dados de apoio).

Alimentam os selects do formulario de cadastro de usuario. Envelope {"itens": [...]}
em ambas as rotas, como o contrato especifica.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CargoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cargo: int
    nome_cargo: str


class OrganizacaoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_organizacao: int
    nome_organizacao: str


class ListaCargos(BaseModel):
    itens: list[CargoItem]


class ListaOrganizacoes(BaseModel):
    itens: list[OrganizacaoItem]
