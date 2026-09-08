"""Schemas da secao 7 (Usuarios).

A senha entra em texto puro sobre HTTPS e nunca sai: nenhum schema de resposta
deste modulo tem o campo.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.constantes import TIPOS_LOGRADOURO, UFS
from app.schemas.comum import DataHora
from app.core.security import LIMITE_BYTES_SENHA

SENHA_MINIMA = 8


def _somente_digitos(valor: str) -> str:
    return "".join(c for c in valor if c.isdigit())


# --- Endereco --------------------------------------------------------------

class EnderecoEntrada(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tipo_logradouro: str = Field(max_length=15)
    logradouro: str = Field(min_length=1, max_length=120)
    numero: str = Field(min_length=1, max_length=10)
    cep: str
    estado_uf: str
    cidade: str = Field(min_length=1, max_length=50)
    complemento: str | None = Field(default=None, max_length=50)

    @field_validator("numero", mode="before")
    @classmethod
    def _numero_como_texto(cls, v: object) -> object:
        """O exemplo do contrato manda 180 como numero, mas a coluna e
        VARCHAR2(10) -- e ha numeros que nao sao inteiros ("180-A", "s/n")."""
        return str(v) if isinstance(v, int) else v

    @field_validator("tipo_logradouro")
    @classmethod
    def _tipo_valido(cls, v: str) -> str:
        v = v.strip()
        if v not in TIPOS_LOGRADOURO:
            raise ValueError(
                "Deve ser um destes: " + ", ".join(TIPOS_LOGRADOURO) + "."
            )
        return v

    @field_validator("cep")
    @classmethod
    def _cep_valido(cls, v: str) -> str:
        digitos = _somente_digitos(v)
        if len(digitos) != 8:
            raise ValueError("Deve conter 8 dígitos numéricos.")
        return digitos

    @field_validator("estado_uf")
    @classmethod
    def _uf_valida(cls, v: str) -> str:
        uf = v.strip().upper()
        if uf not in UFS:
            raise ValueError("Deve ser uma UF brasileira válida, com 2 letras.")
        return uf

    @field_validator("logradouro", "cidade", "complemento")
    @classmethod
    def _sem_espacos_nas_bordas(cls, v: str | None) -> str | None:
        return v.strip() if v else v


# --- Entrada de usuario ----------------------------------------------------

class UsuarioBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr = Field(max_length=100)
    telefone: str
    nome: str = Field(min_length=1, max_length=60)
    sobrenome: str = Field(min_length=1, max_length=60)
    is_admin: bool = False
    cargo_id: int = Field(gt=0)
    organizacao_id: int = Field(gt=0)
    endereco: EnderecoEntrada

    @field_validator("telefone")
    @classmethod
    def _telefone_valido(cls, v: str) -> str:
        digitos = _somente_digitos(v)
        # 10 = DDD + 8 digitos (fixo); 11 = DDD + 9 (celular).
        if not 10 <= len(digitos) <= 15:
            raise ValueError("Deve conter DDD e número, de 10 a 15 dígitos.")
        return digitos

    @field_validator("email")
    @classmethod
    def _email_normalizado(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("nome", "sobrenome")
    @classmethod
    def _nome_limpo(cls, v: str) -> str:
        limpo = " ".join(v.split())
        if not limpo:
            raise ValueError("Campo obrigatório ausente.")
        return limpo


def _validar_senha(v: str) -> str:
    if len(v) < SENHA_MINIMA:
        raise ValueError(f"Deve ter no mínimo {SENHA_MINIMA} caracteres.")
    if len(v.encode("utf-8")) > LIMITE_BYTES_SENHA:
        raise ValueError(f"Excede o limite de {LIMITE_BYTES_SENHA} bytes.")
    return v


class UsuarioCriar(UsuarioBase):
    cpf: str
    senha: str

    @field_validator("cpf")
    @classmethod
    def _cpf_valido(cls, v: str) -> str:
        # Aceita com ou sem mascara; grava so os digitos (coluna VARCHAR2(11)).
        # Nao conferimos digito verificador de proposito: a massa de teste do
        # projeto usa CPFs sinteticos como 12345678901.
        digitos = _somente_digitos(v)
        if len(digitos) != 11:
            raise ValueError("Deve conter 11 dígitos numéricos.")
        return digitos

    @field_validator("senha")
    @classmethod
    def _senha_valida(cls, v: str) -> str:
        return _validar_senha(v)


class UsuarioAtualizar(UsuarioBase):
    """Mesmo corpo do cadastro, com duas diferencas do contrato:

    senha e opcional (ausente = mantem a atual) e cpf e imutavel (se vier com
    valor diferente do atual, e ignorado).
    """

    cpf: str | None = None
    senha: str | None = None

    @field_validator("senha")
    @classmethod
    def _senha_valida(cls, v: str | None) -> str | None:
        return _validar_senha(v) if v is not None else None


# --- Saida -----------------------------------------------------------------

class CargoResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cargo: int
    nome_cargo: str


class OrganizacaoResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_organizacao: int
    # O contrato chama de "nome" aqui, e de "nome_organizacao" na rota
    # GET /organizacoes. Seguimos o exemplo de cada rota: e o que o front espera.
    nome: str


class UsuarioItem(BaseModel):
    id_usuario: int
    nome_completo: str
    email: str
    telefone: str
    is_admin: bool
    cargo: CargoResumo
    organizacao: OrganizacaoResumo


class PaginaUsuarios(BaseModel):
    total: int
    pagina: int
    tamanho: int
    itens: list[UsuarioItem]


class UsuarioCriado(BaseModel):
    id_usuario: int
    nome_completo: str
    email: str
    criado_em: DataHora


class UsuarioAtualizado(BaseModel):
    id_usuario: int
    nome_completo: str
    email: str
    atualizado_em: DataHora
