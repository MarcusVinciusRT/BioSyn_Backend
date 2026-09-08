"""Hash de senha (bcrypt) e emissao/validacao de JWT.

Usamos a lib bcrypt diretamente em vez de passlib: passlib esta sem manutencao e
quebra com bcrypt 4.x na deteccao de versao.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

# O bcrypt so considera os primeiros 72 bytes da senha. Aceitar mais que isso
# silenciosamente faria duas senhas diferentes autenticarem uma a outra.
LIMITE_BYTES_SENHA = 72


class SenhaMuitoLongaError(ValueError):
    pass


def hash_senha(senha: str) -> str:
    bytes_senha = senha.encode("utf-8")
    if len(bytes_senha) > LIMITE_BYTES_SENHA:
        raise SenhaMuitoLongaError(
            f"Senha excede {LIMITE_BYTES_SENHA} bytes, limite do bcrypt."
        )
    return bcrypt.hashpw(bytes_senha, bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    bytes_senha = senha.encode("utf-8")
    if len(bytes_senha) > LIMITE_BYTES_SENHA:
        return False
    try:
        return bcrypt.checkpw(bytes_senha, hash_armazenado.encode("utf-8"))
    except ValueError:
        # Hash corrompido ou em formato desconhecido: trata como senha errada.
        return False


@dataclass(frozen=True, slots=True)
class TokenDecodificado:
    id_usuario: int
    email: str
    is_admin: bool


class TokenInvalidoError(Exception):
    pass


def criar_token(id_usuario: int, email: str, is_admin: bool) -> tuple[str, int]:
    """Devolve (token, segundos_ate_expirar).

    O payload carrega o id e a flag de administrador, o que evita ida ao banco a
    cada requisicao so para checar permissao.
    """
    settings = get_settings()
    agora = datetime.now(UTC)
    expira_em = settings.jwt_expira_segundos

    payload = {
        "sub": str(id_usuario),  # o JWT exige "sub" como string
        "email": email,
        "is_admin": is_admin,
        "iat": int(agora.timestamp()),
        "exp": int((agora + timedelta(seconds=expira_em)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)
    return token, expira_em


def decodificar_token(token: str) -> TokenDecodificado:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algoritmo],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as erro:
        raise TokenInvalidoError("Token expirado.") from erro
    except jwt.InvalidTokenError as erro:
        raise TokenInvalidoError("Token inválido.") from erro

    try:
        id_usuario = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as erro:
        raise TokenInvalidoError("Token sem identificador de usuário válido.") from erro

    return TokenDecodificado(
        id_usuario=id_usuario,
        email=str(payload.get("email", "")),
        is_admin=bool(payload.get("is_admin", False)),
    )
