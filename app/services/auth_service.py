"""Regra de autenticacao (secao 3 do contrato)."""

from __future__ import annotations

import logging
import secrets

from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.core.security import criar_token, hash_senha, verificar_senha
from app.models import Usuario
from app.repositories import usuario_repository
from app.schemas.auth import LoginResponse, UsuarioAutenticado

logger = logging.getLogger(__name__)

# Hash bcrypt real de uma senha aleatoria, gerado uma vez na importacao do
# modulo. Serve so para gastar o mesmo tempo de CPU quando o e-mail nao existe.
# Precisa ser um hash valido: um texto qualquer faria o checkpw falhar na hora,
# e o 401 instantaneo denunciaria que o e-mail nao esta na base.
_HASH_DESCARTAVEL = hash_senha(secrets.token_urlsafe(24))


def montar_usuario_autenticado(usuario: Usuario) -> UsuarioAutenticado:
    """Objeto "usuario" comum ao login e ao /auth/me."""
    return UsuarioAutenticado(
        id_usuario=usuario.id_usuario,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        is_admin=usuario.is_admin,
        cargo=usuario.cargo.nome_cargo,
        organizacao=usuario.organizacao.nome_organizacao,
    )


def autenticar(db: Session, email: str, senha: str) -> LoginResponse:
    """Valida credenciais e emite o token.

    E-mail inexistente, usuario inativo e senha errada devolvem exatamente o
    mesmo 401, sem distincao: revelar qual das tres falhou entregaria a um
    atacante a lista de e-mails validos da base.
    """
    usuario = usuario_repository.buscar_por_email(db, email)

    # A senha e conferida mesmo quando o usuario nao existe ou esta inativo,
    # contra um hash descartavel, para que o tempo de resposta nao denuncie o
    # caso -- um 401 instantaneo revelaria "esse e-mail nao existe".
    hash_para_conferir = usuario.senha if usuario else _HASH_DESCARTAVEL
    senha_confere = verificar_senha(senha, hash_para_conferir)

    if usuario is None or not usuario.ativo or not senha_confere:
        motivo = (
            "email inexistente" if usuario is None
            else "usuario inativo" if not usuario.ativo
            else "senha incorreta"
        )
        # O motivo fica so no log do servidor, nunca na resposta.
        logger.info("login recusado (%s)", motivo)
        raise AppError(CodigoErro.CREDENCIAIS_INVALIDAS)

    token, expira_em = criar_token(usuario.id_usuario, usuario.email, usuario.is_admin)
    logger.info("login efetuado id_usuario=%s admin=%s", usuario.id_usuario, usuario.is_admin)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expira_em=expira_em,
        usuario=montar_usuario_autenticado(usuario),
    )


