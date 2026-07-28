from bpmn.enums import (
    BpmnElementType,
    TaskType,
)
from bpmn.models import (
    BpmnMetadata,
    BpmnModel,
    Process,
    Task,
)


def test_create_minimal_bpmn_model() -> None:
    process = Process(
        id="Process_1",
        name="Préparation de l'appel d'offres",
    )

    task = Task(
        id="Task_1",
        element_type=BpmnElementType.USER_TASK,
        name="Créer un dossier d'appel d'offres",
        process_id="Process_1",
        task_type=TaskType.USER,
    )

    model = BpmnModel(
        metadata=BpmnMetadata(
            source_path="example.bpmn",
        ),
        processes=[process],
        tasks=[task],
    )

    assert model.element_count == 2
    assert model.node_by_id("Task_1") == task
    assert model.process_by_id("Process_1") == process
    assert model.summary["task_count"] == 1


def test_model_can_be_serialized() -> None:
    model = BpmnModel(
        metadata=BpmnMetadata(
            source_path="example.bpmn",
        )
    )

    result = model.model_dump(
        mode="json",
        exclude_none=True,
    )

    assert result["metadata"]["source_path"] == "example.bpmn"
    assert result["processes"] == []