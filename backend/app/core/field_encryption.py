"""Authenticated encryption of PII and keyed exact-match email lookup."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from dotenv import dotenv_values

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


def _key(name: str) -> bytes:
    value = os.getenv(name) or dotenv_values(
        Path(__file__).resolve().parents[2] / ".env").get(name)
    if not value:
        raise RuntimeError(f"{name} no está configurada (base64 de 32 bytes)")
    try:
        key = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError(f"{name} debe ser base64 de 32 bytes") from exc
    if len(key) != 32:
        raise RuntimeError(f"{name} debe contener exactamente 32 bytes")
    return key


def validate_pii_keys() -> None:
    if _key("PII_ENCRYPTION_KEY") == _key("PII_BLIND_INDEX_KEY"):
        raise RuntimeError("Las claves de cifrado y de índice ciego deben ser diferentes")


def encrypt_text(value: str, purpose: str) -> str:
    nonce = os.urandom(12)
    encrypted = AESGCM(_key("PII_ENCRYPTION_KEY")).encrypt(
        nonce, value.encode("utf-8"), purpose.encode("utf-8"))
    return "enc:v1:" + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_text(value: str, purpose: str) -> str:
    if not value.startswith("enc:v1:"):
        raise ValueError("Campo cifrado ausente o formato desconocido")
    raw = base64.urlsafe_b64decode(value.removeprefix("enc:v1:"))
    if len(raw) < 29:
        raise ValueError("Campo cifrado inválido")
    try:
        return AESGCM(_key("PII_ENCRYPTION_KEY")).decrypt(
            raw[:12], raw[12:], purpose.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise ValueError("No se pudo autenticar el campo cifrado") from exc


def blind_index(value: str, purpose: str = "users.email") -> str:
    return hmac.new(_key("PII_BLIND_INDEX_KEY"),
                    (purpose + "\0" + value.strip().lower()).encode("utf-8"),
                    hashlib.sha256).hexdigest()


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, purpose: str):
        super().__init__()
        self.purpose = purpose

    def process_bind_param(self, value, dialect):
        return encrypt_text(value, self.purpose) if value is not None else None

    def process_result_value(self, value, dialect):
        return decrypt_text(value, self.purpose) if value is not None else None


class EncryptedJSON(TypeDecorator):
    impl = JSONB
    cache_ok = True

    def __init__(self, purpose: str):
        super().__init__()
        self.purpose = purpose

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return {"__encrypted_v1__": encrypt_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")), self.purpose)}

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"__encrypted_v1__"}:
            raise ValueError("Campo JSON cifrado ausente")
        return json.loads(decrypt_text(value["__encrypted_v1__"], self.purpose))
