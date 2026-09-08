"""Preparacao do wallet do Oracle ADB para ambientes sem disco persistente.

Em desenvolvimento o wallet fica descompactado em ./wallet e basta apontar
WALLET_DIR. Em hospedagem (Render, Fly, Railway) isso nao funciona: o wallet e
segredo, esta fora do git, e nao ha volume para monta-lo.

A saida e WALLET_BASE64 -- o .zip do wallet codificado em base64 numa variavel
de ambiente secreta. Na inicializacao ele e materializado num diretorio
temporario com permissao restrita, que morre junto com o processo.

Ordem de precedencia:
  1. WALLET_BASE64  -> materializa e usa
  2. WALLET_DIR     -> usa o diretorio como esta
  3. nenhum dos dois-> TLS sem wallet (o DSN carrega tudo que o driver precisa)
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Arquivo que todo wallet do ADB tem; serve para achar a raiz depois de extrair.
_ARQUIVO_MARCADOR = "tnsnames.ora"

_diretorio_materializado: str | None = None


class WalletInvalidoError(RuntimeError):
    pass


def _extrair(conteudo_zip: bytes, destino: Path) -> Path:
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as arquivo:
            # Recusa caminhos absolutos ou com ".." antes de escrever qualquer
            # coisa: um zip malicioso poderia sobrescrever arquivos fora do destino.
            for nome in arquivo.namelist():
                caminho = Path(nome)
                if caminho.is_absolute() or ".." in caminho.parts:
                    raise WalletInvalidoError(
                        f"WALLET_BASE64 contém caminho suspeito: {nome!r}"
                    )
            arquivo.extractall(destino)
    except zipfile.BadZipFile as erro:
        raise WalletInvalidoError(
            "WALLET_BASE64 não é um .zip válido. Gere com: "
            "base64 -i wallet.zip | tr -d '\\n'"
        ) from erro

    # O zip pode trazer os arquivos na raiz ou dentro de uma pasta.
    if (destino / _ARQUIVO_MARCADOR).exists():
        return destino
    for caminho in destino.rglob(_ARQUIVO_MARCADOR):
        return caminho.parent

    raise WalletInvalidoError(
        f"O wallet extraído não contém {_ARQUIVO_MARCADOR}. "
        "Confirme que o .zip é o wallet baixado do Console OCI."
    )


def materializar_de_base64(wallet_base64: str) -> str:
    """Escreve o wallet num diretorio temporario e devolve o caminho."""
    global _diretorio_materializado
    if _diretorio_materializado is not None:
        return _diretorio_materializado

    try:
        conteudo = base64.b64decode(wallet_base64.strip(), validate=True)
    except (binascii.Error, ValueError) as erro:
        raise WalletInvalidoError(
            "WALLET_BASE64 não é base64 válido. Gere com: "
            "base64 -i wallet.zip | tr -d '\\n'"
        ) from erro

    # 0o700: a chave privada do wallet nao pode ficar legivel para outros
    # usuarios da maquina.
    temporario = Path(tempfile.mkdtemp(prefix="biosyn-wallet-"))
    os.chmod(temporario, 0o700)

    raiz = _extrair(conteudo, temporario)
    for arquivo in raiz.iterdir():
        if arquivo.is_file():
            os.chmod(arquivo, 0o600)

    _diretorio_materializado = str(raiz)
    logger.info("wallet materializado a partir de WALLET_BASE64 (%d bytes)", len(conteudo))
    return _diretorio_materializado


def preparar(wallet_base64: str | None, caminho_wallet: str | None) -> str | None:
    """Devolve o diretorio do wallet a usar, ou None para TLS sem wallet."""
    if wallet_base64:
        return materializar_de_base64(wallet_base64)

    if caminho_wallet:
        if not Path(caminho_wallet).is_dir():
            raise WalletInvalidoError(
                f"WALLET_DIR aponta para {caminho_wallet}, que não existe. "
                "Em hospedagem sem disco persistente, use WALLET_BASE64."
            )
        return caminho_wallet

    logger.info("sem wallet: conectando por TLS, com o DSN carregando a configuração")
    return None
