"""Ciclo completo de usuario contra o Oracle real.

Marcado com `banco`: em CI sem acesso ao ADB, rode com -m "not banco".
Cada teste limpa o que criou (DELETE fisico, nao a desativacao logica da API).
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, CodigoErro
from app.db.session import criar_sessao, encerrar_banco, iniciar_banco
from app.models import Cargo, Organizacao, Usuario
from app.schemas.usuario import UsuarioAtualizar, UsuarioCriar
from app.services import usuario_service

pytestmark = pytest.mark.banco

CPF_TESTE = "90000000001"
EMAIL_TESTE = "pytest.usuario@saude.gov.br"
TELEFONE_TESTE = "11900000001"


@pytest.fixture(scope="module", autouse=True)
def banco() -> Iterator[None]:
    iniciar_banco()
    yield
    encerrar_banco()


@pytest.fixture
def db() -> Iterator[Session]:
    sessao = criar_sessao()
    yield sessao
    sessao.close()


@pytest.fixture
def referencias(db: Session) -> tuple[int, int]:
    """Um cargo e uma organizacao ativos quaisquer, para amarrar o usuario."""
    cargo = db.execute(select(Cargo).limit(1)).scalar_one_or_none()
    org = db.execute(select(Organizacao).limit(1)).scalar_one_or_none()
    if cargo is None or org is None:
        pytest.skip("rode scripts/seed_dados_apoio.py antes")
    return cargo.id_cargo, org.id_organizacao


def _limpar(db: Session) -> None:
    """Remove fisicamente o usuario de teste e o endereco dele."""
    usuario = db.execute(
        select(Usuario).where(Usuario.cpf == CPF_TESTE)
    ).scalar_one_or_none()
    if usuario is None:
        return
    id_endereco = usuario.enderecos_id_endereco
    db.delete(usuario)
    db.flush()
    db.execute(text("DELETE FROM enderecos WHERE id_endereco = :i"), {"i": id_endereco})
    db.commit()


@pytest.fixture(autouse=True)
def limpeza(db: Session) -> Iterator[None]:
    _limpar(db)
    yield
    _limpar(db)


def _dados(referencias: tuple[int, int], **mudancas) -> UsuarioCriar:
    cargo_id, organizacao_id = referencias
    base = {
        "cpf": CPF_TESTE,
        "email": EMAIL_TESTE,
        "telefone": TELEFONE_TESTE,
        "senha": "senhaDeTeste123",
        "nome": "Pytest",
        "sobrenome": "Usuario",
        "is_admin": False,
        "cargo_id": cargo_id,
        "organizacao_id": organizacao_id,
        "endereco": {
            "tipo_logradouro": "Rua",
            "logradouro": "de Teste",
            "numero": 1,
            "cep": "01001000",
            "estado_uf": "SP",
            "cidade": "São Paulo",
            "complemento": None,
        },
    }
    return UsuarioCriar(**{**base, **mudancas})


def test_cadastro_cria_endereco_e_usuario_na_mesma_transacao(db, referencias):
    resposta = usuario_service.criar(db, _dados(referencias))

    assert resposta.id_usuario > 0
    # nome_completo e montado pela API, nao enviado pelo cliente.
    assert resposta.nome_completo == "Pytest Usuario"
    # criado_em vem do DEFAULT do banco e chega com fuso.
    assert resposta.criado_em.tzinfo is not None

    gravado = db.execute(
        select(Usuario).where(Usuario.cpf == CPF_TESTE)
    ).scalar_one()
    assert gravado.enderecos_id_endereco is not None
    assert gravado.ativo is True
    # A senha e gravada como hash bcrypt, nunca em texto puro.
    assert gravado.senha.startswith("$2b$")
    assert "senhaDeTeste123" not in gravado.senha


def test_cadastro_falha_nao_deixa_endereco_orfao(db, referencias):
    """Se o usuario nao entrar, o endereco criado antes dele nao pode sobrar."""
    antes = db.execute(text("SELECT COUNT(*) FROM enderecos")).scalar_one()

    usuario_service.criar(db, _dados(referencias))
    with pytest.raises(AppError) as erro:
        usuario_service.criar(db, _dados(referencias, email="outro@saude.gov.br",
                                         telefone="11900000002"))
    assert erro.value.codigo == CodigoErro.CPF_DUPLICADO

    depois = db.execute(text("SELECT COUNT(*) FROM enderecos")).scalar_one()
    assert depois == antes + 1  # so o endereco do cadastro bem-sucedido


@pytest.mark.parametrize(
    ("campo", "valor", "codigo"),
    [
        ("email", EMAIL_TESTE, CodigoErro.EMAIL_DUPLICADO),
        ("telefone", TELEFONE_TESTE, CodigoErro.TELEFONE_DUPLICADO),
    ],
)
def test_unicidade_por_campo(db, referencias, campo, valor, codigo):
    usuario_service.criar(db, _dados(referencias))
    outro = {"cpf": "90000000009", campo: valor}
    if campo != "email":
        outro["email"] = "diferente@saude.gov.br"
    if campo != "telefone":
        outro["telefone"] = "11900000009"

    with pytest.raises(AppError) as erro:
        usuario_service.criar(db, _dados(referencias, **outro))
    assert erro.value.codigo == codigo
    db.rollback()
    db.execute(text("DELETE FROM usuarios WHERE cpf = '90000000009'"))
    db.commit()


def test_unicidade_vale_tambem_sobre_desativados(db, referencias):
    """Comportamento conhecido e aceito no contrato: a desativacao e logica,
    mas as constraints UK_USUARIOS_* continuam valendo."""
    criado = usuario_service.criar(db, _dados(referencias))
    usuario_service.desativar(db, criado.id_usuario, id_solicitante=999999)

    with pytest.raises(AppError) as erro:
        usuario_service.criar(db, _dados(referencias))
    assert erro.value.codigo == CodigoErro.CPF_DUPLICADO


def test_referencia_inativa_e_recusada(db, referencias):
    cargo_id, organizacao_id = referencias
    db.execute(text("UPDATE cargos SET ativo=0 WHERE id_cargo=:i"), {"i": cargo_id})
    db.flush()
    try:
        with pytest.raises(AppError) as erro:
            usuario_service.criar(db, _dados(referencias))
        assert erro.value.codigo == CodigoErro.REFERENCIA_INVALIDA
    finally:
        db.rollback()


def test_edicao_mantem_a_senha_quando_ausente(db, referencias):
    criado = usuario_service.criar(db, _dados(referencias))
    hash_original = db.execute(
        select(Usuario.senha).where(Usuario.id_usuario == criado.id_usuario)
    ).scalar_one()

    cargo_id, organizacao_id = referencias
    usuario_service.atualizar(
        db,
        criado.id_usuario,
        UsuarioAtualizar(
            email=EMAIL_TESTE, telefone=TELEFONE_TESTE, nome="Pytest",
            sobrenome="Usuario Editado", is_admin=False,
            cargo_id=cargo_id, organizacao_id=organizacao_id,
            endereco={"tipo_logradouro": "Avenida", "logradouro": "Nova",
                      "numero": "2", "cep": "01002000", "estado_uf": "SP",
                      "cidade": "São Paulo"},
        ),
    )
    db.expire_all()
    atual = db.execute(
        select(Usuario).where(Usuario.id_usuario == criado.id_usuario)
    ).scalar_one()
    assert atual.senha == hash_original
    assert atual.nome_completo == "Pytest Usuario Editado"


def test_edicao_ignora_mudanca_de_cpf(db, referencias):
    criado = usuario_service.criar(db, _dados(referencias))
    cargo_id, organizacao_id = referencias
    usuario_service.atualizar(
        db,
        criado.id_usuario,
        UsuarioAtualizar(
            cpf="11111111111", email=EMAIL_TESTE, telefone=TELEFONE_TESTE,
            nome="Pytest", sobrenome="Usuario", is_admin=False,
            cargo_id=cargo_id, organizacao_id=organizacao_id,
            endereco={"tipo_logradouro": "Rua", "logradouro": "de Teste",
                      "numero": "1", "cep": "01001000", "estado_uf": "SP",
                      "cidade": "São Paulo"},
        ),
    )
    db.expire_all()
    assert db.execute(
        select(Usuario.cpf).where(Usuario.id_usuario == criado.id_usuario)
    ).scalar_one() == CPF_TESTE


def test_desativacao_e_logica_e_a_linha_permanece(db, referencias):
    """A linha fica no banco para preservar a FK do historico de alertas."""
    criado = usuario_service.criar(db, _dados(referencias))
    usuario_service.desativar(db, criado.id_usuario, id_solicitante=999999)

    db.expire_all()
    usuario = db.execute(
        select(Usuario).where(Usuario.id_usuario == criado.id_usuario)
    ).scalar_one()
    assert usuario.ativo is False


def test_admin_nao_desativa_a_propria_conta(db, referencias):
    criado = usuario_service.criar(db, _dados(referencias))
    with pytest.raises(AppError) as erro:
        usuario_service.desativar(db, criado.id_usuario, id_solicitante=criado.id_usuario)
    assert erro.value.codigo == CodigoErro.AUTO_DESATIVACAO


def test_busca_encontra_por_trecho_sem_distincao_de_maiusculas(db, referencias):
    usuario_service.criar(db, _dados(referencias))
    pagina = usuario_service.listar(db, busca="pYtEsT", pagina=1, tamanho=20)
    assert any(i.email == EMAIL_TESTE for i in pagina.itens)


def test_desativado_some_da_listagem(db, referencias):
    criado = usuario_service.criar(db, _dados(referencias))
    usuario_service.desativar(db, criado.id_usuario, id_solicitante=999999)
    pagina = usuario_service.listar(db, busca="Pytest", pagina=1, tamanho=20)
    assert all(i.id_usuario != criado.id_usuario for i in pagina.itens)


def test_auditoria_registra_o_cadastro_sem_vazar_a_senha(db, referencias):
    """As triggers *_AUD_TRG gravam sozinhas, na mesma transação da DML."""
    criado = usuario_service.criar(db, _dados(referencias))
    linhas = db.execute(
        text(
            "SELECT dados_novos FROM logs_auditoria "
            "WHERE tabela='USUARIOS' AND id_linha=:i AND acao='INSERT'"
        ),
        {"i": criado.id_usuario},
    ).scalars().all()
    assert len(linhas) == 1
    assert "$2b$" not in str(linhas[0])
