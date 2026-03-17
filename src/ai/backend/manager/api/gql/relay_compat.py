"""Relay NodeID compatibility layer for Pydantic UUID fields in GraphQL types.

This module provides utilities for bridging Pydantic DTOs and Strawberry Relay
Node types, with automatic UUID ↔ Relay Global ID conversion for fields
annotated with ``NodeUUID``.

Usage::

    from ai.backend.common.types import NodeUUID
    from ai.backend.manager.api.gql.relay_compat import pydantic_node_type

    class UserDTO(BaseModel):
        id: NodeUUID
        name: str

    @pydantic_node_type(model=UserDTO)
    class UserDemoGQL:
        pass  # all fields auto-mapped; NodeUUID → NodeID[str]

    # Convert DTO → GQL
    gql_obj = UserDemoGQL.from_pydantic(user_dto)
    # Convert GQL → DTO
    user_dto = gql_obj.to_pydantic()
"""

from __future__ import annotations

import dataclasses
import types as pytypes
from collections.abc import Callable
from typing import (
    Annotated,
    Any,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

import strawberry
from graphql_relay.utils import base64, unbase64
from pydantic import BaseModel
from pydantic_core import PydanticUndefinedType
from strawberry.relay import Node, NodeID

from ai.backend.common.exception import InvalidAPIParameters
from ai.backend.common.types import NodeIDMarker

__all__ = (
    "NodeGQLMixin",
    "node_id_to_uuid",
    "pydantic_node_type",
    "uuid_to_node_id",
)

_ClsT = TypeVar("_ClsT")

# Global registry: Pydantic model class → Strawberry GQL type created by pydantic_node_type.
# Used for automatic nested-model conversion inside from_pydantic().
_pydantic_to_gql_registry: dict[type[BaseModel], type[NodeGQLMixin]] = {}


class NodeGQLMixin:
    """Mixin that exposes ``from_pydantic`` / ``to_pydantic`` on GQL Node types.

    Concrete implementations are injected by :func:`pydantic_node_type`.
    This class exists so that static type-checkers can resolve the methods
    on the decorated class.
    """

    @classmethod
    def from_pydantic(cls, instance: BaseModel) -> Any:
        """Convert a Pydantic DTO to this GQL type (overridden by pydantic_node_type)."""
        raise NotImplementedError

    def to_pydantic(self) -> BaseModel:
        """Convert this GQL type instance to a Pydantic DTO (overridden by pydantic_node_type)."""
        raise NotImplementedError


def uuid_to_node_id(type_name: str, value: UUID) -> str:
    """Encode a UUID into a Relay Global ID string (base64 ``TypeName:uuid``)."""
    return base64(f"{type_name}:{value}")


def node_id_to_uuid(global_id: str) -> UUID:
    """Decode a Relay Global ID string and return the embedded UUID.

    Raises:
        InvalidAPIParameters: when *global_id* is not a valid Relay Global ID.
    """
    try:
        raw = unbase64(global_id)
        _, _, id_part = raw.partition(":")
        return UUID(id_part)
    except (ValueError, AttributeError) as exc:
        raise InvalidAPIParameters(f"Invalid Relay Global ID format: {global_id!r}") from exc


def _check_node_uuid(annotation: Any) -> tuple[bool, bool]:
    """Inspect a type annotation, returning ``(is_node_uuid, is_optional)``.

    *is_node_uuid* is True when the annotation is ``NodeUUID``
    (``Annotated[UUID, NodeIDMarker()]``) or ``Optional[NodeUUID]``.
    *is_optional* is True for the ``Optional[NodeUUID]`` case.
    """
    # Direct: Annotated[UUID, NodeIDMarker()]
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if args[0] is UUID and any(isinstance(m, NodeIDMarker) for m in args[1:]):
            return True, False

    # Optional[NodeUUID] → Union[Annotated[UUID, NodeIDMarker()], None]
    origin = get_origin(annotation)
    if origin is Union or isinstance(annotation, pytypes.UnionType):
        inner_args = get_args(annotation)
        non_none = [a for a in inner_args if a is not type(None)]
        if len(non_none) == 1:
            is_node, _ = _check_node_uuid(non_none[0])
            if is_node:
                return True, True

    return False, False


def pydantic_node_type(
    model: type[BaseModel],
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[type[_ClsT]], type[_ClsT]]:
    """Decorator factory that creates a Strawberry Relay Node type from a Pydantic model.

    The decorated class **must inherit from** :class:`NodeGQLMixin` so that
    static type-checkers can resolve ``from_pydantic`` and ``to_pydantic``:

    .. code-block:: python

        @pydantic_node_type(model=UserDTO, name="UserV2Demo")
        class UserV2DemoGQL(NodeGQLMixin):
            pass

    At runtime the decorated class is replaced by a new ``@strawberry.type``
    dataclass that inherits from both :class:`~strawberry.relay.Node` and
    :class:`NodeGQLMixin`.  All fields are inferred automatically from *model*;
    ``NodeUUID`` fields are mapped to ``NodeID[str]`` in the GraphQL schema.

    The resulting class provides two conversion helpers:

    * ``from_pydantic(instance)`` — classmethod; converts a DTO instance to this
      GQL type, encoding ``NodeUUID`` values as Relay Global IDs.
    * ``to_pydantic()`` — instance method; converts back to the Pydantic DTO,
      decoding Relay Global IDs back to UUIDs.

    The mapping is registered globally so that nested Pydantic models (whose
    own GQL type was also created with ``pydantic_node_type``) are converted
    automatically during ``from_pydantic``.

    Args:
        model: Pydantic ``BaseModel`` subclass to derive fields from.
        name: Override the GraphQL type name (defaults to the decorated class name).
        description: Optional GraphQL type description.
    """

    def decorator(cls: type[_ClsT]) -> type[_ClsT]:
        type_name = name or cls.__name__
        hints = get_type_hints(model, include_extras=True)

        # --- Build field list ------------------------------------------------
        # Strawberry (dataclass) requires fields without defaults before those
        # with defaults, so we collect them in two buckets.
        node_uuid_fields: dict[str, bool] = {}  # field_name → is_optional
        required_fields: list[tuple[str, Any, dataclasses.Field[Any]]] = []
        optional_fields: list[tuple[str, Any, dataclasses.Field[Any]]] = []

        for field_name, field_type in hints.items():
            is_node, is_opt = _check_node_uuid(field_type)

            if is_node:
                node_uuid_fields[field_name] = is_opt
                gql_type: Any = NodeID[str] | None if is_opt else NodeID[str]
            else:
                gql_type = field_type

            pydantic_field = model.model_fields.get(field_name)
            if pydantic_field is None:
                # Computed / private field — skip
                continue

            default = pydantic_field.default
            default_factory = pydantic_field.default_factory

            if isinstance(default, PydanticUndefinedType) and default_factory is None:
                sf: dataclasses.Field[Any] = dataclasses.field()
                required_fields.append((field_name, gql_type, sf))
            elif default_factory is not None:
                sf = dataclasses.field(default_factory=cast("Callable[[], Any]", default_factory))
                optional_fields.append((field_name, gql_type, sf))
            else:
                sf = dataclasses.field(default=default)
                optional_fields.append((field_name, gql_type, sf))

        all_fields = required_fields + optional_fields

        # --- Build dataclass inheriting from Node and NodeGQLMixin -----------
        # NodeGQLMixin provides the stub methods that type-checkers can resolve.
        new_cls = dataclasses.make_dataclass(type_name, all_fields, bases=(Node, NodeGQLMixin))

        # Preserve any methods defined on the original decorated class
        for attr_name, attr_val in vars(cls).items():
            if attr_name.startswith("__") and attr_name.endswith("__"):
                continue
            setattr(new_cls, attr_name, attr_val)

        # --- Capture context for closures ------------------------------------
        _model = model
        _node_uuid_fields = node_uuid_fields
        _type_name = type_name

        # --- from_pydantic implementation ------------------------------------
        def _from_pydantic_impl(cls_inner: type, instance: BaseModel) -> Any:
            """Convert a Pydantic DTO to this Strawberry GQL type.

            NodeUUID fields are encoded as Relay Global IDs.
            Nested BaseModel fields whose type is registered in
            ``_pydantic_to_gql_registry`` are converted recursively.
            """
            kwargs: dict[str, Any] = {}
            for fname in get_type_hints(_model, include_extras=True):
                value = getattr(instance, fname)
                if fname in _node_uuid_fields:
                    kwargs[fname] = None if value is None else uuid_to_node_id(_type_name, value)
                elif isinstance(value, BaseModel):
                    nested_gql_cls = _pydantic_to_gql_registry.get(type(value))
                    if nested_gql_cls is not None:
                        kwargs[fname] = nested_gql_cls.from_pydantic(value)
                    else:
                        kwargs[fname] = value
                else:
                    kwargs[fname] = value
            return cls_inner(**kwargs)

        # --- to_pydantic implementation --------------------------------------
        def _to_pydantic_impl(self: Any) -> BaseModel:
            """Convert this GQL type instance to a Pydantic DTO.

            NodeID[str] fields are decoded back to UUID values.
            """
            kwargs: dict[str, Any] = {}
            for fname in get_type_hints(_model, include_extras=True):
                value = getattr(self, fname)
                if fname in _node_uuid_fields:
                    kwargs[fname] = None if value is None else node_id_to_uuid(str(value))
                else:
                    kwargs[fname] = value
            return _model(**kwargs)

        setattr(new_cls, "from_pydantic", classmethod(_from_pydantic_impl))
        setattr(new_cls, "to_pydantic", _to_pydantic_impl)

        # --- Apply @strawberry.type ------------------------------------------
        result = strawberry.type(new_cls, name=type_name, description=description or "")

        # Register so nested models can be auto-converted
        gql_type_result = cast(type[NodeGQLMixin], result)
        _pydantic_to_gql_registry[model] = gql_type_result

        return cast(type[_ClsT], result)

    return decorator
