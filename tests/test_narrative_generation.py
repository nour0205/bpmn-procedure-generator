from __future__ import annotations

import json
from pathlib import Path

from narrative_generation.config import NarrativeGenerationConfig
from narrative_generation.inputs import load_and_merge_inputs
from narrative_generation.runner import run_narrative_generation
from narrative_generation.units import (
    build_narrative_units,
    resolved_structural_operation_numbers,
)


FIXTURES = Path(__file__).parent / "fixtures"
PLAN_PATH = FIXTURES / "suivi_commandes_narrative_plan.json"
CONTEXTS_PATH = FIXTURES / "suivi_commandes_operation_contexts.json"


def test_build_units_covers_every_operation_once() -> None:
    loaded = load_and_merge_inputs(
        narrative_plan_path=PLAN_PATH,
        operation_contexts_path=CONTEXTS_PATH,
    )

    units, coverage, warnings = build_narrative_units(
        loaded.narrative_plan
    )

    assert len(units) == 7
    assert coverage["missing_operation_numbers"] == []
    assert coverage["duplicated_operation_numbers"] == []
    assert coverage["owned_operation_numbers"] == list(
        range(1, 12)
    )
    assert coverage["referenced_operation_numbers"] == [7]
    assert warnings == []


def test_nested_decision_prefix_and_resolved_structures() -> None:
    loaded = load_and_merge_inputs(
        narrative_plan_path=PLAN_PATH,
        operation_contexts_path=CONTEXTS_PATH,
    )
    units, _, _ = build_narrative_units(
        loaded.narrative_plan
    )

    nested = next(
        unit
        for unit in units
        if unit["unit_id"] == "block_2_decision"
    )

    assert nested["prefix"] == (
        "Dans le prolongement du scénario « Oui », "
    )
    assert resolved_structural_operation_numbers(
        loaded.narrative_plan
    ) == {5, 7}


def test_runner_writes_word_compatible_narrative(
    tmp_path: Path,
) -> None:
    result = run_narrative_generation(
        narrative_plan_path=PLAN_PATH,
        operation_contexts_path=CONTEXTS_PATH,
        output_dir=tmp_path,
        config=NarrativeGenerationConfig(
            use_model=False,
        ),
    )

    generated = json.loads(
        result.generated_narrative_path.read_text(
            encoding="utf-8"
        )
    )

    assert set(generated) == {
        "process_id",
        "process_title",
        "model_name",
        "paragraphs",
        "quality_summary",
    }
    assert set(generated["quality_summary"]) == {
        "paragraph_count",
        "placeholder_count",
        "max_paragraph_characters",
    }
    assert (
        "Dans le prolongement du scénario « Oui »"
        in generated["paragraphs"][3]
    )
    assert generated["quality_summary"]["placeholder_count"] == 0
