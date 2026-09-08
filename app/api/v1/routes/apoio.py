"""Secao 8 do contrato: Dados de apoio.

Rotas auxiliares que alimentam os campos de selecao do formulario de cadastro
de usuario. Retornam apenas registros ativos, ordenados por nome.
"""

from fastapi import APIRouter

from app.core.deps import AdminDep, SessaoDep
from app.schemas.apoio import ListaCargos, ListaOrganizacoes
from app.services import apoio_service

router = APIRouter(tags=["dados de apoio"])


@router.get("/cargos", response_model=ListaCargos, summary="Listar cargos")
def listar_cargos(db: SessaoDep, _: AdminDep) -> ListaCargos:
    """Acesso: somente administrador."""
    return apoio_service.listar_cargos(db)


@router.get(
    "/organizacoes", response_model=ListaOrganizacoes, summary="Listar organizações"
)
def listar_organizacoes(db: SessaoDep, _: AdminDep) -> ListaOrganizacoes:
    """Acesso: somente administrador."""
    return apoio_service.listar_organizacoes(db)
