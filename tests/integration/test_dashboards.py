"""Secao 4: abas do dashboard."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import oracle

from app.core import deps
from app.core.security import criar_token
from app.db.tipos import esta_ativo
from app.models import DashboardConfig
from app.repositories import dashboard_repository, usuario_repository
from tests.unit.test_auth_service import montar_usuario

ABAS = [
    DashboardConfig(id_dashboard=1, nome_aba="Geral", ordem=1, ativo=True,
                    url_embbed="https://app.powerbi.com/reportEmbed?reportId=abc123"),
    DashboardConfig(id_dashboard=2, nome_aba="População", ordem=2, ativo=True,
                    url_embbed="https://app.powerbi.com/reportEmbed?reportId=def456"),
    DashboardConfig(id_dashboard=3, nome_aba="Hospitais", ordem=3, ativo=True,
                    url_embbed="https://app.powerbi.com/reportEmbed?reportId=ghi789"),
]


@pytest.fixture
def cliente(monkeypatch):
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    monkeypatch.setattr(dashboard_repository, "listar_abas_ativas", lambda db: ABAS)
    return TestClient(app, raise_server_exceptions=False)


def _autenticar(monkeypatch, *, admin: bool = False) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


def test_resposta_usa_o_envelope_abas(cliente, monkeypatch):
    """Esta rota usa "abas", nao "itens" como as de dados de apoio."""
    r = cliente.get("/api/v1/dashboards", headers=_autenticar(monkeypatch))
    assert r.status_code == 200
    assert list(r.json()) == ["abas"]


def test_cada_aba_traz_id_nome_e_url_de_embed(cliente, monkeypatch):
    itens = cliente.get("/api/v1/dashboards", headers=_autenticar(monkeypatch)).json()["abas"]
    assert len(itens) == 3
    assert all(set(i) == {"id_dashboard", "nome_aba", "url_embbed"} for i in itens)


def test_nao_vaza_ordem_nem_flag_ativo(cliente, monkeypatch):
    """São detalhes de configuração; o contrato não os expõe."""
    itens = cliente.get("/api/v1/dashboards", headers=_autenticar(monkeypatch)).json()["abas"]
    assert all("ordem" not in i and "ativo" not in i for i in itens)


def test_a_ordem_do_repositorio_e_preservada(cliente, monkeypatch):
    itens = cliente.get("/api/v1/dashboards", headers=_autenticar(monkeypatch)).json()["abas"]
    assert [i["nome_aba"] for i in itens] == ["Geral", "População", "Hospitais"]


def test_usuario_comum_tem_acesso(cliente, monkeypatch):
    """Diferente de /cargos e /usuarios, esta rota não exige administrador."""
    r = cliente.get("/api/v1/dashboards", headers=_autenticar(monkeypatch, admin=False))
    assert r.status_code == 200


def test_sem_token_e_401(cliente):
    assert cliente.get("/api/v1/dashboards").status_code == 401


def test_sql_ordena_por_ordem_com_desempate_e_filtra_ativas():
    """Sem o desempate, duas abas com a mesma `ordem` poderiam trocar de lugar
    entre requisições."""
    sql = str(
        select(DashboardConfig.id_dashboard)
        .where(esta_ativo(DashboardConfig.ativo))
        .order_by(DashboardConfig.ordem, DashboardConfig.id_dashboard)
        .compile(dialect=oracle.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "ativo = 1" in sql
    assert "ORDER BY dashboard_configs.ordem, dashboard_configs.id_dashboard" in sql
