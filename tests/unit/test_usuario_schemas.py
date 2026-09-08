"""Regras de validacao da secao 7, na borda da API."""

import pytest
from pydantic import ValidationError

from app.schemas.usuario import EnderecoEntrada, UsuarioAtualizar, UsuarioCriar

ENDERECO_OK = {
    "tipo_logradouro": "Rua",
    "logradouro": "das Laranjeiras",
    "numero": 180,
    "cep": "22240003",
    "estado_uf": "RJ",
    "cidade": "Rio de Janeiro",
    "complemento": "Bloco B, sala 12",
}
USUARIO_OK = {
    "cpf": "12345678901",
    "email": "carlos.oliveira@saude.gov.br",
    "telefone": "21998877665",
    "senha": "senhaProvisoria123",
    "nome": "Carlos",
    "sobrenome": "Oliveira",
    "is_admin": False,
    "cargo_id": 5,
    "organizacao_id": 2,
    "endereco": ENDERECO_OK,
}


def criar(**mudancas):
    return UsuarioCriar(**{**USUARIO_OK, **mudancas})


def endereco(**mudancas):
    return EnderecoEntrada(**{**ENDERECO_OK, **mudancas})


# --- Normalizacao ----------------------------------------------------------

def test_cpf_aceita_mascara_e_guarda_so_digitos():
    assert criar(cpf="123.456.789-01").cpf == "12345678901"


def test_telefone_aceita_formatacao_e_guarda_so_digitos():
    assert criar(telefone="(21) 99887-7665").telefone == "21998877665"


def test_email_e_normalizado_para_minusculas():
    assert criar(email="  Carlos@Saude.GOV.br ").email == "carlos@saude.gov.br"


def test_uf_minuscula_e_promovida():
    assert endereco(estado_uf="rj").estado_uf == "RJ"


def test_cep_aceita_hifen():
    assert endereco(cep="22240-003").cep == "22240003"


def test_numero_aceita_inteiro_porque_a_coluna_e_texto():
    """O exemplo do contrato manda 180 como número, mas a coluna é VARCHAR2(10)
    e há números que não são inteiros ("180-A", "s/n")."""
    assert endereco(numero=180).numero == "180"
    assert endereco(numero="180-A").numero == "180-A"


def test_espacos_extras_no_nome_sao_colapsados():
    assert criar(nome="  Carlos   Eduardo  ").nome == "Carlos Eduardo"


# --- Recusas ---------------------------------------------------------------

@pytest.mark.parametrize("cpf", ["123", "1234567890123", "abcdefghijk", ""])
def test_cpf_fora_de_11_digitos_e_recusado(cpf):
    with pytest.raises(ValidationError):
        criar(cpf=cpf)


def test_cpf_sintetico_e_aceito():
    """Nao conferimos digito verificador: a massa de teste do projeto usa CPFs
    sinteticos como 12345678901."""
    assert criar(cpf="12345678901").cpf == "12345678901"


@pytest.mark.parametrize("senha", ["1234567", "curta", ""])
def test_senha_abaixo_de_8_caracteres_e_recusada(senha):
    with pytest.raises(ValidationError):
        criar(senha=senha)


def test_senha_acima_do_limite_do_bcrypt_e_recusada():
    with pytest.raises(ValidationError):
        criar(senha="a" * 73)


@pytest.mark.parametrize("uf", ["ZZ", "XX", "R", "RIO", ""])
def test_uf_invalida_e_recusada(uf):
    """A UF define quem recebe os alertas: aceitar lixo aqui significa
    disparo silencioso para ninguém."""
    with pytest.raises(ValidationError):
        endereco(estado_uf=uf)


def test_tipo_de_logradouro_fora_da_constraint_e_recusado():
    """Espelha CK_TIPO_LOGRADOURO: melhor 422 com o campo apontado que ORA-02290."""
    with pytest.raises(ValidationError):
        endereco(tipo_logradouro="Viela")


@pytest.mark.parametrize("telefone", ["123", "9999", "1" * 16])
def test_telefone_fora_da_faixa_e_recusado(telefone):
    with pytest.raises(ValidationError):
        criar(telefone=telefone)


def test_nome_com_mais_de_60_caracteres_e_recusado():
    with pytest.raises(ValidationError):
        criar(nome="a" * 61)


# --- Edicao ----------------------------------------------------------------

def test_edicao_aceita_corpo_sem_senha():
    dados = {k: v for k, v in USUARIO_OK.items() if k not in ("senha", "cpf")}
    assert UsuarioAtualizar(**dados).senha is None


def test_edicao_ainda_valida_a_senha_quando_enviada():
    dados = {k: v for k, v in USUARIO_OK.items() if k != "cpf"}
    with pytest.raises(ValidationError):
        UsuarioAtualizar(**{**dados, "senha": "curta"})


def test_nome_completo_nao_e_aceito_do_cliente():
    """A API monta a partir de nome + sobrenome; aceitar do cliente permitiria
    divergencia com a coluna usada na busca."""
    u = criar(nome_completo="Nome Falsificado")
    assert not hasattr(u, "nome_completo")
