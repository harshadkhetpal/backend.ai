"""
Reproduction test for the ownership transfer + re-share scenario.

On main, create_vfolder_permission uses RBACGranter with ON CONFLICT DO NOTHING,
so the scope-entity mapping duplicate is handled at SQL level without poisoning
the transaction. This test verifies the full flow works correctly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa

from ai.backend.common.types import BinarySize, ResourceSlot, VFolderUsageMode
from ai.backend.manager.data.auth.hash import PasswordHashAlgorithm
from ai.backend.manager.data.group.types import ProjectType
from ai.backend.manager.data.permission.id import ObjectId, ScopeId
from ai.backend.manager.data.permission.types import EntityType, RoleSource, ScopeType
from ai.backend.manager.data.vfolder.types import (
    VFolderMountPermission,
    VFolderOperationStatus,
    VFolderOwnershipType,
)
from ai.backend.manager.models.domain import DomainRow
from ai.backend.manager.models.group import GroupRow
from ai.backend.manager.models.hasher.types import PasswordInfo
from ai.backend.manager.models.keypair import KeyPairRow
from ai.backend.manager.models.rbac_models import UserRoleRow
from ai.backend.manager.models.rbac_models.association_scopes_entities import (
    AssociationScopesEntitiesRow,
)
from ai.backend.manager.models.rbac_models.permission.object_permission import ObjectPermissionRow
from ai.backend.manager.models.rbac_models.permission.permission import PermissionRow
from ai.backend.manager.models.rbac_models.role import RoleRow
from ai.backend.manager.models.resource_policy import (
    KeyPairResourcePolicyRow,
    ProjectResourcePolicyRow,
    UserResourcePolicyRow,
)
from ai.backend.manager.models.user import (
    UserRole,
    UserRow,
    UserStatus,
)
from ai.backend.manager.models.utils import ExtendedAsyncSAEngine
from ai.backend.manager.models.vfolder import VFolderPermissionRow, VFolderRow
from ai.backend.manager.repositories.vfolder.repository import VfolderRepository
from ai.backend.testutils.db import with_tables


class TestVFolderPermissionWithExistingScopeMapping:
    """
    Test that create_vfolder_permission works when scope-entity mapping already exists.
    This reproduces the ownership transfer + re-share scenario.
    """

    @pytest.fixture
    async def db_with_cleanup(
        self,
        database_connection: ExtendedAsyncSAEngine,
    ) -> AsyncGenerator[ExtendedAsyncSAEngine, None]:
        async with with_tables(
            database_connection,
            [
                DomainRow,
                UserResourcePolicyRow,
                ProjectResourcePolicyRow,
                KeyPairResourcePolicyRow,
                RoleRow,
                UserRoleRow,
                UserRow,
                KeyPairRow,
                GroupRow,
                VFolderRow,
                VFolderPermissionRow,
                AssociationScopesEntitiesRow,
                ObjectPermissionRow,
                PermissionRow,
            ],
        ):
            yield database_connection

    @pytest.fixture
    async def test_domain_name(
        self,
        db_with_cleanup: ExtendedAsyncSAEngine,
    ) -> str:
        domain_name = f"test-domain-{uuid.uuid4().hex[:8]}"
        async with db_with_cleanup.begin_session() as db_sess:
            domain = DomainRow(
                name=domain_name,
                description="Test domain",
                is_active=True,
                total_resource_slots=ResourceSlot(),
                allowed_vfolder_hosts={},
                allowed_docker_registries=[],
            )
            db_sess.add(domain)
            await db_sess.flush()
        return domain_name

    @pytest.fixture
    async def test_user_resource_policy_name(
        self,
        db_with_cleanup: ExtendedAsyncSAEngine,
    ) -> str:
        policy_name = f"test-policy-{uuid.uuid4().hex[:8]}"
        async with db_with_cleanup.begin_session() as db_sess:
            user_policy = UserResourcePolicyRow(
                name=policy_name,
                max_vfolder_count=10,
                max_quota_scope_size=BinarySize.finite_from_str("10GiB"),
                max_session_count_per_model_session=5,
                max_customized_image_count=3,
            )
            db_sess.add(user_policy)
            await db_sess.flush()
        return policy_name

    @pytest.fixture
    async def test_project_resource_policy_name(
        self,
        db_with_cleanup: ExtendedAsyncSAEngine,
    ) -> str:
        policy_name = f"test-policy-{uuid.uuid4().hex[:8]}"
        async with db_with_cleanup.begin_session() as db_sess:
            project_policy = ProjectResourcePolicyRow(
                name=policy_name,
                max_vfolder_count=10,
                max_quota_scope_size=BinarySize.finite_from_str("10GiB"),
                max_network_count=3,
            )
            db_sess.add(project_policy)
            await db_sess.flush()
        return policy_name

    @pytest.fixture
    async def test_group(
        self,
        db_with_cleanup: ExtendedAsyncSAEngine,
        test_domain_name: str,
        test_project_resource_policy_name: str,
    ) -> uuid.UUID:
        group_uuid = uuid.uuid4()
        async with db_with_cleanup.begin_session() as db_sess:
            group = GroupRow(
                id=group_uuid,
                name=f"test-group-{group_uuid.hex[:8]}",
                domain_name=test_domain_name,
                description="Test group",
                is_active=True,
                total_resource_slots=ResourceSlot(),
                allowed_vfolder_hosts={},
                resource_policy=test_project_resource_policy_name,
                type=ProjectType.GENERAL,
            )
            db_sess.add(group)
            await db_sess.flush()
        return group_uuid

    async def _create_user_with_rbac(
        self,
        db: ExtendedAsyncSAEngine,
        domain_name: str,
        policy_name: str,
    ) -> uuid.UUID:
        """Create a user with proper RBAC role setup."""
        user_uuid = uuid.uuid4()
        password_info = PasswordInfo(
            password="dummy",
            algorithm=PasswordHashAlgorithm.PBKDF2_SHA256,
            rounds=600_000,
            salt_size=32,
        )

        async with db.begin_session() as db_sess:
            user = UserRow(
                uuid=user_uuid,
                username=f"testuser-{user_uuid.hex[:8]}",
                email=f"test-{user_uuid.hex[:8]}@example.com",
                password=password_info,
                need_password_change=False,
                status=UserStatus.ACTIVE,
                status_info="active",
                domain_name=domain_name,
                role=UserRole.USER,
                resource_policy=policy_name,
            )
            db_sess.add(user)
            await db_sess.flush()

            role_row = RoleRow(
                id=uuid.uuid4(),
                name=f"user-role-{user_uuid.hex[:8]}",
                source=RoleSource.SYSTEM,
            )
            db_sess.add(role_row)
            await db_sess.flush()

            user_role_row = UserRoleRow(
                id=uuid.uuid4(),
                user_id=user_uuid,
                role_id=role_row.id,
            )
            db_sess.add(user_role_row)
            await db_sess.flush()

        return user_uuid

    async def test_create_vfolder_permission_with_preexisting_scope_mapping(
        self,
        db_with_cleanup: ExtendedAsyncSAEngine,
        test_domain_name: str,
        test_user_resource_policy_name: str,
        test_group: uuid.UUID,
    ) -> None:
        """
        Reproduce the scenario:
        1. Create user A with RBAC setup
        2. Create a vfolder owned by A, with scope-entity mapping for A
        3. Simulate ownership transfer to B (update vfolders.user only, no RBAC cleanup)
        4. Try create_vfolder_permission for user A on the same vfolder
        5. RBACGranter uses ON CONFLICT DO NOTHING so this should succeed
        """
        user_a_id = await self._create_user_with_rbac(
            db_with_cleanup, test_domain_name, test_user_resource_policy_name
        )
        user_b_id = await self._create_user_with_rbac(
            db_with_cleanup, test_domain_name, test_user_resource_policy_name
        )

        vfolder_id = uuid.uuid4()

        # Step 1: Create a vfolder owned by user A with scope-entity mapping
        async with db_with_cleanup.begin_session() as db_sess:
            vfolder_row = VFolderRow(
                id=vfolder_id,
                name=f"test-vfolder-{vfolder_id.hex[:8]}",
                domain_name=test_domain_name,
                usage_mode=VFolderUsageMode.GENERAL,
                permission=VFolderMountPermission.OWNER_PERM,
                host="local:volume1",
                creator=f"test-{user_a_id.hex[:8]}@example.com",
                ownership_type=VFolderOwnershipType.USER,
                user=user_a_id,
                group=test_group,
                unmanaged_path=None,
                cloneable=False,
                status=VFolderOperationStatus.READY,
                quota_scope_id=f"user:{user_a_id}",
            )
            db_sess.add(vfolder_row)
            await db_sess.flush()

            # Pre-existing scope-entity mapping for user A (as the owner would have)
            mapping = AssociationScopesEntitiesRow(
                id=uuid.uuid4(),
                scope_type=ScopeType.USER,
                scope_id=str(user_a_id),
                entity_type=EntityType.VFOLDER,
                entity_id=str(vfolder_id),
            )
            db_sess.add(mapping)
            await db_sess.flush()

        # Step 2: Simulate ownership transfer to B (WITHOUT RBAC cleanup)
        async with db_with_cleanup.begin_session() as db_sess:
            await db_sess.execute(
                sa.update(VFolderRow).where(VFolderRow.id == vfolder_id).values(user=user_b_id)
            )

        # Step 3: B shares the vfolder back to A.
        # The scope-entity mapping for A still exists from Step 1.
        repo = VfolderRepository(db=db_with_cleanup)

        result = await repo.create_vfolder_permission(
            vfolder_id,
            user_a_id,
            VFolderMountPermission.READ_WRITE,
        )

        assert result is not None
        assert result.vfolder == vfolder_id
        assert result.user == user_a_id
        assert result.permission == VFolderMountPermission.READ_WRITE
