from pathlib import Path

from bpmn.enums import (
    EventDefinitionType,
    EventType,
    GatewayType,
    SubProcessType,
    TaskType,
)
from bpmn.parser import BpmnParser


FLOW_NODE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:collaboration id="Collaboration_1">
        <bpmn:participant
            id="Participant_1"
            name="Procurement"
            processRef="Process_1" />
    </bpmn:collaboration>

    <bpmn:process
        id="Process_1"
        name="Procurement process"
        isExecutable="false">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane id="Lane_1" name="SPCM">
                <bpmn:flowNodeRef>Task_1</bpmn:flowNodeRef>
                <bpmn:flowNodeRef>Gateway_1</bpmn:flowNodeRef>
                <bpmn:flowNodeRef>SubProcess_1</bpmn:flowNodeRef>
            </bpmn:lane>
        </bpmn:laneSet>

        <bpmn:startEvent id="StartEvent_1">
            <bpmn:timerEventDefinition id="TimerDefinition_1">
                <bpmn:timeDate>
                    2026-01-01T08:00:00
                </bpmn:timeDate>
            </bpmn:timerEventDefinition>
        </bpmn:startEvent>

        <bpmn:userTask
            id="Task_1"
            name="Create tender file">
            <bpmn:incoming>Flow_1</bpmn:incoming>
            <bpmn:outgoing>Flow_2</bpmn:outgoing>
        </bpmn:userTask>

        <bpmn:exclusiveGateway
            id="Gateway_1"
            name="File complete?"
            default="Flow_4">
            <bpmn:incoming>Flow_2</bpmn:incoming>
            <bpmn:outgoing>Flow_3</bpmn:outgoing>
            <bpmn:outgoing>Flow_4</bpmn:outgoing>
        </bpmn:exclusiveGateway>

        <bpmn:subProcess
            id="SubProcess_1"
            name="Validate tender file">

            <bpmn:startEvent id="SubStart_1" />

            <bpmn:serviceTask
                id="SubTask_1"
                name="Run automatic validation" />

            <bpmn:endEvent id="SubEnd_1" />
        </bpmn:subProcess>

        <bpmn:endEvent id="EndEvent_1" />
    </bpmn:process>
</bpmn:definitions>
"""


def parse_example(tmp_path: Path):
    path = tmp_path / "flow_nodes.bpmn"
    path.write_text(
        FLOW_NODE_BPMN,
        encoding="utf-8",
    )

    return BpmnParser().parse_file(path)


def test_extract_tasks_events_and_gateways(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert len(model.tasks) == 2
    assert len(model.events) == 4
    assert len(model.gateways) == 1
    assert len(model.subprocesses) == 1

    task = model.node_by_id("Task_1")

    assert task is not None
    assert task.name == "Create tender file"
    assert task.task_type == TaskType.USER
    assert task.lane_id == "Lane_1"
    assert task.lane_name == "SPCM"
    assert task.incoming == ["Flow_1"]
    assert task.outgoing == ["Flow_2"]


def test_extract_gateway_information(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    gateway = model.node_by_id("Gateway_1")

    assert gateway is not None
    assert gateway.gateway_type == GatewayType.EXCLUSIVE
    assert gateway.default_flow_id == "Flow_4"
    assert gateway.outgoing == ["Flow_3", "Flow_4"]


def test_extract_timer_event_definition(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    start_event = model.node_by_id("StartEvent_1")

    assert start_event is not None
    assert start_event.event_type == EventType.START
    assert len(start_event.definitions) == 1

    definition = start_event.definitions[0]

    assert (
        definition.definition_type
        == EventDefinitionType.TIMER
    )
    assert definition.timer_type == "timeDate"
    assert definition.timer_value == "2026-01-01T08:00:00"


def test_extract_subprocess_recursively(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    subprocess = model.node_by_id("SubProcess_1")
    child_task = model.node_by_id("SubTask_1")

    assert subprocess is not None
    assert subprocess.subprocess_type == SubProcessType.EMBEDDED
    assert subprocess.child_node_ids == [
        "SubStart_1",
        "SubTask_1",
        "SubEnd_1",
    ]

    assert child_task is not None
    assert child_task.task_type == TaskType.SERVICE
    assert child_task.parent_subprocess_id == "SubProcess_1"