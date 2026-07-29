"""Configuration for narrative generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NarrativeGenerationConfig:
    """Runtime configuration shared by local tests and Kaggle inference."""

    model_name: str = "Qwen/Qwen3-8B"
    prompt_version: str = "independent-narrative-v1.2"
    max_attempts_per_unit: int = 3
    max_new_tokens_per_unit: int = 650
    use_model: bool = True
    cache_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.max_attempts_per_unit < 1:
            raise ValueError("max_attempts_per_unit must be at least 1.")

        if self.max_new_tokens_per_unit < 64:
            raise ValueError("max_new_tokens_per_unit must be at least 64.")
