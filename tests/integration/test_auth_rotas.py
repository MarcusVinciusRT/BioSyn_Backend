"""Rotas de autenticacao e as dependencias de autorizacao.

Usa dependency_overrides para nao depender do Oracle: aqui o alvo e a fiacao
(status, envelope, formato da resposta), nao a persistencia.
"""

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.security import criar_token
from app.repositories import usuario_repository
from tests.unit.test_auth_service import SENHA, montar_usuario


@pytest.fixture
def app_teste(monkeypatch):
    """App real, com a sessao de banco neutralizada."""
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None

    # Rotas protegidas exigem admin em outros steps; aqui basta o /auth/me.
    @app.get("/api/v1/_so-admin")
    def _so_admin(admin: deps.AdminDep) -> dict[str, int]:
        return {"id": admin.id_usuario}

    return app


@pytest.fixture
def cliente(app_teste):
    # sem lifespan: nao abre pool contra o Oracle
    return TestClient(app_teste, raise_server_exceptions=False)


def _instalar_usuario(monkeypatch, usuario):
    monkeypatch.setattr(usuario_repository, "buscar_por_email", lambda db, e: usuario)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)


def _token_de(usuario) -> str:
    token, _ = criar_token(usuario.id_usuario, usuario.email, usuario.is_admin)
    return token


# --- POST /auth/login ------------------------------------------------------

def test_login_responde_no_formato_do_contrato(cliente, monkeypatch):
    _instalar_usuario(monkeypatch, montar_usuario())
    r = cliente.post(
        "/api/v1/auth/login",
        json={"email": "maria.santos@saude.gov.br", "senha": SENHA},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert set(corpo) == {"access_token", "token_type", "expira_em", "usuario"}
    assert corpo["token_type"] == "bearer"
    assert corpo["expira_em"] == 1800
    assert set(corpo["usuario"]) == {
        "id_usuario", "nome_completo", "email", "is_admin", "cargo", "organizacao",
    }


def test_login_com_senha_errada_e_401(cliente, monkeypatch):
    _instalar_usuario(monkeypatch, montar_usuario())
    r = cliente.post(
        "/api/v1/auth/login",
        json={"email": "maria.santos@saude.gov.br", "senha": "errada"},
    )
    assert r.status_code == 401
    assert r.json()["erro"]["codigo"] == "CREDENCIAIS_INVALIDAS"


def test_login_com_email_malformado_e_422(cliente, monkeypatch):
    _instalar_usuario(monkeypatch, None)
    r = cliente.post("/api/v1/auth/login", json={"email": "xxx", "senha": "12345678"})
    assert r.status_code == 422
    assert r.json()["erro"]["campos"] == [
        {"campo": "email", "detalhe": "E-mail em formato inválido."}
    ]


# --- GET /auth/me ----------------------------------------------------------

def test_me_devolve_o_mesmo_objeto_usuario_do_login(cliente, monkeypatch):
    usuario = montar_usuario()
    _instalar_usuario(monkeypatch, usuario)

    login = cliente.post(
        "/api/v1/auth/login",
        json={"email": "maria.santos@saude.gov.br", "senha": SENHA},
    ).json()
    me = cliente.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json() == login["usuario"]


def test_me_sem_token_e_401(cliente):
    r = cliente.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["erro"]["codigo"] == "NAO_AUTENTICADO"


def test_me_com_token_adulterado_e_401(cliente, monkeypatch):
    _instalar_usuario(monkeypatch, montar_usuario())
    r = cliente.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


def test_usuario_desativado_perde_a_sessao_mesmo_com_token_valido(cliente, monkeypatch):
    """Sem a consulta ao banco na dependencia, um admin desativado continuaria
    operando ate o token vencer -- ate 30 minutos."""
    usuario = montar_usuario(ativo=True)
    token = _token_de(usuario)

    _instalar_usuario(monkeypatch, montar_usuario(ativo=False))
    r = cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["erro"]["codigo"] == "NAO_AUTENTICADO"


def test_usuario_apagado_perde_a_sessao(cliente, monkeypatch):
    token = _token_de(montar_usuario())
    _instalar_usuario(monkeypatch, None)
    r = cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# --- Autorizacao -----------------------------------------------------------

def test_rota_de_admin_aceita_administrador(cliente, monkeypatch):
    admin = montar_usuario(is_admin=True)
    _instalar_usuario(monkeypatch, admin)
    r = cliente.get(
        "/api/v1/_so-admin", headers={"Authorization": f"Bearer {_token_de(admin)}"}
    )
    assert r.status_code == 200


def test_rota_de_admin_recusa_usuario_comum_com_403(cliente, monkeypatch):
    comum = montar_usuario(is_admin=False)
    _instalar_usuario(monkeypatch, comum)
    r = cliente.get(
        "/api/v1/_so-admin", headers={"Authorization": f"Bearer {_token_de(comum)}"}
    )
    assert r.status_code == 403
    assert r.json()["erro"]["codigo"] == "ACESSO_NEGADO"


def test_privilegio_vem_do_banco_e_nao_do_token(cliente, monkeypatch):
    """Um token forjado com is_admin=true nao promove ninguem: quem decide e a
    coluna is_admin da linha do usuario."""
    comum = montar_usuario(is_admin=False)
    _instalar_usuario(monkeypatch, comum)

    token_mentiroso, _ = criar_token(comum.id_usuario, comum.email, is_admin=True)
    r = cliente.get(
        "/api/v1/_so-admin", headers={"Authorization": f"Bearer {token_mentiroso}"}
    )
    assert r.status_code == 403
