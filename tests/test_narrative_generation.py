from __future__ import annotations

import json
from pathlib import Path

from narrative_generation.config import NarrativeGenerationConfig
from narrative_generation.inputs import load_and_merge_inputs
from narrative_generation.models import GeneratedUnit
from narrative_generation.runner import run_narrative_generation
from narrative_generation.units import (
    build_narrative_units,
    resolved_structural_operation_numbers,
)
from narrative_generation.validation import validate_generated_unit


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
    assert [unit["unit_id"] for unit in units] == [
        "block_1_decision",
        "block_1_branch_1",
        "block_2_decision",
        "block_2_branch_1",
        "block_2_branch_2",
        "block_1_branch_2",
        "block_3_convergence",
    ]
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

    nested_paragraph_index = next(
        index
        for index, paragraph in enumerate(
            generated["paragraphs"]
        )
        if "Dans le prolongement du scénario « Oui »"
        in paragraph
    )
    parent_non_index = next(
        index
        for index, paragraph in enumerate(
            generated["paragraphs"]
        )
        if (
            paragraph.startswith(
                "Dans le scénario « Non »"
            )
            and "reporting" in paragraph
        )
    )

    assert nested_paragraph_index < parent_non_index
    assert generated["quality_summary"]["placeholder_count"] == 0


def test_locked_facts_are_injected_deterministically() -> None:
    unit = {
        "unit_id": "mixed_unit",
        "facts": [
            {
                "fact_id": "op_1",
                "locked": False,
                "kind": "operation",
                "text": "Phrase source.",
                "source_text": "Phrase source.",
                "required_tokens": [],
                "timer_labels": [],
                "actor": None,
                "execution_mode": None,
                "allow_purpose_clause": False,
            },
            {
                "fact_id": "decision_rule",
                "locked": True,
                "kind": "decision",
                "text": (
                    "La décision « Validation ? » distingue des "
                    "scénarios alternatifs : « Oui », « Non »."
                ),
                "source_text": "Validation Oui Non",
                "required_tokens": [],
                "timer_labels": [],
                "actor": None,
                "execution_mode": None,
                "allow_purpose_clause": False,
            },
        ],
    }
    generated = GeneratedUnit.model_validate(
        {
            "sentences": [
                {
                    "fact_id": "op_1",
                    "sentence": "Phrase reformulée.",
                }
            ]
        }
    )

    result = validate_generated_unit(unit, generated)

    assert result == [
        "Phrase reformulée.",
        (
            "La décision « Validation? » distingue des "
            "scénarios alternatifs: « Oui », « Non »."
        ),
    ]
