"""Strongly typed semantic models for BPMN documents."""

from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .enums import (
    AnnotationCategory,
    AssociationDirection,
    BpmnElementType,
    DocumentDirection,
    EventDefinitionType,
    EventType,
    GatewayType,
    SourceType,
    SubProcessType,
    TaskType,
    ValidationSeverity,
)


class BpmnBaseModel(BaseModel):
    """Base configuration shared by all BPMN models."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=False,
    )


class SourceValue(BpmnBaseModel):
    """A value together with traceability and confidence information."""

    value: str
    source: SourceType = SourceType.BPMN_XML
    source_element_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_validation: bool = False


class ExtensionElement(BpmnBaseModel):
    """Vendor-specific or custom content found in extensionElements."""

    type: str
    attributes: dict[str, str] = Field(default_factory=dict)
    text: str | None = None
    children: list["ExtensionElement"] = Field(default_factory=list)


class BpmnElement(BpmnBaseModel):
    """Common fields shared by identified BPMN elements."""

    id: str
    element_type: BpmnElementType
    name: str | None = None
    documentation: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    extensions: list[ExtensionElement] = Field(default_factory=list)


class Process(BpmnElement):
    """A BPMN process."""

    element_type: BpmnElementType = BpmnElementType.PROCESS
    is_executable: bool | None = None
    participant_ids: list[str] = Field(default_factory=list)
    lane_ids: list[str] = Field(default_factory=list)
    flow_node_ids: list[str] = Field(default_factory=list)
    sequence_flow_ids: list[str] = Field(default_factory=list)


class Participant(BpmnElement):
    """A pool or external participant in a BPMN collaboration."""

    element_type: BpmnElementType = BpmnElementType.PARTICIPANT
    process_ref: str | None = None

    @computed_field
    @property
    def is_external(self) -> bool:
        """Return True when the participant has no modeled internal process."""
        return self.process_ref is None


class Lane(BpmnElement):
    """A BPMN lane representing an actor or organizational responsibility."""

    element_type: BpmnElementType = BpmnElementType.LANE
    process_id: str
    participant_id: str | None = None
    parent_lane_id: str | None = None
    child_lane_ids: list[str] = Field(default_factory=list)
    flow_node_refs: list[str] = Field(default_factory=list)


class FlowNode(BpmnElement):
    """Common structure shared by BPMN nodes connected by sequence flows."""

    process_id: str
    participant_id: str | None = None
    lane_id: str | None = None
    lane_name: str | None = None
    parent_subprocess_id: str | None = None
    incoming: list[str] = Field(default_factory=list)
    outgoing: list[str] = Field(default_factory=list)


class Task(FlowNode):
    """A BPMN task or call activity."""

    task_type: TaskType
    input_document_ids: list[str] = Field(default_factory=list)
    output_document_ids: list[str] = Field(default_factory=list)
    annotation_ids: list[str] = Field(default_factory=list)
    system_names: list[str] = Field(default_factory=list)
    called_element: str | None = None


class EventDefinition(BpmnBaseModel):
    """Definition describing the trigger or result of an event."""

    definition_type: EventDefinitionType
    id: str | None = None
    reference: str | None = None
    timer_type: str | None = None
    timer_value: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class Event(FlowNode):
    """A start, intermediate, end or boundary event."""

    event_type: EventType
    definitions: list[EventDefinition] = Field(default_factory=list)
    attached_to_ref: str | None = None
    cancel_activity: bool | None = None

    @model_validator(mode="after")
    def validate_boundary_event(self) -> "Event":
        if self.event_type == EventType.BOUNDARY and not self.attached_to_ref:
            raise ValueError("A boundary event must define attached_to_ref")
        return self


class Gateway(FlowNode):
    """A BPMN decision, merge or synchronization gateway."""

    gateway_type: GatewayType
    default_flow_id: str | None = None


class SubProcess(FlowNode):
    """An embedded BPMN subprocess."""

    element_type: BpmnElementType = BpmnElementType.SUB_PROCESS
    subprocess_type: SubProcessType = SubProcessType.EMBEDDED
    triggered_by_event: bool = False
    child_node_ids: list[str] = Field(default_factory=list)
    child_flow_ids: list[str] = Field(default_factory=list)
    annotation_ids: list[str] = Field(default_factory=list)
    input_document_ids: list[str] = Field(default_factory=list)
    output_document_ids: list[str] = Field(default_factory=list)


class SequenceFlow(BpmnElement):
    """A sequence relation between two flow nodes."""

    element_type: BpmnElementType = BpmnElementType.SEQUENCE_FLOW
    process_id: str
    parent_subprocess_id: str | None = None
    source_ref: str
    target_ref: str
    condition_expression: str | None = None
    is_default: bool = False


class MessageFlow(BpmnElement):
    """A message exchange between participants or process elements."""

    element_type: BpmnElementType = BpmnElementType.MESSAGE_FLOW
    source_ref: str
    target_ref: str
    message_ref: str | None = None


class DataObject(BpmnElement):
    """A document or business data object represented in BPMN."""

    element_type: BpmnElementType
    process_id: str | None = None
    data_state: str | None = None
    item_subject_ref: str | None = None
    original_data_object_ref: str | None = None
    produced_by: list[str] = Field(default_factory=list)
    consumed_by: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def direction(self) -> DocumentDirection:
        """Infer whether the object is consumed, produced or both."""
        has_inputs = bool(self.consumed_by)
        has_outputs = bool(self.produced_by)

        if has_inputs and has_outputs:
            return DocumentDirection.INPUT_OUTPUT
        if has_inputs:
            return DocumentDirection.INPUT
        if has_outputs:
            return DocumentDirection.OUTPUT
        return DocumentDirection.UNKNOWN


class DataAssociation(BpmnElement):
    """Input or output association between a flow node and business data."""

    element_type: BpmnElementType
    process_id: str
    parent_activity_id: str
    source_refs: list[str] = Field(default_factory=list)
    target_ref: str | None = None
    transformation: str | None = None
    assignment_expressions: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def direction(self) -> DocumentDirection:
        if self.element_type == BpmnElementType.DATA_INPUT_ASSOCIATION:
            return DocumentDirection.INPUT
        if self.element_type == BpmnElementType.DATA_OUTPUT_ASSOCIATION:
            return DocumentDirection.OUTPUT
        return DocumentDirection.UNKNOWN


class TextAnnotation(BpmnElement):
    """A BPMN text annotation and its semantic classification."""

    element_type: BpmnElementType = BpmnElementType.TEXT_ANNOTATION
    process_id: str | None = None
    parent_subprocess_id: str | None = None
    text: str
    category: AnnotationCategory = AnnotationCategory.UNCLASSIFIED
    associated_element_ids: list[str] = Field(default_factory=list)
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_validation: bool = True


class Association(BpmnElement):
    """Association connecting annotations, artifacts or BPMN elements."""

    element_type: BpmnElementType = BpmnElementType.ASSOCIATION
    process_id: str | None = None
    source_ref: str
    target_ref: str
    direction: AssociationDirection = AssociationDirection.NONE


class Bounds(BpmnBaseModel):
    """Position and dimensions of a BPMN shape."""

    x: float
    y: float
    width: float
    height: float


class Waypoint(BpmnBaseModel):
    """A point defining the path of a BPMN diagram edge."""

    x: float
    y: float


class DiagramShape(BpmnBaseModel):
    """Layout information for a BPMN graphical shape."""

    id: str
    bpmn_element_id: str
    bounds: Bounds | None = None
    is_horizontal: bool | None = None
    is_expanded: bool | None = None


class DiagramEdge(BpmnBaseModel):
    """Layout information for a BPMN graphical edge."""

    id: str
    bpmn_element_id: str
    waypoints: list[Waypoint] = Field(default_factory=list)


class DiagramLayout(BpmnBaseModel):
    """All graphical BPMN DI information."""

    shapes: dict[str, DiagramShape] = Field(default_factory=dict)
    edges: dict[str, DiagramEdge] = Field(default_factory=dict)


class ValidationIssue(BpmnBaseModel):
    """A structural or semantic problem detected in the BPMN model."""

    code: str
    severity: ValidationSeverity
    message: str
    element_id: str | None = None
    element_type: BpmnElementType | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BpmnBaseModel):
    """Complete model validation result."""

    issues: list[ValidationIssue] = Field(default_factory=list)

    @computed_field
    @property
    def errors(self) -> list[ValidationIssue]:
        return [
            issue
            for issue in self.issues
            if issue.severity == ValidationSeverity.ERROR
        ]

    @computed_field
    @property
    def warnings(self) -> list[ValidationIssue]:
        return [
            issue
            for issue in self.issues
            if issue.severity == ValidationSeverity.WARNING
        ]

    @computed_field
    @property
    def is_valid(self) -> bool:
        return not self.errors


class GraphEdge(BpmnBaseModel):
    """Resolved graph representation of a sequence flow."""

    flow_id: str
    source_ref: str
    target_ref: str
    label: str | None = None
    condition: str | None = None


class ProcessGraph(BpmnBaseModel):
    """Graph structure derived from BPMN sequence flows."""

    adjacency: dict[str, list[str]] = Field(default_factory=dict)
    predecessors: dict[str, list[str]] = Field(default_factory=dict)
    edges: list[GraphEdge] = Field(default_factory=list)
    entry_node_ids: list[str] = Field(default_factory=list)
    exit_node_ids: list[str] = Field(default_factory=list)


class BpmnMetadata(BpmnBaseModel):
    """Technical metadata about the parsed BPMN file."""

    source_path: str
    exporter: str | None = None
    exporter_version: str | None = None
    target_namespace: str | None = None
    namespaces: dict[str, str] = Field(default_factory=dict)


class BpmnModel(BpmnBaseModel):
    """Root semantic representation of an entire BPMN document."""

    metadata: BpmnMetadata

    processes: list[Process] = Field(default_factory=list)
    participants: list[Participant] = Field(default_factory=list)
    lanes: list[Lane] = Field(default_factory=list)

    tasks: list[Task] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    gateways: list[Gateway] = Field(default_factory=list)
    subprocesses: list[SubProcess] = Field(default_factory=list)

    sequence_flows: list[SequenceFlow] = Field(default_factory=list)
    message_flows: list[MessageFlow] = Field(default_factory=list)

    data_objects: list[DataObject] = Field(default_factory=list)
    data_associations: list[DataAssociation] = Field(default_factory=list)

    annotations: list[TextAnnotation] = Field(default_factory=list)
    associations: list[Association] = Field(default_factory=list)

    layout: DiagramLayout = Field(default_factory=DiagramLayout)
    graphs: dict[str, ProcessGraph] = Field(default_factory=dict)
    validation: ValidationReport = Field(default_factory=ValidationReport)

    @computed_field
    @property
    def flow_nodes(self) -> list[FlowNode]:
        """Return all BPMN nodes that can participate in sequence flows."""
        return [
            *self.tasks,
            *self.events,
            *self.gateways,
            *self.subprocesses,
        ]

    @computed_field
    @property
    def element_count(self) -> int:
        return sum(
            (
                len(self.processes),
                len(self.participants),
                len(self.lanes),
                len(self.flow_nodes),
                len(self.sequence_flows),
                len(self.message_flows),
                len(self.data_objects),
                len(self.data_associations),
                len(self.annotations),
                len(self.associations),
            )
        )

    @computed_field
    @property
    def summary(self) -> dict[str, Any]:
        """Return a compact deterministic summary of the BPMN document."""
        task_types = Counter(task.task_type.value for task in self.tasks)
        gateway_types = Counter(
            gateway.gateway_type.value for gateway in self.gateways
        )
        event_types = Counter(event.event_type.value for event in self.events)

        return {
            "process_count": len(self.processes),
            "participant_count": len(self.participants),
            "lane_count": len(self.lanes),
            "task_count": len(self.tasks),
            "subprocess_count": len(self.subprocesses),
            "event_count": len(self.events),
            "gateway_count": len(self.gateways),
            "sequence_flow_count": len(self.sequence_flows),
            "message_flow_count": len(self.message_flows),
            "document_count": len(self.data_objects),
            "annotation_count": len(self.annotations),
            "task_types": dict(task_types),
            "gateway_types": dict(gateway_types),
            "event_types": dict(event_types),
            "has_parallelism": any(
                gateway.gateway_type == GatewayType.PARALLEL
                for gateway in self.gateways
            ),
            "has_subprocesses": bool(self.subprocesses),
            "has_external_participants": any(
                participant.is_external
                for participant in self.participants
            ),
            "is_valid": self.validation.is_valid,
            "warning_count": len(self.validation.warnings),
            "error_count": len(self.validation.errors),
        }

    def element_by_id(self, element_id: str) -> BpmnElement | None:
        """Find any supported BPMN element by its identifier."""
        collections: list[list[BpmnElement]] = [
            self.processes,
            self.participants,
            self.lanes,
            self.tasks,
            self.events,
            self.gateways,
            self.subprocesses,
            self.sequence_flows,
            self.message_flows,
            self.data_objects,
            self.data_associations,
            self.annotations,
            self.associations,
        ]

        for collection in collections:
            for element in collection:
                if element.id == element_id:
                    return element

        return None

    def node_by_id(self, node_id: str) -> FlowNode | None:
        """Find a flow node by identifier."""
        return next(
            (
                node
                for node in self.flow_nodes
                if node.id == node_id
            ),
            None,
        )

    def lane_by_id(self, lane_id: str) -> Lane | None:
        return next(
            (lane for lane in self.lanes if lane.id == lane_id),
            None,
        )

    def process_by_id(self, process_id: str) -> Process | None:
        return next(
            (
                process
                for process in self.processes
                if process.id == process_id
            ),
            None,
        )

    def documents_for_activity(
        self,
        activity_id: str,
    ) -> tuple[list[DataObject], list[DataObject]]:
        """Return the input and output documents of an activity."""
        input_documents = [
            document
            for document in self.data_objects
            if activity_id in document.consumed_by
        ]
        output_documents = [
            document
            for document in self.data_objects
            if activity_id in document.produced_by
        ]
        return input_documents, output_documents

    def annotations_for_element(
        self,
        element_id: str,
    ) -> list[TextAnnotation]:
        """Return annotations associated with a BPMN element."""
        return [
            annotation
            for annotation in self.annotations
            if element_id in annotation.associated_element_ids
        ]

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> "BpmnModel":
        """Reject duplicate BPMN identifiers in the semantic model."""
        all_ids: list[str] = []

        collections: list[list[BpmnElement]] = [
            self.processes,
            self.participants,
            self.lanes,
            self.tasks,
            self.events,
            self.gateways,
            self.subprocesses,
            self.sequence_flows,
            self.message_flows,
            self.data_objects,
            self.data_associations,
            self.annotations,
            self.associations,
        ]

        for collection in collections:
            all_ids.extend(element.id for element in collection)

        duplicate_ids = sorted(
            element_id
            for element_id, count in Counter(all_ids).items()
            if count > 1
        )

        if duplicate_ids:
            raise ValueError(
                "Duplicate BPMN element IDs detected: "
                + ", ".join(duplicate_ids)
            )

        return self
