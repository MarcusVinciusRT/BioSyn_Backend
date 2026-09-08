import time

import pytest

from app.core.security import (
    LIMITE_BYTES_SENHA,
    SenhaMuitoLongaError,
    TokenInvalidoError,
    criar_token,
    decodificar_token,
    hash_senha,
    verificar_senha,
)


def test_hash_confere_com_a_senha_original():
    hash_gerado = hash_senha("senhaProvisoria123")
    assert hash_gerado != "senhaProvisoria123"
    assert verificar_senha("senhaProvisoria123", hash_gerado)


def test_hash_recusa_senha_errada():
    assert not verificar_senha("outraSenha", hash_senha("senhaProvisoria123"))


def test_hashes_da_mesma_senha_sao_diferentes():
    """Salt aleatorio: dois cadastros com a mesma senha nao viram o mesmo hash."""
    assert hash_senha("mesmaSenha123") != hash_senha("mesmaSenha123")


def test_senha_acima_do_limite_do_bcrypt_e_recusada():
    """Sem essa guarda, duas senhas longas com 72 bytes iguais se autenticariam."""
    with pytest.raises(SenhaMuitoLongaError):
        hash_senha("a" * (LIMITE_BYTES_SENHA + 1))


def test_hash_corrompido_nao_estoura():
    assert not verificar_senha("qualquer", "isso-nao-e-um-hash-bcrypt")


def test_token_carrega_id_email_e_flag_de_admin():
    token, expira_em = criar_token(42, "maria.santos@saude.gov.br", True)
    assert expira_em == 1800  # valor devolvido no campo "expira_em" do login

    decodificado = decodificar_token(token)
    assert decodificado.id_usuario == 42
    assert decodificado.email == "maria.santos@saude.gov.br"
    assert decodificado.is_admin is True


def test_token_adulterado_e_recusado():
    token, _ = criar_token(42, "maria@saude.gov.br", False)
    with pytest.raises(TokenInvalidoError):
        decodificar_token(token[:-4] + "AAAA")


def test_token_expirado_e_recusado(monkeypatch):
    import app.core.security as seguranca

    settings = seguranca.get_settings()
    monkeypatch.setattr(settings, "jwt_expira_segundos", -1)
    token, _ = criar_token(42, "maria@saude.gov.br", False)
    with pytest.raises(TokenInvalidoError):
        decodificar_token(token)


def test_texto_qualquer_nao_passa_por_token():
    with pytest.raises(TokenInvalidoError):
        decodificar_token("nao.e.um.jwt")
