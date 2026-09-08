"""Ambiente dos testes.

Sem .env (tipicamente em CI), preenche o minimo para os testes unitarios
importarem a aplicacao. Com .env presente, nao mexe em nada: variavel de
ambiente tem precedencia sobre o arquivo, e sobrescrever aqui quebraria os
testes marcados com `banco`, que precisam das credenciais reais.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if not (RAIZ / ".env").exists():
    os.environ.setdefault("DB_USER", "TESTE")
    os.environ.setdefault("DB_PASSWORD", "teste")
    os.environ.setdefault("DB_DSN", "teste_dsn")
    os.environ.setdefault("JWT_SECRET", "segredo-de-teste-nao-usar-em-producao")
