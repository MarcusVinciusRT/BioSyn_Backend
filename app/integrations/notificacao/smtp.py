"""Canal de alertas por e-mail, via SMTP.

Deliberadamente generico: qualquer provedor que fale SMTP serve (Brevo, Gmail
com senha de app, Resend, Amazon SES, Mailtrap). Trocar de provedor e mudar as
variaveis SMTP_*, sem tocar em codigo -- nao ha SDK proprietario aqui.

Duas decisoes que valem explicacao:

1. Os destinatarios viajam so no envelope SMTP, nunca num cabecalho. Se
   fossem para o campo "Para", cada profissional de saude receberia a lista de
   e-mails de todos os outros da UF -- vazamento de dado pessoal, sem ganho.
2. O envio e fatiado em lotes. Servidores de e-mail limitam destinatarios por
   mensagem (a faixa comum e algumas dezenas), e um unico envio para uma UF
   grande seria recusado inteiro.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.integrations.notificacao.base import Destinatario, FalhaEnvioAlertaError

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 30.0


class CanalEmailSmtp:
    nome = "smtp"

    def __init__(
        self,
        host: str,
        porta: int,
        usuario: str | None,
        senha: str | None,
        remetente: str,
        remetente_nome: str,
        seguranca: str = "starttls",
        tamanho_lote: int = 50,
    ) -> None:
        self._host = host
        self._porta = porta
        self._usuario = usuario
        self._senha = senha
        self._remetente = remetente
        self._remetente_nome = remetente_nome
        self._seguranca = seguranca
        self._tamanho_lote = max(tamanho_lote, 1)

    def _conectar(self) -> smtplib.SMTP:
        if self._seguranca == "ssl":
            conexao: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, self._porta, timeout=TIMEOUT_SEGUNDOS,
                context=ssl.create_default_context(),
            )
        else:
            conexao = smtplib.SMTP(self._host, self._porta, timeout=TIMEOUT_SEGUNDOS)
            if self._seguranca == "starttls":
                conexao.starttls(context=ssl.create_default_context())

        if self._usuario and self._senha:
            conexao.login(self._usuario, self._senha)
        return conexao

    def _montar_mensagem(self, assunto: str, corpo: str) -> EmailMessage:
        email = EmailMessage()
        email["From"] = formataddr((self._remetente_nome, self._remetente))
        # Os destinatarios reais viajam apenas no envelope SMTP (to_addrs), nunca
        # num cabecalho: assim nenhum profissional de saude recebe a lista de
        # e-mails de todos os outros da UF.
        # Rotulo convencional (RFC) de copia oculta, no lugar do endereco do
        # remetente -- que faria a caixa dele receber uma copia por lote.
        # Em ASCII de proposito: com acento, o cabecalho sai codificado em
        # RFC 2047 dentro de uma sintaxe de grupo, que nem todo servidor aceita.
        email["To"] = "undisclosed-recipients:;"
        email["Subject"] = assunto
        # quoted-printable em vez do 8bit que o set_content escolheria sozinho:
        # 8bit depende da extensao 8BITMIME e nem todo servidor SMTP anuncia.
        # Com quoted-printable a mensagem e 7-bit limpa e a acentuacao sobrevive
        # em qualquer servidor.
        email.set_content(corpo, cte="quoted-printable")
        return email

    def enviar_lote(
        self, destinatarios: list[Destinatario], assunto: str, mensagem: str
    ) -> int:
        if not destinatarios:
            return 0

        enderecos = [d.email for d in destinatarios]
        lotes = [
            enderecos[i : i + self._tamanho_lote]
            for i in range(0, len(enderecos), self._tamanho_lote)
        ]
        aceitos = 0
        recusados = 0

        try:
            email = self._montar_mensagem(assunto, mensagem)
            with self._conectar() as conexao:
                for indice, lote in enumerate(lotes, 1):
                    # to_addrs explicito: sem ele o smtplib deriva os destinatarios
                    # do cabecalho To, e o proprio remetente receberia uma copia de
                    # cada lote (numa UF grande, dezenas de copias).
                    # send_message devolve um dict com os destinatarios recusados.
                    problemas = conexao.send_message(email, to_addrs=lote)
                    recusados_no_lote = len(problemas)
                    aceitos += len(lote) - recusados_no_lote
                    recusados += recusados_no_lote
                    if problemas:
                        # Endereco invalido nao pode derrubar o disparo inteiro.
                        logger.warning(
                            "lote %d/%d: %d destinatários recusados pelo servidor",
                            indice, len(lotes), recusados_no_lote,
                        )
        except (smtplib.SMTPException, OSError, ssl.SSLError) as erro:
            raise FalhaEnvioAlertaError(
                f"servidor SMTP {self._host}:{self._porta} indisponível ou "
                f"rejeitou o envio: {erro}"
            ) from erro

        if aceitos == 0:
            raise FalhaEnvioAlertaError(
                f"servidor SMTP recusou todos os {len(enderecos)} destinatários."
            )

        logger.info(
            "alerta enviado por e-mail: %d aceitos, %d recusados, em %d lote(s)",
            aceitos, recusados, len(lotes),
        )
        return aceitos
