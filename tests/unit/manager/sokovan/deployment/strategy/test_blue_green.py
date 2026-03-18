"""Tests for BlueGreenStrategy.evaluate_cycle().

Tests cover:
- FSM state transitions: PROVISIONING, AWAITING_PROMOTION, COMPLETED
- auto_promote / manual promote / delayed promote scenarios
- Edge cases and boundary conditions
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ai.backend.common.data.endpoint.types import EndpointLifecycle
from ai.backend.manager.data.deployment.types import (
    DeploymentInfo,
    DeploymentMetadata,
    DeploymentNetworkSpec,
    DeploymentState,
    DeploymentSubStep,
    ReplicaSpec,
    RouteInfo,
    RouteStatus,
    RouteTrafficStatus,
)
from ai.backend.manager.models.deployment_policy import BlueGreenSpec
from ai.backend.manager.repositories.deployment.creators import RouteCreatorSpec
from ai.backend.manager.sokovan.deployment.strategy.blue_green import BlueGreenStrategy

# =============================================================================
# Helpers
# =============================================================================

ENDPOINT_ID = UUID("00000000-0000-0000-0000-000000000001")
OLD_REVISION_ID = UUID("00000000-0000-0000-0000-000000000010")
NEW_REVISION_ID = UUID("00000000-0000-0000-0000-000000000020")
SESSION_OWNER_ID = UUID("00000000-0000-0000-0000-000000000099")
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000088")


def _make_deployment(
    desired_replicas: int = 2,
    deploying_revision_id: UUID = NEW_REVISION_ID,
) -> DeploymentInfo:
    return DeploymentInfo(
        id=ENDPOINT_ID,
        metadata=DeploymentMetadata(
            name="test-deployment",
            domain="default",
            project=PROJECT_ID,
            resource_group="default",
            created_user=SESSION_OWNER_ID,
            session_owner=SESSION_OWNER_ID,
            created_at=datetime.now(UTC),
            revision_history_limit=5,
        ),
        state=DeploymentState(
            lifecycle=EndpointLifecycle.DEPLOYING,
            retry_count=0,
        ),
        replica_spec=ReplicaSpec(
            replica_count=desired_replicas,
            desired_replica_count=desired_replicas,
        ),
        network=DeploymentNetworkSpec(open_to_public=False),
        model_revisions=[],
        current_revision_id=OLD_REVISION_ID,
        deploying_revision_id=deploying_revision_id,
    )


def _make_route(
    revision_id: UUID,
    status: RouteStatus = RouteStatus.HEALTHY,
    traffic_status: RouteTrafficStatus = RouteTrafficStatus.ACTIVE,
    created_at: datetime | None = None,
) -> RouteInfo:
    return RouteInfo(
        route_id=uuid4(),
        endpoint_id=ENDPOINT_ID,
        session_id=None,
        status=status,
        traffic_ratio=1.0 if traffic_status == RouteTrafficStatus.ACTIVE else 0.0,
        created_at=created_at or datetime.now(UTC),
        revision_id=revision_id,
        traffic_status=traffic_status,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def deployment() -> DeploymentInfo:
    return _make_deployment()


@pytest.fixture
def auto_promote_strategy() -> BlueGreenStrategy:
    return BlueGreenStrategy(BlueGreenSpec(auto_promote=True, promote_delay_seconds=0))


@pytest.fixture
def manual_promote_strategy() -> BlueGreenStrategy:
    return BlueGreenStrategy(BlueGreenSpec(auto_promote=False))


@pytest.fixture
def delayed_promote_strategy() -> BlueGreenStrategy:
    return BlueGreenStrategy(BlueGreenSpec(auto_promote=True, promote_delay_seconds=60))


# =============================================================================
# Tests
# =============================================================================


class TestBlueGreenNoGreenRoutes:
    """No green routes -> create INACTIVE green routes -> PROVISIONING."""

    def test_no_routes_at_all(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        result = auto_promote_strategy.evaluate_cycle(deployment, [])

        assert result.sub_step == DeploymentSubStep.PROVISIONING
        assert len(result.route_changes.rollout_specs) == 2
        for creator in result.route_changes.rollout_specs:
            spec = creator.spec
            assert isinstance(spec, RouteCreatorSpec)
            assert spec.revision_id == NEW_REVISION_ID
            assert spec.traffic_status == RouteTrafficStatus.INACTIVE
            assert spec.traffic_ratio == 0.0

    def test_only_blue_routes_exist(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        blue_routes = [
            _make_route(OLD_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(OLD_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, blue_routes)

        assert result.sub_step == DeploymentSubStep.PROVISIONING
        assert len(result.route_changes.rollout_specs) == 2


class TestBlueGreenProvisioning:
    """Green routes still PROVISIONING -> wait."""

    def test_green_provisioning_waits(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.PROVISIONING),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        assert result.sub_step == DeploymentSubStep.PROVISIONING
        assert not result.route_changes.rollout_specs
        assert not result.route_changes.drain_route_ids

    def test_all_green_provisioning(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.PROVISIONING),
            _make_route(NEW_REVISION_ID, RouteStatus.PROVISIONING),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        assert result.sub_step == DeploymentSubStep.PROVISIONING


class TestBlueGreenNotAllHealthy:
    """Not all green healthy -> PROVISIONING (waiting for readiness)."""

    def test_partial_green_healthy(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            # Only 1 of 2 desired is healthy
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        assert result.sub_step == DeploymentSubStep.PROVISIONING

    def test_mixed_healthy_and_degraded(
        self,
        auto_promote_strategy: BlueGreenStrategy,
    ) -> None:
        deployment = _make_deployment(desired_replicas=3)
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.DEGRADED),
            # DEGRADED counts as provisioning in the classifier
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        # 1 healthy + 1 provisioning(DEGRADED) < 3 desired -> still provisioning
        assert result.sub_step == DeploymentSubStep.PROVISIONING


class TestBlueGreenAllGreenFailed:
    """All green failed -> PROVISIONING (coordinator timeout handles rollback).

    When all green routes have failed, the strategy returns PROVISIONING
    without creating new routes. The coordinator's timeout sweep will
    eventually transition to ROLLING_BACK.
    """

    def test_all_green_failed_to_start(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        failed_routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.FAILED_TO_START),
            _make_route(NEW_REVISION_ID, RouteStatus.FAILED_TO_START),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, failed_routes)

        # Failed routes exist but no running green -> PROVISIONING (wait for timeout)
        assert result.sub_step == DeploymentSubStep.PROVISIONING
        assert not result.route_changes.rollout_specs

    def test_all_green_terminated(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        terminated_routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.TERMINATED),
            _make_route(NEW_REVISION_ID, RouteStatus.TERMINATED),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, terminated_routes)

        # Terminated routes exist but no running green -> PROVISIONING (wait for timeout)
        assert result.sub_step == DeploymentSubStep.PROVISIONING
        assert not result.route_changes.rollout_specs


class TestBlueGreenManualPromote:
    """auto_promote=False -> AWAITING_PROMOTION (manual wait)."""

    def test_all_green_healthy_manual_promote(
        self,
        manual_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = manual_promote_strategy.evaluate_cycle(deployment, routes)

        assert result.sub_step == DeploymentSubStep.AWAITING_PROMOTION
        assert not result.route_changes.promote_route_ids
        assert not result.route_changes.drain_route_ids


class TestBlueGreenDelayedPromote:
    """auto_promote=True + delay>0 -> check elapsed time."""

    def test_delay_not_elapsed_yet(
        self,
        delayed_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY, created_at=datetime.now(UTC)),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY, created_at=datetime.now(UTC)),
        ]

        result = delayed_promote_strategy.evaluate_cycle(deployment, routes)

        # 60s delay, just created -> still waiting
        assert result.sub_step == DeploymentSubStep.AWAITING_PROMOTION

    def test_delay_elapsed_promotes(
        self,
        delayed_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        old_time = datetime.now(UTC) - timedelta(seconds=120)
        green_routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY, created_at=old_time),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY, created_at=old_time),
        ]
        blue_routes = [
            _make_route(OLD_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = delayed_promote_strategy.evaluate_cycle(deployment, blue_routes + green_routes)

        assert result.sub_step == DeploymentSubStep.COMPLETED
        assert len(result.route_changes.promote_route_ids) == 2
        assert len(result.route_changes.drain_route_ids) == 1


class TestBlueGreenImmediatePromote:
    """auto_promote=True + delay=0 -> promote immediately."""

    def test_all_green_healthy_auto_promote(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        green_routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
        ]
        blue_routes = [
            _make_route(OLD_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(OLD_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, blue_routes + green_routes)

        assert result.sub_step == DeploymentSubStep.COMPLETED
        assert len(result.route_changes.promote_route_ids) == 2
        assert len(result.route_changes.drain_route_ids) == 2
        assert not result.route_changes.rollout_specs

    def test_promote_with_no_blue_routes(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        """First deployment: no old-revision routes to drain."""
        green_routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, green_routes)

        assert result.sub_step == DeploymentSubStep.COMPLETED
        assert len(result.route_changes.promote_route_ids) == 2
        assert not result.route_changes.drain_route_ids


class TestBlueGreenEdgeCases:
    """Edge cases and mixed scenarios."""

    def test_blue_terminated_routes_ignored(
        self,
        auto_promote_strategy: BlueGreenStrategy,
        deployment: DeploymentInfo,
    ) -> None:
        """Terminated blue routes should not appear in drain list."""
        routes = [
            _make_route(OLD_REVISION_ID, RouteStatus.TERMINATED),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        assert result.sub_step == DeploymentSubStep.COMPLETED
        assert not result.route_changes.drain_route_ids

    def test_mixed_green_healthy_and_failed(
        self,
        auto_promote_strategy: BlueGreenStrategy,
    ) -> None:
        """Some green healthy + some green failed -> still PROVISIONING (not enough healthy)."""
        deployment = _make_deployment(desired_replicas=3)
        routes = [
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.FAILED_TO_START),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        # 2 healthy < 3 desired
        assert result.sub_step == DeploymentSubStep.PROVISIONING

    def test_single_replica_deployment(
        self,
        auto_promote_strategy: BlueGreenStrategy,
    ) -> None:
        deployment = _make_deployment(desired_replicas=1)
        routes = [
            _make_route(OLD_REVISION_ID, RouteStatus.HEALTHY),
            _make_route(NEW_REVISION_ID, RouteStatus.HEALTHY),
        ]

        result = auto_promote_strategy.evaluate_cycle(deployment, routes)

        assert result.sub_step == DeploymentSubStep.COMPLETED
        assert len(result.route_changes.promote_route_ids) == 1
        assert len(result.route_changes.drain_route_ids) == 1

    def test_route_creators_have_correct_metadata(
        self,
        auto_promote_strategy: BlueGreenStrategy,
    ) -> None:
        deployment = _make_deployment(desired_replicas=1)

        result = auto_promote_strategy.evaluate_cycle(deployment, [])

        assert len(result.route_changes.rollout_specs) == 1
        spec = result.route_changes.rollout_specs[0].spec
        assert isinstance(spec, RouteCreatorSpec)
        assert spec.endpoint_id == ENDPOINT_ID
        assert spec.session_owner_id == SESSION_OWNER_ID
        assert spec.domain == "default"
        assert spec.project_id == PROJECT_ID
        assert spec.revision_id == NEW_REVISION_ID
        assert spec.traffic_status == RouteTrafficStatus.INACTIVE
        assert spec.traffic_ratio == 0.0
