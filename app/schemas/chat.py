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
    # Devolvido de proposito: permite conferir se o modelo entendeu a pergunta e
    # demonstra o mecanismo. Se a interface nao exibir, pode sair sem impacto.
    sql_executado: str
    linhas_retornadas: int | None
    tempo_ms: int
