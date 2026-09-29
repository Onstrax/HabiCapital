import base64

import pytest

from app.core.field_encryption import (
    EncryptedJSON, EncryptedText, blind_index, decrypt_text, encrypt_text,
    validate_pii_keys,
)


def test_randomized_field_encryption_and_authenticated_context(monkeypatch):
    monkeypatch.setenv("PII_ENCRYPTION_KEY", base64.b64encode(b"e" * 32).decode())
    first = encrypt_text("juan@example.com", "users.email")
    second = encrypt_text("juan@example.com", "users.email")
    assert first != second
    assert "juan@example.com" not in first
    assert decrypt_text(first, "users.email") == "juan@example.com"
    with pytest.raises(ValueError):
        decrypt_text(first, "users.full_name")
    with pytest.raises(ValueError):
        decrypt_text(first[:-2] + "AA", "users.email")


def test_email_blind_index_normalizes_and_requires_independent_key(monkeypatch):
    monkeypatch.setenv("PII_BLIND_INDEX_KEY", base64.b64encode(b"b" * 32).decode())
    assert blind_index(" JUAN@EXAMPLE.COM ") == blind_index("juan@example.com")
    assert blind_index("otro@example.com") != blind_index("juan@example.com")
    monkeypatch.delenv("PII_BLIND_INDEX_KEY")
    with pytest.raises(RuntimeError):
        blind_index("juan@example.com")


def test_json_audit_and_replay_payloads_never_bind_as_plaintext(monkeypatch):
    monkeypatch.setenv("PII_ENCRYPTION_KEY", base64.b64encode(b"e" * 32).decode())
    mapper = EncryptedJSON("audit_logs.payload")
    payload = {"email": "juan@example.com", "amount": 100}
    stored = mapper.process_bind_param(payload, None)
    assert "juan@example.com" not in str(stored)
    assert mapper.process_result_value(stored, None) == payload
    with pytest.raises(ValueError):
        mapper.process_result_value({"email": "juan@example.com"}, None)
    assert mapper.process_result_value(None, None) is None
    assert EncryptedText("users.email").process_bind_param(None, None) is None


def test_keys_must_be_distinct(monkeypatch):
    same_key = base64.b64encode(b"A" * 32).decode()
    monkeypatch.setenv("PII_ENCRYPTION_KEY", same_key)
    monkeypatch.setenv("PII_BLIND_INDEX_KEY", same_key)
    with pytest.raises(RuntimeError, match="diferentes"):
        validate_pii_keys()
