from pathlib import Path

from bpmn.parser import BpmnParser


LAYOUT_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
    xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
    xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process id="Process_1" name="Layout process">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane
                id="Lane_1"
                name="Procurement" />

            <bpmn:lane
                id="Lane_2"
                name="Finance" />
        </bpmn:laneSet>

        <bpmn:userTask
            id="Task_1"
            name="Prepare request" />

        <bpmn:userTask
            id="Task_2"
            name="Review budget" />

        <bpmn:sequenceFlow
            id="Flow_1"
            sourceRef="Task_1"
            targetRef="Task_2" />

    </bpmn:process>

    <bpmndi:BPMNDiagram id="Diagram_1">
        <bpmndi:BPMNPlane
            id="Plane_1"
            bpmnElement="Process_1">

            <bpmndi:BPMNShape
                id="LaneShape_1"
                bpmnElement="Lane_1">
                <dc:Bounds
                    x="0"
                    y="0"
                    width="1000"
                    height="200" />
            </bpmndi:BPMNShape>

            <bpmndi:BPMNShape
                id="LaneShape_2"
                bpmnElement="Lane_2">
                <dc:Bounds
                    x="0"
                    y="200"
                    width="1000"
                    height="200" />
            </bpmndi:BPMNShape>

            <bpmndi:BPMNShape
                id="TaskShape_1"
                bpmnElement="Task_1">
                <dc:Bounds
                    x="100"
                    y="60"
                    width="120"
                    height="80" />
            </bpmndi:BPMNShape>

            <bpmndi:BPMNShape
                id="TaskShape_2"
                bpmnElement="Task_2">
                <dc:Bounds
                    x="300"
                    y="260"
                    width="120"
                    height="80" />
            </bpmndi:BPMNShape>

            <bpmndi:BPMNEdge
                id="FlowEdge_1"
                bpmnElement="Flow_1">
                <di:waypoint x="220" y="100" />
                <di:waypoint x="300" y="300" />
            </bpmndi:BPMNEdge>

        </bpmndi:BPMNPlane>
    </bpmndi:BPMNDiagram>

</bpmn:definitions>
"""


def test_infer_lanes_from_layout(
    tmp_path: Path,
) -> None:
    path = tmp_path / "layout.bpmn"
    path.write_text(
        LAYOUT_BPMN,
        encoding="utf-8",
    )

    model = BpmnParser().parse_file(path)

    task_1 = model.node_by_id("Task_1")
    task_2 = model.node_by_id("Task_2")

    assert task_1 is not None
    assert task_2 is not None

    assert task_1.lane_id == "Lane_1"
    assert task_1.lane_name == "Procurement"

    assert task_2.lane_id == "Lane_2"
    assert task_2.lane_name == "Finance"


def test_inferred_refs_are_added_to_lanes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "layout.bpmn"
    path.write_text(
        LAYOUT_BPMN,
        encoding="utf-8",
    )

    model = BpmnParser().parse_file(path)

    lane_1 = model.lane_by_id("Lane_1")
    lane_2 = model.lane_by_id("Lane_2")

    assert lane_1 is not None
    assert lane_2 is not None

    assert lane_1.flow_node_refs == ["Task_1"]
    assert lane_2.flow_node_refs == ["Task_2"]


def test_extract_layout_shapes_and_edges(
    tmp_path: Path,
) -> None:
    path = tmp_path / "layout.bpmn"
    path.write_text(
        LAYOUT_BPMN,
        encoding="utf-8",
    )

    model = BpmnParser().parse_file(path)

    assert "Task_1" in model.layout.shapes
    assert "Lane_1" in model.layout.shapes
    assert "Flow_1" in model.layout.edges

    task_bounds = (
        model.layout.shapes["Task_1"].bounds
    )

    assert task_bounds is not None
    assert task_bounds.x == 100.0
    assert task_bounds.y == 60.0

    edge = model.layout.edges["Flow_1"]

    assert len(edge.waypoints) == 2