from pathlib import Path

from bpmn.parser import BpmnParser


INVALID_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process
        id="Process_1"
        name="Validation example">

        <bpmn:startEvent id="Start_1">
            <bpmn:outgoing>Flow_1</bpmn:outgoing>
        </bpmn:startEvent>

        <bpmn:userTask
            id="Task_1">
            <bpmn:incoming>Flow_1</bpmn:incoming>
            <bpmn:outgoing>Flow_2</bpmn:outgoing>
        </bpmn:userTask>

        <bpmn:exclusiveGateway
            id="Gateway_1">
            <bpmn:incoming>Flow_2</bpmn:incoming>
            <bpmn:outgoing>Flow_3</bpmn:outgoing>
            <bpmn:outgoing>Flow_4</bpmn:outgoing>
        </bpmn:exclusiveGateway>

        <bpmn:userTask
            id="Task_2"
            name="Reachable task">
            <bpmn:incoming>Flow_3</bpmn:incoming>
        </bpmn:userTask>

        <bpmn:userTask
            id="Task_Unreachable"
            name="Unreachable task" />

        <bpmn:textAnnotation id="Annotation_1">
            <bpmn:text>
                This note is not connected.
            </bpmn:text>
        </bpmn:textAnnotation>

        <bpmn:dataObject
            id="Document_1"
            name="Unused document" />

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
            sourceRef="Gateway_1"
            targetRef="Task_2" />

        <bpmn:sequenceFlow
            id="Flow_4"
            sourceRef="Gateway_1"
            targetRef="Task_2" />

    </bpmn:process>
</bpmn:definitions>
"""


def parse_example(tmp_path: Path):
    path = tmp_path / "invalid.bpmn"
    path.write_text(
        INVALID_BPMN,
        encoding="utf-8",
    )

    return BpmnParser().parse_file(path)


def validation_codes(model) -> set[str]:
    return {
        issue.code
        for issue in model.validation.issues
    }


def test_detect_missing_end_event(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert (
        "PROCESS_WITHOUT_END_EVENT"
        in validation_codes(model)
    )


def test_detect_unnamed_task(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    issues = [
        issue
        for issue in model.validation.issues
        if issue.code == "UNNAMED_FLOW_NODE"
    ]

    assert len(issues) == 1
    assert issues[0].element_id == "Task_1"


def test_detect_unlabeled_gateway_branches(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    issues = [
        issue
        for issue in model.validation.issues
        if issue.code == "UNLABELED_GATEWAY_BRANCH"
    ]

    assert len(issues) == 2


def test_detect_unassociated_annotation(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert (
        "UNASSOCIATED_ANNOTATION"
        in validation_codes(model)
    )


def test_detect_unused_document(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert (
        "UNUSED_BUSINESS_DOCUMENT"
        in validation_codes(model)
    )


def test_detect_unreachable_task(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    issues = [
        issue
        for issue in model.validation.issues
        if issue.code == "UNREACHABLE_FLOW_NODE"
    ]

    unreachable_ids = {
        issue.element_id
        for issue in issues
    }

    assert "Task_Unreachable" in unreachable_ids


def test_warnings_do_not_make_model_invalid(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert model.validation.is_valid is True
    assert len(model.validation.errors) == 0
    assert len(model.validation.warnings) > 0