"""Execucao das metricas de relatorio contra o lakehouse (secao 6).

Dois modos, escolhidos por LAKEHOUSE_MODO:

  "views"    consulta a view nomeada em METRICAS.nome_view. E o destino final.
             Contrato esperado da view: uma coluna VALOR com o numero ja
             agregado, a coluna de recorte nomeada em METRICAS.coluna_filtro, e
             uma coluna de data DATA_REFERENCIA para o corte de periodo.

  "fallback" agrega direto de GOLD.INTERNACOES. Existe porque as views ainda nao
             foram criadas e sem ele a rota de relatorios nao funcionaria.

SEGURANCA: nome_view e coluna_filtro entram na string do SQL, entao vem sempre
da tabela METRICAS -- nunca do cliente -- e ainda assim sao validados contra um
padrao de identificador antes de qualquer interpolacao. Valor do filtro e datas
vao exclusivamente por bind variable.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constantes import UF_PARA_NOME_LAKEHOUSE
from app.models import Metrica

logger = logging.getLogger(__name__)


class FalhaLakehouseError(Exception):
    """Consulta falhou ou excedeu o tempo limite. O service traduz para 502."""


# Identificador Oracle simples, opcionalmente qualificado por schema.
_IDENTIFICADOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*)?$")

# Coluna de data usada no corte de periodo em cada modo.
_COLUNA_DATA_VIEW = "DATA_REFERENCIA"
_COLUNA_DATA_FALLBACK = "DATA_INTERNACAO"

# nome_view -> expressao de agregacao sobre GOLD.INTERNACOES.
# A chave e a mesma nos dois modos: quando as views existirem, basta trocar
# LAKEHOUSE_MODO para "views" e nada mais muda -- nem a tabela METRICAS.
AGREGACOES_FALLBACK: dict[str, str] = {
    "VW_INTERNACOES_TOTAL": "COUNT(*)",
    "VW_INTERNACOES_VALOR_TOTAL": "ROUND(SUM(VALOR_TOTAL), 2)",
    "VW_INTERNACOES_VALOR_MEDIO": "ROUND(AVG(VALOR_TOTAL), 2)",
    "VW_INTERNACOES_PERMANENCIA_MEDIA": "ROUND(AVG(DIAS_PERMANENCIA), 2)",
    "VW_INTERNACOES_IDADE_MEDIA": "ROUND(AVG(IDADE), 1)",
    "VW_INTERNACOES_TAXA_ALTA_COMPLEXIDADE": (
        "ROUND(100 * SUM(CASE WHEN COMPLEXIDADE = 'ALTA COMPLEXIDADE' "
        "THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1)"
    ),
}


def _validar_identificador(valor: str, rotulo: str) -> str:
    if not _IDENTIFICADOR.match(valor):
        # Nao deveria acontecer: o valor vem da tabela METRICAS. Se acontecer,
        # e sinal de linha adulterada -- recusar e melhor que interpolar.
        raise FalhaLakehouseError(
            f"{rotulo} inválido na tabela METRICAS: {valor!r}"
        )
    return valor


def _normalizar_filtro(coluna_filtro: str, filtro: str) -> str:
    """Traduz sigla de UF para o nome por extenso usado no lakehouse.

    A coluna UF de GOLD.INTERNACOES guarda "SAO PAULO", mas o contrato
    exemplifica o filtro como "SP" -- e o resto do sistema (enderecos, alertas)
    trabalha com sigla. Sem esta traducao o relatorio devolveria zero calado.
    """
    if coluna_filtro.upper() != "UF":
        return filtro
    return UF_PARA_NOME_LAKEHOUSE.get(filtro.strip().upper(), filtro)


def executar_metrica(
    db: Session, metrica: Metrica, filtro: str | None, inicio: date, fim: date
) -> float | None:
    """Devolve o valor agregado da metrica, ou None se nao houver dado."""
    settings = get_settings()

    if settings.lakehouse_modo == "views":
        sql, parametros = _consulta_por_view(metrica, filtro, inicio, fim)
    else:
        sql, parametros = _consulta_fallback(metrica, filtro, inicio, fim)

    try:
        valor = db.execute(text(sql), parametros).scalar_one_or_none()
    except Exception as erro:
        logger.exception(
            "consulta ao lakehouse falhou metrica=%s view=%s",
            metrica.id_metrica,
            metrica.nome_view,
        )
        raise FalhaLakehouseError(str(erro)) from erro

    return float(valor) if valor is not None else None


def _consulta_por_view(
    metrica: Metrica, filtro: str | None, inicio: date, fim: date
) -> tuple[str, dict[str, object]]:
    view = _validar_identificador(metrica.nome_view, "nome_view")
    coluna = _validar_identificador(metrica.coluna_filtro, "coluna_filtro")

    sql = (
        f"SELECT SUM(VALOR) FROM {view} "  # noqa: S608 - identificador validado acima
        f"WHERE {_COLUNA_DATA_VIEW} BETWEEN :inicio AND :fim"
    )
    parametros: dict[str, object] = {"inicio": inicio, "fim": fim}
    if filtro:
        sql += f" AND {coluna} = :filtro"
        parametros["filtro"] = _normalizar_filtro(coluna, filtro)
    return sql, parametros


def _consulta_fallback(
    metrica: Metrica, filtro: str | None, inicio: date, fim: date
) -> tuple[str, dict[str, object]]:
    settings = get_settings()
    agregacao = AGREGACOES_FALLBACK.get(metrica.nome_view)
    if agregacao is None:
        raise FalhaLakehouseError(
            f"métrica {metrica.nome_metrica!r} não tem agregação equivalente no "
            f"modo fallback (nome_view={metrica.nome_view!r}). Crie a view e "
            f"mude LAKEHOUSE_MODO para 'views', ou registre a agregação."
        )

    tabela = _validar_identificador(
        settings.lakehouse_tabela_fallback, "LAKEHOUSE_TABELA_FALLBACK"
    )
    coluna = _validar_identificador(metrica.coluna_filtro, "coluna_filtro")

    sql = (
        f"SELECT {agregacao} FROM {tabela} "  # noqa: S608 - identificadores validados
        f"WHERE {_COLUNA_DATA_FALLBACK} BETWEEN :inicio AND :fim"
    )
    parametros: dict[str, object] = {"inicio": inicio, "fim": fim}
    if filtro:
        sql += f" AND {coluna} = :filtro"
        parametros["filtro"] = _normalizar_filtro(coluna, filtro)
    return sql, parametros
