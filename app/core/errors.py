"""Catalogo de erros e envelope unico de resposta (secoes 2.3 e 2.4 do contrato).

Toda falha da API sai no mesmo formato, para o front tratar em um ponto so:

    {"erro": {"codigo": "...", "mensagem": "..."}}

Erros de validacao de campo acrescentam a lista "campos".

Regra de camada: services levantam AppError, nunca HTTPException. A traducao
para HTTP acontece exclusivamente nos handlers registrados em main.py.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import status


class CodigoErro(StrEnum):
    # --- Transversais ---
    VALIDACAO = "VALIDACAO"
    JSON_INVALIDO = "JSON_INVALIDO"
    NAO_AUTENTICADO = "NAO_AUTENTICADO"
    ACESSO_NEGADO = "ACESSO_NEGADO"
    NAO_ENCONTRADO = "NAO_ENCONTRADO"
    METODO_NAO_PERMITIDO = "METODO_NAO_PERMITIDO"
    REQUISICAO_INVALIDA = "REQUISICAO_INVALIDA"
    # Nao consta na tabela de status do contrato: acrescentado junto com o
    # limite de tentativas de login.
    MUITAS_TENTATIVAS = "MUITAS_TENTATIVAS"
    ERRO_INTERNO = "ERRO_INTERNO"

    # --- Autenticacao (secao 3) ---
    CREDENCIAIS_INVALIDAS = "CREDENCIAIS_INVALIDAS"

    # --- Alertas (secao 5) ---
    # O contrato documentava FALHA_GATEWAY_SMS. Renomeado ao trocar o canal
    # de SMS para e-mail: um codigo dizendo "SMS" num sistema que manda
    # e-mail engana quem for depurar.
    FALHA_ENVIO_ALERTA = "FALHA_ENVIO_ALERTA"

    # --- Relatorios (secao 6) ---
    METRICA_DESCONHECIDA = "METRICA_DESCONHECIDA"
    PERIODO_INVALIDO = "PERIODO_INVALIDO"
    FALHA_LAKEHOUSE = "FALHA_LAKEHOUSE"

    # --- Usuarios (secao 7) ---
    CPF_DUPLICADO = "CPF_DUPLICADO"
    EMAIL_DUPLICADO = "EMAIL_DUPLICADO"
    TELEFONE_DUPLICADO = "TELEFONE_DUPLICADO"
    REFERENCIA_INVALIDA = "REFERENCIA_INVALIDA"
    USUARIO_NAO_ENCONTRADO = "USUARIO_NAO_ENCONTRADO"
    AUTO_DESATIVACAO = "AUTO_DESATIVACAO"

    # --- Chat com IA (secao 9) ---
    PERGUNTA_VAZIA = "PERGUNTA_VAZIA"
    CONSULTA_NAO_PERMITIDA = "CONSULTA_NAO_PERMITIDA"
    FALHA_MODELO = "FALHA_MODELO"
    FALHA_CONSULTA = "FALHA_CONSULTA"


# codigo -> (status HTTP, mensagem padrao)
CATALOGO: dict[CodigoErro, tuple[int, str]] = {
    CodigoErro.VALIDACAO: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Dados inválidos.",
    ),
    CodigoErro.JSON_INVALIDO: (
        status.HTTP_400_BAD_REQUEST,
        "Corpo da requisição malformado.",
    ),
    CodigoErro.NAO_AUTENTICADO: (
        status.HTTP_401_UNAUTHORIZED,
        "Token ausente, inválido ou expirado.",
    ),
    CodigoErro.ACESSO_NEGADO: (
        status.HTTP_403_FORBIDDEN,
        "Esta operação exige privilégio de administrador.",
    ),
    CodigoErro.NAO_ENCONTRADO: (
        status.HTTP_404_NOT_FOUND,
        "Recurso não encontrado.",
    ),
    CodigoErro.METODO_NAO_PERMITIDO: (
        status.HTTP_405_METHOD_NOT_ALLOWED,
        "Método HTTP não permitido para esta rota.",
    ),
    CodigoErro.REQUISICAO_INVALIDA: (
        status.HTTP_400_BAD_REQUEST,
        "Requisição inválida.",
    ),
    CodigoErro.MUITAS_TENTATIVAS: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Tentativas de login em excesso. Aguarde e tente novamente.",
    ),
    CodigoErro.ERRO_INTERNO: (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Erro interno. Tente novamente em instantes.",
    ),
    # Mensagem deliberadamente generica: nao revela se o e-mail existe na base
    # nem se o usuario esta inativo.
    CodigoErro.CREDENCIAIS_INVALIDAS: (
        status.HTTP_401_UNAUTHORIZED,
        "E-mail ou senha incorretos.",
    ),
    CodigoErro.FALHA_ENVIO_ALERTA: (
        status.HTTP_502_BAD_GATEWAY,
        "Serviço de envio indisponível ou rejeitou o lote. "
        "Nenhum alerta foi registrado.",
    ),
    CodigoErro.METRICA_DESCONHECIDA: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Código de métrica fora do catálogo.",
    ),
    CodigoErro.PERIODO_INVALIDO: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Período ausente ou com data inicial posterior à final.",
    ),
    CodigoErro.FALHA_LAKEHOUSE: (
        status.HTTP_502_BAD_GATEWAY,
        "A consulta ao lakehouse falhou ou excedeu o tempo limite.",
    ),
    CodigoErro.CPF_DUPLICADO: (
        status.HTTP_409_CONFLICT,
        "Já existe usuário com esse CPF.",
    ),
    CodigoErro.EMAIL_DUPLICADO: (
        status.HTTP_409_CONFLICT,
        "Já existe usuário com esse e-mail.",
    ),
    CodigoErro.TELEFONE_DUPLICADO: (
        status.HTTP_409_CONFLICT,
        "Já existe usuário com esse telefone.",
    ),
    CodigoErro.REFERENCIA_INVALIDA: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Cargo ou organização inexistente.",
    ),
    CodigoErro.USUARIO_NAO_ENCONTRADO: (
        status.HTTP_404_NOT_FOUND,
        "Id inexistente ou usuário já desativado.",
    ),
    CodigoErro.AUTO_DESATIVACAO: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Um administrador não pode desativar a própria conta.",
    ),
    CodigoErro.PERGUNTA_VAZIA: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Pergunta ausente ou composta apenas por espaços.",
    ),
    CodigoErro.CONSULTA_NAO_PERMITIDA: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "A consulta gerada não é uma leitura ou toca objeto fora do permitido.",
    ),
    CodigoErro.FALHA_MODELO: (
        status.HTTP_502_BAD_GATEWAY,
        "Select AI indisponível ou tempo limite excedido.",
    ),
    CodigoErro.FALHA_CONSULTA: (
        status.HTTP_502_BAD_GATEWAY,
        "A consulta gerada não pôde ser executada no banco.",
    ),
}


class AppError(Exception):
    """Erro de negocio. E o unico tipo de excecao que os services levantam."""

    def __init__(
        self,
        codigo: CodigoErro,
        mensagem: str | None = None,
        campos: list[dict[str, str]] | None = None,
        *,
        http_status: int | None = None,
    ) -> None:
        padrao_status, padrao_mensagem = CATALOGO[codigo]
        self.codigo = codigo
        self.mensagem = mensagem or padrao_mensagem
        self.campos = campos
        self.http_status = http_status or padrao_status
        super().__init__(f"{codigo}: {self.mensagem}")

    def para_envelope(self) -> dict[str, Any]:
        corpo: dict[str, Any] = {"codigo": str(self.codigo), "mensagem": self.mensagem}
        if self.campos:
            corpo["campos"] = self.campos
        return {"erro": corpo}


def envelope(
    codigo: CodigoErro,
    mensagem: str | None = None,
    campos: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Monta o envelope de erro sem precisar levantar a excecao."""
    return AppError(codigo, mensagem, campos).para_envelope()
