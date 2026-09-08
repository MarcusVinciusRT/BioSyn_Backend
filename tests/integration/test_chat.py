"""Secao 9: rota do chat."""

import pytest
from fastapi.testclient import TestClient

from app.core import deps
from app.core.security import criar_token
from app.integrations import select_ai
from app.integrations.select_ai import RespostaSelectAI
from app.repositories import usuario_repository
from app.services import chat_service
from tests.unit.test_auth_service import montar_usuario

PERGUNTA = {"pergunta": "Quantas internações por dengue tivemos em São Paulo neste ano?"}
SQL_GERADO = "SELECT COUNT(*) FROM GOLD.INTERNACOES WHERE UF = 'SAO PAULO'"
NARRATIVA = "São Paulo registrou 47.312 internações por dengue em 2026."


@pytest.fixture
def cliente(monkeypatch):
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    monkeypatch.setattr(
        chat_service.select_ai,
        "perguntar",
        lambda db, p: RespostaSelectAI(sql_gerado=SQL_GERADO, resposta_natural=NARRATIVA),
    )
    monkeypatch.setattr(chat_service.select_ai, "contar_linhas", lambda db, sql: 6)
    return TestClient(app, raise_server_exceptions=False)


def _auth(monkeypatch, *, admin: bool = False) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


def test_resposta_segue_o_formato_do_contrato(cliente, monkeypatch):
    r = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert r.status_code == 200
    corpo = r.json()
    assert set(corpo) == {"resposta", "sql_executado", "linhas_retornadas", "tempo_ms"}
    assert corpo["resposta"] == NARRATIVA
    assert corpo["sql_executado"] == SQL_GERADO
    assert corpo["linhas_retornadas"] == 6
    assert isinstance(corpo["tempo_ms"], int)


def test_usuario_comum_tem_acesso(cliente, monkeypatch):
    """Não é rota de administrador."""
    assert cliente.post(
        "/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch, admin=False)
    ).status_code == 200


def test_sem_token_e_401(cliente):
    assert cliente.post("/api/v1/chat", json=PERGUNTA).status_code == 401


@pytest.mark.parametrize("pergunta", ["   ", "\n\t "])
def test_pergunta_so_com_espacos(cliente, monkeypatch, pergunta):
    r = cliente.post(
        "/api/v1/chat", json={"pergunta": pergunta}, headers=_auth(monkeypatch)
    )
    assert r.status_code == 422
    assert r.json()["erro"]["codigo"] == "PERGUNTA_VAZIA"


def test_pergunta_ausente_e_validacao(cliente, monkeypatch):
    r = cliente.post("/api/v1/chat", json={}, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["campos"][0]["campo"] == "pergunta"


def test_modelo_indisponivel_vira_502(cliente, monkeypatch):
    """Estado atual do ambiente: o Select AI não responde e a chamada estoura o
    tempo limite. A API precisa devolver 502, não pendurar."""
    def estoura(db, p):
        raise select_ai.FalhaModeloError("DPY-4024: call timeout")

    monkeypatch.setattr(chat_service.select_ai, "perguntar", estoura)
    r = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "FALHA_MODELO"


def test_sql_de_escrita_gerado_pelo_modelo_vira_422(cliente, monkeypatch):
    monkeypatch.setattr(
        chat_service.select_ai,
        "perguntar",
        lambda db, p: RespostaSelectAI(
            sql_gerado="DELETE FROM usuarios", resposta_natural="ok"
        ),
    )
    r = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["codigo"] == "CONSULTA_NAO_PERMITIDA"


def test_sql_que_nao_executa_vira_502_falha_consulta(cliente, monkeypatch):
    def estoura(db, sql):
        raise select_ai.FalhaConsultaError("ORA-00942")

    monkeypatch.setattr(chat_service.select_ai, "contar_linhas", estoura)
    r = cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "FALHA_CONSULTA"


def test_a_pergunta_nao_e_gravada_em_lugar_nenhum(cliente, monkeypatch):
    """Não há histórico nem memória: a rota não pode persistir nada."""
    escritas = []

    class SessaoQueDenuncia:
        def add(self, obj): escritas.append(obj)
        def commit(self): escritas.append("commit")
        def connection(self): raise AssertionError("não deveria abrir conexão")

    cliente.app.dependency_overrides[deps.get_db] = SessaoQueDenuncia
    cliente.post("/api/v1/chat", json=PERGUNTA, headers=_auth(monkeypatch))
    assert escritas == []
