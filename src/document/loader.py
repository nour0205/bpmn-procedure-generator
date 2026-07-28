"""Load and validate the LLM-generated procedure JSON.

The generated procedure is an integration contract between the Kaggle
inference notebook and the local document pipeline.  The contract remains
strict (unknown fields are rejected), while supporting the enriched metadata
exported by the current notebook.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)


class GeneratedBaseModel(BaseModel):
    """Strict base model for every generated-procedure payload."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class GeneratedAssociatedNote(GeneratedBaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class GeneratedSemanticItem(GeneratedBaseModel):
    """Document or business-rule item copied from deterministic context.

    The parser currently emits only a subset of these fields depending on the
    item type.  Keeping one explicit strict model avoids accepting arbitrary
    dictionaries while remaining compatible with both notes/rules/documents.
    """

    id: str | None = None
    name: str | None = None
    text: str | None = None
    label: str | None = None
    description: str | None = None
    value: str | None = None
    content: str | None = None
    source_type: str | None = None
    produced_by_operation_ids: list[str] = Field(default_factory=list)
    consumed_by_operation_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_readable_value(self) -> "GeneratedSemanticItem":
        if not any(
            value and str(value).strip()
            for value in (
                self.name,
                self.text,
                self.label,
                self.description,
                self.value,
                self.content,
            )
        ):
            raise ValueError(
                "A semantic item must contain at least one readable value."
            )
        return self


GeneratedBusinessRule = Annotated[
    str | GeneratedSemanticItem,
    Field(union_mode="left_to_right"),
]


class GeneratedOperationReference(GeneratedBaseModel):
    """Deterministic reference to a previous or next operation."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    actor_name: str | None = None
    element_kind: str = Field(min_length=1)


class GeneratedOperationBranch(GeneratedBaseModel):
    """Decision branch attached to a generated operation."""

    gateway_id: str = Field(min_length=1)
    gateway_name: str | None = None
    label: str | None = None
    condition: str | None = None
    is_default: bool = False
    target_element_id: str = Field(min_length=1)
    target_name: str | None = None


class GeneratedDecisionBranch(GeneratedBaseModel):
    label: str | None = None
    condition: str | None = None
    is_default: bool = False
    target_element_id: str = Field(min_length=1)
    target_name: str | None = None


class GeneratedDecision(GeneratedBaseModel):
    gateway_id: str = Field(min_length=1)
    gateway_name: str | None = None
    source_operation_number: int = Field(ge=1)
    source_bpmn_element_id: str = Field(min_length=1)
    branches: list[GeneratedDecisionBranch] = Field(min_length=1)


class GeneratedProcedureQualitySummary(GeneratedBaseModel):
    operations_requiring_validation: list[int] = Field(default_factory=list)
    placeholder_count: int = Field(default=0, ge=0)
    missing_note_count: int = Field(default=0, ge=0)


class GeneratedOperation(GeneratedBaseModel):
    """One enriched operation emitted by the Kaggle generator."""

    operation_number: int = Field(ge=1)
    bpmn_element_id: str = Field(min_length=1)

    # Deterministic mirror fields used for end-to-end consistency checks.
    raw_name: str | None = None
    actor_name: str | None = None
    element_kind: str | None = None
    source_type: str | None = None
    execution_mode: str | None = None
    event_role: str | None = None

    description: str = Field(min_length=1)

    previous_operations: list[GeneratedOperationReference] = Field(
        default_factory=list
    )
    next_operations: list[GeneratedOperationReference] = Field(
        default_factory=list
    )
    branches: list[GeneratedOperationBranch] = Field(default_factory=list)

    input_documents: list[GeneratedSemanticItem] = Field(default_factory=list)
    output_documents: list[GeneratedSemanticItem] = Field(default_factory=list)
    input_document_names: list[str] = Field(default_factory=list)
    output_document_names: list[str] = Field(default_factory=list)

    associated_notes: list[GeneratedAssociatedNote] = Field(
        default_factory=list
    )
    business_rules: list[GeneratedBusinessRule] = Field(default_factory=list)
    incorporated_note_ids: list[str] = Field(default_factory=list)
    missing_note_ids: list[str] = Field(default_factory=list)

    confidence: float = Field(ge=0.0, le=1.0)
    requires_validation: bool = False
    warnings: list[str] = Field(default_factory=list)
    validation_issue_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_note_coverage(self) -> "GeneratedOperation":
        associated_ids = {note.id for note in self.associated_notes}
        incorporated_ids = set(self.incorporated_note_ids)
        missing_ids = set(self.missing_note_ids)

        overlap = incorporated_ids & missing_ids
        if overlap:
            raise ValueError(
                "A note cannot be both incorporated and missing: "
                + ", ".join(sorted(overlap))
            )

        unknown_ids = (incorporated_ids | missing_ids) - associated_ids
        if unknown_ids:
            raise ValueError(
                "Note coverage references unknown associated notes: "
                + ", ".join(sorted(unknown_ids))
            )

        if missing_ids and not self.requires_validation:
            raise ValueError(
                "An operation with missing notes must require validation."
            )

        return self

    @model_validator(mode="after")
    def validate_document_names(self) -> "GeneratedOperation":
        expected_input_names = [
            item.name for item in self.input_documents if item.name
        ]
        expected_output_names = [
            item.name for item in self.output_documents if item.name
        ]

        if expected_input_names and self.input_document_names != expected_input_names:
            raise ValueError(
                "input_document_names does not match input_documents."
            )

        if expected_output_names and self.output_document_names != expected_output_names:
            raise ValueError(
                "output_document_names does not match output_documents."
            )

        return self


class GeneratedProcedure(GeneratedBaseModel):
    process_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    operation_count: int = Field(ge=0)

    decisions: list[GeneratedDecision] = Field(default_factory=list)
    operations: list[GeneratedOperation] = Field(default_factory=list)

    # Kept for compatibility with the previous generator contract.
    generation_warnings: list[str] = Field(default_factory=list)
    quality_summary: GeneratedProcedureQualitySummary | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "GeneratedProcedure":
        if self.operation_count != len(self.operations):
            raise ValueError(
                "operation_count does not match the number of operations."
            )

        operation_ids = [operation.bpmn_element_id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("Duplicate BPMN operation IDs were found.")

        operation_numbers = [operation.operation_number for operation in self.operations]
        if len(operation_numbers) != len(set(operation_numbers)):
            raise ValueError("Duplicate operation numbers were found.")

        operation_id_set = set(operation_ids)
        operation_number_set = set(operation_numbers)

        for decision in self.decisions:
            if decision.source_bpmn_element_id not in operation_id_set:
                raise ValueError(
                    "A decision references an unknown source operation: "
                    f"{decision.source_bpmn_element_id}"
                )
            if decision.source_operation_number not in operation_number_set:
                raise ValueError(
                    "A decision references an unknown source operation number: "
                    f"{decision.source_operation_number}"
                )
            unknown_targets = {
                branch.target_element_id
                for branch in decision.branches
                if branch.target_element_id not in operation_id_set
            }
            if unknown_targets:
                raise ValueError(
                    "A decision references unknown target operations: "
                    + ", ".join(sorted(unknown_targets))
                )

        if self.quality_summary is not None:
            expected_validation = sorted(
                operation.operation_number
                for operation in self.operations
                if operation.requires_validation
            )
            declared_validation = sorted(
                self.quality_summary.operations_requiring_validation
            )
            if declared_validation != expected_validation:
                raise ValueError(
                    "quality_summary.operations_requiring_validation "
                    "does not match operation validation flags."
                )

            expected_missing_notes = sum(
                len(operation.missing_note_ids)
                for operation in self.operations
            )
            if self.quality_summary.missing_note_count != expected_missing_notes:
                raise ValueError(
                    "quality_summary.missing_note_count does not match "
                    "operation missing-note data."
                )

        return self

    @property
    def operations_requiring_validation(self) -> list[int]:
        if self.quality_summary is not None:
            return list(
                self.quality_summary.operations_requiring_validation
            )
        return [
            operation.operation_number
            for operation in self.operations
            if operation.requires_validation
        ]

    @property
    def placeholder_count(self) -> int:
        return (
            self.quality_summary.placeholder_count
            if self.quality_summary is not None
            else 0
        )

    @property
    def missing_note_count(self) -> int:
        if self.quality_summary is not None:
            return self.quality_summary.missing_note_count
        return sum(
            len(operation.missing_note_ids)
            for operation in self.operations
        )


class GeneratedProcedureLoadError(ValueError):
    """Raised when generated procedure JSON cannot be loaded."""


def load_generated_procedure(path: str | Path) -> GeneratedProcedure:
    """Load and validate the Qwen-generated procedure.

    Invalid generation-quality output is rejected before a Word document can
    be produced.  Operations explicitly marked for human validation are still
    accepted and remain visible in the final bundle.
    """

    input_path = Path(path)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Generated procedure file not found: {input_path}"
        )

    try:
        raw_data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GeneratedProcedureLoadError(
            f"Invalid generated procedure JSON: {exc}"
        ) from exc

    try:
        procedure = GeneratedProcedure.model_validate(raw_data)
    except ValidationError as exc:
        raise GeneratedProcedureLoadError(
            "Generated procedure does not match the expected schema: "
            f"{exc}"
        ) from exc

    if procedure.placeholder_count:
        raise GeneratedProcedureLoadError(
            "Generated procedure still contains "
            f"{procedure.placeholder_count} placeholder(s)."
        )

    if procedure.missing_note_count:
        raise GeneratedProcedureLoadError(
            "Generated procedure still has "
            f"{procedure.missing_note_count} missing BPMN note(s)."
        )

    return procedure
