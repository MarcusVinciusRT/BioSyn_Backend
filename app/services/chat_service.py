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
        resposta = select_ai.narrar(db, pergunta)
    except select_ai.FalhaModeloError as erro:
        raise AppError(CodigoErro.FALHA_MODELO) from erro

    tempo_ms = int((time.perf_counter() - inicio) * 1000)
    logger.info("chat respondido tempo_ms=%d", tempo_ms)

    # sql_executado e linhas_retornadas continuam no contrato, sempre nulos:
    # o SQL gerado deixou de ser pedido ao modelo (ver app/integrations/select_ai.py).
    return ChatResponse(
        resposta=resposta,
        sql_executado=None,
        linhas_retornadas=None,
        tempo_ms=tempo_ms,
    )
