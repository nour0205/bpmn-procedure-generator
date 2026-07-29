"""Independent BPMN narrative generation package."""

from narrative_generation.config import NarrativeGenerationConfig
from narrative_generation.runner import NarrativeRunResult, run_narrative_generation

__all__ = [
    "NarrativeGenerationConfig",
    "NarrativeRunResult",
    "run_narrative_generation",
]
