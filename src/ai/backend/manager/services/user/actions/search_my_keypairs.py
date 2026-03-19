from __future__ import annotations

from dataclasses import dataclass
from typing import override
from uuid import UUID

from ai.backend.manager.actions.action import BaseActionResult
from ai.backend.manager.actions.types import ActionOperationType
from ai.backend.manager.data.keypair.types import MyKeypairData
from ai.backend.manager.repositories.base.querier import BatchQuerier
from ai.backend.manager.services.user.actions.base import UserAction


@dataclass
class SearchMyKeypairsAction(UserAction):
    """Action for listing keypairs of the current authenticated user."""

    user_uuid: UUID
    querier: BatchQuerier

    @override
    def entity_id(self) -> str | None:
        return str(self.user_uuid)

    @override
    @classmethod
    def operation_type(cls) -> ActionOperationType:
        return ActionOperationType.SEARCH


@dataclass
class SearchMyKeypairsActionResult(BaseActionResult):
    """Result of listing keypairs for the current authenticated user."""

    keypairs: list[MyKeypairData]
    total_count: int
    has_next_page: bool
    has_previous_page: bool

    @override
    def entity_id(self) -> str | None:
        return None
