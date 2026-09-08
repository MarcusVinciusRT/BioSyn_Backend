"""Consultas para o disparo de alertas."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.tipos import esta_ativo
from app.integrations.notificacao.base import Destinatario
from app.models import Endereco, Usuario


def buscar_destinatarios_por_uf(db: Session, uf: str) -> list[Destinatario]:
    """Usuarios ativos cujo endereco pertence a UF informada.

    O filtro de atividade e sobre o usuario, como o contrato descreve: quem foi
    desativado nao recebe mais alerta.
    """
    consulta = (
        select(Usuario.nome_completo, Usuario.email)
        .join(Endereco, Usuario.enderecos_id_endereco == Endereco.id_endereco)
        .where(esta_ativo(Usuario.ativo), Endereco.estado_uf == uf)
    )
    return [
        Destinatario(nome=nome, email=email)
        for nome, email in db.execute(consulta).all()
    ]
