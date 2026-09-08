"""Rotas da secao 7: autorizacao, paginacao e contrato de resposta."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.errors import AppError, CodigoErro
from app.core.security import criar_token
from app.repositories import usuario_repository
from app.schemas.usuario import PaginaUsuarios, UsuarioCriado
from app.services import usuario_service
from tests.unit.test_auth_service import montar_usuario
from tests.unit.test_usuario_schemas import USUARIO_OK


@pytest.fixture
def cliente():
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _autenticar(monkeypatch, *, admin: bool = True) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


# --- Autorizacao -----------------------------------------------------------

CHAMADAS = [
    ("get", "/api/v1/usuarios", None),
    ("post", "/api/v1/usuarios", USUARIO_OK),
    ("put", "/api/v1/usuarios/9", {k: v for k, v in USUARIO_OK.items() if k != "cpf"}),
    ("delete", "/api/v1/usuarios/9", None),
]


@pytest.mark.parametrize(("metodo", "rota", "corpo"), CHAMADAS)
def test_toda_rota_de_usuario_exige_administrador(cliente, monkeypatch, metodo, rota, corpo):
    extras = {"json": corpo} if corpo is not None else {}
    r = getattr(cliente, metodo)(
        rota, headers=_autenticar(monkeypatch, admin=False), **extras
    )
    assert r.status_code == 403
    assert r.json()["erro"]["codigo"] == "ACESSO_NEGADO"


@pytest.mark.parametrize(("metodo", "rota", "corpo"), CHAMADAS)
def test_toda_rota_de_usuario_exige_token(cliente, metodo, rota, corpo):
    extras = {"json": corpo} if corpo is not None else {}
    assert getattr(cliente, metodo)(rota, **extras).status_code == 401


# --- Paginacao -------------------------------------------------------------

def test_parametros_padrao_de_paginacao(cliente, monkeypatch):
    capturado = {}

    def espiao(db, busca, pagina, tamanho):
        capturado.update(busca=busca, pagina=pagina, tamanho=tamanho)
        return PaginaUsuarios(total=0, pagina=pagina, tamanho=tamanho, itens=[])

    monkeypatch.setattr(usuario_service, "listar", espiao)
    cliente.get("/api/v1/usuarios", headers=_autenticar(monkeypatch))
    assert capturado == {"busca": None, "pagina": 1, "tamanho": 20}


@pytest.mark.parametrize(
    ("query", "esperado"),
    [("tamanho=101", 422), ("tamanho=0", 422), ("pagina=0", 422), ("tamanho=100", 200)],
)
def test_limites_de_paginacao(cliente, monkeypatch, query, esperado):
    """O contrato define máximo de 100 registros por página."""
    monkeypatch.setattr(
        usuario_service,
        "listar",
        lambda db, b, p, t: PaginaUsuarios(total=0, pagina=p, tamanho=t, itens=[]),
    )
    r = cliente.get(f"/api/v1/usuarios?{query}", headers=_autenticar(monkeypatch))
    assert r.status_code == esperado


# --- Contrato de resposta --------------------------------------------------

def test_cadastro_responde_201_com_os_quatro_campos(cliente, monkeypatch):
    monkeypatch.setattr(
        usuario_service,
        "criar",
        lambda db, dados: UsuarioCriado(
            id_usuario=43,
            nome_completo="Carlos Oliveira",
            email="carlos.oliveira@saude.gov.br",
            criado_em=datetime(2026, 8, 22, 18, 2, 44, tzinfo=UTC),
        ),
    )
    r = cliente.post("/api/v1/usuarios", json=USUARIO_OK, headers=_autenticar(monkeypatch))
    assert r.status_code == 201
    assert r.json() == {
        "id_usuario": 43,
        "nome_completo": "Carlos Oliveira",
        "email": "carlos.oliveira@saude.gov.br",
        "criado_em": "2026-08-22T15:02:44-03:00",
    }


def test_desativacao_responde_204_sem_corpo(cliente, monkeypatch):
    monkeypatch.setattr(usuario_service, "desativar", lambda db, i, s: None)
    r = cliente.delete("/api/v1/usuarios/9", headers=_autenticar(monkeypatch))
    assert r.status_code == 204
    assert r.content == b""


@pytest.mark.parametrize(
    ("codigo", "status_esperado"),
    [
        (CodigoErro.CPF_DUPLICADO, 409),
        (CodigoErro.EMAIL_DUPLICADO, 409),
        (CodigoErro.TELEFONE_DUPLICADO, 409),
        (CodigoErro.REFERENCIA_INVALIDA, 422),
    ],
)
def test_erros_do_cadastro_seguem_o_catalogo(cliente, monkeypatch, codigo, status_esperado):
    def estoura(db, dados):
        raise AppError(codigo)

    monkeypatch.setattr(usuario_service, "criar", estoura)
    r = cliente.post("/api/v1/usuarios", json=USUARIO_OK, headers=_autenticar(monkeypatch))
    assert r.status_code == status_esperado
    assert r.json()["erro"]["codigo"] == str(codigo)


def test_auto_desativacao_recebe_o_id_de_quem_pediu(cliente, monkeypatch):
    """O service precisa do solicitante para barrar a auto-desativação."""
    capturado = {}
    monkeypatch.setattr(
        usuario_service,
        "desativar",
        lambda db, i, s: capturado.update(alvo=i, solicitante=s),
    )
    cliente.delete("/api/v1/usuarios/99", headers=_autenticar(monkeypatch))
    assert capturado == {"alvo": 99, "solicitante": 42}
