"""Traducao de excecoes para o envelope de erro. Registrado em main.py.

Este e o unico lugar da aplicacao que decide status HTTP a partir de uma falha.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, CodigoErro, envelope

logger = logging.getLogger("biosyn.erro")

# Traducao das mensagens do pydantic-core para portugues. Sem isso o front
# receberia "Field required" no meio de uma resposta em portugues.
_MENSAGENS_PYDANTIC: dict[str, str] = {
    "missing": "Campo obrigatório ausente.",
    "string_type": "Deve ser um texto.",
    "int_type": "Deve ser um número inteiro.",
    "float_type": "Deve ser um número.",
    "bool_type": "Deve ser verdadeiro ou falso.",
    "int_parsing": "Deve ser um número inteiro.",
    "float_parsing": "Deve ser um número.",
    "bool_parsing": "Deve ser verdadeiro ou falso.",
    "date_type": "Deve ser uma data no formato AAAA-MM-DD.",
    "date_parsing": "Deve ser uma data no formato AAAA-MM-DD.",
    "date_from_datetime_parsing": "Deve ser uma data no formato AAAA-MM-DD.",
    "string_too_short": "Mais curto que o mínimo permitido.",
    "string_too_long": "Excede o tamanho máximo permitido.",
    "string_pattern_mismatch": "Fora do formato esperado.",
    "greater_than": "Abaixo do mínimo permitido.",
    "greater_than_equal": "Abaixo do mínimo permitido.",
    "less_than": "Acima do máximo permitido.",
    "less_than_equal": "Acima do máximo permitido.",
    "enum": "Valor fora das opções permitidas.",
    "literal_error": "Valor fora das opções permitidas.",
    "too_short": "Menos itens que o mínimo exigido.",
    "too_long": "Mais itens que o máximo permitido.",
    "json_invalid": "JSON malformado.",
}


def _nome_do_campo(localizacao: tuple[object, ...]) -> str:
    """Converte a loc do pydantic em um nome que o front reconheca.

    ("body", "endereco", "cep") -> "endereco.cep"
    ("query", "pagina")         -> "pagina"
    """
    partes = [
        str(parte)
        for parte in localizacao
        if parte not in ("body", "query", "path", "header", "cookie")
    ]
    return ".".join(partes) if partes else "corpo"


def _detalhe(erro: dict[str, object]) -> str:
    tipo = str(erro.get("type", ""))
    if tipo in _MENSAGENS_PYDANTIC:
        return _MENSAGENS_PYDANTIC[tipo]

    # Validadores proprios (raise ValueError) chegam como value_error com a
    # mensagem ja escrita em portugues por nos -- vale mais que um texto
    # generico, entao ela passa direto.
    mensagem = str(erro.get("msg", "")).removeprefix("Value error, ").strip()

    # Excecao: o EmailStr do pydantic responde em ingles. O contrato pede
    # "E-mail em formato invalido" nesse caso.
    if mensagem.lower().startswith("value is not a valid email address"):
        return "E-mail em formato inválido."

    return mensagem or "Valor inválido."


def _mensagem_customizada(erro: StarletteHTTPException) -> str | None:
    """Devolve o detail so quando ele foi escrito por nos.

    O Starlette preenche detail com a frase padrao do status ("Not Found",
    "Method Not Allowed"), em ingles. Deixar isso passar colocaria texto em
    ingles no meio de uma resposta em portugues.
    """
    if not isinstance(erro.detail, str):
        return None
    try:
        frase_padrao = HTTPStatus(erro.status_code).phrase
    except ValueError:
        return erro.detail
    return None if erro.detail == frase_padrao else erro.detail


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, erro: AppError) -> JSONResponse:
        if erro.http_status >= 500:
            logger.error("%s: %s", erro.codigo, erro.mensagem)
        return JSONResponse(status_code=erro.http_status, content=erro.para_envelope())

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, erro: RequestValidationError) -> JSONResponse:
        detalhes = erro.errors()

        # Corpo que nem chegou a ser JSON valido e 400, nao 422.
        if any(d.get("type") == "json_invalid" for d in detalhes):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=envelope(CodigoErro.JSON_INVALIDO),
            )

        campos = [
            {"campo": _nome_do_campo(d.get("loc", ())), "detalhe": _detalhe(d)}
            for d in detalhes
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=envelope(CodigoErro.VALIDACAO, campos=campos),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, erro: StarletteHTTPException) -> JSONResponse:
        """Cobre 404 de rota inexistente, 405 e afins, para que nem essas
        respostas escapem do envelope."""
        por_status = {
            status.HTTP_400_BAD_REQUEST: CodigoErro.REQUISICAO_INVALIDA,
            status.HTTP_401_UNAUTHORIZED: CodigoErro.NAO_AUTENTICADO,
            status.HTTP_403_FORBIDDEN: CodigoErro.ACESSO_NEGADO,
            status.HTTP_404_NOT_FOUND: CodigoErro.NAO_ENCONTRADO,
            status.HTTP_405_METHOD_NOT_ALLOWED: CodigoErro.METODO_NAO_PERMITIDO,
        }
        if erro.status_code in por_status:
            codigo = por_status[erro.status_code]
        elif erro.status_code >= 500:
            codigo = CodigoErro.ERRO_INTERNO
        else:
            codigo = CodigoErro.REQUISICAO_INVALIDA
        mensagem = _mensagem_customizada(erro)
        corpo = envelope(codigo, mensagem)
        resposta = JSONResponse(status_code=erro.status_code, content=corpo)
        # Preserva o WWW-Authenticate que as dependencias de auth emitem.
        if erro.headers:
            resposta.headers.update(erro.headers)
        return resposta

    @app.exception_handler(Exception)
    async def _nao_tratado(_: Request, erro: Exception) -> JSONResponse:
        # Stacktrace vai para o log; o cliente recebe apenas a mensagem generica.
        logger.exception("excecao nao tratada: %s", type(erro).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=envelope(CodigoErro.ERRO_INTERNO),
        )
