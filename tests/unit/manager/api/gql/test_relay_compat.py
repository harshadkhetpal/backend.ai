"""Tests for the Relay NodeID compatibility layer (relay_compat module)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Any, Self, cast
from uuid import UUID

import pytest
from graphql_relay.utils import base64, unbase64
from pydantic import BaseModel, Field

from ai.backend.common.exception import InvalidAPIParameters
from ai.backend.common.types import NodeUUID
from ai.backend.manager.api.gql.relay_compat import (
    NodeGQLMixin,
    _pydantic_to_gql_registry,
    node_id_to_uuid,
    pydantic_node_type,
    uuid_to_node_id,
)

_TEST_UUID = UUID("550e8400-e29b-41d4-a716-446655440000")


# ---------------------------------------------------------------------------
# Demo Pydantic DTOs
# ---------------------------------------------------------------------------


class FlatDTO(BaseModel):
    """Simple flat DTO with one required NodeUUID and one plain UUID field."""

    id: NodeUUID = Field(description="Node UUID")
    ref_id: UUID = Field(description="Regular UUID — must NOT be encoded as NodeID")
    name: str


class OptionalNodeDTO(BaseModel):
    """DTO with Optional[NodeUUID] to verify None handling."""

    id: NodeUUID
    opt_id: NodeUUID | None = None


class NestedChildDTO(BaseModel):
    """Nested model whose id is a NodeUUID."""

    id: NodeUUID
    label: str


class NestedParentDTO(BaseModel):
    """Parent model referencing a nested DTO."""

    id: NodeUUID
    child: NestedChildDTO


# ---------------------------------------------------------------------------
# Demo GQL types (created once at module level)
# Decorated classes inherit from NodeGQLMixin so that static type-checkers
# can resolve from_pydantic() and to_pydantic().
# ---------------------------------------------------------------------------


@pydantic_node_type(model=FlatDTO, name="FlatGQL")
class FlatGQL(NodeGQLMixin):
    pass


@pydantic_node_type(model=OptionalNodeDTO, name="OptionalNodeGQL")
class OptionalNodeGQL(NodeGQLMixin):
    pass


@pydantic_node_type(model=NestedChildDTO, name="NestedChildGQL")
class NestedChildGQL(NodeGQLMixin):
    pass


@pydantic_node_type(model=NestedParentDTO, name="NestedParentGQL")
class NestedParentGQL(NodeGQLMixin):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_global_id(global_id: str) -> tuple[str, str]:
    raw = unbase64(global_id)
    type_name, _, local_id = raw.partition(":")
    return type_name, local_id


# ---------------------------------------------------------------------------
# uuid_to_node_id
# ---------------------------------------------------------------------------


class TestUuidToNodeId:
    def test_encodes_type_and_uuid(self) -> None:
        result = uuid_to_node_id("UserGQL", _TEST_UUID)
        assert isinstance(result, str)
        type_name, local_id = _decode_global_id(result)
        assert type_name == "UserGQL"
        assert local_id == str(_TEST_UUID)

    def test_base64_encoded(self) -> None:
        result = uuid_to_node_id("X", _TEST_UUID)
        assert result == base64(f"X:{_TEST_UUID}")


# ---------------------------------------------------------------------------
# node_id_to_uuid
# ---------------------------------------------------------------------------


class TestNodeIdToUuid:
    def test_roundtrip(self) -> None:
        global_id = uuid_to_node_id("UserGQL", _TEST_UUID)
        recovered = node_id_to_uuid(global_id)
        assert recovered == _TEST_UUID

    def test_invalid_global_id_raises(self) -> None:
        with pytest.raises(InvalidAPIParameters):
            node_id_to_uuid("not-valid-base64!!!")

    def test_malformed_uuid_raises(self) -> None:
        # Valid base64 but UUID part is not a valid UUID
        bad = base64("TypeName:not-a-uuid")
        with pytest.raises(InvalidAPIParameters):
            node_id_to_uuid(bad)


# ---------------------------------------------------------------------------
# from_pydantic — UUID → NodeID conversion
# ---------------------------------------------------------------------------


class TestFromPydanticUuidToNodeId:
    def test_node_uuid_field_encoded_as_global_id(self) -> None:
        dto = FlatDTO(id=_TEST_UUID, ref_id=_TEST_UUID, name="alice")
        gql = FlatGQL.from_pydantic(dto)
        type_name, local_id = _decode_global_id(str(gql.id))
        assert type_name == "FlatGQL"
        assert local_id == str(_TEST_UUID)

    def test_plain_uuid_field_not_encoded(self) -> None:
        dto = FlatDTO(id=_TEST_UUID, ref_id=_TEST_UUID, name="alice")
        gql = FlatGQL.from_pydantic(dto)
        # ref_id is a plain UUID — it must not be converted to a Global ID
        assert gql.ref_id == _TEST_UUID
        assert isinstance(gql.ref_id, UUID)

    def test_optional_node_uuid_with_value(self) -> None:
        dto = OptionalNodeDTO(id=_TEST_UUID, opt_id=_TEST_UUID)
        gql = OptionalNodeGQL.from_pydantic(dto)
        assert gql.opt_id is not None
        type_name, local_id = _decode_global_id(str(gql.opt_id))
        assert type_name == "OptionalNodeGQL"
        assert local_id == str(_TEST_UUID)

    def test_optional_node_uuid_none_stays_none(self) -> None:
        dto = OptionalNodeDTO(id=_TEST_UUID, opt_id=None)
        gql = OptionalNodeGQL.from_pydantic(dto)
        assert gql.opt_id is None

    def test_non_uuid_fields_preserved(self) -> None:
        dto = FlatDTO(id=_TEST_UUID, ref_id=_TEST_UUID, name="bob")
        gql = FlatGQL.from_pydantic(dto)
        assert gql.name == "bob"


# ---------------------------------------------------------------------------
# to_pydantic — NodeID → UUID back-conversion
# ---------------------------------------------------------------------------


class TestToPydanticNodeIdToUuid:
    def test_roundtrip_uuid(self) -> None:
        dto = FlatDTO(id=_TEST_UUID, ref_id=_TEST_UUID, name="alice")
        gql = FlatGQL.from_pydantic(dto)
        recovered = gql.to_pydantic()
        assert recovered.id == _TEST_UUID

    def test_optional_node_uuid_restored(self) -> None:
        dto = OptionalNodeDTO(id=_TEST_UUID, opt_id=_TEST_UUID)
        gql = OptionalNodeGQL.from_pydantic(dto)
        recovered = gql.to_pydantic()
        assert recovered.opt_id == _TEST_UUID

    def test_optional_none_preserved(self) -> None:
        dto = OptionalNodeDTO(id=_TEST_UUID, opt_id=None)
        gql = OptionalNodeGQL.from_pydantic(dto)
        recovered = gql.to_pydantic()
        assert recovered.opt_id is None

    def test_invalid_global_id_raises(self) -> None:
        # Build a valid GQL instance, then replace opt_id with a malformed value
        gql: Any = OptionalNodeGQL.from_pydantic(OptionalNodeDTO(id=_TEST_UUID, opt_id=_TEST_UUID))
        gql_bad = dataclasses.replace(gql, opt_id="not-valid-base64!!!")
        with pytest.raises(InvalidAPIParameters):
            gql_bad.to_pydantic()


# ---------------------------------------------------------------------------
# Reusability — arbitrary Pydantic DTOs
# ---------------------------------------------------------------------------


class TestReusability:
    def test_can_apply_to_arbitrary_model(self) -> None:
        class ArbitraryDTO(BaseModel):
            id: NodeUUID
            value: int

        @pydantic_node_type(model=ArbitraryDTO, name="ArbitraryGQL")
        class ArbitraryGQL(NodeGQLMixin):
            pass

        uuid = UUID("12345678-1234-5678-1234-567812345678")
        dto = ArbitraryDTO(id=uuid, value=42)
        gql = ArbitraryGQL.from_pydantic(dto)
        _, local_id = _decode_global_id(str(gql.id))
        assert local_id == str(uuid)
        assert gql.value == 42

    def test_multiple_independent_types(self) -> None:
        """Two different DTOs → two independent GQL types with correct names."""

        class ADTO(BaseModel):
            id: NodeUUID

        class BGQL_DTO(BaseModel):
            id: NodeUUID

        @pydantic_node_type(model=ADTO, name="AGQL")
        class AGQL(NodeGQLMixin):
            pass

        @pydantic_node_type(model=BGQL_DTO, name="BGQL")
        class BGQL(NodeGQLMixin):
            pass

        a_uuid = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        b_uuid = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        a_gql = AGQL.from_pydantic(ADTO(id=a_uuid))
        b_gql = BGQL.from_pydantic(BGQL_DTO(id=b_uuid))

        a_type, a_local = _decode_global_id(str(a_gql.id))
        b_type, b_local = _decode_global_id(str(b_gql.id))

        assert a_type == "AGQL"
        assert b_type == "BGQL"
        assert a_local == str(a_uuid)
        assert b_local == str(b_uuid)


# ---------------------------------------------------------------------------
# Nested model recursive conversion
# ---------------------------------------------------------------------------


class TestNestedModelConversion:
    def test_nested_node_uuid_converted(self) -> None:
        child_uuid = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        parent_uuid = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        child_dto = NestedChildDTO(id=child_uuid, label="child")
        parent_dto = NestedParentDTO(id=parent_uuid, child=child_dto)

        gql = NestedParentGQL.from_pydantic(parent_dto)

        # Parent id is encoded
        p_type, p_local = _decode_global_id(str(gql.id))
        assert p_type == "NestedParentGQL"
        assert p_local == str(parent_uuid)

        # Nested child id is also encoded
        c_type, c_local = _decode_global_id(str(gql.child.id))
        assert c_type == "NestedChildGQL"
        assert c_local == str(child_uuid)

    def test_registry_populated(self) -> None:
        """pydantic_node_type registers models in the global registry."""
        assert FlatDTO in _pydantic_to_gql_registry
        assert NestedChildDTO in _pydantic_to_gql_registry
        assert NestedParentDTO in _pydantic_to_gql_registry


# ---------------------------------------------------------------------------
# Relay Node resolve_nodes integration
# ---------------------------------------------------------------------------


class TestRelayNodeIntegration:
    def test_resolve_nodes_can_be_overridden(self) -> None:
        """GQL type produced by pydantic_node_type accepts a resolve_nodes override."""

        class MyDTO(BaseModel):
            id: NodeUUID

        @pydantic_node_type(model=MyDTO, name="MyGQL")
        class MyGQL(NodeGQLMixin):
            @classmethod
            async def resolve_nodes(
                cls,
                *,
                info: object,
                node_ids: Iterable[str],
                required: bool = False,
            ) -> Iterable[Self | None]:
                return [None for _ in node_ids]

        # Verify resolve_nodes is present and is a classmethod
        assert callable(MyGQL.resolve_nodes)


# ---------------------------------------------------------------------------
# Adapter sharing pattern
# ---------------------------------------------------------------------------
#
# Demonstrates the recommended flow for GQL resolvers:
#   Output: DataLayer type → SharedAdapter.to_dto() → DTO → from_pydantic() → GQL
#   Input:  GQL object  → to_pydantic()             → DTO → SharedAdapter.action()
# ---------------------------------------------------------------------------


class ProjectDataStub:
    """Minimal stand-in for a Data Layer type (replaces a frozen dataclass)."""

    def __init__(self, id: UUID, title: str) -> None:
        self.id = id
        self.title = title


class ProjectDTO(BaseModel):
    """Demo DTO using NodeUUID to participate in the relay_compat pattern."""

    id: NodeUUID = Field(description="Project UUID")
    title: str


@pydantic_node_type(model=ProjectDTO, name="ProjectDemoGQL")
class ProjectDemoGQL(NodeGQLMixin):
    pass


class SharedProjectAdapter:
    """Shared adapter callable from both REST and GQL resolvers.

    Demonstrates the converter pattern:
    * ``to_dto``  — Data Layer type → Pydantic DTO (shared across REST + GQL)
    * ``from_gql`` — GQL object → Pydantic DTO via ``to_pydantic()``
    """

    def to_dto(self, data: ProjectDataStub) -> ProjectDTO:
        return ProjectDTO(id=data.id, title=data.title)

    def from_gql(self, gql_obj: NodeGQLMixin) -> ProjectDTO:
        return cast(ProjectDTO, gql_obj.to_pydantic())


class TestAdapterSharingPattern:
    """Verify that the pydantic_node_type pattern integrates with a shared adapter."""

    def test_output_flow_data_to_gql(self) -> None:
        """Output flow: Data → adapter.to_dto() → from_pydantic() → GQL object."""
        project_uuid = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        data = ProjectDataStub(id=project_uuid, title="My Project")
        adapter = SharedProjectAdapter()

        dto = adapter.to_dto(data)
        gql = ProjectDemoGQL.from_pydantic(dto)

        # GQL resolver does NOT call data layer directly — it goes through adapter
        p_type, p_local = _decode_global_id(str(gql.id))
        assert p_type == "ProjectDemoGQL"
        assert p_local == str(project_uuid)
        assert gql.title == "My Project"

    def test_input_flow_gql_to_adapter(self) -> None:
        """Input flow: GQL object → to_pydantic() → adapter (DTO) → service."""
        project_uuid = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        data = ProjectDataStub(id=project_uuid, title="Original")
        adapter = SharedProjectAdapter()

        # Simulate a round-trip: data comes in, gets converted to GQL, then back
        dto = adapter.to_dto(data)
        gql = ProjectDemoGQL.from_pydantic(dto)

        # A mutation handler would call to_pydantic() and pass the DTO to the service
        recovered_dto = adapter.from_gql(gql)
        assert recovered_dto.id == project_uuid
        assert recovered_dto.title == "Original"
