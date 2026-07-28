from pathlib import Path

from bpmn.parser import BpmnParser


MINIMAL_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
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
        name="Call for tenders"
        isExecutable="false">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane
                id="Lane_1"
                name="SPCM">
                <bpmn:flowNodeRef>Task_1</bpmn:flowNodeRef>
            </bpmn:lane>
        </bpmn:laneSet>

        <bpmn:startEvent id="StartEvent_1" />

        <bpmn:userTask
            id="Task_1"
            name="Create tender file" />

        <bpmn:endEvent id="EndEvent_1" />

        <bpmn:sequenceFlow
            id="Flow_1"
            sourceRef="StartEvent_1"
            targetRef="Task_1" />

        <bpmn:sequenceFlow
            id="Flow_2"
            sourceRef="Task_1"
            targetRef="EndEvent_1" />
    </bpmn:process>
</bpmn:definitions>
"""


def test_parse_process_participant_and_lane(
    tmp_path: Path,
) -> None:
    bpmn_path = tmp_path / "example.bpmn"
    bpmn_path.write_text(
        MINIMAL_BPMN,
        encoding="utf-8",
    )

    model = BpmnParser().parse_file(bpmn_path)

    assert len(model.processes) == 1
    assert len(model.participants) == 1
    assert len(model.lanes) == 1

    process = model.processes[0]
    participant = model.participants[0]
    lane = model.lanes[0]

    assert process.id == "Process_1"
    assert process.name == "Call for tenders"
    assert process.is_executable is False

    assert participant.process_ref == process.id
    assert participant.id in process.participant_ids

    assert lane.name == "SPCM"
    assert lane.process_id == process.id
    assert lane.participant_id == participant.id
    assert lane.flow_node_refs == ["Task_1"]
    assert lane.id in process.lane_ids

    assert len(model.tasks) == 1
    assert len(model.events) == 2
    assert model.gateways == []
    assert model.subprocesses == []

    task = model.tasks[0]
    assert task.id == "Task_1"
    assert task.process_id == process.id
    assert task.participant_id == participant.id
    assert task.lane_id == lane.id
    assert task.lane_name == lane.name

    assert {event.id for event in model.events} == {
        "StartEvent_1",
        "EndEvent_1",
    }


def test_parser_extracts_source_metadata(
    tmp_path: Path,
) -> None:
    bpmn_path = tmp_path / "example.bpmn"
    bpmn_path.write_text(
        MINIMAL_BPMN,
        encoding="utf-8",
    )

    model = BpmnParser().parse_file(bpmn_path)

    assert model.metadata.source_path == str(bpmn_path)
    assert (
        model.metadata.target_namespace
        == "https://example.com/bpmn"
    )
    assert (
        model.metadata.namespaces["bpmn"]
        == "http://www.omg.org/spec/BPMN/20100524/MODEL"
    )
