"""Select AI de verdade, com o profile configurado.

Marcado com `banco`. Depende do Oracle e do provedor de IA externo, e cada
chamada leva dezenas de segundos -- existe para pegar profile trocado ou
quebrado, como o APP_PROFILE, que passou a travar sem responder.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import criar_sessao, encerrar_banco, iniciar_banco
from app.integrations import select_ai

pytestmark = pytest.mark.banco


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


def test_profile_configurado_responde_em_linguagem_natural(db):
    resposta = select_ai.narrar(db, "Quantas internações existem no total?")
    assert resposta.strip(), f"profile {get_settings().ai_profile_name} devolveu vazio"
