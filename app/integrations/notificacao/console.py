"""Canal de mentira: registra no log e conta os destinatarios.

E o canal padrao (ALERTA_CANAL=console). Permite exercitar a rota de alertas
ponta a ponta, inclusive a gravacao do disparo, sem configurar servidor de
e-mail e sem mandar mensagem de verdade para ninguem.
"""

from __future__ import annotations

import logging

from app.integrations.notificacao.base import Destinatario, FalhaEnvioAlertaError

logger = logging.getLogger(__name__)


def mascarar(email: str) -> str:
    """joao.silva@saude.gov.br -> jo***@saude.gov.br"""
    usuario, _, dominio = email.partition("@")
    if not dominio:
        return "***"
    visivel = usuario[:2]
    return f"{visivel}{'*' * max(len(usuario) - 2, 1)}@{dominio}"


class CanalConsole:
    nome = "console"

    def __init__(self, falhar: bool = False) -> None:
        # `falhar` existe para os testes exercitarem o caminho do 502.
        self._falhar = falhar

    def enviar_lote(
        self, destinatarios: list[Destinatario], assunto: str, mensagem: str
    ) -> int:
        if self._falhar:
            raise FalhaEnvioAlertaError("canal console configurado para falhar")

        logger.info(
            "[ALERTA CONSOLE] %d destinatários | assunto: %s | mensagem: %.60s%s",
            len(destinatarios),
            assunto,
            mensagem,
            "..." if len(mensagem) > 60 else "",
        )
        # E-mail e dado pessoal: no log entra so a contagem e uma amostra
        # mascarada, nunca a lista completa.
        if destinatarios:
            logger.debug(
                "[ALERTA CONSOLE] amostra: %s",
                ", ".join(mascarar(d.email) for d in destinatarios[:3]),
            )
        return len(destinatarios)
