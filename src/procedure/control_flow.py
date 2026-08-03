"""Deterministic control-flow analysis for procedure operations."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .models import (
    DirectConvergenceBranch,
    ProcedureBranch,
    ProcedureModel,
    ProcedureOperation,
)


@dataclass(frozen=True, slots=True)
class ConvergenceInfo:
    """A common continuation shared by the branches of one gateway."""

    gateway_id: str
    target_operation_id: str
    branch_labels: list[str]


def _reachable_distances(
    *,
    start_id: str,
    adjacency: dict[str, list[str]],
    excluded_edges: set[tuple[str, str]],
) -> dict[str, int]:
    """Return shortest operation distances while ignoring loop-back edges."""

    distances = {start_id: 0}
    queue = deque([start_id])

    while queue:
        current_id = queue.popleft()

        for next_id in adjacency.get(current_id, []):
            if (current_id, next_id) in excluded_edges:
                continue

            if next_id in distances:
                continue

            distances[next_id] = distances[current_id] + 1
            queue.append(next_id)

    return distances


def _analyze_common_continuations(
    procedure: ProcedureModel,
) -> list[ConvergenceInfo]:
    operations_by_id = {
        operation.bpmn_element_id: operation
        for operation in procedure.operations
    }
    adjacency = {
        operation.bpmn_element_id: [
            next_id
            for next_id in operation.next_operation_ids
            if next_id in operations_by_id
        ]
        for operation in procedure.operations
    }
    excluded_edges = {
        (
            operation.bpmn_element_id,
            branch.target_element_id,
        )
        for operation in procedure.operations
        for branch in operation.branches
        if branch.is_loop_back
    }

    decisions: dict[
        tuple[str, str],
        list[ProcedureBranch],
    ] = defaultdict(list)

    for operation in procedure.operations:
        for branch in operation.branches:
            decisions[
                (operation.bpmn_element_id, branch.gateway_id)
            ].append(branch)

    results: list[ConvergenceInfo] = []

    for (_, gateway_id), branches in decisions.items():
        branches_by_flow: dict[str, list[ProcedureBranch]] = (
            defaultdict(list)
        )

        for branch in branches:
            branches_by_flow[branch.flow_id].append(branch)

        if len(branches_by_flow) < 2:
            continue

        forward_branch_groups = [
            flow_branches
            for flow_branches in branches_by_flow.values()
            if (
                not any(
                    branch.is_loop_back
                    for branch in flow_branches
                )
                and any(
                    branch.target_element_id in operations_by_id
                    for branch in flow_branches
                )
            )
        ]

        if len(forward_branch_groups) < 2:
            continue

        distances_by_branch: list[dict[str, int]] = []

        for branch_group in forward_branch_groups:
            group_distances: dict[str, int] = {}

            for branch in branch_group:
                if branch.target_element_id not in operations_by_id:
                    continue

                distances = _reachable_distances(
                    start_id=branch.target_element_id,
                    adjacency=adjacency,
                    excluded_edges=excluded_edges,
                )

                for operation_id, distance in distances.items():
                    group_distances[operation_id] = min(
                        distance,
                        group_distances.get(operation_id, distance),
                    )

            distances_by_branch.append(group_distances)

        common_ids = set(distances_by_branch[0])

        for distances in distances_by_branch[1:]:
            common_ids.intersection_update(distances)

        if not common_ids:
            continue

        target_id = min(
            common_ids,
            key=lambda operation_id: (
                max(
                    distances[operation_id]
                    for distances in distances_by_branch
                ),
                sum(
                    distances[operation_id]
                    for distances in distances_by_branch
                ),
                operations_by_id[operation_id].number,
                operation_id,
            ),
        )
        branch_labels = [
            str(
                branch_group[0].label
                or branch_group[0].condition
                or ""
            ).strip()
            for branch_group in forward_branch_groups
        ]

        results.append(
            ConvergenceInfo(
                gateway_id=gateway_id,
                target_operation_id=target_id,
                branch_labels=[
                    label
                    for label in branch_labels
                    if label
                ],
            )
        )

    return results


def find_common_continuations(
    procedure: ProcedureModel,
) -> dict[str, list[str]]:
    """Map common continuation operations to their source gateways."""

    gateway_ids_by_target: dict[str, list[str]] = defaultdict(list)

    for convergence in _analyze_common_continuations(procedure):
        gateway_ids_by_target[
            convergence.target_operation_id
        ].append(convergence.gateway_id)

    return {
        target_id: list(dict.fromkeys(gateway_ids))
        for target_id, gateway_ids in gateway_ids_by_target.items()
    }


def attach_direct_convergence_branches(
    operations: list[ProcedureOperation],
) -> None:
    """Attach branches whose first operation is the convergence itself."""

    operations_by_id = {
        operation.bpmn_element_id: operation
        for operation in operations
    }

    for source_operation in operations:
        for branch in source_operation.branches:
            if branch.is_loop_back:
                continue

            target = operations_by_id.get(
                branch.target_element_id
            )

            if target is None:
                continue

            if not target.is_common_continuation:
                continue

            if (
                branch.gateway_id
                not in target.convergence_gateway_ids
            ):
                continue

            direct_branch = DirectConvergenceBranch(
                gateway_id=branch.gateway_id,
                gateway_name=branch.gateway_name,
                label=branch.label,
                condition=branch.condition,
                is_default=branch.is_default,
            )

            if (
                direct_branch
                not in target.direct_convergence_branches
            ):
                target.direct_convergence_branches.append(
                    direct_branch
                )
