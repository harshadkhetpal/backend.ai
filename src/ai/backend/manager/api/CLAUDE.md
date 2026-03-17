# Manager API Layer — Guardrails

> For full implementation patterns, see the `/api-guide` skill.

## Handler Style

- All handlers MUST be methods on an `APIHandler` class — no module-level async functions.
- Parse requests via `BodyParam[T]` and `PathParam[T]` — never read `request.json()` or
  `request.rel_url.query` directly inside a handler.
- Return `APIResponse.build(status_code=..., response_model=...)` — never `web.json_response()`.

## Calling Services

- Handlers MUST invoke services through a Processor, not directly:
  ```python
  # CORRECT — handler receives specific processor via constructor DI
  await self._foo.wait_for_complete(FooAction(...))
  # WRONG — never call service methods directly
  await self._foo_service.do_something(...)
  ```

## Naming

- Scoped endpoints: `{scope}_create_`, `{scope}_search_`, `{scope}_update_`, ... prefix.
- Superadmin-only endpoints (no scope): `admin_` prefix + call `_check_superadmin(request)` first.

## Routing

- Route registration belongs exclusively in `create_app()`.
- `app["prefix"]` must be set to the URL segment for this sub-app.

## What Belongs Here

- HTTP request/response translation only.
- Auth decorators (`@auth_required_for_method`).

## What Does NOT Belong Here

- Business logic or domain rules.
- Direct database access or ORM imports from `manager/models/`.
- Imports of Repository or Service classes (use Processors via context).

## Shared Adapter Pattern (GQL + REST)

> Validated in PoC: BA-5149 (strawberry.experimental.pydantic integration)

Both GQL resolvers and REST handlers call a shared `Adapter` instead of invoking Processors directly.
Adapters live in `api/adapters/{domain}.py` and accept/return Pydantic DTOs.

```
GQL resolver  → to_pydantic() → Adapter → Processor → from_pydantic()
REST handler  →               → Adapter → Processor
```

### Rules

1. **Adapter required for mutation/write operations**: `create`, `update`, `delete`, `purge` MUST
   go through `api/adapters/{domain}.py`. Read-only fetchers may call Processors directly.

2. **to_pydantic() mandatory for GQL Input**: Every GQL mutation input MUST call `to_pydantic()`
   before passing data to the Adapter. This ensures Pydantic validation runs on GQL inputs.

3. **from_pydantic() mandatory for GQL Output**: GQL resolvers MUST convert the Adapter's
   returned DTO via `RoleGQL.from_pydantic(dto)` (or equivalent). Never return raw data objects.

4. **Validation boundary**: Pydantic validation occurs inside `to_pydantic()` at the GQL layer.
   No additional validation is needed inside the Adapter or Processor.

### strawberry.experimental.pydantic Constraints (PoC Findings)

- **Output types** (`@strawberry_pydantic.type`): Incompatible with `strawberry.relay.Node`
  due to metaclass conflicts. Use **hybrid approach**: keep `@strawberry.type` + `Node`, add
  `from_pydantic()` class method manually.

- **Input types** (`@strawberry_pydantic.input`): Works with `fields=[...]` to select a subset
  of Pydantic model fields. Internal enum types (`RoleSource`, `RoleStatus`) must NOT be
  auto-mapped — specify them manually in the class body using registered GQL enum types
  (`RoleSourceGQL`, `RoleStatusGQL`) and override `to_pydantic()` for conversion.

- **Sentinel fields**: `str | Sentinel | None` fields are incompatible with
  `@strawberry_pydantic.input`. Exclude them via `fields=[...]` and add as `str | None`
  in the class body. Map GQL `null` to `SENTINEL` (no-op) inside `to_pydantic()`.

- **Filter/OrderBy types**: These contain domain-specific query-building logic.
  Keep them as regular `@strawberry.input` types — do NOT use `@strawberry_pydantic.input`.

### Example

```python
# GQL resolver
async def admin_create_role(info, input: CreateRoleInputGQL) -> RoleGQL:
    adapter = RoleServiceAdapter(info.context.processors.permission_controller)
    dto = input.to_pydantic()          # triggers Pydantic validation
    result = await adapter.create_role(dto)
    return RoleGQL.from_pydantic(result)

# REST handler
async def create_role(self, body: BodyParam[CreateRoleRequest], ...) -> APIResponse:
    role_dto = await self._role_service_adapter.create_role(body.parsed)
    return APIResponse.build(status_code=HTTPStatus.CREATED,
                             response_model=CreateRoleResponse(role=role_dto))
```
