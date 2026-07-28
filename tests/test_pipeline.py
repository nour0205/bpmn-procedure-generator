from pathlib import Path

from pipeline.service import (
    ProcedureGenerationPipeline,
)


PIPELINE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process
        id="Process_Empty"
        name="Empty wrapper" />

    <bpmn:process
        id="Process_1"
        name="Procédure de validation">

        <bpmn:laneSet id="LaneSet_1">
            <bpmn:lane
                id="Lane_1"
                name="Direction métier">

                <bpmn:flowNodeRef>
                    Task_1
                </bpmn:flowNodeRef>

                <bpmn:flowNodeRef>
                    Event_1
                </bpmn:flowNodeRef>

                <bpmn:flowNodeRef>
                    Task_2
                </bpmn:flowNodeRef>

            </bpmn:lane>
        </bpmn:laneSet>

        <bpmn:startEvent id="Start_1" />

        <bpmn:userTask
            id="Task_1"
            name="Préparer le dossier" />

        <bpmn:intermediateThrowEvent
            id="Event_1"
            name="Réunion de validation" />

        <bpmn:userTask
            id="Task_2"
            name="Valider le dossier" />

        <bpmn:endEvent id="End_1" />

        <bpmn:sequenceFlow
            id="Flow_1"
            sourceRef="Start_1"
            targetRef="Task_1" />

        <bpmn:sequenceFlow
            id="Flow_2"
            sourceRef="Task_1"
            targetRef="Event_1" />

        <bpmn:sequenceFlow
            id="Flow_3"
            sourceRef="Event_1"
            targetRef="Task_2" />

        <bpmn:sequenceFlow
            id="Flow_4"
            sourceRef="Task_2"
            targetRef="End_1" />

    </bpmn:process>
</bpmn:definitions>
"""


def test_complete_pipeline(
    tmp_path: Path,
) -> None:
    bpmn_path = tmp_path / "pipeline.bpmn"

    bpmn_path.write_text(
        PIPELINE_BPMN,
        encoding="utf-8",
    )

    result = ProcedureGenerationPipeline().run(
        bpmn_path
    )

    assert (
        result.bpmn_model.process_by_id(
            "Process_1"
        )
        is not None
    )

    assert (
        result.procedure_model.metadata.process_id
        == "Process_1"
    )

    assert (
        result.procedure_model.operation_count
        == 3
    )

    assert (
        result.procedure_draft.operation_count
        == 3
    )

    descriptions = [
        operation.description
        for operation
        in result.procedure_draft.operations
    ]

    assert descriptions == [
        (
            "Direction métier réalise l’opération "
            "suivante : Préparer le dossier."
        ),
        (
            "Direction métier réalise l’opération "
            "suivante : Réunion de validation."
        ),
        (
            "Direction métier réalise l’opération "
            "suivante : Valider le dossier."
        ),
    ]


def test_pipeline_ignores_empty_wrapper_process(
    tmp_path: Path,
) -> None:
    bpmn_path = tmp_path / "pipeline.bpmn"

    bpmn_path.write_text(
        PIPELINE_BPMN,
        encoding="utf-8",
    )

    result = ProcedureGenerationPipeline().run(
        bpmn_path
    )

    assert (
        result.procedure_draft.process_id
        == "Process_1"
    )