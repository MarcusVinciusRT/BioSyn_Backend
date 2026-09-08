#!/usr/bin/env python
"""Cria o primeiro administrador do BioSyn.

Necessario porque a plataforma nao tem autocadastro: todo usuario e criado por
um administrador, entao sem este bootstrap nao ha como entrar na aplicacao.

Alem do usuario, cria o cargo, a organizacao e os enderecos de que ele depende,
caso ainda nao existam. Rodar de novo com o mesmo e-mail nao duplica nada:
o script aborta avisando.

Uso:
    python scripts/criar_admin.py --email admin@saude.gov.br --nome Maria --sobrenome Santos
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_senha  # noqa: E402
from app.db.session import encerrar_banco, iniciar_banco, sessao  # noqa: E402
from app.models import Cargo, Endereco, Organizacao, Usuario  # noqa: E402

SENHA_MINIMA = 8


def _obter_ou_criar_endereco(db: Session, cidade: str, uf: str) -> Endereco:
    endereco = db.execute(
        select(Endereco).where(Endereco.cidade == cidade, Endereco.estado_uf == uf)
    ).scalars().first()
    if endereco is not None:
        return endereco

    endereco = Endereco(
        tipo_logradouro="Avenida",
        logradouro="Não informado",
        numero="0",
        cep="70058900",
        estado_uf=uf,
        cidade=cidade,
        complemento=None,
        ativo=True,
    )
    db.add(endereco)
    db.flush()
    print(f"  endereco criado      id={endereco.id_endereco} ({cidade}/{uf})")
    return endereco


def _obter_ou_criar_cargo(db: Session, nome: str) -> Cargo:
    cargo = db.execute(select(Cargo).where(Cargo.nome_cargo == nome)).scalar_one_or_none()
    if cargo is not None:
        print(f"  cargo reaproveitado  id={cargo.id_cargo} ({nome})")
        return cargo
    cargo = Cargo(nome_cargo=nome, ativo=True)
    db.add(cargo)
    db.flush()
    print(f"  cargo criado         id={cargo.id_cargo} ({nome})")
    return cargo


def _obter_ou_criar_organizacao(db: Session, nome: str, endereco: Endereco) -> Organizacao:
    org = db.execute(
        select(Organizacao).where(Organizacao.nome_organizacao == nome)
    ).scalar_one_or_none()
    if org is not None:
        print(f"  organizacao reaprov. id={org.id_organizacao} ({nome})")
        return org
    org = Organizacao(
        nome_organizacao=nome,
        enderecos_id_endereco=endereco.id_endereco,
        ativo=True,
    )
    db.add(org)
    db.flush()
    print(f"  organizacao criada   id={org.id_organizacao} ({nome})")
    return org


def _ler_senha(argumento: str | None) -> str:
    if argumento:
        return argumento
    senha = getpass.getpass("Senha do administrador: ")
    if senha != getpass.getpass("Confirme a senha: "):
        sys.exit("As senhas não conferem.")
    return senha


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria o primeiro administrador.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--nome", required=True)
    parser.add_argument("--sobrenome", required=True)
    parser.add_argument("--cpf", required=True, help="11 dígitos, apenas números")
    parser.add_argument("--telefone", required=True, help="DDD + número, apenas dígitos")
    parser.add_argument(
        "--senha",
        help="Se omitido, é solicitada interativamente (não fica no histórico do shell).",
    )
    parser.add_argument("--cargo", default="Administrador do Sistema")
    parser.add_argument("--organizacao", default="Ministério da Saúde")
    parser.add_argument("--cidade", default="Brasília")
    parser.add_argument("--uf", default="DF")
    args = parser.parse_args()

    cpf = "".join(filter(str.isdigit, args.cpf))
    telefone = "".join(filter(str.isdigit, args.telefone))
    if len(cpf) != 11:
        sys.exit(f"CPF deve ter 11 dígitos numéricos (recebi {len(cpf)}).")
    if not telefone:
        sys.exit("Telefone é obrigatório.")

    senha = _ler_senha(args.senha)
    if len(senha) < SENHA_MINIMA:
        sys.exit(f"A senha deve ter no mínimo {SENHA_MINIMA} caracteres.")

    iniciar_banco()
    try:
        with sessao() as db:
            ja_existe = db.execute(
                select(Usuario).where(func.lower(Usuario.email) == args.email.lower())
            ).scalar_one_or_none()
            if ja_existe is not None:
                sys.exit(
                    f"Já existe usuário com o e-mail {args.email} "
                    f"(id={ja_existe.id_usuario}). Nada foi alterado."
                )

            print("Criando dependências:")
            endereco_org = _obter_ou_criar_endereco(db, args.cidade, args.uf)
            cargo = _obter_ou_criar_cargo(db, args.cargo)
            organizacao = _obter_ou_criar_organizacao(db, args.organizacao, endereco_org)
            # O DDL exige um endereco proprio por usuario.
            endereco_usuario = _obter_ou_criar_endereco(db, args.cidade, args.uf)

            usuario = Usuario(
                cpf=cpf,
                email=args.email.strip().lower(),
                telefone=telefone,
                senha=hash_senha(senha),
                nome=args.nome.strip(),
                sobrenome=args.sobrenome.strip(),
                nome_completo=f"{args.nome.strip()} {args.sobrenome.strip()}",
                is_admin=True,
                ativo=True,
                cargos_id_cargo=cargo.id_cargo,
                enderecos_id_endereco=endereco_usuario.id_endereco,
                organizacoes_id_organizacao=organizacao.id_organizacao,
            )
            db.add(usuario)
            db.flush()
            print(f"\nAdministrador criado: id={usuario.id_usuario} {usuario.email}")
    finally:
        encerrar_banco()


if __name__ == "__main__":
    main()
