"""Serializacao do relatorio para download (secao 6)."""

from app.exporters.csv_exporter import gerar_csv
from app.exporters.xlsx_exporter import gerar_xlsx

EXTENSAO = {"csv": "csv", "xlsx": "xlsx"}
TIPO_MIME = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
}

__all__ = ["EXTENSAO", "TIPO_MIME", "gerar_csv", "gerar_xlsx"]
