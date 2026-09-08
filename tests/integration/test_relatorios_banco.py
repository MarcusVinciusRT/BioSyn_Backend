"""Engine de metricas contra GOLD.INTERNACOES de verdade.

Marcado com `banco`: em CI sem acesso ao ADB, rode com -m "not banco".
Somente leitura -- nao escreve nada.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import criar_sessao, encerrar_banco, iniciar_banco
from app.integrations.lakehouse import executar_metrica
from app.repositories import metrica_repository
from app.schemas.relatorio import RelatorioRequest
from app.services import relatorio_service

pytestmark = pytest.mark.banco

INICIO, FIM = date(2024, 1, 1), date(2024, 12, 31)


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


@pytest.fixture
def catalogo(db: Session):
    metricas = metrica_repository.listar_ativas(db)
    if not metricas:
        pytest.skip("rode scripts/seed_dados_apoio.py antes")
    return {m.nome_view: m for m in metricas}


def test_contagem_bate_com_a_consulta_direta(db, catalogo):
    """A engine não pode divergir do SQL que um analista escreveria à mão."""
    metrica = catalogo["VW_INTERNACOES_TOTAL"]
    pela_engine = executar_metrica(db, metrica, "SP", INICIO, FIM)

    direto = db.execute(
        text(
            "SELECT COUNT(*) FROM GOLD.INTERNACOES "
            "WHERE UF = 'SAO PAULO' AND DATA_INTERNACAO BETWEEN :i AND :f"
        ),
        {"i": INICIO, "f": FIM},
    ).scalar_one()

    assert pela_engine == float(direto)
    assert pela_engine > 0, "a massa de teste deveria ter dados de SP em 2024"


def test_filtro_por_sigla_encontra_os_mesmos_dados_que_o_nome_por_extenso(db, catalogo):
    """Regressão: a coluna UF guarda "SAO PAULO"; sem a tradução o filtro "SP"
    devolveria zero em silêncio."""
    metrica = catalogo["VW_INTERNACOES_TOTAL"]
    assert executar_metrica(db, metrica, "SP", INICIO, FIM) == executar_metrica(
        db, metrica, "SAO PAULO", INICIO, FIM
    )


def test_uf_sem_dados_no_periodo_devolve_none_ou_zero(db, catalogo):
    metrica = catalogo["VW_INTERNACOES_TOTAL"]
    valor = executar_metrica(db, metrica, "SP", date(1900, 1, 1), date(1900, 12, 31))
    assert valor in (0.0, None)


def test_percentual_fica_entre_0_e_100(db, catalogo):
    metrica = catalogo["VW_INTERNACOES_TAXA_ALTA_COMPLEXIDADE"]
    valor = executar_metrica(db, metrica, "SP", INICIO, FIM)
    assert valor is not None
    assert 0.0 <= valor <= 100.0


def test_todas_as_metricas_do_catalogo_executam(db, catalogo):
    """Guarda contra semear uma métrica cujo SQL não roda."""
    for metrica in catalogo.values():
        valor = executar_metrica(db, metrica, "SP", INICIO, FIM)
        assert valor is None or isinstance(valor, float), metrica.nome_metrica


def test_relatorio_completo_ponta_a_ponta(db):
    metricas = metrica_repository.listar_ativas(db)
    pedido = RelatorioRequest(
        metricas=[{"id_metrica": m.id_metrica, "filtro": "SP"} for m in metricas[:3]],
        periodo={"inicio": INICIO, "fim": FIM},
        formato="json",
    )
    relatorio = relatorio_service.gerar(db, pedido)

    assert len(relatorio.resultados) == 3
    assert relatorio.gerado_em.tzinfo is not None
    assert all(r.unidade in ("numero", "percentual") for r in relatorio.resultados)


def test_soma_das_ufs_bate_com_o_total_do_brasil(db, catalogo):
    """Consistência: filtrar por cada UF e somar tem de dar o total sem filtro."""
    from app.core.constantes import UFS

    metrica = catalogo["VW_INTERNACOES_TOTAL"]
    total = executar_metrica(db, metrica, None, INICIO, FIM) or 0.0
    soma = sum(executar_metrica(db, metrica, uf, INICIO, FIM) or 0.0 for uf in UFS)
    assert soma == total
