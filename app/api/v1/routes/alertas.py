"""Secao 5 do contrato: Alertas.

Tela exclusiva de administrador, reduzida a uma unica acao: escrever uma
mensagem, escolher o estado de destino e disparar.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.deps import AdminDep, SessaoDep
from app.integrations.notificacao import obter_canal
from app.integrations.notificacao.base import CanalDeAlerta
from app.schemas.alerta import AlertaRequest, AlertaResponse
from app.services import alerta_service

router = APIRouter(tags=["alertas"])

# Dependencia em vez de import direto: os testes trocam o canal sem
# monkeypatch, e trocar de provedor continua sendo so a variavel de ambiente.
CanalDep = Annotated[CanalDeAlerta, Depends(obter_canal)]


@router.post(
    "/alertas",
    response_model=AlertaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Disparar alerta",
)
def disparar_alerta(
    corpo: AlertaRequest,
    db: SessaoDep,
    solicitante: AdminDep,
    canal: CanalDep,
) -> AlertaResponse:
    """Acesso: somente administrador."""
    return alerta_service.disparar(db, corpo, solicitante.id_usuario, canal)
