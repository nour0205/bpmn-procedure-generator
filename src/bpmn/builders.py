"""Builders that convert BPMN XML elements into typed flow-node models."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .enums import (
    AnnotationCategory,
    AssociationDirection,
    BpmnElementType,
    EventDefinitionType,
    EventType,
    GatewayType,
    SubProcessType,
    TaskType,
)
from .models import (
    Association,
    DataAssociation,
    DataObject,
    Event,
    EventDefinition,
    Gateway,
    SequenceFlow,
    SubProcess,
    Task,
    TextAnnotation,
)
from .namespaces import (
    NamespaceContext,
    child_texts,
    first_child_text,
    local_name,
    normalize_text,
)


TASK_TYPE_BY_TAG: dict[str, TaskType] = {
    "task": TaskType.GENERIC,
    "userTask": TaskType.USER,
    "serviceTask": TaskType.SERVICE,
    "manualTask": TaskType.MANUAL,
    "scriptTask": TaskType.SCRIPT,
    "businessRuleTask": TaskType.BUSINESS_RULE,
    "sendTask": TaskType.SEND,
    "receiveTask": TaskType.RECEIVE,
    "callActivity": TaskType.CALL_ACTIVITY,
}

TASK_ELEMENT_TYPE_BY_TAG: dict[str, BpmnElementType] = {
    "task": BpmnElementType.TASK,
    "userTask": BpmnElementType.USER_TASK,
    "serviceTask": BpmnElementType.SERVICE_TASK,
    "manualTask": BpmnElementType.MANUAL_TASK,
    "scriptTask": BpmnElementType.SCRIPT_TASK,
    "businessRuleTask": BpmnElementType.BUSINESS_RULE_TASK,
    "sendTask": BpmnElementType.SEND_TASK,
    "receiveTask": BpmnElementType.RECEIVE_TASK,
    "callActivity": BpmnElementType.CALL_ACTIVITY,
}

EVENT_TYPE_BY_TAG: dict[str, EventType] = {
    "startEvent": EventType.START,
    "endEvent": EventType.END,
    "intermediateCatchEvent": EventType.INTERMEDIATE_CATCH,
    "intermediateThrowEvent": EventType.INTERMEDIATE_THROW,
    "boundaryEvent": EventType.BOUNDARY,
}

EVENT_ELEMENT_TYPE_BY_TAG: dict[str, BpmnElementType] = {
    "startEvent": BpmnElementType.START_EVENT,
    "endEvent": BpmnElementType.END_EVENT,
    "intermediateCatchEvent": BpmnElementType.INTERMEDIATE_CATCH_EVENT,
    "intermediateThrowEvent": BpmnElementType.INTERMEDIATE_THROW_EVENT,
    "boundaryEvent": BpmnElementType.BOUNDARY_EVENT,
}

GATEWAY_TYPE_BY_TAG: dict[str, GatewayType] = {
    "exclusiveGateway": GatewayType.EXCLUSIVE,
    "inclusiveGateway": GatewayType.INCLUSIVE,
    "parallelGateway": GatewayType.PARALLEL,
    "eventBasedGateway": GatewayType.EVENT_BASED,
    "complexGateway": GatewayType.COMPLEX,
}

GATEWAY_ELEMENT_TYPE_BY_TAG: dict[str, BpmnElementType] = {
    "exclusiveGateway": BpmnElementType.EXCLUSIVE_GATEWAY,
    "inclusiveGateway": BpmnElementType.INCLUSIVE_GATEWAY,
    "parallelGateway": BpmnElementType.PARALLEL_GATEWAY,
    "eventBasedGateway": BpmnElementType.EVENT_BASED_GATEWAY,
    "complexGateway": BpmnElementType.COMPLEX_GATEWAY,
}

SUBPROCESS_TYPE_BY_TAG: dict[str, SubProcessType] = {
    "subProcess": SubProcessType.EMBEDDED,
    "adHocSubProcess": SubProcessType.AD_HOC,
    "transaction": SubProcessType.TRANSACTION,
}

SUBPROCESS_ELEMENT_TYPE_BY_TAG: dict[str, BpmnElementType] = {
    "subProcess": BpmnElementType.SUB_PROCESS,
    "adHocSubProcess": BpmnElementType.AD_HOC_SUB_PROCESS,
    "transaction": BpmnElementType.TRANSACTION,
}

EVENT_DEFINITION_TYPE_BY_TAG: dict[str, EventDefinitionType] = {
    "messageEventDefinition": EventDefinitionType.MESSAGE,
    "timerEventDefinition": EventDefinitionType.TIMER,
    "errorEventDefinition": EventDefinitionType.ERROR,
    "escalationEventDefinition": EventDefinitionType.ESCALATION,
    "cancelEventDefinition": EventDefinitionType.CANCEL,
    "compensateEventDefinition": EventDefinitionType.COMPENSATION,
    "conditionalEventDefinition": EventDefinitionType.CONDITIONAL,
    "linkEventDefinition": EventDefinitionType.LINK,
    "signalEventDefinition": EventDefinitionType.SIGNAL,
    "terminateEventDefinition": EventDefinitionType.TERMINATE,
    "multipleEventDefinition": EventDefinitionType.MULTIPLE,
    "parallelMultipleEventDefinition": EventDefinitionType.PARALLEL_MULTIPLE,
}

DATA_OBJECT_ELEMENT_TYPE_BY_TAG: dict[str, BpmnElementType] = {
    "dataObject": BpmnElementType.DATA_OBJECT,
    "dataObjectReference": BpmnElementType.DATA_OBJECT_REFERENCE,
    "dataStoreReference": BpmnElementType.DATA_STORE_REFERENCE,
    "dataInput": BpmnElementType.DATA_INPUT,
    "dataOutput": BpmnElementType.DATA_OUTPUT,
}

DATA_ASSOCIATION_ELEMENT_TYPE_BY_TAG: dict[str, BpmnElementType] = {
    "dataInputAssociation": BpmnElementType.DATA_INPUT_ASSOCIATION,
    "dataOutputAssociation": BpmnElementType.DATA_OUTPUT_ASSOCIATION,
}


@dataclass(frozen=True)
class FlowNodeContext:
    """Context inherited by an extracted BPMN flow node."""

    process_id: str
    participant_id: str | None
    lane_id: str | None
    lane_name: str | None
    parent_subprocess_id: str | None


def parse_boolean(
    value: str | None,
    default: bool | None = None,
) -> bool | None:
    """Parse an XML boolean value."""

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"true", "1"}:
        return True

    if normalized in {"false", "0"}:
        return False

    return default


def require_element_id(
    element: ET.Element,
    element_kind: str,
) -> str:
    """Return an element ID or raise a clear parsing error."""

    element_id = element.attrib.get("id")

    if not element_id:
        raise ValueError(
            f"A BPMN {element_kind} is missing its required id."
        )

    return element_id


def common_flow_node_fields(
    element: ET.Element,
    context: FlowNodeContext,
    namespace_context: NamespaceContext,
) -> dict[str, object]:
    """Build fields shared by tasks, events, gateways and subprocesses."""

    return {
        "id": require_element_id(
            element,
            local_name(element.tag),
        ),
        "name": normalize_text(element.attrib.get("name")),
        "documentation": first_child_text(
            element,
            "documentation",
        ),
        "attributes": namespace_context.attributes(element),
        "process_id": context.process_id,
        "participant_id": context.participant_id,
        "lane_id": context.lane_id,
        "lane_name": context.lane_name,
        "parent_subprocess_id": context.parent_subprocess_id,
        "incoming": child_texts(element, "incoming"),
        "outgoing": child_texts(element, "outgoing"),
    }


def build_task(
    element: ET.Element,
    context: FlowNodeContext,
    namespace_context: NamespaceContext,
) -> Task:
    """Build a typed task from a BPMN task element."""

    tag = local_name(element.tag)

    if tag not in TASK_TYPE_BY_TAG:
        raise ValueError(f"Unsupported BPMN task type: {tag}")

    fields = common_flow_node_fields(
        element,
        context,
        namespace_context,
    )

    return Task(
        **fields,
        element_type=TASK_ELEMENT_TYPE_BY_TAG[tag],
        task_type=TASK_TYPE_BY_TAG[tag],
        called_element=element.attrib.get("calledElement"),
    )


def build_event_definition(
    element: ET.Element,
    namespace_context: NamespaceContext,
) -> EventDefinition:
    """Build an event trigger/result definition."""

    tag = local_name(element.tag)

    definition_type = EVENT_DEFINITION_TYPE_BY_TAG.get(
        tag,
        EventDefinitionType.NONE,
    )

    reference = (
        element.attrib.get("messageRef")
        or element.attrib.get("errorRef")
        or element.attrib.get("signalRef")
        or element.attrib.get("escalationRef")
    )

    timer_type: str | None = None
    timer_value: str | None = None

    if definition_type == EventDefinitionType.TIMER:
        for child in list(element):
            child_tag = local_name(child.tag)

            if child_tag in {
                "timeDate",
                "timeDuration",
                "timeCycle",
            }:
                timer_type = child_tag
                timer_value = normalize_text(child.text)
                break

    return EventDefinition(
        id=element.attrib.get("id"),
        definition_type=definition_type,
        reference=reference,
        timer_type=timer_type,
        timer_value=timer_value,
        attributes=namespace_context.attributes(element),
    )


def build_event(
    element: ET.Element,
    context: FlowNodeContext,
    namespace_context: NamespaceContext,
) -> Event:
    """Build a typed BPMN event."""

    tag = local_name(element.tag)

    if tag not in EVENT_TYPE_BY_TAG:
        raise ValueError(f"Unsupported BPMN event type: {tag}")

    definitions = [
        build_event_definition(
            child,
            namespace_context,
        )
        for child in list(element)
        if local_name(child.tag).endswith("EventDefinition")
    ]

    fields = common_flow_node_fields(
        element,
        context,
        namespace_context,
    )

    event_type = EVENT_TYPE_BY_TAG[tag]

    return Event(
        **fields,
        element_type=EVENT_ELEMENT_TYPE_BY_TAG[tag],
        event_type=event_type,
        definitions=definitions,
        attached_to_ref=element.attrib.get("attachedToRef"),
        cancel_activity=(
            parse_boolean(
                element.attrib.get("cancelActivity"),
                default=True,
            )
            if event_type == EventType.BOUNDARY
            else None
        ),
    )


def build_gateway(
    element: ET.Element,
    context: FlowNodeContext,
    namespace_context: NamespaceContext,
) -> Gateway:
    """Build a typed BPMN gateway."""

    tag = local_name(element.tag)

    if tag not in GATEWAY_TYPE_BY_TAG:
        raise ValueError(f"Unsupported BPMN gateway type: {tag}")

    fields = common_flow_node_fields(
        element,
        context,
        namespace_context,
    )

    return Gateway(
        **fields,
        element_type=GATEWAY_ELEMENT_TYPE_BY_TAG[tag],
        gateway_type=GATEWAY_TYPE_BY_TAG[tag],
        default_flow_id=element.attrib.get("default"),
    )


def build_subprocess(
    element: ET.Element,
    context: FlowNodeContext,
    namespace_context: NamespaceContext,
) -> SubProcess:
    """Build a typed BPMN subprocess."""

    tag = local_name(element.tag)

    if tag not in SUBPROCESS_TYPE_BY_TAG:
        raise ValueError(f"Unsupported BPMN subprocess type: {tag}")

    subprocess_id = require_element_id(
        element,
        tag,
    )

    child_node_ids: list[str] = []
    child_flow_ids: list[str] = []

    for child in list(element):
        child_tag = local_name(child.tag)
        child_id = child.attrib.get("id")

        if not child_id:
            continue

        if child_tag == "sequenceFlow":
            child_flow_ids.append(child_id)
        elif (
            child_tag in TASK_TYPE_BY_TAG
            or child_tag in EVENT_TYPE_BY_TAG
            or child_tag in GATEWAY_TYPE_BY_TAG
            or child_tag in SUBPROCESS_TYPE_BY_TAG
        ):
            child_node_ids.append(child_id)

    fields = common_flow_node_fields(
        element,
        context,
        namespace_context,
    )

    return SubProcess(
        **fields,
        element_type=SUBPROCESS_ELEMENT_TYPE_BY_TAG[tag],
        subprocess_type=SUBPROCESS_TYPE_BY_TAG[tag],
        triggered_by_event=bool(
            parse_boolean(
                element.attrib.get("triggeredByEvent"),
                default=False,
            )
        ),
        child_node_ids=child_node_ids,
        child_flow_ids=child_flow_ids,
    )


def build_sequence_flow(
    element: ET.Element,
    process_id: str,
    parent_subprocess_id: str | None,
    namespace_context: NamespaceContext,
    default_flow_ids: set[str],
) -> SequenceFlow:
    """Build a typed BPMN sequence flow."""

    flow_id = require_element_id(
        element,
        "sequenceFlow",
    )

    source_ref = element.attrib.get("sourceRef")
    target_ref = element.attrib.get("targetRef")

    if not source_ref:
        raise ValueError(
            f"Sequence flow {flow_id} is missing sourceRef."
        )

    if not target_ref:
        raise ValueError(
            f"Sequence flow {flow_id} is missing targetRef."
        )

    condition_expression = first_child_text(
        element,
        "conditionExpression",
    )

    return SequenceFlow(
        id=flow_id,
        name=normalize_text(element.attrib.get("name")),
        documentation=first_child_text(
            element,
            "documentation",
        ),
        attributes=namespace_context.attributes(element),
        process_id=process_id,
        parent_subprocess_id=parent_subprocess_id,
        source_ref=source_ref,
        target_ref=target_ref,
        condition_expression=condition_expression,
        is_default=flow_id in default_flow_ids,
    )


def build_data_object(
    element: ET.Element,
    process_id: str | None,
    namespace_context: NamespaceContext,
) -> DataObject:
    """Build a BPMN data object, reference, input, output or data store."""

    tag = local_name(element.tag)

    if tag not in DATA_OBJECT_ELEMENT_TYPE_BY_TAG:
        raise ValueError(f"Unsupported BPMN data element: {tag}")

    data_state: str | None = None

    for child in list(element):
        if local_name(child.tag) == "dataState":
            data_state = normalize_text(
                child.attrib.get("name")
                or child.text
            )
            break

    return DataObject(
        id=require_element_id(element, tag),
        element_type=DATA_OBJECT_ELEMENT_TYPE_BY_TAG[tag],
        name=normalize_text(element.attrib.get("name")),
        documentation=first_child_text(
            element,
            "documentation",
        ),
        attributes=namespace_context.attributes(element),
        process_id=process_id,
        data_state=data_state,
        item_subject_ref=element.attrib.get("itemSubjectRef"),
        original_data_object_ref=(
            element.attrib.get("dataObjectRef")
            or element.attrib.get("dataStoreRef")
        ),
    )


def build_data_association(
    element: ET.Element,
    process_id: str,
    parent_activity_id: str,
    namespace_context: NamespaceContext,
) -> DataAssociation:
    """Build a BPMN input or output data association."""

    tag = local_name(element.tag)

    if tag not in DATA_ASSOCIATION_ELEMENT_TYPE_BY_TAG:
        raise ValueError(
            f"Unsupported BPMN data association type: {tag}"
        )

    source_refs = child_texts(
        element,
        "sourceRef",
    )

    target_refs = child_texts(
        element,
        "targetRef",
    )

    transformation = first_child_text(
        element,
        "transformation",
    )

    assignment_expressions: list[str] = []

    for child in list(element):
        if local_name(child.tag) != "assignment":
            continue

        for assignment_child in list(child):
            expression = normalize_text(assignment_child.text)

            if expression:
                assignment_expressions.append(expression)

    return DataAssociation(
        id=require_element_id(
            element,
            tag,
        ),
        element_type=DATA_ASSOCIATION_ELEMENT_TYPE_BY_TAG[tag],
        name=normalize_text(element.attrib.get("name")),
        documentation=first_child_text(
            element,
            "documentation",
        ),
        attributes=namespace_context.attributes(element),
        process_id=process_id,
        parent_activity_id=parent_activity_id,
        source_refs=source_refs,
        target_ref=target_refs[0] if target_refs else None,
        transformation=transformation,
        assignment_expressions=assignment_expressions,
    )


def build_text_annotation(
    element: ET.Element,
    process_id: str,
    parent_subprocess_id: str | None,
    namespace_context: NamespaceContext,
) -> TextAnnotation:
    """Build a BPMN text annotation."""

    annotation_id = require_element_id(
        element,
        "textAnnotation",
    )

    text = first_child_text(
        element,
        "text",
    )

    if not text:
        text = normalize_text(element.text)

    if not text:
        text = ""

    return TextAnnotation(
        id=annotation_id,
        name=normalize_text(element.attrib.get("name")),
        documentation=first_child_text(
            element,
            "documentation",
        ),
        attributes=namespace_context.attributes(element),
        process_id=process_id,
        parent_subprocess_id=parent_subprocess_id,
        text=text,
        category=AnnotationCategory.UNCLASSIFIED,
        associated_element_ids=[],
        classification_confidence=0.0,
        requires_validation=True,
    )


def build_association(
    element: ET.Element,
    process_id: str,
    namespace_context: NamespaceContext,
) -> Association:
    """Build a generic BPMN association."""

    association_id = require_element_id(
        element,
        "association",
    )

    source_ref = element.attrib.get("sourceRef")
    target_ref = element.attrib.get("targetRef")

    if not source_ref:
        raise ValueError(
            f"Association {association_id} is missing sourceRef."
        )

    if not target_ref:
        raise ValueError(
            f"Association {association_id} is missing targetRef."
        )

    direction_raw = element.attrib.get(
        "associationDirection",
        AssociationDirection.NONE.value,
    )

    try:
        direction = AssociationDirection(direction_raw)
    except ValueError:
        direction = AssociationDirection.NONE

    return Association(
        id=association_id,
        name=normalize_text(element.attrib.get("name")),
        documentation=first_child_text(
            element,
            "documentation",
        ),
        attributes=namespace_context.attributes(element),
        process_id=process_id,
        source_ref=source_ref,
        target_ref=target_ref,
        direction=direction,
    )
