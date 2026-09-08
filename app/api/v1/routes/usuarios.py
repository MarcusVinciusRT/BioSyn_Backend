"""Secao 7 do contrato: Usuarios.

Tela exclusiva de administrador. Nao existe autocadastro.
"""

from fastapi import APIRouter, Path, Query, Response, status

from app.core.deps import AdminDep, SessaoDep
from app.schemas.usuario import (
    PaginaUsuarios,
    UsuarioAtualizado,
    UsuarioAtualizar,
    UsuarioCriado,
    UsuarioCriar,
)
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("", response_model=PaginaUsuarios, summary="Listar e buscar usuários")
def listar(
    db: SessaoDep,
    _: AdminDep,
    busca: str | None = Query(
        default=None,
        max_length=200,
        description="Trecho do nome completo, sem distinção de maiúsculas.",
    ),
    pagina: int = Query(default=1, ge=1, description="Página desejada."),
    tamanho: int = Query(
        default=20, ge=1, le=100, description="Registros por página, máximo 100."
    ),
) -> PaginaUsuarios:
    """Acesso: somente administrador. Apenas usuários ativos são retornados."""
    return usuario_service.listar(db, busca, pagina, tamanho)


@router.post(
    "",
    response_model=UsuarioCriado,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar usuário",
)
def criar(corpo: UsuarioCriar, db: SessaoDep, _: AdminDep) -> UsuarioCriado:
    """Acesso: somente administrador.

    Cria o endereço e o usuário em uma única transação.
    """
    return usuario_service.criar(db, corpo)


@router.put(
    "/{id_usuario}", response_model=UsuarioAtualizado, summary="Editar usuário"
)
def atualizar(
    corpo: UsuarioAtualizar,
    db: SessaoDep,
    _: AdminDep,
    id_usuario: int = Path(ge=1),
) -> UsuarioAtualizado:
    """Acesso: somente administrador."""
    return usuario_service.atualizar(db, id_usuario, corpo)


@router.delete(
    "/{id_usuario}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Desativar usuário",
)
def desativar(
    db: SessaoDep,
    solicitante: AdminDep,
    id_usuario: int = Path(ge=1),
) -> None:
    """Acesso: somente administrador. Exclusão lógica (ativo = 0)."""
    usuario_service.desativar(db, id_usuario, solicitante.id_usuario)
