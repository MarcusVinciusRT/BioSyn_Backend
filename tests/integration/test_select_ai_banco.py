"""Contagem de linhas e guarda contra o Oracle real.

Marcado com `banco`. Nao depende do Select AI estar acessivel: exercita o SQL
que o modelo geraria, ja escrito a mao.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db.session import criar_sessao, encerrar_banco, iniciar_banco
from app.integrations import select_ai

pytestmark = pytest.mark.banco


@pytest.fixture(scope="module", autouse=True)
def banco() -> Iterator[None]:
    iniciar_banco()
    yield
    encerrar_banco()


@pytest.fixture
def db() -> Iterator[Session]:
    sessao = criar_sessao()
    yield sessao
    sessao.close()


def test_contagem_de_agrupamento_bate_com_as_27_ufs(db):
    sql = "SELECT ESTADO, COUNT(*) FROM GOLD.INTERNACOES GROUP BY ESTADO"
    select_ai.validar_somente_leitura(sql)
    assert select_ai.contar_linhas(db, sql) == 27


def test_contagem_respeita_o_limite_da_consulta(db):
    sql = "SELECT * FROM GOLD.INTERNACOES WHERE ROWNUM <= 10"
    assert select_ai.contar_linhas(db, sql) == 10


def test_comentario_no_fim_nao_quebra_o_envolucro(db):
    """Regressão: sem as quebras de linha em volta do SQL, o parêntese de
    fechamento do COUNT caía dentro do comentário e a consulta ficava malformada."""
    assert select_ai.contar_linhas(db, "SELECT 1 FROM DUAL -- comentario") == 1


def test_sql_invalido_vira_falha_de_consulta_e_nao_erro_interno(db):
    with pytest.raises(select_ai.FalhaConsultaError):
        select_ai.contar_linhas(db, "SELECT * FROM TABELA_QUE_NAO_EXISTE")


def test_o_usuario_da_conexao_nao_consegue_escrever_em_gold(db):
    """Última camada de defesa: mesmo que a guarda falhasse, APP_BACKEND só tem
    SELECT em GOLD."""
    from sqlalchemy import text

    with pytest.raises(Exception) as erro:
        db.execute(text("DELETE FROM GOLD.INTERNACOES WHERE ROWNUM <= 1"))
    # O Oracle recusa com ORA-41900 (privilégio ausente) neste ambiente, mas
    # ORA-01031 e ORA-00942 também significam recusa. O que importa é não passar.
    mensagem = str(erro.value)
    assert any(c in mensagem for c in ("ORA-41900", "ORA-01031", "ORA-00942")), mensagem
    db.rollback()
