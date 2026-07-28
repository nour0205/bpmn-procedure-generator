from pathlib import Path

from bpmn.enums import (
    BpmnElementType,
    DocumentDirection,
)
from bpmn.parser import BpmnParser


DATA_OBJECT_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/bpmn">

    <bpmn:process
        id="Process_1"
        name="Document process">

        <bpmn:dataObject
            id="DataObject_Request"
            name="Purchase request" />

        <bpmn:dataObjectReference
            id="DataReference_Request"
            dataObjectRef="DataObject_Request" />

        <bpmn:dataObject
            id="DataObject_Report"
            name="Validation report" />

        <bpmn:dataObjectReference
            id="DataReference_Report"
            dataObjectRef="DataObject_Report" />

        <bpmn:startEvent id="Start_1" />

        <bpmn:userTask
            id="Task_1"
            name="Validate purchase request">

            <bpmn:ioSpecification>
                <bpmn:dataInput
                    id="Input_1"
                    name="Request input" />

                <bpmn:dataOutput
                    id="Output_1"
                    name="Report output" />

                <bpmn:inputSet id="InputSet_1">
                    <bpmn:dataInputRefs>
                        Input_1
                    </bpmn:dataInputRefs>
                </bpmn:inputSet>

                <bpmn:outputSet id="OutputSet_1">
                    <bpmn:dataOutputRefs>
                        Output_1
                    </bpmn:dataOutputRefs>
                </bpmn:outputSet>
            </bpmn:ioSpecification>

            <bpmn:dataInputAssociation id="InputAssociation_1">
                <bpmn:sourceRef>
                    DataReference_Request
                </bpmn:sourceRef>
                <bpmn:targetRef>Input_1</bpmn:targetRef>
            </bpmn:dataInputAssociation>

            <bpmn:dataOutputAssociation id="OutputAssociation_1">
                <bpmn:sourceRef>Output_1</bpmn:sourceRef>
                <bpmn:targetRef>
                    DataReference_Report
                </bpmn:targetRef>
            </bpmn:dataOutputAssociation>

        </bpmn:userTask>

        <bpmn:endEvent id="End_1" />

        <bpmn:sequenceFlow
            id="Flow_1"
            sourceRef="Start_1"
            targetRef="Task_1" />

        <bpmn:sequenceFlow
            id="Flow_2"
            sourceRef="Task_1"
            targetRef="End_1" />

    </bpmn:process>
</bpmn:definitions>
"""


def parse_example(tmp_path: Path):
    path = tmp_path / "data_objects.bpmn"
    path.write_text(
        DATA_OBJECT_BPMN,
        encoding="utf-8",
    )

    return BpmnParser().parse_file(path)


def test_extract_data_objects(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert len(model.data_objects) == 6

    request_reference = model.element_by_id(
        "DataReference_Request"
    )

    assert request_reference is not None
    assert (
        request_reference.element_type
        == BpmnElementType.DATA_OBJECT_REFERENCE
    )
    assert request_reference.name == "Purchase request"
    assert (
        request_reference.original_data_object_ref
        == "DataObject_Request"
    )


def test_extract_data_associations(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    assert len(model.data_associations) == 2

    input_association = model.element_by_id(
        "InputAssociation_1"
    )

    assert input_association is not None
    assert input_association.source_refs == [
        "DataReference_Request"
    ]
    assert input_association.target_ref == "Input_1"


def test_enrich_task_documents(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    task = model.node_by_id("Task_1")

    assert task is not None

    assert task.input_document_ids == [
        "DataReference_Request"
    ]

    assert task.output_document_ids == [
        "DataReference_Report"
    ]

    input_documents, output_documents = (
        model.documents_for_activity("Task_1")
    )

    assert [
        document.name
        for document in input_documents
    ] == ["Purchase request"]

    assert [
        document.name
        for document in output_documents
    ] == ["Validation report"]


def test_document_direction(
    tmp_path: Path,
) -> None:
    model = parse_example(tmp_path)

    request = model.element_by_id(
        "DataReference_Request"
    )

    report = model.element_by_id(
        "DataReference_Report"
    )

    assert request is not None
    assert report is not None

    assert request.direction == DocumentDirection.INPUT
    assert report.direction == DocumentDirection.OUTPUT