
"""Structural and semantic validation for parsed BPMN models."""

from __future__ import annotations

from collections import defaultdict, deque

from .enums import (
    BpmnElementType,
    ValidationSeverity,
)
from .models import (
    BpmnModel,
    FlowNode,
    SequenceFlow,
    ValidationIssue,
    ValidationReport,
)


BUSINESS_DOCUMENT_TYPES = {
    BpmnElementType.DATA_OBJECT,
    BpmnElementType.DATA_OBJECT_REFERENCE,
    BpmnElementType.DATA_STORE_REFERENCE,
}


class BpmnValidator:
    """Validate a parsed BPMN semantic model."""

    def validate(self, model: BpmnModel) -> ValidationReport:
        """Run all supported validation rules."""

        issues: list[ValidationIssue] = []

        issues.extend(self._validate_processes(model))
        issues.extend(self._validate_flow_nodes(model))
        issues.extend(self._validate_sequence_flows(model))
        issues.extend(self._validate_gateways(model))
        issues.extend(self._validate_annotations(model))
        issues.extend(self._validate_documents(model))
        issues.extend(self._validate_reachability(model))

        return ValidationReport(issues=issues)

    def _validate_processes(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Validate process-level requirements."""

        issues: list[ValidationIssue] = []

        for process in model.processes:
            process_nodes = [
                node
                for node in model.flow_nodes
                if node.process_id == process.id
                and node.parent_subprocess_id is None
            ]

            start_events = [
                event
                for event in model.events
                if event.process_id == process.id
                and event.parent_subprocess_id is None
                and event.element_type
                == BpmnElementType.START_EVENT
            ]

            end_events = [
                event
                for event in model.events
                if event.process_id == process.id
                and event.parent_subprocess_id is None
                and event.element_type
                == BpmnElementType.END_EVENT
            ]

            if process_nodes and not start_events:
                issues.append(
                    ValidationIssue(
                        code="PROCESS_WITHOUT_START_EVENT",
                        severity=ValidationSeverity.WARNING,
                        element_id=process.id,
                        element_type=process.element_type,
                        message=(
                            f"Process '{process.name or process.id}' "
                            "does not contain a top-level start event."
                        ),
                    )
                )

            if process_nodes and not end_events:
                issues.append(
                    ValidationIssue(
                        code="PROCESS_WITHOUT_END_EVENT",
                        severity=ValidationSeverity.WARNING,
                        element_id=process.id,
                        element_type=process.element_type,
                        message=(
                            f"Process '{process.name or process.id}' "
                            "does not contain a top-level end event."
                        ),
                    )
                )

        return issues

    def _validate_flow_nodes(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Validate names, actors and basic flow-node information."""

        issues: list[ValidationIssue] = []

        processes_with_lanes = {
            lane.process_id
            for lane in model.lanes
        }

        for node in model.flow_nodes:
            if not node.name and node.element_type not in {
                BpmnElementType.START_EVENT,
                BpmnElementType.END_EVENT,
                BpmnElementType.EXCLUSIVE_GATEWAY,
                BpmnElementType.INCLUSIVE_GATEWAY,
                BpmnElementType.PARALLEL_GATEWAY,
                BpmnElementType.EVENT_BASED_GATEWAY,
                BpmnElementType.COMPLEX_GATEWAY,
            }:
                issues.append(
                    ValidationIssue(
                        code="UNNAMED_FLOW_NODE",
                        severity=ValidationSeverity.WARNING,
                        element_id=node.id,
                        element_type=node.element_type,
                        message=(
                            f"BPMN element '{node.id}' has no name."
                        ),
                    )
                )

            if (
                node.process_id in processes_with_lanes
                and node.lane_id is None
                and node.element_type not in {
                    BpmnElementType.START_EVENT,
                    BpmnElementType.END_EVENT,
                    BpmnElementType.INTERMEDIATE_CATCH_EVENT,
                    BpmnElementType.INTERMEDIATE_THROW_EVENT,
                    BpmnElementType.BOUNDARY_EVENT,
                    BpmnElementType.EXCLUSIVE_GATEWAY,
                    BpmnElementType.INCLUSIVE_GATEWAY,
                    BpmnElementType.PARALLEL_GATEWAY,
                    BpmnElementType.EVENT_BASED_GATEWAY,
                    BpmnElementType.COMPLEX_GATEWAY,
                }
            ):
                issues.append(
                    ValidationIssue(
                        code="FLOW_NODE_WITHOUT_ACTOR",
                        severity=ValidationSeverity.WARNING,
                        element_id=node.id,
                        element_type=node.element_type,
                        message=(
                            f"Activity '{node.name or node.id}' is not "
                            "assigned to a BPMN lane."
                        ),
                    )
                )

        return issues

    def _validate_sequence_flows(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Validate source and target references."""

        issues: list[ValidationIssue] = []

        node_ids = {
            node.id
            for node in model.flow_nodes
        }

        for flow in model.sequence_flows:
            if flow.source_ref not in node_ids:
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_SEQUENCE_FLOW_SOURCE",
                        severity=ValidationSeverity.ERROR,
                        element_id=flow.id,
                        element_type=flow.element_type,
                        message=(
                            f"Sequence flow '{flow.id}' references unknown "
                            f"source node '{flow.source_ref}'."
                        ),
                        context={
                            "source_ref": flow.source_ref,
                        },
                    )
                )

            if flow.target_ref not in node_ids:
                issues.append(
                    ValidationIssue(
                        code="UNKNOWN_SEQUENCE_FLOW_TARGET",
                        severity=ValidationSeverity.ERROR,
                        element_id=flow.id,
                        element_type=flow.element_type,
                        message=(
                            f"Sequence flow '{flow.id}' references unknown "
                            f"target node '{flow.target_ref}'."
                        ),
                        context={
                            "target_ref": flow.target_ref,
                        },
                    )
                )

        return issues

    def _validate_gateways(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Validate gateway branches and labels."""

        issues: list[ValidationIssue] = []

        flows_by_id = {
            flow.id: flow
            for flow in model.sequence_flows
        }

        for gateway in model.gateways:
            outgoing_flows = [
                flows_by_id[flow_id]
                for flow_id in gateway.outgoing
                if flow_id in flows_by_id
            ]

            if len(outgoing_flows) == 1:
                issues.append(
                    ValidationIssue(
                        code="GATEWAY_WITH_SINGLE_OUTGOING_FLOW",
                        severity=ValidationSeverity.WARNING,
                        element_id=gateway.id,
                        element_type=gateway.element_type,
                        message=(
                            f"Gateway '{gateway.name or gateway.id}' "
                            "has only one outgoing sequence flow."
                        ),
                    )
                )

            if len(outgoing_flows) <= 1:
                continue

            for flow in outgoing_flows:
                has_branch_information = bool(
                    flow.name
                    or flow.condition_expression
                    or flow.is_default
                )

                if not has_branch_information:
                    issues.append(
                        ValidationIssue(
                            code="UNLABELED_GATEWAY_BRANCH",
                            severity=ValidationSeverity.WARNING,
                            element_id=flow.id,
                            element_type=flow.element_type,
                            message=(
                                f"Outgoing branch '{flow.id}' from gateway "
                                f"'{gateway.name or gateway.id}' has no label, "
                                "condition or default-flow marker."
                            ),
                            context={
                                "gateway_id": gateway.id,
                            },
                        )
                    )

        return issues

    def _validate_annotations(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Validate annotation content and relationships."""

        issues: list[ValidationIssue] = []

        for annotation in model.annotations:
            if not annotation.text.strip():
                issues.append(
                    ValidationIssue(
                        code="EMPTY_ANNOTATION",
                        severity=ValidationSeverity.WARNING,
                        element_id=annotation.id,
                        element_type=annotation.element_type,
                        message=(
                            f"Annotation '{annotation.id}' contains no text."
                        ),
                    )
                )

            if not annotation.associated_element_ids:
                issues.append(
                    ValidationIssue(
                        code="UNASSOCIATED_ANNOTATION",
                        severity=ValidationSeverity.WARNING,
                        element_id=annotation.id,
                        element_type=annotation.element_type,
                        message=(
                            f"Annotation '{annotation.id}' is not associated "
                            "with any BPMN element."
                        ),
                    )
                )

        return issues

    def _validate_documents(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Validate business-document names and usage."""

        issues: list[ValidationIssue] = []

        for document in model.data_objects:
            if document.element_type not in BUSINESS_DOCUMENT_TYPES:
                continue

            if not document.name:
                issues.append(
                    ValidationIssue(
                        code="UNNAMED_BUSINESS_DOCUMENT",
                        severity=ValidationSeverity.WARNING,
                        element_id=document.id,
                        element_type=document.element_type,
                        message=(
                            f"Business document '{document.id}' has no name."
                        ),
                    )
                )

            if not document.produced_by and not document.consumed_by:
                issues.append(
                    ValidationIssue(
                        code="UNUSED_BUSINESS_DOCUMENT",
                        severity=ValidationSeverity.WARNING,
                        element_id=document.id,
                        element_type=document.element_type,
                        message=(
                            f"Business document "
                            f"'{document.name or document.id}' is not linked "
                            "to any activity."
                        ),
                    )
                )

        return issues

    def _validate_reachability(
        self,
        model: BpmnModel,
    ) -> list[ValidationIssue]:
        """Detect nodes that cannot be reached from a start event."""

        issues: list[ValidationIssue] = []

        containers = self._group_nodes_by_container(model)
        flows_by_container = self._group_flows_by_container(
            model.sequence_flows
        )

        for container_key, nodes in containers.items():
            process_id, parent_subprocess_id = container_key

            node_ids = {
                node.id
                for node in nodes
            }

            start_ids = {
                node.id
                for node in nodes
                if node.element_type
                == BpmnElementType.START_EVENT
            }

            if not start_ids:
                continue

            adjacency: dict[str, list[str]] = defaultdict(list)

            for flow in flows_by_container.get(container_key, []):
                if (
                    flow.source_ref in node_ids
                    and flow.target_ref in node_ids
                ):
                    adjacency[flow.source_ref].append(
                        flow.target_ref
                    )

            reachable = self._walk_graph(
                start_ids=start_ids,
                adjacency=adjacency,
            )

            for node in nodes:
                if node.id in reachable:
                    continue

                issues.append(
                    ValidationIssue(
                        code="UNREACHABLE_FLOW_NODE",
                        severity=ValidationSeverity.WARNING,
                        element_id=node.id,
                        element_type=node.element_type,
                        message=(
                            f"BPMN element '{node.name or node.id}' cannot "
                            "be reached from a start event in its container."
                        ),
                        context={
                            "process_id": process_id,
                            "parent_subprocess_id": (
                                parent_subprocess_id
                            ),
                        },
                    )
                )

        return issues

    @staticmethod
    def _group_nodes_by_container(
        model: BpmnModel,
    ) -> dict[
        tuple[str, str | None],
        list[FlowNode],
    ]:
        containers: dict[
            tuple[str, str | None],
            list[FlowNode],
        ] = defaultdict(list)

        for node in model.flow_nodes:
            key = (
                node.process_id,
                node.parent_subprocess_id,
            )
            containers[key].append(node)

        return dict(containers)

    @staticmethod
    def _group_flows_by_container(
        sequence_flows: list[SequenceFlow],
    ) -> dict[
        tuple[str, str | None],
        list[SequenceFlow],
    ]:
        containers: dict[
            tuple[str, str | None],
            list[SequenceFlow],
        ] = defaultdict(list)

        for flow in sequence_flows:
            key = (
                flow.process_id,
                flow.parent_subprocess_id,
            )
            containers[key].append(flow)

        return dict(containers)

    @staticmethod
    def _walk_graph(
        start_ids: set[str],
        adjacency: dict[str, list[str]],
    ) -> set[str]:
        """Return every node reachable from the supplied start nodes."""

        visited: set[str] = set()
        queue: deque[str] = deque(start_ids)

        while queue:
            node_id = queue.popleft()

            if node_id in visited:
                continue

            visited.add(node_id)

            for successor_id in adjacency.get(node_id, []):
                if successor_id not in visited:
                    queue.append(successor_id)

        return visited
