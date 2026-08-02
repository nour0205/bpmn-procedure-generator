"""Document-oriented models derived from BPMN semantics."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ProcedureBaseModel(BaseModel):
    """Shared configuration for procedure models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class ProcedureElementKind(StrEnum):
    """How a BPMN activity is presented in the procedure."""

    OPERATION = "operation"
    SUBPROCESS = "subprocess"
    BUSINESS_EVENT = "business_event"


class ProcedureActor(ProcedureBaseModel):
    """An actor responsible for one or more procedure operations."""

    id: str
    name: str
    source_type: str
    process_id: str | None = None
    participant_id: str | None = None


class ProcedureDocument(ProcedureBaseModel):
    """A business document used or produced by the procedure."""

    id: str
    name: str
    source_type: str
    produced_by_operation_ids: list[str] = Field(default_factory=list)
    consumed_by_operation_ids: list[str] = Field(default_factory=list)


class ProcedureNote(ProcedureBaseModel):
    """An annotation or documentation item associated with an operation."""

    id: str
    text: str
    associated_operation_ids: list[str] = Field(default_factory=list)
    source_type: str = "textAnnotation"


class ProcedureBranch(ProcedureBaseModel):
    """A branch originating from a BPMN gateway."""

    flow_id: str
    gateway_id: str
    gateway_name: str | None = None
    label: str | None = None
    condition: str | None = None
    is_default: bool = False
    is_loop_back: bool = False
    target_element_id: str


class ProcedureOperation(ProcedureBaseModel):
    """One numbered operation in the generated procedure."""

    number: int
    bpmn_element_id: str
    raw_name: str
    element_kind: ProcedureElementKind
    source_type: str

    process_id: str
    actor_id: str | None = None
    actor_name: str | None = None

    input_document_ids: list[str] = Field(default_factory=list)
    output_document_ids: list[str] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)

    previous_operation_ids: list[str] = Field(default_factory=list)
    next_operation_ids: list[str] = Field(default_factory=list)

    preceding_gateway_ids: list[str] = Field(default_factory=list)
    following_gateway_ids: list[str] = Field(default_factory=list)
    branches: list[ProcedureBranch] = Field(default_factory=list)

    parent_subprocess_id: str | None = None
    order_ambiguous: bool = False


class ProcedureMetadata(ProcedureBaseModel):
    """Basic procedure identification information."""

    process_id: str
    title: str
    source_path: str
    participant_name: str | None = None


class ProcedureValidationSummary(ProcedureBaseModel):
    """Validation information forwarded from the BPMN parser."""

    is_valid: bool
    error_count: int
    warning_count: int
    issue_codes: list[str] = Field(default_factory=list)


class ProcedureModel(ProcedureBaseModel):
    """Document-oriented representation consumed by the agent."""

    metadata: ProcedureMetadata

    actors: list[ProcedureActor] = Field(default_factory=list)
    operations: list[ProcedureOperation] = Field(default_factory=list)
    documents: list[ProcedureDocument] = Field(default_factory=list)
    notes: list[ProcedureNote] = Field(default_factory=list)

    validation: ProcedureValidationSummary

    @computed_field
    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def operation_by_id(
        self,
        bpmn_element_id: str,
    ) -> ProcedureOperation | None:
        return next(
            (
                operation
                for operation in self.operations
                if operation.bpmn_element_id == bpmn_element_id
            ),
            None,
        )
