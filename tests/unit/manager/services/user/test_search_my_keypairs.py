"""Unit tests for UserService.search_my_keypairs.

Tests action dispatch and result mapping using mocked KeyPairRepository.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai.backend.common.types import AccessKey
from ai.backend.manager.data.keypair.types import MyKeypairData
from ai.backend.manager.repositories.base.pagination import OffsetPagination
from ai.backend.manager.repositories.base.querier import BatchQuerier
from ai.backend.manager.repositories.keypair.repository import KeyPairRepository
from ai.backend.manager.repositories.keypair.types import KeyPairSearchResult
from ai.backend.manager.repositories.user.repository import UserRepository
from ai.backend.manager.services.user.actions.search_my_keypairs import (
    SearchMyKeypairsAction,
    SearchMyKeypairsActionResult,
)
from ai.backend.manager.services.user.service import UserService


def _make_service(
    mock_user_repo: MagicMock,
    mock_keypair_repo: MagicMock,
) -> UserService:
    return UserService(
        storage_manager=MagicMock(),
        valkey_stat_client=MagicMock(),
        agent_registry=MagicMock(),
        user_repository=mock_user_repo,
        keypair_repository=mock_keypair_repo,
    )


def _make_my_keypair_data(
    access_key: str = "TESTKEY00000000000",
    is_active: bool = True,
    is_admin: bool = False,
) -> MyKeypairData:
    return MyKeypairData(
        access_key=AccessKey(access_key),
        is_active=is_active,
        is_admin=is_admin,
        created_at=datetime.now(tz=UTC),
        last_used=None,
        resource_policy="default",
        rate_limit=1000,
    )


class TestSearchMyKeypairs:
    """Tests for UserService.search_my_keypairs."""

    @pytest.fixture
    def mock_user_repository(self) -> MagicMock:
        return MagicMock(spec=UserRepository)

    @pytest.fixture
    def mock_keypair_repository(self) -> MagicMock:
        return MagicMock(spec=KeyPairRepository)

    @pytest.fixture
    def service(
        self,
        mock_user_repository: MagicMock,
        mock_keypair_repository: MagicMock,
    ) -> UserService:
        return _make_service(mock_user_repository, mock_keypair_repository)

    async def test_returns_keypairs_with_correct_count(
        self,
        service: UserService,
        mock_keypair_repository: MagicMock,
    ) -> None:
        """Action with user_uuid and querier returns mapped SearchMyKeypairsActionResult."""
        user_uuid = uuid.uuid4()
        keypairs = [_make_my_keypair_data(f"KEY{i:017d}") for i in range(3)]
        mock_keypair_repository.search_my_keypairs = AsyncMock(
            return_value=KeyPairSearchResult(
                items=keypairs,
                total_count=3,
                has_next_page=False,
                has_previous_page=False,
            )
        )

        querier = BatchQuerier(pagination=OffsetPagination(limit=10, offset=0))
        action = SearchMyKeypairsAction(user_uuid=user_uuid, querier=querier)

        result = await service.search_my_keypairs(action)

        assert isinstance(result, SearchMyKeypairsActionResult)
        assert len(result.keypairs) == 3
        assert result.total_count == 3
        assert result.has_next_page is False
        assert result.has_previous_page is False

    async def test_repository_called_with_correct_args(
        self,
        service: UserService,
        mock_keypair_repository: MagicMock,
    ) -> None:
        """Repository is called with the exact user_uuid and querier from the action."""
        user_uuid = uuid.uuid4()
        mock_keypair_repository.search_my_keypairs = AsyncMock(
            return_value=KeyPairSearchResult(
                items=[],
                total_count=0,
                has_next_page=False,
                has_previous_page=False,
            )
        )

        querier = BatchQuerier(pagination=OffsetPagination(limit=5, offset=0))
        action = SearchMyKeypairsAction(user_uuid=user_uuid, querier=querier)

        await service.search_my_keypairs(action)

        mock_keypair_repository.search_my_keypairs.assert_called_once_with(user_uuid, querier)

    async def test_pagination_flags_mapped_correctly(
        self,
        service: UserService,
        mock_keypair_repository: MagicMock,
    ) -> None:
        """has_next_page and has_previous_page are mapped from repository result."""
        user_uuid = uuid.uuid4()
        keypairs = [_make_my_keypair_data(f"KEY{i:017d}") for i in range(2)]
        mock_keypair_repository.search_my_keypairs = AsyncMock(
            return_value=KeyPairSearchResult(
                items=keypairs,
                total_count=5,
                has_next_page=True,
                has_previous_page=True,
            )
        )

        querier = BatchQuerier(pagination=OffsetPagination(limit=2, offset=2))
        action = SearchMyKeypairsAction(user_uuid=user_uuid, querier=querier)

        result = await service.search_my_keypairs(action)

        assert result.total_count == 5
        assert result.has_next_page is True
        assert result.has_previous_page is True
        assert len(result.keypairs) == 2

    async def test_empty_result_maps_correctly(
        self,
        service: UserService,
        mock_keypair_repository: MagicMock,
    ) -> None:
        """Empty repository result maps to empty keypairs list with total_count=0."""
        user_uuid = uuid.uuid4()
        mock_keypair_repository.search_my_keypairs = AsyncMock(
            return_value=KeyPairSearchResult(
                items=[],
                total_count=0,
                has_next_page=False,
                has_previous_page=False,
            )
        )

        querier = BatchQuerier(pagination=OffsetPagination(limit=10, offset=0))
        action = SearchMyKeypairsAction(user_uuid=user_uuid, querier=querier)

        result = await service.search_my_keypairs(action)

        assert result.keypairs == []
        assert result.total_count == 0
        assert result.has_next_page is False
        assert result.has_previous_page is False

    async def test_keypair_data_fields_preserved(
        self,
        service: UserService,
        mock_keypair_repository: MagicMock,
    ) -> None:
        """All MyKeypairData fields are passed through unchanged in result.keypairs."""
        user_uuid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        keypair = MyKeypairData(
            access_key=AccessKey("MYKEY12345678901"),
            is_active=False,
            is_admin=True,
            created_at=created,
            last_used=None,
            resource_policy="special-policy",
            rate_limit=2000,
        )
        mock_keypair_repository.search_my_keypairs = AsyncMock(
            return_value=KeyPairSearchResult(
                items=[keypair],
                total_count=1,
                has_next_page=False,
                has_previous_page=False,
            )
        )

        querier = BatchQuerier(pagination=OffsetPagination(limit=10, offset=0))
        action = SearchMyKeypairsAction(user_uuid=user_uuid, querier=querier)

        result = await service.search_my_keypairs(action)

        assert len(result.keypairs) == 1
        item = result.keypairs[0]
        assert item.access_key == AccessKey("MYKEY12345678901")
        assert item.is_active is False
        assert item.is_admin is True
        assert item.created_at == created
        assert item.last_used is None
        assert item.resource_policy == "special-policy"
        assert item.rate_limit == 2000
