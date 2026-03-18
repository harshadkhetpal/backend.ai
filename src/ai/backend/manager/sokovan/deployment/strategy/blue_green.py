"""Blue-green deployment strategy evaluation for a single deployment cycle (BEP-1049).

Provisions a full set of new-revision routes, validates them, then atomically
switches traffic from the old revision to the new one.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import override

from ai.backend.logging import BraceStyleAdapter
from ai.backend.manager.data.deployment.types import (
    DeploymentInfo,
    DeploymentSubStep,
    RouteInfo,
    RouteStatus,
    RouteTrafficStatus,
)
from ai.backend.manager.models.deployment_policy import BlueGreenSpec
from ai.backend.manager.models.routing import RoutingRow
from ai.backend.manager.repositories.base import Creator
from ai.backend.manager.repositories.deployment.creators import RouteCreatorSpec

from .types import AbstractDeploymentStrategy, RouteChanges, StrategyCycleResult

log = BraceStyleAdapter(logging.getLogger(__name__))


@dataclass
class _ClassifiedRoutes:
    """Routes classified by revision and status."""

    blue_active: list[RouteInfo] = field(default_factory=list)
    green_provisioning: list[RouteInfo] = field(default_factory=list)
    green_healthy: list[RouteInfo] = field(default_factory=list)
    green_failed: list[RouteInfo] = field(default_factory=list)

    @property
    def total_green_running(self) -> int:
        """Count of green-revision routes whose processes are still running.

        Includes provisioning routes to prevent duplicate route creation.
        """
        return len(self.green_provisioning) + len(self.green_healthy)


class BlueGreenStrategy(AbstractDeploymentStrategy):
    """Blue-green deployment strategy FSM."""

    _spec: BlueGreenSpec

    def __init__(self, spec: BlueGreenSpec) -> None:
        super().__init__(spec)
        self._spec = spec

    @override
    def evaluate_cycle(
        self,
        deployment: DeploymentInfo,
        routes: Sequence[RouteInfo],
    ) -> StrategyCycleResult:
        """Evaluate one cycle of blue-green deployment for a single deployment.

        FSM flow:
            1. Classify routes into blue (old) / green (new) by revision_id.
            2. If no green routes -> create all green (INACTIVE) -> PROVISIONING.
            3. If any green PROVISIONING -> PROVISIONING (wait).
            4. If not all green healthy -> PROVISIONING (wait for readiness).
            5. If all green healthy + awaiting promotion -> AWAITING_PROMOTION.
            6. If all green healthy + promote -> COMPLETED.

        Rollback is not decided by the FSM — the coordinator's timeout
        sweep handles it by transitioning to ROLLING_BACK when the
        deploying timeout is exceeded.
        """
        deploying_revision = deployment.deploying_revision_id
        desired = deployment.replica_spec.target_replica_count

        classified = self._classify_routes(routes, deploying_revision)

        log.debug(
            "deployment {}: sub_step={}, routes total={}, "
            "blue_active={}, green_prov={}, green_healthy={}, green_failed={}",
            deployment.id,
            deployment.sub_step,
            len(routes),
            len(classified.blue_active),
            len(classified.green_provisioning),
            len(classified.green_healthy),
            len(classified.green_failed),
        )

        if result := self._check_provisioning(deployment, classified, desired):
            return result
        if result := self._check_completed(deployment, classified, desired):
            return result
        return self._check_awaiting_promotion(deployment)

    def _classify_routes(
        self,
        routes: Sequence[RouteInfo],
        deploying_revision: uuid.UUID | None,
    ) -> _ClassifiedRoutes:
        """Classify routes into blue (old) / green (new) buckets."""
        classified = _ClassifiedRoutes()
        for route in routes:
            is_green = route.revision_id == deploying_revision
            if not is_green:
                if route.status.is_active():
                    classified.blue_active.append(route)
                continue

            if route.status.is_provisioning():
                classified.green_provisioning.append(route)
            elif route.status.is_inactive():
                classified.green_failed.append(route)
            elif route.status == RouteStatus.HEALTHY:
                classified.green_healthy.append(route)
        return classified

    def _check_provisioning(
        self,
        deployment: DeploymentInfo,
        classified: _ClassifiedRoutes,
        desired: int,
    ) -> StrategyCycleResult | None:
        """Return PROVISIONING if green routes need to be created or are still starting."""
        # No green routes -> create all green (INACTIVE)
        if classified.total_green_running == 0 and not classified.green_failed:
            log.debug(
                "deployment {}: no green routes — creating {} INACTIVE routes",
                deployment.id,
                desired,
            )
            return StrategyCycleResult(
                sub_step=DeploymentSubStep.PROVISIONING,
                route_changes=RouteChanges(
                    rollout_specs=_build_route_creators(deployment, desired),
                ),
            )

        # Green routes still PROVISIONING -> wait
        if classified.green_provisioning:
            log.debug(
                "deployment {}: {} green routes still provisioning",
                deployment.id,
                len(classified.green_provisioning),
            )
            return StrategyCycleResult(sub_step=DeploymentSubStep.PROVISIONING)

        # Not all green healthy -> wait for readiness
        if len(classified.green_healthy) < desired:
            log.debug(
                "deployment {}: green healthy={}/{} — waiting for readiness",
                deployment.id,
                len(classified.green_healthy),
                desired,
            )
            return StrategyCycleResult(sub_step=DeploymentSubStep.PROVISIONING)

        return None

    def _check_completed(
        self,
        deployment: DeploymentInfo,
        classified: _ClassifiedRoutes,
        desired: int,
    ) -> StrategyCycleResult | None:
        """Return COMPLETED if all green are healthy and promotion conditions are met."""
        if len(classified.green_healthy) < desired:
            return None

        if not self._spec.auto_promote:
            return None

        if self._spec.promote_delay_seconds > 0:
            latest_healthy_at = _latest_created_at(classified.green_healthy)
            if latest_healthy_at is None:
                return None
            elapsed = (datetime.now(UTC) - latest_healthy_at).total_seconds()
            if elapsed < self._spec.promote_delay_seconds:
                return None

        log.info(
            "deployment {}: promoting {} green routes, terminating {} blue routes",
            deployment.id,
            len(classified.green_healthy),
            len(classified.blue_active),
        )
        route_changes = RouteChanges(
            promote_route_ids=[route.route_id for route in classified.green_healthy],
            drain_route_ids=[route.route_id for route in classified.blue_active],
        )
        return StrategyCycleResult(
            sub_step=DeploymentSubStep.COMPLETED,
            route_changes=route_changes,
        )

    def _check_awaiting_promotion(
        self,
        deployment: DeploymentInfo,
    ) -> StrategyCycleResult:
        """Return AWAITING_PROMOTION when all green are healthy but promotion conditions not met."""
        log.debug(
            "deployment {}: all green healthy, awaiting promotion",
            deployment.id,
        )
        return StrategyCycleResult(sub_step=DeploymentSubStep.AWAITING_PROMOTION)


def _latest_created_at(routes: list[RouteInfo]) -> datetime | None:
    """Return the most recent created_at among the given routes.

    Ideally this would use ``status_updated_at`` to measure how long
    the route has been HEALTHY, but that field is not yet available
    on RouteInfo. ``created_at`` serves as a conservative proxy.
    """
    timestamps = [route.created_at for route in routes]
    return max(timestamps) if timestamps else None


def _build_route_creators(
    deployment: DeploymentInfo,
    count: int,
) -> list[Creator[RoutingRow]]:
    """Build route creator specs for green routes (INACTIVE, traffic_ratio=0.0)."""
    creators: list[Creator[RoutingRow]] = []
    for _ in range(count):
        creator_spec = RouteCreatorSpec(
            endpoint_id=deployment.id,
            session_owner_id=deployment.metadata.session_owner,
            domain=deployment.metadata.domain,
            project_id=deployment.metadata.project,
            revision_id=deployment.deploying_revision_id,
            traffic_status=RouteTrafficStatus.INACTIVE,
            traffic_ratio=0.0,
        )
        creators.append(Creator(spec=creator_spec))
    return creators
