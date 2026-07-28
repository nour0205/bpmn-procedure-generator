from pathlib import Path

from bpmn.parser import BpmnParser


SEQUENCE_FLOW_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process
        id="Process_1"
        name="Example process">

        <bpmn:startEvent id="Start_1">
            <bpmn:outgoing>Flow_1</bpmn:outgoing>
        </bpmn:startEvent>

        <bpmn:userTask
            id="Task_1"
            name="Check request">
            <bpmn:incoming>Flow_1</bpmn:incoming>
            <bpmn:outgoing>Flow_2</bpmn:outgoing>
        </bpmn:userTask>

        <bpmn:exclusiveGateway
            id="Gateway_1"
            name="Approved?"
            default="Flow_4">
            <bpmn:incoming>Flow_2</bpmn:incoming>
            <bpmn:outgoing>Flow_3</bpmn:outgoing>
            <bpmn:outgoing>Flow_4</bpmn:outgoing>
        </bpmn:exclusiveGateway>

        <bpmn:userTask
            id="Task_2"
            name="Approve request">
            <bpmn:incoming>Flow_3</bpmn:incoming>
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
            targetRef="Gateway_1" />

        <bpmn:sequenceFlow
            id="Flow_3"
            name="Yes"
            sourceRef="Gateway_1"
            targetRef="Task_2">
            <bpmn:conditionExpression>
                approved = true
            </bpmn:conditionExpression>
        </bpmn:sequenceFlow>

        <bpmn:sequenceFlow
            id="Flow_4"
            name="No"
            sourceRef="Gateway_1"
            targetRef="End_1" />

        <bpmn:sequenceFlow
            id="Flow_5"
            sourceRef="Task_2"
            targetRef="End_1" />
    </bpmn:process>
</bpmn:definitions>
"""


def parse_example(tmp_path: Path):
    path = tmp_path / "sequence_flows.bpmn"
    path.write_text(
        SEQUENCE_FLOW_BPMN,
        encoding="utf-8",
    )

    return BpmnParser().parse_file(path)


def test_extract_sequence_flows(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert len(model.sequence_flows) == 5

    flow = next(
        item
        for item in model.sequence_flows
        if item.id == "Flow_3"
    )

    assert flow.name == "Yes"
    assert flow.source_ref == "Gateway_1"
    assert flow.target_ref == "Task_2"
    assert flow.condition_expression == "approved = true"
    assert flow.is_default is False


def test_extract_default_flow(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    flow = next(
        item
        for item in model.sequence_flows
        if item.id == "Flow_4"
    )

    assert flow.is_default is True
    assert flow.name == "No"


def test_build_process_graph(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    graph = model.graphs["Process_1"]

    assert graph.adjacency["Start_1"] == ["Task_1"]
    assert graph.adjacency["Task_1"] == ["Gateway_1"]
    assert set(
        graph.adjacency["Gateway_1"]
    ) == {"Task_2", "End_1"}

    assert graph.predecessors["Task_1"] == ["Start_1"]
    assert graph.entry_node_ids == ["Start_1"]
    assert graph.exit_node_ids == ["End_1"]