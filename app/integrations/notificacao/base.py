"""Contrato do canal de envio de alertas.

O service de alertas conhece apenas esta interface. Trocar de canal ou de
provedor e questao de mudar ALERTA_CANAL, sem tocar em regra de negocio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FalhaEnvioAlertaError(Exception):
    """Canal indisponivel ou que rejeitou o lote.

    O service traduz para 502 FALHA_ENVIO_ALERTA e nada e gravado no banco.
    """


@dataclass(frozen=True, slots=True)
class Destinatario:
    nome: str
    email: str


class CanalDeAlerta(Protocol):
    nome: str

    def enviar_lote(
        self, destinatarios: list[Destinatario], assunto: str, mensagem: str
    ) -> int:
        """Envia a mensagem a todos e devolve quantos foram aceitos pelo servidor.

        Levanta FalhaEnvioAlertaError se o lote nao for aceito. Nao ha rastreio
        de entrega por destinatario: se o servidor aceitou o lote, o disparo e
        considerado bem-sucedido.
        """
        ...
