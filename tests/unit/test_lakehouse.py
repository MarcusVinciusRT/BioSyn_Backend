"""Montagem do SQL das métricas. Sem banco."""

from datetime import date

import pytest

from app.core.constantes import UFS, UF_PARA_NOME_LAKEHOUSE
from app.integrations.lakehouse import (
    AGREGACOES_FALLBACK,
    FalhaLakehouseError,
    _consulta_fallback,
    _consulta_por_view,
    _normalizar_filtro,
    _validar_identificador,
)
from app.models import Metrica

INICIO, FIM = date(2024, 1, 1), date(2024, 12, 31)


def metrica(**mudancas) -> Metrica:
    base = {
        "id_metrica": 1,
        "nome_metrica": "Internações totais",
        "nome_view": "VW_INTERNACOES_TOTAL",
        "coluna_filtro": "ESTADO",
        "descricao": "x",
        "unidade": "numero",
        "ativo": True,
    }
    return Metrica(**{**base, **mudancas})


# --- Segurança -------------------------------------------------------------

@pytest.mark.parametrize(
    "malicioso",
    [
        "TABELA; DROP TABLE USUARIOS",
        "TABELA WHERE 1=1 --",
        "GOLD.INTERNACOES, USUARIOS",
        "VW' OR '1'='1",
        "",
        "1TABELA",
    ],
)
def test_identificador_suspeito_e_recusado(malicioso):
    """nome_view e coluna_filtro entram na string do SQL. Vêm da tabela METRICAS
    e nunca do cliente, mas ainda assim são validados antes de interpolar."""
    with pytest.raises(FalhaLakehouseError):
        _validar_identificador(malicioso, "teste")


@pytest.mark.parametrize("valido", ["VW_TOTAL", "GOLD.INTERNACOES", "_X", "A$B"])
def test_identificador_legitimo_passa(valido):
    assert _validar_identificador(valido, "teste") == valido


def test_filtro_e_datas_vao_por_bind_variable():
    """O valor do filtro vem do cliente: nunca pode entrar na string do SQL."""
    sql, parametros = _consulta_fallback(metrica(), "SP", INICIO, FIM)
    assert ":filtro" in sql and ":inicio" in sql and ":fim" in sql
    assert "SAO PAULO" not in sql
    assert parametros["filtro"] == "SAO PAULO"


def test_filtro_com_tentativa_de_injecao_nao_toca_no_sql():
    sql, parametros = _consulta_fallback(metrica(), "SP' OR '1'='1", INICIO, FIM)
    assert "OR" not in sql.replace("COMPLEXIDADE", "")
    assert parametros["filtro"] == "SP' OR '1'='1"  # inerte, vai por bind


# --- Tradução de UF --------------------------------------------------------

@pytest.mark.parametrize("coluna", ["UF", "ESTADO", "estado"])
def test_sigla_de_estado_vira_o_nome_usado_no_lakehouse(coluna):
    """A coluna guarda "SAO PAULO", mas o contrato exemplifica o filtro como
    "SP". Sem traduzir, o relatório daria zero calado.

    Aceita UF e ESTADO: a coluna foi renomeada em 2026-09-08 quando o schema
    GOLD foi recriado."""
    assert _normalizar_filtro(coluna, "SP") == "SAO PAULO"
    assert _normalizar_filtro(coluna, "df") == "DISTRITO FEDERAL"


def test_todas_as_ufs_tem_traducao():
    assert set(UF_PARA_NOME_LAKEHOUSE) == set(UFS)


def test_valor_desconhecido_passa_intacto():
    assert _normalizar_filtro("ESTADO", "SAO PAULO") == "SAO PAULO"


def test_traducao_nao_vale_para_outras_colunas():
    assert _normalizar_filtro("MUNICIPIO", "SP") == "SP"


# --- Modos -----------------------------------------------------------------

def test_fallback_usa_a_agregacao_registrada_e_a_coluna_de_data_certa():
    sql, _ = _consulta_fallback(metrica(), None, INICIO, FIM)
    assert "COUNT(*)" in sql
    assert "DATA_INTERNACAO BETWEEN" in sql


def test_fallback_sem_filtro_nao_acrescenta_where_de_filtro():
    sql, parametros = _consulta_fallback(metrica(), None, INICIO, FIM)
    assert ":filtro" not in sql
    assert "filtro" not in parametros


def test_metrica_sem_agregacao_no_fallback_falha_com_mensagem_util():
    with pytest.raises(FalhaLakehouseError, match="fallback"):
        _consulta_fallback(metrica(nome_view="VW_INEXISTENTE"), None, INICIO, FIM)


def test_modo_views_consulta_a_view_da_tabela_metricas():
    sql, _ = _consulta_por_view(metrica(), "SP", INICIO, FIM)
    assert "FROM VW_INTERNACOES_TOTAL" in sql
    assert "DATA_REFERENCIA BETWEEN" in sql


def test_toda_metrica_semeada_tem_agregacao_no_fallback():
    """Guarda contra semear uma métrica sem equivalente no modo fallback."""
    import scripts.seed_dados_apoio as seed

    for _, view, _, _, _ in seed.METRICAS:
        assert view in AGREGACOES_FALLBACK, f"{view} sem agregação no fallback"
