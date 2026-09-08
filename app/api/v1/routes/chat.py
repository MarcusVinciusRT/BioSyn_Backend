"""Secao 9 do contrato: Chat com IA.

O assistente e uma aba propria, sem historico e sem memoria.
"""

from fastapi import APIRouter

from app.core.deps import SessaoDep, UsuarioDep
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Enviar pergunta")
def perguntar(corpo: ChatRequest, db: SessaoDep, _: UsuarioDep) -> ChatResponse:
    """Acesso: qualquer usuário autenticado."""
    return chat_service.perguntar(db, corpo)
