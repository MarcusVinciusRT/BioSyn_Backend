"""CORS: quem o navegador pode chamar.

CORS vale so para navegador. Postman, curl e o proprio /docs nao passam por
aqui -- por isso o time de front consegue testar antes de a lista estar pronta.
"""

import pytest
from fastapi.testclient import TestClient

import app.core.config as config


def montar_cliente(monkeypatch, origens: str, regex: str | None = None) -> TestClient:
    monkeypatch.setenv("CORS_ORIGENS", origens)
    if regex is None:
        monkeypatch.delenv("CORS_ORIGENS_REGEX", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGENS_REGEX", regex)
    config.get_settings.cache_clear()

    from app.main import criar_app

    cliente = TestClient(criar_app(), raise_server_exceptions=False)
    cliente.__exit__ = lambda *a: config.get_settings.cache_clear()
    return cliente


def liberado(cliente: TestClient, origem: str) -> bool:
    r = cliente.options(
        "/api/v1/auth/login",
        headers={"Origin": origem, "Access-Control-Request-Method": "POST"},
    )
    return "access-control-allow-origin" in r.headers


@pytest.fixture(autouse=True)
def _limpar_cache():
    yield
    config.get_settings.cache_clear()


LOCAL = "http://localhost:5173,http://localhost:3000"


def test_origem_da_lista_e_liberada(monkeypatch):
    cliente = montar_cliente(monkeypatch, LOCAL)
    assert liberado(cliente, "http://localhost:5173")


def test_origem_fora_da_lista_e_bloqueada(monkeypatch):
    cliente = montar_cliente(monkeypatch, LOCAL)
    assert not liberado(cliente, "https://site-do-atacante.com")


def test_requisicao_sem_origin_nao_passa_por_cors(monkeypatch):
    """É o caso de Postman, curl e testes automatizados: sem Origin, o navegador
    não está no meio e o CORS não se aplica."""
    cliente = montar_cliente(monkeypatch, LOCAL)
    r = cliente.post("/api/v1/auth/login", json={"email": "x@y.com", "senha": "errada"})
    assert r.status_code != 403


PADRAO_VERCEL = r"https://biosyn-front(-git-[a-z0-9-]+)?\.vercel\.app"


@pytest.mark.parametrize(
    "origem",
    [
        "https://biosyn-front.vercel.app",
        "https://biosyn-front-git-feature-login-abc.vercel.app",
    ],
)
def test_padrao_libera_a_producao_e_os_previews(monkeypatch, origem):
    """Vercel e Netlify criam uma URL nova por preview; uma lista fixa quebraria
    em todo PR do front."""
    cliente = montar_cliente(monkeypatch, LOCAL, PADRAO_VERCEL)
    assert liberado(cliente, origem)


@pytest.mark.parametrize(
    "origem",
    [
        "https://biosyn-front.vercel.app.atacante.com",  # sufixo colado
        "https://outro-projeto.vercel.app",              # outro projeto
        "https://site-do-atacante.com",
    ],
)
def test_padrao_nao_pode_ser_burlado(monkeypatch, origem):
    """O Starlette compara com fullmatch, então o padrão já fica ancorado nas
    duas pontas -- um sufixo colado no domínio não passa."""
    cliente = montar_cliente(monkeypatch, LOCAL, PADRAO_VERCEL)
    assert not liberado(cliente, origem)


def test_sem_padrao_configurado_so_a_lista_vale(monkeypatch):
    cliente = montar_cliente(monkeypatch, LOCAL)
    assert not liberado(cliente, "https://biosyn-front.vercel.app")
