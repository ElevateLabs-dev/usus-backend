import bcrypt

UNUSABLE_PASSWORD = "!"  # sentinel — account locked until password is set


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if hashed == UNUSABLE_PASSWORD:
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())
