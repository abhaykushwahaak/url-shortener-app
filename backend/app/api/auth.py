"""Authentication routes: register, login, current user."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import TokenWithUser, UserLogin, UserRead, UserRegister
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()


@router.post(
    "/register",
    response_model=TokenWithUser,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Registers a new user and returns a JWT immediately, so the client does "
        "not need a second round-trip to log in. Returns **409** if the email is "
        "already registered."
    ),
)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> TokenWithUser:
    user = auth_service.register_user(db, payload)
    token = auth_service.issue_token(user, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return TokenWithUser(**token.model_dump(), user=UserRead.model_validate(user))


@router.post(
    "/login",
    response_model=TokenWithUser,
    summary="Log in",
    description=(
        "Exchanges email + password for a JWT. Send the token as "
        "`Authorization: Bearer <token>` on protected endpoints. Returns **401** "
        "for either a wrong email or a wrong password."
    ),
)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenWithUser:
    user = auth_service.authenticate_user(db, payload.email, payload.password)
    token = auth_service.issue_token(user, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return TokenWithUser(**token.model_dump(), user=UserRead.model_validate(user))


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get the current user",
    description="Returns the account behind the supplied bearer token.",
)
def read_me(current_user: User = Depends(auth_service.get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)