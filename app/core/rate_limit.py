"""Limite de tentativas de login.

Sem isso, /auth/login aceita quantas tentativas de senha o atacante quiser, na
velocidade que a rede permitir -- e o bcrypt sozinho so encarece cada tentativa,
nao limita o total.

Contamos apenas as tentativas QUE FALHARAM. Quem acerta a senha nunca e barrado,
e quem erra muito e desacelerado.

Limitacao conhecida: o contador vive na memoria do processo. Com varias replicas
atras de um balanceador, cada uma tem o seu, e o limite efetivo se multiplica.
Para valer no conjunto, trocar por um contador compartilhado (Redis) -- ficou
fora do escopo desta versao.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class LimitadorDeTentativas:
    """Janela deslizante por chave, em memoria."""

    def __init__(self, limite: int, janela_segundos: int) -> None:
        self._limite = limite
        self._janela = janela_segundos
        self._tentativas: dict[str, deque[float]] = {}
        # As rotas rodam em threadpool: sem o lock, duas requisicoes simultaneas
        # corromperiam o deque.
        self._trava = threading.Lock()

    def _limpar(self, chave: str, agora: float) -> deque[float]:
        marcas = self._tentativas.setdefault(chave, deque())
        limite_inferior = agora - self._janela
        while marcas and marcas[0] < limite_inferior:
            marcas.popleft()
        return marcas

    def bloqueado(self, chave: str) -> bool:
        agora = time.monotonic()
        with self._trava:
            return len(self._limpar(chave, agora)) >= self._limite

    def registrar_falha(self, chave: str) -> None:
        agora = time.monotonic()
        with self._trava:
            self._limpar(chave, agora).append(agora)
            self._podar(agora)

    def esquecer(self, chave: str) -> None:
        """Chamado no login bem-sucedido: acertar a senha zera o contador."""
        with self._trava:
            self._tentativas.pop(chave, None)

    def segundos_para_liberar(self, chave: str) -> int:
        agora = time.monotonic()
        with self._trava:
            marcas = self._limpar(chave, agora)
            if len(marcas) < self._limite:
                return 0
            return max(1, int(self._janela - (agora - marcas[0])) + 1)

    def _podar(self, agora: float) -> None:
        """Remove chaves ja vencidas, para o dicionario nao crescer sem limite."""
        if len(self._tentativas) < 1000:
            return
        limite_inferior = agora - self._janela
        vencidas = [
            chave
            for chave, marcas in self._tentativas.items()
            if not marcas or marcas[-1] < limite_inferior
        ]
        for chave in vencidas:
            del self._tentativas[chave]
