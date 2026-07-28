"""Models representing the deterministic narrative plan."""

from __future__ import annotations

from pydantic import Field

from .narrative_models import NarrativeBaseModel


class NarrativePlanOperation(NarrativeBaseModel):
    """Compact operation information used by narrative generation."""

    number: int
    raw_name: str

    actor: str | None = None
    execution_mode: str
    event_role: str | None = None

    previous_operation_numbers: list[int] = Field(
        default_factory=list
    )
    next_operation_numbers: list[int] = Field(
        default_factory=list
    )

    notes: list[str] = Field(
        default_factory=list
    )
    business_rules: list[str] = Field(
        default_factory=list
    )

    input_documents: list[str] = Field(
        default_factory=list
    )
    output_documents: list[str] = Field(
        default_factory=list
    )


class NarrativePlanBranch(NarrativeBaseModel):
    """One explicit branch of a process decision."""

    label: str
    condition: str | None = None

    target_operation_number: int
    target_operation_name: str

    path_operation_numbers: list[int] = Field(
        default_factory=list
    )

    is_loop_back: bool = False
    loop_back_to_operation_number: int | None = None

    converges_to_operation_number: int | None = None


class NarrativePlanDecision(NarrativeBaseModel):
    """One decision and its explicit outgoing branches."""

    source_operation_number: int
    gateway_name: str | None = None

    # Values currently used:
    # exclusive, unknown
    routing_mode: str = "unknown"

    branches: list[NarrativePlanBranch] = Field(
        default_factory=list
    )

    shared_convergence_operation_number: int | None = None


class NarrativePlanConvergence(NarrativeBaseModel):
    """One operation reached from multiple incoming paths."""

    operation_number: int
    operation_name: str

    incoming_operation_numbers: list[int] = Field(
        default_factory=list
    )


class NarrativeWritingBranch(NarrativeBaseModel):
    """One branch arranged specifically for narrative writing."""

    label: str
    condition: str | None = None

    operation_numbers: list[int] = Field(
        default_factory=list
    )

    nested_decision_source_numbers: list[int] = Field(
        default_factory=list
    )

    is_loop_back: bool = False
    loop_back_to_operation_number: int | None = None

    convergence_operation_number: int | None = None


class NarrativeWritingBlock(NarrativeBaseModel):
    """One ordered block that the LLM must narrate once."""

    order: int

    # sequence, decision, nested_decision or convergence
    block_type: str

    source_operation_number: int | None = None

    parent_decision_source_number: int | None = None
    parent_branch_label: str | None = None

    gateway_name: str | None = None
    routing_mode: str | None = None

    operation_numbers: list[int] = Field(
        default_factory=list
    )

    branches: list[NarrativeWritingBranch] = Field(
        default_factory=list
    )

    convergence_operation_number: int | None = None


class NarrativePlan(NarrativeBaseModel):
    """Complete deterministic writing plan for the narrative LLM."""

    process_id: str
    process_title: str
    end_event_status: str

    entry_operation_numbers: list[int] = Field(
        default_factory=list
    )

    terminal_operation_numbers: list[int] = Field(
        default_factory=list
    )

    operations: list[NarrativePlanOperation] = Field(
        default_factory=list
    )

    decisions: list[NarrativePlanDecision] = Field(
        default_factory=list
    )

    convergences: list[NarrativePlanConvergence] = Field(
        default_factory=list
    )

    writing_blocks: list[NarrativeWritingBlock] = Field(
        default_factory=list
    )
