"""Main orchestrator for parsing BPMN XML into typed domain models."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .builders import (
    DATA_ASSOCIATION_ELEMENT_TYPE_BY_TAG,
    DATA_OBJECT_ELEMENT_TYPE_BY_TAG,
    EVENT_TYPE_BY_TAG,
    GATEWAY_TYPE_BY_TAG,
    SUBPROCESS_TYPE_BY_TAG,
    TASK_TYPE_BY_TAG,
    FlowNodeContext,
    build_association,
    build_data_association,
    build_data_object,
    build_event,
    build_gateway,
    build_sequence_flow,
    build_subprocess,
    build_task,
    build_text_annotation,
)
from .enums import BpmnElementType
from .models import (
    Association,
    BpmnMetadata,
    BpmnModel,
    Bounds,
    DataAssociation,
    DataObject,
    DiagramEdge,
    DiagramLayout,
    DiagramShape,
    Event,
    FlowNode,
    Gateway,
    GraphEdge,
    Lane,
    Participant,
    Process,
    ProcessGraph,
    SequenceFlow,
    SubProcess,
    Task,
    TextAnnotation,
    Waypoint,
)
from .namespaces import (
    NamespaceContext,
    child_texts,
    collect_namespaces,
    first_child_text,
    local_name,
    normalize_text,
)
from .validator import BpmnValidator


class BpmnParseError(Exception):
    """Raised when a BPMN document cannot be parsed."""


class BpmnParser:
    """Parse BPMN XML files into a validated semantic model."""

    def parse_file(self, path: str | Path) -> BpmnModel:
        """Parse a BPMN file from disk."""

        source_path = Path(path)

        if not source_path.exists():
            raise FileNotFoundError(
                f"BPMN file does not exist: {source_path}"
            )

        if not source_path.is_file():
            raise BpmnParseError(
                f"BPMN path is not a file: {source_path}"
            )

        try:
            namespaces = collect_namespaces(source_path)
            root = ET.parse(source_path).getroot()
        except ET.ParseError as exc:
            raise BpmnParseError(
                f"Invalid XML in {source_path}: {exc}"
            ) from exc

        namespace_context = NamespaceContext(namespaces)

        self._validate_root(root)

        processes = self._extract_processes(
            root,
            namespace_context,
        )

        participants = self._extract_participants(
            root,
            namespace_context,
        )

        lanes = self._extract_lanes(
            root,
            participants,
            namespace_context,
        )

        layout = self._extract_layout(root)

        tasks, events, gateways, subprocesses = self._extract_flow_nodes(
            root=root,
            participants=participants,
            lanes=lanes,
            namespace_context=namespace_context,
        )

        self._infer_lane_assignments(
            nodes=[
                *tasks,
                *events,
                *gateways,
                *subprocesses,
            ],
            lanes=lanes,
            layout=layout,
        )

        sequence_flows = self._extract_sequence_flows(
            root=root,
            gateways=gateways,
            namespace_context=namespace_context,
        )

        data_objects, data_associations = self._extract_data_elements(
            root=root,
            namespace_context=namespace_context,
        )

        self._enrich_document_relationships(
            data_objects=data_objects,
            data_associations=data_associations,
            tasks=tasks,
            subprocesses=subprocesses,
        )

        annotations, associations = (
            self._extract_annotations_and_associations(
                root=root,
                namespace_context=namespace_context,
            )
        )

        self._enrich_annotation_relationships(
            annotations=annotations,
            associations=associations,
            tasks=tasks,
            subprocesses=subprocesses,
        )

        graphs = self._build_process_graphs(
            processes=processes,
            tasks=tasks,
            events=events,
            gateways=gateways,
            subprocesses=subprocesses,
            sequence_flows=sequence_flows,
        )

        self._enrich_process_references(
            processes=processes,
            participants=participants,
            lanes=lanes,
        )

        metadata = self._extract_metadata(
            root=root,
            source_path=source_path,
            namespaces=namespaces,
            namespace_context=namespace_context,
        )

        model = BpmnModel(
            metadata=metadata,
            processes=processes,
            participants=participants,
            lanes=lanes,
            tasks=tasks,
            events=events,
            gateways=gateways,
            subprocesses=subprocesses,
            sequence_flows=sequence_flows,
            data_objects=data_objects,
            data_associations=data_associations,
            annotations=annotations,
            associations=associations,
            layout=layout,
            graphs=graphs,
        )

        model.validation = BpmnValidator().validate(model)

        return model

    @staticmethod
    def _validate_root(root: ET.Element) -> None:
        """Validate that the XML root is a BPMN definitions element."""

        if local_name(root.tag) != "definitions":
            raise BpmnParseError(
                "The XML root element must be BPMN 'definitions'."
            )

    def _extract_layout(
        self,
        root: ET.Element,
    ) -> DiagramLayout:
        """Extract BPMN DI shapes, bounds, edges and waypoints."""

        shapes: dict[str, DiagramShape] = {}
        edges: dict[str, DiagramEdge] = {}

        for element in root.iter():
            tag = local_name(element.tag)

            if tag == "BPMNShape":
                bpmn_element_id = element.attrib.get("bpmnElement")
                shape_id = element.attrib.get("id")

                if not bpmn_element_id or not shape_id:
                    continue

                bounds: Bounds | None = None

                for child in list(element):
                    if local_name(child.tag) != "Bounds":
                        continue

                    try:
                        bounds = Bounds(
                            x=float(child.attrib["x"]),
                            y=float(child.attrib["y"]),
                            width=float(child.attrib["width"]),
                            height=float(child.attrib["height"]),
                        )
                    except (KeyError, ValueError):
                        bounds = None

                    break

                shapes[bpmn_element_id] = DiagramShape(
                    id=shape_id,
                    bpmn_element_id=bpmn_element_id,
                    bounds=bounds,
                    is_horizontal=self._parse_optional_boolean(
                        element.attrib.get("isHorizontal")
                    ),
                    is_expanded=self._parse_optional_boolean(
                        element.attrib.get("isExpanded")
                    ),
                )

            elif tag == "BPMNEdge":
                bpmn_element_id = element.attrib.get("bpmnElement")
                edge_id = element.attrib.get("id")

                if not bpmn_element_id or not edge_id:
                    continue

                waypoints: list[Waypoint] = []

                for child in list(element):
                    if local_name(child.tag) != "waypoint":
                        continue

                    try:
                        waypoints.append(
                            Waypoint(
                                x=float(child.attrib["x"]),
                                y=float(child.attrib["y"]),
                            )
                        )
                    except (KeyError, ValueError):
                        continue

                edges[bpmn_element_id] = DiagramEdge(
                    id=edge_id,
                    bpmn_element_id=bpmn_element_id,
                    waypoints=waypoints,
                )

        return DiagramLayout(
            shapes=shapes,
            edges=edges,
        )

    @staticmethod
    def _parse_optional_boolean(
        value: str | None,
    ) -> bool | None:
        if value is None:
            return None

        normalized = value.strip().lower()

        if normalized in {"true", "1"}:
            return True

        if normalized in {"false", "0"}:
            return False

        return None

    @staticmethod
    def _infer_lane_assignments(
        nodes: list[FlowNode],
        lanes: list[Lane],
        layout: DiagramLayout,
    ) -> None:
        """
        Assign nodes to lanes from diagram coordinates.

        Explicit flowNodeRef assignments always take priority.
        """

        lanes_by_process: dict[str, list[Lane]] = {}

        for lane in lanes:
            lanes_by_process.setdefault(
                lane.process_id,
                [],
            ).append(lane)

        for node in nodes:
            # Keep the explicit BPMN lane assignment when it exists.
            if node.lane_id is not None:
                continue

            node_shape = layout.shapes.get(node.id)

            if node_shape is None or node_shape.bounds is None:
                continue

            node_bounds = node_shape.bounds

            center_x = (
                node_bounds.x
                + node_bounds.width / 2
            )
            center_y = (
                node_bounds.y
                + node_bounds.height / 2
            )

            containing_lanes: list[
                tuple[float, Lane]
            ] = []

            for lane in lanes_by_process.get(
                node.process_id,
                [],
            ):
                lane_shape = layout.shapes.get(lane.id)

                if (
                    lane_shape is None
                    or lane_shape.bounds is None
                ):
                    continue

                lane_bounds = lane_shape.bounds

                contains_center = (
                    lane_bounds.x
                    <= center_x
                    <= lane_bounds.x + lane_bounds.width
                    and lane_bounds.y
                    <= center_y
                    <= lane_bounds.y + lane_bounds.height
                )

                if not contains_center:
                    continue

                # If nested lanes overlap, prefer the smallest one.
                area = (
                    lane_bounds.width
                    * lane_bounds.height
                )

                containing_lanes.append(
                    (area, lane)
                )

            if not containing_lanes:
                continue

            _, selected_lane = min(
                containing_lanes,
                key=lambda item: item[0],
            )

            node.lane_id = selected_lane.id
            node.lane_name = selected_lane.name

            if node.id not in selected_lane.flow_node_refs:
                selected_lane.flow_node_refs.append(
                    node.id
                )

    @staticmethod
    def _extract_metadata(
        root: ET.Element,
        source_path: Path,
        namespaces: dict[str, str],
        namespace_context: NamespaceContext,
    ) -> BpmnMetadata:
        """Extract technical metadata from BPMN definitions."""

        return BpmnMetadata(
            source_path=str(source_path),
            exporter=root.attrib.get("exporter"),
            exporter_version=root.attrib.get("exporterVersion"),
            target_namespace=root.attrib.get("targetNamespace"),
            namespaces=namespaces,
        )

    def _extract_processes(
        self,
        root: ET.Element,
        namespace_context: NamespaceContext,
    ) -> list[Process]:
        """Extract all top-level BPMN processes."""

        processes: list[Process] = []

        for element in list(root):
            if local_name(element.tag) != "process":
                continue

            process_id = element.attrib.get("id")

            if not process_id:
                raise BpmnParseError(
                    "A BPMN process is missing its required id."
                )

            is_executable_raw = element.attrib.get("isExecutable")

            is_executable = None
            if is_executable_raw is not None:
                is_executable = (
                    is_executable_raw.strip().lower() == "true"
                )

            flow_node_ids: list[str] = []
            sequence_flow_ids: list[str] = []

            for child in list(element):
                child_type = local_name(child.tag)
                child_id = child.attrib.get("id")

                if not child_id:
                    continue

                if child_type == "sequenceFlow":
                    sequence_flow_ids.append(child_id)
                elif child_type not in {
                    "laneSet",
                    "documentation",
                    "extensionElements",
                    "dataObject",
                    "dataObjectReference",
                    "dataStoreReference",
                    "association",
                    "textAnnotation",
                    "group",
                }:
                    flow_node_ids.append(child_id)

            processes.append(
                Process(
                    id=process_id,
                    name=normalize_text(element.attrib.get("name")),
                    documentation=first_child_text(
                        element,
                        "documentation",
                    ),
                    attributes=namespace_context.attributes(element),
                    is_executable=is_executable,
                    flow_node_ids=flow_node_ids,
                    sequence_flow_ids=sequence_flow_ids,
                )
            )

        return processes

    def _extract_participants(
        self,
        root: ET.Element,
        namespace_context: NamespaceContext,
    ) -> list[Participant]:
        """Extract participants from BPMN collaborations."""

        participants: list[Participant] = []

        for collaboration in list(root):
            if local_name(collaboration.tag) != "collaboration":
                continue

            for element in list(collaboration):
                if local_name(element.tag) != "participant":
                    continue

                participant_id = element.attrib.get("id")

                if not participant_id:
                    raise BpmnParseError(
                        "A BPMN participant is missing its required id."
                    )

                participants.append(
                    Participant(
                        id=participant_id,
                        name=normalize_text(
                            element.attrib.get("name")
                        ),
                        process_ref=element.attrib.get("processRef"),
                        attributes=namespace_context.attributes(element),
                    )
                )

        return participants

    def _extract_lanes(
        self,
        root: ET.Element,
        participants: list[Participant],
        namespace_context: NamespaceContext,
    ) -> list[Lane]:
        """Extract lanes and nested child lanes from every process."""

        participant_by_process = {
            participant.process_ref: participant.id
            for participant in participants
            if participant.process_ref
        }

        lanes: list[Lane] = []

        for process_element in list(root):
            if local_name(process_element.tag) != "process":
                continue

            process_id = process_element.attrib.get("id")

            if not process_id:
                continue

            participant_id = participant_by_process.get(process_id)

            for element in list(process_element):
                if local_name(element.tag) != "laneSet":
                    continue

                lanes.extend(
                    self._extract_lane_set(
                        lane_set=element,
                        process_id=process_id,
                        participant_id=participant_id,
                        parent_lane_id=None,
                        namespace_context=namespace_context,
                    )
                )

        return lanes

    def _extract_lane_set(
        self,
        lane_set: ET.Element,
        process_id: str,
        participant_id: str | None,
        parent_lane_id: str | None,
        namespace_context: NamespaceContext,
    ) -> list[Lane]:
        """Recursively extract lanes from a lane set."""

        lanes: list[Lane] = []

        for element in list(lane_set):
            if local_name(element.tag) != "lane":
                continue

            lane_id = element.attrib.get("id")

            if not lane_id:
                raise BpmnParseError(
                    "A BPMN lane is missing its required id."
                )

            child_lane_ids: list[str] = []

            for child in list(element):
                if local_name(child.tag) != "childLaneSet":
                    continue

                for nested_lane in list(child):
                    if local_name(nested_lane.tag) == "lane":
                        nested_id = nested_lane.attrib.get("id")
                        if nested_id:
                            child_lane_ids.append(nested_id)

            lane = Lane(
                id=lane_id,
                name=normalize_text(element.attrib.get("name")),
                documentation=first_child_text(
                    element,
                    "documentation",
                ),
                attributes=namespace_context.attributes(element),
                process_id=process_id,
                participant_id=participant_id,
                parent_lane_id=parent_lane_id,
                child_lane_ids=child_lane_ids,
                flow_node_refs=child_texts(
                    element,
                    "flowNodeRef",
                ),
            )

            lanes.append(lane)

            for child in list(element):
                if local_name(child.tag) != "childLaneSet":
                    continue

                lanes.extend(
                    self._extract_lane_set(
                        lane_set=child,
                        process_id=process_id,
                        participant_id=participant_id,
                        parent_lane_id=lane_id,
                        namespace_context=namespace_context,
                    )
                )

        return lanes

    def _extract_flow_nodes(
        self,
        root: ET.Element,
        participants: list[Participant],
        lanes: list[Lane],
        namespace_context: NamespaceContext,
    ) -> tuple[
        list[Task],
        list[Event],
        list[Gateway],
        list[SubProcess],
    ]:
        """Extract all supported BPMN flow nodes recursively."""

        tasks: list[Task] = []
        events: list[Event] = []
        gateways: list[Gateway] = []
        subprocesses: list[SubProcess] = []

        participant_by_process = {
            participant.process_ref: participant.id
            for participant in participants
            if participant.process_ref
        }

        lane_by_node_id = {
            node_id: lane
            for lane in lanes
            for node_id in lane.flow_node_refs
        }

        for process_element in list(root):
            if local_name(process_element.tag) != "process":
                continue

            process_id = process_element.attrib.get("id")

            if not process_id:
                continue

            participant_id = participant_by_process.get(process_id)

            self._extract_container_flow_nodes(
                container=process_element,
                process_id=process_id,
                participant_id=participant_id,
                parent_subprocess_id=None,
                lane_by_node_id=lane_by_node_id,
                namespace_context=namespace_context,
                tasks=tasks,
                events=events,
                gateways=gateways,
                subprocesses=subprocesses,
            )

        return tasks, events, gateways, subprocesses

    def _extract_container_flow_nodes(
        self,
        container: ET.Element,
        process_id: str,
        participant_id: str | None,
        parent_subprocess_id: str | None,
        lane_by_node_id: dict[str, Lane],
        namespace_context: NamespaceContext,
        tasks: list[Task],
        events: list[Event],
        gateways: list[Gateway],
        subprocesses: list[SubProcess],
    ) -> None:
        """Extract flow nodes from a process or subprocess container."""

        for element in list(container):
            tag = local_name(element.tag)

            if (
                tag not in TASK_TYPE_BY_TAG
                and tag not in EVENT_TYPE_BY_TAG
                and tag not in GATEWAY_TYPE_BY_TAG
                and tag not in SUBPROCESS_TYPE_BY_TAG
            ):
                continue

            element_id = element.attrib.get("id")
            lane = (
                lane_by_node_id.get(element_id)
                if element_id
                else None
            )

            context = FlowNodeContext(
                process_id=process_id,
                participant_id=participant_id,
                lane_id=lane.id if lane else None,
                lane_name=lane.name if lane else None,
                parent_subprocess_id=parent_subprocess_id,
            )

            if tag in TASK_TYPE_BY_TAG:
                tasks.append(
                    build_task(
                        element,
                        context,
                        namespace_context,
                    )
                )
                continue

            if tag in EVENT_TYPE_BY_TAG:
                events.append(
                    build_event(
                        element,
                        context,
                        namespace_context,
                    )
                )
                continue

            if tag in GATEWAY_TYPE_BY_TAG:
                gateways.append(
                    build_gateway(
                        element,
                        context,
                        namespace_context,
                    )
                )
                continue

            if tag in SUBPROCESS_TYPE_BY_TAG:
                subprocess = build_subprocess(
                    element,
                    context,
                    namespace_context,
                )
                subprocesses.append(subprocess)

                self._extract_container_flow_nodes(
                    container=element,
                    process_id=process_id,
                    participant_id=participant_id,
                    parent_subprocess_id=subprocess.id,
                    lane_by_node_id=lane_by_node_id,
                    namespace_context=namespace_context,
                    tasks=tasks,
                    events=events,
                    gateways=gateways,
                    subprocesses=subprocesses,
                )

    def _extract_sequence_flows(
        self,
        root: ET.Element,
        gateways: list[Gateway],
        namespace_context: NamespaceContext,
    ) -> list[SequenceFlow]:
        """Extract sequence flows recursively from processes and subprocesses."""

        default_flow_ids = {
            gateway.default_flow_id
            for gateway in gateways
            if gateway.default_flow_id
        }

        sequence_flows: list[SequenceFlow] = []

        for process_element in list(root):
            if local_name(process_element.tag) != "process":
                continue

            process_id = process_element.attrib.get("id")

            if not process_id:
                continue

            self._extract_container_sequence_flows(
                container=process_element,
                process_id=process_id,
                parent_subprocess_id=None,
                namespace_context=namespace_context,
                default_flow_ids=default_flow_ids,
                sequence_flows=sequence_flows,
            )

        return sequence_flows

    def _extract_container_sequence_flows(
        self,
        container: ET.Element,
        process_id: str,
        parent_subprocess_id: str | None,
        namespace_context: NamespaceContext,
        default_flow_ids: set[str],
        sequence_flows: list[SequenceFlow],
    ) -> None:
        """Extract sequence flows from one BPMN container."""

        for element in list(container):
            tag = local_name(element.tag)

            if tag == "sequenceFlow":
                sequence_flows.append(
                    build_sequence_flow(
                        element=element,
                        process_id=process_id,
                        parent_subprocess_id=parent_subprocess_id,
                        namespace_context=namespace_context,
                        default_flow_ids=default_flow_ids,
                    )
                )
                continue

            if tag in SUBPROCESS_TYPE_BY_TAG:
                subprocess_id = element.attrib.get("id")

                if not subprocess_id:
                    continue

                self._extract_container_sequence_flows(
                    container=element,
                    process_id=process_id,
                    parent_subprocess_id=subprocess_id,
                    namespace_context=namespace_context,
                    default_flow_ids=default_flow_ids,
                    sequence_flows=sequence_flows,
                )

    def _extract_data_elements(
        self,
        root: ET.Element,
        namespace_context: NamespaceContext,
    ) -> tuple[
        list[DataObject],
        list[DataAssociation],
    ]:
        """Extract BPMN documents and their activity associations."""

        data_objects: list[DataObject] = []
        data_associations: list[DataAssociation] = []

        for process_element in list(root):
            if local_name(process_element.tag) != "process":
                continue

            process_id = process_element.attrib.get("id")

            if not process_id:
                continue

            self._extract_container_data_elements(
                container=process_element,
                process_id=process_id,
                namespace_context=namespace_context,
                data_objects=data_objects,
                data_associations=data_associations,
            )

        return data_objects, data_associations

    def _extract_container_data_elements(
        self,
        container: ET.Element,
        process_id: str,
        namespace_context: NamespaceContext,
        data_objects: list[DataObject],
        data_associations: list[DataAssociation],
    ) -> None:
        """Extract documents and associations from a BPMN container."""

        for element in list(container):
            tag = local_name(element.tag)

            if tag in DATA_OBJECT_ELEMENT_TYPE_BY_TAG:
                data_objects.append(
                    build_data_object(
                        element=element,
                        process_id=process_id,
                        namespace_context=namespace_context,
                    )
                )
                continue

            if (
                tag in TASK_TYPE_BY_TAG
                or tag in SUBPROCESS_TYPE_BY_TAG
            ):
                activity_id = element.attrib.get("id")

                if activity_id:
                    self._extract_activity_data_associations(
                        activity=element,
                        process_id=process_id,
                        activity_id=activity_id,
                        namespace_context=namespace_context,
                        data_objects=data_objects,
                        data_associations=data_associations,
                    )

                if tag in SUBPROCESS_TYPE_BY_TAG:
                    self._extract_container_data_elements(
                        container=element,
                        process_id=process_id,
                        namespace_context=namespace_context,
                        data_objects=data_objects,
                        data_associations=data_associations,
                    )

    def _extract_activity_data_associations(
        self,
        activity: ET.Element,
        process_id: str,
        activity_id: str,
        namespace_context: NamespaceContext,
        data_objects: list[DataObject],
        data_associations: list[DataAssociation],
    ) -> None:
        """Extract associations and local inputs/outputs of one activity."""

        for child in list(activity):
            tag = local_name(child.tag)

            if tag in DATA_ASSOCIATION_ELEMENT_TYPE_BY_TAG:
                data_associations.append(
                    build_data_association(
                        element=child,
                        process_id=process_id,
                        parent_activity_id=activity_id,
                        namespace_context=namespace_context,
                    )
                )
                continue

            if tag != "ioSpecification":
                continue

            for io_element in list(child):
                io_tag = local_name(io_element.tag)

                if io_tag not in {
                    "dataInput",
                    "dataOutput",
                }:
                    continue

                data_objects.append(
                    build_data_object(
                        element=io_element,
                        process_id=process_id,
                        namespace_context=namespace_context,
                    )
                )

    def _extract_annotations_and_associations(
        self,
        root: ET.Element,
        namespace_context: NamespaceContext,
    ) -> tuple[
        list[TextAnnotation],
        list[Association],
    ]:
        """Extract text annotations and generic associations recursively."""

        annotations: list[TextAnnotation] = []
        associations: list[Association] = []

        for process_element in list(root):
            if local_name(process_element.tag) != "process":
                continue

            process_id = process_element.attrib.get("id")

            if not process_id:
                continue

            self._extract_container_annotations_and_associations(
                container=process_element,
                process_id=process_id,
                parent_subprocess_id=None,
                namespace_context=namespace_context,
                annotations=annotations,
                associations=associations,
            )

        return annotations, associations

    def _extract_container_annotations_and_associations(
        self,
        container: ET.Element,
        process_id: str,
        parent_subprocess_id: str | None,
        namespace_context: NamespaceContext,
        annotations: list[TextAnnotation],
        associations: list[Association],
    ) -> None:
        """Extract annotations and associations from one BPMN container."""

        for element in list(container):
            tag = local_name(element.tag)

            if tag == "textAnnotation":
                annotations.append(
                    build_text_annotation(
                        element=element,
                        process_id=process_id,
                        parent_subprocess_id=parent_subprocess_id,
                        namespace_context=namespace_context,
                    )
                )
                continue

            if tag == "association":
                associations.append(
                    build_association(
                        element=element,
                        process_id=process_id,
                        namespace_context=namespace_context,
                    )
                )
                continue

            if tag in SUBPROCESS_TYPE_BY_TAG:
                subprocess_id = element.attrib.get("id")

                if not subprocess_id:
                    continue

                self._extract_container_annotations_and_associations(
                    container=element,
                    process_id=process_id,
                    parent_subprocess_id=subprocess_id,
                    namespace_context=namespace_context,
                    annotations=annotations,
                    associations=associations,
                )

    @staticmethod
    def _enrich_annotation_relationships(
        annotations: list[TextAnnotation],
        associations: list[Association],
        tasks: list[Task],
        subprocesses: list[SubProcess],
    ) -> None:
        """Connect annotations to their associated BPMN activities."""

        annotations_by_id = {
            annotation.id: annotation
            for annotation in annotations
        }

        activities_by_id = {
            activity.id: activity
            for activity in [
                *tasks,
                *subprocesses,
            ]
        }

        for association in associations:
            source_annotation = annotations_by_id.get(
                association.source_ref
            )
            target_annotation = annotations_by_id.get(
                association.target_ref
            )

            # Activity -> annotation
            if target_annotation:
                associated_element_id = association.source_ref

                if (
                    associated_element_id
                    not in target_annotation.associated_element_ids
                ):
                    target_annotation.associated_element_ids.append(
                        associated_element_id
                    )

                activity = activities_by_id.get(associated_element_id)

                if (
                    activity
                    and target_annotation.id
                    not in activity.annotation_ids
                ):
                    activity.annotation_ids.append(
                        target_annotation.id
                    )

            # Annotation -> activity
            if source_annotation:
                associated_element_id = association.target_ref

                if (
                    associated_element_id
                    not in source_annotation.associated_element_ids
                ):
                    source_annotation.associated_element_ids.append(
                        associated_element_id
                    )

                activity = activities_by_id.get(associated_element_id)

                if (
                    activity
                    and source_annotation.id
                    not in activity.annotation_ids
                ):
                    activity.annotation_ids.append(
                        source_annotation.id
                    )

    @staticmethod
    def _enrich_document_relationships(
        data_objects: list[DataObject],
        data_associations: list[DataAssociation],
        tasks: list[Task],
        subprocesses: list[SubProcess],
    ) -> None:
        """Connect documents to the activities that consume or produce them."""

        documents_by_id = {
            document.id: document
            for document in data_objects
        }

        activities_by_id = {
            activity.id: activity
            for activity in [
                *tasks,
                *subprocesses,
            ]
        }

        # A reference may have no name while its original data object does.
        for document in data_objects:
            original_ref = document.original_data_object_ref

            if not original_ref or document.name:
                continue

            original_document = documents_by_id.get(original_ref)

            if original_document and original_document.name:
                document.name = original_document.name

        for association in data_associations:
            activity = activities_by_id.get(
                association.parent_activity_id
            )

            if not activity:
                continue

            if (
                association.element_type
                == BpmnElementType.DATA_INPUT_ASSOCIATION
            ):
                document_ids = [
                    reference
                    for reference in association.source_refs
                    if reference in documents_by_id
                ]

                for document_id in document_ids:
                    document = documents_by_id[document_id]

                    if activity.id not in document.consumed_by:
                        document.consumed_by.append(activity.id)

                    if document_id not in activity.input_document_ids:
                        activity.input_document_ids.append(document_id)

            elif (
                association.element_type
                == BpmnElementType.DATA_OUTPUT_ASSOCIATION
            ):
                document_id = association.target_ref

                if (
                    not document_id
                    or document_id not in documents_by_id
                ):
                    continue

                document = documents_by_id[document_id]

                if activity.id not in document.produced_by:
                    document.produced_by.append(activity.id)

                if document_id not in activity.output_document_ids:
                    activity.output_document_ids.append(document_id)

    def _build_process_graphs(
        self,
        processes: list[Process],
        tasks: list[Task],
        events: list[Event],
        gateways: list[Gateway],
        subprocesses: list[SubProcess],
        sequence_flows: list[SequenceFlow],
    ) -> dict[str, ProcessGraph]:
        """Build one graph per BPMN process."""

        all_nodes = [
            *tasks,
            *events,
            *gateways,
            *subprocesses,
        ]

        nodes_by_process: dict[str, set[str]] = {}

        for node in all_nodes:
            nodes_by_process.setdefault(
                node.process_id,
                set(),
            ).add(node.id)

        flows_by_process: dict[str, list[SequenceFlow]] = {}

        for flow in sequence_flows:
            flows_by_process.setdefault(
                flow.process_id,
                [],
            ).append(flow)

        graphs: dict[str, ProcessGraph] = {}

        for process in processes:
            process_node_ids = nodes_by_process.get(
                process.id,
                set(),
            )

            process_flows = flows_by_process.get(
                process.id,
                [],
            )

            adjacency: dict[str, list[str]] = {
                node_id: []
                for node_id in process_node_ids
            }

            predecessors: dict[str, list[str]] = {
                node_id: []
                for node_id in process_node_ids
            }

            edges: list[GraphEdge] = []

            for flow in process_flows:
                adjacency.setdefault(
                    flow.source_ref,
                    [],
                ).append(flow.target_ref)

                predecessors.setdefault(
                    flow.target_ref,
                    [],
                ).append(flow.source_ref)

                adjacency.setdefault(
                    flow.target_ref,
                    [],
                )

                predecessors.setdefault(
                    flow.source_ref,
                    [],
                )

                edges.append(
                    GraphEdge(
                        flow_id=flow.id,
                        source_ref=flow.source_ref,
                        target_ref=flow.target_ref,
                        label=flow.name,
                        condition=flow.condition_expression,
                    )
                )

            entry_node_ids = [
                node_id
                for node_id in process_node_ids
                if not predecessors.get(node_id)
            ]

            exit_node_ids = [
                node_id
                for node_id in process_node_ids
                if not adjacency.get(node_id)
            ]

            graphs[process.id] = ProcessGraph(
                adjacency=adjacency,
                predecessors=predecessors,
                edges=edges,
                entry_node_ids=entry_node_ids,
                exit_node_ids=exit_node_ids,
            )

        return graphs

    @staticmethod
    def _enrich_process_references(
        processes: list[Process],
        participants: list[Participant],
        lanes: list[Lane],
    ) -> None:
        """Populate process references after all elements are extracted."""

        processes_by_id = {
            process.id: process
            for process in processes
        }

        for participant in participants:
            if not participant.process_ref:
                continue

            process = processes_by_id.get(participant.process_ref)

            if process and participant.id not in process.participant_ids:
                process.participant_ids.append(participant.id)

        for lane in lanes:
            process = processes_by_id.get(lane.process_id)

            if process and lane.id not in process.lane_ids:
                process.lane_ids.append(lane.id)
