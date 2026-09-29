import base64

import pytest

from scripts.init_pii_keys import main


def test_replaces_template_placeholders_once_and_preserves_other_settings(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ADMIN_PASSWORD=stable\nPII_ENCRYPTION_KEY=replace-with-a-key\n"
                   "PII_BLIND_INDEX_KEY=replace-with-a-different-key\n")
    main(env)
    result = env.read_text()
    assert "ADMIN_PASSWORD=stable" in result
    assert "replace-with-" not in result
    keys = [line.split("=", 1)[1] for line in result.splitlines() if line.startswith("PII_")]
    assert len(keys) == 2 and keys[0] != keys[1]
    assert all(len(base64.b64decode(value)) == 32 for value in keys)
    main(env)
    assert env.read_text() == result


def test_refuses_to_overwrite_one_existing_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PII_ENCRYPTION_KEY=" + base64.b64encode(b"a" * 32).decode() + "\n")
    with pytest.raises(SystemExit, match="clave PII existente"):
        main(env)
