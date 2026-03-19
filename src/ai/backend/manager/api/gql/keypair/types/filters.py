"""Keypair GraphQL filter and order-by types."""

from __future__ import annotations

from enum import StrEnum
from typing import override

import strawberry

from ai.backend.manager.api.gql.base import DateTimeFilter, OrderDirection
from ai.backend.manager.api.gql.types import GQLFilter, GQLOrderBy
from ai.backend.manager.repositories.base import (
    QueryCondition,
    QueryOrder,
    combine_conditions_or,
    negate_conditions,
)
from ai.backend.manager.repositories.keypair.options import KeyPairConditions, KeyPairOrders


@strawberry.input(
    name="KeyPairFilter",
    description=(
        "Added in 26.x. Filter input for querying keypairs. "
        "Supports filtering by active status, admin status, and creation time. "
        "Multiple filters can be combined using AND, OR, and NOT logical operators."
    ),
)
class KeyPairFilterGQL(GQLFilter):
    """Filter for keypair queries."""

    is_active: bool | None = strawberry.field(
        default=None,
        description="Filter by keypair active status.",
    )
    is_admin: bool | None = strawberry.field(
        default=None,
        description="Filter by keypair admin privilege.",
    )
    created_at: DateTimeFilter | None = strawberry.field(
        default=None,
        description="Filter by creation timestamp. Supports before, after, and between operations.",
    )

    AND: list[KeyPairFilterGQL] | None = strawberry.field(
        default=None,
        description="Combine multiple filters with AND logic. All conditions must match.",
    )
    OR: list[KeyPairFilterGQL] | None = strawberry.field(
        default=None,
        description="Combine multiple filters with OR logic. At least one condition must match.",
    )
    NOT: list[KeyPairFilterGQL] | None = strawberry.field(
        default=None,
        description="Negate the specified filters. Records matching these conditions will be excluded.",
    )

    @override
    def build_conditions(self) -> list[QueryCondition]:
        """Build query conditions from filter fields.

        Returns:
            List of QueryCondition callables.
        """
        conditions: list[QueryCondition] = []

        if self.is_active is not None:
            conditions.append(KeyPairConditions.by_is_active(self.is_active))

        if self.is_admin is not None:
            conditions.append(KeyPairConditions.by_is_admin(self.is_admin))

        if self.created_at:
            condition = self.created_at.build_query_condition(
                before_factory=lambda dt: KeyPairConditions.by_created_at_before(dt),
                after_factory=lambda dt: KeyPairConditions.by_created_at_after(dt),
            )
            if condition:
                conditions.append(condition)

        # Handle logical operators
        if self.AND:
            for sub_filter in self.AND:
                conditions.extend(sub_filter.build_conditions())

        if self.OR:
            or_sub_conditions: list[QueryCondition] = []
            for sub_filter in self.OR:
                or_sub_conditions.extend(sub_filter.build_conditions())
            if or_sub_conditions:
                conditions.append(combine_conditions_or(or_sub_conditions))

        if self.NOT:
            not_sub_conditions: list[QueryCondition] = []
            for sub_filter in self.NOT:
                not_sub_conditions.extend(sub_filter.build_conditions())
            if not_sub_conditions:
                conditions.append(negate_conditions(not_sub_conditions))

        return conditions


@strawberry.enum(
    name="KeyPairOrderField",
    description=(
        "Added in 26.x. Fields available for ordering keypair query results. "
        "CREATED_AT: Order by creation timestamp. "
        "ACCESS_KEY: Order by access key alphabetically."
    ),
)
class KeyPairOrderFieldGQL(StrEnum):
    CREATED_AT = "created_at"
    ACCESS_KEY = "access_key"


@strawberry.input(
    name="KeyPairOrderBy",
    description=(
        "Added in 26.x. Specifies ordering for keypair query results. "
        "Combine field selection with direction to sort results. "
        "Default direction is DESC (descending)."
    ),
)
class KeyPairOrderByGQL(GQLOrderBy):
    """OrderBy for keypair queries."""

    field: KeyPairOrderFieldGQL = strawberry.field(
        description="The field to order by. See KeyPairOrderField for available options."
    )
    direction: OrderDirection = strawberry.field(
        default=OrderDirection.DESC,
        description="Sort direction. ASC for ascending, DESC for descending.",
    )

    @override
    def to_query_order(self) -> QueryOrder:
        """Convert to repository QueryOrder.

        Returns:
            QueryOrder for the specified field and direction.
        """
        ascending = self.direction == OrderDirection.ASC
        match self.field:
            case KeyPairOrderFieldGQL.CREATED_AT:
                return KeyPairOrders.created_at(ascending)
            case KeyPairOrderFieldGQL.ACCESS_KEY:
                return KeyPairOrders.access_key(ascending)
            case _:
                raise ValueError(f"Unknown order field: {self.field}")
