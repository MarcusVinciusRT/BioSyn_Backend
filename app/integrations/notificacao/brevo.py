"""Canal de alertas por e-mail via API HTTP da Brevo.

Existe porque o Render bloqueia as portas SMTP (25, 465 e 587) no plano
gratuito: o CanalEmailSmtp funciona local e em plano pago, mas la a conexao e
cortada antes de sair. A API da Brevo fala HTTPS na porta 443, que nenhum PaaS
bloqueia.

Privacidade: cada destinatario vai numa "messageVersion" propria, com o proprio
"to". Assim nenhum profissional de saude recebe a lista de e-mails dos outros da
UF -- o mesmo cuidado do canal SMTP, que usa so o envelope.

Remetente: a Brevo exige que o e-mail de envio esteja cadastrado como remetente
na conta. Endereco de provedor gratuito (gmail.com) nao pode ser autenticado, e
a Brevo troca o dominio de envio por @brevosend.com -- a mensagem sai, com o
nome de exibicao preservado. Com dominio proprio autenticado, sai com ele.
"""

from __future__ import annotations

import logging

import httpx

from app.integrations.notificacao.base import Destinatario, FalhaEnvioAlertaError

logger = logging.getLogger(__name__)

URL = "https://api.brevo.com/v3/smtp/email"
TIMEOUT_SEGUNDOS = 20.0
# A API aceita ate 2000 destinatarios por requisicao. Usamos metade: se uma
# requisicao falhar no meio de uma UF grande, perde-se menos de uma vez.
MAX_POR_REQUISICAO = 1000


def _motivo(resposta: httpx.Response) -> str:
    """Mensagem de erro da Brevo, que vem em JSON como {"code", "message"}."""
    try:
        corpo = resposta.json()
        return str(corpo.get("message") or corpo.get("code") or corpo)[:200]
    except ValueError:
        return resposta.text[:200]


class CanalEmailBrevo:
    nome = "brevo"

    def __init__(
        self,
        api_key: str,
        remetente: str,
        remetente_nome: str,
        cliente: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._remetente = remetente
        self._remetente_nome = remetente_nome
        # Injetavel para os testes simularem a API sem rede.
        self._cliente = cliente

    def _corpo(self, lote: list[Destinatario], assunto: str, mensagem: str) -> dict:
        return {
            "sender": {"email": self._remetente, "name": self._remetente_nome},
            "subject": assunto,
            "textContent": mensagem,
            "messageVersions": [
                {"to": [{"email": d.email, "name": d.nome}]} for d in lote
            ],
        }

    def enviar_lote(
        self, destinatarios: list[Destinatario], assunto: str, mensagem: str
    ) -> int:
        if not destinatarios:
            return 0

        lotes = [
            destinatarios[i : i + MAX_POR_REQUISICAO]
            for i in range(0, len(destinatarios), MAX_POR_REQUISICAO)
        ]
        cabecalhos = {"api-key": self._api_key, "accept": "application/json"}
        aceitos = 0
        falha: str | None = None

        cliente = self._cliente or httpx.Client(timeout=TIMEOUT_SEGUNDOS)
        try:
            for indice, lote in enumerate(lotes, 1):
                try:
                    resposta = cliente.post(
                        URL, headers=cabecalhos, json=self._corpo(lote, assunto, mensagem)
                    )
                except httpx.HTTPError as erro:
                    falha = f"Brevo inacessível: {type(erro).__name__}: {erro}"
                    break

                if resposta.status_code in (201, 202):
                    aceitos += len(lote)
                    continue

                falha = (
                    f"Brevo recusou o lote {indice}/{len(lotes)}: "
                    f"HTTP {resposta.status_code} {_motivo(resposta)}"
                )
                break
        finally:
            if self._cliente is None:
                cliente.close()

        if falha:
            if aceitos == 0:
                raise FalhaEnvioAlertaError(falha)
            # Parte ja saiu e nao ha como desfazer: registra o que se perdeu e
            # devolve so o que foi aceito, para destinatarios ficar honesto.
            logger.error(
                "%s -- %d de %d destinatários já tinham sido aceitos",
                falha, aceitos, len(destinatarios),
            )

        logger.info(
            "alerta enviado pela Brevo: %d aceitos em %d requisição(ões)",
            aceitos, len(lotes),
        )
        return aceitos
