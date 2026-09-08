"""Secao 6 do contrato: Relatorios.

Gerados sob demanda e nao persistidos. O fluxo e: selecionar, gerar, exportar.
"""

from fastapi import APIRouter, Response

from app.core.deps import SessaoDep, UsuarioDep
from app.exporters import EXTENSAO, TIPO_MIME, gerar_csv, gerar_xlsx
from app.schemas.relatorio import (
    CatalogoMetricas,
    RelatorioRequest,
    RelatorioResponse,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


@router.get(
    "/metricas", response_model=CatalogoMetricas, summary="Listar métricas disponíveis"
)
def listar_metricas(db: SessaoDep, _: UsuarioDep) -> CatalogoMetricas:
    """Acesso: qualquer usuário autenticado."""
    return relatorio_service.listar_metricas(db)


# response_model=None: em csv e xlsx o corpo e o arquivo binario, nao JSON.
@router.post("", response_model=None, summary="Gerar relatório")
def gerar_relatorio(
    corpo: RelatorioRequest, db: SessaoDep, _: UsuarioDep
) -> RelatorioResponse | Response:
    """Acesso: qualquer usuário autenticado.

    O campo `formato` controla a saída: `json` para o front renderizar na tela,
    `csv` ou `xlsx` para download direto do arquivo já montado pela API.
    """
    relatorio = relatorio_service.gerar(db, corpo)

    if corpo.formato == "json":
        return relatorio

    conteudo = gerar_csv(relatorio) if corpo.formato == "csv" else gerar_xlsx(relatorio)
    arquivo = relatorio_service.nome_do_arquivo(
        relatorio.gerado_em, EXTENSAO[corpo.formato]
    )
    return Response(
        content=conteudo,
        media_type=TIPO_MIME[corpo.formato],
        headers={"Content-Disposition": f'attachment; filename="{arquivo}"'},
    )
