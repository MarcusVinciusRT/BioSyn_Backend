"""SQL dos dados de apoio, compilado sem banco.

Compilar a consulta pega erros de dialeto (como o ORA-00908 abaixo) sem precisar
de conexao com o Oracle -- roda em CI.
"""

from sqlalchemy import select
from sqlalchemy.dialects import oracle

from app.db.tipos import esta_ativo
from app.models import Cargo, Organizacao
from app.repositories.apoio_repository import _ordem_por_nome


def _sql(consulta) -> str:
    return str(
        consulta.compile(
            dialect=oracle.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_filtro_de_ativo_compara_com_1_e_nao_usa_IS():
    """Regressao ORA-00908: `ativo IS :param` e invalido no Oracle, porque a
    coluna e NUMBER(1) e nao um BOOLEAN nativo."""
    sql = _sql(select(Cargo.id_cargo).where(esta_ativo(Cargo.ativo)))
    assert "ativo = 1" in sql
    assert " IS " not in sql.upper()


def test_ordenacao_usa_colacao_linguistica():
    """Sem NLSSORT o Oracle ordena por code point, e "Épico"/"Órgão" cairiam
    depois de "Zelador"."""
    sql = _sql(select(Cargo.id_cargo).order_by(_ordem_por_nome(Cargo.nome_cargo)))
    assert "nlssort" in sql.lower()
    assert "NLS_SORT=BINARY_AI" in sql


def test_ambas_as_rotas_ordenam_pelo_nome_e_nao_pelo_id():
    for coluna in (Cargo.nome_cargo, Organizacao.nome_organizacao):
        sql = _sql(select(coluna).order_by(_ordem_por_nome(coluna)))
        assert "ORDER BY nlssort" in sql
