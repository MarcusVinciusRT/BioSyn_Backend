"""Secao 9: rota do chat."""

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.security import criar_token
from app.integrations import select_ai
from app.repositories import usuario_repository
from app.services import chat_service
from tests.unit.test_auth_service import montar_usuario

PERGUNTA = {"pergunta": "Quais municípios tiveram mais internações"}
NARRATIVA = "Os municípios com mais internações são Rio de Janeiro e Belo Horizonte."


@pytest.fixture
def cliente(monkeypatch):
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    monkeypatch.setattr(chat_service.select_ai, "narrar", lambda db, p: NARRATIVA)
    return TestClient(app, raise_server_exceptions=False)


def _auth(monkeypatch, *, admin: bool = False) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


def test_resposta_mantem_os_quatro_campos_do_contrato(cliente, monkeypatch):
    r = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert r.status_code == 200
    corpo = r.json()
    assert set(corpo) == {"resposta", "sql_executado", "linhas_retornadas", "tempo_ms"}
    assert corpo["resposta"] == NARRATIVA
    assert isinstance(corpo["tempo_ms"], int)


def test_sql_e_linhas_saem_nulos(cliente, monkeypatch):
    """O SQL deixou de ser pedido ao modelo. Os campos continuam presentes, como
    null, para o front que já os lê não quebrar."""
    corpo = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch)).json()
    assert corpo["sql_executado"] is None
    assert corpo["linhas_retornadas"] is None


def test_faz_uma_unica_chamada_ao_modelo(cliente, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        chat_service.select_ai, "narrar", lambda db, p: chamadas.append(p) or NARRATIVA
    )
    cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert chamadas == ["Quais municípios tiveram mais internações"]


def test_usuario_comum_tem_acesso(cliente, monkeypatch):
    assert cliente.post(
        "/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch, admin=False)
    ).status_code == 200


def test_sem_token_e_401(cliente):
    assert cliente.post("/api/v1/chat", json=PERGUNTA).status_code == 401


@pytest.mark.parametrize("pergunta", ["   ", "\n\t "])
def test_pergunta_so_com_espacos(cliente, monkeypatch, pergunta):
    r = cliente.post("/api/v1/chat", json={"pergunta": pergunta}, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["codigo"] == "PERGUNTA_VAZIA"


def test_pergunta_ausente_e_validacao(cliente, monkeypatch):
    r = cliente.post("/api/v1/chat", json={}, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["campos"][0]["campo"] == "pergunta"


def test_modelo_indisponivel_vira_502(cliente, monkeypatch):
    def estoura(db, p):
        raise select_ai.FalhaModeloError("DPY-4024: call timeout")

    monkeypatch.setattr(chat_service.select_ai, "narrar", estoura)
    r = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "FALHA_MODELO"


def test_a_pergunta_nao_e_gravada_em_lugar_nenhum(cliente, monkeypatch):
    """Não há histórico nem memória: a rota não pode persistir nada."""
    escritas = []

    class SessaoQueDenuncia:
        def add(self, obj): escritas.append(obj)
        def commit(self): escritas.append("commit")

    cliente.app.dependency_overrides[deps.get_db] = SessaoQueDenuncia
    cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert escritas == []
