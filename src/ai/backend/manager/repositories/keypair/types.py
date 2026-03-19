"""Types for keypair repository operations.

Contains SearchResult dataclasses for keypair search operations.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.backend.manager.data.keypair.types import MyKeypairData

__all__ = ("KeyPairSearchResult",)


@dataclass(frozen=True)
class KeyPairSearchResult:
    """Result of keypair search operations."""

    items: list[MyKeypairData]
    """List of keypair data items."""

    total_count: int
    """Total number of items matching the query (before pagination)."""

    has_next_page: bool
    """Whether there are more items after the current page."""

    has_previous_page: bool
    """Whether there are items before the current page."""
