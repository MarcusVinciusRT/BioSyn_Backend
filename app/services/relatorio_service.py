"""Regras da secao 6 (Relatorios).

Relatorios sao gerados sob demanda e nao sao persistidos em lugar nenhum:
selecionar, gerar, exportar. Fechou a aba, acabou o relatorio.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.integrations.lakehouse import FalhaLakehouseError, executar_metrica
from app.repositories import metrica_repository
from app.schemas.comum import para_fuso_local
from app.schemas.relatorio import (
    CatalogoMetricas,
    MetricaCatalogo,
    RelatorioRequest,
    RelatorioResponse,
    ResultadoMetrica,
)

logger = logging.getLogger(__name__)


def listar_metricas(db: Session) -> CatalogoMetricas:
    metricas = metrica_repository.listar_ativas(db)
    return CatalogoMetricas(
        metricas=[
            MetricaCatalogo(
                id_metrica=m.id_metrica, nome=m.nome_metrica, descricao=m.descricao
            )
            for m in metricas
        ]
    )


def gerar(db: Session, pedido: RelatorioRequest) -> RelatorioResponse:
    # Periodo e catalogo tem codigos de erro proprios no contrato, entao a
    # checagem fica aqui e nao no schema -- no schema viraria VALIDACAO generico.
    if pedido.periodo.inicio > pedido.periodo.fim:
        raise AppError(
            CodigoErro.PERIODO_INVALIDO,
            "A data inicial não pode ser posterior à final.",
        )

    solicitadas = pedido.metricas
    catalogo = metrica_repository.buscar_ativas_por_ids(
        db, (m.id_metrica for m in solicitadas)
    )

    desconhecidas = sorted(
        {m.id_metrica for m in solicitadas} - set(catalogo)
    )
    if desconhecidas:
        raise AppError(
            CodigoErro.METRICA_DESCONHECIDA,
            "Código de métrica fora do catálogo: "
            + ", ".join(str(i) for i in desconhecidas)
            + ".",
        )

    resultados: list[ResultadoMetrica] = []
    for solicitada in solicitadas:
        metrica = catalogo[solicitada.id_metrica]
        try:
            valor = executar_metrica(
                db,
                metrica,
                solicitada.filtro,
                pedido.periodo.inicio,
                pedido.periodo.fim,
            )
        except FalhaLakehouseError as erro:
            logger.error(
                "falha ao apurar metrica id=%s (%s): %s",
                metrica.id_metrica,
                metrica.nome_metrica,
                erro,
            )
            raise AppError(CodigoErro.FALHA_LAKEHOUSE) from erro

        resultados.append(
            ResultadoMetrica(
                id_metrica=metrica.id_metrica,
                nome=metrica.nome_metrica,
                filtro=solicitada.filtro,
                valor=valor,
                unidade=metrica.unidade,
            )
        )

    logger.info(
        "relatorio gerado metricas=%d periodo=%s..%s formato=%s",
        len(resultados),
        pedido.periodo.inicio,
        pedido.periodo.fim,
        pedido.formato,
    )
    return RelatorioResponse(
        gerado_em=datetime.now(UTC),
        periodo=pedido.periodo,
        resultados=resultados,
    )


def nome_do_arquivo(gerado_em: datetime, extensao: str) -> str:
    """relatorio_20260822_1440.xlsx, como o contrato exemplifica."""
    return f"relatorio_{para_fuso_local(gerado_em):%Y%m%d_%H%M}.{extensao}"
