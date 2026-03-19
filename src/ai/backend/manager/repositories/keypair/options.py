"""Query conditions and orders for keypair repository operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa

from ai.backend.manager.models.keypair.row import KeyPairRow
from ai.backend.manager.repositories.base import QueryCondition, QueryOrder

__all__ = (
    "KeyPairConditions",
    "KeyPairOrders",
)


class KeyPairConditions:
    """Query conditions for filtering keypairs."""

    @staticmethod
    def by_user(user_uuid: UUID) -> QueryCondition:
        """Filter by user UUID (security base condition)."""

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            return KeyPairRow.user == user_uuid

        return inner

    @staticmethod
    def by_is_active(is_active: bool) -> QueryCondition:
        """Filter by is_active flag."""

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            return KeyPairRow.is_active == is_active

        return inner

    @staticmethod
    def by_is_admin(is_admin: bool) -> QueryCondition:
        """Filter by is_admin flag."""

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            return KeyPairRow.is_admin == is_admin

        return inner

    @staticmethod
    def by_created_at_before(dt: datetime) -> QueryCondition:
        """Filter by created_at < datetime."""

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            return KeyPairRow.created_at < dt

        return inner

    @staticmethod
    def by_created_at_after(dt: datetime) -> QueryCondition:
        """Filter by created_at > datetime."""

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            return KeyPairRow.created_at > dt

        return inner

    # ==================== Cursor Pagination ====================

    @staticmethod
    def by_cursor_forward(cursor_id: str) -> QueryCondition:
        """Cursor condition for forward pagination (after cursor).

        Uses subquery to get created_at of the cursor row and compare.
        The cursor_id is the access_key of the cursor keypair.
        """

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            subquery = (
                sa.select(KeyPairRow.created_at)
                .where(KeyPairRow.access_key == cursor_id)
                .scalar_subquery()
            )
            return KeyPairRow.created_at < subquery

        return inner

    @staticmethod
    def by_cursor_backward(cursor_id: str) -> QueryCondition:
        """Cursor condition for backward pagination (before cursor).

        Uses subquery to get created_at of the cursor row and compare.
        The cursor_id is the access_key of the cursor keypair.
        """

        def inner() -> sa.sql.expression.ColumnElement[bool]:
            subquery = (
                sa.select(KeyPairRow.created_at)
                .where(KeyPairRow.access_key == cursor_id)
                .scalar_subquery()
            )
            return KeyPairRow.created_at > subquery

        return inner


class KeyPairOrders:
    """Query orders for sorting keypairs."""

    @staticmethod
    def created_at(ascending: bool = True) -> QueryOrder:
        if ascending:
            return KeyPairRow.created_at.asc()
        return KeyPairRow.created_at.desc()

    @staticmethod
    def access_key(ascending: bool = True) -> QueryOrder:
        if ascending:
            return KeyPairRow.access_key.asc()
        return KeyPairRow.access_key.desc()
