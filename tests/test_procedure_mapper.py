from pathlib import Path

from bpmn.parser import BpmnParser
from procedure.mapper import ProcedureMapper
from procedure.models import ProcedureElementKind


PROCEDURE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:collaboration id="Collaboration_1">
        <bpmn:participant
            id="Participant_1"
            name="Procurement Department"
            processRef="Process_1" />
    </bpmn:collaboration>

    <bpmn:process
        id="Process_1"
        name="Tender procedure"
        isExecutable="false">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane id="Lane_1" name="SPCM">
                <bpmn:flowNodeRef>Task_1</bpmn:flowNodeRef>
                <bpmn:flowNodeRef>Call_1</bpmn:flowNodeRef>
            </bpmn:lane>

            <bpmn:lane id="Lane_2" name="General Management">
                <bpmn:flowNodeRef>Event_Validation</bpmn:flowNodeRef>
                <bpmn:flowNodeRef>Task_2</bpmn:flowNodeRef>
            </bpmn:lane>
        </bpmn:laneSet>

        <bpmn:startEvent id="Start_1">
            <bpmn:outgoing>Flow_1</bpmn:outgoing>
        </bpmn:startEvent>

        <bpmn:userTask
            id="Task_1"
            name="Create tender file">
            <bpmn:incoming>Flow_1</bpmn:incoming>
            <bpmn:outgoing>Flow_2</bpmn:outgoing>
        </bpmn:userTask>

        <bpmn:callActivity
            id="Call_1"
            name="Determine procurement needs"
            calledElement="NeedsProcess">
            <bpmn:incoming>Flow_2</bpmn:incoming>
            <bpmn:outgoing>Flow_3</bpmn:outgoing>
        </bpmn:callActivity>

        <bpmn:intermediateThrowEvent
            id="Event_Validation"
            name="Validation meeting">
            <bpmn:incoming>Flow_3</bpmn:incoming>
            <bpmn:outgoing>Flow_4</bpmn:outgoing>
        </bpmn:intermediateThrowEvent>

        <bpmn:userTask
            id="Task_2"
            name="Validate procurement program">
            <bpmn:incoming>Flow_4</bpmn:incoming>
            <bpmn:outgoing>Flow_5</bpmn:outgoing>
        </bpmn:userTask>

        <bpmn:endEvent id="End_1">
            <bpmn:incoming>Flow_5</bpmn:incoming>
        </bpmn:endEvent>

        <bpmn:sequenceFlow
            id="Flow_1"
            sourceRef="Start_1"
            targetRef="Task_1" />

        <bpmn:sequenceFlow
            id="Flow_2"
            sourceRef="Task_1"
            targetRef="Call_1" />

        <bpmn:sequenceFlow
            id="Flow_3"
            sourceRef="Call_1"
            targetRef="Event_Validation" />

        <bpmn:sequenceFlow
            id="Flow_4"
            sourceRef="Event_Validation"
            targetRef="Task_2" />

        <bpmn:sequenceFlow
            id="Flow_5"
            sourceRef="Task_2"
            targetRef="End_1" />

    </bpmn:process>
</bpmn:definitions>
"""


def parse_procedure(tmp_path: Path):
    bpmn_path = tmp_path / "procedure.bpmn"
    bpmn_path.write_text(
        PROCEDURE_BPMN,
        encoding="utf-8",
    )

    bpmn_model = BpmnParser().parse_file(bpmn_path)

    return ProcedureMapper().map_process(
        model=bpmn_model,
        process_id="Process_1",
    )


def test_map_bpmn_to_procedure(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    assert procedure.metadata.process_id == "Process_1"
    assert procedure.metadata.title == "Tender procedure"
    assert (
        procedure.metadata.participant_name
        == "Procurement Department"
    )

    assert procedure.operation_count == 4


def test_map_actors_from_lanes(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    actor_names = {
        actor.name
        for actor in procedure.actors
    }

    assert actor_names == {
        "SPCM",
        "General Management",
    }


def test_map_standard_task_as_operation(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    task = procedure.operation_by_id("Task_1")

    assert task is not None
    assert task.number == 1
    assert task.raw_name == "Create tender file"
    assert task.actor_name == "SPCM"
    assert (
        task.element_kind
        == ProcedureElementKind.OPERATION
    )
    assert task.source_type == "userTask"


def test_map_call_activity_as_subprocess(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    call_activity = procedure.operation_by_id("Call_1")

    assert call_activity is not None
    assert call_activity.number == 2
    assert (
        call_activity.raw_name
        == "Determine procurement needs"
    )
    assert call_activity.actor_name == "SPCM"
    assert (
        call_activity.element_kind
        == ProcedureElementKind.SUBPROCESS
    )
    assert call_activity.source_type == "callActivity"


def test_map_named_intermediate_event_as_business_event(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    event = procedure.operation_by_id(
        "Event_Validation"
    )

    assert event is not None
    assert event.number == 3
    assert event.raw_name == "Validation meeting"
    assert event.actor_name == "General Management"
    assert (
        event.element_kind
        == ProcedureElementKind.BUSINESS_EVENT
    )
    assert event.source_type == "intermediateThrowEvent"


def test_map_final_task_after_business_event(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    task = procedure.operation_by_id("Task_2")

    assert task is not None
    assert task.number == 4
    assert (
        task.raw_name
        == "Validate procurement program"
    )
    assert task.actor_name == "General Management"
    assert (
        task.element_kind
        == ProcedureElementKind.OPERATION
    )


def test_previous_and_next_operations(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    task_1 = procedure.operation_by_id("Task_1")
    call_activity = procedure.operation_by_id("Call_1")
    event = procedure.operation_by_id(
        "Event_Validation"
    )
    task_2 = procedure.operation_by_id("Task_2")

    assert task_1 is not None
    assert call_activity is not None
    assert event is not None
    assert task_2 is not None

    assert task_1.previous_operation_ids == []
    assert task_1.next_operation_ids == ["Call_1"]

    assert call_activity.previous_operation_ids == [
        "Task_1"
    ]
    assert call_activity.next_operation_ids == [
        "Event_Validation"
    ]

    assert event.previous_operation_ids == ["Call_1"]
    assert event.next_operation_ids == ["Task_2"]

    assert task_2.previous_operation_ids == [
        "Event_Validation"
    ]
    assert task_2.next_operation_ids == []


def test_operations_are_numbered_in_execution_order(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    ordered_ids = [
        operation.bpmn_element_id
        for operation in procedure.operations
    ]

    assert ordered_ids == [
        "Task_1",
        "Call_1",
        "Event_Validation",
        "Task_2",
    ]

    assert [
        operation.number
        for operation in procedure.operations
    ] == [1, 2, 3, 4]


def test_start_and_end_events_are_not_numbered(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    operation_ids = {
        operation.bpmn_element_id
        for operation in procedure.operations
    }

    assert "Start_1" not in operation_ids
    assert "End_1" not in operation_ids


def test_validation_summary_is_forwarded(
    tmp_path: Path,
) -> None:
    procedure = parse_procedure(tmp_path)

    assert procedure.validation.is_valid is True
    assert procedure.validation.error_count == 0