"""Strict Pydantic contracts for procedure generation."""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class GeneratedOperationContent(StrictModel):
    description: str = Field(min_length=1)
    incorporated_note_ids: list[str] = Field(
        default_factory=list
    )


class AssociatedNote(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SemanticItem(StrictModel):
    id: str | None = None
    name: str | None = None
    text: str | None = None
    label: str | None = None
    description: str | None = None
    value: str | None = None
    content: str | None = None
    source_type: str | None = None
    produced_by_operation_ids: list[str] = Field(
        default_factory=list
    )
    consumed_by_operation_ids: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def require_readable_value(self) -> "SemanticItem":
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
                "A semantic item must contain a readable value."
            )

        return self


BusinessRule = Annotated[
    str | SemanticItem,
    Field(union_mode="left_to_right"),
]


class OperationReference(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    actor_name: str | None = None
    element_kind: str = Field(min_length=1)


class OperationBranch(StrictModel):
    gateway_id: str = Field(min_length=1)
    gateway_name: str | None = None
    label: str | None = None
    condition: str | None = None
    is_default: bool = False
    target_element_id: str = Field(min_length=1)
    target_name: str | None = None


class DecisionBranch(StrictModel):
    label: str | None = None
    condition: str | None = None
    is_default: bool = False
    target_element_id: str = Field(min_length=1)
    target_name: str | None = None


class Decision(StrictModel):
    gateway_id: str = Field(min_length=1)
    gateway_name: str | None = None
    source_operation_number: int = Field(ge=1)
    source_bpmn_element_id: str = Field(min_length=1)
    branches: list[DecisionBranch] = Field(
        min_length=1
    )


class ProcedureQualitySummary(StrictModel):
    operations_requiring_validation: list[int] = Field(
        default_factory=list
    )
    placeholder_count: int = Field(
        default=0,
        ge=0,
    )
    missing_note_count: int = Field(
        default=0,
        ge=0,
    )


class GeneratedOperation(StrictModel):
    operation_number: int = Field(ge=1)
    bpmn_element_id: str = Field(min_length=1)

    raw_name: str | None = None
    actor_name: str | None = None
    element_kind: str | None = None
    source_type: str | None = None
    execution_mode: str | None = None
    event_role: str | None = None

    description: str = Field(min_length=1)

    previous_operations: list[
        OperationReference
    ] = Field(default_factory=list)
    next_operations: list[
        OperationReference
    ] = Field(default_factory=list)
    branches: list[
        OperationBranch
    ] = Field(default_factory=list)

    input_documents: list[
        SemanticItem
    ] = Field(default_factory=list)
    output_documents: list[
        SemanticItem
    ] = Field(default_factory=list)
    input_document_names: list[str] = Field(
        default_factory=list
    )
    output_document_names: list[str] = Field(
        default_factory=list
    )

    associated_notes: list[
        AssociatedNote
    ] = Field(default_factory=list)
    business_rules: list[
        BusinessRule
    ] = Field(default_factory=list)
    incorporated_note_ids: list[str] = Field(
        default_factory=list
    )
    missing_note_ids: list[str] = Field(
        default_factory=list
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    requires_validation: bool = False
    warnings: list[str] = Field(
        default_factory=list
    )
    validation_issue_codes: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_note_coverage(
        self,
    ) -> "GeneratedOperation":
        associated_ids = {
            note.id
            for note in self.associated_notes
        }
        incorporated_ids = set(
            self.incorporated_note_ids
        )
        missing_ids = set(
            self.missing_note_ids
        )

        overlap = (
            incorporated_ids
            & missing_ids
        )

        if overlap:
            raise ValueError(
                "A note cannot be both incorporated and missing: "
                + ", ".join(sorted(overlap))
            )

        unknown = (
            incorporated_ids
            | missing_ids
        ) - associated_ids

        if unknown:
            raise ValueError(
                "Unknown note IDs: "
                + ", ".join(sorted(unknown))
            )

        if (
            missing_ids
            and not self.requires_validation
        ):
            raise ValueError(
                "An operation with missing notes "
                "must require validation."
            )

        return self

    @model_validator(mode="after")
    def validate_document_names(
        self,
    ) -> "GeneratedOperation":
        expected_inputs = [
            item.name
            for item in self.input_documents
            if item.name
        ]
        expected_outputs = [
            item.name
            for item in self.output_documents
            if item.name
        ]

        if (
            expected_inputs
            and self.input_document_names
            != expected_inputs
        ):
            raise ValueError(
                "input_document_names does not "
                "match input_documents."
            )

        if (
            expected_outputs
            and self.output_document_names
            != expected_outputs
        ):
            raise ValueError(
                "output_document_names does not "
                "match output_documents."
            )

        return self


class GeneratedProcedure(StrictModel):
    process_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    operation_count: int = Field(ge=0)
    decisions: list[Decision] = Field(
        default_factory=list
    )
    operations: list[
        GeneratedOperation
    ] = Field(default_factory=list)
    generation_warnings: list[str] = Field(
        default_factory=list
    )
    quality_summary: (
        ProcedureQualitySummary | None
    ) = None

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "GeneratedProcedure":
        if self.operation_count != len(
            self.operations
        ):
            raise ValueError(
                "operation_count does not match "
                "the number of operations."
            )

        operation_numbers = [
            operation.operation_number
            for operation in self.operations
        ]
        operation_ids = [
            operation.bpmn_element_id
            for operation in self.operations
        ]

        if len(operation_numbers) != len(
            set(operation_numbers)
        ):
            raise ValueError(
                "Duplicate operation numbers were found."
            )

        if len(operation_ids) != len(
            set(operation_ids)
        ):
            raise ValueError(
                "Duplicate BPMN element IDs were found."
            )

        number_set = set(operation_numbers)
        id_set = set(operation_ids)

        for decision in self.decisions:
            if (
                decision.source_operation_number
                not in number_set
            ):
                raise ValueError(
                    "A decision references an unknown "
                    "source operation number."
                )

            if (
                decision.source_bpmn_element_id
                not in id_set
            ):
                raise ValueError(
                    "A decision references an unknown "
                    "source BPMN element."
                )

            unknown_targets = {
                branch.target_element_id
                for branch in decision.branches
                if branch.target_element_id
                not in id_set
            }

            if unknown_targets:
                raise ValueError(
                    "A decision references unknown "
                    "target elements: "
                    + ", ".join(
                        sorted(
                            unknown_targets
                        )
                    )
                )

        return self
