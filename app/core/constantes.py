"""Constantes de dominio compartilhadas entre schemas e services."""

from __future__ import annotations

# Unidades federativas validas. Usada no cadastro de endereco (secao 7) e no
# disparo de alertas por UF (secao 5) -- o estado do endereco e o que define
# quem recebe o alerta.
UFS: frozenset[str] = frozenset(
    {
        "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
        "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
        "SE", "SP", "TO",
    }
)

# Espelha a constraint CK_TIPO_LOGRADOURO do DDL. Validar aqui devolve 422 com
# o campo apontado, em vez de deixar o banco estourar ORA-02290.
TIPOS_LOGRADOURO: tuple[str, ...] = (
    "Alameda", "Avenida", "Beco", "Condomínio", "Estrada",
    "Loteamento", "Praça", "Rodovia", "Rua", "Travessa",
)


# Sigla -> nome como a coluna UF do lakehouse guarda (maiusculas, sem acento).
# O contrato exemplifica o filtro do relatorio como "SP", mas GOLD.INTERNACOES
# grava "SAO PAULO"; sem esta traducao o filtro nao casaria com nada e o
# relatorio devolveria zero em silencio.
UF_PARA_NOME_LAKEHOUSE: dict[str, str] = {
    "AC": "ACRE",
    "AL": "ALAGOAS",
    "AM": "AMAZONAS",
    "AP": "AMAPA",
    "BA": "BAHIA",
    "CE": "CEARA",
    "DF": "DISTRITO FEDERAL",
    "ES": "ESPIRITO SANTO",
    "GO": "GOIAS",
    "MA": "MARANHAO",
    "MG": "MINAS GERAIS",
    "MS": "MATO GROSSO DO SUL",
    "MT": "MATO GROSSO",
    "PA": "PARA",
    "PB": "PARAIBA",
    "PE": "PERNAMBUCO",
    "PI": "PIAUI",
    "PR": "PARANA",
    "RJ": "RIO DE JANEIRO",
    "RN": "RIO GRANDE DO NORTE",
    "RO": "RONDONIA",
    "RR": "RORAIMA",
    "RS": "RIO GRANDE DO SUL",
    "SC": "SANTA CATARINA",
    "SE": "SERGIPE",
    "SP": "SAO PAULO",
    "TO": "TOCANTINS",
}
