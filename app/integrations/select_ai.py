"""Consulta em linguagem natural via Select AI da Oracle (secao 9).

Duas acoes de DBMS_CLOUD_AI.GENERATE numa unica query: 'showsql' devolve o SQL
que o modelo gerou e 'narrate' devolve a resposta em texto corrido. O profile
(APP_PROFILE) e passado explicitamente, sem SET_PROFILE antes.

O profile limita o modelo a GOLD.INTERNACOES pelo object_list, e o usuario
APP_BACKEND so tem SELECT nessa tabela. A guarda abaixo e uma terceira camada:
o contrato exige o codigo CONSULTA_NAO_PERMITIDA, e defesa em profundidade nao
custa nada aqui.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FalhaModeloError(Exception):
    """Select AI indisponivel ou tempo limite excedido. Vira 502 FALHA_MODELO."""


class FalhaConsultaError(Exception):
    """O SQL gerado nao executou no banco. Vira 502 FALHA_CONSULTA."""


class ConsultaNaoPermitidaError(Exception):
    """O SQL gerado nao e uma leitura. Vira 422 CONSULTA_NAO_PERMITIDA."""


# Comandos que nao podem aparecer no SQL gerado, mesmo que o usuario da conexao
# nao tenha privilegio para executa-los.
_PROIBIDOS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "EXECUTE",
    "CALL", "BEGIN", "DECLARE", "RENAME", "COMMENT", "LOCK",
)
_REGEX_PROIBIDOS = re.compile(r"\b(" + "|".join(_PROIBIDOS) + r")\b", re.IGNORECASE)
_COMENTARIO_LINHA = re.compile(r"--[^\n]*")
_COMENTARIO_BLOCO = re.compile(r"/\*.*?\*/", re.DOTALL)
_CERCA_MARKDOWN = re.compile(r"^\s*```(?:sql)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RespostaSelectAI:
    sql_gerado: str
    resposta_natural: str


def _ler_clob(valor: object) -> str:
    """DBMS_CLOUD_AI.GENERATE devolve CLOB."""
    return valor.read() if hasattr(valor, "read") else (valor or "")


def limpar_sql(bruto: str) -> str:
    """Remove cerca de markdown e ponto e virgula final.

    O modelo as vezes devolve o SQL embrulhado em ```sql ... ```, e o Oracle
    recusa tanto a cerca quanto o ponto e virgula final numa subconsulta.
    """
    limpo = _CERCA_MARKDOWN.sub("", bruto.strip())
    return limpo.strip().rstrip(";").strip()


def validar_somente_leitura(sql: str) -> None:
    """Recusa qualquer coisa que nao seja uma unica consulta de leitura."""
    if not sql:
        raise ConsultaNaoPermitidaError("O modelo não devolveu SQL.")

    # Comentarios saem antes da checagem: "SELECT 1 -- ; DROP TABLE x" nao pode
    # esconder comando atras de comentario.
    sem_comentarios = _COMENTARIO_BLOCO.sub(" ", _COMENTARIO_LINHA.sub(" ", sql))
    normalizado = sem_comentarios.strip()

    if ";" in normalizado.rstrip(";"):
        raise ConsultaNaoPermitidaError("Mais de um comando na consulta gerada.")

    if not re.match(r"^\s*(SELECT|WITH)\b", normalizado, re.IGNORECASE):
        raise ConsultaNaoPermitidaError("A consulta gerada não é uma leitura.")

    proibido = _REGEX_PROIBIDOS.search(normalizado)
    if proibido:
        raise ConsultaNaoPermitidaError(
            f"A consulta gerada contém o comando {proibido.group(1).upper()}."
        )


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


def perguntar(db: Session, pergunta: str) -> RespostaSelectAI:
    """Gera o SQL e a resposta em linguagem natural, numa unica query."""
    settings = get_settings()
    sql = """
        SELECT
            DBMS_CLOUD_AI.GENERATE(
                prompt => :pergunta, profile_name => :perfil, action => 'showsql'
            ) AS sql_gerado,
            DBMS_CLOUD_AI.GENERATE(
                prompt => :pergunta, profile_name => :perfil, action => 'narrate'
            ) AS resposta_natural
        FROM DUAL
    """
    bruta, anterior = _com_timeout(db, settings.ai_timeout_segundos * 1000)
    try:
        linha = db.execute(
            text(sql),
            {"pergunta": pergunta, "perfil": settings.ai_profile_name},
        ).one_or_none()
    except Exception as erro:
        logger.error("Select AI falhou: %s", str(erro).splitlines()[0])
        raise FalhaModeloError(str(erro)) from erro
    finally:
        bruta.call_timeout = anterior

    if linha is None:
        raise FalhaModeloError("Select AI não retornou resultado.")

    return RespostaSelectAI(
        sql_gerado=limpar_sql(_ler_clob(linha[0])),
        resposta_natural=_ler_clob(linha[1]).strip(),
    )


def contar_linhas(db: Session, sql: str) -> int:
    """Conta as linhas que o SQL gerado devolveria.

    Envolvido em COUNT(*) de proposito: da o numero que o contrato pede sem
    materializar o resultado, e sem gastar uma terceira chamada ao modelo.
    Pressupoe que validar_somente_leitura ja passou.
    """
    # As quebras de linha em volta do SQL sao necessarias: se o modelo terminar
    # com um comentario "--", sem elas o parentese de fechamento cairia dentro
    # do comentario e a consulta ficaria malformada.
    envolvido = f"SELECT COUNT(*) FROM (\n{sql}\n)"
    try:
        return int(db.execute(text(envolvido)).scalar_one())  # noqa: S608
    except Exception as erro:
        logger.warning("SQL gerado nao executou: %s", str(erro).splitlines()[0])
        raise FalhaConsultaError(str(erro)) from erro
