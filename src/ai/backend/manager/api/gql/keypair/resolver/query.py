"""Keypair GraphQL query resolvers."""

from __future__ import annotations

import strawberry
from strawberry import Info

from ai.backend.common.contexts.user import current_user
from ai.backend.manager.api.gql.keypair.fetcher import fetch_my_keypairs
from ai.backend.manager.api.gql.keypair.types import (
    KeyPairFilterGQL,
    KeyPairOrderByGQL,
    MyKeypairConnection,
)
from ai.backend.manager.api.gql.types import StrawberryGQLContext


@strawberry.field(
    description=(
        "Added in 26.x. List keypairs of the current authenticated user. "
        "Returns all keypairs belonging to the currently authenticated user. "
        "Supports filtering, ordering, and cursor-based pagination. "
        "Returns an error if not authenticated."
    )
)  # type: ignore[misc]
async def my_keypairs(
    info: Info[StrawberryGQLContext],
    filter: KeyPairFilterGQL | None = None,
    order_by: list[KeyPairOrderByGQL] | None = None,
    before: str | None = None,
    after: str | None = None,
    first: int | None = None,
    last: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> MyKeypairConnection | None:
    """List keypairs of the current authenticated user.

    Args:
        info: Strawberry GraphQL context.
        filter: Optional filter criteria (is_active, is_admin, created_at).
        order_by: Optional ordering specification.
        before: Cursor for backward pagination.
        after: Cursor for forward pagination.
        first: Number of items from the start.
        last: Number of items from the end.
        limit: Maximum number of items (offset-based).
        offset: Starting position (offset-based).

    Returns:
        MyKeypairConnection with paginated keypair records belonging to the current user.

    Raises:
        Unauthorized: If the user is not authenticated.
    """
    me = current_user()
    if me is None:
        from aiohttp import web

        raise web.HTTPUnauthorized(reason="Authentication required")

    return await fetch_my_keypairs(
        info,
        user_uuid=me.user_id,
        filter=filter,
        order_by=order_by,
        before=before,
        after=after,
        first=first,
        last=last,
        limit=limit,
        offset=offset,
    )
