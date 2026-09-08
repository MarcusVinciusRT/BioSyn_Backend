"""Secao 4 do contrato: Dashboard."""

from fastapi import APIRouter

from app.core.deps import SessaoDep, UsuarioDep
from app.schemas.dashboard import ListaAbas
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboards", response_model=ListaAbas, summary="Listar abas do dashboard")
def listar_dashboards(db: SessaoDep, _: UsuarioDep) -> ListaAbas:
    """Acesso: qualquer usuário autenticado.

    Retorna as abas ativas ordenadas para exibição. O front monta um botão por
    aba e troca o src do iframe conforme a seleção.
    """
    return dashboard_service.listar_abas(db)
