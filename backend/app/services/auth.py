"""Registration, login and the `get_current_user` dependency."""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import Token, UserRegister

# NOTE: we use HTTPBearer rather than OAuth2PasswordBearer because /auth/login
# accepts JSON, not a form body. In /docs click "Authorize" and paste the token.
bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def register_user(db: Session, payload: UserRegister) -> User:
    """Create an account. Emails are stored lowercased so they are unique case-insensitively."""
    email = payload.email.lower()
    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Return the user when the password matches, else raise 401.

    The same error is returned for "no such user" and "wrong password" so the
    endpoint cannot be used to enumerate registered emails.
    """
    user = get_user_by_email(db, email.lower())
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def issue_token(user: User, expires_in_seconds: int) -> Token:
    return Token(
        access_token=create_access_token(str(user.id)),
        expires_in=expires_in_seconds,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve the bearer token into a User row."""
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(credentials.credentials)
        subject = payload.get("sub")
        if subject is None:
            raise CREDENTIALS_EXCEPTION
        user_id = uuid.UUID(subject)
    except (PyJWTError, ValueError) as exc:
        raise CREDENTIALS_EXCEPTION from exc

    user = db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user