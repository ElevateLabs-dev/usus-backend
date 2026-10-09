import secrets

import bcrypt

UNUSABLE_PASSWORD = "!"  # sentinel — account locked until password is set
MIN_PASSWORD_LENGTH = 8


def generate_temporary_password() -> str:
    """Random 12-character password for invited users (replaced on first sign-in)."""
    return secrets.token_urlsafe(9)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if hashed == UNUSABLE_PASSWORD:
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())
