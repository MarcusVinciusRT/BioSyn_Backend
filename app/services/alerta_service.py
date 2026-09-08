"""Regras da secao 5 (Alertas).

Fluxo: buscar os destinatarios da UF, enviar o lote pelo canal configurado e so
entao gravar a linha do disparo. Um disparo corresponde a uma UF e a uma linha
no banco.

O canal e e-mail: os destinatarios sao os proprios usuarios da plataforma
(profissionais de saude cadastrados), nao a populacao.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.integrations.notificacao.base import CanalDeAlerta, FalhaEnvioAlertaError
from app.models import AlertaDisparado
from app.repositories import alerta_repository
from app.schemas.alerta import AlertaRequest, AlertaResponse

logger = logging.getLogger(__name__)


def montar_assunto(uf: str) -> str:
    return f"[BioSyn] Alerta de saúde pública — {uf}"


def disparar(
    db: Session,
    dados: AlertaRequest,
    id_solicitante: int,
    canal: CanalDeAlerta,
) -> AlertaResponse:
    destinatarios = alerta_repository.buscar_destinatarios_por_uf(db, dados.estado_uf)

    if destinatarios:
        try:
            enviados = canal.enviar_lote(
                destinatarios, montar_assunto(dados.estado_uf), dados.mensagem
            )
        except FalhaEnvioAlertaError as erro:
            # Nada e gravado: o contrato exige que uma falha do canal de envio
            # nao deixe registro de disparo.
            logger.error(
                "canal de alertas recusou o disparo uf=%s destinatarios=%d: %s",
                dados.estado_uf,
                len(destinatarios),
                erro,
            )
            raise AppError(CodigoErro.FALHA_ENVIO_ALERTA) from erro
    else:
        # Nenhum usuario ativo na UF. Nao chamamos o canal com lote vazio, mas o
        # disparo e registrado com destinatarios=0: o administrador precisa ver
        # que o alerta nao alcancou ninguem.
        enviados = 0
        logger.warning(
            "disparo sem destinatarios: nenhum usuario ativo na UF %s",
            dados.estado_uf,
        )

    alerta = AlertaDisparado(
        mensagem=dados.mensagem,
        estado_uf_destino=dados.estado_uf,
        destinatarios=enviados,
        usuarios_id_usuario=id_solicitante,
    )
    db.add(alerta)

    try:
        db.commit()
    except Exception:
        # As mensagens ja sairam e nao ha como desfazer. Registrar em CRITICAL
        # com todos os dados deixa o disparo reconstituivel a partir do log.
        db.rollback()
        logger.critical(
            "ALERTA ENVIADO MAS NAO REGISTRADO uf=%s destinatarios=%d solicitante=%d "
            "mensagem=%r",
            dados.estado_uf,
            enviados,
            id_solicitante,
            dados.mensagem,
        )
        raise

    db.refresh(alerta)
    logger.info(
        "alerta disparado id=%s uf=%s destinatarios=%d por id_usuario=%d",
        alerta.id_alerta,
        alerta.estado_uf_destino,
        alerta.destinatarios,
        id_solicitante,
    )

    return AlertaResponse(
        id_alerta=alerta.id_alerta,
        estado_uf_destino=alerta.estado_uf_destino,
        destinatarios=alerta.destinatarios,
        criado_em=alerta.criado_em,
    )
