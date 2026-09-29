"""Create stable, independent AES and HMAC secrets in an existing local .env.

Never regenerate these keys while encrypted data exists: doing so loses access.
"""

import base64
import os
import tempfile
from pathlib import Path

def main(path: Path | None = None) -> None:
    path = path or Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        raise SystemExit("Primero crea backend/.env desde backend/.env.example")
    content = path.read_text()
    names = ("PII_ENCRYPTION_KEY", "PII_BLIND_INDEX_KEY")
    lines = content.splitlines(keepends=True)
    existing = {name: next((line.partition("=")[2].strip() for line in lines
                            if line.startswith(name + "=")), None) for name in names}
    if all(existing.values()) and all(not value.startswith("replace-with-")
                                      for value in existing.values()):
        try:
            keys = [base64.b64decode(existing[name], validate=True) for name in names]
        except (ValueError, base64.binascii.Error) as exc:
            raise SystemExit("Las claves PII deben estar codificadas en base64") from exc
        if any(len(key) != 32 for key in keys) or keys[0] == keys[1]:
            raise SystemExit("Las claves PII deben ser distintas y de 32 bytes")
        print("Las claves PII existentes son válidas; se conservaron")
        return
    if any(value and not value.startswith("replace-with-") for value in existing.values()):
        raise SystemExit("Hay una clave PII existente: revisa backend/.env para no perder datos")
    generated = {name: base64.b64encode(os.urandom(32)).decode() for name in names}
    updated = [f"{line.partition('=')[0]}={generated[line.partition('=')[0]]}\n"
               if line.partition("=")[0] in generated else line for line in lines]
    for name in names:
        if existing[name] is None:
            if updated and not updated[-1].endswith("\n"):
                updated.append("\n")
            updated.append(f"{name}={generated[name]}\n")
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix=".pii-keys-")
    try:
        with os.fdopen(fd, "w") as output:
            output.writelines(updated)
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)
    os.chmod(path, 0o600)
    print("Claves PII creadas en backend/.env; consérvalas fuera del repositorio")


if __name__ == "__main__":
    main()
