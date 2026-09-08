"""Health check. Rota publica, fora do fluxo de autenticacao."""

from fastapi import APIRouter, Response, status

from app.db.session import banco_saudavel

router = APIRouter(tags=["infra"])


@router.get("/health")
def health(resposta: Response) -> dict[str, str]:
    ok = banco_saudavel()
    if not ok:
        resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ok else "degradado",
        "banco": "ok" if ok else "indisponivel",
    }
