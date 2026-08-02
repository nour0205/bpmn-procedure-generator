"""Mapping from BPMN semantic models to procedure-oriented models."""

from __future__ import annotations

import re

from bpmn.enums import (
    BpmnElementType,
    EventDefinitionType,
    TaskType,
)
from bpmn.models import (
    BpmnModel,
    DataObject,
    Event,
    FlowNode,
    Gateway,
    SequenceFlow,
    SubProcess,
    Task,
)

from .models import (
    ProcedureActor,
    ProcedureBranch,
    ProcedureDocument,
    ProcedureElementKind,
    ProcedureMetadata,
    ProcedureModel,
    ProcedureNote,
    ProcedureOperation,
    ProcedureValidationSummary,
)
from .ordering import ProcedureOrderer


BUSINESS_DOCUMENT_TYPES = {
    BpmnElementType.DATA_OBJECT,
    BpmnElementType.DATA_OBJECT_REFERENCE,
    BpmnElementType.DATA_STORE_REFERENCE,
}


class ProcedureMapper:
    """Transform a parsed BPMN model into a procedure model."""

    def __init__(
        self,
        orderer: ProcedureOrderer | None = None,
    ) -> None:
        self.orderer = orderer or ProcedureOrderer()

    def map_process(
        self,
        model: BpmnModel,
        process_id: str,
    ) -> ProcedureModel:
        """Map one BPMN process into a procedure representation."""

        process = model.process_by_id(process_id)

        if process is None:
            raise ValueError(
                f"Unknown process ID: {process_id}"
            )

        participant = next(
            (
                item
                for item in model.participants
                if item.process_ref == process_id
            ),
            None,
        )

        operation_ids = self.orderer.order_process(
            model=model,
            process_id=process_id,
        )

        actors = self._map_actors(
            model=model,
            process_id=process_id,
        )

        documents = self._map_documents(
            model=model,
            process_id=process_id,
            operation_ids=set(operation_ids),
        )

        notes = self._map_notes(
            model=model,
            operation_ids=set(operation_ids),
        )

        operations = self._map_operations(
            model=model,
            process_id=process_id,
            ordered_ids=operation_ids,
        )

        return ProcedureModel(
            metadata=ProcedureMetadata(
                process_id=process.id,
                title=(
                    process.name
                    or (participant.name if participant else None)
                    or process.id
                ),
                source_path=model.metadata.source_path,
                participant_name=(
                    participant.name
                    if participant
                    else None
                ),
            ),
            actors=actors,
            operations=operations,
            documents=documents,
            notes=notes,
            validation=ProcedureValidationSummary(
                is_valid=model.validation.is_valid,
                error_count=len(model.validation.errors),
                warning_count=len(model.validation.warnings),
                issue_codes=sorted(
                    {
                        issue.code
                        for issue in model.validation.issues
                    }
                ),
            ),
        )

    @staticmethod
    def _map_actors(
        model: BpmnModel,
        process_id: str,
    ) -> list[ProcedureActor]:
        """Convert BPMN lanes into procedure actors."""

        actors: list[ProcedureActor] = []

        for lane in model.lanes:
            if lane.process_id != process_id:
                continue

            actors.append(
                ProcedureActor(
                    id=lane.id,
                    name=lane.name or lane.id,
                    source_type="lane",
                    process_id=lane.process_id,
                    participant_id=lane.participant_id,
                )
            )

        if actors:
            return actors

        participant = next(
            (
                item
                for item in model.participants
                if item.process_ref == process_id
            ),
            None,
        )

        if participant:
            actors.append(
                ProcedureActor(
                    id=participant.id,
                    name=participant.name or participant.id,
                    source_type="participant",
                    process_id=process_id,
                    participant_id=participant.id,
                )
            )

        return actors

    def _map_operations(
        self,
        model: BpmnModel,
        process_id: str,
        ordered_ids: list[str],
    ) -> list[ProcedureOperation]:
        """Create numbered procedure operations."""

        operation_id_set = set(ordered_ids)
        operations: list[ProcedureOperation] = []

        for number, element_id in enumerate(
            ordered_ids,
            start=1,
        ):
            node = model.node_by_id(element_id)

            if node is None:
                continue

            previous_ids = self._nearest_operations(
                model=model,
                start_id=element_id,
                operation_ids=operation_id_set,
                direction="backward",
            )

            next_ids = self._nearest_operations(
                model=model,
                start_id=element_id,
                operation_ids=operation_id_set,
                direction="forward",
            )

            actor_id, actor_name = self._resolve_actor(node)

            operations.append(
                ProcedureOperation(
                    number=number,
                    bpmn_element_id=node.id,
                    raw_name=node.name or node.id,
                    element_kind=self._element_kind(node),
                    source_type=node.element_type.value,
                    process_id=process_id,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    input_document_ids=list(
                        getattr(
                            node,
                            "input_document_ids",
                            [],
                        )
                    ),
                    output_document_ids=list(
                        getattr(
                            node,
                            "output_document_ids",
                            [],
                        )
                    ),
                    note_ids=list(
                        getattr(
                            node,
                            "annotation_ids",
                            [],
                        )
                    ),
                    previous_operation_ids=previous_ids,
                    next_operation_ids=next_ids,
                    preceding_gateway_ids=self._adjacent_gateways(
                        model,
                        node.id,
                        direction="backward",
                    ),
                    following_gateway_ids=self._adjacent_gateways(
                        model,
                        node.id,
                        direction="forward",
                    ),
                    branches=self._branches_after_operation(
                        model=model,
                        node_id=node.id,
                    ),
                    parent_subprocess_id=node.parent_subprocess_id,
                    order_ambiguous=len(previous_ids) > 1,
                )
            )

        return operations

    @staticmethod
    def _element_kind(
        node: FlowNode,
    ) -> ProcedureElementKind:
        """Map BPMN semantics to document semantics."""

        if isinstance(node, SubProcess):
            return ProcedureElementKind.SUBPROCESS

        if (
            isinstance(node, Task)
            and node.task_type == TaskType.CALL_ACTIVITY
        ):
            return ProcedureElementKind.SUBPROCESS

        if isinstance(node, Event) and node.name:
            return ProcedureElementKind.BUSINESS_EVENT

        return ProcedureElementKind.OPERATION

    @classmethod
    def _resolve_actor(
        cls,
        node: FlowNode,
    ) -> tuple[str | None, str | None]:
        """Resolve the semantic executor instead of blindly using the lane.

        Lanes remain useful context, but they are not necessarily the actor of
        automated tasks, timer events or events explicitly initiated by an
        external party.
        """

        if (
            isinstance(node, Task)
            and node.task_type == TaskType.SERVICE
        ):
            return None, "Système d'information"

        if isinstance(node, Event):
            if any(
                definition.definition_type
                == EventDefinitionType.TIMER
                for definition in node.definitions
            ):
                return None, "Événement temporel"

            external_actor = cls._explicit_external_actor(
                node.name
            )

            if external_actor:
                return None, external_actor

        return node.lane_id, node.lane_name

    @staticmethod
    def _explicit_external_actor(
        name: str | None,
    ) -> str | None:
        """Extract an actor only when the BPMN label states it explicitly."""

        if not name:
            return None

        match = re.search(
            r"\bde la part (?:du|de la|des|de l['’])\s+"
            r"(.+?)(?=\s+(?:sur|via|par)\b|[,.;]|$)",
            name,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        actor = " ".join(match.group(1).split()).strip()

        if not actor:
            return None

        return actor[0].upper() + actor[1:]

    @staticmethod
    def _path_exists(
        *,
        model: BpmnModel,
        start_id: str,
        target_id: str,
    ) -> bool:
        """Return True when target_id is reachable from start_id."""

        start_node = model.node_by_id(start_id)

        if start_node is None:
            return False

        graph = model.graphs.get(start_node.process_id)

        if graph is None:
            return False

        queue = [start_id]
        visited: set[str] = set()

        while queue:
            current = queue.pop(0)

            if current in visited:
                continue

            visited.add(current)

            if current == target_id:
                return True

            queue.extend(graph.adjacency.get(current, []))

        return False

    @staticmethod
    def _map_documents(
        model: BpmnModel,
        process_id: str,
        operation_ids: set[str],
    ) -> list[ProcedureDocument]:
        """Map only business-facing BPMN documents."""

        documents: list[ProcedureDocument] = []

        for document in model.data_objects:
            if document.process_id != process_id:
                continue

            if document.element_type not in BUSINESS_DOCUMENT_TYPES:
                continue

            produced_by = [
                activity_id
                for activity_id in document.produced_by
                if activity_id in operation_ids
            ]

            consumed_by = [
                activity_id
                for activity_id in document.consumed_by
                if activity_id in operation_ids
            ]

            documents.append(
                ProcedureDocument(
                    id=document.id,
                    name=document.name or document.id,
                    source_type=document.element_type.value,
                    produced_by_operation_ids=produced_by,
                    consumed_by_operation_ids=consumed_by,
                )
            )

        return documents

    @staticmethod
    def _map_notes(
        model: BpmnModel,
        operation_ids: set[str],
    ) -> list[ProcedureNote]:
        """Map annotations without classifying their meaning."""

        notes: list[ProcedureNote] = []

        for annotation in model.annotations:
            associated_operations = [
                element_id
                for element_id in annotation.associated_element_ids
                if element_id in operation_ids
            ]

            notes.append(
                ProcedureNote(
                    id=annotation.id,
                    text=annotation.text,
                    associated_operation_ids=associated_operations,
                )
            )

        return notes

    @staticmethod
    def _nearest_operations(
        model: BpmnModel,
        start_id: str,
        operation_ids: set[str],
        direction: str,
    ) -> list[str]:
        """Find the closest numbered operations across events and gateways."""

        process_id = model.node_by_id(start_id).process_id
        graph = model.graphs[process_id]

        adjacency = (
            graph.adjacency
            if direction == "forward"
            else graph.predecessors
        )

        queue = list(adjacency.get(start_id, []))
        visited: set[str] = set()
        found: list[str] = []

        while queue:
            current_id = queue.pop(0)

            if current_id in visited:
                continue

            visited.add(current_id)

            if current_id in operation_ids:
                found.append(current_id)
                continue

            queue.extend(
                adjacency.get(current_id, [])
            )

        return found

    @staticmethod
    def _adjacent_gateways(
        model: BpmnModel,
        node_id: str,
        direction: str,
    ) -> list[str]:
        """Return directly adjacent gateways."""

        node = model.node_by_id(node_id)

        if node is None:
            return []

        graph = model.graphs[node.process_id]

        adjacent_ids = (
            graph.adjacency.get(node_id, [])
            if direction == "forward"
            else graph.predecessors.get(node_id, [])
        )

        gateway_ids = {
            gateway.id
            for gateway in model.gateways
        }

        return [
            element_id
            for element_id in adjacent_ids
            if element_id in gateway_ids
        ]

    @staticmethod
    def _branches_after_operation(
        model: BpmnModel,
        node_id: str,
    ) -> list[ProcedureBranch]:
        """Extract branches when an operation is followed by a gateway."""

        node = model.node_by_id(node_id)

        if node is None:
            return []

        graph = model.graphs[node.process_id]

        gateway_by_id = {
            gateway.id: gateway
            for gateway in model.gateways
        }

        flow_by_pair: dict[
            tuple[str, str],
            SequenceFlow,
        ] = {
            (
                flow.source_ref,
                flow.target_ref,
            ): flow
            for flow in model.sequence_flows
        }

        branches: list[ProcedureBranch] = []

        for successor_id in graph.adjacency.get(
            node_id,
            [],
        ):
            gateway = gateway_by_id.get(successor_id)

            if gateway is None:
                continue

            for target_id in graph.adjacency.get(
                gateway.id,
                [],
            ):
                flow = flow_by_pair.get(
                    (
                        gateway.id,
                        target_id,
                    )
                )

                if flow is None:
                    continue

                branches.append(
                    ProcedureBranch(
                        flow_id=flow.id,
                        gateway_id=gateway.id,
                        gateway_name=gateway.name,
                        label=flow.name,
                        condition=flow.condition_expression,
                        is_default=flow.is_default,
                        is_loop_back=(
                            ProcedureMapper._path_exists(
                                model=model,
                                start_id=target_id,
                                target_id=node_id,
                            )
                        ),
                        target_element_id=target_id,
                    )
                )

        return branches
