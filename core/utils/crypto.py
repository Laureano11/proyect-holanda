"""
Helpers de cifrado simétrico para datos sensibles (tokens).
Usa Fernet (AES128 + HMAC) con una clave de 32 bytes en base64 (FIELD_ENCRYPTION_KEY).
El valor cifrado se guarda con prefijo 'enc::' para distinguirlo de texto plano legado.
"""

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc::"


class EncryptionKeyMissing(Exception):
    """Se lanza si falta la clave de cifrado requerida."""


def _get_key() -> bytes:
    raw = os.getenv("FIELD_ENCRYPTION_KEY", "")
    if not raw:
        raise EncryptionKeyMissing("Falta FIELD_ENCRYPTION_KEY en entorno.")
    try:
        key = raw.encode()
        # Validar longitud base64 (Fernet requiere 32 bytes base64)
        Fernet(key)  # valida formato
        return key
    except Exception as exc:  # pragma: no cover - validación defensiva
        raise EncryptionKeyMissing(f"FIELD_ENCRYPTION_KEY inválida: {exc}") from exc


def encrypt_string(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value.startswith(PREFIX):
        return value  # ya cifrado
    fernet = Fernet(_get_key())
    token = fernet.encrypt(value.encode()).decode()
    return f"{PREFIX}{token}"


def decrypt_string(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if not value.startswith(PREFIX):
        return value  # valor legado en texto plano
    token = value[len(PREFIX) :]
    fernet = Fernet(_get_key())
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionKeyMissing("No se pudo descifrar el valor (token inválido o clave incorrecta).") from exc

