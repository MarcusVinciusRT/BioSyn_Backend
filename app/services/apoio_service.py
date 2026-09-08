"""Secao 8: dados de apoio para os selects do formulario de usuario.

So registros ativos, ordenados por nome. Nao ha regra alem disso -- o service
existe para manter a rota longe do repositorio, como no resto da aplicacao.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import apoio_repository
from app.schemas.apoio import (
    CargoItem,
    ListaCargos,
    ListaOrganizacoes,
    OrganizacaoItem,
)


def listar_cargos(db: Session) -> ListaCargos:
    cargos = apoio_repository.listar_cargos_ativos(db)
    return ListaCargos(itens=[CargoItem.model_validate(c) for c in cargos])


def listar_organizacoes(db: Session) -> ListaOrganizacoes:
    organizacoes = apoio_repository.listar_organizacoes_ativas(db)
    return ListaOrganizacoes(
        itens=[OrganizacaoItem.model_validate(o) for o in organizacoes]
    )
