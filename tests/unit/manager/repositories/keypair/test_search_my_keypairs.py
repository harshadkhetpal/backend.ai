"""Tests for KeyPairRepository.search_my_keypairs.

Uses real database operations to verify user scoping and pagination.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest

from ai.backend.common.types import AccessKey

# Row imports required to trigger mapper initialization (FK dependency order)
from ai.backend.manager.models.agent import AgentRow
from ai.backend.manager.models.deployment_auto_scaling_policy import DeploymentAutoScalingPolicyRow
from ai.backend.manager.models.deployment_policy import DeploymentPolicyRow
from ai.backend.manager.models.deployment_revision import DeploymentRevisionRow
from ai.backend.manager.models.domain import DomainRow
from ai.backend.manager.models.endpoint import EndpointRow
from ai.backend.manager.models.group import AssocGroupUserRow, GroupRow
from ai.backend.manager.models.image import ImageRow
from ai.backend.manager.models.kernel import KernelRow
from ai.backend.manager.models.keypair import KeyPairRow
from ai.backend.manager.models.rbac_models import UserRoleRow
from ai.backend.manager.models.resource_policy import (
    KeyPairResourcePolicyRow,
    ProjectResourcePolicyRow,
    UserResourcePolicyRow,
)
from ai.backend.manager.models.resource_preset import ResourcePresetRow
from ai.backend.manager.models.routing import RoutingRow
from ai.backend.manager.models.scaling_group import ScalingGroupRow
from ai.backend.manager.models.session import SessionRow
from ai.backend.manager.models.user import UserRow, UserStatus
from ai.backend.manager.models.utils import ExtendedAsyncSAEngine
from ai.backend.manager.models.vfolder import VFolderRow
from ai.backend.manager.repositories.base.pagination import OffsetPagination
from ai.backend.manager.repositories.base.querier import BatchQuerier
from ai.backend.manager.repositories.keypair.options import KeyPairConditions, KeyPairOrders
from ai.backend.manager.repositories.keypair.repository import KeyPairRepository
from ai.backend.testutils.db import with_tables

_TABLES = [
    DomainRow,
    ScalingGroupRow,
    UserResourcePolicyRow,
    ProjectResourcePolicyRow,
    KeyPairResourcePolicyRow,
    UserRoleRow,
    UserRow,
    KeyPairRow,
    GroupRow,
    AssocGroupUserRow,
    ImageRow,
    VFolderRow,
    EndpointRow,
    DeploymentPolicyRow,
    DeploymentAutoScalingPolicyRow,
    DeploymentRevisionRow,
    SessionRow,
    AgentRow,
    KernelRow,
    RoutingRow,
    ResourcePresetRow,
]

_TEST_DOMAIN = "test-domain"
_TEST_USER_RESOURCE_POLICY = "default"
_TEST_KEYPAIR_RESOURCE_POLICY = "default"


class TestSearchMyKeypairs:
    """Integration tests for KeyPairRepository.search_my_keypairs."""

    @pytest.fixture
    async def db_with_tables_created(
        self,
        database_connection: ExtendedAsyncSAEngine,
    ) -> AsyncGenerator[ExtendedAsyncSAEngine, None]:
        """Create required tables, yield the engine, then clean up."""
        async with with_tables(database_connection, _TABLES):
            yield database_connection

    @pytest.fixture
    async def two_users_with_keypairs(
        self,
        db_with_tables_created: ExtendedAsyncSAEngine,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Insert two users (A and B) with keypairs; return (user_a_uuid, user_b_uuid).

        User A gets 3 keypairs, User B gets 2 keypairs.
        """
        db = db_with_tables_created
        user_a_uuid = uuid.uuid4()
        user_b_uuid = uuid.uuid4()

        async with db.begin_session() as session:
            session.add(
                DomainRow(
                    name=_TEST_DOMAIN,
                    description="Test domain",
                    is_active=True,
                    total_resource_slots={},
                    allowed_vfolder_hosts={},
                    allowed_docker_registries=[],
                    dotfiles=b"",
                    integration_id=None,
                )
            )
            await session.flush()

            session.add(
                UserResourcePolicyRow(
                    name=_TEST_USER_RESOURCE_POLICY,
                    max_vfolder_count=0,
                    max_quota_scope_size=-1,
                    max_session_count_per_model_session=10,
                    max_customized_image_count=10,
                )
            )
            await session.flush()

            session.add(
                KeyPairResourcePolicyRow(
                    name=_TEST_KEYPAIR_RESOURCE_POLICY,
                    total_resource_slots={},
                    max_concurrent_sessions=10,
                    max_session_lifetime=0,
                    max_pending_session_count=5,
                    max_pending_session_resource_slots={},
                    max_concurrent_sftp_sessions=5,
                    max_containers_per_session=1,
                    idle_timeout=0,
                )
            )
            await session.flush()

            session.add_all([
                UserRow(
                    uuid=user_a_uuid,
                    username=f"user-a-{user_a_uuid.hex[:8]}",
                    email=f"user-a-{user_a_uuid.hex[:8]}@example.com",
                    password="hashed",
                    need_password_change=False,
                    full_name="User A",
                    description="",
                    status=UserStatus.ACTIVE,
                    status_info="admin-requested",
                    domain_name=_TEST_DOMAIN,
                    role="user",
                    resource_policy=_TEST_USER_RESOURCE_POLICY,
                ),
                UserRow(
                    uuid=user_b_uuid,
                    username=f"user-b-{user_b_uuid.hex[:8]}",
                    email=f"user-b-{user_b_uuid.hex[:8]}@example.com",
                    password="hashed",
                    need_password_change=False,
                    full_name="User B",
                    description="",
                    status=UserStatus.ACTIVE,
                    status_info="admin-requested",
                    domain_name=_TEST_DOMAIN,
                    role="user",
                    resource_policy=_TEST_USER_RESOURCE_POLICY,
                ),
            ])
            await session.flush()

            # User A: 3 keypairs
            for i in range(3):
                session.add(
                    KeyPairRow(
                        access_key=str(AccessKey(f"USERAKEY{i:012d}")),
                        secret_key=f"secret{i:034d}",
                        user_id=str(user_a_uuid),
                        user=user_a_uuid,
                        is_active=True,
                        is_admin=False,
                        resource_policy=_TEST_KEYPAIR_RESOURCE_POLICY,
                        rate_limit=1000,
                        dotfiles=b"\x90",
                        bootstrap_script="",
                    )
                )

            # User B: 2 keypairs
            for i in range(2):
                session.add(
                    KeyPairRow(
                        access_key=str(AccessKey(f"USERBKEY{i:012d}")),
                        secret_key=f"bsecret{i:033d}",
                        user_id=str(user_b_uuid),
                        user=user_b_uuid,
                        is_active=True,
                        is_admin=False,
                        resource_policy=_TEST_KEYPAIR_RESOURCE_POLICY,
                        rate_limit=500,
                        dotfiles=b"\x90",
                        bootstrap_script="",
                    )
                )

            await session.commit()

        return user_a_uuid, user_b_uuid

    @pytest.fixture
    def repository(self, db_with_tables_created: ExtendedAsyncSAEngine) -> KeyPairRepository:
        return KeyPairRepository(db=db_with_tables_created)

    async def test_returns_only_user_a_keypairs(
        self,
        two_users_with_keypairs: tuple[uuid.UUID, uuid.UUID],
        repository: KeyPairRepository,
    ) -> None:
        """User A's query returns only user A's keypairs (not user B's)."""
        user_a_uuid, _ = two_users_with_keypairs

        querier = BatchQuerier(
            conditions=[KeyPairConditions.by_user(user_a_uuid)],
            orders=[KeyPairOrders.created_at(ascending=True)],
            pagination=OffsetPagination(limit=100, offset=0),
        )

        result = await repository.search_my_keypairs(user_a_uuid, querier)

        assert result.total_count == 3
        assert len(result.items) == 3
        # All returned keypairs belong to user A (access key prefix)
        for item in result.items:
            assert str(item.access_key).startswith("USERAKEY")

    async def test_user_b_query_returns_only_user_b_keypairs(
        self,
        two_users_with_keypairs: tuple[uuid.UUID, uuid.UUID],
        repository: KeyPairRepository,
    ) -> None:
        """User B's query returns only user B's keypairs."""
        _, user_b_uuid = two_users_with_keypairs

        querier = BatchQuerier(
            conditions=[KeyPairConditions.by_user(user_b_uuid)],
            orders=[KeyPairOrders.created_at(ascending=True)],
            pagination=OffsetPagination(limit=100, offset=0),
        )

        result = await repository.search_my_keypairs(user_b_uuid, querier)

        assert result.total_count == 2
        assert len(result.items) == 2
        for item in result.items:
            assert str(item.access_key).startswith("USERBKEY")

    async def test_pagination_limit_returns_has_next_page_true(
        self,
        two_users_with_keypairs: tuple[uuid.UUID, uuid.UUID],
        repository: KeyPairRepository,
    ) -> None:
        """Limit=2 with 3 keypairs returns 2 items with has_next_page=True."""
        user_a_uuid, _ = two_users_with_keypairs

        querier = BatchQuerier(
            conditions=[KeyPairConditions.by_user(user_a_uuid)],
            orders=[KeyPairOrders.created_at(ascending=False)],
            pagination=OffsetPagination(limit=2, offset=0),
        )

        result = await repository.search_my_keypairs(user_a_uuid, querier)

        assert len(result.items) == 2
        assert result.total_count == 3
        assert result.has_next_page is True
        assert result.has_previous_page is False

    async def test_pagination_offset_returns_has_previous_page_true(
        self,
        two_users_with_keypairs: tuple[uuid.UUID, uuid.UUID],
        repository: KeyPairRepository,
    ) -> None:
        """Offset=2 with 3 total keypairs returns has_previous_page=True."""
        user_a_uuid, _ = two_users_with_keypairs

        querier = BatchQuerier(
            conditions=[KeyPairConditions.by_user(user_a_uuid)],
            orders=[KeyPairOrders.created_at(ascending=False)],
            pagination=OffsetPagination(limit=10, offset=2),
        )

        result = await repository.search_my_keypairs(user_a_uuid, querier)

        assert result.total_count == 3
        assert result.has_previous_page is True

    async def test_unknown_user_returns_empty_result(
        self,
        two_users_with_keypairs: tuple[uuid.UUID, uuid.UUID],
        repository: KeyPairRepository,
    ) -> None:
        """Query for a user with no keypairs returns empty items and zero total."""
        unknown_uuid = uuid.uuid4()

        querier = BatchQuerier(
            conditions=[KeyPairConditions.by_user(unknown_uuid)],
            orders=[KeyPairOrders.created_at(ascending=True)],
            pagination=OffsetPagination(limit=10, offset=0),
        )

        result = await repository.search_my_keypairs(unknown_uuid, querier)

        assert result.total_count == 0
        assert result.items == []
        assert result.has_next_page is False
        assert result.has_previous_page is False
