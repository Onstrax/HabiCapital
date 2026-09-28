"""Display minimization and canonical alias validation."""

import re

ALIAS_PATTERN = re.compile(r"[a-z0-9_]{3,20}\Z", flags=re.ASCII)


def mask_full_name(full_name: str) -> str:
    if not full_name or not full_name.strip():
        return ""
    return " ".join(word[0] + "*" * max(1, len(word) - 1) for word in full_name.split())


def sanitize_alias(alias: str) -> str:
    cleaned = alias.strip().lower()
    if not ALIAS_PATTERN.fullmatch(cleaned):
        raise ValueError("El alias debe tener 3-20 caracteres: a-z, 0-9 o guion bajo")
    return cleaned
