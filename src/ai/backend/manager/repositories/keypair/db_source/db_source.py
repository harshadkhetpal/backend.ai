"""DB source for keypair repository operations."""

from __future__ import annotations

import sqlalchemy as sa

from ai.backend.common.types import AccessKey
from ai.backend.manager.data.keypair.types import MyKeypairData
from ai.backend.manager.models.keypair.row import KeyPairRow
from ai.backend.manager.models.utils import ExtendedAsyncSAEngine
from ai.backend.manager.repositories.base.querier import BatchQuerier, execute_batch_querier
from ai.backend.manager.repositories.keypair.types import KeyPairSearchResult

__all__ = ("KeyPairDBSource",)


def _row_to_my_keypair_data(row: KeyPairRow) -> MyKeypairData:
    return MyKeypairData(
        access_key=AccessKey(row.access_key),
        is_active=row.is_active if row.is_active is not None else True,
        is_admin=row.is_admin if row.is_admin is not None else False,
        created_at=row.created_at,
        last_used=row.last_used,
        resource_policy=row.resource_policy,
        rate_limit=row.rate_limit if row.rate_limit is not None else 0,
    )


class KeyPairDBSource:
    _db: ExtendedAsyncSAEngine

    def __init__(self, db: ExtendedAsyncSAEngine) -> None:
        self._db = db

    async def search_my_keypairs(
        self,
        querier: BatchQuerier,
    ) -> KeyPairSearchResult:
        """Search keypairs matching the given querier.

        User scoping is enforced by the caller via ``KeyPairConditions.by_user``
        in ``querier.base_conditions``.

        Args:
            querier: BatchQuerier containing base conditions (including user scope),
                filters, orders, and pagination.

        Returns:
            KeyPairSearchResult with matching keypairs and pagination info.
        """
        async with self._db.begin_readonly_session() as db_session:
            query = sa.select(KeyPairRow)
            result = await execute_batch_querier(db_session, query, querier)

            items = [_row_to_my_keypair_data(row.KeyPairRow) for row in result.rows]
            return KeyPairSearchResult(
                items=items,
                total_count=result.total_count,
                has_next_page=result.has_next_page,
                has_previous_page=result.has_previous_page,
            )
