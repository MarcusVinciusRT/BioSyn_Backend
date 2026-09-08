"""SQL da listagem de usuarios, compilado sem banco."""

from sqlalchemy import select
from sqlalchemy.dialects import oracle

from app.db.tipos import esta_ativo
from app.models import Usuario
from app.repositories import usuario_repository as repo


def _sql(consulta) -> str:
    return str(
        consulta.compile(
            dialect=oracle.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_busca_usa_upper_e_like_como_o_contrato_descreve():
    """UPPER(nome_completo) LIKE '%TERMO%' casa com o índice funcional
    IDX_USUARIOS_NC do DDL."""
    sql = _sql(repo._filtro_busca(select(Usuario.id_usuario), "santos"))
    assert "upper(usuarios.nome_completo) LIKE '%SANTOS%'" in sql


def test_curingas_digitados_pelo_usuario_sao_escapados():
    """Sem escape, buscar por "%" listaria a base inteira."""
    assert repo._escapar_like("100%") == "100\\%"
    assert repo._escapar_like("a_b") == "a\\_b"
    assert repo._escapar_like("c:\\x") == "c:\\\\x"
    assert "ESCAPE" in _sql(repo._filtro_busca(select(Usuario.id_usuario), "50%"))


def test_busca_vazia_nao_acrescenta_filtro():
    for termo in (None, "", "   "):
        assert "LIKE" not in _sql(repo._filtro_busca(select(Usuario.id_usuario), termo))


def test_listagem_filtra_apenas_ativos():
    sql = _sql(select(Usuario.id_usuario).where(esta_ativo(Usuario.ativo)))
    assert "ativo = 1" in sql


def test_ordenacao_tem_desempate_por_id():
    """Sem desempate, duas linhas de mesmo nome poderiam trocar de posição entre
    páginas, fazendo a paginação repetir uma e pular outra."""
    from sqlalchemy import func

    sql = _sql(
        select(Usuario.id_usuario).order_by(
            func.upper(Usuario.nome_completo), Usuario.id_usuario
        )
    )
    assert "ORDER BY upper(usuarios.nome_completo), usuarios.id_usuario" in sql


def test_busca_de_destinatarios_junta_endereco_e_filtra_usuario_ativo():
    """Quem recebe o alerta é definido pelo estado do endereço do usuário; quem
    foi desativado não recebe mais."""
    from sqlalchemy import select as _select

    from app.models import Endereco
    from app.db.tipos import esta_ativo as _ativo

    sql = _sql(
        _select(Usuario.nome_completo, Usuario.email)
        .join(Endereco, Usuario.enderecos_id_endereco == Endereco.id_endereco)
        .where(_ativo(Usuario.ativo), Endereco.estado_uf == "SP")
    )
    assert "JOIN enderecos" in sql
    assert "usuarios.ativo = 1" in sql
    assert "enderecos.estado_uf = 'SP'" in sql
