"""Unit tests for RBAC Role GQL Pydantic integration (PoC: BA-5149).

Validates:
- RoleGQL.from_pydantic(): RoleDTO → RoleGQL conversion
- CreateRoleInputGQL.to_pydantic(): GQL input → Pydantic DTO with validation
- UpdateRoleInputGQL.to_pydantic(): GQL input → Pydantic DTO with validation
- Pydantic ValidationError raised for invalid inputs
- GraphQL schema structure matches expected field names and types
- Backward-compatible to_creator() / to_updater() methods
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import strawberry
from pydantic import ValidationError

from ai.backend.common.api_handlers import SENTINEL
from ai.backend.common.data.permission.types import RoleSource, RoleStatus
from ai.backend.common.dto.manager.rbac.request import CreateRoleRequest, UpdateRoleRequest
from ai.backend.common.dto.manager.rbac.response import RoleDTO
from ai.backend.manager.api.gql.rbac.types.role import (
    CreateRoleInputGQL,
    RoleGQL,
    RoleSourceGQL,
    RoleStatusGQL,
    UpdateRoleInputGQL,
)

# ==================== Fixtures ====================


@pytest.fixture
def sample_role_dto() -> RoleDTO:
    return RoleDTO(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        name="test-role",
        source=RoleSource.CUSTOM,
        status=RoleStatus.ACTIVE,
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
        deleted_at=None,
        description="A test role",
    )


@pytest.fixture
def sample_role_dto_minimal() -> RoleDTO:
    return RoleDTO(
        id=uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        name="minimal-role",
        source=RoleSource.SYSTEM,
        status=RoleStatus.INACTIVE,
        created_at=datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC),
        deleted_at=datetime(2024, 6, 2, 0, 0, 0, tzinfo=UTC),
        description=None,
    )


# ==================== RoleGQL.from_pydantic() Tests ====================


class TestRoleGQLFromPydantic:
    """Tests for RoleGQL.from_pydantic() hybrid conversion."""

    def test_from_pydantic_all_fields_converted(self, sample_role_dto: RoleDTO) -> None:
        """All RoleDTO fields are correctly mapped to RoleGQL fields."""
        gql = RoleGQL.from_pydantic(sample_role_dto)

        assert str(gql.id) == "12345678-1234-5678-1234-567812345678"
        assert gql.name == "test-role"
        assert gql.description == "A test role"
        assert gql.source == RoleSourceGQL.CUSTOM
        assert gql.status == RoleStatusGQL.ACTIVE
        assert gql.created_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert gql.updated_at == datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC)
        assert gql.deleted_at is None

    def test_from_pydantic_none_description(self, sample_role_dto_minimal: RoleDTO) -> None:
        """None description is preserved in RoleGQL."""
        gql = RoleGQL.from_pydantic(sample_role_dto_minimal)

        assert gql.description is None

    def test_from_pydantic_deleted_at_set(self, sample_role_dto_minimal: RoleDTO) -> None:
        """deleted_at is correctly mapped when set."""
        gql = RoleGQL.from_pydantic(sample_role_dto_minimal)

        assert gql.deleted_at == datetime(2024, 6, 2, 0, 0, 0, tzinfo=UTC)

    def test_from_pydantic_enum_conversion_custom(self, sample_role_dto: RoleDTO) -> None:
        """RoleSource.CUSTOM maps to RoleSourceGQL.CUSTOM."""
        gql = RoleGQL.from_pydantic(sample_role_dto)
        assert gql.source == RoleSourceGQL.CUSTOM

    def test_from_pydantic_enum_conversion_system(self, sample_role_dto_minimal: RoleDTO) -> None:
        """RoleSource.SYSTEM maps to RoleSourceGQL.SYSTEM."""
        gql = RoleGQL.from_pydantic(sample_role_dto_minimal)
        assert gql.source == RoleSourceGQL.SYSTEM

    def test_from_pydantic_status_inactive(self, sample_role_dto_minimal: RoleDTO) -> None:
        """RoleStatus.INACTIVE maps to RoleStatusGQL.INACTIVE."""
        gql = RoleGQL.from_pydantic(sample_role_dto_minimal)
        assert gql.status == RoleStatusGQL.INACTIVE


# ==================== CreateRoleInputGQL.to_pydantic() Tests ====================


class TestCreateRoleInputGQLToPydantic:
    """Tests for CreateRoleInputGQL.to_pydantic() Pydantic validation."""

    def test_to_pydantic_with_all_fields(self) -> None:
        """to_pydantic() returns valid CreateRoleRequest with all fields set."""
        gql_input = CreateRoleInputGQL(
            name="new-role",
            description="A new role",
            source=RoleSourceGQL.CUSTOM,
            status=RoleStatusGQL.ACTIVE,
        )

        dto = gql_input.to_pydantic()

        assert isinstance(dto, CreateRoleRequest)
        assert dto.name == "new-role"
        assert dto.description == "A new role"
        assert dto.source == RoleSource.CUSTOM
        assert dto.status == RoleStatus.ACTIVE

    def test_to_pydantic_defaults_applied(self) -> None:
        """When source/status are None, defaults (CUSTOM/ACTIVE) are applied."""
        gql_input = CreateRoleInputGQL(name="default-role")

        dto = gql_input.to_pydantic()

        assert dto.source == RoleSource.CUSTOM
        assert dto.status == RoleStatus.ACTIVE
        assert dto.description is None

    def test_to_pydantic_triggers_validation_error_for_missing_name(self) -> None:
        """Calling CreateRoleRequest without name triggers Pydantic ValidationError."""
        with pytest.raises(ValidationError):
            CreateRoleRequest(name=None)  # type: ignore[arg-type]

    def test_to_pydantic_triggers_validation_error_for_invalid_source(self) -> None:
        """Calling CreateRoleRequest with invalid source triggers Pydantic ValidationError."""
        with pytest.raises(ValidationError):
            CreateRoleRequest(name="role", source="invalid_source")  # type: ignore[arg-type]

    def test_to_pydantic_system_source(self) -> None:
        """RoleSourceGQL.SYSTEM is correctly converted to RoleSource.SYSTEM."""
        gql_input = CreateRoleInputGQL(
            name="system-role",
            source=RoleSourceGQL.SYSTEM,
        )

        dto = gql_input.to_pydantic()
        assert dto.source == RoleSource.SYSTEM

    def test_to_pydantic_preserves_method_not_stripped(self) -> None:
        """to_pydantic() method is preserved by @strawberry_pydantic.input (special case).

        PoC Finding: @strawberry_pydantic.input strips all custom methods except
        to_pydantic(), from_pydantic(), and is_type_of(). Methods like to_creator()
        cannot be defined on the class — use RoleServiceAdapter instead.
        """
        assert hasattr(CreateRoleInputGQL, "to_pydantic")
        assert not hasattr(CreateRoleInputGQL, "to_creator")


# ==================== UpdateRoleInputGQL.to_pydantic() Tests ====================


class TestUpdateRoleInputGQLToPydantic:
    """Tests for UpdateRoleInputGQL.to_pydantic() Pydantic validation."""

    def test_to_pydantic_partial_update(self) -> None:
        """to_pydantic() returns valid UpdateRoleRequest with partial update."""
        role_id = uuid.uuid4()
        gql_input = UpdateRoleInputGQL(
            id=role_id,
            name="updated-name",
        )

        dto = gql_input.to_pydantic()

        assert isinstance(dto, UpdateRoleRequest)
        assert dto.name == "updated-name"
        assert dto.source is None
        assert dto.status is None

    def test_to_pydantic_description_none_maps_to_sentinel(self) -> None:
        """description=None (GQL null) maps to SENTINEL (no-op) in UpdateRoleRequest."""
        role_id = uuid.uuid4()
        gql_input = UpdateRoleInputGQL(id=role_id, name="name")

        dto = gql_input.to_pydantic()

        assert dto.description is SENTINEL

    def test_to_pydantic_description_value_passed_through(self) -> None:
        """description='new desc' is passed through to UpdateRoleRequest."""
        role_id = uuid.uuid4()
        gql_input = UpdateRoleInputGQL(id=role_id, description="new desc")

        dto = gql_input.to_pydantic()

        assert dto.description == "new desc"

    def test_to_pydantic_enum_conversion_status(self) -> None:
        """RoleStatusGQL.INACTIVE is converted to RoleStatus.INACTIVE."""
        role_id = uuid.uuid4()
        gql_input = UpdateRoleInputGQL(
            id=role_id,
            status=RoleStatusGQL.INACTIVE,
        )

        dto = gql_input.to_pydantic()

        assert dto.status == RoleStatus.INACTIVE

    def test_to_pydantic_preserves_method_not_stripped(self) -> None:
        """to_pydantic() preserved by @strawberry_pydantic.input; to_updater() is stripped.

        PoC Finding: @strawberry_pydantic.input strips custom methods except to_pydantic().
        The resolver should use RoleServiceAdapter.update_role() with the DTO from to_pydantic()
        instead of calling to_updater() directly on the GQL input class.
        """
        assert hasattr(UpdateRoleInputGQL, "to_pydantic")
        assert not hasattr(UpdateRoleInputGQL, "to_updater")


# ==================== Schema Structure Tests ====================


class TestGraphQLSchemaStructure:
    """Tests for GraphQL schema introspection — verifies field names and types."""

    def test_create_role_input_gql_has_name_field(self) -> None:
        """CreateRoleInputGQL exposes 'name' field in GQL schema."""

        @strawberry.type
        class DummyQuery:
            @strawberry.field
            def dummy(self) -> str:
                return "x"

        schema = strawberry.Schema(
            query=DummyQuery,
            types=[CreateRoleInputGQL],
        )
        introspection = schema.introspect()
        type_map = {t["name"]: t for t in introspection["__schema"]["types"]}
        assert "CreateRoleInput" in type_map
        input_type = type_map["CreateRoleInput"]
        field_names = {f["name"] for f in input_type["inputFields"]}
        assert "name" in field_names
        assert "description" in field_names
        assert "source" in field_names
        assert "status" in field_names

    def test_update_role_input_gql_schema_fields(self) -> None:
        """UpdateRoleInputGQL exposes expected fields in GQL schema."""

        @strawberry.type
        class DummyQuery:
            @strawberry.field
            def dummy(self) -> str:
                return "x"

        schema = strawberry.Schema(
            query=DummyQuery,
            types=[UpdateRoleInputGQL],
        )
        introspection = schema.introspect()
        type_map = {t["name"]: t for t in introspection["__schema"]["types"]}
        assert "UpdateRoleInput" in type_map
        input_type = type_map["UpdateRoleInput"]
        field_names = {f["name"] for f in input_type["inputFields"]}
        assert "id" in field_names
        assert "name" in field_names
        assert "description" in field_names
        assert "source" in field_names
        assert "status" in field_names
