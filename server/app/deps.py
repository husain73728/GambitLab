"""FastAPI dependencies and shared helpers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ConnectedAccount, User


def get_current_user(session: Session) -> User:
    """Single-user local app: ensure a default user exists."""
    user = session.scalar(select(User).order_by(User.id))
    if user is None:
        user = User(display_name="Player")
        session.add(user)
        session.commit()
    return user


def get_account(session: Session, user_id: int, provider: str = "chesscom"):
    return session.scalar(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id, ConnectedAccount.provider == provider
        )
    )
