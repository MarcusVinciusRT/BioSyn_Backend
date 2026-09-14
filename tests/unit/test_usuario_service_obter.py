"""usuario_service.obter sem banco: mapeamento e regra de desativado."""

import pytest

from app.core.errors import AppError, CodigoErro
from app.models import Endereco
from app.repositories import usuario_repository
from app.services import usuario_service
from tests.unit.test_auth_service import montar_usuario


def _com_endereco(*, ativo: bool = True):
    usuario = montar_usuario(ativo=ativo)
    usuario.endereco = Endereco(
        id_endereco=1, tipo_logradouro="Rua", logradouro="das Laranjeiras",
        numero="180", cep="22240003", estado_uf="RJ", cidade="Rio de Janeiro",
        complemento=None, ativo=True,
    )
    return usuario


def test_campos_do_formulario_saem_com_os_nomes_do_put(monkeypatch):
    monkeypatch.setattr(usuario_repository, "buscar_detalhe_por_id", lambda db, i: _com_endereco())
    detalhe = usuario_service.obter(None, 42)

    assert detalhe.cargo_id == 3            # coluna cargos_id_cargo
    assert detalhe.organizacao_id == 1      # coluna organizacoes_id_organizacao
    assert detalhe.cargo.nome_cargo == "Analista Epidemiológico"
    assert detalhe.organizacao.nome == "Ministério da Saúde"
    assert detalhe.endereco.cep == "22240003"
    assert detalhe.endereco.complemento is None


def test_senha_nao_faz_parte_do_detalhe(monkeypatch):
    monkeypatch.setattr(usuario_repository, "buscar_detalhe_por_id", lambda db, i: _com_endereco())
    assert "senha" not in usuario_service.obter(None, 42).model_dump()


@pytest.mark.parametrize("encontrado", [None, "desativado"])
def test_inexistente_ou_desativado_e_404(monkeypatch, encontrado):
    usuario = None if encontrado is None else _com_endereco(ativo=False)
    monkeypatch.setattr(usuario_repository, "buscar_detalhe_por_id", lambda db, i: usuario)
    with pytest.raises(AppError) as erro:
        usuario_service.obter(None, 42)
    assert erro.value.codigo == CodigoErro.USUARIO_NAO_ENCONTRADO
    assert erro.value.http_status == 404
