from pathlib import Path

from agent.context_builder import OperationContextBuilder
from bpmn.parser import BpmnParser
from procedure.mapper import ProcedureMapper


CONTEXT_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process id="Process_1" name="Contract process">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane id="Lane_1" name="Legal Department">
                <bpmn:flowNodeRef>Task_1</bpmn:flowNodeRef>
                <bpmn:flowNodeRef>Task_2</bpmn:flowNodeRef>
            </bpmn:lane>
        </bpmn:laneSet>

        <bpmn:dataObject
            id="DataObject_1"
            name="Signed contract" />

        <bpmn:startEvent id="Start_1" />

        <bpmn:userTask
            id="Task_1"
            name="Review contract" />

        <bpmn:userTask
            id="Task_2"
            name="Sign contract">

            <bpmn:dataOutputAssociation id="OutputAssociation_1">
                <bpmn:targetRef>DataObject_1</bpmn:targetRef>
            </bpmn:dataOutputAssociation>

        </bpmn:userTask>

        <bpmn:textAnnotation id="Annotation_1">
            <bpmn:text>
                The contract must be signed after legal review.
            </bpmn:text>
        </bpmn:textAnnotation>

        <bpmn:association
            id="Association_1"
            sourceRef="Task_2"
            targetRef="Annotation_1" />

        <bpmn:endEvent id="End_1" />

        <bpmn:sequenceFlow
            id="Flow_1"
            sourceRef="Start_1"
            targetRef="Task_1" />

        <bpmn:sequenceFlow
            id="Flow_2"
            sourceRef="Task_1"
            targetRef="Task_2" />

        <bpmn:sequenceFlow
            id="Flow_3"
            sourceRef="Task_2"
            targetRef="End_1" />

    </bpmn:process>
</bpmn:definitions>
"""


def build_procedure(tmp_path: Path):
    path = tmp_path / "context.bpmn"
    path.write_text(
        CONTEXT_BPMN,
        encoding="utf-8",
    )

    bpmn_model = BpmnParser().parse_file(path)

    return ProcedureMapper().map_process(
        model=bpmn_model,
        process_id="Process_1",
    )


def test_build_all_operation_contexts(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    contexts = OperationContextBuilder().build_all(
        procedure
    )

    assert len(contexts) == 2
    assert contexts[0].raw_name == "Review contract"
    assert contexts[1].raw_name == "Sign contract"


def test_context_contains_actor_and_neighbours(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    context = OperationContextBuilder().build_all(
        procedure
    )[1]

    assert context.actor_name == "Legal Department"

    assert len(context.previous_operations) == 1
    assert (
        context.previous_operations[0].name
        == "Review contract"
    )

    assert context.next_operations == []


def test_context_contains_documents_and_notes(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    context = OperationContextBuilder().build_all(
        procedure
    )[1]

    assert len(context.output_documents) == 1
    assert (
        context.output_documents[0].name
        == "Signed contract"
    )
    assert (
        context.output_documents[0].direction
        == "output"
    )

    assert len(context.notes) == 1
    assert (
        context.notes[0].text
        == "The contract must be signed after legal review."
    )


def test_context_can_be_serialized(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    context = OperationContextBuilder().build_all(
        procedure
    )[0]

    result = context.model_dump(
        mode="json",
        exclude_none=True,
    )

    assert result["operation_number"] == 1
    assert result["raw_name"] == "Review contract"