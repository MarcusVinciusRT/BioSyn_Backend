"""Canal de alertas pela API HTTP da Brevo, com a API simulada (sem rede).

Existe porque o Render gratuito bloqueia as portas SMTP: la, o unico caminho
para o e-mail sair e HTTPS.
"""

import json

import httpx
import pytest

import app.core.config as config
from app.integrations import notificacao
from app.integrations.notificacao.base import Destinatario, FalhaEnvioAlertaError
from app.integrations.notificacao.brevo import MAX_POR_REQUISICAO, URL, CanalEmailBrevo

CHAVE = "xkeysib-chave-de-teste-nao-real"
ASSUNTO = "[BioSyn] Alerta de saúde pública — SP"
MENSAGEM = "Surto de dengue confirmado. Reforce a eliminação de focos."


def destinatarios(quantidade: int) -> list[Destinatario]:
    return [
        Destinatario(nome=f"Profissional {i}", email=f"prof{i}@saude.gov.br")
        for i in range(quantidade)
    ]


class ApiFalsa:
    """Responde 201 por padrao; aceita uma fila de respostas ou excecoes."""

    def __init__(self, fila: list | None = None) -> None:
        self.requisicoes: list[httpx.Request] = []
        self._fila = list(fila or [])

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        self.requisicoes.append(requisicao)
        if self._fila:
            item = self._fila.pop(0)
            if isinstance(item, Exception):
                raise item
            status, corpo = item
            return httpx.Response(status, json=corpo)
        return httpx.Response(201, json={"messageIds": ["<id@smtp-relay.brevo.com>"]})

    def corpo(self, indice: int = 0) -> dict:
        return json.loads(self.requisicoes[indice].content)


def montar(api: ApiFalsa) -> CanalEmailBrevo:
    cliente = httpx.Client(transport=httpx.MockTransport(api))
    return CanalEmailBrevo(CHAVE, "alertas@saude.gov.br", "BioSyn", cliente=cliente)


def test_requisicao_segue_o_contrato_da_api():
    api = ApiFalsa()
    aceitos = montar(api).enviar_lote(destinatarios(3), ASSUNTO, MENSAGEM)

    assert aceitos == 3
    requisicao = api.requisicoes[0]
    assert requisicao.method == "POST"
    assert str(requisicao.url) == URL
    assert requisicao.headers["api-key"] == CHAVE

    corpo = api.corpo()
    assert corpo["sender"] == {"email": "alertas@saude.gov.br", "name": "BioSyn"}
    assert corpo["subject"] == ASSUNTO
    assert corpo["textContent"] == MENSAGEM


def test_nenhum_destinatario_ve_os_outros():
    """LGPD: cada profissional recebe a própria mensagem, com só o próprio
    endereço no "Para" -- nunca a lista da UF inteira."""
    api = ApiFalsa()
    montar(api).enviar_lote(destinatarios(5), ASSUNTO, MENSAGEM)

    corpo = api.corpo()
    assert "to" not in corpo and "bcc" not in corpo and "cc" not in corpo
    versoes = corpo["messageVersions"]
    assert len(versoes) == 5
    assert all(len(v["to"]) == 1 for v in versoes)
    assert len({v["to"][0]["email"] for v in versoes}) == 5


def test_uf_grande_e_fatiada_em_requisicoes():
    """A API aceita até 2000 destinatários por requisição."""
    api = ApiFalsa()
    total = 2 * MAX_POR_REQUISICAO + 500
    assert montar(api).enviar_lote(destinatarios(total), ASSUNTO, MENSAGEM) == total
    assert [len(api.corpo(i)["messageVersions"]) for i in range(3)] == [
        MAX_POR_REQUISICAO, MAX_POR_REQUISICAO, 500,
    ]


def test_resposta_202_agendada_tambem_conta_como_aceita():
    api = ApiFalsa([(202, {"messageIds": ["<x>"]})])
    assert montar(api).enviar_lote(destinatarios(2), ASSUNTO, MENSAGEM) == 2


def test_chave_invalida_vira_falha_com_o_motivo_da_brevo():
    api = ApiFalsa([(401, {"message": "Key not found", "code": "unauthorized"})])
    with pytest.raises(FalhaEnvioAlertaError) as erro:
        montar(api).enviar_lote(destinatarios(1), ASSUNTO, MENSAGEM)
    assert "HTTP 401" in str(erro.value)
    assert "Key not found" in str(erro.value)


def test_remetente_nao_cadastrado_vira_falha():
    api = ApiFalsa([(400, {"code": "invalid_parameter", "message": "sender is invalid"})])
    with pytest.raises(FalhaEnvioAlertaError, match="sender is invalid"):
        montar(api).enviar_lote(destinatarios(1), ASSUNTO, MENSAGEM)


def test_rede_fora_vira_falha():
    api = ApiFalsa([httpx.ConnectError("sem rede")])
    with pytest.raises(FalhaEnvioAlertaError, match="inacessível"):
        montar(api).enviar_lote(destinatarios(1), ASSUNTO, MENSAGEM)


def test_falha_no_meio_devolve_so_o_que_foi_aceito(caplog):
    """Parte já saiu e não há como desfazer: destinatarios tem de refletir só o
    que a Brevo aceitou, e o que se perdeu vai para o log."""
    api = ApiFalsa([(201, {"messageIds": []}), (500, {"message": "erro interno"})])
    with caplog.at_level("ERROR"):
        aceitos = montar(api).enviar_lote(
            destinatarios(MAX_POR_REQUISICAO + 10), ASSUNTO, MENSAGEM
        )
    assert aceitos == MAX_POR_REQUISICAO
    assert any("já tinham sido aceitos" in r.getMessage() for r in caplog.records)


def test_lote_vazio_nao_chama_a_api():
    api = ApiFalsa()
    assert montar(api).enviar_lote([], ASSUNTO, MENSAGEM) == 0
    assert api.requisicoes == []


def test_a_chave_nunca_aparece_no_erro_nem_no_log(caplog):
    api = ApiFalsa([(401, {"message": "Key not found"})])
    with caplog.at_level("DEBUG"), pytest.raises(FalhaEnvioAlertaError) as erro:
        montar(api).enviar_lote(destinatarios(1), ASSUNTO, MENSAGEM)
    assert CHAVE not in str(erro.value)
    assert CHAVE not in caplog.text


# --- Fabrica ---------------------------------------------------------------

@pytest.fixture
def ambiente_limpo():
    config.get_settings.cache_clear()
    notificacao.obter_canal.cache_clear()
    yield
    config.get_settings.cache_clear()
    notificacao.obter_canal.cache_clear()


def test_fabrica_falha_na_inicializacao_sem_a_chave(monkeypatch, ambiente_limpo):
    """Descobrir que falta a chave durante um alerta de surto é tarde demais."""
    monkeypatch.setenv("ALERTA_CANAL", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "")
    monkeypatch.setenv("BREVO_REMETENTE", "alertas@saude.gov.br")
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        notificacao.obter_canal()


def test_fabrica_monta_o_canal_brevo(monkeypatch, ambiente_limpo):
    monkeypatch.setenv("ALERTA_CANAL", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", CHAVE)
    monkeypatch.setenv("BREVO_REMETENTE", "alertas@saude.gov.br")
    assert isinstance(notificacao.obter_canal(), CanalEmailBrevo)
