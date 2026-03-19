"""KeyPair repository — delegates DB operations to KeyPairDBSource."""

from __future__ import annotations

from uuid import UUID

from ai.backend.common.exception import BackendAIError
from ai.backend.common.metrics.metric import DomainType, LayerType
from ai.backend.common.resilience.policies.metrics import MetricArgs, MetricPolicy
from ai.backend.common.resilience.policies.retry import BackoffStrategy, RetryArgs, RetryPolicy
from ai.backend.common.resilience.resilience import Resilience
from ai.backend.manager.models.utils import ExtendedAsyncSAEngine
from ai.backend.manager.repositories.base.querier import BatchQuerier
from ai.backend.manager.repositories.keypair.db_source import KeyPairDBSource
from ai.backend.manager.repositories.keypair.types import KeyPairSearchResult

__all__ = ("KeyPairRepository",)


keypair_repository_resilience = Resilience(
    policies=[
        MetricPolicy(MetricArgs(domain=DomainType.REPOSITORY, layer=LayerType.KEYPAIR_REPOSITORY)),
        RetryPolicy(
            RetryArgs(
                max_retries=10,
                retry_delay=0.1,
                backoff_strategy=BackoffStrategy.FIXED,
                non_retryable_exceptions=(BackendAIError,),
            )
        ),
    ]
)


class KeyPairRepository:
    _db_source: KeyPairDBSource

    def __init__(self, db: ExtendedAsyncSAEngine) -> None:
        self._db_source = KeyPairDBSource(db)

    @keypair_repository_resilience.apply()
    async def search_my_keypairs(
        self,
        user_uuid: UUID,
        querier: BatchQuerier,
    ) -> KeyPairSearchResult:
        """Search keypairs for a specific user.

        User scoping is enforced via ``KeyPairConditions.by_user(user_uuid)``
        in ``querier.base_conditions``, so ``user_uuid`` is not passed to the
        DB source directly.

        Args:
            user_uuid: UUID of the user whose keypairs are being queried.
            querier: BatchQuerier containing base conditions (including user scope),
                filters, orders, and pagination.

        Returns:
            KeyPairSearchResult with matching keypairs and pagination info.
        """
        return await self._db_source.search_my_keypairs(querier)
