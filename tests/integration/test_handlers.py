"""Verifica que TODA falha da API sai no envelope unico da secao 2.3."""

import pytest
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import AppError, CodigoErro
from app.core.handlers import registrar_handlers
from app.core.logging import RequestIdMiddleware


class Endereco(BaseModel):
    cep: str = Field(min_length=8, max_length=8)


class CorpoTeste(BaseModel):
    cpf: str = Field(min_length=11, max_length=11)
    idade: int
    endereco: Endereco


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    """App sintetico: exercita os handlers sem subir banco nenhum."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    registrar_handlers(app)

    @app.post("/eco")
    def eco(corpo: CorpoTeste) -> dict[str, str]:
        return {"ok": corpo.cpf}

    @app.get("/negocio")
    def negocio() -> None:
        raise AppError(CodigoErro.CPF_DUPLICADO)

    @app.get("/negocio-com-campos")
    def negocio_com_campos() -> None:
        raise AppError(
            CodigoErro.VALIDACAO,
            campos=[{"campo": "cpf", "detalhe": "Deve conter 11 dígitos numéricos."}],
        )

    @app.get("/gateway")
    def gateway() -> None:
        raise AppError(CodigoErro.FALHA_ENVIO_ALERTA)

    @app.get("/http-401")
    def http_401() -> None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente.")

    @app.get("/query")
    def query(pagina: int = Query(default=1, ge=1)) -> dict[str, int]:
        return {"pagina": pagina}

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("segredo interno que nao pode vazar")

    return TestClient(app, raise_server_exceptions=False)


def test_erro_de_negocio_usa_o_envelope_e_o_status_do_catalogo(cliente):
    r = cliente.get("/negocio")
    assert r.status_code == 409
    assert r.json() == {
        "erro": {
            "codigo": "CPF_DUPLICADO",
            "mensagem": "Já existe usuário com esse CPF.",
        }
    }


def test_erro_de_gateway_externo_e_502(cliente):
    r = cliente.get("/gateway")
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "FALHA_ENVIO_ALERTA"


def test_erro_de_negocio_pode_carregar_campos(cliente):
    r = cliente.get("/negocio-com-campos")
    assert r.json()["erro"]["campos"] == [
        {"campo": "cpf", "detalhe": "Deve conter 11 dígitos numéricos."}
    ]


def test_envelope_sem_campos_nao_traz_a_chave_campos(cliente):
    assert "campos" not in cliente.get("/negocio").json()["erro"]


def test_validacao_de_corpo_vira_422_com_lista_de_campos(cliente):
    r = cliente.post("/eco", json={"cpf": "123", "endereco": {"cep": "222"}})
    assert r.status_code == 422
    corpo = r.json()["erro"]
    assert corpo["codigo"] == "VALIDACAO"
    assert corpo["mensagem"] == "Dados inválidos."

    por_campo = {c["campo"]: c["detalhe"] for c in corpo["campos"]}
    # Campo aninhado sai com caminho pontuado, sem o prefixo "body".
    assert por_campo["endereco.cep"] == "Mais curto que o mínimo permitido."
    assert por_campo["cpf"] == "Mais curto que o mínimo permitido."
    assert por_campo["idade"] == "Campo obrigatório ausente."


def test_mensagens_de_validacao_estao_em_portugues(cliente):
    r = cliente.post("/eco", json={"cpf": "12345678901", "idade": "abc",
                                   "endereco": {"cep": "22240003"}})
    detalhes = [c["detalhe"] for c in r.json()["erro"]["campos"]]
    assert detalhes == ["Deve ser um número inteiro."]


def test_validacao_de_query_string_tambem_entra_no_envelope(cliente):
    r = cliente.get("/query", params={"pagina": 0})
    assert r.status_code == 422
    assert r.json()["erro"]["campos"] == [
        {"campo": "pagina", "detalhe": "Abaixo do mínimo permitido."}
    ]


def test_json_malformado_e_400_e_nao_422(cliente):
    r = cliente.post(
        "/eco", content=b"{isso nao e json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400
    assert r.json()["erro"]["codigo"] == "JSON_INVALIDO"


def test_http_exception_401_entra_no_envelope(cliente):
    r = cliente.get("/http-401")
    assert r.status_code == 401
    assert r.json() == {
        "erro": {"codigo": "NAO_AUTENTICADO", "mensagem": "Token ausente."}
    }


def test_rota_inexistente_tambem_sai_no_envelope(cliente):
    r = cliente.get("/rota-que-nao-existe")
    assert r.status_code == 404
    assert r.json()["erro"]["codigo"] == "NAO_ENCONTRADO"


def test_excecao_nao_tratada_vira_500_generico_sem_vazar_detalhe(cliente):
    r = cliente.get("/explode")
    assert r.status_code == 500
    assert r.json() == {
        "erro": {
            "codigo": "ERRO_INTERNO",
            "mensagem": "Erro interno. Tente novamente em instantes.",
        }
    }
    assert "segredo interno" not in r.text


def test_toda_resposta_carrega_o_request_id(cliente):
    assert cliente.get("/negocio").headers["X-Request-Id"]


def test_request_id_enviado_pelo_front_e_preservado(cliente):
    r = cliente.get("/negocio", headers={"X-Request-Id": "rastro-do-front"})
    assert r.headers["X-Request-Id"] == "rastro-do-front"


def test_404_nao_vaza_a_frase_padrao_em_ingles_do_starlette(cliente):
    """Regressao: o handler devolvia {"mensagem": "Not Found"}."""
    corpo = cliente.get("/rota-que-nao-existe").json()["erro"]
    assert corpo["mensagem"] == "Recurso não encontrado."


def test_405_nao_e_classificado_como_erro_interno(cliente):
    """Regressao: metodo errado caia em ERRO_INTERNO, o que e enganoso."""
    r = cliente.get("/eco")  # /eco so aceita POST
    assert r.status_code == 405
    assert r.json() == {
        "erro": {
            "codigo": "METODO_NAO_PERMITIDO",
            "mensagem": "Método HTTP não permitido para esta rota.",
        }
    }


def test_detail_escrito_por_nos_continua_sendo_respeitado(cliente):
    """A correcao acima nao pode engolir mensagem nossa."""
    assert cliente.get("/http-401").json()["erro"]["mensagem"] == "Token ausente."


def test_email_invalido_responde_em_portugues():
    """Regressao: o EmailStr do pydantic responde em ingles e o mapa generico
    engolia a mensagem, devolvendo apenas "Valor inválido."."""
    from pydantic import EmailStr

    app = FastAPI()
    registrar_handlers(app)

    class Corpo(BaseModel):
        email: EmailStr

    @app.post("/login-falso")
    def login_falso(corpo: Corpo) -> dict[str, str]:
        return {"ok": corpo.email}

    cliente_local = TestClient(app, raise_server_exceptions=False)
    r = cliente_local.post("/login-falso", json={"email": "nao-e-email"})
    assert r.json()["erro"]["campos"] == [
        {"campo": "email", "detalhe": "E-mail em formato inválido."}
    ]


def test_mensagem_de_validador_proprio_chega_intacta():
    """Nossos validadores escrevem em portugues; o handler nao pode substituir."""
    from pydantic import field_validator

    app = FastAPI()
    registrar_handlers(app)

    class Corpo(BaseModel):
        cpf: str

        @field_validator("cpf")
        @classmethod
        def _valida(cls, v: str) -> str:
            raise ValueError("Deve conter 11 dígitos numéricos.")

    @app.post("/cadastro-falso")
    def cadastro_falso(corpo: Corpo) -> dict[str, str]:
        return {"ok": corpo.cpf}

    cliente_local = TestClient(app, raise_server_exceptions=False)
    r = cliente_local.post("/cadastro-falso", json={"cpf": "123"})
    assert r.json()["erro"]["campos"] == [
        {"campo": "cpf", "detalhe": "Deve conter 11 dígitos numéricos."}
    ]
