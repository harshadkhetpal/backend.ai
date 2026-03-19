"""Keypair GraphQL data fetcher functions."""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from strawberry import Info
from strawberry.relay import PageInfo

from ai.backend.manager.api.gql.adapter import PaginationOptions, PaginationSpec
from ai.backend.manager.api.gql.base import encode_cursor
from ai.backend.manager.api.gql.keypair.types import (
    KeyPairFilterGQL,
    KeyPairOrderByGQL,
    MyKeypairConnection,
    MyKeypairEdge,
    MyKeypairGQL,
)
from ai.backend.manager.api.gql.types import StrawberryGQLContext
from ai.backend.manager.models.keypair.row import KeyPairRow
from ai.backend.manager.repositories.keypair.options import KeyPairConditions, KeyPairOrders
from ai.backend.manager.services.user.actions.search_my_keypairs import SearchMyKeypairsAction


@lru_cache(maxsize=1)
def get_keypair_pagination_spec() -> PaginationSpec:
    """Cached pagination spec for keypair queries."""
    return PaginationSpec(
        forward_order=KeyPairOrders.created_at(ascending=False),
        backward_order=KeyPairOrders.created_at(ascending=True),
        forward_condition_factory=KeyPairConditions.by_cursor_forward,
        backward_condition_factory=KeyPairConditions.by_cursor_backward,
        tiebreaker_order=KeyPairRow.access_key.asc(),
    )


async def fetch_my_keypairs(
    info: Info[StrawberryGQLContext],
    user_uuid: UUID,
    filter: KeyPairFilterGQL | None = None,
    order_by: list[KeyPairOrderByGQL] | None = None,
    before: str | None = None,
    after: str | None = None,
    first: int | None = None,
    last: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> MyKeypairConnection:
    """Fetch keypairs belonging to the given user.

    The user_uuid is always applied as a base condition (security boundary),
    ensuring users can only see their own keypairs regardless of filter arguments.

    Args:
        info: Strawberry GraphQL context.
        user_uuid: UUID of the authenticated user (security boundary).
        filter: Optional additional filter criteria.
        order_by: Optional ordering specification.
        before: Cursor for backward pagination.
        after: Cursor for forward pagination.
        first: Number of items from the start.
        last: Number of items from the end.
        limit: Maximum number of items (offset-based).
        offset: Starting position (offset-based).

    Returns:
        MyKeypairConnection with paginated keypair records.
    """
    processors = info.context.processors

    # Build querier with user scoping as base condition (security boundary)
    querier = info.context.gql_adapter.build_querier(
        PaginationOptions(
            first=first,
            after=after,
            last=last,
            before=before,
            limit=limit,
            offset=offset,
        ),
        get_keypair_pagination_spec(),
        filter=filter,
        order_by=order_by,
        base_conditions=[KeyPairConditions.by_user(user_uuid)],
    )

    # Execute via processor
    action_result = await processors.user.search_my_keypairs.wait_for_complete(
        SearchMyKeypairsAction(user_uuid=user_uuid, querier=querier)
    )

    # Build connection
    nodes = [MyKeypairGQL.from_data(data) for data in action_result.keypairs]
    edges = [MyKeypairEdge(node=node, cursor=encode_cursor(node.access_key)) for node in nodes]

    return MyKeypairConnection(
        edges=edges,
        page_info=PageInfo(
            has_next_page=action_result.has_next_page,
            has_previous_page=action_result.has_previous_page,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
        ),
        count=action_result.total_count,
    )
