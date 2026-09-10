"""Canal de envio de alertas, selecionado por ALERTA_CANAL."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.notificacao.base import (
    CanalDeAlerta,
    Destinatario,
    FalhaEnvioAlertaError,
)
from app.integrations.notificacao.console import CanalConsole

logger = logging.getLogger(__name__)


# Provedores que so aceitam enviar como a propria conta autenticada.
_PROVEDORES_REMETENTE_FIXO = ("gmail.com", "googlemail.com", "office365.com", "outlook.com")


def _avisar_remetente_incompativel(
    host: str | None, usuario: str | None, remetente: str | None
) -> None:
    """Gmail e Outlook nao deixam enviar como um endereco diferente do da conta.

    Configurar SMTP_REMETENTE diferente de SMTP_USUARIO nesses provedores faz o
    servidor reescrever o remetente ou recusar o envio -- e a descoberta viria
    so no primeiro disparo de alerta.
    """
    if not host or not usuario or not remetente:
        return
    if not any(p in host.lower() for p in _PROVEDORES_REMETENTE_FIXO):
        return
    if usuario.strip().lower() != remetente.strip().lower():
        logger.error(
            "SMTP_REMETENTE (%s) difere de SMTP_USUARIO (%s). O provedor %s "
            "nao permite enviar como outro endereco: use o mesmo nos dois.",
            remetente, usuario, host,
        )


@lru_cache
def obter_canal() -> CanalDeAlerta:
    settings = get_settings()

    if settings.alerta_canal == "smtp":
        faltando = [
            nome
            for nome, valor in (
                ("SMTP_HOST", settings.smtp_host),
                ("SMTP_REMETENTE", settings.smtp_remetente),
            )
            if not valor
        ]
        if faltando:
            # Falha na inicializacao, e nao no primeiro disparo: descobrir que
            # falta configuracao durante um alerta de surto e tarde demais.
            raise RuntimeError(
                "ALERTA_CANAL=smtp exige " + ", ".join(faltando) + " no ambiente."
            )

        _avisar_remetente_incompativel(
            settings.smtp_host, settings.smtp_usuario, settings.smtp_remetente
        )

        from app.integrations.notificacao.smtp import CanalEmailSmtp

        logger.info(
            "canal de alertas: smtp (%s:%s)", settings.smtp_host, settings.smtp_porta
        )
        return CanalEmailSmtp(
            host=settings.smtp_host,  # type: ignore[arg-type]
            porta=settings.smtp_porta,
            usuario=settings.smtp_usuario,
            senha=settings.smtp_senha,
            remetente=settings.smtp_remetente,  # type: ignore[arg-type]
            remetente_nome=settings.smtp_remetente_nome,
            seguranca=settings.smtp_seguranca,
            tamanho_lote=settings.alerta_tamanho_lote,
        )

    if settings.alerta_canal == "brevo":
        faltando = [
            nome
            for nome, valor in (
                ("BREVO_API_KEY", settings.brevo_api_key),
                ("BREVO_REMETENTE", settings.brevo_remetente),
            )
            if not valor
        ]
        if faltando:
            raise RuntimeError(
                "ALERTA_CANAL=brevo exige " + ", ".join(faltando) + " no ambiente."
            )

        from app.integrations.notificacao.brevo import CanalEmailBrevo

        logger.info("canal de alertas: brevo (API HTTPS)")
        return CanalEmailBrevo(
            api_key=settings.brevo_api_key,  # type: ignore[arg-type]
            remetente=settings.brevo_remetente,  # type: ignore[arg-type]
            remetente_nome=settings.brevo_remetente_nome,
        )

    logger.warning("canal de alertas: console -- nenhum e-mail sai de verdade")
    return CanalConsole()


__all__ = [
    "CanalConsole",
    "CanalDeAlerta",
    "Destinatario",
    "FalhaEnvioAlertaError",
    "obter_canal",
]
