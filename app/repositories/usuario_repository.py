"""Consultas sobre USUARIOS."""

from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.tipos import esta_ativo
from app.models import Usuario

# Caractere de escape do LIKE. Sem ele, um "%" ou "_" digitado na busca viraria
# curinga: buscar por "%" listaria a base inteira.
_ESCAPE = "\\"


def _com_relacoes(consulta):  # type: ignore[no-untyped-def]
    """Carrega cargo e organizacao no mesmo SELECT.

    As relacoes sao lazy="raise", entao quem precisa do nome do cargo ou da
    organizacao pede explicitamente -- e evita N+1 na listagem paginada.
    """
    return consulta.options(joinedload(Usuario.cargo), joinedload(Usuario.organizacao))


def _escapar_like(termo: str) -> str:
    for caractere in (_ESCAPE, "%", "_"):
        termo = termo.replace(caractere, _ESCAPE + caractere)
    return termo


def _filtro_busca(consulta, busca: str | None):  # type: ignore[no-untyped-def]
    """Aplica UPPER(nome_completo) LIKE '%TERMO%', como o contrato especifica.

    O UPPER casa com o indice funcional IDX_USUARIOS_NC do DDL.
    """
    if not busca or not busca.strip():
        return consulta
    padrao = f"%{_escapar_like(busca.strip().upper())}%"
    return consulta.where(
        func.upper(Usuario.nome_completo).like(padrao, escape=_ESCAPE)
    )


def contar(db: Session, busca: str | None = None) -> int:
    consulta = _filtro_busca(
        select(func.count()).select_from(Usuario).where(esta_ativo(Usuario.ativo)), busca
    )
    return db.execute(consulta).scalar_one()


def listar(
    db: Session, busca: str | None, pagina: int, tamanho: int
) -> list[Usuario]:
    """Apenas usuarios ativos: desativados nao aparecem em nenhuma listagem."""
    consulta: Select[tuple[Usuario]] = _com_relacoes(
        _filtro_busca(select(Usuario).where(esta_ativo(Usuario.ativo)), busca)
        # Ordem determinstica. Sem o desempate por id, duas linhas de mesmo nome
        # poderiam trocar de posicao entre paginas, fazendo a paginacao repetir
        # uma e pular outra.
        .order_by(func.upper(Usuario.nome_completo), Usuario.id_usuario)
        .offset((pagina - 1) * tamanho)
        .limit(tamanho)
    )
    return list(db.execute(consulta).unique().scalars().all())


def buscar_por_email(db: Session, email: str) -> Usuario | None:
    consulta = _com_relacoes(
        select(Usuario).where(func.lower(Usuario.email) == email.strip().lower())
    )
    return db.execute(consulta).unique().scalar_one_or_none()


def buscar_por_id(db: Session, id_usuario: int) -> Usuario | None:
    consulta = _com_relacoes(select(Usuario).where(Usuario.id_usuario == id_usuario))
    return db.execute(consulta).unique().scalar_one_or_none()


def buscar_conflito_de_unicidade(
    db: Session,
    cpf: str | None,
    email: str | None,
    telefone: str | None,
    ignorar_id: int | None = None,
) -> Usuario | None:
    """Procura um usuario que ja ocupe algum dos tres valores unicos.

    Vale tambem sobre usuarios desativados: a desativacao e logica e as
    constraints UK_USUARIOS_* continuam valendo sobre eles. Comportamento
    conhecido e aceito nesta versao do contrato.
    """
    condicoes = []
    if cpf:
        condicoes.append(Usuario.cpf == cpf)
    if email:
        condicoes.append(func.lower(Usuario.email) == email.lower())
    if telefone:
        condicoes.append(Usuario.telefone == telefone)
    if not condicoes:
        return None

    consulta = select(Usuario).where(or_(*condicoes))
    if ignorar_id is not None:
        consulta = consulta.where(Usuario.id_usuario != ignorar_id)
    return db.execute(consulta).scalars().first()
