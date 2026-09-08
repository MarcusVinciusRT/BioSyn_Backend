"""Schemas da secao 5 (Alertas)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constantes import UFS
from app.schemas.comum import DataHora

LIMITE_MENSAGEM = 500


class AlertaRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 500 e o limite da coluna no banco (VARCHAR2(500)).
    mensagem: str = Field(min_length=1, max_length=LIMITE_MENSAGEM)
    estado_uf: str

    @field_validator("mensagem")
    @classmethod
    def _mensagem_com_conteudo(cls, v: str) -> str:
        limpa = v.strip()
        if not limpa:
            raise ValueError("Não pode ser vazia ou conter apenas espaços.")
        return limpa

    @field_validator("estado_uf")
    @classmethod
    def _uf_valida(cls, v: str) -> str:
        uf = v.strip().upper()
        if uf not in UFS:
            raise ValueError("Deve ser uma UF brasileira válida, com 2 letras.")
        return uf


class AlertaResponse(BaseModel):
    id_alerta: int
    estado_uf_destino: str
    # Quantidade de destinatarios aceitos pelo canal. Nao ha rastreio de
    # entrega individual.
    destinatarios: int
    criado_em: DataHora
