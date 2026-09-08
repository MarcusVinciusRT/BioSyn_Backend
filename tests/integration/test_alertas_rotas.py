"""Rota da secao 5 (Alertas)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.security import criar_token
from app.integrations.notificacao import obter_canal
from app.integrations.notificacao.base import Destinatario
from app.integrations.notificacao.console import CanalConsole
from app.repositories import alerta_repository, usuario_repository
from app.schemas.alerta import LIMITE_MENSAGEM
from tests.unit.test_auth_service import montar_usuario

PEDIDO = {
    "mensagem": "Surto de dengue confirmado. Reforce a eliminação de focos.",
    "estado_uf": "SP",
}


@pytest.fixture
def cliente(monkeypatch):
    from app.main import criar_app

    app = criar_app()

    class SessaoFalsa:
        def add(self, obj): self._ultimo = obj
        def commit(self): pass
        def rollback(self): pass
        def refresh(self, obj):
            obj.id_alerta = 17
            obj.criado_em = datetime(2026, 8, 22, 17, 32, 10, tzinfo=UTC)

    app.dependency_overrides[deps.get_db] = SessaoFalsa
    app.dependency_overrides[obter_canal] = CanalConsole
    monkeypatch.setattr(
        alerta_repository,
        "buscar_destinatarios_por_uf",
        lambda db, uf: [
            Destinatario(nome=f"Usuario {i}", email=f"u{i}@saude.gov.br")
            for i in range(1432)
        ],
    )
    return TestClient(app, raise_server_exceptions=False)


def _autenticar(monkeypatch, *, admin: bool = True) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


def test_disparo_responde_201_no_formato_do_contrato(cliente, monkeypatch):
    r = cliente.post("/api/v1/alertas", json=PEDIDO, headers=_autenticar(monkeypatch))
    assert r.status_code == 201
    assert r.json() == {
        "id_alerta": 17,
        "estado_uf_destino": "SP",
        "destinatarios": 1432,
        "criado_em": "2026-08-22T14:32:10-03:00",
    }


def test_uf_minuscula_e_aceita_e_normalizada(cliente, monkeypatch):
    r = cliente.post(
        "/api/v1/alertas",
        json={**PEDIDO, "estado_uf": "sp"},
        headers=_autenticar(monkeypatch),
    )
    assert r.json()["estado_uf_destino"] == "SP"


def test_usuario_comum_recebe_403(cliente, monkeypatch):
    r = cliente.post(
        "/api/v1/alertas", json=PEDIDO, headers=_autenticar(monkeypatch, admin=False)
    )
    assert r.status_code == 403
    assert r.json()["erro"]["codigo"] == "ACESSO_NEGADO"


def test_sem_token_recebe_401(cliente):
    assert cliente.post("/api/v1/alertas", json=PEDIDO).status_code == 401


@pytest.mark.parametrize(
    ("campo", "valor", "motivo"),
    [
        ("estado_uf", "ZZ", "UF inexistente"),
        ("estado_uf", "S", "UF com 1 letra"),
        ("estado_uf", "SAO", "UF com 3 letras"),
        ("mensagem", "", "mensagem vazia"),
        ("mensagem", "   ", "mensagem só com espaços"),
        ("mensagem", "a" * (LIMITE_MENSAGEM + 1), "acima do limite da coluna"),
    ],
)
def test_validacoes_do_contrato(cliente, monkeypatch, campo, valor, motivo):
    r = cliente.post(
        "/api/v1/alertas",
        json={**PEDIDO, campo: valor},
        headers=_autenticar(monkeypatch),
    )
    assert r.status_code == 422, motivo
    assert r.json()["erro"]["codigo"] == "VALIDACAO"
    assert r.json()["erro"]["campos"][0]["campo"] == campo


def test_mensagem_no_limite_exato_e_aceita(cliente, monkeypatch):
    r = cliente.post(
        "/api/v1/alertas",
        json={**PEDIDO, "mensagem": "a" * LIMITE_MENSAGEM},
        headers=_autenticar(monkeypatch),
    )
    assert r.status_code == 201


def test_falha_do_canal_responde_502(cliente, monkeypatch):
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    app.dependency_overrides[obter_canal] = lambda: CanalConsole(falhar=True)
    monkeypatch.setattr(
        alerta_repository,
        "buscar_destinatarios_por_uf",
        lambda db, uf: [Destinatario(nome="Usuario", email="u@saude.gov.br")],
    )
    local = TestClient(app, raise_server_exceptions=False)

    r = local.post("/api/v1/alertas", json=PEDIDO, headers=_autenticar(monkeypatch))
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "FALHA_ENVIO_ALERTA"
