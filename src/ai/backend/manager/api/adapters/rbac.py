"""Shared RBAC service adapter for GQL resolvers and REST handlers.

Both GQL resolvers and REST handlers call this adapter instead of invoking
Processors directly. The adapter accepts Pydantic DTOs and returns Pydantic DTOs,
keeping transport-layer code (GQL types, HTTP request/response) out of service logic.

Flow:
  GQL resolver  → to_pydantic() → RoleServiceAdapter → Processor → from_pydantic()
  REST handler  →               → RoleServiceAdapter → Processor
"""

from __future__ import annotations

from uuid import UUID

from ai.backend.common.api_handlers import SENTINEL
from ai.backend.common.dto.manager.rbac.request import CreateRoleRequest, UpdateRoleRequest
from ai.backend.common.dto.manager.rbac.response import RoleDTO
from ai.backend.manager.data.permission.role import RoleData, RoleDetailData
from ai.backend.manager.models.rbac_models.role import RoleRow
from ai.backend.manager.repositories.base import Creator, Updater
from ai.backend.manager.repositories.permission_controller.creators import RoleCreatorSpec
from ai.backend.manager.repositories.permission_controller.updaters import RoleUpdaterSpec
from ai.backend.manager.services.permission_contoller.actions.create_role import CreateRoleAction
from ai.backend.manager.services.permission_contoller.actions.update_role import UpdateRoleAction
from ai.backend.manager.services.permission_contoller.processors import (
    PermissionControllerProcessors,
)
from ai.backend.manager.types import OptionalState, TriState

__all__ = ("RoleServiceAdapter",)


class RoleServiceAdapter:
    """Shared adapter for role CRUD operations.

    Accepts Pydantic DTOs and returns Pydantic DTOs, encapsulating
    the Processor call and data-layer conversion in one place.
    Both GQL resolvers and REST handlers instantiate this adapter.
    """

    def __init__(self, processors: PermissionControllerProcessors) -> None:
        self._processors = processors

    async def create_role(self, request: CreateRoleRequest) -> RoleDTO:
        """Create a role from a validated Pydantic request DTO."""
        creator = Creator(
            spec=RoleCreatorSpec(
                name=request.name,
                source=request.source,
                status=request.status,
                description=request.description,
            )
        )
        action_result = await self._processors.create_role.wait_for_complete(
            CreateRoleAction(creator=creator)
        )
        return self._to_dto(action_result.data)

    async def update_role(self, role_id: UUID, request: UpdateRoleRequest) -> RoleDTO:
        """Update a role from a validated Pydantic request DTO."""
        updater = self._build_updater(role_id, request)
        action_result = await self._processors.update_role.wait_for_complete(
            UpdateRoleAction(updater=updater)
        )
        return self._to_dto(action_result.data)

    def _build_updater(self, role_id: UUID, request: UpdateRoleRequest) -> Updater[RoleRow]:
        name: OptionalState[str] = (
            OptionalState.update(request.name) if request.name is not None else OptionalState.nop()
        )
        source = (
            OptionalState.update(request.source)
            if request.source is not None
            else OptionalState.nop()
        )
        status = (
            OptionalState.update(request.status)
            if request.status is not None
            else OptionalState.nop()
        )
        description: TriState[str] = (
            TriState.nop()
            if request.description is SENTINEL
            else TriState.nullify()
            if request.description is None
            else TriState.update(str(request.description))
        )
        spec = RoleUpdaterSpec(
            name=name,
            source=source,
            status=status,
            description=description,
        )
        return Updater(spec=spec, pk_value=role_id)

    def _to_dto(self, data: RoleData | RoleDetailData) -> RoleDTO:
        return RoleDTO(
            id=data.id,
            name=data.name,
            source=data.source,
            status=data.status,
            created_at=data.created_at,
            updated_at=data.updated_at,
            deleted_at=data.deleted_at,
            description=data.description,
        )
