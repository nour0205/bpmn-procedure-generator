"""Deterministic structured ordering of BPMN activities."""

from __future__ import annotations

from bpmn.enums import EventType
from bpmn.models import BpmnModel, Event, FlowNode


class ProcedureOrderingError(Exception):
    """Raised when procedure ordering cannot be constructed."""


class ProcedureOrderer:
    """Produce a stable business-readable order of documentable BPMN nodes.

    The traversal is depth-first so one branch is completed before the next
    branch is narrated. Shared continuation nodes are postponed until all of
    their forward predecessors have been visited. Explicit loop-back edges are
    detected separately and never cause an already described operation to be
    emitted a second time.
    """

    def order_process(
        self,
        model: BpmnModel,
        process_id: str,
    ) -> list[str]:
        """Return BPMN IDs in structured execution order."""

        graph = model.graphs.get(process_id)

        if graph is None:
            raise ProcedureOrderingError(
                f"No graph exists for process '{process_id}'."
            )

        node_by_id = {
            node.id: node
            for node in model.flow_nodes
            if node.process_id == process_id
            and node.parent_subprocess_id is None
        }

        entry_ids = [
            node_id
            for node_id in graph.entry_node_ids
            if node_id in node_by_id
        ]

        if not entry_ids and node_by_id:
            entry_ids = sorted(node_by_id)

        back_edges = self._classify_back_edges(
            model=model,
            node_by_id=node_by_id,
            entry_ids=entry_ids,
            adjacency=graph.adjacency,
        )

        forward_predecessors = {
            node_id: {
                predecessor_id
                for predecessor_id in graph.predecessors.get(
                    node_id,
                    [],
                )
                if (
                    predecessor_id in node_by_id
                    and (predecessor_id, node_id) not in back_edges
                )
            }
            for node_id in node_by_id
        }

        convergence_ids = {
            node_id
            for node_id, predecessors in forward_predecessors.items()
            if len(predecessors) > 1
        }

        visited: set[str] = set()
        active: set[str] = set()
        postponed: set[str] = set()
        ordered_activity_ids: list[str] = []

        def predecessors_ready(node_id: str) -> bool:
            return forward_predecessors.get(node_id, set()).issubset(
                visited
            )

        def visit(node_id: str) -> None:
            if (
                node_id in visited
                or node_id in active
                or node_id not in node_by_id
            ):
                return

            if (
                node_id in convergence_ids
                and not predecessors_ready(node_id)
            ):
                postponed.add(node_id)
                return

            active.add(node_id)
            visited.add(node_id)
            postponed.discard(node_id)

            node = node_by_id[node_id]

            if self._is_documentable_activity(node):
                ordered_activity_ids.append(node_id)

            successors = self._sort_successors(
                model=model,
                successor_ids=[
                    successor_id
                    for successor_id in graph.adjacency.get(
                        node_id,
                        [],
                    )
                    if (
                        successor_id in node_by_id
                        and (node_id, successor_id) not in back_edges
                    )
                ],
            )

            for successor_id in successors:
                visit(successor_id)
                drain_ready_postponed()

            active.remove(node_id)

        def drain_ready_postponed() -> None:
            while True:
                ready = [
                    node_id
                    for node_id in postponed
                    if predecessors_ready(node_id)
                ]

                if not ready:
                    return

                for node_id in self._sort_successors(
                    model=model,
                    successor_ids=ready,
                ):
                    visit(node_id)

        for entry_id in self._sort_successors(
            model=model,
            successor_ids=entry_ids,
        ):
            visit(entry_id)
            drain_ready_postponed()

        # Preserve disconnected or structurally unusual components.
        for node_id in self._sort_successors(
            model=model,
            successor_ids=list(node_by_id),
        ):
            visit(node_id)
            drain_ready_postponed()

        unreachable_activities = [
            node.id
            for node in node_by_id.values()
            if self._is_documentable_activity(node)
            and node.id not in ordered_activity_ids
        ]

        ordered_activity_ids.extend(
            self._sort_successors(
                model=model,
                successor_ids=unreachable_activities,
            )
        )

        return ordered_activity_ids

    def _classify_back_edges(
        self,
        *,
        model: BpmnModel,
        node_by_id: dict[str, FlowNode],
        entry_ids: list[str],
        adjacency: dict[str, list[str]],
    ) -> set[tuple[str, str]]:
        """Classify DFS back edges without treating every cycle edge as back."""

        visited: set[str] = set()
        active: set[str] = set()
        back_edges: set[tuple[str, str]] = set()

        def walk(node_id: str) -> None:
            if node_id in visited or node_id not in node_by_id:
                return

            visited.add(node_id)
            active.add(node_id)

            for successor_id in self._sort_successors(
                model=model,
                successor_ids=[
                    item
                    for item in adjacency.get(node_id, [])
                    if item in node_by_id
                ],
            ):
                if successor_id in active:
                    back_edges.add((node_id, successor_id))
                elif successor_id not in visited:
                    walk(successor_id)

            active.remove(node_id)

        for entry_id in self._sort_successors(
            model=model,
            successor_ids=entry_ids,
        ):
            walk(entry_id)

        for node_id in self._sort_successors(
            model=model,
            successor_ids=list(node_by_id),
        ):
            walk(node_id)

        return back_edges

    @staticmethod
    def _is_documentable_activity(
        node: FlowNode,
    ) -> bool:
        if hasattr(node, "task_type"):
            return True

        if hasattr(node, "subprocess_type"):
            return True

        if isinstance(node, Event):
            return (
                node.event_type
                in {
                    EventType.INTERMEDIATE_CATCH,
                    EventType.INTERMEDIATE_THROW,
                }
                and bool(node.name)
            )

        return False

    @staticmethod
    def _sort_successors(
        model: BpmnModel,
        successor_ids: list[str],
    ) -> list[str]:
        """Apply stable ordering using diagram position when available."""

        def sort_key(node_id: str) -> tuple[float, float, str]:
            shape = model.layout.shapes.get(node_id)

            if shape and shape.bounds:
                return (
                    shape.bounds.x,
                    shape.bounds.y,
                    node_id,
                )

            return (
                float("inf"),
                float("inf"),
                node_id,
            )

        return sorted(
            dict.fromkeys(successor_ids),
            key=sort_key,
        )
