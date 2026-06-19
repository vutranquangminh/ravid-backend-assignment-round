"""Business logic for the accounts app.

Design decisions:
- D-002: email stored as BOTH username and email (username is the unique key).
- Passwords are hashed by Django's ``create_user`` (never stored in plain text).
- ``authenticate_user`` looks up by email (= username) then checks the password;
  it returns ``None`` on any failure so the caller can return a uniform 401.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser

User = get_user_model()


def register_user(email: str, password: str) -> AbstractBaseUser:
    """Create and return a new User.

    Args:
        email: Normalised (lowercase) email address, used as the username.
        password: Plain-text password — hashed by ``create_user``.

    Returns:
        The newly created ``User`` instance.

    Raises:
        ValueError: If a user with that email already exists.  The message is
            exact per spec (D-022) so the view can surface it directly.
    """
    email = email.lower()
    if User.objects.filter(username=email).exists():
        raise ValueError("User with this email already exists.")

    user: AbstractBaseUser = User.objects.create_user(  # type: ignore[call-arg]
        username=email,
        email=email,
        password=password,
    )
    return user


def authenticate_user(email: str, password: str) -> AbstractBaseUser | None:
    """Return the User if credentials are valid, else None.

    Looks up by username (= email) and calls ``check_password``; this avoids
    the Django ``authenticate()`` backend chain, which is not needed here.
    """
    email = email.lower()
    try:
        user: AbstractBaseUser = User.objects.get(username=email)
    except User.DoesNotExist:
        return None

    if not user.check_password(password):
        return None

    return user
