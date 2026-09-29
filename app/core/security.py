from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


Role = Literal["teacher", "student"]


def create_access_token(subject_id: str, role: Role = "teacher") -> str:
    """JWT for a teacher or a student account. The role claim keeps the two
    apart: a student token is never accepted where a teacher token is needed
    (and vice versa)."""
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


class InvalidTokenError(Exception):
    pass


def decode_access_token(token: str, role: Role = "teacher") -> str:
    """Returns the account id if the token is valid *for this role*. Tokens
    issued before roles existed carry no role claim and are teacher tokens."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    account_id = payload.get("sub")
    if not account_id:
        raise InvalidTokenError("Token missing subject")
    if payload.get("role", "teacher") != role:
        raise InvalidTokenError(f"Not a {role} token")
    return account_id
