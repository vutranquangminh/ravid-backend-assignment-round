"""Models for the accounts app (slice 02 + slice 05).

``CreditAccount`` stores a per-user chat-credit balance that is decremented by
``tokens_consumed`` on every successful chat query (D-016).  It is lazily
created on first access via ``get_or_create_account(user)`` so the slice-02
registration flow needs no changes.

Design notes:
- OneToOneField to the auth user (CASCADE on delete).
- ``balance`` is a PositiveIntegerField; it is floored at 0 by the view so it
  can never go negative in normal operation.
- ``get_or_create_account`` sets the balance from ``settings.DEFAULT_CHAT_CREDITS``
  at creation time, not as a field default, so the setting can be changed without
  requiring a new migration.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CreditAccount(models.Model):
    """Per-user credit balance for chat queries."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_account",
    )
    balance = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "credit account"
        verbose_name_plural = "credit accounts"

    def __str__(self) -> str:
        return f"CreditAccount(user_id={self.user_id}, balance={self.balance})"


def get_or_create_account(user: object) -> CreditAccount:
    """Return the ``CreditAccount`` for *user*, creating it if it doesn't exist.

    On creation the balance is set from ``settings.DEFAULT_CHAT_CREDITS`` so
    the correct value is used regardless of when the migration was generated.

    Args:
        user: A Django auth user instance.

    Returns:
        The user's ``CreditAccount`` (either existing or newly created).
    """
    account, created = CreditAccount.objects.get_or_create(
        user=user,
        defaults={"balance": settings.DEFAULT_CHAT_CREDITS},
    )
    return account
