"""Schemas da secao 3 (Autenticacao).

Os nomes de campo seguem exatamente os exemplos JSON do contrato -- e o que o
front espera.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr = Field(max_length=100)
    # min_length=1 apenas: a regra de forca vale no cadastro, nao aqui. Exigir
    # 8 caracteres no login revelaria quais senhas sao curtas demais para existir.
    senha: str = Field(min_length=1, max_length=200)


class UsuarioAutenticado(BaseModel):
    """Objeto "usuario" devolvido pelo login e, sozinho, pelo GET /auth/me.

    Aqui cargo e organizacao sao textos (o nome), diferente da listagem de
    usuarios da secao 7, onde sao objetos. E o que o documento especifica.
    """

    id_usuario: int
    nome_completo: str
    email: str
    is_admin: bool
    cargo: str
    organizacao: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: int
    usuario: UsuarioAutenticado
