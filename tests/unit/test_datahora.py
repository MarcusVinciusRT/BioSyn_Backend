"""Fuso horario: o driver descarta o offset das colunas TIMESTAMP WITH TIME ZONE."""

from datetime import UTC, datetime, timedelta, timezone

from app.db.tipos import TimestampComFuso
from app.schemas.usuario import UsuarioCriado

TIPO = TimestampComFuso()


def test_valor_naive_do_driver_e_rotulado_como_utc():
    """O python-oracledb thin devolve TSTZ sem tzinfo; as colunas do DDL sao
    preenchidas por SYSTIMESTAMP com DBTIMEZONE=+00:00, entao o valor e UTC."""
    lido = TIPO.process_result_value(datetime(2026, 8, 22, 18, 2, 44), None)
    assert lido.tzinfo is not None
    assert lido == datetime(2026, 8, 22, 18, 2, 44, tzinfo=UTC)


def test_valor_aware_e_convertido_para_utc():
    origem = datetime(2026, 8, 22, 15, 2, 44, tzinfo=timezone(timedelta(hours=-3)))
    assert TIPO.process_result_value(origem, None) == datetime(
        2026, 8, 22, 18, 2, 44, tzinfo=UTC
    )


def test_nulo_continua_nulo():
    assert TIPO.process_result_value(None, None) is None
    assert TIPO.process_bind_param(None, None) is None


def test_resposta_sai_em_iso_8601_com_fuso_como_o_contrato_exige():
    """Regressao: a API devolvia "2026-09-03T21:34:36.543143", sem fuso e em
    UTC, e o front renderizaria 3 horas adiantado."""
    resposta = UsuarioCriado(
        id_usuario=43,
        nome_completo="Carlos Oliveira",
        email="carlos.oliveira@saude.gov.br",
        criado_em=datetime(2026, 8, 22, 18, 2, 44, 543143, tzinfo=UTC),
    )
    assert resposta.model_dump()["criado_em"] == "2026-08-22T15:02:44-03:00"


def test_microssegundos_sao_descartados():
    resposta = UsuarioCriado(
        id_usuario=1, nome_completo="X Y", email="x@y.com",
        criado_em=datetime(2026, 1, 1, 12, 0, 0, 999999, tzinfo=UTC),
    )
    assert "." not in resposta.model_dump()["criado_em"]
