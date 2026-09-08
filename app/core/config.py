"""Configuracao da aplicacao. Tudo vem de variavel de ambiente."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


# app/core/config.py -> app/core -> app -> raiz
RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicacao ---
    ambiente: Literal["dev", "homolog", "prod"] = "dev"
    log_level: str = "INFO"
    api_prefixo: str = "/api/v1"
    # Fuso usado para serializar datas nas respostas. O contrato exemplifica
    # com -03:00; internamente tudo trafega em UTC.
    fuso_horario: str = "America/Sao_Paulo"

    # --- Banco: OLTP + lakehouse GOLD + Select AI, tudo no mesmo ADB ---
    db_user: str
    db_password: str
    db_dsn: str
    # Preenchidos apenas no modo mTLS (wallet). Em TLS puro, deixe vazios.
    wallet_dir: str | None = None
    wallet_password: str | None = None
    # Alternativa a WALLET_DIR para hospedagem sem disco persistente: o .zip do
    # wallet em base64. Tem precedencia sobre WALLET_DIR. Ver app/db/wallet.py.
    wallet_base64: str | None = None
    db_pool_min: int = 1
    db_pool_max: int = 8

    # --- JWT ---
    jwt_secret: str
    jwt_algoritmo: str = "HS256"
    # 1800s = 30min. E o valor devolvido no campo "expira_em" do login.
    jwt_expira_segundos: int = 1800

    # --- Limite de tentativas de login ---
    login_tentativas_max: int = 10
    login_janela_segundos: int = 300

    # --- Select AI ---
    ai_profile_name: str = "APP_PROFILE"
    ai_timeout_segundos: int = 60

    # --- Canal de alertas (secao 5) ---
    # "console" -> apenas registra no log, nada e enviado
    # "smtp"    -> envia e-mail de verdade por qualquer provedor SMTP
    alerta_canal: Literal["console", "smtp"] = "console"
    # Destinatarios por mensagem. Servidores de e-mail limitam quantos endereços
    # aceitam de uma vez; acima disso o lote inteiro e recusado.
    alerta_tamanho_lote: int = 50

    smtp_host: str | None = None
    smtp_porta: int = 587
    smtp_usuario: str | None = None
    smtp_senha: str | None = None
    smtp_remetente: str | None = None
    smtp_remetente_nome: str = "BioSyn"
    smtp_seguranca: Literal["starttls", "ssl", "nenhum"] = "starttls"

    # --- Relatorios ---
    # "views"    -> consulta as views nomeadas em METRICAS.nome_view
    # "fallback" -> agrega direto de GOLD.INTERNACOES enquanto as views nao existem
    lakehouse_modo: Literal["views", "fallback"] = "fallback"
    lakehouse_tabela_fallback: str = "GOLD.INTERNACOES"

    # --- CORS ---
    # NoDecode: sem ele o pydantic-settings tentaria json.loads antes do validador.
    cors_origens: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origens", mode="before")
    @classmethod
    def _split_origens(cls, v: object) -> object:
        """Aceita CORS_ORIGENS como lista JSON ou como CSV simples."""
        if not isinstance(v, str):
            return v
        texto = v.strip()
        if texto.startswith("["):
            return json.loads(texto)
        return [origem.strip() for origem in texto.split(",") if origem.strip()]

    @field_validator("smtp_senha", mode="before")
    @classmethod
    def _limpar_senha_smtp(cls, v: object) -> object:
        """Remove os espacos da senha de app do Gmail.

        O Google exibe a senha no formato "abcd efgh ijkl mnop", e colar assim e
        o caminho natural. Os espacos sao so formatacao visual.
        """
        return v.replace(" ", "") if isinstance(v, str) else v

    @property
    def usa_wallet(self) -> bool:
        return bool(self.wallet_base64 or self.wallet_dir)

    @property
    def caminho_wallet(self) -> str | None:
        """Caminho do wallet resolvido a partir da raiz do projeto.

        Caminho relativo no .env (ex.: ./wallet) sobrevive a renomear a pasta do
        projeto e a rodar de qualquer diretorio -- ao contrario do absoluto, que
        quebra em silencio quando a pasta muda de nome.
        """
        if not self.wallet_dir:
            return None
        caminho = Path(self.wallet_dir).expanduser()
        if not caminho.is_absolute():
            caminho = RAIZ_DO_PROJETO / caminho
        return str(caminho.resolve())


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
