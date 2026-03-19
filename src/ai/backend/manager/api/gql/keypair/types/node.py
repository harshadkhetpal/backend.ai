"""Keypair GraphQL Node, Edge, and Connection types."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Self

import strawberry
from strawberry import ID, Info
from strawberry.relay import Connection, Edge, Node, NodeID

from ai.backend.manager.api.gql.types import StrawberryGQLContext
from ai.backend.manager.data.keypair.types import MyKeypairData


@strawberry.type(
    name="MyKeypair",
    description=(
        "Added in 26.x. Represents a keypair belonging to the currently authenticated user. "
        "Does not expose the secret key — secret keys are only returned at creation time."
    ),
)
class MyKeypairGQL(Node):
    """Keypair entity for the currently authenticated user."""

    id: NodeID[str] = strawberry.field(description="Unique identifier (access key).")
    access_key: str = strawberry.field(description="The access key identifier.")
    is_active: bool = strawberry.field(description="Whether this keypair is active.")
    is_admin: bool = strawberry.field(description="Whether this keypair has admin privileges.")
    created_at: datetime | None = strawberry.field(
        description="Timestamp when the keypair was created."
    )
    last_used: datetime | None = strawberry.field(
        description="Timestamp when the keypair was last used."
    )
    resource_policy: str = strawberry.field(
        description="Name of the resource policy attached to this keypair."
    )
    rate_limit: int = strawberry.field(
        description="Request rate limit for this keypair (requests per minute)."
    )

    @classmethod
    async def resolve_nodes(  # type: ignore[override]  # Strawberry Node uses AwaitableOrValue overloads incompatible with async def
        cls,
        *,
        info: Info[StrawberryGQLContext],
        node_ids: Iterable[str],
        required: bool = False,
    ) -> Iterable[Self | None]:
        # Node resolution by relay ID is not supported for MyKeypair.
        return [None for _ in node_ids]

    @classmethod
    def from_data(cls, data: MyKeypairData) -> Self:
        return cls(
            id=ID(data.access_key),
            access_key=data.access_key,
            is_active=data.is_active,
            is_admin=data.is_admin,
            created_at=data.created_at,
            last_used=data.last_used,
            resource_policy=data.resource_policy,
            rate_limit=data.rate_limit,
        )


MyKeypairEdge = Edge[MyKeypairGQL]


@strawberry.type(
    name="MyKeypairConnection",
    description=(
        "Added in 26.x. Paginated connection for the current user's keypair records. "
        "Provides relay-style cursor-based pagination. "
        "Use 'edges' to access individual records with cursor information, "
        "or 'nodes' for direct data access."
    ),
)
class MyKeypairConnection(Connection[MyKeypairGQL]):
    """Paginated connection for the current user's keypair records."""

    count: int = strawberry.field(
        description="Total number of keypair records matching the query criteria."
    )

    def __init__(self, *args: Any, count: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.count = count
