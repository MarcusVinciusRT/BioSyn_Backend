"""Dependencias compartilhadas pelas rotas: sessao de banco e autorizacao."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.core.security import TokenInvalidoError, decodificar_token
from app.db.session import criar_sessao
from app.models import Usuario
from app.repositories import usuario_repository

# auto_error=False para que a ausencia de token caia no nosso envelope de erro
# em vez do 403 cru que o HTTPBearer emitiria por conta propria.
_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """Uma sessao por requisicao.

    Sem commit automatico: quem escreve e o service, que sabe onde a transacao
    comeca e termina. Rollback aqui e so a rede de seguranca.
    """
    db = criar_sessao()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


SessaoDep = Annotated[Session, Depends(get_db)]
_CredenciaisDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def usuario_atual(credenciais: _CredenciaisDep, db: SessaoDep) -> Usuario:
    """Usuario autenticado da requisicao.

    O token carrega id e is_admin, mas ainda assim consultamos o banco: sem
    isso, um usuario desativado continuaria operando com privilegio de
    administrador ate o token vencer (ate 30 minutos). Como o custo e uma busca
    por chave primaria, a troca vale -- ainda mais numa rota que dispara alerta
    para um estado inteiro.
    """
    if credenciais is None or not credenciais.credentials:
        raise AppError(CodigoErro.NAO_AUTENTICADO, "Token de acesso ausente.")

    try:
        token = decodificar_token(credenciais.credentials)
    except TokenInvalidoError as erro:
        raise AppError(CodigoErro.NAO_AUTENTICADO, str(erro)) from erro

    usuario = usuario_repository.buscar_por_id(db, token.id_usuario)
    if usuario is None or not usuario.ativo:
        raise AppError(
            CodigoErro.NAO_AUTENTICADO,
            "Sessão inválida. Autentique-se novamente.",
        )
    return usuario


UsuarioDep = Annotated[Usuario, Depends(usuario_atual)]


def admin_atual(usuario: UsuarioDep) -> Usuario:
    """Exigido pelas rotas de Alertas e de Usuarios."""
    if not usuario.is_admin:
        raise AppError(CodigoErro.ACESSO_NEGADO)
    return usuario


AdminDep = Annotated[Usuario, Depends(admin_atual)]
