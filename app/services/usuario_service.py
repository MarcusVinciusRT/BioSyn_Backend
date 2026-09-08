"""Regras da secao 7 (Usuarios).

Nao existe autocadastro: o administrador cria, edita e desativa contas.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.core.security import hash_senha
from app.db.tipos import esta_ativo
from app.models import Cargo, Endereco, Organizacao, Usuario
from app.repositories import usuario_repository
from app.schemas.usuario import (
    CargoResumo,
    EnderecoEntrada,
    OrganizacaoResumo,
    PaginaUsuarios,
    UsuarioAtualizado,
    UsuarioAtualizar,
    UsuarioCriado,
    UsuarioCriar,
    UsuarioItem,
)

logger = logging.getLogger(__name__)

TAMANHO_MAXIMO_PAGINA = 100

# Constraint violada -> codigo do contrato. A checagem previa de unicidade
# resolve o caso comum, mas duas requisicoes simultaneas podem passar por ela
# ao mesmo tempo; ai quem barra e o banco, e a mensagem precisa ser a mesma.
_CONSTRAINT_PARA_CODIGO = {
    "UK_USUARIOS_CPF": CodigoErro.CPF_DUPLICADO,
    "UK_USUARIOS_EMAIL": CodigoErro.EMAIL_DUPLICADO,
    "UK_USUARIOS_TELEFONE": CodigoErro.TELEFONE_DUPLICADO,
}


# --- Leitura ---------------------------------------------------------------

def _para_item(usuario: Usuario) -> UsuarioItem:
    return UsuarioItem(
        id_usuario=usuario.id_usuario,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        telefone=usuario.telefone,
        is_admin=usuario.is_admin,
        cargo=CargoResumo.model_validate(usuario.cargo),
        organizacao=OrganizacaoResumo(
            id_organizacao=usuario.organizacao.id_organizacao,
            nome=usuario.organizacao.nome_organizacao,
        ),
    )


def listar(
    db: Session, busca: str | None, pagina: int, tamanho: int
) -> PaginaUsuarios:
    tamanho = min(tamanho, TAMANHO_MAXIMO_PAGINA)
    total = usuario_repository.contar(db, busca)
    usuarios = usuario_repository.listar(db, busca, pagina, tamanho)
    return PaginaUsuarios(
        total=total,
        pagina=pagina,
        tamanho=tamanho,
        itens=[_para_item(u) for u in usuarios],
    )


# --- Escrita ---------------------------------------------------------------

def _traduzir_integridade(erro: IntegrityError) -> AppError:
    texto = str(erro.orig).upper()
    for constraint, codigo in _CONSTRAINT_PARA_CODIGO.items():
        if constraint in texto:
            return AppError(codigo)
    logger.error("violacao de integridade nao mapeada: %s", erro.orig)
    return AppError(CodigoErro.ERRO_INTERNO)


def _garantir_unicidade(
    db: Session,
    cpf: str | None,
    email: str,
    telefone: str,
    ignorar_id: int | None = None,
) -> None:
    conflito = usuario_repository.buscar_conflito_de_unicidade(
        db, cpf, email, telefone, ignorar_id
    )
    if conflito is None:
        return
    if cpf and conflito.cpf == cpf:
        raise AppError(CodigoErro.CPF_DUPLICADO)
    if conflito.email.lower() == email.lower():
        raise AppError(CodigoErro.EMAIL_DUPLICADO)
    raise AppError(CodigoErro.TELEFONE_DUPLICADO)


def _validar_referencias(db: Session, cargo_id: int, organizacao_id: int) -> None:
    """Cargo e organizacao precisam existir E estar ativos."""
    cargo = db.execute(
        select(Cargo.id_cargo).where(
            Cargo.id_cargo == cargo_id, esta_ativo(Cargo.ativo)
        )
    ).scalar_one_or_none()
    if cargo is None:
        raise AppError(
            CodigoErro.REFERENCIA_INVALIDA, "Cargo inexistente ou inativo."
        )

    organizacao = db.execute(
        select(Organizacao.id_organizacao).where(
            Organizacao.id_organizacao == organizacao_id,
            esta_ativo(Organizacao.ativo),
        )
    ).scalar_one_or_none()
    if organizacao is None:
        raise AppError(
            CodigoErro.REFERENCIA_INVALIDA, "Organização inexistente ou inativa."
        )


def _aplicar_endereco(destino: Endereco, dados: EnderecoEntrada) -> None:
    destino.tipo_logradouro = dados.tipo_logradouro
    destino.logradouro = dados.logradouro
    destino.numero = dados.numero
    destino.cep = dados.cep
    destino.estado_uf = dados.estado_uf
    destino.cidade = dados.cidade
    destino.complemento = dados.complemento


def criar(db: Session, dados: UsuarioCriar) -> UsuarioCriado:
    """Cria endereco e usuario na mesma transacao."""
    _validar_referencias(db, dados.cargo_id, dados.organizacao_id)
    _garantir_unicidade(db, dados.cpf, dados.email, dados.telefone)

    endereco = Endereco(ativo=True)
    _aplicar_endereco(endereco, dados.endereco)
    db.add(endereco)
    db.flush()  # precisa do id_endereco para amarrar o usuario

    usuario = Usuario(
        cpf=dados.cpf,
        email=dados.email,
        telefone=dados.telefone,
        senha=hash_senha(dados.senha),
        nome=dados.nome,
        sobrenome=dados.sobrenome,
        # Nao vem do cliente: a API monta e grava, porque e a coluna da busca.
        nome_completo=f"{dados.nome} {dados.sobrenome}",
        is_admin=dados.is_admin,
        ativo=True,
        cargos_id_cargo=dados.cargo_id,
        enderecos_id_endereco=endereco.id_endereco,
        organizacoes_id_organizacao=dados.organizacao_id,
    )
    db.add(usuario)

    try:
        db.flush()
    except IntegrityError as erro:
        db.rollback()
        raise _traduzir_integridade(erro) from erro

    db.commit()
    # criado_em vem do DEFAULT do banco, entao so existe depois do commit.
    db.refresh(usuario)
    logger.info("usuario criado id=%s admin=%s", usuario.id_usuario, usuario.is_admin)

    return UsuarioCriado(
        id_usuario=usuario.id_usuario,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        criado_em=usuario.criado_em,
    )


def atualizar(db: Session, id_usuario: int, dados: UsuarioAtualizar) -> UsuarioAtualizado:
    usuario = usuario_repository.buscar_por_id(db, id_usuario)
    if usuario is None or not usuario.ativo:
        raise AppError(CodigoErro.USUARIO_NAO_ENCONTRADO)

    _validar_referencias(db, dados.cargo_id, dados.organizacao_id)
    # cpf=None aqui de proposito: o CPF e imutavel, entao nao entra na checagem.
    _garantir_unicidade(db, None, dados.email, dados.telefone, ignorar_id=id_usuario)

    usuario.email = dados.email
    usuario.telefone = dados.telefone
    usuario.nome = dados.nome
    usuario.sobrenome = dados.sobrenome
    usuario.nome_completo = f"{dados.nome} {dados.sobrenome}"
    usuario.is_admin = dados.is_admin
    usuario.cargos_id_cargo = dados.cargo_id
    usuario.organizacoes_id_organizacao = dados.organizacao_id

    # cpf enviado com valor diferente do atual e ignorado (contrato).
    if dados.cpf is not None and dados.cpf != usuario.cpf:
        logger.info("cpf ignorado na edicao do usuario id=%s (campo imutável)", id_usuario)

    # senha ausente mantem a atual.
    if dados.senha is not None:
        usuario.senha = hash_senha(dados.senha)

    endereco = db.get(Endereco, usuario.enderecos_id_endereco)
    if endereco is not None:
        _aplicar_endereco(endereco, dados.endereco)

    try:
        db.flush()
    except IntegrityError as erro:
        db.rollback()
        raise _traduzir_integridade(erro) from erro

    db.commit()
    # atualizado_em e escrito pela trigger USUARIOS_UPD_TRG.
    db.refresh(usuario)
    logger.info("usuario atualizado id=%s", id_usuario)

    return UsuarioAtualizado(
        id_usuario=usuario.id_usuario,
        nome_completo=usuario.nome_completo,
        email=usuario.email,
        atualizado_em=usuario.atualizado_em,
    )


def desativar(db: Session, id_usuario: int, id_solicitante: int) -> None:
    """Exclusao logica: marca ativo = 0.

    A linha permanece no banco para preservar a integridade do historico de
    alertas (FK alerta_disparados -> usuarios).
    """
    if id_usuario == id_solicitante:
        raise AppError(CodigoErro.AUTO_DESATIVACAO)

    usuario = usuario_repository.buscar_por_id(db, id_usuario)
    if usuario is None or not usuario.ativo:
        raise AppError(CodigoErro.USUARIO_NAO_ENCONTRADO)

    usuario.ativo = False
    db.commit()
    logger.info("usuario desativado id=%s por id=%s", id_usuario, id_solicitante)
