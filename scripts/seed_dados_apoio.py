#!/usr/bin/env python
"""Popula os dados de apoio do BioSyn: cargos, organizacoes, abas e metricas.

Idempotente: roda quantas vezes quiser, so insere o que ainda nao existe.
Optei por Python em vez de .sql porque roda com o proprio venv do projeto, sem
exigir SQL*Plus, e porque a idempotencia fica legivel.

Uso:
    python scripts/seed_dados_apoio.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import encerrar_banco, iniciar_banco, sessao  # noqa: E402
from app.models import (  # noqa: E402
    Cargo,
    DashboardConfig,
    Endereco,
    Metrica,
    Organizacao,
)

CARGOS = [
    "Administrador do Sistema",
    "Analista Epidemiológico",
    "Agente Comunitário de Saúde",
    "Coordenador de Vigilância",
    "Enfermeiro",
    "Gestor Estadual",
    "Gestor Municipal",
    "Médico",
    "Técnico Hospitalar",
    "Técnico em Enfermagem",
]

# (nome da organizacao, cidade, uf) -- cada organizacao exige um endereco (FK).
ORGANIZACOES = [
    ("Ministério da Saúde", "Brasília", "DF"),
    ("Fundação Oswaldo Cruz", "Rio de Janeiro", "RJ"),
    ("Hospital das Clínicas - RJ", "Rio de Janeiro", "RJ"),
    ("Secretaria de Saúde - SP", "São Paulo", "SP"),
    ("Secretaria de Saúde - MG", "Belo Horizonte", "MG"),
    ("Secretaria de Saúde - BA", "Salvador", "BA"),
]


# (nome da aba, ordem de exibicao). A URL de embed real vem do Power BI e e
# configurada depois -- aqui entra um marcador obvio para nao passar por real.
ABAS_DASHBOARD = [
    ("Geral", 1),
    ("População", 2),
    ("Hospitais", 3),
]

# (nome, nome_view, coluna_filtro, descricao, unidade)
# nome_view e a chave usada tanto no modo "views" quanto no fallback sobre
# GOLD.INTERNACOES -- ver AGREGACOES_FALLBACK em app/integrations/lakehouse.py.
METRICAS = [
    ("Internações totais", "VW_INTERNACOES_TOTAL", "ESTADO",
     "Quantidade de internações no período", "numero"),
    ("Valor total das internações", "VW_INTERNACOES_VALOR_TOTAL", "ESTADO",
     "Soma do valor total das internações, em reais", "numero"),
    ("Valor médio por internação", "VW_INTERNACOES_VALOR_MEDIO", "ESTADO",
     "Valor médio de cada internação, em reais", "numero"),
    ("Permanência média", "VW_INTERNACOES_PERMANENCIA_MEDIA", "ESTADO",
     "Média de dias de permanência hospitalar", "numero"),
    ("Idade média dos internados", "VW_INTERNACOES_IDADE_MEDIA", "ESTADO",
     "Idade média dos pacientes internados, em anos", "numero"),
    ("Taxa de alta complexidade", "VW_INTERNACOES_TAXA_ALTA_COMPLEXIDADE", "ESTADO",
     "Percentual de internações de alta complexidade", "percentual"),
]

URL_EMBED_PENDENTE = "https://app.powerbi.com/reportEmbed?reportId=CONFIGURAR"


def _endereco_da_cidade(db: Session, cidade: str, uf: str) -> Endereco:
    endereco = db.execute(
        select(Endereco).where(Endereco.cidade == cidade, Endereco.estado_uf == uf)
    ).scalars().first()
    if endereco is not None:
        return endereco
    endereco = Endereco(
        tipo_logradouro="Avenida",
        logradouro="Não informado",
        numero="0",
        cep="00000000",
        estado_uf=uf,
        cidade=cidade,
        complemento=None,
        ativo=True,
    )
    db.add(endereco)
    db.flush()
    return endereco


def main() -> None:
    iniciar_banco()
    try:
        with sessao() as db:
            criados = reaproveitados = 0

            print("Cargos:")
            for nome in CARGOS:
                existente = db.execute(
                    select(Cargo).where(Cargo.nome_cargo == nome)
                ).scalar_one_or_none()
                if existente is not None:
                    reaproveitados += 1
                    continue
                db.add(Cargo(nome_cargo=nome, ativo=True))
                criados += 1
                print(f"  + {nome}")

            print("\nOrganizações:")
            for nome, cidade, uf in ORGANIZACOES:
                existente = db.execute(
                    select(Organizacao).where(Organizacao.nome_organizacao == nome)
                ).scalar_one_or_none()
                if existente is not None:
                    reaproveitados += 1
                    continue
                endereco = _endereco_da_cidade(db, cidade, uf)
                db.add(
                    Organizacao(
                        nome_organizacao=nome,
                        enderecos_id_endereco=endereco.id_endereco,
                        ativo=True,
                    )
                )
                criados += 1
                print(f"  + {nome} ({cidade}/{uf})")

            print("\nAbas do dashboard:")
            for nome, ordem in ABAS_DASHBOARD:
                existente = db.execute(
                    select(DashboardConfig).where(DashboardConfig.nome_aba == nome)
                ).scalar_one_or_none()
                if existente is not None:
                    reaproveitados += 1
                    continue
                db.add(
                    DashboardConfig(
                        nome_aba=nome,
                        url_embbed=URL_EMBED_PENDENTE,
                        ordem=ordem,
                        ativo=True,
                    )
                )
                criados += 1
                print(f"  + {nome} (ordem {ordem})")

            print("\nMétricas:")
            for nome, view, coluna, descricao, unidade in METRICAS:
                existente = db.execute(
                    select(Metrica).where(Metrica.nome_metrica == nome)
                ).scalar_one_or_none()
                if existente is not None:
                    reaproveitados += 1
                    continue
                db.add(
                    Metrica(
                        nome_metrica=nome,
                        nome_view=view,
                        coluna_filtro=coluna,
                        descricao=descricao,
                        unidade=unidade,
                        ativo=True,
                    )
                )
                criados += 1
                print(f"  + {nome} ({unidade})")

            print(f"\n{criados} criados, {reaproveitados} já existiam.")
            print(
                "\nAtenção: as abas ficaram com uma URL de embed marcadora. "
                "Substitua pelas URLs reais do Power BI antes de usar."
            )
    finally:
        encerrar_banco()


if __name__ == "__main__":
    main()
