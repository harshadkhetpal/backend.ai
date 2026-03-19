"""Unit tests for MyKeypair GraphQL types.

Tests KeyPairFilterGQL, KeyPairOrderByGQL, MyKeypairGQL, MyKeypairConnection.
"""

from __future__ import annotations

from datetime import UTC, datetime

from strawberry.relay import PageInfo

from ai.backend.common.types import AccessKey
from ai.backend.manager.api.gql.base import OrderDirection
from ai.backend.manager.api.gql.keypair.types.filters import (
    KeyPairFilterGQL,
    KeyPairOrderByGQL,
    KeyPairOrderFieldGQL,
)
from ai.backend.manager.api.gql.keypair.types.node import (
    MyKeypairConnection,
    MyKeypairEdge,
    MyKeypairGQL,
)
from ai.backend.manager.data.keypair.types import MyKeypairData

# Row imports to trigger mapper initialization (FK dependency order).
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
from ai.backend.manager.models.user import UserRow
from ai.backend.manager.models.vfolder import VFolderRow
from ai.backend.manager.repositories.base import QueryCondition

# Reference Row models to prevent unused-import removal.
_MAPPER_ROWS = [
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


def _compile(condition_callable: QueryCondition) -> str:
    """Compile a QueryCondition callable to SQL string."""
    return str(condition_callable().compile(compile_kwargs={"literal_binds": True}))


class TestKeyPairFilterGQL:
    """Tests for KeyPairFilterGQL.build_conditions()."""

    def test_is_active_true_generates_condition(self) -> None:
        f = KeyPairFilterGQL(is_active=True)
        conditions = f.build_conditions()
        assert len(conditions) == 1
        sql = _compile(conditions[0])
        assert "is_active" in sql
        assert "true" in sql.lower() or "True" in sql

    def test_is_active_false_generates_condition(self) -> None:
        f = KeyPairFilterGQL(is_active=False)
        conditions = f.build_conditions()
        assert len(conditions) == 1
        sql = _compile(conditions[0])
        assert "is_active" in sql
        assert "false" in sql.lower() or "False" in sql

    def test_is_admin_true_generates_condition(self) -> None:
        f = KeyPairFilterGQL(is_admin=True)
        conditions = f.build_conditions()
        assert len(conditions) == 1
        sql = _compile(conditions[0])
        assert "is_admin" in sql

    def test_is_admin_false_generates_condition(self) -> None:
        f = KeyPairFilterGQL(is_admin=False)
        conditions = f.build_conditions()
        assert len(conditions) == 1
        sql = _compile(conditions[0])
        assert "is_admin" in sql

    def test_combined_is_active_and_is_admin(self) -> None:
        f = KeyPairFilterGQL(is_active=True, is_admin=False)
        conditions = f.build_conditions()
        assert len(conditions) == 2

    def test_empty_filter_returns_empty_conditions(self) -> None:
        f = KeyPairFilterGQL()
        conditions = f.build_conditions()
        assert conditions == []

    def test_and_logic_extends_conditions(self) -> None:
        f = KeyPairFilterGQL(
            AND=[
                KeyPairFilterGQL(is_active=True),
                KeyPairFilterGQL(is_admin=False),
            ]
        )
        conditions = f.build_conditions()
        assert len(conditions) == 2

    def test_or_logic_wraps_in_single_condition(self) -> None:
        f = KeyPairFilterGQL(
            OR=[
                KeyPairFilterGQL(is_active=True),
                KeyPairFilterGQL(is_admin=True),
            ]
        )
        conditions = f.build_conditions()
        # OR wraps into a single condition
        assert len(conditions) == 1

    def test_not_logic_wraps_in_single_condition(self) -> None:
        f = KeyPairFilterGQL(
            NOT=[
                KeyPairFilterGQL(is_active=False),
            ]
        )
        conditions = f.build_conditions()
        assert len(conditions) == 1


class TestKeyPairOrderByGQL:
    """Tests for KeyPairOrderByGQL.to_query_order()."""

    def test_created_at_ascending(self) -> None:
        order = KeyPairOrderByGQL(
            field=KeyPairOrderFieldGQL.CREATED_AT,
            direction=OrderDirection.ASC,
        )
        result = order.to_query_order()
        sql = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "created_at" in sql
        assert "ASC" in sql.upper()

    def test_created_at_descending(self) -> None:
        order = KeyPairOrderByGQL(
            field=KeyPairOrderFieldGQL.CREATED_AT,
            direction=OrderDirection.DESC,
        )
        result = order.to_query_order()
        sql = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "created_at" in sql
        assert "DESC" in sql.upper()

    def test_access_key_ascending(self) -> None:
        order = KeyPairOrderByGQL(
            field=KeyPairOrderFieldGQL.ACCESS_KEY,
            direction=OrderDirection.ASC,
        )
        result = order.to_query_order()
        sql = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "access_key" in sql
        assert "ASC" in sql.upper()

    def test_access_key_descending(self) -> None:
        order = KeyPairOrderByGQL(
            field=KeyPairOrderFieldGQL.ACCESS_KEY,
            direction=OrderDirection.DESC,
        )
        result = order.to_query_order()
        sql = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "access_key" in sql
        assert "DESC" in sql.upper()


class TestMyKeypairGQL:
    """Tests for MyKeypairGQL node type."""

    def _make_data(
        self,
        access_key: str = "TESTKEY12345678901",
        is_active: bool = True,
        is_admin: bool = False,
        rate_limit: int = 1000,
        resource_policy: str = "default",
    ) -> MyKeypairData:
        return MyKeypairData(
            access_key=AccessKey(access_key),
            is_active=is_active,
            is_admin=is_admin,
            created_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            last_used=datetime(2025, 3, 1, 8, 30, 0, tzinfo=UTC),
            resource_policy=resource_policy,
            rate_limit=rate_limit,
        )

    def test_from_data_maps_all_seven_fields(self) -> None:
        """from_data() correctly maps all 7 fields from MyKeypairData."""
        data = self._make_data(
            access_key="MYACCESS12345678",
            is_active=False,
            is_admin=True,
            rate_limit=2000,
            resource_policy="premium",
        )

        node = MyKeypairGQL.from_data(data)

        assert node.access_key == "MYACCESS12345678"
        assert node.is_active is False
        assert node.is_admin is True
        assert node.created_at == datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert node.last_used == datetime(2025, 3, 1, 8, 30, 0, tzinfo=UTC)
        assert node.resource_policy == "premium"
        assert node.rate_limit == 2000

    def test_from_data_with_none_timestamps(self) -> None:
        """from_data() handles None for created_at and last_used."""
        data = MyKeypairData(
            access_key=AccessKey("NULLTIMESTAMPKEY"),
            is_active=True,
            is_admin=False,
            created_at=None,
            last_used=None,
            resource_policy="default",
            rate_limit=500,
        )

        node = MyKeypairGQL.from_data(data)

        assert node.created_at is None
        assert node.last_used is None

    def test_secret_key_is_absent_from_schema(self) -> None:
        """MyKeypairGQL does NOT expose secret_key at the schema level."""
        # Verify via dir() — no secret_key attribute exists at all
        type_fields = [
            field_name
            for field_name in dir(MyKeypairGQL)
            if not field_name.startswith("_") and field_name == "secret_key"
        ]
        assert "secret_key" not in type_fields

        # Also verify via class annotations accumulated from the MRO
        annotations: dict[str, object] = {}
        for klass in MyKeypairGQL.__mro__:
            if hasattr(klass, "__annotations__"):
                annotations.update(klass.__annotations__)
        assert "secret_key" not in annotations

    def test_my_keypair_gql_has_expected_fields(self) -> None:
        """MyKeypairGQL exposes the expected 7 fields."""
        data = self._make_data()
        node = MyKeypairGQL.from_data(data)

        # Check all 7 required fields exist
        assert hasattr(node, "access_key")
        assert hasattr(node, "is_active")
        assert hasattr(node, "is_admin")
        assert hasattr(node, "created_at")
        assert hasattr(node, "last_used")
        assert hasattr(node, "resource_policy")
        assert hasattr(node, "rate_limit")
        # secret_key must NOT be present
        assert not hasattr(node, "secret_key")


class TestMyKeypairConnection:
    """Tests for MyKeypairConnection."""

    def test_count_field_is_set(self) -> None:
        """MyKeypairConnection stores the count field correctly."""
        connection = MyKeypairConnection(
            edges=[],
            page_info=PageInfo(
                has_next_page=False,
                has_previous_page=False,
                start_cursor=None,
                end_cursor=None,
            ),
            count=42,
        )

        assert connection.count == 42

    def test_count_reflects_total_not_page_size(self) -> None:
        """count represents total matching records, not the page size."""
        data = MyKeypairData(
            access_key=AccessKey("TESTKEY12345678901"),
            is_active=True,
            is_admin=False,
            created_at=None,
            last_used=None,
            resource_policy="default",
            rate_limit=1000,
        )
        node = MyKeypairGQL.from_data(data)
        edges = [MyKeypairEdge(node=node, cursor="cursor1")]

        connection = MyKeypairConnection(
            edges=edges,
            page_info=PageInfo(
                has_next_page=True,
                has_previous_page=False,
                start_cursor="cursor1",
                end_cursor="cursor1",
            ),
            count=100,  # Total count, not page size
        )

        assert len(connection.edges) == 1
        assert connection.count == 100
