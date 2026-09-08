"""Regras do disparo de alertas, com banco e canal de envio falsos."""

from datetime import UTC, datetime

import pytest

from app.core.errors import AppError, CodigoErro
from app.integrations.notificacao.base import Destinatario, FalhaEnvioAlertaError
from app.integrations.notificacao.console import CanalConsole
from app.repositories import alerta_repository
from app.schemas.alerta import AlertaRequest
from app.services import alerta_service


class SessaoFalsa:
    """Registra o que o service tentou gravar, sem tocar em banco."""

    def __init__(self, falhar_no_commit: bool = False) -> None:
        self.adicionados: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self._falhar = falhar_no_commit

    def add(self, obj: object) -> None:
        self.adicionados.append(obj)

    def commit(self) -> None:
        if self._falhar:
            raise RuntimeError("falha simulada no commit")
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, obj: object) -> None:
        # O banco preencheria id e criado_em pelos DEFAULTs/sequences.
        obj.id_alerta = 17
        obj.criado_em = datetime(2026, 8, 22, 17, 32, 10, tzinfo=UTC)


def destinatarios_de(*emails: str) -> list[Destinatario]:
    return [Destinatario(nome=f"Usuario {i}", email=e) for i, e in enumerate(emails, 1)]


@pytest.fixture
def destinatarios(monkeypatch):
    def instalar(lista: list[Destinatario]) -> None:
        monkeypatch.setattr(
            alerta_repository, "buscar_destinatarios_por_uf", lambda db, uf: lista
        )
    return instalar


PEDIDO = AlertaRequest(
    mensagem="Surto de dengue confirmado. Reforce a eliminação de focos.",
    estado_uf="SP",
)


def test_disparo_bem_sucedido_grava_uma_linha(destinatarios):
    destinatarios(destinatarios_de("a@saude.gov.br", "b@saude.gov.br"))
    db = SessaoFalsa()

    resposta = alerta_service.disparar(db, PEDIDO, 42, CanalConsole())

    assert resposta.id_alerta == 17
    assert resposta.estado_uf_destino == "SP"
    assert resposta.destinatarios == 2
    # Um disparo corresponde a uma UF e a uma linha no banco.
    assert len(db.adicionados) == 1
    assert db.commits == 1


def test_o_registro_guarda_quem_disparou(destinatarios):
    destinatarios(destinatarios_de("a@saude.gov.br"))
    db = SessaoFalsa()
    alerta_service.disparar(db, PEDIDO, id_solicitante=42, canal=CanalConsole())
    assert db.adicionados[0].usuarios_id_usuario == 42


def test_falha_do_canal_vira_502_e_nada_e_gravado(destinatarios):
    """O contrato é explícito: canal indisponível ou que rejeitou o lote,
    nada é gravado."""
    destinatarios(destinatarios_de("a@saude.gov.br"))
    db = SessaoFalsa()

    with pytest.raises(AppError) as erro:
        alerta_service.disparar(db, PEDIDO, 42, CanalConsole(falhar=True))

    assert erro.value.codigo == CodigoErro.FALHA_ENVIO_ALERTA
    assert erro.value.http_status == 502
    assert db.adicionados == []
    assert db.commits == 0


def test_uf_sem_destinatarios_registra_com_zero_sem_chamar_o_canal(destinatarios):
    """Nao ha codigo de erro no contrato para "ninguem nessa UF". Registrar com
    destinatarios=0 deixa o administrador ver que o alerta nao alcancou ninguem."""
    destinatarios([])

    class CanalQueNaoPodeSerChamado:
        nome = "proibido"

        def enviar_lote(self, destinatarios, assunto, mensagem):
            raise AssertionError("nao deveria chamar o canal com lote vazio")

    db = SessaoFalsa()
    resposta = alerta_service.disparar(db, PEDIDO, 42, CanalQueNaoPodeSerChamado())

    assert resposta.destinatarios == 0
    assert db.commits == 1


def test_envio_bem_sucedido_com_gravacao_falha_e_registrado_como_critico(
    destinatarios, caplog
):
    """As mensagens ja sairam e nao ha como desfazer: o log precisa deixar o
    disparo reconstituivel."""
    destinatarios(destinatarios_de("a@saude.gov.br"))
    db = SessaoFalsa(falhar_no_commit=True)

    with caplog.at_level("CRITICAL"), pytest.raises(RuntimeError):
        alerta_service.disparar(db, PEDIDO, 42, CanalConsole())

    assert db.rollbacks == 1
    critico = [r for r in caplog.records if r.levelname == "CRITICAL"]
    assert critico, "deveria registrar CRITICAL"
    texto = critico[0].getMessage()
    assert "SP" in texto and "42" in texto and "dengue" in texto


def test_canal_console_conta_os_destinatarios():
    lote = destinatarios_de("a@x.com", "b@x.com", "c@x.com")
    assert CanalConsole().enviar_lote(lote, "assunto", "oi") == 3


def test_canal_console_em_modo_falha_levanta_a_excecao_do_contrato():
    with pytest.raises(FalhaEnvioAlertaError):
        CanalConsole(falhar=True).enviar_lote(destinatarios_de("a@x.com"), "s", "oi")
