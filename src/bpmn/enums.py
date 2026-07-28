"""Enumerations used by the semantic BPMN domain model."""

from __future__ import annotations

from enum import StrEnum


class BpmnElementType(StrEnum):
    """Supported BPMN element types."""

    PROCESS = "process"
    PARTICIPANT = "participant"
    LANE = "lane"

    TASK = "task"
    USER_TASK = "userTask"
    SERVICE_TASK = "serviceTask"
    MANUAL_TASK = "manualTask"
    SCRIPT_TASK = "scriptTask"
    BUSINESS_RULE_TASK = "businessRuleTask"
    SEND_TASK = "sendTask"
    RECEIVE_TASK = "receiveTask"
    CALL_ACTIVITY = "callActivity"

    SUB_PROCESS = "subProcess"
    AD_HOC_SUB_PROCESS = "adHocSubProcess"
    TRANSACTION = "transaction"

    START_EVENT = "startEvent"
    END_EVENT = "endEvent"
    INTERMEDIATE_CATCH_EVENT = "intermediateCatchEvent"
    INTERMEDIATE_THROW_EVENT = "intermediateThrowEvent"
    BOUNDARY_EVENT = "boundaryEvent"

    EXCLUSIVE_GATEWAY = "exclusiveGateway"
    INCLUSIVE_GATEWAY = "inclusiveGateway"
    PARALLEL_GATEWAY = "parallelGateway"
    EVENT_BASED_GATEWAY = "eventBasedGateway"
    COMPLEX_GATEWAY = "complexGateway"

    SEQUENCE_FLOW = "sequenceFlow"
    MESSAGE_FLOW = "messageFlow"

    DATA_OBJECT = "dataObject"
    DATA_OBJECT_REFERENCE = "dataObjectReference"
    DATA_STORE_REFERENCE = "dataStoreReference"
    DATA_INPUT = "dataInput"
    DATA_OUTPUT = "dataOutput"

    DATA_INPUT_ASSOCIATION = "dataInputAssociation"
    DATA_OUTPUT_ASSOCIATION = "dataOutputAssociation"

    TEXT_ANNOTATION = "textAnnotation"
    ASSOCIATION = "association"
    GROUP = "group"


class TaskType(StrEnum):
    """Semantic task categories."""

    GENERIC = "generic"
    USER = "user"
    SERVICE = "service"
    MANUAL = "manual"
    SCRIPT = "script"
    BUSINESS_RULE = "business_rule"
    SEND = "send"
    RECEIVE = "receive"
    CALL_ACTIVITY = "call_activity"


class EventType(StrEnum):
    """Position or behavior of a BPMN event."""

    START = "start"
    END = "end"
    INTERMEDIATE_CATCH = "intermediate_catch"
    INTERMEDIATE_THROW = "intermediate_throw"
    BOUNDARY = "boundary"


class EventDefinitionType(StrEnum):
    """BPMN event trigger or result type."""

    NONE = "none"
    MESSAGE = "message"
    TIMER = "timer"
    ERROR = "error"
    ESCALATION = "escalation"
    CANCEL = "cancel"
    COMPENSATION = "compensation"
    CONDITIONAL = "conditional"
    LINK = "link"
    SIGNAL = "signal"
    TERMINATE = "terminate"
    MULTIPLE = "multiple"
    PARALLEL_MULTIPLE = "parallel_multiple"


class GatewayType(StrEnum):
    """Supported BPMN gateway types."""

    EXCLUSIVE = "exclusive"
    INCLUSIVE = "inclusive"
    PARALLEL = "parallel"
    EVENT_BASED = "event_based"
    COMPLEX = "complex"


class SubProcessType(StrEnum):
    """Supported subprocess categories."""

    EMBEDDED = "embedded"
    AD_HOC = "ad_hoc"
    TRANSACTION = "transaction"
    CALL_ACTIVITY = "call_activity"


class AssociationDirection(StrEnum):
    """Direction of a BPMN association."""

    NONE = "None"
    ONE = "One"
    BOTH = "Both"


class DocumentDirection(StrEnum):
    """How a document is used by an activity."""

    INPUT = "input"
    OUTPUT = "output"
    INPUT_OUTPUT = "input_output"
    UNKNOWN = "unknown"


class AnnotationCategory(StrEnum):
    """Semantic classification used by the document generator."""

    BUSINESS_RULE = "business_rule"
    INTERNAL_CONTROL = "internal_control"
    SYSTEM_NOTE = "system_note"
    DOCUMENT_NOTE = "document_note"
    EXCEPTION = "exception"
    PROCEDURAL_NOTE = "procedural_note"
    GENERAL_NOTE = "general_note"
    UNCLASSIFIED = "unclassified"


class ValidationSeverity(StrEnum):
    """Severity level of a validation issue."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SourceType(StrEnum):
    """Origin of a value in the generated procedure."""

    BPMN_XML = "bpmn_xml"
    BPMN_EXTENSION = "bpmn_extension"
    USER_INPUT = "user_input"
    DETERMINISTIC_INFERENCE = "deterministic_inference"
    LLM_GENERATED = "llm_generated"
