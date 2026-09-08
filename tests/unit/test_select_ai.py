"""Limpeza do SQL gerado e guarda de somente-leitura. Sem banco."""

import pytest

from app.integrations.select_ai import (
    ConsultaNaoPermitidaError,
    limpar_sql,
    validar_somente_leitura,
)


# --- Limpeza ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("```sql\nSELECT 1 FROM DUAL;\n```", "SELECT 1 FROM DUAL"),
        ("```\nSELECT 2 FROM DUAL\n```", "SELECT 2 FROM DUAL"),
        ("  SELECT 3 FROM DUAL ;  ", "SELECT 3 FROM DUAL"),
        ("SELECT 4 FROM DUAL", "SELECT 4 FROM DUAL"),
    ],
)
def test_cerca_de_markdown_e_ponto_e_virgula_sao_removidos(bruto, esperado):
    """O modelo às vezes devolve o SQL embrulhado em ```sql; o Oracle recusa
    tanto a cerca quanto o ponto e vírgula dentro de uma subconsulta."""
    assert limpar_sql(bruto) == esperado


# --- Guarda ----------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM GOLD.INTERNACOES",
        "select uf, count(*) from gold.internacoes group by uf",
        "WITH t AS (SELECT 1 FROM DUAL) SELECT * FROM t",
        "  \n SELECT 1 FROM DUAL",
    ],
)
def test_leitura_legitima_passa(sql):
    validar_somente_leitura(sql)


@pytest.mark.parametrize(
    ("sql", "motivo"),
    [
        ("DELETE FROM GOLD.INTERNACOES", "DML"),
        ("UPDATE usuarios SET is_admin = 1", "DML"),
        ("INSERT INTO usuarios VALUES (1)", "DML"),
        ("DROP TABLE usuarios", "DDL"),
        ("TRUNCATE TABLE usuarios", "DDL"),
        ("GRANT DBA TO APP_BACKEND", "DCL"),
        ("BEGIN NULL; END;", "bloco PL/SQL"),
        ("SELECT 1; DROP TABLE usuarios", "dois comandos"),
        ("", "vazio"),
        ("   ", "só espaços"),
    ],
)
def test_consulta_perigosa_e_recusada(sql, motivo):
    with pytest.raises(ConsultaNaoPermitidaError):
        validar_somente_leitura(sql)


def test_comando_escondido_atras_de_comentario_e_detectado():
    """Comentários saem antes da checagem: /* */ não pode esconder DML."""
    with pytest.raises(ConsultaNaoPermitidaError):
        validar_somente_leitura("SELECT 1 FROM DUAL /* x */ ; DELETE FROM usuarios")


def test_comentario_de_linha_inerte_nao_bloqueia():
    """"-- ; DROP TABLE x" é inerte para o Oracle: só SELECT 1 executa."""
    validar_somente_leitura("SELECT 1 FROM DUAL -- ; DROP TABLE usuarios")


def test_palavra_proibida_dentro_de_identificador_nao_e_falso_positivo():
    """A checagem usa limite de palavra: uma coluna chamada CREATED_AT não pode
    ser confundida com o comando CREATE."""
    validar_somente_leitura("SELECT created_at, updated_at FROM GOLD.INTERNACOES")
