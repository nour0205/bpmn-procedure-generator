"""Load and validate a generated process narrative."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .narrative_models import GeneratedNarrative


class NarrativeLoadError(ValueError):
    """Raised when a generated narrative cannot be loaded."""


def load_generated_narrative(path: str | Path) -> GeneratedNarrative:
    """Load a generated narrative JSON file and enforce quality gates."""

    source_path = Path(path)

    if not source_path.exists():
        raise FileNotFoundError(
            f"Generated narrative not found: {source_path}"
        )

    try:
        raw_data = json.loads(source_path.read_text(encoding="utf-8"))
        narrative = GeneratedNarrative.model_validate(raw_data)
    except json.JSONDecodeError as exc:
        raise NarrativeLoadError(
            f"Invalid generated narrative JSON: {exc}"
        ) from exc
    except ValidationError as exc:
        raise NarrativeLoadError(
            f"Invalid generated narrative schema: {exc}"
        ) from exc

    if narrative.placeholder_count:
        raise NarrativeLoadError(
            "The generated narrative still contains "
            f"{narrative.placeholder_count} placeholder(s)."
        )

    return narrative
