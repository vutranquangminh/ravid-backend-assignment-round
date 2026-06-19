"""Typed environment variable helpers.

Reads from os.environ — no hard dependency on third-party env libraries.
All helpers accept a ``default`` to avoid hard failures during import;
required production secrets should be validated at startup instead.

Contract:
- env(key)          -> str | None
- env(key, default) -> str
- env_bool(key, default=False) -> bool
- env_int(key, default=0)      -> int
- env_list(key, default="")    -> list[str]  (comma-separated)
"""

from __future__ import annotations

import os
from typing import overload


@overload
def env(key: str) -> str | None: ...


@overload
def env(key: str, default: str) -> str: ...


def env(key: str, default: str | None = None) -> str | None:
    """Return the value of *key* from os.environ, or *default*."""
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    """Return the boolean value of *key*.

    Truthy string values (case-insensitive): ``1``, ``true``, ``yes``, ``on``.
    All other non-empty values are falsy.
    """
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int = 0) -> int:
    """Return the integer value of *key*, or *default* if absent/invalid."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def env_list(key: str, default: str = "") -> list[str]:
    """Return a list of strings from a comma-separated env var.

    Empty strings after splitting are filtered out.
    """
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]
