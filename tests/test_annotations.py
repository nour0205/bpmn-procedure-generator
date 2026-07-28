from pathlib import Path

from bpmn.enums import (
    AnnotationCategory,
    AssociationDirection,
)
from bpmn.parser import BpmnParser


ANNOTATION_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process
        id="Process_1"
        name="Annotated process">

        <bpmn:startEvent id="Start_1" />

        <bpmn:userTask
            id="Task_1"
            name="Validate contract" />

        <bpmn:serviceTask
            id="Task_2"
            name="Upload signed contract" />

        <bpmn:textAnnotation id="Annotation_1">
            <bpmn:text>
                The contract must be reviewed before signature.
            </bpmn:text>
        </bpmn:textAnnotation>

        <bpmn:textAnnotation id="Annotation_2">
            <bpmn:text>
                The system automatically notifies procurement.
            </bpmn:text>
        </bpmn:textAnnotation>

        <bpmn:association
            id="Association_1"
            sourceRef="Task_1"
            targetRef="Annotation_1"
            associationDirection="None" />

        <bpmn:association
            id="Association_2"
            sourceRef="Annotation_2"
            targetRef="Task_2"
            associationDirection="One" />

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


def parse_example(tmp_path: Path):
    path = tmp_path / "annotations.bpmn"
    path.write_text(
        ANNOTATION_BPMN,
        encoding="utf-8",
    )

    return BpmnParser().parse_file(path)


def test_extract_text_annotations(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert len(model.annotations) == 2

    annotation = model.element_by_id("Annotation_1")

    assert annotation is not None
    assert (
        annotation.text
        == "The contract must be reviewed before signature."
    )
    assert (
        annotation.category
        == AnnotationCategory.UNCLASSIFIED
    )
    assert annotation.requires_validation is True


def test_extract_associations(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert len(model.associations) == 2

    association = model.element_by_id("Association_2")

    assert association is not None
    assert association.source_ref == "Annotation_2"
    assert association.target_ref == "Task_2"
    assert association.direction == AssociationDirection.ONE


def test_attach_annotation_to_task(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    task_1 = model.node_by_id("Task_1")
    annotation_1 = model.element_by_id("Annotation_1")

    assert task_1 is not None
    assert annotation_1 is not None

    assert task_1.annotation_ids == ["Annotation_1"]
    assert annotation_1.associated_element_ids == ["Task_1"]


def test_reverse_association_direction_is_supported(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    task_2 = model.node_by_id("Task_2")
    annotation_2 = model.element_by_id("Annotation_2")

    assert task_2 is not None
    assert annotation_2 is not None

    assert task_2.annotation_ids == ["Annotation_2"]
    assert annotation_2.associated_element_ids == ["Task_2"]


def test_annotations_for_element_lookup(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    annotations = model.annotations_for_element("Task_1")

    assert len(annotations) == 1
    assert annotations[0].id == "Annotation_1"