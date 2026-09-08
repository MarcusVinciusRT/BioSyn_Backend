"""Secao 4: abas do dashboard.

As tres visoes (Geral, Populacao, Hospitais) foram unificadas numa tela so, com
seletor de abas. Esta rota nao toca em nenhum dos dois bancos de dados de
negocio: apenas devolve as URLs de embed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import dashboard_repository
from app.schemas.dashboard import AbaDashboard, ListaAbas


def listar_abas(db: Session) -> ListaAbas:
    abas = dashboard_repository.listar_abas_ativas(db)
    return ListaAbas(abas=[AbaDashboard.model_validate(a) for a in abas])
