"""Data contracts for the local/Kaggle automation pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GenerationMode = Literal["procedure", "narrative", "both"]
WorkerStatus = Literal["success", "failed", "skipped"]


class AutomationBaseModel(BaseModel):
    """Strict base model shared by automation contracts."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class RunManifest(AutomationBaseModel):
    """Immutable identity and configuration of one generation run."""

    schema_version: str = "1.0"
    run_id: str = Field(min_length=1)
    created_at_utc: datetime

    process_slug: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    process_title: str = Field(min_length=1)
    bpmn_filename: str = Field(min_length=1)
    bpmn_path: str = Field(min_length=1)

    generation_mode: GenerationMode
    model_name: str = Field(min_length=1)
    git_commit: str | None = None
    git_branch: str | None = None
    git_dirty: bool = False

    notebook_filename: str = (
        "qwen-bpmn-combined-worker.ipynb"
    )
    expected_outputs: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_expected_outputs(self) -> "RunManifest":
        required = {"run_result.json"}

        if self.generation_mode in {"procedure", "both"}:
            required.update(
                {
                    "generated_procedure.json",
                    "procedure_validation_report.json",
                }
            )

        if self.generation_mode in {"narrative", "both"}:
            required.update(
                {
                    "generated_narrative.json",
                    "narrative_validation_report.json",
                }
            )

        missing = sorted(required - set(self.expected_outputs))
        if missing:
            raise ValueError(
                "expected_outputs is missing required files: "
                + ", ".join(missing)
            )

        return self


class WorkerComponentResult(AutomationBaseModel):
    """Status returned by one independent Kaggle generator."""

    status: WorkerStatus
    generated_file: str | None = None
    validation_file: str | None = None
    preview_file: str | None = None
    quality: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "WorkerComponentResult":
        if self.status == "success":
            if not self.generated_file or not self.validation_file:
                raise ValueError(
                    "Successful components must declare generated_file "
                    "and validation_file."
                )

        if self.status == "failed" and not self.error_message:
            raise ValueError(
                "Failed components must declare error_message."
            )

        return self


class WorkerRunResult(AutomationBaseModel):
    """Combined result written by the Kaggle worker."""

    schema_version: str = "1.0"
    run_id: str = Field(min_length=1)
    generation_mode: GenerationMode

    process_slug: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    process_title: str = Field(min_length=1)

    model_name: str = Field(min_length=1)
    git_commit: str | None = None

    procedure: WorkerComponentResult
    narrative: WorkerComponentResult


class FinalizationReport(AutomationBaseModel):
    """Local report produced after validating downloaded outputs."""

    run_id: str
    process_slug: str
    process_id: str
    process_title: str
    generation_mode: GenerationMode

    procedure_validation: str
    narrative_validation: str
    word_generation: str
    copied_files: list[str] = Field(default_factory=list)
    generated_documents: list[str] = Field(default_factory=list)
    final_status: Literal["success", "failed"]
