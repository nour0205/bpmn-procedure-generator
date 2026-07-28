"""Shared document models used by procedure and specification generators."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentBaseModel(BaseModel):
    """Common configuration for document-layer models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class DocumentOperationKind(StrEnum):
    """Business meaning of a generated operation."""

    OPERATION = "operation"
    SUBPROCESS = "subprocess"
    BUSINESS_EVENT = "business_event"


class DocumentMetadata(DocumentBaseModel):
    """Administrative information shared by generated documents."""

    process_id: str
    title: str

    domain: str | None = None
    reference: str | None = None
    creation_date: str | None = None
    last_modified_date: str | None = None
    version: str = "V1.0"

    source_bpmn_path: str | None = None


class DocumentActor(DocumentBaseModel):
    """An actor involved in the business process."""

    id: str
    name: str
    source_type: str
    operation_ids: list[str] = Field(default_factory=list)


class DocumentNote(DocumentBaseModel):
    """Original BPMN annotation preserved for traceability."""

    id: str
    text: str
    incorporated_in_description: bool = False


class DocumentBranch(DocumentBaseModel):
    """A decision branch originating from a gateway."""

    gateway_id: str
    gateway_name: str | None = None
    label: str | None = None
    condition: str | None = None
    is_default: bool = False

    target_operation_id: str
    target_operation_name: str | None = None


class DocumentOperation(DocumentBaseModel):
    """One operation displayed in the procedure and specification."""

    number: int
    bpmn_element_id: str

    raw_name: str
    description: str

    actor_id: str | None = None
    actor_name: str | None = None

    element_kind: DocumentOperationKind
    source_type: str
    execution_mode: str | None = None
    event_role: str | None = None

    previous_operation_ids: list[str] = Field(default_factory=list)
    next_operation_ids: list[str] = Field(default_factory=list)

    input_document_names: list[str] = Field(default_factory=list)
    output_document_names: list[str] = Field(default_factory=list)

    notes: list[DocumentNote] = Field(default_factory=list)
    branches: list[DocumentBranch] = Field(default_factory=list)

    confidence: float = Field(ge=0.0, le=1.0)
    requires_validation: bool = False
    warnings: list[str] = Field(default_factory=list)
    validation_issue_codes: list[str] = Field(default_factory=list)


class DocumentBusinessDocument(DocumentBaseModel):
    """A business document used or produced by operations."""

    id: str
    name: str
    source_type: str

    produced_by_operation_ids: list[str] = Field(default_factory=list)
    consumed_by_operation_ids: list[str] = Field(default_factory=list)


class DocumentValidationSummary(DocumentBaseModel):
    """Validation status inherited from parsing and generation."""

    parser_is_valid: bool
    parser_error_count: int
    parser_warning_count: int
    parser_issue_codes: list[str] = Field(default_factory=list)

    generation_warnings: list[str] = Field(default_factory=list)

    generation_operations_requiring_validation: list[int] = Field(
        default_factory=list
    )
    generation_placeholder_count: int = Field(default=0, ge=0)
    generation_missing_note_count: int = Field(default=0, ge=0)


class DocumentBusinessRule(DocumentBaseModel):
    """A business rule derived from a BPMN annotation."""

    operation_number: int
    text: str
    source_note_id: str


class ProcedureDocumentData(DocumentBaseModel):
    """Data required to populate the procedure template."""

    purpose: str | None = None
    related_procedures: list[str] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)

    operations: list[DocumentOperation] = Field(default_factory=list)
    documents: list[DocumentBusinessDocument] = Field(default_factory=list)

    internal_controls: list[dict[str, str]] = Field(default_factory=list)
    business_rules: list[DocumentBusinessRule] = Field(
        default_factory=list
    )


class SpecificationDocumentData(DocumentBaseModel):
    """Detailed semantic data required for the specification document."""

    process_overview: str | None = None
    detailed_narrative: str | None = None

    actors: list[DocumentActor] = Field(default_factory=list)
    operations: list[DocumentOperation] = Field(default_factory=list)
    documents: list[DocumentBusinessDocument] = Field(default_factory=list)

    subprocess_operation_ids: list[str] = Field(default_factory=list)
    business_event_operation_ids: list[str] = Field(default_factory=list)
    decision_gateway_ids: list[str] = Field(default_factory=list)

    systems: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_points: list[str] = Field(default_factory=list)


class DocumentBundle(DocumentBaseModel):
    """Single trusted source for every generated document."""

    metadata: DocumentMetadata
    actors: list[DocumentActor] = Field(default_factory=list)
    documents: list[DocumentBusinessDocument] = Field(default_factory=list)
    operations: list[DocumentOperation] = Field(default_factory=list)

    validation: DocumentValidationSummary

    procedure: ProcedureDocumentData
    specification: SpecificationDocumentData

    @property
    def operation_count(self) -> int:
        return len(self.operations)
