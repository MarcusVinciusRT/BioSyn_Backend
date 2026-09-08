"""Regras da secao 9 (Chat com IA).

Nao ha historico nem memoria: cada pergunta e independente e nada e gravado.
Fechou a aba, a conversa some.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.integrations import select_ai
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


def perguntar(db: Session, pedido: ChatRequest) -> ChatResponse:
    pergunta = pedido.pergunta.strip()
    if not pergunta:
        raise AppError(CodigoErro.PERGUNTA_VAZIA)

    inicio = time.perf_counter()

    try:
        resultado = select_ai.perguntar(db, pergunta)
    except select_ai.FalhaModeloError as erro:
        raise AppError(CodigoErro.FALHA_MODELO) from erro

    try:
        select_ai.validar_somente_leitura(resultado.sql_gerado)
    except select_ai.ConsultaNaoPermitidaError as erro:
        logger.warning(
            "consulta gerada recusada: %s | sql=%.200s", erro, resultado.sql_gerado
        )
        raise AppError(CodigoErro.CONSULTA_NAO_PERMITIDA, str(erro)) from erro

    try:
        linhas = select_ai.contar_linhas(db, resultado.sql_gerado)
    except select_ai.FalhaConsultaError as erro:
        raise AppError(CodigoErro.FALHA_CONSULTA) from erro

    tempo_ms = int((time.perf_counter() - inicio) * 1000)
    logger.info("chat respondido linhas=%s tempo_ms=%d", linhas, tempo_ms)

    return ChatResponse(
        resposta=resultado.resposta_natural,
        sql_executado=resultado.sql_gerado,
        linhas_retornadas=linhas,
        tempo_ms=tempo_ms,
    )
