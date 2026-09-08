"""Regra de autenticacao, sem tocar no banco."""

import pytest

from app.core.errors import AppError, CodigoErro
from app.core.security import decodificar_token, hash_senha
from app.models import Cargo, Organizacao, Usuario
from app.repositories import usuario_repository
from app.services import auth_service

SENHA = "senhaCorreta123"


def montar_usuario(*, ativo: bool = True, is_admin: bool = True) -> Usuario:
    usuario = Usuario(
        id_usuario=42,
        cpf="12345678901",
        email="maria.santos@saude.gov.br",
        telefone="11987654321",
        senha=hash_senha(SENHA),
        nome="Maria",
        sobrenome="Santos",
        nome_completo="Maria Santos",
        is_admin=is_admin,
        ativo=ativo,
        cargos_id_cargo=3,
        enderecos_id_endereco=1,
        organizacoes_id_organizacao=1,
    )
    usuario.cargo = Cargo(id_cargo=3, nome_cargo="Analista Epidemiológico", ativo=True)
    usuario.organizacao = Organizacao(
        id_organizacao=1,
        nome_organizacao="Ministério da Saúde",
        enderecos_id_endereco=1,
        ativo=True,
    )
    return usuario


@pytest.fixture
def repo_com(monkeypatch):
    """Substitui a busca por e-mail, para o service rodar sem banco."""
    def instalar(usuario: Usuario | None) -> None:
        monkeypatch.setattr(
            usuario_repository, "buscar_por_email", lambda db, email: usuario
        )
    return instalar


def test_login_valido_devolve_token_e_o_objeto_usuario(repo_com):
    repo_com(montar_usuario())
    resposta = auth_service.autenticar(None, "maria.santos@saude.gov.br", SENHA)

    assert resposta.token_type == "bearer"
    assert resposta.expira_em == 1800
    assert resposta.usuario.id_usuario == 42
    assert resposta.usuario.nome_completo == "Maria Santos"
    # cargo e organizacao sao textos aqui, nao objetos (secao 3 do contrato).
    assert resposta.usuario.cargo == "Analista Epidemiológico"
    assert resposta.usuario.organizacao == "Ministério da Saúde"


def test_token_emitido_carrega_id_e_flag_de_admin(repo_com):
    repo_com(montar_usuario(is_admin=True))
    resposta = auth_service.autenticar(None, "maria.santos@saude.gov.br", SENHA)

    decodificado = decodificar_token(resposta.access_token)
    assert decodificado.id_usuario == 42
    assert decodificado.is_admin is True


def test_a_senha_nunca_aparece_na_resposta(repo_com):
    repo_com(montar_usuario())
    resposta = auth_service.autenticar(None, "maria.santos@saude.gov.br", SENHA)
    assert "senha" not in resposta.model_dump()["usuario"]
    assert SENHA not in resposta.model_dump_json()


@pytest.mark.parametrize(
    ("cenario", "usuario", "senha"),
    [
        ("email inexistente", None, SENHA),
        ("senha incorreta", "ativo", "senhaErrada"),
        ("usuario inativo", "inativo", SENHA),
    ],
)
def test_as_tres_falhas_sao_indistinguiveis(repo_com, cenario, usuario, senha):
    """O contrato exige o mesmo 401 nos tres casos: distinguir entregaria a um
    atacante a lista de e-mails validos da base."""
    mapa = {
        None: None,
        "ativo": montar_usuario(ativo=True),
        "inativo": montar_usuario(ativo=False),
    }
    repo_com(mapa[usuario])

    with pytest.raises(AppError) as capturado:
        auth_service.autenticar(None, "maria.santos@saude.gov.br", senha)

    assert capturado.value.codigo == CodigoErro.CREDENCIAIS_INVALIDAS
    assert capturado.value.http_status == 401
    assert capturado.value.mensagem == "E-mail ou senha incorretos."


def test_hash_descartavel_e_um_bcrypt_valido():
    """Se nao fosse, o checkpw falharia na hora e o 401 instantaneo denunciaria
    que o e-mail nao existe na base."""
    assert auth_service._HASH_DESCARTAVEL.startswith("$2b$")
