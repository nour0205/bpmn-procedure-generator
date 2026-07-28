"""Deterministic ordering of BPMN activities for procedure generation."""

from __future__ import annotations

from collections import deque

from bpmn.enums import EventType
from bpmn.models import BpmnModel, Event, FlowNode


class ProcedureOrderingError(Exception):
    """Raised when procedure ordering cannot be constructed."""


class ProcedureOrderer:
    """Produce a stable order of documentable BPMN activities."""

    def order_process(
        self,
        model: BpmnModel,
        process_id: str,
    ) -> list[str]:
        """Return ordered BPMN IDs for tasks and subprocess activities."""

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

        queue: deque[str] = deque(
            sorted(entry_ids)
        )

        visited: set[str] = set()
        ordered_activity_ids: list[str] = []

        while queue:
            node_id = queue.popleft()

            if node_id in visited:
                continue

            visited.add(node_id)

            node = node_by_id.get(node_id)

            if node is None:
                continue

            if self._is_documentable_activity(node):
                ordered_activity_ids.append(node.id)

            successors = graph.adjacency.get(node_id, [])

            for successor_id in self._sort_successors(
                model=model,
                successor_ids=successors,
            ):
                if successor_id not in visited:
                    queue.append(successor_id)

        unreachable_activities = sorted(
            node.id
            for node in node_by_id.values()
            if self._is_documentable_activity(node)
            and node.id not in visited
        )

        ordered_activity_ids.extend(unreachable_activities)

        return ordered_activity_ids

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
            successor_ids,
            key=sort_key,
        )
