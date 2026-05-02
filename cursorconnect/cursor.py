"""Cursor account-level namespace for the CursorConnect SDK.

Use :class:`Cursor` for operations scoped to the authenticated user account
rather than a specific agent: reading the user profile, listing available
models, and browsing connected repositories.

All methods accept an *api_key* parameter that falls back to the
``CURSOR_API_KEY`` environment variable when omitted, so you never need to
hard-code credentials in application code.
"""

from __future__ import annotations

import os
from typing import List, Optional

from .client import CursorClient
from .types import ModelListItem, ModelParameterDefinition, ModelVariant
from .types.account import User, Repository
from .exceptions import CursorAgentError


def _resolve_key(api_key: Optional[str]) -> str:
    """Return *api_key* or the ``CURSOR_API_KEY`` env var, raising on miss."""
    key = api_key or os.environ.get("CURSOR_API_KEY")
    if not key:
        raise CursorAgentError(
            "No API key provided.  Pass api_key= or set CURSOR_API_KEY.",
            code="missing_api_key",
        )
    return key


class _ModelsNamespace:
    """
    Namespace for model-related account-level operations.

    Accessed via ``Cursor.models``.
    """

    @staticmethod
    def list(api_key: Optional[str] = None) -> List[ModelListItem]:
        """
        Return the set of models available to the authenticated user.

        Parameters
        ----------
        api_key : str, optional
            Cursor API key.  Falls back to the ``CURSOR_API_KEY`` env var.

        Returns
        -------
        list of ModelListItem
            Available models with IDs, display names, parameter definitions,
            and variant configurations.

        Raises
        ------
        CursorAgentError
            If no API key is available or the request fails.
        """
        client = CursorClient(_resolve_key(api_key))
        raw = client._get("/models")

        items: List[ModelListItem] = []
        for item in raw.get("items", []):
            params = [
                ModelParameterDefinition(
                    id=p.get("id", ""),
                    values=p.get("values", []),
                    displayName=p.get("displayName"),
                )
                for p in (item.get("parameters") or [])
            ]
            variants = [
                ModelVariant(
                    params=[],
                    displayName=v.get("displayName", ""),
                    description=v.get("description"),
                    isDefault=v.get("isDefault"),
                )
                for v in (item.get("variants") or [])
            ]
            items.append(
                ModelListItem(
                    id=item.get("id", ""),
                    displayName=item.get("displayName", item.get("id", "")),
                    description=item.get("description"),
                    parameters=params or None,
                    variants=variants or None,
                )
            )
        return items


class _RepositoriesNamespace:
    """
    Namespace for repository-related account-level operations.

    Accessed via ``Cursor.repositories``.
    """

    @staticmethod
    def list(api_key: Optional[str] = None) -> List[Repository]:
        """
        List GitHub repositories accessible to the authenticated user.

        .. note::
            This endpoint is subject to strict rate limits:
            **1 request / user / minute** and **30 requests / user / hour**.

        Parameters
        ----------
        api_key : str, optional
            Cursor API key.  Falls back to the ``CURSOR_API_KEY`` env var.

        Returns
        -------
        list of Repository
            Repositories the authenticated user has connected to their
            Cursor account, including URL and available metadata.

        Raises
        ------
        CursorAgentError
            If no API key is available or the request fails.
        """
        client = CursorClient(_resolve_key(api_key))
        raw = client._get("/repositories")
        return [
            Repository(
                url=item.get("url", ""),
                name=item.get("name"),
                description=item.get("description"),
                is_private=item.get("isPrivate"),
                default_branch=item.get("defaultBranch"),
            )
            for item in raw.get("items", [])
        ]


class Cursor:
    """
    Account-level namespace for the CursorConnect SDK.

    All methods are static (or accessible via class-level namespace objects)
    and accept an optional *api_key* parameter that falls back to the
    ``CURSOR_API_KEY`` environment variable.

    Attributes
    ----------
    models : _ModelsNamespace
        Sub-namespace for listing available models.
        Call ``Cursor.models.list(api_key=...)`` to retrieve them.
    repositories : _RepositoriesNamespace
        Sub-namespace for listing connected repositories.
        Call ``Cursor.repositories.list(api_key=...)`` to retrieve them.

    Examples
    --------
    Read the authenticated user's profile:

    >>> from cursorconnect import Cursor
    >>> user = Cursor.me(api_key="sk-...")
    >>> print(user.email)
    user@example.com

    List available models and repositories:

    >>> models = Cursor.models.list(api_key="sk-...")
    >>> for m in models:
    ...     print(m.id, "-", m.displayName)

    >>> repos = Cursor.repositories.list(api_key="sk-...")
    >>> for r in repos:
    ...     print(r.url)
    """

    models = _ModelsNamespace()
    repositories = _RepositoriesNamespace()

    @staticmethod
    def me(api_key: Optional[str] = None) -> User:
        """
        Retrieve the authenticated user's profile.

        Parameters
        ----------
        api_key : str, optional
            Cursor API key.  Falls back to the ``CURSOR_API_KEY`` env var.

        Returns
        -------
        User
            User profile containing ``api_key_name``, ``created_at``, and ``user_email``.

        Raises
        ------
        CursorAgentError
            If no API key is available or the request fails.
        """
        client = CursorClient(_resolve_key(api_key))
        raw = client._get("/me")
        return User(
            api_key_name=raw.get("apiKeyName", ""),
            created_at=raw.get("createdAt", ""),
            user_email=raw.get("userEmail"),
        )
