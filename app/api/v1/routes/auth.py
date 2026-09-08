"""Secao 3 do contrato: Autenticacao.

Sem biometria, sem SSO Gov, sem autocadastro e sem recuperacao de senha: todo
usuario e criado por um administrador. Nao existe rota de logout -- o front
descarta o token e redireciona para o login.
"""

import logging

from fastapi import APIRouter, Request, status

from app.core.config import get_settings
from app.core.deps import SessaoDep, UsuarioDep
from app.core.errors import AppError, CodigoErro
from app.core.rate_limit import LimitadorDeTentativas
from app.schemas.auth import LoginRequest, LoginResponse, UsuarioAutenticado
from app.services import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["autenticacao"])

_settings = get_settings()
_limitador = LimitadorDeTentativas(
    limite=_settings.login_tentativas_max,
    janela_segundos=_settings.login_janela_segundos,
)


def _origem(request: Request) -> str:
    """IP de origem da tentativa.

    Atras de proxy, o IP real so chega se o servidor rodar com --proxy-headers;
    sem isso, todas as tentativas contam como vindas do proxy e o limite fica
    global. Documentado no README.
    """
    return request.client.host if request.client else "desconhecido"


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticar usuário",
)
def login(corpo: LoginRequest, db: SessaoDep, request: Request) -> LoginResponse:
    """Acesso: público."""
    chave = _origem(request)

    if _limitador.bloqueado(chave):
        espera = _limitador.segundos_para_liberar(chave)
        logger.warning("login bloqueado por excesso de tentativas origem=%s", chave)
        raise AppError(
            CodigoErro.MUITAS_TENTATIVAS,
            f"Tentativas de login em excesso. Tente novamente em {espera} segundos.",
        )

    try:
        resposta = auth_service.autenticar(db, corpo.email, corpo.senha)
    except AppError:
        # So a falha conta: quem acerta a senha nunca e barrado.
        _limitador.registrar_falha(chave)
        raise

    _limitador.esquecer(chave)
    return resposta


@router.get(
    "/me",
    response_model=UsuarioAutenticado,
    summary="Dados do usuário autenticado",
)
def me(usuario: UsuarioDep) -> UsuarioAutenticado:
    """Acesso: qualquer usuario autenticado.

    Devolve o mesmo objeto "usuario" do login, para o front reidratar a sessao
    depois de um refresh de pagina sem guardar dados fora do token.
    """
    return auth_service.montar_usuario_autenticado(usuario)
