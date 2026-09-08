"""Limite de tentativas no /auth/login."""

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.rate_limit import LimitadorDeTentativas
from app.repositories import usuario_repository
from tests.unit.test_auth_service import SENHA, montar_usuario

CREDENCIAIS = {"email": "maria.santos@saude.gov.br", "senha": SENHA}
ERRADAS = {**CREDENCIAIS, "senha": "senhaErrada"}


@pytest.fixture
def cliente(monkeypatch):
    from app.api.v1.routes import auth
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    monkeypatch.setattr(usuario_repository, "buscar_por_email", lambda db, e: montar_usuario())
    # Limitador novo por teste: o do modulo e global e vazaria estado entre eles.
    monkeypatch.setattr(auth, "_limitador", LimitadorDeTentativas(limite=3, janela_segundos=300))
    return TestClient(app, raise_server_exceptions=False)


def test_tentativas_dentro_do_limite_continuam_respondendo_401(cliente):
    for _ in range(3):
        assert cliente.post("/api/v1/auth/login", json=ERRADAS).status_code == 401


def test_estourar_o_limite_responde_429(cliente):
    for _ in range(3):
        cliente.post("/api/v1/auth/login", json=ERRADAS)

    r = cliente.post("/api/v1/auth/login", json=ERRADAS)
    assert r.status_code == 429
    assert r.json()["erro"]["codigo"] == "MUITAS_TENTATIVAS"
    assert "segundos" in r.json()["erro"]["mensagem"]


def test_bloqueio_vale_mesmo_com_a_senha_certa(cliente):
    """Depois de bloqueado, nem a credencial correta passa -- é o que impede o
    atacante de descobrir a senha na tentativa seguinte ao limite."""
    for _ in range(3):
        cliente.post("/api/v1/auth/login", json=ERRADAS)
    assert cliente.post("/api/v1/auth/login", json=CREDENCIAIS).status_code == 429


def test_login_bem_sucedido_zera_o_contador(cliente):
    """Quem erra a senha duas vezes e acerta na terceira não pode ficar perto do
    bloqueio pelo resto da janela."""
    for _ in range(2):
        cliente.post("/api/v1/auth/login", json=ERRADAS)

    assert cliente.post("/api/v1/auth/login", json=CREDENCIAIS).status_code == 200
    for _ in range(3):
        assert cliente.post("/api/v1/auth/login", json=ERRADAS).status_code == 401


def test_sucesso_nunca_e_barrado(cliente):
    """Só a falha conta: um usuário legítimo em uso intenso não trava."""
    for _ in range(10):
        assert cliente.post("/api/v1/auth/login", json=CREDENCIAIS).status_code == 200


def test_o_limite_nao_afeta_as_outras_rotas(cliente):
    for _ in range(4):
        cliente.post("/api/v1/auth/login", json=ERRADAS)
    # /auth/me sem token continua devolvendo 401, e nao 429.
    assert cliente.get("/api/v1/auth/me").status_code == 401


# --- Limitador isolado -----------------------------------------------------

def test_janela_desliza(monkeypatch):
    import app.core.rate_limit as modulo

    relogio = {"agora": 1000.0}
    monkeypatch.setattr(modulo.time, "monotonic", lambda: relogio["agora"])

    limitador = LimitadorDeTentativas(limite=2, janela_segundos=60)
    limitador.registrar_falha("ip")
    limitador.registrar_falha("ip")
    assert limitador.bloqueado("ip")

    relogio["agora"] += 61
    assert not limitador.bloqueado("ip"), "a janela deveria ter deslizado"


def test_chaves_diferentes_nao_se_afetam():
    limitador = LimitadorDeTentativas(limite=1, janela_segundos=60)
    limitador.registrar_falha("ip-a")
    assert limitador.bloqueado("ip-a")
    assert not limitador.bloqueado("ip-b")


def test_contador_e_seguro_entre_threads():
    """As rotas rodam em threadpool: sem o lock o deque corromperia."""
    import threading

    limitador = LimitadorDeTentativas(limite=10_000, janela_segundos=300)
    threads = [
        threading.Thread(target=lambda: [limitador.registrar_falha("ip") for _ in range(200)])
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(limitador._tentativas["ip"]) == 8 * 200
