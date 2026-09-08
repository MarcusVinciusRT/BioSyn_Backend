"""Rotas da secao 8 (dados de apoio)."""

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.security import criar_token
from app.models import Cargo, Organizacao
from app.repositories import apoio_repository, usuario_repository
from tests.unit.test_auth_service import montar_usuario

CARGOS = [
    Cargo(id_cargo=1, nome_cargo="Administrador do Sistema", ativo=True),
    Cargo(id_cargo=3, nome_cargo="Agente Comunitário de Saúde", ativo=True),
    Cargo(id_cargo=2, nome_cargo="Analista Epidemiológico", ativo=True),
]
ORGS = [
    Organizacao(id_organizacao=2, nome_organizacao="Fundação Oswaldo Cruz",
                enderecos_id_endereco=1, ativo=True),
    Organizacao(id_organizacao=1, nome_organizacao="Ministério da Saúde",
                enderecos_id_endereco=1, ativo=True),
]


@pytest.fixture
def cliente(monkeypatch):
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    monkeypatch.setattr(apoio_repository, "listar_cargos_ativos", lambda db: CARGOS)
    monkeypatch.setattr(apoio_repository, "listar_organizacoes_ativas", lambda db: ORGS)
    return TestClient(app, raise_server_exceptions=False)


def _autenticar(monkeypatch, *, admin: bool) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("rota", ["/api/v1/cargos", "/api/v1/organizacoes"])
def test_resposta_usa_o_envelope_itens(cliente, monkeypatch, rota):
    r = cliente.get(rota, headers=_autenticar(monkeypatch, admin=True))
    assert r.status_code == 200
    assert list(r.json()) == ["itens"]


def test_cargos_devolve_apenas_id_e_nome(cliente, monkeypatch):
    r = cliente.get("/api/v1/cargos", headers=_autenticar(monkeypatch, admin=True))
    itens = r.json()["itens"]
    assert len(itens) == 3
    assert all(set(i) == {"id_cargo", "nome_cargo"} for i in itens)


def test_organizacoes_nao_vaza_o_endereco_nem_o_flag_ativo(cliente, monkeypatch):
    """O contrato so pede id e nome; expor mais seria vazamento de modelo."""
    r = cliente.get("/api/v1/organizacoes", headers=_autenticar(monkeypatch, admin=True))
    itens = r.json()["itens"]
    assert all(set(i) == {"id_organizacao", "nome_organizacao"} for i in itens)


def test_a_ordem_do_repositorio_e_preservada(cliente, monkeypatch):
    """Quem ordena e o banco (NLSSORT); o service nao pode reordenar."""
    r = cliente.get("/api/v1/cargos", headers=_autenticar(monkeypatch, admin=True))
    assert [i["nome_cargo"] for i in r.json()["itens"]] == [
        c.nome_cargo for c in CARGOS
    ]


@pytest.mark.parametrize("rota", ["/api/v1/cargos", "/api/v1/organizacoes"])
def test_usuario_comum_recebe_403(cliente, monkeypatch, rota):
    r = cliente.get(rota, headers=_autenticar(monkeypatch, admin=False))
    assert r.status_code == 403
    assert r.json()["erro"]["codigo"] == "ACESSO_NEGADO"


@pytest.mark.parametrize("rota", ["/api/v1/cargos", "/api/v1/organizacoes"])
def test_sem_token_recebe_401(cliente, rota):
    assert cliente.get(rota).status_code == 401
