"""Relatorio em CSV."""

from __future__ import annotations

import csv
import io

from app.schemas.relatorio import RelatorioResponse

CABECALHO = ["id_metrica", "nome", "filtro", "valor", "unidade"]


def gerar_csv(relatorio: RelatorioResponse) -> bytes:
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    escritor.writerow(CABECALHO)
    for resultado in relatorio.resultados:
        escritor.writerow(
            [
                resultado.id_metrica,
                resultado.nome,
                resultado.filtro or "",
                "" if resultado.valor is None else resultado.valor,
                resultado.unidade,
            ]
        )

    # BOM: sem ele o Excel em portugues abre "Internações" como "InternaÃ§Ãµes".
    # O ponto e virgula como separador tambem e o que o Excel pt-BR espera.
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
