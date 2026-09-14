"""Consulta em linguagem natural via Select AI da Oracle (secao 9).

Uma unica chamada a DBMS_CLOUD_AI.GENERATE com action 'narrate': o proprio
Oracle gera o SQL, executa e devolve a resposta em texto corrido. O profile e
passado explicitamente, sem SET_PROFILE antes.

Nao pedimos mais o 'showsql' nem executamos o SQL gerado para contar linhas:
cada uma dessas etapas era uma chamada extra ao modelo ou ao banco, e o front
deixou de usar o SQL. A resposta continua com os campos sql_executado e
linhas_retornadas, sempre nulos, para nao quebrar quem ja consome o contrato.

O que limita o modelo e o proprio profile (object_list restrito ao schema GOLD)
e o usuario APP_BACKEND, que so tem SELECT nessas tabelas.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FalhaModeloError(Exception):
    """Select AI indisponivel ou tempo limite excedido. Vira 502 FALHA_MODELO."""


def _ler_clob(valor: object) -> str:
    """DBMS_CLOUD_AI.GENERATE devolve CLOB."""
    return valor.read() if hasattr(valor, "read") else (valor or "")


def _com_timeout(db: Session, milissegundos: int):  # type: ignore[no-untyped-def]
    """Aplica call_timeout na conexao do driver e devolve o valor anterior.

    Sem isso a chamada ao Select AI fica pendurada indefinidamente quando o
    provedor esta inacessivel -- e cada requisicao presa segura uma thread e uma
    conexao do pool, ate a API inteira travar.
    """
    bruta = db.connection().connection.dbapi_connection
    anterior = getattr(bruta, "call_timeout", 0)
    bruta.call_timeout = milissegundos
    return bruta, anterior


def narrar(db: Session, pergunta: str) -> str:
    """Resposta em linguagem natural para a pergunta."""
    settings = get_settings()
    sql = """
        SELECT DBMS_CLOUD_AI.GENERATE(
            prompt => :pergunta, profile_name => :perfil, action => 'narrate'
        ) FROM DUAL
    """
    bruta, anterior = _com_timeout(db, settings.ai_timeout_segundos * 1000)
    try:
        valor = db.execute(
            text(sql),
            {"pergunta": pergunta, "perfil": settings.ai_profile_name},
        ).scalar_one_or_none()
    except Exception as erro:
        logger.error(
            "Select AI falhou (profile=%s): %s",
            settings.ai_profile_name,
            str(erro).splitlines()[0],
        )
        raise FalhaModeloError(str(erro)) from erro
    finally:
        bruta.call_timeout = anterior

    resposta = _ler_clob(valor).strip()
    if not resposta:
        raise FalhaModeloError("Select AI não retornou resposta.")
    return resposta
