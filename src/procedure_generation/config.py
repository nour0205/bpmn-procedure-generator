"""Configuration for procedure generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProcedureGenerationConfig:
    """Runtime configuration shared by local tests and Kaggle inference."""

    model_name: str = "Qwen/Qwen3-8B"
    prompt_version: str = "independent-procedure-v1.0"
    max_attempts_per_operation: int = 3
    max_new_tokens_per_operation: int = 420
    use_model: bool = True
    cache_dir: Path | None = None
    title_override: str | None = None

    def __post_init__(self) -> None:
        if self.max_attempts_per_operation < 1:
            raise ValueError(
                "max_attempts_per_operation must be at least 1."
            )

        if self.max_new_tokens_per_operation < 64:
            raise ValueError(
                "max_new_tokens_per_operation must be at least 64."
            )

        if (
            self.title_override is not None
            and not self.title_override.strip()
        ):
            raise ValueError(
                "title_override cannot be blank."
            )
