import secrets

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
RESERVED = {"api", "auth", "docs", "redoc", "health", "openapi.json", "static"}


def generate(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_alias(alias: str) -> bool:
    return (
        3 <= len(alias) <= 32
        and alias not in RESERVED
        and all(char in ALPHABET or char in "-_" for char in alias)
    )
