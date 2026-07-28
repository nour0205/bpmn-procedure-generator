from document.bundle_builder import DocumentBundleBuilder
from document.loader import load_generated_procedure
from pipeline.service import ProcedureGenerationPipeline


def test_build_document_bundle() -> None:
    result = ProcedureGenerationPipeline().run(
        "bpmn_files/Détermination des besoins d'appro.bpmn"
    )

    generated = load_generated_procedure(
        "output/determination_besoins/llm/generated_procedure.json"
    )

    bundle = DocumentBundleBuilder().build(
        procedure=result.procedure_model,
        generated=generated,
    )

    assert bundle.metadata.process_id == generated.process_id
    assert bundle.operation_count == generated.operation_count
    assert len(bundle.procedure.operations) == generated.operation_count
    assert len(bundle.specification.operations) == generated.operation_count


def test_bundle_preserves_document_semantics() -> None:
    result = ProcedureGenerationPipeline().run(
        "bpmn_files/Détermination des besoins d'appro.bpmn"
    )

    generated = load_generated_procedure(
        "output/determination_besoins/llm/generated_procedure.json"
    )

    bundle = DocumentBundleBuilder().build(
        procedure=result.procedure_model,
        generated=generated,
    )

    assert bundle.operation_count == 13

    subprocesses = [
        operation
        for operation in bundle.operations
        if operation.element_kind.value == "subprocess"
    ]

    business_events = [
        operation
        for operation in bundle.operations
        if operation.element_kind.value == "business_event"
    ]

    assert len(subprocesses) >= 1
    assert len(business_events) >= 1

    operation_3 = next(
        operation
        for operation in bundle.operations
        if operation.number == 3
    )

    assert operation_3.requires_validation is True
    assert operation_3.notes
