"""Canal de alertas por e-mail, contra um servidor SMTP local de verdade.

Nao usa mock de smtplib: sobe um servidor real com aiosmtpd e inspeciona o que
chegou. Isso cobre conexao, envelope, lotes e codificacao -- justamente o que um
mock esconderia.
"""

import email as emaillib
import socket
from collections.abc import Iterator
from email import policy

import pytest
from aiosmtpd.controller import Controller

from app.integrations.notificacao.base import Destinatario, FalhaEnvioAlertaError
from app.integrations.notificacao.smtp import CanalEmailSmtp

MENSAGEM = "Reforce a eliminação de focos. Ação urgente — não adie."
ASSUNTO = "[BioSyn] Alerta de saúde pública — SP"


class ColetorSmtp:
    def __init__(self) -> None:
        self.mensagens: list[tuple[list[str], bytes]] = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        self.mensagens.append((list(envelope.rcpt_tos), envelope.content))
        return "250 OK"

    @property
    def destinatarios(self) -> list[str]:
        return [r for rcpt, _ in self.mensagens for r in rcpt]


def _porta_livre() -> int:
    """O Controller do aiosmtpd nao aceita port=0: ele checa prontidao
    conectando na porta informada. Reservamos uma livre no SO e liberamos."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def servidor() -> Iterator[tuple[ColetorSmtp, int]]:
    coletor = ColetorSmtp()
    porta = _porta_livre()
    controle = Controller(coletor, hostname="127.0.0.1", port=porta)
    controle.start()
    try:
        yield coletor, porta
    finally:
        controle.stop()


def montar_canal(porta: int, tamanho_lote: int = 50) -> CanalEmailSmtp:
    return CanalEmailSmtp(
        host="127.0.0.1", porta=porta, usuario=None, senha=None,
        remetente="alertas@saude.gov.br", remetente_nome="BioSyn",
        seguranca="nenhum", tamanho_lote=tamanho_lote,
    )


def destinatarios_de(quantidade: int) -> list[Destinatario]:
    return [
        Destinatario(nome=f"Profissional {i}", email=f"prof{i}@saude.gov.br")
        for i in range(1, quantidade + 1)
    ]


def test_envio_simples_chega_ao_servidor(servidor):
    coletor, porta = servidor
    aceitos = montar_canal(porta).enviar_lote(destinatarios_de(3), ASSUNTO, MENSAGEM)

    assert aceitos == 3
    assert len(coletor.mensagens) == 1
    assert sorted(coletor.destinatarios) == [
        "prof1@saude.gov.br", "prof2@saude.gov.br", "prof3@saude.gov.br"
    ]


def test_nenhum_destinatario_aparece_nos_cabecalhos(servidor):
    """LGPD: um profissional de saúde não pode receber a lista de e-mails de
    todos os outros da UF."""
    coletor, porta = servidor
    montar_canal(porta).enviar_lote(destinatarios_de(5), ASSUNTO, MENSAGEM)

    _, conteudo = coletor.mensagens[0]
    msg = emaillib.message_from_bytes(conteudo, policy=policy.default)
    cabecalhos = "\n".join(f"{nome}: {msg[nome]}" for nome in msg.keys())

    assert "prof" not in cabecalhos
    assert msg["Bcc"] is None
    assert msg["To"] == "undisclosed-recipients:;"


def test_envio_e_fatiado_em_lotes(servidor):
    """Servidores de e-mail limitam destinatários por mensagem; um envio único
    para uma UF grande seria recusado inteiro."""
    coletor, porta = servidor
    aceitos = montar_canal(porta, tamanho_lote=3).enviar_lote(
        destinatarios_de(7), ASSUNTO, MENSAGEM
    )

    assert aceitos == 7
    assert [len(rcpt) for rcpt, _ in coletor.mensagens] == [3, 3, 1]


def test_remetente_nao_recebe_copia_de_cada_lote(servidor):
    """Regressão: sem to_addrs explícito o smtplib derivava os destinatários do
    cabeçalho To, e a caixa do remetente recebia uma cópia por lote."""
    coletor, porta = servidor
    montar_canal(porta, tamanho_lote=3).enviar_lote(
        destinatarios_de(7), ASSUNTO, MENSAGEM
    )

    assert len(coletor.destinatarios) == 7
    assert "alertas@saude.gov.br" not in coletor.destinatarios


def test_acentuacao_sobrevive_e_a_mensagem_e_7bit_limpa(servidor):
    """Regressão: com Content-Transfer-Encoding 8bit a mensagem depende da
    extensão 8BITMIME, que nem todo servidor anuncia."""
    coletor, porta = servidor
    montar_canal(porta).enviar_lote(destinatarios_de(1), ASSUNTO, MENSAGEM)

    _, conteudo = coletor.mensagens[0]
    assert all(byte < 128 for byte in conteudo), "mensagem deve ser 7-bit limpa"

    msg = emaillib.message_from_bytes(conteudo, policy=policy.default)
    assert msg.get_content().strip() == MENSAGEM
    assert msg["Subject"] == ASSUNTO


def test_lote_vazio_nao_abre_conexao(servidor):
    coletor, porta = servidor
    assert montar_canal(porta).enviar_lote([], ASSUNTO, MENSAGEM) == 0
    assert coletor.mensagens == []


def test_servidor_inacessivel_vira_falha_do_contrato():
    """Porta fechada: o service traduz isso em 502 e nada é gravado."""
    canal = CanalEmailSmtp(
        host="127.0.0.1", porta=9, usuario=None, senha=None,
        remetente="alertas@saude.gov.br", remetente_nome="BioSyn",
        seguranca="nenhum",
    )
    with pytest.raises(FalhaEnvioAlertaError):
        canal.enviar_lote(destinatarios_de(1), ASSUNTO, MENSAGEM)


# --- Guarda de configuração ------------------------------------------------

@pytest.mark.parametrize(
    ("host", "usuario", "remetente", "deve_avisar"),
    [
        ("smtp.gmail.com", "eu@gmail.com", "alertas@saude.gov.br", True),
        ("smtp.gmail.com", "eu@gmail.com", "EU@Gmail.com", False),
        ("smtp-relay.brevo.com", "chave", "alertas@saude.gov.br", False),
        ("smtp.gmail.com", None, "alertas@saude.gov.br", False),
    ],
)
def test_aviso_de_remetente_incompativel(caplog, host, usuario, remetente, deve_avisar):
    """Gmail e Outlook reescrevem ou recusam um remetente diferente da conta
    autenticada, e a descoberta viria só no primeiro disparo."""
    from app.integrations.notificacao import _avisar_remetente_incompativel

    with caplog.at_level("ERROR"):
        _avisar_remetente_incompativel(host, usuario, remetente)

    avisou = any("SMTP_REMETENTE" in r.getMessage() for r in caplog.records)
    assert avisou is deve_avisar
