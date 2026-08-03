from __future__ import annotations

from pathlib import Path

from docx import Document

from document.bundle_builder import DocumentBundleBuilder
from document.loader import GeneratedOperation, GeneratedProcedure
from document.procedure_generator import ProcedureDocumentGenerator
from pipeline.service import ProcedureGenerationPipeline
from procedure.models import ProcedureModel

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/procedure_template.docx"


def _procedure(relative_path: str) -> ProcedureModel:
    return ProcedureGenerationPipeline().run(
        ROOT / relative_path
    ).procedure_model


def _generated_mirror(
    procedure: ProcedureModel,
) -> GeneratedProcedure:
    """Build a local generated contract without Kaggle or output files."""

    return GeneratedProcedure(
        process_id=procedure.metadata.process_id,
        title=procedure.metadata.title,
        operation_count=len(procedure.operations),
        operations=[
            GeneratedOperation(
                operation_number=operation.number,
                bpmn_element_id=operation.bpmn_element_id,
                description=(
                    f"Description contrôlée de l’opération "
                    f"« {operation.raw_name} »."
                ),
                confidence=0.95,
            )
            for operation in procedure.operations
        ],
    )


def _bundle(relative_path: str):
    procedure = _procedure(relative_path)
    generated = _generated_mirror(procedure)
    bundle = DocumentBundleBuilder().build(
        procedure=procedure,
        generated=generated,
    )
    return procedure, bundle


def _operation_rows(document_path: Path) -> dict[int, str]:
    document = Document(document_path)
    table = ProcedureDocumentGenerator._find_operations_table(
        document
    )

    rows: dict[int, str] = {}
    for row in table.rows[1:]:
        number_text = row.cells[1].text.strip()
        if not number_text.isdigit():
            continue
        rows[int(number_text)] = row.cells[2].text.strip()

    return rows


def test_bundle_propagates_convergence_metadata() -> None:
    procedure, bundle = _bundle(
        "bpmn_files/Détermination des besoins d'appro.bpmn"
    )

    source = next(
        operation
        for operation in procedure.operations
        if operation.raw_name
        == "Lancer le calcul des besoins (CBN) sur le SI"
    )
    rendered = next(
        operation
        for operation in bundle.operations
        if operation.bpmn_element_id
        == source.bpmn_element_id
    )

    assert rendered.is_common_continuation is True
    assert (
        rendered.convergence_gateway_ids
        == source.convergence_gateway_ids
    )


def test_determination_document_renders_structure_not_actor_specific_text(
    tmp_path: Path,
) -> None:
    procedure, bundle = _bundle(
        "bpmn_files/Détermination des besoins d'appro.bpmn"
    )
    output = tmp_path / "determination.docx"

    ProcedureDocumentGenerator().generate(
        bundle=bundle,
        template_path=TEMPLATE,
        output_path=output,
    )

    rows = _operation_rows(output)

    branch_operation = next(
        operation
        for operation in procedure.operations
        if operation.raw_name
        == "Renseigner le niveau de la consommation moyenne prévisionnelle"
    )
    common_operation = next(
        operation
        for operation in procedure.operations
        if operation.raw_name
        == "Lancer le calcul des besoins (CBN) sur le SI"
    )

    branch_text = rows[branch_operation.number]
    common_text = rows[common_operation.number]

    assert "Article nouvellement introduit ? — Oui" in branch_text
    assert "Article nouvellement introduit ? — Non" not in common_text
    assert "Convergence" in common_text
    assert (
        "Les différents scénarios se rejoignent avant cette opération."
        in common_text
    )


def test_direct_branch_is_rendered_in_convergence_block(
    tmp_path: Path,
) -> None:
    _, bundle = _bundle(
        "bpmn_files/Détermination des besoins d'appro.bpmn"
    )
    operation = next(
        item
        for item in bundle.operations
        if item.raw_name
        == "Lancer le calcul des besoins (CBN) sur le SI"
    )
    output = tmp_path / "procedure.docx"

    ProcedureDocumentGenerator().generate(
        bundle=bundle,
        template_path=TEMPLATE,
        output_path=output,
    )

    text = _operation_rows(output)[operation.number]

    assert "Convergence" in text
    assert (
        "La branche « Non » accède directement "
        "à cette opération."
        in text
    )
    assert (
        "Article nouvellement introduit ? — Non"
        not in text
    )


def test_suivi_loop_back_is_not_rendered_as_convergence(
    tmp_path: Path,
) -> None:
    procedure, bundle = _bundle(
        "bpmn_files/Suivi des commandes.bpmn"
    )
    output = tmp_path / "suivi.docx"

    ProcedureDocumentGenerator().generate(
        bundle=bundle,
        template_path=TEMPLATE,
        output_path=output,
    )

    rows = _operation_rows(output)

    reception = next(
        operation
        for operation in procedure.operations
        if operation.raw_name == "Gestion des réceptions"
    )
    reminder_letter = next(
        operation
        for operation in procedure.operations
        if operation.raw_name == "Générer les lettres de relance"
    )

    assert "Convergence" in rows[reception.number]
    assert (
        "Les différents scénarios se rejoignent avant cette opération."
        in rows[reception.number]
    )
    assert "Convergence" not in rows[reminder_letter.number]
