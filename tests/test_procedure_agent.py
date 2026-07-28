from pathlib import Path

from agent.llm import (
    DeterministicOperationGenerator,
    OperationGenerator,
)
from agent.models import (
    OperationContext,
    OperationDraft,
)
from agent.orchestrator import ProcedureAgent
from bpmn.parser import BpmnParser
from procedure.mapper import ProcedureMapper


AGENT_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process
        id="Process_1"
        name="Procédure de contrat">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane
                id="Lane_1"
                name="Direction juridique">
                <bpmn:flowNodeRef>Task_1</bpmn:flowNodeRef>
                <bpmn:flowNodeRef>Task_2</bpmn:flowNodeRef>
            </bpmn:lane>
        </bpmn:laneSet>

        <bpmn:startEvent id="Start_1" />

        <bpmn:userTask
            id="Task_1"
            name="Vérifier le contrat" />

        <bpmn:userTask
            id="Task_2"
            name="Signer le contrat" />

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
    path = tmp_path / "agent.bpmn"
    path.write_text(
        AGENT_BPMN,
        encoding="utf-8",
    )

    bpmn_model = BpmnParser().parse_file(path)

    return ProcedureMapper().map_process(
        model=bpmn_model,
        process_id="Process_1",
    )


def test_generate_complete_procedure_draft(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    agent = ProcedureAgent(
        generator=DeterministicOperationGenerator()
    )

    draft = agent.generate(procedure)

    assert draft.process_id == "Process_1"
    assert draft.title == "Procédure de contrat"
    assert draft.operation_count == 2

    assert (
        draft.operations[0].description
        == (
            "Direction juridique réalise l’opération "
            "suivante : Vérifier le contrat."
        )
    )


def test_generated_operations_keep_identifiers(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    draft = ProcedureAgent(
        generator=DeterministicOperationGenerator()
    ).generate(procedure)

    first = draft.operation_by_id("Task_1")
    second = draft.operation_by_id("Task_2")

    assert first is not None
    assert second is not None

    assert first.operation_number == 1
    assert second.operation_number == 2


class FailingGenerator(OperationGenerator):
    def generate(
        self,
        context: OperationContext,
    ) -> OperationDraft:
        if context.operation_number == 2:
            raise RuntimeError("Simulated failure")

        return OperationDraft(
            operation_number=context.operation_number,
            bpmn_element_id=context.bpmn_element_id,
            description=context.raw_name,
            confidence=1.0,
        )


def test_one_failure_does_not_stop_generation(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    draft = ProcedureAgent(
        generator=FailingGenerator()
    ).generate(procedure)

    assert draft.operation_count == 2
    assert len(draft.generation_warnings) == 1

    failed_operation = draft.operations[1]

    assert failed_operation.requires_validation is True
    assert failed_operation.confidence == 0.0
    assert failed_operation.description == "Signer le contrat"


def test_procedure_draft_can_be_serialized(
    tmp_path: Path,
) -> None:
    procedure = build_procedure(tmp_path)

    draft = ProcedureAgent(
        generator=DeterministicOperationGenerator()
    ).generate(procedure)

    result = draft.model_dump(
        mode="json",
        exclude_none=True,
    )

    assert result["process_id"] == "Process_1"
    assert len(result["operations"]) == 2