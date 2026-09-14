"""Schemas da secao 9 (Chat com IA).

Nao ha historico nem memoria: cada pergunta e independente e nada e gravado.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

LIMITE_PERGUNTA = 1000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pergunta: str = Field(min_length=1, max_length=LIMITE_PERGUNTA)


class ChatResponse(BaseModel):
    resposta: str
    # Sempre nulos: o SQL gerado deixou de ser pedido ao modelo. Os campos ficam
    # na resposta para o front, que ja os le, nao quebrar.
    sql_executado: str | None = None
    linhas_retornadas: int | None = None
    tempo_ms: int
