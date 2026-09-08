"""Secao 6: catalogo de metricas, geracao e exportacao."""

import io
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.core import deps
from app.core.security import criar_token
from app.integrations import lakehouse
from app.models import Metrica
from app.repositories import metrica_repository, usuario_repository
from tests.unit.test_auth_service import montar_usuario

CATALOGO = [
    Metrica(id_metrica=1, nome_metrica="Internações totais",
            nome_view="VW_INTERNACOES_TOTAL", coluna_filtro="UF",
            descricao="Quantidade de internações no período", unidade="numero", ativo=True),
    Metrica(id_metrica=6, nome_metrica="Taxa de alta complexidade",
            nome_view="VW_INTERNACOES_TAXA_ALTA_COMPLEXIDADE", coluna_filtro="UF",
            descricao="Percentual de internações de alta complexidade",
            unidade="percentual", ativo=True),
]
VALORES = {1: 101953.0, 6: 7.3}

PEDIDO = {
    "metricas": [{"id_metrica": 1, "filtro": "SP"}, {"id_metrica": 6, "filtro": "SP"}],
    "periodo": {"inicio": "2024-01-01", "fim": "2024-12-31"},
}


@pytest.fixture
def cliente(monkeypatch):
    from app.main import criar_app

    app = criar_app()
    app.dependency_overrides[deps.get_db] = lambda: None
    monkeypatch.setattr(metrica_repository, "listar_ativas", lambda db: CATALOGO)
    def buscar(db, ids):
        # list() antes: o service passa um gerador, e reavaliá-lo dentro da
        # compreensão o esvaziaria na primeira iteração.
        pedidos = set(ids)
        return {m.id_metrica: m for m in CATALOGO if m.id_metrica in pedidos}

    monkeypatch.setattr(metrica_repository, "buscar_ativas_por_ids", buscar)
    monkeypatch.setattr(
        lakehouse,
        "executar_metrica",
        lambda db, m, f, i, fim: VALORES[m.id_metrica],
    )
    monkeypatch.setattr(
        "app.services.relatorio_service.executar_metrica",
        lambda db, m, f, i, fim: VALORES[m.id_metrica],
    )
    return TestClient(app, raise_server_exceptions=False)


def _auth(monkeypatch, *, admin: bool = False) -> dict[str, str]:
    usuario = montar_usuario(is_admin=admin)
    monkeypatch.setattr(usuario_repository, "buscar_por_id", lambda db, i: usuario)
    token, _ = criar_token(usuario.id_usuario, usuario.email, admin)
    return {"Authorization": f"Bearer {token}"}


# --- Catálogo --------------------------------------------------------------

def test_catalogo_usa_o_envelope_metricas(cliente, monkeypatch):
    r = cliente.get("/api/v1/relatorios/metricas", headers=_auth(monkeypatch))
    assert r.status_code == 200
    assert list(r.json()) == ["metricas"]
    assert all(set(m) == {"id_metrica", "nome", "descricao"} for m in r.json()["metricas"])


def test_catalogo_nao_vaza_a_view_nem_a_coluna_de_filtro(cliente, monkeypatch):
    """São detalhes internos da montagem do SQL; expor facilitaria sondagem."""
    corpo = cliente.get("/api/v1/relatorios/metricas", headers=_auth(monkeypatch)).text
    assert "VW_" not in corpo
    assert "coluna_filtro" not in corpo


def test_catalogo_e_acessivel_a_usuario_comum(cliente, monkeypatch):
    assert cliente.get(
        "/api/v1/relatorios/metricas", headers=_auth(monkeypatch, admin=False)
    ).status_code == 200


# --- Geração ---------------------------------------------------------------

def test_relatorio_json_segue_o_formato_padronizado(cliente, monkeypatch):
    """Formato padronizado em vez de uma lista de objetos: o front monta a tabela
    genericamente e uma métrica nova não exige mudança no front."""
    r = cliente.post("/api/v1/relatorios", json=PEDIDO, headers=_auth(monkeypatch))
    assert r.status_code == 200
    corpo = r.json()
    assert set(corpo) == {"gerado_em", "periodo", "resultados"}
    assert corpo["periodo"] == {"inicio": "2024-01-01", "fim": "2024-12-31"}
    assert all(
        set(x) == {"id_metrica", "nome", "filtro", "valor", "unidade"}
        for x in corpo["resultados"]
    )
    assert corpo["resultados"][0]["valor"] == 101953.0
    assert corpo["resultados"][1]["unidade"] == "percentual"


def test_gerado_em_sai_com_fuso(cliente, monkeypatch):
    corpo = cliente.post("/api/v1/relatorios", json=PEDIDO, headers=_auth(monkeypatch)).json()
    assert corpo["gerado_em"].endswith("-03:00")


def test_filtro_ausente_volta_como_nulo(cliente, monkeypatch):
    pedido = {**PEDIDO, "metricas": [{"id_metrica": 1}]}
    corpo = cliente.post("/api/v1/relatorios", json=pedido, headers=_auth(monkeypatch)).json()
    assert corpo["resultados"][0]["filtro"] is None


# --- Erros do contrato -----------------------------------------------------

def test_metrica_fora_do_catalogo(cliente, monkeypatch):
    pedido = {**PEDIDO, "metricas": [{"id_metrica": 1}, {"id_metrica": 999}]}
    r = cliente.post("/api/v1/relatorios", json=pedido, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["codigo"] == "METRICA_DESCONHECIDA"
    assert "999" in r.json()["erro"]["mensagem"]


def test_periodo_invertido(cliente, monkeypatch):
    pedido = {**PEDIDO, "periodo": {"inicio": "2024-12-31", "fim": "2024-01-01"}}
    r = cliente.post("/api/v1/relatorios", json=pedido, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["codigo"] == "PERIODO_INVALIDO"


def test_falha_do_lakehouse_vira_502(cliente, monkeypatch):
    def estoura(db, m, f, i, fim):
        raise lakehouse.FalhaLakehouseError("timeout")

    monkeypatch.setattr("app.services.relatorio_service.executar_metrica", estoura)
    r = cliente.post("/api/v1/relatorios", json=PEDIDO, headers=_auth(monkeypatch))
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "FALHA_LAKEHOUSE"


def test_sem_token_e_401(cliente):
    assert cliente.post("/api/v1/relatorios", json=PEDIDO).status_code == 401


@pytest.mark.parametrize(
    ("pedido", "campo"),
    [
        ({"metricas": [], "periodo": PEDIDO["periodo"]}, "metricas"),
        ({"metricas": PEDIDO["metricas"]}, "periodo"),
        ({**PEDIDO, "formato": "pdf"}, "formato"),
    ],
)
def test_validacoes_de_entrada(cliente, monkeypatch, pedido, campo):
    r = cliente.post("/api/v1/relatorios", json=pedido, headers=_auth(monkeypatch))
    assert r.status_code == 422
    assert r.json()["erro"]["campos"][0]["campo"] == campo


def test_teto_de_metricas_por_requisicao(cliente, monkeypatch):
    """Sem teto, uma requisição vira dezenas de consultas ao lakehouse."""
    pedido = {**PEDIDO, "metricas": [{"id_metrica": 1}] * 21}
    r = cliente.post("/api/v1/relatorios", json=pedido, headers=_auth(monkeypatch))
    assert r.status_code == 422


# --- Exportação ------------------------------------------------------------

def test_csv_traz_cabecalho_de_download_e_bom(cliente, monkeypatch):
    r = cliente.post(
        "/api/v1/relatorios", json={**PEDIDO, "formato": "csv"}, headers=_auth(monkeypatch)
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="relatorio_' in r.headers["content-disposition"]
    # BOM: sem ele o Excel em português abre "Internações" como "InternaÃ§Ãµes".
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert "Internações totais" in r.content.decode("utf-8-sig")


def test_xlsx_e_uma_planilha_valida_com_os_dados(cliente, monkeypatch):
    r = cliente.post(
        "/api/v1/relatorios", json={**PEDIDO, "formato": "xlsx"}, headers=_auth(monkeypatch)
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    aba = load_workbook(io.BytesIO(r.content)).active
    valores = [c for linha in aba.iter_rows(values_only=True) for c in linha if c]
    assert "Internações totais" in valores
    assert 101953 in valores


def test_horario_do_xlsx_bate_com_o_do_json(cliente, monkeypatch):
    """Regressão: o cabeçalho da planilha saía em UTC enquanto o JSON e o nome
    do arquivo saíam no fuso local — três horas de diferença na mesma resposta."""
    from app.exporters import gerar_xlsx
    from app.schemas.relatorio import RelatorioResponse

    gerado = datetime(2026, 9, 3, 22, 49, 9, tzinfo=UTC)
    relatorio = RelatorioResponse(
        gerado_em=gerado,
        periodo={"inicio": date(2024, 1, 1), "fim": date(2024, 12, 31)},
        resultados=[],
    )
    aba = load_workbook(io.BytesIO(gerar_xlsx(relatorio))).active
    assert "19:49" in aba["A2"].value
    assert relatorio.model_dump()["gerado_em"].startswith("2026-09-03T19:49")


def test_nome_do_arquivo_segue_o_contrato():
    from app.services.relatorio_service import nome_do_arquivo

    gerado = datetime(2026, 8, 22, 17, 40, 2, tzinfo=UTC)
    assert nome_do_arquivo(gerado, "xlsx") == "relatorio_20260822_1440.xlsx"
